"""The evidence manifest records each file target's format (CLI-FMT Part B)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decoy.cli.evidence import build_manifest, compute_manifest_hash, verify_manifest

_LAYOUT = {"columns": [{"name": "a", "start": 0, "width": 3}]}


def _build(tmp_path: Path, targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text("version: 2\n", encoding="utf-8")
    for entry in targets.values():
        if entry.get("path"):
            Path(entry["path"]).write_text("x\n", encoding="utf-8")
    return build_manifest(
        pipeline_path=pipeline,
        config_dict={"targets": targets},
        run_result={},
        cli_version="0",
        engine_version="0",
    )


def test_entries_carry_format_and_only_fixed_width_carries_layout(tmp_path: Path) -> None:
    targets = {
        "a": {"type": "file", "format": "csv", "path": str(tmp_path / "a.csv")},
        "b": {"type": "file", "format": "parquet", "path": str(tmp_path / "b.pq")},
        "c": {
            "type": "file",
            "format": "fixed_width",
            "path": str(tmp_path / "c"),
            "layout": _LAYOUT,
        },
    }
    entries = _build(tmp_path, targets)["output_fingerprints"]
    assert [entries[k]["format"] for k in "abc"] == ["csv", "parquet", "fixed_width"]
    assert "layout" not in entries["a"] and "layout" not in entries["b"]
    assert entries["c"]["layout"] == _LAYOUT
    assert entries["c"]["fingerprint"].startswith("sha256:")


def test_a_missing_output_still_records_its_format(tmp_path: Path) -> None:
    targets = {"a": {"type": "file", "format": "parquet", "path": str(tmp_path / "gone.pq")}}
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text("version: 2\n", encoding="utf-8")
    manifest = build_manifest(
        pipeline_path=pipeline,
        config_dict={"targets": targets},
        run_result={},
        cli_version="0",
        engine_version="0",
    )
    assert manifest["output_fingerprints"]["a"]["format"] == "parquet"
    assert manifest["output_fingerprints"]["a"]["fingerprint"] is None


def test_the_hash_covers_the_new_keys_and_an_old_manifest_still_verifies(tmp_path: Path) -> None:
    targets = {"a": {"type": "file", "format": "csv", "path": str(tmp_path / "a.csv")}}
    manifest = _build(tmp_path, targets)
    assert manifest["schema_version"] == "cli-local-1"
    assert manifest["manifest_hash"] == compute_manifest_hash(manifest)
    tampered = {
        **manifest,
        "output_fingerprints": {"a": {**manifest["output_fingerprints"]["a"], "format": "parquet"}},
    }
    assert compute_manifest_hash(tampered) != manifest["manifest_hash"]
    old = {
        **manifest,
        "output_fingerprints": {
            "a": {k: v for k, v in manifest["output_fingerprints"]["a"].items() if k != "format"}
        },
    }
    old["manifest_hash"] = compute_manifest_hash(old)
    assert verify_manifest(old) == []
