# S5 build plan — `run` capability flags (+ disguise-wiring escalation)

Status: build plan, PRE-RELEASE (2026-10-23). Fifth sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Additive (new flags), pre-GA. Awaiting plan-gate review.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, scope-discipline,
documentation, testing.

Risk: R2 (additive CLI flags surfacing existing engine kwargs; no engine change; feature-branch; no merge).

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

`decoy run` surfaces the report-shaped engine kwargs it already accepts, as clean flags:
- `run --explain-plan` → `run_pipeline(explain_plan=True)`: print the per-column/table plan rationale after
  the run (the same explanation `validate compile --explain` gives pre-run), from the `ExecutionResult`.
- `run --fidelity` → `run_pipeline(fidelity_report=True)`: compute + render the distribution-fidelity report
  inline. REPORT-ONLY (a low grade never fails the run), matching the engine contract.
- `run --post-validate` → `run_pipeline(post_validation=True)`: run the job-level validators and render the
  results. `run --post-validate-enforce` → `post_validation_enforce=True`: a failing validator makes the run
  exit `EXIT_FINDINGS` (4). Default off; report-only unless `--enforce`.

All three pass through to existing `run_pipeline` kwargs (`execution/_pipeline.py:122,135,123-128`); the CLI
adds flags + renders the result fields. No engine change; no data behavior in the CLI.

Non-goals: the disguise wiring (escalated above); `run --pin` (engine export); any change to the default run
behavior (all three flags default off).

## Design notes

House style on touched code. No new abstraction — three boolean flags on the existing `run` command, passed
to the existing `run_pipeline` call, with small render helpers for the explain/fidelity/post-validation
result sections (data comes from `ExecutionResult`; the CLI only formats). Reuse `validate compile
--explain`'s rationale renderer if the explain payload shape matches.

## Slice (single)

- Add `--explain-plan`, `--fidelity`, `--post-validate`, `--post-validate-enforce` to `cli/run.py`'s `run`
  command; pass the matching kwargs into the existing `run_pipeline(...)` call; after a successful run,
  render each requested section (explain rationale; fidelity grade/summary; validator results) in human mode
  and include them in the `--json` envelope. `--post-validate-enforce` maps a failing validator result to
  `EXIT_FINDINGS` (reuse `cli.exit_codes.EXIT_FINDINGS`); `--enforce` implies `--post-validate`.
- Confirm the `ExecutionResult` actually carries the explain/fidelity/post-validation outputs when the
  kwargs are set (read the engine result shape; if a field is absent, STOP and report — do not fabricate a
  renderer for data the engine doesn't return).
- Help/epilog: document the three flags with examples; `run --fidelity` cross-links `report fidelity`
  (inline vs post-hoc). Regen `docs/cli-reference.md`; keep the three doc sentries green.
- Tests: `run --explain-plan` prints the rationale + `--json` carries it; `run --fidelity` renders a grade
  and does NOT fail on a low grade; `run --post-validate` renders validator results (exit 0); `run
  --post-validate-enforce` exits `EXIT_FINDINGS` when a validator fails and 0 when all pass; the default
  `run` (no flags) is byte-for-byte unchanged (regression net).

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