"""E2E tests for the stateless CLI (S4a / D3).

The project/catalog/jobs persistence subsystem is gone. Two invariants:

  1. `decoy run --evidence-out ev.json` writes the evidence manifest and
     creates NO `.decoy/` workspace or catalog anywhere (dir-snapshot before
     and after the run).
  2. The removed top-level sub-apps (`project`, `catalog`, `jobs`) are no
     longer registered: invoking them reports "No such command".
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def _snapshot(root: Path) -> set[str]:
    """Relative paths of every file/dir under `root`."""
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.fixture
def mask_config(tmp_path: Path) -> Path:
    """Minimal V2 mask pipeline writing a masked CSV under tmp_path."""
    src = tmp_path / "input.csv"
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "email": ["a@example.com", "b@example.com", "c@example.com"],
        }
    ).to_csv(src, index=False)

    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "customer_id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "faker", "provider": "person_email"},
                ],
            },
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "masked.csv")},
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config), encoding="utf-8")
    return path


def test_run_evidence_out_writes_no_catalog(mask_config: Path, tmp_path: Path) -> None:
    """`run --evidence-out` writes the manifest and creates no `.decoy/`."""
    work = tmp_path / "work"
    work.mkdir()
    evidence_out = work / "ev.json"

    before = _snapshot(work)
    result = runner.invoke(
        app,
        ["run", str(mask_config), "--mode", "mask", "--evidence-out", str(evidence_out)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    # The manifest was written and is a valid evidence manifest.
    assert evidence_out.exists()
    manifest = _json.loads(evidence_out.read_text(encoding="utf-8"))
    assert "run_id" in manifest and "input_fingerprints" in manifest

    # No `.decoy/` workspace or catalog appeared anywhere under the work dir.
    after = _snapshot(work)
    created = after - before
    assert not any(".decoy" in p for p in created), f"stateful dir created: {sorted(created)}"
    assert not any(p.endswith(".duckdb") for p in created), (
        f"a catalog db was written: {sorted(created)}"
    )
    assert str(evidence_out.relative_to(work)) in created


@pytest.mark.parametrize("sub", ["project", "catalog", "jobs"])
def test_removed_subapp_is_no_such_command(sub: str) -> None:
    """The deleted top-level sub-apps report 'No such command'."""
    result = runner.invoke(app, [sub], catch_exceptions=False)
    assert result.exit_code != 0
    combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "No such command" in combined or "no such command" in combined.lower()
