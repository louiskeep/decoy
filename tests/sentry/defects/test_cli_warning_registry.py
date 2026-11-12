"""G-CLI-WARNING-REGISTRY: a CLI warning is recorded only through `RunContext.add_cli_warning`.

That method refuses a code outside `CLI_WARNING_CODES`. A module that appends to
`_cli_warnings` itself would put a machine-readable code in `run --json` that no registry
lists. This walks every module under `src/decoy/` and fails on a mutating call
(`append`, `extend`, `insert`) or an augmented assignment on a `_cli_warnings` attribute
outside that one method.

Named limit of a syntax walk: an alias such as `w = ctx._cli_warnings; w.append(...)` is not seen.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
OWNER = ("cli/run/_context.py", "add_cli_warning")
MUTATORS = frozenset({"append", "extend", "insert"})


def _is_list(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "_cli_warnings"


def violations(source: str, rel: str) -> list[str]:
    found: list[str] = []

    def walk(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            )
            mutates = (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr in MUTATORS
                and _is_list(child.func.value)
            ) or (isinstance(child, ast.AugAssign) and _is_list(child.target))
            if mutates and (rel, scope) != OWNER:
                found.append(f"{rel}:{child.lineno}: _cli_warnings changed outside add_cli_warning")
            walk(child, inner)

    walk(ast.parse(source), "")
    return found


def test_only_add_cli_warning_changes_the_list() -> None:
    out: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        out.extend(violations(path.read_text(encoding="utf-8"), rel))
    assert out == []


def test_seeded_append_is_caught() -> None:
    source = "def f(ctx):\n    ctx._cli_warnings.append({})\n"
    assert violations(source, "cli/run/_execute.py")


def test_seeded_extend_and_augassign_are_caught() -> None:
    source = "def f(ctx):\n    ctx._cli_warnings.extend([])\n    ctx._cli_warnings += []\n"
    assert len(violations(source, "cli/run/_prepare.py")) == 2


def test_the_owning_method_is_allowed() -> None:
    source = "class C:\n    def add_cli_warning(self, code, message):\n        self._cli_warnings.append({})\n"
    assert violations(source, "cli/run/_context.py") == []
