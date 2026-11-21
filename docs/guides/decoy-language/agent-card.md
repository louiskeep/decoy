# The Decoy language on one page

Status: current

Everything needed to write a `.decoy` pipeline, sized to paste into a prompt. Each complete
program on this page is compiled by `tests/unit/lang/test_docs.py`, so the page cannot drift
from the compiler.

Any `decoy` command that takes a pipeline file takes a `.decoy` file, for example
`decoy validate pipeline.decoy`. Converting from YAML and formatting are not available from the
command line yet.

## Shape of a file

```decoy
decoy 1

pipeline nightly_export {
  seed 42

  mask customers from csv("in/customers.csv", header: true) to parquet("out/customers.parquet") {
    customer_id : hash in customer_identity
    email       : faker(person_email)
    ssn         : fpe(charset: digits) in ssn_identity
    notes       : redact
    keep signup_date, tier
  }
}
```

Rules that hold everywhere:

- First line `decoy 1`. One `pipeline { }` block; its name is optional. `seed <number>` is required.
- Layout is free: spaces and line breaks only separate words. Blocks use braces. Comments start with `#`.
- Every column of a masked table needs a rule or a `keep`. Columns left out are an error at run time.
- A call is `name(plain values, key: value, ...)`. Options use the engine's own names.
- Values: numbers (`1_000`, `2.5`, `1e-6`), `true`/`false`, bare words (`digits`), `"double quoted"` (JSON escapes), `'single quoted'` (taken as written, good for `'C:\data\in.csv'`), lists `[a, b]`, maps `{key: value}`.
- A name that is a word of the language, or has a space, goes in single quotes: `'First Name' : redact`, `keep 'limit'`.

## Masking a table: `mask <table> from <source> to <target> { }`

Sources and targets: `csv("path", header: true)` (a csv source must say `header: true` or `false`), `parquet("path")`, `fixed_width("path", layout: {...})`,
`s3("bucket", "path/file.parquet")`, `gcs("bucket", "path/file.csv")`. An `s3` or `gcs` name must
end in `.csv` or `.parquet`, or the call needs `format: csv` or `format: parquet`. A CSV source has
a header row; one without is `csv("p.csv", header: false, column_names: [a, b])`. Other options
pass through: `delimiter: "|"`, `credentials: "name"`.

A rule is `columns : strategy(...)` followed by optional words, in this order:

| Word | Meaning |
|---|---|
| `in <namespace>` | Columns in one namespace mask equal inputs to equal outputs. `hash`, `fpe` and `tokenize` need one (the engine checks this when it plans the run). |
| `deterministic` | For `faker`, `categorical`, `shuffle`: equal inputs give equal outputs. |
| `vaulted` | Record the mapping in the token vault so it can be reversed. |
| `when <condition>` | Mask only the rows where it holds: `when country == 'US' and age >= 18`. |

Strategies: `redact`, `hash`, `fpe`, `tokenize`, `faker(<provider>)`, `date_shift`, `truncate`,
`bucketize`, `bucket_perturb`, `top_code`, `shuffle`, `categorical`, `geo_generalize`, `code_set`,
`text_redact`, `text_mask`, `joint_mask`, `formula`, `derived`, `derived_aggregate`, `group_key`,
`grouped_series`, `windowed_date`. `keep a, b` leaves columns unchanged.

Options used most: `fpe(charset: digits)` (also `alpha`, `alphanum`, `ALPHANUM`; `validate_luhn: true`
for card numbers), `date_shift(min_days: -30, max_days: 30, date_format: "%Y-%m-%d")`, `truncate(length: 3)`,
`geo_generalize(type: zip, ...)`. `redact`, `hash` and `shuffle` need none.

Common providers for `faker`: `person_name`, `person_first_name`, `person_last_name`,
`person_email`, `person_phone`, `address_street`, `address_city`, `address_state`, `address_zip`,
`synthetic_ssn`, `synthetic_account_number`, `uuid`.

```decoy
decoy 1

pipeline {
  seed 7
  secret ref("env:DECOY_MASK_KEY")
  unconfigured columns error

  let shift = date_shift(min_days: -30, max_days: 30, date_format: "%Y-%m-%d") in patient_dates

  mask patients from csv("patients.csv", header: true, delimiter: "|") to csv("out/patients.csv") {
    where status != 'TEST' and age >= 18
    full_name = first_name + ' ' + last_name
    sort by admitted desc, patient_id
    limit 1_000_000
    dedupe on patient_id
    drop internal_notes

    patient_id         : hash in patient_identity
    first_name, last_name : faker(person_name) in people deterministic
    full_name          : faker(person_name)
    dob, admitted      : shift
    zip                : geo_generalize(type: zip, cascade: [zip5, zip3, state, suppress], k_threshold: 20000)
    card_number        : fpe(charset: digits, validate_luhn: true) in pan_identity vaulted
    ssn                : redact when country == 'US'
    keep age, status, country
  }
}
```

- `let name = rule` names a rule for reuse; use it bare (`dob : shift`).
- A rule or `keep` that ends with `?` (`email : faker(person_email) ?`) was inferred by a tool and
  has not been checked. The file does not compile until the `?` is removed.
- Shaping runs before masking, in the order written: `where <condition>`, `name = <expression>`
  (a new column), `sort by a desc, b`, `limit N`, `dedupe` or `dedupe on a, b`, `drop a, b`.
- Expressions: `+ - * / //`, comparisons, `and or not`, `in [...]`, `concat(a, b)`, `slice(s, 0, 3)`,
  `days_between(a, b)`, `if(cond, a, b)`. Inside an expression true and false are `True` and `False`.

## Joins and groups

```decoy
decoy 1

pipeline {
  seed 7

  mask customers from csv("customers.csv", header: true) to csv("out/customers.csv") {
    customer_id : hash in customer_identity
    {first_name, last_name, email} : faker(composite_name_email)
  }

  mask orders from csv("orders.csv", header: true) to csv("out/orders.csv") {
    order_id    : hash in order_identity
    customer_id <- customers.customer_id orphans preserve
    keep total
  }

  mask order_lines from csv("lines.csv", header: true) to csv("out/lines.csv") {
    order_id, customer_id <- orders.(order_id, customer_id) in order_keys orphans fail
    keep sku, quantity
  }
}
```

- `child <- table.key orphans <policy>` is a foreign key: the child takes the parent key's masked
  value. `orphans` is required: `preserve`, `remap`, `warn` or `fail`. The parent key needs a
  namespace, or put `in <namespace>` on the link.
- `{a, b, c} : faker(<composite provider>)` keeps those columns consistent within a row.

## Generating a table: `generate <table> rows <N> to <target> { }`

```decoy
decoy 1

pipeline {
  seed 42

  generate customers rows 1000 to csv("customers.csv") {
    customer_id = sequence(10000, step: 1, unique: true)
    first_name  = faker(first_name)
    email       = faker(email)
    tier        = categorical({None: 0.6, Silver: 0.3, Gold: 0.1})
    spend       = faker(random_int, faker_kwargs: {min: 1, max: 500})
    label       = concat(tier, '-', customer_id)
  }

  generate orders rows 3000 to csv("orders.csv") {
    order_id    = sequence(1)
    customer_id <- customers.customer_id
    placed_on   = faker(date_this_year)
    status      = categorical({New: 0.2, Paid: 0.5, Shipped: 0.3})
  }
}
```

- `name = generator(...)`: `sequence(start)`, `faker(faker_type)`, `categorical({value: weight})`,
  `constant(value)`, `reference(table, column)`, `distribution(family)`, `lookup(...)`,
  `statistical(snapshot_file)`, `windowed_date(anchor, max_days)`, `grouped_series(group_by, order_by)`,
  `group_key(group_by)`, `derived_aggregate(op, column)`, `formula(formula)`.
- `name <- table.column` draws values from another generated table. `name = <expression>` is a
  computed column. `unique (a, b)` stops a pair of reference columns repeating.
- A masked table cannot hold a generator; use a `generate` block.

## Pipeline-level statements

```decoy
decoy 1

pipeline {
  seed 42

  settings {
    post_validation: true
    on_pool_exhaustion: fail
  }

  subset {
    start customers sample 2% by customer_id
    start orders where total > 1000, status == open, closed_at is null
    follow customers.customer_id -> orders.customer_id downward
    budget(max_total_rows: 2_000_000)
  }

  scan before(regex)
  scan after(regex, integrity: true)
  expect leak_check(customers.email, min_rows: 50)
  expect fk_intact
  quarantine("out/quarantine.jsonl", triggers: [validation_fail])
  delivery(strict)
  namespace customer_identity for customers.customer_id, orders.customer_id

  mask customers from csv("customers.csv", header: true) to csv("out/customers.csv") {
    customer_id : hash in customer_identity
    email       : faker(person_email)
  }

  mask orders from csv("orders.csv", header: true) to csv("out/orders.csv") {
    customer_id : hash in customer_identity
    keep total, status, closed_at
  }

  options {
    protected_quarantine: {schema_version: 1, access_policy: "ops", retention_seconds: 3600, max_rows: 1000, max_bytes: 1000000, required_protection: encrypted}
  }
}
```

- `settings { }` takes any pipeline setting by its engine name.
- `subset { }`: `start <table> sample N% by key` or `sample N rows by key`; `start <table> where`
  with simple tests (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in [...]`, `is null`, `is not null`)
  separated by commas; `start <table> keys key in [1, 2]`; `follow parent.key -> child.key`
  with `both`, `downward`, `upward` or `none`; `budget(...)`; `allow dangling`. A subset follows
  every foreign key both ways unless a `follow` line says otherwise, so `follow` is optional.
- `scan before(...)` and `scan after(...)` take detectors. `regex` is always one of them; `ner` and
  `classifier` are added to it: `scan before(regex, ner)`. After masking, any detector beyond
  `regex` needs `integrity: true`.
- `expect <check>(table.column, key: value)`: `leak_check`, `fk_intact`, `no_orphan_children`,
  `luhn`, `npi`, `iban`, `vin`, `regex_match`, `column_in_set`.
- `quarantine("path", triggers: [...])`, `baseline("path", on_drift: warn)`, `delivery(strict)` or
  `delivery(best_effort)`, `namespace <name> for table.column, ...`.
- `options { }` takes any top-level config block that has no statement of its own.

## Mistakes the compiler catches, and the fix

| Message | Fix |
|---|---|
| `is not a strategy` | Check the list above; the hint suggests the nearest name. |
| `is a word of the language` | Put the column name in single quotes. |
| `does not say what happens to rows with no matching parent` | Add `orphans preserve`, `remap`, `warn` or `fail`. |
| `the parent key ... has no namespace` | Add `in <namespace>` to the parent column's rule or to the link. |
| `a masked table can only define a column from an expression` | Move the generator to a `generate` block. |
| `this backslash sequence is not one the language reads` | Use single quotes, or double the backslash. |
