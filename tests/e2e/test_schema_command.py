"""End-to-end tests for `decoy schema`."""

from __future__ import annotations

import json as _json
from pathlib import Path

from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def test_schema_default_prints_json_with_properties():
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    parsed = _json.loads(result.stdout)
    # Must be a JSON Schema object.
    assert "properties" in parsed or "$defs" in parsed
    # Top-level pipeline keys are present somewhere in the schema.
    props = parsed.get("properties", {})
    for key in ("version", "sources", "tables", "targets"):
        assert key in props, f"expected '{key}' in schema properties, got: {list(props)}"


def test_schema_output_file(tmp_path: Path):
    out = tmp_path / "s.json"
    result = runner.invoke(app, ["schema", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    parsed = _json.loads(out.read_text())
    assert "properties" in parsed or "$defs" in parsed


def test_schema_json_envelope():
    result = runner.invoke(app, ["schema", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "schema"
    assert payload["status"] == "ok"
    assert "schema" in payload
    # The wrapped schema should still look like a JSON Schema.
    inner = payload["schema"]
    assert "properties" in inner or "$defs" in inner


def test_schema_quiet_produces_no_stdout():
    result = runner.invoke(app, ["schema", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_schema_help_includes_examples():
    result = runner.invoke(app, ["schema", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "decoy schema" in result.stdout


def test_schema_output_file_with_json_writes_envelope(tmp_path: Path):
    """FIX B: --output and --json compose -- the file receives the envelope."""
    out = tmp_path / "s.json"
    result = runner.invoke(app, ["schema", "-o", str(out), "--json"])
    assert result.exit_code == 0
    assert out.exists()
    parsed = _json.loads(out.read_text())
    assert parsed["command"] == "schema"
    assert parsed["status"] == "ok"
    assert "schema" in parsed
    inner = parsed["schema"]
    assert "properties" in inner or "$defs" in inner


def test_schema_output_file_without_json_writes_raw_schema(tmp_path: Path):
    """FIX B: --output without --json writes the raw schema (no envelope keys)."""
    out = tmp_path / "s.json"
    result = runner.invoke(app, ["schema", "-o", str(out)])
    assert result.exit_code == 0
    parsed = _json.loads(out.read_text())
    assert "command" not in parsed
    assert "properties" in parsed or "$defs" in parsed
