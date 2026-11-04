Status: record

# X0a CLI build record (part 1a: ratchet framework and sentry manifest)

Slice X0a, CLI half, part 1a, of `decoy-platform/docs/plans/2026-11-04-cross-cutting-v1-foundations.md`.
Branch `feat/x0a-gate`. Part 1b (registering the CLI allowlist) is `2026-11-04-x0a-cli-registry.md`.

## Environment

- Base: CLI `origin/main` `cffab75c0175974bb33aa9d5e86444d31ff870d5`.
- Venv `.venv` from `scripts/dev/bootstrap.sh`: `RESULT:     OK, environment matches requirements-dev.lock and the engine pins`.
- Python 3.10.20 (the floor, so `tomli` is the TOML reader), pytest 9.2.0, ruff 0.15.14, GNU bash 5.2.21.
- Port sources: engine `tests/sentry/_ratchet.py`, `scripts/dev/ratchet_check.py` (#378 `217f1899`);
  platform `--slice` rule (#169 `5cc2db2c`).

## What changed

- `tests/sentry/_ratchet.py`: the engine helper, plus two rules. A baseline whose `created_in`
  is missing, blank or not a string is a finding. A newly registered id (no removed ids, so not
  a split) whose `created_in` differs from `--slice` is a finding when `--slice` is given.
- `scripts/dev/ratchet_check.py`: engine script plus `--slice NAME`. Exit 2 with
  `run: git fetch origin main` when there is no merge base.
- `scripts/dev/sentry_registry.toml`: header only. `tests/sentry/baselines/.gitkeep`: empty.
- `scripts/dev/gates.sh`: `SENTRY_PATHS` names the three `tests/unit` sentries; the sentry step
  runs `ratchet_check.py` first in the engine's bash 3.2 safe form, skipped when the script is absent.
- `tests/sentry/test_sentry_manifest.py`: `SENTRIES` (16 `tests/sentry` files plus three
  `tests/unit` sentries). `PYTEST_ARGS` is parsed with `shlex`: CLI main has no `-m`, so the
  collection run passes none.

## Red and green per AT

Red run on commit `e922e0d` (tests only, mechanism absent), command
`.venv/bin/python -m pytest -p no:cacheprovider -q tests/sentry/test_ratchet_check.py tests/sentry/test_sentry_manifest.py`:
`33 failed, 3 passed`.

| AT | Red on base | Green on head |
|---|---|---|
| AT-CI0 | all 30 cases fail: `can't open file '.../scripts/dev/ratchet_check.py'` | 30 passed |
| AT-CI1 | `test_gates_sentry_paths_cover_every_sentry`, `test_gates_step_collects_every_sentry`: `Left contains 3 more items, first extra item: 'tests/unit/test_cli_surface.py'` | passed |
| AT-CI2 | `test_removing_a_sentry_path_is_detected` red only because the three `tests/unit` files were uncovered | passed |

Plan drift: AT-CI1 names `tests/policy`; the CLI has none, so the red case is the three
`tests/unit` sentries. AT-CI2 keeps a seeded `tests/policy/test_seeded.py` negative.

## Mutations (each applied once, run, reverted)

| Mechanism | Mutation | Went red |
|---|---|---|
| subset check | key counts instead of key sets | `test_baseline_gaining_a_key_fails` (one key swapped, counts equal) |
| split rule | skip the removed-ids union check | `test_split_whose_union_adds_a_key_fails`, `test_renamed_baseline_with_extra_key_fails` |
| unregistered file | drop the on-disk scan | `test_new_baseline_without_registry_entry_fails` |
| reason schema | `MIN_REASON = 0` | `test_empty_or_placeholder_reason_fails[]`, `[   ]`, `[too short]` |
| created_in slice | ignore `slice_name` | `test_first_inventory_created_in_must_match_slice` |
| created_in present | drop the non-empty check | `test_missing_created_in_fails` (4 params) |
| gates wiring | scratch commit adding unregistered `baselines/scratch.json` | with the call: `[sentry] FAIL(rc=1)`, `ratchet: FAIL tests/sentry/baselines/scratch.json: baseline file is not registered`; call removed: `[sentry] PASS passed=363` |
| manifest coverage | drop `tests/unit/test_cli_surface.py` from `SENTRY_PATHS` | `test_gates_sentry_paths_cover_every_sentry`, `test_removing_a_sentry_path_is_detected`, `test_gates_step_collects_every_sentry` |

The rename case uses a new id (old path deleted), so the split rule holds it, not the kept-id
subset check; the moved-path case for a kept id is `test_moved_baseline_for_a_kept_id_fails`.

## Gates

`bash scripts/dev/gates.sh --keep-going --baseline` on `954eb8d`: env PASS, ruff PASS,
format SKIP, mypy SKIP, sentry PASS (363; baseline 327), tests PASS (36; baseline SKIP, no paths).
Failing ids: branch 0, baseline 0, branch-only 0. Baseline worktree skipped the ratchet (script absent).
`tests/unit/test_dev_bootstrap_gates.py`: 15 passed. `bash -n scripts/dev/gates.sh`: ok.
`ruff check src tests scripts/dev/ratchet_check.py`: pass; `ruff format --check` on the new files: pass.

## Files vs allowed list

Exactly the eight allowed files (`git diff --name-only origin/main...HEAD`).

## Size

`git diff --shortstat origin/main...HEAD` before this record: 7 files, 577 insertions, 2 deletions.
No generated files.

## Named limits

- A module-level `skip` still collects, so the manifest test does not see a skipped sentry.
- `PYTEST_ARGS` and `SENTRY_PATHS` are parsed with `[^)]*`; a `-m` expression containing `)` is not supported.
- A first inventory is reported for human review; the check cannot judge its content.
- Key sets only: a kept key with a rewritten, still valid reason passes.

## V2-LOG

- `scripts/dev/gates.sh:83` (unchanged line, out of scope) expands `"${PYTEST_ARGS[@]}"` with an
  empty array, which aborts under bash 3.2 `set -u`; the later CLI CI part owns it.

## Not verified

- AT-CI3, AT-CI4 (self-hosted workflow, trigger, `flock`): out of scope.
- bash 3.2: no binary on this host; only bash 5.2 and `bash -n` were run.
- Full suite: `gates.sh` is a trigger, deferred to orchestrator T3.
