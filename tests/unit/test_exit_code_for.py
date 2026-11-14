"""`exit_code_for`: the one exception-to-exit map, and its parity with the three older copies.

AT-CL3-7. Until CL4 the `decoy run` classifier (`cli/run/_errors.py`), `decoy demo`'s three-type
map and `decoy fit`'s differential-privacy arms still decide for themselves. This file runs the
same exception through each and through `exit_code_for`, so the owner cannot drift from them
before they are deleted. The categories come from the run classifier's own type list, so a type
added there without a matching rule here fails the parity test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import typer

from decoy import _native_gate
from decoy._config_file import ConfigFileError
from decoy.cli.exit_codes import (
    EXIT_CAPACITY,
    EXIT_RUNTIME,
    EXIT_USAGE,
    exit_code_for,
)
from decoy.cli.gate import PreRunCheckError, capacity_codes
from decoy.cli.run import _errors
from decoy.ui.output import setup_output


def _classifier_exit(exc: Exception) -> int:
    """The exit the `decoy run` error arm gives `exc`, through its real `fail`."""
    ctx = SimpleNamespace(
        state=setup_output(False, True, False),  # quiet: the arm prints one stderr line
        notify_channels=[],
        notify_on=SimpleNamespace(value="failure"),
        config_str="pipeline.yaml",
        yaml_mode="mask",
        rows=None,
        layout=None,
        _run_started_at=datetime.now(timezone.utc),
    )
    with pytest.raises(typer.Exit) as info:
        _errors.fail(ctx, exc)  # type: ignore[arg-type]
    return info.value.exit_code


def _bare(cls: type[BaseException]) -> BaseException:
    """An instance built without its constructor: only the type matters for the exit.

    The run classifier reads `.code` and `.message` for a few types, so a stand-in is set on each."""
    exc = cls.__new__(cls)
    for name in ("code", "message"):
        if not hasattr(exc, name):
            setattr(exc, name, "stand_in")
    return exc


def _pre_run(exit_code: int) -> PreRunCheckError:
    kind = "capacity" if exit_code == EXIT_CAPACITY else "validation"
    return PreRunCheckError(
        "refused", exit_code=exit_code, error_kind=kind, code=None, extra=None, messages=[]
    )


def _run_categories() -> dict[str, Any]:
    from decoy_engine import GenerationError
    from decoy_engine.errors import DecoyError
    from decoy_engine.execution import ExecutionError

    capacity = sorted(capacity_codes())[0]
    cases: dict[str, Any] = {
        "pre-run usage": _pre_run(EXIT_USAGE),
        "pre-run capacity": _pre_run(EXIT_CAPACITY),
        "execution capacity code": ExecutionError(code=capacity, message="x"),
        "engine capacity code": DecoyError.__new__(DecoyError),
        "memory error": MemoryError(),
        "uniqueness impossible": GenerationError(
            code=_errors.UNIQUENESS_IMPOSSIBLE_CODE, message="x"
        ),
        "other generation error": GenerationError(code="dtype_unsafe", message="x"),
        "native gate": _bare(_native_gate.NativeGateError),
        "runtime error": RuntimeError("boom"),
        "os error": OSError("disk"),
        "value error": ValueError("bad"),
    }
    cases["engine capacity code"].code = capacity
    for t in _errors._usage_types():
        cases[f"usage type {t.__name__}"] = _bare(t)
    return cases


@pytest.mark.parametrize("name", sorted(_run_categories()))
def test_every_run_category_matches_the_classifier(name: str) -> None:
    exc = _run_categories()[name]

    assert exit_code_for(exc) == _classifier_exit(exc)


def test_the_documented_exits() -> None:
    assert exit_code_for(ConfigFileError("yaml.empty", "x")) == EXIT_USAGE
    assert exit_code_for(MemoryError()) == EXIT_CAPACITY
    assert exit_code_for(OSError("read failed")) == EXIT_RUNTIME
    assert exit_code_for(RuntimeError("x")) == EXIT_RUNTIME


def test_an_engine_env_flag_error_is_a_usage_exit() -> None:
    # The class ships with the engine's env-flag slice; the pinned engine may predate it.
    errors = pytest.importorskip("decoy_engine.errors")
    cls = getattr(errors, "EnvFlagError", None)
    if cls is None:
        pytest.skip("the pinned engine has no EnvFlagError yet")

    assert exit_code_for(cls.__new__(cls)) == EXIT_USAGE


def test_the_demo_map_is_the_owner_map() -> None:
    from decoy_engine import ConfigError, PipelineValidationError
    from decoy_engine.plan import PlanCompileError

    for exc in (
        PlanCompileError("c", None, "m"),
        PipelineValidationError("m"),
        ConfigError("m"),
    ):
        assert exit_code_for(exc) == EXIT_USAGE
    assert exit_code_for(RuntimeError("m")) == EXIT_RUNTIME


@pytest.mark.parametrize(
    ("module", "name", "code", "expected"),
    [
        ("dp_provenance", "ProvenanceError", "dp_provenance_refused", EXIT_RUNTIME),
        ("dp_budget", "DpBudgetError", "dp_schedule_mismatch", EXIT_RUNTIME),
        ("dp_budget", "DpBudgetError", "dp_budget_exceeded", EXIT_USAGE),
        ("dp", "DpError", "dp_bad_request", EXIT_USAGE),
        ("carriers", "CarrierError", "carrier_bad", EXIT_USAGE),
    ],
)
def test_the_fit_dp_arms_are_the_owner_map(
    module: str, name: str, code: str, expected: int
) -> None:
    import importlib

    cls = getattr(importlib.import_module(f"decoy_engine.quality.{module}"), name)

    assert exit_code_for(cls(code=code, message="m")) == expected


def test_a_blocking_post_scan_is_findings_and_an_existing_vault_is_usage() -> None:
    """Every command agrees with `decoy run`'s repin cases (engine 0.24.0 behaviour)."""
    from decoy_engine import VaultError
    from decoy_engine.verification.postmask import PostScanBlockedError

    from decoy.cli.exit_codes import EXIT_FINDINGS

    assert exit_code_for(PostScanBlockedError({})) == EXIT_FINDINGS
    assert exit_code_for(VaultError(code="vault_exists", message="m")) == EXIT_USAGE
    assert exit_code_for(VaultError(code="vault_other", message="m")) == EXIT_RUNTIME
