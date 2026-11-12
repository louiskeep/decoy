# V2 sprints: plugin SDK, semi-structured data, healthcare, privacy, synthesis, reach

Status: proposal (sprint outline for V2; nothing here is scheduled)

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.
Feature detail: [v2-v3-expansion-candidates.md](v2-v3-expansion-candidates.md). Effort, dependencies
and product shape: [v2-v3-complexity-and-ecosystem.md](v2-v3-complexity-and-ecosystem.md). V1+
sprints: [v1plus-sprints.md](v1plus-sprints.md).

This document orders the V2 features into sprints and gives each slice the inputs FRAME and PLAN
need. It does not replace the plan: each slice still needs its own plan on disk, the gates its risk
level requires, and the research the development loop asks for
(`/home/cam/dev-rules/development-loop.md`).

## Scope

- **V2 core (sprints V2-0 to V2-4, about 40 slices, 9 to 10 engineer-months):** plugin SDK
  (X-25), JSON path masking (X-02), per-entity dates and DICOM headers (X-13 part, X-21), region
  disguises (X-08), anonymity enforcement (X-12, the delivery of F37), and Gaussian copula
  synthesis (X-14, the heart of F48).
- **V2 extended (sprints V2-5 to V2-9, about 60 to 70 slices):** schema-first and edge-case data
  (X-16, X-17 with F46), better free-text detection and metadata scrubbing (X-11, X-19 with F38
  and DETECT-PROFILES), XML, Excel and lakehouse tables (X-04, X-03, X-05), more databases
  (X-06), multi-table synthesis (X-15). Run in customer-pull order after the core.
- **Starts after:** CLI V1 release (row 94). Several sprints also wait on Phase 2 and 3 roadmap
  rows; each sprint lists them.
- **Estimates** assume one slice per engineer-week; recalibrate with the measured rate.

## Defaults for every slice

These apply unless a slice says otherwise, so the slices below do not repeat them.

- **Risk: R2.** New privacy logic, readers of untrusted files, new config schema and reason
  codes are all R2: reviewed plan on disk, adversarial review, exact-artifact gate. Slices marked
  R3 have an irreversible or external-cost side effect and need human authorization at that
  step.
- **Rules consulted (starting set):** `00-universal.md`, `risk-and-exceptions.md`,
  `development-loop.md`, `feature-dev.md`, `reuse-first.md`, `architecture.md`, `testing.md`,
  `security.md`, `api-and-compatibility.md`, `cross-cutting-concerns.md`, `performance.md`,
  `documentation.md`, and the recurring defect catalog. Add `config-secrets-and-supply-chain.md`
  for any new dependency or credential, `data-and-migrations.md` for any artifact schema change
  (snapshots, evidence), and `observability-and-resilience.md` for connectors. Read them during
  planning.
- **Established solutions first.** Every slice below names the methods and tools to search. The
  plan's "Established solutions" section records the search actually run, not only this list.
- **Design notes** are required for every slice that adds a module, a strategy, a route or a
  plugin kind. House style per the development loop.
- **Placement.** Engine plans check the engine CODEMAP directory map and the 600-line module
  target (`tests/sentry/test_module_size.py`); CLI plans check the CLI CODEMAP "Where things go"
  table. New sub-packages are stated in the plan as a map change.
- **Determinism:** a new mask or generator is a pure function of input, config and key (or seed),
  tested twice in-process and across processes, and across every route it is admitted to.
- **Route admission:** each new strategy states which routes admit it and refuses the rest at
  plan time with a reason code (`E:docs/execution-backends.md`).
- **Honest claims:** each new privacy or detection feature adds its limits to
  `E:docs/what-we-cannot-prove.md` in the same slice.
- **Registries:** capability matrix regenerated, `strategies.md` updated, reason codes added in
  registry order (REG-RENUMBER), compatibility corpus extended for any new artifact.
- **Close-out:** shipped log, roadmap, graph refresh and the plain-language Slack note.

## Build status (V2 work built ahead of time; owner instruction 2026-11-07: do not merge)

Built through the standard dev loop (plan, independent plan review, build, independent code
review, remediation) in parallel with CLI V1. Engine plans live in `E:docs/plans/2026-11-07-v2-*.md`;
each records every review finding and its fix. None of these slices changes CLI V1 behavior
except by adding provider names (5.4), and none is merged. Each still needs a T3 full-suite run on a merge head, and
the one pre-merge cross-model review below, before any merge.

**Owner decision 2026-11-12 (cross-model gate deferred).** The per-slice Codex gate is replaced by one
large Codex review across every built V1+ and V2 slice before any merge. Until then the Dennis-reviewed,
T1-green slices count as a working base: new slices may stack on them. The gate is deferred, not
passed; no slice records it as green. T3 on each merge head and the owner exceptions already listed
still apply, and the 2026-11-07 do-not-merge instruction stands.

| Slice | Plan branch | Build branch (head) | Review state | Open |
|---|---|---|---|---|
| V2-3.2 anonymity metrics (k, l, t; F37 measurement half) | `plan/v2-3.2-anonymity-metrics` | `feat/v2-3.2-anonymity-metrics` (`0d8fdf0b`) | code review PASS (round 4) | follow-ups: profiler reuse, ARX cross-check |
| V2-4.2 + 4.3 Gaussian copula fit and sample (F48 core) | `plan/v2-4.2-4.3-gaussian-copula` | `feat/v2-4.2-4.3-gaussian-copula` (`f6773297`) | code review round 3: all findings resolved | **owner exception for the secret-material census (2 `seed` keys)**; the sentry gate stays red until decided; differencing attacks need the DP follow-up |
| V2-5.4 edge-case providers (F46) | `plan/v2-5.4-edge-case-providers` | `feat/v2-5.4-edge-case-providers` (`f6a31a52`) | code review PASS WITH CONCERNS (round 2; advisories recorded) | conflicts with V1P-2.3 on registry count pins at merge (combined 49) |
| V2-3.1 generalization hierarchies (library: interval, band, prefix, date, category; `Lattice`) | `plan/v2-3.1-generalization-hierarchies` | `feat/v2-3.1-generalization-hierarchies` (`a4923eb6`) | plan review FAIL, FAIL (fixes folded into build); code review PASS WITH CONCERNS, then PASS. T1 gates all green on `a4923eb6`; no ratchet growth | merges second with V2-3.2 removes the copied `type_family` table; merges second with V2-3.4 folds `anonymize/__init__.py` and a duplicate CODEMAP row; config wiring is a later slice |
| V2-3.4 microaggregation (MDAV, library) | `plan/v2-3.4-microaggregation` | `feat/v2-3.4-microaggregation` (`d17dbaff`) | plan review PASS WITH CONCERNS; code review PASS WITH CONCERNS, then PASS. T1 gates all green; no ratchet growth | sdcMicro never run (no R in the build environment); cross-test with V2-3.2's `measure_k_anonymity` once that is on main; F-MDAV for larger tables |
| V2-4.4 copula quality report (pairwise fidelity, DCR, attacks) | `plan/v2-4.4-copula-quality-report` | `feat/v2-4.4-copula-quality-report` (`7a79cc3d`), stacked on the copula branch | plan review FAIL then PASS WITH CONCERNS; code review FAIL (test gaps) then PASS WITH CONCERNS. T1: all green except the inherited copula census keys (sentry tests 4215 passed when run directly) | merges only after V2-4.2/4.3; `synthetic` must be drawn from the model by the wiring slice; moving `synth-report/v1` onto the new DCR core is CLI row 69a (SYNTH-DCR) |
| V2-2.1 per-entity date offset (`date_shift` `entity_key`) | `plan/v2-2.1-entity-date-offset` | `feat/v2-2.1-entity-date-offset` (`8508a7f6`) | plan review PASS WITH CONCERNS; code review PASS WITH CONCERNS, re-review FAIL (multi-table fallback count) then PASS. T1 gates all green; no ratchet growth; registry consistent | owner 2026-11-08: the V1 `group_by` leak is CLI row 24zh, `group_by` kept; the near-miss and explicit-null `entity_key` refusals accepted as a narrow exception to dark; text keys drop trailing spaces only |
| V2-3.3 enforcement search and suppression (slice 1: library) | `plan/v2-3.3-enforcement-search` (base `bc711b6c`: V2-3.1 build with V2-3.2 merged in) | `feat/v2-3.3-enforcement-search` (`21aed114`) | plan review PASS WITH CONCERNS (folded, rev 2); code review PASS WITH CONCERNS; remediation verified PASS. T1 gates all green (sentry 4369, selected tests 2027); no ratchet growth; registry consistent against its base | stacked on V2-3.1 and V2-3.2, merges after both; lattice ceiling 5,000 nodes (worst case measured 269 s at 9,072 nodes, 200k rows); Flash-style traversal is the follow-up; slice 2 (config and full-frame planner wiring) not started; one advisory test tidy-up open |
| V2-3.5 risk and utility report (slice 1: library) | `plan/v2-3.5-risk-utility-report` (on V2-3.3 `21aed114`) | `feat/v2-3.5-risk-utility-report` (building) | plan review PASS WITH CONCERNS (folded into the build) | stacks on V2-3.3; journalist and marketer risk only with a caller-supplied population; owner question for slice 2: a config default for the risk threshold |

## Sprint order and dependencies

| Sprint | Theme | Slices | Core | Depends on (outside this doc) |
|---|---|---|---|---|
| V2-0 | Foundations: plugin SDK, path selector, evaluation data | 6 to 7 | yes | none |
| V2-1 | JSON and JSONL | 7 to 8 | yes | F07 (shares the path selector), CLI-FMT |
| V2-2 | Healthcare and regional: entity dates, DICOM, disguises | 9 to 11 | yes | F16 (disguises applied in the engine), F47 |
| V2-3 | Privacy: anonymity enforcement (F37) | 8 | yes | POSTSCAN-STREAM, F35 quality contracts |
| V2-4 | Synthesis: Gaussian copula (F48) | 8 | yes | DPS plan (`E:docs/backlog/dps-dp-synthetic-implementation.md`) |
| V2-5 | Test data: schema-first and edge cases | 8 | no | F46 |
| V2-6 | Free text and metadata | 9 to 10 | no | DETECT-PROFILES, F08, F38, V2-0 SDK |
| V2-7 | More files: XML, Excel, Delta and Iceberg | 10 to 11 | no | F22, CLI-CLOUD |
| V2-8 | More databases | 16 to 24 | no | F01 (Postgres target), row 64b |
| V2-9 | Multi-table synthesis | 12 | no | V2-4 |

Inside this doc: V2-1 needs V2-0.3; V2-2's DICOM slices need V2-2.1; V2-6's model slices need
V2-0.1 and V2-0.2; V2-7's XML slices reuse V2-0.3; V2-9 needs V2-4.

---

## Sprint V2-0: Foundations (core)

**Goal.** The interfaces and data the rest of V2 builds on: a plugin SDK so heavy dependencies
stay out of the core install, one path selector for nested data, and the evaluation data and CI
lanes later sprints need.

### V2-0.1 Plugin interface (X-25, F40)

- **Repo:** engine. **Size:** 2 slices.
- **FRAME**
  - Problem: optional heavy capabilities (models, connectors) would bloat the core and blur its
    guarantees.
  - Done when: a versioned plugin interface for four kinds (strategy, provider, detector,
    reader or writer), each declaring capabilities (deterministic or not, chunk-safe or not,
    dtypes, routes); the plan compiler admits or refuses a plugin through the same checks as a
    built-in; a sample plugin lives in a test package.
  - Non-goals: a plugin marketplace; sandboxing plugin code (plugins are trusted code the user
    installs, stated plainly in the docs); plugin config UIs.
  - Reuse check: `E:src/decoy_engine/sdk.py` (public connector SDK), `providers_v2` registry,
    `execution/_operator_registry.py`, the strategy handler registry.
- **PLAN**
  - Established solutions: Python entry points (`importlib.metadata.entry_points`); pluggy
    (pytest, Datasette, the `llm` CLI); Airflow providers and LangChain partner packages for
    versioning a core against many plugins.
  - Design notes: capability declarations are data the planner reads, so admission stays in one
    place. One registry per kind, not one per plugin.
  - Choke point: plugin registration goes only through the registry the planner reads. Guard: a
    test that a plugin registering outside it is refused. Mutation: let `compile_plan` skip
    capability checks for plugins; the guard goes red.
  - Acceptance: sample plugin of each kind admitted and run; a plugin claiming chunk-safety but
    marked non-deterministic refused on chunked routes; an incompatible interface version refused
    with a reason code.
  - Compatibility: the interface is frozen at GA; record that in
    `E:docs/compatibility-contract.md`.

### V2-0.2 CLI plugin discovery and the light-core lane

- **Repo:** CLI and engine CI. **Size:** 1 slice. **Depends on:** V2-0.1.
- **FRAME**
  - Done when: installed plugins appear in `decoy --version` output and the capability listing;
    a CI lane installs the engine without extras and proves the core import graph has no heavy
    dependencies.
  - Non-goals: a `decoy install` command.
- **PLAN**
  - Established solutions: `llm plugins`, `pip list` style reporting.
  - Choke point: the engine import-surface sentry (`tests/sentry/test_engine_import_surface.py`
    in the CLI) extended to plugins. Mutation: import a heavy module at engine import time; the
    light-core lane goes red.

### V2-0.3 Path selector for nested data

- **Repo:** engine. **Size:** 1 to 2 slices. **Depends on:** none. **Shared with:** F07.
- **FRAME**
  - Problem: JSON, JSONB and XML masking all need to address values inside a document.
  - Done when: one selector type with a closed grammar (child, wildcard, array index and slice;
    no filter expressions), statically checked at plan time, with a compiled matcher usable on
    Arrow struct and list columns and on parsed documents.
  - Non-goals: XPath (the XML adapter maps its subset onto this type in V2-7); write access by
    selector outside masking.
  - Reuse check: `E:src/decoy_engine/expressions/` (Lark grammars, closed vocabulary), F07 plan
    when it exists.
- **PLAN**
  - Established solutions: RFC 9535 (JSONPath); jq path expressions; Arrow nested-type compute.
  - Design notes: a frozen parsed selector object, one parser, one place for the grammar
    (beside the existing `.lark` files).
  - Acceptance: grammar tests, refusal of unsupported syntax with a reason code, matcher tests
    on nested Arrow arrays and on documents.

### V2-0.4 Evaluation data and CI lanes

- **Repo:** engine (data and CI), owner tasks. **Size:** 1 slice plus paperwork. **Risk:** R3 for
  any paid account or data use agreement (external cost and legal commitment).
- **FRAME**
  - Problem: V2-2, V2-3 and V2-6 need labelled data we are allowed to use, and V2-7 and V2-8 need
    container and cloud test lanes.
  - Done when: a register of evaluation datasets with licence, allowed use and storage rules
    (n2c2 2014 de-identification corpus under its data use agreement; MIDI-B DICOM benchmark;
    public synthetic sets for the rest); CI lanes defined for MySQL and SQL Server containers;
    Snowflake and BigQuery test accounts requested with spend caps.
  - Non-goals: storing restricted datasets in any repo.
- **PLAN**
  - Established solutions: dataset licence terms from each publisher; the CI lane files CI-E2
    (row 3) introduces (`ci/required-jobs.toml`, `ci/unlaned.toml`).
  - Acceptance: the register exists and each dataset entry names its approver.

---

## Sprint V2-1: JSON and JSONL (X-02, core)

**Goal.** Mask JSON documents and JSON Lines files by path, and JSON held in a table column.

### V2-1.1 JSONL source and target, flatten mode

- **Size:** 2 slices. **Depends on:** V2-0.3.
- **FRAME**
  - Done when: `format: jsonl` reads records with a stable schema into Arrow (struct and list
    columns), applies existing strategies at selected paths, and writes JSONL back with the same
    key order; bounded memory on the chunked route.
  - Non-goals: irregular documents (V2-1.2); JSON arrays at file top level larger than memory.
  - Reuse check: Polars and pyarrow JSON readers; `config/_sources.py`; chunked input machinery.
- **PLAN**
  - Established solutions: JSON Lines specification; NDJSON; pyarrow `read_json` schema
    inference and explicit schemas.
  - Choke point: the format reader dispatch and the format parity guard (every format has a
    reader, writer and profile path).
  - Acceptance: round-trip tests (byte-equal for passthrough where JSON allows: key order,
    number formatting rules stated), deterministic masking at nested paths, FK join on a nested
    key against a table column.

### V2-1.2 Walk mode for irregular documents and whole-file JSON

- **Size:** 2 slices. **Depends on:** V2-1.1.
- **FRAME**
  - Done when: documents with varying shape are masked by walking each record; missing paths
    follow a stated policy (skip or refuse); top-level JSON arrays and objects are supported with
    a size limit.
  - Non-goals: streaming a single multi-GB JSON document (record a known limit).
- **PLAN**
  - Established solutions: `ijson` style iterative parsing for large arrays; Presidio-structured's
    JSON handling as a reference for key-based detection.
  - Acceptance: shape-varying fixtures; size-limit refusal; malicious inputs (deep nesting, huge
    numbers, duplicate keys) refused or handled per a stated rule.

### V2-1.3 JSON inside a column (JSONB and string JSON)

- **Size:** 1 slice. **Depends on:** V2-1.2; coordinate with F07.
- **FRAME**
  - Done when: a column strategy `json_paths` applies per-path strategies to a JSON value in a
    cell; invalid JSON follows the row-error and quarantine rules.
- **PLAN**
  - Reuse: row errors (`execution/_row_errors.py`), quarantine.
  - Acceptance: JSONB round-trip through the Postgres source (row 64b) once it exists.

### V2-1.4 Scan: path discovery

- **Size:** 1 slice. **Depends on:** V2-1.1.
- **FRAME**
  - Done when: `decoy scan` samples JSON paths, reports presence (always, sometimes, array) and
    runs detectors per path; the starter config emits path rules.
- **PLAN**
  - Reuse: `profile/` readers, `scan-set/v1` (SCAN-MULTI); raw-value isolation sentries.

### V2-1.5 CLI wiring

- **Repo:** CLI. **Size:** 1 slice. **Depends on:** engine release of V2-1.1 to V2-1.4.
- **PLAN:** readers and writers in `C:src/decoy/cli/io/`; evidence records format and selectors.

---

## Sprint V2-2: Healthcare and regional compliance (core)

**Goal.** Keep time relationships per patient or customer, de-identify DICOM headers to the DICOM
standard, and ship region disguises.

### V2-2.1 Per-entity date offset (X-13, part)

- **Size:** 1 to 2 slices. **Depends on:** none.
- **FRAME**
  - Problem: independent per-row date shifts break intervals and order for one entity.
  - Done when: `date_shift` takes an `entity_key` column; every date for one entity moves by the
    same keyed offset, across tables that share the key; intervals and order are preserved.
  - Non-goals: preserving day of week (option, later); sub-day offsets.
  - Reuse check: `transforms/date_shift.py`, `windowed_date.py`, `determinism/_hkdf.py`.
- **PLAN**
  - Established solutions: date shifting in clinical de-identification (i2b2 and OMOP practice;
    HIPAA Expert Determination guidance on date shifting); HKDF-derived per-entity offsets.
  - Acceptance: interval preservation property test; cross-table consistency; chunked route
    parity.

### V2-2.2 DICOM tag profile engine (X-21)

- **Size:** 2 slices. **Depends on:** V2-2.1.
- **FRAME**
  - Problem: DICOM headers carry identifiers in hundreds of tags with action codes defined by
    the standard.
  - Done when: the PS3.15 Annex E Basic Application Level Confidentiality Profile table is
    loaded as data (tag, action code D, Z, X, K, C, U) with the standard edition recorded, and an
    engine applies it with Decoy strategies (tokenize or hash IDs, entity date offsets, redact
    names).
  - Non-goals: pixel data (Decoy Optic, V3); DICOM networking (C-STORE).
  - Reuse check: strategy handlers, vault, `reference_tables` loader for the profile table.
- **PLAN**
  - Established solutions: the PS3.15 Annex E table itself (load from the published standard,
    not hand-typed); pydicom (MIT) and pydicom `deid`; RSNA CTP and its Python anonymizer;
    Aryanto et al. 2015 tool comparison; Clunie on default choices.
  - Design notes: the profile is data, the engine is generic; options are profile overlays.
  - Choke point: one profile applier every DICOM path goes through. Guard: a test that every tag
    in the profile has an action applied. Mutation: drop one action code mapping; guard goes red.
  - Acceptance: tag-by-tag fixtures per action code; the profile edition is printed in evidence.

### V2-2.3 Profile options, UIDs and private tags

- **Size:** 2 slices. **Depends on:** V2-2.2.
- **FRAME**
  - Done when: the standard's options (Retain Longitudinal Temporal Information with Modified
    Dates, Retain Patient Characteristics, Retain Device Identity, Clean Descriptors and others)
    are selectable; UIDs are replaced deterministically under a Decoy root so study, series and
    instance links survive across files; private tags are removed unless allow-listed; sequences
    are walked.
- **PLAN**
  - Established solutions: PS3.15 Annex E options table; UID generation per PS3.5 (UUID-derived
    `2.25.` UIDs); CTP's private tag handling.
  - Acceptance: cross-file UID consistency; sequence nesting; burned-in annotation flag
    detected and reported (not cleaned) per the non-goal.

### V2-2.4 DICOM files in the pipeline and CLI

- **Repo:** engine, then CLI. **Size:** 1 to 2 slices. **Depends on:** V2-2.3.
- **FRAME**
  - Done when: a DICOM source reads a directory tree of files, writes de-identified files to a
    target tree, links patient keys to tabular data through the same vault, and the CLI exposes
    it (`decoy run` with a `dicom` source, or a `decoy dicom` command: decide in PLAN).
- **PLAN**
  - Security: DICOM files are untrusted input: bounded reads, refusal of malformed files with a
    reason code, fuzz tests through pydicom.
  - Acceptance: an end-to-end run where a claims table and DICOM files for the same patients come
    out with matching tokens.

### V2-2.5 Validation against a public benchmark

- **Size:** 1 slice. **Depends on:** V2-2.4, V2-0.4.
- **FRAME**
  - Done when: the DICOM pipeline runs on the MIDI-B benchmark (or the dataset V2-0.4 approved)
    and the results are published in `E:docs/` with what is and is not covered.
- **PLAN**
  - Acceptance: benchmark scorer output stored as evidence; any miss becomes a fix or a stated
    known limit.

### V2-2.6 Region disguises (X-08)

- **Size:** 1 to 2 slices. **Depends on:** V1P-2 detectors; F16 (disguises applied in the
  engine).
- **FRAME**
  - Done when: disguises for UK GDPR, PIPEDA, LGPD, APPI and DPDP, each citing the statute
    sections it implements, using the V1+ international detectors and generators.
  - Non-goals: legal advice; the disguise states what it masks, not that it makes data compliant.
- **PLAN**
  - Established solutions: the statutes and regulator guidance (ICO anonymisation guidance;
    Office of the Privacy Commissioner of Canada; ANPD; PPC Japan); existing disguise YAMLs as
    the in-repo pattern.
  - Acceptance: disguise schema tests; each rule names a detector that exists.

### V2-2.7 Series noise and seasonality options (X-13, rest; optional)

- **Size:** 1 to 2 slices. **Depends on:** V2-2.1.
- **PLAN:** autocorrelation-preserving noise (noise on differences); day-of-week preservation
  option. Acceptance: trend and autocorrelation within stated tolerance.

---

## Sprint V2-3: Formal anonymity enforcement (X-12, F37, core)

**Goal.** Users state a target (k, l, t) over quasi-identifiers; Decoy generalizes, aggregates or
suppresses until it holds and reports measured risk and information loss.

### V2-3.1 Generalization hierarchies

- **Size:** 1 slice.
- **FRAME**
  - Done when: config declares a hierarchy per quasi-identifier (age bands, ZIP prefix levels,
    date to month, quarter, year, categorical trees), built on `bucketize`, `geo_generalize` and
    `truncate`.
  - Reuse check: those strategies; the k-anonymity profiler in
    `E:src/decoy_engine/profiling/profiler.py`.
- **PLAN**
  - Established solutions: ARX hierarchy builders (interval, order, masking); sdcMicro global
    recoding.
  - Acceptance: each hierarchy level is monotone (coarser never splits classes).

### V2-3.2 Privacy model checks (measure)

- **Size:** 2 slices. **Depends on:** V2-3.1; POSTSCAN-STREAM; F35.
- **FRAME**
  - Done when: post-mask validators compute k-anonymity, distinct and entropy l-diversity, and
    t-closeness (equal-distance and ordered EMD), report the worst classes, and can fail a run
    under a quality contract.
  - Non-goals: differential privacy (separate DPS program).
- **PLAN**
  - Established solutions: Sweeney 2002; Machanavajjhala et al. 2007; Li et al. 2007; ARX's
    implementations as a cross-check oracle in a dev-only test.
  - Choke point: the validators framework (`E:src/decoy_engine/validators/`).
  - Acceptance: hand-computed fixtures for each model; ARX agreement on shared fixtures.

### V2-3.3 Enforcement search and suppression

- **Size:** 2 slices. **Depends on:** V2-3.2.
- **FRAME**
  - Done when: given targets and hierarchies, Decoy finds the least-loss generalization lattice
    node that meets them with a suppression budget, applies it, and states the chosen node.
  - Non-goals: local recoding (cell-level) in V2; optimal search for very wide lattices (refuse
    above a stated size).
- **PLAN**
  - Established solutions: Flash (Kohlmayer et al. 2012, ARX); Incognito (LeFevre et al. 2005);
    information-loss metrics (discernibility, non-uniform entropy, loss metric).
  - Design notes: whole-table operation; the planner admits it only on the full-frame route and
    states a memory estimate (`execution/_mem_estimate.py`).
  - Acceptance: optimality on small lattices checked by brute force; determinism of the chosen
    node.

### V2-3.4 Microaggregation for numeric quasi-identifiers

- **Size:** 1 slice. **Depends on:** V2-3.2.
- **PLAN:** MDAV (Domingo-Ferrer and Mateo-Sanz 2002); sdcMicro as reference. Acceptance: every
  group has at least k records; within-group variance reported.

### V2-3.5 Risk and utility report

- **Size:** 2 slices. **Depends on:** V2-3.3.
- **FRAME**
  - Done when: a frozen report (prosecutor, journalist and marketer risk as ARX defines them;
    information loss; suppressed rows) attached to evidence, shown by the CLI.
- **PLAN**
  - Established solutions: ARX risk models; Office for Civil Rights guidance on Expert
    Determination (what a risk report should state).
  - Data change: a new report schema version and compatibility corpus entry.

---

## Sprint V2-4: Gaussian copula synthesis (X-14, F48, core)

**Goal.** Synthetic tables that keep correlations between columns.

### V2-4.1 Snapshot schema extension

- **Size:** 1 slice. **Risk:** R2 (artifact schema change).
- **FRAME**
  - Done when: `distribution-snapshot/v1` gains (or a v2 adds) a correlation matrix in normal
    score space and per-column transform parameters, with a compatibility decision recorded.
  - Reuse check: `E:src/decoy_engine/quality/snapshot.py`, `generation/statistical/`.
- **PLAN**
  - Established solutions: SDV GaussianCopula (Patki et al. 2016; method only, SDV is under a
    Business Source License); copula theory (Nelsen, An Introduction to Copulas).

### V2-4.2 Fit and sample numeric columns

- **Size:** 2 slices. **Depends on:** V2-4.1.
- **PLAN:** rank-based normal scores, correlation estimation with a positive-definite repair
  (nearest correlation matrix, Higham 2002), seeded sampling, inverse transform through the fitted
  marginals. Acceptance: correlation fidelity within tolerance on fixtures; determinism per seed.

### V2-4.3 Categorical and mixed columns

- **Size:** 2 slices. **Depends on:** V2-4.2.
- **PLAN:** SDV's frequency-interval encoding for categoricals; nulls as their own state.
  Acceptance: category frequencies and cross-tabs within tolerance.

### V2-4.4 Quality report: pairwise fidelity and privacy checks

- **Size:** 1 slice. **Depends on:** V2-4.3.
- **PLAN:** pairwise correlation and contingency similarity (SDMetrics' metric definitions as the
  method reference); DCR and existing attack checks run on copula output.

### V2-4.5 DP on the correlation release (with DPS)

- **Size:** 2 slices. **Depends on:** V2-4.4 and the DPS program's budget accountant.
- **PLAN:** noise on the correlation matrix with a privacy budget, following published DP copula
  methods (for example Li, Xiong and Jiang 2014, DPCopula); positive-definite repair after
  noise. Acceptance: budget composition recorded in the DP ledger; no raw-data access during
  sampling (the DPS contract test).

---

## Sprint V2-5: Test data: schema-first and edge cases (X-16, X-17, F46)

### V2-5.1 Generate from SQL DDL

- **Size:** 2 slices.
- **FRAME:** done when Postgres and MySQL DDL (tables, types, not null, unique, check, enum,
  foreign keys) produce a starter generate config and data that loads back into the database.
- **PLAN:** `sqlglot` (MIT) for parsing; name hints in `E:src/decoy_engine/detection/name_hints/`
  for provider choice; Tonic Fabricate and Mockaroo as product references. Acceptance: generated
  rows load into a real database in CI with every constraint enforced.

### V2-5.2 Generate from JSON Schema and OpenAPI

- **Size:** 1 slice. **Depends on:** V2-1.
- **PLAN:** JSON Schema 2020-12; Hypothesis' `hypothesis-jsonschema` as a method reference.
  Acceptance: every generated document validates against its schema.

### V2-5.3 Generate from dbt models

- **Size:** 1 slice. **Depends on:** V2-5.1.
- **PLAN:** dbt `manifest.json` and model tests (unique, not_null, accepted_values,
  relationships) mapped to constraints.

### V2-5.4 Edge-case generator family

- **Size:** 2 slices.
- **FRAME:** done when a `mix` option inserts type-valid edge cases at a stated rate,
  deterministically.
- **PLAN:** boundary-value analysis (ISO/IEC/IEEE 29119-4); Big List of Naughty Strings (MIT);
  Unicode test data; Hypothesis strategies as a reference for shrinking-friendly values.
  Acceptance: every edge case is valid for the column's declared type and constraints.

### V2-5.5 QA scenarios (F46)

- **Size:** 2 slices. **Depends on:** V2-5.4.
- **PLAN:** named scenario bundles (for example "time zones", "international names") built from
  the edge-case family; wire into F46's plan.

---

## Sprint V2-6: Free text and metadata (X-11, X-19)

### V2-6.1 Context-scored detectors; reach TIER-2

- **Size:** 2 slices.
- **FRAME:** done when the 14 TIER-2 detectors fire on the built-in path through
  pattern plus context words plus checksum with scores and thresholds, and recall and precision
  are measured per detector.
- **PLAN:** Presidio recognizer design (pattern, context, score); the profiling eval harness.
  Acceptance: per-detector metrics on the approved corpus; thresholds recorded.

### V2-6.2 GLiNER detector plugin

- **Size:** 2 slices. **Depends on:** V2-0.1, V2-0.2.
- **FRAME:** done when an optional plugin runs a pinned GLiNER PII model through ONNX Runtime on
  CPU and feeds spans into the same overlap resolution as spaCy.
- **PLAN:** GLiNER (Zaratiana et al. 2023); `gliner_multi_pii-v1` (Apache-2.0; pin the exact
  model and record its lineage); model export and quantisation to ONNX. Determinism per pinned
  model and runtime, stated like `detection/ner.py`.

### V2-6.3 Clinical text evaluation

- **Size:** 1 slice. **Depends on:** V2-6.2, V2-0.4.
- **PLAN:** n2c2 2014 de-identification track scoring (token and entity level); publish results
  with the dataset's terms respected.

### V2-6.4 Detection profiles (DETECT-PROFILES)

- **Size:** 1 to 2 slices.
- **PLAN:** named sets of detectors, thresholds and models selected by name, as the V2 backlog
  row describes; regions from V1P-2 country tags.

### V2-6.5 File metadata scrubbing (X-19, F38)

- **Size:** 2 slices.
- **PLAN:** EXIF (Pillow), PDF document info and XMP (`pikepdf`, MPL-2.0), Office core and app
  properties (`python-docx`, `openpyxl`); per-field drop, keep or mask policy aligned with F38.
  Acceptance: re-reading output shows no listed field; files still open in their applications.

---

## Sprint V2-7: More files: XML, Excel, Delta and Iceberg (X-04, X-03, X-05)

### V2-7.1 XML with selector masking

- **Size:** 2 slices. **Depends on:** V2-0.3.
- **PLAN:** `lxml.etree.iterparse` streaming; XPath 1.0 subset mapped onto the selector;
  `defusedxml` protections (entity expansion, external entities). Acceptance: namespace and
  attribute handling; billion-laughs and external entity tests refused.

### V2-7.2 Excel read

- **Size:** 1 slice.
- **PLAN:** `fastexcel` (Calamine) through Polars; sheet and header-row selection; type inference
  rules stated.

### V2-7.3 Excel write

- **Size:** 1 to 2 slices. **Depends on:** V2-7.2.
- **PLAN:** `openpyxl`; keep number formats; formulas stripped by default (they can reference
  unmasked cells); workbook properties through V2-6.5. Acceptance: output opens and matches
  types.

### V2-7.4 Delta Lake source and target

- **Size:** 2 slices. **Depends on:** F22, CLI-CLOUD.
- **PLAN:** `deltalake` (delta-rs); read by version; write as a new table through the
  transactional commit and F22's publication contract; evidence records version.

### V2-7.5 Apache Iceberg source and target

- **Size:** 2 slices. **Depends on:** V2-7.4 pattern.
- **PLAN:** `pyiceberg`; catalogs supported stated; snapshot id in evidence.

### V2-7.6 CLI wiring for V2-7

- **Repo:** CLI. **Size:** 1 slice.

---

## Sprint V2-8: More databases (X-06)

### V2-8.1 Database adapter contract

- **Size:** 2 slices. **Depends on:** F01 (Postgres target) and row 64b (Postgres source).
- **FRAME:** done when the Postgres adapter's behaviour is written down as a contract
  (snapshot-consistent read, type-mapping report, staging, constraint, index and sequence
  restore, atomic publish, refusals) with a conformance test suite any adapter must pass.
- **PLAN:** ADBC (Arrow Database Connectivity) specification; Delphix's connector model as a
  product reference. Choke point: the conformance suite. Mutation: an adapter that skips
  constraint restore must fail it.

### V2-8.2 to V2-8.5 One database per step

| Slice | Database | Size | Bulk path to research | Notes |
|---|---|---|---|---|
| V2-8.2 | MySQL and MariaDB | 4 to 6 | `LOAD DATA`, ADBC or `mysqlclient` | container lane in CI |
| V2-8.3 | SQL Server | 4 to 6 | bulk copy (BCP, `bulk insert`), ADBC or `pyodbc` | container lane; licence of the container image |
| V2-8.4 | Snowflake | 4 to 6 | staged Parquet plus `COPY INTO`; Snowflake ADBC driver | R3 for paid account usage; spend cap |
| V2-8.5 | BigQuery | 4 to 6 | load jobs from Parquet; BigQuery Storage Read API | R3 for paid project usage; spend cap |

Order by customer pull. Each slice: type-mapping report, conformance suite green, credential
handling through the F13 secret providers (never plain config), and observability per
`observability-and-resilience.md`.

---

## Sprint V2-9: Multi-table synthesis (X-15)

### V2-9.1 Parent and child size models

- **Size:** 3 slices. **Depends on:** V2-4.
- **PLAN:** SDV HMA1 (Patki et al. 2016): child-count distribution per parent, conditioned on
  parent attributes. Acceptance: child-count distribution fidelity; every FK resolves.

### V2-9.2 Conditional child attributes

- **Size:** 3 slices. **Depends on:** V2-9.1.
- **PLAN:** child copula parameters conditioned on the parent, as HMA1 does. Acceptance:
  parent-child correlation fidelity.

### V2-9.3 Deeper schemas and bounded memory

- **Size:** 4 slices. **Depends on:** V2-9.2.
- **PLAN:** recursion depth limits, a memory estimate, and refusal above it; chunked generation
  per parent batch. Acceptance: three-level schema fixture; memory budget test.

### V2-9.4 CLI and reports

- **Size:** 2 slices.

---

## Questions to settle before V2-0 starts

1. Confirm the V2 core (V2-0 to V2-4) and the order of V2-5 to V2-9.
2. Plugin interface freeze: at V2 release or at GA?
3. DICOM: a `dicom` source in `decoy run`, or a separate `decoy dicom` command?
4. Who signs the n2c2 data use agreement and owns the evaluation data register?
5. Which databases first in V2-8, and the spend caps for Snowflake and BigQuery test accounts?
