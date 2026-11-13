"""`decoy project new DIR`: make the folders and the marker of a project."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import typer

from decoy._atomic import AtomicWriteError
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.io import (
    PIPELINES_DIR,
    PROJECT_NESTED,
    PROJECT_ROOT_REFUSED,
    LayoutError,
    LayoutWarning,
    ensure_decoy_dir,
    find_project,
    prepare_out,
    shown_path,
    write_project_marker,
)
from decoy.cli.project._common import print_warnings, refuse, warning_records
from decoy.ui.output import OutputMode, emit_json, setup_output

NEW_EPILOG = """\
Examples:

  decoy project new acme

    Make ./acme as a project: decoy.yaml, pipelines/, out/ and .decoy/.

  decoy project new .

    Make the current folder a project. Run it again later to fill in anything missing.

Exit codes: 0 made, or already a project; 1 refused (an invalid decoy.yaml, your home folder,
a parent of it, or `/`); 3 a folder could not be made. Next: decoy init <name> --source <file>.
"""


@dataclass(frozen=True)
class CreatedProject:
    root: Path
    already_project: bool
    warnings: tuple[LayoutWarning, ...]


def _is_refused_root(path: Path) -> bool:
    """`$HOME`, any parent of it, or the filesystem root: too broad to be one client's project."""
    if path == Path(path.anchor):
        return True
    try:
        home = Path(os.path.expanduser("~")).resolve()
    except (OSError, RuntimeError):
        return False
    return path == home or path in home.parents


def _outer_project_warning(root: Path) -> tuple[LayoutWarning, ...]:
    """A warning when `root` sits inside another project; the nearer marker wins there."""
    try:
        outer = find_project(root.parent, None)
    except LayoutError:
        # An unusable marker further up is that project's problem, not a reason to refuse here.
        return ()
    if outer.implicit:
        return ()
    return (PROJECT_NESTED.warning(path=root, outer=outer.root),)


def create_project(directory: Path) -> CreatedProject:
    """Make the project at `directory` (and its parents), filling only what is missing.

    An existing `decoy.yaml` is validated before anything else is made, so an invalid one
    leaves the folder as it was. Safe to call from several processes: the marker is created
    exclusively and a loser reads back the winner's. Raises `LayoutError` or `OSError`.
    """
    root = directory.resolve()
    if _is_refused_root(root):
        raise PROJECT_ROOT_REFUSED.error(path=root)
    root.mkdir(parents=True, exist_ok=True)
    warnings = list(_outer_project_warning(root))
    wrote = write_project_marker(root)
    find_project(None, root)
    (root / PIPELINES_DIR).mkdir(exist_ok=True)
    _, out_warnings = prepare_out(root)
    warnings.extend(out_warnings)
    warnings.extend(ensure_decoy_dir(root))
    return CreatedProject(root, not wrote, tuple(warnings))


def new_command(
    directory: Path = typer.Argument(
        ..., metavar="DIR", help="Folder to make the project in. `.` is the current folder."
    ),
    json_: bool = typer.Option(False, "--json", help="Emit a JSON record instead of text."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Make a Decoy project: a decoy.yaml marker, pipelines/, out/ and .decoy/."""
    state = setup_output(json_, quiet, verbose)
    failure: LayoutError | None = None
    problem: OSError | None = None
    write_code: str | None = None
    created: CreatedProject | None = None
    try:
        created = create_project(directory)
    except LayoutError as exc:
        failure = exc
    except AtomicWriteError as exc:
        write_code = exc.code
    except OSError as exc:
        problem = exc
    # Refused outside the handlers so the refusal carries no chained context or OS text.
    if failure is not None:
        refuse(state, {"command": "project new"}, failure.message, code=failure.code)
    if write_code is not None:
        refuse(
            state,
            {"command": "project new"},
            f"could not write the project files ({write_code}).",
            exit_code=EXIT_RUNTIME,
        )
    if problem is not None:
        not_a_folder = isinstance(problem, (FileExistsError, NotADirectoryError))
        refuse(
            state,
            {"command": "project new"},
            f"{shown_path(directory)} cannot be made into a project folder.",
            exit_code=EXIT_USAGE if not_a_folder else EXIT_RUNTIME,
        )
    assert created is not None
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "project new",
                "status": "ok",
                "root": str(created.root),
                "already_project": created.already_project,
                "warnings": warning_records(created.warnings),
            },
        )
        return
    print_warnings(state, created.warnings)
    if state.mode is OutputMode.quiet:
        return
    verdict = "already a project" if created.already_project else "made a project"
    state.console.print(f"{created.root}: {verdict}", markup=False, highlight=False, soft_wrap=True)
    state.console.print("Next: decoy init <name> --source <file>", markup=False, highlight=False)
