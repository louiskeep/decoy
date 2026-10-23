"""Targets are written by their DECLARED `format`, never by file suffix
(enterprise-hardening A5), and fixed-width OUTPUT is wired to the engine's
write_fixed_width (A1).

Complements the source-side dispatch test (test_source_format_dispatch.py):
fixed-width targets write through the engine's public writer, the declared
format wins over the suffix, and `--chunked` refuses a fixed-width target
(the engine's fixed-width writer needs the whole frame).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_STR_LAYOUT: dict[str, Any] = {
    "columns": [
        {"name": "id", "start": 0, "width": 4, "type": "str", "pad": " ", "align": "left"},
        {"name": "code", "start": 4, "width": 6, "type": "str", "pad": " ", "align": "left"},
    ]
}

_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "code", "strategy": "passthrough"},
]


def _source_csv(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    src.write_text("id,code\n1,ab\n22,cde\n", encoding="utf-8")
    return src


def _config(tmp_path: Path, target: dict) -> Path:
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"people": {"type": "file", "format": "csv", "path": str(_source_csv(tmp_path))}},
        "tables": [{"name": "people", "columns": _COLUMNS}],
        "targets": {"people": target},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def test_fixed_width_target_writes_fixed_width_not_csv(tmp_path: Path):
    out = tmp_path / "out.fw"
    config = _config(
        tmp_path,
        {"type": "file", "format": "fixed_width", "layout": _STR_LAYOUT, "path": str(out)},
    )
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    # id: width 4 space-pad left; code: width 6 space-pad left (passthrough).
    records = out.read_text(encoding="utf-8").rstrip("\n").split("\n")
    assert records == ["1   ab    ", "22  cde   "]


def test_parquet_format_wins_over_suffix(tmp_path: Path):
    out = tmp_path / "out.dat"  # suffix would say CSV
    config = _config(tmp_path, {"type": "file", "format": "parquet", "path": str(out)})
    result = runner.invoke(app, ["run", str(config)])
    assert result.exit_code == 0, result.output
    assert pq.read_table(str(out)).num_rows == 2  # a real parquet file


def test_chunked_refuses_fixed_width_target(tmp_path: Path):
    out = tmp_path / "out.fw"
    config = _config(
        tmp_path,
        {"type": "file", "format": "fixed_width", "layout": _STR_LAYOUT, "path": str(out)},
    )
    result = runner.invoke(app, ["run", str(config), "--chunked"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not out.exists()


class TestFixedWidthHelpers:
    """Unit coverage for the int-coercion + writer helpers (no full run)."""

    _INT_LAYOUT = {
        "columns": [
            {"name": "id", "start": 0, "width": 4, "type": "int", "pad": "0", "align": "right"},
            {"name": "code", "start": 4, "width": 5, "type": "str", "pad": " ", "align": "left"},
        ]
    }

    def test_coerce_casts_clean_integral_float(self):
        from decoy.cli.run import _coerce_fixed_width_int_columns

        frame = pd.DataFrame({"id": [1.0, 2.0], "code": ["a", "b"]})
        assert _coerce_fixed_width_int_columns(frame, self._INT_LAYOUT)["id"].dtype.kind == "i"

    def test_coerce_leaves_null_bearing_float_untouched(self):
        from decoy.cli.run import _coerce_fixed_width_int_columns

        frame = pd.DataFrame({"id": [1.0, None], "code": ["a", "b"]})
        assert _coerce_fixed_width_int_columns(frame, self._INT_LAYOUT)["id"].dtype.kind == "f"

    def test_write_fixed_width_target_coerces_and_writes(self, tmp_path: Path):
        from decoy.cli.run import _write_fixed_width_target

        out = tmp_path / "x.fw"
        table = pa.table({"id": pa.array([1.0, 22.0], type=pa.float64()), "code": ["ab", "cde"]})
        _write_fixed_width_target(table, {"layout": self._INT_LAYOUT}, out)
        records = out.read_text(encoding="utf-8").rstrip("\n").split("\n")
        assert records == ["0001ab   ", "0022cde  "]

    def test_write_fixed_width_target_missing_layout_rejected(self, tmp_path: Path):
        import typer

        from decoy.cli.run import _write_fixed_width_target

        with pytest.raises(typer.Exit):
            _write_fixed_width_target(pa.table({"id": [1]}), {}, tmp_path / "x.fw")


class TestChunkedWriterFormat:
    def test_declared_csv_format_wins_over_parquet_suffix(self, tmp_path: Path):
        from decoy.cli.run import _write_chunked_output

        out = tmp_path / "out.parquet"  # suffix would say parquet
        _write_chunked_output(
            iter([pa.table({"a": [1, 2]})]),
            out,
            tmp_path / "in.csv",
            src_is_parquet=False,
            tgt_format="csv",
        )
        assert out.read_text().splitlines()[0] == "a"  # wrote CSV, not parquet

    def test_unknown_chunked_target_format_raises(self, tmp_path: Path):
        import typer

        from decoy.cli.run import _write_chunked_output

        with pytest.raises(typer.Exit):
            _write_chunked_output(
                iter([pa.table({"a": [1]})]),
                tmp_path / "out.x",
                tmp_path / "in.csv",
                src_is_parquet=False,
                tgt_format="orc",
            )


class TestNonChunkedUnknownFormat:
    def test_unknown_target_format_raises(self, tmp_path: Path):
        import typer

        from decoy.cli.run import _write_mask_outputs

        class _Result:
            outputs = {"t": pa.table({"a": [1]})}

        cfg = {"targets": {"t": {"type": "file", "format": "orc", "path": str(tmp_path / "o.orc")}}}
        with pytest.raises(typer.Exit):
            _write_mask_outputs(cfg, _Result(), tmp_path)
