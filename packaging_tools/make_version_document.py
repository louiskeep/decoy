"""Assemble + sign the hosted version document from a set of built bundles (build host).

Reads the tarballs (+ their ``.sha256`` sidecars) in a dist dir, builds the v1 version
document (`decoy.distribution.version_document`), writes it as canonical bytes to
``version.json``, and detached-signs it to ``version.json.sig`` with the release key.
The signed document + its sidecar are what the install script and `decoy upgrade`
fetch from the Decoy-hosted endpoint.

The document is served static behind a CDN for V1 (packaging spec: "a static file is
acceptable for V1"); nothing here assumes a live service.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from decoy.distribution import manifest as manifest_mod
from decoy.distribution import targets as targets_mod
from decoy.distribution import version_document as vd


def _read_sha256(sha_path: Path) -> str:
    # sha256sum format: "<hex>  <filename>"
    return sha_path.read_text(encoding="utf-8").split()[0]


def collect_artifacts(dist_dir: Path, *, version: str, base_url: str) -> dict[str, dict[str, str]]:
    """One {url, sha256, sig} per target that has a built tarball in ``dist_dir``.

    ``base_url`` is the directory the bundles are published under; the per-file names
    follow the assembler's convention (``decoy-<version>-<target>.tar.gz`` + ``.sig``)."""
    base = base_url.rstrip("/")
    artifacts: dict[str, dict[str, str]] = {}
    for target in targets_mod.SUPPORTED_TARGETS:
        name = f"decoy-{version}-{target}.tar.gz"
        tarball = dist_dir / name
        sha_path = dist_dir / (name + ".sha256")
        sig_path = dist_dir / (name + ".sig")
        if not (tarball.exists() and sha_path.exists() and sig_path.exists()):
            continue
        # Cross-check the sidecar against the actual bytes so a stale sidecar can never
        # ship a wrong (signed) checksum.
        actual = manifest_mod.sha256_file(tarball)
        declared = _read_sha256(sha_path)
        if actual != declared:
            raise ValueError(f"{name}: sidecar sha256 {declared} != actual {actual}")
        artifacts[target] = {
            "url": f"{base}/{name}",
            "sha256": actual,
            "sig": f"{base}/{name}.sig",
        }
    return artifacts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="make_version_document")
    ap.add_argument("--version", required=True, help="the latest release version")
    ap.add_argument("--min-supported", required=True)
    ap.add_argument("--dist", required=True, help="dir holding the built tarballs + sidecars")
    ap.add_argument("--base-url", required=True, help="published base URL for the bundles")
    ap.add_argument("--out", required=True, help="output path for version.json")
    ap.add_argument("--message", default="")
    ap.add_argument("--yanked", nargs="*", default=[])
    ap.add_argument("--sign", action="store_true")
    args = ap.parse_args(argv)

    dist = Path(args.dist)
    artifacts = collect_artifacts(dist, version=args.version, base_url=args.base_url)
    if not artifacts:
        sys.stderr.write("no bundles found in dist dir; nothing to publish\n")
        return 2

    doc = vd.build_document(
        latest=args.version,
        min_supported=args.min_supported,
        artifacts=artifacts,
        yanked=list(args.yanked),
        message=args.message,
    )
    data = vd.canonical_document_bytes(doc)
    out = Path(args.out)
    out.write_bytes(data)
    sys.stderr.write(f"wrote {out} ({len(artifacts)} target(s): {', '.join(sorted(artifacts))})\n")

    if args.sign:
        from packaging_tools.sign_release import load_private_key, sign_file

        sign_file(out, load_private_key())
        sys.stderr.write(f"signed {out} -> {out}.sig\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
