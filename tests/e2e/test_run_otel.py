"""F30 C1a: `decoy run --otel-endpoint` settings, the `[otel]` extra and env isolation.

C-T1 `env`, C-T5 and C-T6 through `typer.testing.CliRunner`; the exporter cells live in
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
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
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
