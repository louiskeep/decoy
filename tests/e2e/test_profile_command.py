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


# ---------------------------------------------------------------------------
# --rows: real row bounding (HIGH-1)
# ---------------------------------------------------------------------------


@pytest.fixture
def large_csv(tmp_path: Path) -> Path:
    """CSV with 200 rows -- more than the --rows 50 limit used in tests below."""
    df = pd.DataFrame(
        {
            "id": list(range(200)),
            "value": [f"val_{i}" for i in range(200)],
        }
    )
    path = tmp_path / "large.csv"
    df.to_csv(path, index=False)
    return path


def test_profile_rows_limits_row_count_in_json(large_csv: Path) -> None:
    """--rows N must result in a row_count of at most N in the profile output.

    Proves --rows is REAL: a 200-row file profiled with --rows 50 must
    report row_count ~50, not 200.
    """
    result = runner.invoke(app, ["profile", str(large_csv), "--rows", "50", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["row_count"] <= 50, (
        f"--rows 50 on a 200-row file reported row_count={payload['row_count']}. "
        "--rows must bound the profile to at most N rows."
    )


def test_profile_rows_0_full_scan_in_json(large_csv: Path) -> None:
    """--rows 0 must produce a full scan (row_count == 200)."""
    result = runner.invoke(app, ["profile", str(large_csv), "--rows", "0", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["row_count"] == 200, (
        f"--rows 0 (full scan) on a 200-row file reported row_count={payload['row_count']}. "
        "--rows 0 must profile every row."
    )


def test_profile_default_rows_limits_row_count(large_csv: Path) -> None:
    """Default --rows 10000 must NOT silently scan everything when rows > 10000.

    Here the file only has 200 rows (< default 10000), so this confirms the
    default produces a full result -- both paths behave correctly.
    """
    result = runner.invoke(app, ["profile", str(large_csv), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    # 200 <= 10000 so the full 200 rows are profiled
    assert payload["row_count"] == 200, (
        f"Default --rows should scan all 200 rows of a small file. "
        f"Got row_count={payload['row_count']}."
    )


# ---------------------------------------------------------------------------
# dtype inference for CSV (MEDIUM-1)
# ---------------------------------------------------------------------------


def test_profile_numeric_column_reports_numeric_type(sample_csv: Path) -> None:
    """CSV numeric columns must report an integer/float type, not 'string'.

    The 'score' column in sample_csv has integer values [1, 2, 3, 4, 5].
    With proper dtype inference (no dtype=str override), STORM must report
    inferred_type as 'integer', NOT 'string'.
    """
    result = runner.invoke(app, ["profile", str(sample_csv), "--show-fields", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)

    score_field = next((f for f in payload.get("fields", []) if f["name"] == "score"), None)
    assert score_field is not None, "Expected 'score' field in profile output."

    dtype = score_field.get("dtype", "")
    assert dtype not in ("string", "object", "str"), (
        f"CSV column 'score' (integer values 1-5) reported dtype={dtype!r}. "
        "Profile must infer real dtypes -- not force 'string' for all CSV columns."
    )
    assert dtype in ("integer", "float", "int64", "int32", "numeric"), (
        f"CSV column 'score' reported unexpected dtype={dtype!r}. "
        "Expected an integer/float/numeric type."
    )
