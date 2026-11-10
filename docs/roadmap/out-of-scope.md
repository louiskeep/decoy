# Out of V1 scope (V2 and post-V1)

Status: plan

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

The 21 Council-V2 features, built when a customer pulls: F03 file unions, F05 fixed-width streaming,
F08 coherent free-text identity binding, F11 output ordering and byte reproducibility, F12 customer
regression suites, F17 portable disguise bundles, F18 config composition, F19 semantic diff and repair,
F20 config migration, F27 governed schedules (owner may pull), F28 local execution node, F37 post-mask
privacy risk (k-anonymity and QI already ship in `decoy scan`), F38 metadata preserve and redact, F39
OpenLineage export, F40 plugin SDK, F41 expression evaluator preview, F42 Unix streams, F46 QA
scenarios, F47 healthcare packs, F48 statistical synthesis, F49 clone-system handoff, F50 native
masking-policy export. Detail: `P:docs/backlog/v2-candidate-plan.md`.

| V2 row | What | Source |
|---|---|---|
| DETECT-PROFILES | Detection settings profiles: named sets of detection settings (detectors, overrides, thresholds, ML on or off) that a pipeline picks by name | owner, 2026-11-05 |
| EXPAND | Core expansion candidates for V2 and V3 (more inputs and outputs, masks, generators, documents, images, video and audio), each with method, users, difficulty and placement: [v2-v3-expansion-candidates.md](v2-v3-expansion-candidates.md). Proposal for the V2/V3 discussion; not scheduled | owner, 2026-11-06 |
| GEN-WINDOW | Local windowed generate in the CLI: expose the engine primitive behind GEN-API (`E:src/decoy_engine/generation/window.py` `generate_rows`) as a CLI command that returns a deterministic slice of a generate job by seed, offset and count, with no server or keys. Rows match what the platform GEN-API returns for the same job and seed. The GEN-API HTTP route, keys and quotas stay platform-only. Before building, the engine must enforce the spec's M5 window bound (`offset + count > row_count` is `422 window_exceeds_row_count`); a live QA run on 2026-11-09 found it unimplemented | owner, 2026-11-09 |

Post-V1 on demand: route-coverage phase 2 (OOC address faker, FPE FK key, resident escape hatch, OOC
quarantine); the CLI init wizard (spec CLI #73); value-based FK discovery (SCAN-MULTI plan section 7);
chunk-level resume; a user-level library store (LIB Q7).

V2 corrective backlog and audit: vault `handoffs/V2-CORRECTIVE-BACKLOG.md`. DuckDB opportunities:
vault `v2/duckdb/` and platform `plan/v2-duckdb-plans` (`1c8eba8d`); proposals, not scheduled.
