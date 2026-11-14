"""G-NO-SUBSET-EDIT: the CLI never edits a config's `subset` block, and `run/` names no subset type.

`--no-subset` is `run_pipeline(subset_request="skip")`. A CLI that stripped the key instead would
change what the engine hashes and stamps. The scan fails on, anywhere under `src/decoy`:
a store, delete or `pop`/`setdefault`/`update` of the key "subset", and a dict display that
sets it. It also fails when a module under `cli/run/` names `SubsetError`, `SubsetBudgetExceededError`
or another `Subset*Error`: a subset failure keeps the generic exit map (exit 3).

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


def key_edits(source: str, rel: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Subscript) and _is_key(node.slice):
            # `payload["subset"]` is the `--json` output object, not a pipeline config.
            is_output = isinstance(node.value, ast.Name) and node.value.id == "payload"
            if isinstance(node.ctx, (ast.Store, ast.Del)) and not is_output:
                found.append(f"{rel}:{line}: store or delete of ['subset']")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _EDITS and node.args and _is_key(node.args[0]):
                found.append(f"{rel}:{line}: .{node.func.attr}('subset')")
        elif isinstance(node, ast.Dict):
            if any(_is_key(k) for k in node.keys):
                found.append(f"{rel}:{line}: dict display with a 'subset' key")
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
    assert not key_edits('payload["subset"] = m', "x.py")
    assert key_edits('cfg.pop("subset", None)', "x.py")
    assert key_edits('x = {**cfg, "subset": None}', "x.py")
    assert not key_edits('x = cfg.get("subset")', "x.py")
    assert subset_type_names("from e import SubsetError", "cli/run/x.py")
    assert subset_type_names(
        "try:\n    pass\nexcept e.SubsetBudgetExceededError:\n    pass", "cli/run/x.py"
    )
