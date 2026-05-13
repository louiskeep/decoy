"""End-to-end tests for `decoy demo` -- both the single-table flow and --ref."""

from __future__ import annotations

import json as _json
import re
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from decoy.__main__ import app


runner = CliRunner()

_HEX12 = re.compile(r"^[0-9a-f]{12}$")


# -- help + single-table flow ------------------------------------------


def test_demo_help_includes_examples():
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "See also:" in result.stdout


def test_demo_help_documents_ref_flag():
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "--ref" in result.stdout
    assert "--rows" in result.stdout


def test_demo_runs_end_to_end(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir)])
    assert result.exit_code == 0, result.stdout

    assert (out_dir / "patients.csv").exists()
    assert (out_dir / "patients_masked.csv").exists()
    assert (out_dir / "scan.json").exists()
    assert (out_dir / "forecast.json").exists()
    assert (out_dir / "pipeline.yaml").exists()

    masked = (out_dir / "patients_masked.csv").read_text()
    assert "alice@example.com" not in masked
    assert "111-22-3333" not in masked
    assert "REDACTED" in masked


def test_demo_json_envelope(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--json"])
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "demo"
    assert payload["variant"] == "single"
    assert payload["status"] == "ok"
    assert payload["pii_columns"] >= 3
    assert payload["top_disguise"]


def test_demo_quiet_produces_empty_stdout(tmp_path: Path):
    out_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert (out_dir / "patients_masked.csv").exists()


# -- --ref variant ------------------------------------------------------


def test_demo_ref_creates_all_three_tables_and_pipelines(tmp_path: Path):
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0, result.stdout

    for name in ("customers", "orders", "payments"):
        assert (out_dir / f"{name}.csv").exists(), f"missing {name}.csv"
        assert (out_dir / f"{name}_masked.csv").exists(), f"missing {name}_masked.csv"
        assert (out_dir / f"{name}_pipeline.yaml").exists(), f"missing {name}_pipeline.yaml"


def test_demo_ref_cleans_up_empty_mappings_dir(tmp_path: Path):
    """The engine eagerly creates `mappings/` on Masker init even when no
    transform writes to it. The demo removes it post-run since the
    deterministic transforms have nothing to persist.
    """
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0
    # Either the mappings dir doesn't exist (removed post-run) or it exists
    # but is empty (cleanup failed harmlessly).
    mappings_dir = out_dir / "mappings"
    if mappings_dir.exists():
        assert not any(mappings_dir.iterdir()), \
            "mappings/ should be empty -- deterministic transforms don't use it"


def test_demo_ref_each_table_has_requested_row_count(tmp_path: Path):
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0

    for name in ("customers", "orders", "payments"):
        raw = pd.read_csv(out_dir / f"{name}.csv")
        masked = pd.read_csv(out_dir / f"{name}_masked.csv")
        assert len(raw) == 50, f"{name}.csv: expected 50 rows, got {len(raw)}"
        assert len(masked) == 50, f"{name}_masked.csv: expected 50 rows, got {len(masked)}"


def test_demo_ref_preserves_referential_integrity(tmp_path: Path):
    """The whole point of --ref: FK joins survive masking."""
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0

    cust = pd.read_csv(out_dir / "customers_masked.csv")
    ord_ = pd.read_csv(out_dir / "orders_masked.csv")
    pay = pd.read_csv(out_dir / "payments_masked.csv")

    cust_ids = set(cust["customer_id"].astype(str))
    ord_cust_ids = set(ord_["customer_id"].astype(str))
    orphans = ord_cust_ids - cust_ids
    assert orphans == set(), f"orphan customer_id(s) in orders: {sorted(orphans)[:5]}"

    ord_ids = set(ord_["order_id"].astype(str))
    pay_ord_ids = set(pay["order_id"].astype(str))
    orphans = pay_ord_ids - ord_ids
    assert orphans == set(), f"orphan order_id(s) in payments: {sorted(orphans)[:5]}"


def test_demo_ref_fk_columns_are_hex_hashes(tmp_path: Path):
    """Confirm the FK columns landed as hex hashes, not as the original
    `C00042` / `O00042` / `P00042` patterns.
    """
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0

    cust = pd.read_csv(out_dir / "customers_masked.csv")
    ord_ = pd.read_csv(out_dir / "orders_masked.csv")
    pay = pd.read_csv(out_dir / "payments_masked.csv")

    for value in cust["customer_id"]:
        assert _HEX12.match(str(value)), f"unexpected customer_id format: {value!r}"
    for value in ord_["order_id"]:
        assert _HEX12.match(str(value)), f"unexpected order_id format: {value!r}"
    for value in pay["payment_id"]:
        assert _HEX12.match(str(value)), f"unexpected payment_id format: {value!r}"


def test_demo_ref_determinism_is_what_makes_it_work(tmp_path: Path):
    """The crux: hash(value) in pipeline A equals hash(value) in pipeline B
    only because the transforms are deterministic. Spot-check that the same
    raw customer_id resolves to the same masked customer_id in both
    customers and orders.
    """
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0

    raw_cust = pd.read_csv(out_dir / "customers.csv")
    masked_cust = pd.read_csv(out_dir / "customers_masked.csv")
    raw_ord = pd.read_csv(out_dir / "orders.csv")
    masked_ord = pd.read_csv(out_dir / "orders_masked.csv")

    # Build raw -> masked customer_id map from the customers table, then
    # check each row in the orders table matches.
    cust_map = dict(
        zip(raw_cust["customer_id"].astype(str), masked_cust["customer_id"].astype(str))
    )
    for raw_cid, masked_cid in zip(
        raw_ord["customer_id"].astype(str), masked_ord["customer_id"].astype(str)
    ):
        assert cust_map[raw_cid] == masked_cid, (
            f"determinism break: customer_id {raw_cid} -> {cust_map[raw_cid]}"
            f" in customers vs {masked_cid} in orders"
        )


def test_demo_ref_masks_actually_change_values(tmp_path: Path):
    """Sanity check: the masked PII columns don't equal the raw ones."""
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50"]
    )
    assert result.exit_code == 0

    raw = pd.read_csv(out_dir / "customers.csv")
    masked = pd.read_csv(out_dir / "customers_masked.csv")

    # customer_id moved from C##### -> 12-char hex.
    assert all(str(v).startswith("C") for v in raw["customer_id"])
    assert all(_HEX12.match(str(v)) for v in masked["customer_id"])

    # ssn changed (was XXX-XX-XXXX, now sha256 hex).
    assert (raw["ssn"] != masked["ssn"]).all()

    # email was faked away -- the literal raw values don't leak through.
    # Note: Faker's email provider uses example.com / example.net / example.org
    # by design, so we can't assert "no @example.com" -- Faker's replacements
    # routinely land there. The masking contract is that each row's email
    # changed, not that the domain changed.
    assert (raw["email"].astype(str) != masked["email"].astype(str)).all()


def test_demo_ref_json_envelope_shape(tmp_path: Path):
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50", "--json"]
    )
    assert result.exit_code == 0
    payload = _json.loads(result.stdout)
    assert payload["command"] == "demo"
    assert payload["variant"] == "ref"
    assert payload["status"] == "ok"
    assert payload["fk_strategy"] == "hash-sha256-truncated"
    assert set(payload["pipelines"]) == {"customers", "orders", "payments"}
    assert set(payload["masked"]) == {"customers", "orders", "payments"}
    assert payload["integrity"]["customers_rows"] == 50
    assert payload["integrity"]["orders_rows"] == 50
    assert payload["integrity"]["payments_rows"] == 50
    assert payload["integrity"]["orders_customer_id_orphans"] == 0
    assert payload["integrity"]["payments_order_id_orphans"] == 0


def test_demo_ref_quiet_produces_empty_stdout(tmp_path: Path):
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "50", "--quiet"]
    )
    assert result.exit_code == 0
    assert result.stdout == ""
    assert (out_dir / "customers_masked.csv").exists()
    assert (out_dir / "orders_masked.csv").exists()
    assert (out_dir / "payments_masked.csv").exists()


def test_demo_ref_uses_separate_default_dir(tmp_path: Path, monkeypatch):
    """`decoy demo --ref` (no --dir) drops into decoy_demo_ref/, not decoy_demo/."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["demo", "--ref", "--rows", "20"])
    assert result.exit_code == 0
    assert (tmp_path / "decoy_demo_ref").is_dir()
    assert (tmp_path / "decoy_demo_ref" / "customers.csv").exists()
    assert not (tmp_path / "decoy_demo").exists()


def test_demo_ref_rows_below_minimum_rejected(tmp_path: Path):
    out_dir = tmp_path / "demo_ref"
    result = runner.invoke(
        app, ["demo", "--ref", "--dir", str(out_dir), "--rows", "5"]
    )
    assert result.exit_code != 0
