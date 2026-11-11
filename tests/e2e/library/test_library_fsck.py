"""`decoy library path` and `decoy library fsck [--repair]` (plan 4.10, 4.15; L1c.2).

C1-fsck-findings at the command level: each problem exits 4 (EXIT_FINDINGS), a 0644 record is
an advisory note with exit 0, a clean library exits 0. C1-repair-safe through `--repair`.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import open_library
from tests.unit.library._helpers import envelope, job_log, object_files, object_path

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
runner = CliRunner()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()  # bounds the project walk
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    return tmp_path / DECOY_DIR


def _fill(root: Path, count: int = 2) -> list[str]:
    library = open_library(root)
    return [library.put(envelope(n)).id for n in range(count)]


def _fsck(*args: str) -> object:
    return runner.invoke(app, ["library", "fsck", *args])


def test_path_prints_the_root_and_where_it_came_from(root: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["library", "path"])
    assert result.exit_code == EXIT_OK, result.output
    assert str(root.resolve()) in result.output and "project" in result.output
    other = tmp_path / "elsewhere"
    result = runner.invoke(app, ["library", "path", "--library", str(other)])
    assert str(other.resolve()) in result.output and "--library" in result.output
    assert not other.exists()  # `path` creates nothing


def test_path_reports_degraded_mode_and_why(root: Path) -> None:
    _fill(root, 1)
    (root / "library" / "index.sqlite").unlink()
    (root / "library" / "index.sqlite").mkdir()
    result = runner.invoke(app, ["library", "path"])
    assert result.exit_code == EXIT_OK, result.output
    assert "degraded" in result.output and "lock_unavailable" in result.output


def test_a_clean_library_exits_0(root: Path) -> None:
    ids = _fill(root)
    result = _fsck()
    assert result.exit_code == EXIT_OK, result.output
    assert f"{len(ids)} records" in result.output  # non-vacuous: the objects were checked


def test_no_library_is_clean_and_creates_nothing(root: Path) -> None:
    result = _fsck()
    assert result.exit_code == EXIT_OK, result.output
    assert not root.exists()


def test_each_problem_exits_with_findings(root: Path) -> None:
    ids = _fill(root, 3)
    corrupt = object_path(root, ids[0])
    corrupt.write_bytes(corrupt.read_bytes().replace(b'"sample_size":1', b'"sample_size":7'))
    result = _fsck()
    assert result.exit_code == EXIT_FINDINGS, result.output
    assert "object_corrupt" in result.output
    assert "library/objects/" in result.output  # the target, relative to the library root


@posix_only
def test_a_0644_record_is_a_note_and_exits_0(root: Path) -> None:
    ids = _fill(root)
    os.chmod(object_path(root, ids[0]), 0o644)
    result = _fsck()
    assert result.exit_code == EXIT_OK, result.output
    assert "note" in result.output and "mode_open" in result.output


@posix_only
def test_a_0644_log_is_a_finding(root: Path) -> None:
    _fill(root)
    logs = root / "logs"
    logs.mkdir(mode=0o700)
    log = logs / "x.jsonl"
    log.write_bytes(job_log())
    os.chmod(log, 0o644)
    result = _fsck()
    assert result.exit_code == EXIT_FINDINGS, result.output
    assert "mode_open" in result.output and "logs/x.jsonl" in result.output


def test_repair_fixes_and_then_exits_0(root: Path) -> None:
    ids = _fill(root, 3)
    corrupt = object_path(root, ids[0])
    corrupt.write_bytes(corrupt.read_bytes().replace(b'"sample_size":1', b'"sample_size":7'))
    stale = root / "library" / "tmp" / ".x.decoy-1.tmp"
    stale.write_bytes(b"partial")
    os.chmod(stale, 0o600)
    old = time.time() - 2 * 3600
    os.utime(stale, (old, old))
    assert _fsck().exit_code == EXIT_FINDINGS  # non-vacuous: there was something to repair
    result = _fsck("--repair")
    assert result.exit_code == EXIT_OK, result.output
    assert "object_quarantined" in result.output and "temp_deleted" in result.output
    assert len(object_files(root)) == 2
    assert len(list((root / "library" / "quarantine").iterdir())) == 1
    assert _fsck().exit_code == EXIT_OK


def test_a_newer_layout_is_a_finding_and_repair_refuses(root: Path) -> None:
    _fill(root, 1)
    (root / "library" / "LAYOUT").write_text('{"layout":2}', encoding="utf-8")
    result = _fsck("--repair")
    assert result.exit_code == EXIT_FINDINGS, result.output
    assert "layout_newer" in result.output
