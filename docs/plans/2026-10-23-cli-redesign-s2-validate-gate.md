# S2 build plan — the `validate` pre-run gate

Status: build plan, PRE-RELEASE (2026-10-23). Second sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Operationalizes the design writeup
`docs/plans/2026-10-23-validate-consolidation-writeup.md` (which this adopts) and extends it to also fold the
top-level `plan` command. Breaking, pre-GA hard delete. Awaiting plan-gate review before DEVELOP.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, documentation,
api-and-compatibility, reuse-first, scope-discipline, testing.

Risk: R2. Breaking surface change + a real behavior change (new default `validate` aggregates three check
layers; exit-code aggregation). Pre-GA, feature-branch, reversible, no engine behavior change, no merge to
main. No R3 side effect.

## Guarantee

A developer who wants to know "is my job OK to run?" calls one command:
- `decoy validate CONFIG` — runs the WHOLE pre-run gate (config -> compile -> preflight) and prints one
  report grouped by layer, with one aggregated exit code.
- `decoy validate config CONFIG` — schema + config-only checks (fast, no source read). UNCHANGED.
- `decoy validate compile CONFIG [--explain] [--output PLAN]` — plan compilation + the S1 plan-compile
  checks; `--explain` prints the per-column/table rationale; `--output` writes the frozen plan artifact.
- `decoy validate preflight CONFIG [--local] [--fail-on-warning]` — source/file/schema readiness +
  capacity estimate + native probe.
- `decoy validate distribution ...` — UNCHANGED, post-run, explicitly NOT part of the default (relocates to
  `report fidelity` in S4; untouched here beyond a "moving in S4" help note).

The config-only validation runs EXACTLY ONCE in the default path (no triple-run).

Non-goals: no change to what any individual check computes (the engine checks are reused verbatim); no
relocation of `distribution` (S4); no `--force`/overwrite work (S1 B2 follow-up).

## Established solutions / reuse

- The three checks already exist and are reused unchanged: `validate config` composes
  `PipelineConfig.model_validate` + `run_config_only_checks` (`cli/validate.py:291,320,344`); `compile`
  composes `compile_plan(..., no_profile=True)` + the plan-compile checks (`cli/compile_explain.py:140-159`);
  `preflight` composes source-file + target-overwrite + `estimate_job_capacity` + `native_companion_status`
  (`cli/preflight.py:188,369,549`). S2 is a RE-LAYERING of existing calls, not new check logic.
- Two result accumulators already exist: `_ValidationAccumulator` (`validate.py:160+`) and
  `_PreflightAccumulator` (`preflight.py:120+`, which already distinguishes fail/warn and owns the
  capacity fan-in -> EXIT_CAPACITY). S2 unifies them into one aggregate report with a `layer` tag per
  finding rather than inventing a third shape.
- Convention source for the one-envelope / `messages[]` shape and the exit-code precedence is the
  validate-consolidation writeup (§"Proposed surface", §"Design decisions") + clig.dev (human report +
  stable `--json`).

## Design notes

House style on touched code. New structure: ONE aggregate result type carrying findings tagged by
`layer ∈ {config, compile, preflight}` with `severity ∈ {error/fail, warn}`, built once and rendered two
ways (grouped human report; one `--json` envelope with a `messages` list of
`{layer, severity, code, message, location}`). The shared config-only layer is a single function each path
composes (config alone; the default; and preflight's steps 1-3), so it executes once in the default
(dedupe). One place per fact: the config-only checks live in one layer function, not restated in three
commands. No flag argument that switches behavior; `--explain` stays a `compile`-layer concern (the default
reports pass/fail only, not the explain rationale — per the writeup's lean).

## Surface + layering

```
validate CONFIG                      config-layer -> compile-layer -> preflight-layer, one report, one code
validate config CONFIG               config-layer only (fast, no source read)             [unchanged]
validate compile CONFIG --explain    compile-layer (+ config-layer beneath it); --explain rationale
validate compile CONFIG --output P   also write the frozen plan artifact (absorbs today's `plan`)
validate preflight CONFIG            preflight-layer (source/capacity/native; includes config-layer)
validate distribution ...            post-run fidelity                                    [unchanged, S4 note]
```

Layer composition (dedupe): config-layer is the base; compile-layer and preflight-layer each depend on a
VALID config, so they compose the config-layer's result rather than re-run it. In `validate` (default) the
config-layer runs once; compile and preflight consume its parsed/validated config.

## `plan` + `compile` + `preflight` disposition (deletions)

- Delete top-level `compile` (`cli/compile_explain.py` command) and `preflight` (`cli/preflight.py` command);
  their logic moves to the `validate compile` / `validate preflight` subcommands. Keep the check helpers.
- Delete top-level `plan` (`cli/plan.py`). Its one real capability — writing the frozen plan artifact — is
  absorbed by `validate compile --output PLAN` (`--format yaml|json`, resolving the S1-deferred `plan --json`
  question: `validate compile --json` is the standard envelope; the artifact's on-disk format is `--format`).
  Confirm with plan-gate that no caller needs a standalone `plan` verb.
- Update `__main__.py` (remove the three top-level registrations + their imports/epilogs; `validate_app`
  gains `compile`/`preflight` subcommands), the root-help `_ROOT_HELP` lines that name `compile`/`plan`
  (the S1 anti-drift test will fail until they are reconciled — that is the test doing its job), the README,
  `explain` topics, and `docs/cli-reference.md` (regen).

## Exit-code precedence (one contract for the default)

Aggregate all findings; the default's exit code is the worst outcome by this precedence (highest first):
1. **usage error** (config did not parse / schema invalid / a layer raised a usage error) -> `EXIT_USAGE` (1)
2. **capacity refusal** (preflight's fan-in impossibility) -> `EXIT_CAPACITY` (5) — preserved as its own code
3. **findings** (any fail-severity finding) -> `EXIT_USAGE` (1)  *(align with today's per-command behavior)*
4. **warnings** -> `EXIT_OK` (0) unless `--fail-on-warning`, then `EXIT_USAGE` (1)
`--fail-on-warning` applies across the whole aggregate (an advisory capacity WARNING does not fail the
default unless asked; the hard capacity FAIL always exits `EXIT_CAPACITY`). The subcommands keep their
current individual exit semantics. (Plan-gate: confirm findings map to `EXIT_USAGE` vs a distinct code — the
writeup §3 leaves "worst-severity wins"; today compile/preflight use `EXIT_USAGE` for a failed check, so
reuse it rather than mint a new one.)

## Tests (written first where meaningful)

- `validate CONFIG` happy path: a clean config exits 0 and the report shows all three layers passing.
- Dedup: the config-only checks execute exactly once in the default (assert via a spy/patch on
  `run_config_only_checks` call count == 1 for `validate`, not 3).
- Each layer surfaces its own failure in the default: a schema error (usage), a compile-check failure, a
  preflight source-missing fail, and the capacity fan-in -> `EXIT_CAPACITY`; assert the aggregated code
  follows the precedence and the `--json` `messages[]` carries the right `layer`/`severity`/`code`.
- `--fail-on-warning` flips an advisory warning (e.g. advisory capacity) to `EXIT_USAGE` but a clean-but-warn
  run is 0 without it.
- Subcommands run exactly their layer with today's semantics: `validate config` unchanged (regression net);
  `validate compile --explain` prints rationale; `validate compile --output plan.yaml` writes a plan the
  engine can read back; `validate preflight` matches old `preflight` output.
- Deletions: `plan`, `compile`, `preflight` top-level resolve to "No such command"; the anti-drift +
  surface tests pass after `_ROOT_HELP`/README/reference are reconciled.
- One combined `--json` envelope shape is pinned (keys + `messages[]` item shape).

## Verification

Full `pytest -q` green (new + the existing validate/compile/preflight/plan suites, adapted); `ruff check`;
regen `docs/cli-reference.md` + `test_cli_surface.py` + `test_surface_docs_consistency.py` green;
test-strength on the new aggregate/layer code.

## Acceptance

- `validate` runs config+compile+preflight, one grouped report + one JSON envelope, config-only checks run
  once; exit code follows the precedence; capacity fan-in still exits `EXIT_CAPACITY`; `--fail-on-warning`
  spans the aggregate.
- Each subcommand runs exactly its layer with today's semantics; `validate compile --output` writes the plan
  artifact (absorbing `plan`).
- `plan`/`compile`/`preflight` are gone top-level; `validate distribution` unchanged and not in the default.
- Full suite + ruff green; all three doc-surface sentries green; no engine behavior change.

## Loop handoff

Plan-gate review before DEVELOP (confirm: the `plan`->`validate compile --output` fold; the findings
exit-code choice; the layering dedupe). On GO: build in recoverable slices (S2a: add `validate compile` +
`validate preflight` subcommands composing existing helpers, delete the three top-level commands; S2b: the
`validate` default aggregator + one envelope + precedence; S2c: reconcile root-help/README/reference + the
anti-drift allowlists), each self-check + verify, then one independent review of the S2 diff, then DOCUMENT.
No merge to main.