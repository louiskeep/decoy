"""End-to-end tests for `decoy storm fields` and `decoy storm show`."""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()


@pytest.fixture
def scan_file(tmp_path: Path) -> Path:
    """Hand-built scan JSON -- avoids depending on engine detector behaviour."""
    path = tmp_path / "scan.json"
    path.write_text(
        _json.dumps(
            {
                "row_count": 5,
                "source_label": "sample.csv",
                "sample_strategy": "head",
                "sample_row_cap": None,
                "reid_risk_score": 88.9,
                "quasi_identifier_groups": [["first_name", "email"]],
                "fields": [
                    {
                        "name": "customer_id",
                        "pii_score": 0.0,
                        "top_values": [],
                        "detector_matches": [],
                        "sentinels": [],
                    },
                    {
                        "name": "first_name",
                        "pii_score": 0.35,
                        "top_values": [{"value": "Alice", "count": 1}],
                        "detector_matches": [{"detector": "name"}],
                        "sentinels": [],
                    },
                    {
                        "name": "email",
                        "pii_score": 0.7,
                        "top_values": [],
                        "detector_matches": [{"detector": "email"}],
                        "sentinels": [],
                    },
                    {
                        "name": "ssn",
                        "pii_score": 0.95,
                        "top_values": [],
                        "detector_matches": [{"detector": "ssn"}],
                        "sentinels": [{"value": "000-00-0000", "count": 0}],
                    },
                ],
            }
        )
    )
    return path


# -- storm fields -------------------------------------------------------


def test_storm_fields_help_includes_examples():
    result = runner.invoke(app, ["storm", "fields", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_storm_fields_lists_all_fields_by_default(scan_file: Path):
    result = runner.invoke(app, ["storm", "fields", str(scan_file)])
    assert result.exit_code == 0, result.stdout
    for name in ("customer_id", "first_name", "email", "ssn"):
        assert name in result.stdout


def test_storm_fields_pii_high_filters_correctly(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "fields", str(scan_file), "--pii", "high", "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    names = sorted(f["name"] for f in payload["fields"])
    assert names == ["email", "ssn"]
    assert payload["matched"] == 2
    assert payload["total"] == 4


def test_storm_fields_quasi_filter_returns_qi_members(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "fields", str(scan_file), "--quasi", "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    names = sorted(f["name"] for f in payload["fields"])
    assert names == ["email", "first_name"]


def test_storm_fields_combined_filters_intersect(scan_file: Path):
    result = runner.invoke(
        app,
        ["storm", "fields", str(scan_file), "--pii", "high", "--quasi", "--json"],
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    # Only email is both high PII and a QI member.
    assert [f["name"] for f in payload["fields"]] == ["email"]


def test_storm_fields_quiet_produces_empty_stdout(scan_file: Path):
    result = runner.invoke(app, ["storm", "fields", str(scan_file), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_storm_fields_json_envelope_shape(scan_file: Path):
    result = runner.invoke(app, ["storm", "fields", str(scan_file), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm fields"
    assert payload["status"] == "ok"
    assert payload["total"] == 4
    assert payload["matched"] == 4
    by_name = {f["name"]: f for f in payload["fields"]}
    assert by_name["ssn"]["pii_bucket"] == "high"
    assert by_name["customer_id"]["pii_bucket"] == "none"
    assert by_name["email"]["quasi_identifier"] is True
    assert by_name["ssn"]["quasi_identifier"] is False


def test_storm_fields_invalid_pii_value_exits_user_error(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "fields", str(scan_file), "--pii", "extreme"]
    )
    assert result.exit_code != 0


def test_storm_fields_missing_scan_exits_user_error(tmp_path: Path):
    result = runner.invoke(
        app, ["storm", "fields", str(tmp_path / "nope.json")]
    )
    assert result.exit_code == 1


def test_storm_fields_no_match_prints_friendly_hint(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "fields", str(scan_file), "--pii", "none", "--quasi"]
    )
    assert result.exit_code == 0
    assert "No fields match" in result.stdout


def test_storm_fields_csv_input_emits_scan_first_hint(tmp_path: Path):
    """Passing a raw CSV instead of a scan -> friendly 'scan it first' hint."""
    csv = tmp_path / "patients.csv"
    csv.write_text("customer_id,first_name,email\n1,Alice,a@x.com\n")
    result = runner.invoke(app, ["storm", "fields", str(csv)])
    assert result.exit_code == 1
    # The error names the file and identifies it as raw data.
    assert "patients.csv" in result.stdout
    assert "raw data" in result.stdout
    # The hint includes the literal scan command the user should run.
    assert "decoy storm scan" in result.stdout


def test_storm_fields_csv_input_json_emits_error_envelope(tmp_path: Path):
    csv = tmp_path / "patients.csv"
    csv.write_text("a,b,c\n1,2,3\n")
    result = runner.invoke(app, ["storm", "fields", str(csv), "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm fields"
    assert payload["status"] == "error"
    assert "raw data" in payload["error"]


# -- storm show ---------------------------------------------------------


def test_storm_show_help_includes_examples():
    result = runner.invoke(app, ["storm", "show", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_storm_show_renders_field_card(scan_file: Path):
    result = runner.invoke(app, ["storm", "show", str(scan_file), "ssn"])
    assert result.exit_code == 0, result.stdout
    assert "ssn" in result.stdout
    assert "PII score" in result.stdout
    assert "high" in result.stdout


def test_storm_show_includes_top_values_table(scan_file: Path):
    result = runner.invoke(app, ["storm", "show", str(scan_file), "first_name"])
    assert result.exit_code == 0
    assert "Top values" in result.stdout
    assert "Alice" in result.stdout


def test_storm_show_includes_qi_membership(scan_file: Path):
    result = runner.invoke(app, ["storm", "show", str(scan_file), "email"])
    assert result.exit_code == 0
    assert "Quasi-identifier" in result.stdout
    assert "first_name" in result.stdout


def test_storm_show_includes_sentinels_table(scan_file: Path):
    result = runner.invoke(app, ["storm", "show", str(scan_file), "ssn"])
    assert result.exit_code == 0
    assert "Sentinel" in result.stdout
    assert "000-00-0000" in result.stdout


def test_storm_show_unknown_field_exits_with_did_you_mean(scan_file: Path):
    result = runner.invoke(app, ["storm", "show", str(scan_file), "ssm"])
    assert result.exit_code == 1
    assert "ssn" in result.stdout  # the suggestion


def test_storm_show_json_envelope_shape(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "show", str(scan_file), "ssn", "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm show"
    assert payload["status"] == "ok"
    assert payload["field"]["name"] == "ssn"
    assert payload["pii_bucket"] == "high"
    assert payload["quasi_identifier_groups"] == []


def test_storm_show_quiet_produces_empty_stdout(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "show", str(scan_file), "ssn", "--quiet"]
    )
    assert result.exit_code == 0
    assert result.stdout == ""


def test_storm_show_unknown_field_json_emits_error_envelope(scan_file: Path):
    result = runner.invoke(
        app, ["storm", "show", str(scan_file), "wat", "--json"]
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm show"
    assert payload["status"] == "error"
    assert payload["field"] == "wat"


def test_storm_show_accepts_envelope_shape(tmp_path: Path):
    """`storm scan --json` envelopes wrap the profile in a `profile` key --
    `storm show` should accept that shape too, matching forecast's loader.
    """
    path = tmp_path / "envelope.json"
    path.write_text(
        _json.dumps(
            {
                "command": "storm scan",
                "status": "ok",
                "profile": {
                    "row_count": 1,
                    "quasi_identifier_groups": [],
                    "fields": [{"name": "x", "pii_score": 0.1}],
                },
            }
        )
    )
    result = runner.invoke(app, ["storm", "show", str(path), "x"])
    assert result.exit_code == 0
    assert "x" in result.stdout


def test_storm_show_csv_input_emits_scan_first_hint(tmp_path: Path):
    csv = tmp_path / "patients.csv"
    csv.write_text("customer_id,first_name,email\n1,Alice,a@x.com\n")
    # Even a valid-looking field name doesn't help -- we should bail at load.
    result = runner.invoke(app, ["storm", "show", str(csv), "first_name"])
    assert result.exit_code == 1
    assert "patients.csv" in result.stdout
    assert "raw data" in result.stdout
    assert "decoy storm scan" in result.stdout
