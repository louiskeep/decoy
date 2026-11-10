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
    f"{CODE}: reversing keyed columns needs the mask secret the run used. Pass "
    f"--mask-secret with {_FORMS}, or set global_settings.mask_secret_ref in the pipeline "
    "YAML (one place, not both): the same secret the mask run used. See `decoy explain keys`."
)

REPORT_VAULT = (
    f"{CODE}: a vault is encrypted under the mask secret the run used, and none was "
    f"supplied. Pass --mask-secret with {_FORMS}, or set global_settings.mask_secret_ref in "
    "the pipeline YAML (one place, not both): the same secret the `decoy run --vault` call "
    "used. See `decoy explain keys`."
)

TOKENIZE = (
    f"{CODE}: tokenize is keyed and no mask secret was supplied. Pass --mask-secret with "
    f"{_FORMS}, or set global_settings.mask_secret_ref in the pipeline YAML (one place, not "
    f"both). {_LOCAL}, then add --mask-secret env:DECOY_MASK_SECRET. See `decoy explain keys`."
)

API = (
    f"{CODE}: this pipeline uses a keyed masking strategy and no mask secret was supplied. "
    f"Pass mask_secret= with {_FORMS}, or set global_settings.mask_secret_ref in the "
    "config (one place, not both). See `decoy explain keys`."
)

# The installed engine predates keyed masking (no `keyprovider` module), so it would ignore a mask
# secret and emit unkeyed output. One fixed text per surface, each naming its own remedy.
_OLD_ENGINE_HEAD = (
    "the installed decoy-engine is too old to honor it: it has no keyed-masking support, "
    "so it would silently emit "
)
_OLD_ENGINE_TAIL = ". Upgrade decoy-engine to 0.4.0 or later."

OLD_ENGINE_RUN = (
    "a mask secret is configured (mask_secret_ref or --mask-secret) but "
    + _OLD_ENGINE_HEAD
    + "UNKEYED output"
    + _OLD_ENGINE_TAIL
    + " See `decoy explain keys`."
)

OLD_ENGINE_TOKENIZE = (
    "a mask secret is configured but "
    + _OLD_ENGINE_HEAD
    + "UNKEYED (forgeable) tokens"
    + _OLD_ENGINE_TAIL
)

OLD_ENGINE_API = (
    "a mask secret is configured (mask_secret= or mask_secret_ref) but "
    + _OLD_ENGINE_HEAD
    + "UNKEYED output"
    + _OLD_ENGINE_TAIL
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


# Every other secret refusal: fixed text by registered code. The engine's own message is never
# printed, so nothing a provider, a ref or a path put in it can reach the terminal or --json.
SECRET_REMEDIES = {
    "weak_mask_secret": (
        "weak_mask_secret: the mask secret is shorter than 32 bytes. Use a secret of at least "
        f"32 bytes (hex or base64). {_LOCAL}. See `decoy explain keys`."
    ),
    "missing_mask_secret": (
        "missing_mask_secret: the referenced mask secret is not set (an unset env: variable or "
        "a missing or empty file: path). Check the reference. See `decoy explain keys`."
    ),
    "bad_secret_ref": (
        f"bad_secret_ref: the mask secret reference is malformed; use {_FORMS}. "
        "See `decoy explain keys`."
    ),
    "secret_provider_unknown": (
        "secret_provider_unknown: the reference names a secret provider this CLI does not "
        "register (it reads env: and file: references). See `decoy explain keys`."
    ),
    "secret_file_permissions_unsafe": (
        "secret_file_permissions_unsafe: the mask secret file must be owner-only (no group or "
        "other access): chmod 600 it, or make it with umask 077. See `decoy explain keys`."
    ),
}
_SECRET_DEFAULT = "the mask secret could not be admitted. See `decoy explain keys`."
_CODE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


def secret_error_text(exc: BaseException, keyed_remedy: str) -> str:
    """Constant text for a `MaskSecretError`, chosen by its registered code; never `str(exc)`."""
    code = getattr(exc, "code", None)
    # Registered codes are a `str` subclass; take the plain value and accept only code shapes.
    code = str.__str__(code) if isinstance(code, str) else ""
    if not code or not set(code) <= _CODE_CHARS or len(code) > 64:
        code = "mask_secret_error"
    if code == CODE:
        return keyed_remedy
    return SECRET_REMEDIES.get(code, f"{code}: {_SECRET_DEFAULT}")


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
