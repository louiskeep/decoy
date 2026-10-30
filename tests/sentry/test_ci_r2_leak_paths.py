"""A10 round 2: the leak paths a stdout/stderr/report scan cannot see.

Real-process regressions (a harness drives the real CLI after seeding the failure that a
real engine or filesystem produces): engine FILE logs, hostile `--output` and
`--unsafe-debug-log` paths, and a failed debug-log write. Every created OR modified file
in the working tree is scanned, not just the requested report.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from tests.ci_support import (
    MANIFEST_NAME,
    child_env,
    ci_manifest,
    commit_all,
    make_repo,
    write,
    write_clean_pipeline,
)

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE

CANARY_TABLE = "ENGINETABLE_e3c71b90"
ROOT_MARK = "leakroot_r2_4f8a"

# What any engine strategy does on first use (`get_logger()` builds the file handler), then
# the out-of-core capacity advisory the pinned engine logs with the user's table name.
_ENGINE_NOISE = f"""
import logging
from decoy.ci import adapters as _adapters
_orig = _adapters.validation_outcome
def _noisy(*a, **k):
    import decoy_engine.internal.logging as _elog
    _elog.get_logger()
    logging.getLogger("decoy_engine.execution.out_of_core._capacity_eval").warning(
        "capacity advisory: table %s is near its memory budget", {CANARY_TABLE!r})
    return _orig(*a, **k)
_adapters.validation_outcome = _noisy
"""

_FLUSH_FAILS = """
from decoy.ci import debug as _debug
def _fail(self):
    raise OSError("disk full at /secret/leak/path")
_debug.DebugSink.flush = _fail
"""


def run_patched(
    repo: Path, patch: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    script = patch + textwrap.dedent(
        """
        import sys
        from decoy.__main__ import app
        sys.argv = ["decoy", *sys.argv[1:]]
        app()
        """
    )
    return subprocess.run(
        [sys.executable, "-c", script, "ci", "check", MANIFEST_NAME, *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env(env),
        shell=False,
        timeout=180,
        check=False,
    )


def _repo(tmp_path: Path, *, validation: bool = True) -> Path:
    repo = make_repo(tmp_path / ROOT_MARK)
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest(validation=validation))
    commit_all(repo)
    return repo


def _snapshot(repo: Path) -> dict[str, str]:
    snap: dict[str, str] = {}
    for p in repo.rglob("*"):
        if ".git" in p.parts or not p.is_file() or p.is_symlink():
            continue
        snap[p.relative_to(repo).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snap


def _changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(k for k, v in after.items() if before.get(k) != v)


def _assert_value_free(repo: Path, proc, needles: list[str], before: dict[str, str]) -> None:
    for where, text in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        for needle in needles:
            assert needle not in text, f"{needle!r} leaked into {where}"
    after = _snapshot(repo)
    for rel in _changed(before, after):
        data = (repo / rel).read_bytes().decode("utf-8", "replace")
        for needle in needles:
            assert needle not in data, f"{needle!r} leaked into created/modified file {rel}"


# ---- 1. engine FILE logs ------------------------------------------------------------


def test_engine_file_log_is_never_written_and_nothing_leaks(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _snapshot(repo)
    proc = run_patched(repo, _ENGINE_NOISE, "--format", "json")
    assert proc.returncode == EXIT_OK, proc.stderr[-400:]
    _assert_value_free(repo, proc, [CANARY_TABLE, ROOT_MARK], before)
    assert not (repo / "logs").exists(), "decoy ci must not create engine log artifacts"
    assert _changed(before, _snapshot(repo)) == []


def test_preexisting_engine_log_is_untouched(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    log = write(repo, "logs/decoy_engine.log", "2026-01-01 00:00:00 - INFO - earlier run\n")
    stat = log.stat()
    before = _snapshot(repo)
    proc = run_patched(repo, _ENGINE_NOISE, "--format", "json")
    assert proc.returncode == EXIT_OK, proc.stderr[-400:]
    assert log.read_text(encoding="utf-8") == "2026-01-01 00:00:00 - INFO - earlier run\n"
    assert log.stat().st_mtime_ns == stat.st_mtime_ns
    _assert_value_free(repo, proc, [CANARY_TABLE, ROOT_MARK], before)
    assert not list(repo.glob("logs/decoy_engine.log.*")), "no rotation of an existing log"


def test_engine_records_do_not_reach_stderr_via_the_last_resort_handler(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = run_patched(repo, _ENGINE_NOISE, "--format", "json", "--verbose")
    assert CANARY_TABLE not in proc.stdout + proc.stderr
    assert "capacity advisory" not in proc.stdout + proc.stderr


# ---- 2. hostile --output / --unsafe-debug-log paths ---------------------------------


def _hostile_root(tmp_path: Path) -> Path:
    repo = _repo(tmp_path)
    (repo / "loop").symlink_to("loop")  # a symlink loop: resolve() cannot finish
    return repo


@pytest.mark.parametrize("flag", ["--output", "--unsafe-debug-log"])
@pytest.mark.parametrize("target", ["loop/report.json", "loop/deeper/report.json"])
def test_symlink_loop_target_is_a_fixed_refusal_not_a_traceback(
    tmp_path: Path, flag: str, target: str
) -> None:
    repo = _hostile_root(tmp_path)
    before = _snapshot(repo)
    proc = run_patched(repo, "", "--format", "json", flag, target)
    assert proc.returncode == EXIT_USAGE, (proc.returncode, proc.stderr[-400:])
    assert "Traceback" not in proc.stderr and "Error" not in proc.stderr
    assert proc.stdout == ""
    assert proc.stderr.startswith("error: ") and proc.stderr.count("\n") == 1
    _assert_value_free(repo, proc, [ROOT_MARK, str(tmp_path), "loop"], before)


@pytest.mark.parametrize("flag", ["--output", "--unsafe-debug-log"])
def test_overlong_path_component_is_a_fixed_refusal(tmp_path: Path, flag: str) -> None:
    repo = _repo(tmp_path)
    proc = run_patched(repo, "", "--format", "json", flag, "x" * 5000 + "/r.json")
    assert proc.returncode == EXIT_USAGE, (proc.returncode, proc.stderr[-400:])
    assert "Traceback" not in proc.stderr
    assert ROOT_MARK not in proc.stderr and str(tmp_path) not in proc.stderr


@pytest.mark.parametrize("flag", ["--output", "--unsafe-debug-log"])
def test_filesystem_failure_while_resolving_is_a_fixed_refusal(tmp_path: Path, flag: str) -> None:
    repo = _repo(tmp_path)
    patch = f"""
from pathlib import Path
_real = Path.resolve
def _boom(self, *a, **k):
    if self.name == "poison":
        raise OSError(5, "I/O error", "{tmp_path}/{ROOT_MARK}/poison")
    return _real(self, *a, **k)
Path.resolve = _boom
"""
    proc = run_patched(repo, patch, "--format", "json", flag, "poison/r.json")
    assert proc.returncode == EXIT_USAGE, (proc.returncode, proc.stderr[-400:])
    assert "Traceback" not in proc.stderr
    assert ROOT_MARK not in proc.stderr and str(tmp_path) not in proc.stderr


# ---- 4. a failed debug-log write must not claim success -----------------------------


def test_failed_debug_log_flush_reports_failure_only(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = run_patched(repo, _FLUSH_FAILS, "--format", "json", "--unsafe-debug-log", "dbg.txt")
    assert "could not write the debug log" in proc.stderr
    assert "was written" not in proc.stderr, "must not claim a log that does not exist"
    assert not (repo / "dbg.txt").exists()
    assert "disk full" not in proc.stderr and "/secret" not in proc.stderr
    # The requested artifact is missing, so a clean report must not look like a clean run.
    assert proc.returncode == EXIT_RUNTIME
    assert '"status":"ok"' in proc.stdout


def test_failed_debug_log_flush_never_masks_a_worse_exit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / ROOT_MARK)
    write(repo, MANIFEST_NAME, "schema_version: nope\n")  # refused -> usage exit
    commit_all(repo)
    proc = run_patched(repo, _FLUSH_FAILS, "--format", "json", "--unsafe-debug-log", "dbg.txt")
    assert proc.returncode == EXIT_USAGE
    assert "was written" not in proc.stderr
    assert "could not write the debug log" in proc.stderr


def test_successful_debug_log_still_warns(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = run_patched(repo, "", "--format", "json", "--unsafe-debug-log", "dbg.txt")
    assert proc.returncode == EXIT_OK, proc.stderr[-400:]
    assert (repo / "dbg.txt").exists()
    assert "UNSAFE debug log was written" in proc.stderr
    assert os.path.getsize(repo / "dbg.txt") > 0
