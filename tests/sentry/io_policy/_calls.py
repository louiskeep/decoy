"""One normalized call scanner for the I/O policy sentries (stdlib `ast` only).

Shared by G-ONE-CSV-READ (`tests/sentry/test_csv_read_choke_point.py`) and G-ONE-TARGET-WRITE
(`test_target_writes.py`), so import normalization lives in one place.

A call is resolved to a dotted name only when it starts at a bound import: `pq.write_table`,
`pyarrow.parquet.write_table` after `import pyarrow.parquet`, and `parquet.write_table` after
`from pyarrow import parquet` all resolve to `pyarrow.parquet.write_table`. A receiver that is
not a bound import (a local, `self`, a call result) resolves to nothing.

Named limits: a call through a runtime-bound name (`getattr(pd, "read_csv")`), an alias by
assignment (`w = pq.write_table; w(t, p)`), `from x import *`, and `exec`.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

Bindings = dict[str, str]


def bindings(tree: ast.AST) -> Bindings:
    """Map each local name an import binds to the dotted path it stands for."""
    bound: Bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    bound[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    bound[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                bound[a.asname or a.name] = f"{node.module}.{a.name}"
    return bound


def qualified(call: ast.Call, bound: Bindings) -> str | None:
    """The dotted name of the call target when it starts at a bound name, else None."""
    parts: list[str] = []
    node: ast.expr = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name) or node.id not in bound:
        return None
    return ".".join([bound[node.id], *reversed(parts)])


def call_sites(
    source: str,
    *,
    qualified_match: Callable[[str, str], bool],
    method_names: frozenset[str] = frozenset(),
) -> list[tuple[int, str]]:
    """Return (line, enclosing function or '<module>') for each matching call.

    A call matches when `qualified_match(module, name)` accepts its dotted name, or when its
    attribute name is in `method_names` on any receiver.
    """
    tree = ast.parse(source)
    bound = bindings(tree)
    found: list[tuple[int, str]] = []

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            )
            if isinstance(child, ast.Call) and _hit(child, bound, qualified_match, method_names):
                found.append((child.lineno, scope))
            visit(child, inner)

    visit(tree, "<module>")
    return found


def _hit(
    call: ast.Call,
    bound: Bindings,
    qualified_match: Callable[[str, str], bool],
    method_names: frozenset[str],
) -> bool:
    if isinstance(call.func, ast.Attribute) and call.func.attr in method_names:
        return True
    name = qualified(call, bound)
    if name is None:
        return False
    module, _dot, member = name.rpartition(".")
    return qualified_match(module, member)


def tally(
    root: Path, *, skip: str, finder: Callable[[str], list[tuple[int, str]]]
) -> dict[tuple[str, str], int]:
    """Count matching calls per (file, function) over `root`, skipping the choke-point file."""
    counts: dict[tuple[str, str], int] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel == skip:
            continue
        for _line, scope in finder(path.read_text(encoding="utf-8")):
            counts[(rel, scope)] = counts.get((rel, scope), 0) + 1
    return counts
