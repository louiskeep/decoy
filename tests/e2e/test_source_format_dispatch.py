"""Sources are read by their DECLARED `format`, never by file suffix.

Covers the CLI half of the source-format dispatch plan
(docs/plans/2026-09-30-cli-source-format-dispatch.md, A5b): fixed-width
sources read through the engine's public reader, the declared format wins
over the suffix in plain and chunked modes, `--chunked` refuses fixed-width,
and native eligibility follows the declared format.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app
from decoy.api import ConfigValidationError
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_LAYOUT: dict[str, Any] = {
    "columns": [
        {"name": "id", "start": 0, "width": 6},
        {"name": "name", "start": 6, "width": 10},
        {"name": "age", "start": 16, "width": 3, "type": "int", "align": "right"},
    ]
}

_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "name", "strategy": "hash", "namespace": "name_ns"},
    {"name": "age", "strategy": "passthrough"},
]

_PEOPLE = [("A00001", "Alice", 31), ("A00002", "Bob", 4), ("A00003", "Carol", 57)]


def _write_fixed_width(path: Path, rows=_PEOPLE) -> None:
    lines = [f"{i:<6}{n:<10}{a:>3}" for i, n, a in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [p[0] for p in _PEOPLE],
            "name": [p[1] for p in _PEOPLE],
            "age": [p[2] for p in _PEOPLE],
        }
    )


def _config(
    tmp_path: Path,
    src: Path,
    fmt: str,
    *,
    layout: dict | None = None,
    tgt_name: str = "out.csv",
) -> Path:
    source: dict[str, Any] = {"type": "file", "format": fmt, "path": str(src)}
    if layout is not None:
        source["layout"] = layout
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"people": source},
        "tables": [{"name": "people", "columns": _COLUMNS}],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / tgt_name)}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def _fixed_width_config(tmp_path: Path, **kw) -> Path:
    src = tmp_path / "people.dat"
    _write_fixed_width(src)
    return _config(tmp_path, src, "fixed_width", layout=_LAYOUT, **kw)


def _engine_expected(tmp_path: Path, config_path: Path) -> pd.DataFrame:
    """Masked output the engine produces from `read_fixed_width` output."""
    from decoy_engine import PipelineConfig, read_fixed_width, run_pipeline
    from decoy_engine import __version__ as engine_version

    config_dict = PipelineConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    ).model_dump()
    src = config_dict["sources"]["people"]
    table = pa.Table.from_pandas(read_fixed_width(src["path"], src["layout"]), preserve_index=False)
    result = run_pipeline(
        config_dict, {"people": table}, engine_version=engine_version, derive_key=None
    )
    return result.outputs["people"].to_pandas()


# --------------------------------------------------------------------------
# Acceptance 2: fixed_width read per layout, matches the engine's reader
# --------------------------------------------------------------------------


def test_read_source_fixed_width_has_typed_columns(tmp_path: Path):
    from decoy.cli._sources import read_source

    cfg = yaml.safe_load(_fixed_width_config(tmp_path).read_text())
    table = read_source("people", cfg["sources"]["people"], tmp_path)
    assert table.schema.field("id").type == pa.string()
    assert table.schema.field("name").type == pa.string()
    assert table.schema.field("age").type == pa.int64()
    assert table.column("age").to_pylist() == [31, 4, 57]
    assert table.column("name").to_pylist() == ["Alice", "Bob", "Carol"]


def test_run_fixed_width_matches_engine_on_public_reader(tmp_path: Path):
    config = _fixed_width_config(tmp_path)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    got = pd.read_csv(tmp_path / "out.csv", dtype=str)
    expected = _engine_expected(tmp_path, config).astype(str)
    pd.testing.assert_frame_equal(got, expected, check_dtype=False)
    assert got["age"].tolist() == ["31", "4", "57"]
    assert got["name"].tolist() != ["Alice", "Bob", "Carol"]


def test_demo_path_fixed_width_matches_engine(tmp_path: Path):
    from decoy.cli.demo import _run_v2_mask

    config = _fixed_width_config(tmp_path)
    _run_v2_mask(config)
    got = pd.read_csv(tmp_path / "out.csv", dtype=str)
    assert list(got.columns) == ["id", "name", "age"]
    assert got["age"].tolist() == ["31", "4", "57"]


def test_mask_api_fixed_width_matches_engine(tmp_path: Path):
    config = _fixed_width_config(tmp_path)
    got = decoy.mask(config=str(config))
    assert list(got.columns) == ["id", "name", "age"]
    assert [int(a) for a in got["age"]] == [31, 4, 57]
    expected = _engine_expected(tmp_path, config)
    pd.testing.assert_frame_equal(got.reset_index(drop=True), expected.reset_index(drop=True))


# --------------------------------------------------------------------------
# Acceptance 3: CSV and Parquet read exactly as before
# --------------------------------------------------------------------------


def test_csv_and_parquet_sources_read_as_before(tmp_path: Path):
    from decoy.cli.run import _load_sources_from_config

    df = _frame()
    csv_path = tmp_path / "in.csv"
    pq_path = tmp_path / "in.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(pq_path, index=False)
    config = {
        "sources": {
            "c": {"type": "file", "format": "csv", "path": str(csv_path)},
            "p": {"type": "file", "format": "parquet", "path": str(pq_path)},
        }
    }
    got = _load_sources_from_config(config, tmp_path)
    assert got["c"].equals(
        pa.Table.from_pandas(pd.read_csv(csv_path, dtype=str), preserve_index=False)
    )
    assert got["p"].equals(pq.read_table(str(pq_path)))


def test_csv_and_parquet_run_output_is_identical(tmp_path: Path):
    df = _frame()
    csv_dir, pq_dir = tmp_path / "c", tmp_path / "p"
    csv_dir.mkdir()
    pq_dir.mkdir()
    df.to_csv(csv_dir / "in.csv", index=False)
    df.to_parquet(pq_dir / "in.parquet", index=False)
    outs = []
    for d, name, fmt in ((csv_dir, "in.csv", "csv"), (pq_dir, "in.parquet", "parquet")):
        config = _config(d, d / name, fmt)
        assert runner.invoke(app, ["run", str(config)]).exit_code == 0
        outs.append((d / "out.csv").read_bytes())
    # Same hash column over the same values: identical bytes regardless of
    # which reader fed the engine (the age column is int64 vs str but
    # serializes identically).
    assert outs[0] == outs[1]


# --------------------------------------------------------------------------
# Acceptance 4: declared format wins over the suffix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("filename", ["data.pq", "data_no_ext"])
@pytest.mark.parametrize("chunked", [False, True])
def test_parquet_declared_wins_over_suffix(tmp_path: Path, filename: str, chunked: bool):
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    _frame().to_parquet(ref_dir / "in.parquet", index=False)
    ref = _config(ref_dir, ref_dir / "in.parquet", "parquet")
    assert runner.invoke(app, ["run", str(ref)]).exit_code == 0

    src = tmp_path / filename
    _frame().to_parquet(src, index=False)
    config = _config(tmp_path, src, "parquet")
    args = ["run", str(config)] + (["--chunked"] if chunked else [])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").read_bytes() == (ref_dir / "out.csv").read_bytes()


@pytest.mark.parametrize("chunked", [False, True])
def test_csv_declared_wins_over_suffix(tmp_path: Path, chunked: bool):
    src = tmp_path / "data.dat"
    _frame().to_csv(src, index=False)
    config = _config(tmp_path, src, "csv")
    args = ["run", str(config)] + (["--chunked"] if chunked else [])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    got = pd.read_csv(tmp_path / "out.csv", dtype=str)
    assert got["id"].tolist() == ["A00001", "A00002", "A00003"]


def test_csv_named_parquet_is_read_as_csv(tmp_path: Path):
    """The suffix lies the other way too: a CSV declared csv but named
    `.parquet` must not be handed to the Parquet reader."""
    src = tmp_path / "data.parquet"
    _frame().to_csv(src, index=False)
    config = _config(tmp_path, src, "csv")
    for args in (["run", str(config)], ["run", str(config), "--chunked"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output


# --------------------------------------------------------------------------
# Acceptance 5: missing / unknown format fails at the schema boundary
# --------------------------------------------------------------------------


def _raw_config(tmp_path: Path, source: dict) -> Path:
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"people": source},
        "tables": [{"name": "people", "columns": _COLUMNS}],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


@pytest.mark.parametrize("fmt", [None, "xlsx"])
def test_missing_or_unknown_format_is_usage_error(tmp_path: Path, fmt):
    src = tmp_path / "in.csv"
    _frame().to_csv(src, index=False)
    source: dict[str, Any] = {"type": "file", "path": str(src)}
    if fmt is not None:
        source["format"] = fmt
    config = _raw_config(tmp_path, source)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_USAGE
    assert not (tmp_path / "out.csv").exists()
    with pytest.raises(ConfigValidationError):
        decoy.mask(config=str(config))


def test_read_source_unknown_format_names_table_and_format(tmp_path: Path):
    from decoy.cli._sources import read_source

    with pytest.raises(ValueError) as excinfo:
        read_source("people", {"type": "file", "format": "xlsx", "path": "x"}, tmp_path)
    assert "people" in str(excinfo.value)
    assert "xlsx" in str(excinfo.value)


# --------------------------------------------------------------------------
# Acceptance 6: fixed_width + --chunked is a preflight usage error
# --------------------------------------------------------------------------


def test_fixed_width_chunked_is_rejected_in_preflight(tmp_path: Path):
    config = _fixed_width_config(tmp_path)
    result = runner.invoke(app, ["run", str(config), "--chunked"])
    assert result.exit_code == EXIT_USAGE
    assert "fixed_width" in result.output
    assert not (tmp_path / "out.csv").exists()


def test_fixed_width_chunked_writes_no_table_even_with_other_tables(tmp_path: Path):
    """The refusal happens before ANY table is written, including an
    earlier csv table in a multi-table config."""
    csv_src = tmp_path / "a.csv"
    _frame().to_csv(csv_src, index=False)
    fw_src = tmp_path / "b.dat"
    _write_fixed_width(fw_src)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "a": {"type": "file", "format": "csv", "path": str(csv_src)},
            "b": {"type": "file", "format": "fixed_width", "path": str(fw_src), "layout": _LAYOUT},
        },
        "tables": [
            {"name": "a", "columns": _COLUMNS},
            {"name": "b", "columns": _COLUMNS},
        ],
        "targets": {
            "a": {"type": "file", "format": "csv", "path": str(tmp_path / "a_out.csv")},
            "b": {"type": "file", "format": "csv", "path": str(tmp_path / "b_out.csv")},
        },
    }
    p = tmp_path / "multi.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["run", str(p), "--chunked"])
    assert result.exit_code == EXIT_USAGE
    assert not (tmp_path / "a_out.csv").exists()
    assert not (tmp_path / "b_out.csv").exists()


# --------------------------------------------------------------------------
# Acceptance 7: malformed fixed-width surfaces the engine reader's error
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_line",
    ["A00004Dave", "A00004Dave      xyz"],
    ids=["short_record", "bad_int_cast"],
)
def test_malformed_fixed_width_surfaces_engine_error(tmp_path: Path, bad_line: str):
    from decoy_engine import FixedWidthParseError, read_fixed_width

    src = tmp_path / "people.dat"
    _write_fixed_width(src)
    with src.open("a", encoding="utf-8") as fh:
        fh.write(bad_line + "\n")
    config = _config(tmp_path, src, "fixed_width", layout=_LAYOUT)
    with pytest.raises(FixedWidthParseError) as engine_err:
        read_fixed_width(src, _LAYOUT)

    result = runner.invoke(app, ["run", str(config), "--json"])
    assert result.exit_code != 0
    payload = _json.loads(result.stdout)
    assert str(engine_err.value) in payload["error"]
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# Acceptance 8: native gate follows the declared format
# --------------------------------------------------------------------------


def _broken_status():
    from decoy_engine import NativeCompanionStatus

    return NativeCompanionStatus(
        present=True,
        ok=False,
        abi_expected="1",
        abi_actual="1",
        version="9.9.9",
        reason="kat-corrupt",
        cause=RuntimeError("x"),
    )


def _native_config(fmt: str) -> dict:
    return {
        "sources": {
            "people": {
                "type": "file",
                "format": fmt,
                "path": "x.dat",
                **({"layout": _LAYOUT} if fmt == "fixed_width" else {}),
            }
        },
        "tables": [
            {
                "name": "people",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "name", "strategy": "hash", "namespace": "n"},
                ],
            }
        ],
    }


@pytest.mark.parametrize("fmt", ["csv", "parquet", "fixed_width"])
def test_static_native_eligibility_accepts_declared_formats(fmt: str):
    from decoy._native_gate import static_native_eligibility

    assert static_native_eligibility(_native_config(fmt)) is True


def test_static_native_eligibility_ignores_suffix():
    from decoy._native_gate import static_native_eligibility

    config = _native_config("csv")
    config["sources"]["people"]["path"] = "in.parquet"
    assert static_native_eligibility(config) is True
    config["sources"]["people"]["format"] = "xlsx"
    assert static_native_eligibility(config) is False
    del config["sources"]["people"]["format"]
    assert static_native_eligibility(config) is False


@pytest.mark.parametrize("fmt", ["csv", "fixed_width"])
def test_broken_companion_fails_closed_for_csv_and_fixed_width(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fmt: str
):
    if fmt == "csv":
        src = tmp_path / "in.csv"
        _frame().to_csv(src, index=False)
        config = _config(tmp_path, src, "csv")
    else:
        config = _fixed_width_config(tmp_path)
    monkeypatch.setattr("decoy_engine.native_companion_status", _broken_status)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_USAGE
    assert "kat-corrupt" in result.output
    assert not (tmp_path / "out.csv").exists()


def test_fixed_width_succeeds_under_no_native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _fixed_width_config(tmp_path)
    monkeypatch.setattr("decoy_engine.native_companion_status", _broken_status)
    result = runner.invoke(app, ["run", str(config), "--no-native"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").exists()


def test_fixed_width_succeeds_under_mask_native_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _fixed_width_config(tmp_path)
    monkeypatch.setattr("decoy_engine.native_companion_status", _broken_status)
    with pytest.warns(UserWarning):
        got = decoy.mask(config=str(config), native=False)
    assert [int(a) for a in got["age"]] == [31, 4, 57]
