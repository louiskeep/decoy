"""Engine internal-boundary sentry for the decoy CLI.

`decoy_engine.internal` and any `_private` engine name are not a public surface: the engine
may move or delete them in any release with no compatibility notice. They also resolve today,
so the resolve-only sentry (`test_engine_import_surface.py`) cannot see the drift coming.
This sentry bans them from `src/decoy` outright, except for an explicit allowlist in which
every entry carries a reason and a removal note.

Scope: static references only, reported as full dotted symbols and counted per file. It sees
imports of any form (aliased, nested, in any scope); attribute chains through any binding that
came from a `decoy_engine` import, an assignment of an engine path, or a literal
`importlib.import_module(...)` / `__import__(...)` (positional, keyword and relative-with-package
forms); and literal `getattr/setattr/hasattr/delattr(<engine path>, "name")`. Bindings are scoped
per module/function/class/lambda, and one name bound to two engine targets in one scope fails as
ambiguous. Not seen (documented limits): names built at run time, tuple-unpacking assignments,
and aliases passed through function calls. Dunder names (`__version__`) are public by Python
convention and are not flagged.
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


def _chain(node: ast.expr) -> list[str] | None:
    """`a.b.c` -> ["a", "b", "c"]; None when the base is not a plain name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def _literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _arg(call: ast.Call, pos: int, keyword: str) -> ast.expr | None:
    if len(call.args) > pos:
        return call.args[pos]
    return next((k.value for k in call.keywords if k.arg == keyword), None)


_REFLECT = {"getattr", "setattr", "hasattr", "delattr"}


def _dynamic_import(call: ast.Call) -> tuple[list[str], list[str]] | None:
    """For a literal `importlib.import_module(...)` / `__import__(...)` of an engine
    module: (path of the value the call returns, every engine path it touches)."""
    callee = _chain(call.func)
    if not callee or callee[-1] not in {"import_module", "__import__"}:
        return None
    name = _literal(_arg(call, 0, "name"))
    if name is None:
        return None
    is_import_module = callee[-1] == "import_module"
    if name.startswith("."):
        package = _literal(_arg(call, 1, "package")) if is_import_module else None
        if package is None:
            return None
        try:
            name = importlib.util.resolve_name(name, package)
        except (ImportError, ValueError):
            return None
    if not _is_engine(name):
        return None
    touched = [name]
    result = name
    if not is_import_module:
        fromlist = _arg(call, 3, "fromlist")
        items = fromlist.elts if isinstance(fromlist, (ast.List, ast.Tuple)) else []
        names = [lit for e in items if (lit := _literal(e))]
        touched += [f"{name}.{n}" for n in names]
        result = name if names else _ENGINE  # __import__ returns the top package without a fromlist
    return result.split("."), [t for t in touched]


def _reflective(call: ast.Call) -> tuple[ast.expr, str] | None:
    """`getattr(obj, "literal"[, ...])` and its set/has/del siblings: (obj, literal)."""
    if isinstance(call.func, ast.Name) and call.func.id in _REFLECT and len(call.args) >= 2:
        lit = _literal(call.args[1])
        if lit is not None:
            return call.args[0], lit
    return None


class _Scan:
    """One file. Scopes (module, function, class, lambda) each own their bindings, filled by
    a pre-pass so a use may precede its import; one name bound to two different engine
    targets in one scope is reported as ambiguous instead of picking one."""

    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.found: list[tuple[str, str, str]] = []
        self.stack: list[dict[str, str]] = []

    def report(self, path: list[str] | str, node: ast.AST) -> None:
        parts = path.split(".") if isinstance(path, str) else path
        if _bad_path(parts):
            self.found.append((self.rel, ".".join(parts), f"{self.rel}:{node.lineno}"))  # type: ignore[attr-defined]

    def lookup(self, name: str) -> str | None:
        return next((s[name] for s in reversed(self.stack) if name in s), None)

    def resolve(self, expr: ast.expr) -> list[str] | None:
        """The engine path an expression denotes, or None."""
        if isinstance(expr, ast.Name):
            found = self.lookup(expr.id)
            return found.split(".") if found else None
        if isinstance(expr, ast.Attribute):
            base = self.resolve(expr.value)
            return [*base, expr.attr] if base else None
        if isinstance(expr, ast.Call):
            if (dyn := _dynamic_import(expr)) is not None:
                return dyn[0]
            if (call := _reflective(expr)) and isinstance(expr.func, ast.Name) and expr.func.id == "getattr":
                base = self.resolve(call[0])
                return [*base, call[1]] if base else None
        return None

    def bind(self, name: str, path: str, node: ast.AST) -> None:
        scope = self.stack[-1]
        if name in scope and scope[name] != path:
            self.found.append(
                (
                    self.rel,
                    f"ambiguous binding of {name!r}: {scope[name]} vs {path}",
                    f"{self.rel}:{node.lineno}",  # type: ignore[attr-defined]
                )
            )
            return
        scope[name] = path

    def prepass(self, body: list[ast.AST]) -> None:
        imports: list[ast.AST] = []
        assigns: list[ast.AST] = []
        todo = list(body)
        while todo:
            node = todo.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                assigns.append(node)
            todo.extend(ast.iter_child_nodes(node))
        key = lambda n: (n.lineno, n.col_offset)  # noqa: E731
        for node in sorted(imports, key=key):
            if isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module and _is_engine(node.module):
                    for a in node.names:
                        if a.name != "*":
                            self.bind(a.asname or a.name, f"{node.module}.{a.name}", node)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if _is_engine(a.name):
                        local = a.asname or a.name.split(".")[0]
                        self.bind(local, a.name if a.asname else _ENGINE, node)
        for node in sorted(assigns, key=key):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if value is None or (path := self.resolve(value)) is None:
                continue
            for t in targets:
                if isinstance(t, ast.Name):
                    self.bind(t.id, ".".join(path), node)

    def scoped(self, body: list[ast.AST]) -> None:
        self.stack.append({})
        self.prepass(body)
        for stmt in body:
            self.visit(stmt)
        self.stack.pop()

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and _is_engine(node.module):
                for a in node.names:
                    self.report(f"{node.module}.{a.name}", node)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if _is_engine(a.name):
                    self.report(a.name, node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args
            outer = [*args.defaults, *(d for d in args.kw_defaults if d is not None)]
            if not isinstance(node, ast.Lambda):
                outer += node.decorator_list
            for expr in outer:
                self.visit(expr)
            self.scoped(node.body if isinstance(node.body, list) else [node.body])
        elif isinstance(node, ast.ClassDef):
            for expr in [*node.bases, *(k.value for k in node.keywords), *node.decorator_list]:
                self.visit(expr)
            self.scoped(node.body)
        elif isinstance(node, (ast.Attribute, ast.Call)) and self.visit_access(node):
            return
        else:
            for child in ast.iter_child_nodes(node):
                self.visit(child)

    def visit_access(self, node: ast.Attribute | ast.Call) -> bool:
        """Report a maximal attribute / reflective access chain once, at its full path.
        False when the node is not such a chain (the caller descends normally)."""
        if isinstance(node, ast.Call):
            if (dyn := _dynamic_import(node)) is not None:
                for touched in dyn[1]:
                    self.report(touched, node)
                return False
            refl = _reflective(node)
            if refl is None:
                return False
            base = self.resolve(refl[0])
            if base is None:
                return False
            self.report([*base, refl[1]], node)
            self.visit_chain_base(refl[0])
            return True
        path = self.resolve(node)
        if path is None:
            return False
        self.report(path, node)
        self.visit_chain_base(node.value)
        return True

    def visit_chain_base(self, node: ast.AST) -> None:
        """Walk down a chain already reported, visiting only a dynamic-import call at its
        root (its own module may be bad); a Name root needs nothing."""
        while True:
            if isinstance(node, ast.Attribute):
                node = node.value
            elif isinstance(node, ast.Call) and (refl := _reflective(node)) and self.resolve(refl[0]):
                node = refl[0]
            else:
                break
        if isinstance(node, ast.Call):
            self.visit(node)


def internal_refs(root: Path) -> list[tuple[str, str, str]]:
    """(relative path, full dotted symbol, "path:line") for every boundary violation."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        scan = _Scan(rel)
        scan.scoped(tree.body)
        found.extend(scan.found)
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


def test_bindings_are_scoped_to_their_function(tmp_path: Path) -> None:
    source = (
        "def f():\n    from decoy_engine import kernel as m\n    return m._cache\n"
        "def g():\n    from decoy_engine import sdk as m\n    return m._other\n"
    )
    assert sorted(_scan(tmp_path, source)) == ["decoy_engine.kernel._cache", "decoy_engine.sdk._other"]


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
