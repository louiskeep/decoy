"""The one root, error and exit path of the `decoy library` commands.

Every command (`path`, `fsck`, `list`, `show`, `diff`, `ref`) starts a `LibraryCommand`, which
finds the root (`--library`, `DECOY_LIBRARY`, the project), opens the library and reports a
failure through `decoy.ui.output.emit_error`, the CLI's one error emitter: `error: [code] ...`
on stderr, or one `decoy-error-v1` object on stdout under `--json`. A code in
`USAGE_CODES` describes what the user typed and exits `EXIT_USAGE` (1); any other library code
is the library's own state and exits `EXIT_RUNTIME` (3).

Imports nothing from the record engine at import time (see `_commands`); library operations come
from the package facade.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import typer

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputState, emit_error, setup_output

if TYPE_CHECKING:
    from decoy.cli.io import PipelineRef
    from decoy.cli.library import Library, LibraryRoot

__all__ = ["LIBRARY_HELP", "SOURCE", "LibraryCommand", "library_option", "start"]

LIBRARY_HELP = "Use DIR as the library (else DECOY_LIBRARY, else the project's .decoy/ folder)."
SOURCE = {"flag": "--library", "env": "DECOY_LIBRARY", "project": "project"}


def library_option() -> Any:
    return typer.Option(None, "--library", metavar="DIR", help=LIBRARY_HELP)


@dataclass(frozen=True)
class LibraryCommand:
    """One running `decoy library` command: its output state and its name for errors."""

    state: OutputState
    name: str

    def fail(
        self, message: str, exit_code: int = EXIT_USAGE, *, code: str | None = None
    ) -> NoReturn:
        """Report a refusal through the one emitter and exit. `message` names the problem,
        never a path, a value or the typed text."""
        emit_error(self.state, self.name, message, code=code)
        raise typer.Exit(code=exit_code)

    def fail_library(self, exc: Exception | None) -> NoReturn:
        """A `LibraryError` (or a layout refusal): its code and error class, never a path."""
        from decoy.cli.library import USAGE_CODES

        code = getattr(exc, "code", None)
        exit_code = EXIT_USAGE if code in USAGE_CODES else EXIT_RUNTIME
        self.fail(str(exc), exit_code, code=code)

    def root(self, library: Path | None, pipeline: PipelineRef | None = None) -> LibraryRoot:
        """The library root: `--library`, else the environment, else the project of the pipeline
        when one is given (its YAML's folder, or `--project`), else of the current folder. A
        root that cannot be found is a usage error."""
        from decoy.cli.io import LayoutError
        from decoy.cli.library import LibraryError, resolve_root

        failure: LayoutError | None = None
        fault: LibraryError | None = None
        try:
            if pipeline is None:
                return resolve_root(flag=library)
            project = pipeline.project.root if pipeline.project is not None else None
            return resolve_root(flag=library, pipeline=pipeline.yaml, project=project)
        except LayoutError as exc:
            failure = exc
        except LibraryError as exc:
            fault = exc
        if fault is not None:
            self.fail_library(fault)
        self.fail(str(failure), EXIT_USAGE, code=getattr(failure, "code", None))

    def library(self, root: Path) -> Library:
        from decoy.cli.library import LibraryError, open_library

        caught: LibraryError | None = None
        try:
            return open_library(root)
        except LibraryError as exc:
            caught = exc
        self.fail_library(caught)


def start(name: str, json_: bool = False) -> LibraryCommand:
    """Set up output for the command `name` (`"library list"`, ...)."""
    return LibraryCommand(setup_output(json_, False, False), name)
