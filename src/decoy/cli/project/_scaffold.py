"""Where `decoy init` puts a pipeline and which paths it writes into it.

The command maps its arguments here and keeps the file writes itself (the file-sink registry
names `cli/init.py`). This module only decides:

- the argument: an existing file is the source (as before), any other token is a pipeline name;
- the destination: `pipelines/<name>/pipeline.yaml` of the selected project, a file given with
  `-o`, or stdout;
- the source path written into the YAML (relative to the YAML's folder when that stays inside
  the project or follows `-o`, else absolute) and the bare target `<stem>.masked.<ext>` that `run`
  places in a run folder.

Nothing here reads or prints a row value.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.io import (
    PIPELINE_NAME_INVALID,
    PIPELINES_DIR,
    PROJECT_NOT_FOUND,
    LayoutError,
    find_project,
    is_valid_name,
    looks_like_path,
    member_has_link,
    member_yaml,
    name_slug,
)
from decoy.ui.output import OutputMode, OutputState, emit_error

# The one table of source file types `init` scaffolds from: suffix to (format, csv delimiter).
SOURCE_SUFFIXES: dict[str, tuple[str, str | None]] = {
    ".csv": ("csv", None),
    ".tsv": ("csv", "\t"),
    ".parquet": ("parquet", None),
    ".pq": ("parquet", None),
}
DATA_SUFFIXES = tuple(SOURCE_SUFFIXES)


class ScaffoldRefused(Exception):
    """A usage refusal with fixed text. `code` is None: only `layout.*` refusals carry one."""

    code: str | None = None

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Argument:
    """What the positional token and `--source` mean. `name` is None until one is known."""

    name: str | None
    source: Path | None


@dataclass(frozen=True)
class Placement:
    """Where the YAML goes: `kind` is `member` (in a project), `file` (`-o FILE`) or `stdout`."""

    kind: str
    yaml: Path | None = None
    name: str | None = None
    root: Path | None = None

    @property
    def is_member(self) -> bool:
        return self.kind == "member"

    @property
    def is_stdout(self) -> bool:
        return self.kind == "stdout"


def split_argument(token: str | None, source: Path | None) -> Argument:
    """Classify the positional token. An existing data file (or a path to one) is the source; anything else is a name.

    A token that names a data file which is not there stays "does not exist", as before, instead
    of becoming a pipeline called `missing.csv`.
    """
    if source is not None and not source.is_file():
        raise ScaffoldRefused(f"{source} does not exist.")
    if token is None:
        return Argument(None, source)
    is_data = token.lower().endswith(DATA_SUFFIXES)
    # An extensionless name that happens to match a file is still a name.
    if (Path(token).suffix or looks_like_path(token)) and os.path.isfile(token):
        if source is not None:
            raise ScaffoldRefused("Give the source file once: as the argument or with --source.")
        return Argument(None, Path(token))
    if is_data:
        raise ScaffoldRefused(f"{token} does not exist.")
    return Argument(token, source)


def member_placement(root: Path, name: str) -> Placement:
    """`pipelines/<name>/pipeline.yaml` of the project at `root`. Raises `LayoutError`."""
    if not is_valid_name(name):
        raise PIPELINE_NAME_INVALID.error(name=name)
    return Placement("member", member_yaml(root, name), name, root)


def place(argument: Argument, out: Path | None, explicit: Path | None) -> Placement:
    """The destination for `init`. Raises `LayoutError` (from `decoy.cli.io`) or `ScaffoldRefused`, before any prompt.

    `-o` wins and needs no project. Without it the selected project is required: a walk that
    found no marker never makes the folder the user stands in into a project.
    """
    if out is not None:
        if str(out) == "-":
            return Placement("stdout")
        return Placement("file", out, argument.name)
    project = find_project(None, explicit)
    if project.implicit:
        raise PROJECT_NOT_FOUND.error(where="the current folder")
    name = argument.name
    if name is None and argument.source is not None:
        name = name_slug(argument.source.stem)
        if not name:
            raise PIPELINE_NAME_INVALID.error(name=argument.source.stem)
    if name is None:
        return Placement("member", None, None, project.root)
    return member_placement(project.root, name)


def check_folder(destination: Placement) -> None:
    """Refuse a project pipeline that would be written through a link. Makes nothing.

    `pipelines/`, `pipelines/<name>/` and `pipeline.yaml` must not be links (a planted link would
    send the write outside the project), and the folder must resolve inside `pipelines/`.
    Raises `ScaffoldRefused`; the messages carry no OS text.
    """
    root = destination.root if destination.is_member else None
    if root is None or destination.name is None or destination.yaml is None:
        return
    escaped = False
    failed = False
    try:
        linked = member_has_link(root, destination.name)
        escaped = destination.yaml.parent.resolve().parent != (root / PIPELINES_DIR).resolve()
    except OSError:
        failed = True
        linked = False
    if failed:
        raise ScaffoldRefused("The pipeline folder could not be checked.")
    if linked or escaped:
        raise ScaffoldRefused(
            f"{PIPELINES_DIR}/{destination.name} is, or sits under, a link; init does not write "
            "through links."
        )


def prepare_folder(destination: Placement) -> None:
    """Check the destination, then make the folder the YAML goes in. Raises `ScaffoldRefused`."""
    assert destination.yaml is not None
    check_folder(destination)
    try:
        destination.yaml.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        failed = True
    else:
        failed = False
    if failed:
        raise ScaffoldRefused("The pipeline folder could not be made.")


def _relative(source: Path, base: Path) -> str | None:
    try:
        return Path(os.path.relpath(source.resolve(), base.resolve())).as_posix()
    except (OSError, ValueError):
        return None


def source_text(source: Path, destination: Placement) -> str:
    """The source path to write into the YAML.

    `-o FILE`: relative to FILE's folder, so `run` finds it. In a project: relative to the
    pipeline's folder when the source is inside the project, else absolute. Stdout has no
    folder, so the path stays as typed.
    """
    if destination.yaml is None:
        return source.as_posix()
    base = destination.yaml.parent
    if destination.is_member:
        root = destination.root
        inside = root is not None and root.resolve() in source.resolve().parents
        relative = _relative(source, base) if inside else None
    else:
        relative = _relative(source, base)
    return relative if relative is not None else str(source.resolve())


def target_text(source: Path, file_format: str) -> str:
    """The bare target `<stem>.masked.<ext>`; `run` places it in the pipeline's run folder."""
    ext = ".parquet" if file_format == "parquet" else ".csv"
    return f"{source.stem}.masked{ext}"


def _refuse(state: OutputState, failure: LayoutError | ScaffoldRefused) -> NoReturn:
    """Print a placement refusal (a `layout.*` code or fixed text) and exit 1."""
    emit_error(state, "init", failure.message, code=failure.code)
    raise typer.Exit(code=EXIT_USAGE)


def resolve_destination(
    state: OutputState,
    token: str | None,
    source: Path | None,
    out: Path | None,
    explicit: Path | None,
    *,
    check_source: Callable[[Path], object] | None,
) -> tuple[Argument, Placement]:
    """Settle what `init` writes and where, before anything is read, asked or written.

    `check_source` runs on a named source first (it exits on an unsupported file type). Inside a
    project with nothing to name the pipeline after, the wizard asks for the name; `--json` and
    `--quiet` cannot ask and exit 1. Exits 1 on any refusal.
    """
    refusal: LayoutError | ScaffoldRefused | None = None
    argument: Argument | None = None
    destination: Placement | None = None
    try:
        argument = split_argument(token, source)
    except ScaffoldRefused as exc:
        refusal = exc
    if refusal is None and argument is not None and argument.source is not None:
        if check_source is not None:
            check_source(argument.source)
    if refusal is None and argument is not None:
        try:
            destination = place(argument, out, explicit)
        except (LayoutError, ScaffoldRefused) as exc:
            refusal = exc
    if refusal is not None:
        _refuse(state, refusal)
    assert argument is not None and destination is not None
    if destination.is_member and destination.name is None and destination.root is not None:
        if state.mode is not OutputMode.default:
            emit_error(state, "init", "Give the pipeline a name: decoy init <name>.")
            raise typer.Exit(code=EXIT_USAGE)
        try:
            destination = member_placement(destination.root, typer.prompt("Pipeline name").strip())
        except LayoutError as exc:
            refusal = exc
        if refusal is not None:
            _refuse(state, refusal)
    # The link rule comes first, before an overwrite prompt, a source read or a fit: every init
    # path (mask scaffold, wizard, generate) passes through here. Folders are made later.
    prepare(state, destination, make=False)
    return argument, destination


def prepare(state: OutputState, destination: Placement, *, make: bool = True) -> None:
    """Check the destination and make its folder, or refuse with fixed text.

    `make=False` only checks: the generate scaffold makes its own folders, inside its rollback.
    """
    problem: ScaffoldRefused | None = None
    try:
        (prepare_folder if make else check_folder)(destination)
    except ScaffoldRefused as exc:
        problem = exc
    if problem is not None:
        _refuse(state, problem)


def placed_members(destination: Placement) -> dict[str, str]:
    """The `--json` members a project pipeline adds: its name and the project root."""
    if destination.is_member and destination.name and destination.root:
        return {"name": destination.name, "project": str(destination.root)}
    return {}


__all__ = [
    "DATA_SUFFIXES",
    "Argument",
    "Placement",
    "ScaffoldRefused",
    "member_placement",
    "place",
    "placed_members",
    "prepare",
    "prepare_folder",
    "resolve_destination",
    "source_text",
    "split_argument",
    "target_text",
]
