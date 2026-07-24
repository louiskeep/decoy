"""T8 (docs/plans/2026-07-24-oom-checker-cli-v1.md, "Revised acceptance
tests"): one job, run through BOTH `decoy preflight` and `decoy run`, must
agree -- preflight INSUFFICIENT <=> run raises + exits EXIT_CAPACITY. Real
derivation on both sides (real files, real `evaluate_capacity`), not a
mocked verdict standing in for either command.

Parametrized over fit and insufficient (the `out_of_core_insufficient_memory`
code). The sibling `out_of_core_fanin_exceeds_budget` refusal needs a
many-distinct-parent-tables-into-one-child topology to occur through a real
FK graph, which sits awkwardly against the out-of-core route's
single-parent-per-child compatibility gate -- that code's evaluator-level
parity (same inputs, same evaluator, same raise) is covered in
decoy-engine's own `test_capacity_evaluator.py`; this file exercises the one
that arises naturally through a real CLI job, `out_of_core_insufficient_memory`.

Both commands need the SAME lowered out-of-core size threshold (neither
exposes a CLI flag for it): `low_threshold` patches `decoy_engine.execution.
capacity.decide_execution_route` for preflight and `decoy_engine.run_pipeline`
for run, both with the identical override, so the two commands see the
identical routing knob.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_OK

runner = CliRunner()


def _hash_col(name: str, namespace: str) -> dict[str, Any]:
    return {"name": name, "strategy": "hash", "namespace": namespace}


def _parent_child_tables(n: int) -> tuple[pa.Table, pa.Table]:
    parent = pa.table(
        {
            "id": pa.array([f"p{i}" for i in range(n)], type=pa.string()),
            "note": pa.array([f"secret{i}" for i in range(n)], type=pa.string()),
        }
    )
    child = pa.table(
        {
            "cid": pa.array([f"c{i}" for i in range(n)], type=pa.string()),
            "parent_id": pa.array([f"p{i}" for i in range(n)], type=pa.string()),
        }
    )
    return parent, child


def _write_config(tmp_path: Path, parent: pa.Table, child: pa.Table) -> Path:
    pq.write_table(parent, tmp_path / "parent.parquet")
    pq.write_table(child, tmp_path / "child.parquet")
    cfg = {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {
            "parent": {
                "type": "file",
                "path": str(tmp_path / "parent.parquet"),
                "format": "parquet",
            },
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
            {
                "name": "parent",
                "columns": [_hash_col("id", "ns"), {"name": "note", "strategy": "redact"}],
            },
            {"name": "child", "columns": [_hash_col("cid", "cns"), _hash_col("parent_id", "ns")]},
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


@pytest.fixture()
def low_threshold_both_commands(monkeypatch: pytest.MonkeyPatch):
    """The SAME lowered out-of-core threshold for both `decoy preflight`
    (patches the estimator's own routing call) and `decoy run` (patches
    `decoy_engine.run_pipeline`, the seam `run.py` imports fresh per
    invocation) -- one fixture, so a parity test can never accidentally
    compare the two commands under different routing knobs."""
    import decoy_engine
    import decoy_engine.execution.capacity as capacity_mod

    real_decide = capacity_mod.decide_execution_route
    real_run_pipeline = decoy_engine.run_pipeline

    def _patched_decide(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("out_of_core_threshold_rows", 10)
        kwargs.setdefault("full_frame_reject_rows", 10)
        return real_decide(*args, **kwargs)

    def _patched_run_pipeline(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("out_of_core_threshold_rows", 10)
        kwargs.setdefault("full_frame_reject_rows", 10)
        return real_run_pipeline(*args, **kwargs)

    monkeypatch.setattr(capacity_mod, "decide_execution_route", _patched_decide)
    monkeypatch.setattr(decoy_engine, "run_pipeline", _patched_run_pipeline)


class TestParity:
    def test_fit_agrees_preflight_ok_run_succeeds(
        self, tmp_path: Path, low_threshold_both_commands
    ) -> None:
        parent, child = _parent_child_tables(40)
        config_path = _write_config(tmp_path, parent, child)

        preflight_result = runner.invoke(app, ["preflight", str(config_path)])
        assert preflight_result.exit_code == EXIT_OK
        assert "OK" in preflight_result.output

        run_result = runner.invoke(app, ["run", str(config_path)])
        assert run_result.exit_code == EXIT_OK

    def test_insufficient_agrees_preflight_and_run_both_refuse(
        self, tmp_path: Path, low_threshold_both_commands
    ) -> None:
        # A parent large enough to push its floor past the resolved budget
        # even a 1 MiB detected ceiling floors at (_MIN_BUDGET_BYTES, 64 MiB).
        parent, child = _parent_child_tables(300_000)
        config_path = _write_config(tmp_path, parent, child)

        with mock.patch(
            "decoy_engine.execution.out_of_core._budget.detect_effective_memory_bytes",
            return_value=1024 * 1024,
        ):
            preflight_result = runner.invoke(app, ["preflight", str(config_path)])
            run_result = runner.invoke(app, ["run", str(config_path)])

        assert preflight_result.exit_code == EXIT_CAPACITY
        assert "INSUFFICIENT" in preflight_result.output

        assert run_result.exit_code == EXIT_CAPACITY
        assert "capacity:" in run_result.output
