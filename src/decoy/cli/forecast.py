"""`decoy forecast` -- recommendations over a saved STORM profile."""

from __future__ import annotations

import json as _json
import sys
from datetime import datetime
from pathlib import Path

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import spinner
from decoy.ui.table import make_table
from decoy.ui.theme import code, error, hint


forecast_app = typer.Typer(
    name="forecast",
    help="Recommend Disguises and per-field Masks from a STORM profile.",
    no_args_is_help=True,
)


_RECOMMEND_EPILOG = """\
Examples:

  decoy forecast recommend scan.json
    Print the top Disguise + risk flags. Saves forecast_<timestamp>.json.

  decoy storm scan data.csv --json | decoy forecast recommend -
    Pipe a fresh scan straight in.

  decoy forecast recommend scan.json --json
    Emit the full ForecastReport JSON.

See also: decoy storm scan, decoy run.
"""


def _storm_profile_from_dict(data: dict):
    from decoy_engine.storm.types import (
        DetectorMatch,
        FieldStats,
        SentinelFlag,
        StormProfile,
        TopValue,
    )

    fields = []
    for fs_dict in data.get("fields", []):
        fs_dict = dict(fs_dict)
        fs_dict["top_values"] = [TopValue(**tv) for tv in fs_dict.get("top_values", [])]
        fs_dict["detector_matches"] = [
            DetectorMatch(**dm) for dm in fs_dict.get("detector_matches", [])
        ]
        fs_dict["sentinels"] = [SentinelFlag(**s) for s in fs_dict.get("sentinels", [])]
        fields.append(FieldStats(**fs_dict))
    payload = dict(data)
    payload["fields"] = fields
    return StormProfile(**payload)


def _load_profile(scan_path: str) -> "StormProfile":  # noqa: F821 -- forward
    if scan_path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(scan_path).read_text(encoding="utf-8")
    data = _json.loads(raw)
    # Accept both the bare to_dict() shape and the {"profile": {...}} envelope
    # that `decoy storm scan --json` (non-stdin) emits.
    if "profile" in data and "row_count" not in data:
        data = data["profile"]
    return _storm_profile_from_dict(data)


def _recommend(
    scan: str = typer.Argument(
        ...,
        help="Path to the STORM scan JSON, or `-` for stdin.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Where to save the ForecastReport JSON. Default: forecast_<timestamp>.json next to the scan.",
    ),
    json_: bool = typer.Option(
        False, "--json", help="Emit the full ForecastReport JSON to stdout."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Recommend Disguises and per-field Masks for a saved STORM profile.

    FORECAST never reads raw data -- only the statistical summary STORM
    produced. Run `decoy storm scan` first, then feed the saved JSON here.
    """
    state = setup_output(json_, quiet, verbose)

    try:
        from decoy_engine import recommend

        with spinner(state, "Recommending Disguises..."):
            profile = _load_profile(scan)
            report = recommend(profile)
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "forecast recommend",
                    "status": "error",
                    "scan": scan,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=3)

    out_path: Path | None = None
    if scan != "-":
        if out is not None and str(out) == "-":
            out_path = None
        elif out is not None:
            out_path = out
        else:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            out_path = Path(scan).parent / f"forecast_{ts}.json"
    elif out is not None and str(out) != "-":
        out_path = out

    pipeline_path: Path | None = None
    if out_path is not None:
        out_path.write_text(_json.dumps(report.to_dict(), indent=2))
        if report.proposed_pipeline_yaml:
            pipeline_path = out_path.with_suffix(".pipeline.yaml")
            pipeline_path.write_text(report.proposed_pipeline_yaml)

    if state.mode is OutputMode.json:
        if scan == "-" or (out is not None and str(out) == "-"):
            sys.stdout.write(_json.dumps(report.to_dict()) + "\n")
        else:
            emit_json(
                state,
                {
                    "command": "forecast recommend",
                    "status": "ok",
                    "scan": scan,
                    "saved": str(out_path) if out_path else None,
                    "report": report.to_dict(),
                },
            )
        return

    if state.mode is OutputMode.quiet:
        return

    top = report.disguise_recommendations[0] if report.disguise_recommendations else None
    facts: list[tuple[str, str]] = []
    if top is not None:
        facts.append(("Top recommendation", f"{top.name} (score {top.match_score:.2f})"))
        facts.append(("Fields covered", f"{len(top.matched_fields)} of {len(profile.fields)}"))
    else:
        facts.append(("Top recommendation", "(none above min_score)"))
    facts.append(("Risk flags", str(len(report.risk_flags))))
    if out_path is not None:
        facts.append(("Saved", str(out_path)))
    if pipeline_path is not None:
        facts.append(("Pipeline draft", str(pipeline_path)))

    render_card(
        state,
        command="decoy forecast recommend",
        facts=facts,
        next_hint=(f"decoy run {pipeline_path}" if pipeline_path else None),
        status="ok",
    )

    # Detail follow-up: list each disguise with score, plus risk flags table.
    if report.disguise_recommendations:
        t = make_table("Disguise", "Score", "Fields", title="All Disguises")
        for d in report.disguise_recommendations:
            t.add_row(d.name, f"{d.match_score:.2f}", str(len(d.matched_fields)))
        state.console.print(t)

    if report.risk_flags:
        t = make_table("Field", "Kind", "Note", title="Risk flags")
        for r in report.risk_flags:
            t.add_row(r.field_name, r.kind, r.note)
        state.console.print(t)


forecast_app.command(name="recommend", epilog=_RECOMMEND_EPILOG)(_recommend)
