"""Verify an extracted bundle against its in-bundle signed manifest (installer helper).

Run by `install.sh` / `decoy upgrade` through the bundle's own interpreter AFTER the
tarball's Ed25519 signature has already been verified against the pinned release key.
The signature is the trust anchor; this is defense in depth: it recomputes every
file's SHA-256 against ``manifest.json`` and rejects any on-disk file the manifest does
not list (forward + reverse), catching a truncated or altered extraction before the
runtime is promoted.

Optionally re-verifies ``manifest.json``'s own detached signature when a pinned public
key is supplied, so the check does not rest solely on the caller having verified the
enclosing tarball.

Exit 0 = clean; non-zero = refuse the install.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from decoy.distribution import manifest as manifest_mod
from decoy.distribution import signing


def verify_extracted(bundle_root: Path, *, expected_public_pem: str | None = None) -> list[str]:
    """Return a list of human-readable problems ([] = clean)."""
    problems: list[str] = []
    man_path = bundle_root / manifest_mod.MANIFEST_NAME
    if not man_path.is_file():
        return [f"missing {manifest_mod.MANIFEST_NAME}"]
    man_bytes = man_path.read_bytes()

    if expected_public_pem is not None:
        sig_path = bundle_root / manifest_mod.MANIFEST_SIG_NAME
        if not sig_path.is_file():
            problems.append(f"missing {manifest_mod.MANIFEST_SIG_NAME}")
        elif not signing.verify_detached(
            man_bytes, sig_path.read_text(encoding="utf-8").strip(),
            expected_public_pem=expected_public_pem,
        ):
            problems.append("manifest signature invalid")

    try:
        manifest = json.loads(man_bytes)
    except ValueError as exc:
        return [*problems, f"manifest is not valid JSON: {exc}"]
    if manifest.get("schema_version") != manifest_mod.MANIFEST_SCHEMA_VERSION:
        problems.append(f"unexpected manifest schema: {manifest.get('schema_version')!r}")

    for p in manifest_mod.verify_manifest(manifest, bundle_root):
        problems.append(f"{p['problem']}: {p['path']}")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m decoy.distribution.verify_extracted <bundle-root> [pubkey.pem]", file=sys.stderr)
        return 2
    bundle_root = Path(argv[0])
    pub = Path(argv[1]).read_text(encoding="utf-8") if len(argv) > 1 else None
    problems = verify_extracted(bundle_root, expected_public_pem=pub)
    if problems:
        for p in problems[:20]:
            print(f"decoy: bundle verify problem -- {p}", file=sys.stderr)
        return 1
    print("OK: bundle manifest verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
