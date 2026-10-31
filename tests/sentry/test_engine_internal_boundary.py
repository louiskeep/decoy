"""Engine internal-boundary sentry for the decoy CLI.

`decoy_engine.internal` and any `_private` engine name are not a public surface: the engine
may move or delete them in any release with no compatibility notice. They also resolve today,
so the resolve-only sentry (`test_engine_import_surface.py`) cannot see the drift coming.
This sentry bans them from `src/decoy` outright, except for an explicit allowlist in which
every entry carries a reason and a removal note.

Counting rule (one sentence): a reference is counted once per import-statement name and once
per maximal attribute/getattr chain through a binding, so `from m import x; x()` is 1 and
`import m; m.x()` is 2 when `m` is bad; a bare use of a from-imported name is not a new reference.

What it sees: imports of any form; attribute chains and literal getattr/setattr/hasattr/delattr
through any name bound to an engine path (import, assignment, walrus, for/with/except target,
comprehension target, literal `import_module` / `__import__` result, any depth); annotations,
decorators, defaults and class bases (string annotations when they parse).

One flat binding table per file, no scope analysis: a name bound anywhere in the file to an
engine path resolves to it everywhere in the file. A name bound to two different engine targets
is reported as "ambiguous binding". Shadowing therefore OVER-flags (a parameter, class attribute
or non-engine rebinding named like an engine alias); the remedy for such a false positive is an
allowlist entry with a reason, or renaming. `except ... as name` names are exempt from the
ambiguity report (they are instances, reused for unrelated exceptions).

Not seen (documented limits): names built at run time, tuple-unpacking assignments, aliases
passed through function calls, and string annotations that do not parse or sit inside a
subscript. Dunder names (`__version__`) are public by Python convention and are not flagged.
"""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "decoy"
_ENGINE = "decoy_engine"


@dataclass(frozen=True)
class AllowedInternal:
    file: str  # path relative to src/decoy
    symbol: str  # full dotted engine symbol exactly as the scan reports it
    count: int  # exact references allowed (imports + attribute/reflective accesses); more or fewer fail
    reason: str
    removal: str  # what has to land, and where, before this entry can be deleted


# Entries are added only when the pinned engine and engine main have no public equivalent.
# One entry per (file, full symbol) with the exact occurrence count: a new symbol, or one more
# reference (import or access) to an allowed symbol, fails until reviewed and listed here.
# A bare use of a name already imported under an entry is the same reviewed symbol.
_NEEDS = "docs/handoffs/inputs/cli-needs-engine-public-api.md"
_LOG = "decoy_engine.internal.logging"
_STRAT = "decoy_engine.execution._strategies.SCALAR_HANDLERS"
_REG = "decoy_engine.validators._registry._REGISTRY"
_LOG_WHY = (
    "Silences the engine's cwd-relative file logger during `decoy ci` and restores its "
    "singleton; the engine has no public logging configuration (only the `Logger` protocol)."
)
_LOG_GONE = f"Engine exports a public logging opt-out ({_NEEDS} #1); then delete this entry."
_STRAT_WHY = "`decoy list/show strategy` reads the live SCALAR_HANDLERS registry; no public listing."
_STRAT_GONE = f"Engine exports a strategy-registry accessor ({_NEEDS} #2); then delete this entry."
_REG_WHY = "`decoy list validators` reads the live validator registry; no public listing."
_REG_GONE = f"Engine exports a validator-name accessor ({_NEEDS} #4); then delete this entry."
ALLOWLIST: tuple[AllowedInternal, ...] = (
    AllowedInternal("ci/engine_logging.py", _LOG, 1, _LOG_WHY, _LOG_GONE),
    AllowedInternal("ci/engine_logging.py", f"{_LOG}.get_logger", 1, _LOG_WHY, _LOG_GONE),
    AllowedInternal("ci/engine_logging.py", f"{_LOG}._LOGGER_INSTANCE", 3, _LOG_WHY, _LOG_GONE),
    AllowedInternal("cli/cockpit.py", _STRAT, 2, _STRAT_WHY, _STRAT_GONE),
    AllowedInternal("cli/cockpit.py", f"{_STRAT}.items", 1, _STRAT_WHY, _STRAT_GONE),
    AllowedInternal("cli/cockpit.py", f"{_STRAT}.get", 1, _STRAT_WHY, _STRAT_GONE),
    AllowedInternal("cli/cockpit.py", f"{_STRAT}.keys", 1, _STRAT_WHY, _STRAT_GONE),
    AllowedInternal(
        "cli/cockpit.py",
        "decoy_engine.checksums._KNOWN_SCHEMES",
        1,
        "`decoy list checksums` reads the live scheme set; no public listing.",
        f"Engine exports a checksum-scheme accessor ({_NEEDS} #3); then delete this entry.",
    ),
    AllowedInternal("cli/cockpit.py", _REG, 1, _REG_WHY, _REG_GONE),
    AllowedInternal("cli/cockpit.py", f"{_REG}.keys", 1, _REG_WHY, _REG_GONE),
)


def _is_private(segment: str) -> bool:
    return segment.startswith("_") and not (segment.startswith("__") and segment.endswith("__"))


def _bad_path(path: list[str]) -> bool:
    """`path[0]` is the engine root; any `internal` / `_private` segment below it is bad."""
    return any(seg == "internal" or _is_private(seg) for seg in path[1:])


def _is_engine(name: str) -> bool:
    return name == _ENGINE or name.startswith(_ENGINE + ".")


def _literal(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _arg(call: ast.Call, pos: int, keyword: str) -> ast.expr | None:
    """An argument by keyword or position, uniformly."""
    for k in call.keywords:
        if k.arg == keyword:
            return k.value
    return call.args[pos] if len(call.args) > pos else None


_REFLECT = {"getattr", "setattr", "hasattr", "delattr"}
_MAX_ALIAS_ROUNDS = 8  # aliases of aliases settle in a few rounds; past this the scan fails closed


def _dynamic_import(call: ast.Call) -> tuple[list[str], list[str]] | None:
    """For a literal `import_module(...)` / `__import__(...)` of an engine module: (path of
    the value the call returns, every engine path it names)."""
    func = call.func
    callee = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
    if callee not in {"import_module", "__import__"}:
        return None
    name = _literal(_arg(call, 0, "name"))
    if name is not None and name.startswith("."):
        package = _literal(_arg(call, 1, "package")) if callee == "import_module" else None
        try:
            name = importlib.util.resolve_name(name, package) if package else None
        except (ImportError, ValueError):
            name = None
    if name is None or not _is_engine(name):
        return None
    if callee == "import_module":
        return name.split("."), [name]
    fromlist = _arg(call, 3, "fromlist")
    items = fromlist.elts if isinstance(fromlist, (ast.List, ast.Tuple)) else []
    touched = [name, *(f"{name}.{lit}" for e in items if (lit := _literal(e)))]
    # `__import__` returns the submodule only when fromlist is truthy; a fromlist that is not
    # a literal is treated as truthy (the conservative reading).
    falsy = fromlist is None or (isinstance(fromlist, (ast.List, ast.Tuple)) and not items)
    falsy = falsy or (isinstance(fromlist, ast.Constant) and not fromlist.value)
    return (_ENGINE if falsy else name).split("."), touched


def _reflective(call: ast.Call) -> tuple[ast.expr, str] | None:
    """`getattr(obj, "literal", ...)` and its set/has/del siblings: (obj, literal)."""
    if isinstance(call.func, ast.Name) and call.func.id in _REFLECT and len(call.args) >= 2:
        if (lit := _literal(call.args[1])) is not None:
            return call.args[0], lit
    return None


class _Scan:
    """One file, one flat binding table: a name bound anywhere in the file to an engine path
    resolves to it everywhere in the file, and a name bound to two different engine targets
    is reported as ambiguous (except-clause names, reused for unrelated exceptions, excepted).
    Shadowing therefore over-flags and never under-flags."""

    def __init__(self, rel: str, tree: ast.Module) -> None:
        self.rel = rel
        self.found: list[tuple[str, str, str]] = []
        self.table: dict[str, dict[str, int]] = {}  # name -> {engine path: first line}
        self.caught: set[str] = set()  # names bound by `except ... as name`
        self.collect(tree)
        for name, paths in self.table.items():
            if len(paths) > 1 and name not in self.caught:
                self.found.append(
                    (rel, f"ambiguous binding of {name!r}: " + " vs ".join(sorted(paths)), f"{rel}:{max(paths.values())}")
                )
        self.visit(tree)

    def bind(self, name: str, path: str, node: ast.AST) -> None:
        self.table.setdefault(name, {}).setdefault(path, node.lineno)  # type: ignore[attr-defined]

    def collect(self, tree: ast.Module) -> None:
        pairs: list[tuple[str, ast.expr, ast.AST, bool]] = []  # (name, value, node, iterates)
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module and _is_engine(n.module):
                for a in n.names:
                    if a.name != "*":
                        self.bind(a.asname or a.name, f"{n.module}.{a.name}", n)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if _is_engine(a.name):
                        self.bind(a.asname or a.name.split(".")[0], a.name if a.asname else _ENGINE, n)
            elif isinstance(n, ast.Assign):
                pairs += [(t.id, n.value, n, False) for t in n.targets if isinstance(t, ast.Name)]
            elif isinstance(n, (ast.AnnAssign, ast.NamedExpr)) and isinstance(n.target, ast.Name):
                if n.value is not None:
                    pairs.append((n.target.id, n.value, n, False))
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                if isinstance(n.target, ast.Name):
                    pairs.append((n.target.id, n.iter, n.target, True))
            elif isinstance(n, ast.withitem) and isinstance(n.optional_vars, ast.Name):
                pairs.append((n.optional_vars.id, n.context_expr, n.optional_vars, False))
            elif isinstance(n, ast.ExceptHandler) and n.name and n.type is not None:
                pairs.append((n.name, n.type, n, False))
                self.caught.add(n.name)
        size = -1
        for _ in range(_MAX_ALIAS_ROUNDS):
            if size == (size := sum(len(v) for v in self.table.values())):
                return
            for name, value, node, iterates in pairs:
                exprs = value.elts if iterates and isinstance(value, (ast.List, ast.Tuple, ast.Set)) else [value]
                for expr in exprs:
                    if (path := self.resolve(expr)) is not None:
                        self.bind(name, ".".join(path), node)
        self.found.append((self.rel, "unstable alias chain", f"{self.rel}:1"))

    def resolve(self, expr: ast.expr) -> list[str] | None:
        """The engine path an expression denotes, or None."""
        if isinstance(expr, ast.Name):
            paths = self.table.get(expr.id)
            # several paths only for an `except` name: prefer a bad one so nothing is dropped
            return min(paths, key=lambda p: (not _bad_path(p.split(".")), p)).split(".") if paths else None
        if isinstance(expr, ast.NamedExpr):
            return self.resolve(expr.value)
        if isinstance(expr, ast.Attribute):
            base = self.resolve(expr.value)
            return [*base, expr.attr] if base else None
        if isinstance(expr, ast.Call):
            if (dyn := _dynamic_import(expr)) is not None:
                return dyn[0]
            if (refl := _reflective(expr)) and getattr(expr.func, "id", "") == "getattr":
                base = self.resolve(refl[0])
                return [*base, refl[1]] if base else None
        return None

    def report(self, path: list[str] | str, node: ast.AST) -> None:
        parts = path.split(".") if isinstance(path, str) else path
        if _bad_path(parts):
            self.found.append((self.rel, ".".join(parts), f"{self.rel}:{node.lineno}"))  # type: ignore[attr-defined]

    def access_path(self, node: ast.AST) -> list[str] | None:
        """The full engine path of a maximal attribute / reflective-access chain."""
        if isinstance(node, ast.Attribute):
            return self.resolve(node)
        if isinstance(node, ast.Call) and (refl := _reflective(node)):
            base = self.resolve(refl[0])
            return [*base, refl[1]] if base else None
        return None

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and _is_engine(node.module):
                for a in node.names:
                    self.report(f"{node.module}.{a.name}", node)
            return
        if isinstance(node, ast.Import):
            for a in node.names:
                if _is_engine(a.name):
                    self.report(a.name, node)
            return
        if (path := self.access_path(node)) is not None:
            self.report(path, node)
            self.visit_chain(node, ".".join(path))
            return
        if isinstance(node, ast.Call) and (dyn := _dynamic_import(node)):
            for touched in dyn[1]:
                self.report(touched, node)
        for ann in (getattr(node, "annotation", None), getattr(node, "returns", None)):
            if (text := _literal(ann)) is not None:  # string annotation: scan it when it parses
                try:
                    parsed = ast.parse(text.strip(), mode="eval")
                except SyntaxError:
                    continue
                ast.increment_lineno(parsed, ann.lineno - 1)  # type: ignore[union-attr]
                self.visit(parsed.body)
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    def visit_chain(self, node: ast.AST, full: str) -> None:
        """Descend a chain already reported as `full`: visit what is not on its spine (the
        remaining reflective-call arguments), and report a dynamic-import root's module only
        if the chain's path does not already contain it."""
        while True:
            if isinstance(node, (ast.Attribute, ast.NamedExpr)):
                node = node.value
            elif isinstance(node, ast.Call) and (refl := _reflective(node)) and self.resolve(refl[0]):
                for extra in [*node.args[1:], *(k.value for k in node.keywords)]:
                    self.visit(extra)
                node = refl[0]
            else:
                break
        if isinstance(node, ast.Call) and (dyn := _dynamic_import(node)):
            for touched in dyn[1]:
                if full != touched and not full.startswith(touched + "."):
                    self.report(touched, node)
            for child in ast.iter_child_nodes(node):
                self.visit(child)


def internal_refs(root: Path) -> list[tuple[str, str, str]]:
    """(relative path, full dotted symbol, "path:line") for every boundary violation."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            rel = path.relative_to(root).as_posix()
            found.extend(_Scan(rel, ast.parse(path.read_text(encoding="utf-8"), filename=rel)).found)
    return found


def unallowed_internal_refs(
    root: Path, allowlist: tuple[AllowedInternal, ...] = ALLOWLIST
) -> list[str]:
    """Occurrences of a (file, symbol) beyond what its entry allows; no entry allows none."""
    allowed = {(a.file, a.symbol): a.count for a in allowlist}
    by_key: dict[tuple[str, str], list[str]] = {}
    for rel, symbol, where in internal_refs(root):
        by_key.setdefault((rel, symbol), []).append(where)
    return [
        f"{', '.join(wheres)}: {symbol} ({len(wheres)} found, {allowed.get((rel, symbol), 0)} allowed)"
        for (rel, symbol), wheres in by_key.items()
        if len(wheres) > allowed.get((rel, symbol), 0)
    ]


# --- the sentry ----------------------------------------------------------------


def test_cli_does_not_import_engine_internals() -> None:
    """No `decoy_engine.internal.*` or engine `_private` reference in `src/decoy`
    outside the allowlist."""
    problems = unallowed_internal_refs(_SRC)
    assert not problems, (
        "The CLI reaches into engine internals (not a public surface; the engine may "
        "move them without notice). Use the public export, or if none exists list the "
        "needed symbol in docs/handoffs/inputs/cli-needs-engine-public-api.md and add an "
        "ALLOWLIST entry with a removal note:\n  - " + "\n  - ".join(problems)
    )


def allowlist_problems(
    root: Path, allowlist: tuple[AllowedInternal, ...] = ALLOWLIST
) -> list[str]:
    live: dict[tuple[str, str], int] = {}
    for rel, symbol, _ in internal_refs(root):
        live[(rel, symbol)] = live.get((rel, symbol), 0) + 1
    problems: list[str] = []
    for entry in allowlist:
        if not entry.reason.strip() or not entry.removal.strip():
            problems.append(f"entry lacks a reason or removal note: {entry.file} {entry.symbol}")
        if entry.count < 1:
            problems.append(f"entry count must be >= 1: {entry.file} {entry.symbol}")
        now = live.get((entry.file, entry.symbol), 0)
        if now != entry.count:
            problems.append(
                f"stale or wrong count ({now} live, {entry.count} listed): {entry.file} {entry.symbol}"
            )
    keys = [(a.file, a.symbol) for a in allowlist]
    if len(set(keys)) != len(keys):
        problems.append("duplicate allowlist entry")
    return problems


def test_every_allowlist_entry_is_justified_and_still_needed() -> None:
    """The allowlist may only shrink: an entry needs a reason and a removal note, and its
    count must equal the live references (a fixed site must lower or drop its entry)."""
    problems = allowlist_problems(_SRC)
    assert not problems, "\n  - ".join(["allowlist is out of date:", *problems])


def test_allowlist_hygiene_check_bites(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("import decoy_engine.internal.fs\n", encoding="utf-8")
    ok = AllowedInternal("x.py", "decoy_engine.internal.fs", 1, "r", "x")
    assert allowlist_problems(tmp_path, (ok,)) == []
    bad = {
        "stale": AllowedInternal("x.py", "decoy_engine.internal.base", 1, "r", "x"),
        "too many": AllowedInternal("x.py", "decoy_engine.internal.fs", 2, "r", "x"),
        "no reason": AllowedInternal("x.py", "decoy_engine.internal.fs", 1, " ", "x"),
        "no removal": AllowedInternal("x.py", "decoy_engine.internal.fs", 1, "r", ""),
        "zero": AllowedInternal("x.py", "decoy_engine.internal.fs", 0, "r", "x"),
    }
    for name, entry in bad.items():
        assert allowlist_problems(tmp_path, (entry,)), name
    assert allowlist_problems(tmp_path, (ok, ok)), "duplicate"


def test_boundary_scan_reaches_nested_packages(tmp_path: Path) -> None:
    """A violation in a deep subpackage is found: a refactor cannot narrow the walk."""
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "mod.py").write_text("import decoy_engine.internal.fs\n", encoding="utf-8")
    assert [rel for rel, _, _ in internal_refs(tmp_path)] == ["a/b/mod.py"]


# --- negative controls: the mechanism must actually bite --------------------------


def _scan(tmp_path: Path, source: str) -> list[str]:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    return [ref for _, ref, _ in internal_refs(tmp_path)]


def test_flags_each_import_shape_of_an_internal_module(tmp_path: Path) -> None:
    shapes = {
        "import decoy_engine.internal.logging\n": ["decoy_engine.internal.logging"],
        "import decoy_engine.internal.logging as lg\n": ["decoy_engine.internal.logging"],
        "from decoy_engine.internal.faker_setup import get_faker_providers\n": [
            "decoy_engine.internal.faker_setup.get_faker_providers"
        ],
        "from decoy_engine.internal import faker_setup\n": ["decoy_engine.internal.faker_setup"],
        "from decoy_engine import internal\n": ["decoy_engine.internal"],
        "def f():\n    from decoy_engine.internal.fs import x\n": ["decoy_engine.internal.fs.x"],
        "try:\n    import decoy_engine.internal.base\nexcept ImportError:\n    pass\n": [
            "decoy_engine.internal.base"
        ],
    }
    for source, expected in shapes.items():
        assert _scan(tmp_path, source) == expected, source


def test_flags_private_engine_names(tmp_path: Path) -> None:
    assert _scan(tmp_path, "from decoy_engine import _hidden\n") == ["decoy_engine._hidden"]
    assert _scan(tmp_path, "from decoy_engine.kernel import _impl\n") == [
        "decoy_engine.kernel._impl"
    ]
    assert _scan(tmp_path, "import decoy_engine._core\n") == ["decoy_engine._core"]
    assert _scan(tmp_path, "from decoy_engine._core.x import y\n") == ["decoy_engine._core.x.y"]


def test_flags_private_attribute_reads_through_any_engine_binding(tmp_path: Path) -> None:
    assert _scan(tmp_path, "import decoy_engine\nx = decoy_engine._state\n") == [
        "decoy_engine._state"
    ]
    assert _scan(tmp_path, "import decoy_engine\nx = decoy_engine.internal.logging\n") == [
        "decoy_engine.internal.logging"
    ]
    assert _scan(tmp_path, "from decoy_engine import kernel\nkernel._cache.clear()\n") == [
        "decoy_engine.kernel._cache.clear"
    ]
    assert _scan(tmp_path, "import decoy_engine.kernel as k\nk._cache = None\n") == [
        "decoy_engine.kernel._cache"
    ]


def test_flags_literal_dynamic_imports(tmp_path: Path) -> None:
    source = (
        "import importlib\n"
        "m = importlib.import_module('decoy_engine.internal.logging')\n"
        "n = __import__('decoy_engine.internal.base')\n"
    )
    assert _scan(tmp_path, source) == ["decoy_engine.internal.logging", "decoy_engine.internal.base"]


def test_does_not_flag_public_engine_use_or_unrelated_private_names(tmp_path: Path) -> None:
    source = (
        "import decoy_engine\n"
        "from decoy_engine import run_pipeline, list_generate_faker_providers\n"
        "from decoy_engine.keyprovider import make_key_resolver\n"
        "import decoy_engine.sdk as sdk\n"
        "v = decoy_engine.__version__\n"
        "class C:\n    _own = 1\n"
        "c = C()._own\n"
        "from other_pkg.internal import thing\n"
        "import other_pkg._private\n"
        "import importlib\nimportlib.import_module('other_pkg.internal')\n"
        "sdk.run_config_only_checks\n"
    )
    assert _scan(tmp_path, source) == []


def test_allowlist_excuses_exactly_its_file_and_ref(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import decoy_engine.internal.logging\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("import decoy_engine.internal.logging\n", encoding="utf-8")
    allow = (AllowedInternal("ok.py", "decoy_engine.internal.logging", 1, "r", "x"),)
    left = unallowed_internal_refs(tmp_path, allow)
    assert len(left) == 1 and left[0].startswith("other.py:1"), left


# --- remediation round 1: red-first controls ------------------------------------------


def test_allowlist_does_not_cover_a_new_symbol_in_an_allowlisted_file(tmp_path: Path) -> None:
    """Granularity: an entry excuses its own symbol, not everything else under the same
    truncated prefix."""
    (tmp_path / "x.py").write_text(
        "import decoy_engine.internal.logging\nimport decoy_engine.internal.fs\n", encoding="utf-8"
    )
    allow = (AllowedInternal("x.py", "decoy_engine.internal.logging", 1, "r", "x"),)
    assert unallowed_internal_refs(tmp_path, allow), "new internal symbol folded into old entry"


def test_allowlist_does_not_cover_a_second_private_read_under_one_prefix(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text(
        "from decoy_engine.execution._strategies import SCALAR_HANDLERS\n"
        "from decoy_engine.execution._strategies import OTHER_PRIVATE\n",
        encoding="utf-8",
    )
    allow = (
        AllowedInternal("x.py", "decoy_engine.execution._strategies.SCALAR_HANDLERS", 1, "r", "x"),
    )
    left = unallowed_internal_refs(tmp_path, allow)
    assert left, "a second private symbol folded into the first entry"


def test_flags_relative_and_keyword_dynamic_imports(tmp_path: Path) -> None:
    for source in (
        "import importlib\nimportlib.import_module('.internal.fs', 'decoy_engine')\n",
        "import importlib\nimportlib.import_module('.internal.fs', package='decoy_engine')\n",
        "import importlib\nimportlib.import_module(name='decoy_engine.internal.fs')\n",
        "import importlib\nimportlib.import_module(package='decoy_engine', name='.internal.fs')\n",
        "__import__(name='decoy_engine.internal.fs')\n",
        "__import__('decoy_engine', fromlist=['internal'])\n",
    ):
        assert len(_scan(tmp_path, source)) == 1, source


def test_tracks_the_value_a_dynamic_import_returns(tmp_path: Path) -> None:
    assert _scan(
        tmp_path,
        "import importlib\nm = importlib.import_module('decoy_engine.kernel')\nm._cache\n",
    ) == ["decoy_engine.kernel._cache"]
    assert _scan(
        tmp_path,
        "import importlib\nimportlib.import_module('decoy_engine.kernel')._cache\n",
    ) == ["decoy_engine.kernel._cache"]
    assert _scan(tmp_path, "import decoy_engine\nk = decoy_engine.kernel\nk._cache\n") == [
        "decoy_engine.kernel._cache"
    ]


def test_flags_reflective_access_with_a_literal_name(tmp_path: Path) -> None:
    for source in (
        "import decoy_engine\ngetattr(decoy_engine, '_state')\n",
        "import decoy_engine\ngetattr(decoy_engine, '_state', None)\n",
        "from decoy_engine import kernel\nsetattr(kernel, '_cache', 1)\n",
        "from decoy_engine import kernel\nhasattr(kernel, '_cache')\n",
        "from decoy_engine import kernel\ndelattr(kernel, '_cache')\n",
        "import decoy_engine\ngetattr(decoy_engine.kernel, '_cache')\n",
        "import decoy_engine\ngetattr(decoy_engine, 'internal')\n",
    ):
        assert len(_scan(tmp_path, source)) == 1, source
    for source in (
        "import decoy_engine\ngetattr(decoy_engine, 'run_pipeline')\n",
        "import decoy_engine\nname = 'x'\ngetattr(decoy_engine, name)\n",
        "o = object()\ngetattr(o, '_private')\n",
    ):
        assert _scan(tmp_path, source) == [], source


def test_one_name_bound_to_two_engine_targets_fails_closed(tmp_path: Path) -> None:
    source = (
        "from decoy_engine import kernel as m\nfrom decoy_engine import sdk as m\nm.fine\n"
    )
    assert any("ambiguous" in r for r in _scan(tmp_path, source))


def test_allowlist_count_is_exact_not_a_floor(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text(
        "import decoy_engine.internal.logging as a\n"
        "a.get_logger()\n"
        "a.get_logger()\n",
        encoding="utf-8",
    )
    allow = (
        AllowedInternal("x.py", "decoy_engine.internal.logging", 1, "r", "x"),
        AllowedInternal("x.py", "decoy_engine.internal.logging.get_logger", 1, "r", "x"),
    )
    left = unallowed_internal_refs(tmp_path, allow)
    assert len(left) == 1 and "get_logger" in left[0] and "2 found, 1 allowed" in left[0], left


def test_scopes_and_expression_shapes_the_scan_must_cover(tmp_path: Path) -> None:
    cases = {
        "def f():\n    return k._c\nimport decoy_engine.kernel as k\n": ["decoy_engine.kernel._c"],
        "class C:\n    def f(self):\n        import decoy_engine\n        return decoy_engine._s\n": [
            "decoy_engine._s"
        ],
        "import decoy_engine\nf = lambda x=decoy_engine._s: x\n": ["decoy_engine._s"],
        "import decoy_engine\n[decoy_engine._s for _ in range(2)]\n": ["decoy_engine._s"],
        "import decoy_engine\ngetattr(getattr(decoy_engine, 'kernel'), '_c')\n": [
            "decoy_engine.kernel._c"
        ],
        "from decoy_engine import kernel as m\nfrom decoy_engine import kernel as m\nm.ok\n": [],
        "import other\nother._p\nfrom other import internal\ninternal.x\n": [],
        "x = 'decoy_engine.internal.logging'\n": [],
    }
    for source, expected in cases.items():
        assert _scan(tmp_path, source) == expected, source


# --- remediation round 2: red-first controls ------------------------------------------

_IMPORT_DE = "import decoy_engine\n"


def test_annotations_are_scanned(tmp_path: Path) -> None:
    for source in (
        "def f(x: decoy_engine._T): ...\n",
        "def f(x: decoy_engine._T, /): ...\n",
        "def f(*a: decoy_engine._T): ...\n",
        "def f(*, k: decoy_engine._T): ...\n",
        "def f(**kw: decoy_engine._T): ...\n",
        "def f() -> decoy_engine._T: ...\n",
        "async def f(x: decoy_engine._T) -> None: ...\n",
        "v: decoy_engine._T = 1\n",
        "class C(decoy_engine._T): ...\n",
        "class C(metaclass=decoy_engine._T): ...\n",
        "def f(x: 'decoy_engine._T'): ...\n",
        "def f() -> 'decoy_engine._T': ...\n",
        "v: 'decoy_engine._T' = 1\n",
    ):
        assert _scan(tmp_path, _IMPORT_DE + source) == ["decoy_engine._T"], source
    # an unparseable string annotation is a documented limit, not a crash
    assert _scan(tmp_path, _IMPORT_DE + "def f(x: 'not ((valid'): ...\n") == []


def test_reflective_calls_keep_their_other_arguments(tmp_path: Path) -> None:
    for source, expected in (
        ("getattr(decoy_engine, '_a', decoy_engine._b)\n", ["decoy_engine._a", "decoy_engine._b"]),
        (
            "setattr(decoy_engine.kernel, '_c', decoy_engine.internal.x)\n",
            ["decoy_engine.kernel._c", "decoy_engine.internal.x"],
        ),
        ("hasattr(decoy_engine, '_a', default=decoy_engine._b)\n", ["decoy_engine._a", "decoy_engine._b"]),
    ):
        assert sorted(_scan(tmp_path, _IMPORT_DE + source)) == sorted(expected), source


def test_every_binding_construct_registers_an_engine_alias(tmp_path: Path) -> None:
    imp = "import importlib\n"
    cases = (
        (imp + "(m := importlib.import_module('decoy_engine.kernel'))\nm._c\n", ["decoy_engine.kernel._c"]),
        (imp + "(m := importlib.import_module('decoy_engine.kernel'))._c\n", ["decoy_engine.kernel._c"]),
        (_IMPORT_DE + "for m in (decoy_engine.kernel,):\n    m._c\n", ["decoy_engine.kernel._c"]),
        (_IMPORT_DE + "x = [m._c for m in (decoy_engine.kernel,)]\n", ["decoy_engine.kernel._c"]),
        (
            imp + "with importlib.import_module('decoy_engine.kernel') as m:\n    m._c\n",
            ["decoy_engine.kernel._c"],
        ),
        (
            _IMPORT_DE + "try:\n    pass\nexcept decoy_engine.errors.DecoyError as e:\n    e._detail\n",
            ["decoy_engine.errors.DecoyError._detail"],
        ),
    )
    for source, expected in cases:
        assert _scan(tmp_path, source) == expected, source


def test_dunder_import_with_a_non_literal_fromlist_returns_the_submodule(tmp_path: Path) -> None:
    for source in (
        "v = 'a'\nm = __import__('decoy_engine.kernel', fromlist=[v])\nm._cache\n",
        "v = ['a']\nm = __import__('decoy_engine.kernel', fromlist=v)\nm._cache\n",
        "v = ['a']\nm = __import__('decoy_engine.kernel', None, None, v)\nm._cache\n",
    ):
        assert _scan(tmp_path, source) == ["decoy_engine.kernel._cache"], source
    # an empty / absent fromlist returns the top package
    assert _scan(tmp_path, "m = __import__('decoy_engine.kernel')\nm.sdk\n") == []


def test_a_dynamic_import_at_the_root_of_a_chain_is_reported_once(tmp_path: Path) -> None:
    imp = "import importlib\n"
    assert _scan(tmp_path, imp + "importlib.import_module('decoy_engine.internal.logging').get_logger()\n") == [
        "decoy_engine.internal.logging.get_logger"
    ]
    # the touched module is not a prefix of the chain here, so it is still reported
    assert _scan(tmp_path, "__import__('decoy_engine.internal.x').sdk\n") == ["decoy_engine.internal.x"]


def test_counting_rule_one_per_import_name_and_one_per_access_chain(tmp_path: Path) -> None:
    """A reference is counted once per import-statement name and once per maximal
    attribute/getattr chain; a bare use of a from-imported name is not a new reference."""
    from_form = "from decoy_engine.internal.logging import get_logger\nget_logger()\nget_logger()\n"
    assert _scan(tmp_path, from_form) == ["decoy_engine.internal.logging.get_logger"]
    module_form = "import decoy_engine.internal.logging as L\nL.get_logger()\nL.get_logger()\n"
    assert _scan(tmp_path, module_form) == [
        "decoy_engine.internal.logging",
        "decoy_engine.internal.logging.get_logger",
        "decoy_engine.internal.logging.get_logger",
    ]


def test_dynamic_import_arguments_are_read_uniformly_by_keyword_or_position(tmp_path: Path) -> None:
    imp = "import importlib\n"
    for source, expected in (
        (imp + "importlib.import_module(name='.internal.fs', package='decoy_engine')\n", "decoy_engine.internal.fs"),
        (imp + "importlib.import_module('.internal.fs', package='decoy_engine')\n", "decoy_engine.internal.fs"),
        (imp + "importlib.import_module(package='decoy_engine', name='.internal.fs')\n", "decoy_engine.internal.fs"),
        ("__import__('decoy_engine', fromlist=['internal'])\n", "decoy_engine.internal"),
        ("__import__('decoy_engine', None, None, fromlist=['internal'])\n", "decoy_engine.internal"),
        ("__import__('decoy_engine', globals(), locals(), ['internal'])\n", "decoy_engine.internal"),
        (
            "__import__(name='decoy_engine', globals=None, locals=None, fromlist=['internal'], level=0)\n",
            "decoy_engine.internal",
        ),
    ):
        assert _scan(tmp_path, source) == [expected], source


def test_one_flat_binding_table_per_file_over_flags_shadowing(tmp_path: Path) -> None:
    """Documented over-flags: a name bound anywhere in the file to an engine path resolves to
    it everywhere in the file (class bodies, parameters, non-engine rebinding included), and
    one name bound to two engine targets anywhere in the file is ambiguous."""
    cases = (
        "from decoy_engine import kernel\ndef f(kernel):\n    return kernel._c\n",
        "import decoy_engine as e\ne = object()\ne._p\n",
        "class C:\n    import decoy_engine.kernel as k\n    def f(self):\n        return k._c\n",
        "def f():\n    import decoy_engine.kernel as m\n\ndef g():\n    m = 1\n    return m._c\n",
    )
    for source in cases:
        assert _scan(tmp_path, source), source
    two_functions = (
        "def f():\n    from decoy_engine import kernel as m\n"
        "def g():\n    from decoy_engine import sdk as m\n"
    )
    assert any("ambiguous" in r for r in _scan(tmp_path, two_functions))


def test_except_names_are_not_ambiguous_but_never_hide_a_bad_path(tmp_path: Path) -> None:
    clean = (
        "import decoy_engine\n"
        "try:\n    pass\nexcept decoy_engine.A as e:\n    e.args\n"
        "try:\n    pass\nexcept decoy_engine.B as e:\n    e.args\n"
    )
    assert _scan(tmp_path, clean) == []
    with_bad = clean.replace("decoy_engine.A", "decoy_engine.internal.errors.X")
    assert sorted(_scan(tmp_path, with_bad)) == [
        "decoy_engine.internal.errors.X",
        "decoy_engine.internal.errors.X.args",
        "decoy_engine.internal.errors.X.args",
    ]


def test_alias_chains_resolve_and_a_chain_past_the_round_cap_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    forward = "import decoy_engine\na = decoy_engine.kernel\nb = a\nc = b\nc._x\n"
    assert _scan(tmp_path, forward) == ["decoy_engine.kernel._x"]
    # bound last-to-first, each alias needs one more round than the one before it
    reverse = "import decoy_engine\nd = c\nc = b\nb = a\na = decoy_engine.kernel\nd._x\n"
    assert _scan(tmp_path, reverse) == ["decoy_engine.kernel._x"]
    monkeypatch.setitem(globals(), "_MAX_ALIAS_ROUNDS", 2)
    assert "unstable alias chain" in _scan(tmp_path, reverse)


# --- remediation round 3: red-first controls ------------------------------------------

_TRY = "try:\n    pass\nexcept {} as e:\n    pass\n"


def test_an_except_name_with_any_other_binding_is_not_exempt(tmp_path: Path) -> None:
    """The exemption holds only when every binding of the name is an except clause; one
    other binding makes two engine targets ambiguous again, so a mis-attributed access
    cannot pass under an entry written for the other target."""
    exc = _TRY.format("decoy_engine.errors.DecoyError")
    other_bindings = (
        "e = decoy_engine.kernel\n",
        "from decoy_engine import kernel as e\n",
        "for e in (decoy_engine.kernel,):\n    pass\n",
        "(e := decoy_engine.kernel)\n",
        "import importlib\nwith importlib.import_module('decoy_engine.kernel') as e:\n    pass\n",
    )
    for binding in other_bindings:
        source = _IMPORT_DE + binding + exc + "e._cache\n"
        assert any("ambiguous" in r for r in _scan(tmp_path, source)), binding
        (tmp_path / "mod.py").write_text(source, encoding="utf-8")
        hide = (AllowedInternal("mod.py", "decoy_engine.errors.DecoyError._cache", 1, "r", "x"),)
        assert unallowed_internal_refs(tmp_path, hide), binding
    # a parameter is a non-except binding too: two except targets plus a parameter is ambiguous
    two = _TRY.format("decoy_engine.A") + _TRY.format("decoy_engine.B")
    param = _IMPORT_DE + two + "def f(e):\n    return e._x\n"
    assert any("ambiguous" in r for r in _scan(tmp_path, param))


def test_tuple_handler_types_register_each_engine_member(tmp_path: Path) -> None:
    cases = (
        (
            _TRY.format("(decoy_engine.errors.A, ValueError)") + "e._detail\n",
            ["decoy_engine.errors.A._detail"],
        ),
        (
            _TRY.format("(ValueError, decoy_engine.errors._Hidden)") + "e.args\n",
            ["decoy_engine.errors._Hidden", "decoy_engine.errors._Hidden.args"],
        ),
        (_TRY.format("(ValueError, OSError)") + "e._x\n", []),
    )
    for source, expected in cases:
        assert sorted(_scan(tmp_path, _IMPORT_DE + source)) == expected, source


def test_a_pure_except_name_reused_across_unrelated_handlers_stays_exempt(tmp_path: Path) -> None:
    source = _IMPORT_DE + "".join(
        _TRY.format(t) + "e.args\n"
        for t in (
            "decoy_engine.A",
            "decoy_engine.plan.B",
            "ValueError",
            "(decoy_engine.C, OSError)",
            "(decoy_engine.D, decoy_engine.E)",
        )
    )
    assert _scan(tmp_path, source) == []
