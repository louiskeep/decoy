"""`decoy profile [--show-fields]` -- profile a source dataset.

Runs the engine's STORM (Statistical Top-down Risk Mapping) detector on a CSV
or Parquet file and reports:

  - Dataset shape: row count, field count, sample strategy.
  - Per-field stats (with --show-fields): dtype, null_rate, distinct_count.
  - PII candidates (when STORM fires): framed explicitly as SUGGESTIONS the
    user reviews -- NEVER as authoritative auto-classification.

HONESTY rules (required by Decoy's design):

  1. PII candidate language: when STORM's pii_score indicates a field may
     contain PII, output says "PII candidate (suggestion -- review required)".
     It NEVER says "classified as", "detected as", or "is PII" (authoritative).
     The user picks the PII type per field; auto-classification is abandoned
     by design (ADR noted in decoy-platform docs).

  2. No raw values: field stats include ONLY dtype, null_rate, distinct_count,
     and pii_score. The profile output does NOT include top_values, mode_value,
     min_value, max_value, or any other aggregate that could expose raw cell
     data. This is the same privacy discipline as SP-18b's diff command.

     Exception: dtype labels (e.g. "string", "integer") are safe metadata;
     they describe the data type, not a cell value.

Reuses the engine's `run_storm` function. Does NOT reimplement detection.
"""

from __future__ import annotations

from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, warn

# PII score threshold to surface a field as a candidate.
# Mirrors the engine's STORM internal threshold (>=0.6 is "PII candidate").
_PII_CANDIDATE_THRESHOLD = 0.6

_PROFILE_EPILOG = """\
Examples:

  decoy profile data.csv
    Profile a CSV: row count, field count, PII candidates (as suggestions).

  decoy profile data.csv --show-fields
    Per-field detail: dtype, null_rate, distinct_count, PII candidate flag.

  decoy profile data.csv --show-fields --json
    Same as --show-fields but as structured JSON for scripting.

  decoy profile data.parquet
    Profile a Parquet file (format inferred from extension).

HONESTY: PII candidates are SUGGESTIONS based on STORM pattern matching.
They are NOT authoritative classifications. The user reviews each flagged field
and decides what masking to apply. Decoy never auto-classifies PII.

No raw cell values appear in the output. Field stats include dtype, null_rate,
distinct_count only.

See also: decoy storm analyze, decoy explain storm, decoy validate.
"""


def profile(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the source CSV or Parquet file to profile.",
    ),
    show_fields: bool = typer.Option(
        False,
        "--show-fields",
        help="Show per-field detail: dtype, null_rate, distinct_count, PII candidate flag.",
    ),
    rows: int = typer.Option(
        10_000,
        "--rows",
        help="Maximum rows to sample. Use 0 for full scan.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit structured JSON instead of the styled table output.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Exit code carries success or failure."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Profile a source dataset: shape, field stats, PII candidates (as suggestions).

    Runs STORM detection on the source file. PII candidates are surfaced as
    SUGGESTIONS for review -- never as authoritative auto-classifications.
    No raw cell values appear in any output mode.
    """
    state = setup_output(json_, quiet, verbose)

    # Load the source file into a pandas DataFrame.
    try:
        import pandas as pd

        suffix = source.suffix.lower()
        if suffix in (".parquet", ".pq"):
            df = pd.read_parquet(str(source))
        else:
            df = pd.read_csv(str(source), dtype=str)
    except Exception as exc:
        msg = f"could not read {source}: {exc}"
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "profile", "status": "error", "source": str(source), "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    # Run STORM to profile the dataset.
    try:
        from decoy_engine import run_storm

        sample_cap = rows if rows > 0 else None
        storm_profile = run_storm(
            df,
            source_label=source.name,
            sample_strategy="full",
            sample_row_cap=sample_cap,
        )
    except Exception as exc:
        msg = f"profile failed: {exc}"
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "profile", "status": "error", "source": str(source), "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=EXIT_RUNTIME)

    # Build privacy-safe field records (no raw cell values).
    field_records = [_safe_field_record(f) for f in storm_profile.fields]

    # Count PII candidates.
    pii_candidate_count = sum(
        1 for f in storm_profile.fields if f.pii_score >= _PII_CANDIDATE_THRESHOLD
    )

    if state.mode is OutputMode.json:
        payload: dict = {
            "command": "profile",
            "status": "ok",
            "source": str(source),
            "row_count": storm_profile.row_count,
            "field_count": len(storm_profile.fields),
            "sample_strategy": storm_profile.sample_strategy,
            "pii_candidate_count": pii_candidate_count,
            "pii_note": (
                "PII candidates are SUGGESTIONS based on STORM pattern matching. "
                "They are not authoritative classifications. Review each flagged field "
                "and decide what masking to apply. Decoy never auto-classifies PII."
            ),
        }
        if show_fields:
            payload["fields"] = field_records
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable output.
    state.console.print(accent(f"Profile: {source.name}"))
    state.console.print()

    # Summary table.
    summary = make_table("Stat", "Value")
    summary.add_row("Rows", str(storm_profile.row_count))
    summary.add_row("Fields", str(len(storm_profile.fields)))
    summary.add_row("Sample strategy", storm_profile.sample_strategy)
    if pii_candidate_count > 0:
        summary.add_row(
            "PII candidates",
            f"{pii_candidate_count} field(s) -- suggestions only, review required",
        )
    else:
        summary.add_row("PII candidates", "none detected")
    state.console.print(summary)
    state.console.print()

    if show_fields:
        _render_fields(state, field_records, pii_candidate_count)
    else:
        state.console.print(
            hint("Tip:"),
            "add",
            code("--show-fields"),
            "for per-field detail.",
        )


def _safe_field_record(field_stats) -> dict:
    """Return a privacy-safe field record from a FieldStats object.

    Includes ONLY: name, inferred_type, null_rate, distinct_count, pii_score,
    pii_candidate (bool), detector_ids (names only, no match details).

    NEVER includes: top_values, mode_value, min_value, max_value, sample_invalid,
    mean_value, or any other aggregate that could expose raw cell data.
    """
    is_candidate = field_stats.pii_score >= _PII_CANDIDATE_THRESHOLD
    # Detector IDs only (no match rates, no sample_misses which could be raw data).
    detector_ids = [m.detector_id for m in (field_stats.detector_matches or [])]
    return {
        "name": field_stats.name,
        "dtype": field_stats.inferred_type,
        "null_rate": round(field_stats.null_rate, 4),
        "distinct_count": field_stats.distinct_count,
        "pii_score": round(field_stats.pii_score, 3),
        "pii_candidate": is_candidate,
        # Detector IDs are safe metadata (pattern names, not cell values).
        "detector_hits": detector_ids,
    }


def _render_fields(state, field_records: list[dict], pii_candidate_count: int) -> None:
    """Render the per-field detail table."""
    state.console.print(accent(f"Fields ({len(field_records)}):"))

    tbl = make_table("Field", "Type", "Null rate", "Distinct", "PII candidate")
    for f in field_records:
        pii_cell = ""
        if f["pii_candidate"]:
            detectors = ", ".join(f["detector_hits"]) if f["detector_hits"] else ""
            pii_cell = "suggestion -- review"
            if detectors:
                pii_cell += f" [{detectors}]"
        tbl.add_row(
            f["name"],
            f["dtype"],
            f"{f['null_rate']:.1%}",
            str(f["distinct_count"]),
            pii_cell,
        )
    state.console.print(tbl)
    state.console.print()

    if pii_candidate_count > 0:
        state.console.print(
            warn("PII candidates:"),
            f"{pii_candidate_count} field(s) flagged by STORM pattern matching.",
        )
        state.console.print(
            " ",
            hint("These are SUGGESTIONS for review -- NOT authoritative classifications."),
        )
        state.console.print(
            " ",
            "Review each flagged field and choose the masking strategy that fits.",
            "Use",
            code("decoy templates show"),
            "to browse available templates.",
        )
        state.console.print()


PROFILE_EPILOG = _PROFILE_EPILOG
