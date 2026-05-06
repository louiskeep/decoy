"""End-to-end tests for `decoy forecast recommend`."""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()


@pytest.fixture
def saved_scan(tmp_path: Path) -> Path:
    """Run a scan first so forecast has something to recommend over."""
    csv_path = tmp_path / "data.csv"
    pd.DataFrame(
        {
            "first_name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
            "last_name": ["A", "B", "C", "D", "E"],
            "email": ["a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com"],
            "ssn": [
                "111-22-3333",
                "222-33-4444",
                "333-44-5555",
                "444-55-6666",
                "555-66-7777",
            ],
            "dob": ["1990-01-01", "1985-02-02", "1992-03-03", "1988-04-04", "2000-05-05"],
            "zip": ["10001", "90210", "60601", "77001", "94016"],
            "gender": ["F", "M", "F", "M", "F"],
        }
    ).to_csv(csv_path, index=False)

    scan_path = tmp_path / "scan.json"
    result = runner.invoke(
        app, ["storm", "scan", str(csv_path), "--out", str(scan_path), "--quiet"]
    )
    assert result.exit_code == 0
    return scan_path


def test_forecast_help_includes_examples():
    result = runner.invoke(app, ["forecast", "recommend", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_forecast_recommend_writes_report_and_pipeline(saved_scan: Path):
    result = runner.invoke(app, ["forecast", "recommend", str(saved_scan)])
    assert result.exit_code == 0, result.stdout

    forecast_files = list(saved_scan.parent.glob("forecast_*.json"))
    pipeline_files = list(saved_scan.parent.glob("forecast_*.pipeline.yaml"))
    assert forecast_files, "expected a forecast_<ts>.json next to the scan"
    assert pipeline_files, "expected a pipeline draft next to the forecast"

    report = _json.loads(forecast_files[0].read_text())
    assert "disguise_recommendations" in report
    assert report["proposed_pipeline_yaml"]


def test_forecast_recommend_json_envelope(saved_scan: Path):
    result = runner.invoke(
        app, ["forecast", "recommend", str(saved_scan), "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "forecast recommend"
    assert payload["status"] == "ok"
    assert payload["report"]["disguise_recommendations"]


def test_forecast_recommend_quiet_produces_empty_stdout(saved_scan: Path):
    result = runner.invoke(
        app, ["forecast", "recommend", str(saved_scan), "--quiet"]
    )
    assert result.exit_code == 0
    assert result.stdout == ""
