"""Generated integer columns with nulls stay integers in every CLI output.

Engine 0.20.0 types an unformatted `sequence` as int64. Plain `pyarrow.Table.to_pandas()` widens
an int64 column holding a null to float64, so a CSV target would print `1001.0` and `decoy.mask()`
would return floats. The CLI converts generated tables with `generated_table_to_pandas`.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app

runner = CliRunner()


def _config(out: Path) -> dict:
    return {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {},
        "tables": [
            {
                "name": "ids",
                "row_count": 40,
                "generate_columns": [
                    {
                        "name": "id",
                        "type": "sequence",
                        "start": 1000,
                        "step": 1,
                        "null_probability": 0.5,
                    }
                ],
            }
        ],
        "targets": {"ids": {"type": "file", "format": "csv", "path": str(out)}},
    }


def _cells(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [row["id"] for row in csv.DictReader(fh)]


def test_run_writes_integer_text_for_a_nullable_generated_column(tmp_path: Path) -> None:
    out = tmp_path / "ids.csv"
    config_path = tmp_path / "gen.yaml"
    config_path.write_text(yaml.safe_dump(_config(out)), encoding="utf-8")

    result = runner.invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0, result.output
    cells = _cells(out)
    filled = [c for c in cells if c]
    assert filled and len(filled) < len(cells), "the seed must give both nulls and values"
    assert all(re.fullmatch(r"\d+", c) for c in filled), filled


def test_mask_returns_nullable_integers_for_a_generated_column(tmp_path: Path) -> None:
    out = decoy.mask(None, _config(tmp_path / "ids.csv"))

    assert isinstance(out, pd.DataFrame)
    assert pd.api.types.is_integer_dtype(out["id"].dtype)
    assert out["id"].isna().any() and out["id"].notna().any()
    assert all(re.fullmatch(r"\d+", c) for c in _cells(tmp_path / "ids.csv") if c)
