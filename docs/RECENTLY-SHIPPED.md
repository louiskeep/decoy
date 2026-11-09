# Recently shipped

Reverse-chronological log of shipped work, moved off the roadmap so the roadmap
carries only current + next-up work. This is orientation context, not the
exhaustive record: the full dated history lives in the platform repo's `docs/archive/backlog-2026/sprint-ledger.md`, and each
program's own plan doc under the implementing repo's `docs/plans/` holds the
per-task gate detail.

Standing rule (dev-loop DOCUMENT phase): when a slice lands, move it here, update
the roadmap's current + next-up, and reconcile any trailing plan STATUS lines.

Status: record

Moved here from `decoy-platform/docs/backlog/RECENTLY-SHIPPED.md` on 2026-11-05 with the roadmap
([ROADMAP.md](ROADMAP.md)). The platform copy is frozen at that date. Entries below 2026-11-05 are
copied unchanged; paths in them are relative to the repo they name.

Last updated: 2026-11-09 (entries for 2026-10-27 to 2026-10-30 are not filled in here; see the repos'
git logs).

---

## 2026-11-09

- **CLI** (`0fafd0a`, #132): X7c part S1 (roadmap row 24). Private output files are created and chmodded through one helper, `_private_file`, so every CLI write gets owner-only permissions the same way; staging temps no longer read the mode back. Parts S2 (move the remaining call sites) and S3 (sentry) are next. Gate: Dennis GO, Codex GO; full suite on the main merge 0 failing against the `b1a6350f` baseline (3,159 collected, +25).

## 2026-11-08

- **Engine** (`bf15cd99`, engine #412): VALUE-FREE-ERRORS parts A1 and A2 (roadmap row 24a). One converter turns every config error into problem codes that name keys, tables, columns and files but never a data value or secret; new exports `ConfigProblem`, `ConfigRuleError` and `parse_pipeline_config`. Part A3 (route wiring, engine release) is next. Gate: Dennis GO, Codex GO; full suite at the tested head 37,125 passed, 0 failed, 0 new failures (42,429 collected, +53).
- **Engine** (`c9064cbc`, engine #413): the test gate keeps its pytest temp root under a short /tmp path and the shared `root_dir` fixture uses the short path, so the file-access socket test no longer fails under a long temp path. Test tooling only. Gate: Codex to the cap, Dennis verified the fix (GO with fixes, applied); full suite 37,089 passed, 0 failed, 0 new failures.
- **Engine** (`942dae2d`, engine #411): LIB L0.2, run row dirs use the issued scratch root. Every row directory the engine creates during a run now comes from the one scratch root issued for that run, so out-of-core and isolated runs leave no scratch folder behind after success or failure; caller-named roots are left alone. Unblocks the F25 protected-scratch build (roadmap row 58). Gate: Dennis GO, Codex GO (lib-l02-r1), PR CI gate passed; full suite on test-6 at the tested head 37,089 passed, 0 failed, 0 new failures against the main baseline (42,393 collected, +17).
- **Engine** (`a5eb66e2`, engine #408): derived expression visibility (roadmap row 13). A `derived` expression reads exactly the columns it names, by real name; a per-row failure no longer echoes the cell value; a source with repeated field names is refused at every public entry with `duplicate_source_field_names`. Declared sources are read under their own config key through one helper, and one shared scan finds repeated names at each boundary. Registry 1.9.0. Gate: Dennis BLOCK r1 (wrong file-access key at run entry), GO r2 and r3; Codex NO-GO r1 (design: a second scan, a flat test folder), GO r2. Full suite: one failure, an edit to a released CHANGELOG section, fixed before merge; a fresh main baseline is being written.
- **Engine** (`33d05c90`, engine #407): init wizard part E3. `keyed_columns_for_config` and `KeyedColumn` list each config column that needs the mask secret, so the wizard asks for a key only when the config needs one. `secret_requirements_for_config` shares the same walk and keeps its result. Gate: Dennis GO, Codex GO; full suite 0 failing (42,148 collected), promoted as the main baseline.
- **CLI** (`e7bdae0`, #122): the CI step that fetches a pinned binary retries a timeout, a reset, a DNS try-again or a 5xx up to three times, and never retries a permanent failure. Gate: Codex GO r2, Dennis GO.
- **Engine** (`4acac80a`, engine #406): value-free discovery, subset-seed and filter errors (roadmap row 14). A subset filter literal that does not match the column type, a discovery read failure, and several FK-key and pandas-ingest errors now name the table and column only and carry no chained library error that could quote a cell. Gate: Codex GO r2, Dennis GO; full suite on the merge head 0 failing (42,028 collected), promoted as the main baseline.
- **CLI** (`e9df7b1`, #120): init wizard Phase 1a plan (`docs/plans/2026-11-08-init-wizard-phase-1a.md`). Twelve CLI slices and engine parts E1 and E3; adds one CLI-wide reason-code registry in W1a.0. Plan gate: Dennis NO-GO r1, GO r2, then Codex fix to GO.
- **Engine** (`38951412`, engine #405): SCAN-ML M1. Config fields for the pre-scan and post-scan detectors, model status and loading, NER on free-text columns only at `NER_MIN_RATE` 0.211, and the classifier wired in (off by default). Reason manifest 1.8.0. Gate: Dennis GO, Codex GO; full suite 0 failing (41,909 collected).
- **CLI** (`08124b5`, #119): init wizard spec v3, applying the 2026-11-08 spec review (Phase 1a and 1b split; section mode is `decoy edit`).
- **CLI** (`12fc2e6`, #118): `--verbose` tracebacks keep each frame header on one line under a long directory, which was the last Mac-only CLI failure. A Mac full suite on that main then ran 3108 passed, 7 skipped, 0 failed.
- **Engine** (`09376f24`, engine #404): the `openat2` binding's type annotations pass mypy on macOS too, so the Mac engine gate is clean.
- **CLI** (`834ab99`, #115): CLI-BASELINE. `gates.sh` can write a stored failing-id baseline on main (`--write-baseline`) and compare a branch against it (`--baseline-file`), refusing a file whose head does not share main's tree. The first CLI main baseline was written the same day (0 failing, 3054 collected), so a CLI full merge test is one suite run instead of two. Gate: Dennis GO r3, Codex GO r3; full suite on the merge head green on decoy-test-6.
- **Engine** (`45553d7e`, engine #403): LIB L0.1. The protected directory allocator under `fileaccess`, the first piece of the L1a records module and the first user of REG-RENUMBER. Gate: Dennis GO, Codex GO; full suite green on decoy-test-6; Mac gate green.
- **CLI** (`6694c8e`, #114): `decoy init` writes the source path into the first source entry only, keeps a trailing comment, and exits with a clear error when a preset template has no `path` under `sources:`.
- **CLI** (`91d191b`, #112): CLI-MAC-TESTS S2. All stderr output goes through one soft-wrapped console and tracebacks print through one helper, so long paths in error text stay whole on any terminal width. A sentry pins the single console. Gate: Dennis GO r2, Codex GO r2; full suite on the merge head green on decoy-test-6.
- **CLI** (`9ecf445`, #111): init wizard spec v2 (UX-reviewed with the owner) and its spec-review handoff, linked from roadmap row 32b.
- **CLI** (`ec209ec`, #110): CLI-MAC-TESTS S1. The DP tests take the refusal code the host earns from the engine reason registry, and the install and upgrade tests serve the host target, so seven Mac-only failures pass on macOS with Linux results unchanged.
- **CLI** (`92cdcac`, #109): `decoy run` prints error text unfolded with markup off, so long paths and bracketed text in errors are no longer cut or eaten.
- **CLI** (`8ac0f8d`, #107): VALIDATE-ALWAYS Part 2. `decoy run` runs the whole `decoy validate` check (config, compile, preflight) through the shared gate before it reads any source rows; an error stops the run with validate's exit code (1, or 5 for a capacity refusal), warnings are counted on stderr, and `--json` refusals add `error_kind` and `messages`. A missing source now exits 1 instead of 3. The gate adds about 0.8 s per run. Known follow-ups: a `--duckdb-source` relation is staged before the gate (FU-2) and a non-UTF-8 config still exits 3 (FU-7). Gate: Dennis GO r1, Codex GO r2.

## 2026-11-07

- **CLI** (`4cd24dd`, #105): ATOMIC-OUTPUT. Every CLI table write (CSV, Parquet, compressed CSV, chunked output) is staged in a temp file beside the output and replaces it in one rename, so a failed or interrupted run keeps the old file or writes none. An existing output keeps its mode bits. `unmask` and `detokenize` write owner-only (0600) on Linux and macOS, including a stdout redirected to a file. Closes row 61a (chunked partial target). Gate: Dennis GO r2, Codex GO r3.
- **CLI** (`ff82bc9`, #101 to #103): CLI-FMT. Every file target is written in its declared format
  (csv, parquet, fixed width) through one writer module, `cli/io/_targets.py`; before this, Parquet and
  fixed-width targets could come out as CSV. A format that contradicts the suffix, or a compression
  suffix on a Parquet or fixed-width target, exits 1 before any write; a fixed-width value that does
  not fit exits 3 with no file. A2 adds the G-ONE-TARGET-WRITE sentry and a shared scanner for the
  read and write sentries, and `validate` / `ci check` report the contradiction. Part B reads
  CLI-written files back by declared format (detokenize, unmask, `report diff`), records format and
  layout in the evidence manifest, and makes unmask fail closed when its input has none of the
  configured columns. One T3 on the stack top (2612 passed, 0 branch-only failures), then merged in
  order. Dennis GO and Codex GO on each part (A and B at round 2, A2 at round 2).
- **Engine** (`b5b1ad16`, #402): ENGINE-PAR P2. The gate's test step runs under pytest-xdist
  (`GATES_WORKERS`, default auto) with tests marked `serial` in a second plain pass; stored-baseline
  writes and compares stay serial. A collection guard refuses test ids that carry a memory address,
  which made every worker collect different ids (one test on main fixed). Mac full suite went from
  24 to about 13 minutes. Dennis GO, Codex GO; the id guard closed at the 3-round cap by owner call.
- **CLI** (`586eb18`, #99): CLI-DIALECT Part C. Every CSV read (run plain and chunked, tokenize,
  demo, init, the `data=` override, both report verbs) goes through the engine 0.19.0 reader with
  the source's declared `has_header`, `column_names` and `delimiter`; before this `decoy run`
  ignored them. Repins `decoy-engine==0.19.0`. Sentry G-ONE-CSV-READ keeps reads on one reader. A
  chunked run failing after chunk one can still leave a partial target (strict xfail, row 61a).
- **Engine** (`4a0d5b1f`, #399): R-c, engine `v0.19.0` release prep and tag.
- **Engine** (`2335fcce`, #400): init-wizard slice E0. `decoy_engine.strategy_catalog()` returns one
  `StrategyInfo` row per scalar strategy with its options, for the CLI wizard.
- **Engine** (`d46dbc85`, #398): REG-RENUMBER. `scripts/dev/registry_renumber.py` moves a branch's
  reason-registry version to the next free number after a merge race; `--check` for the merge gate.
  Version policy lives in one module, with a sentry against copies.
- **Engine** (`4c6ca215`, #397): RESULT E1. The frozen `decoy-run-result/v1` document, one record per
  `decoy run`; `derive_outcome` is the one place that maps failure category, delivery state and
  blocking check to run status and exit code.
- **Engine** (`ab7a36fc`, #396): SCAN-ML M0. The `ner` extra declares click (spaCy needs it), the
  model wheel is pinned by version and sha256 (`NER_MODEL_WHEELS`), and a `ner-gate` CI job runs the
  NER tests with the extra installed.
- **Engine** (`dd31ea91`, #401): a flaky secret-provider test checks the refused mode only in the
  error text.
- **CLI** (#95 to #98): ledger re-point at engine main, and roadmap text (SCAN-ML-MD, REL-IMAGE).
- **Engine** (`79f229d0`, #393): ENGINE-PAR P1. `scripts/dev/gates.sh` can store main's failing test
  ids once (`--write-baseline`) and compare each candidate against that file (`--baseline-file`), so
  a full merge test is one suite run instead of two. One strict reader (`load_baseline`) refuses a
  stale or shrunken baseline. Port of platform #156; P2 adds parallel workers.
- **Engine** (`cf68a280`, #394): CI-E1s. Eight locked packages move to the lowest release that clears
  their advisories (anyio, certifi, cryptography 50.0.0, pyasn1, setuptools, soupsieve, urllib3
  2.8.0, werkzeug); `pyproject.toml` ranges are unchanged. The DP certified-stack table gains one
  3.10.20 row. The audit step can no longer be hidden or narrowed. CHANGELOG notes the urllib3 2.8
  proxy TLS change for S3 and GCS users behind an HTTPS proxy.
- **Engine** (`b2ee6502`, #392): CLI-DIALECT Part E. The engine reads CSV with the declared
  `has_header`, `column_names` and `delimiter` on every route (whole file, chunked, strict
  file-access policy). Defaults live in `CSV_DIALECT_DEFAULTS`; parser failures under a strict
  policy are value-free coded refusals. Pydantic error locations naming config keys moved to
  VALUE-FREE-ERRORS (row 24a, owner 2026-11-06). The CLI side follows the `0.19.0` release.
- **Engine** (`b4c6915d`, #395): the merge gate runs on any self-hosted runner labelled
  `decoy-gate` (the Mac and the Linux runner on decoy-test-1). Plan, V2 and V1+ branches skip the
  gate queue; `main` never does. The owner-approved docs-only skip is not built, because sentries
  read `docs/` and `*.md` and path filters stop at 3,000 files; a sentry pins that no path filter
  exists. Record: `E:docs/records/2026-11-07-ci-gate-any-runner.md`.

---

## 2026-11-06

- **CLI** (`c16a5fa`, #85): LIB L1b.1, one shared atomic file writer (`src/decoy/_atomic.py`) with
  `write_atomic` for library-controlled names and `write_local_target` for user-chosen paths, on one
  write, move and fsync core. CREATE_ONCE never overwrites a competing writer. Windows reserved names
  follow CPython. `cli/ci.py`, `ci/debug.py`, the installer trust-state write and the `run.py`
  directory fsync use it, and the G-ONE-ATOMIC-WRITER sentry blocks new inline copies (allowlist 5).
  Dennis GO, Codex GO, full suite 0 branch-only. Follow-up: the Windows behavior needs a run on the
  Windows lane (WIN-RUNNER).

- **Engine** (`2986fd5a`, #388): CI-E1. Engine CI installs from the lock with `uv sync --frozen`;
  stale bench kwargs fixed, sphinx `-W` cross-refs, a truthful `pip-audit`, and two sentries that
  refuse unlocked installs and hidden CI failures. Audit-guard gaps followed in CI-E1s (#394).
- **Engine** (`adc212f3`, #389): SUB-STOP. A pipeline with a `subset:` the run path does not apply is
  refused before any read (`config.subset_run_unsupported`, registry 1.6.0) instead of masking the
  full sources. Record: `E:docs/records/2026-11-06-sub-stop-build.md`.
- **Engine** (`d9e18fa6`, #390) and **CLI** (`d60d1fa`, #93): CI-X and CI-L1. Both CI lock-install
  sentries parse shell through one shared core (`tests/sentry/ci_scan`), so both repos refuse the
  same install forms. CLI CI installs through the lock, which fixed the red CLI main (the smoke job
  now clears `output.csv` before its `git init`). Both shared-file ledgers then point at main
  commits (engine #391 `3c01f877`, CLI #94 `be5ba11`).
- **CLI** (`4ab55d4`, #88): VALIDATE-ALWAYS part 1. The validate checks live in `src/decoy/cli/gate/`,
  `decoy validate` uses them, a unique column is a validate warning (owner Q1), and a sentry keeps
  every pre-run check behind the gate. Part 2 wires the gate into `decoy run`.
- **Docs**: engine #387 points the engine docs at the roadmap in this repo; CLI #86, #87 and #89 to
  #92 are roadmap text (atomic writer shipped, V1 row status, V2 and V3 candidates, RUN-STREAM rows,
  SCAN-ML and INIT-WIZARD rows).

---

## 2026-11-03 to 2026-11-05 (summary, from the roadmap main-tips rows)

Re-read from each repo's `origin/main` on 2026-11-05. One line per merge group; detail is in each PR.

- **Engine** (`41a86f47`): H-1 E0 pure-move checker and Wave B sentries (#372 to #375); F31 E0c
  registry 1.5.0 (#377); X0a ratchet and manifest (#378, #379); X0a self-hosted gate (#380); H-1 E5
  (#381); X7b isolated-run payload as a private file (#382); CI-E0 golden suite repair and tokenize
  coverage (#383); X4d GCS client timeouts and the outbound client construction sentry (#384, #385);
  H-1 E3 module splits (#386).
- **CLI** (`8fba6af`): F30 C1a OTel exporter (#80); CLI X0a ratchet, every sentry gated and
  baselines shrink-only (#81), CLI allowlists registered in the ratchet (#82).
- **Platform** (`73a0bfca`): user role builds and runs pipelines (#164); B-10 S1b (#165); F21 s1b
  layout authoring (#170); credential cascade on user delete (#171); RBAC S0-pre shared route walk
  (#173); X0b (#178); X0a gate CI (#180); X0a-h plan (#181); X7a (#182, #183); deactivation S1 and
  S1b (#184, #193); test trust (#185, #186); CI lanes plan (#187); X5b (#188, #189); password-reset
  token fix (#192); pipeline baseline (#194); X2a FK delete policy (#195, #196).


## 2026-11-01 evening (merges after R-a)

Re-read from each repo's `origin/main` on 2026-11-02. Gate verdicts are from the gate ledger; test counts are
worker-reported unless marked.

- **Platform #131** (`32b4149f`, `fix/key-restore-output`): key restore returns only `which`,
  `restart_required` and `message`; the three 422 refusals use fixed text with no cause or context;
  `KeyDurabilityError` no longer chains the `OSError`; the SSO discovery test returns no URL or error text.
  Canary tests fail on the old behavior. Gate: argon text-only GO.
- **Platform #132** (`584a15a7`): roadmap currency, Phase 0 evening update.
- **Engine #359** (`a3fe49e8`, `fix/sbom-polish`): SBOM generator failures use fixed messages, raw `uv`
  and CycloneDX output is replaced by fixed lines unless `DECOY_SBOM_DEBUG=1`, `PIP_*` and `PYTHON*` scrubbed by
  allowlist. Gate: argon text-only GO-WITH-FIXES. Known follow-ups: `sbom.sh` line 96 `cd` stderr can name
  the caller path; lock-mode refusal still prints lock package names.
- **Platform #133** (`2d40c9a5`, `feat/di1-gof-build`): DI1 goodness-of-fit measurement. Main merged in with
  one docs-header conflict (main's header kept). Suites: no new failing id against main.
  `api/quality/runner_hook.py` is now 710 lines (main was 631).
- **CLI #76** (`57e8b81`, `chore/repin-engine-0.17.0`): repin to engine 0.17.0 (split renames,
  `version: 2` configs, keyed mask secret on `report vault` and `unmask`, rule-code allowlist derived lazily
  from the engine reason registry, per-route keyed-secret guidance). 1979 tests pass on 3.10, 3.11 and 3.12
  against 1866 on the previous main. Gate: argon text-only GO.

## 2026-11-01 (engine release R-a, platform remainder)

Re-read from each repo's `origin/main` on 2026-11-01. Worker-reported test counts are from `uv.lock` or
`requirements-dev.lock` venvs and were not rerun by the orchestrator.

- **Engine release R-a:** annotated tag `v0.17.0` at `1132d29e` (R-a prep merge: version single
  source 0.17.0, `docs/records/release-ra-facts.md`, `scripts/release/cut-release.sh`, reason-release pin
  tooling, differential-privacy rows re-pinned). Carries the STORM close-out, F13 slices 0-2, the OOC
  correctness harvest, the main-health fixes, the B-2 release script fixes and the SBOM generator.
- **Platform #130** (`19b50071`, `fix/platform-remainder`): the suite is green apart from a known list.
  Str-valued enums format as their value on every Python (59 enums, one base class, a sentry);
  24 mutating routes classified for audit coverage with a test that every listed helper writes audit;
  `hash_csv_file` handles NUL on 3.10; `/api` router wiring moved to `api/api_router.py` with an
  identical route table; stale tests corrected; the slow h5 test sized for the row-framed reader
  (about 156 s down to 7 s alone). Worker-reported on 3.10: 15 failures left, all known (13 P6
  parquet-size drift, one p6b golden case kept red for BLOCKER-2, one flaky genapi_1f test).

---

## 2026-10-31 evening (all repos): main-health fixes, release script, SBOM generators

Merge commits re-read from each repo's `origin/main` on 2026-11-01. Tests quoted here were run by the
workers on `uv.lock`/`requirements-dev.lock` venvs, not rerun by the orchestrator.

- **Engine #352** (`0090f6f9`): main-health fixes (module-size census, 3.12 f-string and fd fixes, mypy
  16 to 0, numpy timedelta, `type` added to the frozen `when` reserved names). **Engine #353**
  (`78b78e2d`): the native companion release workflow and its checks script (relative key paths survive
  the `cd`, five-field wheel names, anchored platform regexes, pinned version, checksum parsing like
  `sha256sum --check`); unexercised, Actions is billing-blocked. **Engine #354** (`1491c7fa`): OOC
  correctness harvest. **Engine #355** (`1ee89e68`): CycloneDX SBOM generation from `uv.lock` in a
  hash-pinned tool environment. Engine main worker-reported: 0 failures on 3.10, one known failure on
  3.12 (`test_skewed_weights_skew_cdf`, `899999 == 900000`). Released as `v0.17.0` on 2026-11-01 (R-a).
- **Platform #128** (`4077fa21`): canary-check ownership checked against the caller, `create_job`
  passes the authorized pipeline id, snapshot-less canary-check refused (409), `run_job` persists the
  snapshot atomically with pending to running, log-key contracts. **Platform #129** (`c7bc3dc4`): main
  imports and collects again (storm consumer migration, duplicate catalog keys removed, mypy and ruff
  clean, route-template label under FastAPI 0.162, new engine-import-surface sentry). Worker-reported
  full suite on the #129 branch: 41 failures remain (13 P6 parquet-size drift, 28 other groups).
- **CLI #74** (`8834ab9`): AST sentry forbidding private `decoy_engine` references outside an exact,
  counted allowlist. **CLI #75** (`df4c069`): CycloneDX SBOM generation for the CLI runtime pins.

Not shipped from this day, still open: the OOC temporal FK seam (built, round 2), A-4 (Codex NO-GO,
round 3), the B-6 batch writer (not gated), release R-a (prep running), the platform remainder.

## 2026-10-31 (all repos): STORM close-out, F13 slices 0-2, R1-a closed, health records

Merge commits re-read from each repo's `origin/main` on 2026-10-31.

- **Engine #339** (`6ce435ce`): F13 secret provider, engine slices 0-2 (secret-provider/v1 contract,
  before-read admission, Vault KV v2 adapter; 7 `runtime` reason identities). Slices 3-5 are next.
- **Engine #349** (`6d82517f`): STORM close-out. Profiling/verification split, F29 registry
  unification, v0.16.0 identities kept as tombstones. Registry on main after #339 and #349: 891
  identities, 14 namespaces, 2 tombstones (counted with `uv run --frozen` from `uv.lock`). Not yet
  released; the latest engine tag is still v0.16.0.
- **Engine #350** (`79b5c264`): engine main health record (survey only). **Engine #351**
  (`545d913c`): per-column routing performance concept (docs, not gated).
- **Platform #124** (`aad2de7`, 2026-10-30 23:50 -0500): roadmap branch register. **Platform #125**
  (`b31bbaa`): cross-model audit packets 11-20. **Platform #126** (`a4f5857`): platform main
  health record (survey only).
- **CLI #71** (`850fd92`): dead engine substrate plumbing removed and an engine import-surface
  sentry added; closes R1-a. Breaking, pre-GA. **CLI #72** (`8b4353b`): CLI main health record.
  **CLI #73** (`c459758`): `decoy init` wizard spec, registered Post-V1 on demand.

Main was red in all three repos on 2026-10-31 (engine module-size sentry, platform `api.main`
import, CLI e2e until #71). Fixes are in flight and not shipped, so they are not logged here.

## 2026-10-26 (platform): main un-red - tokenize catalog coverage + engine 0.15.1 reconcile

Platform main had been non-bootable since the #105 repin left the 0.15.x migration half-done
(pyproject + CI at 0.15.0, but the engine_compat specifier, the version-fence tests, FROZEN, the
capability doc, the fence PIN_PREFIX, and the Dockerfile engine ARG all still at 0.14.2). The GitHub CI
is billing-blocked, so only the local ci-mirror caught it. Un-red landed as a decoupled standalone
(`c717fa43`; dennis GO, and Codex had already cleared the catalog coverage + import against 0.15.1 in
the B-6 gate): the confirmed-safe tokenize strategy-catalog coverage plus the full engine 0.15.1
reconcile, WITHOUT the B-6 vault feature (whose crypto/concurrency half was still in security
remediation). `api.main` now imports and boots on engine 0.15.1 (tag v0.15.1, stamp fd51be10). The
vault platform half rebases onto this bootable main and lands its vault-only delta once it clears both
gates.

## 2026-10-26 (engine): 0.15.1 release + B-9 DI1a engine half (datetime / free-text GOF)

The DI1a measurement half (engine) merged and shipped as a point release:

- **B-9 DI1a engine measurement** (engine PR #326, merge `f6ce5db1`): extends generation-output
  fidelity (GOF) measurement to datetime and free-text columns. Report-only; no distribution claim.
  dennis GREEN; Codex final GO (one non-blocking MEDIUM: a serialized metric keeps the generic
  `ks_complement_binned_cdf` tag without the domain label).
- **Engine 0.15.1 release**: version stamp off `release/v0.15.1` (`fd51be10`), tagged `v0.15.1`. It is
  0.15.0 plus the DI1a GOF and the post-0.15.0 main progression (the #309 bounded reader, parity E2a).
  DI0 golden is byte-identical on both 0.15.0 and 0.15.1 (the GOF is additive). Platform reconciles to
  `decoy-engine==0.15.1` as part of the B-6 platform-half merge.

## 2026-10-26 (engine): 0.15.0 release + route-coverage, tokenize sentries, bounded reader

Four engine merges landed after the B-6 write-seam, all two-checkpoint gated (dennis then Codex
cross-model) and reconciled onto a moving main:

- **Route-coverage phase 1** (PR #324, `a39c648`): B3-B7 out-of-core and bounded-sequential strategy
  coverage (faker pool, group_key, text_mask, code_set).
- **Tokenize sentry registration** (PR #323, `bbe4dce`): registered the `tokenize` strategy across the
  correctness sentries (distribution-behavior label, leak-check TRANSFORMATIVE, proof-manifest waiver,
  capability matrix, technique class) that the #322 write-seam had left unregistered, which had reddened
  main. Green-main fix.
- **gm bounded reader + progress sink** (PR #309, tip `17c0bdeb`): parity E2a `decoy_engine.io` reader plus
  the value-free progress sink (output bytes never depend on the sink).
- **Engine 0.15.0 release**: version stamp off main, tagged `v0.15.0` (the additive feature release since
  0.14.2: vault write-seam, Phase D FK, CSV source params, route coverage). Platform repin to 0.15.0 is the
  remaining D-4 piece.

## 2026-10-26 (platform): docs currency - capabilities + roadmap ground truth (#103, #104)

Refreshed `docs/product/capabilities.md` to the shipped surface (engine tokenize write-seam, the 10-feature
governance bundle, FORECAST retired, mask count 24) and added `docs/backlog/roadmap-vs-reality-2026-10-26.md`:
a code-verified SHIPPED/PARTIAL/OPEN map of all 27 V1 build-order items (12/7/8), then folded those verdicts
and the day's merges into ROADMAP.md and archived the superseded current-assignment table.

## 2026-10-26 (engine): B-6 tokenization vault - engine write-seam (PR #322)

Engine half of reversible tokenization. A `tokenize` masking strategy writes a deterministic surrogate
token per source value and records the plaintext->token mapping through a platform-injected
`TokenVaultWriter`; `run_pipeline` gains a keyword-only `token_vault_writer` (additive, recorded in
compatibility-contract 3.4). Full-frame only; fails closed with no vault, no namespace, non-string
dtype, or any vault error (coded `tokenize_vault_error`, no value/token leak). Always-keyed, so GA
requires a real secret. Vault identity is scoped by `(namespace, plaintext)`.

Gate: dennis GREEN; Codex final GO. The Codex cross-model gate caught three security findings the
internal review missed - GA secret bypass, cross-namespace token collision, and plaintext leaking
through a vault-callback exception - all fixed at source with regression tests and confirmed closed on
re-gate. Local verification 7803 passed / 8 skipped; ruff + mypy clean.

Next in the B-6 chain: cut an engine release exposing the write-seam, repin the platform, then build
the platform half - the vault store (must key by `(namespace, plaintext)`; its exception-logging must
not dump `exc.__context__`) plus the admin-only de-tokenize auth (already implemented + dennis-verified).

## 2026-10-26 (platform): confident-dirac 10-feature hardening bundle + OBS-5 audit-drift fix

**confident-dirac bundle.** The ten reviewed-and-remediated platform-idea features merged to main:
Ed25519-signed output passport, external-KMS master-key envelope, air-gapped install bundle, bounded
output canary-leak check, referential-subset preview, checksum-validated regional detector packs,
source schema-contract with drift detection, upgrade-determinism golden gate, advisory
column-disposition memory, and admin-authored org-disguise presets. Four alembic migrations serialize
into one linear head (table count 79). dennis-GO on the rebase reconcile (migration chain + 79 tables
verified on real Postgres; feature code byte-identical to the earlier Codex-GO'd state).

**OBS-5 audit-action drift guard.** Registered the ENV-2 `pipeline.binding.*` actions in
`AUDIT_ACTIONS` and classified the `genkey.*` and confident-dirac governance actions
(`passport.sign`, `golden.*`, `schema_contract.*`, `column_disposition.*`, `org_disguise.*`) as
blocking in `SECURITY_CRITICAL`, greening the audit-coverage drift guard.

---

## 2026-10-26 (engine): cross-column PR1, release-hygiene, v0.14.2

**Cross-column dependency PR1 (engine #315).** Fixes a latent order-dependent read: `derived`,
`group_key`, and `joint_mask` could read a declared sibling driver column by lexicographic name-sort
accident instead of its masked value. Adds an explicit dependent-after-driver ordering edge and pins
the driver-read direction per strategy (derived/group_key read masked from the live frame; joint_mask
key_by reads source from the pre-mask snapshot). Double-gated (dennis GO + Codex GO) after three Codex
remediation rounds that closed the joint_mask multi-entry writer-map stale read, the missing-snapshot
fail-closed gap, the when-gated snapshot alignment, and the gated multi-output writeback. PR2 (the
derivation feature itself) is a later slice.

**Engine release hygiene (#314).** `gen_proof_manifest.py` now derives the stamped engine version from
the newest CHANGELOG release section instead of a frozen `0.2.0`; the proof manifest was regenerated.

**Engine v0.14.2 tagged.** Patch release carrying the subset single-table edgeless-over-budget fix
(#312), cut so the platform referential-subsetting preview can pin it.

**Known CI note:** the `substrate (pandas)` RSS perf test (`_ENVELOPE_FACTOR = 1.35`) is too tight for
the CI runner and fails non-blockingly on engine PRs; recalibration to ~1.45 is queued (decision D2).
The CodSpeed `benchmarks` job is also broken repo-wide (action v4 + installer-hash mismatch).

---

## 2026-10-25 (docs + web currency): D-1/D-2 refresh, marketing-site honesty fixes

**D-1 capabilities.md (platform).** Refreshed to the V1 shape and then a follow-up pass corrected
the stateless-CLI command surface, stated pandas as the default masking engine (Polars scoped to
subset only), and fixed an over-stated platform vault-recovery claim (the full-frame route does wire
a VaultWriter; end-to-end recovery is not yet developer-verified). dennis docs-honesty gate caught
the false vault claim; fixed and re-gated GO.

**D-2 architecture docs (platform).** Rewrote the living `docs/architecture/*.md` to the stateless
CLI shape and dropped the retired project/catalog/jobs and FORECAST surfaces. Accepted ADRs were
left immutable (the refresh touched only the living docs).

**Marketing-site honesty (B-3 partial, decoy-web).** Softened two overstated claims: the audit-log
heading now reads "tamper-evident" rather than "proves it was not edited", and single sign-on reads
"supported, documented for" rather than "tested with" (real-IdP testing is customer-deferred; CI is
mock-based). The homepage performance figures, DP wording, and license split were flagged for a
human decision and left unchanged.

**A-3 reconciled.** Confirmed the route/backend capability page already shipped as
`decoy-engine/docs/execution-backends.md` (#305), including the composite and multi-parent FK
decline-with-reason detail; no second page was created.

## 2026-10-25: Phase D multi-parent FK (A-9, Dmp) + DuckDB-in CLI source (B-1)

**Dmp (multi-parent FK, engine #310, `c5e70982`).** Multi-parent foreign keys now admit on the
out-of-core (streaming) route with byte-parity to the reference path (folds N parent relations into one
first-hit-wins relation, then the child joins once; deterministic; fail-closed on cross-parent dtype
mismatch). Rebased onto the post-dcomp main (supersedes the closed #308). Double-gated; the real-kernel
suite is non-vacuous (require_companion gate, 150 passed), zero new substrate failures. With dcomp
(#307) this completes A-9: both hard FK shapes are native on the out-of-core route.

**DuckDB-in CLI source (decoy #c1f5e60).** `decoy run --duckdb-source TABLE=DB_PATH` (repeatable) reads
a table from a DuckDB file as a masking source: opens read-only, snapshots the relation to a temp
parquet (reserved-word / case-variant safe via catalog-resolved double-quoting, default-schema-only),
and masks via the ordinary parquet path (no engine change). Double-gated; 18 e2e tests. Completes the
B-1 DuckDB-in item.

## 2026-10-24: Environments / release RBAC (B-7, PR #100)

Typed per-environment pipeline resource bindings (`pipeline_resource_bindings`, the `${resource.*}`
scope) plus promotion/release RBAC merged to main (`14209a19`). The remote worker's branch was rebased
onto current main (migration re-pointed onto the `genapi1e` head for a single alembic head), then
double-gated across several rounds. The gate closed: the ENV-2 cross-user validate-yaml binding leak
(HIGH, foreign user now 404s with zero decrypt), value-free refusals (no submitted field, descriptor
type, or role echoed anywhere), a false-green `${resource.db.<field>}` at validate time (now matches
the run-time field walk, bare NO_DEFAULT references too), and existence-only validate (no decrypt on
the reject path). dennis GO + Codex GO. The in-app admin/RM/user roles are the V1 model; owner/grant
self-service de-token stays V2.

## 2026-10-24: Served PipelineConfig JSON Schema endpoint

`GET /api/pipelines/config-schema` now serves the engine's `PipelineConfig.model_json_schema()` (in an
envelope with the installed engine version) so the web client can pre-check a pipeline document's shape
before a server round-trip. Read-only, authenticated with the standard pipelines gate, no new
permission. The served schema is the engine model's own, so it can never fork from server validation;
`validate-yaml` and job-preview stay the authority. First of the 2026-10-24 remote-worker `feature/*`
batch to clear the gate (dennis GO, Codex GO-WITH-CHANGES on docs only). Merged `a69265e0`; branch
deleted. Plan: `docs/plans/2026-10-24-served-pipelineconfig-json-schema.md`.

## 2026-10-24: MCP server (B-8) + platform-wide file-source authorization

The in-app MCP server merged to platform main (`ababaf6c`): an agent-facing `/mcp` surface with a
capability-tier registry, a fail-closed `CuratedTargetGuard` (exact-route allowlist, refuses to mount if
any curated route is missing), and a `wait_for_job` long-poll that releases its DB connection before
sleeping and caps waiters per-principal and globally. It ships with `api/jobs/source_authz.py`, a single
choke-point that authorizes every pipeline file source under the caller's principal at four entry points
(create_job, job preview, node preview, workflow-step build): a non-admin may read only their own managed
uploads; absolute/external paths stay admin-only; foreign and missing uploads return an identical 403 (no
existence oracle); any descriptor that is not a literal `s3`/`gcs` binding type has its path authorized,
so a variable/missing/unknown source type cannot smuggle an absolute path past the check. Double-gated
(dennis + Codex); the cross-model gate caught and closed, across rounds, a path-injection tier bypass, a
source-authz BOLA, an unbounded download, a connection-pool exhaustion, and the variable-typed-source
escape. Deferred (documented): a claim-time re-check for jobs queued before the fix and for iteration
children (defense-in-depth for the single-org trust boundary). Supersedes the earlier MCP branches and
PR #101 (landed via the rebased `feat/mcp-b8-complete`). Plan:
`docs/plans/archive/2026-10-22-mcp-server-buildout.md`.

## Older entries

Entries dated 2026-10-24 and earlier, and the program-level history, are in
[archive/](archive/README.md).
