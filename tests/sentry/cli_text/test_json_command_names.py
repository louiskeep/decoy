"""AT-S3: every ``--json`` envelope ``command`` value names a command the user can type.

A literal copied from an old mount point (``"compile explain"`` after the command moved under
``validate``) stays wrong with no test noticing. This reads the Click tree at test time and
checks, by AST over ``src/decoy/cli/**``, every string that becomes an envelope ``command``:

* dict literals with the key ``"command"``;
* subscript assignments ``envelope["command"] = "..."``;
* the call-site literals of the named forwarders in ``FORWARDERS`` (a helper that takes the
  command name as an argument and puts it in the envelope).

A value is valid when its longest prefix that is a visible Click path (with or without a leading
``decoy``) is followed by nothing, or, for ``list`` and ``show`` only, by one kind from that
command's own registry. Hidden paths (``scan _scan``, ``validate _gate``) do not count. A
non-literal at any other site fails; ``FORWARDERS`` is the only escape.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import typer.main

from decoy.__main__ import app
from decoy.cli.reference import _LIST_KINDS, _SHOW_KINDS

CLI_DIR = Path(__file__).resolve().parents[3] / "src" / "decoy" / "cli"

# (file relative to CLI_DIR, function, parameter name, parameter index) of helpers that put an
# argument into the envelope `command`. Each call site must pass a literal; the helper's own
# `{"command": <param>}` is then not a violation.
FORWARDERS: dict[tuple[str, str], tuple[str, int]] = {
    ("report.py", "_load_manifest"): ("command", 2),
    ("scan.py", "_emit_load_error"): ("command_name", 3),
    ("reference.py", "_reject_kind"): ("verb", 99),
}

KIND_REGISTRIES = {"list": set(_LIST_KINDS), "show": set(_SHOW_KINDS)}


def _visible_paths() -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()

    def walk(cmd: object, prefix: tuple[str, ...]) -> None:
        for name, sub in getattr(cmd, "commands", {}).items():
            if getattr(sub, "hidden", False):
                continue
            paths.add((*prefix, name))
            walk(sub, (*prefix, name))

    walk(typer.main.get_command(app), ())
    return paths


def is_valid(value: str, paths: set[tuple[str, ...]]) -> bool:
    tokens = value.split()
    if tokens[:1] == ["decoy"]:
        tokens = tokens[1:]
    for cut in range(len(tokens), 0, -1):
        if tuple(tokens[:cut]) in paths:
            rest = tokens[cut:]
            if not rest:
                return True
            registry = KIND_REGISTRIES.get(tokens[cut - 1]) if cut == 1 else None
            return registry is not None and len(rest) == 1 and rest[0] in registry
    return False


def _is_command_key(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "command"


class _Collector(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.sites: list[tuple[int, ast.expr]] = []  # (line, value) envelope values
        self.calls: list[ast.Call] = []

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if _is_command_key(key):
                self.sites.append((node.lineno, value))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript) and _is_command_key(target.slice):
                self.sites.append((node.lineno, node.value))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)


def _forwarder_for(rel: str, func: str) -> str | None:
    for (frel, ffunc), (param, _idx) in FORWARDERS.items():
        if frel == rel and ffunc == func:
            return param
    return None


def _call_name(call: ast.Call) -> str | None:
    fn = call.func
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None


def collect() -> tuple[list[tuple[str, int, str]], list[str]]:
    """Return ((file, line, literal) values to validate, problems that are not value errors)."""
    values: list[tuple[str, int, str]] = []
    problems: list[str] = []
    forwarder_funcs = {ffunc: (frel, p) for (frel, ffunc), p in FORWARDERS.items()}
    for path in sorted(CLI_DIR.rglob("*.py")):
        rel = path.relative_to(CLI_DIR).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        col = _Collector(rel)
        col.visit(tree)
        # Enclosing function per site, found by line span.
        spans = [
            (n.lineno, n.end_lineno or n.lineno, n.name)
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
        ]
        for line, value in col.sites:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values.append((rel, line, value.value))
                continue
            encl = [s for s in spans if s[0] <= line <= s[1]]
            inner = min(encl, key=lambda s: s[1] - s[0]) if encl else None
            param = _forwarder_for(rel, inner[2]) if inner else None
            if param and isinstance(value, ast.Name) and value.id == param:
                continue
            problems.append(f"{rel}:{line}: envelope command is not a string literal")
        # Call sites of forwarders defined in this file.
        for call in col.calls:
            name = _call_name(call)
            if name not in forwarder_funcs or forwarder_funcs[name][0] != rel:
                continue
            param, idx = FORWARDERS[(rel, name)]
            arg = next((k.value for k in call.keywords if k.arg == param), None)
            if arg is None and len(call.args) > idx:
                arg = call.args[idx]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                values.append((rel, call.lineno, arg.value))
            else:
                problems.append(f"{rel}:{call.lineno}: forwarder {name} gets a non-literal")
    return values, problems


def test_envelope_command_values_are_typeable() -> None:
    paths = _visible_paths()
    values, problems = collect()
    bad = [f"{r}:{n}: {v!r}" for r, n, v in values if not is_valid(v, paths)]
    assert problems == [] and bad == []


def test_collector_sees_the_known_sites() -> None:
    values, _ = collect()
    seen = {v for _, _, v in values}
    assert {"validate", "report fidelity", "report render", "init", "run"} <= seen


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("validate compile", True),
        ("decoy validate preflight", True),
        ("list templates", True),
        ("show schema", True),
        ("compile explain", False),
        ("preflight", False),
        ("scan templates", False),
        ("templates", False),
        ("scan _scan", False),
        ("validate _gate", False),
        ("validate compile extra", False),
    ],
)
def test_validator_bites(value: str, ok: bool) -> None:
    assert is_valid(value, _visible_paths()) is ok
