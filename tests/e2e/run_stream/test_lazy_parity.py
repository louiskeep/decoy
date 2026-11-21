"""C1l: a plain `decoy run` hands local mask sources to the engine lazily, with the same output.

Each cell runs the CLI twice on the same config: once as shipped, once with the candidate
builder turned off so every source is read whole (the base resident run). The output bytes,
the exit code and the route's resident fallback keyword are compared.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from decoy_engine.profile import LazySource
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.csv_sources import csv_source, file_source
from tests.keyed_secret import secret_env, with_mask_secret

runner = CliRunner()
_ROWS = 50


def _col(name: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "strategy": "faker", "provider": "person_email", **extra}


def _write_sources(tmp: Path) -> dict[str, dict]:
    ids = list(range(_ROWS))
    emails = [f"user{i}@example.invalid" for i in ids]
    pq.write_table(pa.table({"id": ids, "email": emails}), tmp / "p.parquet", row_group_size=10)
    (tmp / "c.csv").write_text(
        "id,email\n" + "".join(f"{i},{e}\n" for i, e in zip(ids, emails)), encoding="utf-8"
    )
    lines = [f"{i:<6}{e:<30}" for i, e in zip(ids, emails)]
    (tmp / "f.dat").write_text("\n".join(lines) + "\n", encoding="utf-8")
    layout = {
        "columns": [
            {"name": "id", "start": 0, "width": 6},
            {"name": "email", "start": 6, "width": 30},
        ]
    }
    pq.write_table(
        pa.table({"id": pa.array([], pa.int64()), "email": pa.array([], pa.string())}),
        tmp / "e.parquet",
    )
    return {
        "parquet": file_source(tmp / "p.parquet", "parquet"),
        "csv": csv_source(tmp / "c.csv"),
        "fixed_width": file_source(tmp / "f.dat", "fixed_width", layout=layout),
        "empty": file_source(tmp / "e.parquet", "parquet"),
    }


def _config(tmp: Path, name: str, out: Path) -> Path:
    descriptors = _write_sources(tmp)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {"people": descriptors[name]},
        "tables": [
            {
                "name": "people",
                "columns": [{"name": "id", "strategy": "passthrough"}, _col("email")],
            }
        ],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(out)}},
    }
    path = tmp / f"{name}.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def _spy_run_pipeline(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    import decoy_engine

    seen: list[dict[str, Any]] = []
    real = decoy_engine.run_pipeline

    def spy(config: Any, sources: Any, **kwargs: Any) -> Any:
        seen.append({"sources": dict(sources), "kwargs": kwargs})
        return real(config, sources, **kwargs)

    monkeypatch.setattr(decoy_engine, "run_pipeline", spy)
    return seen


@pytest.mark.parametrize("fmt", ["parquet", "csv", "fixed_width", "empty"])
def test_lazy_run_matches_the_resident_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fmt: str
) -> None:
    lazy_out, base_out = tmp_path / f"lazy-{fmt}.csv", tmp_path / f"base-{fmt}.csv"
    seen = _spy_run_pipeline(monkeypatch)
    lazy = runner.invoke(app, ["run", str(_config(tmp_path, fmt, lazy_out))])
    assert lazy.exit_code == 0, lazy.output
    assert len(seen) == 1
    assert isinstance(seen[0]["sources"]["people"], LazySource)
    assert seen[0]["kwargs"]["resident_fallback"] is True

    seen.clear()
    monkeypatch.setattr("decoy.cli.run._execute.lazy_sources", lambda config, base: {})
    base = runner.invoke(app, ["run", str(_config(tmp_path, fmt, base_out))])
    assert base.exit_code == 0, base.output
    assert isinstance(seen[0]["sources"]["people"], pa.Table)
    assert lazy_out.read_bytes() == base_out.read_bytes()


def _fk_config(tmp: Path, out: Path) -> Path:
    parent = pa.table({"id": [f"p{i}" for i in range(20)], "note": [f"n{i}" for i in range(20)]})
    child = pa.table(
        {"cid": [f"c{i}" for i in range(60)], "parent_id": [f"p{i % 20}" for i in range(60)]}
    )
    pq.write_table(parent, tmp / "parent.parquet", row_group_size=7)
    pq.write_table(child, tmp / "child.parquet", row_group_size=7)

    def hashed(name: str, ns: str) -> dict[str, Any]:
        return {"name": name, "strategy": "hash", "namespace": ns}

    cfg = with_mask_secret(
        {
            "version": 2,
            "global_settings": {"seed": 3},
            "sources": {
                "parent": file_source(tmp / "parent.parquet", "parquet"),
                "child": file_source(tmp / "child.parquet", "parquet"),
            },
            "tables": [
                {
                    "name": "parent",
                    "columns": [hashed("id", "ns"), {"name": "note", "strategy": "redact"}],
                },
                {"name": "child", "columns": [hashed("cid", "cns"), hashed("parent_id", "ns")]},
            ],
            "relationships": [
                {
                    "parent": {"table": "parent", "columns": ["id"]},
                    "children": [{"table": "child", "columns": ["parent_id"]}],
                    "orphan_policy": "preserve",
                    "namespace": "ns",
                }
            ],
            "targets": {
                name: {"type": "file", "format": "csv", "path": str(out / f"{name}.csv")}
                for name in ("parent", "child")
            },
        }
    )
    path = tmp / f"fk-{out.name}.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def test_relationship_job_matches_the_resident_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var, value in secret_env().items():
        monkeypatch.setenv(var, value)
    lazy_dir, base_dir = tmp_path / "lazy", tmp_path / "base"
    lazy_dir.mkdir()
    base_dir.mkdir()
    lazy = runner.invoke(app, ["run", str(_fk_config(tmp_path, lazy_dir))])
    assert lazy.exit_code == 0, lazy.output
    monkeypatch.setattr("decoy.cli.run._execute.lazy_sources", lambda config, base: {})
    base = runner.invoke(app, ["run", str(_fk_config(tmp_path, base_dir))])
    assert base.exit_code == 0, base.output
    for name in ("parent", "child"):
        assert (lazy_dir / f"{name}.csv").read_bytes() == (base_dir / f"{name}.csv").read_bytes()


def test_bad_fixed_width_field_exits_3_and_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "f.dat").write_text("      a@example.invalid\n", encoding="utf-8")
    layout = {
        "columns": [
            {"name": "id", "start": 0, "width": 6, "type": "int"},
            {"name": "email", "start": 6, "width": 20},
        ]
    }
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "sources": {"people": file_source(tmp_path / "f.dat", "fixed_width", layout=layout)},
        "tables": [
            {
                "name": "people",
                "columns": [{"name": "id", "strategy": "passthrough"}, _col("email")],
            }
        ],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(tmp_path / "o.csv")}},
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["run", str(path)])
    assert result.exit_code == 3, result.output
    assert "example.invalid" not in result.output
    assert not (tmp_path / "o.csv").exists()
