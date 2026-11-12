"""The library reads its files only through the CLI's one small-file reader.

A FIFO, a symlink or an oversized file at an object path is refused, and none of them hangs a
read (`decoy.cli.io.read_small_file`: `lstat` first, a no-follow non-blocking open, the opened
descriptor judged). Review round 1 on #205, item 1.
"""

from __future__ import annotations

import ast
import os
import threading
from pathlib import Path

import pytest
from decoy_engine import records
from tests.unit.library._helpers import ROOT, envelope, object_path

from decoy.cli.io import DECOY_DIR, _small_file
from decoy.cli.library import LibraryError, _errors, _store, open_library
from decoy.cli.library._errors import LIBRARY_READ_FAILED

posix_only = pytest.mark.skipif(os.name != "posix", reason="FIFOs and symlinks without privilege")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "private-project-name"
    project.mkdir()
    return project / DECOY_DIR


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every path the library hands to the one reader (proves the case reaches it)."""
    seen: list[Path] = []
    real = _small_file.read_small_file

    def spy(path: Path, max_bytes: int) -> object:
        seen.append(Path(path))
        return real(path, max_bytes)

    import decoy.cli.library._fs as fs

    monkeypatch.setattr(fs, "read_small_file", spy, raising=False)
    return seen


def _get_in_thread(library: object, record_id: str) -> tuple[threading.Thread, list[object]]:
    out: list[object] = []

    def call() -> None:
        try:
            out.append(library.get(record_id))  # type: ignore[attr-defined]
        except BaseException as exc:
            out.append(exc)

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(timeout=10)
    return worker, out


@posix_only
def test_a_fifo_at_an_object_path_is_refused_and_does_not_hang(
    root: Path, reads: list[Path]
) -> None:
    env = envelope()
    library = open_library(root)
    library.put(env)
    stored = object_path(root, env.id)
    stored.unlink()
    os.mkfifo(stored)
    worker, out = _get_in_thread(library, env.id)
    hung = worker.is_alive()
    if hung:  # free the blocked open so the test process can finish
        fd = os.open(stored, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        worker.join(timeout=10)
    assert not hung, "get blocked on a FIFO"
    assert out
    assert isinstance(out[0], LibraryError) and out[0].code == LIBRARY_READ_FAILED
    assert stored in reads  # non-vacuous: the one reader judged this path


@posix_only
def test_a_symlink_at_an_object_path_is_refused(
    root: Path, tmp_path: Path, reads: list[Path]
) -> None:
    env = envelope()
    library = open_library(root)
    library.put(env)
    stored = object_path(root, env.id)
    outside = tmp_path / "elsewhere.json"
    outside.write_bytes(stored.read_bytes())
    stored.unlink()
    stored.symlink_to(outside)
    assert records.decode(stored.read_bytes()).id == env.id  # the link target is a valid record
    with pytest.raises(LibraryError) as caught:
        library.get(env.id)
    assert caught.value.code == LIBRARY_READ_FAILED
    assert str(outside) not in str(caught.value) and str(stored) not in str(caught.value)
    assert stored in reads


def test_an_oversized_object_is_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch, reads: list[Path]
) -> None:
    env = envelope()
    library = open_library(root)
    library.put(env)
    stored = object_path(root, env.id)
    size = stored.stat().st_size
    monkeypatch.setattr(_store, "MAX_RECORD_BYTES", size - 1)
    with pytest.raises(LibraryError) as caught:
        library.get(env.id)
    assert caught.value.code == _errors.LIBRARY_FILE_TOO_LARGE
    assert stored in reads
    monkeypatch.setattr(_store, "MAX_RECORD_BYTES", size)
    assert library.get(env.id).id == env.id  # control: at the cap it still reads


def test_a_record_over_the_cap_is_never_written(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record the library could not read back is refused before any object file exists."""
    env = envelope()
    monkeypatch.setattr(_store, "MAX_RECORD_BYTES", len(records.encode(env)) - 1)
    with pytest.raises(LibraryError) as caught:
        open_library(root).put(env)
    assert caught.value.code == _errors.LIBRARY_FILE_TOO_LARGE
    assert not object_path(root, env.id).exists()


def test_the_record_cap_is_generous_for_value_free_metadata() -> None:
    assert _store.MAX_RECORD_BYTES == 16 * 1024 * 1024


def _own_reads(source: str) -> list[int]:
    """Lines that read a file without the one reader: `open(...)`, `Path.open`, `read_bytes`,
    `read_text` (`os.open` is a descriptor call the writer and lock paths own, not a read)."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            found.append(node.lineno)
        elif isinstance(func, ast.Attribute) and func.attr in {"read_bytes", "read_text"}:
            found.append(node.lineno)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "open"
            and not (isinstance(func.value, ast.Name) and func.value.id == "os")
        ):
            found.append(node.lineno)
    return found


def test_own_reads_sees_each_spelling() -> None:
    assert _own_reads("open(p)\np.open()\np.read_bytes()\np.read_text()\n") == [1, 2, 3, 4]
    assert _own_reads("os.open(p, f)\nread_small_file(p, 9)\n") == []


def test_the_library_has_no_second_reader() -> None:
    """The class, not the instance: no library module reads a file by itself."""
    import decoy.cli.library._fs as fs

    assert not hasattr(fs, "read_file")
    package = ROOT / "src" / "decoy" / "cli" / "library"
    sources = {p.name: p.read_text(encoding="utf-8") for p in package.glob("*.py")}
    assert "_store.py" in sources  # non-vacuous: the package was scanned
    offenders = {name: lines for name, text in sources.items() if (lines := _own_reads(text))}
    assert offenders == {}
