"""Scanner for the exit-code owner sentry: code that maps exception types to exit codes.

`decoy.cli.exit_codes.exit_code_for` is the one map from an exception to an exit code. A second
map drifts: `decoy demo` once sent two exception types to exit 1 and everything else to 3 while
`decoy run` sent twenty. A site is a function (keyed `path::function`, path relative to
`src/decoy`) holding one of three shapes, each choosing an exit by exception type:

* an `if` or conditional expression that names an `EXIT_*` constant and tests an exception, by
  `isinstance(exc, ...)` or by reading the name an enclosing `except ... as name` binds;
* a dict literal whose keys are exception classes and whose values are `EXIT_*` constants.

`exit_codes.py` is the owner and is not scanned. Named limits: a map built from a list of
tuples, an exit looked up through a variable, and a handler that picks an exit by `exc.code`
alone.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
OWNER = "cli/exit_codes.py"
# Parameter and local names that hold an exception outside an `except ... as` clause.
_EXC_NAMES = frozenset({"exc", "e", "err", "error", "exception"})


def _exit_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id.startswith("EXIT_"):
            names.add(n.id)
        elif isinstance(n, ast.Attribute) and n.attr.startswith("EXIT_"):
            names.add(n.attr)
    return names


def _tests_an_exception(test: ast.AST, caught: frozenset[str]) -> bool:
    for n in ast.walk(test):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "isinstance":
            first = n.args[0] if n.args else None
            if isinstance(first, ast.Name) and (first.id in caught or first.id in _EXC_NAMES):
                return True
        if isinstance(n, ast.Name) and n.id in caught:
            return True
    return False


def _is_exception_class(node: ast.AST) -> bool:
    name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
    return name.endswith(("Error", "Exception", "Exit")) or name == "MemoryError"


def _scope_nodes(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    scopes: list[tuple[str, ast.AST]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}.{child.name}" if prefix else child.name
                scopes.append((qual, child))
                walk(child, qual)
            else:
                walk(child, prefix)

    walk(tree, "")
    return scopes


def _is_map_site(node: ast.AST, caught: frozenset[str]) -> bool:
    if isinstance(node, (ast.If, ast.IfExp)):
        return _tests_an_exception(node.test, caught) and bool(_exit_names(node))
    if isinstance(node, ast.Dict):
        pairs = [(k, v) for k, v in zip(node.keys, node.values) if k is not None]
        return any(
            _exit_names(v)
            and (
                _is_exception_class(k)
                or (isinstance(k, ast.Tuple) and any(_is_exception_class(e) for e in k.elts))
            )
            for k, v in pairs
        )
    return False


def _map_sites_in(scope: ast.AST) -> bool:
    """Whether the scope holds a map shape, tracking the names its `except` clauses bind."""

    def visit(node: ast.AST, caught: frozenset[str]) -> bool:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            inner = caught
            if isinstance(child, ast.ExceptHandler) and child.name:
                inner = caught | {child.name}
            if _is_map_site(child, inner) or visit(child, inner):
                return True
        return False

    return visit(scope, frozenset())


def sites_in_source(source: str, rel: str) -> set[str]:
    """The `path::function` keys of every exception-to-exit map in one file."""
    tree = ast.parse(source)
    keys: set[str] = set()
    for qual, scope in _scope_nodes(tree):
        if isinstance(scope, ast.ClassDef):
            continue
        if _map_sites_in(scope):
            keys.add(f"{rel}::{qual}")
    return keys


def inventory(src: Path = SRC) -> set[str]:
    keys: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        if rel != OWNER and "__pycache__" not in path.parts:
            keys |= sites_in_source(path.read_text(encoding="utf-8"), rel)
    return keys
