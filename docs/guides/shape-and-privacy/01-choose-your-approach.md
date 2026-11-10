# 1. Choose your approach

[Back to the guide index](README.md)

## The options

| Goal | Use | Touches real data? | Privacy basis |
|---|---|---|---|
| A safe copy of a real file, same rows and joins | Masking: `decoy run` with `columns:` strategies | Yes, it transforms it | Keyed transforms. No formal proof. |
| Fake data from rules you write | Generation: `decoy run` with `generate_columns:` of type `faker`, `categorical`, `sequence`, and so on | No | Never reads real data. |
| Fake data shaped like your real data | `decoy fit`, then `type: statistical` columns | Yes, at fit time | None by default. The snapshot holds real values. |
| Fake data shaped like your real data, with a privacy guarantee | `decoy fit --epsilon`, then `type: statistical` columns under `global_settings.dp` | Yes, at fit time | Differential privacy, one column at a time. |
| A score for how much shape survived | `decoy report fidelity`, or `decoy run --fidelity` | Reads source and output | A measurement only. |

## Quick decision guide

1. **Do you need the real rows to survive** (same customers, same joins between
   tables)? Use masking. Go to [page 2](02-check-shape-after-masking.md).
2. **Do you only need realistic-looking rows**, with no link to real people?
   Use generation.
   - If made-up shapes are fine, write the columns by hand (`faker`,
     `categorical` with weights). No fit needed.
   - If the shape must follow your real data, fit first. Go to
     [page 3](03-fit-and-generate.md).
3. **Will the snapshot or the output leave a trusted environment**, and do you
   need a guarantee you can state to an auditor? Use the DP fit. Go to
   [page 4](04-differential-privacy.md).

## Does masking use differential privacy?

No. Masked output carries no differential privacy, no epsilon, and no
mathematical bound on re-identification risk. Masking and DP protect in
different ways:

- Masking works on rows. Each real row becomes one output row with sensitive
  values replaced (hashed, encrypted, faked, shifted).
- DP works on summaries. It adds noise to counts about the whole table. No real
  row reaches the output.

## What each approach keeps

| | Masking | Plain fit + generate | DP fit + generate |
|---|---|---|---|
| Real rows | Yes, transformed | No | No |
| Row count | Same as the source | You choose | You choose |
| Joins between tables | Kept | Not from the fit (see page 3) | No |
| Single-column shape | Depends on the strategy | Yes, approximately | Yes, with noise |
| Links between columns | Kept unless a strategy breaks them | Only pairs you fit with `--joint` | No |
| Dates | Depends on the strategy | Year mix only | Not supported |
| Free text | Depends on the strategy | Length only (lorem ipsum filler) | Not supported |
| Formal privacy guarantee | No | No | Yes, per column |

## Two things people get wrong

- **A plain snapshot is sensitive.** For category columns it stores the real
  values and their exact counts. Treat it like the source file. See
  [page 3](03-fit-and-generate.md#what-is-in-a-snapshot).
- **A high fidelity score is not a privacy score.** A perfect copy of the
  source scores 1.0 on every metric and protects nobody.
