"""`_private_file.try_lock_exclusive`: the one advisory-lock primitive and its errno table."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from decoy import _private_file
from decoy._private_file import PRIVATE_BUSY, PRIVATE_OPEN_FAILED, PrivateFileError

posix = pytest.mark.skipif(os.name != "posix", reason="flock is POSIX only")


@posix
@pytest.mark.parametrize("code", [errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES])
def test_contention_errnos_are_busy(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    def refuse(_fd: int, _op: int) -> None:
        raise OSError(code, "busy")

    monkeypatch.setattr(_private_file.fcntl, "flock", refuse)
    with pytest.raises(PrivateFileError) as caught:
        _private_file.try_lock_exclusive(0)
    assert caught.value.code == PRIVATE_BUSY
    assert caught.value.errno == code


@posix
def test_any_other_errno_is_an_open_failure_that_keeps_the_errno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_fd: int, _op: int) -> None:
        raise OSError(errno.ENOLCK, "no locks")

    monkeypatch.setattr(_private_file.fcntl, "flock", refuse)
    with pytest.raises(PrivateFileError) as caught:
        _private_file.try_lock_exclusive(0)
    assert caught.value.code == PRIVATE_OPEN_FAILED
    assert caught.value.errno == errno.ENOLCK


@posix
def test_a_free_lock_is_taken_and_a_second_descriptor_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "f"
    first = _private_file.lock_exclusive(path)
    try:
        with pytest.raises(PrivateFileError) as caught:
            _private_file.lock_exclusive(path)
        assert caught.value.code == PRIVATE_BUSY
    finally:
        os.close(first)
    os.close(_private_file.lock_exclusive(path))


def test_no_fcntl_means_no_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_private_file, "fcntl", None)
    assert _private_file.advisory_lock_available() is False
    assert _private_file.try_lock_exclusive(0) is False
