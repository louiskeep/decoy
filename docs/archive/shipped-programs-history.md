# Shipped log archive: programs and older history

Status: record

Older entries of [../RECENTLY-SHIPPED.md](../RECENTLY-SHIPPED.md), moved here unchanged on 2026-11-05 (program-level history relocated from the old roadmap). Index: [README.md](README.md).

## Execution Consolidation and Native Throughput program (native/Rust masking)

Plan: `decoy-engine: docs/plans/2026-09-09-execution-consolidation-and-native-throughput.md`.
This is the active governing program for native masking. It SUPERSEDES the earlier
`2026-08-26-engine-efficiency-plan.md` (predecessor; its Part 1 Phases map onto this
program's Phase 1-2, its Part 2 onto Phase 5). The five original efficiency-plan
"open decisions" (native language, streaming all-or-nothing, funding, parallel
Phase 0 start, 100M cap) are all RESOLVED. Do not track native work against the
2026-08-26 doc.

### 2026-09-18 -- D9 perf-cert GREEN + per-tier RSS budget (engine PR #164)

The unified-slice lane is now D9-certified on the reference host (GCE n2-standard-8):
`d9_certified: true`, all tiers pass -- 10k RSS 1.025x, 100k 1.071x, 1M 1.121x, wall
~3-4.3x faster (1M: 9.6s vs 41.2s). The peak-RSS gate was made per-tier (1.10x below
1M, 1.25x at 1M+): the 1M lane peaks ~1.12x of legacy, over the old flat 1.10x band,
but that band is a relative regression check, not an absolute-safety limit (absolute
peak ~1.8GB, far under the 6.5GiB host ceiling). This unblocks route activation (the
cert was activation's governance gate). Cert artifact:
`docs/product/release-1-validation-runs/2026-09-18-tb6-50m/`. dennis + Codex FINAL gated.

Naming note: this program's "Phase 4/Phase 5" are DISTINCT from the older
streaming/OOC efficiency work that was once also called "phases 4-5" (see the
"streaming routes + OOC reorder" entry below). They are different work.

### Shipped to engine main

- **Faker widening (generation throughput): DONE + MERGED 2026-09-18 (engine PRs
  #162 harness, #163 addition).** A cross-process/cross-time determinism harness
  (`scripts/faker-determinism/`) certifies which pooled faker `(type, locale)` pairs
  produce byte-identical output across fresh processes (varied `PYTHONHASHSEED`) and
  a committed golden: **183 certified pairs**. On top of it, a locale-aware
  `pool_eligible` adds **29 new reuse-safe PII types** (gendered name/prefix/suffix
  variants, job/company variants, geo scalars) as 135 certified pairs. Measured:
  pooled generation **~2.2M rows/s** (8x past the 267k-rows/s masking kernel), so
  those columns drop from ~10-23k rows/s per-row Faker to ~2.2M at N>=50k. Legacy 10
  types unchanged (global); unique-key types (email/uuid/ssn) stay per-row by design;
  byte-identical where pooling declines. Codex plan+final GO + dennis APPROVE on both.
- **D9 RSS overshoot PART 1 (native single-range pool fix): DONE + MERGED 2026-09-18
  (engine PR #161).** The native derive built the host-sized shared rayon pool even
  for single-range batches (whose per-thread runtime state scales with host cores),
  the core-dependent half of the D9 1M peak-RSS overshoot. `run_range_tasks` now runs
  a single range serially, never constructing the pool; >=2 ranges still use it.
  Byte-identical (thread-invariance parity tests). Dropped 1M peak RSS ~1.22x ->
  ~1.18x. dennis APPROVE + Codex final GO. (PART 2, the pandas-reconstruction
  remainder, is Cam-deferred; see the ROADMAP Phase-4 blocker.)
- **Phase 0 (freeze decision + evidence): DONE, Cam-approved 2026-09-09.** Frozen
  workloads, route inventory, acceptance matrix; Task 0.2 authoritative baseline on
  the reference host (GCP n2-standard-8), all 8 section-15 decisions locked.
- **Phase 1 (optimize the Rust keyed-hash kernel): COMPLETE + MERGED (engine PR #129,
  merge `8d833c30`).** Cached namespace key, GIL release, bounded Rayon. Headline
  result: **100M rows masked in a median 429.9 s at 8 threads** (mask-only, the
  frozen W2 workload, <=600 s contract met with ~170 s margin), peak RSS ~447 MB
  (flat). Hash kernel: 1,280 s baseline -> 299.7 s single-thread (~4.3x) -> 94.8 s at
  8 threads (**~13.5x** total).
- **Phase 2 (compiled deterministic Faker pool selection, `derive_index_batch`):
  COMPLETE + Cam-approved (engine PR #129).** Pool-index selection ~105k -> **~1.37M
  rows/s (~13x)**; 1M-tier total wall 60.9 s -> 13.1 s. (Pool BUILD time is separate
  and unchanged.)
- **Phase 3.2 (native companion bundled in the production image + probe):
  MERGED 2026-09-13** (engine #135 `712aa1ea`; platform #45 `0e13b607`).
- **Phase 4.1-4.4 (unified physical-plan scaffolding): MERGED.** 4.1 design (`c13e1b62`),
  4.2 adapter seam (`31ae76fb`), 4.3 physical-plan compiler (`f2811e32`), 4.4 shadow
  coordinator (`c617b47a`). These are the disconnected physical-plan + shadow-mode
  layers; they do not yet own any production route.
- **Phase 4.5 (unified-slice production lane): MERGED 2026-09-15** (engine #141
  `90b49abf`). A default-OFF engine-only lane (`unified_slice_enabled=False`) that runs
  one bounded slice through the coordinator and returns a result byte-identical to the
  pandas full-frame route. Engine-ready; caller activation deferred to 4.6.
- **D9 perf-cert harness (a 4.6 prerequisite): MERGED 2026-09-15** (engine #142
  `54120b97`). `scripts/bench-unified-slice/bench_compare.py`: a two-arm (flag off vs on)
  statistical driver over the frozen worker, paired ratio + p95 + seeded bootstrap CI and
  peak-RSS ratio. Built but NOT yet run: the offline 10k/100k/1M cert run on a bench node
  is still owed before any 4.6 route activation.
- **Phase 4.6 slice-1 (deterministic-Faker shadow operator): MERGED 2026-09-16** (engine
  #143 `42b5e16f`). Shadow-only parity vs the oracle (no publish, no activation): the
  coordinator selects Faker pool values through the same identity + per-run registry the
  oracle uses, proven cell-for-cell.
- **Phase 4.6 slice-2 (single-table chunked masking parity): MERGED 2026-09-16** (engine
  #144 `794c684e`). Test-layer only (no production src change): proves the coordinator
  matches the chunked oracle cell-for-cell across identical chunk boundaries, over the
  five shadow strategies.
- **Phase 4.6 slices 3-6: ALL MERGED 2026-09-16** (engine #145/#147/#150/#152/#154).
  slice-3 DuckDB out-of-core FK shadow parity (wraps `run_fk_out_of_core` via the Task 4.2
  adapter); slice-4 bounded Group B/C payload operators; slice-5 generation ownership
  (5a generate-only, 5b-i mixed generate+mask, 5b-ii mixed generate-parent->mask-child FK
  + stitch); slice-6 global full-frame path. All double-gated (dennis + Codex), main green.
- **Activation prerequisites: BOTH MERGED 2026-09-17.** The unified-slice exception boundary
  widened to reroute ANY unexpected error on an admitted job to the legacy route (engine
  PR #158 `4369f38c`), and the shared bench driver hardened to fail closed on missing per-rep
  RSS + render None-safe summaries (engine PR #159 `88f8291b`).
- **Generation-throughput workstream: MERGED 2026-09-17.** GP2 pool-based Faker generation
  (engine PR #156 `4501b85f`): an eligible faker column builds a bounded value pool once and
  vector-samples it, ~124x faster at 1M rows, byte-preserving below a 50k threshold, opt-out
  via `pooled: false`. GP1 throughput probe harness (engine PR #157 `08ca57f5`), the tool that
  measures the pooled-vs-per-row crossover (the real sweep + N_THRESHOLD refinement is an owed
  offline follow-up). 5a-faker (engine PR #160): admits the 10 deterministic faker types to
  the generation shadow-parity proof, threading an immutable custom-provider snapshot through
  admission + both generate calls so the two sequential runs cannot diverge.
- **D9 cert RUN 2026-09-17 (result: unified lane FASTER but over the RSS budget).** On a GCE
  n2-standard-8: the unified lane is ~3-4.4x faster at 10k/100k/1M, but peak RSS at 1M is
  ~1.18x the legacy route (budget <=1.10x; 10k 1.03x and 100k 1.095x pass). Wall-time and CI
  gates pass at every tier. The overhead is not in tracked Python (tracemalloc) or Arrow
  (pyarrow-allocated) memory, pointing at native-kernel runtime. Route activation is BLOCKED
  pending a fix-or-accept decision (see the roadmap's current-priority block). A reusable
  `unified-cert` battery was added to the gcp-bench harness (provisions Rust + builds/verifies
  the native companion, then runs `bench_compare.py --require-cert`).

### What the native speedup covers (and does NOT) as of 2026-09-16

- **Covered, merged:** the Rust crate `decoy-engine-native` (`derive_batch` keyed
  hash, `derive_index_batch` pool index, one shared long-lived Rayon pool); native
  scalar kernels for passthrough / redact / truncate / keyed-hash; compiled Faker
  pool-index selection.
- **NOT yet:** it is a **bounded slice** (single non-FK table, fixed Arrow schema,
  the four scalar strategies + pooled Faker), **default-OFF** (`native_route_enabled=
  False`), and **not the customer default**. The opt-in Route 4a excludes hash; the
  optimized hash kernel has no production caller until Phase 4's coordinator
  activates it. redact/truncate are native but still single-threaded (the new serial
  floor, a Phase 5 target). FPE, Faker providers/generation, date_shift, bucketize,
  code_set, formula, nested-JSON, text/NER, and arbitrary-Python providers all remain
  on the pandas oracle.

Bottom line: the Rust work is real, merged, byte-parity-clean, double-gated, and hit
its headline target as a benchmarked capability. It becomes the shipped customer
default only as Phase 4 (4.5+) activates it.

---

## Older streaming / out-of-core efficiency work (NOT the native-throughput program)

- **Streaming routes + out-of-core reorder + batched NER: SHIPPED 2026-09-09.**
  (Previously labeled "engine efficiency phases 4-5" on the roadmap; relabeled here
  to remove the collision with the native-throughput program's Phase 4-5.) Engine-
  efficiency streaming routes and out-of-core reorder with a native columnar lane
  (engine PR #126); batched NER inference for ~5x text-masking speedup, byte-identical
  (engine PR #127); OOC capacity preflight recalibration with advisory build-floor,
  hard fan-in, recalibrated slope (engine PR #128). GCP curve on main: 100M @ 8GB,
  200M @ 16GB, 400M @ 24GB peak, parity-clean on the streaming path. A faker-payload
  GCP run confirmed the OOC route rejects faker by design (falls back to
  sequential/full-frame): the 100M-to-8GB streaming win covers FK-relational plus
  hash/redact/truncate, NOT faker/pool payloads.

---

## Programs and features (relocated from the roadmap's inline history)

- **§TEST Enterprise-readiness program: COMPLETE 2026-07-29..30 (behavior under
  load), plus the T1+T2 test-suite audit.** TEST-1/2/3/4/5/6/7/9/10 all DONE and
  merged; verdict CONDITIONAL GO (acceptance test-flight 53/53 green with matching
  fingerprints; five of six readiness gates MET, gate 1 partial pending the
  100M/200M capacity run). TEST-3 found and fixed three real cleartext-leak paths in
  the `nested` JSON strategy. The T1+T2 coverage audit reset baselines (engine 87.6%
  / platform 76.6%) and caught platform `main` un-runnable against engine `main` for
  ~11 days (fixed, suite 0 -> 3222 passing); T3-T6 deferred. Remaining tail: TEST-8
  (web E2E, needs Playwright infra) and the 200M capacity run (BENCH). Full detail:
  `docs/product/enterprise-readiness-go-no-go.md`.
- **§TQ Test-Quality Program: crown jewels + focused sweep + execution substrates
  SHIPPED 2026-07-26..28 (engine PRs #113, #114, #115, #116).** TQ-0 measure-first
  mutation grading with mutmut; ~33 modules to logic-100% in #113 (crypto + RI/FK at
  the 100% bar, ~15 execution strategies, ~7 transforms, codeset config/index); #114
  closed the execution-SUBSTRATE tier mutmut had mis-scored (a `scripts/tq_mutate.py`
  post-processor re-adjudicates survivors); #115/#116 closed the last residuals plus
  the RI correctness fix (`_fk_keys.py`: equal-valued float and Decimal now mint the
  same FK join token). All dennis- and Codex-approved. In-process-gradeable tier
  COMPLETE. TQ PAUSED at diminishing returns (Cam 2026-07-28); spawn-boundary +
  codeset_etl / plan / env-gated tiers DEFERRED to pre-release (engine tq-findings #15).
- **§DPS Differential Privacy Synthesis: marginal DP SHIPPED 2026-07-24 (engine
  PR #110).** DPS-CODEC 0.5.0 + CLI cert-stack + `decoy fit` on `fit_dp_snapshot`;
  marginal DP over numeric AND categorical via OpenDP mechanisms + Google
  `dp_accounting` PLD composition; nine `dp_*` modules, crown-jewel graded. Follow-ons
  (not current): platform-side DP integration (rides the held platform release) and
  DPS-4 / PrivBayes (joint/correlated DP).
- **OOM / capacity checker v1: SHIPPED (engine PR #112, 2026-07-25).**
  `enforce_ooc_memory_preflight` productized into a customer-facing capacity estimator
  + CLI wiring: refuses early with "needs ~X GB, you have Y" instead of OOM-crashing.
- **§OOC memory architecture: PRODUCT DECISION 2026-07-22. Tiered RAM guidance
  replaces infinite-scale streaming.** Routing / disk-aware admission / phase-aware
  budgeting from engine PRs #86/#87/#88/#94 remains shipped. The single-read OOC-B
  (PR #107) was reverted by PR #108 after the 200M@8GB GCP proof showed peak RSS ~21GB;
  main runs the O(parent) relation path. Deterministic/keyed FK masking is unlimited
  at any row count (flat memory); full synthetic remap + linked-table generation are
  RAM-tiered (published sizing guidance); OOM safety net is the graceful preflight.
  Bounded external-reorder work SHELVED on `feat/ooc-b-external-reorder` (`67c3bd6`).
  Sizing guide: `docs/guides/sizing-and-hardware.md`.
- **§HC healthcare de-id + code sets: COMPLETE 2026-07-21.** HC-2/3a/3b/5/6/7 merged;
  HC-1 public-domain corpora: ETL infra (#100), ICD-10-CM (#101), O(1) mask selection
  (#102), HCPCS Level II (#103), MS-DRG (#104), ICD-10-PCS (#105), full-corpus ETL doc
  (#106); NDC parquet present. GA-corpus-freeze blocker cleared. HC-4 parked (compliance).
- **§TX free-text NER: TX-1 + TX-2 shipped.** Activate text_redact NER (#90); wire
  spaCy NER into text_mask so person/location synthesize (#92).
- **§MLF ML post-merge hardening: mostly shipped.** CI ml-gate (#81); wheel-include
  pack + require pack signatures, DE-07/DE-04 (#82/#83); corpus expansion + isotonic
  calibration, MLF-4/5 (#84); doc staleness MLF-7 (#85).
- **§TEST / §BENCH: partial.** CodSpeed harness + Mergify JUnit wiring, inert
  (#96/#98, TEST-1); canonical hard-caps sweep (#95, TEST-4); per-strategy payload
  probe knob (#99, BENCH-CODE-1). GCP BENCH-R1 sizing runs 1-4 (100M + 200M@8/16GB).
- **ML foundation (ML0-ML3.2):** 2026-06-27: LightGBM `lgbm-v1`, 11 semantic types,
  macro-F2 0.979, HMAC-signed packs, `POST /api/v2/classify-fields` (admin-gated,
  off by default, advisory). Live-but-off; no operator UI (ML3.3 open).
- **Crypto GA delivery** (DE-01/02/03/11): engine main 2026-07-14: whole keyed
  surface rekeys off a secret, fail-closed at GA.
- **Backlog-buildout (SP-01..SP-28):** 2026-06-29; **Capability-review A-H:**
  2026-07-03; **FK-RI memory-scaling** `run_sequential` (~25-27% peak-RSS cut);
  **50M-row OOM + throughput hardening** (#49/#50); **DE-10 chunked-FK dtype family**
  (#74). Detail in the platform repo's `docs/archive/backlog-2026/sprint-ledger.md`.
