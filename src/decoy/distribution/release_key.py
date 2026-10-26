"""The pinned release public key the shipped CLI trusts for `decoy upgrade`.

Single source of truth: ``release_key.pub.pem`` beside this module (committed +
shipped in the wheel). The release-publish step fills it with the real release key's
public half and injects the SAME key into `install.sh`'s inline pin; until then the
committed file holds the ``__DECOY_RELEASE_PUBLIC_KEY__`` placeholder, and this loader
treats a build that still carries the placeholder as "no key pinned" -- a hard refusal
for `decoy upgrade`, never a silent accept. Tests and the local smoke inject a real
ephemeral key via ``DECOY_RELEASE_PUBKEY_FILE`` rather than committing one whose
private half would have to live somewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

PLACEHOLDER_MARKER = "__DECOY_RELEASE_PUBLIC_KEY__"
_KEY_FILE = Path(__file__).resolve().parent / "release_key.pub.pem"


class NoPinnedKeyError(RuntimeError):
    """Raised when this build carries no real pinned release key (still the placeholder)
    and no ``DECOY_RELEASE_PUBKEY_FILE`` override is set."""


def pinned_public_pem() -> str:
    """Return the pinned release public key PEM.

    ``DECOY_RELEASE_PUBKEY_FILE`` overrides the committed file (used by tests + the
    smoke). Raises NoPinnedKeyError if neither the override nor a filled-in committed
    key is present, so an unsigned-build upgrade refuses rather than trusting a
    placeholder."""
    override = os.environ.get("DECOY_RELEASE_PUBKEY_FILE")
    if override:
        return Path(override).read_text(encoding="utf-8")
    text = _KEY_FILE.read_text(encoding="utf-8")
    if PLACEHOLDER_MARKER in text:
        raise NoPinnedKeyError(
            "this decoy build has no pinned release key (placeholder present); "
            "a release build injects it. Set DECOY_RELEASE_PUBKEY_FILE to verify "
            "against a specific key."
        )
    return text
