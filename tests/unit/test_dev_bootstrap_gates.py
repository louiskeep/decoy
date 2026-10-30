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


def _run(argv: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    # Point the scripts at the interpreter running this test so nothing is installed.
    env = dict(os.environ, DECOY_VENV=sys.prefix)
    env.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=600, check=check
    )


def _git(cwd: Path, *args: str) -> str:
    ident = ["-c", "user.name=gates-test", "-c", "user.email=gates-test@example.invalid"]
    return _run([str(GIT), *ident, *args], cwd, check=True).stdout


def test_bootstrap_check_fails_on_an_engine_pin_that_differs_from_the_install(
    tmp_path: Path,
) -> None:
    text, n = re.subn(
        r'"decoy-engine==[^"]+"', '"decoy-engine==0.0.1"', (REPO / "pyproject.toml").read_text()
    )
    assert n == 1, "decoy-engine pin not found in pyproject.toml"
    (tmp_path / "pyproject.toml").write_text(text)
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True)
    shutil.copy2(REPO / ".github" / "workflows" / "ci.yml", wf)
    shutil.copytree(DEV, tmp_path / "scripts" / "dev")

    proc = _run([str(BASH), "scripts/dev/bootstrap.sh", "--check"], tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert re.search(r"decoy-engine\s+installed \S+\s+pin 0\.0\.1\s+MISMATCH", out), out
    assert "BOOTSTRAP FAIL: decoy-engine installed" in out, out
    assert "fix:" in out


def test_gates_baseline_reports_a_seeded_failure_as_branch_only(tmp_path: Path) -> None:
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
