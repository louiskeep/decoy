"""B1-atomic-unit: `write_atomic` leaves the old or the new file at every fault, no temp file."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from decoy import _atomic, _private_file
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


_BAD_NAMES = [
    "", ".", "..", "a/b", "a\\b", "a\0b", "../x",
    "C:x", "a:b", "NUL", "nul", "con.txt", "CON.tar.gz", "COM1", "lpt9.log", "AUX", "PRN.x",
    "x.", "x ", " x", ".hidden", "a b", "caf\u00e9", "x" * 201,
]  # fmt: skip


@pytest.mark.parametrize("name", _BAD_NAMES)
def test_bad_name_fails_closed_before_any_file(tmp_path: Path, name: str) -> None:
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, name, b"x", WriteMode.REPLACE)
    assert info.value.code == _atomic.ATOMIC_BAD_NAME
    assert _names(tmp_path) == []


@pytest.mark.parametrize(
    "name", ["a.txt", "A-b_c.json", "0", "x" * 200, "console.txt", "COM10", "COM0", "LPT0.log"]
)
def test_plain_names_are_accepted(tmp_path: Path, name: str) -> None:
    assert write_atomic(tmp_path, name, b"x", WriteMode.REPLACE) is True


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
    assert info.value.__context__ is None
    assert _names(tmp_path) == ["t"]


def test_error_carries_no_path_or_cause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE)
    exc = info.value
    assert str(exc) == _atomic.ATOMIC_WRITE_FAILED and exc.errno == errno.EIO
    assert exc.__cause__ is None and exc.__context__ is None
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


def _no_link(*_a: object, **_k: object) -> None:
    raise OSError(errno.EPERM, "no links at /secret/path")


def test_create_once_without_hard_links_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "link", _no_link)
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, "r", b"a", WriteMode.CREATE_ONCE)
    assert info.value.code == _atomic.ATOMIC_NOCLOBBER_UNSUPPORTED
    assert info.value.errno == errno.EPERM
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert _names(tmp_path) == []


def test_no_hard_links_never_overwrites_a_competing_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V1: the old check-then-replace let a file created after the check be clobbered."""

    def competitor_then_refuse(*_a: object, **_k: object) -> None:
        (tmp_path / "r").write_bytes(b"competitor")
        raise OSError(errno.EPERM, "no links at /secret/path")

    monkeypatch.setattr(os, "link", competitor_then_refuse)
    with pytest.raises(AtomicWriteError) as info:
        write_atomic(tmp_path, "r", b"mine", WriteMode.CREATE_ONCE)
    assert info.value.code == _atomic.ATOMIC_NOCLOBBER_UNSUPPORTED
    assert (tmp_path / "r").read_bytes() == b"competitor"
    assert _names(tmp_path) == ["r"]


@pytest.mark.skipif(os.name == "nt", reason="the hard-link move is POSIX only")
def test_create_once_drops_the_temp_link_before_the_directory_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(_atomic, "fsync_directory", lambda d: seen.append(_names(d)))
    assert write_atomic(tmp_path, "r", b"x", WriteMode.CREATE_ONCE) is True
    assert seen == [["r"]]


@pytest.mark.parametrize(
    "name",
    ["report final.json", "_report.json", ".report.sarif", "r\u00e9sum\u00e9.json", "a b", "COM0"],
)
def test_local_target_accepts_any_single_component(tmp_path: Path, name: str) -> None:
    assert _atomic.write_local_target(tmp_path / name, b"x", WriteMode.REPLACE) is True
    assert (tmp_path / name).read_bytes() == b"x"
    assert not [n for n in _names(tmp_path) if n.endswith(".tmp")]


def test_local_target_shares_the_write_core(tmp_path: Path) -> None:
    assert _atomic.write_local_target(tmp_path / "r", b"a", WriteMode.CREATE_ONCE) is True
    assert _atomic.write_local_target(tmp_path / "r", b"b", WriteMode.CREATE_ONCE) is False
    assert (tmp_path / "r").read_bytes() == b"a"
    if os.name != "nt":
        assert (tmp_path / "r").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("name", [".", "..", "", "a\0b"])
def test_local_target_refuses_a_bad_component(name: str) -> None:
    # A Path splits on separators, so the last component never holds one; the rest can fail.
    with pytest.raises(AtomicWriteError) as info:
        _atomic.write_local_target(Path(name), b"x", WriteMode.REPLACE)
    assert info.value.code == _atomic.ATOMIC_BAD_NAME


@pytest.mark.parametrize(
    "name", ["NUL", "con.txt", "COM1", "lpt9.log", "COM\u00b9", "CONIN$", "aux .txt"]
)
def test_local_target_refuses_windows_devices_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(_private_file, "_WINDOWS", True)
    with pytest.raises(AtomicWriteError) as info:
        _atomic.write_local_target(tmp_path / name, b"x", WriteMode.REPLACE)
    assert info.value.code == _atomic.ATOMIC_BAD_NAME


@pytest.mark.parametrize("name", ["COM0", "LPT0.log", "COM10", "console.txt"])
def test_local_target_accepts_cpython_non_devices_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    # Parity with CPython os.path.isreserved: COM0 and LPT0 are ordinary names on Windows.
    monkeypatch.setattr(_private_file, "_WINDOWS", True)
    assert _atomic.write_local_target(tmp_path / name, b"x", WriteMode.REPLACE) is True


def test_competitor_between_temp_and_link_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def competitor_then_link(src: str, dst: Path) -> None:
        (tmp_path / "r").write_bytes(b"competitor")
        real_link(src, dst)

    monkeypatch.setattr(os, "link", competitor_then_link)
    assert write_atomic(tmp_path, "r", b"mine", WriteMode.CREATE_ONCE) is False
    assert (tmp_path / "r").read_bytes() == b"competitor"
    assert _names(tmp_path) == ["r"]


def test_windows_create_once_uses_rename_and_keeps_a_competitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def rename_refuses(src: str, dst: Path) -> None:
        (tmp_path / "r").write_bytes(b"competitor")
        raise FileExistsError(errno.EEXIST, "exists")

    def forbidden(*_a: object, **_k: object) -> None:
        raise AssertionError("no link or replace on the Windows no-clobber path")

    monkeypatch.setattr(_private_file, "_WINDOWS", True)
    monkeypatch.setattr(os, "rename", rename_refuses)
    monkeypatch.setattr(os, "link", forbidden)
    monkeypatch.setattr(os, "replace", forbidden)
    assert write_atomic(tmp_path, "r", b"mine", WriteMode.CREATE_ONCE) is False
    assert (tmp_path / "r").read_bytes() == b"competitor"
    assert _names(tmp_path) == ["r"]


def _fsync_kinds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import stat

    real, kinds = os.fsync, []

    def fsync(fd: int) -> None:
        kinds.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return kinds


def test_create_once_miss_does_not_fsync_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_atomic(tmp_path, "r", b"first", WriteMode.CREATE_ONCE)
    kinds = _fsync_kinds(monkeypatch)
    assert write_atomic(tmp_path, "r", b"second", WriteMode.CREATE_ONCE) is False
    assert kinds == ["file"]


def test_one_directory_is_synced_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kinds = _fsync_kinds(monkeypatch)
    write_atomic(tmp_path, "r", b"x", WriteMode.REPLACE, tmp_dir=tmp_path)
    assert kinds == ["file", "dir"]


def test_separate_tmp_dir_is_synced_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out, tmp = tmp_path / "out", tmp_path / "tmp"
    out.mkdir()
    tmp.mkdir()
    kinds = _fsync_kinds(monkeypatch)
    write_atomic(out, "r", b"x", WriteMode.REPLACE, tmp_dir=tmp)
    assert kinds == ["file", "dir", "dir"]


@pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory")
def test_public_fsync_directory_raises_plain_oserror(tmp_path: Path) -> None:
    _atomic.fsync_directory(tmp_path)
    with pytest.raises(OSError) as info:
        _atomic.fsync_directory(tmp_path / "missing")
    assert not isinstance(info.value, AtomicWriteError)


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

    monkeypatch.setattr(_private_file, "_WINDOWS", True)
    monkeypatch.setattr(_atomic, "_sleep", sleeps.append)
    monkeypatch.setattr(os, "replace", flaky)
    assert write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE) is True
    assert sleeps == [0.01, 0.02, 0.04]
    assert _names(tmp_path) == ["t"]


def test_windows_gives_up_after_the_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def held(*_a: object) -> None:
        raise PermissionError(errno.EACCES, "held open")

    monkeypatch.setattr(_private_file, "_WINDOWS", True)
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

    monkeypatch.setattr(_private_file, "_WINDOWS", False)
    monkeypatch.setattr(_atomic, "_sleep", sleeps.append)
    monkeypatch.setattr(os, "replace", held)
    with pytest.raises(AtomicWriteError):
        write_atomic(tmp_path, "t", b"x", WriteMode.REPLACE)
    assert sleeps == []


def test_failed_temp_unlink_after_link_is_retried_by_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A first unlink that fails (EBUSY) must not hide the temp link from the final cleanup.
    real_unlink = os.unlink
    calls = {"n": 0}

    def flaky_unlink(path: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(16, "busy")
        real_unlink(path)

    monkeypatch.setattr(_atomic.os, "unlink", flaky_unlink)
    assert write_atomic(tmp_path, "r", b"x", WriteMode.CREATE_ONCE) is True
    assert _names(tmp_path) == ["r"]


# --- replace_symlink (PROJECT-LAYOUT P1a) ---

_posix_only = pytest.mark.skipif(os.name == "nt", reason="needs symlinks")


@_posix_only
def test_replace_symlink_creates_a_relative_link(tmp_path: Path) -> None:
    _atomic.replace_symlink(tmp_path / "latest", "run-1")
    assert os.readlink(tmp_path / "latest") == "run-1"
    assert _names(tmp_path) == ["latest"]


@_posix_only
def test_replace_symlink_retargets_without_a_missing_moment(tmp_path: Path) -> None:
    link = tmp_path / "current"
    _atomic.replace_symlink(link, "versions/a")
    seen: list[str] = []
    real = os.replace

    def spy(src: object, dst: object) -> None:
        seen.append(os.readlink(link))  # the old link is still whole at the swap
        real(src, dst)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_atomic.os, "replace", spy)
        _atomic.replace_symlink(link, "versions/b")
    assert seen == ["versions/a"]
    assert os.readlink(link) == "versions/b"
    assert _names(tmp_path) == ["current"]


@_posix_only
def test_replace_symlink_replaces_a_planted_link_not_its_target(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"keep")
    link = tmp_path / "latest"
    link.symlink_to(victim)
    _atomic.replace_symlink(link, "run-2")
    assert os.readlink(link) == "run-2"
    assert victim.read_bytes() == b"keep"


@_posix_only
def test_replace_symlink_refuses_a_regular_file_in_the_way(tmp_path: Path) -> None:
    (tmp_path / "latest").write_bytes(b"mine")
    with pytest.raises(AtomicWriteError) as caught:
        _atomic.replace_symlink(tmp_path / "latest", "run-3")
    assert caught.value.code == _atomic.ATOMIC_WRITE_FAILED
    assert caught.value.__context__ is None
    assert (tmp_path / "latest").read_bytes() == b"mine"
    assert _names(tmp_path) == ["latest"]


@_posix_only
def test_replace_symlink_failure_removes_its_temp_and_keeps_the_old_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "latest"
    _atomic.replace_symlink(link, "run-1")
    monkeypatch.setattr(_atomic.os, "replace", _boom)
    with pytest.raises(AtomicWriteError) as caught:
        _atomic.replace_symlink(link, "run-2")
    assert caught.value.code == _atomic.ATOMIC_WRITE_FAILED
    assert caught.value.errno == errno.EIO
    assert "secret" not in str(caught.value) and caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert os.readlink(link) == "run-1"
    assert _names(tmp_path) == ["latest"]


@_posix_only
def test_replace_symlink_symlink_failure_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_atomic.os, "symlink", _boom)
    with pytest.raises(AtomicWriteError) as caught:
        _atomic.replace_symlink(tmp_path / "latest", "run-1")
    assert caught.value.__context__ is None
    assert _names(tmp_path) == []


@_posix_only
def test_replace_symlink_lstat_failure_keeps_no_path_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny(*_a: object, **_k: object) -> None:
        raise OSError(errno.EACCES, "x", "/secret/path")

    monkeypatch.setattr(_atomic.os, "lstat", deny)
    with pytest.raises(AtomicWriteError) as caught:
        _atomic.replace_symlink(tmp_path / "latest", "run-1")
    assert caught.value.errno == errno.EACCES
    assert caught.value.__context__ is None
