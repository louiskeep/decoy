Status: plan

# LIB: the local record library and its retention classes

Owner: Cam. Date: 2026-11-05. Scope: CLI V1 (CLI repo, plus one engine module).
Planned against CLI `origin/main` 8fba6af and engine `origin/main` 41a86f47, and
the SCAN-MULTI plan on engine branch `plan/scan-multi` at 01ee6fde.

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

- scan snapshots (`scan-set/v1`, SCAN-MULTI S1d, planned for `.decoy/scans/`),
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
   (or the current directory when no YAML is involved). `--library DIR` and
   `DECOY_LIBRARY` override it. Every command that writes to it prints the
   root it used.
2. Every record is one immutable JSON file in one envelope
   (`decoy-record/v1`) with a kind, a per-kind payload tag, a content id, a
   creation time, producer versions, an invocation id and typed links to
   related records.
3. Records and job logs never contain a data value. This is enforced by the
   only writer (strict payload models, engine progress events) and proven by
   canary tests for every registered kind. Scratch is the only Decoy area that
   holds rows.
4. Files Decoy creates in the library are 0600 and directories it creates are
   0700 on Linux and macOS, at creation time. On Windows `scratch/` gets an
   owner-only ACL; records and logs inherit the parent directory's ACL
   (section 4.6 names the limit).
5. A record write is atomic on Linux, macOS and Windows: a reader sees the
   whole record or no record. A crash leaves at most a temp file that `fsck`
   removes.
6. Two Decoy processes may write to one library at once. No record is lost,
   no ref update is lost silently, and prune never deletes a record that a
   ref or a kept record links to.
7. Records are kept until the user prunes them. Job logs and scratch follow
   their own defaults, configurable in one file (`.decoy/library.yaml`).
   Every `decoy run` writes a job log; only the records can be opted out.
8. `decoy library export` writes one self-verifying file
   (`decoy-library-export/v1`) that the platform can import idempotently.
9. A library written by this version stays readable by every later V1 CLI
   (compatibility contract §3.1 rules).

### Non-goals

- No user-level store in V1 (section 4.1 keeps the slot open).
- No search over payload contents beyond the index columns (kind, time,
  pipeline, tables, status, links).
- No signing. Record ids are unkeyed SHA-256, like `manifest_hash`: they detect
  accidental change, not a tamperer.
- No network or shared-drive guarantee. A library on NFS or SMB works in
  degraded mode (section 4.8); concurrent writers on a network drive are
  unsupported.
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
| Two processes write records at once | Each writes its own uniquely named temp file and renames it to its own content id. No conflict. The index takes each insert in its own SQLite transaction with a busy timeout. |
| Two processes move the same ref at once | Ref updates run under the library lock (an SQLite `BEGIN IMMEDIATE` on the index). The loser waits up to the busy timeout and then fails with `library_busy`; it never overwrites silently. |
| Prune while a run is writing | Prune holds the library lock, never deletes a record younger than the grace period (one hour, the git `gc.pruneExpire` idea), and never deletes a record reachable from a ref or from a kept record. |
| Windows: target file open by another process during `os.replace` | Records never replace an existing file (same id means same bytes, so an existing object is success). Ref and state files retry the replace with bounded backoff (10 tries, about 1 second in total), then fail with `library_busy`. |
| Record file whose bytes do not hash to its name | Readers refuse it with `record_corrupt` and the id. `fsck` reports it and `fsck --repair` moves it to `library/quarantine/`; nothing is deleted. |
| Index missing, corrupt, or from another layout version | The index is a cache. Any open failure marks it stale and `list` falls back to a directory scan with a notice; `fsck --repair` rebuilds it from the object files and ref files. |
| Index cannot be locked (network filesystem) | Record writes still succeed (the object file is the truth) and mark the index stale. Ref updates and prune refuse with `library_lock_unavailable`. |
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
    the registered strict model (`extra="forbid"`, typed fields). Guard
    G-LIB-WRITER walks the CLI package syntax tree: no module outside
    `decoy/cli/_library/` imports `_library._fs`, refers to the `.decoy`
    literal, or calls `records.encode` (the bytes producer). Proven on a
    seeded bypass. Mutation M-LIB-INLINE: `scan.py` writes
    `Path(".decoy/library/x.json")` directly; the guard goes red.
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
- **No registry for one site.** Library root resolution is one function.
- **House style.** Typed context objects (`LibraryRoot`, `RecordEnvelope`,
  `RetentionPolicy`), no flag arguments that switch behavior (separate
  `prune_preview` and `prune_apply`), comments that explain why.

## 4. Decisions

Each decision states the recommendation first, then the alternatives weighed.

### 4.1 Where the library lives

**Recommendation: project-local only in V1.** The root is resolved in this
order: `--library DIR`, then `DECOY_LIBRARY` (the value `off` disables the
library for the process), then `<directory of the pipeline YAML>/.decoy/`,
then `<current directory>/.decoy/`. Records describe a pipeline and its data,
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

### 4.3 One envelope, per-kind payloads

**Recommendation.** Every record is:

```json
{
  "record_schema": "decoy-record/v1",
  "kind": "scan-set",
  "payload_schema": "scan-set/v1",
  "id": "sha256:<64 hex>",
  "created_at": "2026-11-05T21:14:03Z",
  "invocation_id": "<uuid4>",
  "producer": {"name": "decoy-cli", "version": "0.x.y", "engine_version": "0.x.y"},
  "labels": {"pipeline": "pipelines/claims.yaml", "tables": ["claims", "members"], "status": "ok"},
  "links": [{"rel": "baseline", "id": "sha256:..."}],
  "payload_digest": "sha256:<64 hex>",
  "payload": {}
}
```

- `id` is the SHA-256 of the canonical bytes of the envelope without `id`.
  Because `created_at` and `invocation_id` are inside, a rescan of unchanged
  data gets a new record (SCAN-MULTI S1d kept that behavior).
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
| `scan-set` | `scan-set/v1` (core, `detail=False`) | engine, SCAN-MULTI S1a | L2 |
| `evidence` | `cli-local-1` (the existing manifest, unchanged) | CLI `evidence.py` | L3a |
| `run-result` | `decoy-run-result/v1` | RESULT row (UX map 5.4) | L3a, once RESULT defines it |
| `sample-run` | `sample-run/v1` (new, section 4.13) | this plan | L3b |
| `publication` | reserved | DELIV plan | not in this plan |
| `checkpoint` | reserved (`checkpoint-index/v1`) | F23 plan | not in this plan |

A reserved kind is registered with no payload model; `records.build` refuses
it with `record_kind_reserved` until its plan adds the model. This keeps the
kind names and link types stable now. For F23, the authoritative checkpoint
activation record stays with the staged artifacts in the run's delivery root
(UX map 6.1); the library holds only a value-free index entry pointing at it.
F23 may reuse the engine envelope and the CLI atomic writer for the
activation record itself.

Alternatives: *a bare payload file per feature* (today's plan for S1d) gives
no common listing, linking or import; *one big JSON per run holding all
kinds* couples kinds that have different lifetimes and owners.

### 4.4 Index

**Recommendation: object files are the truth; `index.sqlite` is a rebuildable
cache.** One table `records(id, kind, payload_schema, created_at,
invocation_id, pipeline, status, payload_digest, size)`, one `links(src, rel,
dst)` table, one `tables(id, table_name)` table, `PRAGMA user_version` for the
index schema. Rollback-journal mode (SQLite's default), `busy_timeout` 5
seconds. A version mismatch or any corruption means rebuild, never migrate.

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

- `latest` is virtual: computed from the index (newest record of a kind,
  optionally filtered by pipeline or table set). No stored file, so two runs
  never contend over it.
- Stored refs live at `refs/<kind>/<name>` (names `[a-z0-9][a-z0-9._-]{0,63}`,
  a `/` allowed once for a pipeline scope). V1 writers: `decoy scan
  --emit-config` sets `scan-set/baseline/<pipeline slug>`; users set others
  with `decoy library ref`.
- Refs are the garbage-collection roots: prune keeps every record reachable
  from a ref through `links`.
- Ids may be abbreviated to any unique prefix of 8 or more hex digits, as git
  allows.

Alternatives: *time-named files* (S1d's `<time>-<hash>.json`) sort nicely but
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
- Paths: records may carry the paths the user wrote in the YAML (the
  evidence manifest does today). Paths are not data values, but they can name
  users and hosts, so export strips them to file names by default (4.11).
- Modes on Linux and macOS: temp files come from `tempfile.mkstemp` (0600,
  `O_EXCL`) in `library/tmp/`; directories the library creates get 0700 at
  creation, and an existing parent is never re-permissioned (the token-vault
  rule). `fsck` reports any library file that is group- or world-readable.
- Windows: `os.chmod` cannot express 0600. `scratch/`, the only class that
  can hold rows, gets a protected DACL when the library creates it: the
  current user and SYSTEM only, inheritance from the parent disabled,
  inherited by every child, set with `SetNamedSecurityInfoW` through `ctypes`
  (no new dependency). If the ACL cannot be applied, scratch allocation fails
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

- Record writes need no lock: unique temp name, rename to a content-addressed
  name. If the final name exists, the record exists (same id means same
  bytes; the writer verifies the existing file's hash and reports corruption
  if it differs).
- The index takes one short transaction per insert.
- One library lock for ref updates, prune, clean and index rebuild:
  `BEGIN IMMEDIATE` on `index.sqlite`. SQLite locking works the same on
  Linux, macOS and Windows, so the library does not need `fcntl` (which is
  absent on Windows, `distribution/lock.py`) or a hand-written lock file with
  stale-lock rules.
- When the index cannot be locked (network filesystems, section 2), record
  writes continue and mark the index stale; ref updates, prune and clean
  refuse with `library_lock_unavailable`.

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
3. For `CREATE_ONCE`, if the target exists: verify it and return. Otherwise
   `os.replace(tmp, target)`. On Windows, retry a `PermissionError` with
   bounded backoff (10 tries, doubling from 10 ms, about 1 second).
4. On POSIX, fsync the target directory. On Windows, skip it (a directory
   cannot be opened with `os.open`; NTFS journals the rename).
5. Any failure unlinks the temp file and raises one coded error without the
   path in `str(exc)` (the engine `write_private` rule).

The engine's `fileaccess.write_private` is not reused: it runs through the
engine's file-access policy and its POSIX descriptor machinery
(`_openat2.py`, `_rooted.py`), meant for engine copies of real data, and the
library is CLI-owned and must run on Windows. The recipe is the same and the
code cites it.

`.decoy/.gitignore` is written once, only if absent, with `scratch/`,
`logs/`, `library/index.sqlite`, `library/tmp/`, `library/quarantine/`.

### 4.10 Corruption handling and fsck

`decoy library fsck` (read-only) checks: every object's bytes hash to its
name; every envelope parses and its payload validates for its tag; every ref
points to an existing record; every link target exists (dangling links are
warnings, since prune may remove an unprotected target); the index matches
the objects; no temp file is older than one hour; POSIX modes are private;
job log lines parse (a partial last line is a warning). Exit 0 clean, 4 on
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
  `--keep-paths`. Without `--keep-paths`, paths are reduced to file names;
  because that changes the bytes, each such line gets a new id and carries
  the original id as `source_id`, and the header says `paths_stripped:
  true`. Scratch is never exportable.
- The engine owns the codec (`records.export_lines`, `records.read_export`),
  so the platform importer upserts by id with the same code.

Alternative: a zip or tar of `objects/`. Easy to produce, but harder to
stream, filter and verify line by line, and a tar from Windows carries
platform quirks.

### 4.12 Job logs

**Recommendation.** A job log is `.decoy/logs/<invocation_id>.jsonl`:

- Line 1 is a header: `{"log_schema": "decoy-job-log/v1",
  "event_schema": <engine EVENT_SCHEMA_VERSION>, "invocation_id", "command",
  "pipeline", "started_at", "producer"}`.
- Every other line is `event_to_dict(event)` for an engine `ProgressEvent`
  (phase, rate, route, warning, retry, checkpoint, publication, terminal),
  plus CLI-side events built from the same classes (validate step finished,
  library write failed). The engine already sanitizes names, admits only
  registered codes and keeps only exception class names, so the log is
  value-free by construction.
- Lines are appended and flushed as events arrive; the file is fsynced and
  closed at the end. A crash leaves a truncated last line, which readers skip
  and `fsck` reports as a warning. The log is never renamed into place, so a
  reader can follow a running job.
- When the run ends, the run-result record links to the log (`rel: log`) with
  its SHA-256, so `decoy library show <run>` can open it and detect edits.
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
| Kind registry, payload models for engine-owned kinds (`scan-set/v1`, `decoy-run-result/v1`, `sample-run/v1`) and the reserved kinds | engine | the platform stores and reads the same payloads |
| Export codec (`export_lines`, `read_export`) | engine | the platform importer reads it |
| Job log header model and line reader | engine | the platform job-log store can ingest the same lines |
| `cli-local-1` evidence payload model | CLI, registered into the engine registry at import time through `records.register_kind` | the manifest is CLI-owned today; moving it is a separate decision |
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
  (`--library` and `DECOY_LIBRARY=<dir>` move it with the records). The only
  run without a log is one whose root is not writable, and that run warns
  (4.17).
- `--evidence-out` keeps working and writes the same manifest to the path
  given.

### 4.17 Library write failure on a run that worked

**Decision: warn, keep the exit code** (Revision 2, Q3). In a production
pipeline the data outcome is what the exit code reports; a full disk under
`.decoy/` must not turn a delivered run into a failure that an orchestrator
retries (delivering twice). The warning goes to stderr and into `--json`
(`library.status = "failed"` with a code; `log.status` the same for the job
log). An opt-in `--require-library` that exits 3 is a later, additive flag,
not V1.

## 5. Slices

Order: L1a-engine, engine release and CLI repin, L1b, L1c, then L2, L3a,
L3b, L4, L5a and L5b, which depend only on L1c and their feature rows and can run
in parallel on non-overlapping files. Test depth: T0 per edit, T1
impact-selected per commit. L1a adds frozen tags and moves the CLI's
canonical-JSON call; L1b moves the engine pin; L1b, L1c and L4 add a
destructive command and a concurrency scheme. These are escalation
triggers, so each merge head gets the full suite against the saved main
baseline.

**OS lanes (Revision 2, Q2).** macOS tests run on the Mac mini as a
self-hosted GitHub Actions runner. Windows tests run on a self-hosted runner
on a GCP VM, provisioned before L1b starts and stopped when idle (the
existing `vm-reap` rule). A lane runs the library test paths only
(`tests/unit/library/`, `tests/e2e/test_library_*.py`,
`tests/e2e/test_job_logs.py`, the guard in
`tests/sentry/test_library_writer.py`), not the full suite. Required lanes
per slice:

| Slice | Linux | macOS (Mac mini) | Windows (GCP VM) | Why |
|---|---|---|---|---|
| L1a-engine | yes | no | no | pure functions; no filesystem |
| L1b-cli | yes | yes | yes | atomic writes, retries, modes, scratch ACL, ref lock |
| L1c-cli | yes | yes | yes | SQLite locking, degraded mode, fsck |
| L2-cli | yes | yes | no | scan writes through L1b paths already proven on Windows |
| L3a-cli | yes | no | no | uses L1 primitives only |
| L3b-cli | yes | yes | yes | scratch ACL and TTL deletion on a real sample |
| L4-cli | yes | yes | yes | prune under concurrency, clean |
| L5a-cli | yes | no | no | in-process event wiring |
| L5b-cli | yes | yes | yes | append, kill mid-run, rotation |

A Windows or macOS lane result counts toward the slice's T1 and the gate's
T2 for the library paths; it is not the T3 full suite.

### L1a-engine: records module (engine, about 520 lines)

**Files.**
- new `src/decoy_engine/records/__init__.py`, `_envelope.py`
  (`RecordEnvelope`, `Link`, `Labels`, `Producer`), `_canonical.py`,
  `_registry.py` (`register_kind`, `registered_kinds`, `kind_spec`),
  `_kinds.py` (scan-set, run-result, sample-run, reserved publication and
  checkpoint), `_export.py`, `_joblog.py` (header model, line reader).
- `src/decoy_engine/__init__.py`: additive exports.
- `docs/compatibility-contract.md` §3.1 (new tags `decoy-record/v1`,
  `decoy-library-export/v1`, `decoy-job-log/v1`, `sample-run/v1`), the
  compatibility corpus samples, `CHANGELOG.md`.
- tests: `tests/unit/records/test_envelope.py`, `test_registry.py`,
  `test_export.py`, `test_joblog.py`.

**Behavior.** `build(kind, payload, *, producer, invocation_id, labels,
links, created_at)` validates the payload with the kind's strict model and
returns a frozen envelope with `id` and `payload_digest`. `encode(envelope)`
returns canonical bytes; `decode(bytes)` verifies the id, the envelope major
and the payload tag, and returns the envelope (unknown payload major gives
`RecordNeedsNewer`, not an error that stops a listing). The `run-result`
model is a placeholder until RESULT fixes `decoy-run-result/v1`; if RESULT
is not ready when L1a lands, the kind is registered reserved and L3a turns it
on.

**Acceptance tests (written first) and named mutations.**

| Test | Asserts | Mutation that must turn it red |
|---|---|---|
| A1-id-stable | the same inputs give the same id across two processes and match a fixture recorded on another machine | MA1-unsorted: drop `sort_keys` |
| A1-id-covers-all | changing any envelope field or payload byte changes the id | MA1-skip: exclude `labels` from the hashed body |
| A1-canonical-shared | `evidence.compute_manifest_hash` and `records._canonical` give identical bytes for the manifest corpus | MA1-ascii: `ensure_ascii=True` |
| A1-strict-payload | an unknown payload field raises `record_invalid` naming the field, not its value | MA1-extra: `extra="ignore"` |
| A1-no-float-envelope | a float in a label raises | MA1-float: allow floats |
| A1-reserved | building a reserved kind raises `record_kind_reserved` | MA1-open: treat reserved as free-form |
| A1-decode-verify | a one-byte edit fails decode with `record_corrupt` | MA1-trust: skip the id check |
| A1-newer | payload tag `scan-set/v9` decodes to `RecordNeedsNewer` | MA1-crash: raise instead |
| A1-export-roundtrip | export then read gives the same envelopes; a tampered line is rejected alone | MA1-batch: reject the whole file on one bad line |
| A1-registry-walk | `registered_kinds()` lists every kind defined in `_kinds.py` (walked from the module, not a hand list) | MA1-hidden: define a kind outside the registry |

**Frozen-contract effects.** Four new tags in §3.1, additive public API, a
compatibility corpus sample per tag. No determinism or vault effect.

### L1b-cli: store, atomic writes, refs, scratch (CLI, about 700 lines)

Depends on L1a released and repinned.

**Files.**
- new `src/decoy/cli/_library/__init__.py` (`Library`, `open_library`),
  `_paths.py` (root resolution, subdirectory names), `_fs.py`
  (`write_atomic`, `create_private_file`, `ensure_private_dir`, Windows
  retry, directory fsync), `_store.py` (`put`, `get`, `resolve`), `_refs.py`,
  `_scratch.py` (`scratch(owner, ttl)`, expiry), `_winacl.py` (the
  owner-only DACL for `scratch/`, `ctypes` over `SetNamedSecurityInfoW`),
  `_policy.py` (`RetentionPolicy`, reads `.decoy/library.yaml`).
- `src/decoy/cli/evidence.py`: `compute_manifest_hash` calls the engine
  canonical form.
- `pyproject.toml` engine pin; `CHANGELOG.md`; `docs/library.md` (new).
- tests: `tests/unit/library/test_fs.py`, `test_store.py`, `test_refs.py`,
  `test_paths.py`, `test_policy.py`; the G-LIB-WRITER guard in
  `tests/sentry/test_library_writer.py`, registered in the sentry registry.

**Behavior.** Sections 4.1, 4.2, 4.5, 4.6, 4.8 (record and ref parts), 4.9.
Until L1c lands, ref updates take the lock through a minimal
`index.sqlite` holding only the lock.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| B1-resolve | resolution order `--library`, `DECOY_LIBRARY`, YAML directory, cwd; `off` disables | MB1-order: env before flag |
| B1-mode | after puts, refs and a scratch allocation, every created file is 0600 and directory 0700 (POSIX); a pre-existing parent keeps its mode | M-MODE |
| B1-atomic-kill | a child process killed (SIGKILL on POSIX, `TerminateProcess` on Windows) during `put` leaves no readable partial record; only a temp file | MB1-direct: write to the final name |
| B1-idempotent | putting the same envelope twice gives one file and no error, including on Windows while another process holds the file open | MB1-replace: always `os.replace` |
| B1-existing-corrupt | an existing object with wrong bytes makes `put` raise `record_corrupt` | MB1-trust-existing |
| B1-concurrent | two processes put 50 records each; 100 files, each decodes | MB1-shared-tmp: fixed temp name |
| B1-ref-race | two processes set the same ref 20 times each; the final ref is one of the written ids and no update raises anything but `library_busy` | MB1-nolock: write refs without the lock |
| B1-win-retry | with the ref file held open (Windows lane), the update succeeds once the holder closes within the retry window, and fails with `library_busy` after it | MB1-noretry |
| B1-no-path-in-error | a write failure's message has the code and error class, not the path's text in `str(exc)` | MB1-exc |
| B1-gitignore | the first write creates `.decoy/.gitignore` with the scratch and logs entries and never edits an existing one | MB1-clobber |
| B1-win-scratch-acl | (Windows lane) the `scratch/` DACL is protected and lists only the current user and SYSTEM; a file created inside inherits it; records and logs keep the inherited ACL | MB1-inherit: skip the DACL |
| B1-acl-fail-closed | with the ACL call forced to fail, scratch allocation raises `scratch_acl_failed` and no scratch directory remains | MB1-acl-warn: warn and continue |
| G-LIB-WRITER | no import of `_library._fs`, `.decoy` literal or `records.encode` outside `decoy/cli/_library/`; seeded bypass shown red | M-LIB-INLINE |

**Frozen-contract effects.** New on-disk location `.decoy/` (layout 1). No
CLI verb yet.

### L1c-cli: index, fsck, degraded mode (CLI, about 560 lines)

Depends on L1b.

**Files.**
- new `src/decoy/cli/_library/_index.py` (schema, insert, query, rebuild,
  stale marker), `_fsck.py`.
- `src/decoy/cli/library.py` (new command group with `path` and `fsck`),
  `src/decoy/__main__.py` registration, `docs/cli-reference.md` regenerated,
  `docs/library.md`, `CHANGELOG.md`.
- tests: `tests/unit/library/test_index.py`, `test_fsck.py`,
  `tests/e2e/test_library_fsck.py`.

**Behavior.** Sections 4.4, 4.8 (index and degraded mode), 4.10.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| C1-rebuild | delete the index; `list` falls back with a notice; `fsck --repair` rebuilds rows equal to before | MC1-norebuild |
| C1-corrupt-index | random bytes in `index.sqlite`: commands still list via scan, `fsck --repair` fixes it | MC1-crash: propagate the SQLite error |
| C1-lock-unavailable | with SQLite locking forced to fail, `put` succeeds and marks stale; ref set and prune exit with `library_lock_unavailable` | MC1-unlocked-ref: allow refs without the lock |
| C1-fsck-findings | a corrupt object, a dangling ref, a stale temp file and a 0644 file each produce one finding and exit 4 | MC1-silent: skip the hash check |
| C1-repair-safe | `--repair` quarantines the corrupt object, deletes the stale temp, keeps every valid record | MC1-delete: delete instead of quarantine |
| C1-layout-newer | `LAYOUT` 2 makes writes refuse with `library_layout_newer` | MC1-ignore |
| C1-list-speed | 5 000 records list in under 1 second from the index (performance marker, T4) | none (budget check) |

**Frozen-contract effects.** New CLI noun `library` with `path` and `fsck`
(additive). `docs/cli-reference.md` and the surface sentry move.

### L2-cli: scan snapshots on the library (CLI, about 380 lines; replaces SCAN-MULTI S1d)

Depends on L1c and SCAN-MULTI S1c (and so on S1a and S1b released).

**Files.**
- `src/decoy/cli/scan.py`: after a successful scan, `library.put(build(
  "scan-set", scan_set_to_dict(s, detail=False), labels={tables, pipeline},
  ...))`; `--no-save`; `--library DIR`; `scan diff` accepts ids, refs,
  record paths, bare `scan-set/v1` files and `--latest`.
- tests: `tests/e2e/test_scan_library.py`; the scan canary fixture for
  G-KIND-CANARY in `tests/e2e/test_library_canary.py` (new, shared by L3 and
  L5).
- docs, `CHANGELOG.md`.

**How SCAN-MULTI S1d changes.**
- `_scan_library.py` (`save_snapshot`, `load_snapshot`,
  `resolve_library_dir`) is not built. Its jobs move to `Library.put`,
  `Library.resolve` and `_paths.resolve_root`.
- The snapshot location changes from `.decoy/scans/<UTC time>-<12 hex>.json`
  to `.decoy/library/objects/<2>/<62>.json`, and the file holds a
  `decoy-record/v1` envelope whose payload is the same `scan-set/v1` core.
- Immutability and "a same-content rescan still gets a new record" stay: the
  envelope's `created_at` and `invocation_id` change the id;
  `payload_digest` shows the content is unchanged.
- `--library DIR` now names the library root, not a scans directory.
- `scan diff --latest` uses the virtual `latest` ref filtered by the same
  table set, and `latest~1`.
- S1d's G-ONE-SAVER guard is replaced by G-LIB-WRITER and G-KIND-CANARY.
  S1d's T6 tests carry over below with the same intent and mutation names.
- S1d's ~400 lines become L2's ~380, but L2 needs L1a to L1c first.
- S3-cli: `--emit-config` writes `scan_baseline.path` as the object path
  relative to the YAML and also sets the stored ref
  `scan-set/baseline/<pipeline slug>`, so prune keeps it. S3-engine's
  baseline loader (and S3-cli preflight) must read both an envelope-wrapped
  snapshot (detected by `record_schema`) and a bare `scan-set/v1` file; the
  field's `schema: "scan-set/v1"` still names the payload. An optional
  `record_id` member on `scan_baseline` is suggested to S3-engine as an
  additive field so preflight can check the file is the record the YAML
  meant.
- The record stores each column's detector result, with no suggestion when
  no PII is found. The starter YAML renderer maps "no suggestion" to
  `redact` (owner answer to SCAN-MULTI Q9, which reverses S3's planned
  `passthrough` fallback; S3-engine's `_starter_strategies` table and the
  T4-runs passthrough assertion change accordingly). The scan record never
  stores a policy default, so changing that default later does not change
  any record.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L2-saved | a scan writes exactly one `scan-set` record, 0600, and the card and `--json` show its short id and root | M6-mode: default umask |
| L2-no-save | `--no-save` writes nothing under `.decoy/` | M6-ignore |
| L2-value-free | canary fixture: no canary under `.decoy/` after scan | M6-detail: save with `detail=True`; M-PAYLOAD-LEAK |
| L2-atomic | a scan whose last table fails leaves no record and no temp file | M6-early: save before the last table |
| L2-diff-latest | two scans with a column added: `scan diff --latest` reports it | M6-order: oldest two |
| L2-same-content | two scans of unchanged files: two ids, equal `payload_digest` | ML2-dedupe: reuse the first id |
| L2-no-pii-no-suggestion | a column with no detector match is stored with no suggestion, not `redact` or `passthrough` | ML2-policy: store the fallback strategy |
| L2-legacy-file | `scan diff` still accepts two bare `scan-set/v1` files from `--output` | ML2-envelope-only |
| G-KIND-CANARY | `scan-set` has a canary fixture | M-KIND-NOFIX |

**Frozen-contract effects.** The S1d on-disk location is replaced before it
ships (no migration). CLI flags as S1d planned. `scan_baseline` reader change
in S3 (above).

### L3a-cli: evidence and run-result records (CLI, about 520 lines)

Depends on L1c. The run-result half depends on the RESULT row
(`decoy-run-result/v1`, F29 C1); the evidence half does not and may land
first.

**Files.**
- `src/decoy/cli/run.py`: at the end of a run (success or handled failure),
  write the `evidence` record (success path, as today) and the `run-result`
  record, both with the run's `invocation_id`, linked to each other and to
  the scan baseline when the YAML names one; `--no-library`; the card and
  `--json` print the ids; library failure handling per 4.17.
- `src/decoy/cli/evidence.py`: register the `cli-local-1` payload model with
  the engine registry; `build_manifest` unchanged.
- `src/decoy/cli/report.py`: `report show`, `verify` and `diff` also accept
  an id or ref.
- tests: `tests/e2e/test_run_library_records.py`, canary fixtures for
  `evidence` and `run-result`; docs, `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L3-records | a successful run writes one evidence and one run-result record sharing an invocation id and linked both ways | ML3-nolink |
| L3-failed-run | a run that fails at runtime writes a run-result record with status `error` and the exit code, and no evidence record | ML3-evidence-on-fail |
| L3-baseline-link | with `scan_baseline` set, the run-result links to that scan record | ML3-path-only: store the path, not the id |
| L3-evidence-same | the record payload equals the `--evidence-out` file after canonicalization | ML3-drift: build the manifest twice |
| L3-no-library | `--no-library` and `DECOY_LIBRARY=off` write no record under `.decoy/library/` (once L5b lands, the job log is still written) | ML3-ignore |
| L3-readonly | read-only library root: run exits with its normal code, stderr has one warning with the code, `--json` has `library.status = "failed"` | ML3-fail: exit 3 |
| L3-canary | canary fixture: no canary in either record | M-PAYLOAD-LEAK |
| L3-report-id | `decoy report verify <id>` equals `report verify <file>` | ML3-file-only |

**Frozen-contract effects.** `decoy run` gains a default write (4.16) and two
flags; `report` accepts ids (additive). `cli-local-1` shape unchanged.

### L3b-cli: sample-run records and scratch lifecycle (CLI, about 450 lines)

Depends on L1c and the SAMPLE row (`decoy run --sample N` through subset).

**Files.**
- `src/decoy/cli/run.py` (sample path): take the output directory from
  `Library.scratch("sample", ttl)`, write the `sample-run` record, replace the
  previous sample of the same pipeline, run lazy expiry.
- `src/decoy/cli/_library/_scratch.py`: expiry and replace rules.
- tests: `tests/e2e/test_sample_library.py`, the scratch positive control in
  `test_library_canary.py`; docs, `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L3b-scratch-only | after `--sample`, the canary appears under `.decoy/scratch/` and nowhere else under `.decoy/` (the positive control for every canary test) | ML3b-record-rows: copy the first output row into the record |
| L3b-metadata | the record has N, root, per-table counts, approximate columns, file hashes and the relative scratch path | ML3b-abs: absolute path |
| L3b-replace | a second sample of the same pipeline removes the first sample's scratch and keeps both records | ML3b-keep-all |
| L3b-ttl | scratch older than the TTL is removed by the next command; its record then shows "expired" | ML3b-nottl |
| L3b-targets-untouched | targets and vault paths in the YAML are not created or changed by `--sample` | ML3b-target |
| L3b-staging | a failed sample leaves no staging directory | ML3b-leak-staging |

**Frozen-contract effects.** New tag `sample-run/v1` (registered in L1a).

### L4-cli: library commands (CLI, about 720 lines)

Depends on L1c; `diff` for `run-result` needs L3a.

**Files.**
- `src/decoy/cli/library.py`: `list`, `show`, `diff`, `ref`, `prune`,
  `export`, `clean`.
- `src/decoy/cli/_library/_prune.py` (`prune_preview`, `prune_apply`,
  reachability), `_diff.py` (dispatch by kind through the registry).
- `docs/cli-reference.md` regenerated, `docs/library.md`, `CHANGELOG.md`.
- tests: `tests/e2e/test_library_commands.py`,
  `tests/unit/library/test_prune.py`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L4-list | filters by kind, pipeline, table and time; `--json` is stable | ML4-filter |
| L4-show | `show <prefix>` resolves a unique 8-hex prefix and refuses an ambiguous one | ML4-first-match |
| L4-prune-preview | without `--yes`, prune lists exact ids and deletes nothing | ML4-apply: delete on preview |
| L4-prune-reach | a record reachable from a ref or linked from a kept record survives `--keep-last 1` | ML4-noreach |
| L4-prune-grace | a record younger than one hour survives | ML4-nograce |
| L4-prune-concurrent | prune while another process puts records: no new record is deleted and fsck is clean after | ML4-unlocked |
| L4-export-import | export then `records.read_export` gives the same ids; `--ref` exports exactly the reachable set; paths are stripped unless `--keep-paths` | ML4-paths: keep paths by default |
| L4-export-scratch | no export option includes scratch content | ML4-scratch |
| L4-clean | `clean` previews, then with `--yes` removes only `.decoy/scratch/`; a vault file inside the project is untouched | ML4-wide: remove `.decoy/` |
| L4-diff | scan-set, evidence and run-result pairs give the kind-specific diff; mismatched kinds are a usage error | ML4-generic: structural diff for all |

**Frozen-contract effects.** Additive `library` verbs; export format frozen
under `decoy-library-export/v1`.

### L5a-cli: wire the engine ProgressSink into `decoy run` (CLI, about 380 lines)

Depends on L1c. Owns the hook found missing in the first pass: `decoy run`
shows a spinner (`run.py:41`) and passes no `ProgressSink` to the engine
today.

**Files.**
- new `src/decoy/cli/_progress_fanout.py`: a `ProgressSink` that forwards
  each engine event to registered consumers (the terminal progress display
  now, the log writer in L5b), so the engine sees one sink.
- `src/decoy/cli/run.py`: pass the sink on every route `decoy run` uses
  (full-frame, chunked, sequential, out-of-core, sample); replace the bare
  spinner with a display that reads phase and rate events; mint the run's
  `invocation_id` here so L3a records and L5b logs share it.
- `src/decoy/ui/progress.py`: phase and rate rendering on stderr.
- tests: `tests/unit/test_progress_fanout.py`,
  `tests/e2e/test_run_progress_events.py`; `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L5a-every-route | a test consumer receives a terminal event and at least one phase event on each route `decoy run` can take (route forced per case) | ML5a-route: pass the sink on the full-frame route only |
| L5a-order | events reach consumers in emission order with increasing `sequence` | ML5a-buffer: reorder through a set |
| L5a-consumer-fault | a consumer that raises does not change the run's outcome or exit code; the failure is counted, not retried | ML5a-propagate: let the consumer error escape |
| L5a-quiet-json | `--quiet` and `--json` keep stdout free of progress; events still reach non-display consumers | ML5a-stdout |
| L5a-no-value | events carry only engine-sanitized fields (the canary fixture produces no canary in any event dict) | ML5a-wrap: add a CLI message field |

**Frozen-contract effects.** None persisted. stderr progress text changes
(not a contract).

### L5b-cli: job logs (CLI, about 500 lines)

Depends on L5a and L3a (the run-result link).

**Files.**
- new `src/decoy/cli/_library/_logs.py` (writer as an L5a consumer,
  rotation, reader).
- `src/decoy/cli/run.py` and multi-table `scan.py`: register the log writer
  on every run; CLI-side events built from engine event classes.
- `src/decoy/cli/library.py`: `show --log`.
- tests: `tests/e2e/test_job_logs.py`, log canary in
  `test_library_canary.py`; docs, `CHANGELOG.md`.

**Acceptance tests and named mutations.**

| Test | Asserts | Mutation |
|---|---|---|
| L5-written | a run writes one log with the header and a terminal event; the run-result links to it with a matching hash | ML5-nolink |
| L5-always | `--no-library` and `DECOY_LIBRARY=off` still write the log; only an unwritable root skips it, with one warning and `log.status = "failed"` in `--json` | ML5-optout: honor `--no-library` for the log |
| L5-value-free | canary fixture, including a failure whose exception text quotes a cell: no canary in the log, and the terminal line has the class name only | M-LOG-MSG |
| L5-verbose | `--verbose` traceback appears on stderr and not in the log | ML5-tee: copy stderr into the log |
| L5-truncated | a run killed mid-way leaves a log whose complete lines parse; readers skip the partial last line | ML5-strict: fail on a partial line |
| L5-rotate | with 52 logs for one pipeline, the next run leaves 50, never removing a log linked from a ref-protected record | ML5-noprotect |
| L5-age | logs older than `max_age_days` are rotated | ML5-noage |
| L5-tail | `library show <run> --log` prints the events in order and says if the hash no longer matches | ML5-nohash |

**Frozen-contract effects.** New tag `decoy-job-log/v1` (registered in L1a);
log lines are the engine's frozen event schema.

### Totals

| Slice | Repo | Lines (est.) | Depends on |
|---|---|---|---|
| L1a-engine | engine | ~520 | none |
| L1b-cli | CLI | ~700 | L1a release and repin; Windows runner provisioned |
| L1c-cli | CLI | ~560 | L1b |
| L2-cli | CLI | ~380 | L1c, SCAN-MULTI S1c (replaces S1d) |
| L3a-cli | CLI | ~520 | L1c; RESULT for the run-result half |
| L3b-cli | CLI | ~450 | L1c, SAMPLE |
| L4-cli | CLI | ~720 | L1c (L3a for run-result diff) |
| L5a-cli | CLI | ~380 | L1c |
| L5b-cli | CLI | ~500 | L5a, L3a |

Each slice is under 800 hand-written lines including tests. Logging per
slice: one operational line per library write failure and per prune or clean
(counts, kind, error class; never a path's contents or a value), plus the job
log itself in L5.

## 6. Owner questions

All eight questions are answered; see Revision 2 at the top. The original
text is kept below for the record.

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
