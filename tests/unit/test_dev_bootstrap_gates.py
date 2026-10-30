"""The worker harness scripts (`scripts/dev/bootstrap.sh`, `scripts/dev/gates.sh`).

bootstrap must fail loudly when the installed engine differs from the pyproject pin, and
`gates.sh --baseline` must compute which failing tests are branch-only rather
than leave "same failures as baseline" as a claim."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEV = REPO / "scripts" / "dev"
BASH = shutil.which("bash")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(BASH is None or GIT is None, reason="needs bash and git")


def _run(
    argv: list[str], cwd: Path, check: bool = False, **extra: str
) -> subprocess.CompletedProcess[str]:
    # Point the scripts at the interpreter running this test so nothing is installed.
    env = {**os.environ, "DECOY_VENV": sys.prefix, **extra}
    env.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=600, check=check
    )


def _git(cwd: Path, *args: str) -> str:
    ident = ["-c", "user.name=gates-test", "-c", "user.email=gates-test@example.invalid"]
    return _run([str(GIT), *ident, *args], cwd, check=True).stdout


LOCK = "requirements-dev.lock"
needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="bootstrap.sh drives uv")


def _bootstrap_copy(tmp_path: Path) -> Path:
    """The files bootstrap.sh reads, copied so a test can corrupt one of them."""
    for rel in ("pyproject.toml", LOCK, ".github/workflows/ci.yml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, tmp_path / rel)
    shutil.copytree(DEV, tmp_path / "scripts" / "dev")
    return tmp_path


def _check(root: Path) -> tuple[int, str]:
    proc = _run([str(BASH), "scripts/dev/bootstrap.sh", "--check"], root)
    return proc.returncode, proc.stdout + proc.stderr


@needs_uv
def test_bootstrap_check_fails_on_an_engine_pin_that_differs_from_the_install(
    tmp_path: Path,
) -> None:
    _bootstrap_copy(tmp_path)
    text, n = re.subn(
        r'"decoy-engine==[^"]+"', '"decoy-engine==0.0.1"', (REPO / "pyproject.toml").read_text()
    )
    assert n == 1, "decoy-engine pin not found in pyproject.toml"
    (tmp_path / "pyproject.toml").write_text(text)

    proc = _run([str(BASH), "scripts/dev/bootstrap.sh", "--check"], tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert re.search(r"decoy-engine\s+installed \S+\s+pin 0\.0\.1\s+MISMATCH", out), out
    assert "BOOTSTRAP FAIL: decoy-engine installed" in out, out
    assert "fix:" in out


def test_the_lock_pins_every_package_exactly() -> None:
    lines = [ln for ln in (REPO / LOCK).read_text().splitlines() if ln and ln[0].isalnum()]
    assert len(lines) > 20, lines
    for ln in lines:
        assert re.fullmatch(
            r"[A-Za-z0-9._-]+(\[[^\]]+\])?==\S+ \\|decoy-engine @ git\+\S+@[0-9a-f]{40}", ln
        ), ln


@needs_uv
def test_bootstrap_fails_when_the_lock_is_missing(tmp_path: Path) -> None:
    (_bootstrap_copy(tmp_path) / LOCK).unlink()
    # The install run gets a throwaway venv and no network, so a regression cannot install anything.
    offline = {
        "DECOY_VENV": str(tmp_path / "venv"),
        "UV_OFFLINE": "1",
        "PIP_NO_INDEX": "1",
        "GIT_ALLOW_PROTOCOL": "file",
    }
    for argv, env in ((["--check"], {}), ([], offline)):
        proc = _run([str(BASH), "scripts/dev/bootstrap.sh", *argv], tmp_path, **env)
        out = proc.stdout + proc.stderr
        assert proc.returncode != 0, out
        assert f"BOOTSTRAP FAIL: {LOCK} is missing" in out, out


@needs_uv
def test_bootstrap_check_fails_on_an_installed_version_that_differs_from_the_lock(
    tmp_path: Path,
) -> None:
    lock = _bootstrap_copy(tmp_path) / LOCK
    text, n = re.subn(r"(?m)^duckdb==\S+", "duckdb==0.0.1", lock.read_text())
    assert n == 1, "duckdb pin not found in the lock"
    lock.write_text(text)
    rc, out = _check(tmp_path)
    assert rc != 0, out
    assert re.search(r"duckdb\s+installed \S+\s+lock 0\.0\.1\s+MISMATCH", out), out
    assert "BOOTSTRAP FAIL: duckdb installed" in out, out


@needs_uv
def test_bootstrap_check_fails_on_a_lock_that_is_stale_against_pyproject(tmp_path: Path) -> None:
    pyproject = _bootstrap_copy(tmp_path) / "pyproject.toml"
    text, n = re.subn(r'(?m)^ *"jsonschema>=4,<5",\n', "", pyproject.read_text())
    assert n == 1, "jsonschema dev requirement not found in pyproject.toml"
    pyproject.write_text(text)
    rc, out = _check(tmp_path)
    assert rc != 0, out
    assert f"BOOTSTRAP FAIL: {LOCK} is stale against pyproject.toml" in out, out


@needs_uv
def test_lock_check_passes_on_the_committed_lock(tmp_path: Path) -> None:
    # Positive control for the staleness test: the committed lock re-resolves to itself.
    proc = _run([str(BASH), "scripts/dev/lock.sh", "--check"], _bootstrap_copy(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _seeded_clone(tmp_path: Path) -> Path:
    """A clone whose origin/main has one shared failure and whose HEAD adds one more."""
    clone = tmp_path / "repo"
    _git(tmp_path, "clone", "-q", "--shared", str(REPO), str(clone))
    # Test the scripts in this working tree, not whatever the clone's HEAD carries.
    shutil.rmtree(clone / "scripts" / "dev", ignore_errors=True)
    shutil.copytree(DEV, clone / "scripts" / "dev")
    seed = clone / "tests" / "_seeded"
    seed.mkdir()
    (seed / "test_seed_shared.py").write_text("def test_shared():\n    assert False\n")
    (seed / "test_seed_ok.py").write_text("def test_ok():\n    assert True\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "base")
    _git(clone, "update-ref", "refs/remotes/origin/main", "HEAD")
    (seed / "test_seed_branch.py").write_text("def test_branch():\n    assert False\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "seed")
    return clone


def test_gates_baseline_reports_a_seeded_failure_as_branch_only(tmp_path: Path) -> None:
    clone = _seeded_clone(tmp_path)
    argv = [str(BASH), "scripts/dev/gates.sh", "--steps", "tests", "--baseline", "tests/_seeded"]
    proc = _run(argv, clone)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "EVIDENCE" in out, out
    ids = out.split("FAILING TEST IDS", 1)[-1]
    assert re.search(r"BRANCH-ONLY\s+tests/_seeded/test_seed_branch\.py::test_branch", ids), out
    assert re.search(r"BOTH\s+tests/_seeded/test_seed_shared\.py::test_shared", ids), out
    assert "test_ok" not in ids, out
    assert "branch-only=1" in ids, out
    worktrees = _git(clone, "worktree", "list").splitlines()
    assert len(worktrees) == 1, f"baseline worktree was not cleaned up: {worktrees}"


def test_gates_passes_a_green_run_with_an_evidence_block(tmp_path: Path) -> None:
    clone = _seeded_clone(tmp_path)
    argv = [str(BASH), "scripts/dev/gates.sh", "--steps", "tests", "tests/_seeded/test_seed_ok.py"]
    proc = _run(argv, clone)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert re.search(r"(?m)^=+ EVIDENCE =+$", proc.stdout), out
    assert "[tests] PASS passed=1 failed=0" in proc.stdout, out


_BROKEN_REPORTERS = {
    "missing": None,
    "crashing": "raise SystemExit('reporter crashed')\n",
    "silent": "",
    "truncated": "print('=' * 30 + ' EVIDENCE ' + '=' * 30)\n",
    # A complete block is still not a pass when the reporter itself fails.
    "nonzero": "print('=' * 30 + ' EVIDENCE ' + '=' * 30)\nprint('=' * 70)\nraise SystemExit(1)\n",
}


@pytest.mark.parametrize("kind", sorted(_BROKEN_REPORTERS))
def test_gates_fails_when_the_reporter_does_not_print_evidence(tmp_path: Path, kind: str) -> None:
    clone = _seeded_clone(tmp_path)
    reporter = clone / "scripts" / "dev" / "_gates_report.py"
    body = _BROKEN_REPORTERS[kind]
    if body is None:
        reporter.unlink()
    else:
        reporter.write_text(body)
    argv = [str(BASH), "scripts/dev/gates.sh", "--steps", "tests", "tests/_seeded/test_seed_ok.py"]
    proc = _run(argv, clone)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "gates: FAIL: no complete EVIDENCE block" in proc.stderr, out


@pytest.mark.parametrize("steps", ["tests", ""])
def test_gates_fails_when_no_step_ran(tmp_path: Path, steps: str) -> None:
    # A gate that ran nothing is not a pass, even though nothing failed.
    clone = _seeded_clone(tmp_path)
    argv = [str(BASH), "scripts/dev/gates.sh", "--steps", steps, "tests/_seeded/absent.py"]
    proc = _run(argv, clone)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "gates: FAIL: no step ran" in proc.stderr, out
