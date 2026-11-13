"""Output shared by the `decoy project` commands: refusals and warnings, human and `--json`."""

from __future__ import annotations

from collections.abc import Iterable
from typing import NoReturn

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.io import LayoutWarning
from decoy.ui.output import OutputMode, OutputState, emit_json
from decoy.ui.theme import error, warn


def warning_records(warnings: Iterable[LayoutWarning]) -> list[dict[str, str]]:
    """The `--json` form of a warning: its registry code and fixed message."""
    return [{"code": w.code, "message": w.message} for w in warnings]


def print_warnings(state: OutputState, warnings: Iterable[LayoutWarning]) -> None:
    """Warnings on stderr for a human reader; `--json` carries them in the envelope instead."""
    if state.mode is OutputMode.default or state.verbose:
        for w in warnings:
            state.err_console.print(warn("warning:"), w.code, w.message, markup=False)


def refuse(
    state: OutputState,
    envelope: dict[str, object],
    message: str,
    *,
    code: str | None = None,
    exit_code: int = EXIT_USAGE,
) -> NoReturn:
    """Print one refusal in the command's own mode and exit.

    `envelope` is the command's own `{"command": "<literal>"}` member, so each command names
    itself where the `--json` command-name sentry can read it. `code` is a `layout.*` code.
    """
    if state.mode is OutputMode.json:
        body: dict[str, object] = {**envelope, "status": "error", "error": message}
        if code is not None:
            body["code"] = code
        emit_json(state, body)
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), message, markup=False)
    raise typer.Exit(code=exit_code)
