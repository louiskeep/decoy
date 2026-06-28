"""Unit tests for the SP-19 cockpit commands (anti-drift registry correspondence).

The key invariant for each list command: the CLI output must reflect the
REAL engine registry at runtime, not a hardcoded list. These tests import
the engine registries directly and assert that the CLI JSON output
contains exactly the same keys/names as the registry.

Anti-drift assertions:
- strategies list: output names == SCALAR_HANDLERS.keys()
- providers list: output names == registry.known_providers()
- checksums list: output schemes == _KNOWN_SCHEMES
- validators list: output validators == _REGISTRY.keys()

Known members from previous sprints are checked by name to guard against
accidental removal (geo_generalize from SP-08, npi from SP-04, no_orphan_children
from SP-05).
"""

from __future__ import annotations

import json as _json

from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# strategies list -- anti-drift
# ---------------------------------------------------------------------------


def test_strategies_list_json_matches_engine_registry():
    """CLI output names == SCALAR_HANDLERS keys (anti-drift)."""
    from decoy_engine.execution._strategies import SCALAR_HANDLERS

    result = runner.invoke(app, ["strategies", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    cli_names = {s["name"] for s in payload["strategies"]}
    engine_names = set(SCALAR_HANDLERS.keys())
    assert cli_names == engine_names, (
        f"CLI strategies do not match SCALAR_HANDLERS.\n"
        f"  CLI only: {cli_names - engine_names}\n"
        f"  Engine only: {engine_names - cli_names}"
    )
    assert payload["count"] == len(engine_names)


def test_strategies_list_contains_known_members():
    """geo_generalize (SP-08), fpe, faker, redact are in the registry."""
    result = runner.invoke(app, ["strategies", "list", "--json"])
    payload = _json.loads(result.stdout)
    cli_names = {s["name"] for s in payload["strategies"]}
    for expected in ("geo_generalize", "fpe", "faker", "redact", "passthrough"):
        assert expected in cli_names, f"expected {expected!r} in strategies list"


def test_strategies_list_count_matches_registry():
    """The count field in the JSON must equal the SCALAR_HANDLERS size."""
    from decoy_engine.execution._strategies import SCALAR_HANDLERS

    result = runner.invoke(app, ["strategies", "list", "--json"])
    payload = _json.loads(result.stdout)
    assert payload["count"] == len(SCALAR_HANDLERS)


# ---------------------------------------------------------------------------
# strategies inspect
# ---------------------------------------------------------------------------


def test_strategies_inspect_known_strategy_json():
    result = runner.invoke(app, ["strategies", "inspect", "fpe", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["name"] == "fpe"
    assert payload["class"]
    assert payload["module"]


def test_strategies_inspect_geo_generalize_json():
    result = runner.invoke(app, ["strategies", "inspect", "geo_generalize", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["name"] == "geo_generalize"


def test_strategies_inspect_unknown_exits_1():
    result = runner.invoke(app, ["strategies", "inspect", "no_such_strategy", "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "known" in payload


# ---------------------------------------------------------------------------
# providers list -- anti-drift
# ---------------------------------------------------------------------------


def test_providers_list_json_matches_engine_registry():
    """CLI provider names == registry.known_providers() (anti-drift)."""
    from decoy_engine.providers_v2 import get_default_registry

    registry = get_default_registry()
    engine_names = registry.known_providers()

    result = runner.invoke(app, ["providers", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    cli_names = {p["name"] for p in payload["providers"]}
    assert cli_names == engine_names, (
        f"CLI providers do not match engine registry.\n"
        f"  CLI only: {cli_names - engine_names}\n"
        f"  Engine only: {engine_names - cli_names}"
    )
    assert payload["count"] == len(engine_names)


def test_providers_list_contains_known_members():
    """person_name, synthetic_ssn, uuid are in the provider registry."""
    result = runner.invoke(app, ["providers", "list", "--json"])
    payload = _json.loads(result.stdout)
    cli_names = {p["name"] for p in payload["providers"]}
    for expected in ("person_name", "synthetic_ssn", "uuid"):
        assert expected in cli_names, f"expected {expected!r} in providers list"


def test_providers_list_count_matches_registry():
    """The count field must equal the registry's known_providers count."""
    from decoy_engine.providers_v2 import get_default_registry

    registry = get_default_registry()
    result = runner.invoke(app, ["providers", "list", "--json"])
    payload = _json.loads(result.stdout)
    assert payload["count"] == len(registry.known_providers())


# ---------------------------------------------------------------------------
# providers inspect
# ---------------------------------------------------------------------------


def test_providers_inspect_known_provider_json():
    result = runner.invoke(app, ["providers", "inspect", "person_name", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["name"] == "person_name"
    assert "backend_type" in payload
    assert "poolable" in payload
    assert "supports_deterministic" in payload


def test_providers_inspect_unknown_exits_1():
    result = runner.invoke(app, ["providers", "inspect", "no_such_provider", "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "known" in payload


# ---------------------------------------------------------------------------
# checksums list -- anti-drift
# ---------------------------------------------------------------------------


def test_checksums_list_json_matches_engine_registry():
    """CLI schemes == _KNOWN_SCHEMES (anti-drift)."""
    from decoy_engine.checksums import _KNOWN_SCHEMES

    result = runner.invoke(app, ["checksums", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    cli_schemes = set(payload["schemes"])
    assert cli_schemes == set(_KNOWN_SCHEMES), (
        f"CLI checksums do not match _KNOWN_SCHEMES.\n"
        f"  CLI only: {cli_schemes - set(_KNOWN_SCHEMES)}\n"
        f"  Engine only: {set(_KNOWN_SCHEMES) - cli_schemes}"
    )
    assert payload["count"] == len(_KNOWN_SCHEMES)


def test_checksums_list_contains_npi_and_vin():
    """npi (SP-04) and vin are in the checksum registry."""
    result = runner.invoke(app, ["checksums", "list", "--json"])
    payload = _json.loads(result.stdout)
    cli_schemes = set(payload["schemes"])
    assert "npi" in cli_schemes, "npi must be in checksums list (SP-04)"
    assert "vin" in cli_schemes, "vin must be in checksums list"
    assert "luhn" in cli_schemes, "luhn must be in checksums list"


# ---------------------------------------------------------------------------
# validators list -- anti-drift
# ---------------------------------------------------------------------------


def test_validators_list_json_matches_engine_registry():
    """CLI validator names == _REGISTRY.keys() (anti-drift)."""
    from decoy_engine.validators._registry import _REGISTRY

    result = runner.invoke(app, ["validators", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    cli_names = set(payload["validators"])
    engine_names = set(_REGISTRY.keys())
    assert cli_names == engine_names, (
        f"CLI validators do not match _REGISTRY.\n"
        f"  CLI only: {cli_names - engine_names}\n"
        f"  Engine only: {engine_names - cli_names}"
    )
    assert payload["count"] == len(engine_names)


def test_validators_list_contains_known_members():
    """no_orphan_children (SP-05), fk_intact, and luhn are in the validator registry."""
    result = runner.invoke(app, ["validators", "list", "--json"])
    payload = _json.loads(result.stdout)
    cli_names = set(payload["validators"])
    assert "no_orphan_children" in cli_names, (
        "no_orphan_children must be in validators list (SP-05)"
    )
    assert "fk_intact" in cli_names, "fk_intact must be in validators list"
    assert "luhn" in cli_names, "luhn must be in validators list"


# ---------------------------------------------------------------------------
# doctor -- healthy env
# ---------------------------------------------------------------------------


def test_doctor_exits_0_in_healthy_env():
    """In a complete dev environment, doctor exits 0."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, f"doctor failed:\n{result.stdout}"


def test_doctor_json_healthy_env():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["command"] == "doctor"
    assert payload["hard_failed"] == []
    check_names = {c["name"] for c in payload["checks"]}
    assert "python" in check_names
    assert "decoy_engine" in check_names


def test_doctor_json_decoy_engine_check_passes():
    """The decoy_engine hard check must pass in the test environment."""
    result = runner.invoke(app, ["doctor", "--json"])
    payload = _json.loads(result.stdout)
    engine_check = next(c for c in payload["checks"] if c["name"] == "decoy_engine")
    assert engine_check["status"] == "pass"
    assert engine_check["kind"] == "hard"


def test_doctor_json_python_version_is_present():
    result = runner.invoke(app, ["doctor", "--json"])
    payload = _json.loads(result.stdout)
    py_check = next(c for c in payload["checks"] if c["name"] == "python")
    assert py_check["status"] == "pass"
    assert "." in py_check["note"]


def test_doctor_quiet_exits_0():
    result = runner.invoke(app, ["doctor", "--quiet"])
    assert result.exit_code == 0


def test_doctor_hard_req_missing_exits_nonzero(monkeypatch):
    """doctor MUST fail loudly (non-zero exit) when a hard requirement is absent.

    This is doctor's load-bearing honesty guarantee. We point _HARD_REQS at a
    package that genuinely cannot import (real failure, not a mocked one) and
    assert the non-zero exit + fail status across all three output modes.
    """
    from decoy.cli import cockpit

    monkeypatch.setattr(cockpit, "_HARD_REQS", ["decoy_engine_definitely_missing_xyz"])

    # default (human) mode
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == cockpit.EXIT_RUNTIME

    # --json mode: fail status + the missing pkg surfaced in hard_failed
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == cockpit.EXIT_RUNTIME
    payload = _json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert "decoy_engine_definitely_missing_xyz" in payload["hard_failed"]

    # --quiet mode
    result = runner.invoke(app, ["doctor", "--quiet"])
    assert result.exit_code == cockpit.EXIT_RUNTIME


# ---------------------------------------------------------------------------
# Output modes (list commands)
# ---------------------------------------------------------------------------


def test_strategies_list_human_output():
    result = runner.invoke(app, ["strategies", "list"])
    assert result.exit_code == 0
    assert "fpe" in result.stdout
    assert "geo_generalize" in result.stdout


def test_strategies_list_quiet():
    result = runner.invoke(app, ["strategies", "list", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_providers_list_human_output():
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    assert "person_name" in result.stdout


def test_checksums_list_human_output():
    result = runner.invoke(app, ["checksums", "list"])
    assert result.exit_code == 0
    assert "luhn" in result.stdout
    assert "npi" in result.stdout


def test_validators_list_human_output():
    result = runner.invoke(app, ["validators", "list"])
    assert result.exit_code == 0
    assert "luhn" in result.stdout
    assert "fk_intact" in result.stdout
