"""G-ONE-SAMPLE-REQUEST: rows of a sample are chosen only by the engine's `sample_request`.

Under `src/decoy/` the scan fails on an import of `select_subset`, `run_subset`, `plan_subset` or
`SubsetSelection` (direct, aliased, `from x import y`, or an attribute such as `subset.select_subset`),
on a `sample_request` call outside `cli/run/_sample.py`, and on `.slice(`, `.take(` or `.head(` in
`cli/run/` (a CLI that cut the sources itself would pick rows the engine does not know about).

Mutation: import `select_subset` in `cli/run/_sample.py`.
Named limit: a name built at run time is invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
BANNED = frozenset({"select_subset", "run_subset", "plan_subset", "SubsetSelection"})
BUILDER = "cli/run/_sample.py"
CUTS = frozenset({"slice", "take", "head"})


def findings(source: str, rel: str) -> list[str]:
    out: list[str] = []
    # `decoy subset` is the engine's whole-table subsetter; it never builds a sample.
    banned = BANNED - {"plan_subset", "run_subset"} if rel == "cli/subset.py" else BANNED
    tree = ast.parse(source)
    # Names bound to `sample_request` by `from x import sample_request as y`, and `import x as y`
    # module aliases (their `y.sample_request(...)` call is read through the attribute name).
    request_names = {"sample_request"} | {
        a.asname
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for a in n.names
        if a.name == "sample_request" and a.asname
    }
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.ImportFrom):
            out += [f"{rel}:{line}: imports {a.name}" for a in node.names if a.name in banned]
        elif isinstance(node, ast.Import):
            out += [
                f"{rel}:{line}: imports {a.name}"
                for a in node.names
                if a.name.split(".")[-1] in banned
            ]
        elif isinstance(node, ast.Attribute) and node.attr in banned:
            out.append(f"{rel}:{line}: names {node.attr}")
        elif isinstance(node, ast.Call):
            name = _called(node.func)
            if name in request_names and rel != BUILDER:
                out.append(f"{rel}:{line}: sample_request called outside {BUILDER}")
            if (
                rel.startswith("cli/run/")
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in CUTS
            ):
                out.append(f"{rel}:{line}: .{node.func.attr}( in cli/run/")
    return out


def _called(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def test_the_source_tree_has_no_second_row_chooser() -> None:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        found += findings(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    assert found == []


# One seeded case per covered spelling (AT-C9).
SEEDED = {
    "from decoy_engine.subset import select_subset": "imports select_subset",
    "from decoy_engine.subset import select_subset as pick": "imports select_subset",
    "from decoy_engine.subset import run_subset": "imports run_subset",
    "from decoy_engine.subset import plan_subset": "imports plan_subset",
    "from decoy_engine.subset import SubsetSelection": "imports SubsetSelection",
    "import decoy_engine.subset.select_subset": "imports decoy_engine.subset.select_subset",
    "import decoy_engine.subset as s\ns.select_subset(1)": "names select_subset",
    "from decoy_engine import subset\nsubset.plan_subset(1)": "names plan_subset",
}


def test_each_covered_spelling_is_found() -> None:
    for source, expected in SEEDED.items():
        assert any(expected in f for f in findings(source, BUILDER)), source


def test_sample_request_is_allowed_only_in_the_builder() -> None:
    call = "from decoy_engine.subset import sample_request\nsample_request({}, rows=1)"
    assert findings(call, BUILDER) == []
    assert any("outside" in f for f in findings(call, "cli/run/_execute.py"))
    aliased = "from decoy_engine.subset import sample_request as sr\nsr({}, rows=1)"
    assert any("outside" in f for f in findings(aliased, "cli/run/_execute.py"))
    assert findings(aliased, BUILDER) == []
    attr = "import decoy_engine.subset as s\ns.sample_request({}, rows=1)"
    assert any("outside" in f for f in findings(attr, "cli/other.py"))


def test_cutting_a_source_in_cli_run_is_found() -> None:
    for call in ("ctx.sources['a'].slice(0, 5)", "frame.take([0])", "t.head(3)"):
        assert any("cli/run/" in f for f in findings(call, "cli/run/_execute.py")), call
    assert findings("t.head(3)", "cli/scan.py") == []
