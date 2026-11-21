# Decoy Roadmap: CLI V1 first, then Platform V1

Status: plan

This is the one Decoy roadmap for all four repos (engine, CLI, platform, web). It is an index: it
says what the goal is, what is in each release and where each item lives. Status detail lives in the
group files. History lives in the shipped log ([`RECENTLY-SHIPPED.md`](RECENTLY-SHIPPED.md)) and in
git. The roadmap as it stood before the 2026-11-18 split, with its history notes, is kept whole in
[archive/2026-11-18-roadmap-before-split.md](archive/2026-11-18-roadmap-before-split.md).

Path shorthand: `E:` is the engine repo (`decoy-data/decoy-engine`), `C:` is this repo
(`decoy-data/decoy`), `P:` is the platform repo (`decoy-data/decoy-platform`). "Vault" is
`~/obsidian-vault/10_Projects/decoy/`.

---

## 1. Goal

**CLI V1** is the engine plus the CLI: a finished, downloadable Decoy application from the website,
fit for production pipelines on Linux, macOS and Windows. Windows is in 1.0 (owner 2026-11-18): the CLI
must download, install and run the demo on a Windows machine; WIN-FEAS reports any blocker to the owner. Owner:
"CLI V1 is going to be a finished, working Decoy application available for download on the website
and use in production pipelines." On Windows: "would be ideal if possible."

**Platform V1** comes after. It is the paid self-hosted product and is PARKED until CLI V1 ships
([roadmap/platform-parked.md](roadmap/platform-parked.md)). Owner: "Platform is paid, so we don't need to release that at the same time as Decoy
CLI."

**1.0 scope is cut** (2026-11-18, [record](records/2026-11-18-1.0-scope-triage.md)). 1.0 is the rows in the 1.0 tables of the group files below and nothing else. This replaces the 2026-11-05 rule that every track row ships in 1.0. The additive rows move to 1.x.

In the release gates ([roadmap/release-gates.md](roadmap/release-gates.md)), R1 is CLI V1 and R2 is Platform V1.

## 2. The one pipeline

The CLI and the platform build the same pipeline configuration and run the same engine. In order, a
pipeline holds:

1. **Source**: files, databases, cloud paths.
2. **Subset** (optional), keeping related rows consistent.
3. **Pre-scan**: opt-in, available by default; profiles and detects sensitive data, with ML or
   without.
4. **Mask and generate**, per table.
5. **Post-scan**: the output is safe and faithful (leaks, fidelity). Integrity checks are standard.
6. **Delivery**: stage, then write the finished dataset to its targets.

The tokenization vault and CI use are part of the baseline on both products. Workflows are retired:
the pipeline is the only job unit. The CLI is single-user and does not self-orchestrate; it returns
exit codes and a result document. The platform adds teams, orchestration and records.

Full text: [`P:docs/product/v1-pipeline-baseline.md`](https://github.com/decoy-data/decoy-platform/blob/main/docs/product/v1-pipeline-baseline.md).
It stays in the platform repo next to the journeys, the capabilities page and the V1 UX map that
link to it. The V1 UX map is `P:docs/product/v1-ux-map.md` (branch `docs/v1-ux-map`, in its own
review); its section 8 is the source of the UX map rows below.

**Engine contracts stay platform-ready.** The platform will later compile the same YAML. A contract
(a config key such as `delivery:`, a reason code, the result document, the publication record) is
built once in the engine and the CLI consumes it. No CLI-only fork of an engine contract.

## 3. How to use this roadmap

The reasons and the day-to-day steps are in the handoff
[handoffs/2026-11-18-roadmap-strategy.md](handoffs/2026-11-18-roadmap-strategy.md).

1. **New work enters through the inbox.** A finding, review note, QA result or idea is one line in
   [roadmap/inbox.md](roadmap/inbox.md). It is not a row until triage places it.
2. **A row blocks 1.0 only on one of three tests.** Freeze: it changes a public name, default, output,
   exit code, reason or stored format, or adds a refusal of something that works today. Safety: a
   leak, a wrong result reported as success, or a known advisory. Broken today: a shipped command
   fails or misleads on the documented path. Anything else is Later or Maintenance.
3. **Every row has one home.** Its group file, in one of three tables: 1.0, Later, Maintenance. This
   index lists row names only.
4. **State is short.** One state word (NOT STARTED, PLANNED, BUILDING, IN REVIEW, PARTLY MERGED), then
   what is left. Pull request numbers, hashes and dates of merged slices go to the shipped log, not
   the row. Rows carried from the old track are trimmed to this shape when they are next touched.
5. **A finished row leaves.** When its last slice merges, add it to the shipped log and delete the
   row in the same change.
6. **Three release buckets** (owner, 2026-11-18). v1 is the 1.0 tables. Anything that does not break
   the contract is v1+: a 1.x release, planned as themed minors (one headline group from Later plus
   what fits a fixed time budget). Anything that breaks the contract is v2 and waits in
   [roadmap/2.0-holding.md](roadmap/2.0-holding.md). The contract and the tests that decide are in
   [roadmap/post-1.0-plan.md](roadmap/post-1.0-plan.md).
7. **Process rules are not here.** The dev loop, the choke-point rules and the sequencing rules are in
   [roadmap/working-rules.md](roadmap/working-rules.md).

## 4. Scope by feature group

55 rows block 1.0, 33 are Later and 12 are Maintenance (2026-11-21). Each cell lists the row
number and short name; the row itself is in the group file. Each group file also lists its v1+
candidates that have no plan yet (86 in all), and the health file lists 31 maintenance candidates. The named 1.x speed slots (1.0.x to 1.3) are listed in [roadmap/post-1.0-plan.md](roadmap/post-1.0-plan.md).

| Group | 1.0 (open) | Later (1.x) | Maintenance |
|---|---|---|---|
| [Scan and detection](roadmap/groups/scan.md) | 16 NAME-REMOVAL E1, 27 SCAN-MULTI S1c-cli, 29 SCAN-MULTI S3-cli, 32c SCAN-ML-MD, 56 NAME-REMOVAL, CLI half, PRE-SCAN-RUN | 30 SCAN-LIB, 31 DIST-INTEGRITY, 32 DRIFT, 80 F15 | none |
| [Config, validation and the init wizard](roadmap/groups/config.md) | 24e CLI-QA1, DECOY-LANG | none | none |
| [Masking, policy, vault and secrets](roadmap/groups/mask.md) | 79 F09, FAKER-MIGRATE, DATE-SHIFT-FORMAT, FAKER-NATIVE-WIDEN, LARGE-STRING-CAST and UF-DOMAIN, COLUMN-SHAPE-RULE | 24zt F16-PROHIBIT-DOC, 81 F16, 83 F13 external adapters, TEXT-REDACT-RUST-SPLICE (1.0.x), FPE-CHECKSUM-NATIVE (1.0.x), RUST-DATE-TEXT (1.2) | none |
| [Fit and generate](roadmap/groups/generate.md) | 24f QA-FIT-REDACT, 24n GEN-REL, 24p GEN-PROVIDERS, 24q GEN-TYPES, 24s GEN-CATALOG, GEN-WINDOWED-BATCH | 24r GEN-INHERIT, GEN-VECTOR-STREAMS (1.0.x) | none |
| [Run, publication and results](roadmap/groups/run.md) | 24zs F26-RESERVED-NAME, OUTPUT-METADATA-LEAK, 58 F25, 59 F22, 61 CLI delivery, 63 SAMPLE CLI half, 63a RUN-STREAM, 74 F26 CLI local cleanup and engine part, FREEZE-OUTPUT, NONFK-OOM, NATIVE-MISSING-WARN, ENGINE-THREADS-DEFAULT, DOC-DRIFT-ROUTES, HANDLER-ROW-COUNT | 85 F23 resume, CLI half, PER-COLUMN-ROUTING (1.1), CHUNK-PARALLEL (1.3), OOC-QUARANTINE (1.x), OOC-DATE-BUCKET (1.x), FK-CHUNKED-HASH-CHILD (1.x) | none |
| [Local record library](roadmap/groups/library.md) | 36 L2-cli, 37 L3a-cli | 38 L3b-cli, 41 L5a-cli, 42 L5b-cli | none |
| [Sources and targets](roadmap/groups/connect.md) | none | 64 CLI-CLOUD, 64b CLI-DB-SRC, 82 F07, 86 F01, 87 F02 | none |
| [Quality and evidence](roadmap/groups/trust.md) | none | 68 F36, 69 F35, 70 F32 remainder, 72 F33 CLI verifier and engine signature, 78 F10 | none |
| [Install, packaging and release](roadmap/groups/release.md) | 24zc CERT-PIN-CVES, 88 F44 CLI half, UPGRADE-KEY, 89 WIN-FEAS, 6 WIN-RUNNER, 90 REL-PKG, 91 REL-WEB, 92 REL-DOCS, 93 REL-GATE, 94 CLI-REL, EXPERIMENTAL-TIER, QA-BETA | 90a REL-IMAGE, PIP-NATIVE-EXTRA (1.x) | 24zr SETUP-NER-JSON |
| [Codebase health and CI](roadmap/groups/health.md) | 3 CI-E2, 24zf DUP-FREEZE, 24zi PROP-FALLBACK, 24zj PROP-SURFACE, 24zk PROP-SHIMS, 24zo CI-SELECT-GAP, FREEZE-SURFACE | none | 24ze DUP-GUARDS, 24zl PROP-GUARDS, 46 H-1 C0, 47 H-1 C1, 48 H-1 E1.1, 49 H-1 E6a, 50 H-1 E0r, 51 H-1 E1.2, then E1.3, 52 H-1 E2 and E4, 53 H-1 C3, 54 H-1 E7 |

Build order inside 1.0 follows each row's After column and the sequencing rules in
[roadmap/working-rules.md](roadmap/working-rules.md). The release rows (90 to 94) come last.

Platform V1 is parked until CLI V1 ships: [roadmap/platform-parked.md](roadmap/platform-parked.md).

## 5. Linked roadmap documents

| Document | What it holds |
|---|---|
| [roadmap/groups/](roadmap/groups/) | one file per feature group: its 1.0, Later and Maintenance rows |
| [roadmap/inbox.md](roadmap/inbox.md) | untriaged items and open owner questions |
| [roadmap/working-rules.md](roadmap/working-rules.md) | how work moves, develop correctly, sequencing rules |
| [roadmap/platform-parked.md](roadmap/platform-parked.md) | Platform V1, parked, with its rows for the restart |
| [roadmap/post-1.0-plan.md](roadmap/post-1.0-plan.md) | the compatibility rule: what breaks the contract (v2) and what does not (v1+) |
| [roadmap/2.0-holding.md](roadmap/2.0-holding.md) | v2: accepted breaks, items that are v2 only if built the breaking way, and what is fixed for the life of 1.x |
| [roadmap/v2-v3-expansion-candidates.md](roadmap/v2-v3-expansion-candidates.md) | expansion candidates (formats, masks, generators, documents, media); a source for Later |
| [roadmap/release-gates.md](roadmap/release-gates.md) | R1 (CLI V1) and R2 (Platform V1) completion gates |
| [roadmap/row-detail.md](roadmap/row-detail.md) | detail, sources and FRAME findings for the track rows |
| [roadmap/phase-principles.md](roadmap/phase-principles.md) | the phase pillars (the acceptance lens at FRAME) |
| [roadmap/decisions.md](roadmap/decisions.md) | dated owner decisions |
| [roadmap/findings-register.md](roadmap/findings-register.md) | review notes and reconciliation findings G1 to G24 |
| [roadmap/feature-checklist.md](roadmap/feature-checklist.md) | the 29 Council-V1 features and where each lands |
| [roadmap/branch-register.md](roadmap/branch-register.md) | engine and CLI branches with no row, and their disposition |
| [roadmap/sources.md](roadmap/sources.md) | source documents |
| [RECENTLY-SHIPPED.md](RECENTLY-SHIPPED.md) | the shipped log; older entries in [archive/](archive/README.md) |
| [records/2026-11-18-1.0-scope-triage.md](records/2026-11-18-1.0-scope-triage.md) | the 1.0 scope cut, row by row, with reasons |
