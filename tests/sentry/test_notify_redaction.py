"""Raw-value isolation + log-hygiene sentry for `decoy run --notify` (N3).

Mirrors the platform's own redaction discipline
(`api/notifications/dispatcher.py:129-150`, `:137-142` -- "payloads carry
facts only: id, status, counts, timing, a job link; never rows, source/
output values, or secrets") and this repo's own sentry pattern
(tests/sentry/test_report_raw_value_isolation.py): plant a sentinel that
looks like a real source/output cell value or a real secret, run the
event builder / channel senders / a full `decoy run --notify` invocation,
and assert the sentinel never appears anywhere in what gets sent or
printed.

Two lanes:
  1. build_run_event: the event payload itself never carries a raw cell
     value, even when threaded through error_summary.
  2. `decoy run --notify` end to end: a run whose source CSV contains a
     sentinel PII value, notified over --json, must not leak that
     sentinel into stdout/stderr or the notify envelope. Also asserts
     the webhook secret / SMTP password never appear in CLI output.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.notify import build_run_event

runner = CliRunner()

_SENTINEL_PII = "SENTRY_NOTIFY_RAW_PII_" + "Q" * 20
_SENTINEL_SECRET = "SENTRY_NOTIFY_WEBHOOK_SECRET_" + "K" * 20

_ALLOWED_EVENT_FIELDS = {
    "kind",
    "severity",
    "occurred_at",
    "detail",
    "status",
    "config",
    "run_id",
    "row_count",
    "started_at",
    "finished_at",
}


# ---------------------------------------------------------------------------
# Lane 1: build_run_event never carries fields beyond the fact set.
# ---------------------------------------------------------------------------


def test_run_event_field_set_is_exactly_the_fact_fields():
    event = build_run_event(
        status="failure",
        config_path="pipeline.yaml",
        row_count=10,
        started_at=None,
        finished_at=None,
        error_summary="StrategyError",  # caller passes a safe TYPE name, never raw text
    )
    assert set(event.keys()) == _ALLOWED_EVENT_FIELDS, (
        f"build_run_event must carry only fact fields; got extra keys: "
        f"{set(event.keys()) - _ALLOWED_EVENT_FIELDS}"
    )


def test_build_run_event_folds_error_summary_verbatim_so_caller_must_redact():
    """Documents the sharp edge the sprint-5 BLOCKER was about: build_run_event
    folds error_summary VERBATIM into the outbound `detail`. This is exactly
    why `decoy run`'s failure path must NOT hand it a raw engine error (see
    the failure-path egress test below). This test pins that contract so a
    future edit that starts trusting error_summary is caught here first."""
    event = build_run_event(
        status="failure",
        config_path="pipeline.yaml",
        row_count=None,
        started_at=None,
        finished_at=None,
        error_summary=_SENTINEL_PII,
    )
    # If a caller passes raw text, it DOES reach detail -- hence callers must
    # pass a redacted summary. The run.py guard is what this documents.
    assert _SENTINEL_PII in event["detail"]


# ---------------------------------------------------------------------------
# Lane 2: `decoy run --notify` end to end -- no raw values, no secrets.
# ---------------------------------------------------------------------------


def _write_mask_config(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"customer_id": ["1", "2"], "email": [f"{_SENTINEL_PII}@x.com", "b@x.com"]}).to_csv(
        src, index=False
    )
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "customer_identity",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def test_run_notify_json_envelope_never_leaks_raw_pii(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DECOY_NOTIFY_WEBHOOK_SECRET", _SENTINEL_SECRET)
    cfg_path = _write_mask_config(tmp_path)

    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)) as spy:
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg_path),
                "--notify",
                "webhook:https://hooks.example.com/x",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    assert _SENTINEL_PII not in result.output, (
        "decoy run --notify leaked a raw source cell value into --json output"
    )
    assert _SENTINEL_SECRET not in result.output, (
        "decoy run --notify leaked the webhook secret into --json output"
    )
    payload = _json.loads(result.output)
    assert "notify" in payload
    for entry in payload["notify"]:
        assert set(entry.keys()) <= {"kind", "delivered", "target_host"}
        assert _SENTINEL_PII not in _json.dumps(entry)
        assert _SENTINEL_SECRET not in _json.dumps(entry)

    # The event actually handed to the webhook sender must also be clean.
    assert spy.call_count == 1
    sent_event = spy.call_args[0][1]
    assert _SENTINEL_PII not in _json.dumps(sent_event)
    assert _SENTINEL_SECRET not in _json.dumps(sent_event)


def test_run_notify_stderr_never_leaks_webhook_secret(tmp_path: Path, monkeypatch):
    """A channel delivery failure's stderr warning must name the host,
    never the secret or full URL (D3 log hygiene)."""
    monkeypatch.setenv("DECOY_NOTIFY_WEBHOOK_SECRET", _SENTINEL_SECRET)
    cfg_path = _write_mask_config(tmp_path)

    with mock.patch(
        "decoy.notify.send_webhook", return_value=(False, "delivery failed after retries")
    ):
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg_path),
                "--notify",
                f"webhook:https://hooks.example.com/x?auth={_SENTINEL_SECRET}",
            ],
        )

    assert result.exit_code == 0, "a channel failure must never change the run's exit code"
    assert _SENTINEL_SECRET not in result.output


# ---------------------------------------------------------------------------
# Lane 3: FAILING run whose engine error quotes a cell value (sprint-5 BLOCKER).
# ---------------------------------------------------------------------------


def test_failing_run_engine_error_with_pii_never_reaches_the_wire(tmp_path: Path):
    """The top-weighted egress risk: a FAILING run whose engine exception
    quotes a raw source-row cell value must NOT egress that value to the
    notification channel. Asserts the sentinel is absent from BOTH the
    dispatched event AND the real POST body, while confirming it DID reach
    local stdout (so the test genuinely exercised the error path, not a
    no-op)."""
    cfg_path = _write_mask_config(tmp_path)

    captured: dict = {}

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _FakeResponse()

    # Force the engine to raise an exception whose message quotes the
    # sentinel cell value, exactly the shape run.py:403-407 warns about.
    engine_error = RuntimeError(f"could not mask value {_SENTINEL_PII}: bad row")

    with (
        mock.patch("decoy_engine.run_pipeline", side_effect=engine_error),
        mock.patch("urllib.request.urlopen", _fake_urlopen),
    ):
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg_path),
                "--notify",
                "webhook:https://hooks.example.com/x",
                "--notify-on",
                "always",
                "--json",
            ],
        )

    # The run failed (engine raised), so exit code is non-zero.
    assert result.exit_code != 0, result.output
    # Control: the raw error DID reach local stdout (the --json envelope's
    # `error` field). This proves the error path actually fired.
    assert _SENTINEL_PII in result.stdout, (
        "test setup error: the engine error did not reach local output, so the "
        "egress assertion below would be vacuously true"
    )

    # A real POST was made over the (mocked-transport) webhook.
    assert "body" in captured, "the failure-path notification must have been dispatched"
    body_text = captured["body"].decode("utf-8")
    assert _SENTINEL_PII not in body_text, (
        "BLOCKER regression: a raw source cell value quoted by an engine error "
        "egressed to the webhook body. The failure path must send the exception "
        "TYPE name only, never the raw error string."
    )

    # And the run's own --json envelope's notify block stays clean too.
    payload = _json.loads(result.stdout)
    assert _SENTINEL_PII not in _json.dumps(payload.get("notify", []))
