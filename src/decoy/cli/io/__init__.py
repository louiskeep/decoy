"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module;
`report diff` and the evidence manifest import the read-side format rule the same way.
"""

from decoy.cli.io._targets import (
    TargetFormatError,
    check_output_path,
    entry_format,
    format_for_path,
    input_format,
    resolve_target_format,
    target_format_issues,
    write_table,
)

__all__ = [
    "TargetFormatError",
    "check_output_path",
    "entry_format",
    "format_for_path",
    "input_format",
    "resolve_target_format",
    "target_format_issues",
    "write_table",
]
