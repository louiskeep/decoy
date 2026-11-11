"""G-ONE-PROJECT-ROOT: `cli/io/_project.py` is the only place that looks for a project marker.

Walks every module under `src/decoy/` and fails when one outside `_project.py`:

- names the marker file as a string (`"decoy.yaml"`, `"sub/decoy.yaml"`), docstrings aside;
- refers to the marker-name constant `MARKER_NAME` (a plain use, an import, an alias or a
  module-qualified spelling);
- loops over `.parents` inside a function that also names a `.yaml` or `.yml` file, which is the
  shape of "walk up looking for a config".

There is no allowlist: any hit is a second root finder. The pipeline-argument half of this file
(G-ONE-PIPELINE-ARG) arrives with the `_pipelines.py` slice.

Named limits: a marker name assembled at run time (`"decoy" + ".yaml"`), `getattr`, and a walk that
reads `os.path.dirname` in a loop are not seen. The rule targets the spellings a contributor
would write by habit.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"
CHOKE_POINT = "cli/io/_project.py"
MARKER_FILE = "decoy.yaml"
MARKER_CONSTANT = "MARKER_NAME"
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, *_SCOPES)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _names_yaml_file(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value.lower().endswith((".yaml", ".yml"))
        for n in ast.walk(node)
    )


def _iterates_parents(node: ast.AST) -> bool:
    loops: list[ast.expr] = []
    for n in ast.walk(node):
        if isinstance(n, (ast.For, ast.AsyncFor)):
            loops.append(n.iter)
        elif isinstance(n, ast.comprehension):
            loops.append(n.iter)
    return any(
        isinstance(inner, ast.Attribute) and inner.attr == "parents"
        for expr in loops
        for inner in ast.walk(expr)
    )


def violations(source: str, rel: str) -> list[str]:
    """Findings (`file:line reason`) for one module's source; empty for the choke point."""
    if rel == CHOKE_POINT:
        return []
    tree = ast.parse(source)
    docs = _docstring_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
            and (node.value == MARKER_FILE or node.value.endswith("/" + MARKER_FILE))
        ):
            found.append(f"{rel}:{line} names the project marker file")
        elif isinstance(node, ast.alias) and node.name.split(".")[-1] == MARKER_CONSTANT:
            found.append(f"{rel}:{line} imports {MARKER_CONSTANT}")
        elif isinstance(node, ast.Name) and node.id == MARKER_CONSTANT:
            found.append(f"{rel}:{line} uses {MARKER_CONSTANT}")
        elif isinstance(node, ast.Attribute) and node.attr == MARKER_CONSTANT:
            found.append(f"{rel}:{line} uses {MARKER_CONSTANT}")
        elif isinstance(node, _SCOPES) and _iterates_parents(node) and _names_yaml_file(node):
            found.append(f"{rel}:{line} walks .parents looking for a YAML file")
    return found


def scan() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        found.extend(violations(path.read_text(encoding="utf-8"), rel))
    return found


def test_no_module_outside_the_project_module_looks_for_a_marker() -> None:
    assert scan() == []


def test_the_choke_point_exists_and_names_the_marker() -> None:
    text = (SRC / CHOKE_POINT).read_text(encoding="utf-8")
    assert f'MARKER_NAME = "{MARKER_FILE}"' in text


@pytest.mark.parametrize(
    "source",
    [
        'from pathlib import Path\nx = Path.cwd() / "decoy.yaml"\n',
        'import os\nx = os.path.join(base, "sub/decoy.yaml")\n',
        'open("decoy.yaml")\n',
        "from decoy.cli.io._project import MARKER_NAME\n",
        "from decoy.cli.io._project import MARKER_NAME as M\nx = p / M\n",
        "from decoy.cli.io import _project\nx = p / _project.MARKER_NAME\n",
        "def f(start):\n    for d in start.parents:\n        if (d / 'decoy.yml').is_file():\n"
        "            return d\n",
        "def f(start):\n    return [d for d in (start, *start.parents) if (d / 'x.yaml').exists()]\n",
    ],
)
def test_each_spelling_of_a_second_root_finder_is_caught(source: str) -> None:
    assert violations(source, "cli/other.py") != []


@pytest.mark.parametrize(
    "source",
    [
        '"""Docstring mentioning decoy.yaml is prose."""\n',
        "def f(p):\n    for a in p.parents:\n        if a.name == 'out':\n            return a\n",
        "x = 'decoy.yaml.bak'\n",
    ],
)
def test_prose_and_unrelated_parent_walks_are_not_flagged(source: str) -> None:
    assert violations(source, "cli/other.py") == []


def test_the_choke_point_itself_is_exempt() -> None:
    assert violations('x = "decoy.yaml"\n', CHOKE_POINT) == []
