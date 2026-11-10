"""GEN-FIT-SHAPE C1 (AT-11): `decoy fit` reports each column's null rate.

The summary appends `, N% null` to a column that has nulls, and `--json` gains an additive
`null_rates` map. Both come from the engine's `quality.snapshot_null_fraction`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

_ROWS = 1000
_NULLS = 138


def _source(tmp_path: Path) -> Path:
    smoker: list[str | None] = ["yes", "no"] * (_ROWS // 2)
    for i in range(_NULLS):
        smoker[i * 7] = None
    src = tmp_path / "qa.csv"
    pd.DataFrame({"smoker": smoker, "age": list(range(_ROWS))}).to_csv(src, index=False)
    return src


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_summary_appends_the_null_rate_to_a_column_with_nulls(tmp_path: Path) -> None:
    result = runner.invoke(app, ["fit", str(_source(tmp_path)), "-o", str(tmp_path / "s.json")])
    assert result.exit_code == 0, result.output
    text = _flat(result.output)
    assert "smoker (categorical, 13.8% null)" in text
    assert "age (numeric)" in text


def test_json_carries_null_rates_from_the_engine(tmp_path: Path) -> None:
    out = tmp_path / "s.json"
    result = runner.invoke(app, ["fit", str(_source(tmp_path)), "-o", str(out), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["null_rates"] == {"smoker": 0.138, "age": 0.0}
    assert payload["columns"] == {"smoker": "categorical", "age": "numeric"}


def test_snapshot_file_carries_cell_format(tmp_path: Path) -> None:
    out = tmp_path / "s.json"
    result = runner.invoke(app, ["fit", str(_source(tmp_path)), "-o", str(out)])
    assert result.exit_code == 0, result.output
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert all("cell_format" in col for col in doc["columns"].values())


def test_rate_comes_from_the_engine_helper(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []

    def fake(col: dict) -> float | None:
        calls.append(col)
        return 0.5

    monkeypatch.setattr("decoy_engine.quality.snapshot_null_fraction", fake)
    result = runner.invoke(
        app, ["fit", str(_source(tmp_path)), "-o", str(tmp_path / "s.json"), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert calls, "fit must ask the engine helper for each column"
    assert json.loads(result.stdout)["null_rates"] == {"smoker": 0.5, "age": 0.5}
