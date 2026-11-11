"""The index (plan 4.4, 4.3a, 4.8; L1c.1): a rebuildable SQLite cache over the object files.

Rows C1-rebuild, C1-corrupt-index, C1-hand-added, C1-crash-gap, C1-gone-file, C1-unknown-kind,
C1-index-mode, C1-lock-unavailable, C1-remote-fs and C1-list-no-parse. Prune and clean do not
exist yet, so C1-lock-unavailable covers `put` and ref set only; `library path` arrives in
L1c.2, so C1-remote-fs asserts the library object's degraded state and reason.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import sys
from pathlib import Path

import pytest
from decoy_engine import records
from tests.unit.library._helpers import envelope, object_path, start_child

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, _index, open_library
from decoy.cli.library._errors import LIBRARY_LOCK_UNAVAILABLE

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


def _index_file(root: Path) -> Path:
    return root / "library" / "index.sqlite"


def _rows(root: Path) -> set[str]:
    conn = sqlite3.connect(str(_index_file(root)))
    try:
        return {r[0] for r in conn.execute("SELECT id FROM records")}
    finally:
        conn.close()


def _put_many(root: Path, count: int) -> list[str]:
    library = open_library(root, probe=lambda _p: None)
    return [library.put(envelope(n)).id for n in range(count)]


# -- put inserts after the object, and queries -------------------------------------------------


def test_put_indexes_the_record_and_latest_is_virtual(root: Path) -> None:
    ids = _put_many(root, 3)
    assert _rows(root) == set(ids)
    library = open_library(root, probe=lambda _p: None)
    rows = library.rows(kind="sample-run")
    assert [r.id for r in rows] == sorted(ids)  # same created_at, so ordered by id
    assert {r.known for r in rows} == {True}
    assert library.latest("sample-run") == max(ids)  # the largest (created_at, id)
    assert library.latest("evidence") is None
    assert not (root / "library" / "refs").exists()  # latest is never stored as a ref


def test_latest_filters_by_pipeline_and_table(root: Path) -> None:
    library = open_library(root, probe=lambda _p: None)
    base = json.loads(records.encode(envelope(0)))
    payload = base["payload"]
    a = records.build(
        "sample-run", payload, producer=base["producer"], invocation_id=base["invocation_id"],
        created_at=_utc("2026-11-11T00:00:00"), labels={"pipeline": "a.yaml", "tables": ["orders"]},
    )  # fmt: skip
    b = records.build(
        "sample-run", payload, producer=base["producer"], invocation_id=base["invocation_id"],
        created_at=_utc("2026-11-12T00:00:00"), labels={"pipeline": "b.yaml", "tables": ["users"]},
    )  # fmt: skip
    library.put(a)
    library.put(b)
    assert library.latest("sample-run") == b.id
    assert library.latest("sample-run", pipeline="a.yaml") == a.id
    assert library.latest("sample-run", table="orders") == a.id
    assert library.latest("sample-run", table="missing") is None
    rows = library.rows(pipeline="b.yaml")
    assert [(r.id, r.pipeline, r.tables) for r in rows] == [(b.id, "b.yaml", ("users",))]


def _utc(text: str):
    from datetime import datetime, timezone

    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# -- C1-rebuild --------------------------------------------------------------------------------


def test_a_deleted_index_is_rebuilt_on_the_next_open(root: Path) -> None:
    """MC1-norebuild covers the version case below; this one needs the freshness sync."""
    ids = _put_many(root, 4)
    before = _rows(root)
    _index_file(root).unlink()
    open_library(root, probe=lambda _p: None)
    assert _rows(root) == before == set(ids)


def test_an_index_of_another_version_is_rebuilt_not_migrated(root: Path) -> None:
    """MC1-norebuild: keeping the old tables leaves an index the new code cannot use; red."""
    ids = _put_many(root, 3)
    _index_file(root).unlink()
    conn = sqlite3.connect(str(_index_file(root)), isolation_level=None)
    conn.execute("CREATE TABLE records(id TEXT)")
    conn.execute("INSERT INTO records VALUES ('stale')")
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    library = open_library(root, probe=lambda _p: None)
    assert _rows(root) == set(ids)
    assert [r.id for r in library.rows()] == sorted(ids)
    conn = sqlite3.connect(str(_index_file(root)))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _index.SCHEMA_VERSION
    conn.close()


# -- C1-corrupt-index --------------------------------------------------------------------------


def test_random_bytes_in_the_index_still_list_and_are_rebuilt(root: Path) -> None:
    """MC1-crash: letting the SQLite error escape the open turns this red."""
    ids = _put_many(root, 3)
    _index_file(root).write_bytes(os.urandom(4096))
    with pytest.raises(sqlite3.DatabaseError):  # non-vacuous: the file really is not a database
        sqlite3.connect(str(_index_file(root))).execute("SELECT 1 FROM records")
    library = open_library(root, probe=lambda _p: None)
    assert [r.id for r in library.rows()] == sorted(ids)
    assert _rows(root) == set(ids)
    assert library.degraded is None


# -- C1-hand-added, C1-gone-file ---------------------------------------------------------------


def test_a_hand_added_object_is_listed_without_fsck(root: Path, tmp_path: Path) -> None:
    """MC1-trust-index: skipping the freshness listing hides the copied record; red."""
    _put_many(root, 2)
    other = tmp_path / "other" / DECOY_DIR
    (other.parent).mkdir()
    extra = envelope(7)
    open_library(other, probe=lambda _p: None).put(extra)
    target = object_path(root, extra.id)
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(object_path(other, extra.id), target)  # as `git pull` would
    assert extra.id not in _rows(root)  # non-vacuous: the index did not know it
    library = open_library(root, probe=lambda _p: None)
    assert extra.id in {r.id for r in library.rows()}
    assert library.latest("sample-run") == max([*_rows(root)])
    assert extra.id in _rows(root)


def test_a_hand_deleted_object_drops_its_row(root: Path) -> None:
    """MC1-keep-rows: keeping rows whose file is gone turns this red."""
    ids = _put_many(root, 3)
    object_path(root, ids[0]).unlink()
    assert ids[0] in _rows(root)  # non-vacuous: the row was there
    library = open_library(root, probe=lambda _p: None)
    assert ids[0] not in {r.id for r in library.rows()}
    assert ids[0] not in _rows(root)


# -- C1-crash-gap ------------------------------------------------------------------------------

_KILL_BEFORE_INSERT = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from tests.unit.library._helpers import envelope\n"
    "from decoy.cli.library import _index, open_library\n"
    "def stall(*_a, **_k):\n"
    "    print('inserting', flush=True)\n"
    "    time.sleep(60)\n"
    "_index.insert = stall\n"
    "open_library(Path(sys.argv[1]), probe=lambda _p: None).put(envelope(5))\n"
)


def test_a_writer_killed_between_link_and_insert_is_caught_up(root: Path) -> None:
    """MC1-insert-first: inserting the row before the object exists turns this red."""
    _put_many(root, 1)
    child = start_child(_KILL_BEFORE_INSERT, str(root))
    try:
        assert child.stdout is not None
        line = child.stdout.readline().strip()
    finally:
        child.kill()
        child.wait()
    assert line == "inserting", child.stderr.read() if child.stderr else ""
    missing = envelope(5).id
    assert object_path(root, missing).is_file()  # the object was linked before the insert
    assert missing not in _rows(root)
    library = open_library(root, probe=lambda _p: None)
    assert missing in {r.id for r in library.rows()}
    assert missing in _rows(root)


# -- C1-unknown-kind ---------------------------------------------------------------------------


def _pull_future_thing(root: Path) -> str:
    raw = json.loads(records.encode(envelope(3)))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["created_at"] = "2027-01-01T00:00:00.000000Z"  # newer than every known record
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    return str(raw["id"])


def test_an_unknown_kind_is_indexed_as_opaque(root: Path) -> None:
    """MC1-unknown-crash: indexing only registered kinds and raising on others turns this red."""
    ids = _put_many(root, 2)
    future = _pull_future_thing(root)
    library = open_library(root, probe=lambda _p: None)
    rows = {r.id: r for r in library.rows()}
    assert set(rows) == {*ids, future}
    assert (rows[future].kind, rows[future].known) == ("future-thing", False)
    assert rows[future].created_at == "2027-01-01T00:00:00.000000Z"
    assert library.latest("sample-run") == max(ids)  # unchanged by the newer opaque record
    assert library.latest("future-thing") == future


# -- C1-index-mode -----------------------------------------------------------------------------


@posix_only
def test_the_index_is_0600_before_any_sql_runs(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MC1-umask: letting `sqlite3.connect` create the file gives the umask mode; red."""
    seen: list[tuple[bool, int]] = []
    real = sqlite3.connect

    def spy(database: str, *args: object, **kwargs: object) -> sqlite3.Connection:
        path = Path(database)
        seen.append((path.exists(), stat.S_IMODE(os.stat(path).st_mode) if path.exists() else 0))
        return real(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", spy)
    old = os.umask(0)
    try:
        open_library(root, probe=lambda _p: None).put(envelope())  # the first index open
    finally:
        os.umask(old)
    assert seen and seen[0] == (True, 0o600)  # non-vacuous: at least the first connect seen
    assert set(seen) == {(True, 0o600)}
    assert stat.S_IMODE(os.stat(_index_file(root)).st_mode) == 0o600


# -- C1-lock-unavailable -----------------------------------------------------------------------


def test_an_unlockable_index_degrades_put_works_and_refs_refuse(root: Path) -> None:
    """MC1-unlocked-ref: moving a ref without the lock turns this red. (Prune and clean do not
    exist yet; they will refuse the same way.)"""
    first = _put_many(root, 1)[0]
    _index_file(root).unlink()
    _index_file(root).mkdir()  # a folder where the lock file must be: it cannot be opened
    library = open_library(root, probe=lambda _p: None)
    assert library.degraded == "lock_unavailable"
    second = library.put(envelope(1)).id  # the object file is the truth
    assert object_path(root, second).is_file()
    with pytest.raises(LibraryError) as caught:
        library.set_ref("sample-run", "baseline", first)
    assert caught.value.code == LIBRARY_LOCK_UNAVAILABLE
    assert not (root / "library" / "refs").exists()
    assert {r.id for r in library.rows()} == {first, second}  # listed from the files


# -- C1-remote-fs ------------------------------------------------------------------------------


def test_a_remote_root_is_degraded_and_refs_refuse(root: Path) -> None:
    """MC1-trust-lock: ignoring the probe lets the ref through on a remote mount; red."""
    first = _put_many(root, 1)[0]
    probed: list[Path] = []

    def nfs(path: Path) -> str | None:
        probed.append(path)
        return "nfs"

    library = open_library(root, probe=nfs)
    assert len(probed) == 1  # once per open
    assert (library.degraded, library.filesystem) == ("remote_filesystem", "nfs")
    assert library.put(envelope(1)).created is True
    with pytest.raises(LibraryError) as caught:
        library.set_ref("sample-run", "baseline", first)
    assert caught.value.code == LIBRARY_LOCK_UNAVAILABLE
    local = open_library(root, probe=lambda _p: None)
    assert local.degraded is None
    local.set_ref("sample-run", "baseline", first)
    assert local.read_ref("sample-run", "baseline") == first


# -- C1-list-no-parse --------------------------------------------------------------------------


def _write_objects(root: Path, count: int) -> list[str]:
    """Object files written directly (no fsync, no index), so a 5 000-record fixture is cheap."""
    open_library(root, probe=lambda _p: None).put(envelope(0))
    ids = []
    for n in range(1, count):
        env = envelope(n)
        target = object_path(root, env.id)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(records.encode(env))
        ids.append(env.id)
    return [envelope(0).id, *ids]


# Every file open in this process while a list is active (audit event "open" covers io.open,
# os.open and pathlib, which binds io.open at import on Python 3.10).
_OPENS: list[list[str]] = []


def _audit(event: str, args: tuple) -> None:  # type: ignore[type-arg]
    if event == "open" and _OPENS and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENS[-1].append(os.fsdecode(args[0]))


sys.addaudithook(_audit)


@pytest.mark.timeout(600)
def test_listing_a_fresh_index_opens_no_object_file(root: Path) -> None:
    """MC1-parse-all: listing by parsing every object opens 5 000 files; red. (The 1-second
    budget is a separate T4 performance marker, not asserted here.)"""
    ids = _write_objects(root, 5000)
    open_library(root, probe=lambda _p: None)  # the catch-up open parses the new files once
    assert len(_rows(root)) == 5000
    marker = os.sep + "objects" + os.sep
    seen: list[str] = []
    _OPENS.append(seen)
    try:
        library = open_library(root, probe=lambda _p: None)
        rows = library.rows(kind="sample-run")
        under_objects = [p for p in seen if marker in p]
        object_path(root, ids[0]).read_bytes()  # non-vacuous: the hook does see an object open
    finally:
        _OPENS.pop()
    assert len(rows) == 5000 and {r.id for r in rows} == set(ids)
    assert under_objects == []
    assert [p for p in seen if marker in p] == [str(object_path(root, ids[0]))]
