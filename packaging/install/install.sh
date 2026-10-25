#!/bin/sh
# Decoy CLI installer (posix: Linux, macOS).
#
# Lays down a managed, self-contained runtime under ~/.decoy and a `decoy`
# launcher on PATH. It VERIFIES a checksum and a signature BEFORE it extracts
# anything; a bad checksum or signature is a hard stop and nothing is installed.
#
# Scheme (see packaging/sign/): the release publishes, per version, a per-target
# bundle tarball plus a SHA256SUMS manifest and an ECDSA-P256/SHA-256 detached
# signature OVER that manifest. This script verifies the manifest signature with
# the openssl already on the box, then verifies the tarball against the manifest,
# then extracts. That is the rustup / uv pattern.
#
# Usage:
#   install.sh [--version X.Y.Z]      install latest (or a pinned version)
#   install.sh uninstall              remove the managed runtime and launcher
#   install.sh --help
#
# Config (env; defaults are the real self-hosted channel):
#   DECOY_INSTALL_HOME       install root            (default: $HOME/.decoy)
#   DECOY_INSTALL_BIN        PATH dir for launcher    (default: $HOME/.local/bin)
#   DECOY_INSTALL_BASE_URL   download host base URL   (default: https://decoy.dev/cli)
#   DECOY_INSTALL_LOCAL_DIR  install from a local dir (offline / air-gapped; no network)
#   DECOY_INSTALL_PUBKEY     verify with this pubkey  (default: the embedded release key)
set -eu

DECOY_INSTALL_HOME=${DECOY_INSTALL_HOME:-$HOME/.decoy}
DECOY_INSTALL_BIN=${DECOY_INSTALL_BIN:-$HOME/.local/bin}
DECOY_INSTALL_BASE_URL=${DECOY_INSTALL_BASE_URL:-https://decoy.dev/cli}
DECOY_INSTALL_LOCAL_DIR=${DECOY_INSTALL_LOCAL_DIR:-}
DECOY_INSTALL_PUBKEY=${DECOY_INSTALL_PUBKEY:-}

# The release public key, embedded so a `curl | sh` bootstrap can verify with no
# prior download. THIS IS A LOCAL TEST KEY (packaging/sign/README.md); the real
# release build swaps this block for the real public key. DECOY_INSTALL_PUBKEY
# overrides it (used by the signing self-test).
EMBEDDED_PUBKEY='-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEE474c7kSNltShBhZahXv3Ny74pdQ
kgpAWRkfzJb6n4cuudOalN2Upm2mVDBfVq6pkmSeFc69GcbotqFde4ruhQ==
-----END PUBLIC KEY-----'

die() {
    echo "decoy-install: $*" >&2
    exit 1
}

info() {
    echo "decoy-install: $*"
}

detect_target() {
    os=$(uname -s 2>/dev/null || echo unknown)
    arch=$(uname -m 2>/dev/null || echo unknown)
    case "$os" in
        Linux) os_key=linux ;;
        Darwin) os_key=macos ;;
        *) die "unsupported OS '$os'. Supported: Linux, macOS. See packaging/README.md for the supported targets and the plain-archive fallback." ;;
    esac
    case "$os_key:$arch" in
        linux:x86_64 | linux:amd64) echo "linux-x86_64" ;;
        linux:aarch64 | linux:arm64) echo "linux-aarch64" ;;
        macos:arm64) echo "macos-arm64" ;;
        macos:x86_64)
            die "macOS Intel (x86_64) has no bundle at launch (open target decision; see packaging/README.md). No partial or slow install is performed." ;;
        *) die "unsupported target '$os_key/$arch'. Supported: linux-x86_64, linux-aarch64, macos-arm64. No install performed." ;;
    esac
}

# Copy from the local dir (offline) or download from the base URL. One place
# decides the source, so the verify path below is identical offline and online.
fetch() {
    rel=$1
    dest=$2
    if [ -n "$DECOY_INSTALL_LOCAL_DIR" ]; then
        [ -f "$DECOY_INSTALL_LOCAL_DIR/$rel" ] || die "artifact not found in local dir: $rel"
        cp -- "$DECOY_INSTALL_LOCAL_DIR/$rel" "$dest"
    else
        command -v curl >/dev/null 2>&1 || die "curl is required for a network install"
        curl -fsSL "$DECOY_INSTALL_BASE_URL/$rel" -o "$dest" \
            || die "download failed: $DECOY_INSTALL_BASE_URL/$rel"
    fi
}

json_string_field() {
    # Extract a flat top-level string field "key": "value" from a JSON file.
    # The installer only needs `latest`; the richer artifacts map is for the
    # version client, not this bootstrap path.
    sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$2" | head -n1
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        die "no sha256sum or shasum found to verify the checksum"
    fi
}

do_uninstall() {
    launcher=$DECOY_INSTALL_BIN/decoy
    if [ -L "$launcher" ] || [ -f "$launcher" ]; then
        rm -f -- "$launcher"
        info "removed launcher $launcher"
    fi
    if [ -d "$DECOY_INSTALL_HOME" ]; then
        rm -rf -- "$DECOY_INSTALL_HOME"
        info "removed managed runtime $DECOY_INSTALL_HOME"
    fi
    info "uninstalled."
}

VERSION=""
while [ $# -gt 0 ]; do
    case "$1" in
        uninstall) do_uninstall; exit 0 ;;
        --version) shift; [ $# -gt 0 ] || die "--version needs a value"; VERSION=$1 ;;
        --version=*) VERSION=${1#--version=} ;;
        --help | -h)
            sed -n '2,30p' "$0" 2>/dev/null || echo "see packaging/README.md"
            exit 0 ;;
        *) die "unknown argument '$1' (try --help)" ;;
    esac
    shift
done

command -v openssl >/dev/null 2>&1 || die "openssl is required to verify the signature"

target=$(detect_target)
info "target: $target"

# Stage everything in a temp dir; nothing touches the install root until the
# tarball has passed both the signature and the checksum check.
staging=$(mktemp -d "${TMPDIR:-/tmp}/decoy-install.XXXXXX") || die "could not create a staging dir"
trap 'rm -rf -- "$staging"' EXIT

# Resolve the version: an explicit --version, else `latest` from version.json.
if [ -z "$VERSION" ]; then
    fetch "version.json" "$staging/version.json"
    VERSION=$(json_string_field latest "$staging/version.json")
    [ -n "$VERSION" ] || die "could not read 'latest' from version.json"
fi
info "version: $VERSION"

tarball_name="decoy-$VERSION-$target.tar.gz"
fetch "$VERSION/$tarball_name" "$staging/$tarball_name"
fetch "$VERSION/SHA256SUMS" "$staging/SHA256SUMS"
fetch "$VERSION/SHA256SUMS.sig" "$staging/SHA256SUMS.sig"

# The pubkey: an override file, or the embedded release key written out.
pubkey=$staging/decoy-release.pub
if [ -n "$DECOY_INSTALL_PUBKEY" ]; then
    [ -f "$DECOY_INSTALL_PUBKEY" ] || die "pubkey not found: $DECOY_INSTALL_PUBKEY"
    cp -- "$DECOY_INSTALL_PUBKEY" "$pubkey"
else
    printf '%s\n' "$EMBEDDED_PUBKEY" > "$pubkey"
fi

# 1. Verify the manifest signature. A failure here is a hard stop: the manifest
#    cannot be trusted, so the checksums in it cannot be trusted.
if ! openssl dgst -sha256 -verify "$pubkey" -signature "$staging/SHA256SUMS.sig" \
        "$staging/SHA256SUMS" >/dev/null 2>&1; then
    die "SIGNATURE VERIFICATION FAILED for SHA256SUMS. Refusing to install. The download may be tampered or corrupt."
fi
info "signature OK"

# 2. Verify the tarball against the now-trusted manifest.
expected=$(awk -v f="$tarball_name" '$2 == f {print $1}' "$staging/SHA256SUMS")
[ -n "$expected" ] || die "no checksum for $tarball_name in SHA256SUMS. Refusing to install."
actual=$(sha256_of "$staging/$tarball_name")
if [ "$expected" != "$actual" ]; then
    die "CHECKSUM MISMATCH for $tarball_name (expected $expected, got $actual). Refusing to install."
fi
info "checksum OK"

# Verified. Extract into the versioned dir, then flip `current` atomically so an
# interrupted install never leaves `current` pointing at a half-written dir.
versions_dir=$DECOY_INSTALL_HOME/versions
version_dir=$versions_dir/$VERSION
mkdir -p "$versions_dir"
rm -rf -- "$version_dir"
mkdir -p "$version_dir"
tar -xzf "$staging/$tarball_name" -C "$version_dir" || die "extraction failed"

# The tarball may wrap its contents in a single top directory; if so, lift them.
if [ ! -e "$version_dir/bundle-manifest.json" ]; then
    inner=$(find "$version_dir" -mindepth 1 -maxdepth 1 -type d | head -n1)
    if [ -n "$inner" ] && [ -e "$inner/bundle-manifest.json" ]; then
        mv -- "$inner"/* "$version_dir"/ 2>/dev/null || true
        mv -- "$inner"/.[!.]* "$version_dir"/ 2>/dev/null || true
        rmdir -- "$inner" 2>/dev/null || true
    fi
fi
[ -e "$version_dir/bundle-manifest.json" ] || die "bundle is malformed: no bundle-manifest.json after extract"

# Atomic `current` flip via a temp symlink + rename.
tmp_link=$DECOY_INSTALL_HOME/.current.$$
ln -sfn "$version_dir" "$tmp_link"
mv -T "$tmp_link" "$DECOY_INSTALL_HOME/current" 2>/dev/null \
    || mv -f "$tmp_link" "$DECOY_INSTALL_HOME/current"

# Launcher on PATH (a symlink to current/bin/decoy, so an upgrade needs no PATH
# change: only `current` moves).
mkdir -p "$DECOY_INSTALL_BIN"
ln -sfn "$DECOY_INSTALL_HOME/current/bin/decoy" "$DECOY_INSTALL_BIN/decoy"

info "installed decoy $VERSION for $target."
info "launcher: $DECOY_INSTALL_BIN/decoy"
case ":$PATH:" in
    *":$DECOY_INSTALL_BIN:"*) : ;;
    *) info "add $DECOY_INSTALL_BIN to your PATH, then restart your shell." ;;
esac
