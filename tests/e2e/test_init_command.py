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
    """CLI.3 (2026-06-02): bundled minimal template is now V2 PipelineConfig
    shape: `version: 1`, `tables[].columns`, no `masking_rules`."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", "--out", str(out), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.exists()
    data = yaml.safe_load(out.read_text())
    assert data.get("version") == 1
    assert "tables" in data
    assert len(data["tables"]) >= 1
    assert len(data["tables"][0]["columns"]) >= 3


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
    """CLI.3 (2026-06-02): bundled template body is V2 (`tables:` block)."""
    out = tmp_path / "pipeline.yaml"
    out.write_text("existing")
    result = runner.invoke(app, ["init", "--out", str(out), "--yes", "--quiet"])
    assert result.exit_code == 0
    assert "tables:" in out.read_text()


def test_init_preset_hipaa_writes_hipaa_template(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "hipaa", "--out", str(out), "--quiet"]
    )
    assert result.exit_code == 0
    body = out.read_text()
    # Pulled from the bundled hipaa template -- must include PHI columns.
    assert "first_name" in body
    assert "mrn" in body
    assert "ssn" in body


def test_init_preset_unknown_suggests_close_match(tmp_path: Path):
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app,
        ["init", "--preset", "hippa", "--out", str(out), "--yes"],
    )
    assert result.exit_code == 1
    assert "unknown preset" in result.stderr.lower()
    assert "hipaa" in result.stderr


def test_init_preset_json_envelope_carries_preset_and_count(tmp_path: Path):
    import json as _json

    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "pci", "--out", str(out), "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["preset"] == "pci"
    assert payload["rule_count"] >= 1


def test_init_preset_generate_produces_generator_yaml(tmp_path: Path):
    """The generate preset uses `mode: generate` + `generate_columns`. CLI.3
    (2026-06-02): V1 `generator_settings:` block folded into the unified
    V2 `global_settings:`."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "generate", "--out", str(out), "--quiet"]
    )
    assert result.exit_code == 0
    body = out.read_text()
    assert "tables:" in body
    assert "mode: generate" in body
    assert "generate_columns:" in body
