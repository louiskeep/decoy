# Masking, policy, vault and secrets

Status: current

Part of the roadmap: [ROADMAP.md](../../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

Rows keep their number from the pre-split track. A row number or section number that is not in a group file is a closed row or old section in the [snapshot](../../archive/2026-11-18-roadmap-before-split.md).

## 1.0

Blocks the 1.0 release.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 79 | F09: domain-version object, rotation and remap (engine); authenticated, versioned CLI token vault header (G9, 11.8) | engine, CLI | PARTLY MERGED. E0 MERGED: `vault.py` is now the `vault/` package, bodies unchanged (in engine 0.28.0). Its dependency is met: the B-6 core merged (engine #559, `c86ca58d`, 2026-11-13) and ships in engine 0.24.0. Plan gated 2026-11-15 (`E:plan/f09-domain-version`, `b5d59d96`; Dennis r1-r2, Codex GREEN); owner Q1-Q7 answered as recommended. E1 MERGED (engine #741, 2026-11-21): vaults are written as v3 with an authenticated, versioned header, and v2 vaults open read-only. Left: the CLI header | none | none (B-6 core merged) |
| FAKER-MIGRATE | Move the launch engine from Faker 40.23.0 to 40.31 before the freeze (owner 2026-11-18). Faker's name and data pools are not semver-stable, so the Faker release that ships in 1.0 fixes deterministic `faker` output for the life of 1.x; the provider fixes in 40.31 cannot ship later without a 2.0. Re-pin, regenerate the determinism goldens as one reviewed act, and re-certify the DP stack row. Snapshotting the pools so Faker can be upgraded freely is non-breaking and is a Later candidate | engine, CLI | PARTLY MERGED. S0 MERGED: a record of what Faker 40.54.0 changes on the engine (only the version pin test goes red). S1 MERGED: the Faker output lock under 40.23.0, so the later repin shows which provider and locale pairs move (not yet in an engine release). Left: S2 (the repin and moved goldens) and C1 (CLI repin) | `E:fix/faker-40-31-migration` (was planned as a replay after R1; see release gate D-4) | none; merges before row 93 |
| DATE-SHIFT-FORMAT | `date_shift` requires `date_format`, with a coded refusal when it is missing (owner 2026-11-19, Q4). `decoy scan` and `decoy init` fill it in. Today a `date_shift` without a format leaves the native routes and runs in pandas full-frame. The refusal is new, so it lands before the freeze. Record item F4 | engine, CLI | PARTLY MERGED. S4a MERGED (engine #721, 2026-11-20): `jitter_days` is read through one window resolver on every route. S4b MERGED (engine #728, 2026-11-20): a `date_shift` without `date_format` is refused at plan compile with `date_shift_requires_date_format`, and the starter writes the detected format. C1 MERGED (CLI #342, 2026-11-20): `decoy init` writes `date_format`, and the `hipaa` and `pci` templates set it. Left: the engine release that carries #721 and #728 (0.28.2, stamp PR engine #740 is open) and the CLI repin. The refusal reaches CLI users only after the repin | plan `E:docs/plans/2026-11-19-speed-batch-f1-f3-f4.md` (branch `plan/speed-batch-f1-f3-f4`); record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.2 F4 | none |
| FAKER-NATIVE-WIDEN | Widen the native `faker` allowlist from first and last name to the disguise providers (email, phone, full name, street address, ipv4, zip). 58 of 109 shipped disguise rules are `faker`, and today one such column puts the whole table on pandas. Each provider needs an all-string, byte-stable pool proof. Output bytes do not change. V1 if a slot is free, else 1.0.x (owner 2026-11-19, Q3). Record item C1 | engine | NOT STARTED | record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.3 C1; plan not written | FAKER-MIGRATE (the pool proofs use the launch Faker) |
| LARGE-STRING-CAST and UF-DOMAIN | Exact-string operators accept `large_string` through a boundary cast, as redact and truncate already do. The unified slice passthrough domain widens to float, date, timestamp and the other int widths (UF-DOMAIN). Today a float or date passthrough column sends a small table to pandas, so a 99,999-row table can be slower than a 100,000-row table with the same schema. Output bytes do not change. V1 if a slot is free, else 1.0.x (owner 2026-11-19, Q3). Record item C4 | engine | NOT STARTED | record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.3 C4; plan not written | none |
| COLUMN-SHAPE-RULE | Declare a column's type and format only where the engine would otherwise guess. Typed sources (Parquet, DuckDB, database) take the shape from the source schema with no declaration; untyped text used by a strategy that reads the value (`date_shift`, `windowed_date`, `bucket_perturb`, `bucketize`, `top_code`) needs the type and format, refused at plan compile if missing; value-opaque strategies never need one; no guessing at run time. One rule in `E:contracts/strategy_requirements.py`. Owner 2026-11-21 (go with recommended); `bucket_perturb` dropping format detection is a freeze item | engine, CLI | PARTLY MERGED. E0 MERGED (engine #745, 2026-11-21): `bucket_perturb` never writes an unparsed date cell through unmasked; it is a `format_error` row error, or a coded stop on the out-of-core route. In review: E1a (engine #750, shape vocabulary, `Plan.column_shapes`, one required source-facts value on every compile route). Built: E1b (engine #751, `date_shift` on typed dates, stacked on #750) and E3 (numeric strategies, local, waits on E1a). Left: E0b, E2, E5, C1, C2, C3. Breaking for 1.0 users of the pre-release: a number column with a `date_format` is refused; `compile_plan` needs `sources=` (CLI follow-up at the repin) | `E:docs/plans/2026-11-21-column-shape-rule.md` (on `E:feat/column-shape-e1a`) | none |

Row 79 is split. 1.0 holds only the authenticated, versioned CLI token vault header, because the vault format freezes at 1.0. The domain-version object, rotation and remap are Later.

## Later (1.x)

Additive. Not scheduled until a 1.x release picks it up.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 24zt | F16-PROHIBIT-DOC (found in engine #631 review): policy prohibitions see only the mask columns a table declares, not every column of the source. The behavior stays; document it in the CLI explain text and guide (slice C2 of row 81). V1 doc item | CLI | NOT STARTED | engine #631 | row 81 E3 |
| 81 | F16: selector grammar, prohibition predicates, 5-level precedence; disguises applied in the engine | engine, CLI | PARTLY MERGED. Plan `E:plan/f16-selectors` (revision 2). E2a MERGED (engine #631, `50cc74827`, 2026-11-17): the `policy` block models, selector grammar, 5-level precedence and `expand_policy`; nothing calls it until E3. E2b is open (engine #642, prohibitions and explanation). Left: E2b, E1, E3, the release, C1, C2 | `E:plan/f16-selectors` | Phase 1 rows |
| 83 | F13 external adapters (HashiCorp Vault, AWS and GCP Secret Manager, Azure Key Vault) | engine, CLI | NOT STARTED | none | F13 preflight (merged) |
| TEXT-REDACT-RUST-SPLICE | 1.0.x. `text_redact` splices in Rust, reusing the detect and splice in `text_mask.rs`. Free text is the slowest per-row masking. Output bytes do not change. Owner 2026-11-19, record item C3 | engine | NOT STARTED | record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.3 C3; plan not written | none |
| FPE-CHECKSUM-NATIVE | 1.0.x. Native FPE checksum schemes (Luhn, NPI, IBAN, VIN, ISBN-13, EAN-13, GTIN) on top of the existing FF1 and Luhn body mode, KAT-locked to python-stdnum. Today the 28 `checksum:` parameters in the cpni, pc and hipaa presets run in Python on every route. Output bytes do not change. Was platform V2 plan item 5 in the health maintenance candidates. Owner 2026-11-19, record item C5 | engine | NOT STARTED | record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 5.3 C5; plan not written | none |
| RUST-DATE-TEXT | 1.2. Rust date parse and format for the common formats, with pandas kept for unusual ones, so `date_shift` and `bucket_perturb` stop parsing in pandas. Full-Unicode `text_redact` and `text_mask` paths. Batch-level work in the hash, index and group_key kernels, and text kernels that release the GIL and use `native_threads` (audit items R10 and R11 in `E:docs/records/2026-11-04-rust-companion-design-audit.md`). Output bytes do not change. Owner 2026-11-19, record section 6 | engine | NOT STARTED | record `E:docs/records/2026-11-19-engine-speed-and-route-completeness.md` (engine #715) section 6; plan not written | none |

### Candidates with no plan yet

Non-breaking ideas, so v1+ by rule. A candidate becomes a row in the table above when a release picks it up.

| Item | Source | Why it does not break |
|---|---|---|
| F17 portable disguise bundles | Council features | New export and import of the existing bundle model. Companion scope says V1: check. |
| F40 plugin SDK | Council features | New public extension contract. It creates a new frozen surface of its own, so the first release of it must be reviewed as one. |
| F47 healthcare packs | Council features | New packs and presets; existing presets keep their output. |
| F50 native masking-policy export | Council features | New export. |
| VAULT-STREAM: A reversible-masking vault (`decoy run --vault`) on runs that write output before they finish: `--chunked`, out-of-core FK runs and sink runs. Today the engine refuses these with `runtime/vault_requires_resident_output` and the CLI refuses `--chunked --vault` first, so a vault run must fit in memory. Needs a staged two-step publish: hold the output where no one can read it, save the vault durably, then release the output, with cleanup on every failure path. | owner | Turns a refusal into a success. The vault format does not change. |
| TOKENIZE-CHUNKED: `decoy tokenize` on the chunked and auto-chunk routes. Today a tokenize job is forced to the full-frame route and the bounded routes fail closed with `tokenize_requires_vault`, so a tokenize job must fit in memory. Needs the token vault wired through the chunked and auto-chunk lanes with per-chunk token reuse. | owner, 2026-11-13 | Turns a refusal into a success. |
| X-08 International identifiers, generators and region disguises | Expansion candidates X-01 to X-25 | New detectors and new dated disguise versions. A released disguise version is never edited. |
| X-10 Meaning-preserving masks | Expansion candidates X-01 to X-25 | New strategies. |
| X-13 Time-series and event masking | Expansion candidates X-01 to X-25 | New strategies. |
| X-19 File metadata scrubbing | Expansion candidates X-01 to X-25 | New option; the default stays as it is. |
| X-25 Plugin SDK as the home for heavy extras (same item as F40) | Expansion candidates X-01 to X-25 | See F40. |
| 1 Reversible tokenization vault, de-tokenize half (MG-5) | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | New feature on the existing vault; the vault format keeps its permanent readers. Blocked on an auth-model decision (who may de-tokenize); owner question. |
| 3 Cross-job joinable masking (`fpe_join_group` expansion) | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | New explicit join-group option. Changing how an existing config derives tokens would be 2.0 (see the contract's `fpe_join_group` note). |
| Secondary: temporal and decimal Faker sources | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | New sources; today "not planned". |
| Secondary: NDC therapeutic-chapter derivation via ATC mapping | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | New derivation. |
| Phase F deferral: `windowed_date` supported-range widening | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | Widens an accepted range; today's range stays valid. |
| 11 Conditional (`when:`) hashing of number columns | Platform V2 candidate plan (`P:docs/backlog/v2-candidate-plan.md`) | Turns a deferred decline into a success. |
| Snapshot the Faker pools so the Faker dependency can be upgraded in 1.x | owner 2026-11-18 | Output stays byte-identical if the snapshot is taken from the pinned release. |

## Maintenance

No user-visible change. Merges at any time and never gates a release.

None.
