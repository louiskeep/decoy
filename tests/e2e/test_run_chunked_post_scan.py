"""AT-29: `decoy run --chunked` and the post-scan key check.

The chunked route never runs the relationship key check. A config that asks for it
(`post_scan.integrity: true`) is refused before any read; a config that only declares
relationships runs with one value-free warning and a record in the run result.
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
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_REFUSAL = (
    "--chunked does not support post-scan integrity (post_scan.integrity is true). "
    "Run without --chunked, or turn post_scan.integrity off."
)
_WARNING = (
    "--chunked does not run the relationship key check. "
    "Run without --chunked to check the declared relationships."
)
_CODE = "chunked_key_check_not_run"


def _hash_col(name: str, namespace: str) -> dict:
    return {"name": name, "strategy": "hash", "namespace": namespace, "dtype": "string"}


def _pipeline(tmp_path: Path, *, relationships: bool, integrity: bool) -> Path:
    out = tmp_path / "outdir"
    out.mkdir()
    pd.DataFrame({"id": ["p1", "p2"]}).to_csv(tmp_path / "parent.csv", index=False)
    pd.DataFrame({"cid": ["c1", "c2"], "parent_id": ["p1", "p2"]}).to_csv(
        tmp_path / "child.csv", index=False
    )
    cfg: dict = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {
            "parent": csv_source(tmp_path / "parent.csv"),
            "child": csv_source(tmp_path / "child.csv"),
        },
        "tables": [
            {"name": "parent", "columns": [_hash_col("id", "ns")]},
            {"name": "child", "columns": [_hash_col("cid", "cns"), _hash_col("parent_id", "ns")]},
        ],
        "targets": {
            "parent": {"type": "file", "format": "csv", "path": str(out / "parent.csv")},
            "child": {"type": "file", "format": "csv", "path": str(out / "child.csv")},
        },
    }
    if relationships:
        cfg["relationships"] = [
            {
                "parent": {"table": "parent", "columns": ["id"]},
                "children": [{"table": "child", "columns": ["parent_id"]}],
                "orphan_policy": "remap",
                "namespace": "ns",
            }
        ]
    if integrity:
        cfg["post_scan"] = {"integrity": True}
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _codes(output: str) -> list[str]:
    return [w["code"] for w in json.loads(output)["warnings"]]


def test_integrity_requested_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=True)
    result = runner.invoke(app, ["run", str(cfg), "--chunked"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert _REFUSAL in " ".join(result.output.split())
    assert list((tmp_path / "outdir").iterdir()) == []


def test_relationships_only_runs_with_a_warning_and_a_record(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=False)
    result = runner.invoke(app, ["run", str(cfg), "--chunked", "--json"])
    assert result.exit_code == EXIT_OK, result.output
    warnings = json.loads(result.stdout)["warnings"]
    assert [w["message"] for w in warnings if w["code"] == _CODE] == [_WARNING]
    assert str(tmp_path) not in result.stderr


def test_neither_behaves_as_before(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=False, integrity=False)
    result = runner.invoke(app, ["run", str(cfg), "--chunked", "--json"])
    assert result.exit_code == EXIT_OK, result.output
    assert "key check" not in result.stderr
    assert _CODE not in _codes(result.stdout)


def test_refusal_comes_before_any_source_is_opened(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=True)
    (tmp_path / "parent.csv").unlink()
    result = runner.invoke(app, ["run", str(cfg), "--chunked"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert _REFUSAL in " ".join(result.output.split())
    assert "not found" not in result.output.lower()


def test_refusal_comes_before_duckdb_staging(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=True)
    doc = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    del doc["sources"]["parent"]
    cfg.write_text(yaml.safe_dump(doc), encoding="utf-8")
    missing = tmp_path / "no-such.duckdb"
    result = runner.invoke(
        app, ["run", str(cfg), "--chunked", "--duckdb-source", f"parent={missing}"]
    )
    assert result.exit_code == EXIT_USAGE, result.output
    assert _REFUSAL in " ".join(result.output.split())


def test_null_sources_refuses_before_duckdb_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=True)
    doc = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    doc["sources"] = None
    cfg.write_text(yaml.safe_dump(doc), encoding="utf-8")

    def _staged(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("staged")

    monkeypatch.setattr("decoy.cli.run._prepare.acquire_relation", _staged)
    db = tmp_path / "no-such.duckdb"
    flags = ["--duckdb-source", f"parent={db}", "--duckdb-source", f"child={db}"]
    result = runner.invoke(app, ["run", str(cfg), "--chunked", *flags])
    assert result.exit_code == EXIT_USAGE, result.output
    assert _REFUSAL in " ".join(result.output.split())
    assert "staged" not in result.output


def test_the_validated_config_is_checked_again_before_the_chunked_route() -> None:
    from decoy.cli.run._execute import _check_chunked_tables, _ChunkedIntegrityError

    with pytest.raises(_ChunkedIntegrityError) as caught:
        _check_chunked_tables({"post_scan": {"integrity": True}, "tables": []})
    assert str(caught.value) == _REFUSAL


def test_malformed_config_still_gets_its_validation_error(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=True)
    doc = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    del doc["sources"]
    cfg.write_text(yaml.safe_dump(doc), encoding="utf-8")
    result = runner.invoke(app, ["run", str(cfg), "--chunked"])
    assert result.exit_code != EXIT_OK, result.output
    assert _REFUSAL not in " ".join(result.output.split())


def test_warning_prints_once_in_human_mode(tmp_path: Path) -> None:
    cfg = _pipeline(tmp_path, relationships=True, integrity=False)
    result = runner.invoke(app, ["run", str(cfg), "--chunked"])
    assert result.exit_code == EXIT_OK, result.output
    text = " ".join((result.stdout + result.stderr).split())
    assert text.count(_WARNING) == 1
