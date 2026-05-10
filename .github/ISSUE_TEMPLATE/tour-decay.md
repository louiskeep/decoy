---
name: Tour decay walk-through
about: Quarterly check that the CLI onboarding tour still describes reality. Per Item 50 Phase F.
title: 'Tour decay: 1-onboarding.tour'
labels: ['docs', 'maintenance']
---

## Tour to walk

- `.tours/1-onboarding.tour` — 9-stop walkthrough of the CLI's structure (Typer app → command registration → `decoy run` → engine dispatch boundary → keyed-determinism resolver → semantic-token UI primitives → `forge` deprecation shim).

## Procedure

1. Open the repo in VS Code with the [CodeTour extension](https://marketplace.visualstudio.com/items?itemName=vsls-contrib.codetour) installed (publisher: `vsls-contrib`).
2. Play through the tour stop by stop.
3. For each stop, check whether:
   - The pinned line still contains what the description claims.
   - The cross-references (other files, ADRs, guides, sibling tours) still resolve.
   - The narrative matches the current implementation — not just literally true at the line, but conceptually accurate about what the file does.
4. Note every drift below.

## Drifts found

<!-- One bullet per drift. Cite the stop number, the file, and what's stale. -->

-

## Resolution

- [ ] Open a PR fixing the tour, OR delete the tour entirely if the drift is wider than rationally fixable in this issue.
- [ ] PR: #
- [ ] Walk the (fixed) tour cleanly end-to-end after merge to confirm.

## Cadence

- This walk: <!-- YYYY-MM-DD -->
- Previous walk: <!-- YYYY-MM-DD; check the prior closed tour-decay issue -->
- Next walk due: <!-- 3 months from this walk's completion date -->

> *A wrong tour is worse than no tour.* If you can't confidently fix the drift, delete the tour and reopen this issue with the deletion as the resolution.
