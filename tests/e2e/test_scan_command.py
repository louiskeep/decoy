"""E2E tests for the S3a `decoy pre-scan` merge behaviors.

These cover the behaviors unique to the profile+analyze merge (not already
carried by the ported profile tests): persist-only-on-`--output`,
`--output -` streaming, the PII-honesty framing (H4) in both human and JSON,
and the privacy-safe field record (H5) that drops raw aggregates.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "sample.csv"
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4", "C5"],
            "first_name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
            "email": ["a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com"],
            "ssn": ["111-22-3333", "222-33-4444", "333-44-5555", "444-55-6666", "555-66-7777"],
        }
    ).to_csv(path, index=False)
    return path


@pytest.fixture
def large_csv(tmp_path: Path) -> Path:
    path = tmp_path / "large.csv"
    pd.DataFrame({"id": list(range(200)), "value": [f"v{i}" for i in range(200)]}).to_csv(
        path, index=False
    )
    return path


# ---------------------------------------------------------------------------
# Default command: exit 0 + PII-honesty framing (H4)
# ---------------------------------------------------------------------------


def test_scan_exits_0(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv)])
    assert result.exit_code == 0, result.output


def test_scan_human_frames_pii_as_suggestions(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv)])
    assert result.exit_code == 0, result.output
    lower = result.output.lower()
    # Positive: candidates are framed as suggestions / review.
    assert "suggestion" in lower or "review" in lower
    # Negative: never authoritative classification language.
    for bad in ("auto-classified", "classified as pii", "detected as pii", "is pii"):
        assert bad not in lower


def test_scan_json_carries_pii_note_and_counts(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "pre-scan"
    assert payload["status"] == "ok"
    assert payload["pii_candidate_count"] >= 1
    # H4: the honesty note travels in JSON.
    assert "pii_note" in payload
    assert "suggestion" in payload["pii_note"].lower()
    assert "never auto-classifies" in payload["pii_note"].lower()


# ---------------------------------------------------------------------------
# Persist only on --output (H7b)
# ---------------------------------------------------------------------------


def test_scan_output_writes_json_file(sample_csv: Path, tmp_path: Path) -> None:
    out = tmp_path / "scan.json"
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    payload = _json.loads(out.read_text())
    assert payload["row_count"] == 5
    assert payload["fields"]


def test_scan_without_output_writes_no_file(sample_csv: Path, tmp_path: Path) -> None:
    """No auto scan_<ts>.json: nothing may appear next to the source or in cwd."""
    before = set(sample_csv.parent.iterdir())
    result = runner.invoke(app, ["pre-scan", str(sample_csv)])
    assert result.exit_code == 0, result.output
    after = set(sample_csv.parent.iterdir())
    assert after == before, f"scan wrote an unrequested file: {after - before}"


def test_scan_output_dash_streams_to_stdout(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--output", "-"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    # The streamed artifact is the value-free projection, not the rich profile.
    assert payload["row_count"] == 5
    assert "source_label" not in payload
    assert all("top_values" not in f for f in payload["fields"])


# ---------------------------------------------------------------------------
# `--output -` conflicts with the privacy-safe stdout contracts.
#
# Regression for the final-gate finding: `--output -` streams the rich,
# raw-value-bearing profile to stdout, and the stream path used to win
# unconditionally -- so `--output - -q` leaked the full profile despite quiet,
# and `--output - --json` emitted that raw artifact instead of the
# privacy-safe envelope. The combination is now rejected up front (EXIT_USAGE)
# before the scan runs, so neither mode can leak.
# ---------------------------------------------------------------------------


def test_scan_output_dash_with_json_is_rejected(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--output", "-", "--json"])
    assert result.exit_code == 1  # EXIT_USAGE: invalid flag combination
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["command"] == "pre-scan"
    # The raw profile must NOT have streamed: the only stdout is the error envelope.
    assert "fields" not in payload
    assert "source_label" not in result.stdout  # the rich artifact's marker key


def test_scan_output_dash_with_quiet_is_rejected(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--output", "-", "-q"])
    assert result.exit_code == 1  # EXIT_USAGE
    # Quiet's contract holds: nothing on stdout (the rich profile never streamed).
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Privacy-safe field record (H5): no raw aggregates in inline / --json output
# ---------------------------------------------------------------------------


def test_scan_show_fields_json_has_no_raw_aggregates(sample_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--show-fields", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    for f in payload["fields"]:
        for banned in ("top_values", "min_value", "max_value", "mode_value", "mean_value"):
            assert banned not in f, f"privacy leak: {banned} in field record {f['name']}"
        # The allowed privacy-safe keys.
        assert set(f) <= {
            "name", "dtype", "null_rate", "distinct_count",
            "pii_score", "pii_candidate", "detector_hits",
        }


# ---------------------------------------------------------------------------
# --rows default bounds the sample (H7a)
# ---------------------------------------------------------------------------


def test_scan_rows_default_bounds_sample(large_csv: Path) -> None:
    """A huge-file guard: --rows bounds the sample; --rows 50 caps at 50."""
    result = runner.invoke(app, ["pre-scan", str(large_csv), "--rows", "50", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["row_count"] <= 50


def test_scan_rows_zero_full_scan(large_csv: Path) -> None:
    result = runner.invoke(app, ["pre-scan", str(large_csv), "--rows", "0", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["row_count"] == 200
    assert payload["sample_strategy"] == "full"


# ---------------------------------------------------------------------------
# Removed surfaces -> "No such command"; post-scan integrity is registered.
# ---------------------------------------------------------------------------


def test_top_level_profile_is_gone() -> None:
    result = runner.invoke(app, ["profile", "some.csv"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_post_scan_integrity_registered() -> None:
    # The integrity check lives under the Post-scan phase.
    result = runner.invoke(app, ["post-scan", "integrity", "--help"])
    assert result.exit_code == 0
    assert "--source" in result.output


def test_pre_scan_profiler_failure_exits_runtime_without_raw_text(
    sample_csv: Path, monkeypatch
) -> None:
    """A requested pre-scan that cannot run is a non-zero exit, never a clean
    result, and the error carries the exception type name only."""
    import decoy_engine

    from decoy.cli.exit_codes import EXIT_RUNTIME

    def boom(*_a, **_k):
        raise RuntimeError("raw cell value SECRET-ABC-123")

    monkeypatch.setattr(decoy_engine, "profile_columns", boom)
    result = runner.invoke(app, ["pre-scan", str(sample_csv), "--json"])
    assert result.exit_code == EXIT_RUNTIME
    assert "SECRET-ABC-123" not in result.output
    assert _json.loads(result.stdout)["status"] == "error"
