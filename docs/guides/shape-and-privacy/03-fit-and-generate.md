# 3. Fit and generate

[Back to the guide index](README.md)

Make new rows that follow the shape of a real file. Three steps: fit, generate,
check.

This page covers the plain (exact) fit. It has no privacy guarantee. For the
private version see [page 4](04-differential-privacy.md).

## Step 1: fit a snapshot

```bash
decoy fit customers.csv --parse-dates signup_date --joint state,tier
```

```text
OK customers.snapshot.json
  500 rows; columns: customer_id (numeric), full_name (freetext), email
(freetext), state (categorical), tier (categorical), amount (numeric),
signup_date (datetime), is_active (categorical)
  joints captured: statextier
```

| Flag | Use |
|---|---|
| `-o, --output PATH` | Where to write the snapshot. Default is `<source>.snapshot.json`. |
| `--parse-dates COL` | Treat a column as dates. Repeatable. CSV has no types, so you must name date columns. |
| `--joint a,b` | Also record how two columns go together. Repeatable. Needed for `condition_on`. |

The source must be a CSV. The snapshot file is written readable by its owner
only (mode 0600).

### What is in a snapshot

`fit` stores a summary per column. The kind of column decides what is stored.

| Column kind | When | What is stored |
|---|---|---|
| numeric | Number columns | min, max, mean, standard deviation, five percentiles (5, 25, 50, 75, 95), and a 10-bucket histogram |
| categorical | Text columns with 30 or fewer distinct values, and true/false columns | The 20 most common values with exact counts, plus one "other" count |
| datetime | Columns named with `--parse-dates` | Earliest date, latest date, and a count per year |
| freetext | Text columns with more than 30 distinct values | Text length statistics only. No content. |
| joint | Pairs named with `--joint` | A table of how often each pair of values occurs |

Every column also records its null count, non-null count and distinct count.

In the sample file, `full_name` has 80 distinct values, so it is treated as
free text and only its length is kept.

**The snapshot is sensitive.** For a category column it holds the real values:

```json
"state": {
  "kind": "categorical",
  "stats": {
    "top_values": [
      {"value": "CA", "count": 216},
      {"value": "TX", "count": 117},
      {"value": "NY", "count": 99},
      {"value": "FL", "count": 45},
      {"value": "WA", "count": 23}
    ],
    "other_count": 0
  }
}
```

State codes are harmless. A column of 25 surnames or diagnosis codes is not.
`fit` prints no warning about this. Do not share a plain snapshot more widely
than you would share the source.

## Step 2: generate from the snapshot

`gen.yaml`:

```yaml
version: 2
global_settings:
  seed: 42
sources: {}
tables:
  - name: synthetic
    row_count: 500
    generate_columns:
      - name: customer_id
        type: sequence
        start: 1
        step: 1
      - name: full_name
        type: faker
        faker_type: name
      - name: state
        type: statistical
        source_column: state
        snapshot_file: customers.snapshot.json
        allow_real_categories: true
      - name: tier
        type: statistical
        source_column: tier
        snapshot_file: customers.snapshot.json
        allow_real_categories: true
        condition_on: state
      - name: amount
        type: statistical
        source_column: amount
        snapshot_file: customers.snapshot.json
      - name: signup_date
        type: statistical
        source_column: signup_date
        snapshot_file: customers.snapshot.json
targets:
  synthetic:
    type: file
    format: csv
    path: ./synthetic.csv
```

```bash
decoy validate gen.yaml
```

```bash
decoy run gen.yaml
```

```text
customer_id,full_name,state,tier,amount,signup_date
1,Javier Cruz,TX,silver,25.849769587687348,2023-06-28 06:34:49.426341
2,Marilyn Mclaughlin,TX,bronze,79.2657871313156,2022-09-25 02:46:11.246438
```

Always set `source_column` on every statistical column, even when it matches
the column's `name`. Without it, columns come out wrongly correlated. See
[the known defect below](#known-defect-columns-move-together-when-they-should-not).

### Options for a `type: statistical` column

| Key | Meaning |
|---|---|
| `snapshot_file` | Required. Path to the snapshot. |
| `source_column` | The snapshot column to sample from. Defaults to the column's own `name`, but set it anyway (see the known defect below). |
| `allow_real_categories: true` | Required for a category column from a plain snapshot. You are confirming that real values will appear in the output. |
| `condition_on: other_col` | Pick this column's value based on another generated column. The pair must have been fitted with `--joint`. |
| `other_mode` | What to do with the "other" count: `redistribute` (default, spread it over the top values) or `emit` (output the placeholder `__other__`). |

You can mix statistical columns with any other generate type (`faker`,
`sequence`, `categorical`, `formula`) in the same table.

### How values are drawn

| Kind | Method |
|---|---|
| numeric | Pick a histogram bucket by its count, then a uniform random value inside it. |
| categorical | Weighted draw from the stored values. |
| datetime | Pick a year by its count, then a random moment in that year, kept between the earliest and latest source dates. |
| freetext | Pick a length from the length histogram and fill it with lorem ipsum words. |
| with `condition_on` | Draw from the row of the pair table that matches the parent value. If the parent value was never seen, fall back to the column's own distribution. |

Output is reproducible: the same seed and the same snapshot give the same file.

## Step 3: check the result

```bash
decoy report fidelity customers.csv synthetic.csv --generate --joint state,tier
```

```text
PASS grade B  overall_score 0.910
           Marginal fidelity

 Column        Comparable   Similarity
 ─────────────────────────────────────
 amount        yes          0.990
 customer_id   yes          1.000
 full_name     yes          0.799
 signup_date   yes          0.385
 state         yes          0.968
 tier          yes          0.992

          Pairwise fidelity

 Joint        Comparable   Similarity
 ────────────────────────────────────
 statextier   yes          0.964

OK no policy violations.
```

`--generate` tells the report that row counts may differ.

The low `signup_date` score is a reporting artifact, not a generation fault.
The source has `2022-10-02` and the output has `2023-06-28 06:34:49.426341`.
The report compares them as text, and the lengths differ.

## Using `condition_on`

`condition_on` makes one category column depend on another, so real
combinations carry over and impossible ones do not appear.

1. Fit the pair: `decoy fit customers.csv --joint state,tier`.
2. Declare the parent column first, then put `condition_on: state` on the child.

For each row, the child is drawn only from the values seen with that row's
parent value. In the sample data no Florida customer is gold, and none is
generated.

Rules:

- The child must be a category column. One parent per column. Chains work
  (`tier` on `state`, then `plan` on `tier`).
- The parent's generated `name` must equal its name in the snapshot. A renamed
  parent cannot be conditioned on.
- **Only the 25 most common pairs are kept.** A parent value whose pairs all
  fall outside the top 25 is drawn from the child's overall counts instead,
  with no warning. In a test with 36 real pairs this produced combinations that
  never occur in the source. Check the snapshot: under `joints`, compare
  `cell_count` with the number of entries in `cells`.
- A parent value that was never in the fit also falls back silently.
- Not allowed with differential privacy.

## Check your source before you fit

The fit handles some data badly, and the fidelity report will not tell you
(see [page 5](05-reading-fidelity-reports.md#what-the-report-misses)).
Measured results from [the QA record](../../records/2026-11-10-cli-qa-generation-distribution-models.md):

| Source column | What happens | What to do |
|---|---|---|
| A number column with one extreme value | The whole column is ruined. Values near 100 with one value of 1,000,000 generated a mean of 49,940. | Remove or cap outliers before fitting. |
| A heavily skewed number column | The median moved from 19.9 to 91.5. | Fit a transformed column (for example a log), or generate it another way. |
| A number column with a few fixed values (prices, ratings) | Four price points became 20,000 different values. | Do not fit it. Generate it as a `categorical` column with the values and weights written out. |
| A column with blanks | Blanks are not reproduced: 10% and 90% blank both came out 0%. | Add `null_probability` to the generate column yourself. |
| A date column | Only the year mix is kept. 66% January became 9%. | Generate dates another way if month or weekday matters. |
| Codes with leading zeros (zip, account numbers) | Read as numbers; leading zeros are lost. | Not fixable at fit time today. Generate these with `faker` or a format rule. |
| A category held by one person | Stored with `count: 1` and can be generated. | Remove rare values before fitting, or use the DP fit. |
| A number column's largest or smallest value | Stored exactly as `max` / `min`. | Cap the column before fitting if an extreme identifies someone. |
| Short free text with 30 or fewer distinct values | Stored and generated word for word. | Drop the column, or mask it first. |

## What this method cannot do

- **Fine numeric detail.** Shape is only as fine as 10 buckets. Values come out
  with many decimals (`25.849769587687348`), not the source's two.
- **Date patterns.** The year mix is kept. Month, weekday and time-of-day
  patterns are not. Dates come out as full timestamps.
- **Free text content.** Only length is kept.
- **Links between columns** unless you fit the pair with `--joint` and use
  `condition_on`.
- **Null rates.** Blanks in the source are not reproduced in the output.
- **Rare categories** beyond the top 20 are lumped into "other".
- **Table relationships.** A snapshot describes one file. It does not make a
  child table follow the parent's real fan-out (for example orders per
  customer).
- **Uniqueness.** There is no control to force unique generated values.

## Known defect: columns move together when they should not

Two statistical columns with identical settings draw the same random number on
every row. Each column's own shape is still right, but the columns are locked
together. In a test with two unrelated source columns (correlation 0.02), the
generated columns had a correlation of 0.97, and two unrelated category
columns came out as near-functions of each other.

**Cause.** A column's random seed is built from its settings, and the column's
`name` is deliberately left out of that. Two columns that differ only by name
(same `type`, same `snapshot_file`) get the same seed.

**Workaround.** Give every statistical column an explicit `source_column`. That
makes the settings differ, so the seeds differ:

```yaml
      - name: state
        type: statistical
        source_column: state
        snapshot_file: customers.snapshot.json
        allow_real_categories: true
```

With that one line per column, the same test gave a correlation of 0.02 and
the category pair scored 0.964 against the source.

The same cause affects other generate types: two `faker` columns with the same
`faker_type` produce identical values. This is recorded as finding C1 in
[`docs/records/2026-11-08-cli-qa-generation.md`](../../records/2026-11-08-cli-qa-generation.md).

**Detecting it.** `decoy report fidelity` only partly catches it. With
`--joint`, the unrelated category pair scored 0.649, a visible drop. The
unrelated number pair still scored 0.986. Check number pairs yourself, for
example with a correlation in pandas.
