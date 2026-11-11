"""AT-9 (P3): evidence records the files the run used and verifies the same from any folder.

In a project with a `decoy.yaml` marker the manifest records paths relative to the root with
`path_base: "project"`. `report verify` and `decoy ci check` read them through the one reader,
`verify_manifest_issues`, from the typed `--project` or the marker above the manifest file,
never from the working directory or `DECOY_PROJECT`. A manifest without `path_base` keeps the
old working-directory rule, and a malformed one is refused.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.evidence import (
    ManifestError,
    compute_manifest_hash,
    hash_file,
    verify_manifest_issues,
)
from tests.ci_support import (
    MANIFEST_NAME,
    ci_check,
    ci_manifest,
    make_repo,
    parse_stdout,
    run_decoy,
    write,
)

runner = CliRunner()
MARKER = "kind: decoy-project/v1\n"


def _project(root: Path, *, marker: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if marker:
        (root / "decoy.yaml").write_text(MARKER, encoding="utf-8")
    return root


def _pipeline(root: Path) -> Path:
    """`pipelines/orders/pipeline.yaml` with a source beside it, named relative to the YAML."""
    folder = root / "pipelines" / "orders"
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"email": ["a@example.invalid", "b@example.invalid"]}).to_csv(
        folder / "in.csv", index=False
    )
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": {"type": "file", "format": "csv", "has_header": True, "path": "in.csv"}},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "masked.csv"}},
    }
    path = folder / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _run(cfg: Path, evidence: Path, monkeypatch, cwd: Path) -> dict:
    monkeypatch.chdir(cwd)
    result = runner.invoke(app, ["run", str(cfg), "--evidence-out", str(evidence)])
    assert result.exit_code == 0, result.output
    return json.loads(evidence.read_text(encoding="utf-8"))


def _verify(evidence: Path, *args: str):
    return runner.invoke(app, ["report", "verify", str(evidence), "--json", *args])


def _rehash(manifest: dict) -> dict:
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    return manifest


@pytest.fixture
def elsewhere(tmp_path: Path) -> Path:
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    return folder


def test_a_project_run_records_project_relative_paths_of_the_files_it_used(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    cfg = _pipeline(root)
    manifest = _run(cfg, root / "ev.json", monkeypatch, elsewhere)
    real = root.resolve()
    assert manifest["path_base"] == "project"
    assert manifest["pipeline_path"] == "pipelines/orders/pipeline.yaml"
    source = manifest["input_fingerprints"]["a"]
    assert source["path"] == "pipelines/orders/in.csv"
    assert source["fingerprint"] == hash_file(real / source["path"])
    (run,) = [p for p in (real / "out" / "orders").iterdir() if p.is_dir() and p.name[0].isdigit()]
    output = manifest["output_fingerprints"]["a"]
    assert output["path"] == (run / "masked.csv").relative_to(real).as_posix()
    assert output["fingerprint"] is not None
    assert output["fingerprint"] == hash_file(run / "masked.csv")


def test_the_config_fingerprint_is_equal_across_two_runs(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    cfg = _pipeline(root)
    first = _run(cfg, root / "ev1.json", monkeypatch, elsewhere)
    second = _run(cfg, root / "ev2.json", monkeypatch, root)
    assert first["pipeline_fingerprint"] == second["pipeline_fingerprint"]
    assert first["output_fingerprints"]["a"]["path"] != second["output_fingerprints"]["a"]["path"]


def test_report_verify_passes_from_another_folder_by_the_marker_above_the_manifest(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    evidence = root / "ev.json"
    _run(_pipeline(root), evidence, monkeypatch, root)
    monkeypatch.chdir(elsewhere)
    result = _verify(evidence)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["issue_count"] == 0


def test_report_verify_reads_a_manifest_outside_the_project_with_typed_project(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    evidence = tmp_path / "ev.json"
    _run(_pipeline(root), evidence, monkeypatch, root)
    monkeypatch.chdir(elsewhere)
    refused = _verify(evidence)
    assert refused.exit_code == 1
    assert "--project" in json.loads(refused.output)["error"]
    result = _verify(evidence, "--project", str(root))
    assert result.exit_code == 0, result.output


def test_decoy_project_for_another_project_does_not_steer_verification(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    other = _project(tmp_path / "other")
    evidence = root / "ev.json"
    _run(_pipeline(root), evidence, monkeypatch, root)
    _pipeline(other)
    monkeypatch.setenv("DECOY_PROJECT", str(other))
    monkeypatch.chdir(other)
    result = _verify(evidence)
    assert result.exit_code == 0, result.output


def test_a_drifted_output_is_found_from_another_folder(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    evidence = root / "ev.json"
    manifest = _run(_pipeline(root), evidence, monkeypatch, root)
    (root / manifest["output_fingerprints"]["a"]["path"]).write_text("changed\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    result = _verify(evidence)
    assert result.exit_code == 4
    assert json.loads(result.output)["issue_count"] == 1


def test_a_run_with_no_marker_records_absolute_paths_and_no_path_base(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "loose", marker=False)
    evidence = tmp_path / "ev.json"
    manifest = _run(_pipeline(root), evidence, monkeypatch, elsewhere)
    assert "path_base" not in manifest
    paths = [manifest["pipeline_path"], manifest["input_fingerprints"]["a"]["path"]]
    paths.append(manifest["output_fingerprints"]["a"]["path"])
    assert all(Path(p).is_absolute() for p in paths)
    assert manifest["input_fingerprints"]["a"]["fingerprint"] is not None
    result = _verify(evidence)
    assert result.exit_code == 0, result.output


def test_a_manifest_without_path_base_keeps_the_working_directory_rule(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    evidence = root / "ev.json"
    manifest = _run(_pipeline(root), evidence, monkeypatch, root)
    del manifest["path_base"]
    evidence.write_text(json.dumps(_rehash(manifest)), encoding="utf-8")
    monkeypatch.chdir(root)
    assert _verify(evidence).exit_code == 0
    monkeypatch.chdir(elsewhere)
    missed = _verify(evidence)
    assert missed.exit_code == 4
    assert json.loads(missed.output)["issue_count"] == 3


def _valid(tmp_path: Path, monkeypatch) -> tuple[dict, Path]:
    root = _project(tmp_path / "proj")
    evidence = root / "ev.json"
    return _run(_pipeline(root), evidence, monkeypatch, root), evidence


@pytest.mark.parametrize(
    ("edit", "field"),
    [
        (lambda m: m.pop("schema_version"), "schema_version"),
        (lambda m: m.update(schema_version="cli-local-2"), "schema_version"),
        (lambda m: m.update(path_base="cwd"), "path_base"),
        (lambda m: m.update(path_base=None), "path_base"),
        (lambda m: m.update(pipeline_path=7), "pipeline_path"),
        (lambda m: m.update(output_fingerprints=[]), "output_fingerprints"),
        (lambda m: m["output_fingerprints"].update(a="x"), "output_fingerprints.a"),
        (lambda m: m["input_fingerprints"]["a"].update(path=["x"]), "input_fingerprints.a.path"),
        (lambda m: m["output_fingerprints"]["a"].update(fingerprint=1), "output_fingerprints.a"),
    ],
)
def test_a_malformed_manifest_is_refused_naming_the_field(
    tmp_path: Path, monkeypatch, edit, field: str
) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    edit(manifest)
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=evidence)
    assert caught.value.kind == "malformed"
    assert f"`{field}" in caught.value.message
    evidence.write_text(json.dumps(manifest), encoding="utf-8")
    result = _verify(evidence)
    assert result.exit_code == 1
    assert "malformed" in json.loads(result.output)["error"]


def test_extra_manifest_fields_are_tolerated(tmp_path: Path, monkeypatch) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    manifest["added_later"] = {"any": "shape"}
    manifest["output_fingerprints"]["a"]["added_later"] = 1
    evidence.write_text(json.dumps(_rehash(manifest)), encoding="utf-8")
    assert _verify(evidence).exit_code == 0


def test_the_refusal_names_no_recorded_value(tmp_path: Path, monkeypatch) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    canary = "canary-7f3e"
    bad = copy.deepcopy(manifest)
    bad["path_base"] = canary
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(bad, manifest_file=evidence)
    assert canary not in caught.value.message


def _ci_repo(tmp_path: Path) -> Path:
    """A git repo whose project sits in `proj/`, so the repo root is not the project root."""
    repo = make_repo(tmp_path / "repo")
    root = _project(repo / "proj")
    _pipeline(root)
    (root / "build").mkdir()
    proc = run_decoy(
        ["run", "pipelines/orders/pipeline.yaml", "--evidence-out", "build/evidence.json"], root
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    evidence = "  evidence:\n    - {id: e, manifest: proj/build/evidence.json}\n"
    pipelines = "  - id: primary\n    path: proj/pipelines/orders/pipeline.yaml\n"
    text = ci_manifest(validation=False, extra_checks=evidence, pipelines=pipelines)
    write(repo, MANIFEST_NAME, text)
    return repo


def test_ci_check_reads_project_paths_from_the_marker_not_the_repo_root(tmp_path: Path) -> None:
    repo = _ci_repo(tmp_path)
    manifest = json.loads((repo / "proj/build/evidence.json").read_text(encoding="utf-8"))
    assert manifest["path_base"] == "project"
    report = parse_stdout(ci_check(repo, "--format", "json"))
    assert report["findings"] == [], report


def test_ci_check_ignores_decoy_project_for_another_project(tmp_path: Path) -> None:
    repo = _ci_repo(tmp_path)
    other = _project(tmp_path / "other")
    proc = ci_check(repo, "--format", "json", env={"DECOY_PROJECT": str(other)})
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert parse_stdout(proc)["findings"] == []


def test_ci_check_refuses_a_project_manifest_with_no_marker_above_it(tmp_path: Path) -> None:
    repo = _ci_repo(tmp_path)
    (repo / "proj" / "decoy.yaml").unlink()
    proc = ci_check(repo, "--format", "json")
    assert proc.returncode == 1, proc.stderr[-2000:]
    (check,) = [c for c in parse_stdout(proc)["checks"] if c["kind"] == "evidence"]
    assert check["reason_code"] == "ci.evidence_unreadable"
