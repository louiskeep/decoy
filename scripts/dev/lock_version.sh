#!/usr/bin/env bash
# Mirror of decoy-engine scripts/dev/lock_version.sh (CI-E1). Differences: it reads
# requirements-dev.lock, takes --python-minor (the CLI profile is a minor, not a patch), and adds
# --supported-minors and --engine-spec; the ruff pin and key dependencies live here too.
# Usage: scripts/dev/lock_version.sh <package>         first locked version of one package
#        scripts/dev/lock_version.sh --python-minor    the CPython minor of the lock profile
#        scripts/dev/lock_version.sh --supported-minors  the minors CI and bootstrap accept
#        scripts/dev/lock_version.sh --engine-spec     the engine git spec every install uses
#        scripts/dev/lock_version.sh --ruff-pin        the ruff version the lock carries
#        scripts/dev/lock_version.sh --check [pkg...]  installed vs locked (default: key deps)
# --check looks in $DECOY_VENV, else $UV_PROJECT_ENVIRONMENT, else `python` on PATH, and exits 1 on
# any difference. Plain awk and stdlib Python: it runs before any dependency exists.
set -euo pipefail

PROFILE_PYTHON_MINOR=3.10
SUPPORTED_MINORS="3.10 3.11 3.12"
ENGINE_SPEC="git+https://github.com/louiskeep/decoy-engine@v0.22.0"
RUFF_PIN=0.15.14
KEY_DEPS="duckdb pyarrow polars pandas pydantic pydantic-core typer ruff"
OUTSIDE_LOCK="decoy-cli,decoy-engine-native"   # installed by bootstrap, not in the lock

root=$(cd "$(dirname "$0")/../.." && pwd)
lock=$root/requirements-dev.lock

locked() { awk -v n="$1" '{ split($1, a, "=="); if (a[2] != "" && a[1] == n) { print a[2]; exit } }' "$lock"; }

check() {
  local py=python venv=${DECOY_VENV:-${UV_PROJECT_ENVIRONMENT:-}}
  if [ -n "$venv" ]; then py=$venv/bin/python; fi
  if [ "$(locked ruff)" != "$RUFF_PIN" ]; then
    echo "ruff pin $RUFF_PIN differs from requirements-dev.lock ($(locked ruff))" >&2
    return 1
  fi
  # shellcheck disable=SC2086  # KEY_DEPS is a space-separated word list on purpose
  [ $# -gt 0 ] || set -- $KEY_DEPS
  "$py" "$root/scripts/dev/_lock_verify.py" "$lock" "$OUTSIDE_LOCK" "$@"
}

case ${1:-} in
  --python-minor) echo "$PROFILE_PYTHON_MINOR" ;;
  --supported-minors) echo "$SUPPORTED_MINORS" ;;
  --engine-spec) echo "$ENGINE_SPEC" ;;
  --ruff-pin) echo "$RUFF_PIN" ;;
  --check) shift; check "$@" ;;
  "" | -*) sed -n 5,11p "$0" >&2; exit 2 ;;
  *) locked "$1" ;;
esac
