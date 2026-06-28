"""E2E tests for `decoy preflight` (SP-17).

TDD: tests fail first, then implementation makes them pass.

Framing: preflight checks FILE existence, FILE readability, and YAML/SCHEMA
validity. It does NOT check platform conditions, network access, secrets,
vault accessibility, or engine run-time constraints. This is explicitly
documented in the command help and framed honestly in the output.

Assertions:
P1. Config with all source files present -> exits 0 (PASS).
P2. Config with a missing source file -> exits non-zero, reports the missing path.
P3. Invalid YAML -> exits non-zero, reports parse error.
P4. Invalid schema (wrong field) -> exits non-zero, reports schema error.
P5. --json mode emits a structured result with checks/status.
P6. --local flag is accepted and still performs file checks.
P7. Missing source file + --json -> exits non-zero, structured JSON with finding.
P8. --help mentions what preflight checks (honest framing visible in docs).
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_config(tmp_path: Path) -> tuple[dict, Path]:
    """Return (config_dict, config_yaml_path) with source file present."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@b.com", "c@d.com"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "cust_ns",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "out.csv"),
            }
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return cfg, p


def _missing_source_config(tmp_path: Path) -> Path:
    """Config where the source CSV does not exist on disk."""
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "DOES_NOT_EXIST.csv"),
            },
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "cust_ns",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "out.csv"),
            }
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# P1: valid config passes
# ---------------------------------------------------------------------------


def test_preflight_passes_valid_config(tmp_path: Path):
    """preflight exits 0 for a config where all source files exist."""
    _, p = _valid_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(p)])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# P2: missing source file is reported
# ---------------------------------------------------------------------------


def test_preflight_reports_missing_source(tmp_path: Path):
    """preflight exits non-zero and mentions the missing path."""
    p = _missing_source_config(tmp_path)
    result = runner.invoke(app, ["preflight", str(p)])
    assert result.exit_code != 0
    combined = (result.stdout or "") + (result.output or "")
    assert "DOES_NOT_EXIST" in combined


# ---------------------------------------------------------------------------
# P3: invalid YAML
# ---------------------------------------------------------------------------


def test_preflight_invalid_yaml(tmp_path: Path):
    """preflight exits non-zero on a YAML parse error."""
    p = tmp_path / "bad.yaml"
    p.write_text("version: 1\n  bad_indent: [unclosed", encoding="utf-8")
    result = runner.invoke(app, ["preflight", str(p)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P4: schema error
# ---------------------------------------------------------------------------


def test_preflight_schema_error(tmp_path: Path):
    """preflight exits non-zero on a pipeline with a schema violation."""
    # Missing required 'version' field causes pydantic to reject it.
    cfg = {"global_settings": {"seed": 42}, "sources": {}, "tables": [], "targets": {}}
    p = tmp_path / "no_version.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["preflight", str(p)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P5: --json mode
# ---------------------------------------------------------------------------


def test_preflight_json_valid_config(tmp_path: Path):
    """preflight --json exits 0 and emits structured JSON with check results."""
    _, p = _valid_config(tmp_path)
    result = runner.invoke(app, ["preflight", "--json", str(p)])
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["command"] == "preflight"
    assert data["status"] == "ok"
    assert "checks" in data


# ---------------------------------------------------------------------------
# P6: --local flag is accepted
# ---------------------------------------------------------------------------


def test_preflight_local_flag_accepted(tmp_path: Path):
    """--local flag is accepted and performs the same file checks."""
    _, p = _valid_config(tmp_path)
    result = runner.invoke(app, ["preflight", "--local", str(p)])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# P7: missing source + --json
# ---------------------------------------------------------------------------


def test_preflight_json_missing_source(tmp_path: Path):
    """preflight --json with missing source exits non-zero with structured error."""
    p = _missing_source_config(tmp_path)
    result = runner.invoke(app, ["preflight", "--json", str(p)])
    assert result.exit_code != 0
    data = _json.loads(result.stdout)
    assert data["status"] != "ok"
    # Either 'checks' or 'messages' should contain the finding
    combined = _json.dumps(data)
    assert "DOES_NOT_EXIST" in combined or "missing" in combined.lower()


# ---------------------------------------------------------------------------
# P8: --help mentions honest framing
# ---------------------------------------------------------------------------


def test_preflight_help_shows_what_it_checks(tmp_path: Path):
    """--help is reachable and mentions file/source checks."""
    result = runner.invoke(app, ["preflight", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "file" in output or "source" in output
