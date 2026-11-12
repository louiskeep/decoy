"""Index failures after the lock is taken, and the one lock file (review round 1 on #209).

The index is a cache (plan 4.4): a SQLite error after `BEGIN IMMEDIATE` must never escape as a
raw `sqlite3.Error`, a corrupt index is reset and rebuilt, and "a failed index update never fails
put" holds. The reset truncates the file in place, so every process locks one inode and two
holders cannot coexist; prune and clean depend on that lock.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest
from tests.unit.library._helpers import envelope, object_path, start_child

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, _index, open_library
from decoy.cli.library._errors import LIBRARY_BUSY

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX inode identity")


def _local(_p: Path) -> None:
    return None


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


def _index_file(root: Path) -> Path:
    return root / "library" / "index.sqlite"


def _put_many(root: Path, count: int) -> list[str]:
    library = open_library(root, probe=_local)
    return [library.put(envelope(n)).id for n in range(count)]


def _integrity(root: Path) -> str:
    conn = sqlite3.connect(str(_index_file(root)))
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


def _corrupt_after_first_page(root: Path) -> None:
    """Keep page 1 (the header and `sqlite_master`) and break every later page in place."""
    path = _index_file(root)
    data = bytearray(path.read_bytes())
    page = int.from_bytes(data[16:18], "big") or 65536
    assert len(data) > page  # non-vacuous: there are later pages to break
    data[page:] = b"\xa5" * (len(data) - page)
    with path.open("r+b") as handle:
        handle.write(bytes(data))


# -- item 1: no raw sqlite3.Error after the lock -------------------------------------------------


def test_an_index_with_corrupt_later_pages_opens_lists_and_is_rebuilt(root: Path) -> None:
    ids = _put_many(root, 40)
    _corrupt_after_first_page(root)
    with pytest.raises(sqlite3.DatabaseError):  # the file really is corrupt past page 1
        sqlite3.connect(str(_index_file(root))).execute("SELECT * FROM records").fetchall()
    library = open_library(root, probe=_local)  # must not raise
    assert sorted(r.id for r in library.rows()) == sorted(ids)
    assert library.latest("sample-run") == max(ids)
    open_library(root, probe=_local)
    assert _integrity(root) == "ok"  # the next locked open left a rebuilt, valid index


def test_a_current_version_index_with_missing_tables_is_rebuilt(root: Path) -> None:
    ids = _put_many(root, 3)
    conn = sqlite3.connect(str(_index_file(root)))
    conn.execute("DROP TABLE records")
    conn.execute("DROP TABLE links")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _index.SCHEMA_VERSION
    conn.close()
    library = open_library(root, probe=_local)  # must not raise
    assert sorted(r.id for r in library.rows()) == sorted(ids)


def test_a_failed_insert_after_the_object_is_stored_never_fails_put(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def full_disk(conn: sqlite3.Connection, row: _index.IndexRow) -> None:
        calls.append(row.id)
        raise sqlite3.OperationalError("database or disk is full")

    library = open_library(root, probe=_local)
    env = envelope()
    monkeypatch.setattr(_index, "insert", full_disk)
    result = library.put(env)  # must not raise
    assert calls and calls[-1] == env.id  # non-vacuous: the insert really failed
    assert result.id == env.id and object_path(root, env.id).is_file()
    monkeypatch.undo()
    assert [r.id for r in open_library(root, probe=_local).rows()] == [env.id]  # caught up


def test_a_failed_commit_after_the_object_is_stored_never_fails_put(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def failing(conn: sqlite3.Connection) -> None:
        calls.append(1)
        raise sqlite3.OperationalError("disk I/O error")

    library = open_library(root, probe=_local)
    library.put(envelope(0))
    env = envelope(1)
    monkeypatch.setattr(_index, "_commit", failing, raising=False)
    result = library.put(env)  # must not raise
    assert calls  # non-vacuous: the commit really failed
    assert result.id == env.id and object_path(root, env.id).is_file()
    monkeypatch.undo()
    assert env.id in {r.id for r in open_library(root, probe=_local).rows()}


def test_no_raw_sqlite_error_leaves_the_lock(root: Path) -> None:
    _put_many(root, 1)
    library = open_library(root, probe=_local)
    with pytest.raises(LibraryError) as caught:
        with _index.locked(library.library_dir) as conn:
            conn.execute("SELECT * FROM no_such_table")
    err = caught.value
    assert err.code == "library_index_failed" and err.error_class == "OperationalError"
    # A `with` body's error is always the context of what its exit raises; it is suppressed, so
    # no traceback renders the SQLite text, and the library error never holds it.
    assert err.__cause__ is None and err.__suppress_context__
    assert "no_such_table" not in str(err) and "no_such_table" not in repr(err)


# -- item 3: a schema rebuilt mid-process still answers ------------------------------------------


def test_rows_and_latest_survive_a_rebuild_in_the_same_process(root: Path) -> None:
    ids = _put_many(root, 3)
    library = open_library(root, probe=_local)
    assert len(library.rows()) == 3
    conn = sqlite3.connect(str(_index_file(root)))
    conn.execute(f"PRAGMA user_version = {_index.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    assert sorted(r.id for r in library.rows()) == sorted(ids)  # rebuilt, then synced
    assert library.latest("sample-run") == max(ids)


# -- item 2: the reset never replaces the file, so there is one lock ----------------------------

_HOLD = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from decoy.cli.library import _index\n"
    "lib, tmp, held, release = (Path(a) for a in sys.argv[1:5])\n"
    "try:\n"
    "    with _index.locked(lib) as conn:\n"
    "        held.write_text('held')\n"
    "        deadline = time.time() + 30\n"
    "        while not release.exists() and time.time() < deadline:\n"
    "            time.sleep(0.01)\n"
    "except Exception as exc:\n"
    "    print(type(exc).__name__)\n"
)


@posix_only
def test_two_processes_never_hold_the_lock_at_once_after_a_reset(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A holder keeps the lock; the index is then corrupted under it. A second opener that
    resets the corrupt file must wait for the holder, not lock a fresh file beside it."""
    _put_many(root, 2)
    library = open_library(root, probe=_local)
    held, release = tmp_path / "held", tmp_path / "release"
    child = start_child(
        _HOLD, str(library.library_dir), str(library.tmp_dir), str(held), str(release)
    )
    try:
        deadline = time.time() + 60
        while not held.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert held.exists(), child.stderr.read() if child.stderr else ""
        index = _index_file(root)
        before = os.stat(index).st_ino
        with index.open("r+b") as handle:  # the index goes bad while the child holds the lock
            handle.write(os.urandom(4096))
        monkeypatch.setattr(_index, "BUSY_TIMEOUT_SECONDS", 0.5)
        entered: list[bool] = []
        with pytest.raises(LibraryError) as caught:
            with _index.locked(library.library_dir):
                entered.append(True)
        assert entered == []  # one lock: the child still holds it
        assert caught.value.code == LIBRARY_BUSY
        assert os.stat(index).st_ino == before  # reset in place, never replaced
    finally:
        release.touch()
        child.communicate(timeout=60)
