"""Raw-value isolation sentry for `decoy profile` (SP-19b).

Enforces the same privacy discipline as SP-18b's diff command: the profile
output must NEVER include raw cell values from the source data.

Rationale: STORM profiles contain counts, null rates, and cardinality data.
They must NOT contain top_values, mode_value, min_value, max_value, or any
other raw aggregates that could reconstruct original values. The profile CLI
command wraps run_storm but explicitly strips any raw-value fields before
emitting output.

Test structure mirrors test_report_raw_value_isolation.py:
  1. Write a CSV with a distinctive sentinel value in every data column.
  2. Invoke the `profile` CLI command.
  3. Assert the sentinel NEVER appears in stdout, not even partially.

This sentry is separate from the e2e tests so it runs in the sentry
tier (which catches regressions even when the e2e suite is skipped).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

# Sentinels: must be distinctive enough to never appear in aggregate output.
_STRING_SENTINEL = "SENTRY_PROFILE_RAW_PII_" + "Z" * 20
_SENTINEL_SSN = "888-77-6655-SENTRY_PROFILE"


def _write_sentinel_csv(path: Path) -> None:
    """Write a CSV whose cells contain distinctive sentinel strings."""
    df = pd.DataFrame(
        {
            "email": [f"{_STRING_SENTINEL}@nowhere.test", "a@b.com"],
            "ssn": [_SENTINEL_SSN, "000-00-0000"],
            "name": [f"USER_{_STRING_SENTINEL}", "Jane"],
        }
    )
    df.to_csv(path, index=False)


def test_profile_text_output_no_raw_values(tmp_path: Path) -> None:
    """profile text output must not contain any sentinel cell value.

    Even partial matches are banned (e.g. the sentinel string appearing as
    part of a 'top value' or 'example value' section).
    """
    csv_path = tmp_path / "data.csv"
    _write_sentinel_csv(csv_path)

    result = runner.invoke(app, ["profile", str(csv_path), "--show-fields"])
    assert result.exit_code == 0, result.output

    assert _STRING_SENTINEL not in result.output, (
        f"profile --show-fields leaked sentinel '{_STRING_SENTINEL}' into text output. "
        "Profile must emit counts/types/cardinality only -- never raw cell values."
    )
    assert _SENTINEL_SSN not in result.output, (
        f"profile --show-fields leaked sentinel '{_SENTINEL_SSN}' into text output."
    )


def test_profile_json_output_no_raw_values(tmp_path: Path) -> None:
    """profile --json output must not contain any sentinel cell value."""
    csv_path = tmp_path / "data.csv"
    _write_sentinel_csv(csv_path)

    result = runner.invoke(app, ["profile", str(csv_path), "--show-fields", "--json"])
    assert result.exit_code == 0, result.output

    payload_str = result.stdout
    assert _STRING_SENTINEL not in payload_str, (
        f"profile --json leaked sentinel '{_STRING_SENTINEL}'. "
        "JSON output must emit only aggregate fields -- no raw cell values."
    )
    assert _SENTINEL_SSN not in payload_str, (
        f"profile --json leaked sentinel '{_SENTINEL_SSN}'."
    )


def test_sentinel_is_present_in_source_file(tmp_path: Path) -> None:
    """Negative control: sentinels MUST be present in the CSV.

    If this test fails the sentry setup is broken and the isolation tests
    above give false assurance.
    """
    csv_path = tmp_path / "data.csv"
    _write_sentinel_csv(csv_path)
    content = csv_path.read_text(encoding="utf-8")
    assert _STRING_SENTINEL in content, "Setup error: string sentinel not in CSV."
    assert _SENTINEL_SSN in content, "Setup error: SSN sentinel not in CSV."
