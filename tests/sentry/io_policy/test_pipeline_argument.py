"""G-ONE-PROJECT-ROOT: `cli/io/_project.py` is the only place that looks for a project marker.

Walks every module under `src/decoy/` and fails when one outside `_project.py`:

- names the marker file as a string (`"decoy.yaml"`, `"sub/decoy.yaml"`), docstrings aside;
- refers to the marker-name constant `MARKER_NAME` (a plain use, an import, an alias or a
  module-qualified spelling);
- loops over `.parents` inside a function that also names a `.yaml` or `.yml` file, which is the
  shape of "walk up looking for a config".

There is no allowlist: any hit is a second root finder.

G-ONE-PIPELINE-ARG (second half of this file): `cli/io/_pipelines.py` is the only parser of a
pipeline token. The test walks the Typer app (registered commands and groups, recursively, the
hidden `validate` default handler included) and fails for any parameter that takes a pipeline
YAML without `callback=parse_pipeline_token` and `autocompletion=pipeline_names`, or whose
command body does not call `resolve_pipeline` on it after `setup_output`. It also bans private
Typer imports under `src/` and any `DECOY_PROJECT` literal outside `_pipelines.py`. There is
no allowlist: a parameter outside the 12 is a new command and joins `EXPECTED` on purpose.

Named limits: a marker name assembled at run time (`"decoy" + ".yaml"`), `getattr`, and a walk that
reads `os.path.dirname` in a loop are not seen. The rule targets the spellings a contributor
would write by habit.
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Annotated

import pytest
import typer
from typer.models import ArgumentInfo, OptionInfo

from decoy.cli.completers import pipeline_names
from decoy.cli.io import parse_pipeline_token, pipeline_argument, pipeline_option

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


# --- G-ONE-PIPELINE-ARG --------------------------------------------------------------------

_NAMES = {"config", "pipeline_config", "pipeline"}
# A help text that opens by describing the parameter itself as a pipeline config. `--master-key`
# only mentions the YAML in passing, so it does not match.
_HELP_RULE = re.compile(
    r"^(path to the )?(yaml pipeline|pipeline yaml|pipeline config)|^the pipeline config"
    r"|^optional pipeline\.yaml|^path or name of the (yaml )?pipeline",
    re.IGNORECASE,
)
EXPECTED = {
    "run:config",
    "validate config:config",
    "validate _gate:config",
    "validate compile:config",
    "validate preflight:config",
    "tokenize:config",
    "detokenize:config",
    "unmask:config",
    "subset:config",
    "report fidelity:pipeline_config",
    "report integrity:config",
    "report vault:config",
}


def typer_commands(
    instance: typer.Typer, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, Callable]]:
    """Every command of the app by its path, groups followed recursively."""
    for info in instance.registered_commands:
        assert info.callback is not None
        name = info.name or info.callback.__name__.replace("_", "-")
        yield " ".join((*prefix, name)), info.callback
    for group in instance.registered_groups:
        assert group.name is not None
        yield from typer_commands(group.typer_instance, (*prefix, group.name))


def pipeline_parameters(callback: Callable) -> Iterator[tuple[str, ArgumentInfo | OptionInfo]]:
    for pname, param in inspect.signature(callback).parameters.items():
        info = param.default
        if not isinstance(info, (ArgumentInfo, OptionInfo)):
            continue
        decls = getattr(info, "param_decls", None) or ()
        if pname in _NAMES or "--config" in decls or _HELP_RULE.match(str(info.help or "")):
            yield pname, info


def parameter_findings(instance: typer.Typer) -> tuple[set[str], list[str]]:
    """The matched parameters (`command:param`) and the ones missing the shared hooks."""
    matched: set[str] = set()
    findings: list[str] = []
    for path, callback in typer_commands(instance):
        for pname, info in pipeline_parameters(callback):
            key = f"{path}:{pname}"
            matched.add(key)
            if info.callback is not parse_pipeline_token:
                findings.append(f"{key} lacks callback=parse_pipeline_token")
            if info.autocompletion is not pipeline_names:
                findings.append(f"{key} lacks autocompletion=pipeline_names")
    return matched, findings


def call_problem(module_source: str, function: str, param: str) -> str | None:
    """Why `function` does not resolve `param` after `setup_output`, else None.

    Direct, aliased (`from x import resolve_pipeline as r`) and module-qualified calls count.
    """
    tree = ast.parse(module_source)
    bound: dict[str, set[str]] = {"setup_output": set(), "resolve_pipeline": set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in bound:
                    bound[alias.name].add(alias.asname or alias.name)

    def calls(call: ast.Call, key: str) -> bool:
        target = call.func
        return (isinstance(target, ast.Name) and target.id in bound[key]) or (
            isinstance(target, ast.Attribute) and target.attr == key
        )

    body = next((n for n in ast.walk(tree) if isinstance(n, _SCOPES) and n.name == function), None)
    if body is None:
        return f"{function} not found"
    found = [n for n in ast.walk(body) if isinstance(n, ast.Call)]
    setup = [c.lineno for c in found if calls(c, "setup_output")]
    resolve = [
        c.lineno
        for c in found
        if calls(c, "resolve_pipeline")
        and any(isinstance(a, ast.Name) and a.id == param for a in c.args)
    ]
    if not resolve:
        return f"{function} never calls resolve_pipeline on {param}"
    if not setup or min(setup) > min(resolve):
        return f"{function} resolves {param} before setup_output"
    return None


def private_typer_imports(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[0] == "typer" and any(p.startswith("_") for p in parts[1:]):
                found.append(f"line {node.lineno}: {name}")
                break
    return found


def project_variable_literals(source: str, rel: str) -> list[str]:
    if rel == "cli/io/_pipelines.py":
        return []
    tree = ast.parse(source)
    docs = _docstring_nodes(tree)
    return [
        f"{rel}:{n.lineno} reads the DECOY_PROJECT variable"
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == "DECOY_PROJECT" and id(n) not in docs
    ]


def test_every_pipeline_parameter_uses_the_shared_hooks() -> None:
    from decoy.__main__ import app

    matched, findings = parameter_findings(app)
    assert matched == EXPECTED
    assert findings == []


def test_every_command_body_resolves_its_pipeline_after_output_setup() -> None:
    from decoy.__main__ import app

    problems: list[str] = []
    for path, callback in typer_commands(app):
        names = [n for n, _ in pipeline_parameters(callback)]
        source = inspect.getsource(sys.modules[callback.__module__])
        problems.extend(
            f"{path}: {problem}"
            for pname in names
            if (problem := call_problem(source, callback.__name__, pname)) is not None
        )
    assert problems == []


def test_the_master_key_help_is_not_taken_for_a_pipeline_parameter() -> None:
    from decoy.cli.run import run

    helps = {
        name: str(info.help)
        for name, info in ((n, p.default) for n, p in inspect.signature(run).parameters.items())
        if isinstance(info, OptionInfo) and name in {"master_key", "mask_secret"}
    }
    assert set(helps) == {"master_key", "mask_secret"}
    assert not any(_HELP_RULE.match(text) for text in helps.values())


def _scratch(decl: object) -> typer.Typer:
    scratch = typer.Typer()

    def cmd(spec: str = decl) -> None:  # type: ignore[assignment]
        """Scratch command."""

    scratch.command(name="cmd")(cmd)
    return scratch


def test_a_parameter_without_the_callback_is_found_by_its_help_text() -> None:
    seeded = _scratch(typer.Option(..., help="Path to the pipeline YAML."))
    matched, findings = parameter_findings(seeded)
    assert matched == {"cmd:spec"}
    assert len(findings) == 2


def test_a_plain_path_argument_with_the_name_or_path_help_is_found() -> None:
    scratch = typer.Typer()

    def cmd(spec: Path = typer.Argument(..., help="Path or name of the pipeline config.")) -> None:
        """Scratch command."""

    scratch.command(name="cmd")(cmd)
    matched, findings = parameter_findings(scratch)
    assert matched == {"cmd:spec"}
    assert len(findings) == 2


def _command(fn: Callable) -> typer.Typer:
    scratch = typer.Typer()
    scratch.command(name="cmd")(fn)
    return scratch


def test_an_annotated_parameter_is_found_and_flagged_without_the_hooks() -> None:
    def cmd(
        target: Annotated[str, typer.Argument(help="Path or name of the pipeline config")],
    ) -> None:
        """Scratch command."""

    matched, findings = parameter_findings(_command(cmd))
    assert matched == {"cmd:target"}
    assert len(findings) == 2


def test_an_annotated_parameter_with_the_shared_hook_passes() -> None:
    def cmd(
        target: Annotated[str, pipeline_argument(help="Path or name of the pipeline config")],
    ) -> None:
        """Scratch command."""

    assert parameter_findings(_command(cmd)) == ({"cmd:target"}, [])


def test_another_spelling_of_the_config_option_is_found_and_flagged() -> None:
    def cmd(cfg: Path = typer.Option(..., "--pipeline-config", help="YAML file to run")) -> None:
        """Scratch command."""

    matched, findings = parameter_findings(_command(cmd))
    assert matched == {"cmd:cfg"}
    assert len(findings) == 2


def test_another_spelling_with_the_shared_hook_passes() -> None:
    def cmd(cfg: Path = pipeline_option(..., "--pipeline-config", help="YAML file to run")) -> None:
        """Scratch command."""

    assert parameter_findings(_command(cmd)) == ({"cmd:cfg"}, [])


def test_a_parameter_with_both_hooks_is_clean() -> None:
    hooks = typer.Option(
        ..., callback=parse_pipeline_token, autocompletion=pipeline_names, help="Pipeline config."
    )
    assert parameter_findings(_scratch(hooks)) == ({"cmd:spec"}, [])


_ALIASED = (
    "from decoy.cli.io import resolve_pipeline as r, parse_pipeline_token as p\n"
    "from decoy.ui.output import setup_output as s\n"
)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("def f(c):\n    s(1)\n    r(c, 1, 'f')\n", None),
        (
            "import decoy.cli.io as io\nimport decoy.ui.output as ui\ndef f(c):\n    ui.setup_output(1)\n    io.resolve_pipeline(c)\n",
            None,
        ),
        ("def f(c):\n    s(1)\n    return 1\n", "never calls"),
        ("def f(c):\n    r(c, 1, 'f')\n    s(1)\n", "before setup_output"),
        ("def f(c):\n    r(c, 1, 'f')\n", "before setup_output"),
        ("def f(c):\n    s(1)\n    r(other, 1, 'f')\n", "never calls"),
    ],
)
def test_the_call_check_sees_each_spelling(source: str, expected: str | None) -> None:
    problem = call_problem(_ALIASED + source, "f", "c")
    assert (problem is None) if expected is None else (expected in (problem or ""))


@pytest.mark.parametrize(
    "source",
    [
        "import typer._click\n",
        "import typer._click as c\n",
        "from typer._click import Context\n",
        "from typer._click.shell_completion import CompletionItem\n",
        "from typer import _click\n",
    ],
)
def test_each_spelling_of_a_private_typer_import_is_caught(source: str) -> None:
    assert private_typer_imports(source) != []


@pytest.mark.parametrize(
    "source",
    ["import typer\n", "from typer import Context\n", "from typer.models import CompletionItem\n"],
)
def test_public_typer_imports_pass(source: str) -> None:
    assert private_typer_imports(source) == []


def test_no_module_under_src_imports_a_private_typer_module() -> None:
    found = [
        f"{path.relative_to(SRC)} {hit}"
        for path in sorted(SRC.rglob("*.py"))
        for hit in private_typer_imports(path.read_text(encoding="utf-8"))
    ]
    assert found == []


def test_only_the_pipeline_module_reads_the_project_variable() -> None:
    found = [
        hit
        for path in sorted(SRC.rglob("*.py"))
        for hit in project_variable_literals(
            path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix()
        )
    ]
    assert found == []


@pytest.mark.parametrize(
    "source",
    ["import os\nx = os.environ['DECOY_PROJECT']\n", "import os\nx = os.getenv('DECOY_PROJECT')\n"],
)
def test_a_second_reader_of_the_project_variable_is_caught(source: str) -> None:
    assert project_variable_literals(source, "cli/other.py") != []
    assert project_variable_literals(source, "cli/io/_pipelines.py") == []


def test_prose_naming_the_project_variable_is_not_a_reader() -> None:
    source = '"""Reads DECOY_PROJECT."""\nhelp = "default: DECOY_PROJECT, else the walk"\n'
    assert project_variable_literals(source, "cli/other.py") == []
