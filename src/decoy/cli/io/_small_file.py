"""The one reader for small bookkeeping files the CLI trusts: project markers, claims and `LATEST`.

A planted symlink, Windows reparse point, FIFO or device at one of these paths must never be read
through. The path is checked with `lstat` first and refused unless it is a plain regular file, so
the guarantee does not depend on `O_NOFOLLOW` (absent on Windows, and Python documents it as
platform-dependent). The open then adds `O_NOFOLLOW`, `O_NONBLOCK` and `O_NOCTTY` where the
platform has them, and the opened descriptor must be the same regular file `lstat` saw, so a swap
between the check and the open is refused too (CERT FIO01-C: judge the descriptor, not the path).
`tests/sentry/io_policy/test_small_file_reader.py` keeps every other module under `cli/` from
building its own no-follow open.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

# Not in `stat` on POSIX builds; the Windows value.
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class UnsafeFileError(Exception):
    """Something other than a plain regular file is at the path, or it could not be read."""


@dataclass(frozen=True)
class SmallFile:
    """At most the requested number of bytes, with the size and owner the descriptor reported."""

    data: bytes
    size: int
    uid: int


def _plain_regular(info: os.stat_result) -> bool:
    reparse = getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    return stat.S_ISREG(info.st_mode) and not reparse


def read_small_file(path: Path, max_bytes: int) -> SmallFile | None:
    """The first `max_bytes` of the regular file at `path`; None when nothing is there.

    Raises `UnsafeFileError` for a symlink, reparse point, FIFO, device, directory, a file that
    changed between the check and the open, or one that cannot be read.
    """
    try:
        before = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise UnsafeFileError from exc
    if not _plain_regular(before):
        raise UnsafeFileError
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOCTTY", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise UnsafeFileError from exc
    try:
        info = os.fstat(fd)
        same = (info.st_dev, info.st_ino) == (before.st_dev, before.st_ino)
        if not (same and _plain_regular(info)):
            raise UnsafeFileError
        return SmallFile(os.read(fd, max_bytes), info.st_size, info.st_uid)
    except OSError as exc:
        raise UnsafeFileError from exc
    finally:
        os.close(fd)
