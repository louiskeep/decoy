"""`decoy storm` -- dataset analysis (PII detectors, sentinels, re-id risk)."""

from __future__ import annotations

import json as _json
from datetime import datetime
from enum import Enum
from pathlib import Path

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import multistage
from decoy.ui.theme import code, error, hint


storm_app = typer.Typer(
    name="storm",
    help="Dataset analysis -- the STORM event. Scan first, then forecast.",
    no_args_is_help=True,
)


class SampleStrategy(str, Enum):
    full = "full"
    head = "head"
    random = "random"


_SCAN_EPILOG = """\
Examples:

  decoy storm scan data.csv
    Scan a CSV with default sampling, save scan_<timestamp>.json.

  decoy storm scan data.csv --rows 50000 --strategy random
    Sample 50K random rows.

  decoy storm scan data.csv --json > scan.json
    Pipe the full StormProfile JSON for forecast --stdin.

See also: decoy forecast, decoy run.
"""


def _load_csv_with_sampling(path: Path, rows: int | None, strategy: SampleStrategy):
    import pandas as pd

    if strategy is SampleStrategy.full or rows is None:
        return pd.read_csv(path)
    if strategy is SampleStrategy.head:
        return pd.read_csv(path, nrows=rows)
    if strategy is SampleStrategy.random:
        df = pd.read_csv(path)
        if len(df) <= rows:
            return df
        return df.sample(n=rows, random_state=42).reset_index(drop=True)
    return pd.read_csv(path)


def _scan(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to a CSV file to scan.",
    ),
    rows: int | None = typer.Option(
        None,
        "--rows",
        help="Sample row cap. Default: scan everything.",
    ),
    strategy: SampleStrategy = typer.Option(
        SampleStrategy.head,
        "--strategy",
        help="Sampling strategy when --rows is set.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Where to save the scan JSON. Use - for stdout. Default: scan_<timestamp>.json next to the source.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit the full StormProfile JSON to stdout. No card.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Scan a dataset and produce a STORM profile.

    Use this when you've been handed a dataset and want to know what's in it
    -- which fields are PII, which look like quasi-identifiers, what
    re-identification risk the dataset carries -- before writing a masking
    pipeline. Pass the saved scan JSON to `decoy forecast`.
    """
    state = setup_output(json_, quiet, verbose)
    source_str = str(source)

    try:
        from decoy_engine import run_storm

        with multistage(state, ["Load source", "Profile columns", "Save profile"]) as ms:
            df = _load_csv_with_sampling(source, rows, strategy)
            ms.complete()
            profile = run_storm(
                df,
                source_label=source.name,
                sample_strategy=strategy.value,
                sample_row_cap=rows,
            )
            ms.complete()

            if out is not None and str(out) == "-":
                out_path: Path | None = None
            elif out is not None:
                out_path = out
            else:
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                out_path = source.parent / f"scan_{ts}.json"

            if out_path is not None:
                out_path.write_text(_json.dumps(profile.to_dict(), indent=2))
            ms.complete()
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "storm scan",
                    "status": "error",
                    "source": source_str,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=3)

    if state.mode is OutputMode.json:
        # Full StormProfile to stdout when piping.
        if out is not None and str(out) == "-":
            import sys

            sys.stdout.write(_json.dumps(profile.to_dict()) + "\n")
        else:
            emit_json(
                state,
                {
                    "command": "storm scan",
                    "status": "ok",
                    "source": source_str,
                    "saved": str(out_path) if out_path else None,
                    "profile": profile.to_dict(),
                },
            )
        return

    if state.mode is OutputMode.quiet:
        return

    pii_columns = sum(1 for f in profile.fields if f.pii_score >= 0.6)
    facts: list[tuple[str, str]] = [
        ("Source", source.name),
        ("Rows scanned", f"{profile.row_count:,} ({profile.sample_strategy})"),
        ("Columns", str(len(profile.fields))),
        ("PII columns", str(pii_columns)),
        ("Reid risk", f"{profile.reid_risk_score}"),
    ]
    if profile.quasi_identifier_groups:
        qi = ", ".join("(" + " + ".join(g) + ")" for g in profile.quasi_identifier_groups)
        facts.append(("Quasi-identifiers", qi))
    next_hint = None
    if out_path is not None:
        facts.append(("Saved", str(out_path)))
        next_hint = f"decoy forecast {out_path}"

    render_card(
        state,
        command="decoy storm scan",
        facts=facts,
        next_hint=next_hint,
        status="ok",
    )


storm_app.command(name="scan", epilog=_SCAN_EPILOG)(_scan)
