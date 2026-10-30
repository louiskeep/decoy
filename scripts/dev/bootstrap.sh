#!/usr/bin/env bash
# Make the venv match requirements-dev.lock exactly (ci.yml's pytest + ruff closure,
# the engine locked to the commit of its pinned git tag), install the CLI editable
# with --no-deps on top, then print the environment header.
# Usage: scripts/dev/bootstrap.sh [--check]
#   --check  verify only, never install (gates.sh runs this as its env step)
# Venv: $DECOY_VENV, else ./.venv. Exits non-zero on any mismatch, a missing lock or a
# lock stale against pyproject.toml; there is no fallback install path.
set -uo pipefail

REPO_NAME=decoy
DIST=decoy-cli                 # installed editable outside the lock
PY_SERIES=3.10                 # ci.yml ruff job and the lowest pytest matrix entry
KEY_DEPS=(duckdb pyarrow polars pandas typer ruff)
WF=.github/workflows/ci.yml
LOCK=requirements-dev.lock

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT" || exit 2
VENV=${DECOY_VENV:-$ROOT/.venv}
PY=$VENV/bin/python
CHECK=0
case ${1:-} in
  --check) CHECK=1 ;;
  "") ;;
  *) sed -n 5,8p "$0"; exit 2 ;;
esac

die() { echo "BOOTSTRAP FAIL: $1" >&2; echo "  fix: $2" >&2; exit 1; }
# The pytest job's engine spec, e.g. git+https://github.com/louiskeep/decoy-engine@v0.15.1
ENGINE_SPEC=$(sed -n 's/^ *pip install "\(git+https:[^"]*decoy-engine@[^"]*\)"$/\1/p' "$WF" | head -n 1)
ENGINE_REF=${ENGINE_SPEC##*@}
PYPROJECT_PIN=$(sed -n 's/^ *"decoy-engine==\([^"]*\)",.*/\1/p' pyproject.toml)
[ -n "$ENGINE_SPEC" ] || die "cannot read the engine spec from $WF" "report it"
command -v uv >/dev/null || die "uv not on PATH" "install uv, https://docs.astral.sh/uv/"
[ -f "$LOCK" ] || die "$LOCK is missing" "git checkout $LOCK (regenerate only with scripts/dev/lock.sh)"

ERRORS=()
err() { ERRORS+=("$1|$2"); }
report() {
  for e in "${ERRORS[@]}"; do
    echo "BOOTSTRAP FAIL: ${e%%|*}" >&2
    echo "  fix: ${e#*|}" >&2
  done
  exit 1
}
FIX="scripts/dev/bootstrap.sh"

lock_out=$(bash scripts/dev/lock.sh --check 2>&1) ||
  err "$(sed -n 's/^LOCK FAIL: //p' <<<"$lock_out" | head -n 1)" "do not edit the lock on a worker branch; report it"

if [ $CHECK = 0 ]; then
  [ ${#ERRORS[@]} -eq 0 ] || report   # never install from a stale lock
  if [ ! -x "$PY" ]; then
    uv venv -q --python "$PY_SERIES" "$VENV" || die "venv creation failed" "install CPython $PY_SERIES (uv python install $PY_SERIES)"
  fi
  echo "bootstrap: uv pip sync $LOCK && uv pip install --no-deps -e ." >&2
  uv pip sync -q --python "$PY" "$LOCK" >&2 || die "uv pip sync $LOCK failed" "read the uv error above"
  uv pip install -q --python "$PY" --no-deps -e . >&2 || die "CLI install failed" "read the uv error above"
fi
[ -x "$PY" ] || die "no venv at $VENV" "$FIX"

echo "== $REPO_NAME environment =="
echo "venv:       $VENV"
py_have=$("$PY" -c 'import platform; print(platform.python_version())')
echo "python:     $py_have (ci.yml expects $PY_SERIES.x)"
[[ $py_have == "$PY_SERIES".* ]] || err "python is $py_have, expected $PY_SERIES.x" "rm -rf $VENV && $FIX"
echo "lock:       $LOCK sha256 $(sha256sum "$LOCK" | cut -c1-16) ($(grep -q '^LOCK OK' <<<"$lock_out" && echo fresh || echo NOT fresh))"

info=$("$PY" - <<'PY'
import importlib.metadata as m, json
try:
    vcs = json.loads(m.distribution("decoy-engine").read_text("direct_url.json") or "{}")
    print(m.version("decoy-engine"), vcs.get("vcs_info", {}).get("commit_id", "none"))
    import decoy_engine
    print(decoy_engine.__file__)
except Exception as exc:
    print("absent none")
    print(f"unimportable:{type(exc).__name__}")
PY
)
read -r eng_ver eng_sha <<<"$(head -n 1 <<<"$info")"
eng_file=$(sed -n 2p <<<"$info")
lock_sha=$(sed -n 's/^decoy-engine @ git+.*@\([0-9a-f]\{40\}\)$/\1/p' "$LOCK")
mark=OK
[ "$eng_ver" = "$PYPROJECT_PIN" ] && [ "$eng_sha" = "$lock_sha" ] || mark=MISMATCH
printf '%-12s installed %-10s pin %-10s %s\n' decoy-engine "$eng_ver" "$PYPROJECT_PIN" "$mark"
echo "             commit $eng_sha (lock pins $lock_sha; ci.yml installs @$ENGINE_REF)"
[ "$eng_ver" = "$PYPROJECT_PIN" ] ||
  err "decoy-engine installed $eng_ver but pyproject pins $PYPROJECT_PIN" "$FIX"
[ "v$PYPROJECT_PIN" = "$ENGINE_REF" ] ||
  err "pyproject pins $PYPROJECT_PIN but ci.yml installs @$ENGINE_REF" "report it; do not repin on a worker branch"

diffs=$(mktemp "${TMPDIR:-/tmp}/lockdiff.XXXXXX")
"$PY" scripts/dev/_lock_verify.py "$LOCK" "$DIST,decoy-engine-native" "${KEY_DEPS[@]}" 2>"$diffs"
# uv pip sync leaves venv seed packages (pip, setuptools) alone; only a fresh unseeded venv drops them.
while read -r d; do
  case $d in *"but not in $LOCK") err "$d" "rm -rf $VENV && $FIX" ;; *) err "$d" "$FIX (runs uv pip sync $LOCK)" ;; esac
done <"$diffs"
rm -f -- "$diffs"

abi_want=$(sed -n 's/^_EXPECTED_ABI_VERSION = "\(.*\)"/\1/p' \
  "$(dirname "$eng_file")/execution/native/_crypto_ext.py" 2>/dev/null)
abi_have=$("$PY" -c 'from decoy_engine_native import _kernel; print(_kernel.abi_version())' 2>/dev/null)
if [ -z "$abi_have" ]; then
  echo "native:     companion NOT installed; engine expects ${abi_want:-unknown} (the CLI does not need it)"
elif [ "$abi_have" = "$abi_want" ]; then
  echo "native:     companion installed, ABI $abi_have; engine expects $abi_want  OK"
else
  echo "native:     companion installed, ABI $abi_have; engine expects $abi_want  MISMATCH"
  err "native companion ABI $abi_have, engine expects $abi_want" "uninstall decoy-engine-native or rebuild it at @$ENGINE_REF"
fi

dep_out=$(uv pip check --python "$PY" 2>&1) || err "uv pip check: $(tail -n 1 <<<"$dep_out")" "$FIX"
echo "deps check: $(tail -n 1 <<<"$dep_out")"

[ ${#ERRORS[@]} -eq 0 ] || report
echo "RESULT:     OK, environment matches $LOCK and the engine pins"
