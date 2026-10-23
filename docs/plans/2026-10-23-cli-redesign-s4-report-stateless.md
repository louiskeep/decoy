# S4 build plan — `report` consolidation + stateless CLI (D3)

Status: build plan, PRE-RELEASE (2026-10-23). Fourth (largest) sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Breaking, pre-GA hard delete. Awaiting plan-gate review.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, documentation,
reuse-first, scope-discipline, architecture, data-and-migrations, testing.

Established solutions: n/a — command-tree reshaping + removing a persistence subsystem; no new domain
primitive. Relocations reuse the existing command bodies (as S2's `plan`/`compile`/`preflight` re-parent did).

Risk: R2. Breaking surface + a structural change (remove the local persistence subsystem; change two
commands' argument contract from run-id to file path). No engine behavior change; feature-branch; no merge to
main; no R3 side effect. `data-and-migrations` consulted because D3 removes a persisted store (`.decoy/`
DuckDB catalog) — but pre-GA, local-only, no migration owed (hard delete).

## Guarantee

One post-run noun, and a stateless CLI:
- `decoy report {show, render, verify, fidelity, integrity, diff, vault}` — everything about judging/handling
  a run's output, operating on files (evidence manifests + output data), never a run catalog.
- `decoy run` writes evidence only to `--evidence-out`; it records nothing to a `.decoy/` catalog.
- `project`, `catalog`, `jobs` (the platform-mirror local-state subsystem) are GONE.
- `validate distribution` relocates to `report fidelity` (validate is now purely pre-run). `storm integrity`
  relocates to `report integrity` (the `storm` group disappears). `vault info` → `report vault` (D5).

Non-goals / deferred: `report fidelity --privacy` (DCR / synth-attack metrics) stays S6 (needs the engine
`quality` export); plain `report fidelity` (distribution grade, today's `validate distribution`) ships here.
No `--force`/overwrite work (S1 B2 follow-up). `list detectors` is still S5.

## What's already file-first (no change needed)

`report render` (`report.py:_render`), `report summarize` (`_summarize`), `report compare` (`_compare`), and
`evidence show`/`verify` all already take evidence-manifest FILE paths. Only `report show` (`_show`,
`report.py:1250`) and `report diff` (`_diff`, `:1444`) resolve run-ids from the DuckDB catalog (via
`catalog._catalog_db`/`_require_workspace` + `jobs._lookup_run`). `run._record_run_to_catalog`
(`run.py:1291-1374`, called ~`:937`) is the only writer.

## Slices

### S4a — stateless (D3): drop the catalog subsystem, make `report show`/`diff` file-first
- Delete the `project`, `catalog`, `jobs` sub-apps (modules `cli/project.py`, `cli/catalog.py`,
  `cli/jobs.py`) and their registrations/imports/epilogs in `__main__.py`.
- `run.py`: remove `_record_run_to_catalog` (`:1291-1374`) and its call site (~`:934-943`); `run` keeps
  writing the manifest to `--evidence-out` exactly as today, just no catalog write. Remove the now-unused
  `catalog`/`project` imports. Confirm no other run behavior depends on the workspace.
- `report show RUN` → `report show MANIFEST` (an evidence-manifest file path); drop the
  `catalog`/`jobs`/`workspace` resolution (`report.py:1287-1295`) and read the manifest directly (reuse the
  `_load_manifest` helper that `render`/`summarize` use). `report diff A B` → `report diff MANIFEST_A
  MANIFEST_B` likewise (`:1474-1480`). These are breaking arg-contract changes (run-id → path), acceptable
  pre-GA.
- Remove the "LOCAL ONLY / DuckDB catalog / `decoy project init`" disclaimers that moved with these commands.
- Dead-string sweep + grep gate: `decoy project`, `decoy catalog`, `decoy jobs` appear nowhere under
  `src/decoy/`; prune them from the `test_surface_docs_consistency.py` allowlists and `_ROOT_HELP`/README;
  regen `docs/cli-reference.md` (S4a green on its own).
- Tests: `report show evidence.json` / `report diff a.json b.json` work from files; `run` writes the
  manifest with `--evidence-out` and creates NO `.decoy/` catalog (dir-snapshot assert); top-level
  `project`/`catalog`/`jobs` → "No such command"; port/retire the catalog/jobs/project test files.

### S4b — consolidate the post-run verbs under `report`
- `report show` ALSO absorbs `report summarize` + `evidence show` (all "human summary of a manifest" — dedupe
  to one `report show MANIFEST`, keeping the richest output; `--format`/`--output` where they existed).
- `report verify MANIFEST` ← `evidence verify` (fingerprint check). Delete the `evidence` sub-app.
- `report fidelity SOURCE OUTPUT [...]` ← `validate distribution` (move the whole command body + its options
  verbatim); delete `validate distribution` and its registration (validate keeps config/compile/preflight).
- `report integrity MASKED --source SRC [...]` ← `storm integrity` (move the body); the `storm` group
  disappears entirely (its only remaining command). Keep `EXIT_FINDINGS` semantics.
- `report diff` ALSO absorbs `report compare` (both compare two manifests/outputs — dedupe; keep the
  data-level compare and the manifest compare as one `report diff` with the inputs it needs, or two clearly
  named inputs — settle in build).
- `report vault VAULT --config CONFIG` ← `vault info` (D5); delete the `vault` sub-app.
- Anti-drift: update the allowlists/`_ROOT_HELP`/README for the removed `evidence`/`vault`/`storm`/`validate
  distribution` names and the enriched `report`; regen reference; dead-string sweep + grep gate for `decoy
  evidence`, `decoy vault`, `storm integrity`, `validate distribution`.
- Tests: each `report {show,render,verify,fidelity,integrity,diff,vault}` subcommand runs its function with
  today's semantics (port the evidence/vault/distribution/integrity tests to the new paths); the old homes
  (`evidence`, `vault`, `storm`, `validate distribution`) → "No such command"; `validate` no longer has a
  `distribution` subcommand.

## Design notes

House style on touched code. No new abstraction — `report` subcommands reuse the existing command bodies
(moved/registered under `report_app`), dispatch stays per-command. The one structural change is a DELETION
(the catalog/workspace persistence subsystem); its removal simplifies `run` (one fewer side effect, more
idempotent — clig "make external actions explicit": `run` no longer silently writes a catalog). `report`
reads only the files it is given.

## Verification

Full `pytest -q` green; `ruff check`; regen `docs/cli-reference.md` + the three doc sentries green;
test-strength on the file-first `report show`/`diff` and the relocated commands. A real end-to-end check:
`run --evidence-out ev.json` then `report show ev.json` / `report verify ev.json` on the produced manifest.

## Acceptance

- `report {show,render,verify,fidelity,integrity,diff,vault}` is the single post-run surface; `evidence`,
  `vault`, `storm`, `project`, `catalog`, `jobs` sub-apps and `validate distribution` are gone.
- The CLI is stateless: `run` writes no catalog/`.decoy/`; `report show`/`diff` read manifest/file paths.
- `validate` is purely pre-run (no `distribution`); `EXIT_FINDINGS`/`EXIT_CAPACITY` semantics preserved
  where they lived (integrity findings, etc.).
- No source string names a removed command; all three doc sentries green; full suite + ruff green; no engine
  change.

## Loop handoff

Plan-gate review before DEVELOP (confirm: the file-first arg-contract break on `report show`/`diff`; the
`report show`+`summarize`+`evidence show` dedupe; the `report diff`+`compare` dedupe; that removing the
catalog breaks no run behavior; whether any `report` consumer truly needs run-id resolution). On GO: build
S4a (stateless) then S4b (consolidate), each self-check + verify, then one independent review of the S4 diff,
then DOCUMENT. No merge to main.