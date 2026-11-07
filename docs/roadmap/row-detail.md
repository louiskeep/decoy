# CLI V1 track: row detail

Status: plan

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

**SUB-STOP (row 10).** Closes the silent ignore of `subset:` in a run (UX map Q1, run-confirmed).
The CLI gets the refusal after R-c and the repin. SUB-RUN later replaces the refusal.

**CLI-DIALECT, CLI-FMT, CONFIG-EXPLICIT (rows 19 to 22).** UX map Q20 (run-confirmed) and section
3.9. Owner (2026-11-05 night): "explicit config is important." Today `has_header` is optional with
default true (`E:config/_sources.py:95-101`). The parked CLI branch `claude/enterprise-hardening`
(archive tag `archive/claude/enterprise-hardening`, `17bb5006`) has a fixed-width writer that stays
parked; fixed-width output is V1 through CLI-FMT.

**KEY-LABEL-SEP (row 24b).** Domain-separation defect in key derivation. `derive(seed, namespace, source)` (`E:src/decoy_engine/determinism/_derive.py:261`) frames the namespace and the source with length prefixes, which stops ambiguity between them but not a data value equal to a fixed label: `hash` passes the canonical bytes of each cell as `source`, and the FF1 key derivation passes the ASCII label `ff1-key/v1` in the same position under the same namespace. Reproduction (2026-11-07, engine `dd31ea91`): one table, `note` as `hash` and `card` as `fpe` (digits), both `namespace: ns1`, `mask_secret_ref` from a file; a `note` cell `ff1-key/v1` comes out as 64 hex characters equal to the FF1 key, and `fpe_decrypt_value` with that key and the column tweak returns the source card numbers. A truncated `hash` leaks part of the key. Precondition: someone who can put that exact text into a source row of a `hash` column, and later read the masked output. FRAME must list every fixed label (`FF1_KEY_LABEL`, `code_set`'s `_KEYED_SALT`, any other) and every data-sourced `derive(` path, including the native and unified hash kernels' input types. Design reference: the V1P-3.4 Crypto-PAn label `\xffdecoy-cryptopan-key/v1` and its unreachability test (engine branch `feat/v1plus-p3.4-ip-keep-prefix`). Alternative to weigh in PLAN: separate the two uses inside `derive` (a distinct domain byte for key derivation versus per-value derivation) so no label list is needed. Either way the masked output of every `fpe` column changes, so it lands before the REL-GATE versioning freeze; V1P-3.3 (`keep_bin`) reuses the FF1 key and inherits the fix.

**CI lanes (rows 1 to 5).** Plan `P:docs/plans/2026-11-05-ci-lanes.md` (merged as platform #187,
owner approved). CI-E0 MERGED (engine #383). The platform slices CI-P1 to CI-P3 are parked with the
platform. The engine has a self-hosted gate (engine #380) on the Mac runner user `decoyci`;
decoy-test-1 is a second Linux gate runner.

**FILE-SIZE (row 7).** Port the engine census pattern to the CLI: a `C:tests/sentry/test_module_size.py`
with an 800-line ceiling for new and touched files, the four oversize files pinned at their exact
line counts (shrink-only), registered in the CLI ratchet manifest. In both repos add a package check:
modules per package directory, with today's counts pinned shrink-only and a stated limit for new
packages (the plan sets the number after measuring). Keep the engine's 600 and 700 thresholds. Close
the engine census gap its docstring names (a deliberate census edit in the same PR passes the test)
by routing allowlist growth through the X0a-h approval path once that exists. H-1 C0 may be the same
work; the plan decides.

**PHASE 0.5 cross-cutting foundations (engine and CLI parts).** Plan
`P:docs/plans/2026-11-04-cross-cutting-v1-foundations.md` (Codex GO `04b92412`). Engine and CLI
slices merged: X0a ratchet and manifest (engine #378, #379), X0a self-hosted gate (engine #380), X4d
(engine #384, #385), X7b (engine #382), CLI X0a (CLI #81, #82). Open here: X7c (row 24). X0a-h E1,
E2, C1, C2 (row 9) are deferred off the V1 path. Test trust (owner, 2026-11-05): a green suite counts only when each test was seen
red under a named mutation; the platform test-trust slices are parked; the CLI journey row is 75.
The dev-rule `cross-cutting-concerns.md` is the standing rule (ROADMAP section 4).

**STORM concept reframe (2026-10-29).** STORM is removed as a concept. Decoy is a data-manipulation
compiler pipeline with phase-bound scans: pre-scan (profile and detect), transform (mask and
generate), post-scan (verify, leak and fidelity). The STORM wire, config, route, CLI and doc surfaces
(`run_storm`, `decoy storm` verbs, `storm.scan`, `storm-post-mask/v1`) are renamed in one pre-GA
wave. Rules the wave honours: permission flags are deny-only rows, so a rename without a row
migration fails open; lenient request models silently drop old keys; the scheduler filters on the
stored mode `storm.scan`. The after-publish STORM post-mask hook retires once DELIV lands one in-run
post-scan path. Earlier engine parts MERGED (engine #329, #349).

**Phase 1 slice 0 (owner, 2026-10-30; before F31).** 11.1 vault writer seed fallback (`vault.py:349-355`
falls back to the 8-byte `job_seed`; reproduced) plus the 12.3 simpleeval floor (housekeeping): row
11. 14.1 untyped pyarrow seam: MERGED (engine #360). 12.1 residue (derived expressions bind the whole
row, `_derived.py:65-66`): row 13.

**Audit packets 11 to 20.** The substrate-hardening refactors (ValidatedMaskKey boundary,
schema-bound expression context, snapshot and identity binding, enforced ResourceLedger,
SensitiveDiagnosticBoundary, oracle sentries) ride F31, F29, F25, F35 and F36: build the mechanism
when the feature is built, not a point patch. Owner-decision findings 18.1, 18.3, 11.2 and 19.7 wait
on an owner call and bite only in multi-worker mode.

**F31 (row 65).** One typed safe-event boundary plus an adversarial secret-injection corpus,
replacing per-surface redaction; the sanitizer behind F29's `approve_ref`; the CLI's F43
`SafeFinding` is the pattern. Source `E:docs/plans/2026-10-19-obs-1b-engine-log-leak-scrub.md`. FRAME
findings: `str(exc)`-style sites route through one exception-capture policy; physical-seam
`<code>:<detail>` composites become typed. Owner 2026-11-02: CUT the alias, legend and run-UUID
stack. Owner 2026-11-02 O1 to O3: no ban on except-bound text inside `raise`, but a ratchet so the
count cannot grow; no debug opt-out, only frame locals are cleared.

**F29 (rows 62, 66).** Engine half MERGED (engine #336: versioned registry, `RetryClass`, bytes,
retry and checkpoint progress); C0 record MERGED (engine #367). FRAME findings: the CLI maps
`CommitError` and verification failures to their own exit codes and the `--json` error payload drops
raw exception text (closes 13.7 on the CLI side); if free, a `warning` event on native-kernel silent
fallback (G11). The CLI does not retry or self-orchestrate.

**F25 (row 58).** A scratch manager (job-owned 0700 dirs plus byte quotas that every spool, temp
Parquet, subset and DB spill registers with), at-rest encryption, lease-checked orphan sweep. FRAME
findings: the three temp roots register with the one scratch manager (G6); cloud reads go through a
bounded reader (G7); the isolated route caps staged-table materialization (G7); spill encryption is
shown per path or recorded as not covered.

**F22 (row 59).** Add the idempotent half: detect and report an existing committed result on
republish, an explicit overwrite policy with optional protected backup, one publication descriptor
bound into commit. FRAME finding: the descriptor carries unit identity so F23's checkpoint store can
key on it. Superseded branch `claude/wizardly-allen-8ymekg`.

**POSTSCAN-STREAM (row 60).** Today `run_post_mask` takes whole frames
(`E:verification/postmask/runner.py:38-43`), so routing forces full-frame
(`E:execution/_pipeline_routing.py:140-142`); PK uniqueness and FK link checks are full-frame only.

**CLI delivery (row 61).** UX map sections 5.1 to 5.3a: a `delivery:` YAML key owned by the engine;
every run writes into an immutable per-run delivery root; post-scan runs on the staged output; the
attempt vault is made durable; one publication record is published last. Strict delivers nothing if
any table fails; best-effort delivers the good tables and drops failed ones and their FK dependents.
All file targets of a strict pipeline sit under one root, or validate refuses the config with a
registered code. The CLI chunked path (G4: `C:src/decoy/cli/run.py:1475-1497` has no
`TransactionalSink`) writes through the same sink. Q4 (default `strict`), Q10, Q11 and Q17 apply. In
strict mode a post-scan `fail` finding (F34) or a failed contract (F35) blocks delivery.

**RESULT and SAMPLE (rows 62, 63).** UX map section 5.4: one result document per run and an
additive exit code 6 for partial delivery (Q5). SAMPLE runs the first N rows through the subset so FKs
link; Q9 and Q19 apply.

**F34 (row 67).** A canary-driven text-span scanner (bounded canary set, shared scanner,
normalized-span rules, safe match-mode, location and count report). FRAME finding: the post-mask
identity helper tells "no signal" from "comparison failed", and a failed comparison is a finding
(G8). The F34 release must precede the F32 release.

**F36 (row 68).** `pk_uniqueness` exists (`validation/post/_checks/_pk_uniqueness.py`); add a bounded
invariant language (equality, inequality, ordering, null), a join-cardinality-change metric, stable
check ids. FRAME finding: promote `pk_uniqueness` to the validators catalog and make it out-of-core
safe. Engine PR #313 `docs/cross-column-dependency-plans` (OPEN); branch `review/f36-opus`.

**F35 (row 69).** A versioned quality-contract object (metrics, subjects, limits, required statuses)
that gates publication; V1 is measurement-only (label-free fidelity). Sources
`P:docs/plans/2026-10-16-distribution-integrity-program.md`, B-9 measurement.

**F32 (rows 15, 70).** A pseudonymised, user-inspectable, no-auto-upload support bundle plus a
bounded synthetic reproducer. FRAME: allowed metadata, pseudonym scope, reproduction limits; the
bundle's safe errors are `ReasonRecord`s, never exception text. Slice re-cut accepted (owner).

**F30 (row 71).** OpenTelemetry export to a customer-chosen collector; the CLI exporter (C1a MERGED);
read, transform, validate and publish spans. SLOs reduced scope. OpenTelemetry export is opt-in
(CLI-REL statement).

**F33 (row 72).** Signature envelope (`manifest_hash` is unkeyed SHA-256 today), public-key offline
verify, KMS interface, rotation and revocation, inconclusive-detector strict gate. Owner Q16:
`post_validation_enabled` defaults to False; E1b 14-file waiver confirmed. FRAME finding: the passport
signing key joins the backup and custody list (G22).

**F13 (rows 73, 83).** Engine slices 0 to 2 MERGED (engine #339); CLI 4a/4b `--mask-secret` for
`run`, `unmask` and `report vault` MERGED (CLI #78). Remaining: plan revision for 3b and 5; slice 3a
is platform provider injection (parked). Live Vault tests UNVERIFIED.

**F26 (row 74).** Sweeper for expired uploads, outputs, snapshots, staging and checkpoints; dry-run
inventory; hold- and dependency-aware audited cleanup; a CLI local-cleanup command. The inventory
includes the F25 scratch roots (G6). LIB L4b `prune` and `clean` overlap it; the re-scope settles the
boundary.

**F43 (merged).** `decoy ci check`, `decoy-ci/v1`, SARIF 2.1.0, `SafeFinding`, staged literal scan,
pre-commit hook, Actions and GitLab templates (CLI #69). The reduced-scope remainder is in
`C:docs/ci-contracts.md`; no further dispatch.

**F06 (merged).** Declared parsing, casting, quarantine; MERGED (engine #338, registry 1.4.0).

**H-1 (rows 43 to 55).** Split oversized, mixed-concern modules into cohesive packages; consolidate
duplicated helpers. FRAME findings: the CLI fixed-width scan parse (`pd.read_fwf`, G5) and the
grade-threshold and PII-bucket copies in `report.py` and `scan.py` become engine imports. The review's
"if free" deletion of the scheduler package (G24) is not taken (owner, 2026-11-02). Open H-1 owner
questions: Q2, Q3 (E8 timing), Q5 to Q10, Q12.

**F10 (row 78).** One portable lock envelope (engine compat, seed protocol, canon, providers, pool
digests, generator logic, deps). FRAME: `runtime_identity` includes Faker and provider and pool
digests; the engine's wide dependency floors (G12) are what it must pin. Source
`P:docs/plans/2026-10-24-upgrade-determinism-gate.md`.

**F09 (row 79).** The immutable domain-version object {input type, canon, namespace, transform, key
version, output format, collision policy}, three rotation modes, impact preview, remap manifest;
reduced scope defers the advanced UI. FRAME: `key_version` on the Plan and in evidence for every keyed
strategy. B-6 existing-vault compatibility is a hard cut; the CLI refuses to overwrite an existing
vault (owner, 2026-11-02).

**F15, F16, F07 (rows 80 to 82).** F15 restores the strict-drift publication-block preflight removed
in reframe-C; `DetectorMatch` carries the detector version. F16's 5-level precedence and per-field
expansion fingerprint. F07 has depth, array-expansion and cell-size bounds with declared failure
behavior; complex nested formats and XML defer.

**F24 (row 84).** Advisory per section CAP; enforced admission is V2. The deployment contract states
that admission is measure-only in V1 and names the operator mitigation.

**F23 (row 85).** Table-level resume skips tables already staged; about 8 to 12 slices (UNVERIFIED
until FRAME). Chunk-level resume (continuation tokens, sink state, chunk digests) is post-V1. FRAME:
the engine half is NEW (`CheckpointInfo` is vocabulary only); the store keys on F22's descriptor; the
default recovery path is fault-injected (SIGKILL mid-job); the matrix states per phase "resumed" or
"failed, never requeued".

**F01, F02, F44 (rows 86 to 88).** F01: a write-mechanism decision first; `sslmode=require` by
default with `sslrootcert`; a snapshot id bound into the run; the type-mapping report separates exact,
normalized, lossy and unsupported. PostgreSQL is the one complete connected workflow for V1. F02: the
SFTP sink writes through an F22 adapter; connector errors carry type names, not SDK text; GCS and SFTP
can trail S3. F44 known SBOM follow-ups: `sbom.sh` line 96 `cd` stderr can name the caller path; the
CLI root `version` is not checked in the completeness check; lock-mode refusal prints lock package
names (owner question).
