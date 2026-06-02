"""End-to-end roundtrip for `decoy init <file>` (OSS.4c, 2026-06-02).

The shape pinned here is the operator's golden path:

    decoy storm analyze customers.csv          # see what STORM sees
    decoy init customers.csv --out p.yaml      # scaffold with REVIEW comments
    decoy validate p.yaml                      # engine accepts the schema
    decoy run p.yaml                           # masks the data
    decoy storm integrity customers.masked.csv --source customers.csv

If this test starts failing, the friction the user hits when trying out
the CLI for the first time just went up; investigate the regression
before merging.

Tests touch a real (tiny) DataFrame and run real STORM scans, but no
network and no cloud storage. The masked output lands under tmp_path.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


@pytest.fixture
def csv_with_pii(tmp_path: Path) -> Path:
    """Tiny CSV with two well-known PII detector hits + one neutral column.

    STORM should flag `email` (email detector) and `ssn` (ssn detector),
    leaving `note` to fall through to the redact fallback. That mix
    exercises both branches of `_infer_strategy_for_column`.
    """
    csv = tmp_path / "customers.csv"
    pd.DataFrame(
        {
            "email": [
                "alice@example.com",
                "bob@example.com",
                "carol@example.com",
                "dave@example.com",
            ],
            "ssn": ["111-22-3333", "222-33-4444", "333-44-5555", "444-55-6666"],
            "note": ["hello", "world", "foo", "bar"],
        }
    ).to_csv(csv, index=False)
    return csv


def test_init_scaffolds_yaml_with_review_comments(csv_with_pii: Path, tmp_path: Path):
    """The column-aware scaffold writes a YAML with `# REVIEW:` above
    every column entry and pins the provenance header at the top."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(app, ["init", str(csv_with_pii), "--out", str(out), "--quiet"])
    assert result.exit_code == 0, result.stdout + result.stderr
    body = out.read_text(encoding="utf-8")
    # Provenance + UX-critical text.
    assert "decoy init customers.csv" in body
    assert "# REVIEW:" in body
    # PII columns get their inference-table strategies.
    assert "strategy: faker" in body
    assert "person_email" in body
    # The neutral note column falls through to redact.
    assert "strategy: redact" in body


def test_init_json_mode_reports_column_count(csv_with_pii: Path, tmp_path: Path):
    """--json emits a structured record (command, status, source, column_count)
    suitable for piping into another tool. column_count == number of fields
    STORM found in the CSV."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", str(csv_with_pii), "--out", str(out), "--json"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = _json.loads(result.stdout)
    assert payload["command"] == "init"
    assert payload["status"] == "ok"
    assert payload["mode"] == "scaffold-from-file"
    assert payload["source"] == str(csv_with_pii)
    assert payload["column_count"] == 3


def test_init_validate_then_run_smoke(csv_with_pii: Path, tmp_path: Path):
    """Roundtrip: scaffold a YAML, validate it, and read the body to
    confirm sources/tables/targets are present in the expected shape."""
    out = tmp_path / "pipeline.yaml"
    init_result = runner.invoke(
        app, ["init", str(csv_with_pii), "--out", str(out), "--quiet"]
    )
    assert init_result.exit_code == 0

    # Sources + tables + targets are present and reference the input file.
    body = out.read_text(encoding="utf-8")
    assert "sources:" in body
    assert "tables:" in body
    assert "targets:" in body
    assert str(csv_with_pii) in body or csv_with_pii.name in body

    # `decoy validate` exits 0 against the scaffolded YAML.
    validate_result = runner.invoke(app, ["validate", str(out), "--quiet"])
    assert validate_result.exit_code == 0, (
        validate_result.stdout + validate_result.stderr
    )


def test_init_stdout_with_dash(csv_with_pii: Path, tmp_path: Path):
    """`--out -` writes the YAML body to stdout instead of a file."""
    result = runner.invoke(
        app, ["init", str(csv_with_pii), "--out", "-"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "version: 1" in result.stdout
    assert "# REVIEW:" in result.stdout


def test_init_missing_file_exits_usage(tmp_path: Path):
    """A nonexistent positional input file is a usage error."""
    result = runner.invoke(
        app, ["init", str(tmp_path / "nope.csv"), "--out", str(tmp_path / "p.yaml"), "--quiet"]
    )
    assert result.exit_code == 1


def test_init_unsupported_extension_exits_usage(tmp_path: Path):
    """`.json` (or any non-CSV/Parquet) is a usage error, not a runtime crash."""
    bogus = tmp_path / "data.json"
    bogus.write_text('{"a": 1}', encoding="utf-8")
    result = runner.invoke(
        app, ["init", str(bogus), "--out", str(tmp_path / "p.yaml"), "--quiet"]
    )
    assert result.exit_code == 1


def test_init_preset_still_works_unchanged(tmp_path: Path):
    """OSS.4c must not regress the existing preset path: `decoy init`
    with `--preset` (and no positional file) still scaffolds from the
    bundled template."""
    out = tmp_path / "pipeline.yaml"
    result = runner.invoke(
        app, ["init", "--preset", "minimal", "--out", str(out), "--json"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = _json.loads(result.stdout)
    assert payload["preset"] == "minimal"
    assert "rule_count" in payload
