"""G-ONE-MANIFEST-PATH: a stored manifest path becomes a file path only in `resolve_manifest_path`.

An evidence manifest stores `pipeline_path` and a `path` in every `input_fingerprints` and
`output_fingerprints` entry. Project-relative paths mean nothing against the working directory,
so the one manifest-aware resolver (`decoy.cli.evidence.resolve_manifest_path`) is the only code
that may turn one into a filesystem path. `report diff` once did `Path(raw)` itself and read
outputs from the current folder (PROJECT-LAYOUT plan, section 3.9).

The walk covers every module under `src/decoy`. Per function it marks, through one-hop
assignments and `for` targets:

- group values: `x["input_fingerprints"]`, `x.get("output_fingerprints")`, and names spelled
  like a fingerprint group (`...fingerprints...`, `fps`, `out_fps_a`);
- entries: a subscript or `.get` of a group;
- stored paths: `x["pipeline_path"]` / `x.get("pipeline_path")`, and `"path"` of an entry.

A stored path passed to `pathlib.Path`/`PurePath` (direct, aliased or module-qualified),
`os.path.*`, `open`, `contained_path`, `hash_file`, a data reader, a `/` join, or a filesystem
method fails the test outside the allowlist. Arguments of a `resolve_manifest_path` call are its
input, and its result is a resolved path, so neither is marked.

`report show` and `report render` are metadata-only consumers: they render stored paths as text
and make no filesystem call, so they need no entry here. Named limits: a stored path passed
through a function parameter not spelled like a group, a container, or `getattr` is not traced.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from tests.sentry.io_policy._calls import bindings, qualified

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"

RESOLVER = "resolve_manifest_path"
PATH_BUILDING_ALLOW = {("src/decoy/cli/evidence.py", RESOLVER)}
RESOLVER_CALLERS = {
    ("src/decoy/cli/evidence.py", "read_manifest"),
    ("src/decoy/cli/evidence.py", "verify_manifest_issues"),
    ("src/decoy/cli/report.py", "compare_data"),
}

_GROUP_KEYS = {"input_fingerprints", "output_fingerprints"}
_GROUP_NAME = re.compile(r"fingerprints|(?:^|_)fps(?:_|$)")
_PATH_CALLS = {
    "pathlib.Path",
    "pathlib.PurePath",
    "pathlib.PurePosixPath",
    "pathlib.PureWindowsPath",
    "io.open",
    "os.open",
    "os.stat",
    "os.lstat",
    "os.fspath",
}
_PATH_LEAVES = {
    "open",
    "contained_path",
    "hash_file",
    "read_file",
    "read_csv",
    "read_parquet",
    "read_table",
}
_FS_METHODS = {"resolve", "exists", "is_file", "open", "read_text", "read_bytes", "stat"}
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _key(node: ast.AST) -> str | None:
    """The constant key of `x["k"]` or `x.get("k", ...)`, with the receiver."""
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return node.slice.value if isinstance(node.slice.value, str) else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None


def _receiver(node: ast.AST) -> ast.expr | None:
    if isinstance(node, ast.Subscript):
        return node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.value
    return None


def _is_resolver(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Name) and f.id == RESOLVER) or (
        isinstance(f, ast.Attribute) and f.attr == RESOLVER
    )


def _own(node: ast.AST) -> Iterator[ast.AST]:
    """Every node under `node`, not inside a nested function."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(c for c in ast.iter_child_nodes(n) if not isinstance(c, _SCOPES))


def _nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Every node under `node`, not inside a nested function or a resolver call."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _SCOPES) or _is_resolver(child):
                continue
            stack.append(child)


class _Taint:
    def __init__(self) -> None:
        self.groups: set[str] = set()
        self.entries: set[str] = set()
        self.stored: set[str] = set()

    def group(self, e: ast.AST | None) -> bool:
        if isinstance(e, ast.Name):
            return e.id in self.groups or bool(_GROUP_NAME.search(e.id))
        return _key(e) in _GROUP_KEYS if e is not None else False

    def entry(self, e: ast.AST | None) -> bool:
        if isinstance(e, ast.Name):
            return e.id in self.entries
        getter = (
            isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and e.func.attr == "get"
        )
        return (isinstance(e, ast.Subscript) or getter) and self.group(_receiver(e))

    def path(self, e: ast.AST | None) -> bool:
        if isinstance(e, ast.Name):
            return e.id in self.stored
        k = _key(e) if e is not None else None
        return k == "pipeline_path" or (k == "path" and self.entry(_receiver(e)))

    def has(self, test, expr: ast.AST) -> bool:
        return any(test(n) for n in _nodes(expr))

    def learn(self, fn: ast.AST) -> None:
        """Mark names through assignments and `for` targets until nothing changes."""
        changed = True
        while changed:
            changed = False
            for n in _nodes(fn):
                pairs: list[tuple[ast.expr, ast.expr, bool]] = []
                if isinstance(n, ast.Assign):
                    pairs = [(t, n.value, False) for t in n.targets]
                elif isinstance(n, (ast.AnnAssign, ast.NamedExpr)) and n.value is not None:
                    pairs = [(n.target, n.value, False)]
                elif isinstance(n, (ast.For, ast.comprehension)):
                    pairs = [(n.target, n.iter, True)]
                for target, value, loop in pairs:
                    changed |= self._bind(target, value, loop)

    def _bind(self, target: ast.expr, value: ast.expr, loop: bool) -> bool:
        if _is_resolver(value):
            return False
        if loop:
            # `for k, entry in group.items()` / `for entry in group.values()`
            it = (
                value.func.value
                if isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr in ("items", "values")
                else None
            )
            if it is None or not self.group(it):
                return False
            names = target.elts[-1:] if isinstance(target, ast.Tuple) else [target]
            return self._add(self.entries, names)
        names = [target] if isinstance(target, ast.Name) else []
        if isinstance(target, ast.Tuple):
            names = list(target.elts)
        if self.has(self.path, value):
            return self._add(self.stored, names)
        if self.has(self.entry, value):
            return self._add(self.entries, names)
        if self.has(self.group, value):
            return self._add(self.groups, names)
        return False

    @staticmethod
    def _add(into: set[str], names: list[ast.expr]) -> bool:
        new = {n.id for n in names if isinstance(n, ast.Name)} - into
        into |= new
        return bool(new)


def _sinks(fn: ast.AST, taint: _Taint, bound: dict[str, str]) -> Iterator[int]:
    for n in _nodes(fn):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            if taint.has(taint.path, n.left) or taint.has(taint.path, n.right):
                yield n.lineno
        if not isinstance(n, ast.Call):
            continue
        name = qualified(n, bound) or ""
        last = name.rsplit(".", 1)[-1] if name else ""
        if not name and isinstance(n.func, ast.Name):
            last = n.func.id
        elif not name and isinstance(n.func, ast.Attribute):
            last = n.func.attr
        args = [*n.args, *(k.value for k in n.keywords)]
        building = name in _PATH_CALLS or name.startswith("os.path.") or last in _PATH_LEAVES
        if building and any(taint.has(taint.path, a) for a in args):
            yield n.lineno
        if (
            isinstance(n.func, ast.Attribute)
            and n.func.attr in _FS_METHODS
            and taint.has(taint.path, n.func.value)
        ):
            yield n.lineno


def _functions(
    node: ast.AST, bound: dict[str, str], scope: str
) -> Iterator[tuple[str, ast.AST, dict[str, str]]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            yield from _functions(child, bound, f"{scope}{child.name}.")
        elif isinstance(child, _SCOPES):
            inner = {**bound, **bindings(child)}
            yield f"{scope}{child.name}", child, inner
            yield from _functions(child, inner, f"{scope}{child.name}.")


def scan(src: Path, base: Path) -> tuple[list[tuple[str, str, int]], set[tuple[str, str]]]:
    """(path-building sites outside the allowlist, every resolver-calling function)."""
    building: list[tuple[str, str, int]] = []
    callers: set[tuple[str, str]] = set()
    for file in sorted(src.rglob("*.py")):
        rel = file.relative_to(base).as_posix()
        tree = ast.parse(file.read_text(encoding="utf-8"))
        module_bound = bindings(tree)
        scopes = [("<module>", tree, module_bound), *_functions(tree, module_bound, "")]
        for qual, fn, bound in scopes:
            taint = _Taint()
            taint.learn(fn)
            if (rel, qual) not in PATH_BUILDING_ALLOW:
                building.extend((rel, qual, line) for line in _sinks(fn, taint, bound))
            for n in _own(fn):
                if _is_resolver(n) and qual.rsplit(".", 1)[-1] != RESOLVER:
                    callers.add((rel, qual))
    return sorted(set(building)), callers


def test_only_the_resolver_turns_a_stored_manifest_path_into_a_file_path() -> None:
    building, _ = scan(SRC, ROOT)
    assert building == [], (
        "a stored manifest path is used as a file path outside resolve_manifest_path; "
        f"route it through decoy.cli.evidence.resolve_manifest_path: {building}"
    )


def test_the_resolver_is_called_by_exactly_the_allowed_consumers() -> None:
    _, callers = scan(SRC, ROOT)
    assert callers == RESOLVER_CALLERS


# --- self-tests: every realistic spelling turns the scan red --------------------------------

_SEEDS = {
    "direct": """
from pathlib import Path
def f(m):
    for _t, entry in m["output_fingerprints"].items():
        return Path(entry["path"])
""",
    "aliased": """
from pathlib import Path as _P
def f(m):
    entry = m["input_fingerprints"]["a"]
    return _P(entry["path"])
""",
    "local_import": """
def f(fps_a):
    from pathlib import Path as _Path
    fp = fps_a.get("t") or {}
    raw = fp.get("path") if isinstance(fp, dict) else None
    return _Path(raw)
""",
    "qualified": """
import pathlib
def f(m):
    return pathlib.Path(m["pipeline_path"])
""",
    "os_path": """
import os
def f(manifest, root):
    out = manifest.get("output_fingerprints") or {}
    info = out.get("a")
    return os.path.join(root, info["path"])
""",
    "div_join": """
def f(m, root):
    return root / m["pipeline_path"]
""",
    "one_hop": """
def f(m):
    for info in m["output_fingerprints"].values():
        p = info["path"]
        with open(p) as fh:
            return fh.read()
""",
    "reader": """
from decoy.cli.io import read_file
def f(manifest):
    entries = manifest["output_fingerprints"]
    return [read_file(e["path"]) for e in entries.values()]
""",
}

_CLEAN = """
from pathlib import Path
from decoy.cli.evidence import resolve_manifest_path
def compare_data(m, f):
    for name, entry in m["output_fingerprints"].items():
        path = resolve_manifest_path(m, entry["path"], manifest_file=f, field=name)
        if path.exists():
            return Path(path), str(entry["path"]), entry.get("path", "?")
"""


def _tree(tmp_path: Path, body: str) -> Path:
    src = tmp_path / "src" / "decoy" / "cli"
    src.mkdir(parents=True)
    (src / "seeded.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_every_seeded_spelling_is_found(tmp_path: Path) -> None:
    missed = []
    for name, body in _SEEDS.items():
        base = _tree(tmp_path / name, body)
        building, _ = scan(base / "src" / "decoy", base)
        if not building:
            missed.append(name)
    assert missed == []


def test_resolver_results_and_display_text_are_not_flagged(tmp_path: Path) -> None:
    base = _tree(tmp_path, _CLEAN)
    building, callers = scan(base / "src" / "decoy", base)
    assert building == []
    assert callers == {("src/decoy/cli/seeded.py", "compare_data")}


def test_a_missing_or_extra_resolver_caller_breaks_the_exact_set(tmp_path: Path) -> None:
    base = _tree(
        tmp_path,
        _CLEAN + "\ndef helper(m, f):\n    return resolve_manifest_path(m, 'x', manifest_file=f)\n",
    )
    _, callers = scan(base / "src" / "decoy", base)
    assert ("src/decoy/cli/seeded.py", "helper") in callers
    assert callers != RESOLVER_CALLERS
