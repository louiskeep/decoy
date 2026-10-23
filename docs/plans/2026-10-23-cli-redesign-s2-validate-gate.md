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

Plan-gate review incorporated (GO-WITH-REVISIONS, 2026-10-23): findings 1-8 folded in below. The two
load-bearing corrections: (F1) the `plan` fold must carry `--profile/--no-profile` or it silently drops the
profiled full-check path — `validate compile` now takes those flags, making the fold lossless; (F2) code 2
is NOT unused — `_WARN_EXIT = 2` is already returned by `validate`/`preflight` under `--fail-on-warning`
(`validate.py:63`, `preflight.py:108`), so S1's "code 2 reserved/unused" doc claim was WRONG (the S1 build
and its review both missed it). S2 corrects it by promoting code 2 to a public `EXIT_WARNINGS` constant with
one meaning across all paths.

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

F5 (dedup scope, precise): only the `run_config_only_checks` CALL is deduped to once in the default.
`compile_plan` independently re-validates a superset of those structural checks internally
(`_compile.py`), so on the success path that subset runs again inside compile — harmless and accepted; the
dedup test asserts `run_config_only_checks` is called exactly once, which is the real guarantee.

F7 (envelope mapping): the default `validate --json` is one envelope with a `messages` list of
`{layer, severity, code, message, location}`. Define the maps up front: preflight's `checks[]` `status` ->
`severity` (`fail`->`error`, `warn`->`warning`, `pass` omitted from messages), and each check `name` ->
`code`/`location`. The default view is intentionally COARSER than `validate preflight --json`: the
structured `capacity`/`native_companion`/`native_eligibility` blocks (`preflight.py:805-822`) remain only on
`validate preflight --json`, not flattened into the aggregate. The default `validate` group had no prior
`--json` envelope (it is `no_args_is_help`), and each subcommand keeps its own existing envelope — so no
stable shape is broken.

## Surface + layering

```
validate CONFIG                           config-base, then compile + preflight (run all, aggregate)
validate config CONFIG                     config-layer only (fast, no source read)         [unchanged]
validate compile CONFIG [--explain]        compile-layer (config-base beneath); --explain rationale
validate compile CONFIG --profile P        full profiled compile (profile-dependent checks run)
validate compile CONFIG [--no-profile]     no-profile compile (profile-dependent checks skipped) [default]
validate compile CONFIG --output P [--format yaml|json]   also write the frozen plan artifact (absorbs `plan`)
validate preflight CONFIG [--local]        preflight-layer (source/capacity/native; config-base beneath)
validate distribution ...                  post-run fidelity                                [unchanged, S4 note]
```

Layer composition (F3 — shared base + two independent consumers, NOT a 3-level stack): the config-layer is
the shared base; `compile` and `preflight` are INDEPENDENT consumers of a valid config (preflight never
calls `compile_plan`; compile never reads sources/capacity). In the `validate` default: run the config-base
once; if the config fails to PARSE or schema-validate, short-circuit with `EXIT_USAGE` (compile/preflight
cannot run without a valid config). Otherwise RUN BOTH compile and preflight and AGGREGATE all findings (do
NOT short-circuit on a compile failure — the user should see every problem in one pass). The config-base's
`run_config_only_checks` call executes once (dedup); see F5 note under Design notes.

## `plan` + `compile` + `preflight` disposition (deletions)

- Delete top-level `compile` (`cli/compile_explain.py` command) and `preflight` (`cli/preflight.py` command);
  their logic moves to the `validate compile` / `validate preflight` subcommands. Keep the check helpers.
- Delete top-level `plan` (`cli/plan.py`). F1: `plan` is NOT just an artifact writer — it loads a
  pre-computed Profile (`--profile P`) and runs ALL FIVE plan-compile checks including the profile-dependent
  ones (fk_plan_ordering, basic_uniqueness_pre_flight), or records them as `checks_skipped` under
  `--no-profile` (`plan.py:75-82,164-182`). To fold LOSSLESSLY, `validate compile` gains `--profile PATH`
  and `--no-profile` (default `--no-profile`, matching today's `compile`; `--profile` gives the full
  profiled compile), plus `--output PATH`/`--format yaml|json` to write the frozen plan artifact. This
  resolves the S1-deferred `plan --json`: `validate compile --json` is the standard envelope; the artifact's
  on-disk format is `--format`. The H1 (no check in both passed+skipped) and H2 (unique-cardinality) honesty
  guards `plan` enforces (`plan.py:128-149,262-278`) must be preserved — see Acceptance.
- Update `__main__.py` (remove the three top-level registrations + imports/epilogs; `validate_app` gains
  `compile`/`preflight` subcommands) and `docs/cli-reference.md` (regen).

## Dead-string sweep + grep gate (F4 — analog of S1 slice A)

The anti-drift sentry covers only `_ROOT_HELP` + the README table, not epilogs/topics/docstrings. After the
deletions these user-facing strings still advertise the removed top-level commands and must be repointed to
`decoy validate compile|preflight`:
- `src/decoy/cli/explain.py:315,319,406,410,419` (`explain exit-codes`/`explain native` name `decoy
  preflight`/its `--help`).
- `src/decoy/cli/subset.py:74` ("See also: ... decoy preflight").
- `src/decoy/cli/exit_codes.py:26,66` and `README.md:126` (the capacity-code text names `decoy preflight`).
- `_ROOT_HELP` (`__main__.py:64`) names `compile` -> repoint to `validate compile`.
Add a grep gate asserting the command strings `decoy compile`, `decoy plan`, and `decoy preflight` (as
top-level invocations) appear nowhere under `src/decoy/`.

## Anti-drift allowlist reconciliation (F6 — exact)

`_ROOT_HELP` names `compile` (line 64) only; `plan`/`preflight` live in `_ROOT_HELP_OMITTED`
(`test_surface_docs_consistency.py:39-52`), and `compile`/`plan`/`preflight` in `_README_TABLE_OMITTED`
(`:57-80`). Required edits so the `stale = OMITTED - TOP_LEVEL` assertions (`:218-222,261-265`) still hold:
rewrite `__main__.py:64` to `validate compile`; PRUNE `plan` and `preflight` from `_ROOT_HELP_OMITTED`; PRUNE
`compile`, `plan`, `preflight` from `_README_TABLE_OMITTED`.

## Exit-code precedence + the code-2 correction (F2)

**Correct the code-2 contract first.** Code 2 is NOT unused: `_WARN_EXIT = 2` is already returned by
`validate`/`preflight` under `--fail-on-warning` (`validate.py:63,363`, `preflight.py:108,779`,
pinned by `test_preflight_capacity.py:267`). S1's docs calling code 2 "reserved/unused" were wrong. S2 fixes
this honestly by PROMOTING code 2 to a public named constant `EXIT_WARNINGS = 2` in `cli/exit_codes.py`
(documented: "ran clean except for warnings, and `--fail-on-warning` was set"), replacing the private
`_WARN_EXIT` in both modules, and correcting the S1 exit-code docs (`exit_codes.py` docstring, the README
exit-code table, `explain exit-codes`) from "2 reserved" to the `EXIT_WARNINGS` meaning. One warning exit
code across the aggregate AND the subcommands (no `validate preflight --fail-on-warning` -> 2 while
`validate --fail-on-warning` -> 1 mismatch).

**Default `validate` exit code** — run all layers, aggregate, then by precedence (highest first):
1. **config parse / schema invalid** -> `EXIT_USAGE` (1). This short-circuits (compile/preflight need a
   valid config).
2. **capacity refusal** (preflight's fan-in impossibility) -> `EXIT_CAPACITY` (5). Outranks lower findings.
3. **any fail-severity finding** (failed compile check, missing source, etc.) -> `EXIT_USAGE` (1). Matches
   today's per-command behavior (compile `compile_explain.py:122,133,156`, preflight `:776-777`).
4. **warnings present AND `--fail-on-warning`** -> `EXIT_WARNINGS` (2).
5. else -> `EXIT_OK` (0).
Co-occurrence resolved: a failed compile check (a "finding", #3) and a capacity refusal (#2) can both
appear; the exit CODE is `EXIT_CAPACITY` (#2 outranks #3) while the REPORT shows both. `--fail-on-warning`
spans the whole aggregate; an advisory capacity WARNING does not fail unless asked; the hard capacity FAIL
always exits `EXIT_CAPACITY`. Subcommands keep their individual exit semantics (now including the unified
`EXIT_WARNINGS`).

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
- One combined `--json` envelope shape is pinned (keys + `messages[]` item shape + the status->severity map).
- F8: `validate compile --profile P` runs the profile-dependent checks (fk_plan_ordering,
  basic_uniqueness_pre_flight) that `--no-profile` skips; the H1 honesty guard (no check in both
  `checks_passed` and `checks_skipped`, `plan.py:262-278`) and the H2 unique-cardinality guard
  (`plan.py:128-149`) hold under the fold; `validate compile --output plan.json --format json` writes an
  artifact the engine reads back (not just yaml).
- F2: `validate --fail-on-warning` and `validate preflight --fail-on-warning` return the SAME code
  (`EXIT_WARNINGS` = 2) for the same warning condition; `exit_codes.py`/README/`explain exit-codes` describe
  code 2 as `EXIT_WARNINGS`, not reserved.

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