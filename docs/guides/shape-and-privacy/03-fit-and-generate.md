# 3. Fit and generate

Status: current

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
| `--include-values` | Keep the real values of columns the profiler flags as sensitive. The file then holds real data. Not allowed with `--epsilon`. |

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

Every column also records its null count, non-null count and distinct count. The `fit` summary adds `, N% null` after the kind of each column that has nulls, and `fit --json` carries a `null_rates` map (column to null share). Generation keeps the source null rate unless the column sets `null_probability`.

In the sample file, `full_name` has 80 distinct values, so it is treated as
free text and only its length is kept.

**The snapshot can still be sensitive.** `fit` profiles the whole file and withholds the values of every column it flags as personal data (an SSN, a name, an id). The snapshot then carries `value_policy: flagged-redacted/v1` and lists those columns under `redacted_columns`. `fit` prints their names, never their values. A withheld number column keeps one coarse range and a withheld date column keeps years. A column the profiler does not flag still holds its real values. For a category column that looks like this:

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
Do not share a plain snapshot more widely than you would share the source.

A column the profiler does not flag keeps its values, including a rare
category and its exact largest and smallest number. In the re-test, a
30-value note column was not flagged and every note was stored word for word.

To sample a withheld column as categories, re-run with `--include-values`. The
file then holds real data and `fit` warns on stderr with the column names. A
differentially private release (`--epsilon`) never holds real values, but it
needs a certified DP install; see `decoy explain differential-privacy`.

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
      # source_column is needed on engine 0.19.0, until the engine repin.
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

On engine 0.19.0, also add `source_column: <name>` to every statistical
column, even when it matches the column's `name`. Without it, columns with the
same settings come out locked together. Fixed after engine 0.19.0; see
[the fixed defect below](#fixed-columns-move-together-when-they-should-not).

### Options for a `type: statistical` column

| Key | Meaning |
|---|---|
| `snapshot_file` | Required. Path to the snapshot. |
| `source_column` | The snapshot column to sample from. Defaults to the column's own `name`. Set it when the generated name differs from the snapshot name, or on engine 0.19.0 (see the fixed defect below). |
| `allow_real_categories: true` | Required for a category column from a plain snapshot. You are confirming that real values will appear in the output. |
| `condition_on: other_col` | Pick this column's value based on another generated column. The pair must have been fitted with `--joint`. |
| `null_probability` | Share of rows set to blank. With a snapshot that records cell formats it replaces the fitted blank rate; it is never added on top. See [blanks](#blanks). |
| `other_mode` | What to do with the "other" count: `redistribute` (default, spread it over the top values) or `emit` (output the placeholder `__other__`). |

You can mix statistical columns with any other generate type (`faker`,
`sequence`, `categorical`, `formula`) in the same table.

### How values are drawn

| Kind | Method |
|---|---|
| numeric | Pick a histogram bucket by its count, then a uniform random value inside it. With a recorded cell format the value is rounded to the source's decimal places. |
| categorical | Weighted draw from the stored values. |
| datetime | Pick a year by its count, then a random moment in that year, kept between the earliest and latest source dates. With a recorded cell format the value is cut to the source resolution, so a date-only source gives dates. |
| freetext | Pick a length from the length histogram and fill it with lorem ipsum words. |
| with `condition_on` | Draw from the row of the pair table that matches the parent value. If the parent value was never seen, fall back to the column's own distribution. |

Output is reproducible: the same seed and the same snapshot give the same file.

### Blanks

A snapshot that records each column's cell format also holds its blank rate,
and generation reproduces it. The engine writes that block after 0.19.0
(engine #434 and #436). In a re-test, 10% and 90% blank columns came out at
9.7% and 90.2%.

`null_probability` on a column replaces the fitted rate. It is not added on
top: `0` turns blanks off and `0.1` gives 10%, whatever the source had.

`decoy fit` records the cell format per column, so its snapshots carry the
blank rate.

## Step 3: check the result

```bash
decoy report fidelity customers.csv synthetic.csv --generate --joint state,tier
```

```text
REPORT ONLY (no threshold violations) grade B  overall_score 0.910
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
The report compares them as text, and the lengths differ. A snapshot with a
recorded cell format generates date-only values, which removes the mismatch.

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
  with no warning. In a re-test with 12 parent values and 36 real pairs, the
  rarest parent lost all its pairs and 43 of 6,000 rows (0.7%) had
  combinations that never occur in the source. Check the snapshot: under `joints`, compare
  `cell_count` with the number of entries in `cells`.
- A parent value that was never in the fit also falls back silently.
- Not allowed with differential privacy.

## Check your source before you fit

The fit handles some data badly, and the fidelity report will not tell you
(see [page 5](05-reading-fidelity-reports.md#what-the-report-misses)).
Measured results from [the QA record](../../records/2026-11-10-cli-qa-generation-distribution-models.md):

| Source column | What happens | What to do |
|---|---|---|
| A number column with one extreme value | The whole column is ruined. Values near 100 with one value of 1,000,000 generated a mean of 50,084, and 99.8% of rows landed above 200. | Remove or cap outliers before fitting. |
| A heavily skewed number column | The median moved from 20.5 to 92.1. | Fit a transformed column (for example a log), or generate it another way. |
| A number column with a few fixed values (prices, ratings) | Four price points became 20,000 different values, none of them a real price. With a recorded cell format they keep two decimals but are still spread out: 3,585 values, 0.08% on a real price. | Do not fit it. Generate it as a `categorical` column with the values and weights written out. |
| A column with blanks | Snapshots from older CLI versions dropped blanks (10% and 90% blank both came out 0%). Current `decoy fit` snapshots record the cell format and keep the blank rate. | See [blanks](#blanks). |
| A date column | Only the year mix is kept. 66% January became 8%. | Generate dates another way if month or weekday matters. |
| Codes with leading zeros (zip, account numbers) | Read as numbers; leading zeros are lost (10.9% of generated zips were short). | Not fixable at fit time today. Generate these with `faker` or a format rule. |
| A category held by one person | Stored with `count: 1` and can be generated. | Remove rare values before fitting, or use the DP fit. |
| A number column's largest or smallest value | Stored exactly as `max` / `min`. | Cap the column before fitting if an extreme identifies someone. |
| Short free text with 30 or fewer distinct values | Stored and generated word for word. | Drop the column, or mask it first. |

## What this method cannot do

- **Fine numeric detail.** Shape is only as fine as 10 buckets. On engine
  0.19.0 values come out with many decimals (`25.849769587687348`); a recorded
  cell format rounds them to the source's places.
- **Date patterns.** The year mix is kept. Month, weekday and time-of-day
  patterns are not. On engine 0.19.0 dates come out as full timestamps; a
  recorded cell format keeps the source resolution.
- **Free text content.** Only length is kept.
- **Links between columns** unless you fit the pair with `--joint` and use
  `condition_on`.
- **Rare categories** beyond the top 20 are lumped into "other".
- **Table relationships.** A snapshot describes one file. It does not make a
  child table follow the parent's real fan-out (for example orders per
  customer).
- **Uniqueness.** A fitted column repeats values. A `statistical` column takes no
  `unique` option. For distinct values use `unique: true` on a `faker`, `categorical`,
  `reference` or `sequence` column, or `unique_together` for a junction table (see
  `decoy explain unique`).

## Fixed: columns move together when they should not

On engine 0.19.0, two statistical columns with identical settings draw the
same random number on every row. Each column's own shape is right, but the
columns are locked together: two unrelated source columns (correlation 0.02)
came out at 0.97. The same applies to two `faker` columns with the same
`faker_type`. The cause was a column seed built from its settings with the
`name` left out.

Fixed after engine 0.19.0 (engine #421): the seed now includes the column name.
In a re-test on engine main, two columns with identical settings matched on no
rows (statistical, `pyint`) or at chance (0.4% for `first_name`), and two
unrelated statistical columns kept their source correlation (-0.01 against
-0.01).

On 0.19.0, give every statistical column an explicit `source_column` so the
settings differ. This is finding C1 in
[`docs/records/2026-11-08-cli-qa-generation.md`](../../records/2026-11-08-cli-qa-generation.md).
