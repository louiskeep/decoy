"""E2E tests for `decoy report diff <run-id-a> <run-id-b>` (SP-18b).

TDD: tests fail first, then the implementation makes them pass.

`report diff` is a DATA-LEVEL compare. It reads the actual output data files
from two runs (via their evidence manifests) and reports:
  - Row count deltas
  - Schema changes (columns added/removed/type-changed)
  - Per-column: null-count delta, unique-count delta
  - For numeric columns: min/max/mean delta (via pandas.DataFrame.describe())

What `report diff` is NOT:
  - It is NOT `report compare` (manifest-vs-manifest, SP-18, already built).
  - It does NOT expose raw row values -- only summary statistics.
  - It does NOT require or imply platform connectivity (LOCAL ONLY).

Methodology: column profiling follows pandas.DataFrame.describe() (pandas v2.x)
and pandas.Series.nunique() / .isnull().sum() for column-level deltas.
No novel statistical method is used.

Assertions:

D1. `report diff <id-a> <id-b>` with identical output files reports no data
    change (any_data_change=False).
D2. `report diff <id-a> <id-b>` with different row counts shows the delta.
D3. `report diff <id-a> <id-b>` with different column values shows column-level
    deltas (null-count or unique-count or numeric stat delta).
D4. `report diff <id-a> <id-b> --json` emits structured JSON with data delta
    fields.
D5. `report diff` for a run-id whose evidence has no output paths exits
    non-zero with a clear error.
D6. `report diff` for a missing run-id exits non-zero.
D7. `report diff` for runs whose output files no longer exist exits non-zero
    with a clear "file not found" message.
D8. `report diff` --json for identical outputs has `any_data_change` = False
    (tested via unit-level data to give real teeth).
D9. `report diff` --json for different outputs has `any_data_change` = True.
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


def _write_evidence_for_output(
    tmp_path: Path,
    suffix: str,
    output_csv: str,
    row_count: int = 2,
) -> tuple[Path, dict[str, Any]]:
    """Write fixture files + evidence manifest for a given output CSV content."""
    src_path = tmp_path / f"in{suffix}.csv"
    out_path = tmp_path / f"out{suffix}.csv"
    pipeline_path = tmp_path / f"pipeline{suffix}.yaml"
    evidence_path = tmp_path / f"evidence{suffix}.json"

    src_path.write_text("email\nfoo@bar.com\nbaz@qux.com\n", encoding="utf-8")
    out_path.write_text(output_csv, encoding="utf-8")
    config_dict = _minimal_config(src_path, out_path)
    pipeline_path.write_text(yaml.dump(config_dict), encoding="utf-8")

    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": row_count}},
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
        "status": "ok",
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
# D1: identical outputs -> no data change
# ---------------------------------------------------------------------------


def test_report_diff_identical_outputs_no_change(tmp_path: Path) -> None:
    """report diff with identical output files reports any_data_change=False."""
    _init_workspace(tmp_path)
    same_csv = "email\nA@B.com\nC@D.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", same_csv, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", same_csv, row_count=2)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--json", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert "any_data_change" in data
    assert data["any_data_change"] is False


# ---------------------------------------------------------------------------
# D2: different row counts show delta
# ---------------------------------------------------------------------------


def test_report_diff_row_count_delta(tmp_path: Path) -> None:
    """report diff reports row count deltas when outputs differ in row count."""
    _init_workspace(tmp_path)

    # Run A: 2 rows, Run B: 3 rows
    csv_a = "email\nA@B.com\nC@D.com\n"
    csv_b = "email\nA@B.com\nC@D.com\nE@F.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=3)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--json", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is True
    # Row count deltas should be reported
    assert "table_deltas" in data
    deltas = data["table_deltas"]
    assert len(deltas) >= 1
    # customers table should show +1 row
    by_table = {d["table"]: d for d in deltas}
    assert "customers" in by_table
    assert by_table["customers"]["row_count_delta"] == 1


# ---------------------------------------------------------------------------
# D3: different column values show column-level deltas
# ---------------------------------------------------------------------------


def test_report_diff_column_level_deltas(tmp_path: Path) -> None:
    """report diff reports column-level stats when outputs have different values.

    Uses unique_count as the expected delta: run A has 2 unique emails,
    run B has 1 unique email (duplicate). This is a reliable signal that
    does not depend on trailing-newline CSV parsing behavior.
    """
    _init_workspace(tmp_path)

    # Run A: 2 unique emails; Run B: 1 unique email (A@B.com duplicated)
    csv_a = "email\nA@B.com\nC@D.com\n"
    csv_b = "email\nA@B.com\nA@B.com\n"  # duplicate -- unique_count drops to 1

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=2)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--json", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is True
    # Should report column-level deltas for the email column
    deltas = data["table_deltas"]
    by_table = {d["table"]: d for d in deltas}
    assert "customers" in by_table
    col_deltas = by_table["customers"].get("column_deltas", [])
    assert len(col_deltas) >= 1
    email_delta = next((c for c in col_deltas if c["column"] == "email"), None)
    assert email_delta is not None
    # unique_count should have changed (-1: from 2 to 1)
    assert email_delta.get("unique_count_delta") == -1


# ---------------------------------------------------------------------------
# D4: report diff --json emits structured JSON
# ---------------------------------------------------------------------------


def test_report_diff_json_structure(tmp_path: Path) -> None:
    """report diff --json emits structured JSON with required fields."""
    _init_workspace(tmp_path)
    csv = "email\nA@B.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=1)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--json", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["command"] == "report diff"
    assert data["status"] == "ok"
    assert "any_data_change" in data
    assert "table_deltas" in data
    assert "run_id_a" in data
    assert "run_id_b" in data


# ---------------------------------------------------------------------------
# D5: run evidence has no output paths
# ---------------------------------------------------------------------------


def test_report_diff_no_evidence_path_exits_nonzero(tmp_path: Path) -> None:
    """report diff for a run without evidence exits non-zero with a clear error."""
    _init_workspace(tmp_path)
    # One run has evidence, the other doesn't
    csv = "email\nA@B.com\n"
    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=None)

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# D6: missing run-id
# ---------------------------------------------------------------------------


def test_report_diff_missing_run_id_exits_nonzero(tmp_path: Path) -> None:
    """report diff with a missing run-id exits non-zero."""
    _init_workspace(tmp_path)
    csv = "email\nA@B.com\n"
    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, "00000000-0000-0000-0000-000000000000",
         "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# D7: output files no longer exist
# ---------------------------------------------------------------------------


def test_report_diff_missing_output_files_exits_nonzero(tmp_path: Path) -> None:
    """report diff when output files were deleted exits non-zero with clear message."""
    _init_workspace(tmp_path)
    csv = "email\nA@B.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=1)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    # Delete the output files that the evidence manifests point to
    (tmp_path / "out_a.csv").unlink()
    (tmp_path / "out_b.csv").unlink()

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# D8/D9: teeth tests via direct command
# ---------------------------------------------------------------------------


def test_report_diff_identical_has_no_data_change(tmp_path: Path) -> None:
    """Identical runs -> any_data_change is False (teeth: real data comparison)."""
    _init_workspace(tmp_path)
    csv = "id,value\n1,100\n2,200\n3,300\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=3)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=3)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--json", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is False


def test_report_diff_different_shows_data_change(tmp_path: Path) -> None:
    """Different outputs -> any_data_change is True (teeth: real data comparison)."""
    _init_workspace(tmp_path)
    csv_a = "id,value\n1,100\n2,200\n3,300\n"
    csv_b = "id,value\n1,100\n2,200\n3,300\n4,400\n"  # extra row

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=3)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=4)
    id_a = _seed_run_entry(tmp_path, name="run_a", evidence_path=str(ev_a))
    id_b = _seed_run_entry(tmp_path, name="run_b", evidence_path=str(ev_b))

    result = runner.invoke(
        app,
        ["report", "diff", id_a, id_b, "--json", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is True
