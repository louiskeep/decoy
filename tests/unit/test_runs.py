"""Unit tests for `decoy.runs` (parity C4a): records, liveness, sinks, prune."""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

from decoy import runs as R
from decoy_engine.progress import PhaseEvent, RateSample, RouteEvent, TerminalEvent


def test_runs_root_honours_decoy_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    assert R.runs_root() == tmp_path / "home" / "runs"


def test_create_save_load_round_trip(tmp_path: Path) -> None:
    rec = R.RunRecord.create(config="pipeline.yaml", mode="mask", root=tmp_path, run_id="r1")
    assert (tmp_path / "r1" / "status.json").exists()
    assert (tmp_path / "r1" / "heartbeat").exists()
    loaded = R.RunRecord.load(tmp_path / "r1")
    assert loaded is not None
    assert loaded.status.run_id == "r1" and loaded.status.state == "running"
    assert loaded.status.pid == os.getpid()
    assert loaded.effective_state() == "running"


def test_finish_is_terminal_and_never_stale(tmp_path: Path) -> None:
    rec = R.RunRecord.create(config="p.yaml", mode="mask", root=tmp_path, run_id="r1")
    rec.finish("ok", exit_code=0)
    assert R.find_run("r1", tmp_path).effective_state() == "ok"
    assert not rec.is_stale()


def test_dead_pid_or_old_heartbeat_reads_as_stale(tmp_path: Path) -> None:
    rec = R.RunRecord.create(config="p.yaml", mode="mask", root=tmp_path, run_id="r1", pid=2**22 + 12345)
    assert rec.is_stale()
    rec2 = R.RunRecord.create(config="p.yaml", mode="mask", root=tmp_path, run_id="r2")
    old = time.time() - R.STALE_AFTER_S - 5
    os.utime(tmp_path / "r2" / "heartbeat", (old, old))
    assert rec2.is_stale()
    rec2.touch()
    assert not rec2.is_stale()


def test_record_sink_updates_snapshot_and_appends_events(tmp_path: Path) -> None:
    rec = R.RunRecord.create(config="p.yaml", mode="mask", root=tmp_path, run_id="r1")
    sink = R.RunRecordSink(rec)
    sink.on_event(RouteEvent("full_frame", lane="chunked"))
    sink.on_event(PhaseEvent("mask", "start", table="t", rows_in=10))
    sink.on_event(RateSample("t", 5, 50.0, 0.1))
    sink.on_event(PhaseEvent("mask", "finish", table="t", rows_out=10))
    sink.on_event(TerminalEvent("ok"))
    st = R.find_run("r1", tmp_path).status
    assert st.route == "full_frame" and st.lane == "chunked"
    assert st.phase == "mask" and st.table == "t" and st.rows_done == 5 and st.tables_done == 1
    events = list(rec.events())
    assert [e["kind"] for e in events] == ["route", "phase", "rate", "phase", "terminal"]
    assert all(e["run_id"] == "r1" for e in events)


def test_jsonl_stream_sink_writes_one_line_per_event() -> None:
    buf = io.StringIO()
    sink = R.JsonlStreamSink(buf, run_id="r9", config="p.yaml")
    sink.on_event(PhaseEvent("resolve", "start"))
    sink.on_event(TerminalEvent("ok"))
    lines = [json.loads(l) for l in buf.getvalue().splitlines()]
    assert [l["kind"] for l in lines] == ["phase", "terminal"]
    assert lines[0]["run_id"] == "r9" and lines[0]["config"] == "p.yaml"


def test_fanout_isolates_a_failing_sink() -> None:
    seen = []

    class Bad:
        def on_event(self, e):
            raise RuntimeError("x")

    R.FanoutSink([Bad(), R.CallbackSink(seen.append)]).on_event(TerminalEvent("ok"))
    assert len(seen) == 1


def test_list_runs_newest_first_and_prune_keeps_running(tmp_path: Path) -> None:
    for i in range(4):
        rec = R.RunRecord.create(config="p.yaml", mode="mask", root=tmp_path, run_id=f"2026010{i}T000000-aaaaaa")
        if i < 3:
            rec.finish("ok", exit_code=0)
    ids = [r.status.run_id for r in R.list_runs(tmp_path)]
    assert ids == sorted(ids, reverse=True)
    removed = R.prune(tmp_path, keep=1)
    assert removed == 2
    remaining = {r.status.run_id for r in R.list_runs(tmp_path)}
    assert "20260103T000000-aaaaaa" in remaining  # the running one survives
    assert len(remaining) == 2


def test_heartbeat_thread_touches_the_file(tmp_path: Path) -> None:
    rec = R.RunRecord.create(config="p.yaml", mode="mask", root=tmp_path, run_id="r1")
    old = time.time() - 100
    os.utime(tmp_path / "r1" / "heartbeat", (old, old))
    with R.Heartbeat(rec, interval_s=0.05):
        time.sleep(0.2)
    assert rec.heartbeat_age_s() < 5
