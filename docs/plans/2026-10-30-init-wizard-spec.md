# `decoy init` wizard: design spec

Status: DRAFT v2 for discussion, not committed scope. Created 2026-10-30; revised 2026-11-08 after a UX
review with the owner (section 18 records what was settled). Promotion into real scope is a planner
decision. Items marked **OPEN** are undecided.

Related: `docs/cli-reference.md` (`decoy init` today), `docs/ci-contracts.md` (the CI manifest the
wizard can scaffold), engine config models in `decoy_engine/config/`, and the engine's
`strategy_catalog()` (#400), which lists every strategy and its options for the wizard.

## 1. Summary

`decoy init` becomes the main way to build a pipeline. It walks the user through every part of a
pipeline with menus, from what the pipeline should do to where the output goes, and every feature the
engine supports can be reached from it: all source locations and formats, headerless and fixed-width
input, per-field strategy review, post-scan checks, quarantine and distribution checks.

The user can move back and forth freely, and nothing is written until the final review screen. The
same steps can be re-entered later to change one part of an existing pipeline, and only that part of
the YAML file is rewritten.

Two modes, one set of steps:

- **Project mode** (`decoy init`): walk every applicable step and write a whole pipeline.
- **Section mode** (`decoy init <section> <pipeline>`): run one step against an existing pipeline and
  rewrite only that block.

## 2. Goals and non-goals

Goals:

1. A new user gets from "I have a file" to a validated, runnable pipeline without reading the schema.
2. Every pipeline feature in the engine schema can be set from the wizard, either directly or from an
   "advanced" branch of a step.
3. The user can go back to any earlier step, change an answer, and come forward again without losing
   later answers.
4. Every step shows what it understood (parsed preview, before → after preview, summary) before moving on.
5. Any step can be skipped. Skipped work is listed at the end with the command that finishes it.
6. One part of an existing pipeline can be changed without touching the rest of the file, including
   the user's comments.
7. The wizard can never write a config the engine rejects.
8. Every prompt has a non-interactive equivalent, so the same result can be scripted.

Non-goals (V1):

- A full-screen terminal editor. The wizard is a sequence of prompts.
- Replacing hand-editing. The YAML stays the source of truth, and users are expected to edit it.
- Network access beyond the user's own S3/GCS sources, accounts or telemetry.

## 3. Command surface

```text
decoy init [INPUT_FILE]                       project mode (existing positional arg kept)
decoy init <section> <pipeline>               section mode
decoy init --resume                           continue an interrupted project-mode run
decoy init --answers FILE                     build without prompts from a saved answers file
decoy init --list-sections                    print section names
```

Existing flags stay: `-o/--output`, `--preset`, `-y/--yes`, `--json`, `-q`, `-v`.
New flags:

| Flag | Meaning |
|---|---|
| `--answers FILE` | Read answers from a YAML or JSON file instead of prompting (section 11). |
| `--save-answers FILE` | Also write the answers file at the end. Off unless asked (section 11). |
| `--no-samples` | Show value shapes (`a***@mail.com`) instead of real sample values. Samples are on by default. |
| `--skip SECTION[,..]` | Skip these sections in project mode. |
| `--only SECTION[,..]` | Run only these sections in project mode. |
| `--no-validate` | Skip the final validation (escape hatch; not recommended). |
| `--diff` | Section mode: print the diff and exit without writing. |

**OPEN:** whether section mode is spelled `init <section>` or a separate verb such as `edit`. `init`
usually means "create", so `decoy init subset pipeline.yaml` reads oddly as an edit.

Section names (fixed, tab-completed): `goal`, `sources`, `scan`, `fields`, `relationships`, `subset`,
`checks`, `quality`, `output`, `secrets`, `ci`.

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

### 4.3 Moving back and forth

- Every answer is kept in the wizard state, so going back never loses anything. When the user returns
  to a step, its previous answers are the defaults.
- Changing an earlier answer re-checks the later steps against it. Answers that are still valid are
  kept. Answers that no longer fit are not deleted; the step is marked `⚠` and the user is shown what
  changed when they reach it. Examples: removing a source marks Fields, Relationships and Output; turning
  off Subset in Goal removes the Subset step; changing a field from `hash` to `passthrough` removes the
  validators that only applied to it and marks Checks.
- The Review screen refuses to write while any step is marked `⚠`, and offers to jump to it.

### 4.4 Choosing from lists

- Short choices are numbered menus with the default first. Multi-select menus accept `1,3`, ranges
  `1-4`, and `a` for all.
- Long choices (strategies, faker providers, validators) are a tree of small menus, at most about eight
  entries per level (section 5.4.3).
- **Type-ahead.** At any menu, the user can instead type a name with Tab completion: `geo⇥` completes
  to `geo_generalize`, and a tree path such as `generalize/locations/geo_generalize` also works. File
  path prompts complete paths the same way. This is the fast path for experienced users.
- Menus and completions are generated from the engine (`strategy_catalog()`, the provider registry,
  the validator registry, config enums), so they can never offer something the engine rejects.

**OPEN:** Tab completion needs a prompt library. `prompt_toolkit` gives completion and arrow-key menus
on Linux, macOS and Windows; stdlib `readline` works only on Unix. Recommendation: adopt
`prompt_toolkit` (or `questionary`, which wraps it), and fall back to plain numbered menus when the
terminal does not support it.

### 4.5 Samples and previews

- Sample values are on by default. The data is local and the user already has access to it, and seeing
  real values is the quickest way to judge a suggestion. `--no-samples` shows shapes instead
  (`jane.doe@mail.com` → `a***.a**@mail.com`, `415-555-0142` → `999-999-9999`).
- After sources: a parsed preview of the first rows, so a wrong delimiter or layout is caught before
  scanning.
- In field review: a before → after preview of two or three values with the chosen strategy applied.
- Samples and previews never go into the draft, the answers file or the pipeline.

### 4.6 Writing

Nothing is written to the pipeline path until the user confirms on the Review screen. `q` and Ctrl-C
save a draft beside the output (section 10) and exit with code 1.

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
  2  Edit a section of an existing pipeline
  3  Start from a preset (minimal, hipaa, pci, gdpr, generate)
  4  Replay an answers file
```

A preset pre-fills the steps; the user still walks them and can change anything.

### 5.1 Goal

Multi-select. Any combination is allowed, including all four (`a`).

| Choice | Effect |
|---|---|
| Mask | Tables read from sources are mask-kind (`columns:`). Turns on Sources and Scan. |
| Generate | Tables built from scratch are generate-kind (`generate_columns:`). No source needed. |
| Subset | Turns on the Subset step. Subset reads Parquet sources only (see 5.6). |
| Tokenize | Adds `tokenize` to the strategy tree (it is hidden otherwise) and adds a vault path to Secrets. |

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
in the state in case the user turns the goal back on.

### 5.2 Sources

One source at a time, then "Add another source? [y/N]".

1. **Location:** local file, Amazon S3, Google Cloud Storage.
   - Local: path, with Tab completion. Missing files are reported, with an option to keep the path
     anyway (the file may not exist on this machine yet).
   - S3: bucket, key, region (optional), endpoint URL (advanced), credentials reference.
   - GCS: bucket, object, credentials reference.
   - Credentials are references only (`env:NAME` or `file:/PATH`), never values. For S3 and GCS the
     wizard offers "Test access by reading the first rows? [Y/n]".
2. **Format:** the menu offers only formats the engine reads from that location.
   - Local: CSV (comma), TSV (tab), delimited with another character, Parquet, fixed-width.
   - S3 and GCS: CSV, Parquet.
   - The suggested option is the one the file looks like: the extension, or a delimiter that appears
     the same number of times on every sampled line.
3. **Column names** (CSV, TSV and delimited):
   - First row of the file (`has_header: true`, the default).
   - A header file: one name per line, or one delimited line. The count must match the number of fields
     per record. The names are copied into `column_names` (the engine has no header-file reference).
   - Type them in: one name per prompt, or one line separated by commas.
4. **Fixed-width layout:**
   - A layout file in the engine's `FixedWidthLayout` shape (YAML or JSON), the same shape the platform
     stores.
   - Type it in, with a ruler over the first record. Each column asks for name, start, width and type
     (`str`, `int`, `float`); start defaults to where the previous column ended, so most columns need
     only a name and a width. Pad character and alignment are under "advanced". Then record width and
     whether the width must be exact.
   - **OPEN:** offer a suggested layout from runs of spaces in the first records.
5. **Parsed preview:** the first three records parsed with the chosen settings, as a table. "Does this
   look right? [Y/n]". `n` returns to format and column names.
6. **Table name:** defaults to the file stem.

Parquet sources skip 3 and 4: the column names come from the file.

### 5.3 Scan

Per source: which detectors to run (all built-in, or pick) and how many rows to sample (default
10,000). The scan reuses the engine profiler (`profile_columns`) and the existing inference in
`cli/_init_inference.py`. The result is a summary table: field, type, nulls, unique share, what was
detected, confidence. Nothing is written from this step; the results feed Fields, Relationships and
Checks.

### 5.4 Fields

#### 5.4.1 Review mode

Per table:

```text
How do you want to review the 8 fields?
  1  Every field, one at a time                     (default)
  2  Only flagged fields; choose one strategy for the rest
```

A field is **flagged** when the scan detected sensitive data in it or was unsure (medium or low
confidence).

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

Then it reviews the flagged fields one at a time. The Review screen lists the unflagged fields and the
strategy they received, so a choice made in bulk is still visible before writing. The engine's free-text
advisory still warns at validation time about a `passthrough` field that looks like free text.

#### 5.4.2 One field

```text
[6/8] zip   str · US ZIP (high)
  Suggested  truncate  keep the first 3 digits
  Preview    94110 → 941    10001 → 100
  Enter accept · r reject · o options · k keep as-is · d drop · b back · ? why
```

- **accept**: use the suggestion with its default options.
- **reject**: choose another strategy from the tree (5.4.3) or by typing its name.
- **options**: edit the strategy's options. Options come from `strategy_catalog()`: required ones are
  asked, optional ones show their default. The preview updates.
- **keep as-is**: `passthrough`.
- **drop**: remove the field from the output (a `drop_column` transform).
- **why**: what the scan found and why this strategy was suggested.

Every strategy whose catalog entry says `namespace_required` gets `namespace: <field name>` written
for it, without asking. Sharing a namespace across fields (so the same value masks the same way in two
fields) is under "advanced" in options.

#### 5.4.3 The strategy tree

Strategies are grouped by what they do to the data. No level has more than about eight entries, and
faker providers are folded into the tree, so the user picks "fake email address" rather than "faker"
and then a provider.

```text
Keep as-is ........................ passthrough
Remove
  ├ Blank out the value ........... redact
  └ Keep only part of it .......... truncate
Replace with realistic fakes
  ├ People ........................ full name · first name · last name · name · email · phone ·
  │                                 date of birth · person (combined) · name + email (combined)
  ├ Addresses ..................... full address · street · city · state · ZIP ·
  │                                 address (combined) · city/state/ZIP (combined)
  ├ Identifiers ................... SSN · MRN · NPI · member id · plan id · account number ·
  │                                 EIN · IBAN · card number (PAN) · CUSIP · UUID
  ├ Medical codes ................. ICD-10 · NDC
  ├ Other ......................... lorem text · random choice · random number · custom composite ·
  │                                 provider (combined)
  └ Pick from my own list ......... categorical
Scramble consistently (same input → same output, joins keep working)
  ├ One-way hash .................. hash
  ├ Keep the format ............... fpe
  └ Reversible token (vault) ...... tokenize        shown only when Tokenize is in the goal
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

The leaves are exactly the strategies with `offer_in_wizard=True` in `strategy_catalog()` plus the
provider registry's providers. Grouping is a CLI presentation concern and lives in the CLI, but a sync
test (section 15) fails if a strategy or provider is missing from the tree or appears twice, so the tree
cannot fall behind the engine.

Type-ahead works at every level: typing `email⇥` at the top jumps to the email provider.

#### 5.4.4 Generated tables

When Generate is in the goal, after the source tables: "Add a generated table? [y/N]". Then a table
name, a loop of column name → generator → options (from the engine's generate column types), and a row
count. Written as `tables[].generate_columns[]`.

### 5.5 Relationships

Shown only with two or more tables. Candidates come from the scan (matching key names and value
overlap). For each candidate, the user confirms, edits or rejects:

1. Parent table and column(s).
2. Child table(s) and column(s). Composite keys are supported (the config takes a list of columns).
3. Orphan policy (required, no default): `preserve`, `remap`, `warn`, `fail`, each with a plain
   sentence of explanation.
4. Optional namespace.

The user may add relationships by hand. Cardinality is implied by the parent and children lists, so the
wizard does not ask for it.

### 5.6 Subset

Per the engine schema, a seed rule is one of three modes:

| Mode | Prompts | V1 wizard |
|---|---|---|
| `filter` | table, then one or more `{column, op, value}` predicates (ANDed) | yes |
| `sample` | table, key columns, then `fraction` or `count` | yes |
| `keys` | table, key columns, explicit key list | no (edit the YAML) |

Operators: `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in`, `is_null`, `is_not_null`. Then an optional budget
(`max_total_rows`, `max_table_seed_multiple`) and an offer to show projected row counts with
`decoy subset --dry-run`. Edge directions and `allow_dangling` stay hand-edited.

Subset reads Parquet sources only. If a source is not Parquet, the step says so and offers to go back
to Sources (`g`) or to continue without subset.

### 5.7 Checks

What to check after the run, and what to do with rows that fail. Suggestions come from the field
choices.

1. **Post-scan integrity** (`post_scan.integrity`): check the output for leftover sensitive data, broken
   keys and policy violations. Report only. Default on.
2. **Validators:** a checklist of suggested validators, all pre-selected, plus "add another…".
   Suggestions:
   - `leak_check` on fields masked with faker, hash, fpe or redact.
   - `column_in_set` on low-cardinality `passthrough` fields, with the values the scan saw.
   - `luhn`, `npi`, `iban`, `vin` on fields that hold those identifiers after masking.
   - `fk_intact` and `no_orphan_children` when relationships are declared.
   "Add another" lists every validator in the registry and asks for its columns and parameters.
3. **Quarantine:** send failing rows to a file instead of stopping the run. Triggers are suggested from
   the pipeline: `validation_fail` when any validator is on, `format_error` when `date_shift` or
   `bucketize` is used, `mask_error` when `code_set` with `chapter_preserve` is used. Output path
   defaults to `out/<table>.quarantine.jsonl`.

### 5.8 Quality

How closely the output should match the source's distributions.

- **Post-validation** (`global_settings.post_validation`): check the output's invariants after masking.
  Default on.
- **Fidelity warning threshold** (`fidelity_warn_threshold`, default 0.80): only asked when the pipeline
  has generated statistical columns, which is what it applies to.
- **Category retention warning threshold** (`categorical_retention_warn_threshold`, default 0.80).
- **Full fidelity report:** this is the `decoy run --fidelity` option, not a pipeline setting, so a yes
  here adds `--fidelity` to the run command printed at the end.
- Advanced: `unconfigured_column_policy` (`warn` or `error`), the free-text advisory thresholds, and
  differential privacy (`dp`) for generated tables.

### 5.9 Output

One target per table.

1. Location: local file, S3, GCS (same prompts and credential references as Sources).
2. Format: the menu offers what the engine writes to that location (local: CSV, Parquet, fixed-width;
   S3/GCS: CSV, Parquet). Default follows the source.
3. Fixed-width output reuses the source layout by default.
4. Path: defaults to `out/<table>.masked.<ext>`.

CSV output is always comma-separated with a header row; the engine's targets have no dialect settings.
When the source used another delimiter or no header, the step says so (section 16).

### 5.10 Secrets

This step explains the two values, because they are easy to confuse:

| | Seed | Mask secret |
|---|---|---|
| What it is | A plain number, for example `42` | A private key of 32 or more random bytes |
| What it does | Makes random choices repeatable: the same seed, config and input give the same output | Keys the strategies that must not be reversible or guessable: hash, fpe, date_shift, tokenize, and any `deterministic` or `vault` field |
| Who may see it | Anyone. It is written in the pipeline file | Only the people allowed to run the pipeline. The pipeline holds only a reference to it |
| If it leaks | Nothing is exposed | Someone with the secret and the masked output can test guesses, for example hash every possible SSN and match the results |
| Keep it the same when | You want reproducible runs | You want the same value masked the same way across runs and pipelines (joins across datasets) |

Prompts:

1. Seed (default 42).
2. Mask secret, only asked when a keyed strategy is used:
   - Store a reference in the pipeline (`global_settings.mask_secret_ref`): environment variable
     (default `env:DECOY_MASK_SECRET`) or file (`file:/PATH`). Default.
   - Supply it at run time instead (`decoy run --mask-secret …`), which keeps the pipeline file free of
     environment details.
   Setting both is a usage error in `decoy run`, so the wizard writes one or the other, and the printed
   run command matches.
   The wizard checks whether the variable or file exists now and warns if not. It never reads, prints
   or stores the value.
3. Tokenize vault path, when Tokenize is in the goal, with a reminder that the vault is cleartext at rest
   and an offer to add it to `.gitignore`.
4. When the pipeline has generated tables: a note that portable generation uses the separate
   `--master-key` / `--key-label` run options, which are independent of the mask secret
   (`decoy explain keys`).

### 5.11 Review

```text
  Enter write · y view YAML · g go to a step · a save answers file · q save draft & quit
```

1. A summary: each source → target, each field and its strategy (bulk-assigned fields marked), checks,
   quarantine, quality, secret reference.
2. `y` shows the full YAML before writing.
3. On write: validate (config, compile, preflight), write `pipeline.yaml`, print the checklist of
   skipped or incomplete items, and print the run command.
4. `a` (or `--save-answers`) also writes the answers file. Off unless asked.
5. Offer to write `.decoy-ci.yaml` (schema `decoy-ci/v1`) with this pipeline registered. Default no.

## 6. Walkthrough

A single-table masking pipeline. The source `customers.txt` is pipe-delimited with no header row; the
column names are in `customers_header.txt`. Values and previews are illustrative.

```text
$ decoy init

decoy init  ·  build a pipeline step by step
Keys: Enter default · b back · f forward · g go to · s skip · ? help · q save & quit

── 0 · Start ─────────────────────────────────────────────────────────
  1  New pipeline                                   (default)
  2  Edit a section of an existing pipeline
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
Path: cust⇥  →  customers.txt
  ✓ found  ·  4.2 MB  ·  38,214 lines

What format is it?
  1  CSV (comma)
  2  TSV (tab)
  3  Delimited, other character     ← suggested: "|" appears 7× on every sampled line
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
Which detectors should run?
  1  All built-in detectors      (default)
  2  Pick detectors
>
Rows to sample [10000]:

Scanning customers  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  10,000 rows · 1.4s

  field      type  nulls  unique     detected             confidence
  cust_id    int    0%    100%       unique key           high
  full_name  str    0%     97%       person name          high
  email      str    1%     99%       email                high
  phone      str    3%     98%       US phone             high
  dob        date   0%     71%       date                 high
  zip        str    0%     12%       US ZIP               high
  plan_tier  str    0%    3 values   —                    —
  notes      str   41%     95%       free text (names?)   medium

── 4/9 Fields · customers ────────────────────────────────────────────
How do you want to review the 8 fields?
  1  Every field, one at a time                     (default)
  2  Only flagged fields; choose one strategy for the rest
> 1

[1/8] cust_id   int · unique key (high)
  Suggested  hash   same id always becomes the same value; joins keep working
  Preview    10482 → 9f2c41e07b    10483 → 03d7aa5c18
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
  Suggested  date_shift  ±365 days; the same date always shifts the same way
  Preview    1984-03-12 → 1984-09-27
> o
  min_days [-365]: -30
  max_days [365]: 30
  date_format [%Y-%m-%d, detected]:
  Preview    1984-03-12 → 1984-03-29
  ✓ date_shift ±30 days

[6/8] zip   str · US ZIP (high)
  Suggested  truncate  keep the first 3 digits
  Preview    94110 → 941
> r
  Choose a strategy (or type a name, Tab completes):
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
  k_threshold [20000]:
  Preview    94110 → 941    05753 → VT   (sparse areas fall back to the next level)
  ✓ geo_generalize · zip3 → state → suppress

  (an experienced user types instead:  > geo⇥  →  geo_generalize)

[7/8] plan_tier   str · 3 values: basic, plus, pro · not flagged
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
  ✓ 1  leak_check     full_name, email, phone   no source value survives (≤ 2% identical)
  ✓ 2  column_in_set  plan_tier                 output stays within {basic, plus, pro}
    3  Add another check…
>

Send failing rows to a quarantine file instead of stopping the run? [Y/n]
  Triggers (suggested from your choices):
  ✓ 1  validation_fail   a row fails one of the checks above
  ✓ 2  format_error      a dob value can't be parsed as a date
  >
  Quarantine file [out/customers.quarantine.jsonl]:

── 6/9 Quality ───────────────────────────────────────────────────────
Check the output's invariants after masking (post-validation)? [Y/n]
Warn when category retention drops below [0.80]:
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

hash, date_shift and the fake-value fields are keyed. They need a mask
secret: a private key of 32+ random bytes that only people allowed to run
this pipeline should have. The pipeline stores where to find it, never
the secret itself.
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

  Checks      post-scan integrity · leak_check (3 fields) · column_in_set (plan_tier)
  Quarantine  validation_fail, format_error → out/customers.quarantine.jsonl
  Quality     post-validation · category retention warning at 0.80 · fidelity report on run
  Secrets     seed 42 · mask secret from env:DECOY_MASK_SECRET

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
  categorical_retention_warn_threshold: 0.8

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
    columns: {customers: [full_name, email, phone]}
    params: {max_identical_ratio: 0.02}
  - name: column_in_set
    columns: {customers: [plan_tier]}
    params: {allowed_values: [basic, plus, pro]}

quarantine:
  enabled: true
  output_path: out/customers.quarantine.jsonl
  triggers: [validation_fail, format_error]

targets:
  customers:
    type: file
    format: csv
    path: 'out/customers.masked.csv'
```

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
[1/7] cust_id   int · unique key (high)
  …
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
  Record width [45]:
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
  Credentials reference [env:AWS_PROFILE]:
  Test access by reading the first rows? [Y/n]
  ✓ read 3 rows · Parquet · 8 columns
```

## 7. Section mode

```text
decoy init checks pipeline.yaml
  -> load and validate the existing file (refuse if it does not load)
  -> pre-fill the step with the current values
  -> run the step (back and forth work within it)
  -> validate the whole resulting config
  -> show a diff of the changed block only
  -> confirm, then rewrite only that block
```

- Current values are the defaults. If the block is absent, the step starts empty.
- If the file already fails validation for an unrelated reason, report that and still allow the edit,
  but do not claim the file is valid at the end.
- If an edit makes another block invalid (for example renaming a table that a relationship uses), name
  the broken block and offer to run that section next.

End-of-run checklist (both modes):

```text
Skipped or incomplete:
  - subset      no seed rule        run: decoy init subset pipeline.yaml
  - checks      none configured     run: decoy init checks pipeline.yaml
Next: decoy validate config pipeline.yaml
```

## 8. How a section is written

Changing one section changes only that block's lines. Everything else in the file, including comments,
key order and blank lines, is preserved byte for byte.

The CLI uses PyYAML today, which drops comments and reorders keys on write. Approaches:

| Approach | Preserves comments | New dependency | Risk |
|---|---|---|---|
| Round-trip YAML library (for example `ruamel.yaml`) | yes, including inside the block | yes | formatting churn on unrelated lines |
| Block splice: replace only the top-level key's line range | yes, exactly | no | needs a careful range parser |
| Write `<file>.new` plus diff, user accepts | n/a | no | extra step for the user |

**OPEN.** Recommendation: block splice, with an atomic temp-file-and-rename write and a re-parse check
that the untouched blocks are unchanged. Fall back to `<file>.new` plus diff when the top-level key
cannot be located safely (anchors, merge keys, flow-style top-level maps).

The splice finds a top-level key at column 0 and takes lines up to the next column-0 key or end of
file. A comment immediately above a key stays with that key. Writes never follow a symlink out of the
working tree.

`global_settings` is shared by Quality and Secrets, so those two sections splice individual keys inside
that block rather than the whole block.

## 9. Validation

The wizard builds a plain dict and validates with the engine's `PipelineConfig.model_validate`. It does
not re-implement any rule.

- After each step: validate the partial config where possible; on failure, re-ask only that step and
  show the engine's message.
- Before writing: validate the whole config.
- After writing: run the same layers as `decoy validate` (config, compile, preflight) and show the
  grouped report.
- `--no-validate` skips the final run.

## 10. Skip, drafts and resume

- Skipping never invents a value. It leaves a marker comment such as
  `# TODO(decoy-init): set the source path`, and `decoy validate` reports remaining markers as warnings.
- `q`, Ctrl-C and errors save a draft beside the output (for example `.pipeline.yaml.init-draft.json`).
  `--resume` loads it and opens the step the user was on. **OPEN:** exact draft name and location.
- The draft holds answers, scan summaries (types, detectors, counts) and step status. It never holds
  sample values, secrets or raw data.
- A successful write deletes the draft.

## 11. Non-interactive parity and answers files

- Every prompt has an answers-file key, using the same names as the YAML blocks plus wizard-only choices
  (review mode, bulk strategy). `--answers FILE` builds without prompts; missing required answers fail
  with a message naming the key.
- The answers file is written only when asked: `--save-answers FILE`, or `a` on the Review screen.
- With no terminal attached and no `--answers`, the command refuses with exit code 1 rather than hang.
- `--json` keeps its current meaning: no wizard, emit a JSON record of what was written.
- `-y` skips the overwrite confirmation only. It does not accept defaults for other prompts.

## 12. Architecture

A new subpackage `src/decoy/cli/wizard/`; `cli/init.py` stays the thin entry that dispatches to it
(`init.py` is already about 650 lines and must not grow).

```text
cli/wizard/
  steps/            one module per step
  state.py          WizardState: answers, scan summaries, step status; serialises to the draft
  nav.py            back / forward / go-to, and marking later steps when an answer changes
  tree.py           the strategy tree (section 5.4.3) built from strategy_catalog() and the providers
  preview.py        sample values, shapes (--no-samples) and before -> after previews
  splice.py         read a block's line range, replace only that block
  render.py         dict -> YAML text for one block, with REVIEW / TODO markers
  checklist.py      the end-of-run list
  prompts.py        menus, multi-select, text with Tab completion, confirm
```

Each step is an object with:

- `applies(state) -> bool`
- `defaults(state, existing) -> dict`
- `ask(state, prompts) -> dict` (the only part that touches the terminal)
- `to_block(answers) -> dict`
- `depends_on(state) -> set[str]` (which earlier answers it reads, for `⚠` marking)
- `incomplete(state) -> list[str]`

Rules:

- Library code does not know its callers. Detection, inference inputs, strategy metadata and validation
  stay in `decoy_engine`; the wizard calls them.
- All menus come from the engine's registries and config enums. The grouping in `tree.py` is the only
  hand-written list, and a test keeps it in step with the engine.
- Terminal I/O is isolated in `prompts.py` so steps are tested with scripted input.

## 13. Terminology

User-facing text does not say "STORM"; it says "scan" and "suggested". Strategy names are shown with a
plain description, and faker providers are shown by what they produce ("fake email"), with the
provider name available under `?`.

## 14. Exit codes

Only the six public codes are used. No new codes.

| Code | Wizard use |
|---|---|
| 0 | Wrote a valid result, or `--diff` completed |
| 1 | Usage error, bad answers file, cancelled, no terminal, config does not load |
| 2 | Final validation produced warnings and `--fail-on-warning` is set |
| 3 | I/O or engine failure while scanning, previewing or writing |

## 15. Testing

- **Per-step tests** with scripted input and a fixture state, asserting the block produced.
- **Navigation tests:** back and forward keep answers; changing a source marks Fields, Relationships and
  Output; turning off a goal removes its step and turning it on again restores its answers; Review
  refuses to write while a step is marked.
- **Tree sync test:** every `offer_in_wizard` strategy and every provider appears exactly once in the
  tree, and nothing in the tree is unknown to the engine.
- **Splice tests:** a file with comments, blank lines, anchors and reordered blocks; editing each block
  leaves every other byte unchanged. Include a block at end of file without a trailing newline.
- **Round-trip property:** the full flow with answers A equals the same sections run one at a time in
  section mode with the same answers.
- **Privacy tests:** no draft, answers file or pipeline contains a sample value or secret value; only
  `env:` and `file:` references. `--no-samples` output contains no real values.
- **No-terminal test:** the command refuses cleanly.
- **Golden tests:** the walkthrough in section 6, and a two-table pipeline with a relationship and a
  subset filter, validate against `PipelineConfig`.

## 16. Engine gaps

1. **Previews.** The CLI needs a supported way to apply one column strategy to a few values. Either a
   small public engine function, or the wizard runs the whole draft pipeline in memory on a handful of
   rows. **OPEN.**
2. **Header file reference.** Sources cannot point at a header file, so names are copied into
   `column_names`. Editing the header file later does not update the pipeline.
3. **CSV target dialect.** CSV targets have no delimiter or header settings, so a pipe-delimited or
   headerless source becomes comma-delimited output with a header.
4. **Delimiter and layout suggestion.** Suggesting a delimiter, and a fixed-width layout from runs of
   spaces, is new logic that belongs next to the CLI's CSV reader.
5. **Fidelity report** is a `decoy run` option, not a pipeline setting. The wizard adds it to the run
   command; it cannot store it in the pipeline.

## 17. Phasing

1. **Phase 1.** Project mode: Start, Goal (all combinations), Sources (all locations and formats, header
   options, fixed-width), Scan, Fields (both review modes, the strategy tree, previews), Checks,
   Quality, Output, Secrets, Review. Back, forward and go-to. Drafts and `--resume`. Final validation and
   checklist. Replaces today's three-question flow.
2. **Phase 2.** Section mode with the splice writer. Relationships, Subset (filter and sample), generated
   tables. `--answers` and `--save-answers`.
3. **Phase 3.** Tab completion and arrow-key menus (if the prompt library is adopted), layout
   suggestion, the CI manifest, tokenize vault prompts.

Each phase ships with its tests and leaves the previous behaviour working. Pre-GA = hard delete: the old
Q&A path is removed when Phase 1 lands, not kept behind a flag.

## 18. Decisions

Settled 2026-10-30: one flow with skippable stops, a skipped-items list at the end, multi-select goal,
per-table scan prompt, single-section editing that touches only that block.

Settled 2026-11-08 (UX review):

1. Goal accepts any combination, including all four.
2. The user can move back and forth through the steps (back, forward, go to) without losing answers.
3. Field review defaults to every field one at a time. "Only flagged fields" is an option; with it, one
   strategy is chosen for the unflagged fields, from a short list with `passthrough` first, then
   `redact`, `hash`, then the full tree.
4. Sample values are shown by default; `--no-samples` turns them off.
5. Strategies are presented as a tree grouped by what they do, with no long flat lists. Experienced
   users can type a name with Tab completion instead.
6. Checks and Quality are two separate steps.
7. The answers file is written only when asked.

## 19. Open decisions

1. Section mode spelling: `init <section>` or a separate verb (`edit`).
2. Section write method: block splice (recommended) or a round-trip YAML library.
3. Prompt library for Tab completion and arrow keys: `prompt_toolkit` / `questionary` (recommended) or
   numbered menus only.
4. How previews are computed (section 16, item 1).
5. Draft file name and location.
6. Whether to suggest a fixed-width layout from the data.
7. Whether `keys` subset seeds ever get a wizard prompt.

## 20. Sources and basis

- `docs/cli-reference.md`: current `decoy init` options.
- `decoy_engine/config/` (`_pipeline.py`, `_sources.py`, `_fixed_width.py`, `_tables.py`,
  `_relationships.py`, `_subset.py`, `_post_scan.py`, `_validators.py`, `_global_settings.py`,
  `_targets.py`): the blocks, enums and rules the steps map onto.
- `decoy_engine.strategy_catalog()` and the provider registry: the strategy tree's leaves and options.
- `src/decoy/cli/init.py`, `src/decoy/cli/_init_inference.py`: existing prompts and inference.
- `decoy explain keys`: seed, mask secret and master key semantics.
- Interaction patterns: guided scaffolders such as `npm init`, `cargo generate` and `dbt init` (prompt
  per field, defaults in brackets, review before write); `prompt_toolkit` for completion.
