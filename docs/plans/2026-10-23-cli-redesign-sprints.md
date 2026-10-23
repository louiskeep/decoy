# Decoy CLI redesign — sprint plan

Status: build roadmap, PRE-RELEASE (2026-10-23). Sequences the CLI command-surface redesign settled in
`docs/plans/2026-10-23-cli-interface-redesign.md` (decisions D1-D6 locked to the recommended option) into
shippable sprints. Each sprint is one or more build slices; each slice gets its own build plan and the
standard gate chain (Codex plan-gate -> Sonnet build -> dennis -> Codex final) before any merge to main.

Scope: CLI surface only. Breaking, pre-GA hard delete (no shims). Two engine exports are called out as
their own additive engine slices; the rest is pure CLI-side.

Rules consulted: 00-universal, development-loop, documentation, scope-discipline, api-and-compatibility.

Locked decisions (from the redesign §10): **D1** one `run`, mode inferred · **D2** `scan` (STORM stays the
engine profiler + animation) · **D3** drop `project`/`catalog`/`jobs`, CLI stateless, `report` file-first ·
**D4** hard-delete `forge` shim + exit code 2 · **D5** `vault info` -> `report vault` · **D6** disguises in
the first cut; `query`/`run --pin` fast-follow; `report fidelity --privacy` gated on an engine export.

---

## Sprint sequence at a glance

| Sprint | Theme | Leaves the CLI at... | Depends on |
|--------|-------|----------------------|------------|
| S1 ✅ | Foundations: conventions, deletions, anti-drift | smaller, uniform surface; same capabilities | — |
| S2 ✅ | Pre-run gate: `validate` | one pre-run gate; `plan`/`compile`/`preflight` folded in | S1 |
| S3 ✅ | Inspection: `scan` + `list`/`show` | one "look at my data" verb; one reference vocabulary | S1 |
| S4 ✅ | Post-run: `report` + stateless | one post-run noun; `project`/`catalog`/`jobs` gone | S1, S2, S3 |
| S5 ◑ | `run` flags shipped; disguises end-to-end owner-gated | run flags done; compliance wiring escalated | S2, S3 |
| S6 | Delight / fast-follows: `query`, privacy metrics | optional capabilities surfaced | S4; engine exports |

Runs in parallel, independently: the **file-format contract** slice
(`docs/plans/2026-09-30-cli-source-format-dispatch.md`) — it is engine-release-gated and touches the source
reader, not the command tree, so it does not block or get blocked by this sequence.

Cross-cutting, every sprint (the development-loop discipline):
- TDD per task; regenerate `docs/cli-reference.md` (the drift sentry) and keep `tests/unit/test_cli_surface.py`
  green; `pytest -q` + `ruff check src/decoy tests` before each commit.
- Each sprint ends **shippable**: a coherent surface, the regenerated reference, and the README "Common
  commands" table + root-help block regenerated from it (never hand-edited after S1).
- Output discipline preserved (stdout=data, stderr=messaging, `NO_COLOR`/TTY, the six-code exit contract).

---

## S1 — Foundations: conventions, deletions, anti-drift

Goal: shrink and standardize the surface **without** restructuring any capability, so later sprints move a
clean, uniform base. Lowest risk, highest churn-reduction — do it first.

Slices:
1. **Shared options + uniform output trio.** One options helper so every command has identical
   `--json` (stable machine envelope) / `--quiet,-q` / `--verbose,-v`. Fix `plan`'s off-meaning `--json`
   (envelope, not a YAML/JSON toggle; move the format choice to `--format`). Remove the `plan`-only gap and
   the `schema`/`info`/`doctor` partial coverage.
2. **One flag vocabulary.** Hard-rename `--out` -> `--output,-o` everywhere (pre-GA, no alias). Confirm
   `--force,-f`, `--dry-run,-n`, `--yes,-y`, `--no-input` spellings and wire the destructive-overwrite
   confirmation (output/vault overwrite prompts unless `--force`/`--yes`; `--no-input` fails with the flag
   to pass instead).
3. **Deletions (D4 + vestigial).** Remove `storm test` (animation demo), the deprecated `storm scan` alias,
   `jobs watch`, and the `forge` shim + `EXIT_DEPRECATED_SHIM` (exit code 2). Update the exit-code table,
   `explain exit-codes`, and `cli/exit_codes.py` to the five live codes (0/1/3/4/5).
4. **Anti-drift pipeline.** Generate the README "Common commands" table and the `__main__.py` root-help
   block from `docs/cli-reference.md`, and add a drift-sentry test that fails if the three surfaces diverge.
   This is the fix for the "three disagreeing command lists" finding and the guardrail for every later sprint.

Acceptance: every command carries the uniform trio with identical semantics; `--output` is the one spelling;
no flag has two meanings; the four deletions resolve to "No such command"; the exit contract is five codes;
README + root help are provably generated from the reference.

## S2 — Pre-run gate: `validate`

Goal: one pre-run gate; kill the four-door "compile a plan" redundancy.

Slices:
1. **Adopt the validate-consolidation writeup** (`docs/plans/2026-10-23-validate-consolidation-writeup.md`)
   verbatim: `validate CONFIG` runs the whole gate (config + compile + preflight, deduped to one shared
   config-layer); `validate config|compile|preflight` run one layer each; `validate compile --explain` is
   the plan-explanation path. Aggregated exit-code precedence per that writeup.
2. **Delete the top-level `plan`, `compile`, `preflight`** (folded in; resolves `plan` vs `compile`).
3. **Hold `validate distribution` in place but out of the default** (writeup already excludes it) — it
   relocates to `report fidelity` in S4. Leave a one-line "moving to `report fidelity`" note in its help.

Acceptance: the writeup's acceptance sketch, plus `plan`/`compile`/`preflight` no longer resolve and the
shared config-only checks run exactly once.

Depends on: S1 (conventions). Pairs with the file-format contract slice but does not depend on it.

## S3 — Inspection: `scan` + `list`/`show`

Goal: one "look at my data" verb (D2) and one reference vocabulary.

Slices:
1. **`scan SOURCE`** merges `profile` + `storm analyze` into one profiling command (stats + PII detectors +
   re-id risk), `--output scan.json` to persist. Saved-scan ops become subcommands: `scan show SCAN FIELD`,
   `scan diff OLD NEW`. The STORM rain/lightning animation moves under `scan` unchanged. Delete `profile`
   and the `storm` sub-app shell. `storm integrity` is **not** deleted here — it is post-run verification
   and relocates to `report integrity` in S4; keep it reachable until then.
2. **`list KIND` + `show KIND NAME`** fold the four registry sub-apps (`strategies`, `providers`,
   `checksums`, `validators`), `templates list/show`, and `schema` into one verb pair. `KIND` ∈
   {strategies, providers, detectors, validators, checksums, templates, disguises}. Adds two new kinds:
   `detectors` (the 25 STORM detectors) and `disguises` (the 10 compliance bundles). `show schema` is the
   grouped form; keep top-level `schema` as a thin alias for CI muscle memory.

Engine dependency: listing `disguises` reads `load_disguises`, which is not in `decoy_engine.__all__` today
(it is in `disguises/`). Needs a small additive engine export (its own engine slice, gate chain on the
engine side) before S3's disguise-listing task — or S3 ships without `disguises`/`detectors` and they land
with S5. (Recommendation: do the engine export first so S3 ships `list` complete.)

Acceptance: `profile`/`storm analyze` gone, replaced by `scan`; one `list`/`show` vocabulary covers all
seven kinds (or five, if the engine export slips to S5); `inspect` no longer exists as a second verb.

Depends on: S1.

## S4 — Post-run: `report` consolidation + stateless CLI (D3)

Goal: one post-run noun; drop the platform-mirror local state.

Slices:
1. **`report {show, render, verify, fidelity, integrity, diff}`** collapses `evidence show/verify`,
   `report render/summarize/compare/show/diff`, the relocated `validate distribution` (-> `report
   fidelity`), and `storm integrity` (-> `report integrity`). `report integrity` runs the job-level
   validators (D6: validators surfaced here and via `list validators`).
2. **Stateless (D3).** Delete `project`, `catalog`, `jobs`. Make `report` **file-first**: it operates on
   evidence manifests and output files on disk (paths), not a DuckDB run catalog. Remove `run`'s
   auto-record-to-catalog (`run.py` `_record_run_to_catalog`) and the `.decoy/` workspace machinery.
   `report show`/`diff` take manifest/output paths, not run-ids. Remove the "LOCAL ONLY / does not sync"
   disclaimers with the commands that carried them.
3. **`vault info` -> `report vault`** (D5); drop the standalone `vault` noun.

Engine dependency: `report fidelity --privacy` (DCR / synth-attack metrics) needs the engine `quality`
compute surface exported from `decoy_engine.__all__` (today lazy/private). That `--privacy` task is gated on
that engine slice; plain `report fidelity` (distribution grade, already reachable via `validate
distribution`/`run --fidelity`) ships in S4 regardless.

Acceptance: every post-run operation resolves under `report`; no `evidence`/`project`/`catalog`/`jobs`/
`vault` nouns remain; `run` writes no catalog and needs no workspace; reports read paths; `report integrity`
runs validators.

Depends on: S1, S2 (distribution relocation handoff), S3.

## S5 — Compliance story: disguises end-to-end + `run` flags

Goal: make the headline latent capability (D6, first cut) real.

Slices:
1. **Disguises in `init`.** `init --preset {minimal,hipaa,pci,gdpr,glba,ccpa,ferpa,sox,cpni,pc}` maps each
   preset to its disguise bundle (extend today's four presets to the full ten). `scan --suggest` reads the
   detector hits and emits a starter config pre-wired to the matching disguise rules — turning `scan` from
   "here is your PII" into "here is a compliant config."
2. **`run` capability flags.** Surface the engine `run_pipeline` kwargs cleanly as flags: `--explain-plan`,
   `--fidelity`, and `--pin` (pinned-generation byte-reproducibility, D6). Keep routing knobs
   (`--chunked`/`--substrate`) as-is; do not reimplement routing.

Acceptance: a `scan --suggest` + `init --preset hipaa` flow produces a runnable, HIPAA-disguised config;
`run --pin` emits the reproducibility fingerprint; `run --explain-plan`/`--fidelity` work.

Depends on: S2 (`run`), S3 (`scan`, `list disguises`), the `load_disguises` engine export.

## S6 — Delight / fast-follows (optional)

Goal: surface the remaining latent capability once the core surface is stable.

Slices:
1. **`decoy query OUTPUT "SELECT ..."`** — read-only discovery SQL over masked Parquet output
   (`run_discovery_sql`, already public; SELECT/WITH/VALUES/TABLE only, in-memory DuckDB).
2. **`report fidelity --privacy`** — DCR / new-row-synthesis attack metrics; lands with the engine
   `quality` export slice.
3. **`fit` polish** — keep as the generation-prep verb; tighten help to state its relationship to `run`
   generate mode and the DP-budget knobs. No behavior change.

Depends on: S4; the engine `quality` export (for task 2).

---

## Engine-side slices this depends on (additive, on the engine's own gate chain)

1. **Export `load_disguises`** from `decoy_engine.__all__` — unblocks `list disguises` (S3) and the preset
   mapping (S5). Smallest honest surface; alternative is a `list_disguises()` thin wrapper.
2. **Export the `quality` compute surface** (`compute_quality_report`/`score_to_grade`/`compute_dcr`/synth
   metrics) — unblocks `report fidelity --privacy` (S6). Larger; sequence after the core redesign.

Both are additive engine changes (no behavior change), each on a branch off engine `main` through the
engine's Codex/dennis gate, shipped in an engine release the CLI's `pyproject.toml` minimum then targets.

## ROADMAP indexing

The cross-repo `decoy-platform/docs/ROADMAP.md` is the single what-to-do-next index and should carry one
entry for this redesign, linking here and to the per-sprint build plans as they are authored. Adding that
entry is a `decoy-platform` change (its own small docs commit); flagged, not done here, to keep this a
CLI-repo-only change.
