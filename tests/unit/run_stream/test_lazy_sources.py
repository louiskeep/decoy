"""C1l candidates: `lazy_sources` builds one engine lazy source per local mask table."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from decoy_engine.profile import LazySource
from tests.csv_sources import csv_source, file_source

from decoy.cli.io._lazy import lazy_sources


def _cfg(sources: dict, tables: list[str]) -> dict:
    return {
        "version": 2,
        "sources": sources,
        "tables": [
            {
                "name": name,
                "columns": [{"name": "a", "strategy": "faker", "provider": "person_email"}],
            }
            for name in tables
        ],
    }


def _parquet(path: Path) -> Path:
    pq.write_table(pa.table({"a": ["x", "y"]}), path)
    return path


def test_parquet_and_csv_mask_tables_become_candidates(tmp_path: Path) -> None:
    pq_path = _parquet(tmp_path / "p.parquet")
    csv_path = tmp_path / "c.csv"
    csv_path.write_text("a\nx\n", encoding="utf-8")
    cfg = _cfg(
        {"p": file_source(pq_path, "parquet"), "c": csv_source(csv_path)},
        ["p", "c"],
    )
    found = lazy_sources(cfg, tmp_path)
    assert sorted(found) == ["c", "p"]
    assert all(isinstance(src, LazySource) for src in found.values())


def test_relative_path_resolves_against_the_config_folder(tmp_path: Path) -> None:
    _parquet(tmp_path / "p.parquet")
    cfg = _cfg({"p": {"type": "file", "format": "parquet", "path": "p.parquet"}}, ["p"])
    found = lazy_sources(cfg, tmp_path)
    assert sorted(found) == ["p"]
    # The candidate names the file by the config folder, never the working directory.
    assert Path(found["p"].path) == tmp_path / "p.parquet"


def test_compressed_csv_stays_resident(tmp_path: Path) -> None:
    gz = tmp_path / "c.csv.gz"
    gz.write_bytes(b"")
    cfg = _cfg({"c": csv_source(gz)}, ["c"])
    assert lazy_sources(cfg, tmp_path) == {}


def test_source_without_path_and_generate_table_are_skipped(tmp_path: Path) -> None:
    pq_path = _parquet(tmp_path / "p.parquet")
    column = {"name": "a", "strategy": "faker", "provider": "person_email"}
    cfg = {
        "version": 2,
        "sources": {
            "gen": file_source(pq_path, "parquet"),
            "nopath": {"type": "file", "format": "parquet"},
        },
        "tables": [
            {"name": "gen", "row_count": 3, "generate_columns": [column]},
            {"name": "nopath", "columns": [column]},
        ],
    }
    assert lazy_sources(cfg, tmp_path) == {}


def test_no_sources_block(tmp_path: Path) -> None:
    assert lazy_sources({"version": 2}, tmp_path) == {}
