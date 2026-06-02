"""End-to-end tests for `decoy validate` and the `--version` flag.

CLI.2 commit 1 (2026-06-02): rewritten against the V2 PipelineConfig
choke point. Pre-rewrite the file exercised V1 graph YAML + V1
`masking_rules` shapes; both are dead under the V2 clean break (S22 /
storm-reframe-C) and the validator now hard-rejects them. The new
cells verify (a) a minimal valid V2 PipelineConfig passes, (b) V1
graph YAML exits 1 with a typed PipelineValidationError, (c) V1
`masking_rules` configs exit 1 (no `version: 1`), (d) malformed YAML
exits 1, (e) missing file exits 1, (f) `--help` and `--version` flags
remain functional.
"""

from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy import __version__
from decoy.__main__ import app

runner = CliRunner()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _valid_v2_mask_config(tmp_path: Path) -> dict:
    """Minimal V2 PipelineConfig that satisfies all required-field invariants:
    `version: 1`, `mode: mask`, at least one table (with at least one
    column or generate_column), at least one target. Pulled from the
    canonical golden-fixture shape at
    `decoy-engine/tests/integration/golden/test_execution_e2e.py`."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"customer_id": ["1", "2"], "name": ["a", "b"]}).to_csv(src, index=False)
    return {
        "version": 1,
        "mode": "mask",
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src)},
        },
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
                    },
                ],
            },
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")},
        },
    }


# --------------------------------------------------------------------------
# Flag plumbing (--version, --help)
# --------------------------------------------------------------------------


def test_version_flag_prints_version_and_exits():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "decoy" in result.stdout


def test_help_lists_validate_subcommand():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "validate" in result.stdout


def test_validate_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["validate", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


# --------------------------------------------------------------------------
# V2 PipelineConfig path: happy + rejected shapes
# --------------------------------------------------------------------------


def test_validate_passes_for_valid_v2_config(tmp_path: Path):
    """A minimal V2 PipelineConfig that satisfies every required field
    validates clean and exits 0 with 'OK' on stdout."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(_valid_v2_mask_config(tmp_path)))

    result = runner.invoke(app, ["validate", str(config_path)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.stdout


def test_validate_rejects_graph_mode_yaml(tmp_path: Path):
    """V1 `mode: graph` YAML exits 1 with a typed validation error. The
    V2 choke point (`PipelineConfig.model_validate`) rejects the legacy
    discriminator at the model layer; the CLI surfaces the typed error
    instead of the pre-CLI.2 `validate_graph` happy path."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"a": [1, 2]}).to_csv(src, index=False)
    cfg = {
        "mode": "graph",
        "nodes": [
            {"id": "s", "kind": "source.file", "config": {"path": str(src)}},
            {"id": "t", "kind": "target.file", "config": {"output_filename": str(tmp_path / "o.csv")}},
        ],
        "edges": [{"from": "s", "to": "t"}],
    }
    p = tmp_path / "graph.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 1, result.output


def test_validate_rejects_v1_mask_config(tmp_path: Path):
    """V1 `masking_rules` config (no `version: 1`, no `tables` block)
    exits 1. The V2 choke point treats it as a schema violation."""
    config = {
        "global_settings": {"seed": 42},
        "input": {"type": "csv", "path": str(tmp_path / "in.csv")},
        "output": {"type": "csv", "path": str(tmp_path / "out.csv")},
        "masking_rules": [
            {"column": "name", "type": "faker", "faker_type": "name"},
        ],
    }
    p = tmp_path / "v1.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 1


def test_validate_fails_for_invalid_v2_config(tmp_path: Path):
    """A V2 config missing required fields exits 1."""
    config = _valid_v2_mask_config(tmp_path)
    del config["tables"]  # tables is required (min_length=1)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config))

    result = runner.invoke(app, ["validate", str(config_path)])
    assert result.exit_code == 1
    assert "Invalid" in result.output or "Invalid" in result.stdout


def test_validate_fails_for_unparseable_yaml(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("{ unbalanced: [oops", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 1


def test_validate_fails_for_non_mapping_yaml(tmp_path: Path):
    """A YAML scalar (not a mapping) exits 1 with a typed error."""
    p = tmp_path / "scalar.yaml"
    p.write_text("just_a_string\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 1


def test_validate_fails_for_missing_file():
    result = runner.invoke(app, ["validate", "/nonexistent/path.yaml"])
    assert result.exit_code != 0


# --------------------------------------------------------------------------
# JSON envelope contract
# --------------------------------------------------------------------------


def test_validate_emits_json_envelope_on_success(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(_valid_v2_mask_config(tmp_path)))

    result = runner.invoke(app, ["validate", str(config_path), "--json"])
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.stdout)
    assert payload["command"] == "validate"
    assert payload["status"] == "ok"


def test_validate_emits_json_envelope_on_error(tmp_path: Path):
    cfg = {"mode": "graph", "nodes": [], "edges": []}
    p = tmp_path / "graph.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p), "--json"])
    assert result.exit_code == 1
    import json

    payload = json.loads(result.stdout)
    assert payload["command"] == "validate"
    assert payload["status"] == "error"
    assert "error" in payload
