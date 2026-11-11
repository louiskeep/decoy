"""Every CLI route that validates a pipeline config goes through the engine's value-free parse.

Pydantic's ``ValidationError`` renders the submitted values (``input_value=``, the union tag
echo, validator text built from the input). The engine's ``parse_pipeline_config`` turns it into
``PipelineConfigError.problems``: names and locations only. A CLI site that validates an engine
model itself, or reads ``ValidationError.errors()`` / ``str()``, puts those values into stdout,
stderr or the ``--json`` envelope.

Two layers:

* An AST walk of ``src/decoy`` flags the ways a raw ``ValidationError`` can reach output:
  ``.model_validate*`` / ``.validate_python`` on a model that comes from ``decoy_engine``, an
  import of Pydantic's ``ValidationError``, and a ``.errors()`` call. The one allowlisted site
  validates a CLI-owned model.
* A route cell per config-taking command feeds a config whose values are markers and asserts
  that no marker reaches any output while the structural names do. A Click-tree walk makes the
  cell table complete: a command added later with a config parameter must get a cell or a
  reasoned exemption.

Named limits: the AST layer sees the spellings it resolves (``from`` imports, module aliases);
the route cells are what catches a spelling it does not.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "decoy"

# ---------------------------------------------------------------------------------------------
# Layer 1: the AST walk.
# ---------------------------------------------------------------------------------------------

_VALIDATE_METHODS = frozenset(
    {"model_validate", "model_validate_json", "model_validate_strings", "validate_python"}
)
_PYDANTIC_MODULES = frozenset({"pydantic", "pydantic_core"})

# (path relative to src/decoy, reason). Shrink-only baseline: tests/sentry/baselines/config-route-allow.json.
# Each entry must still hold a violation (checked below).
ALLOWLIST: tuple[tuple[str, str], ...] = (
    (
        "cli/io/_scan_set.py",
        "validates the engine's scan-set read model, catches the error without reading it and raises a fixed message outside the handler; a scan file is not a pipeline config",
    ),
    (
        "ci/manifest.py",
        "validates the CLI-owned CiManifest and reads only the error type, never a value or a message (FU-4 moves it onto validation_problems if its codes ever need a location)",
    ),
)


def _is_engine(module: str | None) -> bool:
    return bool(module) and (module == "decoy_engine" or module.startswith("decoy_engine."))


def violations(source: str) -> list[tuple[int, str]]:
    """The raw-ValidationError routes in one module's source, as ``(line, what)``."""
    tree = ast.parse(source)
    engine_names: set[str] = set()  # bound by `from decoy_engine... import X [as Y]`
    engine_modules: set[str] = set()  # bound by `import decoy_engine... [as Z]`
    pydantic_modules: set[str] = set()
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                bound = alias.asname or alias.name
                if _is_engine(node.module):
                    engine_names.add(bound)
                if node.module in _PYDANTIC_MODULES and alias.name == "ValidationError":
                    found.append((node.lineno, f"imports {node.module}.ValidationError"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_engine(alias.name):
                    engine_modules.add(alias.asname or alias.name.split(".")[0])
                if alias.name in _PYDANTIC_MODULES:
                    pydantic_modules.add(alias.asname or alias.name)

    def root(expr: ast.expr) -> str | None:
        while isinstance(expr, (ast.Attribute, ast.Call, ast.Subscript)):
            expr = expr.value if not isinstance(expr, ast.Call) else expr.func
        return expr.id if isinstance(expr, ast.Name) else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr == "ValidationError" and root(node) in pydantic_modules:
                found.append((node.lineno, "uses pydantic ValidationError"))
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr == "errors":
            found.append((node.lineno, "calls .errors()"))
        elif attr in _VALIDATE_METHODS:
            base = root(node.func.value)
            if base in engine_names or base in engine_modules:
                found.append((node.lineno, f"{attr} on an engine model"))
    return sorted(found)


def _walk_src() -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(SRC.rglob("*.py")):
        found = violations(path.read_text(encoding="utf-8"))
        if found:
            out[path.relative_to(SRC).as_posix()] = found
    return out


def test_no_raw_validation_error_route_in_src() -> None:
    offenders = {p: v for p, v in _walk_src().items() if p not in {a for a, _ in ALLOWLIST}}
    assert not offenders, (
        "These sites validate an engine model or read a Pydantic ValidationError themselves; "
        "call decoy_engine.parse_pipeline_config and render PipelineConfigError.problems:\n"
        + "\n".join(f"  {p}:{ln} {what}" for p, found in offenders.items() for ln, what in found)
    )


def test_allowlist_entries_still_hold_a_violation() -> None:
    walked = _walk_src()
    stale = [p for p, _ in ALLOWLIST if p not in walked]
    assert not stale, f"allowlist entries with no violation left, remove them: {stale}"


@pytest.mark.parametrize(
    ("label", "source"),
    [
        (
            "from-import",
            "from decoy_engine import PipelineConfig\nPipelineConfig.model_validate(x)",
        ),
        (
            "engine submodule import",
            "from decoy_engine.config import TableConfig as T\nT.model_validate(x)",
        ),
        ("module alias", "import decoy_engine as de\nde.PipelineConfig.model_validate(x)"),
        (
            "adapter",
            "from decoy_engine import PipelineConfig\nTypeAdapter(PipelineConfig).validate_python(x)\n"
            "PipelineConfig.model_validate_json(x)",
        ),
        ("pydantic import", "from pydantic import ValidationError as V"),
        ("pydantic_core import", "from pydantic_core import ValidationError"),
        ("pydantic attribute", "import pydantic\nexcept_ = pydantic.ValidationError"),
        ("errors loop", "for e in exc.errors():\n    pass"),
    ],
)
def test_walk_sees_each_planted_bypass(label: str, source: str) -> None:
    assert violations(textwrap.dedent(source)), f"the walk missed the planted {label} bypass"


@pytest.mark.parametrize(
    "source",
    [
        "from decoy_engine import parse_pipeline_config\nparse_pipeline_config(x)",
        "from decoy.ci.manifest import CiManifest\nCiManifest.model_validate(x)",
        "from decoy_engine import PipelineConfigError\ntry:\n    pass\nexcept PipelineConfigError:\n    pass",
    ],
)
def test_walk_leaves_the_choke_point_alone(source: str) -> None:
    assert violations(source) == []


# ---------------------------------------------------------------------------------------------
# Layer 2: the route cells.
# ---------------------------------------------------------------------------------------------

_MARKER = "VFE_MARKER"
_FIRST = "sources.customers"  # the first problem's location, a name: it must stay visible
_EXTRA = "zz_extra_key"  # the extra key's location: shown by every renderer of the full list
_BAD_CONFIG = f"""\
version: 2
global_settings:
  seed: 1
{_EXTRA}: {_MARKER}_EXTRA
sources:
  customers:
    type: {_MARKER}_TAG
tables:
  - name: customers
    columns:
      - name: id
        strategy: {_MARKER}_STRATEGY
targets:
  customers:
    type: file
    format: csv
    path: out.csv
"""
_WIDE_ENV = {"COLUMNS": "10000"}  # keep Rich from cutting a marker mid-string

runner = CliRunner()

# label -> argv builder over (config, source file, masked/output file).
CELLS: dict[str, Callable[[str, str, str], list[str]]] = {
    # `validate CONFIG` dispatches to the hidden default command `_gate`.
    "validate _gate": lambda c, s, o: ["validate", c],
    "validate _gate --json": lambda c, s, o: ["validate", c, "--json"],
    "validate config": lambda c, s, o: ["validate", "config", c],
    "validate config --json": lambda c, s, o: ["validate", "config", c, "--json"],
    "validate compile": lambda c, s, o: ["validate", "compile", c],
    "validate compile --json": lambda c, s, o: ["validate", "compile", c, "--json"],
    "validate preflight": lambda c, s, o: ["validate", "preflight", c],
    "validate preflight --json": lambda c, s, o: ["validate", "preflight", c, "--json"],
    "subset": lambda c, s, o: ["subset", c, "--dry-run"],
    "subset --json": lambda c, s, o: ["subset", c, "--dry-run", "--json"],
    "run": lambda c, s, o: ["run", c],
    "run --json": lambda c, s, o: ["run", c, "--json"],
    "tokenize": lambda c, s, o: ["tokenize", c, "--vault", o + ".vault"],
    "detokenize": lambda c, s, o: ["detokenize", c, o, "--vault", o + ".vault"],
    "unmask": lambda c, s, o: ["unmask", c, o],
    "report fidelity --config": lambda c, s, o: [
        "report",
        "fidelity",
        s,
        o,
        "--config",
        c,
        "--json",
    ],
    "report integrity --config": lambda c, s, o: [
        "report",
        "integrity",
        o,
        "--source",
        s,
        "--config",
        c,
        "--json",
    ],
    "report vault --config": lambda c, s, o: ["report", "vault", o, "--config", c, "--json"],
}

# Cells whose command never validates the config schema (it stops on an earlier refusal or runs
# another layer), so only "no marker in the output" holds. The reason is the value.
MARKER_ONLY: dict[str, str] = {
    "validate compile": "runs the compile layer only; schema errors come from `validate config`",
    "validate compile --json": "same",
    "unmask": "reads the config for column strategies and stops first on the missing mask secret",
    "report vault --config": "stops first on the missing mask secret",
}
# Commands that print only the first problem rather than the full list.
FIRST_ONLY = frozenset({"subset", "subset --json", "run", "run --json", "validate config"})
# Exit codes that differ from EXIT_USAGE and did before this change (A3 changes text, not codes).
EXIT_OVERRIDE = {"report integrity --config": EXIT_RUNTIME}

# Commands that take a config parameter but cannot be fed a user config on a marker route.
PACKAGED_CONFIG_ONLY: dict[str, str] = {
    "demo": "validates the packaged demo pipeline, which takes no user config",
}

_CONFIG_PARAMS = frozenset({"config", "pipeline_config"})


def _config_taking_commands() -> set[str]:
    """Space-joined paths of every leaf command with a config argument or option."""
    found: set[str] = set()

    def visit(cmd: object, prefix: tuple[str, ...]) -> None:
        for name, sub in getattr(cmd, "commands", {}).items():
            path = (*prefix, name)
            subs = getattr(sub, "commands", None)
            if subs:
                visit(sub, path)
            if any(p.name in _CONFIG_PARAMS for p in getattr(sub, "params", ())):
                found.add(" ".join(path))
        return None

    visit(typer.main.get_command(app), ())
    return found


def _covered(label: str) -> str:
    """The command path a cell label exercises (the label minus its flags)."""
    return " ".join(w for w in label.split() if not w.startswith("--"))


def test_every_config_taking_command_has_a_cell_or_an_exemption() -> None:
    covered = {_covered(label) for label in CELLS} | set(PACKAGED_CONFIG_ONLY)
    missing = sorted(_config_taking_commands() - covered)
    assert not missing, (
        f"commands with a config parameter and no route cell: {missing}. Add a cell to CELLS, "
        "or a PACKAGED_CONFIG_ONLY entry with the reason."
    )


def test_marker_only_cells_exist() -> None:
    assert set(MARKER_ONLY) <= set(CELLS)


def test_cells_name_real_commands() -> None:
    real = _config_taking_commands()
    stale = sorted({_covered(label) for label in CELLS} - real)
    assert not stale, f"cells for commands that no longer take a config: {stale}"


@pytest.mark.parametrize("label", list(CELLS))
def test_config_error_output_is_value_free(label: str, tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(_BAD_CONFIG, encoding="utf-8")
    src = tmp_path / "src.csv"
    src.write_text("id\n1\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    out.write_text("id\n1\n", encoding="utf-8")

    argv = CELLS[label](str(cfg), str(src), str(out))
    result = runner.invoke(app, argv, env=_WIDE_ENV, catch_exceptions=True)
    combined = (result.stdout or "") + (result.stderr or "")
    assert _MARKER not in combined, f"`decoy {' '.join(argv)}` printed a config value:\n{combined}"
    if label in MARKER_ONLY:
        return
    assert _FIRST in combined, (
        f"`decoy {' '.join(argv)}` did not name the offending key, so it may not have reached "
        f"config validation:\n{combined}"
    )
    if label not in FIRST_ONLY:
        assert _EXTRA in combined, (
            f"`decoy {' '.join(argv)}` dropped a structural name:\n{combined}"
        )
    expected = EXIT_OVERRIDE.get(label, EXIT_USAGE)
    assert result.exit_code == expected, (
        f"`decoy {' '.join(argv)}` exited {result.exit_code}, expected {expected}:\n{combined}"
    )
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_api_mask_config_error_is_value_free_and_chainless(tmp_path: Path) -> None:
    """``decoy.api.mask`` (AT-A5 and AT-A8): no marker in the message or the traceback chain."""
    import traceback

    from decoy.api import ConfigValidationError, mask

    cfg = tmp_path / "bad.yaml"
    cfg.write_text(_BAD_CONFIG, encoding="utf-8")
    with pytest.raises(ConfigValidationError) as caught:
        mask(config=cfg)
    exc = caught.value
    rendered = "".join(traceback.format_exception(exc))
    assert _MARKER not in str(exc)
    assert _MARKER not in rendered
    assert _FIRST in str(exc)
    assert exc.__cause__ is None
    assert exc.__context__ is None
