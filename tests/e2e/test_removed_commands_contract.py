"""Negative public contract: the renamed-away commands are gone, with no alias.

The Pre-scan / Transform / Post-scan reframe hard-renamed the public commands
(pre-GA, no compatibility aliases). Each old spelling must resolve to an
unknown-command error with a non-zero exit, and each new spelling must exist.
This file names the old literals on purpose, so it is an exact exception in the
residual sentry (`tests/sentry/test_no_residual_removed_surface.py`).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

REMOVED_ARGVS = [
    ["scan", "data.csv"],
    ["scan"],
    ["scan", "fields", "scan.json"],
    ["scan", "show", "scan.json", "email"],
    ["scan", "diff", "a.json", "b.json"],
    ["storm"],
    ["storm", "scan"],
    ["storm", "analyze", "data.csv"],
    ["storm", "integrity", "masked.csv"],
    ["report", "integrity", "masked.csv", "--source", "source.csv"],
    ["report", "fidelity", "source.csv", "output.csv"],
]


@pytest.mark.parametrize("argv", REMOVED_ARGVS, ids=[" ".join(a) for a in REMOVED_ARGVS])
def test_removed_command_is_an_unknown_command(argv: list[str]) -> None:
    result = runner.invoke(app, argv)
    assert result.exit_code != 0, f"{argv} unexpectedly succeeded"
    assert "no such command" in result.output.lower(), result.output


def test_explain_storm_topic_is_gone() -> None:
    result = runner.invoke(app, ["explain", "storm"])
    assert result.exit_code != 0
    assert "unknown topic" in result.stderr.lower()
    # No alias: the old topic must not be redirected to a phase topic.
    assert "pre-scan" not in result.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["pre-scan", "--help"],
        ["pre-scan", "fields", "--help"],
        ["pre-scan", "show", "--help"],
        ["pre-scan", "diff", "--help"],
        ["post-scan", "--help"],
        ["post-scan", "integrity", "--help"],
        ["post-scan", "fidelity", "--help"],
        ["explain", "pipeline"],
        ["explain", "pre-scan"],
        ["explain", "post-scan"],
        ["report", "verify", "--help"],
    ],
    ids=lambda a: " ".join(a),
)
def test_new_command_exists(argv: list[str]) -> None:
    result = runner.invoke(app, argv)
    assert result.exit_code == 0, result.output


def test_root_help_names_phases_and_no_removed_commands() -> None:
    out = runner.invoke(app, ["--help"]).output
    assert "pre-scan" in out and "post-scan" in out
    assert "decoy scan" not in out
    assert "storm" not in out.lower()


def test_report_verify_is_an_artifact_check_not_a_privacy_check() -> None:
    out = runner.invoke(app, ["report", "verify", "--help"]).output.lower()
    assert "privacy" in out  # says what it is NOT
    assert "not a privacy" in out or "does not" in out


def test_old_config_keys_are_rejected(tmp_path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text("version: 1\nrun_storm: true\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", "config", str(cfg)])
    assert result.exit_code != 0
