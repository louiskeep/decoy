"""G-ONE-TARGET-WRITE: a table is written to a target through `cli/io/_targets.py` only.

Walks every module under `src/decoy/` for table write calls and fails on one outside
`cli/io/_targets.py` unless its (file, enclosing function) is in ALLOWLIST with the exact site
count. Inside the choke point, writes may sit only in the functions named in WRITERS. The
baseline may shrink and never grow (tests/sentry/baselines/target-writes-allow.json, checked by
scripts/dev/ratchet_check.py). The scanner is shared with G-ONE-CSV-READ (`_calls.py`).

Watched:
- any receiver: `.to_csv(`, `.to_parquet(`
- `pyarrow.parquet`: `write_table`, `ParquetWriter`, `write_to_dataset`
- `pyarrow.csv`: `write_csv`, `CSVWriter`
- `decoy_engine` (any submodule): `write_fixed_width`

Named limits of a syntax walk: a call through a runtime-bound name (`getattr(pd, "to_csv")`),
an alias by assignment (`w = pq.write_table; w(t, p)`), `from x import *`, and `exec`. Writer
families not watched (the CLI uses none today): polars `.write_csv` and `.write_parquet`,
`pyarrow.feather`, pandas `to_feather`, `to_excel` and `to_json`. A slice that adds one also
adds it to the watch set. `csv.writer` and `write_text` are not table writers here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.sentry.io_policy._calls import call_sites, tally

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "cli/io/_targets.py"
WRITERS = ("write_table", "write_chunked_output", "_write_fixed_width")
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "target-writes-allow.json"

_METHODS = frozenset({"to_csv", "to_parquet"})
_PARQUET = {"write_table", "ParquetWriter", "write_to_dataset"}
_ARROW_CSV = {"write_csv", "CSVWriter"}


@dataclass(frozen=True)
class AllowedWrite:
    file: str  # relative to src/decoy
    function: str
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedWrite, ...] = (
    AllowedWrite(
        "api.py",
        "_stage_source_entry",
        1,
        "Spools in-memory data= to a private temp Parquet read back as a source; "
        "not a target write.",
    ),
)


def _owns(module: str, name: str) -> bool:
    if module == "pyarrow.parquet":
        return name in _PARQUET
    if module == "pyarrow.csv":
        return name in _ARROW_CSV
    return module.split(".")[0] == "decoy_engine" and name == "write_fixed_width"


def write_sites(source: str) -> list[tuple[int, str]]:
    """Return (line, enclosing function or '<module>') for each watched write call."""
    return call_sites(source, qualified_match=_owns, method_names=_METHODS)


def _tally(root: Path) -> dict[tuple[str, str], int]:
    return tally(root, skip=CHOKE_POINT, finder=write_sites)


def _allowed() -> dict[tuple[str, str], int]:
    return {(a.file, a.function): a.sites for a in ALLOWLIST}


def test_no_table_write_outside_the_writer_module() -> None:
    found, allowed = _tally(SRC), _allowed()
    extra = {k: n for k, n in found.items() if allowed.get(k, 0) < n}
    assert not extra, f"table write outside cli/io/_targets.py: {sorted(extra)}"


def test_allowlist_entries_are_live_and_exact() -> None:
    found = _tally(SRC)
    stale = {k: n for k, n in _allowed().items() if found.get(k, 0) != n}
    assert not stale, f"allowlist entries that no longer match the code: {sorted(stale)}"


def test_allowlist_has_reasons_and_unique_identities() -> None:
    assert len(_allowed()) == len(ALLOWLIST)
    assert all(len(a.reason) >= 15 for a in ALLOWLIST)


def test_baseline_json_records_the_same_entries_and_reasons() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    expected = {f"{a.file}::{a.function}": {"reason": a.reason} for a in ALLOWLIST}
    assert entries == expected


def _outside_writers(source: str) -> list[str]:
    return sorted({scope for _l, scope in write_sites(source) if scope not in WRITERS})


def test_writer_module_writes_only_in_its_writers() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    scopes = {scope for _l, scope in write_sites(source)}
    assert _outside_writers(source) == []
    assert set(WRITERS) <= scopes, f"writers with no write site: {sorted(set(WRITERS) - scopes)}"
    seeded = source + "\n\ndef sneaky(df, p):\n    df.to_csv(p)\n"
    assert _outside_writers(seeded) == ["sneaky"]


@pytest.mark.parametrize(
    "source",
    [
        "import pyarrow.parquet as pq\ndef f(t, p):\n    pq.write_table(t, p)\n",
        "import pyarrow.parquet\ndef f(t, p):\n    pyarrow.parquet.write_table(t, p)\n",
        "from pyarrow import parquet\ndef f(t, p):\n    parquet.write_table(t, p)\n",
        "from pyarrow.parquet import write_table as wt\ndef f(t, p):\n    wt(t, p)\n",
        "import pyarrow.parquet as pq\ndef f(p, s):\n    pq.ParquetWriter(p, s)\n",
        "import pyarrow.parquet as pq\ndef f(t, p):\n    pq.write_to_dataset(t, p)\n",
        "import pyarrow.csv\ndef f(t, p):\n    pyarrow.csv.write_csv(t, p)\n",
        "import pyarrow.csv as pc\ndef f(p, s):\n    pc.CSVWriter(p, s)\n",
        "def f(frame, p):\n    frame.to_parquet(p)\n",
        "def f(frame, p):\n    frame.to_csv(p)\n",
        "def f(t, p):\n    t.to_pandas().to_csv(p)\n",
        "import pandas as pd\ndef f(frame, p):\n    pd.DataFrame.to_csv(frame, p)\n",
        "import decoy_engine as de\ndef f(fr, lay, p):\n    de.write_fixed_width(fr, lay, p)\n",
        "from decoy_engine import write_fixed_width\ndef f(fr, lay, p):\n    write_fixed_width(fr, lay, p)\n",
    ],
)
def test_walk_sees_each_spelling(source: str) -> None:
    assert [scope for _l, scope in write_sites(source)] == ["f"]


@pytest.mark.parametrize(
    "source",
    [
        "def f(t, writer):\n    writer.write_table(t)\n",
        "def f(t, p, make):\n    w = make(p)\n    w.write_table(t)\n",
        "class C:\n    def f(self, t):\n        self.sink.write_table(t)\n",
        "def to_csvish(x):\n    return x\ndef f(x):\n    return to_csvish(x)\n",
        "import pyarrow.parquet as pq\ndef f(p):\n    return pq.read_table(p)\n",
    ],
)
def test_walk_ignores_lookalikes(source: str) -> None:
    assert write_sites(source) == []


def test_seeded_bypass_is_red(tmp_path: Path) -> None:
    pkg = tmp_path / "cli"
    pkg.mkdir()
    seeds = {
        "sneaky.py": "def save(df, p):\n    df.to_csv(p)\n",
        "sneaky2.py": "import pyarrow.parquet as pq\ndef save(t, p):\n    pq.write_table(t, p)\n",
        "sneaky3.py": (
            "from decoy_engine import write_fixed_width\n"
            "def save(f, lay, p):\n    write_fixed_width(f, lay, p)\n"
        ),
    }
    for name, text in seeds.items():
        (pkg / name).write_text(text, encoding="utf-8")
    assert _tally(tmp_path) == {(f"cli/{name}", "save"): 1 for name in seeds}
