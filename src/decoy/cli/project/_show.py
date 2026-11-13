"""`decoy project show`: the selected project and its pipelines."""

from __future__ import annotations

import typer
from rich.table import Table

from decoy.cli.io import (
    PROJECT_NOT_FOUND,
    LayoutError,
    LayoutWarning,
    Project,
    explicit_project,
    find_project,
    list_pipelines,
    run_history,
)
from decoy.cli.project._common import print_warnings, refuse, warning_records
from decoy.ui.output import OutputMode, emit_json, setup_output

NO_RUN = "-"

SHOW_EPILOG = """\
Examples:

  decoy project show

    The project around the current folder, with each pipeline's newest run and last clean run.

  decoy --project acme project show --json

    The same for the project in ./acme, as JSON.

Exit codes: 0 shown; 1 no project here (make one with `decoy project new <dir>`) or an invalid
marker. Status is `-` until run records exist.
"""


def _rows(project: Project) -> tuple[list[dict[str, str | None]], list[LayoutWarning]]:
    rows: list[dict[str, str | None]] = []
    warnings: list[LayoutWarning] = []
    for entry in list_pipelines(project):
        history = run_history(project.root, entry.name)
        warnings.extend(history.warnings)
        rows.append(
            {
                "name": entry.name,
                "yaml": entry.yaml.relative_to(project.root).as_posix(),
                "last_run": history.last_run,
                "last_clean_run": history.last_clean,
                "status": NO_RUN,
            }
        )
    return rows, warnings


def show_command(
    ctx: typer.Context,
    json_: bool = typer.Option(False, "--json", help="Emit a JSON record instead of a table."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Show the selected project: its root, marker and pipelines with their last runs."""
    state = setup_output(json_, quiet, verbose)
    failure: LayoutError | None = None
    project: Project | None = None
    try:
        project = find_project(None, explicit_project(ctx))
        if project.implicit:
            raise PROJECT_NOT_FOUND.error(where="the current folder")
    except LayoutError as exc:
        failure = exc
    if failure is not None:
        refuse(state, {"command": "project show"}, failure.message, code=failure.code)
    assert project is not None
    rows, warnings = _rows(project)
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "project show",
                "status": "ok",
                "root": str(project.root),
                "pipelines": rows,
                "warnings": warning_records(warnings),
            },
        )
        return
    print_warnings(state, warnings)
    if state.mode is OutputMode.quiet:
        return
    state.console.print(f"Project: {project.root}", markup=False, highlight=False, soft_wrap=True)
    if not rows:
        state.console.print("No pipelines yet. Next: decoy init <name> --source <file>")
        return
    table = Table("Name", "YAML", "Last run", "Last clean run", "Status")
    for row in rows:
        table.add_row(
            str(row["name"]),
            str(row["yaml"]),
            row["last_run"] or NO_RUN,
            row["last_clean_run"] or NO_RUN,
            str(row["status"]),
        )
    state.console.print(table)
