"""What a CLI user sees for a `date_shift` with no `date_format` (DATE-SHIFT-FORMAT).

Engine 0.28.2 refuses the column at plan compile with `date_shift_requires_date_format`. The
CLI carries that code through its one error path, with exit 1 and a hint that names the key to
set, and never echoes a source value. A second check holds every shipped template and example
to the same rule: none of them may be refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.templates import list_templates
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

runner = CliRunner()

CODE = "date_shift_requires_date_format"
_SOURCE_DATES = ("2021-03-04", "2020-11-30", "2019-07-15")
_REPO = Path(__file__).resolve().parents[2]


def _config(tmp_path: Path, provider_config: dict) -> Path:
    src = tmp_path / "visits.csv"
    pd.DataFrame({"visit": list(_SOURCE_DATES)}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"visits": csv_source(src)},
        "tables": [
            {
                "name": "visits",
                "columns": [
                    {
                        "name": "visit",
                        "strategy": "date_shift",
                        "namespace": "dates",
                        "provider_config": provider_config,
                    }
                ],
            }
        ],
        "targets": {"visits": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _assert_value_free(text: str) -> None:
    for date in _SOURCE_DATES:
        assert date not in text, text


def test_validate_json_refuses_with_code_hint_and_exit(tmp_path: Path, mask_secret: str) -> None:
    cfg = _config(tmp_path, {"min_days": -30, "max_days": 30})
    result = runner.invoke(app, ["validate", "config", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    doc = json.loads(result.stdout)
    assert doc["status"] == "error"
    (msg,) = doc["messages"]
    assert msg["code"] == CODE
    assert "date_format" in msg["message"]
    assert "date_format" in msg["hint"]
    _assert_value_free(result.output)
    assert not (tmp_path / "out.csv").exists()


def test_validate_human_output_names_code_and_hint(tmp_path: Path, mask_secret: str) -> None:
    cfg = _config(tmp_path, {"min_days": -30, "max_days": 30})
    result = runner.invoke(app, ["validate", "config", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert CODE in result.output
    hint_lines = [ln for ln in result.output.splitlines() if "hint:" in ln]
    assert hint_lines and "date_format" in " ".join(hint_lines), result.output
    _assert_value_free(result.output)


def test_run_refuses_before_reading_and_writes_nothing(tmp_path: Path, mask_secret: str) -> None:
    cfg = _config(tmp_path, {"min_days": -30, "max_days": 30})
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    doc = json.loads(result.stdout)
    (msg,) = doc["messages"]
    assert msg["code"] == CODE
    assert "date_format" in msg["hint"]
    _assert_value_free(result.output)
    assert not (tmp_path / "out.csv").exists()


def test_the_same_config_with_a_format_validates(tmp_path: Path, mask_secret: str) -> None:
    cfg = _config(tmp_path, {"min_days": -30, "max_days": 30, "date_format": "%Y-%m-%d"})
    result = runner.invoke(app, ["validate", "config", str(cfg), "--json"])
    assert result.exit_code == EXIT_OK, result.output


def _shipped_configs_with_date_shift() -> list[tuple[str, str]]:
    found = [(f"template:{t.name}", t.body) for t in list_templates() if "date_shift" in t.body]
    for path in sorted((_REPO / "examples").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        if "date_shift" in text:
            found.append((f"example:{path.name}", text))
    return found


def test_the_shipped_set_includes_the_compliance_templates() -> None:
    ids = {i for i, _ in _shipped_configs_with_date_shift()}
    assert {"template:hipaa", "template:pci"} <= ids


@pytest.mark.parametrize(
    ("ident", "body"), _shipped_configs_with_date_shift(), ids=lambda v: v if "/" not in v else ""
)
def test_no_shipped_config_is_refused_for_a_missing_date_format(
    ident: str, body: str, tmp_path: Path, mask_secret: str
) -> None:
    cfg = yaml.safe_load(body)
    # Point sources at real files so validate reaches plan compile, not a missing-path stop.
    for src in cfg.get("sources", {}).values():
        if "path" in src:
            local = tmp_path / Path(src["path"]).name
            local.write_text("x\n", encoding="utf-8")
            src["path"] = str(local)
    cfg.setdefault("global_settings", {})["mask_secret_ref"] = TEST_MASK_SECRET_REF
    path = tmp_path / "shipped.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["validate", "config", str(path), "--json"])
    codes = [m["code"] for m in json.loads(result.stdout).get("messages", [])]
    assert CODE not in codes, f"{ident} is refused: {codes}"
