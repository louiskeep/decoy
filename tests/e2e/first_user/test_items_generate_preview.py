"""`decoy run --rows N`: a small preview of a generate pipeline (GEN-CLI C2, AT-14 and AT-15).

The preview scales every generate table by one ratio, runs the pipeline, prints the rows and
writes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()


def _flat(text: str) -> str:
    return " ".join(text.split())


def _parent_child(parents: int = 1000, children: int = 5000) -> list[dict]:
    return [
        {
            "name": "parents",
            "row_count": parents,
            "generate_columns": [{"name": "pid", "type": "sequence", "start": 1, "step": 1}],
        },
        {
            "name": "children",
            "row_count": children,
            "generate_columns": [
                {
                    "name": "pid",
                    "type": "reference",
                    "reference_table": "parents",
                    "reference_column": "pid",
                },
                {"name": "n", "type": "sequence", "start": 1, "step": 1},
            ],
        },
    ]


def _write(folder: Path, tables: list[dict]) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {},
        "tables": tables,
        "targets": {
            t["name"]: {"type": "file", "format": "csv", "path": f"{t['name']}.csv"} for t in tables
        },
    }
    path = folder / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _mixed(folder: Path) -> Path:
    pd.DataFrame({"name": ["a", "b", "c"]}).to_csv(folder / "people.csv", index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source("people.csv")},
        "tables": [
            {"name": "people", "columns": [{"name": "name", "strategy": "shuffle"}]},
            *_parent_child(),
        ],
        "targets": {
            "people": {"type": "file", "format": "csv", "path": "people_out.csv"},
            "parents": {"type": "file", "format": "csv", "path": "parents.csv"},
            "children": {"type": "file", "format": "csv", "path": "children.csv"},
        },
    }
    path = folder / "mixed.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _written(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


# --- AT-14 -------------------------------------------------------------------


def test_rows_scales_every_table_by_one_ratio_and_writes_nothing(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _parent_child())
    before = _written(tmp_path)

    res = runner.invoke(app, ["run", str(cfg), "--rows", "5", "--json"])

    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload["command"] == "run" and payload["status"] == "ok"
    assert payload["preview"] is True
    assert payload["warnings"] == []
    by_name = {t["name"]: t for t in payload["tables"]}
    assert list(by_name) == ["parents", "children"]  # generation order, parents first
    assert by_name["parents"]["rows"] == 1 and by_name["children"]["rows"] == 5
    assert by_name["children"]["columns"] == ["pid", "n"]
    parent_keys = {row["pid"] for row in by_name["parents"]["sample"]}
    assert {row["pid"] for row in by_name["children"]["sample"]} <= parent_keys
    assert len(by_name["children"]["sample"]) == 5
    assert _written(tmp_path) == before  # no target, no evidence, nothing


def test_rows_human_output_prints_each_table_in_generation_order(tmp_path: Path) -> None:
    cfg = _write(tmp_path, list(reversed(_parent_child())))

    res = runner.invoke(app, ["run", str(cfg), "--rows", "4"])

    assert res.exit_code == 0, res.output
    text = _flat(res.stdout)
    assert text.index("parents") < text.index("children")
    assert "preview" in text.lower()
    assert not (tmp_path / "children.csv").exists()


def test_rows_keeps_every_table_at_one_row_or_more(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _parent_child(parents=3, children=900))

    res = runner.invoke(app, ["run", str(cfg), "--rows", "10", "--json"])

    assert res.exit_code == 0, res.output
    rows = {t["name"]: t["rows"] for t in json.loads(res.stdout)["tables"]}
    assert rows == {"parents": 1, "children": 10}


def test_rows_failure_on_a_per_parent_bound_hints_at_raising_rows(tmp_path: Path) -> None:
    tables = [
        {
            "name": "parents",
            "row_count": 10,
            "generate_columns": [{"name": "code", "type": "categorical", "categories": ["A", "B"]}],
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
    cfg = _write(tmp_path, tables)

    res = runner.invoke(app, ["run", str(cfg), "--rows", "5"])

    assert res.exit_code == EXIT_USAGE, res.output
    assert "raise --rows" in _flat(res.output)
    assert not (tmp_path / "children.csv").exists()


# --- AT-15 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["--chunked"],
        ["--chunk-size", "50"],
        ["--evidence-out", "ev.json"],
        ["--explain-plan"],
        ["--native"],
        ["--duckdb-source", "parents=x.duckdb"],
        ["--notify", "webhook:https://hooks.example.com/x"],
        ["--vault", "v.bin"],
        ["--fidelity"],
        ["--post-validate"],
        ["--post-validate-enforce"],
    ],
)
def test_rows_refuses_a_conflicting_flag_before_any_work(tmp_path: Path, extra: list[str]) -> None:
    cfg = _write(tmp_path, _parent_child())
    before = _written(tmp_path)

    res = runner.invoke(app, ["run", str(cfg), "--rows", "5", *extra])

    assert res.exit_code == EXIT_USAGE, res.output
    assert "--rows" in _flat(res.output) and extra[0] in _flat(res.output)
    assert _written(tmp_path) == before


def test_rows_refuses_a_mask_table(tmp_path: Path) -> None:
    cfg = _mixed(tmp_path)
    before = _written(tmp_path)

    res = runner.invoke(app, ["run", str(cfg), "--rows", "5", "--json"])

    assert res.exit_code == EXIT_USAGE, res.output
    payload = json.loads(res.stdout)
    assert payload["status"] == "error"
    assert "mask table" in payload["error"]
    assert _written(tmp_path) == before


@pytest.mark.parametrize("value", ["0", "1001", "-3"])
def test_rows_outside_1_to_1000_exits_1(tmp_path: Path, value: str) -> None:
    cfg = _write(tmp_path, _parent_child())

    res = runner.invoke(app, ["run", str(cfg), "--rows", value])

    assert res.exit_code == EXIT_USAGE, res.output
    assert "1 to 1000" in _flat(res.output)
    assert not (tmp_path / "parents.csv").exists()


def test_rows_accepts_the_bounds(tmp_path: Path) -> None:
    cfg = _write(tmp_path, _parent_child(parents=3000, children=9000))

    low = runner.invoke(app, ["run", str(cfg), "--rows", "1", "--json"])
    high = runner.invoke(app, ["run", str(cfg), "--rows", "1000", "--json"])

    assert low.exit_code == 0 and high.exit_code == 0, (low.output, high.output)
    assert {t["name"]: t["rows"] for t in json.loads(high.stdout)["tables"]} == {
        "parents": 333,
        "children": 1000,
    }


def test_a_plain_run_still_writes_targets(tmp_path: Path) -> None:
    """Non-vacuity: without --rows the same config writes its targets."""
    cfg = _write(tmp_path, _parent_child(parents=10, children=20))

    res = runner.invoke(app, ["run", str(cfg)])

    assert res.exit_code == 0, res.output
    assert (tmp_path / "children.csv").is_file()
