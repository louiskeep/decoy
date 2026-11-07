Status: record

# ATOMIC-OUTPUT build record (2026-11-07)

Branch `feat/atomic-output`, from CLI main `ff82bc9`. Plan: `p05-atomic-output-build-handoff.md` with its 2026-11-07 amendment.

## Placement

- `src/decoy/_atomic.py` holds `staged_local_target` and `describe`; `write_local_target(REPLACE)` goes through the staged path. `write_atomic` and `CREATE_ONCE` keep the existing `mkstemp` core, so two temp-create paths remain (a DESIGN item below).
- `src/decoy/cli/io/_compression.py` (new, 62 lines): the suffix table, `split_compression`, `is_archive_csv`, `csv_compression`. No table write call.
- `src/decoy/cli/io/_targets.py` stages in `write_table` and `write_chunked_output` only.

## Deviations from the plan

- A compressed tar needs `"mode": "w:gz"` (or `w:bz2`, `w:xz`) in the `compression` dict. pandas reads the tar mode from the written file's suffix, and the staging name ends in `.tmp`, so without it `out.csv.tar.gz` held a plain tar.
- Base `out.csv.tar.gz` stored the member as `out.csv.tar.gz`; it is now `out.csv` as the plan says. This changes a success output.
- A Ctrl-C exits 130 with empty CliRunner output on the base and on head. The plan said exit 1 and "Aborted!". The test pins the measured 130.
- The empty-source case is pinned with a patched iterator that yields nothing. A header-only CSV yields one zero-row chunk and writes a header-only file, as on the base.
- `_atomic.py` is 427 lines (plan cap 400); `_targets.py` is 444 (base 449).

## Self-review against the defect catalog

1. Value-bearing output: checked every new message; `describe` gives the code and `os.strerror` only. Report handlers still print the user-chosen output path, as before.
2. Races: checked create (`O_EXCL`, retry on `FileExistsError`), replace (single `os.replace`), directory fsync after it. A concurrent writer to the same target is last-replace-wins.
3. Input normalization: checked long non-ASCII names (cut by characters to the filesystem name limit), `.`/`..`/empty names, case-insensitive suffix match in the compression table.
4. Every route and caller: checked `write_table` (run via `write_targets`, demo, `decoy.mask`, unmask, detokenize), `write_chunked_output` (run), `write_local_target` (ci, debug, fit, scan, evidence, four report sites). `describe` sits at each boundary.
5. Referential integrity: n/a (no stored relations).
6. Tests that can fail: every test has a named killing mutation below. No pin or count was changed.
7. Honest records: CHANGELOG, the detokenize help text and `docs/cli-reference.md` state the 0600 split and the named limits.
8. Field paths and keys: errors carry codes only.
9. Sentries: extended A2's sentry through its shared scanner (`call_contexts` in `_calls.py`); no new allowlist key, no equivalent API used to dodge it.
10. Today's real rule: existing mode bits and group are copied for masked outputs; private outputs are 0600; the owner changes to the runner (stated in the plan).
11. Read paths match write paths: the compression name is read from the real target name by writer and sentry alike; readers are unchanged.
12. Cross-OS and concurrency edges: POSIX modes run on the VM and the Mac; Windows is not verified (O_RDWR reopen from the FlushFileBuffers documentation).
13. Tests that cannot go red: see the mutation table.
14. Choke points: `staged_local_target` (publish), `csv_compression` (codec), `describe` (message), A2's sentry (writes).
15. Sizes: `_atomic.py` 427, `_targets.py` 444, `_compression.py` 62, `run.py` 1758 (base 1758), `report.py` 2364 (base 2369).
16. Sameness: the two temp-create paths in `_atomic.py` are a DESIGN item; nothing else duplicated.
17. Placement: all files follow the plan and CODEMAP.
18. Recurring catalog: anchored validation n/a; strict wire types n/a; no exception context checked (AT-A8 asserts `__cause__` and `__context__` are None); versioned read models n/a; normalized scanners checked (one scanner); private imports: `_targets` imports `_compression` inside its own package only; hidden CI failures n/a; one trust class per entry point checked (`write_atomic` vs `write_local_target`/`staged_local_target`); final-head mutations run on `3f0020d`; allowlisted helpers unchanged; no raised pins.

## Mutations (head `3f0020d`)

Each mutation turned the named test red; the full table is in the builder report.

## V2-LOG

- `.gz` header can store the staging basename.
- ACLs and xattrs of an old output are not copied.
- Unify the `mkstemp` core of `write_atomic` and `CREATE_ONCE` with `_create_temp`.
- `_atomic.py` over 400 lines: split staging from the record writer.

## Gate round 1

Dennis NO-GO on one HIGH, two MEDIUM.

- H1: a stdout redirected to a regular file stats as a regular file, so the staged path replaced it (Linux) or failed at the temp create (macOS). Fixed at the classification: a user-given absolute path under `/dev/` or `/proc/` is written through before any stat. Tests: `test_a_redirected_stdout_is_written_through_not_replaced` (subprocess, stdout to a file, bytes written, inode unchanged; red on the old head on the VM and on the Mac) and the pipe case.
- H1 correction: the first fix wrote through everything under `/dev/` and `/proc/`, which skipped staging and the 0600 rule for `/dev/shm`. Only the fd aliases (`/dev/stdin|stdout|stderr`, `/dev/fd/N`, `/proc/self/fd/N`) now match, anchored; real FIFOs and devices elsewhere are still caught by the stat check. Tests: `/dev/shm` is staged (private ends 0600), near-misses are not aliases. Mutation: the prefix rule (`startswith`) turns the `/dev/shm` test red.
- M1: the temp is now chmod 0600 right after creation for every target; the final bits are applied at publish as before.
- M2: `test_the_temp_is_owner_only_while_it_is_written` asserts the temp mode inside the block for private and non-private targets (new, existing 0600, existing 0644) under umask 022, 002 and 000. Mutation "temp chmod keeps the umask bits" turns it red. Creating the private temp at 0666 is now an equivalent mutant, because the chmod follows before the block runs.
- The classify-by-stat-only mutation is killed by the redirect test.

V2-LOG, left as is: the second temp-create path (`write_atomic`, `CREATE_ONCE`); `_atomic.py` size; a KeyboardInterrupt during the temp chmod can leave an empty hidden temp; ENOSPC raised inside the writer block is not mapped to `atomic_write_failed`.
