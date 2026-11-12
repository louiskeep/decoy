# LIB L1d (library scratch): build evidence

Slice L1d of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7: slice L1d-cli, sections 4.6 on Windows scratch, 4.7 on scratch and best-effort
deletes, and 3 on the protected-scratch choke point). Branch `feat/lib-l1d-scratch` from
`origin/feat/lib-l1c2-fsck` at `48c025b` (L1c.2 with `origin/main` 92d730a merged in).

## Environment

- OS: Linux 6.18.44 (x86_64), ext4, run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`).
- Engine: `decoy-engine` 0.22.0 (`open_protected_dir`, `protected_scratch_dir` public).
- Code head the checks ran on: `150e71b`. This record is the only later commit (Markdown only).

## Commits

| Commit | What |
|---|---|
| `4dc5e35` | red-first `tests/unit/library/test_scratch.py` |
| `150e71b` | `cli/library/_scratch.py`, `Library.scratch` and `Library.delete_scratch`, docs, CHANGELOG, CODEMAP |

## Red first (`4dc5e35`)

`pytest tests/unit/library --continue-on-collection-errors`: **130 passed, 4 skipped, 1 error.**
The error is `test_scratch.py` failing to collect, because `decoy.cli.library._scratch` did not
exist.

## What was built

- `Library.scratch(owner, invocation_id, *, ttl=None)` is a context manager that yields a
  `ScratchAllocation` (`path`, `kept`, `write(name, data)` (0600 through `_fs.replace_file`),
  `report`, `skipped`).
  - It first runs `Library.prepare()`, so the root and `.decoy/.gitignore` exist before
    `scratch/`.
  - `scratch/` is opened with `decoy_engine.open_protected_dir(scratch, create=True)` on every
    call: created 0700, or checked and reused, an empty too-open one tightened, a too-open one
    with files refused.
  - `ttl=None` (delete_on_exit staging): `decoy_engine.protected_scratch_dir(scratch,
    "<owner>-<invocation_id>-")`. When the block exits, on success or exception, `delete_tree`
    runs file by file and reports what it could not remove, then the engine removes the folder.
  - With a `ttl` (sample output): `open_protected_dir(scratch/<owner>-<invocation_id>,
    create=True)`; the folder is kept.
- Engine failures: a `DecoyError` with code `scratch_acl_failed` or `scratch_unsafe` (imported
  from `decoy_engine.reasons.runtime`) becomes `LibraryError` with that code, raised outside the
  `except`. The block never runs, and the engine leaves no folder.
- `Library.delete_scratch(path)` is the best-effort delete for folders inside `scratch/` only.
  It returns a `DeleteReport` (`removed`, `skipped`, and `code` = the engine's
  `library_delete_skipped` when anything was skipped). A `PermissionError` on one file is
  skipped, never raised.
- Owner grammar: `[a-z0-9][a-z0-9-]{0,31}`. Anything else is a `ValueError`, raised before any
  folder is made.
- No `Path.mkdir`, `os.makedirs`, `chmod` or `ctypes` for scratch in the CLI.

## Mutations (`mutate_d.py`; each applied once and restored; tree clean)

| Mutation | Change | Test | Result |
|---|---|---|---|
| M-MODE | `ScratchAllocation.write` with plain `write_bytes` | `test_an_allocation_is_0700_and_its_files_0600` | red |
| MD1-leak (first form) | skip the engine context manager's exit | `test_delete_on_exit_removes_the_allocation_on_success_and_on_error` | **green**. The mutation did not leak: CPython finalizes the abandoned generator when it goes out of scope, which runs the engine's `finally` and removes the folder. Not a test gap |
| MD1-leak (applied form) | staging treated as kept (`if True:` in place of `if ttl is not None:`) | same | red |
| MD1-own-mkdir | the allocation made with `Path.mkdir` | `test_scratch_and_every_allocation_come_from_the_engine_allocator` | red |
| MB1-acl-warn | print a warning and `mkdir` an unprotected folder | `test_an_acl_failure_on_scratch_itself_stops_the_owner` | red |
| MD1-skip-reopen-check | `scratch/` via `mkdir(exist_ok=True)` | `test_scratch_is_reopened_tightened_or_refused` | red |
| MD1-raise | let `PermissionError` escape the delete | `test_a_file_held_open_is_reported_and_skipped_then_cleaned_later` | red |

## Checks on `150e71b`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/library tests/e2e/library tests/sentry -q -p no:cacheprovider` | 1247 passed, 6 skipped (Windows/macOS-only cases) |
| `.venv/bin/ruff check src tests` | pass |
| `ruff format --check` on the `.py` files changed since the base | 3 files already formatted |
| `uvx mypy --python-executable .venv/bin/python src/decoy`, compared with base `48c025b` | no new error |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection (`tests/unit/library tests/e2e/library tests/unit/private_file tests/unit/project_layout tests/unit/test_atomic.py tests/unit/test_cli_surface.py tests/unit/test_surface_docs_consistency.py tests/e2e/private_file`) | branch 392 passed, 6 skipped; base (`PYTHONPATH=<worktree>/src`) 377 passed, 4 skipped |

Failure sets: branch none; base none.

## Sentry registrations

None. The G-ONE-PRIVATE-FILE census stays at 61 watched sinks and 23 entry calls (scratch writes
reuse `_fs.replace_file`). No baseline changed.

**G-ONE-PROTECTED-DIR (CLI half) does not exist on main.** No sentry under `tests/sentry/` checks
raw row-directory creators; the private-file sentry sees `tempfile.mkdtemp` only as a `temp`
sink. Per the brief it was not built here (L0.3 scope). D1-uses-allocator is held by the spy
test.

## Differences from the plan's wording (engine behavior tested as is)

1. **Fresh allocation name.** `protected_scratch_dir(parent, prefix)` always appends 16 random
   hex digits and creates the directory itself. Staging folders are therefore
   `<owner>-<invocation_id>-<16 hex>`, not `<owner>-<invocation_id>`. Kept (TTL) allocations get
   the exact plan name through `open_protected_dir` at that path; the engine creates or checks it
   there too. The CLI creates no directory itself.
2. **The engine removes a fresh directory with `shutil.rmtree(ignore_errors=True)`**, which skips
   held-open files silently. To report them, the CLI's file-by-file `delete_tree` runs inside the
   allocation before the engine's exit. The engine's removal then finds the folder gone, or a
   folder still holding the skipped file, which `delete_scratch` removes later.
3. **D1-reopen matches the plan.** The engine tightens an empty 0755 `scratch/` to 0700 and
   refuses a 0755 one with a file in it (`scratch_unsafe`).
4. **TTL expiry of kept sample output is not built here.** It belongs to the sample lifecycle
   (L3b). The policy model already carries `sample_ttl_hours`.

## Open question O1 (carried from L1b.2; recommendation only, no guarantee changed)

A `--library DIR` (or `DECOY_LIBRARY=DIR`) whose folder is not named `.decoy` gets no
`.gitignore`, because the one writer, `ensure_decoy_dir`, knows only `<project>/.decoy`. If that
folder sits inside a git work tree, `scratch/` rows could be staged by `git add -A`.

- Today: no command allocates scratch yet (L2 and L3b will), so no row can land there with this
  branch alone. Not a function break, data loss or value leak on this branch.
- Recommendation for the owner, before L2 or L3b ships:
  - (a) give `cli/io` a `.gitignore` writer for any library root (the same content and
    create-once rule as `ensure_decoy_dir`); or
  - (b) have `Library.scratch` refuse (`scratch_unsafe` or a new code) when a non-`.decoy` root
    lies inside a git work tree.

  (a) keeps the CLI surface unchanged and is the smaller rule. `docs/library.md` now tells users
  to keep such a folder outside any git work tree.

## OS lanes

- Linux: run.
- macOS: NOT RUN (no runner).
- Windows: NOT RUN (no runner). `test_scratch_and_allocation_dacls_are_owner_only_on_windows`
  (D1-win-scratch-acl, read back through the engine's `_win_state`) and
  `test_a_file_held_open_on_windows_is_skipped` (D1-delete-open) are written and skip-marked;
  the Linux run forces the `PermissionError` path instead.

## Not run

The full suite, the macOS and Windows lanes, and mypy from `.venv`.

## V2-LOG (noticed, not built)

- `delete_tree` follows the walk order of `os.walk`. A symlink inside an allocation is removed as
  a link (`os.unlink`), never followed. A test for that edge would be cheap to add when L3b writes
  real sample files.
- The engine's `protected_scratch_dir` has no "report skipped" hook. An engine option to return
  what `rmtree` skipped would remove the CLI's pre-pass.
