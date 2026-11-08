# Handoff: review the `decoy init` wizard spec before planning

Status: plan. Written 2026-11-08. This is the first step of roadmap row 32b INIT-WIZARD. Do it
before writing the Phase 1 implementation plan.

Rules consulted: 00-universal, development-loop, documentation, code-review

## What to review

- File: [`2026-10-30-init-wizard-spec.md`](../plans/2026-10-30-init-wizard-spec.md), the full rewrite of the
  draft spec (v2, 2026-11-08).
- Roadmap row: **32b INIT-WIZARD** in [`../ROADMAP.md`](../ROADMAP.md).

## Background

Today `decoy init` asks three questions: preset, input path, output path. The owner wants the
wizard to be the main way to build pipelines, reaching every engine feature through menus. The
spec was revised in a UX review with the owner. Section 18 of the spec records what was settled.
Treat those as decisions, not open questions:

1. Goal is multi-select and accepts all four (mask, generate, subset, tokenize).
2. Back, forward and go-to navigation without losing answers.
3. Field review defaults to every field one at a time. An optional "flagged fields only" mode
   picks one strategy for the rest (passthrough first, then redact, hash, then the full tree).
4. Sample values are shown by default; `--no-samples` turns them off.
5. Strategies are shown as a grouped tree, with no long flat lists. Tab-completed typing is the
   fast path.
6. Checks and Quality are separate steps.
7. The answers file is written only when asked.

## What to check

1. **Schema accuracy.** Every key, enum and option in the spec must exist in the engine. Check
   against `decoy-engine/src/decoy_engine/config/` (`_sources.py`, `_fixed_width.py`,
   `_targets.py`, `_tables.py`, `_post_scan.py`, `_validators.py`, `_global_settings.py`,
   `_subset.py`, `_relationships.py`), `decoy_engine.strategy_catalog()` and the provider registry
   (`providers_v2.get_default_registry().known_providers`). In particular:
   - The YAML in section 6 should pass `PipelineConfig.model_validate` (run it).
   - The strategy tree (5.4.3) should contain each `offer_in_wizard=True` strategy and each
     provider exactly once. `tokenize` has `offer_in_wizard=False`; the spec shows it only when
     Tokenize is in the goal. Decide whether that is right.
   - Validator suggestions (5.7) and quarantine triggers (`validation_fail`, `format_error`,
     `mask_error`).
   - `fidelity_warn_threshold` applies to generated statistical columns only, so 5.8 asks for it
     only then. Confirm.
2. **Secrets (5.10).** `decoy run` rejects `--mask-secret` and `mask_secret_ref` together, so the
   wizard writes one or the other. The `global_settings` docstring says pre-GA keyed strategies
   fall back to the seed when no secret is set, but `decoy explain keys` and the init YAML comment
   say a run refuses. Confirm which is current and that the seed vs secret table is accurate.
3. **Navigation (4.3).** Is the "mark later steps `⚠`, don't delete" rule implementable with the
   step interface in section 12 (`depends_on`)? Look for cases it misses, for example renaming a
   table, changing a field's strategy after validators were chosen, or turning a goal off and on.
4. **Flagged-only mode (5.4.1).** Bulk passthrough on unflagged fields is a leak risk if detection
   misses something. Check that the Review screen listing, the free-text advisory and
   `leak_check` suggestions are enough, or propose a guard.
5. **Samples (4.5).** Confirm samples and previews can never reach the draft, answers file,
   pipeline or logs, and that the privacy tests in section 15 cover it.
6. **Phasing (17).** Phase 1 is now large (every source location and format, both review modes,
   the tree, previews, navigation, drafts). Judge whether it should be split.
7. **Engine gaps (16)** and **open decisions (19).** Give a recommendation for each, especially
   the prompt library (`prompt_toolkit` / `questionary` vs numbered menus only) and how previews
   are computed.
8. **House rules.** Module-size limits (CLI `init.py` is about 650 lines; new code goes in
   `cli/wizard/`), "library code does not know its callers", "use established methodology"
   citations, no "STORM" in user-facing text, plain-English writing.

## Known issues to confirm or fix

- The current `decoy init` wizard ignores the typed input and output paths. `_replace_yaml_path`
  in `src/decoy/cli/init.py` looks for a top-level `input:` key with a single-quoted path. Current
  templates use `sources:`/`targets:` with unquoted paths, so nothing matches. This affects
  `--json` and `--quiet` too. Not fixed; Phase 1 replaces this code. Decide whether to hot-fix it
  first.
- `_PATHED_PRESETS` and comments in `init.py` still mention a removed `graph` preset.
- The column-aware path (`decoy init <file>`) labelled a `customer_id` column as an MRN in
  testing, so its REVIEW comment was wrong.

## Expected output

A review of the spec with findings ranked by severity, each citing a spec section and the engine
file that confirms or contradicts it, plus a recommendation on each open decision. Edits to the
spec are fine. Write no code. The next step after the review is a Phase 1 implementation plan in
`docs/plans/`.

## Environment notes

`decoy-engine` needs Python < 3.13. A Python 3.12 venv with both repos installed editable
(`uv venv -p 3.12`, `uv pip install -e ./decoy-engine -e ./decoy`) is enough to run `decoy init`
and `strategy_catalog()`.
