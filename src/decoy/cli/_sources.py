"""Read every data file the CLI reads, dispatching on a declared `format`.

`FileSource.format` is required by the engine's config schema and every
entry point (run, demo, the `mask()` API) validates before reading, so the
declared format is the only thing consulted here. A file's suffix says
nothing about how it should be parsed: a Parquet file named `.pq` and a CSV
named `.dat` both read correctly.

The engine owns the CSV dialect (`has_header`, `column_names`, `delimiter`) and
the headerless width scan. This module owns path resolution and the format
dispatch. It is the one place the CLI reads a data file (the sentry in
tests/sentry/test_csv_read_choke_point.py keeps it that way), and `read_csv_frame` is the one
place a CSV is read. `read_file` reads a file whose format is already decided: a CLI-written
target read back, or the Parquet input of `decoy init` and `decoy scan`. The format decision
for CLI-written files lives with their writer, in `cli/io/_targets.py`.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pyarrow as pa


def resolve_path(raw_path: str, base_dir: Path) -> Path:
    """Resolve a YAML path against the config's directory; absolute paths pass through.

    The one YAML path resolver: `run`, `demo` and the target writers share it. The choice of
    base and the join belong to the engine (`fileaccess.config_relative`); this wrapper keeps
    the CLI's `Path` type and its canonical form for a relative path.
    """
    from decoy_engine.fileaccess import config_relative

    joined = config_relative(raw_path, base_dir)
    return Path(joined) if Path(raw_path).is_absolute() else Path(joined).resolve()


def resolved_source_config(config_dict: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """A shallow copy of a config whose file sources name their files by absolute path.

    The engine profiles a run from the declared source descriptors and opens `path` and
    `column_names_file` as written, so a relative one reads from the working directory. The
    CLI hands the engine this copy instead (the engine's capacity estimate does the same).
    Sources are not part of the config hash, so the copy leaves the run's identity unchanged.
    """
    from decoy_engine import FILE_SOURCE_PATH_FIELDS

    sources = config_dict.get("sources")
    if not isinstance(sources, dict) or not sources:
        return config_dict
    resolved: dict[str, Any] = {}
    for name, descriptor in sources.items():
        if isinstance(descriptor, dict) and descriptor.get("type") == "file":
            descriptor = dict(descriptor)
            for field in FILE_SOURCE_PATH_FIELDS:
                value = descriptor.get(field)
                if isinstance(value, str) and value:
                    descriptor[field] = str(resolve_path(value, base_dir))
        resolved[name] = descriptor
    return {**config_dict, "sources": resolved}


# The CSV dialect keys of a file-source descriptor, the engine's `CsvDialect` fields plus
# `column_names_file`. The one list: `csv_file_source` accepts exactly these, and the `data=`
# override in `decoy.api` carries exactly these over from a declared source.
CSV_DIALECT_KEYS: tuple[str, ...] = ("has_header", "column_names", "column_names_file", "delimiter")


def csv_file_source(path: str | Path, **dialect: Any) -> dict[str, Any]:
    """A `format: csv` file-source descriptor for a file the CLI names itself.

    The engine requires `has_header` on every csv descriptor (`resolve_csv_dialect` refuses
    one without it, and so does `FileSource`), so a descriptor built here states it. A file
    with no declaration is read the way it always was, with a header row. `dialect` keys
    (`CSV_DIALECT_KEYS`) override that; any other key is a TypeError.
    """
    unknown = sorted(set(dialect) - set(CSV_DIALECT_KEYS))
    if unknown:
        raise TypeError(f"csv_file_source: unknown dialect key(s) {unknown}")
    return {"type": "file", "format": "csv", "path": str(path), "has_header": True, **dialect}


def _unknown_format(table_name: str, fmt: object, kind: str = "source") -> ValueError:
    return ValueError(
        f"{kind} {table_name!r}: unsupported format {fmt!r} "
        "(expected one of csv, parquet, fixed_width)"
    )


def read_csv_frame(
    table_name: str,
    src: dict[str, Any],
    base_dir: Path,
    *,
    dtype: type[str] | None,
    nrows: int | None = None,
    chunk_size: int | None = None,
) -> Any:
    """Read a declared CSV source through the engine reader, the one CSV read point.

    The source's `has_header`, `column_names` and `delimiter` apply; omitted keys take the
    engine defaults. `dtype` is a parameter because the callers differ: `decoy run` reads
    every cell as text (`dtype=str`), while `decoy init` and the report verbs keep pandas
    dtypes (`dtype=None`) so their inference and scores do not change. With `chunk_size` the
    engine scans a headerless file at this call and the result is an iterator of frames
    (a `pandas.DataFrame` without it; the return type is `Any` for that reason).
    """
    from decoy_engine import read_csv_source, resolve_csv_dialect

    # The names file sits beside the data file in the YAML, so it resolves like `path`. The
    # descriptor copy keeps the caller's dict (and the config hash, which excludes sources) intact.
    names_file = src.get("column_names_file")
    if names_file:
        src = {**src, "column_names_file": str(resolve_path(names_file, base_dir))}
    return read_csv_source(
        resolve_path(src["path"], base_dir),
        resolve_csv_dialect(src),
        table=table_name,
        dtype=dtype,
        nrows=nrows,
        chunksize=chunk_size,
    )


def read_report_source(path: Path, config_dict: dict[str, Any], config_dir: Path) -> Any:
    """Read the `--source` file of a report verb, with its declared dialect when it has one.

    The declared dialect applies only when a `format: csv` source in `config_dict` resolves
    to this very file; any other file, or no config, reads with the default dialect. Pandas
    dtypes are kept, so the scores are the ones the verbs gave before.
    """
    target = path.resolve()
    for name, src in (config_dict.get("sources") or {}).items():
        if (
            isinstance(src, dict)
            and src.get("format") == "csv"
            and src.get("path")
            and resolve_path(src["path"], config_dir).resolve() == target
        ):
            return read_csv_frame(name, src, config_dir, dtype=None)
    # The user's own path is relative to the current folder, never to the config directory.
    return read_csv_frame(path.stem, csv_file_source(target), config_dir, dtype=None)


def read_file(path: Path, fmt: str, layout: Mapping[str, Any] | None, *, table: str) -> Any:
    """Read one whole file whose format is already decided; returns a `pandas.DataFrame`.

    csv is read all-text through `read_csv_frame` (tokens and masked values match byte for
    byte), parquet keeps its native types, fixed_width is typed per `layout`. Any other
    format raises before the file is opened.
    """
    if fmt == "csv":
        # Absolute, so `resolve_path` does not join a relative path onto its own folder.
        return read_csv_frame(table, csv_file_source(path.resolve()), path.parent, dtype=str)
    if fmt == "parquet":
        import pandas as pd

        return pd.read_parquet(path)
    if fmt == "fixed_width" and layout is not None:
        from decoy_engine import read_fixed_width

        return read_fixed_width(path, dict(layout))
    raise _unknown_format(table, fmt, kind="file")


def read_source(table_name: str, src: dict[str, Any], base_dir: Path) -> pa.Table:
    """Read one file source whole, per its declared `format`.

    csv keeps the `dtype=str` contract (every column arrives as a string);
    parquet keeps its native types; fixed_width goes through the engine's
    public reader so the columns are typed per the declared layout, the same
    way the platform reads it.
    """
    fmt = src.get("format")
    path = resolve_path(src["path"], base_dir)
    if fmt == "parquet":
        import pyarrow.parquet as pq

        return pq.read_table(str(path))
    if fmt == "csv":
        frame = read_csv_frame(table_name, src, base_dir, dtype=str)
        return pa.Table.from_pandas(frame, preserve_index=False)
    if fmt == "fixed_width":
        from decoy_engine import read_fixed_width

        df = read_fixed_width(path, src["layout"])
        return pa.Table.from_pandas(df, preserve_index=False)
    raise _unknown_format(table_name, fmt)


def iter_source_chunks(
    table_name: str, src: dict[str, Any], base_dir: Path, chunk_size: int
) -> Iterator[pa.Table]:
    """Return an iterator of `pa.Table`s of at most `chunk_size` rows from a csv or parquet source.

    This is a plain function, not a generator: the engine scans a headerless csv file when
    this is called, so a misfit file raises here, before the first chunk exists.

    Parquet batches can come back SHORTER than chunk_size at row-group
    boundaries; that is fine and must stay fine, because chunked output is
    chunking-invariant by the engine's parity contract. Nobody should
    "fix" the short batches by re-buffering.

    fixed_width is not streamable: the engine has no bounded fixed-width
    iterator, so `decoy run` refuses it up front and this raises as a
    backstop for any caller that skips that check.
    """
    fmt = src.get("format")
    path = resolve_path(src["path"], base_dir)
    if fmt == "parquet":
        return _parquet_chunks(path, chunk_size)
    if fmt == "csv":
        frames = read_csv_frame(table_name, src, base_dir, dtype=str, chunk_size=chunk_size)
        return (pa.Table.from_pandas(df, preserve_index=False) for df in frames)
    if fmt == "fixed_width":
        raise ValueError(
            f"source {table_name!r}: format 'fixed_width' cannot be read in "
            "chunks; run without --chunked"
        )
    raise _unknown_format(table_name, fmt)


def source_schema_and_chunks(
    table_name: str, src: dict[str, Any], base_dir: Path, chunks: Iterator[pa.Table]
) -> tuple[pa.Schema, Iterator[pa.Table]]:
    """The source schema for a `--chunked` table, and `chunks` with nothing consumed.

    The engine checks the config against `source_schema` before it reads any chunk, and no
    chunk may carry a column outside it. Parquet reports its footer schema without reading
    rows. A csv source has no schema until it is read, so the first chunk is read to take it
    and then put back at the head of the stream; a csv with no chunk at all takes the schema
    of its whole-file read, which is the empty frame.
    """
    if src.get("format") == "parquet":
        return parquet_schema(resolve_path(src["path"], base_dir)), chunks
    first = next(chunks, None)
    if first is None:
        empty = read_csv_frame(table_name, src, base_dir, dtype=str)
        return pa.Table.from_pandas(empty, preserve_index=False).schema, iter(())
    return first.schema, itertools.chain([first], chunks)


def parquet_schema(path: Path) -> pa.Schema:
    """The Arrow schema of a Parquet file, without reading its rows."""
    import pyarrow.parquet as pq

    return pq.ParquetFile(str(path)).schema_arrow


def _parquet_chunks(path: Path, chunk_size: int) -> Iterator[pa.Table]:
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(str(path))
    for batch in parquet_file.iter_batches(batch_size=chunk_size):
        yield pa.Table.from_batches([batch])
