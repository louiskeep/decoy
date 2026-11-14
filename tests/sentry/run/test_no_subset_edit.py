"""G-NO-SUBSET-EDIT: the CLI never edits a config's `subset` block, and `run/` names no subset type.

`--no-subset` is `run_pipeline(subset_request="skip")`. A CLI that stripped the key instead would
change what the engine hashes and stamps. The scan fails on, anywhere under `src/decoy`:
a store, delete or `pop`/`setdefault`/`update` of the key "subset", a dict display or a
`dict(..., subset=...)` call that sets it, and a dict comprehension that filters it out. The one
exemption is the `--json` output dict, by file and function (`cli/run/_render.py`, `finish`).
It also fails when a module under `cli/run/` names `SubsetError`, `SubsetBudgetExceededError` or another `Subset*Error`: a subset failure keeps the generic exit map (exit 3).

Mutation: `config.pop("subset", None)` in `_execute.py`, or `except SubsetError` in `_errors.py`.
Named limit: a key built at run time is invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
KEY = "subset"
_EDITS = {"pop", "setdefault", "update"}


def _is_key(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == KEY


# The one store of the key that is not a config edit: `--json` output, in `finish`.
OUTPUT_OWNER = ("cli/run/_render.py", "finish")


def _filters_key(node: ast.DictComp) -> bool:
    """A dict comprehension with a condition that names the key: `... if k != "subset"`."""
    return any(
        _is_key(const) for gen in node.generators for cond in gen.ifs for const in ast.walk(cond)
    )


def key_edits(source: str, rel: str) -> list[str]:
    found: list[str] = []

    def walk(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            )
            line = getattr(child, "lineno", 0)
            if isinstance(child, ast.Subscript) and _is_key(child.slice):
                if isinstance(child.ctx, (ast.Store, ast.Del)) and (rel, scope) != OUTPUT_OWNER:
                    found.append(f"{rel}:{line}: store or delete of ['subset']")
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr in _EDITS and child.args and _is_key(child.args[0]):
                    found.append(f"{rel}:{line}: .{child.func.attr}('subset')")
            if isinstance(child, ast.Call) and any(k.arg == KEY for k in child.keywords):
                found.append(f"{rel}:{line}: call with subset=... keyword")
            elif isinstance(child, ast.Dict) and any(_is_key(k) for k in child.keys):
                found.append(f"{rel}:{line}: dict display with a 'subset' key")
            elif isinstance(child, ast.DictComp) and _filters_key(child):
                found.append(f"{rel}:{line}: dict comprehension that filters the 'subset' key")
            walk(child, inner)

    walk(ast.parse(source), "")
    return found


def subset_type_names(source: str, rel: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        name = (
            node.id
            if isinstance(node, ast.Name)
            else node.attr
            if isinstance(node, ast.Attribute)
            else node.name
            if isinstance(node, ast.alias)
            else ""
        )
        if name.startswith("Subset") and name.endswith("Error"):
            found.append(f"{rel}:{getattr(node, 'lineno', 0)}: {name}")
    return found


def _scan() -> tuple[list[str], list[str]]:
    edits: list[str] = []
    names: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        text = path.read_text(encoding="utf-8")
        edits += key_edits(text, rel)
        if rel.startswith("cli/run/"):
            names += subset_type_names(text, rel)
    return edits, names


def test_cli_never_edits_the_subset_key() -> None:
    edits, _ = _scan()
    assert edits == []


def test_run_package_names_no_subset_error_type() -> None:
    _, names = _scan()
    assert names == []


def test_the_scan_sees_each_planted_edit() -> None:
    assert key_edits('cfg["subset"] = None', "x.py")
    assert key_edits('del cfg["subset"]', "x.py")
    assert key_edits('payload["subset"] = m', "x.py")
    assert key_edits('payload["subset"] = m', "cli/run/_render.py")
    assert not key_edits('def finish(ctx):\n    payload["subset"] = m', "cli/run/_render.py")
    assert key_edits('{k: v for k, v in cfg.items() if k != "subset"}', "x.py")
    assert key_edits("dict(cfg, subset=None)", "x.py")
    assert key_edits("dict(**cfg, subset=None)", "x.py")
    assert key_edits('cfg.pop("subset", None)', "x.py")
    assert key_edits('x = {**cfg, "subset": None}', "x.py")
    assert not key_edits('x = cfg.get("subset")', "x.py")
    assert subset_type_names("from e import SubsetError", "cli/run/x.py")
    assert subset_type_names(
        "try:\n    pass\nexcept e.SubsetBudgetExceededError:\n    pass", "cli/run/x.py"
    )
