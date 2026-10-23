"""End-to-end tests for the S5 `decoy run` capability flags.

The four additive, default-off flags surface existing `run_pipeline` kwargs and
render from `ExecutionResult.quality_metrics`:

  --explain-plan          -> quality_metrics["execution_plan"] (the EXECUTION
                             ROUTE decision: mode/reason/rejections -- NOT the
                             per-column masking rationale `validate compile
                             --explain` gives pre-run).
  --fidelity              -> quality_metrics["fidelity_reports"] (quick inline
                             marginal check; never fails the run).
  --post-validate         -> quality_metrics["failed_checks"] + ["quality_summary"]
                             (validator results; warn-only, exit 0).
  --post-validate-enforce -> same, but a non-empty failed_checks exits
                             EXIT_FINDINGS(4). The engine never fails the job
                             (plan P1-2); the CLI does the mapping after the
                             outputs are written.

`--chunked` combined with any of the four is rejected EXIT_USAGE (the chunked
path returns no ExecutionResult -- plan P2-3). A default run (no new flags) is
unchanged (regression net).
"""

import json as _json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_USAGE

runner = CliRunner()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def clean_config(tmp_path: Path) -> Path:
    """A mask config whose output has no post-validation findings.

    passthrough/faker/redact -- none of these re-emit a source value, so the
    leakage scan does not fire and failed_checks stays empty.
    """
    src = tmp_path / "input.csv"
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "first_name": ["Alice", "Bob", "Carol"],
            "ssn": ["111-22-3333", "444-55-6666", "777-88-9999"],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "customer_id", "strategy": "passthrough"},
                    {"name": "first_name", "strategy": "faker", "provider": "person_first_name"},
                    {"name": "ssn", "strategy": "redact"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "clean.yaml"
    p.write_text(yaml.dump(cfg))
    return p


@pytest.fixture
def leaky_config(tmp_path: Path) -> Path:
    """A mask config whose output hard-fails the leakage scan.

    truncate is a substitution strategy; "AAAAA"[:3] == "AAA", a source value,
    so a source value reappears in the output -> the leakage scan hard-fails.
    Mirrors decoy-engine's `_leaky_config` (the leak is real on any engine).
    """
    src = tmp_path / "lin.csv"
    pd.DataFrame({"code": ["AAAAA", "AAA", "BBBBB"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "t",
                "columns": [
                    {
                        "name": "code",
                        "strategy": "truncate",
                        "provider": "person_email",
                        "namespace": "ns",
                        "provider_config": {"length": 3},
                    }
                ],
            }
        ],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "lout.csv")}},
    }
    p = tmp_path / "leaky.yaml"
    p.write_text(yaml.dump(cfg))
    return p


@pytest.fixture
def generate_config(tmp_path: Path) -> Path:
    """A pure-generate config (no sources) for the --explain-plan stamp test."""
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {},
        "tables": [
            {
                "name": "emp",
                "row_count": 5,
                "generate_columns": [{"name": "id", "type": "sequence", "start": 1, "step": 1}],
            }
        ],
        "targets": {"emp": {"type": "file", "format": "csv", "path": str(tmp_path / "emp.csv")}},
    }
    p = tmp_path / "gen.yaml"
    p.write_text(yaml.dump(cfg))
    return p


# --------------------------------------------------------------------------
# --explain-plan: the EXECUTION ROUTE decision (not a per-column rationale)
# --------------------------------------------------------------------------


def test_explain_plan_human_renders_execution_route(clean_config: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--explain-plan"])
    assert result.exit_code == 0, result.output
    # The route section renders, labeled "Execution route" (NOT "plan rationale").
    assert "Execution route" in result.stdout
    assert "Mode:" in result.stdout
    assert "Reason:" in result.stdout
    # It points per-column seekers at the pre-run compile path.
    assert "validate compile --explain" in result.stdout
    # It is NOT the per-column masking rationale `compile --explain` renders:
    # that renderer stamps each column "declared in pipeline config".
    assert "declared in pipeline config" not in result.stdout


def test_explain_plan_json_carries_execution_plan(clean_config: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--json", "--explain-plan"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    plan = payload["report"]["execution_plan"]
    # Route fields present...
    assert plan["mode"]
    assert plan["reason"]
    assert "rejections" in plan
    # ...and it is NOT a per-column rationale payload.
    assert "tables" not in plan
    assert "columns" not in plan


def test_pure_generate_explain_plan_stamps_nonempty_execution_plan(generate_config: Path):
    """A pure-GENERATE run still stamps a non-empty execution_plan (classify_job
    runs whenever explain_plan is set)."""
    result = runner.invoke(app, ["run", str(generate_config), "--json", "--explain-plan"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    plan = payload["report"]["execution_plan"]
    assert plan is not None
    assert plan["mode"], "execution_plan mode is empty for a pure-generate run"
    assert plan["reason"], "execution_plan reason is empty for a pure-generate run"


# --------------------------------------------------------------------------
# --fidelity: a quick inline check that never fails the run
# --------------------------------------------------------------------------


def test_fidelity_renders_section_and_does_not_fail_on_low_grade(leaky_config: Path):
    """The truncate leak drags marginal fidelity to a low grade; --fidelity
    renders a fidelity section and still exits 0 (report-only)."""
    result = runner.invoke(app, ["run", str(leaky_config), "--fidelity"])
    assert result.exit_code == 0, result.output
    assert "Fidelity" in result.stdout
    # Cross-links the fuller post-hoc grade.
    assert "report fidelity" in result.stdout


def test_fidelity_json_carries_fidelity_reports(clean_config: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--json", "--fidelity"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert "fidelity_reports" in payload["report"]
    # Per-mask-table block present for the one mask table.
    assert "customers" in (payload["report"]["fidelity_reports"] or {})


# --------------------------------------------------------------------------
# --post-validate: validator results, warn-only (exit 0)
# --------------------------------------------------------------------------


def test_post_validate_renders_findings_and_exits_zero(leaky_config: Path, tmp_path: Path):
    result = runner.invoke(app, ["run", str(leaky_config), "--post-validate"])
    assert result.exit_code == 0, result.output
    assert "Post-validation" in result.stdout
    # Output still written.
    assert (tmp_path / "lout.csv").exists()


def test_post_validate_json_carries_validator_results(leaky_config: Path):
    result = runner.invoke(app, ["run", str(leaky_config), "--json", "--post-validate"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    report = payload["report"]
    assert [c["code"] for c in report["failed_checks"]] == ["leakage"]
    assert report["quality_summary"] is not None


def test_post_validate_clean_reports_all_passed(clean_config: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--json", "--post-validate"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["report"]["failed_checks"] == []


# --------------------------------------------------------------------------
# --post-validate-enforce: EXIT_FINDINGS iff failed_checks is non-empty
# --------------------------------------------------------------------------


def test_post_validate_enforce_exits_findings_on_failure(leaky_config: Path, tmp_path: Path):
    result = runner.invoke(app, ["run", str(leaky_config), "--post-validate-enforce"])
    assert result.exit_code == EXIT_FINDINGS, result.output
    # Outputs stay written -- the mask succeeded; enforce only changes the code.
    assert (tmp_path / "lout.csv").exists()


def test_post_validate_enforce_exits_zero_when_all_pass(clean_config: Path, tmp_path: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--post-validate-enforce"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").exists()


def test_post_validate_enforce_json_envelope_on_findings(leaky_config: Path):
    result = runner.invoke(app, ["run", str(leaky_config), "--json", "--post-validate-enforce"])
    assert result.exit_code == EXIT_FINDINGS, result.output
    # The success envelope + report still emit before the findings exit.
    payload = _json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["report"]["post_validation_enforce"] is True
    assert [c["code"] for c in payload["report"]["failed_checks"]] == ["leakage"]


# --------------------------------------------------------------------------
# --chunked interaction: reject with any of the four flags (plan P2-3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag",
    ["--explain-plan", "--fidelity", "--post-validate", "--post-validate-enforce"],
)
def test_chunked_plus_report_flag_rejected_usage(clean_config: Path, flag: str, tmp_path: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--chunked", flag])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "--chunked" in result.stderr
    assert flag in result.stderr
    # Rejected up front -- no masked output written.
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# Regression net: a default run (no new flags) is unchanged
# --------------------------------------------------------------------------


def test_default_run_has_no_report_section(clean_config: Path, tmp_path: Path):
    result = runner.invoke(app, ["run", str(clean_config), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert "report" not in payload
    assert payload["status"] == "ok"
    assert (tmp_path / "out.csv").exists()


def test_default_run_human_unchanged(clean_config: Path):
    result = runner.invoke(app, ["run", str(clean_config)])
    assert result.exit_code == 0, result.output
    # None of the S5 section headers appear without their flags.
    assert "Execution route" not in result.stdout
    assert "Fidelity" not in result.stdout
    assert "Post-validation" not in result.stdout
