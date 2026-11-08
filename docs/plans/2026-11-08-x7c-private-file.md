Status: plan

# X7c: one choke point for CLI private files (roadmap row 24)

Owner: Cam. Author: claudeworkerbee (Opus). Date: 2026-11-08. Scope: CLI, V1. Revision 1.

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`
(PLAN: choke point, Placement, Design notes, Established solutions), `feature-dev.md`, `architecture.md`
(layout), `reuse-first.md`, `security.md`, `testing.md`, `cross-cutting-concerns.md`; the plan contract
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
this plan names the one seam it extends and builds nothing for Windows.

## 1. FRAME

### Problem

The CLI writes files that hold raw values or secrets: the encrypted vault, the token vault (a cleartext
re-identification map), restored `unmask` and `detokenize` output, fit snapshots, evidence manifests,
reports, scan profiles, the debug log, frozen plan artifacts and the `decoy.mask()` spool of the caller's
DataFrame. Most already go through `src/decoy/_atomic.py`, whose private forms publish 0600. Four do not:

1. `cli/compile_explain.py:243` writes the plan artifact with `Path.write_text`: umask default mode, not
   atomic. The plan carries the seed envelope and, with statistical generate columns, the fitted generation
   payload (engine `plan/_types.py:283`, field `generation`), the same class of data as the fit snapshot that
   `cli/fit.py:497` already writes 0600. This is the one live gap.
2. `cli/_token_vault.py:109,137` creates the SQLite file with `os.open(..., 0o600)` and then chmods the file
   and its new parent by hand (`_restrict`). Correct on POSIX today, but a second owner-only idiom.
3. `api.py:258` spools the caller's DataFrame through `tempfile.mkstemp` (0600 by the stdlib guarantee).
   Correct on POSIX, a third idiom.
4. `cli/run.py:1602` stages the vault through `tempfile.mkstemp` inside `_commit_vault` (L5a moves this
   function to `_vault_commit.py`), and `cli/run.py:649` and `ci/engine_logging.py:29` make 0700 temp
   directories through the stdlib.

Nothing stops a fifth idiom, and nothing names the place WIN-FEAS must change: today the 0600 narrowing sits
in five calls across two modules (`_atomic.py:229,231,269,348`, `cli/_token_vault.py:137`).

### Guarantee (what V1 promises)

- Every CLI file write is classified `public`, `private`, `read` or `temp` in one registry. A new write with no
  row fails the sentry.
- A `private` file is owner-only (0600 on POSIX) from its first byte, under any umask including 000. It is
  written through one of the private entry points (section 4), which create the staging file exclusively and
  never through a symlink (`O_CREAT | O_EXCL | O_NOFOLLOW`), and publish atomically where the writer has a
  target (old bytes or new bytes, never neither).
- Owner-only narrowing (`chmod`, `fchmod`) happens in one function, `_private_file.restrict_owner_only`. WIN-FEAS
  replaces its Windows branch and nothing else.
- Errors carry a code and an errno, never a path (the existing `_atomic.AtomicWriteError` rule).
- The mask-secret admission sentry derives the admitting call sites from the AST; a new admission site with no
  surface test fails.

### Non-goals (V1)

- Windows ACLs (row 89). Today the Windows branch keeps the documented behavior: the file inherits its
  folder's permissions (`_atomic.py:396-404`).
- The vault commit transaction (`cli/run.py:1577`, L5a) and the install-directory swaps in `distribution/`.
  Both stay where they are, with baseline rows that name their exit.
- Directory modes created by `mkdir` for parents. A private file inside a shared directory is still 0600;
  the token vault keeps narrowing a parent it creates (section 5.3).
- Making scaffolded configs, masked outputs, the JSON schema, the demo data or the update-check cache private
  (section 9, OQ2 and OQ3).

### Failure modes

| Failure | Today | After X7c |
|---|---|---|
| Plan artifact with a generation payload written 0644 under umask 022 (0666 under 000) | yes (`compile_explain.py:243`) | 0600, atomic (S3) |
| A new command writes a key or map with `write_text` | silent | sentry red (new sink, no row) |
| A builder adds `os.chmod(p, 0o600)` in a `try` with `pass` | silent | sentry red (rule P3) |
| A builder narrows a mode outside the seam | silent | sentry red (rule P4) |
| WIN-FEAS has to find every 0600 site | five calls in two modules | one function |
| A new `admitted_key_provider` call with no surface test | silent (hand list `_CLI_SURFACES`) | sentry red |
| Temp file created through a pre-planted symlink | already refused (`_atomic.py:188`) | unchanged, now pinned by AT-P1c |

## 2. Established solutions

- Exclusive create at the final mode, then fsync, then `rename`: the SQLite rollback-journal commit and the
  ext4 rename and fsync notes, already cited in `_atomic.py:3-9`. Creating with mode 0600 in `open(2)` means the
  umask can only remove bits, so the file is never wider than 0600 between create and narrow (POSIX `open`,
  `umask`).
- `O_NOFOLLOW | O_EXCL` for the staging file: the CERT rule FIO15-C and the Python `tempfile.mkstemp`
  implementation (`_mkstemp_inner` uses `O_EXCL | O_NOFOLLOW` and mode 0600).
- `tempfile.mkdtemp` makes a directory "readable, writable, and searchable only by the creating user ID"
  (Python docs); the baseline rows rely on that guarantee on POSIX.
- SQLite gives a database's `-journal` and `-wal` files the mode of the database file (`findCreateFileMode`
  in `os_unix.c`), so creating the database 0600 covers its journals.
- One narrowing function with a Windows branch: OpenSSH for Windows keeps owner-only key handling in one
  routine (`contrib/win32/win32compat`, `FixHostFilePermissions`), and the protected-DACL recipe
  (`SetNamedSecurityInfoW` with `PROTECTED_DACL_SECURITY_INFORMATION`, an ACE for the owner SID only) is the
  documented Windows equivalent of 0600. WIN-FEAS picks the binding; this plan only fixes the seam.
- Engine X7b `fileaccess.write_private` (`fileaccess/_private.py`), whose recipe `_atomic.py` already mirrors
  (`_atomic.py:7-8`).

## 3. Reuse decision: why the CLI does not import engine `write_private`

`decoy_engine.fileaccess.write_private(request: FileRequest, data: bytes)` is public
(`fileaccess/__init__.py:34`), but the CLI does not call it, and it is not copied either:

1. It takes a `FileRequest` and calls `current().output_dir(request).begin("file", "replace", label=...)`,
   so it needs an active engine file-access policy that has issued an output directory. CLI writes go to paths
   the user chose (`--output`, `--vault`, `--evidence-out`) under the ambient CLI policy, often before or after
   any engine run scope. Wrapping each in a synthetic `FileRequest` would push CLI path semantics into the
   engine's policy, against "library code does not know its callers" (CLI `CLAUDE.md:13`).
2. The CLI already owns the equivalent core, `_atomic._staged` (`_atomic.py:247`), mirrored from the engine
   recipe without its policy so it runs on Windows (`_atomic.py:7-8`). Importing the engine helper as well
   would put two private-write cores in one process, which is the blocked shape.
3. X7c therefore adds no new write core. `_private_file.py` takes the creation and narrowing half of `_atomic`
   (moved, not copied) and becomes the place the mode decision lives; `_atomic.py` keeps publication.

Pinning the two repos: both sentries use the same rule numbers (P1 disposition, P2 private only through the
helper, P3 no chmod swallowed, P4 no narrowing outside the helper) and the same acceptance ids (AT-P1 to AT-P3).
`_private_file.py`'s docstring names engine `fileaccess/_private.py` and the engine sentry; a change to either
contract names the other repo's plan row in its own plan. No runtime coupling.

## 4. Design notes

### Choke point and registry

- Choke point: `src/decoy/_private_file.py`. It owns every owner-only creation and narrowing in the CLI:
  - `restrict_owner_only(fd: int, *, directory: bool = False) -> None`: the seam. POSIX: `fchmod(fd, 0o700 if
    directory else 0o600)`, then re-`fstat` and raise `PrivateFileError("private_mode_failed", errno)` if any
    group or other bit remains. Windows: returns without change today, with the docstring stating the
    inheritance behavior; WIN-FEAS replaces this branch.
  - `create_exclusive(parent: Path, base: str, *, private: bool) -> tuple[str, int]`: moved from
    `_atomic._create_temp` and `_temp_name` (`_atomic.py:174-199`), unchanged in behavior: `O_WRONLY | O_CREAT
    | O_EXCL | O_NOFOLLOW`, mode 0600 when private, a random `.decoy-<hex>.tmp` suffix that fits `PC_NAME_MAX`.
    For a private file it calls `restrict_owner_only` on the new descriptor before returning (replaces
    `_atomic.py:269`).
  - `open_private(path: Path, *, new_parent: bool) -> None`: create-or-open for a writer that must open the
    path itself (SQLite). `O_RDWR | O_CREAT | O_NOFOLLOW`, mode 0600, then `restrict_owner_only` on the
    descriptor (repairs a file an earlier build left 0644), and on a parent this call created,
    `restrict_owner_only(directory=True)` through an `O_DIRECTORY` descriptor. Replaces `_token_vault.py:109,137`.
  - `create_private_temp(prefix: str, suffix: str) -> Path`: `create_exclusive` in `tempfile.gettempdir()`,
    for the `decoy.mask()` spool. Replaces `api.py:258`.
  - `PrivateFileError(code, errno)`: same shape as `AtomicWriteError` (code text only, no path, no chained
    cause).
- `_atomic.py` imports `create_exclusive` and `restrict_owner_only` from `_private_file` and calls the seam
  where it narrows today: the publish step for private writes (`_atomic.py:229,231`) and the fd-alias narrowing
  (`_atomic.py:348`). `_final_bits` keeps the public path (old file's bits). No import goes the other way.
- Private entry points (the only ways a `private` row may be written): `_atomic.write_atomic`,
  `_atomic.write_local_target` (both forms publish 0600, `_atomic.py:144-156,326-329`), `_atomic.staged_private_target`,
  `cli/io/_targets.write_private_table`, and `_private_file.open_private`, `create_private_temp`.
- Registry: `tests/sentry/io_policy/file_sinks.toml`. One row per (file, enclosing qualified function, sink
  kind): `disposition = "public" | "private" | "read" | "temp"`, `reason`. Entry-point calls classify
  themselves (private, or public for `staged_local_target`) and need no row. Raw sinks (section 6.5) need a
  row. A raw sink whose row says `private` fails unless the row is in the shrink-only baseline
  `tests/sentry/baselines/private-file-sinks.json` (registered in `scripts/dev/sentry_registry.toml`, checked
  by `scripts/dev/ratchet_check.py`).
- Guard test: `tests/sentry/io_policy/test_private_files.py`, G-ONE-PRIVATE-FILE. It reuses the shared
  scanner `tests/sentry/io_policy/_calls.py` (import resolution, qualified scopes), so no second walker.

### Rules the sentry enforces (same numbering as engine `tests/sentry/test_private_files.py`)

- P1: every raw sink has a registry row; every row has a live sink (stale rows fail); `disposition` is one of
  the four values; `reason` is non-empty.
- P2: a raw sink with `disposition = "private"` fails unless baselined. The baseline starts with the rows S3
  removes and the three rows with a named exit (section 6.5).
- P3: `os.chmod`, `os.fchmod`, `os.lchmod`, `Path.chmod` inside a `try` whose handler body is only `pass`,
  `continue` or `...` fails, anywhere in `src/decoy/`.
- P4: a mode-setting call outside `_private_file.py` fails unless its mode is a constant with an execute bit
  (the 0755 launcher at `distribution/installer.py:669`, which stays public). A non-constant mode outside
  `_private_file.py` also fails.

### Symlinks

The staging file and every file `_private_file` creates are opened with `O_NOFOLLOW | O_EXCL` (or
`O_NOFOLLOW` for `open_private`, which may reopen an existing vault). A symlink at a user-chosen final target
keeps today's documented behavior (followed, its destination replaced: `_atomic.py:357-381`); the bytes land
0600, so following cannot widen access. OQ1 asks whether to refuse a target symlink owned by another user.

### Mask-secret surfaces from the AST

`tests/sentry/test_mask_secret_file_mode.py:99` hand-lists `_CLI_SURFACES`. S2 replaces the list with a
derivation: walk `src/decoy/` with `_calls.py` for references to `decoy._mask_secret.admitted_key_provider`,
key each by `file::qualname`, and look each key up in `ADMISSION_SITES`, a mapping from site to the surface
ids that exercise it (`cli/run.py::run` to `run` and `run_chunked`; `cli/unmask.py::unmask`;
`cli/report.py::_vault` to `report_vault`; `cli/tokenize.py::tokenize`; `api.py::mask` to the `decoy.mask()`
tests). `_CLI_SURFACES` becomes the union of the CLI entries. A derived site missing from the mapping, or a
mapping key with no live site, fails at collection with the site named.

## 5. Behavior

### 5.1 Private writes through `_atomic` (unchanged API)

`write_atomic`, `write_local_target` and `staged_private_target` behave as today. The only change is that the
staging file comes from `_private_file.create_exclusive` and the final narrowing from `restrict_owner_only`.
The temp is 0600 before its first byte under umask 000 (AT-P1a).

### 5.2 Plan artifact (`decoy validate compile --output`)

`cli/compile_explain.py:243` moves to `write_local_target(out, text.encode("utf-8"), WriteMode.REPLACE)`, with
`AtomicWriteError` rendered by `_atomic.describe` and exit `EXIT_RUNTIME`, the same shape as `cli/fit.py:497`.
The artifact is 0600 and atomic. Byte content is unchanged (AT-P3 compares with a pre-change golden).

### 5.3 Token vault

`LocalTokenVault.__init__` calls `_private_file.open_private(path, new_parent=parent_is_new)` instead of the
inline `os.open` plus `_restrict`. Error mapping is kept: a `PrivateFileError` becomes
`TokenVaultError(code="vault_permission_error")` or `"vault_open_error"` as today, still without the path in
the code. The `-journal` file is 0600 during a write transaction under umask 000 (AT-P3).

### 5.4 `decoy.mask()` spool

`api.py::_stage_source_entry` takes its temp from `create_private_temp(prefix=f"decoy-mask-{name}-",
suffix=".parquet")`. Cleanup through `tmp_paths` is unchanged. The `api.py` row leaves
`tests/sentry/baselines/atomic-writer-allow.json` (one `mkstemp` site fewer) and the `target-writes-allow.json`
row stays (still a non-target table write).

### 5.5 Windows

`restrict_owner_only` on Windows returns without change, as the files do today. Nothing else in the CLI
narrows a mode, so WIN-FEAS edits one function and adds its own tests.

## 6. Enumerations (from the code at `994bc7a`)

### 6.1 Exit paths

- `decoy validate compile --output` write failure: today an uncaught `OSError` (a traceback carrying the path, exit 1
  from Typer); after S3, `atomic_write_failed (<strerror>)` on stderr and `EXIT_RUNTIME`, the
  `cli/fit.py:497-503` shape.
- Token vault create or narrow failure: `TokenVaultError` codes `vault_open_error` and
  `vault_permission_error` (`cli/_token_vault.py:110-113,138-145`), unchanged codes.
- `decoy.mask()` spool failure: `OSError` from `mkstemp` today (`api.py:258`); after S3 a `PrivateFileError`
  with a code and no path, mapped where `api.py` maps other staging errors.
- `_atomic` publish failure: `AtomicWriteError` (`_atomic.py:112-121`), unchanged.

### 6.2 Routes

- Whole-table private output: `write_private_table` (`cli/io/_targets.py:392-398`) through
  `staged_private_target`.
- Bytes to a user-chosen path: `write_local_target` (`_atomic.py:144-156`), used by evidence, fit, report,
  scan, ci and the debug log.
- Library-named files: `write_atomic` (`_atomic.py:124-141`), used by the installer trust state.
- Writer opens the path itself: `open_private` (token vault) and the baselined `mkstemp` in
  `cli/run.py:1602`, whose descriptor the engine vault writer reopens (engine `vault.py:269`, "a path that is
  overwritten as it always was" under the ambient CLI policy, so the 0600 mode survives).

### 6.3 FK shapes

N/A: X7c changes file modes and creation calls only; no table, key or relationship code is touched, and
output bytes are pinned unchanged by AT-P3.

### 6.4 Fields

- Registry row fields: `file`, `function` (qualified), `sink` (kind), `disposition`, `reason`.
- Baseline entry fields (`private-file-sinks.json`): key `file::function::sink`, `reason`, `exit` (the row or
  slice that removes it); top-level `sentry_id = "private-file-sinks"`, `created_in = "X7c-S2"`.
- `PrivateFileError` fields: `code`, `errno` (mirrors `AtomicWriteError`, `_atomic.py:112-121`).

### 6.5 Output surfaces (census of every CLI write site)

Regenerated by an AST walk of `src/decoy/` at `994bc7a` (calls to `open` with a write mode, `Path.open`,
`write_text`, `write_bytes`, `os.open`, `os.fdopen`, `tempfile.*`, `sqlite3.connect`, `duckdb.connect`,
pandas and pyarrow writers, `shutil` copies, `chmod`/`fchmod`, and the `_atomic` entry points). 55 sites; the 9
inside `_atomic.py` are the implementation and are not listed. Disposition is what S2's registry records.

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
| `cli/compile_explain.py:243` | frozen plan artifact (seed envelope, generation payload) | private | `write_text`, umask mode | `write_local_target` (S3) |
| `cli/_token_vault.py:109` | token vault file (cleartext re-identification map) | private | inline `os.open` 0600 | `open_private` (S3) |
| `cli/_token_vault.py:122` | token vault SQLite connection and journals | private | file pre-created 0600 | same, after `open_private` |
| `cli/_token_vault.py:137` | `chmod` of the vault and its new parent | private | inline `os.chmod` | seam (S3) |
| `api.py:258` | `decoy.mask()` spool file | private | `tempfile.mkstemp` | `create_private_temp` (S3) |
| `api.py:263` | the spool's Parquet bytes | private | `pq.write_table` into the 0600 temp | same, into the new temp |
| `cli/run.py:1602` | vault staging file | private | `tempfile.mkstemp` | baseline, exit L5a (`_vault_commit.py`) |
| `cli/run.py:1606` | reopen of the vault temp for fsync | private | `os.open(O_RDWR)` | baseline, exit L5a |
| `cli/run.py:649` | DuckDB spill directory (raw rows) | temp | `tempfile.mkdtemp` (0700) | baseline, exit WIN-FEAS |
| `ci/engine_logging.py:29` | engine log scratch directory | temp | `TemporaryDirectory` (0700) | baseline, exit WIN-FEAS |
| `cli/io/_targets.py:364,366,368` | table bytes into the stager's temp | public | stager passed by caller | same (G-ONE-TARGET-WRITE checks the stager) |
| `cli/io/_targets.py:453,455,457,461` | chunked masked output | public | `staged_local_target` | same |
| `cli/init.py:537,618,634,670` | scaffolded `pipeline.yaml` | public (OQ2) | `write_text` | same |
| `cli/schema.py:73` | `PipelineConfig` JSON schema | public | `write_text` | same |
| `cli/demo.py:64,152,156,332,356,371` | synthetic demo data, profile and config | public | `write_text`, `open("w")` | same |
| `_update_check.py:71` | update-check cache (time, version) | public | `write_text` | same |
| `distribution/installer.py:665,667,669` | 0755 launcher shim | public | `mkstemp`, `chmod 0o755` | same (P4 allows an execute bit) |
| `distribution/lock.py:51` | empty install lock file | public | `os.open(O_CREAT, 0o600)` | same |
| `_mask_secret.py:124` | mask secret, opened read-only | read | `os.open(O_RDONLY)` | same |
| `cli/_duckdb_source.py:81` | DuckDB source | read | `duckdb.connect(read_only=True)` | same |

Totals after X7c: 16 private sites through entry points, 4 private or temp sites in the baseline with a named
exit, 29 public, 2 read. The baseline at S2 holds 9 rows (the 4 above plus `compile_explain.py:243`,
`_token_vault.py:109,137`, `api.py:258,263`); S3 shrinks it to 4.

## 7. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | plan artifact, token vault, spool, restored output written wider than 0600 | private entry points publish 0600; registry disposition per sink | AT-P3 per private surface under umask 000 | M3: write the plan artifact with `write_text` again |
| 2 | Cleanup missing on an exit path | staging temps on failure; spool temps | `_atomic._staged` removes the temp on every exit (unchanged); `create_private_temp` paths stay in `tmp_paths` cleanup | AT-P1d: injected `restrict_owner_only` failure leaves no temp | M2: drop the unlink in the `create_exclusive` failure branch |
| 3 | State and ordering | narrowing must precede the first byte | `create_exclusive` narrows before returning the name; `open_private` narrows before SQLite connects | AT-P1a stats the temp before the first write | M1: move the narrowing after the write |
| 4 | Route parity and silent fallback | public versus private stager chosen per caller | entry points classify themselves; raw sinks need a row | AT-P2a: a raw sink with no row fails | M4: delete one registry row |
| 5 | Referential integrity | N/A: no tables, keys or relationships change; bytes pinned by AT-P3 | N/A | N/A | N/A |
| 6 | Untrusted producer | a user-chosen path that is a pre-planted symlink or FIFO | staging opens `O_NOFOLLOW | O_EXCL`; specials are written through as today | AT-P1c: a symlink at the temp name is refused | M6: drop `O_NOFOLLOW` from `create_exclusive` |
| 7 | Check then use on a path (TOCTOU) | create then chmod by path (`_token_vault.py:109,137`) | narrowing by descriptor (`fchmod` on the opened fd), never by path | AT-P3 token vault case with the path swapped between open and narrow | M7: narrow by path in `open_private` |
| 8 | Weak tests and overclaimed evidence | mode asserted only after publish hides a window | AT-P1a asserts the mode before the first byte, under umask 000, in its own process | AT-P1a | M8: set umask 022 in the test (it must still pass only because of the helper, checked by M1) |
| 9 | Behavior-preserving refactor drift | moving `_create_temp` out of `_atomic` | moved code, unchanged flags and names; existing `tests/unit/test_atomic*.py` run unchanged except the `_WINDOWS` patch target | existing atomic tests plus AT-P1 | M9: change the temp suffix |
| 10 | Frozen contract drift | `AtomicWriteError` codes, `TokenVaultError` codes, `decoy validate compile --output` bytes | codes unchanged; plan bytes compared with a golden | AT-P3 golden and existing token vault tests | M10: rename `vault_permission_error` |

## 8. Acceptance tests (red first)

Each is written and seen red (or, for behavior that already holds, seen red under its mutation) before the
code in its slice.

- AT-P1a (S1): under `os.umask(0)` in a subprocess, `staged_private_target(p)` yields a temp whose
  `os.stat` mode is 0600 before any byte is written; `write_local_target` publishes 0600.
- AT-P1b (S1): `create_private_temp` and `open_private` produce 0600 under umask 000; `open_private` repairs an
  existing 0644 file to 0600 and narrows a parent it created to 0700.
- AT-P1c (S1): a symlink planted at the staging name, or at the `open_private` path, is refused
  (`private_mode_failed` or `atomic_write_failed` with errno `ELOOP`), and the link's target is unchanged.
- AT-P1d (S1): `restrict_owner_only` raising leaves no temp behind and raises a code with no path in its text.
- AT-P1e (S1): on POSIX, `restrict_owner_only` leaves no group or other bit; with `_private_file._WINDOWS`
  patched true it changes nothing (the documented seam).
- AT-P2a to AT-P2h (S2, seeded sources parsed in the test, each red): (a) `path = settings.key_path;
  path.write_bytes(v)` with no row; (b) `p = Path(cfg.key_dir) / name; p.write_text(v)` with no row; (c)
  `open(target, "wb")` in a function whose row says private and is not baselined; (d) `try: os.chmod(p, 0o600)
  except OSError: pass`; (e) `os.chmod(p, 0o600)` outside `_private_file.py`; (f) `from os import chmod as c;
  c(p, mode)`; (g) a registry row whose sink is gone; (h) a baseline key added (ratchet).
- AT-P2i (S2): the live tree passes with the 9-row baseline.
- AT-S1 (S2): the mask-secret sentry derives five admission sites; adding a call to `admitted_key_provider`
  in a seeded module with no `ADMISSION_SITES` entry fails, naming `file::function`.
- AT-P3 (S3, e2e, umask 000): each private surface is 0600 after the command: `decoy validate compile --output` (and its
  bytes equal the golden), `decoy tokenize --vault` (the database and its `-journal` during a held write
  transaction), `decoy unmask --output`, `decoy detokenize`, `decoy run --vault` and `--evidence-out`, `decoy
  fit`, `decoy scan --output`, `decoy report ... --output`, `decoy ci ... --output` and the debug log, and the
  `decoy.mask()` spool while it exists. The case list is derived from the registry's private rows and entry
  point call sites, so a new private row without a case fails.

## 9. Owner questions (each answerable alone; recommended answer first)

- OQ1. Should a user-chosen target that is a symlink owned by another user be refused? Recommended: yes, in S1,
  as `atomic_write_failed` with `EPERM`. It mirrors Linux `fs.protected_symlinks`, which macOS lacks; it closes
  the case where another local user redirects a write onto one of the victim's own files (data loss, not a
  leak, since the bytes land 0600). A symlink the user owns is still followed.
- OQ2. Are scaffolded configs (`decoy init`) public? Recommended: yes. They hold column names, paths and secret
  references (`env:`, `file:`), never a secret value or a raw value (`cli/init.py:412-440` reads only
  profile field names), and teams commit them. The task brief listed them as private; this answer changes
  that, so it needs the owner's word.
- OQ3. Do masked outputs keep the old file's mode bits (public)? Recommended: yes, the existing contract
  (`_atomic.py:384-394`); masked data is the shareable product.
- OQ4. Is the plan artifact private? Recommended: yes (section 1), the same class as the fit snapshot.

## 10. Reuse inventory

- `src/decoy/_atomic.py`: the publish core `_staged`, entry points, `AtomicWriteError` shape. Reused; its
  creation half moves to `_private_file.py`.
- `tests/sentry/io_policy/_calls.py`: import resolution and qualified scopes. Reused by the new sentry and by
  the mask-secret derivation; no new walker.
- `tests/sentry/_ratchet.py`, `scripts/dev/ratchet_check.py`, `scripts/dev/sentry_registry.toml`: the shrink-only
  baseline machinery.
- `tests/sentry/test_sentry_manifest.py`: the new sentry is added to `SENTRIES` so the gate collects it.
- Engine `tests/sentry/test_private_files.py`: rule numbering and seeded-case shapes, copied as a contract,
  not as code.

## 11. Placement

| Item | Where | CODEMAP row | Size |
|---|---|---|---|
| `_private_file.py` (seam, `create_exclusive`, `open_private`, `create_private_temp`, `PrivateFileError`) | `src/decoy/` (10 modules today, 11 after) | `CODEMAP.md:48`, private shared filesystem primitives | ~150 lines new |
| `_atomic.py` shrink | `src/decoy/` | `CODEMAP.md:48` | 493 to ~460 |
| Unit tests AT-P1 | `tests/unit/private_file/test_private_file.py` (new sub-package: `tests/unit/` already has 41 flat modules) | `CODEMAP.md:48` row edited to name `tests/unit/<noun>/` for new primitives | ~220 |
| Sentry G-ONE-PRIVATE-FILE | `tests/sentry/io_policy/test_private_files.py` (`tests/sentry/` has 26 flat modules; `io_policy/` has 3) | `CODEMAP.md:57` | ~280 |
| Sink registry | `tests/sentry/io_policy/file_sinks.toml` | `CODEMAP.md:57` | ~130 |
| Baseline | `tests/sentry/baselines/private-file-sinks.json` | `CODEMAP.md:56` | ~45 at S2, ~25 at S3 |
| Mask-secret derivation | `tests/sentry/test_mask_secret_file_mode.py` (edited, 318 to ~360) | `CODEMAP.md:56` | +45 |
| AT-P3 e2e | `tests/e2e/private_file/test_private_surfaces.py` (new sub-package: `tests/e2e/` has 82 flat modules) | `CODEMAP.md:59` pattern of named e2e folders | ~250 |
| Call-site moves | `cli/compile_explain.py`, `cli/_token_vault.py`, `api.py` | `cli/` is frozen for new modules; edits in place are allowed | net about -20 |

## 12. Frozen contracts touched

- `AtomicWriteError` codes and texts: unchanged.
- `TokenVaultError` codes `vault_open_error`, `vault_permission_error`: unchanged.
- `decoy validate compile --output` file bytes: unchanged; mode becomes 0600 and the write becomes atomic; a write
  failure becomes a coded `EXIT_RUNTIME` error instead of a traceback (additive, pre-GA).
- `decoy.mask()` return value and cleanup: unchanged.
- Sentry baselines: one new id (`private-file-sinks`); `atomic-writer-allow.json` loses the `api.py` entry
  (shrink).

## 13. Slices

Each slice is at most 10 files and 800 lines, on its own branch from CLI `main`, tests on the Mac or a VM
(never the devbox), T0 per edit, T1 per commit, T2 at the slice head.

| Slice | Content | Files | Lines | Depends on |
|---|---|---|---|---|
| S1 | `_private_file.py`; move `_create_temp`/`_temp_name` from `_atomic.py`; seam calls in `_atomic.py`; OQ1 check in `_atomic._staged_target`; AT-P1a to AT-P1e; `tests/unit/test_atomic.py` `_WINDOWS` patches retargeted; CODEMAP row | `src/decoy/_private_file.py`, `src/decoy/_atomic.py`, `tests/unit/private_file/__init__.py`, `tests/unit/private_file/test_private_file.py`, `tests/unit/test_atomic.py`, `CODEMAP.md` | ~420 | CLI X0a (on main) |
| S2 | G-ONE-PRIVATE-FILE sentry, registry, 9-row baseline, sentry registry row, manifest row; AST-derived mask-secret surfaces | `tests/sentry/io_policy/test_private_files.py`, `tests/sentry/io_policy/file_sinks.toml`, `tests/sentry/baselines/private-file-sinks.json`, `scripts/dev/sentry_registry.toml`, `tests/sentry/test_sentry_manifest.py`, `tests/sentry/test_mask_secret_file_mode.py` | ~520 | S1 |
| S3 | Move `compile_explain.py:243`, `_token_vault.py:109,137`, `api.py:258` onto the entry points; baseline 9 to 4 rows; atomic-writer baseline shrink; AT-P3 | `src/decoy/cli/compile_explain.py`, `src/decoy/cli/_token_vault.py`, `src/decoy/api.py`, `tests/sentry/baselines/private-file-sinks.json`, `tests/sentry/baselines/atomic-writer-allow.json`, `tests/sentry/test_atomic_writer.py`, `tests/sentry/io_policy/file_sinks.toml`, `tests/e2e/private_file/__init__.py`, `tests/e2e/private_file/test_private_surfaces.py` | ~380 | S2 |

S3 touches `tests/sentry/test_atomic_writer.py` only to drop the `api.py` `AllowedInline` entry. The full
suite runs before S1 and S3 merge (escalation triggers: S1 moves a shared primitive, S3 changes a sentry
baseline and serialization of an error path); S2 runs T1 plus the sentry folder.

## 14. Pre-mortem

- The `_WINDOWS` patches in `tests/unit/test_atomic.py:225-376` stop steering the narrowing once it lives in
  `_private_file`. S1 retargets them to `_private_file._WINDOWS` where the test is about mode bits and keeps
  `_atomic._WINDOWS` where it is about rename retries; a test that silently stops covering Windows narrowing is
  the failure, so AT-P1e covers the seam directly.
- An import cycle if a later change makes `_private_file` import `_atomic`. The sentry S2 adds a one-line rule:
  `_private_file.py` imports nothing from `decoy`.
- The registry rots into a rubber stamp (every new sink marked public). Mitigation: a `public` row needs a
  reason, and a reviewer reads each new row; the AT-P3 derivation catches only private rows, so this stays a
  review item, named in the sentry docstring.
- Umask is process-wide, so AT-P1a and AT-P3 set it in a subprocess, never in the pytest worker.
- L5a moves `_commit_vault` while S2 is open: the baseline key `cli/run.py::_commit_vault::mkstemp` then goes
  stale and P1 fails loudly; L5a renames the row in its own slice (named in the row's `exit`).
- SQLite journal mode: the token vault uses the default rollback journal; if a later change enables WAL, the
  `-wal` and `-shm` files take the database mode by the same SQLite rule, and AT-P3 is extended in that change.

## 15. Follow-ups (recorded, not in V1)

- WIN-FEAS (row 89): implement the Windows branch of `restrict_owner_only` with a protected owner-only DACL and
  move the two `temp` baseline rows onto a `private_temp_dir` helper.
- L5a: move `_commit_vault` onto `create_exclusive` when it becomes `_vault_commit.py`, removing two baseline
  rows.
