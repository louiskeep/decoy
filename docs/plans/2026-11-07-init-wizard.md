Status: plan

# INIT-WIZARD: `decoy init` as a review wizard (CLI roadmap row 32b)

Owner: Cam. Author: claudeworkerbee (Opus). Date: 2026-11-07. Scope: CLI V1, two small engine parts.

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`,
`development-loop.md`, `profiles/local-operations.md`, `feature-dev.md`, `api-and-compatibility.md`,
`cross-cutting-concerns.md`, `reuse-first.md`, `architecture.md`, `testing.md`. Also the plan contract
(`30_Resources/Decoy-Plan-Contract-and-Defect-Catalog.md`), `LOCAL-BUILDER-BRIEF.md`,
`WORKER-STANDARDS.md`, `V1-BAR-WORKER-SECTION.md` and the owner decisions
"SCAN-ML and INIT-WIZARD (2026-11-06)" in `10_Projects/decoy/OWNER-DECISIONS-2026-10-30.md`.

Risk: R2. The plan changes a public CLI command, adds a file format (the answers file), adds public
engine API, edits a user's existing pipeline YAML in place, and its output must stay value-free.
Nothing is destructive beyond an atomic replace of a file the user named, which the wizard shows and
confirms first. Approver: Cam.

Bases: CLI `origin/main` `be5ba11`, engine `origin/main` `3c01f877` (both fetched 2026-11-07).
Inputs: CLI `docs/ROADMAP.md` rows 32a, 32b, 63a; the draft spec
`docs/plans/2026-10-30-init-wizard-spec.md` (kept as input, not deleted); the SCAN-MULTI plan
(engine branch `plan/scan-multi`, `docs/plans/2026-11-05-scan-multi-fk-discovery.md`); the companion
SCAN-ML plan (engine branch `plan/scan-ml`, `docs/plans/2026-11-07-scan-ml.md`), which cites this
plan for the suggestion and decision shapes.

## 1. FRAME

### Problem

`decoy init FILE` scans one file and writes a YAML whose suggestions are live with a `# REVIEW:`
comment above each. Nobody is asked whether a suggestion is right. The owner wants `decoy init` to
become a V1 wizard: scan the sources with the chosen detectors, build the pipeline YAML, then walk the
user section by section and column by column so each suggestion is confirmed or rejected. After a run,
the post-scan findings are reviewed the same way. CI and scripts must reach the same YAML without any
prompt.

SCAN-MULTI S3 already moves the scan and the starter YAML into the engine (`scan_sources`,
`starter_config`) and gives the CLI one YAML renderer (`cli/_scaffold_yaml.py`, guard
G-ONE-EMITTER). SCAN-ML adds the classifier and NER detectors and their config fields. This plan adds
the review step between "the engine suggested" and "the file is written", and the review of post-scan
findings against an existing file.

### Guarantee (what V1 promises)

1. **Every suggestion is reviewable, one column at a time.** For each table (a section), the wizard
   shows a summary, then walks each column with a suggestion or a note. The user answers each with
   one verdict from one fixed vocabulary (section 4.2). A verdict changes only that column.
2. **Nothing an ML model suggests is applied without a confirm.** A classifier or NER suggestion
   changes a column's strategy only on a `confirm` verdict, typed by the user or written in an answers
   file. A skipped column keeps exactly what `starter_config` wrote for it (the regex suggestion, or
   `redact` when there is none, owner answer Q9 of SCAN-MULTI), with its REVIEW note.
3. **Same answers, same file.** An interactive session saved with `--save-answers A` and a
   non-interactive run with `--answers A` on the same sources and engine produce byte-identical YAML.
   A non-interactive run with no answers equals an interactive session where every item was skipped.
4. **No prompt without a terminal.** When stdin or stdout is not a TTY, or `--no-input`, `--json`, `-q`
   or `--answers` is given, the wizard never prompts. A required input that no flag or answer supplies
   is a usage error (exit 1) naming the flag, before any source is read.
5. **One writer per kind of write.** A new pipeline YAML is written only through
   `_scaffold_yaml.render` (SCAN-MULTI G-ONE-EMITTER, extended to the wizard). An existing pipeline
   YAML is edited only through `cli/wizard/_yaml_edit.py`, which changes only the bytes of the edited
   entries and leaves every other byte, comment included, unchanged. Both write through
   `src/decoy/_atomic.py`.
6. **Value-free.** Prompts, summaries, REVIEW notes, the answers file, `--json`, errors and logs carry
   names (tables, columns, detectors, strategies, models, file names; owner 2026-11-06 "names are
   structure") and counts, never a cell value or a secret.
7. **The wizard never writes a config the engine refuses.** Before any write the result passes the
   pre-run gate's config and compile layers (`decoy.cli.gate`); after the write the full gate runs
   (config, compile, preflight) and its report is shown with `gate_exit_code`.

### Non-goals (V1)

- Relationship, subset, checks and CI steps of the draft spec (sections 4.5, 4.6, 4.9, 4.10). The
  YAML keeps SCAN-MULTI's commented relationship template. Follow-up row INIT-WIZARD-2.
- Section mode of the draft spec for every block (`decoy init <section> <pipeline>`), drafts and
  `--resume`, project scaffold files. Only the post-scan findings review edits an existing file in V1.
- Arrow-key selection or any new prompt dependency (section 2).
- A `decoy validate` warning for unreviewed REVIEW notes (spec section 8). Follow-up row; it edits the
  gate and is not needed for the owner's ask.
- Downloading models. The wizard never touches the network; it names the SCAN-ML setup command when
  NER is chosen but not installed.
- Writing a mask secret. The wizard asks only for a reference (`env:` or `file:`), as today.

### Failure modes

| Case | V1 behavior |
|---|---|
| No TTY and a required input is missing (sources, a CSV header flag) | Exit 1 before any read, naming the missing flag. No prompt, no hang. |
| `--answers` file does not parse, has an unknown key, wrong schema tag, or names a table or column that is not in the scan | Exit 1 before any write. The error names the key path and the code (`init.answers_invalid`, `init.answers_unknown_column`) through the value-free error converter; it never echoes a submitted value. A column name is a name and may be shown. |
| User presses Ctrl-C or sends EOF at a prompt | Exit 1 (`cancelled`), nothing written, no answers file written. |
| User answers `q` | Review stops; every remaining item counts as `skip`; the wizard goes on to the write step. |
| A source fails to read or scan | Exit 3 naming the table and the exception class only (SCAN-MULTI S3a behavior). Nothing written. |
| An `edit` verdict names a strategy the engine does not know, or omits a required option | Re-asked at the prompt with the engine's value-free message. In an answers file: exit 1 naming the column path. |
| The reviewed config fails the gate's config or compile layer | A builder bug: exit 3, nothing written, the gate findings shown. Acceptance AT-W7 proves the review cannot produce one for any verdict sequence over the fixtures. |
| Output file exists | Same as today: refuse without `--yes` in non-interactive modes; ask in a terminal. `--yes` only answers this question. |
| NER chosen but spaCy or its model is not installed | The detector step says so, names the SCAN-ML install command, and offers to continue without NER. Non-interactive: exit 1 naming the command. |
| Post-scan review: the pipeline YAML changed on disk after it was read | Refused before replace (`init.yaml_changed`), nothing written. |
| Post-scan review: the entry to edit uses an anchor, alias, merge key or flow style, or the key is duplicated | Refused for that entry (`init.yaml_edit_unsupported`, naming the column path); the replacement entry is printed for a hand edit. Other entries still apply only if the user confirms the partial edit. |
| Post-scan review edits a key column of a declared relationship | The `edit` and `confirm` verdicts keep the column's strategy keyed and its namespace; a strategy that drops the namespace is refused with the compiler's own `namespace_ambiguity` code. |
| Post-scan review: no run result found, or the result has no post-scan findings | Exit 1 with a hint to run `decoy run` with post-scan on. |

## 2. Established solutions

Searches run on 2026-11-07: web searches for wizard prompt libraries and answers-file parity
(questionary, click prompts, dbt init), YAML editing with PyYAML node marks and ruamel.yaml, and the
`git add --patch` prompt; plus the CLI and engine code at the bases above.

- **Per-item review vocabulary: `git add --patch`.** Git reviews one hunk at a time with single-key
  verdicts: `y` stage, `n` skip, `q` quit, `a` this and all later hunks in the file, `d` none of the
  later hunks, `?` help (git-add documentation, Interactive Mode; `add-patch.c`). Section 4.2 adopts the
  same keys for columns, with a table as the "file". Users of git already know them.
- **Scaffold, then review: `dbt init`.** dbt reads a `profile_template.yml` with `fixed` values and
  `prompts`, and has `--skip-profile-setup` and `--profile` to run without prompts
  (https://docs.getdbt.com/reference/commands/init). The CLI scaffolder already cites dbt init and
  cookiecutter (`src/decoy/cli/init.py:13`). This plan follows the same split: the engine builds the
  starter (`starter_config`), the CLI asks, and every prompt has a flag or answers-file key.
- **No prompt without a terminal.** A prompt in a non-interactive run can hang a script (Stack
  Overflow thread on click prompting; click's own `auto_envvar_prefix` is the documented workaround).
  Guarantee 4 follows the common CLI convention of refusing to prompt off a TTY and requiring flags
  instead (as `terraform -input=false` and `gh` do).
- **Prompt library.** Surveyed: Typer and click `prompt`/`confirm` (already used, `init.py:585`,
  `init.py:462`), `rich.prompt` (Rich is already a dependency), questionary and InquirerPy (arrow keys,
  both pull in `prompt_toolkit`, not in the lock). No new dependency: the wizard uses click's prompts
  through one `Prompter` interface, with numbered lists for multi-select as the draft spec chose
  (spec section 11). questionary can replace the terminal implementation later behind the same
  interface without touching any step.
- **Answers as data.** questionary's `form` and dict-driven `prompt` return answers keyed by name,
  which maps directly onto a file. The answers file here is a strict pydantic model with
  `extra="forbid"` and `hide_input_in_errors=True`, the same posture as the engine config models
  (`decoy_engine/config/_post_scan.py`).
- **Editing an existing YAML.** ruamel.yaml round-trips comments and key order
  (https://yaml.dev/doc/ruamel.yaml/overview) but is a new runtime dependency and still reflows some
  formatting. PyYAML, already in the lock, records `start_mark` and `end_mark` on every composed node
  (`yaml/composer.py`), so the exact byte span of one column entry is known from the parser itself, not
  from a hand-written line scanner. The editor composes the file, takes the span of each entry to
  change, replaces only those bytes, re-parses, and checks that the parsed result differs from the
  original only at the intended paths. This keeps every other byte, needs no dependency, and refuses
  the shapes whose span is not a plain block mapping (anchors, aliases, merge keys, flow style). It
  replaces the draft spec's column-0 "block splice" (spec section 6), which needed a custom range
  parser.
- **Atomic write.** `src/decoy/_atomic.py` (`write_local_target`), the CLI's one durable-replace
  writer, guarded by `tests/sentry/test_atomic_writer.py`. Today `init.py` writes with a plain
  `write_text` (`init.py:478`, `init.py:559`, `init.py:575`, `init.py:606`).

No custom algorithm remains. The custom code is the review loop and the answers model, both thin.

## 3. Design notes

- **Library code does not know its callers.** The engine decides what a verdict does to a config
  (`apply_review`, `finding_edits`); the CLI asks the questions, reads answers files and writes bytes.
  The platform's later review UI can call the same two engine functions. This is the CLI boundary rule
  (CLI `CLAUDE.md`: data behavior goes to the engine).
- **Principles applied.** Single responsibility: prompts, answers, review loop, YAML editing and the
  command body are separate modules, each with one reason to change. Open/closed: a new section is
  one `Section` descriptor in a tuple; the flow loop does not change. Dependency inversion: steps
  depend on the `Prompter` protocol, not on click, so tests drive them with a scripted prompter and
  questionary could replace click later. Deep module: `_yaml_edit.apply_edits(text, edits)` hides
  composing, spans and the structural check behind one call.
- **House style.** Typed context objects (`WizardContext` holds the output state, the prompter, the
  scan and the decisions) instead of long parameter lists; no flag arguments that switch behavior (the
  interactive and answers-file paths are two `Prompter` implementations, not an `interactive: bool`).
- **One place per fact.** The verdict vocabulary is one enum in the engine (`ReviewVerdict`); the CLI
  key map (`y` to `confirm`, and so on) is one table in `_prompts.py`; the strategy list shown at an
  `edit` prompt comes from the engine strategy registry, never a hand list. Detector names and the
  pre-scan and post-scan config fields come from SCAN-ML's config models.
- **Choke points.** See the class table rows 1, 4 and 6 and section 7 (G-ONE-EMITTER, G-ONE-EDITOR,
  the prompt-boundary sentry).

## 4. Behavior

### 4.1 Command surface

```text
decoy init [FILES...] [--has-header|--no-header] [--column-names ...]   project mode (wizard)
decoy init --review-findings PIPELINE [--result FILE]                   post-scan findings review
decoy init --preset NAME                                                template path (unchanged)
```

New flags: `--answers FILE`, `--save-answers FILE`, `--no-input`, `--review-findings PIPELINE`,
`--result FILE`. Kept: `-o/--output`, `--preset`, `-y/--yes`, `--json`, `-q`, `-v`, and the header
flags SCAN-MULTI S3a.1 adds. `--json` and `-q` imply `--no-input`. Section mode spelling is owner
question Q1 (section 9); `--review-findings` is the recommended form and the only edit entry in V1.

Bare `decoy init` in a terminal asks first: "Start from data files, or from a template?" The template
answer runs today's preset path unchanged. Off a TTY, bare `decoy init` keeps today's behavior (the
`minimal` preset, `init.py:556`).

### 4.2 The review vocabulary (shared with SCAN-ML)

One prompt per item, the `git add --patch` keys:

| Key | Verdict | Effect on the column |
|---|---|---|
| `y` | `confirm` | Apply this suggestion's entry (strategy, provider, options, namespace). |
| `n` | `reject` | Use the no-suggestion entry: `redact` with a note that the suggestion was rejected. |
| `e` | `edit` | Pick a strategy from the engine registry list and answer its required options. |
| `s` | `skip` | Keep what `starter_config` wrote, with its REVIEW note. |
| `a` | `confirm` for this item and every later item in the table that has a suggestion | as `y` for each |
| `d` | `skip` for this item and every later item in the table | as `s` for each |
| `q` | `skip` for every remaining item in every table | as `s` |
| `?` | help | prints the table above |

A column with several suggestions (for example regex says `email`, the classifier says
`person_name`) shows them numbered; `y` confirms the first, `y2` the second. The verdict records which
suggestion was confirmed (`source`).

Post-scan findings use the same keys and verdicts (section 4.5). For a finding, `confirm` means "this
is real PII: mask it" and `reject` means "false positive: dismiss it".

### 4.3 Project mode flow

```text
decoy init customers.csv orders.parquet --has-header
  1 sources      file list and header flags (prompted only for what flags did not give)
  2 detectors    pre-scan: regex (always), classifier, NER; post-scan: on/off, detectors,
                 NER findings warn or fail                                [part W2, needs SCAN-ML]
  3 scan         scan_sources over every table with the pre-scan detectors; one progress line per table
  4 columns      per table: summary, then column-by-column review (4.2)
  5 targets      default per SCAN-MULTI (<stem>.masked.<ext>); confirm or change the directory
  6 secrets      mask_secret_ref only when a keyed strategy was chosen (env: or file: reference)
  7 write        apply_review -> config and compile layers -> render -> atomic write -> full gate
  -> summary: counts of confirmed, rejected, edited, skipped per table; the next command
```

The column summary is a Rich table with one row per column: name, suggested type, source
(`regex`, `classifier`, `ner`), band or confidence bucket, the entry that skip keeps, and the
suggested entry. Values never appear (the scan record holds none: SCAN-MULTI `ScanSetCore`).

Before the summary, the wizard offers per table: review each column, confirm every suggestion (`a`),
or skip the table (`d`). This answers the draft spec's open question 8 (tables with 50 or more
columns) without a separate mode.

### 4.4 Non-interactive path

- Inputs come from flags (sources, header flags, `-o`), then from `--answers`, and nothing is prompted
  (Guarantee 4).
- The answers file, schema tag `decoy-init-answers/v1`, YAML or JSON:

  ```yaml
  schema: decoy-init-answers/v1
  detectors:                       # part W2; field names are SCAN-ML's config fields
    pre_scan: [regex, classifier]
    post_scan: {detectors: [regex, ner], ner_findings: warn}
  tables:
    customers:
      email: confirm               # confirm the first suggestion
      full_name: {verdict: confirm, source: classifier}
      notes: reject
      region: {verdict: edit, strategy: passthrough}
  unlisted: skip                   # skip (default) or confirm
  targets_dir: out/                # optional
  mask_secret_ref: env:DECOY_MASK_SECRET   # optional
  ```

- `unlisted: confirm` is the explicit "accept every suggestion" answer for CI. It is a user
  confirmation written in a file the user controls, so owner decision "the user confirms" holds.
- `--save-answers FILE` writes the decisions the session made in this exact shape (every reviewed
  column listed, `unlisted: skip`), atomically, 0600 like other CLI outputs that name tables. Its
  replay is acceptance AT-W3.

### 4.5 Post-scan findings review (part W3)

```text
decoy init --review-findings pipeline.yaml [--result run-result.json]
  1 load       the pipeline YAML (through the gate's parse) and the findings: --result FILE, or the
               newest run-result record for this pipeline in its library (LIB L3a link)
  2 review     per table, per finding: table, column, detector, source and model, severity, match
               rate; verdicts from 4.2
  3 edits      engine finding_edits(config, decisions) -> list of ConfigEdit
  4 preview    a unified diff of the YAML text, then "Write these changes? [y/N]"
  5 write      _yaml_edit.apply_edits -> structural check -> full gate on the result -> atomic replace
```

- `confirm` on a finding for a column with no entry, or with `passthrough`, sets the suggested
  strategy for that detector (the same descriptor `starter_config` uses); `edit` picks one.
- `confirm` on a finding for a column already masked (severity `fail`: the pattern survived) keeps the
  column and proposes the descriptor's stronger entry, shown in the diff; the user still confirms the
  write.
- `reject` adds one entry to the post-scan dismiss list (`post_scan.dismissed`, a SCAN-ML config field:
  `{table, column, detector}`), so the next run reports that finding as `info`. Owner question Q2
  confirms that a reject persists; the recommended answer is yes.
- `skip` changes nothing.

### 4.6 Shared shapes (SCAN-ML cites this section)

The suggestion shape is engine-owned and extends SCAN-MULTI's `ColumnSuggestion`
(`profiling/starter_config.py`, S3-engine.2). Fields the wizard reads, with the part that adds each:

| Field | Type | Added by |
|---|---|---|
| `table`, `column` | `str` | SCAN-MULTI S3-engine.2 |
| `entry` | the column entry this suggestion would write (strategy, provider, provider_config, namespace) as a dict | SCAN-MULTI S3-engine.2 |
| `detector_id` | `str` or `None` (regex detector id or model label) | SCAN-MULTI S3-engine.2 |
| `confidence_bucket` | the regex confidence bucket the CLI inference reads today | SCAN-MULTI S3-engine.2 |
| `note` | value-free REVIEW text | SCAN-MULTI S3-engine.2 |
| `source` | `Literal["regex", "classifier", "ner"]` | SCAN-ML (always `regex` before it) |
| `model` | `ModelRef(id: str, version: str)` or `None` | SCAN-ML |
| `band` | `Literal["high", "review", "low"]` or `None` (classifier band) | SCAN-ML |
| `live` | `bool`: true when `starter_config` wrote this entry into `config` | this plan, E1 |

`StarterConfig.suggestions` is a tuple of `ColumnSuggestion` in table order, then column order, then
source order (`regex`, `classifier`, `ner`). Precedence rule (SCAN-ML must keep it): only a `regex`
suggestion may be `live`; `classifier` and `ner` suggestions are never live. If SCAN-MULTI S3-engine.2
merges without one of its rows above, E1 adds it there as an additive field.

The decision shape is engine-owned, new in E1 (`profiling/starter_review.py`):

```python
class ReviewVerdict(StrEnum):           # one vocabulary for columns and findings
    CONFIRM = "confirm"; REJECT = "reject"; EDIT = "edit"; SKIP = "skip"

@dataclass(frozen=True)
class ReviewDecision:                   # pre-scan: one column
    table: str
    column: str
    verdict: ReviewVerdict
    source: Literal["regex", "classifier", "ner"] | None = None   # which suggestion (CONFIRM)
    entry: Mapping[str, Any] | None = None                        # EDIT only: strategy and options

@dataclass(frozen=True)
class FindingDecision:                  # post-scan: one finding
    table: str
    column: str
    detector_id: str
    verdict: ReviewVerdict
    entry: Mapping[str, Any] | None = None                        # EDIT only

def apply_review(starter: StarterConfig, decisions: Sequence[ReviewDecision]) -> StarterConfig
def finding_edits(config: Mapping[str, Any], decisions: Sequence[FindingDecision]) -> tuple[ConfigEdit, ...]

@dataclass(frozen=True)
class ConfigEdit:                        # what to change; the CLI decides how to write it
    path: tuple[str | int, ...]          # e.g. ("tables", 0, "columns", 3)
    op: Literal["replace", "append"]
    value: Mapping[str, Any]
```

`apply_review` returns a new `StarterConfig` whose `config` passes `PipelineConfig.model_validate` and
`compile_plan` (it raises on a builder bug, like `starter_config`), whose notes say "confirmed",
"rejected (suggested X)" or "edited" for reviewed columns, and which keeps the original note for
skipped ones. A decision for a column not in the starter raises `ReviewInputError` with code
`init.answers_unknown_column`. Two decisions for one column raise with `init.answers_duplicate`.

## 5. Enumerations (from the code at the bases)

### 5.1 Exit paths of `decoy init` today and after

Today (`src/decoy/cli/init.py`):

- `init.py:341` missing input file, exit 1; `init.py:348` bad extension, exit 1, prints `str(exc)`.
- `init.py:352` read failure, exit 3, prints `{exc}` (can carry a value; V1 bar).
- `init.py:361` scan failure, exit 3, prints `{exc}`; `init.py:395` scaffold validation failure, exit 3,
  prints `str(exc)`.
- `init.py:457`, `init.py:546` output exists without `--yes` (non-default modes), exit 1;
  `init.py:464`, `init.py:553` overwrite declined, exit 1; `init.py:540` unknown preset, exit 1.
- Note: `init.py:339`, `init.py:346`, `init.py:350` print the error only when the mode is NOT default,
  so an interactive user sees no message before the exit. SCAN-MULTI S3a.1 rewrites these paths; W1.2
  asserts every exit prints one line in default mode (AT-W9).

Added by this plan: cancel (Ctrl-C, EOF) exit 1; no TTY with a missing input exit 1; answers file
invalid exit 1; NER not installed in non-interactive mode exit 1; reviewed config refused by the gate
(builder bug) exit 3; atomic write failure exit 3 with the `_atomic` code; post-scan: no findings exit
1, YAML changed on disk exit 1, unsupported entry (partial write only on confirm) exit 0 or 1; final
gate warnings with `--fail-on-warning` exit 2 (`gate_exit_code`).

### 5.2 Routes into the wizard

- `decoy init FILES...` in a terminal (prompter: terminal).
- `decoy init FILES...` off a TTY, or with `--no-input`, `--json`, `-q` (prompter: answers, all skip).
- `decoy init FILES... --answers A` (prompter: answers file).
- bare `decoy init` in a terminal (first question: files or template) and off a TTY (preset
  `minimal`, unchanged).
- `decoy init --preset NAME` (template path, unchanged, `init.py:513` to `init.py:577`).
- `-o -` (stdout): the review needs the screen, so `-o -` implies `--no-input`.
- `decoy init --review-findings PIPELINE` in a terminal, or with `--answers` (finding decisions).
- `decoy scan --emit-config` (SCAN-MULTI S3a.2) is NOT a wizard route: it writes the unreviewed starter.
  G-ONE-EMITTER makes both reach the same renderer.

### 5.3 FK shapes

The wizard declares no relationship in V1, but post-scan review can edit a key column of one the user
declared. Shapes from `decoy_engine/config/_relationships.py:24` (`RelationshipEnd.columns`, a list)
and `_relationships.py:37` (`RelationshipConfig`):

- single-column FK (parent and child one column each);
- composite FK (`columns` longer than 1);
- self-referencing FK (parent table equals a child table);
- one parent with several children, possibly in different tables;
- a column that is a key in two relationships (must share one namespace, `namespace_ambiguity`).

Rule (section 4.5): an edit to any key column keeps a keyed strategy and the relationship namespace; the
full gate runs on the edited config before the replace. AT-W12 covers each shape.

### 5.4 Fields of the public types

- `ColumnSuggestion` and `ReviewDecision`, `FindingDecision`, `ConfigEdit`: section 4.6 (every field).
- `ResidualPIIFinding` (`decoy_engine/verification/postmask/types.py:24`): `table`, `column`,
  `detector_id`, `match_rate`, `severity`, `configured_strategy`, `sample_match_count`, `message`,
  `source_identity_rate`, `source_compared`. The review shows table, column, detector, severity and
  match rate; it never shows `message` (free text built elsewhere), and SCAN-ML adds `source` and
  `model`.
- Answers model (`decoy-init-answers/v1`): `schema`, `detectors`, `tables` (name to column to verdict
  or `{verdict, source, strategy, provider, provider_config}`), `unlisted`, `targets_dir`,
  `mask_secret_ref`, and for findings `findings` (table to column to detector to verdict).
- `--json` record (today `init.py:481`): `command`, `status`, `out`, `source`, `mode`,
  `column_count`; the wizard adds `reviewed: {confirm, reject, edit, skip}` counts and `answers` (the
  saved path or null).

### 5.5 Output surfaces

- Terminal prompts and the column summary (stdout, Rich).
- Errors (stderr): each a fixed code plus names; exception class only, never `str(exc)`.
- `--json` record (stdout) and `-q` (nothing on success).
- The written pipeline YAML, REVIEW notes included.
- The answers file written by `--save-answers`.
- The unified diff preview in post-scan review (YAML text only: names and strategies; a pipeline YAML
  holds no cell values).
- Logs at `-v` (stderr): which sections ran, counts, detector and model names (SCAN-ML log lines).
- Help text and epilog (`init.py:33`), including the removal of "STORM" from user-facing text (spec
  section 12).
- Answers-file parse errors (pydantic): routed through the VALUE-FREE-ERRORS converter (roadmap 24a)
  or, if that has not merged, `hide_input_in_errors=True` plus code and location only.

## 6. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | prompts, summary, notes, answers file, `--json`, errors, logs, diff | Suggestions and findings arrive value-free from the engine (`ScanSetCore`, `ColumnSuggestion.note`); errors are fixed codes plus names through the value-free converter; no `str(exc)` anywhere in `cli/wizard/` | AT-W8 seeded canary corpus through every surface in every route; sentry `test_wizard_no_exc_text.py` (AST: no `str(exc)`, f-string of an exception, or `exc.args` in `cli/wizard/`) | M-W8a: a note quotes a top value; M-W8b: an error prints `str(exc)` |
| 2 | Cleanup missing on an exit path | cancel, `q`, scan failure, write failure, gate refusal | Nothing is written until the single write step; the write goes through `_atomic.write_local_target`, which removes its temp file on every failure | AT-W10 exit-path matrix: Ctrl-C, EOF, `q`, scan error, `_atomic` failure, gate refusal, YAML changed; asserts no output file, no answers file, no temp file | M-W10: write the answers file before the YAML write succeeds |
| 3 | State machine and concurrency | review state per item; YAML changed during post-scan review | The review is a pure fold of decisions over the starter (`apply_review`), no hidden state; the editor compares the file hash read at start with the bytes just before replace | AT-W11 property: any permutation of the same decision set gives the same config; AT-W14 file changed between read and write is refused | M-W11: last-writer-wins on duplicate decisions instead of refusing; M-W14: skip the hash check |
| 4 | Route parity and silent fallback | terminal, answers file, no-TTY, `--json`, `-q` | One review loop over a `Prompter` interface; the answers file and the terminal are two implementations; no `if interactive` branch in steps | AT-W3 replay parity (byte-identical YAML); AT-W4 no-TTY equals all-skip; sentry `test_wizard_prompt_boundary.py` (only `_prompts.py` calls `typer.prompt`, `typer.confirm`, `click.prompt`, `input`, `rich.prompt`) | M-W3: answers path applies `confirm` to classifier suggestions on `unlisted: skip`; M-W4: a step calls `typer.prompt` directly |
| 5 | Referential integrity | post-scan edit of a key column | `finding_edits` keeps a keyed strategy and the namespace for any column named in a relationship; the full gate runs on the edited config before replace | AT-W12 per FK shape in 5.3 | M-W12: let `edit` set `redact` on a child key |
| 6 | Untrusted producer | the answers file, the run-result file, the existing YAML | Strict pydantic models with `extra="forbid"` and a schema tag; YAML read through the gate's `parse_pipeline_yaml` (sanitized errors); spans from PyYAML node marks, not regexes | AT-W5 hostile answers corpus (unknown keys, wrong tag, oversize file, alias bombs, non-string keys); AT-W13 hostile YAML shapes refused | M-W5: drop `extra="forbid"`; M-W13: accept an alias node span |
| 7 | Check then use on a path (TOCTOU) | output exists then write; YAML read then replace | Output uses `_atomic` (`CREATE_ONCE` when `--yes` is absent and the file did not exist at start); post-scan replace re-reads and compares the hash immediately before the replace. Residual window accepted for a single-operator CLI (SCAN-MULTI precedent) | AT-W14 | M-W14 (as row 3) |
| 8 | Weak tests and overclaimed evidence | every acceptance test | Each acceptance test names its mutation (section 7); red runs recorded as assertion failures against stubs | Reviewer reruns the named mutations on the final head | removing any named mutation from the evidence record is a gate finding |
| 9 | Behavior-preserving refactor drift | `decoy init --preset`, bare `decoy init` off a TTY, `decoy init FILE` with no answers | Characterization tests first: today's preset output and the S3a.1 `decoy init FILE` output are pinned before W1.2 edits `init.py` | AT-W1 characterization (byte-equal preset output; non-interactive `decoy init FILE` equals S3a.1 output) | M-W1: change the default preset |
| 10 | Frozen contract drift | CLI flags, exit codes, `--json` keys, engine public API, `PipelineConfig` | Additive only: new flags, new `--json` keys, new engine exports; the six exit codes unchanged; no config field added by this plan (SCAN-ML adds the detector fields and `post_scan.dismissed`) | AT-W15 `--json` key snapshot; engine export snapshot test | M-W15: rename `column_count` |

## 7. Acceptance tests (red first)

Written before the build steps of each part. Each test records its red run (assertion failure against
a stub) and names the mutation that must turn it red on the final head. Fixtures: a three-table set
(CSV with header, headerless CSV, Parquet) with seeded canary cells in every column, built by the
SCAN-MULTI fixture helpers.

| Id | Part | Asserts | Mutation |
|---|---|---|---|
| AT-E1 | E1 | `apply_review` over every verdict for a column with one regex suggestion gives: confirm = the suggestion entry, reject = `redact` with the rejected note, edit = the given entry, skip = unchanged entry and note; the result validates and compiles | M-E1a: reject keeps the suggestion entry |
| AT-E2 | E1 | a classifier suggestion is never live in `starter_config` output and becomes the column entry only on `confirm` with `source="classifier"` | M-E2: mark classifier suggestions live |
| AT-E3 | E1 | unknown column and duplicate decisions raise with their codes; the message names the column, never a value | M-E3: silently ignore unknown columns |
| AT-E4 | E1 | property (Hypothesis, fixed seed): for random decision sets over the fixture starter, the result always validates and compiles, and every column not named keeps its starter entry | M-E4: drop namespace on `edit` to a keyed strategy |
| AT-E5 | E2 | `finding_edits`: confirm on an unmasked column yields one `replace` with the descriptor entry; reject yields one `append` to `post_scan.dismissed`; skip yields none | M-E5: reject edits the column |
| AT-W1 | W1.2 | characterization: `--preset` outputs and non-interactive `decoy init FILE` output equal the pinned bytes | M-W1 |
| AT-W2 | W1.2 | scripted terminal session (pty) over the fixture: the YAML reflects each verdict typed, and `a`, `d`, `q` cover the right items | M-W2: `d` skips the whole run instead of the table |
| AT-W3 | W1.2 | `--save-answers A` from the AT-W2 session, then `--answers A --no-input`: byte-identical YAML | M-W3 |
| AT-W4 | W1.2 | off a TTY with no answers: YAML equals the S3a.1 unreviewed starter; a missing header flag exits 1 naming the flag before any read (spy on `scan_sources`) | M-W4 |
| AT-W5 | W1.1 | hostile answers corpus: each case exits 1 with its code, no value echoed, nothing written | M-W5 |
| AT-W6 | W1.1 | the strategy list at an `edit` prompt equals the engine registry list (no hand list); sentry fails on a literal list of strategy names in `cli/wizard/` | M-W6: hard-code the list |
| AT-W7 | W1.2 | for every verdict sequence the scripted prompter can produce over the fixture (exhaustive for 3 columns, sampled for the rest), the written YAML passes `decoy validate config` and `compile` | M-E4 |
| AT-W8 | W1.2, W2, W3 | canary corpus: no canary in stdout, stderr, `--json`, the YAML, the answers file, the diff preview or `-v` logs, on every route in 5.2; non-vacuity: the same corpus is found in the raw fixture bytes | M-W8a, M-W8b |
| AT-W9 | W1.2 | every exit path in 5.1 prints exactly one error line in default mode, and none of the lines holds a canary | M-W9: restore the `is not OutputMode.default` guard |
| AT-W10 | W1.2 | exit-path matrix (class row 2) | M-W10 |
| AT-W11 | W1.1 | permutation property (class row 3) | M-W11 |
| AT-W15 | W1.2 | `--json` key snapshot and engine export snapshot | M-W15 |
| AT-W16 | W2 | detector step writes SCAN-ML's pre-scan and post-scan fields exactly as chosen; NER not installed: terminal offers to continue, non-interactive exits 1 naming the install command | M-W16: write NER into the config when it is not installed |
| AT-W17 | W2 | a classifier suggestion is shown with its model id, version and band, applied only on confirm, and the YAML note names the model | M-E2 |
| AT-W12 | W3 | per FK shape (5.3): editing a key column keeps a keyed strategy and the namespace; the gate passes | M-W12 |
| AT-W13 | W3 | `_yaml_edit`: for a corpus of pipeline files (comments everywhere, blank lines, CRLF, BOM, last entry without trailing newline, unicode names, quoted keys), every byte outside the edited spans is unchanged and the re-parsed dict differs only at the edit paths; anchors, aliases, merge keys, flow-style entries and duplicate keys are refused | M-W13; M-W13b: skip the structural check |
| AT-W14 | W3 | the YAML is changed between read and replace: refused, the file holds the second writer's bytes | M-W14 |
| AT-W18 | W3 | reject on a finding adds a `post_scan.dismissed` entry; the next `decoy run` reports it as `info` (needs the SCAN-ML dismiss part); a second review of the same finding adds nothing | M-W18: append the entry twice on repeat review |
| G-ONE-EMITTER | W1.2 | SCAN-MULTI's guard extended: the wizard's write reaches `_scaffold_yaml.render`; no other module under `src/decoy/` emits a pipeline YAML | M-EMIT-W: the wizard writes `yaml.safe_dump` output |
| G-ONE-EDITOR | W3 | sentry: only `cli/wizard/_yaml_edit.py` writes bytes derived from an existing pipeline YAML (AST walk over write calls in modules that parse a pipeline path) | M-EDIT: post-scan review re-renders the whole file |

## 8. Hostile corpus (ten ways a gate reviewer breaks it)

The plan contract section 4 asks for these; each is an acceptance test above.

1. Answers file with a key named after a cell value, expecting it echoed in the error (AT-W5).
2. A column named `yes`, `null`, `#id` or `a: b` reviewed through `edit` (renderer quoting, AT-W13).
3. A classifier suggestion confirmed by `unlisted: skip` through a default (AT-E2, M-W3).
4. `q` at the first prompt, then a write that still applies suggestions (AT-W2).
5. Ctrl-C after `--save-answers` was given, leaving a half answers file (AT-W10).
6. Off-TTY run that blocks on a prompt (AT-W4, class row 4 sentry).
7. A post-scan edit that turns a composite child key into `redact` (AT-W12).
8. A pipeline file whose column entry is an alias of another (AT-W13).
9. The user edits the YAML in an editor while the review runs (AT-W14).
10. The scan error text carrying a cell value printed at default verbosity (AT-W8, AT-W9).

## 9. Owner questions (each answerable alone; recommended answer first)

- **Q1. How is the post-scan review spelled?** Recommended: `decoy init --review-findings
  pipeline.yaml`. Alternatives: `decoy review pipeline.yaml` (a new verb) or `decoy init findings
  pipeline.yaml` (the draft spec's section mode). Builders proceed with the recommended form; a rename
  is one Typer option.
- **Q2. Does rejecting a post-scan finding persist?** Recommended: yes, as a `post_scan.dismissed`
  entry in the pipeline YAML (`{table, column, detector}`), so the next run reports it as `info`
  instead of warning again. Without it, rejecting a finding changes nothing.
- **Q3. Is `unlisted: confirm` allowed in an answers file?** Recommended: yes; it is the explicit CI
  way to accept every suggestion and is visible in a file the user wrote.

## 10. Reuse inventory

| Need | Existing code | Use |
|---|---|---|
| Scan many tables | SCAN-MULTI `scan_sources` (S1a) | called once per wizard run |
| Starter config and suggestions | SCAN-MULTI `starter_config`, `ColumnSuggestion` (S3-engine.2) | extended additively (4.6), not copied |
| Detector to strategy facts | the engine descriptor registry (SCAN-MULTI S3-engine.1, `profiling/recommendations.py`) | `apply_review` and `finding_edits` read it; no CLI table |
| YAML emission | `cli/_scaffold_yaml.render` (S3a.1), G-ONE-EMITTER | the only new-file writer |
| Pre-run validation | `decoy.cli.gate` (`run_gate_on_config`, `gate_exit_code`), G-ONE-GATE (`tests/sentry/test_gate_single_entry.py`) | the only validation path |
| YAML parse with sanitized errors | `gate/_layers.py` `parse_pipeline_yaml`, `cli/_yaml_errors.py` | for the existing YAML |
| Atomic write | `src/decoy/_atomic.py` (`write_local_target`), `tests/sentry/test_atomic_writer.py` | YAML and answers file |
| Value-free error text | VALUE-FREE-ERRORS converter (roadmap 24a, engine) | answers-file and config errors |
| Output modes | `decoy/ui/output.py` (`setup_output`, `emit_json`) | unchanged |
| Mask secret guidance | `decoy/_mask_secret_guidance.py` | the secrets step and keyed hint |
| Strategy list and options | engine strategy registry | the `edit` prompt |
| Run result and library | RESULT `decoy-run-result/v1` (C1a), LIB L3a run-result record | post-scan findings source |
| Sentry ratchet | `tests/sentry/_ratchet.py`, `scripts/dev/sentry_registry.toml` | new sentries register here |

## 11. Placement

CLI `CODEMAP.md` "Where things go" has no row for an interactive command helper package, and `cli/` is
frozen (LAYOUT draft: "new commands go in a named sub-package"; owner 2026-11-06 Q4). Map change made
in W1.1: add the row "Interactive review wizard for `decoy init`: `src/decoy/cli/wizard/`, files
`_<noun>.py`, tests `tests/unit/test_wizard_*.py` and `tests/e2e/test_init_wizard*.py`, sentries in
`tests/sentry/`".

| New file | Directory | Map line that places it | Sits beside |
|---|---|---|---|
| `cli/wizard/__init__.py` | `src/decoy/cli/wizard/` | new row above (map change in W1.1) | `src/decoy/cli/gate/` (same shape: a named sub-package under the frozen `cli/`) |
| `cli/wizard/_prompts.py` | same | same | |
| `cli/wizard/_answers.py` | same | same | |
| `cli/wizard/_review.py` | same | same | |
| `cli/wizard/_flow.py` | same | same | |
| `cli/wizard/_findings.py` (W3) | same | same | |
| `cli/wizard/_yaml_edit.py` (W3) | same | same | |
| `tests/sentry/test_wizard_prompt_boundary.py`, `test_wizard_no_exc_text.py`, `test_one_editor.py` | `tests/sentry/` | "Repository policy sentries and their scanners" | `test_gate_single_entry.py` |
| engine `profiling/starter_review.py` | `src/decoy_engine/profiling/` | engine CODEMAP Directory Map, `profiling/` row (profiling and detector suggestions; the engine map has no "Where things go" section until LAYOUT E1) | `profiling/starter_config.py` (SCAN-MULTI S3-engine.2) |
| engine `tests/unit/profiling/test_starter_review.py` | engine `tests/unit/profiling/` | same convention as SCAN-MULTI's `test_starter_config.py` | |

Fan-out: `src/decoy/cli/wizard/` holds 7 modules at most; `profiling/` holds 10 entries today.
Sizes: every new file under 400 lines; `cli/init.py` must not grow past its S3a.1 size (about 300):
W1.2 moves the review body into `cli/wizard/_flow.py` and leaves `init.py` the option wiring.

## 12. Frozen contracts touched

- CLI flags of `decoy init`: additive (`--answers`, `--save-answers`, `--no-input`,
  `--review-findings`, `--result`). Behavior change, pre-GA (CLI `CLAUDE.md`: hard delete): a terminal
  `decoy init FILE` now prompts for review; scripts already run off a TTY and get today's output.
- Exit codes: the six public codes only (`src/decoy/cli/exit_codes.py`), no new code.
- `--json` record of `init`: additive keys `reviewed`, `answers`.
- New file format `decoy-init-answers/v1`: new, versioned by its schema tag; a later breaking change
  takes `v2`.
- Engine public API: additive exports `ReviewVerdict`, `ReviewDecision`, `FindingDecision`,
  `ConfigEdit`, `apply_review`, `finding_edits`, `ReviewInputError`; one additive `ColumnSuggestion`
  field (`live`). Compatibility contract note in engine `docs/compatibility-contract.md`.
- `PipelineConfig`: untouched by this plan. The detector fields and `post_scan.dismissed` belong to
  SCAN-ML.
- Error codes: `init.answers_invalid`, `init.answers_unknown_column`, `init.answers_duplicate`,
  `init.yaml_changed`, `init.yaml_edit_unsupported`. The two `answers_*` codes raised by the engine
  (`ReviewInputError`) are engine reason identities, claimed by E1 at merge through REG-RENUMBER; the
  CLI-only ones follow the CLI's existing fixed-code convention.

## 13. Slices

Sizes are hand-written lines (source + tests + docs), estimated. Every part stays under about 800.

| Part | Repo | Lines | Contents | Depends on |
|---|---|---|---|---|
| E1 | engine | ~520 (220 + 270 + 30) | `starter_review.py`: verdict enum, `ReviewDecision`, `apply_review`, `ReviewInputError`; `ColumnSuggestion.live`; exports; AT-E1 to AT-E4 | SCAN-MULTI S3-engine.2 merged |
| W1.1 | CLI | ~640 (330 + 280 + 30) | `cli/wizard/` package: `_prompts.py` (Prompter protocol, terminal and answers implementations, key table), `_answers.py` (model, load, save), `_review.py` (per-table loop over a Prompter); CODEMAP row; sentries for prompt boundary, no exception text, no strategy literal; AT-W5, AT-W6, AT-W11 | E1 released and repinned |
| W1.2 | CLI | ~700 (260 + 400 + 40) | `cli/wizard/_flow.py` (sections, write step, gate); `init.py` rewired to it; `--answers`, `--save-answers`, `--no-input`; G-ONE-EMITTER extended; CHANGELOG, `docs/cli-reference.md`; AT-W1 to AT-W4, AT-W7 to AT-W10, AT-W15 | W1.1; SCAN-MULTI S3a.1 merged (renderer and the `init` rewrite) |
| W2 | CLI | ~420 (160 + 230 + 30) | detector section (pre-scan and post-scan choices, NER availability, the SCAN-ML install command), model and band in the summary; AT-W16, AT-W17, AT-W8 for this route | W1.2; SCAN-ML engine parts with the config fields, classifier suggestions and the NER availability probe, released and repinned |
| E2 | engine | ~380 (150 + 200 + 30) | `finding_edits`, `ConfigEdit`, `FindingDecision`; AT-E5; FK-shape cases for AT-W12 at engine level | E1; SCAN-ML's `post_scan.dismissed` field |
| W3 | CLI | ~780 (330 + 410 + 40) | `cli/wizard/_findings.py`, `cli/wizard/_yaml_edit.py`, `--review-findings`, `--result`; G-ONE-EDITOR; AT-W12 to AT-W14, AT-W18, AT-W8 for this route | W1.2, E2 released and repinned, RESULT C1a, LIB L3a, SCAN-ML post-scan finding fields |

Which parts need what:

- Need SCAN-MULTI S3 (`starter_config`): E1 (S3-engine.2), W1.2 (S3a.1). W1.1 needs only E1.
- Need SCAN-ML: W2 (detector fields, classifier suggestions, NER probe), E2 and W3 (dismiss field,
  post-scan finding `source` and `model`). E1, W1.1 and W1.2 work with regex suggestions only, so the
  wizard ships its core before SCAN-ML.
- Shared files: `cli/init.py` is written by S3a.1 then W1.2 (one writer at a time, after S3a.1
  merges). `profiling/starter_config.py` is written by S3-engine.2, then E1 (one field), then SCAN-ML.

Test depth per part: T0 per edit, T1 impact-selected per commit (`scripts/dev/gates.sh --baseline`).
Escalation triggers: E1 and E2 change engine public exports (frozen contract surface) and may touch
the reason registry; W1.2, W2 and W3 repin the engine. Each of those merge heads gets the full suite
diffed against the stored main baseline, run once by the orchestrator. Tests run on the Mac mini or
`~/bin/vm-run`, never on the devbox.

## 14. Worker evidence rules

Copied from the plan contract section 5; they go into every build handoff for these parts.

- Name the class of every finding and fix the class (the structure in section 6), not only the listed
  instance.
- Write the generated tests first (the canary corpus, the exit-path matrix, the permutation property,
  the hostile answers and YAML corpora) and record them red, as assertion failures against stubs.
- Before pushing, attack your own diff: mutate each new mechanism once (section 7 names them) and
  show its test goes red, then revert. Never commit with a mutation applied.
- Run baselines with `uv.lock` in the same environment as the branch (`scripts/dev/gates.sh
  --baseline`). State what you did not run.
- Never widen a threshold, skip a test, raise a size pin or reduce a budget to make a part pass.
- If a new defect of a class already in the catalog appears, stop and report it. Do not patch a third
  time.
- Commit messages: Conventional Commits, at most 72 characters, final line `cam`, no em-dashes.

## 15. Pre-mortem

Assume it shipped and failed. The likely causes, and what in this plan prevents each:

- **The wizard and `scan --emit-config` drift apart.** One renderer and G-ONE-EMITTER (W1.2).
- **CI hangs on a prompt.** Guarantee 4, AT-W4 and the prompt-boundary sentry.
- **An ML suggestion silently masks (or unmasks) a column.** The `live` precedence rule (4.6), AT-E2
  and AT-W17.
- **Post-scan review wipes the user's comments or reorders the file.** Span-only edits from PyYAML
  marks, the structural check and AT-W13; refusal for shapes it cannot edit exactly.
- **The answers file leaks a value through a validation error.** Strict model with
  `hide_input_in_errors`, the value-free converter, AT-W5 and AT-W8.
- **The review breaks a declared join.** `finding_edits` keeps keyed strategies and namespaces, and the
  full gate runs before replace (AT-W12).
- **SCAN-MULTI S3 or SCAN-ML slips.** E1, W1.1 and W1.2 need only S3; W2 and W3 wait for SCAN-ML.
  The roadmap row stays in progress until W3 lands.
- **Builders re-litigate scope.** Non-goals in section 1 and the follow-up row INIT-WIZARD-2 for the
  draft spec's other steps.

## 16. Follow-ups (recorded, not in V1)

- INIT-WIZARD-2: relationships, subset, checks and CI steps; section mode for every block; drafts and
  `--resume`.
- A `decoy validate` warning when REVIEW notes remain (spec section 8).
- Arrow-key prompts behind the same `Prompter` interface, if users ask.
