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

DPS-CLI rewire (docs/plans/2026-07-24-dps-cli-fit-rewire.md). `--epsilon`
now selects a second, disjoint mode that calls the engine's
`fit_dp_snapshot` (typed-carrier `dps-marginal/v3`), replacing the removed
`apply_dp_noise`. The two modes are kept from blurring by making every
DP-only option (`--delta`, `--dp-number`/`--dp-flag`/`--dp-text`,
`--numeric-bins`, `--dp-allow-omit`) a usage error when `--epsilon` is
absent -- otherwise an operator who declares carriers but forgets
`--epsilon` would silently fall through to the exact, non-DP snapshot (a
fail-open release of exact data).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import typer

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success, warn

_FIT_EPILOG = """\
Examples:

  decoy fit customers.csv
    Write customers.snapshot.json next to the source.

  decoy fit customers.csv --output snapshot.json --parse-dates signup_date
    Treat signup_date as a datetime column.

  decoy fit customers.csv --joint state,tier
    Capture the (state, tier) contingency table so a statistical column
    can use `condition_on`.

  decoy fit customers.csv --epsilon 1.0 --delta 1e-6 \\
      --dp-number amount:0:500 --dp-text state --dp-flag is_active
    Differentially private release (dps-marginal/v3): every declared
    column is released under one (epsilon, delta) budget through OpenDP.
    Every column MUST be declared with a carrier (--dp-number for a
    numeric column plus its data-independent domain, --dp-text for a
    categorical column, --dp-flag for a boolean column); an undeclared
    source column is a usage error unless --dp-allow-omit is passed.
    --epsilon requires --delta and is incompatible with --joint and
    --parse-dates.

See also: decoy run, decoy validate, decoy explain differential-privacy.
"""


class _FitUsageError(Exception):
    """A pre-CSV-read validation failure: bad flag combination, malformed
    carrier declaration, or an omitted column with no `--dp-allow-omit`.
    Carries a machine-readable `code` so `--json` mode can surface it
    alongside the human message, same shape as the engine's own coded
    exceptions."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def _parse_dp_number_spec(spec: str) -> tuple[str, tuple[float, float]]:
    """Parse one `--dp-number COL:LO:HI` spec. Validated here, before the CSV
    is read, so a malformed domain never reaches the engine (which would
    otherwise reject it only after the source file has been opened)."""
    parts = spec.split(":")
    if len(parts) != 3 or not parts[0].strip():
        raise _FitUsageError(
            f"--dp-number expects 'COL:LO:HI'; got {spec!r}.",
            code="dp_number_spec_invalid",
        )
    col, lo_raw, hi_raw = parts[0].strip(), parts[1].strip(), parts[2].strip()
    try:
        lo = float(lo_raw)
        hi = float(hi_raw)
    except ValueError:
        raise _FitUsageError(
            f"--dp-number {spec!r}: LO and HI must be numbers.",
            code="dp_number_spec_invalid",
        )
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise _FitUsageError(
            f"--dp-number {spec!r}: LO and HI must be finite.",
            code="dp_numeric_domain_invalid",
        )
    if not lo < hi:
        raise _FitUsageError(
            f"--dp-number {spec!r}: domain must satisfy LO < HI, got ({lo!r}, {hi!r}).",
            code="dp_numeric_domain_invalid",
        )
    return col, (lo, hi)


def _build_column_schema(
    dp_number: list[str], dp_flag: list[str], dp_text: list[str]
) -> dict[str, dict[str, Any]]:
    """Parse the repeatable carrier flags into the engine's `column_schema`
    shape. Duplicate or conflicting declarations for one column (the same
    column named twice, in the same flag or across flags) are a usage
    error -- never silently last-wins (D1 of the rewire plan)."""
    schema: dict[str, dict[str, Any]] = {}

    def _declare(raw_col: str, entry: dict[str, Any], source: str) -> None:
        col = raw_col.strip()
        if not col:
            raise _FitUsageError(f"{source}: empty column name.", code="dp_schema_column_empty")
        if col in schema:
            raise _FitUsageError(
                f"column {col!r} is declared more than once ({source} conflicts with a "
                "prior --dp-number/--dp-flag/--dp-text declaration for this column); each "
                "column may have exactly one DP carrier declaration.",
                code="dp_schema_duplicate_column",
            )
        schema[col] = entry

    for spec in dp_number:
        col, (lo, hi) = _parse_dp_number_spec(spec)
        _declare(col, {"kind": "numeric", "carrier": "number", "bounds": [lo, hi]}, "--dp-number")
    for raw_col in dp_flag:
        _declare(raw_col, {"kind": "categorical", "carrier": "flag"}, "--dp-flag")
    for raw_col in dp_text:
        _declare(raw_col, {"kind": "categorical", "carrier": "text"}, "--dp-text")
    return schema


# The fixed, case-insensitive, whitespace-trimmed flag grammar (D6 of the
# rewire plan). CSV carries no dtype, so a `--dp-flag` column arrives as
# strings; the engine's flag codec rejects strings outright (a `"1"` is not
# a flag). Every token outside this set maps to null SILENTLY -- no error,
# warning, or count may depend on a cell's content, because that would make
# a fit's success/failure a function of the data, the exact channel the
# codec's totality/boxing-invariance design closes.
_FLAG_TRUE_TOKENS = frozenset({"true", "1"})
_FLAG_FALSE_TOKENS = frozenset({"false", "0"})


def _map_flag_token(cell: object) -> bool | None:
    if cell is None:
        return None
    try:
        import pandas as pd

        if pd.isna(cell):
            return None
    except (TypeError, ValueError):
        pass
    token = str(cell).strip().lower()
    if token in _FLAG_TRUE_TOKENS:
        return True
    if token in _FLAG_FALSE_TOKENS:
        return False
    return None


def _apply_flag_grammar(df: Any, flag_columns: list[str]) -> Any:
    """Return a copy of `df` with every declared `--dp-flag` column mapped
    through the fixed grammar to `True`/`False`/`None`. Runs BEFORE the
    engine call so the frame it receives already carries real bool cells
    for flag columns (the codec never sees the raw CSV string)."""
    if not flag_columns:
        return df
    out = df.copy()
    for col in flag_columns:
        out[col] = out[col].map(_map_flag_token)
    return out


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
        help="Column(s) to parse as datetimes (repeatable). CSV carries no dtype, so date columns must be named explicitly. Not supported with --epsilon.",
    ),
    joint: list[str] = typer.Option(
        [],
        "--joint",
        help="Column pair 'a,b' whose contingency table to capture (repeatable). Needed for `condition_on`. Not supported with --epsilon.",
    ),
    epsilon: float = typer.Option(
        None,
        "--epsilon",
        help=(
            "Select DP mode: fit a dps-marginal/v3 artifact via the engine's "
            "fit_dp_snapshot instead of the exact snapshot. Requires --delta and "
            "at least one carrier declaration (--dp-number/--dp-flag/--dp-text). "
            "This is the ONLY DP-mode selector -- every DP-only option is a usage "
            "error without it, so a forgotten --epsilon never silently falls back "
            "to the exact release."
        ),
    ),
    delta: float = typer.Option(
        None,
        "--delta",
        help="DP failure probability, required with --epsilon (no default: a silent delta would set an unchosen privacy level). Finite, in (0, 1).",
    ),
    dp_number: list[str] = typer.Option(
        [],
        "--dp-number",
        help="'COL:LO:HI' -- declare COL as a DP numeric carrier with a data-independent domain (repeatable). Requires --epsilon.",
    ),
    dp_flag: list[str] = typer.Option(
        [],
        "--dp-flag",
        help="Declare COL as a DP boolean/flag carrier (repeatable). Requires --epsilon.",
    ),
    dp_text: list[str] = typer.Option(
        [],
        "--dp-text",
        help="Declare COL as a DP categorical text carrier (repeatable). Requires --epsilon.",
    ),
    numeric_bins: int = typer.Option(
        None,
        "--numeric-bins",
        help="Bin count per DP numeric column (engine default if omitted). Requires --epsilon.",
    ),
    dp_allow_omit: bool = typer.Option(
        False,
        "--dp-allow-omit",
        help=(
            "Allow the DP release to omit source columns nobody declared with "
            "--dp-number/--dp-flag/--dp-text (default: omission is a usage error "
            "listing the columns). Requires --epsilon."
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

    Without --epsilon: reads the source CSV, captures per-column
    distribution shape (numeric histograms + quantiles, categorical top-k,
    datetime year bins) plus any requested pairwise contingency tables, and
    writes the JSON artifact `type: statistical` generate columns reference
    via `snapshot_file`.

    With --epsilon: fits a `dps-marginal/v3` artifact instead, releasing
    ONLY the columns declared via --dp-number/--dp-flag/--dp-text under one
    (epsilon, delta) budget. Exits 0 on success, 1 on bad input, 3 if the
    engine's DP fit refuses at run time (an uncertified proof stack, or an
    internal schedule invariant).
    """
    state = setup_output(json_, quiet, verbose)

    def _emit_error(
        message: str, *, err_code: str | None = None, hint_text: str | None = None
    ) -> None:
        if state.mode is OutputMode.json:
            payload: dict[str, Any] = {
                "command": "fit",
                "status": "error",
                "source": str(source),
            }
            if err_code is not None:
                payload["code"] = err_code
                payload["message"] = message
                payload["error"] = f"{err_code}: {message}"
            else:
                payload["error"] = message
            if hint_text is not None:
                payload["hint"] = hint_text
            emit_json(state, payload)
        elif state.mode is not OutputMode.quiet:
            prefix = f"{err_code}: " if err_code is not None else ""
            state.err_console.print(error("error:"), f"{prefix}{message}")
            if hint_text is not None:
                state.err_console.print(" ", hint("hint:"), hint_text)

    joint_pairs: list[tuple[str, str]] = []
    for spec in joint:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        if len(parts) != 2:
            _emit_error(
                f"--joint expects 'colA,colB'; got {spec!r}.",
                err_code="dp_usage_joint_spec_invalid",
            )
            raise typer.Exit(code=EXIT_USAGE)
        joint_pairs.append((parts[0], parts[1]))

    # --- D0: DP mode is explicit and fail-closed, decided BEFORE the CSV is
    # read and before any carrier declaration is parsed for content. ---------
    has_carrier_decls = bool(dp_number or dp_flag or dp_text)
    delta_given = delta is not None
    numeric_bins_given = numeric_bins is not None

    try:
        if epsilon is None:
            dp_only_given = []
            if delta_given:
                dp_only_given.append("--delta")
            if has_carrier_decls:
                dp_only_given.append("--dp-number/--dp-flag/--dp-text")
            if numeric_bins_given:
                dp_only_given.append("--numeric-bins")
            if dp_allow_omit:
                dp_only_given.append("--dp-allow-omit")
            if dp_only_given:
                raise _FitUsageError(
                    f"{', '.join(dp_only_given)} require --epsilon (DP mode is not "
                    "selected). Pass --epsilon to run the DP fit, or drop them to run "
                    "the exact (non-DP) fit.",
                    code="dp_mode_not_selected",
                )
        else:
            if joint_pairs:
                raise _FitUsageError(
                    "--epsilon with --joint is not supported: releasing marginals "
                    "plus joint tables under one epsilon needs composition accounting "
                    "not implemented here. Drop --joint or omit --epsilon.",
                    code="dp_mode_joint_unsupported",
                )
            if parse_dates:
                raise _FitUsageError(
                    "--epsilon with --parse-dates is not supported: datetime handling "
                    "for a DP fit is decided at the option level, never by inspecting "
                    "data. Declare a date-like column with --dp-text (ordinary "
                    "categorical text) if that is acceptable, or omit --epsilon.",
                    code="dp_mode_parse_dates_unsupported",
                )
            if not delta_given:
                raise _FitUsageError(
                    "--epsilon requires --delta: the (epsilon, delta) budget must be "
                    "fully specified, and there is no default delta (a silent default "
                    "would set a privacy level you did not choose).",
                    code="dp_mode_delta_required",
                )
            if not has_carrier_decls:
                raise _FitUsageError(
                    "--epsilon requires at least one carrier declaration "
                    "(--dp-number/--dp-flag/--dp-text): an epsilon with nothing "
                    "declared would release nothing.",
                    code="dp_mode_no_carriers",
                )

        column_schema = _build_column_schema(dp_number, dp_flag, dp_text)
    except _FitUsageError as exc:
        _emit_error(exc.message, err_code=exc.code)
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

    if epsilon is None:
        snapshot = compute_distribution_snapshot(df, joint_columns=joint_pairs or None)
        omitted_columns: list[str] = []
    else:
        from decoy_engine.quality.carriers import CarrierError
        from decoy_engine.quality.dp import DpError, fit_dp_snapshot
        from decoy_engine.quality.dp_budget import DpBudgetError
        from decoy_engine.quality.dp_provenance import ProvenanceError

        # D3: only declared columns are ever released; an undeclared source
        # column is a usage error by default (the foot-gun of silently
        # dropping a column the operator expected to see), unless the
        # operator explicitly opts in with --dp-allow-omit.
        omitted_columns = sorted(set(df.columns) - set(column_schema))
        if omitted_columns and not dp_allow_omit:
            _emit_error(
                f"source column(s) not declared for the DP release: {', '.join(omitted_columns)}.",
                err_code="dp_columns_omitted",
                hint_text=(
                    "declare each with --dp-number/--dp-flag/--dp-text, or pass "
                    "--dp-allow-omit to release only the declared columns."
                ),
            )
            raise typer.Exit(code=EXIT_USAGE)
        if omitted_columns:
            omission_notice = (
                f"omitting {len(omitted_columns)} undeclared source column(s) from "
                f"the DP release: {', '.join(omitted_columns)}."
            )
            if state.mode is not OutputMode.quiet:
                state.err_console.print(warn("notice:"), omission_notice)

        flag_columns = [c for c, spec in column_schema.items() if spec.get("carrier") == "flag"]
        typed_df = _apply_flag_grammar(df, flag_columns)

        dp_kwargs: dict[str, Any] = {}
        if numeric_bins is not None:
            dp_kwargs["numeric_bins"] = numeric_bins

        try:
            snapshot = fit_dp_snapshot(
                typed_df, column_schema, epsilon=epsilon, delta=delta, **dp_kwargs
            )
        except ProvenanceError as exc:
            _emit_error(
                exc.message,
                err_code=exc.code,
                hint_text="this host is not a certified DP platform/stack.",
            )
            raise typer.Exit(code=EXIT_RUNTIME)
        except DpBudgetError as exc:
            exit_code = EXIT_RUNTIME if exc.code == "dp_schedule_mismatch" else EXIT_USAGE
            _emit_error(exc.message, err_code=exc.code)
            raise typer.Exit(code=exit_code)
        except (DpError, CarrierError) as exc:
            _emit_error(exc.message, err_code=exc.code)
            raise typer.Exit(code=EXIT_USAGE)

    # Only reached on success: no artifact is created or overwritten when the
    # fit above raised.
    out_path = output if output is not None else source.with_suffix(".snapshot.json")
    out_path.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    if state.mode is OutputMode.json:
        payload: dict[str, Any] = {
            "command": "fit",
            "status": "ok",
            "source": str(source),
            "output": str(out_path),
            "row_count": snapshot["row_count"],
            "columns": {name: entry["kind"] for name, entry in snapshot["columns"].items()},
            "joints": [j["columns"] for j in snapshot["joints"]],
        }
        if epsilon is not None:
            payload["dp"] = {"schema": snapshot["dp"]["schema"]}
            payload["omitted_columns"] = omitted_columns
        emit_json(state, payload)
        return
    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("OK"), code(str(out_path)))
    kinds = ", ".join(f"{n} ({e['kind']})" for n, e in snapshot["columns"].items())
    state.console.print(f"  {snapshot['row_count']} rows; columns: {kinds}")
    if snapshot["joints"]:
        pairs = ", ".join("x".join(j["columns"]) for j in snapshot["joints"])
        state.console.print(f"  joints captured: {pairs}")
    if epsilon is not None:
        state.console.print(
            f"  DP release: {snapshot['dp']['schema']}, epsilon={epsilon}, delta={delta}"
        )


FIT_EPILOG = _FIT_EPILOG
