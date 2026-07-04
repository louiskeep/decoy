"""Unit tests for `decoy validate distribution` (BF1, Sprint 5).

Covers the CLI-side logic that is NOT already exercised end to end by
tests/e2e/test_validate_distribution_e2e.py: flag validation, --joint spec
parsing, the --min-grade/--min-score shorthand translation, the
--config -> strategy_map flattening helper, and -- the headline assertion
for this slice -- that the CLI computes NO fidelity metric itself. It is a
thin surface over `decoy_engine.quality.compute_quality_report` +
`apply_quality_policy`; this file spies on both to prove it.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_USAGE
from decoy.cli.validate import _GRADE_MIN_SCORE, _build_strategy_map

runner = CliRunner()


def _write_pair(tmp_path: Path, src_rows: dict, out_rows: dict) -> tuple[Path, Path]:
    src = tmp_path / "source.csv"
    out = tmp_path / "output.csv"
    pd.DataFrame(src_rows).to_csv(src, index=False)
    pd.DataFrame(out_rows).to_csv(out, index=False)
    return src, out


# ---------------------------------------------------------------------------
# Acceptance 6: no CLI-side metric -- the CLI calls the engine, not its own math.
# ---------------------------------------------------------------------------


def test_distribution_calls_engine_compute_quality_report(tmp_path: Path):
    """The command must call decoy_engine.quality.compute_quality_report and
    apply_quality_policy; it must not compute a fidelity number itself."""
    src, out = _write_pair(tmp_path, {"a": [1, 2, 3]}, {"a": [1, 2, 3]})

    import decoy_engine.quality as eq

    real_report = eq.compute_quality_report
    real_policy = eq.apply_quality_policy

    with (
        mock.patch.object(eq, "compute_quality_report", wraps=real_report) as spy_report,
        mock.patch.object(eq, "apply_quality_policy", wraps=real_policy) as spy_policy,
    ):
        result = runner.invoke(app, ["validate", "distribution", str(src), str(out), "--json"])

    assert result.exit_code == 0, result.output
    assert spy_report.call_count == 1, "validate distribution must call compute_quality_report exactly once"
    assert spy_policy.call_count == 1, "validate distribution must call apply_quality_policy exactly once"

    payload = _json.loads(result.output)
    assert payload["schema_version"] == "quality-report/v1"
    assert "policy" in payload
    assert payload["policy"]["schema_version"] == "quality-policy/v1"


def test_distribution_expect_row_parity_true_by_default(tmp_path: Path):
    """Default (no --generate) calls compute_quality_report with
    expect_row_parity=True (mask semantics)."""
    src, out = _write_pair(tmp_path, {"a": [1, 2, 3]}, {"a": [1, 2, 3]})

    import decoy_engine.quality as eq

    with mock.patch.object(eq, "compute_quality_report", wraps=eq.compute_quality_report) as spy:
        result = runner.invoke(app, ["validate", "distribution", str(src), str(out), "--json"])

    assert result.exit_code == 0, result.output
    _, kwargs = spy.call_args
    assert kwargs["expect_row_parity"] is True


def test_distribution_generate_flag_sets_expect_row_parity_false(tmp_path: Path):
    """--generate flips expect_row_parity=False (Slice 1 acceptance 2)."""
    src, out = _write_pair(tmp_path, {"a": [1, 2, 3, 4]}, {"a": [1, 2]})

    import decoy_engine.quality as eq

    with mock.patch.object(eq, "compute_quality_report", wraps=eq.compute_quality_report) as spy:
        result = runner.invoke(
            app, ["validate", "distribution", str(src), str(out), "--generate", "--json"]
        )

    assert result.exit_code == 0, result.output
    _, kwargs = spy.call_args
    assert kwargs["expect_row_parity"] is False
    payload = _json.loads(result.output)
    row_count_check = next(
        c for c in payload["diagnostic"]["checks"] if c["check"] == "row_count"
    )
    assert row_count_check["passed"] is True, (
        "row-count mismatch must not be flagged when --generate is set"
    )


# ---------------------------------------------------------------------------
# --joint parsing (ported from fit.py's --joint parser, D4).
# ---------------------------------------------------------------------------


def test_distribution_joint_bad_spec_exits_usage(tmp_path: Path):
    src, out = _write_pair(tmp_path, {"a": [1], "b": [2]}, {"a": [1], "b": [2]})
    result = runner.invoke(
        app, ["validate", "distribution", str(src), str(out), "--joint", "onlyone"]
    )
    assert result.exit_code == EXIT_USAGE


def test_distribution_joint_produces_pairwise_block(tmp_path: Path):
    """Slice 1 acceptance 4: --joint state,tier produces a pairwise block."""
    src, out = _write_pair(
        tmp_path,
        {"state": ["CA", "NY"] * 5, "tier": ["gold", "silver"] * 5},
        {"state": ["CA", "NY"] * 5, "tier": ["gold", "silver"] * 5},
    )
    result = runner.invoke(
        app,
        ["validate", "distribution", str(src), str(out), "--joint", "state,tier", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)
    joints = payload["pairwise"]["joints"]
    assert len(joints) == 1
    assert joints[0]["columns"] == ["state", "tier"]


# ---------------------------------------------------------------------------
# --mode / --min-grade / --min-score flag validation and translation.
# ---------------------------------------------------------------------------


def test_distribution_bad_mode_exits_usage(tmp_path: Path):
    src, out = _write_pair(tmp_path, {"a": [1]}, {"a": [1]})
    result = runner.invoke(
        app, ["validate", "distribution", str(src), str(out), "--mode", "bogus"]
    )
    assert result.exit_code == EXIT_USAGE


def test_distribution_bad_min_grade_exits_usage(tmp_path: Path):
    src, out = _write_pair(tmp_path, {"a": [1]}, {"a": [1]})
    result = runner.invoke(
        app, ["validate", "distribution", str(src), str(out), "--min-grade", "Z"]
    )
    assert result.exit_code == EXIT_USAGE


def test_distribution_min_grade_and_min_score_together_exits_usage(tmp_path: Path):
    src, out = _write_pair(tmp_path, {"a": [1]}, {"a": [1]})
    result = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--min-grade",
            "B",
            "--min-score",
            "0.5",
        ],
    )
    assert result.exit_code == EXIT_USAGE


@pytest.mark.parametrize("grade,expected", sorted(_GRADE_MIN_SCORE.items()))
def test_min_grade_translates_to_engine_grade_thresholds(grade, expected):
    """The CLI's grade->score table must match the engine's own thresholds
    (decoy_engine.quality.report._GRADE_THRESHOLDS) exactly, or --min-grade
    would silently gate at the wrong score."""
    assert _GRADE_MIN_SCORE[grade] == expected


def test_distribution_mode_fail_with_drift_exits_findings(tmp_path: Path):
    """Slice 1 acceptance 3: --mode fail on drifted output exits EXIT_FINDINGS
    (not EXIT_RUNTIME -- see the module docstring for the deviation rationale:
    this mirrors `decoy storm integrity`'s data-audit exit-code contract)."""
    src, out = _write_pair(
        tmp_path,
        {"a": list(range(50))},
        {"a": [999] * 50},
    )
    result = runner.invoke(
        app,
        ["validate", "distribution", str(src), str(out), "--mode", "fail", "--min-grade", "B"],
    )
    assert result.exit_code == EXIT_FINDINGS, result.output


def test_distribution_mode_report_never_fails_even_with_drift(tmp_path: Path):
    """Slice 1 acceptance 3: --mode report records the violation but the
    verdict stays 'pass' and the exit code stays 0."""
    src, out = _write_pair(
        tmp_path,
        {"a": list(range(50))},
        {"a": [999] * 50},
    )
    result = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--mode",
            "report",
            "--min-grade",
            "B",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)
    assert payload["policy"]["verdict"] == "pass"
    assert payload["policy"]["violations"], "report mode should still record the violation"


def test_distribution_fail_on_warning_promotes_warn_to_nonzero(tmp_path: Path):
    src, out = _write_pair(
        tmp_path,
        {"a": list(range(50))},
        {"a": [999] * 50},
    )
    warn_result = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--mode",
            "warn",
            "--min-grade",
            "B",
        ],
    )
    assert warn_result.exit_code == 0

    fail_on_warning_result = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--mode",
            "warn",
            "--min-grade",
            "B",
            "--fail-on-warning",
        ],
    )
    assert fail_on_warning_result.exit_code == EXIT_FINDINGS


# ---------------------------------------------------------------------------
# --config -> strategy_map (intentional-loss path, Slice 1 acceptance 1).
# ---------------------------------------------------------------------------


def test_build_strategy_map_flattens_mask_and_generate_columns():
    config_dict = {
        "tables": [
            {
                "name": "t1",
                "columns": [{"name": "email", "strategy": "hash"}],
                "generate_columns": [{"name": "synthetic_id"}],
            },
            {
                "name": "t2",
                "columns": [{"name": "ssn", "strategy": "fpe"}],
            },
        ],
    }
    strategy_map = _build_strategy_map(config_dict)
    assert strategy_map == {
        "email": "hash",
        "synthetic_id": "generate",
        "ssn": "fpe",
    }


def test_distribution_config_prevents_intentional_loss_from_flagging(tmp_path: Path):
    """Slice 1 acceptance 1: a --config naming a hash column keeps that
    column's low value-identity similarity from being raised as accidental
    drift under a strict policy."""
    src = tmp_path / "source.csv"
    out = tmp_path / "output.csv"
    pd.DataFrame({"email": [f"user{i}@example.com" for i in range(50)]}).to_csv(src, index=False)
    # A hashed column looks totally disjoint from the source under
    # value-identity TVD (this is exactly the D5a-corrected 0.05 default
    # expectation for "hash" in decoy_engine.quality.policy).
    pd.DataFrame({"email": [f"hash_{i:064x}" for i in range(50)]}).to_csv(out, index=False)

    cfg = {
        "version": 1,
        "global_settings": {"seed": 1},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "t", "columns": [{"name": "email", "strategy": "hash"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(out)}},
    }
    cfg_path = tmp_path / "pipeline.yaml"
    cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

    # Without --config: apply_quality_policy has no strategy_map, so it
    # cannot resolve a per-column expectation for "email" at all -- no
    # per-column ("check": "column") violation can fire either way. The
    # point of --config is what happens WITH a strategy_map: the per-column
    # check must use the strategy's own (low, D5a-corrected) expectation
    # instead of a generic high bar, so it does not flag intentional loss.
    with_config = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--config",
            str(cfg_path),
            "--mode",
            "fail",
            "--json",
        ],
    )
    payload = _json.loads(with_config.output)
    column_violations = [
        v for v in payload["policy"]["violations"] if v["check"] == "column"
    ]
    assert not column_violations, (
        "a --config naming the hash strategy must not raise the hashed "
        f"column's low value-identity similarity as accidental drift: {column_violations}"
    )


# ---------------------------------------------------------------------------
# CSV read errors -> EXIT_USAGE (mirrors fit.py's read/error handling).
# ---------------------------------------------------------------------------


def test_distribution_missing_source_exits_usage(tmp_path: Path):
    out = tmp_path / "output.csv"
    pd.DataFrame({"a": [1]}).to_csv(out, index=False)
    result = runner.invoke(
        app, ["validate", "distribution", str(tmp_path / "nope.csv"), str(out)]
    )
    assert result.exit_code != 0


def test_distribution_report_out_writes_json(tmp_path: Path):
    src, out = _write_pair(tmp_path, {"a": [1, 2, 3]}, {"a": [1, 2, 3]})
    report_out = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--report-out",
            str(report_out),
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    written = _json.loads(report_out.read_text(encoding="utf-8"))
    assert written["schema_version"] == "quality-report/v1"
    assert written["policy"]["schema_version"] == "quality-policy/v1"
