"""The one process boundary for `decoy pre-scan` and `decoy post-scan`.

The boundary is ambient, not opt-in. `value_free_group` is the Click group class
of both sub-apps; its `make_context` and `invoke` enter `_bounded` BEFORE any
parsing, parameter conversion, lazy import, config validation or command
callback runs, so command code cannot execute outside it (`surface()` raises if
called without an active boundary). Inside it:

  * `sys.stdout` / `sys.stderr` are swapped for a discarding sink. The real
    streams are captured first and held only by the `Surface` (private), so a
    stray `print`, `warnings.showwarning`, logging handler or rich Live redirect
    has nowhere to write.
  * every log record is contained: `logging.disable(sys.maxsize)` (CRITICAL is
    only 50; custom levels above it still fire) plus a `NullHandler` swap on the
    root and every named logger, ref-counted so overlapping entries restore the
    process state exactly once.
  * warnings are recorded, never shown, inside `warnings.catch_warnings`, which
    restores `warnings.filters`; `--verbose` prints only their count and
    allowlisted category names.
  * every `BaseException` (including `SystemExit("text")` and
    `KeyboardInterrupt`) is trapped and becomes a closed reason; only an integer
    exit code ever leaves.

What reaches a surface is decided by `decoy.cli._value_free`: minted
`Projection`s, closed reasons and notices, and `Printer` fragments built from
literal templates and `SafeStr`/number arguments.

The one deliberate raw artifact is the saved scan written by
`pre-scan --output FILE`: the explicit, user-requested full profile (sample top
values and sentinels included). It is written owner-only (0600) with the source
label replaced, and the sentry pins `write_saved_scan` to that one call site.

Residual (outside Python stream mediation): native code writing directly to file
descriptors 1/2, or to `sys.__stdout__`/`sys.__stderr__`.

Pattern: object-capability confinement (Miller, "Robust Composition", 2006) --
authority to write exists only as references the boundary holds -- applied to
the process streams the way `contextlib.redirect_stdout` and
`warnings.catch_warnings` scope ambient state.
"""

from __future__ import annotations

import contextlib
import contextvars
import io
import json as _json
import logging
import os
import sys
import threading
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, TextIO, TypeVar

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer.core import TyperCommand, TyperGroup

try:  # typer >= 0.26 vendors Click
    from typer._click import exceptions as _cx
except ImportError:  # pragma: no cover - older typer on stock Click
    from click import exceptions as _cx  # type: ignore[no-redef]

from decoy.cli import _value_free as vf
from decoy.cli._value_free import REASONS, Location, Projection, SafeStr, StageId
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, OutputState
from decoy.ui.scan_progress import scan_stages
from decoy.ui.table import make_table
from decoy.ui.theme import DECOY_THEME, TOKEN_STYLES

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Ambient process containment.
# ---------------------------------------------------------------------------


class _Sink(io.TextIOBase):
    """A text stream that accepts and discards everything."""

    encoding = "utf-8"

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        return len(s)

    def isatty(self) -> bool:
        return False


class _Containment:
    """Process-global saved state. Only the first entry swaps it in and only the last
    restores it, so overlapping (non-LIFO) entries from threads cannot clobber each
    other's restoration of streams, warning filters or the logging threshold."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.depth = 0
        self.disable = logging.NOTSET
        self.handlers: list[tuple[logging.Logger, list[logging.Handler]]] = []
        self.out: TextIO = sys.stdout
        self.err: TextIO = sys.stderr
        self.warn_cm: warnings.catch_warnings | None = None
        self.caught: list[warnings.WarningMessage] = []

    def enter(self) -> None:
        self.disable = logging.root.manager.disable
        loggers = [logging.root] + [
            lg
            for lg in list(logging.root.manager.loggerDict.values())
            if isinstance(lg, logging.Logger)
        ]
        self.handlers = [(lg, list(lg.handlers)) for lg in loggers]
        for lg in loggers:
            lg.handlers = [logging.NullHandler()]
        # CRITICAL is 50; custom levels above it are only blocked by a larger threshold.
        logging.disable(sys.maxsize)
        self.out, self.err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = _Sink(), _Sink()
        self.warn_cm = warnings.catch_warnings(record=True)
        caught = self.warn_cm.__enter__()
        assert caught is not None  # record=True always yields the recording list
        self.caught = caught
        warnings.simplefilter("always")

    def exit(self) -> None:
        if self.warn_cm is not None:
            self.warn_cm.__exit__(None, None, None)
        self.warn_cm = None
        sys.stdout, sys.stderr = self.out, self.err
        for lg, handlers in self.handlers:
            lg.handlers = handlers
        self.handlers = []
        logging.disable(self.disable)


_CONTAINMENT = _Containment()


class _Entry:
    def __init__(self, out: TextIO, err: TextIO, start: int) -> None:
        self.out, self.err, self._start = out, err, start

    def warnings(self) -> list[warnings.WarningMessage]:
        with _CONTAINMENT.lock:
            return list(_CONTAINMENT.caught[self._start :])


@contextlib.contextmanager
def _contain_process() -> Iterator[_Entry]:
    c = _CONTAINMENT
    with c.lock:
        if c.depth == 0:
            c.enter()
        c.depth += 1
        entry = _Entry(c.out, c.err, len(c.caught))
    try:
        yield entry
    finally:
        with c.lock:
            c.depth -= 1
            if c.depth == 0:
                c.exit()


_ACTIVE: contextvars.ContextVar[Surface | None] = contextvars.ContextVar(
    "decoy_value_free_surface", default=None
)


def _sniff(args: Sequence[str]) -> tuple[bool, bool, bool]:
    """Output flags from raw argv, used only until the command's parsed flags arrive."""
    tokens = list(args)
    if "--" in tokens:
        tokens = tokens[: tokens.index("--")]
    return (
        "--json" in tokens,
        "--quiet" in tokens or "-q" in tokens,
        "--verbose" in tokens or "-v" in tokens,
    )


def _bounded(label: str, flags: tuple[bool, bool, bool], fn: Callable[[], T]) -> T:
    if _ACTIVE.get() is not None:
        return fn()
    code = EXIT_RUNTIME
    with _contain_process() as entry:
        surface = Surface(label, entry.out, entry.err, *flags)
        token = _ACTIVE.set(surface)
        try:
            try:
                return fn()
            except BaseException as exc:
                code = surface._trap(exc)
            finally:
                surface._flush_warnings(entry.warnings())
        finally:
            _ACTIVE.reset(token)
    raise _cx.Exit(code)


@contextlib.contextmanager
def _help_passthrough() -> Iterator[None]:
    """`--help` text is static, code-defined; it alone may use the real stdout."""
    surface = _ACTIVE.get()
    if surface is None:
        yield
        return
    with contextlib.redirect_stdout(surface._out):
        yield


_FLAGS_KEY = "decoy.value_free.flags"


def value_free_group(base: type[TyperGroup], label: str) -> type[TyperGroup]:
    """The group class for a value-free sub-app: parsing and invocation run bounded."""
    if label not in vf.COMMANDS:
        raise ValueError("unknown value-free command label")

    class ValueFreeGroup(base):  # type: ignore[valid-type, misc]
        def make_context(
            self, info_name: str | None, args: list[str], parent: Any = None, **extra: Any
        ) -> Any:
            flags = _sniff(args)
            ctx = _bounded(
                label,
                flags,
                lambda: super(ValueFreeGroup, self).make_context(info_name, args, parent, **extra),
            )
            ctx.meta[_FLAGS_KEY] = flags
            return ctx

        def invoke(self, ctx: Any) -> Any:
            flags = ctx.meta.get(_FLAGS_KEY, (False, False, False))
            return _bounded(label, flags, lambda: super(ValueFreeGroup, self).invoke(ctx))

        def get_help(self, ctx: Any) -> str:
            with _help_passthrough():
                return super().get_help(ctx)

    return ValueFreeGroup


class ValueFreeCommand(TyperCommand):
    """A leaf command that refuses to run outside a value-free boundary."""

    def invoke(self, ctx: Any) -> Any:
        if _ACTIVE.get() is None:
            raise RuntimeError("value-free command invoked outside its boundary")
        return super().invoke(ctx)

    def get_help(self, ctx: Any) -> str:
        with _help_passthrough():
            return super().get_help(ctx)


def surface(command: str, *, json_: bool, quiet: bool, verbose: bool) -> Surface:
    """The active Surface, configured with the command's parsed output flags."""
    active = _ACTIVE.get()
    if active is None:
        raise RuntimeError("command executed outside the value-free boundary")
    active._configure(command, json_, quiet, verbose)
    return active


# ---------------------------------------------------------------------------
# Printer: literal templates + SafeStr/number arguments, nothing else.
# ---------------------------------------------------------------------------

_FRAGMENT = object()
_STYLES = frozenset(TOKEN_STYLES)
_CARD_GLYPHS = {"ok": ("v", "success"), "warn": ("!", "warn"), "error": ("x", "error")}


class Fragment:
    """Styled text a Printer built; opaque to renderers."""

    __slots__ = ("_text",)

    def __init__(self, text: Text, token: object) -> None:
        if token is not _FRAGMENT:
            raise TypeError("Fragments are built by a Printer only")
        self._text = text


Part = Fragment | SafeStr | int | float | bool | None


def _literal(value: Any) -> str:
    # The sentry proves these positions are source literals; at runtime a SafeStr
    # or any data-derived subclass is refused so data cannot pose as a template.
    if type(value) is not str:
        raise TypeError("template, header and label positions take a source literal")
    return value


def _part(value: Any) -> Text:
    if isinstance(value, Fragment):
        return value._text.copy()
    if type(value) is SafeStr:
        return Text(str(value))
    if value is None or type(value) in (bool, int):
        return Text(str(value))
    if type(value) is float:
        return Text(str(value))
    raise TypeError("a Printer accepts only Fragments, SafeStr and numbers")


def _styled(value: Any, style: str) -> Text:
    text = _part(value)
    text.stylize(style)
    return text


def _title(value: Any) -> str | Text:
    return value._text.copy() if isinstance(value, Fragment) else _literal(value)


def _scalar(value: Any) -> Any:
    if type(value) is SafeStr or value is None or type(value) in (bool, int, float):
        return value
    raise TypeError("template arguments must be SafeStr or numbers")


class Printer:
    """What a renderer may do. Constructed by the Surface only."""

    def __init__(self, state: OutputState, token: object) -> None:
        if token is not _FRAGMENT:
            raise TypeError("Printers are built by the Surface only")
        self.__state = state

    def t(self, template: str, *args: Any, style: str | None = None) -> Fragment:
        if style is not None and style not in _STYLES:
            raise ValueError("unknown style")
        text = _literal(template).format(*(_scalar(a) for a in args))
        return Fragment(Text(text, style=style or ""), _FRAGMENT)

    def cat(self, *parts: Part) -> Fragment:
        return Fragment(Text.assemble(*(_part(p) for p in parts)), _FRAGMENT)

    def join(self, sep: str, parts: Iterable[Part]) -> Fragment:
        return Fragment(Text(_literal(sep)).join(_part(p) for p in parts), _FRAGMENT)

    def line(self, *parts: Part) -> None:
        self.__state.console.print(*(_part(p) for p in parts))

    def table(
        self, *headers: str, rows: Iterable[Sequence[Part]], title: str | Fragment | None = None
    ) -> None:
        tbl = make_table(*(_literal(h) for h in headers))
        if title is not None:
            tbl.title = _title(title)
        for row in rows:
            tbl.add_row(*(_part(c) for c in row))
        self.__state.console.print(tbl)

    def card(
        self, command: str, facts: Iterable[tuple[Part, Part]], next_hint: Part, status: str
    ) -> None:
        glyph, token = _CARD_GLYPHS[_literal(status)]
        title = Text.assemble((glyph, token), " ", (_literal(command), "accent"))
        body = Table.grid(padding=(0, 2))
        body.add_column(style="info", no_wrap=True)
        body.add_column(style="info")
        for label, value in facts:
            body.add_row(_part(label), _styled(value, "code"))
        if next_hint is not None:
            body.add_row("", "")
            body.add_row(Text("Next:", style="hint"), _styled(next_hint, "code"))
        self.__state.console.print(
            Panel(body, title=title, title_align="left", border_style="accent")
        )


Render = Callable[[Printer, Mapping[str, Any]], None]


# ---------------------------------------------------------------------------
# The Surface: the only holder of the real streams.
# ---------------------------------------------------------------------------


class _Progress:
    def __init__(self, handle: Any) -> None:
        self.__handle = handle

    def complete(self) -> None:
        self.__handle.complete()


class Surface:
    def __init__(
        self, label: str, out: TextIO, err: TextIO, json_: bool, quiet: bool, verbose: bool
    ) -> None:
        self._out = out
        self._err = err
        self._command = label
        self._json, self._quiet, self._verbose = json_, quiet and not json_, verbose and not quiet
        self._state = self._build_state()

    def _build_state(self) -> OutputState:
        no_color = os.environ.get("NO_COLOR") is not None

        def console(file: TextIO) -> Console:
            return Console(file=file, theme=DECOY_THEME, no_color=no_color, highlight=False)

        mode = (
            OutputMode.json
            if self._json
            else OutputMode.quiet
            if self._quiet
            else OutputMode.default
        )
        return OutputState(
            mode=mode,
            verbose=self._verbose,
            console=console(self._out),
            err_console=console(self._err),
        )

    def _configure(self, command: str, json_: bool, quiet: bool, verbose: bool) -> None:
        if command not in vf.COMMANDS:
            raise ValueError("unknown value-free command label")
        self._command = command
        self._json, self._quiet, self._verbose = json_, quiet, verbose
        conflict = (
            "verbose_and_quiet"
            if quiet and verbose
            else "json_and_quiet"
            if json_ and quiet
            else None
        )
        if conflict is not None:
            self._json, self._quiet, self._verbose = False, False, False
            self._state = self._build_state()
            self.fail(conflict)
        self._state = self._build_state()

    @property
    def mode(self) -> str:
        return self._state.mode.value

    # ---- errors -----------------------------------------------------------

    def _report(
        self,
        reason: str,
        *,
        exc: BaseException | None = None,
        location: Location | None = None,
        suggestion: SafeStr | None = None,
    ) -> int:
        r = REASONS[reason]
        hint_text = f"did you mean {suggestion}?" if type(suggestion) is SafeStr else r.hint
        if self._state.mode is OutputMode.json:
            payload: dict[str, Any] = {
                "command": self._command,
                "status": "error",
                "code": r.code,
                "reason": reason,
                "error": r.message,
            }
            if location is not None:
                payload["location"] = location.as_json()
            if exc is not None:
                payload["error_type"] = str(vf.exc_label(exc))
            self._emit(payload)
        else:
            detail = [r.message]
            if location is not None:
                detail.append(f"({location.text()})")
            if exc is not None:
                detail.append(f"[{vf.exc_label(exc)}]")
            err = self._state.err_console
            err.print(Text("error:", style="error"), Text(" ".join(detail)))
            if hint_text and self._state.mode is not OutputMode.quiet:
                err.print(" ", Text("hint:", style="hint"), Text(hint_text))
        return r.exit_code

    def fail(
        self,
        reason: str,
        *,
        exc: BaseException | None = None,
        location: Location | None = None,
        suggestion: SafeStr | None = None,
    ) -> NoReturn:
        """Emit a closed-reason error and exit. `suggestion` must be a minted SafeStr."""
        raise _cx.Exit(self._report(reason, exc=exc, location=location, suggestion=suggestion))

    def _usage(self, exc: BaseException) -> int:
        name = getattr(getattr(exc, "param", None), "name", None)
        param = name if type(name) is str and name.isidentifier() and len(name) <= 64 else None
        if self._state.mode is OutputMode.json:
            payload: dict[str, Any] = {
                "command": self._command,
                "status": "error",
                "code": "usage_error",
                "reason": "usage_error",
                "error": "invalid usage.",
            }
            if param is not None:
                payload["param"] = param
            self._emit(payload)
        else:
            where = f" for '{param}'" if param else ""
            self._err.write(f"error: invalid usage{where} (usage_error).\n")
            self._err.write("  hint: run the command with --help.\n")
            self._err.flush()
        return EXIT_USAGE if not isinstance(getattr(exc, "exit_code", None), int) else exc.exit_code  # type: ignore[attr-defined]

    def _trap(self, exc: BaseException) -> int:
        """Map any escaped BaseException to an exit code; only closed text is emitted."""
        try:
            if isinstance(exc, BrokenPipeError) or isinstance(exc.__context__, BrokenPipeError):
                return 1  # the reader went away; there is no one left to tell
            if isinstance(exc, _cx.Exit):
                code = exc.exit_code
                return code if type(code) is int else EXIT_RUNTIME
            if isinstance(exc, _cx.NoArgsIsHelpError):
                return exc.exit_code  # help already went out through `get_help`
            if isinstance(exc, _cx.Abort):
                return 1
            if isinstance(exc, _cx.UsageError):
                return self._usage(exc)
            if isinstance(exc, SystemExit):
                if exc.code is None:
                    return 0
                if type(exc.code) is int:
                    return exc.code
                return self._report("unexpected", exc=exc)
            if isinstance(exc, KeyboardInterrupt):
                return self._report("interrupted")
            return self._report("unexpected", exc=exc)
        except BaseException:
            return EXIT_RUNTIME

    def _flush_warnings(self, caught: list[warnings.WarningMessage]) -> None:
        if not (self._verbose and caught):
            return
        kinds = Counter(str(vf.safe_cls_name(w.category, "Warning")) for w in caught)
        summary = ", ".join(f"{name} x{n}" for name, n in sorted(kinds.items()))
        with contextlib.suppress(Exception):
            self._state.err_console.print(
                Text("debug:", style="hint"),
                Text(f"{len(caught)} engine warning(s) withheld ({summary})."),
            )

    # ---- value-free output -----------------------------------------------

    def notice(self, key: str) -> None:
        self._state.err_console.print(Text("warning:", style="warn"), Text(vf.NOTICES[key]))

    def emit(self, projection: Projection, *, status: str, render: Render | None = None) -> None:
        """`--json`: the projection under a command/status envelope; default: `render`."""
        _require(projection)
        if status not in vf.ENVELOPE_STATUSES:
            raise ValueError("unknown envelope status")
        if self._state.mode is OutputMode.json:
            self._emit({"command": self._command, "status": str(status), **projection.json()})
        elif self._state.mode is OutputMode.default and render is not None:
            render(Printer(self._state, _FRAGMENT), projection.body)

    def stream(self, projection: Projection) -> None:
        """`--output -`: the bare projection on stdout."""
        _require(projection)
        self._emit(projection.json())

    def write_report(self, path: Path, projection: Projection) -> None:
        _require(projection)
        try:
            path.write_text(_json.dumps(projection.json(), indent=2), encoding="utf-8")
        except Exception as exc:
            self.fail("report_write_failed", exc=exc)

    def write_saved_scan(self, path: Path, profile_dict: Mapping[str, Any]) -> None:
        """The one raw artifact: the full profile the user asked to save, owner-only, no path."""
        try:
            payload = _json.dumps({**profile_dict, "source_label": "source"}, indent=2).encode()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                # O_CREAT's mode is ignored for an existing file; force 0600 either way.
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o600)
                else:  # pragma: no cover - Windows
                    os.chmod(path, 0o600)
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
            finally:
                os.close(fd)
        except Exception as exc:
            self.fail("report_write_failed", exc=exc)

    @contextlib.contextmanager
    def progress(self, *stages: StageId) -> Iterator[_Progress]:
        if not all(type(s) is StageId for s in stages):
            raise TypeError("progress takes StageId members only")
        with scan_stages(self._state, [s.value for s in stages]) as handle:
            yield _Progress(handle)

    # ---- inputs (reads only) ---------------------------------------------

    def read_text(self, path: str) -> str:
        """A UTF-8 input file, or stdin for `-`."""
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")

    def peek_text(self, path: Path, size: int) -> str:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(size)

    def _emit(self, payload: dict[str, Any]) -> None:
        self._out.write(_json.dumps(payload) + "\n")
        self._out.flush()


def _require(projection: Projection) -> None:
    if not vf.is_minted(projection):
        raise TypeError("only a minted Projection can cross the value-free boundary")
