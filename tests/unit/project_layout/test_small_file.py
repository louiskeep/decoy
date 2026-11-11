"""The one small-file reader fails closed whatever open flags the platform has."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from decoy.cli.io import _small_file
from decoy.cli.io._small_file import UnsafeFileError, read_small_file

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks and FIFOs")

# What Windows lacks. The lstat check must hold without them.
_PLATFORM_FLAGS = ("O_NOFOLLOW", "O_NONBLOCK", "O_NOCTTY")


@pytest.fixture(params=[False, True], ids=["all flags", "no O_NOFOLLOW"])
def gap(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    if request.param:
        for name in _PLATFORM_FLAGS:
            monkeypatch.delattr(os, name, raising=False)
    return bool(request.param)


def test_a_regular_file_is_read_up_to_the_limit(tmp_path: Path, gap: bool) -> None:
    path = tmp_path / "LATEST"
    path.write_bytes(b"abcdef")
    found = read_small_file(path, 4)
    assert found is not None
    assert (found.data, found.size) == (b"abcd", 6)


def test_nothing_there_is_none(tmp_path: Path, gap: bool) -> None:
    assert read_small_file(tmp_path / "absent", 10) is None
    (tmp_path / "file").write_text("x", encoding="utf-8")
    assert read_small_file(tmp_path / "file" / "under", 10) is None


@posix_only
def test_a_symlink_to_a_regular_file_is_refused(tmp_path: Path, gap: bool) -> None:
    real = tmp_path / "real"
    real.write_text("other run", encoding="utf-8")
    link = tmp_path / "LATEST"
    link.symlink_to(real)
    with pytest.raises(UnsafeFileError):
        read_small_file(link, 10)


@posix_only
def test_a_fifo_is_refused_without_blocking(tmp_path: Path, gap: bool) -> None:
    fifo = tmp_path / "PIPELINE"
    os.mkfifo(fifo)
    outcome: list[object] = []

    def read() -> None:
        try:
            outcome.append(read_small_file(fifo, 10))
        except UnsafeFileError as exc:
            outcome.append(exc)

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    worker.join(10)
    assert not worker.is_alive(), "the reader blocked on a FIFO"
    assert isinstance(outcome[0], UnsafeFileError)


def test_a_directory_is_refused(tmp_path: Path, gap: bool) -> None:
    with pytest.raises(UnsafeFileError):
        read_small_file(tmp_path, 10)


def test_a_file_swapped_between_the_check_and_the_open_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gap: bool
) -> None:
    path = tmp_path / "decoy.yaml"
    path.write_text("kind: decoy-project\n", encoding="utf-8")
    real_open = os.open

    def swapping_open(target: str | os.PathLike[str], flags: int, *args: int) -> int:
        replacement = tmp_path / "planted"
        replacement.write_text("kind: other\n", encoding="utf-8")
        os.replace(replacement, target)
        return real_open(target, flags, *args)

    monkeypatch.setattr(_small_file.os, "open", swapping_open)
    with pytest.raises(UnsafeFileError):
        read_small_file(path, 100)
