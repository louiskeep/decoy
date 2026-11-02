"""The one mask-secret path the CLI surfaces share.

`--mask-secret REF` (or `mask_secret=`) fills the same `global_settings.mask_secret_ref` slot the
YAML can set; both set is a usage error, keyed on presence, so one secret source is chosen
explicitly. A command admits the secret once through the engine's public `admit_mask_key` inside
an `AdmissionScope` (closed on every exit) and hands that one provider to every engine entry it
calls, so a run and its vault see one read and one key. With a provider the engine does not read
the ref again (`secret_providers.admit_mask_key`: "a programmatic key_provider wins").

No implicit source: nothing here reads an environment variable, a default file or generates key
bytes; the ref names the secret and the engine resolves it. Errors never echo the ref value.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# `vault://` parses in the engine; the CLI registers no provider for it, so the engine refuses
# it with `secret_provider_unknown` instead of the CLI calling it malformed.
_REF_PREFIXES = ("env:", "file:", "vault://")

BOTH_SET = (
    "--mask-secret was passed but the YAML already sets "
    "global_settings.mask_secret_ref. Set the masking "
    "secret in exactly one place: drop --mask-secret, or "
    "remove mask_secret_ref from the config."
)
INVALID = (
    "Invalid mask secret: expected an 'env:NAME' or "
    "'file:/PATH' reference to a >=32-byte secret (from "
    "--mask-secret or global_settings.mask_secret_ref). It "
    "is a REFERENCE, never the raw secret. "
    "See: decoy explain keys."
)
FLAG_HELP = (
    "Reference to the mask secret the run used: 'env:NAME' or 'file:/PATH' (a >=32-byte "
    "secret; an owner-only file, never the raw value). Sets global_settings.mask_secret_ref "
    "for this command; an error if the YAML also sets it. See: decoy explain keys."
)


class MaskSecretFlagError(Exception):
    """A usage error from `apply_mask_secret` (exits EXIT_USAGE); its text holds no value."""


def is_valid_mask_secret_ref(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_REF_PREFIXES)


def apply_mask_secret(
    config_dict: dict,
    flag: str | None,
    *,
    error: type[Exception] = MaskSecretFlagError,
    both_set: str = BOTH_SET,
    invalid: str = INVALID,
) -> None:
    """Inject `flag` into the config, then check the effective ref's shape.

    Presence, not truthiness: a YAML `mask_secret_ref: ""` is a configured slot the flag must
    not override, and an empty ref is refused rather than read as "no secret". A non-mapping
    `global_settings` (unvalidated YAML on `unmask` / `report vault`) is left to the engine's
    own refusal; there is no slot to put a flag into."""
    settings = config_dict.get("global_settings")
    if settings is not None and not isinstance(settings, dict):
        if flag is not None:
            raise error(invalid)
        return
    if flag is not None:
        if (settings or {}).get("mask_secret_ref") is not None:
            raise error(both_set)
        if settings is None:
            settings = config_dict["global_settings"] = {}
        settings["mask_secret_ref"] = flag
    ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
    if ref is not None and not is_valid_mask_secret_ref(ref):
        raise error(invalid)


@contextmanager
def admitted_key_provider(config_dict: dict) -> Iterator[Any]:
    """The command's one admitted provider; None when nothing is keyed and no ref is set."""
    from decoy_engine.secret_providers import AdmissionScope, admit_mask_key

    with AdmissionScope() as scope:
        yield scope.adopt(admit_mask_key(config_dict)).key_provider
