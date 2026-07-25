# Plan: OOM checker, CLI-first v1

Status: PLAN v2 (Opus-authored 2026-07-24, Codex plan-reviewed REVISE -> revised; build-ready). The
"Codex plan-review revisions" section at the end OVERRIDES the body where they conflict; read it as the spec.
Scope decision: Cam chose CLI-first v1 (2026-07-24). Platform reconciliation + generate-path
sizing are tracked fast-follows, NOT in this plan. No dependency on the paused GCP calibration.

## Context

The engine already has a real capacity gate, `enforce_ooc_memory_preflight`
(`decoy-engine/.../execution/out_of_core/_memory_estimate.py:460`): mid-run, on the out-of-core
FK-mask route, it predicts a job's resident-memory floor vs the cgroup-aware budget and raises
`ExecutionError(code="out_of_core_insufficient_memory", message="... this job needs approximately
N GB ...")` (or `out_of_core_fanin_exceeds_budget`). Today the CLI swallows that good message into
its generic runtime-error path (`decoy/src/decoy/cli/run.py:534` catch-all, EXIT_RUNTIME, printed as
`error: <message>`), with no capacity label, no distinct exit signal, and no pre-run warning. This
v1 productizes that existing refusal into an operator-facing capacity check on the CLI.

Two deliverables:
- **A. Labeled capacity refusal in `decoy run`** (small; the engine already refuses, we just surface
  it as a distinct, machine-detectable capacity result).
- **B. Pre-run capacity check in `decoy preflight`** (larger; estimate "needs ~X GB, you have Y"
  BEFORE a run, so a long job is refused up front instead of after it starts).

## Facts established (read 2026-07-24)

- `ExecutionError` (`decoy-engine/.../execution/_errors.py:19`) carries `code: str` + `message: str`
  only; the GB figure is IN the message, not a field.
- The refusing codes: `out_of_core_insufficient_memory` (`_memory_estimate.py:556`) and
  `out_of_core_fanin_exceeds_budget` (`:125`).
- The cgroup-aware "you have Y" detector: `detect_effective_memory_bytes()`
  (`decoy-engine/.../out_of_core/_budget.py:338`); the recommendation math is
  `declared_minimum_ceiling_bytes()` (`_memory_estimate.py:398`).
- The preflight is called only inside the OOC route (`_pipeline_route_exec.py:360`), after plan
  compile, with row counts + FK fan-in already known. There is NO estimate-only entrypoint today.
- `decoy run` error handling: `except Exception` at `run.py:534`, type-dispatch to EXIT_USAGE vs
  EXIT_RUNTIME, then a `--json` envelope via `emit_json` or a stderr render. `ExecutionError` is not
  in the EXIT_USAGE list, so it is EXIT_RUNTIME.
- `decoy preflight` (`preflight.py`) runs LOCAL YAML/schema/source-existence checks and explicitly
  excludes engine run-time constraints (capacity/row counts). It reuses the `validate` config-only
  check path.

## Design

### Part A — labeled capacity refusal in `decoy run`

In the `run.py:534` handler, BEFORE the generic render, add a typed branch:
```
if isinstance(exc, ExecutionError) and exc.code in _CAPACITY_CODES:
    # distinct capacity refusal, not a generic runtime defect
    _emit_capacity_error(state, code=exc.code, message=exc.message)
    raise typer.Exit(code=EXIT_CAPACITY)
```
- `_CAPACITY_CODES = {"out_of_core_insufficient_memory", "out_of_core_fanin_exceeds_budget"}`.
- Render: human stderr gets a labeled line, e.g. `capacity: <message>` + a hint
  ("this job needs more memory than this host has; use a larger tier or reduce the job"). The
  `--json` envelope gets `{"status":"error","error_kind":"capacity","code":<code>,"message":<message>}`
  so scripts can detect it.
- Exit code: NEW `EXIT_CAPACITY` in `decoy/src/decoy/cli/exit_codes.py`, distinct from EXIT_RUNTIME,
  so automation can tell "needs a bigger box" from "the run crashed". (Decision to confirm at review:
  add a new code vs reuse EXIT_RUNTIME with only the JSON `error_kind`. Recommend the new code; it is
  the machine-detectable signal the roadmap asks for.)
- `ExecutionError` import: lazy, matching the existing lazy engine imports in this handler; guard the
  isinstance with a `()` fallback when the class is unavailable (mirror the MaskSecretError pattern at
  `run.py:544-551`) so the error handler never crashes on an old engine.

The engine message already contains the GB figure; v1 passes it through. (Fast-follow: the engine
could add structured `needed_gib`/`available_gib` fields to `ExecutionError` for the CLI to format
itself; out of scope here.)

### Part B — pre-run capacity check in `decoy preflight`

Add an ENGINE estimate-only entrypoint (the model belongs in the engine; the CLI only renders):
`estimate_job_capacity(config, sources, *, budget_bytes: int | None = None) -> CapacityEstimate`
in a new/existing engine module (e.g. `decoy_engine.execution.capacity`). It:
1. Compiles the plan config-only (reuse the existing config-only compile the CLI already calls; no
   profile, no execution).
2. Determines the route the job WOULD take (reuse the engine routing decision) and, for the OOC-FK
   route, derives `parent_table_rows` + `incoming_edge_counts`. Row counts come from a cheap
   metadata read of the source files (parquet footer row-count; CSV: a counted scan or a documented
   estimate) — NOT a full load.
3. Calls the SAME `enforce_ooc_memory_preflight` math in a NON-raising mode (return the
   `MemoryPreflight` / a verdict instead of raising), using `budget_bytes` from
   `detect_effective_memory_bytes()` when not supplied.
4. Returns `CapacityEstimate{fits: bool, needed_gib: float | None, available_gib: float | None,
   route: str, detectable: bool, reason: str}`. When RAM is undetectable (budget None) it returns
   `detectable=False` and does not claim a verdict (fail-open, matching the engine gate).

In `decoy preflight`, add a capacity section (only when the config declares a run the estimator
covers): call `estimate_job_capacity`, and render one of:
- `capacity: OK — needs ~X GB, you have ~Y GB` (fits),
- `capacity: INSUFFICIENT — needs ~X GB, you have ~Y GB; use a larger tier or reduce the job`
  (does not fit) -> preflight exits non-zero (EXIT_CAPACITY), so an operator is refused up front,
- `capacity: not checked — available memory not detectable here` (fail-open),
- `capacity: not applicable — this job does not use the out-of-core route` (keyed/deterministic mask
  or a route with no ceiling; say so plainly).
Preserve preflight's honest framing: it is a v1 that covers the OOC-FK route only; generate-path and
non-FK single-table sizing are explicitly "not checked (v1)".

## Observable behavior (definition of done)

- `decoy run` on a job the engine refuses for memory: exits `EXIT_CAPACITY` (not EXIT_RUNTIME), prints
  a `capacity:` labeled message carrying the GB figure, and `--json` emits `error_kind:"capacity"` +
  the code. A config error still exits EXIT_USAGE; an unrelated crash still exits EXIT_RUNTIME.
- `decoy preflight` on a job that will not fit: prints `capacity: INSUFFICIENT — needs ~X GB, you have
  ~Y GB`, exits EXIT_CAPACITY, WITHOUT running the pipeline. On a job that fits: `capacity: OK`,
  exit 0. On undetectable RAM: `capacity: not checked`, does not fail. On a non-OOC job:
  `capacity: not applicable`.
- No behavior change for jobs that already pass; the engine's mid-run gate is unchanged.

## Known failure modes to guard against

1. Over-broad code match reclassifies a non-capacity ExecutionError as capacity. Guard: match the
   exact two codes only.
2. The pre-run estimate disagrees with the mid-run gate (different inputs) and a job passes preflight
   then fails at run, or vice-versa. Guard: Part B calls the SAME `enforce_ooc_memory_preflight` math
   on the SAME derived inputs; test that preflight-verdict == run-outcome on the same job.
3. Row-count derivation reads/loads too much (defeats "cheap pre-run"). Guard: parquet footer only;
   CSV documented; assert no full frame is materialized in the estimate path.
4. Fail-open lost: undetectable RAM makes preflight refuse a job that would run. Guard: undetectable
   -> "not checked", never INSUFFICIENT; test it.
5. New EXIT_CAPACITY collides with an existing code or breaks the exit_codes contract. Guard: pick an
   unused value; update the exit_codes doc/test.
6. The estimator crashes preflight (e.g. compile error on a valid-but-uncovered config). Guard: the
   capacity section degrades to "not checked / not applicable", never crashes preflight.

## Acceptance tests (red now, green after)

- A1 (Part A): a `run` test that injects the engine `ExecutionError(out_of_core_insufficient_memory)`
  (monkeypatch the execution entrypoint to raise it) asserts exit == EXIT_CAPACITY, a `capacity:`
  label in output, and `--json` `error_kind=="capacity"`, `code==...`. A sibling test with a generic
  `ExecutionError(other_code)` still exits EXIT_RUNTIME (no capacity label) — proves the narrow match.
- A2 (Part A): a config-error run still exits EXIT_USAGE (no regression in type-dispatch).
- A3 (engine): `estimate_job_capacity` on a small job that fits returns `fits=True` with sane
  needed/available; on a job whose declared rows exceed a tiny injected budget returns `fits=False`
  with `needed_gib` matching what the mid-run gate reports. Same inputs -> same verdict (failure
  mode 2).
- A4 (engine): undetectable budget (`budget_bytes=None`, detector patched to None) returns
  `detectable=False`, `fits` not asserted.
- A5 (Part B): `decoy preflight` on a fits/does-not-fit/undetectable/non-OOC job renders the four
  respective lines and exits 0 / EXIT_CAPACITY / 0 / 0, WITHOUT executing the pipeline (assert the
  execution entrypoint was not called).
- A6 (parity): a single job run through BOTH `decoy preflight` and `decoy run` agrees (preflight
  INSUFFICIENT <=> run refuses with EXIT_CAPACITY) — the anti-drift test.

## Build order
1. `EXIT_CAPACITY` in exit_codes.py + its contract test.
2. Part A: the typed capacity branch in run.py + `_emit_capacity_error` + JSON `error_kind`. Tests A1/A2.
3. Engine: `estimate_job_capacity` + `CapacityEstimate`, reusing the existing preflight math in a
   non-raising mode + cheap row-count read + `detect_effective_memory_bytes`. Engine tests A3/A4.
4. Part B: the `decoy preflight` capacity section. Tests A5.
5. Parity test A6. Docs: regenerate cli-reference for any new flag; note the v1 scope (OOC-FK route
   only) in preflight's help.

## Out of scope (tracked fast-follows)
- Generate-path sizing (needs the paused GCP sweep + a new ExecutionPath).
- Platform reconciliation (`admission.py` <-> engine estimator; making the OOC preflight reachable
  through the platform runner) — the larger architectural item in the gap doc §3.
- Structured `needed_gib`/`available_gib` fields on `ExecutionError`.
- Distinct-key cardinality signal; non-FK single-table byte check.
- Recalibrating the engine constants (`_BUILD_FLOOR_BYTES_PER_ROW` etc.) once the sweep resumes.

## Codex plan-review revisions (2026-07-24) — REQUIRED, override the body on conflict

Codex verdict REVISE. Each finding and the corrected spec:

### R1 (P1) — one pure evaluator shared by BOTH gates (anti-drift)
Factor a PURE capacity evaluator out of `enforce_ooc_memory_preflight`:
`evaluate_capacity(inputs: CapacityInputs, budget_bytes: int | None) -> CapacityEstimate`,
where `CapacityInputs` is the TYPED, already-derived set (parent_table_rows, incoming_edge_counts,
sink, route). BOTH the mid-run gate (which keeps raising on INSUFFICIENT) and the estimate-only
entrypoint call THIS. Also share the route-selection + input-derivation: the estimate path must run
the SAME routing decision and the SAME `parent_table_rows`/`incoming_edge_counts` derivation the run
path uses, not a re-implementation. The mid-run gate becomes: `est = evaluate_capacity(...); if
est.verdict is INSUFFICIENT: raise ExecutionError(est.code, est.message)`.

### R2 (P1) — explicit estimator boundary; no materialized tables; base_dir
`estimate_job_capacity` takes the NORMALIZED config (`PipelineConfig.model_dump()`) plus an explicit
`base_dir` (or already-resolved source descriptors), NOT Arrow tables. run resolves sources against
the YAML dir (`run.py:938`); preflight against CWD (`preflight.py:177`) -> both must pass the SAME
resolved descriptors/base_dir into the estimator so path resolution cannot differ.

### R3 (P1) — tri-state verdict; defects stay runtime failures
`CapacityEstimate.verdict in {FIT, INSUFFICIENT, UNKNOWN, NOT_APPLICABLE}` (drop `fits: bool`; if a
bool is kept it is `fits: bool | None` with None == UNKNOWN). ONLY `INSUFFICIENT` may exit
`EXIT_CAPACITY`. `UNKNOWN` is for EXPECTED indeterminacy (RAM undetectable; CSV not exactly countable;
engine estimator absent) -> CLI exits 0, prints "not checked". An UNEXPECTED estimator exception is
NOT swallowed into UNKNOWN: it propagates as a normal runtime failure (never a false-successful
preflight). A4 asserts verdict == UNKNOWN and exit 0.

### R4 (P1) — honest v1 framing (this does NOT prove the whole job fits)
`run` fully loads parquet/CSV BEFORE `run_pipeline` (`run.py:510,940`), so an ingestion `MemoryError`
or OS OOM-kill occurs before the engine gate and will NOT become `EXIT_CAPACITY`; the engine
resident-floor estimate also excludes the CLI's pandas->Arrow ingestion peak. v1 is explicitly an
opt-in "OOC-FK engine-gate capacity checker", not a whole-job OOM guarantee. `capacity: OK` says what
passed: "OOC-FK estimated resident floor is within budget (does not include ingestion peak)". Say so
in preflight help and the refuse/OK copy. (Auto-running the estimator before materialization is a
fast-follow consideration; it still would not cover the ingestion peak, so the framing is the fix.)

### R5 (P1) — engine-version compatibility for Part B
The new estimator entrypoint won't exist in `decoy-engine==0.5.0`. Either bump the CLI floor to the
first engine version that ships `estimate_job_capacity` (preferred; a chore(deps) commit), OR
capability-detect the entrypoint (`hasattr`) and return `UNKNOWN` ("capacity check needs a newer
engine") when absent. Part A's defensive import does not cover Part B. Decide at build: if the engine
change lands in the same cycle, bump the floor.

### R6 (P2) — CSV counting
Parquet: footer row-count (cheap, exact) -> usable for a refusal. CSV: an exact count is an O(size)
scan AND must use run-equivalent parsing (quoted multiline, parser options); a naive line count is
wrong. v1: EITHER do an exact count with the SAME reader options the run uses, OR return `UNKNOWN` for
CSV. NEVER refuse on an approximation. Recommend UNKNOWN for CSV in v1 unless the exact-count path is
trivially the run's own reader; note it in the honest framing.

### R7 (P2) — preserve the run JSON error contract
The existing `--json` error envelope has `command`, `config`, `mode`, `error` (`run.py:612`). The
capacity branch ADDS `error_kind:"capacity"` and `code`; it does NOT drop `error`. The early branch
must retain the 500-char message cap, failure-notification dispatch, quiet-mode behavior, and
verbose-traceback behavior the later handler already implements (refactor so the capacity branch flows
through the same emit, just pre-tagged, rather than a parallel emit that loses those).

### R8 (P2) — EXIT_CAPACITY = 5 + full surface update
0-4 are public/pinned (`exit_codes.py:27`, `test_exit_codes.py:25`); `2` is taken (preflight
`_WARN_EXIT` + deprecated-shim). Use `EXIT_CAPACITY = 5`. Update `__all__`, README, `decoy explain
exit-codes`, the generated cli-reference if affected, `test_exit_codes.py`, and the CHANGELOG.

### R9 (P2) — CapacityEstimate carries exact bytes + code
Fields: `verdict`, `code` (one of the two refusal codes when INSUFFICIENT, else None),
`needed_bytes`, `available_bytes` (exact ints; GiB is display-only), `route`, `message`. Both refusal
modes (`out_of_core_insufficient_memory`, `out_of_core_fanin_exceeds_budget`) are representable and
assertable without parsing display text.

### Revised acceptance tests (supersede A1-A6)
- T1 (Part A, human): inject engine `ExecutionError(out_of_core_insufficient_memory)` at the run
  execution seam -> exit EXIT_CAPACITY, `capacity:` label, GB figure present. Repeat for
  `out_of_core_fanin_exceeds_budget`.
- T2 (Part A, json): same injection with `--json` -> envelope keeps `command/config/mode/error` AND
  adds `error_kind=="capacity"`, `code==<code>`.
- T3 (Part A, negatives): a non-capacity `ExecutionError` still exits EXIT_RUNTIME; a config error
  still exits EXIT_USAGE (regression guards, not red-before).
- T4 (engine, evaluator): `evaluate_capacity` on typed inputs returns FIT within budget, INSUFFICIENT
  when floor>budget with `needed_bytes` matching the mid-run raise on the same inputs (parity at the
  evaluator, not just a fixture), NOT_APPLICABLE for a non-OOC route.
- T5 (engine, unknown): budget None (detector patched) -> UNKNOWN, `fits is None`.
- T6 (engine, no-materialization): estimate over a parquet source reads the footer only (assert no
  full frame built); CSV path returns UNKNOWN (or exact-count if implemented) and never materializes.
- T7 (Part B): `decoy preflight` over fit / insufficient / unknown / not-applicable jobs -> the four
  lines and exit 0 / EXIT_CAPACITY / 0 / 0, WITHOUT calling the execution entrypoint; INSUFFICIENT
  must exit EXIT_CAPACITY, NOT preflight's generic `has_failures -> EXIT_USAGE` path
  (`preflight.py:381`). Include a RELATIVE source-path case + a threshold-boundary case.
- T8 (parity, end-to-end): one job run through BOTH `preflight` and `run` (real derivation, not mocked
  verdicts) agrees: preflight INSUFFICIENT <=> run raises + EXIT_CAPACITY. Parameterize over
  fit/insufficient and both refusal codes.
- T9 (version compat): with the estimator entrypoint absent (simulate old engine) -> preflight
  capacity section returns UNKNOWN and exits 0 (or the floor is bumped and this is a dep test).

### Revised build order
1. Engine: extract `evaluate_capacity` + `CapacityInputs`/`CapacityEstimate` (tri-state, exact bytes,
   code); re-express the raising gate in terms of it (T4/T5). Share the input-derivation + routing.
2. Engine: `estimate_job_capacity(config_dump, base_dir, budget_bytes=None)` reusing (1) + cheap
   row-count read (parquet footer; CSV UNKNOWN or exact-with-run-reader) (T6). Version/floor decision (R5).
3. CLI: `EXIT_CAPACITY=5` + surface updates (R8). Part A capacity branch through the existing emit
   (R7) (T1/T2/T3).
4. CLI: `decoy preflight` capacity section (R2 base_dir, tri-state render, EXIT_CAPACITY not EXIT_USAGE)
   (T7). Honest framing copy (R4).
5. Parity test T8; version-compat T9; regenerate cli-reference; CHANGELOG.
