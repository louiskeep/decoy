"""B1-atomic-unit: `write_atomic` leaves the old or the new file at every fault, no temp file."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from decoy import _atomic
from decoy._atomic import AtomicWriteError, WriteMode, write_atomic


def _names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def _boom(*_a: object, **_k: object) -> None:
    raise OSError(errno.EIO, "disk fault at /secret/path")


def test_replace_writes_and_overwrites(tmp_path: Path) -> None:
    assert write_atomic(tmp_path, "a.txt", b"one", WriteMode.REPLACE) is True
    assert write_atomic(tmp_path, "a.txt", b"two", WriteMode.REPLACE) is True
    assert (tmp_path / "a.txt").read_bytes() == b"two"
    assert _names(tmp_path) == ["a.txt"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_file_is_owner_only(tmp_path: Path) -> None:
    write_atomic(tmp_path, "a.txt", b"x", WriteMode.REPLACE)
    assert (tmp_path / "a.txt").stat().st_mode & 0o777 == 0o600


def test_create_once_never_clobbers(tmp_path: Path) -> None:
    assert write_atomic(tmp_path, "r", b"first", WriteMode.CREATE_ONCE) is True
    assert write_atomic(tmp_path, "r", b"second", WriteMode.CREATE_ONCE) is False
    assert (tmp_path / "r").read_bytes() == b"first"
    assert _names(tmp_path) == ["r"]


def test_tmp_dir_holds_the_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out, tmp = tmp_path / "out", tmp_path / "tmp"
    out.mkdir()
    tmp.mkdir()
    seen: list[str] = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append(str(a)), real(a, b))[1])
    write_atomic(out, "f", b"x", WriteMode.REPLACE, tmp_dir=tmp)
    assert seen and Path(seen[0]).parent == tmp
    assert _names(out) == ["f"] and _names(tmp) == []


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "a\0b", "../x"])
def test_bad_name_fails_closed_before_any_file(tmp_path: Path, name: str) -> None:
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, name, b"x", WriteMode.REPLACE)
    assert info.value.code == _atomic.ATOMIC_BAD_NAME
    assert _names(tmp_path) == []


@pytest.mark.parametrize("step", ["fsync_file", "replace", "dir_fsync"])
def test_replace_fault_keeps_old_or_new_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    (tmp_path / "t").write_bytes(b"old")
    real_fsync, calls = os.fsync, {"n": 0}

    def fsync(fd: int) -> None:
        calls["n"] += 1
        # First fsync is the data file, the second is the directory.
        if (step == "fsync_file" and calls["n"] == 1) or (step == "dir_fsync" and calls["n"] == 2):
            _boom()
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    if step == "replace":
        monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(AtomicWriteError):
        write_atomic(tmp_path, "t", b"new", WriteMode.REPLACE)
    assert (tmp_path / "t").read_bytes() in (b"old", b"new")
    if step != "dir_fsync":
        assert (tmp_path / "t").read_bytes() == b"old"
    assert _names(tmp_path) == ["t"]


def test_create_once_fault_leaves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "link", _boom)
    with pytest.raises(AtomicWriteError):
        write_atomic(tmp_path, "r", b"x", WriteMode.CREATE_ONCE)
    assert _names(tmp_path) == []


def test_dir_fsync_failure_has_its_own_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, calls = os.fsync, {"n": 0}

    def fsync(fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            _boom()
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, "t", b"new", WriteMode.CREATE_ONCE)
    assert info.value.code == _atomic.ATOMIC_SYNC_FAILED
    assert _names(tmp_path) == ["t"]


def test_error_carries_no_path_or_cause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE)
    exc = info.value
    assert str(exc) == _atomic.ATOMIC_WRITE_FAILED and exc.errno == errno.EIO
    assert exc.__cause__ is None and exc.__suppress_context__
    assert "secret" not in repr(exc) and str(tmp_path) not in repr(exc)


def test_keyboard_interrupt_cleans_up_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*_a: object, **_k: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupt)
    with pytest.raises(KeyboardInterrupt):
        write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE)
    assert _names(tmp_path) == []


def test_create_once_without_hard_links_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_link(*_a: object, **_k: object) -> None:
        raise OSError(errno.EPERM, "no links")

    monkeypatch.setattr(os, "link", no_link)
    assert write_atomic(tmp_path, "r", b"a", WriteMode.CREATE_ONCE) is True
    assert write_atomic(tmp_path, "r", b"b", WriteMode.CREATE_ONCE) is False
    assert (tmp_path / "r").read_bytes() == b"a"
    assert _names(tmp_path) == ["r"]


def test_cross_device_link_error_is_not_a_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def xdev(*_a: object, **_k: object) -> None:
        raise OSError(errno.EXDEV, "x")

    monkeypatch.setattr(os, "link", xdev)
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, "r", b"a", WriteMode.CREATE_ONCE)
    assert info.value.errno == errno.EXDEV
    assert _names(tmp_path) == []


def test_windows_retries_permission_error_with_bounded_backoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    real, fails = os.replace, {"n": 3}

    def flaky(a: str, b: Path) -> None:
        if fails["n"]:
            fails["n"] -= 1
            raise PermissionError(errno.EACCES, "held open")
        real(a, b)

    monkeypatch.setattr(_atomic, "_WINDOWS", True)
    monkeypatch.setattr(_atomic, "_sleep", sleeps.append)
    monkeypatch.setattr(os, "replace", flaky)
    assert write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE) is True
    assert sleeps == [0.01, 0.02, 0.04]
    assert _names(tmp_path) == ["t"]


def test_windows_gives_up_after_the_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def held(*_a: object) -> None:
        raise PermissionError(errno.EACCES, "held open")

    monkeypatch.setattr(_atomic, "_WINDOWS", True)
    monkeypatch.setattr(_atomic, "_sleep", sleeps.append)
    monkeypatch.setattr(os, "replace", held)
    with pytest.raises(AtomicWriteError):
        write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE)
    assert len(sleeps) == 9 and max(sleeps) == 0.16 and sum(sleeps) < 1.0
    assert _names(tmp_path) == []


def test_posix_does_not_retry_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    def held(*_a: object) -> None:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(_atomic, "_WINDOWS", False)
    monkeypatch.setattr(_atomic, "_sleep", sleeps.append)
    monkeypatch.setattr(os, "replace", held)
    with pytest.raises(AtomicWriteError):
        write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE)
    assert sleeps == []
