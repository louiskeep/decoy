# S3 build plan — `scan` + `list`/`show`

Status: build plan, PRE-RELEASE (2026-10-23). Third sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Breaking, pre-GA hard delete. Awaiting plan-gate review.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, documentation,
reuse-first, scope-discipline, testing.

Risk: R2. Breaking surface change (merge/rename commands), no engine behavior change, feature-branch, no
merge to main, no R3 side effect.

## Guarantee

One "look at my data" verb and one reference vocabulary:
- `decoy scan SOURCE` — profile + PII/risk in one command (merges today's `profile` + `storm analyze`),
  `--output scan.json` to persist. Saved-scan ops are subcommands: `scan fields SCAN`, `scan show SCAN
  FIELD`, `scan diff OLD NEW`. The STORM animation is kept.
- `decoy list KIND` — one verb over the engine registries: `KIND ∈ {strategies, providers, checksums,
  validators, templates}`. `decoy show KIND NAME` — detail for one item where a detail view exists
  (`strategy`, `provider`, `template`), plus `show schema`. Folds the `strategies`/`providers`/`checksums`/
  `validators` sub-apps + `templates list/show` + `schema`.

Non-goals / deferred: `list detectors` and `list disguises` are DEFERRED to S5 — the engine exposes neither
cleanly (no public detector enumeration; `load_disguises` is not in `decoy_engine.__all__`), so they need an
additive engine export, which is a cross-repo engine slice best done with the S5 disguise work. `storm
integrity` is NOT touched here (it is post-run verification → `report integrity` in S4); it remains reachable
as a transient lone `storm integrity` command until S4. No `--force`/overwrite work (S1 B2 follow-up).

## Reuse

- `run_storm` is the single engine entry both `profile` (`cli/profile.py:153-165`) and `storm analyze`
  (`cli/storm.py:_scan`) already call — `scan` composes it once; no detection logic is written.
- The `_DefaultCommandGroup` built in S2 (`cli/validate.py:69-102`) already solves "a group command that
  also takes a positional" (bare `validate CONFIG`). EXTRACT it to a shared module
  (`cli/_default_group.py`) and reuse it for `scan SOURCE` so the pattern has one home (reuse-first; one
  place per fact). `validate` imports it from there.
- cockpit's list/inspect bodies already read the LIVE engine registries (strategies, providers via
  `get_default_registry`, checksums, validators via `validators._registry`); `list`/`show` re-dispatch to
  those existing bodies by KIND rather than reimplementing them.

## Design notes

House style on touched code. The extracted `_DefaultCommandGroup` is the only shared structure (moved, not
new). `list`/`show` dispatch on a `KIND` argument to the existing per-registry functions — a thin dispatch
table (`KIND -> callable`), not a new abstraction per kind. `scan` is one command composing `run_storm` +
the existing field/show/diff renderers. No flag argument that switches behavior.

## Surface

```
scan SOURCE [--show-fields] [--rows N] [--strategy ...] [--output FILE] [--format ...]   profile + PII/risk
scan fields SCAN [--pii ...] [--quasi]      list fields from a saved scan            (was storm fields)
scan show SCAN FIELD                        per-field detail from a saved scan       (was storm show)
scan diff OLD NEW [--strict]                compare two saved scans                  (was storm diff)

list KIND            KIND ∈ strategies|providers|checksums|validators|templates
show KIND NAME       KIND ∈ strategy|provider|template ; + `show schema`
schema [--output]    PipelineConfig JSON Schema (kept top-level; `show schema` is the grouped alias)
```

## Slices

### S3a — `scan` (merge `profile` + `storm analyze`)
- Extract `_DefaultCommandGroup` from `validate.py` to `cli/_default_group.py`; `validate` imports it.
- New `cli/scan.py`: a `scan` sub-app (cls=the shared default group). Default action `scan SOURCE` composes
  `run_storm` with the union of today's flags: `--show-fields`/`--rows` (from `profile`) + `--strategy`/
  `--output`/`--format` + the STORM animation (from `storm analyze`). Subcommands `fields`/`show`/`diff`
  move from `storm.py` (`_fields`/`_show`/`_diff`) unchanged in behavior.
- Delete top-level `profile` (`cli/profile.py` command + registration) and the `storm` sub-app's
  `analyze`/`fields`/`show`/`diff` registrations. KEEP `storm integrity` (the `storm` group now holds only
  `integrity`, transiently, with a one-line "moves to `report integrity` in S4" note). KEEP the animation
  module.
- Register `scan` in `__main__.py`; update `_ROOT_HELP` (scan replaces the `profile`/`storm analyze` lines).
- Dead-string sweep + grep gate: `decoy profile` and `decoy storm analyze`/`storm fields`/`storm show`/
  `storm diff` appear nowhere under `src/decoy/` (mirror S1/S2 gates; `storm integrity` is still allowed).
- Tests: `scan SOURCE` produces a profile (exit 0, PII counts shown, `--output` writes JSON); `--show-fields`
  renders the inline field table; `scan fields/show/diff` behave as the old storm subcommands (port those
  tests); top-level `profile` and `storm analyze` → "No such command".

### S3b — `list`/`show` unification
- New `cli/reference.py` (or extend an existing module): `list KIND` + `show KIND NAME` commands dispatching
  by KIND to the existing registry readers (reuse cockpit's `_strategies_list`/`_providers_list`/
  `_checksums_list`/`_validators_list` and templates' `_list`; and `_strategies_inspect`/`_providers_inspect`
  and templates' `_show` for `show`). `show schema` reuses the `schema` body.
- Delete the `strategies`/`providers`/`checksums`/`validators` sub-apps and `templates` sub-app
  registrations in `__main__.py`; register `list`/`show`. Keep top-level `schema` as an alias.
- Validate `KIND`: an unknown kind lists the valid kinds (a clean `EXIT_USAGE`, not a traceback).
- Anti-drift: prune the removed sub-app names from the `test_surface_docs_consistency.py` allowlists; add
  `list`/`show` where appropriate; update `_ROOT_HELP`/README; regen `docs/cli-reference.md`.
- Dead-string sweep: `decoy strategies`/`providers`/`checksums`/`validators`/`templates list|show` repointed
  to `decoy list ...`/`decoy show ...`; grep gate.
- Tests: `list strategies|providers|checksums|validators|templates` each exit 0 and show the live registry
  contents (reuse cockpit's existing assertions); `show strategy <name>`/`show provider <name>`/`show
  template <name>`/`show schema` show detail; `list bogus` → EXIT_USAGE naming the valid kinds; the old
  sub-apps → "No such command".

## Verification

Full `pytest -q` green; `ruff check`; regen `docs/cli-reference.md` + the surface/consistency sentries green;
test-strength on the new `scan` compose + the `list`/`show` dispatch.

## Acceptance

- `scan SOURCE` merges profile+analyze (one command, animation kept, `--output` persists); `scan
  fields/show/diff` carry the old storm-subcommand behavior; `profile`/`storm analyze` gone.
- `list KIND` covers the five exposed kinds reading the live registry; `show KIND NAME` + `show schema`
  work; the four registry sub-apps + `templates` sub-app gone; `schema` kept as alias.
- `_DefaultCommandGroup` lives in one shared module used by both `validate` and `scan`.
- detectors/disguises explicitly deferred to S5 (engine export); `storm integrity` untouched (S4).
- Full suite + ruff green; all three doc sentries green; no engine behavior change.

## Loop handoff

Plan-gate review before DEVELOP (confirm: detectors/disguises deferral; the transient lone `storm
integrity`; the extracted default-group; `show` only for kinds with a detail view). On GO: build S3a then
S3b, each self-check + verify, then one independent review of the S3 diff, then DOCUMENT. No merge to main.