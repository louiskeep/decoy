"""`decoy project list [DIR]`: the projects in a folder, one level down."""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.table import Table

from decoy.cli.io import (
    PROJECT_NOT_FOUND,
    LayoutError,
    Project,
    find_project,
    list_pipelines,
)
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import warn

LIST_EPILOG = """\
Examples:

  decoy project list

    The current folder if it is a project, and each folder directly inside it that is one.

  decoy project list ~/clients --json

    The projects under ~/clients, as JSON.

Exit codes: 0 listed (nothing found is not an error); 2 DIR does not exist. A folder with an
unusable decoy.yaml is skipped and reported as a warning.
"""


def _probe(folder: Path) -> tuple[Project | None, LayoutError | None]:
    """The project rooted exactly at `folder`, None when it has no marker, or its refusal."""
    try:
        return find_project(None, folder), None
    except LayoutError as exc:
        if exc.code == PROJECT_NOT_FOUND.code:
            return None, None
        return None, exc


def _candidates(base: Path) -> list[tuple[str, Path]]:
    """`base` itself, then each direct subfolder in name order. Links are not followed."""
    found = [(".", base)]
    try:
        with os.scandir(base) as entries:
            names = sorted(e.name for e in entries if e.is_dir(follow_symlinks=False))
    except OSError:
        names = []
    found.extend((name, base / name) for name in names)
    return found


def list_command(
    directory: Path = typer.Argument(
        Path("."),
        metavar="[DIR]",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Folder to look in (default: the current folder).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit a JSON record instead of a table."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List the projects in DIR and in each folder directly under it."""
    state = setup_output(json_, quiet, verbose)
    base = directory.resolve()
    projects: list[dict[str, object]] = []
    skipped: list[tuple[str, LayoutError]] = []
    for folder, path in _candidates(base):
        project, refusal = _probe(path)
        if refusal is not None:
            skipped.append((folder, refusal))
        elif project is not None:
            count = len(list_pipelines(project))
            projects.append({"folder": folder, "root": str(project.root), "pipelines": count})
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "project list",
                "status": "ok",
                "projects": projects,
                "warnings": [
                    {"code": exc.code, "message": exc.message, "folder": folder}
                    for folder, exc in skipped
                ],
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return
    for _folder, exc in skipped:
        state.err_console.print(warn("warning:"), exc.code, exc.message, markup=False)
    if not projects:
        state.console.print(f"No projects found in {base}", markup=False, highlight=False)
        return
    table = Table("Folder", "Pipelines", "Root")
    for row in projects:
        table.add_row(str(row["folder"]), str(row["pipelines"]), str(row["root"]))
    state.console.print(table)
