# Notify live-channel runbook + log (append-only)

`decoy run --notify` (N3) ships with two proof layers:

1. **Automated, CI-safe**: `tests/e2e/test_notify_live_webhook.py` runs a
   real `decoy run --notify webhook:...` subprocess against a real local
   HTTP server over a real socket (stdlib `http.server`, no mocking) and
   verifies the HMAC signature, headers, and event payload. This proves
   the webhook transport on every CI run.
2. **Manual, human-run**: Slack incoming-webhooks and real SMTP relays
   cannot be exercised headlessly in CI (they need a live external
   service and real credentials). This runbook is that manual check. Run
   it once per release (or whenever the notify transport changes) and
   append a row to the log below, mirroring `docs/release/smoke-log.md`'s
   pattern.

## Manual runbook

Prerequisites:
- A Slack workspace with an incoming-webhook URL
  (`https://hooks.slack.com/services/...`), or a webhook-echo SaaS like
  <https://webhook.site> as a stand-in if no live Slack workspace is
  available for this run.
- A real SMTP relay (a personal/dev SMTP account, or a local
  `python -m smtpd` / MailHog-style catcher for a dry run without sending
  real mail).

Steps:

```bash
export DECOY_NOTIFY_SMTP_HOST=smtp.example.com
export DECOY_NOTIFY_SMTP_PORT=587
export DECOY_NOTIFY_SMTP_USER=you@example.com
export DECOY_NOTIFY_SMTP_PASS=your-app-password
export DECOY_NOTIFY_SMTP_FROM=you@example.com

decoy demo  # or any small pipeline.yaml

decoy run pipeline.yaml \
  --notify slack:https://hooks.slack.com/services/XXX/YYY/ZZZ \
  --notify email:you@example.com \
  --notify-on always \
  --json
```

Confirm:
- The Slack channel behind the incoming-webhook received one message
  (text starting `[i] Decoy: decoy run success: pipeline.yaml`).
- The email address received one message (subject
  `[Decoy / INFO] run_completed`).
- The `--json` envelope's `notify` array shows
  `{"kind": "slack", "delivered": true, ...}` and
  `{"kind": "email", "delivered": true, ...}`.
- Neither the Slack message nor the email contains any source/output row
  values (facts only: status, row count, config path, timestamps).

Paste the delivery evidence (a screenshot or the raw Slack/email receipt)
into the PR or the release notes, then append a row below.

## Log

| Date | SHA | Channels | Run by | Notes |
|------|-----|----------|--------|-------|
| _no manual run recorded yet_ | | | | Sprint 5 (2026-07-04) shipped the automated webhook proof (`tests/e2e/test_notify_live_webhook.py`, green in CI) but the manual Slack + SMTP runbook above has not yet been executed against live credentials -- this sandbox has none. **Run the steps above against a real Slack workspace + SMTP relay and record the result here before calling N3's "live proof" fully closed.** |
