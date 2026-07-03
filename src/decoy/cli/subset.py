"""`decoy subset` -- FK-aware subsetting: cut a referentially-complete slice.

Thin wrapper over `decoy_engine.subset` (Sprint G SS1-SS5, shipped to engine
main). This module does arg-parsing, config-loading, output formatting, and
exit-code mapping ONLY -- the closure algorithm, budget enforcement, and
Parquet I/O all live in the engine (`decoy_engine.subset._api.run_subset` /
`plan_subset`). No subsetting logic is reimplemented here.

The seed spec (sample / filter / keys) and the fan-out policy (per-edge
direction toggles, budget caps, allow_dangling) are declared in the pipeline
YAML's `subset:` block -- the SAME config surface every other `decoy`
command reads (`PipelineConfig.model_validate`), per the engine's GATE-1 #5
decision. There is no separate subset-only CLI flag surface for those.

Modeled on `decoy plan` (dry-run-vs-real distinction, `--out` to redirect
output) and `decoy preflight` (surfacing a fail-closed report as clean
per-finding errors instead of a stack trace).

Dry-run safety UX (GATE-1 #3 "mandatory dry-run/estimate before any real
run"): `--dry-run` calls `plan_subset`, which never touches `output_dir` and
never reads a non-key column. The real run (`run_subset`) computes that same
estimate internally before writing anything -- the budget gate always sits
before the first Parquet write, with or without `--dry-run`.

No raw key values are ever printed. `SubsetPlan`/`SubsetManifest` (and their
`seed_specs_public`) are counts-and-identifiers-only by construction on the
engine side; this module only ever prints those objects, never a `SeedSpec`
verbatim.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, success, warn

_SUBSET_EPILOG = """\
Examples:

  decoy subset pipeline.yaml --dry-run
    Compute and print the projected per-table row counts WITHOUT writing
    anything. Runs the full preflight + closure estimate. Always do this
    before a real run on data you have not subsetted before.

  decoy subset pipeline.yaml --out subset_out/
    Run the subset for real: write filtered Parquet per table plus
    subset-manifest.json into subset_out/. subset_out/ must not already
    exist (or must be empty).

  decoy subset pipeline.yaml --out subset_out/ --json
    Same as above, structured JSON result on stdout.

The pipeline YAML must declare a `subset:` block (seeds + optional budget /
edge_directions / allow_dangling) alongside its `relationships:` block --
the same config surface `decoy run` reads. See `decoy schema` for the full
shape.

What this command checks before touching any data:
  - Every subsetted/relationship table's source is Parquet (subsetting does
    not run on CSV; the error names the offending table).
  - Every relationship edge's key columns exist, are type-compatible, and
    are not a half-declared composite.
  - Source-level FK orphans, per each relationship's orphan_policy.
  - The fan-out budget (max_total_rows / max_table_seed_multiple), BEFORE
    any output directory is created.

See also: decoy run, decoy validate, decoy preflight.
"""


def subset(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config (must declare a subset: block).",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help=(
            "Output directory for the filtered Parquet + subset-manifest.json. "
            "Required unless --dry-run. Must not already exist as a non-empty "
            "directory."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Compute the projected per-table row counts and print them WITHOUT "
            "materializing anything. No Parquet is written, no output_dir is "
            "created or touched. Use this before every real run."
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
        help="Suppress stdout. Errors still go to stderr; exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Cut a referentially-complete FK-aware subset of a relational dataset.

    Seeds a subset of root-table rows (per the config's `subset.seeds:`
    block) and pulls every row needed to keep foreign keys intact: children
    of a surviving parent (downward) and, by default, every parent of a
    surviving child (upward -- prevents dangling FKs). Runs a fail-closed
    preflight first (Parquet-only, schema/type checks, source-orphan scan)
    and a budget check before any output is written.

    `--dry-run` computes the same estimate and writes nothing; use it to see
    the projected row counts before committing to a real run.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    if not dry_run and out is None:
        _fail_usage(
            state,
            config_str,
            code_="subset_cli_missing_out",
            message=(
                "decoy subset requires --out <dir> for a real run "
                "(or pass --dry-run to only see the estimate)."
            ),
        )
        raise typer.Exit(code=EXIT_USAGE)

    if dry_run and out is not None and state.mode is not OutputMode.quiet:
        state.err_console.print(
            warn("warning:"),
            "--out is ignored with --dry-run; no files are written in dry-run mode.",
        )

    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _fail_usage(state, config_str, code_="yaml.parse_error", message=f"YAML parse error: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    if raw is None:
        _fail_usage(state, config_str, code_="yaml.empty", message="Pipeline YAML is empty.")
        raise typer.Exit(code=EXIT_USAGE)

    if not isinstance(raw, dict):
        _fail_usage(
            state,
            config_str,
            code_="yaml.not_mapping",
            message=f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.",
        )
        raise typer.Exit(code=EXIT_USAGE)

    from decoy_engine import PipelineConfig
    from decoy_engine import __version__ as engine_version
    from pydantic import ValidationError

    try:
        validated = PipelineConfig.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ())) or None
        msg = first.get("msg", str(exc))
        _fail_usage(
            state,
            config_str,
            code_=first.get("type", "validation_error"),
            message=f"{msg}" + (f" ({loc})" if loc else ""),
        )
        raise typer.Exit(code=EXIT_USAGE)

    if validated.subset is None:
        _fail_usage(
            state,
            config_str,
            code_="subset_config_missing",
            message=(
                "config has no `subset:` block. Add one (seeds + optional "
                "budget/edge_directions/allow_dangling) to run `decoy subset`. "
                "See `decoy schema` for the shape."
            ),
        )
        raise typer.Exit(code=EXIT_USAGE)

    config_dict = validated.model_dump()

    from decoy_engine.plan import PlanCompileError, job_seed_for_config
    from decoy_engine.subset import (
        SubsetBudgetExceededError,
        SubsetConfigError,
        SubsetInternalError,
        SubsetPreflightError,
        plan_subset,
        run_subset,
        subset_inputs_from_config,
    )

    try:
        sources, relationships, seeds, policy = subset_inputs_from_config(config_dict)
        job_seed = job_seed_for_config(config_dict)
    except SubsetConfigError as exc:
        _fail_usage(state, config_str, code_=exc.code, message=exc.message)
        raise typer.Exit(code=EXIT_USAGE)
    except PlanCompileError as exc:
        _fail_usage(state, config_str, code_=exc.code, message=exc.message)
        raise typer.Exit(code=EXIT_USAGE)

    try:
        if dry_run:
            plan = plan_subset(
                sources=sources,
                relationships=relationships,
                seeds=seeds,
                policy=policy,
                job_seed=job_seed,
                engine_version=engine_version,
            )
            _emit_dry_run(state, config_str, plan)
            return

        assert out is not None  # guaranteed by the --out/--dry-run check above
        result = run_subset(
            sources=sources,
            relationships=relationships,
            seeds=seeds,
            policy=policy,
            job_seed=job_seed,
            engine_version=engine_version,
            output_dir=out,
        )
        _emit_real_run(state, config_str, result, out)
    except SubsetPreflightError as exc:
        _emit_preflight_failure(state, config_str, exc)
        raise typer.Exit(code=EXIT_USAGE)
    except SubsetBudgetExceededError as exc:
        _emit_budget_failure(state, config_str, exc)
        raise typer.Exit(code=EXIT_USAGE)
    except SubsetConfigError as exc:
        _fail_usage(state, config_str, code_=exc.code, message=exc.message)
        raise typer.Exit(code=EXIT_USAGE)
    except SubsetInternalError as exc:
        # An engine-side invariant violation, not a user input problem.
        _fail_runtime(state, config_str, code_=exc.code, message=exc.message)
        raise typer.Exit(code=EXIT_RUNTIME)
    except typer.Exit:
        raise
    except Exception as exc:
        error_text = str(exc)
        if len(error_text) > 500:
            error_text = error_text[:500] + "..."
        _fail_runtime(state, config_str, code_=type(exc).__name__, message=error_text)
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=EXIT_RUNTIME)


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _table_estimate_rows(state, tables) -> None:
    tbl = make_table("Table", "Input rows", "Seed rows", "Surviving rows", "Seed-null-excluded")
    for t in sorted(tables, key=lambda e: e.table):
        tbl.add_row(
            t.table,
            str(t.input_rows),
            str(t.seed_rows),
            str(t.surviving_rows),
            str(t.seed_null_excluded),
        )
    state.console.print(tbl)


def _edge_stats_rows(state, edges) -> None:
    tbl = make_table("Edge", "Direction", "Rows added downward", "Rows added upward")
    for e in sorted(edges, key=lambda e: e.edge_id):
        tbl.add_row(e.edge_id, e.direction, str(e.rows_added_downward), str(e.rows_added_upward))
    state.console.print(tbl)


def _table_estimate_to_dict(t) -> dict[str, Any]:
    return {
        "table": t.table,
        "input_rows": t.input_rows,
        "seed_rows": t.seed_rows,
        "surviving_rows": t.surviving_rows,
        "seed_null_excluded": t.seed_null_excluded,
    }


def _edge_stats_to_dict(e) -> dict[str, Any]:
    return {
        "edge_id": e.edge_id,
        "direction": e.direction,
        "rows_added_downward": e.rows_added_downward,
        "rows_added_upward": e.rows_added_upward,
    }


def _emit_dry_run(state, config_str: str, plan) -> None:
    """Print the dry-run estimate. This is the safety UX: it must be
    unmistakable that nothing was written."""
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "subset",
                "status": "ok",
                "dry_run": True,
                "config": config_str,
                "engine_version": plan.engine_version,
                "seed_specs": list(plan.seed_specs_public),
                "tables": [_table_estimate_to_dict(t) for t in plan.tables],
                "edges": [_edge_stats_to_dict(e) for e in plan.edges],
                "closure_rounds": plan.closure_rounds,
                "budget_outcome": plan.budget_outcome,
                "total_surviving_rows": plan.total_surviving_rows,
                "warnings": list(plan.warnings),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"DRY RUN -- {config_str} -- no files written"))
    state.console.print()
    _table_estimate_rows(state, plan.tables)
    state.console.print()
    _edge_stats_rows(state, plan.edges)
    state.console.print()
    state.console.print(
        hint("Closure rounds:"), str(plan.closure_rounds),
        " ", hint("Budget:"), plan.budget_outcome,
        " ", hint("Total surviving rows:"), str(plan.total_surviving_rows),
    )
    for w in plan.warnings:
        state.console.print(warn("warning:"), w)
    state.console.print()
    state.console.print(
        hint("Next:"), "drop --dry-run and add", code("--out <dir>"), "to materialize this subset."
    )


def _emit_real_run(state, config_str: str, result, out: Path) -> None:
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "subset",
                "status": "ok",
                "dry_run": False,
                "config": config_str,
                "out": str(out),
                "engine_version": result.manifest.engine_version,
                "seed_specs": list(result.manifest.seed_specs_public),
                "tables": [_table_estimate_to_dict(t) for t in result.manifest.tables],
                "edges": [_edge_stats_to_dict(e) for e in result.manifest.edges],
                "closure_rounds": result.manifest.closure_rounds,
                "budget_outcome": result.manifest.budget_outcome,
                "output_paths": [
                    {"table": table, "path": path} for table, path in result.output_paths
                ],
                "manifest_path": str(out / "subset-manifest.json"),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(success(f"Subset written -- {config_str}"))
    state.console.print()
    _table_estimate_rows(state, result.manifest.tables)
    state.console.print()
    total = sum(t.surviving_rows for t in result.manifest.tables)
    state.console.print(
        hint("Output dir:"), code(str(out)),
        " ", hint("Tables written:"), str(len(result.output_paths)),
        " ", hint("Total rows:"), str(total),
    )
    state.console.print(hint("Manifest:"), code(str(out / "subset-manifest.json")))


def _emit_preflight_failure(state, config_str: str, exc) -> None:
    """A fail-closed preflight condition (type mismatch, half-composite,
    dangling column, non-Parquet source, source orphans under
    orphan_policy=fail). Never a stack trace: every code and message here
    comes straight off `FkPreflightReport`."""
    report = exc.report
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "subset",
                "status": "error",
                "error_kind": "preflight",
                "config": config_str,
                "code": exc.code,
                "error": exc.message,
                "failures": [
                    {"code": f.code, "relationship": f.relationship, "message": f.message}
                    for f in report.failures
                ],
                "warnings": list(report.warnings),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.err_console.print(error("error:"), "subset preflight failed:")
    for f in report.failures:
        # f.message already names the relationship/edge_id (built by the
        # engine's preflight); do not prefix it again here.
        state.err_console.print(" ", error(f"[{f.code}]"), f.message)
    for w in report.warnings:
        state.err_console.print(" ", warn("warning:"), w)
    state.err_console.print(
        " ", hint("hint:"), "fix the config/source problems above, then rerun."
    )


def _emit_budget_failure(state, config_str: str, exc) -> None:
    """The fan-out budget was exceeded. No output was ever written (the
    engine's hard-fail contract runs the budget check before output_dir is
    touched); this handler never has cleanup to do."""
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "subset",
                "status": "error",
                "error_kind": "budget_exceeded",
                "config": config_str,
                "code": exc.code,
                "error": exc.message,
                "scope": exc.scope,
                "table": exc.table,
                "cap": exc.cap,
                "actual": exc.actual,
                "seed_total": exc.seed_total,
                "edge_id": exc.edge_id,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.err_console.print(error("error:"), exc.message)
    state.err_console.print(
        " ", hint("hint:"), "rerun with --dry-run to inspect the estimate before adjusting budget."
    )


def _fail_usage(state, config_str: str, *, code_: str, message: str) -> None:
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "subset",
                "status": "error",
                "error_kind": "usage",
                "config": config_str,
                "code": code_,
                "error": message,
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return
    state.err_console.print(error("error:"), f"[{code_}] {message}")


def _fail_runtime(state, config_str: str, *, code_: str, message: str) -> None:
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "subset",
                "status": "error",
                "error_kind": "runtime",
                "config": config_str,
                "code": code_,
                "error": message,
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return
    state.err_console.print(error("error:"), f"[{code_}] {message}")
    state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")


SUBSET_EPILOG = _SUBSET_EPILOG
