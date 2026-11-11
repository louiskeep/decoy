"""Named refs and the library lock (plan 4.5, 4.8; L1b.3).

A ref is git's named ref: a small file `library/refs/<kind>/<name>` holding one record id and a
newline. It is replaced in one step through `_atomic` (`REPLACE`, which retries a held-open
target on Windows), so a reader sees the old id or the new one. Refs are the roots prune keeps.

Every ref update runs under the library lock: `BEGIN IMMEDIATE` on `library/index.sqlite`.
SQLite locking behaves the same on Linux, macOS and Windows, so there is no `fcntl` lock and no
lock file with stale-holder rules (plan 4.8; sqlite.org/lockingv3.html). The file is pre-created
0600 through `_private_file.open_private` before `sqlite3.connect`, the token-vault recipe, so
SQLite never creates it with the umask mode. Until L1c it holds no tables, only the lock. A
waiter gives up after `BUSY_TIMEOUT_SECONDS` with `library_busy` and never overwrites; a lock
that cannot be taken at all is `library_lock_unavailable`. The target's existence is checked
under the lock, so a later prune (which takes the same lock) cannot remove it in between.

`latest` is virtual and computed from the index (L1c); it is not a stored ref.
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from decoy_engine import records

from decoy._private_file import PrivateFileError, open_private
from decoy.cli.library._errors import (
    LIBRARY_BUSY,
    LIBRARY_LOCK_UNAVAILABLE,
    RECORD_CORRUPT,
    REF_NAME_INVALID,
    LibraryError,
    library_error,
)
from decoy.cli.library._fs import ensure_private_dir, read_file, replace_file
from decoy.cli.library._paths import INDEX_FILE, REFS, record_digest

if TYPE_CHECKING:
    from decoy.cli.library._store import Library

__all__ = ["BUSY_TIMEOUT_SECONDS", "library_lock", "read_ref", "set_ref"]

BUSY_TIMEOUT_SECONDS = 5.0  # read at call time, so a test can shorten it
# One name segment (plan 4.5); a name may hold two, `<scope>/<name>`, for a pipeline scope.
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_MAX_SEGMENTS = 2
# SQLITE_BUSY and SQLITE_LOCKED; `sqlite_errorcode` exists from Python 3.11.
_BUSY_CODES = frozenset({5, 6})


def _ref_parts(kind: str, name: str) -> tuple[str, ...]:
    """The path parts under `refs/`; `ref_name_invalid` for anything outside the grammar."""
    kinds = {spec.kind for spec in records.registered_kinds()}
    parts = name.split("/")
    ok = (
        kind in kinds
        and len(parts) <= _MAX_SEGMENTS
        and all(_SEGMENT.fullmatch(part) for part in parts)
    )
    if not ok:
        raise LibraryError(REF_NAME_INVALID)
    return (kind, *parts)


def _is_busy(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        return code in _BUSY_CODES
    return "locked" in str(exc)  # Python 3.10: "database is locked" / "database table is locked"


@contextlib.contextmanager
def library_lock(library_dir: Path) -> Iterator[None]:
    """Hold the library lock for the block. Raises `LibraryError` before the block runs."""
    path = library_dir / INDEX_FILE
    failure: BaseException | None = None
    conn: sqlite3.Connection | None = None
    try:
        open_private(path, new_parent=False)
        conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None)
        conn.execute("BEGIN IMMEDIATE")
    except (PrivateFileError, sqlite3.Error) as exc:
        failure = exc
    if failure is not None:
        if conn is not None:
            conn.close()
        raise library_error(
            LIBRARY_BUSY if _is_busy(failure) else LIBRARY_LOCK_UNAVAILABLE, failure
        )
    assert conn is not None
    try:
        yield
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")  # nothing was written; this only releases the lock
        conn.close()


def set_ref(library: Library, kind: str, name: str, record_id: str) -> None:
    """Point the ref at `record_id`, which must be stored. Raises `LibraryError`:
    `ref_name_invalid`, `record_not_found`, `record_corrupt`, `library_busy`,
    `library_lock_unavailable` or `library_write_failed`."""
    parts = _ref_parts(kind, name)
    library.prepare()
    with library_lock(library.library_dir):
        library.get(record_id)  # exists and is the record its id names
        folder = library.library_dir / REFS
        ensure_private_dir(folder)
        for part in parts[:-1]:
            folder = folder / part
            ensure_private_dir(folder)
        replace_file(folder, parts[-1], f"{record_id}\n".encode(), tmp_dir=library.tmp_dir)


def read_ref(library: Library, kind: str, name: str) -> str | None:
    """The id the ref holds, or None when it is not set. A ref file is replaced in one step, so
    it is read without the lock. A file that holds no record id is `record_corrupt`."""
    path = library.library_dir / REFS
    for part in _ref_parts(kind, name):
        path = path / part
    data = read_file(path)
    if data is None:
        return None
    text = data.decode("utf-8", errors="replace").strip()
    if record_digest(text) is None:
        raise LibraryError(RECORD_CORRUPT)
    return text
