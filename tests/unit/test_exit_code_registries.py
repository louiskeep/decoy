"""One exit taxonomy: the CI registry, the docs and the `decoy run` map all follow it."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

from decoy.ci import contracts
from decoy.cli import exit_codes

ROOT = Path(__file__).resolve().parents[2]


def test_taxonomy() -> None:
    named = {getattr(exit_codes, n) for n in exit_codes.__all__ if n.startswith("EXIT_")}
    assert contracts.EXIT_CODES == frozenset(named)
    assert 6 in contracts.EXIT_CODES
    assert contracts.EXIT_PRECEDENCE == (5, 3, 1, 6, 4, 2, 0)
    doc = (ROOT / "docs" / "ci-contracts.md").read_text(encoding="utf-8")
    for code in named:
        assert f"| {code} | `EXIT_" in doc, code
    assert "**5 > 3 > 1 > 6 > 4 > 2 > 0**" in doc


def test_run_exit_map_total() -> None:
    from decoy_engine.run_result import derive_outcome  # noqa: F401
    from decoy_engine.run_result._model import FailureCategory, RunStatus

    reachable = {("succeeded", None), ("findings", None), ("partially_delivered", None)}
    reachable |= {("failed", c) for c in get_args(FailureCategory) if c != "cancelled"}
    reachable.add(("cancelled", "cancelled"))
    assert {s for s, _ in reachable} <= set(get_args(RunStatus))
    assert set(exit_codes.RUN_EXIT_MAP) == reachable
    assert dict(exit_codes.RUN_EXIT_MAP) == {
        ("succeeded", None): 0,
        ("findings", None): 4,
        ("partially_delivered", None): 6,
        ("failed", "usage"): 1,
        ("failed", "parameter"): 2,
        ("failed", "runtime"): 3,
        ("failed", "capacity"): 5,
        # Ctrl-C keeps the 128+SIGINT status Typer returns today.
        ("cancelled", "cancelled"): 130,
    }
    # 130 is a run-only status; it must not join the `decoy ci` taxonomy.
    assert 130 not in contracts.EXIT_CODES


def test_unknown_gate_exit_is_refused() -> None:
    import pytest

    from decoy.cli.gate import PreRunCheckError
    from decoy.cli.run._context import RunContext
    from decoy.cli.run._errors import fail

    exc = PreRunCheckError(
        "refused", exit_code=2, error_kind="validation", code=None, extra=None, messages=[]
    )
    # A gate exit with no category must stop the run, not fold into exit 1.
    with pytest.raises(RuntimeError, match="no category"):
        fail(object.__new__(RunContext), exc)
