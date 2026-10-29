"""E2E tests for `decoy report show` and `decoy report verify` (SP-17).

TDD: these tests fail first, then the implementation makes them pass.

Assertions:
S1. `report show <evidence.json>` exits 0 and renders key fields.
S2. `report show --json <evidence.json>` exits 0 with structured JSON.
S3. `report show missing.json` exits 1 with an error message.
S4. `report show bad.json` (invalid JSON) exits 1 with an error message.

V1. `report verify <evidence.json>` exits 0 when all files are unchanged.
V2. `report verify` exits non-zero when the pipeline file has changed.
V3. `report verify` exits non-zero when an input file has changed.
V4. `report verify` exits non-zero when an output file has changed.
V5. `report verify` exits non-zero when the manifest_hash has been tampered.
V6. `report verify --json` emits structured JSON (clean and tampered cases).
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.evidence import build_manifest

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _minimal_config(src_path: Path, out_path: Path) -> dict:
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


def _write_evidence(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Write all fixture files and evidence.json; return
    (evidence_path, pipeline_path, src_path, out_path)."""
    src_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.csv"
    pipeline_path = tmp_path / "pipeline.yaml"
    evidence_path = tmp_path / "evidence.json"

    src_path.write_text("email\nfoo@bar.com\nbaz@qux.com\n", encoding="utf-8")
    out_path.write_text("email\nA@B.com\nC@D.com\n", encoding="utf-8")
    config_dict = _minimal_config(src_path, out_path)
    pipeline_path.write_text(yaml.dump(config_dict), encoding="utf-8")

    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": 2}},
        cli_version="0.1.0",
        engine_version="0.3.1",
    )
    evidence_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
    return evidence_path, pipeline_path, src_path, out_path


# ---------------------------------------------------------------------------
# S1-S4: report show
# ---------------------------------------------------------------------------


def test_evidence_show_clean(tmp_path: Path):
    """report show exits 0 and renders key manifest fields."""
    evidence_path, _, _, _ = _write_evidence(tmp_path)
    result = runner.invoke(app, ["report", "show", str(evidence_path)])
    assert result.exit_code == 0
    # Key fields should appear in the output
    output = result.stdout + (result.output or "")
    assert "pipeline" in output.lower() or "fingerprint" in output.lower()


def test_evidence_show_json(tmp_path: Path):
    """report show --json exits 0 and emits valid JSON with status ok."""
    evidence_path, _, _, _ = _write_evidence(tmp_path)
    result = runner.invoke(app, ["report", "show", "--json", str(evidence_path)])
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "report show"
    assert "manifest" in data


def test_evidence_show_missing_file(tmp_path: Path):
    """report show on a missing file exits 1."""
    result = runner.invoke(app, ["report", "show", str(tmp_path / "no_such.json")])
    assert result.exit_code != 0


def test_evidence_show_invalid_json(tmp_path: Path):
    """report show on a non-JSON file exits 1."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all {broken", encoding="utf-8")
    result = runner.invoke(app, ["report", "show", str(bad)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# V1-V6: report verify
# ---------------------------------------------------------------------------


def test_evidence_verify_clean(tmp_path: Path):
    """report verify exits 0 when all files are unchanged."""
    evidence_path, _, _, _ = _write_evidence(tmp_path)
    result = runner.invoke(app, ["report", "verify", str(evidence_path)])
    assert result.exit_code == 0


def test_evidence_verify_detects_changed_pipeline(tmp_path: Path):
    """report verify exits non-zero when the pipeline file has changed."""
    evidence_path, pipeline_path, _, _ = _write_evidence(tmp_path)
    pipeline_path.write_text("version: 2\n# TAMPERED\n", encoding="utf-8")
    result = runner.invoke(app, ["report", "verify", str(evidence_path)])
    assert result.exit_code != 0


def test_evidence_verify_detects_changed_input(tmp_path: Path):
    """report verify exits non-zero when an input file has changed."""
    evidence_path, _, src_path, _ = _write_evidence(tmp_path)
    src_path.write_text("email\ntampered@evil.com\n", encoding="utf-8")
    result = runner.invoke(app, ["report", "verify", str(evidence_path)])
    assert result.exit_code != 0


def test_evidence_verify_detects_changed_output(tmp_path: Path):
    """report verify exits non-zero when an output file has changed."""
    evidence_path, _, _, out_path = _write_evidence(tmp_path)
    out_path.write_text("email\naltered@evil.com\n", encoding="utf-8")
    result = runner.invoke(app, ["report", "verify", str(evidence_path)])
    assert result.exit_code != 0


def test_evidence_verify_detects_tampered_manifest_hash(tmp_path: Path):
    """report verify exits non-zero when the manifest_hash field is wrong."""
    evidence_path, _, _, _ = _write_evidence(tmp_path)
    # Corrupt the manifest_hash field
    manifest = _json.loads(evidence_path.read_text(encoding="utf-8"))
    manifest["manifest_hash"] = "0" * 64
    evidence_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
    result = runner.invoke(app, ["report", "verify", str(evidence_path)])
    assert result.exit_code != 0


def test_evidence_verify_json_clean(tmp_path: Path):
    """report verify --json exits 0 and emits JSON with status ok."""
    evidence_path, _, _, _ = _write_evidence(tmp_path)
    result = runner.invoke(app, ["report", "verify", "--json", str(evidence_path)])
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "report verify"


def test_evidence_verify_json_tampered(tmp_path: Path):
    """report verify --json with tamper exits non-zero and emits JSON with issues."""
    evidence_path, pipeline_path, _, _ = _write_evidence(tmp_path)
    pipeline_path.write_text("version: 2\n# TAMPERED\n", encoding="utf-8")
    result = runner.invoke(app, ["report", "verify", "--json", str(evidence_path)])
    assert result.exit_code != 0
    data = _json.loads(result.stdout)
    assert data["status"] != "ok"
    assert "issues" in data
    assert len(data["issues"]) > 0
