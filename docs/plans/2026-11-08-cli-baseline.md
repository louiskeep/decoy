# CLI-BASELINE: a stored failing-id baseline for the CLI gates

Status: plan

Roadmap row 5b (`docs/ROADMAP.md`). Repo `louiskeep/decoy` (CLI). Base: CLI `origin/main`
`a1d67ff` (2026-11-08). Author: claudeworkerbee (Opus), 2026-11-08. Build handoff:
`10_Projects/decoy/handoffs/phase0.5/p05-cli-baseline-build-handoff.md` in the vault.

Rules consulted: `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`,
`testing.md`, `reuse-first.md`, `cross-cutting-concerns.md`, `scope-discipline.md`,
`architecture.md` (fan-out), `verification.md`, `workspace-and-vcs.md`, `documentation.md`.

Risk: R2. The slice changes the merge gate itself. A wrong comparison passes a broken branch
(false green) or blocks a good one, and the stored file is read by tooling outside this repo
(`~/bin/decoy-vm-t3`, `~/bin/decoy-vm-t3-promote`).

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
engine's guard test, because the port rewrites the same lines (see section 10, Q2).

Non-goals:
- pytest-xdist for the CLI suite (section 9 decides: not in this slice).
- Changing what the legacy `--baseline` mode compares, beyond what the port needs.
- The 16 macOS-only CLI test failures (row 5c).
- Editing `~/bin/decoy-vm-t3` or `~/bin/decoy-vm-t3-promote` (orchestrator tooling; section 8
  lists the two changes they need).
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

Remaining custom code: none beyond the port and the CLI's repo configuration.

## 3. Behavior

| Case | Before | After |
|---|---|---|
| `gates.sh --keep-going --baseline tests` (legacy) | branch run, then main rerun in a detached worktree; fails on branch-only failing ids | unchanged |
| `gates.sh --write-baseline F tests` on a clean checkout of `origin/main` | exit 2, unknown flag | runs the whole suite once, writes `F`, prints `gates: wrote baseline F`; exit 1 when main has known failing ids, 0 when none |
| `--write-baseline` on a selection, a dirty tree, or a HEAD other than `origin/main` | exit 2, unknown flag | exit 2 before running, no file |
| `gates.sh --keep-going --baseline-file F tests` on a branch | exit 2, unknown flag | one suite run; exit 1 on a failing id not in `F`; known ids alone give exit 0; ids in `F` that now pass are listed |
| `F` behind `origin/main` by a change to anything but Markdown that no test reads | n/a | exit 2 before running, naming the changed path |
| `F` behind `origin/main` only by Markdown no test names, no doc walker reads, and no stored failing id is a doc walker | n/a | accepted; the header says main moved only in Markdown |
| `F` for another repo, platform, worker count or test order; wrong types; unknown fields; `format_version` not 1 | n/a | exit 2 before running, saying why |
| branch collects fewer tests than `F` beyond the ids of test files it deleted | n/a | exit 1 |
| branch skips more tests than `F` | n/a | exit 1 |
| pytest's totals line disagrees with the JUnit failure count | n/a | exit 3 |
| `PYTEST_ADDOPTS` or `PYTEST_PLUGINS` set in the environment of a write or compare | narrows the run | ignored for the tests step |
| run on macOS `/bin/bash` 3.2 | `mapfile: command not found`, empty selection | works; same selection as bash 5 |
| `gates.sh --order-from` or `GATES_WORKERS` | unknown flag; variable ignored | unchanged: not supported (no xdist, no order hook); the header prints `workers: 1 (the CLI suite runs serial)` |

A stored file never changes test results: every test still runs and reports as it does today.
Only the gate's verdict reads the file.

## 4. Design notes

- One model of the stored file, `_gates_baseline.py` (ported): `load_baseline` is the only
  reader, and the writer serializes the same dataclass. `gates.sh` never parses JSON or JUnit;
  it calls reporter subcommands (`--check-stored`, `--suite-collected`, `--stored-failing-under`,
  `--verdict`). Engine P1 arrived at this after Codex found coerced fields (`true` as a count).
- Repo facts live once, in the configuration block at the top of `gates.sh`: `REPO_NAME=decoy`,
  `SENTRY_PATHS`, `NON_CODE_GLOBS`, `DOC_WALK_ROOTS`, `DOC_WALK_GUARDS`, the format and mypy
  SKIP switches. Logic below the block is the engine's, minus the parallel pass and
  `--order-from` (section 9).
- The CLI port is a port, not a mirror. Each repo keeps its own copy; differences are listed
  in the build record. A shared package is a V2-LOG item.
- House style: single-purpose reporter subcommands, no flag arguments that switch behavior
  inside one function, comments that say why.
- Choke point: the gate verdict in a compare run is computed only by the reporter from the
  stored model and the JUnit. Guard: `test_gates_sh_parses_no_json_or_junit_inline` (ported)
  fails when `gates.sh` contains `json.load`, `import json`, `ElementTree` or `xml.etree`.
  Mutation that must turn it red: read `main_sha` with an inline `python -c 'import json...'`.

## 4a. Invariants

- A compare run passes only if every failing id of the branch's whole-suite run is in the stored
  file, and the stored file describes the `origin/main` the branch is compared against (same
  commit, or a later one that differs only in Markdown no test reads).
- The stored file is only ever written from a whole-suite run on a clean checkout of exactly
  `origin/main`, and only read through one model that refuses anything it does not recognize.
- A gate verdict never comes from a run that did not finish: no JUnit, zero cases, or a totals
  line that disagrees with the JUnit is a failure, never a pass.

## 4b. Class table

| # | Class | Applies how | Closing structure | Proof (sentry or test) | Mutation that must turn it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | the EVIDENCE block, stderr lines and the stored file carry test ids, paths and SHAs only; no test data | the reporter prints ids and counts from JUnit attributes, never captured output | AT-3 field list (no other keys); AT-7 unknown field refused | add the failure message text to `failing` entries: AT-3 red |
| 2 | Cleanup missing on an exit path | the baseline worktree and the merge-base worktree under `$OUT` | one `cleanup` EXIT trap removes both on every exit (ported) | AT-8 deleted-ids cell leaves no worktree in `git worktree list`; AT-15 pin | drop the merge-base tree from `cleanup`: AT-8 worktree check red |
| 3 | State machine and concurrency | N/A: one process, no shared state; two runs never share `$OUT` (`mktemp -d`) | `mktemp -d` per run | AT-15 pin | n/a |
| 4 | Route parity and silent fallback | four routes (section 4c): plain, legacy, write, compare; a compare must never fall back to legacy or to a selection | the compare refuses a selection (`WHOLE_SUITE`) and never adds the baseline tree | AT-1, AT-4, AT-11 | let `--baseline-file` accept a selection: AT-4 selection cell red |
| 5 | Referential integrity | N/A: no tables or keys; the only reference is `main_sha` to a commit, covered by class 8 | stale refusal | AT-5 (`main_sha` not in the repo) | n/a |
| 6 | Untrusted producer | the stored file and the JUnit come from another run (another host, an older tool) | `load_baseline` with exact types and `format_version`; JUnit counted and cross-checked against pytest's totals | AT-7, AT-10 | accept a bool as a count: AT-7 red; drop the totals check: AT-10 red |
| 7 | Check then use (TOCTOU) | the stored file is copied into `$OUT` once and only the copy is read after the checks | copy before use (ported) | AT-18 | read `$BASEFILE` again after the copy: AT-18 red |
| 8 | Weak tests and overclaimed evidence | the slice's whole point: a compare that passes without running the suite, or with fewer tests | shrink, skip and totals rules; `no step ran` exit 3 | AT-8, AT-9, AT-10, AT-15 | drop the shrink rule: AT-8 red; drop the skip rule: AT-9 red |
| 9 | Refactor drift | `gates.sh` is rewritten; its legacy route must keep its verdict | characterization pins first (AT-15, AT-17) | AT-15, AT-17 | change the legacy verdict to fail on shared failures: AT-15 red |
| 10 | Frozen contract drift | the stored file format shared with the engine and read by `decoy-vm-t3-promote`; the EVIDENCE header lines the orchestrator greps | the engine's `format_version` 1 model, ported unchanged; AT-13 pins the promote argv | AT-3, AT-13 | rename `main_sha`: AT-3 and AT-13 red |

## 4c. Enumerations

### Exit paths

- `gates.sh` exit 0: every branch step passed (plain), no branch-only failure (legacy), no new id
  and every rule held (compare).
- exit 1: a failing step or id; a refused write after the run (`WRITE_REFUSED`); a write on a main
  with known failures (still writes).
- exit 2: usage, missing venv or `origin/main`, a refused write before running, a stale, foreign
  or malformed stored file.
- exit 3: no complete EVIDENCE block, no step ran, totals disagree with the JUnit.
- Every exit runs the EXIT trap that removes `$OUT/baseline-tree` and `$OUT/merge-base-tree`.
- `_gates_report.py` exits: 0, 1 (main, `scripts/dev/_gates_report.py:71` today), 4 (totals
  mismatch, ported), 64 (usage, ported).

### Routes

- Plain: `gates.sh [paths]` (today; `scripts/dev/_gates_report.py:71` prints the block).
- Legacy: `--baseline` (today; `tests/unit/test_dev_bootstrap_gates.py:163` pins it).
- Write: `--write-baseline FILE tests` (new).
- Compare: `--baseline-file FILE tests` (new).
- Direct reporter call from `decoy-vm-t3-promote merged` (`_gates_report.py OUT --whole-suite
  --write-baseline ...`), outside this repo (AT-13).

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
- Files: the stored baseline (write only), `$OUT/*.log`, `*.xml`, `*.steps`, `meta`,
  `new-failing`, `shortfall`, `skip-increase`.
- Exit code (section 4c, exit paths).
- `CONTRIBUTING.md:40` (docs of the flags).

## 4d. Reuse inventory

- Engine `scripts/dev/gates.sh`, `_gates_report.py`, `_gates_baseline.py` on `b5b1ad16`: ported.
- Engine `tests/unit/scripts/test_gates_baseline_file.py`, `_gates_harness.py`: ported (P1 cells
  and the run-mode cells; not the parallel cells of `test_gates_parallel.py`).
- Engine `tests/sentry/test_bash32_compat.py`: ported unchanged.
- CLI `scripts/dev/ratchet_check.py` and the sentry step: kept as is.
- CLI `tests/unit/test_dev_bootstrap_gates.py`: kept, pinned (AT-15).
- CLI `tests/sentry/test_sentry_manifest.py:24` (`SENTRIES`): one line for the new sentry.
- No new machinery beyond the port.

## 4e. Frozen contracts touched

- The stored baseline format (`format_version` 1): additive to the CLI (new file), identical to
  the engine's. Not changed.
- The `gates.sh` command line: additive (`--write-baseline`, `--baseline-file`, `--full`). Every
  existing flag and the default selection keep their meaning (AT-15).
- The EVIDENCE header: additive (`workers:` and, in a compare, `baseline:` and `run mode:`
  lines). Existing lines unchanged (AT-17).
- `decoy-ci/v1` and every user-facing CLI surface: not touched.

## 5. The CLI-specific inputs (measured on `a1d67ff`; re-measure at STEP ZERO)

- Commit mix: 28 of the last 40 commits on CLI main touch only Markdown, so the Markdown
  exception decides whether a stored file survives most main moves.
- Tests that walk or read docs: at least `tests/unit/test_exit_codes.py`,
  `test_no_dead_command_strings.py`, `test_surface_docs_consistency.py`, `test_cli_surface.py`
  (`docs/cli-reference.md`), `test_ci_docs.py` (`docs/ci-contracts.md`), `test_sbom_script.py`
  (`docs/release/sbom.md`), `test_ci_manifest.py`, and the sentries `test_baseline_registry.py`,
  `test_gate_single_entry.py`, `test_engine_internal_boundary.py`, `test_ci_output_isolation.py`.
  A test that names a file is caught by the "a test names it" rule. A test that walks a
  directory goes in `DOC_WALK_ROOTS` (the directory) or, when it walks all of `docs/`, in
  `DOC_WALK_GUARDS` (its test path), which makes any main move stale while one of its ids is in
  the stored failing list. `tests/sentry/` is a guard prefix as in the engine.
- `bash 3.2`: `gates.sh` has 11 bash 4 constructs (`mapfile` at :71, ten bare array
  expansions); `bootstrap.sh:43` has one bare array expansion; `lock.sh` and `lock_version.sh`
  have none.
- No `pytest-xdist` in `requirements-dev.lock`; no `serial` marker; no collection-order hook in
  `tests/conftest.py`.
- `decoy-vm-t3-promote merged` writes the file with `--repo decoy-$REPO`, which is
  `decoy-cli` for the CLI, while `gates.sh` says `REPO_NAME=decoy`. See section 8.

## 6. Acceptance tests

Red first on the base unless marked "pin". All run in a scratch clone with seeded test files
(the engine's `_gates_harness.py` pattern), never against the real suite, except AT-15.

| AT | Test | Red on base because |
|---|---|---|
| AT-1 | `--write-baseline` on a selection exits 2 and writes nothing | flag unknown |
| AT-2 | `--write-baseline` with HEAD not `origin/main`, or a dirty tree, exits 2 | flag unknown |
| AT-3 | `--write-baseline` on a clean `origin/main` with one seeded failing test writes a file with every field (`format_version` 1, `repo` `decoy`, `main_sha`, `head_sha`, `collected`, `skipped`, sorted `failing`, `workers` 1, `dist` `no`, `platform`, `order` `collection`, `order_seconds` `{}`, `file_seconds`), prints `gates: wrote baseline`, exits 1 | flag unknown |
| AT-4 | compare: a new failing id exits 1 and names it; only known ids exit 0; a known id that passes now is listed | flag unknown |
| AT-5 | stale: a code change on main after the stored sha exits 2 before running; a Markdown change no test names is accepted with the NOTE line; a Markdown file a test names is stale; a change under a `DOC_WALK_ROOTS` directory is stale; a stored failing id under a `DOC_WALK_GUARDS` prefix makes any move stale; a `main_sha` not in the repo is stale | flag unknown |
| AT-6 | run mode: a file for another platform, `workers` 2, or `order` other than `collection` exits 2 naming both modes | flag unknown |
| AT-7 | strict model: a missing or other `format_version`, a bool as a count, a string list as `collected`, an unknown field each exit 2 | flag unknown |
| AT-8 | shrink rule: a branch collecting 10 fewer ids than the file fails; deleting a test file with exactly those ids passes; a collection error in a kept file fails | flag unknown |
| AT-9 | skip rule: one more skip than the file fails | flag unknown |
| AT-10 | totals cross-check: a pytest log whose `N failed` disagrees with the JUnit exits 3; a zero-case JUnit refuses the write | no cross-check |
| AT-11 | environment scrub: `PYTEST_ADDOPTS="-k ok"` during a write still collects every seeded test | flag unknown |
| AT-12 | an inherited test is keyed by the collected module, not the defining file | reporter keys by file today |
| AT-13 | promote contract (pin of the argv): `_gates_report.py OUT --whole-suite --write-baseline F --repo decoy --main-sha S --head-sha H` writes the same model as a gates run | subcommand missing |
| AT-14 | bash 3.2: `tests/sentry/test_bash32_compat.py` (ported) is red on its seeds (`mapfile`, a bare `${a[@]}`) and green on every `scripts/dev/*.sh`; on the Mac, `/bin/bash scripts/dev/gates.sh --steps tests` with a seeded changed module selects the same files as bash 5 | `mapfile` at `gates.sh:71`; `bootstrap.sh:43` |
| AT-15 (pin) | the existing `tests/unit/test_dev_bootstrap_gates.py` cells pass unchanged, including the legacy `--baseline` branch-only cell and the "no complete EVIDENCE block" and "no step ran" cells | |
| AT-16 | `test_gates_sh_parses_no_json_or_junit_inline` (ported) | no guard |
| AT-17 (pin) | the EVIDENCE header keeps the CLI's steps: `format` and `mypy` report SKIP with today's reasons; the sentry step runs `SENTRY_PATHS` with the ratchet first | |
| AT-18 | the compare reads the checked copy: a seeded test rewrites `F` during the run (adds its own id to `failing` and moves `main_sha`); the verdict still uses the content that passed the checks, so the seeded failure is new and the run exits 1 | flag unknown |

End-to-end evidence (not a unit test): on a VM, write a real CLI main baseline at `origin/main`,
then compare one real branch against it; record both wall times and the legacy-mode time for the
same branch.

## 7. Placement

`tests/unit/` holds 40 entries, over the fan-out limit (about 25), so the new script tests go
in a sub-package. CODEMAP has no row for tests of developer scripts; this slice adds one.

| File | Directory | CODEMAP line | Beside | Change |
|---|---|---|---|---|
| `gates.sh` | `scripts/dev/` | "Developer environment scripts" | `bootstrap.sh` | rewritten as the port |
| `_gates_report.py` | `scripts/dev/` | same | `gates.sh` | extended as the port |
| `_gates_baseline.py` | `scripts/dev/` | same | `_gates_report.py` | new: the stored-file model |
| `bootstrap.sh` | `scripts/dev/` | same | | line 43 guarded expansion only |
| `test_gates_baseline_file.py`, `_gates_harness.py`, `__init__.py` | `tests/unit/scripts/` | new row "Tests of developer scripts: `tests/unit/scripts/`" | | new |
| `test_bash32_compat.py` | `tests/sentry/` | the sentries row | `test_ratchet_check.py` | new; one `SENTRIES` line in `test_sentry_manifest.py` |
| `CODEMAP.md` | root | | | the new row |
| `CONTRIBUTING.md` | root | | | line 40: the new flags in one paragraph |

`tests/unit/test_dev_bootstrap_gates.py` stays where it is (AT-15 pins it); moving it is not
part of this slice.

## 8. After the merge (orchestrator, not the builder)

1. `~/bin/decoy-vm-t3-promote`: `--repo decoy-$REPO` writes `decoy-cli`; the CLI file must say
   `decoy`. Map `cli` to `decoy` there (recommended; see Q3).
2. Write the first CLI main baseline: `decoy-vm-t3 <vm> cli <main> base-cli-1 write`, then
   `decoy-vm-t3-promote <vm> cli base-cli-1 write`.
3. `~/bin/decoy-vm-t3`: drop the `cli` branch of the docs-only staleness check (the CLI
   `gates.sh` now refuses a stale file itself, as the engine's does).
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

That is a slice of its own. Recommendation: a follow-up row CLI-PAR, decided after CLI merges
have run in `stored` mode for a while and the 19 minutes is measured as the bottleneck. This
slice keeps the stored format ready for it (`workers`, `dist`, `order` are recorded and
checked), so CLI-PAR changes no file format.

## 9a. Slices

One slice, one PR, in the CLI repo: about 1,900 lines, mostly ported
(`gates.sh` about 400, `_gates_report.py` about 420, `_gates_baseline.py` about 180, tests about
950, sentry about 90, docs about 20). Splitting the reporter from `gates.sh` would leave a
half-wired flag in between; engine P1 shipped them together for the same reason. The orchestrator
steps of section 8 follow the merge.

## 9b. Pre-mortem

Ten ways a gate reviewer breaks it, each answered by an AT:
1. A docs-walking unit test fails on main after a docs-only main move, and the compare blames the
   branch: `DOC_WALK_ROOTS` and the "a test names it" rule (AT-5); STEP ZERO lists every walker.
2. A docs fix on main hides a re-break of a walker that is in the stored failing list:
   `DOC_WALK_GUARDS` (AT-5).
3. A collection error in a kept file shrinks the suite and reads as green: shrink rule against
   deleted ids only (AT-8).
4. A branch adds `pytest.skip` to a failing test: skip rule (AT-9).
5. pytest crashes mid-run and leaves a partial JUnit: totals cross-check and `SUITE_OK` (AT-10).
6. `PYTEST_ADDOPTS=-x` in the VM environment stops at the first failure: environment scrub (AT-11).
7. A Linux file is used on the Mac: the platform field (AT-6).
8. The promote script writes `decoy-cli` and every later compare exits 2: AT-13 pins the
   argv; section 8 step 1 maps the name.
9. The port drops the CLI's format and mypy SKIP rules and the sentry step suddenly runs
   `ruff format --check` on a tree that is not format-clean: AT-17.
10. `bash 3.2` dies on an empty array under `set -u` in the new code: AT-14 sentry and the Mac
    run.

## 10. Questions (recommended answer first)

- Q1 (orchestrator): xdist now or later? Recommended: later, as row CLI-PAR (section 9).
- Q2 (orchestrator): row 5c (CLI-MAC-TESTS) says "make `gates.sh` bash 3.2 safe, or install
  bash 4 on the Mac". This slice rewrites `gates.sh` and makes it bash 3.2 safe with the guard
  test. Recommended: 5b takes that half; 5c keeps the macOS test failures only.
- Q3 (orchestrator): the repo name in the stored file. Recommended: keep `REPO_NAME=decoy`
  (it is in every EVIDENCE block today) and map `cli` to `decoy` in `decoy-vm-t3-promote`.
  Alternative: `REPO_NAME=decoy-cli`, which changes every CLI EVIDENCE header.

## 11. Follow-ups (not in this slice)

- CLI-PAR (xdist), section 9.
- V2-LOG: one gates package shared by engine, CLI and platform, instead of three ports. Until
  then, a fix to the engine reporter must be carried to the CLI copy by hand; the build record
  lists every intended difference so the next port can diff against it.
- Platform's `gates.sh` lacks P1's stale refusal and strict model (platform row, not this one).
