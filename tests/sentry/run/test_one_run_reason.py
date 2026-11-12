"""G-ONE-REASON: one place in `src/decoy/` turns an exception into an engine reason.

`reason_from_exception` is named exactly once outside comments: the call inside
`_failure_reason` in `cli/run/_errors.py`. A second call site would re-decide which failures
carry a reason, so a refusal the CLI owns could start to look engine-raised. The scan counts
every identifier, attribute, import alias and string constant that holds the name, so an import
alias or a `getattr(module, "reason_from_exception")` is seen too.

Named limit: a name built from parts at run time is invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
NAME = "reason_from_exception"
OWNER = ("cli/run/_errors.py", "_failure_reason")


def _mentions(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == NAME
    if isinstance(node, ast.Attribute):
        return node.attr == NAME
    if isinstance(node, ast.alias):
        return NAME in node.name or node.asname == NAME
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and NAME in node.value
    return False


def violations(source: str, rel: str) -> list[str]:
    """Every mention outside the owner function, plus a second mention inside it."""
    found: list[str] = []
    inside = 0

    def walk(node: ast.AST, scope: str) -> None:
        nonlocal inside
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            )
            if _mentions(child):
                line = getattr(child, "lineno", 0)
                if (rel, scope) != OWNER:
                    found.append(f"{rel}:{line}: {NAME} outside _failure_reason")
                else:
                    inside += 1
            walk(child, inner)

    walk(ast.parse(source), "")
    if inside > 1:
        found.append(f"{rel}: {NAME} named {inside} times inside _failure_reason")
    return found


def _scan() -> tuple[list[str], int]:
    out: list[str] = []
    owner_mentions = 0
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        text = path.read_text(encoding="utf-8")
        out.extend(violations(text, rel))
        if rel == OWNER[0]:
            owner_mentions = text.count(NAME)
    return out, owner_mentions


def test_one_reason_call_in_the_failure_helper() -> None:
    out, owner_mentions = _scan()
    assert out == []
    assert owner_mentions >= 1, "the owner no longer names the engine helper"


def test_seeded_second_call_in_another_module_is_caught() -> None:
    source = "def f(e):\n    return reason_from_exception(e)\n"
    assert violations(source, "cli/run/_render.py")


def test_seeded_import_alias_and_getattr_are_caught() -> None:
    alias = "from decoy_engine.reason_adapter import reason_from_exception as r\n"
    dyn = "def f(m):\n    return getattr(m, 'reason_from_exception')\n"
    assert violations(alias, "cli/run/_render.py")
    assert violations(dyn, "cli/run/_render.py")


def test_seeded_second_mention_inside_the_owner_is_caught() -> None:
    twice = (
        "def _failure_reason(a, b):\n"
        "    x = adapter.reason_from_exception(a)\n"
        "    return adapter.reason_from_exception(b)\n"
    )
    assert violations(twice, "cli/run/_errors.py")


def test_the_owner_with_one_call_is_allowed() -> None:
    once = "def _failure_reason(a, b):\n    return adapter.reason_from_exception(b)\n"
    assert violations(once, "cli/run/_errors.py") == []
