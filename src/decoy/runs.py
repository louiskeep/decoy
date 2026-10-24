"""Local run records: what `decoy status` reads and what `decoy run` writes.

Pattern: pueue / task-spooler (one directory per run holding a status snapshot,
an append-only event file and a log), with systemd-style liveness (pid plus a
heartbeat file's mtime). Records live under `$DECOY_HOME/runs/<run-id>/`
(default `~/.decoy/runs`), never inside the project directory, so a CLI run
leaves nothing beside the user's data. A record holds metadata only: run id,
config path, mode, pid, timestamps, state, phase, row counts and rates, exit
code and an exception class name. Never cell values, secrets, config contents
or exception text.

`RunRecordSink` is the engine `ProgressSink` that keeps the snapshot current
and appends every event as one JSON line; `JsonlStreamSink` mirrors the same
lines to a stream for CI (`decoy run --progress jsonl`). Both are value-free by
construction because the engine's events are.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

HEARTBEAT_INTERVAL_S = 5.0
STALE_AFTER_S = 3 * HEARTBEAT_INTERVAL_S
DEFAULT_KEEP = 50
TERMINAL_STATES = frozenset({"ok", "error", "interrupted"})


def runs_root() -> Path:
    """`$DECOY_HOME/runs`, default `~/.decoy/runs`."""
    home = os.environ.get("DECOY_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".decoy"
    return base / "runs"


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{os.urandom(3).hex()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class RunStatus:
    """The `status.json` snapshot, one per run."""

    run_id: str
    config: str
    mode: str
    pid: int
    started_at: str
    updated_at: str
    state: str = "running"
    phase: str | None = None
    table: str | None = None
    rows_done: int = 0
    rows_per_sec: float | None = None
    route: str | None = None
    lane: str | None = None
    exit_code: int | None = None
    error_class: str | None = None
    finished_at: str | None = None
    tables_done: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunStatus:
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**kwargs, extra=extra)


class RunRecord:
    """One run's directory: `status.json`, `events.jsonl`, `heartbeat`, `run.log`."""

    def __init__(self, directory: Path, status: RunStatus) -> None:
        self.dir = directory
        self.status = status
        self._lock = threading.Lock()
        self._events = self.dir / "events.jsonl"
        self._heartbeat = self.dir / "heartbeat"

    # -- lifecycle -----------------------------------------------------------
    @classmethod
    def create(
        cls,
        *,
        config: str,
        mode: str,
        run_id: str | None = None,
        root: Path | None = None,
        pid: int | None = None,
    ) -> RunRecord:
        root = root or runs_root()
        run_id = run_id or new_run_id()
        directory = root / run_id
        directory.mkdir(parents=True, exist_ok=False)
        now = _utc_now()
        status = RunStatus(
            run_id=run_id,
            config=config,
            mode=mode,
            pid=pid or os.getpid(),
            started_at=now,
            updated_at=now,
        )
        rec = cls(directory, status)
        rec.save()
        rec.touch()
        return rec

    @classmethod
    def load(cls, directory: Path) -> RunRecord | None:
        try:
            data = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return cls(directory, RunStatus.from_dict(data))
        except TypeError:
            return None

    def save(self) -> None:
        with self._lock:
            self.status.updated_at = _utc_now()
            _write_atomic(self.dir / "status.json", json.dumps(self.status.to_dict(), sort_keys=True))

    def touch(self) -> None:
        try:
            self._heartbeat.touch()
        except OSError:
            pass

    def append_event(self, event: dict[str, Any]) -> None:
        with self._lock, self._events.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    def log(self, line: str) -> None:
        with self._lock, (self.dir / "run.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{_utc_now()} {line}\n")

    def finish(self, state: str, *, exit_code: int | None, error_class: str | None = None) -> None:
        self.status.state = state
        self.status.exit_code = exit_code
        self.status.error_class = error_class
        self.status.finished_at = _utc_now()
        self.save()

    # -- liveness ------------------------------------------------------------
    def heartbeat_age_s(self) -> float | None:
        try:
            return max(0.0, time.time() - self._heartbeat.stat().st_mtime)
        except OSError:
            return None

    def is_stale(self, *, now: float | None = None) -> bool:
        """A `running` record whose process is gone or whose heartbeat expired."""
        if self.status.state in TERMINAL_STATES:
            return False
        if not _pid_alive(self.status.pid):
            return True
        age = self.heartbeat_age_s()
        return age is None or age > STALE_AFTER_S

    def effective_state(self) -> str:
        return "stale" if self.is_stale() else self.status.state

    def events(self) -> Iterable[dict[str, Any]]:
        try:
            with self._events.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
        except OSError:
            return


def list_runs(root: Path | None = None, *, limit: int | None = DEFAULT_KEEP) -> list[RunRecord]:
    """Recent runs, newest first (by run id, which starts with a UTC stamp)."""
    root = root or runs_root()
    if not root.is_dir():
        return []
    records: list[RunRecord] = []
    for d in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        rec = RunRecord.load(d)
        if rec is not None:
            records.append(rec)
        if limit is not None and len(records) >= limit:
            break
    return records


def find_run(run_id: str, root: Path | None = None) -> RunRecord | None:
    root = root or runs_root()
    d = root / run_id
    return RunRecord.load(d) if d.is_dir() else None


def prune(root: Path | None = None, *, keep: int = DEFAULT_KEEP) -> int:
    """Delete the oldest finished records beyond `keep`. Running records are kept."""
    import shutil

    root = root or runs_root()
    if not root.is_dir():
        return 0
    finished = [r for r in list_runs(root, limit=None) if r.status.state in TERMINAL_STATES or r.is_stale()]
    removed = 0
    for rec in finished[keep:]:
        shutil.rmtree(rec.dir, ignore_errors=True)
        removed += 1
    return removed


class Heartbeat:
    """Touches the heartbeat file every interval on a daemon thread, so a long
    silent engine phase never reads as stale."""

    def __init__(self, record: RunRecord, interval_s: float = HEARTBEAT_INTERVAL_S) -> None:
        self._record = record
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="decoy-heartbeat", daemon=True)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._record.touch()

    def __enter__(self) -> Heartbeat:
        self._record.touch()
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval)


# ---------------------------------------------------------------------------
# Progress sinks
# ---------------------------------------------------------------------------


def event_dict(event: Any) -> dict[str, Any]:
    """The engine event as a JSON-ready dict (value-free by the engine's contract)."""
    from decoy_engine.progress import event_to_dict

    return event_to_dict(event)


class RunRecordSink:
    """Engine `ProgressSink` that keeps `status.json` current and appends every
    event to `events.jsonl`."""

    def __init__(self, record: RunRecord) -> None:
        self._record = record

    def on_event(self, event: Any) -> None:
        d = event_dict(event)
        d["run_id"] = self._record.status.run_id
        self._record.append_event(d)
        st = self._record.status
        kind = d.get("kind")
        if kind == "phase":
            if d.get("status") == "start":
                st.phase = d.get("name")
                st.table = d.get("table")
            elif d.get("status") == "finish" and d.get("table") and d.get("name") in ("mask", "generate"):
                st.tables_done += 1
        elif kind == "rate":
            st.rows_done = int(d.get("rows_done") or 0)
            st.rows_per_sec = d.get("rows_per_sec")
            st.table = d.get("table")
        elif kind == "route":
            st.route = d.get("route")
            st.lane = d.get("lane")
        self._record.save()
        self._record.touch()


class JsonlStreamSink:
    """Engine `ProgressSink` that writes one JSON line per event to a stream
    (`--progress jsonl` to stderr, or `--progress-file`)."""

    def __init__(self, stream: TextIO, *, run_id: str | None = None, config: str | None = None) -> None:
        self._stream = stream
        self._run_id = run_id
        self._config = config

    def on_event(self, event: Any) -> None:
        d = event_dict(event)
        if self._run_id is not None:
            d["run_id"] = self._run_id
        if self._config is not None:
            d["config"] = self._config
        self._stream.write(json.dumps(d, sort_keys=True) + "\n")
        self._stream.flush()


class CallbackSink:
    def __init__(self, fn: Callable[[Any], None]) -> None:
        self._fn = fn

    def on_event(self, event: Any) -> None:
        self._fn(event)


class FanoutSink:
    """Deliver each event to every sink; one sink's failure never starves another."""

    def __init__(self, sinks: Iterable[Any]) -> None:
        self._sinks = [s for s in sinks if s is not None]

    def on_event(self, event: Any) -> None:
        for sink in self._sinks:
            try:
                sink.on_event(event)
            except Exception:
                continue


__all__ = [
    "DEFAULT_KEEP",
    "FanoutSink",
    "HEARTBEAT_INTERVAL_S",
    "Heartbeat",
    "JsonlStreamSink",
    "RunRecord",
    "RunRecordSink",
    "RunStatus",
    "STALE_AFTER_S",
    "find_run",
    "list_runs",
    "new_run_id",
    "prune",
    "runs_root",
]
