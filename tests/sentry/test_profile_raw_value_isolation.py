"""Raw-value isolation sentry for `decoy profile` (SP-19b).

Enforces the same privacy discipline as SP-18b's diff command: the profile
output must NEVER include raw cell values from the source data.

Rationale: STORM profiles contain counts, null rates, and cardinality data.
They must NOT contain top_values, mode_value, min_value, max_value, or any
other raw aggregates that could reconstruct original values. The profile CLI
command wraps run_storm but explicitly strips any raw-value fields before
emitting output.

Text-lane implementation note:
  The text sentry forces COLUMNS=10000 in the test invocation so Rich does NOT
  truncate table cells with an ellipsis.  Without a wide console, Rich silently
  clips long cell values at the terminal width and a long sentinel such as
  SENTRY_PROFILE_RAW_PII_ZZZZZZZZZZZZZZZZZZZZ would appear as
  "SENTRY_PROFILE_RAW_PI..." -- meaning `sentinel in output` could pass even
  when there IS a leak, because only a prefix of the sentinel is present.
  Forcing a wide console makes the text lane genuinely bite.

  test_text_sentry_bites_if_raw_value_injected below proves this: it
  monkeypatches a raw value into a profile cell and confirms the isolation
  test would flag it under wide-console rendering.

Test structure:
  1. Write a CSV with a distinctive sentinel value in every data column.
  2. Invoke the `profile` CLI command with COLUMNS=10000.
  3. Assert the sentinel NEVER appears in stdout, not even partially.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

# Sentinels: must be distinctive enough to never appear in aggregate output.
_STRING_SENTINEL = "SENTRY_PROFILE_RAW_PII_" + "Z" * 20
_SENTINEL_SSN = "888-77-6655-SENTRY_PROFILE"

# Wide environment forces Rich to render cells without truncation.
_WIDE_ENV = {"COLUMNS": "10000"}


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

    Renders through a wide (10000-col) console so Rich does NOT truncate cells.
    Even partial matches are banned (e.g. the sentinel string appearing as
    part of a 'top value' or 'example value' section).
    """
    csv_path = tmp_path / "data.csv"
    _write_sentinel_csv(csv_path)

    result = runner.invoke(
        app, ["profile", str(csv_path), "--show-fields"], env=_WIDE_ENV
    )
    assert result.exit_code == 0, result.output

    assert _STRING_SENTINEL not in result.output, (
        f"profile --show-fields leaked sentinel '{_STRING_SENTINEL}' into text output. "
        "Profile must emit counts/types/cardinality only -- never raw cell values."
    )
    assert _SENTINEL_SSN not in result.output, (
        f"profile --show-fields leaked sentinel '{_SENTINEL_SSN}' into text output."
    )


def test_text_sentry_bites_if_raw_value_injected(tmp_path: Path) -> None:
    """Prove the wide-console text sentry detects raw cell leaks.

    Monkeypatches _safe_field_record to inject the sentinel into a profile
    cell (simulating a bug that emits raw values), then verifies the isolation
    test WOULD catch it -- i.e., the sentinel appears un-truncated in the
    wide-console output.  Reverts the patch at the end.

    If this test FAILS, the sentry is still decorative: the wide console is
    not wide enough or Rich is truncating via another path.
    """
    csv_path = tmp_path / "data.csv"
    _write_sentinel_csv(csv_path)

    import decoy.cli.profile as profile_mod

    original_safe = profile_mod._safe_field_record

    def leaky_safe_field_record(field_stats):
        rec = original_safe(field_stats)
        # Inject sentinel into the dtype cell to simulate a raw-value leak.
        rec["dtype"] = _STRING_SENTINEL
        return rec

    with patch.object(profile_mod, "_safe_field_record", leaky_safe_field_record):
        result = runner.invoke(
            app, ["profile", str(csv_path), "--show-fields"], env=_WIDE_ENV
        )

    assert result.exit_code == 0, result.output
    # With a leaky implementation the sentinel MUST appear in the wide output.
    assert _STRING_SENTINEL in result.output, (
        "Wide-console sentry did NOT catch the injected sentinel. "
        "The text sentry is still decorative: widen the console further or "
        "switch to JSON-mode assertion."
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
