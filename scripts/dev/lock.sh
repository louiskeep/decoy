#!/usr/bin/env bash
# Write or check requirements-dev.lock, the exact closure bootstrap.sh installs, and
# ci/ci-tools.lock, the hashed wheel-only closure of the CI linters in ci/ci-tools.in.
# Usage: scripts/dev/lock.sh [--check]
#   --check  exit 1 if a lock is missing or stale against its inputs (pyproject.toml /
#            lock_version.sh for the dev lock, ci/ci-tools.in for the tools lock)
# Inputs: pyproject [dev,otel], and the engine git ref (locked to its commit) and ruff pin that
# scripts/dev/lock_version.sh owns. Profile: CPython 3.10 on x86_64 Linux, with hashes.
# Stale means a re-resolve that prefers the current pins (pip-compile style) changes
# the file. pyproject.toml is never edited here.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT" || exit 2
LOCK=requirements-dev.lock
TOOLS_IN=ci/ci-tools.in
TOOLS_LOCK=ci/ci-tools.lock
PROFILE=scripts/dev/lock_version.sh
ENGINE_SPEC=$(bash "$PROFILE" --engine-spec)
RUFF_PIN=$(bash "$PROFILE" --ruff-pin)
fail() { echo "LOCK FAIL: $1" >&2; echo "  fix: $2" >&2; exit 1; }
[ -n "$ENGINE_SPEC" ] && [ -n "$RUFF_PIN" ] || fail "cannot read the engine spec or ruff pin from $PROFILE" "report it"
command -v uv >/dev/null || fail "uv not on PATH" "install uv, https://docs.astral.sh/uv/"

compile() {  # $1 output file (its pins are kept where still valid), rest: extra uv flags
  local out=$1; shift
  printf 'decoy-engine @ %s\nruff==%s\n' "$ENGINE_SPEC" "$RUFF_PIN" |
    uv pip compile -q pyproject.toml - --extra dev --extra otel --python-version 3.10 \
      --python-platform x86_64-unknown-linux-gnu --generate-hashes \
      --custom-compile-command scripts/dev/lock.sh "$@" -o "$out"
}

compile_tools() {  # same contract as compile; --no-build refuses any sdist-only package
  local out=$1; shift
  uv pip compile -q "$TOOLS_IN" --generate-hashes --no-build --python-version 3.12 \
    --python-platform x86_64-unknown-linux-gnu --custom-compile-command scripts/dev/lock.sh \
    "$@" -o "$out"
}

check_one() {  # $1 lock, $2 compile function, $3 what the lock is stale against
  local lock=$1 fn=$2 against=$3
  [ -f "$lock" ] || fail "$lock is missing" "git checkout $lock (regenerate only with scripts/dev/lock.sh)"
  cp "$lock" "$tmp/lock"
  # Offline first so a warm cache needs no network; a git tag still has to be resolved online.
  if ! "$fn" "$tmp/lock" --offline 2>/dev/null; then
    cp "$lock" "$tmp/lock"
    "$fn" "$tmp/lock" 2>"$tmp/err" ||
      fail "cannot re-resolve $lock: $(tail -n 1 "$tmp/err")" "check network and engine repo access, then rerun"
  fi
  diff -u "$lock" "$tmp/lock" >"$tmp/diff" ||
    fail "$lock is stale against $against: $(grep -c '^[-+][a-z]' "$tmp/diff") changed line(s)" \
      "do not edit the lock on a worker branch; report it (owner regenerates with scripts/dev/lock.sh)"
}

case ${1:-} in
  "") compile "$LOCK" || fail "uv pip compile failed" "read the uv error above"
      compile_tools "$TOOLS_LOCK" || fail "uv pip compile failed for $TOOLS_LOCK" "read the uv error above"
      echo "lock.sh: wrote $LOCK and $TOOLS_LOCK" >&2 ;;
  --check)
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/lock.XXXXXX"); trap 'rm -rf -- "$tmp"' EXIT
    check_one "$LOCK" compile "pyproject.toml / $PROFILE"
    check_one "$TOOLS_LOCK" compile_tools "$TOOLS_IN"
    echo "LOCK OK: $LOCK and $TOOLS_LOCK re-resolve unchanged from pyproject.toml, $PROFILE and $TOOLS_IN" ;;
  *) sed -n 2,6p "$0"; exit 2 ;;
esac
