"""Shared plumbing for the `decoy library` commands: the `--library` option, the root, errors.

Imports nothing from the record engine at import time (see `_commands`). Errors print `error:`
on stderr in every mode, with `EXIT_USAGE` for what the user typed and `EXIT_RUNTIME` for the
library's own state; `--json` stdout carries only a successful result.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import typer

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputState
from decoy.ui.theme import error

if TYPE_CHECKING:
    from decoy.cli.library._paths import LibraryRoot
    from decoy.cli.library._store import Library

__all__ = ["LIBRARY_HELP", "SOURCE", "fail", "library_option", "open_or_fail", "root_or_fail"]

LIBRARY_HELP = "Use DIR as the library (else DECOY_LIBRARY, else the project's .decoy/ folder)."
SOURCE = {"flag": "--library", "env": "DECOY_LIBRARY", "project": "project"}


def library_option() -> Any:
    return typer.Option(None, "--library", metavar="DIR", help=LIBRARY_HELP)


def fail(state: OutputState, message: str, code: int = EXIT_USAGE) -> NoReturn:
    # stderr in every mode: under --json, stdout stays empty on failure (the exit code says so).
    state.err_console.print(error("error:"), message, markup=False, highlight=False)
    raise typer.Exit(code=code)


def fail_library(state: OutputState, exc: Exception) -> NoReturn:
    """A `LibraryError`: its text is the code and an error class, never a path."""
    from decoy.cli.library._errors import (
        LIBRARY_PATH_TOO_LONG,
        LIBRARY_POLICY_INVALID,
        REF_NAME_INVALID,
    )

    # Codes that describe what the user typed; anything else is the library's own state.
    usage = {REF_NAME_INVALID, LIBRARY_PATH_TOO_LONG, LIBRARY_POLICY_INVALID}
    code = getattr(exc, "code", "")
    fail(state, str(exc), EXIT_USAGE if code in usage else EXIT_RUNTIME)


def root_or_fail(state: OutputState, library: Path | None) -> LibraryRoot:
    from decoy.cli.io import LayoutError
    from decoy.cli.library._paths import resolve_root

    failure: LayoutError | None = None
    try:
        return resolve_root(flag=library)
    except LayoutError as exc:
        failure = exc
    fail(state, str(failure))


def open_or_fail(state: OutputState, root: Path) -> Library:
    from decoy.cli.library._errors import LibraryError
    from decoy.cli.library._store import open_library

    caught: LibraryError | None = None
    try:
        return open_library(root)
    except LibraryError as exc:
        caught = exc
    fail_library(state, caught)
