# 6. Troubleshooting

[Back to the guide index](README.md)

## Errors

### `dp_stack_uncertified` (exit 3)

The DP fit ran on a setup that was not tested. Build the certified environment
described on [page 4](04-differential-privacy.md#before-you-start-the-certified-environment).
Common causes: a normal `pip install`, a different Python patch version, or an
extra package added to the certified environment.

### `dp_platform_uncertified`

The machine is not Linux x86-64 with glibc. Run the fit in a Linux x86-64
container or VM.

### `dp_columns_omitted`

```text
error: dp_columns_omitted: source column(s) not declared for the DP release: customer_id, email, ...
```

Declare each column with `--dp-number`, `--dp-text` or `--dp-flag`, or pass
`--dp-allow-omit` to release only the declared ones.

### `dp_mode_not_selected`

A `--dp-*` flag was used without `--epsilon`. Add `--epsilon` and `--delta`, or
remove the DP flags for a plain fit.

### `dp_mode_delta_required`

`--epsilon` needs `--delta`. There is no default.

### "budget ceiling is malformed ... delta='1e-6'"

YAML read `1e-6` as text. Write `0.000001` or `1.0e-6`.

### "compose to epsilon_total=... which exceeds the declared ceiling"

The snapshots this pipeline uses cost more privacy budget than
`global_settings.dp` allows. Raise the ceiling, use fewer DP snapshots, or
refit with a smaller epsilon.

### "references a snapshot with no 'dps-marginal/v3' `dp` block"

The pipeline has a `dp:` block but a column points at a plain snapshot. Refit
that snapshot with `--epsilon`, or remove the `dp:` block.

### "the snapshot's top_values contain REAL source values"

A category column is sampling from a plain snapshot. Either accept the
disclosure with `allow_real_categories: true` on that column, or use a DP
snapshot together with a `global_settings.dp` block.

A DP snapshot used without a `dp:` block gives this same error.

### `statistical_snapshot_unreadable`

The `snapshot_file` path does not exist or is not valid JSON. Check the path
and which folder you ran the command from.

### "Extra inputs are not permitted (tables.0.columns.5...)"

A strategy option is at the wrong level. Options such as `width`, `min_days`
and `max_days` go under `provider_config:`.

## Surprising results

### `PASS` next to a low grade

The default mode only records. See
[page 5](05-reading-fidelity-reports.md#the-first-line).

### A masked name or ID column scores near 0

Expected. The values were replaced. Pass `--config pipeline.yaml` so the report
knows the strategy.

### A masked name column scores high

Free text is compared by length only. It does not mean real names survived.

### A date column scores low after generation

Generated dates are full timestamps and the report compares dates as text.
See [page 3](03-fit-and-generate.md#step-3-check-the-result).

### `run --fidelity` and `report fidelity` give different grades

They read the data differently. Keep the `report fidelity` number.
See [page 2](02-check-shape-after-masking.md#why-the-two-grades-differ).

### `run --fidelity` prints nothing useful on a generate pipeline

The inline check covers masked tables only. Use
`decoy report fidelity SOURCE OUTPUT --generate`.

### Generated numbers have too many decimals

Values are drawn uniformly inside histogram buckets. Round them downstream.

### Generated columns are correlated when the source columns are not

A known defect with a one-line workaround: set `source_column` on every
statistical column. See
[page 3](03-fit-and-generate.md#known-defect-columns-move-together-when-they-should-not).

### Two faker columns have identical values

Same cause. Two generate columns with identical settings share a seed. Make
the settings differ, or accept the duplication.

### Blanks in the source do not appear in generated data

Null rates are not reproduced by statistical columns. Add `null_probability`
to the generate column.

### A generated number column looks nothing like the source

Check the source for an extreme value or heavy skew. One outlier stretches the
fit's ten buckets and ruins the column. See
[page 3](03-fit-and-generate.md#check-your-source-before-you-fit).

### A good grade on output that is clearly wrong

The report has blind spots. See
[page 5](05-reading-fidelity-reports.md#what-the-report-misses).

### `condition_on` produced a combination that is not in the source

More than 25 distinct pairs were fitted and the rest were dropped, or the
parent value was not in the fit. See
[page 3](03-fit-and-generate.md#using-condition_on).

### "no joint contingency for (...)" when the pair was fitted

The parent column was renamed. `condition_on` needs the parent's generated
`name` to match its snapshot name.

### `statistical_stats_degenerate` at run after validate passed

A DP snapshot released no values for that column. See
[page 4](04-differential-privacy.md#an-empty-release).

### The DP fit takes a long time

Expected. Time grows with the number of declared columns. See
[page 4](04-differential-privacy.md#fit-time).

### A fidelity warning was configured but nothing was printed

`fidelity_warn_threshold` writes to `logs/decoy_engine.log` only.

### The DP output is missing categories

Values with small counts are dropped on purpose. With little data, most
values count as small. See
[page 4](04-differential-privacy.md#expect-accuracy-to-depend-on-data-size).

### The policy file has no effect

An unrecognized key is ignored silently. Check the key names on
[page 2](02-check-shape-after-masking.md#policy-file).

## Safe handling

| Artifact | Sensitivity |
|---|---|
| Plain snapshot (`*.snapshot.json`) | As sensitive as the source for category columns. It holds real values and exact counts. |
| DP snapshot | Safe to share within the stated (epsilon, delta). Columns you omitted are not in it. |
| Fidelity report JSON | Scores and counts only. No data values. |
| Masked output | Protected by the strategies you chose. No formal guarantee. |
| Mask secret | Keep it out of the pipeline file and out of version control. |

## More help

- `decoy fit --help`, `decoy report fidelity --help`
- `decoy explain differential-privacy`, `decoy explain keys`, `decoy explain exit-codes`
- Known issues from hands-on testing, newest first:
  [`docs/records/2026-11-10-cli-qa-generation-distribution-models.md`](../../records/2026-11-10-cli-qa-generation-distribution-models.md),
  [`docs/records/2026-11-08-cli-qa-distribution-integrity.md`](../../records/2026-11-08-cli-qa-distribution-integrity.md)
  and [`docs/records/2026-11-08-cli-qa-generation.md`](../../records/2026-11-08-cli-qa-generation.md)
