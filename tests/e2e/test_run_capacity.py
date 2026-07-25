"""Part A of the OOM checker v1 (docs/plans/2026-07-24-oom-checker-cli-v1.md):
`decoy run` labels the engine's out-of-core-FK memory-capacity refusal as a
distinct, machine-detectable result instead of the generic runtime-error path.

T1/T2/T3 ("Revised acceptance tests"): injects the engine's `ExecutionError`
at the run's execution seam (`decoy_engine.run_pipeline`, the same seam
`tests/sentry/test_notify_redaction.py` already patches to simulate an
engine-side failure) rather than actually starving a real job -- the point
here is the CLI's dispatch/render/JSON-envelope behavior, not the engine's
own memory math (that lives in decoy-engine's own test suite).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_RUNTIME, EXIT_USAGE

runner = CliRunner()


def _write_mask_config(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"customer_id": ["1", "2"], "email": ["a@x.com", "b@x.com"]}).to_csv(
        src, index=False
    )
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [{"name": "email", "strategy": "redact"}],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _capacity_error(code: str):
    from decoy_engine.execution import ExecutionError

    return ExecutionError(
        code=code,
        message=f"predicted resident floor exceeds the actual build cap; this job needs "
        f"approximately 8 GB of memory ({code}).",
    )


class TestPartAHumanOutput:
    def test_insufficient_memory_exits_capacity_with_labeled_line(self, tmp_path: Path) -> None:
        cfg_path = _write_mask_config(tmp_path)
        with mock.patch(
            "decoy_engine.run_pipeline",
            side_effect=_capacity_error("out_of_core_insufficient_memory"),
        ):
            result = runner.invoke(app, ["run", str(cfg_path)])
        assert result.exit_code == EXIT_CAPACITY
        assert "capacity:" in result.output
        assert "GB of memory" in result.output

    def test_fanin_exceeds_budget_also_exits_capacity(self, tmp_path: Path) -> None:
        cfg_path = _write_mask_config(tmp_path)
        with mock.patch(
            "decoy_engine.run_pipeline",
            side_effect=_capacity_error("out_of_core_fanin_exceeds_budget"),
        ):
            result = runner.invoke(app, ["run", str(cfg_path)])
        assert result.exit_code == EXIT_CAPACITY
        assert "capacity:" in result.output


class TestPartAJsonEnvelope:
    def test_json_envelope_keeps_existing_fields_and_adds_capacity_fields(
        self, tmp_path: Path
    ) -> None:
        cfg_path = _write_mask_config(tmp_path)
        with mock.patch(
            "decoy_engine.run_pipeline",
            side_effect=_capacity_error("out_of_core_insufficient_memory"),
        ):
            result = runner.invoke(app, ["run", str(cfg_path), "--json"])
        assert result.exit_code == EXIT_CAPACITY
        payload = _json.loads(result.output)
        # R7: command/config/mode/error are never dropped by the capacity branch.
        assert payload["command"] == "run"
        assert payload["status"] == "error"
        assert payload["config"] == str(cfg_path)
        assert payload["mode"] == "mask"
        assert payload.get("error")
        # New fields the capacity branch adds.
        assert payload["error_kind"] == "capacity"
        assert payload["code"] == "out_of_core_insufficient_memory"


class TestPartANegatives:
    """T3: narrow code match -- a non-capacity ExecutionError and a config
    error must NOT be reclassified."""

    def test_non_capacity_execution_error_still_exits_runtime(self, tmp_path: Path) -> None:
        cfg_path = _write_mask_config(tmp_path)
        with mock.patch(
            "decoy_engine.run_pipeline",
            side_effect=_capacity_error("orphan_fk_violation"),
        ):
            result = runner.invoke(app, ["run", str(cfg_path)])
        assert result.exit_code == EXIT_RUNTIME
        assert "capacity:" not in result.output

    def test_config_error_still_exits_usage(self, tmp_path: Path) -> None:
        # A config that fails PipelineConfig schema validation (unknown
        # top-level key) never reaches run_pipeline at all -- confirms the
        # capacity branch does not widen the EXIT_USAGE type-dispatch above it.
        bad_cfg = tmp_path / "bad.yaml"
        bad_cfg.write_text(yaml.dump({"version": 1, "not_a_real_key": True}), encoding="utf-8")
        result = runner.invoke(app, ["run", str(bad_cfg)])
        assert result.exit_code == EXIT_USAGE
        assert "capacity:" not in result.output
