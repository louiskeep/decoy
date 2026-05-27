"""End-to-end tests for `decoy plan` and `decoy replan`.

Covers: --no-profile path, --profile path, --json, --out, mutually-
exclusive flag rejection, the deferred fully-automatic path's clear
error, replan stub error, and the integration with the planner's five
S1 plan-compile checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _good_config() -> dict:
    """Minimal config that compiles cleanly when --no-profile is used."""
    return {
        "global_settings": {"seed": 7},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker_email",
                        "provider": "person_email",
                        "backend_type": "faker",
                        "backend_version": "stub-0",
                        "cardinality_mode": "reuse",
                    }
                ],
            }
        ],
    }


# -- help -------------------------------------------------------------


def test_plan_help_includes_examples() -> None:
    result = runner.invoke(app, ["plan", "--help"])
    assert result.exit_code == 0
    assert "--no-profile" in result.stdout
    assert "--profile" in result.stdout
    assert "Examples:" in result.stdout


def test_replan_help_documents_s1_stub() -> None:
    result = runner.invoke(app, ["replan", "--help"])
    assert result.exit_code == 0
    assert "S1 stub" in result.stdout
    assert "--from" in result.stdout


# -- --no-profile happy path -----------------------------------------


def test_plan_no_profile_emits_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(app, ["plan", str(config_path), "--no-profile"])
    assert result.exit_code == 0, result.stdout
    assert "plan_version: 1" in result.stdout
    assert "seed_protocol_version: 0" in result.stdout


def test_plan_no_profile_records_skipped_check(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(app, ["plan", str(config_path), "--no-profile"])
    assert result.exit_code == 0, result.stdout
    plan_doc = yaml.safe_load(result.stdout)
    assert "basic_uniqueness_pre_flight" in plan_doc["plan_compile"]["checks_skipped"]


def test_plan_no_profile_warns_on_stderr(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app,
        ["plan", str(config_path), "--no-profile"],
    )
    assert result.exit_code == 0
    assert "WARNING" in result.stderr
    assert "basic_uniqueness_pre_flight" in result.stderr


# -- --json output ----------------------------------------------------


def test_plan_json_emits_parseable_json(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(app, ["plan", str(config_path), "--no-profile", "--json"])
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["plan_version"] == 1
    assert parsed["seed_protocol_version"] == 0


# -- --out writes to file --------------------------------------------


def test_plan_out_writes_to_file(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    out_path = tmp_path / "plan.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app, ["plan", str(config_path), "--no-profile", "--out", str(out_path)]
    )
    assert result.exit_code == 0, result.stdout
    assert out_path.exists()
    assert "plan_version: 1" in out_path.read_text(encoding="utf-8")
    # stdout should be silent when --out is used (verify no plan dump on stdout)
    assert "plan_version" not in result.stdout


# -- error paths ------------------------------------------------------


def test_plan_no_flags_points_at_deferred_slice(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app,
        ["plan", str(config_path)],
    )
    assert result.exit_code == 1
    assert "profile_source orchestration" in result.stderr
    assert "--no-profile" in result.stderr or "--profile" in result.stderr


def test_plan_mutually_exclusive_flags_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    profile_path = tmp_path / "profile.json"
    _write_yaml(config_path, _good_config())
    profile_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "plan",
            str(config_path),
            "--no-profile",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


def test_plan_rejects_unknown_provider(tmp_path: Path) -> None:
    """An unknown provider fires the S1 plan-compile check; CLI exits 1
    with the typed error code on stderr."""
    config = _good_config()
    config["tables"][0]["columns"][0]["provider"] = "totally_fake_provider"
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, config)

    result = runner.invoke(app, ["plan", str(config_path), "--no-profile"])
    assert result.exit_code == 1
    assert "unknown_provider" in result.stderr
    assert "totally_fake_provider" in result.stderr


def test_plan_rejects_malformed_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    # Top-level YAML list, not a mapping.
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    result = runner.invoke(app, ["plan", str(config_path), "--no-profile"])
    assert result.exit_code == 1
    assert "mapping" in result.stderr or "ERROR" in result.stderr


def test_plan_with_invalid_profile_json(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    profile_path = tmp_path / "profile.json"
    _write_yaml(config_path, _good_config())
    profile_path.write_text("{not real json", encoding="utf-8")

    result = runner.invoke(
        app,
        ["plan", str(config_path), "--profile", str(profile_path)],
    )
    assert result.exit_code == 1
    assert "Profile JSON" in result.stderr


# -- --profile happy path --------------------------------------------


def test_plan_with_valid_profile_json(tmp_path: Path) -> None:
    """A pre-computed Profile JSON loads + drives compile_plan."""
    from datetime import datetime

    from decoy_engine.profile import Profile, profile_to_json

    # Build a minimal but valid Profile, write it as JSON, then have the CLI consume it.
    profile = Profile(
        schema_version=1,
        tables=(),
        relationships=(),
        profiled_at=datetime(2026, 5, 27, 0, 0, 0),
        decoy_engine_version="0.1.0",
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile_to_json(profile), encoding="utf-8")

    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app, ["plan", str(config_path), "--profile", str(profile_path)]
    )
    assert result.exit_code == 0, result.stdout
    plan_doc = yaml.safe_load(result.stdout)
    # All five checks should pass when a real profile is loaded; no skipped checks.
    assert plan_doc["plan_compile"]["checks_skipped"] == []
    assert "basic_uniqueness_pre_flight" in plan_doc["plan_compile"]["checks_passed"]


# -- determinism ------------------------------------------------------


def test_plan_two_invocations_byte_identical(tmp_path: Path) -> None:
    """S1 determinism contract: same input -> byte-identical output."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result1 = runner.invoke(app, ["plan", str(config_path), "--no-profile"])
    result2 = runner.invoke(app, ["plan", str(config_path), "--no-profile"])
    assert result1.exit_code == 0
    assert result2.exit_code == 0
    assert result1.stdout == result2.stdout


# -- replan stub ------------------------------------------------------


def test_replan_errors_with_stub_pointer(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"placeholder": true}', encoding="utf-8")

    result = runner.invoke(app, ["replan", "--from", str(manifest_path)])
    assert result.exit_code == 1
    assert "S1 stub" in result.stderr
    assert "slice 7" in result.stderr or "plan-as-manifest" in result.stderr


def test_replan_requires_from_flag() -> None:
    result = runner.invoke(app, ["replan"])
    # Typer's missing-required-option behavior: exit 2 with usage message.
    assert result.exit_code != 0
