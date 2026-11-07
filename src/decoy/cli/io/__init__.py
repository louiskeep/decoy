"""CLI target writers. `cli/_sources.py` (the source reader) moves here under H-1.

The pre-run gate imports `target_format_issues` from here, not from the private module.
"""

from decoy.cli.io._targets import target_format_issues

__all__ = ["target_format_issues"]
