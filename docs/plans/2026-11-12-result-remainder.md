Status: plan

# RESULT remainder: run result document, exit 6, capacity widening, F29 C1 (roadmap row 62)

Rules consulted: `/home/cam/dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`,
`development-loop.md`, `cross-cutting-concerns.md`, `api-and-compatibility.md`, `testing.md`,
`architecture.md`, `catalogs/recurring-defects.md`; CLI `CODEMAP.md`; engine `CODEMAP.md`.

Bases (2026-11-12): CLI `origin/main` `ae58f68`, engine `origin/main` `c38f17cd` (every engine
file:line reference below is unchanged at `ad63ba1b`; two line counts differ and section 8
gives both), CLI pins
`decoy-engine==0.22.0` (`pyproject.toml:122`). Source plans: the gated RESULT handoff
(vault `10_Projects/decoy/handoffs/phase0.5/p05-result-build-handoff.md`, revision 4, owner
questions Q1 to Q6 confirmed 2026-11-06), the F29 remainder plan (engine
`plan/f29-errors-progress-remainder` `a26994bf`, slice C1 only), the DELIV plan (engine
`plan/deliv` `037ab1ac`, `docs/plans/2026-11-12-deliv.md`). This plan
replaces the handoff's E2, E3, C1a, C1b and C2 for building. Where it differs from the handoff,
section 3 says why. Risk: R2 overall (frozen exit taxonomy, a public `--json` member, a frozen
artifact tag); per-slice tiers in section 10. Out of scope and not planned: F29 platform slices
P1 and P2 and F31 P8 (parked with Platform V1); LIB L3a storing the record (row 37); LIB L5b
`links.log` (row 37 group); best-effort delivery itself (DELIV, row 61).

## 1. Frame

### 1.1 What exists, what consumes it, what V1 still needs

| Part | Exists today (file:line on origin/main) | Consumed by | Missing for V1 |
|---|---|---|---|
| Run result model | Engine `src/decoy_engine/run_result/_model.py:362` `RunResult` write model, `RunResultRead`, value-free leaf types, `RUN_RESULT_SCHEMA`; merged as engine #397 (`4c6ca215`), shipped in `v0.19.0` and in the pinned `v0.22.0`. Constructor sentry `tests/sentry/test_run_result_constructor.py:15` names `run_result/_build.py` as the only builder, which does not exist yet | LIB L1a kind `run-result` (`src/decoy_engine/records/_kinds.py:118`); `records/_envelope.py:17`, `_joblog.py:23` reuse the leaf types | Nothing in the model. E1 is fully done |
| Status and exit derivation | `src/decoy_engine/run_result/_outcome.py:27` `derive_outcome` (cancelled, failed, partially delivered, findings, succeeded; exit integers from the caller's map) | Nothing calls it. The CLI decides exits in several places: `src/decoy/cli/run/_errors.py:142` to `:208`, `_render.py:119`, `:124`, `:177`, `_evidence.py:57`, `_notify.py:120`, `_prepare.py:174` | A CLI exit map and every `decoy run` exit read through `derive_outcome` |
| Run result document (builder, projection, collector) | Not built. Handoff parts E2 and E3 never started (READY-STATUS 2026-11-08 rows 19 and 20; no branch on either remote) | n/a | Engine projection, builder and collector; the CLI build of one document per run and the `--json` `result` member |
| `--json` failure `reason` (F29 C1) | Not built. The failure envelope is `src/decoy/cli/run/_errors.py:258` to `:287` (`command`, `status`, `config`, `mode`, `error`, plus `error_kind` and `code` for capacity, native and missing extra). No `reason_from_exception` reference anywhere in `src/decoy/` | n/a | The `reason` member, the attach rule, one reason call |
| Exit 6 | Not built. `src/decoy/cli/exit_codes.py:100` `__all__` has six names (0 to 5); `src/decoy/ci/contracts.py:119` `EXIT_CODES` and `:123` `EXIT_PRECEDENCE` are hand-written without 6; `src/decoy/cli/explain.py:452` says "one of six exit codes" (topic at `:448`) | `decoy ci` report models validate `exit_code in EXIT_CODES` (`contracts.py:334`, `:359`, `:397`) | The constant, the map entry, the taxonomy docs. Exit 6 becomes reachable only when DELIV C3 adds best-effort; nothing in this row makes it reachable |
| Capacity widening | Partly done. Engine `src/decoy_engine/errors.py:514` `CAPACITY_REASON_CODES` holds three codes: `generation_budget_exceeded` (engine #424, owner 2026-11-08 GEN QA "over-capacity row_count = exit 5"), `out_of_core_insufficient_memory`, `out_of_core_fanin_exceeds_budget`. The CLI reads it through `src/decoy/cli/gate/_run.py:31` `capacity_codes()` at `_errors.py:122` (ExecutionError) and `:127` (any coded DecoyError). A bare `MemoryError` already exits 5 with fixed text (`_errors.py:131`, `:144`, `:218`). The old `run.py` `_CAPACITY_CODES` copy is gone | `gate/_run.py:86` (picks the capacity finding for the gate envelope); engine pin test `tests/unit/generation/test_generation_floor.py:481` | Four owner-confirmed codes (handoff Q3): `out_of_core_faker_pool_budget_exceeded`, `out_of_core_reorder_budget_too_small`, `pool_exceeds_cache_budget`, `isolated_worker_out_of_memory`; the new identity `decoy.process_out_of_memory` for `MemoryError` (reason registry, needs engine #506); a walk that classifies every memory, budget or capacity code |

Owner decision that supersedes the handoff: Q3 listed `generation_budget_exceeded` as "no,
unchanged"; the owner's 2026-11-08 generation QA call made over-capacity generation exit 5, and
engine #424 put it in the set. It stays in.

Already closed by other rows since the handoff (no work here): the evidence write failure
exits 3, not a traceback (`src/decoy/cli/run/_evidence.py:51` to `:57`, the handoff's Q6); the
evidence `run_id` is the run's `invocation_id` (`_evidence.py:44`, minted at
`src/decoy/cli/run/_flow.py:32`); atomic writes exist (`decoy._atomic`, `write_local_target`);
`pipeline_config_hash` is public (`src/decoy_engine/plan/__init__.py:37`).

### 1.2 Problem

A `decoy run` leaves no machine-readable record of what happened. The `--json` failure envelope
cannot tell configuration, execution and publication failures apart. Exit decisions live in
several call sites with their own tables, so DELIV's exit 6 and DUP-FREEZE's "one
exception-to-exit-code map" (row 24zf) have nowhere to land. Four memory refusals still exit 3.

## 2. Guarantee

1. Every `decoy run` that gets past Click parsing and `setup_output` emits exactly one
   `decoy-run-result/v1` document as the `--json` member `result`, on success, findings, every
   failure category, preview and Ctrl-C. Limits: Click parse errors (exit 2), `setup_output`
   conflicts (exit 1), the managed-runtime refusal in the root callback (exit 3), an unexpected
   exception raised after the run's `try` has closed (root crash guard, X14, exit 1), SIGTERM,
   SIGKILL, a second Ctrl-C while the document is written.
2. The engine owns the shape, the projection, the one constructor and `derive_outcome`. The CLI
   passes typed facts and never assembles the document by hand.
3. Every exit of `decoy run` outside the limits of item 1 comes from `derive_outcome` with one
   map, `RUN_EXIT_MAP` in `src/decoy/cli/exit_codes.py`. No exit integer of any path changes in
   this row except the capacity widening (3 to 5 for the four codes), which is labelled breaking
   (pre-1.0) in the changelog. `derive_outcome` raises `ValueError` for a key outside the map
   (`_outcome.py:53` to `:56`); nothing catches it, so a map gap would reach the root crash guard
   (exit 1). AT-X2 keeps the map total, so a gap is a red test, not a runtime path.
4. The `--json` failure envelope carries `reason` (the engine's registered reason payload) for
   engine-raised failures, computed from the exception as raised; CLI-owned refusals carry none.
   The attach rule is F29 C1's (3.3). The document's `failure.reason` is the same payload.
5. Value-free: no cell value, exception text, absolute path, display text or key material in
   `result`, `result_status`, `reason` or any line this row adds.

V1 bar: only a function break, data loss, a leak to a non-admin or a cascading design problem
blocks. Everything else goes to V2-LOG (section 13).

## 3. Design

### 3.1 Changes from the gated handoff, and why

| Handoff item | This plan | Why |
|---|---|---|
| `DeliveryRecorder` in engine E2, filled by `_targets.py` writers | Dropped. The builder takes a typed `DeliveryFacts` input. Before DELIV the CLI fills it from the publication ledger (`src/decoy/cli/run/_context.py:147` `published_members`, `ctx._published`); DELIV fills the same input from its sink receipt | DELIV owns per-table delivery facts ("DELIV fills them; RESULT renders", DELIV plan 2.3). A recorder would be a second delivery-facts copy and would edit `io/_targets.py`, which DELIV C2a changes |
| `failure_facts` in engine E2 | Dropped. One CLI function `_failure_reason(exc)` in `run/_errors.py` (built in C-REASON) is the only `reason_from_exception` call in `src/decoy/`; the builder takes the `ReasonRecord` | Without the recorder the engine helper has one caller. One call site in the CLI, guarded, is the choke point |
| `reasons/_capacity.py` `CAPACITY_IDENTITIES` | Widen the existing `errors.CAPACITY_REASON_CODES`; add the reasoned exclusion map beside it | The set already exists and the CLI already reads it; a second set would be a copy |
| Warning codes `warning.run_result_build_failed`, `warning.run_result_write_failed` in the reason registry | CLI closed list `CLI_WARNING_CODES` (`src/decoy/cli/run/_context.py:26`) gains `run_result_build_failed` and `run_result_write_failed` | Both are CLI-side events; the closed CLI list is the existing registry for CLI warnings; no wait on engine #506 |
| `_run_outcome.py` (flat `cli/`) | `src/decoy/cli/run/_result.py` | The flat `cli/` folder is frozen; `decoy run` lives in `cli/run/` |
| `EXIT_MAP` in `_run_outcome.py` | `EXIT_PARTIAL` and `RUN_EXIT_MAP` in `exit_codes.py` | Matches DELIV 2.3 and 7.1; one place for exit integers |
| C1b `--evidence-out` exit change, `run_id` unification | Dropped | Already on main (1.1) |
| One E3 slice | E3a collector, E3b chunked events | Size; E3b touches the chunked entries other open PRs edit |

### 3.2 Engine

- `run_result/_project.py` (E2a): `CollectedFacts` (frozen: per table phase start, finish rows,
  error seen, final rate rows, elapsed; aggregate phase error; phase durations), `DeliveryFacts`
  (frozen: `mode`, `vault`, `tables: Mapping[str, TableDelivery]`, and the named constructor
  `DeliveryFacts.not_applicable()` for a preview). The per-table entry is the model's own
  `run_result.TableDelivery` (`_model.py:282`: state, format, output, reason, dropped_because),
  so no third delivery type exists beside it and DELIV's `delivery.TableDelivery`
  (`src/decoy_engine/delivery/_plan.py:24`). E2a exports `TableDelivery` from
  `decoy_engine.run_result`, so the CLI builds the entries without importing `_model`. AT-P5
  pins only that `DeliveryFacts.tables` values are `run_result.TableDelivery` instances; the
  agreement of DELIV's `DeliveryState` with `TableDeliveryState` stays with the existing
  `tests/unit/delivery/test_vocabulary.py:17`. The adapter from DELIV's `DeliveryDecision` plus
  `DeliveryReceipt` to `DeliveryFacts` is DELIV's: DELIV C2a writes it as the body of the one
  CLI provider `_result.delivery_facts(ctx)` (3.3), in the `_result.py` lane slot section 10
  gives it, and picks where any engine helper lives. The rule RESULT needs from it: a table reads `delivered` only when the decision says `delivered` and
  the receipt is `delivered` or `uncertain` (the pointer moved, DELIV AT-12); on a `nothing`
  receipt every such table reads `none`, so `delivery.outcome` can never say delivered for a
  run whose pointer did not move. `ProjectedTables` and
  `project_tables(*, config, execution_result, facts, delivery)`. One rule
  for `rows_out` on every route: `ExecutionResult.outputs`, else the phase finish rows, else the
  final rate sample, else null; `rows_source` says which. Outcome rule as the handoff (E2
  "Precedence"). A table whose delivery fact is `failed` is `failed` with that reason even when
  execution succeeded. `delivery.outcome` is derived once here: every target table delivered is
  `delivered`, some is `partial`, none is `nothing`, no target table or a preview is
  `not_applicable`.
- `run_result/_build.py` (E2b): `FailureInput(category, reason: ReasonRecord | None,
  error_class: str | None)`; `build_run_result(*, tables, execution_result, failure, config_ref,
  producer, invocation_id, exit_map, delivery, blocking_failed, native, chunked, links,
  started_at, finished_at, elapsed_s, phases)`: the only module that constructs `RunResult`. It
  calls `derive_outcome` once with the caller's `blocking_failed`, projects checks (codes and
  counts only; `blocking` equals `blocking_failed`), route and warnings, and returns the frozen
  model. The builder never re-decides blocking.
- `run_result/_collect.py` (E3a): `RunResultCollector`, a `ProgressSink` whose `on_event` never
  raises and keeps typed counters; `snapshot() -> CollectedFacts`.
- `execution/chunked/_progress.py` (E3b, new sub-package `execution/chunked/`; the flat
  `execution/` folder is frozen at 104 modules by `tests/sentry/layout/test_package_fanout.py:32`,
  whose comment names `execution/chunked/` as the next route cluster): `observe_chunked(table,
  chunks)` with manual `phase_start` and `phase_finish` (never the `phase()` context manager)
  plus `count_rows`; `run_mask_pipeline_chunked` (`src/decoy_engine/execution/_chunked.py:379`)
  calls it with net zero lines in `_chunked.py` (600 at `c38f17cd`, the goal), and
  `native/_chunked_entry.py:660` calls it in place of its direct `count_rows`.
- `errors.py` (E-CAP): `CAPACITY_REASON_CODES` gains the four codes; `CAPACITY_EXCLUSIONS:
  Mapping[str, str]` (code to reason) holds every other memory, budget, capacity or OOM code,
  including `fk_full_frame_oom_risk_rejected` and `fk_full_frame_oom_risk_rejected_estimated`
  (`src/decoy_engine/reasons/runtime/_part1.py:189` to `:194`; OQ-5).
- Exports: the new names are exported from `decoy_engine.run_result` only (its `__all__` and
  docstring), not from the top-level `decoy_engine/__init__.py`, which sits at the 600-line goal.
  The CLI imports them from `decoy_engine.run_result`, as it does other public sub-packages.
- Reason registry (E-OOM, after #506): `decoy.process_out_of_memory` (`since=UNRELEASED`,
  retry `environment_repair`), a `_FIXED` row `("builtins", "MemoryError", ...)` in
  `src/decoy_engine/reason_adapter.py:99`, and the code in `CAPACITY_REASON_CODES`.

### 3.3 CLI

- `exit_codes.py` (C-EXIT): `EXIT_PARTIAL = 6` and `RUN_EXIT_MAP: Mapping[tuple[str, str | None],
  int]`: `(succeeded, None)` 0, `(findings, None)` 4, `(partially_delivered, None)` 6,
  `(failed, usage)` 1, `(failed, parameter)` 2, `(failed, runtime)` 3, `(failed, capacity)` 5,
  `(cancelled, cancelled)` today's Ctrl-C status (OQ-1). `(failed, parameter)` reuses the
  integer of `EXIT_WARNINGS` (2); the README and `decoy explain exit-codes` say that 2 also means
  a Click usage error. `ci/contracts.py` `EXIT_CODES` is
  derived from the `EXIT_` integers in `exit_codes.__all__`; `EXIT_PRECEDENCE` is
  `5 > 3 > 1 > 6 > 4 > 2 > 0` (handoff Q2, owner confirmed).
- `run/_errors.py` (C-EXIT, C-REASON): today's type dispatch at `_errors.py:142` to `:208`
  returns a category, not an integer; the exit is `derive_outcome(...).exit_code`. The exit-1
  tuple becomes `_usage_types()`, used by both the category rule and the reason attach rule.
  C-REASON builds F29 C1 (5.1) as written there: bind `engine_exc = exc` before the
  missing-extra and NER rewrites at `_errors.py:69` to `:81`; one helper
  `_engine_family(exc) -> bool | None` is the only CLI caller of `registered_families()`;
  `_cli_refusal_types()` is the `_usage_types()` members that are not an engine family, plus
  `_VaultWriteError` (`run/_vault.py:20`, exit 3) and `PreRunCheckError` (gate refusals, exit 1
  or 5). Rule, stated once: **attach `reason_from_exception(engine_exc).to_payload()` unless
  `exc` is in `_cli_refusal_types()` and `engine_exc` is not an engine family.** Both sets are
  computed lazily in the failure path, never at import, and the classifier runs before the
  `exc` test (F29 C1 evaluation order). `_failure_reason(exc)` holds all of it in one guard and
  returns None on any error. Every typed refusal C-DOC2 adds joins `_usage_types()` (exit 1) or
  `_cli_refusal_types()` (other exits), so it carries no reason; C-DOC2 updates the AT-R7 pin.
- `run/_render.py` (C-DOC1): one `_blocking_failed(ctx) -> bool` replaces today's two copies of
  the enforce decision (`_render.py:56` in `commit_latest` and `:84` `_enforce_fires`) and is the
  builder's `blocking_failed` input. DELIV C5 extends that one function for a post-scan block
  (DELIV 6.2 rows 6 and 7, exit 4); it adds no second input.
- `run/_result.py` (C-DOC1, new): reads the run's facts off `RunContext`, builds `DeliveryFacts`
  in one function `delivery_facts(ctx)`, the only `DeliveryFacts` construction in `src/decoy/`
  (the `not_applicable()` constructor included; AT-D10), calls `project_tables` and the one `build_run_result(`, and returns the
  payload and `result_status` (`{"document": "built"|"failed", "file": "written"|"failed"|
  "not_requested", "code": <CLI warning code or null>}`). A build failure falls back to
  `derive_outcome` directly with the same inputs and the code `run_result_build_failed`.
  `_result` sits after `_vault` and before `_execute` in the package `ORDER`, so it imports only
  `_context`, `_notify` and `_vault`. `_errors`, `_render`, `_evidence` and `_flow` call it with
  the prebuilt legacy payload (`_seed_warnings` and `_where_written` stay in `_render`), the
  category and the reason. `_notify` and `_vault`, which come before it, raise typed refusals
  and never call `finish`.
- `delivery_facts(ctx)` before DELIV reads the ledger: a table in `ctx._published` is
  `delivered` with its format and run-relative output; every other configured table is `none`
  with no reason. DELIV C2a replaces that body with the decision-plus-receipt rule of 3.2 and
  fills `failed`, `withheld` and `dropped` with their reason and `dropped_because`; no other
  module builds delivery facts, and the projection (AT-P7) already renders every state.
- C-DOC2 moves every `emit_json(` and `raise typer.Exit(` of `decoy run` into one
  `_result.finish(ctx, outcome)` so the early refusals, the evidence failure and Ctrl-C produce
  the document. Exit integers stay as today. Each new typed refusal is raised after its `except`
  block closes, so it carries no `__context__`. AT-O6 proves it; the existing
  `tests/sentry/defects/test_exception_context.py` only ratchets `raise ... from None` inside an
  `except` block and does not see a plain raise there.
- C-DOC2 moves `ctx._run_started_at` and `ctx.started` to the first lines of `execute`
  (`src/decoy/cli/run/_flow.py:30`), before `parse_channels`, so X3 to X5 have timings. A path
  that stops before the config is read or the run starts takes value-free defaults: `config`
  and `pipeline_kind` null; `route` with `execution_mode`, `route_reason` and `native` null and
  `chunked` from the flag; `delivery` from `DeliveryFacts` with no tables, `mode` `in_place` (the mode before a config
  names one), `vault` `not_used` and outcome `nothing`; no tables, checks,
  warnings or phases; every `links` member null. AT-O1 asserts them on X3 to X5.
- C-DOC3 adds `--result PATH`, written through `write_local_target` (`REPLACE`). The path joins
  the one collision rule: C-DOC3 adds `("--result", ctx.result)` to the typed side files in
  `_prepare._placement` (`src/decoy/cli/run/_prepare.py:246` to `:256`), so
  `resolved_output_collisions` (`src/decoy/cli/io/_placement.py:118`) refuses a result path
  equal to a target, a quarantine file, `--evidence-out` or `--vault` before any row is read,
  symlink and hard-link aliases included (AT-F4). Whether it counts as a `replaces_final` writer
  like `--vault` follows how `write_local_target` `REPLACE` treats a final link; C-DOC3 STEP
  ZERO reads that and the `OutputPlacement` docstring (`_placement.py:36`) gains the flag.
- Legacy `--json` members keep their values; `result` and `result_status` are added.

## 4. Behaviour

| # | Case | Exit | `result.status` | `failure.category` | `reason` in envelope |
|---|---|---|---|---|---|
| B1 | success | 0 | `succeeded` | null | absent |
| B2 | `--post-validate-enforce` with failed checks | 4 | `findings` | null | absent |
| B3 | config, compile or CLI usage refusal inside the run | 1 | `failed` | `usage` | engine family only |
| B4 | bad `--master-key` or `--key-label` (`BadParameter`) | 2 | `failed` | `parameter` | absent |
| B5 | engine runtime error | 3 | `failed` | `runtime` | yes |
| B6 | engine-raised capacity code in `CAPACITY_REASON_CODES`, or `MemoryError` | 5 | `failed` | `capacity` | yes (MemoryError: after E-OOM) |
| B6g | gate capacity refusal (`PreRunCheckError`, exit 5) | 5 | `failed` | `capacity` | absent (CLI-owned) |
| B7 | evidence write failure after outputs | 3 | `failed` | `runtime` | absent (CLI-owned) |
| B8 | Ctrl-C | today's status (OQ-1) | `cancelled` | `cancelled` | `run_cancelled` |
| B9 | `--rows` preview | 0 | `succeeded` | null | absent; `delivery.outcome` `not_applicable` |
| B10 | best-effort partial (DELIV C3, not this row) | 6 | `partially_delivered` | null | absent |
| B11 | document build raises (a defect) | the B1 to B9 exit | absent; `result_status.document` `failed` | n/a | unchanged |
| B12 | `--result PATH` write fails | unchanged | unchanged | unchanged | unchanged; one stderr warning |

## 5. Failure modes and enumerations

### 5.1 Class table

| # | Class | Structure that closes it | Proof (test or sentry) | Mutation that turns it red |
|---|---|---|---|---|
| 1 | Value-bearing output | The model's value-free leaf types (E1); `_failure_reason` passes only the `ReasonRecord`; table names through `approve_name`; outputs as `RelPath` or file name | AT-D3 canary over `result`, `result_status`, `reason`, stderr; AT-R4; AT-B3 | copy `ctx.config_str` into `config.name`; read `exc.code` into the reason |
| 2 | Cleanup missing on an exit path | One `finish` reached from every exit path inside the run (C-DOC2), `finally` order kept in `_flow.py`; the post-`try` crash (X14) is a named limit through the root guard | AT-O1 path matrix; AT-O3 Ctrl-C; AT-O5 | emit the bad-notify envelope before `finish` |
| 3 | State and concurrency | `RunResultCollector` keeps only typed counters and never raises; one document per run; the build fallback; one blocking decision (`_blocking_failed`) | AT-K3, AT-D4, AT-O4, AT-D9 | let `on_event` errors escape; emit twice on a build failure |
| 4 | Route parity and silent fallback | One `rows_out` precedence rule for every route; `observe_chunked` for both chunked entries; unknown route values map to `other`, never dropped | AT-K1, AT-K5, AT-P1 | remove the `observe_chunked` call in `_chunked.py` |
| 5 | Referential integrity | Per-table outcome follows the execution facts: a failed parent on the sequential route leaves children `not_run`, never `succeeded` | AT-K2, AT-P2 | mark every table `failed` on any error |
| 6 | Untrusted producer | Progress events are read through the typed `ProgressEvent`; a malformed event is counted as nothing; the read model stays tolerant (E1) | AT-K3 | trust an event's `table` string without `approve_name` |
| 7 | Check then use (TOCTOU) | Delivery facts come from the ledger the writers fill after each file is published, not from the config's target list | AT-D6 | mark tables delivered from `targets:` instead of `ctx._published` |
| 8 | Weak tests and overclaimed evidence | Each AT names its mutation; mutations rerun on the final head and the head is recorded | gate reviewers rerun them | an AT that stays green under its mutation |
| 9 | Behaviour-preserving refactor drift | C-EXIT and C-DOC2 keep every exit integer; base key sets of every envelope recorded before coding and pinned | AT-X3, AT-O1 | map `runtime` to 1 in `RUN_EXIT_MAP` |
| 10 | Frozen contract drift | `decoy-run-result/v1` unchanged (no `_model.py` edit); exit taxonomy additive (6); `--json` additive (`result`, `result_status`, `reason`); capacity widening labelled breaking | AT-X1, AT-X5, AT-C2, the E1 compat corpus | edit a `Literal` in `_model.py`; drop a legacy key |

### 5.2 Enumerations

#### Exit paths

Measured on CLI `ae58f68`. "Own envelope" means the path prints its own `--json` object today.

- X1 Click parse error: exit 2, no document (limit).
- X2 `setup_output` conflict (`src/decoy/cli/run/__init__.py:379`): exit 1, no document (limit).
- X3 bad `--notify` spec, own envelope (`src/decoy/cli/run/_notify.py:112` to `:120`): exit 1; document from C-DOC2.
- X4 `--rows` refusals and `--fidelity` without a mask table, own envelope through `_refuse_usage` (`src/decoy/cli/run/_prepare.py:165` to `:174`): exit 1; document from C-DOC2.
- X5 `_build_resolver` `BadParameter` (`_prepare.py:70`), called outside the `try` at `src/decoy/cli/run/_flow.py:44`: Click exit 2; document from C-DOC2, which re-raises the original `click.UsageError` so Click prints the same message.
- X6 telemetry refusal, gate refusal (`PreRunCheckError`, exit 1 or 5), every `Exception` inside the `try` (`_flow.py:84` to `:86`, then `src/decoy/cli/run/_errors.py:142` to `:208`): 1, 3 or 5; document from C-DOC1.
- X7 an inner `typer.Exit` re-raised at `_flow.py:81` to `:83`: C-DOC2 replaces each inner raise with a typed refusal.
- X8 evidence write failure (`src/decoy/cli/run/_evidence.py:51` to `:57`): exit 3, no JSON today; document from C-DOC2.
- X9 enforce findings (`src/decoy/cli/run/_render.py:117` to `:124`, `:177`): exit 4; document from C-DOC1.
- X10 success (`_render.py:117`) and preview (`_render.py:187`): 0; document from C-DOC1.
- X11 Ctrl-C: `KeyboardInterrupt` is not caught by `except Exception` (`_flow.py:84`); Click `Abort`, expected exit 1 with `Aborted!` (not measured; C-DOC2 STEP ZERO measures it).
- X12 SIGTERM, SIGKILL, kernel OOM: no document (limit, handoff Q5).
- X13 managed-runtime refusal in the root callback (`src/decoy/__main__.py`): exit 3, no document (limit).
- X14 an unexpected exception after the run's `try` has closed (`_flow.py:103` onward: for
  example `build_manifest` at `_evidence.py:37` hashing an output that vanished, which the
  `AtomicWriteError` catch at `_evidence.py:55` does not cover; `commit_latest`; notification
  dispatch): the root crash guard (`src/decoy/__main__.py:146` to `:165`) prints
  `internal error (<class>)` and exits 1 with no JSON. Limit: a document would need a category
  for exit 1 that is not `usage`, which changes the exit taxonomy. AT-O5 pins the limit.

#### Routes

- Plain `run_pipeline` (`src/decoy/cli/run/_execute.py:307`), whose engine routes are full-frame, sequential, out-of-core, mixed (`src/decoy_engine/execution/_pipeline_mixed_route.py:252`) and stream (RUN-STREAM E1a). The document reads the route from `quality_metrics["execution"]` (`src/decoy_engine/execution/_pipeline_route_exec.py:107`); a value outside `ExecutionMode` becomes `other`.
- `--chunked` through `_run_chunked_mask` (`_execute.py:66`): oracle `run_mask_pipeline_chunked` (`src/decoy_engine/execution/_chunked.py:379`) emits no phase events today; the native entry only counts rows (`src/decoy_engine/execution/native/_chunked_entry.py:660`). Until E3b ships, chunked `rows_out` is null with `rows_source` null (named limit in C-DOC1).
- `--rows` preview (`_execute.py:352`): document with `delivery.outcome` `not_applicable`.
- Native and pandas variants of the plain route: same projection; `route.native` from the CLI's `RouteClassification` without its label.

#### FK shapes

- No relationships: one entry per table, config order.
- Parent and child on the sequential route: a failing parent leaves the child `not_run` (AT-K2).
- Multiple parents, self-reference and fan-out: the projection does not walk FKs; outcome comes from the per-table events only, so every shape gets the same rule.
- Cross-table cycles: V1 falls back to full frame (owner, denied V1 first-class); one aggregate phase, so an error marks every unfinished table `failed` (AT-P2).
- Best-effort `dropped_because` along FK edges: filled by DELIV C3 into `DeliveryFacts`, rendered unchanged.

#### Fields

- Document: every field of `RunResult` (`src/decoy_engine/run_result/_model.py:362` to `:379`), unchanged.
- `--json` added members: `result`, `result_status`, and on failure `reason`.
- `--json` legacy members, values unchanged: success `command`, `status`, `config`, `mode`, `elapsed_s`, `tables`, `warnings`, `outputs`, `output_dir`, `project`, `pipeline`, `resources`, `notify`, `native_route`, `report` (`_render.py:86` to `:116`); the preview envelope's `preview` member (`_render.py:192`); failure `command`, `status`, `config`, `mode`, `error`, `hint`, `error_kind`, `code`, `extra`, `notify` and the gate members (`_errors.py:258` to `:287`).
- Exit taxonomy: `EXIT_PARTIAL`, `RUN_EXIT_MAP`.
- CLI warning codes: `run_result_build_failed`, `run_result_write_failed`.

#### Output surfaces

- stdout `--json`: one object per run, now always with `result` (C-DOC2 onward).
- stderr: the build-failure line and the `--result` write-failure line, class name and code only.
- `--result PATH` file (C-DOC3): the same payload as `result`.
- Exit code: unchanged except the capacity widening.
- Notify events and the evidence manifest: unchanged in this row.
- The LIB record store (row 37, L3a) later stores exactly the `result` payload; not built here.

## 6. Reuse inventory

- Engine: `RunResult`, `RunResultRead`, `derive_outcome` (E1); `reason_from_exception` and
  `registered_families` (`src/decoy_engine/reason_adapter.py:158`, `:129`); `safe_error_class`
  (`decoy_engine.progress`); `ProgressSink`, `use_progress` (`src/decoy_engine/progress.py:68`,
  `:510`); `pipeline_config_hash`; `approve_name`, `approve_ref`; `CAPACITY_REASON_CODES`.
- CLI: L5a's fan-out sink `ctx.progress` (CLI PR #216, `run/_progress.py`); the publication
  ledger `ctx._published`; `CLI_WARNING_CODES`; `write_local_target` and `WriteMode.REPLACE`;
  `emit_json`; `_native_gate.classify_route`; `evidence.hash_file` for `config.file_sha256`;
  `mint_invocation_id`.
- Sentries reused: `tests/sentry/test_engine_reason_code_copies.py`. One capacity-code literal
  is allowlisted there today: `cli/preflight.py:446` matches
  `exc.code == "out_of_core_fanin_exceeds_budget"` (allowlist entry at `:73`), and the run gate's
  preflight layer reuses it. C-CAP replaces it with `exc.code in capacity_codes()` and deletes
  the allowlist entry, so `decoy validate` and `decoy run` agree on every widened code and no
  new sentry is needed; `tests/sentry/test_engine_import_surface.py`
  (every new engine name the CLI imports); `tests/sentry/layout/test_run_package_shape.py`
  (600-line cap, import order); engine `tests/sentry/test_run_result_constructor.py`.

## 7. Acceptance tests, red first

Red on base for the reason given; each mutation is applied once, the named test goes red, the
mutation is reverted. Markers: cells `zz_marker_a` and `zz_marker_b`, a `tmp_path` subfolder
`zz_marker_dir`, exception text `zz_marker_exc`.

### 7.1 Engine

| Id | Slice | Test | Mutation that turns it red |
|---|---|---|---|
| AT-P1 | E2a | `tests/unit/run_result/test_project.py::test_rows_precedence`: outputs over phase over rate, `rows_source` per rule, parametrized on synthetic `CollectedFacts` | swap phase and rate precedence |
| AT-P2 | E2a | `test_outcomes`: aggregate error marks unfinished tables `failed`; start-only is `failed` on a failed run and `succeeded` otherwise; no events is `not_run`; no facts and no result gives every table `not_run` | treat the aggregate error as `not_run` |
| AT-P3 | E2a | `test_delivery_facts`: a `failed` delivery fact overrides execution success with its reason; a table without a fact gets `none`; `delivery.outcome` delivered, partial, nothing and `not_applicable` cells | let execution success win over a delivery failure |
| AT-P4 | E2a | `test_names`: a name `approve_name` refuses gives `name: null` with its `index` | pass the raw name |
| AT-P5 | E2a | `test_delivery_states_agree`: `DeliveryFacts.tables` values are `decoy_engine.run_result.TableDelivery` instances, and a `DeliveryFacts` built with any other entry type is refused; state agreement with DELIV stays in `tests/unit/delivery/test_vocabulary.py` | remove the runtime `TableDelivery` check in `DeliveryFacts` (the wrong-entry case goes green, so the test is red) |
| AT-P7 | E2a | `test_delivery_states_project`: `DeliveryFacts` with one table each `delivered`, `failed` (a reason), `withheld` and `dropped` (`dropped_because` a sibling name): each entry's state, reason and `dropped_because` pass through unchanged; `delivery.outcome` `partial`; `derive_outcome` with the best-effort mode gives `partially_delivered` | map `withheld` to `none`; drop `dropped_because` |
| AT-P6 | E2a | `tests/unit/run_result/test_exports.py::test_package_exports`: `decoy_engine.run_result.__all__` lists the new names (E2a's, `TableDelivery` among them, then E2b and E3a each extend it); the top-level `decoy_engine.__all__` is unchanged | export from the top-level `__init__.py` |
| AT-B1 | E2b | `tests/unit/run_result/test_build.py::test_success_two_tables`: `run_pipeline` on a two-table FK fixture (one mask, one generate): the document validates with `RunResultRead`, two entries in config order, `rows_out == len(outputs[t])`, `kind` from `table_kinds`, `status` `succeeded` | skip the generate table |
| AT-B2 | E2b | `test_failure_input`: a `ReasonRecord` from `reason_from_exception(ExecutionError(code="out_of_core_insufficient_memory", message="zz_marker_exc"))` comes back equal in `failure.reason`; marker absent from `json.dumps(payload)`; `status` follows `category` | pass `category=None` to `derive_outcome` |
| AT-B3 | E2b | `test_checks_value_free`: `failed_checks` messages and `quality_summary.sampled_values` with markers give codes and counts only; `blocking` equals the `blocking_failed` input and `status` is `findings` only when it is true | copy `message` into `codes`; recompute blocking from the checks inside the builder |
| AT-B4 | E2b | `test_paths_and_native`: an absolute target gives its file name; `../x.csv` gives `x.csv`; `out/a.csv` stays; `native` has no label | keep the absolute path |
| AT-B5 | E2b | existing `tests/sentry/test_run_result_constructor.py` green with `_build.py` present; its seeded `model_copy` case in `_project.py` red | `model_copy(update=...)` in `_project.py` |
| AT-B6 | E2b | `test_route_values`: every route value `execution_telemetry` is called with (listed at STEP ZERO) maps to a member of `ExecutionMode` or to `other` | drop the `other` mapping (the read of a new value raises) |
| AT-K1 | E3a | `tests/unit/run_result/test_collect.py::test_whole_table_routes_count_rows`: full-frame, sequential and out-of-core under `use_progress(collector)`: the snapshot projected with `execution_result=None` (so the phase rows are the source) gives `rows_out` equal to the outputs and `rows_source` `phase` | drop phase finish rows in the collector |
| AT-K2 | E3a | `test_per_table_on_failure`: sequential forced, table 2 raises: 1 `succeeded`, 2 `failed`, 3 `not_run`; full-frame mask strategy raises: every mask table `failed` | mark every table `failed` on any error |
| AT-K3 | E3a | `test_collector_never_changes_a_run`: `collector.on_event` called directly (not through `Progress.emit`, which already swallows sink errors at `progress.py:186` to `:197`) with a malformed event and with an event whose read raises: no exception, counters unchanged; and a run's outputs are byte-identical with and without the collector | let `on_event` exceptions escape |
| AT-K4 | E3a | `test_phase_timings`: `resolve` and `mask` present, `elapsed_s >= 0`, first-seen order | keep only the last phase |
| AT-K5 | E3b | `test_chunked_entries_count_rows`: oracle and native (where the companion is installed) chunked entries: `rows_out` equals the rows the caller received, `rows_source` `phase` | remove the `observe_chunked` call in `_chunked.py` |
| AT-K6 | E3b | `test_observe_chunked_outcomes`: early close after one chunk on a successful run gives `succeeded` and no phase error event; a producer exception gives `failed` and propagates unchanged | use the `phase()` context manager |
| AT-CAP1 | E-CAP | `tests/unit/test_capacity_reason_codes.py::test_members`: the seven codes are in `CAPACITY_REASON_CODES` and registered; the old pin at `tests/unit/generation/test_generation_floor.py:481` moves to this set (named pin update) | drop `out_of_core_faker_pool_budget_exceeded` |
| AT-CAP2 | E-CAP | `test_registry_walk`: every registered code whose name contains `memory`, `budget`, `capacity` or `oom` is in exactly one of `CAPACITY_REASON_CODES` or `CAPACITY_EXCLUSIONS`; every exclusion has a non-empty reason; the walk's count is recorded in the build record, never hard-coded | delete one exclusion entry |
| AT-OOM1 | E-OOM | `test_memory_error_identity`: `reason_from_exception(MemoryError())` is `decoy.process_out_of_memory` with retry `environment_repair`; the code is in `CAPACITY_REASON_CODES`; the registry snapshot passes with `since=UNRELEASED` | drop the `_FIXED` row |

### 7.2 CLI

| Id | Slice | Test | Mutation that turns it red |
|---|---|---|---|
| AT-X1 | C-EXIT | `tests/unit/test_exit_code_registries.py::test_taxonomy`: `contracts.EXIT_CODES` equals the `EXIT_` integers in `exit_codes.__all__`; `EXIT_PRECEDENCE == (5, 3, 1, 6, 4, 2, 0)`; `docs/ci-contracts.md` has a row per code and the precedence string | a hand-written `EXIT_CODES` without 6 |
| AT-X2 | C-EXIT | `test_run_exit_map_total`: `RUN_EXIT_MAP` has an entry for every `(status, category)` `derive_outcome` can return (from `get_args`), and nothing else; every value is pinned as a literal (0, 4, 6, 1, 2, 3, 5 and the OQ-1 Ctrl-C integer) | map `partially_delivered` to 3; map `parameter` to 1 |
| AT-X3 | C-EXIT | `tests/e2e/test_run_exit_map.py::test_exits_read_the_map`: config error 1, engine runtime error 3, fan-in capacity 5, gate refusal 1, gate capacity 5, enforce findings 4, success 0, each equal to today; then with `RUN_EXIT_MAP[("failed", "runtime")]` patched to 9 the runtime case exits 9 | `fail` raises its local `_exit_code` again |
| AT-X4 | C-EXIT | `test_explain_lists_exit_6`: `decoy explain exit-codes` and the README "Exit codes" section list 6 as partially delivered, reserved for best-effort delivery | drop the explain line |
| AT-X5 | C-EXIT | `tests/unit/test_exit_codes.py` expected `__all__` gains `EXIT_PARTIAL` and `RUN_EXIT_MAP`; `tests/unit/test_ci_docs.py` precedence pin updated (named pin updates, nothing else changes) | n/a (pin update) |
| AT-R1 | C-REASON | `tests/e2e/test_run_reason_envelope.py::test_capacity_failure_carries_reason`: `ExecutionError(code="out_of_core_insufficient_memory", message="zz_marker_exc")`: exit 5, `reason` identity `runtime.out_of_core_insufficient_memory`, `error_kind` and `code` kept, marker absent from `reason` | no `reason` key |
| AT-R2 | C-REASON | `test_publication_failure`: engine `CommitError`: exit 3, `decoy.publication_failed` | attach from the category instead of the exception |
| AT-R3 | C-REASON | `test_config_failure`: `ConfigError("zz_marker_exc")`: exit 1, retry `configuration_repair` | none attached for usage categories |
| AT-R4 | C-REASON | `test_unknown_exception`: `ValueError` with `.code = "zz_marker_exc"`: exit 3, `decoy.unexpected_error`, marker absent | read `exc.code` into the reason |
| AT-R5 | C-REASON | `test_rewrites_keep_the_original_reason`: a missing extra has no `reason`; an engine `NerUnavailableError` rewritten to `MissingExtraError` keeps the engine record of the original | compute from the rewritten exception |
| AT-R6 | C-REASON | `test_cli_owned_refusals_have_no_reason[...]`: cases derived from `_cli_refusal_types()` (no hand list), at least `_VaultUsageError`, `_ChunkedVaultError`, `_VaultWriteError`, `OutDirUsageError`, `PreRunCheckError` (exit 1 and exit 5) and `_OtelSettingsUsageError`: no `reason`, exits unchanged | attach `unexpected_error` to every failure; leave `_VaultWriteError` out of `_cli_refusal_types()` |
| AT-R7 | C-REASON | `test_usage_types_single_source`: `_usage_types()` equals the base tuple at `_errors.py:157` to `:205` member for member (listed at STEP ZERO), and both the exit category and the attach rule read it; C-DOC2 extends the pinned list by its typed refusals (named pin update) | drop `DuckDBSourceError` from one rule only |
| AT-R8 | C-REASON | `test_classifier_failure_keeps_exit`: `registered_families` patched to raise `RuntimeError("zz_marker_exc")`: exits 1, 3, 5 unchanged, no `reason`, marker absent from stdout and stderr | remove the guard in `_failure_reason` |
| AT-R9 | C-REASON | `tests/sentry/run/test_one_run_reason.py` (G-ONE-REASON): exactly one `reason_from_exception` reference in `src/decoy/`, inside `_failure_reason`; seeded-violation self-test in a scratch copy | a second call in `_render.py` |
| AT-D1 | C-DOC1 | `tests/e2e/run_result/test_run_result.py::test_success_document`: mixed config with `--json`: `result` validates with `RunResultRead`, `result.exit_code == 0 ==` process exit, `pipeline_kind` `mixed` while legacy `mode` stays as today, `config.file_sha256 == evidence.hash_file(config)` on a CRLF fixture, legacy key set equals the base set plus `result` and `result_status` | read legacy `mode` from `pipeline_kind` |
| AT-D2 | C-DOC1 | `test_failure_document`: engine runtime error: `result.status` `failed`, `failure.category` `runtime`, `failure.reason` equals the envelope `reason`, `result.exit_code == 3 ==` process exit; engine capacity case gives `capacity` and 5; gate capacity refusal gives `capacity`, 5, no `failure.reason` | pass `category="runtime"` for every failure in `_result.py` (capacity cell red) |
| AT-D3 | C-DOC1 | `test_value_free`: success, runtime, usage and capacity runs over the markers: `result` and `result_status` hold no marker and no `str(tmp_path)` | pass `ctx.config_str` as `config.name` |
| AT-D4 | C-DOC1 | `test_build_failure_keeps_exit`: `build_run_result` patched to raise `RuntimeError("zz_marker_exc")` on a success and a runtime failure: exits 0 and 3, no `result`, `result_status.document` `failed` with `run_result_build_failed`, marker absent; for every C-DOC1 path the fallback exit equals the builder's | let the exception escape |
| AT-D5 | C-DOC1 | `tests/sentry/run/test_one_result_builder.py` (G-RESULT-ONE-BUILDER): one `build_run_result(` in `src/decoy/`, in `_result.py`; no `RunResult(` or `RunResultRead(` call, no `model_construct`, `model_validate` or `model_copy` on a `RunResult` or `RunResultRead` receiver (the engine sentry's scope; `cli/io/_scan_set.py:131` is not one), and no `decoy-run-result/v1` literal in `src/decoy/`; seeded self-test | a second `build_run_result(` in `_render.py` |
| AT-D6 | C-DOC1 | `test_in_place_delivery`: success gives `in_place` `delivered`; the second target's write fails: exit 3, `delivery.outcome` `partial`, table 1 `delivered`, table 2 `none` | mark tables delivered from `targets:` |
| AT-D7 | C-DOC1 | `test_preview_document`: `--rows 5 --json`: `result` present, `delivery.outcome` `not_applicable`, nothing written | derive `nothing` for a preview |
| AT-D8 | C-DOC1 | `test_collector_registered`: a sequential run whose second table raises: document tables `succeeded`, `failed`, `not_run` | skip `ctx.progress.add(collector.on_event)` in `_flow.py` |
| AT-D10 | C-DOC1 | `tests/sentry/run/test_one_result_builder.py::test_one_delivery_facts_provider`: every `DeliveryFacts(` call and `DeliveryFacts.not_applicable(` call in `src/decoy/` is inside `_result.delivery_facts`; seeded self-test | build `DeliveryFacts(` in `_render.py` |
| AT-D9 | C-DOC1 | `test_one_blocking_decision`: enforce with failed checks: exit 4, `result.status` `findings`, `LATEST` not moved; enforce off with the same checks: exit 0, `succeeded`, `LATEST` moved | keep the `commit_latest` copy of the enforce test and invert it there only |
| AT-O1 | C-DOC2 | `tests/e2e/run_result/test_run_exit_paths.py::test_every_path_has_one_document` (X3 to X11): `result.exit_code` equals the process exit and the base integer; X3 to X5 carry `timings.started_at <= finished_at` and the 3.3 defaults (`delivery.mode` `in_place`, `delivery.vault` `not_used`); legacy key set equals the base set recorded before coding, plus `result` and `result_status` (X5, X8, X11 had no JSON on base: their pinned sets are new and the changelog says so); X5 keeps Click's message on stderr; X8 has no `reason` and `failure.category` `runtime` | emit the X3 envelope before `finish`; attach `unexpected_error` to the evidence failure |
| AT-O2 | C-DOC2 | `tests/sentry/run/test_one_run_exit.py` (G-RUN-ONE-EXIT): under `src/decoy/cli/run/`, `emit_json(` and every exit raise appear only in `_result.py`. Covered shapes, listed in the docstring: `typer.Exit`, `click.exceptions.Exit`, `SystemExit`, `sys.exit(`, `typer.Abort`, and the same names bound through `from typer import Exit`, an `as` alias, or a module alias (`import sys as s; s.exit(1)`, `import typer as t; raise t.Exit()`); `getattr` and `importlib` are a named limit; seeded self-test per shape | re-add `raise typer.Exit(code=EXIT_USAGE)` in `_notify.py`; `sys.exit(1)` in `_prepare.py`; `import sys as s` then `s.exit(1)` in `_flow.py` |
| AT-O3 | C-DOC2 | `test_ctrl_c`: `KeyboardInterrupt` from a patched `run_pipeline`: `status` `cancelled`, `failure.reason.code` `run_cancelled`, exit and stderr line equal to the STEP ZERO measurement | catch only `Exception` in the wrapper |
| AT-O4 | C-DOC2 | `test_one_json_object`: stdout parses as exactly one JSON object on every AT-O1 path | emit twice on the build fallback |
| AT-O5 | C-DOC2 | `test_post_try_crash_is_a_named_limit` (X14): `build_manifest` patched to raise `OSError("zz_marker_exc")` with `--evidence-out --json`: exit 1, `internal error (OSError)` on stderr, no partial JSON on stdout, marker absent from both | emit a half-built envelope before the root guard |
| AT-O7 | C-DOC2 | `test_no_document_limits[X1,X2,X13]`: a Click parse error (exit 2), a `setup_output` conflict (exit 1) and the managed-runtime refusal (exit 3) with `--json`: exits as today and no JSON object on stdout; X12 (SIGTERM, SIGKILL, kernel OOM) is an untested process-termination limit | emit a `result` envelope from the `setup_output` refusal |
| AT-O6 | C-DOC2 | `test_typed_refusals_carry_no_context[...]`: for every typed refusal C-DOC2 adds (cases derived from `_usage_types()` and `_cli_refusal_types()` members defined in `cli/run/`), the refusal caught at `finish` has `__context__ is None` and `__cause__ is None` | move one typed refusal's raise inside its `except` block |
| AT-F1 | C-DOC3 | `tests/e2e/run_result/test_result_file.py::test_file_equals_member`: `--json --result out.json`: the file equals the envelope `result`; `result_status.file` `written`; human mode prints `Result: out.json` | write the whole envelope to the file instead of its `result` member |
| AT-F2 | C-DOC3 | `test_write_failure_keeps_exit`: a missing directory on success and on a runtime failure: exits 0 and 3, one stderr line with `run_result_write_failed` and no path, `result_status.file` `failed` | raise `EXIT_RUNTIME` on the write failure |
| AT-F3 | C-DOC3 | existing `tests/sentry/test_atomic_writer.py` green with the new call | `Path.write_text` in `_result.py` |
| AT-F4 | C-DOC3 | `test_result_path_collides[target,quarantine,evidence,vault,symlink,hardlink]`: `--result` equal to a table target, an enabled quarantine file, `--evidence-out`, `--vault`, a symlink to a target and a hard link to an existing target: the existing `output_path_collision` refusal with its exit, flag and config-location labels only, no source row read, no file written or replaced | drop the `--result` entry from `_placement`'s `typed` |
| AT-C1 | C-CAP | `tests/e2e/test_run_capacity_widening.py::test_each_capacity_code_exits_5`: each exception-family member of `CAPACITY_REASON_CODES` raised as its engine class with its code (and `MemoryError()`) from a patched `run_pipeline`: exit 5, `error_kind` `capacity`; `isolated_worker_out_of_memory` (no exception class in `decoy run`) covered by a unit call of the category rule. `failure.category` is not asserted here: C-CAP may land before C-DOC1, and AT-D2 covers the capacity category | the CLI keeps a local three-code set |
| AT-C2 | C-CAP | `test_excluded_codes_keep_their_exit`: one code per exclusion family (`storage_capacity_exhausted`, `out_of_core_budget_invalid`, `subset_budget_exceeded`, `dp_budget_exceeded`, `pool_capacity_pre_flight_unique`, `fk_full_frame_oom_risk_rejected`) keeps today's exit | widen by substring `budget` in the CLI |
| AT-C3 | C-CAP | `tests/e2e/test_run_preflight_capacity_parity.py` gains `test_widened_codes_agree`: each member of `CAPACITY_REASON_CODES` raised from a patched `estimate_job_capacity` gives the same capacity verdict and exit in `decoy validate` and in the `decoy run` gate | keep the fan-in literal at `cli/preflight.py:446` |

Behaviour kept (assertions unchanged): every `tests/e2e/test_run_*.py`,
`tests/e2e/test_run_capacity.py`, `tests/e2e/generate_config/test_generate_capacity.py`,
`tests/e2e/test_stateless_cli.py`, `tests/unit/test_ci_*.py` apart from the named pin, the
sentries under `tests/sentry/`.

## 8. Placement

| New file | Directory and CODEMAP line | Neighbour module | Slice |
|---|---|---|---|
| `src/decoy_engine/run_result/_project.py` | `run_result/` (engine `CODEMAP.md`, the run_result row gains the module) | `run_result/_outcome.py` | E2a |
| `src/decoy_engine/run_result/_build.py` | same | `run_result/_model.py` | E2b |
| `src/decoy_engine/run_result/_collect.py` | same | `progress.py` (the `ProgressSink` protocol) | E3a |
| `src/decoy_engine/execution/chunked/__init__.py`, `src/decoy_engine/execution/chunked/_progress.py` | new sub-package `execution/chunked/`, the route cluster `tests/sentry/layout/test_package_fanout.py:32` names for the next `execution/` module (the flat folder is frozen at 104); engine `CODEMAP.md` gains a row; `_progress.py` joins `GUARDED_MODULES` in `tests/sentry/test_physical_seam_disconnection.py:64` | `execution/_chunked.py` | E3b |
| `tests/unit/run_result/test_project.py`, `test_build.py`, `test_collect.py`, `test_exports.py` | tests mirror the package | `tests/unit/run_result/test_outcome.py` | E2a, E2b, E3a |
| `tests/unit/test_capacity_reason_codes.py` | `tests/unit/` | `tests/unit/generation/test_generation_floor.py` | E-CAP |
| `src/decoy/cli/run/_result.py` | `cli/run/` (CLI `CODEMAP.md:50`, row gains `_result.py`); `ORDER` in `tests/sentry/layout/test_run_package_shape.py` gains `_result` after `_vault`, before `_execute` | `run/_render.py` | C-DOC1 |
| `tests/unit/test_exit_code_registries.py` | `tests/unit/` (CLI `CODEMAP.md:56`, exit codes row) | `tests/unit/test_exit_codes.py` | C-EXIT |
| `tests/e2e/test_run_exit_map.py`, `tests/e2e/test_run_reason_envelope.py`, `tests/e2e/test_run_capacity_widening.py` | `tests/e2e/` beside the other `test_run_*` files | `tests/e2e/test_run_capacity.py` | C-EXIT, C-REASON, C-CAP |
| `tests/e2e/run_result/` (`__init__.py` if the topic folders on main carry one, `test_run_result.py`, `test_run_exit_paths.py`, `test_result_file.py`) | `tests/e2e/<topic>/` as `tests/e2e/project_layout/` on main | `tests/e2e/project_layout/` | C-DOC1 to C-DOC3 |
| `tests/sentry/run/__init__.py`, `tests/sentry/run/test_one_run_reason.py`, `test_one_result_builder.py`, `test_one_run_exit.py` | new group `tests/sentry/run/` (`decoy run` choke points), as CLI `CODEMAP.md:67` asks (`tests/sentry/<group>/test_<rule>.py`; the flat `tests/sentry/` holds existing rules only); the CODEMAP sentry row names the group; each file is listed in `SENTRIES` in `tests/sentry/test_sentry_manifest.py`. `scripts/dev/sentry_registry.toml` is not touched: none of the three has a baseline file | `tests/sentry/defects/` | C-REASON, C-DOC1, C-DOC2 |

No module goes in the frozen flat `src/decoy/cli/` or the frozen flat engine `execution/`.
Sizes at the base: engine `__init__.py` 600 (the goal; no slice edits it, the new names are
exported from `decoy_engine.run_result` only), `execution/_chunked.py` 600 at `c38f17cd` and 599
at `ad63ba1b` (net 0 in E3b; no new size-census entry), `execution/native/_chunked_entry.py` 681
at `c38f17cd` and 685 at `ad63ba1b`, ceiling 689 (net 0 in E3b), `errors.py` 548, CLI `run/_errors.py` 320, `run/_render.py` 201,
`run/_flow.py` 125, `run/_context.py` 163 (cap 600 for `cli/run/`). Every new module stays under
300 lines.

## 9. Frozen contracts touched

- Exit taxonomy (`exit_codes.__all__`, `ci/contracts.EXIT_CODES`, `EXIT_PRECEDENCE`,
  `docs/ci-contracts.md`, `decoy explain exit-codes`, README): 6 added (C-EXIT); four codes move
  to 5 (C-CAP; `MemoryError` already exits 5). Changelog: additive for 6, breaking pre-1.0 for
  the widening (MINOR under `docs/release/versioning.md`).
- `decoy run --json`: `reason` (C-REASON), `result` and `result_status` (C-DOC1) added; legacy
  members unchanged; X5, X8 and X11 gain a JSON object they did not have (C-DOC2, changelog).
- `decoy-run-result/v1`: unchanged. No slice edits `run_result/_model.py`.
- Reason registry: one identity `since=UNRELEASED` (E-OOM, after #506); consumer contract
  regenerated.
- Engine public API: `project_tables`, `ProjectedTables`, `CollectedFacts`, `DeliveryFacts`,
  `TableDelivery`, `build_run_result`, `FailureInput`, `RunResultCollector` in `decoy_engine.run_result.__all__`,
  pinned by `tests/unit/run_result/test_exports.py` (AT-P6); `CAPACITY_EXCLUSIONS` in
  `decoy_engine.errors`, pinned by AT-CAP2. The top-level `decoy_engine.__all__` and
  `tests/unit/test_public_api.py` are unchanged.
- New CLI option `--result PATH` (C-DOC3); `docs/cli-reference.md` regenerated.

## 10. Slices

One fixed writer order per shared `cli/run/` module. Every lane is a strict sequence: a writer
starts on the merged head of the one before it, never in parallel and never out of order. The
DELIV plan's own order (deliv.md section 10) has no RESULT slice in the `_execute.py` lane,
names "F29 C1" as the RESULT writer of `_render.py`, gives DELIV C3 the exit-map work and has no
`_result.py` slot; the orchestrator amends the DELIV plan with this table, the `_result.py`
slot and the OQ-3 correction before C-DOC1 or DELIV C2a starts (pre-mortem, stop line).

| Module | Writers, in order (merged ones struck from the head of the lane as they land) |
|---|---|
| `run/_execute.py` | L5a (#216), SUB-RUN C1, C-DOC1 (two lines: keep the `ExecutionResult` on `ctx` in the plain branch), DELIV C2a, C3, C4, C5 |
| `run/_flow.py` | L5a (#216), C-DOC1 (one line), C-DOC2, DELIV C2a (moves the `write_evidence` call into the sink), LIB L3b, L5b |
| `run/_errors.py` | C-EXIT, C-REASON, C-DOC1, C-DOC2 (no DELIV writer) |
| `run/_render.py` | C-EXIT, C-DOC1, C-DOC2, DELIV C2a, DELIV C5 (extends `_blocking_failed`) |
| `run/_context.py` | L5a (#216), C-DOC1, C-DOC3, DELIV C2a (`sink` field) |
| `run/_prepare.py` | SUB-RUN C1, C-DOC2, C-DOC3 (the `--result` entry in `_placement`) |
| `run/_result.py` | C-DOC1, C-DOC2, C-DOC3, DELIV C2a (the `delivery_facts` body) |
| `run/_evidence.py` | C-DOC2 (the X8 typed refusal); DELIV C2a then calls it from the sink unchanged |
| `run/_notify.py` | C-DOC2 |
| `run/__init__.py` | C-DOC3 |

So DELIV C2a starts after C-DOC2 and C-DOC3 have merged; C-DOC3 waits on nothing from DELIV. C-REASON writes no `_render.py`; DELIV's "F29 C1"
`_render.py` slot is C-DOC1 and C-DOC2 here. C-CAP writes no `cli/run/` module.

| Slice | Repo | Files | Src / test lines | Tier | Depends on | Startable now |
|---|---|---|---|---|---|---|
| C-EXIT | CLI | `cli/exit_codes.py`, `ci/contracts.py`, `run/_errors.py`, `run/_render.py`, `cli/explain.py`, `README.md`, `docs/ci-contracts.md`, `CHANGELOG.md`, AT-X1 to AT-X5 tests (`tests/unit/test_exit_codes.py` and `tests/unit/test_ci_docs.py` named pins) | ~90 / ~150 | R2 | nothing (engine 0.22.0 has `derive_outcome`) | yes |
| C-REASON (F29 C1) | CLI | `run/_errors.py`, `CHANGELOG.md`, `tests/e2e/test_run_reason_envelope.py`, `tests/sentry/run/__init__.py`, `tests/sentry/run/test_one_run_reason.py`, `SENTRIES` row, CODEMAP sentry row | ~80 / ~240 | R2 | C-EXIT merged (same module) | yes, after C-EXIT; it waits on nothing outside this row |
| E2a | engine | `run_result/_project.py`, `run_result/__init__.py`, `tests/unit/run_result/test_project.py`, `tests/unit/run_result/test_exports.py`, `CODEMAP.md`, `CHANGELOG.md` | ~170 / ~170 | R2 | nothing | yes |
| E-CAP | engine | `errors.py`, `tests/unit/test_capacity_reason_codes.py`, `tests/unit/generation/test_generation_floor.py` (pin), `docs/strategies.md`, `CHANGELOG.md` | ~60 / ~90 | R2 | nothing (OQ-5 has a working answer; the exclusion entries change if the owner says otherwise) | yes |
| E2b | engine | `run_result/_build.py`, `run_result/__init__.py`, `test_build.py`, `test_exports.py`, `CHANGELOG.md` | ~170 / ~210 | R2 | E2a | no: E2a |
| E3a | engine | `run_result/_collect.py`, `run_result/__init__.py`, `test_collect.py`, `test_exports.py`, `CHANGELOG.md` | ~160 / ~140 | R2 | E2a (`CollectedFacts`) | no: E2a |
| E3b | engine | `execution/chunked/__init__.py`, `execution/chunked/_progress.py`, `execution/_chunked.py` (net 0), `execution/native/_chunked_entry.py` (net 0), `tests/sentry/test_physical_seam_disconnection.py` (`GUARDED_MODULES` entry), `test_collect.py` (chunked cases), `CODEMAP.md`, `CHANGELOG.md` | ~70 / ~150 | R2 | E3a; merge main in before its gate if engine #505 or #508 (both edit the chunked entries) merged | no: E3a |
| E-OOM | engine | `reasons/decoy/_core.py`, `reason_adapter.py`, `errors.py`, registry snapshot and consumer contract, `docs/reasons.md`, `CHANGELOG.md`, test | ~30 / ~80 | R1 | engine #506 merged; E-CAP | no: #506 |
| REL | engine, CLI | engine release with E2a, E2b, E3a, E-CAP (and E3b, E-OOM when merged); CLI repin per the repin checklist | small | R1 | the slices it carries | no |
| C-CAP | CLI | `cli/exit_codes.py` (docstring), `cli/explain.py`, `cli/preflight.py` (the `:446` literal), `tests/sentry/test_engine_reason_code_copies.py` (allowlist entry `:73` removed), `README.md`, `CHANGELOG.md` (breaking line), `tests/e2e/test_run_capacity_widening.py`, `tests/e2e/test_run_preflight_capacity_parity.py` | ~40 / ~140 | R2 | the repin carrying E-CAP; lands with that repin or the same day | no: release |
| C-DOC1 | CLI | `run/_result.py`, `run/_errors.py`, `run/_render.py`, `run/_flow.py` (one line), `run/_execute.py` (two lines), `run/_context.py`, `tests/sentry/layout/test_run_package_shape.py` (`ORDER`), `tests/sentry/run/test_one_result_builder.py`, `SENTRIES` row, `CODEMAP.md`, `CHANGELOG.md`, AT-D1 to AT-D10 tests | ~260 / ~320 | R2 | REL with E2a, E2b, E3a; C-REASON; L5a (#216) and SUB-RUN C1 merged (the `_execute.py` lane) | no: release and #216 |
| C-DOC2 | CLI | `run/_result.py`, `run/_flow.py`, `run/_notify.py`, `run/_prepare.py`, `run/_evidence.py`, `run/_errors.py`, `run/_render.py`, `tests/sentry/run/test_one_run_exit.py`, `SENTRIES` row, `CHANGELOG.md`, AT-O1 to AT-O7 tests, AT-R7 pin update | ~210 / ~310 | R2 | C-DOC1; SUB-RUN C1 merged (`_prepare.py`) | no: C-DOC1 |
| C-DOC3 | CLI | `run/__init__.py` (one option hunk), `run/_context.py`, `run/_result.py`, `run/_prepare.py` (the `typed` entry), `cli/io/_placement.py` (docstring), `docs/cli-reference.md` (generated), `CHANGELOG.md`, AT-F1 to AT-F4 tests | ~90 / ~170 | R2 (new public option and a frozen artifact written at a user path) | C-DOC2 | no: C-DOC2 |

C-DOC2 is the largest (about 520 lines with tests) and stays one slice: its exit paths share one
`finish` and one sentry, and splitting them would leave the sentry red between the halves.

Can start today without waiting on DELIV, engine #506 or the `_execute.py` order: **C-EXIT**
(CLI), then C-REASON on its head; **E2a** and **E-CAP** (engine) in parallel with them.
C-EXIT is the first pick: it is the smallest, unblocks C-REASON, and gives DELIV C3 the map it
needs. None of these four edits `_execute.py`.

Engine `run_result/__init__.py` takes additive export lines from E2a, E2b and E3a in that
order. The top-level `__init__.py` and `tests/unit/test_public_api.py`, which the open engine
PRs #508 and #512 edit, are not touched.

Test depth: T0 per edit, T1 impact selection per commit. Full-suite escalation triggers: C-EXIT
(frozen exit contract, `ci` contracts), C-DOC2 (frozen `--json` envelope), E-OOM (registry), REL
(version pin). Mutations: every mutation in section 7, rerun on the final head.

Gates: Codex plus Dennis for R2, Codex for R1. Row 62 is DONE when C-DOC3 and C-CAP are merged
and released. Exit 6 is reachable after DELIV C3; that is row 61's acceptance, not this row's.

## 11. Owner questions

- **OQ-1. Exit status on Ctrl-C.** Today Click's `Abort` (expected 1 with `Aborted!`, measured at
  C-DOC2 STEP ZERO). The DELIV plan (2.3, 6.2) writes 130. Options: (a) keep today's integer;
  (b) 130 (128 plus SIGINT, what shells report), a changelog line and a new named constant.
  Working answer: (a). No one decided a Ctrl-C exit change, and RESULT's guarantee is "no exit
  integer changes". The DELIV plan text should be corrected to "today's Ctrl-C status".
- **OQ-2. Exit for `BadParameter` (`--master-key`, `--key-label`).** Today 2 (Click usage
  error). The DELIV plan maps `parameter` to 1. Working answer: keep 2, as the handoff D5 table
  has it; correct the DELIV plan text.
- **OQ-3 (orchestrator, not owner). Who adds `EXIT_PARTIAL` and `RUN_EXIT_MAP`.** DELIV 7.1 says
  DELIV C3. Working answer: C-EXIT adds both now, because it can start today and every RESULT CLI
  slice needs the map; DELIV C3 reuses them and its file list drops `exit_codes.py`.
- **OQ-4 (technical, taken). Warning codes for a failed build or `--result` write.** Taken: the
  CLI closed list `CLI_WARNING_CODES`, not the reason registry, so nothing waits on #506.
  Alternative: two `warning.*` registry identities after #506.
- **OQ-5 (owner). Do the full-frame OOM-risk refusals exit 5?** `fk_full_frame_oom_risk_rejected`
  and `fk_full_frame_oom_risk_rejected_estimated` (`reasons/runtime/_part1.py:189` to `:194`)
  are raised as `ExecutionError` before any row is read and exit 3 today. They are not in the
  handoff Q3 table, and preflight files them as "not applicable", not capacity
  (`execution/capacity.py:149`). Working answer: keep exit 3 and list both in
  `CAPACITY_EXCLUSIONS` with the reason "a routing refusal decided before any row is read; the
  fix is the job's shape, not more memory". The other answer moves them to 5 with the four Q3
  codes in C-CAP.

## 12. Recurring-defect walk (`/home/cam/dev-rules/catalogs/recurring-defects.md`)

1. Anchored validation: no new validator; the model's `\Z` anchors (E1 fix round 3) are reused.
   E2a names go through `approve_name`, which ends in `\Z`.
2. Strict wire types: no new persisted field; `DeliveryFacts`, `CollectedFacts` and
   `FailureInput` are in-process inputs, and their output lands in the strict E1 model.
3. No exception context: `_failure_reason` and the build fallback never put the exception in an
   output; every typed refusal C-DOC2 adds is raised after its `except` block closes, proved by
   AT-O6 (the existing `test_exception_context.py` sentry does not cover a plain raise inside an
   `except`).
4. Versioned read models: AT-D1 reads `result` with `RunResultRead`; no new format.
5. Normalized guard scanners: AT-R9, AT-D5 and AT-O2 match calls through `ast` (attribute and
   name forms, `from x import y as z` aliases, module aliases such as `import sys as s`); covered shapes are listed in each sentry's
   docstring, and AT-O2 names every exit form (`typer.Exit`, `click.exceptions.Exit`,
   `SystemExit`, `sys.exit(`, `typer.Abort`) with a seeded case per shape; `getattr` and
   `importlib` are a named limit.
6. No private imports: the CLI imports `decoy_engine` public names only, checked by
   `test_engine_import_surface.py`; engine `_collect.py` uses the public `progress` module.
7. No hidden CI failures: no new workflow or script.
8. One input, one trust class: no user-named file or key enters a new entry point except
   `--result PATH`, which goes through the existing user-path writer.
9. Mutations on the final head: required in every slice record (section 10).
10. Allowlisted helpers: the builder sentry and the exit sentry allow exactly `_result.py` by
    `(path, name)`; no forwarding helper.
11. No raised caps: no cap or allowlist rises. The frozen engine `execution/` folder (104
    modules) gets nothing: E3b's module goes in the new `execution/chunked/` sub-package the
    fan-out sentry names. Engine `__init__.py` (600, the goal) is not edited; `_chunked.py`
    changes net 0, so no new size-census entry. `test_run_package_shape.py` `ORDER` gains a
    module name and `GUARDED_MODULES` gains one entry, which are placement and a stricter guard,
    not caps. C-CAP shrinks the reason-code copy allowlist by one.

## 13. V2-LOG

- Per-table `failed` delivery state on an in-place write failure before DELIV (C-DOC1 leaves the
  failed table at `none`; DELIV's sink fills it).
- A route value outside `ExecutionMode` (for example the mixed and stream routes) reads `other`.
- `decoy tokenize`, `decoy demo` and `decoy.mask()` produce no run result.
- SIGTERM writes no document (handoff Q5); a second Ctrl-C during `finish`.
- The legacy `error` member keeps `str(exc)` capped at 500 characters (F31, row 65).
- A gate capacity refusal (`PreRunCheckError`) carries no `reason` (CLI-owned; B6g).
- X14: an unexpected exception after the run's `try` has closed exits 1 through the root crash
  guard with no document.
- Ctrl-C and a usage error share exit 1 under OQ-1's working answer; only the document's
  `status` tells them apart.
- `MemoryError` reason reads `decoy.unexpected_error` until E-OOM ships.

## 14. Pre-mortem

- C-DOC2 changes an exit integer by accident. Guard: base key sets and exits recorded before
  coding, AT-O1 pins them.
- The engine release slips and C-DOC1 waits. C-EXIT and C-REASON still close the exit-map and
  `reason` parts; the row's status says which parts remain.
- E3b collides with #505 or #508 on the chunked entries. It is the last engine slice; merge main
  in before its gate.
- DELIV C3 also adds `RUN_EXIT_MAP` if OQ-3 is not passed on. The orchestrator posts the
  correction on the DELIV plan before C3 starts.
- The two plans keep different writer orders and a builder takes the wrong slot. The
  orchestrator posts the section 10 lane table on the DELIV plan (C-DOC1 in the `_execute.py`
  lane before C2a; C-DOC1 and C-DOC2 as the RESULT `_render.py` writers; C2a after C-DOC2; the
  `_result.py` lane with C2a's `delivery_facts` slot), and the DELIV receipt-to-`DeliveryFacts`
  rule (3.2), before C-DOC1 or C2a starts. DELIV C2a's own tests then cover `nothing`,
  `uncertain`, `failed`, `withheld` and `dropped` receipts end to end (reason,
  `dropped_because`, `delivery.outcome`, exit 6).
- The widened set changes a platform consumer. The platform is parked; C-CAP's builder greps the
  platform checkout for `CAPACITY_REASON_CODES` and reports any hit.

## 15. Stop lines for builders

- Stop if any slice needs an edit to `src/decoy_engine/run_result/_model.py`.
- Stop if any exit integer of a path in 5.2 changes, other than C-CAP's listed codes.
- Stop if C-DOC1 needs more than the two named lines in `run/_execute.py`, or any slice other
  than C-DOC1 needs `_execute.py`.
- Stop if a `cli/run/` module would pass 600 lines, or an engine module 700.
- Stop if a new module would land in the flat `src/decoy/cli/` folder or the flat engine
  `execution/` folder, if engine `__init__.py` needs an edit, or if `execution/_chunked.py`
  would grow.
- Stop if a slice needs a DELIV-owned file (`io/_targets.py`, `io/_delivery.py`, `io/_layout.py`,
  `run/_vault.py`) or a writer slot that section 10 does not give it.
- Stop before C-DOC1 or DELIV C2a starts if the DELIV plan does not yet carry the section 10
  lane table and the `_result.py` slot.
- Stop if a legacy `--json` key would be added, removed or change value; only `result`,
  `result_status` and `reason` are new.
- Stop if `run/_result.py` would pass 300 lines, or a second CLI-owned refusal list appears
  beside `_usage_types()` and `_cli_refusal_types()`.
- Stop if a second `reason_from_exception` call, a second `build_run_result(` call or a second
  exit table appears.
- Stop if E-OOM is started before #506 merges, or if a slice needs any other registry code.
- Name the defect class of every finding; write the tests first and see them red; mutate your
  own diff; run baselines in the same environment from `uv.lock`; never widen a threshold, skip
  a test or loosen an assertion; stop and report if a defect of a class already in the catalog
  repeats.
- Commits: Conventional Commits subject, at most 72 characters, final line `cam`, no other
  trailer.

## 16. Not verified

- The Ctrl-C exit status and stderr line of `decoy run` today (no tests run on this machine).
- That every widened code reaches `_errors.fail` as a coded `DecoyError` and is not wrapped on
  the way (read at the raise sites only).
- The full list of `execution_telemetry` route values (E2b STEP ZERO lists them).
- CLI PR #216 as it will merge (read from its open diff: it adds `ctx.progress` and
  `run/_progress.py`).
- Whether the DELIV plan's second review already changed its exit map text.
- Whether `write_local_target` `REPLACE` replaces a final link, which sets the `--result` entry's
  `replaces_final` value (C-DOC3 STEP ZERO), and how the collision key treats a hard link.
- Whether `estimate_job_capacity` can raise any of the four widened codes (C-CAP's AT-C3 patches
  the raise, so it holds either way).
- Platform consumers of `CAPACITY_REASON_CODES` (the platform is parked; C-CAP greps for them).
- That the registry walk with `oom` added yields exactly the plan's capacity and exclusion sets
  (read by grep, not by a live import of the registry; E-CAP STEP ZERO lists the walk).
