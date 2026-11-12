"""G-ONE-QUARANTINE-ENABLED: "is quarantine on" has one reader, `quarantine_enabled`.

Under `src/decoy/`, no function body other than `quarantine_enabled` reads both the
`"quarantine"` key and the `"enabled"` key (`.get("k")` or `["k"]`). A fifth hand copy of the
two-line check would drift from the others (for example on what counts as a block), so the
rule fails it. A function that reads only `"quarantine"` (block present) is a different fact
and stays allowed.

An AST walk of function bodies: a key held in a variable is not seen.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
CHOKE = "quarantine_enabled"
BLOCK_KEY = "quarantine"
FLAG_KEY = "enabled"


def _keys_read(func: ast.AST) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
        ):
            arg = node.args[0]
        elif isinstance(node, ast.Subscript):
            arg = node.slice
        else:
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            keys.add(arg.value)
    return keys


def two_key_readers(source: str) -> list[tuple[int, str]]:
    """(line, function name) for each function body reading both the block and flag keys."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            keys = _keys_read(node)
            if {BLOCK_KEY, FLAG_KEY} <= keys:
                found.append((node.lineno, node.name))
    return found


def _tree_readers() -> list[tuple[str, int, str]]:
    return [
        (path.relative_to(SRC).as_posix(), line, name)
        for path in sorted(SRC.rglob("*.py"))
        for line, name in two_key_readers(path.read_text(encoding="utf-8"))
    ]


def test_only_the_choke_point_reads_both_keys() -> None:
    stray = [site for site in _tree_readers() if site[2] != CHOKE]
    assert not stray, (
        "read quarantine.enabled through quarantine_enabled(cfg) "
        f"(decoy.cli.io), not by hand: {stray}"
    )


def test_rule_sees_the_choke_point() -> None:
    # Non-vacuity: if the walk could not see the real reader, the rule above would pass on
    # any tree.
    assert [name for _rel, _line, name in _tree_readers()] == [CHOKE]


@pytest.mark.parametrize(
    "body",
    [
        'q = cfg.get("quarantine")\nreturn q.get("enabled")',
        'q = cfg["quarantine"]\nreturn q["enabled"]',
        'q = cfg.get("quarantine")\nreturn q["enabled"]',
        'q = cfg["quarantine"]\nreturn q.get("enabled", False)',
        'return cfg.get("quarantine", {}).get("enabled")',
    ],
)
def test_rule_fires_on_each_spelling(body: str) -> None:
    source = "def f(cfg):\n" + "".join(f"    {line}\n" for line in body.splitlines())
    assert two_key_readers(source) == [(1, "f")]


@pytest.mark.parametrize(
    "body",
    ['return cfg.get("quarantine")', 'return cfg.get("enabled")', 'return cfg["other"]["enabled"]'],
)
def test_rule_ignores_a_single_key(body: str) -> None:
    assert two_key_readers(f"def f(cfg):\n    {body}\n") == []
