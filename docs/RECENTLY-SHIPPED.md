# Recently shipped

Reverse-chronological log of shipped work, moved off the roadmap so the roadmap
carries only current + next-up work. This is orientation context, not the
exhaustive record: the full dated history lives in the platform repo's `docs/archive/backlog-2026/sprint-ledger.md`, and each
program's own plan doc under the implementing repo's `docs/plans/` holds the
per-task gate detail.

Standing rule (dev-loop DOCUMENT phase): when a slice lands, move it here, update
the roadmap's current + next-up, and reconcile any trailing plan STATUS lines.

Status: record

## 2026-11-21: merges of the day

- **Engine #747 (STAMP-IMPORT, `94ec3cb6`):** the release stamp no longer deletes the `UNRELEASED` import from a reason module, so a new unreleased code on a stamped module no longer fails at import. A sentry checks every reason module.
- **Engine #741 (row 79, F09 E1, `152de220`):** vaults are written as v3 with an authenticated, versioned header; v2 vaults open read-only. An older engine cannot open a v3 vault.
- **CLI #365 (row 63, SAMPLE SC1, `1c63fe74`):** the sample run writes into a staged folder and refuses unsafe output names before it writes.
- **Engine #745 (COLUMN-SHAPE-RULE E0, `5bc0227e`):** `bucket_perturb` never writes an unparsed date cell through unmasked.
- **CLI #368 (`0da58741`):** roadmap rows PRE-SCAN-RUN and HANDLER-ROW-COUNT.
- **Engine #684 (row 82, F07 E3b) not merged:** held as a draft until 1.1, because row 82 is a Later row.

## 2026-11-21: engine 0.28.2 repin (CLI)

- **CLI**: the engine repin to 0.28.2 (tag `v0.28.2`, engine #740, `2bee0c523`). `requirements-certified.txt` keeps its 70 pins; fingerprint is now `44aaa90f...`, a certified row in the engine.

## 2026-11-21: roadmap catch-up for merges of 2026-11-13 to 2026-11-20

- Row 24zx (MAC-WHEEL-RUNNERS) is closed. Its only slice, E5 of the V1 fix batch, is engine #651 (2026-11-20): a PR that does not touch the native companion no longer waits for a macOS runner. The owner swapped the three required `companion-wheel-macos` checks for `companion-wheel-macos-ok` on 2026-11-20. Row 24zo (CI-SELECT-GAP) shares slice E5 (`engine-gate/verdict` status and the `verify` check) but stays open until the owner adds that status to the required checks. Earlier slices of the same batch: E1 #649 (row 24zp) and E2 #648 (row 24zu).
- Row 24zi (PROP-FALLBACK) stays open. E-F0 is engine #617 (2026-11-20): `text_mask` refuses detector and strategy pairs the engine cannot run, which closed a live leak. Slices E-F1, E-F2, C-F1a and C-F1b are not merged.
- FREEZE-SURFACE: S2 (CLI #343, hidden `decoy demo --ref` and `--rows` removed), S7b (CLI #341, CLI tag census) and the public renames table (engine #730) are merged. Every slice is now merged; the row waits only on a sign-off.
- FREEZE-OUTPUT: O1 (engine #702, 2026-11-19). `when:` compares integers exactly beyond 2**53, and one blank-row rule holds on every route. O2 is not merged.
- DATE-SHIFT-FORMAT: S4a (engine #721, `jitter_days` through one window resolver), S4b (engine #728, `date_format` required with a coded refusal, detected format in the starter) and C1 (CLI #342, `decoy init` writes `date_format`). Left: the engine release and the CLI repin.
- GEN-WINDOWED-BATCH S1 (engine #718, 2026-11-19): batched derive, parse, shift and format for `windowed_date`, same bytes.
- NONFK-OOM S1 (engine #719) and S4a (engine #717): the resident lower bound with its baseline, and the multi-table split decided in `decide_route`.
- OUTPUT-METADATA-LEAK: E0 (engine #692), E1 (engine #700) and E2 (engine #726, 2026-11-20). C1 (CLI targets) is in review.
- Row 74 (F26): E1 (engine #638) and E2a (engine #641), both 2026-11-20.
- Row 24p (GEN-PROVIDERS) E1 (engine #661, 2026-11-20). Row 24n (GEN-REL) slice 1 (engine #523, 2026-11-20). Row 24s (GEN-CATALOG) GC3-E (engine #643, 2026-11-20). Row 24f E2 (engine #732, 2026-11-20).
- Row 24e (CLI-QA1) DI close: E0 (engine #611), E1 (engine #615) and E2 (engine #736). Left: C1 and C2.
- Row 56: C1 (CLI #292), C1b (CLI #293) and C2 (CLI #304) of the retired-name removal. Left: C3.
- DECOY-LANG: the compiler, converter and formatter (CLI #333, 2026-11-20).
- Row 63a E5b (engine #605, 2026-11-16) and row 61 DELIV C1 (CLI #237, 2026-11-13).
- Rows 24zk and 24zl: C-S1a (CLI #312), C-G1 (CLI #318) and E-G1 (engine #688, 2026-11-20).
- QA-BETA S0 (CLI #356), S1a (CLI #358) and S1b (CLI #360), all 2026-11-20. The owner paused the program after S1b.
- Also merged on 2026-11-20: CLI #362 (the baseline ratchet gains owner-approved `approved_growth` rows) and engine #739 (contract checklist wording; docs only).

## 2026-11-20: `decoy.scan()` returns the scan document (FREEZE-SURFACE item 3)

- FREEZE-SURFACE item 3 (audit J2) is done. CLI C1 #354 put `decoy scan` and `decoy demo` behind one shared scan call, `decoy.cli.scanning.scan_descriptors`. C2 ports `decoy.scan()` onto it: it returns the value-free `scan-set/v1` document that `decoy scan --output` writes, with the CLI's input rules (a CSV states `has_header`, `.tsv` is tab-delimited, the default is 10,000 rows). This is a breaking Python API change, owner-approved before GA. A sentry now fails on any other first-party call of `scan_sources`, `scan_set_to_dict` or `profile_columns`, except `decoy init`.

## 2026-11-20: optional ML detectors in scans (row 32a)

- Row 32a (SCAN-ML) is closed. Engine: M0 #396, M1 #405, M5 #508, M4 #512 and M3a #602. CLI: C1 #298 (`decoy models`, the setup step, the model preflight and `decoy doctor` rows), C2a #301 (the run post-scan report and the exit 4 block) and C2b #351 (`decoy scan --detectors`; a model that is not installed is refused before any data is read). The last slice, M3b (classifier suggestions in a starter config), moves to the DECOY-LANG row as S8 (owner 2026-11-20), because the init wizard it was planned onto stopped on 2026-11-19.

## 2026-11-20: run result document and F29 remainder (rows 62 and 66)

- Row 62 (RESULT) is closed. Every slice of plan `result-remainder` is merged. Engine: E2a #535, E-CAP #536, E3a #538, E-OOM #544, E2b #543, E3b #552 and the exit 5 disk code #551, all in engine 0.28.1, which the CLI pins. CLI: C-EXIT #228, C-REASON #229, C-CAP #240, C-DOC1 #336, C-DOC2 #344 and C-DOC3 #350, which adds `--result PATH` to write the run result document.
- Row 66 (F29 remainder) is closed. Its CLI consumer work (C1) is the row 62 CLI work above, all merged, and C0 is engine #367. The F31 hook no longer applies: the owner closed F31 for CLI V1 on 2026-11-12.

## 2026-11-20: freeze slices S5 and S7a (engine)

- `when:` filters reserve `null`, `true`, `false`, `between`, `like`, `ilike`, `matches`, `startswith` and `endswith` as column names, so later grammar can use them (engine #722).
- A tag census classifies every `name/vN` constant in engine source as a frozen format, a derivation label, an internal tag or a declared casting format (engine #723).
- Engine 0.28.1 released (engine #706).

## 2026-11-20: library commands (rows 39 and 40)

- `decoy library list`, `show`, `diff` and `ref` (CLI #215) and `prune`, `clean` and `export` (CLI #219) are merged. Paths print as plain text, never as Rich markup.
- OS lanes: Linux and macOS ran. The Windows lane (`test_clean_with_a_file_held_open_on_windows`) is written and skip-marked; it runs with the Windows chain (row 89 WIN-FEAS).

Moved here from `decoy-platform/docs/backlog/RECENTLY-SHIPPED.md` on 2026-11-05 with the roadmap
([ROADMAP.md](ROADMAP.md)). The platform copy is frozen at that date. Entries below 2026-11-05 are
copied unchanged; paths in them are relative to the repo they name.

Last updated: 2026-11-20 (entries for 2026-10-27 to 2026-10-30 are not filled in here; see the repos'
git logs). Dates are the UTC merge dates from GitHub.

---

## 2026-11-20

- **Roadmap** (rows 24zb and 24b, both closed): row 24zb DATE-SHIFT-UNKEYED. An unkeyed `date_shift` is refused in V1. The engine deletes the MD5 offset path and pins the refusal (engine #612, `57f5d25f1`, 2026-11-16). CLI #346 (`be6e452e`, 2026-11-20) tests that `decoy run`, `decoy run --chunked` and `decoy.mask()` each refuse an unkeyed `date_shift` with `keyed_strategy_requires_secret` and write nothing. Row 24b QA-GATE: `decoy validate` refuses what `run` would refuse. A declared column missing from the source exits 1 at validate (CLI #300, `f7deac1e`, 2026-11-17). `fpe` with no namespace exits 1 at validate (engine #569, `e6eeea105`, 2026-11-13). A statistical column with no usable labels gives `statistical_stats_degenerate` at validate (engine #619, `b3206c042`, 2026-11-17; CLI test in #348, `73b85a43`, 2026-11-20). Remote s3 and gcs sources get a warning at validate, not an open, by design (CLI #300).
- **Roadmap** (row 84, closed): F24 engine half, the full-lifecycle job estimate. Its slices 84-E1 and 84-E2 shipped in engine 0.28.0, and the row closed once the CLI pinned that engine; it now pins 0.28.1. The plan has no CLI change.
- **Roadmap** (row 34, closed): L1b-cli, the local record store. Every slice is merged: L1b.1 shared atomic writer (#85, `c16a5fa`), L1b.2 store core (CLI #205, `16135525`), L1b.3 refs and retention (CLI #206, `f9f6b680`) and L1d library scratch (CLI #214, `b1478867`). Its Windows lane runs with the Windows chain (row 6) after the V1 build.
- **CLI** (CLI #340, stacked on #327): the CLI halves that wait on engine 0.28.1, closing four rows. PROFILE-SAMPLE-LABELS C1: `decoy scan` labels a sampled count (`10,000 of about 28,058 (sample, head)`), lists no key on a sample, and `--json` gains `basis`, `scanned_rows` and `row_count_exact` with `row_count` now the source count; `scan show` labels a sampled saved scan. Row 24zm C1: the `decoy.scan()` docstring says the saved profile is floored. Row 24z Z-C1: `decoy run --post-validate` prints a line for a deterministic `faker` column whose distinct sources merged. Row 24zu: a test pins that `decoy demo` then `decoy report integrity` exits 0.
- **CLI** (CLI #327): the engine repin to 0.28.1 (tag `v0.28.1`, carries 0.28.0). `requirements-certified.txt` has 70 pins (adds `joserfc`, `rfc8785` and `pynacl`) and fingerprint `b61dcfd6...`, which the engine lists as a certified row. Rows 24zp FIT-YEAR-CODING and 24zq NESTED-INIT-REG (engine halves merged) close with the pin. The CLI halves of rows 24zm, 24f, 24z, 24zu and PROFILE-SAMPLE-LABELS follow in a stacked change.
- **Roadmap**: row 32b INIT-WIZARD closed under the owner's 2026-11-19 decision to stop the guided wizard. 1.0 keeps today's `decoy init` (presets, and `decoy init <file>` with `# REVIEW:` comments) plus the engine pieces E3 (engine #407), E1 (engine #653, `56a06f1b3`, 2026-11-19: `column_entry` and `apply_review`) and E2 (engine #654, `40e2bb275`, 2026-11-19: `finding_edits`). E1 and E2 ship in the experimental tier. The rest of `C:plan/init-wizard-v1-rest` is stopped; pipeline authoring moves to DECOY-LANG.

## 2026-11-19

Engine 0.28.0 (tag `v0.28.0`, engine #698, `7dc9e30bd`) was cut at 00:45 UTC. The CLI pins 0.28.2 (CLI #327, then the 0.28.2 repin). Engine entries below 0.28.0 marked "after the tag" are in no release yet.

- **Engine** (`fa656aa23`, engine #700; `ce542ffaa`, engine #692, 2026-11-18): OUTPUT-METADATA-LEAK slices E0 and E1 (roadmap row OUTPUT-METADATA-LEAK, partly merged). E0 is the canary matrix across every output route. E1: published Parquet files carry only an allow-list of key/value metadata, through new `output_schema` and `output_table`. Extension-type columns are written as their storage type, except `arrow.uuid`, `arrow.bool8`, `arrow.json` and the pandas period and interval types. E2 (carrier sites) and C1 (CLI) are left.
- **Engine** (`cc0149152`, engine #707): PROFILE-SAMPLE-LABELS slice E0 (partly merged). `ProfileSource.sample_frame(n)` returns n rows unless the source ended. Cloud CSV scans now profile the requested 10,000 rows, so their null counts, distinct counts and profile hash can change.
- **Engine** (`7cf921365`, engine #704), (`208478504`, engine #699) and (`b25e5b71f`, engine #697) with **CLI** (`9a0874df`, CLI #325; `c76b2ca1`, CLI #326): freeze batch slices O3, S1, X0, S4 and S6. O3 (row FREEZE-OUTPUT, partly merged): pass-through `large_string` text narrows to `string` by one width state. S1 and S4 and S6 (row FREEZE-SURFACE, partly merged): the unused strategy base modules are removed; the ambiguous `--source` refusal is `report.source_ambiguous` and the gate and warning code sets are pinned by an exact snapshot; one `decoy._outbound.open_url` opens every CLI request, with fixed schemes and a redirect rule per purpose. X0 (row EXPERIMENTAL-TIER, partly merged): the stability registry with frozen, experimental and internal tiers.
- **Engine** (`4b45bf93f`, engine #701): EW1 (roadmap row 89, partly merged). Every open flag comes from `fileaccess/_osflags.py`, so the engine imports and opens files on Windows.
- **Engine** (`e744abe35`, engine #695; `9e6547298`, engine #696, 2026-11-18): FAKER-MIGRATE slices S1 and S0 (partly merged). S0 records what Faker 40.54.0 changes. S1 is the Faker output lock under 40.23.0.
- **Engine** (`305fd36ed`, engine #709): a test-only fix. The descriptor test counts only descriptors under its own root. No roadmap row.
- **CLI** (`fa242c2c`, CLI #328): UPGRADE-KEY slice UK1a (roadmap row UPGRADE-KEY, partly merged). Trust state, backup pin placeholder, key fingerprints, `keygen --encrypt` and `backup-check`. UK1b to UK1d are left; the real backup key is an owner task due 2026-11-28.
- **CLI** (`0c18778c`, CLI #331): rows 24zv and 24zw (both closed). `decoy report fidelity` prints `column <name>: <metric> goodness-of-fit unavailable (<reason>)` instead of the placeholder line, and the `decoy report vault` help says the vault opens under the mask secret and the seed is not key material.
- **CLI** (`ccc5540a`, CLI #318): PROP-GUARDS slice C-G1 (roadmap row 24zl, partly merged). Each sentry allowlist lives only in its baseline JSON; the sentry list is a glob; `ratchet_check.py` runs on pull requests.
- **CLI** (`8e98a836`, CLI #317, 2026-11-18): DUP-FREEZE slice CL5 (roadmap row 24zf, partly merged). The root crash guard prints an engine `EnvFlagError` through the one error emitter and exits 1.
- **CLI** (`0e8534dc`, CLI #313, 2026-11-18): PROP-SHIMS D6, saved-scan half (roadmap row 24zk, partly merged). `decoy demo` writes `scan-set/v1`, and the saved-scan reader refuses an untagged file with `scan.saved_scan_schema_unsupported`.
- **CLI** (`d8181e0f`, CLI #323, 2026-11-18): the Windows proof lane record `docs/records/2026-11-18-win-lane.md` (roadmap row 6, partly merged).
- **CLI** (`a081902e`, CLI #314, 2026-11-18): `decoy library path` no longer folds a long path across lines off a terminal. No roadmap row.

## 2026-11-18

All engine entries below merged before the 0.28.0 release prep (engine #698) and are in engine 0.28.0 (tag `v0.28.0`).

- **Engine** (`ad36687a6`, engine #658): F33 slices E1a and E1b (roadmap row 72, partly merged). The signed-evidence verifier moves into the engine. C1a, C1b and the release slice are left.
- **Engine** (`6e83a1dcb`, engine #664): F15 slice E2 (roadmap row 80, partly merged). `scan_baseline.sha256` pins the baseline bytes and `on_drift: fail` needs it (`config/scan_baseline_unbound`). E1 was engine #625.
- **Engine** (`2163ae1c8`, engine #668): DI-1b of the DRIFT plan (roadmap row 31, partly merged). The `post_scan.distribution` config block (`warn` only), gate glue and report section.
- **Engine** (`0a804752c`, engine #680): F24 slice 84-E2 (roadmap row 84, all slices merged). The lifecycle estimate covers generate-only and mixed jobs. 84-E1 was engine #635.
- **Engine** (`ff3d3efa0`, engine #681) and (`335c9fb23`, engine #683): F02 slices E1 and E6 (roadmap row 87, partly merged). One retry executor with S3 body resume; remote subset sources through local copies.
- **Engine** (`2b7bc8902`, engine #679) and (`cd45ad64a`, engine #682): F07 slices 82-E2a and 82-E3a (roadmap row 82, partly merged). Both are moves that change no behavior.
- **Engine** (`7fde782f3`, engine #693): F09 slice E0 (roadmap row 79, partly merged). `vault.py` becomes the `vault/` package, bodies unchanged.
- **Engine** (`9a2b3e836`, engine #665): row 24zm slice E1b (partly merged). A plain profile document floors every column the profiler did not flag at 10 rows.
- **Engine** (`584380a06`, engine #649) and (`074e7db9e`, engine #648): row 24zp E1 (all slices merged) and row 24zu E2 (partly merged). Datetime years in a plain fit snapshot are bottom and top coded; residual PII from name-hint-only detectors is graded by source identity.
- **Engine** (`05b5b2817`, engine #652): row 24zq slice E3 (all slices merged). Pure re-export `__init__` files are non-physical by rule.
- **Engine** (`f3c7ff9ab`, engine #645; `c67e60ac2`, engine #655): run warnings and every `QualityWarning` pass the evidence model, so out-of-core FK runs store an evidence record. No roadmap row.
- **Engine** (`bcb086de7`, engine #675; `69f19276d`, engine #674; `2c869dce6`, engine #666; `df8b15584`, engine #677): capped-worker fixes. One capped child env and memory-cap setter with a sentry; a Postgres connect fails as `source_unreachable` through libpq `connect_timeout`; BLAS thread pools stop in the capped child; the d4a perf test starts its worker with the capped env. No roadmap row.
- **Engine** (`73d38b12b`, engine #676): `redact_array` and `truncate_array` take the vectorized path for `large_string` input (plan row 24zy LARGE-STRING-FAST, which is not in the roadmap tables). `3ccde0bcf` (engine #669) splits `batch.rs` and `text_redact.rs` into submodules with no change in logic. `c4ee4d7bd` (engine #659) keeps the changelog link footer out of the 0.1.0 pin.

## 2026-11-17

- **Engine** (`80c1c9daf`, engine #622): F22 slice b2 (roadmap row 59, partly merged). `publish_unit` writes the vault first and binds the unit only after the vault is durable. W1 (Windows arm) is left.
- **Engine** (`e701c2826`, engine #639): SCAN-ML-MD M-2a2 (roadmap row 32c, partly merged). One not-installed message for a missing NER model on every surface, and the resolved NER model in the resume fingerprint. Earlier slices: M-1 (engine #616) and M-2a1 (engine #630). M-2a3, M-2b and M-3 are left.
- **CLI** (`d564f00f`, CLI #298): SCAN-ML C1 (roadmap row 32a, partly merged). `decoy models list`, `decoy models install ner`, a `models` step in `decoy setup`, the model-availability preflight in the shared gate and three `decoy doctor` rows. C2a is open as CLI #301.
- **Engine** (`a50dc56ce`, engine #633): F10 slice 78-E2 (roadmap row 78, partly merged). The synthetic probe and an optional `probe` field in `lock/v1`. 78-E1 was engine #618. The CLI slice 78-C1 waits on the engine release and repin.
- **Engine** (`50cc74827`, engine #631): F16 slice E2a (roadmap row 81, partly merged). The `policy` block models, selector grammar, 5-level precedence and `expand_policy`. Nothing calls it until E3.
- **Engine** (`2d01b91af`, engine #636): F07 slice 82-E1a (roadmap row 82, partly merged). The nested handler moved to `nested/_handler.py`; no handler line changed.
- **Engine** (`dd199b914`, engine #632): fit unflagged values slice E1 (roadmap row 24f, partly merged). A plain `decoy fit` snapshot floors every column the profiler did not flag at 10 rows, and is `distribution-snapshot/v2`. E0 was engine #609. C1 is left.
- **Engine** (`d3a160441`, engine #637): a one-time pre-GA exception that lets the release pin and the append-only reason check accept the corrected `rules` of eight connector reason codes. No roadmap row. Engine #634 (`f8eeec7c0`) repaired stale test fixtures after #624 and #630 in the same red-main fix.
- **Engine** (`db018471a`, engine #628) and (`80c381b5c`, engine #621): DUP-GUARDS slices G-E3 and G-E4 (roadmap row 24ze, partly merged). Draw-site call sites are keyed by function, not line, and release prep writes the DP certified rows.
- **Engine** (`98f281d6d`, engine #627): ENGINE-DOCS-TRUTH slice A-E1 (roadmap row 24za, closed). `docs/strategies.md` has a section for every mask strategy, and the keyed text names `mask_key`, not `job_seed`.
- **Engine** (`9df5582b2`, engine #620): FAKER-POOL-DISTINCT slice Z-E1 (roadmap row 24z, partly merged). `--post-validate` reports faker collisions per column. Z-C1 (CLI text) is left.
- **CLI** (`55cd4a05`, CLI #299; `419572a2`, CLI #302): GEN-CATALOG slices GC1 and GC2 (roadmap row 24s, partly merged). `decoy list generate-types` and `faker-types`, and six industry generate starter templates. GC3-E is open as engine #643.
- **CLI** (`7dcd32c5`, CLI #210; `b1478867`, CLI #214; 2026-11-16): LIB slices L1c.2 and L1d (roadmap rows 35 and 34, both closed). Earlier on 2026-11-15: L1b.3 (CLI #206, `f9f6b680`) and L1c.1 (CLI #209, `36d83877`). CLI #215 and #219 (L4a, L4b) are open.
- **CLI** (CLI #306, #307): CLI V1 journey and QA checklist exit column (roadmap rows 75 and 92a). `docs/qa/cli-v1-journey.md` holds twelve steps, CJ-01 to CJ-12, each with one e2e test and an exit code read from the document. CJ-12 stays an expected failure until row 61. Every one of the 204 checklist checks now names its exit code per command, and a sentry fails on a wrong cell count, an unknown code, a broken id sequence or a fixture value in a check cell.
- **Engine** (`68a0c1a47`, engine #626) and **CLI** (CLI #305): WF-R tombstones (roadmap row 17, closed). The three `WORKFLOW_*` reasons keep resolving and carry `deprecated_in=UNRELEASED` with a live replacement. Two explain-topic tests keep the old guide pointer and the workflow codes out of `decoy explain`.

## 2026-11-16

- **Engine** (`733a9e62a`, engine #607): F22 slice b1 (roadmap row 59, partly merged). Vault leaves are adopted durably and only the vault module issues a `VaultCommit`.
- **Engine** (`986793c27`, engine #558): F22 slice c2 (roadmap row 59, partly merged). The isolated subprocess route publishes through `publish_unit`, all-or-none. B1 and B2 (vault before output) and W1 (Windows arm) are left.
- **Engine** (`00e19eb10`, engine #604): RUN-STREAM E5a (roadmap row 63a, in progress). A lazy Parquet table with no sink reaches the collector lane, the collector spills under scoped engine scratch, and `bounded_admission` is the one bounded-route composition. E5b, C1l, C1a, C1b, C2 and M1 are left.
- **CLI** (`b272beb8`, CLI #255): CONFIG-EXPLICIT C1 (roadmap row 22, closed). Every CLI reader asks the engine to check source columns against the declared tables before it reads a data row, and a new sentry keeps new readers on that choke point.
- **Engine** (`9c666d6a1`, engine #603): F23 slice E2 (roadmap row 85, in progress). The `decoy-resume-run/v1` and `decoy-resume-table/v1` store records and `plan_resume`. The CLI slices wait on the engine release and repin.
- **Engine** (`b3117d5b3`, engine #599): REL-GATE slice RG-F1 (roadmap row 93, partly merged). `docs/frozen-surfaces.md` maps each frozen engine surface to its code and pinning test, a sentry checks it, and the `PipelineConfig` and `RunResult` JSON schemas are snapshotted.
- **Engine** (`4157ead6`, engine #541): F22 slice c1b (roadmap row 59, partly merged). Every route publishes through one all-or-none `publish_unit`, with reconcile and restart recovery. Slice c2 followed (engine #558).
- **Engine** (`2cce9c40`, engine #602): SCAN-ML M3a (roadmap row 32a, partly merged). Classifier and NER hits go into the pre-scan record. M3b waits on INIT-WIZARD E1.
- **Engine** (`368b3157`, engine #601): RUN-STREAM E5 (roadmap row 63a, in progress). A plain `auto` run reads lazy inputs whole when routing cannot stream them.
- **Engine** (`bcec31f7`, engine #522): F25 protected scratch stack (roadmap row 58, left open), merged as one unit. Engine #500, #502, #505, #507, #509, #513, #516 and #518 were closed into it.
- **Engine** (`12c2b8c3`, engine #532): F22 slice c1a (roadmap row 59, partly merged). The sink state table, and the write half split out.
- **CLI** (`39e60d26`, CLI #285): roadmap date fixes. **CLI** (`d27807b7`, CLI #284): post-1.0 plan, every V2 item classed 1.x or 2.0.
- **Engine** (`32ab8044`, engine #512): SCAN-ML M4 (roadmap row 32a, partly merged). Model findings join the post-scan. The post-scan report is now `post-scan-integrity/v3` (owner ruling 2026-11-16); the verdict reader still accepts v2. M3 is not on main yet.
- **Engine** (`dde37ca4`, engine #521): F22 slice A3 (roadmap row 59, partly merged). `publish_unit` judges and binds a publication unit under the destination lock.
- **Engine** (`1c8e413c`, engine #496): F22 slice A2 (roadmap row 59, partly merged). The v1 publication descriptor codec and receipt types.

## 2026-11-15

- **CLI** (`074e6256`, CLI #281): MAC-V1b (roadmap row 90, partly merged). The signer writes `.sshsig` sidecars with `ssh-keygen -Y sign` and checks the pinned key forms in `install.sh`. MAC-V1a, the verifier that stock macOS runs, is still open.
- **CLI** (`6a3adca5`, CLI #278): `decoy scan diff --strict` exits 4 on drift, the same code `decoy ci check` returns (REL-GATE plan Q8 (a), row 93). The flag is unreleased, so this sets the code.
- **CLI** (`06cf2cd7`, CLI #280): proportionality audit rows 24zi to 24zl added to the roadmap (not started). The 2026-11-15 audit report is in `docs/records/`.
- **CLI** (`d36ba1e4`, CLI #279): REL-WEB RW-C2a (roadmap row 91, partly merged). The update host moves to trydecoy.com, and pinned bundles resolve from GitHub releases under `DECOY_BUNDLE_BASE`.
- **Engine** (`a7f278eb`, engine #489): F22 slice A1b (roadmap row 59, partly merged). Publication units publish durably under a lock.
- **CLI** (`5f642e0f`, CLI #275): REL-GATE slice RG-R (row 93, partly merged). Release-readiness template and `scripts/release/readiness_check.py`. `--release` stays red until counsel confirms the licensor name.
- **CLI** (`de4cdeea`, CLI #277): REL-GATE slice RG-S (row 93, partly merged). `packaging_tools.candidate` writes `SHA256SUMS` and `candidate.json`, and `smoke_install.py` smokes a signed candidate on the host.
- **CLI** (`73482905`, CLI #276): REL-GATE slice RG-L, CLI half (row 93). Versioning policy rewritten; FSL-1.1-ALv2 in the license and install wording.
- **Engine** (`72ff5089`, engine #600): REL-GATE slice RG-L, engine half (row 93). The README says the engine ships inside the CLI bundle in V1.
- **CLI** (`e716f445`, CLI #274): REL-GATE slice RG-F3 (row 93, partly merged). `scripts/release/launch_pin_check.py` checks the engine pin against the engine tag.
- **CLI** (`4db0ec88`, CLI #273): REL-GATE slice RG-F2, CLI half (row 93, partly merged). Frozen-surface map and `--json` shape snapshots.
- **CLI** (`4f5887f3`, CLI #272): REL-WEB RW-C1 (roadmap row 91, partly merged). The update check sends a fixed header set and follows no redirect.
- **CLI** (`a2db34d9`, CLI #270): REL-GATE slice RG-X (row 93, in progress). `run --all` and `decoy ci` now use one exit-code order, 5, 3, 1, 6, 4, 2, 0, from `decoy.cli.exit_codes`; `run --all` keeps a child's exit 6. A crash still exits 1, now under a named constant, and the README and `decoy explain exit-codes` list 130 for Ctrl-C. A sentry keeps both docs in step with the code.
- **CLI** (`1825e45a`, CLI #269): CLI-QA-CHECKLIST (roadmap row 92a, now done). `docs/qa/cli-v1-checklist.md` lists each V1 CLI promise and its check by feature group, with a run template for the dated record. It is used after the V1 build, one complete group at a time; it has not been run yet.

## 2026-11-14

- **CLI** (`0d8f5b91`, CLI #253): PROJECT-LAYOUT P9 (roadmap row 24t, still partly merged). Side files and reports follow the run folder. P10 is in review as CLI #256.
- **CLI** (`ba7cdc7c`, CLI #252): SUB-RUN C1 (roadmap row 57, now closed). `decoy run` applies the subset block, and `--no-subset` turns it off.
- **CLI** (`49dac61a`, CLI #254): DUP-DEFECTS C1 (roadmap row 24zd, now closed). End-to-end tests prove the duplicated-logic fixes through the CLI.
- **CLI** (`1828b808`, CLI #250): PROJECT-LAYOUT P7 (roadmap row 24t). `decoy init` writes pipelines into the project, with paths relative to the YAML.
- **CLI** (`8477b345`, CLI #248): PROJECT-LAYOUT P8 (roadmap row 24t, still partly merged). `decoy run` with no argument runs the project's one pipeline; `decoy run --all` runs every pipeline in its own process and exits with the most serious child exit code.
- **CLI** (`f876137f`, CLI #246): DUP-FREEZE CL3 (roadmap row 24zf, partly merged). One config loader, one exception-to-exit-code map and one secret-ref rule.
- **CLI** (`41986152`, CLI #245): repin to engine 0.24.0. A vault is created only under its writer lock, a failed run removes only the vault it created, and layout refusals come before vault and source checks.
- **Engine** (`e5114b17`, engine #585): POSTSCAN-STREAM PS-11 (roadmap row 60, partly merged). Loader and transformed baselines are teed on the sequential route. It ships in the next engine release.
- **Engine** (`f298104e`, engine #584): LOADER-DROP (roadmap row 24zg, added and closed). A run refuses a declared table the plan would drop: `config/loader_table_undeclared` before any read, `config/declared_table_dropped` after the plan is built. It ships in the next engine release.
- **Engine** (`07763ff5`, engine #579): POSTSCAN-STREAM part PS-10 (roadmap row 60, still partly merged). Staged output is checked before commit on streamed routes. PS-11 merged later the same day (engine #585).
- **Engine** (`a43bdaa8`, engine #578): PS-9. An isolated post-scan block reports outcome `blocked`.
- **Engine** (`81dbfe00`, engine #570): PS-8. The post-scan gate runs on every no-sink route.
- **Engine** (`b1254eb1`, engine #581): DUP-FREEZE E1 (roadmap row 24zf, partly merged). One canonical JSON owner for digests and fingerprints. It ships in the next engine release.
- **Engine** (`8a77c8b6`, engine #580): DUP-FREEZE E3. One flag registry with two spelling sets.
- **Engine** (`61aa9d8e`, engine #577): DUP-FREEZE E4. One NER mismatch raise and one generated-at shape.
- **Engine** (`5aeda26f`, tag `v0.24.0`, engine #576): engine release 0.24.0. The CLI repin is CLI #245 (open).
- **Engine** (engine #563 `85d99c75`, #564 `de22841d`, #565 `63beef10`, 2026-11-13): DUP-DEFECTS E1 to E3 (roadmap row 24zd, now partly merged). One snapshot parse helper, one missing-cell rule for derived and formula, one text-type predicate for the chunked guard. All three are in 0.24.0.
- **CLI** (`af9b07fc`, #243): DUP-FREEZE CL2. One env flag rule and one JSON document writer.
- **CLI** (`50da81e6`, #244): DUP-FREEZE CL1. One error emitter and one `--json` error shape. CL0 (#242, `1f36e1ed`) merged 2026-11-13; CL3 is in review as #246.

## 2026-11-13

- **Engine** (`8c9c1162`, engine #562): F23 resume part E1 (roadmap row 85, now partly merged). Resume run fingerprint, `binding_digest`, the HMAC key check and the `decoy/resume_*` reason codes. Nothing calls it yet; it ships in the next engine release.
- **Engine** (`c86ca58d`, engine #559): B-6 vault core (roadmap row 12, now done). HKDF key derivation, scoped tokens and exclusive publish of the vault file. Pre-GA hard cut: no reader for old vaults. It merged after the `v0.23.0` tag, so it ships in the next engine release. The CLI handles `vault_exists` and `TokenVaultWriter.derivation_scope` at its next repin.
- **Engine** (`dac26109`, engine #548): POSTSCAN-STREAM part PS-7 (roadmap row 60). The post-scan gate core and its applies predicate.
- **Engine** (`efedebc0`, engine #560): perf test fix. The reorder memory tests pass the config to `run_fk_out_of_core`.
- **Engine** (`a2b2d77f`, engine #556, tag `v0.23.0`): engine release 0.23.0. The licence is FSL-1.1-ALv2 from this release. The CLI repin is CLI #233.
- **CLI** (`7850e217`, #233): repin to engine 0.23.0. The CLI now pins `decoy-engine==0.23.0`. Roadmap row 71 needs no further repin; row 67 (F34 E3 and its release) is done.
- **Engine** (`13778a0d`, engine #549): CLI-CLOUD part EC2a (roadmap row 64), merged 2026-11-12 and in 0.23.0. One S3 put path and SDK floors.
- **CLI** (`16135525`, #205): LIB part L1b.2 (roadmap row 34). The local record store core. L1b.3 remains.
- **CLI** (`048068a6`, #232): V2 rows VAULT-STREAM and TOKENIZE-CHUNKED added to `docs/roadmap/out-of-scope.md` (now in `docs/roadmap/post-1.0-plan.md`, as 1.x minor).

## 2026-11-12

- **Engine** (`7a0547ee`, engine #547): SAMPLE part SE2 (roadmap row 63, still partly merged). The sample stage runs inside the subset stage.
- **CLI** (`52a2399b`, #226): PROJECT-LAYOUT part P5 (roadmap row 24t, still open). Every command takes a pipeline name in place of its config path. P6 to P10 remain.
- **CLI** (`ae58f682`, #225): SAMPLE part SC0 (roadmap row 63). `decoy run --rows` refuses a run with quarantine on, and the quarantine path is passed to the engine explicitly.
- **CLI** (`62798427`, #224): CLI-QA1 part C3b (roadmap row 24e). `decoy validate` checks output targets. This is the last slice of `plan/cli-qa1`; the row stays open for its distribution-integrity QA items.
- **CLI** (`cf20450a`, #223): DELIV part CR (roadmap row 61). `decoy run --chunked` refuses `post_scan.integrity: true` with exit 1 instead of skipping the check.
- **CLI** (`8144c9e6`, #213): PROJECT-LAYOUT part P4 (roadmap row 24t). `validate`, `ci check` and `run` refuse an escaping or invalid output location before any source row is read; `--out-dir` is added.
- **Engine** (`c38f17cd`, engine #525): POSTSCAN-STREAM part PS-5 (roadmap row 60). Exact per-column facts for the post-scan column suite, computed over batches.
- **Engine** (`a8c6af73`, engine #519): DELIV part E1a (roadmap row 61). The delivery config and the pure `plan_delivery` decision.
- **Engine** (`105291d8`, engine #517): POSTSCAN-STREAM part PS-1 (roadmap row 60). Key facts and batch inputs for the streamed post-scan.
- **Engine** (`12bd94bf`, engine #515): SUB-RUN part E1 (roadmap row 57). Typed subset requests and one input seam.
- **Engine** (`426e6d05`, engine #491): CI-E2a (roadmap row 3). PR and nightly triggers are back for the lanes the self-hosted gate does not cover: certified-profile, DP and determinism on every PR; the full hosted suite, testflight and security nightly on main. `ci/required-jobs.toml` and `ci/unlaned.toml` say which job owns each test marker, and a lane sentry fails on a marker with no lane, a missing required job, or a PR workflow that cannot cancel its stale runs. One JUnit totals reader and one "the suite really ran" guard (`scripts/dev/junit_ran.py`). The substrate-matrix workflow is gone. Record: `E:docs/records/2026-11-12-ci-e2a-build.md`. Left: E2b, the merge-tier verifier.
- **Roadmap closures** (checked 2026-11-12 on engine main `426e6d05` and CLI main `e642d69`; every commit below is an ancestor of that main):
  - Row 24a VALUE-FREE-ERRORS, V1 slices: A1 and A2 engine #412 `bf15cd99` (2026-11-08), B1 engine #417 `38517493` (2026-11-09), A3 CLI #187 `ed39bb7d` (2026-11-11), B2 CLI #195 `68f90d0d` (2026-11-11). Both engine commits are in engine v0.22.0, which the CLI pins. B3 is V2 corrective.
  - Row 33 L1a-engine: L0.1 engine #403 `45553d7e` (2026-11-08), L0.2 engine #411 `942dae2d` (2026-11-08), L1a engine #444 `35370165` (2026-11-10); all in engine v0.20.0 and later. The CLI halves are row 34.
  - Row 5c CLI-MAC-TESTS: S1 CLI #110 `ec209ec6`, S2 CLI #112 `91d191b9`, bash 3.2 `gates.sh` CLI #115 `834ab996` (sentry `tests/sentry/test_bash32_compat.py`, no `mapfile` left in `scripts/`), last Mac failure CLI #118 `12fc2e62`, all 2026-11-08; engine mypy on macOS engine #404 `09376f24`. The last Mac full run (3108 passed, 0 failed) was on `12fc2e6`; none since.

## 2026-11-11

- **CLI** (`ac0cb686`, #204): F13 slice 5-v1, CLI half (roadmap row 73, now closed). One test, `tests/sentry/test_mask_secret_ref_shape.py::test_vault_ref_is_refused_without_echo`, runs `run`, `tokenize`, `unmask`, `report vault` and `decoy.mask()` with valid inputs and a `vault://` mask-secret reference carrying a canary path. Each refuses with `secret_provider_unknown` and the constant text in console, `--json` and `--verbose` modes, the canary appears in no output, and no file under the test directory changes. No logic changed. Closeout record `docs/records/2026-11-11-f13-5v1-closeout.md`: the six CLI F13 test modules, 192 passed on the Mac at engine 0.22.0.
- **Engine** (`c96e2855`, engine #487): F13 slice 5-v1, engine half (roadmap row 73). `docs/security/secret-providers.md` gains a Consumers section: every CLI keyed surface takes its secret from exactly one place and admits it once; `file:` first, `env:` for CI, `vault://` refused with constant text (direct adapters are row 83); platform provider injection is parked with Platform V1. Docs only.
- **Engine** (`0651d215`, engine #486): tooling. A main push skips the self-hosted gate only when its tree hash equals the head tree of a recent green owner dispatch of the gate in `full` mode with both shards passed (`scripts/dev/gate_tree_proof.py`, a hosted `tree-proof` job). Any other case, or a failed lookup, runs the gate as before. Manual dispatch takes `mode: baseline|full`. CI only.
- **CLI** (`a4109afe`, #200): PROJECT-LAYOUT part P3 (roadmap row 24t, still open). In a project with a `decoy.yaml` marker, `decoy run --evidence-out` records pipeline, source and output paths relative to the project root and adds `path_base: "project"`; paths outside the project, and every path without a marker, stay absolute. Sources are fingerprinted at the file the run read and outputs at the placed file in the run folder. `decoy report verify` and `decoy ci check` read manifests through one reader: a project manifest resolves from `report verify --project` or the marker above the manifest, never from `DECOY_PROJECT` or the working directory, and every stored path goes through one resolver, `resolve_manifest_path`, held by the AST sentry G-ONE-MANIFEST-PATH (with a registered allowlist for entries forwarded to helpers). A path that leaves the project, a manifest bound to another project, or a manifest with the wrong `schema_version`, `path_base` or field types is refused, naming the field but not its value. `report diff` now reads output formats from the resolved path. Logged to V2 under the V1 bar: V1-1 provenance (a manifest copied to the same relative place in another project binds to that project's files, since the marker has no project id). Next: P4 to P10; the engine slices E1 and E2 merged on 2026-11-09 (engine #423, #426).
- **Engine** (`a0338ea7`, engine #480): LAYOUT part E3 (roadmap row 7). An import-linter layer contract for the engine (`.importlinter`, 6 tiers, 42 measured ignores) and its sentry, run only in `.venv-layers` through a new `gates.sh` layers step and a layers-gate CI job. import-linter is a separate `layers` extra, so the certified install is unchanged.
- **CLI** (`f1f9a58e`, #199): LAYOUT part C3 (roadmap row 7, now closed). The CLI import-layer contract (7 tiers, 18 measured ignores, the flat `src/decoy/cli/` placed as one unit) and its sentry, with the same `.venv-layers` gate step and CI job; `requirements-dev.lock` gains import-linter 2.15. All six LAYOUT parts (E1 to E3, C1 to C3) are in.
- **CLI** (`6eb2080b`, #197): PROJECT-LAYOUT link fix (roadmap row 24t). The link to the last clean run is now `out/<name>/current`; the `LATEST` file is unchanged. `latest` collided with `LATEST` on case-insensitive filesystems (the macOS and Windows defaults), so on macOS the link was never made. A test that runs on every OS checks that no two names in the pipeline folder fold to the same name.
- **CLI** (`7d3ed44d`, #196): LAYOUT part C2 (roadmap row 7). CLI files under `src/`, `scripts/` and `packaging_tools/` are capped at 800 lines, with `report.py`, `scan.py`, `preflight.py` and `fit.py` exact and shrink-only; packages are capped at 25 modules, with `src/decoy/cli/` frozen at 30. The engine's E2 helpers are vendored and sha-pinned, the baseline ratchet checks a numeric `max`, and the sentry manifest walks nested folders. Tests only. Engine E3 (import layers) is next.
- **CLI** (`68f90d0d`, #195): VALUE-FREE-ERRORS part B2 (roadmap row 24a). CLI `re` validators anchor with `\Z` instead of `$`, so a trailing newline no longer passes, and a shrink-only ratchet holds `raise ... from None` inside an `except` block at its 37 sites. The scan is the engine's vendored `_defect_scan.py`. B3 (V2 corrective) waits for LAYOUT E3 and C3.
- **Engine** (`6e2e57bd`, engine #478): GEN-STRICT part D (roadmap row 24k, now closed). The generation sections of `docs/strategies.md`: a per-type option table that a test checks against `generate_option_catalog()`, which now lists `derived_aggregate`'s `op` and `column` as required (checked at plan compile, `required_at_plan`); the six missing-reference codes; and the memory floor with the `decoy validate` commands that check it. The editor schema allows `pooled` only on `faker`. The catalog and schema views moved to `config/_generate_option_catalog.py`. Not yet in a tagged engine release.
- **CLI** (`3f954118`, #193): PROJECT-LAYOUT part P2b (roadmap row 24t). `decoy run` and `decoy tokenize` write relative outputs into `out/<name>/<run-id>/` and move `latest` only after a clean run. The project marker and `latest` are read through one small-file reader that refuses symlinks, FIFOs and files swapped between check and open. Engine E2, then P3 to P10, remain.
- **Engine** (`66d0f879`, engine #479): LAYOUT part E2 (roadmap row 7). A package fan-out census: at most 25 modules per directory, with six oversize directories frozen at their count and shrink-only, one shared size and fan-out ratchet, and a numeric `max` in the baseline ratchet. Tests only. CLI C2 (the CLI census) is next.
- **Engine** (`82d00f4e`, engine #477): GEN-TYPES part E2 (roadmap row 24q). Generate columns take an `output_type`. Not yet in a tagged engine release.
- **CLI** (`475dfd30`, #192): QA-FK-FANOUT part C1 (roadmap row 24h, now closed). `decoy fit --fanout COLUMN` records per-key child counts in the snapshot, so a `reference` column with `distribution: fitted` keeps the source's fan-out shape. `--fanout` with `--epsilon` is refused before any read; success lines carry counts only.
- **CLI** (`b13f58bb`, #190): GEN-STRICT part C2 (roadmap row 24k). A generated table too large for memory exits 5 at `decoy validate` and before `decoy run` writes anything. Engine D (#478) is the row's last slice.
- **CLI** (`ed39bb7d`, #187): VALUE-FREE-ERRORS part A3 (roadmap row 24a). Every command that validates a pipeline config routes its errors through the engine's value-free parse: messages carry names and locations, never submitted values. B1 to B3 remain.
- **CLI** (`aa05799d`, #189): GEN-CLI part C3 (roadmap row 24o, now closed). Help panels with a sentry, `validate compile --explain` for generate tables, and explain topics `generation`, `transforms`, `pipeline` and `yaml`.
- **CLI** (`d0e8ba53`, #188): GEN-STRICT part C1 (roadmap row 24k). Tests hold `decoy validate` and `decoy run`'s pre-run gate to the engine's per-type generate-option checks: a typo, a negative or all-zero weight, an unknown faker type or locale, a bad formula and the other QA inputs fail `validate` with exit 1 and a code, and `run` stops at its gate before writing. No option value reaches the output. `decoy schema` closes every generate type.
- **CLI** (`3800e0ed`, #186): GEN-COND-CAP part C1 (roadmap row 24w, now closed). `decoy fit --joint-max-cells N` (default 25, at most 1000; without `--include-values` a raised cap works only on pairs of plain categorical columns). `fit` prints one `warning:` line per truncated pair on stderr and `--json` gains `warnings`; the run summary names the generation fallback. Names and counts only.
- **CLI** (`7e29f5fe`, #182): GEN-CLI part C2 (roadmap row 24o). `decoy run --rows N` previews a generate pipeline and writes nothing, `decoy init -o -` writes to stdout, and `decoy init <csv> --preset generate` writes a snapshot and config pair published together.
- **CLI** (`03b3dd2d`, #185): pytest-timeout in the `dev` extra with a 300 s per-test default, so a hung test fails with a stack dump instead of stalling a suite. No roadmap row.
- **CLI** (`990199ef`, #184): repin to `decoy-engine==0.22.0` (`v0.22.0`), with the certified DP stack moved to row `d5898d1f`. `validate` and `run` now refuse generate columns with unknown faker types or locales and formulas the runtime cannot evaluate (GEN-STRICT E2); `decoy fit` profiles every row it fits on in seconds.

## 2026-11-10

- **CLI** (`581844b6`, #183): LAYOUT part C1 (roadmap row 7). The CLI "Where Things Go" map in CODEMAP.md (five columns, 27 rows) and the path guard `tests/sentry/layout/test_codemap_paths.py`, which fails when a listed path does not exist.
- **Engine** (`8a9b5f00`, engine #471): CONFIG-EXPLICIT part E2c (roadmap row 22). `run_pipeline` and the other source readers refuse a source column or table the config does not declare, before any data row is read. Breaking pre-GA, no shim. Merged after the `v0.22.0` tag, so it ships with the next release.
- **CLI** (`3b44dbbb`, #180): PROJECT-LAYOUT part P1b (roadmap row 24t). The one project-root finder (`decoy.yaml` marker, `kind: decoy-project/v1`), pipeline names, claims, run ids and run folders, `out/.gitignore` and the `layout.*` codes. No command uses them yet.
- **CLI** (`6fafa5cd`, #181): CLI-QA1 part C1 (roadmap row 24e). No-profile compiles carry the config's relationships, so `validate compile` orders parents first and reports a relationship it cannot resolve; in `decoy validate`, a `capacity.plan_uncompilable` row that repeats a compile error becomes a warning.
- **CLI** (`ccddb1f6`, #179): RUN-SPLIT (roadmap row 95, now closed). `src/decoy/cli/run.py` (1737 lines) becomes the package `src/decoy/cli/run/`; behavior and help text unchanged. Owner-approved one-off split.
- **Engine** (`98670941`, engine #472): engine `v0.22.0` release prep and tag, same steps as 0.21.0 (#466). Folds five fragments (one breaking: GEN-STRICT E2) and adds two certified DP rows; registry pin unchanged at 1.22.0. Carries #465, #467, #468, #469 and #470. The CLI pins it since CLI #184 (`990199ef`).
- **Engine** (`45533490`, engine #467): GEN-TYPES part E1 (roadmap row 24q). New generate types `constant` and `distribution` (the `uniform` family only, from a new `dist` RNG family); the other families are refused at compile with `generate_option_value_unknown` and move to E1b.
- **Engine** (`bbc96dc8`, engine #470): QA-FK-FANOUT part D (roadmap row 24h). `docs/strategies.md` documents fitted reference fan-out and every refusal code. Docs only.
- **Engine** (`59a9b8f3`, engine #469): GEN-COND-CAP follow-up (roadmap row 24w). `MAX_CONTINGENCY_TOP_K` is exported from `decoy_engine.quality` for the CLI.
- **CLI** (`c9f97494`, #175): FIT-ROWS (roadmap row 24x, now closed). `decoy fit` reads at most `fit.max_rows` (default 1,000,000) or `--rows N`; a larger file is fitted on a seeded sample from the whole file and the summary says `fitted on N of M rows`. DP mode never samples, and `--rows` with `--epsilon` is refused.
- **CLI** (`cf4df70d`, #173): GEN-FIT-SHAPE part C1 (roadmap row 24l, now closed). `decoy fit` shows null rates in its summary and `--json` (`null_rates`), `report fidelity` adds a Nulls column when rates drift, and both CSV writers keep nullable integers whole.
- **Engine** (`defe89c2`, engine #465): GEN-STRICT part E2 (roadmap row 24k). One compile-time check, `check_generate_columns`, refuses generate configs that would fail or silently fall back at run (unknown faker provider, locale or kwarg, unevaluable formulas, forward `derived` references, `group_by` equal to `order_by`, a weights length mismatch). Value-free messages. Breaking: configs that used to fail at run or fall back now fail at compile.
- **Engine** (`4d18a3f8`, engine #468): whole-frame profiling speed (roadmap row 24f follow-up). Detectors, datetime sniffing, k-anonymity and the sentinel scan work on distinct values, so `decoy fit` can profile every row: 1M rows x 8 columns went from 298 s to 7 s with the same results.
- **CLI** (`40f464b1`, #176): GEN-UNIQUE part C1 (roadmap row 24m, now closed). `decoy run` and the pre-run gate map the engine's `uniqueness_impossible` refusal (a `unique` column or `unique_together` pair the data cannot satisfy) to exit 1 instead of 3, before any output is written, and `generation_budget_exceeded` to exit 5 (`--json` carries `error_kind: capacity`). Messages name the table and column with counts, never a value. New topic `decoy explain unique`.
- **CLI** (`e6bfb00c`, #177): QA-SCAN-REDACT slice C (roadmap row 24c, now closed). `decoy demo` writes `scan.json` through the engine's `profile_document`, so sensitive columns carry `[redacted]` and the file lists `redacted_columns`. `decoy explain security` and the `decoy.scan()` docstring say `decoy scan --output` files hold no cell values and a plain `decoy fit` snapshot withholds sensitive columns' values unless `--include-values` is passed. A new `io_policy` sentry fails if a CLI module writes a raw `profile.to_dict()`. No scan opt-in flag (plan Q1 (a)).
- **CLI** (`38cdb695`, #174): GEN-CLI part C1 (roadmap row 24o). Relative YAML source and output paths resolve against the config file's folder in `run`, `tokenize`, `validate`, `preflight`, `demo` and `decoy.mask()`, through one call that a sentry checks. `decoy run` prints engine warnings and per-table lines, warns when no seed is set, and refuses `--fidelity` (exit 1) on a config with no mask table. Breaking pre-GA: a relative path no longer follows the shell's working directory.
- **CLI** (`50c4af33`, #172): QA-DP-GATED CLI half (roadmap row 24g, now closed). `decoy fit --epsilon` reads only the CSV header, runs the column-name checks and the engine's `check_dp_fit_request`, then reads the body. An uncertified install exits 3 with a plain message and a hint that names `--include-values` first; bad `--epsilon`, `--delta` and `--numeric-bins` keep their codes.
- **CLI** (`02d278fd`, #171): QA-FIT-REDACT CLI half (roadmap row 24f, now closed). `decoy fit` writes its snapshot through the engine's `distribution_snapshot_document`, profiling the whole file: flagged columns keep no cell values, a number column keeps one range and a date column keeps years. The file carries `value_policy: flagged-redacted/v1` and `redacted_columns`, `fit` prints the withheld column names (never values), and `--json` gains both keys. `--include-values` keeps every column's values and prints a warning. Breaking pre-GA.
- **Engine** (`b63c0fb9`, engine #464): GEN-UNIQUE part D1 (roadmap row 24m). User guide for `unique` and `unique_together` on generate columns, including the refusals and `pooled`. Docs only; merged after the `v0.21.0` tag, so it ships with the next release.
- **CLI** (`488823ac`, #169): repin to `decoy-engine==0.21.0` (`v0.21.0`). Breaking for consumers: `contingency_top_k` takes only an int from 1 to 1000, and a cap above the default is refused in a plain snapshot when a joint column is numeric, datetime, freetext, empty or `high_cardinality`. Fitted number columns keep their shape through a quantile grid, so generated numbers differ from 0.20.0, and tables with two or more parents generate parents first. No CLI flag or verb changes.
- **Engine** (`57d44a9a`, engine #463): GATE-SELECT option C (owner 2026-11-10), no roadmap row. PR gates keep name-based test selection and always add a declared set of output-pinning tests (`scripts/dev/gate_pins.txt`: route baselines, determinism goldens, byte pins, the H-1 definition-owner test). A sentry fails if the list goes stale. The main full run stays the backstop.
- **Engine** (`b1e4aa9a`, engine #466): engine `v0.21.0` release prep and tag, same steps as 0.20.0 (#457). Folds the changelog fragments into the 0.21.0 section, bumps the version, pins reasons at 1.22.0, refreezes FR0 and adds two certified DP stack rows. One breaking entry: `contingency_top_k` takes only an int from 1 to 1000. Carries #456, #458, #459, #460, #461 and #462. The CLI pins it since CLI #169 (`488823ac`).
- **CLI** (`f32834bb`, #166): SCAN-MULTI part S1c.1 (roadmap row 27). `decoy scan` takes several files and writes one value-free scan-set core (`scan-set/v1`) through the engine's `scan_sources`. Saved scans load through one reader, `load_scan_set`, which accepts the new core or a strict legacy single-table file and drops every value-bearing member. `fields`, `show` and `diff` gain `--table`. CSV scans now need `--has-header` or `--no-header`. Breaking pre-GA: `--output` holds the value-free core, and `scan show` no longer prints top values or sentinels. S1c.2 has `--config`, `--table` on scan, `--column-names-file`, `--skip-integrity` and the integrity block.
- **Engine** (`1155b20c`, engine #461): GEN-COND-CAP part E1b (roadmap row 24w). When a conditional `statistical` column draws from its overall counts because the `condition_on` parent value was never seen in the fit, generation raises one `warning.generation_condition_parent_unseen` per column per run (registry 1.22.0). It reaches `on_warning` and `ExecutionResult.warnings` with counts only, no cell value. Generated bytes do not change.
- **Engine** (`fad62a69`, engine #459): RUN-STREAM part E3 (roadmap row 63a). `route_summary(quality_metrics)` returns a frozen `RouteSummary`: the route and why it ran, the native status, the input and output modes, and the thread and memory caps the route applied. A configured cap without evidence is never shown as applied. The caller passes the cap source labels. The out-of-core resources block also records `memory_cap_bytes`.
- **Engine** (`2aec8be8`, engine #462): main test fix after #460, no roadmap row. The definition-owner fixture lists `generation_order`, and the mixed-backend witness reads the new `_generate` return (tables plus warnings). Test seam and fixture only; assertions unchanged.
- **CLI** (`a14ed8ca`, #165): RUN-STREAM part C3 (roadmap row 63a). `decoy run --max-memory` and `--threads`, `DECOY_MAX_MEMORY` and `DECOY_THREADS`, and `$DECOY_HOME/settings.json` set the run's memory and CPU threads. Each key resolves on its own: flag, then environment, then the file, then `auto` (the engine's usable CPU count and its conservative out-of-core budget, 25% of the memory ceiling). A new `decoy setup` step writes the file atomically with mode 0600 under a settings lock, rereads it under the lock and keeps every other section and key, and replaces a file it cannot read. Reads accept unknown minors and keys and refuse an unknown major, a file over 64 KiB, a duplicate key, a wrong type or NaN with a value-free message (exit 1). `decoy doctor` lists each value with its source and warns when the file is group or world writable; `decoy run --json` gains a `resources` record. `--chunked` ignores the settings until C2.
- **Engine** (`4694c91f`, engine #460): GEN-CLI part E1 (roadmap row 24o). A new `base_dir` keyword on `compile_plan`, `run_config_only_checks`, `run_pipeline`, `run_pipeline_isolated`, `validate_plan`, the pinned compiles, the estimators and `capture_physical_plan_inputs` makes a relative `snapshot_file` and `quarantine.output_path` resolve against the config file's folder through one join, `fileaccess.config_relative`; without it nothing changes, and config hashes, plan bytes and output bytes are the same from any folder. `pin_and_check_snapshots` replaces the two duplicate snapshot blocks in compile. The generation fidelity gate hands a `QualityWarning` (`warning.generation_fidelity_below_threshold`) to a new `on_warning` keyword and into `ExecutionResult.warnings`, and it now also warns when one comparable column scores below `fidelity_warn_threshold` (default 0.8 unchanged; `detail` carries `trigger` and `below_columns`). `generation_order(config)` gives both generation routes one table order (parents first, then declaration and first-reference order), independent of `PYTHONHASHSEED`. `config.generate_option_catalog()` lists each generate type's options for CLI help. Codes are registered in 1.22.0 (`warning.seed_ignored_with_master_key` added for hosts to raise); no version change.
- **CLI** (`620290a4`, #164): repin to `decoy-engine==0.20.0` (`v0.20.0`), with the lock, CI, release smoke, fresh-install smoke and certified DP stack (fingerprint `725f80a3`) moved to it. Generated output goes through `decoy_engine.generated_table_to_pandas`, so a generated integer column that holds nulls writes whole numbers in CSV (`1001`, not `1001.0`) and `decoy.mask()` returns a nullable integer dtype; a masked int column with nulls in CSV output also prints `1` instead of `1.0`. The shape-and-privacy guide's DP page installs engine 0.20.0.
- **Engine** (`86a28222`, engine #458): GEN-NUM-SHAPE (roadmap row 24u). A fitted number column keeps its shape: one with 30 or fewer distinct values stores those values (`stats.exact_values`, each held by at least 10 source rows) and generates them at their source shares; one with at least 100 values and more than 30 distinct values stores a quantile grid (`stats.quantile_grid`) in place of ten equal-width bins, so one extreme value no longer spreads rows across the range and skewed columns keep their median. Every interval and tail holds at least 10 source rows, and the snapshot loader validates the stored mass (capped at 2**40 rows). A redacted fit withholds both keys; snapshots fitted earlier generate as before. Reaches CLI users with the next engine release.
- **Engine** (`217ff0e8`, engine #456): GEN-COND-CAP part E1 (roadmap row 24w). `contingency_top_k` on the snapshot builders takes an int from 1 to 1000 (`quality.contingency_top_k_invalid` otherwise), and a cap above the default is refused in a plain snapshot when a joint column would hold raw values (`quality.contingency_top_k_kind_unsupported`). Dropped cells collapse into the joint's `other_count`. New public `snapshot_joint_warnings(doc, contingency_top_k=...)` returns one `QualityWarning` (`warning.fit_joint_cells_truncated`) per truncated joint, names and counts only. Registry 1.22.0. E1b waits on GEN-CLI E1.
- **Engine** (`fb28bb68`, engine #457): engine `v0.20.0` release prep and tag. Folds the changelog fragments into the 0.20.0 section with its breaking-for-consumers list and recertifies the DP stack (distribution-set fingerprint `725f80a3`). The CLI pins it since CLI #164 (`620290a4`).
- **Engine** (`53632b57`, engine #455): FID-RANGE docs follow-up (roadmap row 24v). The distribution-integrity guide `extending.md` marks QA defect C3 fixed by #454, and the plan moves to `docs/plans/2026-11-10-fid-range.md`. Docs only.
- **Engine** (`c15f1c37`, engine #454): FID-RANGE (roadmap row 24v). Numeric column similarity now divides the quantile error by the source interquartile range (p75 - p25) instead of the min-to-max range, so one extreme value no longer hides a wrong shape. When that range is 0 it uses p95 - p05, then max - min. A constant column scores 1 when the output quantiles match it and 0 otherwise, and the old 1.0 floor is gone, so scores no longer depend on the column's units. The report shape and method name do not change. Breaking: scores drop for skewed or drifted columns; re-check `fidelity_warn_threshold` and policy floors.
- **Engine** (`1a5b36e5`, engine #445): GEN-C2 (roadmap row 24j). Generated numeric columns are typed int64/float64 instead of text: an unformatted `sequence` and a faker provider that returns an int or a float. `derived` arithmetic and `grouped_series` ordering now work on numbers, and Parquet output has numeric columns. A column stays text when its values cannot be proven to fit int64 or when a reader of it needs text (formula references, group labels, window anchors, statistical conditioning, a string comparison in a `derived` expression). New `decoy_engine.generated_table_to_pandas` converts with nullable integer dtypes; the CLI must switch to it when it takes this engine, or nullable integer columns print as `1.0`.
- **Engine** (`97a1cbbd`, engine #442): RUN-STREAM part E1b (roadmap row 63a). `decoy_engine.detect_usable_cpus` moves the platform's cgroup-aware core count into the engine (tightest cgroup v1 or v2 quota, capped by CPU affinity). `run_pipeline(out_of_core_threads=...)` caps the DuckDB threads of the out-of-core route, and DuckDB thread sizing uses usable CPUs instead of `os.cpu_count()`; the applied settings are returned in `quality_metrics["resources"]["out_of_core"]`. `resolve_conservative_ooc_budget_bytes` returns 25% of the memory ceiling, and the memory budget now finds its cgroup through mountinfo. Registry 1.21.0 adds `runtime.cpu_detection_failed`. The CLI half waits for the engine release.
- **Engine** (`35370165`, engine #444): LIB part L1a (roadmap row 33). `decoy_engine.records` holds the shared `decoy-record/v1` envelope with one canonical JSON form and content-addressed ids, a kind registry (`evidence`, `run-result`, `sample-run/v1`, `scan-set`; `publication` and `checkpoint` reserved), the `decoy-library-export/v1` codec and the `decoy-job-log/v1` header and reader. An unknown kind or a later major decodes to an opaque record or `RecordNeedsNewer`. Registry 1.20.0 adds `runtime.record_invalid`, `runtime.record_corrupt`, `runtime.record_kind_reserved`, `warning.library_write_failed`, `warning.job_log_write_failed`, `warning.library_degraded` and `warning.library_delete_skipped`. The CLI halves (L1b on) wait for the engine release and repin.
- **Engine** (`1c0d3553`, engine #448): FK-FANOUT part E2a (roadmap row 24h). A `reference` column with `distribution: fitted` has its `snapshot_file` read once and pinned in the plan. Compile, `run_config_only_checks` and `plan_from_yaml` refuse a fitted column with no `snapshot_file`, an unreadable snapshot, no fan-out for the source column (every DP snapshot), an invalid fan-out block, or `weights`, `min_per_parent` or `max_per_parent` set. One wrapper, `check_generate_snapshot_columns`, runs the statistical and fitted checks at all three sites. No registry change.
- **Engine** (`dd9a4e4c`, engine #453): distribution-integrity developer guides under `docs/distribution-integrity/` (index, statistical generation, snapshot and fidelity, differential privacy, extending), re-checked against main. `extending.md` lists the QA defects fixed on main and points the open ones at roadmap rows 24u, 24v and 24w. Docs only.
- **Engine** (`cfef8a6e`, engine #452): FK-FANOUT part E2b (roadmap row 24h). A fitted `reference` column gives each parent a child count drawn from the fitted degree histogram in the pinned snapshot, in place of independent uniform picks; the column takes the whole-table route. A fitted column with no pinned fan-out stops with `plan.reference_fanout_missing`, and child rows against an empty parent pool stop with `plan.reference_parent_pool_empty`. Other distributions generate the same cells as before. Merged before E2a (#448).
- **Engine** (`5c24a75e`, engine #450): REG-RELEASE part E1. Changelog fragments: a PR that changes behavior adds one `changelog.d/<slug>.md` file instead of editing `CHANGELOG.md`, which keeps an empty `[Unreleased]` heading. Release prep compiles the fragments into the dated section with `scripts/release/stamp_release.py` and deletes them; a release is refused while fragments remain. PRs get a fragment check. E2 (registry stamping at release) waits on owner question R1.
- **Engine** (`f3816b81`, engine #441): CONFIG-EXPLICIT part E2a (roadmap row 22). The declared-columns module (`source_columns`, `declared_columns`, `check_columns_declared`, `prepare_declared_sources`) and the `config_explicit` codemod modes `declare-columns` and `source-schema`. Registry 1.19.0 adds `source_file.undeclared_column` and `source_file.undeclared_table`. No run route calls the check yet, so runs are unchanged.
- **Engine** (`937d9e53`, engine #446): GEN-UNIQUE part E2 (roadmap row 24m). `unique: true` works on faker, categorical and reference generate columns, and a table can declare `unique_together` column pairs. A domain too small for the row count is refused with the E0 codes. Faker retries reseed and stop at 1,000 attempts for each row. Nested values (such as dict parents) are matched by equality. Unique plans run resident; the pinned route refuses `unique_together`. Columns without `unique` generate the same cells as before.
- **Engine** (`125f479b`, engine #447): SIZE-CEIL (roadmap row 7, owner rule 2026-11-10). Module-size pins are ceilings: each census entry is the file's lines plus 20, capped at 700, and a ceiling more than 40 above the file fails until it is lowered. Files already over 700 stay exact and may only shrink. Test-only.
- **Engine** (`e82b89b8`, engine #451): main fix. The H-1 owner fixture lists `parent_keys` (added by #440) under its owner file, so the wave-b owner coverage test passes again.
- **Engine** (`d43e2845`, engine #449): main fix. Two r3 route baseline scenarios re-pinned for the `value_similarity` and `missing_value_similarity` keys #438 added; no existing value changed.

## 2026-11-09

- **Engine** (`fbc42f14`, engine #439): RUN-STREAM part E1a (roadmap row 63a). `run_pipeline(execution_mode="stream")` is a strict switch: a strict preflight either confirms the run can stream or refuses it with `runtime.streaming_unavailable`. Registry 1.18.0 adds that code. There is no size threshold.
- **Engine** (`9257cdff`, engine #443): CI. A push to a feature branch runs a fast hosted check (environment, ruff, format, mypy, sentries). The self-hosted gate runs on dispatch (impact-selected tests in 2 shards; the baseline reruns only the branch's failures) and on main pushes (full suite in 2 shards). Owner-approved 2026-11-09 to stop gate queueing.
- **Engine** (`79d5ded7`, engine #438): GEN-FIT-SHAPE part E3 (roadmap row 24l). `report fidelity` column entries gain `value_similarity` and `missing_value_similarity`, so null-rate drift lowers the score; DP snapshots report the null rate without scoring it. Six fidelity goldens re-pinned for the two new keys.
- **Engine** (`84f4290d`, engine #440): GEN-UNIQUE part E1 (roadmap row 24m). Groundwork for `unique` with nothing wired to it yet: config checks, the shared parent key list and one uniqueness refusal builder. A golden test pins that existing configs generate the same bytes.
- **Engine** (`35719f55`, engine #437): RUN-STREAM part E2 (roadmap row 63a). `CsvLazySource` reads CSV in chunks through the one CSV reader, checks the header before counting, and checks file identity around facts and batches.
- **Engine** (`6bdd4840`, engine #436): GEN-FIT-SHAPE part E2 (roadmap row 24l). The statistical sampler reads the snapshot's `cell_format` block: generated columns keep the source null rate (unless `null_probability` is set, `0` included), the freetext blank fraction, the decimal places (whole numbers come out as `int`) and the datetime resolution (day resolution emits `datetime.date`, Parquet `date32`). An all-null source column generates all nulls. A malformed block is refused with `plan.statistical_cell_format_invalid`. Snapshots without the block, and DP snapshots, generate the same bytes as before. The `gen.statistical_per_row` draw-site entry is re-pinned.
- **Engine** (`ad0e6683`, engine #435): GEN-UNIQUE part E0 (roadmap row 24m). Registry 1.17.0 adds `config.generate_unique_conflict`, `config.generate_unique_domain_too_small`, `config.generate_unique_unsupported` and `plan.pinned_unique_pair_unsupported`. Nothing raises them yet; E1 and E2 add the checks.
- **Engine** (`5a7f14dc`, engine #434): GEN-FIT-SHAPE part E1 (roadmap row 24l). `compute_distribution_snapshot(..., cell_format=True)` adds a `cell_format` block per column (decimal places, datetime resolution, blank count), and `decoy fit` writes it. The block holds counts and fixed names only, so redacted fits carry it for sensitive columns too. Generation reads it from E2.
- **Engine** (`881095b7`, engine #433): GEN-FIT-SHAPE part E0 (roadmap row 24l). Registry 1.16.0 adds `plan.statistical_cell_format_invalid`. The plan doc landed with it.
- **Engine** (`858e50a1`, engine #409): CONFIG-EXPLICIT part E1 (roadmap row 22). A CSV source must set `has_header`; without it validation fails with `source_file.has_header_required`. New `column_names_file` reads header names from a file through the file-access policy, capped at 1 MiB. `resolve_csv_dialect` and `build_profile_source` are file-access entry points. Registry 1.15.0 adds three config reasons. Pre-GA breaking: the physical plan hash moves for CSV configs; `pipeline_config_hash` and output bytes do not. Gate: Dennis GO, Codex GO at r2.
- **CLI** (`9f752825`, #151): CLI-QA1 part C5 (roadmap row 24e). `decoy run` reports only the paths it published. A chunked CSV stream that writes nothing is no longer counted as a written file. The card shows Tables, Rows and Files, and `--json` gains `tables`.
- **Engine** (`7b5f120d`, engine #431): the sentry ratchet counts permitted keys per site. Re-keying a site passes with a review line. Growth or a new site still fails.
- **CLI** (`a565bded`, #150): CLI-QA1 part C3a (roadmap row 24e). The `command` field in `--json` output says `validate compile` and `validate preflight`. A new sentry checks each `command` value against the visible command tree.
- **Engine** (`f118ee02`, engine #428): QA-FK-FANOUT part E1 (roadmap row 24h). The snapshot carries a fan-out degree histogram, with a decoder and a degree allocator. The fan-out block stays on columns flagged sensitive.
- **Engine** (`325703f3`, engine #430): GEN-STRICT part E1 (roadmap row 24k). A generate column accepts only the option keys its type reads, and static values are checked at config parse. A duplicate generate column name is refused.
- **CLI** (`d5ff37dd`, #149): CLI-QA1 part C2b (roadmap row 24e). Old-engine refusal texts for run, tokenize and `decoy.mask()` live in `_mask_secret_guidance.py`. A new sentry checks user-visible text for internal names.
- **Engine** (`9bc86d24`, engine #427): QA-FK-FANOUT part E0 (roadmap row 24h). Six fan-out reason codes. Compile and plan load refuse `distribution: fitted` on a reference column when the pipeline declares DP.
- **Engine** (`97545972`, engine #425): GEN-STRICT part E0 (roadmap row 24k). Nineteen value-free reason codes for generate-column options and plan checks.
- **CLI** (`6a175432`, #148): CLI-QA1 part C0b (roadmap row 24e). `validate preflight` records an uncompilable plan as a capacity FAIL with the engine code, not a traceback.
- **Engine** (`3b1b285d`, engine #429): CLI-QA1 engine part (roadmap row 24e). `decoy_engine.profile.profile_relationships_from_config` is public. Importing the engine attaches a NullHandler to its logger.
- **Engine** (`98551956`, engine #423): PROJECT-LAYOUT part E1 (roadmap row 24t). Optional `name:` on the pipeline config, one shared name rule, and the `config.pipeline_name_invalid` reason code.
- **Engine** (`67fe6d45`, engine #424): GEN-STRICT part E3 (roadmap row 24k). A resident generate run whose output cannot fit in detected memory is refused up front with `generation_budget_exceeded`, before any provider runs; `estimate_job_capacity` returns INSUFFICIENT for it. Skipped when a byte budget is set, when the plan streams to a bounded sink, or when memory cannot be detected.
- **CLI** (`4eb43a52`, #147): CLI-QA1 part C4 (roadmap row 24e). Report-mode fidelity no longer prints PASS beside a failing grade. `report integrity` lists each residual-PII finding. `decoy scan` shows reid risk as `x / 100`.
- **CLI** (`df418657`, #145): CLI-QA1 (roadmap row 24e). The root app turns an unexpected exception into one line, `error: internal error (<ClassName>)`, with exit 1. `--verbose` adds the traceback.
- **Engine** (`38517493`, engine #417): CLASS-SWEEP part B1. Sixteen internal `re` patterns end with `\Z` instead of `$`, so a trailing newline no longer matches; this includes the S3 endpoint check. `decoy_engine.reasons` exports `COUNT_KEYS`, `MAX_COUNTS` and `is_count`. Two new ratchet sentries keep both classes from coming back. Gate: Dennis GO, Codex GO; full suite 0 new failures; T1 on the main merge green.
- **Engine** (`24796b0f`, engine #421): GEN-C1 (roadmap row 24i). Generated columns with identical settings no longer repeat each other: each column's draw stream now derives from the job seed, the strategy config and the column identity (table plus column name). Output changes for existing seeds (accepted pre-GA). Lands before GEN-C2. Gate: Dennis GO, Codex GO.
- **Engine** (`3af398d5`, engine #420): QA-FIT-REDACT parts E1, E3 and E2 (roadmap rows 24f and 24g, engine half). `decoy fit` snapshots no longer carry raw values of sensitive columns by default: numeric ranges become one coarse bin, datetime bounds pad to whole years, categorical top values empty into `other_count`. The document carries `value_policy` and `redacted_columns`. Generation refuses sampling or `condition_on` that would read hidden values. `check_dp_fit_request` is public. `profile_row_cap=0` now raises. The CLI half is next. Gate: Dennis GO at r2, Codex GO at r3; T1 on the main merge 6643 passed.
- **Engine** (`1e8739ae`, engine #419): QA-FK-FANOUT part E1b (roadmap row 24h). The derived, formula and reference generators moved from `synthesize.py` to `_synthesize_derived.py`, byte for byte, with no behavior change. E0 and E1 are in review; E2b, E2a, D, R and C1 are to come. Gate: Dennis GO at r2, Codex GO; T1 9668 passed.
- **CLI** (`0e8ae59d`, #141): PROJECT-LAYOUT part P1a (roadmap row 24t). New `_atomic.replace_symlink` swaps a link under a temp name and renames it over the old one; the install link swap in `distribution/layout.py` uses it, so the G-ONE-ATOMIC-WRITER allowlist drops from four entries to three.
- **CLI** (`b03fb261`, #143): PROJECT-LAYOUT part P2a (roadmap row 24t). `owning_run(path, ref)` in `cli/io/_targets.py` lets `input_format` treat a file inside a run folder (`out/<name>/<run-id>/`, `latest` followed) as the declared target. No caller passes `ref` yet, so behavior is unchanged until P9.
- **Engine** (`368abe0e`, engine #422): SCAN-MULTI part S1b (roadmap row 26). The `scan-set/v1` document now carries integrity facts for declared relationships. Relationships are parsed through the value-free config parse (new `decoy_engine.config.parse_relationship_config`), and scan refusals are value-free. Ships with S1a in the next engine release; the CLI half (S1c) waits for the repin. Gate: Dennis GO, Codex GO, including the ratchet root-cause fix round; full suite on the stack head 0 failing; PR CI gate passed.
- **Engine** (`809c2218`, engine #416): F25 part S1a-0 (roadmap row 58). Stage directories and private stage files made through `RootedFileAccess` keep their owner bits under any umask (directories 0700, private files 0600). The scratch ownership check compares with the effective user id. Gate: Dennis GO, Codex GO; full suite 0 new failures; T1 on the main merge green; PR CI gate passed.
- **Engine** (`046887e9`, engine #414): SCAN-MULTI part S1a (roadmap row 25). `scan_sources` runs one scan over several sources and returns the new `scan-set/v1` document, with classified scan errors and masked suspect headers. Gate: Dennis, then Codex GO at r3; full suite 0 failing (+66 collected); PR CI gate passed.

- **CLI** (`6cff2cd`, #137): X7c part S3 (roadmap row 24, now DONE). The private-file sentry classifies every watched file sink in the CLI as private, staged, public or read; private writes must go through `_private_file`. Import aliases are resolved, a staged row must write the stager's temp path, and a swallowed chmod failure is red. Census: 48 watched sinks, 13 private entries. Gate: Dennis GO, Codex GO after 3 design fixes; full suite on the merge head 0 failing (3224 collected). The plan's S3 file list missed `tests/sentry/_baseline_sources.py`, which gained a `data_file` field.
- **CLI** (`99c400a`, #135): X7c part S2 (roadmap row 24). `validate compile --output`, the token vault and the `decoy.mask()` spool are written through `_private_file`: 0600 files, 0700 for a new vault parent; a compile write failure exits 3 with `atomic_write_failed`; `tokenize --vault` refuses a symlink at the vault path. Part S3 (sentry) is next. Gate: Dennis GO with fixes (applied), Codex GO; full suite on the main merge 0 failing (+37 tests).
- **Engine** (`44d6afe2`, engine #415): QA-SCAN-REDACT engine part S1 (roadmap row 24c). Scan documents no longer carry raw cell values (top values and sample text) for sensitive columns unless the caller opts in. The CLI half comes with the next engine repin. Gate: Dennis GO, Codex GO; T1 green; PR CI gate passed.
- **Engine** (`1bf9e7f8`, engine #418): QA-SHUFFLE-DET (roadmap row 24d). `shuffle` without `deterministic: true` drew from an unseeded generator, so two runs with the same config, seed and secret differed. It now draws from the mask key with the job seed and the table and column names bound in, and repeats across processes. Output changes once (pre-GA, owner OK); one new determinism golden. Gate: Dennis GO, Codex GO; full suite clean apart from one unformatted test file, fixed before merge; PR CI gate passed.
- **CLI** (`0fafd0a`, #132): X7c part S1 (roadmap row 24). Private output files are created and chmodded through one helper, `_private_file`, so every CLI write gets owner-only permissions the same way; staging temps no longer read the mode back. Parts S2 (move the remaining call sites) and S3 (sentry) are next. Gate: Dennis GO, Codex GO; full suite on the main merge 0 failing against the `b1a6350f` baseline (3,159 collected, +25).

## 2026-11-08

- **Engine** (`bf15cd99`, engine #412): VALUE-FREE-ERRORS parts A1 and A2 (roadmap row 24a). One converter turns every config error into problem codes that name keys, tables, columns and files but never a data value or secret; new exports `ConfigProblem`, `ConfigRuleError` and `parse_pipeline_config`. Part A3 (route wiring, engine release) is next. Gate: Dennis GO, Codex GO; full suite at the tested head 37,125 passed, 0 failed, 0 new failures (42,429 collected, +53).
- **Engine** (`c9064cbc`, engine #413): the test gate keeps its pytest temp root under a short /tmp path and the shared `root_dir` fixture uses the short path, so the file-access socket test no longer fails under a long temp path. Test tooling only. Gate: Codex to the cap, Dennis verified the fix (GO with fixes, applied); full suite 37,089 passed, 0 failed, 0 new failures.
- **Engine** (`942dae2d`, engine #411): LIB L0.2, run row dirs use the issued scratch root. Every row directory the engine creates during a run now comes from the one scratch root issued for that run, so out-of-core and isolated runs leave no scratch folder behind after success or failure; caller-named roots are left alone. Unblocks the F25 protected-scratch build (roadmap row 58). Gate: Dennis GO, Codex GO (lib-l02-r1), PR CI gate passed; full suite on test-6 at the tested head 37,089 passed, 0 failed, 0 new failures against the main baseline (42,393 collected, +17).
- **Engine** (`a5eb66e2`, engine #408): derived expression visibility (roadmap row 13). A `derived` expression reads exactly the columns it names, by real name; a failure on one row no longer echoes the cell value; a source with repeated field names is refused at every public entry with `duplicate_source_field_names`. Declared sources are read under their own config key through one helper, and one shared scan finds repeated names at each boundary. Registry 1.9.0. Gate: Dennis BLOCK r1 (wrong file-access key at run entry), GO r2 and r3; Codex NO-GO r1 (design: a second scan, a flat test folder), GO r2. Full suite: one failure, an edit to a released CHANGELOG section, fixed before merge; a fresh main baseline is being written.
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
