# QA record: distribution integrity (masking + generation), first-user pass

Date: 2026-11-08. decoy-cli 0.1.0, decoy-engine 0.19.0, Python 3.12, NO_COLOR captures.
Companion to `2026-11-08-cli-qa-first-user.md` (same data, same method).
No code was changed. "DI" = distribution integrity: does the output keep the
statistical shape of the source (and only that), and can you reproduce it.

## Test data (regenerated, seed 7)

`patients` 10 rows (patient_id, full_name, ssn) and `visits` 20 rows
(patient_id FK, diagnosis). 5 columns, 3 PHI, 1 FK. Deliberately skewed:
visits per patient 8/5/2/1/1/1/1/1/0/0; diagnosis 9/5/3/2/1.
Edge copy adds a duplicate name, a duplicate SSN, 3 null diagnoses, 1 null name.

## Question bank

A. User ignorance (what a first-timer does not know)
1. What is a "distribution snapshot" and is it safe to share?
2. What does "fidelity" mean, and is a high or low score good for masking?
3. Why is `PASS` printed next to grade F?
4. What is a master key vs a mask secret, and which do I need?
5. What does `--key-label` do, and why is it a flag and not YAML?
6. What are epsilon and delta? What do I pick?
7. Does masking keep my counts and ratios, or only the format?
8. Is the same input always the same output?

B. User expectations
1. Fan-out (visits per patient) survives masking.
2. Category frequencies survive masking.
3. Nulls stay null; duplicates stay duplicates.
4. Same seed + secret = same file, every run.
5. Generated data follows the fitted shape, including skew, and its FKs resolve.
6. Real values never appear in generated data or in a shareable snapshot.
7. A low score on a faked column is expected, not an alarm.

C. Unclear workflow
1. fit -> generate -> fidelity: which file goes where, which flag is needed?
2. How do I generate two tables with an FK?
3. Which report do I run after masking vs after generating?
4. What do I do when DP fit refuses?

## Results: what held up (do not regress)

- Masking keeps fan-out exactly (8/5/2/1/1/1/1/1 in and out), diagnosis counts
  exactly, no orphans, no source ids in output, nulls stay null (3 in, 3 out).
- hash/fpe/faker are reproducible: two runs gave byte-identical patients files;
  a different mask secret changes them; a missing secret is refused before any
  data is read with a clear message.
- fpe is value-consistent (duplicate SSN -> same output; keeps dashes/length).
- Generation: same master key + same label = identical output; a different
  label = different output. Generated FK has no orphans. No real SSN or name
  appears in generated output.
- Engine refuses to emit real categories from a snapshot without an explicit
  `allow_real_categories: true`. Good guard.

## Findings

### High

H1. `shuffle` is not reproducible. Two identical runs (same seed, same secret)
give different `diagnosis` order; every other strategy is byte-identical. Breaks
the "same seed = same file" promise and evidence-manifest diffs. Needs a
decision: seed it from `global_settings.seed`, or document it as non-deterministic.

H2. `decoy fit` (default, non-DP) copies raw values into the snapshot with no
warning. `pat.snap.json` held every real name, SSN and patient id in
`top_values`. The command prints only "10 rows; columns: ... (categorical)". The
file is 0600 but the artifact is designed to be passed to generation and shared.
The engine catches it later at `validate` (error text says "REAL source values")
but a user who emails the snapshot has already leaked. Suggest: warn at fit time
for high-cardinality or detected-PII columns, and suggest `--epsilon`.

H3. DP fit is unusable on a default install. Every `--epsilon` run ends with
`dp_stack_uncertified ... fingerprint '4cd745...'`, exit 3 (reported as a run
error). There is no path for a normal user; the message talks about proof
stacks and lock fingerprints. Needs a plain-English line ("DP release needs the
certified install; use `pip install ...` / use the exact snapshot instead") and
a pointer in `explain differential-privacy` that this is gated.

H4. Generated FK does not reproduce skew. Source: 8/5/2/1/1/1/1/1 visits per
patient. Generated (reference column, `distribution: weighted`): max 5, 25 of
30 patients have visits. `fit` captures the parent-key counts in the snapshot,
but the reference column does not use them. User expectation B5 is not met and
nothing says so.

H5. `validate` traceback also hits generation: a generate-only relationship
without `namespace` crashes `decoy validate` with a Rich traceback, while
`validate compile` passes (same bug as the first report, H1). Also: `namespace`
is a masking concept and is required even when nothing is masked.

### Medium

M1. `report fidelity` verdict semantics: masked patients show "PASS grade F
overall_score 0.000". For masking, low similarity on name/ssn is the goal;
grade F and a 0.000 are alarming and the PASS next to it is confusing. The
report needs a per-column "intended" marker (it knows the strategy only with
`--config`) and plain wording ("lower is expected for masked columns").

M2. With `--config`, `patient_id` (hash) is still listed as a policy violation
("Expected 0.05, Actual 0.0") although the config declares `hash`. Help says
`--config` stops intentional loss being flagged; it does not here.

M3. `fidelity --generate` on the generated table returns "patient_id: not
comparable" and a joint `diagnosisxpatient_id` similarity of 0.000 (the id
spaces differ by design), overall 0.458 grade F, verdict PASS. The joint of a
key column against a different id space is meaningless and should be skipped.

M4. Per-patient link is lost by `shuffle` (patient-to-diagnosis pairing differs
in output). Marginals are preserved, joint is not. Correct for shuffle, but
there is no note in `explain transforms` or the run summary. Users who expect
cohort analytics to still work will be misled.

M5. `faker` is row-positional, not value-consistent: two source rows with the
same name ("Alice Moore") became two different fake names. That inflates
distinct counts (name frequency distribution flattens) and breaks joins on
names. fpe/hash do keep duplicates equal. Not documented; users cannot tell
which strategies preserve value frequency.

M6. `report integrity` says the masked `full_name`/`ssn` "matched ... but was
not configured to be masked" although they were masked. The tool is run on the
output without the config, so it cannot know. It prints 2 warnings with no
column names in the table; names appear only in `--json`. The useful number
(`source_identity_rate: 0.0`, i.e. nothing leaked from source) is not shown.

M7. Run summary has no row counts and no fidelity or integrity line for either
mode (`Elapsed`, `Route`, `Mode` only), so DI cannot be judged from the run.

M8. Validate warning "Output target directory does not exist" is noise (run
creates it) and is also what the "2 pre-run warning(s)" banner on `run` points
to. First-time users see a warning on every fresh project.

### Language and explanation audit (simple English)

- Internal jargon in user-facing help: `explain modes` mentions "FC-1",
  "storm-reframe-C", "S22-CL-V1GRAPHRUNNER" and V1 history; `report fidelity`
  help cites `report.py:97, policy.py:142` and "BF1"; `report integrity` says
  "Storm integrity" in its table title and "the platform's mask job". A user
  does not know what STORM is.
- `explain keys` is ~60 lines and mixes two mechanisms; the key point (use
  `--master-key` for generation, `--mask-secret` for masking) is buried. The
  panel subtitle truncates mid-word ("...(--─╯").
- `fit --help` examples run together as one wrapped paragraph; the DP example
  is unreadable. `report fidelity` examples have the same problem.
- No `explain` topic for `fit`, `generate`, `fidelity`, `snapshot`; `explain
  differential-privacy` exists but is not listed in `explain` and `fit --help`
  names it without saying it is gated (H3).
- `show template generate` comments are stale: "The YAML's `mode: generate`
  selects the synthesis path", "CLI.3 (2026-06-02) rewrite". `explain modes`
  says the top-level `mode:` key was removed; `decoy-engine/docs/recipes.md:151`
  still tells users to write `mode: generate` / `--mode generate`.
- `--mode` is "only a label" per `explain modes`; a flag that does nothing but
  print is a footgun. Consider removing it (pre-GA hard delete).
- Error "statistical column ...: top_values contain REAL source values" is
  correct but does not say what to do besides the key name; add the two
  choices (DP release, or accept disclosure) in plain words.
- Generated reference column syntax (`type: reference`, `reference_table`,
  `reference_column`, `distribution`) appears in no example or template; the
  only way to find it is reading engine source. The generate template has no
  FK example at all (C2 unanswered).

### Command-family check

- `fit` is top-level but belongs with `report`/`scan` thinking-wise: it is the
  first step of generation and does not appear next to `run` in the help
  ordering. Suggest a "Generate" help panel: `fit`, `run`, `report fidelity`.
- `report fidelity` and `report integrity` are post-run checks but take
  different arguments (`SOURCE OUTPUT` vs `MASKED --source`). Make the shape
  match.
- `--generate` on `report fidelity` is an easy-to-forget flag; the manifest
  already records the mode, so fidelity could read `--evidence` and infer it.

## Suggested order

1. H1 (decide shuffle determinism) and H2 (fit-time warning): both are quick
   and are the integrity promise itself.
2. H4 and M1/M3 together (fidelity semantics for generated FK and keys).
3. H3 message, H5 traceback (already queued from the first report).
4. Language pass: strip internal ticket ids; split `explain keys`.

## Not tested / limits

DP numeric and flag carriers (blocked by H3); `--parse-dates`, `--joint` at
fit time; cross-machine determinism (only one host); data larger than 30
rows, so no statistical power on similarity scores.
