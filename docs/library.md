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
  library/
    LAYOUT              {"layout":1}
    objects/ab/cdef...json   one immutable record per file, named by its id
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

Errors name a code and an error class, never a path.

## File modes

On Linux and macOS every file the library creates is 0600 and every folder it creates is 0700.
A folder that already existed (your project folder, or a `.decoy/` you made) keeps its mode. On
Windows the files and folders inherit the project folder's permissions.
