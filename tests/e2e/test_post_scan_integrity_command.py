"""End-to-end tests for `decoy post-scan integrity`.

The CLI verb wraps `decoy_engine.verification.run_post_mask` and returns the
same `post-scan-integrity/v2` report-shaped payload a mask job produces when it
declares `post_scan.integrity: true`. These cells pin the wire shape, the
exit-code contract, the report-only honesty copy, and the no-raw-error rule.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS

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
    result = runner.invoke(app, ["post-scan", "integrity", "--help"])
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
        app, ["post-scan", "integrity", str(masked), "--source", str(src), "--json"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = _json.loads(result.stdout)
    assert payload["command"] == "post-scan integrity"
    assert payload["status"] == "ok"
    # The envelope carries only the value-free projection, never the raw report.
    assert "report" not in payload
    assert payload["schema_version"] == "integrity-report/v1"
    for bucket in ("residual_pii", "fk_preservation", "policy_validation"):
        assert bucket in payload
    assert payload["fail_count"] == 0
    assert payload["error_count"] == 0


def test_integrity_returns_report_shape(clean_pair: tuple[Path, Path]):
    """Pin the `integrity-report/v1` projection: 3 finding lists, 4 counters,
    per-bucket summary, and nothing free-text (no messages, no table names)."""
    src, masked = clean_pair
    result = runner.invoke(
        app, ["post-scan", "integrity", str(masked), "--source", str(src), "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    report = payload
    expected = {
        "schema_version",
        "source_schema_version",
        "buckets",
        "note",
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
    """`--output <path>` writes the integrity-report/v1 projection to disk."""
    src, masked = clean_pair
    out_path = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "post-scan",
            "integrity",
            str(masked),
            "--source",
            str(src),
            "--output",
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    assert out_path.exists()
    data = _json.loads(out_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "integrity-report/v1"
    assert "residual_pii" in data


def test_integrity_missing_source_exits_usage(tmp_path: Path):
    """A missing `--source` file is a usage error, not a runtime crash."""
    masked = tmp_path / "masked.csv"
    pd.DataFrame({"x": [1]}).to_csv(masked, index=False)
    result = runner.invoke(
        app,
        ["post-scan", "integrity", str(masked), "--source", str(tmp_path / "nope.csv")],
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
        ["post-scan", "integrity", str(masked), "--source", str(src), "--quiet"],
    )
    assert result.exit_code == 0
    assert result.stdout == ""


class TestExitFourReachable:
    """Audit H6/C1 (2026-06-12): with the pre-fix engine, `post-scan
    integrity` could never exit 4 in the no-config path -- residual-PII
    findings capped at 'warning' and real output==source leaks on
    faker-family strategies classified 'info'. The README's documented
    contract ('exit 4 on residual PII') is now reachable: a masked file
    that IS the source must fail."""

    def test_identical_masked_file_exits_findings(self, tmp_path):
        import pandas as pd

        src = tmp_path / "source.csv"
        pd.DataFrame(
            {"email": [f"user{i}@realmail.com" for i in range(50)]}
        ).to_csv(src, index=False)
        masked = tmp_path / "masked.csv"
        masked.write_bytes(src.read_bytes())  # mask "ran" but changed nothing

        result = runner.invoke(
            app, ["post-scan", "integrity", str(masked), "--source", str(src), "--json"]
        )
        assert result.exit_code == EXIT_FINDINGS, result.output
        payload = _json.loads(result.output)
        severities = [f["severity"] for f in payload["residual_pii"]]
        assert all(f["table"] == "table-1" and "message" not in f for f in payload["residual_pii"])
        assert "fail" in severities

    def test_properly_masked_file_exits_zero(self, tmp_path):
        import pandas as pd

        src = tmp_path / "source.csv"
        pd.DataFrame(
            {"email": [f"user{i}@realmail.com" for i in range(50)]}
        ).to_csv(src, index=False)
        masked = tmp_path / "masked.csv"
        pd.DataFrame(
            {"email": [f"fake{i}@masked.example" for i in range(50)]}
        ).to_csv(masked, index=False)

        result = runner.invoke(
            app, ["post-scan", "integrity", str(masked), "--source", str(src), "--json"]
        )
        assert result.exit_code == 0, result.output


class TestHonestyAndFailureTruth:
    """Report-only never claims a verdict it did not earn; a check that cannot
    run is a non-zero exit, never a clean pass; errors never echo raw text."""

    def test_clean_run_is_report_only_not_verified_or_approved(self, clean_pair):
        src, masked = clean_pair
        result = runner.invoke(
            app, ["post-scan", "integrity", str(masked), "--source", str(src)]
        )
        assert result.exit_code == 0
        out = " ".join(result.output.lower().split())
        assert "report-only" in out
        assert "not a release decision" in out
        for banned in ("verified", "release-approved", "safe to release", "compliant"):
            assert banned not in out

    def test_json_envelope_carries_the_report_only_note_and_schema(self, clean_pair):
        src, masked = clean_pair
        result = runner.invoke(
            app, ["post-scan", "integrity", str(masked), "--source", str(src), "--json"]
        )
        payload = _json.loads(result.output)
        assert "report-only" in payload["note"].lower()
        assert payload["schema_version"] == "integrity-report/v1"
        assert payload["source_schema_version"] == "post-scan-integrity/v2"

    def test_old_config_version_and_key_fail_without_echoing_values(self, clean_pair, tmp_path):
        src, masked = clean_pair
        cfg = tmp_path / "old.yaml"
        cfg.write_text("version: 1\nrun_flag_secret_value: SECRET-ABC-123\n", encoding="utf-8")
        result = runner.invoke(
            app,
            ["post-scan", "integrity", str(masked), "--source", str(src), "--config", str(cfg)],
        )
        assert result.exit_code != 0
        assert "SECRET-ABC-123" not in result.output

    def test_engine_crash_exits_runtime_with_type_name_only(self, clean_pair, monkeypatch):
        import decoy_engine.verification as verification

        from decoy.cli.exit_codes import EXIT_RUNTIME

        def boom(*_a, **_k):
            raise RuntimeError("raw cell value SECRET-ABC-123")

        monkeypatch.setattr(verification, "run_post_mask", boom)
        src, masked = clean_pair
        result = runner.invoke(
            app, ["post-scan", "integrity", str(masked), "--source", str(src), "--json"]
        )
        assert result.exit_code == EXIT_RUNTIME
        assert "SECRET-ABC-123" not in result.output
        payload = _json.loads(result.stdout)
        assert payload["status"] == "error"
        assert payload["error_type"] == "RuntimeError"
        assert payload["reason"] == "integrity_failed"

    def test_declared_post_scan_integrity_config_is_accepted(self, clean_pair, tmp_path):
        src, masked = clean_pair
        cfg = tmp_path / "p.yaml"
        cfg.write_text(
            "version: 2\nglobal_settings: {seed: 1}\n"
            f"sources:\n  data: {{type: file, format: csv, path: {src}}}\n"
            "tables:\n  - name: data\n    columns:\n      - {name: email, strategy: redact}\n"
            f"targets:\n  data: {{type: file, format: csv, path: {masked}}}\n"
            "post_scan:\n  integrity: true\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            [
                "post-scan", "integrity", str(masked), "--source", str(src),
                "--config", str(cfg), "--json",
            ],
        )
        assert result.exit_code in (0, EXIT_FINDINGS), result.output
        assert _json.loads(result.stdout)["command"] == "post-scan integrity"
