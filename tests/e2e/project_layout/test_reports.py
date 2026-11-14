"""AT-29 (P9): `report integrity` and `report fidelity` write into the run folder by default.

With no output flag and the checked file inside a run folder, the JSON report is also written to
`<run>/reports/<kind>.json` and its path is printed. A typed flag wins and is the only file
written. A file outside any run folder writes nothing new.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK
from tests.csv_sources import csv_source

runner = CliRunner()
WIDE = {"COLUMNS": "1000"}


def _masked_run(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "proj"
    (root / "pipelines" / "orders").mkdir(parents=True)
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    src = root / "a.csv"
    pd.DataFrame({"email": pd.Series(["a@example.com", "b@example.com"], dtype="string")}).to_csv(
        src, index=False
    )
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": "masked.csv"}},
    }
    (root / "pipelines" / "orders" / "pipeline.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )
    result = runner.invoke(app, ["run", str(root / "pipelines" / "orders" / "pipeline.yaml")])
    assert result.exit_code == EXIT_OK, result.output
    (run,) = [p for p in (root / "out" / "orders").iterdir() if p.is_dir() and p.name[0].isdigit()]
    return root, src, run / "masked.csv"


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _integrity(masked: Path, src: Path, *extra: str):
    return runner.invoke(
        app, ["report", "integrity", str(masked), "--source", str(src), *extra], env=WIDE
    )


def _fidelity(src: Path, masked: Path, *extra: str):
    return runner.invoke(app, ["report", "fidelity", str(src), str(masked), *extra], env=WIDE)


@pytest.mark.parametrize("kind", ["integrity", "fidelity"])
def test_a_run_output_gets_a_report_in_its_run_folder(tmp_path: Path, kind: str) -> None:
    _root, src, masked = _masked_run(tmp_path)
    result = _integrity(masked, src) if kind == "integrity" else _fidelity(src, masked)
    assert result.exit_code in (EXIT_OK, 4), result.output
    report = masked.parent / "reports" / f"{kind}.json"
    assert json.loads(report.read_text(encoding="utf-8"))
    assert (
        str(report) in result.output or report.relative_to(Path.cwd()).as_posix() in result.output
    )
    if sys.platform != "win32":
        assert (report.parent.stat().st_mode & 0o077) == 0
        assert (report.stat().st_mode & 0o077) == 0
    assert "a@example.com" not in report.read_text(encoding="utf-8")


def test_a_typed_flag_wins_and_is_the_only_file(tmp_path: Path) -> None:
    root, src, masked = _masked_run(tmp_path)
    typed = tmp_path / "typed.json"
    before = _files(root)
    assert _integrity(masked, src, "--output", str(typed)).exit_code in (EXIT_OK, 4)
    assert typed.is_file()
    assert _files(root) == before
    typed_f = tmp_path / "typed-f.json"
    assert _fidelity(src, masked, "--report-out", str(typed_f)).exit_code in (EXIT_OK, 4)
    assert typed_f.is_file()
    assert _files(root) == before


@pytest.mark.parametrize("kind", ["integrity", "fidelity"])
def test_a_file_outside_any_run_folder_writes_nothing(tmp_path: Path, kind: str) -> None:
    root, src, masked = _masked_run(tmp_path)
    loose = root / "loose.csv"
    loose.write_bytes(masked.read_bytes())
    before = _files(root)
    result = _integrity(loose, src) if kind == "integrity" else _fidelity(src, loose)
    assert result.exit_code in (EXIT_OK, 4), result.output
    assert _files(root) == before


def test_json_stdout_stays_one_document(tmp_path: Path) -> None:
    _root, src, masked = _masked_run(tmp_path)
    result = _integrity(masked, src, "--json")
    assert result.exit_code in (EXIT_OK, 4), result.output
    json.loads(result.stdout)
