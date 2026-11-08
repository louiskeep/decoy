Status: record

# CLI-MAC-TESTS S1 build record (DP refusal code and host-target distribution tests)

Plan `docs/plans/2026-11-08-cli-mac-tests.md` (branch `plan/cli-mac-tests`, Revision 3), slice S1 only. Branch `feat/cli-mac-tests-s1` from CLI `origin/main` `b6e0437`. Failure ids 1 to 7. S2 (stderr soft wrap, id 8) and the bootstrap ids (CLI-BASELINE) are not in this slice.

## STEP ZERO

1. `origin/main` is `b6e0437`. Engine pin in `requirements-dev.lock` is `4a0d5b1f`; the Mac venv holds the same commit (engine 0.19.0). `check_fit_environment` at that pin refuses a non-`CERTIFIED_PLATFORM` first with `dp_platform_uncertified`, then an uncertified `(platform, cpython, fingerprint)` row with `dp_stack_uncertified`. Order and codes match the plan.
2. Tests asserting either DP code: only the lines the plan names (`test_fit_command.py` 472, 535, 634, 642, 906 and `test_dp_provenance_certification.py` 60); the other hits are prose. No other test drives `decoy upgrade`, `install.sh` or `install_version` on a host-detected target: `test_distribution_acceptance.py` has its own doc builder and passes `target="linux-x86_64"` explicitly. Every other `_serve_bundle` / `_doc_for_latest` caller in `test_distribution.py` passes `target="linux-x86_64"` to `install_version` (directly or through a `kw` dict).
3. Not S1 (stderr line-break assertions belong to S2).
4. Not S1.
5. `COLUMNS` is unset on the VM and `0` in the Mac ssh shell. S1 does not depend on it.

## Changes

- `tests/dp_env.py` (new): `current_row_is_certified`, `expected_dp_refusal_code`, `expected_dp_refusal_code_required` as in plan section 4. One addition beyond the plan's contract: `foreign_platform()` (a `CERTIFIED_PLATFORM` copy with `system="plan9"`), so the two foreign cells share one definition.
- `test_dp_provenance_certification.py`: uses the helper; new `test_the_expected_code_helper_matches_the_engine_gate[host|foreign]` (AT-2).
- `test_fit_command.py`: ids 2 to 5 assert `expected_dp_refusal_code_required()`; the phantom-column cell is parametrized `host` / `foreign` and first asserts neither DP code appears (AT-3).
- `test_distribution.py`: `_serve_bundle` gains `target` (declared target now defaults to it), `_doc_for_latest` gains `target`; ids 6 and 7 use `targets.detect_target()` and skip when it is `None`.
- `CODEMAP.md`: one row placing shared cross-suite test helpers at `tests/`.

## Results (before and after)

Base `b6e0437`, files `test_dp_provenance_certification.py`, `test_fit_command.py`, `test_distribution.py`:

| Host | Base | Head `6ca3a9c` |
|---|---|---|
| Mac (arm64, folder `~/decoy/cli-mac-s1`, `decoy.__file__` inside it) | ids 1 to 7 red, 120 passed | all pass |
| Linux VM 6 (`vm-run cli`) | 127 passed | all pass |

Head, same three files plus `test_distribution_acceptance.py` and `tests/sentry`: 684 passed on Mac and 684 passed on the VM. On the Mac no `test_distribution.py` id other than 6 and 7 changed result.

## Mutations (head `6ca3a9c`, each reverted, never committed)

| # | Mutation | Host | Result |
|---|---|---|---|
| 1 | `expected_dp_refusal_code()` always returns `dp_stack_uncertified` | VM | `helper_matches_engine_gate[foreign]` red (`dp_platform_uncertified` vs `dp_stack_uncertified`); `[host]` green |
| 1 | same | Mac | `[host]`, `[foreign]` and `test_dp_fit_matches_this_environments_certification_status` red |
| 2 | `fit.py` `if missing_declared and False:` | VM | `phantom_number...[host]` red on the stack component (platform component green); `[foreign]` red on the platform component (stack component green) |
| 2 | same | Mac | `[host]` and `[foreign]` red on the platform component |
| 3 | id 6 uses `linux-x86_64` again | Mac | `test_upgrade_force_recovers_retained_bundle_without_current` red; 64 others green |
| 4 | id 7 bundle declares `linux-x86_64` again | Mac | `test_install_sh_refuses_wrong_version_without_installing_anything` red; 64 others green |
| 5 | `_serve_bundle` default `target` is `detect_target()` | Mac | 15 other `test_distribution.py` ids red (pin, activate, repair and rollback cells) |

## Not run

- Full CLI suite (no escalation trigger; S1 changes tests, one helper and one CODEMAP row).
- Intel Mac or Windows (the skip path of ids 6 and 7).
- `ruff format --check` passes on `tests/dp_env.py` only; the repo excludes format from CI and `test_distribution.py` is already unformatted at base, so it was left as is. `ruff check` passes on every touched file.
