# Phase 6 — CLI graph passthrough

> **Status:** shipped (uncommitted)
> **Branch:** `feature/cli-graph` (proposed)
> **References:** [PIPELINE_GRAPH_GUIDE.md](../../forge-platform/PIPELINE_GRAPH_GUIDE.md), [forge-engine/plans/2026-05-05-graph-package.md](../../forge-engine/plans/2026-05-05-graph-package.md)

## Goal

`decoy run pipeline.yaml` and `decoy validate pipeline.yaml` accept `mode: graph` YAML transparently. CLI uses inline `dsn:` fields only — no platform connector store dependency.

## Touch-points

1. `src/decoy/cli/run.py` — read `mode` from YAML; new `Mode.graph` enum; dispatch to `decoy_engine.run_graph`.
2. `src/decoy/cli/validate.py` — branch on `mode == 'graph'` to call `decoy_engine.validate_graph`.
3. Mirror `PIPELINE_GRAPH_GUIDE.md` to forge repo root.
4. Update `forge/CLAUDE.md` active guides list.

## Verification

- `decoy validate <good_graph.yaml>` exits 0; `<bad_graph.yaml>` exits 1.
- `decoy run <good_graph.yaml>` runs end-to-end and produces the expected output file.
- `decoy run --json` emits the run-summary JSON object on success/failure.
- Existing `decoy run`/`validate` tests still pass for `mode: mask|generate|convert`.
