"""`decoy demo` -- 30-second end-to-end walkthrough on bundled sample data.

Default flow: a small single-table CSV, scanned (STORM) -> masked via the V2
PipelineConfig spine. All artifacts land in `./decoy_demo/`. The legacy
FORECAST recommender step was removed under storm-reframe-C / S22; do not
re-introduce.

With `--ref`: deferred to a follow-up sprint (V2 multi-table FK-preservation
demo needs a single PipelineConfig with a `relationships:` block; the V1
three-pipeline implementation was retired with the V1 graph runner). The
`--ref` builders still in this module are V1-shape stubs flagged at each
call site; see the `# V1 SHAPE` comments before re-wiring.
"""

from __future__ import annotations

import csv
import json as _json
import random
from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, OutputState, emit_json, setup_output
from decoy.ui.theme import accent, code, error, hint, success


_DEMO_EPILOG = """\
Examples:

  decoy demo
    Run the simple scan -> mask walkthrough in ./decoy_demo/.

  decoy demo --ref
    Generate 3 related CSVs (customers, orders, payments) with FK
    relationships and mask all three with deterministic hashing.
    FK joins survive masking without any shared state. ~1000 rows each.

  decoy demo --ref --rows 5000 --dir my_demo
    Same, but 5K rows per dataset and a custom output directory.

  decoy demo --json
    Same flow, but emit a JSON summary instead of cards.

See also: decoy storm analyze, decoy run.
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
    """V2 PipelineConfig shape per decoy-engine `decoy_engine.config._pipeline`.

    Provider names come from the engine's default registry. customer_id
    rides the deterministic envelope (deterministic + namespace) so a
    future multi-table demo can re-join on it; deterministic faker
    output is the V2-equivalent of the V1 'hash for FK join' trick the
    original demo used.

    CLI QA fix (2026-06-02, F6): build a dict and serialize via
    yaml.safe_dump rather than f-string templating. Pre-fix a single
    quote in a path (e.g. --dir "O'Hare_demo") produced un-escaped YAML
    that yaml.safe_load then rejected with a ScannerError, surfacing as
    a confusing crash. safe_dump quotes path strings correctly.
    """
    import yaml as _yaml

    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(input_path),
            },
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "customer_id", "strategy": "redact"},
                    {"name": "first_name", "strategy": "faker",
                     "provider": "person_first_name"},
                    {"name": "last_name", "strategy": "faker",
                     "provider": "person_last_name"},
                    {"name": "email", "strategy": "faker",
                     "provider": "person_email"},
                    {"name": "ssn", "strategy": "redact"},
                    {"name": "dob", "strategy": "redact"},
                    {"name": "zip", "strategy": "redact"},
                    {"name": "gender", "strategy": "passthrough"},
                ],
            },
        ],
        "targets": {
            "customers": {
                "type": "file",
                "format": "csv",
                "path": str(output_path),
            },
        },
    }
    return _yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False)


def _run_single_demo(state: OutputState, out_dir: Path) -> int:
    """V2 one-CSV walkthrough.

    CLI.3 commit 2 (2026-06-02): rewritten against the V2 spine.
    Pre-rewrite the demo called `recommend` (FORECAST, retired under
    storm-reframe-C) and `Masker(...).mask()` (V1 surface deleted under
    S22-CL-V1GRAPHRUNNER). The new walkthrough: write a sample CSV ->
    STORM scan -> V2 PipelineConfig validate -> compile_plan ->
    select_execution_adapter().run(...) -> write masked output.
    The FORECAST step is dropped (no V2 successor); the storm scan
    still surfaces PII counts so the operator gets the same gut-check
    on what the engine saw in their data.
    """
    sample_csv = out_dir / "customers.csv"
    masked_csv = out_dir / "customers_masked.csv"
    pipeline_yaml = out_dir / "pipeline.yaml"
    scan_json = out_dir / "scan.json"

    if state.mode is OutputMode.default:
        state.console.print(accent("[1/3]"), "Writing sample dataset...")
    _write_sample_csv(sample_csv)

    if state.mode is OutputMode.default:
        state.console.print(accent("[2/3]"), "Scanning with STORM...")
    import pandas as pd
    from decoy_engine import run_storm

    df = pd.read_csv(sample_csv)
    profile = run_storm(df, source_label=sample_csv.name, sample_strategy="full")
    scan_json.write_text(_json.dumps(profile.to_dict(), indent=2))

    if state.mode is OutputMode.default:
        state.console.print(accent("[3/3]"), "Running V2 masking pipeline...")
    pipeline_yaml.write_text(_build_pipeline_yaml(sample_csv, masked_csv))
    _run_v2_mask(pipeline_yaml)

    pii_columns = sum(1 for f in profile.fields if f.pii_score >= 0.6)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "demo",
                "variant": "single",
                "status": "ok",
                "dir": str(out_dir),
                "scan": str(scan_json),
                "masked": str(masked_csv),
                "pii_columns": pii_columns,
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
            ("Masked output", str(masked_csv)),
        ],
        next_hint=f"head {masked_csv}",
        status="ok",
    )
    state.console.print(success("OK"), "demo complete.")
    return 0


def _run_v2_mask(pipeline_yaml: Path) -> None:
    """Execute a V2-shape mask pipeline end-to-end.

    Mirrors `decoy run`'s V2 dispatch (cli/run.py) inline: validate ->
    profile_source -> compile_plan -> build_namespace_registry ->
    check_orphan_fk_policy_completeness + build_relationship_graph (if
    relationships) -> select_execution_adapter().run(...) -> write the
    masked output to the declared target path. Per best-practices §3.3
    the demo composes the engine calls itself; extracting a shared
    helper would couple two callers prematurely.
    """
    from decoy_engine import (
        PipelineConfig,
        compile_plan,
        get_default_registry,
        select_execution_adapter,
        __version__ as engine_version,
    )
    from decoy_engine.profile import profile_source
    from decoy_engine.relationships import (
        RelationshipGraph,
        build_namespace_registry,
        build_relationship_graph,
        check_orphan_fk_policy_completeness,
    )

    import yaml as _yaml

    text = pipeline_yaml.read_text(encoding="utf-8")
    raw = _yaml.safe_load(text)
    config_dict = PipelineConfig.model_validate(raw).model_dump()

    job_seed = (config_dict.get("global_settings") or {}).get("seed")
    profile = profile_source(
        config_dict,
        seed=job_seed if isinstance(job_seed, int) else None,
    )
    plan = compile_plan(config_dict, profile, decoy_engine_version=engine_version)
    ns_registry = build_namespace_registry(config_dict, profile)
    if profile.relationships:
        lookup = check_orphan_fk_policy_completeness(config_dict, profile.relationships)
        graph = build_relationship_graph(
            profile.relationships,
            namespace_registry=ns_registry,
            orphan_policy_lookup=lookup,
        )
    else:
        graph = RelationshipGraph(edges=(), ordering=())

    sources = _load_sources_from_config(config_dict, pipeline_yaml.parent)
    adapter = select_execution_adapter()
    result = adapter.run(
        plan,
        sources,
        registry=get_default_registry(),
        relationship_graph=graph,
        namespace_registry=ns_registry,
    )
    _write_mask_outputs(config_dict, result, pipeline_yaml.parent)


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p).resolve()


def _load_sources_from_config(config_dict: dict, base_dir: Path) -> dict:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    out: dict[str, pa.Table] = {}
    sources = config_dict.get("sources") or {}
    if not isinstance(sources, dict):
        return out
    for table_name, src in sources.items():
        if not isinstance(src, dict):
            continue
        raw_path = src.get("path")
        if not isinstance(raw_path, str):
            continue
        path = _resolve_path(raw_path, base_dir)
        if path.suffix.lower() == ".parquet":
            out[table_name] = pq.read_table(str(path))
        else:
            df = pd.read_csv(path, dtype=str)
            out[table_name] = pa.Table.from_pandas(df, preserve_index=False)
    return out


def _write_mask_outputs(config_dict: dict, result, base_dir: Path) -> None:
    """Write each declared target. The engine `ExecutionResult` carries
    masked tables on `outputs` (dict[table_name -> pa.Table]); not
    `tables`."""
    targets = config_dict.get("targets") or {}
    if not isinstance(targets, dict):
        return
    outputs = getattr(result, "outputs", None)
    if not isinstance(outputs, dict):
        return
    for table_name, entry in targets.items():
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        table = outputs.get(table_name)
        if table is None:
            continue
        path = _resolve_path(raw_path, base_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".parquet":
            import pyarrow.parquet as pq

            pq.write_table(table, str(path))
        else:
            table.to_pandas().to_csv(path, index=False)


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


# ──────────────────────────────────────────────────────────────────────────
# V1-SHAPE STUBS for the deferred --ref multi-table demo path.
#
# CLI QA fix (2026-06-02, F5): the three `_build_*_yaml` helpers below
# emit V1 pipeline YAML (`version: '1.0'`, `input:`, `output:`,
# `masking_rules:`) that the V2 PipelineConfig validator hard-rejects.
# They are unreachable today (the `--ref` path is deferred to a follow-up
# sprint), but the functions remain importable. A contributor who wires
# `--ref` to call them without noticing the V1 shape will get a confusing
# PipelineValidationError at runtime.
#
# DO NOT RE-WIRE these helpers to a live code path without first
# rewriting their output to V2 PipelineConfig shape (see
# `src/decoy/templates/minimal.yaml` for the canonical reference) and
# adding a single shared `relationships:` block so the three tables run
# in one pipeline. The same caveat applies to `_verify_ref_integrity`
# below, which reads output files the V1 demo flow would have written.
# ──────────────────────────────────────────────────────────────────────────


def _build_customers_yaml(out_dir: Path) -> str:
    """V1 SHAPE -- replace with V2 PipelineConfig before wiring to --ref."""
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
    """V1 SHAPE -- replace with V2 PipelineConfig before wiring to --ref."""
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
    """V1 SHAPE -- replace with V2 PipelineConfig before wiring to --ref."""
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
    """V1 SHAPE -- reads output files the deferred --ref flow would have
    written. Replace with a V2-pipeline-aware check before wiring to
    --ref."""
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
    """3-table FK demo. CLI.3 commit 2 (2026-06-02): deferred per
    Q-CLI3-1 (Dennis resolution: drop if effort exceeds 0.5 eng-days).

    The pre-CLI.3 implementation built three V1-shape YAMLs and ran
    `Masker(...).mask()` on each, joining via a shared SHA-256 hash on
    the FK columns. The V2 equivalent needs a single multi-table
    PipelineConfig with a `relationships:` block (the engine's V2 FK
    coordinator owns the join contract end-to-end), the deterministic
    HKDF/HMAC envelope replacing the truncated hash, and a verifying
    golden. That is a focused follow-up sprint; clobbering it into
    CLI.3 commit 2 would exceed the spec's 0.5-day budget.

    The data-generation helpers + integrity verifier above stay in
    place so the follow-up sprint can reuse them.
    """
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "demo",
                "variant": "ref",
                "status": "error",
                "error": (
                    "decoy demo --ref is deferred to a follow-up sprint. The "
                    "V2 multi-table FK-preservation demo needs a single "
                    "PipelineConfig with a `relationships:` block; the V1 "
                    "shape (three V1 YAMLs joined by a shared truncated hash) "
                    "no longer runs against the V2 engine. Use `decoy demo` "
                    "(single-table walkthrough) until the multi-table follow-up "
                    "lands."
                ),
            },
        )
        return 1

    state.err_console.print(
        error("error:"),
        "decoy demo --ref is deferred to a follow-up sprint.",
    )
    state.err_console.print(
        " ", hint("why:"),
        "The V2 multi-table FK-preservation demo needs a single",
        "PipelineConfig with a `relationships:` block; the V1 shape",
        "(three V1 YAMLs joined by a shared truncated hash) no longer",
        "runs against the V2 engine.",
    )
    state.err_console.print(
        " ", hint("workaround:"),
        "Use `decoy demo` (single-table walkthrough) until the",
        "multi-table follow-up lands.",
    )
    return 1


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
    """Walk through scan -> mask on a bundled sample dataset.

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
    # Resolve to absolute up front. Pre-fix the relative `out_dir` (e.g.
    # `decoy_demo`) flowed into `_build_pipeline_yaml`, which wrote
    # `decoy_demo/customers.csv` into the pipeline YAML. Then
    # `_run_v2_mask` re-resolved that relative path against
    # `pipeline_yaml.parent` (which is `decoy_demo` again), producing
    # `decoy_demo/decoy_demo/customers.csv` and a FileNotFoundError.
    # Dennis launch-readiness audit (2026-06-02) BLOCKER finding.
    out_dir = out_dir.resolve()

    try:
        if ref:
            exit_code = _run_ref_demo(state, out_dir, rows)
        else:
            exit_code = _run_single_demo(state, out_dir)
    except typer.Exit:
        # CLI QA fix (2026-06-02, F7): preserve inner typer.Exit codes.
        raise
    except Exception as exc:
        # Audit H10 (2026-06-12): dispatch on exception type so scripts
        # can tell "your config is wrong" (EXIT_USAGE, per the
        # exit_codes.py contract) from "the run blew up" (EXIT_RUNTIME).
        from decoy_engine import ConfigError, PipelineValidationError
        from decoy_engine.plan import PlanCompileError

        _exit_code = (
            EXIT_USAGE
            if isinstance(exc, (PlanCompileError, PipelineValidationError, ConfigError))
            else EXIT_RUNTIME
        )
        # CLI QA fix (2026-06-02, F8): truncate the error message at
        # 500 chars before emitting through --json.
        error_text = str(exc)
        if len(error_text) > 500:
            error_text = error_text[:500] + "..."
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "demo", "status": "error", "error": error_text},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), error_text)
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=_exit_code)

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


_demo.__doc__ = _demo.__doc__
DEMO_EPILOG = _DEMO_EPILOG
