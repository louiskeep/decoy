"""`decoy demo` -- 30-second end-to-end walkthrough on a bundled CSV.

Generates a small sample CSV, scans it (STORM), recommends a Disguise
(FORECAST), then runs the recommended masking pipeline. All artifacts
land in a `./decoy_demo/` directory in the current working directory.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import accent, code, error, hint, success


_DEMO_EPILOG = """\
Examples:

  decoy demo
    Run the full scan -> forecast -> mask walkthrough in ./decoy_demo/.

  decoy demo --json
    Same flow, but emit a JSON summary instead of cards.

See also: decoy storm scan, decoy forecast recommend, decoy run.
"""


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


def _build_pipeline_yaml(input_path: Path, output_path: Path, mappings_dir: Path) -> str:
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
mappings:
  store_directory: '{mappings_dir.as_posix()}'
masking_rules:
  - column: customer_id
    type: passthrough
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


def _demo(
    out_dir: Path = typer.Option(
        Path("decoy_demo"),
        "--dir",
        help="Where to drop the demo artifacts.",
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
    needing your own data or pipeline. All output lands in `./decoy_demo/`.
    """
    state = setup_output(json_, quiet, verbose)

    out_dir.mkdir(parents=True, exist_ok=True)
    sample_csv = out_dir / "patients.csv"
    masked_csv = out_dir / "patients_masked.csv"
    mappings_dir = out_dir / "mappings"
    pipeline_yaml = out_dir / "pipeline.yaml"
    scan_json = out_dir / "scan.json"
    forecast_json = out_dir / "forecast.json"

    try:
        if state.mode is OutputMode.default:
            state.console.print(accent("[1/4]"), "Writing sample dataset...")
        _write_sample_csv(sample_csv)

        # 2. STORM scan.
        if state.mode is OutputMode.default:
            state.console.print(accent("[2/4]"), "Scanning with STORM...")
        import pandas as pd
        from decoy_engine import run_storm

        df = pd.read_csv(sample_csv)
        profile = run_storm(df, source_label=sample_csv.name, sample_strategy="full")
        scan_json.write_text(_json.dumps(profile.to_dict(), indent=2))

        # 3. FORECAST recommend.
        if state.mode is OutputMode.default:
            state.console.print(accent("[3/4]"), "Asking FORECAST for a Disguise...")
        from decoy_engine import recommend

        report = recommend(profile)
        forecast_json.write_text(_json.dumps(report.to_dict(), indent=2))

        # 4. Run the masking pipeline.
        if state.mode is OutputMode.default:
            state.console.print(accent("[4/4]"), "Running masking pipeline...")
        pipeline_yaml.write_text(_build_pipeline_yaml(sample_csv, masked_csv, mappings_dir))
        from decoy_engine import Masker

        Masker(str(pipeline_yaml)).mask()
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

    pii_columns = sum(1 for f in profile.fields if f.pii_score >= 0.6)
    top = report.disguise_recommendations[0] if report.disguise_recommendations else None

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "demo",
                "status": "ok",
                "dir": str(out_dir),
                "scan": str(scan_json),
                "forecast": str(forecast_json),
                "masked": str(masked_csv),
                "pii_columns": pii_columns,
                "top_disguise": top.name if top else None,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

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


_demo.__doc__ = _demo.__doc__

DEMO_EPILOG = _DEMO_EPILOG
