"""E2E tests for `decoy run` with mixed mask+generate configs (FC-1).

After the CLI is wired to `run_pipeline`, a config that mixes mask
tables (columns:) and generate tables (generate_columns:) must:
- exit 0
- write both target files
- preserve FK join integrity (child FK values are a subset of the parent
  generate table's PK values after remap)

Also covers the `--chunked` + generate-table guard (exit 1).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# --------------------------------------------------------------------------
# Shared config builder
# --------------------------------------------------------------------------


def _mixed_cfg(tmp_path: Path, orders_csv: Path) -> dict:
    """2-table config: generate parent (customers) + mask child (orders).

    customers: generate_columns sequence 1..5 as customer_id (int).
    orders: mask with passthrough; FK to customers.customer_id via
    relationships block; orphan_policy "preserve" keeps source FK values
    unchanged so CSV output is consistent (source FK values "1", "2", "3"
    are string representations of the parent's generated int IDs 1-5).

    Note on orphan_policy: "remap" requires the parent column to be a
    masked node in the plan work list, which it is not for generate-kind
    tables. "preserve" keeps the source FK values as-is; since the source
    orders use FK values "1"-"3" which are the string form of the
    generated parent IDs 1-5, the FK join is coherent in the output CSVs.
    """
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "orders": {"type": "file", "format": "csv", "path": str(orders_csv)},
        },
        "tables": [
            {
                "name": "customers",
                "row_count": 5,
                "generate_columns": [
                    {"name": "customer_id", "type": "sequence", "start": 1, "step": 1}
                ],
            },
            {
                "name": "orders",
                "columns": [
                    {"name": "order_id", "strategy": "passthrough"},
                    {"name": "customer_id", "strategy": "passthrough"},
                    {"name": "amount", "strategy": "passthrough"},
                ],
            },
        ],
        "relationships": [
            {
                "parent": {"table": "customers", "columns": ["customer_id"]},
                "children": [{"table": "orders", "columns": ["customer_id"]}],
                "orphan_policy": "preserve",
                "namespace": "customer_orders",
            }
        ],
        "targets": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "customers_out.csv"),
            },
            "orders": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "orders_out.csv"),
            },
        },
    }


@pytest.fixture
def orders_csv(tmp_path: Path) -> Path:
    """Source CSV for the mask child table.

    FK values "1", "2", "3" are the string representation of the parent's
    generated customer_id sequence (int 1-5). This ensures child FK values
    are a subset of parent PK values when both are read from CSV as strings.
    """
    path = tmp_path / "orders_src.csv"
    pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3"],
            "customer_id": ["1", "2", "3"],  # match parent sequence 1-5 as strings
            "amount": ["100", "200", "300"],
        }
    ).to_csv(path, index=False)
    return path


# --------------------------------------------------------------------------
# Mixed config success tests
# --------------------------------------------------------------------------


class TestMixedConfigSuccess:
    """After run_pipeline is wired, a mixed mask+generate config succeeds."""

    def test_mixed_config_exits_zero(self, tmp_path, orders_csv):
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", str(config_path)])

        assert result.exit_code == 0, f"expected exit 0; got {result.exit_code}\n{result.output}"

    def test_generate_target_file_written(self, tmp_path, orders_csv):
        """The generate-kind target (customers_out.csv) must be written."""
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        runner.invoke(app, ["run", str(config_path)])

        assert (tmp_path / "customers_out.csv").exists(), "generate target file not written"

    def test_mask_target_file_written(self, tmp_path, orders_csv):
        """The mask-kind target (orders_out.csv) must be written."""
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        runner.invoke(app, ["run", str(config_path)])

        assert (tmp_path / "orders_out.csv").exists(), "mask target file not written"

    def test_generate_table_has_declared_row_count(self, tmp_path, orders_csv):
        """The generate output must have the declared row_count (5)."""
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        runner.invoke(app, ["run", str(config_path)])

        customers_df = pd.read_csv(tmp_path / "customers_out.csv", dtype=str)
        assert len(customers_df) == 5, f"expected 5 generated rows; got {len(customers_df)}"

    def test_mask_table_preserves_source_row_count(self, tmp_path, orders_csv):
        """The mask output must have the same row count as the source (3)."""
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        runner.invoke(app, ["run", str(config_path)])

        orders_df = pd.read_csv(tmp_path / "orders_out.csv", dtype=str)
        assert len(orders_df) == 3, f"expected 3 masked rows; got {len(orders_df)}"

    def test_fk_join_preserved_after_remap(self, tmp_path, orders_csv):
        """Child FK values must be a subset of the generate parent's PK values.

        The source orders use FK values "1", "2", "3" which are the string
        form of the parent's generated customer_id sequence 1-5. The
        preserve orphan policy keeps source FK values unchanged. After the
        run, the output CSVs are join-coherent: every child customer_id
        appears as a string in the parent customer_id column.
        """
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", str(config_path)])
        assert result.exit_code == 0, result.output

        parent_ids = set(
            pd.read_csv(tmp_path / "customers_out.csv", dtype=str)["customer_id"].tolist()
        )
        child_fk_ids = set(
            pd.read_csv(tmp_path / "orders_out.csv", dtype=str)["customer_id"].tolist()
        )

        assert child_fk_ids.issubset(parent_ids), (
            f"FK join broken: child IDs {child_fk_ids} not subset of parent IDs {parent_ids}"
        )

    def test_json_output_exits_zero_with_ok_status(self, tmp_path, orders_csv):
        """--json output must carry status='ok' and exit 0 on a mixed config."""
        import json

        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", str(config_path), "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "ok"


# --------------------------------------------------------------------------
# --chunked + generate-table guard
# --------------------------------------------------------------------------


class TestChunkedGenerateGuard:
    """--chunked combined with a generate-table config must exit with EXIT_USAGE."""

    def test_chunked_plus_generate_only_exits_usage(self, tmp_path):
        """Pure-generate config + --chunked must exit 1 with a clear message."""
        cfg = {
            "version": 1,
            "global_settings": {"seed": 1},
            "tables": [
                {
                    "name": "synth",
                    "row_count": 5,
                    "generate_columns": [
                        {"name": "id", "type": "sequence", "start": 1, "step": 1}
                    ],
                }
            ],
            "targets": {
                "synth": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")},
            },
        }
        config_path = tmp_path / "gen.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", str(config_path), "--chunked"])

        assert result.exit_code == 1, f"expected exit 1 (usage); got {result.exit_code}\n{result.output}"
        assert "chunked" in result.output.lower() or "generate" in result.output.lower(), (
            f"error message should mention chunked or generate; got: {result.output}"
        )

    def test_chunked_plus_mixed_config_exits_usage(self, tmp_path, orders_csv):
        """Mixed config + --chunked must exit 1 (chunked only supports mask-only)."""
        cfg = _mixed_cfg(tmp_path, orders_csv)
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", str(config_path), "--chunked"])

        assert result.exit_code == 1, f"expected exit 1 (usage); got {result.exit_code}\n{result.output}"
        assert "chunked" in result.output.lower() or "generate" in result.output.lower(), (
            f"error message should mention chunked or generate; got: {result.output}"
        )
