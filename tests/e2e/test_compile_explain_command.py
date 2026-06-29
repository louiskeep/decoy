"""E2E tests for `decoy compile --explain` (SP-19b).

Covers:
  - compile --explain on a real recipe shows per-column strategy + params.
  - compile --explain --json has the expected structure.
  - Exit codes: 0 on success, EXIT_USAGE on bad config / missing file.
  - compile without --explain still compiles (plan summary only, no per-column dump).
  - Rationale field present and is HONEST (no guarantees -- just what was declared
    in config and what the compile checks verified).

TDD: these tests MUST be written before the implementation.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _minimal_config() -> dict:
    """Minimal V2 config that compiles cleanly."""
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": "/tmp/x.csv"}
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "email", "strategy": "faker", "provider": "person_email"},
                    {"name": "ssn", "strategy": "redact"},
                    {"name": "account_number", "strategy": "hash"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": "/tmp/y.csv"}
        },
    }


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_compile_help_includes_explain_flag(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compile", "--help"])
    assert result.exit_code == 0
    assert "--explain" in result.stdout


def test_compile_help_includes_examples(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compile", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


# ---------------------------------------------------------------------------
# compile --explain: happy path
# ---------------------------------------------------------------------------


def test_compile_explain_exits_0(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output


def test_compile_explain_shows_per_column_strategy(tmp_path: Path) -> None:
    """The explain output must show each column's resolved strategy."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output
    # All three column strategies must appear
    assert "faker" in result.output
    assert "redact" in result.output
    assert "hash" in result.output


def test_compile_explain_shows_provider_when_set(tmp_path: Path) -> None:
    """Provider name must appear for columns that declare one."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output
    assert "person_email" in result.output


def test_compile_explain_shows_column_names(tmp_path: Path) -> None:
    """All column names must appear in the output."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output
    assert "email" in result.output
    assert "ssn" in result.output
    assert "account_number" in result.output


def test_compile_explain_shows_table_name(tmp_path: Path) -> None:
    """Table name must appear in the explain output."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output
    assert "customers" in result.output


def test_compile_explain_shows_checks_passed(tmp_path: Path) -> None:
    """Compile checks section must appear in the output."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output
    # compile checks section must be present
    assert "unknown_provider" in result.output


def test_compile_explain_honesty_no_guarantee(tmp_path: Path) -> None:
    """The output must NOT claim to guarantee correctness, safety, or PII coverage.

    compile --explain explains decisions; it does not certify outcomes.
    """
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain"])
    assert result.exit_code == 0, result.output
    lower = result.output.lower()
    # Must not make safety guarantees
    for phrase in ("guaranteed safe", "guarantees", "all pii covered", "certif"):
        assert phrase not in lower, (
            f"compile --explain must not claim '{phrase}'. "
            "It explains decisions, not outcomes."
        )


# ---------------------------------------------------------------------------
# compile --explain --json
# ---------------------------------------------------------------------------


def test_compile_explain_json_structure(tmp_path: Path) -> None:
    """--json output must have command, status, columns list."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "compile explain"
    assert payload["status"] == "ok"
    assert "tables" in payload
    assert len(payload["tables"]) == 1
    table = payload["tables"][0]
    assert "name" in table
    assert "columns" in table
    assert len(table["columns"]) == 3


def test_compile_explain_json_column_fields(tmp_path: Path) -> None:
    """Each column in --json output must have name, strategy, rationale."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    col = payload["tables"][0]["columns"][0]
    assert "name" in col
    assert "strategy" in col
    assert "rationale" in col


def test_compile_explain_json_rationale_is_declared_in_config(tmp_path: Path) -> None:
    """Rationale must say 'config' (user-declared), not 'auto-detected' etc."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    for col in payload["tables"][0]["columns"]:
        rationale = col["rationale"].lower()
        assert "config" in rationale, (
            f"Column '{col['name']}' rationale must say 'config' (user-declared). "
            f"Got: {col['rationale']!r}"
        )


def test_compile_explain_json_has_checks(tmp_path: Path) -> None:
    """--json output must have compile_checks with passed/skipped lists."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert "compile_checks" in payload
    cc = payload["compile_checks"]
    assert "passed" in cc
    assert "skipped" in cc
    assert isinstance(cc["passed"], list)
    assert "unknown_provider" in cc["passed"]


# ---------------------------------------------------------------------------
# compile without --explain: plan summary only (no per-column dump)
# ---------------------------------------------------------------------------


def test_compile_no_explain_exits_0(tmp_path: Path) -> None:
    """compile without --explain compiles and shows a plan summary."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path)])
    assert result.exit_code == 0, result.output


def test_compile_no_explain_shows_ok(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path)])
    assert result.exit_code == 0, result.output
    # Should indicate success
    lower = result.output.lower()
    assert "ok" in lower or "pass" in lower or "success" in lower


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_compile_explain_missing_file_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compile", str(tmp_path / "nope.yaml"), "--explain"])
    assert result.exit_code != 0


def test_compile_explain_invalid_yaml_exits_nonzero(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "pipeline.yaml"
    bad_yaml.write_text("{invalid yaml: [}", encoding="utf-8")
    result = runner.invoke(app, ["compile", str(bad_yaml), "--explain"])
    assert result.exit_code != 0


def test_compile_explain_json_quiet_mode(tmp_path: Path) -> None:
    """--quiet produces no stdout, exit 0."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _minimal_config())
    result = runner.invoke(app, ["compile", str(config_path), "--explain", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
