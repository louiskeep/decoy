"""Exclusivity checks for the value-free boundary, as reusable pure functions.

Each check takes module source text and returns a list of violations, so the same
functions run against the real modules (must be empty) and against seeded
evasions (must be non-empty). That pairing is what makes the sentry non-vacuous.

These are allowlists, not spelling denylists: a command or projection module may
import only what is listed, may not touch any I/O-capable builtin or attribute,
and may hand `Surface.emit` only a pure renderer.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping

# --- imports -------------------------------------------------------------------------------------

PURE_IMPORTS = frozenset(
    {
        "__future__",
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "difflib",
        "enum",
        "math",
        "re",
        "typing",
        "decoy.cli._value_free",
    }
)
COMMAND_IMPORTS = PURE_IMPORTS | {
    "pathlib",
    "json",
    "typer",
    "yaml",
    "pandas",
    "decoy.cli._boundary",
    "decoy.cli._projections",
    "decoy.cli.exit_codes",
    "decoy.cli._default_group",
}
ENGINE_PREFIX = "decoy_engine"

# --- names and attributes ------------------------------------------------------------------------

FORBIDDEN_NAMES = frozenset(
    {
        "open", "print", "input", "eval", "exec", "compile", "__import__", "getattr",
        "setattr", "delattr", "globals", "locals", "vars", "repr", "ascii", "breakpoint",
        "exit", "quit", "help", "memoryview", "__builtins__",
        "_MINT", "_mint_str", "_FRAGMENT", "_CONTAINMENT", "_ACTIVE",
    }
)  # fmt: skip
# Constructors only the boundary may call.
FORBIDDEN_CALLS = frozenset(
    {"Surface", "Printer", "Fragment", "SafeStr", "Projection", "OutputState", "Console"}
)
FORBIDDEN_ATTRS = frozenset(
    {
        # file / stream writes
        "open", "write", "write_text", "write_bytes", "writelines", "print", "echo", "secho",
        "touch", "mkdir", "unlink", "rename", "replace", "chmod", "symlink_to",
        "hardlink_to", "rmdir", "fdopen", "dup2",
        # serializers that write or hand raw objects out
        "dump", "dumps", "safe_dump", "to_csv", "to_parquet", "to_json", "to_excel",
        "to_pickle", "to_feather", "to_hdf", "to_sql", "to_html", "to_latex", "to_markdown",
        "to_clipboard", "to_stata", "to_orc", "to_xml",
        # stream and boundary internals
        "console", "err_console", "stdout", "stderr", "stdin", "state", "mint_str",
    }
)  # fmt: skip
COMMAND_ONLY_FORBIDDEN_ATTRS = frozenset({"mint"})


def _module_of(node: ast.ImportFrom) -> str:
    return node.module or ""


def import_violations(tree: ast.Module, allowed: frozenset[str]) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = _module_of(node)
            if node.level:
                names = [f"<relative>.{mod}"]
            elif mod == "decoy.cli":
                names = [f"decoy.cli.{a.name}" for a in node.names]
            else:
                names = [mod]
            for a in node.names:
                if a.name in FORBIDDEN_NAMES or a.name in FORBIDDEN_ATTRS:
                    hits.append(f"{node.lineno}: import name {a.name}")
        for name in names:
            if name == ENGINE_PREFIX or name.startswith(ENGINE_PREFIX + "."):
                continue
            if name not in allowed:
                hits.append(f"{node.lineno}: import {name}")
    return hits


def capability_violations(tree: ast.Module, *, command: bool) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            hits.append(f"{node.lineno}: name {node.id}")
        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr in FORBIDDEN_ATTRS or (command and attr in COMMAND_ONLY_FORBIDDEN_ATTRS):
                hits.append(f"{node.lineno}: .{attr}")
            # Private/dunder attributes are boundary internals, except a class's own state.
            elif attr.startswith("_") and not (
                isinstance(node.value, ast.Name) and node.value.id == "self"
            ):
                hits.append(f"{node.lineno}: .{attr}")
        if isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if fname in FORBIDDEN_CALLS:
                hits.append(f"{node.lineno}: constructs {fname}")
    return hits


def module_violations(source: str, *, command: bool) -> list[str]:
    tree = ast.parse(source)
    allowed = COMMAND_IMPORTS if command else PURE_IMPORTS
    return import_violations(tree, allowed) + capability_violations(tree, command=command)


# --- the one raw-artifact call site --------------------------------------------------------------


def saved_scan_call_sites(sources: Mapping[str, str]) -> list[tuple[str, int]]:
    sites = []
    for name, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            # Any reference counts, called or not: an alias is a second call site.
            if isinstance(node, ast.Attribute) and node.attr == "write_saved_scan":
                sites.append((name, node.lineno))
            if isinstance(node, ast.Name) and node.id == "write_saved_scan":
                sites.append((name, node.lineno))
            if isinstance(node, ast.Constant) and node.value == "write_saved_scan":
                sites.append((name, node.lineno))
    return sites


# --- pure renderers ------------------------------------------------------------------------------

PRINTER_METHODS = frozenset({"t", "cat", "join", "line", "table", "card"})
DATA_METHODS = frozenset({"get", "items", "keys", "values", "append"})
SAFE_BUILTINS = frozenset(
    {
        "len", "isinstance", "int", "float", "any", "all", "sorted", "enumerate", "range",
        "zip", "min", "max", "sum", "bool", "abs", "round", "list", "tuple",
    }
)  # fmt: skip
_BANNED_NODES = (
    ast.Global,
    ast.Nonlocal,
    ast.Lambda,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.JoinedStr,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Import,
    ast.ImportFrom,
)


def _is_str_const(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is str


def _is_literal_choice(node: ast.AST) -> bool:
    if _is_str_const(node):
        return True
    return isinstance(node, ast.IfExp) and _is_str_const(node.body) and _is_str_const(node.orelse)


def _body_nodes(fn: ast.FunctionDef) -> Iterable[ast.AST]:
    for stmt in fn.body:
        yield from ast.walk(stmt)


def _printer_call_violations(call: ast.Call, method: str) -> list[str]:
    where = f"{call.lineno}: p.{method}"
    if method in ("t", "join") and not (call.args and _is_str_const(call.args[0])):
        return [f"{where} needs a literal template/separator"]
    if method == "t":
        for kw in call.keywords:
            if kw.arg == "style" and not _is_str_const(kw.value):
                return [f"{where} style must be a literal"]
    if method == "table" and not all(_is_str_const(a) for a in call.args):
        return [f"{where} headers must be literals"]
    if method == "card":
        status = call.args[3] if len(call.args) > 3 else None
        for kw in call.keywords:
            if kw.arg == "status":
                status = kw.value
        if not (call.args and _is_str_const(call.args[0])) or status is None:
            return [f"{where} needs a literal command and status"]
        if not _is_literal_choice(status):
            return [f"{where} status must be literal"]
    return []


def renderer_violations(tree: ast.Module, name: str, seen: set[str] | None = None) -> list[str]:
    """`name` must be a module-level function whose first parameter is `p` and whose
    body only calls `p` methods (literal templates), safe builtins, read-only data
    methods and other functions that pass this same check."""
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    fn = funcs.get(name)
    if fn is None:
        return [f"renderer {name} is not a module-level function"]
    params = [a.arg for a in fn.args.args]
    if not params or params[0] != "p" or fn.args.vararg or fn.args.kwarg or fn.decorator_list:
        return [f"{fn.lineno}: {name} must take the Printer as `p` and nothing variadic"]
    hits: list[str] = []
    local = set(params)
    for node in _body_nodes(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        if isinstance(node, ast.arg):
            local.add(node.arg)
    for node in _body_nodes(fn):
        if isinstance(node, _BANNED_NODES):
            hits.append(f"{node.lineno}: {name} uses {type(node).__name__}")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in local or node.id in SAFE_BUILTINS:
                continue
            if node.id in funcs:
                hits.extend(renderer_violations(tree, node.id, seen))
                continue
            hits.append(f"{node.lineno}: {name} reads non-local {node.id}")
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "p":
                if node.attr not in PRINTER_METHODS:
                    hits.append(f"{node.lineno}: {name} uses p.{node.attr}")
            elif node.attr not in DATA_METHODS:
                hits.append(f"{node.lineno}: {name} uses .{node.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            f = node.func
            if isinstance(f.value, ast.Name) and f.value.id == "p":
                hits.extend(_printer_call_violations(node, f.attr))
    return hits


def emit_renderer_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    hits = []
    found = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "emit":
            continue
        for kw in node.keywords:
            if kw.arg != "render":
                continue
            found += 1
            if not isinstance(kw.value, ast.Name):
                hits.append(f"{node.lineno}: render= must name a module-level function")
                continue
            hits.extend(renderer_violations(tree, kw.value.id))
    return hits if found else ["no emit(render=...) call found"]
