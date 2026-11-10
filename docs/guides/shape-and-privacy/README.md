# Data shape and privacy: user guide

How to keep, copy, measure and protect the statistical shape of your data with
the `decoy` CLI. "Shape" means things like how many customers are in each
state, or how order amounts are spread out.

Every command and output on these pages was run against decoy-cli 0.1.0 and
decoy-engine 0.19.0 on a 500-row sample file.

## Pick the page for your task

| I want to... | Read |
|---|---|
| Understand which tool fits my problem | [1. Choose your approach](01-choose-your-approach.md) |
| Mask a real file and check what shape survived | [2. Check shape after masking](02-check-shape-after-masking.md) |
| Make fake data that looks like my real data | [3. Fit and generate](03-fit-and-generate.md) |
| Make fake data with a formal privacy guarantee | [4. Differential privacy](04-differential-privacy.md) |
| Understand a score, a grade or a verdict | [5. Reading fidelity reports](05-reading-fidelity-reports.md) |
| Fix an error or a surprising result | [6. Troubleshooting](06-troubleshooting.md) |

## The four ideas, in one minute

- **Masking** changes sensitive values in a real file, row by row. You still
  have one output row per real row. It has no formal privacy proof.
- **Fitting** (`decoy fit`) reads a real file and writes a small JSON summary
  of each column, called a snapshot.
- **Statistical generation** builds brand-new rows by sampling from a snapshot.
- **Fidelity** is a score from 0 to 1 that says how close the output's shape
  is to the source's shape. It is a measurement. It is not a privacy property.

Differential privacy (DP) is an optional mode of fitting. It adds calibrated
noise to the summary so that no single person's row can be detected. It is the
only part of Decoy that carries a mathematical privacy guarantee, and it covers
single columns only.

## Sample data used on these pages

`customers.csv`, 500 rows:

```text
customer_id,full_name,email,state,tier,amount,signup_date,is_active
1,Cara Nguyen,cara.nguyen1@example.com,TX,silver,18.06,2022-10-02,False
2,Ana Lee,ana.lee2@example.com,CA,silver,47.97,2023-07-02,False
```

`state` has five values (CA 216, TX 117, NY 99, FL 45, WA 23). `tier` depends
on `state`. `amount` is skewed toward small values.

## Related reference

- Command reference: [`docs/cli-reference.md`](../../cli-reference.md)
  (`decoy fit`, `decoy run`, `decoy report fidelity`).
- In the terminal: `decoy explain differential-privacy`, `decoy explain keys`.
- How it works inside the engine: the distribution-integrity developer docs in
  the `decoy-engine` repo, `docs/distribution-integrity/`.
- What Decoy does not prove: `docs/what-we-cannot-prove.md` in `decoy-engine`.
