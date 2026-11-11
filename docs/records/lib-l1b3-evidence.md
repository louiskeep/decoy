# LIB L1b.3 (refs and the retention policy model): build evidence

Slice L1b.3 of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7: slice L1b-cli part .3, sections 4.5, 4.7 for the model only, 4.8 for refs, and the
failure-mode rows for refs), placed per `docs/records/lib-reframe-2026-11-11.md`. Branch
`feat/lib-l1b3-refs` from the final L1b.2 head `9b137c0` (`feat/lib-l1b2-store`).

## Environment

- OS: Linux 6.18.44 (x86_64), run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`).
- Engine: `decoy-engine` 0.22.0 (no repin).
- Code head the checks ran on: `597c92a` (this record is the only later commit; it is Markdown only).

## Commits

| Commit | What |
|---|---|
| `1c35a47` | red-first tests: `tests/unit/library/test_refs.py`, `test_policy.py`; private-file registrations (two `PRIVATE_CASES`, one sink row, census 58 to 60) and the case test `test_library_lock_and_ref_files_are_owner_only_under_umask_zero` |
| `47c1c73` | `cli/library/_refs.py`, `_policy.py`; `_fs.replace_file` and one shared `_write` core; `Library.set_ref`, `read_ref`, `prepare`; `record_digest` moved to `_paths`; `read_small_file` and `UnsafeFileError` exported from `decoy.cli.io`; docs |
| `597c92a` | the policy's error path moved onto the engine's `safe_output.validation_problems` (see Deviations 1) |

## Red first (`1c35a47`)

`pytest tests/unit/library tests/sentry/io_policy/test_private_files.py tests/unit/private_file --continue-on-collection-errors`:
**7 failed, 95 passed, 1 skipped, 2 errors.**

- 2 collection errors: `test_refs.py` (no `decoy.cli.library._refs`) and `test_policy.py` (no
  `LibraryPolicy`).
- G-ONE-PRIVATE-FILE (6): the new cases and the census name sites that did not exist yet.
- The lock and ref mode case (1): `set_ref` did not exist.

## What was built

- **Refs.** `library/refs/<kind>/<name>` holds one record id plus a newline.
  - The kind must be registered (`records.registered_kinds()`). A name is
    `[a-z0-9][a-z0-9._-]{0,63}`, with one `/` allowed for a pipeline scope. Anything else is
    `ref_name_invalid`, checked before any write or lock.
  - The target must be stored and pass the id rule: `Library.get`, called under the lock, raises
    `record_not_found` or `record_corrupt` otherwise.
  - The ref is written with `write_atomic(REPLACE, tmp_dir=library/tmp)` through `_fs`. Folders are
    created 0700.
  - `read_ref` reads without the lock (the file is replaced in one step); a file that holds no id
    is `record_corrupt`.
  - `latest` is not built (it belongs to L1c).
- **Lock.** `library_lock` makes `library/index.sqlite` with `open_private` (0600, never created by
  SQLite), then runs `sqlite3.connect(timeout=5 s)` and `BEGIN IMMEDIATE`.
  - SQLite busy or locked: `library_busy`. On Python 3.10 this is read from the error class and
    its fixed "locked" message, since `sqlite_errorcode` arrives in 3.11.
  - Any other open or SQLite failure: `library_lock_unavailable`.
  - The file holds no tables until L1c.
- **Windows retry.** There is no second retry loop: `_atomic._retry_on_windows` does the 10
  bounded tries. Its leftover `PermissionError` surfaces as `atomic_write_failed` with
  `EACCES`/`EPERM`. On Windows only, `_fs._write` maps that, for `REPLACE`, to `library_busy`.
- **Policy.** `load_policy(root)` reads `<root>/library.yaml` with `decoy.cli.io.read_small_file`
  (regular file, 64 KiB cap) and `yaml.safe_load`, the project-marker pattern. It returns one
  frozen strict model with the 4.7 defaults:
  - records: `default: {keep: all}`, plus per-kind `{keep: all}` or `{keep_last: N}` for
    registered kinds only;
  - logs: 50 runs per pipeline, 30 days;
  - scratch: sample TTL 24 h, `staging: delete_on_exit`.

  An absent or empty file gives the defaults. A bad file is `library_policy_invalid` with field
  locations only. Nothing enforces retention.

New CLI codes in `cli/library/_errors.py`: `ref_name_invalid` and `library_policy_invalid`.
`library_busy` and `library_lock_unavailable` were already defined in L1b.2.

## Mutations

Each mutation was applied once with `/tmp/.../scratchpad/mutate_b.py` and restored; `src` was
clean after every run.

| Mutation | Change | Test | Result |
|---|---|---|---|
| MB1-nolock | `set_ref` without `library_lock` | `test_two_processes_set_the_same_ref_twenty_times_each` (B1-ref-race) | **green**: the race alone cannot show a missing lock, because the atomic replace keeps every observable ref a whole, valid id |
| MB1-nolock | same | `test_a_second_setter_waits_for_the_lock_holder` (deterministic barrier: a child holds `BEGIN IMMEDIATE`; the setter must still be blocked 0.5 s later with the ref unchanged) | red |
| MB1-nolock | same | `test_the_loser_fails_with_library_busy_and_never_overwrites` | red |
| MB1-noretry | `_atomic._RETRY_ATTEMPTS = 1` | `test_a_ref_held_open_briefly_is_replaced_after_retries` (Linux, Windows branch forced) | red |
| MB1-noretry | same | `test_a_ref_held_open_past_the_window_is_library_busy` | red |
| extra (MC1-umask form) | `open_private` removed, so SQLite creates the lock file | `test_the_lock_file_is_0600_before_any_sql_runs` | red |
| extra | policy models `extra="ignore"` | `test_an_unknown_key_or_kind_is_refused_by_name` | red (3 of 4 cases; the unknown-kind case is the field validator) |
| extra | the policy error keeps `repr(parsed)` | `test_a_bad_value_error_names_fields_never_the_value` | red (3 of 5; the YAML-error and non-mapping cases never reach validation) |

The two policy mutations were run again on `597c92a`, after the error path changed: both red.

## Checks on `597c92a`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/library tests/sentry -q -p no:cacheprovider` | 1150 passed, 2 skipped (the two Windows-only cases) |
| `.venv/bin/ruff check src tests` | pass |
| `ruff format --check` on the `.py` files this branch touched | 12 files already formatted (main stays red on 64 untouched files; none was reformatted) |
| `uvx mypy --python-executable .venv/bin/python src/decoy`, compared with base `9b137c0` | one new line, `cli/library/_policy.py: Library stubs not installed for "yaml" [import-untyped]`. This is the same environment gap (the uvx env has no `types-PyYAML`) that the base reports for 16 modules; it is not a typing error in the code, and no module suppresses it. No other new error |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection: `tests/unit/library tests/unit/private_file tests/unit/project_layout tests/unit/test_atomic.py tests/unit/test_atomic_staged.py tests/unit/test_atomic_callers.py tests/e2e/private_file tests/e2e/project_layout tests/unit/test_evidence.py tests/unit/test_token_vault.py` | branch 519 passed, 2 skipped; base `9b137c0` 480 passed, 1 skipped |

Failure sets for the paths run: branch none; base none.

The first sentry run on `47c1c73` found one failure:
`tests/sentry/defects/test_config_error_routes.py::test_no_raw_validation_error_route_in_src`
flagged `_policy.py` for importing pydantic's `ValidationError` and calling `.errors()`. Its
allowlist is a shrink-only baseline, so I did not add an entry; `597c92a` moved the error path
onto the engine's public `validation_problems` instead.

## OS lanes

- Linux: run.
- macOS: NOT RUN (no runner).
- Windows: NOT RUN (no runner).
  - `test_a_ref_held_open_on_windows` is written and skip-marked off Windows.
  - B1-win-retry runs on Linux with `_private_file._WINDOWS` forced and `os.replace` refusing with
    `PermissionError`. That proves the reuse of `_atomic`'s bounded retry and the `library_busy`
    mapping. It does not prove the real Windows sharing-violation behavior.

## Not run

The full suite, the macOS and Windows lanes, and mypy from `.venv` (not installed).

## Registrations (numbers)

- G-ONE-PRIVATE-FILE census: from 58 watched sinks and 22 entry calls to 60 and 23. Row
  dispositions: private from 4 to 5. The private-file baseline stays at 5 rows.
  - New sites: `cli/library/_refs.py::library_lock::open_private::1` and
    `::sqlite3.connect::1` (a `private` row with `via = "open_private"`).
  - `cli/library/_fs.py::write_once::write_atomic::1` became `::_write::write_atomic::1`: one
    `write_atomic` call now serves both modes.
  - These are registrations of new sites, which the owner accepted in L1b.2.
- No ratchet, baseline or allowlist rose. The G-ONE-SCAN-READER exemption is the owner's L1b.2
  decision and lives on the L1b.2 branch.

## Deviations

1. **Policy errors use `decoy_engine.safe_output.validation_problems`.** The CLI catches the
   failure as `ValueError` (pydantic's `ValidationError` subclasses it) and passes it to the engine.
   The sentry's rule forbids importing pydantic's error or calling `.errors()` in CLI code; this
   is the route that sentry's own allowlist reasons name (FU-4). The locations follow the engine's
   joining rule (`a.b[0].c`).
2. **The kind is checked against the registered kinds, but the target record's kind is not
   compared with the ref's kind.** The plan does not say. A `scan-set` ref can name an `evidence`
   record (V2-LOG).
3. **`resolve_root` and the root rule are unchanged; no CLI verb or flag was added.**
4. **`decoy.cli.io` exports `read_small_file` and `UnsafeFileError`**, so the library reads the policy
   through the one small-file reader without importing a private `cli/io` module.

## V2-LOG (noticed, not built)

- A name that passes the ref grammar but not `_atomic`'s portable-name rule (one ending in `.`,
  or a Windows device stem such as `con`) is refused at write time as `library_write_failed`,
  not `ref_name_invalid`. The grammar could reuse `_atomic`'s name check.
- Ref kind versus target kind (Deviation 2).
- `sqlite_errorcode` arrives in Python 3.11. On 3.10 the busy check reads SQLite's fixed
  "locked" message; drop that branch when the floor moves.
- A `library.yaml` owned by another user is read (the marker's owner check is not applied);
  decide when prune starts honouring the file.
