"""G-ONE-GATE: every pre-run check goes through `decoy.cli.gate`.

Walks the syntax tree of every module under `src/decoy/` and resolves each call through the
module's import table to a dotted target (`import x as y`, `import x.y`, `from x import y as z`,
attribute calls on module aliases, module-level functions, and one-step `f = g` aliases), never
by bare name. Targets that only the gate may call, outside `decoy/cli/gate/`:

- `run_config_only_checks`, called on anything under `decoy_engine`;
- `compile_plan(..., no_profile=<not False>)`, called on anything under `decoy_engine`;
- the preflight layer checks `_check_source_files`, `_check_target_overwrite`, `_check_capacity`
  and `_check_native`, whatever module defines or imports them (so a copy of one is red too);
- `yaml.safe_load` and `PipelineConfig.model_validate` in `cli/run.py` and `cli/validate.py`.

An exemption is the exact `(module, outermost function, rule)` identity of a call site, recorded in
ALLOWLIST with a reason and in the shrink-only baseline
`tests/sentry/baselines/gate-single-entry-allow.json`. A stale exemption (no matching call) is red.

Named limits, invisible to a syntax walk: `getattr(mod, "name")`, a call through a name bound by
anything but a plain `import`, `from ... import` or `a = b` assignment, `from x import *`, and a
method call on an object built elsewhere.

The `cli.run` entries exist only because P1 does not touch `run.py` (the run lane belongs to
P2 of docs/plans/2026-11-06-validate-always.md). P2 deletes them with the code they cover.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decoy"
GATE_DIR = "cli/gate"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "gate-single-entry-allow.json"

RULE_CONFIG_ONLY = "run_config_only_checks"
RULE_COMPILE = "compile_plan_no_profile"
RULE_PREFLIGHT = "preflight_check"
RULE_YAML = "yaml_safe_load"
RULE_MODEL = "pipeline_model_validate"
_PREFLIGHT_CHECKS = {
    "_check_source_files",
    "_check_target_overwrite",
    "_check_capacity",
    "_check_native",
}
_YAML_MODEL_FILES = {"cli/run.py", "cli/validate.py"}


@dataclass(frozen=True)
class Allowed:
    module: str
    function: str
    rule: str
    reason: str


ALLOWLIST: tuple[Allowed, ...] = (
    Allowed(
        "decoy.cli.preflight",
        "preflight",
        RULE_PREFLIGHT,
        "The `validate preflight` command body is the third copy of steps 1-3 and calls the "
        "layer checks itself until CONFIG-EXPLICIT C2 folds it onto the gate.",
    ),
    Allowed(
        "decoy.cli.preflight",
        "preflight",
        RULE_CONFIG_ONLY,
        "The same third copy of steps 1-3 also runs the config-only checks itself until "
        "CONFIG-EXPLICIT C2 folds it onto the gate.",
    ),
    Allowed(
        "decoy.cli.compile_explain",
        "compile",
        RULE_COMPILE,
        "`validate compile --no-profile` is the single-layer command the gate's compile layer "
        "reuses helpers from; it keeps its own compile call and its unique-column error.",
    ),
    Allowed(
        "decoy.cli.run",
        "_load_raw_config",
        RULE_YAML,
        "P1 does not touch run.py; P2 replaces this parse with parse_pipeline_yaml and "
        "deletes this entry.",
    ),
    Allowed(
        "decoy.cli.run",
        "run",
        RULE_YAML,
        "P1 does not touch run.py; P2 deletes the re-parse in `run` and this entry.",
    ),
    Allowed(
        "decoy.cli.run",
        "run",
        RULE_MODEL,
        "P1 does not touch run.py; P2 reads GateResult.config instead of validating again "
        "and deletes this entry.",
    ),
)


def _module_name(rel: str) -> str:
    parts = rel[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(["decoy", *parts])


def _import_table(tree: ast.Module, module: str, rel: str) -> dict[str, str]:
    """Local name -> dotted target, from imports, module-level defs and one-step aliases."""
    table: dict[str, str] = {}
    package = module if rel.endswith("__init__.py") else module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    table[a.asname] = a.name
                else:
                    table[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join([*up, base]) if base else ".".join(up)
            for a in node.names:
                if a.name != "*":
                    table[a.asname or a.name] = f"{base}.{a.name}"
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            table.setdefault(node.name, f"{module}.{node.name}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, (ast.Name, ast.Attribute))
        ):
            target = _resolve(node.value, table)
            if target is not None:
                table.setdefault(node.targets[0].id, target)
    return table


def _resolve(node: ast.expr, table: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return table.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve(node.value, table)
        return f"{base}.{node.attr}" if base is not None else None
    return None


def _rules(target: str, call: ast.Call, rel: str) -> list[str]:
    last = target.rsplit(".", 1)[-1]
    engine = target.startswith("decoy_engine")
    out: list[str] = []
    if engine and last == "run_config_only_checks":
        out.append(RULE_CONFIG_ONLY)
    if engine and last == "compile_plan":
        for kw in call.keywords:
            if kw.arg == "no_profile" and not (
                isinstance(kw.value, ast.Constant) and kw.value.value is False
            ):
                out.append(RULE_COMPILE)
    if last in _PREFLIGHT_CHECKS:
        out.append(RULE_PREFLIGHT)
    if rel in _YAML_MODEL_FILES:
        if target == "yaml.safe_load":
            out.append(RULE_YAML)
        if engine and target.endswith("PipelineConfig.model_validate"):
            out.append(RULE_MODEL)
    return out


def call_sites(source: str, rel: str) -> list[tuple[int, str, str, str]]:
    """Return (line, module, outermost function, rule) for each flagged call in `source`."""
    tree = ast.parse(source)
    module = _module_name(rel)
    table = _import_table(tree, module, rel)
    found: list[tuple[int, str, str, str]] = []

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            fn = function
            if not function and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = child.name
            if isinstance(child, ast.Call):
                target = _resolve(child.func, table)
                if target is not None:
                    found.extend(
                        (child.lineno, module, function or "<module>", rule)
                        for rule in _rules(target, child, rel)
                    )
            visit(child, fn)

    visit(tree, "")
    return found


def scan(root: Path) -> dict[str, list[tuple[int, str, str, str]]]:
    out: dict[str, list[tuple[int, str, str, str]]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(GATE_DIR + "/"):
            continue
        sites = call_sites(path.read_text(encoding="utf-8"), rel)
        if sites:
            out[rel] = sites
    return out


def findings(found: dict[str, list[tuple[int, str, str, str]]]) -> list[str]:
    allowed = {(e.module, e.function, e.rule) for e in ALLOWLIST}
    seen: set[tuple[str, str, str]] = set()
    out: list[str] = []
    for rel, sites in sorted(found.items()):
        for line, module, function, rule in sites:
            seen.add((module, function, rule))
            if (module, function, rule) not in allowed:
                out.append(f"{rel}:{line}: {rule} called in {function} outside decoy.cli.gate")
    out += [
        f"{m}::{f}::{r}: allowlisted but has no matching call (remove the entry)"
        for m, f, r in sorted(allowed - seen)
    ]
    return out


def test_no_pre_run_check_outside_the_gate() -> None:
    assert findings(scan(SRC)) == []


def test_allowlist_has_reasons_and_unique_identities() -> None:
    assert len({(e.module, e.function, e.rule) for e in ALLOWLIST}) == len(ALLOWLIST) == 6
    assert all(len(e.reason.strip()) >= 15 for e in ALLOWLIST)


def test_baseline_json_records_the_same_entries_and_reasons() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    assert {k: v["reason"] for k, v in entries.items()} == {
        f"{e.module}::{e.function}::{e.rule}": e.reason for e in ALLOWLIST
    }


def test_choke_point_package_exists_and_is_excluded() -> None:
    assert (SRC / "cli" / "gate" / "_layers.py").is_file()
    assert not any(rel.startswith(GATE_DIR) for rel in scan(SRC))


# -- seeded bypasses: each spelling must be seen ------------------------------------------------

_SEEDS = [
    (
        "cli/run.py",
        "from decoy.cli.preflight import _check_source_files\n"
        "def run(raw):\n    _check_source_files(raw, None, None)\n",
        [("decoy.cli.run", "run", RULE_PREFLIGHT)],
    ),
    (
        "scratch.py",
        "import decoy_engine as de\ndef f(x):\n    de.run_config_only_checks(x)\n",
        [("decoy.scratch", "f", RULE_CONFIG_ONLY)],
    ),
    (
        "scratch.py",
        "import decoy_engine\ndef f(x):\n    decoy_engine.run_config_only_checks(x)\n",
        [("decoy.scratch", "f", RULE_CONFIG_ONLY)],
    ),
    (
        "scratch.py",
        "from decoy_engine import run_config_only_checks as chk\ndef f(x):\n    chk(x)\n",
        [("decoy.scratch", "f", RULE_CONFIG_ONLY)],
    ),
    (
        "cli/run.py",
        "from yaml import safe_load as s\ndef _load_raw_config(t):\n    return s(t)\n",
        [("decoy.cli.run", "_load_raw_config", RULE_YAML)],
    ),
    (
        "cli/run.py",
        "import yaml\ndef run(t):\n    return yaml.safe_load(t)\n",
        [("decoy.cli.run", "run", RULE_YAML)],
    ),
    (
        "cli/validate.py",
        "import yaml as y\ndef config(t):\n    return y.safe_load(t)\n",
        [("decoy.cli.validate", "config", RULE_YAML)],
    ),
    (
        "cli/validate.py",
        "def _check_target_overwrite(raw, acc):\n    pass\ndef config(raw):\n"
        "    _check_target_overwrite(raw, None)\n",
        [("decoy.cli.validate", "config", RULE_PREFLIGHT)],
    ),
    (
        "scratch.py",
        "import decoy.cli.preflight as pf\ndef f(raw):\n    pf._check_capacity(raw, None, None)\n",
        [("decoy.scratch", "f", RULE_PREFLIGHT)],
    ),
    (
        "scratch.py",
        "from decoy.cli import preflight\ndef f(raw):\n    preflight._check_native(raw, None)\n",
        [("decoy.scratch", "f", RULE_PREFLIGHT)],
    ),
    (
        "scratch.py",
        "from decoy.cli.preflight import _check_native\ndef f(raw):\n"
        "    g = _check_native\n    g(raw, None)\n",
        [("decoy.scratch", "f", RULE_PREFLIGHT)],
    ),
    (
        "cli/run.py",
        "from decoy_engine import PipelineConfig\ndef run(raw):\n"
        "    return PipelineConfig.model_validate(raw)\n",
        [("decoy.cli.run", "run", RULE_MODEL)],
    ),
    (
        "cli/validate.py",
        "import decoy_engine\ndef f(raw):\n    decoy_engine.PipelineConfig.model_validate(raw)\n",
        [("decoy.cli.validate", "f", RULE_MODEL)],
    ),
    (
        "scratch.py",
        "from decoy_engine.plan import compile_plan\ndef f(raw, p):\n"
        "    compile_plan(raw, p, no_profile=True)\n",
        [("decoy.scratch", "f", RULE_COMPILE)],
    ),
    (
        "scratch.py",
        "from decoy_engine.plan import compile_plan as cp\ndef f(raw, p):\n"
        "    def inner():\n        cp(raw, p, no_profile=True)\n    inner()\n",
        [("decoy.scratch", "f", RULE_COMPILE)],
    ),
    (
        "cli/gate/inner.py",
        "import decoy_engine\ndef f(x):\n    decoy_engine.run_config_only_checks(x)\n",
        [],  # excluded by scan(); call_sites alone still sees it, see below
    ),
]


@pytest.mark.parametrize(("rel", "source", "expected"), _SEEDS)
def test_walk_sees_each_spelling(
    rel: str, source: str, expected: list[tuple[str, str, str]]
) -> None:
    got = [(m, f, r) for _, m, f, r in call_sites(source, rel)]
    if rel.startswith(GATE_DIR):
        assert got == [("decoy.cli.gate.inner", "f", RULE_CONFIG_ONLY)]
    else:
        assert got == expected


@pytest.mark.parametrize(
    "source",
    [
        "from decoy_engine.plan import compile_plan\ndef f(r, p):\n    compile_plan(r, p)\n",
        "from decoy_engine.plan import compile_plan\ndef f(r, p):\n"
        "    compile_plan(r, p, no_profile=False)\n",
        "import yaml\ndef f(t):\n    return yaml.safe_load(t)\n",  # outside run.py / validate.py
        "def _check_native(a):\n    pass\n",  # a definition is not a call
    ],
)
def test_walk_ignores_lookalikes(source: str) -> None:
    assert call_sites(source, "scratch.py") == []


def test_seeded_bypass_outside_the_allowlist_is_red(tmp_path: Path) -> None:
    """Mutation: add `_check_source_files(...)` to run.py's `main` (not allowlisted for it)."""
    (tmp_path / "cli").mkdir()
    (tmp_path / "cli" / "run.py").write_text(
        "from decoy.cli.preflight import _check_source_files\n"
        "def main(raw):\n    _check_source_files(raw, None, None)\n",
        encoding="utf-8",
    )
    got = findings(scan(tmp_path))
    assert got[0] == "cli/run.py:3: preflight_check called in main outside decoy.cli.gate"


def test_seeded_extra_rule_in_an_exempt_function_is_red() -> None:
    """The preflight exemption covers the preflight rule only, not a second parse in it."""
    seeded = {
        "cli/preflight.py": [(10, "decoy.cli.preflight", "preflight", RULE_PREFLIGHT)],
        "cli/validate.py": [(5, "decoy.cli.validate", "config", RULE_YAML)],
    }
    out = findings(seeded)
    assert "cli/validate.py:5: yaml_safe_load called in config outside decoy.cli.gate" in out
    assert not any(line.startswith("cli/preflight.py") for line in out)


def test_stale_exemption_is_red() -> None:
    out = findings({})
    assert len(out) == len(ALLOWLIST)
    assert all("allowlisted but has no matching call" in line for line in out)
