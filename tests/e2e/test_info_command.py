"""End-to-end tests for `decoy info` and the banner."""

from __future__ import annotations

import json as _json

from typer.testing import CliRunner

from decoy import __version__
from decoy.__main__ import app


runner = CliRunner()


def test_info_help_includes_examples():
    result = runner.invoke(app, ["info", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_info_default_renders_banner_with_version_and_quickstart():
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    # Quick-start hints surfaced from the banner.
    assert "decoy storm scan" in result.stdout
    assert "decoy demo" in result.stdout
    assert "decoy templates list" in result.stdout


def test_info_json_emits_metadata():
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "info"
    assert payload["version"] == __version__
    assert payload["topics"]
    assert payload["templates"]


def test_info_quiet_produces_empty_stdout():
    result = runner.invoke(app, ["info", "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_root_help_advertises_new_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("explain", "info", "templates"):
        assert cmd in result.stdout, f"--help missing {cmd}"
