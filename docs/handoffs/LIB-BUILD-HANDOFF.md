# LIB build: the local record library, CLI slices L1b to L5b (roadmap rows 34 to 42)

Repo `louiskeep/decoy` (the CLI). Plan: `docs/plans/2026-11-05-local-record-library.md` on branch `plan/local-record-library` (plan passed Dennis and Codex 2026-11-06, revision 7). The engine half is done: L0.1, L0.2 and L1a (`decoy_engine.records`, the `decoy-record/v1` envelope, kind registry, value-free codec, registry 1.20.0) are in engine 0.20.0, which the CLI already pins. L1b.1 (shared atomic writer, CLI #85) is merged. Status: handoff. You build and test on your own nodes. You do not review your own work and you do not merge.

## Step 0: re-FRAME against current main (before any code)

The plan was written on 2026-11-05/06. Since then CLI `main` changed in ways the plan does not know:

- PROJECT-LAYOUT (row 24t, owner 2026-11-09): every file a pipeline writes lands under the project, `out/<pipeline>/<run-id>/`; a project is found by its marker; `.decoy/` is the project's private folder. The P3 slice (project-relative evidence manifests) is in review as CLI PR #200; its plan is `docs/plans/2026-11-09-project-layout.md` on branch `plan/project-layout`.
- `decoy run` was split into the `src/decoy/cli/run/` package.
- The flat `src/decoy/cli/` package is FROZEN: no new top-level modules there. New code goes in a subpackage (for example `src/decoy/cli/library/`).
- LAYOUT: `.importlinter` layer contract and an import-layer test (`tests/sentry/layout/`, run only through `scripts/dev/gates.sh --steps layers`), a file-size ratchet (files about 800 lines at most), and package fan-out guards.

Write `docs/records/lib-reframe-<date>.md` on your first branch: for each slice you will build, the plan's file placement mapped to where it must go on current main, every plan assumption that no longer holds (paths, module names, library root vs the project layout's `.decoy/`, how `decoy run` hands off results), and whether the change is placement only or alters a guarantee. Placement-only changes: proceed. Anything that changes a guarantee, a record format, the library root or a CLI surface in plan 4.15: stop and report before building. Push that record and report.

## Slice chain

Build in this order. Branch names are suggestions; one PR per slice part.

| # | Slice (plan section) | Roadmap row | Ready now? |
|---|---|---|---|
| 1 | L1b.2, L1b.3: store and refs on the merged atomic writer (L1b-cli) | 34 | yes |
| 2 | L1c.1, L1c.2: index, freshness, degraded mode, fsck (L1c-cli) | 35 | after 1 |
| 3 | L1d: library scratch through the engine allocator (L1d-cli) | 34 | after 2 |
| 4 | L4a: read commands and refs (`list`, `show`, `diff`, `ref`, `export` read side) (L4a-cli) | 39 | after 2; run-result `diff` waits for L3a |
| 5 | L5a: wire the engine `ProgressSink` into `decoy run` (L5a-cli) | 41 | after 2 |
| 6 | L4b: prune, export, clean (L4b-cli) | 40 | after 4 |
| 7 | L3a: evidence and run-result records (L3a-cli) | 37 | ONLY after CLI #200 (P3) is merged to main, and the run-result half only after RESULT (row 62) lands. Ask before starting. |
| 8 | L5b: job logs for `decoy run` (L5b-cli) | 42 | after 5 and 7 |
| 9 | L3b: sample-run records (L3b-cli) | 38 | waits for SAMPLE (row 63); skip unless told it landed |
| 10 | L2: scan records (L2-cli) | 36 | waits for SCAN-MULTI S1c (row 27); skip unless told it landed |
| - | L5c: job logs for multi-table scan | - | out of scope here |

Stacking: slice 1 branches from `main`; each later slice branches from the slice it depends on, and its PR's base is that branch. If `main` moves, merge `origin/main` into your branch. Never rebase a pushed branch, never force-push. If a slice in the chain is blocked, skip to the next one that is ready and say so.

You may take the whole chain. Stop and report when: the re-FRAME finds a guarantee change; the plan is wrong or silent on something that changes a guarantee; a defect of a class the plan already closes appears again; a size or census number would have to rise; or a test needs weakening to pass.

## Per slice: done when

1. First commit = the slice's red-first tests from the plan (its acceptance tests and hostile cases), recorded red on the slice start commit with the reason. Every generated test carries a non-vacuity assertion (the case really reaches the code it claims).
2. Then the production change, placed per your re-FRAME record. One central mechanism per concern: the store, the atomic writer, the index and the id rule each exist once (plan 3.1, LM4). Never a second copy.
3. Each mutation the plan names for the slice applied once, its test shown red, then reverted.
4. Docs the plan names for the slice updated; `CHANGELOG.md` per the repo's current convention.
5. Checks green on the exact head, on your own nodes:
   ```
   uv sync --frozen --extra dev
   uv run pytest <the slice's test paths> tests/sentry -q -p no:cacheprovider
   uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src/decoy
   bash scripts/dev/gates.sh --steps layers
   ```
   plus the impact-selected tests for the change (`scripts/dev/gates.sh --keep-going --baseline` if present on main). OS lanes per plan 5.1: Linux always; macOS and Windows where the plan's lane table says yes. If you have no Windows node, say so in the evidence and mark the Windows lane NOT RUN; do not claim it. Record OS, `python -V`, the engine version and both failure sets (branch and main) in `docs/records/lib-<slice>-evidence.md`. State what you did not run. No full suite per slice; the orchestrator runs it before merge.
6. Push, open the PR (title = the slice's commit subject; body: what it does, red-first and mutation evidence, OS lanes run, the final line `cam`). Report the PR number and head, then start the next ready slice.

## Rules

- V1 bar: only a function break, data loss or a real value/secret reaching a non-admin blocks V1. Anything else you notice goes in the evidence file as V2-LOG; do not build it.
- Records are value-free by construction (plan 4.6): names, counts, digests and codes only. No data values or expression text in records, logs or error messages.
- Fix the class, not only the instance. Never widen a threshold, raise a ratchet, census or pin, skip a test, or weaken an assertion to make a change pass.
- No new module in the flat `src/decoy/cli/`. Files about 800 lines at most.
- Commits: Conventional Commits subject, at most 72 characters, imperative, no body unless it explains why, final line `cam`. No file lists, test counts or tool trailers.
- No edits to `main` or to any branch you did not create. Do not touch `feat/project-layout-*`, `plan/*` or `feat/v1plus-*` branches.
- Do not review your own work. Codex reviews each PR on the orchestrator side; fix what it returns on the same branch.
- Worker standards and defect catalog: `docs/handoffs/WORKER-STANDARDS.md` and `docs/handoffs/DEFECT-CATALOG.md` on decoy-platform branch `handoffs/queue` if you can read them; the rules above are the binding minimum.

## Report per slice

PR number, head SHA, red-first summary, mutations run, checks and OS lanes run, anything not run, V2-LOG items, and any stop condition hit.

cam
