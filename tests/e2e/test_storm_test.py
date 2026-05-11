"""End-to-end tests for `decoy storm test` -- the animation demo command."""

from __future__ import annotations

import json as _json
import time

from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()


def test_storm_test_help_includes_examples():
    result = runner.invoke(app, ["storm", "test", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout
    # Help mentions the demo intent.
    assert "No data" in result.stdout or "demo" in result.stdout.lower()


def test_storm_test_default_renders_demo_card_quickly():
    """--seconds 0 lets us exercise the full code path without waiting."""
    result = runner.invoke(app, ["storm", "test", "--seconds", "0"])
    assert result.exit_code == 0
    # Card heading.
    assert "decoy storm test" in result.stdout
    # Demo marker so users don't mistake it for a real scan.
    assert "demo (no data scanned)" in result.stdout
    # Next hint points at the real scan command.
    assert "decoy storm scan" in result.stdout


def test_storm_test_seconds_flag_controls_duration():
    start = time.monotonic()
    result = runner.invoke(app, ["storm", "test", "--seconds", "0.3"])
    elapsed = time.monotonic() - start
    assert result.exit_code == 0
    # Should sleep ~0.3s total. Allow generous slack for CI jitter and the
    # multistage Live setup overhead.
    assert 0.25 <= elapsed < 5.0


def test_storm_test_json_emits_envelope_without_sleeping():
    start = time.monotonic()
    result = runner.invoke(app, ["storm", "test", "--json"])
    elapsed = time.monotonic() - start
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm test"
    assert payload["status"] == "ok"
    assert payload["demo"] is True
    # facts dict mirrors the human card.
    assert "PII columns" in payload["facts"]
    # Should be near-instant -- no animation.
    assert elapsed < 2.0


def test_storm_test_quiet_produces_empty_stdout_quickly():
    start = time.monotonic()
    result = runner.invoke(app, ["storm", "test", "--quiet"])
    elapsed = time.monotonic() - start
    assert result.exit_code == 0
    assert result.stdout == ""
    assert elapsed < 2.0


def test_storm_test_negative_seconds_rejected():
    result = runner.invoke(app, ["storm", "test", "--seconds", "-1"])
    assert result.exit_code != 0
