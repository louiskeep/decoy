"""Tests for the section-4 output-mode contract.

Covers --json / --quiet / --verbose behavior on the existing `run` and
`validate` commands, plus the NO_COLOR env precondition.
"""

from __future__ import annotations

import json as _json
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
        "version": 2,
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
    result = runner.invoke(app, ["validate", "config", str(good_config), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "validate"
    assert payload["status"] == "ok"
    assert payload["config"] == str(good_config)


def test_validate_json_failure_emits_error_object_and_exits_nonzero(bad_config: Path):
    result = runner.invoke(app, ["validate", "config", str(bad_config), "--json"])
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["command"] == "validate"
    assert payload["status"] == "error"
    assert payload["error"]


# --quiet ----------------------------------------------------------------


def test_validate_quiet_success_produces_empty_stdout(good_config: Path):
    result = runner.invoke(app, ["validate", "config", str(good_config), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_validate_quiet_failure_still_exits_nonzero_with_empty_stdout(bad_config: Path):
    result = runner.invoke(app, ["validate", "config", str(bad_config), "--quiet"])
    assert result.exit_code == 1
    assert result.stdout == ""


# Mutually-exclusive flags -----------------------------------------------


def test_verbose_plus_quiet_is_a_user_error(good_config: Path):
    result = runner.invoke(app, ["validate", "config", str(good_config), "--verbose", "--quiet"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


def test_json_plus_quiet_is_a_user_error(good_config: Path):
    result = runner.invoke(app, ["validate", "config", str(good_config), "--json", "--quiet"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


# Error shape (section 9) -------------------------------------------------


def test_validate_error_has_cause_and_hint(bad_config: Path):
    result = runner.invoke(app, ["validate", "config", str(bad_config)])
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


# One soft-wrapped stderr console (CLI-MAC-TESTS AT-6) ---------------------
#
# Off a TTY Rich folds at 80 columns and puts a newline inside a long path. The path is
# the thing a user greps for, so error text must stay on one line. COLUMNS=80 pins the
# width the failing macOS tmp paths hit.

LONG_DIR_LEN = 90


def _long_dir(tmp_path: Path) -> Path:
    d = tmp_path / ("d" * LONG_DIR_LEN)
    d.mkdir(exist_ok=True)
    return d


def _missing_source_config(tmp_path: Path) -> tuple[Path, Path]:
    absent = _long_dir(tmp_path) / "absent.csv"
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(absent)}},
        "tables": [
            {
                "name": "customers",
                "columns": [{"name": "name", "strategy": "faker", "provider": "person_name"}],
            },
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")},
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.dump(cfg))
    return path, absent


def _bad_profile(tmp_path: Path, good_config: Path) -> tuple[Path, Path]:
    profile = _long_dir(tmp_path) / "profile.json"
    profile.write_text("{not json", encoding="utf-8")
    return good_config, profile


def _non_mapping_config(tmp_path: Path) -> Path:
    cfg = _long_dir(tmp_path) / "list.yaml"
    cfg.write_text("- a\n- b\n", encoding="utf-8")
    return cfg


def test_run_missing_source_path_is_printed_whole(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    path, absent = _missing_source_config(tmp_path)
    result = runner.invoke(app, ["run", str(path)])
    assert result.exit_code != 0
    assert str(absent) in result.stderr, result.stderr


def test_compile_bad_profile_path_is_printed_whole(tmp_path: Path, good_config: Path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    config, profile = _bad_profile(tmp_path, good_config)
    result = runner.invoke(app, ["validate", "compile", str(config), "--profile", str(profile)])
    assert result.exit_code != 0
    assert str(profile) in result.stderr, result.stderr


def test_compile_non_mapping_config_path_is_printed_whole(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    cfg = _non_mapping_config(tmp_path)
    result = runner.invoke(app, ["validate", "compile", str(cfg)])
    assert result.exit_code != 0
    assert str(cfg) in result.stderr, result.stderr


# JSON contract guards: green on the base by design. Layout work must not touch stdout JSON.


def test_run_missing_source_json_envelope_is_unchanged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    path, absent = _missing_source_config(tmp_path)
    result = runner.invoke(app, ["run", str(path), "--json"])
    assert result.exit_code != 0
    payload = _json.loads(result.stdout)
    assert set(payload) == {
        "command",
        "status",
        "config",
        "mode",
        "error",
        "error_kind",
        "messages",
    }
    assert payload["command"] == "run" and payload["error_kind"] == "validation"
    assert str(absent) in payload["error"]
    first = payload["messages"][0]
    assert set(first) == {"layer", "severity", "code", "message", "location"}
    assert first["code"] == "source.customers.exists"
    assert str(absent) in first["message"]


def test_compile_json_envelopes_are_unchanged(tmp_path: Path, good_config: Path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    config, profile = _bad_profile(tmp_path, good_config)
    bad = runner.invoke(
        app, ["validate", "compile", str(config), "--profile", str(profile), "--json"]
    )
    payload = _json.loads(bad.stdout)
    assert set(payload) == {"command", "config", "error", "status"}
    assert payload["command"] == "compile explain"
    assert str(profile) in payload["error"]

    cfg = _non_mapping_config(tmp_path)
    flat = runner.invoke(app, ["validate", "compile", str(cfg), "--json"])
    payload = _json.loads(flat.stdout)
    assert set(payload) == {"command", "config", "error", "status"}
    assert payload["command"] == "compile explain"
    assert str(cfg) in payload["config"] and str(cfg) in payload["error"]
