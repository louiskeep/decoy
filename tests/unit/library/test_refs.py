"""Refs (plan 4.5, 4.8; L1b.3): `library/refs/<kind>/<name>` holding one record id, moved under
the library lock (`BEGIN IMMEDIATE` on `library/index.sqlite`).

B1-ref-race, B1-win-retry, the lock-wait case that makes MB1-nolock deterministic, name rules,
missing targets and the 0600 lock file.
"""

from __future__ import annotations

import errno
import os
import sqlite3
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from tests.unit.library._helpers import envelope, start_child

from decoy import _atomic, _private_file
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, _index, open_library
from decoy.cli.library._errors import (
    LIBRARY_BUSY,
    LIBRARY_LOCK_UNAVAILABLE,
    RECORD_NOT_FOUND,
    REF_NAME_INVALID,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


def _ref_file(root: Path, kind: str, name: str) -> Path:
    return root / "library" / "refs" / kind / name


def _stored(root: Path, n: int = 0) -> str:
    env = envelope(n)
    open_library(root).put(env)
    return env.id


# -- basics -----------------------------------------------------------------------------------


def test_set_then_read_a_ref(root: Path) -> None:
    a, b = _stored(root, 0), _stored(root, 1)
    library = open_library(root)
    assert library.read_ref("sample-run", "baseline") is None
    library.set_ref("sample-run", "baseline", a)
    assert _ref_file(root, "sample-run", "baseline").read_text(encoding="utf-8") == a + "\n"
    library.set_ref("sample-run", "pipelines-p/baseline", b)
    library.set_ref("sample-run", "baseline", b)
    assert library.read_ref("sample-run", "baseline") == b
    assert library.read_ref("sample-run", "pipelines-p/baseline") == b


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("sample-run", ""),
        ("sample-run", "Baseline"),
        ("sample-run", "-x"),
        ("sample-run", ".hidden"),
        ("sample-run", "a/b/c"),
        ("sample-run", "../x"),
        ("sample-run", "a/"),
        ("sample-run", "/a"),
        ("sample-run", "x" * 65),
        ("sample-run", "a b"),
        ("Sample-run", "baseline"),
        ("future-thing", "baseline"),
        ("../objects", "baseline"),
    ],
)
def test_a_bad_kind_or_name_is_refused_before_anything_is_written(
    root: Path, kind: str, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _stored(root)
    library = open_library(root)
    locks: list[object] = []
    real = _index.locked
    monkeypatch.setattr(_index, "locked", lambda *a, **k: locks.append(a) or real(*a, **k))
    with pytest.raises(LibraryError) as caught:
        library.set_ref(kind, name, target)
    assert caught.value.code == REF_NAME_INVALID
    assert not (root / "library" / "refs").exists()
    assert locks == []  # refused before the lock (put now creates index.sqlite, L1c.1)


def test_the_name_grammar_accepts_its_edges(root: Path) -> None:
    target = _stored(root)
    library = open_library(root)
    names = ["a", "0", "a" * 64, "a.b-c_d", "scope/" + "n" * 64]
    for name in names:
        library.set_ref("sample-run", name, target)
    assert [library.read_ref("sample-run", name) for name in names] == [target] * len(names)


def test_a_missing_target_is_refused_and_writes_no_ref(root: Path) -> None:
    _stored(root)
    missing = envelope(9).id
    with pytest.raises(LibraryError) as caught:
        open_library(root).set_ref("sample-run", "baseline", missing)
    assert caught.value.code == RECORD_NOT_FOUND
    assert not _ref_file(root, "sample-run", "baseline").exists()


@posix_only
def test_ref_files_and_folders_are_owner_only(root: Path) -> None:
    target = _stored(root)
    old = os.umask(0)
    try:
        open_library(root).set_ref("sample-run", "scope/baseline", target)
    finally:
        os.umask(old)
    ref = _ref_file(root, "sample-run", "scope/baseline")
    assert stat.S_IMODE(os.stat(ref).st_mode) == 0o600
    for folder in (ref.parent, ref.parent.parent, root / "library" / "refs"):
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700


# -- the lock ---------------------------------------------------------------------------------


@posix_only
def test_the_lock_file_is_0600_before_any_sql_runs(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index is pre-created owner-only; sqlite never creates it (plan 4.4, MC1-umask)."""
    target = _stored(root)
    seen: list[tuple[str, int]] = []
    real = sqlite3.connect

    def spy(database: str, *args: object, **kwargs: object) -> sqlite3.Connection:
        path = Path(database)
        seen.append((path.name, stat.S_IMODE(os.stat(path).st_mode)))
        return real(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", spy)
    old = os.umask(0)
    try:
        open_library(root).set_ref("sample-run", "baseline", target)
    finally:
        os.umask(old)
    assert seen and set(seen) == {("index.sqlite", 0o600)}  # every connect found it 0600


def test_an_index_that_cannot_be_opened_is_lock_unavailable(root: Path) -> None:
    target = _stored(root)
    (root / "library" / "index.sqlite").unlink()  # put made it (L1c.1)
    (root / "library" / "index.sqlite").mkdir()  # a folder where the lock file must be
    with pytest.raises(LibraryError) as caught:
        open_library(root).set_ref("sample-run", "baseline", target)
    assert caught.value.code == LIBRARY_LOCK_UNAVAILABLE
    assert str(root) not in str(caught.value)
    assert not _ref_file(root, "sample-run", "baseline").exists()


_HOLD_LOCK = (
    "import sqlite3, sys, time\n"
    "from pathlib import Path\n"
    "db, release = sys.argv[1], Path(sys.argv[2])\n"
    "conn = sqlite3.connect(db, isolation_level=None)\n"
    "conn.execute('BEGIN IMMEDIATE')\n"
    "print('held', flush=True)\n"
    "while not release.exists():\n"
    "    time.sleep(0.01)\n"
    "conn.execute('ROLLBACK')\n"
)


def _hold_lock(root: Path, release: Path):
    holder = start_child(_HOLD_LOCK, str(root / "library" / "index.sqlite"), str(release))
    assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
    return holder


def test_a_second_setter_waits_for_the_lock_holder(root: Path, tmp_path: Path) -> None:
    """MB1-nolock, deterministic form: a ref update must not run while another process holds
    the library lock."""
    a, b = _stored(root, 0), _stored(root, 1)
    library = open_library(root)
    library.set_ref("sample-run", "baseline", a)  # also creates the lock file
    release = tmp_path / "release"
    holder = _hold_lock(root, release)
    done: list[object] = []
    worker = threading.Thread(
        target=lambda: done.append(library.set_ref("sample-run", "baseline", b) or "ok")
    )
    try:
        worker.start()
        time.sleep(0.5)
        assert worker.is_alive() and done == []  # blocked on the lock
        assert library.read_ref("sample-run", "baseline") == a  # nothing moved meanwhile
    finally:
        release.touch()
        worker.join(timeout=10)
        holder.wait(timeout=10)
    assert done == ["ok"]
    assert library.read_ref("sample-run", "baseline") == b


def test_the_loser_fails_with_library_busy_and_never_overwrites(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = _stored(root, 0), _stored(root, 1)
    library = open_library(root)
    library.set_ref("sample-run", "baseline", a)
    monkeypatch.setattr(_index, "BUSY_TIMEOUT_SECONDS", 0.2)
    release = tmp_path / "release"
    holder = _hold_lock(root, release)
    try:
        started = time.monotonic()
        with pytest.raises(LibraryError) as caught:
            library.set_ref("sample-run", "baseline", b)
        waited = time.monotonic() - started
    finally:
        release.touch()
        holder.wait(timeout=10)
    assert caught.value.code == LIBRARY_BUSY
    assert waited >= 0.15  # non-vacuous: it waited on the holder before giving up
    assert library.read_ref("sample-run", "baseline") == a


# -- B1-ref-race ------------------------------------------------------------------------------

_SET_MANY = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from decoy.cli.library import LibraryError, open_library\n"
    "root, go = Path(sys.argv[1]), Path(sys.argv[2])\n"
    "ids = sys.argv[3:]\n"
    "while not go.exists():\n"
    "    time.sleep(0.001)\n"
    "library = open_library(root)\n"
    "ok = busy = 0\n"
    "for i in range(20):\n"
    "    try:\n"
    "        library.set_ref('sample-run', 'baseline', ids[i % len(ids)])\n"
    "        ok += 1\n"
    "    except LibraryError as exc:\n"
    "        if exc.code != 'library_busy':\n"
    "            raise\n"
    "        busy += 1\n"
    "print(ok, busy)\n"
)


def test_two_processes_set_the_same_ref_twenty_times_each(root: Path, tmp_path: Path) -> None:
    ids = [_stored(root, n) for n in range(4)]
    go = tmp_path / "go"
    kids = [
        start_child(_SET_MANY, str(root), str(go), *ids[:2]),
        start_child(_SET_MANY, str(root), str(go), *ids[2:]),
    ]
    go.touch()
    counts = []
    for kid in kids:
        out, err = kid.communicate(timeout=180)
        assert kid.returncode == 0, err
        counts.append(tuple(int(x) for x in out.split()))
    assert all(ok + busy == 20 for ok, busy in counts)
    assert sum(ok for ok, _ in counts) > 0  # non-vacuous: refs were really moved
    assert open_library(root).read_ref("sample-run", "baseline") in ids
    assert [p for p in (root / "library" / "tmp").iterdir()] == []


# -- B1-win-retry -----------------------------------------------------------------------------


def _flaky_replace(monkeypatch: pytest.MonkeyPatch, fails: int) -> list[str]:
    calls: list[str] = []
    real = os.replace

    def replace(src: str, dst: str, **kw: object) -> None:
        if "refs" in str(dst):
            calls.append(str(dst))
            if fails < 0 or len(calls) <= fails:
                raise PermissionError(errno.EACCES, "held open", str(dst))
        real(src, dst, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(_atomic, "_sleep", lambda _s: None)
    monkeypatch.setattr(_private_file, "_WINDOWS", True)  # the Windows retry path, on Linux
    return calls


def test_a_ref_held_open_briefly_is_replaced_after_retries(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux run of B1-win-retry with the Windows branch forced (MB1-noretry turns it red)."""
    a, b = _stored(root, 0), _stored(root, 1)
    library = open_library(root)
    library.set_ref("sample-run", "baseline", a)
    calls = _flaky_replace(monkeypatch, fails=3)
    library.set_ref("sample-run", "baseline", b)
    assert len(calls) == 4  # three refusals, then the move
    monkeypatch.undo()
    assert library.read_ref("sample-run", "baseline") == b


def test_a_ref_held_open_past_the_window_is_library_busy(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = _stored(root, 0), _stored(root, 1)
    library = open_library(root)
    library.set_ref("sample-run", "baseline", a)
    calls = _flaky_replace(monkeypatch, fails=-1)
    with pytest.raises(LibraryError) as caught:
        library.set_ref("sample-run", "baseline", b)
    assert caught.value.code == LIBRARY_BUSY
    assert len(calls) == 10  # the writer's bounded retry, not a loop of its own
    monkeypatch.undo()
    assert library.read_ref("sample-run", "baseline") == a


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows lane: a held-open file blocks a rename"
)
def test_a_ref_held_open_on_windows(root: Path) -> None:
    a, b, c = _stored(root, 0), _stored(root, 1), _stored(root, 2)
    library = open_library(root)
    library.set_ref("sample-run", "baseline", a)
    ref = _ref_file(root, "sample-run", "baseline")
    handle = ref.open("rb")
    timer = threading.Timer(0.2, handle.close)
    timer.start()
    library.set_ref("sample-run", "baseline", b)  # succeeds once the holder closes
    timer.join()
    assert library.read_ref("sample-run", "baseline") == b
    with ref.open("rb"):
        with pytest.raises(LibraryError) as caught:
            library.set_ref("sample-run", "baseline", c)
    assert caught.value.code == LIBRARY_BUSY
