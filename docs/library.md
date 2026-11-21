# The local record library

Decoy keeps small, value-free records about your pipelines (scan snapshots, run results,
evidence manifests, sample-run metadata) in one library per project. This page describes what
exists so far. `decoy run` stores its evidence and run-result records (below); scan and sample
records arrive in later releases. `decoy library path`, `fsck`, `list`, `show`, `diff` and `ref`
read, check and name what is there.

Code: `src/decoy/cli/library/`. Plan: `plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`.

## Where the library lives

The first rule that applies wins:

1. `--library DIR`: the library is `DIR`.
2. `DECOY_LIBRARY=DIR`: the library is `DIR`. `DECOY_LIBRARY=off` turns records off for the
   process; the job log still goes to the root the next rule gives.
3. The project's `.decoy/` folder. The project is the nearest folder holding a `decoy.yaml` with
   `kind: decoy-project/v1`, searched upward from the pipeline YAML's folder for `decoy run`, or
   from the `--emit-config` folder, then the `--config` folder, for `decoy scan`. With neither,
   the search starts in the current folder. `--project` or `DECOY_PROJECT` names the project
   directly. With no marker, the start folder is the project. The search stops after a folder
   holding `.git`, at a filesystem change, and before your home folder.

So `decoy scan data/*.csv --emit-config out/p.yaml` and `decoy run out/p.yaml` share one
library.

On Windows a library root longer than 150 characters is refused with `library_path_too_long`
before anything is written, so the deepest record path stays under the 260-character limit.
Use `--library` with a shorter path.

## Layout

```
.decoy/
  .gitignore            written once if absent: scratch/, logs/, library/index.sqlite,
                        library/tmp/, library/quarantine/
  .gitattributes        written once if absent: library/objects/** -text
  library.yaml          optional retention policy; absent means the defaults below
  library/
    LAYOUT              {"layout":1}
    objects/ab/cdef...json   one immutable record per file, named by its id
    refs/<kind>/<name>  one line: a record id
    index.sqlite        the index (a rebuildable cache) and the library lock; not committed
    tmp/                temp files for atomic writes
    quarantine/         records `fsck --repair` found corrupt (moved here, never deleted)
  scratch/              the only place Decoy keeps rows (sample output, staging); never committed
```

Decoy never edits an existing `.gitignore` or `.gitattributes`. A library root with another name
(a `--library` folder, for example) gets the same two files in that folder, also only if absent,
so scratch rows under it are never committed. A `.gitignore` Decoy cannot write is a warning.

A record id is `sha256:` plus the SHA-256 of the record's canonical JSON without its `id` field.
The check parses the file before hashing, so a copy with CRLF line endings or different
indentation is still the same record. Any unique prefix of 8 or more hex digits names a record.

## How records are written

- A record is written to a temp file in `library/tmp/`, flushed to disk, and linked to its final
  name without ever replacing a file. A reader sees a whole record or none. A crash can leave a
  temp file, never a partial record.
- Writing a record that is already stored is success. If the stored file holds different
  content under that id, the write fails with `record_corrupt` and the file is left as it is.
- A record may link only to records already in the library; otherwise the write fails with
  `record_link_missing` and nothing is written.
- Two Decoy processes may write records to one library at once; record writes take no lock.
- A library whose `LAYOUT` names a version this Decoy does not write refuses writes with
  `library_layout_newer`.

## What `decoy run` stores

A successful `decoy run` stores one `evidence` record: the same manifest `--evidence-out` writes,
built once and stored as built, so the record's payload equals that file. It is stored whether or
not `--evidence-out` is given. The record carries the run's invocation id (the manifest's
`run_id`), the pipeline (the YAML's path from the project root, what `library list --pipeline`
matches) and the target table names. A failed run, a `--rows` preview and a `--duckdb-source` run
store no evidence record.

The run also stores one `run-result` record: the document that is the `result` member of `--json`,
built once. It has the same invocation id and links to the evidence record (the evidence links to
nothing; `library list` and the index find the result from the evidence). A run that failed after it
started stores a `run-result` with status `failed` and no evidence record; a refusal before the run
starts, such as a bad option, stores nothing.

- `--no-library`, or `DECOY_LIBRARY=off`, stores nothing for that run.
- The run card names the record and the library root; `--json` has a `library` object:
  `{"status": "stored", "root": ..., "evidence": <id>, "result": <id>}`, `{"status": "skipped"}`, or
  `{"status": "failed", "root": ..., "code": ...}`.
- A library that cannot be written does not fail the run: stderr gets one warning with the code,
  `--json` says `failed`, and the exit code is the run's own (a delivered run is never reported
  as failed, so an orchestrator does not deliver twice).

A run never writes an output onto the library root. The gate lists every file the run writes
(targets, quarantine, the post-scan report, `--result`, `--evidence-out`, `--vault`, and the
project run folder's own files) and refuses the run before anything is written when one of them
is the root, sits inside it, or holds it, even through a link: `layout.output_path_collision`
with `the record library` as the first party, exit 1. A library root that cannot be resolved
(a link loop, a NUL byte) is `library_path_unsafe`: the run delivers its outputs, stores no
record, warns once and keeps its own exit code, and `--json` says `library.status: failed`.
`decoy library` commands report the same fault as a coded error with exit 3.

Paths in the record are what the manifest holds: project-relative inside a `decoy.yaml` project,
absolute otherwise. `export` reduces them to file names unless `--keep-paths` is given.

## How records are read

Reading a record by its full id parses the file and checks it by the id rule above, so a CRLF
or re-indented copy still reads. A file that holds another record (or no record) under the id
fails with `record_corrupt`; an id that is not stored fails with `record_not_found`. A record
of a kind this Decoy does not know is returned as an opaque record (kind, id, time, labels and
links, payload unread); one written under a newer payload or envelope version is reported as
needing a newer Decoy.

Every library file is read through the CLI's one small-file reader (`decoy.cli.io.read_small_file`).
A symlink, FIFO, device or a file swapped between the check and the open is refused with
`library_read_failed` and never followed or waited on. A record file over 16 MiB is refused with
`library_file_too_large`, and a record that large is never written.

No library operation follows a link out of the library. Every path below the library root is
checked one folder at a time: a symlink, a Windows junction, a file or a pipe where a folder
should be is refused with `library_path_unsafe` before anything is read, written or removed. A
link inside a folder Decoy deletes is removed as an entry; its target is never touched.

Errors name a code and an error class, never a path.

## Refs

A ref is a name for a record: `library/refs/<kind>/<name>` holds one record id. The kind is a
record kind Decoy knows (`scan-set`, `evidence`, ...). A name is 1 to 64 characters of lower-case
letters, digits, `.`, `_` and `-`, starting with a letter or digit; one `/` is allowed for a
pipeline scope (`claims/baseline`). Anything else is refused with `ref_name_invalid`. The one-part
name `baseline` is refused with `ref_name_reserved`: it is the scope of `scan-set/baseline/<slug>`.
A ref can only point at a stored record (`record_not_found` otherwise). A ref file is read through
the same safe reader as records, capped at 128 bytes.

Moving a ref takes the library lock, a SQLite lock on `library/index.sqlite`, which works the
same on Linux, macOS and Windows. A second process that wants to move a ref waits up to 5
seconds and then fails with `library_busy`; it never overwrites silently. If the lock cannot be
taken at all (the file cannot be opened), the update fails with `library_lock_unavailable`. On
Windows, a ref file another program holds open is retried for about a second, then
`library_busy`; any other write failure, a permission denial included, is `library_write_failed`.
Record writes never take the lock.

The newest record of a kind (`latest`) is computed from the index, not stored as a ref: the
record with the largest creation time (then id), optionally for one pipeline or table.

## The index

`library/index.sqlite` lists every record's kind, time, pipeline, tables, status and links, so
listing never opens a record file. It is a cache: the object files are the truth.

- Every open compares the index with the object file names (no file is read) and catches up:
  records added by hand or by `git pull`, records whose writer crashed before indexing them, and
  files deleted by hand. A missing, corrupt or older-version index, or one with a table
  missing, is rebuilt from the files. A corrupt index is emptied in place, never replaced, so
  the library lock (held on that file) stays one lock for every process.
- If the index fails while it is being updated (a full disk, a corrupt page), writing the record
  still succeeds and listings read the record files; the next open catches the index up.
- A record of a kind this Decoy does not know is indexed and listed as unknown; it never stops
  the listing.
- If the index cannot be locked, or the library is on a network filesystem (NFS, SMB/CIFS, AFS,
  9P or FUSE on Linux; `nfs`, `smbfs`, `afpfs` or `webdav` on macOS; a UNC path or network
  drive on Windows), the library runs in degraded mode: writing records still works, moving a
  ref fails with `library_lock_unavailable`, and listings read the record files. A synced folder
  (OneDrive, Dropbox) looks local and is not detected; use it from one machine at a time.

## Reading the library

All of these take `--library DIR`. Every `decoy library` command (`path` and `fsck` included)
reports an error the same way: `error: [code] message` on stderr, or one error object on stdout
under `--json`, with exit 1 for what you typed (an unknown or ambiguous id, a bad ref name, a
ref to a record of another kind) and exit 3 for the library's own state (degraded mode, a
corrupt record, a linked folder).

- `decoy library list [--kind K] [--pipeline P] [--table T] [--since D] [--json]` lists records
  oldest first from the index, without opening record files. `--since` takes `YYYY-MM-DD` or an
  ISO time (UTC unless it says otherwise). A record of a kind this Decoy does not know is listed
  as `unknown kind <name>, needs a newer Decoy`, and `--kind <name>` still finds it.
  `--pipeline P` takes a pipeline the way every other command does: its name in the project
  (`claims` for `pipelines/claims/pipeline.yaml`) or the path to its YAML. It lists the records
  whose `pipeline` label is that YAML's path relative to the project root (relative to the YAML's
  own folder when there is no `decoy.yaml` marker), so a name, a path and a path typed from a
  subfolder select the same records. An unknown name is a usage error (`layout.pipeline_unknown`,
  exit 1) that lists the project's pipelines. With `--pipeline`, the library is the one of that
  pipeline's project unless `--library` or `DECOY_LIBRARY` says otherwise.
- `decoy library show ID|REF [--json]` prints the envelope (id, kind, schema, time, invocation,
  producer, labels, links) and, when this Decoy can read it, the payload.
- `decoy library diff A B [--json]` compares two records of the same kind. Scan records use the
  `decoy scan diff` rules per table; evidence records use the `decoy report diff` manifest
  comparison (warnings as codes); run results compare status, route, delivery and, per table,
  outcome, rows out and delivery; other kinds list the payload fields that changed, were added or
  were removed (paths only). Records of different kinds, or of a kind or version this Decoy
  cannot read, are refused.
- `decoy library ref KIND/NAME [ID]` prints a stored ref, or sets it under the library lock.
  A ref points only at a record of its own kind: setting `scan-set/main` to an evidence record,
  or reading a committed ref that names one, is `ref_kind_mismatch`. A ref path through a
  linked folder is refused (`library_path_unsafe`) for reads and writes alike.

Wherever a record is named you can give:

- the full id (`sha256:...`) or any unique prefix of 8 or more hex digits (an ambiguous prefix
  is refused, never resolved to the first match);
- a stored ref, `KIND/NAME` or `KIND/SCOPE/NAME`;
- `KIND/latest`, the newest record of that kind, or `KIND/latest~N`, the N-th before it. `latest`
  is computed, so it cannot be the name of a stored ref.

## Pruning records and cleaning scratch

Both commands show exactly what they would delete and delete nothing until you add `--yes`. All
take `--library DIR`.

- `decoy library prune [--kind K] [--keep-last N] [--older-than D] [--yes]` deletes records you
  no longer keep: beyond the newest `N` of each kind, and/or older than `D` (`90d`, `12h`, `30m`).
  With no options it applies the `keep_last` rules in `.decoy/library.yaml`; the default policy
  keeps every record. It never deletes:
  - a record a ref points at, or any record a kept record links to (directly or through others);
  - a record younger than one hour (one a running command may still be linking to);
  - a record of a kind this Decoy does not know, or one written by a newer Decoy; their links
    still protect what they point at.

  Prune first accounts for every ref and record file. If one cannot be read (a ref it cannot
  parse, a record file with no index row, a link among them), it cannot know what that entry
  protects: the preview says how many such entries there are and `--yes` refuses with
  `library_unexplained_entries` (exit 3) until `decoy library fsck` explains or repairs them. A
  ref may start with a byte order mark.
- `decoy library clean [--yes]` deletes everything in `.decoy/scratch/` (sample output and
  staging). It never touches records, logs, or anything outside the library: vault files, keys,
  targets and `out/` run folders stay. A link in scratch is removed as an entry; a `scratch/`
  that is itself a link is refused.

Neither command deletes through a linked `library/`, `objects/` or `scratch/` folder: that is
`library_path_unsafe` (exit 3) and nothing is deleted.

Both work under the library lock and refuse in degraded mode (`library_lock_unavailable`, exit
3). A file another program holds open (on Windows) is listed as left behind, the rest is
deleted, and the command exits 4; run it again once the file is closed.

## Exporting

`decoy library export --output FILE [--kind K] [--since D] [--ref R] [--include-logs] [--keep-paths]`
writes one self-verifying JSON Lines file (`decoy-library-export/v1`) that the platform can
import. The file is 0600. `--ref R` exports R (a ref, an id or `KIND/latest`) and every record it
links to; `--kind` and `--since` choose the records an export starts from and cannot be
combined with `--ref`. **An export is always closed**: every record a chosen record links to,
directly or through others, is exported too, whatever its kind or date. Nothing under `scratch/` is ever exported. The output may not be a file inside
`library/` or `scratch/`, or a symlink (`export_destination_unsafe`, exit 1). Like prune, export
refuses with `library_unexplained_entries` while any ref or record file cannot be accounted for
(for example a record written in a newer envelope format), or while a ref or a link names a
record that is not in the library, rather than write a file that is incomplete or not closed.

By default an export carries no raw path: each record's declared path fields are reduced to file
names, which gives that record a new id, and the line names the original id as `source_id`; links
and refs point at the new ids. **A default export withholds the records this Decoy cannot strip**:
a record of a kind it does not know, or one written by a newer Decoy with payload fields it does
not know. They are left out, listed by id in the header's `withheld_records`, and counted in a
notice on stderr. A record that links to a withheld record, directly or through others, is
withheld too (so the file stays closed): it is listed in `withheld_records` as well, named in its
own stderr notice, and a ref to it is left out of the header. Export never writes a file whose
records link outside it; if one would, it refuses with `export_not_closed` and writes nothing. To
include them all, rerun with `--keep-paths`: every record is then exported byte for byte, paths
included, with its original id.

`--include-logs` is accepted, but no job logs exist yet (they arrive with `decoy run` job logs),
so none is exported.

## Retention policy

`.decoy/library.yaml` is optional. Without it, these defaults apply:

```yaml
retention:
  records:
    default: {keep: all}
    # per kind, for example: run-result: {keep_last: 500}
  logs: {keep_last_runs_per_pipeline: 50, max_age_days: 30}
  scratch: {sample_ttl_hours: 24, staging: delete_on_exit}
```

Keys you leave out keep their defaults. An unknown key, a kind Decoy does not know, a number
written as text, or a count below 1 makes the file invalid (`library_policy_invalid`, naming the
field, never its value). The file is read like the project marker: a regular file of at most
64 KiB, owned by you; one another user owns is refused with `library_policy_untrusted`.
`decoy library prune` with no options applies the record rules; log rotation and the scratch
time limit arrive with job logs and `decoy run --sample`.

## Commands

`decoy library path [--library DIR]` prints the library root, where it came from (`--library`,
`DECOY_LIBRARY` or the project), whether records are on, and whether the library runs in
degraded mode and why. It creates nothing.

`decoy library fsck [--repair] [--library DIR]` checks, without changing anything:

- every record's id (the file is parsed first, so a CRLF or re-indented copy passes), its
  envelope and its payload; a record of a kind this Decoy does not know is checked by id only;
- every ref points at a stored record; links to missing records are warnings;
- the index matches the record files;
- no temp file in `library/tmp/` is older than an hour;
- on Linux and macOS, the index, `tmp/`, `scratch/` and `logs/` are private (a finding);
  records and refs that git checked out 0644 get a note only;
- job log lines parse (a truncated last line is a warning);
- no library folder is a link (`path_linked`); fsck reports the link and never looks inside it;
- the index is a regular file (`index_not_file`: a pipe there is never opened).

An entry fsck cannot read is its own finding and the check goes on: `layout_unreadable` (fsck
then stops, and repair changes nothing), `object_unreadable` (a record file or fan folder),
`ref_unreadable` and `log_unreadable`. A ref may start with a byte order mark.

Each problem prints one line: `finding`, `warning` or `note`, a code (`object_corrupt`,
`payload_invalid`, `ref_dangling`, `index_stale`, `temp_stale`, `mode_open`, ...) and the path
inside the library. Exit 0 when there are no findings, 4 when there are.

`--repair` copies each corrupt record into `library/quarantine/` and then removes it, deletes
stale temp files, removes refs to missing records (printing each) and rebuilds the index. Under
the library lock it reads each corrupt record again and moves it only if it still does not
parse or its content is not the record its name says; a record it cannot read is never moved.
A ref is removed only when it was read, holds a record id, and that record is not stored. If
one entry cannot be moved or deleted, repair prints `quarantine_failed` or
`temp_delete_failed` for it and goes on. It
never deletes a valid record, and it changes nothing in a library whose `LAYOUT` is newer than
this Decoy, nothing under a linked folder, and no entry that was replaced after the check.

## Scratch

`.decoy/scratch/` is the only part of the library that may hold rows: sample output and staging.
Decoy's engine creates it and every folder in it owner-only from the first moment (0700 on Linux
and macOS; on Windows a protected access list for you and SYSTEM). Each command checks it again:
an empty `scratch/` that is open to others is tightened, and one that is open to others and
already holds files is refused (`scratch_unsafe`), because those files may have been read. If
the protection cannot be applied, the command stops before it writes any row
(`scratch_acl_failed`) and leaves no folder behind.

- Staging folders (`<owner>-<invocation id>-<random>`) are deleted when their command finishes,
  whether it succeeded or failed.
- Sample output (`<owner>-<invocation id>`) stays until its time limit (24 hours by default,
  `retention.scratch.sample_ttl_hours`); removing expired output arrives with `decoy run --sample`.
- Deletes go file by file. A file another program has open (on Windows, a sample open in Excel)
  is skipped and reported with `library_delete_skipped`, and the next cleanup removes it.
- A `scratch/` that is a link, or a link on the way to the folder being deleted, is refused with
  `library_path_unsafe` and nothing is deleted. A link inside a scratch folder is removed as an
  entry; whatever it points at is never touched.

The library's `.gitignore` ignores `scratch/`, in `.decoy/` and in any `--library` folder.

## File modes

On Linux and macOS every file the library creates (records, refs, the lock file) is 0600 and every folder it creates is 0700.
A folder that already existed (your project folder, or a `.decoy/` you made) keeps its mode. On
Windows the files and folders inherit the project folder's permissions.
