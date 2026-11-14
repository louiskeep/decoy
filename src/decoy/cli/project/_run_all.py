"""`decoy run` with no argument, and `decoy run --all`.

No argument picks the project's one pipeline. `--all` runs every pipeline of the project, each
in its own process (`python -c <entry point> --project ROOT run YAML --json ...`), so engine state, the
logger and memory limits never carry from one pipeline to the next and each child's exit code
keeps its single-run meaning. `--project` goes to each child so it places outputs exactly as
this process resolved the project. The run goes on after a failure.

The summary exit code is the first of 3, 5, 1, 4, 2, 0 that any child produced: failed to
finish, refused, then finished with findings or warnings. A child that exits outside 0 to 5, is
killed by a signal (a negative code), or prints `--json` output that is not one object counts as
3, so a crashed pipeline never reads as clean.

Nothing here prints a row value: messages name pipelines, folders and exit codes only. This
module never imports the run package, which calls it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

import typer
from rich.table import Table

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.io import (
    PROJECT_NOT_FOUND,
    LayoutError,
    PipelineEntry,
    PipelineRef,
    Project,
    explicit_project,
    find_project,
    list_pipelines,
    member_ref,
)
from decoy.ui.output import OutputMode, OutputState, emit_error, emit_json

_PRIORITY = (3, 5, 1, 4, 2, 0)
_RUN_CODES = range(0, 6)
_INIT_HINT = "Make one with `decoy init <name>`."


def _fail(
    state: OutputState, message: str, *, code: str | None = None, hint: str | None = None
) -> NoReturn:
    emit_error(state, "run", message, code=code, hint=hint)
    raise typer.Exit(code=EXIT_USAGE)


def _project_or_fail(state: OutputState, ctx: typer.Context) -> tuple[Project, list[PipelineEntry]]:
    """The selected project and its pipelines, or exit 1 with the registry message."""
    try:
        project = find_project(None, explicit_project(ctx))
        if project.implicit:
            raise PROJECT_NOT_FOUND.error(where="the current folder")
        return project, list_pipelines(project)
    except LayoutError as exc:
        failure = exc
    _fail(state, failure.message, code=failure.code)


def only_pipeline(state: OutputState, ctx: typer.Context) -> PipelineRef:
    """The one pipeline of the selected project, for `decoy run` with no argument.

    No project is the missing-argument usage error (exit 2) with a hint. A project with none or
    with several pipelines exits 1; several are listed so the user can name one.
    """
    try:
        project = find_project(None, explicit_project(ctx))
    except LayoutError as exc:
        failure = exc
    else:
        failure = None
    if failure is not None:
        _fail(state, failure.message, code=failure.code)
    if project.implicit:
        raise typer.BadParameter(
            "Missing argument 'CONFIG'. Name a pipeline or give its path, or run inside a "
            "project (see --project DIR) that has exactly one pipeline.",
            ctx=ctx,
            param_hint="'CONFIG'",
        )
    entries = list_pipelines(project)
    if not entries:
        _fail(state, f"No pipelines in {project.root}.", hint=_INIT_HINT)
    if len(entries) > 1:
        names = ", ".join(e.name for e in entries)
        _fail(
            state,
            f"{project.root} has {len(entries)} pipelines: {names}.",
            hint="name one, or run them all with `decoy run --all`.",
        )
    if state.mode is OutputMode.default:
        state.err_console.print(f"Running the only pipeline: {entries[0].name}", markup=False)
    try:
        return member_ref(project, entries[0].name)
    except LayoutError as exc:
        failure = exc
    _fail(state, failure.message, code=failure.code)


def _effective(returncode: int | None, payload: object) -> int:
    """The exit code to count for one child: its own when it is a run code and its JSON parsed."""
    if returncode in _RUN_CODES and isinstance(payload, dict):
        return returncode
    return EXIT_RUNTIME


def _parse(stdout: str | None) -> object:
    try:
        return json.loads(stdout or "")
    except ValueError:
        return None


def _record(name: str, returncode: int | None, payload: object) -> tuple[int, dict]:
    """One child's exit code and record. `returncode` is None when it could not be started."""
    code = _effective(returncode, payload)
    if isinstance(payload, dict) and code == returncode:
        return code, {**payload, "exit_code": code}
    return code, {
        "command": "run",
        "status": "failed",
        "name": name,
        "exit_code": code,
        "error": (
            f"The run of {name} could not be started."
            if returncode is None
            else f"The run of {name} did not finish cleanly (process status {returncode})."
        ),
    }


def _summary_code(codes: Sequence[int]) -> int:
    return next(code for code in _PRIORITY if code in codes)


# `-m decoy` would put the current folder first on the import path, so a `decoy.py` or a
# `decoy/` package inside a project would replace the installed CLI. A `PYTHONPATH` of `.` or of
# the project folder does the same, so the boot drops every path entry that resolves to the
# working folder or to the project root (argv[2], after `--project`) and then runs the same
# entry point (`decoy.__main__:app`). `-I` would also drop `PYTHONPATH` and other variables a
# child needs, so the environment passes through.
_CHILD_BOOT = (
    "import os, sys\n"
    "bad = {os.path.realpath(os.getcwd()), os.path.realpath(sys.argv[2])}\n"
    "sys.path[:] = [p for p in sys.path if os.path.realpath(p or '.') not in bad]\n"
    "from decoy.__main__ import app\n"
    "app()\n"
)


def _child(root: Path, entry: PipelineEntry, flags: Sequence[str], env: Mapping[str, str]):
    cmd = [sys.executable, "-c", _CHILD_BOOT, "--project", str(root)]
    cmd += ["run", str(entry.yaml), "--json", *flags]
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, text=True, env={**os.environ, **env}, check=False
    )


def _render(state: OutputState, rows: list[tuple[str, int, str]], code: int) -> None:
    table = Table("Pipeline", "Exit", "Run folder")
    for name, exit_code, folder in rows:
        table.add_row(name, str(exit_code), folder)
    state.console.print(table)
    bad = sum(1 for _, c, _ in rows if c != EXIT_OK)
    if bad == 0:
        state.console.print(f"All {len(rows)} pipelines exited 0.", markup=False)
    else:
        line = f"{bad} of {len(rows)} pipelines exited non-zero. Exit code {code}."
        state.console.print(line, markup=False)


def run_all(
    state: OutputState,
    ctx: typer.Context,
    *,
    named: bool,
    refused: Sequence[str],
    flags: Sequence[str],
    env: Mapping[str, str],
) -> NoReturn:
    """Run every pipeline of the selected project and exit with the summary code.

    `named` is true when the user also gave a pipeline; `refused` lists the flags given that
    each name one file; `flags` and `env` are what each child gets besides the fixed command.
    """
    if named:
        _fail(state, "--all runs every pipeline of the project, so it takes no pipeline name.")
    if refused:
        _fail(
            state,
            f"{', '.join(refused)} names one file, and --all would write it once per pipeline.",
            hint="run the pipelines one at a time to use it.",
        )
    project, entries = _project_or_fail(state, ctx)
    if not entries:
        _fail(state, f"No pipelines in {project.root}.", hint=_INIT_HINT)
    records: list[dict] = []
    rows: list[tuple[str, int, str]] = []
    for position, entry in enumerate(entries, start=1):
        if state.mode is OutputMode.default:
            line = f"Running pipeline {entry.name} ({position} of {len(entries)})"
            state.err_console.print(line, markup=False)
        returncode: int | None = None
        stdout: str | None = None
        try:
            done = _child(project.root, entry, flags, env)
            returncode, stdout = done.returncode, done.stdout
        except OSError:
            pass  # a child that cannot start counts as 3 below; the exception text is dropped
        code, record = _record(entry.name, returncode, _parse(stdout))
        records.append(record)
        rows.append((entry.name, code, str(record.get("output_dir", "-"))))
    summary = _summary_code([code for _, code, _ in rows])
    if state.mode is OutputMode.json:
        body: dict = {
            "command": "run",
            "status": "ok" if summary == EXIT_OK else "failed",
            "pipelines": records,
            "exit_code": summary,
        }
        if summary != EXIT_OK:
            body["error"] = f"{sum(1 for r in rows if r[1])} of {len(rows)} pipelines failed."
        emit_json(state, body)
    elif state.mode is OutputMode.default:
        _render(state, rows, summary)
    elif summary != EXIT_OK:
        failed = sum(1 for r in rows if r[1])
        emit_error(state, "run", f"{failed} of {len(rows)} pipelines failed.")
    raise typer.Exit(code=summary)
