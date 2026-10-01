"""Read a declared `sources:` entry into Arrow, dispatching on its `format`.

`FileSource.format` is required by the engine's config schema and every
entry point (run, demo, the `mask()` API) validates before reading, so the
declared format is the only thing consulted here. A file's suffix says
nothing about how it should be parsed: a Parquet file named `.pq` and a CSV
named `.dat` both read correctly.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p).resolve()


def _unknown_format(table_name: str, fmt: object) -> ValueError:
    return ValueError(
        f"source {table_name!r}: unsupported format {fmt!r} "
        "(expected one of csv, parquet, fixed_width)"
    )


def read_source(table_name: str, src: dict[str, Any], base_dir: Path) -> pa.Table:
    """Read one file source whole, per its declared `format`.

    csv keeps the `dtype=str` contract (every column arrives as a string);
    parquet keeps its native types; fixed_width goes through the engine's
    public reader so the columns are typed per the declared layout, the same
    way the platform reads it.
    """
    fmt = src.get("format")
    path = _resolve_path(src["path"], base_dir)
    if fmt == "parquet":
        import pyarrow.parquet as pq

        return pq.read_table(str(path))
    if fmt == "csv":
        import pandas as pd

        return pa.Table.from_pandas(pd.read_csv(path, dtype=str), preserve_index=False)
    if fmt == "fixed_width":
        from decoy_engine import read_fixed_width

        df = read_fixed_width(path, src["layout"])
        return pa.Table.from_pandas(df, preserve_index=False)
    raise _unknown_format(table_name, fmt)


def iter_source_chunks(
    table_name: str, src: dict[str, Any], base_dir: Path, chunk_size: int
) -> Iterator[pa.Table]:
    """Yield `pa.Table`s of at most `chunk_size` rows from a csv or parquet source.

    Parquet batches can come back SHORTER than chunk_size at row-group
    boundaries; that is fine and must stay fine, because chunked output is
    chunking-invariant by the engine's parity contract. Nobody should
    "fix" the short batches by re-buffering.

    fixed_width is not streamable: the engine has no bounded fixed-width
    iterator, so `decoy run` refuses it up front and this raises as a
    backstop for any caller that skips that check.
    """
    fmt = src.get("format")
    path = _resolve_path(src["path"], base_dir)
    if fmt == "parquet":
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(str(path))
        for batch in parquet_file.iter_batches(batch_size=chunk_size):
            yield pa.Table.from_batches([batch])
        return
    if fmt == "csv":
        import pandas as pd

        for df in pd.read_csv(path, dtype=str, chunksize=chunk_size):
            yield pa.Table.from_pandas(df, preserve_index=False)
        return
    if fmt == "fixed_width":
        raise ValueError(
            f"source {table_name!r}: format 'fixed_width' cannot be read in "
            "chunks; run without --chunked"
        )
    raise _unknown_format(table_name, fmt)
