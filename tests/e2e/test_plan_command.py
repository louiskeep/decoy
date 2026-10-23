"""End-to-end tests for the `decoy plan` behavior folded into
`decoy validate compile` (S2).

The top-level `decoy plan` command was removed; its artifact-writing behavior
now lives on `decoy validate compile --output` with `--profile` / `--no-profile`
selection and `--format yaml|json`. These tests cover: the --no-profile path,
the --profile path, --output (yaml + json) with an engine-readable round-trip,
mutually-exclusive flag rejection, the H1/H2 honesty guards, and the integration
with the planner's plan-compile checks.
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


def test_compile_help_includes_profile_flags() -> None:
    result = runner.invoke(app, ["validate", "compile", "--help"])
    assert result.exit_code == 0
    assert "--no-profile" in result.stdout
    assert "--profile" in result.stdout
    assert "--output" in result.stdout
    assert "--format" in result.stdout
    assert "Examples:" in result.stdout


# -- --no-profile artifact (--output) --------------------------------


def test_no_profile_output_writes_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    out_path = tmp_path / "plan.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app, ["validate", "compile", str(config_path), "--no-profile", "--output", str(out_path)]
    )
    assert result.exit_code == 0, result.output
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    # plan_version tracks the engine constant (2 after DPS Scope B's pinned
    # GenerationPlan payload bump; see decoy_engine.plan._compile.PLAN_VERSION).
    assert "plan_version: 2" in text
    # seed_protocol_version tracks the engine constant (7 after the FF1 adoption bump).
    assert "seed_protocol_version: 7" in text


def test_no_profile_output_engine_round_trips(tmp_path: Path) -> None:
    """The written artifact is engine-readable: plan_from_yaml round-trips it."""
    from decoy_engine.plan import plan_from_yaml

    config_path = tmp_path / "pipeline.yaml"
    out_path = tmp_path / "plan.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app, ["validate", "compile", str(config_path), "--output", str(out_path)]
    )
    assert result.exit_code == 0, result.output
    plan = plan_from_yaml(out_path.read_text(encoding="utf-8"))
    assert plan.plan_version == 2


def test_no_profile_output_json_format_round_trips(tmp_path: Path) -> None:
    """--format json writes a JSON artifact the engine can read back."""
    from decoy_engine.plan import plan_from_yaml

    config_path = tmp_path / "pipeline.yaml"
    out_path = tmp_path / "plan.json"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app,
        ["validate", "compile", str(config_path), "--output", str(out_path), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert doc["plan_version"] == 2
    # JSON is a YAML subset, so plan_from_yaml parses the same document.
    plan = plan_from_yaml(out_path.read_text(encoding="utf-8"))
    assert plan.plan_version == 2


def test_no_profile_records_skipped_checks(tmp_path: Path) -> None:
    """--no-profile records the engine's own honest skip set: the genuinely
    profile-dependent basic_uniqueness_pre_flight is SKIPPED, while the
    STRUCTURAL fk_plan_ordering stays in checks_passed (it needs no profile).
    The CLI no longer hand-labels fk_plan_ordering as skipped."""
    config_path = tmp_path / "pipeline.yaml"
    out_path = tmp_path / "plan.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app, ["validate", "compile", str(config_path), "--no-profile", "--output", str(out_path)]
    )
    assert result.exit_code == 0, result.output
    plan_doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    skipped = plan_doc["plan_compile"]["checks_skipped"]
    passed = plan_doc["plan_compile"]["checks_passed"]
    assert "basic_uniqueness_pre_flight" in skipped
    assert "fk_plan_ordering" not in skipped
    assert "fk_plan_ordering" in passed


def test_no_profile_strips_skipped_from_passed(tmp_path: Path) -> None:
    """H1: skipped checks must NOT also appear in checks_passed; a check
    cannot be claimed as both verified and skipped."""
    config_path = tmp_path / "pipeline.yaml"
    out_path = tmp_path / "plan.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app, ["validate", "compile", str(config_path), "--no-profile", "--output", str(out_path)]
    )
    assert result.exit_code == 0, result.output
    plan_doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    passed = set(plan_doc["plan_compile"]["checks_passed"])
    skipped = set(plan_doc["plan_compile"]["checks_skipped"])
    assert not (passed & skipped), (
        f"checks_passed and checks_skipped overlap: {passed & skipped!r}; "
        "a check can be in one list or the other, never both."
    )
    # The three remaining checks should be in passed.
    assert {
        "namespace_ambiguity",
        "unknown_provider",
        "composite_columns_length_match",
    } <= passed


def test_no_profile_json_envelope_reports_skipped(tmp_path: Path) -> None:
    """The standard --json envelope carries the engine's honest skip set:
    basic_uniqueness_pre_flight skipped, structural fk_plan_ordering passed."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(app, ["validate", "compile", str(config_path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    skipped = set(payload["compile_checks"]["skipped"])
    passed = set(payload["compile_checks"]["passed"])
    assert "basic_uniqueness_pre_flight" in skipped
    assert "fk_plan_ordering" in passed
    assert "fk_plan_ordering" not in skipped
    assert not (passed & skipped)


def test_no_profile_rejects_unique_cardinality_mode(tmp_path: Path) -> None:
    """H2 (Dennis slice 4-6 review): --no-profile is incompatible with
    cardinality_mode: unique because the pool-capacity pre-flight check
    cannot run without profile data; the runtime failure mode is severe."""
    config = {
        "global_settings": {"seed": 1},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "customer_id",
                        "strategy": "pool",
                        "provider": "uuid",
                        "backend_type": "pool",
                        "cardinality_mode": "unique",
                        "pool_size": 5,
                    }
                ],
            }
        ],
    }
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, config)

    result = runner.invoke(app, ["validate", "compile", str(config_path), "--no-profile"])
    assert result.exit_code == 1
    assert "cardinality_mode: unique" in result.output
    assert "tables.customers.columns.customer_id" in result.output
    assert "--profile" in result.output


def test_no_profile_accepts_non_unique_cardinality(tmp_path: Path) -> None:
    """Sanity-check H2 narrowness: cardinality_mode: reuse (or omitted) still
    works with --no-profile."""
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, _good_config())  # uses cardinality_mode: reuse

    result = runner.invoke(app, ["validate", "compile", str(config_path), "--no-profile"])
    assert result.exit_code == 0, result.output


# -- error paths ------------------------------------------------------


def test_mutually_exclusive_flags_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    profile_path = tmp_path / "profile.json"
    _write_yaml(config_path, _good_config())
    profile_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "validate",
            "compile",
            str(config_path),
            "--no-profile",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_rejects_unknown_provider(tmp_path: Path) -> None:
    """An unknown provider fires a plan-compile check; CLI exits 1
    with the typed error code on stderr."""
    config = _good_config()
    config["tables"][0]["columns"][0]["provider"] = "totally_fake_provider"
    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(config_path, config)

    result = runner.invoke(app, ["validate", "compile", str(config_path), "--no-profile"])
    assert result.exit_code == 1
    assert "unknown_provider" in result.output
    assert "totally_fake_provider" in result.output


def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    # Top-level YAML list, not a mapping.
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", "compile", str(config_path), "--no-profile"])
    assert result.exit_code == 1
    assert "mapping" in result.output or "error" in result.output.lower()


def test_with_invalid_profile_json(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    profile_path = tmp_path / "profile.json"
    _write_yaml(config_path, _good_config())
    profile_path.write_text("{not real json", encoding="utf-8")

    result = runner.invoke(
        app,
        ["validate", "compile", str(config_path), "--profile", str(profile_path)],
    )
    assert result.exit_code == 1
    assert "Profile JSON" in result.output


# -- --profile happy path --------------------------------------------


def test_with_valid_profile_json_runs_all_checks(tmp_path: Path) -> None:
    """A pre-computed Profile JSON loads + drives compile_plan; the
    profile-dependent checks run (not skipped)."""
    from datetime import datetime

    from decoy_engine.profile import Profile, profile_to_json

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
    out_path = tmp_path / "plan.yaml"
    _write_yaml(config_path, _good_config())

    result = runner.invoke(
        app,
        ["validate", "compile", str(config_path), "--profile", str(profile_path),
         "--output", str(out_path)],
    )
    assert result.exit_code == 0, result.output
    plan_doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    # All checks should pass when a real profile is loaded; no skipped checks.
    assert plan_doc["plan_compile"]["checks_skipped"] == []
    assert "basic_uniqueness_pre_flight" in plan_doc["plan_compile"]["checks_passed"]


def test_profile_json_envelope_reports_no_skipped(tmp_path: Path) -> None:
    """F8: with --profile the profile-dependent checks run, so the --json
    envelope reports an empty checks_skipped and basic_uniqueness in passed."""
    from datetime import datetime

    from decoy_engine.profile import Profile, profile_to_json

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
        app, ["validate", "compile", str(config_path), "--profile", str(profile_path), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["compile_checks"]["skipped"] == []
    assert "basic_uniqueness_pre_flight" in payload["compile_checks"]["passed"]


# -- determinism ------------------------------------------------------


def test_two_artifact_writes_byte_identical(tmp_path: Path) -> None:
    """Determinism contract: same input -> byte-identical artifact."""
    config_path = tmp_path / "pipeline.yaml"
    out1 = tmp_path / "plan1.yaml"
    out2 = tmp_path / "plan2.yaml"
    _write_yaml(config_path, _good_config())

    r1 = runner.invoke(app, ["validate", "compile", str(config_path), "--output", str(out1)])
    r2 = runner.invoke(app, ["validate", "compile", str(config_path), "--output", str(out2)])
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


# -- deletions: top-level commands are gone ---------------------------


def test_top_level_plan_is_gone() -> None:
    result = runner.invoke(app, ["plan", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_top_level_compile_is_gone() -> None:
    result = runner.invoke(app, ["compile", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_top_level_preflight_is_gone() -> None:
    result = runner.invoke(app, ["preflight", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_replan_command_is_gone() -> None:
    """Regression: `replan` was removed; the command must no longer exist."""
    result = runner.invoke(app, ["replan", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output
