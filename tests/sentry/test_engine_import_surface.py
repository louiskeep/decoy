"""Engine import-surface sentry for the decoy CLI.

The CLI is a thin wrapper over the pinned `decoy-engine`; every name it imports
from `decoy_engine` and every keyword it passes to `run_pipeline` is a frozen
contract with that pin. When the engine deletes a symbol, the CLI only finds out
at the first `--chunked` run (an ImportError at call time, exit 3). This sentry
finds out at test time: it derives the CLI's engine surface from the source by
AST, resolves every name against the installed engine, and fails closed on
anything missing or anything it cannot resolve statically.

Scope: `src/decoy` (the product). Tests are checked only for explicit keywords in
`run_pipeline` calls (the "older engine" fakes forward keywords by name); their
`*args, **kwargs` pass-throughs carry whatever the product passed, which the
product scan already covers.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "decoy"
_TESTS = _ROOT / "tests"
_ENGINE = "decoy_engine"
_GUARD_EXCEPTIONS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


@dataclass(frozen=True)
class EngineRef:
    module: str
    name: str | None  # None: the module itself is imported
    where: str  # "<relative path>:<line>"
    guarded: bool  # inside a try whose handler catches ImportError


@dataclass(frozen=True)
class PipelineCall:
    where: str
    keywords: frozenset[str]
    unresolved: tuple[str, ...] = field(default_factory=tuple)  # fail-closed reasons


def _iter_py(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _is_guarded(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    cur = node
    while cur in parents:
        parent = parents[cur]
        if isinstance(parent, ast.Try) and cur in parent.body:
            for handler in parent.handlers:
                names = (
                    [handler.type]
                    if handler.type is None or not isinstance(handler.type, ast.Tuple)
                    else list(handler.type.elts)
                )
                for t in names:
                    if t is None or (isinstance(t, ast.Name) and t.id in _GUARD_EXCEPTIONS):
                        return True
                    if isinstance(t, ast.Attribute) and t.attr in _GUARD_EXCEPTIONS:
                        return True
        cur = parent
    return False


def collect_engine_refs(root: Path) -> list[EngineRef]:
    """Every `decoy_engine` import (any form, any nesting) plus every direct
    attribute access on a module-level `import decoy_engine` binding."""
    refs: list[EngineRef] = []
    for path in _iter_py(root):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        parents = _parents(tree)
        bare_engine_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module == _ENGINE or node.module.startswith(_ENGINE + "."):
                    guarded = _is_guarded(node, parents)
                    for alias in node.names:
                        refs.append(
                            EngineRef(node.module, alias.name, f"{rel}:{node.lineno}", guarded)
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == _ENGINE or alias.name.startswith(_ENGINE + "."):
                        refs.append(
                            EngineRef(
                                alias.name, None, f"{rel}:{node.lineno}", _is_guarded(node, parents)
                            )
                        )
                        if alias.name == _ENGINE and alias.asname is None:
                            bare_engine_names.add(_ENGINE)
        if not bare_engine_names:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in bare_engine_names
            ):
                refs.append(EngineRef(_ENGINE, node.attr, f"{rel}:{node.lineno}", False))
    return refs


def _resolve(ref: EngineRef) -> str | None:
    """None when the reference resolves against the installed engine, else why not."""
    try:
        module = importlib.import_module(ref.module)
    except ImportError as exc:
        missing = getattr(exc, "name", None) or ""
        if ref.guarded and missing and not missing.startswith(_ENGINE):
            return None  # an optional third-party extra, behind the guard that expects it
        return f"module {ref.module} does not import ({type(exc).__name__})"
    if ref.name is None or hasattr(module, ref.name):
        return None
    try:
        importlib.import_module(f"{ref.module}.{ref.name}")
    except ImportError:
        return f"{ref.module} has no attribute or submodule {ref.name!r}"
    return None


def missing_engine_refs(root: Path) -> list[str]:
    return [
        f"{ref.where}: {reason}"
        for ref in collect_engine_refs(root)
        if (reason := _resolve(ref)) is not None
    ]


# --- run_pipeline keywords ---------------------------------------------------


def _is_run_pipeline_callee(func: ast.expr, *, exact: bool) -> bool:
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    if name is None:
        return False
    return name == "run_pipeline" if exact else name.endswith("run_pipeline")


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
    return None


class _KeyResolver:
    """Static keys of a `**expr` argument: dict displays, `dict(k=...)`,
    `dict(<resolvable>)`, `name["k"] = ...` assignments in the enclosing
    function, and calls to a function defined in this package whose returns
    resolve the same way. Anything else is unresolvable (fail closed)."""

    def __init__(self, root: Path, rel: str, tree: ast.Module):
        self.root, self.rel, self.tree = root, rel, tree
        self.parents = _parents(tree)
        self.unresolved: list[str] = []

    def keys_of(self, expr: ast.expr, scope: ast.AST | None) -> set[str]:
        if isinstance(expr, ast.Dict):
            keys: set[str] = set()
            for k in expr.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
                elif k is None:  # {**other}
                    self._fail(expr, "dict unpacking inside a run_pipeline kwargs dict")
                else:
                    self._fail(expr, "non-literal key in a run_pipeline kwargs dict")
            return keys
        if isinstance(expr, ast.IfExp):
            return self.keys_of(expr.body, scope) | self.keys_of(expr.orelse, scope)
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "dict":
            keys = set()
            for arg in expr.args:
                keys |= self.keys_of(arg, scope)
            for kw in expr.keywords:
                if kw.arg is None:
                    keys |= self.keys_of(kw.value, scope)
                else:
                    keys.add(kw.arg)
            return keys
        if isinstance(expr, ast.Name):
            return self._keys_of_local(expr, scope)
        if isinstance(expr, ast.Call):
            return self._keys_of_call(expr)
        self._fail(expr, f"unresolvable run_pipeline kwargs expression ({type(expr).__name__})")
        return set()

    def _keys_of_local(self, name: ast.Name, scope: ast.AST | None) -> set[str]:
        if scope is None:
            self._fail(name, f"run_pipeline **{name.id} outside a function")
            return set()
        keys: set[str] = set()
        found = False
        for node in ast.walk(scope):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == name.id and node.value:
                        found = True
                        keys |= self.keys_of(node.value, scope)
                    elif (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == name.id
                    ):
                        found = True
                        if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                            keys.add(target.slice.value)
                        else:
                            self._fail(target, f"non-literal key assigned into {name.id}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == name.id:
                    found = True
                    self._fail(node, f"{name.id}.{node.func.attr}(...) mutates run_pipeline kwargs")
        if not found:
            self._fail(name, f"no assignment to run_pipeline **{name.id} in its function")
        return keys

    def _keys_of_call(self, call: ast.Call) -> set[str]:
        func_def = self._find_function(call.func)
        if func_def is None:
            self._fail(call, "run_pipeline **<call> to a function outside this package")
            return set()
        keys: set[str] = set()
        for node in ast.walk(func_def):
            if isinstance(node, ast.Return) and node.value is not None:
                keys |= self.keys_of(node.value, func_def)
        return keys

    def _find_function(self, func: ast.expr) -> ast.FunctionDef | None:
        if isinstance(func, ast.Name):
            return _function_in(self.tree, func.id)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = _imported_module(self.tree, func.value.id)
            if module is None:
                return None
            path = self.root / Path(*module.split(".")[1:]).with_suffix(".py")
            if not path.is_file():
                return None
            return _function_in(ast.parse(path.read_text(encoding="utf-8")), func.attr)
        return None

    def _fail(self, node: ast.AST, why: str) -> None:
        self.unresolved.append(f"{self.rel}:{getattr(node, 'lineno', '?')}: {why}")


def _function_in(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _imported_module(tree: ast.Module, local: str) -> str | None:
    """The `decoy...` module a module-level binding `local` refers to."""
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if (alias.asname or alias.name) == local:
                    return f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name) == local:
                    return alias.name
    return None


def collect_pipeline_calls(root: Path, *, star_kwargs: str) -> list[PipelineCall]:
    """`star_kwargs`: "resolve" (fail closed on anything not statically
    resolvable) or "ignore" (pass-through fakes in tests)."""
    calls: list[PipelineCall] = []
    for path in _iter_py(root):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        resolver = _KeyResolver(root, rel, tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_run_pipeline_callee(node.func, exact=star_kwargs == "resolve"):
                continue
            keywords: set[str] = set()
            resolver.unresolved = []
            scope = _enclosing_function(node, resolver.parents)
            for kw in node.keywords:
                if kw.arg is not None:
                    keywords.add(kw.arg)
                elif star_kwargs == "resolve":
                    keywords |= resolver.keys_of(kw.value, scope)
            calls.append(
                PipelineCall(f"{rel}:{node.lineno}", frozenset(keywords), tuple(resolver.unresolved))
            )
    return calls


def _run_pipeline_parameters() -> set[str] | None:
    """None when `run_pipeline` takes **kwargs (then any keyword is accepted)."""
    engine = importlib.import_module(_ENGINE)
    params = inspect.signature(engine.run_pipeline).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return None
    return {n for n, p in params.items() if p.kind is not inspect.Parameter.VAR_POSITIONAL}


def bad_pipeline_keywords(root: Path, *, star_kwargs: str) -> list[str]:
    accepted = _run_pipeline_parameters()
    problems: list[str] = []
    for call in collect_pipeline_calls(root, star_kwargs=star_kwargs):
        problems.extend(call.unresolved)
        if accepted is None:
            continue
        for kw in sorted(call.keywords - accepted):
            problems.append(f"{call.where}: run_pipeline() has no parameter {kw!r}")
    return problems


# --- the sentry ----------------------------------------------------------------


def test_every_engine_import_resolves_against_the_pinned_engine() -> None:
    """Every `decoy_engine` name the CLI imports or dereferences must exist in
    the installed (lock-pinned) engine. A guarded import may only be excused
    by a missing third-party extra, never by a missing engine symbol."""
    missing = missing_engine_refs(_SRC)
    assert not missing, (
        "The CLI imports engine names the pinned decoy-engine does not provide "
        "(engine API drift; fix the CLI or repin):\n  - " + "\n  - ".join(missing)
    )


def test_every_run_pipeline_keyword_exists_on_the_pinned_engine() -> None:
    """Every keyword the CLI passes to `run_pipeline`, including those reaching
    it through a `**kwargs` dict, must be a parameter of the installed engine's
    `run_pipeline`. Keys that cannot be derived statically fail closed."""
    problems = bad_pipeline_keywords(_SRC, star_kwargs="resolve")
    problems += [f"tests/{p}" for p in bad_pipeline_keywords(_TESTS, star_kwargs="ignore")]
    assert not problems, (
        "run_pipeline keywords not on the pinned decoy-engine (engine API drift):\n  - "
        + "\n  - ".join(problems)
    )


def test_engine_surface_scan_sees_the_whole_cli() -> None:
    """The scan is only as good as its reach: it must find the CLI's real
    engine entry points, so a refactor cannot quietly narrow it to nothing."""
    refs = {(r.module, r.name) for r in collect_engine_refs(_SRC)}
    assert (_ENGINE, "run_pipeline") in refs
    assert (_ENGINE, "run_storm") in refs
    calls = [c.where for c in collect_pipeline_calls(_SRC, star_kwargs="resolve")]
    assert any(w.startswith("cli/run.py:") for w in calls), calls
    assert any(w.startswith("api.py:") for w in calls), calls


# --- negative controls: the mechanism must actually bite --------------------------


def _write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_sentry_flags_a_missing_engine_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mod.py",
        "def f():\n"
        "    from decoy_engine.execution import ExecutionError, no_such_engine_symbol\n"
        "    import decoy_engine.no_such_module\n",
    )
    missing = missing_engine_refs(tmp_path)
    assert len(missing) == 2, missing
    assert any("no_such_engine_symbol" in m and m.startswith("mod.py:2") for m in missing)
    assert any("decoy_engine.no_such_module" in m and m.startswith("mod.py:3") for m in missing)


def test_sentry_does_not_excuse_a_guarded_missing_engine_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mod.py",
        "try:\n    from decoy_engine import no_such_engine_symbol\nexcept ImportError:\n    pass\n",
    )
    assert len(missing_engine_refs(tmp_path)) == 1


def test_sentry_flags_an_attribute_on_the_bare_engine_module(tmp_path: Path) -> None:
    _write(tmp_path, "mod.py", "import decoy_engine\n\ndef f(raw):\n    return decoy_engine.no_such_fn(raw)\n")
    missing = missing_engine_refs(tmp_path)
    assert len(missing) == 1 and "no_such_fn" in missing[0], missing


def test_sentry_flags_a_run_pipeline_keyword_the_engine_lacks(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mod.py",
        "from decoy_engine import run_pipeline\n\n"
        "def helper():\n    return {'no_such_kw_from_helper': 1}\n\n"
        "def f(cfg):\n"
        "    extra = {}\n"
        "    extra['no_such_kw_subscript'] = 1\n"
        "    return run_pipeline(cfg, engine_version='x', no_such_kw_direct=1, **extra, **helper())\n",
    )
    problems = bad_pipeline_keywords(tmp_path, star_kwargs="resolve")
    flagged = {p.split("parameter ")[-1].strip("'") for p in problems}
    assert flagged == {"no_such_kw_direct", "no_such_kw_subscript", "no_such_kw_from_helper"}, problems


def test_sentry_fails_closed_on_an_unresolvable_star_kwargs(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mod.py",
        "from decoy_engine import run_pipeline\n\n"
        "def f(cfg, opts):\n    return run_pipeline(cfg, engine_version='x', **opts)\n",
    )
    problems = bad_pipeline_keywords(tmp_path, star_kwargs="resolve")
    assert len(problems) == 1 and "no assignment" in problems[0], problems


def test_sentry_accepts_keywords_the_engine_has(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mod.py",
        "from decoy_engine import run_pipeline\n\n"
        "def f(cfg, flag):\n"
        "    kw = {'fidelity_report': True} if flag else {}\n"
        "    return run_pipeline(cfg, engine_version='x', vault_writer=None, **kw)\n",
    )
    assert bad_pipeline_keywords(tmp_path, star_kwargs="resolve") == []
