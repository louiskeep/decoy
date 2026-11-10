# 4. Differential privacy

Status: current

[Back to the guide index](README.md)

A private version of [fit and generate](03-fit-and-generate.md). The snapshot
holds noisy counts instead of exact ones, so it and anything generated from it
carry a mathematical privacy guarantee.

## The idea in plain terms

Published statistics can leak. If you know everyone in a table except one
person, an exact average tells you that person's value. Differential privacy
(DP) adds a small amount of random noise to each released number. The result is
nearly the same whether or not any one person's row was in the data, so no
individual can be picked out.

Two settings control it:

- **epsilon** is the privacy budget. Smaller means more noise and stronger
  privacy. Larger means more accuracy and weaker privacy.
- **delta** is a very small allowed chance that the guarantee does not hold.
  A common choice is one in a million.

## What is covered and what is not

| Covered | Not covered |
|---|---|
| Each number column's histogram | Links between columns |
| Each category column's value counts | `condition_on` and `--joint` |
| True/false columns | Date columns |
| The row count | Free-text columns |
| Rows generated only from a verified DP snapshot | Masked output, plain snapshots |

The guarantee is per column. It says each column's shape is private. It does
not say the whole dataset is private, and it does not protect relationships
between columns.

## Before you start: the certified environment

A DP fit only runs on a software setup that the guarantee was tested against:
Linux on x86-64, CPython 3.10.20, and an exact set of package versions. On any
other setup it refuses:

```text
error: dp_stack_uncertified: no certified proof-stack row for (cpython '3.10.20.final', fingerprint '8c79...') ... The installed distribution set does not match a tested lock, so the fit refuses.
  hint: this host is not a certified DP platform/stack.
```

That is exit code 3. A normal `pip install decoy-cli` produces this error,
because its package set differs from the tested one.

To build the certified environment, work from a checkout of the `decoy` repo at
the release you run. The steps match the certified CI job.

Build the CLI wheel from the checkout:

```bash
git clone https://github.com/louiskeep/decoy.git && cd decoy
```

```bash
uv build --wheel
```

Create a fresh virtual environment with nothing else in it:

```bash
uv venv --python 3.10.20 dp-env
```

```bash
source dp-env/bin/activate
```

Install the engine from its git tag and the CLI wheel, with no dependencies:

```bash
uv pip install --no-deps "git+https://github.com/louiskeep/decoy-engine@v0.19.0" dist/*.whl
```

Install the pinned set from the lock file at the root of the checkout:

```bash
uv pip install -r requirements-certified.txt
```

The engine is not on PyPI, so it installs from its git tag (the same form
`pyproject.toml` and CI use). `--no-deps` keeps the resolver from adding
packages; the last command installs the full certified set. Use the engine tag
that the checkout's `pyproject.toml` pins.
Its header names the exact fingerprint the set produces.

This guide was run from source checkouts instead: `uv pip install --no-deps
<engine-path> <cli-path>`, then the requirements file. That produced the
certified fingerprint and a working DP fit.

Rules for this environment:

- Do not install anything else into it. One extra package changes the
  fingerprint and the fit refuses again.
- Only the fit needs it. Generating from a DP snapshot works on an ordinary
  install and gives byte-identical output.
- macOS, Windows and ARM are not certified. Use a Linux x86-64 machine or
  container.

## Step 1: run the DP fit

Every column you release must be declared with a type:

| Flag | For | Example |
|---|---|---|
| `--dp-number COL:LO:HI` | A number column, with its allowed range | `--dp-number amount:0:500` |
| `--dp-text COL` | A category column | `--dp-text state` |
| `--dp-flag COL` | A true/false column | `--dp-flag is_active` |

```bash
decoy fit customers.csv --epsilon 1.0 --delta 0.000001 \
    --dp-number amount:0:500 --dp-text state --dp-text tier --dp-flag is_active \
    --dp-allow-omit -o customers.dp.json
```

```text
notice: omitting 4 undeclared source column(s) from the DP release: customer_id, email, full_name, signup_date.
OK customers.dp.json
  499 rows; columns: amount (numeric), is_active (categorical), state (categorical), tier
(categorical)
  DP release: dps-marginal/v3, epsilon=1.0, delta=1e-06
```

The row count says 499, not 500. It is noisy too.

Rules:

- `--epsilon` turns DP mode on. `--delta` is required with it and has no
  default.
- **Choose the number range yourself**, from general knowledge of the field
  ("order amounts are between 0 and 500"). Do not read the minimum and maximum
  off the data. Values outside the range are clamped to it.
- Columns you do not declare are an error, unless you pass `--dp-allow-omit`.
  Then they are left out and listed.
- `--joint` and `--parse-dates` cannot be used with `--epsilon`.
- `--numeric-bins N` sets the number of histogram buckets (default 10).

A `--dp-text` column releases only real text cells. A `--dp-flag` column
releases only values that are exactly true/false or 1/0; the text `"1"` counts
as empty.

## Step 2: generate

Declare the privacy budget in the pipeline. This is a ceiling the run enforces.

```yaml
version: 2
global_settings:
  seed: 42
  dp:
    epsilon: 1.0
    delta: 0.000001
sources: {}
tables:
  - name: synthetic_dp
    row_count: 500
    generate_columns:
      # source_column is needed on engine 0.19.0, until the engine repin.
      - name: state
        type: statistical
        source_column: state
        snapshot_file: customers.dp.json
      - name: tier
        type: statistical
        source_column: tier
        snapshot_file: customers.dp.json
      - name: amount
        type: statistical
        source_column: amount
        snapshot_file: customers.dp.json
      - name: is_active
        type: statistical
        source_column: is_active
        snapshot_file: customers.dp.json
targets:
  synthetic_dp:
    type: file
    format: csv
    path: ./synthetic_dp.csv
```

```bash
decoy validate gen_dp.yaml
```

```bash
decoy run gen_dp.yaml
```

With a `dp:` block present, validation rejects anything that would break the
guarantee:

- A snapshot that is not a DP release.
- `allow_real_categories: true`, `high_cardinality: true` or `condition_on` on
  a statistical column.
- Snapshots whose combined privacy cost is more than the ceiling. Using two
  different DP snapshots adds their costs. Using one snapshot for many columns
  counts once.

Write `delta` as a plain decimal in YAML. `1e-6` is read as text and fails
validation; `0.000001` or `1.0e-6` works.

## Expect accuracy to depend on data size

Noise is roughly the same size whatever the row count, so it matters much more
on small data. The budget is also shared between all the released columns, so
more columns means more noise each.

### How much data you need

Category values that survived, for a column with 5 values and a column with 20
values, delta one in a million. Each cell is one random draw, so a cell near
the cut-off can come out differently on another run; read the table as a guide,
not a bound. Full method in
[the QA record](../../records/2026-11-10-cli-qa-generation-distribution-models.md).

| Columns released | Rows | epsilon 0.1 | epsilon 1 | epsilon 5 |
|---|---|---|---|---|
| 2 | 500 | 0 of 5 | 3 of 5 | 5 of 5 |
| 2 | 5,000 | 3 of 5 | 5 of 5 | 5 of 5 |
| 2 | 50,000 | 5 of 5 | 5 of 5 | 5 of 5 |
| 8 | 500 | 0 of 5, 0 of 20 | 0 of 5, 0 of 20 | 4 of 5, 3 of 20 |
| 8 | 5,000 | 1 of 5, 0 of 20 | 5 of 5, 6 of 20 | 5 of 5, 20 of 20 |
| 8 | 50,000 | 5 of 5, 6 of 20 | 5 of 5, 20 of 20 | 5 of 5, 20 of 20 |
| 20 | 500 | 0 of 5, 0 of 20 | 0 of 5, 0 of 20 | 3 of 5, 1 of 20 |
| 20 | 5,000 | 0 of 5, 0 of 20 | 4 of 5, 3 of 20 | 5 of 5, 16 of 20 |
| 20 | 50,000 | 4 of 5, 4 of 20 | 5 of 5, 20 of 20 | 5 of 5, 20 of 20 |

At 500,000 rows every value survived in every case.

Rules of thumb at epsilon 1:

- About 5,000 rows for a release of two columns.
- About 50,000 rows for 8 to 20 columns.
- A column with many distinct values needs far more data than one with few.
- Number columns hold up better than category columns.

A value is only released when its noisy count clears a safety threshold,
because a rare value can identify the few people who have it. On the 500-row
sample at epsilon 1.0, three of the five states and the `false` label were
dropped, and the generated file scored grade C (0.732).

### An empty release

With very little data, a release can contain no values at all, and its row
count can be far from the truth (20 real rows were reported as 318). Such a
snapshot passes `decoy validate` and then fails at `decoy run` with
`statistical_stats_degenerate`. Open the snapshot and check that each category
column has entries under `top_values` before you build on it.

### Fit time

The DP fit spends most of its time working out how to split the budget, before
it reads your data. That cost depends on the number of columns and is paid on
every run:

| Columns declared | Time on 500 rows |
|---|---|
| 2 | 13 s |
| 8 | 37 s |
| 20 | 88 s |

On engine 0.19.0, add `source_column: <name>` to every column in the example
above. Without it the
[column independence defect](03-fit-and-generate.md#fixed-columns-move-together-when-they-should-not)
applies: in an earlier run of this example every generated NY row had tier
gold. It is fixed after engine 0.19.0 (engine #421). The privacy guarantee
holds either way, because the output is built only from the noisy snapshot.
Columns from a DP snapshot are generated independently, so real relationships
between columns are not reproduced.

Practical guidance:

- A few hundred rows is too small for a useful DP release at epsilon 1.
- Release fewer columns to give each one more of the budget.
- Keep the declared number range tight. A range far wider than the data wastes
  buckets.
- Rare categories will disappear. That is the protection working.

## What to tell an auditor

For a DP fit with declared epsilon and delta, the released single-column
numeric and categorical summaries, and columns generated only from them, are
covered by that (epsilon, delta) guarantee, where neighbouring datasets differ
by one added or removed row. Noise and per-column accounting come from OpenDP
0.15.1; the total is composed by Google's `dp_accounting` 0.6.0.

The guarantee applies to the table as you loaded it. If file parsing could
change column types depending on one record (for example a single non-numeric
entry turning a number column into text), fix the column types yourself before
fitting. The full statement and its limits are in
`docs/what-we-cannot-prove.md` in the `decoy-engine` repo.

The snapshot records how it was made: schema `dps-marginal/v3`, the epsilon
actually spent, the declared ranges, library versions and the environment
fingerprint.
