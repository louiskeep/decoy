"""Run folders under `<project>/out/<name>/<run-id>/`: the run-id rule and path placement.

One place owns what a run id looks like (`is_run_id`), how a file is matched to the run
folder that holds it (`owning_run`), and how a declared relative path is placed inside a
run folder (`placed_path`). Writers and readers both go through these.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

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
    """`raw` placed inside `run`, normalized, or None when it is absolute or leaves the run.

    The path may not climb above the run folder at any step, even to come back in: `..`
    followed by the run's own name is a path into the pipeline folder, not a placed one.
    """
    if Path(raw).is_absolute():
        return None
    depth = 0
    for part in Path(raw).parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return None
        elif part != ".":
            depth += 1
    if depth == 0:
        return None
    return Path(os.path.normpath(run.path / raw))
