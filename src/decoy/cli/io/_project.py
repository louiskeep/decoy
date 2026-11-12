"""The one project-root finder: `decoy.yaml` markers, trust, and the `.decoy/` folder.

A project is a folder holding `decoy.yaml` with `kind: decoy-project/v1`. `find_project` is the
only function that looks for that file (`tests/sentry/io_policy/test_pipeline_argument.py`
holds the line). The trust rule follows git's `safe.directory`: a marker is read through
`_small_file.read_small_file` (no links, pipes or devices; judged on the opened descriptor, so a
swap between check and read cannot pass) and must belong to the effective user.
`read_owned_yaml` is that trusted read, shared with the library's `library.yaml` policy.
"""

from __future__ import annotations

import errno
import os
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
from decoy.cli.io._small_file import UnsafeFileError, read_small_file

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


class OwnedYamlError(Exception):
    """A small YAML file that cannot be trusted. `reason` is `"unsafe"` (not a plain regular
    file, over the cap, unreadable or not YAML) or `"untrusted"` (another user owns it). The
    text is the reason alone: the file's path and contents never reach it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OwnedYaml:
    """The parsed content of a trusted small YAML file (`None` for an empty one)."""

    parsed: object


def read_owned_yaml(path: Path, max_bytes: int) -> OwnedYaml | None:
    """Read and parse a small YAML file the current user owns; None when nothing is there.

    The one reader for Decoy's own YAML bookkeeping files (the project marker and the library
    policy): `read_small_file` (no links, pipes or devices), a size cap, the owner rule (git's
    `safe.directory`: a file another user owns is not trusted) and `yaml.safe_load`. Raises
    `OwnedYamlError`, never chained to the OS or parser error (their text holds the path or the
    file's contents).
    """
    unsafe = False
    found = None
    try:
        found = read_small_file(path, max_bytes + 1)
    except UnsafeFileError:
        unsafe = True
    if unsafe or (found is not None and found.size > max_bytes):
        raise OwnedYamlError("unsafe")
    if found is None:
        return None
    if hasattr(os, "geteuid") and found.uid != os.geteuid():
        raise OwnedYamlError("untrusted")
    parsed: object = None
    broken = False
    try:
        parsed = yaml.safe_load(found.data)
    except (yaml.YAMLError, UnicodeDecodeError, RecursionError):
        broken = True
    if broken:
        raise OwnedYamlError("unsafe")
    return OwnedYaml(parsed)


def _read_marker(marker: Path) -> OwnedYaml | None:
    """The marker's parsed YAML, None when there is no file, or a layout refusal."""
    reason: str | None = None
    found = None
    try:
        found = read_owned_yaml(marker, MAX_MARKER_BYTES)
    except OwnedYamlError as exc:
        reason = exc.reason
    # Raised outside the handler so no error is chained onto the refusal.
    if reason == "untrusted":
        raise PROJECT_MARKER_UNTRUSTED.error(path=marker)
    if reason is not None:
        raise PROJECT_MARKER_INVALID.error(path=marker)
    return found


def _parse_marker(marker: Path, parsed: object) -> dict[object, object] | None:
    """The marker mapping, None for a YAML mapping with no `kind` (not a marker)."""
    if not isinstance(parsed, dict):
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
    found = _read_marker(marker)
    parsed = None if found is None else _parse_marker(marker, found.parsed)
    if found is None:
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
        found = _read_marker(marker)
        if found is not None:
            parsed = _parse_marker(marker, found.parsed)
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
