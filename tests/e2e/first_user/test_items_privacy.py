"""`decoy fit` must not write the values of sensitive columns by default.

QA item High 5 (docs/records/2026-11-08-cli-qa-first-user.md): a plain
`decoy fit` copied raw SSNs and names into the snapshot's `top_values`. Each
cell here reproduces that run against a small patients fixture and checks the
file, stdout and stderr for the fixture's values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_ROWS = 60
# Eight repeating SSNs: a unique-per-row column is not sampled into top_values.
_SSNS = [f"{100 + i % 8:03d}-{20 + i % 8:02d}-{1000 + (i % 8) * 7:04d}" for i in range(_ROWS)]
_NAMES = [f"Zelda Quillfeather{i:02d}" for i in range(_ROWS)]
_IDS = [f"PT-{7000 + i}" for i in range(_ROWS)]
_FIXTURE_VALUES = [*_SSNS, *_NAMES, *_IDS]


def _patients(tmp_path: Path) -> Path:
    src = tmp_path / "patients.csv"
    pd.DataFrame(
        {
            "patient_id": _IDS,
            "name": _NAMES,
            "ssn": _SSNS,
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * (_ROWS // 8) + ["CA"] * (_ROWS % 8),
            "amount": [10.5 + i for i in range(_ROWS)],
        }
    ).to_csv(src, index=False)
    return src


def _fit(tmp_path: Path, *extra: str) -> tuple[Any, Path]:
    out = tmp_path / "snap.json"
    result = runner.invoke(app, ["fit", str(_patients(tmp_path)), "-o", str(out), *extra])
    return result, out


def _leaks(text: str) -> list[str]:
    return [v for v in _FIXTURE_VALUES if v in text]


def _stderr(result: Any) -> str:
    try:
        return result.stderr
    except ValueError:
        return ""


def test_f1_default_fit_withholds_sensitive_values(tmp_path: Path) -> None:
    result, out = _fit(tmp_path)
    assert result.exit_code == 0, result.output
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert "ssn" in doc["redacted_columns"]
    assert _leaks(out.read_text(encoding="utf-8")) == []
    assert _leaks(result.output) == []
    assert _leaks(_stderr(result)) == []
    assert "ssn" in result.output
    assert "withheld" in result.output


def test_f2_include_values_keeps_values_and_warns(tmp_path: Path) -> None:
    result, out = _fit(tmp_path, "--include-values")
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["value_policy"] == "raw"
    assert any(ssn in text for ssn in _SSNS)
    warning = " ".join((result.output + _stderr(result)).split())
    assert "holds real values" in warning
    assert "ssn" in warning
    assert str(out) in warning.replace("\n", "")


def test_f3_json_payload_names_policy_and_columns(tmp_path: Path) -> None:
    result, _ = _fit(tmp_path, "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["value_policy"] == "flagged-redacted/v1"
    assert "ssn" in payload["redacted_columns"]
    assert _leaks(result.stdout) == []


def test_f4_listed_columns_come_from_the_document_not_the_output_path(tmp_path: Path) -> None:
    out = tmp_path / "snap.json"
    out.write_text(
        json.dumps({"value_policy": "flagged-redacted/v1", "redacted_columns": ["forged_col"]}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["fit", str(_patients(tmp_path)), "-o", str(out), "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(out.read_text(encoding="utf-8"))
    payload = json.loads(result.stdout)
    assert payload["redacted_columns"] == doc["redacted_columns"]
    assert "forged_col" not in payload["redacted_columns"]
    human = runner.invoke(app, ["fit", str(_patients(tmp_path)), "-o", str(out)])
    assert "forged_col" not in human.output
    for name in doc["redacted_columns"]:
        assert name in human.output


def _gen_config(tmp_path: Path, snap: Path, *, real: bool) -> Path:
    col: dict[str, Any] = {"name": "ssn", "type": "statistical", "snapshot_file": str(snap)}
    if real:
        col["allow_real_categories"] = True
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "tables": [{"name": "synthetic", "row_count": 10, "generate_columns": [col]}],
        "targets": {
            "synthetic": {"type": "file", "format": "csv", "path": str(tmp_path / "o.csv")}
        },
    }
    path = tmp_path / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_f5_validate_rejects_withheld_column_until_refit_with_values(tmp_path: Path) -> None:
    _, snap = _fit(tmp_path)
    cfg = _gen_config(tmp_path, snap, real=True)
    redacted = runner.invoke(app, ["validate", "config", str(cfg)])
    assert redacted.exit_code == 1, redacted.output
    assert "statistical_snapshot_values_redacted" in redacted.output
    assert "--include-values" in redacted.output

    refit, snap = _fit(tmp_path, "--include-values")
    assert refit.exit_code == 0, refit.output
    ok = runner.invoke(app, ["validate", "config", str(_gen_config(tmp_path, snap, real=True))])
    assert ok.exit_code == 0, ok.output


def test_f6_include_values_with_epsilon_is_a_usage_error_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("pd.read_csv must not run")

    monkeypatch.setattr(pd, "read_csv", _no_read)
    src = tmp_path / "s.csv"
    src.write_text("state\nCA\nNY\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["fit", str(src), "--include-values", "--epsilon", "1", "--delta", "1e-6",
         "--dp-text", "state", "--json"],
    )  # fmt: skip
    assert result.exit_code == EXIT_USAGE
    assert json.loads(result.stdout)["code"] == "dp_usage_include_values"


def test_f7_snapshot_carries_cell_format_per_column(tmp_path: Path) -> None:
    _, out = _fit(tmp_path)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert all("cell_format" in col for col in doc["columns"].values())
