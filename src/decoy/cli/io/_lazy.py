"""Lazy source candidates for a plain `decoy run` (RUN-STREAM C1l).

The engine owns which local source has a lazy backend (`build_lazy_source`) and which candidate
may stay lazy (the resident-fallback pre-pass behind `run_pipeline(resident_fallback=True)`).
This module only names the candidates: every local file source of a mask table that the loader
would otherwise read whole. It opens no data row and holds no format or reader-class check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from decoy import _native_gate
from decoy.cli._sources import resolved_source_config


def lazy_sources(config_dict: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """`{table: LazySource}` for each materialized mask-table source the engine can read lazily.

    A source with no lazy backend (the engine answers `None`), a generate table and a source with
    no `path` are left out, so the caller keeps today's resident read for them. Descriptors are
    resolved against `base_dir` first, so a relative path reads from the config's folder.
    """
    from decoy_engine.config import classify_table_kinds
    from decoy_engine.profile import build_lazy_source

    sources = config_dict.get("sources")
    if not isinstance(sources, dict) or not sources:
        return {}
    kinds = classify_table_kinds(config_dict)
    resolved = resolved_source_config(config_dict, base_dir)["sources"]
    found: dict[str, Any] = {}
    for table, descriptor in resolved.items():
        if kinds.get(table) != "mask" or not _native_gate.source_is_materialized(descriptor):
            continue
        candidate = build_lazy_source(table, descriptor)
        if candidate is not None:
            found[table] = candidate
    return found
