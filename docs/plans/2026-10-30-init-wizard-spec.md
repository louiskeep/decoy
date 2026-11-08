# `decoy init` wizard: design spec

Status: plan

Version: v3, 2026-11-08. Created 2026-10-30 (v1); revised 2026-11-08 after a UX review with the owner
(v2, section 18 records what was settled); revised again 2026-11-08 to apply the spec review (v3).
Promotion into real scope is a planner decision. Items marked **OPEN** are undecided; section 22 lists
the ones that need the owner.

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`,
`development-loop.md`, `documentation.md`, `feature-dev.md`, `api-and-compatibility.md`.

Next step: Dennis round 2 on v3 (round 1 fixes applied below), then the Phase 1a plan, written as a
revision of the 2026-11-07 plan (section 0). Roadmap row 32b INIT-WIZARD tracks it.

Related: `docs/cli-reference.md` (`decoy init` today), `docs/ci-contracts.md` (the CI manifest the
wizard can scaffold), engine config models in `decoy_engine/config/`, and the engine's
`strategy_catalog()` (#400), which lists every strategy and its options for the wizard.

## Changes in v3 (2026-11-08)

v3 applies the spec review `10_Projects/decoy/handoffs/phase1/init-wizard/init-wizard-spec-review-2026-11-08.md`
in the vault (reviewer claudeworkerbee, agent-task T0128; bases engine `b5b1ad16`, CLI `ec209ec6`).
The owner's standing rule for V1 is "take the recommended option", so every recommendation is applied
as written. Summary by review item:

- **H1** quarantine holds unmasked rows: the prompt says so, the default path moves to
  `quarantine/<pipeline-stem>.jsonl`, outside the output folder, `.gitignore` is offered, and Review lists the file
  under "contains unmasked data" (5.7, 5.11, 6).
- **H2** `column_in_set` writes source values: kept only behind a per-field confirm that shows the
  values; the one exception is recorded in 4.5 and in the privacy test allow-list (5.7, 15).
- **H3** the draft is a named allow-list projection; the privacy test covers canaries in every
  surface (10, 15).
- **H4** secret prompting comes from `secret_requirements_for_config`; no hand-kept table; Secrets is
  re-marked when a keyed strategy is added later; there is no seed fallback (5.10).
- **H5** confirming a relationship enforces a `join_safe` key strategy and one shared namespace (5.5).
- **H6** section 0 states what this spec supersedes and adopts the 2026-11-07 plan's settled shapes
  and owner answers.
- **H7** and phasing: Phase 1 splits into 1a and 1b; Phase 1a needs an engine repin (17).
- **M1-M11, L1-L8**: folded into the sections they name (map in section 0.3).
- **Engine gaps** (16) and **open decisions** (19) take the review's recommendations. Section mode is
  now a separate verb, `decoy edit <section> <pipeline>` (19.1).
- The hot-fix of today's `decoy init` is done: CLI #114 merged it on 2026-11-08 (section 21).

### Round 1 fixes (2026-11-08)

Dennis round 1 on v3 (NO-GO, 2 HIGH, 6 MEDIUM, 8 LOW), applied in place:

- **HIGH-1** Phase 1a lists its prerequisites: SCAN-MULTI S3-engine (`starter_config`) with the
  2026-11-07 plan's E1 `column_entry`, SCAN-MULTI S3a.1 (`cli/_scaffold_yaml.render`, G-ONE-EMITTER),
  and the engine release that carries them (17). `config.key_column_not_join_safe` is a Phase 2 engine
  prerequisite (16.13), not an existing backstop (0.2, 5.4.2, 5.5, 12).
- **HIGH-2** new engine gap 16.12, `keyed_columns_for_config(config)`, shipped in the 1a release; 5.10
  names fields from it and covers the composite parent key case.
- **MEDIUM-1** the draft joins the `column_in_set` allow-list (4.5, 15).
- **MEDIUM-2** quarantine defaults to `quarantine/<pipeline-stem>.jsonl`; relative paths resolve
  against the directory `decoy run` starts in (4.3, 5.7, 6).
- **MEDIUM-3** new engine gap 16.14, a public per-column free-text advisory check, landed before 1b
  (5.4.1).
- **MEDIUM-4** 1a deletes `_NAMESPACE_REQUIRED_STRATEGIES`; the draft projection reuses `cli/scan.py`
  `_safe_field_record`, promoted to `src/decoy/_safe_profile.py` (5.4.2, 10, 12).
- **MEDIUM-5** the "provider (combined)" leaf is gone; the tree shows the 30 visible providers (5.4.3).
- **MEDIUM-6** `decoy edit` is registered from `cli/wizard/`; a Placement table and one `.gitignore`
  helper (12).
- **LOW 1-8**: engine 0.20.0 with pin and lock moves (17); `example` labelled "example, not the
  default" (5.4.2, 6); `tokenize` moved out of the "joins keep working" heading (5.4.3); pinned Secrets
  test outcomes and a hand-kept-list mutation (15); 1a local CSV includes TSV and other delimiters
  (17); `decoy-init-draft/v1` with a strict loader (10); 16.8 preferred in the same engine release
  (16); user-typed values allowed, data-derived values restricted (4.5).
- **Owner answers on section 22** (2026-11-08): field review keys, no-terminal refusal and the
  flagged-only default are decided (18). The findings review command home stays open (22).

## 0. Relation to the 2026-11-07 plan

### 0.1 What this spec supersedes

- This spec supersedes spec v2 (the same file at CLI #111) in full.
- It does not replace the reviewed plan `docs/plans/2026-11-07-init-wizard.md` on CLI branch
  `plan/init-wizard` (two Dennis rounds, a Codex confirm, owner answers Q1-Q3 on 2026-11-07). That plan
  is the implementation basis. The Phase 1a plan is a revision of it, not a new plan.
- Where v2 re-invented a shape the 2026-11-07 plan had already settled, v3 takes the plan's shape. Where
  this spec adds steps the plan did not cover (Goal, Sources dialects, the strategy tree, Checks,
  Quality, Output, Secrets, navigation, drafts), the plan revision adds them.

### 0.2 Shapes and owner answers adopted from the 2026-11-07 plan

| Shape or decision | Source in the 2026-11-07 plan | Used here in |
|---|---|---|
| `Prompter` protocol: steps depend on it, not on click; terminal and answers-file implementations; scripted test prompter | 3, W1.1 `_prompts.py` | 4.2, 4.4, 12 |
| Shared YAML mark index `src/decoy/_yaml_marks.py`, moved out of `ci/locations.py` | 4.7, W1.1 | 8, 12 |
| Comment-preserving editor `src/decoy/cli/wizard/_yaml_edit.py` (`apply_edits(text, edits)`), with its span rule, refusals and checks before replace | 4.7, W3.1 | 8, 12 |
| `join_safe` key rule: relationship key columns need a `join_safe` strategy. The catalog fact `join_safe` exists (E0, #400); the engine refusal `config.key_column_not_join_safe` (E1) does not exist yet and is a Phase 2 prerequisite (16.13) | 4.6, E0, E1 | 5.5 |
| Strategy catalog `strategy_catalog()` (part E0, merged as engine #400) | 4.6, E0 | 4.4, 5.4 |
| Post-scan findings review is `decoy init --review-findings PIPELINE --report FILE` for now (owner Q1, 2026-11-07; the final command home is open, 22) | 4.1, 9 Q1 | 3, 22 |
| A rejected finding persists as `post_scan.dismissed` (owner Q2, 2026-11-07); the field belongs to SCAN-ML | 9 Q2, 12 | 3, 5.7 |
| `unlisted: confirm` is allowed in an answers file (owner Q3, 2026-11-07) | 9 Q3 | 11 |
| Answers file format `decoy-init-answers/v1`, strict loader | 4.4, 12 | 11 |
| `--no-input` and `--fail-on-warning` flags; `--json` and `-q` imply `--no-input` | 4.1 | 3, 11, 14 |
| One emitter for new files: `cli/_scaffold_yaml.render` with G-ONE-EMITTER. Its single owner is SCAN-MULTI S3a.1; it is not on CLI main yet, so it is a Phase 1a prerequisite (17). One gate path (`decoy.cli.gate`, G-ONE-GATE) and atomic writes through `src/decoy/_atomic.py` are on main | 10, 13 | 9, 10, 12 |
| Column entries come from the engine helper `column_entry` (2026-11-07 plan E1), built on SCAN-MULTI S3-engine.2 `starter_config`, their single owners. Neither is released yet, so both are Phase 1a prerequisites (17) | 4.6, 13 | 5.4.2 |

### 0.3 Where each review item is handled

| Review item | Section |
|---|---|
| H1 | 5.7 item 3, 5.11, 6 |
| H2 | 4.5, 5.7 item 2, 6, 15 |
| H3 | 4.5, 10, 15 |
| H4 | 5.10, 4.3, 6 |
| H5 | 5.5, 4.3 |
| H6 | 0 |
| H7 | 5.1, 17 |
| M1 | 4.3, 12, 15 |
| M2 | 5.4.1, 5.11, 18 |
| M3 | 5.2 item 4, 6.2 |
| M4 | 5.2 items 2-3 |
| M5 | 5.2 item 1, 5.9, 6.3, 16 |
| M6 | 5.2 item 3, 16, 22 |
| M7 | 5.4.2, 5.4.4, 6, 16 |
| M8 | 2 goal 7, 5.7, 16 |
| M9 | 5.3, 6, 16 |
| M10 | 2 goal 2, 7 |
| M11 | 5.1, 5.4.3, 5.10, 15, 22 |
| L1 | 5.8, 6 |
| L2 | 5.7 item 2 |
| L3 | 5.4.3 |
| L4 | 13 |
| L5 | 12 |
| L6 | 4.4, 17 |
| L7 | 20 |
| L8 | 14 |
| Engine gaps (16) | 16 |
| Phasing (17) | 17 |
| Open decisions 19.1-19.7 | 19 (and 3, 4.4, 8, 10, 5.2, 5.6) |
| Hot-fix | 21 |
| Dennis round 1 (HIGH-1 to LOW-8) | Round 1 fixes list above |

## 1. Summary

`decoy init` becomes the main way to build a pipeline. It walks the user through a pipeline with
menus, from what the pipeline should do to where the output goes. It covers source locations and
formats, headerless and fixed-width input, per-field strategy review, post-scan checks, quarantine and
distribution checks. Settings it does not reach are listed as "edit the YAML" (section 7).

The user can move back and forth freely, and nothing is written until the final review screen. A
separate verb, `decoy edit`, re-enters one step later to change one part of an existing pipeline, and
only that part of the YAML file is rewritten.

Two commands, one set of steps:

- **Project mode** (`decoy init`): walk every applicable step and write a whole pipeline.
- **Section mode** (`decoy edit <section> <pipeline>`): run one step against an existing pipeline and
  rewrite only that block.

## 2. Goals and non-goals

Goals:

1. A new user gets from "I have a file" to a validated, runnable pipeline without reading the schema.
2. The common pipeline features can be set from the wizard, directly or from an "advanced" branch of a
   step. The settings it does not reach are named in section 7 as "edit the YAML", and the end-of-run
   checklist names them when the file uses them.
3. The user can go back to any earlier step, change an answer, and come forward again without losing
   later answers.
4. Every step shows what it understood (parsed preview, before → after preview, summary) before moving on.
5. Any step can be skipped. Skipped work is listed at the end with the command that finishes it.
6. One part of an existing pipeline can be changed without touching the rest of the file, including
   the user's comments.
7. The wizard never writes a config that `PipelineConfig.model_validate` or the config-only checks
   reject. Validator names and params are checked by the engine only at run time today (M8), so until
   engine gap 16.8 closes, the wizard offers only validators it can name from the engine and the
   final validation runs the full gate (config, compile, preflight).
8. Every prompt has a non-interactive equivalent, so the same result can be scripted.

Non-goals (V1):

- A full-screen terminal editor. The wizard is a sequence of prompts.
- Replacing hand-editing. The YAML stays the source of truth, and users are expected to edit it.
- Network access beyond the user's own S3/GCS sources, accounts or telemetry.

## 3. Command surface

```text
decoy init [INPUT_FILE]                       project mode (existing positional arg kept)
decoy init --resume                           continue an interrupted project-mode run
decoy init --answers FILE                     build without prompts from a saved answers file
decoy init --review-findings PIPELINE --report FILE
                                              post-scan findings review (owner Q1, 2026-11-07)
decoy edit <section> <pipeline>               section mode
decoy edit --list-sections                    print section names
```

Section mode is a separate verb (19.1). `decoy init [INPUT_FILE]` and `decoy init <section> <pipeline>`
would share one positional, so a data file named `sources` or `checks` would be ambiguous.

Existing flags of `init` stay: `-o/--output`, `--preset`, `-y/--yes`, `--json`, `-q`, `-v`.
New flags:

| Flag | Command | Meaning |
|---|---|---|
| `--answers FILE` | init | Read answers from a `decoy-init-answers/v1` file instead of prompting (section 11). |
| `--save-answers FILE` | init | Also write the answers file at the end. Off unless asked (section 11). |
| `--no-input` | init, edit | Never prompt. `--json` and `-q` imply it. |
| `--fail-on-warning` | init, edit | Exit 2 when the final validation has warnings, as in `decoy validate`. |
| `--no-samples` | init, edit | Show value shapes (`a***@mail.com`) instead of real sample values. Samples are on by default. |
| `--skip SECTION[,..]` | init | Skip these sections in project mode. |
| `--only SECTION[,..]` | init | Run only these sections in project mode. |
| `--no-validate` | init, edit | Skip the final validation (escape hatch; not recommended). |
| `--diff` | edit | Print the diff and exit without writing. |
| `--review-findings PIPELINE`, `--report FILE` | init | Post-scan findings review, as the 2026-11-07 plan defines it. |

Section names (fixed, tab-completed once completion lands): `goal`, `sources`, `scan`, `fields`,
`relationships`, `subset`, `checks`, `quality`, `output`, `secrets`, `ci`.

The findings review keeps `decoy init --review-findings` for now. It takes the finished run as
`--report FILE`, the run's `post-scan-integrity/v2` report; its final command home is open (section 22).

## 4. Interaction model

### 4.1 Screen layout

Every step opens with a header and a progress bar listing all steps that apply to this pipeline:

```text
── 4/9 Fields · customers ────────────────────────────────────────────
 ✓ Goal  ✓ Sources  ✓ Scan  ▸ Fields  · Checks  · Quality  · Output  · Secrets  · Review
```

`✓` done, `▸` current, `·` not yet visited, `⚠` needs review (an earlier change affected it), `–`
skipped. Steps that do not apply (for example Relationships with one table) are left out of the bar
instead of shown as skipped.

### 4.2 Keys

The same keys work at every prompt. The key line is printed once at the start, and `?` reprints it.
The keys are read through the `Prompter` protocol (section 0.2), so the answers-file and scripted
implementations accept the same actions.

| Key | Action |
|---|---|
| `Enter` | Take the default shown in `[brackets]`. |
| `b` | Back: the previous question, or the previous step at the first question of a step. |
| `f` | Forward: the next step, keeping its current answers. Only offered for steps already answered. |
| `g` | Go to: a menu of all steps with their status. Jump to any of them. |
| `s` | Skip the rest of this step. It is listed in the end-of-run checklist. |
| `?` | Explain this question and its choices. |
| `q` | Save a draft and quit. Resume with `decoy init --resume`. |

Inside field review, `b` moves to the previous field, `g` jumps to a field by number or name, and `l`
lists every field with its current choice.

The 2026-11-07 plan used the `git add --patch` keys (`y n e s a d q`) for its review loop. The owner
decided on 2026-11-08 that the field review uses the v2 keys (Enter, `r`, `o`, `k`, `d`, `b`, `q`); the
plan revision adopts them.

### 4.3 Moving back and forth

- Every answer is kept in the wizard state, so going back never loses anything. When the user returns
  to a step, its previous answers are the defaults.
- Each answer records its origin: `suggested` (from the scan, a preset or another answer) or `user`
  (typed or chosen). When an earlier answer changes, suggested values are refreshed silently. User
  values are never changed or deleted silently.
- Tables and fields get stable internal ids. Their names are attributes, so a rename is one edit and
  every reference (`validators[].columns`, `targets`, relationships, subset seeds) follows the id.
- Each step has `stale(state) -> list[Change]`. It returns each answer that no longer fits and why.
  When the list is not empty the step is marked `⚠`, and the user sees the list when they reach it and
  chooses for each item: keep, change, or remove. A dependency set (`depends_on`) is kept only as an
  optimisation that says which steps to re-check.
- Cases `stale` must cover (each has a navigation test, section 15):
  - removing a source: Fields, Relationships, Output;
  - renaming a table: every reference above, through the stable id;
  - a strategy change after validators: `leak_check` on a field that became `passthrough`, or `luhn`
    after a strategy that does not keep the format;
  - a goal turned off and on: restored Subset seeds that name a table removed in the meantime;
  - a re-scan or a new sample size: the flagged set changes under flagged-only mode;
  - a changed delimiter, header choice or header file: the column count changes, so Scan and Fields
    re-run; under CONFIG-EXPLICIT every source column must be declared again;
  - a changed source format: the Output format default and the reused fixed-width layout;
  - a keyed strategy added after Secrets: Secrets is marked (5.10);
  - a relationship confirmed after Fields: the key fields' strategy and namespace change, so Fields is
    marked (5.5).
- The Review screen refuses to write while any step is marked `⚠`, and offers to jump to it.

### 4.4 Choosing from lists

- Short choices are numbered menus with the default first. Multi-select menus accept `1,3`, ranges
  `1-4`, and `a` for all.
- Long choices (strategies, faker providers, validators) are a tree of small menus (section 5.4.3).
- **Type-ahead.** At any menu the user can type a name instead of a number: `geo_generalize`, or a tree
  path such as `generalize/locations/geo_generalize`. Phase 1 matches typed names and unique prefixes
  without Tab completion. Tab completion of names and file paths arrives with `prompt_toolkit` in its
  own later slice (19.3).
- Menus are generated from the engine (`strategy_catalog()`, the provider registry, config enums), so
  they never offer something the engine rejects. The CLI's hand list `TRANSFORM_IDS` in
  `cli/completers.py` is replaced by `strategy_catalog()` when the engine pin moves (Phase 1a).

### 4.5 Samples and previews

- Sample values are on by default. The data is local and the user already has access to it, and seeing
  real values is the quickest way to judge a suggestion. `--no-samples` shows shapes instead
  (`jane.doe@mail.com` → `a***.a**@mail.com`, `415-555-0142` → `999-999-9999`).
- After sources: a parsed preview of the first rows, so a wrong delimiter or layout is caught before
  scanning.
- In field review: a before → after preview of two or three values with the chosen strategy applied,
  once engine gap 16.1 exists (Phase 1b).
- Sample values, previews and scan profile values (`top_values`, `min_value`, `max_value`) never go into
  the draft, the answers file, the pipeline, `-v` logs, `--json` output or re-shown engine error text.
- The rule restricts data-derived values only: values read from the source, the scan or a preview.
  Values the user types (a path, a namespace, an option, a subset filter value) are allowed in the
  pipeline, the draft and the answers file.
- **One exception.** A `column_in_set` validator lists allowed values, which are source values. The
  wizard writes them only after a per-field confirm that shows them ("Write these 3 values into the
  pipeline: basic, plus, pro? [y/N]"). The values then appear in the pipeline, the draft (mode 0600) and the
  answers file if saved, and nowhere else. The privacy test allow-lists exactly this: values under
  `validators[name=column_in_set].params.allowed_values` for fields the user confirmed (section 15).

### 4.6 Writing

Nothing is written to the pipeline path until the user confirms on the Review screen. `q` and Ctrl-C
save a draft (section 10) and exit with code 1.

## 5. Steps

| # | Step | Writes | Applies when |
|---|---|---|---|
| 0 | Start | nothing | always |
| 1 | Goal | nothing directly (turns steps on and off) | always |
| 2 | Sources | `sources:` | mask, subset or tokenize chosen |
| 3 | Scan | nothing (feeds Fields, Relationships, Checks) | sources exist |
| 4 | Fields | `tables:` | always |
| 5 | Relationships | `relationships:` | two or more tables |
| 6 | Subset | `subset:` | subset chosen |
| 7 | Checks | `post_scan:`, `validators:`, `quarantine:` | always |
| 8 | Quality | quality settings in `global_settings:` | always |
| 9 | Output | `targets:` | always |
| 10 | Secrets | `seed` and `mask_secret_ref` in `global_settings:` | always |
| – | Review | files | always |
| – | CI (offered at Review) | `.decoy-ci.yaml` | user accepts |

### 5.0 Start

```text
  1  New pipeline                                   (default)
  2  Edit a section of an existing pipeline         (runs decoy edit)
  3  Start from a preset (minimal, hipaa, pci, gdpr, generate)
  4  Replay an answers file
```

A preset pre-fills the steps; the user still walks them and can change anything.

### 5.1 Goal

Multi-select. Any combination is allowed, including all four (`a`), once every goal has its steps. A
goal is offered only in the phase that ships its steps (section 17): Phase 1a offers Mask only, Generate
and Subset arrive in Phase 2, Tokenize in Phase 3. A user can never pick a goal and reach no step for it.

| Choice | Effect |
|---|---|
| Mask | Tables read from sources are mask-kind (`columns:`). Turns on Sources and Scan. |
| Generate | Tables built from scratch are generate-kind (`generate_columns:`). No source needed. |
| Subset | Turns on the Subset step. Subset reads Parquet sources only (see 5.6). |
| Tokenize | Shows `tokenize` in the strategy tree (5.4.3) and adds `--vault PATH` to the printed run command (5.10). |

What a combination means, grounded in the engine schema:

- There is no top-level `mode:`. A table is mask-kind when it has `columns` and generate-kind when it
  has `generate_columns`, and one pipeline can hold both. The engine generates first, so generated
  tables can be parents of masked tables.
- With Mask and Generate both chosen, the Fields step offers "add a generated table" after the source
  tables are reviewed.
- Subset runs before masking. There is no setting for the reverse, so the wizard does not ask.
- With all four chosen, the step list is: Sources, Scan, Fields (source tables, then generated tables),
  Relationships, Subset, Checks, Quality, Output, Secrets.

Goal can be changed later with `g`. Steps it turns off are removed from the bar; their answers are kept
in the state in case the user turns the goal back on, and `stale` re-checks them then (4.3).

### 5.2 Sources

One source at a time, then "Add another source? [y/N]".

1. **Location:** local file, Amazon S3, Google Cloud Storage.
   - Local: path. Missing files are reported, with an option to keep the path anyway (the file may not
     exist on this machine yet).
   - S3: bucket, key, region (optional), endpoint URL (advanced).
   - GCS: bucket, object.
   - No credentials prompt. `credentials_ref` is opaque to the engine and only the platform resolves
     it; a CLI run uses the cloud SDK's default credential chain. The step says which chain is used
     (AWS: environment variables or the configured profile; GCP: application default credentials).
     "Test access by reading the first rows? [Y/n]" uses that same chain.
2. **Format:** the menu offers only formats the engine reads from that location.
   - Local: CSV (comma), TSV (tab), delimited with another character, Parquet, fixed-width.
   - S3 and GCS: CSV, Parquet. Cloud sources have no dialect fields, so cloud CSV means comma-delimited
     with a header row, and the step says so.
   - The suggested option is the one the file looks like: the extension, or the delimiter
     `csv.Sniffer` finds in the sampled lines (16.4).
3. **Column names** (local CSV, TSV and delimited only):
   - First row of the file (`has_header: true`).
   - A header file: one name per line, or one delimited line. The count must match the number of fields
     per record. Until CONFIG-EXPLICIT E1 ships `column_names_file`, the names are copied into
     `column_names`; once E1 is released and pinned, the wizard writes `column_names_file` so the
     header file stays the source of truth (16.2).
   - Type them in: one name per prompt, or one line separated by commas.
   - `has_header` is always written, `true` included. CONFIG-EXPLICIT (R2) makes it required on file
     CSV sources, so writing it from the start keeps the wizard ahead of that change. Every source
     column must also be declared under CONFIG-EXPLICIT rule 3; whether a `drop_column` transform
     counts as declared is checked against E2's definition in the Phase 1a plan (section 22).
4. **Fixed-width layout:**
   - A layout file in the engine's `FixedWidthLayout` shape (YAML or JSON), the same shape the platform
     stores.
   - Type it in, with a ruler over the first record. Each column asks for name, start, width and type
     (`str`, `int`, `float`); start defaults to where the previous column ended, so most columns need
     only a name and a width. Pad character and alignment are under "advanced".
   - The record width is derived by the engine as `max(start + width)` and cannot be set. The step shows
     the derived width and asks only whether every record must be exactly that wide
     (`exact_record_width`).
   - No layout is suggested from the data in V1 (19.6).
5. **Parsed preview:** the first three records parsed with the chosen settings, as a table. "Does this
   look right? [Y/n]". `n` returns to format and column names.
6. **Table name:** defaults to the file stem.

Parquet sources skip 3 and 4: the column names come from the file.

### 5.3 Scan

Per source: how many rows to sample (default 10,000). The scan reuses the engine profiler
(`profile_columns`) and the existing inference in `cli/_init_inference.py`. The result is a summary
table: field, type, nulls, unique share, what was detected, confidence. Nothing is written from this
step; the results feed Fields, Relationships and Checks.

- No "pick detectors" prompt. `profile_columns` takes custom detectors and extra name hints but cannot
  select a subset of the built-in detectors (engine gap 16.9). Detector choice arrives with SCAN-ML's
  detector fields (2026-11-07 plan part W2).
- Labels say what the detector knows. A name-hint match is shown as "identifier (name matched the
  record-number list)", not "medical record number". The engine's `mrn` hints include `cust_id`,
  `customer_id`, `client_id`, `emp_id` and `account` by design, as a fail-safe.
- Confidence is shown from the detector's bucket. The current CLI counts any match with
  `match_rate >= 0.5` as confident whatever its bucket; the wizard does not.

### 5.4 Fields

#### 5.4.1 Review mode

Per table:

```text
How do you want to review the 8 fields?
  1  Every field, one at a time                     (default)
  2  Only flagged fields; choose one strategy for the rest
```

A field is **flagged** when any of these hold:

- the scan detected sensitive data in it, or was unsure (medium or low confidence);
- it is an unflagged string field with a high unique share (the threshold is set in the Phase 1b plan);
- the engine's free-text advisory would flag it. Today the advisory runs only at validation. This step
  calls a public per-column check over the scan's `FieldStats` with the same thresholds
  (`freetext_advisory_min_avg_length`, `freetext_advisory_min_distinctness`): engine gap 16.14, which
  lands before Phase 1b.

The extra rules exist because a bulk `passthrough` on a field that detection missed is a leak, and no
later safeguard catches a short identifier no detector matched.

With option 2, the wizard first asks what to do with the fields that were not flagged:

```text
Strategy for the 3 fields that weren't flagged (plan_tier, region, created_at):
  1  passthrough   keep as-is                        (default)
  2  redact
  3  hash
  4  Browse all strategies…
> 1
  Enter accept · type field numbers to review them one at a time instead
```

Then it reviews the flagged fields one at a time. The Review screen shows the count "N fields kept
unchanged without review" and asks for an explicit confirm before writing (5.11).

Flagged-only mode ships in Phase 1b. Every-field mode suggests `redact` for an unflagged field while
the bulk default here is `passthrough`; the owner kept `passthrough` with the guard and the Review
confirm (18, 2026-11-08).

#### 5.4.2 One field

```text
[6/8] zip   str · US ZIP (high)
  Suggested  truncate  keep the first 3 digits
  Preview    94110 → 941    10001 → 100
  Enter accept · r reject · o options · k keep as-is · d drop · b back · ? why
```

- **accept**: use the suggestion with its options.
- **reject**: choose another strategy from the tree (5.4.3) or by typing its name.
- **options**: edit the strategy's options. Options come from `strategy_catalog()`: required ones are
  asked. The catalog has no defaults or descriptions today (engine gap 16.6), so an optional option shows
  the catalog's `example` labelled "example, not the default", and Enter leaves it unset. Once the gap closes, defaults are
  shown in brackets.
- **keep as-is**: `passthrough`.
- **drop**: remove the field from the output (a `drop_column` transform).
- **why**: what the scan found and why this strategy was suggested.

The column entry is built by the engine helper `column_entry` (2026-11-07 plan E1, a Phase 1a
prerequisite, 17). Every strategy whose catalog entry says `namespace_required` gets
`namespace: <field name>`, without asking. Phase 1a deletes the CLI's copy of that fact,
`_NAMESPACE_REQUIRED_STRATEGIES` in `cli/init.py`. Sharing a
namespace across fields (so the same value masks the same way in two fields) is under "advanced" in
options. A confirmed relationship sets one shared namespace on its key fields (5.5).

#### 5.4.3 The strategy tree

Strategies are grouped by what they do to the data. Each level has about eight entries or fewer, and
faker providers are folded into the tree, so the user picks "fake email address" rather than "faker"
and then a provider.

```text
Keep as-is ........................ passthrough
Remove
  ├ Blank out the value ........... redact
  └ Keep only part of it .......... truncate
Replace with realistic fakes
  ├ Names ......................... full name · first name · last name · name ·
  │                                 person (combined) · name + email (combined)
  ├ Contact and birth date ........ email · phone · date of birth
  ├ Addresses ..................... full address · street · city · state · ZIP ·
  │                                 address (combined) · city/state/ZIP (combined)
  ├ Personal and health ids ....... SSN · MRN · NPI · member id · plan id · UUID
  ├ Financial ids ................. account number · EIN · IBAN · card number (PAN) · CUSIP
  ├ Medical codes ................. ICD-10 · NDC
  ├ Other ......................... lorem text
  └ Pick from my own list ......... categorical
Scramble consistently (same input → same output, joins keep working)
  ├ One-way hash .................. hash
  └ Keep the format ............... fpe
Reversible token, kept in a vault . tokenize        shown only when Tokenize is in the goal
Shuffle values within the field ... shuffle
Generalize
  ├ Numbers ....................... bucketize · top_code
  ├ Dates ......................... date_shift · bucket_perturb
  └ Locations ..................... geo_generalize
Free text
  ├ Find and mask sensitive parts . text_mask
  └ Find and redact sensitive parts text_redact
Medical and billing code sets ..... code_set
```

The leaves are defined exactly:

- every strategy with `offer_in_wizard=True` in `strategy_catalog()`, except `faker`;
- plus every provider in the provider registry, which stands for `faker`;
- plus `tokenize` when Tokenize is in the goal. `tokenize` keeps `offer_in_wizard=False` in the engine;
  the CLI shows it through a one-entry named exception that states the reason (reversible, needs a
  vault).

Providers that need `provider_config` the engine gives no metadata for (`random_choice`,
`random_int_range`, `composite_custom`, `composite_provider`) are hidden until engine gap 16.6 closes.
The sync test lists them as the named hidden set, so the tree is still checked against the registry.
With them hidden, the tree shows the other 30 providers. `tokenize` sits outside the "joins keep
working" group because the catalog does not mark it `join_safe`.

Grouping is a CLI presentation concern and lives in the CLI, but the tree sync test (section 15) fails
if a leaf is missing, appears twice, or is unknown to the engine, so the tree cannot fall behind the
engine.

Type-ahead works at every level: typing `email` at the top jumps to the email provider.

#### 5.4.4 Generated tables

When Generate is in the goal (Phase 2), after the source tables: "Add a generated table? [y/N]". Then a
table name, a loop of column name → generator → options, and a row count. Written as
`tables[].generate_columns[]`. The 11 generate column types have no catalog today (engine gap 16.7);
this step waits for it.

### 5.5 Relationships

Shown only with two or more tables (Phase 2). Candidates come from the scan (matching key names and
value overlap). For each candidate, the user confirms, edits or rejects:

1. Parent table and column(s).
2. Child table(s) and column(s). Composite keys are supported (the config takes a list of columns).
3. Orphan policy (required, no default): `preserve`, `remap`, `warn`, `fail`, each with a plain
   sentence of explanation.
4. Namespace: one shared namespace for the parent and child keys, defaulting to the parent key's name.

Confirming a relationship does three things, because Fields runs first and the engine gate does not
refuse a non-injective strategy on a key:

- It checks that every key column uses a `join_safe` strategy (today `hash` and `fpe`). If one does
  not, the user picks a `join_safe` strategy for it here, or rejects the relationship. The engine does
  not refuse this today: `redact` on a key compiles. The refusal `config.key_column_not_join_safe`
  (2026-11-07 plan, E1) is a Phase 2 engine prerequisite (16.13), and Phase 2 does not ship before it.
- It sets the shared namespace on the parent and every child key column, replacing the per-field
  namespaces Fields wrote.
- When it changes a field, it marks Fields `⚠` with what changed (4.3).

The user may add relationships by hand. Cardinality is implied by the parent and children lists, so the
wizard does not ask for it.

### 5.6 Subset

Per the engine schema, a seed rule is one of three modes (Phase 2):

| Mode | Prompts | V1 wizard |
|---|---|---|
| `filter` | table, then one or more `{column, op, value}` predicates (ANDed) | yes |
| `sample` | table, key columns, then `fraction` or `count` | yes |
| `keys` | table, key columns, explicit key list | no: the key list is raw data, so it stays hand-edited (19.7) |

Operators: `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in`, `is_null`, `is_not_null`. Then an optional budget
(`max_total_rows`, `max_table_seed_multiple`) and an offer to show projected row counts with
`decoy subset --dry-run`. Edge directions and `allow_dangling` stay hand-edited.

Subset reads Parquet sources only. If a source is not Parquet, the step says so and offers to go back
to Sources (`g`) or to continue without subset.

### 5.7 Checks

What to check after the run, and what to do with rows that fail. Suggestions come from the field
choices. Checks ships in Phase 1b.

1. **Post-scan integrity** (`post_scan.integrity`): check the output for leftover sensitive data, broken
   keys and policy violations. Report only. Default on. Findings are reviewed later with
   `decoy init --review-findings`, and a rejected finding persists as `post_scan.dismissed` (owner Q2,
   2026-11-07; SCAN-ML owns the field).
2. **Validators:** a checklist of suggested validators, all pre-selected, plus "add another…".
   Suggestions:
   - `leak_check` on fields masked with faker, hash or fpe. Not on `redact`: its output is a constant,
     so the check proves nothing.
   - `column_in_set` on low-cardinality `passthrough` fields, only after a per-field confirm that shows
     the values it would write ("Write these 3 values into the pipeline: basic, plus, pro? [y/N]",
     default no). This is the single exception to the no-source-values rule (4.5).
   - `luhn`, `npi`, `iban`, `vin` on fields that hold those identifiers after a format-keeping strategy.
   - `fk_intact` and `no_orphan_children` when relationships are declared.

   "Add another" lists the validators the engine can name. The registry is private today and params are
   checked only at run time (engine gap 16.8), so until that gap closes the list and its params prompts
   come from one CLI table with a sync test against the engine's registry, and the final validation
   runs the full gate.
3. **Quarantine:** send failing rows to a file instead of stopping the run. The prompt says plainly what
   the file holds:

   ```text
   Send failing rows to a quarantine file instead of stopping the run? [Y/n]
     The quarantine file holds the original, unmasked rows. Keep it out of shared folders and git.
   ```

   Triggers are suggested from the pipeline: `validation_fail` when any validator is on, `format_error`
   when `date_shift` or `bucketize` is used, `mask_error` when `code_set` with `chapter_preserve` is
   used. A pipeline has one `quarantine:` block, so the path defaults to
   `quarantine/<pipeline-stem>.jsonl` (for `pipeline.yaml`, `quarantine/pipeline.jsonl`), outside the
   masked output folder. Relative paths resolve against the directory `decoy run` starts in, not the
   pipeline file's folder, and the step says so. The wizard offers to add `quarantine/` to the
   `.gitignore` in that same directory ("Add quarantine/ to .gitignore? [Y/n]"), through the shared
   helper (12). The Review screen lists the file under "contains unmasked data".

### 5.8 Quality

How closely the output should match the source's distributions.

- **Post-validation** (`global_settings.post_validation`): check the output's invariants after masking.
  Default on.
- **Fidelity and retention thresholds:** asked only when the pipeline has generated statistical
  columns, which is what they apply to: `fidelity_warn_threshold` (default 0.80) and
  `categorical_retention_warn_threshold` (default 0.80, drives the fit-time retention gate for snapshot
  columns). A mask-only pipeline is not asked either.
- **Full fidelity report:** this is the `decoy run --fidelity` option, not a pipeline setting, so a yes
  here adds `--fidelity` to the run command printed at the end.
- Advanced: `unconfigured_column_policy` (`warn` or `error`), the free-text advisory thresholds, and
  differential privacy (`dp`) for generated tables.

### 5.9 Output

One target per table.

1. Location: local file, S3, GCS (same prompts as Sources; no credentials prompt, the default chain is
   named).
2. Format: the menu offers what the engine writes to that location (local: CSV, Parquet, fixed-width;
   S3/GCS: CSV, Parquet). Default follows the source.
3. Fixed-width output reuses the source layout by default.
4. Path: defaults to `out/<table>.masked.<ext>`.

CSV output is always comma-separated with a header row; the engine's targets have no dialect settings.
When the source used another delimiter or no header, the step says so (16.3).

### 5.10 Secrets

This step explains the two values, because they are easy to confuse:

| | Seed | Mask secret |
|---|---|---|
| What it is | A plain number, for example `42` | A private key of 32 or more random bytes |
| What it does | Makes random choices repeatable: the same seed, config and input give the same output | Keys the strategies that must not be reversible or guessable. Which fields need it is decided by the engine (below) |
| Who may see it | Anyone. It is written in the pipeline file | Only the people allowed to run the pipeline. The pipeline holds only a reference to it |
| If it leaks | Nothing is exposed | Someone with the secret and the masked output can test guesses, for example hash every possible SSN and match the results |
| Keep it the same when | You want reproducible runs | You want the same value masked the same way across runs and pipelines (joins across datasets) |

Whether the pipeline needs a mask secret comes from the engine's public
`secret_requirements_for_config` (`decoy_engine.secret_providers`), through the CLI's existing
`_mask_secret_guidance.config_is_keyed`. Which fields are keyed comes from a new public engine function,
`keyed_columns_for_config(config)`, which returns `(table, column, strategy)` entries (engine gap 16.12,
shipped in the Phase 1a engine release). The wizard keeps no keyed list of its own.

- The step names each field `keyed_columns_for_config` returns, with its strategy.
- A pipeline can need the secret with no keyed field, for example a composite parent key in a
  relationship. Then the prompt shows the generic sentence "This pipeline needs a mask secret." and
  lists no fields.
- Until 16.12 ships, the prompt is always the generic sentence. The CLI does not copy the keyed list.
There is no seed fallback: `decoy run` refuses a keyed pipeline without a mask secret in every release
phase, so the wizard never suggests running without one.

Prompts:

1. Seed (default 42).
2. Mask secret, only asked when `secret_requirements_for_config` reports a requirement:
   - Store a reference in the pipeline (`global_settings.mask_secret_ref`): environment variable
     (default `env:DECOY_MASK_SECRET`) or file (`file:/PATH`). Default.
   - Supply it at run time instead (`decoy run --mask-secret …`), which keeps the pipeline file free of
     environment details.
   Setting both is a usage error in `decoy run`, so the wizard writes one or the other, and the printed
   run command matches.
   The wizard checks whether the variable or file exists now and warns if not. It never reads, prints
   or stores the value.
3. When Tokenize is in the goal (Phase 3): the vault is the `decoy run --vault PATH` option, not a
   pipeline field, so the wizard asks for a path, adds `--vault PATH` to the printed run command, notes
   that `--vault` cannot be combined with `--chunked`, reminds the user that the vault is cleartext at
   rest, and offers to add it to `.gitignore`.
4. When the pipeline has generated tables: a note that portable generation uses the separate
   `--master-key` / `--key-label` run options, which are independent of the mask secret
   (`decoy explain keys`).

When a keyed strategy is added after this step (for example in Fields or by a relationship), `stale`
marks Secrets `⚠` (4.3).

### 5.11 Review

```text
  Enter write · y view YAML · g go to a step · a save answers file · q save draft & quit
```

1. A summary: each source → target, each field and its strategy (bulk-assigned fields marked), checks,
   quarantine, quality, secret reference.
2. **Contains unmasked data:** a list of every file the pipeline writes that holds source values: the
   quarantine file, and the tokenize vault when used.
3. **Kept unchanged without review:** in flagged-only mode, "N fields kept unchanged without review"
   with their names and an explicit confirm ("Write with N unreviewed passthrough fields? [y/N]").
4. `y` shows the full YAML before writing.
5. On write: validate (config, compile, preflight), write `pipeline.yaml`, print the checklist of
   skipped or incomplete items, and print the run command.
6. `a` (or `--save-answers`) also writes the answers file. Off unless asked.
7. Offer to write `.decoy-ci.yaml` (schema `decoy-ci/v1`) with this pipeline registered. Default no
   (Phase 3).

## 6. Walkthrough

A single-table masking pipeline. The source `customers.txt` is pipe-delimited with no header row; the
column names are in `customers_header.txt`. Values and previews are illustrative. The walkthrough shows
the full V1 flow (Phase 1b); Phase 1a has no Checks step, no previews and no draft.

```text
$ decoy init

decoy init  ·  build a pipeline step by step
Keys: Enter default · b back · f forward · g go to · s skip · ? help · q save & quit

── 0 · Start ─────────────────────────────────────────────────────────
  1  New pipeline                                   (default)
  2  Edit a section of an existing pipeline         (runs decoy edit)
  3  Start from a preset (minimal, hipaa, pci, gdpr, generate)
  4  Replay an answers file
> 1

── 1/9 Goal ──────────────────────────────────────────────────────────
What should this pipeline do? Pick any (1,3 · 1-4 · a = all).
  1  Mask      replace sensitive values in data you already have   (default)
  2  Generate  build synthetic tables from scratch
  3  Subset    keep a referentially intact slice of the data
  4  Tokenize  reversible tokens, kept in a local vault
> 1

── 2/9 Sources ───────────────────────────────────────────────────────
 ✓ Goal  ▸ Sources  · Scan  · Fields  · Checks  · Quality  · Output  · Secrets  · Review
Where is the data?
  1  Local file      (default)
  2  Amazon S3
  3  Google Cloud Storage
> 1
Path: customers.txt
  ✓ found  ·  4.2 MB  ·  38,214 lines

What format is it?
  1  CSV (comma)
  2  TSV (tab)
  3  Delimited, other character     ← suggested: the sampled lines split on "|"
  4  Parquet
  5  Fixed-width
> 3
Delimiter [|]:

Where do the column names come from?
  1  First row of the file
  2  A header file
  3  I'll type them
> 2
Header file: customers_header.txt
  ✓ 8 names (one per line)  ·  matches the 8 fields per record

Parsed preview (first 3 records):
  cust_id │ full_name   │ email             │ phone        │ dob        │ zip   │ plan_tier │ notes
  10482   │ Jane Doe    │ jane.doe@mail.com │ 415-555-0142 │ 1984-03-12 │ 94110 │ pro       │ called re: refund
  10483   │ Raj Patel   │ rpatel@corp.io    │ 212-555-0199 │ 1991-11-02 │ 10001 │ basic     │
  10484   │ Ana Morales │ ana.m@mail.com    │ 312-555-0107 │ 1978-07-30 │ 60614 │ plus      │ VIP, spoke to Tom
Does this look right? [Y/n]

Table name [customers]:
Add another source? [y/N]

── 3/9 Scan ──────────────────────────────────────────────────────────
Rows to sample [10000]:

Scanning customers  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  10,000 rows · 1.4s

  field      type  nulls  unique     detected                                  confidence
  cust_id    int    0%    100%       identifier (name matched the record-       review
                                     number list)
  full_name  str    0%     97%       person name                               high
  email      str    1%     99%       email                                     high
  phone      str    3%     98%       US phone                                  high
  dob        date   0%     71%       date                                      high
  zip        str    0%     12%       US ZIP                                    high
  plan_tier  str    0%    3 values   -                                         -
  notes      str   41%     95%       free text (names?)                        medium

── 4/9 Fields · customers ────────────────────────────────────────────
How do you want to review the 8 fields?
  1  Every field, one at a time                     (default)
  2  Only flagged fields; choose one strategy for the rest
> 1

[1/8] cust_id   int · identifier, name matched the record-number list (review)
  Suggested  hash   same id always becomes the same value; joins keep working
  Preview    10482 → 9f2c41e07b    10483 → 03d7aa5c18   (preview key; real output differs)
  Enter accept · r reject · o options · k keep as-is · d drop · b back · ? why
>
  ✓ hash

[2/8] full_name   str · person name (high)
  Suggested  fake full name
  Preview    Jane Doe → Marcus Lee    Raj Patel → Dana Whitfield
>
  ✓ fake full name

[3/8] email   str · email (high)
  Suggested  fake email
  Preview    jane.doe@mail.com → kward@example.net
>
  ✓ fake email

[4/8] phone   str · US phone (high)
  Suggested  fake phone
  Preview    415-555-0142 → 646-555-0187
>
  ✓ fake phone

[5/8] dob   date · date (high)
  Suggested  date_shift  shift each date by a keyed offset
  Preview    1984-03-12 → 1984-09-27   (preview key; real output differs)
> o
  min_days (example, not the default: -365): -30
  max_days (example, not the default: 365): 30
  date_format (detected in the data) [%Y-%m-%d]:
  Preview    1984-03-12 → 1984-03-29   (preview key; real output differs)
  ✓ date_shift ±30 days

[6/8] zip   str · US ZIP (high)
  Suggested  truncate  keep the first 3 digits
  Preview    94110 → 941
> r
  Choose a strategy (or type a name):
    1  Keep as-is
    2  Remove ▸
    3  Replace with realistic fakes ▸
    4  Scramble consistently ▸
    5  Shuffle values within the field
    6  Generalize ▸
    7  Free text ▸
    8  Medical and billing code sets
  > 6
  Generalize:
    1  Numbers ▸    2  Dates ▸    3  Locations ▸
  > 3
  Locations:
    1  geo_generalize   coarsen a ZIP or lat/lng until each group is large enough
  > 1
  type:  1 zip   2 lat_lng   > 1
  cascade, most specific first (e.g. 1,3,7):
    1 zip3   2 zip5   3 state   4 h3_resolution_5   5 h3_resolution_7   6 h3_resolution_9   7 suppress
  > 1,3,7
  k_threshold (example, not the default: 20000): 20000
  Preview    94110 → 941    05753 → VT   (sparse areas fall back to the next level)
  ✓ geo_generalize · zip3 → state → suppress

  (an experienced user types instead:  > geo_generalize)

[7/8] plan_tier   str · 3 values · not flagged
  Suggested  redact  (the safe choice when nothing was detected)
  Preview    pro → ****
> k
  ✓ passthrough (kept as-is)

[8/8] notes   str · free text, names likely (medium)
  Suggested  text_redact  find names and places in the text and replace them
  Preview    "VIP, spoke to Tom" → "VIP, spoke to [PERSON]"
  ⚠ Name detection needs the en_core_web_sm model, which isn't installed.
      1  Show the install command
      2  Use pattern matching only (emails, phones, …; no names)
      3  Redact the whole field instead
  > 3
  ✓ redact

Fields: 6 replaced or scrambled · 1 kept · 1 redacted · 0 dropped

── 5/9 Checks ────────────────────────────────────────────────────────
After the run, check the output for leftover sensitive data and broken keys?
(post-scan integrity, report only) [Y/n]

Suggested checks (all on; type numbers to turn off, Enter keeps them):
  ✓ 1  leak_check     cust_id, full_name, email, phone   no source value survives (≤ 2% identical)
    2  column_in_set  plan_tier                          output stays within the values the scan saw
    3  Add another check…
> 2
  This check writes the values it saw into the pipeline file.
  Write these 3 values into the pipeline: basic, plus, pro? [y/N] y
  ✓ column_in_set on plan_tier
>

Send failing rows to a quarantine file instead of stopping the run? [Y/n]
  The quarantine file holds the original, unmasked rows. Keep it out of shared folders and git.
  Triggers (suggested from your choices):
  ✓ 1  validation_fail   a row fails one of the checks above
  ✓ 2  format_error      a dob value can't be parsed as a date
  >
  Quarantine file, relative to where decoy run starts [quarantine/pipeline.jsonl]:
  Add quarantine/ to .gitignore? [Y/n]

── 6/9 Quality ───────────────────────────────────────────────────────
Check the output's invariants after masking (post-validation)? [Y/n]
Produce a full fidelity report on every run? [y/N] y
  → adds --fidelity to the run command (a run option, not a pipeline setting)

── 7/9 Output ────────────────────────────────────────────────────────
Where should customers go?
  1  Local file      (default)
  2  Amazon S3
  3  Google Cloud Storage
>
Format:  1 CSV (default)   2 Parquet   3 Fixed-width
>
  ℹ CSV output is comma-separated with a header row. The source's pipe
    delimiter and missing header are not reproduced.
Path [out/customers.masked.csv]:

── 8/9 Secrets ───────────────────────────────────────────────────────
Seed: a plain number that makes runs repeatable. It is stored in the
pipeline and is not secret.
Seed [42]:

cust_id (hash) and dob (date_shift) are keyed. They need a mask secret:
a private key of 32+ random bytes that only people allowed to run this
pipeline should have. The pipeline stores where to find it, never the
secret itself. decoy run refuses this pipeline without it.
  1  Environment variable, referenced in the pipeline   (default)
  2  File, referenced in the pipeline
  3  I'll pass it to `decoy run --mask-secret` each time
>
Variable name [DECOY_MASK_SECRET]:
  ⚠ DECOY_MASK_SECRET isn't set in this shell. The next steps below show how to create it.

── 9/9 Review ────────────────────────────────────────────────────────
 ✓ Goal  ✓ Sources  ✓ Scan  ✓ Fields  ✓ Checks  ✓ Quality  ✓ Output  ✓ Secrets  ▸ Review

  customers.txt  (pipe-delimited, names from customers_header.txt)
    → out/customers.masked.csv

    cust_id     hash
    full_name   fake full name
    email       fake email
    phone       fake phone
    dob         date_shift ±30 days
    zip         geo_generalize zip3 → state → suppress
    plan_tier   passthrough
    notes       redact

  Checks      post-scan integrity · leak_check (4 fields) · column_in_set (plan_tier, 3 values written)
  Quarantine  validation_fail, format_error → quarantine/pipeline.jsonl
  Quality     post-validation · fidelity report on run
  Secrets     seed 42 · mask secret from env:DECOY_MASK_SECRET

  Contains unmasked data
    quarantine/pipeline.jsonl   (in .gitignore)

  Enter write · y view YAML · g go to a step · a save answers file · q save draft & quit
> g
  1 ✓ Goal   2 ✓ Sources   3 ✓ Scan   4 ✓ Fields   5 ✓ Checks
  6 ✓ Quality   7 ✓ Output   8 ✓ Secrets
> 4
  (field review reopens with every answer kept; f returns to Review)
  …
>
  ✓ config   ✓ compile   ✓ preflight
  ✓ wrote pipeline.yaml

Next:
  export DECOY_MASK_SECRET=$(openssl rand -hex 32)
  decoy run pipeline.yaml --fidelity
```

The pipeline it writes:

```yaml
version: 2

global_settings:
  seed: 42
  mask_secret_ref: "env:DECOY_MASK_SECRET"
  post_validation: true

sources:
  customers:
    type: file
    format: csv
    path: 'customers.txt'
    delimiter: "|"
    has_header: false
    # From customers_header.txt.
    column_names: [cust_id, full_name, email, phone, dob, zip, plan_tier, notes]

tables:
  - name: customers
    columns:
      - {name: cust_id,   strategy: hash,  namespace: cust_id}
      - {name: full_name, strategy: faker, provider: person_full_name, namespace: full_name}
      - {name: email,     strategy: faker, provider: person_email,     namespace: email}
      - {name: phone,     strategy: faker, provider: person_phone,     namespace: phone}
      - name: dob
        strategy: date_shift
        namespace: dob
        provider_config: {min_days: -30, max_days: 30, date_format: "%Y-%m-%d"}
      - name: zip
        strategy: geo_generalize
        provider_config: {type: zip, cascade: [zip3, state, suppress], k_threshold: 20000}
      - {name: plan_tier, strategy: passthrough}
      - {name: notes,     strategy: redact}

post_scan:
  integrity: true

validators:
  - name: leak_check
    columns: {customers: [cust_id, full_name, email, phone]}
    params: {max_identical_ratio: 0.02}
  # The user confirmed writing these source values.
  - name: column_in_set
    columns: {customers: [plan_tier]}
    params: {allowed_values: [basic, plus, pro]}

quarantine:
  enabled: true
  # Holds the original, unmasked rows.
  output_path: quarantine/pipeline.jsonl
  triggers: [validation_fail, format_error]

targets:
  customers:
    type: file
    format: csv
    path: 'out/customers.masked.csv'
```

The Phase 1a plan re-runs this YAML through `PipelineConfig.model_validate` and the config-only checks
on the new engine pin, as the review did for v2.

### 6.1 Branch: only flagged fields

```text
How do you want to review the 8 fields?
  1  Every field, one at a time                     (default)
  2  Only flagged fields; choose one strategy for the rest
> 2

Strategy for the 1 field that wasn't flagged (plan_tier):
  1  passthrough   keep as-is                        (default)
  2  redact
  3  hash
  4  Browse all strategies…
>
  Enter accept · type field numbers to review them one at a time instead
>
  ✓ plan_tier → passthrough

Reviewing 7 flagged fields…
[1/7] cust_id   int · identifier, name matched the record-number list (review)
  …

(at Review)
  Kept unchanged without review: 1 field (plan_tier)
  Write with 1 unreviewed passthrough field? [y/N]
```

### 6.2 Branch: fixed-width, layout typed in

```text
Where do the column names come from?
  1  A layout file (YAML/JSON)
  2  I'll type the layout
> 2
  First record:
            1         2         3         4
  0123456789012345678901234567890123456789012345
  0010482JANE DOE            19840312 94110PRO

  Column 1  name: cust_id    start [0]:    width: 7    type [str]: int
  Column 2  name: full_name  start [7]:    width: 20
  Column 3  name: dob        start [27]:   width: 8
  Column 4  name: zip        start [35]:   width: 6
  Column 5  name: plan_tier  start [41]:   width: 4
  Column 6  name:            (empty name finishes)
  Record width: 45 (the end of the last column)
  Require exactly 45 characters per record? [y/N]
  Save this layout to a file for reuse? [y/N] y
  Layout file [customers.layout.yaml]:

Parsed preview (first 3 records):
  cust_id │ full_name │ dob      │ zip   │ plan_tier
  10482   │ JANE DOE  │ 19840312 │ 94110 │ PRO
  …
```

### 6.3 Branch: S3 source

```text
Where is the data?
> 2
  Bucket: acme-exports
  Key: crm/2026-11/customers.parquet
  Region (optional): us-east-1
  Credentials: the AWS default chain (environment variables or the configured profile).
  Test access by reading the first rows? [Y/n]
  ✓ read 3 rows · Parquet · 8 columns
```

## 7. Section mode

```text
decoy edit checks pipeline.yaml
  -> load and validate the existing file (refuse if it does not load)
  -> pre-fill the step with the current values
  -> run the step (back and forth work within it)
  -> validate the whole resulting config
  -> show a diff of the changed block only
  -> confirm, then rewrite only that block
```

- Current values are the defaults, with origin `user` (4.3). If the block is absent, the step starts
  empty.
- If the file already fails validation for an unrelated reason, report that and still allow the edit,
  but do not claim the file is valid at the end.
- If an edit makes another block invalid (for example renaming a table that a relationship uses), name
  the broken block and offer to run that section next.

End-of-run checklist (both modes):

```text
Skipped or incomplete:
  - subset      no seed rule        run: decoy edit subset pipeline.yaml
  - checks      none configured     run: decoy edit checks pipeline.yaml
Set by hand (the wizard does not edit these):
  - transforms: filter (tables.orders)
Next: decoy validate config pipeline.yaml
```

Settings the wizard does not reach, listed as "edit the YAML" and named under "Set by hand" when the
file uses them:

- the `namespaces:` block and `protected_quarantine`;
- `on_pool_exhaustion` and `reference_date`;
- transforms other than `drop_column`: `filter`, `dedupe`, `derive`, `limit`, `sort`;
- column keys `deterministic`, `vault`, `when`, `coherent_with`, `cardinality_mode`, `error_policy`,
  `logical_type`, `parse_format`, `output_format`, `backend_type`, `pool_size`, `allow_collisions`,
  `dtype`, `sentinel_to_null`;
- the strategies with `offer_in_wizard=False` (`tokenize` aside, which the Tokenize goal shows);
- subset `keys` seeds, edge directions and `allow_dangling`.

## 8. How a section is written

Changing one section changes only that block's lines. Everything else in the file, including comments,
key order and blank lines, is preserved byte for byte.

Method (19.2, settled): a block splice built as the 2026-11-07 plan's editor
`src/decoy/cli/wizard/_yaml_edit.py` on the shared mark index `src/decoy/_yaml_marks.py`, not a second
`splice.py`. No `ruamel.yaml`.

- The editor's span rule, refusals and checks before the replace are the plan's (its section 4.7):
  whole-line spans, refusal of anchors, aliases, merge keys, flow style and duplicate keys
  (`init.yaml_edit_unsupported`), a re-parse check that the result equals the original with exactly the
  intended edits, a comment-survival check, and a hash check that the file did not change since it was
  read (`init.yaml_changed`).
- This spec extends it from column entries to top-level blocks: a block spans from its column-0 key to
  the line before the next column-0 key or end of file, and a comment directly above a key stays with
  that key.
- When the block cannot be located safely, the wizard writes `<file>.new` and prints the diff for the
  user to accept.
- Writes go through `src/decoy/_atomic.py` and never follow a symlink out of the working tree
  (`init.yaml_symlink`).
- `global_settings` is shared by Quality and Secrets, so those two sections edit individual keys inside
  that block rather than the whole block.

## 9. Validation

The wizard builds a plain dict and validates with the engine's `PipelineConfig.model_validate`, through
the one gate path `decoy.cli.gate`. It does not re-implement any rule.

- After each step: validate the partial config where possible; on failure, re-ask only that step and
  show the engine's message through the value-free error converter.
- Before writing: validate the whole config.
- After writing: run the same layers as `decoy validate` (config, compile, preflight) and show the
  grouped report.
- `--no-validate` skips the final run.

## 10. Skip, drafts and resume

- Skipping never invents a value. It leaves a marker comment such as
  `# TODO(decoy-init): set the source path`, and `decoy validate` reports remaining markers as warnings.
- `q`, Ctrl-C and errors save a draft beside the output as `.pipeline.yaml.init-draft.json` (for an
  output named `pipeline.yaml`), mode 0600, written atomically through `src/decoy/_atomic.py`. There
  is one draft per output path. `--resume` loads it and opens the step the user was on; with more than
  one draft in the folder it lists them. The wizard offers to add the draft name to `.gitignore`
  through the shared helper (12).
- The draft is a versioned file, schema tag `decoy-init-draft/v1`, read by a strict loader: an unknown
  key, a missing or wrong tag, or a bad type refuses the draft with `init.draft_invalid` (exit 1),
  naming the file and key path, never a value. A later breaking change takes `v2`.
- The draft holds answers (with their origin and stable ids), step status and a named allow-list
  projection of the scan, per field: type, null share, unique share, detector id and confidence bucket.
  Nothing else from the scan is copied. In particular `FieldStats` and `ColumnProfile` are never
  serialized as they are, because they carry `top_values`, `min_value` and `max_value`.
- The projection reuses `cli/scan.py` `_safe_field_record`, which already keeps only privacy-safe
  fields. Phase 1b promotes it to one shared module, `src/decoy/_safe_profile.py`, used by `decoy scan`
  and the draft. The existing sentry `tests/sentry/test_profile_raw_value_isolation.py` guards it; it
  is pointed at the new module.
- The draft never holds sample values, scan profile values, secrets or raw data. A `column_in_set`
  value list the user confirmed is the one exception (4.5).
- A successful write deletes the draft.
- Drafts and `--resume` ship in Phase 1b.

## 11. Non-interactive parity and answers files

- The answers file is the 2026-11-07 plan's `decoy-init-answers/v1` format with its strict loader.
  Every prompt has an answers-file key, using the same names as the YAML blocks plus wizard-only
  choices (review mode, bulk strategy). `--answers FILE` builds without prompts; missing required
  answers fail with a message naming the key path, never the value.
- `unlisted: confirm` is allowed in an answers file (owner Q3, 2026-11-07): it accepts every suggestion
  the file does not list, in a file the user wrote.
- The answers file is written only when asked: `--save-answers FILE`, or `a` on the Review screen.
- With no terminal attached and no `--answers`, the command refuses with exit code 1 rather than hang
  (owner, 2026-11-08). The 2026-11-07 plan's write of the `minimal` preset off a terminal is dropped.
- `--json` keeps its current meaning: no wizard, emit a JSON record of what was written. It implies
  `--no-input`.
- `-y` skips the overwrite confirmation only. It does not accept defaults for other prompts.
- Answers files ship in Phase 2.

## 12. Architecture

A new subpackage `src/decoy/cli/wizard/`; `cli/init.py` stays the thin entry that dispatches to it.
`init.py` is about 690 lines on main and must not grow. The CLI has no module-size sentry today, so the
Phase 1a plan adds one (`tests/sentry/test_module_size*`) or a census line that holds `init.py` and the
new modules to their sizes.

Modules follow the 2026-11-07 plan's names and placement (its section 11), plus the modules this spec's
extra steps need:

```text
src/decoy/_yaml_marks.py       shared YAML mark index (moved from ci/locations.py)
src/decoy/cli/wizard/
  _prompts.py       Prompter protocol: terminal, answers-file and scripted implementations, key table
  _answers.py       decoy-init-answers/v1 model, strict loader, save
  _flow.py          sections, path-role check, write step, gate
  _review.py        per-field review loop over a Prompter
  _state.py         WizardState: answers with origin, stable table and field ids, scan projection,
                    step status; serialises to the draft
  _nav.py           back / forward / go-to, and running each step's stale() to mark ⚠
  _tree.py          the strategy tree (5.4.3) built from strategy_catalog() and the providers
  _preview.py       sample values and shapes (--no-samples); previews once engine gap 16.1 exists
  _yaml_edit.py     the comment-preserving editor (section 8)
  _findings.py      --review-findings
  _edit.py          the `decoy edit` command, registered from here (not a flat cli/edit.py)
  _checklist.py     the end-of-run list
  steps/            one module per step
src/decoy/_safe_profile.py     privacy-safe field record, promoted from cli/scan.py (10)
src/decoy/_gitignore.py        the one .gitignore helper (quarantine, draft, vault)
```

Placement. `cli/` is frozen, so new commands go in a named sub-package. The two CODEMAP rows the
2026-11-07 plan adds in W1.1 ("Interactive review wizard" and "Shared YAML document structure") place
the wizard files; the private shared primitives row places the top-level files.

| New file | Directory | CODEMAP "Where things go" row | Sits beside |
|---|---|---|---|
| `cli/wizard/*.py`, `cli/wizard/steps/*.py` | `src/decoy/cli/wizard/` | "Interactive review wizard for `decoy init`" (new in W1.1) | `src/decoy/cli/gate/` |
| `cli/wizard/_edit.py` | `src/decoy/cli/wizard/` | same; `src/decoy/__main__.py` registers the `edit` verb from it | `cli/wizard/_flow.py` |
| `_yaml_marks.py` | `src/decoy/` | "Shared YAML document structure and source-mark indexing" (new in W1.1) | `_atomic.py` |
| `_safe_profile.py` | `src/decoy/` | "Private shared filesystem or process primitives used by more than one package" | `_atomic.py` |
| `_gitignore.py` | `src/decoy/` | same | `_atomic.py` |
| `tests/unit/test_wizard_*.py`, `tests/e2e/test_init_wizard*.py` | `tests/unit/`, `tests/e2e/` | the W1.1 wizard row | existing init tests |

The `.gitignore` helper is the one place that appends a line to a `.gitignore`: it creates the file if
missing, adds the entry once, and never rewrites other lines. Quarantine (5.7), the draft (10) and the
vault (5.10) call it; a sentry fails on any other `.gitignore` write under `src/decoy/`.

New-file YAML text comes from the one emitter `cli/_scaffold_yaml.render` (G-ONE-EMITTER), owned by
SCAN-MULTI S3a.1 and a Phase 1a prerequisite (17).

Each step is an object with:

- `applies(state) -> bool`
- `defaults(state, existing) -> dict`
- `ask(state, prompter) -> dict` (the only part that touches the terminal, through the `Prompter`)
- `to_block(answers) -> dict`
- `stale(state) -> list[Change]` (what no longer fits and why, for `⚠` marking; 4.3)
- `depends_on(state) -> set[str]` (optional: which steps to re-check)
- `incomplete(state) -> list[str]`

Rules:

- Library code does not know its callers. Detection, inference inputs, strategy metadata, keyed-ness
  and validation stay in `decoy_engine`; the wizard calls them.
- All menus come from the engine's registries and config enums. The grouping in `_tree.py` is the only
  hand-written strategy list, and a test keeps it in step with the engine. The validator table (5.7) is
  the second, temporary one, with its own sync test, until engine gap 16.8 closes.
- Terminal I/O is isolated behind the `Prompter` so steps are tested with scripted input.

## 13. Terminology

User-facing text does not say "STORM"; it says "scan" and "suggested". Strategy names are shown with a
plain description, and faker providers are shown by what they produce ("fake email"), with the
provider name available under `?`.

Today `cli/_init_inference.py` says "STORM" 24 times in review copy that lands in generated YAML, and
`cli/init.py` says it 8 times. Phase 1a does not carry that text over, and adds a sentry that fails if
generated YAML or wizard prompt text contains "STORM".

## 14. Exit codes

Only the six public codes exist (`src/decoy/cli/exit_codes.py`). No new codes.

| Code | Wizard use |
|---|---|
| 0 | Wrote a valid result, or `--diff` completed |
| 1 | Usage error, bad answers file, cancelled, no terminal, config does not load (`EXIT_USAGE`; cancel maps here by the house rule) |
| 2 | Final validation produced warnings and `--fail-on-warning` is set |
| 3 | I/O or engine failure while scanning, previewing or writing |
| 4 | Not used by the wizard (`EXIT_FINDINGS`) |
| 5 | Not used by the wizard (`EXIT_CAPACITY`) |

## 15. Testing

- **Per-step tests** with a scripted `Prompter` and a fixture state, asserting the block produced.
- **Navigation tests**, one per `stale` case in 4.3: back and forward keep answers; removing a source
  marks Fields, Relationships and Output; renaming a table updates every reference through its id; a
  strategy change after validators marks Checks; turning a goal off and on restores its answers and
  flags seeds that name a removed table; a re-scan changes the flagged set; a changed delimiter or header
  file re-runs Scan and Fields; a changed source format refreshes the Output default; a keyed strategy
  added after Secrets marks Secrets; a confirmed relationship marks Fields; suggested values refresh
  silently and user values never do; Review refuses to write while a step is marked.
- **Tree sync test:** the leaves equal, exactly once each, the `offer_in_wizard=True` strategies except
  `faker`, plus every provider in the registry minus the named hidden set (5.4.3), plus `tokenize` when
  Tokenize is in the goal. Nothing in the tree is unknown to the engine.
- **Secrets test:** pinned outcomes. A shuffle-only pipeline: asked. A faker-only pipeline: not asked.
  Faker with `deterministic: true`: asked. A relationship with a composite parent key: asked, with the
  generic sentence and no field list. One field per catalog strategy: asked exactly when
  `secret_requirements_for_config` reports a requirement, and the named fields equal
  `keyed_columns_for_config`. Mutation: adding a hand-kept keyed-strategy list to the CLI and reading it
  instead of the engine must turn the test red.
- **Relationship test:** confirming a relationship whose key uses `redact` is refused until a
  `join_safe` strategy is chosen; parent and child keys end with one namespace.
- **Editor tests:** the 2026-11-07 plan's AT-W13, AT-W14 and AT-W21, extended to top-level blocks: a
  file with comments, blank lines, anchors and reordered blocks; editing each block leaves every other
  byte unchanged. Include a block at end of file without a trailing newline.
- **Round-trip property:** the full flow with answers A equals the same sections run one at a time in
  `decoy edit` with the same answers.
- **Privacy test:** a fixture plants canary values that land in the profile's `top_values`,
  `min_value` and `max_value` and in a free-text cell. The test runs the wizard and checks that no
  canary and no secret value appears in:
  - the draft, the answers file and the pipeline;
  - `-v` logs and `--json` output;
  - the engine error text the wizard re-shows (section 9).

  Only `env:` and `file:` references appear for secrets. The allow-list has one entry: values under
  `validators[name=column_in_set].params.allowed_values` for a field the user confirmed (4.5), in the
  pipeline, the draft (mode 0600) and the answers file only. User-typed values are not canaries. `--no-samples` output contains no real values.
- **No-terminal test:** the command refuses cleanly.
- **Golden tests:** the walkthrough in section 6, and a two-table pipeline with a relationship and a
  subset filter, validate against `PipelineConfig` and pass the config-only checks.

## 16. Engine gaps

1. **Previews.** Add one small public engine function that applies one column config to a short list of
   values. It is a legitimate library API and knows nothing of its caller. Running the whole draft
   pipeline in memory is not used: it would need every source and the real secret.
   - Keyed strategies preview under a throwaway key, labelled "preview key; real output differs". The
     real secret is never resolved for a preview.
   - Strategies that need the whole table (`shuffle`, relationships) get a sentence instead of values.
   - Previews ship in Phase 1b once this exists.
2. **Header file reference.** CONFIG-EXPLICIT E1's `column_names_file` closes this. Write it once E1 is
   released; until then, copy the names into `column_names`.
3. **CSV target dialect.** CSV targets have no delimiter or header settings, so a pipe-delimited or
   headerless source becomes comma-delimited output with a header. Keep the notice; logged as engine
   backlog. It does not block.
4. **Delimiter and layout suggestion.** Delimiter sniffing belongs next to the CLI's CSV reader and uses
   `csv.Sniffer`, the standard library's established method. No layout suggestion in V1 (19.6).
5. **Fidelity report** is a `decoy run` option, not a pipeline setting. The wizard adds it to the run
   command. Fine as written.
6. **Catalog defaults and descriptions, plus provider options.** `StrategyOption` has no `default` and
   no plain description. Providers expose only a `CapabilityMatrix`, so `random_choice`,
   `random_int_range`, `composite_custom` and `composite_provider` have no `provider_config` metadata to
   prompt from. Until this lands, optional options show the catalog `example` and those providers are
   hidden (5.4.2, 5.4.3).
7. **A generate-column catalog.** The 11 `GenerateColumnConfig.type` values have no catalog. Generated
   tables (Phase 2) wait for it.
8. **A public validator list with params metadata, plus a config-time check.** `_REGISTRY` in
   `validators/_registry.py` is private, `ValidatorEntry.name` is a free string, and params are checked
   by each validator at run time, so neither `model_validate` nor the config-only checks catch a bad
   validator name or param. Prefer closing it in the same engine release Phase 1a repins to (0.20.0);
   if it slips, the temporary CLI table of 5.7 stands until it lands.
9. **Built-in detector selection.** `profile_columns` cannot select a subset of the built-in detectors.
10. **The stale `GlobalSettings` docstring.** `config/_global_settings.py` says "pre-GA the keyed surface
    falls back to `job_seed`". No fallback exists in any release phase. A one-line engine docs fix.
11. **`credentials_ref` has no meaning for local runs.** It is opaque to the engine and only the
    platform resolves it. The CLI does not prompt for it (5.2); the engine docs should say so.
12. **Keyed fields.** A public `keyed_columns_for_config(config)` returning `(table, column, strategy)`
    entries, beside `secret_requirements_for_config`. Shipped in the Phase 1a engine release (0.20.0).
    It returns no entry for a requirement that no single field carries, such as a composite parent key.
13. **Join-safe key refusal.** The engine refusal `config.key_column_not_join_safe` (2026-11-07 plan E1):
    a relationship key column with a strategy the catalog does not mark `join_safe` fails at config
    time. A Phase 2 prerequisite.
14. **Per-column free-text advisory.** A public check that applies the free-text advisory thresholds
    to one column's `FieldStats` from the scan, so the Fields step can flag a field before validation.
    Lands before Phase 1b.

## 17. Phasing

Every part either replaces nothing until 1b lands the full flow, or 1a ships behind the existing entry
with the old flow removed in the same slice (pre-GA hard delete). The Phase 1a plan picks one and says
which.

1. **Phase 1a** (one CLI slice plus the repin):
   - Prerequisites. 1a waits for these, because the wizard reuses them and each has a single owner
     (matching roadmap row 32b's After column):
     - SCAN-MULTI S3-engine: the engine's `starter_config` (S3-engine.2), with the 2026-11-07 plan's E1
       `column_entry` built on it;
     - SCAN-MULTI S3a.1: `cli/_scaffold_yaml.render` and G-ONE-EMITTER;
     - the engine release that carries them, with #400 (`strategy_catalog()`) and gap 16.12.
   - Engine release and repin. The CLI pins `decoy-engine==0.19.0`, which predates `strategy_catalog()`
     (#400 merged after the `v0.19.0` release #399). 1a cuts engine 0.20.0 and moves both the
     `pyproject.toml` pin and the engine SHA in `requirements-dev.lock`. The lock change is a full-suite
     escalation trigger, so the 1a merge head gets the full suite diffed against the stored main
     baseline. The repin follows the engine repin checklist.
   - In the same slice: `TRANSFORM_IDS` in `cli/completers.py` is replaced by `strategy_catalog()`, and
     `_NAMESPACE_REQUIRED_STRATEGIES` in `cli/init.py` is deleted in favour of the catalog's
     `namespace_required`.
   - `WizardState` with answer origin and stable ids, and `stale()` per step (4.3).
   - The `Prompter` with numbered menus, plus back, forward and go-to.
   - Goal limited to Mask.
   - Sources limited to local files: CSV, including TSV and any other delimiter through the format and
     delimiter options of 5.2, and Parquet. Header options included, and `has_header` always written.
   - Scan; Fields in every-field mode, with the catalog tree and options.
   - Output limited to local, then Secrets via `secret_requirements_for_config`.
   - Review with final validation.
   - The "STORM" text sentry (13) and the module-size sentry or census line (12).
2. **Phase 1b:**
   - Fixed-width in and out, and S3/GCS without credential prompts.
   - Flagged-only mode with the guard in 5.4.1 (needs engine gap 16.14).
   - Checks with the quarantine (H1) and `column_in_set` (H2) rules, and Quality.
   - Drafts and `--resume` with the allow-list projection and `_safe_profile.py` (10).
   - Previews, once engine gap 16.1 exists.
3. **Phase 2.** Section mode (`decoy edit`) with the editor of section 8. Relationships with the key
   rule of 5.5, after engine gap 16.13. Subset (filter and sample). The Generate and Subset goals, and generated tables (after
   engine gap 16.7). `--answers` and `--save-answers`.
4. **Phase 3.** Tab completion and arrow-key menus through `prompt_toolkit`, in its own slice with its
   own lock-change escalation (19.3). The CI manifest. The Tokenize goal with its `--vault` run option.

Each phase ships with its tests and leaves the previous behaviour working. Pre-GA = hard delete: the old
Q&A path is removed when the wizard replaces it, not kept behind a flag.

The Phase 1a plan is written as a revision of the 2026-11-07 plan (section 0). That plan's parts map
onto these phases; its post-scan findings review (W3.2) and detector section (W2) keep their own
dependencies on SCAN-ML.

## 18. Decisions

Settled 2026-10-30: one flow with skippable stops, a skipped-items list at the end, multi-select goal,
per-table scan prompt, single-section editing that touches only that block.

Settled 2026-11-07 (owner answers on the 2026-11-07 plan): Q1 post-scan review is
`decoy init --review-findings` (revisit the spelling before release); Q2 a rejected finding persists as
`post_scan.dismissed`; Q3 `unlisted: confirm` is allowed in answers files.

Settled 2026-11-08 (UX review):

1. Goal accepts any combination, including all four (offered per phase, 5.1).
2. The user can move back and forth through the steps (back, forward, go to) without losing answers.
3. Field review defaults to every field one at a time. "Only flagged fields" is an option; with it, one
   strategy is chosen for the unflagged fields, from a short list with `passthrough` first, then
   `redact`, `hash`, then the full tree.
4. Sample values are shown by default; `--no-samples` turns them off.
5. Strategies are presented as a tree grouped by what they do, with no long flat lists. Experienced
   users can type a name instead, with Tab completion once `prompt_toolkit` lands.
6. Checks and Quality are two separate steps.
7. The answers file is written only when asked.

Settled 2026-11-08 (spec review, recommended options taken under the owner's standing V1 rule): the
items in section 19 and the review items mapped in section 0.3.

Settled 2026-11-08 (owner answers on v3 section 22):

1. Field review keys are the v2 keys: Enter, `r`, `o`, `k`, `d`, `b`, `q` (4.2).
2. With no terminal and no answers file, the command refuses with exit 1 (11).
3. The flagged-only default for unflagged fields is `passthrough`, with the 5.4.1 guard and a confirm
   on Review (5.4.1, 5.11).

## 19. Open decisions (settled in v3)

1. **Section mode spelling.** Settled: a separate verb, `decoy edit <section> <pipeline>` (section 3).
2. **Section write method.** Settled: block splice with the `<file>.new` plus diff fallback, built as
   the 2026-11-07 plan's `_yaml_edit` on the shared `_yaml_marks` index. No `ruamel.yaml` (section 8).
3. **Prompt library.** Settled: Phase 1 uses numbered menus behind the `Prompter` protocol, with no new
   dependency and scripted tests. A later slice adds `prompt_toolkit` directly, with its lock change as
   its own escalation; it is preferred over `questionary` (one fewer dependency, full control of
   completion). Neither is in the CLI lock today.
4. **Previews.** Settled: one small public engine function (16.1).
5. **Draft file.** Settled: `.pipeline.yaml.init-draft.json` beside the output, mode 0600, written
   atomically through `_atomic`, only the allow-listed fields, one per output path, `--resume` lists
   them when there is more than one, `.gitignore` offered (section 10).
6. **Fixed-width layout suggestion.** Settled: not in V1. The typed layout with a ruler is enough;
   revisit with real files.
7. **`keys` subset seeds.** Settled: no wizard prompt. The key list is raw data; it stays hand-edited.

## 20. Sources and basis

- `docs/cli-reference.md`: current `decoy init` options.
- `decoy_engine/config/` (`_pipeline.py`, `_sources.py`, `_fixed_width.py`, `_tables.py`,
  `_relationships.py`, `_subset.py`, `_post_scan.py`, `_validators.py`, `_global_settings.py`,
  `_targets.py`): the blocks, enums and rules the steps map onto.
- `decoy_engine.strategy_catalog()` and the provider registry: the strategy tree's leaves and options.
- `decoy_engine.secret_providers.secret_requirements_for_config`: which fields need the mask secret.
- `src/decoy/cli/init.py`, `src/decoy/cli/_init_inference.py`: existing prompts and inference.
- `decoy explain keys`: seed, mask secret and master key semantics.
- The 2026-11-07 plan `docs/plans/2026-11-07-init-wizard.md` (CLI branch `plan/init-wizard`): Prompter,
  mark index, editor, catalog, key rule, answers format, owner answers Q1-Q3.
- The spec review of 2026-11-08 (vault `10_Projects/decoy/handoffs/phase1/init-wizard/`).
- Interaction patterns: guided scaffolders such as `npm init`, `cargo generate` and `dbt init` (prompt
  per field, defaults in brackets, review before write); `prompt_toolkit` for completion.
- Stale-answer invalidation (4.3): build-system dirty tracking, where each output records its inputs
  and is rebuilt only when one changes (make prerequisites, Bazel action keys), and form-wizard
  libraries that keep per-field "dirty" versus "touched" state (Final Form, React Hook Form). Answer
  origin is the "touched" bit.
- Block splice (8): the CLI's own mark index in `ci/locations.py` (moving to `_yaml_marks.py`), with
  `ruamel.yaml` round-trip as the comparison that was rejected for formatting churn and a new
  dependency.
- Value shapes for `--no-samples` (4.5): the character-class pattern masks of data-profiling tools
  (Talend Data Quality and OpenRefine pattern analysis: letters to `a`/`A`, digits to `9`, punctuation
  kept).
- Delimiter sniffing (16.4): Python's `csv.Sniffer`.

## 21. Hot-fix of today's `decoy init` (done)

Done: CLI #114 (`fix(init): write the typed paths into the preset pipeline`) merged it on 2026-11-08.
It fixed the silent no-op path edit: `decoy init` with a preset dropped the typed input and output
paths, because the path regex wanted a top-level `input:`/`output:` key that no bundled template has,
so the written pipeline read `./input.csv` and wrote `./output.csv`. The optional copy fix in the same
slice ("STORM detected medical record numbers", M9 and L4) was not part of #114 and moves to Phase 1a
(sections 5.3 and 13).

## 22. Open for the owner

Items still open. Each has the spec's current default.

1. **Findings review command home.** The owner kept `decoy init --review-findings` for now (2026-11-08)
   and noted two things. A findings review needs a finished run passed to it, and `init` does not fit a
   post-run operation, so the final home is to be decided later.
   - How the run is named today: `--report FILE`, the run's `post-scan-integrity/v2` report written by
     `decoy report integrity --output`, bound to the pipeline by its `config_sha256` (SCAN-ML C2a). A
     run record (`decoy-run-result/v1`, RESULT E1) could replace it once that format reaches the CLI.
   - With no report: the command refuses with exit 1 (`init.report_missing`) and prints the command that
     writes one. A report for another pipeline version refuses with `init.report_stale`.
   - Current: `decoy init --review-findings PIPELINE --report FILE`. Candidates include
     `decoy edit findings` and a post-run verb.
2. **Tokenize and the `vault: true` column flag (M11).** Does the Tokenize goal also offer `vault: true`
   on columns, or only the `tokenize` strategy? Current: only the strategy; `vault` is in the
   "edit the YAML" list (7).
3. **`drop_column` under CONFIG-EXPLICIT (M6).** Whether a dropped column still counts as declared
   under rule 3 depends on CONFIG-EXPLICIT E2's definition. Current: the Phase 1a plan checks E2 and
   the wizard follows it; if E2 says a dropped column is undeclared, the wizard also declares it.
