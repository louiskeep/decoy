"""A9: the shipped GitHub Actions / GitLab CI templates are thin invokers.

Static parsing proves platform shape and the invoker-only contract; the extracted
commands are then EXECUTED against a real fixture repo to prove they are runnable.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tests.ci_support import (
    MANIFEST_NAME,
    assert_valid_sarif,
    ci_manifest,
    make_repo,
    write,
    write_clean_pipeline,
)

from decoy.cli.exit_codes import EXIT_OK

REPO_ROOT = Path(__file__).resolve().parents[2]
GITHUB = REPO_ROOT / "integrations" / "github-actions" / "decoy-ci.yml"
GITLAB = REPO_ROOT / "integrations" / "gitlab" / "decoy-ci.yml"
CHECK_CMD = "decoy ci check .decoy-ci.yaml --format sarif --output decoy.sarif"
SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
FORBIDDEN = (
    "curl ",
    "wget ",
    "pip install",
    "pip3 install",
    "npm ",
    "gh pr",
    "gh api",
    "unsafe-debug-log",
    "git push",
    "sudo ",
    "eval ",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _github_steps(doc: dict):
    for job_id, job in doc["jobs"].items():
        for step in job.get("steps", []):
            yield job_id, step


def _decoy_lines(script: str) -> list[str]:
    return [
        ln.strip()
        for ln in script.splitlines()
        if re.search(r"(^|\$\(|[;&|]\s*)decoy\s", ln) and not ln.strip().startswith("#")
    ]


def test_github_permissions_are_least_privilege() -> None:
    doc = _load(GITHUB)
    assert doc["permissions"] == {"contents": "read"}
    for job_id, job in doc["jobs"].items():
        perms = job.get("permissions", doc["permissions"])
        extra = {k for k, v in perms.items() if v != "read"}
        if job_id == "upload-sarif":
            assert extra == {"security-events"} and perms["security-events"] == "write"
            assert "vars.DECOY_UPLOAD_SARIF" in job["if"]  # explicit customer opt-in
        else:
            assert not extra, (job_id, perms)


def test_github_uses_are_immutable_pins() -> None:
    for _, step in _github_steps(_load(GITHUB)):
        if "uses" in step:
            assert SHA_PIN.match(step["uses"]), step["uses"]


def test_github_check_step_is_exactly_the_documented_contract() -> None:
    doc = _load(GITHUB)
    runs = [s["run"] for _, s in _github_steps(doc) if "run" in s]
    check = [ln for r in runs for ln in _decoy_lines(r) if "ci check" in ln]
    assert check == [CHECK_CMD]
    # nothing else invokes decoy except the version probe
    others = [ln for r in runs for ln in _decoy_lines(r) if "ci check" not in ln]
    assert all("--version" in ln for ln in others), others
    text = GITHUB.read_text(encoding="utf-8")
    assert "DECOY_EXPECTED_VERSION" in text  # runtime version is checked, not assumed


def test_github_upload_is_a_distinct_explicit_step_and_decoy_never_uploads() -> None:
    doc = _load(GITHUB)
    uploads = [
        (j, s)
        for j, s in _github_steps(doc)
        if str(s.get("uses", "")).startswith("github/codeql-action/upload-sarif@")
    ]
    assert len(uploads) == 1 and uploads[0][0] == "upload-sarif"
    assert uploads[0][1]["with"]["sarif_file"] == "decoy.sarif"
    for _job_id, step in _github_steps(doc):
        if "run" in step:
            assert "upload" not in step["run"].lower().replace("upload-artifact", ""), step["run"]


def test_github_artifact_paths_are_fixed() -> None:
    doc = _load(GITHUB)
    paths = [
        s["with"]["path"]
        for _, s in _github_steps(doc)
        if str(s.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert paths == ["decoy.sarif"]


def test_gitlab_hidden_job_runs_only_the_documented_command() -> None:
    doc = _load(GITLAB)
    job = doc[".decoy-ci-check"]
    script = "\n".join(job["script"])
    assert [ln for ln in _decoy_lines(script) if "ci check" in ln] == [CHECK_CMD]
    assert all("--version" in ln for ln in _decoy_lines(script) if "ci check" not in ln)
    assert "DECOY_EXPECTED_VERSION" in job["variables"]
    assert job["artifacts"]["paths"] == ["decoy.sarif"]
    assert job["artifacts"]["when"] == "always"
    # a reusable template: no concrete job is defined by merely including it
    assert [k for k in doc if not k.startswith(".")] == []


@pytest.mark.parametrize("path", [GITHUB, GITLAB])
def test_no_hidden_network_comment_or_install_behavior(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for bad in FORBIDDEN:
        assert bad not in text, (path.name, bad)
    assert "invoker only" in text.lower()


def test_gitlab_template_does_not_claim_annotation_conversion() -> None:
    assert "annotation" not in GITLAB.read_text(encoding="utf-8").lower()


def _runnable_env(tmp_path: Path) -> dict[str, str]:
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "decoy"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m decoy "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return {
        **os.environ,
        "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
        "NO_COLOR": "1",
        "TERM": "dumb",
    }


def _version() -> str:
    out = subprocess.run(
        [sys.executable, "-m", "decoy", "--version"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip().split()[-1]


def _bash(script: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_extracted_commands_run_against_a_real_fixture(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest())
    env = _runnable_env(tmp_path)

    gh_scripts = [s["run"] for _, s in _github_steps(_load(GITHUB)) if "run" in s]
    gl = _load(GITLAB)[".decoy-ci-check"]
    gl_scripts = ["\n".join(gl["script"])]

    for scripts in (gh_scripts, gl_scripts):
        for f in repo.glob("decoy.sarif"):
            f.unlink()
        probe = next(s for s in scripts if "DECOY_EXPECTED_VERSION" in s)
        ok = _bash(probe, repo, {**env, "DECOY_EXPECTED_VERSION": _version()})
        assert ok.returncode == 0, ok.stderr
        bad = _bash(probe, repo, {**env, "DECOY_EXPECTED_VERSION": "0.0.0-not-this"})
        assert bad.returncode != 0
        missing = _bash(
            probe, repo, {**env, "DECOY_EXPECTED_VERSION": _version(), "PATH": "/usr/bin:/bin"}
        )
        assert missing.returncode != 0
        check_script = next(s for s in scripts if "ci check" in s)
        done = _bash(check_script, repo, {**env, "DECOY_EXPECTED_VERSION": _version()})
        assert done.returncode == EXIT_OK, done.stdout + done.stderr
        import json

        assert_valid_sarif(json.loads((repo / "decoy.sarif").read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", [GITHUB, GITLAB])
def test_template_version_pin_matches_the_packaged_version(path: Path) -> None:
    """A release bump must refresh the shipped pin, or the template ships a failing check."""
    assert f'DECOY_EXPECTED_VERSION: "{_version()}"' in path.read_text(encoding="utf-8")
