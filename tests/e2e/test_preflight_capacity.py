"""Part B of the OOM checker v1 (docs/plans/2026-07-24-oom-checker-cli-v1.md):
`decoy preflight`'s capacity section.

T7 ("Revised acceptance tests"): the four capacity states (fit / insufficient
/ unknown / not-applicable) each render their own line and exit
0 / EXIT_CAPACITY / 0 / 0 -- INSUFFICIENT must exit EXIT_CAPACITY, never
preflight's generic has_failures -> EXIT_USAGE path. Also covers a relative
source-path case and the out-of-core size-threshold boundary.

`decide_execution_route`'s `out_of_core_threshold_rows` default is
5,000,000 rows; `estimate_job_capacity` exposes no override (R2's pinned
signature), so `low_threshold` monkeypatches `decoy_engine.execution.
capacity.decide_execution_route` with a thin wrapper that lowers it --
mirrors the engine-side test suite's own trick, one layer up (through the
real CLI command instead of calling the estimator directly).
"""

from __future__ import annotations

import json as _json
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

_N = 40


def _hash_col(name: str, namespace: str) -> dict[str, Any]:
    return {"name": name, "strategy": "hash", "namespace": namespace}


def _parent_child_tables(n: int = _N) -> tuple[pa.Table, pa.Table]:
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


def _write_config(
    tmp_path: Path,
    *,
    relative_paths: bool = False,
    tables: tuple[pa.Table, pa.Table] | None = None,
) -> Path:
    """A pure-mask FK job (hash keys + a redact payload -- both out-of-core
    supported) with real Parquet sources, written under `tmp_path`."""
    parent, child = tables if tables is not None else _parent_child_tables()
    pq.write_table(parent, tmp_path / "parent.parquet")
    pq.write_table(child, tmp_path / "child.parquet")

    parent_path = "parent.parquet" if relative_paths else str(tmp_path / "parent.parquet")
    child_path = "child.parquet" if relative_paths else str(tmp_path / "child.parquet")

    cfg = {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {
            "parent": {"type": "file", "path": parent_path, "format": "parquet"},
            "child": {"type": "file", "path": child_path, "format": "parquet"},
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


def _no_relationships_config(tmp_path: Path) -> Path:
    src = tmp_path / "flat.parquet"
    pq.write_table(pa.table({"id": pa.array(range(_N))}), src)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 1},
        "sources": {"flat": {"type": "file", "path": str(src), "format": "parquet"}},
        "tables": [{"name": "flat", "columns": [{"name": "id", "strategy": "passthrough"}]}],
        "targets": {
            "flat": {
                "type": "file",
                "path": str(tmp_path / "flat.out.parquet"),
                "format": "parquet",
            }
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


@pytest.fixture()
def low_threshold(monkeypatch: pytest.MonkeyPatch):
    """Lower the engine's out-of-core size thresholds so the 40-row fixture
    routes `out_of_core` instead of `sequential` -- a test-only wrapper
    around `decide_execution_route`, mirroring decoy-engine's own
    `test_lazy_path_route_admission.py` trick."""
    import decoy_engine.execution.capacity as capacity_mod

    real_decide = capacity_mod.decide_execution_route

    def _patched(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("out_of_core_threshold_rows", 10)
        kwargs.setdefault("full_frame_reject_rows", 10)
        return real_decide(*args, **kwargs)

    monkeypatch.setattr(capacity_mod, "decide_execution_route", _patched)


def _run_preflight(config_path: Path, *, json_mode: bool = False) -> Any:
    args = ["preflight", str(config_path)]
    if json_mode:
        args.append("--json")
    return runner.invoke(app, args)


class TestFourCapacityStates:
    def test_not_applicable_no_relationships(self, tmp_path: Path) -> None:
        config_path = _no_relationships_config(tmp_path)
        result = _run_preflight(config_path)
        assert result.exit_code == EXIT_OK
        assert "capacity:" in result.output
        assert "not applicable" in result.output

    def test_not_applicable_below_size_threshold(self, tmp_path: Path) -> None:
        # No low_threshold fixture: at the real 5,000,000-row default this
        # 40-row FK fixture is sequential-bound, not out-of-core-bound.
        config_path = _write_config(tmp_path)
        result = _run_preflight(config_path)
        assert result.exit_code == EXIT_OK
        assert "capacity:" in result.output
        assert "not applicable" in result.output

    def test_fit(self, tmp_path: Path, low_threshold) -> None:
        config_path = _write_config(tmp_path)
        result = _run_preflight(config_path)
        assert result.exit_code == EXIT_OK
        assert "capacity:" in result.output
        assert "OK" in result.output

    def test_insufficient_exits_capacity_not_usage(self, tmp_path: Path, low_threshold) -> None:
        # A large-enough parent to push its floor past even the 64 MiB
        # `_MIN_BUDGET_BYTES` resolve_ooc_memory_limit floors any budget at.
        big_parent, big_child = _parent_child_tables(300_000)
        config_path = _write_config(tmp_path, tables=(big_parent, big_child))
        with mock.patch(
            "decoy_engine.execution.out_of_core._budget.detect_effective_memory_bytes",
            return_value=1024 * 1024,  # 1 MiB ceiling -> a tiny resolved budget
        ):
            result = _run_preflight(config_path)
        assert result.exit_code == EXIT_CAPACITY
        assert "capacity:" in result.output
        assert "INSUFFICIENT" in result.output

    def test_unknown_older_engine_simulated(self, tmp_path: Path, monkeypatch) -> None:
        """T9 groundwork: with the estimator entrypoint absent (simulating an
        engine older than the one that ships it), the capacity section
        degrades to UNKNOWN/"not checked" and exits 0."""
        import decoy_engine.execution as engine_execution

        monkeypatch.delattr(engine_execution, "estimate_job_capacity")
        config_path = _write_config(tmp_path)
        result = _run_preflight(config_path)
        assert result.exit_code == EXIT_OK
        assert "capacity:" in result.output
        assert "not checked" in result.output
        assert "newer engine" in result.output


class TestJsonEnvelope:
    def test_insufficient_json_carries_code_without_parsing_text(
        self, tmp_path: Path, low_threshold
    ) -> None:
        big_parent, big_child = _parent_child_tables(300_000)
        config_path = _write_config(tmp_path, tables=(big_parent, big_child))
        with mock.patch(
            "decoy_engine.execution.out_of_core._budget.detect_effective_memory_bytes",
            return_value=1024 * 1024,
        ):
            result = _run_preflight(config_path, json_mode=True)
        assert result.exit_code == EXIT_CAPACITY
        payload = _json.loads(result.output)
        assert payload["capacity"]["status"] == "fail"
        assert payload["capacity"]["code"] in {
            "out_of_core_insufficient_memory",
            "out_of_core_fanin_exceeds_budget",
        }
        capacity_checks = [c for c in payload["checks"] if c["name"] == "capacity.out_of_core_fk"]
        assert capacity_checks[0]["code"] == payload["capacity"]["code"]


class TestRelativeSourcePath:
    def test_relative_path_resolves_against_yaml_directory(
        self, tmp_path: Path, low_threshold
    ) -> None:
        # Asserted on the `capacity` block specifically, not the overall exit
        # code: preflight's OTHER (pre-existing, unrelated) file-existence
        # check resolves relative source paths against CWD, not the YAML's
        # directory (R2 documents this as a known asymmetry it does not
        # touch) -- it would report the relative path missing when the test
        # runner's CWD differs from tmp_path, muddying an exit-code assertion
        # that has nothing to do with the capacity section under test here.
        # The capacity check itself DOES resolve against the YAML directory
        # (this module's `low_threshold`-independent base_dir plumbing), so a
        # `capacity: OK` here is exactly what proves R2's requirement.
        config_path = _write_config(tmp_path, relative_paths=True)
        result = _run_preflight(config_path, json_mode=True)
        payload = _json.loads(result.output)
        assert payload["capacity"]["status"] == "pass"
        assert "OK" in payload["capacity"]["message"]


class TestExecutionNeverDispatched:
    def test_preflight_never_calls_the_execution_entrypoint(
        self, tmp_path: Path, low_threshold
    ) -> None:
        config_path = _write_config(tmp_path)
        with mock.patch(
            "decoy_engine.execution.out_of_core.run_fk_out_of_core",
            side_effect=AssertionError("preflight must never dispatch to the runner"),
        ) as spy:
            result = _run_preflight(config_path)
        assert result.exit_code == EXIT_OK
        spy.assert_not_called()
