"""G-ONE-CSV-FRAME and G-ONE-NULL-RATE: two GEN-FIT-SHAPE choke points, checked on the syntax tree.

1. Arrow to CSV goes through `io/_targets.py::_csv_frame`. A bare `to_pandas()` widens an integer
   column that holds a null to float64, so a CSV cell prints `23.0`. The scan flags a `to_csv`
   call whose receiver is a `to_pandas(...)` call, and a `to_csv` on a local name that the same
   function bound from a `to_pandas(...)` call.
2. A null rate comes from the engine's `snapshot_null_fraction`. The scan flags a division in a
   statement that reads `null_count` or `non_null_count`, so the CLI never keeps a second ratio
   (and its own zero-row rule).

Named limits of a syntax walk: a conversion through an alias by assignment, a call through
`getattr`, and a count held under a different name.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
_COUNT_NAMES = {"null_count", "non_null_count"}


def _to_pandas_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_pandas"
    )


def _scopes(tree: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = [tree]
    found += [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return found


def csv_bypass_lines(source: str) -> list[int]:
    """Lines of a `to_csv` fed by an Arrow `to_pandas()` conversion, direct or by a local name."""
    tree = ast.parse(source)
    lines: set[int] = set()
    for scope in _scopes(tree):
        nodes = [n for n in ast.walk(scope)]
        bound = {
            t.id
            for n in nodes
            if isinstance(n, ast.Assign) and _to_pandas_call(n.value)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        for n in nodes:
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            if n.func.attr != "to_csv":
                continue
            recv = n.func.value
            if _to_pandas_call(recv) or (isinstance(recv, ast.Name) and recv.id in bound):
                lines.add(n.lineno)
    return sorted(lines)


def _reads_count(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in _COUNT_NAMES:
            return True
        if isinstance(n, ast.Attribute) and n.attr in _COUNT_NAMES:
            return True
        if isinstance(n, ast.Constant) and n.value in _COUNT_NAMES:
            return True
    return False


def null_rate_division_lines(source: str) -> list[int]:
    """Lines of a division inside a statement or function that reads a null-count field."""
    tree = ast.parse(source)
    lines: set[int] = set()
    for scope in _scopes(tree):
        if isinstance(scope, ast.Module):
            continue
        if not _reads_count(scope):
            continue
        for n in ast.walk(scope):
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv)):
                lines.add(n.lineno)
            if isinstance(n, ast.AugAssign) and isinstance(n.op, (ast.Div, ast.FloorDiv)):
                lines.add(n.lineno)
    return sorted(lines)


def _sites(finder) -> list[str]:
    hits: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        hits += [f"{path.relative_to(SRC)}:{n}" for n in finder(path.read_text(encoding="utf-8"))]
    return hits


def test_no_arrow_to_csv_bypasses_csv_frame() -> None:
    assert _sites(csv_bypass_lines) == []


def test_no_direct_null_rate_division() -> None:
    assert _sites(null_rate_division_lines) == []


def test_csv_frame_is_the_conversion_both_writers_use() -> None:
    text = (SRC / "cli" / "io" / "_targets.py").read_text(encoding="utf-8")
    assert text.count("_csv_frame(") >= 3  # the definition and both writers


def test_seeded_direct_arrow_to_csv_is_detected() -> None:
    direct = "def w(t, p):\n    t.to_pandas().to_csv(p)\n"
    by_name = "def w(t, p):\n    frame = t.to_pandas()\n    frame.to_csv(p)\n"
    clean = "def w(t, p):\n    _csv_frame(t).to_csv(p)\n    pd_frame.to_csv(p)\n"
    assert csv_bypass_lines(direct) == [2]
    assert csv_bypass_lines(by_name) == [3]
    assert csv_bypass_lines(clean) == []


def test_seeded_direct_null_rate_division_is_detected() -> None:
    seeded = (
        "def rate(col):\n"
        "    return col['null_count'] / (col['null_count'] + col['non_null_count'])\n"
    )
    attr = "def rate(c):\n    return c.null_count / c.row_count\n"
    clean = "def rate(col):\n    return snapshot_null_fraction(col)\n"
    unrelated = "def mean(xs):\n    return sum(xs) / len(xs)\n"
    assert null_rate_division_lines(seeded) == [2]
    assert null_rate_division_lines(attr) == [2]
    assert null_rate_division_lines(clean) == []
    assert null_rate_division_lines(unrelated) == []
