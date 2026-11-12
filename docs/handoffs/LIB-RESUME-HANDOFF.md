Status: plan

# LIB resume: three fix rounds bottom first, one main merge, then report (roadmap rows 34 to 42)

Written 2026-11-12 21:20 UTC for a fresh remote session that takes over the local record library stack. It replaces every earlier LIB message, including the L3a evidence reply of 03:50 UTC (its rulings are repeated below). Repo `louiskeep/decoy` (the CLI).

Read first, in full:
1. `docs/handoffs/LIB-BUILD-HANDOFF.md` on branch `handoffs/lib-build`. Its rules, test scope and report sections stay in force. Where it disagrees with this file on state or order, this file wins.
2. The plan on `plan/local-record-library` (head `49a2d450`), including the L3a amendment.
3. The review comments of 01:13 UTC on #205, #206 and #209. They are the fix lists. This file names each item; the comments have the full text.

You build only. You do not review your own work and you do not merge. The orchestrator reviews, runs the full suites and merges.

## Where things stand

CLI main is `5e216ba` at writing time, 20 commits ahead of #205. Since your last push main split `run.py` into the `src/decoy/cli/run/` package and added more `io/` helpers. `src/decoy/cli/` stays flat apart from the packages that are already there; do not add a new top-level module beside `library/`.

The stack, bottom first. Nothing in it is merged.

| PR | branch | base | state |
|---|---|---|---|
| #205 | `feat/lib-l1b2-store` | main | `ee971449`, review 1 GO-WITH-FIXES (2 design items); conflicts with main |
| #206 | `feat/lib-l1b3-refs` | #205 | `2d4455b3`, review 1 GO-WITH-FIXES (5 items) |
| #209 | `feat/lib-l1c1-index` | #206 | `058f7b51`, review 1 NO-GO (1 V1, 1 design, 1 medium) |
| #210 | `feat/lib-l1c2-fsck` | #209 | `2e549b90`, not reviewed |
| #214 | `feat/lib-l1d-scratch` | #210 | `9bcb0c06`, not reviewed |
| #215 | `feat/lib-l4a-read` | #214 | `f15bf456`, not reviewed |
| #216 | `feat/lib-l5a-progress` | #210 | `fbfa996a`, not reviewed |
| #219 | `feat/lib-l4b-prune` | #215 | `c6d68f32`, not reviewed |

The engine part of the L3a evidence binding merged as engine #503. It ships in engine 0.23.0, which is being prepared now; the CLI repin follows.

## Step 1. Main merge into #205 (plain merge, never rebase)

Merge `origin/main` into `feat/lib-l1b2-store`. It conflicts in `CHANGELOG.md`, `CODEMAP.md`, `src/decoy/cli/io/__init__.py` and `tests/sentry/io_policy/test_private_files.py`. All four are ledger-style: keep both sides. Never drop a main row or export.

## Step 2. Fix round on #205, red tests first

1. `library/_fs.py:69-81`: `read_file` is a second reader beside `io/_small_file.py` `read_small_file`. Read through `read_small_file` with a record-size limit and delete the second reader. Test: a FIFO, a symlink and an oversized record are each refused, none hangs.
2. `tests/sentry/io_policy/test_library_writer.py:102` and `:138`: the writer sentry checks only `records.encode` and the literal `.decoy`. Seed `find_project(...).root / DECOY_DIR / "library"` with `records.canonical_bytes` and `write_atomic` as a mutation and detect it structurally, so the one-writer rule holds.

V2-LOG, no change: the three items logged in the #205 comment.

Push. Merge #205 forward into #206 (and so up the stack in step 5).

## Step 3. Fix round on #206, red tests first

1. One id rule: `_store.py:55-57` imports the one in `_paths.py:122-124`; delete the copy (`resolve` uses it).
2. `_fs.py:75` must not read the private `_private_file._WINDOWS` to map EACCES or EPERM to `library_busy`. Let the atomic write raise its own code when its retries run out.
3. `read_ref` (`_refs.py:127`) reads through `read_small_file` with a small cap (about 128 bytes). This follows from #205 item 1.
4. `load_policy` (`_policy.py:116-142`) calls the one project marker reader (with its owner check) instead of its own copy.
5. A ref named `baseline` clashes with `baseline/<slug>` (`_refs.py:110-118`). Refuse the name up front with its own code.

V2-LOG, no change: the four items logged in the #206 comment.

Push. Merge forward into #209.

## Step 4. Fix round on #209, red tests first

1. V1: sqlite errors raised after the lock is taken escape as raw `sqlite3.Error` (`_index.py:162`, `:182`, `:196-198`; `_store.py:110-114`, `:123-129`, `:155-160`). Map `sqlite3.Error` inside `locked()` to `LibraryError`, reset and retry once on CORRUPT and NOTADB. "A failed index update never fails put" must hold. Tests: an index with a valid first page and corrupt later pages, a `user_version=1` file with missing tables, injected INSERT and COMMIT failures (a full disk) after the object is stored.
2. Design: the corrupt-index reset replaces the file (`_index.py:182-184`), so two processes can each hold the lock on a different inode. Truncate in place, or lock a file that is never replaced. Prune and clean depend on this lock. Test: two holders, one lock.
3. Medium: after a mid-process schema rebuild, `rows()` returns `[]` and `latest` returns None (`_store.py:153-163`). Fix it here, or carry a test that pins the intended behaviour.

V2-LOG, no change: the two items logged in the #209 comment.

Push.

## Step 5. Merge up the rest of the stack once

Merge #209 into #210, #210 into #214 and into #216, #214 into #215, #215 into #219. Never rebase. Where a fix above changed a function an upper PR also uses (`read_file`, the id rule, the lock, `load_policy`), the upper PR uses the fixed one; do not keep a copy alive to avoid a conflict. #216 wires progress into `decoy run`: on main that is now the `src/decoy/cli/run/` package, so place its change inside that package where the split put the code it touched.

Do not fix the upper PRs beyond what the merge needs. Their reviews start after #209 is GO.

## Step 6. Checks and report

On the FINAL head of each PR you pushed:
- ruff check, ruff format, mypy on the touched files.
- The CLI sentries (`tests/sentry`) and the PR's T1 selection from the build handoff. The `io_policy` and `layout` sentries must pass with no new allowlist row.
- The fix items' tests shown red before the fix (the red commit is the proof). For the #209 lock fix, revert the fix by editing the line back and show the two-holder test go red.

Report once, at the end: every new head, what each fix item changed in one or two lines, the totals per head (say which head each belongs to), the merge commits and what conflicted, anything you could not run, and V2-LOG items.

## L3a evidence record (do not start yet)

These rulings stand from the 03:50 UTC reply:
- The engine model takes `path_base` and `project_manifest` as optional keys, additive to `cli-local-1`. `path_base` is exactly "project" when present. Both keys are present or both absent. Absent stays absent and an explicit `null` stays `null`, so canonical bytes equal the manifest's.
- `project_manifest` in a record: the manifest is built once per run and stored as built. With `--evidence-out` inside the project it is that file's project-relative path; otherwise `null`. That is what `evidence.py` writes today; add nothing.
- `report verify <id>` takes its project root from the project that owns the library. The "file sits where the run wrote it" check applies only when a manifest file is read.
- Start L3a code only after the CLI is repinned to engine 0.23.0 on CLI main and #209 is merged. You will be told.

## Rules in short (the build handoff has the full list)

- V1 bar only: fix what breaks function, loses data, or shows real values or secrets to a non-admin. Everything else is V2-LOG with file and line.
- One central mechanism per concern: `read_small_file` is the only small-file reader, `write_atomic` the only library writer, one project marker reader, one id rule.
- Never raise a cap, ceiling, pin, ratchet or baseline. No skipped test, no weaker assertion. Stop and report instead.
- Commits: Conventional Commits subject, at most 72 characters, no body unless it explains why, last line exactly `cam`, no other trailers. No em-dashes.
- Plain push only. Never force-push, never rebase a pushed branch, never merge a PR. Full suites and macOS or Windows runs are the orchestrator's.

cam
