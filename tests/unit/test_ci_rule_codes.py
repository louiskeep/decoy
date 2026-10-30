"""The emitted `rule_id` is drawn from a closed allowlist, never from upstream text.

Two halves: an unknown code carrying a canary reaches none of the three report formats,
and every code the pinned engine, the CLI gate, and the evidence verifier can produce today
is in the allowlist -- so a new upstream code fails here and forces an explicit decision
instead of silently collapsing to `unknown_code`.
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
import decoy.cli.preflight as cli_preflight
import decoy.cli.validate as cli_validate
from decoy.ci.rule_codes import (
    EVIDENCE_KINDS,
    UNKNOWN_CODE,
    VALIDATION_CODES,
    rule_code,
)

CANARY = "rulecanary7d41e0"

_CODE_TOKEN = re.compile(r"^[a-z][a-z0-9_.-]*$")
_CODE_NAME = re.compile(r"(^|_)(CODES?|REASONS?)$")

# f-string `code=` sites in the pinned engine, each with the decision taken for it. The
# expansions are in the allowlist; a run-time-only site the gate cannot reach stays out
# (it would map to UNKNOWN_CODE). A new dynamic site fails until it is added here.
_ENGINE_DYNAMIC_CODES: dict[str, tuple[str, ...]] = {
    "plan/_checks_grouped_series.py": (
        "grouped_series_missing_group_by_ref",
        "grouped_series_missing_order_by_ref",
    ),
    "execution/_sequential_native.py": (),
}


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


def _engine_codes() -> tuple[set[str], set[str]]:
    """Literal codes the engine raises or reports, plus the files with f-string codes."""
    import decoy_engine

    root = Path(decoy_engine.__file__).parent
    codes: set[str] = set()
    dynamic: set[str] = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            values: list[ast.AST] = []
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in ("code", "reason"):
                        values.append(kw.value)
                        if isinstance(kw.value, ast.JoinedStr) and kw.arg == "code":
                            dynamic.add(rel)
                name = _call_name(node)
                if node.args and (name.endswith("Error") or name.endswith("Exception")):
                    values.append(node.args[0])
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and _CODE_NAME.search(t.id) for t in targets):
                    values.append(node.value)
            for value in values:
                codes.update(s for s in _literals(value) if _CODE_TOKEN.match(s))
    return codes, dynamic


def _module_tree(module: object) -> ast.AST:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))  # type: ignore[attr-defined]


def _cli_gate_codes() -> tuple[set[str], set[str]]:
    """Codes `run_gate` attaches itself, and the f-string preflight check names."""
    codes: set[str] = set()
    templates: set[str] = set()
    for node in ast.walk(_module_tree(cli_validate)):
        if isinstance(node, ast.Call) and _call_name(node) == "_GateFinding":
            if len(node.args) > 2 and isinstance(node.args[2], ast.Constant):
                codes.add(node.args[2].value)
        # The pydantic fallback: `e.get("type", "validation_error")`.
        if isinstance(node, ast.Call) and _call_name(node) == "get" and len(node.args) == 2:
            if isinstance(node.args[0], ast.Constant) and node.args[0].value == "type":
                codes.update(_literals(node.args[1]))
    gate_checks = {"_check_source_files", "_check_target_overwrite", "_check_capacity", "_check_native"}
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


def test_every_engine_code_is_allowlisted() -> None:
    codes, dynamic = _engine_codes()
    assert codes, "the engine scan found nothing; the scanner is broken"
    assert dynamic == set(_ENGINE_DYNAMIC_CODES), (
        "a new f-string engine code site needs an explicit allowlist decision"
    )
    expanded = {c for group in _ENGINE_DYNAMIC_CODES.values() for c in group}
    assert sorted((codes | expanded) - VALIDATION_CODES) == []


def test_every_pydantic_error_type_is_allowlisted() -> None:
    assert sorted(_pydantic_error_types() - VALIDATION_CODES) == []


def test_every_cli_gate_code_and_preflight_template_is_allowlisted() -> None:
    codes, templates = _cli_gate_codes()
    assert {"yaml.parse_error", "missing_extra", "validation_error"} <= codes
    assert sorted(codes - VALIDATION_CODES) == []
    assert templates, "the preflight scan found no templated check names"
    for template in templates:
        emitted = rule_code(template.format(CANARY), VALIDATION_CODES)
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
        ("Unknown_Provider", UNKNOWN_CODE),
        ("odd code!", UNKNOWN_CODE),
        ("", UNKNOWN_CODE),
        (None, UNKNOWN_CODE),
        (f"leak_{CANARY}", UNKNOWN_CODE),
        ("x" * 300, UNKNOWN_CODE),
    ],
)
def test_validation_codes_map_through_the_allowlist(code: object, expected: str) -> None:
    assert rule_code(code, VALIDATION_CODES) == expected


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
    write(repo, "build/evidence.json", "{}\n")
    ev = "  evidence:\n    - {id: e, manifest: build/evidence.json}\n"
    write(repo, MANIFEST_NAME, ci_manifest(extra_checks=ev))

    gate_codes = [
        f"leak_{CANARY}_code",
        f"source.{CANARY}.exists",
        f"target.{CANARY}.would_overwrite",
        f"Mixed Case {CANARY}!",
    ]

    def _gate(*_a: object, **_k: object) -> cli_validate.GateResult:
        findings = [
            cli_validate._GateFinding("config", "error", code, f"msg {CANARY}")
            for code in gate_codes
        ]
        return cli_validate.GateResult(findings, frozenset({"config"}), False)

    def _issues(*_a: object, **_k: object) -> list[cli_evidence.EvidenceIssue]:
        return [cli_evidence.EvidenceIssue(f"kind_{CANARY}", f"msg {CANARY}")]

    monkeypatch.setattr(cli_validate, "run_gate", _gate)
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
