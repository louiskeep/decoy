"""G-ONE-SCAFFOLD-PUBLISH: the generate scaffold writes its files through `publish_local_targets`.

The snapshot and the config are one unit. A second write path in `cli/gen/_scaffold.py` (a
direct `write_text`, `write_local_target`, `open(..., "w")`) could leave a half scaffold, so the
module may call only `_atomic.publish_local_targets` to put bytes on disk, and must call it.
Scope (owner rule 2026-11-06): the spellings a person would write by habit.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCAFFOLD = ROOT / "src" / "decoy" / "cli" / "gen" / "_scaffold.py"
_WRITERS = frozenset(
    {"write_text", "write_bytes", "write_local_target", "write_atomic", "to_csv", "dump"}
)
_REQUIRED = "publish_local_targets"


def _opens_for_writing(call: ast.Call, is_method: bool) -> bool:
    """`open(p, "w")`, `open(p, mode="w")`, `path.open("w")` and `path.open(mode="w")`."""
    positional = call.args[0 if is_method else 1] if len(call.args) > (not is_method) else None
    keyword = next((k.value for k in call.keywords if k.arg == "mode"), None)
    return any(
        isinstance(mode, ast.Constant) and set(str(mode.value)) & set("wax+")
        for mode in (positional, keyword)
    )


def findings(source: str) -> list[str]:
    out: list[str] = []
    publishes = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == _REQUIRED:
            publishes += 1
        elif name in _WRITERS:
            out.append(f"line {node.lineno}: {name} writes outside {_REQUIRED}")
        elif name == "open" and _opens_for_writing(node, isinstance(func, ast.Attribute)):
            out.append(f"line {node.lineno}: open for writing outside {_REQUIRED}")
    if publishes != 1:
        out.append(f"{publishes} calls of {_REQUIRED}, expected exactly 1")
    return out


def test_the_scaffold_writes_only_through_the_batch_publisher() -> None:
    assert findings(SCAFFOLD.read_text(encoding="utf-8")) == []


def test_a_direct_write_is_red() -> None:
    src = "def f(p, d):\n    p.write_text(d)\n    _atomic.publish_local_targets([])\n"
    assert findings(src) == ["line 2: write_text writes outside publish_local_targets"]


def test_two_independent_atomic_writes_are_red() -> None:
    src = "def f(a, b):\n    write_local_target(a, b'', 1)\n    write_local_target(a, b'', 1)\n"
    assert len(findings(src)) == 3


def test_a_scaffold_that_never_publishes_is_red() -> None:
    assert findings("def f():\n    pass\n") == [
        "0 calls of publish_local_targets, expected exactly 1"
    ]


@pytest.mark.parametrize(
    "call",
    ['p.open("w")', 'p.open(mode="wb")', 'open(p, mode="w")', 'open(p, "a")', 'p.open("r+")'],
)
def test_every_write_spelling_of_open_is_red(call: str) -> None:
    src = f"def f(p):\n    {call}\n    _atomic.publish_local_targets([])\n"
    assert len(findings(src)) == 1


@pytest.mark.parametrize("call", ['p.open("r")', "open(p)", 'open(p, "rb")', "p.open()"])
def test_a_read_open_is_not_a_finding(call: str) -> None:
    src = f"def f(p):\n    {call}\n    _atomic.publish_local_targets([])\n"
    assert findings(src) == []
