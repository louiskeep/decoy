"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module;
`report diff` and the evidence manifest import the read-side format rule the same way.
Saved-scan reading (`load_scan_set`) is exported here too; do not import `_scan_set`.
"""

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
    "ScanSetFormatError",
    "TargetFormatError",
    "check_output_path",
    "entry_format",
    "format_for_path",
    "input_format",
    "load_scan_set",
    "resolve_target_format",
    "scan_set_from_data",
    "select_table",
    "target_format_issues",
    "write_private_table",
    "write_table",
]
