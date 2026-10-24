"""`decoy run` progress stream, local run records and `decoy status` (parity C4a/b)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy import runs as R
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()
_SECRET = "ZQXJV-SECRET-VALUE"


def _config(tmp_path: Path, rows: int = 3) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": [f"{_SECRET}-{i}@x.com" for i in range(rows)]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 1},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "t", "columns": [{"name": "email", "strategy": "hash", "namespace": "e"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def _records_root() -> Path:
    return Path(os.environ["DECOY_HOME"]) / "runs"


def test_run_writes_a_record_and_the_envelope_names_it(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--json", "--run-id", "r-one"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["run_id"] == "r-one"
    rec = R.find_run("r-one", _records_root())
    assert rec is not None
    assert rec.status.state == "ok" and rec.status.exit_code == 0
    assert rec.status.route is not None
    kinds = [e["kind"] for e in rec.events()]
    assert kinds[0] == "phase" and kinds[-1] == "terminal"
    blob = (rec.dir / "status.json").read_text() + (rec.dir / "events.jsonl").read_text()
    assert _SECRET not in blob


def test_progress_jsonl_streams_events_on_stderr_alongside_json(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--json", "--progress", "jsonl", "--run-id", "r-two"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)  # stdout is still exactly one object
    assert payload["status"] == "ok"
    lines = [json.loads(l) for l in result.stderr.splitlines() if l.startswith("{")]
    assert lines, result.stderr
    assert {l["kind"] for l in lines} >= {"phase", "route", "terminal"}
    assert all(l["run_id"] == "r-two" and l["config"].endswith("pipeline.yaml") for l in lines)
    assert _SECRET not in result.stderr


def test_progress_file_appends_the_same_events(tmp_path: Path) -> None:
    out = tmp_path / "progress.jsonl"
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--progress-file", str(out), "--progress", "none"])
    assert result.exit_code == 0, result.output
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    assert lines[-1]["kind"] == "terminal" and lines[-1]["status"] == "ok"


def test_no_record_writes_nothing(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--no-record", "--json"])
    assert result.exit_code == 0, result.output
    assert "run_id" not in json.loads(result.stdout)
    assert not _records_root().exists() or not any(_records_root().iterdir())


def test_invalid_progress_value_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--progress", "xml"])
    assert result.exit_code == EXIT_USAGE


def test_duplicate_run_id_is_a_usage_error(tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", str(_config(tmp_path)), "--run-id", "dup"]).exit_code == 0
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--run-id", "dup"])
    assert result.exit_code == EXIT_USAGE
    assert "already exists" in result.output


def test_failed_run_records_error_class_and_exit_code(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    raw = yaml.safe_load(cfg.read_text())
    raw["sources"]["t"]["path"] = str(tmp_path / "missing.csv")
    cfg.write_text(yaml.safe_dump(raw))
    result = runner.invoke(app, ["run", str(cfg), "--run-id", "r-bad"])
    assert result.exit_code != 0
    rec = R.find_run("r-bad", _records_root())
    assert rec.status.state == "error"
    assert rec.status.exit_code == result.exit_code
    assert rec.status.error_class and "Error" in rec.status.error_class


def test_status_lists_and_details_runs(tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", str(_config(tmp_path)), "--run-id", "r-a"]).exit_code == 0
    assert runner.invoke(app, ["run", str(_config(tmp_path)), "--run-id", "r-b"]).exit_code == 0
    listed = runner.invoke(app, ["status", "--json"])
    assert listed.exit_code == 0, listed.output
    runs = json.loads(listed.stdout)["runs"]
    assert [r["run_id"] for r in runs] == ["r-b", "r-a"]
    assert all(r["state"] == "ok" for r in runs)
    detail = runner.invoke(app, ["status", "r-a", "--json"])
    assert json.loads(detail.stdout)["runs"][0]["record_dir"].endswith("r-a")
    human = runner.invoke(app, ["status"])
    assert human.exit_code == 0 and "r-a" in human.stdout and "ok" in human.stdout
    missing = runner.invoke(app, ["status", "nope"])
    assert missing.exit_code == EXIT_USAGE


def test_status_reports_a_dead_process_as_stale(tmp_path: Path) -> None:
    rec = R.RunRecord.create(config="p.yaml", mode="mask", root=_records_root(), run_id="ghost", pid=2**22 + 777)
    result = runner.invoke(app, ["status", "--json", "--active"])
    runs = json.loads(result.stdout)["runs"]
    assert runs and runs[0]["run_id"] == "ghost" and runs[0]["state"] == "stale"
    assert rec.effective_state() == "stale"


def test_chunked_run_records_rows(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path, rows=10)), "--chunked", "--chunk-size", "4", "--run-id", "r-chunk"])
    assert result.exit_code == 0, result.output
    rec = R.find_run("r-chunk", _records_root())
    rates = [e for e in rec.events() if e["kind"] == "rate"]
    assert rates and rates[-1]["rows_done"] == 10 and rates[-1]["final"] is True
