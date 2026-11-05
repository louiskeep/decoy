Status: plan

# LIB: the local record library and its retention classes

Owner: Cam. Date: 2026-11-05. Scope: CLI V1 (CLI repo, plus one engine module).
Planned against CLI `origin/main` 8fba6af and engine `origin/main` 41a86f47, and
the SCAN-MULTI plan on engine branch `plan/scan-multi` at 9b7cd9ab plus its
Revision 5 (written in the same pass as this plan's Revision 5).

Rules consulted: `dev-rules/README.md`, `00-universal.md`,
`risk-and-exceptions.md`, `development-loop.md`, `feature-dev.md`,
`architecture.md`, `cross-cutting-concerns.md`, `api-and-compatibility.md`,
`data-and-migrations.md`, `destructive-operations.md`,
`observability-and-resilience.md`, `security.md`, `reuse-first.md`,
`testing.md`.

Risk: R2. The work adds a persisted on-disk format that the platform will
import, new frozen artifact tags, a concurrency scheme across processes and
operating systems, private file handling, and a prune command that deletes
files. `decoy run` gains a default side effect. Nothing is irreversible for
user data: prune and clean only touch Decoy's own area and preview first.
Approver: Cam.

Owner direction, 2026-11-05:

- "local record library. we should plan this now so we can have a modular
  design for any other job logs or records or data information we want to
  store locally for the user."
- "does decoy CLI also store job logs? audit and server logs apply to
  platform, but job logs: might want to store those in the library or maybe
  they should be separate? What's the logical separation for different data
  retention?"
- Starter YAML columns with no PII found default to `redact`: "redact is an
  easier way to see that your data is wrong than passthrough for new users or
  if you just make a mistake." (This answers SCAN-MULTI Q9.)
- CLI V1 ships first as a free download used in production pipelines, on
  Linux and macOS, and Windows if possible. The paid platform comes later and
  must be able to import or mirror the same records.

## Revision 5 (2026-11-05): joint Dennis review of LIB 6b50e729 and SCAN-MULTI 9b7cd9ab

Numbered 5 to match the SCAN-MULTI revision written in the same pass; LIB had
revisions 1 and 2 before it. Dennis returned GO-WITH-FIXES. Each claim was
checked against CLI `origin/main` 8fba6af and engine `origin/main` 41a86f47
before the fix was adopted; none was found wrong.

| Finding | Change |
|---|---|
| XH1 | L2 is the only build slice for the scan record; SCAN-MULTI S1d is a pointer to it. Kind `scan-set`, payload tag `scan-set/v1`, objects under `.decoy/library/objects/`, failure warns and keeps the exit code, guards G-LIB-WRITER and G-KIND-CANARY. L2 is rewritten against SCAN-MULTI 9b7cd9ab (the `.decoy/scans/<time>-<hash>` design is gone from both plans). |
| XH2 | L2 adds the envelope branch to SCAN-MULTI's one reader, `load_scan_set(path)` (`records.decode`, id-to-name check, `RecordNeedsNewer`, then the payload). The "S3-engine baseline loader" wording is removed: S3-engine only adds the config field. Tests L2-load-envelope; SCAN-MULTI T4-compare-both and T4-preflight-both. |
| XH3 | 4.1 gives scan's root: `--library`, `DECOY_LIBRARY`, `--emit-config` directory, `--config` directory, current directory. L3a's L3-baseline-link now runs scan, emit and run end to end and checks the link resolves in the same library. |
| XH4 | L2 passes `Library.scratch("scan-integrity", delete_on_exit)` as SCAN-MULTI's new `spill_dir`; with the library off, the engine's own private temp root is used. The scan canary also checks that no spill file outlives the scan. |
| XM1 | SCAN-MULTI S3a-cli owns the ref `scan-set/baseline/<slug>` (slug rule there), set under the L1c lock; a failed save omits `scan_baseline`. 4.5 points at it. |
| XM2 | The only key L2 adds to scan `--json` is `library`; SCAN-MULTI T2-parquet-compat allows exactly that key. L2-saved pins its shape. |
| XM3 | The `scan-set` payload model is SCAN-MULTI S1a's `ScanSetCore`. L1a registers `scan-set` as reserved until the S1a release (or points at the model if S1a merged first). Test A1-scan-model-same. |
| XM4 | New section 5.0 Sequencing, identical in both plans: registry chain (SUB-STOP 1.6.0, STORM E1 1.7.0, then REG-RENUMBER at merge), releases one at a time, build order, one writer per shared file. The platform ROADMAP is not edited here. |
| XM5 | SCAN-MULTI S3-cli split into S3a-cli and S3b-cli. |
| LH1 | Writes validate with the strict model; reads use a tolerant variant (`extra="ignore"`, nested models too) with the major check kept. Test A1-read-tolerant, mutation MA1-read-strict. |
| LH2 | The index is checked against the object names on every open (one directory listing, no file reads) and brought up to date automatically under the lock; a crash between rename and insert, or a `git pull`, can no longer hide a record. Tests C1-hand-added and C1-crash-gap. A stale-marker file was considered and dropped: the name-set check is exact and needs no cleanup rules. |
| LM1 | Under `DECOY_LIBRARY=off` the job log goes to the root the chain resolves with the env step skipped (`--library`, else YAML directory, else current directory). 4.1, 4.16 and L5-always say so. |
| LM2 | Automatic deletes (sample replace, TTL, log rotation) are best effort per file and never change the exit code; explicit `prune --yes` and `clean --yes` report each file left behind and exit 4. Windows-lane tests with an open handle: L3b-replace-open, L3b-ttl-open, L5-rotate-open, L4b-clean-open. |
| LM3 | Remote filesystems are detected when the library opens (`GetDriveTypeW` returns `DRIVE_REMOTE` or the path is UNC on Windows; `statfs` type on Linux and macOS) and the library goes to degraded mode up front. Guarantee 6 is scoped to local filesystems; synced folders are documented as single-writer only. Test C1-remote-fs. |
| LM4 | One id rule everywhere: parse, drop `id`, canonicalize, hash. `fsck`, `put` and `decode` all use it. `.decoy/.gitattributes` gets `library/objects/** -text`. Test C1-crlf. |
| LM5 | `fsck` mode findings cover scratch, logs, the index and `tmp/`; a group- or world-readable record or ref is an advisory note that does not change the exit code (git checks records out 0644). |
| LM6 | `created_at` has microseconds; `latest` orders by `(created_at, id)`, which is the same on every machine and after a rebuild. Clock skew between machines is a documented limit. Test L2-same-instant. |
| LM7 | The `cli-local-1` payload model moves to the engine (`records/_kinds.py`), so the platform importer can decode evidence records and G-KIND-CANARY does not depend on CLI import order. A CLI test pins that `build_manifest` output validates against it. |
| LM8 | Verified: `_safe_registered_code` maps unregistered codes to `unregistered_reason` (`_progress_events.py:101-105`). L1a registers the CLI-side event codes in the engine registry, on the chain in section 5.0. |
| LM9 | "Parallel on non-overlapping files" removed. Section 5.0 serializes the `run.py`, `scan.py` and `library.py` writers (orchestrator ruling). |
| LM10 | L5b depends on L5a (and L4a for `show`) only. Logs are found by `invocation_id`; L3a adds the `log` link when it lands. |
| LM11 | Verified: `tests/e2e/test_stateless_cli.py:89` asserts no `.decoy` path is created. L5b replaces that assertion with a named, stronger one (section 5 L5b); deleting it is a gate finding. |
| LM12 | Each kind spec declares its path fields; export strips only those and remaps `links` inside the export to the new ids, in link order. Test L4b-export-remap. |
| LM13 | L4 split into L4a (list, show, ref, diff) and L4b (prune, export, clean). `_scratch.py` and `_winacl.py` move from L1b into a new L1d. |
| LL1 | `CREATE_ONCE` uses a no-clobber primitive (`os.link` on POSIX, `os.rename` on Windows); "already exists" means verify, then success. |
| LL2 | Verified: `distribution/layout.py:31` and `.decoy-ci.yaml` users. G-LIB-WRITER matches `.decoy` as a path component in string literals, outside docstrings, with a ratchet allowlist (the runtime home in `layout.py`). |
| LL3 | `index.sqlite` is pre-created 0600 with `os.open(..., 0o600)` before `sqlite3.connect`, the `_token_vault.py:108-115` recipe. |
| LL4 | Non-finite payload floats are mapped to `None` in the payload model (SCAN-MULTI S1a); test T1-empty-table there and L2-empty-table here. |
| LL5 | Windows path budget stated in 4.2: roots longer than 150 characters are refused with `library_path_too_long`. Test L1b-win-long-root. |
| LL6 | The log header's `command` is a closed enum (`run`, `scan`), never `argv`. Test L5-header-closed. |
| LL7 | Scratch ACL is set at creation: SDDL `D:P(A;OICI;FA;;;<user SID>)(A;OICI;FA;;;SY)` through `ConvertStringSecurityDescriptorToSecurityDescriptorW`, passed to `CreateDirectoryW`, so there is no unprotected window. |
| LL8 | Record payload paths are stored relative to the project directory (the library root's parent); absolute only when no relative path exists. L2 and L3a do the rewrite before `build`. |
| LL9 | Header refreshed to SCAN-MULTI 9b7cd9ab; the repeated Q9 reversal text is removed from L2 (SCAN-MULTI Revision 3 already applied it). |
| Owner rule (2026-11-05) | New section 3.1 "Central registries and sizing": existing copies found in the CLI and engine, which ones the library reuses, one shared CLI atomic writer with a ratchet guard, and a per-slice file layout with sizes; files over 800 lines that a slice touches must not grow. |

## Revision 2 (2026-11-05): owner and orchestrator answers

Applied to head 43ccfb01. Answers to section 6:

- **Q5 (owner): option 1.** The default `.decoy/.gitignore` ignores `logs/`,
  `scratch/` and the index (plus `library/tmp/` and `library/quarantine/`).
  Records stay committable, so baselines reach CI. No change to 4.9.
- **Q8 (owner): yes.** "anytime a job runs it should write a log." Every
  `decoy run` writes its job log and its run-result record by default.
  `--no-library` (and `DECOY_LIBRARY=off`) is an explicit opt-out for records
  only. The job log cannot be opted out: it is always written to the resolved
  root, and the only time a run has no log is when that root is not writable,
  which warns (4.16, 4.17).
- **Q2 (owner): option (b), self-hosted lanes.** macOS runs on the Mac mini
  as a self-hosted GitHub Actions runner; Windows runs on a new self-hosted
  runner on a GCP VM, provisioned when the first slice that needs it starts
  (L1b). The slices that need these lanes now name them (section 5, "OS
  lanes").
- **Q1 (orchestrator): owner-only ACL on `scratch/` on Windows**, the only
  class that holds rows. Records, logs and the rest of `.decoy/` keep the
  inherited ACL in V1 (4.6). L1b grows by about 80 lines.
- **Q3 (orchestrator):** a failed library write on a successful run warns and
  keeps the exit code. `--require-library` is a later, additive flag (4.17).
- **Q4 (orchestrator): confirmed.** Logs: last 50 runs per pipeline or 30
  days. Sample scratch: 24 hours, replaced by the next sample. Records: kept
  forever unless pruned.
- **Q6 (orchestrator):** exports strip paths to file names unless
  `--keep-paths` is given (4.11, unchanged).
- **Q7 (orchestrator):** the user-level store comes after V1 (4.1,
  unchanged).
- **Progress-event hook:** `decoy run` does not use the engine's
  `ProgressSink` today. L5 now owns wiring it, and is split in two to stay
  under 800 lines: L5a wires the sink into `decoy run` and the progress
  display, L5b writes, rotates and shows job logs.

## 1. FRAME

### Problem

The CLI keeps no local state today. The S4 redesign (CLI plan
`2026-10-23-cli-redesign-s4-report-stateless.md`, commit 1ea8e22) deleted the
DuckDB `.decoy/` run catalog, so `decoy report` works only on files the user
names. Since then the owner has asked for several things that need a place to
live on the user's machine:

- scan records (the `scan-set/v1` payload from SCAN-MULTI S1a, stored by L2),
- the run result document (`decoy-run-result/v1`, RESULT row in the UX map
  section 5.4),
- the evidence manifest (`cli-local-1`, today only written to
  `--evidence-out`),
- sample run metadata (SAMPLE row; the sample rows themselves are data),
- publication records (DELIV) and the checkpoint index (F23),
- job logs (nothing stores these today; progress goes to stderr).

If each feature picks its own directory, file naming, write recipe and
retention rule, we get five stores with five sets of bugs, and the platform
importer has five formats to read. The owner asked for one modular design.

### What exists today (read from the code)

- `~/.decoy/` is the managed runtime home (`src/decoy/distribution/layout.py`:
  `versions/`, `current`, `cache/`). An upgrade swaps it. It holds no user
  records and must not start to.
- No CLI code writes a log file. `decoy run --verbose` prints a full traceback
  to stderr (`src/decoy/cli/run.py:1149`), which can carry exception text.
- Private write recipes exist in three places: the vault commit
  (`run.py:1630`, mkstemp 0600, fsync, `os.replace`, directory fsync), the
  token vault (`_token_vault.py:101-115`, 0700 directory only when it creates
  it, 0600 file before any write), and the engine's `fileaccess.write_private`
  (`decoy_engine/fileaccess/_private.py`, through the file-access policy).
  `run._fsync_directory` opens a directory with `os.open`, which fails on
  Windows.
- The install lock (`src/decoy/distribution/lock.py`) uses `fcntl` and is a
  no-op on Windows.
- The evidence manifest (`src/decoy/cli/evidence.py`) is value-free by design
  and has a canonical JSON hash (`sort_keys`, compact separators,
  `allow_nan=False`, `ensure_ascii=False`) that mirrors the platform's
  `api/evidence/hashing.py`. It stores source and target paths as written in
  the config.
- The engine version-tags every persisted artifact `name/vN` and freezes the
  shape under a tag (engine `docs/compatibility-contract.md` §3.1).
- The engine's progress events (`decoy_engine._progress_events`, exported as
  `ProgressSink` and `event_to_dict`) are value-free by construction: names
  are sanitized, codes must be registered, errors carry the class name only,
  and the event schema is versioned (`EVENT_SCHEMA_VERSION = 1`).
- CLI CI runs on Linux only (`.github/workflows/ci.yml`); the release-smoke
  workflow notes the OS matrix as later work. The Mac mini node exists for
  macOS. There is no Windows runner.

### The organizing idea: four retention classes under one project root

Everything Decoy keeps on the user's machine falls into exactly one class.
Each class has one directory, one write path, one retention rule and one
answer to "can this hold row data?".

| Class | What it holds | Can hold row data? | Default retention | Directory |
|---|---|---|---|---|
| 1. Records | small, durable, value-free metadata: scan snapshots, run results, evidence manifests, sample run metadata, publication records, the checkpoint index | never | keep all; explicit prune by count or age per kind | `.decoy/library/` |
| 2. Job logs | per run, time-ordered, value-free event streams (JSONL) | never | last 50 runs per pipeline and nothing older than 30 days, rotated automatically | `.decoy/logs/` |
| 3. Scratch | sample outputs (source and masked rows side by side), CLI staging, spill, any resume artifacts that live locally | yes, and this is the only Decoy area that ever does | deleted when its owner finishes, or by TTL (sample output 24 hours, replaced by the next sample of the same pipeline); `decoy library clean` | `.decoy/scratch/` |
| 4. Outside Decoy retention | vault files and keys (user-chosen paths), output targets and delivery roots (the user's) | yes | never touched by any Decoy prune or clean | wherever the user put them |

The split follows the established tools surveyed in section 2: dbt keeps
`run_results.json` (records) apart from `logs/dbt.log` (logs) and the rest of
`target/` (build output); MLflow keeps the tracking store (run metadata)
apart from the artifact store (files); git keeps objects and refs (durable)
apart from reflogs (expire after 90 days by default) and from the work tree;
Great Expectations keeps validation results in `uncommitted/` because they
can hold sensitive data.

Platform mapping, for later (no platform work in this plan):

| Class | CLI | Platform |
|---|---|---|
| Records | `.decoy/library/` | rows in the platform database, keyed by record id, imported from the export format (section 4.11) or written directly through the same engine record module |
| Job logs | `.decoy/logs/` | the platform's job-log store (today log text over SSE, `P:api/jobs/routes_streaming.py`), fed by the same event schema |
| Scratch | `.decoy/scratch/` | the platform's staging and preview areas, with their own GC |
| Outside | vault files, targets | the platform's vault and delivery targets; audit and server logs are platform-only classes with their own rules |

### Guarantee (what V1 promises)

1. One library per project, by default `.decoy/` next to the pipeline YAML
   (or the current directory when no YAML is involved; section 4.1 gives
   scan's rule). `--library DIR` and `DECOY_LIBRARY` override it. Every
   command that writes to it prints the root it used.
2. Every record is one immutable JSON file in one envelope
   (`decoy-record/v1`) with a kind, a per-kind payload tag, a content id, a
   creation time, producer versions, an invocation id and typed links to
   related records.
3. Records and job logs never contain a data value. This is enforced by the
   only writer (strict payload models on write, engine progress events) and
   proven by canary tests for every registered kind. Scratch is the only Decoy
   area that holds rows, including the scan integrity spill.
4. Files Decoy creates in the library are 0600 and directories it creates are
   0700 on Linux and macOS, at creation time. On Windows `scratch/` gets an
   owner-only ACL; records and logs inherit the parent directory's ACL
   (section 4.6 names the limit).
5. A record write is atomic on Linux, macOS and Windows: a reader sees the
   whole record or no record. A crash leaves at most a temp file that `fsck`
   removes.
6. On a local filesystem, two Decoy processes may write to one library at
   once. No record is lost, no ref update is lost silently, and prune never
   deletes a record that a ref or a kept record links to. A library on a
   detected network filesystem runs in degraded mode (4.8), where this does
   not hold for refs and prune, which refuse.
7. Records are kept until the user prunes them. Job logs and scratch follow
   their own defaults, configurable in one file (`.decoy/library.yaml`).
   Every `decoy run` writes a job log; only the records can be opted out.
8. `decoy library export` writes one self-verifying file
   (`decoy-library-export/v1`) that the platform can import idempotently.
9. A library written by this version stays readable by every later V1 CLI
   (compatibility contract §3.1 rules), and a record written by a later V1 CLI
   with additive optional payload fields stays readable by this one.

### Non-goals

- No user-level store in V1 (section 4.1 keeps the slot open).
- No search over payload contents beyond the index columns (kind, time,
  pipeline, tables, status, links).
- No signing. Record ids are unkeyed SHA-256, like `manifest_hash`: they detect
  accidental change, not a tamperer.
- No network or shared-drive guarantee. A library on a detected network
  filesystem (NFS, SMB, CIFS, AFP, WebDAV, or a Windows remote drive) works in
  degraded mode (section 4.8). A synced folder (OneDrive, Dropbox) is a local
  filesystem to the OS and cannot be detected reliably; the docs say it is
  supported for one writing machine at a time.
- No platform import code. The engine provides the reader; the importer is a
  platform row.
- No payload design for publication and checkpoint records: those kinds are
  reserved here and their payloads belong to the DELIV and F23 plans.
- No storage of audit or server logs. Those are platform classes.
- No change to how vault files, keys or targets are stored or retained.

### Failure modes

| Case | V1 behavior |
|---|---|
| Library root not writable (read-only container, CI checkout) | The command's own work still runs. A record or log write failure prints one warning naming the root and the error class, and `--json` output carries `library: {status: "failed", code}`. Exit code unchanged (4.17). `--no-library` skips records but not the log, so the warning still appears for the log; pointing `--library` or `DECOY_LIBRARY` at a writable directory clears it. |
| Crash or kill mid-write | Only a temp file under `library/tmp/` can remain. Readers never see it. `fsck` removes temp files older than one hour. |
| Two processes write records at once | Each writes its own uniquely named temp file and links it to its own content id with a no-clobber primitive. No conflict. The index takes each insert in its own SQLite transaction with a busy timeout. |
| Two processes move the same ref at once | Ref updates run under the library lock (an SQLite `BEGIN IMMEDIATE` on the index). The loser waits up to the busy timeout and then fails with `library_busy`; it never overwrites silently. |
| Prune while a run is writing | Prune holds the library lock, never deletes a record younger than the grace period (one hour, the git `gc.pruneExpire` idea), and never deletes a record reachable from a ref or from a kept record. |
| Windows: target file open by another process during `os.replace` | Records never replace an existing file (same id means same bytes, so an existing object is success). Ref and state files retry the replace with bounded backoff (10 tries, about 1 second in total), then fail with `library_busy`. |
| Record file whose parsed id does not match its name | Readers refuse it with `record_corrupt` and the id. The check parses the file, drops `id`, canonicalizes and hashes, so line-ending changes or reformatting by git or an editor are not corruption. `fsck` reports it and `fsck --repair` moves it to `library/quarantine/`; nothing is deleted. |
| Index missing, corrupt, or from another layout version | The index is a cache. An open failure rebuilds it under the lock; if the lock is unavailable, `list` reads a directory scan with a notice. |
| Index valid but missing records (crash between rename and insert, `git pull`, a hand-copied object) | Every open compares the index ids with the object file names (one listing, no reads) and inserts the missing ones and drops rows whose file is gone, under the lock. Without the lock the listing merges them in memory and says the index is stale. |
| Index cannot be locked, or a network filesystem is detected | Record writes still succeed (the object file is the truth). Ref updates, prune and clean refuse with `library_lock_unavailable`; `library path` reports degraded mode and why. |
| Windows: a file to delete is open in another program (a sample output open in Excel) | Automatic deletes (sample replace, TTL, rotation) skip that file, report it once, and leave the exit code alone; the next command retries. `prune --yes` and `clean --yes` list each file left behind and exit 4. |
| Windows: resolved root too long for `MAX_PATH` | The deepest record path is the root plus about 95 characters (`\.decoy\library\objects\ab\` plus 62 hex digits and `.json`). A root longer than 150 characters is refused with `library_path_too_long` before any write; the hint is `--library` with a shorter path. |
| Record written by a newer CLI (unknown payload major) | Listed as "needs a newer Decoy" with its kind and id. Never rewritten. Prune counts it by its envelope like any other record. |
| Unknown envelope major or library layout version | Read commands skip it with a notice; write commands refuse with `library_layout_newer` and the version found. |
| Payload fails its kind model (unknown field, wrong type) | The writer raises `record_invalid` naming the kind and the field name; the record is not written. This is a programming error, caught by tests. |
| Disk full | The temp write fails; no partial record; the warning names the error class. |
| Scratch holds sample rows and the user commits the project | `.decoy/.gitignore` (written once, section 4.9) ignores `scratch/`, `logs/` and the index; records stay committable. |
| User deletes `.decoy/` by hand | Nothing breaks; the next command starts a new library. A YAML `scan_baseline.path` pointing into it fails preflight with the existing missing-file error. |

## 2. Established solutions

Searches run on 2026-11-05 (web search, plus the CLI and engine code cited in
section 1). What each source contributes:

- **git object store and refs.** Content-addressed immutable objects under
  `objects/<2 hex>/<rest>`, mutable named refs as small files, refs updated by
  creating `<ref>.lock` exclusively and renaming it into place, and garbage
  collection that deletes only objects unreachable from refs and older than a
  grace period. Source: Junio Hamano on the lock-then-rename strategy
  (https://public-inbox.org/git/xmqqlgnii7mj.fsf@gitster.mtv.corp.google.com/)
  and the JGit `PackedBatchRefUpdate` notes on all-or-nothing ref batches.
  The library follows this for objects, refs, reachability and the prune grace
  period.
- **DVC cache and `.dvc` files.** A content-addressed cache at
  `.dvc/cache/files/md5/<2>/<30>` inside the project, with small pointer files
  next to the pipeline (https://doc.dvc.org/user-guide/project-structure/internal-files).
  Supports the project-local default and the two-level fan-out.
- **MLflow local tracking store.** `./mlruns` in the working directory with
  per-run folders and `meta.yaml`. MLflow now calls the file backend
  "Keep-the-Light-On" and recommends a database backend
  (https://mlflow.org/docs/3.5.0/self-hosting/architecture/backend-store),
  largely because listing and searching many runs as files is slow. The
  library keeps records as files (inspectable, committable, path-addressable)
  but adds a rebuildable SQLite index so listing does not parse every file.
- **dbt `target/` and `run_results.json`.** Every artifact carries a
  `metadata` block with `dbt_schema_version` (a schema URL), the dbt version
  and an `invocation_id` shared by all artifacts of one invocation; each
  artifact is versioned on its own (https://docs.getdbt.com/reference/artifacts/dbt-artifacts,
  https://schemas.getdbt.com/dbt/run-results/v5.json). dbt writes logs to
  `logs/dbt.log`, apart from artifacts. The envelope copies the metadata block
  idea (producer, versions, `invocation_id`) and the per-artifact version tag.
- **Great Expectations stores.** Validation results default to JSON under
  `gx/uncommitted/validations/`, and the docs warn that results can hold
  sensitive data and should stay out of source control
  (https://docs.greatexpectations.io/docs/guides/setup/configuring_metadata_stores/configure_result_stores).
  The library avoids that problem at the source: records hold no values, so
  they may be committed; only scratch, which may hold values, is ignored.
- **OpenLineage run events.** A run event carries `eventType` (START,
  COMPLETE, FAIL), a UUID `runId`, `producer` and `schemaURL`, and extensions
  go in named facets with `_producer` and `_schemaURL`
  (https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md,
  https://openlineage.io/docs/spec/facets/custom-facets). The envelope takes
  the producer field, the UUID invocation id and typed links; the job log
  reuses the engine's own event schema rather than OpenLineage, and an
  OpenLineage emitter can be a later exporter over the same records.
- **XDG base directories and platform conventions.** `platformdirs` maps the
  user data directory to `$XDG_DATA_HOME` (default `~/.local/share/<app>`) on
  Linux, `~/Library/Application Support/<app>` on macOS and
  `%LOCALAPPDATA%\<author>\<app>` on Windows
  (https://platformdirs.readthedocs.io/en/stable/platforms.html). This is the
  location reserved for a later user-level store (section 4.1). It also says
  where records must not go: `~/.decoy/` is the runtime, which XDG would call
  program data, not user data.
- **SQLite as an application file format vs JSON files.** SQLite's essay
  (https://sqlite.org/appfileformat.html) argues for one atomic, queryable,
  cross-platform file. SQLite also documents that WAL mode does not work over
  a network filesystem and that network locking is unreliable
  (https://sqlite.org/useovernet.html). The design uses SQLite for the index
  only, in the default rollback-journal mode, and keeps the records as files
  so that a broken index never loses a record and a git diff of a record is
  readable. The CLI already ships SQLite for the token vault.
- **Atomic writes per OS.** POSIX `rename(2)` replaces atomically within one
  filesystem; the durable sequence is write, fsync the file, rename, fsync the
  directory (already used at `run.py:1630`). On Windows `os.replace` calls
  `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`, which is atomic in practice
  on one volume but not documented as atomic, and fails with `PermissionError`
  when another process holds the target open without share-delete access
  (CPython issue 27886 discussion,
  https://mail.python.org/archives/list/docs@python.org/thread/FDG54XVBNYLS5OPPA3QCBRATXDQD2QR6/;
  the PostgreSQL "Atomic pgrename on Windows" thread). The `atomicwrites`
  package is deprecated in favor of `os.replace`
  (https://github.com/untitaker/python-atomicwrites). The design avoids
  replacing records at all (content-addressed names), retries ref replaces,
  and skips the directory fsync on Windows, where a directory cannot be opened
  with `os.open`.
- **File permission models.** On POSIX, mode 0600 at creation through
  `tempfile.mkstemp` (which uses `O_EXCL` and mode 0600). On Windows,
  `os.chmod` sets only the read-only flag; real access control is the ACL,
  set with `icacls` or `SetNamedSecurityInfo`
  (https://pypi.org/project/oschmod/0.1.2/ and the CPython `os.chmod`
  documentation). The CLI's mask-secret check already skips the mode check on
  Windows (`src/decoy/_mask_secret.py:148`).
- **Canonical JSON.** RFC 8785 (JCS) is the standard. Decoy already has a
  canonical form shared by the CLI manifest and the platform evidence hash
  (`evidence.compute_manifest_hash`). The record id uses that same form so the
  platform can recompute ids with code it already has; the envelope forbids
  floats in its own fields, which removes the main JCS difference (number
  formatting), and payload floats must be finite.

What remains custom: the envelope fields, the kind registry and the retention
policy file. Each is small and has no maintained library that fits (the
candidates are whole tracking servers). No custom crypto, lock manager or
database.

## 3. Design notes

- **New structure.** One engine module (`decoy_engine.records`) and one CLI
  package (`decoy/cli/_library/`) with a `library` command group. A new
  variant is a new record kind, and kinds keep arriving (the owner's
  "any other job logs or records"), so open/closed applies: a kind is one
  registry entry (tag, payload model, readers, canary fixture), never an edit
  to store code.
- **Library code does not know its callers** (engine `CLAUDE.md`): the engine
  module holds types, canonical bytes, ids, payload models and the export
  codec, and touches no filesystem. The CLI owns paths, locks, the index,
  retention and commands. The platform reuses the engine module and stores
  rows its own way.
- **One place per fact.**
  - The list of kinds lives in the engine registry. CLI `list --kind`
    choices, the canary guard and the export reader all derive from it.
  - The canonical JSON form lives in `decoy_engine.records._canonical`;
    `evidence.compute_manifest_hash` is rewired to call it (byte-identical,
    pinned by a test).
  - The retention defaults live in one pydantic model in
    `decoy/cli/_library/_policy.py`; docs render from it.
  - The `.decoy` directory name and its subdirectory names live in
    `decoy/cli/_library/_paths.py` only.
  - The "no PII found means `redact`" rule lives in the starter YAML renderer
    (SCAN-MULTI S3); the scan record stores the detector result, not the
    policy.
- **Choke points, guards and mutations.**
  - *Record writes.* `Library.put(envelope)` is the only function that writes
    under `.decoy/library/objects/`, and the only way to get an envelope is
    `records.build(kind, payload, ...)`, which validates the payload against
    the registered strict write model (`extra="forbid"`, typed fields). Reads
    go through `records.decode`, which validates against the kind's tolerant
    read model. Guard G-LIB-WRITER walks the CLI package syntax tree: no module
    outside `decoy/cli/_library/` imports `_library._fs`, calls
    `records.encode` (the bytes producer), or holds a non-docstring string
    literal with `.decoy` as a path component (split on `/` and `\`). The
    ratchet allowlist starts with one entry, the managed runtime home in
    `distribution/layout.py:31`; `.decoy-ci.yaml` and `.decoy-debug-` do not
    match the component rule. Proven on a seeded bypass. Mutation
    M-LIB-INLINE: `scan.py` writes `Path(".decoy/library/x.json")` directly;
    the guard goes red.
  - *Value-free records.* Guard G-KIND-CANARY derives the kind list from
    `records.registered_kinds()` and fails when a writable kind has no canary
    end-to-end fixture. Each fixture puts a canary string in every cell, runs
    the real producer command, and asserts the canary appears in no file under
    `.decoy/library/` or `.decoy/logs/`. A positive control runs
    `decoy run --sample` on the same fixture and asserts the canary does
    appear under `.decoy/scratch/`, which proves the search can see data.
    Mutations: M-KIND-NOFIX (register a kind without a fixture; guard red);
    M-PAYLOAD-LEAK (add a `top_values` field to the scan payload model and
    fill it; canary test red).
  - *Value-free logs.* The log writer accepts only engine `ProgressEvent`
    objects and serializes them with `event_to_dict`; it has no free-text
    parameter. The canary fixture includes a failure whose exception message
    quotes a cell. Mutation M-LOG-MSG: the writer adds `str(exc)` to the
    terminal line; canary test red.
  - *Scratch is the only data area.* Allocation goes through
    `Library.scratch(owner, ttl)`; the sample runner and any staging take
    their directory from it. G-LIB-WRITER covers it (same `_fs` rule).
  - *Private modes.* All creation goes through `_fs.create_private_file` and
    `_fs.ensure_private_dir`. Test B1-mode walks every file and directory the
    library created after a full producer run and asserts 0600 and 0700 on
    POSIX. Mutation M-MODE: create the temp file with `open(..., "w")`; red.
- **No registry for one site.** Library root resolution is one function,
  `_paths.resolve_root(command, *, flag, yaml_path, emit_path, config_path)`;
  `run` and `scan` call it with their own inputs (4.1).
- **House style.** Typed context objects (`LibraryRoot`, `RecordEnvelope`,
  `RetentionPolicy`), no flag arguments that switch behavior (separate
  `prune_preview` and `prune_apply`), comments that explain why.

### 3.1 Central registries and sizing

Owner standing rule (2026-11-05): for each component, ask whether it repeats
something the CLI or engine already does differently, and whether one choke
point would make a later change one edit. Searched CLI 8fba6af and engine
41a86f47 (`grep` for `os.replace`, `mkstemp`, `fsync`, `0o600`, `0o700`,
`sort_keys=True`, `mkdtemp`, `chmod`, retention and reason-code helpers, then
read each hit in context).

| Concern | Existing copies found | Decision | Choke point, guard, mutation |
|---|---|---|---|
| Atomic file write (temp in the target directory, fsync, replace, directory fsync, temp removed on failure) | CLI `cli/ci.py:111-115`, `ci/debug.py:44-48`, `run.py:1622-1686` (`_fsync_directory`, vault commit), `distribution/installer.py:219,659-664`, `distribution/layout.py:144-157`, `distribution/first_install.py:71`; engine `fileaccess._output` and `write_private` | One CLI module, `src/decoy/_atomic.py` (L1b, ~150 lines): `write_atomic(dir, name, data, mode)` with `CREATE_ONCE` and `REPLACE`, the Windows retry and the POSIX directory fsync. The library's `_fs` calls it. L5a moves `run.py`'s vault commit onto it (which also shrinks `run.py`); SCAN-MULTI S1c writes `--output` and S3a writes the YAML through it. `ci.py` and `ci/debug.py` start on the allowlist and move when next touched. The distribution files stay allowlisted on purpose: they flip symlinks and swap whole runtime directories under the install lock, a different operation. The engine writers stay engine-side (file-access policy, `openat2`); the library is CLI-owned and must run on Windows (4.9). | Guard G-ONE-ATOMIC-WRITER (`tests/sentry/test_atomic_writer.py`): syntax-tree walk of `src/decoy/` for `os.replace`, `os.rename`, `os.link` and `tempfile.mkstemp` outside `_atomic.py`; ratchet allowlist with a reason per entry, recorded size 7 at L1b (`cli/ci.py`, `ci/debug.py`, `run.py`, the `api.py:252` staging temp file, `distribution/installer.py`, `distribution/layout.py`, `distribution/first_install.py`), 6 after L5a. Mutation M-ATOMIC-INLINE: `_library/_fs.py` calls `os.replace` itself; red. |
| Canonical JSON and content hashing | CLI `evidence.compute_manifest_hash` (`evidence.py:104-121`); `distribution/signing.py:23,48` (same form, release signatures); `notify.py:240` (webhook HMAC body, no `ensure_ascii=False`); `distribution/installer.py:192` | One form, `decoy_engine.records._canonical` (L1a). `evidence.compute_manifest_hash` calls it (byte-identical, test A1-canonical-shared). `signing.py` stays: it is the frozen release-signature input, and rewiring it would couple release verification to an engine version. `notify.py` stays: different bytes on the wire by design. | Guard G-ONE-CANONICAL (`tests/sentry/test_canonical_json.py`): walk for `json.dumps(..., sort_keys=True, separators=(",", ":"))` outside the engine call site; allowlist `signing.py`, `notify.py`, `installer.py`, size 3. Mutation M-CANON-COPY: `_library/_store.py` hashes its own `json.dumps`; red. |
| Private directories and files | CLI `_token_vault.py:100-115` (0700 only when it creates the parent, 0600 pre-create before SQLite opens); engine `out_of_core/_scratch.py` (`private_dir`, `engine_scratch_root`) | `_fs.ensure_private_dir` and `_fs.create_private_file` follow the token-vault recipe; the index pre-create (LL3) uses the same call. The token vault moves onto `_fs` helpers in a later slice; not in this plan (it is not library code and is gated separately). The scan spill reuses the engine helper when the library is off (SCAN-MULTI S1b). | B1-mode walks every created file and directory (M-MODE). |
| Windows ACL | none in the CLI or engine | new `_winacl.py` (L1d), the only `ctypes` ACL code | B1-win-scratch-acl (MB1-inherit) |
| Locks | CLI `distribution/lock.py` (`fcntl`, no-op on Windows) | not reused: it locks the runtime home and does nothing on Windows. The library lock is SQLite `BEGIN IMMEDIATE` (4.8). | C1-lock-unavailable (MC1-unlocked-ref) |
| Error codes and messages | engine reason registry; CLI ad hoc `type(exc).__name__` messages (19 sites) | Library and log codes are engine reason identities (L1a, LM8). One CLI builder, `_library/_errors.py` `library_error(code, exc)`, formats "code plus class name, no path" for every library failure. | B1-no-path-in-error (MB1-exc); the engine's registered-code check turns any unregistered code into `unregistered_reason`, which L5-value-free asserts never appears |
| Retention | none in the CLI; the platform has its own (F26) | one policy model, `_policy.py` | single site, no registry |
| Kinds, payload models, path fields, diff dispatch, canary fixtures | none | one registry entry per kind in the engine (`records/_registry.py`); CLI `list --kind`, diff dispatch, export path stripping and G-KIND-CANARY all derive from it | G-KIND-CANARY (M-KIND-NOFIX), A1-registry-walk (MA1-hidden) |

Oversize files at 8fba6af that slices here touch: `src/decoy/cli/run.py`
(1812 lines), `scan.py` (1442), `report.py` (2382). A slice that edits one keeps
its net line change at or below zero by moving code into a new module, and the
gate checks `git diff --stat` for it. The per-slice layout with sizes is in
each slice below.

## 4. Decisions

Each decision states the recommendation first, then the alternatives weighed.

### 4.1 Where the library lives

**Recommendation: project-local only in V1.** The root is resolved in this
order: `--library DIR`, then `DECOY_LIBRARY` (the value `off` turns records
off for the process), then `<directory of the pipeline YAML>/.decoy/`,
then `<current directory>/.decoy/`.

- For `decoy scan`, "the pipeline YAML" is the `--emit-config` target when
  given, else the `--config` file, else none (current directory). So
  `decoy scan data/*.csv --emit-config out/p.yaml` saves into `out/.decoy/`,
  the same library `decoy run out/p.yaml` uses.
- Under `DECOY_LIBRARY=off` nothing is written under `library/`, but the job
  log is still written: its root is the same chain with the env step skipped
  (`--library`, else the YAML directory, else the current directory). The run
  card names that log path.

Records describe a pipeline and its data,
so they belong next to the pipeline, as `.git/`, `.dvc/`, `./mlruns` and
dbt's `target/` do. A production pipeline in a container points
`DECOY_LIBRARY` at a mounted volume.

Alternatives:

- *User-level only* (`platformdirs.user_data_dir("decoy")`). One place per
  user, but records from different projects mix, CI checkouts lose them, and a
  YAML cannot reference a baseline by a relative path. Rejected for V1.
- *Both, with a merged view.* Useful for ad hoc scans outside any project, but
  doubles the resolution and prune rules. Deferred: the resolution chain above
  can add a final user-level step later without changing any record format.
- *`~/.decoy/`.* Rejected: it is the managed runtime, swapped on upgrade.

### 4.2 Layout on disk

```
.decoy/
  .gitignore              written once if absent (section 4.9)
  .gitattributes          written once if absent: `library/objects/** -text`
  library.yaml            optional retention policy (section 4.7); absent = defaults
  library/
    LAYOUT                {"layout": 1}
    objects/ab/cdef...json  one immutable record per file, named by its id
    refs/<kind>/<name>    one line: a record id
    index.sqlite          rebuildable cache
    tmp/                  temp files for atomic writes (same volume)
    quarantine/           records fsck found corrupt
  logs/
    <invocation_id>.jsonl one job log per run
  scratch/
    <owner>-<invocation_id>/  sample output, staging; the only rows Decoy keeps
```

`library/` is a subdirectory, not `.decoy/` itself, so old developer boxes
that still have the inert S4-era `.decoy/` catalog files are not misread.

Windows path budget: the deepest record path is the root plus about 95
characters, so a root longer than 150 characters is refused with
`library_path_too_long` before any write. Scratch outputs add the table file
name to `scratch\sample-<uuid>\`; a name that would pass 259 characters is
refused with the same code.

### 4.3 One envelope, per-kind payloads

**Recommendation.** Every record is:

```json
{
  "record_schema": "decoy-record/v1",
  "kind": "scan-set",
  "payload_schema": "scan-set/v1",
  "id": "sha256:<64 hex>",
  "created_at": "2026-11-05T21:14:03.123456Z",
  "invocation_id": "<uuid4>",
  "producer": {"name": "decoy-cli", "version": "0.x.y", "engine_version": "0.x.y"},
  "labels": {"pipeline": "pipelines/claims.yaml", "tables": ["claims", "members"], "status": "ok"},
  "links": [{"rel": "baseline", "id": "sha256:..."}],
  "payload_digest": "sha256:<64 hex>",
  "payload": {}
}
```

- `id` is the SHA-256 of the canonical bytes of the envelope without `id`,
  and this is the only id rule: `decode`, `put`'s check of an existing file
  and `fsck` all parse the file, drop `id`, canonicalize and hash. Raw bytes
  are never hashed, so a CRLF checkout or a reformat does not quarantine a
  valid record. Because `created_at` and `invocation_id` are inside, a rescan
  of unchanged data gets a new record.
- `created_at` is UTC with microseconds. "Newest" means the largest
  `(created_at, id)` pair, which every machine and every index rebuild
  computes the same way. Records committed from machines with skewed clocks
  sort by their recorded times; that limit is in the docs, and `diff A B`
  with explicit ids is the exact form.
- `payload_digest` is the SHA-256 of the canonical payload alone, so "same
  content as last time" is one comparison (`diff` and `list --dedupe` use it).
- `invocation_id` ties together every record and the log of one command run,
  like dbt's `invocation_id` and OpenLineage's `runId`.
- `labels` are the indexed fields. Their keys are a closed set defined by the
  envelope model (`pipeline`, `tables`, `status`, `route`, `exit_code`), so
  no free text gets in through them. `pipeline` is the YAML path relative to
  the project root.
- `links` are typed (`rel` from a closed set: `baseline`, `scan`, `evidence`,
  `result`, `sample`, `log`, `publication`, `checkpoint`, `supersedes`). A
  `log` link also carries the log file's SHA-256 (section 4.12).

Kinds registered in V1:

| Kind | Payload tag | Owner of the payload shape | Writable in |
|---|---|---|---|
| `scan-set` | `scan-set/v1` (`ScanSetCore`, the `detail=False` dump) | engine, SCAN-MULTI S1a | L2 |
| `evidence` | `cli-local-1` (the existing manifest, unchanged) | engine model in `records/_kinds.py`, mirroring CLI `evidence.py` (LM7) | L3a |
| `run-result` | `decoy-run-result/v1` | RESULT row (UX map 5.4) | L3a, once RESULT defines it |
| `sample-run` | `sample-run/v1` (new, section 4.13) | this plan | L3b |
| `publication` | reserved | DELIV plan | not in this plan |
| `checkpoint` | reserved (`checkpoint-index/v1`) | F23 plan | not in this plan |

Each kind entry carries: the payload tag, a write model (`extra="forbid"`), a
read model (the same fields with `extra="ignore"`, nested models included, so
an older CLI reads a record a newer one wrote with an added optional field),
its path fields as JSON-pointer patterns (for example
`/payload/tables/*/descriptor/path` for `scan-set`,
`/payload/sources/*/path` and `/payload/targets/*/path` for `evidence`), its
diff rule and its canary fixture id. The major check stays on read: an unknown
payload major gives `RecordNeedsNewer`.

A reserved kind is registered with no payload model; `records.build` refuses
it with `record_kind_reserved` until its plan adds the model. `scan-set` is
reserved in L1a when SCAN-MULTI S1a has not merged yet, and S1a's merge points
it at `ScanSetCore`. This keeps the
kind names and link types stable now. For F23, the authoritative checkpoint
activation record stays with the staged artifacts in the run's delivery root
(UX map 6.1); the library holds only a value-free index entry pointing at it.
F23 may reuse the engine envelope and the CLI atomic writer for the
activation record itself.

Alternatives: *a bare payload file per feature* (the earlier S1d design) gives
no common listing, linking or import; *one big JSON per run holding all
kinds* couples kinds that have different lifetimes and owners.

### 4.4 Index

**Recommendation: object files are the truth; `index.sqlite` is a rebuildable
cache.** One table `records(id, kind, payload_schema, created_at,
invocation_id, pipeline, status, payload_digest, size)`, one `links(src, rel,
dst)` table, one `tables(id, table_name)` table, `PRAGMA user_version` for the
index schema. Rollback-journal mode (SQLite's default), `busy_timeout` 5
seconds. A version mismatch or any corruption means rebuild, never migrate.
The file is pre-created 0600 with `os.open(path, O_RDWR | O_CREAT, 0o600)`
before `sqlite3.connect`, the `_token_vault.py:108-115` recipe; SQLite gives
its journal the database file's mode.

Freshness: on every open the library lists object file names (one
`os.scandir` per fan-out directory, no file reads) and compares the id set with
the index. Missing ids are parsed and inserted, rows whose file is gone are
dropped, all in one transaction under the lock. This covers a crash between
the object link and the index insert, a `git pull` that adds records, and a
first open on a fresh clone. Listing names is cheap next to parsing files (the
cost MLflow's file store pays); C1-list-speed includes it. Without the lock
(degraded mode) the same comparison is done in memory for that command.

Alternatives:

- *Directory scan only.* Simplest and always correct, but `list` parses every
  file; with keep-all and a record per CI run, thousands of files make `list`
  slow (the MLflow file-store lesson). Kept as the fallback when the index is
  stale or cannot open.
- *Append-only JSONL index.* Cheap appends on POSIX, but concurrent appends
  are not guaranteed whole on Windows, deletes need rewrites, and torn lines
  need repair. SQLite handles all three.
- *Records inside SQLite.* One file and real transactions, but records stop
  being diffable, committable or addressable by path (the YAML's
  `scan_baseline.path`), and a corrupt database loses everything.

### 4.5 Content-addressed records and named refs

**Recommendation.** Records are immutable and content-addressed (git objects).
Refs are mutable names that point to one record id:

- `latest` is virtual: computed from the index (the largest
  `(created_at, id)` of a kind, optionally filtered by pipeline or table set).
  No stored file, so two runs never contend over it.
- Stored refs live at `refs/<kind>/<name>` (names `[a-z0-9][a-z0-9._-]{0,63}`,
  a `/` allowed once for a pipeline scope). V1 writers: `decoy scan
  --emit-config` (SCAN-MULTI S3a-cli, which states the slug rule) sets
  `scan-set/baseline/<slug>` under the library lock; users set others with
  `decoy library ref`.
- Refs are the garbage-collection roots: prune keeps every record reachable
  from a ref through `links`.
- Ids may be abbreviated to any unique prefix of 8 or more hex digits, as git
  allows.

Alternatives: *time-named files* (the earlier S1d design's `<time>-<hash>.json`) sort nicely but
make two ids for one record (name and hash); *mutable records* lose the audit
property that evidence depends on.

### 4.6 Value-free by construction, and private files

**Recommendation.**

- Records: section 3 choke point. Payload models type every field. Free-text
  fields are not allowed; strings are identifiers (table, column, kind,
  registered reason codes), relative paths, versions, hashes of whole files,
  or enum values. No hash of a single value or of a column's values is ever
  stored, because a hash of low-entropy text can be reversed by guessing
  (`observability-and-resilience.md`).
- Logs: engine `ProgressEvent` only (section 4.12).
- Paths: records carry paths relative to the project directory (the library
  root's parent), absolute only when no relative path exists (another
  Windows drive, a cloud URI). Scan's positional paths are absolute in memory
  (SCAN-MULTI S1c), so L2 relativizes the kind's declared path fields before
  `build`; L3a does the same for evidence. Paths are not data values, but they
  can name users and hosts, so export strips them to file names by default
  (4.11).
- Modes on Linux and macOS: temp files come from `tempfile.mkstemp` (0600,
  `O_EXCL`) in `library/tmp/`; directories the library creates get 0700 at
  creation, and an existing parent is never re-permissioned (the token-vault
  rule). `fsck` reports a group- or world-readable file in scratch, logs, the
  index or `tmp/` as a finding. Records and refs are checked out by git as
  0644, so for them it is an advisory note that does not change the exit code;
  they hold no values.
- Windows: `os.chmod` cannot express 0600. `scratch/`, the only class that
  can hold rows, and every allocation directory under it are created with a
  protected DACL already attached: SDDL
  `D:P(A;OICI;FA;;;<current user SID>)(A;OICI;FA;;;SY)`, converted with
  `ConvertStringSecurityDescriptorToSecurityDescriptorW` and passed in the
  `SECURITY_ATTRIBUTES` of `CreateDirectoryW` through `ctypes` (no new
  dependency). There is no window in which the directory exists without it,
  and inheritance from the parent is off. If the ACL cannot be applied, scratch allocation fails
  with `scratch_acl_failed` and the sample run stops before it writes a row
  (fail closed, the token-vault rule). Records and logs hold no values, so in
  V1 they keep the ACL inherited from the project directory, which on a
  normal user profile grants the user, SYSTEM and Administrators; the docs
  say so (decided in Revision 2, Q1).

### 4.7 Retention and prune

**Recommendation.** One optional policy file, `.decoy/library.yaml`, read by
a strict pydantic model; absent means these defaults:

```yaml
retention:
  records:
    default: {keep: all}
    # per kind override, for example: run-result: {keep_last: 500}
  logs: {keep_last_runs_per_pipeline: 50, max_age_days: 30}
  scratch: {sample_ttl_hours: 24, staging: delete_on_exit}
```

YAML, not TOML: the CLI supports Python 3.10, which has no `tomllib`, and it
already parses YAML.

- Records: V1 keeps all. Prune is explicit only: `decoy library prune --kind
  K --keep-last N` or `--older-than 90d`. It shows the plan by default and
  deletes only with `--yes` (destructive-operations rule: resolve the exact
  target read-only first). It never deletes a record that is reachable from a
  ref or from a record that is kept, or younger than one hour. A policy with
  `keep_last` makes `prune` with no arguments apply the policy; it still
  previews without `--yes`.
- Logs: rotated automatically at the end of any command that wrote a log
  (git's `gc --auto` idea). A log linked from a record that a ref keeps is
  never rotated. Logs are derived and value-free, so automatic rotation is
  safe.
- Deletes are best effort per file. On Windows a file another program holds
  open cannot be deleted (`PermissionError`). Automatic deletes (sample
  replace, TTL expiry, log rotation) skip such a file, report it once on
  stderr and in `--json`, keep the triggering command's exit code, and retry
  on the next command. Explicit `prune --yes` and `clean --yes` list each file
  left behind and exit 4; the index row for a record goes only after its file
  is gone.
- Scratch: staging is deleted when its owner finishes, success or failure.
  Sample output stays after the command so the user can look at it, is
  replaced by the next sample of the same pipeline, and anything older than
  the TTL is removed lazily by the next Decoy command in the project.
  `decoy library clean` removes all scratch now (preview, then `--yes`).
  Deleting scratch removes data, which is the safe direction.
- Nothing in any class ever touches vault files, keys, targets or delivery
  roots.

Alternatives: *keep-last-N records by default* saves disk but deletes
evidence and baselines without the user asking (rejected for V1, matching
SCAN-MULTI Q10); *retention in the pipeline YAML* mixes per-machine policy
into a file the platform compiles (rejected: the platform has its own
retention, F26).

### 4.8 Concurrency

**Recommendation.**

- Record writes need no lock: unique temp name, then a no-clobber link to the
  content-addressed name (4.9). If the final name exists, the record exists;
  the writer checks the existing file with the id rule (4.3) and reports
  `record_corrupt` if it differs.
- The index takes one short transaction per insert.
- One library lock for ref updates, prune, clean and index rebuild:
  `BEGIN IMMEDIATE` on `index.sqlite`. SQLite locking works the same on
  Linux, macOS and Windows, so the library does not need `fcntl` (which is
  absent on Windows, `distribution/lock.py`) or a hand-written lock file with
  stale-lock rules.
- When the index cannot be locked, record writes continue and the index is
  caught up on the next locked open (4.4); ref updates, prune and clean refuse
  with `library_lock_unavailable`.
- Network filesystems are detected when the library opens, because on SMB,
  NFS and similar mounts a lock can appear to succeed without excluding other
  writers (sqlite.org/useovernet). Windows: `GetDriveTypeW` on the root's
  volume returns `DRIVE_REMOTE`, or the path is UNC. Linux: `statfs` `f_type`
  is NFS, SMB, SMB2, CIFS, AFS, 9P or FUSE. macOS: `statfs` `f_fstypename` is
  `nfs`, `smbfs`, `afpfs` or `webdav`. A detected remote root goes to degraded
  mode up front (same rules as an unlockable index) and `library path` says
  why. Detection runs once per command.

Alternative: git-style `<ref>.lock` files created with `O_EXCL`. Portable,
but a crashed holder leaves a lock that needs age or pid rules, and
`O_EXCL` on network filesystems has its own history. Kept as the documented
fallback if SQLite locking proves unreliable on a supported platform.

### 4.9 Atomic private writes on all three OSes

One function, `_fs.write_atomic(dir, name, data, mode)`, where `mode` is a
two-value enum (`CREATE_ONCE` for records, `REPLACE` for refs and state):

1. `mkstemp(dir=library/tmp)`, so the temp file is 0600 and on the same
   volume as the target.
2. Write all bytes, `os.fsync`.
3. For `CREATE_ONCE`, a no-clobber move: `os.link(tmp, target)` then unlink
   the temp file on POSIX, `os.rename(tmp, target)` on Windows (which fails if
   the target exists). "Already exists" means verify with the id rule and
   return success. Where hard links are unsupported (`EPERM`, `ENOTSUP`, some
   FUSE and exFAT mounts), fall back to `os.replace`: the only race left is a
   valid record overwriting a byte-different file with the same id, which the
   verify step reports. For `REPLACE`, `os.replace(tmp, target)`. On Windows,
   retry a `PermissionError` with bounded backoff (10 tries, doubling from
   10 ms, about 1 second).
4. On POSIX, fsync the target directory. On Windows, skip it (a directory
   cannot be opened with `os.open`; NTFS journals the rename).
5. Any failure unlinks the temp file and raises one coded error without the
   path in `str(exc)` (the engine `write_private` rule).

This function lives in `src/decoy/_atomic.py` (section 3.1), not inside
`_library/`, so the vault commit and the emitted YAML share it.

The engine's `fileaccess.write_private` is not reused: it runs through the
engine's file-access policy and its POSIX descriptor machinery
(`_openat2.py`, `_rooted.py`), meant for engine copies of real data, and the
library is CLI-owned and must run on Windows. The recipe is the same and the
code cites it.

`.decoy/.gitignore` is written once, only if absent, with `scratch/`,
`logs/`, `library/index.sqlite`, `library/tmp/`, `library/quarantine/`.
`.decoy/.gitattributes` is written once, only if absent, with
`library/objects/** -text`, so git never converts line endings in records.

### 4.10 Corruption handling and fsck

`decoy library fsck` (read-only) checks: every object's id, computed by the
4.3 rule, matches its name; every envelope parses and its payload validates
for its tag (read model); every ref
points to an existing record; every link target exists (dangling links are
warnings, since prune may remove an unprotected target); the index matches
the objects; no temp file is older than one hour; POSIX modes are private for
scratch, logs, the index and `tmp/` (records and refs get an advisory note,
4.6); job log lines parse (a partial last line is a warning). Exit 0 clean, 4 on
findings (the CLI's findings code). `fsck --repair` moves corrupt objects to
`quarantine/`, deletes stale temp files, removes refs to missing records
(printing each) and rebuilds the index. It never deletes a valid record.

### 4.11 Schema versioning, migration and export

- The envelope is `decoy-record/v1`; payload tags follow the engine
  compatibility contract §3.1: never change the shape under a tag, add
  optional fields freely, mint `v2` with a kept `v1` reader. Records are
  never migrated in place (they are immutable and their ids would change).
  Readers upgrade on read.
- The index is a cache, so its schema changes by rebuild.
- `LAYOUT` guards the directory layout. A newer layout refuses writes.
- Export: `decoy library export --out FILE` writes `decoy-library-export/v1`
  as JSON Lines: a header line (`export_schema`, `exported_at`, producer,
  record count, refs), then one envelope per line in canonical form. Every
  line is self-verifying (the importer recomputes `id`). Options: `--kind`,
  `--since`, `--ref` (a ref and everything reachable from it),
  `--include-logs` (logs appended as `log` lines with their hash),
  `--keep-paths`. Without `--keep-paths`, only the kind's declared path fields
  (4.3) are reduced to file names. Because that changes the bytes, each such
  line gets a new id and carries the original id as `source_id`, and the
  header says `paths_stripped: true`. Links inside the export are remapped to
  the new ids: lines are written in link order (a record only links to ids
  that existed before it, so the order always exists), each line's `links`
  are rewritten from the old-to-new map before its own id is computed, and
  the header's refs are remapped the same way. A link to a record outside the
  export keeps its original id. Scratch is never exportable.
- The engine owns the codec (`records.export_lines`, `records.read_export`),
  so the platform importer upserts by id with the same code.

Alternative: a zip or tar of `objects/`. Easy to produce, but harder to
stream, filter and verify line by line, and a tar from Windows carries
platform quirks.

### 4.12 Job logs

**Recommendation.** A job log is `.decoy/logs/<invocation_id>.jsonl`:

- Line 1 is a header: `{"log_schema": "decoy-job-log/v1",
  "event_schema": <engine EVENT_SCHEMA_VERSION>, "invocation_id", "command",
  "pipeline", "started_at", "producer"}`. `command` is a closed enum (`run`,
  `scan`), never `argv`.
- Every other line is `event_to_dict(event)` for an engine `ProgressEvent`
  (phase, rate, route, warning, retry, checkpoint, publication, terminal),
  plus CLI-side events built from the same classes (validate step finished,
  library write failed). The engine already sanitizes names, admits only
  registered codes and keeps only exception class names, so the log is
  value-free by construction. Because an unregistered code becomes
  `unregistered_reason` (`_progress_events.py:101-105`), every CLI-side code
  is an engine reason identity registered in L1a.
- Lines are appended and flushed as events arrive; the file is fsynced and
  closed at the end. A crash leaves a truncated last line, which readers skip
  and `fsck` reports as a warning. The log is never renamed into place, so a
  reader can follow a running job.
- A log is found by its `invocation_id` (the file name), so `decoy library
  show <record> --log` works for any record of that invocation without a
  link. Once L3a lands, the run-result record also links to the log
  (`rel: log`) with its SHA-256, so `show` can detect edits.
- Verbose and debug output (tracebacks, `--verbose`) goes to stderr only and
  is never persisted. A future `--log-level debug` adds more events of the
  same classes to the file (rate samples, per-phase timings), still value
  free; it never adds message text.
- Which commands write a log in V1: `decoy run` (including `--sample`) and
  multi-table `decoy scan`. Short read-only commands do not.

Alternatives: *logs as records* (one record per log) would make logs
immutable content-addressed objects, but a log is written while the job runs
and has a shorter life, so it would fight the record class rules; *plain text
logs* cannot be value-free by construction.

### 4.13 Sample output and the library

Sample rows are scratch, never a record. `decoy run --sample N` writes its
output tables to `.decoy/scratch/sample-<invocation_id>/` and then writes one
`sample-run/v1` record holding only metadata: N, the root table, per-table
row counts, the subset seed summary (counts, never key values), the columns
labelled approximate (shuffle, categorical, UX map Q16), the scratch
directory relative to the project root, a SHA-256 per output file, the TTL,
and links to the scan baseline and the log. `library show` on that record says
whether the scratch output still exists and whether its hashes still match.
Pruning the record does not touch scratch; cleaning scratch leaves the record
(which then reports the output as expired). The throwaway vault the sample
uses for tokenize columns (UX map 3.1) lives in the same scratch directory.

### 4.14 What goes in the engine and what in the CLI

| Piece | Repo | Why |
|---|---|---|
| `RecordEnvelope`, `records.build`, canonical bytes, `record_id`, `payload_digest` | engine `decoy_engine/records/` | the platform must compute the same ids |
| Kind registry, payload models (write and read) for every kind (`scan-set/v1` from SCAN-MULTI S1a, `cli-local-1`, `decoy-run-result/v1`, `sample-run/v1`) and the reserved kinds | engine | the platform stores and reads the same payloads |
| Export codec (`export_lines`, `read_export`) | engine | the platform importer reads it |
| Job log header model and line reader | engine | the platform job-log store can ingest the same lines |
| `cli-local-1` evidence payload model | engine `records/_kinds.py` (Revision 5, LM7); the CLI still builds the manifest, and a CLI test validates `build_manifest` output against the engine model | the platform importer must decode evidence records, and registration must not depend on CLI import order |
| Paths, atomic writes, index, locks, refs, fsck, retention, scratch, commands | CLI `decoy/cli/_library/` | local filesystem policy, not reusable by the platform |

The engine module touches no filesystem and has no `FileAccess` entry point,
so it adds nothing to the file-access sentries.

### 4.15 CLI surface

```
decoy library path                      print the resolved root and where it came from
decoy library list [--kind K] [--pipeline P] [--table T] [--since D] [--json]
decoy library show ID|REF [--log] [--json]
decoy library diff A B [--json]         A and B are ids, refs, or latest~1 style
decoy library ref NAME [ID]             show or set a stored ref
decoy library prune [--kind K] [--keep-last N] [--older-than D] [--yes]
decoy library export --out FILE [--kind K] [--since D] [--ref R] [--include-logs] [--keep-paths]
decoy library clean [--yes]             scratch only
decoy library fsck [--repair]
decoy scan ... [--library DIR] [--no-save]
decoy run ...  [--library DIR] [--no-library]
```

`diff` dispatches on kind through the registry: `scan-set` uses the existing
scan-diff rules, `evidence` uses the existing `report diff` manifest
comparison, `run-result` compares status, route, row counts and delivery per
table, and any other kind gets a structural payload diff. `latest~1` means
the record before `latest` for the same filter. A `library` noun was chosen
over extending `decoy list KIND`, which lists engine registries, not stored
state.

### 4.16 `decoy run` writes by default

S4 made the CLI stateless (D3), partly on the clig rule "make external
actions explicit". The owner now wants records kept ("anytime a job runs it
should write a log"), so `decoy run` writes its job log, its run-result
record and its evidence record by default. To keep the action explicit, the
run card and `--json` output always name the log path, the record ids and the
library root.

- `--no-library` or `DECOY_LIBRARY=off` skips the records for that run.
- The job log has no opt-out. It is always written to the resolved root
  (`--library` and `DECOY_LIBRARY=<dir>` move it with the records; under
  `off` the chain skips the env step, 4.1). The only run without a log is one
  whose root is not writable, and that run warns (4.17).
- `--evidence-out` keeps working and writes the same manifest to the path
  given.

### 4.17 Library write failure on a run that worked

**Decision: warn, keep the exit code** (Revision 2, Q3). In a production
pipeline the data outcome is what the exit code reports; a full disk under
`.decoy/` must not turn a delivered run into a failure that an orchestrator
retries (delivering twice). The warning goes to stderr and into `--json`
(`library.status = "failed"` with a code; `log.status` the same for the job
log). An opt-in `--require-library` that exits 3 is a later, additive flag,
not V1. The same rule applies to `decoy scan`'s record save (L2): a failed
save warns, `--json` carries `library.status = "failed"`, and the exit code is
the scan's own.

## 5. Slices

Test depth: T0 per edit, T1 impact-selected per commit. L1a adds frozen tags,
reason identities and moves the CLI's canonical-JSON call; L1b moves the engine
pin; L1b, L1c, L1d and L4b add a destructive command and a concurrency scheme.
These are escalation triggers, so each merge head gets the full suite against
the saved main baseline.

### 5.0 Sequencing (shared with the other plan, identical text)

This section is the same in SCAN-MULTI (engine branch `plan/scan-multi`) and
LIB (CLI branch `plan/local-record-library`). The platform `docs/ROADMAP.md`
gets its rows from the orchestrator; neither plan edits it.

**Outside dependencies.**

- CLI-DIALECT: gated-pending handoff
  `10_Projects/decoy/handoffs/phase0.5/p05-cli-dialect-build-handoff.md` in the
  vault, branch `fix/cli-dialect-honour-csv-fields` from CLI main. Makes
  `decoy run` read CSV with `has_header`, `column_names` and `delimiter`.
  Standalone; it does not depend on CONFIG-EXPLICIT.
- CONFIG-EXPLICIT (plan in progress): the owner rule that a CSV source states
  `has_header`, names its columns through `column_names` or
  `column_names_file`, and lists every column in the YAML. Planned by another
  author. S1c's `--column-names-file` flag and S3-engine depend on it.
- RESULT (`decoy-run-result/v1`, F29 C1) for LIB L3a's run-result half, and
  SAMPLE (`decoy run --sample N`) for LIB L3b. Neither is defined on any branch
  today; both halves wait.
- CLI-CLOUD for any cloud integrity pass (V2 of S1b, section 5 S1b).

**Reason-registry chain.** Engine main is at `REGISTRY_VERSION = "1.5.0"`
(`reasons/_registry.py:24`). SUB-STOP takes 1.6.0 and STORM E1 takes 1.7.0.
After those, each registry-touching slice here claims the next free minor at
merge time through REG-RENUMBER (`scripts/dev/registry_renumber.py`, handoff
`10_Projects/decoy/handoffs/phase0.5/p05-reg-renumber-build-handoff.md`): such
slices may build in parallel but merge one at a time, one new minor per branch,
and never write a version where it does not mean the slice's own minor. The
roadmap rows already on the chain (F35 E1a, F32 E1b, F36 slice 4) interleave by
merge order. Registry-touching slices in these plans:

| Slice | Identities |
|---|---|
| LIB L1a-engine | the CLI-side library and log event codes (LIB LM8) |
| SCAN-MULTI S1a-engine | `warning.scan_header_suspect`, `warning.scan_key_type_mismatch` (S1b adds none) |
| SCAN-MULTI S3-engine | `config.namespace_placeholder_unset` |

**Engine releases** go one at a time. Each is followed by one cumulative CLI
repin that follows the engine repin checklist.

**Build order.**

1. LIB L1a-engine, engine release, then LIB L1b-cli (with the repin), L1c-cli
   and L1d-cli.
2. SCAN-MULTI S1a-engine, then S1b-engine on a branch from S1a; one engine
   release holds both.
3. CLI-DIALECT, then SCAN-MULTI S1c-cli (repin to the step 2 release; needs
   LIB L1b), then LIB L2-cli (needs L1c and L1d).
4. CONFIG-EXPLICIT, then SCAN-MULTI S3-engine and its release, then S3a-cli
   (repin), then S3b-cli.
5. LIB L4a after L1c, then L4b. LIB run side in the `run.py` lane: L5a (needs
   L1b), L5b (also needs L4a), L3a, L3b; RESULT and SAMPLE gate their halves.
   LIB L5c after L5b and S3b-cli.

Steps 1 and 2 can run at the same time on different branches; their releases
go out one after the other.

**One writer at a time per shared file.** The roadmap allows one `run.py`
writer at a time (`ROADMAP.md:548`), and the same rule applies here to the
other files several slices edit. Default order, which the orchestrator may
interleave with other rows (F29 C1 and F32 C0 also write `run.py`):

| File | Writers, in order |
|---|---|
| `src/decoy/cli/run.py` | L5a, L5b, L3a, L3b |
| `src/decoy/cli/scan.py` | S1c, L2, S3a-cli, S3b-cli, L5c |
| `src/decoy/cli/library.py` | L1c, L4a, then L4b and L5b in either order |
| `src/decoy_engine/profiling/scan_set.py` | S1a, S1b |

**OS lanes (Revision 2, Q2).** macOS tests run on the Mac mini as a
self-hosted GitHub Actions runner. Windows tests run on a self-hosted runner
on a GCP VM, provisioned before L1b starts and stopped when idle (the
existing `vm-reap` rule). A lane runs the library test paths only
(`tests/unit/library/`, `tests/e2e/test_library_*.py`,
`tests/e2e/test_job_logs.py`, the guards in `tests/sentry/test_library_writer.py`
and `tests/sentry/test_atomic_writer.py`), not the full suite. Required lanes
per slice:

| Slice | Linux | macOS (Mac mini) | Windows (GCP VM) | Why |
|---|---|---|---|---|
| L1a-engine | yes | no | no | pure functions; no filesystem |
| L1b-cli | yes | yes | yes | atomic writes, no-clobber link, retries, modes, ref lock, path budget |
| L1c-cli | yes | yes | yes | SQLite locking, freshness, remote-fs detection, fsck |
| L1d-cli | yes | yes | yes | scratch ACL at creation, best-effort deletes |
| L2-cli | yes | yes | no | scan writes through paths L1b and L1d already proved on Windows |
| L3a-cli | yes | no | no | uses L1 primitives only |
| L3b-cli | yes | yes | yes | scratch ACL and TTL deletion on a real sample, open handles |
| L4a-cli | yes | no | no | read commands and ref set over L1c |
| L4b-cli | yes | yes | yes | prune under concurrency, clean with open handles |
| L5a-cli | yes | no | no | in-process event wiring and the vault-commit move |
| L5b-cli | yes | yes | yes | append, kill mid-run, rotation with open handles |
| L5c-cli | yes | no | no | scan reuses the L5b writer |

A Windows or macOS lane result counts toward the slice's T1 and the gate's
T2 for the library paths; it is not the T3 full suite.

### L1a-engine: records module (engine, about 600 lines)

**Files and sizes.**
- new `src/decoy_engine/records/__init__.py` (~40), `_envelope.py` (~130:
  `RecordEnvelope`, `Link`, `Labels`, `Producer`), `_canonical.py` (~40),
  `_registry.py` (~110: `register_kind`, `registered_kinds`, `kind_spec`; a
  spec holds tag, write model, read model, path fields, diff rule id, canary
  fixture id), `_kinds.py` (~150: `cli-local-1` evidence, run-result,
  sample-run, reserved publication and checkpoint, and `scan-set` as reserved
  or pointed at SCAN-MULTI's `ScanSetCore` when S1a has merged), `_export.py`
  (~90), `_joblog.py` (~50: header model with the closed `command` enum, line
  reader).
- `src/decoy_engine/reasons/warning/_part1.py` (51) and
  `reasons/runtime/` as fits: the CLI-side event identities
  (`warning.library_write_failed`, `warning.job_log_write_failed`,
  `warning.library_degraded`, `warning.library_delete_skipped`, and the
  phase names the CLI emits if the event sanitizer requires registration; the
  builder lists every CLI event construction in L5a to L5c and registers each
  code). One manifest fixture; the minor is assigned at merge by
  REG-RENUMBER (section 5.0).
- `src/decoy_engine/__init__.py` (496): additive exports, about 10 lines.
- `docs/compatibility-contract.md` §3.1 (new tags `decoy-record/v1`,
  `decoy-library-export/v1`, `decoy-job-log/v1`, `sample-run/v1`), the
  compatibility corpus samples, `docs/reasons.md`, `CHANGELOG.md`.
- tests: `tests/unit/records/test_envelope.py`, `test_registry.py`,
  `test_export.py`, `test_joblog.py`, `test_kinds.py`.

**Behavior.** `build(kind, payload, *, producer, invocation_id, labels,
links, created_at)` validates the payload with the kind's write model and
returns a frozen envelope with `id` and `payload_digest`. `encode(envelope)`
returns canonical bytes; `decode(bytes)` parses, recomputes the id by the 4.3
rule, checks the envelope major and the payload tag, validates the payload
with the kind's read model, and returns the envelope (unknown payload major
gives `RecordNeedsNewer`, not an error that stops a listing). The `run-result`
model is a placeholder until RESULT fixes `decoy-run-result/v1`; if RESULT
is not ready when L1a lands, the kind is registered reserved and L3a turns it
on.

**Acceptance tests (written first) and named mutations.**

| Test | Asserts | Mutation that must turn it red |
|---|---|---|
| A1-id-stable | the same inputs give the same id across two processes and match a fixture recorded on another machine | MA1-unsorted: drop `sort_keys` |
| A1-id-covers-all | changing any envelope field or payload byte changes the id | MA1-skip: exclude `labels` from the hashed body |
| A1-id-parsed | a record re-serialized with CRLF line endings and two-space indent decodes and keeps its id | MA1-raw-bytes: hash the file bytes |
| A1-canonical-shared | `evidence.compute_manifest_hash` and `records._canonical` give identical bytes for the manifest corpus | MA1-ascii: `ensure_ascii=True` |
| A1-strict-payload | building with an unknown payload field raises `record_invalid` naming the field, not its value | MA1-extra: `extra="ignore"` on the write model |
| A1-read-tolerant | a record whose payload carries an extra optional field (as a later CLI would write under the same tag) decodes on this version, the extra field dropped; a wrong type in a known field still fails | MA1-read-strict: decode with the write model |
| A1-no-float-envelope | a float in a label raises | MA1-float: allow floats |
| A1-reserved | building a reserved kind raises `record_kind_reserved` | MA1-open: treat reserved as free-form |
| A1-decode-verify | changing one payload value fails decode with `record_corrupt` | MA1-trust: skip the id check |
| A1-newer | payload tag `scan-set/v9` decodes to `RecordNeedsNewer` | MA1-crash: raise instead |
| A1-export-roundtrip | export then read gives the same envelopes; a tampered line is rejected alone | MA1-batch: reject the whole file on one bad line |
| A1-registry-walk | `registered_kinds()` lists every kind defined in `_kinds.py` (walked from the module, not a hand list) | MA1-hidden: define a kind outside the registry |
| A1-scan-model-same | once SCAN-MULTI S1a is in, `kind_spec("scan-set").write_model is profiling.scan_set.ScanSetCore` | MA1-copy-model: define a second scan-set model in `_kinds.py` |
| A1-evidence-model | the CLI manifest corpus validates against the engine `cli-local-1` model | MA1-evidence-drift: drop a manifest field from the model |
| A1-codes-registered | every code in the L1a manifest fixture is `reasons.is_registered` | MA1-unregistered: emit a code missing from the registry |

**Frozen-contract effects.** Four new tags in §3.1, additive public API, a
compatibility corpus sample per tag, new reason identities at one minor. No
determinism or vault effect.

### L1b-cli: store, atomic writes, refs (CLI, about 620 lines)

Depends on L1a released and repinned.

**Files and sizes.**
- new `src/decoy/_atomic.py` (~150): `write_atomic` (section 4.9), Windows
  retry, POSIX directory fsync.
- new `src/decoy/cli/_library/__init__.py` (~80: `Library`, `open_library`),
  `_paths.py` (~120: `resolve_root`, subdirectory names, Windows path budget),
  `_fs.py` (~110: `create_private_file`, `ensure_private_dir`, calls into
  `_atomic`), `_store.py` (~120: `put`, `get`, `resolve`), `_refs.py` (~80),
  `_errors.py` (~40: `library_error`), `_policy.py` (~60).
- `src/decoy/cli/evidence.py` (557): `compute_manifest_hash` calls the engine
  canonical form; net change about zero.
- `pyproject.toml` engine pin; `CHANGELOG.md`; `docs/library.md` (new).
- tests: `tests/unit/library/test_fs.py`, `test_store.py`, `test_refs.py`,
  `test_paths.py`, `test_policy.py`, `tests/unit/test_atomic.py`; guards
  G-LIB-WRITER in `tests/sentry/test_library_writer.py`, G-ONE-ATOMIC-WRITER
  in `tests/sentry/test_atomic_writer.py` and G-ONE-CANONICAL in
  `tests/sentry/test_canonical_json.py`, all registered in the sentry registry.

**Behavior.** Sections 4.1, 4.2, 4.5, 4.6 (modes), 4.8 (record and ref
parts), 4.9. Until L1c lands, ref updates take the lock through a minimal
`index.sqlite` holding only the lock, pre-created 0600.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| B1-resolve | resolution order `--library`, `DECOY_LIBRARY`, YAML directory, cwd; for scan, `--emit-config` directory before `--config` directory; `off` turns records off and the log root skips the env step | MB1-order: env before flag; MB1-scan-cwd: scan ignores `--emit-config` |
| B1-mode | after puts and refs, every created file is 0600 and directory 0700 (POSIX); a pre-existing parent keeps its mode | M-MODE |
| B1-atomic-kill | a child process killed (SIGKILL on POSIX, `TerminateProcess` on Windows) during `put` leaves no readable partial record; only a temp file | MB1-direct: write to the final name |
| B1-idempotent | putting the same envelope twice gives one file and no error, including on Windows while another process holds the file open | MB1-replace: always `os.replace` |
| B1-no-clobber | two processes race `put` of the same envelope 50 times; no call raises, one file remains, it decodes, and a spy shows no `os.replace` on the record path | MB1-check-then-replace: `exists()` then `os.replace` |
| B1-existing-corrupt | an existing object with a different payload makes `put` raise `record_corrupt` | MB1-trust-existing |
| B1-concurrent | two processes put 50 records each; 100 files, each decodes | MB1-shared-tmp: fixed temp name |
| B1-ref-race | two processes set the same ref 20 times each; the final ref is one of the written ids and no update raises anything but `library_busy` | MB1-nolock: write refs without the lock |
| B1-win-retry | with the ref file held open (Windows lane), the update succeeds once the holder closes within the retry window, and fails with `library_busy` after it | MB1-noretry |
| B1-win-long-root | (Windows lane) a 160-character root is refused with `library_path_too_long` before any file is created; a 140-character root works | MB1-no-budget: skip the length check |
| B1-no-path-in-error | a write failure's message has the code and error class, not the path's text in `str(exc)` | MB1-exc |
| B1-gitfiles | the first write creates `.decoy/.gitignore` (scratch, logs, index, tmp, quarantine) and `.decoy/.gitattributes` (`library/objects/** -text`) and never edits an existing one | MB1-clobber |
| G-LIB-WRITER | no import of `_library._fs`, no `records.encode` call and no non-docstring literal with a `.decoy` path component outside `decoy/cli/_library/`, except the allowlisted runtime home; seeded bypass shown red | M-LIB-INLINE |
| G-ONE-ATOMIC-WRITER | no `os.replace`, `os.rename`, `os.link` or `mkstemp` outside `_atomic.py` except the allowlist (size 7 at L1b); seeded bypass shown red | M-ATOMIC-INLINE |
| G-ONE-CANONICAL | no canonical `json.dumps` outside the engine call except the allowlist (size 3); seeded bypass shown red | M-CANON-COPY |

**Frozen-contract effects.** New on-disk location `.decoy/` (layout 1). No
CLI verb yet.

### L1c-cli: index, freshness, degraded mode, fsck (CLI, about 600 lines)

Depends on L1b.

**Files and sizes.**
- new `src/decoy/cli/_library/_index.py` (~260: schema, 0600 pre-create,
  insert, query, freshness sync, rebuild), `_remote.py` (~80: remote
  filesystem detection per OS), `_fsck.py` (~160).
- new `src/decoy/cli/library.py` (~90 here: the command group with `path` and
  `fsck`), `src/decoy/__main__.py` (164) registration,
  `docs/cli-reference.md` regenerated, `docs/library.md`, `CHANGELOG.md`.
- tests: `tests/unit/library/test_index.py`, `test_remote.py`,
  `test_fsck.py`, `tests/e2e/test_library_fsck.py`.

**Behavior.** Sections 4.4, 4.8 (index, remote filesystems, degraded mode),
4.10.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| C1-rebuild | delete the index; the next open rebuilds it under the lock, rows equal to before | MC1-norebuild |
| C1-corrupt-index | random bytes in `index.sqlite`: commands still list, and the next locked open rebuilds it | MC1-crash: propagate the SQLite error |
| C1-hand-added | copy a valid object file into `objects/` by hand (as `git pull` would): the next `list` and `latest` include it without `fsck` | MC1-trust-index: skip the freshness listing |
| C1-crash-gap | kill a writer after the object link and before the index insert: the next open shows the record | MC1-insert-first: insert the row before the link (a crash then leaves a row with no file) |
| C1-gone-file | delete an object file by hand: the next open drops its row and `list` does not show it | MC1-keep-rows |
| C1-index-mode | the index file is 0600 at creation (POSIX), before any SQL runs | MC1-umask: let `sqlite3.connect` create it |
| C1-lock-unavailable | with SQLite locking forced to fail, `put` succeeds; ref set, prune and clean exit with `library_lock_unavailable` | MC1-unlocked-ref: allow refs without the lock |
| C1-remote-fs | with the filesystem probe returning remote, open enters degraded mode, `library path` reports it, and ref set refuses; with a local result, refs work | MC1-trust-lock: ignore the probe |
| C1-crlf | a committed record rewritten with CRLF endings passes `fsck` | MC1-raw-hash: hash bytes in fsck |
| C1-fsck-findings | a corrupt object, a dangling ref, a stale temp file and a 0644 log file each produce one finding and exit 4; a 0644 record produces an advisory note and exit 0 | MC1-silent: skip the hash check; MC1-record-mode: treat record modes as findings |
| C1-repair-safe | `--repair` quarantines the corrupt object, deletes the stale temp, keeps every valid record | MC1-delete: delete instead of quarantine |
| C1-layout-newer | `LAYOUT` 2 makes writes refuse with `library_layout_newer` | MC1-ignore |
| C1-list-speed | 5 000 records list in under 1 second from the index, freshness listing included (performance marker, T4) | none (budget check) |

**Frozen-contract effects.** New CLI noun `library` with `path` and `fsck`
(additive). `docs/cli-reference.md` and the surface sentry move.

### L1d-cli: scratch and the Windows ACL (CLI, about 330 lines)

Depends on L1b. Split out of L1b (Revision 5, LM13). Needed before L2 (scan
spill) and L3b (sample output).

**Files and sizes.**
- new `src/decoy/cli/_library/_scratch.py` (~130: `scratch(owner, ttl)`,
  `delete_on_exit`, best-effort delete with per-file report), `_winacl.py`
  (~90: SDDL at `CreateDirectoryW`, section 4.6).
- tests: `tests/unit/library/test_scratch.py`, `test_winacl.py`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| D1-mode | a scratch allocation is 0700 on POSIX, files in it 0600 | M-MODE |
| D1-delete-on-exit | a `delete_on_exit` allocation is gone after the owner's block exits, on success and on an exception | MD1-leak |
| D1-win-scratch-acl | (Windows lane) the `scratch/` and allocation DACLs are protected and list only the current user and SYSTEM; a file created inside inherits it; records and logs keep the inherited ACL | MB1-inherit: create the directory, then set the DACL (or skip it) |
| D1-acl-fail-closed | with the ACL call forced to fail, allocation raises `scratch_acl_failed` and no scratch directory remains | MB1-acl-warn: warn and continue |
| D1-delete-open | (Windows lane) a file held open inside an allocation is reported and skipped; the call returns normally; the next cleanup removes it once closed | MD1-raise: let `PermissionError` escape |

**Frozen-contract effects.** None beyond layout 1.

### L2-cli: scan records on the library (CLI, about 460 lines; the only build slice for SCAN-MULTI's scan record)

Depends on L1c, L1d, and SCAN-MULTI S1c (and so S1a and S1b released).
SCAN-MULTI S1d is a pointer to this slice.

**Files and sizes.**
- new `src/decoy/cli/_scan_record.py` (~150): build the `scan-set` record
  (`scan_set_to_dict(s, detail=False)`, path fields relativized, labels
  `{tables, pipeline}`), `put` it, map failure to the 4.17 warning, allocate
  the integrity spill from scratch.
- `src/decoy/cli/_scan_set_io.py` (SCAN-MULTI S1c, ~90): add the envelope
  branch to `load_scan_set` (+~50).
- `src/decoy/cli/scan.py` (1442, must not grow): `--no-save`, `--library
  DIR`, the call into `_scan_record.py`, `scan diff --latest`; net change at
  or below zero.
- tests: `tests/e2e/test_scan_library.py`; the scan canary fixture for
  G-KIND-CANARY in `tests/e2e/test_library_canary.py` (new, shared by L3 and
  L5).
- docs, `CHANGELOG.md`.

**Behavior.**
- After every table has scanned, one record of kind `scan-set`, payload tag
  `scan-set/v1`, is written through `Library.put` into
  `.decoy/library/objects/<2>/<62>.json`. The library root follows the scan
  rule in 4.1. Payload path fields are made relative to the project directory
  first (4.6).
- The card prints the short id and root; `--json` gains exactly one key,
  `library: {status, root, record_id}` (`status` is `saved`, `skipped` or
  `failed` with `code`). SCAN-MULTI T2-parquet-compat allows only this key.
- A failed save warns and keeps the exit code (4.17), the same rule as for
  `decoy run`.
- Integrity spill: `scan_sources(..., spill_dir=Library.scratch(
  "scan-integrity", delete_on_exit))`. With `--no-save`, `DECOY_LIBRARY=off`,
  or an unwritable root, `spill_dir=None`, and the engine uses its own
  private temp root, removed on exit (SCAN-MULTI S1b).
- `load_scan_set(path)`: when the JSON has `record_schema`, call
  `records.decode` (id rule, `RecordNeedsNewer`), check that the id matches
  the object file name when the path is under `objects/`, and return the
  payload; otherwise the bare-file branch from S1c. Every saved-scan reader
  already calls it (SCAN-MULTI guard G-ONE-SCAN-READER).
- `scan diff` accepts ids, refs, record paths, bare `scan-set/v1` files and
  `--latest` (the virtual `latest` and `latest~1` filtered by the same table
  set, ordered by `(created_at, id)`).
- A rescan of unchanged data gets a new record (`created_at` and
  `invocation_id` differ); `payload_digest` shows the content is unchanged.
- The record stores the detector result per column, never a policy default,
  so changing the starter YAML's defaults later changes no record.

**Acceptance tests and named mutations.** S1d's T6 intents carry over with
their mutation names.

| Test | Asserts | Mutation |
|---|---|---|
| L2-saved | a scan writes exactly one `scan-set` record, 0600; the card shows its short id and root; `--json` has `library` with `status: "saved"`, `root` and `record_id`, and no other new key | M6-mode: default umask; M6-bypass: write the file directly |
| L2-no-save | `--no-save` writes nothing under `.decoy/` and `library.status` is `skipped` | M6-ignore |
| L2-save-failed | read-only root: exit code 0, one warning with the code, `library.status = "failed"` | ML2-fail: exit 3 |
| L2-value-free | canary fixture with a declared relationship: no canary under `.decoy/` after the scan, and no spill file remains anywhere under `.decoy/scratch/` | M6-detail: save with `detail=True`; M-PAYLOAD-LEAK; ML2-keep-spill: allocate the spill without `delete_on_exit` |
| L2-spill-scratch | with integrity on, a spy on `scan_sources` sees `spill_dir` under `.decoy/scratch/`; with `--no-save` it sees `None` | ML2-system-tmp: always pass `None` |
| L2-atomic | a scan whose last table fails leaves no record and no temp file | M6-early: save before the last table |
| L2-diff-latest | two scans with a column added: `scan diff --latest` reports it | M6-order: oldest two |
| L2-same-instant | two records with the same `created_at`: `latest` picks the larger id on two machines and after an index rebuild | ML2-insert-order: order by index row id |
| L2-same-content | two scans of unchanged files: two ids, equal `payload_digest` | ML2-dedupe: reuse the first id |
| L2-relative-paths | a scan of `../data/a.csv` from a subdirectory stores `data/a.csv` relative to the project directory in the payload | ML2-abs: store the absolute path |
| L2-empty-table | an empty CSV with a header saves a record (rates `None`, no `record_invalid`) | ML2-nan: keep NaN |
| L2-no-pii-no-suggestion | a column with no detector match is stored with no suggestion, not `redact` or `passthrough` | ML2-policy: store the fallback strategy |
| L2-load-envelope | `fields`, `show` and `diff` give the same result for a library record and for the bare `--output` file of the same scan; a record renamed to another id is refused with `record_corrupt` | ML2-top-level: read only the top-level `scan_schema`; ML2-no-name-check |
| L2-legacy-file | `scan diff` still accepts two bare `scan-set/v1` files from `--output` | ML2-envelope-only |
| G-KIND-CANARY | `scan-set` has a canary fixture | M-KIND-NOFIX |

**Frozen-contract effects.** The earlier S1d location (`.decoy/scans/`) never
ships. Additive scan flags and one additive `--json` key.

### L3a-cli: evidence and run-result records (CLI, about 520 lines)

Depends on L1c and on L5b in the `run.py` lane (section 5.0). The run-result
half depends on RESULT (`decoy-run-result/v1`, F29 C1); the evidence half does
not and may land first.

**Files and sizes.**
- new `src/decoy/cli/_run_records.py` (~220): build and put the `evidence`
  and `run-result` records, relativize path fields, link them to each other,
  to the scan baseline record and to the job log (`rel: log` with its
  SHA-256).
- `src/decoy/cli/run.py` (1812, must not grow): `--no-library` and the call
  into `_run_records.py`; the card and `--json` print the ids; net change at
  or below zero (L5a's vault-commit move leaves room).
- `src/decoy/cli/report.py` (2382, must not grow): `report show`, `verify`
  and `diff` resolve an id or ref through one call into `_library`; net change
  at or below zero.
- tests: `tests/e2e/test_run_library_records.py`, canary fixtures for
  `evidence` and `run-result`; docs, `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L3-records | a successful run writes one evidence and one run-result record sharing an invocation id and linked both ways | ML3-nolink |
| L3-failed-run | a run that fails at runtime writes a run-result record with status `error` and the exit code, and no evidence record | ML3-evidence-on-fail |
| L3-baseline-link | end to end: `decoy scan data/*.csv --has-header --emit-config out/p.yaml` from the repo root, then `decoy run out/p.yaml` from another directory; the run-result links to the scan record by id, and that id resolves in `out/.decoy/library/` (the same library) | ML3-path-only: store the path, not the id; ML3-cwd-root: resolve the run's library from the current directory |
| L3-log-link | the run-result's `log` link names `logs/<invocation_id>.jsonl` with a matching SHA-256 | ML3-no-log-link |
| L3-evidence-same | the record payload equals the `--evidence-out` file after canonicalization, apart from the relativized path fields | ML3-drift: build the manifest twice |
| L3-no-library | `--no-library` and `DECOY_LIBRARY=off` write no record under `.decoy/library/`; the job log is still written | ML3-ignore |
| L3-readonly | read-only library root: run exits with its normal code, stderr has one warning with the code, `--json` has `library.status = "failed"` | ML3-fail: exit 3 |
| L3-canary | canary fixture: no canary in either record | M-PAYLOAD-LEAK |
| L3-report-id | `decoy report verify <id>` equals `report verify <file>` | ML3-file-only |

**Frozen-contract effects.** `decoy run` gains a default write (4.16) and one
flag; `report` accepts ids (additive). `cli-local-1` shape unchanged.

### L3b-cli: sample-run records and scratch lifecycle (CLI, about 450 lines)

Depends on L1d, L3a (the `run.py` lane) and SAMPLE (`decoy run --sample N`
through subset).

**Files and sizes.**
- new `src/decoy/cli/_sample_records.py` (~180): scratch allocation,
  `sample-run` record, replace and lazy expiry calls.
- `src/decoy/cli/run.py` (must not grow): the sample path calls into the new
  module; net change at or below zero.
- `src/decoy/cli/_library/_scratch.py` (L1d): expiry and replace rules
  (+~80).
- tests: `tests/e2e/test_sample_library.py`, the scratch positive control in
  `test_library_canary.py`; docs, `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L3b-scratch-only | after `--sample`, the canary appears under `.decoy/scratch/` and nowhere else under `.decoy/` (the positive control for every canary test) | ML3b-record-rows: copy the first output row into the record |
| L3b-metadata | the record has N, root, per-table counts, approximate columns, file hashes and the relative scratch path | ML3b-abs: absolute path |
| L3b-replace | a second sample of the same pipeline removes the first sample's scratch and keeps both records | ML3b-keep-all |
| L3b-replace-open | (Windows lane) the first sample's output held open: the second sample succeeds with its normal exit code, reports the skipped file, and the next command removes it once closed | ML3b-raise: fail the sample on `PermissionError` |
| L3b-ttl | scratch older than the TTL is removed by the next command; its record then shows "expired" | ML3b-nottl |
| L3b-ttl-open | (Windows lane) an expired file held open is skipped and reported; the command's exit code is unchanged | ML3b-ttl-raise |
| L3b-targets-untouched | targets and vault paths in the YAML are not created or changed by `--sample` | ML3b-target |
| L3b-staging | a failed sample leaves no staging directory | ML3b-leak-staging |

**Frozen-contract effects.** New tag `sample-run/v1` (registered in L1a).

### L4a-cli: library read commands and refs (CLI, about 420 lines)

Depends on L1c; `diff` for `run-result` needs L3a.

**Files and sizes.**
- `src/decoy/cli/library.py` (+~180, stays under ~300): `list`, `show`,
  `diff`, `ref`.
- new `src/decoy/cli/_library/_diff.py` (~140: dispatch by kind through the
  registry).
- `docs/cli-reference.md` regenerated, `docs/library.md`, `CHANGELOG.md`.
- tests: `tests/e2e/test_library_read_commands.py`.

| Test | Asserts | Mutation |
|---|---|---|
| L4-list | filters by kind, pipeline, table and time; `--json` is stable | ML4-filter |
| L4-show | `show <prefix>` resolves a unique 8-hex prefix and refuses an ambiguous one | ML4-first-match |
| L4-ref | `library ref NAME ID` sets under the lock; `library ref NAME` prints it; an invalid name is a usage error | ML4-ref-nolock |
| L4-diff | scan-set, evidence and run-result pairs give the kind-specific diff; mismatched kinds are a usage error | ML4-generic: structural diff for all |

**Frozen-contract effects.** Additive `library` verbs.

### L4b-cli: prune, export, clean (CLI, about 480 lines)

Depends on L4a.

**Files and sizes.**
- `src/decoy/cli/library.py` (+~120, stays under ~420): `prune`, `export`,
  `clean`.
- new `src/decoy/cli/_library/_prune.py` (~150: `prune_preview`,
  `prune_apply`, reachability, best-effort delete report).
- `docs/cli-reference.md`, `docs/library.md`, `CHANGELOG.md`.
- tests: `tests/e2e/test_library_destructive.py`,
  `tests/unit/library/test_prune.py`.

| Test | Asserts | Mutation |
|---|---|---|
| L4b-prune-preview | without `--yes`, prune lists exact ids and deletes nothing | ML4-apply: delete on preview |
| L4b-prune-reach | a record reachable from a ref or linked from a kept record survives `--keep-last 1` | ML4-noreach |
| L4b-prune-grace | a record younger than one hour survives | ML4-nograce |
| L4b-prune-concurrent | prune while another process puts records: no new record is deleted and fsck is clean after | ML4-unlocked |
| L4b-export-import | export then `records.read_export` gives the same ids; `--ref` exports exactly the reachable set; only declared path fields are stripped unless `--keep-paths` | ML4-paths: keep paths by default; ML4-strip-all: strip every string that looks like a path |
| L4b-export-remap | export a scan record and a run-result linking to it with paths stripped: the run-result's `baseline` link points at the scan line's new id, both lines verify, and header refs point at new ids | ML4-no-remap: keep old ids in links |
| L4b-export-scratch | no export option includes scratch content | ML4-scratch |
| L4b-clean | `clean` previews, then with `--yes` removes only `.decoy/scratch/`; a vault file inside the project is untouched | ML4-wide: remove `.decoy/` |
| L4b-clean-open | (Windows lane) a scratch file held open: `clean --yes` lists it as left behind, removes the rest, exits 4 | ML4-clean-raise: stop at the first `PermissionError` |

**Frozen-contract effects.** Additive `library` verbs; export format frozen
under `decoy-library-export/v1`.

### L5a-cli: wire the engine ProgressSink into `decoy run` (CLI, about 430 lines)

Depends on L1b (the shared atomic writer). First writer in the `run.py` lane.
Owns the hook found missing in the first pass: `decoy run` shows a spinner
(`run.py:41`) and passes no `ProgressSink` to the engine today.

**Files and sizes.**
- new `src/decoy/cli/_progress_fanout.py` (~150): a `ProgressSink` that
  forwards each engine event to registered consumers (the terminal progress
  display now, the log writer in L5b), so the engine sees one sink.
- new `src/decoy/cli/_vault_commit.py` (~90): `run.py`'s vault commit
  (`run.py:1622-1686`) moved onto `_atomic.write_atomic`, behavior unchanged;
  this takes `run.py` off the G-ONE-ATOMIC-WRITER allowlist and pays for the
  call-site lines below.
- `src/decoy/cli/run.py` (1812): pass the sink on every route `decoy run` uses
  (full-frame, chunked, sequential, out-of-core, sample); replace the bare
  spinner with a display that reads phase and rate events; mint the run's
  `invocation_id` here so L3a records and L5b logs share it. Net change below
  zero after the vault-commit move.
- `src/decoy/ui/progress.py`: phase and rate rendering on stderr.
- tests: `tests/unit/test_progress_fanout.py`,
  `tests/e2e/test_run_progress_events.py`, the existing vault-commit tests
  re-pointed at `_vault_commit.py` without changing their assertions;
  `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L5a-every-route | a test consumer receives a terminal event and at least one phase event on each route `decoy run` can take (route forced per case) | ML5a-route: pass the sink on the full-frame route only |
| L5a-order | events reach consumers in emission order with increasing `sequence` | ML5a-buffer: reorder through a set |
| L5a-consumer-fault | a consumer that raises does not change the run's outcome or exit code; the failure is counted, not retried | ML5a-propagate: let the consumer error escape |
| L5a-quiet-json | `--quiet` and `--json` keep stdout free of progress; events still reach non-display consumers | ML5a-stdout |
| L5a-no-value | events carry only engine-sanitized fields (the canary fixture produces no canary in any event dict) | ML5a-wrap: add a CLI message field |
| L5a-vault-same | the existing vault-commit tests pass unchanged against `_vault_commit.py`, and the atomic-writer allowlist shrinks from 7 to 6 | ML5a-vault-inline: keep a private `os.replace` in `_vault_commit.py` (G-ONE-ATOMIC-WRITER red) |

**Frozen-contract effects.** None persisted. stderr progress text changes
(not a contract).

### L5b-cli: job logs for `decoy run` (CLI, about 470 lines)

Depends on L5a and L4a (`library show`). Does not depend on L3a or RESULT
(Revision 5, LM10).

**Files and sizes.**
- new `src/decoy/cli/_library/_logs.py` (~220: writer as an L5a consumer,
  rotation with best-effort deletes, reader, lookup by `invocation_id`).
- `src/decoy/cli/run.py` (must not grow): register the log writer on every
  run; CLI-side events built from engine event classes with L1a's registered
  codes.
- `src/decoy/cli/library.py`: `show --log`.
- `tests/e2e/test_stateless_cli.py`: the assertion at line 89 ("no `.decoy`
  path is created") is replaced, not deleted, by a stronger one named
  `test_run_writes_only_resolved_library`: every created path containing
  `.decoy` lies under `<yaml dir>/.decoy/`; under that root only
  `.gitignore`, `.gitattributes`, `logs/` and (after L3a) `library/` appear;
  no `.duckdb` file appears; and the run's row canary appears nowhere under
  `.decoy/` outside `scratch/`. The same rule is applied to any other test
  that asserts no `.decoy` path (the builder greps `tests/` for `".decoy"` and
  lists each hit in the build record). Deleting or loosening such an
  assertion is a gate finding.
- tests: `tests/e2e/test_job_logs.py`, log canary in `test_library_canary.py`;
  docs, `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L5-written | a run writes one log with the header and a terminal event; `library show <any record of that invocation> --log` finds it by `invocation_id` | ML5-nofind: look the log up only through a link |
| L5-header-closed | the header's `command` is `run`; arguments that hold a canary never appear in the header | ML5-argv: write `argv` into `command` |
| L5-always | `--no-library` and `DECOY_LIBRARY=off` still write the log (under `off`, to `<yaml dir>/.decoy/logs/`); only an unwritable root skips it, with one warning and `log.status = "failed"` in `--json` | ML5-optout: honor `--no-library` for the log; ML5-off-cwd: write the `off` log to the current directory |
| L5-value-free | canary fixture, including a failure whose exception text quotes a cell: no canary in the log, the terminal line has the class name only, and no line carries `unregistered_reason` | M-LOG-MSG; ML5-unregistered: emit a CLI code missing from the registry |
| L5-verbose | `--verbose` traceback appears on stderr and not in the log | ML5-tee: copy stderr into the log |
| L5-truncated | a run killed mid-way leaves a log whose complete lines parse; readers skip the partial last line | ML5-strict: fail on a partial line |
| L5-rotate | with 52 logs for one pipeline, the next run leaves 50, never removing a log linked from a ref-protected record | ML5-noprotect |
| L5-rotate-open | (Windows lane) a log held open is skipped and reported; the run's exit code is unchanged | ML5-rotate-raise |
| L5-age | logs older than `max_age_days` are rotated | ML5-noage |
| L5-stateless-replaced | `test_run_writes_only_resolved_library` fails if a `.decoy` path appears in the current directory when the YAML is elsewhere | ML5-cwd-log: write the log under the current directory |
| L5-tail | `library show <run> --log` prints the events in order and, once L3a's link exists, says if the hash no longer matches | ML5-nohash |

**Frozen-contract effects.** New tag `decoy-job-log/v1` (registered in L1a);
log lines are the engine's frozen event schema.

### L5c-cli: job logs for multi-table `decoy scan` (CLI, about 160 lines)

Depends on L5b and SCAN-MULTI S3b-cli (last in the `scan.py` lane). Split out
of L5b so the `run.py` and `scan.py` lanes stay separate (Revision 5, LM9).

**Files and sizes.**
- new `src/decoy/cli/_scan_log.py` (~70): scan's per-table phase and terminal
  events through the L5b writer (command `scan`).
- `src/decoy/cli/scan.py` (must not grow): one registration call; net change
  at or below zero.
- tests: `tests/e2e/test_scan_job_log.py`, scan log canary.

| Test | Asserts | Mutation |
|---|---|---|
| L5c-written | a three-table scan writes one log with `command: scan`, one phase event per table and a terminal event, in the same library as its record | ML5c-cwd: write the log under the current directory |
| L5c-value-free | canary fixture: no canary in the scan log | M-LOG-MSG |

**Frozen-contract effects.** None beyond `decoy-job-log/v1`.

### Totals

| Slice | Repo | Lines (est.) | Depends on |
|---|---|---|---|
| L1a-engine | engine | ~600 | none |
| L1b-cli | CLI | ~620 | L1a release and repin; Windows runner provisioned |
| L1c-cli | CLI | ~600 | L1b |
| L1d-cli | CLI | ~330 | L1b |
| L2-cli | CLI | ~460 | L1c, L1d, SCAN-MULTI S1c (replaces S1d) |
| L3a-cli | CLI | ~520 | L1c, L5b (run.py lane); RESULT for the run-result half |
| L3b-cli | CLI | ~450 | L1d, L3a (run.py lane), SAMPLE |
| L4a-cli | CLI | ~420 | L1c (L3a for run-result diff) |
| L4b-cli | CLI | ~480 | L4a |
| L5a-cli | CLI | ~430 | L1b |
| L5b-cli | CLI | ~470 | L5a, L4a |
| L5c-cli | CLI | ~160 | L5b, SCAN-MULTI S3b-cli |

Each slice is under 800 hand-written lines including tests, and every new file
is under about 300. Logging per slice: one operational line per library write
failure, per skipped delete and per prune or clean (counts, kind, error class;
never a path's contents or a value), plus the job log itself in L5b and L5c.

## 6. Owner questions

All eight questions are answered; see Revision 2 at the top. The original
text is kept below for the record.

No new LIB question in Revision 5. The one new owner question from the joint
review, declared key columns getting `hash` with the relationship namespace
(pending owner confirm), is SCAN-MULTI Q11; it changes no record shape here.

- **Q1. Windows permissions.** V1 relies on inherited ACLs on Windows (records
  and logs hold no values; scratch can). Accept that, or set a protected
  owner-only ACL on `.decoy/` (about 80 more lines in L1b, using `ctypes`)?
  Recommended: accept for V1 and document it, unless Windows ships as a
  supported platform, in which case set the ACL on `scratch/`.
- **Q2. OS lanes in CI.** Proving atomic writes, locks and retries on
  Windows and macOS needs `windows-latest` and `macos-latest` jobs (GitHub
  Actions minutes) or the Mac mini plus a Windows host. Approve GitHub
  Actions lanes for the library tests only?
- **Q3. Library write failure on a run that worked.** Recommended: warn and
  keep the run's exit code (4.17). Alternative: exit 3, or an opt-in
  `--require-library`.
- **Q4. Defaults.** Job logs: last 50 runs per pipeline and 30 days. Sample
  scratch: 24 hours, replaced by the next sample. Records: keep all. Confirm
  or change.
- **Q5. Committing records.** Recommended: `.decoy/.gitignore` ignores
  scratch, logs and the index, and leaves records committable, so a
  `scan_baseline` reference works in CI. Or ignore the whole `.decoy/`?
- **Q6. Paths in exports.** Recommended: strip paths to file names by
  default, `--keep-paths` to keep them.
- **Q7. User-level store.** Deferred to after V1 (4.1). Confirm.
- **Q8. `decoy run` writes by default.** This reverses the S4 stateless rule
  for `run`. Recommended: on by default, always printed, `--no-library` to
  turn off (4.16). Confirm.
