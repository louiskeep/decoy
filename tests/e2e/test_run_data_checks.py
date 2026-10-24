"""`decoy run` reports validator findings and quarantined rows (parity C1b).

The engine runs the `validators:` / `quarantine:` blocks inside `run_pipeline`
and removes quarantined rows from the written output. Before this change the
CLI read none of that evidence, so rows vanished with no message. These tests
pin the "Data checks" card, the `data_checks` JSON block, the quiet-mode
stderr line, and that no cell value leaks into any stream.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

_GOOD = "4111111111111111"
_BAD = "4111111111111112"  # fails Luhn
_SECRET_NAME = "ZQXJV-SECRET-NAME"


def _config(tmp_path: Path, *, quarantine: bool) -> Path:
    src = tmp_path / "cards.csv"
    pd.DataFrame({"cc": [_GOOD, _BAD], "name": [_SECRET_NAME, "Bob"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "t",
                "columns": [
                    {"name": "cc", "strategy": "passthrough"},
                    {"name": "name", "strategy": "hash", "namespace": "n"},
                ],
            }
        ],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
        "validators": [{"name": "luhn", "columns": {"t": ["cc"]}}],
    }
    if quarantine:
        cfg["quarantine"] = {
            "enabled": True,
            "output_path": str(tmp_path / "quarantine.jsonl"),
            "triggers": ["validation_fail"],
        }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_quarantined_rows_are_reported_in_the_card(tmp_path: Path) -> None:
    cfg = _config(tmp_path, quarantine=True)
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == 0, result.output
    assert len(pd.read_csv(tmp_path / "out.csv")) == 1
    assert "Data checks" in result.output
    assert "1 row(s)" in result.output
    assert "quarantine.jsonl" in result.output
    assert "luhn" in result.output
    assert _SECRET_NAME not in result.output
    assert _BAD not in result.output


def test_quarantine_block_in_json_envelope(tmp_path: Path) -> None:
    cfg = _config(tmp_path, quarantine=True)
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    checks = payload["data_checks"]
    assert checks["quarantine"]["total_quarantined"] == 1
    assert checks["quarantine"]["output_path"].endswith("quarantine.jsonl")
    assert checks["quarantine"]["counts_by_trigger"] == {"validation_fail": 1}
    assert checks["validators"]["run"] == ["luhn"]
    assert checks["validators"]["passed"] is False
    assert checks["validators"]["failing_rows_by_validator"] == {"luhn": 1}
    assert _BAD not in result.stdout and _SECRET_NAME not in result.stdout


def test_quiet_mode_still_warns_on_stderr(tmp_path: Path) -> None:
    cfg = _config(tmp_path, quarantine=True)
    result = runner.invoke(app, ["run", str(cfg), "--quiet"])
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "quarantine" in result.stderr.lower()
    assert "1 row(s)" in result.stderr


def test_passing_validators_report_as_passed(tmp_path: Path) -> None:
    cfg = _config(tmp_path, quarantine=True)
    src = tmp_path / "cards.csv"
    pd.DataFrame({"cc": [_GOOD, _GOOD], "name": ["a", "b"]}).to_csv(src, index=False)
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == 0, result.output
    checks = json.loads(result.stdout)["data_checks"]
    assert checks["validators"]["passed"] is True
    assert "quarantine" not in checks
    assert not (tmp_path / "quarantine.jsonl").exists() or (tmp_path / "quarantine.jsonl").stat().st_size == 0


def test_plain_run_without_checks_has_no_block(tmp_path: Path) -> None:
    cfg = _config(tmp_path, quarantine=False)
    raw = yaml.safe_load(cfg.read_text())
    raw.pop("validators")
    cfg.write_text(yaml.safe_dump(raw))
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == 0, result.output
    assert "data_checks" not in json.loads(result.stdout)
