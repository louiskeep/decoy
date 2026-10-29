"""A1 + A2: real CLI, real pinned engine, official OASIS SARIF schema as the oracle."""

from __future__ import annotations

import json
from pathlib import Path

from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from tests.ci_support import (
    CLEAN_PIPELINE,
    MANIFEST_NAME,
    assert_valid_sarif,
    ci_check,
    ci_manifest,
    make_repo,
    parse_stdout,
    write,
    write_clean_pipeline,
)


def _repo(tmp_path: Path, pipeline: str = CLEAN_PIPELINE) -> Path:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo, text=pipeline)
    write(repo, MANIFEST_NAME, ci_manifest())
    return repo


def _sarif(repo: Path, *extra: str):
    proc = ci_check(repo, "--format", "sarif", *extra)
    return proc, parse_stdout(proc)


def test_clean_pipeline_emits_schema_valid_sarif_with_no_results(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc, doc = _sarif(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert_valid_sarif(doc)
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"]) == 1
    assert doc["runs"][0]["results"] == []


def test_clean_sarif_written_to_a_file_is_identical_and_stdout_stays_empty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    via_stdout = ci_check(repo, "--format", "sarif").stdout
    proc = ci_check(repo, "--format", "sarif", "--output", "decoy.sarif")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout == ""
    assert (repo / "decoy.sarif").read_text(encoding="utf-8") == via_stdout


def _bad_provider(extra_top_lines: str = "") -> str:
    return extra_top_lines + CLEAN_PIPELINE.replace("person_email", "not_a_real_provider")


def _only_result(doc: dict) -> dict:
    (run,) = doc["runs"]
    (result,) = run["results"]
    return result


def test_real_engine_finding_maps_to_the_exact_key_and_moves_with_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _bad_provider())
    proc, doc = _sarif(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert_valid_sarif(doc)
    res = _only_result(doc)
    assert res["ruleId"] == "validate.unknown_provider"
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "pipeline.yaml"
    # CLEAN_PIPELINE line 14 is `        provider: ...` (8-space indent)
    assert loc["region"]["startLine"] == 14
    assert loc["region"]["startColumn"] == 9
    assert "snippet" not in json.dumps(doc)
    rule_ids = [r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]]
    assert res["ruleId"] in rule_ids
    first_fp = res["partialFingerprints"]["primary/v1"]

    # Move the offending key two lines down: the region moves, the identity does not.
    write(repo, "pipeline.yaml", _bad_provider("# moved\n# moved\n"))
    proc, doc = _sarif(repo)
    assert proc.returncode == EXIT_USAGE
    res = _only_result(doc)
    region = res["locations"][0]["physicalLocation"]["region"]
    assert (region["startLine"], region["startColumn"]) == (16, 9)
    assert res["partialFingerprints"]["primary/v1"] == first_fp


def test_pipeline_in_a_subdirectory_uses_a_repo_relative_uri(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo, "conf/pipeline.yaml", text=_bad_provider())
    write(repo, "data/in.csv", "email\na@example.invalid\n")
    write(
        repo,
        MANIFEST_NAME,
        ci_manifest(pipelines="  - id: primary\n    path: conf/pipeline.yaml\n"),
    )
    proc, doc = _sarif(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    uri = _only_result(doc)["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "conf/pipeline.yaml"


def test_finding_without_a_provable_logical_path_has_no_location(tmp_path: Path) -> None:
    # A top-level list is a real engine-side `yaml.not_mapping` finding with no path.
    repo = _repo(tmp_path, "- not\n- a\n- mapping\n")
    proc, doc = _sarif(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert_valid_sarif(doc)
    res = _only_result(doc)
    assert "locations" not in res or res["locations"] == []
    assert res["partialFingerprints"]["primary/v1"]
    assert res["ruleId"] in [r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]]


def test_missing_required_key_degrades_to_no_region_not_a_wrong_one(tmp_path: Path) -> None:
    # `version` is required; the leaf is absent and its parent is the document root.
    repo = _repo(tmp_path, CLEAN_PIPELINE.replace("version: 1\n", ""))
    proc, doc = _sarif(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert_valid_sarif(doc)
    for res in doc["runs"][0]["results"]:
        for loc in res.get("locations", []):
            assert "region" not in loc["physicalLocation"]


def test_same_command_json_and_markdown_describe_the_same_report(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _bad_provider())
    js = ci_check(repo, "--format", "json")
    md = ci_check(repo, "--format", "markdown")
    assert js.returncode == md.returncode == EXIT_USAGE
    report = parse_stdout(js)
    assert report["schema_version"] == "decoy-ci-report/v1"
    assert report["status"] == "findings" and report["exit_code"] == EXIT_USAGE
    assert report["findings"][0]["rule_id"] == "validate.unknown_provider"
    assert "validate.unknown_provider" in md.stdout and "pipeline.yaml:14:9" in md.stdout
    assert "```" not in md.stdout
