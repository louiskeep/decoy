"""Scanner for the environment-read inventory: every `os.environ` or `os.getenv` read in the CLI.

A site is keyed `path::function::variable::n`: `path` is relative to `src/decoy`, `function` the
dotted enclosing scope, `variable` the literal name read (`<dynamic>` when it is not a literal)
and `n` the 1-based position among the same triple, in line order. A second read of the same
variable in one function is a new key, so an allowed scope cannot absorb extra reads.

`_env_flags.py` is the one reader of switches and is the only file the scan skips. Every other
read is a baseline row: today they all read a path, a URL, a secret or a number, none a switch.

A read is seen through a bound import (`os.environ.get`, `os.getenv`, `os.environ[...]`,
`from os import environ as e; e.get(...)`), by `_calls.py`. Named limits: a copy made earlier
(`env = os.environ; env.get(...)`), a getter bound to a name by assignment, `getattr` on the
module, `dict(os.environ)`, `k in os.environ` and `os.environ` handed to another function.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from tests.sentry.io_policy import _calls

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
OWNER = "_env_flags.py"
DYNAMIC = "<dynamic>"
_GETTERS = {"os.environ.get", "os.getenv"}


def _first_arg(call: ast.Call | None) -> str:
    if call is not None and call.args:
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return DYNAMIC


def _reads(source: str) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for s in _calls.sites(ast.parse(source)):
        if not isinstance(s.node, (ast.Name, ast.Attribute)):
            continue
        parent = s.ancestors[-1][0] if s.ancestors else None
        if s.name in _GETTERS:
            call = parent if isinstance(parent, ast.Call) and parent.func is s.node else None
            found.append((s.scope, _first_arg(call), s.lineno))
        elif s.name == "os.environ" and isinstance(parent, ast.Subscript):
            if parent.value is s.node:
                key = parent.slice
                named = key.value if isinstance(key, ast.Constant) else None
                found.append((s.scope, named if isinstance(named, str) else DYNAMIC, s.lineno))
    return found


def sites_in_source(source: str, rel: str) -> set[str]:
    """The keys of every environment read in one file."""
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for scope, variable, line in _reads(source):
        groups[(scope, variable)].append(line)
    return {
        f"{rel}::{scope}::{variable}::{n}"
        for (scope, variable), lines in groups.items()
        for n, _line in enumerate(sorted(lines), start=1)
    }


def inventory(src: Path = SRC) -> set[str]:
    """The exact read inventory of every module under `src` except the flag module."""
    keys: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        if rel != OWNER and "__pycache__" not in path.parts:
            keys |= sites_in_source(path.read_text(encoding="utf-8"), rel)
    return keys


_WHY = (
    "environment read of a path, URL, secret or number, recorded when the one flag reader "
    "landed; moves to decoy._env_flags or leaves this baseline, never joins it"
)


def reasons() -> dict[str, str]:
    """Baseline source for the registry test and the one-off generator."""
    return {key: _WHY for key in inventory()}
