"""`decoy init <csv> --preset generate`: fit a snapshot from a CSV and write a generate config.

The snapshot and the config are one unit. The pair is validated from a temporary folder with the
same relative layout first, then `_atomic.publish_local_targets` publishes both: a failure on
either replace restores the old files or removes the new ones. Source patterns: dbt init
(scaffold, then the user edits) and the stage-then-rename discipline in `_atomic.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import typer
import yaml

from decoy import _atomic
from decoy._atomic import LocalTarget, WriteMode
from decoy._config_file import parse_config_mapping
from decoy._resources import ResourceError, read_fit_max_rows
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.gen._fit import FitSourceError, fit_exact_snapshot
from decoy.ui.output import OutputMode, OutputState, emit_error, emit_json
from decoy.ui.theme import code, hint, success

_STDOUT = "-"
_NAME_OK = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SHOWN_FINDINGS = 3
# The header comments carry the CSV name and the config path, so a line break in either would
# end the comment and put the rest into the YAML. Any C0 control or DEL is refused up front,
# and so are NEL, LINE SEPARATOR and PARAGRAPH SEPARATOR, which PyYAML also reads as line breaks.
_CONTROL = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]")


class ScaffoldInvalid(Exception):
    """The candidate pair does not validate. `messages` hold names and locations only."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("scaffold failed validation")
        self.messages = messages


class _OptIn(Exception):
    """The only findings are the real-categories opt-in; `columns` are the columns it names."""

    def __init__(self, columns: list[str]) -> None:
        super().__init__("real-categories opt-in needed")
        self.columns = columns


def _quoted(columns: list[str]) -> str:
    """Column names for a comment or message: JSON-quoted, so a line break cannot get through."""
    return ", ".join(json.dumps(c) for c in columns)


def notice_for(columns: list[str], config: Path) -> str:
    """The text for the CLI output and the YAML header. Names only, never values."""
    return (
        f"column(s) {_quoted(columns)} hold category values from the CSV. {config} is written, "
        "but `decoy run` refuses it until you add `allow_real_categories: true` to those "
        "columns (the output may then repeat CSV values) or change their type "
        "(decoy explain generation)."
    )


@dataclass(frozen=True)
class Layout:
    """Where the scaffold's two files go, and the relative names the config uses."""

    config: Path
    snapshot: Path
    source_name: str
    snapshot_name: str
    target_name: str
    table: str


def layout_for(csv: Path, out: Path) -> Layout:
    """The snapshot sits beside the config and the config names it relative to itself."""
    stem = csv.stem
    table = stem if _NAME_OK.fullmatch(stem) else (re.sub(r"\W", "_", stem) or "data")
    if not _NAME_OK.fullmatch(table):
        table = f"t_{table}"
    return Layout(
        config=out,
        snapshot=out.parent / f"{stem}.snapshot.json",
        source_name=csv.name,
        snapshot_name=f"{stem}.snapshot.json",
        target_name=f"{stem}.synthetic.csv",
        table=table,
    )


def build_config(
    layout: Layout, snapshot: dict[str, Any], rows: int, opt_in: list[str] | None = None
) -> str:
    """The YAML text: one statistical column per fitted column, in file order."""
    columns = []
    for name in snapshot["columns"]:
        column: dict[str, Any] = {
            "name": name,
            "type": "statistical",
            "snapshot_file": layout.snapshot_name,
        }
        columns.append(column)
    body = {
        "version": 2,
        "global_settings": {"seed": 42},
        "tables": [{"name": layout.table, "row_count": rows, "generate_columns": columns}],
        "targets": {
            layout.table: {"type": "file", "format": "csv", "path": layout.target_name},
        },
    }
    header = (
        "# Decoy generate scaffold.\n"
        f"# Fitted from {layout.source_name} by `decoy init`; the shape comes from the "
        "snapshot beside this file.\n"
        + (f"# NOTICE: {notice_for(opt_in, layout.config)}\n" if opt_in else "")
        + f"# Next: decoy run {layout.config}  (add --rows 5 to preview first)\n\n"
    )
    return header + yaml.safe_dump(body, sort_keys=False)


def _validate_pair(config_text: str, staged_snapshot: Path) -> list[str]:
    """Run the pre-run gate on the candidate config against the staged snapshot.

    Returns the columns that only need the real-categories opt-in (the gate's structured
    finding: the engine's `STATISTICAL_REAL_CATEGORIES_NOT_ALLOWED`, column from its config
    path). Any other error raises `ScaffoldInvalid`.

    The staged file is the sibling layout: it sits beside the destination, owner-only, and
    holds the exact bytes about to be published. The copy of the config the gate reads names
    it by absolute path; the published config names the snapshot relative to itself.
    """
    from decoy_engine.reasons.plan import STATISTICAL_REAL_CATEGORIES_NOT_ALLOWED as opt_in_code

    from decoy.cli.gate import GateRoute, run_gate_on_config

    raw = parse_config_mapping(config_text)
    for column in raw["tables"][0]["generate_columns"]:
        column["snapshot_file"] = str(staged_snapshot)
    result = run_gate_on_config(raw, staged_snapshot.parent / "pipeline.yaml", GateRoute.PLAIN)
    problems = [f for f in result.findings if f.severity == "error"]
    prefix = f"tables.{raw['tables'][0]['name']}.generate_columns."
    opt_in = [
        f.logical_path.removeprefix(prefix)
        for f in problems
        if f.code == opt_in_code and (f.logical_path or "").startswith(prefix)
    ]
    others = [
        f
        for f in problems
        if f.code != opt_in_code or not (f.logical_path or "").startswith(prefix)
    ]
    if others:
        raise ScaffoldInvalid(
            [f.message + (f" (at {f.location})" if f.location else "") for f in others]
        )
    return opt_in


def _fail(state: OutputState, text: str, hint_text: str | None = None) -> NoReturn:
    """Print a usage error in the active mode and exit 1. Files and column names only."""
    emit_error(state, "init", text, hint=hint_text or None)
    raise typer.Exit(code=EXIT_USAGE)


def _confirm_overwrite(state: OutputState, existing: list[Path], yes: bool) -> None:
    """Existing files need `--yes`; the interactive mode asks once per file, like `init`."""
    for path in existing:
        if yes:
            return
        if state.mode is not OutputMode.default:
            _fail(state, f"{path} already exists.", "rerun with --yes to overwrite.")
        state.console.print(f"This will overwrite {path} ({path.stat().st_size} bytes). Continue?")
        if not typer.confirm("Overwrite?", default=False):
            state.console.print(hint("aborted."))
            raise typer.Exit(code=EXIT_USAGE)


def _new_folders(folder: Path) -> list[Path]:
    """The folders of `folder`'s path that do not exist yet, outermost first."""
    missing = []
    probe = folder
    while not probe.exists() and probe != probe.parent:
        missing.append(probe)
        probe = probe.parent
    return missing[::-1]


def scaffold_generate(state: OutputState, csv: Path, out: Path, *, yes: bool) -> None:
    """Fit `csv`, validate the pair, publish both files or neither. Exits 1 on any failure."""
    if str(out) == _STDOUT:
        _fail(
            state,
            "init <csv> --preset generate writes a snapshot file beside the config, so the "
            "config cannot go to stdout.",
            "choose a file with -o, for example -o pipeline.yaml.",
        )
    for label, path in (("the CSV path", csv), ("the output path", out)):
        if _CONTROL.search(str(path)):
            _fail(
                state,
                f"{label} contains a control character, such as a line break.",
                "rename the file or choose another path.",
            )
    if not csv.is_file():
        _fail(state, f"{csv} does not exist.")
    layout = layout_for(csv, out)
    _confirm_overwrite(state, [p for p in (layout.snapshot, layout.config) if p.exists()], yes)

    failure: Exception | None = None
    try:
        fitted = fit_exact_snapshot(csv, row_limit=read_fit_max_rows())
    except (FitSourceError, ResourceError) as exc:
        failure = exc
    if failure is not None:  # raised outside the except block: no exception context
        _fail(state, getattr(failure, "message", None) or str(failure))
    snapshot_bytes = json.dumps(fitted.snapshot, indent=1).encode("utf-8")

    made = _new_folders(layout.config.parent)
    problem = ""
    atomic_code = ""
    kept: tuple[str, ...] = ()
    left: tuple[str, ...] = ()
    invalid: ScaffoldInvalid | None = None
    opt_in: list[str] = []
    try:
        layout.config.parent.mkdir(parents=True, exist_ok=True)
        try:
            _publish_pair(
                layout,
                snapshot_bytes,
                build_config(layout, fitted.snapshot, fitted.rows_total),
                opt_in,
            )
        except _OptIn as first:
            # Nothing was changed. Publish again with the notice in the YAML header.
            opt_in = first.columns
            _publish_pair(
                layout,
                snapshot_bytes,
                build_config(layout, fitted.snapshot, fitted.rows_total, opt_in),
                opt_in,
            )
    except ScaffoldInvalid as exc:
        invalid = exc
    except _atomic.AtomicWriteError as exc:
        problem, atomic_code = _atomic.describe(exc), exc.code
        kept, left = exc.kept, exc.left
    except OSError:
        problem = "write failed"
    # A sync failure means both files are in place, and an incomplete rollback means the old
    # data sits in a backup: neither may remove anything.
    keep_all = atomic_code in {_atomic.ATOMIC_SYNC_FAILED, _atomic.ATOMIC_ROLLBACK_INCOMPLETE}
    if (invalid is not None or problem) and not keep_all:
        for folder in reversed(made):
            try:
                folder.rmdir()
            except OSError:
                break
    if invalid is not None:
        shown = invalid.messages[:_SHOWN_FINDINGS]
        more = len(invalid.messages) - len(shown)
        _fail(
            state,
            "the generated config does not validate: "
            + "; ".join(shown)
            + (f" (and {more} more)" if more else ""),
            "replace the column with a generator type (decoy explain generation) or remove it.",
        )
    if atomic_code == _atomic.ATOMIC_SYNC_FAILED:
        _fail(
            state,
            f"the scaffold files were written, but the disk did not confirm them ({problem}).",
            f"check {layout.config} and {layout.snapshot} before you use them.",
        )
    if atomic_code == _atomic.ATOMIC_ROLLBACK_INCOMPLETE:
        parts = []
        if kept:
            parts.append(f"The old file is kept at {', '.join(kept)} in {layout.config.parent}.")
        if left:
            parts.append(f"A new file could not be removed: {', '.join(left)}.")
        _fail(
            state,
            "could not write the scaffold and could not undo every file. " + " ".join(parts),
            "rename a kept file back over the one it replaced; delete a left-over new file.",
        )
    if problem:
        _fail(state, f"could not write the scaffold: {problem}. Nothing was changed.")

    _report(state, csv, layout, fitted.rows_total, len(fitted.snapshot["columns"]), opt_in)


def _publish_pair(
    layout: Layout, snapshot_bytes: bytes, config_text: str, declared: list[str]
) -> None:
    """Publish the snapshot and config as one unit after the gate passes on the staged pair.

    Raises `_OptIn` (nothing changed) when the gate's opt-in columns differ from `declared`,
    the ones `config_text` already names in its header.
    """

    def check(staged: list[Path]) -> None:
        columns = _validate_pair(config_text, staged[0])
        if columns != declared:
            raise _OptIn(columns)

    _atomic.publish_local_targets(
        [
            LocalTarget(
                layout.snapshot,
                snapshot_bytes,
                WriteMode.REPLACE if layout.snapshot.exists() else WriteMode.CREATE_ONCE,
                private=True,
            ),
            LocalTarget(
                layout.config,
                config_text.encode("utf-8"),
                WriteMode.REPLACE if layout.config.exists() else WriteMode.CREATE_ONCE,
            ),
        ],
        check=check,
    )


def _report(
    state: OutputState, csv: Path, layout: Layout, rows: int, columns: int, opt_in: list[str]
) -> None:
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "init",
                "status": "ok",
                "out": str(layout.config),
                "snapshot": str(layout.snapshot),
                "source": str(csv),
                "mode": "generate-scaffold",
                "row_count": rows,
                "column_count": columns,
                **(
                    {"opt_in_columns": opt_in, "notice": notice_for(opt_in, layout.config)}
                    if opt_in
                    else {}
                ),
            },
        )
    elif state.mode is not OutputMode.quiet:
        state.console.print()
        state.console.print(
            success("OK"), "wrote", code(str(layout.config)), "and", code(str(layout.snapshot))
        )
        state.console.print(
            hint("Next:"),
            code(f"decoy run {layout.config} --rows 5"),
            "to preview, then",
            code(f"decoy run {layout.config}"),
        )
    if opt_in and state.mode is not OutputMode.json:
        state.err_console.print(hint("notice:"), notice_for(opt_in, layout.config), markup=False)
