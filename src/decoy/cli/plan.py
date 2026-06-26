"""`decoy plan` -- compile pipeline configs into a versioned plan artifact.

S1 spec §3 (decoy plan CLI subcommand).

`decoy plan <config.yaml>`:
  Compile the pipeline config into a Plan (per `decoy_engine.plan.compile_plan`)
  and print as YAML to stdout. Exit 0 on success; exit 1 with the typed error
  on stderr if any of the five S1 plan-compile checks fires.

Scope cut (honest about what's not yet implemented):

  The profile_source orchestration slice (which would let `decoy plan
  config.yaml` infer the profile by walking source files) is deferred
  pending the V2 pipeline-config shape decision. Until it lands, this
  CLI requires the caller to pass one of:

    --profile <profile.json>   load a pre-computed Profile from JSON
    --no-profile               skip the profile entirely; populate
                               plan_compile.checks_skipped with the
                               profile-dependent check names

  Bare `decoy plan config.yaml` (no profile flag) exits 1 with a pointer
  to this gap so the user knows what's missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
import yaml

from decoy.cli.exit_codes import EXIT_USAGE


# ----------------------------------------------------------------------
# decoy plan
# ----------------------------------------------------------------------


_PLAN_EPILOG = """\
Examples:

  decoy plan pipeline.yaml --no-profile
    Compile-check the config without loading source data. Faster; some
    profile-dependent checks are skipped (recorded in
    plan_compile.checks_skipped on the emitted plan).

  decoy plan pipeline.yaml --profile profile.json
    Load a pre-computed Profile (JSON) and run all five S1 plan-compile
    checks.

  decoy plan pipeline.yaml --no-profile --json
    Emit the plan as JSON (yaml.safe_load -> json.dumps round-trip).

  decoy plan pipeline.yaml --no-profile --out plan.yaml
    Write the plan to a file instead of stdout.

The fully-automated path (`decoy plan pipeline.yaml` with no profile
flag) lands once the profile_source orchestration slice ships.

See also: decoy validate, decoy run.
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
    from decoy_engine.plan import PlanCompileError, compile_plan, plan_to_yaml
    from decoy_engine.profile import profile_from_json

    if not no_profile and profile_path is None:
        typer.echo(
            "ERROR: decoy plan requires either --no-profile or --profile <path>.\n"
            "       The fully-automated profile_source orchestration slice has not\n"
            "       landed yet (deferred pending the V2 pipeline-config shape\n"
            "       decision). Use --no-profile for a partial compile (profile-\n"
            "       dependent checks land in plan_compile.checks_skipped) or\n"
            "       --profile <profile.json> to load a pre-computed Profile.",
            err=True,
        )
        raise typer.Exit(code=EXIT_USAGE)

    if no_profile and profile_path is not None:
        typer.echo(
            "ERROR: --no-profile and --profile are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=EXIT_USAGE)

    config_dict = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(config_dict, dict):
        typer.echo(
            f"ERROR: {config} does not parse to a YAML mapping at the top level.",
            err=True,
        )
        raise typer.Exit(code=EXIT_USAGE)

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
                "       Use --profile <profile.json> to load a pre-computed Profile,\n"
                "       or remove the unique cardinality_mode.",
                err=True,
            )
            raise typer.Exit(code=EXIT_USAGE)

        profile = _empty_profile_for_no_profile(config_dict, engine_version)
        # H1 (Dennis slice 4-6 review): both fk_plan_ordering AND
        # basic_uniqueness_pre_flight need profile data. Under --no-profile they
        # ran against an empty graph / empty profile and trivially passed; that
        # is a silent-fallback (correctness-contract §7 non-negotiable). Both
        # land in checks_skipped, stripped from checks_passed.
        skipped_checks = ("fk_plan_ordering", "basic_uniqueness_pre_flight")
        typer.echo(
            "WARNING: --no-profile skipped 2 profile-dependent checks "
            "(fk_plan_ordering, basic_uniqueness_pre_flight). Pass without "
            "--no-profile for full validation.",
            err=True,
        )
    else:
        if profile_path is None:
            # CLI QA fix (2026-06-02, F10): bare `assert` is stripped by
            # `python -O` / PYTHONOPTIMIZE=1, leaving the next line to
            # AttributeError on NoneType.read_text. The mutual-exclusion
            # check above already prevents this branch when profile_path
            # is None, so the raise here is documentation of the invariant.
            raise RuntimeError(
                "profile_path is None despite the mutual-exclusion check; "
                "this is a bug in plan.py."
            )
        try:
            profile = profile_from_json(profile_path.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as exc:
            typer.echo(
                f"ERROR: --profile {profile_path} did not parse as a Profile JSON: {exc}",
                err=True,
            )
            raise typer.Exit(code=EXIT_USAGE) from exc
        skipped_checks = ()

    try:
        plan_obj = compile_plan(
            config_dict, profile, decoy_engine_version=engine_version
        )
    except PlanCompileError as exc:
        typer.echo(
            f"ERROR: [{exc.code}] {exc.path or '<global>'}: {exc.message}", err=True
        )
        raise typer.Exit(code=EXIT_USAGE) from exc

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
# Internals
# ----------------------------------------------------------------------


# CLI QA fix (2026-06-02, F3): the --no-profile path needs a deterministic
# profiled_at timestamp (so re-running `decoy plan --no-profile` produces
# byte-identical plans). Pre-fix the value was the slice implementation date
# (2026-05-27), which lied about when the profile was taken and aged badly.
# The POSIX epoch is the conventional "no real profile" sentinel; downstream
# consumers that inspect profiled_at can detect "no profile available" by
# comparing to this constant.
_NO_PROFILE_SENTINEL_DATE = None  # set inside _empty_profile_for_no_profile to avoid circular import


def _empty_profile_for_no_profile(config_dict: dict, engine_version: str):
    """Build a minimal empty Profile so `compile_plan` can run without one.

    Used only by the --no-profile path. The resulting Profile has zero
    tables and zero relationships; the profile-dependent checks
    (basic_uniqueness_pre_flight) silently pass because they iterate
    over empty profile data, and the planner records them in
    checks_skipped via `_attach_checks_skipped`.

    The `profiled_at` field carries the POSIX epoch (1970-01-01) as a
    "no real profile available" sentinel; downstream consumers should
    treat this value as "do not trust profile-derived facts" rather
    than "profile was taken on this date" (CLI QA fix 2026-06-02 F3).
    """
    from datetime import datetime

    from decoy_engine.profile import Profile

    return Profile(
        schema_version=1,
        tables=(),
        relationships=(),
        profiled_at=datetime(1970, 1, 1, 0, 0, 0),
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
