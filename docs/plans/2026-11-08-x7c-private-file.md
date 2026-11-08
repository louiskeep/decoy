Status: plan

# X7c: one choke point for CLI private files (roadmap row 24)

Owner: Cam. Author: claudeworkerbee (Opus). Date: 2026-11-08. Scope: CLI, V1. Revision 2.2 (Dennis round 1 on
revision 1 at `af5e39f`, round 2 GO on revision 2 at `d1a84ac`; dispositions in section 0).

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`
(PLAN: choke point, Placement, Design notes, Established solutions), `feature-dev.md`, `architecture.md`
(layout), `reuse-first.md`, `security.md`, `testing.md`, `cross-cutting-concerns.md`, `code-review.md`,
`verification.md`, and `catalogs/recurring-defects.md`; the plan contract
(`30_Resources/Decoy-Plan-Contract-and-Defect-Catalog.md`), `LOCAL-BUILDER-BRIEF.md`; the standing rules
develop-correctly-registries-and-sizing and best-practice-becomes-a-sentry; the V1 bar (a second copy of a
central mechanism, or a new module in a flat folder over 25, always blocks); the CLI CODEMAP "Where things
go" (`CODEMAP.md:42-59`); the foundations plan (platform `docs/plans/2026-11-04-cross-cutting-v1-foundations.md`,
X7a to X7c rows and AT-P1 to AT-P3); the engine X7b helper and sentry at engine `main` `7a61be3c`
(`src/decoy_engine/fileaccess/_private.py`, `tests/sentry/test_private_files.py`); the code at each anchor on
CLI `main` `994bc7a`.

Roadmap row 24 (`docs/ROADMAP.md:244`) and the section 4 choke-point table (`docs/ROADMAP.md:115`): "Private
file writes | engine `_private_file` (X7b, engine #382); CLI `_private_file.py` | write-mode sentries | X7c".
Foundations slice row: "`decoy/_private_file.py` from the existing idiom; sentry derives surfaces from the AST
instead of `_CLI_SURFACES`". Row 89 (WIN-FEAS, `docs/ROADMAP.md:367`) will replace 0600 with Windows ACLs;
this plan names the seam it extends (the `_private_file` module) and builds nothing for Windows.

## 0. Review dispositions

| Finding (Dennis r1) | Disposition |
|---|---|
| B1 narrowing failure escapes `_atomic`'s `OSError` mapping | Fixed: the low-level functions raise plain `OSError` (errno set, `EPERM` when bits did not stick), so `_staged` and `_restrict_fd_target` map it to `AtomicWriteError` as today; only the standalone entry points wrap into `PrivateFileError` (section 4). AT-P1d adds a `narrow` step to `test_atomic_staged.py:152` for a private write. |
| M1 live tree fails P4 (`_atomic.py:229,231,269`, `_token_vault.py:137`) | Fixed: every mode call moves into `_private_file.apply_mode` (public bits too); the call-site moves now land before the sentry (S2 before S3). Codex narrowed the remaining launcher exception in the row below. |
| M2 baseline arithmetic; raw sinks into a private entry point's path | Fixed: rule P2 accepts a raw sink whose path argument is bound from a private entry point in the same function (`via`), and a `staged` disposition defers to G-ONE-TARGET-WRITE. Codex recounted the expanded sink set in the row below. |
| M3 DuckDB `COPY ... TO` at `_duckdb_source.py:110` missed | Fixed: census row (temp, baselined, exit WIN-FEAS); a P1 rule flags `.execute` SQL text containing `COPY` with `TO`; the SQL limit is named. |
| M4 AT-P1c and two mutations cannot fail | Fixed: `O_NOFOLLOW` is tested on `open_private`; the staging file test asserts a collision retry with a fresh name; mutations rewritten (section 7). |
| M5 `test_token_vault.py:217` patches `os.chmod` | Fixed: in S2's file list, retargeted to `os.fchmod`; code mapping stated (section 5.3). |
| Minor: `_WINDOWS` patches are not about mode bits | Accepted: the retarget edit is dropped. |
| Minor: the seam is more than one function | Accepted: the seam is the module; Windows changes land in `apply_mode`, `create_exclusive` and `open_private`. |
| Minor: distribution swaps have no baseline row | Accepted for `os.link` and `os.symlink`, which stay in the atomic-writer allowlist. Codex added `tar.extractall` to the file-sink registry below. |
| Minor: OQ1 built before it is answered | Accepted: S1 builds the owner check only if OQ1 is answered yes; otherwise it is a follow-up. |
| Minor: `ADMISSION_SITES` ids unchecked | Accepted: the sentry checks each id against `_CLI_SURFACES` members and test function names in the module. |
| Minor: the TOCTOU case needs a hook | Accepted: it moves to the S1 unit tests (AT-P1f). |
| R2-1 (Dennis r2, GO) AT-P2j red: `installer.py:219` and the two `report.py` sites have no AT-P3 case | Fixed: explicit `PRIVATE_CASES` map from call site to test id, checked both ways by the sentry; trust-state case (unit level) and one case per `report.py` function added to S2. |
| r2 minor: the class 2 mutation cannot fail | Fixed: `create_exclusive` unlinks its own file when narrowing fails; M2 targets that unlink. |
| r2 minor: section 6.5 totals | Superseded by the Codex census row below: the expanded watched sink set has 49 today and 48 after S2. |
| r2 minor: `via` checks source order only | Accepted as a named limit (the token vault connects on the `create=False` path without `open_private`, which is correct for an existing vault). |
| r2 minor: `COPY ... TO` match | Fixed: case-insensitive; SQL in a variable, `.sql()`, `duckdb.sql()` and `executemany` named as limits. |
| r2 minor: `decoy.mask()` exception type | Fixed: `PrivateFileError` subclasses `OSError` (errno set, no filename), the engine's shape. |
| r2 minor: `O_DIRECTORY` on Windows | Fixed: on Windows `open_private` narrows a new parent through `apply_mode` by path, as `_restrict` does today. |
| DESIGN (Codex): `(file, function, sink)` collapses repeated sinks in one function, so a new matching write could reuse an old row | Fixed: registry, baseline, `PRIVATE_CASES` and admission-site identities include the call ordinal; P1 checks every live ordinal and a seed adds a second same-kind sink to an already registered function. |
| DESIGN (Codex): P4 allowed any constant mode with an execute bit, so a new inline 0700 or 0711 chmod would bypass the choke point | Fixed: P4 has one exact, stale-checked exception for `distribution/installer.py::_write_launcher_shim::os.chmod::ordinal 1::0o755`; every other mode call outside `_private_file.py` fails. |
| V1 (Codex): the census omitted `write_fixed_width` and `tar.extractall`, both real file-content sinks | Fixed: both are watched P1 sinks and public census rows; totals are 49 today and 48 after S2. The tar extraction is no longer named as invisible or as creating no file content. |
| DESIGN (Codex): CODEMAP row 59 places CLI-format tests only, not the new private-file e2e folder | Fixed: S1 edits the layout map to place private-filesystem contract tests in named `tests/unit/<concern>/` and `tests/e2e/<concern>/` sub-packages; the Placement table names that map change. |
| DESIGN (Codex): admission keys collapsed two calls in the same function | Fixed: `ADMISSION_SITES` uses `file::qualname::ordinal`, and AT-S1 seeds a second call in an already mapped function. |
| DESIGN (Codex): `_calls.py` did not expose ancestor `try` blocks, so P3 would need a second AST walk despite the plan's one-scanner claim | Fixed: S3 extends the shared scanner with normalized call records carrying scope, binding and ancestor-path metadata (node plus child field); existing scanner functions project from that core, and P1 to P4 use it. |
| V2-LOG (Codex): two citations and the private-error provenance were imprecise | Fixed: `Plan.generation` points to engine `plan/_types.py:311`, the cleanup assertion points to `test_atomic_staged.py:166`, and the engine comparison is limited to raising outside the handler with no filename. |
| V2-LOG (Codex): `create_private_temp` accepted a suffix that the single moved temp-name generator could not preserve, and a Parquet failure occurred before cleanup registration | Fixed: the helper promises its central `.tmp` name only; the format stays explicit in the source entry, and S2 appends the path to `tmp_paths` before `pq.write_table`, with an injected-failure cleanup test. |
| V2-LOG (Codex): the atomic stager, SQLite handoff and Parquet spool close the protected descriptor before a path-based writer reopens it | Logged in section 15. These are theoretical local swap races in existing handoffs, so they do not decide the V1 verdict. |

## 1. FRAME

### Problem

The CLI writes files that hold raw values or secrets: the encrypted vault, the token vault (a cleartext
re-identification map), restored `unmask` and `detokenize` output, fit snapshots, evidence manifests,
reports, scan profiles, the debug log, frozen plan artifacts, the DuckDB source extract and the
`decoy.mask()` spool of the caller's DataFrame. Most already go through `src/decoy/_atomic.py`, whose private
forms publish 0600. The rest:

1. `cli/compile_explain.py:243` writes the plan artifact with `Path.write_text`: umask default mode, not
   atomic. The plan carries the seed envelope and, with statistical generate columns, the fitted generation
   payload (engine `plan/_types.py:311`, field `generation`), the same class of data as the fit snapshot that
   `cli/fit.py:497` already writes 0600. This is the one live gap.
2. `cli/_token_vault.py:109,137` creates the SQLite file with `os.open(..., 0o600)` and then chmods the file
   and its new parent by path (`_restrict`). Correct on POSIX today, but a second owner-only idiom, and the
   narrowing is by path after the open.
3. `api.py:258` spools the caller's DataFrame through `tempfile.mkstemp` (0600 by the stdlib guarantee): a
   third idiom.
4. `cli/run.py:1602` stages the vault through `tempfile.mkstemp` inside `_commit_vault` (L5a moves this
   function to `_vault_commit.py`); `cli/run.py:649` makes a 0700 DuckDB directory with `mkdtemp`, into which
   `cli/_duckdb_source.py:110` copies the unmasked source table with `COPY ... TO`; `ci/engine_logging.py:29`
   makes a 0700 `TemporaryDirectory`.

Nothing stops a fifth idiom, and the mode calls sit in five places across two modules
(`_atomic.py:229,231,269,348`, `cli/_token_vault.py:137`), so WIN-FEAS has no single place to change.

### Guarantee (what V1 promises)

- Every CLI file write is classified `public`, `private`, `staged`, `read` or `temp` in one registry. A new
  write with no row fails the sentry.
- A `private` file is owner-only (0600 on POSIX) from its first byte, under any umask including 000. It is
  created through `_private_file` (exclusive, never through a symlink at the created name) and, where the
  writer has a target, published atomically by `_atomic` (old bytes or new bytes, never neither).
- Every mode change in `src/decoy/` runs through `_private_file.apply_mode`, except the exact existing 0755
  launcher call. The `_private_file` module is the WIN-FEAS seam: `apply_mode`,
  `create_exclusive` and `open_private` are the three functions it changes.
- Errors carry a code and an errno, never a path (the existing `_atomic.AtomicWriteError` rule).
- The mask-secret admission sentry derives the admitting call sites from the AST; a new admission site with no
  surface test fails.

### Non-goals (V1)

- Windows ACLs (row 89). Today the Windows branch keeps the documented behavior: the file inherits its
  folder's permissions (`_atomic.py:396-404`).
- The vault commit transaction (`cli/run.py:1577`, L5a): baseline rows naming L5a. The install-directory
  swaps in `distribution/` stay in the atomic-writer allowlist
  (`tests/sentry/test_atomic_writer.py`); they write no private data.
- Directory modes created by `mkdir` for parents. A private file inside a shared directory is still 0600;
  the token vault keeps narrowing a parent it creates (section 5.3).
- Making scaffolded configs, masked outputs, the JSON schema, the demo data or the update-check cache private
  (section 9, OQ2 and OQ3).

### Failure modes

| Failure | Today | After X7c |
|---|---|---|
| Plan artifact with a generation payload written 0644 under umask 022 (0666 under 000) | yes (`compile_explain.py:243`) | 0600, atomic (S2) |
| A new command writes a key or map with `write_text` | silent | sentry red (new sink, no row) |
| A builder adds `os.chmod(p, 0o600)` in a `try` with `pass` | silent | sentry red (rule P3) |
| A builder changes a mode outside `_private_file` | silent | sentry red (rule P4) |
| A narrowing failure inside a private `_atomic` write | not possible today (narrowing is an `OSError` path) | still `AtomicWriteError`, pinned by AT-P1d |
| WIN-FEAS has to find every 0600 site | five calls in two modules | three functions in one module |
| A new `admitted_key_provider` call with no surface test | silent (hand list `_CLI_SURFACES`) | sentry red |
| A planted symlink at the token vault path | followed (`os.open` without `O_NOFOLLOW`, `_token_vault.py:109`) | refused (AT-P1c) |

## 2. Established solutions

- Exclusive create at the final mode, then fsync, then `rename`: the SQLite rollback-journal commit and the
  ext4 rename and fsync notes, already cited in `_atomic.py:3-9`. Creating with mode 0600 in `open(2)` means
  the umask can only remove bits, so the file is never wider than 0600 between create and narrow (POSIX
  `open`, `umask`).
- `O_NOFOLLOW | O_EXCL` for created files: CERT FIO15-C and CPython `tempfile._mkstemp_inner` (`O_EXCL |
  O_NOFOLLOW`, mode 0600).
- `tempfile.mkdtemp` makes a directory "readable, writable, and searchable only by the creating user ID"
  (Python docs); the `temp` baseline rows rely on that on POSIX.
- SQLite gives a database's `-journal` and `-wal` files the mode of the database file (`findCreateFileMode`
  in `os_unix.c`), so creating the database 0600 covers its journals.
- Narrowing by descriptor (`fchmod`) rather than by path closes the swap window between open and chmod
  (CERT FIO01-C).
- One owner-only module with a Windows branch: OpenSSH for Windows keeps key-file permission handling in one
  place (`contrib/win32/win32compat`, `FixHostFilePermissions`); the protected-DACL recipe
  (`SetNamedSecurityInfoW` with `PROTECTED_DACL_SECURITY_INFORMATION`, one ACE for the owner SID) is the
  documented Windows equivalent of 0600. WIN-FEAS picks the binding.
- Engine X7b `fileaccess.write_private` (`fileaccess/_private.py`), whose recipe `_atomic.py` already mirrors
  (`_atomic.py:7-8`).

## 3. Reuse decision: why the CLI does not import engine `write_private`

`decoy_engine.fileaccess.write_private(request: FileRequest, data: bytes)` is public
(`fileaccess/__init__.py:34`), but the CLI does not call it, and it is not copied either:

1. It takes a `FileRequest` and calls `current().output_dir(request).begin("file", "replace", label=...)`
   (engine `fileaccess/_private.py:45`), so it needs an active engine file-access policy that has issued an
   output directory. CLI writes go to paths the user chose (`--output`, `--vault`, `--evidence-out`) under
   the ambient CLI policy, often before or after any engine run scope. Wrapping each in a synthetic
   `FileRequest` would push CLI path semantics into the engine's policy, against "library code does not know
   its callers" (CLI `CLAUDE.md:13`).
2. The CLI already owns the equivalent core, `_atomic._staged` (`_atomic.py:247`), mirrored from the engine
   recipe without its policy so it runs on Windows (`_atomic.py:7-8`). Importing the engine helper as well
   would put two private-write cores in one process, which is the blocked shape.
3. X7c adds no new write core. `_private_file.py` takes the creation and mode half of `_atomic` (moved, not
   copied); `_atomic.py` keeps publication.

Pinning the two repos: both sentries use the same rule numbers (P1 disposition, P2 private only through the
helper, P3 no chmod swallowed, P4 no mode change outside the helper) and the same acceptance ids (AT-P1 to
AT-P3). The CLI P4 is stricter than the engine's (it covers `fchmod` too, because the CLI has one module that
applies modes); the sentry docstring says so. `_private_file.py`'s docstring names engine
`fileaccess/_private.py` and the engine sentry; a change to either contract names the other repo's plan row in
its own plan. No runtime coupling.

## 4. Design notes

### Choke point and registry

- Choke point: `src/decoy/_private_file.py`. It owns every owner-only creation and every mode change in the
  CLI. It imports nothing from `decoy`.
  - `apply_mode(fd: int, path: str, bits: int) -> None`: the one mode call. POSIX: `fchmod(fd, bits)`.
    Windows: `os.chmod(path, bits)` (today's `_atomic.py:229` branch). Raises plain `OSError`.
  - `restrict_owner_only(fd: int, path: str, *, directory: bool = False) -> None`: `apply_mode` with 0600
    (0700 for a directory), then on POSIX re-`fstat` and raise `OSError(EPERM)` if a group or other bit
    remains. On Windows it returns after `apply_mode`, as files do today.
  - `create_exclusive(parent: Path, base: str, *, private: bool) -> tuple[str, int]`: moved from
    `_atomic._create_temp` and `_temp_name` (`_atomic.py:174-199`) with the same flags (`O_WRONLY | O_CREAT
    | O_EXCL | O_NOFOLLOW`), mode 0600 when private else 0666, the same `.decoy-<hex>.tmp` name and the same
    retry on `FileExistsError`. It records the created bits, then narrows the temp to 0600 while it is written
    (today's `_atomic.py:269`, which applies to public temps too), by descriptor. If narrowing fails it closes
    and unlinks the file it created before raising, because `_staged` has no temp name yet at that point.
    Raises plain `OSError`.
  - `open_private(path: Path, *, new_parent: bool) -> None`: create-or-open for a writer that opens the path
    itself (SQLite). `O_RDWR | O_CREAT | O_NOFOLLOW`, mode 0600, then `restrict_owner_only` on that descriptor
    (repairs a file an earlier build left 0644), and for a parent this call created, `restrict_owner_only(...,
    directory=True)` on an `O_DIRECTORY | O_NOFOLLOW` descriptor (on Windows, which cannot open a directory,
    through `apply_mode` by path, as `_restrict` does today). Raises `PrivateFileError("private_open_failed",
    errno)` when the open fails and `PrivateFileError("private_mode_failed", errno)` when narrowing fails.
  - `create_private_temp(prefix: str) -> Path`: `create_exclusive` in `tempfile.gettempdir()` with
    `private=True`, for the `decoy.mask()` spool. It keeps the one central `.tmp` naming rule; the caller's
    source entry already declares `format = "parquet"`. Raises `PrivateFileError` with the same two codes.
  - `PrivateFileError(code, errno)`: a subclass of `OSError` with `errno` set and no `filename`, so
    `decoy.mask()` callers that catch `OSError` today (`api.py:447` does not map staging errors) still catch
    it; its text is the code only, no path, and it is raised outside the `except` block so no `OSError` is
    chained. Like engine `fileaccess/_private.py:36-42`, it saves the errno and raises outside the handler
    with no filename; the CLI error code and text remain its own contract.
- `_atomic.py` imports `create_exclusive`, `apply_mode` and `restrict_owner_only` and calls them where it
  creates and changes modes today (`_atomic.py:229,231,269,348`). Because they raise plain `OSError`, the
  existing handlers in `_staged` (`_atomic.py:266-270`), `_publish`'s caller and `_restrict_fd_target`
  (`_atomic.py:335-352`) map every failure to `AtomicWriteError` unchanged.
- Private entry points: `_atomic.write_atomic`, `_atomic.write_local_target` (both publish 0600,
  `_atomic.py:144-156,326-329`), `_atomic.staged_private_target`, `cli/io/_targets.write_private_table`,
  `_private_file.open_private` and `_private_file.create_private_temp`. `_atomic.staged_local_target` and
  `cli/io/_targets.write_table` are public entry points.
- Registry: `tests/sentry/io_policy/file_sinks.toml`. One row per (file, enclosing qualified function, sink
  kind, one-based call ordinal in AST source order): `disposition`, `reason`, and for a private raw sink
  `via` (the entry point whose result it writes into). The ordinal, rather than a line number, keeps the
  identity stable across unrelated line moves and makes a second same-kind sink in the same function red.
  Dispositions:
  - `public`: written with the umask default or the old file's bits; needs a reason.
  - `private`: the sink is an entry-point call (needs no row), or a raw sink with `via` (section rules).
  - `staged`: a raw sink writing into a stager the function receives as a parameter; G-ONE-TARGET-WRITE
    already checks every caller passes a real stager (`test_target_writes.py` `STAGE_CALLS`).
  - `read`: opened read-only.
  - `temp`: a 0700 stdlib temp directory or a file inside one; only allowed in the baseline.
- Baseline: `tests/sentry/baselines/private-file-sinks.json` (shrink-only, registered in
  `scripts/dev/sentry_registry.toml`, checked by `scripts/dev/ratchet_check.py`), 5 rows, each with its exit.
- Guard test: `tests/sentry/io_policy/test_private_files.py`, G-ONE-PRIVATE-FILE. It reuses the shared
  scanner `tests/sentry/io_policy/_calls.py`. S3 extends that scanner's one traversal to return normalized
  call records with the call node, resolved name, qualified scope, bindings and the ancestor path as
  `(node, child_field)` pairs. Existing
  `call_sites` and `call_contexts` become projections of the same records, so P1 to P4 add no second walker.

### Rules the sentry enforces (same numbering as engine `tests/sentry/test_private_files.py`)

- P1: every raw sink (section 6.5 list) and every one-based ordinal has a registry row; every row has that
  exact live sink (stale or extra ordinals fail); the disposition is one of the five values; the reason is
  non-empty. Watched sinks include engine `write_fixed_width` and `tarfile.TarFile.extractall`. An
  `.execute(...)` call whose SQL text (string constant or f-string parts) contains `COPY` and `TO`, matched
  case-insensitively, is a raw sink.
- P1b: `PRIVATE_CASES` in the sentry maps every private entry-point call site and every `via` row
  (`file::function::sink::ordinal`) to an AT-P3 test id; a site with no entry, an entry with no live site, or
  an id that is not a test in `tests/e2e/private_file/test_private_surfaces.py` or
  `tests/unit/private_file/test_private_file.py` fails.
- P2: a raw sink with disposition `private` passes only when its `via` entry point is called earlier in the
  same function and the sink's path argument is the same local name as that call's path argument or result
  (`with staged_private_target(p) as tmp` then `tmp`; `tmp = create_private_temp(...)` then `tmp`;
  `open_private(path, ...)` then `str(path)`; `str()`, `os.fspath()` and `.as_posix()` are stripped). A
  `temp` row, or a private row that fails the binding check, must be in the baseline.
- P3: using the shared call record's ancestor path, `os.chmod`, `os.fchmod`, `os.lchmod`, `Path.chmod` in a
  `Try.body` whose handler body is only `pass`, `continue` or `...` fails, anywhere in `src/decoy/`. Calls in
  `except`, `else` and `finally` blocks are not misclassified as calls in the guarded body.
- P4: a mode call outside `_private_file.py` fails. The only exception is the exact identity
  `distribution/installer.py::_write_launcher_shim::os.chmod::1` with literal mode 0o755
  (`distribution/installer.py:669`); a missing call, a changed mode or any second call fails.
- P5: `_private_file.py` imports nothing from `decoy` (no cycle with `_atomic`).

Named limits of the walk: P2's `via` check is source order in one function, not that the entry point runs on
every path (the token vault connects without `open_private` on its `create=False` path, correct for an
existing vault); SQL other than `COPY ... TO` (for example `ATTACH` or `EXPORT DATABASE`), SQL held in a
variable, and `.sql()`, `duckdb.sql()` and `executemany` calls; a reference through a runtime-bound name, an
alias by assignment, `from x import *`, and filesystem calls that do not create new regular-file content
bytes (`os.link`, `os.symlink`, `mkdir`), which the atomic-writer sentry or the installer's own tests cover.

### Symlinks

Every file `_private_file` creates is opened with `O_NOFOLLOW` at the created name; the staging name is also
`O_EXCL`, so a planted entry there is a collision and the loop retries with a fresh random name. A symlink at
a user-chosen final target keeps today's documented behavior (followed, its destination replaced:
`_atomic.py:357-381`); the bytes land 0600, so following cannot widen access. OQ1 asks whether to refuse a
target symlink owned by another user.

### Mask-secret surfaces from the AST

`tests/sentry/test_mask_secret_file_mode.py:99` hand-lists `_CLI_SURFACES`. S3 replaces the list with a
derivation: walk `src/decoy/` with `_calls.py` for calls to `decoy._mask_secret.admitted_key_provider`,
key each by `file::qualname::ordinal`, and look each key up in `ADMISSION_SITES`, a mapping from site to the
surface ids or test functions that exercise it (`cli/run.py::run` to `run` and `run_chunked`;
`cli/unmask.py::unmask` to `unmask`; `cli/report.py::_vault` to `report_vault`;
`cli/tokenize.py::tokenize` to `tokenize`; `api.py::mask` to `test_api_mask_refuses_an_unsafe_file`,
`test_api_mask_reads_the_checked_descriptor`).
`_CLI_SURFACES` becomes the tuple of the CLI ids. The check fails when a derived ordinal is missing from the
mapping, a mapping key has no live site, an id is not handled by `_argv` (each id must produce argv without
the `assert written is not None` fallback misrouting), or a named test function does not exist in the module.

## 5. Behavior

### 5.1 Private writes through `_atomic` (unchanged API)

`write_atomic`, `write_local_target` and `staged_private_target` behave as today. The staging file comes from
`_private_file.create_exclusive` and every mode change from `apply_mode`. A failure there is an `OSError`
inside `_atomic`, so callers still see `AtomicWriteError(ATOMIC_WRITE_FAILED, errno)` (AT-P1d).

### 5.2 Plan artifact (`decoy validate compile --output`)

`cli/compile_explain.py:243` moves to `write_local_target(out, text.encode("utf-8"), WriteMode.REPLACE)`, with
`AtomicWriteError` rendered by `_atomic.describe` and exit `EXIT_RUNTIME`, the same shape as
`cli/fit.py:497-503`. The artifact is 0600 and atomic. Byte content is unchanged (AT-P3 compares with a golden
written before the change).

### 5.3 Token vault

`LocalTokenVault.__init__` calls `_private_file.open_private(path, new_parent=parent_is_new)` instead of the
inline `os.open` plus `_restrict`, which is deleted. `private_open_failed` maps to
`TokenVaultError(code="vault_open_error")` and `private_mode_failed` to `"vault_permission_error"`, today's
codes (`cli/_token_vault.py:110-113,138-145`); the message no longer carries the path. The `-journal` file is
0600 during a write transaction under umask 000 (AT-P3). `tests/unit/test_token_vault.py:217` patches
`os.fchmod` instead of `os.chmod`.

### 5.4 `decoy.mask()` spool

`api.py::_stage_source_entry` takes its temp from `create_private_temp(prefix=f"decoy-mask-{name}-")` and
appends it to `tmp_paths` before `pq.write_table` at `api.py:263` writes into it (a private raw sink, `via =
"create_private_temp"`). Cleanup uses the existing `tmp_paths` finalizer, including when the Parquet write
fails. The `api.py` entry leaves
`tests/sentry/baselines/atomic-writer-allow.json` and the `ALLOWLIST` in `tests/sentry/test_atomic_writer.py`
(no `mkstemp` left in `api.py`); the `target-writes-allow.json` row stays (still not a target write).

### 5.5 Windows

`apply_mode` on Windows is today's `os.chmod(path, bits)` and `restrict_owner_only` adds no check there. WIN-FEAS
changes `apply_mode`, `create_exclusive` (an ACL set at create time) and `open_private`, all in one module.

## 6. Enumerations (from the code at `994bc7a`)

### 6.1 Exit paths

- `decoy validate compile --output` write failure: today an uncaught `OSError` (a traceback carrying the path,
  exit 1); after S2, `atomic_write_failed (<strerror>)` on stderr and `EXIT_RUNTIME`, the
  `cli/fit.py:497-503` shape.
- Token vault create or narrow failure: `TokenVaultError` codes `vault_open_error` and
  `vault_permission_error` (`cli/_token_vault.py:110-113,138-145`), unchanged codes.
- `decoy.mask()` spool failure: `OSError` from `mkstemp` today (`api.py:258`); after S2 a `PrivateFileError`
  with a code and no path.
- `_atomic` write failure, including a narrowing failure: `AtomicWriteError` (`_atomic.py:112-121`),
  unchanged.

### 6.2 Routes

- Whole-table private output: `write_private_table` (`cli/io/_targets.py:392-398`) through
  `staged_private_target`.
- Bytes to a user-chosen path: `write_local_target` (`_atomic.py:144-156`), used by evidence, fit, report,
  scan, ci, the debug log and (after S2) the plan artifact.
- Library-named files: `write_atomic` (`_atomic.py:124-141`), used by the installer trust state.
- Writer opens the path itself: `open_private` (token vault) and the baselined `mkstemp` in
  `cli/run.py:1602`, whose path the engine vault writer reopens (engine `vault.py:269`, "a path that is
  overwritten as it always was" under the ambient CLI policy, so the 0600 mode survives).

### 6.3 FK shapes

N/A: X7c changes file modes and creation calls only; no table, key or relationship code is touched, and
output bytes are pinned unchanged by AT-P3.

### 6.4 Fields

- Registry row fields: `file`, `function` (qualified), `sink` (kind), `ordinal` (one-based within the same
  file, function and sink), `disposition`, `reason`, `via`
  (private raw sinks only).
- Baseline entry fields (`private-file-sinks.json`): key `file::function::sink::ordinal`, `reason`, `exit`; top-level
  `sentry_id = "private-file-sinks"`, `created_in = "X7c-S3"`.
- `PrivateFileError` fields: `code` (`private_open_failed`, `private_mode_failed`), `errno` (mirrors
  `AtomicWriteError`, `_atomic.py:112-121`).

### 6.5 Output surfaces (census of every CLI write site)

Regenerated by an AST walk of `src/decoy/` at `994bc7a` (calls to `open` with a write mode, `Path.open`,
`write_text`, `write_bytes`, `os.open`, `os.fdopen`, `tempfile.*`, `sqlite3.connect`, `duckdb.connect`,
pandas, pyarrow and fixed-width writers, tar extraction, `shutil` copies, `chmod`/`fchmod`, and the `_atomic`
and `_targets` entry points), plus a grep for SQL `COPY ... TO`. 58 sites: 9 inside `_atomic.py` (the
implementation, not listed) and 49 below.

| Site | What it writes | Disposition | Through today | After X7c |
|---|---|---|---|---|
| `cli/unmask.py:281` | restored original values | private | `write_private_table` | same |
| `cli/tokenize.py:729` | detokenized original values | private | `write_private_table` | same |
| `cli/run.py:1162` | evidence manifest (config, counts, key label) | private | `write_local_target` | same |
| `cli/fit.py:497` | fit snapshot (statistics of raw data) | private | `write_local_target` | same |
| `cli/report.py:86` | report text (`_write_out`) | private | `write_local_target` | same |
| `cli/report.py:705` | report render (`_render`, incl. `report vault`) | private | `write_local_target` | same |
| `cli/scan.py:775` | scan profile | private | `write_local_target` | same |
| `cli/ci.py:189` | CI check output | private | `write_local_target` | same |
| `ci/debug.py:43` | CI debug log | private | `write_local_target` | same |
| `distribution/installer.py:219` | installer trust state | private | `write_atomic` | same |
| `cli/compile_explain.py:243` | frozen plan artifact (seed envelope, generation payload) | private | `write_text`, umask mode | `write_local_target` (S2) |
| `cli/_token_vault.py:109` | token vault file (cleartext re-identification map) | private | inline `os.open` 0600 | `open_private` (S2) |
| `cli/_token_vault.py:122` | token vault SQLite connection and journals | private | file pre-created 0600 | raw sink, `via = "open_private"` |
| `cli/_token_vault.py:137` | `chmod` of the vault and its new parent | private | inline `os.chmod` by path | deleted; `fchmod` inside `open_private` (S2) |
| `api.py:258` | `decoy.mask()` spool file | private | `tempfile.mkstemp` | `create_private_temp` (S2) |
| `api.py:263` | the spool's Parquet bytes | private | `pq.write_table` into the 0600 temp | raw sink, `via = "create_private_temp"` |
| `cli/run.py:1602` | vault staging file | private | `tempfile.mkstemp` | baseline, exit L5a (`_vault_commit.py`) |
| `cli/run.py:1606` | reopen of the vault temp for fsync | private | `os.open(O_RDWR)` | baseline, exit L5a |
| `cli/run.py:649` | DuckDB spill directory | temp | `tempfile.mkdtemp` (0700) | baseline, exit WIN-FEAS |
| `cli/_duckdb_source.py:110` | unmasked source table extract (`COPY ... TO`) into that directory | temp | DuckDB `COPY`, umask mode inside the 0700 dir | baseline, exit WIN-FEAS |
| `ci/engine_logging.py:29` | engine log scratch directory | temp | `TemporaryDirectory` (0700) | baseline, exit WIN-FEAS |
| `cli/io/_targets.py:364,366,368` | table bytes into the stager's temp (public or private by caller) | staged | stager passed by caller | same (G-ONE-TARGET-WRITE checks the stager) |
| `cli/io/_targets.py:422` | masked whole-table output (`write_targets`) | public | `write_table` | same |
| `cli/io/_targets.py:337` | fixed-width masked output | public | engine `write_fixed_width` | same |
| `cli/io/_targets.py:453,455,457,461` | chunked masked output | public | `staged_local_target` and writes into its temp | same |
| `cli/init.py:537,618,634,670` | scaffolded `pipeline.yaml` | public (OQ2) | `write_text` | same |
| `cli/schema.py:73` | `PipelineConfig` JSON schema | public | `write_text` | same |
| `cli/demo.py:64,152,156,332,356,371` | synthetic demo data, profile and config | public | `write_text`, `open("w")` | same |
| `_update_check.py:71` | update-check cache (time, version) | public | `write_text` | same |
| `distribution/installer.py:665,667,669` | 0755 launcher shim | public | `mkstemp`, `fdopen`, `chmod 0o755` | same (P4 exact exception) |
| `distribution/installer.py:344` | verified runtime bundle files | public | filtered `tar.extractall` into the install staging directory | same |
| `distribution/lock.py:51` | empty install lock file | public | `os.open(O_CREAT, 0o600)` | same |
| `_mask_secret.py:124` | mask secret, opened read-only | read | `os.open(O_RDONLY)` | same |
| `cli/_duckdb_source.py:81` | DuckDB source database | read | `duckdb.connect(read_only=True)` | same |

Totals (49): private 18 today (10 through entry points, 8 raw), temp 3, staged 3, public 23, read 2. After S2
(48): 13 private entry-point calls, 2 private raw sinks with `via`, 2 private baseline rows (L5a), 3 temp
baseline rows (WIN-FEAS), 3 staged, 23 public, 2 read; `_token_vault.py:137` is gone and
`compile_explain.py:243`, `_token_vault.py:109` and `api.py:258` become entry-point calls. Baseline at S3: 5
rows.

## 7. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | plan artifact, token vault, spool, restored output written wider than 0600 | private entry points publish 0600; registry disposition per sink | AT-P3 per private surface under umask 000 | M3: write the plan artifact with `write_text` again |
| 2 | Cleanup missing on an exit path | staging temps on failure; spool temps | `_atomic._staged` removes the temp on every exit (unchanged); `create_private_temp` paths stay in `tmp_paths` cleanup | AT-P1d: injected narrowing failure leaves no temp (`test_atomic_staged.py:166` `_names == ["out.csv"]`) | M2: drop the unlink in `create_exclusive`'s narrowing failure branch |
| 3 | State and ordering | owner-only before the first byte | `create_exclusive` and `open_private` create with 0600, narrow by descriptor and return only then | AT-P1a stats the temp before the first write under umask 000 | M1: create with 0o666 and drop the narrowing in `create_exclusive` |
| 4 | Route parity and silent fallback | public versus private writes chosen per caller | entry points classify themselves; raw sinks need a row; `via` binding checked | AT-P2a, AT-P2c | M4: delete one registry row |
| 5 | Referential integrity | N/A: no tables, keys or relationships change; bytes pinned by AT-P3 | N/A | N/A | N/A |
| 6 | Untrusted producer | a planted symlink at the token vault path or at a staging name | `O_NOFOLLOW` on `open_private`; `O_EXCL` plus fresh-name retry on staging | AT-P1c (symlink at the vault path refused with `ELOOP`; collision at a staging name retried, link target unchanged) | M6: drop `O_NOFOLLOW` from `open_private` |
| 7 | Check then use on a path (TOCTOU) | create then chmod by path (`_token_vault.py:109,137`) | narrowing by descriptor, never by path | AT-P1f: path swapped between open and narrow leaves the swapped-in file's mode unchanged | M7: narrow by path in `open_private` |
| 8 | Weak tests and overclaimed evidence | a mode asserted only after publish hides a window | AT-P1a asserts the mode before the first byte, under umask 000, in a subprocess | AT-P1a | M1 must turn it red, which proves it observes the create mode |
| 9 | Behavior-preserving refactor drift | moving `_create_temp` out of `_atomic` | moved code, unchanged flags, names and retry; existing `tests/unit/test_atomic*.py` run unchanged | existing atomic tests plus AT-P1 | M9: change the temp suffix (`test_atomic*.py` name checks) |
| 10 | Frozen contract drift | `AtomicWriteError` codes, `TokenVaultError` codes, `decoy validate compile --output` bytes | codes unchanged; plan bytes compared with a golden | AT-P3 golden, AT-P1d, existing token vault tests | M10: rename `vault_permission_error` |

## 8. Acceptance tests (red first)

Each is written and seen red (or, for behavior that already holds, seen red under its mutation) before the
code in its slice.

- AT-P1a (S1): under `os.umask(0)` in a subprocess, `staged_private_target(p)` yields a temp whose `os.stat`
  mode is 0600 before any byte is written; `write_local_target` publishes 0600. Red under M1.
- AT-P1b (S1): `create_private_temp` and `open_private` produce 0600 under umask 000; `open_private` repairs an
  existing 0644 file to 0600 and narrows a parent it created to 0700.
- AT-P1c (S1): a symlink at the `open_private` path is refused with `private_open_failed` and errno `ELOOP`,
  and the link's target is unchanged; with `secrets.token_hex` patched to return a planted name once,
  `create_exclusive` retries with a fresh name and the planted symlink's target is unchanged.
- AT-P1d (S1): a `narrow` step added to `tests/unit/test_atomic_staged.py:152` for a private write
  (`staged_private_target` and `write_local_target`): `os.fchmod` raising gives
  `AtomicWriteError(ATOMIC_WRITE_FAILED, errno)` with no path in its text and no temp left behind; the same for
  the fd-alias narrowing in `_restrict_fd_target`.
- AT-P1e (S1): on POSIX, `restrict_owner_only` leaves no group or other bit and raises `OSError(EPERM)` when
  `fchmod` is patched to a no-op; with `_private_file._WINDOWS` patched true it calls `os.chmod` by path and
  makes no check.
- AT-P1f (S1): with `os.open` in `_private_file` wrapped to rename a different file onto the path right after
  the open, `open_private` narrows the opened inode, and the swapped-in file keeps its mode.
- AT-P3 (S2, e2e, umask 000 in a subprocess): each private surface is 0600 after the command: `decoy validate
  compile --output` (and its bytes equal the golden), `decoy tokenize --vault` (the database and its
  `-journal` during a held write transaction), `decoy unmask --output`, `decoy detokenize`, `decoy run
  --vault` and `--evidence-out`, `decoy fit`, `decoy scan --output`, one `decoy report` case per writing
  function (`cli/report.py:86` `_write_out` and `cli/report.py:705` `_render`), `decoy ci ... --output` and
  the debug log, and the `decoy.mask()` spool while it exists. The installer trust state
  (`distribution/installer.py:219`) gets a unit-level case in the same S2 file set (it needs no download:
  call the trust-state recorder with a fixture document). A unit case injects a `pq.write_table` failure and
  asserts the registered spool path is removed by the existing finalizer.
- AT-P2a to AT-P2l (S3, seeded sources parsed in the test, each red): (a) `path = settings.key_path;
  path.write_bytes(v)` with no row; (b) `p = Path(cfg.key_dir) / name; p.write_text(v)` with no row; (c)
  `open(target, "wb")` in a row marked private whose `via` call is absent; (d) `try: os.chmod(p, 0o600)
  except OSError: pass`; (e) `os.chmod(p, 0o600)` outside `_private_file.py`; (f) `from os import chmod as c;
  c(p, mode)`; (g) a registry row whose sink is gone; (h) a baseline key added (ratchet); (i)
  `conn.execute(f"COPY t TO '{dest}'")` with no row; (j) a second `Path.write_text` in a function whose first
  ordinal already has a row; (k) `os.chmod(p, 0o700)` outside `_private_file.py`; (l) an import from `decoy`
  in `_private_file.py`.
- AT-P2j (S3): the live tree passes with the 5-row baseline, and `PRIVATE_CASES` (rule P1b) maps every private
  entry-point call site and every `via` row to an existing AT-P3 test (a new private site without a case
  fails, and so does a case id that names no test).
- AT-S1 (S3): the mask-secret derivation finds five admission sites; a seeded module with a sixth call and a
  second call inside an already mapped function both fail naming `file::function::ordinal`; a mapping id that
  is not a `_CLI_SURFACES` member handled by `_argv`, or a test name absent from the module, fails.

## 9. Owner questions (each answerable alone; recommended answer first)

- OQ1. Should a user-chosen target that is a symlink owned by another user be refused? Recommended: yes, as
  `atomic_write_failed` with `EPERM`. It mirrors Linux `fs.protected_symlinks`, which macOS lacks; it closes
  the case where another local user redirects a write onto one of the victim's own files (data loss, not a
  leak, since the bytes land 0600). A symlink the user owns is still followed. S1 builds it only after a yes;
  otherwise it is a follow-up.
- OQ2. Are scaffolded configs (`decoy init`) public? Recommended: yes. They hold column names, types, paths and
  secret references (`env:`, `file:`), never a secret value or a raw value (`cli/init.py:412-440` reads only
  profile field names), and teams commit them. The task brief listed them as private; this answer changes
  that, so it needs the owner's word.
- OQ3. Do masked outputs keep the old file's mode bits (public)? Recommended: yes, the existing contract
  (`_atomic.py:384-394`); masked data is the shareable product.
- OQ4. Is the plan artifact private? Recommended: yes (section 1), the same class as the fit snapshot.

## 10. Reuse inventory

- `src/decoy/_atomic.py`: the publish core `_staged`, entry points, `AtomicWriteError` shape. Reused; its
  creation and mode half moves to `_private_file.py`.
- `tests/sentry/io_policy/_calls.py`: import resolution and qualified scopes. Reused by the new sentry and by
  the mask-secret derivation; S3 adds call records and ancestor metadata to its one traversal, with the
  existing APIs projected unchanged from that core.
- `tests/sentry/_ratchet.py`, `scripts/dev/ratchet_check.py`, `scripts/dev/sentry_registry.toml`: the
  shrink-only baseline machinery.
- `tests/sentry/test_sentry_manifest.py`: the new sentry is added to `SENTRIES` so the gate collects it.
- `tests/sentry/io_policy/test_target_writes.py` `STAGE_CALLS`: the `staged` disposition defers to it.
- Engine `tests/sentry/test_private_files.py`: rule numbering and seeded-case shapes, copied as a contract,
  not as code.

## 11. Placement

| Item | Where | CODEMAP row | Size |
|---|---|---|---|
| `_private_file.py` (`apply_mode`, `restrict_owner_only`, `create_exclusive`, `open_private`, `create_private_temp`, `PrivateFileError`) | `src/decoy/` (10 modules today, 11 after) | `CODEMAP.md:48`, private shared filesystem primitives | ~170 lines new |
| `_atomic.py` shrink | `src/decoy/` | `CODEMAP.md:48` | 493 to ~455 |
| Unit tests AT-P1 | `tests/unit/private_file/test_private_file.py` (new sub-package: `tests/unit/` already has 39 flat modules) | map change in S1: `CODEMAP.md:48` is edited to send new private-filesystem contract tests to `tests/unit/<concern>/` | ~260 |
| AT-P1d step | `tests/unit/test_atomic_staged.py` (edited, 517 to ~545) | `CODEMAP.md:48` | +30 |
| AT-P3 e2e | `tests/e2e/private_file/test_private_surfaces.py` (new sub-package: `tests/e2e/` has 81 flat Python modules) | map change in S1: a new CODEMAP row sends private-filesystem surface contracts to `tests/e2e/<concern>/`; current row 59 covers CLI-format tests only | ~260 |
| Sentry G-ONE-PRIVATE-FILE | `tests/sentry/io_policy/test_private_files.py` (`tests/sentry/` has 26 flat modules; `io_policy/` has 3) | `CODEMAP.md:57` | ~320 |
| Shared call scanner extension | `tests/sentry/io_policy/_calls.py` (edited) | `CODEMAP.md:57`, shared I/O policy scanner | +50 |
| Sink registry | `tests/sentry/io_policy/file_sinks.toml` | `CODEMAP.md:57` | ~150 |
| Baseline | `tests/sentry/baselines/private-file-sinks.json` | `CODEMAP.md:56` | ~30 |
| Mask-secret derivation | `tests/sentry/test_mask_secret_file_mode.py` (edited, 318 to ~370) | `CODEMAP.md:56` | +50 |
| Call-site moves | `cli/compile_explain.py`, `cli/_token_vault.py`, `api.py` | `cli/` is frozen for new modules; edits in place are allowed | net about -25 |

## 12. Frozen contracts touched

- `AtomicWriteError` codes and texts: unchanged, including for a narrowing failure (AT-P1d).
- `TokenVaultError` codes `vault_open_error`, `vault_permission_error`: unchanged codes; the message drops the
  path.
- `decoy validate compile --output` file bytes: unchanged; mode becomes 0600 and the write becomes atomic; a
  write failure becomes a coded `EXIT_RUNTIME` error instead of a traceback (additive, pre-GA).
- `decoy.mask()` return value and cleanup: unchanged; a spool failure is still an `OSError` (now the
  `PrivateFileError` subclass, with no filename).
- Sentry baselines: one new id (`private-file-sinks`); `atomic-writer-allow.json` loses the `api.py` entry
  (shrink).

## 13. Slices

Each slice is at most 10 files and 800 lines, on its own branch from CLI `main`, tests on the Mac or a VM
(never the devbox), T0 per edit, T1 per commit, T2 at the slice head.

| Slice | Content | Files | Lines | Depends on |
|---|---|---|---|---|
| S1 | `_private_file.py`; move `_create_temp`/`_temp_name` and every mode call out of `_atomic.py`; OQ1 check if answered yes; AT-P1a to AT-P1f; CODEMAP row | `src/decoy/_private_file.py`, `src/decoy/_atomic.py`, `tests/unit/private_file/__init__.py`, `tests/unit/private_file/test_private_file.py`, `tests/unit/test_atomic_staged.py`, `CODEMAP.md` | ~500 | CLI X0a (on main) |
| S2 | Move `compile_explain.py:243`, `_token_vault.py:109,137`, `api.py:258` onto the entry points; retarget the token vault test; drop the `api.py` atomic-writer entry; AT-P3 | `src/decoy/cli/compile_explain.py`, `src/decoy/cli/_token_vault.py`, `src/decoy/api.py`, `tests/unit/test_token_vault.py`, `tests/sentry/baselines/atomic-writer-allow.json`, `tests/sentry/test_atomic_writer.py`, `tests/e2e/private_file/__init__.py`, `tests/e2e/private_file/test_private_surfaces.py`, `tests/unit/private_file/test_private_file.py` (trust-state case) | ~430 | S1 |
| S3 | Shared normalized call records; G-ONE-PRIVATE-FILE sentry, ordinal registry, 5-row baseline, sentry registry row, manifest row; ordinal AST-derived mask-secret surfaces | `tests/sentry/io_policy/_calls.py`, `tests/sentry/io_policy/test_private_files.py`, `tests/sentry/io_policy/file_sinks.toml`, `tests/sentry/baselines/private-file-sinks.json`, `scripts/dev/sentry_registry.toml`, `tests/sentry/test_sentry_manifest.py`, `tests/sentry/test_mask_secret_file_mode.py` | ~670 | S2 |

The sentry lands last so its baseline starts at the 5 rows with named exits; S1 and S2 carry their own red-first
tests. The full suite runs before S1 and S2 merge (escalation triggers: S1 moves a shared primitive, S2 changes
a sentry baseline and an error path); S3 runs T1 plus the sentry folder.

## 14. Pre-mortem

- A narrowing failure escapes as a new exception type: prevented by the plain-`OSError` rule inside `_atomic`
  and pinned by AT-P1d; a builder who makes `restrict_owner_only` raise `PrivateFileError` turns AT-P1d red.
- An import cycle: rule P5 fails if `_private_file.py` imports anything from `decoy`.
- The registry rots into a rubber stamp (every new sink marked public). Mitigation: a `public` row needs a
  reason and a reviewer reads each new row; AT-P2j derives AT-P3 cases only from private rows, so a wrong
  `public` stays a review item, named in the sentry docstring.
- Umask is process-wide, so AT-P1a and AT-P3 set it in a subprocess, never in the pytest worker.
- L5a moves `_commit_vault` while S3 is open: the baseline keys `cli/run.py::_commit_vault::*` go stale and P1
  fails loudly; L5a renames the rows in its own slice (named in each row's `exit`).
- The `via` binding check is a same-function name match. A builder who passes the path through a helper
  function loses the binding and lands in the baseline, which the ratchet refuses; the fix is to call the entry
  point in the function that writes.
- SQLite journal mode: the token vault uses the default rollback journal; if a later change enables WAL, the
  `-wal` and `-shm` files take the database mode by the same SQLite rule, and AT-P3 is extended in that change.

## 15. Follow-ups (recorded, not in V1)

- WIN-FEAS (row 89): implement the Windows branches of `apply_mode`, `create_exclusive` and `open_private` with a
  protected owner-only DACL, and add a `private_temp_dir` helper that takes the three `temp` baseline rows.
- L5a: move `_commit_vault` onto `create_exclusive` when it becomes `_vault_commit.py`, removing two baseline
  rows.
- OQ1 if deferred: the symlink-owner check.
- V2 descriptor handoff: evaluate descriptor-taking SQLite, PyArrow and atomic-writer interfaces before
  changing the existing close-then-reopen paths. This is a theoretical local swap race, not a V1 blocker.
