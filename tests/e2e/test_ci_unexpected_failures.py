"""An unexpected exception inside ANY layer becomes a fixed `failed` outcome (exit 3).

The exception text carries a canary and an absolute path (the shape of a real engine or
OS error). It must reach neither stdout nor stderr nor the report -- only the explicit
unsafe debug log -- and no traceback (Typer prints locals) may escape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME
from tests.ci_support import (
    MANIFEST_NAME,
    ci_manifest,
    commit_all,
    git,
    make_evidence,
    make_repo,
    write,
    write_clean_pipeline,
)

CANARY = "UNEXPECTED_CANARY_77e1d0aa"
PATTERN = {
    "id": "pii.seeded-test-identifier",
    "literal": "DECOY_TEST_IDENTIFIER_",
    "paths": ["fixtures/**"],
}


def _boom(*_a, **_k):
    raise RuntimeError(f"{CANARY} while reading {Path.cwd()}/secret.csv")


def _fixture(tmp_path: Path, kind: str) -> Path:
    repo = make_repo(tmp_path / "leakroot_9c3a")
    write_clean_pipeline(repo)
    old = {
        "fields": [{"name": "a", "pii_score": 0.1}],
        "quasi_identifier_groups": [],
        "reid_risk_score": 0.1,
    }
    write(repo, "old.json", json.dumps(old))
    write(repo, "new.json", json.dumps(old))
    if kind == "evidence":
        make_evidence(repo)
    extra = {
        "validation": "",
        "drift": "  drift:\n    - {id: d, baseline: old.json, current: new.json}\n",
        "evidence": "  evidence:\n    - {id: e, manifest: build/evidence.json}\n",
        "staged": "",
    }[kind]
    if kind == "staged":
        write(repo, MANIFEST_NAME, ci_manifest(validation=False, patterns=[PATTERN]))
    else:
        write(repo, MANIFEST_NAME, ci_manifest(validation=kind == "validation", extra_checks=extra))
    commit_all(repo)
    if kind == "staged":
        write(repo, "fixtures/a.txt", "x\n")
        git(repo, "add", "fixtures/a.txt")
    return repo


TARGETS = {
    "validation": ("decoy.cli.validate", "run_gate"),
    "drift": ("decoy.cli.scan", "compute_scan_diff"),
    "evidence": ("decoy.cli.evidence", "verify_manifest_issues"),
    "staged": ("decoy.ci.runner", "scan_staged"),
}


def _invoke(repo: Path, monkeypatch: pytest.MonkeyPatch, *extra: str):
    from decoy.__main__ import app

    monkeypatch.chdir(repo)
    return CliRunner().invoke(app, ["ci", "check", MANIFEST_NAME, "--format", "json", *extra])


@pytest.mark.parametrize("kind", sorted(TARGETS))
def test_adapter_exceptions_become_fixed_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    repo = _fixture(tmp_path, kind)
    ok = _invoke(repo, monkeypatch)  # control: the same fixture is healthy
    assert ok.exit_code == EXIT_OK, ok.output
    module, name = TARGETS[kind]
    monkeypatch.setattr(__import__(module, fromlist=[name]), name, _boom)
    result = _invoke(repo, monkeypatch, "--unsafe-debug-log", "dbg.txt")
    assert result.exit_code == EXIT_RUNTIME, result.output
    report = json.loads(result.stdout)
    assert report["status"] == "partial" and report["findings"] == []
    (check,) = [
        c
        for c in report["checks"]
        if c["kind"] in {"validation", "drift", "evidence", "staged_scan"}
    ]
    assert (check["status"], check["reason_code"]) == ("failed", "ci.check_runtime_failure")
    for stream in (result.stdout, result.stderr):
        assert CANARY not in stream and "leakroot_9c3a" not in stream and "Traceback" not in stream
    # the raw cause exists ONLY in the explicit unsafe sink
    assert CANARY in (repo / "dbg.txt").read_text(encoding="utf-8")


def test_a_runner_level_exception_still_yields_one_fixed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fixture(tmp_path, "validation")
    import decoy.cli.ci as ci_module

    monkeypatch.setattr(ci_module, "run_checks", _boom)
    result = _invoke(repo, monkeypatch)
    assert result.exit_code == EXIT_RUNTIME
    report = json.loads(result.stdout)
    assert (report["status"], report["checks"][0]["kind"]) == ("partial", "manifest")
    assert CANARY not in result.stdout + result.stderr


def test_a_manifest_loader_exception_still_yields_one_fixed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fixture(tmp_path, "validation")
    import decoy.cli.ci as ci_module

    monkeypatch.setattr(ci_module, "load_manifest", _boom)
    result = _invoke(repo, monkeypatch)
    assert result.exit_code == EXIT_RUNTIME
    assert json.loads(result.stdout)["checks"][0]["reason_code"] == "ci.check_runtime_failure"
    assert CANARY not in result.stdout + result.stderr
