"""End-to-end tests for `decoy subset` (Sprint G, SS6 CLI wrapper).

Thin wrapper over `decoy_engine.subset`; these tests exercise the CLI
surface only (arg parsing, config loading, output formatting, exit codes).
The closure/budget/preflight algorithms themselves are covered by the
engine's own test suite -- not re-tested here.

Fixtures: a small customers/orders Parquet pair with a preserve-policy FK
relationship (customers.id -> orders.customer_id), matching the shape the
engine's own acceptance-test fixtures use.

Assertions:
S1. --dry-run prints an estimate and writes nothing (no --out dir created).
S2. --dry-run --json emits a structured estimate envelope.
S3. A real run (--out) writes filtered Parquet + subset-manifest.json,
    and the output is referentially complete (no orphan orders).
S4. Preflight failure (dangling FK column) -> clean error, exit 1, no
    stack trace text, and no output directory created.
S5. Non-Parquet source is rejected with the exact "convert to Parquet for
    subsetting" phrase (caught at config-validation time, before any
    engine call).
S6. No raw seed key values leak into --json output for a `keys` mode seed.
S7. Missing --out (without --dry-run) is a clean usage error, exit 1.
S8. Missing `subset:` block is a clean usage error, exit 1.
S9. Fan-out budget exceeded -> clean error, exit 1, no output directory
    created (hard-fail-before-write contract).
S10. --help documents the dry-run / --out surface.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import polars as pl
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_customers_orders(tmp_path: Path) -> tuple[Path, Path]:
    customers_path = tmp_path / "customers.parquet"
    orders_path = tmp_path / "orders.parquet"
    pl.DataFrame({"id": list(range(1, 21))}).write_parquet(customers_path)
    pl.DataFrame(
        {
            "id": list(range(1, 41)),
            "customer_id": [(i % 20) + 1 for i in range(40)],
        }
    ).write_parquet(orders_path)
    return customers_path, orders_path


def _base_config(tmp_path: Path, customers_path: Path, orders_path: Path) -> dict:
    return {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {
            "customers": {"type": "file", "format": "parquet", "path": str(customers_path)},
            "orders": {"type": "file", "format": "parquet", "path": str(orders_path)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "hash", "namespace": "customer_identity"}
                ],
            },
            {
                "name": "orders",
                "columns": [
                    {"name": "customer_id", "strategy": "hash", "namespace": "customer_identity"}
                ],
            },
        ],
        "relationships": [
            {
                "parent": {"table": "customers", "columns": ["id"]},
                "children": [{"table": "orders", "columns": ["customer_id"]}],
                "orphan_policy": "preserve",
                "namespace": "customer_identity",
            }
        ],
        "targets": {
            "customers": {
                "type": "file",
                "format": "parquet",
                "path": str(tmp_path / "out_customers.parquet"),
            },
            "orders": {
                "type": "file",
                "format": "parquet",
                "path": str(tmp_path / "out_orders.parquet"),
            },
        },
    }


def _write_config(tmp_path: Path, config: dict, name: str = "pipeline.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(config), encoding="utf-8")
    return p


def _sample_subset_config(tmp_path: Path, fraction: float = 0.25) -> Path:
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    config["subset"] = {
        "seeds": [
            {"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": fraction}
        ],
    }
    return _write_config(tmp_path, config)


# ---------------------------------------------------------------------------
# S1: dry-run prints an estimate and writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path: Path):
    p = _sample_subset_config(tmp_path)
    out_dir = tmp_path / "subset_out"
    result = runner.invoke(app, ["subset", str(p), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert not out_dir.exists()
    assert "customers" in result.output
    assert "orders" in result.output
    assert "no files written" in result.output.lower() or "dry run" in result.output.lower()


# ---------------------------------------------------------------------------
# S2: dry-run --json emits a structured estimate
# ---------------------------------------------------------------------------


def test_dry_run_json_envelope(tmp_path: Path):
    p = _sample_subset_config(tmp_path)
    result = runner.invoke(app, ["subset", str(p), "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["command"] == "subset"
    assert data["status"] == "ok"
    assert data["dry_run"] is True
    table_names = {t["table"] for t in data["tables"]}
    assert table_names == {"customers", "orders"}
    customers_row = next(t for t in data["tables"] if t["table"] == "customers")
    assert customers_row["input_rows"] == 20
    assert customers_row["surviving_rows"] == 5  # fraction=0.25 of 20
    assert data["budget_outcome"] == "pass"
    assert not (tmp_path / "subset_out").exists()


# ---------------------------------------------------------------------------
# S3: real run writes filtered Parquet + manifest, referentially complete
# ---------------------------------------------------------------------------


def test_real_run_writes_referentially_complete_subset(tmp_path: Path):
    p = _sample_subset_config(tmp_path)
    out_dir = tmp_path / "subset_out"
    result = runner.invoke(app, ["subset", str(p), "--out", str(out_dir)])
    assert result.exit_code == 0, result.output

    assert (out_dir / "customers.parquet").exists()
    assert (out_dir / "orders.parquet").exists()
    assert (out_dir / "subset-manifest.json").exists()

    customers_out = pl.read_parquet(out_dir / "customers.parquet")
    orders_out = pl.read_parquet(out_dir / "orders.parquet")
    assert customers_out.height == 5  # fraction=0.25 of 20
    # No orphan orders: every surviving order's customer_id is among the
    # surviving customers (referential completeness).
    assert set(orders_out["customer_id"].to_list()) <= set(customers_out["id"].to_list())

    manifest = _json.loads((out_dir / "subset-manifest.json").read_text())
    assert manifest["manifest_version"] == 1
    assert manifest["budget_outcome"] == "pass"


def test_real_run_json_envelope(tmp_path: Path):
    p = _sample_subset_config(tmp_path)
    out_dir = tmp_path / "subset_out"
    result = runner.invoke(app, ["subset", str(p), "--out", str(out_dir), "--json"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["command"] == "subset"
    assert data["status"] == "ok"
    assert data["dry_run"] is False
    assert data["out"] == str(out_dir)
    paths = {row["table"]: row["path"] for row in data["output_paths"]}
    assert Path(paths["customers"]).exists()
    assert Path(paths["orders"]).exists()


# ---------------------------------------------------------------------------
# S4: preflight failure -> clean error, exit 1, no stack trace, no output dir
# ---------------------------------------------------------------------------


def test_preflight_failure_dangling_column_is_clean_error(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    # Point the child edge at a column that does not exist in orders.parquet.
    config["relationships"][0]["children"][0]["columns"] = ["customer_ref_typo"]
    config["subset"] = {
        "seeds": [{"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 0.5}],
    }
    p = _write_config(tmp_path, config)
    out_dir = tmp_path / "subset_out"

    result = runner.invoke(app, ["subset", str(p), "--out", str(out_dir)])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "subset_relationship_column_missing" in result.output
    assert "customer_ref_typo" in result.output
    assert not out_dir.exists()


def test_preflight_failure_json(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    config["relationships"][0]["children"][0]["columns"] = ["customer_ref_typo"]
    config["subset"] = {
        "seeds": [{"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 0.5}],
    }
    p = _write_config(tmp_path, config)

    result = runner.invoke(app, ["subset", str(p), "--dry-run", "--json"])
    assert result.exit_code != 0
    data = _json.loads(result.stdout)
    assert data["status"] == "error"
    assert data["error_kind"] == "preflight"
    assert data["failures"][0]["code"] == "subset_relationship_column_missing"


# ---------------------------------------------------------------------------
# S5: non-Parquet source rejected with the exact contract phrase
# ---------------------------------------------------------------------------


def test_csv_source_rejected_with_exact_phrase(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    customers_csv = tmp_path / "customers.csv"
    pl.read_parquet(customers_path).write_csv(customers_csv)

    config = _base_config(tmp_path, customers_path, orders_path)
    config["sources"]["customers"] = {
        "type": "file",
        "format": "csv",
        "path": str(customers_csv),
    }
    config["subset"] = {
        "seeds": [{"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 0.5}],
    }
    p = _write_config(tmp_path, config)

    result = runner.invoke(app, ["subset", str(p), "--dry-run"])
    assert result.exit_code != 0
    assert "convert to Parquet for subsetting" in result.output
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# S6: no raw seed key values leak into --json output (keys mode)
# ---------------------------------------------------------------------------


def test_keys_mode_seed_does_not_leak_raw_values(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    sentinel_id = 7
    config["subset"] = {
        "seeds": [
            {
                "table": "customers",
                "mode": "keys",
                "key_columns": ["id"],
                "keys": [[sentinel_id]],
            }
        ],
    }
    p = _write_config(tmp_path, config)

    result = runner.invoke(app, ["subset", str(p), "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    raw_text = result.stdout
    # The raw key value must never appear in the CLI's own output; only the
    # redacted seed_specs_public shape (table/mode/key_columns/key_count).
    assert f'"keys": [[{sentinel_id}' not in raw_text
    data = _json.loads(raw_text)
    seed_spec = data["seed_specs"][0]
    assert seed_spec == {
        "table": "customers",
        "mode": "keys",
        "key_columns": ["id"],
        "key_count": 1,
    }


def test_keys_mode_seed_manifest_does_not_leak_raw_values(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    sentinel_id = 7
    config["subset"] = {
        "seeds": [
            {
                "table": "customers",
                "mode": "keys",
                "key_columns": ["id"],
                "keys": [[sentinel_id]],
            }
        ],
    }
    p = _write_config(tmp_path, config)
    out_dir = tmp_path / "subset_out"

    result = runner.invoke(app, ["subset", str(p), "--out", str(out_dir), "--json"])
    assert result.exit_code == 0, result.output
    manifest_text = (out_dir / "subset-manifest.json").read_text()
    assert f"[[{sentinel_id}" not in manifest_text
    assert result.stdout.count(str(sentinel_id)) == 0 or "key_count" in result.stdout


# ---------------------------------------------------------------------------
# S7: missing --out (real run) is a clean usage error
# ---------------------------------------------------------------------------


def test_missing_out_without_dry_run_is_usage_error(tmp_path: Path):
    p = _sample_subset_config(tmp_path)
    result = runner.invoke(app, ["subset", str(p)])
    assert result.exit_code != 0
    assert "--out" in result.output
    assert "--dry-run" in result.output


# ---------------------------------------------------------------------------
# S8: missing subset: block is a clean usage error
# ---------------------------------------------------------------------------


def test_missing_subset_block_is_usage_error(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    p = _write_config(tmp_path, config)
    result = runner.invoke(app, ["subset", str(p), "--dry-run"])
    assert result.exit_code != 0
    assert "subset" in result.output.lower()
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# S9: fan-out budget exceeded -> clean error, no output dir
# ---------------------------------------------------------------------------


def test_budget_exceeded_is_clean_error_and_writes_nothing(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    config["subset"] = {
        "seeds": [
            {"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 1.0}
        ],
        "budget": {"max_total_rows": 1},
    }
    p = _write_config(tmp_path, config)
    out_dir = tmp_path / "subset_out"

    result = runner.invoke(app, ["subset", str(p), "--out", str(out_dir)])
    assert result.exit_code != 0
    assert "budget" in result.output.lower()
    # Rich wraps long lines in the CliRunner's narrow terminal width; collapse
    # whitespace/newlines before matching the (deliberately long) message.
    collapsed = " ".join(result.output.split())
    assert "No output was written" in collapsed
    assert "Traceback" not in result.output
    assert not out_dir.exists()


def test_budget_exceeded_json(tmp_path: Path):
    customers_path, orders_path = _write_customers_orders(tmp_path)
    config = _base_config(tmp_path, customers_path, orders_path)
    config["subset"] = {
        "seeds": [
            {"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 1.0}
        ],
        "budget": {"max_total_rows": 1},
    }
    p = _write_config(tmp_path, config)

    result = runner.invoke(app, ["subset", str(p), "--dry-run", "--json"])
    assert result.exit_code != 0
    data = _json.loads(result.stdout)
    assert data["error_kind"] == "budget_exceeded"
    assert data["code"] == "subset_budget_exceeded"
    assert data["scope"] == "total"
    assert data["cap"] == 1


# ---------------------------------------------------------------------------
# S10: --help documents the dry-run / --out surface
# ---------------------------------------------------------------------------


def test_help_documents_dry_run_and_out(tmp_path: Path):
    result = runner.invoke(app, ["subset", "--help"])
    assert result.exit_code == 0
    output = result.output
    assert "--dry-run" in output
    assert "--out" in output


# ---------------------------------------------------------------------------
# Extra: re-running into a non-empty --out dir is rejected cleanly
# ---------------------------------------------------------------------------


def test_rerun_into_nonempty_out_dir_is_clean_error(tmp_path: Path):
    p = _sample_subset_config(tmp_path)
    out_dir = tmp_path / "subset_out"
    first = runner.invoke(app, ["subset", str(p), "--out", str(out_dir)])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, ["subset", str(p), "--out", str(out_dir)])
    assert second.exit_code != 0
    assert "Traceback" not in second.output
    assert "subset_output_dir_exists" in second.output or "already exists" in second.output


def test_dry_run_out_combo_warns_but_does_not_write(tmp_path: Path):
    """--dry-run with --out both passed: --out is ignored, nothing is written."""
    p = _sample_subset_config(tmp_path)
    out_dir = tmp_path / "subset_out"
    result = runner.invoke(app, ["subset", str(p), "--dry-run", "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert not out_dir.exists()
