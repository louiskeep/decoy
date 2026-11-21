# Fit and generate

Status: current

Part of the roadmap: [ROADMAP.md](../../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

Rows keep their number from the pre-split track. A row number or section number that is not in a group file is a closed row or old section in the [snapshot](../../archive/2026-11-18-roadmap-before-split.md).

## 1.0

Blocks the 1.0 release.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 24f | QA-FIT-REDACT (distribution-integrity QA, owner 2026-11-08): `decoy fit` without `--epsilon` keeps no raw values for PII-flagged or high-cardinality columns in the snapshot unless an explicit opt-in flag is passed (same rule as row 24c), and its message points at `--epsilon`. Leak class, blocks V1. Added 2026-11-10 (DI models QA 2026-11-10 H6, H7; the leak still shows on engine `5c24a75e` and CLI `9f603536`): numeric `min`/`max`, labels with a count of one, and short free text (30 or fewer distinct strings, now classed categorical) are not kept raw in a plain snapshot. Engine #420 covers profiler-flagged columns only, and an unflagged note column kept all 30 strings | engine, CLI | PARTLY MERGED, C1 in review (reopened 2026-11-16 for the 2026-11-10 additions H6 and H7). E0 MERGED (engine #609, `aa729497a`, 2026-11-17): one reader for stored datetime buckets, no writer change. E1 MERGED (engine #632, `dd199b914`, 2026-11-17): a plain fit snapshot floors every column the profiler did not flag at 10 rows (`MIN_RELEASE_COUNT`); rare labels fold into `other_count`, numeric bounds are top and bottom coded, datetime years fold into contiguous ranges, a column too small to floor is withheld and listed; a plain snapshot is now `distribution-snapshot/v2`. E2 MERGED (engine #732, 2026-11-20): a plain numeric histogram no longer holds a bin of 1 to 9 rows; the bins are recoded globally. Engine 0.28.2 carries #732 and the CLI pins it (CLI #369). C1 (CLI `--numeric-bins` on the plain fit, option text and guides, CLI #347) is in review; it closes H6 and H7 on the CLI side. Year top and bottom coding is row 24zp. Merged earlier: Engine MERGED (engine #420, `3af398d5`, 2026-11-09): fit snapshots hide raw values of sensitive columns by default. CLI MERGED (CLI #171, `02d278fd`, 2026-11-10): `decoy fit` writes its snapshot through the engine's `distribution_snapshot_document`, profiling the whole file; flagged columns keep no cell values, a number column keeps one range and a date column keeps years; the file carries `value_policy` and `redacted_columns`, `fit` prints the withheld column names (never values), and `--include-values` keeps every column's values with a warning. Engine half in `v0.21.0`, which the CLI pins since CLI #169 (`488823ac`, 2026-11-10) | DI QA report High 2; DI models QA 2026-11-10 H6, H7 | row 24c |
| 24n | GEN-REL (owner 2026-11-08, all V1): a date window anchored to a parent column; per-parent `derived_aggregate`; self-reference (`manager_id`) as a hierarchy, not a cycle; an empty parent fails under `orphan_policy: fail`; impossible or contradictory `min/max_per_parent` refused; weighted `reference` with no weights refused. Fan-out from a fit is row 24h | engine | PARTLY MERGED. Plan on `E:plan/gen-rel`. Slice 0 MERGED (engine #506, `7d2cd2dc`, 2026-11-12): pending reason codes and the release stamp. Slice 1 MERGED (engine #523, 2026-11-20): per-parent bounds are exact and honor `orphan_policy`. Open and gated as a stack: engine #546 (self-reference trees), #555 (windowed dates anchored to a parent row) and #561 (per-parent categorical mix) | [GEN QA report](../../records/2026-11-08-cli-qa-generation.md) High | row 24h |
| 24p | GEN-PROVIDERS (completeness audit, owner 2026-11-08): includes census item A9 (owner 2026-11-12): each identifier provider declares its real locale scope, with a guard test on the declarations; generation can use every masking domain provider (NPI, MRN, ICD-10, NDC, PAN, IBAN, CUSIP, EIN, SSN and the rest of the 34) and the correlated person and address composites (email matches name, ZIP matches state, sex matches first name, age matches birth date); an unknown provider name fails at validate. Existing code, reused from the masking registry, not copied | engine | PARTLY MERGED. Plan `E:plan/gen-providers` (slices E1, E2, E3). E1 MERGED (engine #661, `efeb56df8`, 2026-11-20): the `provider` generate type for the masking identifier providers, each provider's locale scope declared and guarded (A9), and an unknown provider name refused at validate. Left: E2 (composite handler refactor for the person and address bundles) and E3 (`sex` and `age` fields). Owner questions taken on the recommended answers under standing approval (2026-11-10): `type: provider`; per-provider options and `unique` are V2; `composite_custom` is refused; sex values are F and M | [GEN completeness audit](../../records/2026-11-08-generation-completeness-audit.md) Decision 1, 2 | row 24i, row 24k |
| 24q | GEN-TYPES (owner 2026-11-08): new generate types and options: `constant`; parametric `distribution` (normal, lognormal, uniform, exponential, poisson, beta, zipf), which makes the capability matrix's 12th type real; a weighted lookup list from a file; per-column output type (int, decimal(n), date, bool); conditional `derived` (`if()`) | engine | IN PROGRESS. Plan passed 2026-11-10 (`E:plan/gen-types`). E1 MERGED (engine #467, `45533490`, 2026-11-10): `constant`, and `distribution` with the `uniform` family only, drawn from a new `dist` RNG family; normal, lognormal, exponential, poisson, beta and zipf are refused at compile (`generate_option_value_unknown`) and move to E1b. Owner answer (recommended, standing approval, 2026-11-10): drop the families that are not portable instead of adding a per-architecture caveat. E1 is in engine `v0.22.0` (#472). E2 MERGED (engine #477, `82d00f4e`, 2026-11-11): `output_type` on generate columns. Next: E1b (more families) needs a portable-sampling design first; E3 MERGED (engine #501, `ee156764`, 2026-11-12): the `lookup` generate type. E4 MERGED (engine #490, `72b75489`, 2026-11-12): `if()` and lazy conditionals in derived columns. Left: E1b (more distribution families), which needs a portable-sampling design first | [GEN completeness audit](../../records/2026-11-08-generation-completeness-audit.md) A | rows 24i, 24j, 24k |
| 24s | GEN-CATALOG (owner 2026-11-08): a CLI command that lists every generate type and option, and every provider, from the engine's registries (no hand-kept list); one generate starter template per industry (healthcare, banking, insurance, retail, telecom, HR) | CLI, engine | PARTLY MERGED. Plan `C:plan/gen-catalog` (2026-11-17). GC1 MERGED (CLI #299, `55cd4a05`, 2026-11-17): `decoy list generate-types` and `decoy list faker-types`, read from the engine's live catalogs. GC2 MERGED (CLI #302, `419572a2`, 2026-11-17): six industry generate starter templates (healthcare, banking, insurance, retail, telecom, HR). GC3-E MERGED (engine #643, 2026-11-20): the public `code_set_catalog()`. Left: GC3 (CLI code-set listing), which waits on an engine release that carries #643 and the CLI repin | [GEN completeness audit](../../records/2026-11-08-generation-completeness-audit.md) C | rows 24o, 24p, 24q |
| GEN-WINDOWED-BATCH | Batch the `windowed_date` derive with the batched derive the pool sampler already uses, and vectorize the offsets and formatting. `windowed_date` takes about 87% of pure generation time (measured). The plan first decides whether the batch keeps the per-row bytes identical. V1, before the freeze (owner 2026-11-19, Q2). Record item F1 | engine | PARTLY MERGED. S1 MERGED (engine #718, 2026-11-19): `windowed_date` derives its row keys in one batch and parses, shifts and formats as vectors; output bytes are unchanged. Left: S2 (offsets from the batched index kernel), which changes bytes and has its own benchmark gate | plan `E:docs/plans/2026-11-19-speed-batch-f1-f3-f4.md` (branch `plan/speed-batch-f1-f3-f4`); record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.2 F1 | none |

Row 24n is split. 1.0 holds only the new failures (an empty parent under `orphan_policy: fail`, impossible settings). The new capabilities (a date window anchored to a parent column, per-parent aggregates, self-reference as a hierarchy) are Later.

Rows 24p, 24q and 24s moved here from Later on 2026-11-19. The 2026-11-08 owner decision made generate providers, types and catalog V1; the Later placement was drift (owner 2026-11-19, Q5).

## Later (1.x)

Additive. Not scheduled until a 1.x release picks it up.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 24r | GEN-INHERIT (owner 2026-11-08): a child column takes a parent row's attribute (`claims.state` = the member's state); conditional categoricals declared in YAML, not only from a fitted snapshot | engine | NOT STARTED. Plan passed 2026-11-10 (`E:plan/gen-inherit`); build not started | [GEN completeness audit](../../records/2026-11-08-generation-completeness-audit.md) B | row 24n |
| GEN-VECTOR-STREAMS | 1.0.x. Vectorize the generation `sequence`, `reference` and null-mask streams: numpy indices, one RNG call per batch. 2x to 5x on those columns (estimate). Output bytes must not change; if they do, the row goes back to the owner. Owner 2026-11-19, record item C2 | engine | NOT STARTED | record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.3 C2; plan not written | none |

### Candidates with no plan yet

Non-breaking ideas, so v1+ by rule. A candidate becomes a row in the table above when a release picks it up.

| Item | Source | Why it does not break |
|---|---|---|
| F46 reusable QA scenarios | Council features | New scenario compiler and case library. |
| F48 statistical synthesis | Council features | New opt-in backend and evaluation; existing generation unchanged. |
| X-14 Joint-distribution synthesis (Gaussian copula) | Expansion candidates X-01 to X-25 | New generation method; existing configs unchanged. |
| X-15 Multi-table synthesis | Expansion candidates X-01 to X-25 | New generation method. |
| X-16 Generate from a schema | Expansion candidates X-01 to X-25 | New source of generation specs. |
| X-17 Edge-case test data | Expansion candidates X-01 to X-25 | New generators. |
| X-18 Sequential and event data synthesis | Expansion candidates X-01 to X-25 | New generation method. |
| A certified DP stack for normal users (a DP fit on a default install works) | ROADMAP row 24g | Turns the `dp_stack_uncertified` message into a success. Exit code 3 stays for the cases still refused. |
| GEN-PROVIDERS per-provider options and `unique` | ROADMAP row 24p | New optional keys on `type: provider`. |
| F2 follow-up: dirty generated output (nullable, NaN, nested) on the mixed route | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | Lifts a decline. |
| Generate columns on a masked table: a masked table declares generate columns that add new columns beside its masked ones (today a table is either masked through `columns` or generated through `generate_columns`, never both) | Owner, 2026-11-19 | New optional config on a masked table; existing configs unchanged. |

## Maintenance

No user-visible change. Merges at any time and never gates a release.

None.
