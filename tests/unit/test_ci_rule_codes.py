"""The emitted `rule_id` is drawn from a closed allowlist, never from upstream text.

Two halves: an unknown code carrying a canary reaches none of the three report formats,
and every code the pinned engine, the CLI gate, and the evidence verifier can produce today
is in the allowlist -- so a new upstream code fails here and forces an explicit decision
instead of silently collapsing to `unknown_code`.

The engine's code set comes from its published reason registry
(`decoy_engine.reasons.manifest()`), the source producers reference since 0.16.0. A source
scan alone went blind once producers switched from string literals to registry symbols, so
the literal scan only supplements the registry (codes raised outside it, such as native
companion statuses).
"""

from __future__ import annotations

import ast
import json
import re
import typing
from pathlib import Path

import pytest
from tests.ci_support import MANIFEST_NAME, ci_manifest, make_repo, write, write_clean_pipeline
from typer.testing import CliRunner

import decoy.cli.evidence as cli_evidence
import decoy.cli.gate as cli_gate
import decoy.cli.gate._layers as cli_gate_layers
import decoy.cli.preflight as cli_preflight
from decoy.ci.rule_codes import (
    EVIDENCE_KINDS,
    UNKNOWN_CODE,
    rule_code,
    validation_codes,
)

CANARY = "rulecanary7d41e0"

_CODE_TOKEN = re.compile(r"^[a-z][a-z0-9_.-]*$")
_CODE_NAME = re.compile(r"(^|_)(CODES?|REASONS?)$")

# ---- source scanners --------------------------------------------------------------------


def _literals(node: ast.AST) -> list[str]:
    """String constants in `node`, not descending into f-strings (their parts are prose)."""
    if isinstance(node, ast.JoinedStr):
        return []
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    return [s for child in ast.iter_child_nodes(node) for s in _literals(child)]


def _call_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _registry_codes() -> set[str]:
    """Every wire code in the engine's published reason registry, tombstones included."""
    from decoy_engine import reasons

    return {entry["code"] for entry in reasons.manifest()["entries"]}  # type: ignore[index, union-attr]


# Engine errors whose first positional argument is not a code, so the scan skips it.
# `ScanSourceError(table, cause_class)` names the table (`"relationships"` for the declared
# relationships scan, engine #422); its wire code is the class's own.
_FIRST_ARG_NOT_A_CODE = frozenset({"ScanSourceError"})


def _engine_literal_codes() -> set[str]:
    """Literal codes the engine raises or reports outside the registry."""
    import decoy_engine

    root = Path(decoy_engine.__file__).parent
    codes: set[str] = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            values: list[ast.AST] = []
            if isinstance(node, ast.Call):
                values += [kw.value for kw in node.keywords if kw.arg in ("code", "reason")]
                name = _call_name(node)
                is_error = name.endswith("Error") or name.endswith("Exception")
                if node.args and is_error and name not in _FIRST_ARG_NOT_A_CODE:
                    values.append(node.args[0])
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and _CODE_NAME.search(t.id) for t in targets):
                    values.append(node.value)
            for value in values:
                codes.update(s for s in _literals(value) if _CODE_TOKEN.match(s))
    return codes


def _engine_codes() -> set[str]:
    return _registry_codes() | _engine_literal_codes()


# Computed `code=` sites in the engine, each with the decision taken for it: the codes it can
# produce (each must be allowlisted). A computed code is invisible to the registry and the
# literal scan, so a new one would silently collapse to UNKNOWN_CODE; it fails here until it
# is listed. Engine 0.18.0 has none (0.15.1's two moved into the registry).
_APPROVED_DYNAMIC_CODE_SITES: dict[str, tuple[str, ...]] = {}


def _is_str(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_computed_string(value: ast.AST) -> bool:
    """An f-string, `"...".format(...)`, or `%` / `+` string building, at any depth."""
    for node in ast.walk(value):
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "format" and _is_str(node.func.value):
                return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
            if _is_str(node.left) or _is_str(node.right):
                return True
    return False


def _dynamic_code_sites(root: Path) -> dict[str, list[int]]:
    """Files under `root` with a computed `code=` argument, and the lines."""
    sites: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "code" and _is_computed_string(kw.value):
                        sites.setdefault(path.relative_to(root).as_posix(), []).append(node.lineno)
    return sites


def _unapproved_dynamic_sites(root: Path) -> list[str]:
    return sorted(set(_dynamic_code_sites(root)) - set(_APPROVED_DYNAMIC_CODE_SITES))


def _unlisted(codes: set[str]) -> list[str]:
    """Codes `decoy ci` would emit as UNKNOWN_CODE."""
    return sorted(c for c in codes if rule_code(c, validation_codes()) == UNKNOWN_CODE)


def _module_tree(module: object) -> ast.AST:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))  # type: ignore[attr-defined]


def _cli_gate_codes() -> tuple[set[str], set[str]]:
    """Codes `run_gate` attaches itself, and the f-string preflight check names."""
    codes: set[str] = set()
    templates: set[str] = set()
    for node in ast.walk(_module_tree(cli_gate_layers)):
        if isinstance(node, ast.Call) and _call_name(node) == "GateFinding":
            if len(node.args) > 2 and isinstance(node.args[2], ast.Constant):
                codes.add(node.args[2].value)
    gate_checks = {
        "_check_source_files",
        "_check_target_overwrite",
        "_check_capacity",
        "_check_native",
    }
    for fn in ast.walk(_module_tree(cli_preflight)):
        if not (isinstance(fn, ast.FunctionDef) and fn.name in gate_checks):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg not in ("name", "code"):
                    continue
                if isinstance(kw.value, ast.JoinedStr):
                    templates.add(
                        "".join(
                            p.value if isinstance(p, ast.Constant) else "{}"
                            for p in kw.value.values
                        )
                    )
                else:
                    codes.update(s for s in _literals(kw.value) if _CODE_TOKEN.match(s))
    from decoy.cli import extras

    for node in ast.walk(_module_tree(extras)):
        if isinstance(node, ast.FunctionDef) and node.name == "plan_compile_error_fields":
            for ret in ast.walk(node):
                if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Tuple):
                    codes.update(_literals(ret.value.elts[0]))
    return codes, templates


def _evidence_kinds() -> set[str]:
    kinds: set[str] = set()
    for node in ast.walk(_module_tree(cli_evidence)):
        if isinstance(node, ast.Call) and _call_name(node) == "EvidenceIssue" and node.args:
            kinds.update(_literals(node.args[0]))
    return kinds


def _pydantic_error_types() -> set[str]:
    from pydantic_core import core_schema

    return set(typing.get_args(core_schema.ErrorType))


# ---- completeness: a new upstream code fails the build ---------------------------------


def test_the_engine_code_set_is_not_vacuous() -> None:
    from decoy_engine import reasons

    registry = {spec.code for spec in reasons.specs()}
    assert registry, "the engine registry is empty; the source of truth is broken"
    codes = _engine_codes()
    assert registry <= codes and len(codes) >= len(registry)
    assert all(reasons.is_registered(c) for c in _registry_codes())
    # A seeded code the allowlist does not know is reported, not absorbed.
    canary = "canary_code_absent_from_allowlist"
    assert canary not in validation_codes() and not reasons.is_registered(canary)
    assert rule_code(canary, validation_codes()) == UNKNOWN_CODE
    assert _unlisted(codes | {canary}) == sorted({canary, *_unlisted(codes)})


def test_every_engine_code_is_allowlisted() -> None:
    assert _unlisted(_engine_codes()) == []


def test_every_computed_engine_code_site_is_approved() -> None:
    import decoy_engine

    root = Path(decoy_engine.__file__).parent
    assert _unapproved_dynamic_sites(root) == [], _dynamic_code_sites(root)
    # A listed site that no longer exists is a stale decision, not a pass.
    assert set(_APPROVED_DYNAMIC_CODE_SITES) <= set(_dynamic_code_sites(root))
    expansions = {c for codes in _APPROVED_DYNAMIC_CODE_SITES.values() for c in codes}
    assert _unlisted(expansions) == []


_SEEDED_SITES = {
    "fstring": 'raise ExecutionError(code=f"leak_{value}_x", message="m")',
    "format": 'raise ExecutionError(code="leak_{}_x".format(value), message="m")',
    "percent": 'raise ExecutionError(code="leak_%s_x" % value, message="m")',
    "concat": 'raise ExecutionError(code="leak_" + value, message="m")',
    "nested": 'raise ExecutionError(code=str(f"leak_{value}"), message="m")',
}


@pytest.mark.parametrize("shape", sorted(_SEEDED_SITES))
def test_a_seeded_computed_code_site_is_reported(tmp_path: Path, shape: str) -> None:
    pkg = tmp_path / "fake_engine" / "execution"
    pkg.mkdir(parents=True)
    (pkg / "_ok.py").write_text(
        "def f(value):\n    raise ExecutionError(code=reasons.runtime.X, message=f'{value}')\n"
        "def g():\n    raise ExecutionError(code='literal_code', message='m')\n",
        encoding="utf-8",
    )
    (pkg / "_seeded.py").write_text(
        f"def f(value):\n    {_SEEDED_SITES[shape]}\n", encoding="utf-8"
    )
    assert _unapproved_dynamic_sites(tmp_path / "fake_engine") == ["execution/_seeded.py"]


def test_the_engine_half_is_derived_from_the_registry_not_written_by_hand() -> None:
    """The allowlist holds the whole registry by construction (non-vacuity: at least the
    registry's size), and the explicit literal-only set is exactly what the registry misses,
    so it can neither go stale nor smuggle in a code the engine does not raise."""
    from decoy.ci import rule_codes

    registry = _registry_codes()
    derived = rule_codes._engine_registry_codes()
    assert len(derived) >= len(registry) > 0
    assert derived == registry
    assert registry <= validation_codes()
    assert rule_codes._ENGINE_LITERAL_CODES == _engine_literal_codes() - registry


def test_every_registry_code_is_a_sarif_safe_token() -> None:
    """The allowlist's guarantee is that a rule_id carries no value. Registry codes are
    closed-vocabulary by construction; this checks it instead of assuming it."""
    unsafe = sorted(c for c in _registry_codes() if not _CODE_TOKEN.fullmatch(c))
    assert unsafe == []


@pytest.mark.parametrize(
    "bad",
    ["odd code!", f"leak {CANARY}", "Upper_case", "tab\there", "", "x/y", "ünicode"],
    ids=["space-bang", "canary", "upper", "tab", "empty", "slash", "non-ascii"],
)
def test_the_registry_derivation_drops_a_code_outside_the_safe_set(bad: str) -> None:
    from decoy.ci.rule_codes import _codes_from_registry

    entries = [{"code": "fine_code"}, {"code": bad}, {"code": None}, {}]
    assert _codes_from_registry(entries) == frozenset({"fine_code"})


def test_every_pydantic_error_type_is_allowlisted() -> None:
    assert sorted(_pydantic_error_types() - validation_codes()) == []


def test_every_cli_gate_code_and_preflight_template_is_allowlisted() -> None:
    codes, templates = _cli_gate_codes()
    assert {"yaml.parse_error", "missing_extra", "compile.needs_profile"} <= codes
    assert sorted(codes - validation_codes()) == []
    assert templates, "the preflight scan found no templated check names"
    for template in templates:
        emitted = rule_code(template.format(CANARY), validation_codes())
        assert emitted != UNKNOWN_CODE, template
        assert CANARY not in emitted, template


def test_every_evidence_issue_kind_is_allowlisted() -> None:
    kinds = _evidence_kinds()
    assert "output_fingerprint_changed" in kinds
    assert sorted(kinds - EVIDENCE_KINDS) == []


# ---- the mapping itself ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("unknown_provider", "unknown_provider"),
        ("yaml.parse_error", "yaml.parse_error"),
        ("missing", "missing"),
        ("target.Customers.would_overwrite", "target.would_overwrite"),
        ("source.a.b.exists", "source.exists"),
        ("target.Customers.parent_unwritable", "target.parent_unwritable"),
        ("target.Customers.parent_missing", UNKNOWN_CODE),
        ("Unknown_Provider", UNKNOWN_CODE),
        ("odd code!", UNKNOWN_CODE),
        ("", UNKNOWN_CODE),
        (None, UNKNOWN_CODE),
        (f"leak_{CANARY}", UNKNOWN_CODE),
        ("x" * 300, UNKNOWN_CODE),
    ],
)
def test_validation_codes_map_through_the_allowlist(code: object, expected: str) -> None:
    assert rule_code(code, validation_codes()) == expected


def test_an_engine_code_is_not_a_valid_evidence_kind() -> None:
    assert rule_code("unknown_provider", EVIDENCE_KINDS) == UNKNOWN_CODE
    assert rule_code("manifest_hash_mismatch", EVIDENCE_KINDS) == "manifest_hash_mismatch"


# ---- the canary: unknown upstream text reaches no report format ------------------------


@pytest.mark.parametrize("fmt", ["json", "sarif", "markdown"])
def test_an_unknown_upstream_code_never_reaches_any_report_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fmt: str
) -> None:
    from decoy.__main__ import app

    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    # The shared reader refuses a malformed manifest before the (patched) verifier runs.
    manifest = {
        "schema_version": "cli-local-1",
        "pipeline_path": "pipeline.yaml",
        "pipeline_fingerprint": "sha256:0",
        "input_fingerprints": {},
        "output_fingerprints": {},
        "manifest_hash": "sha256:0",
    }
    write(repo, "build/evidence.json", json.dumps(manifest))
    ev = "  evidence:\n    - {id: e, manifest: build/evidence.json}\n"
    write(repo, MANIFEST_NAME, ci_manifest(extra_checks=ev))

    gate_codes = [
        f"leak_{CANARY}_code",
        f"source.{CANARY}.exists",
        f"target.{CANARY}.would_overwrite",
        f"Mixed Case {CANARY}!",
    ]

    def _gate(*_a: object, **_k: object) -> cli_gate.GateResult:
        findings = [
            cli_gate.GateFinding("config", "error", code, f"msg {CANARY}") for code in gate_codes
        ]
        return cli_gate.GateResult(findings, frozenset({"config"}), False)

    def _issues(*_a: object, **_k: object) -> list[cli_evidence.EvidenceIssue]:
        return [cli_evidence.EvidenceIssue(f"kind_{CANARY}", f"msg {CANARY}")]

    monkeypatch.setattr(cli_gate, "run_gate", _gate)
    monkeypatch.setattr(cli_evidence, "verify_manifest_issues", _issues)
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["ci", "check", MANIFEST_NAME, "--format", fmt])

    out = result.stdout
    assert out.strip(), result.output
    assert CANARY not in result.output
    assert CANARY.upper() not in result.output.upper()
    if fmt == "json":
        rule_ids = {f["rule_id"] for f in json.loads(out)["findings"]}
        assert rule_ids == {
            f"validate.{UNKNOWN_CODE}",
            "validate.source.exists",
            "validate.target.would_overwrite",
            f"evidence.{UNKNOWN_CODE}",
        }


def test_importing_the_ci_modules_does_not_import_the_engine() -> None:
    """`decoy ci` first imports the engine inside engine_logging_silenced, from a scratch cwd,
    so the engine's cwd-relative log file never lands in the checked repository. The allowlist
    must therefore derive the registry half on first use, not when the module is imported."""
    import subprocess
    import sys

    probe = (
        "import sys; import decoy.ci.rule_codes, decoy.ci.adapters, decoy.cli.ci, "
        "decoy.__main__; "
        "print('decoy_engine' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "False"
    import decoy.ci.rule_codes as rule_codes_module

    flat = " ".join((rule_codes_module.__doc__ or "").split())
    assert "at import" not in flat and "on first use" in flat, flat
