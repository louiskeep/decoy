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
(d) a direct `Panel(...)` or `Table(...)` argument to `*.err_console.print(...)`;
(e) `*.err_console.print_exception(...)`: use `ui.output.print_traceback`, which prints the
    traceback unwrapped. Shape (c) exempts that one helper by exact (file, function).

Import resolution comes from the shared scope-aware scanner in
`tests/sentry/io_policy/_calls.py`, so a nested import cannot shadow a module-level alias.

Named limits of a syntax walk: a `Panel` or `Table` held in a variable and printed later is
not seen, nor is an aliased receiver such as `err = state.err_console; err.print(Panel(...))`.
Typer's own usage-error panels use Typer's console and are outside this choke point.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from tests.sentry.io_policy._calls import call_contexts

CONSOLE_FQN = "rich.console.Console"
PRINT_FQN = "rich.print"
RENDERABLES = ("rich.panel.Panel", "rich.table.Table")
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "ui/output.py"
# The one stderr print allowed to turn soft wrap off: a soft-wrapped traceback crops each frame
# header at the panel edge, so the traceback helper prints with Rich's own wrapping.
TRACEBACK_HELPER = ("ui/output.py", "print_traceback")
ERR_METHODS = frozenset({"print", "print_exception"})


def _sites(source: str, *names: str) -> list[tuple[ast.Call, str]]:
    """Calls of any watched dotted name, resolved through the shared scope-aware scanner."""
    found = call_contexts(
        source,
        qualified_match=lambda module, member: f"{module}.{member}" in names,
        with_calls=frozenset(),
    )
    return [(call, scope) for call, scope, _ in found]


def _err_calls(source: str) -> list[tuple[ast.Call, str, str]]:
    """(call, scope, method) for each `<anything>.err_console.print` or `.print_exception`."""
    found = call_contexts(
        source,
        qualified_match=lambda module, member: False,
        method_names=ERR_METHODS,
        with_calls=frozenset(),
    )
    return [
        (call, scope, call.func.attr)
        for call, scope, _ in found
        if isinstance(call.func, ast.Attribute)
        and call.func.attr in ERR_METHODS
        and isinstance(call.func.value, ast.Attribute)
        and call.func.value.attr == "err_console"
    ]


def violations(source: str, rel: str) -> list[str]:
    out: list[str] = []
    if rel != CHOKE_POINT:
        for call, _scope in _sites(source, CONSOLE_FQN):
            out.append(f"{rel}:{call.lineno}: (a) Console constructed outside {CHOKE_POINT}")
    for call, _scope in _sites(source, PRINT_FQN):
        if any(k.arg == "file" for k in call.keywords):
            out.append(f"{rel}:{call.lineno}: (b) rich.print with file=")
    renderables = {(c.lineno, c.col_offset) for c, _ in _sites(source, *RENDERABLES)}
    for call, scope, method in _err_calls(source):
        where = f"{rel}:{call.lineno}"
        if method == "print_exception":
            out.append(f"{where}: (e) err_console.print_exception, use print_traceback")
            continue
        for k in call.keywords:
            if (
                k.arg == "soft_wrap"
                and isinstance(k.value, ast.Constant)
                and k.value.value is False
                and (rel, scope) != TRACEBACK_HELPER
            ):
                out.append(f"{where}: (c) soft_wrap=False on err_console.print")
        for arg in call.args:
            if isinstance(arg, ast.Call) and (arg.lineno, arg.col_offset) in renderables:
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
    assert len(_sites(text, CONSOLE_FQN)) == 1


SEEDED = {
    "a_plain": "from rich.console import Console\nc = Console()\n",
    "a_alias": "from rich.console import Console as C\nc = C(stderr=True)\n",
    "a_attr": "import rich.console\nc = rich.console.Console()\n",
    "a_module_alias": "import rich.console as rc\nc = rc.Console()\n",
    "b_rich_print": "import rich\nrich.print('x', file=None)\n",
    "b_aliased_print": "from rich import print as p\np('x', file=None)\n",
    "c_soft_wrap_false": "def f(state):\n    state.err_console.print('x', soft_wrap=False)\n",
    "a_shadowed_alias": (
        "from rich.console import Console as C\n"
        "def other():\n    import collections as C\n    return C\n"
        "c = C()\n"
    ),
    "e_print_exception": "def f(state):\n    state.err_console.print_exception()\n",
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


def test_the_traceback_helper_is_the_only_soft_wrap_exemption() -> None:
    helper = "def print_traceback(state):\n    state.err_console.print(tb, soft_wrap=False)\n"
    assert violations(helper, "ui/output.py") == []
    assert len(violations(helper, "cli/other.py")) == 1
    other = helper.replace("print_traceback", "other")
    assert len(violations(other, "ui/output.py")) == 1


def test_a_local_import_does_not_hide_the_module_level_alias() -> None:
    got = violations(SEEDED["a_shadowed_alias"], "cli/seeded.py")
    assert len(got) == 1 and "(a)" in got[0]


def test_the_choke_point_itself_is_allowed() -> None:
    assert violations(SEEDED["a_plain"], CHOKE_POINT) == []


def test_ordinary_use_is_not_flagged() -> None:
    ok = "def f(state):\n    state.err_console.print('x', markup=False, soft_wrap=True)\n"
    assert violations(ok, "cli/ok.py") == []
