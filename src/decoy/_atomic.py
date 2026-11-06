"""The one atomic private file writer for the CLI.

The sequence is the standard durable replace: write a 0600 temp file on the same
volume, fsync it, move it onto the target, fsync the directory. Sources:
SQLite's rollback-journal commit and the ext4 documentation on rename and fsync
(data fsync, rename, directory fsync); `os.replace` as the successor to the
deprecated `atomicwrites` package (https://github.com/untitaker/python-atomicwrites);
the engine's `fileaccess.write_private` recipe, which this mirrors without the
engine's file-access policy so it runs on Windows. Local plan:
docs/plans/2026-11-05-local-record-library.md section 4.9.

Rules this module owns (see tests/sentry/test_atomic_writer.py, which fails when
`os.replace`, `os.rename`, `os.link` or `tempfile.mkstemp` appear elsewhere in
`src/decoy/` outside its allowlist):

* After any failure the target holds the old bytes or the new bytes, never
  neither, and no temp file is left behind.
* An error carries a fixed code and an errno, never a path (an `OSError` text
  names the path), and its cause is not chained.
* The caller's `name` passes an allowlist (portable on Windows and POSIX) before any
  file is made.
* `CREATE_ONCE` never replaces a file. Where the mount offers no atomic no-clobber
  move, it fails with `atomic_noclobber_unsupported` instead of checking then replacing.

Not covered: the vault commit in `cli/run.py`, which needs a hard-link backup
and rollback, and the install-directory swaps in `distribution/`. Both are
allowlisted with reasons.
"""

from __future__ import annotations

import contextlib
import enum
import errno
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

__all__ = [
    "ATOMIC_BAD_NAME",
    "ATOMIC_NOCLOBBER_UNSUPPORTED",
    "ATOMIC_SYNC_FAILED",
    "ATOMIC_WRITE_FAILED",
    "AtomicWriteError",
    "WriteMode",
    "fsync_directory",
    "write_atomic",
]

ATOMIC_WRITE_FAILED = "atomic_write_failed"
# The new bytes are in place but the directory entry may not be durable yet.
ATOMIC_SYNC_FAILED = "atomic_sync_failed"
ATOMIC_BAD_NAME = "atomic_name_invalid"
# CREATE_ONCE on a mount with no atomic no-clobber move (no hard links).
ATOMIC_NOCLOBBER_UNSUPPORTED = "atomic_noclobber_unsupported"

# One allowlist for every OS, so a name that is safe here is safe on Windows too. Windows
# also treats a device stem (CON, NUL, ...) as the device with or without an extension.
_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_DEVICE_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)

_WINDOWS = sys.platform == "win32"
_sleep = time.sleep  # a module attribute so tests can replace it

# 10 attempts, 9 sleeps: 10 ms doubling, capped at 160 ms, 950 ms in total.
_RETRY_ATTEMPTS = 10
_RETRY_FIRST_SECONDS = 0.010
_RETRY_CAP_SECONDS = 0.160

# `os.link` refusals that mean "this mount has no hard links" (some FUSE and exFAT
# mounts), as opposed to a real fault such as EXDEV or ENOSPC.
_NO_HARD_LINKS = frozenset(
    code
    for code in (
        errno.EPERM,
        errno.ENOSYS,
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
    )
    if code is not None
)


class WriteMode(enum.Enum):
    CREATE_ONCE = "create_once"  # never replace an existing target (records)
    REPLACE = "replace"  # replace the target in one step (refs, state, outputs)


class AtomicWriteError(Exception):
    """A failed atomic write. `code` is one of the ATOMIC_* constants; `errno` may be None.

    The text is the code alone. It never holds the directory, the name or the OS message.
    """

    def __init__(self, code: str, os_errno: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.errno = os_errno


def write_atomic(
    directory: Path,
    name: str,
    data: bytes,
    mode: WriteMode,
    *,
    tmp_dir: Path | None = None,
) -> bool:
    """Write `data` to `directory/name` atomically with owner-only permissions.

    `tmp_dir` holds the temp file and must be on the same volume as `directory`
    (default: `directory` itself). Returns True when this call put the bytes at the
    target. Returns False only for `CREATE_ONCE` when the target already existed; the
    caller then verifies the existing content (for a record, by its id) and treats a
    match as success. Raises `AtomicWriteError`.
    """
    _require_name(name)
    target = directory / name
    tmp: str | None = None
    failed_errno: int | None = None
    try:
        fd, tmp = tempfile.mkstemp(dir=tmp_dir or directory, prefix=".", suffix=".tmp")
        _write_and_sync(fd, data)
        created = _move_into_place(tmp, target, mode)
        if created:
            _sync_directories(directory, tmp_dir)
        return created
    except OSError as exc:
        failed_errno = exc.errno
    finally:
        # Runs on every exit, including KeyboardInterrupt. After a successful replace the
        # temp name is gone; after a successful link it still names the second hard link.
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    # Raised outside the except block so the OSError (its text names the path) is not
    # kept as `__context__`.
    raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)


def _require_name(name: str) -> None:
    stem = name.split(".", 1)[0].upper()
    ok = (
        _NAME_PATTERN.fullmatch(name) is not None
        and not name.endswith(".")
        and stem not in _DEVICE_STEMS
        and PureWindowsPath(name).name == PurePosixPath(name).name == name
    )
    if not ok:
        raise AtomicWriteError(ATOMIC_BAD_NAME)


def _write_and_sync(fd: int, data: bytes) -> None:
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _move_into_place(tmp: str, target: Path, mode: WriteMode) -> bool:
    if mode is WriteMode.REPLACE:
        _retry_on_windows(lambda: os.replace(tmp, target))
        return True
    return _create_once(tmp, target)


def _create_once(tmp: str, target: Path) -> bool:
    """Move `tmp` to `target` only if `target` does not exist; no check-then-act window."""
    no_hard_links: int | None = None
    try:
        if _WINDOWS:
            # os.rename fails on Windows when the target exists, which is the no-clobber move.
            _retry_on_windows(lambda: os.rename(tmp, target))
        else:
            os.link(tmp, target)
    except FileExistsError:
        return False
    except OSError as exc:
        if _WINDOWS or exc.errno not in _NO_HARD_LINKS:
            raise
        no_hard_links = exc.errno
    else:
        return True
    # No hard links on this mount and no other atomic no-clobber primitive: refuse. The
    # raise sits outside the except block so no OSError is chained.
    raise AtomicWriteError(ATOMIC_NOCLOBBER_UNSUPPORTED, no_hard_links)


def _retry_on_windows(move: Callable[[], None]) -> None:
    """Run `move`, retrying a PermissionError (target briefly held open) on Windows only."""
    delay = _RETRY_FIRST_SECONDS
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            move()
            return
        except PermissionError:
            if not _WINDOWS or attempt == _RETRY_ATTEMPTS - 1:
                raise
            _sleep(delay)
            delay = min(delay * 2, _RETRY_CAP_SECONDS)


def fsync_directory(directory: Path) -> None:
    """Make a rename or unlink in `directory` durable. Raises plain `OSError`.

    Windows cannot open a directory and NTFS journals the rename, so it does nothing there.
    """
    if _WINDOWS:
        return
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_directories(directory: Path, tmp_dir: Path | None) -> None:
    """Sync the target directory, and the temp directory when it is a different one."""
    targets = [directory] if tmp_dir is None or tmp_dir == directory else [directory, tmp_dir]
    failed_errno: int | None = None
    failed = False
    try:
        for each in targets:
            fsync_directory(each)
    except OSError as exc:
        failed, failed_errno = True, exc.errno
    if failed:
        raise AtomicWriteError(ATOMIC_SYNC_FAILED, failed_errno)
