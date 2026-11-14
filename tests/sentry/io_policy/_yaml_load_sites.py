"""Scanner for the YAML-load inventory: every call that loads YAML under `src/decoy`.

A site is a call to `yaml.safe_load`, `yaml.load`, `yaml.full_load`, `yaml.unsafe_load`, their
`_all` forms, `yaml.compose` and `yaml.compose_all`, or `.load(...)` on a `ruamel.yaml.YAML()`
instance built in the same expression, reached through a bound import (`import yaml as _yaml`,
`from yaml import safe_load as sl`). A site is keyed `path::function::n`, `n` being the 1-based
position among the sites of that function in line order, so a second load in an allowed function
is a new key. `_config_file.py` is the one config loader and is the only file the scan skips.

Named limits: an instance bound to a name (`y = YAML(); y.load(...)`), `getattr(yaml, "safe_load")`,
a loader bound by assignment (`f = yaml.safe_load`), and `yaml.parse` / `yaml.scan`, which read
events or tokens and never build a value.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from tests.sentry.io_policy import _calls

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
OWNER = "_config_file.py"
_LOADERS = frozenset(
    f"yaml.{n}"
    for n in (
        "safe_load",
        "load",
        "full_load",
        "unsafe_load",
        "safe_load_all",
        "load_all",
        "full_load_all",
        "unsafe_load_all",
        "compose",
        "compose_all",
    )
)
_RUAMEL = frozenset({"ruamel.yaml.YAML", "ruamel.yaml.main.YAML"})


def _lines(source: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for s in _calls.sites(ast.parse(source)):
        if not isinstance(s.node, ast.Call):
            continue
        callee = s.node.func
        if s.name in _LOADERS:
            found.append((s.scope, s.lineno))
        elif (
            isinstance(callee, ast.Attribute)
            and callee.attr in {"load", "load_all"}
            and isinstance(callee.value, ast.Call)
            and _calls.qualified(callee.value, s.bound) in _RUAMEL
        ):
            found.append((s.scope, s.lineno))
    return found


def sites_in_source(source: str, rel: str) -> set[str]:
    """The keys of every YAML load in one file."""
    groups: dict[str, list[int]] = defaultdict(list)
    for scope, line in _lines(source):
        groups[scope].append(line)
    return {
        f"{rel}::{scope}::{n}"
        for scope, lines in groups.items()
        for n, _line in enumerate(sorted(lines), start=1)
    }


def inventory(src: Path = SRC) -> set[str]:
    keys: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        if rel != OWNER and "__pycache__" not in path.parts:
            keys |= sites_in_source(path.read_text(encoding="utf-8"), rel)
    return keys


def bypass_sites_in_source(source: str, rel: str) -> set[str]:
    """`path::function` of every function that reads bytes and decodes them itself.

    `Path.read_bytes()` plus `.decode(...)` in one function is the loader's read step done by
    hand: a second place that decides what a non-UTF-8 file means (the CI adapter once did).
    Named limits: the bytes handed to a helper that decodes, and `open(...).read().decode(...)`.
    """
    keys: set[str] = set()

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}.{child.name}" if prefix else child.name
                if not isinstance(child, ast.ClassDef):
                    attrs = {
                        n.func.attr
                        for n in ast.walk(child)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    }
                    if {"read_bytes", "decode"} <= attrs:
                        keys.add(f"{rel}::{qual}")
                walk(child, qual)
            else:
                walk(child, prefix)

    walk(ast.parse(source), "")
    return keys


def bypass_inventory(src: Path = SRC) -> set[str]:
    keys: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        if rel != OWNER and "__pycache__" not in path.parts:
            keys |= bypass_sites_in_source(path.read_text(encoding="utf-8"), rel)
    return keys
