# QA record: distribution models for data generation (ten-question pass)

Date: 2026-11-10. decoy-cli 0.1.0, decoy-engine 0.19.0, CPython 3.10.20, Linux x86-64, NO_COLOR.
Fourth record in the series (`2026-11-08-cli-qa-first-user.md`,
`2026-11-08-cli-qa-distribution-integrity.md`, `2026-11-08-cli-qa-generation.md`).
No product code was changed. Docs written from this pass:
[`docs/guides/shape-and-privacy/`](../guides/shape-and-privacy/README.md) here, and
`docs/distribution-integrity/` in `decoy-engine`.

Scope: `decoy fit`, `type: statistical` generation, `condition_on`, `decoy report fidelity`,
`decoy run --fidelity`, and the differential-privacy (DP) fit.

## Method

- Two environments built from the source checkouts at engine `44d6afe`, CLI `d73328c`:
  - **certified**: `uv pip install --no-deps <engine> <cli>` then `requirements-certified.txt`.
    Fingerprint `795732eb...`, `check_fit_environment()` passes. Used for every CLI run.
  - **plain**: `uv pip install <engine> <cli>`. Fingerprint `8c793360...`. Used for the
    uncertified-install test and for pandas analysis of outputs.
- Synthetic test data, generated with fixed seeds. Sizes are given per finding.
- Every number below was measured in this pass. Each DP sweep cell is one random draw.
- Paths in "Where" are relative to `decoy-engine/src/decoy_engine/` unless they start with
  `cli/`, which is `decoy/src/decoy/cli/`. Line numbers are for the commits above.

## Summary

| # | Question | Result | Findings |
|---|---|---|---|
| 1 | Are generated columns independent? | Fails | C1 |
| 2 | Does `condition_on` hold up outside the easy case? | Partly | H1, M1, M2 |
| 3 | Nulls, precision and types end to end | Fails | H2, M3, M4 |
| 4 | Where does the histogram model break? | Fails | C2, H3 |
| 5 | Does the fidelity report catch these? | Mostly not | C3, H4 |
| 6 | Why do `run --fidelity` and `report fidelity` differ? | Explained | M5 |
| 7 | Is the generation fidelity warning visible? | No | H5 |
| 8 | Do plain snapshots leak? | Yes | H6, H7, M6 |
| 9 | When is a DP release usable? | Sizing table below | H8, M7, M8 |
| 10 | Does the DP contract fail closed? | Yes for misuse, no for a forged file | M9 |

## What held up (do not regress)

- Columns whose settings differ in any way are independent (correlation 0.02 to 0.05).
- A three-column `condition_on` chain: zero impossible pairs on a fully fitted link. Zeros in
  the source pair table stay zeros.
- Integer columns stay integers and stay inside the fitted range.
- The year mix of a date column is reproduced (0.331/0.332/0.337 source, 0.332/0.334/0.334 out).
- Same seed and snapshot give a byte-identical file. A DP snapshot generates byte-identical
  output on the plain install.
- The 30-distinct cutoff: 30 values are stored as categories, 31 are stored as length only.
- SSN-like unique text is never stored. Generation without `allow_real_categories` is refused.
- DP refusals, all with clear messages and no output written:
  two releases over the ceiling; one release ID with different bytes; replaced fingerprint;
  missing release ID; changed scope; `allow_real_categories`, `condition_on` or
  `high_cardinality` under `dp`; `dp: null`; `dp: {}`; epsilon over 700; delta 0 or 1;
  inverted or infinite number range; a fit on an uncertified install (exit 3).
- DP accounting: one release used by several columns is charged once, including a
  byte-identical copy at another path. Two distinct releases compose (1.0 + 1.0 = 2.0).

## Findings

### Critical (wrong data, exit 0, no warning)

**C1. Columns with identical settings share a seed.**
- Evidence: 2,000 rows. Two columns with the same config matched on 100% of rows for
  `statistical`, `faker` `first_name`, `categorical`, `faker` `pyint` and `faker`
  `date_between`. Same with `--master-key`. Two statistical columns from independent sources
  (source correlation 0.015) generated at 0.967 when neither set `source_column`.
- Cause: the column seed is a hash of the column config with `name` excluded.
- Where: `generators/derivation.py:57` (`_EXCLUDED_FROM_FINGERPRINT`), `:114`
  (`strategy_config_fingerprint`), `:213` (`for_column`);
  `generation/_statistical_column.py:76`.
- Workaround, verified: give each statistical column a distinct `source_column`. Correlation
  dropped to 0.017 and the category pair scored 0.964 against the source.
- Roadmap: row 24i (GEN-C1). New in this pass: the root-cause location, the workaround, and
  confirmation that a keyed run is affected.

**C2. One outlier ruins a numeric column.**
- Evidence: 20,000 rows near 100 plus one value of 1,000,000. Source mean 150, generated mean
  49,940. 99.8% of generated rows were above 200 (source: 0.005%).
- Cause: ten equal-width buckets over min to max. Almost every real value lands in bucket one,
  which is then sampled uniformly across a range of about 100,000.
- Where: `quality/snapshot.py:401` (`_numeric_stats`), `:449` (`np.histogram`), `:119`
  (`_DEFAULT_NUMERIC_BINS = 10`); sampler `generation/statistical/_sample.py:160`
  (`_numeric_row`), `:265`.
- Roadmap: not listed. Proposed new row.

**C3. The fidelity report passes C2 and most other defects here.**
- Evidence, same file as C2 and H3: grade B, overall 0.918, "OK no policy violations".

  | Column | Defect | Primary score | KS extra | Shape score (JSON only) |
  |---|---|---|---|---|
  | `outlier` | mean 150 to 49,940 | 0.940 | 0.997 | 0.102 |
  | `skew` | median 19.9 to 91.5 | 0.968 | 0.989 | 0.989 |
  | `price` | 4 distinct to 20,000 distinct | 0.935 | 0.998 | 0.998 |
  | `null10` | 10% nulls to 0% | 0.996 | 0.982 | 0.960 |
  | `null90` | 90% nulls to 0% | 0.997 | 0.998 | 0.997 |

- Cause: numeric similarity divides the quantile error by the source range, so a wide range
  hides any error. Nulls are not part of any score.
- Where: `quality/fidelity.py:366` (`_numeric_similarity`; formula at `:19`).
- `--mode fail --min-grade B` exits 0. A policy with `thresholds.diagnostic.required: true`
  exits 4, on the null drift only.
- Roadmap: row 24l covers null scoring. The range-normalization blind spot is not listed.
  Proposed new row.

### High

**H1. `condition_on` silently invents combinations past 25 pairs.**
- Evidence: 6,000 rows, 12 parent values, 36 real pairs. The snapshot kept 25 cells
  (`other_count` 314). The rarest parent lost all its cells and fell back to the child's overall
  counts: 33 rows (0.5%) with pairs that never occur in the source. Pair score 0.931, no warning.
- Where: `quality/snapshot.py:126` (`_DEFAULT_CONTINGENCY_TOP_K = 25`), `:547`
  (`_joint_snapshot`); fallback at `generation/statistical/_sample.py:323`. `decoy fit` has no
  flag to raise the cap (`cli/fit.py:422`).
- Roadmap: not listed. Proposed new row.

**H2. Null rates are not reproduced.**
- Evidence: source nulls 10.3% and 89.9%; generated 0% and 0%.
- Where: `null_count` is fitted (`quality/snapshot.py:232`) and never read by
  `generation/statistical/_sample.py:234`.
- Roadmap: row 24l (GEN-FIT-SHAPE).

**H3. Skewed and discrete numeric columns are distorted.**
- Evidence, 20,000 rows each: lognormal median 19.9 to 91.5 and mean 41 to 98; four price
  points became 20,000 distinct values with 0.08% on a real price; a two-peak column put 1.4%
  of rows in a gap that held 0.04%.
- Where: same as C2.
- Roadmap: row 24l covers precision only. Bucket shape is not listed. Proposed with C2.

**H4. Report warnings never reach the terminal.**
- Evidence: `null_drift` and `kind_drift` appear in `--json` under `warnings` and
  `diagnostic`. The human output prints the score table and "OK no policy violations".
- Where: `cli/report.py:1843` (`_render_fidelity_report`).
- Roadmap: not listed. Fits row 24e (CLI-QA1) or 24o (GEN-CLI).

**H5. The generation fidelity warning is invisible, and its default misses real failures.**
- Evidence: with `fidelity_warn_threshold: 1.0` the warning
  `generation_fidelity_below_threshold` was written to `logs/decoy_engine.log` only. It was
  absent from stdout, stderr, `--verbose` and `--json`. At the default 0.8 it did not fire on
  the C2 file, which scored 0.979.
- Where: `generation/_fidelity_gate.py:52`, `:163`; `config/_global_settings.py:116`;
  `cli/run.py:1379` renders mask-table reports only.
- Roadmap: row 24o (GEN-CLI) covers visibility. The default threshold is not listed.

**H6. A plain snapshot stores single-person values, and `fit` says nothing.**
- Evidence, 1,000 rows:
  - A diagnosis code held by one row is stored as `{"value": "RARE-HIV-B20", "count": 1}` and
    appeared in 9 of 5,000 generated rows.
  - One row's salary of 987,654 is stored exactly as the column `max`. Generated values reached
    974,516. Numeric columns need no consent flag.
- Where: `quality/snapshot.py:464` (`_categorical_stats`), `:401` (`min`/`max`); consent gate
  `generation/statistical/_spec.py:373` covers categories only; `cli/fit.py:422`.
- Roadmap: row 24f (QA-FIT-REDACT). New in this pass: the numeric `min`/`max` case and the
  count-of-one case.

**H7. Short free text is stored and emitted verbatim.**
- Evidence: a note column with 30 distinct strings such as `note: patient Surname24 called` was
  classed as categorical. Every string was stored, and 100% of generated notes were real
  source strings.
- Where: `quality/snapshot.py:133` (`_CATEGORICAL_DISTINCT_CAP = 30`), `:269` (`_stats_for`).
- Roadmap: row 24f.

**H8. A DP fit is slow, and the cost is paid on every CLI call.**
- Evidence, 500 rows through the CLI: 13 s for 2 columns, 37 s for 8, 88 s for 20. In one
  process the first fit per layout took 11 s, 36 s and 85 s; repeats took 0.3 to 2.4 s at
  5,000 rows. At 500,000 rows: 14 s, 55 s and about 140 s.
- Cause: the per-query budget search depends only on the layout and the request. Its result is
  cached in memory, so a new process starts cold.
- Where: `quality/dp_session.py:119` (`_allocate_epsilon_cached`), `quality/dp_budget.py:267`
  (`_ALLOCATION_CACHE`).
- Roadmap: not listed. Proposed new row (persist the scalar allocation, or document the cost).

### Medium

**M1. A renamed parent cannot be used with `condition_on`.** `name: region` with
`source_column: parent`: `condition_on: region` fails with "no joint contingency for
('region', 'kid'). Re-fit with `decoy fit --joint region,kid`", which would not help.
`condition_on: parent` fails with "not declared earlier". Where:
`generation/statistical/_spec.py:453`, `:464`; `plan/_checks.py:396`.

**M2. An unseen parent value falls back silently.** A hand-written categorical parent with a
value `ZZZ` not in the fit drew its child from the overall counts. Where:
`generation/statistical/_sample.py:323`.

**M3. Dates lose everything but the year, and gain a time.** Source 66.4% January; generated
8.8%. Output is `2021-08-11 11:47:15.446627` for a date-only source. Where:
`quality/snapshot.py:487` (`_datetime_stats`), `generation/statistical/_sample.py:327`.
Roadmap: row 24l covers resolution. Month and weekday shape are not listed.

**M4. Zero-padded codes become numbers.** A five-digit zip column was fitted as numeric;
9.8% of generated values were shorter than five characters. Where: `cli/fit.py:402` reads
with pandas type inference.

**M5. `run --fidelity` and `report fidelity` infer types differently.** Same masked run:

| Column | Inline | `report fidelity` |
|---|---|---|
| `customer_id` (hash) | `length_mean_diff` 0.044 | `kind_mismatch`, skipped |
| `amount` (bucketize) | `kind_mismatch`, skipped | `quantile_rmse` 0.946 |
| Overall | 0.833, C | 0.962, A |

Where: `execution/_pipeline_finalize.py:157` (loaded frames); `cli/report.py:1816` (CSV
re-read, no `--parse-dates`).

**M6. `--parse-dates` on an unparseable column falls back to text with no message.** Seen on a
malformed date column in the H6 file.

**M7. An empty DP release validates, then fails at run.** 20 rows at epsilon 0.02: the release
reported 318 rows and no labels for `state`. `decoy validate` passed. `decoy run` exited 3 with
`statistical_stats_degenerate`. Where: `generation/statistical/_sample.py:289`. Roadmap: the
class is row 24b (QA-GATE).

**M8. A DP row count can be 0 or far off.** 500 rows, 20 columns, epsilon 0.1 released
`row_count: 0`; 20 real rows at epsilon 0.02 released 318.

**M9. A forged or edited DP snapshot is accepted.**
- A real label hand-added to a DP snapshot was generated (TX in 58 of 200 rows).
- `epsilon_total` edited to 0.01 passed a ceiling of 0.05.
- A plain snapshot reshaped to match the DP schema, with a copied `dp` block, passed and
  generated all five real states where the honest release had two.
- A plain snapshot with only the `dp` block added was refused (missing carrier).
- Where: `plan/_checks_dp.py:210` (`verify_dp_snapshots`).
- This is a documented limit: `decoy-engine/docs/what-we-cannot-prove.md` lines 49 and 251 to
  289 exclude forged artifacts, and authentication is on the roadmap for a later schema. Listed
  here so the limit is tested, not assumed.

## Q9: DP sizing

Values that survived for a 5-value column (shares 40/25/20/10/5%) and a 20-value column
(Zipf shares). Delta 1e-6. Columns are half text, half number. Run in one process through
`quality.dp.fit_dp_snapshot`, the call the CLI makes.

| Columns (queries) | Rows | epsilon 0.1 | epsilon 1 | epsilon 5 |
|---|---|---|---|---|
| 2 (4) | 500 | 0/5 | 3/5 | 5/5 |
| 2 (4) | 5,000 | 3/5 | 5/5 | 5/5 |
| 2 (4) | 50,000 | 5/5 | 5/5 | 5/5 |
| 2 (4) | 500,000 | 5/5 | 5/5 | 5/5 |
| 8 (13) | 500 | 0/5, 0/20 | 0/5, 0/20 | 4/5, 3/20 |
| 8 (13) | 5,000 | 1/5, 0/20 | 5/5, 6/20 | 5/5, 20/20 |
| 8 (13) | 50,000 | 5/5, 6/20 | 5/5, 20/20 | 5/5, 20/20 |
| 8 (13) | 500,000 | 5/5, 20/20 | 5/5, 20/20 | 5/5, 20/20 |
| 20 (31) | 500 | 0/5, 0/20 | 0/5, 0/20 | 3/5, 1/20 |
| 20 (31) | 5,000 | 0/5, 0/20 | 4/5, 3/20 | 5/5, 16/20 |
| 20 (31) | 50,000 | 4/5, 4/20 | 5/5, 20/20 | 5/5, 20/20 |
| 20 (31) | 500,000 | 5/5, 20/20 | 5/5, 20/20 | 5/5, 20/20 |

Reading it:

- At epsilon 1, about 5,000 rows are enough for a 2-column release and about 50,000 for 8 to
  20 columns.
- 500 rows is not usable beyond two columns at any epsilon up to 5.
- Columns with many values need far more data than columns with few.
- Numeric histograms hold up better: at 5,000 rows and epsilon 1 the histogram distance from
  the truth was 0.009 to 0.026 in every layout.

## Roadmap mapping

The roadmap is `docs/ROADMAP.md`. This record adds no rows; the owner decides.

| Finding | Existing row | Proposed |
|---|---|---|
| C1 | 24i GEN-C1 | Add the root cause and the `source_column` workaround to the row's notes |
| C2, H3 | none | New: numeric fit that survives outliers and skew (quantile-based or clipped buckets), and exact values for low-cardinality numerics |
| C3 | 24l (nulls only) | New: numeric similarity must not normalize by a range one value can stretch; nulls in the score |
| H1, M1, M2 | 24r touches it | New: `condition_on` cap is configurable, truncation and fallback warn, a renamed parent works |
| H2, M3 | 24l GEN-FIT-SHAPE | Add month and weekday shape |
| H4, H5 | 24o GEN-CLI, 24e | Add: report warnings in the terminal; revisit the 0.8 default |
| H6, H7 | 24f QA-FIT-REDACT | Add: numeric `min`/`max`, count-of-one labels, short free text |
| H8 | none | New: DP fit cost per CLI call |
| M4, M6 | none | New: `fit` type control (keep codes as text; say when a date parse fails) |
| M5 | none | New: one type-inference path for both fidelity surfaces |
| M7, M8 | 24b QA-GATE | Add: empty DP release refused at validate |
| M9 | engine roadmap item for artifact authentication | None. Documented limit |

## Repro notes

All commands use the certified environment. Data generators use Python `random.Random(seed)`.

**C1.** Fit any CSV with two unrelated numeric columns `a`, `b`. Generate both as
`type: statistical` with only `snapshot_file` set. Compare `corr(a, b)`. Then add
`source_column: a` and `source_column: b` and compare again.

**C2, C3, H2, H3, M3, M4.** One 20,000-row file, seed 21, columns:
`null10` (gauss 50/10, 10% blank), `null90` (A/B/C, 90% blank), `age` (int 18 to 90),
`skew` (lognormal 3/1.2), `bimodal` (gauss 20/3 or 80/3), `outlier` (gauss 100/15 with row 0
set to 1,000,000), `price` (one of 9.99, 19.99, 49.99, 99.99), `day` (three years, month
weighted to January), `bit` (0/1), `zip` (zero-padded five digits).

```bash
decoy fit types.csv --parse-dates day
```

Generate 20,000 rows with one statistical column per source column, each with
`source_column` and `allow_real_categories: true`, then:

```bash
decoy report fidelity types.csv types_out.csv --generate --json
```

**H1.** 6,000 rows, seed 11: 12 parents with weights 20, 15, 12, 10, 9, 8, 7, 6, 5, 4, 3, 1;
each parent allows three of six child values with weights 6, 3, 1.

```bash
decoy fit cond.csv --joint parent,kid --joint kid,grand
```

Generate `kid` with `condition_on: parent` and count rows whose pair is absent from the source.

**H5.** Add `fidelity_warn_threshold: 1.0` to `global_settings`, run, and search stdout,
stderr, `--json` and `logs/decoy_engine.log` for `fidelity`.

**H6, H7.** 1,000 rows, seed 31, with one row's diagnosis set to a unique code, one row's
salary set to 987,654, and a note column built from 30 surnames. Inspect the snapshot JSON.

**H8, Q9.** Time `decoy fit --epsilon 1.0 --delta 0.000001` on 500 rows with 2, 8 and 20
declared columns. For the table, loop `fit_dp_snapshot` over rows, epsilon and column count
in one process.

**M7.**

```bash
decoy fit tiny.csv --epsilon 0.02 --delta 0.000001 --dp-text state --dp-number amount:0:500 --dp-allow-omit -o tiny.dp.json
```

on a 20-row file, then `decoy validate` and `decoy run` a pipeline that samples `state`.

**M9.** Take a valid DP snapshot. (a) Append a label to a column's `top_values`. (b) Lower
`dp.epsilon_total`. (c) Take a plain snapshot, keep only the DP-declared columns, add each
column's `carrier`, empty `joints`, and copy the `dp` block. Validate and run each under a
`global_settings.dp` block.
