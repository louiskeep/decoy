"""The one value-free output boundary for `decoy pre-scan` and `decoy post-scan`.

Every byte these commands put on a surface -- stdout, stderr, the `--json`
envelope, `--verbose` diagnostics, a written report -- leaves through a
`Surface`. Call sites never format text from data; they hand the boundary one
of three closed things:

  * a reason key from `REASONS` (fixed message + fixed hint + stable code),
    optionally with a typed `Location` (parse position or layout entry index
    plus a closed rule code) and an exception, of which only the type name is
    ever used;
  * a `Projection` minted by `decoy.cli._projections`: an allowlisted, typed,
    value-free view of an engine object (numbers, closed vocabularies, policed
    names, opaque ids) -- raw engine reports are never serialized;
  * a notice key from `NOTICES` (fixed stderr warning).

Engine calls run inside `Surface.engine()`, which captures Python warnings and
logging so engine diagnostics (which can quote cells, paths and table names)
never reach stderr or a log handler; `--verbose` reports only their count and
category names. `guarded` wraps every command so an unexpected exception
becomes a type-name-only error rather than a traceback.

The one deliberate raw artifact is the saved scan written by
`pre-scan --output FILE`: an explicit, user-requested file that keeps the
profiler's top values and sentinels. It is written here too, with the source
label replaced, so even that file carries no path.

Pattern: the platform's typed `fidelity-report/v1` projection
(decoy-platform `api/jobs/fidelity_projection.py`) applied to every CLI surface,
plus a closed error-code table in the style of RFC 9457 problem details (stable
type code, fixed title, no echoed input).
"""

from __future__ import annotations

import functools
import json as _json
import logging
import math
import warnings
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn

import typer
from typer.core import TyperGroup

try:  # typer >= 0.26 vendors Click
    from typer._click.exceptions import UsageError
except ImportError:  # pragma: no cover - older typer on stock Click
    from click.exceptions import UsageError

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import error, hint, warn

# ---------------------------------------------------------------------------
# Closed reason table: the only error text these commands can print.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reason:
    code: str
    message: str
    hint: str | None = None
    exit_code: int = EXIT_USAGE


_NO_TRACE = "no traceback is printed: diagnostics can carry row data."
_SCAN_HINT = "pass the JSON file produced by decoy pre-scan --output scan.json"
_LAYOUT_HINT = "each column needs a string 'name' and integer 'start' (0-indexed) and 'width'."

REASONS: Mapping[str, Reason] = MappingProxyType(
    {
        # pre-scan
        "output_stream_conflict": Reason(
            "usage_error",
            "--output - cannot be combined with --json or --quiet.",
            "use --json for the envelope, or --output - alone for the projection.",
        ),
        "layout_required": Reason(
            "usage_error",
            "fixed-width input requires --layout: column boundaries are ambiguous "
            "without an explicit layout spec.",
            "provide a layout file: decoy pre-scan SOURCE --layout layout.yaml",
        ),
        "layout_not_found": Reason("usage_error", "the --layout file was not found."),
        "layout_invalid": Reason("layout_invalid", "the --layout file is invalid.", _LAYOUT_HINT),
        "scan_failed": Reason("scan_failed", "scan failed.", _NO_TRACE, EXIT_RUNTIME),
        "scan_is_raw_data": Reason(
            "scan_unreadable",
            "the input looks like raw data, not a pre-scan profile JSON.",
            "scan it first: decoy pre-scan SOURCE --output scan.json",
        ),
        "scan_not_found": Reason(
            "scan_unreadable", "could not open the scan file: file not found.", _SCAN_HINT
        ),
        "scan_not_json": Reason(
            "scan_unreadable", "could not parse the scan file as JSON.", _SCAN_HINT
        ),
        "scan_unreadable": Reason("scan_unreadable", "could not read the scan file.", _SCAN_HINT),
        "field_not_found": Reason(
            "usage_error",
            "the requested field is not in the scan.",
            "list all fields with: decoy pre-scan fields SCAN_FILE",
        ),
        "diff_two_stdin": Reason(
            "usage_error",
            "only one of OLD or NEW can be `-` (stdin).",
            "pipe one scan, pass the other as a path.",
        ),
        # post-scan
        "joint_format": Reason("usage_error", "--joint expects 'colA,colB'."),
        "grade_and_score": Reason(
            "usage_error", "specify only one of --min-grade / --min-score, not both."
        ),
        "grade_invalid": Reason("usage_error", "--min-grade must be one of A, B, C, D."),
        "mode_invalid": Reason("usage_error", "--mode must be one of report, warn, fail."),
        "config_invalid": Reason("config_invalid", "could not parse --config."),
        "config_not_yaml": Reason("config_invalid", "could not parse YAML in --config."),
        "policy_not_yaml": Reason("config_invalid", "could not parse YAML in --policy."),
        "policy_invalid": Reason("config_invalid", "could not parse --policy."),
        "policy_not_mapping": Reason("config_invalid", "--policy must be a YAML/JSON mapping."),
        "source_unreadable": Reason("input_unreadable", "could not read the source file."),
        "output_unreadable": Reason("input_unreadable", "could not read the output file."),
        "input_not_found": Reason("input_unreadable", "could not open an input file (not found)."),
        "fidelity_failed": Reason(
            "check_failed", "fidelity measurement failed.", _NO_TRACE, EXIT_RUNTIME
        ),
        "integrity_failed": Reason(
            "check_failed", "integrity check failed.", _NO_TRACE, EXIT_RUNTIME
        ),
        # shared
        "report_write_failed": Reason(
            "write_failed", "could not write the report file.", None, EXIT_RUNTIME
        ),
        "unexpected": Reason("internal_error", "unexpected failure.", _NO_TRACE, EXIT_RUNTIME),
    }
)

NOTICES: Mapping[str, str] = MappingProxyType(
    {
        "source_mismatch": (
            "--source does not match the pipeline's declared input path; proceeding "
            "with --source as ground truth (suppress with --allow-source-mismatch)."
        ),
    }
)

# ---------------------------------------------------------------------------
# Typed locations: positions and closed rule codes, never the offending value.
# ---------------------------------------------------------------------------

LAYOUT_KEYS = frozenset({"name", "start", "width"})
LAYOUT_RULES: Mapping[str, str] = MappingProxyType(
    {
        "not_parseable": "the file is not valid YAML or JSON",
        "not_mapping": "the file must be a mapping with a 'columns' key",
        "columns_not_list": "'columns' must be a list of column mappings",
        "entry_not_mapping": "the entry must be a mapping",
        "name_missing": "'name' is missing or empty",
        "value_missing": "a required key is missing",
        "not_integer": "the value must be an integer",
        "start_negative": "'start' must be >= 0",
        "width_not_positive": "'width' must be > 0",
    }
)


@dataclass(frozen=True)
class Location:
    """Where a parse problem is. Every field is an ordinal or a closed code."""

    kind: str  # "yaml" | "layout"
    line: int | None = None
    column: int | None = None
    index: int | None = None
    key: str | None = None
    rule: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def text(self) -> str:
        if self.kind == "yaml" and self.line is not None:
            return f"invalid syntax at line {self.line}, column {self.column}"
        parts = []
        if self.index is not None:
            parts.append(f"layout column {self.index}")
        if self.key is not None:
            parts.append(f"key '{self.key}'")
        rule = LAYOUT_RULES.get(self.rule or "", "invalid entry")
        return (", ".join(parts) + ": " if parts else "") + rule


def yaml_location(exc: BaseException) -> Location | None:
    """Line/column of a PyYAML mark (1-indexed); the snippet and message are dropped."""
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    line, column = getattr(mark, "line", None), getattr(mark, "column", None)
    if type(line) is int and type(column) is int:
        return Location("yaml", line=line + 1, column=column + 1)
    return None


class LayoutError(ValueError):
    """A layout problem described by entry index + closed key/rule codes only."""

    def __init__(self, rule: str, *, index: int | None = None, key: str | None = None) -> None:
        if rule not in LAYOUT_RULES:
            raise ValueError("unknown layout rule")
        if key is not None and key not in LAYOUT_KEYS:
            raise ValueError("unknown layout key")
        if index is not None and (type(index) is not int or index < 0):
            raise ValueError("layout index must be a non-negative ordinal")
        super().__init__(rule)
        self.location = Location("layout", index=index, key=key, rule=rule)


def exc_label(exc: BaseException) -> str:
    """The exception type name -- the only part of an exception that is safe."""
    return type(exc).__name__


# ---------------------------------------------------------------------------
# Projections: the only payload a Surface will serialize.
# ---------------------------------------------------------------------------

_MINT = object()


@dataclass(frozen=True)
class Projection:
    """A value-free payload. Construct only through `decoy.cli._projections`."""

    schema: str
    body: Mapping[str, Any]
    token: object = None

    def __post_init__(self) -> None:
        if self.token is not _MINT:
            raise TypeError("Projection is minted by decoy.cli._projections only")
        _check_json(self.body)

    def json(self) -> dict[str, Any]:
        return {"schema_version": self.schema, **self.body}


def mint(schema: str, body: dict[str, Any]) -> Projection:
    return Projection(schema, MappingProxyType(body), _MINT)


def _check_json(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite number in projection")
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            if type(k) is not str:
                raise TypeError("projection keys must be str")
            _check_json(v)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _check_json(v)
        return
    raise TypeError(f"{type(value).__name__} cannot cross the value-free boundary")


# ---------------------------------------------------------------------------
# The Surface.
# ---------------------------------------------------------------------------


class Printer:
    """What a renderer may do: print projection fields, tables and cards to stdout."""

    def __init__(self, state: OutputState) -> None:
        self._state = state

    def line(self, *parts: Any) -> None:
        self._state.console.print(*parts)

    def table(self, *headers: str, rows: list[tuple[Any, ...]], title: str | None = None) -> None:
        tbl = make_table(*headers, title=title)
        for row in rows:
            tbl.add_row(*row)
        self._state.console.print(tbl)

    def card(self, command: str, facts: list[tuple[str, str]], next_hint: str | None, status: str):
        render_card(self._state, command=command, facts=facts, next_hint=next_hint, status=status)


class Surface:
    def __init__(self, command: str, json_: bool, quiet: bool, verbose: bool) -> None:
        self.command = command
        self.state = setup_output(json_, quiet, verbose)

    @property
    def mode(self) -> OutputMode:
        return self.state.mode

    def fail(
        self,
        reason: str,
        *,
        exc: BaseException | None = None,
        location: Location | None = None,
        suggestion: str | None = None,
    ) -> NoReturn:
        """Emit a closed-reason error and exit.

        `suggestion` must already be a policed name from a projection.
        """
        r = REASONS[reason]
        hint_text = f"did you mean {suggestion}?" if suggestion else r.hint
        if self.mode is OutputMode.json:
            payload: dict[str, Any] = {
                "command": self.command,
                "status": "error",
                "code": r.code,
                "reason": reason,
                "error": r.message,
            }
            if location is not None:
                payload["location"] = location.as_json()
            if exc is not None:
                payload["error_type"] = exc_label(exc)
            _emit(payload)
        else:
            err = self.state.err_console
            detail = [r.message]
            if location is not None:
                detail.append(f"({location.text()})")
            if exc is not None:
                detail.append(f"[{exc_label(exc)}]")
            err.print(error("error:"), " ".join(detail))
            if hint_text and self.mode is not OutputMode.quiet:
                err.print(" ", hint("hint:"), hint_text)
        raise typer.Exit(code=r.exit_code)

    def notice(self, key: str) -> None:
        self.state.err_console.print(warn("warning:"), NOTICES[key])

    def emit(
        self,
        projection: Projection,
        *,
        status: str,
        render: Callable[[Printer, Mapping[str, Any]], None] | None = None,
        extra: Mapping[str, str] | None = None,
    ) -> None:
        """`--json`: the projection under a command/status envelope; default: `render`."""
        _require(projection)
        if self.mode is OutputMode.json:
            _emit({"command": self.command, "status": status, **(extra or {}), **projection.json()})
        elif self.mode is OutputMode.default and render is not None:
            render(Printer(self.state), projection.body)

    def stream(self, projection: Projection) -> None:
        """`--output -`: the bare projection on stdout."""
        _require(projection)
        _emit(projection.json())

    def write(self, path: Path, projection: Projection) -> None:
        _require(projection)
        try:
            path.write_text(_json.dumps(projection.json(), indent=2), encoding="utf-8")
        except Exception as exc:
            self.fail("report_write_failed", exc=exc)

    def write_saved_scan(self, path: Path, profile_dict: dict[str, Any]) -> None:
        """The one raw artifact: the full profile the user asked to save, minus its path."""
        saved = {**profile_dict, "source_label": "source"}
        try:
            path.write_text(_json.dumps(saved, indent=2), encoding="utf-8")
        except Exception as exc:
            self.fail("report_write_failed", exc=exc)

    @contextmanager
    def engine(self) -> Iterator[None]:
        """Run engine/pandas code with its warnings and log records held back."""
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                yield
        finally:
            logging.disable(previous_disable)
        if self.state.verbose and caught:
            kinds = Counter(w.category.__name__ for w in caught)
            summary = ", ".join(f"{name} x{n}" for name, n in sorted(kinds.items()))
            self.state.err_console.print(
                hint("debug:"), f"{len(caught)} engine warning(s) withheld ({summary})."
            )


def _require(projection: Projection) -> None:
    if not isinstance(projection, Projection) or projection.token is not _MINT:
        raise TypeError("only a minted Projection can cross the value-free boundary")


def _emit(payload: dict[str, Any]) -> None:
    import sys

    sys.stdout.write(_json.dumps(payload) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Command and group guards.
# ---------------------------------------------------------------------------


def guarded(command: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Wrap a command so any escaped exception is a type-name-only error."""

    def deco(fn: Callable[..., None]) -> Callable[..., None]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> None:
            try:
                fn(*args, **kwargs)
            except (typer.Exit, typer.Abort, UsageError):
                raise
            except Exception as exc:
                surface = Surface(
                    command, bool(kwargs.get("json_")), bool(kwargs.get("quiet")), False
                )
                surface.fail("unexpected", exc=exc)

        wrapper.__value_free_guard__ = command  # type: ignore[attr-defined]
        return wrapper

    return deco


def value_free_usage_errors(base: type[TyperGroup]) -> type[TyperGroup]:
    """Wrap a group so Click usage errors name only the declared parameter."""

    class _ValueFreeGroup(base):  # type: ignore[valid-type, misc]
        def invoke(self, ctx):  # type: ignore[override]
            try:
                return super().invoke(ctx)
            except UsageError as exc:
                param = getattr(exc, "param", None)
                name = getattr(param, "name", None)
                where = f" for '{name}'" if isinstance(name, str) and name.isidentifier() else ""
                typer.echo(f"error: invalid usage{where} (usage_error).", err=True)
                typer.echo("  hint: run the command with --help.", err=True)
                ctx.exit(2)

    return _ValueFreeGroup
