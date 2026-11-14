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
from collections.abc import Iterable, Iterator, Mapping
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


def names_schema(names: Iterable[str]) -> pa.Schema:
    """An all-string Arrow schema holding only column names, for a declaration request."""
    return pa.schema([pa.field(name, pa.string()) for name in names])


def _has_path(descriptor: Any) -> bool:
    return isinstance(descriptor, dict) and isinstance(descriptor.get("path"), str)


def refusal_message(exc: Exception) -> str:
    """An engine refusal's text without its leading `code: `, for a printer that shows the code itself."""
    text = str(exc)
    code = getattr(exc, "code", None)
    return text.removeprefix(f"{code}: ") if code else text


def _read_refusal(exc: Exception) -> Any:
    """The coded, value-free refusal for an engine read failure of a declared source.

    A missing, unreadable or malformed file raises `OSError`, `ValueError` (Arrow and decode
    errors) or a non-gate `DecoyError`, and their text names the path. The refusal carries a
    registered code and a fixed text, so every caller catches the one `PipelineValidationError`.
    """
    from decoy_engine import PipelineValidationError, reasons

    if isinstance(exc, FileNotFoundError):
        code, text = (
            reasons.config.SOURCE_FILE_FILE_NOT_FOUND,
            "a declared source file was not found",
        )
    else:
        code = getattr(exc, "code", None) or reasons.runtime.CSV_MALFORMED
        text = "a declared source file could not be read (unreadable or malformed)"
    return PipelineValidationError(f"{code}: {text}", code=code)


def prepared_sources(
    config_dict: dict[str, Any],
    *,
    base_dir: Path,
    schemas: Mapping[str, pa.Schema] | None = None,
) -> Any:
    """Check a validated config's source columns against its declarations before any row is read.

    The engine owns every rule (`prepare_declared_sources`); this builds its request and returns
    its `PreparedDeclaredSources` capability, which a reader needs before it opens a data row.
    With `schemas` (an in-memory table or a DuckDB `DESCRIBE`) the supplied schemas are checked
    and no file is opened; without them each declared source's header or footer is read, never a
    data row. The request holds the reader-side copy, so a relative `path` or
    `column_names_file` resolves against `base_dir` and not the working directory.

    One exception contract: a gate refusal is the engine's `PipelineValidationError` as raised,
    and an engine read failure (missing, unreadable or malformed source) becomes a
    `PipelineValidationError` with a registered code and a fixed, path-free text.
    """
    from decoy_engine import (
        DeclarationRequest,
        DecoyError,
        PipelineValidationError,
        prepare_declared_sources,
    )

    resolved = resolved_source_config(config_dict, base_dir)
    refusal = None
    try:
        if schemas is None:
            # A source with no `path` is not read (`source_is_materialized`), so it has no header.
            read = {n: d for n, d in (resolved.get("sources") or {}).items() if _has_path(d)}
            request = DeclarationRequest.for_descriptors({**resolved, "sources": read})
        else:
            request = DeclarationRequest.for_supplied(resolved, schemas)
        return prepare_declared_sources(request)
    except PipelineValidationError:
        raise
    except (OSError, ValueError, DecoyError) as read_error:
        refusal = _read_refusal(read_error)
    raise refusal


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


def duckdb_probe_config(raw: Any, flags: list[str]) -> dict[str, Any] | None:
    """The validated config with a placeholder Parquet source for each flagged, declared table.

    Staging has not run when a `--duckdb-source` run is checked, and the model requires a source
    per mask table, so a copy stands one in for each flagged table. This is the one deliberate
    parse before the gate (r11 ruling 4): a config that does not parse returns None, so the gate
    keeps reporting it. A malformed `--duckdb-source` flag also returns None; a flag naming an
    undeclared table is left to the membership check.
    """
    from decoy_engine import ConfigError, PipelineValidationError, parse_pipeline_config
    from decoy_engine.config import PipelineConfigError

    from decoy.cli._duckdb_source import DuckDBSourceError, parse_flag

    if not isinstance(raw, dict):
        return None
    # A null `sources` block is an omitted one, as in staging.
    sources = raw.get("sources")
    if sources is not None and not isinstance(sources, dict):
        return None
    tables = raw.get("tables")
    declared = (
        {t.get("name") for t in tables if isinstance(t, dict)}
        if isinstance(tables, list)
        else set()
    )
    probe_sources = dict(sources or {})
    for spec in flags:
        try:
            table = parse_flag(spec)[0]
        except DuckDBSourceError:
            return None
        if table in declared:
            probe_sources[table] = {"type": "file", "format": "parquet", "path": "staged.parquet"}
    try:
        return parse_pipeline_config({**raw, "sources": probe_sources}).model_dump()
    except (PipelineConfigError, PipelineValidationError, ConfigError):
        return None


def check_declared_before_acquire(raw: dict[str, Any], flags: list[str], base_dir: Path) -> None:
    """Refuse an undeclared column of a flagged DuckDB relation before any relation is staged.

    Each relation's columns come from `describe_relation`; the engine checks them against the
    config's table declarations (`prepared_sources`) on the config `duckdb_probe_config` builds.
    A config that does not parse is left alone: the gate reports it, as it does today.
    A flag naming a table the config does not declare is left to the membership check.
    """
    from decoy.cli._duckdb_source import describe_relation, parse_flag

    tables = raw.get("tables")
    if not isinstance(tables, list):
        return
    declared = {t.get("name") for t in tables if isinstance(t, dict)}
    schemas = {}
    for spec in flags:
        table, db = parse_flag(spec)
        if table in declared:
            schemas[table] = names_schema(describe_relation(resolve_path(db, base_dir), table))
    if not schemas:
        return
    validated = duckdb_probe_config(raw, flags)
    if validated is not None:
        prepared_sources(validated, base_dir=base_dir, schemas=schemas)


class ReportSourceError(Exception):
    """A `--config` report refused before its `--source` was read. `message` holds no path,
    column or value; `code` is the engine's reason code when the engine refused."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _declared_table_for(source: Path, config_dict: dict[str, Any], config_dir: Path) -> str | None:
    """The table whose declared source is `source`, else the config's only table, else None."""
    target = source.resolve()
    for name, src in (config_dict.get("sources") or {}).items():
        if isinstance(src, dict) and src.get("path"):
            if resolve_path(src["path"], config_dir).resolve() == target:
                return str(name)
    names = [t.get("name") for t in config_dict.get("tables") or [] if isinstance(t, dict)]
    return str(names[0]) if len(names) == 1 else None


def gate_report_source(
    config_dict: dict[str, Any], config_dir: Path, source: Path, table: str | None = None
) -> str | None:
    """Check `source` against the selected table's declaration before it is read.

    The table is `table` when given (integrity anchors on the first declared one); otherwise the
    declared source whose resolved path is `source`, else the config's only table. The engine
    checks the table's own descriptor with `path` set to `source`, so the bytes read are the bytes
    checked, and a declared dialect applies. A config with no file source has nothing to check.
    Returns the selected table, or None when nothing was selected to check.
    """
    from decoy_engine import PipelineValidationError

    sources = {n: d for n, d in (config_dict.get("sources") or {}).items() if isinstance(d, dict)}
    if not sources:
        return None
    if table is None:
        table = _declared_table_for(source, config_dict, config_dir)
        if table is None:
            from decoy.cli.io import REPORT_SOURCE_AMBIGUOUS

            raise ReportSourceError(REPORT_SOURCE_AMBIGUOUS.message, REPORT_SOURCE_AMBIGUOUS.code)
    descriptor = sources.get(table)
    if descriptor is None or descriptor.get("type", "file") != "file":
        return None
    # `read_report_source` reads any source that is not `format: csv` as a default CSV, so the
    # check uses the descriptor the reader will use, not the declared reader.
    target = str(source.resolve())
    checked = (
        {**descriptor, "path": target}
        if descriptor.get("format") == "csv"
        else csv_file_source(target)
    )
    gated = {**config_dict, "sources": {table: checked}}
    refusal: ReportSourceError | None = None
    try:
        prepared_sources(gated, base_dir=config_dir)
    except PipelineValidationError as exc:
        refusal = ReportSourceError(refusal_message(exc), exc.code)
    if refusal is not None:
        raise refusal
    return table


def read_report_source(
    path: Path, config_dict: dict[str, Any], config_dir: Path, table: str | None = None
) -> Any:
    """Read the `--source` file of a report verb, with its declared dialect when it has one.

    The declared dialect applies when `table` names a `format: csv` source of `config_dict`
    (the table `gate_report_source` selected), or, with no `table`, when a csv source resolves
    to this very file. Any other file, or no config, reads with the default dialect. Pandas
    dtypes are kept, so the scores are the ones the verbs gave before.
    """
    target = path.resolve()
    for name, src in (config_dict.get("sources") or {}).items():
        if not (isinstance(src, dict) and src.get("format") == "csv" and src.get("path")):
            continue
        if name == table or (
            table is None and resolve_path(src["path"], config_dir).resolve() == target
        ):
            return read_csv_frame(name, {**src, "path": str(target)}, config_dir, dtype=None)
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
    and then put back at the head of the stream; a csv with no chunk at all takes the header of
    its whole-file read, which is the empty frame. Every csv chunk is cast to one all-string
    schema built from that header, so an all-empty column never changes type between chunks.
    """
    if src.get("format") == "parquet":
        return parquet_schema(resolve_path(src["path"], base_dir)), chunks
    first = next(chunks, None)
    if first is None:
        empty = read_csv_frame(table_name, src, base_dir, dtype=str)
        return _all_string_schema(pa.Table.from_pandas(empty, preserve_index=False)), iter(())
    schema = _all_string_schema(first)
    return schema, (chunk.cast(schema) for chunk in itertools.chain([first], chunks))


def _all_string_schema(table: pa.Table) -> pa.Schema:
    """One explicit string field per column of `table`.

    A csv read is all-text, but an all-empty column in one chunk still arrives as an Arrow
    `null` field while another chunk gives `string`. The engine rejects non-string chunks for
    text strategies, so the result would then depend on chunk size and row placement.
    """
    return pa.schema([pa.field(name, pa.string()) for name in table.column_names])


def parquet_schema(path: Path) -> pa.Schema:
    """The Arrow schema of a Parquet file, without reading its rows."""
    import pyarrow.parquet as pq

    return pq.ParquetFile(str(path)).schema_arrow


def _parquet_chunks(path: Path, chunk_size: int) -> Iterator[pa.Table]:
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(str(path))
    for batch in parquet_file.iter_batches(batch_size=chunk_size):
        yield pa.Table.from_batches([batch])
