"""`sample_config`, `sample_placement` and `open_sample_layout` (SAMPLE SC1: AT-C3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoy.cli.io import LayoutError, layout_issues
from decoy.cli.run import _sample


def _cfg(targets: dict, **extra: object) -> dict:
    return {"version": 2, "tables": [], "targets": targets, **extra}


def test_every_kind_of_target_becomes_a_relative_basename() -> None:
    layout = {"columns": [{"name": "a", "start": 0, "width": 3}]}
    out = _sample.sample_config(
        _cfg(
            {
                "c": {"type": "file", "format": "csv", "path": "/abs/x.csv"},
                "p": {"type": "file", "format": "parquet", "path": "sub/p.parquet"},
                "f": {
                    "type": "file",
                    "format": "fixed_width",
                    "path": "../f.dat",
                    "layout": layout,
                },
                "s": {"type": "s3", "format": "csv", "bucket": "b", "key": "k"},
                "g": {"type": "gcs", "format": "parquet", "bucket": "b", "object": "o"},
                "d": {"type": "database", "table": "t"},
            },
            quarantine={"enabled": True, "output_path": "/var/q.jsonl"},
        )
    )
    paths = {t: spec["path"] for t, spec in out["targets"].items()}
    assert paths == {
        "c": "c.csv",
        "p": "p.parquet",
        "f": "f.txt",
        "s": "s.parquet",
        "g": "g.parquet",
        "d": "d.parquet",
    }
    assert all(spec["type"] == "file" for spec in out["targets"].values())
    assert out["targets"]["f"]["layout"] == layout
    assert out["quarantine"]["output_path"] == "quarantine.jsonl"


def test_the_input_is_not_changed_and_a_disabled_quarantine_is_left_alone() -> None:
    cfg = _cfg(
        {"c": {"type": "file", "format": "csv", "path": "x.csv"}},
        quarantine={"enabled": False, "output_path": "q.jsonl"},
    )
    before = repr(cfg)
    out = _sample.sample_config(cfg)
    assert repr(cfg) == before
    assert out["quarantine"]["output_path"] == "q.jsonl"


@pytest.mark.parametrize("name", ["with space", ".hidden", "_under", "naïve", "表"])
def test_unusual_table_names_still_work(name: str, tmp_path: Path) -> None:
    out = _sample.sample_config(_cfg({name: {"type": "file", "format": "csv", "path": "x"}}))
    assert out["targets"][name]["path"] == f"{name}.csv"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    cfg_path = tmp_path / "p.yaml"
    assert layout_issues(cfg_path, out, _sample.sample_placement(scratch)) == []


@pytest.mark.parametrize("name", ["a/b", "..", ".", "a\\b", "", "x/../y"])
def test_a_name_that_is_not_one_path_component_escapes(name: str) -> None:
    with pytest.raises(LayoutError) as caught:
        _sample.sample_config(_cfg({name: {"type": "file", "format": "csv", "path": "x"}}))
    assert caught.value.code == "layout.output_path_escapes"


def test_a_case_fold_pair_is_the_gates_collision(tmp_path: Path, monkeypatch) -> None:
    from decoy.cli.io import _placement

    monkeypatch.setattr(_placement, "_folds_case", lambda _folder: True)
    out = _sample.sample_config(
        _cfg(
            {
                "Users": {"type": "file", "format": "csv", "path": "a"},
                "users": {"type": "file", "format": "csv", "path": "b"},
            }
        )
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    issues = layout_issues(tmp_path / "p.yaml", out, _sample.sample_placement(scratch))
    assert [err.code for _loc, err in issues] == ["layout.output_path_collision"]


def test_the_placement_and_layout_are_the_out_dir_ones(tmp_path: Path) -> None:
    scratch = tmp_path / "s"
    scratch.mkdir()
    placement = _sample.sample_placement(scratch)
    assert placement.kind == "fixed" and placement.directory == scratch.resolve()
    layout = _sample.open_sample_layout(scratch)
    assert layout.output_dir() == scratch.resolve()
