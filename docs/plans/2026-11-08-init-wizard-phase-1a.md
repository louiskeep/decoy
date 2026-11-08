Status: plan

# INIT-WIZARD Phase 1a: the first `decoy init` wizard (CLI roadmap row 32b)

Owner: Cam. Author: Opus (plan author, CLI). Date: 2026-11-08. Scope: CLI V1 Phase 1a, two engine
parts.

This plan revises the reviewed plan `docs/plans/2026-11-07-init-wizard.md` (two Dennis rounds, a
Codex confirm, owner answers Q1 to Q3 on 2026-11-07) to the Phase 1a scope of spec v3
`docs/plans/2026-10-30-init-wizard-spec.md` (CLI #119). The 2026-11-07 plan stays on this branch as
the record (`Status: record`). Its shapes in sections 4.6 and 4.7, its class table and its later
parts (E2, W2, W3.1, W3.2) remain the reference for the later phases until their own revisions. Where
this plan restates or amends one of them, this plan wins for Phase 1a.

Bases: CLI `origin/main` `08124b5` (#119), engine `origin/main` `38951412` (#405), both read
2026-11-08. Engine branches read: `plan/scan-multi`, `plan/scan-ml`; local CONFIG-EXPLICIT E1 work in `/home/cam/vscode/wt-cfgexp-e1`
(`feat/config-explicit-e1-schema`, not pushed).

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`,
`development-loop.md` (PLAN), `profiles/local-operations.md`, `feature-dev.md`,
`api-and-compatibility.md`, `cross-cutting-concerns.md`, `reuse-first.md`, `architecture.md`,
`testing.md` (Test depth), `code-review.md`, `security.md`, `observability-and-resilience.md`,
`config-secrets-and-supply-chain.md`, `catalogs/recurring-defects.md`, `workspace-and-vcs.md`
(Commit messages), `documentation.md`. Also CLI
`CODEMAP.md`, `docs/ROADMAP.md` row 32b and section 5.2, and spec v3 sections 0, 11, 12, 15, 16, 17
and 22.

Revision 1 (2026-11-08): Dennis round 1 on `2e09ff7` (NO-GO, 2 HIGH, 10 MEDIUM, 12 LOW). Applied in
place: the header file gets a path role (H1); `d` on a table's last kept field is refused (H2); one
gate write classifier in `cli/gate/` (M1); slice order and sizes (M2, M3); reuse of the mask-secret
guidance module and the shared call scanner (M4, M5); an owner for the engine "STORM" note text
(M6); a pinned keyed-columns oracle (M7); a buildable 14.3 fallback (M8); one value-shape rule (M9);
the `init.py` size pin before growth (M10); and the LOW items (section 19).

Revision 2 (2026-11-08): Dennis round 2. Corrected exit-code coverage, the golden-diff allowance,
read and write path-role collisions, `apply_review` failure handling, prerequisite state, slice
ordering, the V1 no-relationships boundary, gate-path output, and the deferred missing-extra case.
The final self-review also corrected two unbuildable test clauses and centralized CLI-facing reason
codes under the standing design rule. Section 19 records each resolution.

Risk: R2. Phase 1a changes a public CLI command (`decoy init`), adds public engine API, and its
output must stay value-free. It writes only a file the user named, through the atomic writer, after
a confirm. Approver: Cam.

## 0. What changed from the 2026-11-07 plan

| Topic | 2026-11-07 plan | This plan (spec v3) |
|---|---|---|
| Scope of the first phase | W1.1 and W1.2: review the starter's columns, answers files, no-TTY parity | Phase 1a only: Start, Goal (Mask), local Sources, Scan, Fields (every field), local Output, Secrets, Review. Answers files move to Phase 2 |
| Field review keys | `git add --patch` keys `y n e s a d q` | v2 keys: Enter, `r`, `o`, `k`, `d`, `b`, `q` (owner, 2026-11-08), plus `g`, `l`, `s`, `?` |
| No terminal | the wizard falls back to the unreviewed starter; bare init takes `minimal` | three-row rule (spec 11): default mode refuses with exit 1, explicit one-shot flags keep today's output. AT-W4 amended |
| Navigation | one pass, section by section | back, forward and go-to with `WizardState`, answer origin, stable ids and `stale()` per step |
| Strategy choice at `edit` | flat catalog list | the strategy tree (spec 5.4.3), built from `strategy_catalog()` and the provider registry |
| Secrets | `mask_secret_ref` only when keyed, from the CLI | `secret_requirements_for_config` plus the new engine `keyed_columns_for_config` (spec 16.12, part E3 here) |
| Verdict set | confirm, reject, edit, skip | the same plus `drop` (part E1 amended, 6.1), because the `d` key writes a `drop_column` transform |
| `--fail-on-warning`, `--answers`, `--save-answers` | W1.2 | Phase 2, with the scripted wizard path |
| CLI slice count | spec 17 calls Phase 1a "one CLI slice" | this plan amends spec 17: Phase 1a ships as eleven CLI slices of about 300 to 700 lines each (section 11), because one slice would be several thousand lines |
| Shared YAML mark index `_yaml_marks.py` | W1.1 | Phase 2, with the editor and the answers loader, its first users |

## 1. Scope

### 1.1 In Phase 1a

1. `decoy init` and `decoy init FILE` in a terminal run the wizard. The steps are Start, Goal,
   Sources, Scan, Fields, Output, Secrets and Review (spec 5.0 to 5.4.3, 5.9 to 5.11, cut to 1a).
2. Start offers two choices: a new pipeline from data files (default), or a preset. The preset path
   asks today's preset questions through the `Prompter`, with no change to the YAML it writes.
3. Goal is Mask only. The step prints one line ("Goal: mask. Generate, subset and tokenize come in
   later releases.") and asks nothing.
4. Sources: local files only. CSV (comma), TSV, delimited with another one-character delimiter, and
   Parquet. Column names from the first row, from a header file, or typed in. `has_header` is always
   written. A parsed preview of the first three records, and a table name.
5. Scan over every source through SCAN-MULTI `scan_sources` and `starter_config`, with a summary
   table. Labels and confidence follow spec 5.3.
6. Fields in every-field mode, one field at a time, with the strategy tree and catalog options.
7. Output: local files, CSV or Parquet, one target per table.
8. Secrets: seed and mask secret reference, from the engine's keyed-ness functions.
9. Review: summary, view YAML, final validation through the one gate, write, checklist of skipped
   steps, the next command.
10. The no-terminal three-row rule and the new `--no-input` flag.
11. `--no-samples` (value shapes instead of sample values in the parsed preview and field screens).
12. `TRANSFORM_IDS` in `cli/completers.py` replaced by `strategy_catalog()`, and the CLI's
    `_NAMESPACE_REQUIRED_STRATEGIES` deleted in favour of the catalog's `namespace_required`.
13. Sentries: prompt boundary, no exception text, no strategy literal, reason-code guard, "STORM" text,
    module size.

### 1.2 Deferred to Phase 1b

- Fixed-width sources and targets; S3 and GCS sources and targets without credential prompts.
- Flagged-only field review with the guard of spec 5.4.1 (needs engine gap 16.14), and its Review
  confirm for unreviewed `passthrough` fields (owner answer kept, section 15).
- Checks (post-scan, validators, quarantine with the H1 rules, `column_in_set` with the H2 rule) and
  Quality.
- Drafts, `q` as "save draft and quit", `--resume`, `_safe_profile.py`, `_gitignore.py`.
- Before and after previews, once engine gap 16.1 exists.
- Preset pre-fill of the wizard steps (spec 5.0 "a preset pre-fills the steps"). In 1a the preset
  path is today's template questions.

### 1.3 Deferred to Phase 2 and later

- Phase 2: `decoy edit` and the editor (`_yaml_edit.py`, `_yaml_marks.py`), Relationships, Subset,
  the Generate and Subset goals, generated tables, `--answers`, `--save-answers`,
  `--fail-on-warning`, `--skip`, `--only`, `--no-validate`, `--diff`.
- Phase 3: `prompt_toolkit` completion and arrow keys, the CI manifest, the Tokenize goal.
- Not phased by the spec, kept from the 2026-11-07 plan: W2 (detector section, needs SCAN-ML), E2
  and W3.1, W3.2 (post-scan findings review). Their command home is open (section 14).

### 1.4 Guarantee (what Phase 1a promises)

1. **Every field is shown and decided once.** In a terminal, each table's fields are walked one at
   a time. A field the user did not reach (because of `s`) keeps exactly the entry `starter_config`
   wrote, with its `# REVIEW:` note, and the checklist names it.
2. **No prompt without a terminal.** The three-row rule in 5.2 holds on every route. No code path
   off a terminal calls a prompt function.
3. **Nothing is written before Review.** Ctrl-C, EOF and `q` at any step exit 1 and leave no file
   and no temp file.
4. **One writer per kind of write.** The pipeline YAML text comes only from
   `cli/_scaffold_yaml.render` (G-ONE-EMITTER). File output is written only through
   `src/decoy/_atomic.py`; `-o -` performs its final sink emission only after Review and the gate,
   and never creates a temp file. Review `y` may display an in-session preview from the same
   renderer without opening either sink.
5. **Source-cell-value-free outside the terminal screen.** Sample cell values appear only in the
   parsed preview and the field screen, on stdout, and not with `--no-samples`. No source cell or
   secret value reaches the pipeline YAML, `-v` logs, `--json`, stderr or re-shown engine error
   text. Counts, names and detector ids are allowed metadata.
6. **The wizard never writes a config the gate's config or compile layer refuses, or one that fails
   at run time for a missing namespace.** Every column entry is built by the engine's
   `column_entry`; the folded config passes `run_gate_on_config` before the write, and one
   classifier in `cli/gate/` (5.6) decides from each finding's `layer` whether the write may go
   on. A config or compile error is a builder bug: exit 3, nothing written. Preflight findings,
   capacity included, describe this machine, not the config, so the YAML is still written and the
   findings are shown (exit 0, spec 14).
7. **Keyed-ness comes from the engine only.** The Secrets step asks for a mask secret exactly when
   `secret_requirements_for_config` reports a requirement and names exactly the fields
   `keyed_columns_for_config` returns. The CLI keeps no keyed-strategy list.
8. **A write path never aliases another role.** The write roles are the output YAML and each
   target. A write role may not name the same file as any source data file, header file
   (`column_names_file`) or other write role, and two targets may not name the same file. Read roles
   may share a file with each other. This keeps the YAML write and a later `decoy run` from
   overwriting an input (5.6). `-y` and the overwrite confirm answer only "replace the old YAML";
   they never waive a write-role collision.
9. **Every mask table keeps at least one field.** `d` on a table's last kept field is refused at
   decision time, and `apply_review` refuses an all-dropped table as the backstop (5.3, 6.1), so a
   Review write never fails on an empty table and loses the session's answers.

### 1.5 Non-goals (Phase 1a)

Everything in 1.2 and 1.3. Also: no network access; no new prompt dependency; no change to
`decoy run`, `decoy scan` or `decoy validate`; no new exit code; no new pipeline config field.

## 2. Prerequisites

Phase 1a waits for each row below. "State" was read from `origin/main` of both repos on 2026-11-08
unless the row says otherwise.

| # | Prerequisite | Roadmap row | State (2026-11-08) | Needed by |
|---|---|---|---|---|
| P1 | Strategy catalog `strategy_catalog()` (2026-11-07 plan part E0) | 32b (part E0) | MERGED (engine #400, `2335fcce`). Not in any release: `v0.19.0` (#399) predates it. The next engine release carries it, so S3a.1's repin (P8) brings it to the CLI | E1, W1a.0, W1a.3a |
| P2 | SCAN-ML M1: `ModelRef` in `detection/types.py`, config fields, model status | 32a | MERGED (engine #405, `38951412`). `ModelRef` is at `detection/types.py:42` on main | E1 (imports `ModelRef` instead of defining it) |
| P3 | CONFIG-EXPLICIT E1: `has_header` required on CSV sources, `column_names_file` | 22 | BUILDING locally (`feat/config-explicit-e1-schema` in `/home/cam/vscode/wt-cfgexp-e1`, 6 commits, not pushed; red tests in `/home/cam/vscode/wt-acct2-e1-red`) | S3-engine; W1a.4a writes `column_names_file` |
| P4 | CONFIG-EXPLICIT E2: every source column declared; `drop_column` columns count as declared (build handoff line 65) | 22 | NOT STARTED (waits on E1) | S3-engine.1; open decision 14.3 |
| P5 | CONFIG-EXPLICIT C1 and C2 (CLI loader; C2 writes `init.py`) | 22 | NOT STARTED (waits on the E1 and E2 release) | S3a.1; the `init.py` lane |
| P6 | SCAN-MULTI S1a-engine `scan_sources` | 25 | NOT STARTED (plan passed 2026-11-06) | S3-engine.1; W1a.4b |
| P7 | SCAN-MULTI S3-engine.1 and S3-engine.2: detector descriptors and `starter_config` | 28 | NOT STARTED (needs S1a and CONFIG-EXPLICIT E2) | E1; W1a.4b |
| P8 | SCAN-MULTI S3a.1-cli: `cli/_scaffold_yaml.render`, the `decoy init FILE` rewrite, G-ONE-EMITTER at renderer level, and the CLI repin to the S3-engine release (which carries P1) | 29 | NOT STARTED (needs LIB L2, the S3-engine release, CONFIG-EXPLICIT C1 and C2). `src/decoy/cli/_scaffold_yaml.py` does not exist on CLI main | every CLI slice from W1a.0 on (the `init.py` lane), W1a.6a (renderer) |
| P9 | 2026-11-07 plan part E1, amended here (6.1): `column_entry`, suggestion and decision types, `apply_review` with `drop`, `ReviewInputError` | 32b | NOT STARTED. No branch on origin and no local worktree found. The brief for this plan called this "CONFIG-EXPLICIT E1 (`apply_review`)"; the code being built now under the CONFIG-EXPLICIT E1 name is the schema slice in P3, not `apply_review` | W1a.R, W1a.3b, W1a.6a |
| P10 | New part E3 (6.2): `keyed_columns_for_config` (spec 16.12) with its oracle and parity tests, plus the 16.10 docstring fix | 32b | NOT STARTED. Has no dependency: it can build from engine main now | W1a.5a |
| P11 | Engine release R-1a carrying P7, P9 and P10 (and P1 if S3a.1's release has not shipped it) | 76 (cadence) | NOT CUT. Engine `pyproject.toml` is `0.19.0`, latest tag `v0.19.0` | W1a.R |
| P12 | CLI repin to R-1a: `pyproject.toml` pin and the engine SHA in `requirements-dev.lock`, by the engine repin checklist | 76 (cadence) | CLI pins `decoy-engine==0.19.0`, lock SHA `4a0d5b1f` | W1a.R |

Release notes for P11 and P12:

- Spec 17 names the release 0.20.0. The CONFIG-EXPLICIT E1 and E2 release is likely to take 0.20.0
  first, because C1 needs it. This plan calls the 1a release R-1a and does not fix its number.
- Best case: E1 and E3 merge before the S3-engine release is cut. Then one release carries P1, P7,
  P9 and P10, the S3a.1 repin is the 1a repin, and W1a.R shrinks to the golden update alone.
- One release and one CLI repin open at a time (roadmap 5.2 rule 3). The repin moves the lock, a
  full-suite escalation trigger, so its merge head gets the full suite diffed against the stored main
  baseline (`gates.sh --baseline-file`).
- Spec 16.8 (a public validator list) is preferred in the same release but is not a 1a
  prerequisite: Checks ships in 1b.

Phase 1a does not need SCAN-ML beyond M1's `ModelRef`. Suggestions in 1a come from regex only. Row
32b's After column ("SCAN-ML; SCAN-MULTI S3") stays right for the whole row.

## 3. Established solutions and reuse inventory

The 2026-11-07 plan section 2 recorded the searches for the review loop, the answers file, the
prompt library and YAML editing; they still hold. Added for Phase 1a:

- **Guided scaffolders.** `npm init`, `cargo generate` and `dbt init` prompt one field at a time with
  the default in brackets and show a summary before writing. Steps follow that shape.
- **Back and forward without losing answers.** Form-wizard libraries keep per-field "dirty" and
  "touched" state (Final Form, React Hook Form); build systems record each output's inputs and
  rebuild only when one changes (make prerequisites, Bazel action keys). `WizardState` keeps an
  origin per answer (the "touched" bit), and each step's `stale()` compares its recorded inputs.
- **Delimiter suggestion.** Python's `csv.Sniffer` over the first lines (spec 16.4). Standard
  library, no custom detector.
- **Value shapes for `--no-samples`.** The character-class pattern masks of profiling tools (Talend
  Data Quality, OpenRefine pattern analysis): every lowercase letter to `a`, every uppercase letter
  to `A`, every digit to `9`, punctuation and spaces kept. The rule applies to every character,
  the domain of an email included: `Jane.Doe@mail.com` shows as `Aaaa.Aaa@aaaa.aaa` and
  `555-123-4567` as `999-999-9999`. Nothing of the value is kept but its shape.
- **No prompt without a terminal.** `terraform -input=false`, `gh` and the click documentation all
  refuse to prompt off a terminal and name the flags instead.

Custom code left: the step objects, the tree grouping and the review loop. Each is thin and calls
the engine for every data decision.

Reuse inventory (existing code each slice calls instead of writing its own):

| Need | Reused | Where |
|---|---|---|
| Strategy names, options, namespace rule, join safety | `decoy_engine.strategy_catalog`, `StrategyInfo`, `StrategyOption` (public exports) | engine `src/decoy_engine/__init__.py:128` |
| Keyed-ness of one column (engine side, inside E3 only) | `column_is_keyed` | engine `secret_providers/_requirements.py:210` (private; the CLI never imports it) |
| Whether a config needs a mask secret | `decoy_engine.secret_providers.secret_requirements_for_config` (public) | engine `secret_providers/_requirements.py:231` |
| Mask-secret wording: run hint, YAML comment, the no-seed-fallback sentence | `INIT_HINT`, `YAML_COMMENT`, `RUN` in `_mask_secret_guidance.py`; the wizard's Secrets and Review lines are added there as new constants, never written in `cli/wizard/` | `src/decoy/_mask_secret_guidance.py:17`, `:49`, `:56` |
| Shape check for a written `mask_secret_ref` | `_validate_mask_secret_ref_shape` (the DE-02 guard), called on the typed reference before it is accepted | `src/decoy/api.py:96`; sentry `tests/sentry/test_mask_secret_ref_shape.py` |
| Value-free config error text | the VALUE-FREE-ERRORS converter (roadmap row 24a) | `src/decoy/cli/_yaml_errors.py` |
| Multi-source scan and the starter config | `scan_sources`, `starter_config` | SCAN-MULTI S1a and S3-engine (P6, P7) |
| Column entries and verdict folding | `column_entry`, `apply_review` | E1 (6.1) |
| Pipeline YAML text | `_scaffold_yaml.render` | S3a.1 (P8) |
| Validation before the write | `run_gate_on_config` | `src/decoy/cli/gate/_layers.py:302` |
| Source reads and path resolution | `read_file`, `resolve_path` | `src/decoy/cli/_sources.py:93`, `src/decoy/cli/_sources.py:27` |
| Atomic, no-clobber write | `write_local_target` with `WriteMode.CREATE_ONCE` | `src/decoy/_atomic.py:144` |
| Import-alias resolution in sentries | the CODEMAP-designated shared call scanner (`bindings` and its resolver); no wizard-local scanner and no import of the test-local helpers in `test_gate_single_entry.py` | `tests/sentry/io_policy/_calls.py:29` (CODEMAP line 57) |
| Gate write verdict | the new `write_blocking_findings` classifier beside `gate_exit_code` (5.6) | `src/decoy/cli/gate/_layers.py:338` |
| Delimiter guess | `csv.Sniffer` | Python standard library |

## 4. Design notes

- **Library code does not know its callers.** Detection, column entries, verdict folding, keyed-ness
  and validation stay in `decoy_engine`. The CLI asks, holds state and writes bytes.
- **Principles applied, each for a concrete change pain.** Open/closed for steps: 1b and Phase 2 add
  steps (Checks, Quality, Relationships, Subset), so a step is one object in the ordered `STEPS`
  tuple of `cli/wizard/steps/__init__.py`, and `_flow.py` does not change when one is added.
  Dependency inversion for prompts: Phase 2 adds the answers-file path and Phase 3 replaces the
  terminal implementation with `prompt_toolkit`, so steps depend on the `Prompter` protocol and never
  on click. Single responsibility per module (placement table, section 10).
- **Step object** (spec 12): `applies(state)`, `defaults(state)`, `ask(state, prompter)`,
  `to_block(state)`, `stale(state) -> list[Change]`, `depends_on(state)` and `incomplete(state)`.
  Only `ask` touches the `Prompter`.
- **House style.** A typed `WizardContext` (state, prompter, output state, scan result) instead of
  long parameter lists. No `interactive: bool` flag: the terminal and the scripted test prompter are
  two `Prompter` implementations.
- **One place per fact.**
  - Strategies, options, namespace rules and join safety: `strategy_catalog()`.
  - Keyed fields: `keyed_columns_for_config` and `secret_requirements_for_config`.
  - Column entries: `column_entry`. Verdict folding: `apply_review`.
  - Keys: one `Key` enum in `_prompts.py`. Each member carries its character, its label for the key
    line and its `?` text. The key line, the help text and the verdict mapping in
    `_field_review.py` (one dict keyed by the enum, with a test that every field-review member is
    mapped) all read it.
  - One-shot flags: one tuple `ONE_SHOT_FLAGS` in `_prompts.py`, which the no-terminal hint and its
    test both read. The three-row decision itself is one function in `_prompts.py`
    (`refuse_without_terminal`), so `init.py` only calls it and does not grow.
  - Mask-secret wording: `src/decoy/_mask_secret_guidance.py`.
  - Gate write verdict: `write_blocking_findings` in `cli/gate/_layers.py`.
  - Tree grouping: `_tree.py`, the one hand-written strategy list, kept in step by the tree sync test.
  - CLI reason codes: one registry in `src/decoy/_reason_codes.py`. Existing CI-manifest and static
    gate-code sets and the new `init.*` set are derived views, not parallel hand-written tables.
- **Choke points.**
  - Terminal I/O: only `_prompts.py` calls a prompt function or probes `isatty`. Guard: the
    prompt-boundary sentry. Mutation M-W4a turns it red.
  - Wizard error output: `_prompts.py` owns one structured `WizardError` renderer used by terminal,
    no-terminal and scripted routes. It accepts only a fixed message id, codes, table or column
    names, counts and an exception type name. The prompt-boundary sentry rejects direct stderr
    writes elsewhere in `cli/wizard/`; the no-exception-text sentry rejects `str`, `repr`, `.args`,
    f-string or format use of a caught exception. Guards: AT-W8, AT-W9 and
    `test_no_exc_text.py`. Mutations M-W8b and M-W9.
  - Data-derived values on screen: only `Prompter.show_samples` prints them, and only `_preview.py`
    calls it. Guard: AT-W8 and the prompt-boundary sentry's second rule. Mutation M-W8d.
  - YAML text: `_scaffold_yaml.render`. Guard: G-ONE-EMITTER. Mutation M-EMIT-W.
  - Data reads: `cli/_sources.py` (G-ONE-CSV-READ). The parsed preview reads through it.
  - Validation: `decoy.cli.gate` (G-ONE-GATE).
  - Writes: `_atomic.write_local_target` (`tests/sentry/test_atomic_writer.py`).
  - Path roles: one check in `_flow.py` used by flags and by the Sources (data file and header
    file) and Output prompts. It compares every write role against every other role and every
    target against the other targets, while allowing read roles to share. Mutations M-W22,
    M-W22b and M-W22d.
- **Cutover choice (spec 17 asks the plan to pick).** Phase 1a ships behind the existing entry, with
  the old flow removed in the same slice. Slices W1a.2 to W1a.6a add wizard modules that nothing in
  `decoy init` calls yet; they are tested through the scripted `Prompter`. W1a.6b wires the wizard
  into `decoy init` and deletes the old terminal path (pre-GA hard delete). The one-shot route of row
  (c) keeps S3a.1's unreviewed starter.

## 5. Behavior

### 5.1 Command surface in Phase 1a

```text
decoy init                       terminal: Start menu (new pipeline from files, or a preset)
decoy init FILE                  terminal: wizard with FILE as the first source
decoy init --preset NAME         terminal: preset questions through the Prompter
decoy init [FILE] --no-input     one-shot, never prompts (also --json, -q)
```

New flags: `--no-input`, `--no-samples`. Kept: `-o/--output`, `--preset`, `-y/--yes`, `--json`,
`-q`, `-v`, and the header flags S3a.1 adds. `-y` answers only the overwrite question.

`-o -` writes the YAML to stdout. In a terminal the wizard runs and prints the YAML after Review.
Off a terminal it falls under rows (a) and (b) like any other default-mode run. With `-o -` there
is no YAML directory, so paths in the YAML are written relative to the current directory (the
directory `decoy run` must be started from) or absolute when outside it.

### 5.2 No-terminal rule (owner answer, spec 11; amends AT-W4)

"No terminal" means stdin or stdout is not a TTY, read by one function `_prompts.has_terminal()`.
"Default mode" means none of `--json`, `-q` or `--no-input` is given.

| Row | Case | Result |
|---|---|---|
| (a) | Bare `decoy init`, or `decoy init --preset X`, default mode, no terminal | Exit 1 before any prompt or write. One error line, then a hint naming each flag in `ONE_SHOT_FLAGS` |
| (b) | `decoy init FILE`, default mode, no terminal | Exit 1 before reading the source, prompting or writing, with the same hint |
| (c) | `--json`, `-q` or `--no-input`, with or without `FILE`, terminal or not | Never prompts. Today's output: the chosen preset, or `minimal` with no `FILE`; with `FILE`, S3a.1's unreviewed starter |

- Flag errors come first: an unknown preset, a missing `FILE` or a bad extension exit 1 with their
  own message before the row (a) or (b) check, so the message names the real problem.
- In Phase 1a `ONE_SHOT_FLAGS` is `--json`, `-q`, `--no-input`. Phase 2 adds `--answers` to the tuple
  when the flag exists, which makes the hint name it as spec 11 requires. The owner answer ("explicit
  one-shot flags, including `--answers`, keep working") is met once `--answers` exists; the hint never
  names a flag that is not registered.
- The existing-output question counts as a prompt. In row (c), in a terminal or not, an existing
  output without `-y` exits 1 with the "rerun with --yes" hint and never asks. Today's
  `init.py:512-523` asks in a terminal whenever the output mode is default, which `--no-input`
  alone leaves unchanged, so the check moves into `refuse_without_terminal`'s neighbour in
  `_prompts.py` and keys on "one-shot", not on the output mode.

### 5.3 Flow

```text
Start -> Goal -> Sources -> Scan -> Fields (per table) -> Output -> Secrets -> Review -> write
```

The progress bar of spec 4.1 lists these eight steps, with the done, current, not-visited,
needs-review and skipped marks.

- **Start** (spec 5.0, cut): `1 New pipeline from data files` (default), `2 Start from a preset`.
  With `FILE` or `--preset` the menu is skipped (the step's `applies` is false). Start is a step
  object like the others (`steps/start.py`), so the eight entries of the progress bar are exactly
  the `STEPS` tuple.
- **Goal** (spec 5.1): Mask only, no prompt (1.1 item 3). The step exists so 1b and Phase 2 can widen
  it without a flow change.
- **Sources** (spec 5.2 items 1 to 3, 5, 6, local only): one source at a time, then "Add another
  source? [y/N]".
  1. Path. A missing file is reported and the path is re-asked. (Keeping a missing path is a 1b item
     with S3 and GCS, where "the file may not exist on this machine yet" applies.)
  2. Format: CSV (comma), TSV, delimited with another character, Parquet. The default is the
     extension's format, or for `.csv` and `.txt` the delimiter `csv.Sniffer` finds in the first
     lines read through `cli/_sources.py`.
  3. Column names (CSV kinds only): first row (`has_header: true`); a header file, written as
     `column_names_file` (CONFIG-EXPLICIT E1, P3), whose name count must equal the fields per record;
     or typed in, one line separated by commas, written as `column_names`. `has_header` is always
     written. A header file takes the source role in the path-role check (5.6) the moment it is
     entered.
  4. Parsed preview: the first three records parsed with these settings, through
     `Prompter.show_samples`. "Does this look right? [Y/n]"; `n` returns to Format.
  5. Table name: defaults to the file stem; must be unique among tables.
  Parquet skips items 2 and 3: names come from the file.
- **Scan** (spec 5.3): sample size per source (default 10,000), then `scan_sources` and
  `starter_config` once over all sources. A summary table per table: field, type, nulls, unique
  share, what was detected, confidence. A name-hint match is labelled "identifier (name matched the
  record-number list)". Confidence comes from the detector's bucket; the current CLI rule that any
  match with `match_rate >= 0.5` counts as confident is not carried over.
- **Fields** (spec 5.4.2, every-field mode): for each table, each field in source order.

  ```text
  [6/8] zip   str · US ZIP (high)
    Suggested  truncate  keep the first 3 digits
    Samples    94110  10001  60614      (from the first rows read for the preview)
    Enter accept · r reject · o options · k keep as-is · d drop · b back · ? why
  ```

  The `Samples` line shows the first three non-empty values of the field from the same first rows
  the parsed preview read through `cli/_sources.py`. `_preview.py` holds those rows in memory for
  the session and is the only caller of `Prompter.show_samples`; with `--no-samples` it shows
  shapes. The scan result supplies no values.

  Key mapping to the engine verdicts (E1, 6.1), from the one `Key` enum:

  | Key | Meaning | Decision passed to `apply_review` |
  |---|---|---|
  | Enter | accept the shown entry | field with a suggestion: `CONFIRM` with its `SuggestionRef`; field without one: `EDIT` with the starter's entry (the user accepted it) |
  | `r` | reject: pick another strategy from the tree or by typed name | `EDIT` with the chosen strategy and its asked options |
  | `o` | options of the shown strategy | `EDIT` with the same strategy and the edited options |
  | `k` | keep as-is | `EDIT` with `passthrough` |
  | `d` | drop the field from the output | `DROP` (open decision 14.3). Refused on the table's last kept field: "A table needs at least one kept field. Use k to keep it as-is." The field is asked again. A kept field is one whose decision is not `DROP`, undecided fields included |
  | `b`, `g`, `l` | previous field, go to a field by number or name, list every field with its choice | none |
  | `s` | skip the rest of this table | `SKIP` for each remaining field (keeps the starter entry and note; listed in the checklist) |
  | `?` | why: what the scan found and why this strategy was suggested | none |
  | `q` | quit without writing, after "Quit without writing? [y/N]" | none: exit 1 |

  - Options come from `StrategyOption`: required options are asked; an optional option shows the
    catalog `example` labelled "example, not the default", and Enter leaves it unset (spec 5.4.2,
    gap 16.6). Each value is parsed to the option's exact `wire_type`; `choices` are a numbered menu.
  - A namespace is never asked: `column_entry` sets it for every `namespace_required` strategy.
    Sharing a namespace across fields is under "advanced" in options.
  - A reviewed field carries no `# REVIEW:` note in the YAML; a skipped field keeps its note.
- **The strategy tree** (spec 5.4.3): the grouping as written there, with these leaves: every
  `offer_in_wizard=True` catalog row except `faker`; plus every provider in the registry except the
  named hidden set (`random_choice`, `random_int_range`, `composite_custom`, `composite_provider`,
  hidden until gap 16.6). `tokenize` is not shown in 1a (the Tokenize goal is Phase 3). Typing a
  name or a unique prefix at any level jumps to that leaf.
- **Output** (spec 5.9, local): per table, format CSV or Parquet (default: the source's format;
  TSV and other delimiters default to CSV, with the note that CSV targets are comma-delimited with
  a header row, gap 16.3), then path, default `out/<table>.masked.<ext>`.
- **Secrets** (spec 5.10): the seed and mask-secret table of spec 5.10, then:
  1. Seed (default 42), written as `global_settings.seed`.
  2. Only when `secret_requirements_for_config(config)` is not empty: the fields
     `keyed_columns_for_config(config)` returns, with their strategies, or the generic sentence "This
     pipeline needs a mask secret." when it returns none (for example a composite parent key). Then
     a menu: store a reference in the pipeline (`env:DECOY_MASK_SECRET` default, or `file:/PATH`), or
     supply it at run time (`decoy run --mask-secret ...`). One or the other, never both. A typed
     reference must pass the existing shape check (`_validate_mask_secret_ref_shape`,
     `src/decoy/api.py:96`) before it is accepted; a refused one is asked again with that check's
     value-free message. The wizard checks whether the variable or file exists and warns if not; it
     never reads, prints or stores the value. There is no seed fallback. Every sentence in this step
     comes from `src/decoy/_mask_secret_guidance.py`: the existing `INIT_HINT` and the
     no-seed-fallback wording, plus new constants added there for the wizard (`WIZARD_SECRET_ASK`,
     `WIZARD_SECRET_GENERIC`).
- **Review** (spec 5.11, cut): a summary of each source to its target and each field to its
  strategy, plus the secret reference. Keys: Enter write, `y` view YAML, `g` go to a step, `q` quit
  without writing. While any step is marked as needing review, Enter refuses and offers to jump to
  the first marked step. `y` folds and renders through the same preparation as Enter, then displays
  the YAML without running the gate or opening a sink. Enter folds, renders, gates and writes or
  emits (5.6), then shows the checklist of skipped steps and fields and the run command (with
  `--mask-secret ...` when the user chose run-time supply). The run command text is the guidance
  module's `RUN` wording; the YAML comment beside a stored reference is its `YAML_COMMENT`.

### 5.4 Keys outside field review

Spec 4.2: Enter default, `b` back, `f` forward (only to a step already answered), `g` go to, `s`
skip the rest of this step (listed in the checklist), `?` explain, `q` quit without writing (1a
has no draft). The key line prints once at the start; `?` reprints it.

### 5.5 Navigation and stale marking in Phase 1a

Every answer keeps its origin: `suggested` (from the scan, a preset or another answer) or `user`.
Tables and fields have stable ids; names are attributes. When an earlier answer changes, suggested
values refresh silently and user values never change silently. Each step's `stale(state)` lists
what no longer fits; a non-empty list marks the step as needing review, and the user chooses keep,
change or remove for each item when they reach it.

Cases in Phase 1a, each with a navigation test (AT-W23):

1. Removing a source marks Fields and Output.
2. Renaming a table updates every reference through its id (its fields and its target).
3. A changed delimiter, header choice or header file re-runs Scan and marks Fields.
4. A changed source format refreshes a suggested Output format; a user-chosen format is marked.
5. A keyed strategy chosen in Fields after Secrets was answered marks Secrets.
6. Going back and forward keeps every answer.
7. Review refuses to write while a step is marked.

The 1b and Phase 2 cases of spec 4.3 (validators, goal toggling, flagged-set changes, relationships)
arrive with their steps.

### 5.6 Review preparation, the write step and path roles

Review `y` and Enter both run steps 1, 2 and 4's render operation from current state. Enter then
runs step 3 before step 4's sink operation. A later state change invalidates the prepared result,
so the next `y` or Enter rebuilds it.

1. `apply_review(starter, decisions)` over all Fields decisions. It validates and compiles inside
   (E1) and returns the reviewed `StarterConfig`. Any raise here, including `ReviewInputError` or
   its validation or compile assertion, is a builder bug during Review: exit 3, write no file and
   show no rendered YAML, and show only the fixed code plus table or column names. Never show
   `str(exc)`.
2. The wizard sets sources, targets and `global_settings` from its state on that result.
3. `run_gate_on_config(raw, out_path)` once, all layers (`src/decoy/cli/gate/_layers.py:302`).
   The wizard does not call `gate_exit_code` (`_layers.py:338`): that function returns 1 for any
   error finding and 5 for `capacity_insufficient`, and would block the write on a preflight error.
   Instead one new classifier beside it, `write_blocking_findings(result) -> tuple[GateFinding,
   ...]`, returns the error findings whose `GateFinding.layer` (`_layers.py:49`) is `config` or
   `compile`. Non-empty: exit 3, nothing written, findings shown. Empty: the write goes on, and
   every other finding is shown after the write. `capacity_insufficient` is a preflight fact about
   this machine: the YAML is written to its file or emitted on `-o -`, the capacity finding is shown
   with the line "decoy run will stop with exit 5 on this machine", and `decoy init` exits 0. The
   classifier lives in `cli/gate/`
   so any later scaffolding command (`decoy edit`) reuses it.
4. `_scaffold_yaml.render(...)` produces the text. For a file path,
   `_atomic.write_local_target` writes it with `CREATE_ONCE` unless the user confirmed the
   overwrite or gave `-y`. For `-o -`, the same rendered text is emitted to stdout after the gate;
   no file or temp file is opened.

Paths in the YAML are written relative to the output YAML's directory when they sit under it, and
absolute otherwise, because `decoy run` resolves them against the config directory
(`cli/_sources.py:27`). With `-o -` the base is the current directory (5.1).

Path roles: write roles are the output YAML when it is a file and each target. Stdout (`-o -`) has
no file role. Read roles are each source data file
and each header file (`column_names_file`). A write role may not name the same file as any other
role, and two targets may not name the same file. A source data file and a header file may share a
file because both roles only read it. Existing files are compared with `os.path.samefile` (which
catches a symlink and a hard link), missing ones by resolved parent plus name (which catches a
lexical alias). A collision found from flags exits 1 with `init.path_collision` before any source
read; one found at a prompt is re-asked with the same message. `-y` and the overwrite confirm do
not waive the check: they only allow replacing an old YAML that has no other role.

### 5.7 Output surfaces

- Prompts, menus, summaries, previews: stdout, Rich. Sample values only through
  `Prompter.show_samples`. On `-o -`, the rendered YAML also goes to stdout after the gate.
- Errors: stderr, one line each, a fixed text or code plus names; the exception class at most,
  never `str(exc)`.
- `--json` and `-q`: only on row (c) routes, unchanged from today (AT-W15 snapshot).
- `-v` logs: step names, counts, detector names. No values.
- The pipeline YAML.
- Help text and epilog: no "STORM" (spec 13).

### 5.8 Exit codes

The six public codes only. 0 written (preflight findings, capacity included, shown); 1 usage, no
terminal, cancel, `q`, path collision; 3 source read or scan failure, a config or compile finding
from `write_blocking_findings`, any `apply_review` raise at write time (builder bugs), atomic write
failure. 2, 4 and 5 are not used by the wizard in 1a (`--fail-on-warning` is Phase 2; capacity is
reported, not exited on).

## 6. Engine parts

### 6.1 E1 (2026-11-07 plan part E1, amended)

Everything in the 2026-11-07 plan 4.6 "One entry helper", "Suggestion" and "Decisions" (the
pre-scan half), with these amendments:

- `ModelRef` is imported from `detection/types.py` as SCAN-ML M1 defines it (P2), not defined here.
- `ReviewVerdict` gains `DROP = "drop"`. `apply_review` on `DROP` removes the column's entry and adds
  the column to the table's single `drop_column` transform (creating it when absent, appending in
  source order). This keeps the engine rule at `config/_tables.py:439-450` (a column may not be both
  dropped and masked) true by construction. `DROP` on a column named in a declared relationship is
  refused with `config.key_column_not_join_safe`. A decision set that drops every column of a mask
  table is refused with `ReviewInputError` code `pre_scan.review_empty_table`, naming the table,
  before validation; this is the backstop for the wizard's decision-time refusal, because the
  engine refuses a mask table with no columns (`config/_tables.py:419-424`). `finding_edits` (E2, later) refuses `DROP` as not
  applicable to a finding.
- `CONFIRM` and `EDIT` clear the column's REVIEW note; `SKIP` keeps it; `REJECT` writes "rejected
  (suggested X)" as before. The 1a wizard does not emit `REJECT`; `r` maps to `EDIT`.
- Reason identities, each in its existing family and claimed at merge by REG-RENUMBER (section 12):
  `pre_scan.review_unknown_column`, `pre_scan.review_duplicate`, `pre_scan.review_stale`,
  `pre_scan.review_empty_table`, `config.entry_invalid`, `config.key_column_not_join_safe`.
- "STORM" text in the engine notes. `StarterConfig.notes` is a behavior-exact port of
  `cli/_init_inference.py`, whose note text names STORM. E1 owns the wording change: every note
  `starter_config` writes says "scan" or names the detector instead, with an engine test (AT-E8).
  E1 already rewrites how `starter_config` builds entries, so the notes change in the same files.
- `starter_config` builds every entry through `column_entry` (one writer for
  `profiling/starter_config.py` at a time: S3-engine.2, then E1).
- Size about 700 lines (the 2026-11-07 estimate of 640 plus the drop verdict, the empty-table
  refusal, the note wording and their tests). If the build measures above 750, the note wording and
  AT-E8 split off as E1b, merged before R-1a.

### 6.2 E3 (new): keyed fields (spec 16.12 and 16.10)

```python
@dataclass(frozen=True)
class KeyedColumn:
    table: str
    column: str
    strategy: str

def keyed_columns_for_config(config: Mapping[str, Any]) -> tuple[KeyedColumn, ...]
```

- Lives in `secret_providers/_requirements.py` beside `secret_requirements_for_config`, exported from
  `decoy_engine.secret_providers` and `decoy_engine`.
- Both functions walk the config through one private column walk that applies `column_is_keyed`
  (`_requirements.py:210`). `secret_requirements_for_config` keeps its result and adds the
  relationship rule (a composite parent key is keyed with no single field). No behavior change to it.
- Order: tables in config order, columns in config order. Generate tables are skipped, as today.
- Pinned oracle: a literal table of (config, expected `keyed_columns_for_config` result) built from
  the cases in `tests/secret_providers/test_requirements_matrix.py` plus one field per catalog
  strategy. The expected tuples are written out, not computed, so a mutation in the shared column
  walk changes both functions and still fails this table.
- Parity test: over the same corpus, a config needs the secret exactly when
  `keyed_columns_for_config` is non-empty or a composite parent key exists.
- The stale `GlobalSettings` docstring line about a `job_seed` fallback (`config/_global_settings.py`,
  gap 16.10) is corrected in the same part.
- No reason identity. About 250 lines. Builds from engine main now.

## 7. Failure modes

| Case | Phase 1a behavior |
|---|---|
| No terminal, default mode, bare init or `--preset` | Row (a): exit 1, no prompt, no write, hint names `ONE_SHOT_FLAGS` |
| No terminal, default mode, `init FILE` | Row (b): exit 1 before the source is read |
| Unknown preset, missing `FILE`, bad extension | Exit 1 with that message, before the terminal check |
| Ctrl-C or EOF at any prompt | Exit 1, "cancelled", nothing written, no temp file |
| `q` | Confirm, then exit 1, nothing written |
| A source path that does not exist | Re-asked at the prompt; as `FILE`, exit 1 as today |
| A header file whose name count differs from the fields per record | Re-asked with the two counts, no names or values |
| The parsed preview fails to parse | The step shows the engine's value-free message and returns to Format |
| A source read or scan fails | Exit 3 naming the table and the exception class only |
| An option value of the wrong type or outside `choices` | Re-asked with `column_entry`'s value-free message (`config.entry_invalid`, names the option key) |
| A write role (output YAML or target) names the same file as any other role, or two targets name the same file, by lexical alias, symlink or hard link | From flags: exit 1 `init.path_collision` before any read, `-y` or not. At a prompt: re-asked. A source data file and header file may share because both are read roles |
| Output YAML exists and has no other role | Default-mode terminal: ask; `-y` skips the ask. Row (c) without `-y`, terminal or not: exit 1 with the `--yes` hint, no prompt |
| `d` on a table's last kept field | Refused at the key with a fixed message; the field is asked again. `apply_review` refuses an all-dropped table (`pre_scan.review_empty_table`) as the backstop |
| A typed mask secret reference fails the shape check | Asked again with the check's value-free message |
| Review while a step is marked as needing review | Refuses to write and offers to jump to it |
| `apply_review` raises `ReviewInputError` or its validation or compile assertion | Builder bug: exit 3, nothing written; fixed codes and table or column names only |
| `write_blocking_findings` returns a config or compile error | Builder bug: exit 3, nothing written, findings shown |
| Preflight findings (missing native companion, other preflight errors) | YAML written to its file or emitted on `-o -`, findings shown, exit 0 |
| `capacity_insufficient` | YAML written to its file or emitted on `-o -`, capacity finding shown with "decoy run will stop with exit 5 on this machine", exit 0 |
| `_atomic` write failure | Exit 3 with the `_atomic` code; nothing left behind |
| The mask secret variable or file does not exist now | Warning only; the reference is still written |
| A table with many fields | `s` skips the rest; `l` lists; `g` jumps. No bulk accept in 1a (flagged-only mode is 1b) |

## 8. Acceptance tests (red first)

Written before the build steps of each slice, recorded red as an assertion failure against a stub,
each with the mutation that must turn it red on the final head. Fixtures: a three-table set (CSV with
header, pipe-delimited headerless CSV with a header file, Parquet) with seeded canary cells in every
column, built with the SCAN-MULTI fixture helpers; TSV for the dialect cases. The email column's
canary sits in the domain part as well as the local part (`a.b@zqxcanary.example`), so a shape rule
that keeps the domain fails AT-W8.

Carried from the 2026-11-07 plan, amended where noted. Ids not listed here (AT-W3, AT-W5, AT-W12 to
AT-W14, AT-W16 to AT-W21, AT-E5, G-ONE-EDITOR) belong to later phases and are unchanged.

| Id | Slice | Asserts | Mutation |
|---|---|---|---|
| AT-E1 (amended) | E1 | `apply_review` over every verdict for a column with one regex suggestion: confirm gives the suggestion entry with no note; reject gives `redact` with the rejected note; edit gives the given entry with no note; skip keeps entry and note; drop removes the entry and lists the column once in the table's single `drop_column` transform, and a second drop in the same table appends to that transform; the result validates and compiles. Dropping every column of a two-column table raises `ReviewInputError` with `pre_scan.review_empty_table`, naming the table and no value; dropping all but one passes | M-E1a: reject keeps the suggestion entry; M-E1b: drop keeps the column entry; M-E1c: remove the empty-table check (the engine's own refusal then surfaces as a validation error, not the review code) |
| AT-E2 | E1 | a classifier suggestion is never live and applies only on a matching confirm (unchanged; built from a fixture suggestion since 1a has no classifier) | M-E2 |
| AT-E3 (amended) | E1 | as before, plus: drop on a declared relationship key raises `config.key_column_not_join_safe`; messages name the column, never a value; `__cause__` and `__context__` are `None` | M-E3, M-E3b, M-E3c: allow drop on a key |
| AT-E4 (amended) | E1 | the Hypothesis property over random decision sets, now including `drop`: a set that drops every column of some table raises `pre_scan.review_empty_table`; every other set validates, compiles, keeps at least one column per mask table, keeps unnamed columns' entries, has a namespace on every `namespace_required` entry, and has no column both dropped and masked. The strategy is weighted so all-dropped tables occur | M-E4, M-E1c |
| AT-E7 (new) | E3 | the pinned oracle table of 6.2 (expected tuples written out, cases from `test_requirements_matrix.py`); parity of `keyed_columns_for_config` and `secret_requirements_for_config` over the same corpus; order is config order; generate tables skipped | M-E7: drop the `deterministic` term from one function's walk; M-E7b: drop it from the shared walk (both functions change, parity holds, the oracle fails) |
| AT-E8 (new) | E1 | no `StarterConfig.notes` text, over the SCAN-MULTI fixture set and one field per detector, contains "STORM" (case-insensitive) | M-E8: restore one ported note line that names STORM |
| AT-W1 (amended) | W1a.0, W1a.R | characterization: preset outputs and the one-shot `decoy init FILE --no-input` output equal pinned bytes. W1a.0's first commit pins S3a.1's bytes. A commit may change the pinned bytes only as a visible golden diff of two kinds: `namespace:` lines on `faker`, `nested` and `tokenize` entries (spec 17), and the `# REVIEW:` note lines ported from `src/decoy/cli/_init_inference.py:75-121` whose STORM-free wording AT-E8 requires. W1a.0 may change the namespace lines if its catalog swap does so; W1a.R may change those namespace lines and the REVIEW note lines when its repin brings E1's `column_entry` and note rewrite into `starter_config` | M-W1: change the default preset |
| AT-W2 (amended) | W1a.6b | scripted terminal session over the fixture through a pty on Linux and macOS (the scripted `Prompter` on Windows): the YAML reflects each key typed (Enter, `r`, `o`, `k`, `d`, `s`), `b` and `g` keep answers, and `s` skips only the rest of the table | M-W2a: `s` skips the whole run |
| AT-W4 (amended) | W1a.1 | the three rows of 5.2. Row (a): bare init and `--preset minimal`, stdin not a TTY and separately stdout not a TTY, exit 1, no prompt function called (spy), no file written, the hint names each entry of `ONE_SHOT_FLAGS`. Row (b): `init FILE` the same, and the `scan_sources` and reader spies never fire. Row (c): each of `--json`, `-q`, `--no-input`, with and without `FILE`, never prompts and writes today's output (AT-W1 bytes). Row (c) with an existing output and no `-y`, run once with a real terminal (pty) and once without: exit 1 with the `--yes` hint, no prompt, file unchanged. The non-terminal stream is left open so a prompt would hang | M-W4: treat "stdin is a TTY" as enough; M-W4c: let row (b) read the source before refusing; M-W4d: ask the overwrite question when `--no-input` is given in a terminal |
| AT-W6 (amended) | W1a.3a (sentry), W1a.3b (options) | every option prompt's parser type, required flag and choices equal the catalog descriptor, and the produced entry puts each option at its declared `location`. The no-strategy-literal sentry, outside `_tree.py` in `cli/wizard/`, fails on two or more catalog strategy names in any of: a tuple, list, set or frozenset literal; the keys of a dict literal; an `in` or `not in` test against a literal container; a chain of `==` or `!=` comparisons joined by `or` or `and`; `match` cases with literal patterns. Seeded cases for each shape | M-W6: hard-code a strategy list in `_field_review.py`; M-W6b: parse every option as text; M-W6c: a dict literal keyed by strategy names in `steps/fields.py` |
| AT-W7 | W1a.3b | 200 seeded key sequences over the fixture (edits drawn from the tree leaves with their `example_options`) produce a folded config that passes the gate in-process and has a namespace on every `namespace_required` entry; for 5 of them `decoy run` on a tiny fixture exits 0 | M-E4 |
| AT-W8 (amended) | W1a.6b | canary corpus on every 1a route. No canary in stderr, the YAML, `--json`, `-v` logs or re-shown engine errors. In stdout, every canary was printed by `Prompter.show_samples` (the scripted prompter records those calls); with `--no-samples`, no canary at all, the email-domain canary included. Non-vacuity: the corpus is found in the raw fixture bytes | M-W8a: a REVIEW note quotes a top value; M-W8b: an error prints `repr(exc)`; M-W8d: the Scan summary prints `top_values` directly; M-W8e: the shape rule keeps the email domain |
| AT-W9 | W1a.6a | every error exit path in section 7 prints exactly one error line in default mode, none holding a canary. On the exit-3 gate path, the one error line is followed by the findings list | M-W9 |
| AT-W10 (amended) | W1a.6a | exit-path matrix: Ctrl-C and EOF at each step and `q` exit 1; scan error, `_atomic` failure, a config finding, a compile finding and an injected `ReviewInputError` from `apply_review` exit 3. Inject the review error once on `y` and once on Enter. Every file-output row leaves no output file and no temp file. Every applicable `-o -` row emits no rendered YAML; `_atomic` failure is file-only. The `ReviewInputError` cells show only the code and table or column names. A preflight error and, separately, `capacity_insufficient` injected into the gate still write the YAML file, or emit it on `-o -`, and exit 0 with the finding shown. Unit cells for `write_blocking_findings`: config error blocks, compile error blocks, preflight error does not, warnings never block | M-W10: write or emit before the gate; M-W10b: skip the write on a preflight error; M-W10c: classify by severity alone (a preflight error blocks); M-W10d: use `gate_exit_code` (capacity exits 5) |
| AT-W11 (amended) | W1a.3b | any permutation of the same field decision set gives the same folded config (the duplicate-key half moves to Phase 2 with the answers loader) | M-W11b: last-writer-wins in `apply_review` |
| AT-W15 | W1a.6b | `--json` key snapshot of every row (c) route unchanged; engine export snapshot includes `keyed_columns_for_config` | M-W15 |
| AT-W22 (amended) | W1a.6a | the collision matrix over the roles file output YAML, source data file, header file and each target: every write-role pair (output YAML and source, output YAML and header file, target and source, target and header file, target and output YAML, target and target), each as a lexical alias, a symlink and a hard link. Supply a role by flag where Phase 1a has that flag (`-o`, `FILE` and the S3a.1 header-file flag), and exercise target paths through their prompts. A source and header file sharing a file is allowed. Stdout (`-o -`) has no file role. A collision fully known from flags exits 1 `init.path_collision` before the reader spy fires, with and without `-y`. A collision first known at a prompt is re-asked, and the overwrite confirm is never offered. Distinct sibling paths proceed. After every refused case the header file and the source keep their bytes and mtime | M-W22: compare raw path strings; M-W22b: leave the header file out of the role set; M-W22c: let `-y` waive a collision; M-W22d: skip the target-target pair |
| G-ONE-EMITTER | W1a.6b | SCAN-MULTI's guard extended: the wizard's write reaches `_scaffold_yaml.render`, and no module under `src/decoy/cli/wizard/` emits YAML text (`yaml.dump`, `yaml.safe_dump`, string building of `key: value` lines) | M-EMIT-W: the wizard writes `yaml.safe_dump` output |

New for Phase 1a:

| Id | Slice | Asserts | Mutation |
|---|---|---|---|
| AT-W23 | W1a.2 (generic), W1a.3b to W1a.5a (per case) | one navigation test per case in 5.5, with a scripted prompter: the step is marked, the listed change names the cause, suggested values refreshed, user values unchanged; Review refuses while marked | M-W23a: refresh a user value; M-W23b: Review writes while a step is marked; M-W23c: rename by name instead of id (the target keeps the old name) |
| AT-W24 | W1a.3a | tree sync: the leaves equal, exactly once each, the `offer_in_wizard=True` rows except `faker`, plus every registry provider minus the named hidden set; nothing in the tree is unknown to the engine; `tokenize` absent in 1a | M-W24a: drop a leaf; M-W24b: add a leaf the engine does not know |
| AT-W25 | W1a.5a | Secrets pinned outcomes (spec 15): shuffle-only asked; faker-only not asked; faker with `deterministic: true` asked; a composite parent key asked with the generic sentence and no field list; one field per catalog strategy asked exactly when `secret_requirements_for_config` reports, and the named fields equal `keyed_columns_for_config`. The step never reads the variable or file value (spy on reads of the named variable and on file opens). A malformed typed reference is refused by `_validate_mask_secret_ref_shape` and asked again; every line the step prints equals a constant of `_mask_secret_guidance.py` (string literals in `steps/secrets.py` are limited to the menu keys) | M-W25: a hand-kept keyed-strategy list in the CLI read instead of the engine; M-W25b: accept a reference without the shape check; M-W25c: write the secret sentence inline in `steps/secrets.py` |
| AT-W26 | W1a.6a | reason-code guard: every emitted `init.*` code is in the central registry's init view, every registered init code has an emitting path, and the existing CI-manifest and static gate views equal their pre-move sets. Seeded cases cover direct import, alias, module-qualified call and constructor alias, resolved with the shared scanner `tests/sentry/io_policy/_calls.py` | M-W26: change one emitted code to `init.unknown` |
| AT-W27 | W1a.6b | CLI side only (the engine notes are AT-E8): no "STORM" in wizard prompt text, string constants under `src/decoy/cli/wizard/`, `decoy init --help` or the epilog, and none in the generated YAML of the AT-W30 sessions (which carries the engine notes, so this also re-checks AT-E8 end to end) | M-W27: add "STORM" to one wizard prompt string |
| AT-W28 | W1a.0 | module size: every module under `src/decoy/cli/wizard/` is at most 800 lines, and `cli/init.py` is at most its line count at the W1a.0 base (S3a.1's merged head), recorded in the sentry baseline before any 1a slice edits it. The three-row rule and the overwrite rule live in `_prompts.py`, so W1a.1 adds only calls to `init.py`; W1a.6b shrinks it | M-W28: add 20 lines to `init.py` |
| AT-W29 | W1a.4a | Sources: comma, TSV, pipe-delimited and semicolon-delimited files each get the sniffed delimiter as the default; `has_header` is written in every CSV case; a header file is written as `column_names_file` and a count mismatch is re-asked; typed names are written as `column_names`; Parquet skips format and names; the parsed preview shows three records through `show_samples`, and `n` returns to Format; `--no-samples` shows shapes by the one rule of section 3 (`Jane.Doe@mail.com` as `Aaaa.Aaa@aaaa.aaa`, `555-123-4567` as `999-999-9999`); the header file is registered as a source role as soon as it is entered | M-W29a: omit `has_header: true`; M-W29b: copy header-file names into `column_names`; M-W29c: keep punctuation and letters after `@` |
| AT-W30 | W1a.6b | golden: a one-table pipe-delimited headerless source with a header file, and a two-table CSV plus Parquet pipeline, through a full scripted session; both YAMLs pass `PipelineConfig.model_validate` and `decoy validate` (config, compile, preflight), and `decoy run` on the first exits 0. Column names include `yes`, `null`, `#id` and `a: b` | M-W30: write source paths relative to the working directory instead of the YAML's directory |
| AT-W31 | W1a.4b | Scan labels: a name-hint `mrn` match on `customer_id` is labelled "identifier (name matched the record-number list)"; confidence follows the bucket, and a `match_rate` of 0.6 with a low bucket is not shown as high | M-W31: restore the `>= 0.5` rule |
| AT-W32 | W1a.5b | Review: the summary lists every source, target, field and secret reference; `y` shows the rendered YAML; the checklist lists every skipped step and every `SKIP` field; the printed run command carries `--mask-secret ...` exactly when run-time supply was chosen, in the guidance module's `RUN` wording | M-W32: drop skipped fields from the checklist |
| AT-W33 | W1a.3b | last kept field: in a two-field table, `d` then `d` refuses the second `d` with the fixed message and asks the field again; `k` then succeeds; `b` back to the first field and `k` there, then `d` on the second succeeds. In a one-field table the first `d` is refused. The decisions passed to `apply_review` never drop every column of a table | M-W33: allow `d` on the last kept field (the fold then raises `pre_scan.review_empty_table` and the test fails on the exit) |
| AT-W34 | W1a.3b | key table: every `Key` member used in field review has exactly one verdict mapping, the key line and the `?` text are built from the enum, and no key character is written as a literal outside `_prompts.py` | M-W34: add a key to the key line without a mapping |

Hostile cases (plan contract section 4), each covered above: a column named `yes`, `null`, `#id` or
`a: b` (AT-W30, renderer quoting); `q` at the first prompt (AT-W10); an off-terminal run that would
block on a prompt (AT-W4 and the prompt-boundary sentry); a scan error whose text carries a cell
value (AT-W8, AT-W9); `r` to `hash` with no namespace (AT-E4, AT-W7); a keyed strategy chosen after
Secrets so the run would fail (AT-W23 case 5); a target or the YAML that overwrites a source or a
header file, or two targets that share a file (AT-W22); `d` on every field of a table (AT-W33,
AT-E1); a capacity finding on a small machine (AT-W10).

## 9. Enumerations and class table

### 9.1 Exit paths

Every way `decoy init` can end in Phase 1a. Each is a row of AT-W10 or AT-W9.

1. Written: Review Enter, gate passes (preflight findings shown): exit 0.
2. Row (a) or (b) refusal before any prompt or read: exit 1.
3. Flag error (unknown preset, missing `FILE`, bad extension, path collision from flags): exit 1.
4. Ctrl-C or EOF at any prompt: exit 1, nothing written.
5. `q` and its confirm: exit 1, nothing written.
6. Existing output, row (c), no `-y`: exit 1.
7. Source read or scan failure: exit 3.
8. `apply_review` raises `ReviewInputError` or its validation or compile assertion during Review
   `y` or Enter, or a config or compile error finding occurs on the folded config (builder bug):
   exit 3, no file written and no rendered YAML shown. The
   `apply_review` failure shows only fixed codes and table or column names.
   The verdict comes from `write_blocking_findings`, which reads `GateFinding.layer`
   (`src/decoy/cli/gate/_layers.py:49`); the wizard does not call `gate_exit_code`
   (`src/decoy/cli/gate/_layers.py:338`), which would give 1 or 5.
9. `_atomic` write failure: exit 3, no temp file left (`src/decoy/_atomic.py:144`).
10. Preflight findings or `capacity_insufficient`: the YAML is written to its file or emitted on
    `-o -`, the findings are shown, exit 0.

### 9.2 Routes

1. Terminal, bare `decoy init`: Start menu, then the wizard or the preset questions.
2. Terminal, `decoy init FILE`: wizard with FILE as the first source.
3. Terminal, `--preset NAME`: preset questions through the `Prompter`.
4. No terminal, default mode, bare or `--preset`: row (a) refusal.
5. No terminal, default mode, `FILE`: row (b) refusal.
6. Any `ONE_SHOT_FLAGS` flag, terminal or not, with or without `FILE`: row (c), today's output.
7. `-o -` in a terminal: wizard, YAML printed to stdout after Review.
8. Scripted `Prompter` (tests only): the same steps as route 1 with keys from a list.

### 9.3 FK shapes

The 1a wizard declares no relationships (the Relationships step is Phase 2), and SCAN-MULTI V1
explicitly infers none (`T3-no-inferred-relationships`). Therefore no relationship can reach a 1a
config and the key-column refusals below cannot occur in Phase 1a. E1 still guards each shape for
later callers:

1. Single-column parent key: `r`, `o` or `k` to a strategy the catalog does not mark `join_safe` is
   refused with `config.key_column_not_join_safe`; `d` is refused the same way.
2. Child foreign key: the same rules; the entry keeps the relationship namespace.
3. Composite key (parent or child): every member column follows rule 1; Secrets shows the generic
   sentence because no single field is keyed (AT-W25).
4. Self-reference: treated as rules 1 and 2 on one table.

Covered by AT-E3 and AT-E4. The full per-shape `decoy run` matrix (2026-11-07 AT-W12) moves to
Phase 2 with the Relationships step.

### 9.4 Fields

The field kinds the Fields step must handle, each in AT-W7 or AT-W30:

1. A field with a regex suggestion (Enter confirms it).
2. A field with no suggestion (Enter accepts the starter entry; the old namespace rule at
   `src/decoy/cli/init.py:235` is replaced by the catalog's `namespace_required`).
3. A field whose chosen strategy needs a namespace (set by `column_entry`, never asked).
4. A field whose chosen strategy is keyed (marks Secrets, AT-W23 case 5).
5. A dropped field (`d`, one `drop_column` transform per table).
5a. The last kept field of a table: `d` refused at the key (AT-W33), all-dropped refused by
    `apply_review` as the backstop (AT-E1, AT-E4).
6. A skipped field (`s`, keeps the starter note, listed in the checklist).
7. Field names that YAML would misread: `yes`, `null`, `#id`, `a: b` (AT-W30).
8. Parquet fields with names from the file; headerless CSV fields named by a header file or typed in.

### 9.5 Output surfaces

As listed in 5.7, each checked by AT-W8:

1. stdout prompts, menus, summaries (no source cell values except through `show_samples`).
2. stdout parsed preview and field samples (`show_samples` only; shapes with `--no-samples`).
3. stderr error lines.
4. `--json` and `-q` output on row (c) routes.
5. `-v` logs.
6. The rendered pipeline YAML, written to a file or emitted by `-o -`, including REVIEW notes.
7. `--help` text and epilog.

### 9.6 Class table

These are the plan's risk classes retained from the 2026-11-07 plan, not the numbering of the
current recurring-defect catalog.

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | the surfaces in 9.5 | source cell values only through `show_samples`, called only from `_preview.py`; one shape rule for `--no-samples`; errors are fixed text plus names, and a relayed config error goes through the VALUE-FREE-ERRORS converter (`cli/_yaml_errors.py`, row 24a); scan records carry no source cell values from the engine | AT-W8; sentry `tests/sentry/wizard/test_no_exc_text.py` (the 2026-11-07 list of exception spellings, on the shared scanner `tests/sentry/io_policy/_calls.py`) | M-W8a, M-W8b, M-W8d, M-W8e |
| 2 | Cleanup missing on an exit path | the exit paths in 9.1 | nothing is written or emitted before the single write step; one gate write classifier; `_atomic` removes its temp file on file-write failure; `-o -` emits only after the gate | AT-W10 | M-W10, M-W10c |
| 3 | Stale state after navigation | back, forward, go-to, changed earlier answers, the last kept field | answer origin, stable ids, `stale()` per step, Review refuses while marked; the kept-field count is read from the current decisions at each `d` | AT-W23, AT-W33 | M-W23a to c, M-W33 |
| 4 | Route parity and hidden prompts | the routes in 9.2 | one terminal probe and every prompt in `_prompts.py`; steps take a `Prompter` | AT-W4; sentry `tests/sentry/wizard/test_prompt_boundary.py` over `cli/init.py` and `cli/wizard/` (the 2026-11-07 call list plus `isatty`, on the shared scanner) | M-W4, M-W4a: a step calls `typer.prompt`; M-W4b: `from rich.prompt import Confirm as C` in `_flow.py`; M-W4d |
| 5 | Referential integrity | key columns in the FK shapes of 9.3; a table emptied by drops | `apply_review` refuses a non-join-safe strategy or `DROP` on a key column, and an all-dropped table; the gate runs on the result | AT-E3, AT-E4, AT-E1 | M-E3c: allow drop on a key; M-E1c |
| 6 | Untrusted producer | typed option values, typed column names, a header file, typed paths, a typed mask secret reference | option values parsed to the catalog `wire_type` and checked by `column_entry`; header file count checked; paths go through the path-role check; the reference through the DE-02 shape check. No answers file or report is read in 1a | AT-W6, AT-W29, AT-W22, AT-W25 | M-W6b: parse every option as text; M-W29b; M-W25b |
| 7 | Check then use on a path (TOCTOU) | output exists, then write; a write role that collides with a read role or another write role | one path-role check over the output YAML, every target and both read-role kinds, with `samefile` before any read where flags supply the paths and again before the write, never waived by `-y`; read roles may alias each other; the write uses `_atomic` with `CREATE_ONCE` unless an overwrite was confirmed. Residual window accepted for a single-operator CLI (SCAN-MULTI precedent) | AT-W22, AT-W10 | M-W22: compare raw path strings; M-W22b; M-W22c; M-W22d |
| 8 | Weak tests and overclaimed evidence | every acceptance test | each test names its mutation and a real oracle (`decoy run`, namespace assertion, reader spy), not only the gate | reviewer reruns the named mutations on the final head | removing a named mutation from the evidence record is a gate finding |
| 9 | Behavior-preserving refactor drift | `--preset` output and the one-shot `init FILE` output while `init.py` or the engine pin changes | characterization first (AT-W1) before W1a.0, W1a.R and W1a.1 edit the implementation or pin; only the named namespace lines and the AT-E8 REVIEW-note rewrites may change, as a visible golden diff | AT-W1, AT-W28 | M-W1: change the default preset; M-W28 |
| 10 | Frozen contract drift | CLI flags, exit codes, `--json` keys, engine public API | additive flags only; `--json` keys unchanged; six exit codes; engine exports added only | AT-W15 key snapshot and the engine export snapshot | M-W15: rename one `--json` key |

Hand lists drifting from the engine (the 2026-11-07 catalog work) are closed by AT-W6, AT-W24 and
AT-W25 (mutations M-W6, M-W24a, M-W25). Path role confusion is part of class 7. Copied wording
(mask-secret sentences, value-free error text) is closed by reuse of `_mask_secret_guidance.py` and
`cli/_yaml_errors.py` (AT-W25, AT-W8).

Recurring-defect catalog check: the reused mask-secret validator owns its whole-value validation;
option parsers preserve exact wire types; AT-E3 checks empty exception cause and context; no new
stored read model is added; wizard sentries use the normalized shared scanner with seeded alias
forms; no other package's private module is imported; CI checks stay blocking; interactive and
one-shot inputs have separate named routes; final-head mutations are required in section 8; no
helper is allowlisted without its callers being scanned; no size or allowlist pin is raised.

## 10. Placement

CODEMAP "Where things go" has no row for the wizard. W1a.2 adds one row (the spec 12 revision of the
2026-11-07 W1.1 row, with named test folders):

> Interactive review wizard for `decoy init` (and later `decoy edit`): `src/decoy/cli/wizard/`,
> files `_<noun>.py`, one module per step in `cli/wizard/steps/`; unit tests in
> `tests/unit/wizard/`, e2e tests in `tests/e2e/wizard/`, sentries in `tests/sentry/wizard/`
> (they use the shared call scanner `tests/sentry/io_policy/_calls.py`).

W1a.0 creates `tests/sentry/wizard/` (the module-size sentry) and W1a.1 creates the package, so
W1a.0 adds the row. The "Shared YAML document
structure" row and `_safe_profile.py` arrive with their first users (Phase 2 and 1b).

| File | New or changed | Directory | CODEMAP row | Sits beside | Slice | Lines (approx.) |
|---|---|---|---|---|---|---|
| `cli/wizard/__init__.py` | new | `src/decoy/cli/wizard/` | wizard (new) | `src/decoy/cli/gate/` | W1a.1 | 10 |
| `cli/wizard/_prompts.py` | new | same | wizard | | W1a.1 | 300 |
| `cli/wizard/_state.py` | new | same | wizard | | W1a.2 | 220 |
| `cli/wizard/_nav.py` | new | same | wizard | | W1a.2 | 150 |
| `cli/wizard/steps/__init__.py` | new | `src/decoy/cli/wizard/steps/` | wizard | | W1a.2 | 80 |
| `cli/wizard/_tree.py` | new | `src/decoy/cli/wizard/` | wizard | | W1a.3a | 200 |
| `cli/wizard/_field_review.py` (named so it is not confused with `steps/review.py`) | new | same | wizard | | W1a.3b | 250 |
| `cli/wizard/steps/fields.py` | new | `.../steps/` | wizard | | W1a.3b | 150 |
| `cli/wizard/_preview.py` | new | `src/decoy/cli/wizard/` | wizard | | W1a.4a | 120 |
| `cli/wizard/steps/goal.py` | new | `.../steps/` | wizard | | W1a.4a | 40 |
| `cli/wizard/steps/sources.py` | new | `.../steps/` | wizard | | W1a.4a | 280 |
| `cli/wizard/steps/scan.py` | new | `.../steps/` | wizard | | W1a.4b | 150 |
| `cli/wizard/steps/output.py` | new | `.../steps/` | wizard | | W1a.5a | 140 |
| `cli/wizard/steps/secrets.py` | new | `.../steps/` | wizard | | W1a.5a | 140 |
| `src/decoy/_mask_secret_guidance.py` | changed (the wizard's Secrets constants) | `src/decoy/` | existing | | W1a.5a | +20 (119 today) |
| `cli/wizard/steps/review.py` | new | `.../steps/` | wizard | | W1a.5b | 170 |
| `cli/wizard/_checklist.py` | new | `src/decoy/cli/wizard/` | wizard | | W1a.5b | 80 |
| `cli/wizard/steps/start.py` | new | `.../steps/` | wizard | | W1a.6a | 60 |
| `cli/wizard/_flow.py` | new | `src/decoy/cli/wizard/` | wizard | | W1a.6a | 280 |
| `src/decoy/_reason_codes.py` | new | `src/decoy/` | CODEMAP line 48, private shared primitives | `_atomic.py`, `_mask_secret.py` | W1a.0 | 120 |
| `src/decoy/ci/contracts.py`, `src/decoy/ci/rule_codes.py` | changed (derive their existing closed views from the central registry) | `src/decoy/ci/` | existing CI integration layer | | W1a.0 | net neutral |
| `src/decoy/cli/gate/_layers.py` | changed (`write_blocking_findings` beside `gate_exit_code`) | `src/decoy/cli/gate/` | existing G-ONE-GATE package | | W1a.6a | +25 (348 today) |
| `src/decoy/cli/init.py` | changed | `src/decoy/cli/` | existing (`cli/` is frozen: changes only, no new modules) | | W1a.0, W1a.1, W1a.6b | never above its W1a.0 base size (AT-W28); shrinks in W1a.6b |
| `src/decoy/cli/completers.py` | changed | same | existing | | W1a.0 | -20 |
| `src/decoy/cli/_sources.py` | changed (a first-rows reader and `sniff_delimiter`) | same | existing G-ONE-CSV-READ choke point (moves to `cli/io/` under H-1) | | W1a.4a | +50 (183 today) |
| `src/decoy/cli/_scaffold_yaml.py` | changed only if S3a.1's renderer lacks a block the wizard writes (`global_settings.seed`, `mask_secret_ref`, `column_names_file`, `drop_column`) | same | S3a.1's placement | | W1a.6a | +60 at most |
| `tests/unit/wizard/test_*.py` | new | `tests/unit/wizard/` | wizard | `tests/unit/cli_fmt/` | W1a.1 to W1a.6a | 120 to 300 each |
| `tests/e2e/wizard/test_*.py` | new | `tests/e2e/wizard/` | wizard | `tests/e2e/cli_fmt/` | W1a.1, W1a.6b | 150 to 300 each |
| `tests/unit/gate/test_write_blocking.py` (or the existing gate unit folder) | new | existing gate tests folder | existing | | W1a.6a | 80 |
| `tests/unit/test_reason_codes.py` | new | `tests/unit/` | CODEMAP line 48 shared-primitive test convention | `tests/unit/test_atomic.py` | W1a.0 | 100 |
| `tests/e2e/wizard/test_init_scaffold_roundtrip.py` | moved from `tests/e2e/` | same | wizard | | W1a.1 | moved; `test_init_stdout_with_dash` gains `--no-input` |
| `tests/sentry/wizard/test_prompt_boundary.py` | new | `tests/sentry/wizard/` | wizard (shape of `tests/sentry/io_policy/`) | `tests/sentry/io_policy/` | W1a.1 | 90 |
| `tests/sentry/wizard/test_module_size.py` | new | same | same | | W1a.0 | 60 |
| `tests/sentry/wizard/test_no_exc_text.py` | new | same | same | | W1a.2 | 90 |
| `tests/sentry/wizard/test_no_strategy_literal.py` | new | same | same | | W1a.3a | 110 |
| `tests/sentry/wizard/test_reason_codes.py` | new | same | same | | W1a.6a | 90 |
| `tests/sentry/wizard/test_no_storm_text.py` | new | same | same | | W1a.6b | 50 |
| `tests/sentry/test_sentry_manifest.py` | changed (each new sentry added to `SENTRIES`, line 24) | `tests/sentry/` | existing | | each sentry's slice | +1 each |
| `scripts/dev/sentry_registry.toml` | changed (a baseline entry per new sentry, the `init.py` size pin included) | `scripts/dev/` | existing | | each sentry's slice | +3 each |
| `CODEMAP.md` | changed (one row) | root | n/a | | W1a.0 | +2 |
| `docs/cli-reference.md`, `CHANGELOG.md` | changed | `docs/`, root | n/a | | W1a.1, W1a.6b | +60 |
| engine `profiling/starter_review.py` | new | `src/decoy_engine/profiling/` | engine CODEMAP `profiling/` row | `profiling/starter_config.py` (S3-engine.2) | E1 | 300 |
| engine `profiling/starter_config.py` | changed (entries through `column_entry`; note wording without "STORM") | same | existing (S3-engine.2) | | E1 | +30 |
| engine `tests/unit/profiling/test_starter_review.py` | new | `tests/unit/profiling/` | same convention | | E1 | 380 |
| engine `secret_providers/_requirements.py` | changed | `src/decoy_engine/secret_providers/` | existing | | E3 | +70 (267 today) |
| engine `tests/secret_providers/test_keyed_columns.py` | new (pinned oracle and parity) | `tests/secret_providers/` | beside `test_requirements_matrix.py` | | E3 | 200 |
| engine `decoy_engine/__init__.py`, `secret_providers/__init__.py` | changed (export lines, keep-both ledger) | | existing | | E1, E3 | +6 |

Fan-out: `src/decoy/cli/wizard/` holds 10 modules after 1a and `steps/` holds 9, both under the cap
of about 25. Each new module aims under 400 lines; the 800-line cap of AT-W28 is the hard limit.

One registry per cross-cutting concern: CLI-facing reason codes in `src/decoy/_reason_codes.py`,
with existing CI-manifest, static gate and new init views derived from it; steps in the `STEPS` tuple of `cli/wizard/steps/__init__.py`; keys in the
`Key` enum of `_prompts.py`; one-shot flags in `ONE_SHOT_FLAGS`; the tree in `_tree.py`; mask-secret
wording in `_mask_secret_guidance.py`; the gate write verdict in `cli/gate/_layers.py`; sentries in
`SENTRIES` and `sentry_registry.toml`.

## 11. Slices

This plan amends spec 17's "one CLI slice" for Phase 1a into the slices below. Sizes are hand-written
lines including tests and docs. Build order is top to bottom except that W1a.R and W1a.1 may land in
either order once their After columns are met. W1a.3a, W1a.4a and W1a.5a may build in parallel once
their After column is met (they share only `STEPS` tuple lines, a keep-both ledger line) and merge
one at a time.

Hot-file lanes: no 1a slice writes `src/decoy/cli/run.py` or `src/decoy/cli/scan.py`, so Phase 1a
enters neither lane (roadmap 5.2 rule 2). Phase 1a holds an `init.py` lane of its own:
CONFIG-EXPLICIT C2 and SCAN-MULTI S3a.1 write `init.py` first, then W1a.0, W1a.1 and W1a.6b, one at
a time. W1a.R uses the lock and golden lanes, not `init.py`; W1a.R and W1a.1 may land in either
order, one at a time. `cli/_sources.py` is shared with CONFIG-EXPLICIT C1 (the loader) and the H-1 move to
`cli/io/`: W1a.4a enters after C1 merges, and rebases onto the H-1 location if H-1 moves the module
first. Engine E1 and E3 each take the engine `__init__.py` export lane, one at a time; E1 also takes
a registry minor.

| Slice | Repo | Lines | Contents | Tests | Lane | After |
|---|---|---|---|---|---|---|
| E3 | engine | ~300 | `keyed_columns_for_config`, `KeyedColumn`, shared column walk, exports, 16.10 docstring line | AT-E7 (oracle and parity), export snapshot | engine `__init__.py` | none (can build now) |
| E1 | engine | ~700 | 6.1: `column_entry`, `ColumnSuggestion` fields, `StarterConfig.suggestions`, `SuggestionRef`, `ReviewVerdict` with `DROP`, `ReviewDecision`, `apply_review` with the empty-table refusal, `ReviewInputError`; `starter_config` builds through `column_entry`; note wording without "STORM" (E1b if over 750) | AT-E1 to AT-E4, AT-E8 | engine `__init__.py`; registry minor | S3-engine.2 (P7); SCAN-ML M1 (P2) |
| R-1a | engine | n/a | engine release carrying E1, E3 and S3-engine (and E0 if not yet released) | engine release checks | release lane | E1, E3 |
| W1a.0 | CLI | ~600 | AT-W1 characterization first; module-size sentry with the `init.py` pin at this base (AT-W28); CODEMAP rows; central `src/decoy/_reason_codes.py`, with the existing CI-manifest and static gate sets changed to derived views and their existing tests kept green; `TRANSFORM_IDS` replaced by `strategy_catalog()`; `_NAMESPACE_REQUIRED_STRATEGIES` deleted (wherever S3a.1 left it) in favour of `namespace_required`, with its golden diff if the bytes change. Needs only E0, which S3a.1's repin carries | AT-W1, AT-W28, completer test, central-registry tests for unique descriptors, derived-view agreement and whole-token validation (code plus newline refused), existing CI reason-code tests | `init.py`, `completers.py` | P8 |
| W1a.R | CLI | ~150 | repin to R-1a by the engine repin checklist; AT-W1 golden update only for the `namespace:` lines E1's `column_entry` adds and the `# REVIEW:` note lines AT-E8 rewrites; nothing else | AT-W1, full suite | lock, goldens | W1a.0; R-1a (P11) |
| W1a.1 | CLI | ~700 | `cli/wizard/_prompts.py` (Prompter protocol, terminal and scripted implementations, `has_terminal()`, `refuse_without_terminal`, the one-shot overwrite rule, the structured value-free `WizardError` renderer, `ONE_SHOT_FLAGS`, the `Key` enum, numbered and multi-select menus, typed-name and prefix match); `init.py` calls only: `--no-input`, the three-row rule, preset prompts behind the Prompter; move `test_init_scaffold_roundtrip.py` to `tests/e2e/wizard/`; update every existing test that runs `init` off a terminal in default mode (section 16); prompt-boundary sentry | AT-W4, AT-W1 still green, AT-W28 still green, Prompter unit tests | `init.py` | W1a.0 |
| W1a.2 | CLI | ~650 | `_state.py` (`WizardState`, origins, stable ids, step status), `_nav.py` (back, forward, go-to, stale marking), `steps/__init__.py` (Step protocol, `STEPS`); no-exc-text sentry | AT-W23 cases 6 and 7, state unit tests | none | W1a.1 |
| W1a.3a | CLI | ~450 | `_tree.py` from `strategy_catalog()` and the provider registry; no-strategy-literal sentry with its seeded shapes | AT-W24, AT-W6 (sentry half) | none | W1a.2 |
| W1a.3b | CLI | ~700 | `_field_review.py` (key-to-verdict mapping from the `Key` enum, options from `StrategyOption`, last-kept-field refusal), `steps/fields.py` | AT-W6 (options half), AT-W7, AT-W11, AT-W33, AT-W34, AT-W23 case 5 (the Fields half) | none | W1a.3a; W1a.R (`column_entry`, `apply_review`) |
| W1a.4a | CLI | ~700 | `steps/goal.py`, `steps/sources.py` (header file as a source role), `_preview.py` (`show_samples`, field samples, the shape rule), `cli/_sources.py` first-rows reader and `sniff_delimiter` | AT-W29, `_preview.py` unit tests for the shape rule | `_sources.py` (after C1; H-1 rebase note) | W1a.2; P3 (`column_names_file`) |
| W1a.4b | CLI | ~450 | `steps/scan.py` (summary, labels, confidence from the bucket), stale cases tied to Sources | AT-W31, AT-W23 cases 1 to 3 | none | W1a.4a; W1a.R (`scan_sources`, `starter_config`) |
| W1a.5a | CLI | ~650 | `steps/output.py`, `steps/secrets.py`, the wizard constants in `_mask_secret_guidance.py` | AT-W25, AT-W23 cases 4 and 5 | none | W1a.3b, W1a.4b; W1a.R (`keyed_columns_for_config`) |
| W1a.5b | CLI | ~450 | `steps/review.py`, `_checklist.py` | AT-W32, AT-W23 case 7 (Review half) | none | W1a.5a |
| W1a.6a | CLI | ~700 | `steps/start.py`, `_flow.py` (step loop, path-role check over the output YAML, every target and both read-role kinds, write step), `write_blocking_findings` in `cli/gate/_layers.py` with unit tests, the `init.path_collision` descriptor added to the central reason-code registry with its guard, renderer additions if needed. Still not wired into `decoy init` | AT-W9, AT-W10, AT-W22, AT-W26 and existing CI reason-code tests | none (`cli/gate/` has no named lane; one writer at a time) | W1a.5b |
| W1a.6b | CLI | ~650 | `init.py` cutover (terminal routes call `_flow`; the old direct file-scaffold terminal path deleted), the e2e sessions, G-ONE-EMITTER extension, "STORM" sentry, CHANGELOG, `docs/cli-reference.md`, roadmap row 32b and the shipped log | AT-W2, AT-W8, AT-W15, AT-W27, AT-W30, G-ONE-EMITTER | `init.py` | W1a.6a |

If a slice measures above about 750 lines at its first gate, the builder splits it along the module
lines in its Contents column before review, and the plan's table is updated in the same push.

Section 22 decisions against slices: 14.1 and 14.2 block no 1a slice; 14.3 touches E1 (the `DROP`
verdict) and W1a.3b (the `d` key) and blocks neither from starting (section 14).

Test depth (`testing.md`): T0 per edit; T1 impact-selected per commit and slice head
(`scripts/dev/gates.sh --baseline-file`). Escalation to the full suite, diffed against the stored main
baseline: E1 and E3 (engine public exports, a frozen surface; E1 also the reason registry); W1a.0
(central reason-code registry and derived frozen views); W1a.R (lock change); W1a.1 (moved tests and
changed test fixtures); W1a.6b (frozen `decoy init` contract);
any slice that edits `tests/sentry/test_sentry_manifest.py` or `sentry_registry.toml` only if the
change goes beyond adding its own entries. The other slices add unwired modules and run T1 plus the
T2 gate set. Tests run on the Mac first or `~/bin/vm-run`, never on the devbox queue. Worker
evidence rules: the 2026-11-07 plan section 14 applies to every slice unchanged.

## 12. Reason codes

- Engine: the six E1 identities in 6.1, each in its existing family (`pre_scan`, `config`). E1 builds
  against a provisional next minor on its base, and REG-RENUMBER renumbers `REGISTRY_VERSION`, every
  `since=` and the manifest fixture name to `main + 1` at merge (`scripts/dev/registry_renumber.py
  --check` in the merge gate). This plan does not name a registry version. E3 adds no identity.
- CLI-facing: one descriptor registry in `src/decoy/_reason_codes.py` owns each code and its scope.
  The existing CI-manifest `REASON_CODES` (`src/decoy/ci/contracts.py:83`) and static gate
  `_CLI_GATE_CODES` (`src/decoy/ci/rule_codes.py:39`) become derived views with their current
  contents pinned. The registry rejects duplicate descriptors and validates each code as a whole
  token with `fullmatch`; its test refuses a valid code plus a newline. The init view and
  constructor use the same registry. Phase 1a adds only
  `init.path_collision`, its one emitted code, because the guard (AT-W26) fails on a registered init
  code with no emitting path. Each later phase adds its descriptors with their emitters: 1b
  `init.draft_invalid`; Phase 2 `init.answers_invalid`, `init.yaml_changed`,
  `init.yaml_edit_unsupported`, `init.yaml_symlink`; the findings review `init.report_missing`,
  `init.report_schema`, `init.report_stale`. The nine-code set of spec 12 is the end state.
- V2-LOG: the wizard's own fixed error lines are folded into the VALUE-FREE-ERRORS converter
  (`cli/_yaml_errors.py`, row 24a) in V2. In 1a they are fixed text plus names and a relayed config
  error already goes through that converter.
- V2-LOG: `write_blocking_findings` treats a config or compile finding with `extra` set as a builder
  bug even when it represents a missing optional extra. Phase 1a cannot reach that shape because it
  writes no `pre_scan` detectors or NER configuration. Revisit the classification when the wizard
  writes `pre_scan` detectors.

## 13. Frozen contracts touched

- `decoy init` flags: additive (`--no-input`, `--no-samples`).
- Behavior changes, pre-GA hard delete (CLI `CLAUDE.md`): off a terminal in default mode, bare
  `decoy init`, `--preset` and `decoy init FILE` now refuse with exit 1 (owner answer, 2026-11-08).
  In a terminal, `decoy init FILE` now runs the wizard instead of writing the unreviewed starter.
- Exit codes: the six public codes, no new code. `gate_exit_code` is unchanged; the new
  `write_blocking_findings` is internal to the CLI.
- Existing `decoy ci` manifest reason codes and static validation rule ids: unchanged byte for byte;
  their closed sets become derived views of the central registry and existing snapshots pin them.
- `--json` record of `init`: unchanged (the wizard never runs with `--json`).
- Engine public API, additive: E1's names (2026-11-07 plan section 12 list, plus `ReviewVerdict.DROP`
  and the `pre_scan.review_empty_table` reason)
  and E3's `keyed_columns_for_config` and `KeyedColumn`. A compatibility-contract note in engine
  `docs/compatibility-contract.md` for each.
- `PipelineConfig`: untouched.

## 14. Open decisions (spec 22, kept open)

Not decided here. Each names the 1a slice it blocks, if any.

1. **Findings review command home.** Kept as `decoy init --review-findings PIPELINE --report FILE`
   for now (owner, 2026-11-08: "figure that out later"). Blocks no Phase 1a slice: the findings review
   (W3.2) is outside 1a. It blocks W3.2's flag wiring when that part is planned.
2. **Tokenize and the `vault: true` column flag.** Blocks no Phase 1a slice: `tokenize` is not in the
   1a tree and the Tokenize goal is Phase 3.
3. **`drop_column` under CONFIG-EXPLICIT.** Whether a dropped column counts as declared under rule 3
   is CONFIG-EXPLICIT E2's definition. The E2 build handoff (vault
   `handoffs/phase0.5/p05-config-explicit-build-handoff.md`, line 65) counts the columns of every
   `drop_column` transform as declared, which is what the 1a `DROP` verdict relies on. E2 is a
   prerequisite of S3-engine.1, so it merges before 1a builds. This touches E1 (`DROP`) and W1a.3b
   (the `d` key) only. Keeping a `columns` entry for a dropped column is not a fallback: the engine
   refuses a column that is both declared and dropped (`config/_tables.py:439-450`). So the
   fallback is: if E2 as merged has no acceptance test that pins "a `drop_column` column counts as
   declared", the `d` key and the `DROP` verdict are withdrawn from 1a (E1 ships without `DROP`,
   W1a.3b omits `d`, AT-W33 and the drop cells of AT-E1 and AT-E4 move with them to 1b). W1a.3b's
   builder checks for that E2 test at its base and records the result. It blocks neither slice from
   starting.

## 15. Owner answers kept

- 2026-11-07, on the 2026-11-07 plan: Q1 the findings review is `decoy init --review-findings`
  (spelling to revisit before release); Q2 a rejected finding persists as `post_scan.dismissed`; Q3
  `unlisted: confirm` is allowed in an answers file. Q2 and Q3 apply in later phases.
- 2026-11-08, on spec v3 section 22:
  1. Field review keys are the v2 keys: Enter, `r`, `o`, `k`, `d`, `b`, `q` (5.3).
  2. With no terminal, bare init and `init FILE` refuse with exit 1, while explicit one-shot flags
     (`--no-input`, `--json`, `-q`, and `--answers` once Phase 2 adds it) keep working (5.2).
  3. The findings review stays as `decoy init --review-findings --report FILE` for now (14.1).
  4. In flagged-only mode, unflagged fields pass through and need a confirm on Review (1b, spec 5.4.1
     and 5.11).

V1 bar (standing): only a function break, data loss or a non-admin leak blocks V1. Gate findings
outside that bar and outside the guarantee in 1.4 are recorded as follow-ups.

## 16. Findings while planning

1. **More existing tests hit the no-terminal rule than spec 15 says.** Spec 15 names only
   `test_init_scaffold_roundtrip.py::test_init_stdout_with_dash`. At CLI `08124b5` these also run
   `init` in default mode under `CliRunner`, which is not a terminal:
   - `tests/e2e/test_init_command.py` lines 345, 362 and 427 (the `"init"` token of each invoke; the
     #114 path tests, which drive the preset prompts with `input=`);
   - `tests/e2e/test_keyed_secret_guidance.py:177` (preset with `input=`) and `:190` (`init cards.csv
     -y`);
   - `tests/e2e/test_source_csv_dialect.py:273` (`init FILE --output`);
   - `tests/e2e/cli_fmt/test_target_format_readers.py:510` (`init FILE --output --yes`).
   S3a.1 and CONFIG-EXPLICIT C2 may change some of these first. W1a.1 re-runs the census on its base
   (`grep -rn '"init"' tests/`) and fixes each case without weakening it. A case that checks one-shot
   output adds `--no-input`. A case that checks the prompts runs through the scripted `Prompter` with
   `has_terminal()` patched by one fixture, and keeps its assertions. AT-W4 exercises the real probe.
2. **The `init.*` closed set cannot hold all nine codes in 1a.** The guard of spec 12 fails on a
   registered code with no emitter, so 1a registers one code (section 12).
3. **The brief's label for E1.** "CONFIG-EXPLICIT E1 (`apply_review`)" mixes two parts. The code being
   built now under CONFIG-EXPLICIT E1 is the `has_header` and `column_names_file` schema slice (P3).
   `apply_review` is the 2026-11-07 plan's E1 (P9), which has no branch yet.
4. **No answers file in 1a.** Spec 17 puts `--answers` in Phase 2, so the 2026-11-07 AT-W3 parity
   test and the stale-confirm test AT-W19 move there.
5. **`gate_exit_code` cannot drive a scaffold write.** It returns 1 for any error and 5 for capacity,
   and blocks on preflight errors, which spec 14 says must not block `decoy init`. Hence the
   `write_blocking_findings` classifier (5.6).
6. **The header file is a second source path.** `decoy run` reads `column_names_file`, so a YAML or a
   target written over it loses the user's names. The 2026-11-07 role set did not include it.

## 17. Pre-mortem

- **CI hangs or silently changes output.** The three-row rule, one terminal probe, AT-W4 and the
  prompt-boundary sentry.
- **A user's pick is lost after going back.** Answer origin and AT-W23.
- **The Secrets step and `decoy run` disagree on keyed-ness.** One engine walk for both functions
  (E3), AT-E7 and AT-W25.
- **A typed `r` to `hash` writes a config that fails at run time.** `column_entry` and AT-W7.
- **The prerequisites slip.** E3 builds now. E1 waits only for S3-engine.2 and M1. W1a.0, W1a.1,
  W1a.2 and W1a.3a need only E0, which S3a.1's repin carries, so they can merge before R-1a once
  S3a.1 has merged. W1a.4a needs P3 as well. W1a.R and every slice after W1a.3a that calls
  `column_entry`, `apply_review`, `scan_sources` or `keyed_columns_for_config` waits for R-1a. The
  row stays in progress until W1a.6b lands.
- **A user drops every field and loses the session.** Decision-time refusal plus the engine backstop
  (AT-W33, AT-E1).
- **The YAML or a target overwrites an input, or two targets share a file.** Read/write path-role
  check, never waived by `-y` (AT-W22).
- **Builders re-litigate scope.** Sections 1.2, 1.3 and 1.5.

## 18. Owner questions

None blocking. Every choice above takes the recommended option under the standing V1 rule.

## 19. Review resolutions

### Round 1 (Dennis on `2e09ff7`)

| Id | Resolution |
|---|---|
| H1 | Header file is included in the one path-role check, never waived by `-y`; Guarantee 8, 5.3, 5.6, section 7 and AT-W22 were updated. Round 2 M3 later narrowed the refusal to pairs containing a write role and added target-target coverage |
| H2 | `d` refused on a table's last kept field (5.3, AT-W33); `apply_review` raises `pre_scan.review_empty_table` as the backstop (6.1); Guarantee 9, section 7, 9.4 item 5a, AT-E1 cells, AT-E4 property |
| M1 | One classifier `write_blocking_findings` in `cli/gate/_layers.py` by `GateFinding.layer`; capacity is written, shown and exits 0; 5.6, 5.8, 7, 9.1, AT-W10 |
| M2 | W1a.0 needs only E0 (via S3a.1's repin); the repin and the `column_entry` golden diff move to the new W1a.R; pre-mortem and P-table made consistent |
| M3 | W1a.3, W1a.4, W1a.5 and W1a.6 split into a and b halves with sizes including tests; a measured-size split rule added |
| M4 | Secrets and Review wording comes from `_mask_secret_guidance.py` (new wizard constants there); the typed reference passes `_validate_mask_secret_ref_shape` (`api.py:96`); reuse inventory, AT-W25, AT-W32 |
| M5 | Every wizard sentry uses `tests/sentry/io_policy/_calls.py`; no wizard scanner; CODEMAP row and class table fixed |
| M6 | E1 owns the "STORM"-free note wording with engine test AT-E8; AT-W27 is CLI side only |
| M7 | AT-E7 gains a pinned oracle table from `test_requirements_matrix.py` cases; M-E7b mutates the shared walk |
| M8 | 14.3 fallback is now "withdraw `d` from 1a" if no E2 test pins dropped-means-declared; the impossible keep-a-declaration fallback removed |
| M9 | One character-class rule over the whole value, domain included; section 3, AT-W29 example, AT-W8 domain canary, M-W8e, M-W29c |
| M10 | AT-W28 moves to W1a.0 and pins `init.py` at that base; the three-row and overwrite rules live in `_prompts.py` |
| L1 | Section 0 and section 11 state the amendment of spec 17's "one CLI slice" |
| L2 | Row (c) with an existing output exits 1 in a terminal too (5.2); AT-W4 pty cell, M-W4d |
| L3 | New sentries go in `SENTRIES` and `scripts/dev/sentry_registry.toml` (placement table) |
| L4 | One CLI-wide code registry was initially logged as V2; the final DESIGN review superseded that disposition and moved the registry into W1a.0 |
| L5 | VALUE-FREE-ERRORS row 24a and `cli/_yaml_errors.py` cited (reuse inventory, class 1, section 12 V2 fold) |
| L6 | `cli/_sources.py` lane note: after CONFIG-EXPLICIT C1, rebase on H-1 (section 11) |
| L7 | With `-o -`, paths are relative to the current directory (5.1, 5.6) |
| L8 | Field samples come from the preview's first rows via `cli/_sources.py`, routed through `_preview.py` (5.3) |
| L9 | Start is a step (`steps/start.py`) so `STEPS` equals the progress bar; `_review.py` renamed `_field_review.py`; one `Key` enum feeds the key line, help and mapping (AT-W34) |
| L10 | No-strategy-literal sentry shapes listed in AT-W6 with seeded cases |
| L11 | `test_init_command.py` lines corrected to 345, 362 and 427 (the `"init"` tokens) |
| L12 | Reuse inventory names the public `decoy_engine.strategy_catalog` and `decoy_engine.secret_providers` exports; the private helper is marked engine-only |

No LOW item was skipped.

### Round 2 (Dennis, 2026-11-08)

| Id | Resolution |
|---|---|
| M1 | AT-W10 now asserts exit 1 for Ctrl-C, EOF and `q`, and exit 3 for scan, atomic, config and compile failures; every row asserts no output or temp file |
| M2 | AT-W1 and W1a.R allow exactly two visible golden-diff kinds: the named `namespace:` lines and the `# REVIEW:` lines AT-E8 rewrites |
| M3 | Guarantee 8, 5.6, section 7, AT-W22 and class 7 distinguish read and write roles; read roles may alias each other, while every write-role collision and target-target collision is refused; M-W22d skips target-target checking |
| M4 | Any `apply_review` raise at write time is a builder bug: exit 3, no write, and only fixed codes plus table or column names; AT-W10 injects `ReviewInputError`. Final self-review applies the same rule to Review `y` |
| L1 | Exit paths are ordered 1 through 10 and the duplicate existing-output row was removed |
| L2 | P2 records SCAN-ML M1 merged as engine #405 at `38951412`; `ModelRef` is `detection/types.py:42` on main |
| L3 | W1a.R and W1a.1 may land in either order, one at a time; W1a.R uses the lock and golden lanes and does not edit `init.py` |
| L4 | Section 9.3 states that SCAN-MULTI V1 infers no relationships, so key-column refusals are unreachable in 1a |
| L5 | AT-W9 expects one error line followed by the findings list on the exit-3 gate path |
| L6 | Section 12 logs the future missing-optional-extra classification issue and its 1a unreachability |

### Final self-review

| Label | Resolution |
|---|---|
| V1 | AT-W22 now supplies target paths through the only Phase 1a surface that has them, the Output prompts, instead of requiring nonexistent target flags; the collision coverage is unchanged |
| V1 | AT-W9 now applies the one-error-line rule to error exits, not successful writes that show preflight findings |
| V1 | Guarantee 4 and 5.6 now branch the write sink: file output uses `_atomic`, while `-o -` emits the one renderer's bytes to stdout only after the gate and opens no temp file |
| V1 | Review `y` and Enter now share fold-and-render preparation; `apply_review` builder errors are covered on both paths, while only Enter gates and opens the output sink |
| DESIGN | The proposed third hand-written reason-code set was removed. W1a.0 creates one shared descriptor registry at the CODEMAP line 48 placement; the existing CI-manifest and static gate sets and the new init set are derived views with agreement guards |
| V2-LOG | Guarantee 5 now excludes source cell and secret values while permitting counts, names and detector ids, matching the owner-set value definition and SCAN-MULTI's integrity-count notes |
| V2-LOG | AT-W29 spells out the pipe delimiter so its Markdown table row is not split by a literal pipe character |
