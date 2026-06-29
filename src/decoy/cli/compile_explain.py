"""`decoy compile [--explain]` -- compile a pipeline recipe and optionally explain
the resulting plan.

Without --explain: compile the config, run the five S1 plan-compile checks, and
report pass/fail. Exit 0 when all checks pass; exit EXIT_USAGE on a compile error.

With --explain: same compilation, then render per-column declared strategy and
params, the table execution order, and the rationale for each decision.

HONESTY: this command explains the decisions that were explicitly declared in the
pipeline config and what the compile checks verified. It does NOT guarantee:
  - the chosen strategy is appropriate for the actual data in the source file
  - all PII is covered or masked correctly
  - the output is safe to share

Use `decoy storm analyze` to inspect the source data before writing a pipeline,
and `decoy validate` for full config validation.

Reuses the engine's compile_plan path. Does NOT reimplement compilation.
No-profile mode is always used here because --explain is about the config
decisions, not about source-data-dependent checks.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, success, warn

_COMPILE_EPILOG = """\
Examples:

  decoy compile pipeline.yaml
    Compile a recipe and show pass/fail for all compile checks.

  decoy compile pipeline.yaml --explain
    Compile a recipe and show per-column resolved strategy, params, and rationale.

  decoy compile pipeline.yaml --explain --json
    Same as --explain but as structured JSON for scripting or CI.

  decoy compile pipeline.yaml --explain --quiet
    Silent compile; exit code 0 = all checks passed.

HONESTY: compile --explain explains decisions declared in the config and what the
compiler verified. It does not guarantee the strategy is correct for the data,
that all PII is covered, or that the output is safe to share.

See also: decoy validate, decoy plan, decoy storm analyze.
"""

# Rationale templates: strategies come from explicit user declarations in the
# config. The engine does NOT auto-assign strategies (the old FORECAST recommender
# was retired under storm-reframe-C, 2026-05-30). The compile checks then VERIFY
# the declared config (provider exists, namespaces consistent, etc.) but do not
# change any decisions.
_RATIONALE_DECLARED = "declared in pipeline config"
_RATIONALE_NONE = "no strategy declared"


def compile(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the pipeline YAML config to compile.",
    ),
    explain: bool = typer.Option(
        False,
        "--explain",
        help=(
            "Explain the compiled plan: per-column declared strategy, params, "
            "execution order, and rationale. Without this flag, only the compile "
            "pass/fail summary is shown."
        ),
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
    """Compile a pipeline config and run plan-compile checks.

    Use --explain to see per-column strategy, params, and rationale for each
    compile decision. Without --explain, shows a compact pass/fail summary.

    HONESTY: compile explains what is in the config and what the compiler
    verified. It does not guarantee correctness, PII coverage, or safety.
    """
    state = setup_output(json_, quiet, verbose)

    # Parse YAML -- defensive; real parse errors surface here.
    try:
        raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "compile explain",
                    "status": "error",
                    "config": str(config),
                    "error": f"YAML parse error: {exc}",
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"YAML parse error: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    if not isinstance(raw, dict):
        msg = f"{config} does not parse to a YAML mapping at the top level."
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "compile explain", "status": "error", "config": str(config), "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    # Compile: validate config, run plan-compile checks.
    try:
        from datetime import datetime

        from decoy_engine import __version__ as engine_version
        from decoy_engine.plan import compile_plan
        from decoy_engine.profile import Profile

        # Build the empty "no profile" sentinel Profile.
        profile = Profile(
            schema_version=1,
            tables=(),
            relationships=(),
            profiled_at=datetime(1970, 1, 1, 0, 0, 0),
            decoy_engine_version=engine_version,
            profile_seed=None,
        )

        plan = compile_plan(raw, profile, decoy_engine_version=engine_version, no_profile=True)
    except Exception as exc:
        _compile_error(state, config, exc)
        raise typer.Exit(code=EXIT_USAGE)

    # Extract per-column info from the config (strategies come from the user's
    # explicit declarations; compile_plan verifies them but does not change them).
    tables_info = _extract_tables_info(raw)
    checks_passed = list(plan.plan_compile.checks_passed)
    checks_skipped = list(plan.plan_compile.checks_skipped)
    warnings_list = list(plan.plan_compile.warnings)

    if state.mode is OutputMode.json:
        payload: dict = {
            "command": "compile explain",
            "status": "ok",
            "config": str(config),
            "engine_version": plan.engine_version,
            "pipeline_config_hash": plan.pipeline_config_hash,
            "compile_checks": {
                "passed": checks_passed,
                "skipped": checks_skipped,
                "warnings": warnings_list,
            },
        }
        if explain:
            payload["tables"] = tables_info
            payload["ordering"] = [
                {"table": n.table, "columns": list(n.columns)}
                for n in plan.ordering
            ]
            payload["honesty_note"] = (
                "Strategies are declared in the pipeline config by the user. "
                "compile --explain verifies those declarations; it does not "
                "guarantee the strategy is correct for the data or that all PII "
                "is covered. Use decoy storm analyze to inspect source data."
            )
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable output.
    state.console.print(accent(f"Compile: {config.name}"))
    state.console.print()

    if explain:
        _render_explain(state, tables_info, plan)
    else:
        _render_summary(state, checks_passed, checks_skipped, warnings_list)


def _compile_error(state, config: Path, exc: Exception) -> None:
    """Render a compile error to the appropriate output stream."""
    # Import lazily to keep startup fast.
    try:
        from decoy_engine.plan import PlanCompileError

        if isinstance(exc, PlanCompileError):
            msg = f"[{exc.code}] {exc.path or '<global>'}: {exc.message}"
        else:
            msg = str(exc)
    except ImportError:
        msg = str(exc)

    from decoy.ui.output import OutputMode

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "compile explain",
                "status": "error",
                "error": msg,
            },
        )
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), msg)
        state.err_console.print(
            " ", hint("hint:"), "run", code("decoy validate <config>"), "for full validation."
        )


def _extract_tables_info(raw: dict) -> list[dict]:
    """Extract per-table, per-column info from the raw (or validated) config dict.

    Returns a list of table dicts, each with name and columns list.
    Each column has: name, strategy, provider, cardinality_mode, deterministic,
    vault, rationale.

    The rationale distinguishes columns that have an explicit strategy declared
    ('declared in pipeline config') from columns with no strategy ('no strategy
    declared').  Decoy does not auto-assign strategies; the compile checks VERIFY
    declarations but do not generate them.
    """
    tables = raw.get("tables") or []
    result = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        tname = table.get("name", "?")
        columns = table.get("columns") or []
        col_records = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            strategy = col.get("strategy") or "none"
            rationale = _RATIONALE_DECLARED if strategy != "none" else _RATIONALE_NONE
            col_records.append(
                {
                    "name": col.get("name", "?"),
                    "strategy": strategy,
                    "provider": col.get("provider"),
                    "cardinality_mode": col.get("cardinality_mode"),
                    "deterministic": col.get("deterministic", False),
                    "vault": col.get("vault", False),
                    "coherent_with": col.get("coherent_with") or [],
                    "rationale": rationale,
                }
            )
        result.append({"name": tname, "columns": col_records})
    return result


def _render_explain(state, tables_info: list[dict], plan) -> None:
    """Render the per-column explain view."""
    for table_info in tables_info:
        state.console.print(accent(f"Table: {table_info['name']}"))
        table = make_table("Column", "Strategy", "Provider", "Cardinality", "Vault", "Rationale")
        for col in table_info["columns"]:
            table.add_row(
                col["name"],
                col["strategy"],
                col["provider"] or "",
                col["cardinality_mode"] or "default",
                "yes" if col["vault"] else "no",
                col["rationale"],
            )
        state.console.print(table)
        state.console.print()

    # Execution ordering (if the planner produced one).
    if plan.ordering:
        state.console.print(accent("Execution order:"))
        order_table = make_table("Step", "Table", "Columns")
        for i, node in enumerate(plan.ordering, 1):
            order_table.add_row(str(i), node.table, ", ".join(node.columns))
        state.console.print(order_table)
        state.console.print()
    else:
        state.console.print(
            hint("Ordering:"),
            "tables execute in config declaration order (no FK dependencies detected).",
        )
        state.console.print()

    # Compile checks summary.
    _render_checks(state, plan)

    # Honesty notice.
    state.console.print(
        hint("Note:"),
        "compile --explain explains declarations in the config. "
        "It does not guarantee the strategy is correct for the data, "
        "that all PII is covered, or that the output is safe to share. "
        "Use",
        code("decoy storm analyze"),
        "to inspect source data first.",
    )


def _render_summary(
    state, checks_passed: list[str], checks_skipped: list[str], warnings: list[str]
) -> None:
    """Render a compact compile pass/fail summary."""
    state.console.print(
        success("Compile OK."),
        f"{len(checks_passed)} checks passed,",
        f"{len(checks_skipped)} skipped (--no-profile).",
    )
    if warnings:
        for w in warnings:
            state.console.print(warn("warning:"), w)
    state.console.print()
    state.console.print(
        hint("Tip:"),
        "add",
        code("--explain"),
        "to see per-column strategy and rationale.",
    )


def _render_checks(state, plan) -> None:
    """Render the compile checks section."""
    checks_passed = list(plan.plan_compile.checks_passed)
    checks_skipped = list(plan.plan_compile.checks_skipped)
    warnings_list = list(plan.plan_compile.warnings)

    state.console.print(
        accent(
            f"Compile checks: {len(checks_passed)} passed, "
            f"{len(checks_skipped)} skipped (no-profile mode)."
        )
    )
    tbl = make_table("Check", "Result")
    for c in checks_passed:
        tbl.add_row(c, "pass")
    for c in checks_skipped:
        tbl.add_row(c, "skipped")
    state.console.print(tbl)
    if warnings_list:
        for w in warnings_list:
            state.console.print(warn("warning:"), w)
    state.console.print()


COMPILE_EPILOG = _COMPILE_EPILOG
