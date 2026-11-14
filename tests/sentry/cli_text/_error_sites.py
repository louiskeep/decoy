"""Scanner for the D7 error-site inventory: every place the CLI builds a user-facing error.

Three construction shapes count as one error site each:

- a call to ``*.err_console.print`` (or a bare ``err_console.print``) with a ``error(...)``
  styling call among its arguments, which is the human error line;
- a dict literal holding ``"status": "error"``, which is a hand-built ``--json`` error object;
- ``dict(status="error", ...)``, the same object spelled as a call.

A site is keyed ``path::function::fingerprint`` where ``path`` is relative to ``src/decoy``,
``function`` is the dotted enclosing scope (``<module>`` at module level) and ``fingerprint``
is a short hash of the site's normalized syntax tree. Line numbers and formatting are not part
of the tree, so moving a site does not change its key, but editing its expression does: a
changed legacy error is a gained key, not a silent reuse of the old entry. Two identical
expressions in one function get an ordinal suffix so neither hides the other.

The one owner, ``ui/output.py::emit_error``, is not counted: it is where the rule is built.
A same-named function in any other module is still a site.

Named limits of a syntax walk: an aliased receiver (``err = state.err_console; err.print(...)``)
and an error object assembled key by key are not seen. ``error`` is matched by name, as the
output module exports it.
"""

from __future__ import annotations

import ast
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# The owner builds the one human error line and the one JSON error object, so its own
# constructions are the definition of the rule and not a site of it.
OWNER_PATH = "ui/output.py"
OWNER_SCOPE = "emit_error"
SRC = ROOT / "src" / "decoy"
STYLE_NAME = "error"
CONSOLE_NAME = "err_console"
FINGERPRINT_CHARS = 12


def _is_style_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == STYLE_NAME
    return isinstance(func, ast.Attribute) and func.attr == STYLE_NAME


def _is_err_print(node: ast.Call) -> bool:
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "print"):
        return False
    recv = func.value
    if isinstance(recv, ast.Name):
        return recv.id == CONSOLE_NAME
    return isinstance(recv, ast.Attribute) and recv.attr == CONSOLE_NAME


def _is_status_error(key: ast.expr | None, value: ast.expr) -> bool:
    return (
        isinstance(key, ast.Constant)
        and key.value == "status"
        and isinstance(value, ast.Constant)
        and value.value == "error"
    )


def _is_site(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        if _is_err_print(node) and any(_is_style_call(a) for a in node.args):
            return True
        is_dict_call = isinstance(node.func, ast.Name) and node.func.id == "dict"
        return is_dict_call and any(
            kw.arg == "status" and _is_status_error(ast.Constant("status"), kw.value)
            for kw in node.keywords
        )
    if isinstance(node, ast.Dict):
        return any(_is_status_error(k, v) for k, v in zip(node.keys, node.values, strict=True))
    return False


def _fingerprint(node: ast.AST) -> str:
    digest = hashlib.sha256(ast.dump(node).encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_CHARS]


def _walk(node: ast.AST, scope: str, out: list[tuple[str, str]]) -> None:
    for child in ast.iter_child_nodes(node):
        if _is_site(child):
            out.append((scope, _fingerprint(child)))
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = child.name if scope == "<module>" else f"{scope}.{child.name}"
            _walk(child, name, out)
        else:
            _walk(child, scope, out)


def sites_in_source(source: str, rel: str) -> set[str]:
    """Keys of every error site in one module's source text."""
    found: list[tuple[str, str]] = []
    _walk(ast.parse(source), "<module>", found)
    seen: Counter[tuple[str, str]] = Counter()
    keys = set()
    for scope, fp in found:
        if rel == OWNER_PATH and scope.split(".")[0] == OWNER_SCOPE:
            continue
        ordinal = seen[(scope, fp)]
        seen[(scope, fp)] += 1
        keys.add(f"{rel}::{scope}::{fp}" + (f"#{ordinal}" if ordinal else ""))
    return keys


def inventory(src: Path = SRC) -> set[str]:
    """The exact error-site inventory of every module under ``src``."""
    keys: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        keys |= sites_in_source(path.read_text(encoding="utf-8"), rel)
    return keys


_WHY = (
    "legacy error site recorded when the one error emitter landed; converts to emit_error "
    "and leaves this baseline, never joins it"
)


def reasons() -> dict[str, str]:
    """Baseline source for the registry test and the one-off generator."""
    return {key: _WHY for key in inventory()}


def error_literals(source: str) -> list[ast.Dict | ast.Call]:
    """Every ``"status": "error"`` dict literal and ``dict(status="error", ...)`` call."""
    return [
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.Dict, ast.Call)) and not _is_err_print_site(n) and _is_site(n)
    ]


def _is_err_print_site(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_err_print(node)
