# F13 CLI slices 4a-0, 4a, 4b: evidence record

Branch `feat/f13-cli-mask-secret`, base `origin/main` `a5d36b4`. Plan: engine branch
`plan/f13-slices-3-4` (`18847ac`), `docs/plans/2026-10-31-f13-slices-3-4-consumers.md` sections
3.1-3.4, 10.4, 10.5, 13, plus the Dennis amendment (slice 4a-0 from B-6 S7b).

Environment: `scripts/dev/bootstrap.sh` venv, `requirements-dev.lock` sha256 `9b6fadd776bb6c84`
(fresh, 63 pins), CPython 3.10.20, linux x86_64, `decoy-engine` 0.17.0 at `1132d29e`, typer
0.26.8, ruff 0.15.14. Baseline and branch suites ran in the same venv (baseline with
`PYTHONPATH` pointed at a copy of the `a5d36b4` tree).

## Commits

| Slice | Commit | Production files | Lines incl. tests (cap) |
|---|---|---|---|
| 4a-0 | `419681b` | 1 (`cli/run.py`) + regenerated reference | 100 |
| 4a | `f2bbbde` | 8 + regenerated reference (18 lines) | 652 (800) |
| 4b | `bd3ec79` | 5 | 301 (341) |

## Red first (each failed on the tree before its slice)

| Test | Failed at |
|---|---|
| `tests/e2e/test_run_chunked.py::test_chunked_with_vault_is_refused_before_any_output[text,json]` | exit 3: the spy on `vault_writer_for_config` fired (`run.py:791`) |
| `test_mask_secret_flag_parity.py::test_vault_and_fpe_open_under_either_way_of_naming_the_secret[flag-*]`, `::test_unmask_flag_and_yaml_ref_give_identical_results`, `::test_flag_and_yaml_ref_both_set_is_a_usage_error[unmask,report_vault]`, `::test_help_names_the_flag[*]` | Typer "No such option: --mask-secret" (exit 2): `cli/unmask.py:57-115`, `cli/report.py:2211-2247` |
| `test_mask_secret_flag_parity.py::test_no_secret_refuses_with_the_constant_remedy_before_any_output[unmask,report_vault]` | remedy texts name only the YAML key (`_mask_secret_guidance.py:24-34`) |
| `test_mask_secret_single_read.py::test_each_command_reads_the_secret_once[env,file]` | `run --vault` read twice: `run.py:791` and inside `run_pipeline` (`:821`) |
| `test_mask_secret_single_read.py::test_chunked_multi_table_run_reads_the_secret_once` | one read per table inside `run_mask_pipeline_chunked` (`run.py:1443`) |
| `tests/sentry/test_mask_secret_error_text.py::test_secret_refusal_prints_a_constant_remedy` (13 of 16 cells) | the engine message printed: `run.py:1005` (`str(exc)`), `tokenize.py:360`, `cli/unmask.py:234`, `report.py:2311`; tokenize keyed refusal had no CLI text |
| `::test_unmask_dispatches_on_the_secret_code_before_the_class[*]` | caught as `ExecutionError`/`ConfigError` (`cli/unmask.py:205`) or `VaultError` (`:210`) |
| `::test_unmask_runtime_failure_prints_the_type_only` | `cli/unmask.py:237` prints `{exc}` |
| `::test_unreadable_masked_csv_prints_the_path_and_type_not_the_cell` | `cli/unmask.py:190` prints `{exc}` |

Characterization (green before and after): the YAML-ref cells of the parity tests, the `run`
cells of the no-secret and both-set tests, `test_owner_only_file_secret_works`,
`test_usage_and_source_refusals_come_before_the_secret_read[*]` (red only against an interim
4a tree that admitted before the cloud-endpoint, chunked-compatibility and source checks).

## Mutations (each applied to a scratch copy, shown red, reverted; never committed)

| Mechanism | Mutation | Result |
|---|---|---|
| 4a-0 refusal | condition disabled | 2 failed |
| provider to `run_pipeline` | `**_key_kwargs` dropped | 2 failed |
| provider to each chunked table | `key_provider=` dropped | 1 failed |
| `unmask` flag | `apply_mask_secret` skipped | 4 failed |
| `report vault` flag | `apply_mask_secret` skipped | 3 failed |
| both-set rule | `raise` removed | 3 failed |
| refusal order | admission moved before the usage/source checks | 3 failed |
| constant secret text | returns `f"{code}: {exc}"` | 12 failed |
| `unmask` dispatch order | secret branch disabled | 3 failed |
| `unmask` runtime text | prints `{exc}` | 1 failed |
| `unmask` CSV text | prints `{exc}` | 1 failed |
| `run` secret text | only the keyed refusal mapped | 3 failed |

## Suite versus baseline

- Baseline `a5d36b4`: 1979 passed, 5 skipped, 0 failed.
- Branch head: 2021 passed, 5 skipped, 0 failed. By id: removed exactly
  `tests/e2e/test_vault_cli.py::TestVaultRoundTrip::test_chunked_run_writes_equivalent_vault`
  (it pinned chunked vault writing, now refused); added 43; no other id changed.
- `ruff check src tests`: clean. `ruff format --check`: 86 files would reformat on base and on
  the branch; every hunk in a touched file is on pre-existing lines; new files are formatted.
- mypy (ad hoc, `uvx mypy`, no repo config, not a CI gate): no new error; the
  `**_report_kwargs` arg-type errors in `run.py` are pre-existing (argument index moved 7 to 9).
- Internal-boundary allowlist (`tests/sentry/test_engine_internal_boundary.py`): 22 entries,
  unchanged. The helper imports only `decoy_engine.secret_providers`,
  `decoy_engine.execution.check_chunked_compatibility` and `decoy_engine.get_default_registry`.

## Expectation changes, with reasons

- `test_keyed_secret_guidance.py::test_unmask_refusal_is_usage_and_names_the_config_key`:
  `flag=False` to `flag=True`; the remedy names `--mask-secret` because `decoy unmask` now has it.
- `test_run_native.py::test_no_native_stays_compatible_with_an_older_engine`: the fake old
  `run_pipeline` gains `key_provider=None`; every engine at or above the DE-02 floor has it.
- `test_tokenize_cli.py`: secret fixtures `chmod 0o600`; no assertion changed.

## Not run

- A real `file:` secret at 0644 refused by the engine: 0.17.0 has no owner-only check (A-4,
  plan 3.8). The CLI remedy for `secret_file_permissions_unsafe` is tested with an engine double.
- Live Vault (`vault://` with a registered provider), Windows, Python 3.11-3.13 matrix, the
  engine releases carrying the 32-byte vault-key floor and B-6 core.
