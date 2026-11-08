"""Run policy beside the gate: turn a `GateResult` into what `decoy run` needs.

`check_before_run` is the one place `decoy run` consults the gate. It returns the validated
config dict or raises `PreRunCheckError`, which `run`'s single error handler maps to an exit
code and a `--json` envelope. Messages here are the gate's own (names and locations, never
data values); this module only caps their length for the run envelope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decoy.cli.exit_codes import EXIT_CAPACITY
from decoy.cli.gate._layers import (
    GateFinding,
    GateResult,
    GateRoute,
    gate_exit_code,
    run_gate_on_config,
)

# `decoy run` caps every error text it emits (CLI QA F8): an engine exception can quote
# source-row content verbatim, so the cap bounds what reaches a log aggregator.
ERROR_TEXT_CAP = 500

# The engine's two capacity-refusal codes: the out-of-core-FK memory gate raises
# `ExecutionError` with exactly one of them, and the preflight capacity check carries the same
# code on its finding. `out_of_core_insufficient_memory` is legacy-engine compat (a current
# engine's build-floor gate is advisory and never raises it).
CAPACITY_CODES = frozenset({"out_of_core_insufficient_memory", "out_of_core_fanin_exceeds_budget"})


def cap_error_text(text: str) -> str:
    """Cut `text` to `ERROR_TEXT_CAP` characters plus `...`."""
    return text[:ERROR_TEXT_CAP] + "..." if len(text) > ERROR_TEXT_CAP else text


class PreRunCheckError(Exception):
    """The gate refused the run. Carries the exit code and the members `--json` adds.

    Build it with `from_result`; raise it outside any `except` block so it has no cause
    or context to leak.
    """

    def __init__(
        self,
        summary: str,
        *,
        exit_code: int,
        error_kind: str,
        code: str | None,
        extra: str | None,
        messages: list[dict[str, Any]],
    ) -> None:
        super().__init__(summary)
        self.exit_code = exit_code
        self.error_kind = error_kind
        self.code = code
        self.extra = extra
        self.messages = messages

    @classmethod
    def from_findings(cls, findings: list[GateFinding]) -> PreRunCheckError:
        """A refusal from config-layer findings alone (a YAML syntax error saved at parse)."""
        return cls.from_result(GateResult(findings, frozenset({"config"}), False))

    @classmethod
    def from_result(cls, result: GateResult) -> PreRunCheckError:
        """The one run-envelope error builder for a refused `GateResult`."""
        errors = [f for f in result.findings if f.severity == "error"]
        exit_code = gate_exit_code(result, fail_on_warning=False)
        code: str | None = None
        extra: str | None = None
        error_kind = "validation"
        first = errors[0]
        if exit_code == EXIT_CAPACITY:
            error_kind = "capacity"
            capacity = next((f for f in errors if f.code in CAPACITY_CODES), None)
            if capacity is not None:
                code, first = capacity.code, capacity
        else:
            extra = next((f.extra for f in errors if f.extra is not None), None)
            if extra is not None:
                error_kind = "missing_extra"
        where = f" (at {first.location})" if first.location else ""
        summary = (
            f"{len(errors)} error(s) found before the run; first: "
            f"{cap_error_text(first.message)}{where}. "
            "Run `decoy validate CONFIG` for the full report."
        )
        return cls(
            summary,
            exit_code=exit_code,
            error_kind=error_kind,
            code=code,
            extra=extra,
            messages=[_message(f) for f in result.findings],
        )

    def json_members(self) -> dict[str, Any]:
        """The members a refusal adds to run's `--json` error envelope."""
        members: dict[str, Any] = {"error_kind": self.error_kind}
        if self.code is not None:
            members["code"] = self.code
        if self.extra is not None:
            members["extra"] = self.extra
        members["messages"] = self.messages
        return members


def _message(f: GateFinding) -> dict[str, Any]:
    """One `messages[]` entry: the shape `decoy validate --json` emits, message capped."""
    return {
        "layer": f.layer,
        "severity": f.severity,
        "code": f.code,
        "message": cap_error_text(f.message),
        "location": f.location,
    }


def check_before_run(raw: Any, config_path: Path, route: GateRoute, state: Any) -> dict[str, Any]:
    """Run the gate on the parsed YAML; return the validated config or raise.

    Warnings never stop a run. In human mode one stderr line gives their count and the
    command that lists them; `--quiet` and `--json` print nothing extra.
    """
    result = run_gate_on_config(raw, config_path, route)
    if gate_exit_code(result, fail_on_warning=False) != 0:
        raise PreRunCheckError.from_result(result)
    warnings = sum(1 for f in result.findings if f.severity == "warning")
    if warnings and _is_human(state):
        from decoy.ui.theme import warn

        state.err_console.print(
            warn("warning:"),
            f"{warnings} pre-run warning(s); run `decoy validate CONFIG` to list them.",
            markup=False,
        )
    if result.config is None:  # a passing gate always carries its config; kept under -O
        raise RuntimeError("pre-run gate passed without a parsed config")
    return result.config


def _is_human(state: Any) -> bool:
    from decoy.ui.output import OutputMode

    return state.mode is OutputMode.default
