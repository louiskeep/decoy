"""`publish_local_targets`: a batch of local files published as one rollback unit (GEN-CLI C2)."""

from __future__ import annotations

import errno
import os
import threading
from pathlib import Path

import pytest

from decoy import _atomic
from decoy._atomic import AtomicWriteError, LocalTarget, WriteMode, publish_local_targets

posix = pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits and directory locks")


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def _fail_on_call(monkeypatch: pytest.MonkeyPatch, n: int) -> None:
    real = _atomic._publish
    calls = {"n": 0}

    def flaky(*args: object, **kwargs: object) -> bool:
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError(errno.EIO, "disk fault at /secret/path")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_atomic, "_publish", flaky)


def test_publishes_every_target_in_order(tmp_path: Path) -> None:
    publish_local_targets(
        [
            LocalTarget(tmp_path / "a.json", b"snap", WriteMode.CREATE_ONCE, private=True),
            LocalTarget(tmp_path / "b.yaml", b"cfg", WriteMode.CREATE_ONCE),
        ]
    )

    assert (tmp_path / "a.json").read_bytes() == b"snap"
    assert (tmp_path / "b.yaml").read_bytes() == b"cfg"
    assert _names(tmp_path) == ["a.json", "b.yaml"]


@posix
def test_private_target_is_owner_only_and_overwrite_keeps_the_old_mode(tmp_path: Path) -> None:
    old = tmp_path / "b.yaml"
    old.write_bytes(b"old")
    old.chmod(0o640)

    publish_local_targets(
        [
            LocalTarget(tmp_path / "a.json", b"s", WriteMode.CREATE_ONCE, private=True),
            LocalTarget(old, b"new", WriteMode.REPLACE),
        ]
    )

    assert (tmp_path / "a.json").stat().st_mode & 0o777 == 0o600
    assert old.read_bytes() == b"new" and old.stat().st_mode & 0o777 == 0o640


@posix
def test_failure_on_the_second_replace_restores_old_bytes_and_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.yaml"
    first.write_bytes(b"old-a")
    second.write_bytes(b"old-b")
    first.chmod(0o600)
    second.chmod(0o640)
    _fail_on_call(monkeypatch, 2)

    with pytest.raises(AtomicWriteError) as caught:
        publish_local_targets(
            [LocalTarget(first, b"new-a", private=True), LocalTarget(second, b"new-b")]
        )

    assert caught.value.code == _atomic.ATOMIC_WRITE_FAILED
    assert "/secret" not in str(caught.value)
    assert (first.read_bytes(), first.stat().st_mode & 0o777) == (b"old-a", 0o600)
    assert (second.read_bytes(), second.stat().st_mode & 0o777) == (b"old-b", 0o640)
    assert _names(tmp_path) == ["a.json", "b.yaml"]  # no staging or backup file


def test_failure_on_the_second_replace_removes_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_on_call(monkeypatch, 2)

    with pytest.raises(AtomicWriteError):
        publish_local_targets(
            [
                LocalTarget(tmp_path / "a.json", b"a", WriteMode.CREATE_ONCE),
                LocalTarget(tmp_path / "b.yaml", b"b", WriteMode.CREATE_ONCE),
            ]
        )

    assert _names(tmp_path) == []


def test_failure_on_the_first_replace_leaves_the_old_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.json").write_bytes(b"old-a")
    (tmp_path / "b.yaml").write_bytes(b"old-b")
    _fail_on_call(monkeypatch, 1)

    with pytest.raises(AtomicWriteError):
        publish_local_targets(
            [LocalTarget(tmp_path / "a.json", b"x"), LocalTarget(tmp_path / "b.yaml", b"y")]
        )

    assert (tmp_path / "a.json").read_bytes() == b"old-a"
    assert (tmp_path / "b.yaml").read_bytes() == b"old-b"
    assert _names(tmp_path) == ["a.json", "b.yaml"]


def test_a_create_only_target_that_appeared_is_refused_without_mutation(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_bytes(b"someone else")

    with pytest.raises(AtomicWriteError) as caught:
        publish_local_targets(
            [
                LocalTarget(tmp_path / "a.json", b"a", WriteMode.CREATE_ONCE),
                LocalTarget(tmp_path / "b.yaml", b"b", WriteMode.CREATE_ONCE),
            ]
        )

    assert caught.value.code == _atomic.ATOMIC_TARGET_EXISTS
    assert _names(tmp_path) == ["b.yaml"]
    assert (tmp_path / "b.yaml").read_bytes() == b"someone else"


def test_targets_in_two_folders_are_refused(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()

    with pytest.raises(AtomicWriteError) as caught:
        publish_local_targets(
            [LocalTarget(tmp_path / "a.json", b"a"), LocalTarget(tmp_path / "x" / "b.yaml", b"b")]
        )

    assert caught.value.code == _atomic.ATOMIC_BATCH_INVALID
    assert _names(tmp_path) == ["x"]


def test_a_bad_name_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AtomicWriteError) as caught:
        publish_local_targets([LocalTarget(tmp_path / "..", b"a")])
    assert caught.value.code == _atomic.ATOMIC_BAD_NAME


@posix
def test_a_second_publisher_for_the_same_folder_is_refused_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pause the first publisher after its first replace; the second must not touch anything."""
    real = _atomic._publish
    paused, resume = threading.Event(), threading.Event()
    calls = {"n": 0}

    def pausing(*args: object, **kwargs: object) -> bool:
        out = real(*args, **kwargs)  # type: ignore[arg-type]
        calls["n"] += 1
        if calls["n"] == 1:
            paused.set()
            assert resume.wait(10)
        return out

    monkeypatch.setattr(_atomic, "_publish", pausing)
    failures: list[BaseException] = []

    def first() -> None:
        try:
            publish_local_targets(
                [
                    LocalTarget(tmp_path / "a.json", b"one-a"),
                    LocalTarget(tmp_path / "b.yaml", b"one-b"),
                ]
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=first)
    worker.start()
    assert paused.wait(10)
    try:
        with pytest.raises(AtomicWriteError) as caught:
            publish_local_targets(
                [
                    LocalTarget(tmp_path / "a.json", b"two-a"),
                    LocalTarget(tmp_path / "b.yaml", b"two-b"),
                ]
            )
        assert caught.value.code == _atomic.ATOMIC_BATCH_BUSY
        assert (tmp_path / "a.json").read_bytes() == b"one-a"  # still the first publisher's
    finally:
        resume.set()
        worker.join(10)

    assert failures == []
    assert (tmp_path / "a.json").read_bytes() == b"one-a"
    assert (tmp_path / "b.yaml").read_bytes() == b"one-b"
    assert _names(tmp_path) == ["a.json", "b.yaml"]
    publish_local_targets([LocalTarget(tmp_path / "a.json", b"3")])  # the lock was released


def test_check_sees_the_staged_files_and_a_refusal_changes_nothing(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_bytes(b"old-a")
    seen: list[bytes] = []

    def refuse(staged: list[Path]) -> None:
        seen.extend(p.read_bytes() for p in staged)
        assert all(p.parent == tmp_path and p.name not in {"a.json", "b.yaml"} for p in staged)
        raise ValueError("no")

    with pytest.raises(ValueError):
        publish_local_targets(
            [
                LocalTarget(tmp_path / "a.json", b"new-a"),
                LocalTarget(tmp_path / "b.yaml", b"new-b"),
            ],
            check=refuse,
        )

    assert seen == [b"new-a", b"new-b"]
    assert (tmp_path / "a.json").read_bytes() == b"old-a"
    assert _names(tmp_path) == ["a.json"]
