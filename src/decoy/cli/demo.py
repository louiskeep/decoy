"""`decoy demo` -- 30-second end-to-end walkthrough on bundled sample data.

Default flow: a small single-table CSV, scanned (STORM) -> recommended (FORECAST)
-> masked. All artifacts land in `./decoy_demo/`.

With `--ref`: three related CSVs (customers, orders, payments) with foreign-key
relationships, masked through three pipelines that each apply `hash` to the
FK columns. Determinism is what preserves the joins -- not any shared state.
Same input -> same hash -> joins work across pipelines with no coordination.
"""

from __future__ import annotations

import csv
import json as _json
import random
from pathlib import Path

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.theme import accent, code, error, hint, success


_DEMO_EPILOG = """\
Examples:

  decoy demo
    Run the simple scan -> forecast -> mask walkthrough in ./decoy_demo/.

  decoy demo --ref
    Generate 3 related CSVs (customers, orders, payments) with FK
    relationships and mask all three with deterministic hashing.
    FK joins survive masking without any shared state. ~1000 rows each.

  decoy demo --ref --rows 5000 --dir my_demo
    Same, but 5K rows per dataset and a custom output directory.

  decoy demo --json
    Same flow, but emit a JSON summary instead of cards.

See also: decoy storm scan, decoy forecast, decoy run.
"""


# ---------------------------------------------------------------------------
# Single-table demo (default)
# ---------------------------------------------------------------------------


def _write_sample_csv(path: Path) -> None:
    rows = [
        ("customer_id", "first_name", "last_name", "email", "ssn", "dob", "zip", "gender"),
        ("C001", "Alice",   "Anderson", "alice@example.com",   "111-22-3333", "1990-01-15", "10001", "F"),
        ("C002", "Bob",     "Brown",    "bob@example.com",     "222-33-4444", "1985-05-20", "90210", "M"),
        ("C003", "Carol",   "Carter",   "carol@example.com",   "333-44-5555", "1992-08-30", "60601", "F"),
        ("C004", "David",   "Davis",    "david@example.com",   "444-55-6666", "1988-11-04", "77001", "M"),
        ("C005", "Eve",     "Evans",    "eve@example.com",     "555-66-7777", "2000-02-14", "94016", "F"),
        ("C006", "Frank",   "Foster",   "frank@example.com",   "666-77-8888", "1979-09-09", "30301", "M"),
        ("C007", "Grace",   "Green",    "grace@example.com",   "777-88-9999", "1995-12-25", "10001", "F"),
        ("C008", "Henry",   "Harris",   "henry@example.com",   "888-99-0000", "1983-06-18", "20001", "M"),
        ("C009", "Iris",    "Ingram",   "iris@example.com",    "999-00-1111", "1997-03-22", "33101", "F"),
        ("C010", "Jack",    "Johnson",  "jack@example.com",    "000-11-2222", "1991-07-11", "75201", "M"),
    ]
    path.write_text("\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8")


def _build_pipeline_yaml(input_path: Path, output_path: Path) -> str:
    return f"""\
version: '1.0'
global_settings:
  seed: 42
input:
  type: csv
  path: '{input_path.as_posix()}'
  csv_options:
    delimiter: ','
    encoding: utf-8
output:
  type: csv
  path: '{output_path.as_posix()}'
  csv_options:
    delimiter: ','
    encoding: utf-8
masking_rules:
  # customer_id uses `hash` (SHA-256, truncated to 12 hex chars).
  # Hash is a pure function: same input always produces the same output with
  # no state or mapping store. For FK joins across related tables, the same
  # hash produces the same output everywhere -- see `decoy demo --ref`.
  - column: customer_id
    type: hash
    algorithm: sha256
    truncate: 12
  - column: first_name
    type: faker
    faker_type: first_name
  - column: last_name
    type: faker
    faker_type: last_name
  - column: email
    type: faker
    faker_type: email
  - column: ssn
    type: hash
    algorithm: sha256
  - column: dob
    type: date_shift
    jitter_days: 30
  - column: zip
    type: redact
    keep_chars: 3
  - column: gender
    type: passthrough
"""


def _run_single_demo(state: OutputState, out_dir: Path) -> int:
    """Original one-CSV walkthrough. Returns the exit code (always 0 on success)."""
    sample_csv = out_dir / "patients.csv"
    masked_csv = out_dir / "patients_masked.csv"
    pipeline_yaml = out_dir / "pipeline.yaml"
    scan_json = out_dir / "scan.json"
    forecast_json = out_dir / "forecast.json"

    if state.mode is OutputMode.default:
        state.console.print(accent("[1/4]"), "Writing sample dataset...")
    _write_sample_csv(sample_csv)

    if state.mode is OutputMode.default:
        state.console.print(accent("[2/4]"), "Scanning with STORM...")
    import pandas as pd
    from decoy_engine import run_storm

    df = pd.read_csv(sample_csv)
    profile = run_storm(df, source_label=sample_csv.name, sample_strategy="full")
    scan_json.write_text(_json.dumps(profile.to_dict(), indent=2))

    if state.mode is OutputMode.default:
        state.console.print(accent("[3/4]"), "Asking FORECAST for a Disguise...")
    from decoy_engine import recommend

    report = recommend(profile)
    forecast_json.write_text(_json.dumps(report.to_dict(), indent=2))

    if state.mode is OutputMode.default:
        state.console.print(accent("[4/4]"), "Running masking pipeline...")
    pipeline_yaml.write_text(_build_pipeline_yaml(sample_csv, masked_csv))
    from decoy_engine import Masker

    Masker(str(pipeline_yaml)).mask()

    pii_columns = sum(1 for f in profile.fields if f.pii_score >= 0.6)
    top = report.disguise_recommendations[0] if report.disguise_recommendations else None

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "demo",
                "variant": "single",
                "status": "ok",
                "dir": str(out_dir),
                "scan": str(scan_json),
                "forecast": str(forecast_json),
                "masked": str(masked_csv),
                "pii_columns": pii_columns,
                "top_disguise": top.name if top else None,
            },
        )
        return 0

    if state.mode is OutputMode.quiet:
        return 0

    state.console.print()
    render_card(
        state,
        command="decoy demo",
        facts=[
            ("Sample dataset", str(sample_csv)),
            ("Rows scanned", str(profile.row_count)),
            ("PII columns", f"{pii_columns} of {len(profile.fields)}"),
            ("Top recommendation", top.name if top else "(none)"),
            ("Masked output", str(masked_csv)),
        ],
        next_hint=f"head {masked_csv}",
        status="ok",
    )
    state.console.print(success("OK"), "demo complete.")
    return 0


# ---------------------------------------------------------------------------
# Referential-integrity demo (--ref)
# ---------------------------------------------------------------------------


_FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Henry",
    "Iris", "Jack", "Kate", "Liam", "Mia", "Noah", "Olivia", "Paul",
    "Quinn", "Rosa", "Sam", "Tara", "Uma", "Vince", "Wendy", "Xavier",
    "Yara", "Zane",
]
_LAST_NAMES = [
    "Anderson", "Brown", "Carter", "Davis", "Evans", "Foster", "Green",
    "Harris", "Ingram", "Johnson", "Klein", "Lopez", "Mitchell", "Nash",
    "Owens", "Patel", "Quinn", "Rivera", "Singh", "Thomas", "Underwood",
    "Vance", "Wright", "Young", "Zhang",
]
_DOMAINS = ["example.com", "acme.io", "samplecorp.net", "testmail.org"]
_ZIPS = [
    "10001", "90210", "60601", "77001", "94016", "30301", "20001", "33101",
    "75201", "98101", "02101", "15201", "43215", "55401", "80202",
]
_GENDERS = ["F", "M", "X"]
_ORDER_STATUSES = ["pending", "shipped", "delivered", "cancelled", "refunded"]
_PAYMENT_METHODS = ["card", "ach", "wire", "check", "crypto"]

# Length we truncate the SHA-256 hex output to for FK columns. 12 hex chars
# = 48 bits of entropy, comfortably collision-free at the demo's 1K-row
# scale and still readable in the output.
_FK_HASH_TRUNCATE = 12


def _generate_ref_datasets(out_dir: Path, n_rows: int, seed: int = 42) -> tuple[int, int, int]:
    """Build customers / orders / payments CSVs with FK relationships.

    `n_rows` rows per table. customer_id and order_id are dense (`C00001`,
    `O00001`, ...). Each order picks a random customer_id; each payment picks
    a random order_id -- so the FK relationships have realistic many-to-one
    structure (some customers have multiple orders, some orders have multiple
    payments, some have none at all) instead of a degenerate 1:1:1.
    """
    rng = random.Random(seed)

    customers_path = out_dir / "customers.csv"
    orders_path = out_dir / "orders.csv"
    payments_path = out_dir / "payments.csv"

    # Customers -- the PK source.
    customer_ids: list[str] = []
    with customers_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "customer_id", "first_name", "last_name", "email", "ssn",
            "dob", "zip", "phone", "gender",
        ])
        for i in range(1, n_rows + 1):
            cid = f"C{i:05d}"
            customer_ids.append(cid)
            fn = rng.choice(_FIRST_NAMES)
            ln = rng.choice(_LAST_NAMES)
            email = f"{fn.lower()}.{ln.lower()}{i}@{rng.choice(_DOMAINS)}"
            ssn = f"{rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
            year = rng.randint(1950, 2005)
            month = rng.randint(1, 12)
            day = rng.randint(1, 28)
            dob = f"{year:04d}-{month:02d}-{day:02d}"
            zip_ = rng.choice(_ZIPS)
            phone = f"({rng.randint(200, 999)}) {rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
            gender = rng.choice(_GENDERS)
            w.writerow([cid, fn, ln, email, ssn, dob, zip_, phone, gender])

    # Orders -- each row picks a customer_id (with replacement -> realistic FK skew).
    order_ids: list[str] = []
    with orders_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["order_id", "customer_id", "amount", "order_date", "status"])
        for i in range(1, n_rows + 1):
            oid = f"O{i:05d}"
            order_ids.append(oid)
            cid = rng.choice(customer_ids)
            amount = f"{rng.uniform(10, 5000):.2f}"
            month = rng.randint(1, 12)
            day = rng.randint(1, 28)
            order_date = f"2025-{month:02d}-{day:02d}"
            status = rng.choice(_ORDER_STATUSES)
            w.writerow([oid, cid, amount, order_date, status])

    # Payments -- each row picks an order_id (with replacement).
    with payments_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["payment_id", "order_id", "amount", "method", "paid_at"])
        for i in range(1, n_rows + 1):
            pid = f"P{i:05d}"
            oid = rng.choice(order_ids)
            amount = f"{rng.uniform(5, 5000):.2f}"
            method = rng.choice(_PAYMENT_METHODS)
            month = rng.randint(1, 12)
            day = rng.randint(1, 28)
            paid_at = f"2025-{month:02d}-{day:02d}"
            w.writerow([pid, oid, amount, method, paid_at])

    return n_rows, n_rows, n_rows


def _build_customers_yaml(out_dir: Path) -> str:
    in_path = (out_dir / "customers.csv").as_posix()
    out_path = (out_dir / "customers_masked.csv").as_posix()
    return f"""\
# customers pipeline -- the PK source for the FK relationships.
#
# customer_id uses `hash` (SHA-256, truncated to {_FK_HASH_TRUNCATE} hex chars).
# Hash is a pure function: same input always produces the same output, with
# no local state and no coordination between pipelines. Every
# pipeline that hashes the same customer_id produces the same hex string,
# so FK joins survive masking automatically -- that's the whole story.
version: '1.0'
global_settings:
  seed: 42
input:
  type: csv
  path: '{in_path}'
  csv_options:
    delimiter: ','
    encoding: utf-8
output:
  type: csv
  path: '{out_path}'
  csv_options:
    delimiter: ','
    encoding: utf-8
masking_rules:
  - column: customer_id
    type: hash
    algorithm: sha256
    truncate: {_FK_HASH_TRUNCATE}
  - column: first_name
    type: faker
    faker_type: first_name
  - column: last_name
    type: faker
    faker_type: last_name
  - column: email
    type: faker
    faker_type: email
  - column: ssn
    type: hash
    algorithm: sha256  # full 64-char hash for the canonical PII column
  - column: dob
    type: date_shift
    jitter_days: 30
  - column: zip
    type: redact
    keep_chars: 3
  - column: phone
    type: faker
    faker_type: phone_number
  - column: gender
    type: passthrough
"""


def _build_orders_yaml(out_dir: Path) -> str:
    in_path = (out_dir / "orders.csv").as_posix()
    out_path = (out_dir / "orders_masked.csv").as_posix()
    return f"""\
# orders pipeline -- customer_id uses the SAME hash config as the customers
# pipeline. No shared state needed: hash is deterministic, so the masked
# customer_id in orders matches the masked customer_id in customers row by
# row, joining cleanly.
version: '1.0'
global_settings:
  seed: 42
input:
  type: csv
  path: '{in_path}'
  csv_options:
    delimiter: ','
    encoding: utf-8
output:
  type: csv
  path: '{out_path}'
  csv_options:
    delimiter: ','
    encoding: utf-8
masking_rules:
  - column: order_id
    type: hash
    algorithm: sha256
    truncate: {_FK_HASH_TRUNCATE}
  - column: customer_id  # same hash config as customers_pipeline.yaml -> joinable
    type: hash
    algorithm: sha256
    truncate: {_FK_HASH_TRUNCATE}
  - column: amount
    type: passthrough
  - column: order_date
    type: date_shift
    jitter_days: 30
  - column: status
    type: passthrough
"""


def _build_payments_yaml(out_dir: Path) -> str:
    in_path = (out_dir / "payments.csv").as_posix()
    out_path = (out_dir / "payments_masked.csv").as_posix()
    return f"""\
# payments pipeline -- order_id uses the SAME hash config as the orders
# pipeline. Determinism preserves the order_id join the same way customer_id
# is preserved between customers and orders.
version: '1.0'
global_settings:
  seed: 42
input:
  type: csv
  path: '{in_path}'
  csv_options:
    delimiter: ','
    encoding: utf-8
output:
  type: csv
  path: '{out_path}'
  csv_options:
    delimiter: ','
    encoding: utf-8
masking_rules:
  - column: payment_id
    type: hash
    algorithm: sha256
    truncate: {_FK_HASH_TRUNCATE}
  - column: order_id  # same hash config as orders_pipeline.yaml -> joinable
    type: hash
    algorithm: sha256
    truncate: {_FK_HASH_TRUNCATE}
  - column: amount
    type: passthrough
  - column: method
    type: passthrough
  - column: paid_at
    type: date_shift
    jitter_days: 7
"""


def _verify_ref_integrity(out_dir: Path) -> dict:
    """After masking all three tables, confirm the FKs still resolve.

    Reads the masked outputs and computes: how many customer_id values in
    masked_orders DON'T appear in masked_customers (should be 0), and how
    many order_id values in masked_payments DON'T appear in masked_orders
    (should be 0). Both are zero whenever the same deterministic transform
    is applied to the same FK column across the related pipelines.
    """
    import pandas as pd

    cust = pd.read_csv(out_dir / "customers_masked.csv")
    ord_ = pd.read_csv(out_dir / "orders_masked.csv")
    pay = pd.read_csv(out_dir / "payments_masked.csv")

    cust_ids = set(cust["customer_id"].astype(str))
    ord_ids = set(ord_["order_id"].astype(str))

    orders_customer_orphans = sorted(
        set(ord_["customer_id"].astype(str)) - cust_ids
    )
    payments_order_orphans = sorted(
        set(pay["order_id"].astype(str)) - ord_ids
    )

    return {
        "customers_rows": int(len(cust)),
        "orders_rows": int(len(ord_)),
        "payments_rows": int(len(pay)),
        "orders_customer_id_orphans": len(orders_customer_orphans),
        "payments_order_id_orphans": len(payments_order_orphans),
        "orders_customer_id_orphan_examples": orders_customer_orphans[:5],
        "payments_order_id_orphan_examples": payments_order_orphans[:5],
    }


def _run_ref_demo(state: OutputState, out_dir: Path, n_rows: int) -> int:
    """3-table FK demo. Returns the exit code (always 0 on success)."""
    customers_yaml = out_dir / "customers_pipeline.yaml"
    orders_yaml = out_dir / "orders_pipeline.yaml"
    payments_yaml = out_dir / "payments_pipeline.yaml"
    customers_masked = out_dir / "customers_masked.csv"
    orders_masked = out_dir / "orders_masked.csv"
    payments_masked = out_dir / "payments_masked.csv"

    if state.mode is OutputMode.default:
        state.console.print(accent("[1/5]"), f"Generating customers / orders / payments ({n_rows:,} rows each)...")
    _generate_ref_datasets(out_dir, n_rows)

    customers_yaml.write_text(_build_customers_yaml(out_dir))
    orders_yaml.write_text(_build_orders_yaml(out_dir))
    payments_yaml.write_text(_build_payments_yaml(out_dir))

    from decoy_engine import Masker

    if state.mode is OutputMode.default:
        state.console.print(accent("[2/5]"), "Masking customers (hash on customer_id)...")
    Masker(str(customers_yaml)).mask()

    if state.mode is OutputMode.default:
        state.console.print(accent("[3/5]"), "Masking orders (same hash, same output)...")
    Masker(str(orders_yaml)).mask()

    if state.mode is OutputMode.default:
        state.console.print(accent("[4/5]"), "Masking payments (same hash, same output)...")
    Masker(str(payments_yaml)).mask()

    if state.mode is OutputMode.default:
        state.console.print(accent("[5/5]"), "Verifying referential integrity post-mask...")
    integrity = _verify_ref_integrity(out_dir)

    ok = (
        integrity["orders_customer_id_orphans"] == 0
        and integrity["payments_order_id_orphans"] == 0
    )

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "demo",
                "variant": "ref",
                "status": "ok" if ok else "warn",
                "dir": str(out_dir),
                "pipelines": {
                    "customers": str(customers_yaml),
                    "orders": str(orders_yaml),
                    "payments": str(payments_yaml),
                },
                "masked": {
                    "customers": str(customers_masked),
                    "orders": str(orders_masked),
                    "payments": str(payments_masked),
                },
                "integrity": integrity,
                "fk_strategy": "hash-sha256-truncated",
            },
        )
        return 0

    if state.mode is OutputMode.quiet:
        return 0

    state.console.print()
    integrity_summary = (
        f"{integrity['orders_rows'] - integrity['orders_customer_id_orphans']:,}"
        f"/{integrity['orders_rows']:,} customer_id joins;"
        f" {integrity['payments_rows'] - integrity['payments_order_id_orphans']:,}"
        f"/{integrity['payments_rows']:,} order_id joins"
    )
    render_card(
        state,
        command="decoy demo --ref",
        facts=[
            ("Customers", f"{integrity['customers_rows']:,} rows -> {customers_masked.name}"),
            ("Orders", f"{integrity['orders_rows']:,} rows -> {orders_masked.name}"),
            ("Payments", f"{integrity['payments_rows']:,} rows -> {payments_masked.name}"),
            ("FK strategy", f"hash (sha256, truncated to {_FK_HASH_TRUNCATE} hex)"),
            ("Integrity", integrity_summary),
        ],
        next_hint=f"head {customers_masked}",
        status="ok" if ok else "warn",
    )
    if ok:
        state.console.print(
            success("OK"),
            "all FK joins survive masking via deterministic hashing --",
            "same input -> same hash -> joins work with no shared state.",
        )
    else:
        state.console.print(
            error("warn:"),
            f"{integrity['orders_customer_id_orphans']} orphan customer_id(s) in orders,",
            f"{integrity['payments_order_id_orphans']} orphan order_id(s) in payments.",
        )
        state.console.print(
            " ", hint("hint:"),
            "check that all three pipelines use identical hash config",
            "(algorithm + truncate) for the shared FK columns.",
        )
    return 0


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _demo(
    out_dir: Path = typer.Option(
        Path("decoy_demo"),
        "--dir",
        help="Where to drop the demo artifacts.",
    ),
    ref: bool = typer.Option(
        False,
        "--ref",
        help="Run the 3-table referential-integrity variant (customers + orders + payments).",
    ),
    rows: int = typer.Option(
        1000,
        "--rows",
        help="Rows per dataset when --ref is set. Default 1000.",
        min=10,
        max=100_000,
    ),
    json_: bool = typer.Option(
        False, "--json", help="Emit a JSON summary instead of cards."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Walk through scan -> forecast -> mask on a bundled sample dataset.

    Use this on a fresh install to see what Decoy can do end to end without
    needing your own data or pipeline. All output lands in `./decoy_demo/`
    (override with `--dir`).

    Pass `--ref` to run the referential-integrity variant instead: three
    related CSVs (customers, orders, payments) with foreign-key columns,
    masked through three pipelines that hash the FK columns identically.
    Determinism is what preserves the joins -- no shared state needed.
    """
    state = setup_output(json_, quiet, verbose)

    if ref and out_dir == Path("decoy_demo"):
        out_dir = Path("decoy_demo_ref")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if ref:
            exit_code = _run_ref_demo(state, out_dir, rows)
        else:
            exit_code = _run_single_demo(state, out_dir)
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "demo", "status": "error", "error": str(exc)},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=3)

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


_demo.__doc__ = _demo.__doc__
DEMO_EPILOG = _DEMO_EPILOG
