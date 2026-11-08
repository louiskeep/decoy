# QA record: synthetic generation (no masking), first-user pass

Date: 2026-11-08. decoy-cli 0.1.0, decoy-engine 0.19.0, Python 3.12, NO_COLOR.
Third record in the series (`2026-11-08-cli-qa-first-user.md`,
`2026-11-08-cli-qa-distribution-integrity.md`). Same method: act as a human
user, build real YAML from scratch, run it, then measure the output. No code
was changed. Test YAML lived in a scratchpad; the minimal repros for every
critical finding are inline below so they can be re-run.

Correction to the DI record: its High 4 ("generated FK does not reproduce
skew") is mostly a user-facing gap, not a regression. `distribution: weighted`
with no `weights` list is silently uniform (see H7). Nothing reads the fitted
parent-key counts.

## 1. General generation questions

A. User ignorance (what a first-timer does not know)
1. Which column types exist, and what options does each take? Where is that list?
2. What is the difference between `faker`, `categorical`, `statistical`, `formula`, `derived`?
3. Do I need `decoy fit` first? When do I use a snapshot and when not?
4. Is a snapshot safe to share? What is `allow_real_categories`?
5. How do I make a child table point at a parent? Do I need `relationships:` too? What is `namespace` for a table with no masking?
6. What does `seed` do vs `--master-key` vs `--key-label`?
7. Where do my files go, relative to what?
8. What do `pooled`, `determinism`, `min_per_parent` mean?
9. How do I get unique emails / ids?
10. How big can I go?

B. User expectations (what a reasonable user assumes)
1. A typo or a bad value is an error, not silently ignored.
2. Two columns I declared separately are independent.
3. Same YAML + same seed = same data; editing the YAML only changes what I edited.
4. Every FK value exists in the parent; a child never has a null FK unless I asked.
5. Ids and emails are unique when they look like ids and emails.
6. Dates are logical (service after birth, ship after order).
7. Numbers can be added and multiplied. Totals roll up per parent.
8. Fitted data keeps nulls, decimals, formats, and skew.
9. The run tells me what it wrote, where, how many rows, and how good it is.
10. Generated data never contains real values.

C. Unclear workflow
1. real CSV -> fit -> YAML -> run -> check: which step produces which file; which command writes the YAML for me?
2. Which report do I run after a generate run?
3. How do I model a hierarchy, a junction table, a time series?
4. What do I do when `validate` says OK and `run` fails?
5. How do I scale to millions of rows, and what stops me from asking for too many?

## 2. Scenarios built

| ID | Industry / shape | Keys and features exercised |
|----|------------------|-----------------------------|
| A | Healthcare claims: providers, members, claims, claim_lines | 3-level FK, 2 parents on one child, min/max per parent, weighted categoricals, null_probability, faker_kwargs, derived, statistical amounts |
| B | Retail: customers, orders, order_items | windowed_date chain, grouped_series, group_key, derived_aggregate, sequential reference |
| C | Banking: accounts, transactions | monotone_walk balance, cumcount, locale, iban/card, timestamps |
| D | Insurance policies fitted from a real CSV | fit with dates and a joint, condition_on, nulls, correlated numerics |
| E | Independent columns from a fitted CSV | does the generator keep independent columns independent |
| F | HR: departments, employees, projects, assignments | self-reference (manager), many-to-many junction |
| G | Contacts with repeated column types | first/middle name, billing/shipping city, created/updated |
| H | ~40 edge cases | typos, bad values, empty parents, infeasible bounds, formats, size, paths |
| I | Keys and determinism | no key, key+label, new label, seed vs key, edits to YAML |
| J | Shipped starting points | bundled `generate` template, `examples/generate_example.yaml`, `init` |

## 3. What worked (do not regress)

- Reproducible: same seed (or same key + label) gives byte-identical files.
  Different label gives different files.
- Stable under edits: adding a column, or growing `row_count` 100 to 150, left
  every existing column's first 100 rows unchanged (keyed and unkeyed).
- FK integrity: every generated child key exists in its parent in A, B, C, F
  (0 orphans). Three-level chains work.
- `windowed_date` honoured its windows (ship 1-7 days after order, delivered
  2-10 after ship). `group_key` and `monotone_walk` behaved (per-account
  balance non-decreasing in order).
- `condition_on` is excellent: tier given region matched the source
  (N 86/7/7 source and generated).
- Statistical numeric marginals are close (age mean 48.8 vs 49.4, premium
  661 vs 666). 1M rows x 3 columns in ~13 s.
- Bundled `generate` template and `generate_example.yaml` validate, run, and
  produce 1000 rows with 0 duplicate emails.
- The engine refuses to emit real categories without
  `allow_real_categories: true`.
- `min_per_parent` / `max_per_parent` are honoured when feasible (3-8 per
  parent: got 3-8).

## 4. Findings

### Critical (wrong data, exit 0, no warning)

C1. Columns with the same settings get identical values. Minimal repro (seed 3, 1000 rows):

    - {name: first_name, type: faker, faker_type: first_name}
    - {name: middle_name, type: faker, faker_type: first_name}
    - {name: created_at, type: faker, faker_type: date_between}
    - {name: updated_at, type: faker, faker_type: date_between}

    Result: `first_name == middle_name` in 100% of rows; `created_at == updated_at`
    100%; same for two categoricals and for `billing_city`/`shipping_city`.
    Same with `--master-key`. Two `pyint` columns correlate at 1.0.
    Statistical columns fitted from independent source columns (source
    correlation 0.02) come out at 0.82-0.95; categoricals become functions of
    each other (`region=N` always gives `note=vip`). The column name is not
    enough to separate the streams (hypothesis: seed comes from the column
    settings; see `_column_ctx` / `_legacy_column_name_seed`). The only escape
    found is `determinism: fresh`, which de-correlates but makes that column
    different on every run, and it is documented nowhere a user sees.
    Needs: separate by column name by default.

C2. Numeric sequences and faker numbers are text inside the generator.
    - `derived: "a * 2"` with `a` a sequence gives `"11"` for row 1 (string
      repeat). `derived: "f * 2"` with a `pyfloat` gives `5.972735.97273`.
      `derived: "a * 0.7"` fails with "an operand has an unsupported type".
      Same expressions work on `categorical` numbers and `statistical`.
    - `grouped_series` with `order_by` on an unpadded numeric sequence sorts
      as text: for rows with `line_id` 5, 405, 805 it gave `line_no` 2, 1, 3.
      Padded string ids (`prefix` + `pad_length`) sort correctly.
    Both exit 0. Net: you cannot compute `quantity * price` from generated ids
    or fake numbers, and sequence numbers per group can be out of order.

### High

H1. Nulls and blanks are lost from a fit. Source `smoker` 13.8% blank, `note`
    50% blank: generated 0% for both. `report fidelity` scored them 1.000 and
    0.998, so the report is blind to it. Also the `fit` summary does not
    mention nulls.

H2. No uniqueness control. At 200,000 rows: `email` 22.3% duplicates,
    `user_name` 39.2%, `name` 95.3% (9,399 distinct). Default `pooled: true`
    caps names at ~9.3k distinct at 50k rows; `pooled: false` gives 40k but is
    2x slower. `pooled` appears in no help. No `unique: true`. A junction table
    got 17 duplicate (emp, project) pairs in 300 rows. Small data is fine
    (bundled example: 0 duplicates in 1000), so users find it late.

H3. Bad input accepted silently (all exit 0, `validate` OK):
    - `faker_type: not_a_provider` -> random words (falls back to `word`).
    - option typos: `weigths: [0.99, 0.01]` is ignored (got 51/49).
      The schema declares generate columns as `additionalProperties: true`,
      so no typo is ever caught.
    - `weights: [-1, 2]` -> every value is the second category.
    - `locale: xx_YY` -> English. `faker_kwargs: {nope: 1}` -> ignored.
    - `null_probability: 2` accepted. `step: 0` -> every id is 1.
    - two columns with the same name -> one is dropped.
    - `categories: [a, a, b]` -> a gets 67% (probably intended, undocumented).
    - `formula` with an error (`"a +"`), a missing reference, no `references:`
      list, or the documented `{a} * 2` syntax -> blank column.

H4. `validate` OK, `run` fails with raw library text and no column name:
    `Total of weights must be greater than zero`; `Expected bytes, got a 'int'
    object` (mixed-type categories); `The column label 'order_id' is not
    unique` (`group_by` equals `order_by`); `derived ... a referenced column is
    missing` (reference to a column declared later). `row_count: 5000000000`
    passes validate, then ends with an empty `error: ` and exit 3 (the
    capacity code 5 exists but is not used here).

H5. Cross-column and cross-table logic cannot be expressed:
    - 5 of 1000 claims have a service date before the member's birth date. A
      date window can only anchor to a column in the same table.
    - Timestamps are not ordered with their sequence (`posted_at` vs `txn_seq`).
    - `derived_aggregate` writes one table-wide total onto every row (62537.55
      on all 1200 order lines). There is no per-parent roll-up such as
      `order_total` on `orders`.
    - Self-reference (`employees.manager_id -> employees.emp_id`) is rejected
      ("reference cycle"). Clear message, but no workaround is offered.

H6. FK contract can be broken quietly:
    - Parent with `row_count: 0`: child rows are generated with 50 of 50 null
      FKs even with `orphan_policy: fail`.
    - `min_per_parent` larger than possible, or `min` greater than `max`: no
      warning, constraint dropped. `max_per_parent: 6` alone gave a max of 7.

H7. `reference` options silently degrade: `distribution: weighted` with no
    `weights`, or with a `weights` list of the wrong length, is uniform;
    `distribution: bogus` is random. No way to reproduce the source fan-out
    skew (8/5/2/1...) from a fit.

### Medium

M1. Fitted numbers lose their shape: source 2 decimals, generated
    `24.788501599966185`; source date `2021-04-26`, generated
    `2021-04-26 10:28:30.056808`; `start_date` fidelity 0.385.
M2. Path rules differ. `targets.path` resolves from the config file's folder;
    `snapshot_file` from the current folder. Same YAML works from one folder
    and fails from another.
M3. The run summary does not say what it did: no output paths, row counts, or
    warnings. `--json` has the same gap. `--fidelity` prints "no mask-table
    fidelity report was produced" on a generate run. `fidelity_warn_threshold:
    0.99` produced no warning with a 0.385 column.
M4. `validate compile --explain` on a generate pipeline prints empty tables,
    "no FK dependencies detected" (3 declared) and "declaration order".
M5. `init`: `--preset generate -o -` creates a file literally named `-`
    (works for the file-argument form). No way to ask for "a synthetic version
    of this CSV"; the scaffold from a CSV is mask-only (every column `redact`).
M6. With `--master-key`, `global_settings.seed` is ignored (seed 5 vs 99 gave
    identical files). Two knobs, one silently dead.
M7. `sequence` requires `start` though code and defaults say 1; the error
    starts "Value error,".
M8. Only `csv`, `parquet`, `fixed_width` targets; no JSON or JSONL.
M9. `namespace` is required on a relationship even when nothing is masked
    (carried from earlier records), and `validate` can crash with a traceback
    when it is missing.
M10. A boolean column in a snapshot needs `allow_real_categories`. Consistent
    but heavy; the error ends with a double period.

### Low

L1. `--explain-plan` says "pandas_fallback" (sounds like a fault).
L2. Phone numbers mix `399.924.2830` and `(527)987-0030x9463`; no format option.
L3. Stray `logs/` folder next to the config after every run (carried).
L4. Evidence for a generate run titles its table "Masking strategies".
L5. Null cells are written as `""` (quoted empty) for faker nulls.

## 5. Language and explanation audit

- `explain pipeline`: says `version 1` (YAML needs `version: 2`); lists no
  generate column types and no `relationships` options; mentions "FC-1",
  "storm-reframe-C", and "decoy-platform's web UI".
- `explain transforms`: still talks about `masking_rule` and `type:` (the
  file uses `strategy:`); says 13 strategies (`list strategies` shows 25);
  lists `categorical` and `formula` as mask strategies; says `formula` can use
  `{col1}` and `randint()` (braces give a blank column); ends with "when a
  future --mask flag is added". No word on generation types.
- `explain yaml`: points to `decoy-platform/docs/guides/cli-yaml-workflows.md`,
  which is not in this repo; says "STORM" without saying what it is.
- No `explain` topic for generation, `fit`, `statistical`, `reference`,
  `unique`, or snapshots. Only 2-9 lines across all topics mention generation.
- `decoy schema` cannot help: per-type options are not in it, and any extra
  key is allowed. The only complete list is in engine source.
- Errors lean on library wording ("Input should be 'faker', 'sequence', ...",
  "Value error", "operand has an unsupported type") and rarely give the fix.
- Undiscoverable options in use: `pooled`, `determinism: fresh`,
  `min_per_parent`, `max_per_parent`, `null_probability`, `faker_kwargs`,
  `locale`, `allow_real_categories`, `condition_on`, `bounds`.

## 6. Command families

- `fit` (prep), `run` (do), `report fidelity` (check) are three top-level
  places for one job. A "Generate" help group would make the path visible.
- `report fidelity` needs `--generate` and cannot compare key columns; the
  run already knows its mode.
- `init` covers masking only; generation has a template but no wizard.
- `validate compile --explain` is mask-shaped; generation has no equivalent
  ("why is this column this type").
- Missing verbs: a per-table preview (`run --rows 5` or `decoy preview`), a
  `decoy list column-types`, and a check that compares a generate run to its
  snapshot (nulls, precision, correlations).

## 7. Suggested order

1. C1 (separate columns by name) and C2 (numeric typing in the generator):
   both silent, both break every realistic use. Add a regression test with two
   identical columns.
2. H3 and H4: reject unknown keys per type, validate values, and make `validate`
   reproduce every run-time failure. One schema change fixes much of this.
3. H2 (a `unique` option) and H1 (carry null rates through `fit`).
4. H5/H6/H7: per-parent aggregates, a parent-anchored date window, strict
   bounds with a clear error, empty-parent failure.
5. M2/M3: one path rule; a run summary with files, rows, warnings.
6. Docs: a "Generation" explain topic that lists the 11 types and their
   options; fix `explain pipeline` and `explain transforms`.

## 8. Not tested / limits

DP generate (`global_settings.dp`) and DP snapshots (blocked, see the DI
record); composite FKs in generation; `grouped_series` with a non-numeric
`order_by`; `fixed_width` output; very wide tables; memory above ~1M rows;
other platforms or locales for determinism; `--native`; `--duckdb-source`.
