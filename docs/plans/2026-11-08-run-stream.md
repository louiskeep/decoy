Status: plan

# RUN-STREAM: one fast run path for `decoy run` (roadmap row 63a)

Owner: Cam. Author: claudeworkerbee (Opus). Date: 2026-11-08. Scope: engine and CLI, V1. Revision 3 (first Codex review of revision 2 at `6b4831e`; dispositions in section 0).

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`
(PLAN: choke point, Placement, Design notes, Established solutions), `feature-dev.md`, `architecture.md`
(layout), `reuse-first.md`, `api-and-compatibility.md`, `cross-cutting-concerns.md`, `testing.md`,
`performance.md`, `security.md`; the plan contract (`30_Resources/Decoy-Plan-Contract-and-Defect-Catalog.md`),
`LOCAL-BUILDER-BRIEF.md`, the V1 bar (a second copy of a central mechanism always blocks); the engine
`CLAUDE.md` (600/700-line module rule, established methodology, pre-GA hard delete); the CLI CODEMAP
"Where things go" (`CODEMAP.md:42-59`, `cli/` is frozen); the code at each anchor on engine `main`
`7a61be3c` and CLI `main` `994bc7a`. Codex review also consulted `code-review.md`, `verification.md`,
`documentation.md`, and `catalogs/recurring-defects.md`.

Roadmap row 63a (`docs/ROADMAP.md:325`): plain `decoy run` streams large sources from disk by itself when
the config can be processed in pieces; relationship jobs larger than memory use the out-of-core (DuckDB)
route; `--chunked` becomes a strict switch on the same code path; Decoy settings hold max memory and max
threads, set in the setup step, with per-run flag and config overrides; defaults use the machine; the
run summary says which route ran and why. Step 1 of the row is a measurement; section 1 holds it.

## 0. Review dispositions

Revision 3 (first Codex review of revision 2 at `6b4831e`):

| Finding | Disposition | Where |
|---|---|---|
| V1-1: `commit()` sealed the sink and the state machine forbade later `write`, but `publish()` then tried to write resident `result.outputs`; full-frame does not call the sink's commit at all (`_pipeline_full_frame.py:269-305`) | `commit()` now closes only engine-owned streamed writes and records engine success. The CLI-only `seal_result(outputs)` is the one second-stage entry point: it stages resident outputs, rejects overlap or a missing target, seals everything, and returns before the native check and vault commit. `publish()` only renames sealed files | 4, 5.2, 7, 8 (AT-C1e, AT-C1g) |
| V1-2: the CLI's `except Exception` does not catch `KeyboardInterrupt`, so a signal after engine commit could leave staged files (`run.py:905-908`) | `TargetSink` is a context manager around the run, native check, vault commit and publish. Every exit before `PUBLISHED`, including `BaseException`, calls non-raising `abort()` | 5.2, 7, 8 (AT-C1d, AT-C1h) |
| V1-3: the FK split named only `gate_fk_child_edges`, but base `--chunked` uses all of `check_chunked_compatibility`, including both-orientation `code_set` and `bucket_perturb` FK checks (`_chunked.py:255-374`) | Strict preflight calls the existing compatibility gate once per mask table. The split extends B7 only when every table passes that gate; its FK component remains `gate_fk_child_edges` | 5.3, 7, 8 (AT-E1a, AT-C2a) |
| V1-4: E2's full CSV counting pass could read source rows before a strict refusal | Strict preflight runs from config plus source schema before any data-row iterator is opened. Only an admitted job may perform the bounded facts pass through the shared reader; the stream threshold remains bypassed | 5.3, 8 (AT-E1a, AT-E2a) |
| V1-5: the platform API accepts `fs_root` and `affinity`, while the frozen engine function was zero-argument; the port also used Linux-only `os.sched_getaffinity` (`api/cgroup_cpu.py:231-244`) | The engine public function preserves the injectable keyword signature, the platform delegates through the engine facade, and hosts without affinity support use `os.cpu_count() or 1`; cgroup files remain optional when absent | 4, 5.4, 8 (AT-E1d), 13 |
| V1-6: `out_of_core_threads` was not connected to the six nested `connect_duckdb` callers, so some DuckDB work would ignore the cap (`_duckdb.py:32-64`) | `run_fk_out_of_core` binds the validated cap once in a run-scoped context; every connection reads it at the single `connect_duckdb` choke point and clamps it with memory and detected CPUs | 4, 5.4, 7, 8 (AT-E1c) |
| V1-7: the new stored settings model did not reject TOML booleans and had no versioned read contract | `settings.toml` has required string `schema_version = "1.0"`; readers use strict primitives and `fullmatch`, refuse missing or unknown majors, and tolerate unknown minors and keys | 5.4, 7, 8 (AT-C3a, AT-C3b), 13 |
| V1-8: config-order target renames could leave a multi-table relationship output split across old and new generations; because `_commit_vault` runs first, the same failure could also replace the old vault while restoring old outputs (`run.py:884-892`) | `TargetSink` adapts CLI delivery's central publication session: it journals the old vault and targets, installs no target before the new vault, and restores the old generation on any caught failure (`docs/ROADMAP.md:319-322`) | 5.2, 7, 8 (AT-C1d, AT-C1h), 9 |
| DESIGN-1: putting the target/vault rollback journal in RUN-STREAM would create a second publication mechanism beside F22 and CLI delivery, whose roadmap contract already owns atomic publication and the one sink (`docs/ROADMAP.md:319-322`) | CLI delivery is now a C1 prerequisite. `TargetSink` is only the engine-protocol adapter over that central publication session; all staging, journaling, rollback, permissions and rename order stay in the delivery choke point and its guard tests | 4, 5.2, 11, 12, 14 |
| V1-9: the engine sends every output table to a supplied sink, but CLI targets are optional and today's writer skips outputs with no declared target (`_targets.py:401-422`); the planned sink would either fail that valid run or lack a `spill_parent` when there were no targets | `TargetSink` consumes and row-counts targetless tables without serializing them. Its run-wide spill parent comes from CLI delivery's protected publication scratch, not from a target path, so zero-target and distinct-target runs remain valid | 5.2, 8 (AT-C1d, AT-C1g) |
| V1-10: routing recognizes lazy inputs through concrete `isinstance(source, LazySource)` checks, so an unrelated CSV lazy class would remain resident or fail (`_chunked_input.py:115-145`, `_pipeline_auto_chunk.py:378-395`) | `CsvLazySource` is a substitutable subclass of the existing public Parquet `LazySource` and overrides its read/facts methods through the one CSV reader. Existing type choke points admit it without parallel CSV routing checks; a guard pins the subclass relationship | 4, 5.1, 7, 8 (AT-E2a), 12 |
| V1-11: the engine streamed sink regroups output at 1,048,576 rows or 256 MiB, while base `--chunked` writes each configured chunk as a Parquet row group (`_chunked_output_sink.py:69-73`, `_targets.py:453-457`), so values would match but bytes would not | Only under `stream_required`, output grouping preserves the base path's row-group boundaries from `chunk_size_rows` and PyArrow's 1,048,576-row writer cap; the 256 MiB early cut remains an `auto` policy only. CSV still uses the shared writer core | 5.3, 7, 8 (AT-E1a, AT-C2a) |
| V1-12: the summary called configured thread and memory caps resources "used" even when the route never opened DuckDB or a native kernel (`_duckdb.py:59-64`, `_pipeline.py:139-145`) | The frozen route view separates configured caps from route-applied values. An unused resource says `not_used`; native or DuckDB settings are shown as applied only from execution evidence, never inferred from the cap | 2 G5, 5.5, 6.4, 8 (AT-E3a, AT-C2b), 13 |

Revision 2 (Dennis round 2 on `337672a`: GO-WITH-FIXES, 3 HIGH, 3 MEDIUM, 2 LOW):

| Finding | Disposition | Where |
|---|---|---|
| V1-1: `TargetSink` had no `spill_parent`, so a streamed table that holds back past one row group raises `HOLD_BACK_SPILL_UNAVAILABLE` (`_chunked_output_sink.py:466-475`) where the resident run works | Superseded by revision 3: `TargetSink.spill_parent` returns CLI delivery's protected run scratch, including when there is no target; AT-C1i | 5.2, 8 |
| V1-2: the lane takes no FK config (`_planner.py:16-18`; `_pipeline_chunk_route.py:84` captures no lazy facts with edges); `gate_fk_child_edges` lives only in the pandas oracle (`_chunked.py:305`); the out-of-core force ignores the FK dtype hazard (`_pipeline_routing_fk_dtype.py:48-75`), so a chain could fail after parents were written | Superseded by revision 3: under `stream` only, every mask table must pass the complete existing `check_chunked_compatibility` gate before the B7 split; other FK configs use out-of-core only when compatible and hazard-free. `auto` is unchanged | 5.3, 6.3, 8 (AT-E1a, AT-C2a), 14 |
| V1-3: `detect_usable_cpus` would be a second copy of the platform's `effective_cores` (`decoy-platform:api/cgroup_cpu.py:231`) | E1b ports `api/cgroup_cpu.py` into the engine (citing it and its sources, automaxprocs and HotSpot); slice P1 makes the platform's `api/cgroup_cpu.py` call the engine's function; `_duckdb.py:84` uses it too | 4, 12, 14, 16 |
| MEDIUM: G4a untrue for the quarantine file; the engine never calls `abort()` after `commit()`; the eight `execution_mode` comparisons; streamed generation | G4a states the quarantine exception; `TargetSink.committed_table_path` preserves the aliasing guard; revision 3 uses a context manager for every post-commit exit; E1a translates `stream` once; generation stays resident without `bounded_write_batches` | 2, 5.2, 5.3, 6.2, 8 |
| LOW: section 9 says "during `commit`"; `detect_usable_cpus` placement | "during `publish`"; placement: `execution/pipeline/_host.py`, because `execution/out_of_core/` is frozen at 44 and the package root has 60 entries; the row names it a host probe, not spine | 9, 12 |
| Threshold "0" | `stream` bypasses the threshold check; it does not pass 0, which `require_positive_int` refuses (`physical/_snapshot.py:118`) | 5.3 |

Revision 1:

| Finding (Dennis r1) | Disposition | Where |
|---|---|---|
| B1: full frame and the mixed route never touch the sink (`_pipeline_full_frame.py:305` commit is inert unless the run streamed; `_isolated_worker.py:157-162` handles two shapes); dropping `_write_mask_outputs` (`run.py:892`) would write nothing on the most common path | Superseded by revision 3: `seal_result` is the one CLI-only resident entry point; it rejects overlap and missing targets before sealing the complete output set | 4, 5.2, 6.2, AT-C1g |
| B2: with a sink inside `run_pipeline`, `commit()` would publish before `post_run_verify` and the vault commit (`run.py:885-890`), so masked output could outlive a lost vault and `--native` would print a false "no output was written" (`_native_gate.py:476-478`) | Superseded by revision 3: engine `commit()` closes streamed writes, `seal_result` closes resident writes, and the rollback journal publishes only after the native check and vault commit | 5.2, 6.1, AT-C1h |
| H1: evidence and notify row counts read `result.outputs` (`run.py:901`, `:904`), empty on streamed runs | The sink counts rows per table; the CLI reads counts from the sink | 5.2, 6.5, AT-C1g |
| H2: under `stream`, small tables (lane threshold 100,000 rows), FK configs `--chunked` admits today (`_chunked.py:299-307`) and CSV before E2 would be refused | `stream` drops the lane's row threshold, and an FK config the lane does not take is forced to the out-of-core route (the existing `execution_mode="out_of_core"` force) instead of refused; C2 waits for E2 in a release; the C2 gate lists every config base `--chunked` accepts that the new path refuses, and a non-empty list blocks C2 | 5.3, 6.3, 14, AT-C2a |
| H3: `RunResources` was a second way to set `native_threads` and `out_of_core_budget_bytes` (`_pipeline.py:139`), and the CLI's "0.6 x ceiling - 1 GiB" a second default memory policy beside `_HOST_RAM_FRACTION` (`_budget.py:137`) | `RunResources` dropped. The CLI passes the existing keywords plus one new one, `out_of_core_threads`. Memory `auto` passes `None`, so the engine's one default applies; Q3 asks whether to raise that engine default for every caller | 2 G4, 4, 5.4, 6.4, 10 Q3, 14 |
| Medium and low items | taken: speed claims marked single-run (1.4); E2 states how a lazy CSV gets its routing facts; the `run_pipeline` call-site sentry scoped to `cli/run.py` (`cli/tokenize.py:347`, `api.py:529` named); E1 split into E1a and E1b; `detect_usable_cpus` out of `_budget.py` (609 lines); 1.3 thread count is 8; DuckDB sources go lazy (they are Parquet snapshots, `run.py:616`); `.csv.gz` and empty-source rules stated; hostile item 2 answered | 1, 5.1, 5.2, 8, 9, 12, 14 |

## 1. Measurement (step 1 of the row)

Harness: `docs/plans/run-stream-evidence/` (`gen.py` writes a four-column string table, `t.parquet` in
1,048,576-row groups and the same rows as `t.csv`; `drive.py` runs `decoy run` end to end in a fresh
process per cell under `/usr/bin/time -v`; `engine_cell.py` calls `run_pipeline` directly). Workload per
row: `hash` on `email`, `redact` on `secret`, `truncate` on `zip`, `passthrough` on `ref`, Parquet target.
Hosts: GCP `decoy-test-6` (CLI, 8 vCPU, 32 GB) and `decoy-test-5` (engine, 8 vCPU, 32 GB), CLI
`994bc7a`, engine `7a61be3c`. Neither venv has `decoy-engine-native`; the CLI prints "native acceleration
is not installed ... Running on the Python fallback", so every cell below is the Python (pandas) path.

### 1.1 `decoy run` today (CLI)

| Rows | Source | Mode | Wall s | Peak RSS MB | Route label printed |
|---|---|---|---|---|---|
| 1M | Parquet 38 MB | plain | 13.5 | 620 | pandas (legacy adapter) |
| 1M | Parquet | `--chunked` | 13.0 | 511 | pandas chunked stream |
| 1M | CSV 76 MB | plain | 13.4 | 630 | pandas (legacy adapter) |
| 1M | CSV | `--chunked` | 13.6 | 469 | pandas chunked stream |
| 4M | Parquet 151 MB | plain | 44.1 | 1,563 | pandas (legacy adapter) |
| 4M | Parquet | `--chunked` | 42.4 | 651 | pandas chunked stream |
| 4M | CSV 304 MB | plain | 48.6 | 1,875 | pandas (legacy adapter) |
| 4M | CSV | `--chunked` | 47.3 | 480 | pandas chunked stream |
| 16M | Parquet 606 MB | plain | 240.2 | 5,056 | pandas (legacy adapter) |
| 16M | Parquet | `--chunked` | 219.2 | 1,130 | pandas chunked stream |
| 16M | CSV 1,216 MB | plain | 278.7 | 6,809 | pandas (legacy adapter) |
| 16M | CSV | `--chunked` | 261.5 | 484 | pandas chunked stream |

Threads (Arrow's CPU pool, `OMP_NUM_THREADS`, plain Parquet run): 1M rows 11.9 s at 1 and 12.0 s at 8;
4M rows 42.9 s at 1 and 47.6 s at 8; 16M rows 274.7 s at 1 and 253.5 s at 8, with the default run
at 240.2 s, so the spread between single runs (about 15%) is larger than any thread effect. No
reliable speedup: the Python path masks on one core and Arrow's pool only decodes Parquet.

What this shows:

- Plain `decoy run` never streams. `_sources.read_source` loads every Parquet source whole
  (`src/decoy/cli/_sources.py:127`) and CSV through pandas then `from_pandas` (`:129-130`); `run.py`
  calls `run_pipeline` with no `sink` and default resources (`src/decoy/cli/run.py:868-878`). Peak
  memory grows with the file: 8 to 16 times the Parquet file size, 5 to 8 times the CSV size.
  At 16M rows a plain CSV run peaks at 6.8 GB.
- `--chunked` is bounded (470 to 1,130 MB at every size) but is a second engine path:
  `run_mask_pipeline_chunked` (`execution/_chunked.py:378`, the pandas oracle) fed by the CLI's own
  chunk reader (`_sources.iter_source_chunks`, `:139`) and writer (`cli/io/_targets.py:425`).
- Throughput is about 85,000 rows per second for three masked string columns up to 4M rows on
  every path. At 16M rows the resident runs slow to about 67,000 (Parquet) and 57,000 (CSV) rows per
  second, and `--chunked` is 6 to 9% faster than plain. Streaming is mainly a memory fix on the
  Python path; the time gain only shows on large inputs.

### 1.2 The engine's own streaming lane (engine, `run_pipeline` direct)

`engine_cell.py`, same data shape (`bench_worker_lazy.py prepare --workload native`, 1,048,576-row
groups), `mask_secret_ref` set:

| Rows | Cell | Wall s | RSS increment MB | Process peak MB | Input mode | Output mode |
|---|---|---|---|---|---|---|
| 4M | `pq.read_table`, no sink (today's CLI) | 48.1 | 1,263 | 1,470 | resident | resident (`no_sink`) |
| 4M | `pq.read_table` + `ParquetTransactionalSink` | 48.3 | 799 | 995 | resident | streamed |
| 4M | `LazySource` + `ParquetTransactionalSink` | 47.9 | 514 | 704 | lazy | streamed |
| 16M | `pq.read_table`, no sink (today's CLI) | 242.9 | 4,651 | 4,824 | resident | resident (`no_sink`) |
| 16M | `pq.read_table` + `ParquetTransactionalSink` | 248.4 | 2,125 | 2,298 | resident | streamed |
| 16M | `LazySource` + `ParquetTransactionalSink` | 191.0 | 528 | 701 | lazy | streamed |

The auto-chunk lane already routes this config (`auto_chunk.mode == "chunked"`, reason "single mask
table with only chunk-safe scalar strategies ... at or above the auto-chunk threshold (100000)"); what
the CLI misses is a `LazySource` input and a sink. `native_admitted` is `False` on every cell (no
companion). With lazy input and a sink the RSS increment stays flat (514 MB at 4M rows, 528 MB at 16M;
605 MB file), and the 16M run is 21 percent faster than today's resident call (191 s against 243 s),
because nothing pays for whole-table Arrow and pandas copies. The engine lane alone gives more than
`--chunked` gives today, on the default path.

### 1.3 Threads where they exist

- Native companion (not installed here): the recorded 100M-row W2 run on `n2-standard-8` took the hash
  kernel from 299.7 s at 1 thread to 94.8 s at 8 (3.2 times), whole job 429.9 s at 8 threads, peak
  447 MB; `redact` and `truncate` stayed single-threaded at about 128 to 178 s
  (engine `docs/records/audit-2026-09-30/stage-2c-summary.md:213-262`; also
  `docs/plans/2026-09-21-phase5-native-operator-expansion.md:35-41`). That run called
  `run_native_or_oracle_chunked` directly, not a product path. The native thread knee is 4 by default
  (`decoy-engine-native/src/threads.rs:47`, `DECOY_NATIVE_MASK_THREAD_KNEE`), so "all cores" means at
  most 4 kernel threads per call unless the knee is raised.
- DuckDB out-of-core FK route: 3M rows per table, 3 tables, `scripts/fk_memory_probe.py --mode out_of_core` on the engine VM.
  At `--mem-cap-mb 4000` DuckDB got `memory_limit` 3200MB and so 1 thread; mask 500.7 s, peak RSS
  905 MB. At 24000 it got 19200MB and so 8 threads (9 by memory, capped at the VM's 8 CPUs, `_duckdb.py:84`); mask 310.4 s
  (38% less), peak RSS 1287 MB. Spill peak about 1 GB and parity ok in both. The thread count comes
  only from the memory limit at 2 GiB per thread (engine
  `src/decoy_engine/execution/out_of_core/_duckdb.py:29`, `:67`), so a small memory budget also
  takes away this route's cores. This route already uses many threads when it has the memory; the
  plan does not change it.
- Mac (macOS arm64): not measured. `~/decoy/acct2-cli-mac` has no venv, and building one is an install
  on the Mac, which needs the owner's go (owner question Q5). The Python path is single-threaded on
  every host, so the Mac would change the absolute numbers, not the thread finding.

### 1.4 What follows for the plan

1. The biggest speed lever is the native companion, and the CLI install does not ship it
   (REL-PKG, row 90: "native companion wheels (engine #353 workflow, never run)"). RUN-STREAM threads
   the resources through so the companion uses them the day it ships; it cannot make the Python path
   multithreaded. This is stated in the run summary (4.5) and is owner question Q1.
2. Streaming is a memory fix on the Python path and already exists in the engine. The CLI change is
   to call it: a `LazySource` per Parquet source and a sink per target. It is faster too once the
   data is large: at 16M rows the engine's lazy-plus-sink cell took 191.0 s against 242.9 s resident
   with no sink (21% less), and the CLI's `--chunked` run took 219.2 s against 240.2 s (1.2), at a
   quarter of the memory or less. Small inputs show no difference either way. These times are single
   runs, and runs of one cell spread by about 15% (1.3), so the time gains are indicative; the memory
   gains are the finding.
3. CSV has no lazy input in the engine lane (`LazySource` is Parquet only,
   `profile/_readers.py:214`), so CSV needs one engine slice (E2).
4. The DuckDB out-of-core FK route already runs on many threads when its memory budget allows
   (1.3). RUN-STREAM keeps its 2 GiB-per-thread rule and only adds the user's thread cap on top
   (the new `out_of_core_threads` keyword, AT-E1c), so a large memory budget no longer means every core
   when the user asked for fewer.

## 2. FRAME

### Problem

Users run `decoy run` and get one of two behaviours: a plain run that holds every source in memory,
or `--chunked`, a separate pandas path with its own reader, writer, refusals and route label. The
engine has a third: the auto-chunk lane with lazy input, streamed output and an out-of-core FK route,
none of which the CLI reaches. Resources are fixed: `native_threads=1` (`execution/_pipeline.py:139`)
and an out-of-core budget of 25 percent of RAM (`out_of_core/_budget.py:137`), with no setting.

### Guarantee (what V1 promises)

- G1. Plain `decoy run` passes every local Parquet source (and every DuckDB source, which the CLI already
  snapshots to Parquet) as a `LazySource` and every target through one CLI `TransactionalSink`; the
  engine picks the route. Every route's output reaches the targets: streamed tables through the sink
  during the run, resident tables through the same sink after it (5.2). A config the auto-chunk lane admits streams
  input and output (peak memory bounded by chunk size, not file size). Large FK jobs take the existing
  out-of-core route by the existing decision (`_pipeline_routing.py:194`).
- G2. After E2, local CSV sources stream the same way, through the engine's one CSV reader.
- G3. `--chunked` means "must stream": the same call with `execution_mode="stream"`; one strict
  preflight uses the existing compatibility and route gates before any source data-row iterator is
  opened, and refuses with a reason code and the blocking fact when no streaming route applies
  (`_chunked.py:255-374`, `_pipeline_chunk_route.py:43-103`).
  Every config base `--chunked` runs keeps running (5.3, AT-C2a). The CLI pandas chunked path
  (`_run_chunked_mask`, `run.py:1449`) is deleted (pre-GA).
- G4. Resources come from one resolved record: flag over environment over settings file over `auto`.
  `auto` threads = the engine's `detect_usable_cpus()` (affinity and cgroup quota, or `os.cpu_count()`
  where affinity is unavailable, following the platform calculation at `api/cgroup_cpu.py:231-244`); `auto` memory = the
  engine's own out-of-core default (passes `None`; 25 percent of host RAM today, Q3). In V1 the memory
  value bounds the out-of-core route (its budget and so its DuckDB threads); the auto-chunk lane is
  bounded by chunk size, not by this value.
- G4a. No target is published before the native evidence check and the vault commit: the sink stages
  streamed output during the run and resident `result.outputs` immediately after the run, then the CLI
  publishes only after `post_run_verify` and `_commit_vault`, as today (`run.py:884-892`). The old
  vault and targets are journaled by CLI delivery's central publication session until every new
  target is durable; a caught failure restores the whole old set, so vault and outputs remain one
  generation (`docs/ROADMAP.md:319-322`).
  One exception, unchanged from today: a quarantine sidecar the sequential route writes is published
  by the engine after `commit()` (`_sequential.py:625-633`); admins only, as today.
- G5. The run summary prints the route, its reason code, input and output modes, configured resource
  caps, and route-specific applied values when execution evidence has them. An inapplicable resource says
  `not_used`; nothing is inferred from a cap. All fields come from `ExecutionResult.quality_metrics`,
  never from a CLI guess (`_duckdb.py:59-64`, `_pipeline.py:139-145`).
- G6. Output semantics are unchanged: a plain streamed run writes the same CSV bytes and Parquet
  values and schema as its resident run. The strict `--chunked` path additionally preserves base
  `--chunked` CSV and Parquet bytes by keeping its chunk-boundary writer grouping
  (`run.py:1462-1466`, `_targets.py:453-467`). For `.csv.gz` targets the decompressed bytes are equal;
  the file itself may be multi-member gzip, as the shared writer core already makes it under
  `--chunked`. Empty sources follow the plain run's rule on both paths; where base `--chunked`
  differed, the CHANGELOG says so.

### Non-goals (V1)

- Multithreading the Python path. Speed beyond today needs the native companion (REL-PKG).
- Cloud sources and targets (`s3`, `gcs`): still refused by `_require_local_io_endpoints`
  (`run.py:1520`).
- Streaming `fixed_width` or archive CSV targets (still resident; the refusal text moves to the engine
  reason under `--chunked`).
- A resources field in the pipeline YAML (owner question Q2; recommendation: no).
- The platform's own budget code (`api/jobs/native_budget.py`): unchanged; V2-LOG item.

### Failure modes

| Failure | Behaviour |
|---|---|
| Lazy source changes between footer read and batch read | engine `facts_match` refusal (`_chunked_input.py`), exit 3, nothing published (sink aborts) |
| A run fails after the sink took some tables | the sink context manager calls non-raising `abort()` for `Exception` or `BaseException`; every staged temp is removed and old targets stay untouched (`run.py:905-908` shows why an `except Exception` alone is insufficient) |
| `post_run_verify` fails after the run | the sink context aborts staged targets; no target or vault changed (G4a) |
| `_commit_vault` or target publication fails | the sink restores journaled targets and vault together, then removes unpublished staging; the old generation remains (G4a) |
| An exception after the engine called `commit()` (the engine never aborts after it, `_sequential.py:639-650`, `out_of_core/_runner.py:302-313`) | leaving the CLI's sink context before `PUBLISHED` rolls back even for `KeyboardInterrupt`; the old vault and targets are restored and staging is removed |
| `--chunked` on a config no streaming route takes | engine `runtime.streaming_unavailable` before a data-row iterator opens; exit 1 (usage) with the blocking fact |
| Settings file unreadable or invalid | exit 1 naming the file and key; never a silent default |
| `--max-memory` below the engine floor | exit 1 (`resources.memory_below_floor`) |
| Memory or CPU detection fails | the engine's coded `OUT_OF_CORE_MEMORY_DETECTION_FAILED` (`_budget.py:222`) surfaces with the flag to pass |
| Out of disk while staging a target | sink aborts, `OSError` errno class kept, exit 3 |

## 3. Established solutions

- Spark and DuckDB: the planner chooses the physical route from facts (sizes, operators) and the user
  sets resources (`spark.executor.memory`, `SET memory_limit`, `SET threads`), not routes. Here the
  engine's `decide_execution_route` and `decide_chunk_route` already choose; the CLI only supplies
  inputs and resources.
- Polars streaming: `collect(engine="streaming")` falls back silently when a node cannot stream; the
  engine's B6b lane chose the opposite and records why (`_chunked_input.py:18-20`). `--chunked` keeps
  that choice and turns it into a hard refusal, like `polars` `streaming=True` with
  `POLARS_FORCE_NEW_STREAMING` failing on an unsupported node.
- Resource defaults: the JVM sizes its heap as a fraction of the cgroup limit
  (`-XX:MaxRAMPercentage`); Ray and the platform's `native_budget.py` set threads from CPU affinity and
  the cgroup CPU quota and export `OMP_NUM_THREADS`. Precedence flag over env over file over default is
  the pip and git configuration model.
- Settings file: TOML under the app home, as `uv` (`uv.toml`) and `pip` (`pip.conf`) do; the CLI
  already owns `decoy_home()` (`src/decoy/distribution/layout.py:29`, `DECOY_HOME` override).
- Atomic output: write to a temp beside the target, rename on commit (the CLI's
  `staged_local_target`, used by `write_chunked_output`, `cli/io/_targets.py:453`).

## 4. Design notes

- One run call. The CLI builds `sources` and `sink` and calls `run_pipeline` once; the `if chunked:`
  fork at `run.py:841-857` goes. `--chunked` only sets `execution_mode="stream"`.
- Two output shapes, one writer (Dennis B1). Streamed routes hand the sink bounded batches during the
  run; full frame and the unstreamed mixed route return `result.outputs` and never touch the sink
  (`_pipeline_full_frame.py:269-305`, `_isolated_worker.py:138-165`). After `run_pipeline` returns, the
  CLI calls the same sink's CLI-only `seal_result(result.outputs)`. It rejects any table present in
  both shapes and any configured target with no staged table, then seals the complete set.
  `_write_mask_outputs` (`run.py:892`) goes; there is no second writer.
- Stage in the run, publish after the checks (Dennis B2). `TargetSink` adapts the single publication
  session delivered by roadmap row 61, which already owns stage-then-deliver through one sink and
  depends on F22 (`docs/ROADMAP.md:319-322`). A streamed route calls `sink.commit()`
  inside the run; for `TargetSink` that closes and fsyncs engine-owned streamed files and records
  engine success, but publishes nothing. A resident route does not call it
  (`_pipeline_full_frame.py:301-305`). In both cases the CLI next calls `seal_result`, then runs
  `post_run_verify`, journals the current vault, calls `_commit_vault`, and only then calls
  `sink.publish()`. The sink context restores the journal on every exit before complete publication.
  Pattern: two-stage prepare followed by rollback-journaled publish.
- The sink reuses the one CLI writer and publication coordinator. `write_chunked_output` already stages, writes CSV with
  `to_csv(header=first)` and Parquet with `ParquetWriter`, and publishes once. The sink calls the same
  per-format core per table, while CLI delivery owns the transaction across targets and vault. No
  second writer or rollback journal is added (`docs/ROADMAP.md:319-322`).
- Resources use the engine's existing keywords (Dennis H3): `native_threads` (`_pipeline.py:139`,
  clamped by the native knee, clamp recorded) and `out_of_core_budget_bytes`, plus one new keyword,
  `out_of_core_threads: int | None`. `run_fk_out_of_core` binds that cap for the run, and the one
  `connect_duckdb` function applies it to every nested connection (`_runner.py:105-127`,
  `_duckdb.py:32-64`). The result stays at most `memory_limit / 2 GiB` (`_duckdb.py:29`) because that
  keeps per-thread buffers inside the budget. There is no new resources object. The CLI resolves flag, env, settings file and `auto` in one
  function (`src/decoy/_resources.py`), used by `run`, `setup` and `doctor`; detection is the engine's
  (`detect_effective_memory_bytes`, `_budget.py:339`; `detect_usable_cpus`, ported from the platform), so the CLI grows no
  cgroup reader and no default policy of its own.
- The route summary is an engine record. `quality_metrics` already carries `execution` and
  `auto_chunk` blocks; E3 adds one frozen `route` view so the CLI renders fields, not dict paths.
- Lazy input keeps one capability boundary. Existing routing uses the concrete `LazySource` identity
  at its choke points (`_chunked_input.py:115-145`, `_pipeline_sources.py:56-64`). E2 adds
  `CsvLazySource(LazySource)` and overrides `footer_facts`, `open_batches`, `iter_batches`, `schema`,
  `num_rows`, `column_null_counts` and `to_table` through `read_csv_source(chunksize=)`. The public
  `LazySource(path)` constructor remains the Parquet implementation (`profile/_readers.py:213-349`).
  This is a substitutable second backend, not a second route test or reader.

## 5. Behavior

### 5.1 Sources (CLI part C1a)

- Local `format: parquet` file source of a mask table: `LazySource(path)` (`decoy_engine.profile`).
- DuckDB sources: the CLI already snapshots each to a temp Parquet file before validation
  (`run.py:613-620`); that file becomes a `LazySource` like any Parquet source.
- Local `format: csv`: resident `read_source` until E2 ships in a release; then `CsvLazySource`, a
  substitutable `LazySource` backend built from the same descriptor, with dialect resolved once
  through `resolve_csv_dialect` and every data pass through `read_csv_source(chunksize=)`
  (`profile/_csv_reader.py:271-337`).
- `fixed_width`, archive CSV: resident, unchanged.
- Generate-only tables: no source, unchanged.

### 5.2 Targets (CLI parts C1a and C1b)

`cli/io/_sink.py`: `TargetSink` adapts CLI delivery's central publication session and implements the
protocol's `write`, `write_batches`, `commit`, `abort`
(`execution/_transactional_sink.py:66-99`) and adds the CLI-only `seal_result()`, `publish()` and
`rows_written() -> dict[str, int]` entry points.

- For a table with a declared file target, `write_batches` stages through the central publication
  session and writes with the shared per-format core; `write` is `write_batches` over one table. For a
  table without a target, both entry points consume and count rows but serialize nothing, matching
  today's `write_targets` skip (`_targets.py:401-422`). A second entry for a table raises.
- `commit()` is the engine boundary: it closes and fsyncs files written by streamed routes, records
  that the engine completed, and publishes nothing. Engine `write` and `write_batches` are forbidden
  after it (`_transactional_sink.py:69-100`).
- `seal_result(outputs)` is the only post-engine staging entry point. It writes each resident target
  through the same per-format core, count-only consumes targetless outputs, refuses overlap with an
  engine-seen table, refuses a configured target with no output table, closes and fsyncs all
  additions, and changes the state to `SEALED`. It accepts
  a no-commit resident result because full frame deliberately leaves the sink inactive
  (`_pipeline_full_frame.py:269-305`); if engine writes exist, it requires a successful `commit()`.
- After `post_run_verify`, `prepare_vault(path)` delegates to CLI delivery's publication session to
  journal the old vault before `_commit_vault` writes the new one (`run.py:884-892`).
- `publish()` performs no serialization. It delegates the sealed target set to the same publication
  session, which installs the targets, fsyncs their parent directories, and keeps target and vault
  rollback armed until the whole set is durable. A caught `BaseException` restores the prior
  generation in reverse order. RUN-STREAM adds no second journal (`docs/ROADMAP.md:319-322`).
- `TargetSink` is a context manager around `run_pipeline`, `seal_result`, the native check, the vault
  commit and `publish`. Every exit before `PUBLISHED`, including `KeyboardInterrupt`, invokes
  non-raising rollback plus staging cleanup (`run.py:905-908`).
- Row counts for `--evidence-out` and the notify line (`run.py:901`, `:904`) come from
  `rows_written()`, which covers both shapes; `result.outputs` is empty on streamed runs.
- `spill_parent` is a run-wide property because the engine reads it without passing the table
  (`_chunked_output_sink.py:465-482`). It returns CLI delivery's protected run scratch from the same
  publication session, including when there are no targets. Any table may use that private scratch
  stage. The engine spill removes it through `close()` (`_chunked_output_sink.py:492-495`); the
  publication session owns final run-scratch cleanup (`docs/ROADMAP.md:318-322`).
- `committed_table_path(table)` returns the target path, as the engine's sink does
  (`_transactional_sink.py:329-341`), so the
  quarantine aliasing guard keeps working. For a targetless count-only table it returns a reserved,
  nonexistent name under the protected run scratch, which cannot alias a user-selected quarantine
  output; it does not invent a publish target (`_transactional_sink.py:329-341`).
- The context manager, not the CLI's `except Exception`, guarantees `abort()` after any failure once
  the engine has called `commit()` (`_sequential.py:603-619`, `out_of_core/_runner.py:302-313`).
- Formats it cannot stream (`fixed_width`, archive CSV) are written whole at `write` time into
  staging; under `--chunked` they are refused up front by the existing
  `check_target_formats(chunked=True)` (`_targets.py:163`).

### 5.3 The strict switch (engine part E1a, CLI part C2)

`run_pipeline(execution_mode="stream")`. E1a translates `"stream"` once at `run_pipeline` entry into
the existing internal `execution_mode="auto"` plus one immutable `stream_required` field on the run
context. The eight existing comparisons therefore keep seeing a valid existing mode and do not grow
their own interpretation (`_pipeline.py:285`, `_pipeline_context.py:281`, `:511`,
`_transforms_admission.py:84`, `:344`, `:380`, `physical/_snapshot.py:126`,
`_pipeline_routing.py:297-324`). Only the routing choke point reads `stream_required`; `auto` routing
is unchanged.

Before any source data-row iterator opens, that choke point performs strict preflight from the
validated config and source schemas. It calls the existing `check_chunked_compatibility` once for
each mask table and records its coded result, checks that every source has a lazy reader and every
target supports streaming, and computes out-of-core compatibility plus
`fk_out_of_core_dtype_hazard` for an FK fallback
(`_chunked.py:255-374`, `_pipeline_routing_fk_dtype.py:48-131`). Parquet schema comes from footer
metadata without column data (`profile/_readers.py:213-223`). CSV schema uses the declared dialect
and all-text contract before a batch iterator is opened; an admitted CSV job may then make E2's
bounded facts pass through the same reader (`profile/_readers_csv.py:1-7`). A complete chunked pass
selects the lane; an FK chunked refusal may select compatible, hazard-free out-of-core; only a job
with neither streaming result raises `runtime.streaming_unavailable`.

- The auto-chunk lane's row threshold check is bypassed (not set to 0, which
  `require_positive_int` refuses, `physical/_snapshot.py:118`): a chunk-safe table of any size takes
  the lane, as base `--chunked` does today.
- Under `stream_required` only, `_chunked_output_sink` preserves base `--chunked` output grouping:
  Parquet row groups follow `min(chunk_size_rows, 1_048_576)` and do not take the lane's 256 MiB
  early cut (`_chunked_output_sink.py:69-73`, `_targets.py:453-457`). Plain `auto` keeps its current
  row and byte caps. This preserves Parquet bytes for the same chunk size and PyArrow version.
- A mask table the lane takes must have `input.mode == "lazy"` and `output.mode == "streamed"`.
- FK configs. The lane takes no job with FK edges today (`_planner.py:16-18`), and base `--chunked`
  masks each table on its own only after `check_chunked_compatibility` passes for that table
  (`run.py:1512-1521`). Its FK component, `gate_fk_child_edges`, admits only child edges that self-mask
  by a value-keyed strategy under the shared namespace, while the same gate also checks parent-side
  `code_set` and `bucket_perturb` keys (`_chunked.py:300-326`). Under `stream`, E1a extends B7's
  independence rule from no FK edges (`_pipeline_multi_table.py:121-148`) to every mask table passing
  that complete existing compatibility gate. Each table then runs as one per-table unit with the FK
  graph removed only from that already-admitted unit's lane classification, exactly as base
  `--chunked` runs it. Lazy facts are captured after preflight instead of being suppressed merely
  because the job has edges (`_pipeline_chunk_route.py:68-103`).
- An FK config with an edge that gate rejects goes to the out-of-core route only when
  `decide_execution_route`'s out-of-core compatibility holds and `fk_ooc_dtype_hazard` is clear
  (`_pipeline_routing_fk_dtype.py:48-75`), both decided from facts before any source row is read.
  Base `--chunked` refuses these configs, so this only adds configs that run.
- Anything else raises `ExecutionError(code=reasons.runtime.STREAMING_UNAVAILABLE)` before a source
  data-row iterator opens, with the blocking fact from the existing reasons (`auto_chunk.input.reason`,
  `auto_chunk.output.reason`, `decide_chunk_route`'s reason, `gate_fk_child_edges`'s code,
  `out_of_core_reject_code`, the dtype hazard).

The CLI maps the refusal to exit 1 and prints the fact. `--chunk-size` maps to `chunk_size_rows`.
Parity rule for C2: the gate runs base `--chunked` and the new path over the CLI's chunked fixture set
and the FK shapes of 6.3, and lists every config base `--chunked` runs that the new path refuses; a
non-empty list blocks C2 (AT-C2a).

### 5.4 Resources (engine part E1b, CLI part C3)

```text
decoy run CONFIG [--max-memory 8GiB] [--threads 6]
DECOY_MAX_MEMORY=8GiB DECOY_THREADS=6 decoy run CONFIG
decoy setup            # resources section: shows detected values, writes settings.toml
decoy doctor           # one row per resolved value and where it came from
```

`$DECOY_HOME/settings.toml` (default `~/.decoy/settings.toml`, `layout.py:29-31`):

```toml
schema_version = "1.0"

[resources]
max_memory = "8GiB"   # or "auto"
threads = 6           # or "auto"
```

Resolution (`_resources.resolve`), first hit wins per key: flag, env, settings file, `auto`. The
stored reader requires a string `schema_version` matched in full as `<major>.<minor>`, refuses a
missing or unknown major, accepts unknown minors and keys, and checks primitives strictly: TOML
booleans never count as integers, `threads` is a positive integer or the literal `"auto"`, and
`max_memory` is a size string or `"auto"`. The CLI does not import `_MIN_BUDGET_BYTES`; it passes parsed positive bytes and the
engine's existing budget resolver owns the floor (`out_of_core/_budget.py:135-147`). The
values go to `run_pipeline` as `native_threads=threads`, `out_of_core_threads=threads` and
`out_of_core_budget_bytes=memory` (`None` for `auto`, so the engine's one default applies). `auto`
threads is `detect_usable_cpus()`. A memory value below the engine floor is refused by the engine.
The resolved record and each value's source go to the run summary and the `--json` envelope.

`out_of_core_threads` is validated with the other `run_pipeline` knobs, then bound once around
`run_fk_out_of_core`. The binding is run-scoped, not a process global. Every nested caller continues
to use `connect_duckdb(temp_dir=..., memory_limit=...)`; that function reads the bound cap and computes
`max(1, min(user cap or detected usable CPUs, memory_limit // 2 GiB))`
(`_duckdb.py:32-84`). `None` means no user cap, but the detected affinity and cgroup ceiling still
replaces the current raw `os.cpu_count()` host ceiling. The same run-scoped binding records the
distinct applied `(memory_limit_bytes, threads)` pairs from every connection and returns them in the
out-of-core route's resources metrics; no logger or CLI reconstructs them.
The setup section is one entry in the `cli/setup/` section list that SCAN-ML C1 creates
(`2026-11-07-scan-ml.md` 4.6, AT-C1f: "RUN-STREAM can append"); if C1 has not merged when C3 starts,
C3 creates the list with one section and C1 appends.

### 5.5 Run summary (engine part E3, CLI part C2)

```text
Route       auto-chunk lane (lazy input, streamed output)
Why         single mask table with chunk-safe strategies, 16,000,000 rows >= 100,000
Resources   thread cap 8 (auto), native threads not used (companion not installed), out-of-core memory not used
```

From `route_summary(result.quality_metrics)` (E3): `route`, `reason_code`, `reason_text`,
`input_mode`, `output_mode`, `thread_cap`, `thread_cap_source`, `native_threads_applied`,
`duckdb_threads_applied`, `out_of_core_memory_cap_bytes`, `out_of_core_memory_limits_applied_bytes`, and
`native` (`admitted`, `not_installed`, `declined: <code>`). Applied-value fields are nullable and
render `not_used`; they are populated only by the route that owns them. `_native_gate.classify_route`
(`src/decoy/_native_gate.py:417`) keeps its native-intent check and takes the label from this record.

## 6. Enumerations (from the code at the bases)

### 6.1 Exit paths

- `decoy run`: 0 OK; 1 config invalid, bad resource flag or settings value, `--chunked` refused
  (`runtime.streaming_unavailable`), gate refusal; 3 runtime failure (including lazy facts mismatch,
  out of disk); 4 enforce findings (unchanged, `run.py:1238`); 5 capacity (unchanged). A `--native`
  evidence failure or a vault commit failure keeps today's exit code and now also aborts the sink, so
  its "no output was written" stays true (`_native_gate.py:474-478`).
- `decoy setup`: 0; 1 invalid input off a TTY without `--yes`.
- `decoy doctor`: unchanged codes; a resource row is informational.

### 6.2 Routes

Every route `run_pipeline` can take, and what this plan changes on it:

- auto-chunk lane, resident input (`execution/_pipeline_auto_chunk.py:378-395`): unchanged; reached by CSV before E2.
- auto-chunk lane, lazy input and streamed output (`execution/_pipeline_auto_chunk.py:315`): the new default for Parquet (AT-C1a).
- full frame (`execution/_pipeline_full_frame.py:98`): `LazySource` resolved whole per route
  (`_pipeline.py:163-166`); the route never touches the sink (its `commit` at `:305` is inert unless the
  run streamed), so its tables reach the targets through `TargetSink.seal_result(result.outputs)`
  (5.2, AT-C1g).
- sequential (`execution/_sequential.py:219`): sink `write` per table, FK-topological order (protocol docstring).
- out-of-core FK (`execution/out_of_core/_runner.py:106`): sink `write_batches`; budget from
  `out_of_core_budget_bytes`, DuckDB threads capped by `out_of_core_threads` (AT-E1c).
- mixed generate and mask (`execution/_pipeline_mixed_route.py:120-146`): unchanged; lazy keys read by
  `_read_key_column`; streamed or not per `outputs_streamed` (`:247`), so either shape (AT-C1g).
- streamed generation (`generation/_streamed.py:94`): runs only when the sink sets
  `bounded_write_batches`; `TargetSink` does not, so generation stays resident and its tables reach
  the targets through `seal_result` and then `publish` (AT-C1g).
- multi-table dispatch (`execution/_pipeline_multi_table.py:290`): per-table streaming as today, now
  with a sink; under `stream` it also splits FK jobs whose every mask table passes the complete
  chunked compatibility gate (5.3, `_chunked.py:255-374`).
- CLI `--chunked` pandas path: deleted (C2).

### 6.3 FK shapes

The plan changes no FK masking logic. Each shape runs through the CLI with lazy sources and the sink,
and must match the resident run (AT-C1c). Under `--chunked`, an FK config for which every mask table
passes the complete `check_chunked_compatibility` gate is split per table onto the lane, as base
`--chunked` runs it; a gate-rejected job runs on out-of-core only when that route is compatible and
has no dtype hazard; otherwise it is refused before a data-row iterator opens (5.3, AT-E1a;
`_chunked.py:255-374`).

- one parent and one child;
- a three-level chain (the `fk_memory_probe.py` chain);
- one parent with two children;
- a composite key.

### 6.4 Fields

- Engine: `run_pipeline(execution_mode="stream")`, `run_pipeline(out_of_core_threads=int | None)`;
  existing `native_threads` and `out_of_core_budget_bytes` unchanged;
  `detect_usable_cpus(*, fs_root: Path | None = None, affinity: int | None = None) -> int`, preserving
  the platform's injectable test seam (`api/cgroup_cpu.py:231-244`);
  `route_summary(quality_metrics) -> RouteSummary` (frozen: `route`, `reason_code`, `reason_text`,
  `input_mode`, `output_mode`, `thread_cap`, `thread_cap_source`, `native_threads_applied`,
  `duckdb_threads_applied` (sorted distinct tuple), `out_of_core_memory_cap_bytes`,
  `out_of_core_memory_cap_source`, `out_of_core_memory_limits_applied_bytes` (sorted distinct tuple),
  `native`).
- CLI: `--max-memory`, `--threads`; env `DECOY_MAX_MEMORY`, `DECOY_THREADS`; `settings.toml`
  `[resources] max_memory`, `threads`; `--json` `resources` and `route` objects.

### 6.5 Output surfaces

No surface prints a cell value or a path outside the config's own paths.

- run summary card (`src/decoy/cli/run.py:1237`, the `Route` row);
- `--json` envelope (`route` and `resources` objects);
- `doctor` rows and `setup` prompts;
- error lines (reason code plus fact);
- evidence manifest (`--evidence-out`: route and resources added; row counts from `rows_written()`,
  5.2).

## 7. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | refusal text under `--chunked`, route reason text, settings errors | Reasons carry codes, counts and column names only (existing reason registry); settings errors name the file and key, never the raw value beyond the key's own text | AT-E1a asserts the refusal for a canary-bearing source has no cell value; existing raw-value sentries run on the new surfaces | M-E1a: put the first lazy batch's first value in the refusal |
| 2 | Cleanup missing on an exit path | staged temps and publication backups on failure, Ctrl-C, out of disk | the sink context calls non-raising rollback and `abort()` on every exit before `PUBLISHED`, including `BaseException`; target and vault journals restore in reverse order (`_transactional_sink.py:69-103` is the narrower engine protocol) | AT-C1d injects failure before and after each rename and directory fsync; old targets and vault are byte-equal and no temp or backup remains | M-C1d: make `__exit__` handle `Exception` only; M-C1d2: omit vault restoration |
| 3 | State machine and concurrency | sink states (`OPEN`, `ENGINE_COMMITTED`, `SEALED`, `VAULT_PUBLISHED`, `PUBLISHING`, `PUBLISHED`, `ABORTED`); publish order; resources resolved once | `TargetSink` refuses engine writes after `commit`, `seal_result` overlap or missing targets, vault preparation before `SEALED`, target publish before the new vault, publish twice, and every operation after abort; rollback remains armed until all directory fsyncs complete (`run.py:884-892`) | AT-C1e state test; AT-C1h ordering | M-C1e: let `publish` serialize outputs; M-C1h: disarm rollback after the first rename |
| 4 | Route parity and silent fallback | `--chunked` on a non-streamable config; CSV before E2; native absent | one strict preflight calls `check_chunked_compatibility` before a data-row iterator opens; `CsvLazySource` inherits the existing lazy identity instead of adding CSV-only route tests; `stream` refuses instead of falling back | AT-E1a non-streaming refusals; AT-E2a CSV reaches every existing lazy choke; AT-C2b summary | M-E1a2: return resident under `stream`; M-E2d: remove `CsvLazySource` inheritance |
| 5 | Referential integrity | FK jobs with lazy sources and sink | No FK code changes; the shapes in 6.3 compared with the resident run | AT-C1c | M-C1c: hand the sink tables out of topological order |
| 6 | Untrusted producer | settings file, env values, flag values | one size parser with `fullmatch`; strict stored primitives; required string `schema_version = "1.0"` with full-value version parsing; TOML via `tomllib`; engine-owned budget floor | AT-C3a corpus (`-1`, `0`, `true`, `"6"` for threads, `8gb `, `8GiB\n`, `auto2`, 2 TB, missing/numeric/trailing-newline/unknown-major versions, accepted unknown minor, non-table `resources`) | M-C3a: accept `bool` as `int`; M-C3d: version regex uses `$` |
| 7 | Check then use on a path (TOCTOU) | lazy source read twice (footer, batches); target staging | Engine `facts_match` compares footer facts with the handle it reads (`_chunked_input.py:26-29`); staging temps are created `O_EXCL` beside the target by `staged_local_target` | AT-C1f: file replaced between routing and read is refused, exit 3, nothing published | M-C1f: drop the facts comparison in the CLI path by passing a resident table |
| 8 | Weak tests and overclaimed evidence | memory claims | Memory acceptance uses a real process and `VmHWM`, on a VM, with the file at least 8 times the bound; the measurement harness is committed | AT-C1b peak-RSS bound | removing the bound check from AT-C1b is a gate finding |
| 9 | Behavior-preserving refactor drift | output bytes; strict Parquet row-group boundaries; route labels | G6 checks resident output; `stream_required` preserves base chunk grouping instead of the auto lane's 1,048,576-row/256 MiB grouping (`_chunked_output_sink.py:69-73`) | AT-C1a, AT-C2a | M-C1a: use `pyarrow.csv`; M-C2d: keep the auto byte cap under strict stream |
| 10 | Frozen contract drift | `run_pipeline` signature, `ExecutionResult.quality_metrics` keys, CLI flags and exit codes, `--json` envelope, reason registry | Additive only: new `execution_mode` literal, new keyword, new record; `--chunked` keeps its flag and exit code 1 for refusals; registry adds one identity through REG-RENUMBER | compatibility snapshot test; reason registry sentry | M-E1d: rename an existing `execution_mode` literal |

## 8. Acceptance tests (red first)

| ID | Part | Test | Mutation |
|---|---|---|---|
| AT-E1a | E1a | `execution_mode="stream"`: empty, 10-row, default-chunk and over-1,048,576-chunk tables bypass the route threshold and preserve base Parquet row-group bytes; compatible FK tables run as lane units equal to base `--chunked`; parent-side `code_set` and `bucket_perturb` failures come from the same gate and take guarded OOC only if compatible and hazard-free; every final refusal precedes Parquet batches or CSV data; existing mode sites see `"auto"`; `auto` routing and its 256 MiB cap are unchanged | M-E1a, M-E1a2; M-E1a3: keep route threshold; M-E1a4: split FK under `auto`; M-E1a5: call only `gate_fk_child_edges`; M-E1a6: keep auto output grouping under strict stream |
| AT-E1b | E1b | `native_threads=6` reaches the native call (clamped to the knee, clamp recorded) and the auto-chunk lane; `out_of_core_budget_bytes` unchanged in behaviour | M-E1b: drop the clamp record |
| AT-E1c | E1b | OOC: every nested DuckDB connection sees `threads = max(1, min(out_of_core_threads or detect_usable_cpus(), memory_limit // 2 GiB))`; its distinct applied pairs reach resources metrics; two concurrent run contexts with different caps and recorders do not bleed; `None` keeps no user cap but honors detected CPUs | M-E1c: make one nested caller bypass `connect_duckdb`; M-E1c2: use a process global; M-E1c3: infer metrics from the cap |
| AT-E1d | E1b | `detect_usable_cpus()` passes the platform's `api/cgroup_cpu.py` fixtures: injected affinity, cgroup v2 `cpu.max` (`200000 100000` gives 2), v1 quota files, ancestor walk, fake `/proc` and cgroup tree; an unreadable present limit file gives a coded error; a host without `sched_getaffinity` uses `os.cpu_count() or 1`; the platform wrapper preserves `fs_root`, `affinity` and `CpuLimitUnreadable`; `_duckdb.py` uses the detector | M-E1d2: ignore quota; M-E1d3: leaf only; M-E1d4: call `os.sched_getaffinity` unconditionally |
| AT-E2a | E2 | `issubclass(CsvLazySource, LazySource)` is pinned; lazy CSV passes the existing facts, planner, input, materialization and out-of-core type choke points without CSV-only branches; strict preflight rejects before the shared reader yields a data row; admitted batches use the one CSV reader and all-text dtype, equal the resident CSV fixture corpus (quotes, embedded newlines, BOM, CRLF, headerless names), and refuse a file changed between facts and batches | M-E2a: use `pyarrow.csv`; M-E2b: skip identity check; M-E2c: start facts before preflight; M-E2d: remove inheritance |
| AT-E3a | E3 | `route_summary` on each route gives expected configured caps and applied values: flat Python and generate routes mark native and OOC resources `not_used`; native evidence reports its applied clamp; OOC reports applied DuckDB threads and memory limit; unknown keys are ignored and missing blocks give `route="unknown"` | M-E3a: render a cap as applied without evidence |
| AT-C1a | C1a | Plain run, Parquet, CSV and DuckDB sources, Parquet, CSV and `.csv.gz` targets, an empty source: output equal (CSV bytes, decompressed `.csv.gz` bytes, Parquet values and schema) to the base CLI's plain run on the fixture set | M-C1a |
| AT-C1b | C1a | VM, 16M-row Parquet source (605 MB): plain `decoy run` peak RSS under 1 GB and route "auto-chunk lane (lazy input, streamed output)" | removing the bound |
| AT-C1c | C1a | the four FK shapes of 6.3 through the CLI equal the resident run, below and above `out_of_core_threshold_rows` (the latter set low in the test) | M-C1c |
| AT-C1d | C1a | sink failure matrix of class row 2 before and after every target/vault rename and directory fsync, with `Exception` and `KeyboardInterrupt`; a source that is also a target; zero targets with a hold-back spill; and distinct target paths where the second table spills through the run-wide protected scratch | M-C1d |
| AT-C1e | C1a | sink state machine, including resident no-commit, streamed commit then resident-distinct additions, overlap, missing configured target, vault absent/present, `BaseException`, reverse-order rollback, and publish doing no serialization | M-C1e |
| AT-C1f | C1a | source replaced between routing and read | M-C1f |
| AT-C1g | C1b | one run per route shape (auto-chunk streamed, full frame, sequential, out-of-core, mixed streamed and unstreamed, multi-table, generate-only), plus a targetless table with and without quarantine: `seal_result` sees each configured target exactly once, every target is written, the alias guard remains valid, bytes equal base, and evidence row counts include targetless table lengths | M-C1g: omit `seal_result` (full frame writes nothing); M-C1g2: count rows from `result.outputs` |
| AT-C1h | C1b | `_commit_vault` patched to raise before and after replacing an old vault, `--native` with no compiled-kernel evidence, an exception after engine `commit()`, and `KeyboardInterrupt` at each seam: every target and vault are byte-equal to before and no staged temp or backup remains; native text is still printed | M-C1h; M-C1h2: replace the sink context with `except Exception` |
| AT-C1i | C1a | a Parquet source of 1.2M rows whose first column is null for its first 1,100,000 rows: plain `decoy run` streams, the hold-back spills in the protected run scratch and is removed, output equal to the resident run | M-C1i: drop `spill_parent` (raises `HOLD_BACK_SPILL_UNAVAILABLE`) |
| AT-C2a | C2 | `--chunked` on base `--chunked`'s fixture set, chunk sizes on both sides of 1,048,576, a wide table that triggers the auto 256 MiB cut, and the 6.3 FK shapes: every config base runs also runs with byte-identical outputs and an empty newly-refused list; configs base refuses keep exit 1; CSV needs E2 in the pinned release | M-C2a: map refusal to exit 3; M-C2a2: refuse below threshold; M-C2a3: apply the auto byte cap |
| AT-C2b | C2 | run summary card and `--json` route/resources objects per route, including `not_used`, native companion absent, and OOC actuals; no cap is labeled as use without route evidence | M-C2b: print the CLI's old label; M-C2b2: render cap as used |
| AT-C2c | C2 | `_run_chunked_mask`, `iter_source_chunks` and the CLI import of `run_mask_pipeline_chunked` are gone; a sentry fails on a second `run_pipeline` call site in `cli/run.py` (the `tokenize` command, `cli/tokenize.py:347`, and the library `api.py:529` are separate callers and unchanged) | M-C2c: re-add a `run_mask_pipeline_chunked` import |
| AT-C3a | C3 | resolution precedence matrix (flag, env, file, auto, per key), strict stored types and version cells from class row 6, the keyword mapping of 5.4 (`auto` memory passes `None`), and proof that no CLI code imports `_MIN_BUDGET_BYTES` | M-C3a, M-C3b: env over flag |
| AT-C3b | C3 | `decoy setup --yes --json` writes versioned `settings.toml` atomically with detected values; off a TTY without `--yes` exits 1; section order fixed | M-C3c: write in place |

## 9. Hostile corpus (ways a gate reviewer breaks it)

- A Parquet file with one 16M-row row group: the lazy lane reads row groups with an 8 MiB buffer
  (`_chunked_input.py:15-17`); AT-C1b adds this file and records peak RSS (expected higher, still
  bounded by the row group, not the file).
- A source that is also a target of the same run: not refused today (no same-file check in `cli/`).
  The sink stages beside the target and publishes after the run, when every read is done, so the run
  reads the old bytes and the target gets the new ones (on POSIX the open reader keeps the old inode).
  AT-C1d adds the case.
- `--threads 0`, `--threads 100000`, `--max-memory 1KiB`: refused (class row 6).
- `DECOY_HOME` pointing at a symlinked or world-writable directory: the settings file is read with
  `tomllib` only, never executed; a world-writable file is warned in `doctor`.
- A cgroup v1 host with unlimited quota: `detect_usable_cpus` returns affinity (the ported platform
  test fixtures cover v1, v2, nested limits and an unreadable limit file).
- A macOS host without `os.sched_getaffinity`: `detect_usable_cpus` returns `os.cpu_count() or 1` and
  does not treat absent `/proc` or cgroup files as an error (`api/cgroup_cpu.py:203-244`).
- Ctrl-C during `publish` with three targets in different directories: the caught `BaseException`
  restores every installed target and the old vault in reverse order; AT-C1d injects the signal after
  each rename and directory fsync. A process kill inside the short journal window is a V2-LOG crash
  recovery limitation, not an accepted partial relationship output.

## 10. Owner questions (each answerable alone; recommended answer first)

- Q1. The native companion is the speed lever and is not in the CLI install. Recommend: ship it under
  REL-PKG before V1 and treat RUN-STREAM's resources as the switch it uses; until then the run summary
  says "native companion not installed". Alternative: build it into the CLI wheel now.
- Q2. "Config overrides" for resources: recommend settings file plus flags plus env only, no pipeline
  YAML field, because YAML travels to other hosts and resources are per host; a YAML field would also
  change the config hash. Alternative: an optional `run.resources` block outside the hash.
- Q3. The engine's default out-of-core memory budget is 25 percent of host RAM (`_budget.py:137`) for
  every caller that passes none; the CLI's `auto` uses it. Recommend: keep 25 percent in V1 and let
  users raise it with `--max-memory` or the settings file, because a higher default changes the
  platform and library too and two runs at 60 percent overcommit a shared box. Alternative: raise the
  engine default to 60 percent of the effective ceiling minus 1 GiB, for all callers.
- Q4. `--chunked` refusals: recommend exit 1 (usage) as today. Alternative: exit 5 (capacity).
- Q5. May I create a venv in `~/decoy/acct2-cli-mac` on the Mac to run the same sweep there (user
  space, `uv sync`, removed after)? Recommend yes; the roadmap row asks for Mac numbers.
- Q7. Order against CLI delivery (row 61, `docs/ROADMAP.md:321`). Row 61 owns staging and delivery
  for every CLI write, the chunked path included, so the CLI half of RUN-STREAM (C1a to C2) adapts
  row 61's publication session instead of building a second one, and waits for it; row 61 itself waits
  for F22 and POSTSCAN-STREAM. Recommend: keep that order, ship the engine half (E1a to E3, R) now so
  the platform and library get `stream` and the CPU probe early, and have row 61's plan name
  `seal_result`, `prepare_vault` and the run-wide `spill_parent` as entry points RUN-STREAM needs.
  Alternative: fold RUN-STREAM's C1a and C1b into row 61 as one CLI program, so one plan owns the sink.
- Q6. Delete `run_mask_pipeline_chunked` from the engine too? Recommend not in V1: the platform still
  names it (`api/config.py:423`); the CLI stops calling it and a V2-LOG item tracks the engine delete.

## 11. Reuse inventory

| Need | Reused | Where |
|---|---|---|
| Lazy Parquet input | `LazySource`, B6b lazy lane | `profile/_readers.py:214`, `execution/_chunked_input.py` |
| Route choice | `decide_execution_route`, `decide_chunk_route` | `execution/_pipeline_routing.py:194`, `_pipeline_chunk_route.py:43-142` |
| Engine sink boundary | `TransactionalSink` protocol | `execution/_transactional_sink.py:66-99` |
| Cross-target and vault publication | F22 plus CLI delivery's one publication session and sink; C1 adapts it, never copies it | `docs/ROADMAP.md:319-322` |
| Per-format serialization | `staged_local_target`, `write_chunked_output` core | `src/decoy/cli/io/_targets.py:425-467` |
| Memory ceiling and default | `detect_effective_memory_bytes`, `_MIN_BUDGET_BYTES`, `_HOST_RAM_FRACTION` | `execution/out_of_core/_budget.py:339`, `:137-142` |
| Usable CPUs | the platform's `effective_cores` and `cpu_quota_cores`, ported (moved, not copied: P1 points the platform at the engine public facade) | `decoy-platform:api/cgroup_cpu.py:203-249` |
| FK admission for per-table masking | the complete `check_chunked_compatibility`, including its `gate_fk_child_edges` component | `execution/_chunked.py:255-374` |
| Per-table split | B7 multi-table dispatch | `execution/_pipeline_multi_table.py:290` |
| Thread and budget inputs | `native_threads`, `out_of_core_budget_bytes` keywords | `execution/_pipeline.py:139`, `:145` |
| OOC sizing | `resolve_ooc_memory_limit`, `_threads_for_memory_limit`, and the single `connect_duckdb` connection choke point | `_budget.py:398`, `out_of_core/_duckdb.py:32-84` |
| CSV dialect and reader | `resolve_csv_dialect`, `read_csv_source`, `CsvFileSource` | `profile/_csv_reader.py`, `profile/_readers_csv.py:34` |
| App home | `decoy_home()` | `src/decoy/distribution/layout.py:29` |
| Setup sections | SCAN-ML C1 `cli/setup/_sections.py` | SCAN-ML plan 4.6 |
| Native gate | `pre_execution_gate`, `post_run_verify` | `src/decoy/_native_gate.py:306`, `:465` |

New mechanisms: `out_of_core_threads` (one keyword), `detect_usable_cpus`, `route_summary`, lazy CSV
input, `TargetSink`, `_resources.resolve`. Each is the only one of its kind; the CLI's `iter_source_chunks` and
`_run_chunked_mask` are deleted so the chunk reader count goes down by one.

## 12. Placement

Engine (CODEMAP "Where Things Go", `CODEMAP.md:204-237` at `7a61be3c`):

| New code | Goes in | Map row | Nearest neighbour |
|---|---|---|---|
| `route_summary` (`_route_summary.py`) | `src/decoy_engine/execution/pipeline/` (target sub-package; this creates it) | "Pipeline spine and routes" (`CODEMAP.md:218`, fan-out freeze at 104) | `_pipeline_finalize.py` |
| `detect_usable_cpus` (`_host.py`, about 250 lines ported) | `src/decoy_engine/execution/pipeline/`, exported from `decoy_engine.__init__` for the platform | "Pipeline spine and routes" (`CODEMAP.md:218`, fan-out freeze at 104); consumers cross the package through the public API (`:215`) | `out_of_core/_budget.py` (the memory probe) |
| `out_of_core_threads` | the existing `run_pipeline` signature, `out_of_core/_runner.py` run-scoped binding, and `out_of_core/_duckdb.py` connection choke point (`_budget.py`, 609 lines, is not touched) | "Out-of-core FK" (`CODEMAP.md:221`) | `_threads_for_memory_limit` |
| lazy CSV input (`_lazy_csv.py`, `CsvLazySource(LazySource)`) | `src/decoy_engine/profile/` beside `_readers_csv.py`; E2 adds the missing CODEMAP row for source profile readers | map change in E2, because current `CODEMAP.md:213-237` has no `profile/` row | `LazySource`, `CsvFileSource` |
| tests | `tests/unit/execution/run_stream/` (new sub-package; `tests/unit/execution/` is over 25) | "Unit tests" (`:237`) | `tests/unit/execution/derived_visibility/` |

CLI (`CODEMAP.md:42-59`):

| New code | Goes in | Map row | Nearest neighbour |
|---|---|---|---|
| `TargetSink` engine adapter (`_sink.py`) | `src/decoy/cli/io/`, beside and over CLI delivery's central publication session | "CLI source readers and target writers" (`CODEMAP.md:50`); row 61 owns the one publication sink (`docs/ROADMAP.md:321`) | `_targets.py` |
| lazy source building (`_lazy.py`) | `src/decoy/cli/io/` | same row | `_sources.py` (moves here under H-1) |
| `_resources.py` | top-level `src/decoy/` | "Private shared ... primitives used by more than one package" (run, setup, doctor) | `_native_gate.py` |
| setup section `_resources.py` | `src/decoy/cli/setup/` (SCAN-ML C1) | C1's row | `_models.py` |
| tests | `tests/unit/run_stream/`, `tests/e2e/run_stream/` (new folders, like `cli_fmt/`) | map change row added in C1a | `tests/e2e/cli_fmt/` |

`run.py` (1,736 lines) only shrinks: the `--chunked` fork and `_run_chunked_mask` go (about 70 lines),
the source loop moves to `cli/io/_lazy.py`.

## 13. Frozen contracts touched

- `run_pipeline` keyword set: adds `out_of_core_threads`; `execution_mode` gains `"stream"`. Additive; the
  CLI capability-detects the keyword like `_native_gate.run_pipeline_kwargs` does (`:482`) until the
  CLI pins the engine release that has it.
- `ExecutionResult.quality_metrics`: adds `route` and `resources` blocks; existing keys unchanged.
- `TransactionalSink` protocol: unchanged. `TargetSink` adds `seal_result`, `publish` and
  `rows_written` as CLI-side methods (the engine never calls them) and implements the two optional
  members the engine's own sink has, `spill_parent` and `committed_table_path`
  (`_transactional_sink.py:322-341`).
- Engine public API: exports
  `detect_usable_cpus(*, fs_root: Path | None = None, affinity: int | None = None) -> int`.
  Platform `api/cgroup_cpu.effective_cores` keeps that same injectable signature and its
  `CpuLimitUnreadable` error, and delegates through the engine facade (`api/cgroup_cpu.py:30-36`,
  `:231-249`).
- Settings file: required string `schema_version = "1.0"`; strict `resources.max_memory` and
  `resources.threads`; unknown minor versions and keys tolerated, missing or unknown major refused.
- Reason registry: one identity `runtime.streaming_unavailable`, one `resources.cpu_detection_failed`;
  version through REG-RENUMBER at merge.
- CLI: `--chunked` keeps its name and refusal exit code; `--chunk-size` kept; new flags additive;
  `--json` envelope gains `route` and `resources`; the printed route label text changes (pre-GA;
  CHANGELOG).
- `decoy-run-result/v1` (RESULT): `route` and `resources` are added only if RESULT's schema allows
  extension; else a RESULT follow-up (section 15).

## 14. Slices

Bound: at most 10 files and 800 lines per slice.

| Slice | Repo | Contents | Files max | Lines max | Gate |
|---|---|---|---:|---:|---|
| E1a | engine | `execution_mode="stream"` translated once to `auto` plus immutable `stream_required`; strict preflight; no route threshold; base chunk-boundary output grouping; complete-gate FK split; guarded out-of-core force; reason identity; AT-E1a; CHANGELOG | 10 | 760 | Dennis, then Codex |
| E1b | engine | public `detect_usable_cpus` ported from the platform with injectable signature, Linux and macOS fixtures; `out_of_core_threads` run-scoped binding at `connect_duckdb`; native clamp record; reason identity; AT-E1b to AT-E1d | 10 | 780 | Codex |
| E2 | engine | `CsvLazySource(LazySource)` overrides the existing lazy read/facts surface through `read_csv_source(chunksize=)`; config/schema strict preflight before data rows; file identity around facts and batches; subclass guard; CODEMAP `profile/` row; AT-E2a | 8 | 550 | Codex |
| E3 | engine | `route_summary` and the `route`/`resources` blocks; AT-E3a | 5 | 250 | Codex |
| R | engine | release: the next engine release after E1a to E3 merge (cadence of row 76: one release per merged group, not R-d) | 3 | 100 | orchestrator |
| C1a | CLI | `cli/io/_lazy.py`, `cli/io/_sink.py` adapter over CLI delivery's publication session (engine commit boundary, CLI `seal_result`, run-wide `spill_parent`, state machine), `run.py` call site; AT-C1a to AT-C1f, AT-C1i | 9 | 700 | Dennis, then Codex |
| C1b | CLI | sink context over run through the central publication session; resident outputs sealed before native check; vault prepared and committed before transactional target install; row counts; AT-C1g, AT-C1h | 6 | 450 | Codex |
| C2 | CLI | `--chunked` to `execution_mode="stream"`, delete `_run_chunked_mask` and `iter_source_chunks`, summary card and `--json`; AT-C2a to AT-C2c | 7 | 500 | Codex |
| C3 | CLI | `_resources.py`, flags, env, versioned strict settings file, setup section, doctor rows; engine-owned budget floor; AT-C3a, AT-C3b | 10 | 650 | Codex |
| P1 | platform | `api/cgroup_cpu.py` calls the public engine `detect_usable_cpus` with `fs_root` and `affinity` (the module keeps its name and `CpuLimitUnreadable` mapping; its tests stay); lands with the platform's repin to release R | 4 | 150 | Codex |

Order: E1a and E1b, then E2 and E3 in any order; R. C1a needs R (or a dev pin to the engine commit for
the branch, never merged) and CLI delivery row 61, because that row owns the one publication session
(`docs/ROADMAP.md:321-322`); C1a only adds the engine adapter. C1b needs C1a; C2 needs C1b and E2 in the pinned release, because base `--chunked` streams
CSV today (AT-C2a); C3 needs E1b in a release and SCAN-ML C1 (or creates the section list, 5.4); P1 needs R in
the platform's pin. C1a can start on Parquet before E2: plain CSV runs stay resident until the pin
moves.

Which engine release: E1a to E3 go into the first engine release cut after they merge. They do not
wait for R-d (row 76), which the cadence already splits into several releases. The CLI repin row
moves the pin and C1a to C3 land after it.

## 15. Pre-mortem

- The sink changes output bytes for a corner (empty source, all-null column, a Parquet schema with
  dictionary encoding). Guard: AT-C1a runs the existing CLI format fixture set and the empty-source
  rule from `write_chunked_output` (`_targets.py:445-450`).
- Defaults overcommit memory on a shared box. Guard: `auto` keeps the engine's 25 percent default
  (Q3); the summary prints the resolved value and its source; `settings.toml` and `--max-memory` cap
  it.
- A route the plan did not list returns tables in `result.outputs` while also streaming some. Guard:
  `seal_result` rejects overlap, requires every configured target exactly once, and performs all
  remaining serialization before checks; `publish` only renames. AT-C1g covers every route shape the
  engine has today (`_isolated_worker.py:138-165` documents the two current shapes).
- The native knee hides the thread setting (6 threads asked, 4 used). Guard: the clamp is recorded and
  printed.
- CSV streaming diverges from the resident CSV read on a dialect edge. Guard: AT-E2a uses the CSV
  framing corpus F06 already has.
- SUB-RUN (row 57) edits the same call site. Guard: C1a lands first or SUB-RUN rebases onto it; one
  `run_pipeline` call site sentry (AT-C2c) keeps both on one path.

## 16. Follow-ups (recorded, not in V1)

- V2-LOG: delete `run_mask_pipeline_chunked` once the platform stops naming the public entry
  (`src/decoy_engine/execution/_chunked.py:377-391`; Q6).
- V2-LOG: `_fpe.py` uses `os.cpu_count()` outside RUN-STREAM's resource path; move it to
  `detect_usable_cpus` in the V2 cleanup (`src/decoy_engine/execution/_strategies/_fpe.py:353`).
- V2-LOG: `TargetSink` has no `publication_evidence`, so engine-side failure observation cannot
  describe its cleanup precisely (`src/decoy_engine/execution/_transactional_sink.py:40-43`).
- V2-LOG: section 1.4's parenthetical `1.2` after the 219.2 s against 240.2 s comparison is an
  unexplained single-run annotation; the surrounding sentence already gives the supported numbers
  (`2026-11-08-run-stream.md:165`).
- V2-LOG: the roadmap-requested Mac sweep is not measured; Linux tests cover the V1 CPU fallback,
  but Mac performance remains an owner-approved follow-up (`2026-11-08-run-stream.md:152-154`;
  `docs/ROADMAP.md:325`).
- V2-LOG: the platform's separate native-job budget policy is unchanged by RUN-STREAM
  (`2026-11-08-run-stream.md:235`).
- V2-LOG: an uncatchable process kill inside the central publication journal window needs the
  crash-recovery behavior owned by F22, not another RUN-STREAM journal
  (`2026-11-08-run-stream.md:616`; `docs/ROADMAP.md:319-322`).
- V2-LOG: section 6.5 overstates its path rule because CPU-limit diagnostics can name `/proc` or
  cgroup paths; paths are user-written structure under the owner bar, so this is not a value leak
  (`2026-11-08-run-stream.md:549`; `api/cgroup_cpu.py:125-131`, `:138-172`).
- DESIGN follow-up, pre-existing and non-blocking: `run.py` is 1,736 lines at the reviewed base and
  already exceeds the cap; RUN-STREAM removes its chunked fork and source loop, so it shrinks rather
  than creating the overrun (`src/decoy/cli/run.py:1-4`, `:841-878`, `:1449-1509`).
- Stream `fixed_width` and archive CSV targets.
- Cloud sources as lazy sources.
- RESULT schema fields for route and resources if RESULT v1 is closed.
