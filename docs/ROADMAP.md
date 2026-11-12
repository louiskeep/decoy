# Decoy Roadmap: CLI V1 first, then Platform V1

Status: plan

This is the one Decoy roadmap for all four repos (engine, CLI, platform, web). It moved here from
`decoy-platform/docs/ROADMAP.md` on 2026-11-05 because the CLI is now the main development point.
Owner (Cam, 2026-11-05): "New goal is Decoy CLI V1 complete, then we can return to platform. Move
roadmap over to decoy CLI since that's the main development point, link it from platform."

Built from the platform roadmap at branch `docs/roadmap-v1-ux-map` head `0d484f7f` (Codex GO at
`23c3ca13`; the later commits there are owner answers and rows). That text is kept whole in the
platform repo at `docs/archive/roadmap-status-snapshots/2026-11-05-platform-roadmap-before-move.md`.
That snapshot lands on platform main from branch `docs/roadmap-pointer`. Earlier history: platform
`docs/archive/roadmap-status-snapshots/` (the 2026-11-03 consolidation
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
baseline, never a second main run. Slices that need a full suite may ride a merge train (owner
2026-11-10, `~/dev-rules/profiles/local-operations.md`): reviewed heads merge into one batch branch
2 or 3 times a day, the suite runs once on the batch head, then each PR merges in order. Gates run locally and on self-hosted runners; hosted GitHub CI
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
| CLI target writers and readers | writers in `C:src/decoy/cli/io/_targets.py`, readers in `C:src/decoy/cli/_sources.py` (`read_file`) | `C:tests/sentry/io_policy/test_target_writes.py` (G-ONE-TARGET-WRITE) and the widened G-ONE-CSV-READ | CLI-FMT A, A2, B (merged #101 to #103) |
| Local record library writes | one library writer (LIB L1b; the shared atomic writer `C:src/decoy/_atomic.py` merged in #85) | `C:tests/sentry/test_atomic_writer.py` (G-ONE-ATOMIC-WRITER) | LIB rows |
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

### 5.1 Main tips (re-read from origin: engine and CLI 2026-11-11, platform 2026-11-07)

| Repo | Tip | Recent merges | Pin and registry |
|---|---|---|---|
| decoy-engine | `c96e2855` (#487) | #487 F13 slice 5-v1 consumers docs, #486 main-gate tree proof, #485 F22 plan rev 11, #484 layer test kept out of shards, #483 LAYOUT plan marked built, #480 LAYOUT E3, #478 GEN-STRICT D, #479 LAYOUT E2, #477 GEN-TYPES E2, #474 and #473 parity test fixes, #476 pytest-timeout, #475 fileaccess bound-iterator fix, #471 CONFIG-EXPLICIT E2c, #472 release 0.22.0, #467 GEN-TYPES E1, #470 FK-FANOUT D docs, #469 GEN-COND-CAP cap export, #465 GEN-STRICT E2, #468 whole-frame profiling speed, #464 GEN-UNIQUE D1 guide, #463 gate selector always runs output-pinning tests, #466 release 0.21.0, #461 GEN-COND-CAP E1b, #459 RUN-STREAM E3, #462 main test fix after #460, #460 GEN-CLI E1, #458 GEN-NUM-SHAPE, #456 GEN-COND-CAP E1, #457 release 0.20.0, #455 FID-RANGE docs, #454 FID-RANGE, #445 GEN-C2, #442 RUN-STREAM E1b, #444 LIB L1a, #448 FK-FANOUT E2a, #453 DI docs, #452 FK-FANOUT E2b, #450 REG-RELEASE E1, #441 CONFIG-EXPLICIT E2a, #446 GEN-UNIQUE E2, #447 SIZE-CEIL, #451 and #449 main test fixes, #439 RUN-STREAM E1a, #443 fast push check and sharded gate on dispatch, #438 GEN-FIT-SHAPE E3, #440 GEN-UNIQUE E1, #437 RUN-STREAM E2; #403 to #436 are in the shipped log | latest tag `v0.22.0` (`98670941`, #472); `REGISTRY_VERSION` 1.22.0 on main (#456) |
| decoy (CLI) | `ac0cb686` (#204) | #204 F13 slice 5-v1 vault:// refusal test, #200 PROJECT-LAYOUT P3, #203 roadmap text, #202 roadmap text, #199 LAYOUT C3, #197 PROJECT-LAYOUT link fix, #196 LAYOUT C2, #195 VALUE-FREE-ERRORS B2, #194 roadmap text, #193 PROJECT-LAYOUT P2b, #192 QA-FK-FANOUT C1, #191 roadmap text, #190 GEN-STRICT C2, #189 GEN-CLI C3, #188 GEN-STRICT C1, #186 GEN-COND-CAP C1, #182 GEN-CLI C2, #185 pytest-timeout, #184 repin to engine 0.22.0, #183 LAYOUT C1, #180 PROJECT-LAYOUT P1b, #181 CLI-QA1 C1, #179 RUN-SPLIT, #178 roadmap text, #175 FIT-ROWS, #173 GEN-FIT-SHAPE C1, #176 GEN-UNIQUE C1, #177 QA-SCAN-REDACT slice C, #174 GEN-CLI C1, #172 QA-DP-GATED CLI, #171 QA-FIT-REDACT CLI, #170 roadmap text, #169 repin to engine 0.21.0, #168 roadmap text, #166 SCAN-MULTI S1c.1, #167 roadmap text, #165 RUN-STREAM C3, #164 repin to engine 0.20.0; #108 to #163 are in the shipped log and git log | `decoy-engine==0.22.0` (#184, `990199ef`) |
| decoy-platform | `fbaee2a9` | parked (see section 6) | `decoy-engine==0.18.0` (#149) |

### 5.2 Sequencing rules

1. **Reason registry chain.** SUB-STOP takes 1.6.0, STORM E1 takes 1.7.0, then every other
   registry-touching row takes the next free minor in merge order (owner OQ-3 = C1, 2026-11-05).
   Once REG-RENUMBER merges, registry slices may build in parallel; they still merge one at a time,
   and the tool renumbers each slice to `main + 1` at merge (owner, 2026-11-05). Until it merges, the
   chain is strictly serial by build order (owner rule, 2026-11-03).
2. **One writer per hot module** (takes effect when RUN-SPLIT, row 95, merges; until then one
   branch at a time writes `C:src/decoy/cli/run.py`, and the run.py rows are CLI-DIALECT, CLI-FMT
   A, VALIDATE-ALWAYS, SUB-RUN CLI half, CLI delivery, RESULT, SAMPLE, LIB L3a, L3b, L5a, L5b, F23
   resume, F29 C1, F30 C1b). `decoy run` lives in `C:src/decoy/cli/run/`. One branch at a time
   writes each module there; two rows that write different modules build in parallel.
   `__init__.py` (the options) is shared: a row adds its option as one additive hunk and rebases at
   merge, and a row that changes an existing option takes the module like any other. Rows and the
   modules they write:
   - SUB-RUN CLI half: `_prepare.py`, `_execute.py`, plus an option.
   - CLI delivery: `_execute.py` (stage then deliver, the chunked path through the same sink).
   - RESULT: `_errors.py` (exit 6, capacity widening), `_render.py` (the run result summary).
   - SAMPLE: `_execute.py` (`--sample` through the subset, output to scratch), plus an option.
   - LIB L3a: `_evidence.py` (evidence and run-result records).
   - LIB L3b: `_flow.py` (scratch lifecycle), `_evidence.py` (sample-run records).
   - LIB L5a: `_execute.py` (the `ProgressSink` on `run_pipeline`), `_flow.py` (the spinner).
   - LIB L5b: `_flow.py`, `_notify.py` (job logs).
   - F23 resume: `_execute.py` (table-level resume), plus `--resume`.
   - F29 C1: `_errors.py`, `_render.py` (error and progress consumers).
   - F30 C1b: `_notify.py` (spans and the exit flush on `_otel`), `_flow.py`.
   - Done and out of the lane: CLI-DIALECT, CLI-FMT A, VALIDATE-ALWAYS.

   Hot pairs: `_execute.py` (SUB-RUN, CLI delivery, SAMPLE, L5a, F23) and `_flow.py` (L3b, L5a,
   L5b, F30 C1b) stay single-writer. One branch at a time writes `C:src/decoy/cli/scan.py`: SCAN-MULTI
   S1c and S3-cli, LIB L2, L5b, H-1 C3, STORM CLI half. CLI-CLOUD's plan must say whether it
   enters the `run.py` lane (after RUN-SPLIT: which `run/` modules it writes). The plan for each
   row names its modules; the module list above is the RUN-SPLIT plan's reading of the row titles.
3. **Engine releases.** One release and one CLI repin open at a time. A CLI half that needs new
   engine code waits for the release and the repin (engine repin checklist: compatibility, fences,
   frozen surfaces, docs, `PIN_PREFIX`, the Dockerfile `ARG`, the catalog).
4. **Release cadence.** Cut an engine release from main every day while engine rows are merging
   (owner, daily engine release train D4, 2026-11-09), carrying whatever has merged (owner may release without per-release confirmation). The
   CLI repins once per release, cumulatively: one repin carries every engine change since the last.
   Named releases below (R-c, R-d) list what each must contain at minimum; the cadence decides when.
5. **LIB.** L1a-engine, then an engine release and the CLI repin, then L1b, then L1c. L2, L3a, L3b,
   L4a, L4b, L5a and L5b follow L1c and their feature rows, in parallel on files that do not
   overlap.
6. **SCAN-MULTI.** S1a and S1b ship in one engine release. CLI-DIALECT lands before S1c, and S1c
   before LIB L2 (L2 replaces the plan's S1d). CONFIG-EXPLICIT lands before S3-engine; S3-engine is
   released, then S3-cli.
7. **CLI-FMT.** DONE 2026-11-07: A, A2 and B merged in order (#101 to #103) after one T3 on B's head.
   ATOMIC-OUTPUT (row 21b) DONE 2026-11-07 (#105).
8. **Publication chain.** F25 before F22 (owner, 2026-10-30); F22 and POSTSCAN-STREAM before CLI
   delivery; SUB-STOP before SUB-RUN; SUB-RUN before SAMPLE; F22 and CLI delivery before F23 resume.
9. **H-1** slices move only files no live branch touches, behavior-preserving, characterization
   tests first.
10. **Close partly merged rows first** (owner, 2026-11-10). A row whose engine half is merged gets
    its CLI half built before any new row starts. No new row plan starts while 5 or more partly
    merged rows wait only on a CLI half.

### 5.3 The track (ordered)

Status last updated 2026-11-12. Merges checked on GitHub with `gh pr list --state merged`: engine #465, #467 to #480, #483 to #487, #491, #495, #497 to #499, #504, #510, CLI #173, #175, #179 to #190, #192 to #197, #199, #200, #202 to #204, #217, #218, #220 and #221. Section 5 rows re-checked 2026-11-12 against engine #397, #515, #517, #519, #525 and CLI #213, #223 to #226; open PRs from `gh pr list --state open`. Rows: 47 closed, 21 partly merged, 69 not started, 3 deferred or parked (140 rows). "Not started" means nothing merged yet; it includes rows with a plan or a PR in review.

Order is the build order within the dependencies. "After" lists what must merge first. Branches are
on origin unless marked local. Detail for each row is in [roadmap/row-detail.md](roadmap/row-detail.md).

**A. Test, CI and structure foundations**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 1 | CI-E1: engine CI installs from the lock (`uv sync --frozen`), stale bench kwargs, sphinx `-W` cross-refs, truthful `pip-audit`, two sentries | engine | MERGED (engine #388, `2986fd5a`); its two audit-guard gaps closed in CI-E1s | done | CI-E0 (MERGED, engine #383) |
| 2 | CI-E1s: lock security bump (26 known vulnerabilities in 8 packages) and DP certified-stack fingerprint re-pin | engine | MERGED (engine #394, `cf68a280`): eight locked packages past their advisories, one new 3.10.20 certified-stack row, and the audit step can no longer be hidden or narrowed | done | CI-E1 |
| 3 | CI-E2: restore engine CI triggers, nightly `determinism`, `ci/required-jobs.toml`, `ci/unlaned.toml`, marker and trigger sentry, retire `engine-v2-substrate-matrix.yml` | engine | PARTLY: E2a MERGED (engine #491, `426e6d05`, 2026-11-12): PR and nightly triggers restored, `determinism` job, `ci/required-jobs.toml`, `ci/unlaned.toml` and the lane sentry, substrate workflow retired. E2b MERGED (engine #504, `4bb95063`, 2026-11-12): `scripts/dev/required_checks.py` (`contexts` prints the merge-tier check names, `verify` checks a head against its tier) and its test `tests/unit/scripts/test_required_checks.py`; the lane sentry also reads `.yaml` workflows. Owner Q1 (yes, 2026-11-12) applied: engine `main` branch protection requires the 25 merge-tier checks. Left: the plan's live check AT-23, `verify --tier nightly` on main after the first scheduled nightly run (none has run since E2a restored the trigger). The plan file is on `plan/ci-e2`, not on engine main | `E:plan/ci-e2` | CI-E1, CI-E1s (until CI-E1s, CI-E2's gate exempts `security.yml`) |
| 4 | ENGINE-PAR: engine parallel tests (pytest-xdist), engine full suite from about 66 minutes to roughly 15 to 20 on the 4-core VMs and the Mac; serial marks only for exclusive resources; same baseline-compare rules | engine | DONE. P1 MERGED (engine #393, `79f229d0`): `gates.sh` stores main's failing test ids once (`--write-baseline`, `--baseline-file`), so a full merge test is one suite run. P2 MERGED (engine #402, `b5b1ad16`): the test step runs under pytest-xdist (`GATES_WORKERS`, default auto) with a separate serial pass; baseline writes and compares stay serial; a collection guard refuses test ids that carry a memory address. Mac full suite 24 to about 13 minutes. Follow-up: one commit for the P2 review LOWs (strict-mode cell isolation, `DECOY_GATE_VENV_STRICT` in the CI regression job, `dp_provenance.py` headroom, comment counts) and the non-recursive sentry-manifest glob | none | CI-E1 |
| 5 | CI-L1: CLI CI (`ci.yml` installs `uv`, runs pytest; `ci/required-jobs.toml`, `ci/unlaned.toml`, sentry) | CLI | DONE 2026-11-12 (all slices merged): L1a MERGED (CLI #93, `d60d1fa`): `ci.yml` installs through the lock with `uv` and runs ruff, pytest, layers-gate, fresh-install-smoke, ci-template-lint and certified-profile on hosted runners (push and PR to main, weekly, manual), sentry `tests/sentry/test_ci_lock_installs.py`; both shared-file ledgers point at main commits (CLI #94, engine #391). L1b MERGED (CLI #218, `a1df1e3e`, 2026-11-12): `ci/required-jobs.toml`, `ci/unlaned.toml`, the lane sentry `tests/sentry/tooling/_ci_lanes.py` and its test `tests/sentry/tooling/test_ci_lanes.py`; `ci.yml` also runs daily, cancels stale PR runs, and every hosted job has a timeout. `main` has no branch protection and no ruleset (protection API 404 on 2026-11-12), so GitHub requires no job. V2-LOG: the lane sentry imports the shared `_shell_tokens` module by a private name (`tests.sentry.ci_scan._shell_tokens`); a small public facade shared by both repos (engine first, then re-vendor) replaces it | none | none |
| 5a | CI-X: the engine vendors the CLI's byte-identical shared CI shell parser (`tests/sentry/ci_scan/`) and its CI scanner parses through it; both repos check each other's copy | engine | MERGED (engine #390, `d9e18fa6`) | done | CI-E1 |
| 5b | CLI-BASELINE: port the engine's stored failing-id baseline (`--write-baseline`, `--baseline-file`) to the CLI `gates.sh`, so a CLI full merge test is one suite run (today CLI runs use legacy mode, main rerun on the VM) | CLI | MERGED (#115, `834ab99`): `gates.sh --write-baseline` and `--baseline-file` with tree-checked provenance; first CLI main baseline saved 2026-11-08 (0 failing of 3054), so CLI full merge tests now run the suite once | none | ENGINE-PAR |
| 5c | CLI-MAC-TESTS: the CLI suite on macOS arm64 has 16 failures unrelated to any slice (path and platform assumptions), and the CLI `gates.sh` needs bash 4 (`mapfile`), which macOS does not ship. Fix the tests and make `gates.sh` bash 3.2 safe, or install bash 4 on the Mac (owner's call) | CLI | DONE 2026-11-12 (all slices merged): S1 MERGED (#110, `ec209ec6`, Mac DP and install tests), S2 MERGED (#112, `91d191b9`, one unfolded stderr console); `gates.sh` bash 3.2 safe (#115, `834ab996`, sentry `tests/sentry/test_bash32_compat.py`); the last Mac failure fixed (#118, `12fc2e62`). Mac full suite on main `12fc2e6` 2026-11-08 ran 3108 passed, 7 skipped, 0 failed; engine mypy on macOS clean (engine #404) | none | none |
| 6 | WIN-RUNNER: Windows self-hosted runner on a GCP VM; spend approved by the owner; stopped when idle (`~/bin/vm-reap`) | infra | NOT STARTED; provision when CI-L1 or LIB L1b first needs a Windows lane | LIB plan section 5 OS lanes | none |
| 7 | FILE-SIZE: file-size ratchet sentry for engine and CLI (new, section 4.2) | engine, CLI | MERGED 2026-11-11 (last slice C3, CLI #199, `f1f9a58e`). Folded into LAYOUT (plan passed 2026-11-06): file-size and fan-out ratchets plus import-linter layer contracts. SIZE-CEIL MERGED (engine #447, `125f479b`, 2026-11-10, owner rule 2026-11-10): engine size pins are ceilings at the file's lines plus 20 (capped at 700), and a ceiling more than 40 above the file fails until lowered; legacy files over 700 stay exact and shrink-only. C1 MERGED (CLI #183, `581844b6`, 2026-11-10): the CLI Where Things Go map in CODEMAP.md (five columns, 27 rows) and the path guard `tests/sentry/layout/test_codemap_paths.py`. E1 MERGED (engine #410, `7a61be3c`, 2026-11-08): the engine Where Things Go map and its path guard. E2 MERGED (engine #479, `66d0f879`, 2026-11-11): package fan-out census (25 modules per directory; six oversize directories frozen shrink-only), one shared size and fan-out ratchet, and a numeric `max` in the baseline ratchet. C2 MERGED (CLI #196, `7d3ed44d`, 2026-11-11): CLI files capped at 800 lines (four legacy files exact and shrink-only), at most 25 modules per package (`src/decoy/cli/` frozen at 30), the E2 helpers vendored and sha-pinned, and the numeric `max` ratchet in the CLI. E3 MERGED (engine #480, `a0338ea7`, 2026-11-11): the engine import-layer contract (`.importlinter`, 6 tiers, 42 measured ignores) and its sentry, run only in `.venv-layers` through a `gates.sh` layers step and a layers-gate CI job; import-linter is a separate `layers` extra, so the certified install is unchanged. C3 MERGED (CLI #199, `f1f9a58e`, 2026-11-11): the CLI import-layer contract (7 tiers, 18 measured ignores, the flat `cli/` placed whole) with the same gate; `requirements-dev.lock` gains import-linter 2.15 | `E:docs/plans/2026-11-06-layout-map-and-guards.md` | CLI X0a ratchet (MERGED, CLI #81, #82) |
| 8 | REG-RENUMBER: `E:scripts/dev/registry_renumber.py` renumbers an unmerged slice's registry minor to `main + 1` at merge; `--check` for the merge gate | engine | MERGED (engine #398, `d46dbc85`): `registry_renumber.py` and its `--check` mode; LIB L0.1 is its first user (registry 1.7.0). REG-RELEASE E1 MERGED (engine #450, `5c24a75e`, 2026-11-10): changelog fragments. An engine PR that changes behavior adds one `changelog.d/<slug>.md` fragment instead of editing `CHANGELOG.md`; release prep folds them in with `scripts/release/stamp_release.py`, and a release is refused while fragments remain. E2 (registry stamping at release) waits on owner question R1 (plan `plan/reg-release`) | `p05-reg-renumber-build-handoff.md` | none; first useful after SUB-STOP |
| 9 | X0a-h engine and CLI parts (E1, E2, C1, C2): vendor `_ratchet.py`, `_approval.py`, `approve_growth.py`, `merge_check.py` byte-identical from the platform | engine, CLI | DEFERRED, off the V1 path (owner, 2026-11-05). Until it returns, the orchestrator flags any ratchet baseline growth by hand at each gate. Re-entry: a hidden exception slips past review, or the platform restarts | plan `P:docs/plans/2026-11-05-x0a-h-ratchet-hardening.md` (#181) | platform H1, H2, H4, H6 (parked) |

**B. Registry chain, gated engine branches and the first release**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 10 | SUB-STOP: every engine entry that runs a config refuses `subset:` before any read, `config.subset_run_unsupported`, registry 1.6.0 | engine | MERGED (engine #389, `adc212f3`), registry 1.6.0 | done | none |
| 11 | Vault key floor and simpleeval floor (slice 0: 11.1, 12.3) | engine | NOT MERGED. No PR; branch unchanged since 2026-11-01, 98 commits behind engine main. Blocked on: the Codex GO-WITH-FIXES findings are not recorded as fixed, and R-c shipped as `v0.19.0` (engine #399) without it, so it needs a merge of main, a re-gate and a new release. Main still has `simpleeval>=0.9.13`. CLI consumer side met by CLI #78 | `fix/vault-key-floor` `b79e864b` | a later engine release |
| 12 | B-6 vault core | engine | NOT MERGED. No PR; branch unchanged since 2026-11-01, 96 commits behind engine main. Blocked on: row 11 merging first; its re-check was a static trace only; its failure codes were registered against registry 1.3.0 (main is at 1.22.0), so it needs a merge of main, renumbered codes and a full gate. R-c (`v0.19.0`) shipped without it | `feat/b6-vault-core` `52df1da8` | row 11; a later engine release |
| 13 | Derived expression visibility (slice 0: 12.1 residue) | engine | MERGED (engine #408, `a5eb66e2`, 2026-11-08) | none | none |
| 14 | Value-free discovery and subset errors | engine | MERGED (engine #406, `4acac80a`, 2026-11-08) | none | none |
| 15 | F32 E1 | engine | MERGED 2026-11-12 in two halves: the closed support-bundle types (engine #498, `308b0af0`: new package `decoy_engine.support`, top tier of `.importlinter`, nothing in the engine imports it, `REGISTRY_VERSION` unchanged) and the label allocator with the no-network sentry (engine #499, `2fc5768c`: `support/_labels.py`, `tests/sentry/test_support_no_network.py`). Both merged after the `v0.22.0` tag, so they ship in the next engine release. The rest of F32 (engine E1b to E3, then the CLI C0, C1 and C1b after an engine release and the CLI repin) is row 70 | done (`feat/f32-e1-types`, `feat/f32-e1-labels`) | none |
| 16 | STORM E1 (engine part of the STORM rename), registry 1.7.0 | engine | NOT MERGED; no `feat/storm-e1` on origin | STORM re-cut plan `P:plan/storm-rename-recut` `dfe7cc6a` | SUB-STOP |
| 17 | WF-R engine and CLI part: tombstone the engine `WORKFLOW_*` reason codes (`E:src/decoy_engine/reasons/platform/_part1.py:72-74`, never deleted) and fix the CLI pointer (`C:src/decoy/cli/explain.py:170`) | engine, CLI | NOT STARTED | none | registry order |
| 18 | Engine release R-c and CLI repin: vault key floor, B-6 core, SUB-STOP, STORM E1, whatever else has merged, and the F34 release (owner Q4, 2026-11-08: R-c is the F34 release) | engine, CLI | RELEASED SHORT OF ITS LIST. Engine `v0.19.0` tagged (engine #399, `4a0d5b1f`, 2026-11-07) and the CLI repinned to `decoy-engine==0.19.0` (CLI #99, `586eb185`, 2026-11-07). It carried SUB-STOP (row 10, engine #389) and F34 E0 to E2 (engine #365, #370, #371). It did not carry the vault key floor (row 11), the B-6 core (row 12), STORM E1 (row 16) or F34 E3 (row 67): none of them has merged, so they wait for a later release | none | rows 10 to 12, 16 |

**C. Live CLI bugs and explicit config**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 19 | CLI-DIALECT: `decoy run` honours `has_header`, `column_names` and `delimiter` (live V1 bug); owned by CONFIG-EXPLICIT, lands ahead of it | CLI | DONE. Engine CSV reader (Part E) MERGED (engine #392, `b2ee6502`); engine `v0.19.0` tagged (#399, `4a0d5b1f`); CLI side (Part C) MERGED (CLI #99, `586eb18`): every CSV read goes through the engine reader with the declared dialect, sentry G-ONE-CSV-READ. Chunked partial-target risk is row 61a | `p05-cli-dialect-build-handoff.md` | none |
| 20 | CLI-FMT Part A: write file targets by declared `format` through one `_targets.py`; fixed width through the engine's `write_fixed_width`; format and suffix mismatch, and `--chunked` with fixed width, refused with exit 1 Owner 2026-11-06: CLI-IO folds in here: one source-reader module and one target-writer module for every format (csv, parquet, fixed width, later cloud and database), whole and chunked, each with an allowlist sentry that fails on a direct `pd.read_*`, `pq.read_table`, `.to_csv` or `.to_parquet` outside them. | CLI | DONE, merged #101 (2026-11-07) | `p05-cli-fmt-build-handoff.md` | CLI-DIALECT |
| 20b | CLI-FMT A2: G-ONE-TARGET-WRITE sentry (every table write inside `cli/io/_targets.py`, one allowlisted `data=` spool), shared import-normalizing scanner for read and write sentries, and `validate` / `ci check` report a declared-format and suffix contradiction | CLI | DONE, merged #102 (2026-11-07) | `p05-cli-fmt-a2-build-handoff.md` | Part A |
| 21 | CLI-FMT Part B: `detokenize`, `unmask` and `report diff` read CLI-written files by declared format; the evidence manifest records `format` and `layout` | CLI | DONE, merged #103 (2026-11-07) | `p05-cli-fmt-b-build-handoff.md` | Part A; merges with A |
| 21b | ATOMIC-OUTPUT: each local output file is staged and published in one replace, so a failed rewrite leaves the old file whole; mode handling for new and existing files; the writer sentry checks every table write goes through the staged path. One target per transaction; multi-target all-or-nothing stays with CLI delivery (row 61) | CLI | DONE 2026-11-07 (#105, `4cd24dd`). Also turned row 61a's strict xfail green. V2 items in `docs/records/2026-11-07-atomic-output-build.md` | `p05-atomic-output-build-handoff.md` | CLI-FMT A, A2, B |
| 22 | CONFIG-EXPLICIT: `has_header` required for CSV sources; headerless files declare `column_names` or a new `column_names_file` (exactly one); every source column listed in `columns:` (`passthrough` allowed), so an unlisted column always fails; `unconfigured_column_policy` retired or fixed to `error` | engine, CLI | IN PROGRESS. E1 MERGED (engine #409, `858e50a1`, 2026-11-09): a CSV source must set `has_header` (`source_file.has_header_required`), new `column_names_file` read through the file-access policy, registry 1.15.0. Pre-GA breaking: the physical plan hash moves for CSV configs, output bytes do not. E2a MERGED (engine #441, `f3816b81`, 2026-11-10): the declared-columns module (`source_columns`, `declared_columns`, `check_columns_declared`, `prepare_declared_sources`), codes `source_file.undeclared_column` and `source_file.undeclared_table` (registry 1.19.0), and the `declare-columns` and `source-schema` codemod modes; no run route calls the check yet, so runs are unchanged. E2c MERGED (engine #471, `8a9b5f00`, 2026-11-10): `profile_source`, `run_pipeline` and `run_pipeline_isolated` refuse a source column or table the config does not declare, before any data row is read, and `run_pipeline` with a `source_loader` needs `source_loader_schemas`. E2c merged after the `v0.22.0` tag, so it ships in the next release. E2d MERGED (engine #495, `8f9fdfab`, 2026-11-12): `run_mask_pipeline_chunked` takes a required `source_schema` and checks it before the chunks are touched; `run_mask_chunked` and `run_native_or_oracle_chunked` check the config at entry and each chunk's columns before it masks. E2b-f MERGED (engine #510, `a001f4d7`, 2026-11-12): test fixtures aligned with their declared columns, no `src/` change. E2b-r1 (the created-column contract) is open as engine #514 and in review. Left: E2b-r2 (refuse a declared column the source lacks), E2b-s (required strategy settings), the engine release that carries them, then the CLI half (C1 with the repin, then C2) | `p05-config-explicit-build-handoff.md` | registry order; CLI half after the release that carries it |
| 23 | VALIDATE-ALWAYS: `decoy run` runs every `decoy validate` check (config, compile, preflight) first and stops on an error | CLI | DONE 2026-11-08. Part 1 MERGED (CLI #88, `4ab55d4`): the validate checks live in `C:src/decoy/cli/gate/`. Part 2 MERGED (CLI #107, `8ac0f8d`): `decoy run` runs the gate before it reads source rows (exit 1, or 5 for capacity; `--json` adds `error_kind` and `messages`); about 0.8 s per run. Follow-ups FU-1 to FU-7 in the plan (FU-2 duckdb staging, FU-7 non-UTF-8 config exit 3) | `plan/validate-always`; `docs/records/2026-11-07-validate-always-p2-build.md` | none |
| 24 | X7c: CLI private file writes (`_private_file.py`) | CLI | DONE. S1 MERGED (#132, `0fafd0a`, 2026-11-09): private file creation and mode calls live in `_private_file`. S2 MERGED (#135, `99c400a`, 2026-11-09): `validate compile --output`, the token vault and the `decoy.mask()` spool go through it. S3 MERGED (#137, `6cff2cd`, 2026-11-09): the private-file sentry classifies every watched file sink and holds private writes to the choke point. Plan `docs/plans/2026-11-08-x7c-private-file.md` | none | none |
| 24a | VALUE-FREE-ERRORS: one config-error converter for every route; names (keys, tables, columns, file names, patterns) are shown, data values and secrets are hidden (owner Q1, 2026-11-06); exception-context ratchet | engine, CLI | MERGED 2026-11-11 (V1 slices; last slices A3 CLI #187 and B2 CLI #195). A1 and A2 MERGED 2026-11-08 (engine #412, `bf15cd99`). A3 MERGED (CLI #187, `ed39bb7d`, 2026-11-11): every CLI command that validates a pipeline config routes its errors through the engine's value-free parse, so messages carry names and locations, never submitted values. B1 MERGED (engine #417, `38517493`, 2026-11-09): engine `re` patterns anchor with `\Z`, and the vendorable `_defect_scan.py`. B2 MERGED (CLI #195, `68f90d0d`, 2026-11-11): CLI `re` patterns anchor with `\Z`, and a shrink-only ratchet holds `raise ... from None` inside `except` at its 37 sites. The V1 slices are all merged. Left for V2: B3 (V2 corrective), which waits for LAYOUT E3 and C3 and H-1. Plan passed 2026-11-06; V2 follow-ups FU-5 and FU-6 in the V2 corrective backlog | `E:plan/value-free-errors` | CLI-DIALECT, LAYOUT E1, row 14 |
| 24b | QA-GATE (first-user QA, owner 2026-11-08): `decoy validate` refuses what `run` would refuse. A declared column missing from the source and a rule missing a required setting (`fpe` with no namespace) fail at the gate with exit 1, the config-error code, never exit 3 at run. Folded into CONFIG-EXPLICIT E2's declaration gate (same pre-read boundary). Added 2026-11-10 (DI models QA 2026-11-10 M7): a DP release with no labels for a sampled column is refused at `decoy validate`, not at run with `statistical_stats_degenerate` | engine, CLI | NOT STARTED; scope added to E2 | [QA report](records/2026-11-08-cli-qa-first-user.md) H2, H3; DI models QA 2026-11-10 M7 | row 22 E1 |
| 24c | QA-SCAN-REDACT (owner 2026-11-08): saved scan files and `scan show` carry no raw values for PII-flagged columns (`top_values` and any other sample text); an explicit opt-in flag keeps them. Leak class, blocks V1 | engine, CLI | MERGED 2026-11-10. Engine S1 MERGED (engine #415, `44d6afe2`, 2026-11-09): scan documents redact cell values of sensitive columns by default. SCAN-MULTI S1c.1 (CLI #166, `f32834bb`) made `decoy scan --output` a value-free core and `scan show` prints no top values. Slice C MERGED (CLI #177, `e6bfb00c`, 2026-11-10), the last slice: `decoy demo` writes a redacted `scan.json` through the engine's `profile_document`, `decoy explain security` and the `decoy.scan()` docstring say what saved scans and fit snapshots hold, and a sentry fails if a CLI module writes a raw `profile.to_dict()`. Closed under plan Q1 (a) (owner 2026-11-10): no scan opt-in flag, because saved scans hold no values; the opt-in moves to row 36. Engine half in `v0.21.0`, which the CLI pins since CLI #169 (`488823ac`, 2026-11-10) | QA report H5 | none |
| 24d | QA-SHUFFLE-DET (owner 2026-11-08): `shuffle` gives byte-identical output for the same config, seed and mask secret; QA saw two runs differ. Engine bug: reproduce, root-cause, fix with a determinism test | engine | DONE, merged engine #418 (`1bf9e7f8`, 2026-11-09): unkeyed `shuffle` now draws from the mask key with the job seed, table and column bound in, and repeats across processes. Output changes once (pre-GA). In engine 0.20.0, which the CLI pins since CLI #164 | QA report M11 | none |
| 24e | CLI-QA1 (owner 2026-11-08: bugs are V1): the validate and preflight traceback when a relationship has no resolvable namespace (and `validate compile` reporting no FK while one is declared); internal names in user text (`_scan`, `_gate`, ticket ids, the platform doc path); `explain pipeline` says version 1; `list disguises` tip names presets `init` rejects; stray `logs/` in the working directory; false "output directory does not exist" warning; fidelity "PASS grade F"; `integrity` column detail outside `--json`; reid risk unit; `explain vault` vs the plaintext tokenize store; `ci check` with no manifest; `validate compile --json` command name; run summary rows, files and tables. STORM wording goes with row 56; wizard items go to row 32b . Also from the distribution-integrity QA: the same traceback for generate-only relationships with no `namespace` (namespace must not be required when nothing is masked); fidelity "intended" marker (hash key columns not flagged, no joint score across id spaces); `integrity` saying configured columns are "not configured to be masked" and hiding `source_identity_rate`; internal ids in help (FC-1, S22-CL-V1GRAPHRUNNER, report.py:97, BF1); `explain keys` length; docs on which strategies keep frequency and joint structure (faker is row-positional, shuffle breaks pairing); `mode: generate` in the generate template and engine recipes.md; a generate-with-FK example | CLI, engine | IN PROGRESS. MERGED 2026-11-09: engine #429 (`3b1b285d`, `profile_relationships_from_config` export, engine logger NullHandler), CLI #145 (`df418657`, root-app traceback guard), CLI #146 (`cfdee4ef`, C2a group paths and internal names out of user text), CLI #147 (`4eb43a52`, C4 report verdicts and integrity findings), CLI #148 (`6a175432`, C0b uncompilable plan as preflight capacity fail), CLI #149 (`d5ff37dd`, C2b internal names out of user text, old-engine refusals via guidance registry), CLI #150 (`a565bded`, C3a real command name in `--json`), CLI #151 (`9f752825`, C5 run reports published paths only). C1 MERGED (CLI #181, `6fafa5cd`, 2026-11-10): no-profile compiles carry the config's relationships, so `validate compile` orders parents first and reports a relationship it cannot resolve; in `decoy validate`, a `capacity.plan_uncompilable` row that repeats a compile error becomes a warning. C3b MERGED (CLI #224, `62798427`, 2026-11-12): `decoy validate` checks output targets. Every slice of `C:plan/cli-qa1` is now merged (E1, C0a, C0b, C1, C2a, C2b, C3a, C3b, C4, C5). The row stays open for its distribution-integrity QA items, which are outside that plan and have no plan or merged PR yet | QA report sections 2 to 4; [DI QA report](records/2026-11-08-cli-qa-distribution-integrity.md) MEDIUM, LANGUAGE, High 5 | none |
| 24f | QA-FIT-REDACT (distribution-integrity QA, owner 2026-11-08): `decoy fit` without `--epsilon` keeps no raw values for PII-flagged or high-cardinality columns in the snapshot unless an explicit opt-in flag is passed (same rule as row 24c), and its message points at `--epsilon`. Leak class, blocks V1. Added 2026-11-10 (DI models QA 2026-11-10 H6, H7; the leak still shows on engine `5c24a75e` and CLI `9f603536`): numeric `min`/`max`, labels with a count of one, and short free text (30 or fewer distinct strings, now classed categorical) are not kept raw in a plain snapshot. Engine #420 covers profiler-flagged columns only, and an unflagged note column kept all 30 strings | engine, CLI | MERGED 2026-11-10. Engine MERGED (engine #420, `3af398d5`, 2026-11-09): fit snapshots hide raw values of sensitive columns by default. CLI MERGED (CLI #171, `02d278fd`, 2026-11-10): `decoy fit` writes its snapshot through the engine's `distribution_snapshot_document`, profiling the whole file; flagged columns keep no cell values, a number column keeps one range and a date column keeps years; the file carries `value_policy` and `redacted_columns`, `fit` prints the withheld column names (never values), and `--include-values` keeps every column's values with a warning. Engine half in `v0.21.0`, which the CLI pins since CLI #169 (`488823ac`, 2026-11-10) | DI QA report High 2; DI models QA 2026-11-10 H6, H7 | row 24c |
| 24g | QA-DP-GATED (owner 2026-11-08): a DP fit on a default install ends with a plain-English message and a next step instead of `dp_stack_uncertified` wording; help marks DP as gated. Exit code stays 3. A certified stack for normal users is V2 | engine, CLI | MERGED 2026-11-10. Engine part MERGED (engine #420, `3af398d5`, 2026-11-09): the DP fit request check is public. CLI MERGED (CLI #172, `50c4af33`, 2026-11-10): `decoy fit --epsilon` reads only the header, runs the name checks and the engine's `check_dp_fit_request`, then the body; an uncertified install exits 3 with a plain message and a hint that names `--include-values` first. Engine half in `v0.21.0`, which the CLI pins since CLI #169 (`488823ac`, 2026-11-10) | DI QA report High 3 | none |
| 24h | QA-FK-FANOUT (owner 2026-11-08): a generated `reference` column draws child counts from the fitted per-parent counts in the snapshot, so generated fan-out keeps the source skew; a test checks the shape. The generation QA found this is a missing feature, not a regression | engine | MERGED 2026-11-11. E1b MERGED (engine #419, `1e8739ae`, 2026-11-09): derived generators moved out of `synthesize.py`, no behavior change. E0 MERGED (engine #427, `9bc86d24`, 2026-11-09): fan-out reason codes, and compile refuses fitted reference fan-out under DP. E1 MERGED (engine #428, `f118ee02`, 2026-11-09): degree histogram, decoder and allocator. E2b MERGED (engine #452, `cfef8a6e`, 2026-11-10): a `reference` column with `distribution: fitted` draws each parent's child count from the fitted degree histogram in the snapshot, read once at compile and pinned. E2a MERGED (engine #448, `1c0d3553`, 2026-11-10): compile, the config-only checks and plan load refuse a fitted `reference` column with no `snapshot_file`, an unreadable snapshot, no fan-out for the column (every DP snapshot) or `weights`, `min_per_parent` or `max_per_parent` set; no registry change. D MERGED (engine #470, `bbc96dc8`, 2026-11-10): `docs/strategies.md` documents fitted reference fan-out and every refusal code. All engine slices are in engine `v0.22.0` (#472), which the CLI pins since CLI #184 (`990199ef`). C1 MERGED (CLI #192, `475dfd30`, 2026-11-11), the last slice: `decoy fit --fanout COLUMN` records per-key child counts in the snapshot, so a `reference` column with `distribution: fitted` keeps the source's fan-out shape; refused with `--epsilon`; counts only | DI QA report High 4 | none |
| 24i | GEN-C1 (generation QA, owner 2026-11-08): each generated column's seed derives from the column name, so two columns with identical settings (two `first_name`, two `date_between`, two categoricals, fitted statistical columns) are independent. Changes output for existing seeds and keys; accepted pre-GA, recorded in the changelog, no adapter. Regression test with two identical columns. Critical, blocks V1 | engine | MERGED (engine #421, `24796b0f`, 2026-11-09); output changes for existing seeds. DI models QA 2026-11-10 re-test confirms the fix on engine main: identical columns share no rows, independent statistical columns at -0.01. In engine 0.20.0, which the CLI pins since CLI #164 | [GEN QA report](records/2026-11-08-cli-qa-generation.md) Critical 1 | none |
| 24j | GEN-C2 (owner 2026-11-08): generated numbers stay numeric inside the generator: `derived` arithmetic on sequence and float columns, `grouped_series` ordering on numeric `order_by`. Critical, blocks V1 | engine, CLI | MERGED (engine #445, `1a5b36e5`, 2026-11-10): generated numeric columns are int64/float64 instead of text (an unformatted `sequence`, a faker provider that returns an int or a float), so `derived` arithmetic and `grouped_series` ordering work on numbers; a column stays text when a reader of it needs text. New `decoy_engine.generated_table_to_pandas` keeps nullable integers as integers. CLI half done in the 0.20.0 repin (CLI #164, `620290a4`, 2026-11-10): generated output goes through `generated_table_to_pandas` | [GEN QA report](records/2026-11-08-cli-qa-generation.md) Critical 2 | none |
| 24k | GEN-STRICT (owner 2026-11-08): per-type strict schema for generate columns (unknown keys such as `weigths`, bad `faker_type`, negative weights, bad locale, `null_probability` outside 0 to 1, `step: 0`, duplicate column names, bad formulas, missing `references`) refused at validate with exit 1; everything `run` refuses (weights all zero, mixed-type categories, `group_by` equal to `order_by`, forward references) fails at validate too, naming the column; an over-capacity `row_count` fails at validate and run with exit 5 (capacity), owner 2026-11-08 | engine, CLI | MERGED 2026-11-11 (last slice D, engine #478, `6e2e57bd`). E0 MERGED (engine #425, `97545972`, 2026-11-09): strict generate-column reason codes. E1 MERGED (engine #430, `325703f3`, 2026-11-09): strict per-type option validation at config parse. E3 MERGED (engine #424, `67fe6d45`, 2026-11-09): a resident generate run whose output cannot fit in detected memory is refused before any provider runs (`generation_budget_exceeded`), and `estimate_job_capacity` reports it as INSUFFICIENT. E2 MERGED (engine #465, `defe89c2`, 2026-11-10): one compile-time check, `check_generate_columns`, refuses generate configs that would fail or fall back at run. E0 to E3 are in engine `v0.22.0` (#472), which the CLI pins since CLI #184 (`990199ef`). C1 MERGED (CLI #188, `d0e8ba53`, 2026-11-11): tests hold `decoy validate` and the pre-run gate to the strict generate-option checks, value-free. C2 MERGED (CLI #190, `b13f58bb`, 2026-11-11): a generated table too large for memory exits 5 at `decoy validate` and before `decoy run` writes anything. D MERGED (engine #478, `6e2e57bd`, 2026-11-11): the generation sections of `docs/strategies.md`, a per-type option table checked against `generate_option_catalog()` (which now lists the keys checked at plan compile), the six missing-reference codes and the memory floor; the editor schema allows `pooled` only on `faker` | [GEN QA report](records/2026-11-08-cli-qa-generation.md) High | row 24b |
| 24l | GEN-FIT-SHAPE (owner 2026-11-08): `fit` carries each column's null and blank rate into generation; `report fidelity` scores null rates; fitted numbers keep source precision and datetimes keep source resolution | engine, CLI | MERGED 2026-11-10. E0 MERGED (engine #433, `881095b7`, 2026-11-09): reason code `plan.statistical_cell_format_invalid`, registry 1.16.0. E1 MERGED (engine #434, `5a7f14dc`, 2026-11-09): fit snapshots record each column's decimal places, datetime resolution and blank count. E2 MERGED (engine #436, `6bdd4840`, 2026-11-09): the statistical sampler applies the fitted format (null rate, blank fraction, decimal places, date resolution); snapshots without the block and DP snapshots generate the same bytes. E3 MERGED (engine #438, `79d5ded7`, 2026-11-09): `report fidelity` scores null-rate drift (`value_similarity` and `missing_value_similarity` per column; DP snapshots report only). C1 MERGED (CLI #173, `cf4df70d`, 2026-11-10): `decoy fit` shows null rates in its summary and `--json` (`null_rates`), `report fidelity` adds a Nulls column when rates drift, and both CSV writers keep nullable integers whole | [GEN QA report](records/2026-11-08-cli-qa-generation.md) High, Medium | none |
| 24m | GEN-UNIQUE (owner 2026-11-08): a `unique` option per generated column and per junction-table key pair, failing clearly when the domain is too small; `pooled` documented | engine, CLI | MERGED 2026-11-10. E0 MERGED (engine #435, `ad0e6683`, 2026-11-09): four uniqueness reason codes, registry 1.17.0; nothing raises them yet. E1 MERGED (engine #440, `84f4290d`, 2026-11-09): unwired groundwork (config checks, shared parent keys, the shared uniqueness refusal builder); output bytes unchanged. E2 MERGED (engine #446, `937d9e53`, 2026-11-10): `unique: true` on faker, categorical and reference generate columns and `unique_together` column pairs; a domain too small is refused; faker retries are capped at 1,000 attempts per row; unique plans run resident and the pinned route refuses `unique_together`; columns without `unique` generate the same cells. D1 MERGED (engine #464, `b63c0fb9`, 2026-11-10): the user guide for `unique` and `unique_together`; docs only, merged after the `v0.21.0` tag, so it ships with the next engine release. CLI C1 MERGED (CLI #176, `40f464b1`, 2026-11-10): `decoy run` and the pre-run gate exit 1 for `uniqueness_impossible` and 5 when generated output cannot fit the memory budget, before any output is written, and `decoy explain` names the reason. E0 to E2 are in `v0.21.0`, which the CLI pins since CLI #169 (`488823ac`, 2026-11-10) | [GEN QA report](records/2026-11-08-cli-qa-generation.md) High | none |
| 24n | GEN-REL (owner 2026-11-08, all V1): a date window anchored to a parent column; per-parent `derived_aggregate`; self-reference (`manager_id`) as a hierarchy, not a cycle; an empty parent fails under `orphan_policy: fail`; impossible or contradictory `min/max_per_parent` refused; weighted `reference` with no weights refused. Fan-out from a fit is row 24h | engine | NOT STARTED. Plan written 2026-11-10 on `E:plan/gen-rel`, not yet gated | [GEN QA report](records/2026-11-08-cli-qa-generation.md) High | row 24h |
| 24o | GEN-CLI (owner 2026-11-08): one path rule (targets and `snapshot_file` relative to the config file); run summary and `--json` list output paths, rows and warnings; a preview (`run --rows N`); `init` for generation and from a CSV; `init -o -` writes to stdout; a Generate help group; `--fidelity` and `fidelity_warn_threshold` work for generate or are refused; `validate compile --explain` covers generate; seed vs `--master-key` stated; a Generation explain topic listing every type and option; `explain pipeline`, `transforms` and `yaml` corrected. Added 2026-11-10 (DI models QA 2026-11-10 H4, H5): `report fidelity` prints its warnings (`null_drift`, `kind_drift`) in the terminal, not only in `--json`; the generation fidelity warning reaches stdout and `--json` (since engine #426 it reaches no output at all unless the host turns on logging); revisit the 0.8 default, which passed the outlier file at 0.861 | CLI, engine | MERGED 2026-11-11. E1 MERGED (engine #460, `4694c91f`, 2026-11-10): relative `snapshot_file` and quarantine paths resolve against the config file's folder through `fileaccess.config_relative`, and a `base_dir` keyword reaches every compile, validate, run, estimate and capture entry; `pin_and_check_snapshots` pins and checks snapshots in one place; the generation fidelity gate returns `QualityWarning` records (`warning.generation_fidelity_below_threshold`), also when one comparable column scores below the 0.8 default; one shared `generation_order` for both generation routes; `config.generate_option_catalog()` lists each generate type's options; codes in registry 1.22.0, no version change. E1 is in engine `v0.21.0` (#466, `b1e4aa9a`, 2026-11-10), which the CLI pins since CLI #169 (`488823ac`). C1 MERGED (CLI #174, `38cdb695`, 2026-11-10): YAML source and output paths resolve from the config file's folder in `run`, `tokenize`, `validate`, `preflight`, `demo` and `decoy.mask()`, through one call a sentry checks; `decoy run` prints engine warnings and per-table lines, warns on a missing seed, and refuses `--fidelity` when no table is masked. C2 MERGED (CLI #182, `7e29f5fe`, 2026-11-11): `decoy run --rows N` previews a generate pipeline and writes nothing, `decoy init -o -` writes to stdout, and `decoy init <csv> --preset generate` writes a snapshot and config pair published together. C3 MERGED (CLI #189, `aa05799d`, 2026-11-11): help panels with a sentry, `validate compile --explain` for generate tables, explain topics `generation` (type list from `generate_option_catalog()`), `transforms`, `pipeline` and `yaml`, README and CLI reference. No CLI slice remains | [GEN QA report](records/2026-11-08-cli-qa-generation.md) Medium, Language; DI models QA 2026-11-10 H4, H5; plan `E:docs/plans/gen-cli.md` (revision 4) | row 24e |
| 24p | GEN-PROVIDERS (completeness audit, owner 2026-11-08): includes census item A9 (owner 2026-11-12): each identifier provider declares its real locale scope, with a guard test on the declarations; generation can use every masking domain provider (NPI, MRN, ICD-10, NDC, PAN, IBAN, CUSIP, EIN, SSN and the rest of the 34) and the correlated person and address composites (email matches name, ZIP matches state, sex matches first name, age matches birth date); an unknown provider name fails at validate. Existing code, reused from the masking registry, not copied | engine | NOT STARTED. Plan on `E:plan/gen-providers`, final Codex fix in progress; build paused by priority. Owner questions taken on the recommended answers under standing approval (2026-11-10): `type: provider`; per-provider options and `unique` are V2; `composite_custom` is refused; sex values are F and M | [GEN completeness audit](records/2026-11-08-generation-completeness-audit.md) Decision 1, 2 | row 24i, row 24k |
| 24q | GEN-TYPES (owner 2026-11-08): new generate types and options: `constant`; parametric `distribution` (normal, lognormal, uniform, exponential, poisson, beta, zipf), which makes the capability matrix's 12th type real; a weighted lookup list from a file; per-column output type (int, decimal(n), date, bool); conditional `derived` (`if()`) | engine | IN PROGRESS. Plan passed 2026-11-10 (`E:plan/gen-types`). E1 MERGED (engine #467, `45533490`, 2026-11-10): `constant`, and `distribution` with the `uniform` family only, drawn from a new `dist` RNG family; normal, lognormal, exponential, poisson, beta and zipf are refused at compile (`generate_option_value_unknown`) and move to E1b. Owner answer (recommended, standing approval, 2026-11-10): drop the families that are not portable instead of adding a per-architecture caveat. E1 is in engine `v0.22.0` (#472). E2 MERGED (engine #477, `82d00f4e`, 2026-11-11): `output_type` on generate columns. Next: E1b (more families) needs a portable-sampling design first; E3 (`lookup`) and E4 (`if()`) are not started | [GEN completeness audit](records/2026-11-08-generation-completeness-audit.md) A | rows 24i, 24j, 24k |
| 24r | GEN-INHERIT (owner 2026-11-08): a child column takes a parent row's attribute (`claims.state` = the member's state); conditional categoricals declared in YAML, not only from a fitted snapshot | engine | NOT STARTED. Plan passed 2026-11-10 (`E:plan/gen-inherit`); build not started | [GEN completeness audit](records/2026-11-08-generation-completeness-audit.md) B | row 24n |
| 24s | GEN-CATALOG (owner 2026-11-08): a CLI command that lists every generate type and option, and every provider, from the engine's registries (no hand-kept list); one generate starter template per industry (healthcare, banking, insurance, retail, telecom, HR) | CLI, engine | NOT STARTED; plan needed | [GEN completeness audit](records/2026-11-08-generation-completeness-audit.md) C | rows 24o, 24p, 24q |
| 24t | PROJECT-LAYOUT (owner 2026-11-09): no loose files. Every file a pipeline writes lands in its own pipeline folder in the project. A relative or missing target path resolves under `out/<pipeline>/<run-id>/`, with a `LATEST` file plus a `current` link per pipeline; side files (`scan --output`, `report`, `detokenize`, `unmask`, sample output) default into the same pipeline folder; an absolute target path in the YAML is still honored for production delivery. Run summary and `--json` print the folder used. `decoy run` warns when a relative target resolves outside the project. Projects (owner 2026-11-09, clean UX and easy navigation across projects and files): a project is a folder (recommended one per client) with `decoy.yaml`, `pipelines/<name>/`, `out/` and `.decoy/`; `decoy project new <dir>` creates one, `decoy init` keeps its job and creates a pipeline inside the current project (`pipelines/<name>/pipeline.yaml`). Pipelines run by name from anywhere in the project (`decoy run <name>`, same name argument for validate, scan, report, fit, plan), `--project`/`DECOY_PROJECT` select another project without cd, `decoy pipelines` lists a project's pipelines, `decoy run --all`. Builds on LIB's `.decoy/` root rule (section E) and the 24o path rule | CLI, engine | IN PROGRESS. P1a MERGED (CLI #141, `0e8ae59d`, 2026-11-09): `replace_symlink` atomic link swap. P2a MERGED (CLI #143, `b03fb261`, 2026-11-09): `owning_run` recognizes run folders, no caller yet. E1 MERGED (engine #423, `98551956`, 2026-11-09): optional `name:` on the pipeline config and the shared name rule. E2 MERGED (engine #426, `9803fd10`, 2026-11-09): `run_pipeline(..., quarantine_path=...)` replaces `quarantine.output_path` after the config hash, and the engine opens no log file unless the caller passes one; in engine `v0.20.0` and later. P1b MERGED (CLI #180, `3b44dbbb`, 2026-11-10): the one project-root finder (`decoy.yaml` marker, `kind: decoy-project/v1`), pipeline names, claims, run ids and run folders, `out/.gitignore`, the `layout.*` codes and `_private_file.create_private_directory`; no command uses them yet. P2b MERGED (CLI #193, `3f954118`, 2026-11-11): `decoy run` and `decoy tokenize` write relative outputs into `out/<name>/<run-id>/` and move `latest` only after a clean run; project markers and `latest` are read through one small-file reader that refuses symlinks, FIFOs and swapped files (plan `C:plan/project-layout`). Link fix MERGED (CLI #197, `6eb2080b`, 2026-11-11): the run link is named `current`, because `latest` collided with the `LATEST` file on case-insensitive filesystems (the macOS and Windows defaults). P3 MERGED (CLI #200, `a4109afe`, 2026-11-11): in a project, `decoy run --evidence-out` records pipeline, source and output paths relative to the project root with `path_base: "project"`; `decoy report verify --project` and `decoy ci check` read manifests through one reader and one path resolver (`resolve_manifest_path`, sentry G-ONE-MANIFEST-PATH), refuse a path that leaves the project, never read `DECOY_PROJECT` or the working directory for a project manifest, and check the manifest shape strictly; `report diff` reads formats from the resolved output path. V2-LOG from the gate (V1 bar): V1-1 provenance, an exact manifest copy at the same relative place in another project still binds to that project's files because the marker holds no project id. P4 MERGED (CLI #213, `8144c9e6`, 2026-11-12): `validate`, `ci check` and `run` refuse an escaping or invalid output location before any source row is read, run `--json` gains its output fields, and `--out-dir` is added. P5 MERGED (CLI #226, `52a2399b`, 2026-11-12): every command takes a pipeline name in place of its config path. Open: P6 to P10 (CLI only; no engine slice remains) | none | row 24o path rule; LIB L1b |
| 24u | GEN-NUM-SHAPE (DI models QA 2026-11-10, owner 2026-11-10): a fitted number column survives one outlier and heavy skew (quantile-based or clipped bins in place of ten equal-width bins over min to max), and a number column with few distinct values keeps its exact values like a categorical, behind the same disclosure gate. Re-test on engine `5c24a75e`: one value of 1,000,000 moved the mean from 150 to 50,084; a lognormal median went from 20.5 to 92.1; four prices became 3,585 values with 0.08% on a real price. Changes snapshot bytes. V1, blocks V1 | engine | MERGED (engine #458, `86a28222`, 2026-11-10): a fit keeps a number column with 30 or fewer distinct values as exact values and gives a larger one (100 or more values) a quantile grid; every interval and tail holds at least 10 source rows, and the snapshot loader validates the stored mass (capped at 2**40 rows). Snapshots fitted earlier generate as before; re-fit to get the new shape. In engine `v0.21.0` (#466); reaches CLI users through the repin, CLI #169 (`488823ac`, 2026-11-10) | DI models QA 2026-11-10 C2, H3; plan `E:docs/plans/2026-11-10-gen-num-shape.md` | none |
| 24v | FID-RANGE (DI models QA 2026-11-10, owner 2026-11-10): numeric fidelity no longer divides the quantile error by the source range, which one value can stretch (interquantile or rank scale instead). Re-test: the outlier column above still scores 0.940 and the price column 0.926. Null scoring is done (engine #438, row 24l E3). Changing `similarity` re-baselines the platform's honest-capability statement and its pinned test. V1, blocks V1 | engine | MERGED (engine #454, `c15f1c37`, 2026-11-10): numeric column similarity divides the quantile error by the source interquartile range (p75 - p25) instead of the min-to-max range, falling back to p95 - p05, then max - min; a constant column scores 1 when the output matches and 0 otherwise; the old 1.0 floor is gone. Breaking in the 0.20.0 changelog: scores drop for skewed or drifted columns, so re-check `fidelity_warn_threshold` and policy floors. Docs follow-up engine #455 (`53632b57`): the DI guide marks C3 fixed and the plan is `docs/plans/2026-11-10-fid-range.md`. The platform's honest-capability statement and its pinned test still need a re-baseline when the platform takes this engine | DI models QA 2026-11-10 C3 | none |
| 24w | GEN-COND-CAP (DI models QA 2026-11-10, owner 2026-11-10): the `condition_on` joint cap (25 cells today) can be raised from `decoy fit`, `fit` warns when a pair has more cells than the cap, and generation warns when a parent value has no cells and falls back to the child's overall counts. Re-test: 36 real pairs, 25 kept, 43 of 6,000 rows (0.72%) were pairs absent from the source, with no warning. Notes: M1 (a renamed parent cannot be conditioned on) and M2 (an unseen parent value falls back silently) are in V2-LOG (v2-corrective-backlog, 2026-11-10). V1, blocks V1 | engine, CLI | MERGED 2026-11-11. E1 MERGED (engine #456, `217ff0e8`, 2026-11-10): the fit-side cap on joint contingency cells (`contingency_top_k` takes 1 to 1000; a cap above the default is refused for value-bearing kinds in a plain snapshot), dropped cells collapse into the joint's `other_count`, and the public `snapshot_joint_warnings` returns one `QualityWarning` (`warning.fit_joint_cells_truncated`) per truncated joint; registry 1.22.0. E1b MERGED (engine #461, `1155b20c`, 2026-11-10): when a conditional column falls back to its overall counts because the parent value was never seen in the fit, generation raises one `warning.generation_condition_parent_unseen` per column, counts only; generated bytes do not change. E1 and E1b are in engine `v0.21.0` (#466), which the CLI pins since CLI #169 (`488823ac`). Engine #469 (`59a9b8f3`, 2026-11-10) exports `MAX_CONTINGENCY_TOP_K` from `decoy_engine.quality` for the CLI; it is in `v0.22.0`. C1 MERGED (CLI #186, `3800e0ed`, 2026-11-11): `decoy fit --joint-max-cells N` (default 25, at most 1000; without `--include-values` a raised cap works only on pairs of plain categorical columns), one `warning:` line per truncated pair on stderr and `warnings` in `fit --json`, and the run summary names the generation fallback; names and counts only | DI models QA 2026-11-10 H1; plan `E:docs/plans/2026-11-10-gen-cond-cap.md` | none |
| 24x | FIT-ROWS (owner 2026-11-10): `decoy fit` reads at most the `fit.max_rows` setting (default 1,000,000, set in `$DECOY_HOME/settings.json`); `--rows N` overrides it for one command; a larger file is fitted on a seeded sample drawn from the whole file | CLI | MERGED (CLI #175, `c9f97494`, 2026-11-10): `decoy fit` reads at most `fit.max_rows` (default 1,000,000) or `--rows N`; a larger file is fitted on a seeded sample from the whole file; the summary says `fitted on N of M rows`; DP mode never samples and `--rows` with `--epsilon` is refused | CLI #175 | CLI #173 (merged) |
| 24y | GEN-FORMULA-SEQ (V1 bar, function break, found 2026-11-10): a generate `formula` that reads a `sequence` column gets its values as strings (engine #445 keeps a `sequence` column as text when a formula reads it), so `round(a/3)` gives all nulls with only a warning. Fix in the engine, then the CLI exit code and docs. V1, blocks V1 | engine, CLI | NOT STARTED | none | none |
| 24z | FAKER-POOL-DISTINCT (engine QA checklist fact-check 2026-11-11 (Codex, engine branch `claude/sharp-cori-um7k6i`)): deterministic `faker` picks a pool slot by reducing a 64-bit derived value modulo `pool_size` (`E:src/decoy_engine/determinism/_derive.py:319`), so two distinct source values can get the same output, while the docs promise distinct in, distinct out. A masked key column can merge two people. The plan either makes the mapping collision-free or corrects the promise and reports a collision count per column. V1 | engine | NOT STARTED | none | none |
| 24za | ENGINE-DOCS-TRUTH (engine QA checklist fact-check 2026-11-11 (Codex, engine branch `claude/sharp-cori-um7k6i`)): three engine docs disagree with the code. `E:docs/strategies.md` says unparseable `date_shift` and `bucketize` cells pass through, but the handlers record a `format_error` row error that fails the job or quarantines the row (`_date_shift.py:234`, `_bucketize.py:126`); the strategy catalog in the same file lists 17 strategies where the handler registry and `docs/capability-matrix.md` have 24 (missing: `tokenize`, `top_code`, `group_key`, `grouped_series`, `windowed_date`); `E:docs/determinism.md` still promises a `job_seed` fallback for a keyed strategy without a secret, which is refused (`keyed_strategy_requires_secret`) in every release phase. Docs only; the code is the intended behavior. V1 | engine | NOT STARTED | none | none |
| 24zb | DATE-SHIFT-UNKEYED (automated QA scan 2026-11-11, finding F2; owner 2026-11-11 option (a)): unkeyed `date_shift` is refused in V1 in the engine and the CLI. A proof on the Mac (2026-11-11, engine 0.22.0) showed the legacy `MD5(value)` shift in `E:src/decoy_engine/transforms/date_shift.py` is reversible by search (one to four candidate dates per row over a 365-day window, the source date always among them), and that `decoy run`, `decoy run --chunked`, `decoy.mask()` and engine `run_pipeline` already refuse an unkeyed `date_shift` with `keyed_strategy_requires_secret` before reading a source. The legacy class has no live caller. Plan: pin the refusal on every surface, hard-delete the MD5 path, add a sentry that no unkeyed shift exists. Plan on engine branch `plan/date-shift-unkeyed`. Feature group: date and number strategies (engine QA checklist section 07); build at that group's QA pass (owner rule 2026-11-11: QA and its fixes run only on a V1-complete group). V1, blocks V1 | engine, CLI | NOT STARTED | none | none |
| 24zc | CERT-PIN-CVES (automated QA scan 2026-11-11, finding F1; owner 2026-11-11): the certified runtime pins in `requirements-certified.txt` carry known advisories. Repin to exactly certifi 2026.10.18, cryptography 50.0.0, pyasn1 0.6.5 and urllib3 2.8.0 (no other line moves, no version above these). The repin changes the DP certified fingerprint (`d5898d1f...`), so the engine must first ship the new CLI-profile row in `_CERTIFIED_STACKS`, then the CLI repins the engine and the four pins together. Plan on CLI branch `plan/certified-pin-cves`. Feature group: fit, fidelity and differential privacy (engine QA checklist section 13); build at that group's QA pass (owner rule 2026-11-11). V1 release blocker | engine, CLI | NOT STARTED | none | an engine release with the new row |
| 24zd | DUP-DEFECTS (duplication census 2026-11-12, packages A and B; owner 2026-11-12: scope added for codebase health): 28 places where two copies of the same logic disagree (17 engine, 11 CLI), listed in `C:docs/records/2026-11-12-duplication-census/REMEDIATION.md`. First a read-only reachability pass that marks each item confirmed or not. Confirmed items that meet the V1 bar (section 3) are fixed in this row; the rest go to the owning feature group's QA remediation. Owner decided 2026-11-12 (go recommended): A1, `joint_mask` fallback and generate-mode draws seed per group through `derive(mask_key, namespace, table, group)`, a one-time output change built in 24zf; A9, each identifier provider declares its real locale scope (SSN, EIN, NPI, NDC refuse outside `en_US`; IBAN, PAN, ICD-10 are locale-free; CUSIP `en_US` and `en_CA`), built in GEN-PROVIDERS (row 24p) | engine, CLI | NOT STARTED | none | none |
| 24ze | DUP-GUARDS (duplication census 2026-11-12, packages D and G; owner 2026-11-12): sentries with a shrink-only baseline of today's sites for RNG construction, digest JSON, hmac, Arrow text predicates, environment reads, CLI error text, config loads, stdout writes, literal exit codes and file operations (D2 to D11; jscpd, D1, may move to V1+), plus two churn reducers: draw-site catalogue keyed by function or marker instead of `file:line` (G1) and the release script writing the DP certified-stack row (G2). No behavior change. Report: `C:docs/records/2026-11-12-duplication-census/REMEDIATION.md` | engine, CLI | NOT STARTED | none | none |
| 24zf | DUP-FREEZE (duplication census 2026-11-12, package C; owner 2026-11-12): settle the surfaces that freeze at REL-GATE. One CLI error emitter and `--json` error shape, one exception-to-exit-code map, one canonical JSON rule for digests, the seed derivations from 24zd (including A1, per-group `joint_mask` seeds), one config loader, `--json` only through `emit_json`, one flag truthiness rule per repo, one generated-at shape, one NER mismatch message, the identifier locale rule (C1 to C10). Builds after the hot `run/` lanes (RESULT, F29 C1, RUN-STREAM C1) merge and before REL-GATE. Report: `C:docs/records/2026-11-12-duplication-census/REMEDIATION.md` | engine, CLI | NOT STARTED | none | 24zd; rows 62, 63a and 66 for C1, C2, C5 |

**D. Scan (SCAN-MULTI and the scan follow-ons)**

SCAN-MULTI plan: `E:docs/plans/2026-11-05-scan-multi-fk-discovery.md` on engine branch
`plan/scan-multi` `9b7cd9ab`. Dennis GO-WITH-FIXES; in a fix round. No FK inference in V1 (users
declare relationships; value-based FK discovery is parked for V2). Columns with no PII default to
`redact` in the starter YAML.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 25 | SCAN-MULTI S1a-engine: `scan_sources` and `scan-set/v1` (~470 lines) | engine | MERGED (engine #414, `046887e9`, 2026-11-09); in engine 0.20.0, which the CLI pins since CLI #164 | `plan/scan-multi` | plan GO |
| 26 | SCAN-MULTI S1b-engine: declared-relationship integrity facts (~480 lines) | engine | MERGED (engine #422, `368abe0e`, 2026-11-09); in engine 0.20.0, which the CLI pins since CLI #164 | `plan/scan-multi` | S1a types; same release as S1a |
| 27 | SCAN-MULTI S1c-cli: `decoy scan` over many tables (~690 lines) | CLI | IN PROGRESS. Plan passed 2026-11-06 (owner Q7-Q8 recommended). S1a and S1b are in engine 0.20.0, which the CLI pins since CLI #164. S1c.1 MERGED (CLI #166, `f32834bb`, 2026-11-10): `decoy scan` takes several files and writes one value-free scan-set core through the engine's `scan_sources`; saved scans load through one reader, `load_scan_set`; CSV scans need `--has-header` or `--no-header`. Next: S1c.2 (`--config`, `--table` on scan, `--column-names-file`, `--skip-integrity`, the integrity block), which waits on CONFIG-EXPLICIT E2 and C1 | `plan/scan-multi` | S1a and S1b release and repin; CLI-DIALECT; CONFIG-EXPLICIT for `--column-names-file` |
| 28 | SCAN-MULTI S3-engine: `starter_config` and `scan_baseline` (~560 lines) | engine | Plan passed 2026-11-06 (owner Q7-Q8 recommended). S1a is in engine 0.20.0; waits on the rest of CONFIG-EXPLICIT E2 (E2c, E2d, E2b-r, E2b-s), then its own engine release | `plan/scan-multi` | S1a; CONFIG-EXPLICIT |
| 29 | SCAN-MULTI S3-cli: `--emit-config` and `--compare` (~720 lines including moved code) | CLI | Plan passed 2026-11-06 (owner Q7-Q8 recommended). Waits on LIB L2 and the S3-engine release and repin; SCAN-MULTI S1c.1 is in review as CLI PR #166 | `plan/scan-multi` | LIB L2 (in place of S1d); S3-engine release and repin; CLI-DIALECT |
| 30 | SCAN-LIB: scan snapshot library (`scan-set/v1` under `.decoy/`); the YAML references a snapshot as its baseline and the run hashes it into evidence | engine, CLI | mostly delivered by S1a (`scan-set/v1`), LIB L2 (snapshots in the library) and S3 (`scan_baseline`); the run-evidence hash is the remainder; confirm at their plan GO | none | S1a, L2, S3-engine |
| 31 | DIST-INTEGRITY: opt-in pre-scan distribution capture plus a post-scan check within n%; a breach blocks in strict mode | engine, CLI | NOT STARTED | none | SCAN-LIB, POSTSCAN-STREAM |
| 32 | DRIFT: opt-in pre-scan drift check at run start against a SCAN-LIB baseline (`on_drift: warn` or `fail`) | engine, CLI | NOT STARTED | none | SCAN-LIB |
| 32a | SCAN-ML: optional ML in scans, set per pipeline (owner 2026-11-06). Default is regex only. The lgbm column classifier ships in every install (off until enabled); spaCy and its NER model are opt-in, installed by the setup step or a model-install command that also takes a copied model file for offline hosts. Pipeline config picks the detectors for the pre-scan and the post-scan separately (regex, classifier, NER, or both models). The classifier only suggests a type per column; the user confirms. NER post-scan findings warn by default; fail is opt-in. Logs, the scan report and the run result always name what ran, what was scanned, and each model and version. Folds in NER-CLICK (the `ner` extra misses `click`, so spaCy cannot load; add it plus a CI leg that installs `ner` alone) | engine, CLI | M0 (NER-CLICK) MERGED (engine #396). M1 (config, model status, loading; NER on free-text columns only, `NER_MIN_RATE` 0.211, owner 2026-11-07) MERGED (engine #405, `38951412`, 2026-11-08). Plan: branch `plan/scan-ml` (Revision 6, Codex GO) | none | SCAN-MULTI S3; shares the setup step with RUN-STREAM (63a) |
| 32b | INIT-WIZARD: `decoy init` becomes a guided wizard (owner 2026-11-06: V1, was post-V1 spec #73). It scans the source with the selected detectors (SCAN-ML), scaffolds the pipeline YAML, then walks the user section by section and column by column to confirm or reject each suggestion. After a run, post-scan findings are shown the same way to confirm or reject | CLI | BUILDING; spec v3 (#119); Phase 1a plan `docs/plans/2026-11-08-init-wizard-phase-1a.md` MERGED (#120, Dennis GO r2, Codex GO). Engine part E3 (`keyed_columns_for_config`) MERGED (engine #407). E1 and the CLI slices wait on SCAN-MULTI S3-engine and S3a.1 (plan section 2) | none | SCAN-ML; SCAN-MULTI S3 `starter_config` |
| 32c | SCAN-ML-MD: make `en_core_web_md` the default NER model, with its own `NER_MIN_RATE` set by the owner's Q7 rule (measured 0.087 against the small model's 0.211; owner 2026-11-07). On the frozen corpus and the Synthea healthcare sample, md flags notes columns whose names appear in 1 cell in 4 or 1 in 5, which the small model misses, and drops the small model's 3 false flags on clinical description columns (drug and vaccine names, lab terms). Costs a larger pinned wheel (`NER_MODEL_WHEELS` hash) and more location hits on organization names. The slice re-measures on the frozen corpora plus a clinical-vocabulary negative set before setting the constant | engine | NOT STARTED; evidence in vault `handoffs/phase1/scanml-ner-model-comparison-2026-11-07.md`; needs a plan | none | SCAN-ML M1 merged |

**E. Local record library (LIB)**

LIB plan: `C:docs/plans/2026-11-05-local-record-library.md` on CLI branch `plan/local-record-library`
`6b50e72` (revision 2 records the owner answers). Dennis GO-WITH-FIXES; in a fix round. Four
retention classes under one project root `.decoy/`; `decoy run` writes records by default
(`--no-library` turns it off).

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 33 | L1a-engine: records module (~520 lines) | engine | MERGED 2026-11-10 (last slice L1a, engine #444). L0.1 protected directory allocator MERGED (engine #403, `45553d7e`); L0.2 issued scratch root for run row dirs MERGED (engine #411, `942dae2d`); L1a MERGED (engine #444, `35370165`, 2026-11-10): `decoy_engine.records` with the `decoy-record/v1` envelope, the record kind registry and the value-free codec; registry 1.20.0 adds seven record and library reasons. L1a is in engine 0.20.0, which the CLI pins since CLI #164 (rule 5.2.5 met). The CLI halves L1b.2 and L1b.3 are row 34; plan passed 2026-11-06 | `plan/local-record-library` | plan GO |
| 34 | L1b-cli: store, atomic writes, refs, scratch (~700 lines); Linux, macOS and Windows lanes | CLI | L1b.1 shared atomic writer MERGED (#85, `c16a5fa`); L1b.2 and L1b.3 waiting | same | L1a release and repin; WIN-RUNNER |
| 35 | L1c-cli: index, fsck, degraded mode (~560 lines); three OS lanes | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L1b |
| 36 | L2-cli: scan snapshots on the library (~380 lines; replaces SCAN-MULTI S1d) | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L1c; SCAN-MULTI S1c |
| 37 | L3a-cli: evidence and run-result records (~520 lines) | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L1c; RESULT for the run-result half |
| 38 | L3b-cli: sample-run records and scratch lifecycle (~450 lines); three OS lanes | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L1c; SAMPLE |
| 39 | L4a-cli: library commands, first part (`list`, `show`, `diff`, `ref`, `export`) | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L1c (L3a for run-result `diff`) |
| 40 | L4b-cli: library commands, second part (`prune`, `clean`, reachability); three OS lanes | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L4a |
| 41 | L5a-cli: wire the engine `ProgressSink` into `decoy run` (~380 lines) | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L1c |
| 42 | L5b-cli: job logs (~500 lines); three OS lanes | CLI | Plan passed 2026-11-06; the CSV reader, REG-RENUMBER and L1a (engine 0.20.0, which the CLI pins since CLI #164) are in place; waits on the rows in After | same | L5a, L3a |

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
| 55 | H-1 E8: `execution/` root restructure (93 modules) | engine | DEFERRED until after CLI V1 (owner H-1 Q3, 2026-11-08) | none | an engine release and the repins |
| 56 | STORM rename, CLI half: re-cut so CLI C0 vendors `storm_slice_measure.py`, `storm_inventory.py`, `slices-cli.json` and drops the platform S2c dependency; CLI V1 ships the new names | CLI | NOT STARTED; re-cut plan needed (owner OQ-2 = B1) | from `P:plan/storm-rename-recut` `dfe7cc6a` | R-c repin |
| 95 | RUN-SPLIT: split `C:src/decoy/cli/run.py` into the `C:src/decoy/cli/run/` package, behavior unchanged, so the `run.py` rows build in parallel lanes (owner 2026-11-10). Closes no row | CLI | DONE. MERGED (CLI #179, `ccddb1f6`, 2026-11-10): `C:src/decoy/cli/run.py` became the `C:src/decoy/cli/run/` package with behavior unchanged; a layout sentry keeps `__init__.py` thin, so the `run/` module lanes in rule 5.2.2 are open | `C:docs/plans/2026-11-10-run-split.md` | CLI #176 (merged) |

**G. Phase 1 engine and CLI: trustworthy local run**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 57 | SUB-RUN: subset inside a pipeline run (`run_subset` inside `run_pipeline`); decide on the Parquet-only rule for relationship tables | engine, CLI | IN PROGRESS. Plan `E:plan/sub-run` (`2026-11-06-sub-run.md`), 3 slices. E1 MERGED (engine #515, `12bd94bf`, 2026-11-12): typed subset requests and one input seam. E2 open as engine #531 (`feat/sub-run-e2`): apply a subset block inside `run_pipeline`. C1 (CLI half) not started; it follows the engine release that carries E2 | `E:plan/sub-run` `a31ef5cb` | SUB-STOP; CLI half after its release |
| 58 | F25: protected scratch, quotas, orphan recovery | engine | building; S1a-0 (owner bits on stage creators under any umask) MERGED (engine #416, `809c2218`, 2026-11-09); plan Codex r7 GO | `E:plan/f25-4c-consumer-capabilities` `53950b27`; `E:feat/f25-protected-scratch` `4c901d38` | none |
| 59 | F22: atomic and idempotent publication | engine | plan rev 11 (V1 scope, owner 2026-11-11) Codex GO, 0 V1; nine V1 build slices, Windows arm w1 after the build; plan docs PR to open | `E:plan/f22-v1-scope` `9e52c6e4` | F25 |
| 60 | POSTSCAN-STREAM: post-scan integrity streams chunk by chunk on every route, with output PK and FK checks when keys are declared | engine | IN PROGRESS. Plan `E:plan/postscan-stream` (`2026-11-12-postscan-stream.md`), amended 2026-11-12, 14 slices. MERGED: PS-1 (engine #517, `105291d8`, 2026-11-12): key facts and batch inputs; PS-5 (engine #525, `c38f17cd`, 2026-11-12): exact column facts over batches. Open PRs: PS-3 (engine #524), PS-2a (engine #526), PS-2b0 (engine #528). Not started: PS-2b, PS-4 and PS-6 to PS-12 | `E:plan/postscan-stream` `b16af00b` | before CLI delivery makes post-scan blocking |
| 61 | CLI delivery (DELIV engine and CLI half): stage then deliver, strict and best-effort, local single-root rule, chunked path (G4) through the same sink; blocks CLI V1 (Q22) | engine, CLI | IN PROGRESS. Plan `E:plan/deliv` (`2026-11-12-deliv.md`), 14 slices. MERGED: E1a (engine #519, `a8c6af73`, 2026-11-12): delivery config and `plan_delivery`; CR (CLI #223, `cf20450a`, 2026-11-12): `decoy run --chunked` refuses `post_scan.integrity: true`. No other slice has a PR. Not started: E1b, E2a, E2b, REL, C0, C1, C2p, C2a, C2b, C3, C4, C5 | `E:plan/deliv` `220e1893` | F22, POSTSCAN-STREAM; CLI half after R-d |
| 61a | ATOMIC-CHUNKED: a `decoy run --chunked` that fails after its first chunk can leave a partial target, because the chunked writer is not atomic. Found in CLI-DIALECT Part C review. Not a leak. Fold it into F22 and CLI delivery (row 59 and this row), or do it right after them. Pinned by the strict xfail `tests/e2e/test_source_csv_dialect.py::test_chunked_failure_after_chunk_one_writes_no_target`, which the fix turns green (remove the mark then) | CLI, engine | DONE 2026-11-07: ATOMIC-OUTPUT (#105) stages the chunked writer too; the xfail mark is removed and the test passes | `p05-atomic-output-build-handoff.md` | F22; CLI delivery |
| 62 | RESULT: run result document, exit 6, capacity widening (in F29 C1) | engine, CLI | IN PROGRESS. Engine E1 MERGED (engine #397, `4c6ca215`, 2026-11-07): the `decoy-run-result/v1` model and `derive_outcome`. Remainder plan `C:plan/result-remainder` (`2026-11-12-result-remainder.md`), 13 slices, passed its gate 2026-11-12 (Codex GO); none built and no PR open. Startable now: C-EXIT, then C-REASON (CLI); E2a and E-CAP (engine). C-DOC1 and DELIV C2a wait until the DELIV plan carries the shared writer order | `C:plan/result-remainder` `a2faa2a`; E1 from `E:plan/f29-errors-progress-remainder` | DELIV best-effort for exit 6; CLI half after R-d |
| 63 | SAMPLE CLI half: `decoy run --sample N` through the subset; output to scratch, never to targets; same behavior on delimited, CSV, fixed-width and Parquet; blocks CLI V1 (Q24) | engine, CLI | IN PROGRESS. Plan `E:plan/sample` (`2026-11-12-sample.md`), amended 2026-11-12, 8 slices. SC0 MERGED (CLI #225, `ae58f682`, 2026-11-12): `--rows` refuses a run with quarantine on, and the quarantine path is passed explicitly. SE1 open as engine #527: sample request with head seeds and upward closure. Not started: SE2, SE3a, SE3b, SC1, SC2, SC3 | `E:plan/sample` `9152969b` | SUB-RUN; CLI half after R-d |
| 63a | RUN-STREAM: one fast run path. Plain `decoy run` streams large sources from disk by itself when the config can be processed in pieces; relationship jobs larger than memory use the out-of-core (DuckDB) route; `--chunked` becomes a strict switch (must stream, fail with a clear reason if the config cannot) on the same code path. Resources (owner 2026-11-06): Decoy settings hold max memory and max threads (CPU), set in the CLI setup step so each box and job type can be configured, with per-run flag and config overrides; defaults use the machine (all cores, multithreaded native and DuckDB paths, a memory share chosen for speed with a safety margin) instead of today's one native thread and 25% of RAM; the run summary says which route ran and why. Goal: Decoy runs as fast as the box allows | engine, CLI | IN PROGRESS. E2 MERGED (engine #437, `35719f55`, 2026-11-09): a CSV backend for the lazy source, read in chunks with file identity checks. E1a MERGED (engine #439, `fbc42f14`, 2026-11-09): `run_pipeline(execution_mode="stream")` must stream or fails with `runtime.streaming_unavailable` (registry 1.18.0). E1b MERGED (engine #442, `97a1cbbd`, 2026-11-10): `decoy_engine.detect_usable_cpus` (cgroup-aware usable cores), `run_pipeline(out_of_core_threads=...)` caps the DuckDB threads of the out-of-core route, `resolve_conservative_ooc_budget_bytes` (25% of the memory ceiling), registry 1.21.0 (`runtime.cpu_detection_failed`); in engine 0.20.0, which the CLI pins since CLI #164, and its CLI half C3 MERGED (CLI #165, `a14ed8ca`, 2026-11-10): `decoy run --max-memory` and `--threads`, `DECOY_MAX_MEMORY` and `DECOY_THREADS`, and `$DECOY_HOME/settings.json` written by a new `decoy setup` step, each key resolved flag, then environment, then file, then the engine's `auto`; `decoy doctor` shows each value and its source; `--chunked` ignores them until C2. E3 MERGED (engine #459, `fad62a69`, 2026-11-10): `route_summary(quality_metrics)` says which route ran and why, the native status, and the thread and memory caps the route applied; a configured cap without evidence is never shown as applied. In engine `v0.21.0` (#466); later slices to come (plan `plan/run-stream`, `docs/plans/2026-11-08-run-stream.md`). Owner 2026-11-06: V1; plan first measures how far plain `decoy run` already streams Parquet and CSV, and the speedup from threads on the GCP VMs and the Mac | none | SUB-RUN (same run path) |
| 64 | CLI-CLOUD: S3 and GCS in the CLI through the DELIV cloud run prefix and conditional pointer | CLI | NOT STARTED; owner 2026-11-06: CLI V1 (UX map Q6 closed). Plan `E:plan/cli-cloud` (`2026-11-12-cli-cloud.md`), 12 slices (EC0 to EC5, REL-C, CC1 to CC5): Dennis round 2 GO-WITH-FIXES, fixes returned at `2b560b90`. Nothing built and no PR open | `E:plan/cli-cloud` `2b560b90` | CLI delivery |
| 64b | CLI-DB-SRC: PostgreSQL as a pipeline source (`type: postgres` with a value-free connection reference, a table list and the CONFIG-EXPLICIT column rules) through the engine `postgres_snapshot` primitive; needs a Postgres CI lane (CI-P2 markers, unparked for the engine and CLI) | engine, CLI | NOT STARTED; owner 2026-11-06: CLI V1 | CONFIG-EXPLICIT, CLI-IO | CLI delivery |
| 65 | F31: shared safe-output and redaction (remaining build slices) | engine, CLI | DONE for CLI V1 (owner 2026-11-12): nothing left to build. E0a MERGED (engine #368, `b4c25aa5`), E0c MERGED (engine #377, `5c04ae6d`). E0b and the platform slices move to Platform V1 (section 6.3). V2-LOG: the `decoy run` error text cap of 500 characters | `E:plan/f31-safe-output` `2340a45b` | none |
| 66 | F29 remainder: CLI consumers (C1, which carries RESULT) and the F31 hook | engine, CLI | C0 MERGED (engine #367) | `E:plan/f29-errors-progress-remainder` | none |
| 67 | F34 E3 and the F34 release | engine | PARTLY: E0, E1, E2 MERGED (engine #365, #370, #371) and released in `v0.19.0`. E3 MERGED (engine #497, `7fc12e7f`, 2026-11-12): `scan_canary_artifacts`, the public canary scan entry point, and report aggregation through `build_report`. E3 merged after the `v0.22.0` tag. Left: the F34 release, which is the next daily engine release (0.23.0) | `P:plan/f34-residual-canary-span` `785af293` | the next engine release; owner Q4 (2026-11-08) placed it in R-c, but R-c shipped as `v0.19.0` (engine #399) without E3 |
| 68 | F36: cross-column invariants (finish), entry slices, slice 4 registry | engine | plan rev 8 GO | `E:plan/f36-cross-column-invariants` `9ed7b47f` | F06 (merged) |
| 69 | F35: quality contracts, E1a onward (registry) | engine | plan rev 4 GO | `P:plan/f35-quality-contracts` `7a3471af` | registry order |
| 70 | F32 remainder: engine E1b to E3, CLI C0, C1, C1b | engine, CLI | plan Codex r5 GO, Dennis r4 GO-WITH-FIXES | `P:plan/f32-support-bundles` `39c2772c` | F32 E1 (row 15) |
| 71 | F30 CLI: C1b and the CLI repin to the F30 release | CLI | DONE 2026-11-12 (all slices merged): C1a MERGED (CLI #80); E1 MERGED (engine #369) and released in `v0.19.0`; the CLI repin that carries it is the 0.20.0 repin (CLI #164), and the CLI now pins 0.22.0 (CLI #184), so no repin is left; C1b MERGED (CLI #221, `75d39ec9`, 2026-11-12): `decoy run --otel-endpoint` (or `DECOY_OTEL_ENDPOINT`) with the `decoy-cli[otel]` extra exports one `decoy.run` trace with the engine's phase spans and flushes on every exit path within 2 seconds. Known limit: the engine's `--chunked` route emits no phase events, so a chunked run exports the root span only | `P:plan/f30-telemetry` `4b385672` | F30 release |
| 72 | F33 CLI verifier and engine signature envelope | engine, CLI | plan in review: rev 9 (V1 scope E1a, E1b, C1a, C1b; owner 2026-11-11) | `P:plan/f33-v1-scope` `bba8b625`; engine PR #335 (OPEN) | plan review |
| 73 | F13 slices 3b and 5 | engine, CLI | MERGED 2026-11-11 (slice 5-v1, the only V1 build left under plan rev 5.1 section 0; slice 3b no longer exists, its pin bump is the platform repin). CLI #204 (`ac0cb686`): one test pins that a `vault://` mask-secret reference is refused with `secret_provider_unknown` and constant text on `run`, `tokenize`, `unmask`, `report vault` and `decoy.mask()`, repeats nothing from the reference and writes no file; closeout record `docs/records/2026-11-11-f13-5v1-closeout.md`. Engine #487 (`c96e2855`): a Consumers section in `docs/security/secret-providers.md`. The platform halves (3a, slice 5 parity, F-6) are parked with Platform V1 (section 6); the live Vault tests moved to row 83; cut cases are listed in the V2 corrective backlog | `E:plan/f13-v1-scope` `872b05f7` | none |
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
| 85 | F23 resume, CLI half: `decoy run --resume RUN_DIR`, table-level: tables that finished are kept, the failed table runs again from its start (owner UX map Q12, 2026-11-08) and the engine checkpoint store | engine, CLI | NOT STARTED | none | F22, CLI delivery |

**I. Phase 3 engine and CLI: connected safe-copy**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 86 | F01: PostgreSQL application-ready write target (staging, constraint, index and sequence restore, atomic publish) and the type-mapping report | engine, CLI | NOT STARTED; owner 2026-11-06: CLI V1 | none | Phase 2 rows; F22 |
| 87 | F02: SFTP, cloud scan, subset against cloud; retry executor; content digest on `WriteResult` | engine, CLI | NOT STARTED | none | CLI-CLOUD; F22 adapter |
| 88 | F44 CLI half: signed bundles, `decoy upgrade` preflight, rollback and offline signature path, release-time SBOM | engine, CLI | SBOM generators MERGED (engine #355, CLI #75; polish #359). Key custody decided (owner 2026-11-12): a GitHub Environment secret (`native-release`) with a required approver, plus an offline backup; creating the key and the Environment remain owner tasks | `C:docs/plans/2026-10-22-cli-distribution-and-packaging-spec.md` | B-2 (merged); R1-c key before the first signed bundle |

**J. Release**

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 89 | WIN-FEAS: Windows for the CLI and engine (private file ACLs instead of 0600, atomic replace with open files, file-access path handling, installer and signing); a blocker goes back to the owner | engine, CLI | NOT STARTED | none | before CLI-REL; LIB L1b gives the first evidence |
| 90 | REL-PKG: packaging. Signed per-platform bundles with a managed runtime, Ed25519 signer and key custody, SHA-256 manifest, verify before extract, install script, offline archive; native companion wheels (engine #353 workflow, never run); NOTICE, SBOM, `--version` (G2) | engine, CLI | B-2 MERGED (CLI #66, #67; engine #353). Key custody decided (owner 2026-11-12): a GitHub Environment secret (`native-release`) with a required approver, plus an offline backup. Owner tasks open: create the signing key and the `native-release` Environment, `native-v*` tag rule, qemu SHA pin | packaging spec above | F44 CLI half (row 88); WIN-FEAS for Windows |
| 90a | REL-IMAGE: official container image for pipelines (owner 2026-11-07: ship the download plus an official image; a GitHub Action, Helm chart and Terraform wait until after V1). Built on each release from the same signed Linux bundle (x86_64 and aarch64), signed and version-pinned by digest; a slim default tag plus a `-ner` tag with the NER model included; runs as a non-root user; recipes for GitHub Actions, GitLab CI and a Kubernetes job in the public docs. Registry and pull access (owner 2026-11-08): a public image that refuses to run without a valid license | CLI | NOT STARTED; needs a plan | none | REL-PKG (row 90); SCAN-ML model install (row 32a) for the `-ner` tag |
| 91 | REL-WEB: website download page on decoy-web, update-check endpoint with its privacy contract (no data, no identifiers, no telemetry), `/proof` synced (B-3) | web | NOT STARTED | decoy-web | REL-PKG |
| 92 | REL-DOCS: public CLI docs (Fumadocs at decoy.dev/docs, decoy-web PR #18) with the P0 pages from the CLI doc audit, install and upgrade docs, release notes, security contact; D-5 launch-gate flip | web, CLI | docs held draft | decoy-web PR #18 | the commands they document |
| 92a | CLI-QA-CHECKLIST: a CLI V1 QA checklist beside the engine one (`E:docs/qa/`, on engine branch `claude/sharp-cori-um7k6i`): commands, exit codes, project layout, records, install. Owner (2026-11-11): the checklists are used after the V1 build, and finished feature groups are marked ready for QA. Results go to a dated record in `docs/records/`; a failed check becomes a row | CLI | NOT STARTED | none | the V1 build rows |
| 93 | REL-GATE: R1 gates. D-4 launch engine freeze, R1-c signing key and license values (owner and counsel), versioning freeze (exit codes including 6, result schema, YAML schema, reason registry), canonical release smoke with recorded runs, a filled release-readiness instance, claims and license checkpoint. Install and license wording: the engine says `pip install` and Apache-2.0 (`E:pyproject.toml`, `E:README.md`) while `C:docs/install.md` says signed bundle and FSL-1.1-ALv2 (engine QA checklist fact-check 2026-11-11 (Codex, engine branch `claude/sharp-cori-um7k6i`)); R1-c settles the license and REL-DOCS (row 92) makes both repos say the same | engine, CLI, web | NOT STARTED. Owner 2026-11-12: D-4 engine freeze is the last daily engine release after build-complete on 2026-12-04; launch version `1.0.0`; customer releases monthly plus security fixes; macOS Intel unsupported in V1. Still open with the owner and counsel: the licensor entity and a contributor license agreement (the license is FSL-1.1-ALv2) | [roadmap/release-gates.md](roadmap/release-gates.md) | every row above |
| 94 | CLI-REL: the CLI V1 release. Final engine release and repin, publication to the download host, smoke install from the published artifact on each supported platform (Linux x86_64 and aarch64, macOS arm64, Windows x86_64 subject to WIN-FEAS) | engine, CLI, web | NOT STARTED. Download host decided (owner 2026-11-12): a static site plus CDN on the website's host | none | rows 89 to 93 |

The track has 94 rows. Rows 43 to 45 are merged and kept so the H-1 sequence reads whole; the
other 91 are open (some carry merged earlier parts, named in their State). Merged groundwork that is
not a row is in 5.7.

### 5.4 Row detail

Detail for each row (sources, FRAME findings, history) is in
[roadmap/row-detail.md](roadmap/row-detail.md).

### 5.5 CLI-REL scope (rows 89 to 94)

Source: `C:docs/plans/2026-10-22-cli-distribution-and-packaging-spec.md`.

- The final engine release and CLI repin.
- Signed per-platform bundles and the installer, published to the download host, then a smoke install
  from the published artifact on each supported platform.
- The official container image (row 90a), built from the signed Linux bundle, with a smoke run from
  the published image.
- The update-check endpoint and its privacy contract; the F30 opt-in statement.
- Platform matrix: Linux x86_64 and aarch64, macOS arm64, Windows x86_64 subject to WIN-FEAS (owner
  OQ-4). This supersedes the F22 "Linux and macOS only" note.
- Native companion wheels through the engine native-release workflow and the B-2 owner tasks.
- Versioning freeze at V1: exit codes (including 6), the result document schema, the YAML schema, the
  reason registry. Exit 6 is planned, not shipped: DELIV slice C3 (row 61) adds `EXIT_PARTIAL = 6`
  for a best-effort run that delivers some tables and drops others.
- CLI `--version` (literal `0.1.0` today, G2), CLI NOTICE and SBOM, security contact, release notes.
- Public docs, download page, install and upgrade docs.
- License: FSL-1.1-ALv2 for the engine, native companion and CLI (owner decision 2026-11-10,
  replacing BUSL-1.1 on the CLI and Apache-2.0 on the engine); counsel confirms the licensor entity
  and a contributor license agreement in R1-c. Plain-English terms: [LICENSING.md](../LICENSING.md).
- Production-readiness checks.

### 5.6 Open questions for the owner (CLI V1)

- First-user QA (2026-11-08, [report](records/2026-11-08-cli-qa-first-user.md)), answered by the owner
  the same day with the recommended options: scan values redacted by default (row 24c); gate catches
  run-time config errors with exit 1 (row 24b); `shuffle` must be deterministic (row 24d); QA bugs are
  V1 (row 24e). The QA wizard asks (data-aware presets, multi-table, color, `--no-input`) go to
  INIT-WIZARD (row 32b). Suggested new commands (`secret generate`, `ci init`, `subset init`,
  `report summary`, `run --dry-run`, help panels, `relationships detect`) are V1-nice-to-have,
  triaged after the critical path; FK detection across files is SCAN-MULTI. The uncovered-column
  finding is CONFIG-EXPLICIT E2 (row 22, owner rule 2026-11-05).

- The other open H-1 questions (Q3 answered: after CLI V1).
- Phase 1 tracks questions still open from `PHASE1-TRACKS.md`: Q9 (fate of `feat/f25-protected-scratch`;
  recommendation: keep it as the F25 build base) and Q11 (F36-P timing; recommendation: with the
  platform, after CLI V1). Q5 answered 2026-11-08: F35 E1a before F32 E1b.
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
suite repair (#383); CI-E1 (#388); SUB-STOP (#389); CI-X shared shell-parsing core (#390, ledger
#391); CLI-DIALECT Part E CSV reader (#392); ENGINE-PAR P1 stored failing-id baseline (#393);
CI-E1s lock advisories (#394); merge gate on any `decoy-gate` runner, no docs path filter (#395);
SCAN-ML M0 ner extra and model pin (#396); RESULT E1 `decoy-run-result/v1` (#397); REG-RENUMBER
(#398); R-c `v0.19.0` (#399); init-wizard strategy catalog (#400); ENGINE-PAR P2 parallel gate (#402).

CLI: B-1 tokenize and local vault (#64); B-2 CLI-LAUNCH packaging (#66, #67); R1-a `resolve_substrate`
fix (#71); worker bootstrap (#70); F43 (#69); SBOM generator (#75); repins to 0.17.0 and 0.18.0 (#76,
#79); F13 4a/4b `--mask-secret` (#78); F30 C1a OTel exporter (#80); X0a ratchet (#81, #82); L1b.1 atomic
writer (#85); VALIDATE-ALWAYS P1 (#88); CI-L1 (#93, ledger #94, #95); CLI-DIALECT Part C and repin to
0.19.0 (#99); CLI-FMT (#101 to #103); ATOMIC-OUTPUT (#105); VALIDATE-ALWAYS P2 (#107); unfolded run
errors (#109); CLI-MAC-TESTS S1 (#110), S2 (#112); init wizard spec v2 and review handoff (#111, #73).

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
   (`plan/scheduler-state-and-direction` `4fff389e`). The dormant S3A, S3B, cgroup, lease and S13 to
   S17 code is not yet active; it is to be finished and activated, never deleted (owner, 2026-11-02).
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
| F31 E0b and the platform slices (moved from CLI row 65, owner 2026-11-12) | F31 | NOT STARTED; plan `E:plan/f31-safe-output` `2340a45b` | on restart |

**Live platform bugs recorded for the restart** (not exposed; the platform is unreleased): SSO can
resolve to the wrong account and does not bind the issuer (X3a fixes it); OUT-PATH.

**Also parked:** X4a part B and X4b call-site conversion; the approved git history scrub of business
docs (run at a quiet point, never mid-stack); the V1 role set (user PATCH accepts only admin or user);
the `sso` license gate is defined but not enforced; the dev license key defaults to the business tier;
flaky tests on platform main (V2 backlog); UX map Q19, Q21, Q25; X0a-h H3 and H5. Platform main
known failures live in the stored baseline `baselines/decoy-platform-main.json` in the vault.

---

## 7. Linked roadmap documents

Each is under about 800 lines and is edited in place; the index above holds the current order and
state.

| Document | What it holds |
|---|---|
| [roadmap/row-detail.md](roadmap/row-detail.md) | detail, sources and FRAME findings for the track rows |
| [roadmap/phase-principles.md](roadmap/phase-principles.md) | the phase pillars (the acceptance lens at FRAME) |
| [roadmap/release-gates.md](roadmap/release-gates.md) | R1 (CLI V1) and R2 (Platform V1) completion gates |
| [roadmap/findings-register.md](roadmap/findings-register.md) | review notes, after-V1 list, reconciliation findings G1 to G24 |
| [roadmap/feature-checklist.md](roadmap/feature-checklist.md) | the 29 Council-V1 features and where each lands |
| [roadmap/decisions.md](roadmap/decisions.md) | dated owner decisions |
| [roadmap/branch-register.md](roadmap/branch-register.md) | engine and CLI branches with no row, and their disposition |
| [roadmap/out-of-scope.md](roadmap/out-of-scope.md) | Council-V2 features, V2 rows, post-V1 items |
| [roadmap/v2-v3-expansion-candidates.md](roadmap/v2-v3-expansion-candidates.md) | V2 and V3 core expansion candidates (formats, masks, generators, documents, media); proposal, not scheduled |
| [roadmap/sources.md](roadmap/sources.md) | source documents |
| [RECENTLY-SHIPPED.md](RECENTLY-SHIPPED.md) | the shipped log; older entries in [archive/](archive/README.md) |

When a slice merges, update its row here and add it to the shipped log in the same change.
