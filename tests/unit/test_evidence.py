"""Unit tests for the evidence manifest module (SP-17).

TDD: these tests assert behavior of the evidence manifest helpers --
hash_file, build_manifest, compute_manifest_hash, verify_manifest.
The tests run BEFORE the implementation to confirm they fail first.

Assertions:
E1. hash_file returns a stable SHA-256 hex string for known content.
E2. build_manifest produces a dict with the required schema fields.
E3. compute_manifest_hash is stable (same input -> same output).
E4. verify_manifest returns no issues for a freshly-built manifest
    where all files still exist and are unchanged.
E5. verify_manifest detects a changed pipeline fingerprint (tamper).
E6. verify_manifest detects a changed input fingerprint (tamper).
E7. verify_manifest detects a changed output fingerprint (tamper).
E8. verify_manifest detects a tampered manifest_hash (manifest edited).
E9. verify_manifest detects a missing input file.
E10. The manifest excludes raw row values; no 'rows' or sample data fields.
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
    """hash_file returns a stable hex string for fixed content."""
    p = tmp_path / "sample.txt"
    p.write_bytes(b"hello world")
    h1 = hash_file(p)
    h2 = hash_file(p)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex = 64 chars
    assert all(c in "0123456789abcdef" for c in h1)


def test_hash_file_changes_with_content(tmp_path: Path):
    """Different content -> different hash."""
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
        "strategies",
        "manifest_hash",
    }
    missing = required - manifest.keys()
    assert not missing, f"Manifest missing fields: {missing}"


def test_build_manifest_fingerprints_are_hex(tmp_path: Path):
    """pipeline_fingerprint and file sha256 values are 64-char hex strings."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)

    pf = manifest["pipeline_fingerprint"]
    assert isinstance(pf, str) and len(pf) == 64

    for _table, info in manifest["input_fingerprints"].items():
        assert len(info["sha256"]) == 64
    for _table, info in manifest["output_fingerprints"].items():
        assert len(info["sha256"]) == 64


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


# ---------------------------------------------------------------------------
# E4: verify_manifest - clean pass
# ---------------------------------------------------------------------------


def test_verify_manifest_clean(tmp_path: Path):
    """verify_manifest returns no issues when all files are unchanged."""
    manifest, _, _, _ = _build_test_manifest(tmp_path)
    issues = verify_manifest(manifest)
    assert issues == [], f"Expected no issues; got: {issues}"


# ---------------------------------------------------------------------------
# E5-E8: verify_manifest - tamper detection
# ---------------------------------------------------------------------------


def test_verify_manifest_detects_changed_pipeline(tmp_path: Path):
    """Changed pipeline file -> pipeline fingerprint mismatch -> issue reported."""
    manifest, pipeline_path, _, _ = _build_test_manifest(tmp_path)
    # Mutate the pipeline file
    pipeline_path.write_text("version: 1\n# TAMPERED\n", encoding="utf-8")
    issues = verify_manifest(manifest)
    assert any("pipeline" in i.lower() for i in issues), (
        f"Expected a pipeline fingerprint issue; got: {issues}"
    )


def test_verify_manifest_detects_changed_input(tmp_path: Path):
    """Changed input file -> input fingerprint mismatch -> issue reported."""
    manifest, _, src_path, _ = _build_test_manifest(tmp_path)
    # Mutate the input file
    src_path.write_text("email\ntampered@evil.com\n", encoding="utf-8")
    issues = verify_manifest(manifest)
    assert any("input" in i.lower() for i in issues), (
        f"Expected an input fingerprint issue; got: {issues}"
    )


def test_verify_manifest_detects_changed_output(tmp_path: Path):
    """Changed output file -> output fingerprint mismatch -> issue reported."""
    manifest, _, _, out_path = _build_test_manifest(tmp_path)
    # Mutate the output file
    out_path.write_text("email\naltered@evil.com\n", encoding="utf-8")
    issues = verify_manifest(manifest)
    assert any("output" in i.lower() for i in issues), (
        f"Expected an output fingerprint issue; got: {issues}"
    )


def test_verify_manifest_detects_tampered_manifest_hash(tmp_path: Path):
    """Edited manifest_hash field -> manifest integrity check fails."""
    import copy

    manifest, _, _, _ = _build_test_manifest(tmp_path)
    m2 = copy.deepcopy(manifest)
    m2["manifest_hash"] = "0" * 64  # Forge an incorrect hash
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
