"""F30 C1: `decoy run --otel-endpoint` settings, the `[otel]` extra, env isolation and spans.

C-T1 `env`, C-T2 to C-T7 through `typer.testing.CliRunner`; the exporter cells live in
tests/unit/test_telemetry_exporter.py, whose `Listener` these reuse.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app
from tests.csv_sources import csv_source

runner = CliRunner()
LOOPBACK = "http://127.0.0.1:4318/v1/traces"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("DECOY_OTEL_ENDPOINT", "DECOY_OTEL_HEADERS"):
        monkeypatch.delenv(name, raising=False)


def _make_listener():
    # Lazy: the shared collector's module imports decoy.telemetry.
    from tests.unit.test_telemetry_exporter import Listener

    return Listener()


@pytest.fixture
def listener():
    lst = _make_listener()
    yield lst
    lst.close()


def _pipeline(tmp_path: Path) -> Path:
    src = tmp_path / "accounts.csv"
    src.write_text("name\nalice\nbob\n", encoding="utf-8")
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"accounts": csv_source(src)},
        "tables": [{"name": "accounts", "columns": [{"name": "name", "strategy": "redact"}]}],
        "targets": {
            "accounts": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _drop_otel_modules(monkeypatch) -> None:
    for name in list(sys.modules):
        if name.split(".")[0] == "opentelemetry" or name == "decoy.telemetry":
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.delattr(decoy, "telemetry", raising=False)


def _hide_otel(monkeypatch) -> None:
    _drop_otel_modules(monkeypatch)
    monkeypatch.setitem(sys.modules, "opentelemetry", None)


def _run(cfg: Path, *args: str):
    return runner.invoke(app, ["run", str(cfg), *args])


def _envelope(result) -> dict:
    payload = json.loads(result.stdout)
    payload.pop("elapsed_s", None)
    return payload


def test_env(tmp_path, monkeypatch, listener) -> None:
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        monkeypatch.setenv(name, listener.url)
    _drop_otel_modules(monkeypatch)
    result = _run(_pipeline(tmp_path), "--json")
    assert result.exit_code == 0, result.output
    time.sleep(0.3)
    assert listener.connections == 0
    assert not [m for m in sys.modules if m.split(".")[0] == "opentelemetry"]
    # Non-vacuity: the same listener is reachable when the provider is driven directly.
    from decoy.telemetry import build_provider, flush_bounded

    tel = build_provider(listener.url, {}, service_version="t")
    tel.provider.get_tracer("t").start_span(
        "decoy.run", record_exception=False, set_status_on_exception=False
    ).end()
    flush_bounded(tel)
    assert listener.connections == 1


REFUSED = {
    "http_remote_with_headers": ("http://MARKER.example:4318/v1/traces", "authorization=MARKER"),
    "query": (LOOPBACK + "?token=MARKER", None),
    "userinfo": ("http://u:MARKER@127.0.0.1:4318/v1/traces", None),
    "malformed_header": (LOOPBACK, "MARKER"),
}
ACCEPTED = {
    "http_loopback_with_headers": (
        [LOOPBACK, "http://localhost:4318/v1/traces", "http://[::1]:4318/v1/traces"],
        "authorization=MARKER",
    ),
    "http_remote_no_headers": (["http://collector.example:4318/v1/traces"], None),
}


@pytest.mark.parametrize("cell", ["missing_extra", "env_only", *REFUSED, *ACCEPTED])
def test_otel_settings_refusals(tmp_path, monkeypatch, cell) -> None:
    cfg = _pipeline(tmp_path)
    off = _run(cfg, "--json")
    assert off.exit_code == 0, off.output
    if cell == "missing_extra":
        _hide_otel(monkeypatch)
        result = _run(cfg, "--json", "--otel-endpoint", LOOPBACK)
        assert result.exit_code == 1, result.output
        payload = json.loads(result.stdout)
        assert payload["error_kind"] == "missing_extra" and payload["extra"] == "otel"
    elif cell == "env_only":
        _hide_otel(monkeypatch)
        monkeypatch.setenv("DECOY_OTEL_ENDPOINT", "http://MARKER.example:4318/v1/traces")
        result = _run(cfg, "--json")
        assert result.exit_code == off.exit_code
        assert _envelope(result) == _envelope(off)
        warnings = [line for line in result.stderr.splitlines() if line.strip()]
        assert len(warnings) == 1 and "otel" in warnings[0] and "MARKER" not in result.stderr
    elif cell in REFUSED:
        endpoint, headers = REFUSED[cell]
        if headers is not None:
            monkeypatch.setenv("DECOY_OTEL_HEADERS", headers)
        for extra_args in ([], ["--json"]):
            result = _run(cfg, *extra_args, "--otel-endpoint", endpoint)
            assert result.exit_code == 1, result.output
            assert "MARKER" not in result.stdout + result.stderr
            assert "otel" in (result.stdout + result.stderr).lower()
            if extra_args:
                assert json.loads(result.stdout)["status"] == "error"
    else:
        endpoints, headers = ACCEPTED[cell]
        if headers is not None:
            monkeypatch.setenv("DECOY_OTEL_HEADERS", headers)
        for endpoint in endpoints:
            result = _run(cfg, "--json", "--otel-endpoint", endpoint)
            assert result.exit_code == 0, result.output
            assert _envelope(result) == _envelope(off)
            assert "MARKER" not in result.stdout + result.stderr


def test_headers_come_only_from_env(tmp_path, monkeypatch, listener) -> None:
    help_text = runner.invoke(app, ["run", "--help"]).stdout
    assert "--otel-endpoint" in help_text and "--otel-headers" not in help_text
    # Rich reads a bare `[otel]` as markup and drops it; the install hint must survive.
    assert "decoy-cli[otel]" in " ".join(help_text.split())
    cfg = _pipeline(tmp_path)
    usage = _run(cfg, "--otel-endpoint", LOOPBACK, "--otel-headers", "a=b")
    assert usage.exit_code == 2 and "No such option" in usage.output
    # Provider level: the env header reaches the configured listener and nowhere else.
    other = _make_listener()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", other.url)
    from decoy.telemetry import configure, flush_bounded

    tel = configure(listener.url, "authorization=MARKER", endpoint_setting="--otel-endpoint")
    tel.provider.get_tracer("t").start_span(
        "decoy.run", record_exception=False, set_status_on_exception=False
    ).end()
    flush_bounded(tel)
    other.close()
    assert listener.connections == 1 and other.connections == 0
    assert b"authorization: MARKER" in listener.requests[0]
    # CLI level: the value appears in no output, accepted or refused.
    for headers in ("authorization=MARKER", "MARKER"):
        monkeypatch.setenv("DECOY_OTEL_HEADERS", headers)
        for extra_args in ([], ["--json"], ["--verbose"]):
            result = _run(cfg, *extra_args, "--otel-endpoint", listener.url)
            assert "MARKER" not in result.stdout + result.stderr


def test_empty_flag_is_refused_not_unset(tmp_path, monkeypatch, listener) -> None:
    cfg = _pipeline(tmp_path)
    monkeypatch.setenv("DECOY_OTEL_ENDPOINT", listener.url)
    for extra_args in ([], ["--json"]):
        for empty in ("", "  "):
            result = _run(cfg, *extra_args, "--otel-endpoint", empty)
            assert result.exit_code == 1, result.output
            text = result.stdout + result.stderr
            assert "--otel-endpoint" in text and listener.url not in text
            if extra_args:
                assert json.loads(result.stdout)["status"] == "error"
    time.sleep(0.3)
    assert listener.connections == 0  # no fall-through to DECOY_OTEL_ENDPOINT


def test_missing_extra_message_names_the_flag(tmp_path, monkeypatch) -> None:
    _hide_otel(monkeypatch)
    result = _run(_pipeline(tmp_path), "--json", "--otel-endpoint", LOOPBACK)
    assert result.exit_code == 1, result.output
    message = json.loads(result.stdout)["error"]
    assert "pip install decoy-cli[otel]" in message
    assert "--otel-endpoint" in message and "this pipeline" not in message


# ---- C1b: spans, leak corpus, dead collector, DP limit ----------------------------------

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guides" / "telemetry.md"


def _spans(listener) -> list:
    """Every span the listener received, decoded from the OTLP protobuf bodies."""
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    found = []
    for raw in listener.requests:
        msg = ExportTraceServiceRequest()
        msg.ParseFromString(raw.split(b"\r\n\r\n", 1)[1])
        for resource in msg.resource_spans:
            for scope in resource.scope_spans:
                found.extend(scope.spans)
    return found


def _wait_for_spans(listener, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not listener.requests and time.monotonic() < deadline:
        time.sleep(0.05)


@pytest.mark.parametrize("route", ["full_frame", "chunked"])
def test_flag_exports_one_trace_with_phase_spans(tmp_path, listener, route) -> None:
    args = ["--chunked"] if route == "chunked" else []
    result = _run(_pipeline(tmp_path), "--json", "--otel-endpoint", listener.url, *args)
    assert result.exit_code == 0, result.output
    _wait_for_spans(listener)
    spans = _spans(listener)
    roots = [s for s in spans if s.name == "decoy.run"]
    phases = [s for s in spans if s.name.startswith("decoy.phase.")]
    assert len(roots) == 1 and not roots[0].parent_span_id
    assert phases, "no phase span reached the collector"
    assert {s.trace_id for s in spans} == {roots[0].trace_id}
    assert {s.parent_span_id for s in phases} == {roots[0].span_id}
    assert roots[0].status.code == 1  # OK


MARKER = "MARKERf30c1b"


def _marker_pipeline(tmp_path: Path) -> Path:
    base = tmp_path / MARKER
    base.mkdir()
    src = base / f"{MARKER}_accounts.csv"
    src.write_text(f"{MARKER}_col\n{MARKER}_cell1\n{MARKER}_cell2\n", encoding="utf-8")
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {f"{MARKER}_table": csv_source(src)},
        "tables": [
            {
                "name": f"{MARKER}_table",
                "columns": [{"name": f"{MARKER}_col", "strategy": "redact"}],
            }
        ],
        "targets": {
            f"{MARKER}_table": {
                "type": "file",
                "format": "csv",
                "path": str(base / f"{MARKER}_out.csv"),
            }
        },
    }
    path = base / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _boom(exc: Exception):
    """An engine entry that opens one phase, then fails with `exc` (text carries the marker)."""

    def run_pipeline(*_args, **_kwargs):
        from decoy_engine.progress import get_active_channel

        with get_active_channel().phase("resolve"):
            raise exc

    return run_pipeline


@pytest.mark.parametrize("cell", ["success", "engine_error", "os_error"])
def test_marker_corpus_absent_from_wire(tmp_path, monkeypatch, listener, cell) -> None:
    import decoy_engine
    from decoy_engine.execution import ExecutionError

    cfg = _marker_pipeline(tmp_path)
    if cell == "engine_error":
        monkeypatch.setattr(
            decoy_engine, "run_pipeline", _boom(ExecutionError(code="boom", message=MARKER))
        )
    elif cell == "os_error":
        monkeypatch.setattr(decoy_engine, "run_pipeline", _boom(OSError(MARKER)))
    args = [
        "--json",
        "--otel-endpoint",
        listener.url,
        "--key-label",
        f"postgresql://{MARKER}:{MARKER}@{MARKER}.example/{MARKER}",
        "--evidence-out",
        str(cfg.parent / f"{MARKER}_evidence.json"),
    ]
    result = _run(cfg, *args)
    if cell == "success":
        assert result.exit_code == 0, result.output
    else:
        assert result.exit_code != 0
        # Non-vacuity: the failure text did carry the marker locally.
        assert MARKER in result.stdout
    _wait_for_spans(listener)
    assert listener.requests, "nothing was exported"
    wire = b"".join(listener.requests)
    assert MARKER.encode() not in wire
    spans = _spans(listener)
    root = next(s for s in spans if s.name == "decoy.run")
    if cell == "success":
        return
    assert root.status.code == 2  # ERROR
    assert root.status.message == ""
    assert len(root.events) == 0
    for span in spans:
        assert span.status.message == "" and len(span.events) == 0


def _quiet_run(cfg: Path, *args: str):
    started = time.monotonic()
    result = _run(cfg, "--json", *args)
    return result, time.monotonic() - started


@pytest.mark.parametrize(
    "behavior",
    ["black_hole", "huge_200", "trickle_200"],
    ids=["black_hole", "huge_body", "trickle"],
)
def test_dead_collector_keeps_exit_code_and_bounds_exit(tmp_path, behavior) -> None:
    from tests.unit.test_telemetry_exporter import Listener

    cfg = _pipeline(tmp_path)
    off, off_wall = _quiet_run(cfg)
    assert off.exit_code == 0, off.output
    lst = Listener(behavior)
    try:
        on, on_wall = _quiet_run(cfg, "--otel-endpoint", lst.url)
        # Non-vacuity: the export worker reached the dead collector with a span queued.
        assert lst.accepted.is_set() and lst.connections >= 1
    finally:
        lst.close()
    assert on.exit_code == off.exit_code
    assert _envelope(on) == _envelope(off)
    assert on.stderr == off.stderr
    assert on_wall - off_wall <= 2.0 + 0.5


def test_otel_extra_documents_dp_refusal() -> None:
    import importlib.metadata as md

    from decoy_engine.quality import dp_provenance

    text = GUIDE.read_text(encoding="utf-8")
    assert "dp_stack_uncertified" in text and "decoy-cli[otel]" in text
    # Non-vacuity: this environment has the extra installed.
    assert md.version("opentelemetry-sdk")
    if dp_provenance.current_platform() != dp_provenance.CERTIFIED_PLATFORM:
        pytest.skip("the stack check runs only on the certified platform (Linux x86-64)")
    with pytest.raises(dp_provenance.ProvenanceError) as caught:
        dp_provenance.check_fit_environment()
    assert caught.value.code == "dp_stack_uncertified"


def test_open_phase_is_closed_on_exit(tmp_path, monkeypatch, listener) -> None:
    """A route that never finishes a phase still exports it, ended as a failed span."""
    import decoy_engine

    def run_pipeline(*_args, **_kwargs):
        from decoy_engine.progress import get_active_channel

        get_active_channel().phase_start("resolve")
        raise OSError(MARKER)

    monkeypatch.setattr(decoy_engine, "run_pipeline", run_pipeline)
    result = _run(_pipeline(tmp_path), "--json", "--otel-endpoint", listener.url)
    assert result.exit_code != 0
    _wait_for_spans(listener)
    phases = [s for s in _spans(listener) if s.name == "decoy.phase.resolve"]
    assert len(phases) == 1 and phases[0].status.code == 2
    assert MARKER.encode() not in b"".join(listener.requests)


def test_sdk_failure_log_never_reaches_stderr(tmp_path, monkeypatch, listener) -> None:
    """An exporter that raises makes the SDK log a traceback with the endpoint; the run's
    stderr must still equal the run without telemetry. `flush_bounded` also raises the
    logger's level; that is switched off here so the quiet handler is what is tested."""
    import logging

    from decoy.telemetry import _DecoySpanExporter

    cfg = _pipeline(tmp_path)
    off = _run(cfg, "--json")

    def raising(self, spans):
        raise RuntimeError(f"export failed for {MARKER}")

    monkeypatch.setattr(_DecoySpanExporter, "export", raising)
    # Under pytest the root logger holds capture handlers; a real CLI has none, so the
    # last-resort handler would print to stderr.
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    monkeypatch.setattr(logging.getLogger("opentelemetry"), "handlers", [])
    monkeypatch.setattr(logging.getLogger("opentelemetry"), "setLevel", lambda level: None)
    on = _run(cfg, "--json", "--otel-endpoint", listener.url)
    assert on.exit_code == off.exit_code == 0
    assert on.stderr == off.stderr and MARKER not in on.stderr + on.stdout
