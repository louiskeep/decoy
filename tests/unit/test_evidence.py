"""Unit tests for the evidence manifest module (SP-17).

TDD: these tests assert behavior of the evidence manifest helpers --
hash_file, build_manifest, compute_manifest_hash, verify_manifest.

Assertions:
E1. hash_file returns a stable sha256:<hex> fingerprint for known content.
E2. build_manifest produces a dict with the required schema fields.
E3. compute_manifest_hash is stable (same input -> same output).
E4. verify_manifest returns no issues for a freshly-built manifest
    where all files still exist and are unchanged.
E5. verify_manifest detects a changed pipeline fingerprint (drift).
E6. verify_manifest detects a changed input fingerprint (drift).
E7. verify_manifest detects a changed output fingerprint (drift).
E8. verify_manifest detects a tampered manifest_hash (manifest edited).
E9. verify_manifest detects a missing input file.
E10. The manifest excludes raw row values; no 'rows' or sample data fields.
E11. A run that produces engine warnings yields a non-empty warnings array.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

from decoy.cli.evidence import build_manifest, compute_manifest_hash, hash_file, verify_manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _make_config_dict(src_path: Path, out_path: Path) -> dict:
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src_path)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "customer_ns",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(out_path)},
        },
    }


def _make_run_result(out_path: Path) -> dict:
    """Minimal run result dict (row counts per table)."""
    return {"row_counts": {"customers": 2}}


def _build_test_manifest(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    """Return (manifest, pipeline_path, src_path, out_path) all files written."""
    src_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.csv"
    pipeline_path = tmp_path / "pipeline.yaml"

    _write_file(src_path, "email\nfoo@bar.com\nbaz@qux.com\n")
    _write_file(out_path, "email\nA@B.com\nC@D.com\n")

    import yaml

    config_dict = _make_config_dict(src_path, out_path)
    _write_file(pipeline_path, yaml.dump(config_dict))

    run_result = _make_run_result(out_path)
    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result=run_result,
        cli_version="0.1.0",
        engine_version="0.3.1",
    )
    return manifest, pipeline_path, src_path, out_path


# ---------------------------------------------------------------------------
# E1: hash_file
# ---------------------------------------------------------------------------


def test_hash_file_stable(tmp_path: Path):
    """hash_file returns a stable sha256:<hex> fingerprint for fixed content."""
    p = tmp_path / "sample.txt"
    p.write_bytes(b"hello world")
    h1 = hash_file(p)
    h2 = hash_file(p)
    assert h1 == h2
    assert h1.startswith("sha256:")
    # "sha256:" prefix (7 chars) + 64 hex chars = 71 total
    assert len(h1) == 71
    hex_part = h1[len("sha256:") :]
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_hash_file_changes_with_content(tmp_path: Path):
    """Different content -> different fingerprint."""
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_bytes(b"hello")
    p2.write_bytes(b"world")
    assert hash_file(p1) != hash_file(p2)


# ---------------------------------------------------------------------------
# E2: build_manifest structure
# ---------------------------------------------------------------------------


def test_build_manifest_required_fields(tmp_path: Path):
    """build_manifest produces a dict with all required schema fields."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)

    required = {
        "schema_version",
        "producer",
        "run_id",
        "run_timestamp",
        "cli_version",
        "engine_version",
        "pipeline_path",
        "pipeline_fingerprint",
        "input_fingerprints",
        "output_fingerprints",
        "row_counts",
        "key_label",
        "warnings",
        "timings",
        "strategies",
        "manifest_hash",
    }
    missing = required - manifest.keys()
    assert not missing, f"Manifest missing fields: {missing}"


def test_build_manifest_producer_and_schema_version(tmp_path: Path):
    """producer is 'decoy-cli'; schema_version is namespaced 'cli-local-1'."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    assert manifest["producer"] == "decoy-cli"
    assert manifest["schema_version"] == "cli-local-1"


def test_build_manifest_fingerprints_are_sha256_prefixed(tmp_path: Path):
    """pipeline_fingerprint and file fingerprint values use sha256:<hex> form."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)

    pf = manifest["pipeline_fingerprint"]
    assert isinstance(pf, str)
    assert pf.startswith("sha256:")
    assert len(pf) == 71  # "sha256:" + 64 hex chars

    for _table, info in manifest["input_fingerprints"].items():
        fp = info["fingerprint"]
        assert fp.startswith("sha256:"), f"Expected sha256: prefix; got {fp!r}"
        assert len(fp) == 71
        assert info["fingerprint_method"] == "full"

    for _table, info in manifest["output_fingerprints"].items():
        fp = info["fingerprint"]
        assert fp.startswith("sha256:"), f"Expected sha256: prefix; got {fp!r}"
        assert len(fp) == 71
        assert info["fingerprint_method"] == "full"


def test_build_manifest_versions(tmp_path: Path):
    """cli_version and engine_version are echoed into the manifest."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    assert manifest["cli_version"] == "0.1.0"
    assert manifest["engine_version"] == "0.3.1"


def test_build_manifest_no_raw_values(tmp_path: Path):
    """Manifest must not contain raw row values or sample data."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    manifest_str = _json.dumps(manifest)
    # Raw source values should never appear
    assert "foo@bar.com" not in manifest_str
    assert "baz@qux.com" not in manifest_str
    # Masked values should never appear
    assert "A@B.com" not in manifest_str
    # Excluded keys
    assert '"rows"' not in manifest_str
    assert '"samples"' not in manifest_str
    assert '"raw_values"' not in manifest_str


# ---------------------------------------------------------------------------
# E3: manifest hash stability
# ---------------------------------------------------------------------------


def test_compute_manifest_hash_stable(tmp_path: Path):
    """Same manifest dict -> same hash (deterministic)."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    h1 = compute_manifest_hash(manifest)
    h2 = compute_manifest_hash(manifest)
    assert h1 == h2


def test_compute_manifest_hash_differs_on_change(tmp_path: Path):
    """Changing any field produces a different hash."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    import copy

    m2 = copy.deepcopy(manifest)
    m2["run_id"] = "changed"
    assert compute_manifest_hash(manifest) != compute_manifest_hash(m2)


def test_compute_manifest_hash_strips_reserved_fields(tmp_path: Path):
    """Adding signature fields does not change the manifest_hash value."""
    import copy

    manifest, _, _, _ = _build_test_manifest(tmp_path)
    m2 = copy.deepcopy(manifest)
    # Add the reserved signature fields that R4 signing will use
    m2["signature"] = "future-sig"
    m2["signature_alg"] = "ed25519"
    m2["signature_key_id"] = "key-v1"
    # Hash should be identical since these fields are stripped
    assert compute_manifest_hash(manifest) == compute_manifest_hash(m2)


# ---------------------------------------------------------------------------
# E4: verify_manifest - clean pass
# ---------------------------------------------------------------------------


def test_verify_manifest_clean(tmp_path: Path):
    """verify_manifest returns no issues when all files are unchanged."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    issues = verify_manifest(manifest)
    assert issues == [], f"Expected no issues; got: {issues}"


# ---------------------------------------------------------------------------
# E5-E8: verify_manifest - drift detection
# ---------------------------------------------------------------------------


def test_verify_manifest_detects_changed_pipeline(tmp_path: Path):
    """Changed pipeline file -> pipeline fingerprint mismatch -> issue reported."""
    manifest, pipeline_path, _, _ = _build_test_manifest(tmp_path)
    # Mutate the pipeline file
    pipeline_path.write_text("version: 1\n# CHANGED\n", encoding="utf-8")
    issues = verify_manifest(manifest)
    assert any("pipeline" in i.lower() for i in issues), (
        f"Expected a pipeline fingerprint issue; got: {issues}"
    )


def test_verify_manifest_detects_changed_input(tmp_path: Path):
    """Changed input file -> input fingerprint mismatch -> issue reported."""
    manifest, _, src_path, _ = _build_test_manifest(tmp_path)
    # Mutate the input file
    src_path.write_text("email\nmodified@example.com\n", encoding="utf-8")
    issues = verify_manifest(manifest)
    assert any("input" in i.lower() for i in issues), (
        f"Expected an input fingerprint issue; got: {issues}"
    )


def test_verify_manifest_detects_changed_output(tmp_path: Path):
    """Changed output file -> output fingerprint mismatch -> issue reported."""
    manifest, _, _, out_path = _build_test_manifest(tmp_path)
    # Mutate the output file
    out_path.write_text("email\naltered@example.com\n", encoding="utf-8")
    issues = verify_manifest(manifest)
    assert any("output" in i.lower() for i in issues), (
        f"Expected an output fingerprint issue; got: {issues}"
    )


def test_verify_manifest_detects_tampered_manifest_hash(tmp_path: Path):
    """Edited manifest_hash field -> manifest integrity check fails."""
    import copy

    manifest, _, _, _ = _build_test_manifest(tmp_path)
    m2 = copy.deepcopy(manifest)
    m2["manifest_hash"] = "0" * 64  # Forge an incorrect value (wrong format + wrong hash)
    issues = verify_manifest(m2)
    assert any("manifest" in i.lower() for i in issues), (
        f"Expected a manifest integrity issue; got: {issues}"
    )


# ---------------------------------------------------------------------------
# E9: missing file
# ---------------------------------------------------------------------------


def test_verify_manifest_detects_missing_input(tmp_path: Path):
    """If an input file has been deleted, verify reports it."""
    manifest, _, src_path, _ = _build_test_manifest(tmp_path)
    src_path.unlink()
    issues = verify_manifest(manifest)
    assert any("input" in i.lower() or "missing" in i.lower() for i in issues), (
        f"Expected a missing-file issue; got: {issues}"
    )


# ---------------------------------------------------------------------------
# E11: non-empty warnings (M1)
# ---------------------------------------------------------------------------


def test_build_manifest_warnings_populated(tmp_path: Path):
    """A run that produces engine warnings yields a non-empty warnings array."""
    from dataclasses import dataclass
    from dataclasses import field as dc_field

    @dataclass(frozen=True)
    class _FakeQualityWarning:
        """Minimal stand-in for decoy_engine.generation.pool._events.QualityWarning."""

        code: str
        provider: str
        column: str | None = None
        detail: dict = dc_field(default_factory=dict)

    src_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.csv"
    pipeline_path = tmp_path / "pipeline.yaml"

    _write_file(src_path, "email\nfoo@bar.com\n")
    _write_file(out_path, "email\nA@B.com\n")

    import yaml

    config_dict = _make_config_dict(src_path, out_path)
    _write_file(pipeline_path, yaml.dump(config_dict))

    warning = _FakeQualityWarning(
        code="low_distinct_ratio",
        provider="faker.name",
        column="email",
        detail={"ratio": 0.3},
    )
    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": 1}},
        cli_version="0.1.0",
        engine_version="0.3.1",
        engine_warnings=(warning,),
    )
    assert len(manifest["warnings"]) > 0, (
        "warnings should be non-empty when engine_warnings are present"
    )
    assert manifest["warnings"][0]["code"] == "low_distinct_ratio"
    assert manifest["warnings"][0]["provider"] == "faker.name"
    assert manifest["warnings"][0]["column"] == "email"


def test_build_manifest_timings_populated(tmp_path: Path):
    """build_manifest serializes timing records into the timings array."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _FakeTiming:
        strategy_type: str
        column: str
        elapsed_ms: float
        peak_memory_delta_kb: int

    src_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.csv"
    pipeline_path = tmp_path / "pipeline.yaml"

    _write_file(src_path, "email\nfoo@bar.com\n")
    _write_file(out_path, "email\nA@B.com\n")

    import yaml

    config_dict = _make_config_dict(src_path, out_path)
    _write_file(pipeline_path, yaml.dump(config_dict))

    timing = _FakeTiming(
        strategy_type="faker", column="email", elapsed_ms=12.5, peak_memory_delta_kb=4
    )
    manifest = build_manifest(
        pipeline_path=pipeline_path,
        config_dict=config_dict,
        run_result={"row_counts": {"customers": 1}},
        cli_version="0.1.0",
        engine_version="0.3.1",
        timings=(timing,),
    )
    assert len(manifest["timings"]) == 1
    t = manifest["timings"][0]
    assert t["strategy_type"] == "faker"
    assert t["column"] == "email"
    assert t["elapsed_ms"] == 12.5
