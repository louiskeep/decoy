# Scan and detection

Status: current

Part of the roadmap: [ROADMAP.md](../../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

Rows keep their number from the pre-split track. A row number or section number that is not in a group file is a closed row or old section in the [snapshot](../../archive/2026-11-18-roadmap-before-split.md).

## 1.0

Blocks the 1.0 release.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 16 | NAME-REMOVAL E1 (engine part of the NAME-REMOVAL), registry 1.7.0 | engine | NOT MERGED; no (an identifier kept in the pre-split snapshot) on origin | NAME-REMOVAL re-cut plan (an identifier kept in the pre-split snapshot) `dfe7cc6a` | SUB-STOP |
| 27 | SCAN-MULTI S1c-cli: `decoy scan` over many tables (~690 lines) | CLI | IN PROGRESS. Plan passed 2026-11-06 (owner Q7-Q8 recommended). S1a and S1b are in engine 0.20.0, which the CLI pins since CLI #164. S1c.1 MERGED (CLI #166, `f32834bb`, 2026-11-10): `decoy scan` takes several files and writes one value-free scan-set core through the engine's `scan_sources`; saved scans load through one reader, `load_scan_set`; CSV scans need `--has-header` or `--no-header`. Next: S1c.2 (`--config`, `--table` on scan, `--column-names-file`, `--skip-integrity`, the integrity block), which waits on CONFIG-EXPLICIT E2 and C1 | `plan/scan-multi` | S1a and S1b release and repin; CLI-DIALECT; CONFIG-EXPLICIT for `--column-names-file` |
| 29 | SCAN-MULTI S3-cli: `--emit-config` and `--compare` (~720 lines including moved code) | CLI | Plan passed 2026-11-06 (owner Q7-Q8 recommended). Waits on LIB L2 and the S3-engine release and repin; SCAN-MULTI S1c.1 is in review as CLI PR #166 | `plan/scan-multi` | LIB L2 (in place of S1d); S3-engine release and repin; CLI-DIALECT |
| 32c | SCAN-ML-MD: make `en_core_web_md` the default NER model, with its own `NER_MIN_RATE` set by the owner's Q7 rule (measured 0.087 against the small model's 0.211; owner 2026-11-07). On the frozen corpus and the Synthea healthcare sample, md flags notes columns whose names appear in 1 cell in 4 or 1 in 5, which the small model misses, and drops the small model's 3 false flags on clinical description columns (drug and vaccine names, lab terms). Costs a larger pinned wheel (`NER_MODEL_WHEELS` hash) and more location hits on organization names. The slice re-measures on the frozen corpora plus a clinical-vocabulary negative set before setting the constant | engine | PARTLY MERGED. Plan `E:docs/plans/2026-11-17-scan-ml-md.md` on `plan/scan-ml-md`. M-1 MERGED (engine #616, `d57c41222`, 2026-11-17): a NER hit threshold per model (md 0.122, sm 0.211) and the md wheel pin. M-2a1 MERGED (engine #630, `612cdfd4b`, 2026-11-17): one model resolver for every NER surface. M-2a2 MERGED (engine #639, `e701c2826`, 2026-11-17): one not-installed message on every surface, and the resolved NER model in the resume fingerprint. Left: M-2a3, M-2b (md becomes the default) and M-3 (CLI install hints). Evidence in vault `handoffs/phase1/scanml-ner-model-comparison-2026-11-07.md` | none | SCAN-ML M1 merged |
| 56 | NAME-REMOVAL, CLI half: re-cut so CLI C0 vendors (an identifier kept in the pre-split snapshot), (an identifier kept in the pre-split snapshot), `slices-cli.json` and drops the platform S2c dependency; CLI V1 ships the new names | CLI | PARTLY MERGED. C1 MERGED (CLI #292, 2026-11-16): the retired name is gone from `decoy scan`, `decoy explain` and `decoy report integrity`, with a residual sentry. C1b MERGED (CLI #293): five scan test files renamed. C2 MERGED (CLI #304): the name is gone from `decoy init`, `decoy demo` and the `decoy-ci/v1` schema text. Left: C3 (comment-only edits, CLI sdist exclude, docs and diagram labels; it deletes the sentry's pending baseline) | from (an identifier kept in the pre-split snapshot) `dfe7cc6a` | R-c repin |
| PRE-SCAN-RUN | `decoy run` never executes a pipeline's `pre_scan` block: the config parses it, but neither the CLI run path (`src/decoy/cli/run/`) nor the engine run path reads it, so a pipeline that asks for a pre-scan runs without one and reports success. Pre-scan is part of the V1 pipeline baseline. Run it at run start through the same scan call `decoy scan` uses, with its report in the run record. Owner 2026-11-21 (go with recommended), found by the language write-up | CLI, engine | IN PROGRESS. Plan `C:plan/pre-scan-run` (`docs/plans/2026-11-21-pre-scan-run.md`). Built and in the final gate: E1 (engine #748: `pre_scan.on_findings`, the plan-hash input, reason codes, validated through the one config route) and E2 (engine #749: the pre-scan check, using the one ordered transform lineage). Left: the CLI run-start step and the run record | vault `30_Resources/Decoy-Language-to-Delivery.md` | none |

## Later (1.x)

Additive. Not scheduled until a 1.x release picks it up.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 30 | SCAN-LIB: scan snapshot library (`scan-set/v1` under `.decoy/`); the YAML references a snapshot as its baseline and the run hashes it into evidence | engine, CLI | mostly delivered by S1a (`scan-set/v1`), LIB L2 (snapshots in the library) and S3 (`scan_baseline`); the run-evidence hash is the remainder; confirm at their plan GO | none | S1a, L2, S3-engine |
| 31 | DIST-INTEGRITY: opt-in pre-scan distribution capture plus a post-scan check within n%; a breach blocks in strict mode | engine, CLI | PARTLY MERGED. DI-1b MERGED (plan `plan/drift`): the `post_scan.distribution` config block (`warn` only), the gate glue and a `distribution` section in the v3 report (in engine 0.28.0). Left: DI-2 (the `on_breach` decision and a blocking mode) and the CLI half | none | SCAN-LIB, POSTSCAN-STREAM |
| 32 | DRIFT: opt-in pre-scan drift check at run start against a SCAN-LIB baseline (`on_drift: warn` or `fail`) | engine, CLI | NOT STARTED | none | SCAN-LIB |
| 80 | F15: bound-baseline object, strict-drift publication block; scan-diff moves into an engine `scan-diff/v1` | engine, CLI | PARTLY MERGED. Plan `plan/f15-bound-baseline`. E1 and E2 MERGED: `scan_baseline.sha256` pins the baseline bytes, `on_drift: fail` needs the digest, and the drift verdict reads a bound baseline (in engine 0.28.0). Left: the slices after E2 and the CLI half | none | NAME-REMOVAL; SCAN-LIB |

### Candidates with no plan yet

Non-breaking ideas, so v1+ by rule. A candidate becomes a row in the table above when a release picks it up.

| Item | Source | Why it does not break |
|---|---|---|
| DETECT-PROFILES: Detection settings profiles: named sets of detection settings (detectors, overrides, thresholds, ML on or off) that a pipeline picks by name. | owner, 2026-11-05 | New optional config key; pipelines without it are unchanged. |
| Value-based FK discovery (SCAN-MULTI plan section 7; DuckDB #14 is the same idea) | Post-V1 on demand (old list) | New scan option; declared relationships keep priority. |
| X-09 Secrets detection | Expansion candidates X-01 to X-25 | New detector. |
| 14 Relationship (PK and FK) discovery (same idea as value-based FK discovery) | DuckDB opportunities (vault `v2/duckdb/`, platform `plan/v2-duckdb-plans`) | See above. |
| 18 Trend and drift analytics across scans and reports | DuckDB opportunities (vault `v2/duckdb/`, platform `plan/v2-duckdb-plans`) | New report. |
| DUP-DEFECTS A6: `fromisoformat` with `Z` on Python 3.10 | ROADMAP row 24zd, `E:plan/dup-defects` section 13 | A hand-made profile that is refused with exit 1 today is accepted. |
| Record the detector set version a scan ran with | compatibility contract read, 2026-11-18 | New field. It lets a better default detector arrive later as a named set a config selects. |

## Maintenance

No user-visible change. Merges at any time and never gates a release.

None.

## Notes carried from the track

SCAN-MULTI plan: `E:docs/plans/2026-11-05-scan-multi-fk-discovery.md` on engine branch
`plan/scan-multi` `9b7cd9ab`. Dennis GO-WITH-FIXES; in a fix round. No FK inference in V1 (users
declare relationships; value-based FK discovery is parked for 1.x, as a minor release; [post-1.0-plan.md](../post-1.0-plan.md)). Columns with no PII default to
`redact` in the starter YAML.
