# Distribution integrity in masking

> **Status:** 💭 draft — captures the design space across multiple sprints; not yet promoted to numbered roadmap items.
> **Last reviewed:** 2026-05-10
> **Owns:** cross-cutting between `decoy-engine` (new strategies + per-entity keying) and `decoy` (job-level validation pass + tolerance thresholds).
> **Related shipped:** Item 32 (FPE) ✅, Item 33 (`bucketize` + `truncate`) ✅, STORM Diff reports ✅.
> **Related queued:** Item 28 (pipeline validation audit) 📋.

## Why this matters

Masked data only earns analyst trust if its distribution still tells the truth. We can mask perfectly for compliance and ship outputs that quietly invalidate every downstream model and report. Distribution drift is the slowest failure mode to detect — by the time analytics flags a regression in a dashboard, weeks of decisions have shipped on bad data.

This is the step that gets skipped, and it's why downstream teams stop trusting masked outputs. The fix is not a single transform; it's a discipline: pick strategies that preserve the invariants the downstream cares about, then verify every job before promoting its output.

## The orthogonality the team keeps tripping on

Determinism — same input → same output across runs — is what makes Item 32 (FPE) and HMAC-keyed hashing work for **referential integrity**. It is **not** the same as distribution preservation, and treating them as the same is what causes downstream analytics breakage.

| Property | Domain | Buys you |
|---|---|---|
| **Determinism** | Property of the *function* (input → output mapping) | Stable reruns; FK joins survive masking; cross-environment parity |
| **Bijectivity over uniques** | Property of the function over the value set | Cardinality preserved; categorical bar heights preserved when relabelled |
| **Distribution preservation** | Property of the *output dataset's shape* vs the source | Marginal histograms / percentiles / null rates / cross-column dependencies match the source |

A deterministic function can destroy distributions (e.g. `hash` on a numeric column produces hex strings — bar heights survive, percentiles do not). A non-deterministic function can preserve them (bounded additive noise approximately preserves mean/variance without being deterministic). Determinism is necessary for invariant 3 below; it is neither necessary nor sufficient for invariants 1, 2, or 4.

## The four invariants

| # | Invariant | Definition | Test |
|---|---|---|---|
| 1 | **Marginal** | Per-column shape: frequency for categoricals, histogram/percentiles for numerics, null rate, cardinality | KS (numeric) / chi-square (categorical) source vs masked |
| 2 | **Joint** | Correlations / dependencies across columns: `(state, zip)`, `(age, diagnosis)`, `(account_type, balance)` | Mutual information or Cramér's V on column pairs, before vs after |
| 3 | **Referential integrity** | Same entity → same masked value across tables, environments, reruns | Bijection holds; cross-table FK joins survive |
| 4 | **Temporal coherence** | Within one entity, dates stay ordered and proportionally spaced | Per-entity date sequences and intervals preserved |

## What the engine preserves today

Strategies are catalogued in `decoy-engine/CAPABILITIES_GUIDE.md` §1 and `decoy-engine/DISGUISES_GUIDE.md`. Mapped against the four invariants:

| Strategy | 1 Marginal | 2 Joint | 3 Ref. integrity | 4 Temporal | Notes |
|---|---|---|---|---|---|
| `hash` | partial — bar heights on relabelled values; numeric shape destroyed | shared key across linked columns ⇒ joint preserved | ✅ keyed-determ | n/a | output is hex string; numeric ordering lost |
| `fpe` (Item 32) | partial — same as `hash` but bijection over format domain | same as `hash` | ✅ keyed-determ + bijection | n/a | recommended for fields that must stay valid-looking |
| `faker` / `map: faker` | cardinality preserved, bar heights preserved on relabelled values, **value-space shape replaced by Faker's** | only if same key → same fake (in-mem map within run; `map: faker` cross-run via JSON) | ✅ within-run; cross-run if seed pinned | n/a | Faker's distribution ≠ source distribution |
| `shuffle` | ✅ exact column distribution (it's a permutation) | ❌ destroys row-wise correlations | ❌ non-deterministic per row | ❌ | full-column op, streaming blocker |
| `bucketize` (Item 33) | partial — shape at bucket grain; within-bucket detail collapsed | depends — bucket boundaries can leak/break joints | ✅ many-to-one but stable | n/a | HIPAA Safe Harbor age/ZIP3 |
| `truncate` (Item 33) | partial — shape at prefix grain | same as bucketize | ✅ | n/a | |
| `date_shift` | partial — date density preserved within ±N day jitter | n/a | per-value det (MD5 of value) | ❌ — see gap below | `transforms/date_shift.py` |
| `redact` | ❌ collapses to constant | ❌ | ✅ trivially | ❌ | total information loss |
| `formula` | depends on body | depends | depends | depends | `randint`/`choice` is non-deterministic |

**Where invariants are well-served today:** 3 (referential integrity) — FPE + HMAC + global mappings cover this comprehensively.

**Where invariants are partially served today:** 1 for categoricals (any bijection over uniques preserves bar heights). 4 for date *density* but not per-entity *coherence*.

**Where invariants are not served today:** 1 for numerics under `hash`/`fpe`/`faker`. 2 for any independently-keyed multi-column masking. 4 for per-entity sequences.

## Gaps

1. **`date_shift` is per-value, not per-entity.** `transforms/date_shift.py` keys the offset off MD5(value). Two dates belonging to the same `entity_id` get two independent offsets, so intervals within an entity are destroyed. Invariant 4 is unmet by default.
2. **No numeric-shape-preserving strategy.** `bucketize` collapses within-bucket; `hash`/`fpe` destroy numeric domain entirely. There is no "preserve mean/variance/percentiles within tolerance" option.
3. **Multi-column tuples are masked independently.** A pipeline that masks `state` and `zip` with separate rules destroys their joint distribution even if each rule is internally consistent. There is no first-class "compound" strategy.
4. **No post-mask validation pass.** STORM profiles are computed *before* masking via `run_storm`; nothing routinely profiles the output and diffs it against the source within a job. STORM Diff exists as a UI surface but is not a job-level gate.
5. **No tolerance thresholds in job config.** Even if we computed the diff, there's no schema for "fail this job if KS p-value < 0.05 on column X" or "fail if cardinality drifts by more than 1%."
6. **Outlier tail re-id is unmitigated.** A maximally-paid employee remains the maximally-paid employee after deterministic masking. Re-id via outlier ranking is possible without explicit tail bucketing.

## Proposed work

### A. Per-entity-keyed `date_shift` (closes invariant 4)

New transform variant or new param on existing `date_shift`:

```yaml
- column: visit_date
  mask: date_shift
  params:
    entity_column: patient_id
    min_days: -30
    max_days: 30
```

Offset is `keyed_hash(entity_id, master_key) mod (max_days - min_days)`. Same entity → same offset across every date column it owns and across reruns. Intervals preserved. Falls back to per-value behavior when `entity_column` is omitted, so HIPAA Safe Harbor existing rules don't change.

Implementation note: the transform needs the entity column visible at apply time. The masker already has the full row in scope at the strategy boundary in `masker/processor.py`; passing the entity value in is a small contract widening, not a redesign.

### B. Bucket-then-perturb numeric strategy (closes invariant 1 for numerics)

New `noise` or `bucket_perturb` strategy:

```yaml
- column: salary
  mask: bucket_perturb
  params:
    bucket_width: 5000        # or `quantiles: 20` for equal-N bins
    noise: uniform            # uniform | gaussian | laplace
    bound_to_bucket: true     # noise can't push a value out of its bucket
```

Algorithm: bin the source column (config or via a STORM-derived bucketing), then mask each value with bounded additive noise. Mean, variance, and percentiles are preserved within tolerance set by bucket width. Differential-privacy variant available via `noise: laplace` with explicit ε for teams that need a formal bound.

Composes with **outlier tail bucketing** as a built-in: top/bottom percentile values get bucketed before perturbation, which closes the outlier re-id surface without a separate pass.

Determinism caveat: noise must be keyed by `(value, master_key)` to keep reruns stable. Optional `entity_column` keys it by entity instead, useful when the same numeric value should not always perturb to the same output across rows.

### C. Compound lookup strategy (closes invariant 2 for known correlated tuples)

New `compound` strategy that masks a tuple as a unit against a real-world lookup:

```yaml
- columns: [state, zip]
  mask: compound
  params:
    lookup: us_geo            # registered lookup table
    distribution: weighted_by_source   # | uniform
```

The lookup is a precomputed table of valid `(state, zip, [city, county, …])` tuples. Masking draws a tuple deterministically from the lookup keyed by the source tuple + master key. Joint distribution of the tuple is preserved at the granularity of the lookup, and cross-field consistency is guaranteed (no Boston/CA/10001).

This is the same shape as Item 50 (address quality) on the roadmap; A and C should ship together and share the lookup-registration mechanism. Other obvious lookups: `(currency, country)`, `(diagnosis, icd_code)`, `(department, manager_role)`.

### D. Distribution-diff validation pass (closes the verification gap)

A post-mask job step that:

1. Profiles the output via the existing STORM machinery (already routinely run as a `run_storm` graph op — `decoy-engine/src/decoy_engine/storm/`).
2. Diffs against the pre-mask profile column by column. STORM Diff already supports this surface; the new piece is wiring it as a gate, not a UI affordance.
3. Compares against tolerance thresholds declared in job config:

```yaml
distribution_invariants:
  default:
    cardinality_ratio: [0.99, 1.01]
    null_rate_delta: 0.005
    numeric_ks_p: 0.05
    categorical_chi2_p: 0.05
  per_column:
    salary:
      numeric_ks_p: 0.01      # tighter
    diagnosis:
      cramers_v_with: [department]   # joint check
```

4. Fails the job loudly with a structured diff report on threshold breach. Default is fail-loud; a `tolerate: warn` flag downgrades to a logged warning for exploratory pipelines.

This is naturally adjacent to **Item 28 (pipeline validation audit)** and probably wants to land on the same validation framework. The distribution checks are a *kind* of node-level validation; folding them into Item 28's contract avoids two parallel validation systems.

## Sequencing

Ordering is driven by dependencies and by what unblocks customer-visible asks:

1. **D (validation pass) first.** Until the pass exists we can't quantify drift and can't tell whether A/B/C are actually working. It also has the highest leverage — it makes existing strategies' drift visible without requiring any strategy change. Folds into Item 28's framework.
2. **A (per-entity `date_shift`) next.** Smallest diff, closes a real HIPAA-adjacent gap (interval-preserving date shifts are explicitly recommended by HHS de-identification guidance), unblocks D's temporal-coherence checks.
3. **C (compound lookup) third.** Pairs with Item 50 (address quality) — same lookup mechanism, ship together. Closes the joint-distribution case that customers most often hit (geographic tuples).
4. **B (bucket-then-perturb) last.** Largest design surface (noise distribution choice, DP semantics, bucket inference from STORM). Worth waiting until D is in place so we can validate it empirically against tolerance thresholds rather than designing in a vacuum.

## Cross-references

- `decoy-engine/CAPABILITIES_GUIDE.md` §1 — current transform inventory and determinism story.
- `decoy-engine/DISGUISES_GUIDE.md` — strategy availability table and HIPAA Safe Harbor mapping.
- `decoy-engine/src/decoy_engine/transforms/date_shift.py` — current per-value MD5 implementation that A proposes to extend.
- `decoy-engine/src/decoy_engine/transforms/registry.py` — where new strategies (`bucket_perturb`, `compound`) register.
- `forge-platform/ROADMAP.md` Item 28 — pipeline validation audit; D should land on this framework.
- `forge-platform/ROADMAP.md` Item 50 — address quality; pairs with C's lookup mechanism.
- `forge-platform/plans/2026-05-09-masking-competitor-analysis.md` — competitor framing; distribution-preservation is a Decoy weakness against Accutive/IRI today and should become a strength.

## Open questions

1. **Where does the entity-column declaration live?** Per-rule (verbose, explicit) or inferred from a table-level `entity_id` annotation in the pipeline header (less repetition, single point of truth)? Lean toward table-level with per-rule override.
2. **Does the validation pass run inside the engine or in `decoy-platform`?** Engine-side keeps it close to the data and makes it CLI-usable; platform-side hooks into the existing job-status UI more cleanly. Probably engine emits a structured `DiffReport` artifact and platform renders + gates on it.
3. **Tolerance thresholds: per-job, per-pipeline, or organisational defaults?** Probably all three with override precedence: org default ← pipeline ← job-run override.
4. **DP-bounded noise as a Tier-1 feature or a follow-up?** Adds a real ε story to the sales pitch but raises the implementation bar. Likely follow-up after B's MVP ships with `uniform`/`gaussian`.
5. **Compound lookup registration surface.** YAML in `decoy-engine/src/decoy_engine/lookups/`? Or platform-managed via an admin UI so customers can upload their own (e.g. internal department↔manager tables)? Both eventually; engine YAML first.
