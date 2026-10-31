# `decoy init` wizard: design spec

Status: DRAFT spec for discussion, not committed scope. Created 2026-10-30. Promotion into real scope
is a planner decision. Items marked **OPEN** are undecided.

Related: `docs/cli-reference.md` (`decoy init` today), `docs/ci-contracts.md` (the CI manifest the
wizard can scaffold), engine config models in `decoy_engine/config/`.

## 1. Summary

Turn `decoy init` from a three-question scaffold into a guided, skippable walk through every part of a
pipeline, from the goal to the CI manifest. The same steps can be re-entered later to change one part
of an existing pipeline, and only that part of the YAML file is rewritten.

Two modes, one set of steps:

- **Project mode** (`decoy init`): walk every applicable step and write a whole project.
- **Section mode** (`decoy init <section> <pipeline>`): run one step against an existing pipeline and
  rewrite only that block.

## 2. Goals and non-goals

Goals:

1. A new user gets from "I have a Parquet or CSV file" to a validated pipeline without reading the
   schema.
2. Any step can be skipped. Skipped work is listed at the end with the command that finishes it.
3. One part of an existing pipeline can be changed without touching the rest of the file, including
   the user's comments.
4. The wizard can never write a config the engine rejects.
5. Every prompt has a non-interactive equivalent, so the same result can be scripted.

Non-goals (V1):

- A full-screen terminal editor. Prompts only.
- Editing strategy parameters beyond a column's strategy and its required options.
- Replacing hand-editing. The YAML stays the source of truth, and users are expected to edit it.
- Network access, accounts or telemetry. The wizard is local like the rest of the CLI.

## 3. Command surface

```text
decoy init [INPUT_FILE]                       project mode (existing positional arg kept)
decoy init <section> <pipeline>               section mode
decoy init --resume                           continue an interrupted project-mode run
decoy init --list-sections                    print section names
```

Existing flags stay: `-o/--output`, `--preset`, `-y/--yes`, `--json`, `-q`, `-v`.
New flags:

| Flag | Meaning |
|---|---|
| `--answers FILE` | Read answers from a YAML or JSON file instead of prompting (see section 9). |
| `--skip SECTION[,..]` | Skip these sections in project mode. |
| `--only SECTION[,..]` | Run only these sections in project mode. |
| `--no-validate` | Skip the final validation (escape hatch; not recommended). |
| `--diff` | Section mode: print the diff and exit without writing. |

**OPEN:** whether section mode is spelled `init <section>` or a separate verb such as `edit`. `init`
usually means "create", so `decoy init subset pipeline.yaml` reads oddly as an edit. See section 15.

Section names (fixed, tab-completed): `goal`, `sources`, `scan`, `columns`, `relationships`, `subset`,
`targets`, `secrets`, `checks`, `ci`.

`goal` is not editable in section mode (it only switches steps on and off). Re-run `decoy init` for that.

## 4. Steps

Each step maps to one top-level block of the pipeline YAML, so a section edit has a clear boundary.

| # | Step | Writes | Applies when | If skipped |
|---|---|---|---|---|
| 1 | `goal` | nothing directly (sets capabilities) | always | defaults to mask |
| 2 | `sources` | `sources:` | any table is mask-kind, or subset is on | `TODO` path placeholder |
| 3 | `scan` | nothing (feeds steps 4 and 5) | sources exist | no inferred suggestions |
| 4 | `columns` | `tables:` | always | inferred picks kept, marked `REVIEW` |
| 5 | `relationships` | `relationships:` | two or more tables | none declared |
| 6 | `subset` | `subset:` | subset capability on | no `subset:` block |
| 7 | `targets` | `targets:` | always | default `./out/<table>` |
| 8 | `secrets` | `global_settings:` | always (required if tokenize or keyed masking) | reminder in checklist |
| 9 | `checks` | `validators:`, `quarantine:` | always | none |
| 10 | `ci` | separate `.decoy-ci.yaml` | always | not created |

### 4.1 `goal`

Multi-select. The user may pick several.

| Choice | Effect |
|---|---|
| mask | Tables with source files are mask-kind (`columns:`). Enables `sources`, `scan`. |
| generate | Tables built from scratch are generate-kind (`generate_columns:`). No source needed. |
| subset | Enables the `subset` step. Requires Parquet sources (see section 4.6). |
| tokenize | Adds `tokenize` to the column strategy list and requires a vault path and a mask secret. |

Notes grounded in the engine schema:

- There is no top-level `mode:` in the config. A table is mask-kind when it has `columns` and
  generate-kind when it has `generate_columns`. A config may mix both, and the engine generates first so
  its output can feed foreign keys on the mask side. When the user picks both mask and generate, the
  wizard asks which tables are which.
- Subset-then-mask order is structural. There is no setting for the reverse.
- Tokenize is a column strategy, not a job type.

### 4.2 `sources`

Prompt for one or more file paths. Detect format from the extension (`csv`, `tsv`, `parquet`;
`fixed_width` needs a layout file and is out of scope for V1). Each file becomes a source named after
the file stem; the user may rename it. Reject missing paths with a clear message and offer to keep the
path anyway (the file may not exist yet on this machine).

If subset is on and a source is not Parquet, say so here and offer to continue without subset.

### 4.3 `scan`

Per source: "Scan `customers.parquet` for PII? [Y/n]". A scan reuses the existing inference in
`cli/_init_inference.py` and the `decoy scan` profiler. Results (column types, PII candidates,
suggested strategy, confidence) are held in memory and in the draft file, and feed `columns` and
`relationships`. Nothing is written to the pipeline from this step.

### 4.4 `columns`

Per table: choose "use scanned table", "pick from sources" or "create new table".

- **Scanned or picked table.** Show a table of every column with its suggested strategy and confidence.
  Ask only about columns flagged low-confidence or sensitive. Offer "accept the rest". For each asked
  column, show strategies grouped by intent with a one-line description from the registry (for example:
  hide / replace with fake data / scramble / keep shape / tokenize / leave unchanged).
- **New table (generate-kind).** Ask for a table name, then loop: column name, then generator, then
  options. End with a row count.
- Strategies that need options (for example `faker` needs a `provider`) ask for them.

Written as `tables[].columns[]` or `tables[].generate_columns[]`. Low-confidence guesses are written
with a `# REVIEW:` comment, as `decoy init <file>` does today.

### 4.5 `relationships`

Shown only with two or more tables. Candidates come from the scan (matching key names and value
overlap). For each candidate, the user confirms or edits:

1. Parent table and column(s).
2. Child table(s) and column(s). Composite keys are supported (the config takes a list of columns).
3. Orphan policy (required, no default): `preserve`, `remap`, `warn`, `fail`, each with a plain
   sentence of explanation.
4. Optional namespace.

The user may add relationships by hand. If the scan was skipped, the step starts empty.

The config has no one-to-one or one-to-many field. Cardinality is implied by the parent and children
lists, so the wizard does not ask for it.

### 4.6 `subset`

Applies only when subset is on. Per the engine schema, a seed is one of three modes:

| Mode | Prompts | V1 wizard |
|---|---|---|
| `filter` | table, then one or more `{column, op, value}` predicates (ANDed) | yes |
| `sample` | table, key columns, then `fraction` or `count` | yes |
| `keys` | table, key columns, explicit key list | no (edit the YAML) |

Operators: `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in`, `is_null`, `is_not_null`.

Then ask for an optional budget: `max_total_rows` and `max_table_seed_multiple`. Offer a dry run
(`decoy subset --dry-run`) to show projected row counts before finishing. Edge directions and
`allow_dangling` are advanced and left to hand-editing, with a note. "None" removes the `subset:` block.

Subset requires Parquet sources, so a CSV source gets a clear error here with the fix.

### 4.7 `targets`

One target per table. Default format follows the source format. Path defaults to `./out/<table>.<ext>`.
At least one target is required by the schema.

### 4.8 `secrets`

- `global_settings.seed` (integer; default offered).
- `global_settings.mask_secret_ref`: a **reference** only, for example `env:DECOY_MASK_SECRET` or
  `file:/path/to/secret`. The wizard never asks for or stores the secret value. Required when a keyed
  strategy or tokenize is used.
- If tokenize is on: vault path, and a reminder that the vault is cleartext at rest.

### 4.9 `checks`

Optional post-scan rules: validators and quarantine settings the engine already supports today. As
F35/F36 land, this step grows to author quality contracts and invariants. Out of scope for this spec
beyond a placeholder step.

### 4.10 `ci`

Offer to write `.decoy-ci.yaml` (schema `decoy-ci/v1`) with the pipeline registered, validation on, and
optional drift and evidence entries. The staged-file scan is off by default.

## 5. Flow

### 5.1 Project mode

```text
decoy init
  1 goal            (multi-select)
  2 sources         if applicable
  3 scan            y/n per source
  4 columns         per table
  5 relationships   if 2+ tables
  6 subset          if subset on
  7 targets
  8 secrets
  9 checks
  10 ci
  -> show the assembled YAML, confirm
  -> write files
  -> validate
  -> print the checklist of skipped or incomplete items and the next command
```

Rules:

- The user can type `s` at any prompt to skip the whole step, and `b` to go back one step.
- Ctrl-C at any point saves a draft and exits with code 1 (usage/cancelled). Nothing is written to the
  target pipeline file.
- If the target file already exists, ask: edit a section, overwrite, or cancel.

### 5.2 Section mode

```text
decoy init subset pipeline.yaml
  -> load and validate the existing file (refuse if it does not load)
  -> pre-fill the step with the current values
  -> run the step
  -> validate the whole resulting config
  -> show a diff of the changed block only
  -> confirm, then rewrite only that block
```

Behaviors:

- Current values are the defaults. If the block is absent, the step starts empty.
- If the file already fails validation for an unrelated reason, report that and still allow the edit, but
  do not claim the file is valid at the end.
- If an edit makes another block invalid (for example renaming a table that a relationship uses), name
  the broken block and offer to jump to that step.

### 5.3 Final checklist

Printed at the end of both modes. Each line names what is missing and the command that fixes it:

```text
Skipped or incomplete:
  - subset      no seed rule        run: decoy init subset pipeline.yaml
  - secrets     no mask secret      run: decoy init secrets pipeline.yaml
  - checks      none configured     run: decoy init checks pipeline.yaml
Next: decoy validate pipeline.yaml
```

## 6. How a section is written

Requirement: changing one section changes only that block's lines. Everything else in the file,
including comments, key order and blank lines, is preserved byte for byte.

The CLI uses PyYAML today, which drops comments and reorders keys on write, so it cannot be used to
rewrite a user-edited file. Approaches:

| Approach | Preserves comments | New dependency | Risk |
|---|---|---|---|
| Round-trip YAML library (for example `ruamel.yaml`) | yes, including inside the block | yes | formatting churn on unrelated lines |
| Block splice: locate the top-level key's line range and replace only that text | yes, exactly | no | needs a careful parser for the range |
| Write `<file>.new` plus diff, user accepts | n/a | no | extra step for the user |

**OPEN.** Recommendation: block splice for section mode (it matches the "change only that part"
requirement exactly and adds no dependency), with an atomic temp-file-and-rename write and a re-parse
check that the untouched blocks are unchanged. Fall back to `<file>.new` plus diff if the top-level key
cannot be located safely (anchors, merge keys, flow-style top-level maps).

The splice finds a top-level key by its column-0 position, takes lines up to the next column-0 key or
end of file, and keeps trailing blank lines and comments that belong to the next block with that block.
A comment immediately above a key stays with that key.

Writes are atomic (temp file in the same directory, then rename) and never follow a symlink out of the
working tree.

## 7. Validation

The wizard builds a plain dict and validates with the engine's `PipelineConfig.model_validate`. It does
not re-implement any rule.

- After each step in project mode: validate the partial config where possible; on failure, re-ask only
  that step, showing the engine's message.
- Before writing: validate the whole config.
- After writing: run the same layers as `decoy validate` (config, compile, preflight) and show the
  grouped report. In section mode, always validate the whole file, not only the edited block.
- `--no-validate` skips the final run.

Skipped steps leave a `TODO` or `REVIEW` marker (section 8), and a config with unresolved required
items (for example no targets) is reported as incomplete, not valid.

## 8. Skip and resume

Skipping:

- Never invents a value. It leaves a marker that is a YAML comment on or above the affected line, in a
  fixed format such as `# TODO(decoy-init): set the source path`.
- `decoy validate` should report remaining markers as warnings, so `--fail-on-warning` and the CI check
  catch unfinished pipelines.

Resume:

- Project mode saves a draft after each completed step to a file beside the output (for example
  `.pipeline.yaml.init-draft.json`). `--resume` loads it.
- The draft holds answers, scan results (no source values), and the list of skipped steps. It never
  holds secrets or raw data.
- A successful write deletes the draft. **OPEN:** exact draft filename and location.

## 9. Non-interactive parity

Every prompt has a flag or an answers-file key, so the same flow can be scripted or tested.

- `--answers FILE` is a YAML or JSON mapping with one key per step, using the same field names as the
  YAML blocks. Missing required answers fail with a clear message.
- With no terminal attached (no TTY) and no `--answers`, the command refuses with exit code 1 and a
  message, rather than hanging.
- `--json` keeps its current meaning: no wizard, emit a JSON record of what was written.
- `-y` skips the overwrite confirmation only. It does not accept defaults for other prompts.

## 10. Project scaffold

Project mode may write more than `pipeline.yaml`:

| File | When |
|---|---|
| `pipeline.yaml` (or `-o` path) | always |
| `.decoy-ci.yaml` | `ci` step accepted |
| `.gitignore` entries for outputs and the token vault | tokenize on, or user accepts |
| `README` stub | **OPEN**, probably not |

It writes into the current directory. It does not create a project folder. **OPEN:** whether to offer one.

## 11. Architecture

Placement: a new subpackage `src/decoy/cli/wizard/`, with `cli/init.py` kept as the thin entry that
dispatches to it. `init.py` is already about 600 lines, so the wizard must not grow it.

```text
cli/wizard/
  steps/            one module per step (goal, sources, scan, columns, ...)
  state.py          WizardState: answers, scan results, skipped list; serialises to the draft
  splice.py         read a block's line range, replace only that block
  render.py         dict -> YAML text for one block, with REVIEW/TODO markers
  checklist.py      build the end-of-run list
  prompts.py        prompt helpers (single select, multi select, text, confirm)
```

Each step is an object with:

- `applies(state) -> bool`
- `defaults(state, existing) -> dict` (pre-fill from the existing file in section mode)
- `ask(state, prompts) -> dict` (the only part that touches the terminal)
- `to_block(answers) -> dict` (what goes into the YAML)
- `incomplete(state) -> list[str]` (feeds the checklist)

Rules:

- Library code does not know its callers. Inference stays in `decoy_engine`; the wizard calls it and
  does not reimplement detection or validation. This follows the CLI guide's boundary rule.
- Prompts come from the engine's config models and registries (strategies, providers, operators,
  orphan policies) so they stay in sync when the schema changes. No hand-copied lists.
- Terminal I/O is isolated in `prompts.py` so steps can be tested with scripted input.

Multi-select: Typer has no checkbox prompt and the CLI has no interactive-prompt dependency today.
V1 uses a numbered list ("enter 1,3"), which works in any terminal and needs no new dependency.
**OPEN:** adopt an interactive library later for arrow-key selection.

## 12. Terminology

User-facing text must not say "STORM". The roadmap is retiring the name in favour of pre-scan,
transform and post-scan stages. The wizard says "scan" and "suggested". The existing `decoy init`
help text and `# REVIEW:` comments are updated in the same change.

## 13. Exit codes

Only the six public codes are used. No new codes.

| Code | Wizard use |
|---|---|
| 0 | Wrote a valid result, or `--diff` completed |
| 1 | Usage error, bad answers file, cancelled, no TTY, config does not load |
| 2 | Final validation produced warnings and `--fail-on-warning` is set |
| 3 | I/O or engine failure while scanning or writing |
| 4 | not used |
| 5 | not used |

## 14. Testing

- **Per-step unit tests** with scripted prompt input and a fixture dict, asserting the block produced.
- **Splice tests:** a file with comments, blank lines, anchors and reordered blocks; editing each block
  leaves every other byte unchanged (compare before and after outside the block). Include a block at the
  end of file without a trailing newline.
- **Round-trip property:** the full flow with answers A equals the same sections run one at a time in
  section mode with the same answers.
- **Schema sync test:** every enum shown in a prompt (strategies, operators, orphan policies) is generated
  from the engine registry, and the test fails if a hand-written list appears.
- **No-secret test:** no answer, draft or output contains a secret value; only `env:` and `file:` references.
- **No-TTY test:** the command refuses cleanly.
- **Golden test:** the sample two-table pipeline (customers and orders with a relationship and a subset
  filter) validates against `PipelineConfig`.

## 15. Open decisions

1. Section mode spelling: `init <section>` or a separate verb (`edit`, `wizard`).
2. Section write method: block splice (recommended) or a round-trip YAML library.
3. Draft file name and location.
4. Whether project mode offers to create a project folder.
5. Whether to scaffold a README stub.
6. Whether `keys` subset seeds ever get a wizard prompt.
7. Whether to adopt an interactive prompt library after V1.
8. How the column step presents 50 or more columns beyond "ask only about flagged ones".

## 16. Phasing

1. **Phase 1.** Project mode for goal, sources, scan, columns, targets, secrets. Splice writer. Final
   validation and checklist. `--answers`. Replaces today's three-question flow.
2. **Phase 2.** Section mode for every step. Relationships and subset (filter and sample).
3. **Phase 3.** Checks and CI steps, `--resume`, tokenize vault prompts, project scaffold files.

Each phase ships with its tests (section 14) and leaves the previous behaviour working. Pre-GA = hard
delete: the old Q&A path is removed when Phase 1 lands, not kept behind a flag.

## 17. Sources and basis

- `docs/cli-reference.md`: current `decoy init` options and examples.
- `decoy_engine/config/` (`_pipeline.py`, `_tables.py`, `_relationships.py`, `_subset.py`,
  `_global_settings.py`): the blocks, enums and rules the steps map onto.
- `src/decoy/cli/init.py` and `src/decoy/cli/_init_inference.py`: existing prompts and inference.
- `docs/ci-contracts.md`: the `decoy-ci/v1` manifest for the `ci` step.
- Settled in conversation 2026-10-30: one flow with skippable stops, a skipped-items list at the end,
  multi-select goal, per-table scan prompt, and single-section editing that touches only that block.
