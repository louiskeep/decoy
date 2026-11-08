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
from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.traceback import Trace, Traceback

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


# A traceback panel's border and padding around each frame header, with some slack.
_PANEL_FRAME = 8


def print_traceback(state: OutputState) -> None:
    """Print the active exception's traceback to stderr, wrapped by Rich.

    The stderr console soft-wraps, and a soft-wrapped traceback crops each frame header
    (`<path>:<line> in <func>`) at the panel edge. This is the one place a stderr print
    turns soft wrap off. Without soft wrap Rich folds a frame header that is wider than the
    panel, which splits `file.py:N in fn` under a long directory, so the panel is made wide
    enough for the widest header and the terminal wraps the line, as it does for the other
    stderr lines. Call it from an `except` block.
    """
    traceback = Traceback()
    if state.err_console.is_terminal:
        # A panel wider than the terminal makes it wrap every box row, borders included, so
        # on a TTY keep Rich's in-panel layout. Only logs and pipes need greppable headers.
        state.err_console.print(traceback, soft_wrap=False)
        return
    widest = _widest_frame_header(traceback.trace) + _PANEL_FRAME
    # Keep Rich's own cap (default 100) on wide consoles; only grow it for a long header.
    traceback.width = max(traceback.width or 0, widest)
    width = max(state.err_console.width, widest)
    state.err_console.print(_AtWidth(traceback, width), soft_wrap=False, crop=False)


class _AtWidth:
    """Render a renderable at a fixed width, wider than the console if need be.

    `Console.print(width=...)` only narrows (it clamps to the console width).
    """

    def __init__(self, renderable: RenderableType, width: int) -> None:
        self.renderable = renderable
        self.width = width

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield from console.render(self.renderable, options.update(width=self.width))


def _widest_frame_header(trace: Trace) -> int:
    """The longest `<path>:<line> in <func>` in `trace`, sub-exceptions of a group included."""
    widest = 0
    for stack in trace.stacks:
        for frame in stack.frames:
            widest = max(widest, cell_len(f"{frame.filename}:{frame.lineno} in {frame.name}"))
        syntax_error = stack.syntax_error
        if syntax_error is not None:  # printed as ` <filename>:<line>`
            widest = max(widest, cell_len(f" {syntax_error.filename}:{syntax_error.lineno}"))
        for group in getattr(stack, "exceptions", ()):  # exception groups (Rich 13.4+)
            widest = max(widest, _widest_frame_header(group) + _PANEL_FRAME)
    return widest


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
