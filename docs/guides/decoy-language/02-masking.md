# 2. Masking

Status: current

A rule is one or more columns, a colon, a strategy, and optional words after it.

```decoy
decoy 1

pipeline {
  seed 7
  secret ref("env:DECOY_MASK_KEY")

  let shift = date_shift(min_days: -30, max_days: 30, date_format: "%Y-%m-%d") in patient_dates

  mask patients from csv("patients.csv", header: true) to parquet("out/patients.parquet") {
    patient_id            : hash in patient_identity
    first_name, last_name : faker(person_name) in people deterministic
    dob, admitted         : shift
    card_number           : fpe(charset: digits, validate_luhn: true) in pan_identity vaulted
    ssn                   : redact when country == 'US'
    keep age, country
  }
}
```

## The words after a strategy

They come in this order, each optional.

| Word | What it does |
|---|---|
| `in <namespace>` | Columns in the same namespace turn equal inputs into equal outputs. Use one name across tables for values that must still match. `hash`, `fpe` and `tokenize` need one; the engine checks this when it plans the run. |
| `deterministic` | For `faker`, `categorical` and `shuffle`: equal inputs give equal outputs. Without it the value depends on the row's position. |
| `vaulted` | Records the mapping in the token vault so it can be reversed later. |
| `when <condition>` | Masks only the rows where the condition holds. |

## Reusing a rule

`let shift = ...` names a rule. Use the name bare, as `dob, admitted : shift`.

## Strategies

A strategy's options use the engine's own names, so the engine's strategy reference applies as
written. The ones used most:

| Strategy | Does |
|---|---|
| `redact` | Replaces the value with a fixed marker |
| `hash in <ns>` | A keyed hash; equal inputs match across tables |
| `fpe(charset: digits) in <ns>` | Format-preserving encryption: nine digits in, nine digits out |
| `faker(person_email)` | A realistic fake value from a provider |
| `date_shift(min_days: -30, max_days: 30, date_format: "%Y-%m-%d") in <ns>` | Moves a date by a per-value offset |
| `truncate(length: 3)` | Keeps the first characters |
| `shuffle` | Reorders the column's values among the rows |
| `keep a, b` | Leaves columns unchanged |

## Shaping the table first

These run before masking, in the order written.

```decoy
decoy 1

pipeline {
  seed 7

  mask signups from csv("signups.csv", header: true) to csv("out/signups.csv") {
    where status != 'TEST' and age >= 18
    full_name = first_name + ' ' + last_name
    sort by signup_date desc, id
    limit 100_000
    dedupe on email
    drop internal_notes

    full_name : faker(person_name)
    email     : faker(person_email)
    first_name, last_name : redact
    keep id, status, age, signup_date
  }
}
```

`name = expression` adds a column. It takes an expression only; to fill a column with generated
values, use a `generate` block ([page 4](04-generating.md)).

## Sources and targets

| Written | Reads or writes |
|---|---|
| `csv("people.csv", header: true)` | A CSV source must say `header: true` or `header: false`; there is no default. `delimiter: "\|"` is an option. Without a header: `header: false, column_names: [a, b]`. A CSV target takes no `header` |
| `parquet("people.parquet")` | A Parquet file |
| `fixed_width("people.txt", layout: {...})` | A fixed-width file |
| `s3("bucket", "path/people.parquet", credentials: "name")` | An object on S3 |
| `gcs("bucket", "path/people.csv")` | An object on Google Cloud Storage. For `s3` and `gcs` the name ends in `.csv` or `.parquet`, or the call says `format: csv` |
