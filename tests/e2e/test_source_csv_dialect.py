"""CSV sources are read with their declared dialect (`has_header`, `column_names`, `delimiter`).

CLI half of slice CLI-DIALECT: every CSV read of a declared source goes through
`decoy.cli._sources.read_csv_frame`, which calls the engine reader, so `decoy run` (plain and
`--chunked`), `decoy tokenize`, `decoy.mask()` (with and without `data=`), `decoy init` and the
source read of the report verbs honour the dialect the config declares.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app
from decoy.api import ConfigValidationError
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_ROWS = [("1", "Alice", "31"), ("2", "Bob", "4"), ("3", "Carol", "57")]
_NAMES = ["id", "name", "age"]
_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "name", "strategy": "hash", "namespace": "name_ns"},
    {"name": "age", "strategy": "passthrough"},
]
_TOKEN_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "name", "strategy": "tokenize", "namespace": "name_ns"},
    {"name": "age", "strategy": "passthrough"},
]


def _write(path: Path, *, delimiter: str = ",", header: bool = True) -> Path:
    lines = ([delimiter.join(_NAMES)] if header else []) + [delimiter.join(r) for r in _ROWS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _config(
    tmp_path: Path,
    src: Path,
    *,
    dialect: dict[str, Any] | None = None,
    columns: list[dict] | None = None,
    out: str = "out.csv",
    fmt: str = "csv",
) -> Path:
    source: dict[str, Any] = {"type": "file", "format": fmt, "path": str(src), **(dialect or {})}
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": source},
        "tables": [{"name": "people", "columns": columns or _COLUMNS}],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / out)}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def _out(tmp_path: Path, name: str = "out.csv") -> pd.DataFrame:
    return pd.read_csv(tmp_path / name, dtype=str)


def _reference(tmp_path: Path) -> pd.DataFrame:
    ref = tmp_path / "ref"
    ref.mkdir()
    cfg = _config(ref, _write(ref / "in.csv"))
    assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
    return _out(ref)


_HEADERLESS = {"has_header": False, "column_names": _NAMES}
_DIALECTS = {
    "tab": ("\t", True, {"delimiter": "\t"}),
    "pipe": ("|", True, {"delimiter": "|"}),
    "pipe-headerless": ("|", False, {"delimiter": "|", **_HEADERLESS}),
}


@pytest.mark.parametrize("verb", ["run", "tokenize", "mask"])
def test_headerless_with_column_names_runs(tmp_path: Path, verb: str) -> None:
    src = _write(tmp_path / "in.csv", header=False)
    columns = _TOKEN_COLUMNS if verb == "tokenize" else _COLUMNS
    cfg = _config(tmp_path, src, dialect=_HEADERLESS, columns=columns)
    if verb == "run":
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == 0, result.output
        got = _out(tmp_path)
        pd.testing.assert_frame_equal(got, _reference(tmp_path))
    elif verb == "tokenize":
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "v.db")])
        assert result.exit_code == 0, result.output
        got = _out(tmp_path)
    else:
        got = decoy.mask(config=str(cfg)).astype(str)
    assert list(got.columns) == _NAMES
    assert got["id"].tolist() == ["1", "2", "3"]
    assert got["age"].tolist() == ["31", "4", "57"]
    assert got["name"].tolist() != [r[1] for r in _ROWS]


@pytest.mark.parametrize("kind", sorted(_DIALECTS))
def test_delimiters(tmp_path: Path, kind: str) -> None:
    delimiter, header, dialect = _DIALECTS[kind]
    work = tmp_path / "w"
    work.mkdir()
    cfg = _config(
        work, _write(work / "in.txt", delimiter=delimiter, header=header), dialect=dialect
    )
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == 0, result.output
    pd.testing.assert_frame_equal(_out(work), _reference(tmp_path))


def test_default_dialect_unchanged(tmp_path: Path) -> None:
    outs = []
    for label, dialect in (("plain", None), ("explicit", {"has_header": True, "delimiter": ","})):
        d = tmp_path / label
        d.mkdir()
        cfg = _config(d, _write(d / "in.csv"), dialect=dialect)
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
        outs.append((d / "out.csv").read_bytes())
    assert outs[0] == outs[1]
    # The bytes the default CSV gave on the repin commit (before the reader moved).
    assert outs[0].decode().splitlines()[0] == "id,name,age"
    assert outs[0].decode().count("\n") == 4


def test_report_source_without_config_equals_pandas(tmp_path: Path) -> None:
    from decoy.cli._sources import read_report_source

    path = _write(tmp_path / "plain.csv")
    pd.testing.assert_frame_equal(read_report_source(path, {}, tmp_path), pd.read_csv(path))


@pytest.mark.parametrize("kind", ["headerless", *sorted(_DIALECTS)])
def test_chunked_honours_dialect(tmp_path: Path, kind: str) -> None:
    if kind == "headerless":
        delimiter, header, dialect = ",", False, _HEADERLESS
    else:
        delimiter, header, dialect = _DIALECTS[kind]
    work = tmp_path / "w"
    work.mkdir()
    cfg = _config(
        work, _write(work / "in.txt", delimiter=delimiter, header=header), dialect=dialect
    )
    result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "2"])
    assert result.exit_code == 0, result.output
    pd.testing.assert_frame_equal(_out(work), _reference(tmp_path))


_MISFITS = {
    "extra_field": (b"1,Alice,31,zz_marker_a\n2,Bob,4\n", "source_file.column_count_mismatch"),
    "short_row": (b"1,Alice\n", "source_file.column_count_mismatch"),
    "no_rows": (b"\n   \n\n", "source_file.column_count_mismatch"),
    "nul": (b"1,Alice,3\x001\n", "source_file.nul_byte"),
    "lone_cr": (b"1,Alice,31\r2,zz_marker_b,4\r", "source_file.lone_cr"),
    "open_quote": (b'1,2,"3\n', "source_file.column_count_mismatch"),
}


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("case", sorted(_MISFITS))
def test_headerless_misfit_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, chunked: bool
) -> None:
    content, code = _MISFITS[case]
    src = tmp_path / "secret_name_file.csv"
    src.write_bytes(content)
    cfg = _config(tmp_path, src, dialect=_HEADERLESS)
    reached: list[Any] = []
    import decoy_engine

    real = decoy_engine.run_mask_pipeline_chunked
    monkeypatch.setattr(
        decoy_engine,
        "run_mask_pipeline_chunked",
        lambda *a, **k: reached.append(1) or real(*a, **k),
    )
    args = ["run", str(cfg)] + (["--chunked", "--chunk-size", "2"] if chunked else [])
    result = runner.invoke(app, args)
    assert result.exit_code == 1, result.output
    assert f"error: {code}: source people " in " ".join(result.output.split()), result.output
    assert not (tmp_path / "out.csv").exists()
    for leaked in ("zz_marker_a", "zz_marker_b", "secret_name_file", str(tmp_path)):
        assert leaked not in result.output
    if not (chunked and case == "open_quote"):
        assert reached == []
    # An unterminated quote is the one misfit the engine's scan cannot see: in a chunked read
    # the parser disagreement surfaces on the first chunk step, inside the engine call, and
    # still exits 1 with the coded message and no output.


@pytest.mark.parametrize("case", ["headerless", "parquet"])
def test_mask_data_override_keeps_dialect(tmp_path: Path, case: str) -> None:
    if case == "headerless":
        declared = _write(tmp_path / "declared.csv", header=False)
        other = tmp_path / "other.csv"
        other.write_text("9,Zed,40\n8,Yan,5\n", encoding="utf-8")
        cfg = _config(tmp_path, declared, dialect=_HEADERLESS)
        got = decoy.mask(config=str(cfg), data=str(other)).astype(str)
        assert list(got.columns) == _NAMES
        assert got["id"].tolist() == ["9", "8"]
        assert got["name"].tolist() != ["Zed", "Yan"]
    else:
        pq_path = tmp_path / "x.parquet"
        pd.DataFrame(dict(zip(_NAMES, zip(*_ROWS)))).to_parquet(pq_path, index=False)
        cfg = _config(tmp_path, pq_path, dialect={"delimiter": "|"}, fmt="parquet")
        # The declaration itself is invalid, so config validation refuses it before the
        # override is staged: a dialect key never reaches a non-csv read.
        with pytest.raises(ConfigValidationError) as exc:
            decoy.mask(config=str(cfg), data=str(pq_path))
        assert "delimited params (delimiter) are only valid when format='csv'" in str(exc.value)


def test_init_tsv_declares_delimiter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import decoy.cli._sources as sources

    calls: list[dict] = []
    real = sources.read_csv_frame

    def spy(table, src, base, **kw):
        calls.append(dict(src))
        return real(table, src, base, **kw)

    monkeypatch.setattr(sources, "read_csv_frame", spy)
    tsv = _write(tmp_path / "data.tsv", delimiter="\t")
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", str(tsv), "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert calls and calls[0].get("delimiter") == "\t"
    doc = yaml.safe_load(
        "\n".join(ln for ln in out.read_text().splitlines() if not ln.lstrip().startswith("#"))
    )
    assert doc["sources"]["data"]["delimiter"] == "\t"
    assert doc["sources"]["data"]["format"] == "csv"


def _report_payload(verb: str, source: Path, other: Path, config: Path | None) -> dict[str, Any]:
    import json

    args = ["report", verb]
    args += (
        [str(source), str(other)] if verb == "fidelity" else [str(other), "--source", str(source)]
    )
    if config is not None:
        args += ["--config", str(config)]
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code in (0, 4), result.output
    payload = json.loads(result.stdout)
    report = payload.get("report", payload)
    for volatile in ("generated_at", "source", "output", "masked"):
        report.pop(volatile, None)
    return report


@pytest.mark.parametrize("verb", ["fidelity", "integrity"])
def test_report_verbs_read_declared_dialect(tmp_path: Path, verb: str) -> None:
    ref = tmp_path / "ref"
    ref.mkdir()
    header_src = _write(ref / "in.csv")
    masked = ref / "masked.csv"
    pd.DataFrame(_ROWS, columns=_NAMES).assign(name=["x1", "x2", "x3"]).to_csv(masked, index=False)
    expected = _report_payload(verb, header_src, masked, _config(ref, header_src))

    pipe = _write(tmp_path / "in.txt", delimiter="|", header=False)
    declared = _config(tmp_path, pipe, dialect={"delimiter": "|", **_HEADERLESS})
    assert _report_payload(verb, pipe, masked, declared) == expected

    elsewhere = _config(tmp_path, _write(tmp_path / "other.csv"), out="o2.csv")
    assert _report_payload(verb, pipe, masked, elsewhere) != expected
