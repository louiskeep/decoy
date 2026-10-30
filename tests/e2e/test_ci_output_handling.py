"""`decoy ci check` file I/O: --output safety, defaults, quiet/verbose, non-git roots.

Writing is the CLI's only side effect, so its edges are pinned here: atomic overwrite of an
explicit regular-file target, refusal of symlinks and paths outside the repository, and a
fixed (value-free) stderr.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from tests.ci_support import (
    MANIFEST_NAME,
    assert_valid_sarif,
    ci_check,
    ci_manifest,
    make_repo,
    parse_stdout,
    run_decoy,
    write,
    write_clean_pipeline,
)

PATTERN = {
    "id": "pii.seeded-test-identifier",
    "literal": "DECOY_TEST_IDENTIFIER_",
    "paths": ["fixtures/**"],
}


def _repo(tmp_path: Path, manifest: str | None = None) -> Path:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, manifest or ci_manifest())
    return repo


def test_default_manifest_is_the_literal_dot_decoy_ci_yaml(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = run_decoy(["ci", "check", "--format", "json"], repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert parse_stdout(proc)["status"] == "ok"
    # no search: a differently named manifest in the same directory is not picked up
    (repo / MANIFEST_NAME).rename(repo / "other.yaml")
    missing = run_decoy(["ci", "check", "--format", "json"], repo)
    assert missing.returncode == EXIT_USAGE
    assert parse_stdout(missing)["checks"][0]["reason_code"] == "ci.manifest_unreadable"


def test_explicit_output_overwrites_atomically_and_leaves_no_temp_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "decoy.sarif", "stale contents\n")
    proc = ci_check(repo, "--format", "sarif", "--output", "decoy.sarif")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert_valid_sarif(json.loads((repo / "decoy.sarif").read_text(encoding="utf-8")))
    assert not [p for p in repo.iterdir() if p.name.startswith((".decoy-ci-", ".decoy-debug-"))]


def test_output_to_a_symlink_is_refused_and_the_target_is_untouched(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    victim = write(repo, "victim.txt", "do not touch\n")
    os.symlink(victim, repo / "report.json")
    proc = ci_check(repo, "--format", "json", "--output", "report.json")
    assert proc.returncode == EXIT_USAGE
    assert victim.read_text(encoding="utf-8") == "do not touch\n"
    assert "regular file" in proc.stderr


def test_output_outside_the_repository_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    outside = tmp_path / "outside.json"
    for target in ("../outside.json", str(outside)):
        proc = ci_check(repo, "--format", "json", "--output", target)
        assert proc.returncode == EXIT_USAGE, proc.stderr
        assert "inside the repository" in proc.stderr
    assert not outside.exists()


def test_output_into_a_missing_directory_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = ci_check(repo, "--format", "json", "--output", "nope/report.json")
    assert proc.returncode == EXIT_USAGE
    assert not (repo / "nope").exists()


def test_quiet_silences_stderr_and_verbose_adds_value_free_check_lines(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    quiet = ci_check(repo, "--format", "json", "--output", "r.json", "--quiet")
    assert quiet.returncode == EXIT_OK and quiet.stderr == "" and quiet.stdout == ""
    loud = ci_check(repo, "--format", "json", "--output", "r.json", "--verbose")
    assert "check validation.primary: ok findings=0" in loud.stderr
    assert "status=ok exit=0" in loud.stderr
    both = ci_check(repo, "--format", "json", "--quiet", "--verbose")
    assert both.returncode == EXIT_USAGE  # the shared flag-conflict rule applies


def test_manifest_in_a_subdirectory_resolves_paths_from_its_own_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo, "conf/pipeline.yaml")
    write(repo, "conf/data/in.csv", "email\na@example.invalid\n")
    (repo / "conf" / "out").mkdir()
    write(repo, "conf/ci.yaml", ci_manifest())
    proc = run_decoy(["ci", "check", "conf/ci.yaml", "--format", "json"], repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert parse_stdout(proc)["status"] == "ok"


def test_outside_a_git_work_tree_the_manifest_directory_is_the_root(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    write_clean_pipeline(plain)
    write(plain, MANIFEST_NAME, ci_manifest())
    ok = run_decoy(["ci", "check", MANIFEST_NAME, "--format", "json"], plain)
    assert ok.returncode == EXIT_OK, ok.stderr
    # ...and a staged scan has no index to read there, so it cannot report clean
    write(plain, MANIFEST_NAME, ci_manifest(validation=False, patterns=[PATTERN]))
    staged = run_decoy(["ci", "check", MANIFEST_NAME, "--format", "json"], plain)
    report = parse_stdout(staged)
    assert staged.returncode == EXIT_RUNTIME
    assert (report["status"], report["checks"][0]["reason_code"]) == ("partial", "ci.git_failure")


def test_an_empty_selection_is_refused_not_a_pass(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ci_manifest(validation=False))
    proc = ci_check(repo, "--format", "json")
    assert proc.returncode == EXIT_USAGE
    assert parse_stdout(proc)["status"] == "refused"


def test_precommit_context_marks_artifact_checks_not_applicable(tmp_path: Path) -> None:
    extra = "  evidence:\n    - id: protected-output\n      manifest: build/evidence.json\n"
    repo = _repo(tmp_path, ci_manifest(extra_checks=extra))
    proc = ci_check(repo, "--format", "json", "--context", "pre-commit")
    report = parse_stdout(proc)
    assert proc.returncode == EXIT_OK, proc.stderr
    (ev,) = [c for c in report["checks"] if c["kind"] == "evidence"]
    assert (ev["status"], ev["reason_code"]) == ("noop", "ci.precommit_not_applicable")
    assert {"note_id": "ci.precommit_mode_narrowed"} in report["notes"]


def test_drift_inputs_that_cannot_be_compared_are_refused_not_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    good = {"fields": [{"name": "a", "pii_score": 0.1}], "quasi_identifier_groups": []}
    write(repo, "good.json", json.dumps(good))
    write(repo, "broken.json", "{not json")
    write(repo, "shape.json", json.dumps({"fields": 5}))
    cases = {
        "broken": ("good.json", "broken.json", "ci.drift_unreadable"),
        "shape": ("good.json", "shape.json", "ci.drift_unreadable"),
        "missing": ("good.json", "absent.json", "ci.input_missing"),
    }
    for baseline, current, reason in cases.values():
        extra = f"  drift:\n    - {{id: d, baseline: {baseline}, current: {current}}}\n"
        write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=extra))
        proc = ci_check(repo, "--format", "json")
        report = parse_stdout(proc)
        assert proc.returncode == EXIT_USAGE, proc.stderr
        assert (report["status"], report["checks"][0]["reason_code"]) == ("refused", reason)


def test_evidence_that_is_not_a_manifest_object_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "build/evidence.json", "[1, 2, 3]")
    extra = "  evidence:\n    - {id: e, manifest: build/evidence.json}\n"
    write(repo, MANIFEST_NAME, ci_manifest(validation=False, extra_checks=extra))
    proc = ci_check(repo, "--format", "json")
    assert proc.returncode == EXIT_USAGE
    assert parse_stdout(proc)["checks"][0]["reason_code"] == "ci.evidence_unreadable"


def test_a_pipeline_that_is_not_utf8_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "pipeline.yaml", b"version: 1\nname: caf\xe9\n")
    proc = ci_check(repo, "--format", "json")
    report = parse_stdout(proc)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert [f["rule_id"] for f in report["findings"]] == ["validate.yaml.parse_error"]


def test_precommit_context_also_skips_drift_and_regression_visibly(tmp_path: Path) -> None:
    extra = (
        "  drift:\n    - {id: d, baseline: a.json, current: b.json}\n"
        "  regression_suites:\n    - {id: r, suite: suites/golden}\n"
    )
    repo = _repo(tmp_path, ci_manifest(extra_checks=extra))
    proc = ci_check(repo, "--format", "json", "--context", "pre-commit")
    report = parse_stdout(proc)
    assert proc.returncode == EXIT_OK, proc.stderr
    skipped = {
        c["kind"]: (c["status"], c["reason_code"])
        for c in report["checks"]
        if c["kind"] != "validation"
    }
    assert skipped == {
        "drift": ("noop", "ci.precommit_not_applicable"),
        "regression": ("noop", "ci.precommit_not_applicable"),
    }
