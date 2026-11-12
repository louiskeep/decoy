"""Tab-completion sources for CLI flag values.

See CLI_UX_GUIDE.md section 11. Each function below produces a list of
strings suitable as a Typer `autocompletion=` argument:

    @app.command()
    def apply(
        disguise: str = typer.Option(..., "--apply", autocompletion=disguise_ids),
    ): ...

The functions are written to be cheap (every Tab press calls them) and
defensive -- they swallow import failures so a broken engine install
doesn't break the shell. Prefer narrow lists over deep introspection.
"""

from __future__ import annotations

import os
from functools import lru_cache

import typer

# Transform IDs are static -- one entry per mask strategy shipped by the engine.
# Keep this list in sync with `decoy_engine.execution._strategies.SCALAR_HANDLERS`
# if a new one ships. (composite/orphan are generation/FK handlers, not column
# `strategy:` values, so they are intentionally absent.)
TRANSFORM_IDS: tuple[str, ...] = (
    "faker",
    "hash",
    "redact",
    "categorical",
    "shuffle",
    "passthrough",
    "date_shift",
    "formula",
    "bucketize",
    "fpe",
    "text_redact",
    "truncate",
    "nested",
)


def transform_ids() -> list[str]:
    """Tab-complete `--mask` values."""
    return list(TRANSFORM_IDS)


@lru_cache(maxsize=1)
def _disguise_ids_cached() -> tuple[str, ...]:
    try:
        from decoy_engine.disguises import load_disguises

        return tuple(d.id for d in load_disguises())
    except Exception:
        return ()


def disguise_ids() -> list[str]:
    """Tab-complete `--apply` values: every Disguise the engine ships."""
    return list(_disguise_ids_cached())


@lru_cache(maxsize=1)
def _faker_provider_ids_cached() -> tuple[str, ...]:
    """The engine's public provider list; the old `internal.faker_setup` import drifted
    once (CLI.3) and the blanket except turned that into a silent empty completer."""
    try:
        from decoy_engine import list_generate_faker_providers

        return tuple(list_generate_faker_providers())
    except Exception:
        return ()


def faker_provider_ids() -> list[str]:
    """Tab-complete `--faker-type` values."""
    return list(_faker_provider_ids_cached())


# Static set: the modes `decoy run --mode` accepts. Mirrors cli.run.Mode.
# CLI.1 (2026-06-02): "convert" and "graph" were V1-only modes removed
# under storm-reframe-C / S22-CL-V1GRAPHRUNNER. The V2 PipelineConfig
# choke point accepts only mask + generate.
RUN_MODES: tuple[str, ...] = ("mask", "generate")


def run_modes() -> list[str]:
    """Tab-complete `decoy run --mode` values."""
    return list(RUN_MODES)


def explain_topics() -> list[str]:
    """Tab-complete `decoy explain <topic>` values."""
    # Imported lazily so a broken explain module doesn't break the shell.
    try:
        from decoy.cli.explain import topic_names

        return topic_names()
    except Exception:
        return []


def template_names() -> list[str]:
    """Tab-complete `decoy show template <name>` values."""
    try:
        from decoy.templates import template_names as _names

        return _names()
    except Exception:
        return []


def init_presets() -> list[str]:
    """Tab-complete `decoy init --preset` values. Mirrors templates."""
    return template_names()


def _yaml_paths(incomplete: str) -> list[str]:
    """Folders and YAML files at the typed location, so a path still completes."""
    head, sep, stem = incomplete.rpartition("/")
    try:
        entries = sorted(os.scandir(head or ("/" if sep else ".")), key=lambda e: e.name)
        found = []
        for entry in entries:
            if not entry.name.startswith(stem) or (entry.name[0] == "." and stem[:1] != "."):
                continue
            if entry.is_dir():
                found.append(f"{head}{sep}{entry.name}/")
            elif entry.name.lower().endswith((".yaml", ".yml")):
                found.append(f"{head}{sep}{entry.name}")
    except OSError:
        return []
    return found


def pipeline_names(ctx: typer.Context, incomplete: str) -> list[str]:
    """Tab-complete a pipeline parameter: project pipeline names, then folders and YAML files.

    The project is `--project` already on the line, else `DECOY_PROJECT`, else the walk from the
    current folder. Typer 0.26 turns every `autocompletion` entry into a plain item (its
    `compat_autocompletion` rejects `CompletionItem`), so the shell's own file completion is not
    available here and the path candidates come from `_yaml_paths`. A failed project lookup
    leaves the paths alone: it never breaks Tab.
    """
    names: list[str] = []
    try:
        from decoy.cli.io import explicit_project, find_project, list_pipelines

        project = find_project(None, explicit_project(ctx))
        if not project.implicit:
            names = [e.name for e in list_pipelines(project) if e.name.startswith(incomplete)]
    except Exception:
        names = []
    return names + _yaml_paths(incomplete)
