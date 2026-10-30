"""Shared helpers for the F43 CI acceptance suite.

Everything here drives the REAL boundary: a real `git` repository on disk and
the real `decoy` process (`python -m decoy`), so stdout, stderr and the exit
integer are the ones a CI runner would see. Nothing in this module patches the
code under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SARIF_SCHEMA_PATH = Path(__file__).parent / "fixtures" / "schemas" / "sarif-schema-2.1.0.json"

MANIFEST_NAME = ".decoy-ci.yaml"

# Line/column layout of CLEAN_PIPELINE is pinned: tests assert exact marks.
CLEAN_PIPELINE = """\
version: 1
global_settings:
  seed: 42
sources:
  customers:
    type: file
    format: csv
    path: data/in.csv
tables:
  - name: customers
    columns:
      - name: email
        strategy: faker
        provider: person_email
        deterministic: true
        namespace: cust_ns
targets:
  customers:
    type: file
    format: csv
    path: out/out.csv
"""


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200", "PYTHONUTF8": "1"})
    env.pop("FORCE_COLOR", None)
    if extra:
        env.update(extra)
    return env


def git(
    repo: Path, *args: str, input: bytes | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input,
        capture_output=True,
        env=child_env(),
        shell=False,
        check=False,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr.decode(errors='replace')}")
    return proc


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "ci@example.invalid")
    git(root, "config", "user.name", "ci")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "core.autocrlf", "false")
    return root


def write(repo: Path, rel: str, content: str | bytes) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="")
    return path


def write_clean_pipeline(
    repo: Path, rel: str = "pipeline.yaml", *, text: str = CLEAN_PIPELINE
) -> Path:
    write(repo, "data/in.csv", "email\na@example.invalid\nb@example.invalid\n")
    (repo / "out").mkdir(exist_ok=True)
    return write(repo, rel, text)


def run_decoy(
    args: list[str], cwd: Path, *, env: dict[str, str] | None = None, timeout: int = 180
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "decoy", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env(env),
        shell=False,
        timeout=timeout,
        check=False,
    )


def ci_check(
    repo: Path, *extra: str, manifest: str = MANIFEST_NAME, env: dict[str, str] | None = None
):
    return run_decoy(["ci", "check", manifest, *extra], repo, env=env)


def load_sarif_schema() -> dict[str, Any]:
    return json.loads(SARIF_SCHEMA_PATH.read_text(encoding="utf-8"))


def assert_valid_sarif(doc: dict[str, Any]) -> None:
    """Validate against the vendored OASIS schema (Draft-04). The schema is the
    oracle; callers add assertions on top of it, never instead of it."""
    import jsonschema

    jsonschema.Draft4Validator(load_sarif_schema()).validate(doc)


def ci_manifest(
    *,
    validation: bool = True,
    patterns: list[dict[str, Any]] | None = None,
    extra_checks: str = "",
    pipelines: str = "  - id: primary\n    path: pipeline.yaml\n",
    staged: str | None = None,
) -> str:
    """Render a small decoy-ci/v1 manifest as YAML text."""
    lines = ["schema_version: decoy-ci/v1", "", "pipelines:", pipelines.rstrip("\n"), "", "checks:"]
    if validation:
        lines += [
            "  validation:",
            "    enabled: true",
            "    mode: full",
            "    pipelines: [primary]",
        ]
    else:
        lines += ["  validation:", "    enabled: false"]
    if extra_checks:
        lines.append(extra_checks.rstrip("\n"))
    if staged is not None:
        lines += ["", staged.rstrip("\n")]
    elif patterns is not None:
        lines += ["", "staged_scan:", "  enabled: true", "  patterns:"]
        for p in patterns:
            lines.append(f"    - id: {p['id']}")
            lines.append(f"      literal: {json.dumps(p['literal'])}")
            lines.append(f"      paths: {json.dumps(p.get('paths', ['**']))}")
            lines.append(f"      exclude_paths: {json.dumps(p.get('exclude_paths', []))}")
    return "\n".join(lines) + "\n"


def make_evidence(repo: Path, rel: str = "build/evidence.json") -> Path:
    """Produce a REAL cli-local-1 evidence manifest by running the pipeline."""
    (repo / Path(rel).parent).mkdir(parents=True, exist_ok=True)
    proc = run_decoy(["run", "pipeline.yaml", "--evidence-out", rel], repo)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return repo / rel


def commit_all(repo: Path, message: str = "base") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def parse_stdout(proc: subprocess.CompletedProcess) -> Any:
    """json.loads(stdout) that fails with the process evidence instead of a bare decode error."""
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"stdout was not JSON (exit {proc.returncode}): {proc.stdout[:200]!r} | stderr: {proc.stderr[-600:]!r}"
        ) from exc
