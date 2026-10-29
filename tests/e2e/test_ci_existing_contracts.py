"""A11: the existing public contracts F43 wraps must not move.

These pins are GREEN on the pre-F43 baseline and must stay green: F43 is a thin
wrapper, so the direct commands it reuses keep their bytes and exit integers.
The seams extracted beneath them (validation gate, scan-diff categorizer,
evidence verifier) are only legitimate if these stay unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, EXIT_WARNINGS
from tests.ci_support import (
    CLEAN_PIPELINE,
    make_evidence,
    make_repo,
    run_decoy,
    write,
    write_clean_pipeline,
)


def _repo(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    return repo


def test_validate_gate_json_shape_is_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = run_decoy(["validate", "pipeline.yaml", "--json"], repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    payload = json.loads(proc.stdout)
    assert list(payload) == ["command", "status", "config", "messages"]
    assert payload == {
        "command": "validate",
        "status": "ok",
        "config": "pipeline.yaml",
        "messages": [],
    }


def test_validate_gate_config_error_keeps_null_location_and_exit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "bad.yaml", CLEAN_PIPELINE.replace("person_email", "not_a_real_provider"))
    proc = run_decoy(["validate", "bad.yaml", "--json"], repo)
    assert proc.returncode == EXIT_USAGE
    (msg,) = json.loads(proc.stdout)["messages"]
    assert list(msg) == ["layer", "severity", "code", "message", "location"]
    assert (msg["layer"], msg["severity"], msg["code"]) == ("config", "error", "unknown_provider")
    # The direct command has never carried a config-layer location; F43 must not
    # change that public byte stream to get its own location.
    assert msg["location"] is None


def test_validate_fail_on_warning_exit_is_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "out/out.csv", "exists\n")
    assert run_decoy(["validate", "pipeline.yaml"], repo).returncode == EXIT_OK
    proc = run_decoy(["validate", "pipeline.yaml", "--fail-on-warning", "--json"], repo)
    assert proc.returncode == EXIT_WARNINGS
    assert json.loads(proc.stdout)["status"] == "warn"


def _scan(fields: list[dict], qi: list[list[str]] | None = None) -> str:
    return json.dumps(
        {"fields": fields, "quasi_identifier_groups": qi or [], "reid_risk_score": 0.1}
    )


def test_scan_diff_strict_keeps_its_direct_command_exit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "old.json", _scan([{"name": "a", "pii_score": 0.1}]))
    write(repo, "new.json", _scan([{"name": "a", "pii_score": 0.9}]))
    proc = run_decoy(["scan", "diff", "old.json", "new.json", "--strict", "--json"], repo)
    # Public direct-command behavior: strict drift is EXIT_USAGE, not EXIT_FINDINGS.
    assert proc.returncode == EXIT_USAGE
    payload = json.loads(proc.stdout)
    assert payload["drift"] is True
    assert payload["summary"]["pii_increased"] == 1
    assert list(payload) == ["command", "status", "old", "new", "summary", "changes", "drift"]
    clean = run_decoy(["scan", "diff", "old.json", "old.json", "--strict", "--json"], repo)
    assert clean.returncode == EXIT_OK
    assert json.loads(clean.stdout)["drift"] is False


def test_report_verify_output_and_exit_are_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    make_evidence(repo)
    ok = run_decoy(["report", "verify", "build/evidence.json", "--json"], repo)
    assert ok.returncode == EXIT_OK
    assert json.loads(ok.stdout) == {
        "command": "report verify",
        "status": "ok",
        "evidence_file": "build/evidence.json",
        "issues": [],
        "issue_count": 0,
    }
    write(repo, "out/out.csv", "tampered\n")
    bad = run_decoy(["report", "verify", "build/evidence.json", "--json"], repo)
    assert bad.returncode == EXIT_FINDINGS
    payload = json.loads(bad.stdout)
    assert payload["status"] == "fingerprint_mismatch"
    (issue,) = payload["issues"]
    # The public issue strings keep their exact prose shape.
    assert issue.startswith(
        "output fingerprint changed: out/out.csv (table 'customers') (recorded sha256:"
    )
    assert issue.endswith("...)")
