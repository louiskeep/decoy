# Parity C1: CLI P0 fixes before the R1 cut

Status: plan, PRE-RELEASE (2026-10-24). Folds into roadmap B-1 (CLI redesign adoption). Part of the parity
program (`decoy-platform/docs/plans/2026-10-24-cli-platform-parity-program.md`); source: parity audit §10
items 1 to 5, §4 rows "Fixed-width output", "Validators + quarantine", "Native kernels".

Rules consulted: 00-universal, development-loop, risk-and-exceptions, bugfix, api-and-compatibility,
scope-discipline, testing, documentation; CLI `CLAUDE.md` (thin wrapper; data behaviour in the engine;
pre-GA hard delete).

Risk: R1 (bounded CLI changes over existing engine capability; two of the items are defect fixes). The
`--threads` flag is additive.

## 1. Guarantee and non-goals

Guarantee: a `format: fixed_width` target is written as fixed-width or refused, never silently as CSV;
quarantined rows and validator findings are reported to the user and in `--json`; a user with the native
companion can use more than one thread; the README and `explain` text describe the shipped surface.

Non-goals: cloud I/O (C2), the dispatcher and lazy sources (C3), monitoring (C4), new strategies.

## 2. Items

### C1a fixed-width output (defect)
- Today `cli/run.py::_write_mask_outputs` dispatches on path suffix only: `.parquet` else `to_csv`
  (`run.py:1555-1567`). A `targets[t].format: fixed_width` with a `layout` is written as CSV.
- Fix: dispatch on `effective_target_format(descriptor)` (engine, after E2b; until then the CLI reads
  `format`/`layout` itself), call the engine `write_fixed_width` for fixed-width, keep suffix fallback for
  csv/parquet. Refuse `fixed_width` without `layout` at `validate` with a coded message.
- Tests: e2e round trip `read_fixed_width -> run -> write_fixed_width -> read_fixed_width` equality; a
  fixed-width target in `--chunked` stays refused (existing behaviour) with the same code.

### C1b validator and quarantine surfacing (defect: silent row removal)
- The engine runs `validators:`/`quarantine:` inside `run_pipeline` and reports `quality_metrics["validation"]`,
  `["quarantine"]`, `["row_errors"]`, `["row_error_summary"]` (`_pipeline_finalize.py:408-479`); the CLI reads
  only `failed_checks`, `quality_summary`, `execution_plan`, `fidelity_reports` (`run.py:1114-1123`).
- Fix: after a successful run, render a "Data checks" card: validators run / passed / failed, quarantine
  path and row count per table, row-error summary; include the same under `report.data_checks` in the
  `--json` envelope. Exit code unchanged (quarantine is a configured success); `--post-validate-enforce`
  semantics unchanged.
- Tests: e2e with a `quarantine:` config asserting the card names the JSONL path and count, and that the
  JSON envelope carries them; sentry that no quarantined value appears in any output stream.

### C1c `--threads N`
- `run_pipeline(native_threads=)` exists (default 1, range 1..1024); the platform grants up to 4 via
  `native_budget`; the CLI never passes it.
- Add `--threads INTEGER` on `decoy run` (and `threads=` on `decoy.mask()`): default `min(4, os.cpu_count())`
  when the companion is present, 1 otherwise (matches the platform's knee); validated with the engine's
  `require_positive_int`; passed only when the installed `run_pipeline` accepts it (same capability-detect
  pattern as `_native_gate.run_pipeline_kwargs`). `--native` output line reports the thread count.
- Tests: kwargs builder unit test; e2e with the companion skipped when absent; `--threads 0` is a usage
  error.

### C1d remove `--substrate` and `decoy.mask(substrate=)` (with engine E3a)
- `VALID_SUBSTRATES` is `("pandas",)`; the flag selects nothing. Hard delete with E3a; `decoy explain
  substrate` topic removed or rewritten to point at `explain native`.

### C1e doc truth
- README: delete "vault has no CLI wiring"; replace the PyPI install block with the self-hosted bundle
  instruction once B-2 ships (until then, mark PyPI as "not yet published"); keep the S3/GCS refusal
  sentence until C2 lands, then delete.
- Re-pin `decoy-engine` to the frozen launch engine (B-1) and drop the `>=0.7.0` floor.
- Regenerate `docs/cli-reference.md`; the drift sentry already guards README table and root help.

## 3. Established solutions

Thread count default follows the platform's existing knee rule (one fact, now in two consumers until E2d
moves it to the engine; C1c reads the engine constant once E2d lands). Output-format dispatch by declared
format follows the source-side rule the CLI already adopted on 2026-09-30.

## 4. Done when

Each item has its e2e test; `tests/unit/test_cli_surface.py` regenerated; CHANGELOG entries under
"Fixed" (C1a, C1b) and "Added" (C1c) and "Removed" (C1d); plan archived.
