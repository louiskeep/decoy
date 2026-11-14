"""The DUP-DEFECTS engine fixes, proved through the CLI (roadmap row 24zd, slice C1).

The engine fixes ship in `decoy-engine` 0.24.0, which the CLI pins: an unreadable statistical
snapshot gets its reason code (A5), a null timestamp feeding a `derived` column writes a null
cell (A10), and `--chunked` runs a `when:` over a parquet `large_string` source (A15). Each test
drives the real `decoy` app and holds the exit code, the reason code and the output bytes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.csv_sources import file_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_UNREADABLE = "STATISTICAL_SNAPSHOT_UNREADABLE"
# The bytes `json.loads` choked on before the fix, and the words a raw codec error carries.
_LEAKS = ("0xff", "\\xff", "ÿ", "codec", "UnicodeDecodeError", "invalid start byte")


def _write_config(folder: Path, cfg: dict[str, Any], name: str = "pipeline.yaml") -> Path:
    path = folder / name
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _no_leak(text: str) -> None:
    lowered = text.lower()
    for leak in _LEAKS:
        assert leak.lower() not in lowered, leak


def _bad_snapshot_config(folder: Path, out: Path) -> Path:
    (folder / "snap.json").write_bytes(b'{"columns": "\xff"}')
    return _write_config(
        folder,
        {
            "version": 2,
            "global_settings": {"seed": 42},
            "tables": [
                {
                    "name": "synthetic",
                    "row_count": 20,
                    "generate_columns": [
                        {"name": "amount", "type": "statistical", "snapshot_file": "snap.json"}
                    ],
                }
            ],
            "targets": {"synthetic": {"type": "file", "format": "csv", "path": str(out)}},
        },
    )


# AT-C1-1 (A5): a snapshot that is not UTF-8 gets its reason code on every path.
@pytest.mark.parametrize("verb", ["validate", "run"])
def test_c1_1_non_utf8_snapshot_is_unreadable_not_a_codec_error(tmp_path: Path, verb: str) -> None:
    out = tmp_path / "out" / "synthetic.csv"
    cfg = _bad_snapshot_config(tmp_path, out)

    plain = runner.invoke(app, [verb, str(cfg)])
    assert plain.exit_code == 1, plain.output
    # Plain output carries the closed message (the code name is in `--json`).
    assert "snapshot_file 'snap.json' could not be read" in plain.output
    assert "not valid UTF-8 JSON" in plain.output
    _no_leak(plain.output)

    machine = runner.invoke(app, [verb, str(cfg), "--json"])
    assert machine.exit_code == 1, machine.output
    _no_leak(machine.output)
    payload = _first_json(machine.output)
    assert payload["status"] == "error"
    assert [m["code"].upper() for m in payload["messages"]] == [_UNREADABLE]

    # A refused run opens no output: nothing is written before the snapshot is read.
    assert not out.exists()
    assert not out.parent.exists() or not any(out.parent.rglob("*"))
    assert not list(tmp_path.rglob("*.csv"))


def _first_json(text: str) -> Any:
    start = text.find("{")
    assert start >= 0, text
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    return value


# AT-C1-2 (A10): a null parquet timestamp feeding `derived` writes an empty cell.
def test_c1_2_null_timestamp_feeding_derived_writes_an_empty_cell(tmp_path: Path) -> None:
    src = tmp_path / "in.parquet"
    pq.write_table(
        pa.table(
            {
                "id": pa.array(["r1", "r2"], type=pa.string()),
                "a": pa.array([None, datetime(2020, 1, 1)], type=pa.timestamp("us")),
                "b": pa.array([datetime(2020, 2, 2)] * 2, type=pa.timestamp("us")),
            }
        ),
        src,
    )
    out = tmp_path / "out.csv"
    cfg = _write_config(
        tmp_path,
        {
            "version": 2,
            "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {"t": file_source(src, "parquet")},
            "tables": [
                {
                    "name": "t",
                    "columns": [
                        {"name": "id", "strategy": "passthrough"},
                        {"name": "a", "strategy": "passthrough"},
                        {"name": "b", "strategy": "passthrough"},
                        {
                            "name": "c",
                            "strategy": "derived",
                            "provider_config": {"expression": "case_when(a < b, 1, 0)"},
                        },
                    ],
                }
            ],
            "targets": {"t": {"type": "file", "format": "csv", "path": str(out)}},
        },
    )
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == 0, result.output
    rows = pd.read_csv(out, dtype=str, keep_default_na=False)
    assert rows["id"].tolist() == ["r1", "r2"]
    # The null-timestamp row is an empty cell, not the `0` the old comparison against NaT gave.
    # The other row keeps its value; a column holding a null prints as float, so `1.0`.
    assert rows["c"][0] == ""
    assert float(rows["c"][1]) == 1.0


# AT-C1-3 (A15): `--chunked` runs a `when:` over a `large_string` parquet source.
def test_c1_3_chunked_when_over_large_string_equals_the_whole_frame_run(tmp_path: Path) -> None:
    src = tmp_path / "in.parquet"
    pq.write_table(
        pa.table(
            {
                "c": pa.array(["a", "b", "a", "c", "b", "a"], type=pa.large_string()),
                "keep": pa.array(["A", "B", "A", "B", "A", "B"], type=pa.large_string()),
            }
        ),
        src,
    )

    def config(out: Path) -> Path:
        return _write_config(
            tmp_path,
            {
                "version": 2,
                "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
                "sources": {"t": file_source(src, "parquet")},
                "tables": [
                    {
                        "name": "t",
                        "columns": [
                            {
                                "name": "c",
                                "strategy": "categorical",
                                "namespace": "ns_c",
                                "provider_config": {"categories": ["x", "y", "z"]},
                                "when": "keep == 'A'",
                            },
                            {"name": "keep", "strategy": "passthrough"},
                        ],
                    }
                ],
                "targets": {"t": {"type": "file", "format": "csv", "path": str(out)}},
            },
            name=f"{out.stem}.yaml",
        )

    whole = tmp_path / "whole.csv"
    result = runner.invoke(app, ["run", str(config(whole))])
    assert result.exit_code == 0, result.output

    chunked = tmp_path / "chunked.csv"
    result = runner.invoke(app, ["run", str(config(chunked)), "--chunked", "--chunk-size", "2"])
    assert result.exit_code == 0, result.output
    assert chunked.read_bytes() == whole.read_bytes()
    # The `when:` really selected: rows where keep is B keep their source value.
    rows = pd.read_csv(whole, dtype=str, keep_default_na=False)
    assert rows["c"].tolist()[1::2] == ["b", "c", "a"]
    assert all(v in {"x", "y", "z"} for v in rows["c"].tolist()[0::2])
