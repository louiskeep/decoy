"""Raw-value isolation sentry for ``decoy report`` (SP-18).

Dennis review note (cli-first-capability-guide.md L534-538):
  Reporting must build from evidence-safe data only. Do not render full STORM
  profiles or raw diagnostic values into HTML/Markdown by default.

This sentry verifies that the renderers and compare_data CANNOT include raw
data values even if a real source or output file contains PII.

Tests:

Renderer isolation (existing):
1. Builds a valid manifest dict (no raw values by construction).
2. Places a sentinel string ("SENTRY_RAW_VALUE_ZZZZZ") in a sibling file
   in the same tmp directory -- simulating a real source or output CSV.
3. Calls render_html and render_markdown with the manifest ONLY.
4. Asserts the sentinel NEVER appears in either rendered report.

Why: the renderers accept a manifest dict, not a directory. They cannot
accidentally slurp up sibling files. This test proves that invariant holds.

compare_data isolation (new -- SP-18b remediation):
compare_data READS the actual output files. Unlike the renderers, it has
filesystem access. The sentry writes two output files each containing a
UNIQUE SENTINEL value (a distinctive string and a distinctive numeric
outlier), runs compare_data on them, and asserts neither sentinel appears
anywhere in json.dumps(result).

Two lanes -- each with a distinct scope:

  String sentry (CSV -- always runs, no optional dependency required):
  Guards that raw string cell values (potential PII) never appear in the
  compare_data result. The function returns only aggregate counts
  (null_count, unique_count, dtype_kind deltas), so there is no code path
  that could surface a string cell into the result dict. This is the
  always-on guard for that invariant.

  Numeric sentry (Parquet -- requires pyarrow; skipped in no-extras lane):
  Guards the zero-baseline min/max leak: when run A's column max is 0, the
  old max_delta computation (max_b - max_a) equalled the raw max of run B,
  surfacing the actual cell value. The test seeds df_a = [0, 0, 0] and
  df_b = [0, 0, SENTINEL] where SENTINEL is a nine-digit outlier. Under the
  old code max_delta == SENTINEL. Under the current code only
  unique_count_delta=1 is returned -- the sentinel never appears.

If either test fails it means compare_data has re-introduced a path that
surfaces raw cell values -- breaking the evidence-safe contract.
"""

from __future__ import annotations

import json as _json
import uuid
from pathlib import Path
from typing import Any

from decoy.cli.report import compare_data, render_html, render_markdown

# The sentinel must not be a real PII value; it just must be unique enough
# that we are certain it cannot appear in a generated report by coincidence.
_SENTINEL = "SENTRY_RAW_VALUE_ZZZZZ_" + "X" * 20


def _make_manifest_with_file_paths(tmp_path: Path) -> dict[str, Any]:
    """Make a manifest whose file paths point into tmp_path (sentinel lives there too)."""
    return {
        "schema_version": "cli-local-1",
        "producer": "decoy-cli",
        "run_id": str(uuid.uuid4()),
        "run_timestamp": "2026-06-28T10:00:00+00:00",
        "cli_version": "0.5.0",
        "engine_version": "0.4.0",
        "pipeline_path": str(tmp_path / "pipeline.yaml"),
        "pipeline_fingerprint": "sha256:" + "a" * 64,
        "input_fingerprints": {
            "customers": {
                "path": str(tmp_path / "source.csv"),
                "fingerprint": "sha256:" + "b" * 64,
                "fingerprint_method": "full",
                "size_bytes": 512,
            }
        },
        "output_fingerprints": {
            "customers": {
                "path": str(tmp_path / "masked.csv"),
                "fingerprint": "sha256:" + "c" * 64,
                "fingerprint_method": "full",
                "size_bytes": 512,
            }
        },
        "row_counts": {"customers": 50},
        "key_label": None,
        "warnings": [],
        "timings": [],
        "strategies": [{"table": "customers", "column": "email", "strategy": "faker"}],
        "manifest_hash": "sha256:" + "d" * 64,
    }


def test_render_html_does_not_read_sibling_files(tmp_path: Path) -> None:
    """render_html must not include the sentinel from a sibling source file.

    Even though the manifest records paths that point into tmp_path, the
    renderer must not read those files. The sentinel appears only in the
    sibling CSV, never in the manifest dict.
    """
    # Plant the sentinel in a file adjacent to the evidence paths
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(f"email\n{_SENTINEL}@example.com\n", encoding="utf-8")

    masked_csv = tmp_path / "masked.csv"
    masked_csv.write_text("email\nfake@example.com\n", encoding="utf-8")

    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(f"# pipeline\n# {_SENTINEL}\n", encoding="utf-8")

    manifest = _make_manifest_with_file_paths(tmp_path)

    html = render_html(manifest)

    assert _SENTINEL not in html, (
        f"render_html leaked the sentinel '{_SENTINEL}' into the HTML report. "
        "The renderer must build from the manifest dict only -- it must not read "
        "source/output CSV files or any other on-disk data."
    )


def test_render_markdown_does_not_read_sibling_files(tmp_path: Path) -> None:
    """render_markdown must not include the sentinel from a sibling source file."""
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(f"email\n{_SENTINEL}@example.com\n", encoding="utf-8")

    masked_csv = tmp_path / "masked.csv"
    masked_csv.write_text("email\nfake@example.com\n", encoding="utf-8")

    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(f"# {_SENTINEL}\n", encoding="utf-8")

    manifest = _make_manifest_with_file_paths(tmp_path)

    md = render_markdown(manifest)

    assert _SENTINEL not in md, (
        f"render_markdown leaked the sentinel '{_SENTINEL}' into the Markdown report. "
        "The renderer must build from the manifest dict only."
    )


def test_sentinel_actually_present_in_sibling_file(tmp_path: Path) -> None:
    """Negative control: confirm the sentinel IS in the sibling file.

    This ensures the sentry cannot be defeated by the sentinel simply never
    being written. If this test fails, the sentry setup is broken.
    """
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(f"email\n{_SENTINEL}@example.com\n", encoding="utf-8")

    content = source_csv.read_text(encoding="utf-8")
    assert _SENTINEL in content, "Setup error: sentinel not written to sibling file."


# ---------------------------------------------------------------------------
# compare_data raw-value isolation sentry (SP-18b remediation)
# ---------------------------------------------------------------------------

# Two sentinels: a distinctive string and a distinctive numeric outlier.
# The numeric outlier is chosen to be impossible to confuse with an aggregate
# count (row_count, null_count, unique_count) which are small integers in tests.
_STRING_SENTINEL = "SENTRY_DIFF_RAW_PII_" + "Z" * 20
_NUMERIC_SENTINEL = 9_999_777_111  # extremely large -- cannot match any aggregate


def test_compare_data_does_not_leak_raw_string_values(tmp_path: Path) -> None:
    """compare_data must not surface any raw string cell value in its result.

    Writes two CSV files each containing a unique sentinel string in a data
    column. Runs compare_data on them and asserts the sentinel never appears
    in the JSON-serialised result.

    Lane: CSV -- always runs; no optional dependency required.

    What this guards: string cell values (potential PII) must never appear in
    compare_data's output. The function returns only aggregate counts
    (null_count, unique_count, dtype_kind deltas) -- there is no code path
    that could surface a string cell value into the result dict.

    Note: the original min/max/mean leak was specific to numeric columns (the
    zero-baseline case where max_delta equalled the raw max of run B). String
    columns never had min/max/mean computed, so this test does not cover that
    bug directly -- the numeric sentry below is the targeted guard for it.
    This test provides complementary always-on coverage for the string lane.
    """
    # File A: sentinel in one row
    csv_a = tmp_path / "out_a.csv"
    csv_a.write_text(
        f"email\n{_STRING_SENTINEL}@example.com\nother@example.com\n",
        encoding="utf-8",
    )
    # File B: different sentinel to distinguish A-side vs B-side leakage
    csv_b = tmp_path / "out_b.csv"
    csv_b.write_text(
        f"email\n{_STRING_SENTINEL}_B@example.com\nsecond@example.com\n",
        encoding="utf-8",
    )

    output_fps_a = {"data": {"path": str(csv_a)}}
    output_fps_b = {"data": {"path": str(csv_b)}}

    result = compare_data(output_fps_a, output_fps_b)
    serialised = _json.dumps(result)

    assert _STRING_SENTINEL not in serialised, (
        f"compare_data leaked the string sentinel '{_STRING_SENTINEL}' into its "
        "result. The diff path must return only aggregate counts (row_count, "
        "null_count, unique_count, dtype_kind) -- never raw cell values."
    )


def test_compare_data_does_not_leak_raw_numeric_values(tmp_path: Path) -> None:
    """compare_data must not surface raw numeric values via the zero-baseline path.

    This is the targeted guard for the min/max/mean leak that was fixed in
    SP-18b: when run A's column max is 0, the old max_delta computation
    (max_b - max_a) equalled the raw max of run B, surfacing the actual cell
    value. The fix removes min/max/mean entirely; only aggregate counts are
    returned.

    Lane: Parquet -- requires pyarrow; skipped in no-extras lane. The CSV
    always-on lane is covered by test_compare_data_does_not_leak_raw_string_values.

    Data (zero-baseline condition):
      df_a = {"amount": [0, 0, 0]}            -- max=0, unique=1
      df_b = {"amount": [0, 0, SENTINEL]}     -- max=SENTINEL, unique=2

    Under old code: max_delta = SENTINEL - 0 = SENTINEL (raw value in result).
    Under current code: unique_count_delta=1 (no raw value in result).

    If this test fails it means compare_data has re-introduced a path that
    emits raw numeric values -- breaking the evidence-safe contract.
    """
    try:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        import pytest

        pytest.skip("pandas/pyarrow not installed -- skipping numeric sentry")

    # Zero-baseline condition: run A max=0, run B max=SENTINEL.
    # Under old code max_delta == SENTINEL (raw leak). Under current code
    # only unique_count_delta=1 is emitted.
    df_a = pd.DataFrame({"amount": [0, 0, 0]})
    df_b = pd.DataFrame({"amount": [0, 0, _NUMERIC_SENTINEL]})

    parquet_a = tmp_path / "out_a.parquet"
    parquet_b = tmp_path / "out_b.parquet"
    pq.write_table(pa.Table.from_pandas(df_a), str(parquet_a))
    pq.write_table(pa.Table.from_pandas(df_b), str(parquet_b))

    output_fps_a = {"data": {"path": str(parquet_a)}}
    output_fps_b = {"data": {"path": str(parquet_b)}}

    result = compare_data(output_fps_a, output_fps_b)
    serialised = _json.dumps(result)

    assert str(_NUMERIC_SENTINEL) not in serialised, (
        f"compare_data leaked the numeric sentinel '{_NUMERIC_SENTINEL}' into its "
        "result. The diff path must return only aggregate counts (row_count, "
        "null_count, unique_count, dtype_kind) -- never raw cell values "
        "(min, max, mean, or derived deltas thereof)."
    )


def test_compare_data_sentry_setup_negative_control(tmp_path: Path) -> None:
    """Negative control: confirm both sentinels ARE present in the data files.

    If this test fails the sentry setup is broken and the isolation tests
    above would give false assurance.
    """
    csv_a = tmp_path / "out_a.csv"
    csv_a.write_text(
        f"email\n{_STRING_SENTINEL}@example.com\n",
        encoding="utf-8",
    )
    content = csv_a.read_text(encoding="utf-8")
    assert _STRING_SENTINEL in content, (
        "Setup error: string sentinel not written to test file."
    )
