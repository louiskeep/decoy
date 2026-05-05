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

from functools import lru_cache


# Transform IDs are static -- one entry per transform shipped by the engine.
# Keep this list in sync with `decoy_engine.transforms.factory` if a new one ships.
TRANSFORM_IDS: tuple[str, ...] = (
    "faker",
    "hash",
    "redact",
    "map",
    "shuffle",
    "passthrough",
    "date_shift",
    "formula",
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
    try:
        from faker import Faker

        from decoy_engine.internal.helpers import get_faker_providers

        return tuple(sorted(get_faker_providers(Faker()).keys()))
    except Exception:
        return ()


def faker_provider_ids() -> list[str]:
    """Tab-complete `--faker-type` values."""
    return list(_faker_provider_ids_cached())
