"""Library scratch (plan 4.6, 4.7, 3 "Protected scratch"; L1d): the only Decoy area that holds rows.

`scratch/` and every allocation come from the engine's one allocator (`open_protected_dir`,
`protected_scratch_dir`, L0); the CLI creates no directory of its own here.
"""

from __future__ import annotations

import os
import re
import stat
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from decoy_engine.fileaccess import _protected_dir
from decoy_engine.reasons import runtime, warning
from tests.unit.library._helpers import INVOCATION

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, _scratch, open_library

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _local(_path: Path) -> None:
    return None


def _scratch_dir(root: Path) -> Path:
    return root / "scratch"


# -- D1-mode -----------------------------------------------------------------------------------


@posix_only
def test_an_allocation_is_0700_and_its_files_0600(root: Path) -> None:
    """M-MODE: writing the file with plain `open` gives the umask mode; red."""
    old = os.umask(0)
    try:
        with open_library(root, probe=_local).scratch("sample", INVOCATION) as alloc:
            alloc.write("orders.csv", b"id\n1\n")
            seen = {
                "scratch": _mode(_scratch_dir(root)),
                "alloc": _mode(alloc.path),
                "file": _mode(alloc.path / "orders.csv"),
            }
            name = alloc.path.name
    finally:
        os.umask(old)
    assert seen == {"scratch": 0o700, "alloc": 0o700, "file": 0o600}
    # The engine names a fresh allocation: the plan's `<owner>-<invocation_id>` plus 16 hex.
    assert re.fullmatch(rf"sample-{INVOCATION}-[0-9a-f]{{16}}", name)
    assert (root / ".gitignore").read_text(encoding="utf-8").startswith("scratch/\n")


# -- D1-delete-on-exit -------------------------------------------------------------------------


def test_delete_on_exit_removes_the_allocation_on_success_and_on_error(root: Path) -> None:
    """MD1-leak: keeping a delete-on-exit allocation turns this red."""
    library = open_library(root, probe=_local)
    with library.scratch("staging", INVOCATION) as alloc:
        alloc.write("part.parquet", b"rows")
        inside = alloc.path
        assert (inside / "part.parquet").is_file()  # non-vacuous: rows were there
    assert not inside.exists()
    with pytest.raises(RuntimeError), library.scratch("staging", INVOCATION) as alloc:
        failing = alloc.path
        alloc.write("part.parquet", b"rows")
        raise RuntimeError("the owner failed")
    assert not failing.exists()
    assert list(_scratch_dir(root).iterdir()) == []


def test_a_ttl_allocation_is_kept_under_its_exact_name(root: Path) -> None:
    library = open_library(root, probe=_local)
    with library.scratch("sample", INVOCATION, ttl=timedelta(hours=24)) as alloc:
        alloc.write("orders.csv", b"id\n1\n")
    assert alloc.path == _scratch_dir(root) / f"sample-{INVOCATION}"
    assert (alloc.path / "orders.csv").read_bytes() == b"id\n1\n"


@pytest.mark.parametrize("owner", ["", "Sample", "a/b", "../x", "x" * 33, "-a"])
def test_an_owner_outside_the_grammar_is_refused(root: Path, owner: str) -> None:
    with pytest.raises(ValueError), open_library(root, probe=_local).scratch(owner, INVOCATION):
        pytest.fail("the block must not run")
    assert not _scratch_dir(root).exists()


# -- D1-uses-allocator -------------------------------------------------------------------------


def test_scratch_and_every_allocation_come_from_the_engine_allocator(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MD1-own-mkdir: creating the allocation with `Path.mkdir` skips the spy; red."""
    calls: list[str] = []
    real_open, real_fresh = _scratch.open_protected_dir, _scratch.protected_scratch_dir

    def spy_open(path: object, **kw: object) -> Path:
        calls.append(f"open:{Path(str(path)).name}")
        return real_open(path, **kw)  # type: ignore[arg-type]

    def spy_fresh(parent: object = None, prefix: str = "decoy-"):
        calls.append(f"fresh:{prefix}")
        return real_fresh(parent, prefix)  # type: ignore[arg-type]

    monkeypatch.setattr(_scratch, "open_protected_dir", spy_open)
    monkeypatch.setattr(_scratch, "protected_scratch_dir", spy_fresh)
    library = open_library(root, probe=_local)
    with library.scratch("staging", INVOCATION) as alloc:
        fresh = alloc.path
    with library.scratch("sample", INVOCATION, ttl=timedelta(hours=1)) as alloc:
        kept = alloc.path
    assert calls == [
        "open:scratch",
        f"fresh:staging-{INVOCATION}-",
        "open:scratch",
        f"open:sample-{INVOCATION}",
    ]
    assert fresh.parent == kept.parent == _scratch_dir(root)


# -- D1-acl-fail-closed ------------------------------------------------------------------------


def _acl_fails(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def boom(path: str) -> None:
        seen.append(path)
        raise _protected_dir.ProtectedDirAclFailed

    monkeypatch.setattr(_protected_dir, "_chmod_private", boom)
    return seen


def test_an_acl_failure_on_scratch_itself_stops_the_owner(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MB1-acl-warn: warning and carrying on into an unprotected folder turns this red."""
    library = open_library(root, probe=_local)
    seen = _acl_fails(monkeypatch)
    ran: list[bool] = []
    with pytest.raises(LibraryError) as caught, library.scratch("sample", INVOCATION):
        ran.append(True)  # the sample's row writing would start here
    assert caught.value.code == runtime.SCRATCH_ACL_FAILED
    assert seen  # non-vacuous: the engine's protection step was reached
    assert ran == [] and not _scratch_dir(root).exists()


def test_an_acl_failure_on_an_allocation_leaves_nothing(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = open_library(root, probe=_local)
    with library.scratch("staging", INVOCATION):
        pass  # scratch/ now exists and is sound
    seen = _acl_fails(monkeypatch)
    ran: list[bool] = []
    for ttl in (None, timedelta(hours=1)):
        with pytest.raises(LibraryError) as caught, library.scratch("sample", INVOCATION, ttl=ttl):
            ran.append(True)
        assert caught.value.code == runtime.SCRATCH_ACL_FAILED
        assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(seen) == 2 and ran == []
    assert list(_scratch_dir(root).iterdir()) == []


# -- D1-reopen ---------------------------------------------------------------------------------


@posix_only
def test_scratch_is_reopened_tightened_or_refused(root: Path, tmp_path: Path) -> None:
    """MD1-skip-reopen-check: `mkdir(exist_ok=True)` for `scratch/` accepts the open one; red."""
    for _ in range(3):  # three commands in one project reuse scratch/
        with open_library(root, probe=_local).scratch("staging", INVOCATION) as alloc:
            assert alloc.path.parent == _scratch_dir(root)
    os.chmod(_scratch_dir(root), 0o755)  # an empty, too-open scratch/ is tightened
    with open_library(root, probe=_local).scratch("staging", INVOCATION):
        pass
    assert _mode(_scratch_dir(root)) == 0o700
    os.chmod(_scratch_dir(root), 0o755)
    (_scratch_dir(root) / "left-behind.csv").write_bytes(b"rows someone may have read")
    ran: list[bool] = []
    with pytest.raises(LibraryError) as caught:
        with open_library(root, probe=_local).scratch("staging", INVOCATION):
            ran.append(True)
    assert caught.value.code == runtime.SCRATCH_UNSAFE
    assert ran == []  # the command's own work stopped before writing rows


# -- D1-delete-open ----------------------------------------------------------------------------


def _held_open(monkeypatch: pytest.MonkeyPatch, name: str) -> list[str]:
    """Simulate a Windows sharing violation on one file: its unlink raises PermissionError."""
    refused: list[str] = []
    real = os.unlink

    def unlink(path: object, *args: object, **kwargs: object) -> None:
        if os.fspath(path).endswith(name):  # type: ignore[arg-type]
            refused.append(name)
            raise PermissionError(13, "held open")
        real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "unlink", unlink)
    return refused


def test_a_file_held_open_is_reported_and_skipped_then_cleaned_later(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux run of D1-delete-open with the PermissionError forced (MD1-raise turns it red)."""
    library = open_library(root, probe=_local)
    refused = _held_open(monkeypatch, "open.xlsx")
    with library.scratch("sample", INVOCATION) as alloc:
        alloc.write("open.xlsx", b"held by a spreadsheet")
        alloc.write("other.csv", b"rows")
    assert refused  # non-vacuous: the delete really hit the held file
    assert alloc.skipped == ("open.xlsx",)
    assert alloc.report is not None and alloc.report.code == warning.LIBRARY_DELETE_SKIPPED
    assert not (alloc.path / "other.csv").exists()
    assert (alloc.path / "open.xlsx").exists()
    monkeypatch.undo()  # the program closed the file
    report = open_library(root, probe=_local).delete_scratch(alloc.path)
    assert report.skipped == () and report.removed >= 1
    assert not alloc.path.exists()


def test_delete_scratch_refuses_a_path_outside_scratch(root: Path, tmp_path: Path) -> None:
    library = open_library(root, probe=_local)
    outside = tmp_path / "user-data"
    outside.mkdir()
    (outside / "keep.csv").write_bytes(b"the user's")
    with pytest.raises(ValueError):
        library.delete_scratch(outside)
    assert (outside / "keep.csv").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows lane: a held-open file blocks delete")
def test_a_file_held_open_on_windows_is_skipped(root: Path) -> None:
    library = open_library(root, probe=_local)
    with library.scratch("sample", INVOCATION) as alloc:
        alloc.write("open.csv", b"rows")
        handle = (alloc.path / "open.csv").open("rb")
    assert alloc.skipped == ("open.csv",)
    handle.close()
    assert open_library(root, probe=_local).delete_scratch(alloc.path).skipped == ()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows lane: protected DACL read back (L0)")
def test_scratch_and_allocation_dacls_are_owner_only_on_windows(root: Path) -> None:
    with open_library(root, probe=_local).scratch("sample", INVOCATION) as alloc:
        for path in (_scratch_dir(root), alloc.path):
            owned, closed = _protected_dir._win_state(str(path))  # type: ignore[attr-defined]
            assert owned and closed
