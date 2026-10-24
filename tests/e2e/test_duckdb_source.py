"""`decoy run --duckdb-source TABLE=DB_PATH` reads an input table from a DuckDB
database file.

Covers the DuckDB-in CLI slice (docs/plans/2026-10-24-cli-duckdb-in-source.md):
the relation is acquired read-only to a temporary Parquet, the in-memory source
is rewritten to that Parquet before engine validation, and the normal parquet
masking path (default + --chunked + native eligibility) runs over it unchanged.
The engine's source schema is never touched; the DuckDB-ness is a CLI-side
snapshot, mirroring the engine's postgres_snapshot DB-input pattern.
"""

from __future__ import annotations

import json as _json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "name", "strategy": "hash", "namespace": "name_ns"},
    {"name": "age", "strategy": "passthrough"},
]
_PEOPLE = [("A00001", "Alice", 31), ("A00002", "Bob", 4), ("A00003", "Carol", 57)]


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [p[0] for p in _PEOPLE],
            "name": [p[1] for p in _PEOPLE],
            "age": [p[2] for p in _PEOPLE],
        }
    )


def _make_duckdb(path: Path, table: str = "people", frame: pd.DataFrame | None = None) -> Path:
    import duckdb

    con = duckdb.connect(str(path))
    try:
        con.register("df", _frame() if frame is None else frame)
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
    finally:
        con.close()
    return path


def _config(tmp_path: Path, sources: dict[str, Any], *, out: str = "out.csv") -> Path:
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": sources,
        "tables": [{"name": "people", "columns": _COLUMNS}],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / out)}},
    }
    import yaml

    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# Parity: a DuckDB source masks exactly as the same data from a Parquet source
# --------------------------------------------------------------------------


def test_duckdb_source_matches_parquet_source(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})  # no YAML source; the flag supplies it
    result = runner.invoke(app, ["run", str(config), "--duckdb-source", f"people={db}"])
    assert result.exit_code == 0, result.output
    got = pd.read_csv(tmp_path / "out.csv", dtype=str)

    # Reference: identical rows from a plain Parquet source.
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    _frame().to_parquet(ref_dir / "in.parquet", index=False)
    ref_config = _config(
        ref_dir,
        {"people": {"type": "file", "format": "parquet", "path": str(ref_dir / "in.parquet")}},
    )
    assert runner.invoke(app, ["run", str(ref_config)]).exit_code == 0
    expected = pd.read_csv(ref_dir / "out.csv", dtype=str)

    pd.testing.assert_frame_equal(got, expected, check_dtype=False)
    # Masking actually happened: id/age passthrough, name hashed.
    assert got["id"].tolist() == ["A00001", "A00002", "A00003"]
    assert got["age"].tolist() == ["31", "4", "57"]
    assert got["name"].tolist() != ["Alice", "Bob", "Carol"]


def test_duckdb_source_json_record_ok(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})
    result = runner.invoke(app, ["run", str(config), "--json", "--duckdb-source", f"people={db}"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "run"
    assert payload["status"] == "ok"


def test_duckdb_source_chunked(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})
    result = runner.invoke(
        app, ["run", str(config), "--chunked", "--duckdb-source", f"people={db}"]
    )
    assert result.exit_code == 0, result.output
    got = pd.read_csv(tmp_path / "out.csv", dtype=str)
    assert got["id"].tolist() == ["A00001", "A00002", "A00003"]


def test_duckdb_source_overrides_declared_yaml_source(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    # The YAML declares a source that does not exist; the flag must override it.
    config = _config(
        tmp_path,
        {"people": {"type": "file", "format": "csv", "path": str(tmp_path / "nope.csv")}},
    )
    result = runner.invoke(app, ["run", str(config), "--duckdb-source", f"people={db}"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# Read-only + temp cleanup
# --------------------------------------------------------------------------


def test_source_database_is_not_modified(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    before = db.read_bytes()
    config = _config(tmp_path, {})
    assert (
        runner.invoke(app, ["run", str(config), "--duckdb-source", f"people={db}"]).exit_code == 0
    )
    assert db.read_bytes() == before


def test_temp_parquet_is_cleaned_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})
    created: list[Path] = []
    _real_mkdtemp = tempfile.mkdtemp

    def _fake_mkdtemp(*args, **kwargs):
        d = _real_mkdtemp(dir=tmp_path)
        created.append(Path(d))
        return d

    monkeypatch.setattr(tempfile, "mkdtemp", _fake_mkdtemp)
    assert (
        runner.invoke(app, ["run", str(config), "--duckdb-source", f"people={db}"]).exit_code == 0
    )
    assert created, "the run did not create a temp dir for the duckdb snapshot"
    assert all(not d.exists() for d in created)


# --------------------------------------------------------------------------
# Usage errors -> EXIT_USAGE, never a traceback
# --------------------------------------------------------------------------


def test_missing_database_file_is_usage_error(tmp_path: Path):
    config = _config(tmp_path, {})
    result = runner.invoke(
        app, ["run", str(config), "--duckdb-source", f"people={tmp_path / 'absent.duckdb'}"]
    )
    assert result.exit_code == EXIT_USAGE
    assert "not found" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "out.csv").exists()


def test_unknown_relation_is_usage_error(tmp_path: Path):
    config = _config(tmp_path, {})
    # The DB holds a `customers` relation, not the `people` the flag asks for,
    # so the catalog lookup misses and the run refuses before masking.
    db = _make_duckdb(tmp_path / "other.duckdb", table="customers")
    result = runner.invoke(app, ["run", str(config), "--duckdb-source", f"people={db}"])
    assert result.exit_code == EXIT_USAGE
    assert "people" in result.output
    assert "not found" in result.output
    assert not (tmp_path / "out.csv").exists()


def test_table_not_in_pipeline_is_usage_error(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})
    result = runner.invoke(app, ["run", str(config), "--duckdb-source", f"ghost={db}"])
    assert result.exit_code == EXIT_USAGE
    assert "ghost" in result.output
    assert not (tmp_path / "out.csv").exists()


@pytest.mark.parametrize("bad", ["peoplenoeq", "1people=x.duckdb", "=x.duckdb", "people="])
def test_malformed_flag_is_usage_error(tmp_path: Path, bad: str):
    config = _config(tmp_path, {})
    result = runner.invoke(app, ["run", str(config), "--duckdb-source", bad])
    assert result.exit_code == EXIT_USAGE
    assert not (tmp_path / "out.csv").exists()


def test_evidence_out_combo_is_refused(tmp_path: Path):
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})
    result = runner.invoke(
        app,
        [
            "run",
            str(config),
            "--duckdb-source",
            f"people={db}",
            "--evidence-out",
            str(tmp_path / "ev.json"),
        ],
    )
    assert result.exit_code == EXIT_USAGE
    assert "evidence-out" in result.output
    assert not (tmp_path / "ev.json").exists()
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# Native eligibility: the rewritten source is an ordinary parquet source
# --------------------------------------------------------------------------


def _broken_status():
    from decoy_engine import NativeCompanionStatus

    return NativeCompanionStatus(
        present=True,
        ok=False,
        abi_expected="1",
        abi_actual="1",
        version="9.9.9",
        reason="kat-corrupt",
        cause=RuntimeError("x"),
    )


def test_duckdb_source_fails_closed_on_broken_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # The rewritten source is parquet (a native-eligible format), so a broken
    # native companion fails closed exactly as it would for a parquet source.
    db = _make_duckdb(tmp_path / "in.duckdb")
    config = _config(tmp_path, {})
    monkeypatch.setattr("decoy_engine.native_companion_status", _broken_status)
    result = runner.invoke(app, ["run", str(config), "--duckdb-source", f"people={db}"])
    assert result.exit_code == EXIT_USAGE
    assert "kat-corrupt" in result.output
    assert not (tmp_path / "out.csv").exists()
