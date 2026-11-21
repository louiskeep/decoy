"""OUTPUT-METADATA-LEAK C1: source metadata never reaches a CLI target file.

A canary sits in every carrier a Parquet source can hold (schema key, `attrs`, field metadata,
column-index name, range-index name, creator, pandas version). Every CLI write path must leave
none of them in the file it publishes: `decoy run`, `decoy run --chunked`, the out-of-core FK
route (forced, and checked from the run's own result), and `decoy unmask` (an Arrow table write).
A DataFrame write is covered by a direct `write_table` cell. A CSV target is a guard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.e2e.cli_fmt import _metadata_canary as mc
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_ROWS = 40


def _hash(name: str, namespace: str) -> dict[str, Any]:
    return {"name": name, "strategy": "hash", "namespace": namespace}


_PEOPLE_COLUMNS = [
    _hash("id", "id_ns"),
    {"name": "note", "strategy": "redact"},
    {"name": "age", "strategy": "passthrough"},
    {"name": "nest", "strategy": "passthrough"},
]


def _canary_source(path: Path, columns: dict[str, pa.Array]) -> str:
    table = mc.canary_table(columns, extension_column="note")
    return mc.write_canary_parquet(path, table)


_NESTED_CHILD = pa.field("c", pa.string(), metadata={b"k": mc.NESTED.encode()})


def _flat_columns(*, nested: bool = True) -> dict[str, pa.Array]:
    columns = {
        "id": pa.array([f"id{i}" for i in range(_ROWS)]),
        "note": pa.array([f"note {i}" for i in range(_ROWS)]),
        "age": pa.array(range(_ROWS), type=pa.int64()),
    }
    if nested:
        rows = [{"c": f"v{i}"} for i in range(_ROWS)]
        columns["nest"] = pa.array(rows, pa.struct([_NESTED_CHILD]))
    return columns


def _config(tmp_path: Path, *, target_format: str = "parquet", nested: bool = True) -> Path:
    """`nested=False` for `--chunked`: its lane fails on a struct column (known bug, 1.0 row CHUNKED-STRUCT)."""
    src = _canary_source(tmp_path / "people.parquet", _flat_columns(nested=nested))
    columns = _PEOPLE_COLUMNS if nested else _PEOPLE_COLUMNS[:-1]
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": {"type": "file", "format": "parquet", "path": src}},
        "tables": [{"name": "people", "columns": columns}],
        "targets": {
            "people": {
                "type": "file",
                "format": target_format,
                "path": str(tmp_path / f"out.{target_format}"),
            }
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _fk_config(tmp_path: Path) -> Path:
    parent = mc.canary_table(
        {
            "id": pa.array([f"p{i}" for i in range(_ROWS)]),
            "note": pa.array([f"note {i}" for i in range(_ROWS)]),
            "extra": pa.array([f"extra {i}" for i in range(_ROWS)]),
        }
    )
    child = mc.canary_table(
        {
            "cid": pa.array([f"c{i}" for i in range(_ROWS)]),
            "parent_id": pa.array([f"p{i % _ROWS}" for i in range(_ROWS)]),
        }
    )
    srcs = {
        "parent": mc.write_canary_parquet(tmp_path / "parent.parquet", parent),
        "child": mc.write_canary_parquet(tmp_path / "child.parquet", child),
    }
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {n: {"type": "file", "format": "parquet", "path": p} for n, p in srcs.items()},
        "targets": {
            n: {"type": "file", "format": "parquet", "path": str(tmp_path / f"{n}.out.parquet")}
            for n in srcs
        },
        "tables": [
            {
                "name": "parent",
                "columns": [
                    _hash("id", "ns"),
                    {"name": "note", "strategy": "redact"},
                    {"name": "extra", "strategy": "passthrough"},
                ],
            },
            {"name": "child", "columns": [_hash("cid", "cns"), _hash("parent_id", "ns")]},
        ],
        "relationships": [
            {
                "parent": {"table": "parent", "columns": ["id"]},
                "children": [{"table": "child", "columns": ["parent_id"]}],
                "orphan_policy": "preserve",
                "namespace": "ns",
            }
        ],
    }
    path = tmp_path / "fk.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _assert_clean(*paths: Path) -> None:
    for path in paths:
        assert path.exists(), path.name
        assert mc.canaries_in(path) == set(), path.name


def test_the_canary_source_is_dirty(tmp_path: Path) -> None:
    """The guard: the fixture really carries every canary, so a clean target means something."""
    src = Path(_config(tmp_path).parent / "people.parquet")
    assert set(mc.ALL_CANARIES) <= mc.canaries_in(src)
    assert mc.PANDAS_ATTRS in mc.canaries_in(src)


def test_cc1_plain_run_parquet_target_is_clean(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path))])
    assert result.exit_code == 0, result.output
    out = tmp_path / "out.parquet"
    assert pq.ParquetFile(out).metadata.num_rows == _ROWS
    _assert_clean(out)


def test_cc2_unmask_table_write_is_clean(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    masked = tmp_path / "people.parquet"
    out = tmp_path / "unmasked.parquet"
    result = runner.invoke(app, ["unmask", str(cfg), str(masked), "--output", str(out)])
    assert result.exit_code == 0, result.output
    _assert_clean(out)


def test_cc3_chunked_run_parquet_target_is_clean(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["run", str(_config(tmp_path, nested=False)), "--chunked", "--chunk-size", "7"]
    )
    assert result.exit_code == 0, result.output
    out = tmp_path / "out.parquet"
    assert pq.ParquetFile(out).metadata.num_row_groups > 1
    _assert_clean(out)


def test_cc3_chunked_run_of_an_empty_source_is_clean(tmp_path: Path) -> None:
    cfg = _config(tmp_path, nested=False)
    empty = mc.canary_table(
        {
            "id": pa.array([], type=pa.string()),
            "note": pa.array([], type=pa.string()),
            "age": pa.array([], type=pa.int64()),
        }
    )
    pq.write_table(empty, tmp_path / "people.parquet")
    result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "7"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "out.parquet"
    assert pq.ParquetFile(out).metadata.num_rows == 0
    _assert_clean(out)


def test_cc4_out_of_core_fk_run_parquet_targets_are_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force the out-of-core route the way the engine's canary test does, and prove it ran."""
    import decoy_engine

    real = decoy_engine.run_pipeline
    results: list[Any] = []

    def forced(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **{**kwargs, "execution_mode": "out_of_core"})
        results.append(result)
        return result

    monkeypatch.setattr(decoy_engine, "run_pipeline", forced)
    result = runner.invoke(app, ["run", str(_fk_config(tmp_path))])
    assert result.exit_code == 0, result.output
    assert len(results) == 1
    assert results[0].quality_metrics["execution"]["execution_mode"] == "out_of_core"
    _assert_clean(tmp_path / "parent.out.parquet", tmp_path / "child.out.parquet")


def test_cc5_csv_target_has_no_canary(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path, target_format="csv"))])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "out.csv").read_text(encoding="utf-8")
    assert [c for c in mc.ALL_CANARIES if c in text] == []


def test_cc2_dataframe_attrs_are_not_written(tmp_path: Path) -> None:
    """`DataFrame.to_parquet` writes `attrs` into the footer; the writer must not use it."""
    import pandas as pd

    from decoy.cli.io import write_table

    frame = pd.DataFrame({"id": ["a", "b"]})
    frame.attrs["note"] = mc.ATTRS
    frame.columns.name = mc.COLIDX
    out = tmp_path / "frame.parquet"
    write_table(frame, "parquet", out)
    assert mc.canaries_in(out) == set()
