# F13 CLI 4a/4b: Codex V1 fixes, round 2: evidence record

Branch `feat/f13-cli-mask-secret`, base of this round `b9fd22db` (Codex gate: NO-GO), `origin/main`
`a5d36b4`. Owner ruling: findings 1-3 are V1 and fixed here; findings 4-6 are V2-LOG, listed
below and not touched in code. The previous worker's `e0f3bd1f` was never pushed; this round
re-does the work from `b9fd22db`.

Environment: `scripts/dev/bootstrap.sh` venv, `requirements-dev.lock` sha256 `9b6fadd776bb6c84`
(fresh, 63 pins; the repo has no `uv.lock`), CPython 3.10.20, linux x86_64, run as root,
`decoy-engine` 0.17.0 at `1132d29e`, typer 0.26.8, ruff 0.15.14. Every suite ran in that one venv;
the `a5d36b4` and `b9fd22db` baselines ran from git worktrees with `PYTHONPATH` set to their own
`src` (in-process and in subprocesses).

Write access was proven before any work: `git push --dry-run origin
HEAD:refs/heads/feat/f13-cli-mask-secret` with a probe commit got `200` from
`info/refs?service=git-receive-pack` and would have updated the branch; the probe was discarded.

## Commits

| Finding | Commit | Production files | Lines incl. tests |
|---|---|---|---|
| V1-1, V1-2, V1-3 | `1739f77` | 5 (`_mask_secret.py`, `api.py`, `cli/run.py`, `cli/tokenize.py`, `cli/unmask.py`) | +798 / -47 (src +238 / -38) |

## Findings and classes

| Finding | Class | Root (b9fd22db) | Fix |
|---|---|---|---|
| V1-1 world-readable `file:` secret accepted | 7 check then use on a path | `_mask_secret.py:88` hands the ref to the engine, whose `FileSecretProvider._read` opens it with no mode check; `tokenize.py:330`, `cli/unmask.py:201`, `api.py:503` let the engine admit the ref itself | `_mask_secret._open_checked` opens the file (symlinks followed, `O_NONBLOCK`, `O_CLOEXEC`), `fstat`s the OPEN descriptor, refuses any `0o077` bit, a directory or any non-regular file with the constant `secret_file_permissions_unsafe` text (exit 1, no output), and admits `file:/dev/fd/N` (query suffix kept). `run` (plain and `--chunked`) and `report vault` already admitted through `admitted_key_provider`; `tokenize`, `unmask` and `decoy.mask()` now admit there too and pass `key_provider=`. A non-mapping `global_settings` passes through untouched. Skipped on Windows |
| V1-2 plain `run --vault` publishes output before the vault | 3 commit order | `run.py:824` outputs, `:838` vault; `tokenize.py:337` outputs, `:344` commit | `run._commit_vault`: `mkstemp` (0600) in the vault's directory, engine writer, data `fsync`, hard-link backup of a pre-existing vault, `os.replace`, directory `fsync`; then outputs. Any failure: exit 3, constant `VAULT_WRITE_FAILED` text, no output, no temp; a renamed-in vault is removed or the backup is put back. `tokenize` commits before it writes output |
| V1-3 `unmask` prints the masked file's path | 8 weak test (the test required the path) | `cli/unmask.py:197`; `tests/sentry/test_mask_secret_error_text.py:187` | prints `could not read the masked file: <Type>`; the test puts a canary in the file name and asserts no path, name or content prints |

## Red first (the final tests, run against the `b9fd22db` tree)

51 failed, 36 passed, 1 skipped.

| Test | Failed at | Why |
|---|---|---|
| `test_mask_secret_file_mode.py::test_unsafe_mode_is_refused_with_no_output[{run,run_chunked,tokenize,unmask,report_vault}-{0o644,0o640,0o604,0o660}]` (20) | `:109` | exit 0: the unsafe secret masked and wrote `out.csv` / `tokens.db` / `unmasked.csv`, or opened the vault |
| `::test_symlink_to_an_unsafe_file_is_refused[*]` (5) | `:109` | same, through a symlink |
| `::test_a_directory_is_refused_with_the_owner_only_text[*]` (5) | `:110` | refused as `missing_mask_secret`, not the owner-only text |
| `::test_api_mask_refuses_an_unsafe_file[*]` (4), `::test_api_mask_refuses_a_symlink_to_an_unsafe_file` | `:245`, `:259` | `DID NOT RAISE MaskSecretConfigError` |
| `::test_swapping_the_path_after_the_check_changes_nothing[*]` (5), `::test_api_mask_reads_the_checked_descriptor`, `::test_list_valued_global_settings_keeps_its_outcome[*]` (2) | `:166`, `:311` | no `_open_checked` hook on `b9fd22db`. This red is structural; what these tests catch is shown by mutants M3-M7 and M4 below |
| `test_vault_commit_order.py::test_failed_vault_write_publishes_no_output[vault_write,directory_fsync]`, `::test_a_pre_existing_vault_survives_a_failed_rewrite[vault_write,directory_fsync]` | `:93` | "masked output was published without its vault" |
| `::test_run_writes_the_vault_durably_before_any_output` | `:165` | events `['outputs']`: the vault is written after the outputs |
| `::test_tokenize_commits_the_token_map_before_any_output` | `:198` | `['outputs', 'commit']` |
| `::test_tokenize_failed_commit_publishes_no_output` | `:215` | "tokenized output was published uncommitted" |
| `test_mask_secret_error_text.py::test_unreadable_masked_csv_prints_the_type_only` | `:211` | `error: could not read /tmp/...: ParserError` |

Positive controls, green before and after: `::test_owner_only_file_is_admitted[*]` (0600 and a
symlink to 0600, all five CLI surfaces; `unmask` reverses to the source values).

## Mutations (each applied to the working file with a backup, its tests run, the file restored and checked by sha256; nothing committed while applied)

| # | Mechanism | Mutation | Killed by |
|---|---|---|---|
| M1 | mode check | `mode & 0o077` dropped | `test_unsafe_mode_is_refused_with_no_output[run-0o644]` |
| M2 | non-regular refusal | `S_ISREG` dropped | `test_a_directory_is_refused_with_the_owner_only_text[run]` |
| M3 | engine reads the checked fd | `yield config_dict` (the path) | `test_swapping_the_path_after_the_check_changes_nothing[run]` |
| M4 | non-mapping guard | `settings.get(...)` unguarded | `test_list_valued_global_settings_keeps_its_outcome[unmask]` |
| M5 | `tokenize` provider wiring | `key_provider=` dropped | `test_swapping_..._nothing[tokenize]` |
| M6 | `decoy.mask()` provider wiring | `key_kwargs = {}` | `test_api_mask_reads_the_checked_descriptor` |
| M7 | `unmask` provider wiring | `key_provider=` dropped | `test_swapping_..._nothing[unmask]` |
| M8 | `decoy.mask()` refusal mapping | branch disabled | `test_api_mask_refuses_an_unsafe_file[0o644]` |
| M9 | vault before outputs | order swapped | `test_run_writes_the_vault_durably_before_any_output` |
| M10 | directory fsync | dropped | `test_failed_vault_write_publishes_no_output[directory_fsync]` |
| M11 | rollback of a renamed-in vault | disabled | `test_failed_vault_write_publishes_no_output[directory_fsync]` |
| M12 | pre-existing vault backup | `os.link` replaced by `raise OSError` | `test_a_pre_existing_vault_survives_a_failed_rewrite[directory_fsync]` |
| M13 | temp cleanup | `tmp` not unlinked | `test_failed_vault_write_publishes_no_output[vault_write]` |
| M14 | temp data fsync | dropped | `test_run_writes_the_vault_durably_before_any_output` (first sweep: SURVIVED; the order spy then gained `fsync` events and is red on `b9fd22db` at `:165`) |
| M15 | 0600 vault | `chmod 0o644` added | `test_run_writes_the_vault_durably_before_any_output` |
| M16 | `tokenize` commit first | order swapped | `test_tokenize_commits_the_token_map_before_any_output` |
| M17 | `unmask` type-only text | path put back | `test_unreadable_masked_csv_prints_the_type_only` |

Last round's two survivors (the `secret_registry` wiring in `tokenize` and in `decoy.mask()`)
correspond to M5 and M6 in this design (the provider is handed over with `key_provider=`); both are killed by per-surface swap tests.

## Suite versus baseline (by test id)

- `a5d36b4`: 1979 passed, 5 skipped, 0 failed.
- `b9fd22db`: 2021 passed, 5 skipped, 0 failed.
- Head: 2076 passed, 5 skipped, 0 failed.
- Head vs `b9fd22db`: removed exactly
  `test_mask_secret_error_text.py::test_unreadable_masked_csv_prints_the_path_and_type_not_the_cell`
  (replaced by `::test_unreadable_masked_csv_prints_the_type_only`, which forbids the path the old
  one required); added 56 (`test_mask_secret_file_mode` 48, `test_vault_commit_order` 7,
  `test_mask_secret_error_text` 1); no status change on any other id.
- Head vs `a5d36b4`: removed only the id the previous slice removed
  (`test_vault_cli.py::TestVaultRoundTrip::test_chunked_run_writes_equivalent_vault`); added 98.
- `ruff check src tests`: clean. `ruff format`: new files formatted; the one hunk in
  `test_mask_secret_error_text.py` is on my lines; the remaining hunks in `cli/tokenize.py` and
  `cli/unmask.py` were already there on `b9fd22db` and are left alone.
- mypy (ad hoc `uvx mypy==1.18.2 --python-executable .venv/bin/python
  --ignore-missing-imports`, no repo config, not a CI gate) on the six touched or neighbouring
  modules: 38 errors on `b9fd22db`, 38 at head, set difference empty.

## Expectation changes, with reasons

- `test_mask_secret_error_text.py`: `_unsafe_ref` (a real 0644 key file) is now `_doubled_ref`, a
  real 0600 key file. With the real check a 0644 file is refused before the mocked engine runs;
  at 0600 the mocked engine error still decides the printed code. No assertion was removed.
- `test_mask_secret_error_text.py`: the path-requiring CSV test is replaced as described above.
- `test_mask_api_native.py::test_mask_native_false_stays_compatible_with_an_older_engine`: the
  fake old `run_pipeline` gains `key_provider=None` and forwards it, the same change the previous
  slice made to its `run` twin. Every engine at the pinned `==0.17.0` (and at the DE-02 floor) has
  the parameter; `mask()` now passes it. No assertion changed.
- Behaviour, `unmask` with a list-valued `global_settings`: was exit 3 `unmask failed:
  AttributeError`, now exit 1 with the coded `secret_provider_unavailable` text, the outcome
  `report vault` already had (both now admit the same way). No existing test pinned the old one.
- Behaviour, `run --vault` with a missing directory or a directory as the vault: both used to
  write masked output, then fail (exit 3, `[Errno ...]` text naming the path); now exit 3 with
  `vault_write_failed` and no output.
- Behaviour, `run --vault LINK` where LINK is a symlink: used to write through the link into
  its target; the atomic rename now replaces the link with the vault and leaves the target
  untouched.
- Decision: a coded engine `VaultError` on the commit path (`vault_crypto_not_installed`, whose
  message is the install remedy) keeps its own value-free text after the same cleanup; every
  other failure prints the constant `vault_write_failed` text.

## Self-attack (my own diff)

`decoy.mask()` on a 0600 `file:` ref 20 times: no descriptor leak. A query suffix
(`?key_version=v1`) and a relative `file:` ref give the same output as the plain ref. A 0600
FIFO is refused without hanging. A missing file is `missing_mask_secret`, and no path appears in the text.
0400 is admitted. A vault path in a missing directory, a directory, or a symlink behaves as
above. The release script is not touched by this slice.

## Same-class grep (every hit)

Class 7 (`os.stat|lstat|access`, `.stat()`, `st_mode`, `is_symlink()` in `src/decoy`):
`_mask_secret.py:122` (the fix); `cli/ci.py:98` (output path validated, then written by `mkstemp`
plus `os.replace`, which replaces a link rather than following it: not a hit);
`cli/evidence.py:182,207`, `cli/init.py:458,547` (sizes for display: not a hit);
`distribution/installer.py:652-654`, `distribution/layout.py:82,84,128,154`,
`distribution/first_install.py:39`, `distribution/manifest.py:120,141,147,180,198,225`
(installer self-management, outside this slice; not assessed). `detokenize` reads no secret.

Class 3 (`write_bytes|write_text|.commit()|os.replace|to_csv|to_parquet|write_table` in
`src/decoy`, `distribution/` excluded): output-plus-reversal pairs are `run` vault (fixed) and
`tokenize` token map (fixed); `_token_vault.py:174` (schema-only commit) and `:278` (the commit
`tokenize` now calls first) are not pairs. Single regenerable artifacts, written once with no
companion: `_update_check.py:71`, `report.py:693,1141,1830,2093`, `fit.py:495`,
`init.py:478,559,575,606`, `compile_explain.py:243`, `demo.py:63,151,155,300,302`,
`schema.py:73`, `scan.py:774`, `run.py:1113` (evidence, written after the outputs it describes),
`unmask.py:248`, `tokenize.py:696,698` (detokenize output). Atomic already:
`ci/debug.py:48`, `cli/ci.py:115`. Staging and chunked output: `api.py:257`, `run.py:1475,1488`
(`--chunked --vault` is refused). Not fixed: non-atomic single-artifact writes are outside this
slice's finding.

Class 1 (a path or exception text next to a type): all V2-LOG, below.

## V2-LOG (class 1; not fixed; line at head, handoff line in brackets)

- `cli/run.py:1002` `error_text = str(exc)` on stderr and `--json` [handoff `run.py:1044`]
- `cli/run.py:1022`, `:1123` config path in the notification [`run.py:1064`, `:1165`]
- `cli/run.py:618` `raise _ConfigValidationError(str(exc)) from exc` chain (b9fd22db `:608`) [`run.py:208` `__context__`; that line could not be matched at `b9fd22db`, this is the nearest chaining site]
- `cli/unmask.py:222`, `:239` engine exception message on the terminal [`unmask.py:221`, `:238`]
- `cli/tokenize.py:359`, `:545` engine exception message [`tokenize.py:358`, `:540`]
- `cli/report.py:2329` engine exception message [`report.py:2329`]
- `cli/report.py:106`, `:1813`, `:1818` path plus `{exc}` [same]
- `cli/tokenize.py:619` `detokenize_unreadable_target` names the input path [`tokenize.py:614`]
- Further same-class hits from the grep: `report.py:695`, `:1143`; `fit.py:412`; `init.py:351`;
  `_token_vault.py:113`, `:126`, `:143`; `compile_explain.py:187`; `_duckdb_source.py:84`, `:115`;
  `tokenize.py:701`; `scan.py:473`.

## Not run

- Windows (the check is skipped there: `os.name == "nt"`) and macOS (`/dev/fd/N` is a `dup` there,
  sharing the file offset; admission reads once, so it should hold, but it was not run). Systems
  with no `/dev/fd` would refuse a `file:` secret as `missing_mask_secret`.
- A non-root run (the suite ran as root; the check reads mode bits, which root does not bypass,
  but no unprivileged run was made).
- The native companion (not installed), the Python 3.11-3.13 matrix, CI itself.
