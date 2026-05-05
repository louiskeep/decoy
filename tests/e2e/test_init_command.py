"""End-to-end tests for `decoy init`."""

from __future__ import annotations

import json as _json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()


def test_init_help_includes_examples():
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_init_quiet_writes_minimal_pipeline(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", "--out", str(out), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.exists()
    data = yaml.safe_load(out.read_text())
    assert "masking_rules" in data
    assert len(data["masking_rules"]) >= 3


def test_init_json_returns_metadata(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", "--out", str(out), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "init"
    assert payload["status"] == "ok"
    assert payload["preset"] == "minimal"
    assert payload["rule_count"] >= 3


def test_init_refuses_to_overwrite_in_json_mode(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    out.write_text("existing")
    result = runner.invoke(app, ["init", "--out", str(out), "--json"])
    assert result.exit_code == 1
    assert "already exists" in result.stderr


def test_init_overwrites_with_yes_flag(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    out.write_text("existing")
    result = runner.invoke(app, ["init", "--out", str(out), "--yes", "--quiet"])
    assert result.exit_code == 0
    assert "masking_rules" in out.read_text()
