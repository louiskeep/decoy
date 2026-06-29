"""E2E tests for `decoy report show <run-id>` (SP-18b).

TDD: tests fail first, then the implementation makes them pass.

`report show <run-id>` resolves a catalog run entry to its evidence artifact,
then renders it using the SP-18 report rendering (same as `report summarize`
for terminal output, same as `report render` for file output).

Resolution path: catalog entry id -> metadata.evidence_path -> load manifest
-> render.

Assertions:

RS1. `report show <run-id>` exits 0 and renders the evidence summary.
RS2. `report show <run-id> --json` exits 0 and emits structured JSON.
RS3. `report show <run-id>` for a run with no evidence path exits non-zero
     with a clear message (honest about what is missing).
RS4. `report show` for a missing run-id exits non-zero.
RS5. `report show <run-id> --format html --out path.html` writes an HTML report.
RS6. `report show <run-id>` output includes key manifest fields (run id, schema
     version, pipeline fingerprint).
RS7. `report show` without a workspace exits non-zero.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.catalog import _open_catalog
from decoy.cli.evidence import build_manifest

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_workspace(tmp_path: Path) -> Path:
    result = runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0, f"project init failed: {result.output}"
    return tmp_path


def _minimal_config(src_path: Path, out_path: Path) -> dict[str, Any]:
    return {
        "version": 1,
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


def _seed_run_entry(
    workspace: Path,
    *,
    name: str = "pipeline",
    evidence_path: str | None = None,
    config_path: str = "/tmp/pipeline.yaml",
    status: str = "ok",
) -> str:
    """Insert a run entry into the catalog and return the entry id."""
    import json as _j
    from datetime import datetime, timezone
    from uuid import uuid4

    entry_id = str(uuid4())
    run_id = str(uuid4())
    recorded_at = datetime.now(tz=timezone.utc).isoformat()

    meta: dict[str, Any] = {
        "run_id": run_id,
        "status": status,
        "mode": "mask",
        "elapsed_s": 1.0,
        "config_path": config_path,
        "engine_version": "0.4.0",
        "cli_version": "0.5.0",
        "run_timestamp": recorded_at,
    }
    if evidence_path is not None:
        meta["evidence_path"] = evidence_path

    conn = _open_catalog(workspace)
    try:
        conn.execute(
            """
            INSERT INTO entries
                (id, entry_type, name, path, recorded_at, metadata, sensitivity_class)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry_id,
                "run",
                name,
                evidence_path or config_path,
                recorded_at,
                _j.dumps(meta),
                "evidence-safe",
            ],
        )
    finally:
        conn.close()

    return entry_id


# ---------------------------------------------------------------------------
# RS1: report show exits 0
# ---------------------------------------------------------------------------


def test_report_show_exits_ok(tmp_path: Path) -> None:
    """report show <run-id> exits 0 and renders the evidence summary."""
    _init_workspace(tmp_path)
    evidence_path, _ = _write_evidence(tmp_path)
    entry_id = _seed_run_entry(tmp_path, evidence_path=str(evidence_path))

    result = runner.invoke(
        app, ["report", "show", entry_id, "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0, f"Expected 0; got {result.exit_code}\n{result.output}"


# ---------------------------------------------------------------------------
# RS2: report show --json
# ---------------------------------------------------------------------------


def test_report_show_json(tmp_path: Path) -> None:
    """report show <run-id> --json exits 0 with structured JSON."""
    _init_workspace(tmp_path)
    evidence_path, manifest = _write_evidence(tmp_path)
    entry_id = _seed_run_entry(tmp_path, evidence_path=str(evidence_path))

    result = runner.invoke(
        app,
        ["report", "show", "--json", entry_id, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "report show"
    assert "manifest" in data
    assert data["manifest"]["run_id"] == manifest["run_id"]


# ---------------------------------------------------------------------------
# RS3: report show for run without evidence path
# ---------------------------------------------------------------------------


def test_report_show_no_evidence_path_exits_nonzero(tmp_path: Path) -> None:
    """report show for a run with no evidence path exits non-zero with a clear message."""
    _init_workspace(tmp_path)
    # Seed a run entry without evidence_path
    entry_id = _seed_run_entry(tmp_path, evidence_path=None)

    result = runner.invoke(
        app, ["report", "show", entry_id, "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code != 0
    # Must say something useful about no evidence
    output = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "evidence" in output.lower() or "no" in output.lower()


# ---------------------------------------------------------------------------
# RS4: report show for missing run-id
# ---------------------------------------------------------------------------


def test_report_show_missing_run_id_exits_nonzero(tmp_path: Path) -> None:
    """report show with a non-existent run-id exits non-zero."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app,
        ["report", "show", "00000000-0000-0000-0000-000000000000", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# RS5: report show --format html --out
# ---------------------------------------------------------------------------


def test_report_show_html_out(tmp_path: Path) -> None:
    """report show <run-id> --format html --out path.html writes an HTML report."""
    _init_workspace(tmp_path)
    evidence_path, _ = _write_evidence(tmp_path)
    entry_id = _seed_run_entry(tmp_path, evidence_path=str(evidence_path))
    out_path = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "report", "show", entry_id,
            "--format", "html",
            "--out", str(out_path),
            "--workspace", str(tmp_path),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE" in content or "<!doctype" in content.lower()


# ---------------------------------------------------------------------------
# RS6: report show output includes key manifest fields
# ---------------------------------------------------------------------------


def test_report_show_includes_key_fields(tmp_path: Path) -> None:
    """report show includes key manifest fields like schema version and pipeline fingerprint."""
    _init_workspace(tmp_path)
    evidence_path, _manifest = _write_evidence(tmp_path)
    entry_id = _seed_run_entry(tmp_path, evidence_path=str(evidence_path))

    result = runner.invoke(
        app, ["report", "show", entry_id, "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    output = result.output
    # Schema version or pipeline fingerprint must appear
    assert "cli-local-1" in output or "sha256:" in output or "pipeline" in output.lower()


# ---------------------------------------------------------------------------
# RS7: report show without workspace
# ---------------------------------------------------------------------------


def test_report_show_no_workspace_exits_nonzero(tmp_path: Path) -> None:
    """report show without an initialized workspace exits non-zero."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        app,
        ["report", "show", "00001111", "--workspace", str(empty)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
