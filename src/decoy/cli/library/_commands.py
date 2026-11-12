"""The `decoy library` command group: `path` and `fsck [--repair]` (plan 4.15; L1c.2).

Later slices add `list`, `show`, `diff`, `ref`, `prune`, `export` and `clean` here. This module
imports nothing from the record engine at import time, so registering the group in
`decoy.__main__` keeps `decoy --help` and `--version` free of the engine import; each command
loads the library when it runs.
"""

from __future__ import annotations

from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from decoy.ui.output import OutputState, setup_output
from decoy.ui.theme import error, hint, success, warn

__all__ = ["library_app"]

library_app = typer.Typer(
    name="library",
    help="The project's local record library: where it lives, and whether it is sound.",
    no_args_is_help=True,
)

_LIBRARY_HELP = "Use DIR as the library (else DECOY_LIBRARY, else the project's .decoy/ folder)."
_SOURCE = {"flag": "--library", "env": "DECOY_LIBRARY", "project": "project"}


def _root(state: OutputState, library: Path | None):
    from decoy.cli.io import LayoutError
    from decoy.cli.library._paths import resolve_root

    failure: LayoutError | None = None
    try:
        return resolve_root(flag=library)
    except LayoutError as exc:
        failure = exc
    state.err_console.print(error("error:"), str(failure))
    raise typer.Exit(code=EXIT_USAGE)


def _usage(state: OutputState, exc: Exception) -> typer.Exit:
    state.err_console.print(error("error:"), str(exc))
    return typer.Exit(code=EXIT_USAGE)


@library_app.command("path")
def path_command(
    library: Path | None = typer.Option(None, "--library", metavar="DIR", help=_LIBRARY_HELP),
) -> None:
    """Print the library root, where it came from, and whether it runs in degraded mode."""
    from decoy.cli.library._errors import LibraryError
    from decoy.cli.library._store import open_library

    state = setup_output(False, False, False)
    root = _root(state, library)
    caught: LibraryError | None = None
    try:
        opened = open_library(root.path)
    except LibraryError as exc:
        caught = exc
    if caught is not None:
        raise _usage(state, caught)
    state.console.print("root:", str(root.path))
    state.console.print("from:", _SOURCE[root.source])
    state.console.print("records:", "on" if root.records else "off (DECOY_LIBRARY=off)")
    if opened.degraded is None:
        state.console.print("mode:", "normal")
    else:
        why = opened.degraded + (f" ({opened.filesystem})" if opened.filesystem else "")
        state.console.print("mode:", warn("degraded"), why)
        state.console.print(
            " ", hint("hint:"), "records are still written; ref updates refuse until it is fixed."
        )
    raise typer.Exit(code=EXIT_OK)


@library_app.command("fsck")
def fsck_command(
    repair: bool = typer.Option(
        False,
        "--repair",
        help=(
            "Quarantine corrupt records, delete stale temp files, remove refs to missing "
            "records and rebuild the index. Never deletes a valid record."
        ),
    ),
    library: Path | None = typer.Option(None, "--library", metavar="DIR", help=_LIBRARY_HELP),
) -> None:
    """Check every record, ref, link, the index, temp files, modes and job logs.

    Exit 0 when clean, 4 when there are findings (warnings and notes do not count).
    """
    from decoy.cli.library import _fsck
    from decoy.cli.library._errors import LibraryError
    from decoy.cli.library._paths import check_root_budget

    state = setup_output(False, False, False)
    root = _root(state, library)
    caught: LibraryError | None = None
    try:
        check_root_budget(root.path)
        if repair:
            actions, report = _fsck.repair(root.path)
        else:
            actions, report = (), _fsck.check(root.path)
    except LibraryError as exc:
        caught = exc
    if caught is not None:
        raise _usage(state, caught)
    state.console.print("library:", str(root.path))
    for action in actions:
        state.console.print(success("repaired"), action.code, action.target)
    for item in report.items:
        label = {"finding": error("finding"), "warning": warn("warning"), "note": hint("note")}
        state.console.print(label[item.level], item.code, item.target)
    count = {
        level: sum(f.level == level for f in report.items)
        for level in ("finding", "warning", "note")
    }
    state.console.print(
        f"{report.objects} records checked: {count['finding']} findings, "
        f"{count['warning']} warnings, {count['note']} notes"
    )
    raise typer.Exit(code=EXIT_OK if report.clean else EXIT_FINDINGS)
