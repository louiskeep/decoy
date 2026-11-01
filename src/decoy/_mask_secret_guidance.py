"""One fixed remedy text per surface for the engine's keyed-secret refusal.

The engine refuses a keyed strategy with no admitted mask secret
(`keyed_strategy_requires_secret`) and words the fix for its own Python API
(`run(key_provider=...)`). A CLI or `decoy.mask()` user cannot act on that, so each surface
replaces it with fixed text naming its own remedy. Fixed text keeps the message closed-set:
nothing from the pipeline, the environment or the exception can ride along.
"""

from __future__ import annotations

CODE = "keyed_strategy_requires_secret"

_FORMS = "an env:NAME or file:/PATH reference to a secret of at least 32 bytes (hex or base64)"
_LOCAL = "For local development: export DECOY_MASK_SECRET=$(openssl rand -hex 32)"

RUN = (
    f"{CODE}: this pipeline uses a keyed masking strategy and no mask secret was supplied. "
    f"Pass --mask-secret with {_FORMS}, or set global_settings.mask_secret_ref in the "
    f"pipeline YAML (one place, not both). {_LOCAL}, then add "
    "--mask-secret env:DECOY_MASK_SECRET. See `decoy explain keys`."
)

UNMASK = (
    f"{CODE}: reversing keyed columns needs the mask secret the run used. Set "
    f"global_settings.mask_secret_ref in the pipeline YAML to {_FORMS}, the same secret "
    "the mask run used. See `decoy explain keys`."
)

API = (
    f"{CODE}: this pipeline uses a keyed masking strategy and no mask secret was supplied. "
    f"Pass mask_secret= with {_FORMS}, or set global_settings.mask_secret_ref in the "
    "config (one place, not both). See `decoy explain keys`."
)

INIT_HINT = (
    "this pipeline uses keyed strategies, so `decoy run` needs a mask secret: "
    "--mask-secret env:DECOY_MASK_SECRET (or file:/PATH), or "
    "global_settings.mask_secret_ref. See `decoy explain keys`."
)

# The comment block a keyed scaffold or bundled template carries.
YAML_COMMENT = (
    "# Keyed: a mask secret is REQUIRED. Without one `decoy run` refuses with\n"
    f"# {CODE} (there is no seed fallback). Supply a >=32-byte secret:\n"
    "#   export DECOY_MASK_SECRET=$(openssl rand -hex 32)\n"
    "#   decoy run pipeline.yaml --mask-secret env:DECOY_MASK_SECRET\n"
    '# or set global_settings.mask_secret_ref: "env:DECOY_MASK_SECRET" (or "file:/PATH").\n'
    "# See `decoy explain keys`.\n"
)


def is_keyed_secret_refusal(exc: BaseException) -> bool:
    """The engine's keyed-secret refusal, matched by its registered code."""
    try:
        from decoy_engine.keyprovider import MaskSecretError
    except ImportError:
        return False
    return isinstance(exc, MaskSecretError) and getattr(exc, "code", None) == CODE


def config_is_keyed(config: dict) -> bool:
    """The engine's own pre-read classifier: does this config need a mask secret?"""
    from decoy_engine.secret_providers import secret_requirements_for_config

    return bool(secret_requirements_for_config(config))
