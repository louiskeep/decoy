"""Run folders under `<project>/out/<name>/<run-id>/`: the run-id rule and path placement.

One place owns what a run id looks like (`is_run_id`), how a file is matched to the run
folder that holds it (`owning_run`), and how a declared relative path is placed inside a
run folder (`placed_path`). Writers and readers both go through these.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

# <UTC start YYYYMMDDTHHMMSSffffffZ>-<8 hex of the invocation id>, plus 4 more hex digits per
# clash, up to all 32.
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}(?:[0-9a-f]{4}){0,6}")


def is_run_id(value: str) -> bool:
    """True when `value` is a well-formed run folder name."""
    return _RUN_ID.fullmatch(value) is not None


@dataclass(frozen=True)
class RunFolder:
    """A run folder `<root>/out/<name>/<run-id>/`, fully resolved."""

    path: Path
    run_id: str


def same_path(a: Path, b: Path) -> bool:
    """True when both paths name one file: by identity when both exist, else by resolved text.

    Identity, not spelling, so a case-insensitive filesystem or a second path to the same
    directory does not split one file in two. Unresolvable paths (a loop, an I/O error) are
    never the same.
    """
    try:
        return os.path.samefile(a, b)
    except OSError:
        pass
    try:
        return a.resolve() == b.resolve()
    except (OSError, RuntimeError):
        return False


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def owning_run(path: Path, root: Path, name: str) -> RunFolder | None:
    """The run folder of pipeline `name` in project `root` that holds `path`, else None.

    `path` is resolved first, so a `latest` link is followed and a link that leaves the run
    folder is judged by where it lands. A run folder is found by identity: the ancestor of
    the file whose parent is the pipeline folder. The run folder itself holds no file and
    gives None. An unresolvable path gives None.
    """
    try:
        base = (root / "out" / name).resolve()
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None
    for ancestor in resolved.parents:
        if _same_dir(ancestor.parent, base):
            if not is_run_id(ancestor.name):
                return None
            return RunFolder(base / ancestor.name, ancestor.name)
    return None


def placed_path(run: RunFolder, raw: str) -> Path | None:
    """`raw` placed inside `run` and resolved, or None when it does not stay inside.

    Refused: any backslash (a declared path uses "/" only, so it means the same on every
    OS), an anchor or drive (`/x`, `C:x`, `//host/share/x`), a trailing separator (a
    directory, not a file), a `..` that climbs above the run at any step (even to come back
    in), and a result that lands outside the run through an existing symlink. Containment is
    by file identity, so another spelling of the run folder still counts. The result is
    resolved, so it compares with a resolved input path. A path that cannot be resolved
    gives None.
    """
    if not raw or "\\" in raw or raw.endswith("/"):
        return None
    for style in (PurePosixPath, PureWindowsPath):
        pure = style(raw)
        if pure.anchor or pure.drive:
            return None
    depth = 0
    for part in PurePosixPath(raw).parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return None
        elif part != ".":
            depth += 1
    if depth == 0:
        return None
    try:
        resolved = Path(os.path.normpath(run.path / raw)).resolve()
    except (OSError, RuntimeError):
        return None
    if any(_same_dir(ancestor, run.path) for ancestor in resolved.parents):
        return resolved
    return None
