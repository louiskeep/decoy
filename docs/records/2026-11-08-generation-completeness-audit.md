# Audit: generation strategies, completeness and usability across industries

Date: 2026-11-08. decoy-cli 0.1.0, decoy-engine 0.19.0.
Companion to `2026-11-08-cli-qa-generation.md` (bugs in what exists). This record
asks the other question: what a user in each industry expects to be able to
generate, and what is missing. Every "tested" claim was run through the CLI;
"read" means taken from engine source or the roadmap. No code was changed.

Status key: PLANNED = already a row in `docs/roadmap/v2-v3-expansion-candidates.md`
or `out-of-scope.md` (the id is given); UNREACHABLE = exists in the engine but a
generation YAML cannot use it; NEW = not found in the roadmap.

## 1. What generation offers today

Eleven column types are accepted in `generate_columns` (the capability matrix
says twelve; its twelfth, `distribution`, is rejected by the schema: tested).

| Type | Options (found in source; no user-facing list exists) | Notes |
|------|--------------------------------------------------------|-------|
| `sequence` | `start` (required), `step`, `prefix`, `suffix`, `pad_length` | Values are text inside the generator (see QA record C2) |
| `faker` | `faker_type`, `locale`, `faker_kwargs`, `null_probability`, `pooled`, `determinism` | 258 Faker names accepted; unknown names silently give words |
| `categorical` | `categories`, `weights` | Inline lists only |
| `reference` | `reference_table`, `reference_column`, `distribution` (random, sequential, weighted), `weights`, `min_per_parent`, `max_per_parent` | Picks a random parent value; not row-aligned to a sibling FK |
| `formula` | `formula`, `references` | Plain column names; `{col}` gives blanks |
| `derived` | `expression`, `bounds`, `null_propagation` | Closed grammar; no `if()` (tested: run fails) |
| `derived_aggregate` | `op` (sum, mean, min, max, count), `column` | One table-wide scalar on every row |
| `statistical` | `snapshot_file`, `condition_on`, `allow_real_categories`, `high_cardinality` | Needs `decoy fit` on a CSV first |
| `grouped_series` | `group_by`, `order_by`, `generator` (cumcount, monotone_walk), `start`, `step`, `max_step` | Numbers only |
| `windowed_date` | `anchor`, `min_days`, `max_days`, `distribution` (uniform + two decays) | Anchor must be in the same table |
| `group_key` | `group_by`, `length`, `prefix` | Hex key per group |

Around them: `row_count`; `global_settings` (`seed`, `dp`, `fidelity_warn_threshold`,
`default_locale`); `--master-key` / `--key-label`; `fit` (`--joint`, `--parse-dates`,
`--epsilon`); outputs csv, parquet, fixed_width; one bundled generate template
(employees) and one example (customers).

## 2. Gaps, grouped

### A. Core column types

| # | Missing | Evidence | Status |
|---|---------|----------|--------|
| A1 | Parametric distributions with no source data: normal, lognormal, uniform, exponential, poisson, beta, zipf | `type: normal` and `type: distribution` rejected; only `pyint` / `pyfloat` (uniform) exist. Today a user with no data cannot say "age ~ normal(40, 10)"; they must invent a CSV and fit it | NEW |
| A2 | Constant / literal value | `type: constant` rejected (workaround: one-category `categorical`) | NEW |
| A3 | Lookup list from a file (ICD-10, product catalog, SKU list, city list) with optional weights | `categories_file` rejected; `categories` inline only | NEW |
| A4 | Uniqueness (`unique: true`), including composite uniqueness for junction tables | 22% duplicate emails at 200k rows; 17 duplicate pairs in 300 junction rows | NEW |
| A5 | Explicit output type per column (int, decimal(2), date, bool) | CSV is all text; fitted numbers print 15 decimals; sequences behave as text | NEW |
| A6 | Boolean with a rate, date with weekday / hour-of-day pattern, holiday / seasonality | Only via `pybool` kwargs or hand-built categories; no calendar model | NEW |
| A7 | Free text beyond lorem (clinical notes, reviews, ticket text) | Only Faker `text` / `paragraph` | NEW (F08 is mask-side) |
| A8 | `if()` / conditional in `derived`; string functions | `derived: if(...)` fails at run; `formula` supports `x if c else y` | NEW |

### B. Coherent records and domain values

| # | Missing | Evidence | Status |
|---|---------|----------|--------|
| B1 | Domain identifiers in generation: NPI, MRN, ICD-10, NDC, PAN, IBAN, CUSIP, EIN, SSN (`synthetic_*`) | `faker_type: synthetic_npi`, `synthetic_icd10`, `synthetic_mrn` all return random English words, exit 0. The 34 providers work under masking `provider:` only | UNREACHABLE |
| B2 | Coherent person / address records (name matches email and sex; city, state, ZIP, lat/long agree) | email contains the name in 1.3% of rows; NY ZIPs start with 5, 0, 4, 7; F rows get "Brian"; `composite_person` as `faker_type` gives words. The roadmap baseline says correlated composites ship (SDV HMA1 pattern) | UNREACHABLE |
| B3 | Age agreeing with date of birth; end date after start date | age vs birth mean error 33 years; 51% of rows end before start | NEW (partly `windowed_date`, same table only) |
| B4 | Insurance / healthcare / finance code sets: CPT, HCPCS, DRG, LOINC, SNOMED, MCC, NAICS, ISIN, SWIFT with validity | None present; `isin`, `npi` fall back to words | PLANNED F47 (healthcare packs), X-08 (international) |
| B5 | International identifiers and addresses beyond US | Roadmap baseline: "mostly US identifiers"; `locale` helps names and addresses only | PLANNED X-08 |

### C. Relationships and structure

| # | Missing | Evidence | Status |
|---|---------|----------|--------|
| C1 | Inherit a parent attribute into a child row (`claims.member_state` = its member's state) | 6% match (chance); denormalized tables are common | NEW (mask side has `from_parent`) |
| C2 | Child-count distribution per parent (Poisson, zipf, "80% have 1 order") | Only `min_per_parent` / `max_per_parent`; weighted fan-out is silently uniform | NEW |
| C3 | Per-parent aggregates (`order_total` on orders = sum of its lines; `n_claims` on members) | `derived_aggregate` is one table-wide number | NEW |
| C4 | Parent-anchored dates (service date after the member's birth / enrollment) | 5 of 1000 claims before birth | NEW |
| C5 | Self-reference and hierarchies (manager, category tree, thread) | "reference cycle" error | NEW |
| C6 | Composite foreign keys in generation | Not tested; engine supports them for masking | not tested |
| C7 | Many-to-many with unique pairs | Duplicate pairs | NEW (see A4) |
| C8 | Stratified / conditional categoricals declared in YAML (diagnosis by age band, tier by region) | `condition_on` works only from a fitted snapshot | NEW |

### D. Time, events, and statistics

| # | Missing | Evidence | Status |
|---|---------|----------|--------|
| D1 | Ordered timestamps per entity, event sequences and state machines (patient journey, order lifecycle, session clicks) | `grouped_series` is numeric; `posted_at` was not ordered by sequence | PLANNED X-18 (V3), X-13 |
| D2 | Joint distributions across many columns (correlations, copula) | Fit captures pairs via `--joint`; independent columns correlate at 0.8+ today (QA record C1) | PLANNED X-14, F48 |
| D3 | Multi-table statistical synthesis (fit parent and child together) | `fit` takes one CSV; fan-out cannot be learned | PLANNED X-15 |
| D4 | Null rate, precision and format carried from fit | Nulls lost, 15 decimals | NEW (bug-shaped; QA record H1/M1) |
| D5 | Generate from a schema (DDL, Postgres catalog, JSON Schema) instead of hand-writing YAML | None | PLANNED X-16 |
| D6 | Scenario packs: rare events (1% fraud), prevalence targets, drift between two datasets | Categorical weights only | PLANNED F46 |

### E. Test-data realism

| # | Missing | Evidence | Status |
|---|---------|----------|--------|
| E1 | Dirty-data injection: typos, duplicates, outliers, malformed dates, mixed case, trailing spaces | `null_probability` is the only knob | PLANNED X-17 |
| E2 | Edge-case values (boundary dates, max-length strings, unicode, leap days) | None | PLANNED X-17 |

### F. Outputs, scale, workflow

| # | Missing | Evidence | Status |
|---|---------|----------|--------|
| F1 | JSON / JSONL, Excel, Avro, ORC, SQL INSERT, database targets for generation | Only csv, parquet, fixed_width | PLANNED X-01, X-02, X-03, F01 (PostgreSQL target) |
| F2 | Streamed generation for more rows than memory | `--chunked` is mask-only; 200k rows x 7 faker columns took 50 s; 5e9 rows ends in an empty error | NEW |
| F3 | Parameterised YAML (`row_count` from a flag, shared column sets) | Row counts and column blocks must be copied by hand | PLANNED F18 (config composition) |
| F4 | `generate --preview` / `run --rows 5` and a column-type catalog command | No way to see a few rows before a full run | NEW |
| F5 | Industry starter templates | One generate template (employees) and one example; four mask templates | NEW (F47 covers healthcare only) |
| F6 | A scoring step for generation against intent (nulls, correlations, uniqueness, FK fan-out) | `report fidelity` compares marginals only | NEW |

## 3. Industry completeness

Reading: "ready" = can be built today with correct results; "partial" = built
today but wrong or unrealistic in a named way; "blocked" = cannot be built.

| Industry | Typical data | Ready | Partial / blocked (gap ids) |
|----------|--------------|-------|-----------------------------|
| Healthcare (payer / provider) | members, providers, claims, lines, encounters, labs | Parent-child keys, categorical status mixes, weighted claim types | NPI, MRN, ICD-10, CPT, NDC, LOINC (B1, B4); service before birth (C4); claim totals (C3); patient journeys (D1); coherent patient (B2) |
| Banking / fintech | customers, accounts, cards, transactions, balances | IBAN and card shape (Faker), per-account running series | PAN / CUSIP / ISIN domain values (B1); ordered timestamps (D1); fraud-rate scenarios (D6); amounts need parametric or fit (A1); balance = sum of txns (C3) |
| Insurance | policies, claims, endorsements, premiums | Fit-based premium and age with `condition_on`; policy-to-claim keys | Policy / claim dates anchored to parents (C4); loss distributions (A1); coherent insured (B2) |
| Retail / e-commerce | customers, products, orders, items, returns | Orders, items, ship / delivery windows, group keys | Order total (C3); product catalog from a file (A3); price x qty arithmetic (QA record C2); seasonality (A6); returns referencing a past order date (C4) |
| Telecom | subscribers, devices, call-detail records, plans | IDs, phone numbers, plans | MSISDN is a Faker name, but IMEI / IMSI missing; CDR event streams (D1); heavy-tailed usage (A1) |
| HR / education | employees, departments, courses, enrollments | Departments, employees, assignments | Manager hierarchy (C5); unique pairs (C7); grade distributions (A1); term calendars (A6) |
| SaaS / IoT / logs | users, sessions, events, devices | Per-device monotone readings, user agents, IPs | Event ordering and sessions (D1); inter-arrival distributions (A1); event-to-user attributes (C1) |
| Public sector / logistics / energy | cases, shipments, meter reads | Keys, codes by categories, addresses | Geo coherence (B2), regional IDs (B5), time series (D1), route / hierarchy graphs (C5) |

Across industries: every sector can build small, flat, categorical-heavy data
that is internally linked. None can currently build realistic money, dates
across tables, or event sequences without either a hand-made CSV or accepting
inconsistent rows.

## 4. Usability observations from the same pass

- A user cannot learn the type list from the product. `decoy schema` allows any
  extra key per column; `explain` has no generation topic; the only complete
  list is engine source (section 1 above was built from it).
- The 34 domain providers and the Faker names look like one feature but are two
  registries; the wrong one fails silently (B1).
- Starting points: `init` scaffolds masking only; there is no "make a synthetic
  copy of this CSV" path (fit plus YAML) and no industry generate templates.
- The capability matrix says 12 generation strategies; the product accepts 11.

## 5. Suggested priorities (for the orchestrator)

1. Reach what already exists: let `type: faker` (or a new `provider:` field)
   call the 34 domain providers and composites (B1, B2). Cheapest large win;
   the code is written.
2. Fill the small core types: constant, parametric distributions, lookup file,
   unique, output type, conditional `derived` (A1 to A5, A8).
3. Relationship features that make multi-table data credible: inherit parent
   attribute, per-parent aggregate, parent-anchored dates, fan-out distribution
   (C1 to C4, C8).
4. Starter templates per industry and a preview command (F4, F5), plus a
   generation explain topic that lists the types (see QA record section 5).
5. Leave to the roadmap: copula, multi-table synthesis, event data, schema
   generation, dirty-data, new formats (D1 to D3, D5, D6, E1, E2, F1). Make
   sure the owner knows the order matters: D2 and D4 depend on fixing the
   column-independence bug first.

Roadmap constraint: this is evidence, not a roadmap. Rows belong in
`docs/ROADMAP.md` via the orchestrator; do not start a separate todo doc.

## 6. Limits

Not tested: composite FKs (C6), date arithmetic inside `derived`, DP generate,
fixed-width output, sources outside CSV, databases. Gap statuses come from a
grep of the roadmap files on this date and may lag the owner's latest decisions.
