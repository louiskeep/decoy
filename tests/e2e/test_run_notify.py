"""End-to-end exercise of `decoy run --notify` (N3, Sprint 5).

Command-surface acceptance tests (Slice 2, acceptance 1-5 of the sprint
guide): bad --notify spec exits pre-run usage error; --notify-on filters
which terminal outcome fires; a channel failure never changes the run's
exit code (best-effort); the --json envelope carries per-channel
{kind, delivered, target_host} only. The real-socket webhook round trip
("proven to send", not mocked) lives in
tests/e2e/test_notify_live_webhook.py (Slice 3). Redaction / log-hygiene
sentries live in tests/sentry/test_notify_redaction.py.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _write_mask_config(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"customer_id": ["1", "2"], "name": ["a", "b"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "customer_id",
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


def _write_bad_config(tmp_path: Path) -> Path:
    """A config that fails at run time (config-level plan-compile error)."""
    cfg = {
        "version": 1,
        "global_settings": {"seed": 1},
        "sources": {"t": {"type": "file", "format": "csv", "path": "./missing.csv"}},
        "tables": [{"name": "t", "columns": [{"name": "x", "strategy": "faker", "provider": "no_such_provider"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# --notify absent: byte-identical existing behavior (no regression).
# ---------------------------------------------------------------------------


def test_run_without_notify_unaffected(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)
    assert "notify" not in payload


# ---------------------------------------------------------------------------
# Bad --notify spec -> EXIT_USAGE, pre-run.
# ---------------------------------------------------------------------------


def test_run_bad_notify_spec_exits_usage_before_running(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    out_path = tmp_path / "out.csv"

    result = runner.invoke(app, ["run", str(cfg), "--notify", "sms:+15551234567"])
    assert result.exit_code == EXIT_USAGE
    assert not out_path.exists(), "a bad --notify spec must be caught before the run executes"


# ---------------------------------------------------------------------------
# --notify-on filtering.
# ---------------------------------------------------------------------------


def test_run_notify_on_success_fires_on_success(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)) as spy:
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg),
                "--notify",
                "webhook:https://hooks.example.com/x",
                "--notify-on",
                "success",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert spy.call_count == 1
    payload = _json.loads(result.output)
    assert payload["notify"] == [
        {"kind": "webhook", "delivered": True, "target_host": "hooks.example.com"}
    ]


def test_run_notify_on_success_does_not_fire_on_failure(tmp_path: Path):
    cfg = _write_bad_config(tmp_path)
    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)) as spy:
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg),
                "--notify",
                "webhook:https://hooks.example.com/x",
                "--notify-on",
                "success",
                "--json",
            ],
        )
    assert result.exit_code != 0
    assert spy.call_count == 0, "a failing run with --notify-on success must not notify"


def test_run_notify_on_failure_fires_on_failure(tmp_path: Path):
    cfg = _write_bad_config(tmp_path)
    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)) as spy:
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg),
                "--notify",
                "webhook:https://hooks.example.com/x",
                "--notify-on",
                "failure",
                "--json",
            ],
        )
    assert result.exit_code != 0
    assert spy.call_count == 1
    payload = _json.loads(result.output)
    assert payload["notify"][0]["delivered"] is True


def test_run_notify_on_always_fires_on_both_outcomes(tmp_path: Path):
    good_cfg = _write_mask_config(tmp_path)
    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)) as spy:
        ok_result = runner.invoke(
            app,
            ["run", str(good_cfg), "--notify", "webhook:https://hooks.example.com/x"],
        )
    assert ok_result.exit_code == 0
    assert spy.call_count == 1


# ---------------------------------------------------------------------------
# Best-effort: a channel failure never changes the run's exit code.
# ---------------------------------------------------------------------------


def test_run_notify_channel_failure_does_not_change_successful_run_exit_code(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    with mock.patch("decoy.notify.send_webhook", side_effect=RuntimeError("unreachable")):
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg),
                "--notify",
                "webhook:https://unreachable.example.invalid/x",
                "--json",
            ],
        )
    assert result.exit_code == 0, (
        f"a channel failure must never change the run's own exit code. output: {result.output}"
    )
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"


def test_run_notify_channel_returns_false_is_reported_but_does_not_fail_run(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    with mock.patch(
        "decoy.notify.send_webhook", return_value=(False, "delivery failed after retries")
    ):
        result = runner.invoke(
            app,
            ["run", str(cfg), "--notify", "webhook:https://hooks.example.com/x", "--json"],
        )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["notify"][0]["delivered"] is False


# ---------------------------------------------------------------------------
# Multiple channels; --json envelope shape.
# ---------------------------------------------------------------------------


def test_run_notify_multiple_channels_all_reported(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    with (
        mock.patch("decoy.notify.send_webhook", return_value=(True, None)),
        mock.patch("decoy.notify.send_slack", return_value=(True, None)),
    ):
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg),
                "--notify",
                "webhook:https://hooks.example.com/x",
                "--notify",
                "slack:https://hooks.slack.com/services/x",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)
    kinds = {entry["kind"] for entry in payload["notify"]}
    assert kinds == {"webhook", "slack"}


def test_run_notify_human_mode_shows_delivery_summary(tmp_path: Path):
    cfg = _write_mask_config(tmp_path)
    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)):
        result = runner.invoke(
            app, ["run", str(cfg), "--notify", "webhook:https://hooks.example.com/x"]
        )
    assert result.exit_code == 0, result.output
    assert "Notify" in result.output
    assert "1/1 delivered" in result.output
