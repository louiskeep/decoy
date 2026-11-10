"""File targets are written by their DECLARED `format`, never by the path suffix.

The target-side mirror of tests/e2e/test_source_format_dispatch.py (CLI-FMT Part A).
Every assertion is on exit codes and file bytes, so each is red on a build that still
picks the writer from the suffix.
"""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from tests.csv_sources import file_source
from tests.e2e.test_source_format_dispatch import (
    _COLUMNS,
    _LAYOUT,
    _engine_expected,
    _frame,
    _write_fixed_width,
)
from tests.e2e.test_tokenize_cli import _TOKENIZE_COLS
from tests.e2e.test_tokenize_cli import _pipeline as _tokenize_pipeline
from tests.e2e.test_unmask_command import _run_mask
from tests.keyed_secret import TEST_MASK_SECRET_REF

# Keyed strategies need an admitted mask secret (engine 0.17.0); see tests/keyed_secret.py.
pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_PAR1 = b"PAR1"
_DETOKENIZE_PARQUET_SHA256 = "af79fcce22552ef79447e2ef4ba35bb6fd3cba32bb4eef2f3e3bd3f524b1e980"
_DEMO_MASKED_SHA256 = "d784565e2ae6bc228f266b8080ad49ab3fd80ee94269f7b7261f79e624723011"
_CSV_HEADER = b"id,name,age"


def _target_layout(expected: pd.DataFrame) -> dict[str, Any]:
    """A fixed-width layout wide enough for the masked frame (hashed names overflow `_LAYOUT`)."""
    columns: list[dict[str, Any]] = []
    start = 0
    for name in expected.columns:
        width = max(len(str(v)) for v in expected[name])
        spec: dict[str, Any] = {"name": name, "start": start, "width": width}
        if name == "age":
            spec.update(type="int", align="right")
        columns.append(spec)
        start += width
    return {"columns": columns}


def _write_config(tmp_path: Path, target: dict | None, *, src: dict | None = None) -> Path:
    """A one-table pipeline over a fixed-width source; `target=None` omits `targets:`."""
    source_path = tmp_path / "people.dat"
    if not source_path.exists():
        _write_fixed_width(source_path)
    cfg: dict[str, Any] = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {
            "people": src
            or {
                "type": "file",
                "format": "fixed_width",
                "path": str(source_path),
                "layout": _LAYOUT,
            }
        },
        "tables": [{"name": "people", "columns": _COLUMNS}],
    }
    if target is not None:
        cfg["targets"] = {"people": {"type": "file", **target}}
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    """The target layout and the masked frame the engine produces for the shared source."""
    expected = _engine_expected(tmp_path, _write_config(tmp_path, {"format": "csv", "path": "x"}))
    return _target_layout(expected), expected


def _target(fmt: str, path: Path, layout: dict | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"format": fmt, "path": str(path)}
    if layout is not None:
        entry["layout"] = layout
    return entry


def _refuse_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any source read fail, so an exit 1 proves the refusal came first."""
    import decoy.cli.run._execute as run_module

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("a source was read before the target refusal")

    monkeypatch.setattr(run_module, "read_source", boom)
    monkeypatch.setattr(run_module, "iter_source_chunks", boom)


# ---------------------------------------------------------------------------
# AT-F1, AT-F2, AT-F3: the declared format rule
# ---------------------------------------------------------------------------


def test_fixed_width_target_writes_fixed_width(tmp_path: Path) -> None:
    layout, expected = _fixture(tmp_path)
    config = _write_config(tmp_path, _target("fixed_width", tmp_path / "out.txt", layout))
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    from decoy_engine import read_fixed_width

    got = read_fixed_width(tmp_path / "out.txt", layout)
    pd.testing.assert_frame_equal(got, expected, check_dtype=False)


def test_mismatched_suffix_is_refused_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, _target("parquet", tmp_path / "out2.csv"))
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not (tmp_path / "out2.csv").exists()
    flat = " ".join(result.output.split())
    for word in ("people", "parquet", ".csv"):
        assert word in flat
    assert str(tmp_path) not in result.output

    _refuse_reads(monkeypatch)
    again = runner.invoke(app, ["run", str(config)])
    assert again.exit_code == EXIT_USAGE, again.output


# (declared format, file name, expected result)
_RULE_ROWS = [
    ("csv", "out.csv", "csv"),
    ("csv", "out.txt", "csv"),
    ("csv", "out.csv.gz", "csv_gz"),
    ("csv", "out.parquet", "refused"),
    ("csv", "out.pq", "refused"),
    ("parquet", "out.parquet", "parquet"),
    ("parquet", "out.PARQUET", "parquet"),
    ("parquet", "out.pq", "parquet"),
    ("parquet", "out.dat", "parquet"),
    ("parquet", "out_no_suffix", "parquet"),
    ("parquet", "out.csv", "refused"),
    ("parquet", "out.csv.gz", "refused"),
    ("fixed_width", "out.txt", "fixed_width"),
    ("fixed_width", "out_no_suffix", "fixed_width"),
    ("fixed_width", "out.csv", "refused"),
    ("fixed_width", "out.parquet", "refused"),
]


@pytest.mark.parametrize(("declared", "name", "expect"), _RULE_ROWS)
def test_declared_format_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declared: str, name: str, expect: str
) -> None:
    layout, expected = _fixture(tmp_path)
    out = tmp_path / name
    config = _write_config(
        tmp_path, _target(declared, out, layout if declared == "fixed_width" else None)
    )
    if expect == "refused":
        _refuse_reads(monkeypatch)
    result = runner.invoke(app, ["run", str(config)])
    if expect == "refused":
        assert result.exit_code == EXIT_USAGE, result.output
        assert not out.exists()
        return
    assert result.exit_code == 0, result.output
    data = out.read_bytes()
    if expect == "parquet":
        assert data.startswith(_PAR1)
    elif expect == "csv":
        assert data.startswith(_CSV_HEADER)
    elif expect == "csv_gz":
        assert data[:2] == b"\x1f\x8b"
        plain = tmp_path / "plain.csv"
        config = _write_config(tmp_path, _target("csv", plain))
        assert runner.invoke(app, ["run", str(config)]).exit_code == 0
        assert gzip.decompress(data) == plain.read_bytes()
    else:
        from decoy_engine import read_fixed_width

        pd.testing.assert_frame_equal(read_fixed_width(out, layout), expected, check_dtype=False)


# ---------------------------------------------------------------------------
# AT-F4, AT-F4b, AT-F5, AT-F5b: --chunked
# ---------------------------------------------------------------------------


def _csv_config(tmp_path: Path, targets: dict[str, dict], *, src_fmt: str = "csv") -> Path:
    """Tables a and b over CSV sources (or one Parquet source per table)."""
    sources, tables = {}, []
    for name in targets:
        if src_fmt == "csv":
            src = tmp_path / f"src_{name}.csv"
            _frame().to_csv(src, index=False)
        else:
            src = tmp_path / f"src_{name}.parquet"
            _frame().to_parquet(src, index=False)
        sources[name] = file_source(src, src_fmt)
        tables.append({"name": name, "columns": _COLUMNS})
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": sources,
        "tables": tables,
        "targets": {n: {"type": "file", **t} for n, t in targets.items()},
    }
    path = tmp_path / "multi.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_chunked_refuses_fixed_width_target_before_any_write(tmp_path: Path) -> None:
    config = _csv_config(
        tmp_path,
        {
            "a": _target("csv", tmp_path / "a.csv"),
            "b": _target("fixed_width", tmp_path / "b.txt", _LAYOUT),
        },
    )
    result = runner.invoke(app, ["run", str(config), "--chunked"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not (tmp_path / "a.csv").exists()
    assert not (tmp_path / "b.txt").exists()


@pytest.mark.parametrize("suffix", [".zip", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz"])
def test_chunked_refuses_container_archive_before_any_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    out = tmp_path / f"out.csv{suffix}"
    config = _csv_config(tmp_path, {"a": _target("csv", out)})
    _refuse_reads(monkeypatch)
    result = runner.invoke(app, ["run", str(config), "--chunked", "--chunk-size", "2"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "--chunked" in result.output
    assert not out.exists()


def test_chunked_writes_declared_parquet(tmp_path: Path) -> None:
    out = tmp_path / "out.dat"
    config = _csv_config(tmp_path, {"a": _target("parquet", out)})
    result = runner.invoke(app, ["run", str(config), "--chunked", "--chunk-size", "2"])
    assert result.exit_code == 0, result.output
    assert out.read_bytes().startswith(_PAR1)
    meta = pq.ParquetFile(str(out)).metadata
    assert meta.num_rows == 3
    assert meta.num_row_groups == 2


def test_chunked_empty_parquet_source_writes_zero_row_file(tmp_path: Path) -> None:
    src = tmp_path / "empty.parquet"
    schema = pa.schema([("id", pa.string()), ("name", pa.string()), ("age", pa.int64())])
    pq.write_table(schema.empty_table(), str(src))
    out = tmp_path / "out.dat"
    config = _write_config(
        tmp_path,
        _target("parquet", out),
        src={"type": "file", "format": "parquet", "path": str(src)},
    )
    result = runner.invoke(app, ["run", str(config), "--chunked", "--chunk-size", "2"])
    assert result.exit_code == 0, result.output
    got = pq.ParquetFile(str(out))
    assert got.metadata.num_rows == 0
    assert got.schema_arrow.equals(schema.remove_metadata())


def test_chunked_csv_bytes_unchanged(tmp_path: Path) -> None:
    plain_dir, chunk_dir = tmp_path / "plain", tmp_path / "chunk"
    for d in (plain_dir, chunk_dir):
        d.mkdir()
    plain = _csv_config(plain_dir, {"a": _target("csv", plain_dir / "out.csv")})
    chunk = _csv_config(chunk_dir, {"a": _target("csv", chunk_dir / "out.csv")})
    assert runner.invoke(app, ["run", str(plain)]).exit_code == 0
    result = runner.invoke(app, ["run", str(chunk), "--chunked", "--chunk-size", "2"])
    assert result.exit_code == 0, result.output
    got = (chunk_dir / "out.csv").read_bytes()
    assert got == (plain_dir / "out.csv").read_bytes()
    assert got.count(_CSV_HEADER) == 1


# ---------------------------------------------------------------------------
# AT-F6, AT-F12: mask(), tokenize
# ---------------------------------------------------------------------------


def test_mask_api_and_tokenize_use_the_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = _write_config(tmp_path, _target("parquet", tmp_path / "out.csv"))
    import decoy_engine

    with monkeypatch.context() as patched:
        _refuse_reads(patched)
        patched.setattr(decoy_engine, "run_pipeline", lambda *a, **k: pytest.fail("engine ran"))
        with pytest.raises(ValueError) as err:
            decoy.mask(config=str(bad))
    assert type(err.value).__name__ == "TargetFormatError"
    assert not (tmp_path / "out.csv").exists()

    good = tmp_path / "ok"
    good.mkdir()
    decoy.mask(config=str(_write_config(good, _target("parquet", good / "out.dat"))))
    assert (good / "out.dat").read_bytes().startswith(_PAR1)

    tok = tmp_path / "tok"
    tok.mkdir()
    cfg = _tokenize_pipeline(tok, _TOKENIZE_COLS, out_name="out.csv", out_format="parquet")
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tok / "v.db")])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not (tok / "out.csv").exists()


def test_mask_out_override_takes_the_suffix_format(tmp_path: Path) -> None:
    layout, _expected = _fixture(tmp_path)
    csv_cfg = _write_config(tmp_path, _target("csv", tmp_path / "out.csv"))
    decoy.mask(config=str(csv_cfg), out=tmp_path / "m.parquet")
    assert (tmp_path / "m.parquet").read_bytes().startswith(_PAR1)

    fw_cfg = _write_config(tmp_path, _target("fixed_width", tmp_path / "out.txt", layout))
    decoy.mask(config=str(fw_cfg), out=tmp_path / "m.csv")
    assert (tmp_path / "m.csv").read_bytes().startswith(_CSV_HEADER)

    got = decoy.mask(config=str(fw_cfg), out=tmp_path / "m.dat")
    from decoy_engine import read_fixed_width

    back = read_fixed_width(tmp_path / "m.dat", layout)
    pd.testing.assert_frame_equal(back, got.reset_index(drop=True), check_dtype=False)

    no_target = _write_config(tmp_path, None)
    decoy.mask(config=str(no_target), out=tmp_path / "m.pq")
    assert (tmp_path / "m.pq").read_bytes().startswith(_PAR1)


# ---------------------------------------------------------------------------
# AT-F7, AT-F8: demo, unmask, detokenize
# ---------------------------------------------------------------------------


def test_demo_writer_uses_the_rule(tmp_path: Path) -> None:
    from decoy.cli.demo import _write_mask_outputs

    config = {"targets": {"people": {"type": "file", "format": "parquet", "path": "x.dat"}}}
    outputs = {"people": pa.Table.from_pandas(_frame(), preserve_index=False)}
    _write_mask_outputs(config, SimpleNamespace(outputs=outputs), tmp_path)
    assert (tmp_path / "x.dat").read_bytes().startswith(_PAR1)

    result = runner.invoke(app, ["demo", "--dir", str(tmp_path / "demo")])
    assert result.exit_code == 0, result.output
    masked = (tmp_path / "demo" / "customers_masked.csv").read_bytes()
    # Recorded on the base tree (05bf840): the bundled demo output must not change.
    assert hashlib.sha256(masked).hexdigest() == _DEMO_MASKED_SHA256


def test_vault_reversal_outputs_follow_the_suffix(tmp_path: Path) -> None:
    unmask_dir = tmp_path / "unmask"
    unmask_dir.mkdir()
    cfg = _run_mask(unmask_dir)
    masked = unmask_dir / "masked.csv"
    for name, magic in (("rec.parquet", _PAR1), ("rec.csv", b"ssn")):
        out = unmask_dir / name
        result = runner.invoke(app, ["unmask", str(cfg), str(masked), "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_bytes().startswith(magic)

    tok = tmp_path / "tok"
    tok.mkdir()
    tcfg = _tokenize_pipeline(tok, _TOKENIZE_COLS)
    vault = tok / "tokens.db"
    assert runner.invoke(app, ["tokenize", str(tcfg), "--vault", str(vault)]).exit_code == 0
    args = ["detokenize", str(tcfg), str(tok / "tokenized.csv"), "--vault", str(vault), "-o"]
    for name in ("out.pq", "out.parquet", "out.csv"):
        assert runner.invoke(app, [*args, str(tok / name)]).exit_code == 0
    assert (tok / "out.pq").read_bytes().startswith(_PAR1)
    assert (tok / "out.csv").read_bytes().startswith(b"id,email")
    # The pandas branch is unchanged: bytes recorded on the base tree (05bf840).
    got = hashlib.sha256((tok / "out.parquet").read_bytes()).hexdigest()
    assert got == _DETOKENIZE_PARQUET_SHA256


# ---------------------------------------------------------------------------
# AT-F9, AT-F13: the fixed-width integer rule
# ---------------------------------------------------------------------------


def _int_layout(ids: int, ages: int) -> dict[str, Any]:
    return {
        "columns": [
            {"name": "id", "start": 0, "width": ids},
            {"name": "age", "start": ids, "width": ages, "type": "int", "align": "right"},
        ]
    }


def _passthrough_config(tmp_path: Path, src: Path, src_fmt: str, out: Path, layout: dict) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"t": file_source(src, src_fmt)},
        "tables": [
            {
                "name": "t",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "age", "strategy": "passthrough"},
                ],
            }
        ],
        "targets": {"t": {"type": "file", **_target("fixed_width", out, layout)}},
    }
    path = tmp_path / "ints.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_fixed_width_int_conversion_matches_platform(tmp_path: Path) -> None:
    from decoy_engine import read_fixed_width

    big = 2**53 + 1
    src = tmp_path / "in.parquet"
    pd.DataFrame({"id": ["a", "b"], "age": [big, 7]}).to_parquet(src, index=False)
    out = tmp_path / "out.txt"
    layout = _int_layout(1, 16)
    config = _passthrough_config(tmp_path, src, "parquet", out, layout)
    assert runner.invoke(app, ["run", str(config)]).exit_code == 0
    assert read_fixed_width(out, layout)["age"].tolist() == [big, 7]

    floats = tmp_path / "floats.parquet"
    pd.DataFrame({"id": ["a", "b"], "age": [31.0, 4.0]}).to_parquet(floats, index=False)
    out2 = tmp_path / "out2.txt"
    config = _passthrough_config(tmp_path, floats, "parquet", out2, _int_layout(1, 3))
    assert runner.invoke(app, ["run", str(config)]).exit_code == 0
    assert out2.read_text(encoding="utf-8").splitlines() == ["a 31", "b  4"]

    bad = tmp_path / "bad.parquet"
    pd.DataFrame({"id": ["a", "b"], "age": [31.0, 4.5]}).to_parquet(bad, index=False)
    out3 = tmp_path / "out3.txt"
    config = _passthrough_config(tmp_path, bad, "parquet", out3, _int_layout(1, 3))
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert not out3.exists()


_ROW_ID = "ZQ9row"


def _csv_ints(tmp_path: Path, values: list[str]) -> Path:
    src = tmp_path / "ints.csv"
    src.write_text("id,age\n" + "".join(f"{_ROW_ID}{i},{v}\n" for i, v in enumerate(values)))
    return src


def test_csv_source_to_fixed_width_int(tmp_path: Path) -> None:
    from decoy_engine import read_fixed_width

    good = ["0", "42", "-7", "9223372036854775807"]
    layout = _int_layout(len(_ROW_ID) + 1, 20)
    out = tmp_path / "good.txt"
    config = _passthrough_config(tmp_path, _csv_ints(tmp_path, good), "csv", out, layout)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    assert read_fixed_width(out, layout)["age"].tolist() == [int(v) for v in good]

    for n, bad in enumerate(("007", "-0", "9223372036854775808", "4.0")):
        sub = tmp_path / f"case{n}"
        sub.mkdir()
        out = sub / "out.txt"
        src = _csv_ints(sub, ["1", bad])
        config = _passthrough_config(sub, src, "csv", out, layout)
        result = runner.invoke(app, ["run", str(config)])
        assert result.exit_code == EXIT_RUNTIME, (bad, result.output)
        assert not out.exists()
        # A cell value or row key never reaches the error text. The temp path is cut out
        # first, so a short value such as "-0" cannot match a directory name.
        shown = result.output.replace(str(tmp_path), "")
        assert _ROW_ID not in shown
        assert bad not in shown


# ---------------------------------------------------------------------------
# Compression suffixes: only CSV can be compressed by its writer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "name"),
    [
        ("parquet", "out.parquet.gz"),
        ("parquet", "out.gz"),
        ("fixed_width", "out.txt.gz"),
        ("fixed_width", "out.zip"),
    ],
)
def test_uncompressed_formats_refuse_a_compression_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declared: str, name: str
) -> None:
    layout, _expected = _fixture(tmp_path)
    out = tmp_path / name
    config = _write_config(
        tmp_path, _target(declared, out, layout if declared == "fixed_width" else None)
    )
    _refuse_reads(monkeypatch)
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not out.exists()
    flat = " ".join(result.output.split())
    assert "compression" in flat
    assert str(tmp_path) not in result.output


def test_vault_reversal_outputs_refuse_a_compression_suffix(tmp_path: Path) -> None:
    unmask_dir = tmp_path / "unmask"
    unmask_dir.mkdir()
    cfg = _run_mask(unmask_dir)
    out = unmask_dir / "rec.parquet.gz"
    result = runner.invoke(
        app, ["unmask", str(cfg), str(unmask_dir / "masked.csv"), "-o", str(out)]
    )
    assert result.exit_code == EXIT_USAGE, result.output
    assert not out.exists()

    tok = tmp_path / "tok"
    tok.mkdir()
    tcfg = _tokenize_pipeline(tok, _TOKENIZE_COLS)
    vault = tok / "tokens.db"
    assert runner.invoke(app, ["tokenize", str(tcfg), "--vault", str(vault)]).exit_code == 0
    out = tok / "out.parquet.gz"
    args = ["detokenize", str(tcfg), str(tok / "tokenized.csv"), "--vault", str(vault)]
    result = runner.invoke(app, [*args, "-o", str(out)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not out.exists()
    assert "compression" in " ".join(result.output.split())
    assert str(tok) not in result.output
    # A CSV output stays compressible.
    ok = tok / "out.csv.gz"
    assert runner.invoke(app, [*args, "-o", str(ok)]).exit_code == 0
    assert ok.read_bytes()[:2] == b"\x1f\x8b"
