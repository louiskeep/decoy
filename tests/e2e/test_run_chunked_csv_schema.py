"""`decoy run --chunked` on a csv with an all-empty column in some chunks.

Pandas reads an all-empty `dtype=str` column as Arrow `null`, not `string`. The engine
rejects non-string chunks for text strategies, so before the fix the result depended on
`--chunk-size` and on where the empty cells sat. Every chunk must read as one all-string
schema, so chunked output equals the full-frame run for any chunk size.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli._sources import iter_source_chunks, source_schema_and_chunks
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_ROWS = 12
# note is empty in the first half only, or in the second half only.
_EMPTY_FIRST = ["" if i < 6 else f"note {i}" for i in range(_ROWS)]
_EMPTY_LAST = [f"note {i}" if i < 6 else "" for i in range(_ROWS)]


def _write(tmp_path: Path, notes: list[str]) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": [f"id{i}" for i in range(_ROWS)], "note": notes}).to_csv(src, index=False)
    return src


def _config(tmp_path: Path, src: Path, out: Path) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"t": csv_source(src)},
        "tables": [
            {
                "name": "t",
                "columns": [
                    {"name": "id", "strategy": "hash", "namespace": "id_ns"},
                    {"name": "note", "strategy": "hash", "namespace": "note_ns"},
                ],
            }
        ],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(out)}},
    }
    path = tmp_path / f"pipeline-{out.stem}.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


@pytest.mark.parametrize("notes", [_EMPTY_FIRST, _EMPTY_LAST], ids=["empty-first", "empty-last"])
def test_every_csv_chunk_has_the_same_all_string_schema(tmp_path: Path, notes: list[str]) -> None:
    src = _write(tmp_path, notes)
    spec = csv_source(src)
    chunks = iter_source_chunks("t", spec, tmp_path, 3)
    schema, stream = source_schema_and_chunks("t", spec, tmp_path, chunks)
    assert schema.names == ["id", "note"]
    assert schema.types == [pa.string(), pa.string()]
    seen = list(stream)
    assert len(seen) == 4
    assert all(chunk.schema.types == [pa.string(), pa.string()] for chunk in seen)


def test_empty_csv_source_schema_is_all_string(tmp_path: Path) -> None:
    src = tmp_path / "empty.csv"
    src.write_text("id,note\n", encoding="utf-8")
    spec = csv_source(src)
    schema, stream = source_schema_and_chunks(
        "t", spec, tmp_path, iter_source_chunks("t", spec, tmp_path, 3)
    )
    assert schema.names == ["id", "note"]
    assert schema.types == [pa.string(), pa.string()]
    assert all(chunk.num_rows == 0 and chunk.schema.types == schema.types for chunk in stream)


@pytest.mark.parametrize("notes", [_EMPTY_FIRST, _EMPTY_LAST], ids=["empty-first", "empty-last"])
def test_chunked_output_is_chunk_size_invariant_and_matches_full_frame(
    tmp_path: Path, notes: list[str]
) -> None:
    src = _write(tmp_path, notes)
    full_out = tmp_path / "full.csv"
    result = runner.invoke(app, ["run", str(_config(tmp_path, src, full_out))])
    assert result.exit_code == 0, result.output
    expected = full_out.read_bytes()
    for size in (1, 3, 6, 7, 100):
        out = tmp_path / f"chunk{size}.csv"
        result = runner.invoke(
            app,
            ["run", str(_config(tmp_path, src, out)), "--chunked", "--chunk-size", str(size)],
        )
        assert result.exit_code == 0, (size, result.output)
        assert out.read_bytes() == expected, size
