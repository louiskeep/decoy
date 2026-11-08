# CLI-MAC-TESTS: the CLI suite passes on macOS arm64

Status: plan

Roadmap row 5c (`docs/ROADMAP.md`). Repo `louiskeep/decoy` (CLI). Base: CLI `origin/main`
`b7009d1` (2026-11-08). Author: claudeworkerbee (Opus), 2026-11-08. Build handoff:
`10_Projects/decoy/handoffs/phase0.5/p05-cli-mac-tests-build-handoff.md` in the vault. Related:
row 5b CLI-BASELINE (`docs/plans/2026-11-08-cli-baseline.md` on `plan/cli-baseline`, Revision
2), which owns the bash 3.2 half of this row (orchestrator answer to its Q2).

Rules consulted: `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`,
`testing.md`, `reuse-first.md`, `cross-cutting-concerns.md`, `scope-discipline.md`,
`verification.md`, `workspace-and-vcs.md`, `documentation.md`.

Risk: R1 for slice S1 (test files and one test helper; no product code). R2 for slice S2 (one
line in the CLI's stderr console, which changes how every error line is laid out off a TTY).

## 1. Goal and guarantee

The CLI full suite fails on the Mac mini (macOS 15.1, arm64, `/bin/bash` 3.2.57) and passes on
Linux. Measured at `b7009d1` on 2026-11-08 (12 minutes, `PYTHONPATH=src`, engine 0.19.0 from
`requirements-dev.lock`): 16 failed, 2793 passed, 6 skipped.

Guarantee: after CLI-BASELINE and both slices of this plan merge, the CLI full suite on the Mac
has 0 failures, and on Linux the same ids pass and fail as before (no Linux id changes result).

Scope (orchestrator note, agent-task T0099): the 8 ids of
`tests/unit/test_dev_bootstrap_gates.py` are fixed by CLI-BASELINE (its `gates.sh` becomes bash
3.2 safe, AT-14 runs that file under `/bin/bash` on the Mac). This plan covers the other 8.

Non-goals:
- Installing bash 4 or anything else on the Mac (an owner option only; not needed).
- Certifying a DP proof stack on macOS (the engine refuses DP fits off Linux x86-64 by design).
- A macOS release bundle in the version document; the tests stop assuming the host is Linux.
- `gates.sh` (CLI-BASELINE).

## 1a. A measurement trap found on the way

The first Mac run gave 50 failures, not 16. The shared venv `~/decoy/venv-cli-mac` holds an
editable install of a different checkout (`_editable_impl_decoy_cli.pth` points at
`~/decoy/wt-cli-cdc/src`, at `05bf840`), so `import decoy` loaded that older tree: 32
`test_atomic_staged.py` ids failed on `ImportError: cannot import name 'staged_local_target'`,
plus a stale `cli-reference.md` and one `ci check` id. With `PYTHONPATH=src` the run imports the
checkout under test and those 34 go away. Every Mac acceptance run of this plan prints
`decoy.__file__` first and must show the checkout under test (handoff, Test depth).

## 2. Root cause per id

| # | Test id | What fails | Root cause | Class | Fix | Slice |
|---|---|---|---|---|---|---|
| 1 | `tests/e2e/test_dp_provenance_certification.py::test_dp_fit_matches_this_environments_certification_status` | `assert 'dp_platform_uncertified' == 'dp_stack_uncertified'` | the engine's `check_fit_environment` refuses a non-Linux platform first, with `dp_platform_uncertified`; the test only knows the stack arm (`test_dp_provenance_certification.py:60`) | test re-derives engine policy (drift) | one helper `tests/dp_env.py::expected_dp_refusal_code()` built on the engine's public `current_platform()` and `CERTIFIED_PLATFORM`; the test asserts its result | S1 |
| 2 | `tests/e2e/test_fit_command.py::TestFitDpFlagGrammar::test_cli_run_with_garbage_tokens_never_exits_usage_from_flag_content` | `'dp_stack_uncertified' in output` false | same: the fit reaches the gate and gets the platform code (`test_fit_command.py:472`) | same | same helper | S1 |
| 3 | `tests/e2e/test_fit_command.py::TestFitDpOmission::test_allow_omit_proceeds_past_the_omission_check` | same | same (`test_fit_command.py:535`) | same | same helper | S1 |
| 4 | `tests/e2e/test_fit_command.py::TestFitDpErrorFamilies::test_provenance_error_exits_runtime_with_dedicated_hint` | same | same (`test_fit_command.py:634`) | same | same helper | S1 |
| 5 | `tests/e2e/test_fit_command.py::TestFitDpErrorFamilies::test_provenance_error_json_has_code_message_and_hint` | `payload["code"] == 'dp_stack_uncertified'` false | same (`test_fit_command.py:642`) | same | same helper | S1 |
| 6 | `tests/unit/test_distribution.py::test_upgrade_force_recovers_retained_bundle_without_current` | exit 3, `version document lists no bundle for target macos-arm64` | the fixture serves only a `linux-x86_64` bundle (`test_distribution.py:539`, helpers at `:581` and `:619`), but `decoy upgrade` asks for the host's target (`src/decoy/distribution/installer.py:462`) | fixture hard-codes a host-detected value | the fixture serves the bundle for `targets.detect_target()` and skips on an unsupported host, as `test_distribution.py:1254` already does | S1 |
| 7 | `tests/unit/test_distribution.py::test_install_sh_refuses_wrong_version_without_installing_anything` | `'declares version'` not in output; install.sh refused earlier with `bundle declares target 'linux-x86_64' but this host is macos-arm64` | the bundle declares `linux-x86_64` (`test_distribution.py:776`); `install.sh` detects the host target (`packaging_tools/install/install.sh:155`) and its target check fires before the version check the test means to reach | same | the staged bundle declares `targets.detect_target()`; skip on an unsupported host | S1 |
| 8 | `tests/e2e/test_plan_command.py::test_with_invalid_profile_json` | `'Profile JSON'` not in output; the output has `pytes\nt-334` | `validate compile` prints the error text through the stderr Rich console (`src/decoy/cli/compile_explain.py:207`); off a TTY the width is 80 and Rich folds a word longer than the line, so the long macOS tmp path (`/private/var/folders/.../T/pytest-of-camkeep/...`) gains newlines and pushes the checked words apart | error text hard-folded at the console width | S2: the stderr console soft-wraps (`src/decoy/ui/output.py:39`), so error text is never folded; the test is not changed | S2 |

Ids 9 to 16 (CLI-BASELINE): `tests/unit/test_dev_bootstrap_gates.py` cells
`test_gates_baseline_reports_a_seeded_failure_as_branch_only`,
`test_gates_passes_a_green_run_with_an_evidence_block`,
`test_gates_fails_when_the_reporter_does_not_print_evidence[crashing|missing|nonzero|silent|truncated]`
and `test_gates_fails_when_no_step_ran[tests]`, all `scripts/dev/gates.sh: line 83:
PYTEST_ARGS[@]: unbound variable` under `/bin/bash` 3.2 with `set -u`. The task brief counted 9;
the 2026-11-07 failure note (vault `handoffs/phase1/cli-mac-tests-failures-2026-11-07.md`) and
this run both show 8. `test_gates_fails_when_no_step_ran[]` passes: with no steps, the line that
expands `PYTEST_ARGS` never runs.

Id 8 is the same class as agent-task T0097 (`tests/e2e/test_mask_secret_single_read.py`,
`[missing_source]`, red on a VM whose tmp path put the fold inside `absent.csv`). The T0097 fix
(branch `fix/mask-secret-missing-source`, `82421c2`, not merged) soft-wraps only `decoy run`'s
error prints. S2 closes the class for every command.

## 3. Behavior

| Case | Before | After |
|---|---|---|
| DP fit test on macOS | expects `dp_stack_uncertified`, gets `dp_platform_uncertified`, fails | expects the code the engine's gate raises on this host; passes |
| DP fit test on Linux x86-64 (uncertified dev venv) | expects and gets `dp_stack_uncertified` | unchanged |
| upgrade and install.sh tests on macOS | serve a Linux bundle to a host that asks for `macos-arm64`; fail | serve and declare the host target; pass |
| same tests on Linux x86-64 | `linux-x86_64` | unchanged (the host target is `linux-x86_64`) |
| same tests on an unsupported host (Intel Mac, Windows) | fail | skip with a reason |
| `decoy <cmd>` error text longer than 80 columns, stderr not a TTY (CI log, redirect, CliRunner) | folded at column 80, a newline inside paths | one line per print; the terminal or viewer wraps it |
| same, stderr is a TTY | folded at the terminal width by Rich | one line per print; the terminal soft-wraps it, so a copied path has no newline |

## 4. Design notes

- S1 changes tests only. The helpers follow existing patterns: `tests/keyed_secret.py` is the
  shared-constant helper beside which `tests/dp_env.py` goes, and the host-target skip copies
  `tests/unit/test_distribution.py:1254`.
- The DP helper mirrors the order of the engine's `check_fit_environment` (platform, then
  stack). To keep it from drifting, one new test calls the engine's own
  `dp_provenance.check_fit_environment()` and asserts it raises exactly the helper's code, or
  nothing when the helper says the row is certified. If the engine changes its order or codes,
  that test fails first, with a clear message.
- The fit tests keep asserting a refusal code; they do not skip on macOS. They still prove the
  CLI maps a provenance refusal to the runtime exit and the dedicated hint, on both platforms.
- The negative check at `tests/e2e/test_fit_command.py:906` (the name check fires before the
  gate) asserts that neither DP refusal code appears. Today it checks only the stack code, so on
  macOS it passes without testing anything.
- S2: `Console(soft_wrap=True)` for the stderr console in `_make_console`. Rich then prints each
  `print` call as one line and leaves wrapping to the terminal. Stdout keeps today's layout
  (summary tables and cards). The per-call `soft_wrap=True` arguments (`src/decoy/cli/run.py:223`
  and, if T0097 merges first, run's error handler) become redundant and are removed, so one
  place owns the rule.
- Choke point for S2: `_make_console(stderr=True)` is the only constructor of the stderr
  console (`setup_output`). Guard: a sentry that scans `src/` with `ast` and fails on any
  `Console(` call outside `src/decoy/ui/output.py` that writes to stderr, so a command cannot
  bring back a folding stderr console. Mutation: add `Console(stderr=True)` in a command module.

## 4a. Invariants

- On Linux, no test id changes result between the base and each slice head (same VM, same
  lock).
- A test that checks a refusal still checks one on every supported host; no test gains a skip
  on macOS arm64.
- Error text the CLI prints to stderr reaches the reader unbroken: no newline is inserted inside
  a word.

## 4b. Class table

| # | Class | Applies how | Closing structure | Proof (sentry or test) | Mutation that must turn it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | N/A: S1 changes tests; S2 changes layout, not content | n/a | AT-6 checks content is unchanged apart from line breaks | n/a |
| 2 | Cleanup missing on an exit path | N/A: no new resources; the distribution fixtures already use `tmp_path` | n/a | n/a | n/a |
| 3 | State machine and concurrency | N/A: no state or concurrency touched | n/a | n/a | n/a |
| 4 | Route parity and silent fallback | stderr prints come from many commands; one that builds its own console would fold again | one stderr console (`_make_console`) | AT-6 (run, validate compile, plan), AT-7 sentry | soft wrap dropped in `_make_console`: AT-6 red; a second `Console(stderr=True)`: AT-7 red |
| 5 | Referential integrity | N/A: no tables or keys | n/a | n/a | n/a |
| 6 | Untrusted producer | N/A: no new inputs | n/a | n/a | n/a |
| 7 | Check then use (TOCTOU) | N/A: no check-then-use | n/a | n/a | n/a |
| 8 | Weak tests and overclaimed evidence | the `:906` negative check passes vacuously on macOS; a Mac run that imports another checkout claims results for the wrong code | assert both codes absent; acceptance runs print `decoy.__file__` | AT-3, AT-8 | the `:906` assert back to the stack code only, with the helper patched to return the platform code: AT-3 red |
| 9 | Refactor drift | the DP helper restates the engine's gate order; a test fixture restates the host target | the drift test against `check_fit_environment` (AT-2); fixtures take `detect_target()` | AT-2, AT-4, AT-5 | helper returns the stack code on every host: AT-2 red on macOS; fixture back to `linux-x86_64`: AT-4 and AT-5 red on macOS |
| 10 | Frozen contract drift | the `--json` error envelope and exit codes of the touched commands | S2 changes only line layout of human output; JSON goes to stdout unchanged | AT-6 JSON cell, AT-9 Linux id parity | n/a (no contract changes) |

## 4c. Enumerations

### Exit paths

No exit code changes. The exits the touched tests check:
- `EXIT_RUNTIME` for a DP provenance refusal (`tests/e2e/test_fit_command.py:630`);
- exit 0 for `decoy upgrade --force` recovering a retained bundle;
- a non-zero `install.sh` exit before any slot is created;
- `EXIT_USAGE` (1) for a `--profile` file that is not a Profile JSON.

### Routes

- S1: the DP fit through `decoy fit` and a direct `fit_dp_snapshot` call; `decoy upgrade
  --force`; `packaging_tools/install/install.sh` offline path (`DECOY_LOCAL_BUNDLE`).
- S2: every command's stderr through `setup_output()` (`src/decoy/ui/output.py:48`); AT-6
  samples `run`, `validate compile` and `plan`.

### FK shapes

N/A: no data tables or foreign keys.

### Fields

N/A for data. The touched values: the DP refusal codes `dp_platform_uncertified` and
`dp_stack_uncertified`; the bundle target ids `linux-x86_64`, `linux-aarch64`, `macos-arm64`
(`src/decoy/distribution/targets.py:43`).

### Output surfaces

- stderr of every command (S2: line layout only).
- `--json` stdout envelopes: unchanged.
- Test files and `tests/dp_env.py` (S1).

## 4d. Reuse inventory

- `tests/keyed_secret.py`: the pattern for a shared test helper at `tests/` root.
- `tests/unit/test_distribution.py:1254`: the host-target skip, copied.
- Engine `decoy_engine.quality.dp_provenance` public `current_platform`, `CERTIFIED_PLATFORM`,
  `check_fit_environment`: used, not re-implemented beyond the two-arm order.
- `src/decoy/ui/output.py:_make_console`: the one stderr console, changed in place.
- `tests/sentry/`: the AST-scan sentry pattern of `test_atomic_writer.py:151`.

## 4e. Frozen contracts touched

- `decoy-ci/v1` and every `--json` envelope: not touched.
- Human stderr layout (S2): changes from folded at 80 columns (off a TTY) to one line per
  print. Not a frozen contract; listed so the orchestrator decides it (Q1).

## 5. Acceptance tests

| AT | Test | Red on base because |
|---|---|---|
| AT-1 | the 5 DP ids pass on the Mac and still pass on Linux | id 1 to 5 red on the Mac |
| AT-2 | new `tests/e2e/test_dp_provenance_certification.py::test_the_expected_code_helper_matches_the_engine_gate`: `check_fit_environment()` raises exactly `expected_dp_refusal_code()`, or nothing when it returns `None` | helper missing |
| AT-3 | the `:906` cell asserts neither DP code appears | checks one code |
| AT-4 | `test_upgrade_force_recovers_retained_bundle_without_current` passes on the Mac and Linux | red on the Mac |
| AT-5 | `test_install_sh_refuses_wrong_version_without_installing_anything` passes on the Mac and Linux and still asserts `declares version` | red on the Mac |
| AT-6 | new e2e: a missing source, a bad `--profile`, and a missing pipeline file, each under a 90-character directory, through `run`, `validate compile` and `plan`; the raw stderr contains the whole path; with `--json` the envelope is byte-identical to the base's | folded on the base |
| AT-7 | new sentry `tests/sentry/test_one_stderr_console.py`: no `Console(` with `stderr=True` in `src/` outside `src/decoy/ui/output.py` | sentry missing |
| AT-8 | `test_with_invalid_profile_json` passes on the Mac unchanged | red on the Mac |
| AT-9 | Linux parity: the full suite on one VM at the base and at each slice head; the only id changes are the new tests | n/a |
| AT-10 (acceptance) | Mac full suite: 0 failures, with CLI-BASELINE merged, `decoy.__file__` printed and inside the checkout under test; Linux unchanged (AT-9) | 16 failures |

## 6. Placement

| File | Directory | Change | Slice |
|---|---|---|---|
| `dp_env.py` | `tests/` | new helper, beside `keyed_secret.py` | S1 |
| `test_dp_provenance_certification.py` | `tests/e2e/` | use the helper; AT-2 cell | S1 |
| `test_fit_command.py` | `tests/e2e/` | lines 472, 535, 634, 642, 906 | S1 |
| `test_distribution.py` | `tests/unit/` | the two tests and the helpers at `:581`, `:619` take the host target | S1 |
| `output.py` | `src/decoy/ui/` | `_make_console`: stderr soft-wraps | S2 |
| `run.py` | `src/decoy/cli/` | drop the now-redundant per-call `soft_wrap=True` | S2 |
| `test_stderr_unfolded.py` | `tests/e2e/` | AT-6 | S2 |
| `test_one_stderr_console.py` | `tests/sentry/` | AT-7; one `SENTRIES` line in `test_sentry_manifest.py` | S2 |

## 7. Slices

- S1 (R1, tests only, about 80 lines): ids 1 to 7, AT-1 to AT-5. Lands on its own.
- S2 (R2, about 60 lines): id 8, AT-6 to AT-8. Needs Q1 answered first. If T0097's branch merges
  first, S2 removes its per-call arguments; if S2 merges first, T0097's branch is dropped.

AT-10 is checked once all of CLI-BASELINE, S1 and S2 are on main.

## 7a. Pre-mortem

1. The helper is right today and the engine reorders its checks later: AT-2 calls the engine's
   own gate.
2. A Linux run silently changes because the helper returns a different code there: AT-9 parity
   and AT-1's Linux half.
3. An Intel Mac or Windows runner starts failing on the target fixtures: they skip with the
   reason the existing `:1254` test uses.
4. S2 changes a stderr line a test matches with an exact multi-line string: AT-9 parity catches
   it; STEP ZERO greps for tests that match stderr across a newline.
5. A Mac run reports results for the wrong checkout again: AT-10 prints `decoy.__file__`.
6. S2 makes a long hint unreadable in a narrow terminal: the terminal soft-wraps; Rich's indent
   of a wrapped hint line is lost (Q1 names this).

## 8. Questions (recommended answer first)

- Q1 (orchestrator): S2 changes every command's stderr layout. Recommended: soft-wrap the stderr
  console in `_make_console` (one place, closes the class; the loss is Rich's hanging indent on
  long hint lines in a terminal). Alternative: per-site `soft_wrap=True` on every print of
  non-authored error text (there are 138 `err_console.print` calls in `src/`; the build's STEP
  ZERO counts how many print exception text), with the sentry checking those calls instead. That keeps authored copy folded but leaves the rule spread
  across files.
- Q2 (orchestrator): the shared Mac venv `~/decoy/venv-cli-mac` is an editable install of
  `~/decoy/wt-cli-cdc`. Recommended: Mac CLI runs set `PYTHONPATH=<checkout>/src` (what this
  plan's runs did) or use a per-checkout venv; the run scripts print `decoy.__file__`. This is
  orchestrator tooling, outside the repo.

## 9. Follow-ups

- If Q1 picks per-site, a sentry that every `err_console.print` of a non-literal text passes
  `soft_wrap=True`.
- A Mac lane in hosted CI (the `decoyci` self-hosted runner exists) so a Linux-only assumption
  fails at PR time instead of on the next Mac run.
