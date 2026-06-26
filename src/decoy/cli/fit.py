"""`decoy fit` -- fit a distribution snapshot from a source CSV.

Capability-gaps WS3 (2026-06-12). Wraps the engine's
`compute_distribution_snapshot` (distribution-snapshot/v1): the JSON it
writes is the fitted-model artifact that `type: statistical` generate
columns consume. The loop is:

    decoy fit source.csv --output snapshot.json
    # reference snapshot.json from generate_columns, then:
    decoy run generate.yaml

The snapshot contains aggregate shape only (bins, quantiles, top-k
category counts) -- EXCEPT categorical `top_values`, which carry real
source values; that is why statistical categorical columns require the
`allow_real_categories: true` opt-in at run time.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, success


_FIT_EPILOG = """\
Examples:

  decoy fit customers.csv
    Write customers.snapshot.json next to the source.

  decoy fit customers.csv --output snapshot.json --parse-dates signup_date
    Treat signup_date as a datetime column.

  decoy fit customers.csv --joint state,tier
    Capture the (state, tier) contingency table so a statistical column
    can use `condition_on`.

  decoy fit customers.csv --epsilon 1.0
    Differentially private release: Laplace noise on every snapshot
    count (OpenDP/SmartNoise histogram mechanism). The budget is per
    column histogram; incompatible with --joint in v1.

See also: decoy run, decoy validate, decoy explain differential-privacy.
"""


def fit(
    source: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Source CSV to fit the distribution snapshot from.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Where to write the snapshot JSON. Default: <source>.snapshot.json.",
    ),
    parse_dates: list[str] = typer.Option(
        [],
        "--parse-dates",
        help="Column(s) to parse as datetimes (repeatable). CSV carries no dtype, so date columns must be named explicitly.",
    ),
    joint: list[str] = typer.Option(
        [],
        "--joint",
        help="Column pair 'a,b' whose contingency table to capture (repeatable). Needed for `condition_on`.",
    ),
    epsilon: float = typer.Option(
        None,
        "--epsilon",
        help=(
            "Differentially private release: per-column Laplace noise on "
            "all snapshot counts; exact quantiles/means are removed. The "
            "budget is PER COLUMN HISTOGRAM (k columns compose to ~k*epsilon "
            "total). Incompatible with --joint in v1."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Fit a distribution-snapshot/v1 artifact for statistical generation.

    Reads the source CSV, captures per-column distribution shape (numeric
    histograms + quantiles, categorical top-k, datetime year bins) plus
    any requested pairwise contingency tables, and writes the JSON
    artifact `type: statistical` generate columns reference via
    `snapshot_file`. Exits 0 on success, 1 on bad input.
    """
    state = setup_output(json_, quiet, verbose)

    def _emit_error(message: str) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "fit",
                    "status": "error",
                    "source": str(source),
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), message)

    joint_pairs: list[tuple[str, str]] = []
    for spec in joint:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if len(parts) != 2:
            _emit_error(f"--joint expects 'colA,colB'; got {spec!r}.")
            raise typer.Exit(code=EXIT_USAGE)
        joint_pairs.append((parts[0], parts[1]))

    if epsilon is not None and joint_pairs:
        _emit_error(
            "--epsilon with --joint is not supported in v1: releasing "
            "marginals plus joint tables under one epsilon needs composition "
            "accounting. Drop --joint or omit --epsilon."
        )
        raise typer.Exit(code=EXIT_USAGE)

    import pandas as pd

    from decoy_engine.quality.snapshot import compute_distribution_snapshot

    try:
        df = pd.read_csv(source, parse_dates=list(parse_dates) or False)
    except Exception as exc:
        _emit_error(f"could not read {source}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    missing = [c for c in parse_dates if c not in df.columns]
    if missing:
        _emit_error(f"--parse-dates column(s) not in the CSV: {', '.join(missing)}.")
        raise typer.Exit(code=EXIT_USAGE)

    snapshot = compute_distribution_snapshot(df, joint_columns=joint_pairs or None)

    if epsilon is not None:
        from decoy_engine.quality.dp import DpError, apply_dp_noise

        try:
            snapshot = apply_dp_noise(snapshot, epsilon=epsilon)
        except DpError as exc:
            _emit_error(f"{exc.code}: {exc.message}")
            raise typer.Exit(code=EXIT_USAGE)

    out_path = output if output is not None else source.with_suffix(".snapshot.json")
    out_path.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "fit",
                "status": "ok",
                "source": str(source),
                "output": str(out_path),
                "row_count": snapshot["row_count"],
                "columns": {
                    name: entry["kind"] for name, entry in snapshot["columns"].items()
                },
                "joints": [j["columns"] for j in snapshot["joints"]],
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("OK"), code(str(out_path)))
    kinds = ", ".join(f"{n} ({e['kind']})" for n, e in snapshot["columns"].items())
    state.console.print(f"  {snapshot['row_count']} rows; columns: {kinds}")
    if snapshot["joints"]:
        pairs = ", ".join("x".join(j["columns"]) for j in snapshot["joints"])
        state.console.print(f"  joints captured: {pairs}")


FIT_EPILOG = _FIT_EPILOG
