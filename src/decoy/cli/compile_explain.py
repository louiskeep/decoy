"""`decoy validate compile [--explain]` -- compile a pipeline recipe, run the
plan-compile checks, and optionally explain the resulting plan or write the
frozen plan artifact.

Without --explain: compile the config, run the plan-compile checks, and report
pass/fail. Exit 0 when all checks pass; exit EXIT_USAGE on a compile error.

With --explain: same compilation, then render per-column declared strategy and
params, the table execution order, and the rationale for each decision.

Profile selection (absorbed from the retired top-level `plan` command, S2):
  --no-profile (default, matching the old `compile`): compile without source
  data; the profile-dependent checks land in plan_compile.checks_skipped.
  --profile <profile.json>: load a pre-computed Profile and run ALL plan-compile
  checks, including the profile-dependent ones.

With --output <path> [--format yaml|json], also write the frozen plan artifact
to disk (the old top-level `plan` command). The H1 (no check in both checks_passed
and checks_skipped) and H2 (--no-profile is incompatible with
cardinality_mode: unique) honesty guards come from `decoy.cli.plan` and are
reused verbatim here.

HONESTY: this command explains the decisions that were explicitly declared in the
pipeline config and what the compile checks verified. It does NOT guarantee:
  - the chosen strategy is appropriate for the actual data in the source file
  - all PII is covered or masked correctly
  - the output is safe to share

Use `decoy pre-scan` to inspect the source data before writing a pipeline,
and `decoy validate config` for schema-only config validation.

Reuses the engine's compile_plan path. Does NOT reimplement compilation.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, success, warn

_COMPILE_EPILOG = """\
Examples:

  decoy validate compile pipeline.yaml
    Compile a recipe and show pass/fail for all compile checks (--no-profile).

  decoy validate compile pipeline.yaml --explain
    Compile a recipe and show per-column declared strategy, params, and rationale.

  decoy validate compile pipeline.yaml --profile profile.json
    Load a pre-computed Profile and run ALL plan-compile checks (none skipped).

  decoy validate compile pipeline.yaml --output plan.yaml
    Also write the frozen plan artifact to plan.yaml (YAML; use --format json for JSON).

  decoy validate compile pipeline.yaml --explain --json
    Same as --explain but as structured JSON for scripting or CI.

  decoy validate compile pipeline.yaml --explain --quiet
    Silent compile; exit code 0 = all checks passed.

HONESTY: compile --explain explains decisions declared in the config and what the
compiler verified. It does not guarantee the strategy is correct for the data,
that all PII is covered, or that the output is safe to share.

See also: decoy validate, decoy validate config, decoy pre-scan.
"""

# Rationale templates: strategies come from explicit user declarations in the
# config. The engine does NOT auto-assign strategies (the old FORECAST recommender
# was retired, 2026-05-30). The compile checks then VERIFY
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
    profile_path: Path | None = typer.Option(
        None,
        "--profile",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Path to a pre-computed Profile JSON file. Runs ALL plan-compile "
            "checks, including the profile-dependent ones. Without it, "
            "--no-profile mode is used (profile-dependent checks are skipped)."
        ),
    ),
    no_profile: bool = typer.Option(
        False,
        "--no-profile",
        help=(
            "Compile without source data (the default). Profile-dependent checks "
            "land in plan_compile.checks_skipped. Incompatible with --profile."
        ),
    ),
    out: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Also write the frozen plan artifact to this path (absorbs the old `plan` command).",
    ),
    out_format: str = typer.Option(
        "yaml",
        "--format",
        help="On-disk format for the --output artifact: yaml (default) or json.",
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
    Use --profile to run the profile-dependent checks, and --output to also
    write the frozen plan artifact (the folded `plan` behavior).

    HONESTY: compile explains what is in the config and what the compiler
    verified. It does not guarantee correctness, PII coverage, or safety.
    """
    # Profile-fold helpers live in cli/plan.py (the retired `plan` command's
    # reusable write/H1/H2 helpers); import them rather than reimplement (S2).
    from decoy.cli.plan import (
        empty_profile_for_no_profile,
        find_first_unique_column_path,
        render_plan_artifact,
    )

    state = setup_output(json_, quiet, verbose)

    if profile_path is not None and no_profile:
        _simple_error(state, config, "--no-profile and --profile are mutually exclusive.")
        raise typer.Exit(code=EXIT_USAGE)

    if out_format not in ("yaml", "json"):
        _simple_error(state, config, f"--format must be one of yaml, json; got {out_format!r}.")
        raise typer.Exit(code=EXIT_USAGE)

    # Parse YAML -- defensive; real parse errors surface here.
    try:
        raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        # YAMLError quotes the offending source line; sanitize to coordinates.
        _simple_error(state, config, sanitize_yaml_error(exc))
        raise typer.Exit(code=EXIT_USAGE)
    except (OSError, UnicodeDecodeError) as exc:
        # A read/decode failure is a different category; report it as one. The
        # path is the user's own argument and only the exception TYPE is shown,
        # never str(exc) (a UnicodeDecodeError repr carries the offending byte).
        # UnicodeDecodeError is a ValueError, not an OSError, so it is named
        # explicitly: without it a non-UTF-8 config would escape as an uncaught
        # traceback and emit no --json envelope.
        _simple_error(state, config, f"could not read {config}: {type(exc).__name__}")
        raise typer.Exit(code=EXIT_USAGE)

    if not isinstance(raw, dict):
        _simple_error(state, config, f"{config} does not parse to a YAML mapping at the top level.")
        raise typer.Exit(code=EXIT_USAGE)

    from decoy_engine import __version__ as engine_version
    from decoy_engine.plan import compile_plan
    from decoy_engine.profile import profile_from_json

    # Resolve the profile. --profile loads a pre-computed Profile and runs the
    # full check set; otherwise no-profile mode (the default) uses the empty
    # sentinel profile and records the profile-dependent checks as skipped.
    use_profile = profile_path is not None
    if use_profile:
        try:
            profile = profile_from_json(profile_path.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as exc:
            _simple_error(
                state, config, f"--profile {profile_path} did not parse as a Profile JSON: {exc}"
            )
            raise typer.Exit(code=EXIT_USAGE) from exc
    else:
        # H2 (reused from cli/plan.py): --no-profile cannot run the
        # pool-capacity pre-flight, so a cardinality_mode: unique column would
        # ship a plan whose runtime fails unpredictably. Hard-error here.
        unique_column_path = find_first_unique_column_path(raw)
        if unique_column_path is not None:
            _simple_error(
                state,
                config,
                "--no-profile is incompatible with cardinality_mode: unique "
                f"(offending column: {unique_column_path}). The "
                "basic_uniqueness_pre_flight check requires profile data; pass "
                "--profile <profile.json>, or remove the unique cardinality_mode.",
            )
            raise typer.Exit(code=EXIT_USAGE)
        profile = empty_profile_for_no_profile(raw, engine_version)

    # Compile: validate config, run plan-compile checks. no_profile=True in the
    # no-profile branch makes the ENGINE emit its own honest checks_skipped set
    # (basic_uniqueness_pre_flight, pool_capacity_pre_flight,
    # null_bearing_int_unsupported, when_string_output_on_numeric_unsupported) and
    # keep structural checks like fk_plan_ordering in checks_passed. We do not
    # hand-maintain a parallel skip list (it drifts from the engine's contract).
    try:
        plan = compile_plan(
            raw, profile, decoy_engine_version=engine_version, no_profile=not use_profile
        )
    except Exception as exc:
        _compile_error(state, config, exc)
        raise typer.Exit(code=EXIT_USAGE)

    # --output: also write the frozen plan artifact (absorbs the old `plan` command).
    if out is not None:
        out.write_text(render_plan_artifact(plan, out_format), encoding="utf-8")

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
        if out is not None:
            payload["artifact"] = {"path": str(out), "format": out_format}
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
                "is covered. Use decoy pre-scan to inspect source data."
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

    if out is not None:
        state.console.print(hint("Wrote plan artifact:"), code(str(out)))


def _simple_error(state, config: Path, msg: str) -> None:
    """Render a usage error in the compile command's envelope / console style."""
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "compile explain",
                "status": "error",
                "config": str(config),
                "error": msg,
            },
        )
    elif state.mode is not OutputMode.quiet:
        # markup=False: msg can carry user paths / bracketed text.
        state.err_console.print(error("error:"), msg, markup=False)


def _compile_error(state, config: Path, exc: Exception) -> None:
    """Render a compile error to the appropriate output stream."""
    # Import lazily to keep startup fast.
    err_code: str | None = None
    try:
        from decoy_engine.plan import PlanCompileError

        if isinstance(exc, PlanCompileError):
            # Shared with run/validate/preflight/plan: a spaCy-missing NER
            # failure must name decoy-cli's own [ner] extra, not the
            # engine's decoy-engine[ner] install line.
            from decoy.cli.extras import plan_compile_error_fields

            err_code, message = plan_compile_error_fields(exc)
            msg = f"[{err_code}] {exc.path or '<global>'}: {message}"
        else:
            msg = str(exc)
    except ImportError:
        msg = str(exc)

    from decoy.ui.output import OutputMode

    if state.mode is OutputMode.json:
        payload: dict = {
            "command": "compile explain",
            "status": "error",
            "error": msg,
        }
        if err_code is not None:
            payload["code"] = err_code
        emit_json(state, payload)
    elif state.mode is not OutputMode.quiet:
        # markup=False: msg starts with a bracketed error code and can carry
        # an install line such as `pip install decoy-cli[ner]`; Rich would
        # parse both as unknown style tags and drop them.
        state.err_console.print(error("error:"), msg, markup=False)
        state.err_console.print(
            " ", hint("hint:"), "run", code("decoy validate config <config>"), "for full validation."
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
        code("decoy pre-scan"),
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
