# 2. Check shape after masking

Status: current

[Back to the guide index](README.md)

Masking changes values. Some strategies keep a column's shape, some change it
on purpose. This page shows what to expect and how to measure it.

## What each strategy does to a column's shape

| Strategy | Effect on the column's distribution |
|---|---|
| `passthrough` | Unchanged. |
| `shuffle` | Same values and same counts. The link between this column and the rest of the row is broken. |
| `hash`, `fpe`, `tokenize` | Values change, but each distinct input maps to one distinct output. The number of distinct values and their frequencies are kept. |
| `date_shift` | Each date moves by an offset inside the range you set. The overall shape is kept, shifted slightly. |
| `bucketize`, `truncate`, `geo_generalize`, `bucket_perturb` | Many values collapse into fewer, coarser ones. |
| `faker`, `categorical` without source weights | The source distribution is not carried over. |
| `redact`, `text_redact` | Collapses to a constant or near-constant. |
| `formula`, `derived`, `text_mask` | Depends on your configuration. |

A low score on a `faker`, `hash` or `redact` column is the strategy working as
intended. It is not a defect.

## Example pipeline

`mask.yaml`:

```yaml
version: 2
global_settings:
  seed: 42
  mask_secret_ref: env:DECOY_MASK_SECRET
sources:
  customers:
    type: file
    format: csv
    path: ./customers.csv
tables:
  - name: customers
    columns:
      - name: customer_id
        strategy: hash
        namespace: customer_ids
      - name: full_name
        strategy: faker
        provider: person_name
      - name: email
        strategy: faker
        provider: person_email
      - name: state
        strategy: passthrough
      - name: tier
        strategy: shuffle
      - name: amount
        strategy: bucketize
        provider_config:
          width: 50
      - name: signup_date
        strategy: date_shift
        namespace: customer_dates
        provider_config:
          min_days: -30
          max_days: 30
      - name: is_active
        strategy: passthrough
targets:
  customers:
    type: file
    format: csv
    path: ./masked.csv
```

`hash` and `date_shift` are keyed, so the run needs a mask secret:

```bash
export DECOY_MASK_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
```

```bash
decoy validate mask.yaml
```

## Option A: a quick check during the run

```bash
decoy run mask.yaml --fidelity
```

```text
Fidelity (quick inline check)

 Table       Grade   Overall score
 ─────────────────────────────────
 customers   C       0.833

  Note: a quick marginal check; a low grade does not fail the run. For the fuller post-hoc grade,
run decoy report fidelity .
```

- One line per masked table. Single columns only, no column pairs.
- It never changes the exit code.
- It is not available with `--chunked`.
- On a generate-only pipeline it prints that no mask-table report was produced.

## Option B: the full report after the run

```bash
decoy report fidelity customers.csv masked.csv --config mask.yaml
```

```text
PASS grade A  overall_score 0.962
           Marginal fidelity

 Column        Comparable   Similarity
 ─────────────────────────────────────
 amount        yes          0.946
 customer_id   no           n/a
 email         yes          0.938
 full_name     yes          0.852
 is_active     yes          1.000
 signup_date   yes          1.000
 state         yes          1.000
 tier          yes          1.000

OK no policy violations.
```

How to read this result:

- `state`, `tier`, `is_active` score 1.000. Passthrough and shuffle keep the
  exact counts.
- `customer_id` is "not comparable". The source column is a number and the
  hashed output is text, so there is nothing to compare. It is left out of the
  overall score.
- `full_name` and `email` are compared by text length only (see
  [page 5](05-reading-fidelity-reports.md#how-each-column-type-is-scored)).
  A high score here says the fake names are about as long as the real ones. It
  says nothing about whether real names leaked.
- `signup_date` scores 1.000 for the same reason: this command reads both CSVs
  without date parsing, so the column is compared as text of equal length.

### Why the two grades differ

The inline check gave C (0.833) and the full report gave A (0.962) on the same
run. The inline check runs inside the engine on the loaded tables. The report
command re-reads both CSV files from disk and infers column types again, so a
column can be scored by a different method. Use the inline check as a smoke
test and `decoy report fidelity` as the number you keep.

### Tell the report what you intended

`--config mask.yaml` passes each column's strategy to the report, so expected
loss is not flagged as drift. Each strategy has a default minimum similarity
(for example `shuffle` 0.85, `bucketize` 0.30, `faker` 0.05). Without
`--config`, no per-column minimums apply.

### Check column pairs

Masking a column can break its link to another column. `shuffle` always does.
Add `--joint` to score a pair:

```bash
decoy report fidelity customers.csv masked.csv --config mask.yaml --joint state,tier
```

In this run the pair scored 0.66 while `state` and `tier` each scored 1.000 on
their own. Shuffling `tier` kept its counts and broke its link to `state`.

## Make the check fail a script

By default the command only reports, and exits 0. To gate on the result, set a
mode and a threshold.

```bash
decoy report fidelity customers.csv masked.csv --mode fail --min-score 0.99
```

```text
 Check     Column   Expected   Actual
 ──────────────────────────────────────
 overall   -        0.99       0.962188
```

This exits with code 4.

| Flag | Effect |
|---|---|
| `--mode report` (default) | Record only. Verdict is always pass. Exit 0. |
| `--mode warn` | Violations give a WARN verdict. Exit 0, or 4 with `--fail-on-warning`. |
| `--mode fail` | Violations give a FAIL verdict. Exit 4. |
| `--min-grade A\|B\|C\|D` | Minimum letter grade. Use this or `--min-score`, not both. |
| `--min-score 0.9` | Minimum overall score. |
| `--policy FILE` | A YAML or JSON policy file. Overrides the three flags above. |
| `--report-out FILE` | Write the full JSON report to disk. |
| `--json` | Print the full JSON report. |

### Policy file

```yaml
mode: fail
thresholds:
  overall:
    min: 0.90
  columns:
    amount: 0.99
```

```bash
decoy report fidelity customers.csv masked.csv --config mask.yaml --policy policy.yaml
```

```text
 Check    Column   Expected   Actual
 ─────────────────────────────────────
 column   amount   0.99       0.945568
```

Supported keys: `mode`, `thresholds.overall.min`, `thresholds.marginal.min`,
`thresholds.pairwise.min`, `thresholds.columns` (column name to minimum),
`thresholds.diagnostic.required`, and `strategy_expectations` (strategy name to
minimum).

Check the key names carefully. A key the policy does not recognize is ignored
without an error, and the check passes.

## Limits

- `decoy report fidelity` reads CSV files only.
- It has no `--parse-dates` option. Date columns are compared as text.
- Masked output has no formal privacy guarantee, whatever the score.
