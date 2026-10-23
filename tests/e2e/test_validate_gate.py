"""E2E tests for the default `decoy validate CONFIG` pre-run gate (S2b).

`decoy validate CONFIG` (the `validate` group invoked with a config path and NO
subcommand) runs the WHOLE pre-run gate -- the shared config base, then the
compile layer and the preflight layer -- and emits one report grouped by layer
plus one aggregated exit code. The subcommands (`config`/`compile`/`preflight`/
`distribution`) keep their own single-layer behavior and are covered by their
own suites; this file pins only the aggregate.

Coverage:
G1. clean config -> exit 0, the report shows all three layers passing.
G2. dedup -> `run_config_only_checks` is called EXACTLY ONCE for the default
    gate (not once per layer).
G3. schema error -> EXIT_USAGE, and compile/preflight are NOT run (short-circuit).
G4. a failed compile check -> EXIT_USAGE (aggregate, a compile-layer finding).
G5. a missing source -> EXIT_USAGE (a preflight-layer finding).
G6. capacity fan-in -> EXIT_CAPACITY, and it OUTRANKS a co-occurring compile fail.
G7. warnings + --fail-on-warning -> EXIT_WARNINGS; clean-but-warn without the
    flag -> 0.
G8. the `--json` envelope shape + `messages[]` item shape + status->severity map.

Config fixtures mirror the shapes used by the existing validate/preflight/
compile suites (`test_preflight_command.py`, `test_preflight_capacity.py`,
`test_compile_explain_command.py`).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_OK, EXIT_USAGE, EXIT_WARNINGS

runner = CliRunner()


# ---------------------------------------------------------------------------
# Config fixtures (same shapes the per-command suites use)
# ---------------------------------------------------------------------------


def _clean_config(tmp_path: Path) -> Path:
    """A config that passes every layer: the source CSV exists, it compiles
    no-profile, and preflight finds nothing wrong (mirrors
    test_preflight_command._valid_config)."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@b.com", "c@d.com"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
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
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _missing_source_config(tmp_path: Path) -> Path:
    """Valid schema + compiles clean, but the declared source CSV is absent."""
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "DOES_NOT_EXIST.csv"),
            }
        },
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
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _schema_error_config(tmp_path: Path) -> Path:
    """Missing the required `version` field -> pydantic schema error."""
    cfg = {"global_settings": {"seed": 42}, "sources": {}, "tables": [], "targets": {}}
    p = tmp_path / "no_version.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _compile_fail_config(tmp_path: Path, *, with_source: bool = True) -> Path:
    """Passes the config base (schema + config-only checks) but fails the
    compile layer: a `cardinality_mode: unique` column is incompatible with the
    gate's no-profile compile (the H2 guard reused from `validate compile`)."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@b.com", "c@d.com"]}).to_csv(src, index=False)
    path = str(src) if with_source else str(tmp_path / "ABSENT.csv")
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": path}},
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
                        "cardinality_mode": "unique",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _fk_config(tmp_path: Path, *, unique_cardinality: bool = False) -> Path:
    """A real FK parquet job (mirrors test_preflight_capacity._write_config). The
    capacity estimator is monkeypatched in the tests; this just provides sources
    that exist so the capacity check actually reaches the estimator. With
    `unique_cardinality`, the compile layer ALSO fails (for the outranks test)."""
    parent = pa.table({"id": pa.array([f"p{i}" for i in range(8)], type=pa.string())})
    child = pa.table(
        {
            "cid": pa.array([f"c{i}" for i in range(8)], type=pa.string()),
            "parent_id": pa.array([f"p{i}" for i in range(8)], type=pa.string()),
        }
    )
    pq.write_table(parent, tmp_path / "parent.parquet")
    pq.write_table(child, tmp_path / "child.parquet")
    parent_cols: list[dict[str, Any]] = [{"name": "id", "strategy": "hash", "namespace": "ns"}]
    if unique_cardinality:
        parent_cols[0]["cardinality_mode"] = "unique"
    cfg = {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {
            "parent": {"type": "file", "path": str(tmp_path / "parent.parquet"), "format": "parquet"},
            "child": {"type": "file", "path": str(tmp_path / "child.parquet"), "format": "parquet"},
        },
        "targets": {
            "parent": {
                "type": "file",
                "path": str(tmp_path / "parent.out.parquet"),
                "format": "parquet",
            },
            "child": {
                "type": "file",
                "path": str(tmp_path / "child.out.parquet"),
                "format": "parquet",
            },
        },
        "tables": [
            {"name": "parent", "columns": parent_cols},
            {
                "name": "child",
                "columns": [
                    {"name": "cid", "strategy": "hash", "namespace": "cns"},
                    {"name": "parent_id", "strategy": "hash", "namespace": "ns"},
                ],
            },
        ],
        "relationships": [
            {
                "parent": {"table": "parent", "columns": ["id"]},
                "children": [{"table": "child", "columns": ["parent_id"]}],
                "orphan_policy": "preserve",
                "namespace": "ns",
            }
        ],
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _gate(config_path: Path, *extra: str) -> Any:
    return runner.invoke(app, ["validate", str(config_path), *extra])


# ---------------------------------------------------------------------------
# G1: clean config -> exit 0, all three layers pass
# ---------------------------------------------------------------------------


def test_gate_clean_config_exits_ok_all_layers_pass(tmp_path: Path) -> None:
    result = _gate(_clean_config(tmp_path))
    assert result.exit_code == EXIT_OK, result.output
    squashed = "".join(result.output.split())
    assert "Config:passed" in squashed
    assert "Compile:passed" in squashed
    assert "Preflight:passed" in squashed


# ---------------------------------------------------------------------------
# G2: dedup -- run_config_only_checks fires exactly once for the default gate
# ---------------------------------------------------------------------------


def test_gate_runs_config_only_checks_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy_engine

    real = decoy_engine.run_config_only_checks
    calls = {"n": 0}

    def _spy(raw: Any) -> Any:
        calls["n"] += 1
        return real(raw)

    monkeypatch.setattr(decoy_engine, "run_config_only_checks", _spy)
    result = _gate(_clean_config(tmp_path))
    assert result.exit_code == EXIT_OK, result.output
    assert calls["n"] == 1, (
        f"the default gate must call run_config_only_checks exactly once, got {calls['n']}"
    )


# ---------------------------------------------------------------------------
# G3: schema error -> EXIT_USAGE and compile/preflight are NOT run
# ---------------------------------------------------------------------------


def test_gate_schema_error_short_circuits(tmp_path: Path) -> None:
    result = _gate(_schema_error_config(tmp_path))
    assert result.exit_code == EXIT_USAGE, result.output
    squashed = "".join(result.output.split())
    # Compile / preflight layers never ran -> not reported as "passed".
    assert "Compile:passed" not in squashed
    assert "Preflight:passed" not in squashed


def test_gate_schema_error_does_not_run_compile_or_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy.cli.validate as validate_mod

    tripped = {"compile": False, "preflight": False}

    def _fail_compile(*_a: Any, **_k: Any) -> Any:
        tripped["compile"] = True
        return []

    def _fail_preflight(*_a: Any, **_k: Any) -> Any:
        tripped["preflight"] = True
        return [], False

    monkeypatch.setattr(validate_mod, "_run_compile_layer", _fail_compile)
    monkeypatch.setattr(validate_mod, "_run_preflight_layer", _fail_preflight)
    result = _gate(_schema_error_config(tmp_path))
    assert result.exit_code == EXIT_USAGE, result.output
    assert tripped == {"compile": False, "preflight": False}


# ---------------------------------------------------------------------------
# G4: a failed compile check -> EXIT_USAGE
# ---------------------------------------------------------------------------


def test_gate_failed_compile_check_exits_usage(tmp_path: Path) -> None:
    result = _gate(_compile_fail_config(tmp_path))
    assert result.exit_code == EXIT_USAGE, result.output
    payload = _json.loads(_gate(_compile_fail_config(tmp_path), "--json").output)
    compile_errors = [
        m for m in payload["messages"] if m["layer"] == "compile" and m["severity"] == "error"
    ]
    assert compile_errors, payload


# ---------------------------------------------------------------------------
# G5: a missing source -> EXIT_USAGE (preflight layer)
# ---------------------------------------------------------------------------


def test_gate_missing_source_exits_usage(tmp_path: Path) -> None:
    result = _gate(_missing_source_config(tmp_path))
    assert result.exit_code == EXIT_USAGE, result.output
    assert "DOES_NOT_EXIST" in "".join(result.output.split())
    payload = _json.loads(_gate(_missing_source_config(tmp_path), "--json").output)
    preflight_errors = [
        m for m in payload["messages"] if m["layer"] == "preflight" and m["severity"] == "error"
    ]
    assert preflight_errors, payload


# ---------------------------------------------------------------------------
# G6: capacity fan-in -> EXIT_CAPACITY, outranking a co-occurring compile fail
# ---------------------------------------------------------------------------


def _patch_fanin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the capacity estimator raise the fan-in refusal (same double the
    preflight suite uses for the propagated-fan-in path)."""
    import decoy_engine.execution as engine_exec
    from decoy_engine import ExecutionError

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ExecutionError(
            code="out_of_core_fanin_exceeds_budget",
            message="fan-in exceeds budget (test double).",
        )

    monkeypatch.setattr(engine_exec, "estimate_job_capacity", _boom)


def test_gate_capacity_fanin_exits_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fanin(monkeypatch)
    result = _gate(_fk_config(tmp_path))
    assert result.exit_code == EXIT_CAPACITY, result.output


def test_gate_capacity_outranks_compile_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fanin(monkeypatch)
    # unique_cardinality makes the compile layer ALSO fail; capacity must win.
    result = _gate(_fk_config(tmp_path, unique_cardinality=True), "--json")
    assert result.exit_code == EXIT_CAPACITY, result.output
    payload = _json.loads(result.output)
    layers = {(m["layer"], m["severity"]) for m in payload["messages"]}
    # The report shows BOTH the compile fail and the preflight capacity fail.
    assert ("compile", "error") in layers, payload
    assert ("preflight", "error") in layers, payload
    fanin = [m for m in payload["messages"] if m["code"] == "out_of_core_fanin_exceeds_budget"]
    assert fanin, payload


# ---------------------------------------------------------------------------
# G7: warnings + --fail-on-warning -> EXIT_WARNINGS; without the flag -> 0
# ---------------------------------------------------------------------------


def _patch_capacity_advisory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the capacity estimator return a FIT-but-warned verdict, which the
    preflight capacity check renders as an advisory WARNING (not a refusal)."""
    import decoy_engine.execution as engine_exec
    from decoy_engine import CapacityVerdict

    def _warned(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(
            verdict=CapacityVerdict.FIT,
            warned=True,
            needed_bytes=70 * 1024**3,
            available_bytes=64 * 1024**3,
            message="relation-build floor nears its cap.",
            code=None,
        )

    monkeypatch.setattr(engine_exec, "estimate_job_capacity", _warned)


def test_gate_clean_but_warn_exits_ok_without_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_capacity_advisory(monkeypatch)
    result = _gate(_fk_config(tmp_path))
    assert result.exit_code == EXIT_OK, result.output
    assert "ADVISORY" in result.output


def test_gate_warn_with_fail_on_warning_exits_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_capacity_advisory(monkeypatch)
    result = _gate(_fk_config(tmp_path), "--fail-on-warning")
    assert result.exit_code == EXIT_WARNINGS, result.output


# ---------------------------------------------------------------------------
# G8: the --json envelope shape + messages[] item shape + status->severity map
# ---------------------------------------------------------------------------


def test_gate_json_envelope_clean(tmp_path: Path) -> None:
    result = _gate(_clean_config(tmp_path), "--json")
    assert result.exit_code == EXIT_OK, result.output
    payload = _json.loads(result.output)
    assert payload["command"] == "validate"
    assert payload["status"] == "ok"
    assert payload["messages"] == []  # a clean gate carries no findings


def test_gate_json_message_item_shape_and_severity_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fanin(monkeypatch)
    result = _gate(_fk_config(tmp_path, unique_cardinality=True), "--json")
    payload = _json.loads(result.output)
    assert payload["command"] == "validate"
    assert payload["status"] == "error"  # any error finding -> status error
    assert payload["messages"], payload
    for m in payload["messages"]:
        # Every message carries the full, stable item shape.
        assert set(m.keys()) == {"layer", "severity", "code", "message", "location"}
        assert m["layer"] in {"config", "compile", "preflight"}
        assert m["severity"] in {"error", "warning"}  # pass never appears


def test_gate_json_status_warn_only_under_fail_on_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_capacity_advisory(monkeypatch)
    # Without the flag: a warning present but status stays "ok" (exit 0).
    ok = _json.loads(_gate(_fk_config(tmp_path), "--json").output)
    assert ok["status"] == "ok"
    warn_msgs = [m for m in ok["messages"] if m["severity"] == "warning"]
    assert warn_msgs, ok  # the advisory warning IS in the report
    # With the flag: the same warning promotes the envelope status to "warn".
    flagged = _json.loads(_gate(_fk_config(tmp_path), "--json", "--fail-on-warning").output)
    assert flagged["status"] == "warn"
