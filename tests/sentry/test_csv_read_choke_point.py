"""G-ONE-CSV-READ: every data-file read goes through `cli/_sources.py`.

Walks the syntax tree of every module under `src/decoy/` for calls to a watched reader, in any
spelling (`pd.read_csv`, `from pandas import read_csv`, an `import ... as` alias,
`from pyarrow import parquet`). The watch table:

- any module: `read_csv`, `read_parquet`;
- pandas: every `read_*` (`read_table`, `read_fwf`, `read_json`, `read_excel`, ...);
- polars: every `read_*` and `scan_*`;
- `pyarrow.dataset`: `dataset`, `parquet_dataset`;
- `pyarrow.parquet` (and its `core` submodule): `read_table`, `read_pandas`, `ParquetFile`, `ParquetDataset`,
  `read_schema`, `read_metadata`;
- `decoy_engine`: `read_csv_source`, `read_fixed_width` and `resolve_csv_dialect` (the names-file
  read sits inside it, so it is called only where `column_names_file` is resolved).

A call outside `cli/_sources.py` fails unless its (file, enclosing function) is in ALLOWLIST with
the exact recorded site count. The allowlisted readers read files a caller named with their own
flags, or the bundled demo sample, not a declared source or a CLI-written target. The baseline
may shrink and never grow (tests/sentry/baselines/csv-read-allow.json, checked by
scripts/dev/ratchet_check.py). The sentry keeps its CSV-era name and id; H-1 renames it.

Named limits of a syntax walk: a call through a runtime-bound name (`getattr(pd, "read_csv")`),
an alias by assignment (`rc = pd.read_csv; rc(p)`), and `from pandas import *`.

The call scanner is shared with G-ONE-TARGET-WRITE (tests/sentry/io_policy/_calls.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.sentry.io_policy._calls import call_sites, tally

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "cli/_sources.py"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "csv-read-allow.json"


@dataclass(frozen=True)
class AllowedRead:
    file: str  # relative to src/decoy
    function: str
    sites: int
    reason: str


ALLOWLIST: tuple[AllowedRead, ...] = (
    AllowedRead(
        "cli/demo.py",
        "_run_single_demo",
        1,
        "Reads the bundled demo sample for the STORM scan step; not a declared source.",
    ),
    AllowedRead(
        "cli/fit.py",
        "fit",
        2,
        "A caller-named file with its own parse flags; not a declared source.",
    ),
    AllowedRead(
        "cli/scan.py",
        "_load_csv_with_sampling",
        4,
        "A caller-named file with its own sampling flags; not a declared source.",
    ),
    AllowedRead(
        "cli/scan.py",
        "_load_fixed_width_with_sampling",
        3,
        "A caller-named fixed-width file with its own layout flags; not a declared source.",
    ),
)


_ANY_MODULE = {"read_csv", "read_parquet"}
_PYARROW_PARQUET = {
    "read_table",
    "read_pandas",
    "ParquetFile",
    "ParquetDataset",
    "read_schema",
    "read_metadata",
}
_PYARROW_DATASET = {"dataset", "parquet_dataset"}
_ENGINE = {"read_csv_source", "read_fixed_width", "resolve_csv_dialect"}


def _owns(package: str, name: str) -> bool:
    """Whether `name` from `package` is a watched reader (see the module docstring)."""
    if name in _ANY_MODULE:
        return True
    top = package.split(".")[0]
    if top == "pandas":
        return name.startswith("read_")
    if top == "polars":
        return name.startswith(("read_", "scan_"))
    if package.startswith("pyarrow.parquet"):
        return name in _PYARROW_PARQUET
    if package == "pyarrow.dataset":
        return name in _PYARROW_DATASET
    return top == "decoy_engine" and name in _ENGINE


def _owns_csv(package: str, name: str) -> bool:
    """The CSV-kind readers: the ones `read_csv_frame` must be the only call of."""
    top = package.split(".")[0]
    if name == "read_csv":
        return True
    if name in {"read_table", "read_fwf"}:
        return top == "pandas"
    return top == "decoy_engine" and name == "read_csv_source"


def read_sites(source: str) -> list[tuple[int, str]]:
    """Return (line, enclosing function or '<module>') for each watched call."""
    # Leaf scope names: the baseline keys (`cli/report.py::_load`) are recorded that way.
    return call_sites(source, qualified_match=_owns, qualified_scopes=False)


def _tally(root: Path) -> dict[tuple[str, str], int]:
    return tally(root, skip=CHOKE_POINT, finder=read_sites)


def _allowed() -> dict[tuple[str, str], int]:
    return {(a.file, a.function): a.sites for a in ALLOWLIST}


def test_no_csv_read_outside_the_choke_point() -> None:
    found, allowed = _tally(SRC), _allowed()
    extra = {k: n for k, n in found.items() if allowed.get(k, 0) < n}
    assert not extra, f"CSV read outside cli/_sources.py read_csv_frame: {sorted(extra)}"


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


def test_the_choke_point_reads_through_the_engine() -> None:
    source = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    sites = call_sites(source, qualified_match=_owns_csv, qualified_scopes=False)
    assert [scope for _l, scope in sites] == ["read_csv_frame"]


@pytest.mark.parametrize(
    "source",
    [
        "import pandas as pd\ndef f(p):\n    return pd.read_csv(p)\n",
        "import pandas\ndef f(p):\n    return pandas.read_csv(p)\n",
        "from pandas import read_csv\ndef f(p):\n    return read_csv(p)\n",
        "from pandas import read_csv as rc\ndef f(p):\n    return rc(p)\n",
        "import pyarrow.csv as pacsv\ndef f(p):\n    return pacsv.read_csv(p)\n",
        "from pyarrow.csv import read_csv\ndef f(p):\n    return read_csv(p)\n",
        "import pandas as pd\ndef f(p):\n    return pd.read_table(p)\n",
        "import pandas as pd\ndef f(p):\n    return pd.read_fwf(p)\n",
        "from pandas import read_fwf\ndef f(p):\n    return read_fwf(p)\n",
        "import decoy_engine as de\ndef f(p, d):\n    return de.read_csv_source(p, d, table='t')\n",
        "import pandas as pd\ndef f(p):\n    return pd.read_parquet(p)\n",
        "import polars as pl\ndef f(p):\n    return pl.read_parquet(p)\n",
        "import polars as pl\ndef f(p):\n    return pl.scan_csv(p)\n",
        "import pyarrow.dataset as ds\ndef f(p):\n    return ds.dataset(p)\n",
        "import pyarrow.parquet.core as core\ndef f(p):\n    return core.read_table(p)\n",
        "import pandas\ndef f(p):\n    return pandas.read_json(p)\n",
        "import pyarrow.parquet as pq\ndef f(p):\n    return pq.read_table(p)\n",
        "import pyarrow.parquet\ndef f(p):\n    return pyarrow.parquet.read_table(p)\n",
        "from pyarrow import parquet\ndef f(p):\n    return parquet.read_table(p)\n",
        "import pyarrow.parquet as pq\ndef f(p):\n    return pq.ParquetFile(p)\n",
        "from decoy_engine import read_fixed_width\ndef f(p, lay):\n    return read_fixed_width(p, lay)\n",
    ],
)
def test_walk_sees_each_spelling(source: str) -> None:
    assert [scope for _l, scope in read_sites(source)] == ["f"]


def test_walk_ignores_lookalikes() -> None:
    src = "def f(p, reader):\n    return reader.read_csv(p)\n"
    assert read_sites(src) == []


def test_parquet_reads_are_hits() -> None:
    src = "import pyarrow.parquet as pq\ndef f(p):\n    return pq.read_table(p)\n"
    assert [scope for _l, scope in read_sites(src)] == ["f"]


def test_seeded_bypass_is_red(tmp_path: Path) -> None:
    pkg = tmp_path / "cli"
    pkg.mkdir()
    (pkg / "sneaky.py").write_text(
        "import pandas as pd\ndef load(p):\n    return pd.read_csv(p)\n", encoding="utf-8"
    )
    assert _tally(tmp_path) == {("cli/sneaky.py", "load"): 1}
    (pkg / "sneaky2.py").write_text(
        "import pandas as pd\ndef load(p):\n    return pd.read_table(p), pd.read_fwf(p)\n",
        encoding="utf-8",
    )
    assert _tally(tmp_path)[("cli/sneaky2.py", "load")] == 2
    (pkg / "sneaky3.py").write_text(
        "import pyarrow.csv as pacsv\ndef load(p):\n    return pacsv.read_csv(p)\n",
        encoding="utf-8",
    )
    assert _tally(tmp_path)[("cli/sneaky3.py", "load")] == 1
    (pkg / "sneaky4.py").write_text(
        "import pandas as pd\ndef load(p):\n    return pd.read_parquet(p)\n", encoding="utf-8"
    )
    assert _tally(tmp_path)[("cli/sneaky4.py", "load")] == 1
