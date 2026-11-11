"""AT-9 (P3): evidence records the files the run used and verifies the same from any folder.

In a project with a `decoy.yaml` marker the manifest records paths relative to the root with
`path_base: "project"`. `report verify` and `decoy ci check` read them through the one reader,
`verify_manifest_issues`, from the typed `--project` or the marker above the manifest file,
never from the working directory or `DECOY_PROJECT`. A manifest without `path_base` keeps the
old working-directory rule, and a malformed one is refused.

The reader also refuses a project-relative path that leaves the project, evidence that is not
where its run wrote it in the project it reads from (`project_manifest`), and any manifest the
writer's schema does not allow (a null required field, a top-level list), without crashing.
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
from decoy.cli import evidence as evidence_module
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
    assert manifest["project_manifest"] == "ev.json"
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
    assert json.loads(evidence.read_text(encoding="utf-8"))["project_manifest"] is None
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


# --- V1-1: a project-relative path never leaves the project -------------------------------


def test_a_source_reached_through_dotdot_is_recorded_absolute(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    root = _project(tmp_path / "proj")
    cfg = _pipeline(root)
    (cfg.parent / "sub").mkdir()
    pd.DataFrame({"email": ["c@example.invalid"]}).to_csv(tmp_path / "outside.csv", index=False)
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw["sources"]["a"]["path"] = "sub/../../../../outside.csv"
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    manifest = _run(cfg, root / "ev.json", monkeypatch, elsewhere)
    source = manifest["input_fingerprints"]["a"]
    assert source["path"] == str((tmp_path / "outside.csv").resolve())
    assert ".." not in Path(source["path"]).parts
    assert _verify(root / "ev.json").exit_code == 0


def _escape(manifest: dict, evidence: Path, path: str, target: Path) -> None:
    """Point the input entry at `path`, fingerprinted from `target`, with a valid hash."""
    target.write_text("outside\n", encoding="utf-8")
    manifest["input_fingerprints"]["a"]["path"] = path
    manifest["input_fingerprints"]["a"]["fingerprint"] = hash_file(target)
    evidence.write_text(json.dumps(_rehash(manifest)), encoding="utf-8")


@pytest.mark.parametrize("path", ["../outside.txt", "pipelines/../../outside.txt"])
def test_a_rehashed_dotdot_path_is_refused(tmp_path: Path, monkeypatch, path: str) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    _escape(manifest, evidence, path, tmp_path / "outside.txt")
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=evidence)
    assert caught.value.kind == "path_outside_project"
    assert "`input_fingerprints.a.path`" in caught.value.message
    assert "outside.txt" not in caught.value.message
    result = _verify(evidence)
    assert result.exit_code == 1
    assert "inside the project" in json.loads(result.output)["error"]


def test_a_path_through_a_symlink_out_of_the_project_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    outside = tmp_path / "outdir"
    outside.mkdir()
    (evidence.parent / "link").symlink_to(outside, target_is_directory=True)
    _escape(manifest, evidence, "link/outside.txt", outside / "outside.txt")
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=evidence)
    assert caught.value.kind == "path_outside_project"


# --- V1-2: evidence binds to the project and place it was written -------------------------


def test_evidence_for_one_project_is_refused_under_another(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    a = _project(tmp_path / "a")
    b = _project(tmp_path / "b")
    _pipeline(b)
    evidence = a / "ev.json"
    _run(_pipeline(a), evidence, monkeypatch, a)
    moved = b / "evidence" / "ev.json"
    moved.parent.mkdir()
    moved.write_bytes(evidence.read_bytes())
    monkeypatch.chdir(elsewhere)
    for args in ((moved,), (moved, "--project", str(b)), (evidence, "--project", str(b))):
        result = _verify(*map(str, args))
        assert result.exit_code == 1, result.output
        assert "where the run wrote it" in json.loads(result.output)["error"]
    manifest = json.loads(moved.read_text(encoding="utf-8"))
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=moved)
    assert caught.value.kind == "project_mismatch"
    assert _verify(str(evidence), "--project", str(a)).exit_code == 0


def test_evidence_moved_inside_its_project_is_refused(tmp_path: Path, monkeypatch) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    moved = evidence.parent / "pipelines" / "ev.json"
    moved.write_bytes(evidence.read_bytes())
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=moved)
    assert caught.value.kind == "project_mismatch"


def test_a_copy_at_the_same_place_in_another_project_reports_its_files(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    """The documented limit: the place matches, so the copy binds to the other project, and
    its fingerprints then report that project's files instead of passing."""
    a = _project(tmp_path / "a")
    b = _project(tmp_path / "b")
    _pipeline(b)
    _run(_pipeline(a), a / "ev.json", monkeypatch, a)
    (b / "ev.json").write_bytes((a / "ev.json").read_bytes())
    monkeypatch.chdir(elsewhere)
    result = _verify(str(b / "ev.json"))
    assert result.exit_code == 4, result.output
    assert json.loads(result.output)["issue_count"] >= 1


def test_evidence_written_outside_its_project_never_binds_by_the_walk(
    tmp_path: Path, monkeypatch, elsewhere: Path
) -> None:
    a = _project(tmp_path / "a")
    b = _project(tmp_path / "b")
    _pipeline(b)
    _run(_pipeline(a), tmp_path / "ev.json", monkeypatch, a)
    placed = b / "ev.json"
    placed.write_bytes((tmp_path / "ev.json").read_bytes())
    monkeypatch.chdir(elsewhere)
    result = _verify(str(placed))
    assert result.exit_code == 1, result.output
    assert "--project" in json.loads(result.output)["error"]


def test_ci_check_refuses_evidence_copied_from_another_project(tmp_path: Path) -> None:
    repo = _ci_repo(tmp_path)
    other = _project(repo / "other")
    _pipeline(other)
    (other / "build").mkdir()
    copied = other / "build" / "copied.json"
    copied.write_bytes((repo / "proj/build/evidence.json").read_bytes())
    evidence = "  evidence:\n    - {id: e, manifest: other/build/copied.json}\n"
    pipelines = "  - id: primary\n    path: proj/pipelines/orders/pipeline.yaml\n"
    text = ci_manifest(validation=False, extra_checks=evidence, pipelines=pipelines)
    write(repo, MANIFEST_NAME, text)
    proc = ci_check(repo, "--format", "json")
    assert proc.returncode == 1, proc.stderr[-2000:]
    (check,) = [c for c in parse_stdout(proc)["checks"] if c["kind"] == "evidence"]
    assert check["reason_code"] == "ci.evidence_unreadable"


# --- V1-3 and DESIGN: one strict schema for the writer and every reader -------------------


@pytest.mark.parametrize(
    "field",
    ["pipeline_path", "pipeline_fingerprint", "manifest_hash", "input_fingerprints"],
)
def test_a_null_required_field_is_refused(tmp_path: Path, monkeypatch, field: str) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    manifest[field] = None
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=evidence)
    assert caught.value.kind == "malformed"
    assert f"`{field}`" in caught.value.message
    evidence.write_text(json.dumps(manifest), encoding="utf-8")
    for command in ("verify", "show"):
        result = runner.invoke(app, ["report", command, str(evidence), "--json"])
        assert result.exit_code == 1, result.output
        assert f"`{field}`" in json.loads(result.output)["error"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda m: m.pop("project_manifest"),
        lambda m: m["input_fingerprints"]["a"].update(path=None),
        lambda m: m["input_fingerprints"]["a"].update(path=""),
        lambda m: m["output_fingerprints"]["a"].pop("fingerprint"),
        lambda m: m["output_fingerprints"]["a"].update(size_bytes="12"),
        lambda m: m.update(key_label=3),
        lambda m: m.update(run_id=5),
        lambda m: m["output_fingerprints"]["a"].update(size_bytes=True),
        lambda m: m["output_fingerprints"]["a"].update(size_bytes=12.0),
        lambda m: m.update(row_counts={"a": True}),
        lambda m: m.update(row_counts={"a": "3"}),
    ],
)
def test_other_shapes_the_writer_never_makes_are_refused(tmp_path: Path, monkeypatch, edit) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    edit(manifest)
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=evidence)
    assert caught.value.kind == "malformed"


@pytest.mark.parametrize("text", ["[]", '["a"]', "3", "null", '{"a": NaN}'])
def test_a_file_that_is_not_a_manifest_object_is_refused_without_a_crash(
    tmp_path: Path, text: str
) -> None:
    evidence = tmp_path / "ev.json"
    evidence.write_text(text, encoding="utf-8")
    with pytest.raises(ManifestError):
        evidence_module.read_manifest(evidence)
    for command in (["verify"], ["show"], ["render", "-o", str(tmp_path / "r.html")]):
        result = runner.invoke(app, ["report", *command, str(evidence), "--json"])
        assert result.exit_code == 1, (command, result.output)
        assert isinstance(result.exception, (SystemExit, type(None))), command
        assert not (tmp_path / "r.html").exists()


@pytest.mark.parametrize("parsed", [[], ["a"], 3, None])
def test_the_verifier_refuses_a_non_object_passed_directly(parsed) -> None:
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(parsed)
    assert caught.value.kind == "malformed"


def test_ci_check_refuses_a_top_level_list(tmp_path: Path) -> None:
    repo = _ci_repo(tmp_path)
    (repo / "proj/build/evidence.json").write_text("[]", encoding="utf-8")
    proc = ci_check(repo, "--format", "json")
    assert proc.returncode == 1, proc.stderr[-2000:]
    (check,) = [c for c in parse_stdout(proc)["checks"] if c["kind"] == "evidence"]
    assert check["reason_code"] == "ci.evidence_unreadable"


def test_the_writer_writes_only_schema_fields_and_checks_its_output(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, _ = _valid(tmp_path, monkeypatch)
    assert set(manifest) <= set(evidence_module._FIELDS)
    for group in ("input_fingerprints", "output_fingerprints"):
        for entry in manifest[group].values():
            assert set(entry) <= set(evidence_module._ENTRY_FIELDS)
    assert evidence_module.check_manifest(copy.deepcopy(manifest)) == manifest


def test_a_nan_inside_a_well_formed_manifest_is_refused_without_a_crash(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    manifest["row_counts"] = {"a": float("nan")}
    evidence.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        evidence_module.read_manifest(evidence)
    assert caught.value.kind == "unreadable"
    result = _verify(evidence)
    assert result.exit_code == 1, result.output
    assert "could not parse" in json.loads(result.output)["error"]


# --- r2: one portable path rule in decoy.cli.io, exact stored primitives ------------------


@pytest.mark.parametrize(
    "path", ["sub\\in.txt", "C:in.txt", "C:/in.txt", "\\\\host\\share\\in.txt"]
)
def test_a_stored_path_with_a_backslash_or_a_windows_anchor_is_refused(
    tmp_path: Path, monkeypatch, path: str
) -> None:
    """A stored path names the same file on every OS, so it uses "/" only and no drive or UNC
    anchor. On POSIX each spelling is a real file here, so only the rule can refuse it."""
    manifest, evidence = _valid(tmp_path, monkeypatch)
    target = evidence.parent.joinpath(*path.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    _escape(manifest, evidence, path, target)
    with pytest.raises(ManifestError) as caught:
        verify_manifest_issues(manifest, manifest_file=evidence)
    assert caught.value.kind == "path_outside_project"
    assert "`input_fingerprints.a.path`" in caught.value.message
    assert "in.txt" not in caught.value.message


_PATH_CORPUS = [
    "in.txt",
    "sub/in.txt",
    "./in.txt",
    "sub/../in.txt",
    "sub\\in.txt",
    "C:in.txt",
    "C:/in.txt",
    "../in.txt",
    "sub/../../in.txt",
    "sub/",
    ".",
    "sub/..",
]


@pytest.mark.parametrize("raw", _PATH_CORPUS)
def test_the_evidence_reader_and_the_layout_share_one_path_rule(tmp_path: Path, raw: str) -> None:
    """Guard for the one validator: the reader accepts exactly what `contained_path` accepts."""
    from decoy.cli.io import contained_path

    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    expected = contained_path(root, raw)
    try:
        got = evidence_module.resolve_manifest_path(raw, root)
    except ManifestError as exc:
        assert exc.kind == "path_outside_project"
        got = None
    assert got == expected


def test_the_evidence_module_parses_no_path_text_itself() -> None:
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    assert "PurePosixPath" not in source
    assert "PureWindowsPath" not in source


@pytest.mark.parametrize(
    "edit",
    [
        lambda m: m["output_fingerprints"]["a"].update(size_bytes=True),
        lambda m: m.update(row_counts={"a": False}),
    ],
)
def test_a_boolean_in_a_number_field_is_refused_by_every_reader(
    tmp_path: Path, monkeypatch, edit
) -> None:
    manifest, evidence = _valid(tmp_path, monkeypatch)
    edit(manifest)
    evidence.write_text(json.dumps(_rehash(manifest)), encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        evidence_module.read_manifest(evidence)
    assert caught.value.kind == "malformed"
    for command in ("verify", "show"):
        result = runner.invoke(app, ["report", command, str(evidence), "--json"])
        assert result.exit_code == 1, result.output
        assert "malformed" in json.loads(result.output)["error"]


def test_a_project_file_whose_name_the_reader_refuses_is_recorded_absolute(
    tmp_path: Path, monkeypatch
) -> None:
    """The writer records relative only what the reader's rule reads back; a POSIX name with a
    backslash is recorded absolute, so the manifest still verifies."""
    if Path("a\\b").name != "a\\b":
        pytest.skip("a backslash separates folders on this OS")
    root = _project(tmp_path / "proj")
    cfg = _pipeline(root)
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    source = Path(raw["sources"]["a"]["path"])
    source = source if source.is_absolute() else cfg.parent / source
    odd = source.with_name("in\\put.csv")
    odd.write_bytes(source.read_bytes())
    raw["sources"]["a"]["path"] = str(odd)
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    manifest = _run(cfg, root / "ev.json", monkeypatch, root)
    assert manifest["input_fingerprints"]["a"]["path"] == str(odd.resolve())
    assert verify_manifest_issues(manifest, manifest_file=root / "ev.json") == []


# --- AT-9 consumer matrix: every consumer from outside the project ----------------------------
# Each row runs with the working directory outside every project and DECOY_PROJECT exported for
# another project, and spies on the one resolver: every stored output must reach it, and each path
# it returns must be an existing file below the manifest's own project root.


@pytest.fixture
def outside(tmp_path: Path, monkeypatch, elsewhere: Path):
    other = _project(tmp_path / "other")
    _pipeline(other)
    returned: list[Path] = []
    real = evidence_module.resolve_manifest_path

    def spy(*args, **kwargs):
        path = real(*args, **kwargs)
        returned.append(path)
        return path

    from decoy.cli import report as report_module

    monkeypatch.setattr(evidence_module, "resolve_manifest_path", spy)
    monkeypatch.setattr(report_module, "resolve_manifest_path", spy, raising=False)

    def enter() -> list[Path]:
        monkeypatch.chdir(elsewhere)
        monkeypatch.setenv("DECOY_PROJECT", str(other))
        returned.clear()
        return returned

    return enter


def _project_run(tmp_path: Path, monkeypatch, name: str) -> tuple[Path, Path, dict]:
    root = _project(tmp_path / name)
    evidence = root / "ev.json"
    manifest = _run(_pipeline(root), evidence, monkeypatch, root)
    return root, evidence, manifest


def _every_output_resolved(returned: list[Path], runs: list[tuple[Path, dict]]) -> None:
    got = {p.resolve() for p in returned}
    roots = [root.resolve() for root, _ in runs]
    for root, manifest in runs:
        for entry in manifest["output_fingerprints"].values():
            placed = (root.resolve() / entry["path"]).resolve()
            assert placed in got, f"output {entry['path']} never reached resolve_manifest_path"
    for path in got:
        assert path.is_file(), path
        assert any(path.is_relative_to(r) for r in roots), path


def test_at9_verify_manifest_issues_from_outside(tmp_path: Path, monkeypatch, outside) -> None:
    root, evidence, manifest = _project_run(tmp_path, monkeypatch, "proj")
    returned = outside()
    assert verify_manifest_issues(manifest, manifest_file=evidence, project=root) == []
    for entry in manifest["output_fingerprints"].values():
        assert hash_file(root / entry["path"]) == entry["fingerprint"]
    _every_output_resolved(returned, [(root, manifest)])


def test_at9_report_show_from_outside(tmp_path: Path, monkeypatch, outside) -> None:
    root, evidence, manifest = _project_run(tmp_path, monkeypatch, "proj")
    returned = outside()
    result = runner.invoke(app, ["report", "show", str(evidence), "--json"])
    assert result.exit_code == 0, result.output
    shown = json.loads(result.output)
    assert shown["manifest"]["output_fingerprints"] == manifest["output_fingerprints"]
    _every_output_resolved(returned, [(root, manifest)])


def test_at9_report_render_from_outside(
    tmp_path: Path, monkeypatch, outside, elsewhere: Path
) -> None:
    root, evidence, manifest = _project_run(tmp_path, monkeypatch, "proj")
    returned = outside()
    report = elsewhere / "report.html"
    result = runner.invoke(app, ["report", "render", str(evidence), "--output", str(report)])
    assert result.exit_code == 0, result.output
    assert report.is_file()
    _every_output_resolved(returned, [(root, manifest)])


def test_at9_report_verify_from_outside(tmp_path: Path, monkeypatch, outside) -> None:
    root, evidence, manifest = _project_run(tmp_path, monkeypatch, "proj")
    returned = outside()
    result = _verify(evidence, "--project", str(root))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["issues"] == []
    _every_output_resolved(returned, [(root, manifest)])


def test_at9_ci_check_from_outside(tmp_path: Path, outside) -> None:
    repo = _ci_repo(tmp_path)
    root = repo / "proj"
    manifest = json.loads((root / "build/evidence.json").read_text(encoding="utf-8"))
    returned = outside()
    result = runner.invoke(app, ["ci", "check", str(repo / MANIFEST_NAME), "--format", "json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    (check,) = [c for c in report["checks"] if c["kind"] == "evidence"]
    assert check["status"] == "ok", check
    assert report["findings"] == []
    _every_output_resolved(returned, [(root, manifest)])


def test_at9_report_diff_require_data_from_outside(tmp_path: Path, monkeypatch, outside) -> None:
    root_a, evidence_a, manifest_a = _project_run(tmp_path, monkeypatch, "proj_a")
    root_b, evidence_b, manifest_b = _project_run(tmp_path, monkeypatch, "proj_b")
    returned = outside()
    result = runner.invoke(
        app,
        ["report", "diff", str(evidence_a), str(evidence_b), "--require-data", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data_level"] == "compared"
    assert payload.get("missing_files", []) == []
    _every_output_resolved(returned, [(root_a, manifest_a), (root_b, manifest_b)])
