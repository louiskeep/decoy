"""AT-1: the one project-root finder (`find_project`) and `.decoy/` setup.

The walk, its stops (`.git`, device change, `$HOME`), the marker trust rule and every marker
refusal. Each tree sits under `tmp_path` with `$HOME` pointed at a folder beside it, so the real
home and the real filesystem above `/tmp` never decide a result.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from decoy._atomic import AtomicWriteError
from decoy.cli.io import (
    GATE_CODES,
    LayoutError,
    Project,
    _project,
    ensure_decoy_dir,
    find_project,
)
from decoy.cli.io._project import MARKER_KIND

MARKER = f"kind: {MARKER_KIND}\n"
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX owners, modes and symlinks")


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `$HOME` beside the trees under test, never an ancestor of them."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    return folder


def _tree(tmp_path: Path, *parts: str) -> Path:
    folder = tmp_path / "work"
    for part in parts:
        folder = folder / part
    folder.mkdir(parents=True)
    return folder


def _marker(folder: Path, text: str = MARKER) -> Path:
    path = folder / "decoy.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _code(exc: pytest.ExceptionInfo[LayoutError]) -> str:
    return exc.value.code


def test_a_marker_two_levels_up_is_found(tmp_path: Path) -> None:
    deep = _tree(tmp_path, "acme", "pipelines", "p")
    _marker(deep.parents[1])
    project = find_project(deep, None)
    assert project == Project(root=deep.parents[1].resolve())
    assert not project.implicit


def test_the_nearest_of_two_markers_wins(tmp_path: Path) -> None:
    inner = _tree(tmp_path, "outer", "inner")
    _marker(inner.parent)
    _marker(inner)
    assert find_project(inner, None).root == inner.resolve()


def test_no_marker_gives_the_start_folder_as_an_implicit_root(tmp_path: Path) -> None:
    folder = _tree(tmp_path, "free")
    (tmp_path / "work" / ".git").mkdir()
    project = find_project(folder, None)
    assert project.root == folder.resolve()
    assert project.implicit


def test_the_start_defaults_to_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, "acme")
    _marker(root)
    sub = root / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    assert find_project(None, None).root == root.resolve()


def test_the_walk_stops_after_a_git_folder(tmp_path: Path) -> None:
    repo = _tree(tmp_path, "top", "repo")
    _marker(repo.parent)
    (repo / ".git").mkdir()
    sub = repo / "sub"
    sub.mkdir()
    project = find_project(sub, None)
    assert project.implicit
    assert project.root == sub.resolve()


def test_the_walk_stops_after_a_git_file(tmp_path: Path) -> None:
    repo = _tree(tmp_path, "top", "repo")
    _marker(repo.parent)
    (repo / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    sub = repo / "sub"
    sub.mkdir()
    project = find_project(sub, None)
    assert project.implicit
    assert project.root == sub.resolve()


def test_a_marker_in_the_folder_that_holds_git_is_found(tmp_path: Path) -> None:
    repo = _tree(tmp_path, "repo")
    (repo / ".git").mkdir()
    _marker(repo)
    sub = repo / "sub"
    sub.mkdir()
    assert find_project(sub, None).root == repo.resolve()


def test_the_walk_stops_at_a_device_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mount = _tree(tmp_path, "top", "mount")
    _marker(mount.parent)
    real = _project._device
    monkeypatch.setattr(
        _project, "_device", lambda p: -1 if Path(p) == mount.resolve() else real(p)
    )
    project = find_project(mount, None)
    assert project.implicit
    assert project.root == mount.resolve()


def test_the_walk_never_reaches_home_and_home_is_not_a_root(home: Path) -> None:
    _marker(home)
    start = home / "clients" / "acme"
    start.mkdir(parents=True)
    project = find_project(start, None)
    assert project.implicit
    assert project.root == start.resolve()
    assert find_project(home, None).implicit


def test_a_marker_below_home_is_found(home: Path) -> None:
    root = home / "clients"
    start = root / "acme"
    start.mkdir(parents=True)
    _marker(root)
    assert find_project(start, None).root == root.resolve()


@posix_only
def test_a_marker_owned_by_another_user_is_untrusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, "acme")
    marker = _marker(root)
    monkeypatch.setattr(os, "geteuid", lambda: marker.stat().st_uid + 1)
    with pytest.raises(LayoutError) as exc:
        find_project(root, None)
    assert _code(exc) == "layout.project_marker_untrusted"
    assert str(marker) in exc.value.message
    with pytest.raises(LayoutError) as explicit:
        find_project(None, root)
    assert _code(explicit) == "layout.project_marker_untrusted"


@posix_only
def test_a_symlinked_marker_is_refused(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    real = tmp_path / "real.yaml"
    real.write_text(MARKER, encoding="utf-8")
    (root / "decoy.yaml").symlink_to(real)
    with pytest.raises(LayoutError) as exc:
        find_project(root, None)
    assert _code(exc) == "layout.project_marker_invalid"


@posix_only
def test_a_marker_swapped_after_the_open_is_judged_by_the_opened_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, "acme")
    marker = _marker(root)
    real_open = os.open

    def swapping_open(path: str | os.PathLike[str], flags: int, *args: int) -> int:
        fd = real_open(path, flags, *args)
        if Path(path) == marker:
            marker.unlink()
            marker.write_text("kind: other\n", encoding="utf-8")
        return fd

    monkeypatch.setattr(_project.os, "open", swapping_open)
    assert find_project(root, None).root == root.resolve()


@pytest.mark.parametrize("text", ["kind: other\n", "kind: [unclosed\n", "- a\n- b\n", "kind: 3\n"])
def test_a_wrong_kind_or_bad_yaml_is_an_invalid_marker(tmp_path: Path, text: str) -> None:
    root = _tree(tmp_path, "acme")
    _marker(root, text)
    with pytest.raises(LayoutError) as exc:
        find_project(root, None)
    assert _code(exc) == "layout.project_marker_invalid"


def test_a_marker_over_64_kib_is_invalid(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    _marker(root, MARKER + "# " + "x" * 70_000 + "\n")
    with pytest.raises(LayoutError) as exc:
        find_project(root, None)
    assert _code(exc) == "layout.project_marker_invalid"


def test_a_decoy_yaml_with_no_kind_is_skipped_and_listed(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    inner = root / "jobs"
    inner.mkdir()
    _marker(root)
    pipeline = _marker(inner, "version: 2\nname: x\n")
    project = find_project(inner, None)
    assert project.root == root.resolve()
    assert project.skipped == (pipeline.resolve(),)


def test_marker_keys_other_than_kind_are_reserved_and_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    _marker(root, MARKER + "owner: ana\ncolor: red\n")
    assert find_project(root, None).extra_keys == ("color", "owner")


def test_an_explicit_folder_needs_its_own_marker_and_does_not_walk(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    sub = root / "sub"
    sub.mkdir()
    _marker(root)
    assert find_project(None, root).root == root.resolve()
    with pytest.raises(LayoutError) as exc:
        find_project(None, sub)
    assert _code(exc) == "layout.project_not_found"


def test_an_explicit_decoy_yaml_without_kind_is_invalid(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    _marker(root, "version: 2\n")
    with pytest.raises(LayoutError) as exc:
        find_project(None, root)
    assert _code(exc) == "layout.project_marker_invalid"


def test_the_marker_errors_carry_no_chained_context(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    _marker(root, "kind: [unclosed\n")
    with pytest.raises(LayoutError) as exc:
        find_project(root, None)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_ensure_decoy_dir_makes_the_folder_and_keeps_an_edited_gitignore(tmp_path: Path) -> None:
    root = _tree(tmp_path, "acme")
    assert ensure_decoy_dir(root) == ()
    ignore = root / ".decoy" / ".gitignore"
    assert ignore.read_text(encoding="utf-8").splitlines()[:2] == ["scratch/", "logs/"]
    ignore.write_text("mine\n", encoding="utf-8")
    assert ensure_decoy_dir(root) == ()
    assert ignore.read_text(encoding="utf-8") == "mine\n"


def test_an_unwritable_decoy_gitignore_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, "acme")

    def refuse(*_a: object, **_k: object) -> bool:
        raise AtomicWriteError("atomic_write_failed", 13)

    monkeypatch.setattr(_project, "write_local_target", refuse)
    (warning,) = ensure_decoy_dir(root)
    assert warning.code == "layout.gitignore_write_failed"


def test_the_marker_codes_are_registered_gate_codes() -> None:
    codes = {
        "layout.project_marker_invalid",
        "layout.project_marker_untrusted",
        "layout.project_not_found",
    }
    assert codes <= GATE_CODES
    assert all(re.fullmatch(r"layout\.[a-z_]+", c) for c in GATE_CODES)
