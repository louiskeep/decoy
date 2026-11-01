"""E2E tests for `decoy report diff MANIFEST_A MANIFEST_B` (file-first, S4a).

`report diff` is a DATA-LEVEL compare. It takes two evidence-manifest FILE
paths, reads the actual output data files referenced by each manifest, and
reports:
  - Row count deltas
  - Schema changes (columns added/removed/type-changed)
  - Per-column: null-count delta, unique-count delta

The CLI is stateless: diff takes file paths, not catalog run-ids, and never
resolves a workspace.

What `report diff` is NOT:
  - It is NOT `report compare` (manifest-vs-manifest fingerprints, SP-18).
  - It does NOT expose raw row values or numeric min/max/mean -- only aggregate
    counts (row-count, null-count, unique-count, dtype changes).

Methodology: pandas.Series.nunique() / .isnull().sum() for column-level counts
(pandas v2.x). No novel statistical method is used.

Assertions:

D1. identical output files -> any_data_change=False.
D2. different row counts -> row-count delta reported.
D3. different column values -> column-level deltas.
D4. --json emits structured JSON with the required fields.
D5. a missing manifest file exits non-zero.
D6. output files that no longer exist exits non-zero with a clear message.
D7/D8. teeth: identical -> False, different -> True.
D9. --json output contains NO min_delta/max_delta/mean_delta keys.
D10. human-readable (no --json) renders a column-deltas table.
D11. --help describes two evidence manifest paths and no catalog/run-id.
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


# ---------------------------------------------------------------------------
# D1: identical outputs -> no data change
# ---------------------------------------------------------------------------


def test_report_diff_identical_outputs_no_change(tmp_path: Path) -> None:
    """report diff with identical output files reports any_data_change=False."""
    same_csv = "email\nA@B.com\nC@D.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", same_csv, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", same_csv, row_count=2)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
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
    csv_a = "email\nA@B.com\nC@D.com\n"
    csv_b = "email\nA@B.com\nC@D.com\nE@F.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=3)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is True
    assert "table_deltas" in data
    by_table = {d["table"]: d for d in data["table_deltas"]}
    assert "customers" in by_table
    assert by_table["customers"]["row_count_delta"] == 1


# ---------------------------------------------------------------------------
# D3: different column values show column-level deltas
# ---------------------------------------------------------------------------


def test_report_diff_column_level_deltas(tmp_path: Path) -> None:
    """report diff reports column-level stats when outputs have different values."""
    csv_a = "email\nA@B.com\nC@D.com\n"
    csv_b = "email\nA@B.com\nA@B.com\n"  # duplicate -- unique_count drops to 1

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=2)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is True
    by_table = {d["table"]: d for d in data["table_deltas"]}
    assert "customers" in by_table
    col_deltas = by_table["customers"].get("column_deltas", [])
    assert len(col_deltas) >= 1
    email_delta = next((c for c in col_deltas if c["column"] == "email"), None)
    assert email_delta is not None
    assert email_delta.get("unique_count_delta") == -1


# ---------------------------------------------------------------------------
# D4: report diff --json emits structured JSON
# ---------------------------------------------------------------------------


def test_report_diff_json_structure(tmp_path: Path) -> None:
    """report diff --json emits structured JSON with required fields."""
    csv = "email\nA@B.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=1)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["command"] == "report diff"
    assert data["status"] == "ok"
    assert "any_data_change" in data
    assert "table_deltas" in data
    assert data["evidence_file_a"] == str(ev_a)
    assert data["evidence_file_b"] == str(ev_b)


# ---------------------------------------------------------------------------
# D5: a missing manifest file
# ---------------------------------------------------------------------------


def test_report_diff_missing_manifest_exits_nonzero(tmp_path: Path) -> None:
    """report diff for a missing manifest file exits non-zero."""
    csv = "email\nA@B.com\n"
    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    missing = tmp_path / "nope.json"

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(missing)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# D6: output files no longer exist -> manifest-level only (note, not failure)
# ---------------------------------------------------------------------------


def test_report_diff_missing_output_files_succeeds_manifest_only(tmp_path: Path) -> None:
    """report diff degrades to manifest-level when output files are gone (exit 0, note)."""
    csv = "email\nA@B.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=1)

    # Delete the output files that the evidence manifests point to.
    (tmp_path / "out_a.csv").unlink()
    (tmp_path / "out_b.csv").unlink()

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b)],
        catch_exceptions=False,
    )
    # S4b superset contract: a missing output file is a NOTE, not a failure.
    assert result.exit_code == 0, result.output
    combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "data-level" in combined.lower() or "missing" in combined.lower()


def test_report_diff_missing_output_files_json_skips_data_level(tmp_path: Path) -> None:
    """report diff --json still returns the manifest-level envelope when files are gone."""
    csv = "email\nA@B.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=1)
    (tmp_path / "out_a.csv").unlink()
    (tmp_path / "out_b.csv").unlink()

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["command"] == "report diff"
    assert data["status"] == "ok"
    # Manifest-level fields always present.
    assert "pipeline_fingerprint_changed" in data
    # Data level was skipped because the output files are gone.
    assert data["data_level"] == "skipped"
    assert data["any_data_change"] is None
    assert data["missing_files"]


def test_report_diff_require_data_hard_fails_on_missing(tmp_path: Path) -> None:
    """--require-data restores today's strict hard-fail when output files are gone."""
    csv = "email\nA@B.com\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=1)
    (tmp_path / "out_a.csv").unlink()
    (tmp_path / "out_b.csv").unlink()

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--require-data"],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# D6b: a referenced output file EXISTS but is corrupt/unreadable.
#
# Regression for the final-gate finding: the data-level boundary caught only a
# missing parquet READER (RuntimeError), so a corrupt parquet raised
# ArrowInvalid (a ValueError) straight out of `report diff --json`, crashing
# with a traceback and producing no JSON. A present-but-unreadable file must
# degrade exactly like a missing one: manifest-level still reported, data level
# skipped, and --require-data still hard-fails -- never a crash, never the raw
# parser message (it can echo file bytes).
# ---------------------------------------------------------------------------


def _write_parquet_evidence(tmp_path: Path, suffix: str) -> Path:
    """Write a VALID parquet output + its evidence manifest, then return the
    manifest path. The caller corrupts the parquet afterward to simulate
    post-run corruption (the manifest was fingerprinted while it was valid)."""
    import pandas as pd

    src_path = tmp_path / f"in{suffix}.csv"
    out_path = tmp_path / f"out{suffix}.parquet"
    pipeline_path = tmp_path / f"pipeline{suffix}.yaml"
    evidence_path = tmp_path / f"evidence{suffix}.json"

    src_path.write_text("email\nfoo@bar.com\nbaz@qux.com\n", encoding="utf-8")
    pd.DataFrame({"email": ["a@b.com", "c@d.com"]}).to_parquet(out_path)

    config_dict = _minimal_config(src_path, out_path)
    config_dict["targets"]["customers"]["format"] = "parquet"
    pipeline_path.write_text(yaml.dump(config_dict), encoding="utf-8")

    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": 2}},
        cli_version="0.5.0",
        engine_version="0.4.0",
    )
    evidence_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
    return evidence_path


def test_report_diff_corrupt_output_json_degrades(tmp_path: Path) -> None:
    """A corrupt parquet output degrades `report diff --json` to manifest-level
    (exit 0, valid JSON, data level skipped) instead of crashing with no JSON."""
    ev_a = _write_parquet_evidence(tmp_path, "_a")
    ev_b = _write_parquet_evidence(tmp_path, "_b")

    # Corrupt both outputs AFTER the manifests were fingerprinted.
    for name in ("out_a.parquet", "out_b.parquet"):
        (tmp_path / name).write_bytes(b"this is not a parquet file")

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)  # fail-before: no JSON at all (ArrowInvalid)
    assert data["command"] == "report diff"
    assert data["status"] == "ok"
    assert data["data_level"] == "skipped"
    assert data["missing_files"]  # the unreadable outputs land here
    # The raw parser message must not leak into the envelope.
    assert "ArrowInvalid" not in result.stdout
    assert "this is not a parquet" not in result.stdout


def test_report_diff_corrupt_output_require_data_hard_fails(tmp_path: Path) -> None:
    """--require-data still hard-fails when an output file is present but corrupt."""
    ev_a = _write_parquet_evidence(tmp_path, "_a")
    ev_b = _write_parquet_evidence(tmp_path, "_b")
    for name in ("out_a.parquet", "out_b.parquet"):
        (tmp_path / name).write_bytes(b"this is not a parquet file")

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--require-data"],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# D6c: manifest-level comparison (absorbed `report compare`) always runs
# ---------------------------------------------------------------------------


def test_report_diff_reports_pipeline_fingerprint_change(tmp_path: Path) -> None:
    """report diff --json always runs the manifest-level compare (absorbed compare)."""
    import copy

    from decoy.cli.evidence import compute_manifest_hash

    csv = "email\nA@B.com\n"
    ev_a, manifest = _write_evidence_for_output(tmp_path, "_a", csv, row_count=1)

    new_manifest = copy.deepcopy(manifest)
    new_manifest["pipeline_fingerprint"] = "sha256:" + "b" * 64
    new_manifest["manifest_hash"] = compute_manifest_hash(new_manifest)
    ev_b = tmp_path / "evidence_b.json"
    ev_b.write_text(_json.dumps(new_manifest, indent=2), encoding="utf-8")

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["pipeline_fingerprint_changed"] is True


# ---------------------------------------------------------------------------
# D7/D8: teeth tests via real data comparison
# ---------------------------------------------------------------------------


def test_report_diff_identical_has_no_data_change(tmp_path: Path) -> None:
    """Identical outputs -> any_data_change is False (teeth: real data comparison)."""
    csv = "id,value\n1,100\n2,200\n3,300\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv, row_count=3)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv, row_count=3)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is False


def test_report_diff_different_shows_data_change(tmp_path: Path) -> None:
    """Different outputs -> any_data_change is True (teeth: real data comparison)."""
    csv_a = "id,value\n1,100\n2,200\n3,300\n"
    csv_b = "id,value\n1,100\n2,200\n3,300\n4,400\n"  # extra row

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=3)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=4)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["any_data_change"] is True


# ---------------------------------------------------------------------------
# D9: --json output contains NO min/max/mean delta keys
# ---------------------------------------------------------------------------


def test_report_diff_json_has_no_min_max_mean(tmp_path: Path) -> None:
    """report diff --json must not emit min_delta, max_delta, or mean_delta."""
    csv_a = "id,score\n1,10\n2,20\n3,30\n"
    csv_b = "id,score\n1,10\n2,20\n3,30\n4,40\n"

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=3)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=4)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    raw_json = result.stdout
    assert "min_delta" not in raw_json, "min_delta must not appear in report diff output"
    assert "max_delta" not in raw_json, "max_delta must not appear in report diff output"
    assert "mean_delta" not in raw_json, "mean_delta must not appear in report diff output"


# ---------------------------------------------------------------------------
# D10: human-readable (non --json) renders column-deltas table
# ---------------------------------------------------------------------------


def test_report_diff_human_readable_renders_column_table(tmp_path: Path) -> None:
    """report diff (no --json) renders a column-deltas table when columns differ."""
    csv_a = "email\nA@B.com\nC@D.com\n"
    csv_b = "email\nA@B.com\nA@B.com\n"  # unique_count drops to 1

    ev_a, _ = _write_evidence_for_output(tmp_path, "_a", csv_a, row_count=2)
    ev_b, _ = _write_evidence_for_output(tmp_path, "_b", csv_b, row_count=2)

    result = runner.invoke(
        app,
        ["report", "diff", str(ev_a), str(ev_b)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    output = result.output
    assert "email" in output
    assert "data changes detected" in output.lower() or "column" in output.lower()


# ---------------------------------------------------------------------------
# D11: --help is file-first
# ---------------------------------------------------------------------------


def test_report_diff_help_is_file_first() -> None:
    """report diff --help names evidence manifest paths and no catalog/run-id."""
    result = runner.invoke(app, ["report", "diff", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    low = result.output.lower()
    assert "manifest" in low
    assert "run-id" not in low and "catalog run id" not in low
    assert "workspace" not in low
