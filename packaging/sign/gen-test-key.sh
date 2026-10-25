#!/bin/sh
# Generate a LOCAL TEST signing keypair for the Decoy CLI distribution.
#
# This is for local build + test only. The real release signing key is generated
# and held out of band (see packaging/sign/README.md for custody and the plug-in
# point); it is never produced by, or committed from, this repo. The private key
# this writes is .gitignore'd and must never be committed.
#
# Scheme: ECDSA P-256 (prime256v1) with SHA-256, verified by `openssl dgst`. That
# primitive is supported by both OpenSSL (Linux, Windows git) and LibreSSL
# (macOS) command-line tools, so the install script can verify with the openssl
# that is already on the box, no extra binary to bootstrap. No custom crypto.
#
# Usage: packaging/sign/gen-test-key.sh <out-dir>
#   writes <out-dir>/decoy-release-test.key (private, keep out of git)
#          <out-dir>/decoy-release.pub      (public, committed to install/)
set -eu

out_dir=${1:-}
if [ -z "$out_dir" ]; then
    echo "usage: $0 <out-dir>" >&2
    exit 2
fi
mkdir -p "$out_dir"
priv=$out_dir/decoy-release-test.key
pub=$out_dir/decoy-release.pub

openssl ecparam -name prime256v1 -genkey -noout -out "$priv"
openssl ec -in "$priv" -pubout -out "$pub" 2>/dev/null
chmod 600 "$priv"

echo "wrote private (keep out of git): $priv"
echo "wrote public  (commit to install/): $pub"
