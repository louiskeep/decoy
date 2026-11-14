# Project layout

Status: current

A Decoy project is one folder, recommended per client. Pipelines, their outputs and the local
record library live inside it, so one client's work can be handed over, archived or deleted as
one folder. Names are unique per project only.

```text
acme/
  decoy.yaml                      the project marker (kind: decoy-project/v1)
  pipelines/
    members-mask/pipeline.yaml    one folder per pipeline; the folder name is the pipeline name
  out/
    .gitignore                    holds `*`: outputs can contain row values
    members-mask/
      PIPELINE                    the YAML this name belongs to
      LATEST                      the newest clean run id
      current -> <run-id>         a link to it (not on Windows)
      <run-id>/members.masked.csv one run's outputs, mode 0700
  .decoy/                         records, job logs and scratch (git-ignored where needed)
```

## Make a project and a pipeline

```console
$ decoy project new acme
$ cd acme
$ decoy init members-mask --source ~/data/members.csv
$ decoy run members-mask
```

`decoy project new DIR` makes the folder, the marker, `pipelines/`, `out/` and `.decoy/`. Run it
again and it fills in only what is missing. It refuses your home folder, a parent of it and `/`.

`decoy init NAME [--source FILE] [--preset P]` writes `pipelines/NAME/pipeline.yaml`:

- `NAME` follows the pipeline name rule: 1 to 64 letters, digits, `_`, `.` or `-`, starting with
  a letter or digit. An invalid name exits 1 with `layout.pipeline_name_invalid`.
- An existing file as the first argument is the source, and the pipeline is named after its file
  stem: `decoy init data.csv` writes `pipelines/data/pipeline.yaml`.
- The source path is written relative to the pipeline's folder when the file is inside the
  project (`../../data/members.csv`), and as an absolute path when it is not.
- The target is the bare file name `<stem>.masked.<ext>`. `run` places it in the run folder, so
  the YAML holds no output path to edit.
- No `name:` key is written. The folder is the name.
- An existing `pipeline.yaml` is replaced only with `--yes`; `--json` and `--quiet` refuse
  without it.
- With no argument inside a project, the wizard asks for the name, then the preset and paths.
  `--json` and `--quiet` cannot ask, so they exit 1.

`decoy --project DIR init ...` and `DECOY_PROJECT` pick a project without `cd`.

### Outside a project

`init` never turns the folder you stand in into a project. Without `-o` it exits 1 with
`layout.project_not_found` before it reads a file or asks a question. Run `decoy project new .`
first, or write a file of your choice:

```console
$ decoy init data.csv -o sub/p.yaml    # source written as ../data.csv, target data.masked.csv
$ decoy init data.csv -o -             # YAML on stdout, nothing written
```

`-o FILE` works anywhere, in or outside a project. The source path is relative to `FILE`'s
folder, so `decoy run sub/p.yaml` finds it. Without a marker above it, the folder of `FILE` acts
as the project root for its outputs (`sub/out/p/<run-id>/`).

## Where a run writes

A relative or bare target path in a pipeline goes to `out/<name>/<run-id>/`. The run summary and
`--json` name the folder. A run that exits 0 moves `LATEST` and `current` to it. A target that
should land elsewhere has three ways out:

- an absolute path in the YAML, honored as written, for delivery to a fixed place;
- `out/<name>/current/<file>` (or the run id) to read a result back;
- `decoy run --out-dir DIR`, one fixed folder for every output of that run.

See `docs/ci-contracts.md` for the evidence manifest paths and `decoy explain` for the exit codes.
