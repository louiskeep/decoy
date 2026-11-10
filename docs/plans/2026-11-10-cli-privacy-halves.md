Status: plan

# CLI privacy halves: roadmap rows 24c, 24f and 24g

Owner: Cam. Author: Opus (plan author, CLI). Date: 2026-11-10. Scope: CLI only. Three small slices.

Bases: CLI `origin/main` `fb7f810` (#168), read 2026-11-10. Engine tag `v0.21.0` (`b1e4aa9a`), which holds
engine #415 (`44d6afe2`) and #420 (`3af398d5`). The CLI pin to 0.21.0 is CLI PR #169
(`chore/repin-engine-0.21.0`, head `02bc404`, open). Every slice here builds on #169 after it merges.

This plan does not re-design. The engine plans for these rows were reviewed and gated, and they already
specify the CLI parts. This plan adopts them, records what changed since they were written, and cuts the work
into buildable slices:

- `E:docs/plans/2026-11-08-qa-fit-redact.md` on engine branch `plan/qa-fit-redact` (`896fee9e`; Dennis rounds 1
  and 2, Codex gate). Its slices C1 and C2 are the CLI halves of 24f and 24g. Cited below as "FR".
- `E:docs/plans/2026-11-08-scan-redact.md` on engine branch `plan/scan-redact`. Its slices S2a and S2b are the
  CLI half of 24c. Cited below as "SR".

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`
(PLAN, Proportion), `profiles/local-operations.md`, `feature-dev.md`, `reuse-first.md`, `scope-discipline.md`,
`cross-cutting-concerns.md`, `architecture.md` (layout), `api-and-compatibility.md`, `security.md`,
`testing.md` (Test depth), `code-review.md`, `catalogs/recurring-defects.md`, `workspace-and-vcs.md` (Commit
messages), `documentation.md`. Also CLI `CODEMAP.md` ("Where things go"), `docs/ROADMAP.md` rows 24c, 24f,
24g, 24l, 24w and 36, and the QA records `docs/records/2026-11-08-cli-qa-first-user.md` (High 5),
`docs/records/2026-11-08-cli-qa-distribution-integrity.md` (H2, H3) and
`docs/records/2026-11-10-cli-qa-generation-distribution-models.md` (H6, H7).

Risk: R2 for slice F (value leak in a written artifact). R1 for slices G and C (wording, read order, a demo
file of bundled sample data, guard tests).

## 1. What changed since the engine plans

1. **CLI #166 (SCAN-MULTI S1c.1, merged 2026-11-10) already did most of the 24c CLI half.** `decoy scan
   --output` and `--output -` write the value-free `scan-set/v1` core (`scan_set_to_dict(detail=False)`,
   `src/decoy/cli/scanning/_multi.py:451`). `scan fields`, `show` and `diff` read through one loader that
   drops `top_values`, sentinels and every other value member of a legacy file
   (`src/decoy/cli/io/_scan_set.py:1-20`). So SR routes R1 to R4 are closed, and stricter than SR asked: no
   column keeps values, not only flagged ones.
2. **What is left for 24c:** the demo still writes `profile.to_dict()` raw (`src/decoy/cli/demo.py:148`, SR
   route R5); `decoy explain security` still says scan JSON "can contain sensitive aggregates and top values"
   (`src/decoy/cli/explain.py:424`); the `decoy.scan()` docstring still says the scan file is the profile
   (`src/decoy/api.py:605`); and the opt-in flag. SR section 3 already ruled that after S1c the opt-in moves
   to the per-table detail behind LIB L2 `--output-detail` (roadmap row 36), because the core has nowhere to
   hold values. Owner question Q1.
3. **The engine S1a wiring that SR planned did not land.** At `v0.21.0`, `scan_set_to_dict(s, detail=True)`
   embeds the raw `profile.to_dict()` and takes no `include_values` (`profiling/scan_set.py:513-527`). No CLI
   path asks for `detail=True` today, so nothing leaks now. Row 36 must not call it until the engine routes
   `detail` through `profile_document`. Recorded as finding P1.
4. **24f grew on 2026-11-10 (H6, H7).** The DI models QA found leaks the engine predicate does not flag:
   a label held by one row, the exact `min` and `max` of an unflagged number column, and short free text
   (30 or fewer distinct strings, classed categorical). Engine `distribution_snapshot_document` hides only
   value-sensitive columns (detector hit, `pii_score` at least 0.6, or near-unique;
   `profiling/_value_redaction.py:290-303`). The CLI cannot close these without copying data rules, which
   belong in the engine (CODEMAP Conventions). Owner question Q2.
5. **Row 24l C1 and row 24w C1 touch the same call.** `distribution_snapshot_document` always passes
   `cell_format=True` (`profiling/_snapshot_values.py:252-261`), so slice F also delivers 24l C1's "pass
   `cell_format=True`" item (the 24l plan says that keyword moves with 24f). Row 24w C1 (`--joint-max-cells`)
   will pass `contingency_top_k` to the same call. Both rebase on slice F.
6. **The engine APIs the CLI calls exist at `v0.21.0`:** `decoy_engine.distribution_snapshot_document(df, *,
   source_label, include_values=False, joint_columns, ..., profile_row_cap)` (`_snapshot_values.py:222`),
   `decoy_engine.quality.check_dp_fit_request(column_schema, *, epsilon, delta, numeric_bins)`
   (`quality/dp.py:265`), `decoy_engine.profile_document(profile, *, include_values=False)`
   (`_value_redaction.py:473`). Reason code `plan.statistical_snapshot_values_redacted` (registry 1.11.0) and
   its hint name `--include-values` (`generation/statistical/_numeric_shape.py:298-310`). Today the CLI has no
   such flag, so the engine's own fix hint points at an option that does not exist. That is a function break.

## 2. Guarantee and non-goals

Guarantee (what these slices promise):

1. `decoy fit` without `--epsilon` writes no raw cell value of a value-sensitive column unless the user passes
   `--include-values`. The engine decides which columns; the CLI reads `redacted_columns` and never evaluates
   the predicate (FR Guarantee 1 and 2).
2. `decoy fit` names the withheld columns (names only) and says what to do next.
3. `--include-values` works, warns on stderr, and is a usage error with `--epsilon`.
4. On an uncertified host a well-formed `decoy fit --epsilon` prints one plain line and a next step, exits 3,
   and reads only the CSV header. Request errors keep their typed exit-1 codes before the gate (FR Guarantee 5).
5. `decoy fit --help` and `decoy explain differential-privacy` say DP runs only on a certified install.
6. No CLI surface writes a raw `profile.to_dict()`; `decoy demo` writes the engine-redacted profile document.

Non-goals:

- Rare labels, exact `min`/`max` and short free text in unflagged columns (H6, H7). Engine work, Q2.
- A scan opt-in flag before row 36, unless Q1 says otherwise.
- Certifying more DP hosts (DPS work), and DP fit speed (DI models QA H8, not on the roadmap).
- Redacting snapshot files on read. No CLI command prints a snapshot (FR follow-up F2).
- The `decoy.scan()` library return value. It is the caller's own process and stays raw.

## 3. Behavior per row

### 24f (slice F): `decoy fit` uses the engine document (FR C1)

- `fit.py:422` calls `distribution_snapshot_document(df, source_label=source.name,
  include_values=include_values, joint_columns=joint_pairs or None, profile_row_cap=10_000)` in place of
  `compute_distribution_snapshot`. 10,000 head rows is the `decoy scan` default sample.
- New option `--include-values`: "Keep real values of sensitive columns in the snapshot. The file then holds
  real data." With `--epsilon` it is usage error `dp_usage_include_values`, exit 1, in the existing D0 block,
  before any CSV read.
- Human success output, when `redacted_columns` is not empty and the policy is `flagged-redacted/v1`:
  `N sensitive column(s) withheld: a, b, c (no cell values kept; numbers reduced to one range, dates to years)`
  and `hint: to sample these as categories, re-run with --include-values (the file then holds real data).
  A DP release (--epsilon) needs a certified DP install; see decoy explain differential-privacy.` (Q3.)
- With `--include-values`: stderr `warning: <path> holds real values of N sensitive column(s): a, b, c. Do not
  share or commit it.`
- `--json` success payload gains `value_policy` and `redacted_columns` (additive).
- Docs: guide pages 01, 03 and 06 of `docs/guides/shape-and-privacy/` stop saying a plain snapshot always holds
  real values; page 06 gains the `statistical_snapshot_values_redacted` entry. `docs/cli-reference.md` is
  regenerated.

### 24g (slice G): DP gate message through the public check (FR C2)

- DP mode reads the header only (`nrows=0`), runs the existing name checks (`dp_columns_omitted`,
  `dp_schema_column_missing`), calls `check_dp_fit_request(column_schema, epsilon=..., delta=...,
  numeric_bins=...)`, then reads the body.
- The exact read and the DP body read merge into one `pd.read_csv(source, **read_kwargs)` call, so `fit` keeps
  2 read sites and the CSV-read pin does not move (FR C2, "Read sites stay at two").
- After the body read, its columns must equal the header's, else usage error `dp_source_changed`, exit 1.
- The read-error catch (`fit.py:412-414`) stops printing `str(exc)`. Human and JSON say only that the named CSV
  could not be read.
- On `dp_platform_uncertified` or `dp_stack_uncertified`, human stderr shows `error: DP fit is not available on
  this install: it runs only on a certified platform and package set.` and `hint: run decoy fit without
  --epsilon (sensitive columns are withheld by default); see decoy explain differential-privacy.` The engine
  message (code, platform, fingerprint) prints only under `--verbose`. Exit 3 as today.
- `--json` keeps `code` (the engine code), `message` (the engine text) and `error`; `hint` carries the new
  next step. Scripts keep keying on `code`.
- Help: `--epsilon` help gains "Runs only on a certified DP install; see decoy explain differential-privacy."
  The `differential-privacy` topic summary becomes "Fit a DP release with `decoy fit --epsilon` (certified
  installs only)." and its body opens with the gate and the no-DP alternative.
- Tests that stub only `fit_dp_snapshot` also stub `check_dp_fit_request` (FR C2 lists them). That is a fixture
  change, not a weaker assertion.

### 24c (slice C): the last raw scan route and stale text (SR S2a R5, S2b text)

- `demo.py:148` writes `profile_document(profile)` in place of `profile.to_dict()`. The demo data is the
  bundled sample, so this is not a user-data leak; it removes the last raw scan writer and teaches the right
  shape. `load_scan_set` still reads the file through its legacy path (extra keys are ignored).
- `explain security`: "Saved scans hold counts, rates, types and detector ids, never cell values. A plain fit
  snapshot withholds sensitive columns' values unless you pass --include-values."
- `api.py:605` docstring: the object is the in-memory profile; `decoy scan --output` writes the value-free core.
- If Q1 answers (b), slice C also adds `decoy scan --include-values` (about 50 more lines; see Q1).

## 4. Failure modes

| # | Failure | Guard |
|---|---|---|
| F-1 | `fit` keeps calling `compute_distribution_snapshot` for output | AT-F8 AST guard |
| F-2 | The CLI re-derives sensitivity (a copied threshold or predicate) | AT-F8 also bans `pii_score` reads and `is_value_sensitive` calls in `fit.py`; the CLI reads `redacted_columns` |
| F-3 | `--include-values` used silently in CI | stderr warning naming columns and path; AT-F2 |
| F-4 | The engine fix hint names a flag the CLI lacks | AT-F5 runs the hint's advice end to end |
| F-5 | DP refusal still reads the CSV body first, or preempts a typed request error | AT-G1 `read_csv` spy; AT-G3 request-error cells |
| F-6 | The CSV changes between header and body reads | `dp_source_changed`; AT-G4 |
| F-7 | A parser exception echoes a cell through output | fixed read error, no `str(exc)`; AT-G5 canary |
| F-8 | The plain DP text drops the detail an operator needs | engine message under `--verbose` and in `--json`; AT-G2 |
| F-9 | A new CLI route writes a raw profile again | AT-C2 AST guard over `src/decoy` |
| F-10 | Existing loop tests pass only because the fixture has no sensitive column | AT-F1 uses the QA fixture with SSN, name and id; a precondition asserts `redacted_columns` is not empty |

## 5. Established solutions and reuse inventory

The established solutions were surveyed and cited in FR section 2 and SR section 2: Google Cloud DLP
`include_quote` (findings omit the quote unless asked), ydata-profiling `sensitive=True`, Presidio `replace`,
statistical disclosure control global recoding (Hundepool et al. 2012, sections 3.4.2 to 3.4.3), HIPAA Safe
Harbor year-only dates. All of it lives in the engine. This plan adds no custom data logic; the CLI calls the
engine's public functions and renders names.

| Need | Reuse | New code |
|---|---|---|
| Which columns are sensitive | engine `redacted_columns` in the document | none |
| Write the snapshot | `distribution_snapshot_document`, then `write_local_target` (`fit.py:497`) | none |
| DP request check | `decoy_engine.quality.check_dp_fit_request` | none |
| Error rendering | `_emit_error` in `fit.py` | a `verbose_detail` path for the engine text |
| Scan profile document | `decoy_engine.profile_document` | none |
| AST guards | `tests/sentry/io_policy/_calls.py` (`bindings`, `qualified`, `call_sites`) | two small sentry files |
| QA fixture | `tests/fixtures/qa_first_user/patients.csv` (copied to `tmp_path`) | none |
| Dev-host DP refusal code | `tests/dp_env.py` (`expected_dp_refusal_code_required`) | none |

## 6. Design notes

No new module, abstraction or variant. All source edits land in existing files: `cli/fit.py` (534 lines;
about 690 after F and G, under the 800 cap), `cli/explain.py`, `cli/demo.py`, `api.py`. If `fit.py` would pass
800 lines, the builder stops and asks: there is no `fit` sub-package and flat `cli/` takes no new module.

Choke points (cross-cutting rule):

- Snapshot output: the one engine writer `distribution_snapshot_document`. Guard AT-F8 fails when any module
  under `src/decoy` calls `compute_distribution_snapshot`. Mutation: restore the old call at `fit.py:422`
  (AT-F8 red).
- Profile output: the one engine writer `profile_document`. Guard AT-C2 fails when a module under
  `src/decoy/cli` calls `.to_dict()` on a name bound from `profile_columns(...)`. Mutation: restore
  `profile.to_dict()` at `demo.py:148` (AT-C2 red). The realistic bypass is exactly that line.
- DP request decision: the engine's shared preparation behind `check_dp_fit_request`. Guard in AT-G3: an AST
  check that `fit.py` calls no private engine DP validator. Mutation: move the gate call after the body read
  (AT-G1 red).

## 7. Enumerations

### 7.1 Exit paths (`decoy fit`)

- `0` success (`src/decoy/cli/fit.py:505-533`): new withheld-columns line, JSON keys.
- `1` D0 usage errors (`src/decoy/cli/fit.py:337-395`): adds `dp_usage_include_values`.
- `1` unreadable CSV (`src/decoy/cli/fit.py:412-414`): text no longer carries `str(exc)`.
- `1` `dp_source_changed` (new): body columns differ from the header.
- `1` DP request errors (`dp_epsilon_invalid` and the rest): now raised by `check_dp_fit_request` before the
  body read; same codes.
- `3` DP uncertified (`src/decoy/cli/fit.py:478-484`): moved before the body read; plain text.
- `3` write failure (`src/decoy/cli/fit.py:496-502`): unchanged.
- `decoy demo` and `decoy explain` exit paths: unchanged.

### 7.2 Routes (every way a profile or snapshot reaches a file or a user)

| # | Route | Site | After |
|---|---|---|---|
| R1 | `decoy fit` exact mode | `src/decoy/cli/fit.py:422` | `distribution_snapshot_document` |
| R2 | `decoy fit --epsilon` | `src/decoy/cli/fit.py:475` | unchanged release; gate moved earlier |
| R3 | `decoy scan --output` and `--output -` | `src/decoy/cli/scanning/_multi.py:451` | unchanged (value-free core since #166) |
| R4 | `scan fields`, `show`, `diff` | `src/decoy/cli/scan.py:493-495` | unchanged (one loader drops values) |
| R5 | `decoy demo` scan.json | `src/decoy/cli/demo.py:148` | `profile_document` |
| R6 | `decoy.scan()` library | `src/decoy/api.py:608-641` | unchanged, in memory; docstring fixed |
| R7 | `decoy init FILE.csv` | `src/decoy/cli/init.py:437-439` | unchanged: uses names and stats, writes no value |

### 7.3 FK shapes

- N/A: no slice reads, writes or checks a relationship. Joint contingency cells of a sensitive column are
  emptied by the engine (FR section 3), and the CLI only passes `--joint` pairs through.
- N/A for `decoy scan` relationships: the core's `relationships` member is value-free and untouched.

### 7.4 Fields (every key or option these slices add)

- `--include-values` on `decoy fit` (bool, default off).
- `value_policy` in `fit --json` (`flagged-redacted/v1` or `raw`), copied from the document.
- `redacted_columns` in `fit --json` (list of column names), copied from the document.
- `hint` text in the DP error JSON (existing key, new text).
- `value_policy` and `redacted_columns` in the demo's `scan.json` (written by the engine).

### 7.5 Output surfaces

- Snapshot file (`fit --output` or `<csv>.snapshot.json`): redacted by default.
- `fit` stdout: withheld-columns line and hint.
- `fit` stderr: `--include-values` warning; DP refusal text; engine detail under `--verbose`.
- `fit --json`: two new keys; DP error `hint`.
- `fit --help`, `explain differential-privacy`, `explain security`, `docs/cli-reference.md`, guide pages.
- `decoy demo` `scan.json`.

## 8. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | raw cells in fit snapshots (R1) and the demo scan file (R5); a cell echoed in a read error | engine writers `distribution_snapshot_document` and `profile_document`; fixed read-error text | AT-F1, AT-F4, AT-C1, AT-G5 | M1: pass `include_values=True` by default (AT-F1 red); M1b: put `str(exc)` back in the read error (AT-G5 red) |
| 2 | Cleanup missing on an exit path | N/A: no temp files; writes stay on `write_local_target`, which leaves no partial file | N/A, reason given | existing `tests/e2e/test_atomic_output.py` fit row stays green | N/A |
| 3 | State and ordering | gate after the body read; request errors preempted by the gate | header read, name checks, `check_dp_fit_request`, then body read | AT-G1 spy, AT-G3 cells, existing name-check-first tests | M3: call the gate after the body read (AT-G1 red) |
| 4 | Route parity and silent fallback | a route keeps the raw writer; a CLI copy of the predicate; a third read site | one engine writer per artifact; one merged body read | AT-F8, AT-C2, CSV-read sentry pin 2 | M4: restore `compute_distribution_snapshot` (AT-F8 red); M4b: keep the DP body read separate (CSV-read sentry red) |
| 5 | Referential integrity | `condition_on` through a withheld column must be refused, not sampled | engine refusal `statistical_snapshot_values_redacted` | AT-F5 joint cell | M5: re-fit without `--include-values` in the escape cell (AT-F5 red) |
| 6 | Untrusted producer | the CLI trusting a hand-edited snapshot marker | the CLI only reads `redacted_columns` of a document it just built; the engine refuses malformed markers at load | AT-F4; engine AT-12 | M6: read `redacted_columns` from a loaded file instead of the built doc (AT-F4 forged-file cell red) |
| 7 | TOCTOU, check-then-use | DP name checks on the header, then body read | body columns must equal header columns, else `dp_source_changed` | AT-G4 | M7: drop the comparison (AT-G4 raises `KeyError`, red) |
| 8 | Weak tests | a fixture with no sensitive column passes trivially; a spy that never sees a read | AT-F1 precondition `redacted_columns` not empty; AT-G1 precondition that the spy is installed on the module the CLI calls | AT-F1, AT-G1 | M8: swap the fixture to the WS3 `_source_csv` (AT-F1 precondition red) |
| 9 | Behavior-preserving refactor drift | merging two `read_csv` calls must not change exact or DP boxing | one call with mode-chosen kwargs, comment kept | existing `TestFitDpFlagGrammar` boxing tests | M9: drop `keep_default_na=False` from the DP kwargs (boxing test red) |
| 10 | Frozen contract drift | `fit --json` keys, exit codes, the snapshot file default content | additive JSON keys; exit codes unchanged; CHANGELOG entry for the default change | AT-F3, existing exit-code tests | M10: rename `redacted_columns` in the payload (AT-F3 red) |

## 9. Acceptance tests (red first)

Run with engine 0.21.0 installed (PR #169 head or main after it). "Red on base" means the test fails on
`origin/main` plus #169. New tests go in `tests/e2e/first_user/test_items_privacy.py` unless named otherwise.

Slice F (24f):

- **AT-F1** QA repro: `decoy fit patients.csv -o snap.json` on a copy of the QA fixture. Precondition:
  `redacted_columns` names `ssn`. The file, stdout and stderr hold no fixture name, SSN or id; stdout names the
  withheld columns; exit 0. Red on base (raw `top_values`).
- **AT-F2** `--include-values`: the file holds the SSNs and `value_policy: raw`; stderr warning names the
  columns and the path. Red on base (no option).
- **AT-F3** `--json` success payload has `value_policy` and `redacted_columns` and no fixture value. Red on base.
- **AT-F4** The CLI line lists exactly the document's `redacted_columns`, and a forged snapshot file at the
  output path before the run does not change it. Red on base.
- **AT-F5** fit, then `decoy validate config` on a generate config: a `type: statistical` categorical column
  on `ssn` and a `condition_on` through it fail exit 1 with `statistical_snapshot_values_redacted` and the hint
  text; after re-fit with `--include-values`, the same columns with `allow_real_categories: true` pass. Red on
  base (base snapshot has no marker, so validate passes the first half).
- **AT-F6** `--include-values --epsilon 1 --delta 1e-6 --dp-text state` on a real CSV with a `pd.read_csv`
  spy: exit 1, code `dp_usage_include_values`, no read. Red on base.
- **AT-F7** The snapshot carries `cell_format` per column (24l overlap, pinned so 24l C1 drops the item). Red
  on base.
- **AT-F8** `tests/sentry/test_fit_value_redaction.py`: no module under `src/decoy` calls
  `compute_distribution_snapshot` in any spelling (direct import, `as` alias, module attribute, the
  `decoy_engine.quality` lazy export); `fit.py` reads no `pii_score` and calls no `is_value_sensitive`. One
  bite fixture per spelling. Red on base (`fit.py:398`, `:422`).

Slice G (24g):

- **AT-G1** Uncertified host (`expected_dp_refusal_code_required()`), real CSV, `pd.read_csv` spy:
  `decoy fit src.csv --epsilon 1 --delta 1e-6 --dp-text state --dp-allow-omit` exits 3; the only read has
  `nrows=0`; `fit_dp_snapshot` is never called. Red on base (full read, fit called).
- **AT-G2** Same run, human stderr: the plain line and the hint; no `dp_stack_uncertified`,
  `dp_platform_uncertified`, `fingerprint`, `PlatformTriple` or digit run of 8 or more. With `--verbose` the
  engine message appears. With `--json`: `code` equals the expected engine code, `message` and `hint` present.
  Red on base (human line prints the code and fingerprint).
- **AT-G3** Request errors keep their codes before the gate: `--epsilon 0`, `--delta 2`, `--numeric-bins 0`,
  a phantom `--dp-number` column, an undeclared column without `--dp-allow-omit`. Each exits 1 with its
  existing code; the spy sees the header read and no body read. An AST check: `fit.py` imports no private
  `decoy_engine.quality.dp` name and the early call is `check_dp_fit_request`. Red on base for the spy clause.
- **AT-G4** Gate patched to pass; the spy returns a header, then a body with another column name: exit 1,
  `dp_source_changed`, JSON error payload, no traceback. Red on base (code does not exist).
- **AT-G5** A fake `read_csv` raising `ValueError("RAW-CELL-CANARY")` in exact mode, DP header read and DP body
  read: exit 1, no canary in human or JSON output. Red on base (`fit.py:413` prints `exc`).
- **AT-G6** `decoy fit --help` says DP runs only on a certified install; `decoy explain differential-privacy`
  summary and first paragraph say so; `decoy explain --json` lists the topic. Red on base.

Slice C (24c):

- **AT-C1** `decoy demo`: `scan.json` has `value_policy: flagged-redacted/v1`, a non-empty `redacted_columns`,
  and every listed column's `top_values` text is `[redacted]`. `decoy scan show scan.json <col>` on it still
  exits 0. Red on base (raw `to_dict()`, no marker).
- **AT-C2** `tests/sentry/test_profile_document_route.py`: no module under `src/decoy/cli` calls `.to_dict()`
  on a name bound from `profile_columns(...)`. Bite fixture with the old demo line. Red on base (`demo.py:148`).
- **AT-C3** Guard, green on base: a hand-built `scan-set/v1` file whose table carries a raw `detail` (the
  engine `detail=True` shape) holding a sentinel: `scan show` and `scan fields`, text and `--json`, print no
  sentinel. Pins the loader rule before row 36 adds a detail writer.
- **AT-C4** `decoy explain security` no longer says scan JSON can contain top values. Red on base.

## 10. Placement

No new source file. New test files only:

| New file | Directory | CODEMAP "Where things go" line | Sits beside |
|---|---|---|---|
| `test_items_privacy.py` | `tests/e2e/first_user/` | "First-user QA item tests, grouped by behavior" | `test_items_text.py` |
| `test_fit_value_redaction.py` | `tests/sentry/` | "Repository policy sentries and their scanners" | `test_profile_raw_value_isolation.py` |
| `test_profile_document_route.py` | `tests/sentry/` | same line | `test_scan_reader.py` |

Both sentry files register in `tests/sentry/test_sentry_manifest.py` and import the scanner from
`tests/sentry/io_policy/_calls.py`. Slice G's DP tests extend `tests/e2e/test_fit_command.py` (existing file,
where the DP classes live) and `tests/e2e/test_explain_command.py`.

## 11. Frozen contracts touched

- Exit codes (`src/decoy/cli/exit_codes.py:40-59`): no integer moves. New codes are CLI-local usage codes at
  exit 1 (`dp_usage_include_values`, `dp_source_changed`).
- `decoy fit --json`: two additive keys. The DP error payload keeps `code`, `message`, `error`; `hint` text
  changes.
- Snapshot file: `distribution-snapshot/v1` gains two optional top-level keys (engine-owned). The default
  content changes (values withheld). Pre-GA breaking change, recorded in CHANGELOG with the fix
  (`--include-values`).
- `decoy demo` `scan.json`: gains two keys; sensitive values withheld.
- `docs/cli-reference.md` is generated; regenerated in F and G.

## 12. Slices

| Slice | Row | Files | Source lines | Test lines | Risk | Review and tests |
|---|---|---|---|---|---|---|
| F | 24f | `cli/fit.py`, `tests/e2e/first_user/test_items_privacy.py`, `tests/e2e/test_fit_command.py`, `tests/sentry/test_fit_value_redaction.py`, `tests/sentry/test_sentry_manifest.py`, guide pages 01, 03, 06, `docs/cli-reference.md`, `CHANGELOG.md` | about 70 | about 170 | R2 | Codex then Dennis. AT-F1 to AT-F8 red first. Full CLI suite on the merge head (frozen-contract trigger: the snapshot default changes) |
| G | 24g | `cli/fit.py`, `cli/explain.py`, `tests/e2e/test_fit_command.py`, `tests/e2e/test_explain_command.py`, guide pages 04 and 06, `docs/cli-reference.md`, `CHANGELOG.md` | about 80 | about 150 | R1 | Codex. AT-G1 to AT-G6 red first. T1 for the touched files plus `tests/sentry`, naming `tests/sentry/test_csv_read_choke_point.py` (pin stays 2; baseline not edited) |
| C | 24c | `cli/demo.py`, `cli/explain.py`, `api.py`, `tests/e2e/first_user/test_items_privacy.py`, `tests/sentry/test_profile_document_route.py`, `tests/sentry/test_sentry_manifest.py`, `CHANGELOG.md` | about 15 (65 if Q1 is b) | about 110 | R1 | Codex. AT-C1 to AT-C4. T1 for the touched files plus `tests/sentry` and `tests/e2e/test_demo_command.py` |

Order: #169 merges first. F and C may build in parallel (different source files; `CHANGELOG.md`, the sentry
manifest and `test_items_privacy.py` are keep-both on merge). G builds after F merges: same file, and G's hint
says sensitive columns are withheld by default, which is true only after F. C and G both edit `explain.py` in
different topics; the second to land rebases. Row 24l C1 and row 24w C1 rebase on F.

Worker rules for every slice: name the class of each finding and fix the class; write the acceptance tests
first and record them red; attack your own diff by mutating each guard once (section 8 mutations) and show
the test goes red; run baselines in the same environment as the branch with `uv.lock`; never widen a
threshold or skip a test, and never weaken an existing assertion to fit the new default (a loop test that needs
real values passes `--include-values` and says why); stop and report if a catalogued class repeats.
Commit subjects follow Conventional Commits, final line `cam`.

## 13. Owner questions

- **Q1. The 24c opt-in flag.** (a) Recommended: no scan flag now. Since #166 the saved scan holds no values
  for any column, so there is nothing to opt into. The opt-in moves to row 36 (`--output-detail`), as SR
  section 3 ruled, and row 36 waits for the engine to route `detail` through `profile_document` (finding
  P1). Row 24c closes after slice C. (b) Add `decoy scan --include-values` now: it needs `--output`, adds a
  per-table `detail` built with `profile_document(profile, include_values=True)`, and warns on stderr;
  terminal, `--json` and `scan show` stay value-free. About 50 more source lines in `scanning/_multi.py`
  and `scan.py` (already 1,156 lines).
- **Q2. The H6 and H7 remainder of 24f.** (a) Recommended: split it. Row 24f closes when slice F merges, and a
  new engine row (QA-FIT-REDACT-2) covers count-of-one labels, exact `min`/`max` of unflagged numbers, and short
  free text. It reaches the CLI by repin alone, because `fit` then calls the engine document function. (b) Keep
  24f open until that engine work ships.
- **Q3. The fit hint and `--epsilon` while DP is gated.** Row 24f says the message points at `--epsilon`;
  row 24g says a default install cannot run it. (a) Recommended: one hint line that names `--include-values`
  first and says a DP release needs a certified install. (b) Point at `--epsilon` only.

## 14. Pre-mortem

- The engine flags fewer columns on a small file than the test expects. AT-F1 asserts the precondition, so the
  test fails loudly instead of passing on a clean file. Not run while planning (see "Not verified").
- `profile_row_cap=10_000` misses a column whose sensitive values start after row 10,000. Same rule and same
  miss as `decoy scan`; FR accepted it. A realistic SSN or email column fires on its first rows.
- A loop test in `tests/e2e/test_fit_command.py` breaks because its column becomes sensitive. The builder adds
  `--include-values` to that test with a comment, and AT-F5 covers the default path. Never relax the value
  assertion.
- G lands before F and the hint lies. The order rule above blocks it.
- 24l C1 or 24w C1 builds on the old call site. Both rows' briefs name slice F as the base.

## 15. Findings while planning

- **P1.** Engine `scan_set_to_dict(detail=True)` embeds raw `profile.to_dict()` at `v0.21.0`
  (`profiling/scan_set.py:524-526`). SR planned to route it through `profile_document`; that did not land.
  No CLI path calls it now. Row 36 must not ship a detail writer until the engine fixes this. Proposed: an
  engine item under row 36.
- **P2.** `fit.py:413` prints `str(exc)` from pandas on a read error. Slice G fixes it (AT-G5).
- **P3.** Roadmap row 24c text says "Next: the CLI half (engine repin, `scan show`, the opt-in flag)". After
  #166 and #169 only slice C remains. The docs-current step updates the row when C merges.

## 16. V2-LOG

- A display-time redactor for loaded snapshot files (FR F2). No CLI command prints a snapshot in V1.
- `decoy.scan()` returning a redacted document option for library callers.
- DP fit cost on every CLI call (DI models QA H8): persist the budget allocation, or document the cost.
- Certified DP for more platforms and interpreters (DPS work).
- A per-column `--include-values COL` instead of all-or-nothing.

## Not verified

- No acceptance test was run. No venv with engine 0.21.0 was at hand; the red-on-base claims come from reading
  `origin/main` and the engine tag.
- That the 5-row QA fixture flags `ssn`, `full_name` and `patient_id` under 0.21.0. AT-F1's precondition
  checks it at build time.
- The exact `fit.py` line ranges after #169 merges (#169 does not touch `fit.py`, `demo.py` or `explain.py`).
