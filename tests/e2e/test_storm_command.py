"""End-to-end tests for `decoy storm analyze`."""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "sample.csv"
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4", "C5"],
            "first_name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
            "email": ["a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com"],
            "ssn": [
                "111-22-3333",
                "222-33-4444",
                "333-44-5555",
                "444-55-6666",
                "555-66-7777",
            ],
        }
    ).to_csv(path, index=False)
    return path


def test_storm_analyze_help_includes_examples(tmp_path: Path):
    result = runner.invoke(app, ["storm", "analyze", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_storm_fields_non_utf8_scan_prints_clean_error(tmp_path: Path):
    """QA 2026-06-04 storm-validate-cli F1 (HIGH): a non-UTF-8 scan file must
    produce a clean usage error, not an unhandled UnicodeDecodeError traceback
    (which would also corrupt --json output). UnicodeDecodeError is a
    ValueError, not an OSError, so it is normalised inside _load_scan_dict."""
    from decoy.cli.exit_codes import EXIT_USAGE

    bad = tmp_path / "bad_scan.json"
    bad.write_bytes(b"\x80\x81\x82 not valid utf-8")
    result = runner.invoke(app, ["storm", "fields", str(bad)])
    assert result.exit_code == EXIT_USAGE, (result.stdout, result.exception)
    assert not isinstance(result.exception, UnicodeDecodeError)


def test_storm_analyze_writes_profile_and_succeeds(sample_csv: Path, tmp_path: Path):
    out_path = tmp_path / "scan.json"
    result = runner.invoke(
        app, ["storm", "analyze", str(sample_csv), "--out", str(out_path)]
    )
    assert result.exit_code == 0, result.stdout
    assert out_path.exists()
    payload = _json.loads(out_path.read_text())
    assert payload["row_count"] == 5
    assert payload["fields"]
    assert payload["source_label"] == "sample.csv"


def test_storm_analyze_json_emits_envelope(sample_csv: Path, tmp_path: Path):
    out_path = tmp_path / "scan.json"
    result = runner.invoke(
        app,
        ["storm", "analyze", str(sample_csv), "--out", str(out_path), "--json"],
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "storm analyze"
    assert payload["status"] == "ok"
    assert payload["profile"]["row_count"] == 5


def test_storm_analyze_quiet_produces_empty_stdout(sample_csv: Path, tmp_path: Path):
    out_path = tmp_path / "scan.json"
    result = runner.invoke(
        app,
        ["storm", "analyze", str(sample_csv), "--out", str(out_path), "--quiet"],
    )
    assert result.exit_code == 0
    assert result.stdout == ""
    assert out_path.exists()


def test_storm_analyze_strategy_random_caps_rows(sample_csv: Path, tmp_path: Path):
    out_path = tmp_path / "scan.json"
    result = runner.invoke(
        app,
        [
            "storm",
            "scan",
            str(sample_csv),
            "--out",
            str(out_path),
            "--rows",
            "3",
            "--strategy",
            "random",
        ],
    )
    assert result.exit_code == 0
    payload = _json.loads(out_path.read_text())
    assert payload["row_count"] == 3


def test_storm_scan_alias_works_and_warns(sample_csv: Path, tmp_path: Path):
    """OSS.4a (2026-06-02): `decoy storm scan` is a deprecated alias for
    `decoy storm analyze`. It must still produce the same scan output AND
    emit a stderr deprecation warning naming the canonical verb + the
    removal target (0.2.0). Pattern source: kubectl deprecation
    convention. Removal of this alias removes this test too."""
    out_path = tmp_path / "scan.json"
    result = runner.invoke(
        app, ["storm", "scan", str(sample_csv), "--out", str(out_path)]
    )
    assert result.exit_code == 0, result.stdout
    assert out_path.exists()
    payload = _json.loads(out_path.read_text())
    assert payload["row_count"] == 5
    # The deprecation warning lives on stderr (`result.output` carries
    # the combined streams under typer.testing.CliRunner).
    assert "`decoy storm scan` is deprecated" in result.output
    assert "`decoy storm analyze`" in result.output
    assert "0.2.0" in result.output
