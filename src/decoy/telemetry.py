"""Opt-in OpenTelemetry trace export for `decoy run` (F30, `decoy-cli[otel]`).

The only CLI module that imports `opentelemetry`; `decoy run` imports it only when
`--otel-endpoint` or `DECOY_OTEL_ENDPOINT` asks for telemetry. Established pattern: the
OpenTelemetry "libraries use the API, applications own the SDK" split; the SDK
`TracerProvider`, `BatchSpanProcessor` and OTLP protobuf encoder (`encode_spans`) are
reused as-is (opentelemetry-python 1.45.2). Three SDK defaults are not followed, because
each lets the environment or the collector widen what leaves the process:

- `Resource.create` merges `OTEL_RESOURCE_ATTRIBUTES` and detectors; the resource here is
  the plain `Resource(attributes)` constructor with two closed keys.
- The stock OTLP/HTTP exporter merges `OTEL_EXPORTER_OTLP_*HEADERS` under explicit
  headers and reads endpoint, TLS and session settings from `OTEL_*`. `_DecoySpanExporter`
  POSTs the encoder's bytes itself and reads no environment.
- `requests.Session.send` runs `resolve_redirects`, which reads `resp.content` even with
  `allow_redirects=False`, and trusts proxy and CA-bundle variables. The exporter sends a
  prepared request through one `HTTPAdapter` (urllib3 `redirect=False`,
  `preload_content=False`, `Retry(0, read=False)`) and closes the response unread.

`force_flush` at 1.45.2 ignores its timeout and exports on the calling thread, so
`flush_bounded` runs it on a daemon thread and stops waiting after `FLUSH_BUDGET_MS`.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import StatusCode, set_span_in_context
from requests.adapters import HTTPAdapter

from decoy._version import __version__ as _cli_version

FLUSH_BUDGET_MS = 2000
HEADERS_SETTING = "DECOY_OTEL_HEADERS"
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")  # RFC 9110 field-name token
_PRINTABLE = re.compile(r"[\x20-\x7e]+")
_URL_CHARS = re.compile(r"[\x21-\x7e]+")


class OtelSettingsError(ValueError):
    """A refused telemetry setting. The message names the setting, never its value."""


def parse_otel_headers(raw: str | None) -> dict[str, str]:
    """`name=value,name=value` into a dict. Names are header tokens, values printable
    ASCII; no percent-decoding, no empty or duplicate entries."""
    if raw is None or not raw.strip():
        return {}
    headers: dict[str, str] = {}
    for index, entry in enumerate(raw.split(","), start=1):
        name, sep, value = entry.partition("=")
        name, value = name.strip(), value.strip()
        if not (sep and _TOKEN.fullmatch(name) and _PRINTABLE.fullmatch(value)):
            raise OtelSettingsError(f"{HEADERS_SETTING}: entry {index} is not a name=value pair")
        if name.lower() in (n.lower() for n in headers):
            raise OtelSettingsError(f"{HEADERS_SETTING}: entry {index} repeats a header name")
        headers[name] = value
    return headers


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.version == 4:
        return addr in ipaddress.ip_network("127.0.0.0/8")
    return addr == ipaddress.IPv6Address("::1")


def validate_endpoint(endpoint: str, *, has_headers: bool, setting: str) -> None:
    """Refuse a collector URL that is not plain `http(s)://host[:port]/path`, and credential
    headers over cleartext to a non-loopback host."""
    if not _URL_CHARS.fullmatch(endpoint):
        raise OtelSettingsError(f"{setting}: not a URL")
    try:
        parts = urlsplit(endpoint)
        host, _port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        raise OtelSettingsError(f"{setting}: not a URL") from None
    if parts.scheme not in {"http", "https"} or not host:
        raise OtelSettingsError(f"{setting}: must be an http:// or https:// URL with a host")
    if "@" in parts.netloc:
        raise OtelSettingsError(f"{setting}: must not carry credentials; use {HEADERS_SETTING}")
    if parts.query or parts.fragment or endpoint.endswith(("?", "#")):
        raise OtelSettingsError(f"{setting}: must not carry a query string or fragment")
    if has_headers and parts.scheme == "http" and not _is_loopback(host):
        raise OtelSettingsError(
            f"{HEADERS_SETTING} needs an https:// {setting} (http only for a loopback host)"
        )


class _DecoySpanExporter(SpanExporter):
    """One POST per batch to the configured endpoint. 2xx is SUCCESS; any other status
    or error is FAILURE. No retry, no redirect, no body read, no logging, no env."""

    def __init__(self, endpoint: str, headers: Mapping[str, str]) -> None:
        self._endpoint = endpoint
        self._headers = {
            **headers,
            "Content-Type": "application/x-protobuf",
            "x-decoy-telemetry": "v1",
        }
        self._adapter = HTTPAdapter()
        self._shutdown = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._shutdown:
            return SpanExportResult.FAILURE
        resp = None
        try:
            body = encode_spans(spans).SerializeToString()
            prepared = requests.Request(
                "POST", self._endpoint, data=body, headers=self._headers
            ).prepare()
            resp = self._adapter.send(
                prepared, stream=True, timeout=(2, 5), verify=True, cert=None, proxies={}
            )
            ok = 200 <= resp.status_code < 300
            return SpanExportResult.SUCCESS if ok else SpanExportResult.FAILURE
        except Exception:
            return SpanExportResult.FAILURE
        finally:
            if resp is not None:
                with suppress(Exception):
                    resp.close()

    def shutdown(self) -> None:
        self._shutdown = True
        with suppress(Exception):
            self._adapter.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


@dataclass(frozen=True)
class CliTelemetry:
    provider: TracerProvider
    exporter: _DecoySpanExporter


def _quiet_otel_logger() -> None:
    # Same idiom as decoy.ci.engine_logging: without it the root last-resort handler
    # prints SDK warnings and export tracebacks (endpoint included) to stderr.
    logger = logging.getLogger("opentelemetry")
    if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
        logger.addHandler(logging.NullHandler())
    logger.propagate = False


def _resource_attributes(service_version: str) -> dict[str, str]:
    from decoy_engine.telemetry import RESOURCE_KEYS

    attributes = {"service.name": "decoy-cli", "service.version": service_version}
    if set(attributes) != RESOURCE_KEYS:
        raise ValueError("resource key is not in RESOURCE_KEYS")
    return attributes


def _root_record(
    start_ns: int, end_ns: int, ok: bool, attributes: Sequence[tuple[str, str | int | float]]
):
    """The root as the engine's validated `SpanRecord`: name, keys and string values are
    checked by the same vocabulary the phase spans pass, before anything reaches the SDK."""
    from decoy_engine.telemetry import SpanRecord

    return SpanRecord("decoy.run", start_ns, end_ns, ok, tuple(attributes))


def build_provider(
    endpoint: str, headers: Mapping[str, str], *, service_version: str = _cli_version
) -> CliTelemetry:
    """A private provider (never the global one) exporting to `endpoint` only."""
    _quiet_otel_logger()
    exporter = _DecoySpanExporter(endpoint, headers)
    provider = TracerProvider(
        sampler=ParentBased(TraceIdRatioBased(1.0)),
        resource=Resource(_resource_attributes(service_version)),
        span_limits=SpanLimits(
            max_attributes=16,
            max_events=0,
            max_links=0,
            max_span_attributes=16,
            max_event_attributes=0,
            max_link_attributes=0,
            max_attribute_length=64,
            max_span_attribute_length=64,
        ),
        shutdown_on_exit=False,
        meter_provider=NoOpMeterProvider(),  # else get_meter_provider() may load OTEL_METER_PROVIDER
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            schedule_delay_millis=2000,
            export_timeout_millis=5000,
            meter_provider=NoOpMeterProvider(),  # the global one may load OTEL_* entry points
        )
    )
    return CliTelemetry(provider=provider, exporter=exporter)


def configure(
    endpoint: str,
    headers_raw: str | None,
    *,
    endpoint_setting: str,
    service_version: str = _cli_version,
) -> CliTelemetry:
    """Validate the Decoy settings (raising OtelSettingsError) and build the provider."""
    headers = parse_otel_headers(headers_raw)
    validate_endpoint(endpoint, has_headers=bool(headers), setting=endpoint_setting)
    return build_provider(endpoint, headers, service_version=service_version)


def flush_bounded(telemetry: CliTelemetry, budget_ms: int = FLUSH_BUDGET_MS) -> bool:
    """Flush on a daemon thread for at most `budget_ms`; then later exports return at once
    and the SDK logger is silenced. True when the flush finished in time."""

    def _flush() -> None:
        with suppress(Exception):
            telemetry.provider.force_flush()

    worker = threading.Thread(target=_flush, name="decoy-otel-flush", daemon=True)
    worker.start()
    worker.join(budget_ms / 1000)
    telemetry.exporter.shutdown()
    logging.getLogger("opentelemetry").setLevel(logging.CRITICAL + 1)
    return not worker.is_alive()


class RunTrace:
    """One `decoy.run` root span with the engine's phase spans under it.

    The engine's `SpanRecorder` pairs phase events into closed `SpanRecord`s; `_adopt`
    turns each into a span parented to the root explicitly, never to the ambient context.
    Every span call passes both exception keywords False and status is set by code only, so
    an engine error text (which can quote a cell value) never reaches the wire.
    """

    def __init__(self, telemetry: CliTelemetry) -> None:
        from decoy_engine import __version__ as engine_version
        from decoy_engine.telemetry import SpanRecorder

        self._tracer = telemetry.provider.get_tracer("decoy.cli")
        self._engine_version = engine_version
        self._start_ns = time.time_ns()
        opening = _root_record(
            self._start_ns, self._start_ns, True, [("decoy.engine.version", engine_version)]
        )
        # An explicit empty Context: an ambient span from another library is never the parent.
        self._root = self._tracer.start_span(
            opening.name,
            context=Context(),
            start_time=self._start_ns,
            attributes=dict(opening.attributes),
            record_exception=False,
            set_status_on_exception=False,
        )
        self._parent = set_span_in_context(self._root)
        self.recorder = SpanRecorder(self._adopt)
        self._finished = False

    def _adopt(self, record) -> None:
        span = self._tracer.start_span(
            record.name,
            context=self._parent,
            start_time=record.start_ns,
            attributes=dict(record.attributes),
            record_exception=False,
            set_status_on_exception=False,
        )
        if not record.ok:
            span.set_status(StatusCode.ERROR)
        span.end(record.end_ns)

    def finish(self, *, ok: bool, error_class: str | None = None) -> None:
        """Close open phases, then end the root. Idempotent."""
        if self._finished:
            return
        self._finished = True
        self.recorder.close()
        attributes: list[tuple[str, str | int | float]] = [
            ("decoy.engine.version", self._engine_version),
            ("decoy.spans_dropped", self.recorder.dropped),
        ]
        if ok:
            attributes.append(("decoy.outcome", "success"))
        else:
            from decoy_engine.progress import safe_error_class

            attributes.append(("decoy.outcome", "failed"))
            attributes.append(("error.type", safe_error_class(error_class) or "Exception"))
        record = _root_record(self._start_ns, max(time.time_ns(), self._start_ns), ok, attributes)
        for key, value in record.attributes:
            self._root.set_attribute(key, value)
        if record.ok:
            self._root.set_status(StatusCode.OK)
        else:
            self._root.set_status(StatusCode.ERROR)
        self._root.end(record.end_ns)
