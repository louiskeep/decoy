"""End-to-end exercise of `decoy validate distribution` (BF1, Sprint 5).

Command-surface tests: real CSVs on disk, invoked through the built `decoy`
Typer app exactly as a user would. Unit-level logic (flag validation,
--config strategy_map flattening, the compute_quality_report spy) lives in
tests/unit/test_validate_distribution.py.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS

runner = CliRunner()


def test_validate_distribution_help_includes_examples_and_see_also():
    result = runner.invoke(app, ["validate", "distribution", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.output
    assert "See also:" in result.output


def test_validate_distribution_identical_frames_grade_a(tmp_path: Path):
    src = tmp_path / "source.csv"
    out = tmp_path / "output.csv"
    pd.DataFrame({"id": range(100), "tier": ["gold", "silver"] * 50}).to_csv(src, index=False)
    pd.DataFrame({"id": range(100), "tier": ["gold", "silver"] * 50}).to_csv(out, index=False)

    result = runner.invoke(app, ["validate", "distribution", str(src), str(out)])
    assert result.exit_code == 0, result.output
    assert "grade A" in result.output


def test_validate_distribution_json_envelope_has_command_and_status(tmp_path: Path):
    src = tmp_path / "source.csv"
    out = tmp_path / "output.csv"
    pd.DataFrame({"id": range(20)}).to_csv(src, index=False)
    pd.DataFrame({"id": range(20)}).to_csv(out, index=False)

    result = runner.invoke(app, ["validate", "distribution", str(src), str(out), "--json"])
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    assert payload["command"] == "validate distribution"
    assert payload["status"] == "ok"
    assert payload["schema_version"] == "quality-report/v1"


def test_validate_distribution_drifted_output_fails_hard_gate(tmp_path: Path):
    src = tmp_path / "source.csv"
    out = tmp_path / "output.csv"
    pd.DataFrame({"amount": list(range(200))}).to_csv(src, index=False)
    pd.DataFrame({"amount": [1] * 200}).to_csv(out, index=False)

    result = runner.invoke(
        app,
        [
            "validate",
            "distribution",
            str(src),
            str(out),
            "--mode",
            "fail",
            "--min-grade",
            "C",
        ],
    )
    assert result.exit_code == EXIT_FINDINGS, result.output


def test_validate_distribution_generate_allows_row_count_mismatch(tmp_path: Path):
    src = tmp_path / "source.csv"
    out = tmp_path / "synthetic.csv"
    pd.DataFrame({"tier": ["gold", "silver"] * 100}).to_csv(src, index=False)
    pd.DataFrame({"tier": ["gold", "silver"] * 10}).to_csv(out, index=False)

    result = runner.invoke(
        app, ["validate", "distribution", str(src), str(out), "--generate", "--json"]
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    row_count_check = next(
        c for c in payload["diagnostic"]["checks"] if c["check"] == "row_count"
    )
    assert row_count_check["passed"] is True


def test_validate_distribution_missing_output_file_exits_nonzero(tmp_path: Path):
    src = tmp_path / "source.csv"
    pd.DataFrame({"a": [1]}).to_csv(src, index=False)
    result = runner.invoke(
        app, ["validate", "distribution", str(src), str(tmp_path / "does_not_exist.csv")]
    )
    assert result.exit_code != 0
