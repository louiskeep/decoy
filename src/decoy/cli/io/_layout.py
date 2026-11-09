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


def owning_run(path: Path, root: Path, name: str) -> RunFolder | None:
    """The run folder of pipeline `name` in project `root` that holds `path`, else None.

    `path` is resolved first, so a `latest` link is followed and a link that leaves the run
    folder is judged by where it lands. The run folder itself holds no file and gives None.
    """
    base = (root / "out" / name).resolve()
    try:
        parts = path.resolve().relative_to(base).parts
    except ValueError:
        return None
    if len(parts) < 2 or not is_run_id(parts[0]):
        return None
    return RunFolder(base / parts[0], parts[0])


def placed_path(run: RunFolder, raw: str) -> Path | None:
    """`raw` placed inside `run` and resolved, or None when it does not stay inside.

    Refused: an anchor or drive in either path style (`/x`, `\\x`, `C:x`, `//host/share/x`), a
    trailing separator (a directory, not a file), a `..` that climbs above the run at any
    step (even to come back in), and a result that resolves outside the run through an
    existing symlink. The result is resolved, so it compares with a resolved input path.
    """
    if not raw or raw.endswith(("/", "\\")):
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
    resolved = Path(os.path.normpath(run.path / raw)).resolve()
    try:
        inside = resolved.relative_to(run.path.resolve()).parts
    except ValueError:
        return None
    return resolved if inside else None
