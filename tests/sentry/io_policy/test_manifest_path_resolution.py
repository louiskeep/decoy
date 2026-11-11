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
- entries: a subscript or `.get` of a group (also through `or {}`, a conditional or a `dict()`
  copy), the value of `for k, v in group.items()`, and every name a `for` unpacks from an
  iterable that holds an entry, directly or through a name bound to a tuple of entries;
- stored paths: `x["pipeline_path"]` / `x.get("pipeline_path")`, and `"path"` of an entry.

A stored path passed to `pathlib.Path`/`PurePath` (direct, aliased or module-qualified),
`os.path.*`, `open`, `contained_path`, `hash_file`, a data reader, a `/` join, or a filesystem
method fails the test. So does a call that hands a whole entry or group (or a tuple holding
entries) to a helper, which could build a path from it out of sight (`entry_format` once did
`Path(entry["path"])`), unless the (file, function, callee) is in `ALLOWLIST`, registered as
sentry `manifest-path-forward-allow`. A few builtins that cannot build a path are exempt; a copy
they return stays marked. Arguments of a `resolve_manifest_path` call are its input, and its
result is a resolved path, so neither is marked.

`report show` and `report render` are metadata-only consumers: they render stored paths as text
and make no filesystem call, so they need no entry here. Named limits: a stored path string
handed to a helper, an entry inside a dict or comprehension, and `getattr` are not traced.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tests.sentry.io_policy._calls import bindings, qualified

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"

BASELINE = ROOT / "tests" / "sentry" / "baselines" / "manifest-path-forward-allow.json"

RESOLVER = "resolve_manifest_path"


@dataclass(frozen=True)
class AllowedForward:
    file: str  # relative to the repo root
    function: str
    callee: str
    reason: str


# A whole entry or group may go only to a callee that cannot build a path from it.
ALLOWLIST: tuple[AllowedForward, ...] = (
    AllowedForward(
        "src/decoy/cli/report.py",
        "compare_manifests",
        "_fp_changes",
        "Compares recorded fingerprints by table name; it reads no `path` and opens nothing.",
    ),
)
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
# Builtins that cannot build a path from a dict; a copy they return stays marked by `learn`.
_INERT = {"isinstance", "len", "bool", "sorted", "list", "dict", "set", "tuple", "any", "all"}
_COPIES = {"dict", "list", "tuple"}
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
        self.holders: set[str] = set()  # names bound to a tuple/list/set literal holding an entry

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
            unpacked = list(target.elts) if isinstance(target, ast.Tuple) else [target]
            if it is not None and self.group(it):
                return self._add(self.entries, unpacked[-1:])
            # `for manifest, entry, where in ((m, entry_a, f), ...)`: any name may be the entry.
            if self.has(self.holds, value):
                return self._add(self.entries, unpacked)
            return False
        names = [target] if isinstance(target, ast.Name) else []
        if isinstance(target, ast.Tuple):
            names = list(target.elts)
        if self.has(self.path, value):
            return self._add(self.stored, names)
        if self.yields(self.entry, value):
            return self._add(self.entries, names)
        if self.yields(self.group, value):
            return self._add(self.groups, names)
        if isinstance(value, (ast.Tuple, ast.List, ast.Set)) and self.has(self.holds, value):
            return self._add(self.holders, names)
        return False

    def holds(self, e: ast.AST) -> bool:
        return self.entry(e) or (isinstance(e, ast.Name) and e.id in self.holders)

    def yields(self, test, e: ast.expr) -> bool:
        """`e` evaluates to the marked dict itself, not to something built from it."""
        if isinstance(e, ast.BoolOp):
            return any(self.yields(test, v) for v in e.values)
        if isinstance(e, ast.IfExp):
            return self.yields(test, e.body) or self.yields(test, e.orelse)
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id in _COPIES:
            return any(self.yields(test, a) for a in e.args)
        return bool(test(e))

    @staticmethod
    def _add(into: set[str], names: list[ast.expr]) -> bool:
        new = {n.id for n in names if isinstance(n, ast.Name)} - into
        into |= new
        return bool(new)


def _forwards(call: ast.Call, taint: _Taint) -> bool:
    """`call` hands a whole entry or group to its callee, which could build a path from it."""
    for arg in [*call.args, *(k.value for k in call.keywords)]:
        arg = arg.value if isinstance(arg, ast.Starred) else arg
        if taint.holds(arg) or taint.group(arg):
            return True
    return False


def _sinks(
    fn: ast.AST, taint: _Taint, bound: dict[str, str], forward_ok: set[str]
) -> Iterator[int]:
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
        if last not in _INERT and last not in forward_ok and _forwards(n, taint):
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


def scan(
    src: Path, base: Path, allow: tuple[AllowedForward, ...] = ALLOWLIST
) -> tuple[list[tuple[str, str, int]], set[tuple[str, str]]]:
    """(path-building and entry-forwarding sites, every resolver-calling function)."""
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
            ok = {a.callee for a in allow if (a.file, a.function) == (rel, qual)}
            building.extend((rel, qual, line) for line in _sinks(fn, taint, bound, ok))
            for n in _own(fn):
                if _is_resolver(n) and qual.rsplit(".", 1)[-1] != RESOLVER:
                    callers.add((rel, qual))
    return sorted(set(building)), callers


def test_only_the_resolver_turns_a_stored_manifest_path_into_a_file_path() -> None:
    building, _ = scan(SRC, ROOT)
    assert building == [], (
        "a stored manifest path is used as a file path, or an entry is handed to a helper, "
        f"outside decoy.cli.evidence.resolve_manifest_path; resolve it there: {building}"
    )


def test_the_resolver_is_called_by_exactly_the_allowed_consumers() -> None:
    _, callers = scan(SRC, ROOT)
    assert callers == RESOLVER_CALLERS


def test_allowlist_entries_are_live_and_have_reasons() -> None:
    """A stale entry would let a later helper of the same name take an entry unchecked."""
    keys = {(a.file, a.function, a.callee) for a in ALLOWLIST}
    assert len(keys) == len(ALLOWLIST)
    assert all(len(a.reason) >= 15 for a in ALLOWLIST)
    for a in ALLOWLIST:
        building, _ = scan(SRC, ROOT, tuple(x for x in ALLOWLIST if x is not a))
        assert any((f, q) == (a.file, a.function) for f, q, _l in building), a


def test_baseline_json_records_the_same_entries_and_reasons() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    expected = {f"{a.file}::{a.function}::{a.callee}": {"reason": a.reason} for a in ALLOWLIST}
    assert entries == expected


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
    "tuple_loop": """
from pathlib import Path
def f(manifest_a, manifest_b, t):
    fp_a = manifest_a["output_fingerprints"][t]
    fp_b = manifest_b["output_fingerprints"][t]
    for manifest, entry in ((manifest_a, fp_a), (manifest_b, fp_b)):
        raw = entry["path"]
        yield Path(raw)
""",
    "forward": """
from decoy.cli.io import entry_format, read_file
def f(manifest_a, path_a, table):
    output_fps_a = manifest_a.get("output_fingerprints") or {}
    fp_a = output_fps_a.get(table) or {}
    return read_file(path_a, *entry_format(fp_a), table=table)
""",
    "forward_holder": """
def f(manifest_a, manifest_b, t, helper):
    fp_a = manifest_a["output_fingerprints"][t]
    sides = ((manifest_a, fp_a), (manifest_b, None))
    return helper(sides)
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
from decoy.cli.io import entry_format
def compare_data(m, f):
    fps = m["output_fingerprints"]
    if not isinstance(fps, dict) or len(fps) == 0:
        return None
    for name, entry in fps.items():
        path = resolve_manifest_path(m, entry["path"], manifest_file=f, field=name)
        recorded = {k: entry[k] for k in ("format", "layout") if k in entry}
        if path.exists():
            frame = entry_format(path, **recorded)
            return Path(path), str(entry["path"]), entry.get("path", "?"), frame
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
