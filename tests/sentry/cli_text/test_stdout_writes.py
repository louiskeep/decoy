"""G-ONE-JSON-STDOUT: a CLI command writes JSON to stdout only through `ui/output.py`.

`emit_json` (the `--json` envelope) and `emit_json_document` (a raw document in default mode) are
the two writers. A third one drifts on flush, newline and mode checks: the streamed scan once
wrote its document by hand and a refactor to `emit_json` would have printed nothing. The scan
reports a stdout write (`sys.stdout.write`, `print`, `typer.echo`, `click.echo`) whose argument
holds a `json.dumps` call, or a name assigned from one in the same function, and a
`json.dump(obj, sys.stdout)`. A write to stderr (`err=True`, `file=sys.stderr`) is not stdout.

Named limits: JSON built by a helper in another function, by `console.print_json`, or by an
encoder other than `json`; the scan sees the `json.dumps` spelling only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from tests.sentry.io_policy import _calls

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
_WRITERS = {"sys.stdout.write", "typer.echo", "click.echo", "print"}
_DUMPERS = {"json.dumps"}


@dataclass(frozen=True)
class AllowedWriter:
    path: str
    function: str
    reason: str


ALLOWLIST: tuple[AllowedWriter, ...] = (
    AllowedWriter("ui/output.py", "emit_json", "the --json envelope writer"),
    AllowedWriter("ui/output.py", "emit_json_document", "the default-mode document writer"),
    AllowedWriter(
        "distribution/selfcheck.py",
        "main",
        "a child-process probe: its parent parses this line, it is not command output",
    ),
)


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


def writes_in_source(source: str, rel: str) -> set[tuple[str, str]]:
    """`(path, function)` for every stdout write of a `json.dumps` result in one file."""
    tree = ast.parse(source)
    found: set[tuple[str, str]] = set()
    for s in _calls.sites(tree):
        call = s.node
        if not isinstance(call, ast.Call):
            continue
        name = _calls.qualified(call, s.bound)
        if name is None and isinstance(call.func, ast.Name) and call.func.id == "print":
            name = "print"
        if name == "json.dump":
            sink = call.args[1] if len(call.args) > 1 else None
            if sink is not None and _calls.qualified(sink, s.bound) == "sys.stdout":
                found.add((rel, s.scope))
            continue
        if name not in _WRITERS or _to_stderr(call, s.bound):
            continue
        tainted = _dumped_names(_enclosing(s, tree), s.bound)
        for arg in [*call.args, *(k.value for k in call.keywords)]:
            named = any(isinstance(n, ast.Name) and n.id in tainted for n in ast.walk(arg))
            if _has_dumps(arg, s.bound) or named:
                found.add((rel, s.scope))
    return found


def problems(
    files: dict[str, str], allow: tuple[AllowedWriter, ...] = ALLOWLIST
) -> tuple[list[str], list[str]]:
    found: set[tuple[str, str]] = set()
    for rel, source in files.items():
        found |= writes_in_source(source, rel)
    listed = {(a.path, a.function) for a in allow}
    unlisted = [f"{p}::{f}" for p, f in sorted(found - listed)]
    stale = [f"{p}::{f}" for p, f in sorted(listed - found)]
    return unlisted, stale


def _src_files() -> dict[str, str]:
    return {
        p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(SRC.rglob("*.py"))
        if "__pycache__" not in p.parts
    }


def test_json_reaches_stdout_only_through_the_output_module() -> None:
    unlisted, stale = problems(_src_files())
    assert unlisted == [], "write JSON through ui.output.emit_json or emit_json_document"
    assert stale == [], "allowlist rows with no matching write (remove them)"


def test_allowlist_rows_have_reasons() -> None:
    assert all(len(a.reason) >= 5 for a in ALLOWLIST)


# --- seeded spellings: each turns the scan red --------------------------------------------

_SEEDS = {
    "write": "import sys, json\ndef f(x):\n    sys.stdout.write(json.dumps(x))\n",
    "print": "import json\ndef f(x):\n    print(json.dumps(x))\n",
    "echo": "import json as _json, typer\ndef f(x):\n    typer.echo(_json.dumps(x))\n",
    "named": 'import sys, json\ndef f(x):\n    s = json.dumps(x)\n    sys.stdout.write(s + "\\n")\n',
    "from_import": "from json import dumps as d\nimport sys\ndef f(x):\n    sys.stdout.write(d(x))\n",
    "dump": "import json, sys\ndef f(x):\n    json.dump(x, sys.stdout)\n",
    "stdout_alias": "from sys import stdout\nimport json\ndef f(x):\n    stdout.write(json.dumps(x))\n",
    "print_stdout": "import json, sys\ndef f(x):\n    print(json.dumps(x), file=sys.stdout)\n",
}


def test_each_seeded_spelling_is_seen() -> None:
    for name, source in _SEEDS.items():
        unlisted, _ = problems({f"{name}.py": source}, allow=())
        assert unlisted == [f"{name}.py::f"], f"{name}: {unlisted}"


def test_stderr_and_non_json_writes_are_allowed() -> None:
    source = (
        "import sys, json, typer\n"
        "def f(x):\n"
        "    sys.stdout.write('text')\n"
        "    typer.echo(json.dumps(x), err=True)\n"
        "    print(json.dumps(x), file=sys.stderr)\n"
        "    json.dump(x, sys.stderr)\n"
        "    s = json.dumps(x)\n"
        "    return s\n"
    )
    assert problems({"ok.py": source}, allow=()) == ([], [])
