"""GEN-UNIQUE C1: `decoy run` exit codes for the engine's uniqueness and budget refusals.

Plan `plan/gen-unique` (decoy-engine), AT-14. The real-engine cases run the pinned engine; the
code-mapping cases inject the engine exception at `decoy_engine.run_pipeline`, the same seam
`test_run_capacity.py` uses, so one other `GenerationError` code can be shown to keep exit 3.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_RUNTIME, EXIT_USAGE

runner = CliRunner()

# A parent key that must never reach a terminal or an envelope.
_SENTINEL = "SENTINEL-PARENT-KEY"


def _write(tmp_path: Path, tables: list[dict]) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {},
        "tables": tables,
        "targets": {
            t["name"]: {"type": "file", "format": "csv", "path": str(tmp_path / f"{t['name']}.csv")}
            for t in tables
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def _two_distinct_parent_keys() -> list[dict]:
    """A parent with 10 rows but 2 distinct keys, and a child asking 6 unique references.

    Validate cannot know the parent's distinct count (a categorical draw), so the refusal
    comes at run time.
    """
    return [
        {
            "name": "parents",
            "row_count": 10,
            "generate_columns": [
                {
                    "name": "code",
                    "type": "categorical",
                    "categories": [f"{_SENTINEL}-A", f"{_SENTINEL}-B"],
                }
            ],
        },
        {
            "name": "children",
            "row_count": 6,
            "generate_columns": [
                {
                    "name": "parent_code",
                    "type": "reference",
                    "reference_table": "parents",
                    "reference_column": "code",
                    "unique": True,
                }
            ],
        },
    ]


def _engine_error(cls_name: str, module: str, code: str, message: str):
    import importlib

    cls = getattr(importlib.import_module(module), cls_name)
    return cls(code=code, message=message)


def test_reference_with_too_few_parent_keys_exits_1_without_values(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _two_distinct_parent_keys())
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "uniqueness_impossible" in result.output
    assert "children.parent_code" in " ".join(result.output.split())
    assert _SENTINEL not in result.output
    assert not (tmp_path / "children.csv").exists()


def test_uniqueness_refusal_json_envelope_is_value_free(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _two_distinct_parent_keys())
    result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert _SENTINEL not in result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "uniqueness_impossible" in payload["error"]


def test_faker_that_runs_out_exits_1(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        [
            {
                "name": "users",
                "row_count": 2000,
                "generate_columns": [
                    {"name": "state", "type": "faker", "faker_type": "state_abbr", "unique": True}
                ],
            }
        ],
    )
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "uniqueness_impossible" in result.output
    assert not (tmp_path / "users.csv").exists()


def test_other_generation_error_code_still_exits_3(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _two_distinct_parent_keys()[:1])
    err = _engine_error(
        "GenerationError", "decoy_engine", "dtype_unsafe", "output dtype is not safe"
    )
    with mock.patch("decoy_engine.run_pipeline", side_effect=err):
        result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_RUNTIME, result.output


def test_injected_uniqueness_code_exits_1(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _two_distinct_parent_keys()[:1])
    err = _engine_error("GenerationError", "decoy_engine", "uniqueness_impossible", "no")
    with mock.patch("decoy_engine.run_pipeline", side_effect=err):
        result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output


def test_generation_budget_exceeded_exits_5_and_labels_capacity(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _two_distinct_parent_keys()[:1])
    err = _engine_error(
        "GenerationBudgetExceeded",
        "decoy_engine.generation._budget_ledger",
        "generation_budget_exceeded",
        "stage 'x' needs 9 bytes but only 1 of 2 remain.",
    )
    with mock.patch("decoy_engine.run_pipeline", side_effect=err):
        result = runner.invoke(app, ["run", str(cfg), "--json"])
    assert result.exit_code == EXIT_CAPACITY, result.output
    payload = json.loads(result.stdout)
    assert payload["error_kind"] == "capacity"
    assert payload["code"] == "generation_budget_exceeded"


def test_explain_unique_names_both_keys_and_pooled() -> None:
    result = runner.invoke(app, ["explain", "unique"])
    assert result.exit_code == 0, result.output
    flat = " ".join(result.stdout.split())
    for word in ("unique", "unique_together", "pooled", "uniqueness_impossible"):
        assert word in flat, word


def test_schema_shows_unique_and_unique_together() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert '"unique"' in result.stdout
    assert '"unique_together"' in result.stdout


def test_preflight_over_scaled_down_junction_reports_an_outcome_not_a_crash(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path,
        [
            {
                "name": "items",
                "row_count": 50,
                "generate_columns": [
                    {"name": "item_id", "type": "sequence", "start": 1, "step": 1}
                ],
            },
            {
                "name": "shelves",
                "row_count": 20,
                "generate_columns": [
                    {"name": "shelf_id", "type": "sequence", "start": 1, "step": 1}
                ],
            },
            {
                "name": "item_shelves",
                "row_count": 990,
                "unique_together": [["item_id", "shelf_id"]],
                "generate_columns": [
                    {
                        "name": "item_id",
                        "type": "reference",
                        "reference_table": "items",
                        "reference_column": "item_id",
                    },
                    {
                        "name": "shelf_id",
                        "type": "reference",
                        "reference_table": "shelves",
                        "reference_column": "shelf_id",
                    },
                ],
            },
        ],
    )
    result = runner.invoke(app, ["validate", "preflight", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
    run = runner.invoke(app, ["run", str(cfg)])
    assert run.exit_code == 0, run.output
    rows = (tmp_path / "item_shelves.csv").read_text(encoding="utf-8").splitlines()[1:]
    assert len(rows) == 990
    assert len(set(rows)) == 990
