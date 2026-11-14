"""Output-mode plumbing for the decoy CLI.

Every command takes `--json`, `--quiet`, `--verbose`, calls `setup_output()`,
and writes through the returned `OutputState`. See CLI_UX_GUIDE.md section 4.
"""

from __future__ import annotations

import json as _json
import re
import sys
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

import typer
from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.traceback import Trace, Traceback

from decoy._env_flags import no_color
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
    return Console(
        stderr=stderr,
        soft_wrap=stderr,
        theme=DECOY_THEME,
        no_color=no_color(),
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


JsonValue: TypeAlias = "None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]"

# The members every error object owns. `context` carries the per-command rest.
_FIXED_MEMBERS = frozenset({"command", "status", "error", "code", "hint"})
# Same rule as `docs/schemas/decoy-error-v1.schema.json`. `fullmatch`, not `$`, so a trailing
# newline cannot slip through.
_CODE_RULE = re.compile(r"[a-z][a-z0-9_.]*")
_HINT_STYLE = hint


def emit_error(
    state: OutputState,
    command: str,
    message: str,
    *,
    code: str | None = None,
    hint: str | None = None,
    context: Mapping[str, JsonValue] | None = None,
) -> None:
    """Report a failure in the active mode. The one place a command's error is built.

    `--json` writes one `decoy-error-v1` object to stdout. Every other mode, `--quiet`
    included, writes `error: <message>` and an optional `  hint: <hint>` to stderr:
    `--quiet` silences stdout, never a failure. `code` is the engine reason code or CLI
    warning code, kept out of `message` in JSON and shown as a `[code]` prefix in the human
    line. The caller builds `message` and `hint` without data values; this function only
    refuses a malformed call (a `ValueError` before anything is written).
    """
    if code is not None and _CODE_RULE.fullmatch(code) is None:
        raise ValueError("error code must match [a-z][a-z0-9_.]*")
    shadowed = _FIXED_MEMBERS.intersection(context or ())
    if shadowed:
        raise ValueError(f"context may not reuse the fixed members {sorted(shadowed)}")
    if state.mode is OutputMode.json:
        payload: dict[str, JsonValue] = {"command": command, "status": "error", "error": message}
        if code is not None:
            payload["code"] = code
        if hint is not None:
            payload["hint"] = hint
        payload.update(context or {})
        emit_json(state, payload)
        return
    # markup=False: the message is engine text, a user path or a bracketed code. Rich would
    # read `[vault]` as a style tag and drop it.
    prefix = f"[{code}] " if code is not None else ""
    state.err_console.print(error("error:"), f"{prefix}{message}", markup=False)
    if hint is not None:
        state.err_console.print(" ", _HINT_STYLE("hint:"), hint, markup=False)


def emit_json_document(state: OutputState, doc: object, *, indent: int | None) -> None:
    """Write one raw JSON document to stdout in default mode.

    This is the document a user pipes to a file (`decoy schema`, `decoy scan --output -`), not
    the `--json` envelope. In `--json` mode stdout belongs to the envelope and in `--quiet`
    mode to nothing, so a call there is a bug in the caller, not a case to ignore. The message
    names no part of the document.
    """
    if state.mode is not OutputMode.default:
        raise ValueError("emit_json_document writes only in default output mode.")
    sys.stdout.write(_json.dumps(doc, indent=indent) + "\n")
    sys.stdout.flush()
