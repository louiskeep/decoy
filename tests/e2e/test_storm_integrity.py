"""End-to-end tests for `decoy storm integrity` (OSS.4b, 2026-06-02).

The CLI verb wraps `decoy_engine.storm.postmask.run_storm_post_mask` and
returns the same JobStormReport-shaped payload the platform persists
when a mask job declared `run_storm: true`. These cells pin the wire
shape + the exit-code contract + the deprecation-free help body.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_USAGE

runner = CliRunner()


@pytest.fixture
def clean_pair(tmp_path: Path) -> tuple[Path, Path]:
    """A source + masked pair where the masked output looks PII-free.

    Email column is masked to plausible-but-synthetic addresses;
    customer_id is preserved verbatim (acts as the FK key under any
    declared relationship). With no `--config` the runner reports
    zero fail/error findings; residual_pii may flag low-severity
    detector matches on the synthetic addresses but those land as
    warning severity, not fail.
    """
    src = tmp_path / "src.csv"
    masked = tmp_path / "masked.csv"
    pd.DataFrame(
        {
            "customer_id": ["1", "2", "3"],
            "email": ["alice@example.com", "bob@example.com", "carol@example.com"],
        }
    ).to_csv(src, index=False)
    pd.DataFrame(
        {
            "customer_id": ["1", "2", "3"],
            "email": ["fake1@redacted.test", "fake2@redacted.test", "fake3@redacted.test"],
        }
    ).to_csv(masked, index=False)
    return src, masked


def test_integrity_help_includes_examples():
    """The `--help` body advertises the four invocation examples plus
    the exit-code contract."""
    result = runner.invoke(app, ["storm", "integrity", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "Exit codes:" in result.stdout
    assert "EXIT_FINDINGS" in result.stdout
    assert "See also:" in result.stdout


def test_integrity_clean_pair_exits_zero(clean_pair: tuple[Path, Path]):
    """A reasonably-masked file with no fail/error findings exits 0
    and reports `status: ok` in --json mode."""
    src, masked = clean_pair
    result = runner.invoke(
        app, ["storm", "integrity", str(masked), "--source", str(src), "--json"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm integrity"
    assert payload["status"] == "ok"
    assert "report" in payload
    report = payload["report"]
    assert "residual_pii" in report
    assert "fk_preservation" in report
    assert "policy_validation" in report
    assert "schema_version" in report
    # fail + error counts are zero on the clean path.
    assert report.get("fail_count", 0) == 0
    assert report.get("error_count", 0) == 0


def test_integrity_returns_jobstormreport_shape(clean_pair: tuple[Path, Path]):
    """The wire shape matches what the platform's JobStormReport.report_json
    column carries: schema_version + 3 finding lists + 4 severity counters
    + pass_failed_with + generated_at. Pin this so a future engine refactor
    can't silently change the public contract."""
    src, masked = clean_pair
    result = runner.invoke(
        app, ["storm", "integrity", str(masked), "--source", str(src), "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    report = payload["report"]
    expected = {
        "schema_version",
        "residual_pii",
        "fk_preservation",
        "policy_validation",
        "pass_count",
        "warning_count",
        "fail_count",
        "error_count",
        "pass_failed_with",
        "generated_at",
    }
    assert expected.issubset(set(report.keys())), (
        f"missing keys: {expected - set(report.keys())}"
    )


def test_integrity_writes_out_file(clean_pair: tuple[Path, Path], tmp_path: Path):
    """`--out <path>` writes the report JSON to disk; the report is
    valid JSON and matches the --json output's `report` key."""
    src, masked = clean_pair
    out_path = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "storm",
            "integrity",
            str(masked),
            "--source",
            str(src),
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    assert out_path.exists()
    data = _json.loads(out_path.read_text(encoding="utf-8"))
    assert "schema_version" in data
    assert "residual_pii" in data


def test_integrity_missing_source_exits_usage(tmp_path: Path):
    """A missing `--source` file is a usage error, not a runtime crash."""
    masked = tmp_path / "masked.csv"
    pd.DataFrame({"x": [1]}).to_csv(masked, index=False)
    result = runner.invoke(
        app,
        ["storm", "integrity", str(masked), "--source", str(tmp_path / "nope.csv")],
    )
    # Typer rejects nonexistent --source paths at the click parser layer
    # before the body runs; exit 2 is the click-canonical "usage error"
    # exit code that typer raises. Either way, NOT zero, and NOT
    # EXIT_FINDINGS, and NOT EXIT_RUNTIME.
    assert result.exit_code != 0
    assert result.exit_code != EXIT_FINDINGS


def test_integrity_quiet_suppresses_stdout(clean_pair: tuple[Path, Path]):
    """`--quiet` suppresses the Rich table. Exit code still carries the
    findings signal."""
    src, masked = clean_pair
    result = runner.invoke(
        app,
        ["storm", "integrity", str(masked), "--source", str(src), "--quiet"],
    )
    assert result.exit_code == 0
    assert result.stdout == ""
