"""Filesystem primitives for ``decoy local-cleanup`` (F26 Slice 5).

Everything here is descriptor-relative and refuses to follow a symlink at ANY path component, so a
candidate can only ever be the exact regular file an allowed root contains. Nothing here prints a
path or a name; callers see closed outcomes only.

Deletion acts on the VERIFIED OBJECT, not on a name. POSIX has no unlink-by-descriptor, so the name
is first CAPTURED by an atomic no-replace rename to a private quarantine name (Linux
``renameat2(RENAME_NOREPLACE)``, macOS ``renameatx_np(RENAME_EXCL)``), the captured inode is compared
to the still-open verified descriptor (a held descriptor pins its inode number), and only then is the
quarantine name unlinked. A different object that was swapped in is renamed back, or, if the
original name was re-created meanwhile, KEPT under the quarantine name: it is never destroyed.

Platform note: this needs ``dir_fd`` support, ``O_NOFOLLOW`` and an atomic no-replace rename (Linux
and macOS). Where they are absent ``safe_open_supported()`` is False and execution refuses; preview
still works through the plain-path fallback, which is read-only.
"""

from __future__ import annotations

import ctypes
import enum
import hashlib
import os
import platform
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1 << 20
QUARANTINE_PREFIX = ".decoy-cleanup-"
_RENAME_NOREPLACE = 1  # Linux renameat2 flag
_RENAME_EXCL = 0x4  # macOS renameatx_np flag
_LINUX_RENAMEAT2 = {"x86_64": 316, "aarch64": 276, "arm64": 276}.get(platform.machine())
_libc = ctypes.CDLL(None, use_errno=True)


def _noreplace_rename_available() -> bool:
    if sys.platform.startswith("linux"):
        return _LINUX_RENAMEAT2 is not None
    if sys.platform == "darwin":
        return hasattr(_libc, "renameatx_np")
    return False


def _rename_noreplace(old_dirfd: int, old: str, new_dirfd: int, new: str) -> None:
    """Atomic rename that fails with EEXIST rather than replace; raises OSError."""
    if sys.platform.startswith("linux") and _LINUX_RENAMEAT2 is not None:
        rc = _libc.syscall(
            _LINUX_RENAMEAT2,
            ctypes.c_int(old_dirfd),
            ctypes.c_char_p(os.fsencode(old)),
            ctypes.c_int(new_dirfd),
            ctypes.c_char_p(os.fsencode(new)),
            ctypes.c_uint(_RENAME_NOREPLACE),
        )
    elif sys.platform == "darwin" and hasattr(_libc, "renameatx_np"):
        rc = _libc.renameatx_np(
            ctypes.c_int(old_dirfd),
            ctypes.c_char_p(os.fsencode(old)),
            ctypes.c_int(new_dirfd),
            ctypes.c_char_p(os.fsencode(new)),
            ctypes.c_uint(_RENAME_EXCL),
        )
    else:
        raise OSError(38, "no atomic no-replace rename")
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def _after_verify(*_args: object) -> None:
    """Seam between 'the open descriptor is verified' and 'the name is captured' (race tests)."""


def safe_open_supported() -> bool:
    return (
        _noreplace_rename_available()
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    )


class Probe(enum.Enum):
    MATCH = "match"
    MISMATCH = "mismatch"  # something else is there (content, size, link count, type, symlink)
    ABSENT = "absent"
    UNREADABLE = "unreadable"
    OUTSIDE = "outside"  # not beneath any allowed root


@dataclass(frozen=True)
class Identity:
    dev: int
    ino: int
    size: int
    mtime_ns: int
    sha256: str


def _flags() -> tuple[int, int]:
    base = getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    return (
        base | nofollow | getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY,
        base | nofollow | os.O_RDONLY,
    )


def open_root(root: Path) -> int:
    """Open an explicit, user-supplied root. The root itself may be reached through the user's own
    symlinks (that is their choice); nothing BENEATH it may be."""
    return os.open(
        os.path.realpath(root), os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    )


def split_beneath(path: Path, root: Path) -> tuple[str, ...] | None:
    """The components of ``path`` beneath ``root`` by whole components, else None (lexical only;
    the kernel-enforced walk in ``open_beneath`` is the real containment check)."""
    try:
        rel = Path(os.path.abspath(path)).relative_to(os.path.abspath(root))
    except ValueError:
        return None
    parts = rel.parts
    if not parts or any(p in ("", ".", "..") for p in parts):
        return None
    return parts


def open_beneath(root_fd: int, parts: tuple[str, ...]) -> tuple[int, int]:
    """Open ``parts`` strictly beneath ``root_fd``, component by component, never following a
    symlink. Returns ``(parent_dir_fd, file_fd)``; the caller closes both."""
    dir_flags, file_flags = _flags()
    cur = os.dup(root_fd)
    try:
        for name in parts[:-1]:
            nxt = os.open(name, dir_flags, dir_fd=cur)
            os.close(cur)
            cur = nxt
        fd = os.open(parts[-1], file_flags | os.O_NONBLOCK, dir_fd=cur)
        return cur, fd
    except BaseException:
        os.close(cur)
        raise


def read_identity(fd: int) -> Identity | None:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        return None
    h = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, _CHUNK):
        h.update(chunk)
    return Identity(st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, h.hexdigest())


def probe_path(root: Path, parts: tuple[str, ...]) -> tuple[Probe, Identity | None]:
    """READ-ONLY fallback for platforms without ``dir_fd``/``O_NOFOLLOW`` (preview only; execution
    refuses there). Every component is ``lstat``-ed and a symlink anywhere is a mismatch."""
    cur = Path(os.path.realpath(root))
    try:
        for name in parts[:-1]:
            cur = cur / name
            st = os.lstat(cur)
            if not stat.S_ISDIR(st.st_mode):
                return Probe.MISMATCH, None
        target = cur / parts[-1]
        st = os.lstat(target)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return Probe.MISMATCH, None
        h = hashlib.sha256()
        with open(target, "rb") as fh:
            while chunk := fh.read(_CHUNK):
                h.update(chunk)
        return Probe.MATCH, Identity(
            st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, h.hexdigest()
        )
    except FileNotFoundError:
        return Probe.ABSENT, None
    except PermissionError:
        return Probe.UNREADABLE, None
    except OSError:
        return Probe.MISMATCH, None


def probe(root_fd: int, parts: tuple[str, ...]) -> tuple[Probe, Identity | None]:
    try:
        parent, fd = open_beneath(root_fd, parts)
    except FileNotFoundError:
        return Probe.ABSENT, None
    except PermissionError:
        return Probe.UNREADABLE, None
    except OSError:
        # ELOOP (a symlink), ENOTDIR (a file where a directory should be), and the like: it is
        # not the plain file the manifest recorded.
        return Probe.MISMATCH, None
    try:
        ident = read_identity(fd)
        return (Probe.MATCH, ident) if ident is not None else (Probe.MISMATCH, None)
    except OSError:
        return Probe.UNREADABLE, None
    finally:
        os.close(fd)
        os.close(parent)


def unlink_exact(root_fd: int, parts: tuple[str, ...], expected: Identity) -> bool:
    """Delete the file only if it is still exactly ``expected`` AND the object removed is the one
    verified: the name is captured by an atomic rename, the captured inode is compared to the open
    verified descriptor, and only then is it unlinked (see the module docstring)."""
    try:
        parent, fd = open_beneath(root_fd, parts)
    except OSError:
        return False
    try:
        if read_identity(fd) != expected:
            return False
        _after_verify(fd, parts[-1])
        held = os.fstat(fd)
        quarantine = QUARANTINE_PREFIX + secrets.token_hex(8)
        try:
            _rename_noreplace(parent, parts[-1], parent, quarantine)
        except OSError:
            return False
        captured = os.stat(quarantine, dir_fd=parent, follow_symlinks=False)
        if (captured.st_dev, captured.st_ino) != (held.st_dev, held.st_ino):
            try:  # not ours: put it back exactly where it was
                _rename_noreplace(parent, quarantine, parent, parts[-1])
            except OSError:
                pass  # the name was re-created meanwhile: the captured object stays, intact
            return False
        os.unlink(quarantine, dir_fd=parent)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
        os.close(parent)
