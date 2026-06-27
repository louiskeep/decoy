"""End-to-end tests for `decoy storm diff`."""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def _write_scan(path: Path, fields: list[dict], **extra) -> Path:
    payload = {
        "row_count": 5,
        "source_label": "sample.csv",
        "sample_strategy": "head",
        "sample_row_cap": None,
        "reid_risk_score": 50.0,
        "quasi_identifier_groups": [],
        "fields": fields,
    }
    payload.update(extra)
    path.write_text(_json.dumps(payload))
    return path


def _field(name: str, score: float = 0.0) -> dict:
    return {
        "name": name,
        "pii_score": score,
        "top_values": [],
        "detector_matches": [],
        "sentinels": [],
    }


@pytest.fixture
def baseline(tmp_path: Path) -> Path:
    return _write_scan(
        tmp_path / "baseline.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
        reid_risk_score=50.0,
    )


# -- help + happy paths --------------------------------------------------


def test_storm_diff_help_includes_examples():
    result = runner.invoke(app, ["storm", "diff", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_storm_diff_identical_scans_reports_no_drift(baseline: Path, tmp_path: Path):
    # Compare baseline against a copy of itself.
    copy = _write_scan(
        tmp_path / "copy.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
        reid_risk_score=50.0,
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(copy), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["drift"] is False
    assert payload["summary"]["added"] == 0
    assert payload["summary"]["removed"] == 0
    assert payload["summary"]["pii_increased"] == 0
    assert payload["summary"]["reid_risk_delta"] == 0.0


# -- categorized changes ------------------------------------------------


def test_storm_diff_detects_added_field(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        [
            _field("customer_id", 0.0),
            _field("first_name", 0.35),
            _field("email", 0.45),
            _field("ssn", 0.95),
        ],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert [r["name"] for r in payload["changes"]["added"]] == ["ssn"]
    assert payload["changes"]["added"][0]["pii_bucket"] == "high"
    # New high-PII field counts as drift.
    assert payload["drift"] is True


def test_storm_diff_detects_removed_field(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35)],
        quasi_identifier_groups=[],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert [r["name"] for r in payload["changes"]["removed"]] == ["email"]
    # Removed fields alone don't count as drift.
    assert payload["drift"] is False


def test_storm_diff_detects_pii_bucket_increase(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        # email goes from 0.45 (med) to 0.7 (high) -- a bucket bump.
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.7)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["summary"]["pii_increased"] == 1
    bumped = payload["changes"]["pii_increased"][0]
    assert bumped["name"] == "email"
    assert bumped["old_bucket"] == "med"
    assert bumped["new_bucket"] == "high"
    assert payload["drift"] is True


def test_storm_diff_detects_pii_bucket_decrease(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        # email goes from 0.45 (med) to 0.0 (none) -- masked away.
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.0)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["summary"]["pii_decreased"] == 1
    # Decreases are an improvement -- never drift.
    assert payload["drift"] is False


def test_storm_diff_detects_new_qi_group(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[
            ["first_name", "email"],
            ["customer_id", "first_name"],
        ],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["summary"]["qi_groups_added"] == 1
    assert payload["drift"] is True


def test_storm_diff_detects_qi_group_member_change(baseline: Path, tmp_path: Path):
    """A QI group with different members is treated as remove + add."""
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "customer_id"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["summary"]["qi_groups_added"] == 1
    assert payload["summary"]["qi_groups_removed"] == 1


def test_storm_diff_reports_reid_risk_delta(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
        reid_risk_score=72.0,
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["summary"]["reid_risk_delta"] == pytest.approx(22.0)


# -- --strict + exit codes ----------------------------------------------


def test_storm_diff_strict_no_drift_exits_zero(baseline: Path, tmp_path: Path):
    copy = _write_scan(
        tmp_path / "copy.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
        reid_risk_score=50.0,
    )
    result = runner.invoke(
        app, ["storm", "diff", str(baseline), str(copy), "--strict"]
    )
    assert result.exit_code == 0


def test_storm_diff_strict_pii_increase_exits_one(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.7)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(
        app, ["storm", "diff", str(baseline), str(new), "--strict"]
    )
    assert result.exit_code == 1


def test_storm_diff_strict_quiet_pii_increase_exits_one_silently(
    baseline: Path, tmp_path: Path
):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.7)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(
        app,
        ["storm", "diff", str(baseline), str(new), "--strict", "--quiet"],
    )
    assert result.exit_code == 1
    assert result.stdout == ""


def test_storm_diff_strict_json_pii_increase_emits_envelope_and_exits_one(
    baseline: Path, tmp_path: Path
):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.7)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(
        app,
        ["storm", "diff", str(baseline), str(new), "--strict", "--json"],
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm diff"
    assert payload["drift"] is True


def test_storm_diff_strict_pii_decrease_alone_exits_zero(
    baseline: Path, tmp_path: Path
):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.0)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(
        app, ["storm", "diff", str(baseline), str(new), "--strict"]
    )
    # Decreases are an improvement, not drift.
    assert result.exit_code == 0


# -- output modes -------------------------------------------------------


def test_storm_diff_quiet_produces_empty_stdout(baseline: Path, tmp_path: Path):
    copy = _write_scan(
        tmp_path / "copy.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(
        app, ["storm", "diff", str(baseline), str(copy), "--quiet"]
    )
    assert result.exit_code == 0
    assert result.stdout == ""


def test_storm_diff_default_renders_card_and_change_tables(
    baseline: Path, tmp_path: Path
):
    new = _write_scan(
        tmp_path / "new.json",
        [
            _field("customer_id", 0.0),
            _field("first_name", 0.35),
            _field("email", 0.7),
            _field("ssn", 0.95),
        ],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new)])
    assert result.exit_code == 0
    # Card heading.
    assert "decoy storm diff" in result.stdout
    # Change tables -- both should appear.
    assert "PII bucket increased" in result.stdout
    assert "Fields added" in result.stdout
    assert "ssn" in result.stdout
    assert "email" in result.stdout


def test_storm_diff_no_changes_prints_no_drift_line(
    baseline: Path, tmp_path: Path
):
    copy = _write_scan(
        tmp_path / "copy.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(copy)])
    assert result.exit_code == 0
    assert "No drift detected" in result.stdout


# -- error paths --------------------------------------------------------


def test_storm_diff_missing_old_exits_user_error(baseline: Path, tmp_path: Path):
    result = runner.invoke(
        app, ["storm", "diff", str(tmp_path / "nope.json"), str(baseline)]
    )
    assert result.exit_code == 1


def test_storm_diff_missing_new_exits_user_error(baseline: Path, tmp_path: Path):
    result = runner.invoke(
        app, ["storm", "diff", str(baseline), str(tmp_path / "nope.json")]
    )
    assert result.exit_code == 1


def test_storm_diff_both_stdin_exits_user_error(baseline: Path):
    result = runner.invoke(app, ["storm", "diff", "-", "-"])
    assert result.exit_code == 1
    # Error message lands on stderr; Click 8.2 stopped mixing into stdout.
    # `result.output` includes both streams.
    assert "only one of OLD or NEW" in result.output


def test_storm_diff_envelope_shape(baseline: Path, tmp_path: Path):
    new = _write_scan(
        tmp_path / "new.json",
        [_field("customer_id", 0.0), _field("first_name", 0.35), _field("email", 0.45)],
        quasi_identifier_groups=[["first_name", "email"]],
    )
    result = runner.invoke(app, ["storm", "diff", str(baseline), str(new), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm diff"
    assert payload["status"] == "ok"
    assert set(payload["summary"]) == {
        "added", "removed", "pii_increased", "pii_decreased",
        "qi_groups_added", "qi_groups_removed", "reid_risk_delta",
    }
    assert set(payload["changes"]) == {
        "added", "removed", "pii_increased", "pii_decreased",
        "qi_groups_added", "qi_groups_removed",
    }
