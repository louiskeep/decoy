Status: record

# CLI-BASELINE build record (roadmap row 5b)

Handoff `p05-cli-baseline-build-handoff.md`, plan `docs/plans/2026-11-08-cli-baseline.md` (Revision 3, on
`plan/cli-baseline`). Branch `feat/cli-baseline` from CLI `origin/main` `b6e0437`. Port source: engine
`origin/main` `b5b1ad16` (`scripts/dev/gates.sh`, `_gates_report.py`, `_gates_baseline.py`, the
`tests/unit/scripts` harness and baseline tests, `tests/sentry/test_bash32_compat.py`).

## Step zero

1. Engine `origin/main` is still `b5b1ad16`; no commit touched the gates scripts or their tests since.
2. Bash 4 constructs on the base: `gates.sh` 11 (`mapfile` at :71, ten bare array expansions), `bootstrap.sh`
   one (:43); `lock.sh` and `lock_version.sh` none. Markdown readers name the file literally (`README.md`,
   `cli-reference.md`, `ci-contracts.md`, `sbom.md`, `versioning.md`, plan docs). The only tests that walk a
   tree are `tests/sentry/test_baseline_registry.py:101` (json and toml, and it is a sentry),
   `test_surface_docs_consistency.py:278` (`src` only) and tmp-dir walks, so `DOC_WALK_ROOTS=()` holds.
   The only workflow that commits to main is `regen-diagrams.yml:65-66`, writing `classes_decoy.svg`,
   `deps.svg`, `packages_decoy.svg`; no test names an svg basename (`test_ci_lock_installs.py` names the
   workflow file only). `GENERATED_UNREAD_GLOBS=('docs/diagrams/*.svg')` holds.
3. Whole-suite `--collect-only -q` on a VM: 2815 tests. Refusal pattern ` at 0x[0-9a-fA-F]+>`: 0 hits.
   Broad audit pattern `0x[0-9a-fA-F]{6,}`: 0 hits. The only other numeric-looking ids are fixed
   integer literals in `test_canonical_int_strings`. No STOP.
4. Last 40 first-parent commits of `b6e0437`: 15 code, 15 Markdown (alone or with svg), 10 svg-only. 24 of
   the 40 leave a stored file usable under the final rules (the plan counted 23 on `b7009d1`; the window
   moved by the merges since).
5. CLI-only behavior kept: `FORMAT_GATE=0` and empty `MYPY_ARGS` SKIP lines, the four `SENTRY_PATHS`,
   `PYPATH_DIRS=(src)`, `IMPORT_PKG=decoy`, the `changed vs origin/main: N test file(s)` wording, plain
   `ruff check`, no `DECOY_GATE_VENV_STRICT`, D1.

## Red first

Commit `fb2a397` (tests only) against the unmodified scripts: 143 failed, 51 passed, 1 error. The error is
`test_gates_step_collects_every_sentry`, which also fails on the devbox venv (old engine) and is green on a
VM. The 51 passes are the pins (AT-15 `test_dev_bootstrap_gates.py`, AT-17 header cells, the guard's seeded
readers, the seeded `test_bash32_compat` snippets, `lock.sh`, `lock_version.sh`).

## Acceptance tests

All in `tests/unit/scripts/test_gates_baseline_file.py` (B) or `test_gates_legacy_verdict.py` (L).

| AT | Where | Red on base | Green on head |
|---|---|---|---|
| 1, 2, 3 | B `test_write_baseline_*` | flag unknown | yes |
| 4 | B `test_baseline_file_*` | flag unknown | yes |
| 5 | B `test_a_baseline_behind_*`, `..._holding_a_sentry_failure_...` | flag unknown | yes |
| 6 | B `..._another_run_mode_...`, `..._not_in_collection_order_...` | flag unknown | yes |
| 7 | B `..._wrongly_typed_or_shaped_field_...`, `..._without_the_run_mode_fields_...` | flag unknown | yes |
| 8, 9 | B `test_a_run_that_collects_ten_fewer...`, `..._deleted_the_test_file...`, `..._skips_more...` | flag unknown | yes |
| 10 | B `*_totals_*`, `*_zero_test_junit` | no cross-check | yes |
| 11 | B `..._smuggled_in_through_the_environment` | flag unknown | yes |
| 12 | L `test_an_inherited_test_*` | keyed by file | yes |
| 13 | L `test_a_reporter_copied_outside_*`, `test_a_test_root_that_is_not_a_directory_*` | subcommand missing | yes |
| 14 | `tests/sentry/test_bash32_compat.py` | `mapfile`, bare expansions | yes |
| 15 (pin) | `tests/unit/test_dev_bootstrap_gates.py` unchanged | green | green |
| 16 | L `test_gates_sh_runs_python_only_*`, `test_the_gates_sh_guard_refuses_each_seeded_reader` | `python -c` in gates.sh | yes |
| 17 (pin) | L `test_the_header_keeps_*`, `test_an_explicit_path_*`, `test_the_sentry_step_*` | green | green |
| 18a, 18b | B `test_the_stored_file_is_copied_before_it_is_checked`, `..._not_read_again_after_the_copy` | flag unknown | yes |
| 19 | L legacy cells | legacy fails on shared failures | yes |
| 20 | B `..._memory_address`, `..._literal_hex_parameter` | flag unknown | yes |

Two cells that the handoff did not list by name: `test_baseline_mode_keeps_going_after_a_failing_step` (L) runs
`--baseline` without `--keep-going` against a failing ruff and counts both sides' pytest calls (the engine's
version greps the script text); `test_default_format_ruff_output_stays_branch_only` (L) pins the fail-closed
edge of C1.

## Mutations

Round 2 rerun: every mutation below was applied to a scratch clone of head `f07162d` (the log line of each
run reads `@ f07162d`), run against the named tests, and reset in the scratch clone. The worktree was never
mutated and nothing was committed from a mutation. All 37 rows (counting 16a and 16b) went red; the rerun
used the updated code (`store_baseline`, the `--steps` operand check, the provenance shape check). The script
`mutate2.py` is not committed.

| # | Mutation | Red test |
|---|---|---|
| 1 | failure text appended to stored ids | `test_write_baseline_stores_the_failing_ids_and_the_run_mode` |
| 2 | merge-base tree dropped from `cleanup` | `test_a_branch_that_deleted_the_test_file_holding_those_ids_passes` |
| 3 | compare accepts a selection | `test_baseline_file_fails_without_a_completed_whole_suite_run` (3 cells) |
| 4 | `main_sha` renamed in the model | `test_write_baseline_stores_...`, `test_a_reporter_copied_outside_...` |
| 5 | write allowed for a selection | `test_write_baseline_refuses_a_selection` (3 cells) |
| 6 | `GENERATED_UNREAD_GLOBS` ignored | `test_a_baseline_behind_an_unread_generated_svg_is_used` |
| 7 | stale check warns instead of exiting | `test_a_baseline_behind_a_code_move_of_main_is_refused` |
| 8 | named Markdown treated as harmless | `test_a_baseline_behind_a_markdown_a_test_names_is_refused` |
| 9 | `DOC_WALK_GUARDS` empty | `test_a_baseline_holding_a_sentry_failure_is_stale_after_any_move` (4 cells) |
| 10 | bool accepted as a count | `test_a_baseline_with_a_wrongly_typed_or_shaped_field_is_refused` (4 cells) |
| 11 | shrink rule dropped | `test_a_run_that_collects_ten_fewer_ids_...`, `..._deleted_the_test_file_...` |
| 12 | skip rule dropped | `test_baseline_file_fails_when_the_branch_skips_more_than_the_baseline` |
| 13 | totals cross-check dropped | `test_write_baseline_refuses_when_pytest_totals_disagree_with_the_junit` |
| 14 | environment scrub dropped | `test_write_baseline_ignores_a_selection_smuggled_in_through_the_environment` (2) |
| 15 | address refusal dropped | `test_write_baseline_refuses_an_id_with_a_default_repr_memory_address` |
| 16a | check `$BASEFILE` before copying | `test_the_stored_file_is_copied_before_it_is_checked` |
| 16b | `$BASEFILE` copied again after the run | `test_the_stored_file_is_not_read_again_after_the_copy` |
| 17 | `--test-root` ignored | `test_a_reporter_copied_outside_the_repo_writes_the_same_file_as_a_gates_run` |
| 18 | legacy fails on shared failures | `test_gates_baseline_passes_when_the_only_failure_is_shared_with_main` |
| 19 | inline `python -c` JSON read in `gates.sh` | `test_gates_sh_runs_python_only_through_allow_listed_programs` |
| 20 | D1 dropped (missing path exits 2) | `test_dev_bootstrap_gates.py::test_gates_fails_when_no_step_ran` (2 cells) |
| 21 | `mapfile` back in `gates.sh` | `test_bash32_compat.py::test_dev_scripts_avoid_bash4_features[gates.sh]` |
| 22 | ids keyed by the defining file | `test_an_inherited_test_is_keyed_by_the_collected_module`, `..._has_a_rerunnable_id` |
| 23 | write allowed from a dirty or non-main HEAD | `test_write_baseline_refuses_a_head_that_is_not_a_clean_origin_main` (2) |
| 24 | SHA validator dropped | `test_a_baseline_with_a_wrongly_typed_or_shaped_field_is_refused` (SHA cells) |
| 25 | non-directory `--test-root` accepted | `test_a_test_root_that_is_not_a_directory_exits_64_and_writes_nothing` (2) |
| 26 | C2 keep-going force dropped | `test_baseline_mode_keeps_going_after_a_failing_step` |
| 27 | `DOC_WALK_ROOTS` ignored | `test_a_baseline_behind_a_markdown_in_a_doc_walk_root_is_refused` |
| 28 | exact-file entry not matched | `test_a_baseline_holding_a_sentry_failure_is_stale_after_any_move` (3 cells) |
| 29 | `--no-renames` dropped from the staleness diff | `test_a_rename_of_a_test_file_into_markdown_makes_the_baseline_stale` |
| 30 | head tree not compared with main's tree | `test_a_baseline_head_must_have_the_tree_of_its_main[other-tree]` |
| 31 | a flag token accepted as an operand (all three flags) | `test_a_baseline_flag_without_its_file_operand_exits_2[next-token-is-a-flag]` (2), `test_steps_without_its_operand_exits_2[next-token-is-a-flag]` |
| 32 | `raise` inside the `except` of `load_baseline` (sets `__context__`) | `test_the_unreadable_json_error_carries_no_exception_context` |
| 33 | writer skips the provenance check | `test_a_write_whose_head_has_another_tree_than_main_is_refused`, `..._naming_a_commit_the_repo_lacks_...`, `..._without_a_test_root_writes_nothing`, the malformed-SHA cells |
| 34 | an unknown `main_sha` always refused at compare | `test_a_baseline_with_an_unknown_main_still_reports_it_as_stale_not_as_a_bad_head` |
| 35 | SHA shape check dropped in `provenance_problems` | `test_a_write_with_a_malformed_sha_is_refused_before_any_lookup` (3) |
| 36 | write refusal raised inside the `except` of `store_baseline` | `test_a_refused_write_carries_no_exception_context` |

Mutation 29 is the AT-5 rename cell (Dennis r1 MEDIUM-1). The same cell is to be carried to the engine copy of
`test_gates_baseline_file.py` when D6, D7 and D10 are carried back.

The first attempt at mutation 4 put the inserted line at the wrong indent and failed on a syntax error; it
was redone with the right indent and the table row is from the redo.

## Verification

- T0 per edit on the touched tests (devbox venv, `pytest-one`).
- T1 on a VM (`vm-run cli`): `tests/unit/scripts`, `tests/unit/test_dev_bootstrap_gates.py`, `tests/sentry`:
  734 passed in 208 s on the head after the merge of `origin/main` and fix rounds 1 and 2 (727 after round 1, 714 before). `ruff check src tests scripts/dev` and `ruff format --check` on the touched files: clean.
- Mac (bash 3.2.57, `GATES_TEST_BASH=/bin/bash`, own folder `~/decoy/acct2-cli-baseline`, venv `venv-cli-mac`
  with `decoy` resolved through `PYTHONPATH=src`): `tests/unit/scripts`, `test_dev_bootstrap_gates.py`,
  `test_bash32_compat.py`: 189 passed.
- End to end on a VM (throwaway clone, `origin/main` set to the branch head, bootstrap first):
  - Head `ca4793d` (a snapshot of the branch at `6c8b544`, based on current CLI main `b6e0437`), bootstrap first:
    the tree stayed clean (0 dirty paths).
  - `gates.sh --keep-going --write-baseline F tests`: exit 0, wall 735 s. Every step ran (env, ruff, sentry and tests
    PASS; format and mypy SKIP). Stored `collected` 2989, `skipped` 4, `failing` 0, `workers` 1, `order` `collection`
    (tests: 2985 passed, 4 skipped; sentry: 580 passed).
  - One seeded failing test on top, `--keep-going --baseline-file F tests`: exit 1, wall 695 s, one `NEW-FAILING`
    line naming only the seeded id, `collected: baseline=2989 branch=2990 delta=+1`.
  - `origin/main` moved by an svg-only commit and the same compare from a branch on it: exit 1, wall 682 s, no
    stale refusal, the same single `NEW-FAILING` id, and the `NOTE:` line saying main moved only in Markdown or
    generated diagrams no test reads.
  - Legacy mode time for the same branch was not measured (a legacy run is two suite runs, about 2 x 12 min).
  - The file was not promoted and was deleted on the VM.

## Declared changes

- C1: `--baseline` fails only on branch-only steps (`branch_only_steps`). A shared `tests` or `sentry`
  failure gives exit 0. Unparsed failures (the default-format `ruff check`, a failing ratchet step) stay
  branch-only and fail closed. To make that reach exit 0 for the CLI, where format and mypy are SKIP, the final
  "a step ran" check counts a rc 1 step as having run in every baseline mode (the engine counts it only for a
  stored compare because its format step always runs green). This is part of C1, not a new behavior.
- C2: `--baseline` implies `--keep-going`.

## Divergences from the engine scripts

D1 an explicit missing test path is skipped (engine exits 2). D2 no `TESTS_REQUIRED`. D3 the selection wording
stays `changed vs origin/main: N test file(s)`. D4 no parallel pass, `--order-from`, `GATES_WORKERS`, order map,
`licenses` step, `DECOY_GATE_VENV_STRICT`, `DECOY_LICENSE_STRICT` or concise ruff output; `--workers` answers
`1 the CLI suite runs serial` and `_gate_workers.py` does not exist. D5 `GENERATED_UNREAD_GLOBS`. D6 the stored
file is copied first and only the copy is read. D7 `--test-root DIR`, an existing directory or exit 64. D8 the
address refusal lives in the reporter's write (`write-baseline refused`, exit 1). D9 `DOC_WALK_GUARDS` derived
from `SENTRY_PATHS`. D10 both SHA fields are 40 lowercase hex characters.

Other differences, all forced by the above or by bash 3.2:

- `check_stored` refuses any stored `order` other than `collection`, and any non-empty `order_seconds`; the
  engine accepts a file ordered by its own map because its suite honors the map.
- `dump_baseline` round-trips the data through the same parser before writing, so the writer cannot store a
  file the gate refuses (a short SHA reaches the reporter as `write-baseline refused`).
- The selection step ignores a failing `merge-base` as before (empty selection), where the engine exits 2.
  This keeps the plain route unchanged (no declared change allows otherwise).
- `--write-baseline` and `--baseline-file` without a following argument read `${2:-}` instead of aborting on an
  unbound variable.
- `--help` prints the whole header comment (the engine's awk), not lines 2 to 8.
- The sentry step has no `env DECOY_GATE_VENV_STRICT=1`.
- The reporter exits 1 only for a refused write, after printing the whole EVIDENCE block; `gates.sh` accepts
  that code only together with `--write-baseline`.

## Fix round 1 (Codex r1, Dennis r1)

- `--baseline-file` and `--write-baseline` exit 2 with `gates: FLAG needs a file operand` when the operand is
  missing or the next token starts with `-` (an empty path is the same case).
- Provenance (V1, accidental mismatch only; no signing): `head_sha` must resolve in the repository and have the
  tree of `main_sha`. `--check-stored` takes the repo root as a fifth argument; the writer applies the same check
  with `require_main`, so an unknown `main_sha` is refused at write and left to the staleness message at compare.
  A reporter copied outside the repo without `--test-root` now refuses to write, because it cannot resolve the
  commits. This replaces the old control that showed the wrong id.
- The unreadable-JSON error and the write refusal use `raise ... from None`.
- The duplicate `Found N errors` regex in the reporter is gone.
- `origin/main` was merged (`cb24259`); the only conflict was the `CODEMAP.md` table, both rows kept.

## Fix round 2 (Dennis r2)

- Head provenance, as the promote flows need it. A stored file records `head_sha == main_sha` by construction,
  and a carry moves both. The reader accepts `head_sha == main_sha` (when `main_sha` is unknown the staleness
  check names it) and otherwise requires `head_sha` to resolve and share `main_sha`'s tree. The writer takes
  `--head-sha` only when it resolves and has `main_sha`'s tree, and writes the value it was given. New cells: a
  carry-shaped file (`head_sha == main_sha ==` a new main whose tree changed) is accepted; head with another
  tree and an unresolvable head are refused (round 1 cells).
- Both SHA arguments are shape-checked (40 lowercase hex) before any lookup, with their own message.
- No exception context: `load_baseline` and `store_baseline` raise after the `except` block has closed, so
  `__cause__` and `__context__` are both `None` (cells for the unreadable-JSON error and for a `WriteRefused`).
- `--steps` goes through the same operand check as the file flags (a missing operand or a flag token exits 2;
  an empty list stays legal, `test_dev_bootstrap_gates.py` pins `--steps ""`).
- The unknown-main cell now carries a resolvable `head_sha != main_sha`, so it reaches the branch it names;
  mutation 34 (always refuse an unknown main) turns it red.
- The refusal and write code moved to `_gates_baseline.py` (`store_baseline`, `WriteRefused`, the address
  pattern), so `_gates_report.py` is 480 lines and `_gates_baseline.py` 267.

## Not covered

- `decoy-vm-t3` and `decoy-vm-t3-promote` are not changed here (plan section 8, orchestrator).
- No full suite on the head: this slice changes the test runner and selection tooling, so the orchestrator
  runs the full CLI suite once on the final head in legacy mode.
- `scripts/dev/*.py` are linted by hand (follow-up L3: add `scripts` to the gate's ruff paths).
- The `carry` promote kind stays the accepted exception of plan section 4a.
- `~/bin/decoy-vm-t3-promote` (orchestrator, not changed here) must, for `merged`, push the squash commit S to
  the VM and pass `--main-sha S --head-sha S` (S has the tree of the tested head), plus `--test-root`; for
  `carry`, rewrite `head_sha` together with `main_sha`, because the reader requires a head that is either equal
  to `main_sha` or shares its tree. A carry that moves only `main_sha` is refused by the gate.
- The engine does not have D6, D7 or D10; carry them back.
