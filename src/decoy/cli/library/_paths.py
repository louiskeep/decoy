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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from decoy.cli.io import DECOY_DIR, find_project
from decoy.cli.library._errors import LIBRARY_PATH_TOO_LONG, LibraryError

__all__ = [
    "ENV_VAR",
    "GITATTRIBUTES",
    "GITATTRIBUTES_TEXT",
    "LAYOUT_FILE",
    "LAYOUT_VERSION",
    "LIBRARY",
    "LOGS",
    "MAX_ROOT_CHARS",
    "OBJECTS",
    "OFF",
    "QUARANTINE",
    "REFS",
    "SCRATCH",
    "TMP",
    "LibraryRoot",
    "check_root_budget",
    "is_project_folder",
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
        return LibraryRoot(flag.resolve(), True, "flag")
    if env and env != OFF:
        return LibraryRoot(Path(env).resolve(), True, "env")
    yaml = next((p for p in (pipeline, emit_config, config) if p is not None), None)
    start = yaml.resolve().parent if yaml is not None else None
    root = find_project(start, project).root / DECOY_DIR
    return LibraryRoot(root, env != OFF, "project")


def check_root_budget(root: Path) -> None:
    """Refuse a root too long for the deepest record path on Windows; a no-op elsewhere."""
    if _WINDOWS and len(os.path.abspath(root)) > MAX_ROOT_CHARS:
        raise LibraryError(LIBRARY_PATH_TOO_LONG)


def is_project_folder(root: Path) -> bool:
    """A root named `.decoy` sits in a project work tree and gets the git files."""
    return root.name == DECOY_DIR
