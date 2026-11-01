"""E2E tests for `decoy report show MANIFEST` (file-first, S4a).

`report show` takes an evidence-manifest FILE path and renders it using the
SP-18 report rendering (same as `report summarize` for terminal output, same
as `report render` for file output). The CLI is stateless: there is no
catalog, workspace, or run-id resolution.

Assertions:

RS1. `report show evidence.json` exits 0 and renders the evidence summary.
RS2. `report show evidence.json --json` exits 0 and emits structured JSON.
RS3. `report show missing.json` (no such file) exits non-zero with a clear
     message.
RS4. `report show evidence.json --format html --output path.html` writes an
     HTML report.
RS5. `report show evidence.json` output includes key manifest fields (schema
     version / pipeline fingerprint).
RS6. `report show --help` describes the argument as an evidence manifest path
     (not a run-id) and names no catalog/workspace.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.evidence import build_manifest

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_config(src_path: Path, out_path: Path) -> dict[str, Any]:
    return {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src_path)},
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
            "customers": {"type": "file", "format": "csv", "path": str(out_path)},
        },
    }


def _write_evidence(tmp_path: Path, suffix: str = "") -> tuple[Path, dict[str, Any]]:
    """Write fixture files and an evidence manifest. Returns (evidence_path, manifest)."""
    src_path = tmp_path / f"in{suffix}.csv"
    out_path = tmp_path / f"out{suffix}.csv"
    pipeline_path = tmp_path / f"pipeline{suffix}.yaml"
    evidence_path = tmp_path / f"evidence{suffix}.json"

    src_path.write_text("email\nfoo@bar.com\nbaz@qux.com\n", encoding="utf-8")
    out_path.write_text("email\nA@B.com\nC@D.com\n", encoding="utf-8")
    config_dict = _minimal_config(src_path, out_path)
    pipeline_path.write_text(yaml.dump(config_dict), encoding="utf-8")

    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": 2}},
        cli_version="0.5.0",
        engine_version="0.4.0",
    )
    evidence_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
    return evidence_path, manifest


# ---------------------------------------------------------------------------
# RS1: report show exits 0
# ---------------------------------------------------------------------------


def test_report_show_exits_ok(tmp_path: Path) -> None:
    """report show MANIFEST exits 0 and renders the evidence summary."""
    evidence_path, _ = _write_evidence(tmp_path)

    result = runner.invoke(
        app, ["report", "show", str(evidence_path)], catch_exceptions=False
    )
    assert result.exit_code == 0, f"Expected 0; got {result.exit_code}\n{result.output}"


# ---------------------------------------------------------------------------
# RS2: report show --json
# ---------------------------------------------------------------------------


def test_report_show_json(tmp_path: Path) -> None:
    """report show MANIFEST --json exits 0 with structured JSON."""
    evidence_path, manifest = _write_evidence(tmp_path)

    result = runner.invoke(
        app,
        ["report", "show", "--json", str(evidence_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "report show"
    assert data["evidence_file"] == str(evidence_path)
    assert "manifest" in data
    assert data["manifest"]["run_id"] == manifest["run_id"]


# ---------------------------------------------------------------------------
# RS3: report show for a missing manifest file
# ---------------------------------------------------------------------------


def test_report_show_missing_file_exits_nonzero(tmp_path: Path) -> None:
    """report show for a non-existent manifest file exits non-zero."""
    missing = tmp_path / "nope.json"
    result = runner.invoke(
        app, ["report", "show", str(missing)], catch_exceptions=False
    )
    assert result.exit_code != 0
    output = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "not found" in output.lower() or "evidence" in output.lower()


# ---------------------------------------------------------------------------
# RS4: report show --format html --output
# ---------------------------------------------------------------------------


def test_report_show_html_out(tmp_path: Path) -> None:
    """report show MANIFEST --format html --output path.html writes an HTML report."""
    evidence_path, _ = _write_evidence(tmp_path)
    out_path = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "report", "show", str(evidence_path),
            "--format", "html",
            "--output", str(out_path),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE" in content or "<!doctype" in content.lower()


# ---------------------------------------------------------------------------
# RS5: report show output includes key manifest fields
# ---------------------------------------------------------------------------


def test_report_show_includes_key_fields(tmp_path: Path) -> None:
    """report show includes key manifest fields like schema version / fingerprint."""
    evidence_path, _manifest = _write_evidence(tmp_path)

    result = runner.invoke(
        app, ["report", "show", str(evidence_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    output = result.output
    assert "cli-local-1" in output or "sha256:" in output or "pipeline" in output.lower()


# ---------------------------------------------------------------------------
# RS6: help describes a manifest path, not a run-id or catalog
# ---------------------------------------------------------------------------


def test_report_show_help_is_file_first(tmp_path: Path) -> None:
    """report show --help names an evidence manifest path and no catalog/run-id."""
    result = runner.invoke(app, ["report", "show", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    low = result.output.lower()
    assert "manifest" in low
    # No stale catalog/run-id resolution wording.
    assert "run-id" not in low and "run catalog id" not in low
    assert "workspace" not in low
