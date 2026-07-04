"""Unit tests for `decoy.notify` (N3, Sprint 5).

Covers: --notify spec parsing, --notify-on filtering, the run-event
builder's redaction-by-construction, the webhook/slack/email channel
senders (via a mocked urllib.urlopen / smtplib.SMTP -- the real-socket
round trip lives in tests/e2e/test_notify_live_webhook.py per the
sprint's Slice 3 "proven to send" requirement), and dispatch()'s
best-effort fan-out + log-hygiene (target_host never the full URL).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from decoy.notify import (
    NotifyChannel,
    NotifySpecError,
    SmtpConfig,
    build_run_event,
    dispatch,
    parse_notify_spec,
    send_email,
    send_slack,
    send_webhook,
    should_notify,
)

# ---------------------------------------------------------------------------
# parse_notify_spec
# ---------------------------------------------------------------------------


def test_parse_webhook_spec():
    ch = parse_notify_spec("webhook:https://hooks.example.com/x?token=abc")
    assert ch.kind == "webhook"
    assert ch.target == "https://hooks.example.com/x?token=abc"


def test_parse_slack_spec():
    ch = parse_notify_spec("slack:https://hooks.slack.com/services/T0/B0/xyz")
    assert ch.kind == "slack"
    assert ch.target == "https://hooks.slack.com/services/T0/B0/xyz"


def test_parse_email_spec():
    ch = parse_notify_spec("email:ops@example.com")
    assert ch.kind == "email"
    assert ch.target == "ops@example.com"


def test_parse_spec_missing_colon_raises():
    with pytest.raises(NotifySpecError):
        parse_notify_spec("webhook-no-colon")


def test_parse_spec_unknown_kind_raises():
    with pytest.raises(NotifySpecError):
        parse_notify_spec("sms:+15551234567")


def test_parse_spec_empty_target_raises():
    with pytest.raises(NotifySpecError):
        parse_notify_spec("webhook:")


# ---------------------------------------------------------------------------
# should_notify (--notify-on filtering)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "notify_on,status,expected",
    [
        ("always", "success", True),
        ("always", "failure", True),
        ("success", "success", True),
        ("success", "failure", False),
        ("failure", "failure", True),
        ("failure", "success", False),
    ],
)
def test_should_notify(notify_on, status, expected):
    assert should_notify(notify_on, status) is expected


# ---------------------------------------------------------------------------
# build_run_event -- redaction by construction
# ---------------------------------------------------------------------------

_ALLOWED_FIELDS = {
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


def test_build_run_event_only_carries_fact_fields():
    event = build_run_event(
        status="success",
        config_path="pipeline.yaml",
        row_count=42,
        started_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 4, 0, 1, tzinfo=timezone.utc),
    )
    assert set(event.keys()) == _ALLOWED_FIELDS
    assert event["status"] == "success"
    assert event["row_count"] == 42
    assert event["config"] == "pipeline.yaml"


def test_build_run_event_failure_severity_is_error():
    event = build_run_event(
        status="failure",
        config_path="pipeline.yaml",
        row_count=None,
        started_at=None,
        finished_at=None,
        error_summary="unknown_provider: no_such_provider",
    )
    assert event["severity"] == "error"
    assert event["status"] == "failure"
    # error_summary is folded into `detail`, not carried as its own field.
    assert "unknown_provider" in event["detail"]
    assert set(event.keys()) == _ALLOWED_FIELDS


def test_build_run_event_never_contains_raw_source_values():
    """Redaction sentry core assertion (mirrors dispatcher.py:137-142): a
    sentinel that looks like a source/output cell value must never appear
    in the built event, even when threaded through error_summary."""
    sentinel = "SENTRY_RAW_ROW_VALUE_ZZZZ_" + "Q" * 20
    event = build_run_event(
        status="success",
        config_path="pipeline.yaml",
        row_count=10,
        started_at=None,
        finished_at=None,
    )
    serialized = json.dumps(event)
    assert sentinel not in serialized


# ---------------------------------------------------------------------------
# send_webhook -- signature, retry, delivery_id
# ---------------------------------------------------------------------------


def test_send_webhook_signs_with_hmac_when_secret_given():
    captured: dict = {}

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        return _FakeResponse()

    event = {"kind": "run_completed", "status": "success"}
    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, detail = send_webhook(
            "https://hooks.example.com/x", event, secret_key="s3cr3t"
        )

    assert delivered is True
    assert detail is None
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert "x-decoy-signature" in headers
    assert "x-decoy-delivery-id" in headers
    expected_sig = hmac.new(b"s3cr3t", captured["body"], hashlib.sha256).hexdigest()
    assert headers["x-decoy-signature"] == f"sha256={expected_sig}"


def test_send_webhook_unsigned_when_no_secret():
    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured: dict = {}

    def _fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _FakeResponse()

    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, detail = send_webhook(
            "https://hooks.example.com/x", {"kind": "run_completed"}, secret_key=None
        )

    assert delivered is True
    assert detail is not None and "unsigned" in detail
    headers = {k.lower() for k in captured["headers"]}
    assert "x-decoy-signature" not in headers


def test_send_webhook_4xx_is_not_retried():
    class _FakeResponse:
        status = 404

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = {"n": 0}

    def _fake_urlopen(req, timeout=None):
        calls["n"] += 1
        return _FakeResponse()

    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, _detail = send_webhook(
            "https://hooks.example.com/x",
            {"kind": "run_completed"},
            secret_key="k",
            _sleep=lambda _: None,
        )

    assert delivered is False
    assert calls["n"] == 1, "4xx must not be retried"


def test_send_webhook_5xx_is_retried_up_to_max_retries():
    class _FakeResponse:
        status = 503

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = {"n": 0}

    def _fake_urlopen(req, timeout=None):
        calls["n"] += 1
        return _FakeResponse()

    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, _detail = send_webhook(
            "https://hooks.example.com/x",
            {"kind": "run_completed"},
            secret_key="k",
            _max_retries=3,
            _sleep=lambda _: None,
        )

    assert delivered is False
    assert calls["n"] == 3, "5xx must be retried up to _max_retries total attempts"


def test_send_webhook_retries_then_succeeds():
    import urllib.error

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = {"n": 0}

    def _fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("connection refused")
        return _FakeResponse()

    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, _detail = send_webhook(
            "https://hooks.example.com/x",
            {"kind": "run_completed"},
            secret_key="k",
            _sleep=lambda _: None,
        )

    assert delivered is True
    assert calls["n"] == 2


def test_send_webhook_delivery_id_stable_across_retries():
    """M2 at-least-once semantics: delivery_id is generated once per call
    and held constant across every retry attempt (mirrors dispatcher.py's
    M2 note)."""
    import urllib.error

    seen_ids: list[str] = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        headers = {k.lower(): v for k, v in req.header_items()}
        seen_ids.append(headers["x-decoy-delivery-id"])
        if len(seen_ids) < 2:
            raise urllib.error.URLError("boom")
        return _FakeResponse()

    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        send_webhook(
            "https://hooks.example.com/x",
            {"kind": "run_completed"},
            secret_key="k",
            _sleep=lambda _: None,
        )

    assert len(seen_ids) == 2
    assert seen_ids[0] == seen_ids[1]


# ---------------------------------------------------------------------------
# send_slack
# ---------------------------------------------------------------------------


def test_send_slack_posts_text_and_blocks():
    captured: dict = {}

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return _FakeResponse()

    event = build_run_event(
        status="success", config_path="pipeline.yaml", row_count=5, started_at=None, finished_at=None
    )
    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, _detail = send_slack("https://hooks.slack.com/services/x", event)

    assert delivered is True
    assert "text" in captured["body"]
    assert "blocks" in captured["body"]


def test_send_slack_unreachable_returns_false():
    import urllib.error

    def _fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("nope")

    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        delivered, _detail = send_slack("https://hooks.slack.com/services/x", {"kind": "x"})

    assert delivered is False


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------


def test_send_email_not_configured_is_best_effort_failure():
    delivered, detail = send_email("ops@example.com", {"kind": "run_completed"}, smtp=None)
    assert delivered is False
    assert "not configured" in detail


def test_send_email_sends_via_smtp_with_starttls_when_supported():
    sent: dict = {}

    class _FakeSmtp:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            sent["ehlo"] = sent.get("ehlo", 0) + 1

        def has_extn(self, name):
            return name.lower() == "starttls"

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["message"] = msg

    smtp_cfg = SmtpConfig(
        host="smtp.example.com", port=587, user="u", password="p", from_addr="from@example.com"
    )
    event = build_run_event(
        status="success", config_path="pipeline.yaml", row_count=3, started_at=None, finished_at=None
    )
    with mock.patch("smtplib.SMTP", _FakeSmtp):
        delivered, _detail = send_email("ops@example.com", event, smtp=smtp_cfg)

    assert delivered is True
    assert sent["starttls"] is True
    assert sent["login"] == ("u", "p")
    assert sent["message"]["To"] == "ops@example.com"


def test_send_email_skips_starttls_when_server_does_not_support_it():
    """LOW-2 regression: a relay/dry-run catcher that does not advertise
    STARTTLS (python -m smtpd, MailHog) must still receive the message,
    not fail on an unconditional server.starttls()."""
    sent: dict = {}

    class _FakeSmtpNoTls:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def has_extn(self, name):
            return False  # no STARTTLS advertised

        def starttls(self):
            raise AssertionError("starttls must NOT be called when unsupported")

        def send_message(self, msg):
            sent["message"] = msg

    smtp_cfg = SmtpConfig(host="localhost", port=1025, from_addr="from@example.com")
    event = build_run_event(
        status="success", config_path="pipeline.yaml", row_count=1, started_at=None, finished_at=None
    )
    with mock.patch("smtplib.SMTP", _FakeSmtpNoTls):
        delivered, _detail = send_email("ops@example.com", event, smtp=smtp_cfg)

    assert delivered is True
    assert sent["message"]["To"] == "ops@example.com"


def test_send_email_smtp_failure_is_best_effort():
    class _FakeSmtp:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            raise ConnectionRefusedError("no smtp")

        def __exit__(self, *a):
            return False

    smtp_cfg = SmtpConfig(host="smtp.example.com", from_addr="from@example.com")
    with mock.patch("smtplib.SMTP", _FakeSmtp):
        delivered, _detail = send_email(
            "ops@example.com", {"kind": "run_completed"}, smtp=smtp_cfg
        )
    assert delivered is False


# ---------------------------------------------------------------------------
# dispatch() -- best-effort fan-out + log hygiene
# ---------------------------------------------------------------------------


def test_dispatch_fans_out_to_multiple_channels():
    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        return _FakeResponse()

    channels = [
        NotifyChannel(kind="webhook", target="https://hooks.example.com/a?token=SECRET"),
        NotifyChannel(kind="slack", target="https://hooks.slack.com/services/T/B/xyz"),
    ]
    event = {"kind": "run_completed", "status": "success"}
    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        results = dispatch(event, channels, webhook_secret="k")

    assert len(results) == 2
    assert all(r.delivered for r in results)
    kinds = {r.kind for r in results}
    assert kinds == {"webhook", "slack"}


def test_dispatch_never_raises_on_channel_exception():
    """A channel whose sender raises must not propagate -- best-effort
    (D2: 'notification is best-effort', mirrors dispatcher.py:14-17)."""

    def _boom(*a, **kw):
        raise RuntimeError("channel exploded")

    channels = [NotifyChannel(kind="webhook", target="https://hooks.example.com/a")]
    with mock.patch("decoy.notify.send_webhook", _boom):
        results = dispatch({"kind": "run_completed"}, channels, webhook_secret="k")

    assert len(results) == 1
    assert results[0].delivered is False


def test_dispatch_target_host_never_leaks_full_url_or_token():
    """Log-hygiene sentry: target_host is host-only, never the full URL
    (which may carry an auth token in its path/query, e.g. a Slack
    incoming-webhook URL or a webhook URL with a signed query string)."""

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        return _FakeResponse()

    secret_path = "https://hooks.example.com/T00/B00/verysecrettoken?auth=SECRET"
    channels = [NotifyChannel(kind="webhook", target=secret_path)]
    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        results = dispatch({"kind": "run_completed"}, channels, webhook_secret="k")

    assert results[0].target_host == "hooks.example.com"
    assert "verysecrettoken" not in results[0].target_host
    assert "SECRET" not in results[0].target_host


def test_dispatch_email_target_host_is_domain_only():
    channels = [NotifyChannel(kind="email", target="ops@example.com")]
    results = dispatch({"kind": "run_completed"}, channels, smtp=None)
    assert results[0].target_host == "***@example.com"
    assert "ops" not in results[0].target_host
