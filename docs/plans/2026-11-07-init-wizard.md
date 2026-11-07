Status: plan

# INIT-WIZARD: `decoy init` as a review wizard (CLI roadmap row 32b)

Owner: Cam. Author: claudeworkerbee (Opus). Date: 2026-11-07. Scope: CLI V1, three small engine parts.

Revision 1 (2026-11-07): Dennis round 1 on 85bd40d (GO-WITH-FIXES, 0/7/11/7). Applied in place:
H1 entry spans and comment survival (4.7, AT-W13); H2 namespaces from one helper, a refusal for
unkeyed relationship keys, real oracles (4.6, AT-E4, AT-W7, AT-W12); H3 post-scan findings come from
the `post-scan-integrity/v2` report, bound to the YAML by hash (4.5); H4 new part E0, a public strategy
catalog; H5 saved confirms carry the suggestion identity and refuse when stale (4.4, AT-W19); H6 one
shared YAML mark index `src/decoy/_yaml_marks.py` for `ci/locations.py` and the editor (4.7); H7
dismissals only for warning-severity detector matches, keyed by source, model and strategy (4.6,
AT-W18); M1 to M11 and L1 to L7 in the sections they name.

Revision 2 (2026-11-07): Dennis round 2 on baebeb0 (GO-WITH-FIXES, 0/1/7/7). Applied in place: H1 key
columns need a `join_safe` strategy, a third catalog fact that `_KEY_STRATEGIES` derives from (4.6,
AT-W12, M-W12b); M1 the mark-index move is in W1.1; M2 conditional namespace rule, `example_options`
and `offer_in_wizard` (4.6); M3 report coverage (4.5); M4 span end for block scalars and a comment
check that does not depend on the span (4.7, AT-W13); M5 engine reason codes in existing families
(12); M6 confirm matches the model too (4.6); M7 preflight errors (Guarantee 7, AT-W10); lows in place.
Not applied: the round-2 citation fix `types.py:17` to `:18`; line 17 is `SCHEMA_VERSION` at
`3c01f877`.

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`,
`development-loop.md`, `profiles/local-operations.md`, `feature-dev.md`, `api-and-compatibility.md`,
`cross-cutting-concerns.md`, `reuse-first.md`, `architecture.md`, `testing.md`. Also the plan contract
(`30_Resources/Decoy-Plan-Contract-and-Defect-Catalog.md`), `LOCAL-BUILDER-BRIEF.md`,
`WORKER-STANDARDS.md`, `V1-BAR-WORKER-SECTION.md` and the owner decisions
"SCAN-ML and INIT-WIZARD (2026-11-06)" in `10_Projects/decoy/OWNER-DECISIONS-2026-10-30.md`.

Revision 3 (2026-11-07): cross-model final gate against CLI `be5ba11` and engine `3c01f877`.
Applied in place: path-role collisions are refused before reads and writes (Guarantee 8, AT-W22);
the post-scan report carries an explicit checked-table manifest instead of inferring coverage from
finding rows (4.5, AT-W20); multiple findings for one column are folded against one final entry and
tested for order independence (4.6, AT-E5); the shared YAML mark work distinguishes the existing
ambiguity-only index from the new strict compose API (4.7); nested answers values are strict and safe
errors are raised after their `except` blocks close (4.4, AT-W5).
Then, aligned with the SCAN-ML plan: `tables_checked` and the other report fields come from SCAN-ML
M4 (not E2); `ModelRef` lives in `detection/types.py`; the answers example uses SCAN-ML's
`pre_scan: {detectors: [...]}` shape; an NER suggestion's entry is `text_redact` with `ner`; and 4.5
no longer cites `decoy-run-result/v1`, which is not on CLI main.

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
   A saved `confirm` names the suggestion it confirmed (source, detector id, model id and version,
   strategy); if the replayed scan suggests something else for that column, the run refuses
   (`pre_scan.review_stale`) instead of applying a suggestion nobody saw.
4. **No prompt without a terminal.** When stdin or stdout is not a TTY, or `--no-input`, `--json`, `-q`
   or `--answers` is given, the wizard never prompts. A required input that no flag or answer supplies
   is a usage error (exit 1) naming the flag, before any source is read.
5. **One writer per kind of write.** A new pipeline YAML is written only through
   `_scaffold_yaml.render` (SCAN-MULTI G-ONE-EMITTER, extended to the wizard). An existing pipeline
   YAML is edited only through `cli/wizard/_yaml_edit.py`, which changes only the lines of the edited
   entries (and the REVIEW note directly above each) and leaves every other byte, every other comment
   included, unchanged (span rule in 4.7). Both write through `src/decoy/_atomic.py`.
6. **Value-free.** Prompts, summaries, REVIEW notes, the answers file, `--json`, errors and logs carry
   names (tables, columns, detectors, strategies, models, file names; owner 2026-11-06 "names are
   structure") and counts, never a cell value or a secret.
7. **The wizard never writes a config the engine refuses, or one that fails at run time for a missing
   namespace.** Before any write the result goes through the pre-run gate once
   (`run_gate_on_config(raw, out_path)`, `src/decoy/cli/gate/_layers.py:288`, all three layers; the
   path is used only for its directory). A config or compile error is a builder bug: exit 3, nothing
   written. Preflight findings (errors included, such as capacity or a missing native companion)
   describe this machine, not the config, so the YAML is still written; they are shown, `--json`
   carries `status: "written"` plus `gate: {errors, warnings, exit_code}`, and the exit code is
   `gate_exit_code` (for example 5 for capacity). Because the
   gate does not check that a namespace-required strategy has a namespace (engine probe at
   `3c01f877`: `{strategy: hash}` with no namespace passes validate and no-profile compile;
   `hash_requires_namespace` is a runtime reason only), every entry the wizard writes is built by the
   one engine entry helper (4.6), which sets the namespace from the strategy catalog (part E0).
8. **A path has one role.** After flags and any answers file are parsed, but before any data source is
   read or any file is written, project mode refuses an output YAML or `--save-answers` target that
   names the same file as a source, the input answers file, or
   each other. Existing files are compared by `samefile`; missing targets by resolved parent plus
   name. The findings route likewise refuses collisions among the pipeline, report, answers input
   and any answers output. `-o -` has no file identity. This prevents the second write from replacing
   the pipeline and prevents a YAML or answers write from replacing source data.

### Non-goals (V1)

- Relationship, subset, checks and CI steps of the draft spec (sections 4.5, 4.6, 4.9, 4.10). The
  YAML keeps SCAN-MULTI's commented relationship template. Follow-up row INIT-WIZARD-2.
- The draft spec's `goal` step (spec 4.1: mask, generate, subset, tokenize). V1 masks scanned
  sources; generate configs stay on the template path (`--preset generate`), tokenize stays a strategy
  the user can add by hand because it requires vault-backed runner setup and is not offered by this
  wizard. Follow-up row INIT-WIZARD-2.
- Section mode of the draft spec for every block (`decoy init <section> <pipeline>`), drafts and
  `--resume`, project scaffold files. Only the post-scan findings review edits an existing file in V1.
- Arrow-key selection or any new prompt dependency (section 2).
- A `decoy validate` warning for unreviewed REVIEW notes (spec section 8). Follow-up row; it edits the
  gate and is not needed for the owner's ask.
- Downloading models. The wizard never touches the network; it names the SCAN-ML setup command when
  NER is chosen but not installed.
- Writing a mask secret. The wizard asks only for a reference (`env:` or `file:`). Today `init`
  asks nothing about secrets and only prints the keyed hint (`init.py:614` to `init.py:618`); the
  secrets step is new and stores the reference only.

### Failure modes

| Case | V1 behavior |
|---|---|
| No TTY and a required input is missing (sources, a CSV header flag) | Exit 1 before any read, naming the missing flag. No prompt, no hang. |
| `--answers` file does not parse, has an unknown or duplicate key, a missing or wrong schema tag, a non-string key, is over 1 MiB, or names a table or column that is not in the scan | Exit 1 before any write. The error names the key path and the code (`init.answers_invalid` for parse, key, tag, type and size problems including a duplicate key; `pre_scan.review_unknown_column` for a name not in the scan) through the value-free error converter. Key paths are names (owner 2026-11-06: config keys, table and column names are shown); the value on the right of a key (a verdict, a strategy, an option) is never echoed. |
| A saved `confirm` no longer matches what the scan suggests for that column (other source, detector, model version or strategy), or a `confirm` names a column with no matching suggestion | Exit 1 (`pre_scan.review_stale`, naming the column path and the field that differs), nothing written. |
| User presses Ctrl-C or sends EOF at a prompt | Exit 1 (`cancelled`), nothing written, no answers file written. |
| User answers `q` | Review stops; every remaining item counts as `skip`; the wizard goes on to the write step. |
| A source fails to read or scan | Exit 3 naming the table and the exception class only (SCAN-MULTI S3a behavior). Nothing written. |
| An `edit` verdict names a strategy the engine does not know, or omits a required option | Re-asked at the prompt with the engine's value-free message. In an answers file: exit 1 naming the column path. |
| The reviewed config fails the gate's config or compile layer | A builder bug: exit 3, nothing written, the gate findings shown. Acceptance AT-W7 proves the review cannot produce one for the sampled verdict sequences over the fixtures. |
| The YAML is written but `--save-answers` fails | Exit 3 with the `_atomic` code; the message says the pipeline was written and the answers file was not. |
| `--save-answers` already exists | Exit 1 before any source read. Answers use `CREATE_ONCE`; `--yes` applies only to the pipeline output and never authorizes replacing an answers record. |
| Two init path roles resolve to the same file, including a symlink or hard link (for example `-o customers.csv`, `--save-answers pipeline.yaml`, or the same file as `--answers`) | Exit 1 (`init.path_collision`) before any source read or write, naming the two roles but not file contents. |
| Output file exists | Same as today: refuse without `--yes` in non-interactive modes; ask in a terminal. `--yes` only answers this question. |
| NER chosen but spaCy or its model is not installed | The detector step says so, names the SCAN-ML install command, and offers to continue without NER. Non-interactive: exit 1 naming the command. |
| Post-scan review: the pipeline YAML changed on disk after it was read | Refused before replace (`init.yaml_changed`), nothing written. |
| Post-scan review: the entry to edit uses an anchor, alias, merge key or flow style, or the key is duplicated; or a dismissal must go into a flow-style `post_scan: {...}` block | Refused for that entry (`init.yaml_edit_unsupported`, naming the column path); the replacement entry is printed for a hand edit. Other entries still apply only if the user confirms the partial edit. |
| An `edit` or `confirm` gives a key column of a declared relationship a strategy the catalog does not mark `join_safe` (anything but an injective, deterministic per-value map: today `hash` and `fpe`), or a namespace other than the relationship's | Refused (`config.key_column_not_join_safe`, naming the column path and the relationship's position) at the prompt, or exit 1 from an answers file. The gate does not catch this today (SCAN-MULTI probe: `redact` on a relationship key compiles), so the engine review functions own the check. |
| Post-scan review: the pipeline YAML is a symlink | Refused (`init.yaml_symlink`); the message says to pass the link's target path. Replacing the link would leave the real file unedited. |
| Post-scan review: no report given, the report has the wrong schema or no `tables_checked` manifest, or it was made from another version of this YAML (its `config_sha256` differs from the file's) | Exit 1 (`init.report_missing`, `init.report_schema`, `init.report_stale`) with a hint naming the command that writes a fresh report. |
| Post-scan review: `n` on a `fail` finding | Not offered: a failed mask check cannot be dismissed (4.6, dismissal rule). The prompt offers confirm, edit or skip. From an answers file: exit 1 (`post_scan.dismiss_refused`). |

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
  (`yaml/composer.py`), and the CLI already indexes those marks for the same pipeline text:
  `src/decoy/ci/locations.py:1` makes a read-only `yaml.compose` pass, resolves numeric and semantic
  paths to nodes, withholds ambiguous locations for aliases, merge keys and duplicate keys, and caps
  the node count (`locations.py:30`). W1.1 moves that walk and adds one strict compose result in the
  shared module so the answers loader and editor can refuse those shapes rather than mistaking an
  absent location for a clean document (4.7). A block mapping's own `end_mark` runs past its last line into the blank lines
  and comments of whatever follows (checked with PyYAML 6.0.3 on 2026-11-07: the first column entry's
  span ended after the next entry's `# REVIEW:` line), so the editor never uses it; the span rule is
  in 4.7. The editor replaces only those lines, re-parses, checks the parsed result differs only at
  the intended paths, and checks every comment outside the replaced lines survives in order. It
  replaces the draft spec's column-0 "block splice" (spec section 6).
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
  `edit` prompt comes from the public strategy catalog (part E0), never a hand list; the catalog is
  one descriptor per handler (four class attributes on each handler, read by `strategy_catalog()`), so
  a new strategy is one edit. Detector names and the pre-scan and post-scan config fields come from
  SCAN-ML's config models. Column entries come from one engine helper (`column_entry`, 4.6).
- **Choke points.** Section 6 rows 1, 4 and 6; section 7 guards G-ONE-EMITTER, G-ONE-EDITOR, the
  prompt-boundary sentry and G-CATALOG. All init file roles pass through the one pre-read path-role
  check in `_flow.py`; AT-W22 seeds a raw-string-only comparison and must turn red.

## 4. Behavior

### 4.1 Command surface

```text
decoy init [FILES...] [--has-header|--no-header] [--column-names ...]   project mode (wizard)
decoy init --review-findings PIPELINE --report FILE                     post-scan findings review
decoy init --preset NAME                                                template path
```

New flags: `--answers FILE`, `--save-answers FILE`, `--no-input`, `--fail-on-warning` (as in
`decoy validate`, feeds `gate_exit_code`), `--review-findings PIPELINE`, `--report FILE`. Kept:
`-o/--output`, `--preset`, `-y/--yes`, `--json`, `-q`, `-v`, and the header flags SCAN-MULTI S3a.1
adds. `--json` and `-q` imply `--no-input`. Section mode spelling is owner question Q1 (section 9);
`--review-findings` is the recommended form and the only edit entry in V1.

Bare `decoy init` in a terminal asks first: "Start from data files, or from a template?" The template
answer runs today's preset questions, now through the `Prompter` (W1.2 moves the raw prompts at
`init.py:462`, `:551`, `:585`, `:594`, `:599` and `:600` behind it). Behavior change: today bare
`decoy init` off a TTY in default mode reaches `typer.prompt` (`init.py:585`) and hangs on an open
stdin or aborts on EOF; only `--json` and `-q` take the `minimal` preset (`init.py:555`,
`init.py:572`). After W1.2, off a TTY it takes the `minimal` preset with today's default paths in
every mode, the same answer the non-interactive `Prompter` gives.

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
suggestion was confirmed by its identity (4.6: source and detector id, plus model id and version for a
model suggestion).

Post-scan findings use the same keys and verdicts (section 4.5). For a finding, `confirm` means "this
is real PII: mask it" and `reject` means "false positive: dismiss it", which is offered only where the
dismissal rule in 4.6 allows it.

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
  7 write        apply_review -> run_gate_on_config (all layers, once) -> render -> atomic write
                 -> --save-answers file if asked
  -> summary: counts of confirmed, rejected, edited, skipped per table; the gate report; the next
     command
```

The column summary is a Rich table with one row per column: name, suggested type, source
(`regex`, `classifier`, `ner`), band or confidence bucket, the entry that skip keeps, and the
suggested entry. Values never appear (the scan record holds none: SCAN-MULTI `ScanSetCore`).

After the summary has been shown, the wizard offers per table: review each column, confirm every
suggestion in the summary (`a`), or skip the table (`d`). The bulk confirm is offered only after the
user has seen every suggestion it applies. This answers the draft spec's open question 8 (tables with
50 or more columns) without a separate mode.

### 4.4 Non-interactive path

- Inputs come from flags (sources, header flags, `-o`), then from `--answers`, and nothing is prompted
  (Guarantee 4).
- The answers file, schema tag `decoy-init-answers/v1`, YAML or JSON:

  ```yaml
  schema: decoy-init-answers/v1
  sources:                         # every source the session used, as it answered them
    - {path: 'data/customers.csv', has_header: true}
    - {path: 'data/raw.csv', has_header: false, column_names: ['id', 'yes', 'null']}
  detectors:                       # part W2; field names are SCAN-ML's config fields
    pre_scan: {detectors: [regex, classifier]}
    post_scan: {integrity: true, detectors: [regex, ner], ner_findings: warn}
  tables:
    'customers':
      'email': {verdict: confirm, source: regex, detector_id: email, strategy: faker}
      'full_name': {verdict: confirm, source: classifier, detector_id: person_name,
                    model: {id: lgbm-v1, version: '0.1.0'}, strategy: faker}
      'notes': reject
      'region': {verdict: edit, entry: {strategy: passthrough}}
  unlisted: skip                   # skip (default) or confirm
  targets_dir: 'out/'              # optional
  mask_secret_ref: 'env:DECOY_MASK_SECRET'   # optional
  ```

- Flags win over the file: a source or header flag given on the command line replaces the file's
  `sources`; giving both for the same path with different values is a usage error.
- A `confirm` carries the identity of the suggestion confirmed. A hand-written short form
  (`email: confirm`) means "confirm the only suggestion for this column"; it is refused
  (`pre_scan.review_stale`) when the column has none or more than one. `--save-answers` always writes the
  full form.
- `unlisted: confirm` is the explicit "accept every suggestion" answer for CI. It is a user
  confirmation written in a file the user controls, so owner decision "the user confirms" holds. It is
  not stale-checked (it names no suggestion); the `-v` log and `--json` count what it confirmed.
- Loader (W1.1): YAML through the shared mark index's strict compose API and duplicate-key refusal
  (4.7), then a pydantic model with `extra="forbid"`, `hide_input_in_errors=True` and strict types
  (`StrictStr`, `StrictBool`, `Literal` verdicts, no coercion of `yes` or `1`). The nested source,
  model, confirm and edit-entry models are strict too: a numeric string, a bool in an integer field,
  or a string in a bool field is refused before `column_entry`; no `Mapping[str, Any]` wire field
  bypasses this rule. The schema tag is required; files over 1 MiB are refused before parsing. A
  caught parser or validation exception is reduced to a code and key path, then the safe exception
  is raised after the `except` block has closed, so both `__cause__` and `__context__` are `None`.
- `--save-answers FILE` writes the decisions the session made in this exact shape (every source and
  every reviewed column listed, `unlisted: skip`), with every table name, column name and path written
  as a single-quoted scalar through the renderer's `_yaml_quote` so names such as `yes`, `null` or `on`
  load back as strings. It is written after the YAML, atomically, 0600 with `CREATE_ONCE`; an existing
  file is never replaced. Its replay is acceptance AT-W3. The one path-role precheck in `_flow.py`
  runs before source reads and covers the YAML, sources, answers input and answers output (AT-W22).

### 4.5 Post-scan findings review (parts W3.1 and W3.2)

```text
decoy init --review-findings pipeline.yaml --report integrity.json
  1 load       the pipeline YAML (through the gate's parse; refused if it is a symlink) and the
               post-scan integrity report (schema post-scan-integrity/v2, the per-finding records
               of decoy_engine/verification/postmask/types.py:24); refuse a report whose
               config_sha256 is not the SHA-256 of this YAML file's bytes
  2 review     per table, per finding: table, column, detector, source and model, severity, match
               rate; verdicts from 4.2 (reject only where the dismissal rule allows)
  3 edits      engine finding_edits(config, decisions) -> tuple of ConfigEdit
  4 preview    a unified diff of the YAML text, then "Write these changes? [y/N]"
  5 write      _yaml_edit.apply_edits -> structural and comment checks -> run_gate_on_config on the
               edited config -> atomic replace keeping the file's mode
```

- **Where findings come from.** `decoy run` does not save the post-scan report today: the engine
  computes it when `post_scan.integrity` is on and keeps it in memory
  (`execution/_pipeline_finalize.py:503`, report-only), and `src/decoy/cli/run.py` never reads it.
  The run `--json` record carries no detector, severity or match rate (`run.py:1210`); the planned
  run result `decoy-run-result/v1` (RESULT plan) is not on CLI main at `be5ba11`. Per-finding data exists only in the `post-scan-integrity/v2` report, which
  `decoy report integrity MASKED --source SRC --config pipeline.yaml --output FILE` writes today
  (`src/decoy/cli/report.py:1949`, with the file write at `:2092`). W3.2 reads that report through
  `--report`. SCAN-ML owns the two
  producer changes W3.2 needs: SCAN-ML adds `config_sha256` (the SHA-256 of the pipeline YAML bytes
  it was made from, when `--config` is given) and per-finding `source` and `model`, and
  `tables_checked` (every table actually passed through the post-scan check, including clean tables
  with no finding row; SCAN-ML part M4 is the one writer of the report types). `decoy run`
  with post-scan on writes the same report beside its outputs. Until the run writes it, users run
  `decoy report integrity` by hand; the hint printed on `init.report_missing` names that command.
  The hand command checks the first declared table only and takes one CSV per side
  (`report.py:1949`), so for a multi-table pipeline the run-written report is the producer W3.2 is
  built for.
- **Coverage.** W3.2 compares the report's strict `tables_checked` manifest with the YAML's tables;
  it never infers coverage from finding rows because a clean checked table has none. Tables in the
  YAML absent from that manifest are listed before the review ("not covered by this report: ...");
  a checked table or finding table not in the YAML, or a finding whose table is absent from
  `tables_checked`, is refused (`init.report_stale`). `--json` carries the uncovered list.
- **Reading the report.** `--report` is read with a 16 MiB cap. The schema is engine-owned and may
  gain keys, so the model ignores unknown keys but requires, with strict types, the schema tag,
  `config_sha256`, `tables_checked` and each finding's table, column, detector, severity, source and
  model. Duplicate checked-table names or duplicate finding identities are refused. An oversize file
  or a missing or mistyped field exits 1 (`init.report_schema`).
- `confirm` on a finding for a column with no entry, or with `passthrough`, sets the entry
  `column_entry` builds for the finding's detector (4.6); `edit` picks one.
- `confirm` on a `fail` finding (the pattern survived the configured strategy, or the output matches
  the source row for row, `types.py:25` to `types.py:45`) proposes the detector's default entry when
  it differs from the configured one. When it is the same strategy, `confirm` is not offered (it would
  change nothing) and the prompt offers `edit` or `skip`.
- `reject` adds one dismissal (4.6) to `post_scan.dismissed`, only for findings the dismissal rule
  allows. When the file has no `post_scan:` block, the edit appends one at the end of the file
  (`ConfigEdit` op `append_block`); when it has one without `dismissed`, it appends the key inside it.
  Owner question Q2 confirms that a reject persists; the recommended answer is yes.
- `skip` changes nothing.
- Each edited column entry's REVIEW note (the comment lines directly above the entry that start with
  `# REVIEW:` and their `#   ` continuations) is replaced by the new note; no other comment changes.
- Routes: off a TTY or with `--json`, `--review-findings` needs `--answers` (finding decisions under
  `findings:`); without it, exit 1 naming `--answers`. With `--json` it prints a record of the counts
  and the edits applied (paths only).
- The replace keeps the original file's permission bits: W3.1 adds a `mode` argument to
  `_atomic.write_local_target` (the one writer; its sentry and tests cover the new argument) and passes
  the stat mode read at load.

### 4.6 Shared shapes (SCAN-ML cites this section)

This section is the single definition of the review shapes. SCAN-MULTI names `ColumnSuggestion` and
`StarterConfig` (S3-engine.2) but does not define their fields; E1 owns the definitions below. If
S3-engine.2 merges first with other fields, E1 reconciles them additively in the same file
(`profiling/starter_config.py`), never with a second type.

**Strategy catalog (E0).** Each scalar strategy handler (today the private table
`execution/_strategies/__init__.py:44` `SCALAR_HANDLERS`, 25 handlers) declares four class attributes
with no inherited default. A public function reads them. Option type and placement are catalog facts,
not a second CLI parser:

```python
@dataclass(frozen=True)
class StrategyOption:
    name: str
    wire_type: Literal["str", "int", "float", "bool", "str_list", "float_list"]
    required: bool
    location: Literal["column", "provider_config"]
    choices: tuple[str, ...] | None
    example: str | int | float | bool | tuple[str, ...] | tuple[float, ...]

@dataclass(frozen=True)
class StrategyInfo:
    name: str
    namespace_required: bool            # true when ANY mode of the strategy needs a namespace
    join_safe: bool                     # injective and deterministic per value: may mask a FK key
    options: tuple[StrategyOption, ...] # allowed V1 wizard options; empty is valid
    offer_in_wizard: bool               # listed at the wizard's `edit` prompt

    @property
    def required_options(self) -> tuple[str, ...]: ...
    @property
    def example_options(self) -> Mapping[str, str | int | float | bool | list[str] | list[float]]: ...

def strategy_catalog() -> tuple[StrategyInfo, ...]      # sorted by name; exported from decoy_engine
```

- `namespace_required` is conservative: `shuffle` needs a namespace only when `deterministic`
  (`_shuffle.py:43`) and `code_set` only in `gen` mode (`_code_set.py:139`); both are marked true and
  `column_entry` always sets a namespace for them. A namespace is harmless where it is not read.
- `join_safe` is the fact the native route already states in prose and in a private tuple:
  "Only hash and fpe may be native FK keys ... both are injective, deterministic per-value maps"
  (`execution/_sequential_native.py:13`, `_KEY_STRATEGIES` at `:129`). E0 marks `hash` and `fpe`
  true and every other handler false, and derives `_KEY_STRATEGIES` from the catalog, so one place
  holds it. `categorical`, `shuffle`, `date_shift` and `bucket_perturb` need a namespace but are not
  join-safe (`categorical` maps inputs into a finite category pool, `_categorical.py:1` to `:10`).
- `offer_in_wizard` is true for the simple scalar strategies whose options are plain values (V1 bar):
  `passthrough`, `redact`, `truncate`, `faker`, `hash`, `bucketize`, `top_code`, `shuffle`,
  `categorical`, `date_shift`, `fpe`, `text_redact`, `text_mask`, `geo_generalize`, `code_set`,
  `bucket_perturb`. Strategies whose options are expressions, column references, child strategies or
  a vault (`formula`, `nested`, `joint_mask`, `derived`, `derived_aggregate`, `grouped_series`,
  `windowed_date`, `group_key`, `tokenize`) are edited by hand in V1.
- `StrategyOption` is the one source for prompt parsing, strict answers types, whether a value is a
  top-level `ColumnConfig` field or a `provider_config` member, choices, and test examples. The two
  derived views above let tests build every offered entry and let prompts enumerate required fields
  without parallel tables. Terminal list options accept one JSON array and answers files use a YAML
  sequence; both are exact-typed element by element. AT-E0b guards the derivation.

The CLI's `_NAMESPACE_REQUIRED_STRATEGIES` (`init.py:180`) and SCAN-MULTI's descriptor copy of it
(planned in `profiling/recommendations.py` and `_starter_inference.py`, S3-engine.1) derive from this
catalog: S3-engine.1 reads it if E0 merges first; otherwise E0 replaces that copy. This is a
shared-file item for the orchestrator's ledger and a note for the SCAN-MULTI builder.

**One entry helper (E1).** Every column entry the review writes is built by one function:

```python
def column_entry(strategy: str, column: str, *, options: Mapping[str, Any] | None = None,
                 namespace: str | None = None) -> dict[str, Any]
```

It refuses an unknown strategy, an option absent from that strategy's descriptor, a wrong exact
primitive type (bool is not int), a value outside `choices`, or a missing required option
(`ReviewInputError`, code `config.entry_invalid`, naming the column and the option key), and sets `namespace` to the given
value or, when the catalog says `namespace_required`, to the column name (today's starter rule,
`init.py:218`). `starter_config` (S3-engine.2) builds its entries through the same function. Each
option's catalog `location` decides whether it is set at the top level or under `provider_config`;
the CLI never introspects `ColumnConfig` or keeps a placement table. The EDIT call is
`column_entry(entry["strategy"], column, options=rest_of_entry)`.

**Suggestion.**

```python
@dataclass(frozen=True)
class ModelRef:                   # defined once in detection/types.py (SCAN-ML 4.2)
    id: str                       # e.g. "lgbm-v1", "en_core_web_sm"
    version: str

@dataclass(frozen=True)
class ColumnSuggestion:
    table: str
    column: str
    source: Literal["regex", "classifier", "ner"]   # always "regex" until SCAN-ML
    detector_id: str              # regex detector id, or the model label mapped to a detector id
    model: ModelRef | None        # None for regex
    band: Literal["high", "review", "low"] | None   # classifier band; None for regex and ner
    confidence_bucket: str | None # the regex bucket the CLI inference reads today; None for models
    entry: Mapping[str, Any]      # built by column_entry: detector_id's default strategy, or for
                                  # source ner `text_redact` with an `ner` option (SCAN-ML 4.3)
    live: bool                    # True when starter_config wrote this entry into config
```

- Identity: `(table, column, source, detector_id)`. There is at most one suggestion per identity;
  a model that yields two labels for one column yields two suggestions with different `detector_id`.
- `StarterConfig.suggestions: tuple[ColumnSuggestion, ...]` in table, column, source order
  (`regex`, `classifier`, `ner`), then `detector_id`. REVIEW text lives only in
  `StarterConfig.notes` (one note per column, SCAN-MULTI); suggestions carry none.
- Precedence: only a `regex` suggestion may be `live`, at most one per column; `classifier` and
  `ner` suggestions are never `live`.
- A model label maps to a `detector_id`, and so to a default entry, through the engine detector
  descriptor registry (SCAN-MULTI S3-engine.1, `profiling/recommendations.py`). SCAN-ML adds the label
  rows (SCAN-ML 4.4); a label with no row yields no suggestion and one count in the scan log.

**Decisions.**

```python
class ReviewVerdict(StrEnum):           # one vocabulary for columns and findings
    CONFIRM = "confirm"; REJECT = "reject"; EDIT = "edit"; SKIP = "skip"

@dataclass(frozen=True)
class SuggestionRef:                    # what the user saw and confirmed
    source: Literal["regex", "classifier", "ner"]
    detector_id: str
    model: ModelRef | None
    strategy: str

@dataclass(frozen=True)
class ReviewDecision:                   # pre-scan: one column
    table: str
    column: str
    verdict: ReviewVerdict
    confirmed: SuggestionRef | None = None    # CONFIRM only
    entry: Mapping[str, Any] | None = None    # EDIT only: strategy and options, through column_entry

@dataclass(frozen=True)
class FindingDecision:                  # post-scan: one finding
    table: str
    column: str
    detector_id: str
    source: Literal["regex", "classifier", "ner"]
    model: ModelRef | None
    verdict: ReviewVerdict
    entry: Mapping[str, Any] | None = None    # EDIT only

def apply_review(starter: StarterConfig, decisions: Sequence[ReviewDecision]) -> StarterConfig
def finding_edits(config: Mapping[str, Any], report: Mapping[str, Any],
                  decisions: Sequence[FindingDecision]) -> tuple[ConfigEdit, ...]

@dataclass(frozen=True)
class ConfigEdit:                        # what to change; the CLI decides how to write it
    path: tuple[str | int, ...]          # e.g. ("tables", 0, "columns", 3)
    op: Literal["replace", "append", "append_block"]
    value: Mapping[str, Any]
    note: str | None                     # the new REVIEW note for a replaced column entry
```

- `apply_review` returns a new `StarterConfig`. CONFIRM applies the suggestion whose identity,
  model (id and version, or both absent) and strategy all equal `confirmed`; if none does, it raises `ReviewInputError` (`pre_scan.review_stale`,
  naming the column and the differing field). REJECT writes `column_entry("redact", column)` with the
  note "rejected (suggested X)". EDIT writes `column_entry(**entry)`. SKIP keeps the starter entry and
  note. A decision for a column not in the starter raises `pre_scan.review_unknown_column`; two for one
  column raise `pre_scan.review_duplicate`. A caught validation exception is reduced to names and a
  registered code, then `ReviewInputError` is raised after the `except` block closes; tests assert
  both `__cause__` and `__context__` are `None`.
- Relationship keys: for a column named in any declared relationship's `parent.columns` or
  `children[].columns` (all shapes in 5.3), CONFIRM and EDIT keep the relationship's namespace, and a
  strategy whose catalog row says `join_safe: false` is refused (`config.key_column_not_join_safe`).
  REJECT on such a column keeps the SCAN-MULTI key entry (`hash` with the relationship namespace)
  instead of `redact`. `finding_edits` applies the same rule.
- The returned config passes `PipelineConfig.model_validate` and `compile_plan` and every entry whose
  strategy is `namespace_required` has a namespace (asserted inside both functions; a failure is a
  builder bug and raises).
- `finding_edits` keys decisions by the full finding identity and refuses an unknown or duplicate
  identity. It groups decisions by column before producing edits. At most one final replacement entry
  is emitted for a column: compatible CONFIRM/EDIT decisions fold to that entry, conflicting proposed
  entries raise `post_scan.review_conflict`, and every dismissal for the column records that final
  strategy. The result is independent of decision order. Its safe errors follow the same closed
  `except`-scope rule as `apply_review`.

**Dismissal (shape owned here, field owned by SCAN-ML).** A `post_scan.dismissed` entry is
`{table, column, detector_id, source, model_id, model_version, strategy}`, where `strategy` is the
column's configured strategy when the dismissal was made. A post-scan finding is reported as `info`
instead of `warning` only when every field matches the finding and the column's current strategy.
Rules:

- Only `warning`-severity residual-PII findings that come from a detector match can be dismissed.
  A `fail` finding, and any finding raised from source-identity evidence (`source_compared` true with
  `source_identity_rate` at or over `_LEAK_WARN_RATE`, `verification/postmask/residual_pii.py:122`),
  is never lowered by a dismissal and cannot be rejected in the review.
- A dismissal stops applying when the column's configured strategy changes, or the detector's model
  version changes; the finding is then reported again at its own severity, and the stale dismissal is
  counted in the run log.
- `finding_edits` never appends a duplicate dismissal (same fields); a repeat review is a no-op.

### 4.7 The YAML editor (W3.1) and the shared mark index (W1.1)

- **One mark index.** W1.1 moves the compose pass and path resolution of
  `src/decoy/ci/locations.py` (numeric and semantic paths, ambiguity markers for aliases, merge keys
  and duplicate keys, and the node cap) into `src/decoy/_yaml_marks.py`. The shared walk returns both
  marks and typed issue records; the existing `YamlSourceIndex` keeps withholding ambiguous locations,
  while the new strict entry used by `_yaml_edit.py` and the answers loader refuses any issue. This
  distinction is required because the pinned `locations.py:132` to `:158` skips ambiguous nodes but
  does not currently reject the document. `ci/locations.py` keeps its public names and its existing
  tests pass unchanged.
- **Span rule.** The span of a column entry is whole lines: from the line of the sequence item's dash
  through the last line of the entry's last scalar, found by recursing to the last value node, never
  the mapping's own `end_mark`. A block scalar's `end_mark` can sit at column 0 of the next line after
  its trailing blank lines (PyYAML 6.0.3 probe by the reviewer, 2026-11-07), so: when the end mark is
  at column 0 the span ends on the previous line, and trailing blank lines are dropped from the span
  unless the scalar's chomping indicator is keep (`|+` or `>+`). The REVIEW note directly above the
  entry is replaced with it (4.5). Blank lines and comments after the span belong to whatever follows
  and are never touched.
- **Refusals** (`init.yaml_edit_unsupported`, naming the column path and the reason): an alias,
  anchor or merge key anywhere in the entry; a flow-style entry; a duplicate key; a comment line or
  trailing comment inside the entry's own lines (it would be lost); an entry sharing a line with
  another node. The replacement entry is printed for a hand edit.
- **Writing an entry.** The replacement lines are the renderer's column-entry text
  (`_scaffold_yaml`, the same emitter that writes new files) at the entry's original indentation, with
  the file's line ending (LF or CRLF) and no change to a BOM.
- **Checks before the replace.** Re-parse the edited text; its `safe_load` result equals the original
  with exactly the `ConfigEdit`s applied; every comment line of the original file, except the REVIEW
  notes of the edited entries, is present in the edited text in the same order (computed from the two
  texts with the tokenizer, independent of the span); the file's bytes on disk still hash to the value
  read at load (`init.yaml_changed`).
- **Dismissal into an existing block.** `post_scan:` as a block mapping takes a `dismissed:` key
  appended as its last child, or one list item appended to an existing block `dismissed:` list. A
  flow-style `post_scan: {...}` or `dismissed: [...]` is refused (`init.yaml_edit_unsupported`).

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
invalid or path-role collision exit 1; NER not installed in non-interactive mode exit 1; reviewed config refused by the gate
(builder bug) exit 3; atomic write failure exit 3 with the `_atomic` code; answers file write
failure after the YAML was written exit 3; stale answers exit 1; post-scan: report missing, wrong
schema or stale exit 1, symlinked YAML exit 1, YAML changed on disk exit 1, no `--answers` off a TTY
exit 1, unsupported entry (partial write only on confirm) exit 0 or 1; gate warnings with the new
`--fail-on-warning` flag exit 2 (`gate_exit_code`).

### 5.2 Routes into the wizard

- `decoy init FILES...` in a terminal (prompter: terminal).
- `decoy init FILES...` off a TTY, or with `--no-input`, `--json`, `-q` (prompter: answers, all skip).
- `decoy init FILES... --answers A` (prompter: answers file).
- bare `decoy init` in a terminal (first question: files or template) and off a TTY (the `minimal`
  preset in every mode; a behavior change in default mode, 4.1).
- `decoy init --preset NAME` (template path, `init.py:513` to `init.py:577`; its prompts move behind
  the `Prompter` in W1.2).
- `-o -` (stdout): the review needs the screen, so `-o -` implies `--no-input`.
- `decoy init --review-findings PIPELINE --report FILE` in a terminal; off a TTY or with `--json` only
  with `--answers` (finding decisions), else exit 1 naming `--answers`.
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
  `model`; the report gains `config_sha256` and `tables_checked` (4.5).
- `StrategyOption`: `name`, `wire_type`, `required`, `location`, `choices`, `example`; `StrategyInfo`:
  `name`, `namespace_required`, `join_safe`, `options`, `offer_in_wizard`, with required names and
  example values derived from `options` (4.6, part E0).
- Answers model (`decoy-init-answers/v1`): `schema`, `sources` (`path`, `has_header`,
  `column_names`), `detectors`, `tables` (name to column to a verdict, or to `{verdict, source,
  detector_id, model, strategy}` for a confirm, or `{verdict: edit, entry}`), `unlisted`,
  `targets_dir`, `mask_secret_ref`, and for findings `findings` (table to column to detector to a
  verdict, or `{verdict: edit, entry}`).
- `--json` record (today `init.py:481`): `command`, `status`, `out`, `source`, `mode`,
  `column_count`; the wizard adds `reviewed: {confirm, reject, edit, skip}` counts and `answers` (the
  saved path or null).

### 5.5 Output surfaces

- Terminal prompts and the column summary (stdout, Rich).
- Errors (stderr): each a fixed code plus names; exception class only, never `str(exc)`.
- `--json` record (stdout) and `-q` (nothing on success).
- The written pipeline YAML, REVIEW notes included.
- The answers file written by `--save-answers`.
- The unified diff preview in post-scan review. A pipeline YAML can hold literals the user wrote
  (`provider_config` values, category lists, `when` literals), so the diff can show them. It is shown
  only to the operator who owns the file, in the terminal, which the V1 threat model allows; it never
  goes to `--json`, logs or the answers file.
- Logs at `-v` (stderr): which sections ran, counts, detector and model names (SCAN-ML log lines).
- Help text and epilog (`init.py:34`), including the removal of "STORM" from user-facing text (spec
  section 12).
- Answers-file parse errors (pydantic): routed through the VALUE-FREE-ERRORS converter (roadmap 24a)
  or, if that has not merged, `hide_input_in_errors=True` plus code and location only.

## 6. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | prompts, summary, notes, answers file, `--json`, errors, logs | Suggestions and findings arrive value-free from the engine (`ScanSetCore`, `StarterConfig.notes`, the report's per-finding fields minus `message`); errors are fixed codes plus names through the value-free converter; right-hand values of an answers file are never echoed; the diff preview goes only to the terminal (5.5) | AT-W8 seeded canary corpus through every surface in every route; sentry `test_wizard_no_exc_text.py` over `cli/wizard/` and `cli/init.py`, resolving calls through G-ONE-GATE's import-table resolver: `str(exc)`, `repr(exc)`, `format(exc)`, f-strings and `%` formatting of a caught exception, `exc.args`, `traceback.format_exc`, `traceback.print_exc`, `logger.exception`, `log.*(exc_info=...)` | M-W8a: a note quotes a top value; M-W8b: an error prints `repr(exc)`; M-W8c: an answers error echoes the strategy value |
| 2 | Cleanup missing on an exit path | cancel, `q`, scan failure, write failure, gate refusal, answers write failure | Nothing is written until the single write step; YAML then answers file, each through `_atomic.write_local_target`, which removes its temp file on every failure; an answers failure after the YAML names both outcomes | AT-W10 exit-path matrix: Ctrl-C, EOF, `q`, scan error, `_atomic` failure on the YAML, on the answers file, gate refusal, YAML changed; asserts which files exist after each, and no temp file | M-W10: write the answers file before the YAML write succeeds |
| 3 | State machine and concurrency | review state per item; duplicate decisions; several findings on one column; YAML changed during post-scan review | Both review functions are pure folds with no hidden state; duplicate keys in an answers file are refused at load by the shared mark index (PyYAML alone keeps the last one); duplicate decisions are refused; `finding_edits` groups by column, emits one final entry and binds dismissals to it; the editor compares the file hash read at load with the bytes just before replace | AT-W11 property: any permutation of the same pre-scan decision set gives the same config, and a file with a duplicate column key is refused; AT-E5 permutes multi-finding decisions; AT-W14 file changed between read and write is refused | M-W11a: drop the duplicate-key refusal in the loader; M-W11b: last-writer-wins in `apply_review`; M-E5c: bind a dismissal before the column's edit; M-W14: skip the hash check |
| 4 | Route parity and silent fallback | terminal, answers file, no-TTY, `--json`, `-q`, template path, findings review | One review loop over a `Prompter` interface; the answers file and the terminal are two implementations; the template path's prompts move behind it (W1.2); no `if interactive` branch in steps | AT-W3 replay parity (byte-identical YAML); AT-W4 no-TTY equals all-skip and bare `decoy init` off a TTY takes the `minimal` preset; sentry `test_wizard_prompt_boundary.py` over `src/decoy/cli/init.py` and `src/decoy/cli/wizard/` (only `_prompts.py` may call): `typer.prompt`, `typer.confirm`, `click.prompt`, `click.confirm`, `click.termui.*`, `rich.prompt.Prompt.ask`, `Confirm.ask`, `IntPrompt.ask`, `input`, `getpass.getpass`, `sys.stdin.read*`, through aliases, resolved with G-ONE-GATE's resolver | M-W3: the answers path confirms classifier suggestions on `unlisted: skip`; M-W4a: a step calls `typer.prompt` directly; M-W4b: `from rich.prompt import Confirm as C` in `_flow.py` |
| 5 | Referential integrity | review or post-scan edit of a key column (every FK shape in 5.3) | `apply_review` and `finding_edits` keep the relationship namespace and refuse a strategy the catalog does not mark `join_safe` on a key column (`config.key_column_not_join_safe`); `_KEY_STRATEGIES` derives from the same fact; REJECT keeps the key entry; the gate runs on the result | AT-W12 per FK shape, with a `decoy run` on a two-table fixture proving the join survives; a join oracle that also masks the key with a namespaced non-injective strategy and shows orphans | M-W12: let `edit` set `redact` on a composite child key; M-W12b: allow `categorical` (namespaced, not join-safe) on a parent key |
| 6 | Untrusted producer | the answers file, the integrity report, the existing YAML | Strict pydantic models at every nested wire field with `extra="forbid"`, a required schema tag and a 1 MiB cap; the report read with a 16 MiB cap and checked for schema, `tables_checked`, required finding fields and `config_sha256`; YAML read through the gate's `parse_pipeline_yaml` and indexed by the one strict mark API (`src/decoy/_yaml_marks.py`, node cap, alias and merge refusal) | AT-W5 hostile answers corpus (unknown keys, missing or wrong tag, oversize file, alias bombs, non-string keys, `yes` as a verdict, duplicate keys, wrong nested primitive types); AT-W13 hostile YAML shapes refused; AT-W20 stale, foreign or internally inconsistent report refused | M-W5: make edit entries `Mapping[str, Any]`; M-W13: accept an alias node span; M-W20: infer coverage from finding rows |
| 7 | Check then use on a path (TOCTOU) | role collision; output exists then write; YAML read then replace; a symlinked YAML | One pre-read path-role check uses `samefile` for existing paths and resolved parent plus name for absent targets; output uses `_atomic` (`CREATE_ONCE` when `--yes` is absent and the file did not exist at start); answers always use `CREATE_ONCE`; post-scan replace re-reads and compares the hash immediately before the replace; a symlinked pipeline is refused; the replace keeps the original mode. Residual window accepted for a single-operator CLI (SCAN-MULTI precedent) | AT-W14; AT-W21 symlink refused and mode kept; AT-W22 collision matrix | M-W14 (as row 3); M-W21: replace without the mode argument; M-W22: compare raw path strings only |
| 8 | Weak tests and overclaimed evidence | every acceptance test | Each acceptance test names its mutation (section 7) and a real oracle (a `decoy run`, an explicit namespace assertion, a comment-survival check), not only the gate, which misses missing namespaces | Reviewer reruns the named mutations on the final head | removing any named mutation from the evidence record is a gate finding |
| 9 | Behavior-preserving refactor drift | `decoy init --preset`, `decoy init FILE` with no answers, `ci/locations.py` after its index moves | Characterization tests first: today's preset output and the S3a.1 `decoy init FILE` output are pinned before W1.2 edits `init.py`; `ci/locations.py`'s existing tests pass unchanged after W1.1 moves its index | AT-W1 characterization; the existing `tests/` for `ci/locations` at W1.1 | M-W1: change the default preset; M-W9b: change the semantic-path spelling in the moved index |
| 10 | Frozen contract drift | CLI flags, exit codes, `--json` keys, engine public API, `PipelineConfig`, the answers schema | Additive only: new flags, new `--json` keys, new engine exports; the six exit codes unchanged; no config field added by this plan (SCAN-ML adds the detector fields and `post_scan.dismissed`); `decoy-init-answers/v1` frozen at W2, once SCAN-ML's detector names exist (W1.2 accepts no `detectors` key yet) | AT-W15 `--json` key snapshot; engine export snapshot test; answers-schema JSON snapshot at W2 | M-W15: rename `column_count` |

## 7. Acceptance tests (red first)

Written before the build steps of each part. Each test records its red run (assertion failure against
a stub) and names the mutation that must turn it red on the final head. Fixtures: a three-table set
(CSV with header, headerless CSV, Parquet) with seeded canary cells in every column, built by the
SCAN-MULTI fixture helpers.

| Id | Part | Asserts | Mutation |
|---|---|---|---|
| AT-E0a | E0 | G-CATALOG: every handler in the handler table declares `namespace_required`, `join_safe`, `wizard_options` (read into `StrategyInfo.options`) and `offer_in_wizard` itself (no inherited default), and `strategy_catalog()` has exactly one row per handler and no duplicate option name | M-E0a: remove the attributes from one handler; M-E0b: add a handler without a catalog row |
| AT-E0b | E0 | for every `offer_in_wizard` row, a column entry built from its derived `example_options` (and a namespace when required) compiles and runs on that strategy's existing minimal fixture and required context; the test asserts the offered set is non-empty. Dropping any required option fails, and a wrong exact type, unknown option, invalid choice or wrong descriptor placement is refused with `config.entry_invalid`; changing a non-offered complex strategy to offered without complete option metadata and a runnable fixture fails. `_KEY_STRATEGIES` equals the rows marked `join_safe`; a test-local mapping of each `join_safe` row on 1,000 distinct values yields 1,000 distinct outputs, and the same input twice yields the same output | M-E0c: mark `hash` `namespace_required: false` (its run fails with `hash_requires_namespace`); M-E0d: mark `categorical` `join_safe`; M-E0e: move `truncate.length` to the column level; M-E0f: mark `tokenize` offered |
| AT-E1 | E1 | `apply_review` over every verdict for a column with one regex suggestion gives: confirm = the suggestion entry, reject = `redact` with the rejected note, edit = the given entry, skip = unchanged entry and note; the result validates and compiles | M-E1a: reject keeps the suggestion entry |
| AT-E2 | E1 | a classifier suggestion is never live in `starter_config` output and becomes the column entry only on a confirm whose `SuggestionRef` matches it | M-E2: mark classifier suggestions live |
| AT-E3 | E1 | unknown column, duplicate decisions and a confirm with no matching suggestion raise with their codes; the message names the column, never a value; `__cause__` and `__context__` are `None` | M-E3: silently ignore unknown columns |
| AT-E4 | E1 | property (Hypothesis, fixed seed): for random decision sets over the fixture starter (edits drawn from the `offer_in_wizard` rows with their `example_options`), the result validates and compiles, every column not named keeps its starter entry, and every entry whose strategy is `namespace_required` has a namespace (explicit assertion; the gate does not check this) | M-E4: `column_entry` skips the namespace for an edit to `hash` |
| AT-E5 | E2 | `finding_edits`: confirm on an unmasked column yields one `replace` built by `column_entry`; reject on a warning detector match yields one `append` (or `append_block` with no `post_scan:`) with every dismissal field; reject on a `fail` or identity finding raises `post_scan.dismiss_refused`; skip yields none; a repeat reject yields none. Property (Hypothesis, fixed seed): permutations of decisions for several findings on one column produce the same single replacement and dismissals bound to its final strategy; conflicting entries, unknown identities and duplicate identities are refused | M-E5a: reject edits the column; M-E5b: allow dismissing a `fail` finding; M-E5c: create dismissals before folding the column edit |
| AT-W1 | W1.2 | characterization: `--preset` outputs and non-interactive `decoy init FILE` output equal the pinned bytes | M-W1 |
| AT-W2 | W1.2 | scripted terminal session over the fixture: the YAML reflects each verdict typed, and `a`, `d`, `q` cover the right items; `a` is accepted only after the table summary has printed. Runs through a pty on the Linux and macOS lanes; the Windows lane runs the same script through the scripted `Prompter` | M-W2a: `d` skips the whole run instead of the table; M-W2b: offer `a` before the summary |
| AT-W3 | W1.2 | `--save-answers A` from the AT-W2 session (the header flag answered by prompt; columns named `yes`, `null`, `on`), then `--answers A --no-input`: byte-identical YAML | M-W3; M-W3b: save names unquoted |
| AT-W4 | W1.2 | with no answers, both asymmetric non-terminal cases (stdin not a TTY, and stdout not a TTY) never call a prompt, including the existing-output question; project YAML equals the S3a.1 unreviewed starter; a missing header flag exits 1 naming the flag before any read (spy on `scan_sources`); bare `decoy init` in either case writes the `minimal` preset in default mode (the non-terminal stream is left open so a prompt would hang) | M-W4 |
| AT-W5 | W1.1 | hostile answers corpus: each case exits 1 with its code; key paths are named, no right-hand value is echoed (a canary strategy value is absent from stderr), nothing written. For every nested primitive field, bool-as-int, numeric string and wrong type are refused; every converted safe exception has `__cause__ is None` and `__context__ is None` | M-W5; M-W8c |
| AT-W6 | W1.1 | the strategy list at an `edit` prompt equals `strategy_catalog()` names; each option prompt, exact parser type and choices equal the catalog descriptor, and the produced entry uses its declared location; sentry fails on a literal tuple, list or set of two or more catalog strategy names in `cli/wizard/` | M-W6: hard-code the list; M-W6b: parse every option as text |
| AT-W7 | W1.2 | for a seeded sample of 200 verdict sequences over the fixture (edits sampled from the `offer_in_wizard` rows with their `example_options`), the reviewed config passes the gate in-process and has a namespace on every `namespace_required` entry; for 5 of them, `decoy run` on a tiny fixture exits 0 | M-E4 |
| AT-W8 | W1.2, W2, W3.2 | canary corpus: no canary in stdout, stderr, `--json`, the YAML, the answers file or `-v` logs, on every route in 5.2; non-vacuity: the same corpus is found in the raw fixture bytes | M-W8a, M-W8b, M-W8c |
| AT-W9 | W1.2 | every exit path in 5.1 prints exactly one error line in default mode, and none of the lines holds a canary | M-W9: restore the `is not OutputMode.default` guard |
| AT-W10 | W1.2 | exit-path matrix (class row 2), plus a preflight error (a capacity or missing-companion finding injected into the gate): the YAML is written, `--json` shows `status: "written"` and `gate.errors`, and the exit code is the one `gate_exit_code` gives | M-W10; M-W10b: skip the write on a preflight error |
| AT-W11 | W1.1 | permutation property and duplicate-key refusal (class row 3) | M-W11a, M-W11b |
| AT-W15 | W1.2 | `--json` key snapshot and engine export snapshot | M-W15 |
| AT-W19 | W1.2, W2 | stale confirm: replay a saved answers file after changing the regex fixture so the column's suggestion changes, and (W2) after bumping the classifier model version in the fixture manifest; both exit 1 with `pre_scan.review_stale` naming the column and the field; the short form `email: confirm` on a column with two suggestions exits 1 | M-W19: match a confirm by source only |
| AT-W16 | W2 | detector step writes SCAN-ML's pre-scan and post-scan fields exactly as chosen; NER not installed: terminal offers to continue, non-interactive exits 1 naming the install command | M-W16: write NER into the config when it is not installed |
| AT-W17 | W2 | a classifier suggestion is shown with its model id, version and band, applied only on a matching confirm, and the YAML note names the model | M-E2 |
| AT-W12 | W3.2 | per FK shape (5.3): confirm and edit on a key column keep the namespace, a strategy not marked `join_safe` (`redact`, and `categorical` with a namespace) is refused with `config.key_column_not_join_safe`, reject keeps the key entry; `decoy run` on the edited two-table fixture exits 0 and every masked child key still joins a masked parent key | M-W12 |
| AT-W13 | W3.1 | `_yaml_edit` over a corpus (comments between entries and after the last entry, a table-level comment after the last column, blank lines, CRLF, BOM, last entry without trailing newline, unicode names, quoted keys, block scalars `|`, `|+` and `>-` as the last value, a multi-line quoted scalar, an entry at end of file with no newline): every comment line of the original except the edited entries' REVIEW notes survives in order (checked from the two texts, not from the span), every byte outside them is unchanged, and the re-parsed dict differs only at the edit paths; anchors, aliases, merge keys, flow-style entries, duplicate keys and comments inside the entry are refused | M-W13a: accept an alias node span; M-W13b: skip the structural check; M-W13c: use the mapping's own `end_mark` as the span end; M-W13d: end a block-scalar span on the end mark's line at column 0 |
| AT-W14 | W3.1 | the YAML is changed between read and replace: refused, the file holds the second writer's bytes | M-W14 |
| AT-W18 | W3.2 | reject on a warning finding writes a dismissal with every field; the next `decoy run` reports it as `info` (needs the SCAN-ML dismiss part); after the column's strategy changes, or the model version changes, it is reported at its own severity again; a `fail` finding cannot be rejected; a second review, against a fresh report from a re-run on the edited YAML, adds nothing; a review against the old report after a write is refused (`init.report_stale`, its `config_sha256` no longer matches), so a partial review is resumed only from a fresh report | M-W18a: append twice on repeat review; M-W18b: match a dismissal without the strategy |
| AT-W20 | W3.2 | a report with another schema, no `config_sha256`, no `tables_checked`, duplicate checked tables or findings, a finding outside `tables_checked`, or a hash of an older YAML is refused with its code; a fresh report with one clean checked table and no finding row reports that table as covered; a table absent from `tables_checked` is reported uncovered | M-W20: derive coverage from finding rows |
| AT-W21 | W3.1 | a symlinked pipeline is refused and the link and its target are unchanged; a 0644 pipeline is still 0644 after an edit | M-W21 |
| AT-W22 | W1.2, W3.2 | before the source-read spy fires, refuse each pair of colliding read/write roles, including lexical aliases, a symlink and a hard link: output/source, output/answers input, output/answers output, answers output/source, answers output/answers input, and on the findings route pipeline/report/answers collisions. An existing `--save-answers` file is unchanged even with `--yes`; distinct sibling paths proceed | M-W22: compare raw path strings only; M-W22b: write answers with `REPLACE` |
| G-ONE-EMITTER | W1.2 | SCAN-MULTI's guard extended: the wizard's write and the editor's entry text reach `_scaffold_yaml`; no other module under `src/decoy/` emits pipeline YAML text | M-EMIT-W: the wizard writes `yaml.safe_dump` output |
| G-ONE-EDITOR | W3.1 | sentry using G-ONE-GATE's import resolver: `_yaml_marks.py` is the only module that calls `yaml.compose` under `src/decoy/`, including `import yaml as y`, `from yaml import compose as c`, and unbound aliases; only `cli/wizard/_yaml_edit.py` writes text derived from an existing pipeline YAML (resolved writes: `_atomic` calls, `Path.write_*`, `open(..., "w")` in modules that read a pipeline path). A seeded case for each listed spelling must fail | M-EDIT: post-scan review re-renders the whole file; M-COMPOSE: `from yaml import compose as c` followed by `c(text)` in `_yaml_edit.py` |

## 8. Hostile corpus (ways a gate reviewer breaks it)

The plan contract section 4 asks for these; each is an acceptance test above.

1. Answers file whose verdict or strategy value is a canary, expecting it echoed in the error (AT-W5).
   Key paths are names and are shown by owner rule; values are not.
2. A column named `yes`, `null`, `#id` or `a: b` reviewed through `edit` (renderer quoting, AT-W13).
3. A classifier suggestion confirmed by `unlisted: skip` through a default (AT-E2, M-W3).
4. `q` at the first prompt, then a write that still applies suggestions (AT-W2); or `a` pressed
   before the summary was shown (AT-W2).
5. Ctrl-C after `--save-answers` was given, leaving a half answers file (AT-W10).
6. Off-TTY run that blocks on a prompt (AT-W4, class row 4 sentry).
7. A post-scan edit that turns a composite child key into `redact` (AT-W12).
8. A pipeline file whose column entry is an alias of another (AT-W13).
9. The user edits the YAML in an editor while the review runs (AT-W14).
10. The scan error text carrying a cell value printed at default verbosity (AT-W8, AT-W9).
11. A model upgrade, then CI replays a saved `confirm` (AT-W19).
12. A post-scan edit deletes the next column's REVIEW comment (AT-W13, M-W13c).
13. `e` to `hash` with no namespace: the gate is green and `decoy run` exits 3 (AT-E4, AT-W7).
14. Reject a `fail` finding and the leak reads as `info` forever (AT-E5, AT-W18).

## 9. Owner questions (each answerable alone; recommended answer first)

- **Q1. How is the post-scan review spelled?** Recommended: `decoy init --review-findings
  pipeline.yaml`. Alternatives: `decoy review pipeline.yaml` (a new verb) or `decoy init findings
  pipeline.yaml` (the draft spec's section mode). Builders proceed with the recommended form; a rename
  is one Typer option.
- **Q2. Does rejecting a post-scan finding persist?** Recommended: yes, as a `post_scan.dismissed`
  entry in the pipeline YAML, so the next run reports it as `info` instead of warning again. The
  entry names the table, column, detector, source, model and the column's strategy; it never lowers a
  failed mask check and stops applying when the strategy or the model version changes (4.6). Without
  it, rejecting a finding changes nothing.
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
| Strategy list and options | the private handler table `execution/_strategies/__init__.py:44`; no public catalog and no options metadata exist | E0 adds `strategy_catalog()` from per-handler attributes; the `edit` prompt and `column_entry` read it |
| Column entry building | `init.py:184` `_emit_column_yaml` (namespace for `_NAMESPACE_REQUIRED_STRATEGIES`, `init.py:180`) | becomes engine `column_entry` (E1), used by `starter_config`, `apply_review` and `finding_edits` |
| YAML node marks for the pipeline text | `src/decoy/ci/locations.py:1` (compose pass, path resolution, alias, merge and duplicate refusal, node cap) | moved to `src/decoy/_yaml_marks.py` in W1.1; `ci/locations.py`, the answers loader and `_yaml_edit.py` share it |
| Join-safe key strategies | `execution/_sequential_native.py:129` `_KEY_STRATEGIES = (HASH, FPE)` | derived from the catalog's `join_safe` in E0; the key-column rule reads the same fact |
| AST call resolution for sentries | `tests/sentry/test_gate_single_entry.py` (import-table resolver) | the new sentries reuse it, not a new scanner |
| Post-scan findings | `post-scan-integrity/v2` report (`verification/postmask/types.py:17`), written by `decoy report integrity --output` (`report.py:1949`, write at `:2092`) | the `--report` input of W3.2 |
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
| `cli/wizard/_findings.py` (W3.2) | same | same | |
| `cli/wizard/_yaml_edit.py` (W3.1) | same | same | |
| `src/decoy/_yaml_marks.py` (W1.1) | `src/decoy/` | "Private shared filesystem or process primitives used by more than one package" (used by `ci/` and `cli/wizard/`) | `src/decoy/_atomic.py` |
| `tests/sentry/test_wizard_prompt_boundary.py`, `test_wizard_no_exc_text.py`, `test_one_editor.py` | `tests/sentry/` | "Repository policy sentries and their scanners" | `test_gate_single_entry.py` |
| engine `profiling/starter_review.py` | `src/decoy_engine/profiling/` | engine CODEMAP Directory Map, `profiling/` row (profiling and detector suggestions; the engine map has no "Where things go" section until LAYOUT E1) | `profiling/starter_config.py` (SCAN-MULTI S3-engine.2) |
| engine `tests/unit/profiling/test_starter_review.py` | engine `tests/unit/profiling/` | same convention as SCAN-MULTI's `test_starter_config.py` | |
| engine `tests/unit/test_strategy_catalog.py` (E0) | engine `tests/unit/` | beside the existing strategy handler tests | |

E0 adds no module: the four attributes go on the existing handler classes, and `strategy_catalog()`
lives in `execution/_strategies/__init__.py` beside `SCALAR_HANDLERS` and is re-exported from
`decoy_engine/__init__.py` (an export line, a keep-both ledger line per owner 2026-11-06). The frozen
`execution/` package therefore gains no module.

Fan-out: `src/decoy/cli/wizard/` holds 7 modules at most; `profiling/` holds 10 entries today.
Sizes: every new file under 400 lines; `cli/init.py` must not grow past its S3a.1 size (about 300):
W1.2 moves the review body into `cli/wizard/_flow.py` and leaves `init.py` the option wiring.

## 12. Frozen contracts touched

- CLI flags of `decoy init`: additive (`--answers`, `--save-answers`, `--no-input`,
  `--fail-on-warning`, `--review-findings`, `--report`). Behavior changes, pre-GA (CLI `CLAUDE.md`:
  hard delete): a terminal `decoy init FILE` now prompts for review (scripts off a TTY get the
  unreviewed starter, as today); bare `decoy init` off a TTY in default mode now writes the `minimal`
  preset instead of prompting (4.1).
- Exit codes: the six public codes only (`src/decoy/cli/exit_codes.py`), no new code.
- `--json` record of `init`: additive keys `reviewed`, `answers`.
- New file format `decoy-init-answers/v1`: new, versioned by its schema tag; a later breaking change
  takes `v2`.
- Engine public API: additive exports `StrategyOption`, `StrategyInfo`, `strategy_catalog` (E0); `ModelRef`,
  `SuggestionRef`, `ReviewVerdict`, `ReviewDecision`, `column_entry`, `apply_review`,
  `ReviewInputError` (E1); `FindingDecision`, `ConfigEdit`, `finding_edits` (E2); the full
  `ColumnSuggestion` field set of 4.6. Compatibility contract note in engine
  `docs/compatibility-contract.md`. Each strategy handler gains four class attributes (internal).
- `post-scan-integrity/v2` report: SCAN-ML M4 adds `config_sha256`, `tables_checked` and per-finding
  `source` and `model` (additive). The tag stays v2: the platform stores the report as opaque JSON and
  the CLI only dumps it (SCAN-ML 4.5 records the check).
- `PipelineConfig`: untouched by this plan. The detector fields and `post_scan.dismissed` belong to
  SCAN-ML.
- Error codes. Engine (`ReviewInputError`, reason identities claimed through REG-RENUMBER at merge),
  each in an existing family of `decoy_engine/reasons/`: `pre_scan.review_unknown_column`,
  `pre_scan.review_duplicate`, `pre_scan.review_stale`, `config.entry_invalid`,
  `config.key_column_not_join_safe` (E1), `post_scan.dismiss_refused` and
  `post_scan.review_conflict` (E2). CLI-only, in the
  CLI's existing fixed-code convention: `init.answers_invalid`, `init.yaml_changed`,
  `init.yaml_edit_unsupported`, `init.yaml_symlink`, `init.report_missing`, `init.report_schema`,
  `init.report_stale`, `init.path_collision`.

## 13. Slices

Sizes are hand-written lines (source + tests + docs), estimated. Every part stays under about 800.

| Part | Repo | Lines | Contents | Depends on |
|---|---|---|---|---|
| E0 | engine | ~540 (190 + 320 + 30) | four class attributes on each of the 25 strategy handlers, `StrategyOption`, `StrategyInfo`, derived required/example views, `strategy_catalog()`, export; `_KEY_STRATEGIES` derived from `join_safe`; G-CATALOG; AT-E0a, AT-E0b | none (engine main) |
| E1 | engine | ~640 (280 + 330 + 30) | `starter_review.py`: `SuggestionRef`, `ModelRef` in `detection/types.py` unless SCAN-ML M1 added it first, verdict enum, `ReviewDecision`, `column_entry`, `apply_review`, `ReviewInputError` and its reason identities; the full `ColumnSuggestion` fields and `StarterConfig.suggestions`; `starter_config` builds entries through `column_entry`; AT-E1 to AT-E4 | E0; SCAN-MULTI S3-engine.2 merged |
| W1.1 | CLI | ~760 (400 + 330 + 30) | `src/decoy/_yaml_marks.py` (index moved from `ci/locations.py`, which keeps its names; its tests pass unchanged); `cli/wizard/` package: `_prompts.py` (Prompter protocol, terminal and answers implementations, key table), `_answers.py` (model, strict loader, save with quoted names), `_review.py` (per-table loop over a Prompter); CODEMAP row; sentries for prompt boundary, no exception text, no strategy literal (on G-ONE-GATE's resolver); AT-W5, AT-W6, AT-W11 | E0 and E1 released and repinned |
| W1.2 | CLI | ~780 (300 + 440 + 40) | `cli/wizard/_flow.py` (sections, path-role check, write step, gate); `init.py` rewired to it, template prompts moved behind the Prompter; `--answers`, `--save-answers`, `--no-input`, `--fail-on-warning`; stale-confirm check; G-ONE-EMITTER extended; CHANGELOG, `docs/cli-reference.md`; AT-W1 to AT-W4, AT-W7 to AT-W10, AT-W15, AT-W19 (regex half), AT-W22 (project route) | W1.1; SCAN-MULTI S3a.1 merged (renderer and the `init` rewrite) |
| W2 | CLI | ~460 (170 + 260 + 30) | detector section (pre-scan and post-scan choices, NER availability, the SCAN-ML install command), model and band in the summary, `detectors` in the answers schema (frozen here, snapshot); AT-W16, AT-W17, AT-W19 (model half), AT-W8 for this route | W1.2; SCAN-ML engine parts with the config fields, classifier suggestions and the NER availability probe, released and repinned |
| E2 | engine | ~420 (180 + 210 + 30) | `FindingDecision`, `ConfigEdit`, order-independent `finding_edits` with the dismissal and key-column rules; AT-E5; FK-shape cases for AT-W12 at engine level | E1; SCAN-ML M1 (`post_scan.dismissed`) and M4 (the report's `source`, `model` and `tables_checked`) |
| W3.1 | CLI | ~540 (200 + 310 + 30) | `cli/wizard/_yaml_edit.py`, the `mode` argument of `_atomic.write_local_target`; G-ONE-EDITOR; AT-W13, AT-W14, AT-W21 | W1.2 |
| W3.2 | CLI | ~590 (220 + 340 + 30) | `cli/wizard/_findings.py`, `--review-findings`, `--report`, findings in the answers schema; AT-W12, AT-W18, AT-W20, AT-W22 (findings route), AT-W8 for this route | W3.1; E2 released and repinned; SCAN-ML's report changes (`config_sha256`, per-finding `source` and `model`) |

Which parts need what:

- Need nothing: E0 (it can build now, from engine main).
- Need SCAN-MULTI S3 (`starter_config`): E1 (S3-engine.2), W1.2 (S3a.1). W1.1 needs E0 and E1.
- Need SCAN-ML: W2 (detector fields, classifier suggestions, NER probe), E2 and W3.2 (dismiss field,
  report `config_sha256`, per-finding `source` and `model`). E0, E1, W1.1, W1.2 and W3.1 work with
  regex suggestions only, so the wizard ships its core and its editor before SCAN-ML.
- Shared files: `cli/init.py` is written by S3a.1 then W1.2 (one writer at a time, after S3a.1
  merges). `profiling/starter_config.py` is written by S3-engine.2, then E1, then SCAN-ML.
  `ci/locations.py` is written by W1.1 only (behavior-preserving move). `_atomic.py` gains one
  argument in W3.1. E0 replaces SCAN-MULTI's namespace-strategy copy in
  `profiling/recommendations.py` and `_starter_inference.py` if S3-engine.1 merges first.

Test depth per part: T0 per edit, T1 impact-selected per commit (`scripts/dev/gates.sh --baseline`).
Escalation triggers: E0, E1 and E2 change engine public exports (frozen contract surface) and E1 and
E2 touch the reason registry; W1.2, W2 and W3.2 repin the engine; W1.1 moves code under the CI
location sentries; W3.1 changes `_atomic.py`, a shared primitive. Each of those merge heads gets the full suite
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
- **SCAN-MULTI S3 or SCAN-ML slips.** E0 needs nothing; E1, W1.1, W1.2 and W3.1 need only S3; W2,
  E2 and W3.2 wait for SCAN-ML. The roadmap row stays in progress until W3.2 lands.
- **Builders re-litigate scope.** Non-goals in section 1 and the follow-up row INIT-WIZARD-2 for the
  draft spec's other steps.

## 16. Follow-ups (recorded, not in V1)

- INIT-WIZARD-2: relationships, subset, checks and CI steps; section mode for every block; drafts and
  `--resume`.
- A `decoy validate` warning when REVIEW notes remain (spec section 8).
- Arrow-key prompts behind the same `Prompter` interface, if users ask.
