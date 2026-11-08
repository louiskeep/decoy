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
from rich.traceback import Traceback

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
    """Build a Rich console. This is the only place the CLI constructs one.

    The stderr console soft-wraps: each print is one line and the terminal does the
    wrapping. Off a TTY Rich otherwise folds at 80 columns and puts a newline inside a long
    path, which breaks log greps. It is for lines only: no `Panel` or `Table` goes to it,
    because soft wrap would crop their cell text. Stdout keeps Rich's own layout.
    """
    no_color = os.environ.get("NO_COLOR") is not None
    return Console(
        stderr=stderr,
        soft_wrap=stderr,
        theme=DECOY_THEME,
        no_color=no_color,
        highlight=False,
    )


def print_traceback(state: OutputState) -> None:
    """Print the active exception's traceback to stderr, wrapped by Rich.

    The stderr console soft-wraps, and a soft-wrapped traceback crops each frame header
    (`<path>:<line> in <func>`) at the panel edge. This is the one place a stderr print
    turns soft wrap off. Call it from an `except` block.
    """
    state.err_console.print(Traceback(), soft_wrap=False)


def setup_output(json_: bool, quiet: bool, verbose: bool) -> OutputState:
    """Validate the flag combo and build the OutputState.

    Call at the top of every command. Conflicting flags exit 1 with the
    section-9 error shape.
    """
    err_console = _make_console(stderr=True)

    if quiet and verbose:
        err_console.print(error("error:"), "--verbose and --quiet are mutually exclusive.")
        err_console.print(
            " ", hint("hint:"), "pick one -- `-v` for debug logs, `-q` to silence stdout."
        )
        raise typer.Exit(code=EXIT_USAGE)

    if json_ and quiet:
        err_console.print(error("error:"), "--json and --quiet are mutually exclusive.")
        err_console.print(
            " ", hint("hint:"), "use `--json` for structured stdout, `--quiet` for none."
        )
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
