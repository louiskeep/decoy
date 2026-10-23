"""Plan-artifact helpers folded into `decoy validate compile` (S2).

The top-level `plan` command was removed in the S2 CLI redesign; its
behavior (compile a pipeline config into a versioned plan artifact, with
--profile / --no-profile selection and an --output artifact writer) now lives
on `decoy validate compile` (`cli/compile_explain.py`).

This module keeps the reusable pieces that command imports, so the logic has
exactly one home:

  - `render_plan_artifact`        serialize a Plan to YAML or JSON.
  - `attach_checks_skipped`       the H1 honesty guard (a check is never in
                                  both checks_passed and checks_skipped).
  - `find_first_unique_column_path`  the H2 guard (--no-profile is incompatible
                                  with cardinality_mode: unique).
  - `empty_profile_for_no_profile`   the empty sentinel Profile for no-profile
                                  compiles.
  - `NO_PROFILE_SKIPPED_CHECKS`   the profile-dependent checks skipped under
                                  --no-profile.
"""

from __future__ import annotations

import json

import yaml

# The two profile-dependent plan-compile checks skipped under --no-profile.
# H1 (Dennis slice 4-6 review): both fk_plan_ordering AND
# basic_uniqueness_pre_flight need profile data; recorded in checks_skipped
# and stripped from checks_passed by `attach_checks_skipped`.
NO_PROFILE_SKIPPED_CHECKS: tuple[str, ...] = ("fk_plan_ordering", "basic_uniqueness_pre_flight")


def render_plan_artifact(plan_obj, fmt: str = "yaml") -> str:
    """Serialize a compiled Plan to the frozen on-disk artifact string.

    `fmt="yaml"` is the canonical manifest shape (`plan_to_yaml`, the engine's
    determinism-contracted serializer). `fmt="json"` runs the same
    yaml.safe_load -> json.dumps round-trip the old `plan --json` used so
    downstream tooling that prefers JSON gets a stable shape. Both forms are
    engine-readable (`decoy_engine.plan.plan_from_yaml` round-trips the YAML;
    the JSON is the same document).
    """
    from decoy_engine.plan import plan_to_yaml

    rendered = plan_to_yaml(plan_obj)
    if fmt == "json":
        rendered = json.dumps(yaml.safe_load(rendered), indent=2, sort_keys=False) + "\n"
    return rendered


def empty_profile_for_no_profile(config_dict: dict, engine_version: str):
    """Build a minimal empty Profile so `compile_plan` can run without one.

    Used only by the --no-profile path. The resulting Profile has zero
    tables and zero relationships; the profile-dependent checks
    (basic_uniqueness_pre_flight) silently pass because they iterate
    over empty profile data, and the caller records them in
    checks_skipped via `attach_checks_skipped`.

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


def attach_checks_skipped(plan_obj, skipped: tuple[str, ...]):
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
    new_passed = tuple(c for c in plan_obj.plan_compile.checks_passed if c not in skipped_set)
    new_pc = replace(plan_obj.plan_compile, checks_passed=new_passed, checks_skipped=skipped)
    return replace(plan_obj, plan_compile=new_pc)


def find_first_unique_column_path(config_dict: dict) -> str | None:
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
