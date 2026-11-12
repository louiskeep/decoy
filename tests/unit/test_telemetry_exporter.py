"""F30 C1a: the CLI's OTLP exporter, provider and bounded flush (C-T1 cells).

Every cell drives the real exporter over loopback against `Listener`, a raw-socket
collector that records connections and raw request bytes and can redirect, black-hole,
stream a huge body or trickle one.
"""

from __future__ import annotations

import json
import select
import socket
import threading
import time
from pathlib import Path

import pytest
import urllib3.response

from decoy.telemetry import (
    OtelSettingsError,
    build_provider,
    flush_bounded,
    parse_otel_headers,
)

MIB = 1 << 20
HUGE = 512 * MIB
VECTORS = Path(__file__).resolve().parents[1] / "fixtures" / "f30" / "otel_header_vectors.json"


class Listener:
    """One-port collector. `behavior`: ok, black_hole, redirect_<code>, huge_<code>, trickle_<code>."""

    def __init__(self, behavior: str = "ok", *, location: str = "", extra: str = "") -> None:
        self.behavior, self.location, self.extra = behavior, location, extra
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}/v1/traces"
        self.connections = 0
        self.requests: list[bytes] = []
        self.accepted = threading.Event()
        self.handled = threading.Event()
        self.header_sent_at: float | None = None
        self.written = 0
        self.client_closed = False
        self._stop = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def close(self) -> None:
        self._stop.set()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.connections += 1
            self.accepted.set()
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
        self.sock.close()

    def _read_request(self, conn: socket.socket) -> None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                return
            data += chunk
        head = data.split(b"\r\n\r\n", 1)[0].lower()
        length = 0
        for line in head.split(b"\r\n"):
            if line.startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1])
        while len(data.split(b"\r\n\r\n", 1)[1]) < length:
            data += conn.recv(65536)
        self.requests.append(data)

    def _peer_closed(self, conn: socket.socket) -> bool:
        if select.select([conn], [], [], 0)[0]:
            try:
                return conn.recv(1, socket.MSG_PEEK) == b""
            except OSError:
                return True
        return False

    def _handle(self, conn: socket.socket) -> None:
        try:
            self._read_request(conn)
            kind, _, code = self.behavior.partition("_")
            if kind == "black":
                self._stop.wait()
                return
            if kind == "ok":
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            total = {"redirect": 5, "huge": HUGE, "trickle": 120}[kind]
            loc = f"Location: {self.location}\r\n" if self.location else ""
            conn.sendall(
                f"HTTP/1.1 {code} X\r\n{loc}{self.extra}Content-Length: {total}\r\n\r\n".encode()
            )
            self.header_sent_at = time.monotonic()
            if kind == "redirect":
                conn.sendall(b"moved")
            while self.written < total and kind != "redirect":
                if self._peer_closed(conn):
                    self.client_closed = True
                    return
                if kind == "trickle":
                    self.written += conn.send(b"x")
                    time.sleep(0.5)
                else:
                    self.written += conn.send(b"x" * MIB)
        except OSError:
            self.client_closed = True
        finally:
            self.handled.set()
            conn.close()


@pytest.fixture
def listeners():
    made: list[Listener] = []

    def make(*args, **kwargs) -> Listener:
        made.append(Listener(*args, **kwargs))
        return made[-1]

    yield make
    for lst in made:
        lst.close()


def _queue(tel):
    return tel.provider._active_span_processor._span_processors[0]._batch_processor._queue


def _one_span(tel, *, queued: bool = False):
    span = tel.provider.get_tracer("t").start_span(
        "decoy.run", record_exception=False, set_status_on_exception=False
    )
    span.end()
    if not queued:  # the cell exports it directly; the batch worker must not send it too
        _queue(tel).clear()
    return span


def _export_in_thread(tel, span, wait_s: float = 10.0):
    out: list = []
    t = threading.Thread(target=lambda: out.append(tel.exporter.export([span])), daemon=True)
    t.start()
    t.join(wait_s)
    return (out[0], time.monotonic()) if out else (None, time.monotonic())


def test_header_vectors() -> None:
    for vec in json.loads(VECTORS.read_text(encoding="utf-8")):
        if vec["ok"]:
            assert parse_otel_headers(vec["input"]) == vec["headers"], vec["id"]
        else:
            with pytest.raises(OtelSettingsError) as info:
                parse_otel_headers(vec["input"])
            assert "MARKER" not in str(info.value), vec["id"]
            assert "DECOY_OTEL_HEADERS" in str(info.value), vec["id"]


def test_headers_env(listeners, monkeypatch) -> None:
    a, b = listeners(), listeners()
    proxy = b.url.rsplit("/v1", 1)[0]
    for name, value in {
        "OTEL_EXPORTER_OTLP_HEADERS": "authorization=MARKER",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "x=MARKER",
        "OTEL_EXPORTER_OTLP_ENDPOINT": b.url,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": b.url,
        "HTTP_PROXY": proxy,
        "HTTPS_PROXY": proxy,
        "http_proxy": proxy,
        "REQUESTS_CA_BUNDLE": "/nonexistent/MARKER.pem",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    tel = build_provider(a.url, {"authorization": "Bearer configured"}, service_version="t")
    assert tel.exporter.export([_one_span(tel)]).name == "SUCCESS"
    assert a.connections == 1 and b.connections == 0
    raw = a.requests[0]
    assert b"MARKER" not in raw
    assert b"authorization: bearer configured" in raw.lower()
    assert b"x-decoy-telemetry: v1" in raw.lower()


@pytest.mark.parametrize("code", ["307", "308"])
def test_redirect(listeners, code) -> None:
    b = listeners()
    a = listeners(f"redirect_{code}", location=b.url)
    tel = build_provider(a.url, {}, service_version="t")
    assert tel.exporter.export([_one_span(tel)]).name == "FAILURE"
    time.sleep(0.3)
    assert a.connections == 1 and b.connections == 0


@pytest.mark.parametrize(
    "behavior,extra",
    [
        ("huge_307", ""),
        ("huge_308", ""),
        ("trickle_307", ""),
        ("trickle_308", ""),
        ("huge_503", "Retry-After: 1\r\n"),
    ],
    ids=[
        "redirect_huge_body-307",
        "redirect_huge_body-308",
        "redirect_trickle-307",
        "redirect_trickle-308",
        "retry_after_huge_body",
    ],
)
def test_redirect_body(listeners, monkeypatch, behavior, extra) -> None:
    returned: list[int] = []
    for meth in ("read", "stream"):
        orig = getattr(urllib3.response.HTTPResponse, meth)

        def wrapped(self, *args, _orig=orig, _meth=meth, **kwargs):
            out = _orig(self, *args, **kwargs)
            if _meth == "read":
                returned.append(len(out or b""))
                return out
            return (returned.append(len(c)) or c for c in out)

        monkeypatch.setattr(urllib3.response.HTTPResponse, meth, wrapped)
    b = listeners()
    a = listeners(behavior, location=b.url if "_30" in behavior else "", extra=extra)
    tel = build_provider(a.url, {}, service_version="t")
    result, done_at = _export_in_thread(tel, _one_span(tel))
    a.handled.wait(15)
    checks = {
        "a_no_connection_to_b": b.connections == 0,
        "b_one_connection_to_a": a.connections == 1,
        "c_failure": result is not None and result.name == "FAILURE",
        "c_within_2s_of_headers": a.header_sent_at is not None and done_at - a.header_sent_at < 2.0,
        "d_closed_with_body_unsent": a.handled.is_set()
        and a.client_closed
        and a.written < 16 * MIB,
        "e_no_body_returned": sum(returned) == 0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    assert not failed, f"failed checks: {failed}"


def test_resource(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "k=MARKER")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "MARKER")
    tel = build_provider("http://127.0.0.1:9/v1/traces", {}, service_version="9.9")
    attrs = dict(tel.provider.resource.attributes)
    assert attrs == {"service.name": "decoy-cli", "service.version": "9.9"}


def test_flush_black_hole_is_bounded(listeners) -> None:
    hole = listeners("black_hole")
    tel = build_provider(hole.url, {}, service_version="t")
    tracer = tel.provider.get_tracer("t")
    for _ in range(512):  # one full batch wakes the worker at once
        tracer.start_span("decoy.run", record_exception=False, set_status_on_exception=False).end()
    assert hole.accepted.wait(5), "export worker never reached the collector"
    tracer.start_span("decoy.run", record_exception=False, set_status_on_exception=False).end()
    assert len(_queue(tel)) >= 1
    started = time.monotonic()
    flush_bounded(tel)
    assert time.monotonic() - started < 2.5


def test_flush_huge_body_200_is_not_read(listeners) -> None:
    big = listeners("huge_200")
    tel = build_provider(big.url, {}, service_version="t")
    _one_span(tel, queued=True)
    flush_bounded(tel)
    assert big.handled.wait(15)
    assert big.connections == 1 and big.written < 16 * MIB


def test_tracer_meter_is_noop_under_hostile_meter_env(monkeypatch) -> None:
    from opentelemetry import metrics as metrics_api
    from opentelemetry.metrics import NoOpMeterProvider
    from opentelemetry.metrics._internal.instrument import NoOpCounter, NoOpUpDownCounter

    # Reset the process-global lazy meter provider so the env var is consulted again.
    monkeypatch.setattr(metrics_api._internal, "_METER_PROVIDER", None)
    monkeypatch.setenv("OTEL_PYTHON_METER_PROVIDER", "sdk_meter_provider")
    monkeypatch.setenv("OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED", "true")
    # Non-vacuity: with these variables the global provider is the SDK one, so a
    # provider that fell back to it would get real instruments.
    assert not isinstance(metrics_api.get_meter_provider(), NoOpMeterProvider)
    monkeypatch.setattr(metrics_api._internal, "_METER_PROVIDER", None)
    tel = build_provider("http://127.0.0.1:9/v1/traces", {}, service_version="t")
    metrics = tel.provider.get_tracer("t")._tracer_metrics
    assert isinstance(metrics._started_spans, NoOpCounter)
    assert isinstance(metrics._live_spans, NoOpUpDownCounter)


def _root_attrs(**over):
    base = {"decoy.spans_dropped": 0, "decoy.outcome": "success"}
    base.update(over)
    return list(base.items())


def test_root_record_accepts_registered_vocabulary() -> None:
    from decoy.telemetry import _root_record

    record = _root_record(1, 2, True, _root_attrs())
    assert record.name == "decoy.run"
    assert dict(record.attributes) == {"decoy.spans_dropped": 0, "decoy.outcome": "success"}


@pytest.mark.parametrize(
    "attributes",
    [
        [("decoy.table", "x")],
        [("decoy.outcome", "done")],
        [("error.type", "not a class name")],
    ],
    ids=["unregistered_key", "unregistered_outcome", "unregistered_error_type"],
)
def test_root_record_refuses_unregistered_attributes(attributes) -> None:
    from decoy.telemetry import _root_record

    with pytest.raises(ValueError):
        _root_record(1, 2, True, attributes)


def test_root_name_is_checked_against_span_names(monkeypatch) -> None:
    from decoy_engine.telemetry import _vocab

    from decoy.telemetry import _root_record

    monkeypatch.setattr(_vocab, "SPAN_NAMES", frozenset({"decoy.job"}))
    with pytest.raises(ValueError):
        _root_record(1, 2, True, _root_attrs())


@pytest.mark.parametrize("ok", [True, False])
def test_root_span_on_the_wire(ok) -> None:
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    from decoy.telemetry import RunTrace

    tel = build_provider("http://127.0.0.1:9/v1/traces", {})
    memory = InMemorySpanExporter()
    tel.provider.add_span_processor(SimpleSpanProcessor(memory))
    trace = RunTrace(tel)
    trace.finish(ok=ok, error_class=None if ok else "ValueError")
    (root,) = memory.get_finished_spans()
    assert root.name == "decoy.run"
    assert root.status.status_code is (StatusCode.OK if ok else StatusCode.ERROR)
    assert root.status.description is None and not root.events
    expected = {"decoy.spans_dropped", "decoy.outcome", "decoy.engine.version"}
    assert set(root.attributes) == expected | (set() if ok else {"error.type"})
    assert root.attributes["decoy.outcome"] == ("success" if ok else "failed")
    if not ok:
        assert root.attributes["error.type"] == "ValueError"
    assert root.end_time >= root.start_time
    tel.exporter.shutdown()


def test_resource_keys_are_checked_against_the_vocabulary(monkeypatch) -> None:
    import decoy_engine.telemetry as engine_telemetry

    from decoy.telemetry import _resource_attributes

    assert set(_resource_attributes("1.0")) == {"service.name", "service.version"}
    monkeypatch.setattr(engine_telemetry, "RESOURCE_KEYS", frozenset({"service.name"}))
    with pytest.raises(ValueError):
        build_provider("http://127.0.0.1:9/v1/traces", {}, service_version="t")
