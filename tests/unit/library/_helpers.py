"""Shared builders for the library tests: real engine envelopes and a child-process runner.

Child processes import this module by its dotted name, so the repository root goes on their
`sys.path` (`CHILD_PRELUDE`).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from decoy_engine import records

ROOT = Path(__file__).resolve().parents[3]
PRODUCER = {"name": "decoy-cli", "version": "0.0.0", "engine_version": "0.22.0"}
INVOCATION = "0b6c9a3e-1d2f-4c5b-8a7e-9f0e1d2c3b4a"
CHILD_PRELUDE = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"


def envelope(n: int = 0, links: Iterable[str] = ()) -> records.RecordEnvelope:
    """A real `sample-run` envelope; `n` changes the payload so each gets its own id."""
    payload = {
        "sample_size": n + 1,
        "root_table": "orders",
        "table_rows": {"orders": n + 1},
        "subset_seed_counts": {"orders": n + 1},
        "approximate_columns": (),
        "scratch_dir": "scratch/sample",
        "outputs": (),
        "ttl_seconds": 60,
    }
    return records.build(
        "sample-run",
        payload,
        producer=PRODUCER,
        invocation_id=INVOCATION,
        created_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
        links=[{"rel": "sample", "id": target} for target in links],
    )


def object_path(library_root: Path, record_id: str) -> Path:
    digest = record_id.removeprefix("sha256:")
    return library_root / "library" / "objects" / digest[:2] / f"{digest[2:]}.json"


def object_files(library_root: Path) -> list[Path]:
    return sorted((library_root / "library" / "objects").glob("*/*.json"))


def mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def run_child(code: str, *argv: str, timeout: float = 120) -> str:
    done = subprocess.run(
        [sys.executable, "-c", CHILD_PRELUDE + code, *argv],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=ROOT,
    )
    return done.stdout


def start_child(code: str, *argv: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", CHILD_PRELUDE + code, *argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=ROOT,
    )
