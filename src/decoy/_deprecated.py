"""Deprecation shim for the old `forge` console command.

Kept for one minor version so users with `pip install forge` muscle memory
get a clear migration message instead of a silent failure.
"""

import sys


def forge_shim() -> None:
    sys.stderr.write(
        "The `forge` CLI is now `decoy`.\n"
        "Install: pip install decoy\n"
        "Docs:    https://decoy.dev\n"
    )
    sys.exit(2)
