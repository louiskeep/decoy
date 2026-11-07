"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module;
`report diff` and the evidence manifest import the read-side format rule the same way.
"""

from decoy.cli.io._targets import (
    TargetFormatError,
    entry_format,
    resolve_target_format,
    target_format_issues,
)

__all__ = ["TargetFormatError", "entry_format", "resolve_target_format", "target_format_issues"]
