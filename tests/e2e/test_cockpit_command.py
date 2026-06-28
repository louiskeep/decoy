"""E2E tests for SP-19 cockpit commands.

These complement the unit tests (which do the anti-drift correspondence
assertions). The E2E layer verifies help text, shell-level exit codes, and
basic flag behaviour for each cockpit sub-command.
"""

from __future__ import annotations

import json as _json

from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------


def test_strategies_help():
    result = runner.invoke(app, ["strategies", "--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout
    assert "inspect" in result.stdout


def test_strategies_list_help_includes_examples():
    result = runner.invoke(app, ["strategies", "list", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


def test_strategies_list_exits_0():
    result = runner.invoke(app, ["strategies", "list"])
    assert result.exit_code == 0


def test_strategies_list_json_structure():
    result = runner.invoke(app, ["strategies", "list", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "strategies list"
    assert payload["status"] == "ok"
    assert isinstance(payload["strategies"], list)
    assert payload["count"] > 0
    first = payload["strategies"][0]
    assert "name" in first
    assert "class" in first


def test_strategies_inspect_exits_0_for_known():
    result = runner.invoke(app, ["strategies", "inspect", "faker"])
    assert result.exit_code == 0


def test_strategies_inspect_help():
    result = runner.invoke(app, ["strategies", "inspect", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


def test_strategies_inspect_missing_name_exits_nonzero():
    result = runner.invoke(app, ["strategies", "inspect", "no_such_strategy"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------


def test_providers_help():
    result = runner.invoke(app, ["providers", "--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout
    assert "inspect" in result.stdout


def test_providers_list_exits_0():
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0


def test_providers_list_json_structure():
    result = runner.invoke(app, ["providers", "list", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "providers list"
    assert payload["status"] == "ok"
    assert isinstance(payload["providers"], list)
    assert payload["count"] > 0
    first = payload["providers"][0]
    assert "name" in first
    assert "backend_type" in first
    assert "poolable" in first


def test_providers_inspect_known_provider():
    result = runner.invoke(app, ["providers", "inspect", "uuid"])
    assert result.exit_code == 0


def test_providers_inspect_json_fields():
    result = runner.invoke(app, ["providers", "inspect", "synthetic_npi", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["name"] == "synthetic_npi"
    assert "backend_type" in payload
    assert "poolable" in payload
    assert "supports_deterministic" in payload
    assert "participates_in_fk_pk" in payload
    assert "supported_locales" in payload


def test_providers_inspect_unknown_exits_1():
    result = runner.invoke(app, ["providers", "inspect", "no_such_provider"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# checksums
# ---------------------------------------------------------------------------


def test_checksums_help():
    result = runner.invoke(app, ["checksums", "--help"])
    assert result.exit_code == 0


def test_checksums_list_exits_0():
    result = runner.invoke(app, ["checksums", "list"])
    assert result.exit_code == 0


def test_checksums_list_json_structure():
    result = runner.invoke(app, ["checksums", "list", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "checksums list"
    assert payload["status"] == "ok"
    assert isinstance(payload["schemes"], list)
    assert payload["count"] > 0


def test_checksums_list_help_includes_examples():
    result = runner.invoke(app, ["checksums", "list", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------


def test_validators_help():
    result = runner.invoke(app, ["validators", "--help"])
    assert result.exit_code == 0


def test_validators_list_exits_0():
    result = runner.invoke(app, ["validators", "list"])
    assert result.exit_code == 0


def test_validators_list_json_structure():
    result = runner.invoke(app, ["validators", "list", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "validators list"
    assert payload["status"] == "ok"
    assert isinstance(payload["validators"], list)
    assert payload["count"] > 0


def test_validators_list_help_includes_examples():
    result = runner.invoke(app, ["validators", "list", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


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
