"""Detached Ed25519 verification over canonical-JSON bytes (verify side only).

Established methodology, ported pattern: this is a faithful port of the platform's
hardened signed-envelope primitive, `decoy-platform/api/crypto/signed_envelope.py`
(the "confident-dirac" output-passport / air-gapped-bundle-manifest signer), reused
here because the CLI repo cannot import the private platform package. Ed25519 via
`cryptography`; no hand-rolled scheme. The verify rules are copied verbatim from the
source so a signature this module accepts is one the platform primitive accepts and
vice versa:

- ``expected_public_pem`` is REQUIRED -- there is no "trust the key embedded in the
  blob" mode (that would let anyone mint an envelope under their own key).
- the pin compares RAW key bytes, so two PEM encodings of the same key (line
  wrapping / CRLF / trailing space) still match.
- ``schema_version`` and ``alg`` are enforced, so an envelope of another type or
  algorithm is rejected rather than silently accepted.

The canonical signed-bytes form is identical to the source primitive AND identical
to the bytes `openssl pkeyutl -verify -rawin` checks, so the three verifiers (this
module in `decoy upgrade`, `openssl` in `install.sh`, and the platform primitive on
the build host) agree on exactly what was signed:

``json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))``

NOTE (carried from the source): this is not yet RFC 8785 JCS (number formatting is
Python's); the shell verifier sidesteps the issue by signing the on-disk file bytes
directly (see `packaging_tools/sign_release.py`), so a non-Python verifier never has to
reproduce this encoding.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNATURE_ALG = "ed25519"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """The single definition of 'what gets signed'. Signer and verifier MUST agree on
    these exact bytes, so this is the one place the encoding lives."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _raw_public_bytes_from_pem(public_pem: str) -> bytes:
    """Load an Ed25519 public key from PEM and return its 32 raw bytes.

    Raises ValueError if the PEM is not a loadable Ed25519 public key."""
    pub = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("not an Ed25519 public key")
    return pub.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


def verify_detached(payload_bytes: bytes, signature_b64: str, *, expected_public_pem: str) -> bool:
    """Verify a base64 detached Ed25519 signature over exact ``payload_bytes`` against a
    PINNED public key. This is the byte-for-byte equivalent of what `openssl pkeyutl
    -verify -pubin -rawin -sigfile <raw-sig>` does in the install script, so a bundle
    the shell installer accepts is one `decoy upgrade` accepts. Returns False on any
    malformed, mismatched, or failing input (never raises)."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(_raw_public_bytes_from_pem(expected_public_pem))
        signature = base64.b64decode(signature_b64, validate=True)
        pub.verify(signature, payload_bytes)
        return True
    except (ValueError, InvalidSignature, TypeError):
        return False


def verify_envelope(
    signed: dict[str, Any], *, expected_public_pem: str, schema_version: str
) -> bool:
    """Verify a signed envelope {alg, payload, signature(b64), public_key(PEM)} against a
    PINNED key and an expected schema_version. Returns False on any malformed,
    mismatched, or failing input (never raises)."""
    try:
        if signed.get("alg") != SIGNATURE_ALG:
            return False
        payload = signed["payload"]
        if not isinstance(payload, dict) or payload.get("schema_version") != schema_version:
            return False
        embedded_raw = _raw_public_bytes_from_pem(signed["public_key"])
        if embedded_raw != _raw_public_bytes_from_pem(expected_public_pem):
            return False
        pub = Ed25519PublicKey.from_public_bytes(embedded_raw)
        signature = base64.b64decode(signed["signature"], validate=True)
        pub.verify(signature, canonical_bytes(payload))
        return True
    except (KeyError, ValueError, InvalidSignature, TypeError, AttributeError, RecursionError):
        # RecursionError: a hostile nesting depth is bad input, not a crash; the
        # verifier's contract is "never raises, returns False on any bad input".
        return False
