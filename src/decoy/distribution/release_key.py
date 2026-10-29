"""The pinned release public key the shipped CLI trusts for `decoy upgrade`.

Single source of truth: ``release_key.pub.pem`` beside this module (committed +
shipped in the wheel). The release-publish step fills it with the real release key's
public half and injects the SAME key into `install.sh`'s inline pin; until then the
committed file holds the ``__DECOY_RELEASE_PUBLIC_KEY__`` placeholder, and this loader
treats a build that still carries the placeholder as "no key pinned" -- a hard refusal
for `decoy upgrade`, never a silent accept. Tests and the local smoke inject a real
ephemeral key via ``DECOY_RELEASE_PUBKEY_FILE`` rather than committing one whose
private half would have to live somewhere.

That override is a DEV/TEST seam only: it is honored solely while the committed key is
still the placeholder (a dev checkout), and warns loudly when used. Once a release build
has injected the real key, an environment variable must never be able to replace the
trust anchor, so the override is ignored (with a warning). Same rule in `install.sh`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PLACEHOLDER_MARKER = "__DECOY_RELEASE_PUBLIC_KEY__"
_KEY_FILE = Path(__file__).resolve().parent / "release_key.pub.pem"


class NoPinnedKeyError(RuntimeError):
    """Raised when this build carries no real pinned release key (still the placeholder)
    and no ``DECOY_RELEASE_PUBKEY_FILE`` override is set."""


def _warn(msg: str) -> None:
    sys.stderr.write(f"decoy: WARNING: {msg}\n")


def pinned_public_pem() -> str:
    """Return the pinned release public key PEM.

    A filled-in committed key always wins. ``DECOY_RELEASE_PUBKEY_FILE`` is honored only
    while the committed key is still the placeholder (dev/test builds), with a loud
    warning; in a release build it is ignored with a warning. Raises NoPinnedKeyError if
    the build is a placeholder build and no override is set, so an unsigned-build upgrade
    refuses rather than trusting a placeholder."""
    text = _KEY_FILE.read_text(encoding="utf-8")
    override = os.environ.get("DECOY_RELEASE_PUBKEY_FILE")
    if PLACEHOLDER_MARKER not in text:
        if override:
            _warn(
                "DECOY_RELEASE_PUBKEY_FILE is set but IGNORED: this build pins its release "
                "key and an environment variable cannot replace the trust anchor."
            )
        return text
    if override:
        _warn(
            f"trusting the release key from DECOY_RELEASE_PUBKEY_FILE={override} instead of a "
            "pinned key. This is a dev/test build; never do this with a real install."
        )
        return Path(override).read_text(encoding="utf-8")
    raise NoPinnedKeyError(
        "this decoy build has no pinned release key (placeholder present); "
        "a release build injects it. Dev/test builds may set DECOY_RELEASE_PUBKEY_FILE."
    )
