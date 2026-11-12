"""G-RUN-SHAPE: `decoy/cli/run/` stays a thin Typer module over small, ordered phase modules.

The `decoy run` command was one 1,737-line module, which let only one branch at a time write it.
It is a package now so the rows that change different parts of the command build in parallel.
This sentry keeps the cut from eroding. It fails when:

- `__init__.py` defines anything at module level besides imports, `__all__`, `_RUN_EPILOG`,
  `RUN_EPILOG` and the one function `run`;
- `run`'s body after its docstring has more than 3 statements, or any compound statement;
- a module under `cli/run/` is longer than 600 lines (the cap is exact; split the module);
- a module imports a sibling that comes later in `ORDER` (the phases form a DAG), or a sibling
  that `ORDER` does not know;
- a module imports `decoy_engine` outside a function (the engine stays off the `--help` path);
- a module imports a private module of the parent package (`decoy.cli._sources`,
  `decoy.cli._duckdb_source`, `decoy.cli.io._targets`, ...) instead of the public facade.

Named limit: the import checks read import statements, so `importlib.import_module("...")` and a
`getattr` on a module are invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
PKG = "cli/run"
PKG_DOTTED = "decoy.cli.run"
MAX_LINES = 600
MAX_RUN_STATEMENTS = 3
# A module may import only modules earlier in this list; `__init__` comes last.
ORDER = (
    "_progress",
    "_context",
    "_notify",
    "_vault",
    "_execute",
    "_prepare",
    "_errors",
    "_render",
    "_evidence",
    "_flow",
    "__init__",
)
_INIT_NAMES = {"__all__", "_RUN_EPILOG", "RUN_EPILOG"}
_COMPOUND = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _imported_modules(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Every dotted module path one import statement names, independent of aliases.

    `from decoy.cli import _sources as s` names `decoy.cli._sources`, so the three common
    spellings of one private import all resolve to the same string.
    """
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    base = node.module or ""
    return [base, *(f"{base}.{a.name}" for a in node.names)]


def _imports(tree: ast.Module) -> list[tuple[ast.Import | ast.ImportFrom, bool]]:
    """Each import statement and whether it sits outside every function."""
    found: list[tuple[ast.Import | ast.ImportFrom, bool]] = []

    def walk(node: ast.AST, in_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            inner = in_function or isinstance(child, _SCOPES)
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                found.append((child, not in_function))
            walk(child, inner)

    walk(tree, False)
    return found


def _init_findings(tree: ast.Module) -> list[str]:
    out: list[str] = []
    functions = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # the module docstring
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            functions += 1
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            if len(body) > MAX_RUN_STATEMENTS:
                out.append(
                    f"__init__.py: run has {len(body)} statements after its docstring, "
                    f"the cap is {MAX_RUN_STATEMENTS}"
                )
            for stmt in body:
                if isinstance(stmt, _COMPOUND):
                    out.append(f"__init__.py:{stmt.lineno}: run has a {type(stmt).__name__}")
            continue
        if isinstance(node, ast.Assign) and all(
            isinstance(t, ast.Name) and t.id in _INIT_NAMES for t in node.targets
        ):
            continue
        what = getattr(node, "name", type(node).__name__)
        out.append(f"__init__.py:{node.lineno}: module-level {type(node).__name__} {what!r}")
    if functions != 1:
        out.append(f"__init__.py: expected exactly one function `run`, found {functions}")
    return out


def _import_findings(name: str, tree: ast.Module) -> list[str]:
    out: list[str] = []
    rank = ORDER.index(name)
    for node, module_level in _imports(tree):
        for mod in _imported_modules(node):
            parts = mod.split(".")
            if module_level and parts[0] == "decoy_engine":
                out.append(f"{name}.py:{node.lineno}: module-level import of {mod}")
            if mod.startswith(PKG_DOTTED + "."):
                sibling = mod[len(PKG_DOTTED) + 1 :].split(".")[0]
                if sibling not in ORDER:
                    out.append(f"{name}.py:{node.lineno}: imports {sibling}, which ORDER lacks")
                elif ORDER.index(sibling) >= rank:
                    out.append(
                        f"{name}.py:{node.lineno}: {name} imports {sibling}, "
                        "which comes later in ORDER"
                    )
                continue
            if parts[:2] == ["decoy", "cli"] and any(p.startswith("_") for p in parts[2:]):
                out.append(
                    f"{name}.py:{node.lineno}: imports the private module {mod}; "
                    "go through the public facade"
                )
    return out


def check_tree(src: Path) -> list[str]:
    """Findings for the `cli/run/` package under `src` (a copy of `src/decoy` in tests)."""
    out: list[str] = []
    for path in sorted((src / PKG).glob("*.py")):
        text = path.read_text(encoding="utf-8")
        name = path.stem
        if len(text.splitlines()) > MAX_LINES:
            out.append(f"{name}.py: {len(text.splitlines())} lines, the cap is {MAX_LINES}")
        tree = ast.parse(text)
        if name == "__init__":
            out += _init_findings(tree)
        if name in ORDER:
            out += _import_findings(name, tree)
        else:
            out.append(f"{name}.py: not listed in ORDER")
    return out


def test_the_run_package_has_the_expected_shape() -> None:
    assert check_tree(SRC) == []


def test_the_scan_sees_every_phase_module() -> None:
    """Non-vacuity: an empty glob would pass the check above."""
    found = {p.stem for p in (SRC / PKG).glob("*.py")}
    assert found == set(ORDER), found ^ set(ORDER)


# -- seeded breaches: each rule must bite on a realistic tree ------------------------------------

_INIT = (
    '"""Doc."""\n'
    "import typer\n"
    "from decoy.cli.run import _flow\n"
    "__all__ = ['run']\n"
    "_RUN_EPILOG = 'x'\n"
    "RUN_EPILOG = _RUN_EPILOG\n"
    "def run(a: int = typer.Argument(1)):\n"
    '    """Help."""\n'
    "    state = 1\n"
    "    _flow.execute(state)\n"
)


def _tree(tmp_path: Path, **modules: str) -> Path:
    pkg = tmp_path / PKG
    pkg.mkdir(parents=True)
    files = {"__init__": _INIT, **{n: "x = 1\n" for n in ORDER[:-1]}, **modules}
    for name, text in files.items():
        (pkg / f"{name}.py").write_text(text, encoding="utf-8")
    return tmp_path


def test_a_clean_seed_tree_passes(tmp_path: Path) -> None:
    assert check_tree(_tree(tmp_path)) == []


def test_a_function_level_engine_import_is_allowed(tmp_path: Path) -> None:
    lazy = "def f():\n    from decoy_engine import run_pipeline\n    return run_pipeline\n"
    assert check_tree(_tree(tmp_path, _execute=lazy)) == []


_SEEDS = {
    "second function in __init__": (
        {"__init__": _INIT + "def helper():\n    return 1\n"},
        "module-level FunctionDef 'helper'",
    ),
    "class in __init__": (
        {"__init__": _INIT + "class Helper:\n    pass\n"},
        "module-level ClassDef 'Helper'",
    ),
    "if in run": (
        {"__init__": _INIT.replace("    state = 1\n", "    if a:\n        pass\n")},
        "run has a If",
    ),
    "fourth statement in run": (
        {"__init__": _INIT.replace("    state = 1\n", "    a = 1\n    b = 2\n    state = 1\n")},
        "run has 4 statements after its docstring",
    ),
    "601-line module": ({"_render": "x = 1\n" * 601}, "_render.py: 601 lines, the cap is 600"),
    "an earlier module imports a later one": (
        {"_context": "from decoy.cli.run import _flow\n"},
        "_context imports _flow, which comes later in ORDER",
    ),
    "a module imports an unknown sibling": (
        {"_flow": "from decoy.cli.run._extra import x\n"},
        "imports _extra, which ORDER lacks",
    ),
    "module-level engine import": (
        {"_execute": "from decoy_engine import run_pipeline\n"},
        "module-level import of decoy_engine",
    ),
    "private import, from-name": (
        {"_execute": "from decoy.cli._sources import read_source\n"},
        "imports the private module decoy.cli._sources",
    ),
    "private import, from-package alias": (
        {"_execute": "from decoy.cli import _sources as sources\n"},
        "imports the private module decoy.cli._sources",
    ),
    "private import, import-as": (
        {"_execute": "import decoy.cli._sources as sources\n"},
        "imports the private module decoy.cli._sources",
    ),
    "private import of the io facade's module": (
        {"_execute": "from decoy.cli.io._targets import write_targets\n"},
        "imports the private module decoy.cli.io._targets",
    ),
}


@pytest.mark.parametrize(("modules", "needle"), list(_SEEDS.values()), ids=list(_SEEDS))
def test_each_breach_is_red(tmp_path: Path, modules: dict[str, str], needle: str) -> None:
    got = check_tree(_tree(tmp_path, **modules))
    assert any(needle in line for line in got), got
