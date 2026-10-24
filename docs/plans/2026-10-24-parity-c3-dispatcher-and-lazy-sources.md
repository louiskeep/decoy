# Parity C3: route the CLI through the chunked dispatcher and lazy sources

Status: plan, PRE-RELEASE (2026-10-24). Part of the parity program; source: parity audit §4 rows "Chunked
dispatcher", "FK sequential / out-of-core routes", "Transactional sink", §7. Depends on engine E2a (bounded
reader) and E2e (finalisation); benefits from C2 (opener).

Rules consulted: 00-universal, development-loop, risk-and-exceptions, api-and-compatibility, performance,
observability-and-resilience, reuse-first, testing, documentation; CLI `CLAUDE.md`.

Risk: R2 (changes which engine path large CLI jobs take; memory behaviour is the point of the change).

## 1. Guarantee and non-goals

Guarantee: `decoy run --chunked` executes the same engine lane the platform's streaming route uses
(`run_mask_chunked` over the bounded reader, native kernels when present, chunk evidence stamped), and a
multi-table FK job no longer requires every source resident before routing: Parquet sources are offered
lazily so the engine's sequential/out-of-core routes see the same `LazySource` shape the platform gives
them, and outputs go through a `TransactionalSink` so a failed run publishes nothing. Masked values stay
byte-identical to a plain run (the engine's existing guarantee 3).

Non-goals: a CLI-side router (the engine decides), the platform's claim-time pricing persistence,
resumable runs (C4 may add restart markers later), generation streaming flags (engine already streams).

## 2. What exists

- CLI `--chunked` (`run.py:1360-1470`) calls the legacy `run_mask_pipeline_chunked` with naive row-count
  chunks from `iter_source_chunks`, writes per chunk, refuses `--native` and the report flags, and
  resolves the vestigial `substrate`.
- Plain `decoy run` materialises every source (`_load_sources_from_config`) and writes outputs itself by
  suffix; `run_pipeline` accepts `sink`, `source_loader`, lazy sources, `chunk_size_rows`,
  `auto_chunk_threshold_rows` and `native_threads`, none passed by the CLI.
- Engine: `run_mask_chunked(seeded_cfg, batches, table, engine_version, vault_writer, base_row_offset,
  native_threads, chunk_result_sink)`; `ParquetTransactionalSink`; `LazySource`; after E2a, the bounded
  reader with `TableBudget`.
- Platform: `_phase1_eligibility` allowlist (hash/redact/truncate/passthrough, single table) for its
  streaming route; the engine's auto-chunk lane is wider (12 operators).

## 3. Established solutions

Reuse the engine's own routing: the CLI stops choosing lanes and passes facts (budget, lazy sources,
sink, threads). This is the dbt/Prefect "wrapper passes context, library decides" pattern already named in
`shared-engine-architecture.md`. Byte-budgeted chunking follows pyarrow streaming readers through the
E2a module.

## 4. Design

- `--chunked` becomes an alias for "force the auto-chunk lane with an explicit budget": the CLI builds
  `TableBudget` from `--chunk-budget-mb` (default engine constant) and passes `chunk_size_rows`/
  `auto_chunk_threshold_rows=0` to `run_pipeline`; no separate code path, so `--native`, `--vault`,
  `--fidelity`, `--post-validate` all work under `--chunked`. Delete `_run_chunked_mask`,
  `iter_source_chunks`, `_write_chunked_output` (pre-GA hard delete).
- Sources: Parquet declared sources are wrapped as `LazySource` (engine type) instead of read resident;
  CSV and fixed-width stay resident until the engine's lazy CSV path exists (declined with the engine's
  own reason code, surfaced by `--explain-plan`).
- Sink: `decoy run` passes `ParquetTransactionalSink(target_dir)` for Parquet targets so FK jobs publish
  atomically; CSV targets keep the write-after-result path with a temp-and-rename publish.
- Evidence: `--evidence-out` records `chunked_route`/lane stamps from `quality_metrics` (today omitted
  for chunked runs).
- `validate preflight` reports the lane the engine would take (`classify_job`), closing the "OOC
  eligibility shown in preflight" redesign item.

## 5. Slices and acceptance

1. **C3a `--chunked` on the dispatcher.** Byte-identity test plain vs chunked (exists, retargeted);
   `--native --chunked` now allowed and proven on the companion matrix; peak RSS on the 10M fixture at or
   below the legacy lane (perf test with the engine's `rss_kb`).
2. **C3b lazy Parquet sources + transactional sink.** FK fixture run with a budget that the resident path
   would exceed completes; a forced mid-run failure leaves the target directory empty.
3. **C3c preflight lane report + evidence stamps + docs** (`explain chunked`, `explain native`, README).

## 6. Done when

No legacy chunked code remains in the CLI; `run_mask_pipeline_chunked` can leave `decoy_engine.__all__`
(E3c); the parity audit's "CLI pays the ingestion peak" note is false.
