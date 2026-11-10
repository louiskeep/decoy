"""GEN-FIT-SHAPE C1 (AT-11): `report fidelity` shows a Nulls column only when null rates differ."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

_HEADER = "Nulls (source/output)"


def _pair(tmp_path: Path, out_null_every: int | None) -> tuple[Path, Path]:
    n = 200
    src_vals: list[str | None] = ["a", "b"] * (n // 2)
    for i in range(0, n, 5):
        src_vals[i] = None  # 20% null
    out_vals: list[str | None] = ["a", "b"] * (n // 2)
    if out_null_every:
        for i in range(0, n, out_null_every):
            out_vals[i] = None
    src, out = tmp_path / "src.csv", tmp_path / "out.csv"
    pd.DataFrame({"c": src_vals, "k": range(n)}).to_csv(src, index=False)
    pd.DataFrame({"c": out_vals, "k": range(n)}).to_csv(out, index=False)
    return src, out


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_nulls_column_appears_when_rates_differ(tmp_path: Path) -> None:
    src, out = _pair(tmp_path, None)
    result = runner.invoke(app, ["report", "fidelity", str(src), str(out)])
    assert result.exit_code == 0, result.output
    text = _flat(result.output)
    assert _HEADER in text
    assert "20.0% / 0.0%" in text


def test_nulls_column_is_absent_when_rates_match(tmp_path: Path) -> None:
    src, out = _pair(tmp_path, 5)
    result = runner.invoke(app, ["report", "fidelity", str(src), str(out)])
    assert result.exit_code == 0, result.output
    assert _HEADER not in result.output


def test_json_report_is_not_changed_by_the_nulls_column(tmp_path: Path) -> None:
    src, out = _pair(tmp_path, None)
    result = runner.invoke(app, ["report", "fidelity", str(src), str(out), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "null_rates" not in payload
    col = next(c for c in payload["marginal"]["columns"] if c["column"] == "c")
    assert col["missing_value_similarity"] == 0.8
