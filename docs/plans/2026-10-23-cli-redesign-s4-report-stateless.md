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
DuckDB catalog) — but pre-GA, local-only, no migration owed (hard delete). **Residual-risk note (#8):**
existing `.decoy/` dirs are left INERT on disk (not cleaned); a dev with past run history loses CLI access
to it; no recovery is owed (pre-GA hard-delete, consistent with both CLAUDE.md files).

Plan-gate review incorporated (GO-WITH-REVISIONS, 2026-10-23): P1 #1-#4 + P2 #5-#8 folded in. Headline
(#1): `report diff` and `report compare` are NOT one operation — `compare` is manifest/fingerprint-level
(pipeline + per-table input/output fingerprint add/remove/change + row-count deltas + warnings; manifest
dicts only, succeeds with output files gone) while `diff` is data-level (reads the CSV/Parquet, needs
pandas, FAILS on missing output files). The merged contract is pinned below as a lossless superset.

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
- Anti-drift (per-slice, #3/#4): in THIS slice prune `project`/`catalog`/`jobs` from
  `_README_TABLE_OMITTED` (`test_surface_docs_consistency.py` ~L57) and remove the `decoy project/catalog/
  jobs` lines from `_ROOT_HELP` (`__main__.py` ~L60-62), or the `stale = OMITTED - TOP_LEVEL` assertions
  (~L215-219,L258-262) fail. #4: MANUALLY reword the `_ROOT_HELP` `report show <run-id>`/`report diff
  <id-a> <id-b>` lines (`__main__.py` ~L63-64) and the README row to MANIFEST/path placeholders — the drift
  sentry does NOT catch stale placeholders (show/diff still resolve). Regen `docs/cli-reference.md`.
- Dead-string sweep + grep gate: `decoy project`, `decoy catalog`, `decoy jobs` appear nowhere under
  `src/decoy/`.
- Tests: `report show evidence.json` / `report diff a.json b.json` work from files; `run` writes the
  manifest with `--evidence-out` and creates NO `.decoy/` catalog (dir-snapshot assert); top-level
  `project`/`catalog`/`jobs` → "No such command". Retire `test_run_catalog_verbose.py`,
  `test_catalog_command.py`, `test_jobs_command.py`; REWRITE `test_jobs_report_show.py` +
  `test_report_diff_command.py` for file-first (the show/diff capability survives — don't just delete);
  port `test_report.py` show/diff run-id cases → paths.

### S4b — consolidate the post-run verbs under `report`
- `report show MANIFEST` absorbs `report summarize` + `evidence show`. #6: the merged card = the UNION of
  all three, not "the richest" — `evidence show`'s input/output fingerprint TABLES + strategies table +
  inline manifest_hash integrity status (`evidence.py:_render_manifest_card` ~511) PLUS the row_counts table
  that `summarize`/`show` render (`report.py:810`, `:1394`). Keep `--format`/`--output` where they existed.
- `report verify MANIFEST` ← `evidence verify` (fingerprint check). Delete the `evidence` sub-app. (`verify`
  and `integrity` do NOT collide: verify = manifest fingerprint-drift; integrity = post-mask residual-PII/FK/
  policy on masked + `--source`. Distinct inputs; both `EXIT_FINDINGS`.)
- `report fidelity SOURCE OUTPUT [...]` ← `validate distribution` (move the body + its 11 options verbatim);
  delete `validate distribution` + its registration (validate keeps config/compile/preflight). Its engine
  deps (`decoy_engine.quality`, `validate.py:658`) ship today → no engine-export gate for plain `fidelity`.
- `report integrity MASKED --source SRC [...]` ← `storm integrity` (move the body + its 7 options); the
  `storm` group disappears entirely. Keep `EXIT_FINDINGS`.
- **`report diff MANIFEST_A MANIFEST_B` — merged contract (#1), a lossless SUPERSET of today's `diff` +
  `compare`:** ALWAYS run the manifest/fingerprint-level comparison (`compare_manifests`: pipeline +
  per-table input/output fingerprint add/remove/change + row-count deltas + warnings added/removed) — this
  works even when output files are gone. ADDITIONALLY run the data-level comparison (`compare_data`, reads
  the CSV/Parquet the manifests reference) WHEN those output files exist; when they don't, print a note and
  report manifest-level only — do NOT fail (today's `diff` EXIT_USAGE-fails on missing files; that
  regression is removed). Keep the exported `compare_manifests`/`compare_data` engine helpers. Exit:
  manifest-level or data-level differences → the drift/findings code `compare` already uses; a missing output
  file is a note, not a failure (add an opt-in `--require-data` to hard-fail if a scripted caller wants
  today's strict behavior). Delete `report compare` (folded in).
- `report vault VAULT --config CONFIG` ← `vault info` (D5); delete the `vault` sub-app.
- **#7 JSON `command` labels:** update each relocated/merged body's hard-coded `command` field to its new
  path — `vault.py` `"vault-info"` → `"report vault"`; `storm.py` `"storm integrity"` → `"report
  integrity"`; validate distribution `"validate distribution"` → `"report fidelity"`; the show/summarize/
  evidence-show envelopes → `"report show"`; `report.py` must add `EXIT_FINDINGS` to its imports. Port the
  tests that assert these labels.
- Anti-drift (#2/#3): in THIS slice prune `vault`/`evidence`/`storm` from `_ROOT_HELP_OMITTED` and
  `_README_TABLE_OMITTED`; and UPDATE the `test_surface_docs_consistency.py` self-check that hard-codes
  `storm integrity` as a live nested path (~L188-189) to a surviving path (e.g. `report integrity`). Keep
  `report` in the README allowlist (still registered). Update `_ROOT_HELP`/README; regen `docs/cli-reference.md`.
- Dead-string REWORD (#5 — reword, don't just delete, or content is lost): `explain.py:404` + `README.md:126`
  + `exit_codes.py:20,66` (`decoy storm integrity` EXIT_FINDINGS exemplar → `report integrity`);
  `preflight.py:105` + `run.py` `--evidence-out` help (`decoy evidence verify` → `report verify`);
  `validate.py:1003` docstring (drop `distribution` from the subcommand list); `report.py` in-code hints
  (~L820, L1404, see-also epilogs L615/726/852: `decoy evidence show` → `report show`/`report verify`).
  Grep gate for `decoy evidence`, `decoy vault`, `storm integrity`, `validate distribution`.
- Tests: each `report {show,render,verify,fidelity,integrity,diff,vault}` runs with today's semantics (port
  `test_evidence.py`→report verify/show, `test_validate_distribution.py`→report fidelity, the vault + storm
  integrity tests→report vault/integrity); `report diff` on manifests with MISSING output files succeeds
  manifest-only (note, not fail) and with files present also does data-level; `--require-data` hard-fails on
  missing; the old homes (`evidence`, `vault`, `storm`, `validate distribution`, `report compare`) → "No
  such command".

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
  `vault`, `storm`, `project`, `catalog`, `jobs` sub-apps, `validate distribution`, and `report compare`
  are gone.
- `report diff` is a lossless superset (manifest-level always + data-level when files present; missing
  output files are a note, not a failure; `--require-data` for strict); `report show` is the union card
  (fingerprint tables + strategies + manifest_hash + row_counts); relocated verbs carry new JSON `command`
  labels.
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