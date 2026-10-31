#!/usr/bin/env bash
# Generate a CycloneDX SBOM (JSON) for the CLI bundle's pinned third-party runtime.
#
# Usage: scripts/release/sbom.sh [PINS] [OUT]
#   PINS  requirements-format pin list (default: requirements-certified.txt)
#   OUT   output file (default: sbom.cdx.json in the current directory)
#
# Input is requirements-certified.txt, the repo's only runtime-profile pin list: the
# exact third-party closure of the certified DP runtime that the bundle's wheels
# (decoy-engine, decoy-engine-native, decoy-cli) are installed alongside. It carries no
# hashes, so components have none. requirements-dev.lock is the dev profile and is refused.
#
# Tool: the upstream CycloneDX Python tool ("requirements" input), pinned and run through
# uvx, so pyproject.toml and the locks are never touched. The format is never hand-written.
#   https://cyclonedx-bom-tool.readthedocs.io/
#
# Reproducibility: --output-reproducible drops serialNumber and timestamp; SOURCE_DATE_EPOCH
# is unset so the environment cannot re-add a timestamp. Same pin list + same tool pins give
# the same bytes. Exit is non-zero, and OUT is not written, on any failure.
#
# Not signed, not published; release wiring lives in the release workflow.
set -euo pipefail

CYCLONEDX_BOM_VERSION="7.6.0"
CYCLONEDX_LIB_VERSION="11.12.0"
SPEC_VERSION="1.6"

root="$(cd "$(dirname "$0")/../.." && pwd)"
pins="${1:-$root/requirements-certified.txt}"
out="${2:-sbom.cdx.json}"

die() { echo "sbom.sh: $*" >&2; exit 1; }

[ -f "$pins" ] || die "pin list not found: $pins"
command -v uv >/dev/null 2>&1 || die "uv is required on PATH"

# Fail closed on anything but "name==version [; marker]", --hash lines and comments:
# index URLs, local paths, git or direct URLs would put infrastructure locations in the
# SBOM, which names public packages only.
bad="$(grep -vE '^[A-Za-z0-9][A-Za-z0-9._-]*==[^ ]+( ;.*)?( \\)?$|^[[:space:]]+--hash=sha256:[0-9a-f]{64}( \\)?$|^[[:space:]]*(#.*)?$' "$pins" || true)"
[ -z "$bad" ] || die "non-public source or unsupported requirement in $(basename "$pins") (SBOM covers public-index pins only)"

pyproject="$(cd "$(dirname "$pins")" && pwd)/pyproject.toml"
pyproject_args=()
[ -f "$pyproject" ] && pyproject_args=(--pyproject "$pyproject" --mc-type application)

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

env -u SOURCE_DATE_EPOCH uvx --quiet \
  --from "cyclonedx-bom==$CYCLONEDX_BOM_VERSION" \
  --with "cyclonedx-python-lib==$CYCLONEDX_LIB_VERSION" \
  cyclonedx-py requirements "$pins" "${pyproject_args[@]}" \
  --sv "$SPEC_VERSION" --output-reproducible --validate -o "$tmp/sbom.json" \
  || die "cyclonedx-py failed"

mkdir -p "$(dirname "$out")"
mv "$tmp/sbom.json" "$out"
echo "wrote $out" >&2
