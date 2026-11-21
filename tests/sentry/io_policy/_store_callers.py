"""One scanner for the "exactly one caller" sentries of the library store functions.

`callers(member)` lists the files under `src/decoy` outside `cli/library/` that call `member`,
through `_calls.sites`, so a call by an alias (`from decoy.cli.library import store_run_result as
s; s(...)`) or through the module (`library.store_run_result(...)`) is found under the member's
own name, not its local spelling. A call by a name that resolves to nothing (a method on a local)
falls back to its last name, which still catches `obj.store_run_result(...)`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.sentry.io_policy._calls import leaf, sites

SRC = Path(__file__).resolve().parents[3] / "src" / "decoy"


def scan(source: str, member: str) -> int:
    """How many calls in `source` resolve to `member`."""
    return sum(
        1
        for site in sites(ast.parse(source))
        if isinstance(site.node, ast.Call) and leaf(site.node, site.bound) == member
    )


def callers(member: str) -> list[str]:
    """The files outside the library package that call `member`, one entry per call."""
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("cli/library/"):
            continue
        found += [rel] * scan(path.read_text(encoding="utf-8"), member)
    return found
