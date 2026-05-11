## Summary

<!-- 1-3 sentences on what changed and why. Link to a roadmap item or plan if applicable. -->

## Test plan

<!-- Bulleted checklist of how this was verified. -->

- [ ] `pytest tests/`
- [ ] `pytest tests/e2e/ -v`
- [ ] (UI changes) Hand-tested: walked the affected commands with `--json`, `--quiet`, `--verbose`, and default modes

## Docs checklist

<!-- Skip a box only if the change genuinely doesn't touch that surface; never delete the box. -->

- [ ] **`docs/architecture.md`** updated if I changed the CLI's structural map
- [ ] **ADR added** if I made a non-obvious architectural decision (one that a future contributor might re-litigate). Format and threshold in [`docs/adr/template.md`](../docs/adr/template.md).
- [ ] **Guide updated** if I changed the target state of a feature documented in a `*_GUIDE.md` (e.g. `CLI_UX_GUIDE.md`, `PIPELINE_GRAPH_GUIDE.md`)
- [ ] **CodeTour fixed** if I moved a line that any stop in `.tours/1-onboarding.tour` points at. *A wrong tour is worse than no tour.*
- [ ] **Plan filed under `plans/`** if this PR is more than a one-PR change

## Cross-repo coordination

- [ ] If this PR introduces new product vocabulary, the cross-repo glossary in [`decoy-platform/GLOSSARY.md`](https://github.com/louiskeep/decoy-platform/blob/main/GLOSSARY.md) needs a matching entry. (Open a sibling PR there.)
- [ ] If this PR ships, supersedes, or pivots a numbered roadmap item, the matching status in [`decoy-platform/ROADMAP.md`](https://github.com/louiskeep/decoy-platform/blob/main/ROADMAP.md) is updated.
- [ ] If this PR depends on engine changes, the engine PR is merged before this one merges.
