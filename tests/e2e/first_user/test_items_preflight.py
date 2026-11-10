"""Preflight and gate output for a first-time user's relationship mistake.

A parent and child that share `patient_id` with no namespace made the capacity
estimator compile the plan, and the engine's `namespace_missing` escaped as a
traceback. The capacity row now records a FAIL under its own check name. In the aggregate gate the
compile layer reports the same error, so the capacity row becomes a not-checked warning.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.gate._layers import GateRoute, run_gate_on_config

runner = CliRunner()

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qa_first_user"
_CHECK = "capacity.plan_uncompilable"


def _stage(tmp_path: Path, name: str) -> Path:
    """Copy the QA pair and one pipeline into tmp_path; the YAML paths are relative."""
    for fixture in ("patients.csv", "visits.csv", name):
        shutil.copy(_FIXTURES / fixture, tmp_path / fixture)
    return tmp_path / name


def _no_traceback(result: Result) -> None:
    # CliRunner captures exceptions instead of printing them, so check the captured one.
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output


def test_preflight_reports_the_uncompilable_plan_as_a_capacity_fail(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = runner.invoke(app, ["validate", "preflight", str(config), "--json"])
    _no_traceback(result)
    assert result.exit_code == EXIT_USAGE
    checks = {c["name"]: c for c in json.loads(result.stdout)["checks"]}
    assert checks[_CHECK]["status"] == "fail"
    assert checks[_CHECK]["code"] == "namespace_missing"
    assert checks[_CHECK]["location"].startswith("relationships[")
    assert "how namespaces are resolved" in checks[_CHECK]["message"]


def test_preflight_fail_names_no_data_value(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = runner.invoke(app, ["validate", "preflight", str(config)])
    _no_traceback(result)
    assert "Ada Example" not in result.output
    assert "000-00-0001" not in result.output


def test_aggregate_validate_reports_the_namespace_error_once(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = runner.invoke(app, ["validate", str(config), "--json"])
    _no_traceback(result)
    assert result.exit_code == EXIT_USAGE
    messages = json.loads(result.stdout)["messages"]
    hits = [m for m in messages if m["code"] == "namespace_missing"]
    assert [(m["layer"], m["severity"]) for m in hits] == [("compile", "error")]
    capacity = [m for m in messages if m["code"] == _CHECK]
    assert [(m["layer"], m["severity"]) for m in capacity] == [("preflight", "warning")]
    assert "not checked" in capacity[0]["message"]


def test_the_preflight_layer_does_not_claim_it_passed(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = runner.invoke(app, ["validate", str(config)])
    _no_traceback(result)
    assert result.exit_code == EXIT_USAGE
    assert "Preflight: passed" not in result.output
    assert "not checked" in result.output


@pytest.mark.parametrize("route", [GateRoute.PLAIN, GateRoute.CHUNKED])
def test_the_gate_reports_the_error_once_on_every_route(tmp_path: Path, route: GateRoute) -> None:
    import yaml

    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    raw = yaml.safe_load(config.read_text())
    result = run_gate_on_config(raw, config, route)
    hits = [f for f in result.findings if f.code == "namespace_missing"]
    assert [(f.layer, f.severity) for f in hits] == [("compile", "error")]
    capacity = [f for f in result.findings if f.code == _CHECK]
    assert [(f.layer, f.severity) for f in capacity] == [("preflight", "warning")]


@pytest.mark.parametrize("route", [GateRoute.PLAIN, GateRoute.CHUNKED])
def test_preflight_alone_keeps_the_fail_on_every_route(tmp_path: Path, route: GateRoute) -> None:
    import yaml

    from decoy.cli.gate._layers import _run_preflight_layer

    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    findings, _ = _run_preflight_layer(yaml.safe_load(config.read_text()), config, route)
    hits = [f for f in findings if f.code == "namespace_missing"]
    assert [(f.layer, f.severity) for f in hits] == [("preflight", "error")]


def test_a_capacity_compile_error_the_compile_layer_missed_stays_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml
    from decoy_engine import execution as engine_execution
    from decoy_engine.plan import PlanCompileError

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise PlanCompileError("orphan_fk_policy_missing", "tables.visits", "SECRET-MSG-7c1d")

    monkeypatch.setattr(engine_execution, "estimate_job_capacity", _raise)
    config = _stage(tmp_path, "pipeline_namespaced.yaml")
    result = run_gate_on_config(yaml.safe_load(config.read_text()), config)
    assert not [f for f in result.findings if f.layer == "compile" and f.severity == "error"]
    hits = [f for f in result.findings if f.code == "orphan_fk_policy_missing"]
    assert [(f.layer, f.severity) for f in hits] == [("preflight", "error")]


def test_a_same_code_capacity_error_at_another_path_stays_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml
    from decoy_engine import execution as engine_execution
    from decoy_engine.plan import PlanCompileError

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise PlanCompileError("namespace_missing", "relationships[9]", "SECRET-MSG-4e2a")

    monkeypatch.setattr(engine_execution, "estimate_job_capacity", _raise)
    config = _stage(tmp_path, "pipeline_no_namespace.yaml")
    result = run_gate_on_config(yaml.safe_load(config.read_text()), config)
    hits = [f for f in result.findings if f.code == "namespace_missing"]
    assert sorted((f.layer, f.severity) for f in hits) == [
        ("compile", "error"),
        ("preflight", "error"),
    ]
    assert [f.location for f in hits if f.layer == "preflight"] == ["relationships[9]"]


def test_a_namespaced_pipeline_still_passes_preflight(tmp_path: Path) -> None:
    config = _stage(tmp_path, "pipeline_namespaced.yaml")
    result = runner.invoke(app, ["validate", "preflight", str(config), "--json"])
    _no_traceback(result)
    assert result.exit_code == EXIT_OK
    names = {c["name"]: c["status"] for c in json.loads(result.stdout)["checks"]}
    assert names.get(_CHECK) is None


def test_non_namespace_compile_error_gets_the_generic_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy_engine import execution as engine_execution
    from decoy_engine.plan import PlanCompileError

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise PlanCompileError("orphan_fk_policy_missing", "tables.visits", "SECRET-MSG-7c1d")

    monkeypatch.setattr(engine_execution, "estimate_job_capacity", _raise)
    config = _stage(tmp_path, "pipeline_namespaced.yaml")
    result = runner.invoke(app, ["validate", "preflight", str(config), "--json"])
    _no_traceback(result)
    assert result.exit_code == EXIT_USAGE
    row = {c["name"]: c for c in json.loads(result.stdout)["checks"]}[_CHECK]
    assert row["code"] == "orphan_fk_policy_missing"
    assert "decoy validate compile" in row["message"]
    assert "namespaces" not in row["message"]
    assert "SECRET-MSG-7c1d" not in result.output
