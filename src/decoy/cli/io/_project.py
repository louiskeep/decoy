"""The one project-root finder: `decoy.yaml` markers, trust, and the `.decoy/` folder.

A project is a folder holding `decoy.yaml` with `kind: decoy-project/v1`. `find_project` is the
only function that looks for that file (`tests/sentry/io_policy/test_pipeline_argument.py`
holds the line). The trust rule follows git's `safe.directory`: a marker is opened with
`O_NOFOLLOW`, judged on the opened descriptor (so a swap between check and read cannot pass),
and must belong to the effective user.
"""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import yaml

from decoy._atomic import AtomicWriteError, WriteMode, write_local_target
from decoy.cli.io._layout_errors import (
    GITIGNORE_WRITE_FAILED,
    PROJECT_MARKER_INVALID,
    PROJECT_MARKER_UNTRUSTED,
    PROJECT_NOT_FOUND,
    LayoutWarning,
)

MARKER_NAME = "decoy.yaml"
MARKER_KIND = "decoy-project/v1"
DECOY_DIR = ".decoy"
MAX_MARKER_BYTES = 64 * 1024
# What the local record library keeps out of git; records and baselines stay committable.
DECOY_DIR_GITIGNORE = "scratch/\nlogs/\nlibrary/index.sqlite\nlibrary/tmp/\nlibrary/quarantine/\n"


@dataclass(frozen=True)
class Project:
    """The project a command works in.

    `implicit` is True when no marker was found and `root` is the start folder. `skipped` lists
    `decoy.yaml` files with no `kind` key met on the walk (pipelines someone named that).
    `extra_keys` are marker keys other than `kind`, reserved and ignored.
    """

    root: Path
    implicit: bool = False
    skipped: tuple[Path, ...] = ()
    extra_keys: tuple[str, ...] = ()


def _device(path: Path) -> int | None:
    try:
        return os.stat(path).st_dev
    except OSError:
        return None


def _home() -> Path | None:
    try:
        return Path(os.path.expanduser("~")).resolve()
    except (OSError, RuntimeError):
        return None


def _read_marker_bytes(marker: Path) -> bytes | None:
    """The marker's bytes, None when there is no file, or a refusal for an unsafe one."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    failure: Exception | None = None
    data: bytes | None = None
    try:
        fd = os.open(marker, flags)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        fd = -1
        failure = PROJECT_MARKER_INVALID.error(path=marker)
    if fd >= 0:
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MARKER_BYTES:
                failure = PROJECT_MARKER_INVALID.error(path=marker)
            elif hasattr(os, "geteuid") and info.st_uid != os.geteuid():
                failure = PROJECT_MARKER_UNTRUSTED.error(path=marker)
            else:
                data = os.read(fd, MAX_MARKER_BYTES + 1)
        except OSError:
            failure = PROJECT_MARKER_INVALID.error(path=marker)
        finally:
            os.close(fd)
    if failure is not None:
        raise failure
    return data


def _parse_marker(marker: Path, data: bytes) -> dict[object, object] | None:
    """The marker mapping, None for a YAML mapping with no `kind` (not a marker)."""
    parsed: object = None
    broken = False
    try:
        parsed = yaml.safe_load(data)
    except (yaml.YAMLError, UnicodeDecodeError, RecursionError):
        broken = True
    if broken or not isinstance(parsed, dict):
        raise PROJECT_MARKER_INVALID.error(path=marker)
    if "kind" not in parsed:
        return None
    if parsed["kind"] != MARKER_KIND:
        raise PROJECT_MARKER_INVALID.error(path=marker)
    return parsed


def _extra(parsed: dict[object, object]) -> tuple[str, ...]:
    return tuple(sorted(str(k) for k in parsed if k != "kind"))


def _explicit_project(explicit: Path) -> Project:
    root = explicit.resolve()
    marker = root / MARKER_NAME
    data = _read_marker_bytes(marker)
    parsed = None if data is None else _parse_marker(marker, data)
    if data is None:
        raise PROJECT_NOT_FOUND.error(where=root)
    if parsed is None:
        raise PROJECT_MARKER_INVALID.error(path=marker)
    return Project(root=root, extra_keys=_extra(parsed))


def find_project(start: Path | None, explicit: Path | None) -> Project:
    """The project for a command.

    `explicit` (from `--project` or `DECOY_PROJECT`) must hold a valid trusted marker; no walk.
    Otherwise walk from `start` (the current folder when None), resolved: check it and each
    parent for a marker. The walk ends after the folder holding `.git` (a folder or a file), at a
    device change, and before `$HOME` when `start` is under it (`$HOME` is never a root). With no
    marker the start folder is an implicit root. Raises `LayoutError`.
    """
    if explicit is not None:
        return _explicit_project(explicit)
    begin = (Path.cwd() if start is None else start).resolve()
    home = _home()
    under_home = home is not None and (begin == home or home in begin.parents)
    skipped: list[Path] = []
    for folder in (begin, *begin.parents):
        if under_home and folder == home:
            break
        marker = folder / MARKER_NAME
        data = _read_marker_bytes(marker)
        if data is not None:
            parsed = _parse_marker(marker, data)
            if parsed is not None:
                return Project(root=folder, skipped=tuple(skipped), extra_keys=_extra(parsed))
            skipped.append(marker)
        if os.path.lexists(folder / ".git"):
            break
        parent = folder.parent
        if parent != folder and _device(folder) != _device(parent):
            break
    return Project(root=begin, implicit=True, skipped=tuple(skipped))


def ensure_decoy_dir(root: Path) -> tuple[LayoutWarning, ...]:
    """Make `<root>/.decoy/` and its `.gitignore` when absent; the one writer of both.

    An existing `.gitignore` is kept (the user may have edited it). A `.gitignore` that cannot
    be written is a warning, not a failure. An unmakeable folder raises `OSError`.
    """
    folder = root / DECOY_DIR
    folder.mkdir(exist_ok=True)
    target = folder / ".gitignore"
    problem = False
    try:
        write_local_target(target, DECOY_DIR_GITIGNORE.encode(), WriteMode.CREATE_ONCE)
    except AtomicWriteError as exc:
        problem = exc.errno != errno.EEXIST
    if problem:
        return (GITIGNORE_WRITE_FAILED.warning(path=target),)
    return ()
