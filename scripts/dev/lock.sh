#!/usr/bin/env bash
# Write or check requirements-dev.lock, the exact closure bootstrap.sh installs.
# Usage: scripts/dev/lock.sh [--check]
#   --check  exit 1 if the lock is missing or stale against pyproject.toml / ci.yml
# Inputs mirror ci.yml: pyproject [dev], the pytest job's engine git ref (locked to its
# commit) and the ruff job's pin. Profile: CPython 3.10 on x86_64 Linux, with hashes.
# Stale means a re-resolve that prefers the current pins (pip-compile style) changes
# the file. pyproject.toml is never edited here.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT" || exit 2
LOCK=requirements-dev.lock
WF=.github/workflows/ci.yml
ENGINE_SPEC=$(sed -n 's/^ *pip install "\(git+https:[^"]*decoy-engine@[^"]*\)"$/\1/p' "$WF" | head -n 1)
RUFF_PIN=$(sed -n 's/^ *run: pip install "ruff==\([^"]*\)"$/\1/p' "$WF" | head -n 1)
fail() { echo "LOCK FAIL: $1" >&2; echo "  fix: $2" >&2; exit 1; }
[ -n "$ENGINE_SPEC" ] && [ -n "$RUFF_PIN" ] || fail "cannot read the engine spec or ruff pin from $WF" "report it"
command -v uv >/dev/null || fail "uv not on PATH" "install uv, https://docs.astral.sh/uv/"

compile() {  # $1 output file (its pins are kept where still valid), rest: extra uv flags
  local out=$1; shift
  printf 'decoy-engine @ %s\nruff==%s\n' "$ENGINE_SPEC" "$RUFF_PIN" |
    uv pip compile -q pyproject.toml - --extra dev --python-version 3.10 \
      --python-platform x86_64-unknown-linux-gnu --generate-hashes \
      --custom-compile-command scripts/dev/lock.sh "$@" -o "$out"
}

case ${1:-} in
  "") compile "$LOCK" || fail "uv pip compile failed" "read the uv error above"
      echo "lock.sh: wrote $LOCK" >&2 ;;
  --check)
    [ -f "$LOCK" ] || fail "$LOCK is missing" "git checkout $LOCK (regenerate only with scripts/dev/lock.sh)"
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/lock.XXXXXX"); trap 'rm -rf -- "$tmp"' EXIT
    cp "$LOCK" "$tmp/lock"
    # Offline first so a warm cache needs no network; a git tag still has to be resolved online.
    if ! compile "$tmp/lock" --offline 2>/dev/null; then
      cp "$LOCK" "$tmp/lock"
      compile "$tmp/lock" 2>"$tmp/err" ||
        fail "cannot re-resolve $LOCK: $(tail -n 1 "$tmp/err")" "check network and engine repo access, then rerun"
    fi
    diff -u "$LOCK" "$tmp/lock" >"$tmp/diff" ||
      fail "$LOCK is stale against pyproject.toml / $WF: $(grep -c '^[-+][a-z]' "$tmp/diff") changed line(s)" \
        "do not edit the lock on a worker branch; report it (owner regenerates with scripts/dev/lock.sh)"
    echo "LOCK OK: $LOCK re-resolves unchanged from pyproject.toml and $WF" ;;
  *) sed -n 2,4p "$0"; exit 2 ;;
esac
