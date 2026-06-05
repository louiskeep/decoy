"""Output-mode plumbing for the decoy CLI.

Every command takes `--json`, `--quiet`, `--verbose`, calls `setup_output()`,
and writes through the returned `OutputState`. See CLI_UX_GUIDE.md section 4.
"""

from __future__ import annotations

import json as _json
import os
import sys
import warnings
from dataclasses import dataclass
from enum import Enum

import typer
from rich.console import Console

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.theme import DECOY_THEME, error, hint


class OutputMode(str, Enum):
    default = "default"
    json = "json"
    quiet = "quiet"


@dataclass(frozen=True)
class OutputState:
    mode: OutputMode
    verbose: bool
    console: Console
    err_console: Console


def _make_console(*, stderr: bool) -> Console:
    no_color = os.environ.get("NO_COLOR") is not None
    return Console(
        stderr=stderr,
        theme=DECOY_THEME,
        no_color=no_color,
        highlight=False,
    )


def setup_output(json_: bool, quiet: bool, verbose: bool) -> OutputState:
    """Validate the flag combo and build the OutputState.

    Call at the top of every command. Conflicting flags exit 1 with the
    section-9 error shape.
    """
    err_console = _make_console(stderr=True)

    if quiet and verbose:
        err_console.print(error("error:"), "--verbose and --quiet are mutually exclusive.")
        err_console.print(" ", hint("hint:"), "pick one -- `-v` for debug logs, `-q` to silence stdout.")
        raise typer.Exit(code=EXIT_USAGE)

    if json_ and quiet:
        err_console.print(error("error:"), "--json and --quiet are mutually exclusive.")
        err_console.print(" ", hint("hint:"), "use `--json` for structured stdout, `--quiet` for none.")
        raise typer.Exit(code=EXIT_USAGE)

    if json_:
        mode = OutputMode.json
    elif quiet:
        mode = OutputMode.quiet
    else:
        mode = OutputMode.default

    # Quiet pandas/dateutil chatter unless the user opted into --verbose.
    # Engine warnings are useful for debugging but pollute the default card UX.
    if not verbose:
        warnings.filterwarnings("ignore", category=UserWarning)

    return OutputState(
        mode=mode,
        verbose=verbose,
        console=_make_console(stderr=False),
        err_console=err_console,
    )


def emit_json(state: OutputState, payload: dict) -> None:
    """Write a single JSON object to stdout when in --json mode.

    No-op in quiet mode. In default mode this is also a no-op - callers that
    want human output write through `state.console.print(...)` themselves.
    """
    if state.mode is OutputMode.json:
        sys.stdout.write(_json.dumps(payload) + "\n")
        sys.stdout.flush()
