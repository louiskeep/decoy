"""End-to-end tests for `decoy validate` and the `--version` flag."""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy import __version__
from decoy.__main__ import app

runner = CliRunner()


def _valid_mask_config(tmp_path: Path) -> dict:
    return {
        "global_settings": {"seed": 42},
        "input": {
            "type": "csv",
            "path": str(tmp_path / "in.csv"),
            "csv_options": {"delimiter": ",", "encoding": "utf-8"},
        },
        "output": {
            "type": "csv",
            "path": str(tmp_path / "out.csv"),
            "csv_options": {"delimiter": ",", "encoding": "utf-8"},
        },
        "masking_rules": [
            {"column": "name", "type": "faker", "faker_type": "name"},
        ],
    }


def test_version_flag_prints_version_and_exits():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "decoy" in result.stdout


def test_help_lists_validate_subcommand():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "validate" in result.stdout


def test_validate_passes_for_valid_config(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(_valid_mask_config(tmp_path)))

    result = runner.invoke(app, ["validate", str(config_path)])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_validate_fails_for_invalid_config(tmp_path: Path):
    config = _valid_mask_config(tmp_path)
    del config["input"]
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config))

    result = runner.invoke(app, ["validate", str(config_path)])
    assert result.exit_code == 1
    # error message goes to stderr; CliRunner mixes output by default
    assert "Invalid" in result.output or "Invalid" in result.stdout


def test_validate_fails_for_missing_file():
    result = runner.invoke(app, ["validate", "/nonexistent/path.yaml"])
    assert result.exit_code != 0


def test_validate_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["validate", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout
