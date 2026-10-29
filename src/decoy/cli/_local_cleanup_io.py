"""Filesystem primitives for ``decoy local-cleanup`` (F26 Slice 5).

Everything here is descriptor-relative and refuses to follow a symlink at ANY path component, so a
candidate can only ever be the exact regular file an allowed root contains. Nothing here prints a
path or a name; callers see closed outcomes only.

Platform note: this needs ``dir_fd`` support and ``O_NOFOLLOW`` (Linux and macOS). Where they are
absent ``safe_open_supported()`` is False and execution refuses; preview still works through the
plain-path fallback, which is read-only.
"""

from __future__ import annotations

import enum
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1 << 20


def safe_open_supported() -> bool:
    return (
        hasattr(os, "O_NOFOLLOW")
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
    """Delete the file only if, right now and through descriptors, it is still exactly ``expected``.

    The name is unlinked relative to its parent descriptor after the open descriptor and a fresh
    ``fstatat(NOFOLLOW)`` of the name agree on the inode. (POSIX has no atomic compare-and-unlink;
    the residual window is a same-user rename race this command is not designed to resist.)"""
    try:
        parent, fd = open_beneath(root_fd, parts)
    except OSError:
        return False
    try:
        now = read_identity(fd)
        if now != expected:
            return False
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (expected.dev, expected.ino):
            return False
        os.unlink(parts[-1], dir_fd=parent)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
        os.close(parent)
