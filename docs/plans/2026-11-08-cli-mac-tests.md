# CLI-MAC-TESTS: the CLI suite passes on macOS arm64

Status: plan, Revision 2 (2026-11-08; Dennis round 1 NO-GO folded in; not gated yet: Dennis
round 2, then Codex)

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

## 0. Revision 2 (Dennis round 1, `p05-cli-mac-tests-dennis-r1.md` in the vault)

Checked again on CLI `origin/main` `b6e0437` (one roadmap commit after `b7009d1`, no file this
plan touches), engine pin `4a0d5b1f`, rich 15.0.0.

| Finding | Change |
|---|---|
| H1 helper default target | `_serve_bundle` and `_doc_for_latest` gain `target: str = "linux-x86_64"`; the stage directory, the tarball name, the `BUNDLE_INFO` and manifest default and the document's artifact key use it. Only ids 6 and 7 pass `targets.detect_target()`, and only they skip on an unsupported host. New invariant: no other test in `test_distribution.py` changes result on the Mac (sections 2, 4, 4a, 5, 6). |
| H2 mutation 2 cannot go red | AT-3 is parametrized `host` / `foreign` (`foreign` monkeypatches `dp_provenance.current_platform` to a non-certified triple). The mutation is now a product change: disable the `dp_schema_column_missing` branch in `src/decoy/cli/fit.py` (`:455-466`). Both AT-3 cells go red on Linux; the old stack-only line stays green in the `foreign` cell, recorded as the before and after proof (sections 4, 4b, 5). |
| H3 AT-6 not deterministic; JSON half not a test | AT-6 sets `COLUMNS=80` and records the base fold as its red; the `--json` half asserts named fields (exact key set, `code`, the whole path inside `message`) instead of a byte comparison with another run (section 5). |
| H4 rulings not carried | Q1 and Q2 recorded as decided (section 8). S2 names every per-call `soft_wrap=True` it removes, keeps T0097's test cell, and takes that cell into its allowed files if S2 builds first. Codex's two further folded prints on `82421c2` (`run.py:528`, `:1730`) are listed; the one console covers them (sections 4, 6, 7). |
| M1 sentry spellings | AT-7 fails on any construction of `rich.console.Console` outside `src/decoy/ui/output.py` after resolving import aliases, on `rich.print(..., file=...)`, and on `soft_wrap=False` passed to an `err_console.print`; one seeded case per shape (sections 4, 5). |
| M2 TTY side effects | Section 3 lists traceback, `Progress`, `Live` and `Panel`/`Table` behavior; `_make_console` docstring states the stderr console is for lines; AT-7 refuses a direct `Panel(` or `Table(` argument to `err_console.print`; pre-mortem 6 rewritten. |
| M3 helper contract | `expected_dp_refusal_code()` returns `None` on a certified row (it owns the one copy of `_current_row_is_certified`, moved from the certification test), else the platform code when `current_platform() != CERTIFIED_PLATFORM`, else the stack code. Fit tests use `expected_dp_refusal_code_required()`, which fails loudly on a certified venv. The private `_CERTIFIED_STACKS` reach is pre-existing (section 4). |
| M4 Linux never runs the platform arm | AT-2 gains a `foreign` cell: with `current_platform` forced to a foreign triple, the helper and `check_fit_environment()` both give `dp_platform_uncertified`; mutation 1 now goes red on the VM (sections 4, 5). |
| M5 flat e2e folder | AT-6 cells go into `tests/e2e/test_output_modes.py` (159 lines, already imports `_make_console`); no new module in `tests/e2e/` (82 entries) (section 6). |
| L1 to L3 | Section 11 (V2-LOG). |

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
| 6 | `tests/unit/test_distribution.py::test_upgrade_force_recovers_retained_bundle_without_current` | exit 3, `version document lists no bundle for target macos-arm64` | the fixture serves only a `linux-x86_64` bundle (`test_distribution.py:539`, helpers at `:581` and `:619`), but `decoy upgrade` asks for the host's target (`src/decoy/distribution/installer.py:462`) | fixture hard-codes a host-detected value | `_serve_bundle` and `_doc_for_latest` gain a `target` keyword (default `linux-x86_64`, so their other callers are unchanged); this test alone passes `targets.detect_target()` to both and to its own `install_version(target=...)` at `:539`, and skips on an unsupported host as `test_distribution.py:1254` does | S1 |
| 7 | `tests/unit/test_distribution.py::test_install_sh_refuses_wrong_version_without_installing_anything` | `'declares version'` not in output; install.sh refused earlier with `bundle declares target 'linux-x86_64' but this host is macos-arm64` | the bundle declares `linux-x86_64` (`test_distribution.py:776`); `install.sh` detects the host target (`packaging_tools/install/install.sh:155`) and its target check fires before the version check the test means to reach | same | this test's staged bundle (`BUNDLE_INFO` and manifest at `:776-778`) declares `targets.detect_target()`; it skips on an unsupported host | S1 |
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
(branch `fix/mask-secret-missing-source`, `82421c2`, in the double gate) soft-wraps five of
`decoy run`'s error prints. Codex found two more on that head that still fold (`run.py:528`,
the `NotifySpecError` message, and `:1730`, `notify dispatch failed: {exc}`). S2 closes the class
for every print of every command.

## 3. Behavior

| Case | Before | After |
|---|---|---|
| DP fit test on macOS | expects `dp_stack_uncertified`, gets `dp_platform_uncertified`, fails | expects the code the engine's gate raises on this host; passes |
| DP fit test on Linux x86-64 (uncertified dev venv) | expects and gets `dp_stack_uncertified` | unchanged |
| upgrade and install.sh tests on macOS | serve a Linux bundle to a host that asks for `macos-arm64`; fail | serve and declare the host target; pass |
| same tests on Linux x86-64 | `linux-x86_64` | unchanged (the host target is `linux-x86_64`) |
| same tests on an unsupported host (Intel Mac, Windows) | fail | skip with a reason |
| `decoy <cmd>` error text longer than 80 columns, stderr not a TTY (CI log, redirect, CliRunner) | folded at column 80, a newline inside paths | one line per print; the terminal or viewer wraps it |
| same, stderr is a TTY | folded at the terminal width by Rich | one line per print; the terminal soft-wraps it, so a copied path has no newline. Rich's hanging indent on a wrapped hint line is lost |
| `--verbose` traceback (`print_exception`, `run.py:1131`, `scan.py:803`) | panel at terminal width; the final exception line folds | panel unchanged; the final line no longer folds |
| `Progress` bars (`ui/progress.py:45`, `:78`, `:153`) | columns cropped to width | byte-identical (measured on rich 15.0.0) |
| `Live` view (`ui/storm_animation.py:176`), TTY narrower than a stage label | label wraps | label is cropped at the terminal width in the transient view; cursor math is unchanged, nothing flickers or repeats |
| a `Panel` or `Table` printed to the stderr console | wraps cell text | would crop cell text silently. None is printed there today (`card.py:60`, `banner.py:60`, `explain.py:553` use stdout); `_make_console`'s docstring and AT-7 keep it that way |
| exit codes, `--json` envelopes (`emit_json` writes `sys.stdout`) | unchanged | unchanged |

## 4. Design notes

- S1 changes tests only. The helpers follow existing patterns: `tests/keyed_secret.py` is the
  shared-constant helper beside which `tests/dp_env.py` goes, and the host-target skip copies
  `tests/unit/test_distribution.py:1254`.
- `tests/dp_env.py` contract:
  - `current_row_is_certified() -> bool`: the one copy of today's `_current_row_is_certified`
    (`test_dp_provenance_certification.py:44-49`, moved, not duplicated). It reads the private
    `dp_provenance._CERTIFIED_STACKS`; that reach is pre-existing, and a public engine
    `is_certified_row()` is V2-LOG.
  - `expected_dp_refusal_code() -> str | None`: `None` when the row is certified; else
    `dp_platform_uncertified` when `dp_provenance.current_platform() != CERTIFIED_PLATFORM`; else
    `dp_stack_uncertified`. It calls `current_platform` through the module attribute
    (`dp_provenance.current_platform()`, never `from ... import current_platform`), the same
    lookup `check_fit_environment` makes, so one monkeypatch moves both.
  - `expected_dp_refusal_code_required() -> str`: the same, but fails the test with "this venv
    is a certified DP row; the refusal tests do not apply" instead of returning `None`. The fit
    tests (ids 2 to 5) use it, so a certified venv fails loudly instead of asserting
    `None in output`.
- The DP helper mirrors the order of the engine's `check_fit_environment` (platform, then
  stack). AT-2 calls the engine's own gate and asserts it raises exactly the helper's code, or
  nothing when the helper returns `None`, on the host and with the platform forced foreign. If
  the engine changes its order or codes, AT-2 fails first.
- Distribution helpers: `_serve_bundle(..., target: str = "linux-x86_64", declared_target: str |
  None = None)` (`declared_target` defaults to `target`) and `_doc_for_latest(..., target: str =
  "linux-x86_64")`. The about 10 other callers (`:644`, `:675`, `:693`, `:720`, `:751`, `:815`,
  `:1028`, `:1333`, `:1527`, `:1559`) pass nothing and keep asking `install_version` for
  `linux-x86_64` explicitly, so they behave the same on every host. The skip lives in ids 6 and 7
  only, never in a helper.
- The fit tests keep asserting a refusal code; they do not skip on macOS. They still prove the
  CLI maps a provenance refusal to the runtime exit and the dedicated hint, on both platforms.
- The negative check at `tests/e2e/test_fit_command.py:906` (the name check fires before the
  gate) asserts that neither DP refusal code appears. Today it checks only the stack code, so on
  macOS it passes without testing anything. The cell is parametrized: `host` as today, and
  `foreign` with `dp_provenance.current_platform` monkeypatched to a copy of
  `CERTIFIED_PLATFORM` with one field changed. The `foreign` cell exercises the platform arm on
  Linux too.
- S2: `Console(soft_wrap=True)` for the stderr console in `_make_console` (decided, Q1). Rich
  then prints each `print` call as one line and leaves wrapping to the terminal. Stdout keeps
  today's layout (summary tables and cards). `_make_console`'s docstring says the stderr console
  is for lines: no `Panel` or `Table` goes to it.
- S2 removes the per-call `soft_wrap=True` arguments the console makes redundant, so one place
  owns the rule: `src/decoy/cli/run.py:223` on main, and, when T0097's `82421c2` is on main,
  its five sites `run.py:1116`, `:1119`, `:1128`, `:1130`, `:1169` and the comment at `:1110`.
  `run.py:528` and `:1730` on that head carry no argument and are covered by the console.
- Choke point for S2: `_make_console` is the only constructor of a Rich console in `src/` (one
  `Console(` today, `output.py:39`). Guard AT-7: an `ast` scan of `src/` that resolves import
  aliases and fails on (a) any construction of `rich.console.Console` outside
  `src/decoy/ui/output.py`, in every spelling: `Console(...)`, `from rich.console import Console
  as C; C(...)`, `rich.console.Console(...)`, `import rich.console as rc; rc.Console(...)`;
  (b) `rich.print(..., file=...)` or an aliased `from rich import print`; (c) `soft_wrap=False`
  passed to any `*.err_console.print(...)`; (d) a direct `Panel(` or `Table(` argument to
  `*.err_console.print(...)`. Each shape has one seeded case in the sentry's self-test. Known
  limit, stated in the sentry docstring: a `Panel` held in a variable and printed later is not
  seen.

## 4a. Invariants

- On Linux, no test id changes result between the base and each slice head (same VM, same
  lock).
- A test that checks a refusal still checks one on every supported host; no test gains a skip
  on macOS arm64.
- No test in `tests/unit/test_distribution.py` other than ids 6 and 7 changes result on the Mac
  (H1).
- Error text the CLI prints to stderr reaches the reader unbroken: no newline is inserted inside
  a word.

## 4b. Class table

| # | Class | Applies how | Closing structure | Proof (sentry or test) | Mutation that must turn it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | N/A: S1 changes tests; S2 changes layout, not content | n/a | AT-6 checks content is unchanged apart from line breaks | n/a |
| 2 | Cleanup missing on an exit path | N/A: no new resources; the distribution fixtures already use `tmp_path` | n/a | n/a | n/a |
| 3 | State machine and concurrency | N/A: no state or concurrency touched | n/a | n/a | n/a |
| 4 | Route parity and silent fallback | stderr prints come from many commands; one that builds its own console would fold again | one stderr console (`_make_console`) | AT-6 (run, validate compile, plan), AT-7 sentry | soft wrap dropped in `_make_console`: AT-6 red; a second console in any AT-7 spelling, `soft_wrap=False` on an `err_console.print`, or a `Panel(` printed to it: AT-7 red |
| 5 | Referential integrity | N/A: no tables or keys | n/a | n/a | n/a |
| 6 | Untrusted producer | N/A: no new inputs | n/a | n/a | n/a |
| 7 | Check then use (TOCTOU) | N/A: no check-then-use | n/a | n/a | n/a |
| 8 | Weak tests and overclaimed evidence | the `:906` negative check passes vacuously on macOS; a Mac run that imports another checkout claims results for the wrong code | assert both codes absent, on the host and with the platform forced foreign; acceptance runs print `decoy.__file__` | AT-3, AT-10 | disable the `dp_schema_column_missing` branch in `fit.py`: both AT-3 cells red on Linux; the old stack-only line stays green in the `foreign` cell (recorded) |
| 9 | Refactor drift | the DP helper restates the engine's gate order; a test fixture restates the host target | the drift test against `check_fit_environment` (AT-2); fixtures take `detect_target()` | AT-2, AT-4, AT-5 | helper returns the stack code on every host: AT-2 `foreign` cell red on Linux and both cells red on macOS; fixture back to `linux-x86_64`: AT-4 and AT-5 red on macOS |
| 10 | Frozen contract drift | the `--json` error envelope and exit codes of the touched commands | S2 changes only line layout of human output; JSON goes to stdout unchanged | AT-6 JSON cells (named fields), AT-9 Linux id parity | n/a (no contract changes) |

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
  print. Not a frozen contract; the orchestrator accepted it (Q1, decided).

## 5. Acceptance tests

| AT | Test | Red on base because |
|---|---|---|
| AT-1 | the 5 DP ids pass on the Mac and still pass on Linux | id 1 to 5 red on the Mac |
| AT-2 | new `tests/e2e/test_dp_provenance_certification.py::test_the_expected_code_helper_matches_the_engine_gate`, cells `host` and `foreign` (`current_platform` monkeypatched to a non-certified triple): `check_fit_environment()` raises exactly `expected_dp_refusal_code()`, or nothing when it returns `None`; the `foreign` cell's code is `dp_platform_uncertified` on every host | helper missing |
| AT-3 | the `:906` cell, parametrized `host` / `foreign`, asserts exit `EXIT_USAGE`, `dp_schema_column_missing` and `amt` in the output, and neither DP code | checks one code; the `foreign` cell does not exist |
| AT-4 | `test_upgrade_force_recovers_retained_bundle_without_current` passes on the Mac and Linux; every other `test_distribution.py` id keeps its result on the Mac (base and head ids compared in the same Mac folder) | red on the Mac |
| AT-5 | `test_install_sh_refuses_wrong_version_without_installing_anything` passes on the Mac and Linux and still asserts `declares version` | red on the Mac |
| AT-6 | new cells in `tests/e2e/test_output_modes.py`, `monkeypatch.setenv("COLUMNS", "80")`: a missing source, a bad `--profile`, and a missing pipeline file, each under a 90-character directory, through `run`, `validate compile` and `plan`; the raw stderr contains the whole path on one line. The `--json` cells parse stdout and assert the exact key set, `code`, and the whole path inside `message`. The base run's fold (a newline inside the path) is the recorded red | folded on the base |
| AT-7 | new sentry `tests/sentry/test_one_stderr_console.py`: shapes (a) to (d) of section 4 on `src/`, alias-resolved, each with one seeded case | sentry missing |
| AT-8 | `test_with_invalid_profile_json` passes on the Mac unchanged; T0097's `test_run_validate_always.py::test_a_long_path_in_run_error_text_is_printed_whole` passes unchanged on S2's head | red on the Mac |
| AT-9 | Linux parity: the full suite on one VM at the base and at each slice head; the only id changes are the new tests | n/a |
| AT-10 (acceptance) | Mac full suite: 0 failures, with CLI-BASELINE merged, `decoy.__file__` printed and inside the checkout under test; Linux unchanged (AT-9) | 16 failures |

## 6. Placement

| File | Directory | Change | Slice |
|---|---|---|---|
| `dp_env.py` | `tests/` | new helper, beside `keyed_secret.py` | S1 |
| `test_dp_provenance_certification.py` | `tests/e2e/` | use the helper; AT-2 cell | S1 |
| `test_fit_command.py` | `tests/e2e/` | lines 472, 535, 634, 642, 906 | S1 |
| `test_distribution.py` | `tests/unit/` | `_serve_bundle` (`:581`) and `_doc_for_latest` (`:619`) gain a `target` keyword defaulting to `linux-x86_64`; ids 6 and 7 pass `detect_target()` and skip on an unsupported host | S1 |
| `output.py` | `src/decoy/ui/` | `_make_console`: stderr soft-wraps | S2 |
| `run.py` | `src/decoy/cli/` | drop the per-call `soft_wrap=True` at `:223` and, with T0097 on main, its five sites and comment | S2 |
| `test_output_modes.py` | `tests/e2e/` | AT-6 cells (no new module in the 82-entry folder) | S2 |
| `test_run_validate_always.py` | `tests/e2e/` | only if S2 builds before T0097 merges: add T0097's `test_a_long_path_in_run_error_text_is_printed_whole` unchanged | S2 |
| `test_one_stderr_console.py` | `tests/sentry/` | AT-7; one `SENTRIES` line in `test_sentry_manifest.py` | S2 |

## 7. Slices

- S1 (R1, tests only, about 80 lines): ids 1 to 7, AT-1 to AT-5. Lands on its own.
- S2 (R2, about 90 lines): id 8, AT-6 to AT-8. Q1 is decided (one console). If T0097's branch
  merges first, S2 removes its five per-call arguments and keeps its test unchanged. If S2 builds
  first, S2 carries T0097's test cell and the orchestrator drops T0097's `run.py` change.

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
6. S2 changes TTY rendering beyond plain lines: measured on rich 15.0.0, tracebacks and
   `Progress` are unchanged, a `Live` stage label wider than the terminal is cropped instead of
   wrapped (transient view only), and a `Panel` or `Table` on stderr would crop silently. None is
   printed there; the `_make_console` docstring and AT-7 (d) keep it so. The hanging indent of a
   wrapped hint line is lost.

## 8. Decisions (orchestrator, agent-task T0112, 2026-11-08)

- Q1, decided: one stderr console, soft-wrapped in `_make_console`, guarded by the AT-7 sentry.
  S2 takes over the per-site `soft_wrap=True` from `fix/mask-secret-missing-source` if that
  merges first and keeps its test.
- Q2, decided: the orchestrator's Mac runs already set `PYTHONPATH=<checkout>/src`; no script
  change. The build still prints `decoy.__file__` before every Mac run.

## 9. Follow-ups

- A Mac lane in hosted CI (the `decoyci` self-hosted runner exists) so a Linux-only assumption
  fails at PR time instead of on the next Mac run.

## 10. What this plan did not verify

- No Mac run of the revised cells. Ids 1 to 8 were red on the Mac at `b7009d1`; whether AT-5
  then reaches the version check is taken from the failure text (`install.sh` past the target
  check uses macOS `openssl` and `shasum`).
- The full-suite numbers (16 failed, 2793 passed, 6 skipped) are from one Mac run.
- STEP ZERO 3 (stderr asserted across a line break) is left to the builder.

## 11. LOW findings (V2-LOG)

- L1: `src/decoy/cli/explain.py:402-403` says the fit "refuses with dp_stack_uncertified" on an
  uncertified host; on macOS it is `dp_platform_uncertified`. A copy fix outside this slice.
- L2: the host-target skip will exist three times in `test_distribution.py` (`:1254` plus ids 6
  and 7). A module fixture `host_target` would be one place. Optional; the builder may take it
  if it stays inside the file.
- L3: no AT covers stderr on a TTY. A cell with `force_terminal=True` through `_make_console` is
  cheap. Optional.
