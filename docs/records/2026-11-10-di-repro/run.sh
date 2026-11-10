#!/usr/bin/env bash
# Re-run the 2026-11-10 distribution-model QA repros in the current directory.
# Needs `decoy` on PATH (CLI with the engine under test) and the files in this folder.
# Writes outputs to ./out and prints the measurements from measure.py.
set -u
here=$(cd "$(dirname "$0")" && pwd)
export NO_COLOR=1
mkdir -p out
python "$here/make_data.py" .
cp "$here"/*.yaml .
log() { echo "== $*"; }

log fit c1;      decoy fit c1.csv -o c1.snapshot.json
log run c1;      decoy run c1_ident.yaml; decoy run c1_indep.yaml

log fit types;   decoy fit types.csv --parse-dates day -o types.snapshot.json
log run types;   decoy run types_gen.yaml
log report;      decoy report fidelity types.csv out/types_out.csv --generate --json > out/fidelity.json
                 decoy report fidelity types.csv out/types_out.csv --generate > out/fidelity.txt 2>&1
                 echo "report rc=$?"

log H5 threshold 1.0
sed 's/^  seed: 21$/  seed: 21\n  fidelity_warn_threshold: 1.0/' types_gen.yaml > h5_gen.yaml
rm -rf logs
decoy run h5_gen.yaml --json > out/h5_stdout.json 2> out/h5_stderr.txt; echo "h5 rc=$?"
grep -rl fidelity logs 2>/dev/null | sed 's/^/h5 log file: /'
grep -c 'generation_fidelity_below_threshold' out/h5_stdout.json out/h5_stderr.txt logs/* 2>/dev/null

log fit cond;    decoy fit cond.csv --joint parent,kid -o cond.snapshot.json
log run cond;    decoy run cond_gen.yaml > out/cond_run.txt 2>&1; echo "cond rc=$?"; cat out/cond_run.txt

log fit leak;    decoy fit leak.csv -o leak.snapshot.json > out/leak_fit.txt 2>&1; echo "leak fit rc=$?"; cat out/leak_fit.txt
log run leak;    decoy run leak_gen.yaml > out/leak_run.txt 2>&1; echo "leak rc=$?"; cat out/leak_run.txt

log engine-level snapshots: cell_format and redaction
python "$here/engine_check.py" snapshots
sed -e 's/types.snapshot.json/types_doc.snapshot.json/' -e 's#out/types_out.csv#out/doc_types_out.csv#' \
    -e 's#out/np_check.csv#out/doc_np_check.csv#' types_gen.yaml > doc_types_gen.yaml
decoy run doc_types_gen.yaml > out/doc_types_run.txt 2>&1; echo "doc types rc=$?"; tail -3 out/doc_types_run.txt
sed -e 's/leak.snapshot.json/leak_doc.snapshot.json/' -e 's#out/leak_out.csv#out/doc_leak_out.csv#' leak_gen.yaml > doc_leak_gen.yaml
decoy run doc_leak_gen.yaml > out/doc_leak_run.txt 2>&1; echo "doc leak rc=$?"; cat out/doc_leak_run.txt
log H5 with engine logging on
python -c "import logging, sys; logging.basicConfig(level=logging.WARNING, stream=sys.stdout); from decoy.__main__ import app; sys.argv=['decoy','run','h5_gen.yaml']; app()" 2>&1 | grep -o 'generation_fidelity_below_threshold[^]]*]' | head -3
log engine fidelity
python "$here/engine_check.py" fidelity
log measure;     python "$here/measure.py" .; python "$here/measure.py" . doc_
