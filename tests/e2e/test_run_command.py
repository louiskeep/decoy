"""End-to-end tests for `decoy run`.

Uses Typer's CliRunner so the CLI is invoked exactly like a real user
would invoke it, but in-process (no subprocess). Each test writes a
self-contained YAML config + input CSV into a tmp dir.
"""

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "first_name": ["Alice", "Bob", "Carol"],
            "email": ["a@example.com", "b@example.com", "c@example.com"],
            "ssn": ["111-22-3333", "444-55-6666", "777-88-9999"],
        }
    ).to_csv(path, index=False)
    return path


@pytest.fixture
def mask_config(tmp_path: Path, sample_csv: Path) -> Path:
    config = {
        "global_settings": {"seed": 42},
        "input": {
            "type": "csv",
            "path": str(sample_csv),
            "csv_options": {"delimiter": ",", "encoding": "utf-8"},
        },
        "output": {
            "type": "csv",
            "path": str(tmp_path / "masked.csv"),
            "csv_options": {"delimiter": ",", "encoding": "utf-8"},
        },
        "mappings": {"store_directory": str(tmp_path / "mappings")},
        "logging": {"level": "info", "file": str(tmp_path / "run.log")},
        "masking_rules": [
            {"column": "customer_id", "type": "passthrough"},
            {"column": "first_name", "type": "faker", "faker_type": "first_name"},
            {"column": "email", "type": "faker", "faker_type": "email"},
            {"column": "ssn", "type": "hash"},
        ],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


def test_help_shows_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout


def test_run_help_shows_options():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.stdout
    assert "--verbose" in result.stdout


def test_run_mask_produces_masked_output(mask_config: Path, tmp_path: Path):
    output_path = tmp_path / "masked.csv"

    result = runner.invoke(app, ["run", str(mask_config), "--mode", "mask"])

    assert result.exit_code == 0, result.stdout
    assert output_path.exists()
    assert not (tmp_path / "mappings").exists()

    masked = pd.read_csv(output_path)
    # customer_id is passthrough, must be unchanged
    assert masked["customer_id"].tolist() == ["C1", "C2", "C3"]
    # first_name and email are faker-replaced â€” must differ from originals
    assert masked["first_name"].tolist() != ["Alice", "Bob", "Carol"]
    # ssn is hashed â€” must not match originals
    assert masked["ssn"].tolist() != ["111-22-3333", "444-55-6666", "777-88-9999"]


def test_run_with_missing_config_fails():
    result = runner.invoke(app, ["run", "/nonexistent/path.yaml"])
    assert result.exit_code != 0


def test_run_with_invalid_mode_fails(mask_config: Path):
    result = runner.invoke(app, ["run", str(mask_config), "--mode", "bogus"])
    assert result.exit_code != 0


def test_run_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_root_help_advertises_completion_install():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.stdout


@pytest.fixture
def graph_config(tmp_path: Path, sample_csv: Path) -> Path:
    out_csv = tmp_path / "graph_out.csv"
    config = {
        "mode": "graph",
        "nodes": [
            {"id": "src", "kind": "source.file", "config": {"path": str(sample_csv)}},
            {"id": "drop", "kind": "drop_column", "config": {"columns": ["ssn"]}},
            {"id": "out", "kind": "target.file", "config": {"output_filename": str(out_csv)}},
        ],
        "edges": [
            {"from": "src", "to": "drop"},
            {"from": "drop", "to": "out"},
        ],
    }
    p = tmp_path / "graph.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    return p


def test_run_graph_pipeline(graph_config: Path, tmp_path: Path):
    """`decoy run` on a mode: graph YAML dispatches to run_graph."""
    result = runner.invoke(app, ["run", str(graph_config)])
    assert result.exit_code == 0, result.stdout
    out_csv = tmp_path / "graph_out.csv"
    assert out_csv.exists()
    written = pd.read_csv(out_csv)
    assert "ssn" not in written.columns
    assert len(written) == 3


def test_run_bad_graph_fails(tmp_path: Path):
    bad = {
        "mode": "graph",
        "nodes": [
            {"id": "a", "kind": "drop_column", "config": {"columns": ["x"]}},
            {"id": "b", "kind": "drop_column", "config": {"columns": ["y"]}},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.dump(bad), encoding="utf-8")
    result = runner.invoke(app, ["run", str(p)])
    assert result.exit_code != 0
