#!/usr/bin/env bash
# Run the local gates in CI order and print an EVIDENCE block to paste.
# Usage: scripts/dev/gates.sh [--keep-going] [--baseline] [--baseline-file FILE]
#        [--write-baseline FILE] [--full] [--steps LIST] [test paths...]
#   --keep-going  run every step even after a failure (default: stop at the first)
#   --baseline    rerun every step on origin/main in a temporary detached worktree, with the
#                 SAME venv, and diff the failures of every step (test ids; mypy/ruff error
#                 lines). Implies --keep-going. Fails only on branch-only failures: a step main
#                 passes, a crash or kill, an unidentified failure, or more of a failure than
#                 main has. Failures main shares are not the branch's.
#   --baseline-file FILE
#                 with --baseline (implied): do NOT rerun origin/main. Load the stored
#                 failing-id baseline FILE, run only the branch pass, then report new
#                 failing ids (exit 1), baseline ids that now pass, and the collected
#                 count delta. Exit 2 before running when FILE is for another repo, was
#                 written in a different run mode (workers, dist, platform, order), is
#                 malformed, or is behind origin/main in anything but Markdown or generated
#                 diagrams that no test reads. Fails unless a whole-suite tests step finished
#                 with collected > 0, the branch skips no more tests than the baseline did,
#                 and it collects no fewer tests than the baseline beyond the test ids in
#                 test files the branch deleted. A missing totals line, or one that
#                 disagrees with the JUnit failure count, exits 3.
#   --write-baseline FILE
#                 after a full-suite run (--full or `tests`, steps include tests, all
#                 steps ran, pytest exit 0 or 1, JUnit with collected > 0) write {repo,
#                 main_sha, head_sha, collected, skipped, failing, workers, dist, platform,
#                 order, order_seconds, file_seconds} to FILE; refused for a selection, and
#                 unless HEAD equals origin/main with a clean tree. Needs origin/main. A
#                 failing id with a memory address in it is refused (it never matches again).
#                 The exit code is still 1 after a successful write when main has known failures.
#   --steps LIST  comma list from: env,ruff,format,mypy,sentry,tests (default: all)
#   --full        run the whole `tests` directory (same as passing `tests`)
#   The CLI suite runs serial in collection order; there is no worker or order option.
#   test paths    default: tests touching files changed against origin/main. That is a
#                 SELECTION, not the full suite; the header says so. Use --full (or `tests`).
set -uo pipefail

# Repo config. Mirrors .github/workflows/ci.yml (ruff and pytest jobs).
REPO_NAME=decoy
RUFF_PATHS=(src tests)
MYPY_ARGS=()           # ci.yml has no mypy gate; the step reports SKIP
FORMAT_GATE=0          # ci.yml runs ruff check only (main is not format-clean); SKIP
# test_sentry_manifest.py fails when a file in its SENTRIES manifest is not collected here
SENTRY_PATHS=(
  tests/sentry
  tests/unit/test_cli_surface.py
  tests/unit/test_surface_docs_consistency.py
  tests/unit/test_no_dead_command_strings.py
)
PYTEST_ARGS=()
SRC_MATCH='src/*.py'   # changed files that map to a dotted module
SRC_STRIP='src/'       # prefix removed before turning a path into a module
PYPATH_DIRS=(src)
IMPORT_PKG=decoy
# Files a stored baseline may be behind main by without going stale, besides Markdown: output
# that .github/workflows/regen-diagrams.yml commits to main after a merge. Like Markdown, a file
# here still makes the baseline stale when a test under tests/ names it.
GENERATED_UNREAD_GLOBS=('docs/diagrams/*.svg')
# Directories a test reads by walking them. The CLI has none (tests/sentry/test_baseline_registry.py
# walks docs/ for json and toml only, and it is a sentry, so DOC_WALK_GUARDS covers it).
DOC_WALK_ROOTS=()
# Any stored failing id under a sentry path makes every main move stale, because a Markdown fix on
# main could hide a re-break on the branch. Derived from SENTRY_PATHS so there is one list.
DOC_WALK_GUARDS=(${SENTRY_PATHS[@]+"${SENTRY_PATHS[@]}"})

ROOT=$(git rev-parse --show-toplevel) || exit 2
VENV=${DECOY_VENV:-$ROOT/.venv}
BIN=$VENV/bin
KEEP=0 BASELINE=0 FULL=0 BASEFILE='' WRITEBASE='' STEPS=env,ruff,format,mypy,sentry,tests PATHS=()
while [ $# -gt 0 ]; do
  case $1 in
    --keep-going) KEEP=1 ;;
    --baseline) BASELINE=1 ;;
    --full) FULL=1 ;;
    --baseline-file|--write-baseline)
      # A missing operand, or another flag where the file belongs, is a usage error: swallowing
      # it would turn `--write-baseline --full` into a baseline file named --full.
      case ${2:-} in ''|-*) echo "gates: $1 needs a file operand" >&2; exit 2 ;; esac
      if [ "$1" = --baseline-file ]; then BASEFILE=$2; BASELINE=1; else WRITEBASE=$2; fi
      shift ;;
    --steps) STEPS=${2:-}; shift ;;
    -h|--help) awk 'NR > 1 { if (!/^#/) exit; print }' "$0"; exit 0 ;;
    -*) echo "gates: unknown flag $1" >&2; exit 2 ;;
    *) PATHS+=("$1") ;;
  esac
  shift
done
# A baseline verdict compares every step, so a step skipped after an early failure can never
# read as shared with main.
if [ $BASELINE = 1 ]; then KEEP=1; fi
[ -x "$BIN/python" ] || { echo "gates: no venv at $VENV; run scripts/dev/bootstrap.sh" >&2; exit 2; }
# Worker count for the tests step, recorded in a stored baseline's run mode. The reporter owns the
# answer (always 1 here); only its stdout is captured, so its diagnostics reach the terminal.
WORKERS_RC=0
WORKERS_LINE=$("$BIN/python" "$ROOT/scripts/dev/_gates_report.py" --workers) || WORKERS_RC=$?
if [ $WORKERS_RC != 0 ]; then
  echo "gates: FAIL: no complete EVIDENCE block (the reporter failed before the run)" >&2; exit 3
fi
WORKERS=${WORKERS_LINE%% *}
WORKERS_WHY=${WORKERS_LINE#* }
OUT=$(mktemp -d "${TMPDIR:-/tmp}/gates.XXXXXX")
WT=$OUT/baseline-tree
MBT=$OUT/merge-base-tree
STORED=$OUT/stored-baseline.json
# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  local d
  for d in "$WT" "$MBT"; do [ -d "$d" ] && git -C "$ROOT" worktree remove --force "$d" 2>/dev/null; done
  return 0
}
trap cleanup EXIT

changed_tests() {
  local base f mod
  base=$(git -C "$ROOT" merge-base origin/main HEAD) || return 1
  { git -C "$ROOT" diff --name-only "$base"; git -C "$ROOT" ls-files --others --exclude-standard; } |
    sort -u | while read -r f; do
      [ -f "$ROOT/$f" ] || continue
      # shellcheck disable=SC2254  # SRC_MATCH is a glob on purpose
      case $f in
        tests/*test_*.py) echo "$f" ;;
        $SRC_MATCH)
          mod=${f#"$SRC_STRIP"}; mod=${mod%.py}; mod=${mod%/__init__}; mod=${mod//\//.}
          (cd "$ROOT" && grep -rlE --include='test_*.py' "${mod//./\\.}([^A-Za-z0-9_]|\$)" tests) ;;
      esac
    done | sort -u
}

if [ $FULL = 1 ] && [ ${#PATHS[@]} -eq 0 ]; then
  PATHS=(tests)
  SELECTION="full suite (tests)"
elif [ ${#PATHS[@]} -eq 0 ]; then
  if ! git -C "$ROOT" rev-parse -q --verify origin/main >/dev/null; then
    echo "gates: origin/main missing; run: git fetch origin main" >&2; exit 2
  fi
  # No read-into-array builtin: the Mac runner has bash 3.2.
  SELECTED=$(changed_tests)
  while IFS= read -r p; do [ -n "$p" ] && PATHS+=("$p"); done <<EOT
$SELECTED
EOT
  SELECTION="changed vs origin/main: ${#PATHS[@]} test file(s)"
else
  SELECTION="explicit: ${PATHS[*]+${PATHS[*]}}"
fi

MAIN_SHA=$(git -C "$ROOT" rev-parse -q --verify origin/main || true)
WHOLE_SUITE=0
[ ${#PATHS[@]} -eq 1 ] && [ "${PATHS[0]}" = tests ] && WHOLE_SUITE=1
if [ -n "$WRITEBASE" ]; then
  # Refuse before spending the run on a result that could not be stored.
  if [ $WHOLE_SUITE = 0 ] || [[ ",$STEPS," != *,tests,* ]]; then
    echo "gates: --write-baseline refused: this run is a selection, not the whole suite (needs --full or the path 'tests', and the tests step)" >&2; exit 2
  fi
  [ -n "$MAIN_SHA" ] || { echo "gates: --write-baseline needs origin/main; run: git fetch origin main" >&2; exit 2; }
  # A baseline describes origin/main, so only a clean checkout of exactly that commit may store one.
  HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)
  if [ "$HEAD_SHA" != "$MAIN_SHA" ] || [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
    echo "gates: --write-baseline refused: HEAD must equal origin/main ($MAIN_SHA) and the tree must be clean" >&2; exit 2
  fi
fi

# 0 when the stored baseline (main_sha $1) is behind origin/main in something a test could read.
# A main move is harmless only if every changed path is Markdown or a GENERATED_UNREAD_GLOBS file
# outside src/ and tests/, outside DOC_WALK_ROOTS, and no file under tests/ (helpers included)
# names it. Reads the copy $STORED, never the original.
baseline_is_stale() {
  local changed f root g harmless
  git -C "$ROOT" cat-file -e "$1^{commit}" 2>/dev/null || { echo "stored main_sha $1 is not in this repository"; return 0; }
  changed=$(git -C "$ROOT" diff --name-only --no-renames "$1" "$MAIN_SHA") || { echo "could not diff $1 against origin/main"; return 0; }
  if [ -n "$changed" ] && "$BIN/python" "$ROOT/scripts/dev/_gates_report.py" --stored-failing-under "$STORED" ${DOC_WALK_GUARDS[@]+"${DOC_WALK_GUARDS[@]}"}; then
    echo "main moved and the stored failing list holds a sentry failure that a Markdown change on main could have hidden"; return 0
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    harmless=0
    case $f in
      src/*|tests/*) ;;
      *.md) harmless=1 ;;
      *)
        for g in ${GENERATED_UNREAD_GLOBS[@]+"${GENERATED_UNREAD_GLOBS[@]}"}; do
          # shellcheck disable=SC2254  # GENERATED_UNREAD_GLOBS entries are globs on purpose
          case $f in $g) harmless=1 ;; esac
        done ;;
    esac
    [ $harmless = 1 ] || { echo "main changed $f"; return 0; }
    for root in ${DOC_WALK_ROOTS[@]+"${DOC_WALK_ROOTS[@]}"}; do
      case $f in "$root"/*) echo "main changed $f, which a sentry walks"; return 0 ;; esac
    done
    if grep -rlFq -- "${f##*/}" "$ROOT/tests"; then echo "main changed $f, which a test names"; return 0; fi
  done <<EOT
$changed
EOT
  return 1
}

if [ -n "$BASEFILE" ]; then
  [ -f "$BASEFILE" ] || { echo "gates: baseline file not found: $BASEFILE" >&2; exit 2; }
  # Copy first, then check and read only the copy: the file the gate checks is the file it uses,
  # even when something rewrites the original while the suite runs.
  cp "$BASEFILE" "$STORED" || { echo "gates: could not copy the baseline file: $BASEFILE" >&2; exit 2; }
  stored_sha=$("$BIN/python" "$ROOT/scripts/dev/_gates_report.py" --check-stored "$STORED" "$REPO_NAME" "$WORKERS" "$ROOT") || exit 2
  [ -n "$MAIN_SHA" ] || { echo "gates: --baseline-file needs origin/main; run: git fetch origin main" >&2; exit 2; }
  if [ "$MAIN_SHA" != "$stored_sha" ]; then
    if reason=$(baseline_is_stale "$stored_sha"); then
      echo "gates: the stored baseline (main_sha $stored_sha) is stale against origin/main $MAIN_SHA: $reason; rewrite it with --write-baseline" >&2; exit 2
    fi
  fi
fi

pypath() { local d out=""; for d in ${PYPATH_DIRS[@]+"${PYPATH_DIRS[@]}"}; do out="$out${out:+:}$1/$d"; done; echo "$out"; }

run_steps() {  # $1 label, $2 tree
  local label=$1 tree=$2 name rc stop=0 p cmd shown tests=() pyt
  : >"$OUT/$label.steps"
  for name in ${STEPS//,/ }; do
    local junit=(-p no:cacheprovider -q -rfE -o junit_family=xunit1 "--junitxml=$OUT/$label-$name.xml" ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"})
    case $name in
      env) cmd=(bash "$ROOT/scripts/dev/bootstrap.sh" --check) ;;
      ruff) cmd=("$BIN/ruff" check ${RUFF_PATHS[@]+"${RUFF_PATHS[@]}"}) ;;
      format) cmd=("$BIN/ruff" format --check ${RUFF_PATHS[@]+"${RUFF_PATHS[@]}"}) ;;
      mypy) cmd=("$BIN/mypy" ${MYPY_ARGS[@]+"${MYPY_ARGS[@]}"}) ;;
      # ratchet_check first (baselines never grow); skipped in trees that predate it (the baseline worktree)
      sentry)
        cmd=(bash -c 'if [ -f scripts/dev/ratchet_check.py ]; then "$0" scripts/dev/ratchet_check.py || exit 1; fi; exec "$0" -m pytest "$@"' "$BIN/python" ${junit[@]+"${junit[@]}"} ${SENTRY_PATHS[@]+"${SENTRY_PATHS[@]}"}) ;;
      tests)
        tests=(); for p in ${PATHS[@]+"${PATHS[@]}"}; do [ -e "$tree/${p%%::*}" ] && tests+=("$p"); done
        pyt=("$BIN/python" -m pytest)
        # A stored or compared baseline must come from the whole suite: ignore selections
        # smuggled in through PYTEST_ADDOPTS, PYTEST_PLUGINS or the config's addopts (this
        # script's own args stay, they are part of the junit array).
        if [ -n "$WRITEBASE$BASEFILE" ]; then
          pyt=(env -u PYTEST_ADDOPTS -u PYTEST_PLUGINS PY_COLORS=0 NO_COLOR=1 "$BIN/python" -m pytest -o addopts= --color=no)
        fi
        cmd=(${pyt[@]+"${pyt[@]}"} ${junit[@]+"${junit[@]}"} ${tests[@]+"${tests[@]}"}) ;;
      *) echo "gates: unknown step $name" >&2; exit 2 ;;
    esac
    if [ $stop = 1 ]; then rc=-2
    elif [ "$name" = tests ] && [ ${#tests[@]} -eq 0 ]; then rc=-1; cmd=("(no test paths present)")
    elif [ "$name" = env ] && [ "$label" = baseline ]; then rc=-1; cmd=("(same venv as branch)")
    elif [ "$name" = mypy ] && [ ${#MYPY_ARGS[@]} -eq 0 ]; then rc=-1; cmd=("(no mypy gate in ci.yml)")
    elif [ "$name" = format ] && [ $FORMAT_GATE = 0 ]; then rc=-1; cmd=("(no format gate in ci.yml)")
    else
      echo "gates: [$label] $name ..." >&2
      (cd "$tree" && PYTHONPATH=$(pypath "$tree") ${cmd[@]+"${cmd[@]}"}) >"$OUT/$label-$name.log" 2>&1
      rc=$?
      if [ $rc != 0 ]; then
        tail -n 15 "$OUT/$label-$name.log" | sed "s/^/  $label $name| /" >&2
        [ $KEEP = 1 ] || stop=1
      fi
    fi
    [ $rc = -1 ] && shown=${cmd[*]+${cmd[*]}} || shown=$(printf '%q ' ${cmd[@]+"${cmd[@]}"})
    printf '%s\t%s\t%s\n' "$name" "$rc" "$shown" >>"$OUT/$label.steps"
  done
}

ver() { local v; v=$("$@" 2>/dev/null | head -n 1); echo "${v:-not installed}"; }
{
  echo "repo:       $REPO_NAME @ $(git -C "$ROOT" rev-parse HEAD) ($(git -C "$ROOT" branch --show-current))"
  echo "dirty:      $(git -C "$ROOT" status --porcelain | wc -l) path(s) uncommitted"
  echo "origin/main $(git -C "$ROOT" rev-parse -q --verify origin/main || echo missing)"
  echo "venv:       $VENV"
  echo "python:     $(ver "$BIN/python" --version)"
  echo "ruff:       $(ver "$BIN/ruff" --version)"
  echo "mypy:       $(ver "$BIN/mypy" --version)"
  echo "pytest:     $(ver "$BIN/python" -m pytest --version)"
  echo "steps:      $STEPS (keep-going=$KEEP)"
  echo "workers:    $WORKERS ($WORKERS_WHY)"
  echo "test paths: $SELECTION"
} >"$OUT/meta"

run_steps branch "$ROOT"
if [ -n "$BASEFILE" ]; then
  {
    echo "baseline:   stored file $BASEFILE (main_sha $stored_sha); origin/main NOT rerun"
    echo "run mode:   workers=$WORKERS, collection order (the baseline was written in the same mode)"
    if [ "$MAIN_SHA" != "$stored_sha" ]; then
      echo "NOTE:       origin/main is $MAIN_SHA; main moved only in Markdown or generated diagrams no test reads"
    fi
  } >>"$OUT/meta"
elif [ $BASELINE = 1 ]; then
  git -C "$ROOT" worktree add -q --detach "$WT" origin/main || exit 2
  {
    echo "baseline:   origin/main @ $(git -C "$WT" rev-parse HEAD) in a detached worktree, same venv and lock as branch"
    echo "            $IMPORT_PKG imported from: $(cd "$WT" && PYTHONPATH=$(pypath "$WT") "$BIN/python" "$ROOT/scripts/dev/_gates_report.py" --import-origin "$IMPORT_PKG" 2>&1 | tail -n 1)"
  } >>"$OUT/meta"
  run_steps baseline "$WT"
fi
echo "logs:       $OUT" >>"$OUT/meta"

REPORT_ARGS=(--workers "$WORKERS")
[ $WHOLE_SUITE = 1 ] && REPORT_ARGS+=(--whole-suite)
# A whole-suite result is only trustworthy if the tests step ran the whole suite,
# pytest finished (rc 0 or 1), and its JUnit file parses with at least one case.
tests_rc=$(awk -F'\t' '$1=="tests"{print $2}' "$OUT/branch.steps")
if awk -F'\t' '$2 == -2 {hit = 1} END {exit !hit}' "$OUT/branch.steps"; then tests_rc=skipped; fi
SUITE_OK=0
if [ $WHOLE_SUITE = 1 ] && { [ "$tests_rc" = 0 ] || [ "$tests_rc" = 1 ]; } &&
  [ "$("$BIN/python" "$ROOT/scripts/dev/_gates_report.py" --suite-collected "$OUT" 2>/dev/null)" -gt 0 ] 2>/dev/null; then
  SUITE_OK=1
fi
WRITE_REFUSED=0
if [ -n "$WRITEBASE" ]; then
  if [ $SUITE_OK = 1 ]; then
    REPORT_ARGS+=(--write-baseline "$WRITEBASE" --repo "$REPO_NAME" --main-sha "$MAIN_SHA" --head-sha "$HEAD_SHA")
  else
    echo "gates: --write-baseline refused: the tests step did not finish the whole suite with a JUnit file and collected > 0 (tests rc ${tests_rc:-none}); use --keep-going" >&2
    WRITE_REFUSED=1
  fi
fi

# Test ids in the test files this branch deleted, counted at the merge base. A rename is not a
# deletion (git -M), so a moved file keeps its ids in the branch's own count.
deleted_test_ids() {
  local base f files=() n
  base=$(git -C "$ROOT" merge-base origin/main HEAD) || return 1
  while IFS= read -r f; do
    case $f in tests/*test_*.py) files+=("$f") ;; esac
  done <<EOT
$(git -C "$ROOT" diff --name-only -M --diff-filter=D "$base")
EOT
  [ ${#files[@]} -gt 0 ] || { echo 0; return 0; }
  git -C "$ROOT" worktree add -q --detach "$MBT" "$base" || return 1
  # A collection error in a deleted file counts no ids, so the shortfall stays and the gate fails.
  n=$(cd "$MBT" && PYTHONPATH=$(pypath "$MBT") env -u PYTEST_ADDOPTS -u PYTEST_PLUGINS "$BIN/python" -m pytest --collect-only -q -p no:cacheprovider -o addopts= --color=no ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"} ${files[@]+"${files[@]}"} 2>/dev/null | grep -cE '^[^ ]+\.py::') || true
  echo "${n:-0}"
}

# A gate passes only on a complete EVIDENCE block and at least one step that ran green.
"$BIN/python" "$ROOT/scripts/dev/_gates_report.py" "$OUT" ${REPORT_ARGS[@]+"${REPORT_ARGS[@]}"} | tee "$OUT/evidence"
report_rc=${PIPESTATUS[0]}
if [ "$report_rc" = 4 ]; then
  echo "gates: FAIL: the failure count in the pytest log disagrees with the JUnit (logs in $OUT)" >&2; exit 3
fi
# The reporter exits 1 only when it refused to write the baseline, after printing the whole block.
write_failed=0
[ "$report_rc" = 1 ] && [ -n "$WRITEBASE" ] && write_failed=1
if { [ "$report_rc" != 0 ] && [ $write_failed = 0 ]; } || ! grep -qx '=* EVIDENCE =*' "$OUT/evidence" || ! tail -n 1 "$OUT/evidence" | grep -qx '=\{70\}'; then
  echo "gates: FAIL: no complete EVIDENCE block (reporter exit $report_rc; logs in $OUT)" >&2; exit 3
fi
if [ $write_failed = 1 ] || [ $WRITE_REFUSED = 1 ]; then exit 1; fi
if [ -n "$BASEFILE" ]; then
  [ $SUITE_OK = 1 ] || { echo "gates: FAIL: baseline comparison needs a completed whole-suite tests step with a JUnit file and collected > 0 (tests rc ${tests_rc:-none})" >&2; exit 1; }
  # A smaller suite is green only when the branch itself deleted those tests; a collection error
  # in a kept file shrinks the count too and must not read as a smaller, passing suite.
  if [ -s "$OUT/shortfall" ]; then
    short=$(cat "$OUT/shortfall")
    if ! deleted=$(deleted_test_ids); then echo "gates: FAIL: could not count the tests the branch deleted" >&2; exit 1; fi
    if [ "$short" -gt "$deleted" ]; then
      echo "gates: FAIL: the branch collects $short fewer tests than the baseline but deleted only $deleted" >&2; exit 1
    fi
    echo "gates: collected $short fewer tests than the baseline; the branch deleted $deleted" >&2
  fi
  # Known failures are not a failure of the branch: only a new id, a failing
  # non-test step, or a pytest run that did not finish blocks.
  [ -s "$OUT/new-failing" ] && exit 1
  [ -s "$OUT/skip-increase" ] && exit 1
  awk -F'\t' '$1!="tests" && $2!=0 && $2!=-1 {bad=1} $1=="tests" && $2!=0 && $2!=1 && $2!=-1 {bad=1} END{exit !bad}' "$OUT/branch.steps" && exit 1
elif [ $BASELINE = 1 ]; then
  # Same host, same venv: a step that also fails on origin/main is a host or main problem, not this
  # branch's. Fail only on branch-only failures (see _gates_report.branch_only_steps).
  if ! BRANCH_ONLY=$("$BIN/python" "$ROOT/scripts/dev/_gates_report.py" --verdict "$OUT"); then
    echo "gates: FAIL: could not compute the baseline verdict" >&2; exit 3
  fi
  [ -n "$BRANCH_ONLY" ] && exit 1
else
  # One awk reads the whole file: a cut | grep -q pipe under pipefail can SIGPIPE and drop a failure.
  awk -F'\t' '$2 != 0 && $2 != -1 {bad = 1} END {exit !bad}' "$OUT/branch.steps" && exit 1
fi
# A step that ended rc 1 only on failures main also has did run. The engine counts this for a
# stored compare only because its format step always runs green; here format and mypy are SKIP,
# so a legacy run whose one real step shares main's failures would otherwise read as "no step ran".
ran_max=0; [ $BASELINE = 1 ] && ran_max=1
awk -F'\t' -v max="$ran_max" '$2 >= 0 && $2 <= max {ran = 1} END {exit !ran}' "$OUT/branch.steps" || { echo "gates: FAIL: no step ran (all skipped or none selected)" >&2; exit 3; }
exit 0
