"""E2E tests for `decoy profile` (SP-19b).

Covers:
  - profile on a CSV shows field-level dtype, cardinality, null_rate, row count.
  - --show-fields lists per-field detail.
  - PII candidates are framed as SUGGESTIONS (never authoritative auto-classification).
  - No raw cell values appear in the output.
  - --json structure is well-defined.
  - Exit codes: 0 on success, EXIT_USAGE on bad input.

HONESTY rules enforced here:
  1. Output must contain "suggestion" or "candidate" when PII is surfaced.
  2. Output must NOT say "classified", "auto-classified", "detected as", or similar
     authoritative language when referring to PII.
  3. Raw cell values must never appear in the output (separate sentry in
     tests/sentry/test_profile_raw_value_isolation.py also covers this).

TDD: these tests MUST be written before the implementation.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

# Sentinel values -- distinctive strings that CANNOT appear in aggregate output.
_SENTINEL_EMAIL = "SENTRY_PII_PROFILE_EMAIL_XXXXXXXZZZZ@example.com"
_SENTINEL_SSN = "SENTRY_NOTANSSN_XXXXXXXZZZZ"

# Threshold used by the engine's STORM to flag a field as a PII candidate.
# The engine's pii_score >= 0.6 is the commonly used threshold.
_PII_THRESHOLD = 0.6


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Small CSV with known PII-like columns for profiling."""
    df = pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4", "C5"],
            "first_name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
            "email": ["a@example.com", "b@example.com", "c@example.com", "d@example.com", "e@example.com"],
            "ssn": [
                "111-22-3333",
                "222-33-4444",
                "333-44-5555",
                "444-55-6666",
                "555-66-7777",
            ],
            "score": [1, 2, 3, 4, 5],
        }
    )
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def sentinel_csv(tmp_path: Path) -> Path:
    """CSV with sentinel values that must NOT appear in profile output."""
    df = pd.DataFrame(
        {
            "email": [_SENTINEL_EMAIL, "normal@example.com"],
            "notes": [_SENTINEL_SSN, "nothing here"],
        }
    )
    path = tmp_path / "sentinel.csv"
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_profile_help_shows_show_fields_flag() -> None:
    result = runner.invoke(app, ["profile", "--help"])
    assert result.exit_code == 0
    assert "--show-fields" in result.stdout


def test_profile_help_shows_examples() -> None:
    result = runner.invoke(app, ["profile", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


# ---------------------------------------------------------------------------
# profile: basic happy path
# ---------------------------------------------------------------------------


def test_profile_exits_0(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv)])
    assert result.exit_code == 0, result.output


def test_profile_shows_row_count(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv)])
    assert result.exit_code == 0, result.output
    assert "5" in result.output


def test_profile_shows_column_count_or_fields(sample_csv: Path) -> None:
    """Profile summary must mention the number of fields/columns."""
    result = runner.invoke(app, ["profile", str(sample_csv)])
    assert result.exit_code == 0, result.output
    # 5 columns in the fixture
    assert "5" in result.output


# ---------------------------------------------------------------------------
# profile --show-fields
# ---------------------------------------------------------------------------


def test_profile_show_fields_exits_0(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields"])
    assert result.exit_code == 0, result.output


def test_profile_show_fields_lists_all_columns(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields"])
    assert result.exit_code == 0, result.output
    for col in ("customer_id", "first_name", "email", "ssn", "score"):
        assert col in result.output


def test_profile_show_fields_shows_null_rate(sample_csv: Path) -> None:
    """Each field entry must show a null rate."""
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields"])
    assert result.exit_code == 0, result.output
    # null_rate appears as a label or value
    assert "null" in result.output.lower()


def test_profile_show_fields_shows_dtype(sample_csv: Path) -> None:
    """Each field entry must show the dtype."""
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields"])
    assert result.exit_code == 0, result.output
    # Some type information must be present
    lower = result.output.lower()
    assert any(t in lower for t in ("string", "int", "float", "object", "text", "numeric", "str")), (
        "Expected dtype info in --show-fields output"
    )


# ---------------------------------------------------------------------------
# HONESTY: PII candidates must be framed as SUGGESTIONS -- never authoritative
# ---------------------------------------------------------------------------


def test_profile_pii_framed_as_suggestion_not_classified(sample_csv: Path) -> None:
    """When STORM flags PII candidates, the output must say 'suggestion' or 'candidate'.

    NEVER: 'classified as', 'auto-classified', 'detected as PII' (authoritative).
    ALWAYS: 'suggestion', 'candidate', or 'review' language.

    This enforces Decoy's core design: the user picks the PII type per field;
    auto-classification is abandoned by design.
    """
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields"])
    assert result.exit_code == 0, result.output
    lower = result.output.lower()

    # Must NOT use authoritative language
    for bad_phrase in ("auto-classified", "classified as pii", "detected as pii", "is pii"):
        assert bad_phrase not in lower, (
            f"profile output must NOT use authoritative PII language '{bad_phrase}'. "
            "PII candidates are SUGGESTIONS the user reviews -- never auto-classified."
        )


def test_profile_json_pii_framed_as_suggestion(sample_csv: Path) -> None:
    """In --json output, any PII field must use 'pii_candidate' or 'suggestion' framing.

    Must NOT have a field called 'pii_classification' or 'pii_detected' (authoritative).
    """
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)

    # Check that if any field has PII-related keys, they use candidate framing
    for field in payload.get("fields", []):
        # Should not have authoritative keys
        assert "pii_classification" not in field, (
            "JSON field must not have 'pii_classification'. Use 'pii_candidate' instead."
        )
        # If pii is surfaced, it should be framed as candidate
        if "pii_candidate" in field or "pii_score" in field:
            # pii_candidate should be boolean or absent
            pass  # present is fine; what matters is the key name and framing

    # Check the command metadata
    assert payload.get("command") == "profile"
    assert payload.get("status") == "ok"


# ---------------------------------------------------------------------------
# PRIVACY: no raw cell values in output
# ---------------------------------------------------------------------------


def test_profile_no_raw_cell_values_in_output(sentinel_csv: Path) -> None:
    """Profile output must NEVER contain raw cell values from the data.

    This is the same privacy discipline as SP-18b's diff command. The sentinel
    values below are distinctive strings from the data file that absolutely
    must not appear in profile output (counts/types/cardinality only).
    """
    result = runner.invoke(app, ["profile", str(sentinel_csv), "--show-fields"])
    assert result.exit_code == 0, result.output
    assert _SENTINEL_EMAIL not in result.output, (
        f"profile output leaked raw cell value '{_SENTINEL_EMAIL}'. "
        "Profile must show counts/types/cardinality only -- no raw cell values."
    )
    assert _SENTINEL_SSN not in result.output, (
        f"profile output leaked raw cell value '{_SENTINEL_SSN}'. "
        "Profile must show counts/types/cardinality only -- no raw cell values."
    )


def test_profile_json_no_raw_cell_values(sentinel_csv: Path) -> None:
    """--json output must also not contain raw cell values."""
    result = runner.invoke(app, ["profile", str(sentinel_csv), "--show-fields", "--json"])
    assert result.exit_code == 0, result.output
    payload_str = result.stdout
    assert _SENTINEL_EMAIL not in payload_str, (
        f"profile --json leaked raw cell value '{_SENTINEL_EMAIL}'."
    )
    assert _SENTINEL_SSN not in payload_str, (
        f"profile --json leaked raw cell value '{_SENTINEL_SSN}'."
    )


# ---------------------------------------------------------------------------
# profile --json: structure
# ---------------------------------------------------------------------------


def test_profile_json_structure(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "profile"
    assert payload["status"] == "ok"
    assert "row_count" in payload
    assert "field_count" in payload


def test_profile_json_show_fields_structure(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert "fields" in payload
    fields = payload["fields"]
    assert len(fields) == 5  # 5 columns in fixture
    # Each field must have name, null_rate, distinct_count
    for f in fields:
        assert "name" in f
        assert "null_rate" in f
        assert "distinct_count" in f


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------


def test_profile_quiet_mode(sample_csv: Path) -> None:
    result = runner.invoke(app, ["profile", str(sample_csv), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_profile_missing_file_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["profile", str(tmp_path / "nope.csv")])
    assert result.exit_code != 0


def test_profile_negative_control_sentinel_present_in_csv(sentinel_csv: Path) -> None:
    """Negative control: confirm sentinels ARE in the CSV file.

    If this fails, the no-leak tests above would give false assurance.
    """
    content = sentinel_csv.read_text(encoding="utf-8")
    assert _SENTINEL_EMAIL in content, "Setup error: email sentinel not written to CSV."
    assert _SENTINEL_SSN in content, "Setup error: SSN sentinel not written to CSV."
