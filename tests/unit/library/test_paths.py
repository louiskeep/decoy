"""B1-resolve and B1-win-long-root: where the library lives, and the Windows path budget.

The default root is the project root's `.decoy/` (PROJECT-LAYOUT LIB-A, owner answers Q1 to Q3
in docs/records/lib-reframe-2026-11-11.md), not the YAML's folder: `--library`, then
`DECOY_LIBRARY`, then `find_project(start, explicit).root / ".decoy"`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tests.unit.library._helpers import envelope, object_files

from decoy.cli import io as cli_io
from decoy.cli.library import LibraryError, _paths, open_library, resolve_root
from decoy.cli.library._errors import LIBRARY_PATH_TOO_LONG

MARKER = "kind: decoy-project/v1\n"


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git-bounded tree, so the project walk never leaves `tmp_path`."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def walks(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path | None, Path | None]]:
    """Every call into the one project-root finder, so a case proves it used it."""
    calls: list[tuple[Path | None, Path | None]] = []
    real = cli_io.find_project

    def spy(start: Path | None, explicit: Path | None) -> cli_io.Project:
        calls.append((start, explicit))
        return real(start, explicit)

    monkeypatch.setattr(_paths, "find_project", spy)
    return calls


def _pipeline(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    yaml = folder / "pipeline.yaml"
    yaml.write_text("tables: {}\n", encoding="utf-8")
    return yaml


# -- B1-resolve -----------------------------------------------------------------------------


def test_flag_beats_env_and_env_beats_the_project(tree: Path, walks: list) -> None:
    """MB1-order: reading the env before the flag turns this red."""
    yaml = _pipeline(tree / "jobs")
    env = {"DECOY_LIBRARY": str(tree / "from-env")}
    got = resolve_root(flag=tree / "from-flag", pipeline=yaml, environ=env)
    assert (got.path, got.records, got.source) == ((tree / "from-flag").resolve(), True, "flag")
    got = resolve_root(pipeline=yaml, environ=env)
    assert (got.path, got.records, got.source) == ((tree / "from-env").resolve(), True, "env")
    got = resolve_root(pipeline=yaml, environ={})
    assert (got.path, got.source) == ((tree / "jobs" / cli_io.DECOY_DIR).resolve(), "project")
    assert len(walks) == 1  # only the last case reached the project rule


def test_a_marker_above_the_yaml_puts_the_library_at_the_project_root(
    tree: Path, walks: list
) -> None:
    (tree / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    yaml = _pipeline(tree / "pipelines" / "p")
    got = resolve_root(pipeline=yaml, environ={})
    assert got.path == (tree / cli_io.DECOY_DIR).resolve()
    assert walks == [(yaml.parent.resolve(), None)]


def test_no_marker_means_the_yaml_folder(tree: Path, walks: list) -> None:
    yaml = _pipeline(tree / "pipelines" / "p")
    assert resolve_root(pipeline=yaml, environ={}).path == (yaml.parent / ".decoy").resolve()
    assert len(walks) == 1


def test_no_yaml_means_the_current_folder(
    tree: Path, walks: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tree / "sub").mkdir()
    monkeypatch.chdir(tree / "sub")
    assert resolve_root(environ={}).path == (tree / "sub" / ".decoy").resolve()
    assert walks == [(None, None)]


def test_an_explicit_project_is_passed_to_the_finder(tree: Path, walks: list) -> None:
    project = tree / "proj"
    project.mkdir()
    (project / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    yaml = _pipeline(tree / "elsewhere")
    got = resolve_root(pipeline=yaml, project=project, environ={})
    assert got.path == (project / ".decoy").resolve()
    assert walks and walks[0][1] == project


def test_scan_starts_at_emit_config_then_config_then_cwd(tree: Path, walks: list) -> None:
    """MB1-scan-cwd: a scan that ignores `--emit-config` turns this red."""
    emit = tree / "out" / "p.yaml"
    emit.parent.mkdir()
    config = _pipeline(tree / "cfg")
    both = resolve_root(emit_config=emit, config=config, environ={})
    assert both.path == (tree / "out" / ".decoy").resolve()
    assert resolve_root(config=config, environ={}).path == (tree / "cfg" / ".decoy").resolve()
    assert resolve_root(environ={}).path == (tree / ".decoy").resolve()
    assert len(walks) == 3


def test_off_turns_records_off_and_the_log_root_skips_the_env_step(tree: Path, walks: list) -> None:
    yaml = _pipeline(tree / "jobs")
    off = resolve_root(pipeline=yaml, environ={"DECOY_LIBRARY": "off"})
    assert (off.records, off.source) == (False, "project")
    assert off.path == (tree / "jobs" / ".decoy").resolve()
    flagged = resolve_root(flag=tree / "lib", pipeline=yaml, environ={"DECOY_LIBRARY": "off"})
    assert (flagged.path, flagged.records) == ((tree / "lib").resolve(), True)
    assert len(walks) == 1


def test_an_empty_env_value_is_unset(tree: Path, walks: list) -> None:
    yaml = _pipeline(tree / "jobs")
    got = resolve_root(pipeline=yaml, environ={"DECOY_LIBRARY": ""})
    assert (got.source, got.records) == ("project", True)
    assert len(walks) == 1


# -- B1-win-long-root -----------------------------------------------------------------------


def _root_of_length(base: Path, length: int) -> Path:
    pad = length - len(str(base)) - 1
    assert pad > 0, "tmp_path is too long for this case"
    return base / ("r" * pad)


def test_long_root_is_refused_before_any_write_when_the_windows_rule_is_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux run of B1-win-long-root with the platform check forced on (MB1-no-budget)."""
    monkeypatch.setattr(_paths, "_WINDOWS", True)
    long_root = _root_of_length(tmp_path, 160)
    with pytest.raises(LibraryError) as caught:
        open_library(long_root).put(envelope())
    assert caught.value.code == LIBRARY_PATH_TOO_LONG
    assert list(tmp_path.iterdir()) == []
    short_root = _root_of_length(tmp_path, 140)
    open_library(short_root).put(envelope())
    assert len(object_files(short_root)) == 1


def test_the_budget_does_not_apply_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_paths, "_WINDOWS", False)
    long_root = _root_of_length(tmp_path, 160)
    open_library(long_root).put(envelope())
    assert len(object_files(long_root)) == 1


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows lane: MAX_PATH budget on a real Windows path"
)
def test_long_root_is_refused_on_windows(tmp_path: Path) -> None:
    long_root = _root_of_length(tmp_path, 160)
    with pytest.raises(LibraryError) as caught:
        open_library(long_root)
    assert caught.value.code == LIBRARY_PATH_TOO_LONG
    assert list(tmp_path.iterdir()) == []
    short_root = _root_of_length(tmp_path, 140)
    open_library(short_root).put(envelope())
    assert len(object_files(short_root)) == 1
