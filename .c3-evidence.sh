#!/usr/bin/env bash
# Scratch evidence for LAYOUT C3 (not committed). Runs in a vm-run snapshot.
set -u
SRC=$PWD
S=$(mktemp -d /tmp/c3s.XXXXXX)
git archive HEAD | tar -x -C "$S"
cd "$S" && git init -q && git add -A && git -c user.name=e -c user.email=e@e commit -qm base
echo "== AT-5 clean host: no .venv, no origin/main =="
ls -d .venv 2>&1 | head -1; git rev-parse -q --verify origin/main || echo "origin/main: absent"
bash scripts/dev/gates.sh --steps layers > "$S/layers.out" 2>&1; echo "LAYERS_ONLY_RC=$?"
grep -E '^\[layers\]|test paths|venv:' "$S/layers.out"
BASE=$(git rev-parse HEAD)
PY=${PY:-$SRC/.venv/bin/python}
reg() { "$PY" -m pytest -q -p no:cacheprovider tests/sentry/test_baseline_registry.py 2>&1 | tail -n 1; }
echo "== AT-6 m1: ignore line added to .importlinter only =="
sed -i.bak 's#^ignore_imports =$#ignore_imports =\n    decoy._row_sample -> decoy.api#' .importlinter; reg
echo "== AT-6 m2: same key also added to the baseline: ratchet =="
"$PY" - <<'PY'
import json; p="tests/sentry/baselines/import-layers.json"; d=json.load(open(p))
d["entries"]["layers::decoy._row_sample -> decoy.api"]={"reason":"seeded"}
json.dump(d,open(p,"w"),indent=1)
PY
reg; "$PY" scripts/dev/ratchet_check.py --base "$BASE" --slice LAYOUT-C3; echo "RATCHET_ADD_RC=$?"
restore() { for f in .importlinter tests/sentry/baselines/import-layers.json; do git show "HEAD:$f" > "$f"; done; rm -f .importlinter.bak; }
restore
echo "== AT-6 m3: one ignore key removed from both =="
K='decoy.ui.output -> decoy.cli.exit_codes'
grep -vF "    $K" .importlinter > x && mv x .importlinter
"$PY" - "$K" <<'PY'
import json,sys; p="tests/sentry/baselines/import-layers.json"; d=json.load(open(p))
del d["entries"]["layers::"+sys.argv[1]]; json.dump(d,open(p,"w"),indent=1)
PY
reg; "$PY" scripts/dev/ratchet_check.py --base "$BASE" --slice LAYOUT-C3; echo "RATCHET_REMOVE_RC=$?"
restore
echo "== AT-6 first inventory against origin/main =="
cd "$SRC" && "$PY" scripts/dev/ratchet_check.py --base origin/main --slice LAYOUT-C3; echo "RATCHET_FIRST_RC=$?"
rm -rf "$S"
