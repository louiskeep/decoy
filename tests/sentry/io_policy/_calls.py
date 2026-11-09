"""One normalized call scanner for the I/O policy sentries (stdlib `ast` only).

Shared by G-ONE-CSV-READ (`tests/sentry/test_csv_read_choke_point.py`), G-ONE-TARGET-WRITE
(`test_target_writes.py`), G-ONE-PRIVATE-FILE (`test_private_files.py`) and the mask-secret
admission derivation, so import normalization lives in one place. `sites` is the single
traversal: it returns normalized records (node, resolved name, qualified scope, bindings and the
ancestor path as `(node, child_field)` pairs). `call_sites` and `call_contexts` are projections.

A reference is resolved to a dotted name only when it starts at a bound import: `pq.write_table`,
`pyarrow.parquet.write_table` after `import pyarrow.parquet`, and `parquet.write_table` after
`from pyarrow import parquet` all resolve to `pyarrow.parquet.write_table`. A receiver that is
not a bound import (a local, `self`, a call result) resolves to nothing. A watched member is
reported wherever it is named, called or passed as a value (`pool.submit(pq.write_table, ...)`,
`functools.partial(...)`). Scopes are qualified names (`Class.method`, `outer.inner`), and an
import binds only inside the module, function or class that makes it (and what it contains).

Named limits: a relative import (`from . import x`) binds nothing here; ruff TID252
(`ban-relative-imports = "all"`) keeps the repo free of them. A call through a runtime-bound name (`getattr(pd, "read_csv")`), an alias by
assignment (`w = pq.write_table; w(t, p)`), `from x import *`, `exec`, and a local name or
parameter that shadows an import.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Site:
    """One normalized record from the single traversal: a `Name`/`Attribute` load or a `Call`.

    `scope` is the qualified enclosing function ('<module>' at top level) and `inner` its
    innermost name. `ancestors` is the path from the module down to this node's parent as
    `(node, child_field)` pairs, so a rule can ask "is this call in the `body` of a `Try`" without
    a second walk; it crosses scope boundaries, so use `guards` to stay inside the function.
    `with_names` are the names bound by enclosing `with <call> as name` statements.
    """

    node: ast.Name | ast.Attribute | ast.Call
    scope: str
    inner: str
    bound: Bindings
    chain_part: bool
    with_names: frozenset[str]
    ancestors: tuple[tuple[ast.AST, str], ...]

    @property
    def name(self) -> str | None:
        """Dotted name of the reference (or of a call's callee) from a bound import, else None."""
        return qualified(self.node, self.bound)

    @property
    def lineno(self) -> int:
        return self.node.lineno

    def guards(self) -> tuple[tuple[ast.AST, str], ...]:
        """The ancestors inside the innermost enclosing function, class or lambda."""
        cut = max(
            (i for i, (n, _f) in enumerate(self.ancestors) if isinstance(n, _SCOPES)), default=-1
        )
        return self.ancestors[cut + 1 :]


def _children(node: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    for field, value in ast.iter_fields(node):
        if isinstance(value, ast.AST):
            yield field, value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    yield field, item


def _opens(item: ast.withitem, with_calls: frozenset[str]) -> str | None:
    ctx, var = item.context_expr, item.optional_vars
    if not (isinstance(ctx, ast.Call) and isinstance(var, ast.Name)):
        return None
    callee = ctx.func
    name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
    return var.id if name in with_calls else None


def sites(tree: ast.AST, *, with_calls: frozenset[str] = frozenset()) -> list[Site]:
    """The one traversal: every reference load and every call, in source order, with context."""
    found: list[Site] = []

    def visit(
        node: ast.AST,
        scope: str,
        inner: str,
        bound: Bindings,
        names: frozenset[str],
        path: tuple[tuple[ast.AST, str], ...],
    ) -> None:
        for field, child in _children(node):
            step = (*path, (node, field))
            if isinstance(child, _SCOPES):
                name = getattr(child, "name", "<lambda>")
                qual = name if scope == "<module>" else f"{scope}.{name}"
                visit(child, qual, name, {**bound, **bindings(child)}, frozenset(), step)
                continue
            inner_names = names
            if isinstance(child, (ast.With, ast.AsyncWith)):
                inner_names = names | {n for n in (_opens(i, with_calls) for i in child.items) if n}
            is_ref = isinstance(child, (ast.Name, ast.Attribute)) and isinstance(
                child.ctx, ast.Load
            )
            if is_ref or isinstance(child, ast.Call):
                chain = isinstance(node, ast.Attribute) and child is node.value
                found.append(Site(child, scope, inner, bound, chain, names, step))  # type: ignore[arg-type]
            visit(child, scope, inner, bound, inner_names, step)

    visit(tree, "<module>", "<module>", bindings(tree), frozenset(), ())
    return found


def call_sites(
    source: str,
    *,
    qualified_match: Callable[[str, str], bool],
    method_names: frozenset[str] = frozenset(),
    qualified_scopes: bool = True,
) -> list[tuple[int, str]]:
    """Return (line, qualified enclosing function or '<module>') for each matching reference.

    A projection of `sites`. A reference matches when `qualified_match(module, name)` accepts its
    dotted name, or when its attribute name is in `method_names` on any receiver.
    `qualified_scopes=False` reports the innermost function name only (the read sentry's baseline
    keys are recorded that way).
    """
    return [
        (s.lineno, s.scope if qualified_scopes else s.inner)
        for s in sites(ast.parse(source))
        if isinstance(s.node, (ast.Name, ast.Attribute))
        and _hit(s.node, s.bound, qualified_match, method_names, s.chain_part)
    ]


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

    A projection of `sites`. Matches a call's callee with the same resolution as `call_sites`. A
    `with` binds its name for its own body only, and nested `with` statements add to the set.
    """
    return [
        (s.node, s.scope, s.with_names)
        for s in sites(ast.parse(source), with_calls=with_calls)
        if isinstance(s.node, ast.Call)
        and isinstance(s.node.func, (ast.Name, ast.Attribute))
        and _hit(s.node.func, s.bound, qualified_match, method_names, False)
    ]


# Where a watched write call takes its path: (positional index, keyword), keyed by the call's
# last name or resolved dotted name. `None` means the path is the receiver (`p.write_text(...)`).
PATH_SLOT: dict[str, tuple[int, str] | None] = {
    "os.open": (0, "path"),
    "sqlite3.connect": (0, "database"),
    "duckdb.connect": (0, "database"),
    "open": (0, "file"),
    "write_table": (1, "where"),
    "to_csv": (0, "path_or_buf"),
    "to_parquet": (0, "path"),
    "ParquetWriter": (0, "where"),
    "write_fixed_width": (2, "path"),
    "write_text": None,
    "write_bytes": None,
}


def path_arg(call: ast.Call, member: str) -> ast.expr | None:
    """The expression a call passes as its path, or None for a receiver path or no such arg."""
    slot = PATH_SLOT.get(member)
    if slot is None:
        return None
    index, keyword = slot
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return call.args[index] if len(call.args) > index else None


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
