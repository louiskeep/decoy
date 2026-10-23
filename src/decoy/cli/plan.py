"""Plan-artifact helpers folded into `decoy validate compile` (S2).

The top-level `plan` command was removed in the S2 CLI redesign; its
behavior (compile a pipeline config into a versioned plan artifact, with
--profile / --no-profile selection and an --output artifact writer) now lives
on `decoy validate compile` (`cli/compile_explain.py`).

This module keeps the reusable pieces that command imports, so the logic has
exactly one home:

  - `render_plan_artifact`        serialize a Plan to YAML or JSON.
  - `find_first_unique_column_path`  the H2 guard (--no-profile is incompatible
                                  with cardinality_mode: unique).
  - `empty_profile_for_no_profile`   the empty sentinel Profile for no-profile
                                  compiles.

The engine emits its own honest checks_skipped set when `compile_plan` is called
with `no_profile=True` (structural checks like fk_plan_ordering stay in
checks_passed; the genuinely profile-dependent checks are skipped), so this
module does NOT hand-maintain a parallel skip list.
"""

from __future__ import annotations

import json

import yaml


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

    Used only by the --no-profile path, paired with `compile_plan(...,
    no_profile=True)` so the engine records the profile-dependent checks as
    skipped (rather than letting them pass vacuously against empty data).

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
