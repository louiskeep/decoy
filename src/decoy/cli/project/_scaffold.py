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
import re
from dataclasses import dataclass
from pathlib import Path

from decoy.cli.io import (
    PIPELINE_NAME_INVALID,
    PIPELINES_DIR,
    PROJECT_NOT_FOUND,
    find_project,
    is_valid_name,
    member_yaml,
)

DATA_SUFFIXES = (".csv", ".tsv", ".parquet", ".pq")
_NAME_MAX = 56
_BAD_NAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


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
    """Classify the positional token. An existing file is the source; anything else is a name.

    A token that names a data file which is not there stays "does not exist", as before, instead
    of becoming a pipeline called `missing.csv`.
    """
    if source is not None and not source.is_file():
        raise ScaffoldRefused(f"{source} does not exist.")
    if token is None:
        return Argument(None, source)
    if os.path.isfile(token):
        if source is not None:
            raise ScaffoldRefused("Give the source file once: as the argument or with --source.")
        return Argument(None, Path(token))
    if token.lower().endswith(DATA_SUFFIXES):
        raise ScaffoldRefused(f"{token} does not exist.")
    return Argument(token, source)


def _slug(stem: str) -> str:
    return _BAD_NAME_CHARS.sub("-", stem).strip("-._")[:_NAME_MAX].rstrip("-.")


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
        name = _slug(argument.source.stem)
        if not name:
            raise PIPELINE_NAME_INVALID.error(name=argument.source.stem)
    if name is None:
        return Placement("member", None, None, project.root)
    return member_placement(project.root, name)


def prepare_folder(destination: Placement) -> None:
    """Make the folder the YAML goes in. A member folder must stay inside `pipelines/`.

    Raises `ScaffoldRefused`. The messages carry no OS text.
    """
    assert destination.yaml is not None
    folder = destination.yaml.parent
    failed = False
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if destination.is_member and destination.root is not None:
            inside = (destination.root / PIPELINES_DIR).resolve()
            escaped = folder.resolve().parent != inside
        else:
            escaped = False
    except OSError:
        failed = True
        escaped = False
    if failed:
        raise ScaffoldRefused("The pipeline folder could not be made.")
    if escaped:
        raise ScaffoldRefused(f"{PIPELINES_DIR}/{destination.name} is a link to another folder.")


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


__all__ = [
    "DATA_SUFFIXES",
    "Argument",
    "Placement",
    "ScaffoldRefused",
    "member_placement",
    "place",
    "prepare_folder",
    "source_text",
    "split_argument",
    "target_text",
]
