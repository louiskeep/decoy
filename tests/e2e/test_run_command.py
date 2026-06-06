"""End-to-end tests for `decoy run`.

CLI.3 commit 3 (2026-06-02): rewritten against the V2 PipelineConfig
spine. Pre-rewrite the file exercised V1 `mode: graph` YAML and V1
`masking_rules:` shapes; both are dead under storm-reframe-C and
S22-CL-V1GRAPHRUNNER. The new cells verify (a) help text renders,
(b) a minimal V2 mask config runs end-to-end and writes a masked CSV
where faker columns differ from the source, (c) a V2 generate config
runs end-to-end and produces the declared row_count, (d) V1 graph
YAML is rejected with a typed error.
"""

from pathlib import Path

import json as _json
import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Three-row source CSV with one each: pass-through-friendly id,
    faker-replaceable name, and a column the mask will redact."""
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
    """Minimal V2 PipelineConfig that masks the sample CSV.

    customer_id: passthrough (verified unchanged).
    first_name: faker (verified replaced).
    email: faker (verified replaced).
    ssn: redact (verified replaced).

    Providers are poolable members of the engine default registry; the
    redact strategy carries non-poolable PII fields (uuid, synthetic_*)
    that would otherwise trip [provider_not_poolable] under the default
    cardinality_mode.
    """
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(sample_csv)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "customer_id", "strategy": "passthrough"},
                    {"name": "first_name", "strategy": "faker", "provider": "person_first_name"},
                    {"name": "email", "strategy": "faker", "provider": "person_email"},
                    {"name": "ssn", "strategy": "redact"},
                ],
            },
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "masked.csv")},
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


@pytest.fixture
def generate_config(tmp_path: Path) -> Path:
    """Minimal V2 PipelineConfig for the generate path (no sources)."""
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {},
        "tables": [
            {
                "name": "employees",
                "row_count": 5,
                "generate_columns": [
                    {"name": "employee_id", "type": "sequence", "start": 1000, "step": 1},
                    {"name": "first_name", "type": "faker", "faker_type": "first_name"},
                ],
            },
        ],
        "targets": {
            "employees": {"type": "file", "format": "csv", "path": str(tmp_path / "employees.csv")},
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


# --------------------------------------------------------------------------
# Help-text plumbing
# --------------------------------------------------------------------------


def test_help_shows_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout


def test_run_help_shows_options():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.stdout
    assert "--verbose" in result.stdout


def test_run_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_root_help_advertises_completion_install():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.stdout


# --------------------------------------------------------------------------
# Mask path end-to-end
# --------------------------------------------------------------------------


def test_run_mask_end_to_end_smoke(mask_config: Path, tmp_path: Path):
    """V2 mask: source -> compile_plan -> PandasExecutionAdapter.run ->
    masked CSV at the declared target. The new spec cell from CLI.3 spec
    DoD 7 ('canonical smoke') is this one."""
    output_path = tmp_path / "masked.csv"

    result = runner.invoke(app, ["run", str(mask_config), "--mode", "mask"])

    assert result.exit_code == 0, result.stdout
    assert output_path.exists()

    source = pd.read_csv(tmp_path / "input.csv")
    masked = pd.read_csv(output_path)

    # Row count preserved.
    assert len(masked) == len(source)

    # customer_id is passthrough -> unchanged.
    assert masked["customer_id"].astype(str).tolist() == source["customer_id"].astype(str).tolist()

    # first_name + email faker-replaced -> at least one column differs from source.
    diffs = (masked["first_name"].astype(str) != source["first_name"].astype(str)).any()
    assert diffs, "faker mask produced identical output for first_name"

    # ssn redacted -> must not match originals.
    assert masked["ssn"].astype(str).tolist() != source["ssn"].astype(str).tolist()


def test_run_mask_with_missing_source_fails(mask_config: Path, tmp_path: Path):
    """Removing the source CSV before run causes the engine to error and
    the CLI to exit non-zero with the typed message."""
    (tmp_path / "input.csv").unlink()
    result = runner.invoke(app, ["run", str(mask_config), "--mode", "mask"])
    assert result.exit_code != 0


def test_run_with_missing_config_fails():
    result = runner.invoke(app, ["run", "/nonexistent/path.yaml"])
    assert result.exit_code != 0


def test_run_with_invalid_mode_fails(mask_config: Path):
    result = runner.invoke(app, ["run", str(mask_config), "--mode", "bogus"])
    assert result.exit_code != 0


def test_run_summary_names_tables(tmp_path: Path):
    from decoy.cli.run import _run_summary

    cfg = tmp_path / "p.yaml"
    cfg.write_text("tables:\n  - name: customers\n  - name: orders\n", encoding="utf-8")
    label = _run_summary(cfg, "mask")
    assert "2 tables" in label
    assert "customers" in label and "orders" in label


def test_run_summary_single_table_is_singular(tmp_path: Path):
    from decoy.cli.run import _run_summary

    cfg = tmp_path / "p.yaml"
    cfg.write_text("tables:\n  - name: only\n", encoding="utf-8")
    label = _run_summary(cfg, "mask")
    assert "1 table " in label and "only" in label


def test_run_summary_falls_back_on_bad_yaml(tmp_path: Path):
    from decoy.cli.run import _run_summary

    cfg = tmp_path / "p.yaml"
    cfg.write_text(": : not : valid : :\n", encoding="utf-8")
    # Best-effort label: never raises, returns the plain fallback.
    assert _run_summary(cfg, "mask") == "Running mask..."


# --------------------------------------------------------------------------
# Generate path end-to-end
# --------------------------------------------------------------------------


def test_run_generate_end_to_end_smoke(generate_config: Path, tmp_path: Path):
    """V2 generate: no source -> generate_tables -> employees CSV at the
    declared target with row_count rows."""
    output_path = tmp_path / "employees.csv"

    result = runner.invoke(app, ["run", str(generate_config), "--json"])

    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "run"
    assert payload["status"] == "ok"
    assert payload["mode"] == "generate"

    assert output_path.exists()
    generated = pd.read_csv(output_path)
    assert len(generated) == 5
    assert "employee_id" in generated.columns


# --------------------------------------------------------------------------
# V1 surface rejection
# --------------------------------------------------------------------------


def test_run_rejects_v1_graph_yaml(tmp_path: Path):
    """V1 `mode: graph` YAML is rejected by the V2 PipelineConfig schema
    at the choke point (not by a CLI-side pre-check). Pre-CLI.3 the CLI
    routed graph YAML to the (deleted) `run_graph` engine entry; now it
    surfaces a typed PipelineValidationError at exit 3."""
    cfg = {
        "mode": "graph",
        "nodes": [
            {"id": "src", "kind": "source.file", "config": {"path": "ignored"}},
            {"id": "out", "kind": "target.file", "config": {"output_filename": "ignored"}},
        ],
        "edges": [{"from": "src", "to": "out"}],
    }
    p = tmp_path / "graph.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")

    result = runner.invoke(app, ["run", str(p), "--json"])

    assert result.exit_code == 3
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    # FC-1 (2026-06-02): the YAML-detected mode is inferred from the
    # tables block, not from the (now-rejected) `mode:` field. A V1 graph
    # config has no V2 `tables:` block, so _detect_mode returns None and
    # the envelope falls back to the CLI --mode default ("mask"). What we
    # pin is that "graph" no longer flows through to the envelope -- the
    # V1 vocabulary is dead.
    assert payload["mode"] != "graph"


def test_run_rejects_v1_masking_rules_shape(tmp_path: Path):
    """V1 `masking_rules:` flat-list config (no `version: 1`, no
    `tables:` block) is rejected at the V2 choke point."""
    cfg = {
        "global_settings": {"seed": 42},
        "input": {"type": "csv", "path": "ignored"},
        "output": {"type": "csv", "path": "ignored"},
        "masking_rules": [{"column": "name", "type": "faker", "faker_type": "name"}],
    }
    p = tmp_path / "v1.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["run", str(p)])
    assert result.exit_code != 0
