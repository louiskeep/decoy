"""AT-C1c: the FK shapes through the CLI, handed lazy with `resident_fallback=True`.

Each shape must equal the base resident run (bytes and route). A shape the engine admits to a
bounded route keeps every table lazy: the pre-pass reads nothing and the routes never read a
lazy source whole. A shape it refuses reads the tables whole in the pre-pass, once each.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from decoy_engine.profile import LazySource

from tests.csv_sources import file_source
from tests.e2e.run_stream._support import install_probe, run_both, write_config
from tests.keyed_secret import TEST_MASK_SECRET_REF, secret_env

_N = 300


def _hash(name: str, ns: str) -> dict[str, Any]:
    return {"name": name, "strategy": "hash", "namespace": ns}


def _rel(parent: str, pcols: list[str], child: str, ccols: list[str], ns: str) -> dict[str, Any]:
    return {
        "parent": {"table": parent, "columns": pcols},
        "children": [{"table": child, "columns": ccols}],
        "orphan_policy": "preserve",
        "namespace": ns,
    }


def _shape(
    name: str, *, text_keys: bool
) -> tuple[dict[str, dict[str, list]], list[dict], list[dict]]:
    ids: list = [f"k{i}" for i in range(_N)] if text_keys else list(range(_N))
    if name == "parent_child":
        data = {"a": {"id": ids}, "b": {"id": ids, "a_id": ids}}
        tables = [
            {"name": "a", "columns": [_hash("id", "na")]},
            {"name": "b", "columns": [_hash("id", "nb"), _hash("a_id", "na")]},
        ]
        rels = [_rel("a", ["id"], "b", ["a_id"], "na")]
    elif name == "chain":
        data = {"a": {"id": ids}, "b": {"id": ids, "a_id": ids}, "c": {"id": ids, "b_id": ids}}
        tables = [
            {"name": "a", "columns": [_hash("id", "na")]},
            {"name": "b", "columns": [_hash("id", "nb"), _hash("a_id", "na")]},
            {"name": "c", "columns": [_hash("id", "nc"), _hash("b_id", "nb")]},
        ]
        rels = [_rel("a", ["id"], "b", ["a_id"], "na"), _rel("b", ["id"], "c", ["b_id"], "nb")]
    elif name == "two_children":
        data = {"a": {"id": ids}, "b": {"id": ids, "a_id": ids}, "c": {"id": ids, "a_id": ids}}
        tables = [
            {"name": "a", "columns": [_hash("id", "na")]},
            {"name": "b", "columns": [_hash("id", "nb"), _hash("a_id", "na")]},
            {"name": "c", "columns": [_hash("id", "nc"), _hash("a_id", "na")]},
        ]
        rels = [
            {
                "parent": {"table": "a", "columns": ["id"]},
                "children": [
                    {"table": "b", "columns": ["a_id"]},
                    {"table": "c", "columns": ["a_id"]},
                ],
                "orphan_policy": "preserve",
                "namespace": "na",
            }
        ]
    else:
        data = {"a": {"k1": ids, "k2": ids}, "b": {"id": ids, "k1": ids, "k2": ids}}
        tables = [
            {"name": "a", "columns": [_hash("k1", "n1"), _hash("k2", "n2")]},
            {"name": "b", "columns": [_hash("id", "nb"), _hash("k1", "n1"), _hash("k2", "n2")]},
        ]
        rels = [_rel("a", ["k1", "k2"], "b", ["k1", "k2"], "nk")]
    return data, tables, rels


@pytest.mark.parametrize("text_keys", [True, False], ids=["text-keys", "int-keys"])
@pytest.mark.parametrize("shape", ["parent_child", "chain", "two_children", "composite"])
def test_fk_shape_equals_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, text_keys: bool
) -> None:
    for var, value in secret_env().items():
        monkeypatch.setenv(var, value)
    probe = install_probe(monkeypatch)
    data, tables, rels = _shape(shape, text_keys=text_keys)
    names = list(data)
    src = tmp_path / "data"
    src.mkdir()
    for name, cols in data.items():
        pq.write_table(pa.table(cols), src / f"{name}.parquet")

    def build(out: Path) -> tuple[Path, list[Path]]:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 2, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {n: file_source(src / f"{n}.parquet", "parquet") for n in names},
            "tables": tables,
            "relationships": rels,
            "targets": {
                n: {"type": "file", "format": "csv", "path": str(out / f"{n}.csv")} for n in names
            },
        }
        return write_config(out / "p.yaml", cfg), [out / f"{n}.csv" for n in names]

    lazy, base, seen = run_both(monkeypatch, tmp_path, build, probe=probe)
    assert lazy.exit_code == 0, lazy.output
    assert lazy.exit_code == base.exit_code
    assert lazy.route == base.route
    assert lazy.files == base.files
    assert seen is not None
    handed = {n for n, s in lazy.sources.items() if isinstance(s, LazySource)}
    assert handed == set(names)
    # Whatever the engine kept lazy was never read whole by a route; whatever it read whole,
    # it read in the pre-pass, once per table.
    assert not seen.lazy_materialized
    if text_keys:
        # Text keys: out-of-core admits the job, so every table stays lazy.
        assert lazy.route == "out_of_core"
        assert seen.prepass_reads == []
    else:
        # Integer keys hashed to another dtype are an out-of-core dtype hazard: every table is
        # read whole in the pre-pass, once each.
        assert len(seen.prepass_reads) == len(names)
