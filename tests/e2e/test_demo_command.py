"""End-to-end tests for `decoy demo`."""

from __future__ import annotations

import json as _json
from pathlib import Path

from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()


def test_demo_help_includes_examples():
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_demo_runs_end_to_end(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir)])
    assert result.exit_code == 0, result.stdout

    assert (out_dir / "patients.csv").exists()
    assert (out_dir / "patients_masked.csv").exists()
    assert (out_dir / "scan.json").exists()
    assert (out_dir / "forecast.json").exists()
    assert (out_dir / "pipeline.yaml").exists()

    sample = (out_dir / "patients.csv").read_text()
    masked = (out_dir / "patients_masked.csv").read_text()
    assert "alice@example.com" not in masked  # email faked away
    assert "111-22-3333" not in masked  # ssn hashed
    assert "REDACTED" in masked  # zip redacted


def test_demo_json_envelope(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "demo"
    assert payload["status"] == "ok"
    assert payload["pii_columns"] >= 3
    assert payload["top_disguise"]


def test_demo_quiet_produces_empty_stdout(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert (out_dir / "patients_masked.csv").exists()
