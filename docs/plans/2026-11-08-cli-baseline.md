# CLI-BASELINE: a stored failing-id baseline for the CLI gates

Status: plan (Revision 3; Dennis GO; Codex plan gate GO)

Roadmap row 5b (`docs/ROADMAP.md`). Repo `louiskeep/decoy` (CLI). Measured on CLI `origin/main`
`b6e0437` (2026-11-08; Revision 2 used `b7009d1`, Revision 1 used `a1d67ff`). Engine source:
`origin/main` `b5b1ad16`.
Author: claudeworkerbee (Opus), 2026-11-08. Build handoff:
`10_Projects/decoy/handoffs/phase0.5/p05-cli-baseline-build-handoff.md` in the vault.

Rules consulted: `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`,
`testing.md`, `reuse-first.md`, `cross-cutting-concerns.md`, `scope-discipline.md`,
`architecture.md` (fan-out), `verification.md`, `workspace-and-vcs.md`, `code-review.md`,
`api-and-compatibility.md`, `documentation.md`, `catalogs/recurring-defects.md`.

Risk: R2. The slice changes the merge gate itself. A wrong comparison passes a broken branch
(false green) or blocks a good one, and the stored file is read by tooling outside this repo
(`~/bin/decoy-vm-t3`, `~/bin/decoy-vm-t3-promote`).

## 0. Revision 3 (Dennis round 2: GO, 0 BLOCKER / 0 HIGH / 4 MEDIUM / 9 LOW)

Review: vault `10_Projects/decoy/handoffs/phase0.5/p05-cli-baseline-dennis-r2.md`. Reviewed
artifact: CLI plan `origin/plan/cli-baseline` at `ffaa590`; current CLI main is `b6e0437` and
the engine source remains `b5b1ad16`.

| Finding | Fix in this revision |
|---|---|
| M-1 `DESIGN`: promote duplicates the D5 staleness rule | `merged` finds the newest first-parent commit `S` on current main whose tree equals tested head `H`, refuses if none, writes `main_sha=S`, and asserts `S`. It has no generated-path list; D5 remains the only staleness rule (section 8). |
| M-2 `V2-LOG`: mutation 16 combines two theoretical race defects | Split into 16a and 16b. AT-18a uses the recording-venv Python shim to rewrite `F` on the first `--check-stored` reporter call, deterministically between a mutant's check and copy; AT-18b rewrites during the suite to catch a later read of the original. |
| M-3 `V1`: `--test-root` silently falls back | A supplied root must be an existing directory or the reporter exits 64 before reading JUnit or writing a file. AT-13 has the refusal cell and mutation 25. Section 8 names `~/decoy/wt-<label>` and its lifetime. |
| M-4 `V1`: SHA fields accept arbitrary strings | D10 validates both SHA fields with `re.fullmatch(r"[0-9a-f]{40}")`. AT-7 covers a symbolic ref, short SHA and trailing newline; mutation 24 drops the validator. Carry back to the engine. |
| L-1 `V1`: address regex blocks legitimate hex ids | D8 uses the engine's ` at 0x[0-9a-fA-F]+>` pattern and the refusal contains `write-baseline refused`; STEP ZERO reports both that pattern and the broader hex audit. |
| L-2 `V2-LOG`: legacy ruff overclaim | C1 promises shared-only success for `tests` and `sentry` only. Unparsed tool failures, including default-format ruff output, remain branch-only and fail closed. |
| L-3 `V2-LOG`: missing mutations | Added mutation 26 for C2 keep-going, 27 for `DOC_WALK_ROOTS`, and 28 for D9's exact-file entry. |
| L-4 `V2-LOG`: D9 matcher change | D9 only derives `DOC_WALK_GUARDS` from `SENTRY_PATHS`; it keeps the engine prefix matcher. AT-5 covers `tests/unit/test_cli_surface.py`. |
| L-5 `V2-LOG`: reuse citations | Section 4d lists the exact engine cells ported and the excluded D2/D4 cells by name. |
| L-6 `V1`: reporter export omitted from the contract | Section 4d keeps `_gates_report.load_baseline` in `__all__`; AT-13 imports it from the copied reporter. |
| L-7 `V2-LOG`: handoff svg step proves nothing | The branch compare changes only a seeded test; the separate main-move step owns the svg check. |
| L-8 `V2-LOG`: sentry fan-out | Section 7 records the accepted 28-entry directory and requires the next sentry family to use a named sub-package. |
| L-9 `V2-LOG`: inherited allowlisted helper gap | Section 11 carries the engine/CLI `_ALLOWED_PY_ARGS` inline-program gap. It does not affect this verdict. |

Codex plan gate (Revision 3): **GO**. No open `V1` finding and no change-created `DESIGN`
finding remains. Acceptance behavior is defined before implementation, all 29 mutations map to
a red cell, and the change adds no second CLI-internal central mechanism. Accepted `V2-LOG`
items are recorded in sections 7 and 11 and do not decide the verdict.

## 0a. Revision 2 (Dennis round 1: NO-GO, 0 BLOCKER / 3 HIGH / 9 MEDIUM / 6 LOW)

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
always keeps going. For the CLI's current output, shared-only success is promised for the
`tests` and `sentry` steps; an unparsed tool failure remains branch-only and fails closed. These
are declared changes C1 and C2 (sections 3 and 4e), not side effects.

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
| legacy verdict | exit 1 on any failing branch step, failures shared with main included (`scripts/dev/gates.sh:147`) | exit 1 only on a branch-only step: a step main passes, a crash or kill code, an unidentified or unparsed failure, or more of an identified failure than main has; shared-only `tests` and `sentry` failures give exit 0, while default-format ruff and other unparsed tool failures fail closed (C1, AT-19) |
| `gates.sh --write-baseline F tests` on a clean checkout of `origin/main` | exit 2, unknown flag | runs the whole suite once, writes `F`, prints `gates: wrote baseline F`; exit 1 when main has known failing ids, 0 when none |
| `--write-baseline` on a selection, a dirty tree, or a HEAD other than `origin/main` | exit 2, unknown flag | exit 2 before running, no file |
| `--write-baseline` where a failing id carries a default-repr memory address (` at 0x[0-9a-fA-F]+>`) | exit 2, unknown flag | runs, refuses to write, includes `write-baseline refused` and names the id, writes nothing, exit 1 (D8, AT-20) |
| `gates.sh --keep-going --baseline-file F tests` on a branch | exit 2, unknown flag | one suite run; exit 1 on a failing id not in `F`; known ids alone give exit 0; ids in `F` that now pass are listed |
| `--baseline-file` on a selection | exit 2, unknown flag | exit 1: a compare needs a completed whole-suite run (AT-4) |
| `F` behind `origin/main` by a change to anything but Markdown or a generated, unread artifact | n/a | exit 2 before running, naming the changed path |
| `F` behind `origin/main` only by Markdown or `docs/diagrams/*.svg` that no test names, no doc walker reads, and no stored failing id is a doc-walk guard | n/a | accepted; the header says main moved only in such files (AT-5) |
| `F` for another repo, platform, worker count or test order; wrong types; unknown fields; `format_version` not 1; `main_sha` or `head_sha` not exactly 40 lowercase hex characters | n/a | exit 2 before running, saying why (D10, AT-7) |
| `F` rewritten while the gate checks or runs | n/a | the gate copies `F` first and checks and reads only the copy (D6, AT-18a, AT-18b) |
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
  count). The CLI adds D10 at this same model choke point: each SHA check retains the strict
  `isinstance(value, str)` guard and then requires
  `re.fullmatch(r"[0-9a-f]{40}", value) is not None`.
- Repo facts live once, in the configuration block at the top of `gates.sh`: `REPO_NAME=decoy`,
  `SENTRY_PATHS`, `PYTEST_ARGS`, `NON_CODE_GLOBS`, `GENERATED_UNREAD_GLOBS`, `DOC_WALK_ROOTS`,
  the format and mypy SKIP switches. `DOC_WALK_GUARDS` is not a second list: it is set from
  `SENTRY_PATHS` (D9). `SENTRY_PATHS=(` and `PYTEST_ARGS=(` keep their one-entry-per-line shape,
  which `tests/sentry/test_sentry_manifest.py` parses.
- Generated, unread artifacts (H1). `.github/workflows/regen-diagrams.yml` commits
  `docs/diagrams/*.svg` to main as github-actions[bot] about a minute after every merge that
  touches `src/`. The staleness rule treats a path matching `GENERATED_UNREAD_GLOBS` like
  Markdown: harmless unless a file under `tests/` names it or it is under `DOC_WALK_ROOTS`.
  No test names `diagrams` or an svg today (unchanged through `b6e0437`). The engine has no such bot, so
  this list is CLI-only (D5).
- The reporter resolves a test's collected module against a test root. It is the repo root by
  default (`parents[2]` of the reporter). A supplied `--test-root DIR` overrides it for a
  reporter copied outside the repo as `decoy-vm-t3-promote merged` does, and must be an existing
  directory. A missing path or non-directory exits 64 before JUnit is read or any destination
  file is written (D7).
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
| 5 | Referential integrity | N/A: no tables or keys; `main_sha` and `head_sha` are commit identifiers | exact 40-lowercase-hex validation in the one stored model, then the stale commit check | AT-7 malformed SHA cells; AT-5 (`main_sha` not in the repo) | 24: SHA validator dropped, AT-7 red |
| 6 | Untrusted producer | the stored file and the JUnit come from another run (another host, an older tool, a reporter copied outside the repo); failing ids come from test parameters | `load_baseline` with exact types, SHA shapes and `format_version`; JUnit counted and cross-checked against pytest's totals; a supplied `--test-root` must be a directory; default-repr address ids refused at write | AT-7, AT-10, AT-13, AT-20 | 10: bool as a count, AT-7 red; 13: totals check dropped, AT-10 red; 15: address check dropped, AT-20 red; 17: `--test-root` ignored, AT-13 red; 24: SHA validator dropped, AT-7 red; 25: non-directory root accepted, AT-13 red |
| 7 | Check then use (TOCTOU) | the stored file is read by the stale check, the model check and the verdict | copy first, check and read only the copy (D6) | AT-18a deterministically rewrites on the first `--check-stored` call; AT-18b rewrites during the suite | 16a: check original before copy, AT-18a red; 16b: read original after copy, AT-18b red |
| 8 | Weak tests and overclaimed evidence | the slice's whole point: a compare that passes without running the suite, or with fewer tests; a guard that a renamed import slips past | shrink, skip and totals rules; `no step ran` exit 3; allow-list guard on `gates.sh` | AT-8, AT-9, AT-10, AT-15, AT-16 | 11: shrink rule dropped, AT-8 red; 12: skip rule dropped, AT-9 red; 19: inline `python -c` JSON read in `gates.sh`, AT-16 red |
| 9 | Refactor drift | `gates.sh` is rewritten; the legacy and plain routes must change only as declared (C1, C2, D1 to D4) | characterization pins first (AT-15, AT-17); the declared legacy verdict and keep-going behavior pinned by AT-19 | AT-15, AT-17, AT-19 | 18: legacy verdict fails on shared test failures, AT-19 red; 20: D1 dropped, AT-15 red; 26: C2 force dropped, AT-19 red |
| 10 | Frozen contract drift | the stored file format shared with the engine and read by `decoy-vm-t3-promote`; the EVIDENCE header lines the orchestrator greps | the engine's `format_version` 1 model, ported unchanged; AT-13 pins the promote argv | AT-3, AT-13 | 4: `main_sha` renamed, AT-3 and AT-13 red |

## 4c. Enumerations

### Exit paths

- `gates.sh` exit 0: every branch step passed (plain), no branch-only step (legacy), no new id
  and every rule held (compare).
- exit 1: a failing step or id; a branch-only legacy step; a refused write after the run
  (`write-baseline refused`: no completed whole suite, or a failing id with a default-repr
  memory address); a write on
  a main with known failures (still writes); a compare without a completed whole suite.
- exit 2: usage, missing venv or `origin/main`, a refused write before running, a stale, foreign
  or malformed stored file.
- exit 3: no complete EVIDENCE block, no step ran, totals disagree with the JUnit, the legacy
  verdict could not be computed.
- Every exit runs the EXIT trap that removes `$OUT/baseline-tree` and `$OUT/merge-base-tree`.
- `_gates_report.py` exits: 0, 1 (main, `scripts/dev/_gates_report.py:71` today), 4 (totals
  mismatch, ported), 64 (usage or an explicit `--test-root` that is not an existing directory).

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
- `format_version` (int, exactly 1), `repo` (str), `main_sha`, `head_sha` (each exactly 40
  lowercase hex characters, checked with `re.fullmatch`);
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
- Engine `tests/unit/scripts/test_dev_bootstrap_gates.py`: port
  `test_gates_baseline_passes_when_the_only_failure_is_shared_with_main`,
  `test_a_branch_crash_is_branch_only_even_when_main_also_failed`,
  `test_a_branch_timeout_is_branch_only_even_when_main_timed_out_too`,
  `test_a_failure_with_no_identifiable_diagnostic_is_branch_only`,
  `test_a_duplicated_identical_diagnostic_is_branch_only`,
  `test_identical_failures_on_both_sides_are_shared`,
  `test_a_total_that_disagrees_with_the_parsed_lines_is_branch_only`,
  `test_a_pytest_failure_main_lacks_is_branch_only_when_main_also_fails`,
  `test_a_repeated_pytest_failure_counts_each_time`,
  `test_a_junit_report_whose_totals_disagree_is_branch_only`,
  `test_a_branch_step_that_never_ran_is_branch_only`, and
  `test_baseline_mode_keeps_going_after_a_failing_step` into AT-19. Do not port the D4-only
  diagnostic cells `test_branch_only_steps_matches_mypy_errors_across_line_moves`,
  `test_branch_only_steps_flags_a_failure_main_does_not_have`, or
  `test_ruff_concise_diagnostics_are_compared_as_a_multiset`. Do not port the D2
  `TESTS_REQUIRED` and doc-path cells
  (`test_gates_fails_a_code_change_that_selects_no_tests`,
  `test_gates_passes_a_docs_only_change_with_tests_not_applicable`,
  `test_gates_fails_a_change_outside_the_old_code_globs_with_no_matching_test`,
  `test_gates_fails_a_mixed_docs_and_code_change_with_no_tests`,
  `test_gates_passes_a_change_made_only_of_documentation_paths`,
  `test_gates_fails_a_code_file_renamed_into_docs_with_no_tests`, and
  `test_gates_treats_a_workflow_change_as_code`).
- `_gates_report.py` continues to re-export `load_baseline` in `__all__`, because promote's
  reader check imports that name from the copied reporter. AT-13 exercises that import.
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
    a branch whose `tests` or `sentry` step shares main's known failures and adds none now passes
    legacy, as it would pass a compare. Unparsed failures, including the CLI's default ruff
    output, remain branch-only and fail closed. AT-19.
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
| D7 | `TEST_ROOT = parents[2]` only | `--test-root DIR` overrides it; when supplied, it must be an existing directory or the reporter exits 64 before writing | promote runs a copied reporter (M6); carry back to the engine |
| D8 | default-repr memory-address ids refused at collection with ` at 0x[0-9a-fA-F]+>` (`tests/conftest.py:102`) | the same pattern is refused at write by the reporter; the message contains `write-baseline refused` | the CLI slice may not touch `tests/conftest.py`; plain hex parameters remain valid |
| D9 | `DOC_WALK_GUARDS` is its own list | derive `DOC_WALK_GUARDS` from `SENTRY_PATHS`; keep the engine's unchanged prefix matcher, so entries cover both exact files and directories | one list (L2); AT-5 covers the directory entries and exact file `tests/unit/test_cli_surface.py` |
| D10 | `main_sha` is any non-empty string and `head_sha` any string | in the one model, both fields retain a strict string-type check and then pass `re.fullmatch(r"[0-9a-f]{40}", value)` | symbolic refs otherwise pass `git cat-file` and can evade staleness; carry back to the engine |

## 5. The CLI-specific inputs (measured on `b7009d1`; source unchanged at `b6e0437`; re-measure at STEP ZERO)

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
| AT-5 | stale: a code change on main after the stored sha exits 2 before running; a Markdown change no test names is accepted with the NOTE line; an svg change under `docs/diagrams/` no test names is accepted; a Markdown file a test names is stale; an svg a test names is stale; a change under a `DOC_WALK_ROOTS` directory is stale (seeded root); a stored failing id under a directory `SENTRY_PATHS` entry makes any move stale; a stored failing id exactly equal to the file entry `tests/unit/test_cli_surface.py` also makes it stale; a `main_sha` not in the repo is stale | flag unknown |
| AT-6 | run mode: a file for another platform, `workers` 2, or `order` other than `collection` exits 2 naming both modes | flag unknown |
| AT-7 | strict model: a missing or other `format_version`, a bool as a count, a string list as `collected`, an unknown field, and either SHA field set to a non-string, symbolic ref, short SHA, uppercase SHA, or 40-hex SHA plus `"\n"` each exit 2 rather than crashing | flag unknown |
| AT-8 | shrink rule: a branch collecting 10 fewer ids than the file fails; deleting a test file with exactly those ids passes and leaves no worktree; a collection error in a kept file fails | flag unknown |
| AT-9 | skip rule: one more skip than the file fails | flag unknown |
| AT-10 | totals cross-check: a pytest log whose `N failed` disagrees with the JUnit exits 3; a zero-case JUnit refuses the write | no cross-check |
| AT-11 | environment scrub: `PYTEST_ADDOPTS="-k ok"` during a write still collects every seeded test | flag unknown |
| AT-12 | an inherited test is keyed by the collected module, not the defining file | reporter keys by file today |
| AT-13 | promote contract: the reporter copied (with its sibling `_gates_*.py`) to a directory outside the clone and run as `_gates_report.py OUT --whole-suite --write-baseline F --repo decoy --main-sha S --head-sha H --test-root CLONE` writes the same model as a gates run, inherited id included, and exposes `load_baseline` through `_gates_report`; a missing path and a regular file passed as `--test-root` each exit 64 and write nothing | subcommand and flag missing |
| AT-14 | bash 3.2: `tests/sentry/test_bash32_compat.py` (ported) is red on its seeds (`mapfile`, a bare `${a[@]}`) and green on every `scripts/dev/*.sh`; on the Mac, `GATES_TEST_BASH=/bin/bash` runs AT-1 to AT-20 and `tests/unit/test_dev_bootstrap_gates.py` green | `mapfile` at `gates.sh:71`; line 83 on `/bin/bash` |
| AT-15 (pin) | the existing `tests/unit/test_dev_bootstrap_gates.py` cells pass unchanged on Linux, including the legacy branch-only cell, the "no complete EVIDENCE block" cells and both "no step ran" cells | |
| AT-16 | `gates_sh_violations` (ported) finds nothing in `gates.sh` and flags each of the eight seeded readers | no guard; `gates.sh:135` runs `python -c` |
| AT-17 (pin) | the EVIDENCE header keeps the CLI's steps and wording: `format` and `mypy` report SKIP with today's reasons; `test paths:` keeps today's text; the sentry step runs `SENTRY_PATHS` with the ratchet first | |
| AT-18a | copy-before-check: extend `recording_venv`'s Python shim so that, on its first reporter call containing `--check-stored`, it rewrites the original `F` to a valid file that includes the seeded failing id before executing that reporter call. Correct code already copied the old file, reports the seeded id NEW and exits 1; a check-then-copy mutant copies the rewrite and exits 0 | flag unknown |
| AT-18b | no read-after-copy: a seeded test rewrites the original `F` during the suite (adds its own id and changes `main_sha`); the verdict still uses the earlier copy, reports the seeded id NEW and exits 1 | flag unknown |
| AT-19 | legacy verdict (ported `branch_only_steps` cells): shared-only `tests` and `sentry` failures exit 0; default-format ruff and any unidentified failure remain branch-only; a branch-only failing id exits 1; a crash code on the branch exits 1 even when main also failed; a step not run on the branch exits 1; a repeated failure counts each time; a JUnit whose totals disagree is branch-only; `--baseline` without `--keep-going` still runs every step | legacy fails on shared failures today |
| AT-20 | a write whose failing id includes `test_x[<Thing at 0x7f3a2b1c>]` refuses with `write-baseline refused`, names it, writes nothing and exits 1; `test_x[0xdeadbeef]` is accepted | flag unknown |

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
15. Default-repr memory-address refusal dropped: AT-20 red.
16a. Check `$BASEFILE` before copying it: deterministic reporter-call trigger in AT-18a red.
16b. Read `$BASEFILE` again after the copy: suite-time rewrite in AT-18b red.
17. `--test-root` ignored: AT-13 red.
18. Legacy verdict fails on shared `tests` or `sentry` failures: AT-19 red.
19. Inline `"$BIN/python" -c 'import json as j; ...'` in `gates.sh`: AT-16 red.
20. D1 dropped (missing explicit path exits 2): AT-15 red.
21. `mapfile` back in `gates.sh`: AT-14 red.
22. Ids keyed by the defining file: AT-12 red.
23. Write allowed from a dirty or non-main HEAD: AT-2 red.
24. The full 40-lowercase-hex validator for either SHA field is dropped: AT-7 red.
25. An explicit `--test-root` that is a missing path or regular file is accepted or falls back:
    AT-13 red.
26. The C2 force that makes legacy mode keep going is dropped: AT-19 red.
27. `DOC_WALK_ROOTS` is ignored: AT-5 seeded-root cell red.
28. D9's unchanged prefix matcher no longer recognizes an exact file entry: AT-5
    `tests/unit/test_cli_surface.py` cell red.

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

V2-LOG (L-8): `tests/sentry/` has 28 direct entries before this slice. Adding the parity sentry
at the mapped `SENTRIES` path is accepted; the next new sentry family must use a named
sub-package rather than add another flat family.

## 8. After the merge (orchestrator, not the builder)

Already done: `~/bin/decoy-vm-t3-promote:15` maps `cli` to `REPO_NAME=decoy` (L6).

1. `~/bin/decoy-vm-t3-promote`:
   - `merged`: resolve `H` to its commit and tree, then walk `origin/main` in first-parent order
     from newest to oldest. Let `S` be the first commit whose tree equals H's tree; refuse before
     writing if no such commit exists. Pass `--main-sha S` to the copied reporter, keep
     `--head-sha H`, and make the final assertion compare the written `main_sha` with `S` rather
     than current main. Do not put `GENERATED_UNREAD_GLOBS`, a path pattern, or any other
     staleness relaxation in promote: on the next compare, the gate's single D5 implementation
     judges the move from `S` to current main. This works whether the diagram bot runs before or
     after promote without creating a second staleness rule.
   - `merged`: pass `--test-root ~/decoy/wt-<label>` to the copied reporter (D7, AT-13). Promote
     before another T3 run starts on that VM: `decoy-vm-t3:89` to `:95` deletes old
     `~/decoy/wt-*` and `/tmp/decoy-out-*` trees.
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

Before step 3, exercise the orchestrator change in a throwaway clone: (a) current main equals
the tested tree, (b) a later first-parent bot commit changes only an svg, and (c) no first-parent
tree equals H. The first two must select the expected `S`, write and assert `main_sha=S`; the
third must refuse without replacing the saved file. In both successful orders, run the CLI
reader and one compare after the bot move so D5, not promote, decides staleness.

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
   `GENERATED_UNREAD_GLOBS` (AT-5 svg cells); section 8 records the equal-tree first-parent
   commit and leaves the later move to the same D5 check.
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
- Carry back to the engine: D6 (copy first), D7 (`--test-root`) and D10 (full SHA shapes); the
  engine's promote route has the same copied-reporter shape.
- V2-LOG (L-9, inherited): `_ALLOWED_PY_ARGS` permits the sentry's `bash -c` forwarding wrapper
  without inspecting its inline program. Carry the catalog-class-10 gap with the engine; do not
  widen this slice for it.
- V2-LOG (catalog class 3, inherited): the engine's `load_baseline` raises its value-free
  `BaselineError` with an attached `__cause__` on JSON/read failures. A traceback is
  server-admin-only under the V1 bar; carry the cleanup with the engine rather than diverge the
  CLI port.
- V2-LOG: one gates package shared by engine, CLI and platform, instead of three ports. Until
  then, a fix to the engine reporter must be carried to the CLI copy by hand; the build record
  lists every intended difference so the next port can diff against it.
- Platform's `gates.sh` lacks P1's stale refusal and strict model (platform row, not this one).
