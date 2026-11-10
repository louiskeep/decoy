"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module;
`report diff` and the evidence manifest import the read-side format rule the same way.
Saved-scan reading (`load_scan_set`) is exported here too; do not import `_scan_set`.
The source and DuckDB helpers `decoy run` uses are re-exported here as one bridge over
`cli/_sources.py` and `cli/_duckdb_source.py`, so `cli/run/` imports no private module.
"""

from decoy.cli._duckdb_source import DuckDBSourceError, acquire_relation, parse_flag
from decoy.cli._sources import (
    iter_source_chunks,
    parquet_schema,
    read_source,
    resolve_path,
    resolved_source_config,
)
from decoy.cli.io._scan_set import (
    ScanSetFormatError,
    load_scan_set,
    scan_set_from_data,
    select_table,
)
from decoy.cli.io._targets import (
    TargetFormatError,
    check_output_path,
    check_target_formats,
    entry_format,
    format_for_path,
    input_format,
    resolve_target_format,
    table_records,
    target_format_issues,
    write_chunked_output,
    write_private_table,
    write_table,
    write_targets,
)

__all__ = [
    "DuckDBSourceError",
    "ScanSetFormatError",
    "TargetFormatError",
    "acquire_relation",
    "check_output_path",
    "check_target_formats",
    "entry_format",
    "format_for_path",
    "input_format",
    "iter_source_chunks",
    "load_scan_set",
    "parquet_schema",
    "parse_flag",
    "read_source",
    "resolve_path",
    "resolve_target_format",
    "resolved_source_config",
    "scan_set_from_data",
    "select_table",
    "table_records",
    "target_format_issues",
    "write_chunked_output",
    "write_private_table",
    "write_table",
    "write_targets",
]
