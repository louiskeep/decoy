"""One value-free output boundary for the pre-scan / post-scan commands.

Everything these commands print (stdout, stderr, JSON, hints) is built here or
passed through here, so no call site decides on its own what is safe:

  * errors carry a stable code plus an exception *type name*, never a message,
    a traceback, a path, or a rejected option value;
  * a profile is projected to counts / types / rates / detector ids / column
    names -- column names are schema; top values, sentinels, samples, min/max
    and modes are data and never leave this boundary;
  * Click usage errors (bad enum, bad int, missing file) are rewritten to name
    only the declared parameter, because Click echoes the rejected value.

The one deliberate exception is the profile file written by
`pre-scan --output FILE`: an explicit, user-requested artifact on disk.
"""

from __future__ import annotations

from typing import Any, NoReturn

import typer
from typer.core import TyperGroup

try:  # typer >= 0.26 vendors Click
    from typer._click.exceptions import UsageError
except ImportError:  # pragma: no cover - older typer on stock Click
    from click.exceptions import UsageError

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, OutputState, emit_json
from decoy.ui.theme import error, hint

PII_CANDIDATE_THRESHOLD = 0.6

# Stable codes: a caller (or log scraper) can match on these without parsing prose.
CODE_USAGE = "usage_error"
CODE_INPUT_UNREADABLE = "input_unreadable"
CODE_SCAN_UNREADABLE = "scan_unreadable"
CODE_SCAN_FAILED = "scan_failed"
CODE_CHECK_FAILED = "check_failed"
CODE_CONFIG_INVALID = "config_invalid"


def exc_label(exc: BaseException) -> str:
    """The exception type name -- the only part of an exception that is safe."""
    return type(exc).__name__


def fail(
    state: OutputState,
    command: str,
    code: str,
    message: str,
    *,
    hint_text: str | None = None,
    exit_code: int = EXIT_USAGE,
) -> NoReturn:
    """Emit a value-free error (JSON envelope or stderr text) and exit.

    `message` must be a fixed string or contain only `exc_label()` output;
    never interpolate a path, option value or exception message into it.
    """
    if state.mode is OutputMode.json:
        emit_json(state, {"command": command, "status": "error", "code": code, "error": message})
    else:
        state.err_console.print(error("error:"), message)
        if hint_text and state.mode is not OutputMode.quiet:
            state.err_console.print(" ", hint("hint:"), hint_text)
    raise typer.Exit(code=exit_code)


def fail_runtime(state: OutputState, command: str, code: str, what: str, exc: BaseException) -> NoReturn:
    """Unexpected failure: type name + stable code, no traceback even with --verbose."""
    fail(
        state,
        command,
        code,
        f"{what}: {exc_label(exc)}",
        hint_text="no traceback is printed: diagnostics can carry row data.",
        exit_code=EXIT_RUNTIME,
    )


def safe_field(field: dict[str, Any]) -> dict[str, Any]:
    """Project one profiled field (live or saved) to value-free facts.

    Allowlist, not blocklist: a new engine key stays out until named here.
    """
    score = field.get("pii_score")
    detectors = field.get("detector_matches") or []
    ids = [
        str(m.get("detector_id") or m.get("detector") or m.get("name"))
        for m in detectors
        if isinstance(m, dict)
    ]
    null_rate = field.get("null_rate")
    return {
        "name": field.get("name"),
        "dtype": field.get("inferred_type") or field.get("dtype"),
        "null_rate": round(null_rate, 4) if isinstance(null_rate, (int, float)) else None,
        "distinct_count": field.get("distinct_count", field.get("unique_count")),
        "pii_score": round(score, 3) if isinstance(score, (int, float)) else None,
        "pii_candidate": isinstance(score, (int, float)) and score >= PII_CANDIDATE_THRESHOLD,
        "detector_hits": ids,
    }


def safe_profile(profile_dict: dict[str, Any]) -> dict[str, Any]:
    """Project a whole profile dict; omits source_label, which is a file name."""
    fields = [safe_field(f) for f in profile_dict.get("fields", [])]
    return {
        "row_count": profile_dict.get("row_count"),
        "field_count": len(fields),
        "sample_strategy": profile_dict.get("sample_strategy"),
        "pii_candidate_count": sum(1 for f in fields if f["pii_candidate"]),
        "reid_risk_score": profile_dict.get("reid_risk_score"),
        "quasi_identifier_groups": [list(g) for g in profile_dict.get("quasi_identifier_groups", [])],
        "fields": fields,
    }


def value_free_usage_errors(base: type[TyperGroup]) -> type[TyperGroup]:
    """Wrap a group so Click usage errors never echo the rejected value."""

    class _ValueFreeGroup(base):  # type: ignore[valid-type, misc]
        def invoke(self, ctx):  # type: ignore[override]
            try:
                return super().invoke(ctx)
            except UsageError as exc:
                param = getattr(exc, "param", None)
                name = getattr(param, "name", None)
                where = f" for '{name}'" if name else ""
                typer.echo(f"error: invalid usage{where} ({CODE_USAGE}).", err=True)
                typer.echo("  hint: run the command with --help.", err=True)
                ctx.exit(2)

    return _ValueFreeGroup
