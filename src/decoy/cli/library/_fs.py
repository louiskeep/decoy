"""The library's filesystem calls: a thin layer over the CLI's one creator and one atomic writer.

Folders come from `decoy._private_file.create_private_directory` (0700 at creation; an existing
folder is never re-permissioned, the token-vault rule). Files come from `decoy._atomic`:
`write_atomic(..., tmp_dir=library/tmp)` for records and `LAYOUT` (temp 0600 on the same volume,
fsync, no-clobber link, directory fsync; plan 4.9), and `write_local_target` for the dot-named
git file, whose leading `.` the record-name allowlist refuses. Nothing here calls `os.replace`,
`mkstemp` or `chmod` itself (G-ONE-ATOMIC-WRITER, G-ONE-PRIVATE-FILE). Reads go through the CLI's
one small-file reader, `decoy.cli.io.read_small_file`, with a cap per file kind.

Every failure leaves as `LibraryError` with `library_write_failed` or `library_read_failed`
and the error class, raised after the `except` block so no path text is chained.
"""

from __future__ import annotations

from pathlib import Path

from decoy._atomic import AtomicWriteError, WriteMode, write_atomic, write_local_target
from decoy._private_file import PRIVATE_EXISTS, PrivateFileError, create_private_directory
from decoy.cli.io import UnsafeFileError, read_small_file
from decoy.cli.library._errors import (
    LIBRARY_FILE_TOO_LARGE,
    LIBRARY_READ_FAILED,
    LIBRARY_WRITE_FAILED,
    LibraryError,
    library_error,
)

__all__ = ["ensure_private_dir", "read_capped", "write_dotfile_once", "write_once"]


def ensure_private_dir(path: Path) -> None:
    """Make `path` an owner-only folder if it is missing; its parent must exist.

    An existing folder (another writer's, or the user's) is accepted as it is.
    """
    failure: BaseException | None = None
    try:
        create_private_directory(path)
    except PrivateFileError as exc:
        if exc.code != PRIVATE_EXISTS or not path.is_dir():
            failure = exc
    if failure is not None:
        raise library_error(LIBRARY_WRITE_FAILED, failure)


def write_once(directory: Path, name: str, data: bytes, *, tmp_dir: Path) -> bool:
    """Create `directory/name` with `data` unless it exists; True when this call created it.

    False means a file was already there; the caller verifies it.
    """
    failure: AtomicWriteError | None = None
    created = False
    try:
        created = write_atomic(directory, name, data, WriteMode.CREATE_ONCE, tmp_dir=tmp_dir)
    except AtomicWriteError as exc:
        failure = exc
    if failure is not None:
        raise library_error(LIBRARY_WRITE_FAILED, failure)
    return created


def write_dotfile_once(path: Path, data: bytes) -> bool:
    """Create the dot-named file `path` unless it exists; an existing one is never edited."""
    failure: AtomicWriteError | None = None
    created = False
    try:
        created = write_local_target(path, data, WriteMode.CREATE_ONCE)
    except AtomicWriteError as exc:
        failure = exc
    if failure is not None:
        raise library_error(LIBRARY_WRITE_FAILED, failure)
    return created


def read_capped(path: Path, max_bytes: int) -> bytes | None:
    """The bytes of the plain regular file at `path`, or None when nothing is there.

    The read goes through the CLI's one small-file reader (`decoy.cli.io.read_small_file`), so a
    symlink, FIFO, device or a file swapped between check and open is refused and never followed
    or waited on (`library_read_failed`). A file over `max_bytes` is refused unread past the cap
    (`library_file_too_large`); a file whose length changed during the read is refused too.
    """
    failure: UnsafeFileError | None = None
    found = None
    try:
        found = read_small_file(path, max_bytes + 1)
    except UnsafeFileError as exc:
        failure = exc
    if failure is not None:
        raise library_error(LIBRARY_READ_FAILED, failure)
    if found is None:
        return None
    if found.size > max_bytes or len(found.data) > max_bytes:
        raise LibraryError(LIBRARY_FILE_TOO_LARGE)
    if len(found.data) != found.size:
        raise LibraryError(LIBRARY_READ_FAILED)
    return found.data
