"""The Decoy-hosted version document: the self-hosted update channel's source of truth.

This is the external contract (api-and-compatibility: version it, keep
omitted-field behaviour defined so an older CLI reading a newer document degrades
cleanly) that `install.sh`, `decoy upgrade`, and the startup notice all read. It is
served as a static file, canonical-JSON on the wire, with a detached Ed25519
signature sidecar (`version.json.sig`) so the shell installer verifies it with
`openssl` and `decoy upgrade` verifies the identical bytes with `decoy.distribution.signing`.

On-disk/on-the-wire form is exactly ``signing.canonical_bytes(payload)``; the signer
signs those bytes, so there is no re-serialization step for any verifier to get wrong.

Payload shape (v1):

    {
      "schema_version": "cli-version-document/v1",
      "latest":        "0.1.0",          # newest non-yanked release
      "min_supported": "0.1.0",          # floor below which the CLI should hard-upgrade
      "yanked":        ["0.0.9"],         # versions pulled post-release
      "message":       "",                # optional advisory shown on upgrade/notice
      "generated":     "2026-10-26T00:00:00Z",
      "serial":        42,                # monotonic; verifiers refuse a lower one
      "expires":       "2026-11-25T00:00:00Z",  # UTC; verifiers refuse after this
      "artifacts": {                      # one entry per supported target
        "linux-x86_64": {"url": "...", "sha256": "<hex>", "sig": "<url>"},
        ...
      }
    }

Freshness (TUF-style, https://theupdateframework.github.io/specification/latest/ -- the
timestamp/snapshot "version" + "expires" roles): ``serial`` is a monotonic integer the
signer bumps on every publish and ``expires`` is a signed wall-clock deadline. A signature
alone proves only WHO signed a document, not that it is CURRENT, so a captured old signed
document could otherwise freeze a client on a stale (or vulnerable) release. Verifiers
refuse an expired document (`check_fresh`) and, via `installer`, refuse a ``serial`` lower
than the highest they have accepted (rollback/replay).

Version ordering uses PEP 440 via `packaging.version` (a direct `decoy-engine`
dependency, so present in the managed runtime); no hand-rolled comparison.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from packaging.version import InvalidVersion, Version

from decoy.distribution import signing

VERSION_DOCUMENT_SCHEMA_VERSION = "cli-version-document/v1"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_VALIDITY_DAYS = 30


def build_document(
    *,
    latest: str,
    min_supported: str,
    artifacts: dict[str, dict[str, str]],
    serial: int,
    yanked: list[str] | None = None,
    message: str = "",
    generated: str | None = None,
    expires: str | None = None,
) -> dict[str, Any]:
    """Assemble a v1 payload. ``artifacts`` maps a target id to {url, sha256, sig};
    ``expires`` defaults to ``DEFAULT_VALIDITY_DAYS`` after ``generated``."""
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    if generated is None:
        generated = now.strftime(TIME_FORMAT)
    if expires is None:
        base = _parse_time(generated) or now
        expires = (base + _dt.timedelta(days=DEFAULT_VALIDITY_DAYS)).strftime(TIME_FORMAT)
    return {
        "schema_version": VERSION_DOCUMENT_SCHEMA_VERSION,
        "latest": latest,
        "min_supported": min_supported,
        "yanked": sorted(yanked or []),
        "message": message,
        "generated": generated,
        "serial": serial,
        "expires": expires,
        "artifacts": artifacts,
    }


def _parse_time(value: object) -> _dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return _dt.datetime.strptime(value, TIME_FORMAT).replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


def canonical_document_bytes(payload: dict[str, Any]) -> bytes:
    return signing.canonical_bytes(payload)


def parse_document(data: bytes) -> dict[str, Any]:
    """Parse the on-the-wire bytes into a payload dict, rejecting a document of the
    wrong schema. Callers verify the signature over ``data`` BEFORE trusting the parse."""
    import json

    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("version document is not an object")
    if payload.get("schema_version") != VERSION_DOCUMENT_SCHEMA_VERSION:
        raise ValueError(f"unexpected version-document schema: {payload.get('schema_version')!r}")
    serial = payload.get("serial")
    if not isinstance(serial, int) or isinstance(serial, bool) or serial < 1:
        raise ValueError("version document has no valid 'serial'")
    if _parse_time(payload.get("expires")) is None:
        raise ValueError("version document has no valid 'expires'")
    return payload


def check_fresh(payload: dict[str, Any], *, now: _dt.datetime | None = None) -> None:
    """Raise ValueError if the (already signature-verified, parsed) document has expired.
    ``now`` is injectable for tests; naive values are taken as UTC."""
    now = now or _dt.datetime.now(tz=_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    expires = _parse_time(payload.get("expires"))
    if expires is None:
        raise ValueError("version document has no valid 'expires'")
    if now >= expires:
        raise ValueError(f"version document expired at {payload['expires']} (stale or replayed)")


def verify_document(data: bytes, signature_b64: str, *, expected_public_pem: str) -> bool:
    """Verify the detached signature over the exact document bytes against the PINNED
    release key -- the same check `openssl pkeyutl -verify -rawin` performs in
    `install.sh`."""
    return signing.verify_detached(data, signature_b64, expected_public_pem=expected_public_pem)


def select_artifact(payload: dict[str, Any], target: str) -> dict[str, str] | None:
    """The {url, sha256, sig} for ``target``, or None if this document lists no bundle for
    it (an older CLI on a target a newer document dropped, or vice versa: degrade, do not
    crash)."""
    art = payload.get("artifacts")
    if not isinstance(art, dict):
        return None
    entry = art.get(target)
    if not isinstance(entry, dict):
        return None
    if not all(isinstance(entry.get(k), str) for k in ("url", "sha256", "sig")):
        return None
    return {"url": entry["url"], "sha256": entry["sha256"], "sig": entry["sig"]}


def is_yanked(payload: dict[str, Any], version: str) -> bool:
    yanked = payload.get("yanked")
    return isinstance(yanked, list) and version in yanked


def _parse(v: str) -> Version | None:
    try:
        return Version(v)
    except (InvalidVersion, TypeError):
        return None


def compare_versions(a: str, b: str) -> int:
    """-1 if a<b, 0 if a==b, 1 if a>b, by PEP 440. Raises ValueError on an unparseable
    version so a caller never silently mis-orders."""
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None:
        raise ValueError(f"unparseable version(s): {a!r}, {b!r}")
    return (pa > pb) - (pa < pb)


def newer_available(current: str, payload: dict[str, Any]) -> bool:
    """Whether ``current`` should be told a newer release exists: latest parses, is newer
    than current, and is not itself yanked. Unparseable input degrades to False (the
    notice/upgrade is advisory and must never crash a run)."""
    latest = payload.get("latest")
    if not isinstance(latest, str) or is_yanked(payload, latest):
        return False
    try:
        return compare_versions(current, latest) < 0
    except ValueError:
        return False


def below_floor(current: str, payload: dict[str, Any]) -> bool:
    """Whether ``current`` is below the document's ``min_supported`` floor. Degrades to
    False on unparseable input."""
    floor = payload.get("min_supported")
    if not isinstance(floor, str):
        return False
    try:
        return compare_versions(current, floor) < 0
    except ValueError:
        return False
