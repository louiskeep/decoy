"""Tests for the section-4 output-mode contract.

Covers --json / --quiet / --verbose behavior on the existing `run` and
`validate` commands, plus the NO_COLOR env precondition.
"""

from __future__ import annotations

import json as _json
import os
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.ui.output import _make_console


runner = CliRunner()
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@pytest.fixture
def good_config(tmp_path: Path) -> Path:
    sample = tmp_path / "input.csv"
    pd.DataFrame({"name": ["Alice", "Bob"]}).to_csv(sample, index=False)

    # CLI.3 (2026-06-02): V2 PipelineConfig shape replaces V1 `input:`/
    # `output:`/`masking_rules:` (rejected by the V2 choke point).
    cfg = {
        "version": 1,
        "mode": "mask",
        "global_settings": {"seed": 42},
        "sources": {
            "people": {"type": "file", "format": "csv", "path": str(sample)},
        },
        "tables": [
            {
                "name": "people",
                "columns": [
                    {"name": "name", "strategy": "faker", "provider": "person_name"},
                ],
            },
        ],
        "targets": {
            "people": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")},
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg))
    return config_path


@pytest.fixture
def bad_config(tmp_path: Path) -> Path:
    cfg = {"global_settings": {"seed": 42}}  # missing input/output/rules
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.dump(cfg))
    return config_path


# --json -----------------------------------------------------------------


def test_validate_json_success_emits_one_object_to_stdout(good_config: Path):
    result = runner.invoke(app, ["validate", str(good_config), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "validate"
    assert payload["status"] == "ok"
    assert payload["config"] == str(good_config)


def test_validate_json_failure_emits_error_object_and_exits_nonzero(bad_config: Path):
    result = runner.invoke(app, ["validate", str(bad_config), "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["command"] == "validate"
    assert payload["status"] == "error"
    assert payload["error"]


# --quiet ----------------------------------------------------------------


def test_validate_quiet_success_produces_empty_stdout(good_config: Path):
    result = runner.invoke(app, ["validate", str(good_config), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_validate_quiet_failure_still_exits_nonzero_with_empty_stdout(bad_config: Path):
    result = runner.invoke(app, ["validate", str(bad_config), "--quiet"])
    assert result.exit_code == 1
    assert result.stdout == ""


# Mutually-exclusive flags -----------------------------------------------


def test_verbose_plus_quiet_is_a_user_error(good_config: Path):
    result = runner.invoke(
        app, ["validate", str(good_config), "--verbose", "--quiet"]
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


def test_json_plus_quiet_is_a_user_error(good_config: Path):
    result = runner.invoke(
        app, ["validate", str(good_config), "--json", "--quiet"]
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


# Error shape (section 9) -------------------------------------------------


def test_validate_error_has_cause_and_hint(bad_config: Path):
    result = runner.invoke(app, ["validate", str(bad_config)])
    assert result.exit_code == 1
    # Cause line + hint line per CLI_UX_GUIDE.md section 9.
    assert "error:" in result.stderr.lower()
    assert "hint:" in result.stderr.lower()


# NO_COLOR precondition ---------------------------------------------------


def test_no_color_env_disables_ansi_on_console(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    console = _make_console(stderr=False)
    assert console.no_color is True


def test_no_color_unset_leaves_console_default(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    console = _make_console(stderr=False)
    assert console.no_color is False


# run command --json regression ------------------------------------------


def test_run_json_success_emits_status_object(good_config: Path):
    result = runner.invoke(app, ["run", str(good_config), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "run"
    assert payload["status"] == "ok"
    assert payload["mode"] == "mask"


def test_run_quiet_success_produces_empty_stdout(good_config: Path):
    result = runner.invoke(app, ["run", str(good_config), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
