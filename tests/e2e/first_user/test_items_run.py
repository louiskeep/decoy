"""`decoy run` summary a first-time user could not read.

The card and JSON payload carried pipeline, mode and elapsed only. A user could not tell how many
tables ran, how many rows were masked, or which files were published. The summary now lists
tables, rows and the exact files written; a chunked run reports `rows` as unknown because it
streams without counting.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import mock

import decoy_engine
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.io import _targets
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qa_first_user"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _stage_pair(tmp_path: Path) -> Path:
    """Copy the QA pair; the pipeline gets a mask secret ref (`hash` is keyed) and absolute paths."""
    for name in ("patients.csv", "visits.csv"):
        shutil.copy(_FIXTURES / name, tmp_path / name)
    cfg = yaml.safe_load((_FIXTURES / "pipeline_namespaced.yaml").read_text(encoding="utf-8"))
    cfg["global_settings"]["mask_secret_ref"] = TEST_MASK_SECRET_REF
    for block in ("sources", "targets"):
        for spec in cfg[block].values():
            spec["path"] = str(tmp_path / spec["path"])
    path = tmp_path / "pipeline_namespaced.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _chunked_config(tmp_path: Path, source_text: str) -> Path:
    (tmp_path / "in.csv").write_text(source_text, encoding="utf-8")
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {"patients": {"type": "file", "path": "in.csv", "format": "csv"}},
        "targets": {"patients": {"type": "file", "path": "out.csv", "format": "csv"}},
        "tables": [
            {
                "name": "patients",
                "columns": [{"name": "full_name", "strategy": "redact"}],
            }
        ],
    }
    path = tmp_path / "chunked.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


# --- Item 14: the run summary lists tables, rows and files --------------------


def test_run_card_shows_tables_rows_and_files(tmp_path: Path) -> None:
    pipeline = _stage_pair(tmp_path)

    result = runner.invoke(app, ["run", str(pipeline)])

    assert result.exit_code == 0, result.output
    text = _flat(result.stdout)
    assert "Tables 2" in text
    assert "Rows 10" in text
    assert "Files 2" in text


def test_run_json_lists_the_exact_tables(tmp_path: Path) -> None:
    pipeline = _stage_pair(tmp_path)

    result = runner.invoke(app, ["run", str(pipeline), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    tables = {t["name"]: t for t in payload["tables"]}
    assert set(tables) == {"patients", "visits"}
    assert tables["patients"]["rows"] == 5
    assert tables["visits"]["rows"] == 5
    for name, record in tables.items():
        assert Path(record["path"]) == tmp_path / "out" / f"{name}.csv"
        assert Path(record["path"]).is_file()


def test_chunked_run_reports_files_but_no_row_count(tmp_path: Path) -> None:
    pipeline = _chunked_config(tmp_path, "full_name\nAda Example\nBen Example\n")

    human = runner.invoke(app, ["run", str(pipeline), "--chunked"])
    machine = runner.invoke(app, ["run", str(pipeline), "--chunked", "--json"])

    assert human.exit_code == 0, human.output
    text = _flat(human.stdout)
    assert "Tables 1" in text
    assert "Files 1" in text
    assert "Rows n/a (chunked)" in text
    record = json.loads(machine.stdout)["tables"][0]
    assert record["name"] == "patients"
    assert record["rows"] is None
    assert Path(record["path"]) == tmp_path / "out.csv"


def test_chunked_run_that_publishes_nothing_counts_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same stream-yields-nothing seam as AT-A9: the CSV writer publishes no file.
    pipeline = _chunked_config(tmp_path, "full_name\nAda Example\n")
    monkeypatch.setattr(decoy_engine, "run_mask_pipeline_chunked", lambda *a, **k: iter(()))

    human = runner.invoke(app, ["run", str(pipeline), "--chunked"])
    machine = runner.invoke(app, ["run", str(pipeline), "--chunked", "--json"])

    assert human.exit_code == 0, human.output
    assert not (tmp_path / "out.csv").exists()
    assert "Files 0" in _flat(human.stdout)
    record = json.loads(machine.stdout)["tables"][0]
    assert record["path"] is None
    assert record["rows"] is None


def test_whole_table_writer_returns_the_published_path(tmp_path: Path) -> None:
    import pyarrow as pa

    out = tmp_path / "out" / "t.csv"
    config = {"targets": {"t": {"type": "file", "path": str(out), "format": "csv"}}}

    written = _targets.write_targets(config, {"t": pa.table({"a": [1]})}, tmp_path)

    assert written == {"t": out}


def test_chunked_writer_returns_none_when_it_publishes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "never.csv"

    published = _targets.write_chunked_output([], "csv", out, empty_schema=None)

    assert published is None
    assert not out.exists()


def test_a_target_with_no_output_table_is_not_reported(tmp_path: Path) -> None:
    import pyarrow as pa

    out = tmp_path / "ghost.csv"
    config = {"targets": {"ghost": {"type": "file", "path": str(out), "format": "csv"}}}

    written = _targets.write_targets(config, {"other": pa.table({"a": [1]})}, tmp_path)

    assert written == {}
    assert not out.exists()


def test_a_path_is_recorded_only_after_its_write_returns(tmp_path: Path) -> None:
    # The second write fails. Only the first table may be recorded, and only because its write
    # returned. A path recorded before its write, or from config alone, would show up here.
    import pyarrow as pa

    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    config = {
        "targets": {
            "a": {"type": "file", "path": str(first), "format": "csv"},
            "b": {"type": "file", "path": str(second), "format": "csv"},
        }
    }
    real_write = _targets.write_table
    calls: list[str] = []

    def write_then_fail(table, fmt, path, layout=None):
        calls.append(path.name)
        if len(calls) == 2:
            raise OSError
        real_write(table, fmt, path, layout)

    outputs = {"a": pa.table({"x": [1]}), "b": pa.table({"x": [2]})}
    with mock.patch.object(_targets, "write_table", write_then_fail):
        with pytest.raises(OSError) as raised:
            _targets.write_targets(config, outputs, tmp_path)

    # write_targets raised, so read what it had recorded from its own frame.
    tb = raised.value.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_name != "write_targets":
        tb = tb.tb_next
    assert tb is not None
    assert tb.tb_frame.f_locals["published"] == {"a": first}
    assert first.is_file()
    assert not second.exists()
