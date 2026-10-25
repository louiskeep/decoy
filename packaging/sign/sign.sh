#!/bin/sh
# Sign a directory of release artifacts for the Decoy CLI distribution.
#
# Produces, in the artifact directory:
#   SHA256SUMS       a checksums manifest over every *.tar.gz / *.zip artifact
#   SHA256SUMS.sig   an ECDSA-P256/SHA-256 detached signature OVER the manifest
#
# The manifest is signed once and each artifact is checksummed, the rustup / uv
# pattern: a client verifies the signature of the manifest, then verifies each
# artifact against the manifest. The install script does exactly that.
#
# The signing key is a path argument, never read from the repo. For local build
# + test, pass the test key from gen-test-key.sh. For a real release, point this
# at the real key material at its custody location (packaging/sign/README.md).
#
# Usage: packaging/sign/sign.sh <artifact-dir> <private-key>
set -eu

artifact_dir=${1:-}
private_key=${2:-}
if [ -z "$artifact_dir" ] || [ -z "$private_key" ]; then
    echo "usage: $0 <artifact-dir> <private-key>" >&2
    exit 2
fi
if [ ! -d "$artifact_dir" ]; then
    echo "sign: artifact dir not found: $artifact_dir" >&2
    exit 1
fi
if [ ! -f "$private_key" ]; then
    echo "sign: private key not found: $private_key" >&2
    exit 1
fi

# Build the manifest with bare filenames (no directory prefix) so verification
# is directory-relative on any host. Prefer sha256sum, fall back to `shasum -a
# 256` (macOS) so the signer runs on either.
if command -v sha256sum >/dev/null 2>&1; then
    hash_cmd="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
    hash_cmd="shasum -a 256"
else
    echo "sign: no sha256sum or shasum found" >&2
    exit 1
fi

manifest=$artifact_dir/SHA256SUMS
: > "$manifest"
found=0
for artifact in "$artifact_dir"/*.tar.gz "$artifact_dir"/*.zip; do
    [ -e "$artifact" ] || continue
    found=1
    name=$(basename -- "$artifact")
    digest=$( (cd -- "$artifact_dir" && $hash_cmd "$name") | awk '{print $1}')
    printf '%s  %s\n' "$digest" "$name" >> "$manifest"
done
if [ "$found" -eq 0 ]; then
    echo "sign: no *.tar.gz or *.zip artifacts in $artifact_dir" >&2
    exit 1
fi

openssl dgst -sha256 -sign "$private_key" -out "$manifest.sig" "$manifest"
echo "signed $(wc -l < "$manifest" | tr -d ' ') artifact(s):"
cat "$manifest"
echo "signature: $manifest.sig"
