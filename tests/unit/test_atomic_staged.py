"""`staged_local_target`: a failed write leaves the target as it was (slice ATOMIC-OUTPUT)."""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from decoy import _atomic
from decoy._atomic import (
    ATOMIC_SYNC_FAILED,
    ATOMIC_WRITE_FAILED,
    AtomicWriteError,
    WriteMode,
    describe,
    staged_local_target,
    staged_private_target,
    write_local_target,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes and special files")


def _names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def _stager(private: bool):  # type: ignore[no-untyped-def]
    return staged_private_target if private else staged_local_target


def _stage(path: Path, data: bytes = b"new", *, private: bool = False) -> None:
    with _stager(private)(path) as tmp:
        tmp.write_bytes(data)


def test_clean_exit_publishes_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    _stage(target)
    assert target.read_bytes() == b"new"
    assert _names(tmp_path) == ["out.csv"]


def test_the_temp_is_a_recognisable_hidden_sibling(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    with staged_local_target(target) as tmp:
        assert tmp.parent == tmp_path
        assert tmp.name.startswith(".out.csv.decoy-") and tmp.name.endswith(".tmp")
        assert not target.exists()


@pytest.mark.parametrize("raised", [RuntimeError("boom"), KeyboardInterrupt()])
@pytest.mark.parametrize("prior", [None, b"old"])
def test_a_failing_block_keeps_the_prior_state(
    tmp_path: Path, raised: BaseException, prior: bytes | None
) -> None:
    target = tmp_path / "out.csv"
    if prior is not None:
        target.write_bytes(prior)
    before = _names(tmp_path)
    with pytest.raises(type(raised)) as caught:
        with staged_local_target(target) as tmp:
            tmp.write_bytes(b"partial")
            raise raised
    assert caught.value is raised
    assert _names(tmp_path) == before
    assert (target.read_bytes() if prior is not None else None) == prior


def test_long_names_are_cut_by_characters_to_fit(tmp_path: Path) -> None:
    name = "é" * 120 + ".csv"  # 244 bytes; the temp name adds 28 more
    target = tmp_path / name
    with staged_local_target(target) as tmp:
        assert len(os.fsencode(tmp.name)) <= 255
        tmp.write_bytes(b"x")
    assert target.read_bytes() == b"x"


@posix_only
def test_symlink_target_updates_its_destination_and_stays_a_link(tmp_path: Path) -> None:
    dest = tmp_path / "real" / "dest.csv"
    dest.parent.mkdir()
    dest.write_bytes(b"old")
    link = tmp_path / "link.csv"
    link.symlink_to(dest)
    _stage(link)
    assert link.is_symlink() and dest.read_bytes() == b"new"
    assert _names(dest.parent) == ["dest.csv"] and _names(tmp_path) == ["link.csv", "real"]


@posix_only
def test_dangling_symlink_creates_its_destination(tmp_path: Path) -> None:
    dest = tmp_path / "dest.csv"
    link = tmp_path / "link.csv"
    link.symlink_to(dest)
    _stage(link)
    assert link.is_symlink() and dest.read_bytes() == b"new"


def test_a_directory_at_the_target_fails_safely(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    target.mkdir()
    (target / "keep.txt").write_text("k")
    with pytest.raises(AtomicWriteError) as caught:
        _stage(target)
    assert caught.value.code == ATOMIC_WRITE_FAILED
    assert _names(tmp_path) == ["out.csv"] and _names(target) == ["keep.txt"]


# -- fault at each step ------------------------------------------------------------------


def _boom(*_a: object, **_k: object) -> None:
    raise OSError(errno.EIO, "disk says no", "/secret/dir/name")


def _inject(monkeypatch: pytest.MonkeyPatch, step: str) -> None:
    real_open = os.open

    def faulty_open(path, flags, *a, **k):  # type: ignore[no-untyped-def]
        if step == "create" and flags & os.O_EXCL:
            _boom()
        if step == "reopen" and flags & os.O_ACCMODE == os.O_RDWR:
            _boom()
        return real_open(path, flags, *a, **k)

    if step in ("create", "reopen"):
        monkeypatch.setattr(os, "open", faulty_open)
    elif step == "chmod":
        monkeypatch.setattr(os, "fchmod", _boom)
    elif step == "fsync":
        monkeypatch.setattr(os, "fsync", _boom)
    elif step == "replace":
        monkeypatch.setattr(os, "replace", _boom)
    elif step == "dirsync":
        monkeypatch.setattr(_atomic, "fsync_directory", _boom)


@posix_only
@pytest.mark.parametrize("step", ["create", "reopen", "chmod", "fsync", "replace", "dirsync"])
def test_a_fault_at_each_step_is_a_value_free_atomic_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    target = tmp_path / "out.csv"
    target.write_bytes(b"old")
    _inject(monkeypatch, step)
    with pytest.raises(AtomicWriteError) as caught:
        _stage(target)
    exc = caught.value
    assert exc.code == (ATOMIC_SYNC_FAILED if step == "dirsync" else ATOMIC_WRITE_FAILED)
    assert exc.errno == errno.EIO
    assert exc.__cause__ is None and exc.__context__ is None
    assert str(exc) == exc.code and "secret" not in str(exc) and str(tmp_path) not in str(exc)
    assert describe(exc) == f"{exc.code} ({os.strerror(errno.EIO)})"
    monkeypatch.undo()
    assert _names(tmp_path) == ["out.csv"]
    assert target.read_bytes() == (b"new" if step == "dirsync" else b"old")


def test_describe_without_an_errno_is_the_bare_code() -> None:
    assert describe(AtomicWriteError(ATOMIC_WRITE_FAILED)) == ATOMIC_WRITE_FAILED


def test_stat_failure_other_than_missing_is_an_atomic_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stat = os.stat

    def deny(path, *a, **k):  # type: ignore[no-untyped-def]
        if Path(path).name == "out.csv":
            raise PermissionError(errno.EACCES, "no", str(path))
        return real_stat(path, *a, **k)

    monkeypatch.setattr(os, "stat", deny)
    with pytest.raises(AtomicWriteError) as caught:
        _stage(tmp_path / "out.csv")
    assert caught.value.errno == errno.EACCES and caught.value.__context__ is None


# -- permissions -------------------------------------------------------------------------

_CHILD = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from decoy._atomic import staged_local_target, staged_private_target\n"
    "os.umask(int(sys.argv[1], 8))\n"
    "with (staged_private_target if sys.argv[3] == '1' else staged_local_target)(Path(sys.argv[2])) as tmp:\n"
    "    tmp.write_bytes(b'new')\n"
)


def _child(umask: str, target: Path, *, private: bool = False) -> None:
    subprocess.run(
        [sys.executable, "-c", _CHILD, umask, str(target), "1" if private else "0"], check=True
    )


@posix_only
@pytest.mark.parametrize("umask", ["022", "077", "002"])
def test_new_output_gets_the_umask_default(tmp_path: Path, umask: str) -> None:
    target = tmp_path / "out.csv"
    _child(umask, target)
    assert _mode(target) == 0o666 & ~int(umask, 8)


@posix_only
def test_an_extreme_umask_still_lets_the_writer_finish(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    _child("277", target)  # removes owner write from every new file
    assert target.read_bytes() == b"new"
    assert _mode(target) == 0o666 & ~0o277


@posix_only
@pytest.mark.parametrize("bits", [0o600, 0o400, 0o640])
def test_an_existing_output_keeps_its_bits(tmp_path: Path, bits: int) -> None:
    target = tmp_path / "out.csv"
    target.write_bytes(b"old")
    target.chmod(bits)
    _child("022", target)
    assert target.read_bytes() == b"new"
    assert _mode(target) == bits


@posix_only
def test_private_output_is_0600_even_over_a_wider_old_file(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    target.write_bytes(b"old")
    target.chmod(0o644)
    _child("022", target, private=True)
    assert _mode(target) == 0o600


_PROBE = (
    "import os, stat, sys\n"
    "from pathlib import Path\n"
    "from decoy._atomic import staged_local_target, staged_private_target\n"
    "os.umask(int(sys.argv[1], 8))\n"
    "with (staged_private_target if sys.argv[3] == '1' else staged_local_target)(Path(sys.argv[2])) as tmp:\n"
    "    print(oct(stat.S_IMODE(os.stat(tmp).st_mode)))\n"
    "    tmp.write_bytes(b'x')\n"
)


@posix_only
@pytest.mark.parametrize("umask", ["022", "002", "000"])
@pytest.mark.parametrize(
    ("private", "old_bits"),
    [(True, None), (True, 0o644), (False, None), (False, 0o600), (False, 0o644)],
)
def test_the_temp_is_owner_only_while_it_is_written(
    tmp_path: Path, umask: str, private: bool, old_bits: int | None
) -> None:
    target = tmp_path / "out.csv"
    if old_bits is not None:
        target.write_bytes(b"old")
        target.chmod(old_bits)
    done = subprocess.run(
        [sys.executable, "-c", _PROBE, umask, str(target), "1" if private else "0"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert done.stdout.strip() == "0o600"


@posix_only
def test_a_different_group_with_a_failed_chown_grants_no_extra_bits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp = tmp_path / "t"
    tmp.write_bytes(b"")
    old = os.stat_result((stat.S_IFREG | 0o666, 0, 0, 1, 0, os.stat(tmp).st_gid + 1, 0, 0, 0, 0))
    monkeypatch.setattr(os, "chown", _boom)
    assert _atomic._final_bits(str(tmp), old, False, 0o644) == 0o666 & 0o644
    monkeypatch.setattr(os, "chown", lambda *a, **k: None)
    assert _atomic._final_bits(str(tmp), old, False, 0o644) == 0o666


# -- special files -----------------------------------------------------------------------


@posix_only
def test_a_fifo_and_a_link_to_it_are_written_through(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    link = tmp_path / "pipe-link"
    link.symlink_to(fifo)
    got: list[bytes] = []

    def drain() -> None:
        with open(fifo, "rb") as handle:
            got.append(handle.read())

    for target in (fifo, link):
        got.clear()
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        with staged_local_target(target) as out:
            assert out == target
            out.write_bytes(b"through")
        reader.join(timeout=10)
        assert got == [b"through"]
    assert _names(tmp_path) == ["pipe", "pipe-link"]


@pytest.mark.skipif(not Path("/dev/stdout").exists(), reason="needs /dev/stdout")
@pytest.mark.parametrize("device", ["/dev/stdout", "/dev/fd/1"])
def test_a_redirected_stdout_is_written_through_not_replaced(tmp_path: Path, device: str) -> None:
    """A stdout redirected to a regular file stats as a regular file; the user-given /dev path
    decides, so the redirect target keeps its inode and receives the bytes."""
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from decoy._atomic import staged_local_target, staged_private_target\n"
        "with staged_local_target(Path(sys.argv[1])) as p:\n"
        "    assert p == Path(sys.argv[1]), p\n"
        "    p.write_bytes(b'hello')\n"
    )
    sink = tmp_path / "sink.txt"
    sink.write_bytes(b"")
    inode = sink.stat().st_ino
    with open(sink, "wb") as handle:
        done = subprocess.run([sys.executable, "-c", code, device], stdout=handle, timeout=60)
    assert done.returncode == 0
    assert sink.read_bytes() == b"hello" and sink.stat().st_ino == inode
    assert _names(tmp_path) == ["sink.txt"]


@pytest.mark.skipif(not Path("/dev/stdout").exists(), reason="needs /dev/stdout")
def test_dev_stdout_to_a_pipe_is_written_through() -> None:
    code = (
        "from pathlib import Path\n"
        "from decoy._atomic import staged_local_target, staged_private_target\n"
        "with staged_local_target(Path('/dev/stdout')) as p:\n"
        "    p.write_bytes(b'hello')\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout == b"hello"


# -- write_local_target ------------------------------------------------------------------


def test_write_local_target_replace_goes_through_the_staged_path(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_bytes(b"old")
    assert write_local_target(target, b"new", WriteMode.REPLACE) is True
    assert target.read_bytes() == b"new" and _names(tmp_path) == ["out.json"]
    if os.name == "posix":
        assert _mode(target) == 0o600


@posix_only
def test_write_local_target_updates_a_symlink_destination(tmp_path: Path) -> None:
    dest = tmp_path / "dest.json"
    link = tmp_path / "link.json"
    link.symlink_to(dest)
    write_local_target(link, b"x", WriteMode.REPLACE)
    assert link.is_symlink() and dest.read_bytes() == b"x"


@posix_only
def test_write_local_target_create_once_still_never_clobbers(tmp_path: Path) -> None:
    target = tmp_path / "rec.json"
    assert write_local_target(target, b"one", WriteMode.CREATE_ONCE) is True
    assert write_local_target(target, b"two", WriteMode.CREATE_ONCE) is False
    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "nowhere.json")
    assert write_local_target(link, b"x", WriteMode.CREATE_ONCE) is False
    assert not (tmp_path / "nowhere.json").exists()
    assert target.read_bytes() == b"one"


def test_write_local_target_failure_is_a_value_free_atomic_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.json"
    target.write_bytes(b"old")
    monkeypatch.setattr(os, "fsync", _boom)
    with pytest.raises(AtomicWriteError) as caught:
        write_local_target(target, b"new", WriteMode.REPLACE)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    monkeypatch.undo()
    assert target.read_bytes() == b"old" and _names(tmp_path) == ["out.json"]


@pytest.mark.skipif(not Path("/dev/shm").is_dir(), reason="needs /dev/shm")
@pytest.mark.parametrize("private", [True, False])
def test_a_regular_file_under_dev_shm_is_staged(private: bool) -> None:
    import tempfile

    with tempfile.TemporaryDirectory(dir="/dev/shm") as shm:
        target = Path(shm) / "out.csv"
        target.write_bytes(b"old")
        with _stager(private)(target) as tmp:
            assert tmp != target and tmp.name.startswith(".out.csv.decoy-")
            tmp.write_bytes(b"new")
        assert target.read_bytes() == b"new"
        if private:
            assert _mode(target) == 0o600
        assert _names(Path(shm)) == ["out.csv"]


@pytest.mark.skipif(not Path("/dev").is_dir(), reason="needs /dev")
@pytest.mark.parametrize("name", ["/dev/stdoutx", "/dev/fd/1x", "/dev/fd/", "/dev/xstdout"])
def test_near_misses_of_the_fd_aliases_are_not_aliases(name: str) -> None:
    from decoy._atomic import _FD_ALIAS

    assert _FD_ALIAS.fullmatch(name) is None


@pytest.mark.parametrize("name", ["/dev/stdout", "/dev/stderr", "/dev/fd/7", "/proc/self/fd/1"])
def test_fd_aliases_match(name: str) -> None:
    from decoy._atomic import _FD_ALIAS

    assert _FD_ALIAS.fullmatch(name) is not None


@pytest.mark.skipif(not Path("/dev/stdout").exists(), reason="needs /dev/stdout")
def test_a_symlink_to_dev_stdout_is_classified_before_realpath(tmp_path: Path) -> None:
    """The alias rule does not see a link by another name; the stat check must, and it must
    run on the path as given because realpath turns a pipe into an unopenable `pipe:[id]`."""
    link = tmp_path / "out-link"
    link.symlink_to("/dev/stdout")
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from decoy._atomic import staged_local_target\n"
        "with staged_local_target(Path(sys.argv[1])) as p:\n"
        "    assert p == Path(sys.argv[1]), p\n"
        "    p.write_bytes(b'hello')\n"
    )
    done = subprocess.run([sys.executable, "-c", code, str(link)], capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout == b"hello"
