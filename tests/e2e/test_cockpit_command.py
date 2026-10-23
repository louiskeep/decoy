"""E2E tests for the surviving standalone cockpit command, `decoy doctor`.

SP-19 shipped the cockpit as `strategies`/`providers`/`checksums`/`validators`
sub-apps plus `doctor`. S3b (CLI redesign) folded the four registry sub-apps
into `decoy list KIND` / `decoy show KIND NAME` -- those are covered by
`test_reference_command.py` now. `doctor` stays a standalone command and is
tested here.
"""

from __future__ import annotations

import json as _json

from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def test_doctor_help():
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


def test_doctor_exits_0():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, f"doctor exited non-zero:\n{result.stdout}"


def test_doctor_json_exits_0():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "doctor"
    assert payload["status"] == "pass"


def test_doctor_shows_engine_and_python():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    # Both checks appear in human output.
    assert "python" in result.stdout
    assert "decoy_engine" in result.stdout


def test_doctor_json_has_checks_array():
    result = runner.invoke(app, ["doctor", "--json"])
    payload = _json.loads(result.stdout)
    assert isinstance(payload["checks"], list)
    assert len(payload["checks"]) > 0
    for c in payload["checks"]:
        assert "name" in c
        assert "status" in c
        assert "kind" in c
        assert "note" in c


def test_doctor_quiet_exits_0():
    result = runner.invoke(app, ["doctor", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
