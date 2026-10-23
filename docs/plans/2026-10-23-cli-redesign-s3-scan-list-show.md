# S3 build plan — `scan` + `list`/`show`

Status: build plan, PRE-RELEASE (2026-10-23). Third sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Breaking, pre-GA hard delete. Awaiting plan-gate review.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, documentation,
reuse-first, scope-discipline, architecture, testing.

Established solutions: n/a — this is command-tree reshaping, not a new domain primitive; the only non-trivial
mechanism (the Click `resolve_command` default-command override) is REUSED from S2's `_DefaultCommandGroup`,
not newly designed.

Risk: R2. Breaking surface change (merge/rename commands), no engine behavior change, feature-branch, no
merge to main, no R3 side effect.

Plan-gate review incorporated (GO-WITH-REVISIONS, 2026-10-23): H1-H8 + M1-M4 + L1-L6 folded in below.
Headlines: H8 — `load_disguises` IS cleanly importable (public in `decoy_engine.disguises.__all__`; the slice
already reads more-private `_KNOWN_SCHEMES`/`_REGISTRY` for checksums/validators), so `list disguises` ships
in S3 and only `list detectors` is deferred (no clean engine enumeration — L4). H4/H5 — `scan` must preserve
profile's PII-honesty framing and privacy-safe field record. H6 — keep `--layout` (fixed-width). H7 — pin
`--rows` default + auto-save. H1/H2/H3 — the dead-string sweep + `fields/show/diff` + `storm integrity`
help/envelopes are all in scope.

## Guarantee

One "look at my data" verb and one reference vocabulary:
- `decoy scan SOURCE` — profile + PII/risk in one command (merges today's `profile` + `storm analyze`),
  `--output scan.json` to persist. Saved-scan ops are subcommands: `scan fields SCAN`, `scan show SCAN
  FIELD`, `scan diff OLD NEW`. The STORM animation is kept.
- `decoy list KIND` — one verb over the engine registries: `KIND ∈ {strategies, providers, checksums,
  validators, templates, disguises}`. `decoy show KIND [NAME]` — detail for one item where a detail view
  exists (`strategy`, `provider`, `template`), plus `show schema` (no NAME). Folds the `strategies`/
  `providers`/`checksums`/`validators` sub-apps + `templates list/show` + `schema`.

Non-goals / deferred: `list detectors` is DEFERRED to S5 — the engine has NO clean public enumeration of
detector IDs (`storm/detectors.py` holds `REGISTERED_DETECTORS` as callables with IDs embedded in
`_evaluate`; the only ID-bearing surface is deep-internal), so it needs an additive engine export, bundled
with the S5 disguise work. `list disguises` DOES ship in S3 (H8): `decoy_engine.disguises.load_disguises` is
a clean public export of that submodule (in its `__all__`, documented), and is strictly more public than the
`_KNOWN_SCHEMES`/`_REGISTRY` internals this same slice already reads for checksums/validators — deferring it
would be inconsistent. (A nice-to-have engine follow-up: re-export `load_disguises` at top-level
`decoy_engine.__all__` for contract tidiness; not S3-blocking.) `storm integrity` is NOT touched here (it is
post-run verification → `report integrity` in S4); it remains reachable as a transient lone `storm integrity`
command until S4. No `--force`/overwrite work (S1 B2 follow-up).

## Reuse

- `run_storm` is the single engine entry both `profile` (`cli/profile.py:153-165`) and `storm analyze`
  (`cli/storm.py:_scan`) already call — `scan` composes it once; no detection logic is written.
- The `_DefaultCommandGroup` built in S2 (`cli/validate.py:69-102`) already solves "a group command that
  also takes a positional" (bare `validate CONFIG`). EXTRACT it to a shared module
  (`cli/_default_group.py`) and reuse it for `scan SOURCE` so the pattern has one home (reuse-first; one
  place per fact). `validate` imports it from there. M1: the class hardcodes `default_cmd_name = "_gate"`;
  parameterize it on extraction (a `make_default_group(name)` factory or two trivial subclasses) so `scan`'s
  hidden default registers under its own name (e.g. `_scan`), not the misleading `_gate`. The class has no
  validate coupling and imports only `typer.core.TyperGroup` (no import cycle) — reuse is correct, not
  duplication.
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
scan SOURCE [--show-fields] [--rows N] [--strategy ...] [--layout FILE] [--output FILE|-] [--format ...]
                                            profile + PII/risk (merges profile + storm analyze)
scan fields SCAN [--pii ...] [--quasi]      list fields from a saved scan            (was storm fields)
scan show SCAN FIELD                        per-field detail from a saved scan       (was storm show)
scan diff OLD NEW [--strict]                compare two saved scans                  (was storm diff)

list KIND            KIND ∈ strategies|providers|checksums|validators|templates|disguises
show KIND [NAME]     KIND ∈ strategy|provider|template (NAME required) ; `show schema` (no NAME, --output ok)
schema [--output]    PipelineConfig JSON Schema (kept top-level; `show schema` is the grouped alias)
```

Pinned behavior defaults (H7 — the two silent conflicts between the merged commands), flagged for owner:
- `--rows` default = **10000** (profile's bounded default; safe on large files), NOT analyze's scan-all.
  A sample is used by default; `--rows 0` scans the whole file. Rationale: a "look at my data" command must
  not silently full-scan a huge file; the bound is explicit and overridable. (Owner may prefer scan-all.)
- Persist only with `--output` (H7b) — `scan` does NOT auto-write `scan_<ts>.json` to cwd the way `storm
  analyze` did (clig: writing an unrequested file is a surprising side effect). The card's next-hint points
  to "run with `--output scan.json`, then `scan fields scan.json`". `--output -` streams the scan JSON to
  stdout (preserve analyze's stdout-pipe capability).
- `--layout FILE` is retained (H6): `--format fixed-width` fail-closes without it; the fixed-width loaders
  (`_load_data`/`_load_fixed_width_with_sampling`/`_parse_layout`) move with `scan`.

## Slices

### S3a — `scan` (merge `profile` + `storm analyze`)
- Extract `_DefaultCommandGroup` from `validate.py` to `cli/_default_group.py` with a parameterized default
  name (M1); `validate` imports it (default name `_gate`), `scan` uses it (default name `_scan`).
- New `cli/scan.py`: a `scan` sub-app (cls=the shared default group). Default action `scan SOURCE` composes
  `run_storm` with the flag union: `--show-fields`/`--rows` (profile) + `--strategy`/`--output`/`--format`/
  `--layout` (analyze) + the STORM animation. Apply the H7 pinned defaults (`--rows 10000`; persist only on
  `--output`; `--output -` to stdout). Move the fixed-width loaders (`_load_data`/
  `_load_fixed_width_with_sampling`/`_parse_layout`) with `scan` (H6).
- **H4 (honesty):** `scan` MUST carry profile's PII-honesty framing — the "suggestion — review required"
  rendering (`profile.py:296-311`) and the `pii_note` (`profile.py:199-210`), in BOTH human and `--json`
  output. Never "classified/detected as". Do not silently adopt analyze's bare "PII columns: N" card.
- **H5 (privacy):** `scan`'s inline/`--show-fields` field rendering MUST use profile's privacy-safe
  `_safe_field_record` (`profile.py:250-271`) — no `top_values`/min/max/mode in the field output. (The
  `--output` artifact inheriting analyze's richer `profile.to_dict()` is pre-existing; call it out, keep it.)
- **H2:** `fields`/`show`/`diff` move from `storm.py` (`_fields`/`_show`/`_diff`) but their bodies ARE
  edited: rewrite every embedded next-step hint / error suggestion / `_emit_load_error` command_name and the
  `_scan` JSON `"command"` field from the `storm …` surface to `scan …` (`storm.py:440,561,585,597,633,653,
  683,723,791,820,852,909,994,999,1122,1124`). Update any test asserting the old `command` strings.
- Delete top-level `profile` (`cli/profile.py` command + registration) and the `storm` sub-app's
  `analyze`/`fields`/`show`/`diff` registrations. **H3:** KEEP `storm integrity`, but scrub the `storm` group
  help (`storm.py:22-28`) to describe only `integrity` (+ "moves to `report integrity` in S4") and drop
  `storm analyze` from `_INTEGRITY_EPILOG` (`storm.py:176`). KEEP the animation module.
- Register `scan` in `__main__.py`; update `_ROOT_HELP` (scan replaces the `profile`/`storm analyze` lines);
  **M4:** regen `docs/cli-reference.md` and add `scan` to the consistency allowlists so S3a is green on its
  own (don't defer doc-regen to S3b).
- **H1 (full dead-string sweep + grep gate):** repoint the removed command strings in ALL offender modules,
  not just profile/storm/__main__: `ui/banner.py:51`, `cli/explain.py:187`, `cli/catalog.py:350,352`,
  `cli/init.py:51`, `cli/compile_explain.py:29,72,266,428`, `cli/demo.py:40,131`, `api.py:4,14,558,560`,
  `ui/storm_animation.py:1,165`, `__init__.py:8`. Extend `tests/unit/test_no_dead_command_strings.py` with
  `decoy profile`, `decoy storm analyze`, `storm fields`, `storm show`, `storm diff` (keep `storm integrity`
  allowed).
- Tests: `scan SOURCE` → exit 0, PII counts shown with the suggestion/review framing (H4), `--output` writes
  JSON, NO file written without `--output` (H7b), `--output -` streams to stdout; `--show-fields --json`
  emits NO top_values/min/max (H5); a fixed-width `scan --format fixed-width --layout L` works and errors
  cleanly without `--layout` (H6); `--rows` default bounds the sample (H7a); `scan fields/show/diff` carry
  the old behavior with `scan …` hints; top-level `profile`/`storm analyze` → "No such command".

### S3b — `list`/`show` unification
- New `cli/reference.py`: a `list KIND` command and a `show KIND [NAME]` command dispatching by KIND to the
  existing readers. `list` kinds: strategies/providers/checksums/validators (reuse cockpit's
  `_strategies_list`/`_providers_list`/`_checksums_list`/`_validators_list`), templates (templates' `_list`),
  and **disguises** (H8: new reader over `decoy_engine.disguises.load_disguises`, listing bundle names +
  rule counts). `show` kinds: strategy/provider (cockpit `_strategies_inspect`/`_providers_inspect`),
  template (templates' `_show`), and schema (the `schema` body).
- **M2 (`show` signature):** `show KIND [NAME]` — NAME is optional with per-kind validation: schema takes NO
  NAME and uniquely accepts `--output/-o`; strategy/provider/template REQUIRE NAME (missing → clean
  EXIT_USAGE). `--output` rides only with `show schema`.
- **M3 (reused bodies ARE edited):** the dispatched cockpit/templates bodies hardcode JSON envelope
  `command` fields ("strategies list", "providers list", etc., `cockpit.py:96,277,…`) and old-surface
  next-step hints in their bodies (`cockpit.py:113-117,194-197,300-304,384-388,461-463,535-537`; templates
  `_list`/`_show`) — rewrite these to the new `list`/`show` surface. The dispatcher MUST pass concrete
  `json_/quiet/verbose` bools (the functions' defaults are `typer.OptionInfo`, not bools, so direct calls
  need explicit values). Add/extend `test_cockpit.py` to assert the envelope `command` strings are the new
  surface (not just registry correspondence).
- Delete the `strategies`/`providers`/`checksums`/`validators` sub-apps and `templates` sub-app
  registrations in `__main__.py`; register `list`/`show`. Keep top-level `schema` as an alias.
- **KIND validation (L3):** an unknown kind → clean `EXIT_USAGE` naming the valid kinds. For
  `show checksum|validator NAME` (list-only kinds with no detail object), return a helpful "no detail view
  for <kind>; detail exists for strategy/provider/template/schema" rather than a bare unknown-kind error.
- **M4:** prune `strategies`/`providers`/`checksums`/`validators`/`templates` from
  `test_surface_docs_consistency.py` allowlists (the `stale = OMITTED - TOP_LEVEL` assertion fires once
  they're removed); add `list`/`show`; update `_ROOT_HELP`/README; regen `docs/cli-reference.md` (S3b green
  on its own).
- Dead-string sweep + grep gate: `decoy strategies`/`providers`/`checksums`/`validators`/`templates
  list|show` repointed to `decoy list …`/`decoy show …`.
- Tests: `list strategies|providers|checksums|validators|templates|disguises` each exit 0 and show the live
  registry contents (reuse cockpit assertions; add a disguises assertion incl. `hipaa`); `show strategy
  <name>`/`show provider <name>`/`show template <name>`/`show schema` show detail; `show schema -o f.json`
  writes the schema; `show strategy` with no NAME → EXIT_USAGE; `show checksum X` → the helpful no-detail
  message; `list bogus` → EXIT_USAGE naming the valid kinds; the old sub-apps → "No such command".

Advisory notes carried into build (L1/L2): `decoy show KIND NAME` (reference detail) and `decoy scan show
SCAN FIELD` (saved-scan field detail) are two distinct `show` paths — acceptable (different noun contexts),
but give each clear help. The singular/plural split (`list strategies` vs `show strategy`) is deliberate
English idiom; the unknown-kind error should cross-suggest the right form.

## Verification

Full `pytest -q` green; `ruff check`; regen `docs/cli-reference.md` + the surface/consistency sentries green;
test-strength on the new `scan` compose + the `list`/`show` dispatch.

## Acceptance

- `scan SOURCE` merges profile+analyze (animation kept); preserves profile's PII-honesty framing (H4) and
  privacy-safe field record (H5); `--layout` fixed-width works (H6); `--rows` bounds by default + persist
  only on `--output` (`--output -` to stdout) (H7); `scan fields/show/diff` carry the old behavior with
  `scan …` hints; `profile`/`storm analyze` gone.
- `list KIND` covers six kinds (strategies/providers/checksums/validators/templates/disguises) reading the
  live registry; `show KIND [NAME]` (schema no-NAME + --output; others NAME-required) works; the four
  registry sub-apps + `templates` sub-app gone; `schema` kept as alias.
- `_DefaultCommandGroup` lives in one shared module (parameterized name) used by both `validate` and `scan`.
- Only `list detectors` deferred to S5 (no clean engine enumeration); `storm integrity` untouched (S4).
- No source string under `src/decoy/` names a removed command (grep gate: `decoy profile`, `storm analyze|
  fields|show|diff`, `decoy strategies|providers|checksums|validators|templates …`); `storm integrity` ok.
- Full suite + ruff green; all three doc sentries green (each slice regens the reference); no engine change.

## Loop handoff

Plan-gate review before DEVELOP (confirm: detectors/disguises deferral; the transient lone `storm
integrity`; the extracted default-group; `show` only for kinds with a detail view). On GO: build S3a then
S3b, each self-check + verify, then one independent review of the S3 diff, then DOCUMENT. No merge to main.

## Build status (2026-10-23)

- **S3a `scan` — DONE** (`f5ffee9`): merged profile+storm-analyze; honesty (H4) + privacy (H5) preserved;
  `--layout` (H6); `--rows` bounded default + persist-only-on-`--output` + `--output -` (H7); shared
  default-group factory (M1); full dead-string sweep (H1). Verified live.
- **S3b `list`/`show` — DONE** (`61c29c5`): six `list` kinds incl. `list disguises` (H8, reads
  `load_disguises`, shows `hipaa`); `show KIND [NAME]` (M2) + no-detail helpful message (L3); reused bodies'
  envelopes repointed (M3); sub-apps deleted.
- **S3 independent review — ACCEPT** (5 low/advisory). **L1 remediated**: `show schema STRAYNAME` now errors
  cleanly (EXIT_USAGE) instead of ignoring the arg (+ test). Recorded advisory follow-ups (not blocking,
  pre-GA): L2 historical "storm analyze" prose in a few docstrings (grep gate forbids only the
  `decoy `-prefixed form, which is clean); L3 `scan diff --strict` uses EXIT_USAGE(1) for drift (ported
  verbatim; a dedicated drift exit code is a later consideration); L4 stale `test_storm_analyze_*` function
  names in `test_storm_sp16.py` (cosmetic); L5 "none detected" wording at zero PII candidates (optional
  "none flagged").

**S3 CLOSED** (merge-ready on the branch; not merged — PO-gated). Suite 1142 pass/5 skip; ruff clean; all
three doc sentries green; no engine behavior change.