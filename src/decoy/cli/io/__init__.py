"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module;
`report diff` and the evidence manifest import the read-side format rule the same way.
Saved-scan reading (`load_scan_set`) is exported here too; do not import `_scan_set`.

The project layout services are public here as well: the project root finder, the run-folder
and pipeline-name helpers, and the `layout.*` descriptors. Commands, `cli/project` and `ci`
import them from this package, never from `_project`, `_layout` or `_layout_errors`.
"""

from decoy.cli.io._layout import (
    PipelineName,
    RunFolder,
    check_path_budget,
    create_run_folder,
    is_run_id,
    name_dir,
    new_run_id,
    pipeline_name_for,
    prepare_out,
    read_claim,
    write_claim,
)
from decoy.cli.io._layout_errors import (
    GATE_CODES,
    GATE_DESCRIPTORS,
    WARNING_CODES,
    WARNING_DESCRIPTORS,
    Descriptor,
    LayoutError,
    LayoutWarning,
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
    entry_format,
    format_for_path,
    input_format,
    resolve_target_format,
    target_format_issues,
    write_private_table,
    write_table,
)

__all__ = [
    "GATE_CODES",
    "GATE_DESCRIPTORS",
    "WARNING_CODES",
    "WARNING_DESCRIPTORS",
    "Descriptor",
    "LayoutError",
    "LayoutWarning",
    "PipelineName",
    "Project",
    "RunFolder",
    "ScanSetFormatError",
    "TargetFormatError",
    "check_output_path",
    "check_path_budget",
    "create_run_folder",
    "ensure_decoy_dir",
    "entry_format",
    "find_project",
    "format_for_path",
    "input_format",
    "is_run_id",
    "load_scan_set",
    "name_dir",
    "new_run_id",
    "pipeline_name_for",
    "prepare_out",
    "read_claim",
    "resolve_target_format",
    "scan_set_from_data",
    "select_table",
    "target_format_issues",
    "write_claim",
    "write_private_table",
    "write_table",
]
