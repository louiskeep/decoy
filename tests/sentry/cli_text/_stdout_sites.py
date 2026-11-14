"""Scanner for the JSON-to-stdout inventory: every stdout write of a `json.dumps` result.

A site is a call to `sys.stdout.write`, `print`, `typer.echo` or `click.echo` whose arguments hold
a `json.dumps` call or a name assigned from one in the same function, or a `json.dump(obj,
sys.stdout)`. A write to stderr (`err=True`, `file=sys.stderr`) is not stdout. A site is keyed
`path::function::n`, `n` being the 1-based position in the function in line order, so a second
write in an allowed function is a new key.

The two writers in `ui/output.py` are not baseline rows: they are the owner contract, pinned
by `OUTPUT_WRITERS` in `test_stdout_writes.py`. Everything else is a legacy site.

Named limits: JSON built by a helper in another function, by `console.print_json`, or by an
encoder other than `json`; a `json.dumps` bound to a name by assignment (`d = json.dumps`); a
call result assigned through a tuple target.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from tests.sentry.io_policy import _calls

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
OUTPUT_MODULE = "ui/output.py"
_WRITERS = {"sys.stdout.write", "typer.echo", "click.echo", "print"}
_DUMPERS = {"json.dumps"}


def _has_dumps(node: ast.AST, bound: _calls.Bindings) -> bool:
    return any(
        isinstance(n, ast.Call) and _calls.qualified(n, bound) in _DUMPERS for n in ast.walk(node)
    )


def _enclosing(site: _calls.Site, tree: ast.Module) -> ast.AST:
    for node, _field in reversed(site.ancestors):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return node
    return tree


def _dumped_names(scope: ast.AST, bound: _calls.Bindings) -> set[str]:
    names: set[str] = set()
    for n in ast.walk(scope):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and n.value is not None:
            if _has_dumps(n.value, bound):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def _to_stderr(call: ast.Call, bound: _calls.Bindings) -> bool:
    for kw in call.keywords:
        if kw.arg == "err" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
        if kw.arg == "file" and _calls.qualified(kw.value, bound) != "sys.stdout":
            return True
    return False


def _is_write(site: _calls.Site, call: ast.Call, tree: ast.Module) -> bool:
    name = _calls.qualified(call, site.bound)
    if name is None and isinstance(call.func, ast.Name) and call.func.id == "print":
        name = "print"
    if name == "json.dump":
        sink = call.args[1] if len(call.args) > 1 else None
        return sink is not None and _calls.qualified(sink, site.bound) == "sys.stdout"
    if name not in _WRITERS or _to_stderr(call, site.bound):
        return False
    tainted = _dumped_names(_enclosing(site, tree), site.bound)
    for arg in [*call.args, *(k.value for k in call.keywords)]:
        named = any(isinstance(n, ast.Name) and n.id in tainted for n in ast.walk(arg))
        if _has_dumps(arg, site.bound) or named:
            return True
    return False


def sites_in_source(source: str, rel: str) -> set[str]:
    """The keys of every JSON stdout write in one file."""
    tree = ast.parse(source)
    groups: dict[str, list[int]] = defaultdict(list)
    for s in _calls.sites(tree):
        if isinstance(s.node, ast.Call) and _is_write(s, s.node, tree):
            groups[s.scope].append(s.lineno)
    return {
        f"{rel}::{scope}::{n}"
        for scope, lines in groups.items()
        for n, _line in enumerate(sorted(lines), start=1)
    }


def all_sites(src: Path = SRC) -> set[str]:
    keys: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" not in path.parts:
            keys |= sites_in_source(
                path.read_text(encoding="utf-8"), path.relative_to(src).as_posix()
            )
    return keys


def inventory(src: Path = SRC) -> set[str]:
    """The legacy inventory: every write outside the output module."""
    return {k for k in all_sites(src) if not k.startswith(f"{OUTPUT_MODULE}::")}


_WHY = (
    "legacy JSON stdout write recorded when the one document writer landed; moves to "
    "ui.output.emit_json_document or leaves this baseline, never joins it"
)


def reasons() -> dict[str, str]:
    """Baseline source for the registry test and the one-off generator."""
    return {key: _WHY for key in inventory()}
