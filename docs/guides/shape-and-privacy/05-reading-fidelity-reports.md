# 5. Reading fidelity reports

[Back to the guide index](README.md)

What the numbers from `decoy report fidelity` and `decoy run --fidelity` mean.

## The first line

```text
PASS grade B  overall_score 0.911
```

| Part | Meaning |
|---|---|
| `PASS` / `WARN` / `FAIL` | The policy verdict. In the default `report` mode it is always PASS, whatever the score. |
| `grade` | A letter for the overall score. |
| `overall_score` | 0 to 1. 1 means the output's shape matches the source. |

So `PASS grade F` is possible and is not a contradiction. PASS means "no rule
you set was broken". With no rules set, nothing can be broken. Set `--mode` and
a threshold to make the verdict mean something
([page 2](02-check-shape-after-masking.md#make-the-check-fail-a-script)).

## Grades

| Grade | Overall score |
|---|---|
| A | 0.95 and up |
| B | 0.85 to 0.95 |
| C | 0.70 to 0.85 |
| D | 0.50 to 0.70 |
| F | below 0.50 |
| unavailable | No columns could be compared |

## Is a high score good?

It depends on what you are doing.

| Job | Column | What you want |
|---|---|---|
| Masking | Kept on purpose (`passthrough`, `shuffle`) | High |
| Masking | Replaced on purpose (`faker`, `hash`, `redact`) | Low is expected |
| Generation | Statistical columns | High |
| Any | Sensitive identifiers | A high score is a warning sign, not a success |

The score measures similarity. It never measures privacy. A straight copy of
the source scores 1.0.

For masking jobs, the overall grade mixes columns you meant to keep with
columns you meant to destroy, so read the per-column table, not the grade.

## How each column type is scored

The report works out each column's type from the CSV, then compares a summary
of the source column with a summary of the output column.

| Column type | Compared by | In the JSON as |
|---|---|---|
| Number | How far apart the 5th, 25th, 50th, 75th and 95th percentiles are, relative to the source's range | `quantile_rmse` |
| Category, true/false | The share of rows in each value, source against output | `tvd` |
| Date (when typed as a date) | The share of rows in each year | `tvd` |
| Free text (more than 30 distinct values) | Average text length only | `length_mean_diff` |

Things that follow from this:

- A free-text score says nothing about content. Real names replaced by fake
  names of similar length score high.
- The category score compares actual values. `CA` hashed to `9f2c...` shares no
  values with the source, so it scores near 0 even though the frequencies are
  intact.
- `decoy report fidelity` reads plain CSV and does not parse dates, so date
  columns are scored as text length. A date written in a different format
  scores low for that reason alone.

### "Comparable: no"

A column is skipped, and left out of the overall score, when:

- It is empty on either side.
- Its type differs between source and output (a number column hashed to text).
- It exists on one side only.

## What the report misses

A good grade does not mean the data is right. In testing, a generated file with
these faults got grade B and "OK no policy violations"
([QA record](../../records/2026-11-10-cli-qa-generation-distribution-models.md)):

| Fault | Score for that column |
|---|---|
| One outlier moved the mean from 150 to 49,940 | 0.940 |
| Median moved from 19.9 to 91.5 | 0.968 |
| Four fixed prices became 20,000 different values | 0.935 |
| 10% blanks became 0% | 0.996 |
| 90% blanks became 0% | 0.997 |
| Two unrelated number columns locked together | pair score 0.986 |

Why:

- A number column's score is measured relative to the source's full range. One
  extreme value makes the range huge, so every error looks small.
- Blanks are not part of any score.
- The printed output shows scores only. Warnings such as `null_drift` and
  `kind_drift` are in the JSON, not on screen.

What to do:

- Always look at `--json` or `--report-out`, and read `warnings` and
  `diagnostic`.
- For number columns, also read `shape_fidelity`. It scored the outlier column
  0.102 where the main score said 0.940.
- Gate on structure as well as score:

  ```yaml
  mode: fail
  thresholds:
    diagnostic: {required: true}
    overall: {min: 0.90}
  ```

- Compare a few plain statistics yourself (mean, median, blank rate, distinct
  count) for the columns that matter.

## Marginal, pairwise and overall

- **Marginal** means one column on its own. The marginal score is the average
  of the comparable columns.
- **Pairwise** scores a pair of columns you named with `--joint a,b`: how often
  each combination of values occurs.
- **Overall** is the average of the marginal and pairwise scores. With no
  `--joint`, it equals the marginal score.

Pairs are the only way to see whether relationships between columns survived.
Without `--joint`, a file can score A with every cross-column link broken.

## The JSON report

`--json` or `--report-out report.json` gives the full report. Useful fields:

| Field | Content |
|---|---|
| `overall_score`, `grade` | As printed |
| `marginal.columns[]` | Per column: `similarity`, `method`, `comparable`, `extra_metrics` |
| `pairwise` | Per-pair scores |
| `diagnostic` | Structural checks: missing columns, row count, type changes |
| `warnings` | For example `column_survival` listing columns missing from the output |
| `omissions` | Columns left out of the score, with a reason |
| `shape_fidelity` | A second scoring that ignores what the values are and compares only the pattern of frequencies |
| `policy` | `verdict`, `mode`, `violations[]` |

`extra_metrics` holds two standard statistics alongside the main score:

- `ks_complement` for number columns (1 minus the largest gap between the two
  cumulative distributions).
- `chi_cramers_v` for category columns (1 minus Cramer's V from a chi-square
  comparison).

They are extra detail. They do not change the score or the grade.

`shape_fidelity` is the place to look for `hash`, `fpe` and `tokenize`
columns. It scores them high when the frequency pattern is intact, where the
main score reads near 0.

The report holds scores and counts only. It contains no values from your data.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Verdict pass, or warn without `--fail-on-warning` |
| 1 | Bad input: missing file, unreadable CSV, conflicting flags |
| 4 | Verdict fail, or warn with `--fail-on-warning` |
