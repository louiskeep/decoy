"""C1l measurements on a test node (AT-C1c peak RSS, AT-C1w timing). Run with vm-run:

    DECOY_RUN_STREAM_PERF=1 $PY -m pytest tests/e2e/run_stream/test_lazy_perf.py -s

Each cell runs the CLI in a fresh process lazy and resident, prints both peaks and wall times,
and asserts the lazy peak is below the resident one. Skipped unless the variable is set, so the
default suite and laptops never build the large inputs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tests.csv_sources import file_source
from tests.e2e.run_stream._support import write_config
from tests.keyed_secret import TEST_MASK_SECRET_REF, secret_env

pytestmark = [
    pytest.mark.skipif(not os.environ.get("DECOY_RUN_STREAM_PERF"), reason="VM measurement cell"),
    pytest.mark.timeout(1800),
]

_DRIVER = Path(__file__).with_name("_perf_driver.py")
_HASH = {"name": "email", "strategy": "hash", "namespace": "em"}


def _measure(config: Path, mode: str) -> dict[str, Any]:
    env = {**os.environ, **secret_env()}
    done = subprocess.run(
        [sys.executable, str(_DRIVER), str(config), mode],
        capture_output=True,
        text=True,
        env=env,
        timeout=1700,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def _compare(tmp: Path, build: Any, label: str, margin: float = 1.0, strict: bool = True) -> None:
    results = {}
    for mode in ("lazy", "base"):
        out = tmp / mode
        out.mkdir()
        results[mode] = _measure(build(out), mode)
        assert results[mode]["exit"] == 0, results[mode]
    lazy, base = results["lazy"], results["base"]
    print(f"\n{label}: lazy {lazy} | resident {base}")
    limit = base["peak_rss"] * margin
    assert lazy["peak_rss"] < limit if strict else lazy["peak_rss"] <= limit


def _emails(n: int, prefix: str = "u") -> pa.Array:
    return pa.array(np.char.add(prefix, np.arange(n).astype(str)))


def test_parquet_peak_rss_below_resident(tmp_path: Path) -> None:
    rows = 4_000_000
    pq.write_table(
        pa.table({"id": np.arange(rows), "email": _emails(rows)}),
        tmp_path / "big.parquet",
        row_group_size=250_000,
    )

    def build(out: Path) -> Path:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 1, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {"big": file_source(tmp_path / "big.parquet", "parquet")},
            "tables": [
                {"name": "big", "columns": [{"name": "id", "strategy": "passthrough"}, _HASH]}
            ],
            "targets": {
                "big": {"type": "file", "format": "parquet", "path": str(out / "big.parquet")}
            },
        }
        return write_config(out / "p.yaml", cfg)

    _compare(tmp_path, build, "parquet 4M rows")


def test_three_level_chain_peak_rss_below_resident(tmp_path: Path) -> None:
    rows = 1_500_000
    ids = np.char.add("k", np.arange(rows).astype(str))
    for name, cols in (
        ("a", {"id": ids}),
        ("b", {"id": ids, "a_id": ids}),
        ("c", {"id": ids, "b_id": ids}),
    ):
        pq.write_table(pa.table(cols), tmp_path / f"{name}.parquet", row_group_size=250_000)

    def hashed(name: str, ns: str) -> dict[str, Any]:
        return {"name": name, "strategy": "hash", "namespace": ns}

    def build(out: Path) -> Path:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 1, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {n: file_source(tmp_path / f"{n}.parquet", "parquet") for n in "abc"},
            "tables": [
                {"name": "a", "columns": [hashed("id", "na")]},
                {"name": "b", "columns": [hashed("id", "nb"), hashed("a_id", "na")]},
                {"name": "c", "columns": [hashed("id", "nc"), hashed("b_id", "nb")]},
            ],
            "relationships": [
                {
                    "parent": {"table": "a", "columns": ["id"]},
                    "children": [{"table": "b", "columns": ["a_id"]}],
                    "orphan_policy": "preserve",
                    "namespace": "na",
                },
                {
                    "parent": {"table": "b", "columns": ["id"]},
                    "children": [{"table": "c", "columns": ["b_id"]}],
                    "orphan_policy": "preserve",
                    "namespace": "nb",
                },
            ],
            "targets": {
                n: {"type": "file", "format": "parquet", "path": str(out / f"{n}.parquet")}
                for n in "abc"
            },
        }
        return write_config(out / "p.yaml", cfg)

    _compare(tmp_path, build, "three-level chain 1.5M rows each", margin=0.9)


def test_fixed_width_four_million_records(tmp_path: Path) -> None:
    rows = 4_000_000
    ids = np.arange(rows).astype(str)
    emails = np.char.add("u", ids)
    lines = np.char.add(np.char.ljust(ids, 8), np.char.ljust(emails, 28))
    (tmp_path / "f.dat").write_text("\n".join(lines.tolist()) + "\n", encoding="utf-8")
    layout = {
        "columns": [
            {"name": "id", "start": 0, "width": 8},
            {"name": "email", "start": 8, "width": 28},
        ]
    }

    def build(out: Path) -> Path:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 1, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {"f": file_source(tmp_path / "f.dat", "fixed_width", layout=layout)},
            "tables": [
                {"name": "f", "columns": [{"name": "id", "strategy": "passthrough"}, _HASH]}
            ],
            "targets": {"f": {"type": "file", "format": "csv", "path": str(out / "f.csv")}},
        }
        return write_config(out / "p.yaml", cfg)

    # AT-C1w records time and peak against resident. The CSV target keeps the output resident
    # with no sink, so the peak can equal the resident run; the plan claims bounded input
    # memory only, so this cell asserts no regression.
    _compare(tmp_path, build, "fixed-width 4M records", strict=False)
