"""The one atomic file writer for the CLI.

The sequence is the standard durable replace: write a temp file on the same volume, fsync it,
move it onto the target, fsync the directory. Sources: SQLite's rollback-journal commit and the
ext4 documentation on rename and fsync; `os.replace` as the successor to the deprecated
`atomicwrites` package (https://github.com/untitaker/python-atomicwrites), whose
`atomic_write` context manager is the shape of `staged_local_target`; the engine's
`fileaccess.write_private` recipe, mirrored without its file-access policy so it runs on Windows.
Creation and every mode change live in `_private_file`, the one module Windows ACLs will change.
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

* `replace_symlink` is the one link swap: a temp link beside the target, then `os.replace`.
  It replaces only a symlink (or nothing), never a regular file or directory.

* `publish_local_targets` publishes a few files of one folder as one unit (a snapshot and the
  config that names it). It stages and fsyncs every file first, keeps a hard-link backup of
  each file it replaces, and restores or removes every file if any replace fails. A
  non-blocking `flock` on the folder keeps a second publisher out until the first is done.
  The lock is POSIX only (Windows has no `fcntl`, so no lock there). A rollback covers every
  exception, an interrupt included; a rollback step that fails keeps its backup and raises
  `ATOMIC_ROLLBACK_INCOMPLETE` with the backup names, or with the names of new files it could
  not remove. A SIGKILL between two replaces cannot
  be rolled back and can leave a half pair plus a hidden `.<name>.decoy-*.bak`.

Not covered: the vault commit in `cli/run/_vault.py`, which needs a hard-link backup and rollback,
and the install-directory moves in `distribution/`. Both are allowlisted with reasons.
"""

from __future__ import annotations

import contextlib
import enum
import errno
import os
import re
import secrets
import stat
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from decoy import _private_file

try:
    import fcntl
except ImportError:  # Windows: no directory lock
    fcntl = None  # type: ignore[assignment]
from decoy._private_file import (
    apply_mode,
    create_exclusive,
    restrict_owner_only,
)

__all__ = [
    "ATOMIC_BAD_NAME",
    "ATOMIC_BATCH_BUSY",
    "ATOMIC_BATCH_INVALID",
    "ATOMIC_NOCLOBBER_UNSUPPORTED",
    "ATOMIC_ROLLBACK_INCOMPLETE",
    "ATOMIC_SYNC_FAILED",
    "ATOMIC_TARGET_EXISTS",
    "ATOMIC_WRITE_FAILED",
    "AtomicWriteError",
    "LocalTarget",
    "WriteMode",
    "describe",
    "fsync_directory",
    "publish_local_targets",
    "replace_symlink",
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
# `publish_local_targets`: another publisher holds the folder; a create-only target exists;
# the batch is malformed (empty, two folders, a repeated name).
ATOMIC_BATCH_BUSY = "atomic_batch_busy"
ATOMIC_TARGET_EXISTS = "atomic_target_exists"
ATOMIC_BATCH_INVALID = "atomic_batch_invalid"
# `publish_local_targets` failed and could not undo every target; the error's `kept` holds
# the hidden backup names (each one the old bytes of a file that was not put back) and its
# `left` the names of new files that could not be removed.
ATOMIC_ROLLBACK_INCOMPLETE = "atomic_rollback_incomplete"

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
    `kept` names (file names, no folder) the backups a failed rollback left on disk; `left`
    names the new files it could not remove.
    """

    def __init__(
        self,
        code: str,
        os_errno: int | None = None,
        kept: tuple[str, ...] = (),
        left: tuple[str, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.errno = os_errno
        self.kept = kept
        self.left = left


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
    if not _private_file._WINDOWS and existing.st_gid != os.stat(tmp).st_gid:
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
        apply_mode(fd, tmp, bits)
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
        # Owner-only while written: create_exclusive narrows the temp before returning it.
        tmp, created = create_exclusive(tmp_dir or real.parent, real.name, private=private)
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
            alive = not made or (mode is WriteMode.CREATE_ONCE and not _private_file._WINDOWS)
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


_STD_FDS = {"/dev/stdin": 0, "/dev/stdout": 1, "/dev/stderr": 2}


def _restrict_fd_target(alias: str) -> None:
    """Make a regular file behind an fd alias owner-only before private bytes reach it.

    `decoy unmask -o /dev/stdout > out.csv` writes through the shell's file, which the shell
    created with the umask default. A pipe or terminal keeps nothing, so only a regular file
    is narrowed. If the fd is closed, or the file cannot be made 0600, the write is refused.
    """
    fd = _STD_FDS[alias] if alias in _STD_FDS else int(alias.rsplit("/", 1)[1])
    failed_errno: int | None = None
    narrowed = True
    try:
        info = os.fstat(fd)
        if stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) & 0o077:
            restrict_owner_only(fd, alias)
    except OSError as exc:
        narrowed, failed_errno = False, exc.errno
    if not narrowed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)


def _refuse_foreign_symlink(path: Path) -> None:
    """Refuse a final-component symlink that another user owns.

    The write follows a symlink, so a local user could point one at a file of the victim's own
    and have the replacement land there (lost data, not a leak: the bytes are 0600). This
    mirrors Linux `fs.protected_symlinks`, which macOS lacks. A link the user owns is followed.
    """
    if _private_file._WINDOWS:
        return
    try:
        info = os.lstat(path)
    except OSError:
        return  # missing or unreadable: the stat that follows reports it
    if stat.S_ISLNK(info.st_mode) and info.st_uid != os.geteuid():
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, errno.EPERM)


@contextlib.contextmanager
def _staged_target(path: Path, private: bool) -> Iterator[Path]:
    _require_component(path.name)
    # POSIX keeps a leading "//" in abspath; collapse it so //dev/stdout is still an alias.
    alias = re.sub(r"^/+", "/", os.path.abspath(path))
    if not _private_file._WINDOWS and _FD_ALIAS.fullmatch(alias):
        if private:
            _restrict_fd_target(alias)
        yield path  # /dev/stdout, /dev/fd/N, /proc/self/fd/N: a redirect is written through
        return
    _refuse_foreign_symlink(path)
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

    An fd alias redirected to a regular file has that file narrowed to 0600 before the block
    runs, or the write is refused.

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
        or (_private_file._WINDOWS and (stem in _DEVICE_STEMS or "\\" in name or ":" in name))
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
        if _private_file._WINDOWS:
            # os.rename fails on Windows when the target exists, which is the no-clobber move.
            _retry_on_windows(lambda: os.rename(tmp, target))
        else:
            os.link(tmp, target)
    except FileExistsError:
        return False
    except OSError as exc:
        if _private_file._WINDOWS or exc.errno not in _NO_HARD_LINKS:
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
            if not _private_file._WINDOWS or attempt == _RETRY_ATTEMPTS - 1:
                raise
            _sleep(delay)
            delay = min(delay * 2, _RETRY_CAP_SECONDS)


def replace_symlink(link: Path, target: str) -> None:
    """Point `link` at `target` (stored as given, so pass a relative one) in one step.

    A symlink cannot be retargeted in place, so the new link is made under a temporary name
    in the same folder and `os.replace`d over the old one: a reader sees the old target or
    the new one, never a missing link. Only a symlink (or nothing) is replaced; a regular
    file or folder in the way is refused so a pointer swap cannot clobber user data. Raises
    `AtomicWriteError` (no path, no cause) and leaves no temp link behind.
    """
    failed = False
    failed_errno: int | None = None
    try:
        if not stat.S_ISLNK(os.lstat(link).st_mode):
            failed = True
    except FileNotFoundError:
        pass
    except OSError as exc:
        failed, failed_errno = True, exc.errno
    # Raised outside the except blocks so an OSError (its text names the path) is not kept as
    # `__context__`.
    if failed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)
    tmp = link.with_name(f".{link.name}.decoy-{secrets.token_hex(6)}.tmp")
    try:
        os.symlink(target, tmp)
        _retry_on_windows(lambda: os.replace(tmp, link))
    except OSError as exc:
        failed, failed_errno = True, exc.errno
        with contextlib.suppress(OSError):
            os.unlink(tmp)
    if failed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)


def fsync_directory(directory: Path) -> None:
    """Make a rename or unlink in `directory` durable. Raises plain `OSError`.

    Windows cannot open a directory and NTFS journals the rename, so it does nothing there.
    """
    if _private_file._WINDOWS:
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


@dataclass(frozen=True)
class LocalTarget:
    """One file of a `publish_local_targets` batch. `private` publishes it 0600."""

    path: Path
    data: bytes
    mode: WriteMode = WriteMode.REPLACE
    private: bool = False


def _stage_bytes(real: Path, data: bytes, private: bool) -> tuple[str, int]:
    """Write `data` to a fsynced temp beside `real`; return its name and the create-time bits."""
    tmp, created = create_exclusive(real.parent, real.name, private=private)
    try:
        with open(tmp, "r+b") as handle:  # r+ so Windows FlushFileBuffers has write access
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return tmp, created


def _unlink_quietly(path: str | Path) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


@contextlib.contextmanager
def _folder_lock(directory: Path) -> Iterator[None]:
    """Hold a non-blocking exclusive lock on the folder itself, so no loose lock file exists.

    POSIX only: without `fcntl` (Windows) there is no lock and two publishers can interleave.
    """
    if fcntl is None:
        yield
        return
    failed = False
    failed_errno: int | None = None
    fd = -1
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        failed, failed_errno = True, exc.errno
        if fd >= 0:
            os.close(fd)
    if failed:
        busy = failed_errno in (errno.EWOULDBLOCK, errno.EAGAIN)
        raise AtomicWriteError(ATOMIC_BATCH_BUSY if busy else ATOMIC_WRITE_FAILED, failed_errno)
    try:
        yield
    finally:
        os.close(fd)  # closing releases the lock


def _rollback(done: list[tuple[Path, str | None]]) -> tuple[list[str], list[str]]:
    """Undo published targets, newest first: put the old file back, or remove a new one.

    Returns the backups it could not restore (the caller keeps those on disk) and the file
    names of new targets it could not remove.
    """
    stuck: list[str] = []
    left: list[str] = []
    for real, backup in reversed(done):
        try:
            if backup is None:
                os.unlink(real)
            else:
                os.replace(backup, real)
        except OSError:
            if backup is None:
                left.append(real.name)
            else:
                stuck.append(backup)
    return stuck, left


def publish_local_targets(
    targets: Sequence[LocalTarget], *, check: Callable[[list[Path]], None] | None = None
) -> None:
    """Publish every target in order, or none: on any failure the old files come back.

    All targets sit in one folder, which this holds locked until it is done. Every file is
    staged and fsynced before the first replace. A file that already exists keeps a hard-link
    backup (the old inode, so its bytes and mode return exactly). If a replace fails, the
    published files are restored or removed and `AtomicWriteError` is raised; so are they on
    any other exception, `KeyboardInterrupt` included, which then propagates. A restore that
    fails keeps its backup and raises `ATOMIC_ROLLBACK_INCOMPLETE` instead. A `CREATE_ONCE`
    target that exists once the lock is held is refused before anything changes. Lock, backup
    or staging failures also refuse before the first replace. `check`, when given, receives the
    staged temp paths (in target order) once everything is staged and before the first replace;
    whatever it raises propagates and nothing has changed. The directory sync after the
    last replace can fail with `ATOMIC_SYNC_FAILED`: the new files are then in place.
    """
    if not targets:
        raise AtomicWriteError(ATOMIC_BATCH_INVALID)
    for target in targets:
        _require_component(target.path.name)
    reals = [Path(os.path.realpath(t.path)) for t in targets]
    directory = reals[0].parent
    if any(r.parent != directory for r in reals) or len({r.name for r in reals}) != len(reals):
        raise AtomicWriteError(ATOMIC_BATCH_INVALID)

    staged: list[tuple[str, int]] = []
    backups: list[str | None] = []
    done: list[tuple[Path, str | None]] = []
    stuck: list[str] = []
    left: list[str] = []
    failed = False
    failed_errno: int | None = None
    try:
        with _folder_lock(directory):
            try:
                existing = [_existing(real) for real in reals]
                for target, old in zip(targets, existing, strict=True):
                    if target.mode is WriteMode.CREATE_ONCE and old is not None:
                        raise AtomicWriteError(ATOMIC_TARGET_EXISTS)
                for target, real in zip(targets, reals, strict=True):
                    staged.append(_stage_bytes(real, target.data, target.private))
                for real, old in zip(reals, existing, strict=True):
                    backups.append(None if old is None else _backup(real))
                if check is not None:
                    check([Path(tmp) for tmp, _created in staged])
                for target, real, old, (tmp, created) in zip(
                    targets, reals, existing, staged, strict=True
                ):
                    bits = _final_bits(tmp, old, target.private, created)
                    if not _publish(tmp, real, bits, target.mode):
                        raise AtomicWriteError(ATOMIC_TARGET_EXISTS)
                    done.append((real, backups[len(done)]))
            except BaseException as exc:
                stuck, left = _rollback(done)
                if stuck or left:
                    pass  # reported below, after the backups are left in place
                elif isinstance(exc, OSError):
                    failed, failed_errno = True, exc.errno
                else:
                    raise
    finally:
        for tmp, _created in staged:
            _unlink_quietly(tmp)
        for backup in backups:
            if backup is not None and backup not in stuck:
                _unlink_quietly(backup)
    if stuck or left:
        raise AtomicWriteError(
            ATOMIC_ROLLBACK_INCOMPLETE,
            kept=tuple(Path(name).name for name in stuck),
            left=tuple(left),
        )
    if failed:
        raise AtomicWriteError(ATOMIC_WRITE_FAILED, failed_errno)
    _sync_directories(directory, None)


def _existing(real: Path) -> os.stat_result | None:
    try:
        return os.stat(real)
    except FileNotFoundError:
        return None


def _backup(real: Path) -> str:
    """A same-folder hard link to the file about to be replaced."""
    name = real.parent / f".{real.name}.decoy-{secrets.token_hex(6)}.bak"
    os.link(real, name)
    return str(name)
