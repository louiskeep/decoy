"""One normalized call scanner for the I/O policy sentries (stdlib `ast` only).

Shared by G-ONE-CSV-READ (`tests/sentry/test_csv_read_choke_point.py`) and G-ONE-TARGET-WRITE
(`test_target_writes.py`), so import normalization lives in one place.

A reference is resolved to a dotted name only when it starts at a bound import: `pq.write_table`,
`pyarrow.parquet.write_table` after `import pyarrow.parquet`, and `parquet.write_table` after
`from pyarrow import parquet` all resolve to `pyarrow.parquet.write_table`. A receiver that is
not a bound import (a local, `self`, a call result) resolves to nothing. A watched member is
reported wherever it is named, called or passed as a value (`pool.submit(pq.write_table, ...)`,
`functools.partial(...)`). Scopes are qualified names (`Class.method`, `outer.inner`), and an
import binds only inside the module, function or class that makes it (and what it contains).

Named limits: a call through a runtime-bound name (`getattr(pd, "read_csv")`), an alias by
assignment (`w = pq.write_table; w(t, p)`), `from x import *`, `exec`, and a local name or
parameter that shadows an import.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

Bindings = dict[str, str]
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def bindings(scope_node: ast.AST) -> Bindings:
    """Map each local name an import in this scope binds to the dotted path it stands for.

    Looks at the scope's own body and does not descend into nested functions or classes.
    """
    bound: Bindings = {}
    stack = list(ast.iter_child_nodes(scope_node))
    while stack:
        node = stack.pop()
        if isinstance(node, _SCOPES):
            continue
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
        stack.extend(ast.iter_child_nodes(node))
    return bound


def qualified(target: ast.expr | ast.Call, bound: Bindings) -> str | None:
    """The dotted name of a Name/Attribute chain (or a call's target) from a bound name."""
    node: ast.expr = target.func if isinstance(target, ast.Call) else target
    parts: list[str] = []
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
    qualified_scopes: bool = True,
) -> list[tuple[int, str]]:
    """Return (line, qualified enclosing function or '<module>') for each matching reference.

    A reference matches when `qualified_match(module, name)` accepts its dotted name, or when
    its attribute name is in `method_names` on any receiver. `qualified_scopes=False` reports the
    innermost function name only (the read sentry's baseline keys are recorded that way).
    """
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []

    def visit(node: ast.AST, scope: str, bound: Bindings, inner_of_chain: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPES):
                name = getattr(child, "name", "<lambda>")
                inner = name if scope == "<module>" or not qualified_scopes else f"{scope}.{name}"
                visit(child, inner, {**bound, **bindings(child)}, False)
                continue
            chain_part = isinstance(node, ast.Attribute) and child is node.value
            if isinstance(child, (ast.Name, ast.Attribute)) and isinstance(child.ctx, ast.Load):
                if _hit(child, bound, qualified_match, method_names, chain_part):
                    found.append((child.lineno, scope))
            visit(child, scope, bound, chain_part)

    visit(tree, "<module>", bindings(tree), False)
    return found


def _hit(
    ref: ast.Name | ast.Attribute,
    bound: Bindings,
    qualified_match: Callable[[str, str], bool],
    method_names: frozenset[str],
    chain_part: bool,
) -> bool:
    if isinstance(ref, ast.Attribute) and ref.attr in method_names:
        return True
    if chain_part:  # only the longest chain is resolved, so a name is not counted twice
        return False
    name = qualified(ref, bound)
    if name is None:
        return False
    module, _dot, member = name.rpartition(".")
    return qualified_match(module, member)


def call_contexts(
    source: str,
    *,
    qualified_match: Callable[[str, str], bool],
    method_names: frozenset[str] = frozenset(),
    with_calls: frozenset[str],
) -> list[tuple[ast.Call, str, frozenset[str]]]:
    """Return (call, qualified scope, names bound by enclosing `with <one of with_calls>(...) as name`).

    Matches a call's callee with the same resolution as `call_sites`. A `with` binds its name
    for its own body only, and nested `with` statements add to the set.
    """
    tree = ast.parse(source)
    found: list[tuple[ast.Call, str, frozenset[str]]] = []

    def opens(item: ast.withitem) -> str | None:
        ctx, var = item.context_expr, item.optional_vars
        if not (isinstance(ctx, ast.Call) and isinstance(var, ast.Name)):
            return None
        callee = ctx.func
        name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
        return var.id if name in with_calls else None

    def visit(node: ast.AST, scope: str, bound: Bindings, names: frozenset[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPES):
                name = getattr(child, "name", "<lambda>")
                inner = name if scope == "<module>" else f"{scope}.{name}"
                visit(child, inner, {**bound, **bindings(child)}, frozenset())
                continue
            inner_names = names
            if isinstance(child, (ast.With, ast.AsyncWith)):
                inner_names = names | {n for n in map(opens, child.items) if n}
            if isinstance(child, ast.Call) and isinstance(child.func, (ast.Name, ast.Attribute)):
                if _hit(child.func, bound, qualified_match, method_names, False):
                    found.append((child, scope, names))
            visit(child, scope, bound, inner_names)

    visit(tree, "<module>", bindings(tree), frozenset())
    return found


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
