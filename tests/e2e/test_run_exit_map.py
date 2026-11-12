"""`decoy run` reads every exit integer from `RUN_EXIT_MAP`; the integers match the old ones."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import exit_codes
from tests.csv_sources import csv_source

runner = CliRunner()


def _config(tmp_path: Path, *, leaky: bool = False) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"code": ["AAAAA", "AAA", "BBBBB"]}).to_csv(src, index=False)
    column = (
        {
            "name": "code",
            "strategy": "truncate",
            "provider": "person_email",
            "namespace": "ns",
            "provider_config": {"length": 3},
        }
        if leaky
        else {"name": "code", "strategy": "redact"}
    )
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {"t": csv_source(src)},
        "tables": [{"name": "t", "columns": [column]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _sub(root: Path, name: str) -> Path:
    (root / name).mkdir()
    return root / name


def _engine_raises(exc: BaseException):
    return mock.patch("decoy_engine.run_pipeline", side_effect=exc)


def _gate_refusal(exit_code: int, kind: str):
    from decoy.cli.gate import PreRunCheckError

    return PreRunCheckError(
        "refused", exit_code=exit_code, error_kind=kind, code=None, extra=None, messages=[]
    )


def _cases(tmp_path: Path):
    from decoy_engine import ConfigError
    from decoy_engine.execution import ExecutionError

    return [
        ("config", ConfigError("bad"), 1, ("failed", "usage")),
        ("runtime", RuntimeError("boom"), 3, ("failed", "runtime")),
        (
            "capacity",
            ExecutionError(code="out_of_core_fanin_exceeds_budget", message="m"),
            5,
            ("failed", "capacity"),
        ),
        ("gate", _gate_refusal(1, "validation"), 1, ("failed", "usage")),
        ("gate_capacity", _gate_refusal(5, "capacity"), 5, ("failed", "capacity")),
    ]


@pytest.mark.parametrize("index", range(5))
def test_exits_read_the_map(tmp_path: Path, index: int) -> None:
    _, exc, expected, key = _cases(tmp_path)[index]
    cfg = _config(tmp_path)
    with _engine_raises(exc):
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == expected
    # The same case follows the map, so no second table can hold the integer.
    with mock.patch.dict(exit_codes.RUN_EXIT_MAP, {key: 9}), _engine_raises(exc):
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == 9


def test_findings_and_success_read_the_map(tmp_path: Path) -> None:
    leaky = _config(_sub(tmp_path, "a"), leaky=True)
    assert runner.invoke(app, ["run", str(leaky), "--post-validate-enforce"]).exit_code == 4
    with mock.patch.dict(exit_codes.RUN_EXIT_MAP, {("findings", None): 9}):
        assert runner.invoke(app, ["run", str(leaky), "--post-validate-enforce"]).exit_code == 9
    clean = _config(_sub(tmp_path, "b"))
    assert runner.invoke(app, ["run", str(clean)]).exit_code == 0


def test_explain_lists_exit_6() -> None:
    out = runner.invoke(app, ["explain", "exit-codes"]).output
    assert "six exit codes" not in out
    assert "  6   Partially delivered" in out
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    assert "| 6    | `EXIT_PARTIAL`" in readme
