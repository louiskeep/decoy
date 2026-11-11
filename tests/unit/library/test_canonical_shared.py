"""A1-canonical-shared: the evidence manifest hash and record ids use one canonical JSON form.

`evidence.compute_manifest_hash` calls `decoy_engine.records.canonical_bytes`. The hashes below
were recorded from the CLI's own `json.dumps` form before the rewire, so a manifest written by an
earlier CLI still verifies byte for byte.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from decoy_engine import records
from tests.csv_sources import csv_source

from decoy.cli import evidence

_PLAIN = {
    "schema_version": "cli-local-1",
    "producer": "decoy-cli",
    "pipeline_fingerprint": "sha256:" + "a" * 64,
    "input_fingerprints": {
        "orders": {"path": "data/orders.csv", "fingerprint": "sha256:" + "b" * 64}
    },
    "output_fingerprints": {},
    "warnings": [],
    "manifest_hash": "x",
}
_AWKWARD = {
    "schema_version": "cli-local-1",
    "producer": "decoy-cli",
    "tables": ["cafés", "注文", "emoji\U0001f600"],
    "n": [1, 2.5, -0.0, 1e300, True, False, None],
    "nested": {"z": {"b": 1, "a": [{"y": 2, "x": '\u2028\x00"\\'}]}},
    "signature": "sig",
}
# Recorded with the pre-rewire `json.dumps(sort_keys, compact, allow_nan=False,
# ensure_ascii=False)` form at CLI main 1d53eda.
PINNED = (
    (_PLAIN, "sha256:e4b9d2b814febce5b8f0ab80108998d7d620cb102e12bd5d7d26020fc89e8a0f"),
    (_AWKWARD, "sha256:1e5b011da579842897df06e126e25054bad76a38fedca69c7dcef68e53cf58f4"),
)


def _legacy_bytes(body: dict[str, Any]) -> bytes:
    """The form `compute_manifest_hash` used before the rewire (the reference, test-side only)."""
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False
    ).encode("utf-8")


def _built_manifest(tmp_path: Path) -> dict[str, Any]:
    src = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    src.write_text("email\nfoo@bar.com\n", encoding="utf-8")
    out.write_text("email\nA@B.com\n", encoding="utf-8")
    config = {
        "version": 2,
        "sources": {"customers": csv_source(src)},
        "tables": [{"name": "customers", "columns": []}],
        "targets": {"customers": {"type": "file", "format": "csv", "path": str(out)}},
    }
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(yaml.dump(config), encoding="utf-8")
    return evidence.build_manifest(
        pipeline_path=pipeline,
        config_dict=config,
        run_result={"row_counts": {"customers": 1}},
        cli_version="0.1.0",
        engine_version="0.22.0",
    )


@pytest.fixture
def engine_calls(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    real = records.canonical_bytes

    def spy(value: object) -> bytes:
        calls.append(value)
        return real(value)

    monkeypatch.setattr(records, "canonical_bytes", spy)
    return calls


@pytest.mark.parametrize(("manifest", "expected"), PINNED, ids=["plain", "non-ascii-and-numbers"])
def test_the_manifest_hash_is_unchanged_and_comes_from_the_engine_form(
    manifest: dict[str, Any], expected: str, engine_calls: list[object]
) -> None:
    assert evidence.compute_manifest_hash(manifest) == expected
    assert len(engine_calls) == 1  # the hash went through the one canonical form


def test_engine_and_legacy_bytes_agree_over_the_manifest_corpus(tmp_path: Path) -> None:
    built = _built_manifest(tmp_path)
    corpus = [m for m, _ in PINNED] + [built]
    assert len(corpus) == 3 and built["manifest_hash"].startswith("sha256:")
    strip = evidence._MANIFEST_HASH_STRIP_FIELDS
    for manifest in corpus:
        body = {k: v for k, v in manifest.items() if k not in strip}
        assert records.canonical_bytes(body) == _legacy_bytes(body)
        expected = f"sha256:{hashlib.sha256(_legacy_bytes(body)).hexdigest()}"
        assert evidence.compute_manifest_hash(manifest) == expected
    assert evidence.verify_manifest(built) == []


def test_nan_is_still_refused() -> None:
    with pytest.raises(ValueError):
        evidence.compute_manifest_hash({"x": float("nan")})
