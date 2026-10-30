#!/usr/bin/env bash
# Build the venv the way ci.yml's pytest job does (engine from its pinned git
# tag, then the CLI editable with [dev]), then print the environment header.
# Usage: scripts/dev/bootstrap.sh [--check]
#   --check  verify only, never install (gates.sh runs this as its env step)
# Venv: $DECOY_VENV, else ./.venv. Exits non-zero on any mismatch; no fallback.
set -uo pipefail
export PIP_DISABLE_PIP_VERSION_CHECK=1

REPO_NAME=decoy
PY_SERIES=3.10                 # ci.yml ruff job and the lowest pytest matrix entry
KEY_DEPS=(duckdb pyarrow polars pandas typer)
WF=.github/workflows/ci.yml

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT" || exit 2
VENV=${DECOY_VENV:-$ROOT/.venv}
PY=$VENV/bin/python
CHECK=0
case ${1:-} in
  --check) CHECK=1 ;;
  "") ;;
  *) sed -n 4,6p "$0"; exit 2 ;;
esac

die() { echo "BOOTSTRAP FAIL: $1" >&2; echo "  fix: $2" >&2; exit 1; }
# The pytest job's engine spec, e.g. git+https://github.com/louiskeep/decoy-engine@v0.15.1
ENGINE_SPEC=$(sed -n 's/^ *pip install "\(git+https:[^"]*decoy-engine@[^"]*\)"$/\1/p' "$WF" | head -n 1)
ENGINE_REF=${ENGINE_SPEC##*@}
RUFF_PIN=$(sed -n 's/^ *run: pip install "ruff==\([^"]*\)"$/\1/p' "$WF" | head -n 1)
PYPROJECT_PIN=$(sed -n 's/^ *"decoy-engine==\([^"]*\)",.*/\1/p' pyproject.toml)
[ -n "$ENGINE_SPEC" ] && [ -n "$RUFF_PIN" ] || die "cannot read the engine spec or ruff pin from $WF" "report it"

if [ $CHECK = 0 ]; then
  if [ ! -x "$PY" ]; then
    base=$(command -v "python$PY_SERIES" || uv python find "$PY_SERIES" 2>/dev/null) ||
      die "no python$PY_SERIES found" "install CPython $PY_SERIES (or uv python install $PY_SERIES)"
    "$base" -m venv "$VENV" || die "venv creation failed" "see the error above"
  fi
  echo "bootstrap: pip install $ENGINE_SPEC && pip install -e .[dev] ruff==$RUFF_PIN" >&2
  "$PY" -m pip install -q "$ENGINE_SPEC" >&2 || die "engine install failed" "see pip output above"
  "$PY" -m pip install -q -e ".[dev]" "ruff==$RUFF_PIN" >&2 || die "CLI install failed" "see pip output above"
fi
[ -x "$PY" ] || die "no venv at $VENV" "scripts/dev/bootstrap.sh"

ERRORS=()
err() { ERRORS+=("$1|$2"); }
FIX="scripts/dev/bootstrap.sh"

echo "== $REPO_NAME environment =="
echo "venv:       $VENV"
py_have=$("$PY" -c 'import platform; print(platform.python_version())')
echo "python:     $py_have (ci.yml expects $PY_SERIES.x)"
[[ $py_have == "$PY_SERIES".* ]] || err "python is $py_have, expected $PY_SERIES.x" "rm -rf $VENV && $FIX"

info=$("$PY" - decoy-engine "${KEY_DEPS[@]}" ruff <<'PY'
import importlib.metadata as m, json, sys
for name in sys.argv[1:]:
    try:
        print(name, m.version(name))
    except m.PackageNotFoundError:
        print(name, "absent")
try:
    vcs = json.loads(m.distribution("decoy-engine").read_text("direct_url.json") or "{}")
    info = vcs.get("vcs_info", {})
    print("engine_ref", info.get("requested_revision", "none"), info.get("commit_id", "none"))
    import decoy_engine
    print("engine_file", decoy_engine.__file__)
except Exception as exc:
    print("engine_ref", f"unreadable:{type(exc).__name__}", "none")
PY
)
have() { awk -v n="$1" '$1 == n { print $2 }' <<<"$info"; }
eng_ver=$(have decoy-engine)
eng_ref=$(have engine_ref)
eng_sha=$(awk '$1 == "engine_ref" { print $3 }' <<<"$info")
eng_file=$(have engine_file)
mark=OK
[ "$eng_ver" = "$PYPROJECT_PIN" ] && [ "$eng_ref" = "$ENGINE_REF" ] || mark=MISMATCH
printf '%-12s installed %-10s pin %-10s %s\n' decoy-engine "$eng_ver" "$PYPROJECT_PIN" "$mark"
echo "             from git ref $eng_ref (ci.yml installs @$ENGINE_REF), commit $eng_sha"
[ "$eng_ver" = "$PYPROJECT_PIN" ] ||
  err "decoy-engine installed $eng_ver but pyproject pins $PYPROJECT_PIN" "$FIX"
[ "$eng_ref" = "$ENGINE_REF" ] || err "engine installed from ref $eng_ref, ci.yml uses @$ENGINE_REF" "$FIX"
[ "v$PYPROJECT_PIN" = "$ENGINE_REF" ] ||
  err "pyproject pins $PYPROJECT_PIN but ci.yml installs @$ENGINE_REF" "report it; do not repin on a worker branch"

got=$(have ruff)
printf '%-12s installed %-10s pin %-10s %s\n' ruff "$got" "$RUFF_PIN" "$([ "$got" = "$RUFF_PIN" ] && echo OK || echo MISMATCH)"
[ "$got" = "$RUFF_PIN" ] || err "ruff installed $got but ci.yml pins $RUFF_PIN" "$FIX"
for dep in "${KEY_DEPS[@]}"; do
  printf '%-12s installed %-10s (no lock: resolved by pip at bootstrap time)\n' "$dep" "$(have "$dep")"
done

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

pip_out=$("$PY" -m pip check 2>&1) || err "pip check: $pip_out" "$FIX"
echo "pip check:  $(head -n 1 <<<"$pip_out")"

if [ ${#ERRORS[@]} -gt 0 ]; then
  for e in "${ERRORS[@]}"; do
    echo "BOOTSTRAP FAIL: ${e%%|*}" >&2
    echo "  fix: ${e#*|}" >&2
  done
  exit 1
fi
echo "RESULT:     OK, engine matches the pyproject and ci.yml pin"
