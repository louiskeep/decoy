# S1 build plan — Foundations: conventions, deletions, anti-drift

Status: build plan, PRE-RELEASE (2026-10-23). First sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`; surface in
`docs/plans/2026-10-23-cli-interface-redesign.md`, decisions D1-D6 locked). Breaking, pre-GA hard delete.
Plan-gate review incorporated (GO-WITH-REVISIONS, 2026-10-23): findings 1-7 folded in below — deletion
sweep extended to all `storm scan`/`storm test` string references + a grep gate (F1); the `plan --json`
semantic rework deferred to S2 (F2); `--out` count corrected to seven with help/epilog refs in scope (F3);
exit-code test/explain surfaces named (F4); registration note + forge entry-point distinction fixed (F5);
parent-doc test path reconciled (F6); root-help consistency test given a real nested-path extractor (F7).

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, documentation,
api-and-compatibility, scope-discipline, testing.

Risk: R2. Breaking surface change, but pre-GA, feature-branch (`claude/happy-fermi-44osad`), reversible,
no engine/data-semantics change, no merge to main (PO-gated). No R3 side effect.

## Guarantee (what this sprint promises)

After S1, the CLI has a smaller, uniform base for the later sprints to restructure:
- Every command exposes `--json` (stable machine envelope), `--quiet/-q`, `--verbose/-v` with identical
  semantics.
- One flag vocabulary: `--output/-o` is the single spelling for an output path (no `--out`).
- The four vestigial/legacy surfaces are gone: `storm test`, the `storm scan` alias, `jobs watch`, and the
  `forge` shim.
- A drift test prevents the README command table and the root-help block from disagreeing with the live
  command set again.

Non-goals (become follow-ups, not blockers): no command is merged, renamed, or re-parented here (that is
S2-S4); `jobs`/`catalog`/`project` as a whole stay until S4 (only `jobs watch` goes now); no new capability.

## Established solutions

Convention source is the Command Line Interface Guidelines (clig.dev), already cited in the redesign doc:
standard flag names and meanings (`--output/-o`, `-q/--quiet`, `--json`), human-default + machine-ready
output, stdout=data / stderr=messaging. No custom logic; this sprint aligns names to the published standard
and deletes surface. The drift test follows the existing in-repo pattern (`tests/unit/test_cli_surface.py`
re-renders `docs/cli-reference.md` from the Typer app and asserts equality).

## Design notes

House style applies to touched code only. The output trio's *semantics* are single-sourced in
`decoy.ui.output.setup_output` / `OutputMode` and stay there. BUILD DECISION (2026-10-23, confirmed in S1
review): no separate "shared CLI-options helper" was extracted — Typer requires options to be declared in
each command's own signature, so a wrapper would not remove the per-command `typer.Option` declarations and
would fight the framework idiom. The one-place-per-fact rule is satisfied by `setup_output` owning the
behavior; the inline declarations are the Typer idiom. No new abstraction.

## Slices (recoverable; each its own commit, each green before the next)

### A. Deletions (D4 + vestigial)

Two kinds of removal: three Typer subcommands, and one console-script entry point (not a Typer command).

Typer subcommands (all three are commands on `storm_app`/`jobs_app` inside their own modules — the edits are
in those modules, not `__main__.py`, which only mounts the sub-apps at `:122`/`:135`):
- `storm test` — `cli/storm.py:1249` (the animation-preview command).
- `storm scan` deprecated alias — shim ~`cli/storm.py:1326-1335`, registered on `storm_app` ~`:1568`.
- `jobs watch` — `cli/jobs.py:329` (decorator `:328`).
Remove each + its registration; drop tests that pin them as existing; add tests asserting each resolves to
Typer "No such command" (non-zero exit).

Console-script entry point:
- `forge` shim — delete `src/decoy/_deprecated.py` AND its `forge = "decoy._deprecated:forge_shim"` entry in
  `pyproject.toml:153`. (This is an installed-script removal; acceptance phrases it as "the `forge` script is
  gone from the wheel / not installed," not a Typer "No such command.")

Exit codes: drop `EXIT_DEPRECATED_SHIM` (its only consumer is the forge shim). **Keep `EXIT_RUNTIME=3`,
`EXIT_FINDINGS=4`, `EXIT_CAPACITY=5` unchanged** — renumbering would break the public scriptable contract for
no gain. Code `2` becomes reserved/unused. Update every surface that names it: the `exit_codes.py` constant +
docstring + `__all__`, `tests/unit/test_exit_codes.py:31` (asserts `== 2`) and `:41` (lists it in `__all__`),
`src/decoy/cli/explain.py:416` (the `explain exit-codes` text), and the README exit-code table.

Dead-string sweep (F1 — the live surfaces that advertise the deleted command names; slice C's drift net does
NOT cover these, so they are explicit targets here):
- `src/decoy/ui/banner.py:51` — the `decoy info` splash prints `decoy storm scan data.csv` as the first-scan
  hint; repoint to `decoy storm analyze data.csv`.
- `src/decoy/cli/catalog.py:350` and `:352` — help/"See also" name `decoy storm scan`; repoint to analyze.
- `src/decoy/cli/demo.py:131` — comment referencing "the storm scan"; update wording.
- `src/decoy/ui/storm_animation.py:165-166` — docstring names both `storm scan` and `storm test`; update
  (keep the module — `scan` needs it in S3).
- Add a **grep gate** (a test, or a check in `test_surface_docs_consistency.py`) asserting the strings
  `storm scan` and `storm test` appear nowhere under `src/decoy/` (comments, help, epilogs, docstrings).

Observable: the three subcommands resolve to "No such command"; `forge` is not installed; `explain
exit-codes` + README show five live codes with `2` reserved; no source string names a deleted command; all
surviving commands behave exactly as before.
Failure modes to guard: deleting the shared storm animation module (needed by `scan` in S3) — delete only the
`storm test` *command*; a lingering `forge` entry in a built wheel; a missed dead-string (grep gate covers it).

### B. Flag + output normalization

- `--out` -> `--output/-o` at all **seven** definition sites (F3): `cli/init.py:407`, `cli/plan.py:95`
  (note: `plan` moves under `validate` in S2, but normalize now so the rename is one mechanical sweep),
  `cli/report.py:628` and `:1225`, `cli/storm.py:541` and `:1367`, `cli/subset.py:88`. Pre-GA hard rename,
  no alias. **In scope with the rename**: the ~20 help/epilog/`next_hint`/error-string references that name
  `--out` (e.g. `report.py:600/603/765/1191/1219-1220/1241/1349`, `init.py:39/42`, `storm.py:197/1492`,
  `subset.py:15/52/57/143/152/244/365`) — otherwise help advertises `--out` while the flag is `--output`.
  The grep gate (`--out` appears nowhere under `src/decoy/` as a flag string) catches misses.
- **`plan --json` rework DEFERRED to S2 (F2).** S2 deletes top-level `plan` (folds into `validate compile
  --explain`), so standing up a new envelope + `--format {yaml,json}` on `plan` now is throwaway churn and
  would contradict the "stable envelope" guarantee. In S1, `plan.py` gets ONLY the mechanical
  `--out`->`--output` rename; its `--json` keeps today's (non-standard) meaning until S2 designs the
  envelope once on `validate compile`.
- Shared options helper gives every command the `--json`/`--quiet,-q`/`--verbose,-v` trio with one
  definition; close the gaps where commands lack one (the envelope-only `schema`/`info`/`doctor` gain
  `--quiet`/`--verbose` where meaningful). `plan`'s trio is normalized in S2 alongside its envelope.
- Confirm/standardize the destructive-action vocabulary already present: `--force/-f`, `--dry-run/-n`,
  `--yes/-y`, `--no-input`; wire an overwrite confirmation where a command writes over an existing output
  (prompt unless `--force`/`--yes`; under `--no-input` fail with the flag to pass). Keep it minimal — only
  commands that already write outputs.

Observable: `decoy <cmd> --help` shows `--output/-o` everywhere and never `--out`; overwriting an existing
output prompts unless forced.
Failure modes: a missed `--out` call site or help string (grep gate); a command whose `--json` output shape
changes unintentionally (envelope snapshot tests).

### C. Anti-drift pipeline

The reference (`docs/cli-reference.md`) is already drift-protected by `tests/unit/test_cli_surface.py`. The
gap is the two **hand-written** surfaces: the README "Common commands" table (`README.md`) and the root-help
block (`_ROOT_HELP`, `__main__.py:57-81`). Add `tests/unit/test_surface_docs_consistency.py`:

- Assert every command named in `_ROOT_HELP` is a registered command (no phantom commands in help), and
  every registered top-level command is either in the root help or in an explicit, commented
  `_ROOT_HELP_OMITTED` allowlist (so omission is a deliberate, reviewed choice, not drift).
- Assert every command in the README "Common commands" table is registered, and flag a registered
  command missing from the table unless allowlisted.
- The test reads the live Typer command registry (same mechanism as `test_cli_surface.py`), so it cannot go
  stale against the code.
- F7: `_ROOT_HELP` lines are freeform examples carrying args/flags and **nested** sub-app paths
  (`storm analyze`, `validate config`, `templates list`, `report show`). The extractor must tokenize example
  lines and resolve nested command paths against the registry (sub-app + subcommand), not do flat
  set-membership. (Verified: post-S1 `_ROOT_HELP` names no deleted command — `profile`/`compile`/`project`/
  `catalog`/`jobs list` all survive S1 — so the test passes on the committed tree once written correctly.)

Observable: adding/removing a command without updating README + root help fails CI.
Failure modes: the allowlists becoming a dumping ground — keep them short and commented; review checks them.

## Verification (every slice)

- `tests/` targeted (the slice's new/changed tests) then full `pytest -q` (baseline: 1086 passed, 5 skipped).
- `ruff check src/decoy tests` (baseline clean).
- Regenerate `docs/cli-reference.md`
  (`python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md`) and confirm
  `test_cli_surface.py` green.
- Test-strength (testing.md) on changed units: assert the deletions resolve to non-zero + message, the
  rename shows in `--help`, the envelope shape holds, and the drift test fails on an injected phantom.
- README table + root help regenerated/consistency-checked green.

## Acceptance

- The three Typer subcommands resolve to "No such command"; the `forge` script is not installed (gone from
  the entry points); five live exit codes (2 reserved); `3/4/5` unchanged.
- No source string under `src/decoy/` names `storm scan` or `storm test` (grep gate).
- Every command (except `plan`, normalized in S2) has the uniform trio; `--output/-o` is the one spelling and
  `--out` appears nowhere; `plan.py` is renamed only (its `--json` meaning is unchanged until S2).
- The drift test fails on a phantom/undocumented command and passes on the committed tree.
- Full suite + ruff green; reference regenerated; no capability changed.

## Loop handoff

Stops at the plan-gate (independent review of this plan against the redesign/sprint docs + rulebooks)
before DEVELOP. On GO: build slices A->B->C TDD, each self-check + verify + independent review, then
DOCUMENT (reconcile this plan's status + the sprint doc). No merge to main.

## Build status (2026-10-23)

- **Slice A — DONE** (commit `fd9b377`): deletions + dead-string sweep + exit-code 2 reserved. Verified:
  suite 1082 pass/5 skip, ruff clean, drift sentry green, deletions confirmed via the live CLI.
- **Slice B1 (rename + trio) — DONE** (commit `5c7cb92`): `--out`->`--output/-o` at all 7 defs + every
  help string; `--json` added to `report render`/`report summarize`; `--out` grep gate. (`plan`'s trio is
  the one intentional gap, normalized in S2 with its envelope.) Verified: suite 1088 pass/5 skip, ruff clean.
- **Slice C (anti-drift) — DONE** (commit `5c7cb92`): `tests/unit/test_surface_docs_consistency.py` pins
  `_ROOT_HELP` + the README table to the live registry. Green.
- **Slice B2 (destructive-overwrite confirmation) — DEFERRED to an S1 follow-up.** It is the only
  behavior change in S1 and carries a real design decision that should be the owner's, not a unilateral
  autonomous call: **in a non-TTY / CI context, should an existing `--output` path be a hard failure
  (forcing `--force`) or a silent overwrite?** A hard failure regresses scripts that intentionally
  overwrite (the CLI is a CI front end); the CLIG-aligned alternative is "prompt only when interactive
  (TTY) + file exists + no `--force`; in non-TTY, overwrite as today." Recommendation: the CLIG-aligned
  TTY-only prompt + a `--force/-f` on the output-writing commands (subset/init/report render/storm
  analyze/storm integrity/fit/unmask/schema), no non-TTY behavior change. Held for owner confirmation of
  that semantics before building, so S1's shippable foundation (A+B1+C) is not blocked on it.

S1 is otherwise complete and shippable; `--force`/overwrite is additive and can land later without
reworking A/B1/C.

- **S1 independent review — ACCEPT-WITH-FOLLOWUPS**, remediated: the new `report render`/`report summarize`
  `--json` envelopes are now pinned by e2e tests (ok keys + the JSON error paths); the "shared options
  helper" design note was resolved to a recorded build decision (inline Typer declarations, semantics
  single-sourced in `setup_output`); the cosmetic `demo.py` leftover was reworded. Suite 1092 pass/5 skip,
  ruff clean, reference regen a no-op. **S1 CLOSED** (merge-ready on the branch; not merged — PO-gated).
