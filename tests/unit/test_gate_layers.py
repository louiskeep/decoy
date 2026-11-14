"""The pre-run gate package (`decoy.cli.gate`): entries, result fields and layer rules.

Mutations that turn each cell red are named in its docstring (plan P1,
docs/plans/2026-11-06-validate-always.md, sections 4 and 7).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from tests.csv_sources import csv_source

from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_OK, EXIT_USAGE
from decoy.cli.gate import (
    GateFinding,
    GateResult,
    GateRoute,
    gate_exit_code,
    parse_pipeline_yaml,
    run_config_gate,
    run_gate,
    run_gate_on_config,
)

MARKER = "gatemarker7c2e19"


def _config(tmp_path: Path, *, target_exists: bool = False, parent: str | None = None) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@b.com", "c@d.com"]}).to_csv(src, index=False)
    out = tmp_path / (parent or ".") / "out.csv"
    if target_exists:
        out.write_text("x\n", encoding="utf-8")
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"customers": csv_source(src)},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "cust_ns",
                    }
                ],
            }
        ],
        "targets": {"customers": {"type": "file", "format": "csv", "path": str(out)}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _codes(result: GateResult) -> list[str]:
    return [f.code for f in result.findings]


# -- parse_pipeline_yaml -------------------------------------------------------


def test_parse_returns_a_mapping_unchanged_with_no_findings(tmp_path: Path) -> None:
    raw, findings = parse_pipeline_yaml(tmp_path / "x.yaml", "a: 1\nb: [2, 3]\n")
    assert findings == []
    assert raw == {"a": 1, "b": [2, 3]}


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "yaml.empty"),
        ("# nothing\n", "yaml.empty"),
        ("- a\n- b\n", "yaml.not_mapping"),
        ("just a scalar\n", "yaml.not_mapping"),
        ("42\n", "yaml.not_mapping"),
    ],
)
def test_the_adapter_owns_the_empty_and_non_mapping_refusals(
    tmp_path: Path, text: str, code: str
) -> None:
    """The loader's checks, as findings. Mutation: let the adapter return the raw value."""
    raw, findings = parse_pipeline_yaml(tmp_path / "x.yaml", text)
    assert raw is None
    assert [(f.layer, f.severity, f.code) for f in findings] == [("config", "error", code)]


def test_the_adapter_refuses_non_utf8_bytes_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_bytes(b"a: \xff\n")
    raw, findings = parse_pipeline_yaml(path)
    assert raw is None
    assert [f.code for f in findings] == ["yaml.not_utf8"]
    assert findings[0].message == "Pipeline YAML is not UTF-8 text."


def test_parse_reports_a_syntax_error_without_the_text(tmp_path: Path) -> None:
    raw, findings = parse_pipeline_yaml(tmp_path / "x.yaml", f"a: [{MARKER}\n")
    assert raw is None
    assert [(f.layer, f.severity, f.code) for f in findings] == [
        ("config", "error", "yaml.parse_error")
    ]
    assert MARKER not in findings[0].message


def test_run_gate_and_run_config_gate_compose_the_same_refusals(tmp_path: Path) -> None:
    for fn in (run_gate, run_config_gate):
        assert _codes(fn(tmp_path / "x.yaml", "")) == ["yaml.empty"]
        assert _codes(fn(tmp_path / "x.yaml", "- a\n")) == ["yaml.not_mapping"]
        assert _codes(fn(tmp_path / "x.yaml", "a: [\n")) == ["yaml.parse_error"]


# -- result fields -------------------------------------------------------------


def test_clean_config_returns_the_validated_config_and_checks_run(tmp_path: Path) -> None:
    """Mutation: leave `config` or `checks_run` unset on success."""
    path = _config(tmp_path)
    raw, _ = parse_pipeline_yaml(path)
    result = run_gate_on_config(raw, path)
    assert result.findings == []
    assert result.ran_layers == frozenset({"config", "compile", "preflight"})
    assert result.checks_run and all(isinstance(c, str) for c in result.checks_run)
    assert result.config is not None and result.config["version"] == 2
    assert run_config_gate(path).config == result.config


def test_new_result_fields_are_last_with_defaults() -> None:
    names = [f.name for f in dataclasses.fields(GateResult)]
    assert names[-2:] == ["checks_run", "config"]
    assert GateResult([], frozenset(), False).config is None
    assert dataclasses.fields(GateFinding)[-1].name == "extra"


# -- extra (missing_extra) -----------------------------------------------------


def test_missing_ner_extra_keeps_the_extra_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: drop `extra` from the finding the config layer builds."""
    import decoy_engine
    from decoy_engine.plan import PlanCompileError

    def _no_spacy(_raw: Any, **_kwargs: Any) -> Any:
        raise PlanCompileError("ner_spacy_not_installed", "tables.t.columns.c", "spacy absent")

    monkeypatch.setattr(decoy_engine, "run_config_only_checks", _no_spacy)
    path = _config(tmp_path)
    result = run_gate(path)
    assert [(f.code, f.extra) for f in result.findings] == [("missing_extra", "ner")]
    assert "spacy absent" not in result.findings[0].message


def test_compile_layer_missing_extra_keeps_the_extra_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy_engine.plan as engine_plan

    def _no_spacy(*_a: Any, **_k: Any) -> Any:
        raise engine_plan.PlanCompileError("ner_spacy_not_installed", None, "spacy absent")

    monkeypatch.setattr(engine_plan, "compile_plan", _no_spacy)
    result = run_gate(_config(tmp_path))
    assert [(f.layer, f.code, f.extra) for f in result.findings] == [
        ("compile", "missing_extra", "ner")
    ]


# -- target-overwrite advisory lives in the config layer -----------------------


def test_target_overwrite_is_a_config_layer_warning_once(tmp_path: Path) -> None:
    """Mutation: also call `_check_target_overwrite` in the preflight layer (the code repeats)."""
    path = _config(tmp_path, target_exists=True)
    for result in (run_gate(path), run_config_gate(path)):
        hits = [f for f in result.findings if f.code == "target.customers.would_overwrite"]
        assert [(f.layer, f.severity, f.location) for f in hits] == [
            ("config", "warning", "targets.customers.path")
        ]
        assert gate_exit_code(result, False) == EXIT_OK


def test_missing_target_directory_gives_no_finding(tmp_path: Path) -> None:
    """The writer creates the folder, so a missing parent is not a finding."""
    result = run_config_gate(_config(tmp_path, parent="no_such_dir"))
    assert result.findings == []


def test_unwritable_target_directory_is_a_config_layer_warning(tmp_path: Path) -> None:
    (tmp_path / "blocker").write_text("a file, not a folder\n", encoding="utf-8")
    result = run_config_gate(_config(tmp_path, parent="blocker"))
    assert [(f.layer, f.severity, f.code) for f in result.findings] == [
        ("config", "warning", "target.customers.parent_unwritable")
    ]


# -- route rule ----------------------------------------------------------------


def _fanin(monkeypatch: pytest.MonkeyPatch) -> None:
    import decoy_engine.execution as engine_exec
    from decoy_engine import ExecutionError

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ExecutionError(code="out_of_core_fanin_exceeds_budget", message="fan-in (double)")

    monkeypatch.setattr(engine_exec, "estimate_job_capacity", _boom)


def test_capacity_refusal_is_an_error_on_plain_and_a_warning_on_chunked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: drop the CHUNKED rule in `_run_preflight_layer` (the chunked cell turns red)."""
    _fanin(monkeypatch)
    path = _config(tmp_path)
    raw, _ = parse_pipeline_yaml(path)

    plain = run_gate_on_config(raw, path)
    assert plain.capacity_insufficient
    assert gate_exit_code(plain, False) == EXIT_CAPACITY

    chunked = run_gate_on_config(raw, path, GateRoute.CHUNKED)
    assert not chunked.capacity_insufficient
    hit = [f for f in chunked.findings if f.code == "out_of_core_fanin_exceeds_budget"]
    assert [(f.layer, f.severity) for f in hit] == [("preflight", "warning")]
    assert gate_exit_code(chunked, False) == EXIT_OK


def test_chunked_route_does_not_soften_other_preflight_errors(tmp_path: Path) -> None:
    path = _config(tmp_path)
    (tmp_path / "in.csv").unlink()
    raw, _ = parse_pipeline_yaml(path)
    result = run_gate_on_config(raw, path, GateRoute.CHUNKED)
    errors = [f for f in result.findings if f.severity == "error"]
    assert [f.code for f in errors] == ["source.customers.exists"]
    assert gate_exit_code(result, False) == EXIT_USAGE


# -- value-free unreadable-source text -----------------------------------------


def test_unreadable_source_text_carries_no_reader_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: restore `{exc.message}` in `_check_capacity` (the reader text returns)."""
    import decoy_engine.profile as engine_profile

    def _bad_read(*_a: Any, **_k: Any) -> Any:
        raise ValueError(f"bad row {MARKER}")

    monkeypatch.setattr(engine_profile, "profile_source", _bad_read)
    result = run_gate(_config(tmp_path))
    hit = [f for f in result.findings if f.code == "capacity_source_unprofilable"]
    assert [(f.layer, f.severity) for f in hit] == [("preflight", "error")]
    assert "ValueError" in hit[0].message
    assert MARKER not in hit[0].message
    assert MARKER not in str(hit[0])
