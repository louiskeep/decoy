"""A3: the exit matrix. Real CLI process, real pinned engine, real git, constants only.

The single in-process row is the capacity refusal, which (like the existing
`validate` suite) can only be provoked by patching the estimator BENEATH the
asserted boundary; the command and its exit mapping are still the real ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.cli.exit_codes import (
    EXIT_CAPACITY,
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    EXIT_WARNINGS,
)
from tests.ci_support import (
    CLEAN_PIPELINE,
    MANIFEST_NAME,
    ci_check,
    ci_manifest,
    commit_all,
    git,
    make_evidence,
    make_repo,
    parse_stdout,
    write,
    write_clean_pipeline,
)

PATTERN = {
    "id": "pii.seeded-test-identifier",
    "literal": "DECOY_TEST_IDENTIFIER_",
    "paths": ["fixtures/**"],
}
EVIDENCE = "  evidence:\n    - id: protected-output\n      manifest: build/evidence.json\n"


def _repo(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    return repo


def _run(repo: Path, *extra: str):
    proc = ci_check(repo, "--format", "json", *extra)
    return proc, parse_stdout(proc)


def _check(report: dict, kind: str) -> dict:
    (c,) = [c for c in report["checks"] if c["kind"] == kind]
    return c


def test_clean_validation_is_ok(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, MANIFEST_NAME, ci_manifest())
    proc, report = _run(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (report["status"], report["exit_code"]) == ("ok", EXIT_OK)
    assert report["findings"] == []


def test_staged_only_manifest_with_nothing_staged_is_noop(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, patterns=[PATTERN]))
    commit_all(repo)
    proc, report = _run(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (report["status"], report["exit_code"]) == ("noop", EXIT_OK)
    assert _check(report, "staged_scan")["reason_code"] == "ci.no_staged_files"


def test_staged_hit_is_findings_exit_four(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, patterns=[PATTERN]))
    commit_all(repo)
    write(repo, "fixtures/a.txt", "x\nDECOY_TEST_IDENTIFIER_123\n")
    git(repo, "add", "fixtures/a.txt")
    proc, report = _run(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert (report["status"], report["exit_code"]) == ("findings", EXIT_FINDINGS)
    assert report["findings"][0]["rule_id"] == "staged.pii.seeded-test-identifier"


def test_real_evidence_mismatch_is_findings_exit_four(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    make_evidence(repo)
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=EVIDENCE))
    ok, report = _run(repo)
    assert ok.returncode == EXIT_OK, ok.stderr
    assert _check(report, "evidence")["status"] == "ok"
    write(repo, "out/out.csv", "tampered\n")
    proc, report = _run(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert report["status"] == "findings"
    assert report["findings"][0]["rule_id"] == "evidence.output_fingerprint_changed"
    # prose from `report verify` (hash prefixes, paths) never reaches the report
    assert "sha256" not in proc.stdout


def test_unreadable_evidence_manifest_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "build/evidence.json", "{not json")
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=EVIDENCE))
    proc, report = _run(repo)
    assert proc.returncode == EXIT_USAGE
    assert report["status"] == "refused"
    assert _check(report, "evidence")["reason_code"] == "ci.evidence_unreadable"


def test_drift_blocking_and_non_blocking(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    old = {
        "fields": [{"name": "a", "pii_score": 0.1}],
        "quasi_identifier_groups": [],
        "reid_risk_score": 0.1,
    }
    new = {
        "fields": [{"name": "a", "pii_score": 0.9}],
        "quasi_identifier_groups": [],
        "reid_risk_score": 0.1,
    }
    write(repo, "ci/base.json", json.dumps(old))
    write(repo, "build/cur.json", json.dumps(new))
    drift = "  drift:\n    - {id: discovery-baseline, baseline: ci/base.json, current: build/cur.json, blocking: %s}\n"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=drift % "true"))
    proc, report = _run(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert report["findings"][0]["rule_id"].startswith("drift.")
    assert report["findings"][0]["level"] == "error"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=drift % "false"))
    proc, report = _run(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert report["findings"][0]["level"] == "warning"
    write(repo, "build/cur.json", json.dumps(old))
    proc, report = _run(repo)
    assert proc.returncode == EXIT_OK and report["findings"] == []


def test_one_clean_check_then_a_real_git_failure_is_partial_exit_three(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, MANIFEST_NAME, ci_manifest(patterns=[PATTERN]))
    commit_all(repo)
    (repo / ".git" / "index").write_bytes(b"this is not a git index")
    proc, report = _run(repo)
    assert proc.returncode == EXIT_RUNTIME, proc.stderr
    assert (report["status"], report["exit_code"]) == ("partial", EXIT_RUNTIME)
    assert _check(report, "validation")["status"] == "ok"
    staged = _check(report, "staged_scan")
    assert (staged["status"], staged["reason_code"]) == ("failed", "ci.git_failure")


def test_malformed_manifest_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, MANIFEST_NAME, "schema_version: decoy-ci/v1\nunknown_field: 1\n")
    proc, report = _run(repo)
    assert proc.returncode == EXIT_USAGE
    assert (report["status"], report["exit_code"]) == ("refused", EXIT_USAGE)
    assert report["checks"][0]["reason_code"] == "ci.manifest_invalid"


def test_missing_manifest_is_refused_not_a_crash(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc, report = _run(
        repo,
    )
    assert proc.returncode == EXIT_USAGE
    assert report["status"] == "refused"
    assert report["checks"][0]["reason_code"] == "ci.manifest_unreadable"


def test_non_empty_regression_selection_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reg = "  regression_suites:\n    - {id: golden, suite: suites/golden}\n"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=reg))
    proc, report = _run(repo)
    assert proc.returncode == EXIT_USAGE
    assert report["status"] == "refused"
    assert _check(report, "regression")["reason_code"] == "ci.regression_runner_unavailable"
    # alongside a completed check the same refusal is `partial`
    write(repo, MANIFEST_NAME, ci_manifest(extra_checks=reg))
    proc, report = _run(repo)
    assert proc.returncode == EXIT_USAGE
    assert report["status"] == "partial"
    assert _check(report, "validation")["status"] == "ok"


def test_over_limit_staged_scan_is_partial_exit_usage_never_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, patterns=[PATTERN]))
    commit_all(repo)
    for i in range(201):
        write(repo, f"fixtures/f{i:03d}.txt", "clean\n")
    git(repo, "add", "fixtures")
    proc, report = _run(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert (report["status"], report["exit_code"]) == ("partial", EXIT_USAGE)
    assert _check(report, "staged_scan")["reason_code"] == "ci.staged_scan_limit"


def test_validation_warning_blocks_only_when_configured(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "out/out.csv", "already here\n")
    write(repo, MANIFEST_NAME, ci_manifest())  # default: warnings block
    proc, report = _run(repo)
    assert proc.returncode == EXIT_WARNINGS, proc.stderr
    assert report["status"] == "findings"
    assert report["findings"][0]["level"] == "warning"
    relaxed = ci_manifest().replace("mode: full", "mode: full\n    fail_on_warning: false")
    write(repo, MANIFEST_NAME, relaxed)
    proc, report = _run(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert report["findings"][0]["level"] == "warning"


def test_validation_error_keeps_the_existing_validate_exit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "pipeline.yaml", CLEAN_PIPELINE.replace("person_email", "not_a_real_provider"))
    write(repo, MANIFEST_NAME, ci_manifest())
    proc, report = _run(repo)
    assert proc.returncode == EXIT_USAGE
    assert (report["status"], report["exit_code"]) == ("findings", EXIT_USAGE)


def test_capacity_refusal_exits_capacity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import decoy_engine.execution as engine_exec
    from decoy_engine import ExecutionError

    from decoy.__main__ import app
    from tests.e2e.test_validate_gate import _fk_config

    def _boom(*_a, **_k):
        raise ExecutionError(
            code="out_of_core_fanin_exceeds_budget", message="fan-in exceeds budget (test double)."
        )

    monkeypatch.setattr(engine_exec, "estimate_job_capacity", _boom)
    repo = make_repo(tmp_path / "repo")
    cfg = _fk_config(repo)
    write(repo, MANIFEST_NAME, ci_manifest(pipelines=f"  - id: primary\n    path: {cfg.name}\n"))
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["ci", "check", MANIFEST_NAME, "--format", "json"])
    assert result.exit_code == EXIT_CAPACITY, result.output
    report = json.loads(result.stdout)
    assert report["exit_code"] == EXIT_CAPACITY
    assert report["status"] in {"refused", "partial"}


def test_precommit_context_narrows_validation_and_says_so(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    # Source data is absent: a full validation would fail preflight; config mode must not look.
    (repo / "data" / "in.csv").unlink()
    write(repo, MANIFEST_NAME, ci_manifest(patterns=[PATTERN]))
    proc, report = _run(repo, "--context", "pre-commit")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert {"note_id": "ci.precommit_mode_narrowed"} in report["notes"]
    # machine-readable format on stdout: the human stderr line is suppressed
    assert "pre-commit mode" not in proc.stderr
    md = ci_check(repo, "--format", "markdown", "--context", "pre-commit")
    assert md.returncode == EXIT_OK
    assert "Running in pre-commit mode; validation narrowed from 'full' to 'config'" in md.stderr
    # and the same notes appear in the written report when output goes to a file
    out = ci_check(repo, "--format", "json", "--context", "pre-commit", "--output", "r.json")
    assert "Running in pre-commit mode" in out.stderr
    assert {"note_id": "ci.precommit_mode_narrowed"} in json.loads((repo / "r.json").read_text())[
        "notes"
    ]
    # the normal CI context really does run the full validation and fails on the missing source
    full = ci_check(repo, "--format", "json")
    assert full.returncode == EXIT_USAGE
    assert parse_stdout(full)["notes"] == []
