"""B1-mode, B1-no-path-in-error and B1-gitfiles: what the library leaves on disk, and how it fails.

The library creates through `decoy._private_file` and writes through `decoy._atomic`; these
cases read the result back from the filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.unit.library._helpers import envelope, mode, object_files

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, open_library
from decoy.cli.library._errors import LIBRARY_WRITE_FAILED, library_error

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")

GITIGNORE = "scratch/\nlogs/\nlibrary/index.sqlite\nlibrary/tmp/\nlibrary/quarantine/\n"
GITATTRIBUTES = "library/objects/** -text\n"


@pytest.fixture
def umask_zero():
    old = os.umask(0)
    try:
        yield
    finally:
        os.umask(old)


# -- B1-mode ----------------------------------------------------------------------------------


@posix_only
def test_every_created_file_is_0600_and_every_created_folder_0700(
    tmp_path: Path, umask_zero: None
) -> None:
    """M-MODE: a temp or record created with plain `open(..., "w")` is 0666 here and fails."""
    project = tmp_path / "project"
    project.mkdir(mode=0o755)
    os.chmod(project, 0o755)
    root = project / DECOY_DIR
    library = open_library(root)
    first = envelope(0)
    library.put(first)
    library.put(envelope(1, links=[first.id]))
    files = [p for p in root.rglob("*") if p.is_file()]
    folders = [root, *(p for p in root.rglob("*") if p.is_dir())]
    assert len(object_files(root)) == 2  # non-vacuous: the walk sees both records
    assert {p.name for p in files} >= {".gitignore", ".gitattributes", "LAYOUT"}
    assert {p.relative_to(root).as_posix(): oct(mode(p)) for p in files} == {
        p.relative_to(root).as_posix(): "0o600" for p in files
    }
    assert {p.relative_to(root).as_posix(): oct(mode(p)) for p in folders} == {
        p.relative_to(root).as_posix(): "0o700" for p in folders
    }
    assert mode(project) == 0o755  # a parent the library did not create keeps its mode


@posix_only
def test_an_existing_library_root_keeps_its_mode(tmp_path: Path, umask_zero: None) -> None:
    root = tmp_path / DECOY_DIR
    root.mkdir()
    os.chmod(root, 0o750)
    open_library(root).put(envelope())
    assert mode(root) == 0o750
    assert mode(root / "library") == 0o700
    assert len(object_files(root)) == 1


# -- B1-no-path-in-error ----------------------------------------------------------------------


def test_a_write_failure_names_the_code_and_class_not_the_path(tmp_path: Path) -> None:
    """MB1-exc: putting `str(exc)` (which names the path) into the error turns this red."""
    blocker = tmp_path / "secret-folder-name"
    blocker.write_text("a file where a folder must go", encoding="utf-8")
    root = blocker / DECOY_DIR
    with pytest.raises(LibraryError) as caught:
        open_library(root).put(envelope())
    err = caught.value
    assert err.code == LIBRARY_WRITE_FAILED
    assert err.error_class  # non-vacuous: the failure came from a real OS error class
    assert str(err) == f"{LIBRARY_WRITE_FAILED} ({err.error_class})"
    assert "secret-folder-name" not in str(err) and str(tmp_path) not in repr(err)
    assert err.__cause__ is None and err.__context__ is None


def test_library_error_keeps_only_code_and_class() -> None:
    exc = FileNotFoundError(2, "No such file", "/home/someone/private/thing")
    err = library_error(LIBRARY_WRITE_FAILED, exc)
    assert (err.code, err.error_class) == (LIBRARY_WRITE_FAILED, "FileNotFoundError")
    assert "/home/someone" not in str(err) and "/home/someone" not in repr(err)
    assert library_error(LIBRARY_WRITE_FAILED).error_class == ""
    assert str(library_error(LIBRARY_WRITE_FAILED)) == LIBRARY_WRITE_FAILED


# -- B1-gitfiles ------------------------------------------------------------------------------


def test_the_first_write_creates_both_git_files(tmp_path: Path) -> None:
    root = tmp_path / DECOY_DIR
    open_library(root).put(envelope())
    assert (root / ".gitignore").read_text(encoding="utf-8") == GITIGNORE
    assert (root / ".gitattributes").read_text(encoding="utf-8") == GITATTRIBUTES
    assert len(object_files(root)) == 1


def test_existing_git_files_are_never_edited(tmp_path: Path) -> None:
    """MB1-clobber: writing either file with REPLACE turns this red."""
    root = tmp_path / DECOY_DIR
    root.mkdir()
    (root / ".gitignore").write_text("mine\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
    library = open_library(root)
    library.put(envelope(0))
    library.put(envelope(1))
    assert len(object_files(root)) == 2  # non-vacuous: the writes ran
    assert (root / ".gitignore").read_text(encoding="utf-8") == "mine\n"
    assert (root / ".gitattributes").read_text(encoding="utf-8") == "* text=auto\n"


def test_a_root_not_named_decoy_gets_no_git_files(tmp_path: Path) -> None:
    """A `--library` folder outside the project (a mounted volume) is not a git work tree."""
    root = tmp_path / "volume"
    open_library(root).put(envelope())
    assert len(object_files(root)) == 1
    assert not (root / ".gitignore").exists() and not (root / ".gitattributes").exists()
    assert not (tmp_path / DECOY_DIR).exists()
