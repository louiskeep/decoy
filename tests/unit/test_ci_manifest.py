"""A4: strict, typed, versioned decoy-ci/v1 manifest and its generated schema."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from tests.ci_support import ci_manifest, make_repo, write

from decoy.ci.contracts import CI_MANIFEST_VERSION
from decoy.ci.manifest import ManifestError, load_manifest, manifest_json_schema_text

REPO_ROOT = Path(__file__).resolve().parents[2]

BASE = """\
schema_version: decoy-ci/v1
pipelines:
  - id: primary
    path: pipeline.yaml
"""


def _load(tmp_path: Path, text: str, name: str = ".decoy-ci.yaml"):
    repo = tmp_path / "repo"
    if not (repo / ".git").exists():
        make_repo(repo)
    write(repo, name, text)
    return load_manifest(repo / name)


def _reject(tmp_path: Path, text: str, code: str = "ci.manifest_invalid") -> ManifestError:
    with pytest.raises(ManifestError) as err:
        _load(tmp_path, text)
    assert err.value.reason_code == code, err.value.reason_code
    return err.value


def test_version_constant_and_required_literal(tmp_path: Path) -> None:
    assert CI_MANIFEST_VERSION == "decoy-ci/v1"
    loaded = _load(tmp_path, BASE)
    assert loaded.manifest.schema_version == "decoy-ci/v1"
    _reject(tmp_path, BASE.replace("decoy-ci/v1", "decoy-ci/v2"), "ci.manifest_version_unsupported")
    _reject(tmp_path, BASE.replace("schema_version: decoy-ci/v1\n", ""))


def test_omitted_checks_default_to_full_validation_with_warnings_blocking(tmp_path: Path) -> None:
    m = _load(tmp_path, BASE).manifest
    v = m.checks.validation
    assert (v.enabled, v.mode, v.fail_on_warning) == (True, "full", True)
    assert v.pipelines is None  # None means every declared pipeline
    assert m.checks.drift == () and m.checks.evidence == () and m.checks.regression_suites == ()
    assert m.staged_scan.enabled is False


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    _reject(tmp_path, BASE + "  - id: primary\n    path: other.yaml\n")
    drift = (
        "checks:\n  drift:\n"
        "    - {id: d1, baseline: a.json, current: b.json}\n"
        "    - {id: d1, baseline: a.json, current: c.json}\n"
    )
    _reject(tmp_path, BASE + drift)
    # check ids share one namespace across drift / evidence / regression
    cross = (
        "checks:\n  drift:\n    - {id: same, baseline: a.json, current: b.json}\n"
        "  evidence:\n    - {id: same, manifest: e.json}\n"
    )
    _reject(tmp_path, BASE + cross)
    pats = (
        "staged_scan:\n  enabled: true\n  patterns:\n"
        '    - {id: p.one, literal: "ABCDEFGH", paths: ["a/**"]}\n'
        '    - {id: p.one, literal: "IJKLMNOP", paths: ["a/**"]}\n'
    )
    _reject(tmp_path, BASE + pats)


def test_unknown_fields_are_rejected_at_every_level(tmp_path: Path) -> None:
    _reject(tmp_path, BASE + "surprise: 1\n")
    _reject(tmp_path, BASE.replace("path: pipeline.yaml", "path: pipeline.yaml\n    extra: 1"))
    _reject(tmp_path, BASE + "checks:\n  validation:\n    enabled: true\n    nope: 1\n")
    _reject(tmp_path, BASE + "staged_scan:\n  enabled: false\n  bogus: 1\n")


@pytest.mark.parametrize(
    "text",
    [
        # Each document is VALID but for the one feature under test, so the rejection can
        # only come from the YAML-feature guard (not from an unknown field).
        "schema_version: decoy-ci/v1\npipelines:\n  - &p {id: primary, path: pipeline.yaml}\n",  # anchor
        "schema_version: decoy-ci/v1\npipelines:\n  - <<: {id: primary, path: pipeline.yaml}\n",  # merge key
        BASE + "---\nschema_version: decoy-ci/v1\n",  # second document
        "schema_version: !!python/object:os.system {}\npipelines: []\n",  # unsafe tag
        "schema_version: !custom decoy-ci/v1\npipelines:\n  - {id: primary, path: pipeline.yaml}\n",
    ],
)
def test_yaml_features_outside_the_contract_are_rejected(tmp_path: Path, text: str) -> None:
    _reject(tmp_path, text)


def test_the_guard_does_not_over_reject_plain_equivalents(tmp_path: Path) -> None:
    """Positive control: the same documents without the forbidden feature load."""
    plain = "schema_version: decoy-ci/v1\npipelines:\n  - {id: primary, path: pipeline.yaml}\n"
    assert _load(tmp_path, plain).manifest.pipelines[0].id == "primary"
    tagged = plain.replace("schema_version: decoy-ci/v1", "schema_version: !!str decoy-ci/v1")
    assert (
        _load(tmp_path, tagged).manifest.schema_version == "decoy-ci/v1"
    )  # standard str tag is fine


def test_duplicate_yaml_keys_are_rejected(tmp_path: Path) -> None:
    _reject(
        tmp_path, BASE + "checks:\n  validation: {enabled: true}\n  validation: {enabled: false}\n"
    )


def test_json_manifest_is_accepted_and_json_duplicate_keys_are_not(tmp_path: Path) -> None:
    doc = {"schema_version": "decoy-ci/v1", "pipelines": [{"id": "p", "path": "pipeline.yaml"}]}
    assert _load(tmp_path, json.dumps(doc), "ci.json").manifest.pipelines[0].id == "p"
    _reject(
        tmp_path,
        '{"schema_version": "decoy-ci/v1", "schema_version": "decoy-ci/v1", "pipelines": []}',
    )


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "../outside.yaml", "a/../../b.yaml", "a/../b.yaml", "a\\\\b.yaml", ""]
)
def test_unsafe_pipeline_paths_are_rejected(tmp_path: Path, bad: str) -> None:
    text = BASE.replace("pipeline.yaml", json.dumps(bad))
    err = _reject(tmp_path, text, "ci.manifest_path_rejected")
    assert bad not in str(err) or bad == ""


def test_nul_in_path_is_rejected(tmp_path: Path) -> None:
    _reject(
        tmp_path, BASE.replace("pipeline.yaml", '"a\\u0000b.yaml"'), "ci.manifest_path_rejected"
    )


def test_duplicate_resolved_paths_are_rejected(tmp_path: Path) -> None:
    text = BASE + "  - id: again\n    path: ./pipeline.yaml\n"
    _reject(tmp_path, text, "ci.manifest_path_rejected")


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    make_repo(repo)
    outside = tmp_path / "outside.yaml"
    outside.write_text("x: 1\n", encoding="utf-8")
    os.symlink(outside, repo / "escape.yaml")
    write(repo, ".decoy-ci.yaml", BASE.replace("pipeline.yaml", "escape.yaml"))
    with pytest.raises(ManifestError) as err:
        load_manifest(repo / ".decoy-ci.yaml")
    assert err.value.reason_code == "ci.manifest_path_rejected"


def test_existing_directory_is_not_a_regular_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    make_repo(repo)
    (repo / "pipeline.yaml").mkdir()
    write(repo, ".decoy-ci.yaml", BASE)
    with pytest.raises(ManifestError) as err:
        load_manifest(repo / ".decoy-ci.yaml")
    assert err.value.reason_code == "ci.manifest_path_rejected"


def test_oversized_lists_are_rejected(tmp_path: Path) -> None:
    many = "".join(f"  - id: p{i}\n    path: p{i}.yaml\n" for i in range(33))
    _reject(tmp_path, "schema_version: decoy-ci/v1\npipelines:\n" + many)
    ok = "".join(f"  - id: p{i}\n    path: p{i}.yaml\n" for i in range(32))
    assert (
        len(_load(tmp_path, "schema_version: decoy-ci/v1\npipelines:\n" + ok).manifest.pipelines)
        == 32
    )
    _reject(tmp_path, "schema_version: decoy-ci/v1\npipelines: []\n")
    reg = "".join(f"    - {{id: r{i}, suite: s{i}}}\n" for i in range(17))
    _reject(tmp_path, BASE + "checks:\n  regression_suites:\n" + reg)
    drift = "".join(
        f"    - {{id: d{i}, baseline: a.json, current: b{i}.json}}\n" for i in range(33)
    )
    _reject(tmp_path, BASE + "checks:\n  drift:\n" + drift)
    pats = "".join(
        f'    - {{id: p.{i}, literal: "ABCDEFGH{i:02d}", paths: ["a/**"]}}\n' for i in range(33)
    )
    _reject(tmp_path, BASE + "staged_scan:\n  enabled: true\n  patterns:\n" + pats)


@pytest.mark.parametrize(
    "literal",
    ["abc", "x" * 129, "a" + "é" * 64, "line\nbreak", "nul\u0000byte", ""],
)
def test_literal_size_and_content_bounds(tmp_path: Path, literal: str) -> None:
    text = BASE + (
        "staged_scan:\n  enabled: true\n  patterns:\n"
        f'    - {{id: p.one, literal: {json.dumps(literal)}, paths: ["a/**"]}}\n'
    )
    _reject(tmp_path, text)


def test_literal_boundaries_in_bytes_are_accepted(tmp_path: Path) -> None:
    for lit in ("abcd", "x" * 128, "é" * 64):  # 4 bytes, 128 bytes, 128 bytes
        text = BASE + (
            "staged_scan:\n  enabled: true\n  patterns:\n"
            f'    - {{id: p.one, literal: {json.dumps(lit)}, paths: ["a/**"]}}\n'
        )
        assert _load(tmp_path, text).manifest.staged_scan.patterns[0].literal == lit


@pytest.mark.parametrize(
    "glob", ["", "/abs/**", "../x/**", "a/[b]/c", "a/{b,c}", "a\\b", "a/\u0000"]
)
def test_invalid_globs_are_rejected(tmp_path: Path, glob: str) -> None:
    text = BASE + (
        "staged_scan:\n  enabled: true\n  patterns:\n"
        f'    - {{id: p.one, literal: "ABCDEFGH", paths: [{json.dumps(glob)}]}}\n'
    )
    _reject(tmp_path, text)


def test_pattern_requires_at_least_one_path_glob(tmp_path: Path) -> None:
    text = BASE + (
        "staged_scan:\n  enabled: true\n  patterns:\n"
        '    - {id: p.one, literal: "ABCDEFGH", paths: []}\n'
    )
    _reject(tmp_path, text)


def test_enabled_staged_scan_needs_a_pattern(tmp_path: Path) -> None:
    _reject(tmp_path, BASE + "staged_scan:\n  enabled: true\n  patterns: []\n")


@pytest.mark.parametrize(
    "limits",
    [
        "max_files: 201",
        "max_blob_bytes: 1048577",
        "max_total_bytes: 5242881",
        "max_finding_groups: 101",
        "max_git_seconds: 11",
        "max_files: 0",
    ],
)
def test_staged_limits_may_be_lowered_but_never_raised(tmp_path: Path, limits: str) -> None:
    head = (
        BASE
        + 'staged_scan:\n  enabled: true\n  patterns:\n    - {id: p.one, literal: "ABCDEFGH", paths: ["a/**"]}\n'
    )
    _reject(tmp_path, head + "  limits:\n    " + limits + "\n")
    lowered = head + "  limits:\n    max_files: 5\n    max_git_seconds: 2\n"
    got = _load(tmp_path, lowered).manifest.staged_scan.limits
    assert (got.max_files, got.max_git_seconds) == (5, 2)


def test_ids_follow_the_token_grammar(tmp_path: Path) -> None:
    for bad in ("Primary", "1abc", "has space", "a" * 65, "UPPER.case", "x/y"):
        _reject(tmp_path, BASE.replace("id: primary", f"id: {json.dumps(bad)}"))


def test_non_empty_regression_selection_parses_and_is_kept(tmp_path: Path) -> None:
    m = _load(
        tmp_path, BASE + "checks:\n  regression_suites:\n    - {id: r1, suite: suites/golden}\n"
    ).manifest
    assert [(r.id, r.suite) for r in m.checks.regression_suites] == [("r1", "suites/golden")]


def test_validation_pipelines_must_reference_declared_ids(tmp_path: Path) -> None:
    _reject(tmp_path, BASE + "checks:\n  validation:\n    pipelines: [ghost]\n")


def test_manifest_errors_never_echo_input(tmp_path: Path) -> None:
    canary = "MANIFEST_VALUE_CANARY_8e41c7"
    err = _reject(tmp_path, BASE + f"surprise_{canary}: {canary}\n")
    assert canary not in str(err) and canary not in repr(err)


def test_generated_schema_matches_the_committed_schema_byte_for_byte() -> None:
    committed = (REPO_ROOT / "docs" / "schemas" / "decoy-ci-v1.schema.json").read_text(
        encoding="utf-8"
    )
    assert committed == manifest_json_schema_text()


def test_generated_schema_forbids_additional_properties_everywhere() -> None:
    schema = json.loads(manifest_json_schema_text())
    assert schema["$id"].endswith("decoy-ci-v1.schema.json")

    def walk(node, path="#"):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, path
            for k, v in node.items():
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}/{i}")

    walk(schema)


def test_canonical_example_loads_and_matches_the_plan_shape() -> None:
    loaded = load_manifest(REPO_ROOT / "examples" / "decoy-ci.yaml", root=REPO_ROOT)
    m = loaded.manifest
    assert [p.id for p in m.pipelines] == ["primary"]
    assert m.checks.validation.mode == "full" and m.checks.validation.fail_on_warning is True
    assert [d.id for d in m.checks.drift] == ["discovery-baseline"]
    assert [e.id for e in m.checks.evidence] == ["protected-output"]
    assert m.checks.regression_suites == ()
    assert m.staged_scan.enabled and m.staged_scan.patterns[0].id == "pii.seeded-test-identifier"


def test_helper_manifest_text_is_valid(tmp_path: Path) -> None:
    assert _load(tmp_path, ci_manifest(patterns=[{"id": "p.one", "literal": "ABCDEFGH"}])).manifest
