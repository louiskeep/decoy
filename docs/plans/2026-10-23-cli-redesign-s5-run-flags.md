# S5 build plan — `run` capability flags (+ disguise-wiring escalation)

Status: build plan, PRE-RELEASE (2026-10-23). Fifth sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Additive (new flags), pre-GA. Awaiting plan-gate review.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, scope-discipline,
documentation, testing.

Risk: R2 (additive CLI flags surfacing existing engine kwargs; no engine change; feature-branch; no merge).

Plan-gate review incorporated (GO-WITH-REVISIONS, 2026-10-23): the escalation was confirmed JUSTIFIED on all
three pieces (not over-cautious). Fixes folded in: P1-1 `--explain-plan` surfaces the EXECUTION-ROUTE
decision (`quality_metrics["execution_plan"]`), NOT a per-column rationale — no parity claim with `validate
compile --explain`; P1-2 enforce is a result FIELD (`failed_checks`), not an exception — the CLI maps it to
`EXIT_FINDINGS` after the write; P2-3 reject `--chunked` + any flag as `EXIT_USAGE` (chunked path returns no
ExecutionResult); P2-4 word `--fidelity` as a quick inline check, not grade-parity with `report fidelity`;
P2-5 test corrections. (Advisory for the owner follow-up: the engine has `storm/recommendations.py
get_default_strategy(detector_id)` — a per-detector smart-default mask table — which could power a narrower
engine-sourced `scan`→starter-masks later; it is not a disguise/regime recommender and is itself unexported.)

## Scope change from the sprint doc (read first)

The sprint doc's S5 was "disguises end-to-end (`init --preset` for 10 bundles, `scan --suggest`) + `run`
flags". Investigation during planning found the disguise half is **NOT autonomously buildable** and is
escalated to the owner (below). S5 ships the **run capability flags** — the clean, domain-risk-free half —
and surfaces the disguise wiring as owner-gated. This is a scope-discipline + autonomous-operation call
("stop for human direction when the next action needs new authority"), not a silent drop.

### Why the disguise wiring is escalated, not built
- **`init --preset` for the other ~7 compliance regimes = authoring legal artifacts.** Per
  `tests/unit/test_template_disguise_drift.py`, a compliance template is "the canonical legal artifact for
  its regulation, versioned on a date," hand-DERIVED from a specific engine disguise version (carrying an
  `# x-derived-from-disguise: <id>@<date>` marker, drift-enforced). Only hipaa/pci/gdpr exist. Authoring
  GLBA/CCPA/FERPA/SOX/CPNI/etc. masking templates is compliance-domain work with real-world-harm risk — it
  needs the owner's authority and a compliance review, not an autonomous builder.
- **`scan --suggest` = compliance-recommendation logic that belongs in the engine.** It must evaluate each
  disguise's `TriggerSpec` (required/any/co_occurrence detectors) against a scan's detections. The engine
  exposes the data (`load_disguises()`, `TriggerSpec`) but NO evaluation/recommend function; reimplementing
  trigger semantics in the CLI violates the charter ("data behavior belongs in the engine") and risks drift
  from the canonical intent. Needs an engine `recommend_disguises(profile)` export first, then a CLI slice.
- **`run --pin`** (pinned-generation reproducibility) stays deferred: `generation/pinned.py` is not in
  `decoy_engine.__all__` (needs an additive engine export).

Owner action for the disguise story: (1) author/greenlight the ~7 compliance templates (legal review);
(2) add an engine `recommend_disguises` + export `load_disguises`/pinned at top level. Then a follow-up CLI
slice ships `init --preset <all>` + `scan --suggest` + `run --pin`. `list disguises` already shipped (S3).

## Guarantee (what S5 builds)

`decoy run` surfaces the report-shaped engine kwargs it already accepts, as clean flags (all default off,
all reading `ExecutionResult.quality_metrics`):
- `run --explain-plan` → `run_pipeline(explain_plan=True)`: render the **execution-route decision** from
  `quality_metrics["execution_plan"]` = `{mode, reason, rejections}` (why sequential vs full_frame vs
  out_of_core). **NOT** the per-column masking rationale — that comes from `compile_plan` and is what
  `validate compile --explain` gives pre-run; `run_pipeline` does not produce it, so S5 does NOT claim
  parity (P1-1). Stamped even for pure-generate runs (classify_job runs whenever `explain_plan` is set).
- `run --fidelity` → `run_pipeline(fidelity_report=True)`: render the inline distribution-fidelity report
  from `quality_metrics["fidelity_reports"]` (per-mask-table, marginal-only, report-only — a low grade never
  fails the run). A QUICK inline check; not grade-parity with the fuller post-hoc `report fidelity` (P2-4).
- `run --post-validate` → `run_pipeline(post_validation=True)`: render the job-level validator results from
  `quality_metrics` (`failed_checks`, `quality_summary`). `run --post-validate-enforce` →
  `post_validation_enforce=True`: the engine does NOT fail the job (it only stamps `failed_checks` +
  `post_validation_enforce`; _pipeline.py:190-199) — the CLI does the mapping: after `_write_mask_outputs`,
  `if enforce and result.quality_metrics.get("failed_checks"): raise typer.Exit(EXIT_FINDINGS)` (P1-2).
  `--enforce` implies `--post-validate`.

All pass through to existing `run_pipeline` kwargs (`execution/_pipeline.py:123/124/127/135`); the CLI adds
flags + renders `quality_metrics` fields. No engine change; no data behavior in the CLI.

Non-goals: the disguise wiring (escalated above); `run --pin` (engine export); any change to the default run
behavior (all three flags default off).

## Design notes

House style on touched code. No new abstraction — four boolean flags on the existing `run` command, passed
to the existing `run_pipeline` call, with small render helpers for the execution-route / fidelity /
post-validation sections (data comes from `ExecutionResult.quality_metrics`; the CLI only formats). Do NOT
reuse `validate compile --explain`'s per-column rationale renderer — the payloads differ (route decision vs
column rationale, P1-1); write a small dedicated route renderer.

## Slice (single)

- Add `--explain-plan`, `--fidelity`, `--post-validate`, `--post-validate-enforce` to `cli/run.py`'s `run`
  command; pass the matching kwargs into the existing non-chunked `run_pipeline(...)` call (run.py ~660-668);
  after the run, render each requested section from `result.quality_metrics` (route `execution_plan`;
  `fidelity_reports`; `failed_checks`/`quality_summary`) in human mode and in the `--json` envelope (run.py
  already has a success envelope ~946-962 + `render_card` ~968-985 to extend).
- **Enforce mapping (P1-2):** the engine does NOT raise/fail on an enforced validator failure — it only
  stamps `quality_metrics["failed_checks"]` + `["post_validation_enforce"]`. So, AFTER `_write_mask_outputs`
  (run.py ~679, the masking already succeeded), do:
  `if post_validation_enforce and result.quality_metrics.get("failed_checks"): raise typer.Exit(EXIT_FINDINGS)`
  (import `EXIT_FINDINGS` from `cli.exit_codes`). `--enforce` implies `--post-validate`.
- **`--chunked` interaction (P2-3):** these flags only flow into the non-chunked path; `_run_chunked_mask`
  (run.py ~647-656) returns no `ExecutionResult`. Reject `--chunked` combined with any of the four flags as
  `EXIT_USAGE` with a clear message (mirror the existing `_ChunkedGenerateError` pattern ~run.py:564) — do
  NOT silently no-op.
- Help/epilog: document the four flags with examples; make clear `--explain-plan` shows the EXECUTION ROUTE
  (not per-column rationale — point to `validate compile --explain` for that) and `--fidelity` is a QUICK
  inline marginal check (point to `report fidelity` for the fuller post-hoc grade). Regen
  `docs/cli-reference.md`; keep the three doc sentries green.
- Tests: `run --explain-plan` renders the `execution_plan` fields (mode/reason/rejections) + `--json` carries
  them (assert on route fields, NOT a per-column rationale); a pure-GENERATE `--explain-plan` run still
  stamps a non-empty `execution_plan`; `run --fidelity` renders a fidelity section and does NOT fail on a low
  grade; `run --post-validate` renders validator results (exit 0); `run --post-validate-enforce` exits
  `EXIT_FINDINGS` ONLY when `failed_checks` is non-empty (and 0 when all pass), with the output files still
  written; `--chunked` + any flag → `EXIT_USAGE`; the default `run` (no flags) is byte-for-byte unchanged
  (regression net).

## Verification

Full `pytest -q` green; `ruff check`; regen reference + sentries green; test-strength on the new flag
branches (esp. the enforce → EXIT_FINDINGS path).

## Acceptance

- `run --explain-plan`/`--fidelity`/`--post-validate[-enforce]` work, default off, surfacing the existing
  engine kwargs; `--post-validate-enforce` is the only one that can change the exit code (→ EXIT_FINDINGS).
- Default `run` unchanged; no engine change; full suite + ruff + sentries green.
- The disguise wiring + `run --pin` are recorded as owner-gated/engine-dependent follow-ups (not built).

## Loop handoff

Plan-gate review before DEVELOP (confirm the scoping/escalation is right — is any part of the disguise
wiring safely autonomous after all? — and that the three kwargs' result fields exist). On GO: build the
single slice, self-check + verify, independent review, DOCUMENT. No merge to main.