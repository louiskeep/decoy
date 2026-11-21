"""C1l counterfactual matrix (AT-C1l): the lazy run against the base resident run.

Each cell asserts the same exit code, engine route and target bytes. The spy cells pin which
tables the engine reads whole (the resident-fallback pre-pass) and which it keeps lazy.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from decoy_engine.profile import LazySource

from tests.csv_sources import csv_source, file_source
from tests.e2e.run_stream._support import (
    EMAILS as _EMAILS,
)
from tests.e2e.run_stream._support import (
    PLAIN as _PLAIN,
)
from tests.e2e.run_stream._support import (
    ROWS as _ROWS,
)
from tests.e2e.run_stream._support import (
    Probe,
    install_probe,
    run_both,
    write_config,
)
from tests.e2e.run_stream._support import (
    single_build as _single,
)
from tests.keyed_secret import TEST_MASK_SECRET_REF, secret_env


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for var, value in secret_env().items():
        monkeypatch.setenv(var, value)


def _same(lazy: Any, base: Any) -> None:
    assert lazy.exit_code == base.exit_code, (lazy.output, base.output)
    assert lazy.route == base.route
    assert lazy.files == base.files


def test_plain_table_stays_lazy_and_never_materializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = install_probe(monkeypatch, chunk_rows=500)
    lazy, base, seen = run_both(
        monkeypatch, tmp_path, _single(tmp_path, columns=_PLAIN), probe=probe
    )
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)
    assert isinstance(lazy.sources["people"], LazySource)
    assert seen is not None
    # The pre-pass names nothing, and the routes never read the admitted lazy source whole.
    assert seen.prepass_reads == []
    assert not seen.lazy_materialized
    # 6000 rows in chunks of 500: the no-sink lane read the file in at least three batches.
    assert seen.batches >= 3


@pytest.mark.parametrize("kind", ["all_null", "no_stats", "empty"])
def test_null_and_empty_tables_equal_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    n = 0 if kind == "empty" else 200
    email = pa.array([None] * n, pa.string()) if kind == "all_null" else pa.array(_EMAILS[:n])
    table = pa.table({"id": pa.array(range(n), pa.int64()), "email": email})
    # `no_stats` drops the footer null counts the router would otherwise read.
    pq.write_table(table, data / "people.parquet", write_statistics=kind != "no_stats")
    source = file_source(data / "people.parquet", "parquet")

    def build(out: Path) -> tuple[Path, list[Path]]:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 5, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {"people": source},
            "tables": [{"name": "people", "columns": _PLAIN}],
            "targets": {
                "people": {"type": "file", "format": "csv", "path": str(out / "people.csv")}
            },
        }
        return write_config(out / "p.yaml", cfg), [out / "people.csv"]

    lazy, base, _ = run_both(monkeypatch, tmp_path, build)
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)


def test_transform_table_equals_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build = _single(tmp_path, columns=_PLAIN, transforms=[{"op": "dedupe", "columns": ["id"]}])
    lazy, base, _ = run_both(monkeypatch, tmp_path, build)
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)


def test_transform_table_under_the_post_scan_gate_is_read_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = install_probe(monkeypatch)
    build = _single(
        tmp_path,
        columns=_PLAIN,
        transforms=[{"op": "dedupe", "columns": ["id"]}],
        extra={"post_scan": {"integrity": True}},
    )
    lazy, base, seen = run_both(monkeypatch, tmp_path, build, probe=probe)
    _same(lazy, base)
    assert seen is not None
    assert len(seen.prepass_reads) == 1
    assert issubclass(seen.prepass_reads[0], LazySource)


def test_vault_run_reads_the_table_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = install_probe(monkeypatch)
    columns = [
        {"name": "id", "strategy": "passthrough"},
        {"name": "email", "strategy": "hash", "namespace": "em", "vault": True},
    ]
    build = _single(tmp_path, columns=columns)
    vault_args = ("--vault", "{out}/vault.db")
    lazy, base, seen = run_both(monkeypatch, tmp_path, build, args=vault_args, probe=probe)
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)
    assert seen is not None
    assert len(seen.prepass_reads) == 1
    assert issubclass(seen.prepass_reads[0], LazySource)


def test_declared_casting_table_is_read_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = install_probe(monkeypatch)
    csv = tmp_path / "data" / "ages.csv"
    csv.parent.mkdir()
    csv.write_text("id,age\n" + "".join(f"{i},{i % 90}\n" for i in range(_ROWS)), encoding="utf-8")
    columns = [
        {"name": "id", "strategy": "passthrough"},
        {
            "name": "age",
            "strategy": "bucketize",
            "provider_config": {"width": 10, "format": "lower"},
            "logical_type": "integer",
            "parse_format": {"id": "integer/ascii/v1", "signed": True, "bit_width": 64},
            "error_policy": "fail",
            "output_format": {
                "id": "integer/zero-pad/v1",
                "width": 3,
                "width_unit": "code_points",
            },
        },
    ]

    def build(out: Path) -> tuple[Path, list[Path]]:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 5},
            "sources": {"ages": csv_source(csv)},
            "tables": [{"name": "ages", "columns": columns}],
            "targets": {"ages": {"type": "file", "format": "csv", "path": str(out / "ages.csv")}},
        }
        return write_config(out / "p.yaml", cfg), [out / "ages.csv"]

    lazy, base, seen = run_both(monkeypatch, tmp_path, build, probe=probe)
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)
    assert seen is not None
    assert len(seen.prepass_reads) == 1
    assert issubclass(seen.prepass_reads[0], LazySource)


def test_subset_job_equals_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    pq.write_table(pa.table({"id": list(range(1, 201))}), data / "customers.parquet")
    pq.write_table(
        pa.table({"id": list(range(1, 401)), "customer_id": [(i % 200) + 1 for i in range(400)]}),
        data / "orders.parquet",
    )

    def build(out: Path) -> tuple[Path, list[Path]]:
        cfg = {
            "version": 2,
            "global_settings": {"seed": 7, "mask_secret_ref": TEST_MASK_SECRET_REF},
            "sources": {n: file_source(data / f"{n}.parquet", "parquet") for n in _TWO},
            "tables": [
                {
                    "name": "customers",
                    "columns": [{"name": "id", "strategy": "hash", "namespace": "ci"}],
                },
                {
                    "name": "orders",
                    "columns": [
                        {"name": "id", "strategy": "passthrough"},
                        {"name": "customer_id", "strategy": "hash", "namespace": "ci"},
                    ],
                },
            ],
            "relationships": [
                {
                    "parent": {"table": "customers", "columns": ["id"]},
                    "children": [{"table": "orders", "columns": ["customer_id"]}],
                    "orphan_policy": "preserve",
                    "namespace": "ci",
                }
            ],
            "subset": {
                "seeds": [
                    {
                        "table": "customers",
                        "mode": "sample",
                        "key_columns": ["id"],
                        "fraction": 0.25,
                    }
                ]
            },
            "targets": {
                n: {"type": "file", "format": "csv", "path": str(out / f"{n}.csv")} for n in _TWO
            },
        }
        return write_config(out / "p.yaml", cfg), [out / f"{n}.csv" for n in _TWO]

    lazy, base, _ = run_both(monkeypatch, tmp_path, build)
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)
    assert lazy.files["customers.csv"] != b""


_TWO = ("customers", "orders")

_COMPANION = importlib.util.find_spec("decoy_engine_native") is not None


@pytest.mark.skipif(not _COMPANION, reason="needs a real compiled decoy-engine-native companion")
def test_native_lane_run_passes_with_compiled_kernel_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from typer.testing import CliRunner

    from decoy.__main__ import app

    build = _single(tmp_path, columns=_PLAIN)
    out = tmp_path / "native"
    out.mkdir()
    config, targets = build(out)
    result = CliRunner().invoke(app, ["run", str(config), "--native", "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["native_route"]["state"] == "native"
    assert targets[0].exists()


def test_probe_dataclass_reports_lazy_materialization() -> None:
    assert Probe(route_reads=[LazySource]).lazy_materialized
    assert not Probe(route_reads=[pa.Table]).lazy_materialized
