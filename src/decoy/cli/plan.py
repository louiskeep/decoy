"""`decoy plan` and `decoy replan` -- compile pipeline configs into a versioned plan artifact.

S1 spec §3 (decoy plan CLI subcommand) + §4 (decoy replan stub).

`decoy plan <config.yaml>`:
  Validate the pipeline config through `decoy_engine.config.PipelineConfig`,
  profile every source declared in `config.sources` via `profile_source`,
  compile the plan via `decoy_engine.plan.compile_plan`, print the result
  as YAML to stdout. Exit 0 on success; exit 1 with the typed error on
  stderr if validation fails or any of the five S1 plan-compile checks fires.

  Two flags control the profile phase:

    (default)                  Full automated path: validate config, profile
                               sources via the engine reader (CSV/Parquet),
                               compile the plan.
    --profile <profile.json>   Skip the profile phase; load a pre-computed
                               Profile from JSON instead. Useful for replay
                               or when source data isn't available locally.
    --no-profile               Skip the profile phase entirely; populate
                               plan_compile.checks_skipped with the
                               profile-dependent check names. Hard error
                               on configs with cardinality_mode: unique
                               (the pre-flight check cannot run without
                               profile data).

`decoy replan --from <manifest>`:
  Re-compile the plan from a job manifest. S1 stub: errors with a clear
  pointer to the plan-as-manifest slice (slice 7) on decoy-platform.
  Full behavior per S2 H3 lands once slice 7 ships on platform main.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
import yaml


# ----------------------------------------------------------------------
# decoy plan
# ----------------------------------------------------------------------


_PLAN_EPILOG = """\
Examples:

  decoy plan pipeline.yaml
    Full automated path: validate config, profile sources from the
    declared file paths, compile + emit the plan.

  decoy plan pipeline.yaml --no-profile
    Compile-check the config without loading source data. Faster; some
    profile-dependent checks are skipped (recorded in
    plan_compile.checks_skipped on the emitted plan). Hard error on
    configs with cardinality_mode: unique.

  decoy plan pipeline.yaml --profile profile.json
    Load a pre-computed Profile (JSON) instead of profiling the live
    source data. Useful for replay or when source data is not local.

  decoy plan pipeline.yaml --json
    Emit the plan as JSON (yaml.safe_load -> json.dumps round-trip).

  decoy plan pipeline.yaml --out plan.yaml
    Write the plan to a file instead of stdout.
"""


def plan(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the pipeline YAML config to compile.",
    ),
    profile_path: Path | None = typer.Option(
        None,
        "--profile",
        help="Path to a pre-computed Profile JSON file (from decoy_engine.profile).",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    no_profile: bool = typer.Option(
        False,
        "--no-profile",
        help="Skip the profile phase; profile-dependent checks land in plan_compile.checks_skipped.",
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit JSON instead of YAML on stdout. (yaml.safe_load -> json.dumps shape.)",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Write the plan to a file instead of stdout.",
    ),
) -> None:
    """Compile a pipeline config into a versioned plan artifact."""
    from decoy_engine import __version__ as engine_version
    from decoy_engine.config import PipelineConfig
    from decoy_engine.plan import PlanCompileError, compile_plan, plan_to_yaml
    from decoy_engine.profile import profile_from_json, profile_source
    from pydantic import ValidationError

    if no_profile and profile_path is not None:
        typer.echo(
            "ERROR: --no-profile and --profile are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    raw_yaml = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(raw_yaml, dict):
        typer.echo(
            f"ERROR: {config} does not parse to a YAML mapping at the top level.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Validate through the choke-point. Pydantic raises ValidationError with
    # a structured error tree; render the first error in a CLI-readable way.
    try:
        config_dict = PipelineConfig.model_validate(raw_yaml).model_dump()
    except ValidationError as exc:
        typer.echo(
            f"ERROR: pipeline-config validation failed for {config}:\n{exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    if no_profile:
        # H2 (Dennis slice 4-6 review): --no-profile cannot run the pool-capacity
        # pre-flight check, so configs with cardinality_mode: unique would skip
        # it silently and ship a plan whose runtime would fail unpredictably.
        # Hard-error here per S1 spec line 225.
        unique_column_path = _find_first_unique_column_path(config_dict)
        if unique_column_path is not None:
            typer.echo(
                f"ERROR: --no-profile is incompatible with cardinality_mode: unique.\n"
                f"       Offending column: {unique_column_path}\n"
                "       The basic_uniqueness_pre_flight check requires profile data\n"
                "       (distinct_count) to verify pool capacity. Without it, the\n"
                "       runtime failure mode is severe (pool exhaustion mid-job).\n"
                "       Drop --no-profile (default path now profiles automatically),\n"
                "       pass --profile <profile.json> for a pre-computed Profile,\n"
                "       or remove the unique cardinality_mode.",
                err=True,
            )
            raise typer.Exit(code=1)

        profile = _empty_profile_for_no_profile(config_dict, engine_version)
        # H1 (Dennis slice 4-6 review): both fk_plan_ordering AND
        # basic_uniqueness_pre_flight need profile data. Under --no-profile they
        # ran against an empty graph / empty profile and trivially passed; that
        # is a silent-fallback (correctness-contract §7 non-negotiable). Both
        # land in checks_skipped, stripped from checks_passed.
        skipped_checks = ("fk_plan_ordering", "basic_uniqueness_pre_flight")
        typer.echo(
            "WARNING: --no-profile skipped 2 profile-dependent checks "
            "(fk_plan_ordering, basic_uniqueness_pre_flight). Drop --no-profile "
            "for full validation.",
            err=True,
        )
    elif profile_path is not None:
        try:
            profile = profile_from_json(profile_path.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as exc:
            typer.echo(
                f"ERROR: --profile {profile_path} did not parse as a Profile JSON: {exc}",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        skipped_checks = ()
    else:
        # Default path: profile_source orchestration reads config["sources"]
        # and walks each declared file. Seed defaults to global_settings.seed
        # for cross-run reproducibility.
        job_seed = config_dict.get("global_settings", {}).get("seed")
        try:
            profile = profile_source(
                config_dict,
                seed=job_seed if isinstance(job_seed, int) else None,
            )
        except (FileNotFoundError, OSError) as exc:
            typer.echo(
                f"ERROR: profile_source could not read a declared source file: {exc}\n"
                "       Check the `sources.<table>.path` entries in the config.\n"
                "       Use --no-profile to compile-check without reading sources, or\n"
                "       --profile <profile.json> to load a pre-computed Profile.",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        skipped_checks = ()

    try:
        plan_obj = compile_plan(
            config_dict, profile, decoy_engine_version=engine_version
        )
    except PlanCompileError as exc:
        typer.echo(
            f"ERROR: [{exc.code}] {exc.path or '<global>'}: {exc.message}", err=True
        )
        raise typer.Exit(code=1) from exc

    # Layer the checks_skipped onto the result. The compile already
    # populated checks_passed; checks_skipped is the no-profile carveout.
    if skipped_checks:
        plan_obj = _attach_checks_skipped(plan_obj, skipped_checks)

    rendered = plan_to_yaml(plan_obj)
    if json_:
        # yaml.safe_load -> json.dumps for a stable JSON shape downstream
        # tooling can consume. L3 of the spec review (citation links) is
        # author-discretion; the shape rule lives here.
        rendered = (
            json.dumps(yaml.safe_load(rendered), indent=2, sort_keys=False) + "\n"
        )

    if out is not None:
        out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


PLAN_EPILOG = _PLAN_EPILOG


# ----------------------------------------------------------------------
# decoy replan
# ----------------------------------------------------------------------


_REPLAN_EPILOG = """\
S1 stub. `decoy replan --from <manifest.json>` re-compiles the plan from
a job manifest. Full behavior per S2 H3: re-profile (optionally with
--source override) + re-compile + stdout. Currently errors out with a
pointer to the plan-as-manifest slice (S1 slice 7) which has not
landed yet on decoy-platform.

After slice 7 lands, this command will:

1. Read the manifest JSON.
2. Extract the embedded config + profile_hash.
3. (Optional) Re-profile against --source if passed.
4. Re-compile the plan and write to stdout.
"""


def replan(
    from_manifest: Path = typer.Option(
        ...,
        "--from",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to a job manifest JSON to re-compile from.",
    ),
    source: Path | None = typer.Option(
        None,
        "--source",
        help="(Optional) Override source data path; re-profile against this and re-compile.",
    ),
) -> None:
    """Re-compile a plan from a job manifest. S1 stub; full flow lands by S9."""
    typer.echo(
        "ERROR: decoy replan is an S1 stub.\n"
        "       The plan-as-manifest slice (S1 slice 7) has not landed on\n"
        "       decoy-platform yet, so there is no manifest format to read\n"
        "       a plan back from. After slice 7 lands, this command will\n"
        "       re-compile + emit to stdout per the S2 H3 resolution.\n"
        f"       Manifest path was: {from_manifest}\n"
        f"       --source override was: {source}",
        err=True,
    )
    raise typer.Exit(code=1)


REPLAN_EPILOG = _REPLAN_EPILOG


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _empty_profile_for_no_profile(config_dict: dict, engine_version: str):
    """Build a minimal empty Profile so `compile_plan` can run without one.

    Used only by the --no-profile path. The resulting Profile has zero
    tables and zero relationships; the profile-dependent checks
    (basic_uniqueness_pre_flight) silently pass because they iterate
    over empty profile data, and the planner records them in
    checks_skipped via `_attach_checks_skipped`.

    This is intentionally not a public API; the proper path is
    profile_source orchestration in a future slice.
    """
    from datetime import datetime

    from decoy_engine.profile import Profile

    return Profile(
        schema_version=1,
        tables=(),
        relationships=(),
        profiled_at=datetime(2026, 5, 27, 0, 0, 0),
        decoy_engine_version=engine_version,
        profile_seed=None,
    )


def _attach_checks_skipped(plan_obj, skipped: tuple[str, ...]):
    """Return a new Plan with `plan_compile.checks_skipped` populated AND
    `checks_passed` stripped of the skipped names.

    Frozen dataclasses can't mutate in-place; this builds a new Plan
    that swaps the `plan_compile` field. Used by the --no-profile path
    to record which checks were skipped. The strip-from-passed half
    (H1 of the Dennis slice 4-6 review) keeps a single check name from
    appearing in both lists, which would mislead manifest consumers
    about what was actually verified.
    """
    from dataclasses import replace

    skipped_set = set(skipped)
    new_passed = tuple(
        c for c in plan_obj.plan_compile.checks_passed if c not in skipped_set
    )
    new_pc = replace(
        plan_obj.plan_compile, checks_passed=new_passed, checks_skipped=skipped
    )
    return replace(plan_obj, plan_compile=new_pc)


def _find_first_unique_column_path(config_dict: dict) -> str | None:
    """Return the dotted path of the first column with cardinality_mode: unique,
    or None if no such column exists.

    Used by the --no-profile guard (H2). Path format matches the planner's
    error-rendering convention: `tables.<name>.columns.<name>`.
    """
    tables = config_dict.get("tables", [])
    if not isinstance(tables, list):
        return None
    for table_entry in tables:
        if not isinstance(table_entry, dict):
            continue
        table_name = table_entry.get("name", "?")
        for col_entry in table_entry.get("columns", []) or []:
            if not isinstance(col_entry, dict):
                continue
            if col_entry.get("cardinality_mode") == "unique":
                col_name = col_entry.get("name", "?")
                return f"tables.{table_name}.columns.{col_name}"
    return None
