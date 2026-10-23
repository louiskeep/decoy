# S1 build plan — Foundations: conventions, deletions, anti-drift

Status: build plan, PRE-RELEASE (2026-10-23). First sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`; surface in
`docs/plans/2026-10-23-cli-interface-redesign.md`, decisions D1-D6 locked). Breaking, pre-GA hard delete.
Awaiting plan-gate review before DEVELOP.

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

House style applies to touched code only. One new structure: a shared CLI-options helper so the output trio
is defined in **one place** rather than restated per command (one place per fact; single-purpose). It wraps
the existing `decoy.ui.output.setup_output` / `OutputMode`; it does not introduce a flag argument that
switches behavior. No other new abstraction.

## Slices (recoverable; each its own commit, each green before the next)

### A. Deletions (D4 + vestigial)

Targets (verified): `storm test` (`cli/storm.py:1249`), `storm scan` deprecated alias (`cli/storm.py:1328`,
registered `__main__.py` storm sub-app), `jobs watch` (`cli/jobs.py:329`), the `forge` shim
(`src/decoy/_deprecated.py`) + its `forge = ...` console script in `pyproject.toml`.

- Remove the four commands/functions and their registrations; remove tests that pin them as existing, add
  tests asserting each now resolves to Typer "No such command" (non-zero exit).
- Exit codes: drop `EXIT_DEPRECATED_SHIM` (the only consumer is the forge shim). **Keep `EXIT_RUNTIME=3`,
  `EXIT_FINDINGS=4`, `EXIT_CAPACITY=5` unchanged** — renumbering would break the public scriptable contract
  for no gain. Code `2` becomes reserved/unused; note it in the exit-code docstring, the README table, and
  `explain exit-codes`.
- `cli/storm.py`'s `storm_animation.py` docstring referencing the old `decoy storm scan` name is corrected.

Observable: the four commands are gone; `decoy explain exit-codes` and the README show five live codes with
`2` marked reserved; all other commands behave exactly as before.
Failure modes to guard: accidentally deleting the shared storm animation (needed by `scan` in S3) — delete
only the `storm test` *command*, not the animation module; a lingering `forge` entry point in a built wheel.

### B. Flag + output normalization

- `--out` -> `--output/-o` at all six call sites: `cli/init.py:407`, `cli/plan.py:95` (note: `plan` moves
  under `validate` in S2, but normalize now so the rename is one mechanical sweep), `cli/report.py:628` and
  `:1225`, `cli/storm.py:541` and `:1367`, `cli/subset.py:88`. Pre-GA hard rename, no alias.
- Fix `plan`'s overloaded `--json` (`cli/plan.py:88-91`): `--json` becomes the standard machine-envelope
  flag (consistent with every other command); the YAML-vs-JSON *artifact format* choice moves to a separate
  `--format {yaml,json}` option. (If plan-gate review prefers, this can instead be deferred to S2 where
  `plan` is folded into `validate compile`; default: fix the flag meaning now, carry it into S2.)
- Shared options helper gives every command the `--json`/`--quiet,-q`/`--verbose,-v` trio with one
  definition; close the gaps where commands lack one (`plan`, and the envelope-only `schema`/`info`/`doctor`
  gain `--quiet`/`--verbose` where meaningful).
- Confirm/standardize the destructive-action vocabulary already present: `--force/-f`, `--dry-run/-n`,
  `--yes/-y`, `--no-input`; wire an overwrite confirmation where a command writes over an existing output
  (prompt unless `--force`/`--yes`; under `--no-input` fail with the flag to pass). Keep it minimal — only
  commands that already write outputs.

Observable: `decoy <cmd> --help` shows `--output/-o` everywhere; `plan --json` emits an envelope;
overwriting an existing output prompts unless forced.
Failure modes: a missed `--out` call site (grep gate); a command whose `--json` output shape changes
unintentionally (envelope snapshot tests).

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

- The four targets resolve to "No such command"; five live exit codes (2 reserved); `3/4/5` unchanged.
- Every command has the uniform trio; `--output/-o` is the one spelling; `plan --json` is an envelope.
- The drift test fails on a phantom/undocumented command and passes on the committed tree.
- Full suite + ruff green; reference regenerated; no capability changed.

## Loop handoff

Stops at the plan-gate (independent review of this plan against the redesign/sprint docs + rulebooks)
before DEVELOP. On GO: build slices A->B->C TDD, each self-check + verify + independent review, then
DOCUMENT (reconcile this plan's status + the sprint doc). No merge to main.
