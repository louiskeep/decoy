"""The CI wrappers consume the SAME results as the direct commands (no second validator).

Parity on real fixtures, plus one call-count seam: a full CI validation runs the engine's
config-only checks exactly once, like `decoy validate`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from decoy.cli.exit_codes import EXIT_FINDINGS
from tests.ci_support import (
    CLEAN_PIPELINE,
    MANIFEST_NAME,
    ci_check,
    ci_manifest,
    make_evidence,
    make_repo,
    parse_stdout,
    run_decoy,
    write,
    write_clean_pipeline,
)

# `decoy ci` emits the fixed family token for a preflight check named after a table
# (`target.<table>.would_overwrite` -> `target.would_overwrite`): the table name is user data.
_TABLE_SEGMENT = re.compile(r"^(source|target)\..+\.([a-z_]+)$")


def _direct_codes(repo: Path, pipeline: str) -> set[str]:
    proc = run_decoy(["validate", pipeline, "--json"], repo)
    return {_TABLE_SEGMENT.sub(r"\1.\2", m["code"]) for m in json.loads(proc.stdout)["messages"]}


@pytest.mark.parametrize(
    "variant",
    [
        "clean",
        "unknown_provider",
        "missing_source",
        "overwrite_warning",
        "not_mapping",
        "no_version",
    ],
)
def test_validation_rule_ids_equal_the_direct_commands_codes(tmp_path: Path, variant: str) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    text = {
        "clean": CLEAN_PIPELINE,
        "unknown_provider": CLEAN_PIPELINE.replace("person_email", "not_a_real_provider"),
        "missing_source": CLEAN_PIPELINE,
        "overwrite_warning": CLEAN_PIPELINE,
        "not_mapping": "- a\n- b\n",
        "no_version": CLEAN_PIPELINE.replace("version: 1\n", ""),
    }[variant]
    write(repo, "pipeline.yaml", text)
    if variant == "missing_source":
        (repo / "data" / "in.csv").unlink()
    if variant == "overwrite_warning":
        write(repo, "out/out.csv", "exists\n")
    write(repo, MANIFEST_NAME, ci_manifest())
    report = parse_stdout(ci_check(repo, "--format", "json"))
    got = {f["rule_id"].removeprefix("validate.") for f in report["findings"]}
    assert got == _direct_codes(repo, "pipeline.yaml")


def test_config_mode_equals_validate_config_layer(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo, text=CLEAN_PIPELINE.replace("person_email", "not_a_real_provider"))
    write(repo, MANIFEST_NAME, ci_manifest().replace("mode: full", "mode: config"))
    report = parse_stdout(ci_check(repo, "--format", "json"))
    direct = run_decoy(["validate", "config", "pipeline.yaml", "--json"], repo)
    direct_codes = {m["code"] for m in json.loads(direct.stdout)["messages"]}
    assert {f["rule_id"].removeprefix("validate.") for f in report["findings"]} == direct_codes


def test_full_ci_validation_runs_config_only_checks_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy_engine

    from decoy.__main__ import app

    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest())
    real = decoy_engine.run_config_only_checks
    calls = {"n": 0}

    def _spy(raw: Any) -> Any:
        calls["n"] += 1
        return real(raw)

    monkeypatch.setattr(decoy_engine, "run_config_only_checks", _spy)
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["ci", "check", MANIFEST_NAME, "--format", "json"])
    assert result.exit_code == 0, result.output
    assert calls["n"] == 1


def test_drift_counts_equal_scan_diff_summary(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    old = {
        "fields": [{"name": "a", "pii_score": 0.1}, {"name": "b", "pii_score": 0.2}],
        "quasi_identifier_groups": [],
        "reid_risk_score": 0.1,
    }
    new = {
        "fields": [
            {"name": "a", "pii_score": 0.9},
            {"name": "b", "pii_score": 0.5},
            {"name": "c", "pii_score": 0.95},
        ],
        "quasi_identifier_groups": [["a", "b"]],
        "reid_risk_score": 0.4,
    }
    write(repo, "old.json", json.dumps(old))
    write(repo, "new.json", json.dumps(new))
    direct = json.loads(run_decoy(["scan", "diff", "old.json", "new.json", "--json"], repo).stdout)
    drift = "  drift:\n    - {id: d, baseline: old.json, current: new.json}\n"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=drift))
    proc = ci_check(repo, "--format", "json")
    assert proc.returncode == EXIT_FINDINGS
    by_rule = {f["rule_id"]: f["occurrences"] for f in parse_stdout(proc)["findings"]}
    assert by_rule == {
        "drift.pii_bucket_increased": direct["summary"]["pii_increased"],
        "drift.new_high_pii_field": 1,
        "drift.new_quasi_identifier_group": direct["summary"]["qi_groups_added"],
    }


def test_evidence_findings_equal_report_verify_issue_count(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    make_evidence(repo)
    write(repo, "out/out.csv", "changed\n")
    write(repo, "data/in.csv", "changed input\n")
    direct = json.loads(
        run_decoy(["report", "verify", "build/evidence.json", "--json"], repo).stdout
    )
    ev = "  evidence:\n    - {id: e, manifest: build/evidence.json}\n"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=ev))
    report = parse_stdout(ci_check(repo, "--format", "json"))
    assert len(report["findings"]) == direct["issue_count"] == 2
    assert {f["rule_id"] for f in report["findings"]} == {
        "evidence.input_fingerprint_changed",
        "evidence.output_fingerprint_changed",
    }


def test_a_fifo_named_by_an_untrusted_evidence_manifest_cannot_hang_the_check(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    make_evidence(repo)
    fifo = repo / "trap.fifo"
    os.mkfifo(fifo)
    ev = json.loads((repo / "build" / "evidence.json").read_text(encoding="utf-8"))
    ev["output_fingerprints"]["customers"]["path"] = "trap.fifo"
    (repo / "build" / "evidence.json").write_text(json.dumps(ev), encoding="utf-8")
    evidence = "  evidence:\n    - {id: e, manifest: build/evidence.json}\n"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=evidence))
    proc = ci_check(repo, "--format", "json")  # would block forever if the FIFO were opened
    assert proc.returncode == EXIT_FINDINGS
