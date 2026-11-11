# LIB L1b.2 (store core): build evidence

Slice L1b.2 of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7), placed per `docs/records/lib-reframe-2026-11-11.md` and its owner answers.
Branch `feat/lib-l1b2-store` from CLI `main` at `1d53eda`.

## Environment

- OS: Linux 6.18.44 (x86_64), run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`; `bootstrap.sh --check` OK).
- Engine: `decoy-engine` 0.22.0 (the pinned release; no repin in this slice).
- Code head the checks below ran on: `6704d62` (this record is the only later commit; it changes
  Markdown only).

## Commits

| Commit | What |
|---|---|
| `de40e5f` | re-FRAME record (cherry-pick of `5b6b64b`) |
| `c3f7367` | owner answers Q1 to Q5 appended to the re-FRAME |
| `e3cb567` | red-first tests only |
| `f1f0901` | production change, docs, CODEMAP row; two test fixes (below) |
| `6704d62` | MB1-exc case added after the first mutation run survived (below) |

## Red first (`e3cb567`)

`pytest tests/unit/library tests/sentry/io_policy/test_canonical_json.py tests/sentry/io_policy/test_library_writer.py tests/sentry/io_policy/test_private_files.py tests/sentry/test_sentry_manifest.py tests/sentry/test_baseline_registry.py tests/unit/private_file --continue-on-collection-errors`:
**12 failed, 137 passed, 3 errors.**

- 3 collection errors: `test_fs.py`, `test_paths.py` and `test_store.py` (no `decoy.cli.library`, and
  `decoy.cli.io` did not export `DECOY_DIR`).
- A1-canonical-shared (2): the engine `canonical_bytes` spy saw 0 calls. The hash literals
  matched the old code.
- G-ONE-CANONICAL (3): `cli/evidence.py:131` still had its own sorted `json.dumps`.
- G-LIB-WRITER (1): no library package to scan.
- G-ONE-PRIVATE-FILE (5) and the private-file case (1): three new cases and the census name
  sites that did not exist yet.

Two test fixes went into `f1f0901` with the production change:
- The B1-no-clobber race test did not create the parent folder of its 50 roots. That was a setup
  bug; the library does not create a missing parent of `--library DIR`.
- The `get` tests were reworked (see Deviations).

## Mutations

Each mutation was applied once with `/tmp/.../scratchpad/mutate.py` (string replace, run the
named test, restore). `git status src` was clean after every run.

| Mutation | Change applied | Test | Result |
|---|---|---|---|
| MB1-order | env checked before flag | `test_paths.py::test_flag_beats_env_and_env_beats_the_project` | red |
| MB1-scan-cwd | `--emit-config` dropped from the start chain | `test_paths.py::test_scan_starts_at_emit_config_then_config_then_cwd` | red |
| M-MODE | record written with `open(..., "w")` | `test_fs.py::test_every_created_file_is_0600_and_every_created_folder_0700` | red |
| MB1-direct | record bytes written to the final name | `test_store.py::test_a_writer_killed_mid_put_leaves_no_readable_record` | red |
| MB1-replace | `CREATE_ONCE` changed to `REPLACE` | `test_store.py::test_putting_the_same_envelope_twice_is_one_file_and_no_error` | red |
| MB1-check-then-replace | `exists()`, then `write_atomic(REPLACE)` | `test_store.py::test_two_processes_racing_one_envelope_never_clobber` | red (the `os.replace` spy saw calls) |
| MB1-trust-existing | `_verify` skipped | `test_store.py::test_an_existing_object_with_another_payload_is_record_corrupt` | red |
| MB1-no-link-check | link check disabled | `test_store.py::test_a_link_to_a_missing_record_is_refused_and_writes_nothing` | red |
| MB1-shared-tmp | fixed `tmp/record.tmp`, then `os.link` | `test_store.py::test_two_processes_put_fifty_records_each` | red (objects share one inode, so bytes land under another id) |
| MB1-no-budget | budget check disabled (Windows rule forced on Linux) | `test_paths.py::test_long_root_is_refused_before_any_write_when_the_windows_rule_is_forced` | red |
| MB1-exc | `library_error` adds `str(exc)` | first run against `test_a_write_failure_names_the_code_and_class_not_the_path` | **survived**: that failure is a `PrivateFileError`, whose text has no path. Added `test_a_read_failure_whose_os_text_names_the_path_keeps_it_out` (`IsADirectoryError`, path in its text): red |
| MB1-clobber | `.gitattributes` written with `REPLACE` | `test_fs.py::test_existing_git_files_are_never_edited` | red |
| M-LIB-INLINE | `cli/scan.py` writes `Path(".decoy/library/x.json")` (live tree, plus a self-test) | `test_library_writer.py::test_only_the_library_writes_the_library` | red |
| M-CANON-COPY | `_store.py` hashes its own sorted `json.dumps` (live tree, plus a self-test) | `test_canonical_json.py::test_no_canonical_json_outside_the_engine_form` | red |

## Checks on `6704d62`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/library tests/sentry -q -p no:cacheprovider` | 1105 passed, 1 skipped (the Windows-only case), run on `1b805d5` (this record's commit; the code is the same as `6704d62`) |
| `.venv/bin/ruff check src tests` | pass |
| `.venv/bin/ruff format --check src tests` | 64 files would be reformatted on the branch and 64 on `origin/main`. All are pre-existing; no new or touched file is among them, and every new file is formatted. `gates.sh` skips this step because `main` is not format-clean |
| `.venv/bin/mypy src/decoy` | `.venv` has no mypy (the lock does not carry it; `gates.sh` notes that CI has no mypy gate). Ran `uvx mypy --python-executable .venv/bin/python src/decoy`: 160 errors on the branch and the same 160 on `origin/main` (same set, line numbers ignored). The changed modules alone: no issues |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection: `tests/unit/test_evidence.py tests/unit/cli_fmt/test_evidence_target_format.py tests/unit/test_report.py tests/unit/test_ci_manifest.py tests/unit/test_ci_rule_codes.py tests/e2e/test_report_command.py tests/e2e/test_report_diff_command.py tests/e2e/test_report_verify_command.py tests/e2e/test_ci_adapter_parity.py tests/e2e/test_ci_existing_contracts.py tests/e2e/cli_fmt/test_target_format_readers.py tests/e2e/private_file/test_private_surfaces.py tests/e2e/test_stateless_cli.py tests/unit/project_layout tests/unit/private_file tests/unit/test_atomic.py tests/unit/test_surface_docs_consistency.py` | branch 458 passed; `origin/main` 457 passed (the extra test is the new private-file case) |
| `bash scripts/dev/gates.sh --keep-going --baseline` | exit 0. Branch: env, ruff, sentry (with `ratchet_check.py`; 1082 passed), layers (22) and tests (39 selected files, 823 passed, 1 skipped) all PASS. Baseline `origin/main`: sentry 1039, layers 22, tests 747, all PASS. Failing ids: branch 0, baseline 0, branch-only 0 |

Failure sets for the paths run: branch none; `origin/main` none.

## OS lanes

- Linux: run (everything above).
- macOS: NOT RUN (no Mac mini runner reachable from this node).
- Windows: NOT RUN (no Windows runner). `test_long_root_is_refused_on_windows` is written and
  skip-marked off Windows; the Linux run forces the platform check instead. B1-idempotent's
  "held open by another process" case and B1-atomic-kill's `TerminateProcess` path run here only
  as their POSIX form.

## Not run

The full suite (out of scope for this slice), the macOS and Windows lanes, and mypy from
`.venv` (not installed).

## Deviations from the plan and the re-FRAME

1. **No `Library.get` (stop item).** `tests/sentry/test_scan_reader.py` (G-ONE-SCAN-READER,
   SCAN-MULTI) bans a `records.decode` call outside `cli/io/_scan_set.py` and has no allowlist.
   To keep it green I would have to add an exception (weakening a test) or hide the call behind
   an alias (working around it). Neither was done. `put` checks an existing object with the
   public id-rule function `records.record_id` (parse, drop `id`, canonicalize, hash: plan 4.3's
   rule exactly), which needs no `decode`. The tests read records back through `records.decode`
   on the test side. An owner decision is needed before `get` lands (L1b.3 or L1c): an exemption
   for `cli/library/_store.py` in G-ONE-SCAN-READER, or routing `scan-set` reads through
   `load_scan_set`.
2. **G-ONE-PRIVATE-FILE census 55 to 58 watched sinks (19 to 22 entry calls).** The re-FRAME
   requires `library/_fs.py` to call `create_private_directory`, `write_atomic` and
   `write_local_target`. Each call is a new entry site with a `PRIVATE_CASES` case
   (`test_library_files_and_folders_are_owner_only_under_umask_zero`). This census counts
   registered sites (PROJECT-LAYOUT raised it from 49 to 55 the same way); it is not a ratchet
   or baseline, and the private-file baseline stays at 5. Flagged for review because the brief
   names "census" as a stop word.
3. **CODEMAP kind registry.** `tests/sentry/layout/test_codemap_paths.py::KINDS` gains the new
   row's kind, as that test's message directs.
4. **Library root meaning.** "Root" is the library folder itself: the project's `.decoy/`, or the
   `--library` / `DECOY_LIBRARY` folder (owner answer Q1 wording). The 150-character Windows
   budget is measured on that folder. Plan 4.2's arithmetic counts from the project folder, so
   this is about 7 characters stricter.
5. **Git files only for a root named `.decoy`.** `.gitignore` has one writer,
   `ensure_decoy_dir(project_root)`, which only knows `<root>/.decoy`. A `--library` folder with
   another name (a mounted volume) gets neither git file. See open question O1.
6. **Extra CLI code `library_read_failed`.** It is raised when an existing object or `LAYOUT`
   cannot be read; it is not corruption. It is not in Q4's list and is a constant in
   `cli/library/_errors.py`.
7. **`resolve` returns every match** (a tuple) instead of raising for "none" or "ambiguous", so
   no not-found or ambiguous code was invented ahead of L4a's verbs.
8. **A `LAYOUT` that is not `{"layout": 1}`** (a newer version, or unreadable JSON) refuses
   writes with `library_layout_newer`. Plan C1-layout-newer (L1c.2) tests only the newer-version
   case; fsck owns repair.
9. **G-ONE-CANONICAL rule and size.** Any `json.dumps` / `json.dump` call with a non-False
   `sort_keys` counts. Size 5: `distribution/signing.py`, `notify.py`, `distribution/installer.py`
   (the plan's three), plus `ci/manifest.py` (sorted pretty schema) and `cli/report.py` (an
   in-memory diff key), as the re-FRAME measured. Under the narrower "sorted and compact" rule it
   would be 3.
10. **G-LIB-WRITER W1** bans every private `decoy.cli.library._*` import outside the package, not
    only `_fs`. W3 also covers the library package itself, so it holds no `.decoy` literal.

## Open questions

- O1 (for L1d, scratch): a `--library DIR` not named `.decoy` that sits inside a git work tree
  gets no `.gitignore`, so a later `scratch/` holding rows could be committed. L1d should decide
  (write a `.gitignore` for any root through an `ensure_decoy_dir` variant in `cli/io`, or refuse
  scratch there).
- O2: `get` and G-ONE-SCAN-READER (Deviation 1).

## V2-LOG (noticed, not built)

- The engine's record-id grammar (`is_record_id`) is private (`records._grammar`). `_store.py`
  checks the `sha256:` + 64-hex shape locally to build object paths safely; exporting it from
  the engine would remove that duplication.
- `mypy` is not in `requirements-dev.lock`, so `.venv/bin/mypy` does not exist. Either drop it
  from slice check lists or add it to the dev lock.
- `ruff format --check src tests` cannot pass on `main` (64 files); check lists should name only
  the touched files until main is formatted.
- A missing parent of `--library DIR` is a `library_write_failed`. Creating it (0700) would be
  friendlier for container volumes.
