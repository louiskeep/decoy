# LIB L1c.2 (fsck and the `library` command group): build evidence

Slice L1c.2 of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7: slice L1c-cli part .2, sections 4.10 and 4.15 for `path` and `fsck` only). Branch
`feat/lib-l1c2-fsck` from the L1c.1 head `6132602` (`feat/lib-l1c1-index`).

## Environment

- OS: Linux 6.18.44 (x86_64), ext4, run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`).
- Engine: `decoy-engine` 0.22.0.
- Code head the checks ran on: `29c6252`. This record is the only later commit (Markdown only).

## Commits

| Commit | What |
|---|---|
| `736dfe4` | red-first tests: `tests/unit/library/test_fsck.py`, `tests/e2e/library/test_library_fsck.py`, G-KIND-CANARY `tests/sentry/defects/test_kind_canary.py` with its baseline and registrations, the private-file sink row for fsck's read-only index open (census 60 to 61), and a `job_log()` helper |
| `29c6252` | `_fsck.py`, `_commands.py`, `_refs.iter_refs` and `remove_refs`, `Library.has` and `rebuild_index`, `_index.rebuild`; a lazy library facade; registration in `__main__.py`; `_ROOT_HELP` and README rows; `docs/cli-reference.md` regenerated; docs, CHANGELOG, CODEMAP; one added e2e test (startup stays engine-free) |

## Red first (`736dfe4`)

`pytest tests/unit/library tests/e2e/library tests/sentry/defects/test_kind_canary.py tests/sentry/io_policy/test_private_files.py --continue-on-collection-errors`:
**15 failed, 152 passed, 4 skipped, 1 error.**

- 1 collection error: `test_fsck.py`, because `decoy.cli.library._fsck` did not exist.
- 9 e2e failures: there was no `library` command.
- 6 G-ONE-PRIVATE-FILE failures: the new sink row and census named a site that did not exist.

G-KIND-CANARY was green from its first commit. It is a pure guard over the engine registry; its
red proof is the seeded M-KIND-NOFIX self-test, plus the live mutation below.

## What was built

- **`decoy library path [--library DIR]`** prints the root, its source (`--library`,
  `DECOY_LIBRARY` or `project`), whether records are on, and `mode: normal` or `degraded
  <reason> (<filesystem>)` with a hint. Exit 0. A layout error exits 1 (`EXIT_USAGE`), and so
  does a root over the Windows budget.
- **`decoy library fsck [--repair] [--library DIR]`** prints one line per item (`finding`,
  `warning` or `note`, a code, and the target relative to the library root) and a summary.
  Exit 0 when there are no findings, 4 (`EXIT_FINDINGS`) when there are.
  - Codes: `object_corrupt`, `object_name_invalid`, `payload_invalid`, `needs_newer` (warning),
    `link_dangling` (warning), `ref_corrupt`, `ref_dangling`, `index_missing`, `index_corrupt`,
    `index_stale`, `temp_stale`, `mode_open` (a finding for the index, `tmp/`, `scratch/` and
    `logs/`; a note for records and refs), `log_header_invalid`, `log_bad_line`,
    `log_truncated` (warning), `layout_newer`.
  - The check is read-only. It builds the library object without the L1c.1 catch-up, and it
    opens the index with a `mode=ro` URI, so it never creates or syncs the index.
  - `index_stale` means the index lacks a record the sync could index, or holds a row whose file
    is gone. Corrupt objects and payloads the read model rejects are never indexable, so they do
    not also count as stale.
- **`--repair`**
  1. Copies each corrupt or misnamed object into `library/quarantine/` with
     `_fs.write_once` (`write_atomic`, create-once, 0600) and only then unlinks the original.
     No raw rename; G-ONE-ATOMIC-WRITER unchanged.
  2. Deletes stale temps.
  3. Under the library lock, removes refs to missing records (re-checked under the lock), with
     each removal printed.
  4. Rebuilds the index (`user_version` reset, schema recreated, sync).

  A record whose id holds but whose payload this version rejects (`payload_invalid`) is reported,
  never moved: it is not corrupt by the id rule. A degraded library skips the ref and index
  steps. A newer `LAYOUT` gets no repair at all.
- **Registration:** the `library` group sits in the "Check and report" help panel. `_ROOT_HELP`
  and the README "Common commands" table gain a `decoy library fsck` row, because the
  shrink-only omitted lists cannot grow. `docs/cli-reference.md` was regenerated with
  `python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md`.
- **Startup:** the facade imports `_commands` eagerly and everything else lazily (PEP 562).
  `decoy --help` still loads no `decoy_engine` module, pinned by
  `test_registering_the_group_keeps_the_engine_out_of_startup`.
- **G-KIND-CANARY:** the kind list comes from `records.registered_kinds()`, and a kind is
  writable when it has a write model. A fixture is
  `tests/e2e/library/test_canary_<fixture id>.py`. `PENDING_ALLOWLIST` holds `scan-set`,
  `evidence`, `run-result` and `sample-run`. It is registered as the shrink-only baseline
  `kind-canary-pending` (in SENTRIES, `sentry_registry.toml` and `_baseline_sources.py`).

## Mutations (`mutate_c2.py`; each applied once and restored; tree clean)

| Mutation | Change | Test | Result |
|---|---|---|---|
| MC1-raw-hash | fsck hashes the file bytes (the id text stripped) before `get` | `test_a_crlf_rewritten_record_passes` | red. Control: under the same mutation `test_a_sound_library_is_clean` stays green, so the mutation is faithful |
| MC1-silent | fsck skips the id check (`decoded = None`) | `test_each_problem_is_one_finding` | red |
| MC1-record-mode | record and ref modes become findings | `test_open_modes_are_findings_for_logs_and_notes_for_records` | red |
| MC1-delete | `--repair` deletes instead of quarantining | `test_repair_quarantines_deletes_temps_drops_dangling_refs_and_keeps_valid_records` | red |
| MC1-ignore | `_check_layout` ignores a newer `LAYOUT` | `test_a_newer_layout_refuses_writes_and_repair` | red |
| M-KIND-NOFIX (live) | the `sample-run` pending row removed, leaving a writable kind with no fixture and no row | `test_every_writable_kind_has_a_canary_or_a_pending_row` | red. The seeded form is `test_seeded_kind_without_a_fixture_is_red` |

## Checks on `29c6252`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/library tests/e2e/library tests/sentry -q -p no:cacheprovider` | 1227 passed, 4 skipped (Windows/macOS-only cases) |
| `.venv/bin/ruff check src tests` | pass |
| `ruff format --check` on the `.py` files changed since the base | 15 files already formatted |
| `uvx mypy --python-executable .venv/bin/python src/decoy`, compared with the base | no new error |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection (`tests/unit/library tests/e2e/library tests/unit/private_file tests/unit/project_layout tests/unit/test_atomic.py tests/unit/test_cli_surface.py tests/unit/test_surface_docs_consistency.py tests/unit/test_no_dead_command_strings.py tests/sentry/cli_text tests/e2e/private_file tests/e2e/test_stateless_cli.py tests/unit/test_exit_codes.py`) | branch: 486 passed, 4 skipped. Base `6132602` (same paths minus `tests/e2e/library`, which the base lacks; run with `PYTHONPATH=<worktree>/src` so child processes import the base's code): 464 passed, 4 skipped |
| real run: `decoy library path`, then `decoy library fsck`, in an empty git folder | root `.decoy` from `project`, records on, mode normal, exit 0; `0 records checked`, exit 0 |

Failure sets: branch none; base none. `tests/e2e/test_stateless_cli.py` passes unchanged:
`decoy run` still writes no `.decoy`.

## Sentry registrations (numbers)

- G-ONE-PRIVATE-FILE census: 60 to 61 watched sinks; 23 entry calls (unchanged); read rows 3 to
  4. The new site is `cli/library/_fsck.py::_indexed_ids::sqlite3.connect::1` (`read`, a
  `mode=ro` URI). The private-file baseline is unchanged at 5.
- New shrink-only baseline: `kind-canary-pending`, 4 entries, `created_in` L1c.2.
- `SENTRIES` gains `tests/sentry/defects/test_kind_canary.py`.
- No other baseline, ratchet, pin or size cap changed. The flat `src/decoy/cli/` gained no
  module (still 30).

## OS lanes

- Linux: run.
- macOS: NOT RUN (no runner).
- Windows: NOT RUN (no runner). On Windows fsck skips the mode checks, since POSIX modes do not
  apply.

## Not run

The full suite, the macOS and Windows lanes, and mypy from `.venv`.

## Deviations

1. **No `--project` on `library path` and `library fsck`.** The brief said `--project` is
   global; on this base it is not. Only `report verify` has one, and nothing reads
   `DECOY_PROJECT`. Adding it here would go beyond the 4.15 surface, so the two commands take
   `--library` only, and the project is found by walking up from the current folder (the L1b.2
   root rule). A global `--project` and `DECOY_PROJECT` are a PROJECT-LAYOUT question.
2. **Quarantine is copy-then-unlink**, not a move: the atomic writer has no move primitive, and
   G-ONE-ATOMIC-WRITER stays at 3 entries. The copy is create-once and fsynced before the
   original is removed, so a crash leaves both copies, never neither.
3. **`payload_invalid` objects are not quarantined.** Their id holds, so by plan 4.3 they are
   valid records this version cannot read; "never deletes a valid record" wins.
4. **`--repair` also removes refs that hold no id** (`ref_corrupt`), besides refs to missing
   records. Both point at no record.
5. **New surface lines:** a `_ROOT_HELP` line and a README row for `decoy library fsck`, required
   by the docs-consistency sentry, whose omitted lists are shrink-only baselines.
6. **Facade made lazy (PEP 562)** so registering the group keeps the engine out of CLI startup.
   Typing is kept through `TYPE_CHECKING` imports.

## V2-LOG (noticed, not built)

- fsck re-reads every object through `Library.get`. On a very large library a `--quick` mode
  that trusts a fresh index is possible (git's `fsck --connectivity-only` idea).
- `library path` uses `open_library`, which catches the index up (a cache write). A strictly
  read-only `path` would need the read-only open fsck uses.
- The mode check runs on POSIX only; Windows ACL checks wait for L0's ACL reader.
