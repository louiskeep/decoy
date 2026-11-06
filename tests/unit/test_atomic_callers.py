"""The ci report, the ci debug log and the trust state write through `decoy._atomic`.

Each used to carry its own temp-file recipe with no fsync. The fsync calls and the fixed
error are what only the shared writer provides, so these fail if a caller goes back to an
inline write.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.ci.debug import DebugSink
from decoy.distribution import installer
from decoy.distribution import version_document as vd


@pytest.fixture
def fsyncs(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    real, calls = os.fsync, []

    def fsync(fd: int) -> None:
        calls.append(fd)
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return calls


def test_debug_log_is_written_durably_and_privately(tmp_path: Path, fsyncs: list[int]) -> None:
    sink = DebugSink(tmp_path / "debug.log")
    sink.add("label", "line \ud800 end")
    sink.flush()
    assert b"[label] line ? end" in (tmp_path / "debug.log").read_bytes()
    assert len(fsyncs) == 2  # the data file, then the directory
    if os.name != "nt":
        assert (tmp_path / "debug.log").stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["debug.log"]


def test_ci_report_file_is_written_durably(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fsyncs: list[int]
) -> None:
    from tests.ci_support import MANIFEST_NAME, ci_manifest, make_repo, write, write_clean_pipeline

    from decoy.__main__ import app

    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest())
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["ci", "check", MANIFEST_NAME, "--output", "report.json"])
    assert (repo / "report.json").is_file(), result.output
    assert len(fsyncs) >= 2


def _document() -> dict:
    return vd.build_document(latest="0.1.0", min_supported="0.1.0", artifacts={}, serial=1)


def test_trust_state_is_written_durably(tmp_path: Path, fsyncs: list[int]) -> None:
    installer.check_document_freshness(_document(), tmp_path)
    assert (tmp_path / "trust_state.json").is_file()
    assert len(fsyncs) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["trust_state.json"]


def test_trust_state_failure_is_an_install_error_without_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object) -> None:
        raise OSError(errno.EIO, f"disk fault at {tmp_path}")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(installer.InstallError) as info:
        installer.check_document_freshness(_document(), tmp_path)
    assert str(tmp_path) not in str(info.value)
    assert not (tmp_path / "trust_state.json").exists()


_USER_NAMES = ["report final.json", "_report.json", ".report.sarif", "r\u00e9sum\u00e9.json"]


def _ci_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> tuple[int, Path]:
    from tests.ci_support import MANIFEST_NAME, ci_manifest, make_repo, write, write_clean_pipeline

    from decoy.__main__ import app

    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest())
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["ci", "check", MANIFEST_NAME, "--output", name])
    return result.exit_code, repo


@pytest.mark.parametrize("name", _USER_NAMES)
def test_ci_report_accepts_the_names_it_always_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    baseline, _ = _ci_run(tmp_path / "base", monkeypatch, "report.json")
    code, repo = _ci_run(tmp_path / "named", monkeypatch, name)
    assert (repo / name).is_file()
    assert code == baseline


@pytest.mark.parametrize("name", ["debug log.txt", "_debug.txt", ".debug", "d\u00e9bug.log"])
def test_debug_log_accepts_the_names_it_always_accepted(tmp_path: Path, name: str) -> None:
    sink = DebugSink(tmp_path / name)
    sink.add("label", "line")
    sink.flush()
    assert b"[label] line" in (tmp_path / name).read_bytes()
