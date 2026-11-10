"""csv source descriptors for the configs tests write.

The engine requires `has_header` on every `format: csv` source (engine #409), so a test config
builds its csv sources here and each one states it. This matches
`decoy.cli._sources.csv_file_source` but is written out on purpose: a test does not take its
expected config from the code under test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def csv_source(path: str | Path, **dialect: Any) -> dict[str, Any]:
    """A `format: csv` file source with a header row; `dialect` keys override or add to it."""
    return {"type": "file", "format": "csv", "path": str(path), "has_header": True, **dialect}


def file_source(path: str | Path, fmt: str, **extra: Any) -> dict[str, Any]:
    """A file source in any format. A csv one comes from `csv_source`, so it states
    `has_header`; the engine refuses that key on the other formats."""
    if fmt == "csv":
        return csv_source(path, **extra)
    return {"type": "file", "format": fmt, "path": str(path), **extra}
