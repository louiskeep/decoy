#!/bin/sh
# Decoy CLI installer: self-hosted, signed, per-platform bundle.
#
# Lays down a managed, self-contained runtime (bundled CPython + matched
# engine/native/CLI wheels) under ~/.decoy and a `decoy` launcher on PATH. The user
# brings no Python of their own.
#
# Trust model (config-secrets-and-supply-chain + security): this script arrives over
# TLS from the Decoy host and PINS the release public key inline. It verifies the
# hosted version document's Ed25519 signature AND the bundle's Ed25519 signature AND a
# SHA-256 checksum against the signed document BEFORE anything is laid down. The
# signature is the raw Ed25519 signature produced by `decoy.distribution.signing` /
# `packaging_tools.sign_release`, so `openssl pkeyutl -verify -rawin` checks the exact same
# bytes `decoy upgrade` checks. A failed signature OR checksum is a HARD REFUSAL, never
# a warning-and-continue. Established methodology: Ed25519 via openssl; no hand-rolled
# verification.
#
# Usage:
#   curl -LsSf https://decoy.dev/cli/install.sh | sh
#   sh install.sh [--version X.Y.Z] [uninstall]
#
# Env overrides (also used by the test harness):
#   DECOY_HOME            install root (default: ~/.decoy)
#   DECOY_BIN_DIR         launcher dir on PATH (default: ~/.local/bin)
#   DECOY_VERSION_URL     version document URL (default: the hosted endpoint)
#   DECOY_RELEASE_PUBKEY_FILE  override the pinned key (testing only)
#   DECOY_LOCAL_BUNDLE    install from a local tarball instead of downloading (offline)
set -eu

DEFAULT_VERSION_URL="https://decoy.dev/cli/version.json"
DECOY_HOME="${DECOY_HOME:-$HOME/.decoy}"
DECOY_BIN_DIR="${DECOY_BIN_DIR:-$HOME/.local/bin}"
DECOY_VERSION_URL="${DECOY_VERSION_URL:-$DEFAULT_VERSION_URL}"

# --- pinned release public key -------------------------------------------------
# DEV/PLACEHOLDER key. Replaced at launch with the real release key's public half
# (generated once in the release secret store; see packaging_tools/README.md). The matching
# private key signs the version document and every bundle.
PINNED_PUBKEY='-----BEGIN PUBLIC KEY-----
__DECOY_RELEASE_PUBLIC_KEY__
-----END PUBLIC KEY-----'

die() { printf 'decoy install: %s\n' "$*" >&2; exit 1; }
info() { printf 'decoy install: %s\n' "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || die "required tool not found: $1"; }

detect_target() {
  _os=$(uname -s 2>/dev/null || echo unknown)
  _arch=$(uname -m 2>/dev/null || echo unknown)
  case "$_arch" in
    x86_64|amd64) _arch=x86_64 ;;
    aarch64) _arch=aarch64 ;;
    arm64) _arch=arm64 ;;
  esac
  case "$_os" in
    Linux)
      case "$_arch" in
        x86_64) echo linux-x86_64 ;;
        aarch64) echo linux-aarch64 ;;
        *) echo "" ;;
      esac ;;
    Darwin)
      case "$_arch" in
        arm64) echo macos-arm64 ;;
        # macOS Intel is intentionally unsupported at launch (not in the matrix).
        *) echo "" ;;
      esac ;;
    # Windows is gated off the advertised matrix this cycle (POSIX-shaped managed
    # runtime; the Windows lifecycle is unverified). Refuse rather than install an
    # unrunnable path. See docs/distribution/decisions/2026-10-26-windows-target-gated.md.
    MINGW*|MSYS*|CYGWIN*|Windows_NT) echo "" ;;
    *) echo "" ;;
  esac
}

fetch() {
  # fetch URL OUTFILE -- curl or wget, failing loudly on HTTP error.
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then
    wget -q "$1" -O "$2"
  else
    die "need curl or wget to download"
  fi
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

verify_sig() {
  # verify_sig DATA_FILE SIG_B64_FILE PUBKEY_PEM -- raw detached Ed25519 via openssl.
  # Returns non-zero on any failure; the caller turns that into a hard refusal.
  _raw="$(mktemp)"
  openssl base64 -d -A -in "$2" -out "$_raw" 2>/dev/null || { rm -f "$_raw"; return 1; }
  if openssl pkeyutl -verify -pubin -inkey "$3" -rawin -in "$1" -sigfile "$_raw" >/dev/null 2>&1; then
    rm -f "$_raw"; return 0
  fi
  rm -f "$_raw"; return 1
}

# Extract one string field from CANONICAL (sorted, compact) JSON. Safe because the
# document is emitted by decoy.distribution.version_document in canonical form and the values
# (version strings, hex, URLs) contain no '"' or '}'.
json_top_string() { grep -o "\"$2\":\"[^\"]*\"" "$1" | head -n1 | sed 's/.*":"//;s/"$//'; }
json_artifact_field() {
  # json_artifact_field FILE TARGET FIELD
  grep -o "\"$2\":{[^}]*}" "$1" | head -n1 \
    | grep -o "\"$3\":\"[^\"]*\"" | head -n1 | sed 's/.*":"//;s/"$//'
}

uninstall() {
  info "removing $DECOY_HOME and $DECOY_BIN_DIR/decoy"
  rm -f "$DECOY_BIN_DIR/decoy"
  rm -rf "$DECOY_HOME"
  info "uninstalled. (remove the PATH line from your shell profile if you added one.)"
  exit 0
}

ACTION=install
PIN_VERSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    uninstall) ACTION=uninstall ;;
    --version) shift; PIN_VERSION="${1:-}" ;;
    --version=*) PIN_VERSION="${1#--version=}" ;;
    -h|--help) printf 'usage: install.sh [--version X.Y.Z] [uninstall]\n'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

[ "$ACTION" = uninstall ] && uninstall

need openssl
need tar
need mktemp

TARGET=$(detect_target)
[ -n "$TARGET" ] || die "unsupported platform ($(uname -s)/$(uname -m)). Supported: linux-x86_64, linux-aarch64, macos-arm64. (macOS Intel and Windows are not supported at launch.)"
info "target: $TARGET"

WORK=$(mktemp -d)
INCOMING=""
# Clean the temp workdir AND any quarantine dir on every exit, so a refusal never
# leaves a half-extracted runtime behind.
trap 'rm -rf "$WORK" "${INCOMING:-/nonexistent}"' EXIT

# Pinned key -> PEM file (test override allowed).
PUBKEY="$WORK/pub.pem"
if [ -n "${DECOY_RELEASE_PUBKEY_FILE:-}" ]; then
  cp "$DECOY_RELEASE_PUBKEY_FILE" "$PUBKEY"
else
  printf '%s\n' "$PINNED_PUBKEY" > "$PUBKEY"
fi

# Base URL for per-version bundles = the version-doc URL minus its filename.
BASE_URL=$(printf '%s' "$DECOY_VERSION_URL" | sed 's#/[^/]*$##')

if [ -n "${DECOY_LOCAL_BUNDLE:-}" ]; then
  # Offline / air-gapped: install from a local tarball + its .sig + .sha256 sidecars.
  TARBALL="$DECOY_LOCAL_BUNDLE"
  SIGFILE="$DECOY_LOCAL_BUNDLE.sig"
  SHAFILE="$DECOY_LOCAL_BUNDLE.sha256"
  [ -f "$TARBALL" ] && [ -f "$SIGFILE" ] && [ -f "$SHAFILE" ] || die "offline install needs $TARBALL plus .sig and .sha256 sidecars"
  VERSION="${PIN_VERSION:-local}"
  EXPECT_SHA=$(cut -d' ' -f1 < "$SHAFILE")
else
  # Fetch + verify the signed version document.
  VDOC="$WORK/version.json"
  fetch "$DECOY_VERSION_URL" "$VDOC" || die "could not fetch version document: $DECOY_VERSION_URL"
  fetch "$DECOY_VERSION_URL.sig" "$VDOC.sig" || die "could not fetch version-document signature"
  verify_sig "$VDOC" "$VDOC.sig" "$PUBKEY" || die "version-document signature INVALID -- refusing (possible tampering)"
  info "version document signature verified"

  LATEST=$(json_top_string "$VDOC" latest)
  [ -n "$LATEST" ] || die "version document has no 'latest'"
  VERSION="${PIN_VERSION:-$LATEST}"

  if [ "$VERSION" = "$LATEST" ]; then
    URL=$(json_artifact_field "$VDOC" "$TARGET" url)
    EXPECT_SHA=$(json_artifact_field "$VDOC" "$TARGET" sha256)
    SIGURL=$(json_artifact_field "$VDOC" "$TARGET" sig)
    [ -n "$URL" ] && [ -n "$EXPECT_SHA" ] && [ -n "$SIGURL" ] || die "version document lists no bundle for $TARGET"
  else
    # Pinned to a non-latest version: the signed version document carries only the
    # latest release's checksum, so construct URLs by convention and take the checksum
    # from the published .sha256 sidecar below. That sidecar is UNSIGNED, so for a pin
    # the Ed25519 signature (verified against the pinned key, always) is the sole trust
    # anchor; the sidecar is only a best-effort corruption check and is skipped if its
    # fetch fails. "flipped byte refuses on checksum" is therefore a guarantee of the
    # latest path (signed checksum); on a pin, a flipped byte refuses on SIGNATURE.
    URL="$BASE_URL/$VERSION/decoy-$VERSION-$TARGET.tar.gz"
    SIGURL="$URL.sig"
    EXPECT_SHA=""
  fi

  TARBALL="$WORK/decoy-$VERSION-$TARGET.tar.gz"
  SIGFILE="$TARBALL.sig"
  fetch "$URL" "$TARBALL" || die "could not download bundle: $URL"
  fetch "$SIGURL" "$SIGFILE" || die "could not download bundle signature: $SIGURL"
  if [ -z "$EXPECT_SHA" ]; then
    fetch "$URL.sha256" "$TARBALL.sha256" 2>/dev/null && EXPECT_SHA=$(cut -d' ' -f1 < "$TARBALL.sha256") || true
  fi
fi

# 1) checksum (corruption + the signed checksum when we have it)
if [ -n "$EXPECT_SHA" ]; then
  GOT_SHA=$(sha256_of "$TARBALL")
  [ "$GOT_SHA" = "$EXPECT_SHA" ] || die "bundle checksum MISMATCH (expected $EXPECT_SHA got $GOT_SHA) -- refusing"
  info "bundle checksum verified"
fi
# 2) signature (the trust anchor) -- hard refusal on failure
verify_sig "$TARBALL" "$SIGFILE" "$PUBKEY" || die "bundle signature INVALID -- refusing (possible tampering)"
info "bundle signature verified"

# 3) quarantine-extract, then promote. Nothing is laid down live until every check
#    above passed and the native self-check below passes.
VERSIONS="$DECOY_HOME/versions"
mkdir -p "$VERSIONS"
INCOMING="$VERSIONS/.incoming.$$"
rm -rf "$INCOMING"; mkdir -p "$INCOMING"
tar -xzf "$TARBALL" -C "$INCOMING"
# The archive holds a single top-level dir decoy-<version>-<target>/.
BUNDLE_ROOT=$(find "$INCOMING" -mindepth 1 -maxdepth 1 -type d | head -n1)
[ -n "$BUNDLE_ROOT" ] || die "bundle archive is malformed (no top-level dir)"
PYBIN="$BUNDLE_ROOT/python/bin/python3"
[ -x "$PYBIN" ] || die "bundle is missing its interpreter"

# The bundled interpreter runs with bytecode writing OFF (-B + PYTHONDONTWRITEBYTECODE):
# the manifest does not sign caches and the verifier rejects any found on disk, so these
# install-time checks must not leave an unsigned __pycache__ behind. (See
# decoy.distribution.manifest.)
export PYTHONDONTWRITEBYTECODE=1

# 3a) manifest verify (defense in depth: the signature already established trust; this
#     catches a truncated/altered extraction OR a planted bytecode cache). Reuses the
#     shipped verifier.
"$PYBIN" -B -m decoy.distribution.verify_extracted "$BUNDLE_ROOT" || die "bundle manifest verification FAILED -- refusing"

# 3b) native-present self-check: LOUD refusal if the companion is missing/mismatched.
"$PYBIN" -B -m decoy.distribution.selfcheck || die "native companion self-check FAILED -- refusing this install"

# 3c) identity check (HIGH: a validly-signed but wrong-version/target bundle served at a
#     pinned URL must NOT overwrite the retained versions/<version> runtime). Compare the
#     bundle's DECLARED version + target (BUNDLE_INFO.json, signed into the manifest)
#     against what was requested, BEFORE any deletion. A mismatch refuses untouched.
BINFO="$BUNDLE_ROOT/BUNDLE_INFO.json"
[ -f "$BINFO" ] || die "bundle is missing BUNDLE_INFO.json; cannot verify its identity -- refusing"
DECLARED_VERSION=$(json_top_string "$BINFO" version)
DECLARED_TARGET=$(json_top_string "$BINFO" target)
[ -n "$DECLARED_VERSION" ] && [ -n "$DECLARED_TARGET" ] || die "bundle BUNDLE_INFO.json has no version/target -- refusing"
[ "$DECLARED_TARGET" = "$TARGET" ] || die "refusing: bundle declares target '$DECLARED_TARGET' but this host is '$TARGET' -- nothing installed"
# When a specific version was requested (every path except an offline bundle with no
# --version, where VERSION is the literal 'local'), the bytes must declare it.
if [ "$VERSION" != "local" ]; then
  [ "$DECLARED_VERSION" = "$VERSION" ] || die "refusing: bundle declares version '$DECLARED_VERSION' but '$VERSION' was requested (resolution mismatch) -- versions/$VERSION left untouched"
fi

# 4) promote into place + flip `current` atomically (reuses the tested layout helper).
DEST="$VERSIONS/$VERSION"
rm -rf "$DEST"
mv "$BUNDLE_ROOT" "$DEST"
rm -rf "$INCOMING"
DECOY_HOME="$DECOY_HOME" "$DEST/python/bin/python3" -B -m decoy.distribution.layout_point "$VERSION" \
  || die "could not point 'current' at $VERSION"

# 5) launcher shim on PATH -> the current runtime.
mkdir -p "$DECOY_BIN_DIR"
cat > "$DECOY_BIN_DIR/decoy" <<EOF
#!/bin/sh
exec "$DECOY_HOME/current/decoy" "\$@"
EOF
chmod 0755 "$DECOY_BIN_DIR/decoy"

info "installed decoy $VERSION -> $DEST"
info "launcher: $DECOY_BIN_DIR/decoy"
case ":$PATH:" in
  *":$DECOY_BIN_DIR:"*) : ;;
  *) info "add $DECOY_BIN_DIR to your PATH, then restart your shell:"
     info "  export PATH=\"$DECOY_BIN_DIR:\$PATH\"" ;;
esac
info "done. run: decoy --version"
