# LIB L1c.1 (index, freshness, remote filesystems): build evidence

Slice L1c.1 of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7: slice L1c-cli part .1, sections 4.3a, 4.4, 4.8 and the failure-mode rows on the index).
Branch `feat/lib-l1c1-index` from `origin/feat/lib-l1b3-refs` at `7f2bfcb` (L1b.3 with
`origin/main` 0418657 merged in).

## Environment

- OS: Linux 6.18.44 (x86_64), ext4, run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`).
- Engine: `decoy-engine` 0.22.0.
- Code head the checks ran on: `450b0c2`. Later commits change Markdown only (CODEMAP and this
  record).

## Commits

| Commit | What |
|---|---|
| `7912c2a` | red-first tests, plus the existing-test adaptations the index forces (listed below) |
| `bebb1d2` | `_index.py`, `_remote.py`, the store wiring, docs and CHANGELOG |
| `450b0c2` | mypy fixes: the query method is renamed `Library.rows` (a method named `records` shadowed the `records` module in the class body) and the row columns are spelled out |

## Red first (`7912c2a`)

`pytest tests/unit/library tests/sentry/io_policy/test_private_files.py tests/unit/private_file --continue-on-collection-errors`:
**6 failed, 110 passed, 1 skipped, 3 errors.**

- 3 collection errors: `test_index.py` and `test_remote.py` (no `_index` or `_remote` module),
  and `test_refs.py` (it now imports `_index`).
- 5 G-ONE-PRIVATE-FILE failures: the lock's sink keys moved to `_index.py::_begin`, which did not
  exist yet.
- 1 private-file case failure: a `put` must now leave 5 owner-only files, `index.sqlite`
  included.

### Existing tests adapted, none weakened

- `test_refs.py`, bad-name case: "no `index.sqlite`" became "the lock was never entered" (a spy
  on `_index.locked` saw 0 calls). `put` now creates the index, so the old marker no longer meant
  "refused before the lock".
- `test_refs.py`, lock-mode case: all connects (now at least two) must find the file 0600. The
  creation case is covered by C1-index-mode.
- `test_refs.py`, unopenable-index case: it removes the index file `put` created before putting
  a folder in its place.
- `test_refs.py`, busy case: it shortens `_index.BUSY_TIMEOUT_SECONDS`, because the timeout moved
  with the lock.
- `test_private_file.py`: it expects 5 owner-only files (`index.sqlite` added).

## Design notes

- **One open and lock mechanism** (`_index.locked` and `_begin`), used by the index and by refs.
  1. `open_private` pre-creates the file 0600.
  2. `sqlite3.connect(timeout=5 s)`, then `BEGIN IMMEDIATE`.
  3. A file that is not a database is replaced by an empty one through `_fs.replace_file` (the
     atomic writer), and the lock is taken again once.
  4. After locking, the file's inode is compared with the path's, so a process that locked a
     file another process just replaced retries on the live file.

  No inline `os.replace`; the G-ONE-ATOMIC-WRITER allowlist is unchanged.
- **Rebuild = schema plus freshness sync.** A missing index is created empty; another
  `user_version` drops the tables and recreates them. The sync lists object names with
  `os.scandir`, drops rows whose file is gone and parses only new ids through `Library.get` (the
  one `records.decode` site). Corrupt objects and unverifiable newer envelopes are left out of
  the index; fsck reports them in L1c.2.
- **`put`** inserts the row after the object exists. Any `LibraryError` from the insert marks
  the library `stale` and never fails the put.
- **Queries.** `Library.rows(kind, pipeline, table)` and `Library.latest(kind, ...)` filter in
  Python over the index rows: the largest `(created_at, id)` wins. When the library is degraded
  or stale they parse the object files instead.
- **Degraded mode.** `remote_filesystem` (with `Library.filesystem` naming it) or
  `lock_unavailable`. `put` works; `set_ref` refuses with `library_lock_unavailable`.
- **The probe** (`_remote.py`) runs once per `open_library` and can be injected through
  `open_library(root, probe=...)`.
  - Linux reads `statfs` `f_type` through ctypes against the kernel magic numbers (sources cited
    in the module).
  - macOS reads `f_fstypename` from the 64-bit-inode `struct statfs` (`statfs$INODE64` on
    x86_64).
  - Windows checks for a UNC path, or `GetDriveTypeW` returning `DRIVE_REMOTE`.
  - A probe that fails reads as local.

## Mutations (`mutate_c1.py`; each applied once, restored, `src` clean; rerun on `450b0c2`)

| Mutation | Change | Test | Result |
|---|---|---|---|
| MC1-norebuild | keep any existing tables (ignore `user_version`) | `test_an_index_of_another_version_is_rebuilt_not_migrated` | red |
| MC1-crash | catch only `OperationalError`, so "file is not a database" propagates | `test_random_bytes_in_the_index_still_list_and_are_rebuilt` | red |
| MC1-trust-index | skip the sync when the index has rows | `test_a_hand_added_object_is_listed_without_fsck` | red |
| MC1-insert-first | insert the row before the object write | `test_a_writer_killed_between_link_and_insert_is_caught_up` | red |
| MC1-keep-rows | never drop rows | `test_a_hand_deleted_object_drops_its_row` | red |
| MC1-unknown-crash | raise on a kind without a model | `test_an_unknown_kind_is_indexed_as_opaque` | red |
| MC1-umask | no `open_private` pre-create | `test_the_index_is_0600_before_any_sql_runs` | red |
| MC1-unlocked-ref | ref set without the degraded check or the lock | `test_an_unlockable_index_degrades_put_works_and_refs_refuse` | red |
| MC1-trust-lock | probe called, result ignored | `test_a_remote_root_is_degraded_and_refs_refuse` | red |
| MC1-parse-all | queries always parse the object files | `test_listing_a_fresh_index_opens_no_object_file` (5 000 records; a `sys.addaudithook` "open" spy, since 3.10's pathlib binds `io.open` at import) | red |

## Checks on `450b0c2`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/library tests/sentry -q -p no:cacheprovider` | 1198 passed, 4 skipped (Windows/macOS-only cases). `tests/e2e/library` does not exist until L1c.2 |
| `.venv/bin/ruff check src tests` | pass |
| `ruff format --check` on the `.py` files changed since the base | clean |
| `uvx mypy --python-executable .venv/bin/python src/decoy`, compared with the base `7f2bfcb` | no new error (the first run found 4, fixed in `450b0c2`) |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection (`tests/unit/library tests/unit/private_file tests/unit/project_layout tests/unit/test_atomic.py tests/unit/test_atomic_staged.py tests/unit/test_atomic_callers.py tests/e2e/private_file tests/e2e/project_layout tests/unit/test_cli_surface.py tests/unit/test_surface_docs_consistency.py tests/unit/test_token_vault.py`) | branch: 637 passed, 4 skipped. Base: 596 passed, 2 skipped, 1 failed (see the note below) |

Failure sets: branch none; base none once the base runs its own code.

The one base failure (`test_library_files_and_folders_are_owner_only_under_umask_zero`) is a
harness artifact. The test spawns a child Python, which imports `decoy` from the editable
install, so it runs this branch's code against the base's expectation of 4 files. Rerun in the
base worktree with `PYTHONPATH=<worktree>/src`, that file passes (28 passed).

## Sentry registrations

- G-ONE-PRIVATE-FILE census unchanged at 60 watched sinks and 23 entry calls. The `open_private`
  and `sqlite3.connect` sites moved from `_refs.py::library_lock` to `_index.py::_begin`; their
  case keys and the sink row were renamed.
- No baseline, ratchet, allowlist or size cap changed.

## OS lanes

- Linux: run.
- macOS: NOT RUN. The live `f_fstypename` probe and the `statfs$INODE64` symbol choice are
  untested.
- Windows: NOT RUN. `GetDriveTypeW` is untested live; the classification tables run on Linux.

## Not run

The full suite, the macOS and Windows lanes, the T4 performance marker (the 1-second `list`
budget over 5 000 records; the normal run asserts only that no object file is opened), and mypy
from `.venv`.

## Deviations

1. **Prune and clean do not exist yet**, so C1-lock-unavailable covers `put` and ref set only.
   `library path` arrives in L1c.2, so C1-remote-fs asserts `Library.degraded` and
   `Library.filesystem` instead.
2. **A lock that stays busy at open does not degrade the library.** It is marked `stale` for
   that command (queries parse the files), per plan 4.4's "says the index is stale".
3. **The query API is `Library.rows` / `Library.latest`.** The CLI `list` verb belongs to L4a.
4. **Records the index skips:** corrupt objects and unverifiable newer envelopes (an unknown
   envelope major). Plan 4.3a: skipped with a notice; the notice is fsck's job (L1c.2).

## V2-LOG (noticed, not built)

- The Linux probe reads `f_type` as a C `long`. That is right on every 64-bit ABI and on i386,
  but `struct statfs` uses `unsigned int` on s390x; that platform is not supported.
- The index stores `labels.pipeline` as written. Normalizing it to the project root (plan 4.3)
  is the producers' job (L2 and L3a).
- Base-worktree runs of tests that spawn a child Python import the editable install. Gate
  baselines that run in a worktree have the same blind spot for those tests (see
  `tests/unit/private_file`).
