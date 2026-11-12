# The local record library

Decoy keeps small, value-free records about your pipelines (scan snapshots, run results,
evidence manifests, sample-run metadata) in one library per project. This page describes what
exists so far. No command writes to the library yet, and there is no `decoy library` command
yet; the scan and run commands start using it in later releases.

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
    index.sqlite        the library lock (the index arrives later); not committed
    tmp/                temp files for atomic writes
```

Decoy never edits an existing `.gitignore` or `.gitattributes`. A library root not named
`.decoy` (a `--library` folder on a mounted volume, for example) gets neither file.

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

The newest record of a kind is computed, not stored as a ref; that arrives with the index.

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
64 KiB, owned by you; one another user owns is refused with `library_policy_untrusted`. Nothing
applies the policy yet: prune and log rotation arrive later.

## File modes

On Linux and macOS every file the library creates (records, refs, the lock file) is 0600 and every folder it creates is 0700.
A folder that already existed (your project folder, or a `.decoy/` you made) keeps its mode. On
Windows the files and folders inherit the project folder's permissions.
