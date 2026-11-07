"""G-ONE-CSV-READ: a declared CSV source is read through `_sources.read_csv_frame` only.

Walks the syntax tree of every module under `src/decoy/` for calls to `read_csv` (pandas, in
any spelling: `pd.read_csv`, `from pandas import read_csv`, an `import ... as` alias) and
`read_csv_source` (the engine reader). A call outside `cli/_sources.py` fails unless its
(file, enclosing function) is in ALLOWLIST with the exact recorded site count. The allowlisted
readers read files the CLI wrote itself or that a caller named with their own flags, not a
declared source. The baseline may shrink and never grow
(tests/sentry/baselines/csv-read-allow.json, checked by scripts/dev/ratchet_check.py).

Named limits of a syntax walk: a call through a runtime-bound name (`getattr(pd, "read_csv")`),
an alias by assignment (`rc = pd.read_csv; rc(p)`), and `from pandas import *`.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "cli/_sources.py"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "csv-read-allow.json"
_WATCHED = {"read_csv", "read_csv_source"}


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
        "cli/report.py",
        "_load",
        1,
        "Reads CLI-written masked files; CLI-FMT Part B moves it to the format dispatch.",
    ),
    AllowedRead(
        "cli/scan.py",
        "_load_csv_with_sampling",
        4,
        "A caller-named file with its own sampling flags; not a declared source.",
    ),
    AllowedRead(
        "cli/tokenize.py",
        "detokenize",
        1,
        "Reads the CLI-written tokenized file; CLI-FMT Part B owns its format.",
    ),
    AllowedRead(
        "cli/unmask.py",
        "unmask",
        1,
        "Reads the CLI-written masked file; CLI-FMT Part B owns its format.",
    ),
)


def _imports(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return (names bound to a watched member, names bound to a module that has one)."""
    members: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in _WATCHED:
                    members.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                modules.add(a.asname or a.name.split(".")[0])
    return members, modules


def read_sites(source: str) -> list[tuple[int, str]]:
    """Return (line, enclosing function or '<module>') for each watched call."""
    tree = ast.parse(source)
    members, modules = _imports(tree)
    found: list[tuple[int, str]] = []

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            )
            if isinstance(child, ast.Call):
                fn = child.func
                if isinstance(fn, ast.Name) and fn.id in members:
                    found.append((child.lineno, scope))
                elif (
                    isinstance(fn, ast.Attribute)
                    and fn.attr in _WATCHED
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id in modules
                ):
                    found.append((child.lineno, scope))
            visit(child, inner)

    visit(tree, "<module>")
    return found


def _tally(root: Path) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel == CHOKE_POINT:
            continue
        for _line, scope in read_sites(path.read_text(encoding="utf-8")):
            counts[(rel, scope)] = counts.get((rel, scope), 0) + 1
    return counts


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
    sites = read_sites((SRC / CHOKE_POINT).read_text(encoding="utf-8"))
    assert [scope for _l, scope in sites] == ["read_csv_frame"]


@pytest.mark.parametrize(
    "source",
    [
        "import pandas as pd\ndef f(p):\n    return pd.read_csv(p)\n",
        "import pandas\ndef f(p):\n    return pandas.read_csv(p)\n",
        "from pandas import read_csv\ndef f(p):\n    return read_csv(p)\n",
        "from pandas import read_csv as rc\ndef f(p):\n    return rc(p)\n",
        "import decoy_engine as de\ndef f(p, d):\n    return de.read_csv_source(p, d, table='t')\n",
    ],
)
def test_walk_sees_each_spelling(source: str) -> None:
    assert [scope for _l, scope in read_sites(source)] == ["f"]


def test_walk_ignores_lookalikes() -> None:
    src = "def f(p, reader):\n    return reader.read_csv(p)\n"
    assert read_sites(src) == []


def test_seeded_bypass_is_red(tmp_path: Path) -> None:
    pkg = tmp_path / "cli"
    pkg.mkdir()
    (pkg / "sneaky.py").write_text(
        "import pandas as pd\ndef load(p):\n    return pd.read_csv(p)\n", encoding="utf-8"
    )
    assert _tally(tmp_path) == {("cli/sneaky.py", "load"): 1}
