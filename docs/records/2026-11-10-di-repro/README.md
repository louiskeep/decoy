# Repro scripts: distribution-model QA re-test

Status: record

Scripts behind the re-test in
[`2026-11-10-cli-qa-generation-distribution-models.md`](../2026-11-10-cli-qa-generation-distribution-models.md).
No data files are stored here; `make_data.py` writes them from fixed seeds.

## Run

From an empty work folder, with `decoy` on `PATH` (the CLI under test, installed against the
engine under test) and `numpy` and `pandas` importable:

```bash
bash /path/to/2026-11-10-di-repro/run.sh > run-output.txt
```

`run-output.txt` in this folder is the output from engine `5c24a75e` and CLI `9f603536` on macOS
arm64, CPython 3.10.

## Files

| File | What it does |
|---|---|
| `make_data.py` | Writes `c1.csv` (seed 5), `types.csv` (seed 21, 20,000 rows), `cond.csv` (seed 11, 6,000 rows) and `leak.csv` (seed 31, 1,000 rows). |
| `c1_ident.yaml` | Pairs of generate columns that differ only by name (C1). |
| `c1_indep.yaml` | Two statistical columns from unrelated sources, no `source_column` (C1). |
| `types_gen.yaml` | One statistical column per `types.csv` column, plus `np_check` with `null_probability` unset, 0, 0.1 and 0.5 (C2, C3, H2, H3, M3, M4). |
| `cond_gen.yaml` | `kid` with `condition_on: parent` (H1). |
| `leak_gen.yaml` | Generates from the `leak.csv` snapshot (H6, H7). |
| `engine_check.py` | `snapshots`: writes snapshots through the engine's `distribution_snapshot_document`, with and without values. `fidelity`: scores outputs with `compute_fidelity`, because `decoy report fidelity` fails on CLI main with engine main. |
| `measure.py` | Prints every number in the record's status table. An optional prefix (`doc_`) reads the outputs generated from the engine document snapshots. |
| `run.sh` | Runs all of the above in order. |
