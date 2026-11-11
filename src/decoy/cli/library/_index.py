"""The library index and the library lock: one SQLite file, `library/index.sqlite` (plan 4.4, 4.8).

The object files are the truth; the index is a rebuildable cache of their envelope fields
(`records`, `links`, `tables`; `PRAGMA user_version` for its schema). A version mismatch or any
corruption means rebuild, never migrate. Rows of a kind this version does not know are kept with
`known = 0` (plan 4.3a). Plan 4.4 compares this with a directory scan only (MLflow's file-store
cost) and with records inside SQLite (no longer committable or addressable by path).

The one open: the file is pre-created 0600 with `_private_file.open_private` before
`sqlite3.connect` (the token-vault recipe; SQLite gives its journal the database file's mode),
then `BEGIN IMMEDIATE` takes the library lock, which every ref update, index write and (later)
prune and clean hold (plan 4.8; sqlite.org/lockingv3.html). A file that is not a database is
replaced by an empty one through the atomic writer and the lock is taken again; the inode is
checked after locking, so a process that locked a file another one just replaced retries on the
live file (the lock-then-verify pattern of lock files). A waiter gives up after
`BUSY_TIMEOUT_SECONDS` with `library_busy`; any other failure is `library_lock_unavailable`.

Freshness (plan 4.4): every locked open lists the object file names (one `os.scandir` per fan-out
folder, no file reads), inserts rows for ids the index lacks and drops rows whose file is gone,
in one transaction. A crash between the object link and the insert, a `git pull` and a fresh
clone are all caught up this way.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decoy._private_file import PrivateFileError, open_private
from decoy.cli.library._errors import (
    LIBRARY_BUSY,
    LIBRARY_LOCK_UNAVAILABLE,
    library_error,
)
from decoy.cli.library._fs import replace_file
from decoy.cli.library._paths import INDEX_FILE, record_digest

__all__ = [
    "BUSY_TIMEOUT_SECONDS",
    "SCHEMA_VERSION",
    "IndexRow",
    "all_rows",
    "ensure_schema",
    "insert",
    "latest",
    "locked",
    "object_ids",
    "row_from",
    "select",
    "sync",
]

SCHEMA_VERSION = 1
BUSY_TIMEOUT_SECONDS = 5.0  # read at call time, so a test can shorten it
_INODE_RETRIES = 3
_SUFFIX = ".json"
# SQLITE_BUSY and SQLITE_LOCKED; `sqlite_errorcode` exists from Python 3.11.
_BUSY_CODES = frozenset({5, 6})
_SCHEMA = (
    "CREATE TABLE records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload_schema TEXT NOT NULL,"
    " created_at TEXT NOT NULL, invocation_id TEXT NOT NULL, pipeline TEXT, status TEXT,"
    " payload_digest TEXT NOT NULL, size INTEGER NOT NULL, known INTEGER NOT NULL)",
    "CREATE TABLE links(src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL)",
    "CREATE TABLE tables(id TEXT NOT NULL, table_name TEXT NOT NULL)",
    "CREATE INDEX records_kind ON records(kind, created_at, id)",
    "CREATE INDEX links_dst ON links(dst)",
    "CREATE INDEX tables_id ON tables(id)",
)


@dataclass(frozen=True)
class IndexRow:
    """The indexed fields of one record. `known` is False for a kind this version cannot read."""

    id: str
    kind: str
    payload_schema: str
    created_at: str
    invocation_id: str
    pipeline: str | None
    status: str | None
    payload_digest: str
    size: int
    known: bool
    tables: tuple[str, ...] = ()
    links: tuple[tuple[str, str], ...] = ()


def row_from(raw: Mapping[str, Any], size: int, known: bool) -> IndexRow:
    """The row for a verified envelope (`DecodedRecord.raw`, `OpaqueRecord.raw` or a built one)."""
    labels = raw.get("labels") or {}
    links = tuple((str(link["rel"]), str(link["id"])) for link in raw.get("links") or ())
    return IndexRow(
        id=str(raw["id"]),
        kind=str(raw["kind"]),
        payload_schema=str(raw["payload_schema"]),
        created_at=str(raw["created_at"]),
        invocation_id=str(raw["invocation_id"]),
        pipeline=labels.get("pipeline"),
        status=labels.get("status"),
        payload_digest=str(raw["payload_digest"]),
        size=size,
        known=known,
        tables=tuple(str(t) for t in labels.get("tables") or ()),
        links=links,
    )


def object_ids(objects_dir: Path) -> set[str]:
    """Every record id under `objects/`, from file names only (no file is opened)."""
    found: set[str] = set()
    try:
        fans = [e for e in os.scandir(objects_dir) if e.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        return found
    for fan in fans:
        with os.scandir(fan.path) as entries:
            for entry in entries:
                if not entry.name.endswith(_SUFFIX):
                    continue
                candidate = f"sha256:{fan.name}{entry.name[: -len(_SUFFIX)]}"
                if record_digest(candidate) is not None:
                    found.add(candidate)
    return found


def _is_busy(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        return code in _BUSY_CODES
    return "locked" in str(exc)  # Python 3.10: "database is locked" / "database table is locked"


def _is_corrupt(exc: BaseException) -> bool:
    # "file is not a database" is a DatabaseError but not an OperationalError.
    return isinstance(exc, sqlite3.DatabaseError) and not isinstance(exc, sqlite3.OperationalError)


def _inode(path: Path) -> tuple[int, int] | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_dev, info.st_ino


def _begin(path: Path) -> tuple[sqlite3.Connection | None, BaseException | None, bool]:
    """Open the file 0600 and take the lock: (connection, failure, still the live file)."""
    conn: sqlite3.Connection | None = None
    try:
        open_private(path, new_parent=False)
        before = _inode(path)
        conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()  # reads the header
    except (PrivateFileError, sqlite3.Error) as exc:
        if conn is not None:
            conn.close()
        return None, exc, True
    return conn, None, before is not None and before == _inode(path)


@contextlib.contextmanager
def locked(library_dir: Path, *, tmp_dir: Path) -> Iterator[sqlite3.Connection]:
    """Hold the library lock on `library_dir/index.sqlite`; commit on a clean exit.

    Raises `LibraryError` (`library_busy`, `library_lock_unavailable`) before the block runs.
    """
    path = library_dir / INDEX_FILE
    conn: sqlite3.Connection | None = None
    failure: BaseException | None = None
    reset = False
    for _ in range(_INODE_RETRIES):
        conn, failure, live = _begin(path)
        if failure is not None and _is_corrupt(failure) and not reset:
            reset = True
            replace_file(library_dir, INDEX_FILE, b"", tmp_dir=tmp_dir)  # a cache: start empty
            continue
        if conn is not None and not live:
            conn.close()  # locked a file that was replaced meanwhile: lock the live one
            conn, failure = None, None
            continue
        break
    if conn is None:
        code = (
            LIBRARY_BUSY if failure is not None and _is_busy(failure) else LIBRARY_LOCK_UNAVAILABLE
        )
        raise library_error(code, failure)
    try:
        yield conn
        conn.execute("COMMIT")
    finally:
        if conn.in_transaction:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
        conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the tables; an index of another schema version is dropped and rebuilt."""
    if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
        return
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        conn.execute(f'DROP TABLE "{name}"')
    for statement in _SCHEMA:
        conn.execute(statement)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def insert(conn: sqlite3.Connection, row: IndexRow) -> None:
    conn.execute("DELETE FROM links WHERE src = ?", (row.id,))
    conn.execute("DELETE FROM tables WHERE id = ?", (row.id,))
    conn.execute(
        "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.id, row.kind, row.payload_schema, row.created_at, row.invocation_id,
            row.pipeline, row.status, row.payload_digest, row.size, int(row.known),
        ),
    )  # fmt: skip
    conn.executemany("INSERT INTO links VALUES (?, ?, ?)", [(row.id, r, d) for r, d in row.links])
    conn.executemany("INSERT INTO tables VALUES (?, ?)", [(row.id, t) for t in row.tables])


def _delete(conn: sqlite3.Connection, record_id: str) -> None:
    for table, column in (("records", "id"), ("links", "src"), ("tables", "id")):
        conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (record_id,))


def sync(
    conn: sqlite3.Connection, on_disk: set[str], load: Callable[[str], IndexRow | None]
) -> None:
    """Make the index match the object names: insert what is missing, drop what is gone."""
    indexed = {r[0] for r in conn.execute("SELECT id FROM records")}
    for gone in sorted(indexed - on_disk):
        _delete(conn, gone)
    for new in sorted(on_disk - indexed):
        row = load(new)
        if row is not None:
            insert(conn, row)


def all_rows(conn: sqlite3.Connection) -> list[IndexRow]:
    tables: dict[str, list[str]] = {}
    for record_id, name in conn.execute("SELECT id, table_name FROM tables ORDER BY rowid"):
        tables.setdefault(record_id, []).append(name)
    links: dict[str, list[tuple[str, str]]] = {}
    for src, rel, dst in conn.execute("SELECT src, rel, dst FROM links ORDER BY rowid"):
        links.setdefault(src, []).append((rel, dst))
    rows = conn.execute("SELECT * FROM records").fetchall()
    return [
        IndexRow(
            *r[:9],
            known=bool(r[9]),
            tables=tuple(tables.get(r[0], ())),
            links=tuple(links.get(r[0], ())),
        )
        for r in rows
    ]


def select(
    rows: Iterable[IndexRow],
    *,
    kind: str | None = None,
    pipeline: str | None = None,
    table: str | None = None,
) -> list[IndexRow]:
    """Rows matching every given filter, oldest first by `(created_at, id)`."""
    picked = [
        r
        for r in rows
        if (kind is None or r.kind == kind)
        and (pipeline is None or r.pipeline == pipeline)
        and (table is None or table in r.tables)
    ]
    return sorted(picked, key=lambda r: (r.created_at, r.id))


def latest(rows: Iterable[IndexRow], **filters: str | None) -> str | None:
    """`latest` is virtual (plan 4.5): the largest `(created_at, id)` of the matching rows."""
    picked = select(rows, **filters)
    return picked[-1].id if picked else None
