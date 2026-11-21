"""Where the library lives (`resolve_root`), the names inside it, and the Windows path budget.

Root order (plan 4.1 with PROJECT-LAYOUT LIB-A; re-FRAME owner answers Q1 to Q3): `--library
DIR`, then `DECOY_LIBRARY` (`off` turns records off for the process), then the project root's
`.decoy/` from `decoy.cli.io.find_project`, the one project-root finder. The walk starts at the
pipeline YAML's folder for `run`, at the `--emit-config` folder then the `--config` folder for
`scan`, else at the current folder. Under `off` the job-log root is the same chain with the env
step skipped. Records sit next to the project, as `.git/`, `.dvc/` and dbt's `target/` do.

The `.decoy` folder name is `decoy.cli.io.DECOY_DIR`; this module owns only the names below it.

Windows budget (plan 4.2): the deepest record path is the root plus `library\\objects\\ab\\`, 62 hex
digits and `.json` (about 87 characters), so a root over 150 characters is refused with
`library_path_too_long` before any write, well inside `MAX_PATH` (260).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from decoy.cli.io import DECOY_DIR, find_project
from decoy.cli.library._errors import LIBRARY_PATH_TOO_LONG, LIBRARY_PATH_UNSAFE, LibraryError
from decoy.cli.library._fs import Entry, anchor, entries

__all__ = [
    "ENV_VAR",
    "GITATTRIBUTES",
    "GITATTRIBUTES_TEXT",
    "INDEX_FILE",
    "LAYOUT_FILE",
    "LAYOUT_VERSION",
    "LIBRARY",
    "LOGS",
    "MAX_ROOT_CHARS",
    "OBJECTS",
    "OFF",
    "POLICY_FILE",
    "QUARANTINE",
    "REFS",
    "SCRATCH",
    "TMP",
    "LibraryRoot",
    "check_root_budget",
    "is_project_folder",
    "record_digest",
    "resolve_project_root",
    "resolve_root",
]

LIBRARY = "library"
OBJECTS = "objects"
REFS = "refs"
TMP = "tmp"
QUARANTINE = "quarantine"
LOGS = "logs"
SCRATCH = "scratch"
LAYOUT_FILE = "LAYOUT"
# The rebuildable index (L1c); until then it holds only the library lock (plan L1b behavior).
INDEX_FILE = "index.sqlite"
# The optional retention policy beside `library/` (plan 4.7).
POLICY_FILE = "library.yaml"
LAYOUT_VERSION = 1
GITATTRIBUTES = ".gitattributes"
# Records are hashed after parsing, but git must still never rewrite their line endings.
GITATTRIBUTES_TEXT = f"{LIBRARY}/{OBJECTS}/** -text\n"

ENV_VAR = "DECOY_LIBRARY"
OFF = "off"
MAX_ROOT_CHARS = 150
_WINDOWS = sys.platform == "win32"  # a module attribute so tests can force the budget


@dataclass(frozen=True)
class LibraryRoot:
    """The resolved root. `records` is False under `DECOY_LIBRARY=off`; `path` is then the root
    the job log still uses."""

    path: Path
    records: bool
    source: Literal["flag", "env", "project"]


def resolve_root(
    *,
    flag: Path | None = None,
    pipeline: Path | None = None,
    emit_config: Path | None = None,
    config: Path | None = None,
    project: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> LibraryRoot:
    """The library root for one command.

    `flag` is `--library`; `pipeline` is `run`'s YAML; `emit_config` and `config` are `scan`'s;
    `project` is `--project` or `DECOY_PROJECT`. Raises `LayoutError` from the project finder.
    """
    env = (os.environ if environ is None else environ).get(ENV_VAR, "")
    if flag is not None:
        return LibraryRoot(anchor(flag), True, "flag")
    if env and env != OFF:
        return LibraryRoot(anchor(Path(env)), True, "env")
    yaml = next((p for p in (pipeline, emit_config, config) if p is not None), None)
    start = anchor(yaml).parent if yaml is not None else None
    root = find_project(start, project).root / DECOY_DIR
    return LibraryRoot(root, env != OFF, "project")


def resolve_project_root(project: Path) -> LibraryRoot:
    """The library root of a found project: `<project>/.decoy`, whatever `DECOY_LIBRARY` says.

    For a command whose files must stay inside the project (a sample's scratch folder). It is
    a named mode of this resolver, so no caller rebuilds the path itself.
    """
    return LibraryRoot(Path(project) / DECOY_DIR, True, "project")


def check_root_budget(root: Path) -> None:
    """Refuse a root too long for the deepest record path on Windows; a no-op elsewhere."""
    if _WINDOWS and len(os.path.abspath(root)) > MAX_ROOT_CHARS:
        raise LibraryError(LIBRARY_PATH_TOO_LONG)


def is_project_folder(root: Path) -> bool:
    """A root named `.decoy` sits in a project work tree and gets the git files."""
    return root.name == DECOY_DIR


ID_PREFIX = "sha256:"
_HEX = frozenset("0123456789abcdef")
_DIGEST_CHARS = 64
_MIN_PREFIX = 8  # as git allows abbreviated object names


def record_digest(record_id: str) -> str | None:
    """The 64 hex digits of a full record id, or None when it is not one (so no path is built
    from it). Object files are named from these digits."""
    digest = record_id.removeprefix(ID_PREFIX) if record_id.startswith(ID_PREFIX) else ""
    return digest if len(digest) == _DIGEST_CHARS and set(digest) <= _HEX else None


OBJECT_SUFFIX = ".json"


def object_path(objects_dir: Path, digest: str) -> Path:
    """Where the record with these 64 hex digits lives: `objects/ab/<62 hex>.json` (git's fan)."""
    return objects_dir / digest[:2] / f"{digest[2:]}{OBJECT_SUFFIX}"


def id_from_name(fan: str, name: str) -> str | None:
    """The one rule from an object's fan folder and file name to its record id; None when the
    pair is not an object name (no path or id is built from anything else)."""
    if not name.endswith(OBJECT_SUFFIX):
        return None
    candidate = f"{ID_PREFIX}{fan}{name[: -len(OBJECT_SUFFIX)]}"
    return candidate if record_digest(candidate) is not None else None


@dataclass(frozen=True)
class ObjectEntry:
    """One entry under `objects/`: its id by the name rule (None for a stray name) and what is
    there, judged without following it; `entry` is None for a folder that cannot be listed."""

    path: Path
    record_id: str | None
    entry: Entry | None

    @property
    def stored(self) -> bool:
        """A record file the library can read: a real file with an object name."""
        return self.record_id is not None and self.entry is not None and self.entry.kind == "file"


def object_entries(root: Path, objects_dir: Path) -> Iterator[ObjectEntry]:
    """The one walk of `objects/`: every fan folder and every entry in it, through `_fs`.

    A linked fan folder or object is yielded as a `link` entry and never entered; a folder that
    cannot be listed is yielded with no entry and the walk goes on. A missing `objects/` is
    empty; a linked one is `library_path_unsafe`.
    """
    try:
        fans = entries(root, objects_dir) or []
    except LibraryError as exc:
        if exc.code == LIBRARY_PATH_UNSAFE:
            raise
        yield ObjectEntry(objects_dir, None, None)
        return
    for fan in fans:
        if fan.kind != "dir":
            yield ObjectEntry(fan.path, None, fan)
            continue
        try:
            items = entries(root, fan.path) or []
        except LibraryError:
            yield ObjectEntry(fan.path, None, None)
            continue
        for item in items:
            yield ObjectEntry(item.path, id_from_name(fan.name, item.name), item)


def record_prefix(text: str) -> str | None:
    """The hex digits of an id or an abbreviation of one (8 to 64 lowercase hex digits, with or
    without `sha256:`), or None when `text` is neither. The one rule beside `record_digest`."""
    digits = text.removeprefix(ID_PREFIX)
    return digits if _MIN_PREFIX <= len(digits) <= _DIGEST_CHARS and set(digits) <= _HEX else None
