# CLI-BASELINE: a stored failing-id baseline for the CLI gates

Status: plan (Revision 2)

Roadmap row 5b (`docs/ROADMAP.md`). Repo `louiskeep/decoy` (CLI). Measured on CLI `origin/main`
`b7009d1` (2026-11-08; Revision 1 used `a1d67ff`). Engine source: `origin/main` `b5b1ad16`.
Author: claudeworkerbee (Opus), 2026-11-08. Build handoff:
`10_Projects/decoy/handoffs/phase0.5/p05-cli-baseline-build-handoff.md` in the vault.

Rules consulted: `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`,
`testing.md`, `reuse-first.md`, `cross-cutting-concerns.md`, `scope-discipline.md`,
`architecture.md` (fan-out), `verification.md`, `workspace-and-vcs.md`, `documentation.md`.

Risk: R2. The slice changes the merge gate itself. A wrong comparison passes a broken branch
(false green) or blocks a good one, and the stored file is read by tooling outside this repo
(`~/bin/decoy-vm-t3`, `~/bin/decoy-vm-t3-promote`).

## 0. Revision 2 (Dennis round 1: NO-GO, 0 BLOCKER / 3 HIGH / 9 MEDIUM / 6 LOW)

Review: vault `10_Projects/decoy/handoffs/phase0.5/p05-cli-baseline-dennis-r1.md`. Orchestrator
answers: Q1 xdist later as CLI-PAR; Q2 yes, this slice owns bash 3.2 for `gates.sh`; Q3 done
(promote already maps `cli` to `decoy`). Ruling on H3: keep the CLI's "no step ran" behavior as
a named divergence and do not edit the read-only test file.

| Finding | Fix in this revision |
|---|---|
| H1 bot svg commit after every merge makes the stored file stale | CLI-only `GENERATED_UNREAD_GLOBS=('docs/diagrams/*.svg')`, treated like unread Markdown, "a test names it" still applied (section 4, AT-5 cells, mutation 6). Section 5 counts corrected (14 Markdown-only, 10 bot svg-only of 40). Section 8 relaxes promote's `merged` tree check by the same list |
| H2 legacy verdict change undeclared; mutation 16 unkillable | Declared as change C1 and C2 (sections 3, 4e). New AT-19 ports the engine's `branch_only_steps` cells; mutation 18 points at AT-19 |
| H3 port breaks the read-only `no step ran[tests]` cell; plain-route changes unlisted | Divergence D1 keeps the CLI behavior for a missing explicit path. Section 4f lists every plain-route difference, ported or not (D1 to D4) |
| M1 two mutation lists | One list, section 6a; the handoff points to it. AT-4 gains the selection cell |
| M2 substring guard is the weak one | Port `gates_sh_violations` and its seeded readers (AT-16); `gates.sh:135` moves to the `--import-origin` subcommand |
| M3 `tests/unit/scripts/__init__.py` breaks imports | Dropped (section 7) |
| M4 check-then-use window | Copy first, check the copy (D6); AT-18 gains the rewrite-between-check-and-copy cell |
| M5 ids with memory addresses | The write refuses them (`WRITE_REFUSED`, exit 1), AT-20, mutation 15 |
| M6 promote runs a reporter outside the repo | Reporter flag `--test-root DIR` (D7); AT-13 runs a reporter copied outside the repo; section 8 passes the flag |
| M7 carry overclaimed | Named as the accepted exception in 4a and section 8; promote's reader check extended to cli |
| M8 end-to-end write cannot work | Procedure rewritten (handoff, "End-to-end") |
| M9 thin bash 3.2 proof | `GATES_TEST_BASH` override in the harness; AT-1 to AT-20 run under `/bin/bash` 3.2 on the Mac (AT-14) |
| L1 walker list wrong | Section 5 corrected; `DOC_WALK_ROOTS=()` |
| L2 second hand-kept list | `DOC_WALK_GUARDS` derived from `SENTRY_PATHS` (D9) |
| L6 section 8 step 1 already done | Removed; noted as done |
| L3, L4, L5 | Section 11 follow-ups |

## 1. Goal and guarantee

Today a CLI merge test (T3) runs the full suite twice on the VM: once on the candidate and once
on `origin/main` (`decoy-vm-t3 ... legacy`, `gates.sh --baseline`), about 19 minutes each on a
4-core VM. `decoy-vm-t3 ... cli` cannot use `stored` mode, because the CLI `gates.sh` has no
`--baseline-file` (it exits 2 on an unknown flag).

Guarantee: after this slice the CLI `scripts/dev/gates.sh` can

1. store main's failing test ids once (`--write-baseline FILE`, whole suite, clean checkout of
   exactly `origin/main`), and
2. compare a branch against that file in one suite run (`--baseline-file FILE`), failing on any
   failing id that is not in the file, with the same refusal rules the engine uses: a stale
   file, a file from another run mode, a malformed file, a smaller suite than the branch can
   explain, more skips than the baseline, or pytest totals that disagree with the JUnit.

The stored file has the engine's format (`format_version` 1, same fields), so
`decoy-vm-t3-promote` and later tooling treat the three repos alike.

The script also becomes bash 3.2 safe (no `mapfile`, guarded array expansions), with the
engine's guard test, because the port rewrites the same lines (Q2, answered yes).

The legacy `--baseline` route takes the engine's verdict (fail only on branch-only steps) and
always keeps going. These are declared changes C1 and C2 (sections 3 and 4e), not side effects.

Non-goals:
- pytest-xdist for the CLI suite (section 9: later, as row CLI-PAR).
- Any plain-route change beyond `--full` and bash 3.2 (section 4f lists what is not ported).
- The macOS-only CLI test failures (row 5c, CLI-MAC-TESTS).
- Editing `~/bin/decoy-vm-t3` or `~/bin/decoy-vm-t3-promote` (orchestrator tooling; section 8
  lists the changes they need).
- A shared gates package across engine, CLI and platform (V2-LOG, section 11).

## 2. Established solutions

Search run (2026-11-08): the engine's own implementation; the platform's port; the web for
"pytest known failures baseline, compare new failures only".

- Engine ENGINE-PAR P1 (engine #393, `79f229d0`) and the run-mode fields of P2 (#402,
  `b5b1ad16`): `scripts/dev/gates.sh`, `_gates_report.py`, `_gates_baseline.py`, records
  `docs/records/2026-11-06-engine-par-p1-build.md` and `2026-11-07-engine-par-p2-build.md`,
  plan `docs/plans/2026-11-06-engine-par.md` on `plan/engine-par`. This is the design followed.
  It already passed Dennis and Codex, and its record lists 23 mutations that each went red.
- Platform `scripts/dev/gates.sh` (327 lines): an earlier port with `--baseline-file` and
  `--write-baseline` but without P1's stale refusal, strict model and run mode. Not followed:
  the orchestrator's T3 script still has to check staleness for it.
- [pytest-quarantine](https://github.com/EnergySage/pytest-quarantine) saves the failing ids to
  a file and marks them xfail on later runs, so only new failures fail the run. Not adopted: it
  changes test outcomes inside pytest (a quarantined test that starts failing differently stays
  hidden), adds a runtime dependency to the lock, and has no notion of a stale file or a run
  mode. The idea (a stored id list, new ids fail) is the same one the engine uses at the gate
  level instead.
- pytest's cache (`--lf`, `--ff`, [docs](https://docs.pytest.org/en/stable/cache.html)) reruns
  the last failures; it is not a stored, reviewed baseline of main.
- A JUnit-versus-committed-baseline compare script is a common shape in other projects
  (for example the nightly xfail-baseline diff in
  [ferro-hgvs](https://docs.rs/crate/ferro-hgvs/1.0.0/source/tests/python/test_diff_nightly_xfail_baseline.py)).
  The engine's reporter is this shape with stricter refusals.

Remaining custom code: the port, the CLI's repo configuration, and the divergences of section 4f.

## 3. Behavior

| Case | Before | After |
|---|---|---|
| `gates.sh --baseline tests` (legacy) without `--keep-going` | stops at the first failing step on each side | keeps going on both sides (C2; the verdict needs every step) |
| legacy verdict | exit 1 on any failing branch step, failures shared with main included (`scripts/dev/gates.sh:147`) | exit 1 only on a branch-only step: a step main passes, a crash or kill code, an unidentified failure, or more of an identified failure than main has; shared-only failures give exit 0 (C1, AT-19) |
| `gates.sh --write-baseline F tests` on a clean checkout of `origin/main` | exit 2, unknown flag | runs the whole suite once, writes `F`, prints `gates: wrote baseline F`; exit 1 when main has known failing ids, 0 when none |
| `--write-baseline` on a selection, a dirty tree, or a HEAD other than `origin/main` | exit 2, unknown flag | exit 2 before running, no file |
| `--write-baseline` where a failing id carries a memory address (`0x` and 6 or more hex digits) | exit 2, unknown flag | runs, refuses to write, names the id, exit 1 (D8, AT-20) |
| `gates.sh --keep-going --baseline-file F tests` on a branch | exit 2, unknown flag | one suite run; exit 1 on a failing id not in `F`; known ids alone give exit 0; ids in `F` that now pass are listed |
| `--baseline-file` on a selection | exit 2, unknown flag | exit 1: a compare needs a completed whole-suite run (AT-4) |
| `F` behind `origin/main` by a change to anything but Markdown or a generated, unread artifact | n/a | exit 2 before running, naming the changed path |
| `F` behind `origin/main` only by Markdown or `docs/diagrams/*.svg` that no test names, no doc walker reads, and no stored failing id is a doc-walk guard | n/a | accepted; the header says main moved only in such files (AT-5) |
| `F` for another repo, platform, worker count or test order; wrong types; unknown fields; `format_version` not 1 | n/a | exit 2 before running, saying why |
| `F` rewritten while the gate checks or runs | n/a | the gate copies `F` first and checks and reads only the copy (D6, AT-18) |
| branch collects fewer tests than `F` beyond the ids of test files it deleted | n/a | exit 1 |
| branch skips more tests than `F` | n/a | exit 1 |
| pytest's totals line disagrees with the JUnit failure count | n/a | exit 3 |
| `PYTEST_ADDOPTS` or `PYTEST_PLUGINS` set in the environment of a write or compare | narrows the run | ignored for the tests step |
| plain route: an explicit test path that does not exist | skipped; with no other step, "no step ran", exit 3 | unchanged (D1; the engine exits 2 here) |
| plain route: a code diff that selects no tests | tests step SKIP | unchanged (D2; the engine fails it) |
| `--full` | unknown flag | runs the whole suite (`tests`), as the engine's flag does |
| run on macOS `/bin/bash` 3.2 | `PYTEST_ARGS[@]: unbound variable` (line 83) or `mapfile: command not found` | works; same selection as bash 5 |
| `gates.sh --order-from` or `GATES_WORKERS` | unknown flag; variable ignored | unchanged: not supported (no xdist, no order hook); the header prints `workers: 1 (the CLI suite runs serial)` |

A stored file never changes test results: every test still runs and reports as it does today.
Only the gate's verdict reads the file.

## 4. Design notes

- One model of the stored file, `_gates_baseline.py` (ported): `load_baseline` is the only
  reader, and the writer serializes the same dataclass. `gates.sh` never parses JSON or JUnit
  and never runs inline Python; it calls reporter subcommands (`--check-stored`,
  `--suite-collected`, `--stored-failing-under`, `--verdict`, `--import-origin`, `--workers`,
  `--write-baseline`). Engine P1 arrived at this after Codex found coerced fields (`true` as a
  count).
- Repo facts live once, in the configuration block at the top of `gates.sh`: `REPO_NAME=decoy`,
  `SENTRY_PATHS`, `PYTEST_ARGS`, `NON_CODE_GLOBS`, `GENERATED_UNREAD_GLOBS`, `DOC_WALK_ROOTS`,
  the format and mypy SKIP switches. `DOC_WALK_GUARDS` is not a second list: it is set from
  `SENTRY_PATHS` (D9). `SENTRY_PATHS=(` and `PYTEST_ARGS=(` keep their one-entry-per-line shape,
  which `tests/sentry/test_sentry_manifest.py` parses.
- Generated, unread artifacts (H1). `.github/workflows/regen-diagrams.yml` commits
  `docs/diagrams/*.svg` to main as github-actions[bot] about a minute after every merge that
  touches `src/`. The staleness rule treats a path matching `GENERATED_UNREAD_GLOBS` like
  Markdown: harmless unless a file under `tests/` names it or it is under `DOC_WALK_ROOTS`.
  No test names `diagrams` or an svg today (grep on `b7009d1`). The engine has no such bot, so
  this list is CLI-only (D5).
- The reporter resolves a test's collected module against a test root. It is the repo root by
  default (`parents[2]` of the reporter); `--test-root DIR` overrides it, for a reporter copied
  outside the repo as `decoy-vm-t3-promote merged` does (D7, M6).
- The CLI port is a port, not a mirror. Each repo keeps its own copy; differences are listed
  in section 4f and in the build record. A shared package is a V2-LOG item.
- House style: single-purpose reporter subcommands, no flag arguments that switch behavior
  inside one function, comments that say why.
- Choke point: the gate verdict in a compare run is computed only by the reporter from the
  stored model and the JUnit. Guard: `gates_sh_violations` (ported from the engine's
  `tests/unit/scripts/test_gates_baseline_file.py`): every `python` call in `gates.sh` must run
  the reporter, `-m pytest` or `--version`; an inline `-c` program, a stdin or heredoc program,
  an aliased interpreter, or `jq` is refused, with the engine's eight seeded readers (AT-16).

## 4a. Invariants

- A compare run passes only if every failing id of the branch's whole-suite run is in the stored
  file, and the stored file describes the `origin/main` the branch is compared against (same
  commit, or a later one that differs only in Markdown or generated svg that no test reads).
- The stored file is only ever written from a whole-suite run on a clean checkout of exactly
  `origin/main`, and only read through one model that refuses anything it does not recognize.
- Accepted exception: `decoy-vm-t3-promote ... carry` (orchestrator tooling, after a merge
  checked by targeted tests only) moves `main_sha` across a code merge and keeps the old failing
  ids. Until the next real write, a branch that re-breaks an id main has since fixed is hidden.
  The orchestrator owns that trade; the gate cannot see it (section 8).
- A gate verdict never comes from a run that did not finish: no JUnit, zero cases, or a totals
  line that disagrees with the JUnit is a failure, never a pass.
- The content the gate checks is the content it reads: the stored file is copied before any
  check, and nothing after the copy opens the original.

## 4b. Class table

| # | Class | Applies how | Closing structure | Proof (sentry or test) | Mutation that must turn it red (section 6a) |
|---|---|---|---|---|---|
| 1 | Value-bearing output | the EVIDENCE block, stderr lines and the stored file carry test ids, paths and SHAs only; no test data | the reporter prints ids and counts from JUnit attributes, never captured output | AT-3 field list (no other keys); AT-7 unknown field refused | 1: failure text added to `failing` entries, AT-3 red |
| 2 | Cleanup missing on an exit path | the baseline worktree and the merge-base worktree under `$OUT` | one `cleanup` EXIT trap removes both on every exit (ported) | AT-8 deleted-ids cell leaves no worktree in `git worktree list`; AT-15 pin | 2: merge-base tree dropped from `cleanup`, AT-8 red |
| 3 | State machine and concurrency | N/A: one process, no shared state; two runs never share `$OUT` (`mktemp -d`) | `mktemp -d` per run | AT-15 pin | n/a |
| 4 | Route parity and silent fallback | four routes (section 4c): plain, legacy, write, compare; a compare must never fall back to legacy or to a selection | the compare refuses a selection (`WHOLE_SUITE`, `SUITE_OK`) and never adds the baseline tree | AT-1, AT-4 selection cell, AT-11 | 3: compare accepts a selection, AT-4 red |
| 5 | Referential integrity | N/A: no tables or keys; the only reference is `main_sha` to a commit, covered by class 8 | stale refusal | AT-5 (`main_sha` not in the repo) | n/a |
| 6 | Untrusted producer | the stored file and the JUnit come from another run (another host, an older tool, a reporter copied outside the repo); failing ids come from test parameters | `load_baseline` with exact types and `format_version`; JUnit counted and cross-checked against pytest's totals; `--test-root`; ids with memory addresses refused at write | AT-7, AT-10, AT-13, AT-20 | 10: bool as a count, AT-7 red; 13: totals check dropped, AT-10 red; 15: address check dropped, AT-20 red; 17: `--test-root` ignored, AT-13 red |
| 7 | Check then use (TOCTOU) | the stored file is read by the stale check, the model check and the verdict | copy first, check and read only the copy (D6) | AT-18 (rewrite before the copy would have run, and during the run) | 16: check `$BASEFILE` then copy, or read it again after the copy, AT-18 red |
| 8 | Weak tests and overclaimed evidence | the slice's whole point: a compare that passes without running the suite, or with fewer tests; a guard that a renamed import slips past | shrink, skip and totals rules; `no step ran` exit 3; allow-list guard on `gates.sh` | AT-8, AT-9, AT-10, AT-15, AT-16 | 11: shrink rule dropped, AT-8 red; 12: skip rule dropped, AT-9 red; 19: inline `python -c` JSON read in `gates.sh`, AT-16 red |
| 9 | Refactor drift | `gates.sh` is rewritten; the legacy and plain routes must change only as declared (C1, C2, D1 to D4) | characterization pins first (AT-15, AT-17); the declared legacy verdict pinned by AT-19 | AT-15, AT-17, AT-19 | 18: legacy verdict fails on shared failures, AT-19 red; 20: D1 dropped (missing explicit path exits 2), AT-15 red |
| 10 | Frozen contract drift | the stored file format shared with the engine and read by `decoy-vm-t3-promote`; the EVIDENCE header lines the orchestrator greps | the engine's `format_version` 1 model, ported unchanged; AT-13 pins the promote argv | AT-3, AT-13 | 4: `main_sha` renamed, AT-3 and AT-13 red |

## 4c. Enumerations

### Exit paths

- `gates.sh` exit 0: every branch step passed (plain), no branch-only step (legacy), no new id
  and every rule held (compare).
- exit 1: a failing step or id; a branch-only legacy step; a refused write after the run
  (`WRITE_REFUSED`: no completed whole suite, or a failing id with a memory address); a write on
  a main with known failures (still writes); a compare without a completed whole suite.
- exit 2: usage, missing venv or `origin/main`, a refused write before running, a stale, foreign
  or malformed stored file.
- exit 3: no complete EVIDENCE block, no step ran, totals disagree with the JUnit, the legacy
  verdict could not be computed.
- Every exit runs the EXIT trap that removes `$OUT/baseline-tree` and `$OUT/merge-base-tree`.
- `_gates_report.py` exits: 0, 1 (main, `scripts/dev/_gates_report.py:71` today), 4 (totals
  mismatch, ported), 64 (usage, ported).

### Routes

- Plain: `gates.sh [paths]` and `gates.sh --full` (today; `scripts/dev/_gates_report.py:71`
  prints the block).
- Legacy: `--baseline` (today; `tests/unit/test_dev_bootstrap_gates.py:163` pins the branch-only
  cell; AT-19 pins the declared verdict).
- Write: `--write-baseline FILE tests` (new).
- Compare: `--baseline-file FILE tests` (new).
- Direct reporter call from `decoy-vm-t3-promote merged`, outside this repo:
  `_gates_report.py OUT --whole-suite --write-baseline F --repo decoy --main-sha S --head-sha H
  --test-root DIR` (AT-13).

### FK shapes

N/A: the slice touches no data tables or foreign keys; it only reads JUnit files and one JSON file.

### Fields

The stored file (the ported `Baseline` model, engine `scripts/dev/_gates_baseline.py:48`):
- `format_version` (int, exactly 1), `repo` (str), `main_sha`, `head_sha` (str);
- `collected`, `skipped` (non-negative int, bool refused), `failing` (sorted list of str);
- `workers` (int, 1 in the CLI), `dist` (`no`), `platform` (str, for example `linux-x86_64`);
- `order` (`collection`), `order_seconds` (empty map), `file_seconds` (map of str to float).

### Output surfaces

- stdout: the EVIDENCE block (`tee`d to `$OUT/evidence`), today from
  `scripts/dev/_gates_report.py:64`.
- stderr: `gates: [label] step ...` progress, the 15-line tail of a failing step, every
  `gates: FAIL` and refusal line, `gates: wrote baseline FILE`.
- Files: the stored baseline (write only), `$OUT/stored-baseline.json` (the checked copy),
  `$OUT/*.log`, `*.xml`, `*.steps`, `meta`, `new-failing`, `shortfall`, `skip-increase`.
- Exit code (section 4c, exit paths).
- `CONTRIBUTING.md:40` to `:44` (the gates bullets).

## 4d. Reuse inventory

- Engine `scripts/dev/gates.sh`, `_gates_report.py`, `_gates_baseline.py` on `b5b1ad16`: ported.
- Engine `tests/unit/scripts/test_gates_baseline_file.py`, `_gates_harness.py`: ported (P1 cells,
  the run-mode cells, `gates_sh_violations` with its seeded readers; not the parallel cells of
  `test_gates_parallel.py`).
- Engine `tests/unit/scripts/test_dev_bootstrap_gates.py:153` to `:330`: the `branch_only_steps`
  cells and the keep-going cell, ported into AT-19 (not the `TESTS_REQUIRED` cell at `:297`,
  D2).
- Engine `tests/sentry/test_bash32_compat.py`: ported unchanged.
- CLI `scripts/dev/ratchet_check.py` and the sentry step: kept as is.
- CLI `tests/unit/test_dev_bootstrap_gates.py`: kept, pinned, read-only (AT-15).
- CLI `tests/sentry/test_sentry_manifest.py:24` (`SENTRIES`): one line for the new sentry.
- No new machinery beyond the port and the divergences of section 4f.

## 4e. Frozen contracts touched

- The stored baseline format (`format_version` 1): additive to the CLI (new file), identical to
  the engine's. Not changed.
- The `gates.sh` command line: additive (`--write-baseline`, `--baseline-file`, `--full`).
  Declared changes to existing meaning, both on the legacy route only:
  - C1: the legacy verdict fails only on branch-only steps (engine `gates.sh:457` to `:463`,
    `_gates_report.branch_only_steps`). Before, any failing branch step failed the gate. Effect:
    a branch that shares main's known failures and adds none now passes legacy, as it would pass
    a compare. AT-19.
  - C2: `--baseline` implies `--keep-going` (engine `gates.sh:93`), so both sides run every step
    and the verdict compares like with like.
  Every other flag, the default selection and the plain verdict keep their meaning (AT-15).
- The EVIDENCE header: additive (`workers:` and, in a compare, `baseline:` and `run mode:`
  lines). Existing lines unchanged, the `test paths:` wording included (AT-17).
- `decoy-ci/v1` and every user-facing CLI surface: not touched.

## 4f. Divergences from the engine scripts (all named; the build record repeats them)

| # | Engine behavior | CLI after this slice | Why |
|---|---|---|---|
| D1 | an explicit test path missing from the branch exits 2 ("explicit test path not found", engine `gates.sh:192`) | skipped as today; with nothing else run, "no step ran", exit 3 | orchestrator ruling on H3; `tests/unit/test_dev_bootstrap_gates.py:216` pins it and is read-only |
| D2 | `TESTS_REQUIRED`: a code diff that selects no tests fails the tests step | not ported: the step reports SKIP as today | plain-route change outside this slice; follow-up |
| D3 | selection label "SELECTION ONLY (...)" | today's "changed vs origin/main: N test file(s)" | AT-17 header pin; plain route unchanged |
| D4 | parallel pass, `--order-from`, `GATES_WORKERS`, order map, `licenses` step, `DECOY_GATE_VENV_STRICT`, `DECOY_LICENSE_STRICT`, `ruff --output-format concise` | absent; ruff, format, mypy and sentry command lines stay the CLI's | no xdist (section 9); the CLI has no license step and reads neither variable |
| D5 | stale rule exempts Markdown only | also `GENERATED_UNREAD_GLOBS` (`docs/diagrams/*.svg`) | the CLI's regen-diagrams bot (H1) |
| D6 | `--check-stored` and the stale check read `$BASEFILE`, then `cp` (engine `gates.sh:242` to `:250`) | copy to `$OUT/stored-baseline.json` first; every check and the verdict read the copy | closes the check-then-use window (M4); carry back to the engine |
| D7 | `TEST_ROOT = parents[2]` only | `--test-root DIR` overrides it | promote runs a copied reporter (M6); carry back to the engine |
| D8 | memory-address ids refused at collection (`tests/conftest.py:101`) | refused at write by the reporter | the CLI slice may not touch `tests/conftest.py` |
| D9 | `DOC_WALK_GUARDS` is its own list | `DOC_WALK_GUARDS` = `SENTRY_PATHS`; an entry matches an id whose file equals it or lies under it as a directory | one list (L2); the three named sentries under `tests/unit/` are covered |

## 5. The CLI-specific inputs (measured on `b7009d1`; re-measure at STEP ZERO)

- Commit mix of the last 40 first-parent commits on CLI main (diff to the first parent): 14
  touch only Markdown, 10 touch only `docs/diagrams/*.svg` (all github-actions[bot]), 16 touch
  code. Of the 24 docs-only moves, 23 keep a stored file usable under this plan's rules (one
  changed a plan doc that `tests/e2e/test_run_validate_always.py` names). Without
  `GENERATED_UNREAD_GLOBS` only 13 would. The bot commit lands about a minute after a merge
  (`8ac0f8d` at 01:20:27 UTC, `b7009d1` at 01:21:25 UTC).
- Tests that read Markdown name the basename literally (`README.md`, `cli-reference.md`,
  `ci-contracts.md`, `sbom.md`), so the "a test names it" rule covers them. The only test that
  walks `docs/` is `tests/sentry/test_baseline_registry.py:101`; it reads only json and toml
  and is a sentry, so it is a guard already. `DOC_WALK_ROOTS=()` for the CLI.
- `bash 3.2`: `gates.sh` has 11 bash 4 constructs (`mapfile` at :71, ten bare array
  expansions); `bootstrap.sh:43` has one bare array expansion; `lock.sh` and `lock_version.sh`
  have none. On the Mac's `/bin/bash` 3.2.57 the current script dies at line 83 on the empty
  `PYTEST_ARGS` (8 ids of `tests/unit/test_dev_bootstrap_gates.py` fail there today).
- No `pytest-xdist` in `requirements-dev.lock`; no `serial` marker; no collection-order hook in
  `tests/conftest.py`. No inherited test classes in `tests/` today (so D7 fixes a latent bug).
- `scripts/dev/` is outside `RUFF_PATHS=(src tests)` and outside `ci.yml`'s ruff job, so the new
  Python is linted by hand in this slice (follow-up L3).

## 6. Acceptance tests

Red first on the base unless marked "pin". All run in a scratch clone with seeded test files
(the engine's `_gates_harness.py` pattern), never against the real suite, except AT-15. The
harness runs `gates.sh` with `GATES_TEST_BASH` when set, else `bash` on the PATH.

| AT | Test | Red on base because |
|---|---|---|
| AT-1 | `--write-baseline` on a selection exits 2 and writes nothing | flag unknown |
| AT-2 | `--write-baseline` with HEAD not `origin/main`, or a dirty tree, exits 2 | flag unknown |
| AT-3 | `--write-baseline` on a clean `origin/main` with one seeded failing test writes a file with exactly the fields of section 4c (`format_version` 1, `repo` `decoy`, `workers` 1, `dist` `no`, `order` `collection`, `order_seconds` `{}`, sorted `failing` of bare ids), prints `gates: wrote baseline`, exits 1 | flag unknown |
| AT-4 | compare: a new failing id exits 1 and names it; only known ids exit 0; a known id that passes now is listed; a compare on a selection exits 1 (engine `test_baseline_file_fails_without_a_completed_whole_suite_run`) | flag unknown |
| AT-5 | stale: a code change on main after the stored sha exits 2 before running; a Markdown change no test names is accepted with the NOTE line; an svg change under `docs/diagrams/` no test names is accepted; a Markdown file a test names is stale; an svg a test names is stale; a change under a `DOC_WALK_ROOTS` directory is stale (seeded root); a stored failing id under a `SENTRY_PATHS` entry makes any move stale; a `main_sha` not in the repo is stale | flag unknown |
| AT-6 | run mode: a file for another platform, `workers` 2, or `order` other than `collection` exits 2 naming both modes | flag unknown |
| AT-7 | strict model: a missing or other `format_version`, a bool as a count, a string list as `collected`, an unknown field each exit 2 | flag unknown |
| AT-8 | shrink rule: a branch collecting 10 fewer ids than the file fails; deleting a test file with exactly those ids passes and leaves no worktree; a collection error in a kept file fails | flag unknown |
| AT-9 | skip rule: one more skip than the file fails | flag unknown |
| AT-10 | totals cross-check: a pytest log whose `N failed` disagrees with the JUnit exits 3; a zero-case JUnit refuses the write | no cross-check |
| AT-11 | environment scrub: `PYTEST_ADDOPTS="-k ok"` during a write still collects every seeded test | flag unknown |
| AT-12 | an inherited test is keyed by the collected module, not the defining file | reporter keys by file today |
| AT-13 | promote contract: the reporter copied (with its sibling `_gates_*.py`) to a directory outside the clone and run as `_gates_report.py OUT --whole-suite --write-baseline F --repo decoy --main-sha S --head-sha H --test-root CLONE` writes the same model as a gates run, inherited id included | subcommand and flag missing |
| AT-14 | bash 3.2: `tests/sentry/test_bash32_compat.py` (ported) is red on its seeds (`mapfile`, a bare `${a[@]}`) and green on every `scripts/dev/*.sh`; on the Mac, `GATES_TEST_BASH=/bin/bash` runs AT-1 to AT-20 and `tests/unit/test_dev_bootstrap_gates.py` green | `mapfile` at `gates.sh:71`; line 83 on `/bin/bash` |
| AT-15 (pin) | the existing `tests/unit/test_dev_bootstrap_gates.py` cells pass unchanged on Linux, including the legacy branch-only cell, the "no complete EVIDENCE block" cells and both "no step ran" cells | |
| AT-16 | `gates_sh_violations` (ported) finds nothing in `gates.sh` and flags each of the eight seeded readers | no guard; `gates.sh:135` runs `python -c` |
| AT-17 (pin) | the EVIDENCE header keeps the CLI's steps and wording: `format` and `mypy` report SKIP with today's reasons; `test paths:` keeps today's text; the sentry step runs `SENTRY_PATHS` with the ratchet first | |
| AT-18 | the compare reads the checked copy: (a) a seeded test rewrites `F` during the run (adds its own id, moves `main_sha`); (b) a wrapper rewrites `F` after `gates.sh` starts and before the tests step; in both the verdict uses the content that was copied, so the seeded failure is new and the run exits 1 | flag unknown |
| AT-19 | legacy verdict (ported `branch_only_steps` cells): shared-only failures exit 0; a branch-only failing id exits 1; a crash code on the branch exits 1 even when main also failed; a step not run on the branch exits 1; a repeated failure counts each time; a JUnit whose totals disagree is branch-only; `--baseline` without `--keep-going` still runs every step | legacy fails on shared failures today |
| AT-20 | a write whose failing ids include one with `0x7f3a2b1c` in its parameters refuses, names it, writes nothing, exits 1 | flag unknown |

End-to-end evidence (not a unit test): on a VM, the handoff's "End-to-end" procedure (a
throwaway clone whose `origin/main` is the slice head, bootstrap first, then write, then compare
a seeded branch on top); record both wall times and the legacy-mode time for the same branch.

## 6a. Mutations (the one list; the handoff points here)

Each on the final head, reverted, never committed; the builder records the SHA and the red test.

1. Failure message text added to `failing` entries: AT-3 red.
2. Merge-base tree dropped from `cleanup`: AT-8 red.
3. Compare accepts a selection: AT-4 red.
4. `main_sha` renamed in the model: AT-3 and AT-13 red.
5. Write allowed for a selection: AT-1 red.
6. `GENERATED_UNREAD_GLOBS` ignored: AT-5 red (svg cell).
7. Stale check warns instead of exit: AT-5 red.
8. A Markdown file a test names treated as harmless: AT-5 red.
9. `DOC_WALK_GUARDS` not applied: AT-5 red.
10. Bool accepted as a count: AT-7 red.
11. Shrink rule dropped: AT-8 red.
12. Skip rule dropped: AT-9 red.
13. Totals cross-check dropped: AT-10 red.
14. Environment scrub dropped: AT-11 red.
15. Memory-address refusal dropped: AT-20 red.
16. Check `$BASEFILE` before the copy, or read it again after: AT-18 red.
17. `--test-root` ignored: AT-13 red.
18. Legacy verdict fails on shared failures: AT-19 red.
19. Inline `"$BIN/python" -c 'import json as j; ...'` in `gates.sh`: AT-16 red.
20. D1 dropped (missing explicit path exits 2): AT-15 red.
21. `mapfile` back in `gates.sh`: AT-14 red.
22. Ids keyed by the defining file: AT-12 red.
23. Write allowed from a dirty or non-main HEAD: AT-2 red.

## 7. Placement

`tests/unit/` holds 40 entries, over the fan-out limit (about 25), so the new script tests go
in a subdirectory. It gets no `__init__.py`: `tests/unit/` has none and neither does
`tests/unit/cli_fmt/`, and with one pytest would import the module as `scripts.*` and shadow the
root `scripts/` folder (M3). CODEMAP has no row for tests of developer scripts; this slice adds
one.

| File | Directory | CODEMAP line | Beside | Change |
|---|---|---|---|---|
| `gates.sh` | `scripts/dev/` | "Developer environment scripts" | `bootstrap.sh` | rewritten as the port |
| `_gates_report.py` | `scripts/dev/` | same | `gates.sh` | extended as the port |
| `_gates_baseline.py` | `scripts/dev/` | same | `_gates_report.py` | new: the stored-file model |
| `bootstrap.sh` | `scripts/dev/` | same | | line 43 guarded expansion only |
| `test_gates_baseline_file.py`, `test_gates_legacy_verdict.py`, `_gates_harness.py` | `tests/unit/scripts/` | new row "Tests of developer scripts: `tests/unit/scripts/`" | | new (split by topic to stay under 900 lines each) |
| `test_bash32_compat.py` | `tests/sentry/` | the sentries row | `test_ratchet_check.py` | new; one `SENTRIES` line in `test_sentry_manifest.py` |
| `CODEMAP.md` | root | | | the new row |
| `CONTRIBUTING.md` | root | | | lines 40 to 44: the new flags, C1 and C2 |

`tests/unit/test_dev_bootstrap_gates.py` stays where it is (AT-15 pins it); moving it is a
follow-up (L5).

## 8. After the merge (orchestrator, not the builder)

Already done: `~/bin/decoy-vm-t3-promote:15` maps `cli` to `REPO_NAME=decoy` (L6).

1. `~/bin/decoy-vm-t3-promote`:
   - `merged`: today it refuses unless main's tree equals H's tree. The bot commit lands about a
     minute after a merge, so accept a main whose diff to H's tree is only in
     `GENERATED_UNREAD_GLOBS` (`docs/diagrams/*.svg`), the same rule the gate applies; record
     `main_sha` as the current main. Otherwise every CLI `merged` promote races the bot.
   - `merged`: pass `--test-root <the run tree on the VM>` to the copied reporter (D7, AT-13).
   - The reader check at `:65` (`if [ "$REPO" = engine ]`): extend it to `cli`, so a promote
     never saves a file the CLI gate refuses (M7).
   - `carry`: keep, as the named exception of section 4a. A carried CLI file hides a re-break
     of an id main fixed since the last real write; prefer a fresh write after any merge that
     touched `tests/`.
2. Write the first CLI main baseline: `decoy-vm-t3 <vm> cli <main> base-cli-1 write`, then
   `decoy-vm-t3-promote <vm> cli base-cli-1 write`.
3. `~/bin/decoy-vm-t3`: drop the `cli` branch of the docs-only staleness check at `:59` only
   after step 1's `merged` change, since the CLI `gates.sh` now refuses a stale file itself
   and accepts the bot's svg moves.
4. From then on, CLI merges use `stored` mode.

## 9. pytest-xdist: not in this slice

Measured cost today: the CLI suite takes about 19 minutes on a 4-core VM and 12 on the Mac. The
stored baseline alone halves a merge test (one run instead of two, about 38 to 19 minutes on a
VM).

xdist would cut the remaining run further (the engine went from 24 to about 13 minutes on the
Mac), but it needs, in the CLI:
- a lock change (`pytest-xdist` in the dev extra and `requirements-dev.lock`), which is a
  full-suite escalation trigger and touches the certified install profile;
- an audit for tests that need the host to themselves, and a `serial` marker with its sentry;
- the xdist report scrubber and the collection-order hook in `tests/conftest.py`.

Answered (Q1): later, as row CLI-PAR. This slice keeps the stored format ready for it
(`workers`, `dist`, `order` are recorded and checked), so CLI-PAR changes no file format.

## 9a. Slices

One slice, one PR, in the CLI repo: about 2,100 lines, mostly ported (`gates.sh` about 420,
`_gates_report.py` about 450, `_gates_baseline.py` about 190, tests about 1,100, sentry about 90,
docs about 25). Splitting the reporter from `gates.sh` would leave a half-wired flag in between;
engine P1 shipped them together for the same reason. The orchestrator steps of section 8 follow
the merge.

## 9b. Pre-mortem

Twelve ways a gate reviewer breaks it, each answered by an AT:
1. The diagram bot commits svgs a minute after each merge and every compare goes stale:
   `GENERATED_UNREAD_GLOBS` (AT-5 svg cells); section 8 relaxes promote's tree check.
2. A docs-reading unit test fails on main after a docs-only main move, and the compare blames
   the branch: the "a test names it" rule (AT-5); STEP ZERO re-lists every reader.
3. A docs fix on main hides a re-break of a sentry that is in the stored failing list:
   `DOC_WALK_GUARDS` from `SENTRY_PATHS` (AT-5).
4. A collection error in a kept file shrinks the suite and reads as green: shrink rule against
   deleted ids only (AT-8).
5. A branch adds `pytest.skip` to a failing test: skip rule (AT-9).
6. pytest crashes mid-run and leaves a partial JUnit: totals cross-check and `SUITE_OK` (AT-10).
7. `PYTEST_ADDOPTS=-x` in the VM environment stops at the first failure: environment scrub (AT-11).
8. A Linux file is used on the Mac: the platform field (AT-6).
9. The legacy route quietly starts passing branches it used to fail: declared as C1 and pinned
   by AT-19; CONTRIBUTING says so.
10. The port drops the CLI's format and mypy SKIP rules, or the CLI's missing-path behavior:
    AT-17 and AT-15.
11. `bash 3.2` dies on an empty array under `set -u` in the new code: AT-14 sentry and the full
    AT set under `/bin/bash` on the Mac.
12. promote's copied reporter keys an inherited test by the wrong file and every later compare
    shows a false NEW: `--test-root` (AT-13).

## 10. Questions

All three Revision 1 questions are answered (section 0). None open.

## 11. Follow-ups (not in this slice)

- CLI-PAR (xdist), section 9.
- L3: add `scripts` to `RUFF_PATHS` and `ci.yml`'s ruff job, so `scripts/dev/*.py` is linted by
  the gate, not by hand.
- L4: the shrink rule counts totals, not ids. A branch can drop kept tests (for example with
  `collect_ignore`) and add as many new ones; deleting one failing test function from a kept
  file is a false red. A per-file presence check from `file_seconds` keys would close both, in
  the engine and the CLI.
- L5: one seeded-clone helper: move `tests/unit/test_dev_bootstrap_gates.py` under
  `tests/unit/scripts/` and have it use `_gates_harness.seeded_clone`, once the AT-15 pin has
  done its job.
- D2: decide whether the CLI wants the engine's `TESTS_REQUIRED` rule on the plain route.
- Carry back to the engine: D6 (copy first) and D7 (`--test-root`); the engine's promote route
  has the same copied-reporter shape.
- V2-LOG: one gates package shared by engine, CLI and platform, instead of three ports. Until
  then, a fix to the engine reporter must be carried to the CLI copy by hand; the build record
  lists every intended difference so the next port can diff against it.
- Platform's `gates.sh` lacks P1's stale refusal and strict model (platform row, not this one).
