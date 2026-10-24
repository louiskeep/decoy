"""`decoy run` writes a `format: fixed_width` target as fixed-width (parity C1a).

Before this fix `_write_mask_outputs` dispatched on the path suffix only, so a
declared fixed-width target was silently written as CSV. The schema already
refuses a fixed-width target without a `layout`; these tests pin the writer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_LAYOUT: dict[str, Any] = {
    "columns": [
        {"name": "id", "start": 0, "width": 6},
        {"name": "name", "start": 6, "width": 10},
        {"name": "age", "start": 16, "width": 3, "type": "int", "align": "right"},
    ]
}
_OUT_LAYOUT: dict[str, Any] = {
    "columns": [
        {"name": "id", "start": 0, "width": 6},
        {"name": "name", "start": 6, "width": 64},
        {"name": "age", "start": 70, "width": 3, "type": "int", "align": "right"},
    ]
}
_PEOPLE = [("A00001", "Alice", 31), ("A00002", "Bob", 4), ("A00003", "Carol", 57)]


def _write_source(path: Path) -> None:
    path.write_text("\n".join(f"{i:<6}{n:<10}{a:>3}" for i, n, a in _PEOPLE) + "\n")


def _config(tmp_path: Path, target: dict[str, Any]) -> Path:
    src = tmp_path / "people.dat"
    _write_source(src)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"people": {"type": "file", "format": "fixed_width", "path": str(src), "layout": _LAYOUT}},
        "tables": [
            {
                "name": "people",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "name", "strategy": "hash", "namespace": "name_ns"},
                    {"name": "age", "strategy": "passthrough"},
                ],
            }
        ],
        "targets": {"people": target},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_fixed_width_target_round_trips_through_the_engine_reader(tmp_path: Path) -> None:
    from decoy_engine import read_fixed_width

    out = tmp_path / "out.dat"
    cfg = _config(tmp_path, {"type": "file", "format": "fixed_width", "path": str(out), "layout": _OUT_LAYOUT})
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "," not in text, "fixed-width target was written as CSV"
    assert all(len(line) == 73 for line in text.splitlines())
    back = read_fixed_width(out, _OUT_LAYOUT)
    assert list(back["id"]) == [p[0] for p in _PEOPLE]
    assert list(back["age"]) == [p[2] for p in _PEOPLE]
    assert all(len(h) == 64 for h in back["name"])


def test_fixed_width_target_ignores_a_misleading_suffix(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    cfg = _config(tmp_path, {"type": "file", "format": "fixed_width", "path": str(out), "layout": _OUT_LAYOUT})
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "," not in out.read_text()


def test_fixed_width_target_without_layout_is_a_usage_error(tmp_path: Path) -> None:
    out = tmp_path / "out.dat"
    cfg = _config(tmp_path, {"type": "file", "format": "fixed_width", "path": str(out)})
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert not out.exists()


def test_csv_target_declared_csv_is_still_csv(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    cfg = _config(tmp_path, {"type": "file", "format": "csv", "path": str(out)})
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == 0, result.output
    frame = pd.read_csv(out, dtype=str)
    assert list(frame.columns) == ["id", "name", "age"]
