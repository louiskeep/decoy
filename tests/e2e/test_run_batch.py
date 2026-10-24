"""`decoy run a.yaml b.yaml --jobs N` and `decoy.run(...)` (parity C4c/C4d)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

import decoy
from decoy import runs as R
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _config(tmp_path: Path, name: str, *, target: str | None = None, missing_source: bool = False) -> Path:
    src = tmp_path / f"{name}.csv"
    if not missing_source:
        pd.DataFrame({"email": [f"{name}{i}@x.com" for i in range(5)]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 1},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "t", "columns": [{"name": "email", "strategy": "hash", "namespace": "e"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / (target or f"{name}_out.csv"))}},
    }
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def _root() -> Path:
    return Path(os.environ["DECOY_HOME"]) / "runs"


def test_batch_runs_every_config_with_its_own_record(tmp_path: Path) -> None:
    a, b = _config(tmp_path, "a"), _config(tmp_path, "b")
    result = runner.invoke(app, ["run", str(a), str(b), "--jobs", "2", "--json", "--run-id", "batch1"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok" and payload["batch_id"] == "batch1" and payload["jobs"] == 2
    assert [r["run_id"] for r in payload["runs"]] == ["batch1-1", "batch1-2"]
    assert all(r["exit_code"] == 0 and r["result"]["status"] == "ok" for r in payload["runs"])
    assert (tmp_path / "a_out.csv").exists() and (tmp_path / "b_out.csv").exists()
    assert R.find_run("batch1-1", _root()).status.state == "ok"
    assert R.find_run("batch1-2", _root()).status.state == "ok"


def test_batch_exit_code_is_the_worst_child(tmp_path: Path) -> None:
    good = _config(tmp_path, "good")
    bad = _config(tmp_path, "bad", missing_source=True)
    result = runner.invoke(app, ["run", str(good), str(bad), "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    codes = {r["config"]: r["exit_code"] for r in payload["runs"]}
    assert codes[str(good)] == 0 and codes[str(bad)] == result.exit_code
    assert (tmp_path / "good_out.csv").exists()


def test_batch_refuses_same_target(tmp_path: Path) -> None:
    a = _config(tmp_path, "a", target="shared.csv")
    b = _config(tmp_path, "b", target="shared.csv")
    result = runner.invoke(app, ["run", str(a), str(b)])
    assert result.exit_code == EXIT_USAGE
    assert "same target" in result.output


def test_batch_refuses_per_run_files(tmp_path: Path) -> None:
    a, b = _config(tmp_path, "a"), _config(tmp_path, "b")
    result = runner.invoke(app, ["run", str(a), str(b), "--evidence-out", str(tmp_path / "ev.json")])
    assert result.exit_code == EXIT_USAGE
    assert "evidence-out" in result.output


def test_batch_human_output_lists_each_run(tmp_path: Path) -> None:
    a, b = _config(tmp_path, "a"), _config(tmp_path, "b")
    result = runner.invoke(app, ["run", str(a), str(b), "--watch", "--run-id", "hb"])
    assert result.exit_code == 0, result.output
    assert "batch" in result.stdout.lower() and "hb-1" in result.stdout and "hb-2" in result.stdout


def test_library_run_returns_one_result_per_config_and_streams_events(tmp_path: Path) -> None:
    a, b = _config(tmp_path, "a"), _config(tmp_path, "b")
    bad = _config(tmp_path, "bad", missing_source=True)
    seen: list = []
    results = decoy.run([a, b, bad], jobs=2, on_progress=seen.append)
    assert [r.ok for r in results] == [True, True, False]
    assert isinstance(results[0].output, pd.DataFrame) and len(results[0].output) == 5
    assert results[2].error is not None
    configs_seen = {str(e.config) for e in seen}
    assert str(a) in configs_seen and str(b) in configs_seen
    assert any(e.kind == "terminal" for e in seen)


def test_mask_on_progress_receives_events(tmp_path: Path) -> None:
    a = _config(tmp_path, "a")
    kinds: list[str] = []
    decoy.mask(config=a, on_progress=lambda e: kinds.append(e.kind))
    assert "terminal" in kinds and "route" in kinds
