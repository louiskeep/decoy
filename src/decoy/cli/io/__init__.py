"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module;
`report diff` and the evidence manifest import the read-side format rule the same way.
Saved-scan reading (`load_scan_set`) is exported here too; do not import `_scan_set`.

The project layout services are public here as well: the project root finder, the run-folder
and pipeline-name helpers, and the `layout.*` descriptors. Commands, `cli/project` and `ci`
import them from this package, never from `_project`, `_layout` or `_layout_errors`.

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
from decoy.cli.io._layout import (
    PipelineName,
    RunFolder,
    RunLayout,
    check_path_budget,
    contained_path,
    create_run_folder,
    has_placed_output,
    is_placed_relative,
    is_run_id,
    mint_invocation_id,
    name_dir,
    new_run_id,
    open_run_layout,
    pipeline_name_for,
    prepare_out,
    read_claim,
    relative_outputs,
    shown_path,
    target_parent_writable,
    write_claim,
)
from decoy.cli.io._layout_errors import (
    GATE_CODES,
    GATE_DESCRIPTORS,
    OUTPUT_DIR_UNUSABLE,
    WARNING_CODES,
    WARNING_DESCRIPTORS,
    Descriptor,
    LayoutError,
    LayoutWarning,
)
from decoy.cli.io._placement import (
    OutputPlacement,
    fixed_target_overwrites,
    layout_failures,
    layout_issues,
    resolved_output_collisions,
)
from decoy.cli.io._project import Project, ensure_decoy_dir, find_project
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
    "GATE_CODES",
    "GATE_DESCRIPTORS",
    "OUTPUT_DIR_UNUSABLE",
    "WARNING_CODES",
    "WARNING_DESCRIPTORS",
    "Descriptor",
    "DuckDBSourceError",
    "LayoutError",
    "LayoutWarning",
    "OutputPlacement",
    "PipelineName",
    "Project",
    "RunFolder",
    "RunLayout",
    "ScanSetFormatError",
    "TargetFormatError",
    "acquire_relation",
    "check_output_path",
    "check_path_budget",
    "check_target_formats",
    "contained_path",
    "create_run_folder",
    "ensure_decoy_dir",
    "entry_format",
    "find_project",
    "fixed_target_overwrites",
    "format_for_path",
    "has_placed_output",
    "input_format",
    "is_placed_relative",
    "is_run_id",
    "iter_source_chunks",
    "layout_failures",
    "layout_issues",
    "load_scan_set",
    "mint_invocation_id",
    "name_dir",
    "new_run_id",
    "open_run_layout",
    "parquet_schema",
    "parse_flag",
    "pipeline_name_for",
    "prepare_out",
    "read_claim",
    "read_source",
    "relative_outputs",
    "resolve_path",
    "resolve_target_format",
    "resolved_output_collisions",
    "resolved_source_config",
    "scan_set_from_data",
    "select_table",
    "shown_path",
    "table_records",
    "target_format_issues",
    "target_parent_writable",
    "write_chunked_output",
    "write_claim",
    "write_private_table",
    "write_table",
    "write_targets",
]
