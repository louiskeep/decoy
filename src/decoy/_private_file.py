"""The one place the CLI creates owner-only files and changes file modes.

`_atomic` publishes (rename, fsync); this module creates and narrows. Keeping every mode call
here means one module changes when Windows gets real ACLs: `apply_mode`, `create_exclusive`
and `open_private` are the three functions to replace. Today the Windows branch keeps the
documented behavior, a file that inherits its folder's permissions.

The creation recipe mirrors the engine's `fileaccess/_private.py` (exclusive create, no
symlink at the created name, narrow by descriptor) without its file-access policy, so it runs
where the CLI runs. Sources: POSIX `open` and `umask` (a create mode can only lose bits to the
umask, never gain them), CERT FIO15-C and CPython `tempfile._mkstemp_inner` for
`O_EXCL | O_NOFOLLOW`, CERT FIO01-C for narrowing a descriptor instead of a path.

Rules this module owns:

* The low-level functions raise plain `OSError` (errno set), so `_atomic` keeps mapping every
  failure to `AtomicWriteError` through the handlers it already has. Only the standalone entry
  points (`open_private`, `create_private_temp`) raise `PrivateFileError`.
* An error carries a code and an errno, never a path (an `OSError` text names the path), and
  it is raised outside the `except` block so no `OSError` is chained to it.
* This module imports nothing from `decoy`, so `_atomic` can import it without a cycle.
"""

from __future__ import annotations

import contextlib
import errno
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path

__all__ = [
    "PRIVATE_EXISTS",
    "PRIVATE_MODE_FAILED",
    "PRIVATE_OPEN_FAILED",
    "PrivateFileError",
    "apply_mode",
    "create_exclusive",
    "create_private_directory",
    "create_private_temp",
    "open_private",
    "restrict_owner_only",
]

PRIVATE_OPEN_FAILED = "private_open_failed"
PRIVATE_MODE_FAILED = "private_mode_failed"
PRIVATE_EXISTS = "private_exists"

_WINDOWS = sys.platform == "win32"
_OWNER_FILE = 0o600
_OWNER_DIR = 0o700
_FALLBACK_NAME_MAX = 255


class PrivateFileError(OSError):
    """A failed standalone private-file step. `code` is a PRIVATE_* constant.

    `errno` is set and `filename` is not, so a caller that catches `OSError` still catches it
    and the text is the code alone.
    """

    def __init__(self, code: str, os_errno: int | None = None) -> None:
        super().__init__(os_errno, code)
        self.code = code

    def __str__(self) -> str:
        return self.code


class _ModeError(OSError):
    """Narrowing failed after the file was created; lets `create_private_temp` name the step."""


def apply_mode(fd: int, path: str, bits: int) -> None:
    """The one mode call. POSIX changes the descriptor; Windows has no fchmod and uses the path.

    Raises plain `OSError`.
    """
    if _WINDOWS:
        os.chmod(path, bits)
    else:
        os.fchmod(fd, bits)


def restrict_owner_only(fd: int, path: str, *, directory: bool = False) -> None:
    """Make the open file or directory owner-only. Raises plain `OSError`.

    On POSIX the mode is read back, because a filesystem that ignores `fchmod` (some FUSE and
    network mounts) would otherwise leave group or other bits on a file meant to be private.
    """
    apply_mode(fd, path, _OWNER_DIR if directory else _OWNER_FILE)
    if _WINDOWS:
        return
    if stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
        raise OSError(errno.EPERM, "mode did not stick")


def _temp_name(base: str, parent: Path) -> str:
    """`.<base>.decoy-<hex>.tmp`, with `base` cut by whole characters to fit the filesystem."""
    try:
        limit = os.pathconf(parent, "PC_NAME_MAX")
    except (AttributeError, ValueError, OSError):
        limit = _FALLBACK_NAME_MAX
    suffix = f".decoy-{secrets.token_hex(8)}.tmp"
    while len(os.fsencode(f".{base}{suffix}")) > limit and base:
        base = base[:-1]
    return f".{base}{suffix}"


def create_exclusive(parent: Path, base: str, *, private: bool) -> tuple[str, int]:
    """Create a staging file exclusively and narrow it to owner-only while it is written.

    Returns its path and the mode bits the create gave it (before narrowing), which a public
    write uses as the mode of a new file. `O_EXCL | O_NOFOLLOW` means a planted entry at the
    random name is a collision, so the loop retries with a fresh name. If narrowing fails the
    file is closed and removed here, because the caller has no name to clean up yet.
    Raises plain `OSError`.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    while True:
        tmp = str(parent / _temp_name(base, parent))
        try:
            fd = os.open(tmp, flags, _OWNER_FILE if private else 0o666)
        except FileExistsError:
            continue
        break
    failed_errno: int | None = None
    failed = False
    bits = 0
    try:
        bits = stat.S_IMODE(os.fstat(fd).st_mode) & 0o777
        # A restrictive umask must not lock the writer out, so the bits are set, not just kept.
        # No read-back: a mount where chmod does nothing must still stage a public output.
        apply_mode(fd, tmp, _OWNER_FILE)
    except OSError as exc:
        failed, failed_errno = True, exc.errno
    finally:
        os.close(fd)
    if failed:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise _ModeError(failed_errno or errno.EPERM, PRIVATE_MODE_FAILED)
    return tmp, bits


def open_private(path: Path, *, new_parent: bool, truncate: bool = False) -> None:
    """Create `path` if missing and leave it owner-only, for a writer that opens it itself.

    Opens with `O_NOFOLLOW`, so a symlink at `path` is refused (`ELOOP`). An existing file
    that an earlier build left wider is repaired. A parent directory this call's caller just
    created is narrowed to 0700 through its own descriptor. `truncate` empties an existing file
    in place (`O_TRUNC`): the same inode, so a lock other processes take on it stays one lock.
    Raises `PrivateFileError`.
    """
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    if truncate:
        flags |= os.O_TRUNC
    code: str | None = None
    failed_errno: int | None = None
    try:
        fd = os.open(path, flags, _OWNER_FILE)
        try:
            restrict_owner_only(fd, str(path))
        except OSError as exc:
            code, failed_errno = PRIVATE_MODE_FAILED, exc.errno
        finally:
            os.close(fd)
        if code is None and new_parent:
            _restrict_directory(path.parent)
    except _ModeError as exc:
        code, failed_errno = PRIVATE_MODE_FAILED, exc.errno
    except OSError as exc:
        code, failed_errno = PRIVATE_OPEN_FAILED, exc.errno
    if code is not None:
        raise PrivateFileError(code, failed_errno)


def _restrict_directory(directory: Path) -> None:
    """Narrow a directory by descriptor; Windows cannot open one, so it goes by path."""
    if _WINDOWS:
        apply_mode(-1, str(directory), _OWNER_DIR)
        return
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
    try:
        restrict_owner_only(fd, str(directory), directory=True)
    except OSError as exc:
        raise _ModeError(exc.errno or errno.EPERM, PRIVATE_MODE_FAILED) from None
    finally:
        os.close(fd)


def _narrow_new_directory(path: Path) -> None:
    """Narrow a directory this process just made.

    A umask that strips the owner's bits leaves a folder the owner cannot open, so that one case
    sets the mode by path first (the name was created exclusively a moment ago) and then goes
    through the descriptor, which also proves it is a real directory and reads the mode back.
    """
    try:
        _restrict_directory(path)
    except PermissionError:
        os.chmod(path, _OWNER_DIR)
        _restrict_directory(path)


def create_private_directory(path: Path) -> None:
    """Create `path` as a new owner-only directory; its parent must exist.

    Exclusive `mkdir` (an existing entry, a symlink included, is `PRIVATE_EXISTS`, so a caller
    that picks names can retry), then the directory is opened with `O_NOFOLLOW | O_DIRECTORY`,
    narrowed to 0700 through that descriptor and read back with `fstat`. A narrowing failure
    removes the directory again, so no wider folder is left for data to land in. Windows has no
    descriptor to open, so it keeps the plain exclusive `mkdir`. Raises `PrivateFileError`.
    """
    code: str | None = None
    failed_errno: int | None = None
    try:
        os.mkdir(path, _OWNER_DIR)
    except FileExistsError as exc:
        code, failed_errno = PRIVATE_EXISTS, exc.errno
    except OSError as exc:
        code, failed_errno = PRIVATE_OPEN_FAILED, exc.errno
    if code is None and not _WINDOWS:
        try:
            _narrow_new_directory(path)
        except OSError as exc:
            code = PRIVATE_MODE_FAILED if isinstance(exc, _ModeError) else PRIVATE_OPEN_FAILED
            failed_errno = exc.errno
            with contextlib.suppress(OSError):
                os.rmdir(path)
    if code is not None:
        raise PrivateFileError(code, failed_errno)


def create_private_temp(prefix: str) -> Path:
    """An owner-only temp file in the system temp directory, for a spool the caller removes.

    Uses the one staging-name rule, so the name ends in `.tmp` whatever the caller writes
    into it. Raises `PrivateFileError`.
    """
    code: str | None = None
    failed_errno: int | None = None
    path = ""
    try:
        path, _ = create_exclusive(Path(tempfile.gettempdir()), prefix, private=True)
    except _ModeError as exc:
        code, failed_errno = PRIVATE_MODE_FAILED, exc.errno
    except OSError as exc:
        code, failed_errno = PRIVATE_OPEN_FAILED, exc.errno
    if code is not None:
        raise PrivateFileError(code, failed_errno)
    return Path(path)
