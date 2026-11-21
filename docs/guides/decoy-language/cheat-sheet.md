# Decoy language cheat sheet

Status: current

Syntax at a glance. For explanations see [the guide](README.md); for a complete reference in one
page see [agent-card.md](agent-card.md). Every snippet here is checked by
`tests/unit/lang/test_docs.py`.

## Skeleton

```decoy
decoy 1

pipeline my_pipeline {
  seed 42

  mask people from csv("people.csv", header: true) to csv("out/people.csv") {
    email : faker(person_email)
    ssn   : redact
    keep id
  }
}
```

```
decoy validate pipeline.decoy       check a file
decoy run pipeline.decoy            run it
```

Converting from YAML and formatting are not available from the command line yet.

## Values and names

| Write | Get |
|---|---|
| `42` `1_000` `2.5` `1e-6` | number |
| `true` `false` | boolean |
| `digits` | the word, same as `"digits"` |
| `"a\nb"` | text, JSON escapes |
| `'C:\data\in.csv'` | text, exactly as written |
| `[a, b]` `{min: 1, max: 9}` | list, map |
| `'First Name'` `'limit'` | a name with a space, or one that is a word of the language |
| `# note` | comment |

Layout is free: spaces and line breaks only separate words.

## Sources and targets

```decoy-pipeline
mask a from csv("a.csv", header: true) to parquet("out/a.parquet") { x : redact }
mask b from csv("b.txt", header: true, delimiter: "|") to csv("out/b.csv") { x : redact }
mask c from csv("c.csv", header: false, column_names: [x, y]) to csv("out/c.csv") { x : redact keep y }
mask d from s3("bucket", "raw/d.parquet", credentials: "ro") to parquet("out/d.parquet") { x : redact }
mask e from gcs("bucket", "raw/e.dat", format: csv) to csv("out/e.csv") { x : redact }
```

## Masking rules

```decoy-mask
email                 : faker(person_email)
ssn                   : redact
customer_id           : hash in customer_ids
card                  : fpe(charset: digits, validate_luhn: true) in cards
dob, admitted         : date_shift(min_days: -30, max_days: 30, date_format: "%Y-%m-%d") in dates
zip                   : truncate(length: 3)
salary                : shuffle
first_name, last_name : faker(person_name) in people deterministic
account               : faker(synthetic_account_number) in accounts deterministic vaulted
tax_id                : redact when country == 'US' and age >= 18
{given, family, mail} : faker(composite_name_email)
guess                 : faker(person_phone) ?
keep id, tier
```

After a strategy, in this order: `in <namespace>` `deterministic` `vaulted` `when <condition>`.
A trailing `?` marks a rule nobody has checked; the file does not compile until it is removed.

Reuse a rule with `let`, at the pipeline level:

```decoy-pipeline
let shift = date_shift(min_days: -30, max_days: 30, date_format: "%Y-%m-%d") in dates
mask t from csv("t.csv", header: true) to csv("out/t.csv") { dob, admitted : shift }
```

## Shaping a table (runs before masking, in order)

```decoy-mask
where status != 'TEST' and age >= 18
full_name = first_name + ' ' + last_name
sort by signup desc, id
limit 100_000
dedupe on email
dedupe
drop internal_notes
full_name : faker(person_name)
```

Expressions: `+ - * / //`, `== != < <= > >=`, `and or not`, `in [...]`, `concat(a, b)`,
`slice(s, 0, 3)`, `days_between(a, b)`, `if(cond, a, b)`. Booleans are `True` and `False` there.

## Foreign keys

```decoy-pipeline
mask customers from csv("c.csv", header: true) to csv("out/c.csv") { customer_id : hash in customer_ids }
mask orders from csv("o.csv", header: true) to csv("out/o.csv") {
  order_id    : hash in order_ids
  customer_id <- customers.customer_id orphans preserve
}
mask lines from csv("l.csv", header: true) to csv("out/l.csv") {
  order_id, customer_id <- orders.(order_id, customer_id) in order_keys orphans fail
}
```

`orphans` is required: `preserve` `remap` `warn` `fail`.

## Generating

```decoy-pipeline
generate customers rows 1000 to csv("customers.csv") {
  id    = sequence(10000, step: 1, unique: true)
  name  = faker(first_name)
  tier  = categorical({None: 0.6, Silver: 0.3, Gold: 0.1})
  spend = faker(random_int, faker_kwargs: {min: 1, max: 500})
  area  = constant("EU")
  label = concat(tier, '-', id)
}
generate orders rows 3000 to csv("orders.csv") {
  order_id    = sequence(1)
  customer_id <- customers.id
  buyer_id    = reference(customers, id)
  unique (customer_id, buyer_id)
}
```

## Pipeline-level statements

```decoy-pipeline
secret ref("env:DECOY_MASK_KEY")
unconfigured columns error
settings {
  post_validation: true
  on_pool_exhaustion: fail
}
subset {
  start customers sample 2% by customer_id
  start orders where total > 1000, status == open, closed_at is null
  start vips keys customer_id in [101, 102]
  follow customers.customer_id -> orders.customer_id downward
  budget(max_total_rows: 2_000_000)
  allow dangling
}
scan before(regex, ner)
scan after(regex, integrity: true)
expect leak_check(customers.email, min_rows: 50)
expect fk_intact
quarantine("out/quarantine.jsonl", triggers: [validation_fail])
baseline("scans/baseline.json", on_drift: warn)
delivery(strict)
namespace customer_ids for customers.customer_id, orders.customer_id
options {
  protected_quarantine: {schema_version: 1, access_policy: "ops", retention_seconds: 3600, max_rows: 1000, max_bytes: 1000000, required_protection: encrypted}
}
mask customers from csv("c.csv", header: true) to csv("out/c.csv") { customer_id : hash in customer_ids keep email }
mask orders from csv("o.csv", header: true) to csv("out/o.csv") { customer_id : hash in customer_ids keep total, status, closed_at }
mask vips from csv("v.csv", header: true) to csv("out/v.csv") { customer_id : hash in customer_ids }
```

## Names you will reach for

| Kind | Names |
|---|---|
| Strategies | `redact` `hash` `fpe` `tokenize` `faker` `date_shift` `truncate` `bucketize` `top_code` `shuffle` `categorical` `geo_generalize` `code_set` `text_redact` `text_mask` |
| `faker` providers (masking) | `person_name` `person_first_name` `person_last_name` `person_email` `person_phone` `address_street` `address_city` `address_state` `address_zip` `synthetic_ssn` `synthetic_account_number` `uuid` |
| Generators | `sequence` `faker` `categorical` `constant` `reference` `distribution` `lookup` `derived` |
| Detectors | `regex` `classifier` `ner` |
| Checks | `leak_check` `fk_intact` `no_orphan_children` `luhn` `npi` `iban` `vin` `regex_match` `column_in_set` |
| Orphan policies | `preserve` `remap` `warn` `fail` |
| Follow directions | `both` `downward` `upward` `none` |

## Common errors

| You see | Do |
|---|---|
| `is not a strategy` | Check the name; the hint suggests the nearest |
| `is a word of the language` | Quote the column name: `'limit' : redact` |
| `does not say what happens to rows with no matching parent` | Add `orphans preserve` (or `remap`, `warn`, `fail`) |
| `the parent key ... has no namespace` | Add `in <namespace>` to the parent's rule or to the link |
| `a masked table can only define a column from an expression` | Move the generator into a `generate` block |
| `this rule was inferred and has not been reviewed` | Check the rule, then delete its `?` |
| `this backslash sequence is not one the language reads` | Use single quotes, or double the backslash |
