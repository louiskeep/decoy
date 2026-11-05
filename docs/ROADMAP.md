# Decoy Roadmap: CLI V1 first, then Platform V1

Status: plan

This is the one Decoy roadmap for all four repos (engine, CLI, platform, web). It moved here from
`decoy-platform/docs/ROADMAP.md` on 2026-11-05 because the CLI is now the main development point.
Owner (Cam, 2026-11-05): "New goal is Decoy CLI V1 complete, then we can return to platform. Move
roadmap over to decoy CLI since that's the main development point, link it from platform."

Built from the platform roadmap at branch `docs/roadmap-v1-ux-map` head `0d484f7f` (Codex GO at
`23c3ca13`; the later commits there are owner answers and rows). That text is kept whole in the
platform repo at `docs/archive/roadmap-status-snapshots/2026-11-05-platform-roadmap-before-move.md`.
Earlier history: platform `docs/archive/roadmap-status-snapshots/` (the 2026-11-03 consolidation
history, the 2026-11-05 pre-CLI-first sequence, the legacy roadmap and the 2026-10-30
reconciliation).

How the facts were checked: main tips, branch heads and plan branches were re-read from origin with
`git fetch` and `git branch -r` on 2026-11-05. Gate verdicts come from the gate ledger
(`10_Projects/decoy/gate-ledger.tsv` in the vault). States reported only by the orchestrator or a
builder say so. Anything not checked says UNVERIFIED.

Editing rule: status tables hold the current state only, one row per item. When a row changes,
replace its text. Old text that must be kept goes into a dated snapshot, not into the row.

Path shorthand: `E:` is the engine repo (`louiskeep/decoy-engine`), `C:` is this repo
(`louiskeep/decoy`), `P:` is the platform repo (`louiskeep/decoy-platform`). "Vault" is
`~/obsidian-vault/10_Projects/decoy/`. Build handoffs named `p05-*.md` are in the vault folder
`handoffs/phase0.5/`; H-1 handoffs and the tracker are in `handoffs/phase1/h1/`.

---

## 1. Goal

**CLI V1** is the engine plus the CLI: a finished, downloadable Decoy application from the website,
fit for production pipelines on Linux and macOS, and on Windows if WIN-FEAS finds no blocker. Owner:
"CLI V1 is going to be a finished, working Decoy application available for download on the website
and use in production pipelines." On Windows: "would be ideal if possible."

**Platform V1** comes after. It is the paid self-hosted product and is PARKED until CLI V1 ships
(section 6). Owner: "Platform is paid, so we don't need to release that at the same time as Decoy
CLI."

**CLI 1.0 is the whole CLI V1 track** (owner, 2026-11-05): every row in section 5.3 ships in 1.0.
There is no early 1.0 cut with later phases shipped as 1.x releases.

In the release gates (section 8), R1 is CLI V1 and R2 is Platform V1.

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

Full text: [`P:docs/product/v1-pipeline-baseline.md`](https://github.com/louiskeep/decoy-platform/blob/main/docs/product/v1-pipeline-baseline.md).
It stays in the platform repo next to the journeys, the capabilities page and the V1 UX map that
link to it. The V1 UX map is `P:docs/product/v1-ux-map.md` (branch `docs/v1-ux-map`, in its own
review); its section 8 is the source of the UX map rows below.

**Engine contracts stay platform-ready.** The platform will later compile the same YAML. A contract
(a config key such as `delivery:`, a reason code, the result document, the publication record) is
built once in the engine and the CLI consumes it. No CLI-only fork of an engine contract.

## 3. How work moves (dev loop and merge rule)

Every row runs the dev loop in `~/dev-rules/development-loop.md` (FRAME, PLAN, build, gate, merge,
DOCUMENT), with risk from `~/dev-rules/risk-and-exceptions.md` and tests from
`~/dev-rules/testing.md`. The PLAN names the behavior, the failure modes and the acceptance tests
first. Plans are authored by Opus and gated by Dennis, then Codex; code gets Codex plus one Dennis
(no OpenRouter gates). The orchestrator merges on double gate green: Codex GO, Dennis GO or APPROVE,
0 V1 findings, a clean trial merge, the head re-verified, a plain squash PR, never `--admin` or
force. Test depth: T0 the touched file's tests per edit, T1 impact-selected per commit, T2 on the
exact merge head; the full suite runs only on an escalation trigger from `testing.md` (registry,
schema, dependency lock, pin, test tooling and the rest) and is diffed against the saved main
baseline, never a second main run. Gates run locally and on self-hosted runners; hosted GitHub CI
is off for billing. The V1 bar: only a function break, data loss or a non-admin leak blocks a merge;
everything else goes to the V2 corrective backlog (vault `handoffs/V2-CORRECTIVE-BACKLOG.md`). A
slice is done when this roadmap and the shipped log ([`RECENTLY-SHIPPED.md`](RECENTLY-SHIPPED.md))
say so. Commits and PR titles follow Conventional Commits (`~/dev-rules/workspace-and-vcs.md`).

## 4. Develop correctly (standing)

Owner (2026-11-05): "make sure we still plan to develop correctly: central registries for any cross
cutting concerns and correctly sized files and file directories." These rules apply to every row
and every plan. Source rules: `~/dev-rules/cross-cutting-concerns.md` and
`~/dev-rules/architecture.md`.

**4.1 One registry or choke point per cross-cutting concern.** A rule that many call sites must
follow (a reason code, a file write mode, a path check, an outbound client limit, a redaction rule)
lives in one place that every site must pass through, so forgetting it fails a test instead of
failing silently. Each choke point has a guard test that walks the real artifact (the import graph,
the syntax tree, the registry manifest), not a list the author remembers. Known exceptions sit in a
ratchet allowlist that can shrink but never grows without a reviewed change (the X0a ratchet
manifest: engine #378, #379; CLI #81, #82).

Choke points the CLI V1 track builds on or adds:

| Concern | Choke point | Guard | Row |
|---|---|---|---|
| Reason codes | `E:src/decoy_engine/reasons/_registry.py`, append-only, versioned | registry and release-pin tests; REG-RENUMBER `--check` at merge | every registry row |
| Safe output and redaction | F31 `SafeEvent` and closed error labels (engine #368) | F31 sentries and the secret-injection corpus | F31 |
| File access | engine file-access policy (A-4, engine #361) | file-access sentry baselines | all source readers |
| Outbound clients | engine connector client limits (X4d, engine #384, #385) | construction sentry | CLI-CLOUD, F02 |
| Private file writes | engine `_private_file` (X7b, engine #382); CLI `_private_file.py` | write-mode sentries | X7c |
| CLI source readers | `C:src/decoy/cli/_sources.py` (`read_source`, `iter_source_chunks`) | CLI-DIALECT tests | CLI-DIALECT |
| CLI target writers and readers | one `C:src/decoy/cli/_targets.py` | format and suffix tests | CLI-FMT A and B |
| Local record library writes | one library writer (LIB L1b) | `C:tests/sentry/test_library_writer.py` | LIB rows |
| Scratch and quotas | the F25 scratch manager | registration sentry | F25 |
| Publication and delivery | F22 publication descriptor, DELIV transactional sink | delivery tests | F22, CLI delivery |
| Module size | the size census per repo | `test_module_size.py` | FILE-SIZE |

A plan that adds a call site names the choke point it goes through. A plan that adds a new concern
names its registry and its guard test, or says why none is needed. A review finding that is a class
of bug (the same mistake possible at many sites) gets a choke point and a sentry, not only a patch.

**4.2 File and directory size.** Source files stay at about 800 lines or fewer. The engine census is
stricter and stays as it is (`E:tests/sentry/test_module_size.py`: goal 600, ceiling 700, exact-match
allowlist). A touched file that is already over the limit must not grow; a slice that needs to add
to it splits it first or moves the new code into a new module. Splits follow the reason to change and
produce cohesive packages, not size-only cuts (H-1). A package that collects too many modules gets
subpackages: `E:src/decoy_engine/execution/` holds 93 modules today (H-1 E8). Oversize today
(2026-11-05): CLI `report.py` 2373, `run.py` 1717, `scan.py` 1405, `preflight.py` 886 lines (the CLI
has no size sentry yet); engine `storm/detectors.py` 1046, `execution/native/_draw_site_providers.py`
985, `storm/eval/corpus.py` 976, `execution/_chunked_fk.py` 970, `execution/native/_determinism_protocol.py`
928, `quality/synth_report.py` 863. A slice is at most about 800 hand-written lines including tests;
bigger work is split into stacked parts.

**4.3 The owner's review question.** Owner (2026-11-05): every plan, build and gate asks "is this
doing something that every other class does differently? could it be rolled into a central location
to make it easier to change later?" A yes means the plan adds or reuses a choke point (4.1) before
the slice adds another copy. Builders read `~/dev-rules/00-universal.md`,
`~/dev-rules/cross-cutting-concerns.md`, `~/dev-rules/architecture.md` and `~/dev-rules/testing.md`
before they write code, and every build handoff says so.

**4.4 Plans name both.** Every PLAN states (a) the registry or choke point for each cross-cutting
rule it touches, and (b) each file it adds or grows, with its line count before and after and the
package it lands in. A gate that finds a plan missing either sends it back.

---

## 5. CLI V1 track

### 5.1 Main tips (re-read from origin, 2026-11-05)

| Repo | Tip | Recent merges | Pin and registry |
|---|---|---|---|
| decoy-engine | `41a86f47` (#383; highest merged PR #386) | #381 H-1 E5, #382 X7b, #383 golden suite repair (CI-E0), #384 and #385 X4d, #386 H-1 E3 | latest tag `v0.18.0` (`f5b46a2c`); `REGISTRY_VERSION` 1.5.0 |
| decoy (CLI) | `8fba6af` (#82) | #80 F30 C1a, #81 and #82 CLI X0a | `decoy-engine==0.18.0` (#79) |
| decoy-platform | `73a0bfca` (#196) | #178 to #196 (see section 6) | `decoy-engine==0.18.0` (#149) |

### 5.2 Sequencing rules

1. **Reason registry chain.** SUB-STOP takes 1.6.0, STORM E1 takes 1.7.0, then every other
   registry-touching row takes the next free minor in merge order (owner OQ-3 = C1, 2026-11-05).
   Once REG-RENUMBER merges, registry slices may build in parallel; they still merge one at a time,
   and the tool renumbers each slice to `main + 1` at merge (owner, 2026-11-05). Until it merges, the
   chain is strictly serial by build order (owner rule, 2026-11-03).
2. **One writer per hot file.** One branch at a time writes `C:src/decoy/cli/run.py`, and one at a
   time writes `C:src/decoy/cli/scan.py`. Rows that write `run.py`: CLI-DIALECT, CLI-FMT A,
   VALIDATE-ALWAYS, SUB-RUN CLI half, CLI delivery, RESULT, SAMPLE, LIB L3a, L3b, L5a, F23 resume, F29
   C1, F30 C1b. Rows that write `scan.py`: SCAN-MULTI S1c and S3-cli, LIB L2, H-1 C3, STORM CLI
   half. The plan for each says which.
3. **Engine releases.** One release and one CLI repin open at a time. A CLI half that needs new
   engine code waits for the release and the repin (engine repin checklist: compatibility, fences,
   frozen surfaces, docs, `PIN_PREFIX`, the Dockerfile `ARG`, the catalog).
4. **Release cadence.** Cut an engine release from main every 2 to 3 days while engine rows are
   merging, carrying whatever has merged (owner may release without per-release confirmation). The
   CLI repins once per release, cumulatively: one repin carries every engine change since the last.
   Named releases below (R-c, R-d) list what each must contain at minimum; the cadence decides when.
5. **LIB.** L1a-engine, then an engine release and the CLI repin, then L1b, then L1c. L2, L3a, L3b,
   L4a, L4b, L5a and L5b follow L1c and their feature rows, in parallel on files that do not
   overlap.
6. **SCAN-MULTI.** S1a and S1b ship in one engine release. CLI-DIALECT lands before S1c, and S1c
   before LIB L2 (L2 replaces the plan's S1d). CONFIG-EXPLICIT lands before S3-engine; S3-engine is
   released, then S3-cli.
7. **CLI-FMT.** Part A after CLI-DIALECT; Part B is stacked on A; A never merges without B (one T3
   on B's head, then A and B in order).
8. **Publication chain.** F25 before F22 (owner, 2026-10-30); F22 and POSTSCAN-STREAM before CLI
   delivery; SUB-STOP before SUB-RUN; SUB-RUN before SAMPLE; F22 and CLI delivery before F23 resume.
9. **H-1** slices move only files no live branch touches, behavior-preserving, characterization
   tests first.

### 5.3 The track (ordered)

Order is the build order within the dependencies. "After" lists what must merge first. Branches are
on origin unless marked local. Detail for each row is in 5.4.

**A. Test, CI and structure foundations**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 1 | CI-E1: engine CI installs from the lock (`uv sync --frozen`), stale bench kwargs, sphinx `-W` cross-refs, truthful `pip-audit`, two sentries | engine | BUILDING (local builder; branch 4 commits ahead, not pushed) | `fix/ci-e1-frozen-installs` local `b56be570`; `p05-ci-e1-build-handoff.md` | CI-E0 (MERGED, engine #383) |
| 2 | CI-E1s: lock security bump (26 known vulnerabilities in 8 packages) and DP certified-stack fingerprint re-pin | engine | NOT STARTED | none | CI-E1 |
| 3 | CI-E2: restore engine CI triggers, nightly `determinism`, `ci/required-jobs.toml`, `ci/unlaned.toml`, marker and trigger sentry, retire `engine-v2-substrate-matrix.yml` | engine | NOT STARTED | none | CI-E1, CI-E1s (until CI-E1s, CI-E2's gate exempts `security.yml`) |
| 4 | ENGINE-PAR: engine parallel tests (pytest-xdist), engine full suite from about 66 minutes to roughly 15 to 20 on the 4-core VMs and the Mac; serial marks only for exclusive resources; same baseline-compare rules | engine | handoff to write | ports P:`feat/parallel-tests` (parked; origin `2804b2af`, local `28507dce`) | CI-E1 |
| 5 | CI-L1: CLI CI (`ci.yml` installs `uv`, runs pytest; `ci/required-jobs.toml`, `ci/unlaned.toml`, sentry) | CLI | NOT STARTED | CI lanes plan `P:docs/plans/2026-11-05-ci-lanes.md` (#187) | none |
| 6 | WIN-RUNNER: Windows self-hosted runner on a GCP VM; spend approved by the owner; stopped when idle (`~/bin/vm-reap`) | infra | NOT STARTED; provision when CI-L1 or LIB L1b first needs a Windows lane | LIB plan section 5 OS lanes | none |
| 7 | FILE-SIZE: file-size ratchet sentry for engine and CLI (new, section 4.2) | engine, CLI | NOT STARTED; plan to write | none | CLI X0a ratchet (MERGED, CLI #81, #82) |
| 8 | REG-RENUMBER: `E:scripts/dev/registry_renumber.py` renumbers an unmerged slice's registry minor to `main + 1` at merge; `--check` for the merge gate | engine | plan review (Dennis, then Codex; full plan gate) | `feat/reg-renumber-tool` (not built); `p05-reg-renumber-build-handoff.md` | none; first useful after SUB-STOP |
| 9 | X0a-h engine and CLI parts (E1, E2, C1, C2): vendor `_ratchet.py`, `_approval.py`, `approve_growth.py`, `merge_check.py` byte-identical from the platform | engine, CLI | DEFERRED, off the V1 path (owner, 2026-11-05). Until it returns, the orchestrator flags any ratchet baseline growth by hand at each gate. Re-entry: a hidden exception slips past review, or the platform restarts | plan `P:docs/plans/2026-11-05-x0a-h-ratchet-hardening.md` (#181) | platform H1, H2, H4, H6 (parked) |

**B. Registry chain, gated engine branches and the first release**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 10 | SUB-STOP: every engine entry that runs a config refuses `subset:` before any read, `config.subset_run_unsupported`, registry 1.6.0 | engine | BUILT (orchestrator); not pushed; gate next | `fix/sub-stop-refuse-unrun-subset` (worktree `~/vscode/wt-sub-stop`); `p05-sub-stop-build-handoff.md` | none |
| 11 | Vault key floor and simpleeval floor (slice 0: 11.1, 12.3) | engine | Codex GO-WITH-FIXES; CLI consumer side met by CLI #78 | `fix/vault-key-floor` `b79e864b` | merge in R-c |
| 12 | B-6 vault core | engine | Codex re-check GO (static trace) | `feat/b6-vault-core` `52df1da8` | row 11; merge in R-c |
| 13 | Derived expression visibility (slice 0: 12.1 residue) | engine | Codex GO, 0 V1; no Dennis row | `fix/derived-visibility` `ac3da2a7` | Dennis, then merge |
| 14 | Value-free discovery and subset errors | engine | Codex round 2 GO; no Dennis row | `fix/value-free-discovery-subset-errors` `7dcd95f4` | Dennis, then merge |
| 15 | F32 E1 | engine | Codex GO, Dennis GO-WITH-FIXES on `55b28933` (2 HIGH; V1 status UNVERIFIED) | `feat/f32-e1` `55b28933` (side branches `feat/f32-e1-labels`, `feat/f32-e1-types`) | re-check, then merge |
| 16 | STORM E1 (engine part of the STORM rename), registry 1.7.0 | engine | NOT MERGED; no `feat/storm-e1` on origin | STORM re-cut plan `P:plan/storm-rename-recut` `dfe7cc6a` | SUB-STOP |
| 17 | WF-R engine and CLI part: tombstone the engine `WORKFLOW_*` reason codes (`E:src/decoy_engine/reasons/platform/_part1.py:72-74`, never deleted) and fix the CLI pointer (`C:src/decoy/cli/explain.py:170`) | engine, CLI | NOT STARTED | none | registry order |
| 18 | Engine release R-c and CLI repin: vault key floor, B-6 core, SUB-STOP, STORM E1, whatever else has merged, and the F34 release if owner Q4 says so | engine, CLI | NOT STARTED | none | rows 10 to 12, 16 |

**C. Live CLI bugs and explicit config**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 19 | CLI-DIALECT: `decoy run` honours `has_header`, `column_names` and `delimiter` (live V1 bug); owned by CONFIG-EXPLICIT, lands ahead of it | CLI | plan review | `p05-cli-dialect-build-handoff.md` | none |
| 20 | CLI-FMT Part A: write file targets by declared `format` through one `_targets.py`; fixed width through the engine's `write_fixed_width`; format and suffix mismatch, and `--chunked` with fixed width, refused with exit 1 | CLI | handoff written, plan gate | `fix/cli-fmt-write-declared-format` (not built); `p05-cli-fmt-build-handoff.md` | CLI-DIALECT |
| 21 | CLI-FMT Part B: `detokenize`, `unmask` and `report diff` read CLI-written files by declared format; the evidence manifest records `format` and `layout` | CLI | handoff written, plan gate | `fix/cli-fmt-b-read-declared-format` (stacked on A); `p05-cli-fmt-b-build-handoff.md` | Part A; merges with A |
| 22 | CONFIG-EXPLICIT: `has_header` required for CSV sources; headerless files declare `column_names` or a new `column_names_file` (exactly one); every source column listed in `columns:` (`passthrough` allowed), so an unlisted column always fails; `unconfigured_column_policy` retired or fixed to `error` | engine, CLI | plan being authored | none yet | registry order; CLI half after the release that carries it |
| 23 | VALIDATE-ALWAYS: `decoy run` runs every `decoy validate` check (config, compile, preflight) first and stops on an error | CLI | NOT STARTED | none | none |
| 24 | X7c: CLI private file writes (`_private_file.py`) | CLI | NOT STARTED; no branch | none | none |

**D. Scan (SCAN-MULTI and the scan follow-ons)**

SCAN-MULTI plan: `E:docs/plans/2026-11-05-scan-multi-fk-discovery.md` on engine branch
`plan/scan-multi` `9b7cd9ab`. Dennis GO-WITH-FIXES; in a fix round. No FK inference in V1 (users
declare relationships; value-based FK discovery is parked for V2). Columns with no PII default to
`redact` in the starter YAML.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 25 | SCAN-MULTI S1a-engine: `scan_sources` and `scan-set/v1` (~470 lines) | engine | plan fix round | `plan/scan-multi` | plan GO |
| 26 | SCAN-MULTI S1b-engine: declared-relationship integrity facts (~480 lines) | engine | plan fix round | `plan/scan-multi` | S1a types; same release as S1a |
| 27 | SCAN-MULTI S1c-cli: `decoy scan` over many tables (~690 lines) | CLI | plan fix round | `plan/scan-multi` | S1a and S1b release and repin; CLI-DIALECT; CONFIG-EXPLICIT for `--column-names-file` |
| 28 | SCAN-MULTI S3-engine: `starter_config` and `scan_baseline` (~560 lines) | engine | plan fix round | `plan/scan-multi` | S1a; CONFIG-EXPLICIT |
| 29 | SCAN-MULTI S3-cli: `--emit-config` and `--compare` (~720 lines including moved code) | CLI | plan fix round | `plan/scan-multi` | LIB L2 (in place of S1d); S3-engine release and repin; CLI-DIALECT |
| 30 | SCAN-LIB: scan snapshot library (`scan-set/v1` under `.decoy/`); the YAML references a snapshot as its baseline and the run hashes it into evidence | engine, CLI | mostly delivered by S1a (`scan-set/v1`), LIB L2 (snapshots in the library) and S3 (`scan_baseline`); the run-evidence hash is the remainder; confirm at their plan GO | none | S1a, L2, S3-engine |
| 31 | DIST-INTEGRITY: opt-in pre-scan distribution capture plus a post-scan check within n%; a breach blocks in strict mode | engine, CLI | NOT STARTED | none | SCAN-LIB, POSTSCAN-STREAM |
| 32 | DRIFT: opt-in pre-scan drift check at run start against a SCAN-LIB baseline (`on_drift: warn` or `fail`) | engine, CLI | NOT STARTED | none | SCAN-LIB |

**E. Local record library (LIB)**

LIB plan: `C:docs/plans/2026-11-05-local-record-library.md` on CLI branch `plan/local-record-library`
`6b50e72` (revision 2 records the owner answers). Dennis GO-WITH-FIXES; in a fix round. Four
retention classes under one project root `.decoy/`; `decoy run` writes records by default
(`--no-library` turns it off).

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 33 | L1a-engine: records module (~520 lines) | engine | plan fix round | `plan/local-record-library` | plan GO |
| 34 | L1b-cli: store, atomic writes, refs, scratch (~700 lines); Linux, macOS and Windows lanes | CLI | plan fix round | same | L1a release and repin; WIN-RUNNER |
| 35 | L1c-cli: index, fsck, degraded mode (~560 lines); three OS lanes | CLI | plan fix round | same | L1b |
| 36 | L2-cli: scan snapshots on the library (~380 lines; replaces SCAN-MULTI S1d) | CLI | plan fix round | same | L1c; SCAN-MULTI S1c |
| 37 | L3a-cli: evidence and run-result records (~520 lines) | CLI | plan fix round | same | L1c; RESULT for the run-result half |
| 38 | L3b-cli: sample-run records and scratch lifecycle (~450 lines); three OS lanes | CLI | plan fix round | same | L1c; SAMPLE |
| 39 | L4a-cli: library commands, first part (`list`, `show`, `diff`, `ref`, `export`) | CLI | plan fix round; the plan's L4 (~720 lines) is being split into L4a and L4b | same | L1c (L3a for run-result `diff`) |
| 40 | L4b-cli: library commands, second part (`prune`, `clean`, reachability); three OS lanes | CLI | plan fix round | same | L4a |
| 41 | L5a-cli: wire the engine `ProgressSink` into `decoy run` (~380 lines) | CLI | plan fix round | same | L1c |
| 42 | L5b-cli: job logs (~500 lines); three OS lanes | CLI | plan fix round | same | L5a, L3a |

The L4a and L4b command split above is this roadmap's reading of the fix round; the plan's next
revision is the authority.

**F. Structure: H-1 Wave B engine and CLI slices, STORM CLI half, size sentry**

H-1 tracker: vault `handoffs/phase1/h1/H1-TRACKER.md`. Plan: `P:docs/plans/2026-11-01-h1-wave-b-code-organization.md`
on `P:plan/h1-wave-b` `944fb295` (Codex GO). Only files no live branch touches.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 43 | H-1 E0: pure-move checker and Wave B sentries | engine | MERGED (engine #372 to #375) | done | n/a |
| 44 | H-1 E5 | engine | MERGED (engine #381) | done | n/a |
| 45 | H-1 E3 | engine | MERGED (engine #386) | done | n/a |
| 46 | H-1 C0: CLI size census and checker port | CLI | handoff not written | none | E0; fold into FILE-SIZE if the plans overlap |
| 47 | H-1 C1: split `C:src/decoy/cli/distribution/installer.py` | CLI | handoff not written | none | C0 |
| 48 | H-1 E1.1 | engine | handoff not written | none | E0 |
| 49 | H-1 E6a (and E6b) | engine | handoff not written | none | E0 |
| 50 | H-1 E0r: F29 producer inventory regeneration | engine | handoff not written | none | F06 #338 (merged) |
| 51 | H-1 E1.2, then E1.3 | engine | handoff not written | none | A-4 (merged) |
| 52 | H-1 E2 and E4 | engine | handoff not written | none | E0r |
| 53 | H-1 C3 | CLI | handoff not written | none | STORM CLI half; CLI branches `claude/storm-split-cli`, `claude/vibrant-feynman-1khw1v` settled |
| 54 | H-1 E7: split files as their blockers merge | engine | not planned in detail | none | per file |
| 55 | H-1 E8: `execution/` root restructure (93 modules) | engine | waits on H-1 Q3 (owner) | none | an engine release and the repins |
| 56 | STORM rename, CLI half: re-cut so CLI C0 vendors `storm_slice_measure.py`, `storm_inventory.py`, `slices-cli.json` and drops the platform S2c dependency; CLI V1 ships the new names | CLI | NOT STARTED; re-cut plan needed (owner OQ-2 = B1) | from `P:plan/storm-rename-recut` `dfe7cc6a` | R-c repin |

**G. Phase 1 engine and CLI: trustworthy local run**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 57 | SUB-RUN: subset inside a pipeline run (`run_subset` inside `run_pipeline`); decide on the Parquet-only rule for relationship tables | engine, CLI | NOT STARTED | none | SUB-STOP; CLI half after its release |
| 58 | F25: protected scratch, quotas, orphan recovery | engine | plan in gate (Codex r7 GO; Dennis r5 GO-WITH-FIXES with 1 blocker) | `E:plan/f25-4c-consumer-capabilities` `53950b27`; `E:feat/f25-protected-scratch` `4c901d38` | none |
| 59 | F22: atomic and idempotent publication | engine | plan revision (Codex r9 NO-GO, 1 blocker); revision must drop the Linux-and-macOS-only rule (WIN-FEAS) | `E:plan/f22-publication-replan` `db230090` | F25 |
| 60 | POSTSCAN-STREAM: post-scan integrity streams chunk by chunk on every route, with output PK and FK checks when keys are declared | engine | NOT STARTED | none | before CLI delivery makes post-scan blocking |
| 61 | CLI delivery (DELIV engine and CLI half): stage then deliver, strict and best-effort, local single-root rule, chunked path (G4) through the same sink; blocks CLI V1 (Q22) | engine, CLI | NOT STARTED | none | F22, POSTSCAN-STREAM; CLI half after R-d |
| 62 | RESULT: run result document, exit 6, capacity widening (in F29 C1) | engine, CLI | NOT STARTED | `E:plan/f29-errors-progress-remainder` `a26994bf` | DELIV best-effort for exit 6; CLI half after R-d |
| 63 | SAMPLE CLI half: `decoy run --sample N` through the subset; output to scratch, never to targets; same behavior on delimited, CSV, fixed-width and Parquet; blocks CLI V1 (Q24) | engine, CLI | NOT STARTED (owner: "very good feature") | none | SUB-RUN; CLI half after R-d |
| 64 | CLI-CLOUD: S3 and GCS in the CLI through the DELIV cloud run prefix and conditional pointer | CLI | NOT STARTED; assumed CLI V1 (UX map Q6 open) | none | CLI delivery |
| 65 | F31: shared safe-output and redaction (remaining build slices) | engine, CLI | plan rev 9 GO; E0a, E0c MERGED (engine #368, #377) | `E:plan/f31-safe-output` `2340a45b` | none |
| 66 | F29 remainder: CLI consumers (C1, which carries RESULT) and the F31 hook | engine, CLI | C0 MERGED (engine #367) | `E:plan/f29-errors-progress-remainder` | F31 for the hook |
| 67 | F34 E3 and the F34 release | engine | E0, E1, E2 MERGED (engine #365, #370, #371) | `P:plan/f34-residual-canary-span` `785af293` | registry order; owner Q4 |
| 68 | F36: cross-column invariants (finish), entry slices, slice 4 registry | engine | plan rev 8 GO | `E:plan/f36-cross-column-invariants` `9ed7b47f` | F06 (merged) |
| 69 | F35: quality contracts, E1a onward (registry) | engine | plan rev 4 GO | `P:plan/f35-quality-contracts` `7a3471af` | registry order |
| 70 | F32 remainder: engine E1b to E3, CLI C0, C1, C1b | engine, CLI | plan Codex r5 GO, Dennis r4 GO-WITH-FIXES | `P:plan/f32-support-bundles` `39c2772c` | F32 E1 (row 15); F31 |
| 71 | F30 CLI: C1b and the CLI repin to the F30 release | CLI | C1a MERGED (CLI #80); E1 MERGED (engine #369) | `P:plan/f30-telemetry` `4b385672` | F30 release; F31 |
| 72 | F33 CLI verifier and engine signature envelope | engine, CLI | plan Codex r12 GO, Dennis r10 NO-GO | `P:plan/f33-signed-evidence-platform-cli` `f4500052`; engine PR #335 (OPEN) | Dennis on the current head; F31 |
| 73 | F13 slices 3b and 5 | engine | plan Codex gate 4 NO-GO (3 blocker, 2 high) | `E:plan/f13-slices-3-4` `18847ac0` | plan revision |
| 74 | F26 CLI local cleanup and engine part | engine, CLI | PARKED until F22 settles; Opus re-scope first | engine PR #337, CLI PR #68 (OPEN) | F22 |
| 75 | One CLI journey for V1; the CLI smoke cites journey ids | CLI | NOT STARTED | none | CLI delivery |
| 76 | Engine release R-d and CLI repin: SUB-RUN, F25, F22, POSTSCAN-STREAM, the engine halves of CONFIG-EXPLICIT (if not earlier), DELIV, RESULT, SAMPLE, and the engine parts of SCAN-LIB, DIST-INTEGRITY and DRIFT; under the cadence this becomes several releases | engine, CLI | NOT STARTED | none | the rows it carries |
| 77 | Later engine releases and CLI repins (R-e onward), one per group of merged rows 65 to 74 and 78 to 88 | engine, CLI | NOT STARTED | none | the rows each carries |

**H. Phase 2 engine and CLI: portable and repeatable**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 78 | F10: lock envelope (`lock/v1` with `key_version`), synthetic probe, CLI environment report, fleet comparison | engine, CLI | NOT STARTED | none | Phase 1 rows |
| 79 | F09: domain-version object, rotation and remap (engine); authenticated, versioned CLI token vault header (G9, 11.8) | engine, CLI | NOT STARTED | none | B-6 core |
| 80 | F15: bound-baseline object, strict-drift publication block; scan-diff moves into an engine `scan-diff/v1` | engine, CLI | NOT STARTED | none | STORM rename; SCAN-LIB |
| 81 | F16: selector grammar, prohibition predicates, 5-level precedence; disguises applied in the engine | engine, CLI | NOT STARTED | none | Phase 1 rows |
| 82 | F07: bounded path-observation discovery, nested-path relations, JSONB coverage | engine | NOT STARTED | none | STORM rename |
| 83 | F13 external adapters (HashiCorp Vault, AWS and GCP Secret Manager, Azure Key Vault) | engine, CLI | NOT STARTED | none | F13 preflight (merged) |
| 84 | F24 engine half: full-lifecycle estimate including the ingestion peak; advisory only | engine | NOT STARTED | none | estimator (engine #328) |
| 85 | F23 resume, CLI half: `decoy run --resume RUN_DIR`, table-level (UX map Q12 open; recommendation table-level) and the engine checkpoint store | engine, CLI | NOT STARTED | none | F22, CLI delivery |

**I. Phase 3 engine and CLI: connected safe-copy**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 86 | F01: PostgreSQL application-ready write target (staging, constraint, index and sequence restore, atomic publish) and the type-mapping report | engine, CLI | NOT STARTED | none | Phase 2 rows; F22 |
| 87 | F02: SFTP, cloud scan, subset against cloud; retry executor; content digest on `WriteResult` | engine, CLI | NOT STARTED | none | CLI-CLOUD; F22 adapter |
| 88 | F44 CLI half: signed bundles, `decoy upgrade` preflight, rollback and offline signature path, release-time SBOM | engine, CLI | SBOM generators MERGED (engine #355, CLI #75; polish #359) | `C:docs/plans/2026-10-22-cli-distribution-and-packaging-spec.md` | REL-PKG |

**J. Release**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 89 | WIN-FEAS: Windows for the CLI and engine (private file ACLs instead of 0600, atomic replace with open files, file-access path handling, installer and signing); a blocker goes back to the owner | engine, CLI | NOT STARTED | none | before CLI-REL; LIB L1b gives the first evidence |
| 90 | REL-PKG: packaging. Signed per-platform bundles with a managed runtime, signer choice (minisign or cosign) and key custody, SHA-256 manifest, verify before extract, install script, offline archive; native companion wheels (engine #353 workflow, never run); NOTICE, SBOM, `--version` (G2) | engine, CLI | B-2 MERGED (CLI #66, #67; engine #353); owner tasks open (signing key, `native-release` Environment, `native-v*` tag rule, qemu SHA pin) | packaging spec above | WIN-FEAS for Windows |
| 91 | REL-WEB: website download page on decoy-web, update-check endpoint with its privacy contract (no data, no identifiers, no telemetry), `/proof` synced (B-3) | web | NOT STARTED | decoy-web | REL-PKG |
| 92 | REL-DOCS: public CLI docs (Fumadocs at decoy.dev/docs, decoy-web PR #18) with the P0 pages from the CLI doc audit, install and upgrade docs, release notes, security contact; D-5 launch-gate flip | web, CLI | docs held draft | decoy-web PR #18 | the commands they document |
| 93 | REL-GATE: R1 gates. D-4 launch engine freeze, R1-c signing key and license values (owner and counsel), versioning freeze (exit codes including 6, result schema, YAML schema, reason registry), canonical release smoke with recorded runs, a filled release-readiness instance, claims and license checkpoint | engine, CLI, web | NOT STARTED | section 8 | every row above |
| 94 | CLI-REL: the CLI V1 release. Final engine release and repin, publication to the download host, smoke install from the published artifact on each supported platform (Linux x86_64 and aarch64, macOS arm64, Windows x86_64 subject to WIN-FEAS) | engine, CLI, web | NOT STARTED | none | rows 89 to 93 |

The track has 94 rows. Rows 43 to 45 are merged and kept so the H-1 sequence reads whole; the
other 91 are open (some carry merged earlier parts, named in their State). Merged groundwork that is
not a row is in 5.7.

### 5.4 Row detail

**SUB-STOP (row 10).** Closes the silent ignore of `subset:` in a run (UX map Q1, run-confirmed).
The CLI gets the refusal after R-c and the repin. SUB-RUN later replaces the refusal.

**CLI-DIALECT, CLI-FMT, CONFIG-EXPLICIT (rows 19 to 22).** UX map Q20 (run-confirmed) and section
3.9. Owner (2026-11-05 night): "explicit config is important." Today `has_header` is optional with
default true (`E:config/_sources.py:95-101`). The parked CLI branch `claude/enterprise-hardening`
(archive tag `archive/claude/enterprise-hardening`, `17bb5006`) has a fixed-width writer that stays
parked; fixed-width output is V1 through CLI-FMT.

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
The dev-rule `cross-cutting-concerns.md` is the standing rule (section 4).

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

### 5.5 CLI-REL scope (rows 89 to 94)

Source: `C:docs/plans/2026-10-22-cli-distribution-and-packaging-spec.md`.

- The final engine release and CLI repin.
- Signed per-platform bundles and the installer, published to the download host, then a smoke install
  from the published artifact on each supported platform.
- The update-check endpoint and its privacy contract; the F30 opt-in statement.
- Platform matrix: Linux x86_64 and aarch64, macOS arm64, Windows x86_64 subject to WIN-FEAS (owner
  OQ-4). This supersedes the F22 "Linux and macOS only" note.
- Native companion wheels through the engine native-release workflow and the B-2 owner tasks.
- Versioning freeze at V1: exit codes (including 6), the result document schema, the YAML schema, the
  reason registry.
- CLI `--version` (literal `0.1.0` today, G2), CLI NOTICE and SBOM, security contact, release notes.
- Public docs, download page, install and upgrade docs.
- License: BUSL-1.1 for the self-hosted distribution per the 2026-10-22 CLI launch direction; owner
  and counsel confirm in R1-c (the engine license, Apache-2.0 versus BUSL-1.1, is also R1-c).
- Production-readiness checks.

### 5.6 Open questions for the owner (CLI V1)

- Owner Q4: is R-c the F34 release?
- UX map Q6 (CLI cloud I/O) and Q12 (resume level).
- H-1 Q3 (engine `execution/` restructure timing) and the other open H-1 questions.
- Phase 1 tracks questions still open from `PHASE1-TRACKS.md`: Q5 (order of F35 E1a and F32 E1b; the
  2026-11-03 chain put F35 first), Q9 (fate of `feat/f25-protected-scratch`), Q11 (F36-P timing).
- Still open from earlier: the SBOM lock-mode refusal that prints lock package names; the engine
  `vault_key_mismatch` message still says "the config's seed does not decrypt this vault"
  (`vault.py:520-524`).

### 5.7 Merged engine and CLI groundwork (not rows)

Engine: R-a `v0.17.0` and R-b `v0.18.0` (`f5b46a2c`); A-4 file access (#361); OOC temporal FK seam
(#360); CDF exact-integer builder (#363); NOTICE and license gate (#362); SBOM polish (#359); subset
explicit keys (#366); F34 E0, E1, E2 (#365, #370, #371); F06 (#338); H-1 Wave A (#348) and E0 stack
(#372 to #375); F31 E0a (#368) and E0c registry 1.5.0 (#377); F29 engine half (#336) and C0 (#367);
F30 E1 (#369); F13 slices 0 to 2 (#339); STORM split and close-out (#329, #349); A-7 text-redact
speedup (#327); D2 RSS sentry (#316); A-8 tokenize write seam (#322); estimator `estimate_job` (#328);
B-9 DI1a (#326); B-6 stage 1 (#331); native-release workflow (#353, unexercised); worker bootstrap
(#347); X0a (#378 to #380); X4d (#384, #385); X7b (#382); H-1 E5 (#381), E3 (#386); CI-E0 golden
suite repair (#383).

CLI: B-1 tokenize and local vault (#64); B-2 CLI-LAUNCH packaging (#66, #67); R1-a `resolve_substrate`
fix (#71); worker bootstrap (#70); F43 (#69); SBOM generator (#75); repins to 0.17.0 and 0.18.0 (#76,
#79); F13 4a/4b `--mask-secret` (#78); F30 C1a OTel exporter (#80); X0a ratchet (#81, #82); init
wizard spec (#73, post-V1).

---

## 6. Platform V1: PARKED

Owner, 2026-11-05: "finish out in flight platform work, document completely, pause platform
development. Focus on CLI/engine through the entire roadmap, then once CLI V1 is out, we can work
platform v1." Restart trigger: CLI V1 has shipped.

Pause record: [`P:docs/PARKED.md`](https://github.com/louiskeep/decoy-platform/blob/main/docs/PARKED.md)
(being written on platform branch `docs/platform-parked`) and the vault note
`10_Projects/decoy/platform-pause-2026-11-05.md` (each finish-out merge is recorded there). On
restart, re-check every row against main first: the engine contracts will have moved under the CLI V1
track.

### 6.1 Group 1: merging now

| Item | State (2026-11-05) | Branch and head |
|---|---|---|
| X10a: job-row choke point and STORM scan pricing (two parts) | Dennis GO and Codex GO round 3; VM 6 merge test 0 NEW-FAILING | `feat/x10a-job-row` `78f25309` (A), `feat/x10a-sentries` `0a0e1468` (B) |
| X4a part A: cloud client factories | Dennis GO, Codex GO at `397c290a`; targeted gate clean | `feat/x4a-clients-onmain` `2923ced4` |
| RBAC S0a: record-mode gate baseline per route and role | Dennis delta GO, Codex GO (`c-s0a4`) at `11ce7f14`; full merge test on VM 5 | `feat/rbac-s0a-gate-baseline` `11ce7f14` |
| X9a: notification owner required, broadcast named, scope sentry (two parts) | Codex GO (`c-x9a`); Dennis reviewing | `feat/x9a-notify-scope-a` `eb53fb2a` (A), `feat/x9a-notify-scope` `93a01a8d` (B) |

### 6.2 Parked with work done (from the finish-out list)

| Item | State at the pause | Branch and head |
|---|---|---|
| Operator set-password (pre-V1 recovery command) | Codex GO-WITH-FIXES on `961eec5a`; value-free fix pushed | `feat/operator-set-password-r2` `83ebb404` |
| X0a-h H6: trusted merge check | Codex GO; Dennis GO-WITH-FIXES (2 MEDIUM, 5 LOW) on `2c1bd451`; uncommitted edits in its worktree | `feat/x0a-h-h6-merge-check` `2c1bd451` |
| X0a-h H1 (owner-signed growth), H2 (ratchet integrity), H4 (gate hygiene) | handoffs written (status plan); not built | `p05-x0ah-h1/h2/h4-build-handoff.md` |
| X1a part A: OWNED_MODELS registry | plan double green; builder in progress, not pushed | `feat/x1a-owned-models` (local, `~/vscode/wt-x1a`) |
| Parallel tests (xdist) | 41 VM failures being fixed; local head ahead of origin | `feat/parallel-tests` origin `2804b2af`, local `28507dce` |
| `plan/x0a-h` | redundant (diff to main empty; #181 merged) | `plan/x0a-h` `0a8d55d2` |

### 6.3 Platform rows kept for the restart

Restart order (preserved from the 2026-11-04 sequence):

1. Phase 0.5 platform slices, in the plan's wave order: X1a part B, X3a, X0a-h H3 and H5, X1b to X1f
   (X1b, X1c, X1d1, X1d2, X1e1, X1e2, X1f), X2b, X4a part B, X4b, X4c, X5a, X5c, X6a, X8a onward, WF-R
   backend (before X1d2 and X1e2), RBAC S0b onward (route registry plan `plan/rbac-route-registry`
   GO at `178ce71d`), deactivation S2 onward (plan `plan/user-deactivation` GO at `7ece3622`), CI-P1
   to CI-P3, OUT-PATH, test trust TT-T2 and TT-T4. X2a MERGED (#195, #196).
2. STORM rename wave, platform half (`plan/storm-rename-recut` `dfe7cc6a`, 71 build handoffs; S0a
   needs `scripts/dev/storm_inventory.py`).
3. H-1 Wave B platform splits (P0, P11a, P10 `api/jobs/` 37 slices, P5, P4, P7, P8, P2, P3, P1, P6).
4. GEN-API 1f real-host rows (owner run; build MERGED #153, default OFF).
5. Phase 1 platform waves P-1 to P-6: F30 P1b, B-10 S1c, H-1 P0; B-10 S2a, F30 repin, F35 P0; B-10
   S2b and S3, F30 P2a, P2b, D1; F34 P0 to P3, H-1 P11a; F32 platform slices, F29 P1 and P2, F35 P1a
   onward. With PUB-REC, POLICY, the platform halves of DELIV and SAMPLE, the B-6 platform consumer
   slice (changes `_persist_job_vault` at the B-6 repin) and the scheduler finish-and-activate plan
   (`plan/scheduler-state-and-direction` `4fff389e`; never delete the dormant S3A, S3B, cgroup, lease
   and S13 to S17 code).
6. Phase 2 platform: F14, F13 slice 3a, the F24 reservation model and the B-10 estimate API route,
   F23 platform resume, F36-P.
7. Phase 3 platform: F45 (claim-time re-authorization, SAML, MFA), the F44 platform half (air-gapped
   bundle, container digests, G13, G18), the F01 and F02 platform surfaces.

| Item | Feature | State | Next |
|---|---|---|---|
| WF-R backend: remove workflow models, FKs, DDL, routes, runner, run gate, schedule fields and tests in one migration; replaces X10b | baseline | NOT STARTED | before X1d2 and X1e2 |
| OUT-PATH: non-admin outputs API returns absolute `output_path` (`api/jobs/routes_outputs.py:124,186`); return opaque ids | F45 | NOT STARTED (live bug, not exposed) | on restart |
| CI-P1, CI-P2, CI-P3: self-hosted backend lanes, Postgres test markers, nightly | CI | NOT STARTED | after X0a-h H2 and H4 |
| PUB-REC: per-table publication record on the full-frame route | F22 interim | NOT STARTED | Phase 1, early |
| DELIV platform half (database "deliver nothing" is a staging schema swap, Q11) | F22, F34, F35 | NOT STARTED | after CLI delivery |
| SAMPLE platform half (web wiring is design input D3) | F04 | NOT STARTED | after SUB-RUN |
| POLICY: per-job retry and low-memory route; retry from scratch after a crash (Q21) | F23, F27 | NOT STARTED | owner call Q21 |
| Re-enable pre-scans: flip `STORM_EXECUTION_DISABLED` in `api/jobs/release_gates.py` (off since 2026-08-27) | F15 | NOT STARTED | after X10a and the STORM platform half |
| SCAN-MULTI platform half (Q25) | F15 | NOT STARTED | with re-enabled pre-scans |
| F21 Studio parity backend: slices 1, 1b, 3a, 5 MERGED (#150, #170, #146, #160); layout store unification and `geo_generalize` UI remain | F21 | plan `plan/f21-studio-parity-backend` `77906360` | on restart |
| F14 wrapping-key rotation (crypto tier): `MultiFernet` with `key_version`, rewrap across all custody targets, SMTP password wrapped (G14), fail closed on a missing key (G23) | F14 | NOT STARTED | Phase 2 |
| F45 finish: claim-time re-authorization (the one item the spec forbids omitting), SAML, MFA; SMTP password encrypted, auth cookie `Secure`; login limit, password policy, CORS (G15); single-process guard (G17) | F45 | NOT STARTED | Phase 3 |
| B-10 estimator S1b onward and an API route for the estimate | F24 | S0, S1m, S1a, S1b MERGED | wave P-2 |

**Live platform bugs recorded for the restart** (not exposed; the platform is unreleased): SSO can
resolve to the wrong account and does not bind the issuer (X3a fixes it); OUT-PATH.

**Also parked:** X4a part B and X4b call-site conversion; the approved git history scrub of business
docs (run at a quiet point, never mid-stack); the V1 role set (user PATCH accepts only admin or user);
the `sso` license gate is defined but not enforced; the dev license key defaults to the business tier;
flaky tests on platform main (V2 backlog); UX map Q19, Q21, Q25; X0a-h H3 and H5. Platform main
known failures live in the stored baseline `baselines/decoy-platform-main.json` in the vault.

---

## 7. Phase principles (the acceptance lens)

The phases follow the MASTER delivery sequence. Read the phase pillars before an item's MASTER Fxx
contract at FRAME. If an item cannot meet its phase's pillars, that is a FRAME signal: the item is
mis-scoped, or the pillar needs a recorded exception.

**Phase 0, close the open branches (CLOSED 2026-11-04).** Finish, don't expand; respect the gate
chain; lockstep what is coupled; keep main bootable; every branch names its Fxx; security blockers
lead.

**Phase 1, trustworthy local run.** A local run is safe (no secret or canary leak on any surface),
honest (signed evidence, stable reason codes, nothing published on an inconclusive result), bounded
(every spool and temp file answers to a quota) and reproducible (atomic, idempotent publication).
Pillars: one sanitizing boundary, not per-surface patches (F31 first); validation never mutates and
evidence is frozen; bounded by default; machine-readable and versioned (one reason registry, stable
exit codes); fail closed on uncertainty; the engine owns the contract and the CLI and platform consume
it.

**Phase 2, portable and repeatable.** The same pipeline gives equivalent results across machines,
engine versions and time. Pillars: portable artifacts over implicit state; explicit drift, never a
silent change; immutable, versioned objects; no version flip without the determinism gate and the
synthetic probe; a reduced scope is a drawn line, not a weakened contract; resume with an unchanged
plan.

**Phase 3, connected safe-copy and enterprise readiness.** Pillars: depth before breadth (one complete
PostgreSQL round trip before more connectors); re-authorize at the point of execution; a connected
target keeps every Phase 1 guarantee; signed, attested distribution; recoverable upgrades; enterprise
breadth only when a customer pulls.

---

## 8. V1 completion gates

**R1 = CLI V1** (engine, CLI and marketing web). The release work is rows 89 to 94.

- **D-4** Freeze a DP-certified launch engine (Faker 40.23.0) and the matched CLI pin. Version
  agreement done (R-a, R-b; static `version` with hatchling). Open: CLI `__version__` literal
  `"0.1.0"`; wide engine dependency floors (G12, F10). Branch `E:fix/faker-40-31-migration`
  (`e68b66c1`, replay by patch after R1).
- **B-3** Marketing-web currency: `docs-src/` off STORM branding and the old command surface;
  `CLAIMS-AUDIT.md` complete; `/proof` synced to the catalog.
- **D-5** Public Fumadocs launch-gate flip, aligned to BUSL at launch.
- **GA-confidentiality freeze (audit packets 11 to 20):** 11.1 and the 12.1 residue land before the
  pre-GA to GA flip (rows 11, 13). 12.2 is closed on the full-frame path; chunked and native paths were
  read, not run. 20.1 is overstated (section 9).
- **R1-c** signing key and CLI license values (owner and counsel); needed for the first signed
  release, not before. Licenses differ per repo today: engine Apache-2.0, CLI `pyproject.toml`
  BUSL-1.1, platform `LICENSE-COMMERCIAL.md`, decoy-web no LICENSE file.
- **R1 gate:** canonical CLI release smoke with recorded runs (G3: `smoke-log.md` had no green runs);
  a filled `release-readiness.md` instance; claims and license checkpoint; docs honesty; local gates
  and the worker-bootstrap gates (R1-d).
- Review item (not adopted): a threat model for the CLI installer and upgrade boundary and the local
  token vault.

**R2 = Platform V1** (parked).

- PREGA-AU automatic-update and recovery run.
- Section AUDIT at a frozen commit and a filled release-readiness instance green on the local gates;
  define AUDIT as a `dev-rules/pre-release-audit.md` instance with SAST, secret scan, dependency audit
  and tool versions recorded (G19, G21, not adopted).
- Dependency hygiene: python-jose replaced (#136); NOTICE and license gates (#137, engine #362); CLI
  root NOTICE (part of REL-PKG); `known-open-vulns.md` and `TRIAGE-001` (G18, not adopted).
- Security ledger at 0 gaps; closes packets 11 to 20 R2 findings 12.3, 11.8, 13.2, 13.7, 17.2, 17.3.
- Validation (not features): B-11 prodsim rebuild and the A-2 100M-row characterization (no 100M run;
  extrapolate from 1M and 10M).
- Market-positioning review against the shipped surface; Go or No-Go.

---

## 9. Review notes and the findings register

Rule: fixes ride features. A review finding becomes an acceptance criterion only for a wrong-value
bug, a confidentiality bug or an R1 blocker; everything else is listed here with no dispatch order.

**Hardening notes.** 20.1 ML-pack "fail-open" is overstated: `load_with_fallback`
(`profiling/model_pack/loader.py:151-166`) falls back to the regex baseline, untrusted packs need a
verifiable signature before `joblib.load`, and `trusted=True` applies only to the wheel-shipped default
pack, whose digest is self-attested. 12.2 is closed on the full-frame path only.

**After V1.** No login rate limit or lockout and no password policy (F45). CLI `scan` uses
`pd.read_fwf`; divergence from the engine reader is untested (H-1 G5). Native-kernel fallback
telemetry beyond a warning; GCS and S3 conditional writes; SFTP fingerprint pinning; the
data_discovery keyword denylist; multi-process API support.

**Findings register** (from the archived 2026-10-30 reconciliation and its review; "FRAME finding"
means unverified until that item's FRAME):

| Finding | Summary | Home | State |
|---|---|---|---|
| G1 | CLI `resolve_substrate` ImportError | R1-a | CLOSED (CLI #71) |
| G2 | Four engine version truths; CLI `--version` literal | D-4 | engine CLOSED; CLI literal OPEN |
| G3 | No recorded smoke runs; release docs are templates | R1 gate | OPEN |
| G4 | CLI chunked output bypasses `TransactionalSink` | CLI delivery | verified by reading 2026-10-30 |
| G5 | CLI scan parses fixed width with `pd.read_fwf` | H-1 FRAME; after V1 | verified by reading |
| G6 | Plaintext spill under three temp roots | F25, F26 FRAME | UNVERIFIED |
| G7 | Cloud sources read the whole object into RAM | F25 FRAME | UNVERIFIED |
| G8 | Post-mask leak helper fails open | F34 FRAME | UNVERIFIED |
| G9 | CLI token vault cleartext, unauthenticated (11.8) | F09 FRAME; R2 11.8 | UNVERIFIED |
| G10 | License placeholders; per-repo licenses | R1-c | OPEN |
| G11 | Native kernels fall back silently | F29 FRAME (if free) | UNVERIFIED |
| G12 | Engine dependency floors too wide | F10 FRAME; D-4 | UNVERIFIED |
| G13 | Startup DDL beside Alembic in production | F44 platform FRAME | UNVERIFIED |
| G14 | SMTP password in plaintext | F45 criterion; F14 FRAME | verified by reading |
| G15 | No login limit or password policy, cookie without `Secure`, wide CORS | F45 | `Secure` verified; rest UNVERIFIED |
| G16 | Graceful shutdown mismatch in the inline topology | F23 FRAME | UNVERIFIED |
| G17 | Single-process state unenforced | F45 FRAME | UNVERIFIED |
| G18 | Python 3.10 image, no platform lockfile, python-jose | F44 platform; R2 | jose CLOSED (#136); rest OPEN |
| G19 | Security scanning has no local equivalent | R2 AUDIT | OPEN |
| G20 | Local ci-mirror is prose | R1 gate | CLOSED (platform #156) |
| G21 | AUDIT undefined; packets 11 to 20 not on disk | R2 AUDIT | packets CLOSED (#125); definition OPEN |
| G22 | Passport signing key outside the backup set | F33, F14 FRAME | UNVERIFIED |
| G23 | Silent key generation when a key is missing | F14 FRAME | UNVERIFIED |
| G24 | Small platform items (SSO fetch, pool timeouts, body cap, forwarded IPs, `/health`, scheduler package) | F45 FRAME (if free) | UNVERIFIED; scheduler deletion not taken |
| D-row 1 to 2 | F29 engine half and F43 already merged | F29, F43 | CLOSED (#336, CLI #69) |
| D-row 3 | `pk_uniqueness` exists, not catalog-level or OOC safe | F36 | as stated |
| D-row 4 | F23 engine half is NEW | F23 FRAME | UNVERIFIED |
| D-row 5 to 6 | Engine pins disagree; 12.2 likely closed | D-4; notes | CLOSED; full-frame only |
| D-row 7 | Shipped log stale (gap 2026-10-27 to 2026-10-30) | process | OPEN |
| Slice 0 | 14.1 closed (#360); cross-column read handled by `order_work`; 11.1 + 12.3 and 12.1 rows 11, 13; 20.1 overstated | slice 0 | as stated |

---

## 10. V1 feature checklist (29 Council-V1 features)

V1 = the 29 Council-V1 features (20 full, 9 reduced `V1*`) from the LLM Council scope doc (owner's
notes); contracts in the MASTER feature specification (owner's notes). Status is from the 2026-10-27
code audit; "merged" means a slice landed, not that the contract is met. Engine and CLI halves run in
the CLI V1 track; platform halves are parked.

| Fxx | Feature | Council | Status | Repos | Phase | Shipped groundwork |
|---|---|---|---|---|---|---|
| F01 | Connected DB copies and app-ready targets | V1 | PARTIAL | E+P | 3 | PG snapshot read |
| F02 | Cloud object storage and SFTP | V1* | PARTIAL | E+C+P | 3 | S3 and GCS |
| F04 | Referential subset and mask in one run | V1 | PARTIAL | E+C+P | 0 to 1 | engine subset; explicit keys (#366) |
| F06 | Declared parsing, casting, quarantine | V1 | PARTIAL | E | 1 | MERGED (#338) |
| F07 | Path-aware nested data | V1* | PARTIAL | E | 2 | nested masking strategy |
| F09 | Cross-job identity domains and vault | V1* | PARTIAL | E+C+P | 0 to 2 | B-6 stages 1 and 2; CLI vault (#64) |
| F10 | Version locks and fleet inventory | V1 | PARTIAL | E+C | 2 | fingerprints; `api/golden/` |
| F13 | Secret providers and preflight | V1 | PARTIAL | E+C+P | 1 to 2 | #339; CLI #78 |
| F14 | Platform wrapping-key rotation | V1 | PARTIAL(thin) | P | 2 | B-6 vault-key half |
| F15 | Continuous discovery and drift | V1 | PARTIAL | E+C+P | 2 | scan loop; schema contract |
| F16 | Reusable policy and selectors | V1 | PARTIAL(thin) | E+C+P | 2 | disguises |
| F21 | Studio parity | V1* | PARTIAL(near) | P | 1 | slices 1, 1b, 3a, 5 |
| F22 | Atomic and idempotent publication | V1 | PARTIAL(near) | E | 1 | atomic publish golden-tested |
| F23 | Recoverable execution and checkpoints | V1 | PARTIAL(near) (engine NEW) | E+C+P | 2 | platform leases and fencing |
| F24 | Capacity estimation and admission | V1* | PARTIAL | E+P | 0 to 2 | estimator (#328); B-10 S0 to S1b |
| F25 | Protected scratch and orphan recovery | V1 | PARTIAL | E | 1 | spill budget and memory caps |
| F26 | Upload, output, staging retention | V1* | PARTIAL | E+C+P | 1 | PRs parked |
| F29 | Machine-readable errors and progress | V1 | PARTIAL | E+C+P | 1 | #336; #367 |
| F30 | Customer-controlled telemetry | V1* | PARTIAL(thin) | E+C+P | 1 | CLI #80; #369; P1a #158 |
| F31 | Shared safe-output and redaction | V1 | PARTIAL | E+C+P | 1 | #368; #377 |
| F32 | Safe support bundles and reproduction | V1 | NEW | E+C+P | 1 | E1 in gate |
| F33 | Signed evidence and offline verify | V1 | PARTIAL(near) | E+C+P | 1 | evidence; `api/passport/` |
| F34 | Residual canary detection (span) | V1 | PARTIAL | E | 1 | #365, #370, #371 |
| F35 | User-defined quality contracts | V1 | PARTIAL | E+P | 1 | B-9 measurement |
| F36 | Cross-column invariants and fidelity | V1 | PARTIAL | E | 1 | `pk_uniqueness` |
| F43 | CI checks, annotations, hooks | V1* | PARTIAL (merged; remainder recorded) | C | 1 | CLI #69 |
| F44 | Signed distribution and upgrade | V1 | PARTIAL | E+C+P | 0 to 3 | B-2; SBOM (#355, #75) |
| F45 | Authorization and enterprise readiness | V1 | PARTIAL | E+P | 0 to 3 | A-4 (#361); B-5 (#157) |
| H-1 | Code organization (tandem) | V1 | NEW | E+C+P | 1 | Wave A; E0 stack; E5; E3 |

F04's remaining contract (no standalone unmasked subset artifact; platform materialization) rides
F22, F25 and SUB-RUN.

Legacy items: A-4 and B-5 become F45; A-5 is the STORM rename; A-7 and D2 merged; A-8, B-6 and B-1
become F09 and F14; B-2 becomes F44; B-9 becomes F35 and F36; B-10 becomes F24; route-coverage phase 2
is post-V1; GEN-API go-live merged (#153); B-11 and A-2 are R2 validation; B-12 scheduler is F27
(council V2) with the scheduler code finished and activated; D-1 to D-5 are shipped or R1 gates.

---

## 11. Owner decisions (dated)

- **2026-11-05 (this move).** CLI V1 complete, then platform; the roadmap moves to the CLI repo and
  the platform links to it. Develop correctly: central registries for cross-cutting concerns and
  correctly sized files and directories (section 4). Registry slices may build in parallel with
  REG-RENUMBER renumbering at merge. Engine releases every 2 to 3 days with a cumulative CLI repin.
  A Windows self-hosted runner on GCP is approved spend. Platform: Group 1 merges, the rest is
  parked.
- **2026-11-05 (X0a-h off the V1 path).** Platform H1, H2, H4 and H6 stay parked, and the engine
  and CLI ports (E1, E2, C1, C2) leave the CLI V1 path. Meanwhile the orchestrator flags any ratchet
  baseline growth by hand at each gate. Re-entry trigger: a hidden exception slips past review, or the
  platform restarts.
- **2026-11-05 (CLI 1.0 scope).** CLI 1.0 is everything on the CLI V1 track; no early 1.0 cut with
  later phases as 1.x.
- **2026-11-05 (detector role floor).** Developers can manage detector settings (custom detectors
  and overrides). The code already gates those routes at `developer`
  (`P:api/storm/detectors_router.py`, `storm.override`, `min_role="developer"`) and does not change.
  This supersedes the 2026-11-03 "STORM detector mutations stay admin-only" wording; docs that said
  admin-only are corrected. New V2 row: detection settings profiles (section 13).
- **2026-11-05 late night (OQ-1 to OQ-4).** OQ-1 = A1: X0a-h H1, H2, H4 are shared gate tooling on
  the finish-out list (now parked; see the X0a-h entry above). OQ-2 = B1: re-cut the STORM CLI half; CLI V1 ships the
  new names. OQ-3 = C1: SUB-STOP 1.6.0, STORM E1 1.7.0, then build order. OQ-4: Windows "would be
  ideal if possible" (WIN-FEAS). SAMPLE confirmed CLI V1. The starter YAML defaults columns with no PII
  to `redact`. LIB rows added before SCAN-MULTI; SCAN-MULTI S1d becomes LIB L2.
- **2026-11-05 night (scan and checks model).** Two kinds of integrity run through both scans: data
  integrity and distribution integrity ("2 different things but both incorporated in pre/post
  scans"). Standard: strict delivery; post-scan integrity on every route; output PK and FK checks
  when keys are declared; every validate check before a run. Opt-in: drift, distribution integrity,
  user rules and contracts (F35, F36), NER. Explicit config (CONFIG-EXPLICIT). `decoy scan` stores a
  versioned snapshot in a local library, referenced by the YAML and hashed into evidence.
- **2026-11-05 (CLI V1 scope).** SCAN-MULTI is CLI V1: "a decoy scan should be able to scan multiple
  files at once in order to build the single YAML for the pipeline." FK discovery parked for V2:
  "users can set up their own FKs, but we do want multi-file discovery at once. 1 scan for 1 pipeline
  build, on however many tables the user selects". CLI-CLOUD assumed CLI V1.
- **2026-11-05 (release order).** CLI V1 first, platform after (quotes in section 1). Supersedes the
  2026-10-22 "CLI-LAUNCH after V1" order and the 2026-11-04 sequence. UX map round 2: Q22 strict
  delivery and Q24 sample block CLI V1 for their CLI halves; OUT-PATH (Q23) is a platform row.
- **2026-11-05 (UX map section 8 adopted).** "Section 8, proposed roadmap changes, let's update our
  roadmap now." Workflows retired (X10b becomes WF-R). Stage then deliver, strict and best-effort.
  Sample output through the subset. "Studio" is the platform web UI, a prototype owned by a separate
  frontend developer. The CLI does not self-orchestrate; the platform applies per-job policy (form
  pending Q21).
- **2026-11-04.** Phase 0.5 cross-cutting foundations before the STORM wave; R1-c to the pre-release
  list; H-1 Wave B completes before Phase 1, after the STORM rename; GEN-API real-host rows after the
  STORM wave; reviews stay org-wide; the self-hosted CI runner may use the Mac; no OpenRouter gates.
- **2026-11-03.** B-5 job vault write: option A (#152's path-based persist kept behind a platform
  output handle); the `bounded_child.py` annotation not approved. Registry chain order F34 E0 1.3.0,
  F06 1.4.0, F31 E0c 1.5.0, then STORM E1, F35 E1a, F32 E1b, F36 slice 4. Merge B-5 without polish.
  V2 audit after V1 from the V2 log. Phases 1 to 3 are hardening. F06 after B-6 lifted. Role floors:
  users are developers; everyone except a viewer builds and runs pipelines including formulas. (The
  2026-11-03 "STORM detector mutations stay admin-only" wording is superseded by the 2026-11-05
  detector role floor.) Docs audit applied (platform #161, #162). The Mac mini is a test
  node; stacked PRs get one full suite on the stack top.
- **2026-11-02 night.** STORM Q8 refuse `variable.unknown_scope`; Q9 (a) keep the W0 forward shims;
  Q11 version A (E1 rides R-c). B-5 161 DEFER rows approved. F33 Q16 False; E1b waiver. F36-P planning
  after Phase 0. F32 re-cut accepted. Engine release order: F34 first. F31 CUT the alias, legend and
  run-UUID stack.
- **2026-11-02.** F31 O1 to O3 (see 5.4). Stale STORM rename branches re-cut from main. B-6
  existing-vault compatibility is a hard cut; the CLI refuses to overwrite an existing vault. The
  dormant scheduler code is finished and activated, never deleted. DuckDB opportunities added to V2.
- **2026-10-31.** Pre-release, no backwards compatibility; no migration for seed-keyed vaults; two
  engine releases (R-a, R-b); R1-c key generated offline by the owner; SBOM tool CycloneDX; CLI
  `claude/enterprise-hardening` parked.
- **2026-10-30.** V1 threat model: self-hosted, single org, engine process trusted; in scope are
  accidental leaks of values or paths into exceptions, logs, reprs, results and reports; hostile
  in-process hardening is V2. Slice 0 before F31. F25 before F22. F13 preflight stays in Phase 1.
  Secret retention in `KeyboardInterrupt(secret)` args is a V2 note.
- **2026-10-29.** STORM concept reframe. GEN-API 1f ships default OFF with per-deployment opt-in.

Full text of the 2026-10-30 to 2026-11-03 decisions: `OWNER-DECISIONS-2026-10-30.md` in the vault
handoffs folder (mirrored on platform `handoffs/queue`).

---

## 12. Branch register (engine and CLI)

Every open row names its branch. A remote branch neither merged nor named here has no owner on record
and is a cleanup candidate (`~/bin/branch-analysis`).

| Branch | What it holds | Disposition |
|---|---|---|
| engine PR #333 `claude/sharp-goodall-ikag71` | superseded A-4 draft | per-branch check, then delete |
| engine `feat/file-access-policy`, `feat/file-access-integrated-wip`, `feat/file-access-sink-coverage`, `claude/laughing-galileo-h18woa` | superseded A-4 work | cleanup candidates |
| engine `claude/youthful-ride-0azacx` (`e780df30`) | earlier copy of the native-release workflow | compare with #353, then retire |
| engine and platform `claude/v2-warehouse-sources-and-tokenization-vault` | warehouse connectors (home F01, F02) | FOLD; HIGH lost-work risk |
| engine `fix/faker-40-31-migration` (`e68b66c1`) | mimesis rebinding regression tests; no merge base | replay by patch after R1 (D-4) |
| engine `feat/b6-batch-vault-writer-engine` (`e3c539d6`) | B-6 batch vault writer | owner: fold into the B-6 core chain or retire |
| engine `feat/f13-e1-file-secret-permissions` (`37f43e47`) | shipped inside A-4 | retire |
| engine `plan/b6-vault-crypto-remediation` (`91488afb`) | B-6 crypto plan | retire after B-6 core merges |
| engine `plan/cdf-exact-arithmetic` (`f89f4ab7`) | built as #363 | retire |
| engine `plan/slice0` (`3a49b782`) | slice 0 plans | retire after slice 0 merges |
| engine `plan/route-coverage-ph2` (`864c2352`), `claude/optimistic-feynman-m5cfy5` (`2086fc73`), `claude/blissful-goldberg-mkwpdk` (`e1f96acb`) | route-coverage phase 2 (post-V1; Codex GO-WITH-FIXES with 5 HIGH) | keep; `blissful-goldberg` HIGH lost-work risk, do not delete |
| CLI `claude/eager-clarke-14deh1` (`d697c6d8`) | stale STORM rename | retire after the STORM CLI half |
| CLI `claude/storm-split-cli` (`a677d509`) | STORM CLI split | owner: compare with the re-cut CLI slices |
| CLI `claude/vibrant-feynman-1khw1v` (`8fa00fb2`) | CLI pre-scan and post-scan work | owner: compare with the re-cut CLI slices |
| CLI `feat/f26-local-cleanup`, PR #68 | F26 CLI half | parked until F22 |
| CLI `plan/f43-ci-integration` | F43 plan; built as #69 | retire |

Platform branches are in the platform pause record.

---

## 13. Out of V1 scope

The 21 Council-V2 features, built when a customer pulls: F03 file unions, F05 fixed-width streaming,
F08 coherent free-text identity binding, F11 output ordering and byte reproducibility, F12 customer
regression suites, F17 portable disguise bundles, F18 config composition, F19 semantic diff and repair,
F20 config migration, F27 governed schedules (owner may pull), F28 local execution node, F37 post-mask
privacy risk (k-anonymity and QI already ship in `decoy scan`), F38 metadata preserve and redact, F39
OpenLineage export, F40 plugin SDK, F41 expression evaluator preview, F42 Unix streams, F46 QA
scenarios, F47 healthcare packs, F48 statistical synthesis, F49 clone-system handoff, F50 native
masking-policy export. Detail: `P:docs/backlog/v2-candidate-plan.md`.

| V2 row | What | Source |
|---|---|---|
| DETECT-PROFILES | Detection settings profiles: named sets of detection settings (detectors, overrides, thresholds, ML on or off) that a pipeline picks by name | owner, 2026-11-05 |

Post-V1 on demand: route-coverage phase 2 (OOC address faker, FPE FK key, resident escape hatch, OOC
quarantine); the CLI init wizard (spec CLI #73); value-based FK discovery (SCAN-MULTI plan section 7);
chunk-level resume; a user-level library store (LIB Q7).

V2 corrective backlog and audit: vault `handoffs/V2-CORRECTIVE-BACKLOG.md`. DuckDB opportunities:
vault `v2/duckdb/` and platform `plan/v2-duckdb-plans` (`1c8eba8d`); proposals, not scheduled.

---

## 14. Shipped log

[`RECENTLY-SHIPPED.md`](RECENTLY-SHIPPED.md) in this folder. It moved here with the roadmap
(copied from `P:docs/backlog/RECENTLY-SHIPPED.md`). When a slice merges, add it there and update its
row here in the same change.

---

## 15. Source documents

- V1 pipeline baseline: `P:docs/product/v1-pipeline-baseline.md`
- V1 UX map (owner questions Q1 to Q25, section 8 rows): `P:docs/product/v1-ux-map.md` (branch
  `docs/v1-ux-map`)
- Platform pause: `P:docs/PARKED.md` and vault `platform-pause-2026-11-05.md`
- Roadmap history: `P:docs/archive/roadmap-status-snapshots/`
- Plans: `C:docs/plans/` (CLI), `E:docs/plans/` (engine), `P:docs/plans/` (platform and cross-repo)
- Handoffs and launch board: vault `handoffs/phase0.5/LAUNCH-BOARD.md`; H-1 tracker
  `handoffs/phase1/h1/H1-TRACKER.md`; Phase 1 tracks `handoffs/phase1/PHASE1-TRACKS.md`
- Gate ledger: vault `gate-ledger.tsv`
- Feature contracts and council scope: MASTER feature specification and the LLM Council V1 and V2
  scope (owner's notes)
- Governing process: `~/dev-rules/development-loop.md`, `~/dev-rules/risk-and-exceptions.md`,
  `~/dev-rules/cross-cutting-concerns.md`, `~/dev-rules/testing.md`
