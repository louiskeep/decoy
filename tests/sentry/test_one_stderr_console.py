"""G-ONE-STDERR-CONSOLE: application stderr goes through the one soft-wrapped console.

`src/decoy/ui/output.py::_make_console` builds the only Rich console. It soft-wraps, so an
error line is never folded at the console width (a fold puts a newline inside a long path).
A second console, a stray `rich.print(..., file=...)`, a `soft_wrap=False` override, or a
`Panel`/`Table` printed to the stderr console would each bring the fold back. This walks the
syntax tree of every module under `src/decoy/` and fails on:

(a) any construction of `rich.console.Console` outside `ui/output.py`, in every spelling:
    `Console(...)`, `from rich.console import Console as C; C(...)`,
    `rich.console.Console(...)`, `import rich.console as rc; rc.Console(...)`;
(b) `rich.print(..., file=...)` or `from rich import print as p; p(..., file=...)`;
(c) `soft_wrap=False` passed to any `*.err_console.print(...)`;
(d) a direct `Panel(...)` or `Table(...)` argument to `*.err_console.print(...)`.

Named limits of a syntax walk: a `Panel` or `Table` held in a variable and printed later is
not seen, nor is an aliased receiver such as `err = state.err_console; err.print(Panel(...))`.
Typer's own usage-error panels use Typer's console and are outside this choke point.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "ui/output.py"
CONSOLE_FQN = "rich.console.Console"
PRINT_FQN = "rich.print"
RENDERABLES = {"rich.panel.Panel", "rich.table.Table", "Panel", "Table"}


def _imports(tree: ast.AST) -> dict[str, str]:
    """Map each local name an import binds to its dotted origin."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names[a.asname or a.name.split(".")[0]] = (
                    a.name if a.asname else a.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                names[a.asname or a.name] = f"{node.module}.{a.name}"
    return names


def _dotted(node: ast.expr, names: dict[str, str]) -> str | None:
    """Resolve a Name/Attribute chain to its fully-qualified dotted name, if it is one."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    root = names.get(node.id, node.id)
    return ".".join([root, *reversed(parts)])


def _is_err_print(call: ast.Call) -> bool:
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == "print"
        and isinstance(f.value, ast.Attribute)
        and f.value.attr == "err_console"
    )


def violations(source: str, rel: str) -> list[str]:
    tree = ast.parse(source)
    names = _imports(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _dotted(node.func, names)
        where = f"{rel}:{node.lineno}"
        if target == CONSOLE_FQN and rel != CHOKE_POINT:
            out.append(f"{where}: (a) Console constructed outside {CHOKE_POINT}")
        if target == PRINT_FQN and any(k.arg == "file" for k in node.keywords):
            out.append(f"{where}: (b) rich.print with file=")
        if _is_err_print(node):
            for k in node.keywords:
                if (
                    k.arg == "soft_wrap"
                    and isinstance(k.value, ast.Constant)
                    and k.value.value is False
                ):
                    out.append(f"{where}: (c) soft_wrap=False on err_console.print")
            for arg in node.args:
                if isinstance(arg, ast.Call) and _dotted(arg.func, names) in RENDERABLES:
                    out.append(f"{where}: (d) Panel/Table printed to err_console")
    return out


def test_src_has_one_soft_wrapped_stderr_console() -> None:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        found += violations(path.read_text(encoding="utf-8"), rel)
    assert found == []


def test_the_choke_point_still_constructs_a_console() -> None:
    """Guards the scan itself: ui/output.py must show one construction, not zero."""
    text = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    tree = ast.parse(text)
    names = _imports(tree)
    built = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _dotted(n.func, names) == CONSOLE_FQN
    ]
    assert len(built) == 1


SEEDED = {
    "a_plain": "from rich.console import Console\nc = Console()\n",
    "a_alias": "from rich.console import Console as C\nc = C(stderr=True)\n",
    "a_attr": "import rich.console\nc = rich.console.Console()\n",
    "a_module_alias": "import rich.console as rc\nc = rc.Console()\n",
    "b_rich_print": "import rich\nrich.print('x', file=None)\n",
    "b_aliased_print": "from rich import print as p\np('x', file=None)\n",
    "c_soft_wrap_false": "def f(state):\n    state.err_console.print('x', soft_wrap=False)\n",
    "d_panel": (
        "from rich.panel import Panel\ndef f(state):\n    state.err_console.print(Panel('x'))\n"
    ),
    "d_table": (
        "from rich import table as t\ndef f(state):\n    state.err_console.print(t.Table())\n"
    ),
}


@pytest.mark.parametrize("case", sorted(SEEDED))
def test_each_shape_is_caught(case: str) -> None:
    got = violations(SEEDED[case], "cli/seeded.py")
    assert len(got) == 1, got
    assert f"({case[0]})" in got[0]


def test_the_choke_point_itself_is_allowed() -> None:
    assert violations(SEEDED["a_plain"], CHOKE_POINT) == []


def test_ordinary_use_is_not_flagged() -> None:
    ok = "def f(state):\n    state.err_console.print('x', markup=False, soft_wrap=True)\n"
    assert violations(ok, "cli/ok.py") == []
