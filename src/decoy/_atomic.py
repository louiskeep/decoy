"""The one atomic file writer for the CLI.

The sequence is the standard durable replace: write a temp file on the same volume, fsync it,
move it onto the target, fsync the directory. Sources: SQLite's rollback-journal commit and the
ext4 documentation on rename and fsync; `os.replace` as the successor to the deprecated
`atomicwrites` package (https://github.com/untitaker/python-atomicwrites), whose
`atomic_write` context manager is the shape of `staged_local_target`; the engine's
`fileaccess.write_private` recipe, mirrored without its file-access policy so it runs on Windows.
Local plan: `plan/local-record-library:docs/plans/2026-11-05-local-record-library.md` section 4.9.

Rules this module owns (tests/sentry/test_atomic_writer.py fails when `os.replace`,
`os.rename`, `os.link` or `tempfile.mkstemp` appear elsewhere in `src/decoy/` outside its
allowlist):

* After any failure the target holds the old bytes or the new bytes, never neither, and no
  temp file is left behind (a SIGKILL can still leave a hidden `.<name>.decoy-*.tmp`).
* An error carries a fixed code and an errno, never a path (an `OSError` text names the path),
  and its cause is not chained. `describe` renders it for the CLI.
* `write_atomic` (library-controlled names, such as record ids) checks the name against an
  allowlist portable on Windows and POSIX. `write_local_target` and the staged forms
  (a path the user chose and the caller already resolved) accept any single path component
  except `.`, `..`, an empty name, a separator, NUL or a Windows device name.
* `staged_local_target` and `staged_private_target` are the streaming forms for a writer that
  needs a path (pandas, pyarrow). They follow a symlink and write a FIFO, device or fd alias
  through. The first keeps the old file's mode bits; the second publishes 0600 (POSIX only: on
  Windows the file inherits its folder's permissions).
* Every write (`write_atomic`, `write_local_target`, both staged forms) runs through one core,
  `_staged`: create the temp, publish, clean up, sync.
* `CREATE_ONCE` never replaces a file. Where the mount offers no atomic no-clobber
  move, it fails with `atomic_noclobber_unsupported` instead of checking then replacing.

Not covered: the vault commit in `cli/run.py`, which needs a hard-link backup and rollback,
and the install-directory swaps in `distribution/`. Both are allowlisted with reasons.
"""

from __future__ import annotations

import contextlib
import enum
import errno
import os
import re
import secrets
import stat
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

__all__ = [
    "ATOMIC_BAD_NAME",
    "ATOMIC_NOCLOBBER_UNSUPPORTED",
    "ATOMIC_SYNC_FAILED",
    "ATOMIC_WRITE_FAILED",
    "AtomicWriteError",
    "WriteMode",
    "describe",
    "fsync_directory",
    "staged_local_target",
    "staged_private_target",
    "write_atomic",
    "write_local_target",
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
# The reserved set follows CPython's os.path.isreserved (Lib/ntpath.py, 3.13): COM0 and
# LPT0 are not devices, and the superscript forms are.
_DEVICE_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{c}" for c in "123456789\u00b9\u00b2\u00b3"}
    | {f"LPT{c}" for c in "123456789\u00b9\u00b2\u00b3"}
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
    return _put_at(directory / name, data, mode, tmp_dir)


def write_local_target(path: Path, data: bytes, mode: WriteMode) -> bool:
    """Write `data` to `path`, a target the user chose and the caller already resolved.

    For `--output` style paths where `write_atomic`'s portable-name allowlist would reject
    names that always worked (spaces, a leading `_` or `.`, non-ASCII). The caller owns
    containment; this checks only that the last component is one safe path component.
    `REPLACE` follows a symlink like `staged_private_target`; `CREATE_ONCE` treats an
    existing symlink as existing. Same return value and errors as `write_atomic`.
    """
    _require_component(path.name)
    if mode is WriteMode.REPLACE:
        return _put(staged_private_target(path), data)
    return _put_at(path, data, mode, None)


def describe(exc: AtomicWriteError) -> str:
    """The one renderer for a CLI message: the code, plus the OS reason when there is one."""
    if exc.errno:
        return f"{exc.code} ({os.strerror(exc.errno)})"
    return exc.code


_SPECIAL_KINDS = (stat.S_ISFIFO, stat.S_ISCHR, stat.S_ISBLK, stat.S_ISSOCK)
_OWNER_RW = 0o600
# The fd aliases, matched on the user-given path before any symlink is resolved. Not all of
# /dev or /proc: /dev/shm is a real tmpfs and must be staged.
_FD_ALIAS = re.compile(r"/dev/(?:stdin|stdout|stderr|fd/[0-9]+)|/proc/self/fd/[0-9]+")
_FALLBACK_NAME_MAX = 255


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


def _create_temp(parent: Path, base: str, private: bool) -> tuple[str, int]:
    """Create the staging file exclusively. Returns its path and the mode bits it was given."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    while True:
        tmp = str(parent / _temp_name(base, parent))
        try:
            fd = os.open(tmp, flags, 0o600 if private else 0o666)
        except FileExistsError:
            continue
        try:
            bits = stat.S_IMODE(os.fstat(fd).st_mode) & 0o777
        finally:
            os.close(fd)
        return tmp, bits


def _final_bits(tmp: str, existing: os.stat_result | None, private: bool, created: int) -> int:
    """Mode for the published file: 0600 if private, else the old file's bits, else a new file's.

    A different group on the old file is copied with chown when allowed; when it is not, the
    old bits are cut to what a new file would have, so the replacement never grants more.
    """
    if private:
        return _OWNER_RW
    if existing is None or not stat.S_ISREG(existing.st_mode):
        return created
    copied = stat.S_IMODE(existing.st_mode) & 0o777
    if not _WINDOWS and existing.st_gid != os.stat(tmp).st_gid:
        try:
            os.chown(tmp, -1, existing.st_gid)
        except OSError:
            return copied & created
    return copied


def _publish(tmp: str, real: Path, bits: int, mode: WriteMode) -> bool:
    """Apply the final mode, fsync the data, and move the temp into place.

    Returns False only for `CREATE_ONCE` when the target already exists.
    """
    fd = os.open(tmp, os.O_RDWR)  # Windows FlushFileBuffers needs write access
    try:
        if _WINDOWS:
            os.chmod(tmp, bits)
        else:
            os.fchmod(fd, bits)
        os.fsync(fd)
    finally:
        os.close(fd)
    if mode is WriteMode.CREATE_ONCE:
        return _create_once(tmp, real)
    _retry_on_windows(lambda: os.replace(tmp, real))
    return True


@dataclass
class _Outcome:
    created: bool = True


@contextlib.contextmanager
def _staged(
    real: Path,
    *,
    private: bool,
    mode: WriteMode = WriteMode.REPLACE,
    tmp_dir: Path | None = None,
    existing: os.stat_result | None = None,
    outcome: _Outcome | None = None,
) -> Iterator[Path]:
    """The one create, publish, clean-up and sync core behind every atomic write.

    Yields a temp path (owner-only while it is written). A clean exit publishes it onto `real`;
    any exception removes it and propagates unchanged. Setup and commit failures raise
    `AtomicWriteError` with no exception context.
    """
    tmp = ""
    created = 0
    failed = False
    failed_errno: int | None = None
    try:
        tmp, created = _create_temp(tmp_dir or real.parent, real.name, private)
        # Owner-only while written, and a restrictive umask must not lock the writer out.
        os.chmod(tmp, _OWNER_RW)
    except OSError as exc:
        failed, failed_errno = True, exc.errno
    if failed:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)
    alive = True  # the temp name still exists and must be removed on the way out
    made = False
    try:
        yield Path(tmp)
        try:
            made = _publish(tmp, real, _final_bits(tmp, existing, private, created), mode)
        except OSError as exc:
            failed, failed_errno = True, exc.errno
        else:
            alive = not made or (mode is WriteMode.CREATE_ONCE and not _WINDOWS)
            if made and alive:
                # The hard-link move leaves the temp name as a second link; drop it before the
                # directory sync so a crash cannot leave a stray hidden entry.
                try:
                    os.unlink(tmp)
                except OSError:
                    pass  # left for the cleanup below to retry
                else:
                    alive = (
                        False  # gone, so the cleanup cannot unlink a name another process reused
                    )
    finally:
        if alive:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    # Raised outside the except block so the OSError (its text names the path) is not kept as
    # `__context__`.
    if failed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)
    if made:
        _sync_directories(real.parent, tmp_dir)
    if outcome is not None:
        outcome.created = made


def _put(stage: AbstractContextManager[Path], data: bytes, outcome: _Outcome | None = None) -> bool:
    """Write `data` into the temp that `stage` yields, mapping an OS failure to the atomic code."""
    failed = False
    failed_errno: int | None = None
    try:
        with stage as tmp:
            tmp.write_bytes(data)
    except OSError as exc:
        failed, failed_errno = True, exc.errno
    if failed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)
    return outcome.created if outcome is not None else True


def _put_at(real: Path, data: bytes, mode: WriteMode, tmp_dir: Path | None) -> bool:
    outcome = _Outcome()
    stage = _staged(real, private=True, mode=mode, tmp_dir=tmp_dir, outcome=outcome)
    return _put(stage, data, outcome)


@contextlib.contextmanager
def _staged_target(path: Path, private: bool) -> Iterator[Path]:
    _require_component(path.name)
    if not _WINDOWS and _FD_ALIAS.fullmatch(os.path.abspath(path)):
        yield path  # /dev/stdout, /dev/fd/N, /proc/self/fd/N: a redirect is written through
        return
    existing: os.stat_result | None = None
    failed_errno: int | None = None
    failed = False
    try:
        existing = os.stat(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        failed, failed_errno = True, exc.errno
    if failed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)
    if existing is not None and any(kind(existing.st_mode) for kind in _SPECIAL_KINDS):
        yield path  # classified before realpath: /dev/stdout resolves to an unopenable name
        return
    with _staged(Path(os.path.realpath(path)), private=private, existing=existing) as tmp:
        yield tmp


def staged_local_target(path: Path) -> AbstractContextManager[Path]:
    """Yield a temp path beside `path`; publish it onto `path` only if the block exits cleanly.

    The shape of `atomicwrites.atomic_write`. An exception from the block removes the temp and
    propagates unchanged, so `path` keeps its old bytes or stays missing. A symlink is followed
    and its destination replaced. A FIFO, device or socket, and an fd alias (/dev/stdout,
    /dev/fd/N, /proc/self/fd/N), is yielded as is, with no staging. The published file keeps an
    existing output's mode bits; a new one gets the umask default.
    """
    return _staged_target(path, False)


def staged_private_target(path: Path) -> AbstractContextManager[Path]:
    """`staged_local_target` for restored or sensitive data: the published file is 0600.

    On Windows the mode bits do not apply: the file inherits its folder's permissions.
    """
    return _staged_target(path, True)


def _require_component(name: str) -> None:
    seps = {"/", os.sep, os.altsep or "/"}
    stem = name.split(".", 1)[0].rstrip(" ").upper()
    if (
        not name
        or name in {".", ".."}
        or "\0" in name
        or any(sep in name for sep in seps)
        or (_WINDOWS and (stem in _DEVICE_STEMS or "\\" in name or ":" in name))
    ):
        raise AtomicWriteError(ATOMIC_BAD_NAME)


def _require_name(name: str) -> None:
    stem = name.split(".", 1)[0].rstrip(" ").upper()
    ok = (
        _NAME_PATTERN.fullmatch(name) is not None
        and not name.endswith(".")
        and stem not in _DEVICE_STEMS
        and PureWindowsPath(name).name == PurePosixPath(name).name == name
    )
    if not ok:
        raise AtomicWriteError(ATOMIC_BAD_NAME)


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
