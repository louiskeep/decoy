"""Best-effort run-notification channels: webhook, Slack, email (N3).

Mirrors decoy-platform's `api/notifications/dispatcher.py` -- the
`job_completed` event shape (`dispatcher.py:202`) and the webhook / Slack
transport + N2c retry policy (`dispatcher.py:501` / `:624`) -- rather than
importing it: the platform's `dispatch_for_event` needs a SQLAlchemy
`Session` and `api.config.settings` / `api.models.NotificationRule`, none
of which exist in a standalone CLI run. This module parameterizes the
target and signing key directly instead of pulling them off a persisted
`NotificationRule` row. See `platform-main-merge/api/notifications/
dispatcher.py` for the mirrored source; every non-stdlib behavior below
cites its line anchor.

Deliberately NOT mirrored: the platform's `_send_email` call convention.
`dispatcher.py:600`'s `_send_email` calls
`api/auth/email.py:send_email(rule.channel_target, subject, body)` --
three positional args against the real signature
`send_email(db, *, to, subject, body, html_body=None)`. That is a
signature mismatch that raises `TypeError`, silently swallowed by
`_deliver`'s broad `except Exception`, so the platform's email channel is
effectively broken today. This module's `send_email` is a fresh stdlib
`smtplib` implementation (mirroring `api/auth/email.py`'s STARTTLS +
login pattern, which IS correct in isolation), not a port of that broken
call site.

Redaction is by construction, mirroring `_outcome_facts`'s discipline
(`dispatcher.py:129-150`, `:137-142`): `build_run_event` returns facts
only -- kind, severity, timestamp, a human `detail` string, status, row
count, timings, and the pipeline config path -- never source or output
cell values, and never a secret (webhook URL, HMAC key, SMTP password).
Log hygiene follows the same rule: `NotifyResult.target_host` is a
host/domain only, never the full URL or address (see `_host_only` /
`_redact_email`).

Best-effort, always: `dispatch()` never raises. A channel failure is
recorded in its `NotifyResult` and logged via `logger.warning`; it never
propagates to the caller. This mirrors the platform's own rule
(`dispatcher.py:14-17`): "alerting must never take a job down." The CLI's
`decoy run --notify` wraps the call site in its own try/except as a second
line of defense (belt and suspenders), but this module's own contract
already guarantees it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any, Callable, Literal
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

ChannelKind = Literal["webhook", "slack", "email"]
RunStatus = Literal["success", "failure"]

_VALID_CHANNEL_KINDS: frozenset[str] = frozenset({"webhook", "slack", "email"})

# N2c retry constants, ported verbatim from
# platform-main-merge/api/notifications/dispatcher.py:86-88 so CLI webhook
# delivery behavior matches the platform's.
_WEBHOOK_MAX_RETRIES: int = 3
_WEBHOOK_BACKOFF_BASE_SECS: float = 1.0
_WEBHOOK_MAX_BACKOFF_SECS: float = 16.0


class NotifySpecError(ValueError):
    """A `--notify` spec string did not parse.

    Raised for an unknown channel kind or a missing target. The caller
    (`decoy run`) catches this BEFORE the pipeline runs and exits
    EXIT_USAGE (D3): a bad spec is a usage error, never a run failure.
    """


@dataclass(frozen=True)
class NotifyChannel:
    kind: ChannelKind
    target: str  # URL for webhook/slack; address for email


@dataclass(frozen=True)
class NotifyResult:
    kind: ChannelKind
    target_host: str  # host/domain only -- never the full URL or address
    delivered: bool
    detail: str | None = None  # short, non-secret diagnostic


@dataclass(frozen=True)
class SmtpConfig:
    """SMTP transport config, read from env vars by the caller (D3).

    Field names mirror the platform's `AppSettings` SMTP columns
    (`api/models.py:1271-1275`: smtp_host/smtp_port/smtp_user/smtp_pass/
    smtp_from) so the two channel models stay conceptually aligned.
    """

    host: str
    port: int = 587
    user: str | None = None
    password: str | None = None
    from_addr: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_addr)


def parse_notify_spec(spec: str) -> NotifyChannel:
    """Parse a `kind:target` --notify spec into a NotifyChannel.

    `kind` is one of webhook/slack/email (mirrors the platform's
    `ChannelKind`, `router.py:63`); `target` is everything after the
    first colon, so a webhook/slack URL's own `://` survives the split.
    Raises NotifySpecError on an unknown kind or empty target.
    """
    if ":" not in spec:
        raise NotifySpecError(
            f"--notify expects 'kind:target' (kind in webhook, slack, email); got {spec!r}."
        )
    kind, target = spec.split(":", 1)
    kind = kind.strip().lower()
    target = target.strip()
    if kind not in _VALID_CHANNEL_KINDS:
        raise NotifySpecError(
            f"--notify kind must be one of webhook, slack, email; got {kind!r}."
        )
    if not target:
        raise NotifySpecError(f"--notify {kind}: target is empty.")
    return NotifyChannel(kind=kind, target=target)  # type: ignore[arg-type]


def should_notify(notify_on: str, status: RunStatus) -> bool:
    """Filter for --notify-on {success, failure, always} (D3).

    Mirrors the platform's job_completed `condition_args {"status": [...]}`
    filter (`dispatcher.py:677-707`): an empty/absent filter fires on both
    terminal outcomes; here "always" is the explicit spelling of that.
    """
    if notify_on == "always":
        return True
    return notify_on == status


def build_run_event(
    *,
    status: RunStatus,
    config_path: str,
    row_count: int | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    run_id: str | None = None,
    error_summary: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the CLI's run-outcome event.

    Mirrors the platform's `job_completed` event
    (`dispatcher.py:202-241`) -- the terminal-outcome-agnostic shape that
    carries the actual status, so a single notification config covers
    "alert on success and/or failure" the same way a `job_completed` rule
    with a `condition_args.status` filter does on the platform. Field
    substitutions for the CLI's job-less context: `config` (the pipeline
    path) and an optional `run_id` (the local catalog run id, when one was
    recorded) replace the platform's `job_id`/`pipeline_id`/`job_url` (the
    CLI has no job id or web deep-link).

    Facts only (mirrors `_outcome_facts`, `dispatcher.py:129-150`): never
    source or output cell values, never a secret. `error_summary`, when
    given, is folded into the `detail` string exactly like the platform's
    `make_job_failed_event` (`dispatcher.py:101-126`) -- it is not carried
    as its own raw field.
    """
    if occurred_at is None:
        occurred_at = datetime.now(timezone.utc)
    severity = "error" if status == "failure" else "info"
    detail = f"decoy run {status}: {config_path}"
    if row_count is not None:
        detail += f" ({row_count} rows)"
    if error_summary:
        detail += f" - {error_summary}"
    return {
        "kind": "run_completed",
        "severity": severity,
        "occurred_at": occurred_at.isoformat(),
        "detail": detail,
        "status": status,
        "config": config_path,
        "run_id": run_id,
        "row_count": row_count,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
    }


# ── channels ─────────────────────────────────────────────────────────────


def send_webhook(
    url: str,
    event: dict[str, Any],
    *,
    secret_key: str | None = None,
    _sleep: Callable[[float], None] = time.sleep,
    _max_retries: int = _WEBHOOK_MAX_RETRIES,
) -> tuple[bool, str | None]:
    """POST `event` as JSON to `url`.

    Mirrors `_send_webhook` (`dispatcher.py:501-597`) verbatim: same
    headers (`X-Decoy-Signature`, `X-Decoy-Event-Kind`,
    `X-Decoy-Delivery-Id`), same stable per-call `delivery_id` (uuid4) for
    at-least-once dedup, same N2c retry policy (5xx / URLError retried
    with exponential backoff up to `_max_retries`; 4xx is a permanent
    rejection and is not retried).

    D3: signing is conditional on `secret_key`. The platform always signs
    (it always has `settings.secret_key`); the CLI may not have
    DECOY_NOTIFY_WEBHOOK_SECRET configured, in which case the request is
    sent unsigned and the caller is told so via the returned detail
    string (never silently). Returns (delivered, detail).
    """
    delivery_id = str(uuid.uuid4())
    body = dict(event)
    body["delivery_id"] = delivery_id
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Decoy-Event-Kind": event.get("kind", ""),
        "X-Decoy-Delivery-Id": delivery_id,
    }
    signed = secret_key is not None
    if signed:
        signature = hmac.new(secret_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        headers["X-Decoy-Signature"] = f"sha256={signature}"
    req = urllib.request.Request(url, data=raw, method="POST", headers=headers)

    for attempt in range(_max_retries):
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                status_code = resp.status
                if 200 <= status_code < 300:
                    return True, (
                        None
                        if signed
                        else "delivered unsigned (DECOY_NOTIFY_WEBHOOK_SECRET not set)"
                    )
                if 400 <= status_code < 500:
                    logger.warning(
                        "webhook %s returned HTTP %s (4xx, not retrying)",
                        _host_only(url),
                        status_code,
                    )
                    return False, f"http {status_code}"
                logger.warning(
                    "webhook %s returned HTTP %s (attempt %d/%d)",
                    _host_only(url),
                    status_code,
                    attempt + 1,
                    _max_retries,
                )
        except urllib.error.URLError as exc:
            logger.warning(
                "webhook %s unreachable (attempt %d/%d): %s",
                _host_only(url),
                attempt + 1,
                _max_retries,
                exc,
            )
        if attempt < _max_retries - 1:
            delay = min(_WEBHOOK_BACKOFF_BASE_SECS * (2**attempt), _WEBHOOK_MAX_BACKOFF_SECS)
            _sleep(delay)
    return False, "delivery failed after retries"


def send_slack(url: str, event: dict[str, Any]) -> tuple[bool, str | None]:
    """POST a Slack incoming-webhook payload (`text` + `blocks`).

    Mirrors `_send_slack` (`dispatcher.py:624-663`): same transport
    (plain POST, no HMAC -- the URL itself is Slack's auth), same
    `text`/`blocks` body shape, no retry (Slack incoming webhooks are
    fire-and-forget; the platform does not retry this channel either).
    """
    sev = event.get("severity", "info")
    emoji = "[!]" if sev == "error" else ("[w]" if sev == "warning" else "[i]")
    detail = event.get("detail", "A decoy run notification fired.")
    body: dict[str, Any] = {"text": f"{emoji} Decoy: {detail}"}
    fields: list[dict[str, str]] = []
    if event.get("config"):
        fields.append({"type": "mrkdwn", "text": f"*Config:* {event['config']}"})
    if event.get("status"):
        fields.append({"type": "mrkdwn", "text": f"*Status:* {event['status']}"})
    if event.get("occurred_at"):
        fields.append({"type": "mrkdwn", "text": f"*When:* {event['occurred_at']}"})
    if fields:
        body["blocks"] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": body["text"]}},
            {"type": "section", "fields": fields},
        ]
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=raw, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            delivered = 200 <= resp.status < 300
            return delivered, None if delivered else f"http {resp.status}"
    except urllib.error.URLError as exc:
        logger.warning("slack webhook %s unreachable: %s", _host_only(url), exc)
        return False, "unreachable"


def send_email(
    to_addr: str,
    event: dict[str, Any],
    *,
    smtp: SmtpConfig | None,
) -> tuple[bool, str | None]:
    """Send a plain-text email via stdlib smtplib.

    A fresh implementation (STARTTLS + optional login), NOT a port of the
    platform's broken `_send_email` call site (see module docstring).
    Mirrors `api/auth/email.py`'s send pattern, which is correct in
    isolation. Returns (delivered, detail); "email not configured" is a
    best-effort failure, not a run failure (D3).
    """
    if smtp is None or not smtp.configured:
        return False, "email not configured (set DECOY_NOTIFY_SMTP_HOST / DECOY_NOTIFY_SMTP_FROM)"

    sev = str(event.get("severity", "info")).upper()
    subject = f"[Decoy / {sev}] {event.get('kind', 'run')}"
    lines = [
        str(event.get("detail", "A decoy run notification fired.")),
        "",
        f"Status: {event.get('status', '')}",
        f"Config: {event.get('config', '')}",
    ]
    if event.get("row_count") is not None:
        lines.append(f"Rows: {event['row_count']}")
    msg = MIMEText("\n".join(lines), "plain")
    msg["Subject"] = subject
    msg["From"] = smtp.from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=10) as server:
            server.starttls()
            if smtp.user and smtp.password:
                server.login(smtp.user, smtp.password)
            server.send_message(msg)
        return True, None
    except Exception as exc:
        logger.warning("SMTP send to %s failed: %s", _redact_email(to_addr), exc)
        return False, "smtp send failed"


# ── fan-out ──────────────────────────────────────────────────────────────


def dispatch(
    event: dict[str, Any],
    channels: list[NotifyChannel],
    *,
    webhook_secret: str | None = None,
    smtp: SmtpConfig | None = None,
) -> list[NotifyResult]:
    """Fan `event` out to every configured channel, best-effort.

    Never raises: each channel is wrapped in its own try/except (mirrors
    `_deliver`, `dispatcher.py:473-498`, "alerting must never take a job
    down", `:14-17`). A channel failure is recorded in its NotifyResult and
    logged, not propagated. The caller (`decoy run --notify`) never has
    its own exit code changed by a channel failure.
    """
    results: list[NotifyResult] = []
    for ch in channels:
        host = _host_only(ch.target) if ch.kind in ("webhook", "slack") else _redact_email(ch.target)
        try:
            if ch.kind == "webhook":
                delivered, detail = send_webhook(ch.target, event, secret_key=webhook_secret)
            elif ch.kind == "slack":
                delivered, detail = send_slack(ch.target, event)
            else:
                delivered, detail = send_email(ch.target, event, smtp=smtp)
        except Exception as exc:
            logger.warning("notify channel %s failed: %s", ch.kind, exc)
            delivered, detail = False, "unexpected error"
        results.append(NotifyResult(kind=ch.kind, target_host=host, delivered=delivered, detail=detail))
    return results


# ── log-hygiene helpers (D3) ───────────────────────────────────────────────


def _host_only(url: str) -> str:
    """Host/domain only, never the full URL (which may carry an auth token
    in its path or query string, e.g. a Slack incoming-webhook URL)."""
    try:
        netloc = urlsplit(url).netloc
        return netloc or "(unknown host)"
    except Exception:
        return "(unknown host)"


def _redact_email(addr: str) -> str:
    """Domain only, never the full address."""
    if "@" in addr:
        return "***@" + addr.split("@", 1)[1]
    return "(redacted)"


__all__ = [
    "NotifyChannel",
    "NotifyResult",
    "NotifySpecError",
    "SmtpConfig",
    "build_run_event",
    "dispatch",
    "parse_notify_spec",
    "send_email",
    "send_slack",
    "send_webhook",
    "should_notify",
]
