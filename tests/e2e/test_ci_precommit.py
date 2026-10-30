"""A8: the shipped pre-commit provider manifest, run by the REAL `pre-commit`, offline.

The hook repository is a throwaway Git repo that contains only the shipped
`.pre-commit-hooks.yaml`, consumed through pre-commit's own `repo:`/`rev:`
machinery. The hook must reach the preinstalled `decoy` on PATH without
installing anything or touching the network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

from tests.ci_support import (
    MANIFEST_NAME,
    ci_manifest,
    commit_all,
    git,
    make_repo,
    write,
    write_clean_pipeline,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_FILE = REPO_ROOT / ".pre-commit-hooks.yaml"
LITERAL = "DECOY_TEST_IDENTIFIER_"
SEEDED_VALUE = "DECOY_TEST_IDENTIFIER_8c1d3f"
PATTERN = {"id": "pii.seeded-test-identifier", "literal": LITERAL, "paths": ["fixtures/**"]}
BIN_DIR = Path(sys.executable).parent


def _tool(name: str) -> str:
    exe = BIN_DIR / name
    assert exe.exists(), f"{name} must be installed next to the test interpreter (dev extra)"
    return str(exe)


def test_provider_manifest_has_the_required_hook_contract() -> None:
    hooks = yaml.safe_load(HOOKS_FILE.read_text(encoding="utf-8"))
    (hook,) = hooks
    assert hook["id"] == "decoy-ci-check"
    assert hook["language"] == "unsupported"  # preinstalled executable; no environment download
    assert hook["pass_filenames"] is False  # worktree filenames never become the scan source
    assert hook["always_run"] is True  # the command decides the true staged no-op
    assert hook["stages"] == ["pre-commit"]
    assert hook["minimum_pre_commit_version"] == "4.4.0"
    assert hook["entry"].split()[:3] == ["decoy", "ci", "check"]
    assert "--context pre-commit" in hook["entry"]
    assert "--unsafe-debug-log" not in HOOKS_FILE.read_text(encoding="utf-8")


def test_provider_manifest_validates_with_pre_commit_itself() -> None:
    proc = subprocess.run(
        [_tool("pre-commit"), "validate-manifest", str(HOOKS_FILE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _env(tmp_path: Path) -> dict[str, str]:
    guard = tmp_path / "netguard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        textwrap.dedent(
            """
            import socket

            _real = socket.socket.connect

            def _deny(self, address):
                if self.family == socket.AF_UNIX:
                    return _real(self, address)
                raise OSError("network access denied by the F43 offline test guard")

            socket.socket.connect = _deny
            """
        ),
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        {
            "PATH": f"{BIN_DIR}{os.pathsep}{env['PATH']}",
            "PIP_NO_INDEX": "1",
            "PRE_COMMIT_HOME": str(tmp_path / "pc-home"),
            "PYTHONPATH": str(guard),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_COLOR": "1",
            "TERM": "dumb",
        }
    )
    return env


def _consumer(tmp_path: Path, manifest: str) -> tuple[Path, dict[str, str]]:
    hook_repo = make_repo(tmp_path / "hook-provider")
    shutil.copy(HOOKS_FILE, hook_repo / ".pre-commit-hooks.yaml")
    commit_all(hook_repo, "provider")
    rev = git(hook_repo, "rev-parse", "HEAD").stdout.decode().strip()

    repo = make_repo(tmp_path / "consumer")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, manifest)
    write(
        repo,
        ".pre-commit-config.yaml",
        yaml.safe_dump(
            {"repos": [{"repo": str(hook_repo), "rev": rev, "hooks": [{"id": "decoy-ci-check"}]}]}
        ),
    )
    commit_all(repo)
    return repo, _env(tmp_path)


def _run_hook(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_tool("pre-commit"), "run", "--verbose"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_hook_blocks_a_staged_seeded_identifier_and_prints_no_value(tmp_path: Path) -> None:
    repo, env = _consumer(tmp_path, ci_manifest(patterns=[PATTERN]))
    write(repo, "fixtures/seed.txt", f"name,id\nx,{SEEDED_VALUE}\n")
    git(repo, "add", "fixtures/seed.txt")
    proc = _run_hook(repo, env)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "pii.seeded-test-identifier" in out
    assert "fixtures/seed.txt" in out
    assert SEEDED_VALUE not in out and LITERAL not in out and "8c1d3f" not in out
    # the narrowed validation is announced to the human, once
    assert "Running in pre-commit mode; validation narrowed from 'full' to 'config'" in out


def test_hook_passes_a_clean_staged_fixture(tmp_path: Path) -> None:
    repo, env = _consumer(tmp_path, ci_manifest(patterns=[PATTERN]))
    write(repo, "fixtures/clean.txt", "name,id\nx,not-sensitive\n")
    git(repo, "add", "fixtures/clean.txt")
    proc = _run_hook(repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Passed" in proc.stdout


def test_hook_reads_the_index_not_the_worktree(tmp_path: Path) -> None:
    repo, env = _consumer(tmp_path, ci_manifest(patterns=[PATTERN]))
    write(repo, "fixtures/seed.txt", f"{SEEDED_VALUE}\n")
    git(repo, "add", "fixtures/seed.txt")
    write(repo, "fixtures/seed.txt", "sanitised in the worktree only\n")
    proc = _run_hook(repo, env)
    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_hook_with_nothing_staged_is_a_clean_noop(tmp_path: Path) -> None:
    repo, env = _consumer(tmp_path, ci_manifest(patterns=[PATTERN]))
    proc = _run_hook(repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_offline_guard_really_denies_network(tmp_path: Path) -> None:
    """Negative control: the guard used above is genuinely active in the child."""
    env = _env(tmp_path)
    probe = "import socket; s = socket.socket(); s.connect(('93.184.216.34', 80))"
    proc = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True, check=False
    )
    assert proc.returncode != 0 and "offline test guard" in proc.stderr
