"""`decoy run` exits 5 for every engine capacity code and keeps the exit of the codes the engine
lists as not capacity. The set comes from the engine; the CLI keeps no copy."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_RUNTIME
from tests.csv_sources import csv_source

runner = CliRunner()


def _config(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"code": ["AAAAA", "BBBBB"]}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {"t": csv_source(src)},
        "tables": [{"name": "t", "columns": [{"name": "code", "strategy": "redact"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _run(tmp_path: Path, exc: BaseException):
    cfg = _config(tmp_path)
    with mock.patch("decoy_engine.run_pipeline", side_effect=exc):
        return runner.invoke(app, ["run", str(cfg), "--json"])


def _capacity_members() -> list[str]:
    from decoy_engine.errors import CAPACITY_REASON_CODES

    return sorted(CAPACITY_REASON_CODES)


@pytest.mark.parametrize("code", _capacity_members())
def test_each_capacity_code_exits_5(tmp_path: Path, code: str) -> None:
    from decoy_engine.execution import ExecutionError

    result = _run(tmp_path, ExecutionError(code=code, message="over the memory budget."))
    assert result.exit_code == EXIT_CAPACITY
    payload = json.loads(result.output)
    assert payload["error_kind"] == "capacity"
    assert payload["code"] == code


def test_memory_error_exits_5(tmp_path: Path) -> None:
    result = _run(tmp_path, MemoryError())
    assert result.exit_code == EXIT_CAPACITY
    assert json.loads(result.output)["error_kind"] == "capacity"


@pytest.mark.parametrize(
    "code",
    [
        "storage_capacity_exhausted",
        "out_of_core_budget_invalid",
        "subset_budget_exceeded",
        "dp_budget_exceeded",
        "pool_capacity_pre_flight_unique",
        "fk_full_frame_oom_risk_rejected",
    ],
)
def test_excluded_codes_keep_their_exit(tmp_path: Path, code: str) -> None:
    from decoy_engine.errors import CAPACITY_EXCLUSIONS, CAPACITY_REASON_CODES
    from decoy_engine.execution import ExecutionError

    assert code in CAPACITY_EXCLUSIONS
    assert code not in CAPACITY_REASON_CODES
    result = _run(tmp_path, ExecutionError(code=code, message="a refusal that is not capacity."))
    assert result.exit_code == EXIT_RUNTIME
    assert json.loads(result.output).get("error_kind") != "capacity"
