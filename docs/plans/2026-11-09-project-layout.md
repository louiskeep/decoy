Status: plan

# PROJECT-LAYOUT: projects, pipelines by name, and one run folder per run (roadmap row 24t)

Owner: Cam. Author: claudeworkerbee (Opus). Date: 2026-11-09. Scope: CLI plus a small engine part, V1.
Revision 5 (Dennis rounds 1 and 2, Codex r1, addenda T0247, T0248 and T0249, and the P4 final-gate
remediation folded).

Repo and branch: CLI `louiskeep/decoy`, plan branch `plan/project-layout` at `0f91bbcf`, off `main`
`ed5de4ed`. Code was checked against `origin/main` `31faa020`. Engine code was checked against
`louiskeep/decoy-engine` `origin/main` `046887e9`.

Rules consulted: `dev-rules/README.md`, `00-universal.md`, `risk-and-exceptions.md`, `development-loop.md`
(PLAN: choke point, Placement, Design notes, Established solutions), `feature-dev.md`, `architecture.md`,
`reuse-first.md`, `exploration.md`, `bugfix.md`, `verification.md`, `code-review.md`, `testing.md` (test depth, escalation triggers), `cross-cutting-concerns.md`,
`api-and-compatibility.md`, `security.md`, `workspace-and-vcs.md`, `scope-discipline.md`, `documentation.md`,
`catalogs/recurring-defects.md`; the plan contract (`30_Resources/Decoy-Plan-Contract-and-Defect-Catalog.md`),
`LOCAL-BUILDER-BRIEF.md`; the standing rules develop-correctly-registries-and-sizing and
best-practice-becomes-a-sentry; the V1 bar (function break, data loss or a non-admin value leak blocks; a
second copy of a central mechanism, or a new module in a flat folder over 25, always blocks); CLI
`CODEMAP.md:50` (new readers and writers go in `src/decoy/cli/io/`; `cli/` is frozen at 32 modules),
`:59-60` (new tests go in named folders). Code read at CLI `ed5de4ed` and engine `44d6afe2`.
P4 remediation was checked against CLI PR #213 head `845d93a5d77b63e877c06e144c2d3820a680bd2e`.

Source: the owner, 2026-11-09: "Decoy should sort records and files somewhere automatically in the project
folder, we don't want loose files out of their own pipeline folders." Roadmap row 24t (CLI
`docs/ROADMAP.md:264`), extended the same day: run pipelines by name from anywhere in the project (T0247),
one project per client with `--project` and `DECOY_PROJECT` (T0248), `decoy init` creates pipelines and
`decoy project new` creates projects, judged against a user walk-through (T0249). Related: row 24o GEN-CLI
(`:259`), the LIB plan (branch `plan/local-record-library`, `docs/plans/2026-11-05-local-record-library.md`,
retention classes and 4.1), the INIT-WIZARD phase 1a plan (`docs/plans/2026-11-08-init-wizard-phase-1a.md`),
and the first-user QA record (`docs/records/2026-11-08-cli-qa-first-user.md` items 9 and 12).

## 0. Revision 2 dispositions

| Item | Disposition |
|---|---|
| Dennis H1 `mask()` | `mask()` places through `RunLayout.fixed(...)`: `out=` relative to the current folder, like a typed `--output`; without `out=`, today's base (the config folder, or the current folder for a dict). No claim, no `latest`, no `out/.gitignore`, no name for a dict. AT-3 cells added. Owner question Q9 |
| H2 evidence | Placed and in-project paths are recorded project-relative (POSIX) with a new manifest field `path_base: project`; one manifest-aware `resolve_manifest_path` is used by `read_manifest`, `report show`, `report render`, `report verify`, `report diff` and `ci check`, and a sentry rejects direct path construction by any consumer. Old manifests keep the current-folder rule of `docs/ci-contracts.md`. AT-9 runs every consumer from outside the project. |
| H3 name rule | Only an invalid declared `name:` is refused. An undeclared name is a safe slug of the stem, plus a short path hash when the slug had to change or its claim is taken. `pipelines/<dir>/pipeline.yaml` takes `<dir>` (T0247). Name and claim checks run only when the config has a placed output |
| H4 trust | Mode check dropped. Owner check kept, made with `fstat` on the marker opened with `O_NOFOLLOW` |
| H5 claim | Superseded by Codex r1. `_private_file.create_exclusive` only makes random staging names. Claims and the marker use `_atomic.write_atomic(..., CREATE_ONCE)`. Hidden `.gitignore` files use `write_local_target(..., CREATE_ONCE)`. On a mount without hard links the run exits 3 naming the mount. |
| H6 symlink swap | `distribution/layout.py:139-157` moves onto the new `_atomic.replace_symlink`; the G-ONE-ATOMIC-WRITER allowlist shrinks by one (`tests/sentry/test_atomic_writer.py:66-70`). Own slice P1a |
| H7 `owning_run` | Lands in slice P2a, before any writer moves; it accepts the old YAML-folder path and a run folder |
| H8 engine test place | Engine tests go in `tests/unit/internal/` and `tests/unit/config/`, not the flat `tests/unit/` (73 modules) |
| M1 counts | Slice file lists recounted; the four tests whose writer signatures change are named in P2b; Codex r1 derives CI gate codes from the central layout registry. |
| M2 quarantine | Quarantine is hashed (`plan/_compile.py:639` excludes only sources, targets, pre_scan), so the placed path goes to the engine as a new `run_pipeline(..., quarantine_path=...)` keyword (E2), not into the config. AT-10 cells per route |
| M3 `.gitignore` | `out/.gitignore` is created when absent on every run folder open, not only when Decoy made `out/`. A YAML under `out/` warns `layout.config_inside_out` |
| M4 invocation id | One mint function `mint_invocation_id()` in `cli/io/_layout.py`, slice P2b; evidence and LIB take its value (LIB-A) |
| M5 walk limits | The walk stops below `$HOME`, at a `.git` folder or file, and at a device change. An untrusted marker refuses (exit 1) instead of being skipped. `decoy project new` refuses `$HOME`, an ancestor of it, and `/` |
| M6 init scaffold | Scaffold code in `cli/project/_scaffold.py`, not `init.py`; P7 coordinates with the INIT-WIZARD lane; W1a's collision check uses placed paths |
| M7 path budget | The 259-character budget applies on Windows only; Codex r1 updates the longest run id to 55 characters. |
| M8 empty outputs | `outputs[]` lists only files written and is omitted when none were published; `latest` moves on exit 0 even when a chunked target wrote nothing |
| M9 `--out-dir` and `owning_run` | Documented gap: files under `--out-dir` are not recognized by `owning_run`; `unmask` and `detokenize` there use the suffix rule, as for any other path (F6) |
| M10 engine log | E2 makes the engine's default log file `None`; the CLI adds no call. `ci/engine_logging.py` drops its `chdir` |
| L1 sentry scope | Sentry (b) checks path-building calls only (`with_suffix`, `/` joins, f-strings passed to `Path`); sentry (a) follows the `_resolve_path` import alias (`run.py:31`) |
| L2 `latest` order | `commit_latest` moves `LATEST` only when the new run id sorts after the current one |
| L3 codes | One name-invalid code; `layout.latest_*` and `layout.gitignore_write_failed` are runtime warnings, not gate findings |
| L4 Windows `latest` | Documented gap: Windows gets `LATEST` only (F5) |
| L5 demo | Demo targets are already absolute (`demo.py:116`, `:496`); they stay; guarantee 7 names the demo folder |
| L6 tokenize | `tokenize` targets use run folders like `run` (Q10) |
| L7 LIB class 4 | LIB-A also amends LIB's class-4 row: run folders under `out/` are class 4 |
| L8 empty target | A target path `""`, `.` or one ending in a separator is refused with `layout.output_path_escapes` |
| T0247 | Sections 3.4 (pipeline argument), 3.12 (`run` with no argument, `--all`), 3.13 (completion), the name rule in 3.5; AT-18 to AT-22 |
| T0248 | Sections 3.2 (marker), 3.3 (project selection), 3.11 (`decoy project`); one project per client recommended (3.11); AT-23 to AT-25 |
| T0249 | `decoy init` makes pipelines (3.10); `decoy project new` makes projects (3.11); walk-through (section 4); command map (section 5); AT-26 |

Dennis round 2 (NO-GO, 2 blocking, 5 high; last Dennis round):

| Item | Disposition |
|---|---|
| R2-B1 claim helper | Verified and corrected by Codex r1: the `_atomic` `CREATE_ONCE` link publishes complete bytes. It now serves the claim, marker and hidden files directly. No `write_if_absent` race and no new create primitive. |
| R2-B2 `pipelines/` names unclaimed | Every placed run writes the claim, `pipelines/` runs included. A step-2 or step-3 name equal to an existing `pipelines/<name>/` folder is taken (declared: refuse; derived: hash suffix). A `pipelines/` run that finds a claim naming another YAML exits 1 `layout.pipeline_name_collision`. AT-7 cells for both orders |
| R2-H1 walk-through `unmask` | The step needed a vault, an fpe column and a mask secret the scaffold does not make. Replaced by `report fidelity` on the `latest` output, which shows report placement; `unmask` stays in the command map and AT-11 |
| R2-H2 command list | `explain` dropped (it takes a topic, `explain.py:580-585`); default `decoy validate CONFIG` (`validate.py:254`) and `validate preflight` (`preflight.py:624`) added; `cli/preflight.py` added to P5 |
| R2-H3 errors in `convert()` | `convert` only splits the token (a path-shaped token that does not exist fails there, exit 2, today's behavior). Name lookup moves to `resolve_pipeline(token, ctx, state)`, called first in each command body after output setup, so `layout.*` refusals exit 1 with the `--json` envelope. The sentry checks the call |
| R2-H4 ambient `DECOY_PROJECT` in verify | Dropped from manifest resolution. Paths are project-relative only for marker projects; an implicit project records absolute paths |
| R2-H5 `run --all` exit code | A child code outside 0 to 5, a negative code (signal), or a child whose `--json` does not parse counts as 3 |
| R2-M1 Typer's vendored Click | Superseded by Codex r1. Public Typer callbacks and `typer.models.CompletionItem` meet the same token and completion contract without a private-module import. |
| R2-M2 completion source | `pipeline_names(ctx, incomplete)` lives in `cli/completers.py`; the type calls it |
| R2-M3 quarantine routes | Verified and simplified by Codex r1. After the original config builds and hashes the context, `run_pipeline` replaces only `ctx.config` with one copied effective config before route selection. All routes already read the context. AT-10 covers each route. |
| R2-M4 generated reference | `docs/cli-reference.md` is regenerated in P5, P6, P7 and P8 (`tests/unit/test_cli_surface.py:38` drift test) |
| R2-M5 token rules | Any token with a separator is a path; a name must pass `is_valid_pipeline_name` before it is joined under `pipelines/` |
| R2-M6 `run --all` children | Each child gets `--project <root>` so it places outputs as the parent resolved them |
| R2-LOW | P9 after P5; `$HOME` resolved physically before the walk compares it; no-argument `run` outside a project keeps today's exit 2; LIB-A also fixes LIB's `--emit-config out/p.yaml` example; `report.py` (2364 lines) gets call-site edits only (about +30 over P5 and P9), no new logic |

Codex r1:

| Label | Finding and resolution |
|---|---|
| V1 | Dennis R2-B1 was incomplete. `write_if_absent` could replace a file won by another writer. Remove the helper. Claims and the marker use `_atomic.write_atomic(..., CREATE_ONCE)`. Hidden `.gitignore` files use the existing `write_local_target(..., CREATE_ONCE)`. A losing writer preserves and checks the complete winner. |
| V1 | Dennis R2-B2 is retained. Every placed run, including a `pipelines/` run, owns a `PIPELINE` claim. Both claim orders are tested. Free-standing YAMLs are not returned by `list_pipelines`, because a listed name must resolve through `pipelines/<name>/pipeline.yaml`. |
| V1 | A seconds-only run id did not order two starts in one second. Run ids now include six UTC fractional digits. The maximum length is 55. `LATEST` uses the same strict parser before comparison. |
| V1 | Run folders can contain row values. They are created mode 0700 through the existing private-file choke point. Managed output paths reject symlink ancestors that leave the physical root. Pipeline name lookup rejects symlink escapes from `pipelines/`. |
| V1 | Evidence resolution now has one caller-facing choke point. `verify_manifest_issues` resolves every recorded path from the evidence file and an explicit project hint. It never reads `DECOY_PROJECT`. New manifest fields and the schema version are strict. |
| V1 | Dennis's exit mapping is retained. `run --all` maps a negative or out-of-range child status, or malformed child JSON, to 3. `run NAME --all` is refused with exit 1. |
| V1 | Explicit `--chunked` already refuses quarantine through the engine route guard. The plan now tests that refusal before a source read instead of promising a quarantine file from that route. |
| V1 | The engine log-default change updates the existing file-access test, policy trace, registry and shrink-only baseline. This prevents hidden full-suite failures. |
| V1 | Preserve no-argument `decoy init`: inside a project it remains the wizard and asks for a pipeline name. Outside a project without `-o`, it refuses before prompting. |
| DESIGN | Remove the private `typer._click` import. One public Typer callback classifies pipeline tokens. Public `typer.models.CompletionItem` provides completion. A normalized sentry guards every config entry point. |
| DESIGN | Put every `layout.*` descriptor and safe message in `cli/io/_layout_errors.py`. Gate codes derive from that public registry. A sentry forbids a second literal table. |
| DESIGN | Extend `_private_file.py` with the private-directory primitive. Do not add a second permission mechanism. Land root, code and output-placement sentries with the mechanism they guard, not in the final sweep. |
| V2-LOG | `run.py` and `report.py` are already over 900 lines. This change adds call-site edits only. A simultaneous `LATEST` read and replace can still lose the ideal pointer order. That is a theoretical race, so it is a V2 follow-up and does not decide this gate. |

## 1. FRAME

### Problem

Output paths are built in many places, against four different bases, and no command knows what a project
or a pipeline name is.

- Table targets resolve against the config file's folder (`cli/_sources.py:27-33` `resolve_path`, called
  with `config.parent` at `run.py:828`, `:842`, `:892`; `tokenize.py:363`; `api.py:501`; `demo.py:272-280`).
  A relative target lands beside the YAML, mixed with the YAML and its sources.
- `quarantine.output_path` is opened by the engine relative to the current folder (`quarantine.py:254-274`),
  so one config writes its quarantine file in different places depending on where `decoy run` starts. The
  quarantine file holds row values.
- The evidence manifest fingerprints `Path(tgt["path"])` and `Path(src["path"])` as typed
  (`evidence.py:207`, `:231`), and `report verify` resolves them against the current folder
  (`evidence.py:433-460`, `docs/ci-contracts.md` around line 77), so a relative target is hashed from the
  wrong folder (or recorded as `None`).
- The preflight overwrite check reads `Path(target["path"])` as typed (`preflight.py:271-306`), a third base,
  and warns "directory does not exist" for a folder the run creates (QA item 9).
- The engine opens `logs/decoy_engine.log` relative to the current folder (`internal/logging.py:111`), so
  `scan`, `demo` and `run` leave a stray `logs/` folder (QA item 12). `decoy ci` works around it by changing
  folder (`ci/engine_logging.py:25-50`).
- `decoy init` writes `pipeline.yaml` into the current folder (`init.py:471`) and copies source and target
  paths as typed (`init.py:305-306`), so `decoy init -o sub/p.yaml data.csv` writes a config that `run`
  resolves against `sub/` and does not find.
- Every command takes a YAML path, so the user has to remember where each pipeline file lives and type it
  from the right folder. There is no list of pipelines and no way to hold two clients apart.
- Every run overwrites the previous output in place. There is no run folder and no run id on disk.

### Guarantee (what V1 promises)

1. **One project root.** A project is a folder holding `decoy.yaml` with `kind: decoy-project/v1`. Every
   command finds it the same way: `--project DIR`, else `DECOY_PROJECT`, else the nearest marker walking up
   from the pipeline YAML's folder (or the current folder when no YAML is given). With no marker, a given
   YAML's folder is the root. LIB's `.decoy/` lives at the root; one function answers for both.
2. **Pipelines by name.** In a project, pipeline `p` is `pipelines/p/pipeline.yaml`. Every command that
   takes a pipeline config accepts either a path or a name, through one callback, from any folder in
   the project or with `--project`.
3. **One run folder per run.** A run of pipeline `p` writes every relative output under
   `<root>/out/<p>/<run-id>/`, created fresh. `<run-id>` sorts by start time and carries the invocation id.
4. **Absolute paths are honored.** An absolute target or quarantine path is written where it says. Remote
   targets (S3, GCS) are unchanged.
5. **No escape.** A relative output path that leaves its run folder, or names no file, is refused at validate
   and at run, exit 1, before any source is read.
6. **`latest` points at the last clean run.** After a run exits 0, `out/<p>/LATEST` names its folder and,
   on Linux and macOS, `out/<p>/latest` links to it. Other exits leave both on the previous clean run.
7. **The run says where it wrote.** The summary prints the run folder. In `--json`, `outputs[]` is present
   only after at least one target file was published, and lists only files that were published.
   `output_dir` is present only when at least one of those files was published inside the placed run folder
   or typed `--out-dir`. Opening or creating a folder is not publication.
8. **No stray files.** With default flags, no Decoy command creates a file outside `<root>/out/`,
   `<root>/.decoy/`, `<root>/pipelines/`, `<root>/decoy.yaml`, a path typed on the command line, an absolute
   path in the YAML, the demo folder, or the folder of an input the command was given (the default output of
   `unmask`, `detokenize` and `fit` goes beside the input). The engine writes no `logs/` file.
9. **One placer, one root finder, one pipeline argument and one error registry.** Output paths are built only in
   `cli/io/_layout.py`, roots found only in `cli/io/_project.py`, pipeline arguments parsed only by
   `cli/io/_pipelines.py`, and layout descriptors live only in `cli/io/_layout_errors.py`. Sentries and
   seeded mutations hold all four.
10. **The user's config is not changed.** Placement never edits the loaded config; the config fingerprint
    is equal across two runs of one config.

### Non-goals (V1)

- No automatic pruning of `out/` (LIB class 4, never touched by Decoy prune). `decoy clean` is F1.
- No change to remote targets, to source path resolution (row 24o owns sources and `snapshot_file`), or to
  output paths typed on the command line (relative to the current folder, the shell rule).
- Pipelines are not made into top-level commands (`decoy members-mask` is not a command; owner, T0247).
- No configured workspace list of projects; `decoy project list` scans one folder level (F3).
- No change to `fit`'s default output (beside its source; Q6).

### Failure modes

| Failure | Behavior |
|---|---|
| Marker found but owned by another user (POSIX) | Exit 1 `layout.project_marker_untrusted` naming the folder, before any read; the fix (`--project`, or remove the file) is in the message. The git `safe.directory` rule |
| Marker unreadable, not YAML, over 64 KiB, or `kind` not `decoy-project/v1` | Exit 1 `layout.project_marker_invalid` |
| A `decoy.yaml` with no `kind` key (a pipeline someone named `decoy.yaml`) | Not a marker; the walk goes on; `--json` lists it under `project.skipped` |
| `--project DIR` or `DECOY_PROJECT` names a folder with no marker | Exit 1 `layout.project_not_found` |
| A path argument lies in a different project than `--project` names | Exit 1 `layout.project_mismatch` naming both roots |
| A name is given but no project is found | Exit 1 `layout.project_not_found`, hint `decoy project new <dir>` or pass a path |
| Unknown pipeline name | Exit 1 `layout.pipeline_unknown`, lists the project's names and the closest match (Q11 on the exit code) |
| A token that looks like a path (has a separator, or ends `.yaml` or `.yml`) and does not exist | File not found, exit 2 (a Click usage error, as today); never retried as a name |
| Declared `name:` invalid, or a name token that fails the name rule | Exit 1 `layout.pipeline_name_invalid` |
| `pipelines/<dir>/pipeline.yaml` with `<dir>` invalid | Exit 1 `layout.pipeline_name_invalid` |
| `pipelines/<dir>/pipeline.yaml` declares a different `name:` | Exit 1 `layout.pipeline_name_mismatch` (Q2) |
| A declared name already claimed by another YAML, or equal to an existing `pipelines/<name>/` folder | Exit 1 `layout.pipeline_name_collision`, before any write; names both YAMLs and the claim file |
| A derived (undeclared) name already claimed, or equal to a `pipelines/<name>/` folder | The name takes the path-hash suffix; no refusal |
| A `pipelines/<name>/` run finds a claim naming another YAML (that YAML ran first) | Exit 1 `layout.pipeline_name_collision`; the message names the claim and says to rename the other YAML or delete the claim |
| A marker or claim can not be made because the mount has no hard links | Exit 3, the message names the mount (`_atomic` `ATOMIC_NOCLOBBER_UNSUPPORTED`) |
| Relative output path leaves its run folder, is empty, `.`, or ends in a separator | Exit 1 `layout.output_path_escapes` at validate and run, before any source read |
| Placed path over 259 characters on Windows | Exit 1 `layout.path_too_long`, checked with the longest run id |
| Two configured outputs resolve to one destination | Exit 1 `layout.output_path_collision` before any source read; no destination changes |
| `--out-dir` names a file, dangling link, non-directory link, or a new directory with no parent | Exit 1 `layout.output_dir_unusable` before any source read; the message does not echo the path |
| Two runs of one pipeline at once | Distinct private run folders; microsecond ids order starts in one second; `LATEST` moves forward except for the recorded V2-LOG read-replace race |
| Run fails after its folder exists | Folder kept with the targets already committed (each target is atomic); an empty folder is removed; `LATEST` unchanged; `--json` names the folder and exact published targets only when the publication ledger is non-empty |
| `latest` link can not be made (no permission, FAT, a file in the way) | Warning `layout.latest_link_failed`; `LATEST` still written; exit code unchanged |
| `LATEST` write fails | Warning `layout.latest_write_failed`; exit code unchanged |
| `out/.gitignore` or `.decoy/.gitignore` can not be written | Warning `layout.gitignore_write_failed`; the run goes on |
| `out/` not writable | Exit 3 as today for a failed target write; the message names the run folder |
| The pipeline YAML lies under `out/` | Warning `layout.config_inside_out` |
| `decoy project new` on `$HOME`, an ancestor of it, or `/` | Exit 1 `layout.project_root_refused` |
| `decoy init <name>` outside any project, without `-o` | Exit 1 `layout.project_not_found`, hint `decoy project new .` |

## 2. Established solutions

- **Project root by walking up to a marker:** git (`.git`, `GIT_CEILING_DIRECTORIES`, stop at a filesystem
  boundary, and since CVE-2022-24765 a refusal for a repository owned by another user, `safe.directory`),
  Cargo (`Cargo.toml` walk), dbt (`dbt_project.yml`). A named file with a schema tag is the common marker.
- **Selecting a project from outside it:** `git -C DIR`, `make -C DIR`, `terraform -chdir=DIR`,
  `dbt --project-dir` with `DBT_PROJECT_DIR`, `cargo --manifest-path`. Flag first, then variable, then walk:
  the dbt order.
- **Named units inside a project:** Cargo workspace members (`cargo run -p NAME`), npm scripts
  (`npm run NAME`, which lists scripts when NAME is unknown), dbt `--select`, Make targets. A name is looked
  up in a fixed place; an unknown name prints the known ones. Git's "did you mean" uses an edit-distance
  match; Python's `difflib.get_close_matches` gives the same.
- **Init versus new:** Cargo `cargo new DIR` makes a package, dbt `dbt init`, Rails `rails new DIR` then
  `rails generate` inside it. Creating the container and adding a unit to it are two commands.
- **Build output under the project:** dbt `target/`, Cargo `target/` with `--target-dir`, Bazel
  `bazel-out/`. The override flag gives `decoy run --out-dir`.
- **A folder per run:** MLflow `mlruns/<experiment>/<run_id>/`, Hydra `outputs/<date>/<time>/`, Weights and
  Biases `wandb/run-<time>-<id>/` with a `latest-run` link. Time-sortable names with a short random id.
- **A `latest` pointer:** W&B `latest-run`, Bazel convenience links (junctions on Windows). Windows needs
  developer mode for symlinks, so a plain pointer file is the portable form.
- **Generated folders ignore themselves:** virtualenv and `.pytest_cache` write a `.gitignore` holding `*`.
- **Atomic link swap:** make the new link under a temporary name, then `rename` over the old one.
- **Shell completion from a parameter type:** Click's `ParamType.shell_complete`, used when no custom
  completer is set; `CompletionItem(type="file")` hands file completion back to the shell.
- **Running all units with one exit code:** `cargo test --workspace`, `npm run --workspaces`, `make -k`:
  run each, keep going, report each, exit with the worst result.

What stays custom: the name and claim rules, the escape rule, and the report placement rule.

## 3. Design notes

### 3.1 Choke points

- **Project root:** `find_project(start, explicit)` in `cli/io/_project.py` is the only root finder. LIB's
  `resolve_root` (L1b.2, `cli/_library/_paths.py`, not yet on main) calls it.
- **Pipeline argument:** `parse_pipeline_token` in `cli/io/_pipelines.py` is the only parser of a pipeline
  token. Every command parameter that takes a pipeline config uses this public Typer callback.
- **Placement:** `RunLayout` in `cli/io/_layout.py` is the only builder of output paths.
- **Table writes:** unchanged choke point `cli/io/_targets.py` (G-ONE-TARGET-WRITE). `write_targets` and
  `write_chunked_output` take a `RunLayout` instead of a `base_dir`.
- **Atomic writes:** `_atomic.py` gains `replace_symlink`; the distribution link swap moves onto it.
- **Create-once files:** claims and `decoy.yaml` use the existing
  `_atomic.write_atomic(parent, name, data, WriteMode.CREATE_ONCE)`. Hidden `.gitignore` names cannot use
  `write_atomic`, so they call the existing `write_local_target(path, data, CREATE_ONCE)` directly. A
  `False` result preserves the winner. No check-then-replace helper is added.
- **Private output:** `_private_file.create_private_directory` is the only creator of value-bearing run
  folders. On POSIX it uses exclusive `mkdir`, opens the directory with `O_NOFOLLOW|O_DIRECTORY`, applies
  mode 0700 with `fchmod`, and verifies the opened descriptor with `fstat`. Any failure is fatal before a
  data write. The existing private-file sentry covers it. Windows uses exclusive `mkdir`.
- **Layout errors:** `cli/io/_layout_errors.py` owns each `layout.*` descriptor and fixed, value-free
  message. Gate and command errors use this registry. `ci/rule_codes.py` derives its set from the public
  `decoy.cli.io` export.
- **Package boundary:** commands, `cli/project` and `ci` import layout services only from public
  `decoy.cli.io`. Private modules are internal to that package.
- **Pipeline name rule:** the engine owns the `name:` field and exports `is_valid_pipeline_name`; the CLI
  checks folder names and slugs with the same function.

### 3.2 Project marker (`decoy.yaml`)

```yaml
kind: decoy-project/v1
```

The marker holds only `kind` in V1; other keys warn and are ignored (reserved). It is parsed with a safe
loader, at most 64 KiB. A `decoy.yaml` with no `kind` key is a pipeline file, not a marker (Failure modes).
`decoy.yaml` was chosen over `decoy-project.yaml` because the owner named it (T0248, T0249); the `kind`
key keeps it from being mistaken for a pipeline.

**Trust.** POSIX: the file is opened with `O_RDONLY|O_NOFOLLOW`, then `fstat` on the descriptor; the owner
must be the effective uid, or the command exits 1 `layout.project_marker_untrusted`. Opening first and
checking the descriptor means a swap between check and read can not pass. Windows: no owner check (F4).

### 3.3 Finding and selecting the project (`cli/io/_project.py`, about 220 lines)

`find_project(start: Path | None, explicit: Path | None) -> Project`:

1. `explicit` (from `--project DIR` or else `DECOY_PROJECT`; relative to the current folder): `DIR/decoy.yaml`
   must be a valid trusted marker, or exit 1 `layout.project_not_found` or the marker codes. No walk.
2. Else walk from `start` (resolved, physical): check `start` and each parent for `decoy.yaml`. Stop with no
   match after the folder holding `.git` (folder or file), at a device change, or before reaching `$HOME`
   when `start` is under `$HOME` (`$HOME` itself is never a root; both are resolved physically before the
   comparison). Outside `$HOME` the walk goes to `/`.
3. With no match: `Project(root=start, implicit=True)`.

Which `start` and `explicit` each command uses:

| Command input | `start` | `explicit` |
|---|---|---|
| a pipeline given by path | the YAML's folder | `--project` only; if set and the YAML's own project differs, exit 1 `layout.project_mismatch` |
| a pipeline given by name, or no pipeline | the current folder | `--project`, else `DECOY_PROJECT` |
| `scan` (no pipeline) | LIB 4.1 order (`--config`, else the current folder) | `--project`, else `DECOY_PROJECT` |

`DECOY_PROJECT` is ignored for a path argument: it is ambient, and refusing every path run in a shell that
exported it would break scripts. An explicit `--project` was typed for this command, so a mismatch is an
error.

`--project` is a global option on the app callback (`src/decoy/__main__.py:99`), stored on the command
context; it does not change the current folder, so typed relative paths keep the shell rule. It is placed
before the command (`decoy --project acme run members-mask`), the `git -C` shape.

`ensure_decoy_dir(root)` creates `.decoy/` and its `.gitignore` (LIB 4.9 content) when absent; `decoy project
new` calls it, and LIB's writers call the same function.

`ensure_decoy_dir` calls `write_local_target(..., CREATE_ONCE)` for `.decoy/.gitignore`. `project new`
calls `write_atomic(..., CREATE_ONCE)` for `decoy.yaml`. A losing marker writer reads and validates the
complete winner. An existing `decoy.yaml` that is not a valid project marker is refused.

### 3.4 Pipeline argument (`cli/io/_pipelines.py`, about 220 lines)

Two public Typer hooks serve every pipeline parameter. No private Typer or Click module is imported.

**`parse_pipeline_token`** is a Typer argument or option callback. The declared annotation stays `str`.
The callback returns frozen `PipelineToken(raw, kind)`. Each command immediately uses
`cast(PipelineToken, parameter)` before `resolve_pipeline`. It is used on `run`, `validate CONFIG`
(`validate.py:254`), `validate config`, `validate compile`
(`compile_explain.py:87`), `validate preflight` (`preflight.py:624`), `tokenize`, `detokenize`
(`tokenize.py:445`), `unmask` (`unmask.py:67`), `subset` (`subset.py:80`), and the `--config` option of
`report fidelity` (`report.py:1638`), `report integrity` (`:1957`) and `report vault` (`:2202`). It only
classifies the token:

1. `-` stays stdin where a command accepts it today.
2. An existing file: `kind="path"`. This includes an extension-less file in the current folder that shares a
   pipeline's name (T0247: an existing file wins).
3. A token with a path separator, or ending `.yaml` or `.yml`: `kind="path"`; if it does not exist,
   `typer.BadParameter` gives exit 2, today's usage behavior.
4. Otherwise `kind="name"`.

**`resolve_pipeline(token, ctx, state) -> PipelineRef(yaml, project, name, given_as)`**, called first in
each command body, after output setup, so its refusals exit 1 and use the command's `--json` envelope. A
path finds its project (3.3). A name must pass `is_valid_pipeline_name` (`layout.pipeline_name_invalid`),
then a project must be found (`layout.project_not_found`). The physical YAML must remain inside the
physical `<root>/pipelines/` folder. A symlink escape is refused. The YAML must exist, or exit 1
`layout.pipeline_unknown` with the sorted
names and `difflib.get_close_matches(token, names, n=1)`. The command passes `ref.yaml` where it used a
`Path` before.

`list_pipelines(project) -> list[PipelineEntry]` returns only validated
`pipelines/*/pipeline.yaml` entries, sorted by name. It uses the same physical-containment and name checks
as `resolve_pipeline`. `run` with no argument, `run --all`, `decoy project show` and completion call it.
Free-standing YAMLs still run by path and claim their output namespace. They are not project members.

### 3.5 Pipeline name and claim

The name decides the folder `out/<name>/`. In order:

1. `<root>/pipelines/<dir>/pipeline.yaml`: the name is `<dir>`. `<dir>` must pass `is_valid_pipeline_name`
   (`layout.pipeline_name_invalid`). A declared `name:` that differs is refused (`layout.pipeline_name_mismatch`,
   Q2). These names are unique by construction (one folder each).
2. Any other YAML with `name:`: the declared name; an invalid one is refused.
3. Any other YAML without `name:`: `slug(stem)`: characters outside `[A-Za-z0-9_.-]` become `-`, runs of
   `-` collapse, leading and trailing `-` and `.` are cut, at most 56 characters. When the slug differs from
   the stem, is empty, or is a Windows device name, or when it is taken (below), the name is
   `<slug or "pipeline">-<first 6 hex of sha256(root-relative POSIX path)>`. A derived name never refuses.

A step-2 or step-3 name is taken when `out/<name>/PIPELINE` names another YAML or when
`<root>/pipelines/<name>/` exists (the folder name is reserved for that pipeline even before its first run).

`is_valid_pipeline_name` uses `re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value)`. It rejects a
trailing `.`, and Windows device names `CON`, `PRN`, `AUX`, `NUL`, `COM1` to `COM9`, `LPT1` to `LPT9`,
and the existing superscript 1, 2 and 3 forms, any case and with any extension. `PipelineConfig.name` is a
strict optional string. A before validator rejects non-strings and registers
`config.pipeline_name_invalid`. The engine public function and CLI use this one rule.

**Claim.** Every run that places a file, `pipelines/` runs included, makes sure `out/<name>/PIPELINE` names
its YAML (root-relative, POSIX). The first run creates it with `write_atomic(..., CREATE_ONCE)`,
which links a fully written temp, so a reader never sees an empty claim and two racing first runs leave one
claim. A losing creator reads the winner and compares it. Later runs read it: a different path is a collision (declared name or a `pipelines/` name: exit 1
`layout.pipeline_name_collision`; derived name: take the hash suffix). On a case-insensitive filesystem
`Orders` and `orders` share one folder and the claim catches it. A moved YAML hits the claim; the message
names the claim file and both fixes (set `name:` or rename, or delete the claim).

Name and claim checks run only when the config has at least one placed output (a relative local target or
a relative quarantine path). A config with only absolute or remote targets has no `out/` folder and no
claim.

### 3.6 Run folder and `latest`

`RunLayout.open(project, name, invocation_id)` runs after the gate passes and before the first write:

1. ensure physical `out/` remains under the physical project root; create `out/.gitignore` with the
   existing `write_local_target(..., CREATE_ONCE)` and preserve an existing file; require the physical
   `out/<name>/` to remain under physical `out/` before a claim or child is created;
2. check or create the claim;
3. create `out/<name>/<run-id>/` mode 0700 through `create_private_directory`. `<run-id>` is
   `<UTC start YYYYMMDDTHHMMSSffffffZ>-<first 8 hex of the invocation id>`; on a clash it takes 4 more hex
   digits, up to all 32. The maximum length is 55.

`mint_invocation_id()` in `_layout.py` is the one mint: a UUID4 per command, made at command entry. The
evidence `run_id` (`evidence.py:309`) takes it instead of minting its own, and LIB records take it (LIB-A),
so run folder, evidence and records join on one id.

`commit_latest()` runs only on the exit-0 path. It parses `out/<name>/LATEST` with the same strict run-id
parser. Invalid content is treated as absent and warns `layout.latest_invalid`. If a valid id sorts after
this one, stop. Otherwise write `LATEST` with `_atomic.write_atomic(..., WriteMode.REPLACE)`, then on POSIX
`_atomic.replace_symlink(out/<name>/latest, <run-id>)`. The read and write are not one atomic step; two
runs crossing between the read and replace can leave the older pointer. This theoretical race is V2-LOG.
The next clean run repairs it. `abandon()` removes the run folder only when empty (`rmdir`).

`--out-dir DIR` (on `run` and `tokenize`) replaces the run folder with `DIR` (relative to the current folder,
created mode 0700 through the same helper after the gate if missing and needed): `RunLayout.out_dir(DIR)`,
no claim, no run id, no `latest`, no `.gitignore`, overwrite as
today. A placed child must stay within `DIR.resolve(strict=False)`, including through existing symlink
ancestors. Files there are not recognized by `owning_run` (F6).

#### 3.6.1 P4 layout gate, collision and JSON contract

**A. Check matrix.** `Runs` means the check executes before a source read; a failure uses the stated exit
and rule code. `Skipped` means the invocation has no such managed state. `Change` marks behavior that the
P4 head `845d93a5` does not yet have. A warning does not change `run`'s exit; at `validate preflight
--fail-on-warning` it exits 2.

| Layout check | Placed project run | `--out-dir` run | Legacy run, absolute targets only | `validate preflight` | `--rows` preview |
|---|---|---|---|---|---|
| Project marker and root | Runs; refuse 1 `layout.project_marker_invalid`, `layout.project_marker_untrusted`, `layout.project_not_found` or `layout.project_mismatch` | Skipped after a path config is resolved (Change); a named config still uses the explicitly selected project only to find its YAML | Skipped | Runs as a normal placed run; refuse 1 with the same codes | Skipped because preview writes nothing (Change) |
| Pipeline name and claim | Runs read-only; refuse 1 `layout.pipeline_name_invalid`, `layout.pipeline_name_mismatch` or `layout.pipeline_name_collision`; repeat the claim check at open | Skipped (Change) | Skipped | Runs read-only; refuse 1 with the same codes | Skipped (Change) |
| Run folder and run id | Gate skips writes; after it passes, exclusive open runs and an operational failure exits 3 with the existing `private_*` code | Skipped; fixed-directory shape runs before the gate and refuses 1 `layout.output_dir_unusable` | Skipped | Skipped | Skipped |
| `LATEST` and `current` | Skipped by the gate; after successful execution, run only on exit 0, including an empty chunked success; `layout.latest_invalid`, `layout.latest_write_failed` and `layout.latest_link_failed` are warnings | Skipped | Skipped | Skipped | Skipped |
| Windows path budget | Runs against `<root>/out/<name>/<max-run-id>`; refuse 1 `layout.path_too_long` | Runs against the resolved `DIR` (Change); refuse 1 `layout.path_too_long` | Skipped for user-chosen absolute paths | Runs as a normal placed run; refuse 1 `layout.path_too_long` | Skipped (Change) |
| Output containment and symlink ancestors | Runs for relative file targets and enabled quarantine; refuse 1 `layout.output_path_escapes` | Runs against physical `DIR`; refuse 1 `layout.output_path_escapes` | Skipped for absolute paths | Runs as a normal placed run; refuse 1 `layout.output_path_escapes` | Skipped (Change) |
| URL carve-out | Runs: a `type: file` path whose scheme and `://` start at offset zero is not made local and is refused 1 `layout.output_path_escapes`; a non-file remote target is skipped | Runs with the same refusal and code; a non-file remote target is skipped | Runs with the same refusal and code; a non-file remote target is skipped | Runs with the same refusal and code; a non-file remote target is skipped | Skipped (Change) |
| NUL and backslash | Runs for relative local outputs; refuse 1 `layout.output_path_escapes` | Runs for relative local outputs; refuse 1 `layout.output_path_escapes` | Runs for NUL and refuses 1 `layout.output_path_escapes`; a native absolute backslash spelling is honored | Runs as normal placement; refuse 1 `layout.output_path_escapes` | Skipped (Change) |
| Existing-file overwrite advisory | Runs for absolute targets only; relative paths in a fresh run folder are skipped; warning `target.<table>.would_overwrite` or `target.<table>.parent_missing` | Runs on each resolved local destination, including relative targets under fixed `DIR` (Change); same warning codes | Runs; same warning codes | Runs for absolute targets only; same warning codes | Skipped |
| Resolved-destination collision | Runs for every local file target, enabled quarantine, and typed run-side file named below; refuse 1 `layout.output_path_collision` (Change) | Runs for the same set after fixed-directory placement; refuse 1 `layout.output_path_collision` (Change) | Runs, including absolute-to-absolute collisions; refuse 1 `layout.output_path_collision` (Change) | Runs for every config destination; refuse 1 `layout.output_path_collision` (Change) | Skipped (Change) |

The gate receives an output-placement context, not a boolean flag. It is normal project placement, a typed
fixed directory, or no-write preview. `_run_config_base` passes that context to `layout_issues`; direct
`validate preflight` passes normal project placement. This is the one route decision. It fixes the current
call at `run/_prepare.py:322`, which loses `--out-dir`, without teaching `gate/_layers.py` a second path
resolver. The check remains before `_check_source_files` on both gate routes.

**B. One collision rule.** Add `resolved_output_collisions(...)` next to `relative_outputs` in
`cli/io/_layout.py`. That function uses the same output enumeration and `contained_path` resolution as
placement. After placement, every local file target and enabled quarantine destination must be pairwise
distinct. Absolute targets participate. URLs and non-file remote targets do not. `run` supplies the typed
`--evidence-out` and `--vault` destinations to the same function, so either typed file also cannot replace a
target, quarantine file, or the other typed file. `validate preflight` has no invocation flags, so it checks
the config destinations only.

Resolve existing symlink ancestors exactly as containment does. Compare existing destinations by file
identity. For destinations not yet present, resolve the nearest existing ancestor and compare the whole
unresolved suffix. Determine case behavior without writing: case-swap an alphabetic component of that
ancestor and use `samefile`; walk existing ancestors until one can be probed. Case-fold the unresolved
suffix only when the probe identifies a case-insensitive filesystem. The first duplicate refuses before any
source read with exit 1 and
`layout.output_path_collision`. Its registry message shape is
`Configured outputs {first} and {second} resolve to one destination. Give each output a different path.`
The fields are config locations such as `targets.orders.path`, `quarantine.output_path`, or flag names, never
path values. The descriptor lives in `_layout_errors.py`; CI derives it through `GATE_DESCRIPTORS`. The gate
and direct `validate preflight` both call this one function through `layout_issues`. There is no collision
loop in `preflight.py`, and its 891-line pin does not move. `check_before_run` remains the construction
choke point for every `run` route; AT-30 is its guard and MP22 is the seeded bypass. AT-31 guards the direct
`validate preflight` route and MP23 removes a real collision class from the shared enumeration.

**C. JSON publication rule.** An opened folder is not evidence that a file exists. Keep one publication
ledger mapping on `RunContext`. Pass that mapping to `write_targets`, which adds an entry immediately after
each target publisher returns; the chunked loop adds its entry immediately after each
`write_chunked_output` returns. A later exception therefore cannot discard earlier entries when
`write_targets()` does not return. Both placed and `--out-dir` runs use it:

- a gate refusal or a failure before the first publish omits both `output_dir` and `outputs`, even when a
  valid `--out-dir` was inspected or already existed;
- a failure after one or more target files publish includes `outputs` with exactly those files; it includes
  `output_dir` only when at least one listed file is below the run folder or `--out-dir`;
- success follows the same rule. An empty chunked run omits both fields. An absolute-target-only success has
  `outputs` but omits `output_dir`. A placed or `--out-dir` success with a published relative target has both.

`outputs` entries keep the P4 shape `{table, path}`, with absolute paths. Quarantine, evidence and vault
artifacts keep their existing dedicated contracts and are not inferred into `outputs`; their destinations
still take part in the collision rule. `project` and `pipeline` keep their existing independent contract.
The success and failure renderers read the same ledger, so a mid-run failure cannot lose the record of an
earlier publish.

**Decided `run --out-dir` cells.** These close the remaining flag and filesystem combinations:

This P4 remediation changes `run` only. The `tokenize --out-dir` wiring and acceptance stay in P9, and
`owning_run` support for fixed output folders stays F6.

- With a path config, `--project` does not re-enable project placement checks. An explicit project is still
  checked for the path-token mismatch contract in 3.3 by requiring the physical YAML to be below that
  explicit root; the command does not walk or validate a marker beside the YAML. With a named config,
  `--project` may locate the YAML, then the fixed-directory matrix applies. `DECOY_PROJECT` remains ignored
  for a path token.
- `--rows --out-dir` and `--all --out-dir` are refused before any folder is made, exit 1. `--all` also keeps
  its existing refusal of `--evidence-out` and `--vault`.
- `--json` follows C. Human output keeps the existing summary contract and may name the opened run or fixed
  folder even when no target file was published.
- `--evidence-out` and `--vault` remain paths typed relative to the current folder and are not moved under
  `DIR`. They are allowed with `--out-dir`, but all resolved destinations join B before any source read.
- `run - --out-dir DIR` stays unsupported because `run` does not accept stdin config today; tokenization of
  `-` does not add a new input route.
- A relative file target is contained under physical `DIR`; an absolute target stays absolute; a file-target
  URL is refused; a non-file remote target is unchanged. Mixed relative, absolute and remote targets use
  those rules independently, then all local destinations enter B.
- Enabled quarantine is placed under `DIR` when relative and enters B; an absolute quarantine stays absolute
  and enters B; disabled or absent quarantine contributes no destination. `--chunked` with enabled
  quarantine keeps its earlier exit-1 refusal.
- A missing `DIR` is created mode 0700 only after the gate passes and only when a relative output is needed.
  A regular file, dangling link, or link to a non-directory is refused before a source read with the fixed,
  value-free `layout.output_dir_unusable` error and exit 1. Its registry message is `--out-dir must name an
  existing directory, or a new directory whose parent exists.` A link to a directory is allowed and its
  physical directory is the containment and collision base. A pre-existing directory that later refuses a
  publish as unwritable exits 3; the gate does not claim a race-free writability proof.
- `DIR` may be inside the selected project's `out/`; it is a typed override, so it gets no claim, run id,
  `.gitignore`, `LATEST` or `current`. It may not escape its own physical base through a child symlink.
- When all targets are absolute or remote and quarantine is absent or absolute, `DIR` is unused and is not
  created. The absolute local destinations still receive overwrite and collision checks.

### 3.7 Placing paths

- `place_target(raw)`: reuses `placed_path(run, raw)` from `_layout.py` (P2a) for the inside-the-run check;
  absolute stays; relative is normalized against the run folder and must stay inside
  it and name a file (`layout.output_path_escapes` otherwise); subfolders are made at write time as today
  (`_targets.py:421`).
- `place_quarantine(raw)`: same rule. The placed absolute path goes to the engine as
  `run_pipeline(..., quarantine_path=...)` (E2). The engine strictly checks the new keyword before source
  work. It builds the context and semantic hash from the original config, then copies the config, replaces
  only `quarantine.output_path`, and uses `dataclasses.replace(ctx, config=effective_config)` before route
  selection. Every route already reads `ctx.config`. The caller's dict and hash stay untouched
  (`_hash_config` hashes the quarantine block, `plan/_compile.py:639`, `:657`).
- `side_file_default(kind, input_path)`: the one table of default side-file names (`unmasked`,
  `detokenized`, `snapshot`) moved verbatim from `unmask.py:279`, `tokenize.py:608-613` and `fit.py:495`.
  Still beside the input.
- `owning_run(path, root, name) -> RunFolder | None`: `path` (with `latest` followed) under
  `<root>/out/<name>/<run-id>/` for the config's pipeline. `_targets.py:203-217` compares a file with the
  declared target through `owning_run` as well as the old `resolve_path(entry["path"], base_dir)` form, so a
  file at either place keeps the declared format and fixed-width layout.
- `describe()`: the summary and `--json` fields, so `run.py` grows only by call sites.

Human output prints a path relative to the current folder when it is under it, else absolute. `--json`
always gives absolute paths.

### 3.8 `mask()` API

`mask(config, out=...)` in `api.py` places through `RunLayout.fixed(base)`: `base` is `Path(out)` relative to
the current folder when `out=` is given (the typed-flag rule, replacing `_apply_out_override`'s target
rewrite at `api.py:290-307`), else the config's folder, or the current folder for a dict config (today's
base). No claim, no run id, no `latest`, no `out/.gitignore`; a dict config has no name. Library callers
keep fixed, predictable paths (Q9).

### 3.9 Evidence and reports

**Evidence.** Output and input fingerprints hash the files the run used (placed targets; sources resolved
against the YAML folder). Paths inside the project are recorded relative to the root, POSIX, and the
manifest gains `path_base: "project"`. This applies only to a project with a marker; an implicit project
(no marker) and paths outside the project are recorded absolute. The existing resolver is strengthened:
`resolve_manifest_path(manifest, raw, *, manifest_file, project=None, field="path")` is the named
caller-facing choke point for every filesystem use of a stored manifest path. It resolves the manifest's
root and then delegates relative-path validation to `decoy.cli.io.contained_path`; it is not a second
parser. After schema validation, `read_manifest(path, project=None)` sends the pipeline path and every
input and output entry through it, using the manifest file and optional typed project, before returning
the raw manifest for metadata rendering. `verify_manifest_issues` uses it again for every path it hashes.
`compare_data` takes each full manifest and its manifest file, not detached `output_fingerprints` dicts,
and passes that context to the resolver before checking or reading either output. `report show` and
`report render` therefore validate every stored path through their shared
`_load_manifest`, even though they do not dereference the output files. `report verify` and `ci check`
reach stored files only through `verify_manifest_issues`. No current or future consumer may pass a
manifest entry to
`Path`, `PurePath`, `os.path`, a `/` path join, `.resolve()`, `.exists()`, `.is_file()`, `open`, or a data
reader directly. With `path_base: "project"`, the root is the typed `--project`, else `find_project` from
the manifest's folder. No marker means refusal with the `--project` hint. It never falls back to the
current folder. `DECOY_PROJECT` is not used here:
it is ambient, and a verify of one client's manifest in a shell exported for another would report false
missing outputs. Without the field, today's current-folder rule (`docs/ci-contracts.md`). The contract doc
gains the second rule. The reader requires exact `schema_version: "cli-local-1"`, accepts only absent or
exact string `"project"` for `path_base`, and tolerates extra keys. Missing or unknown schema versions,
wrong field types and unknown `path_base` values refuse a malformed manifest.

Added after Codex r1 on P3 (three V1 findings, one DESIGN). Paths are resolved before they are made
relative, so `sub/../../x` or a symlinked folder is recorded absolute; the reader refuses a project-relative
path with a `..` part or one that resolves outside the root, before any file is hashed. The marker carries
no identity, so the manifest records `project_manifest`: where it was written relative to the root, or null
when written outside the project. The reader refuses the manifest when its file is not at that place under
the root it reads from (typed `--project` or the marker walk), so evidence for project A stored in project B
is refused; a null value skips the walk and needs `--project`. Residual: an exact copy at the same relative
place in B binds to B and its fingerprints report B's files. One schema table in `evidence.py` drives both
`build_manifest` (it checks its own output) and the one strict reader `read_manifest`, which every `report`
command and `ci check` use; `ci/adapters.py` no longer checks the object itself. Null required fields, a
non-object top level and `NaN` are refused, never a crash.

P3 review-round disposition: r2 removed the private POSIX parser from `evidence.py`, leaving
`decoy.cli.io.contained_path` as the sole stored-relative-path validator and
`evidence.resolve_manifest_path` as its manifest-aware wrapper. R3 at CLI `7400ea4a` found
`report.py:923-926` constructing `Path(raw)` for `report diff`, which made project-relative outputs depend
on the current folder. The choke point, G-ONE-MANIFEST-PATH and the AT-9 consumer matrix close that V1
class by construction. **V2-LOG, V1-1 provenance residual:** an exact manifest copy at the same relative
place in another project still binds to that project's files because the marker has no project identity.
Adding a project id to the marker is V2 work and is not a P3 merge blocker.

**Reports.** `report integrity` and `report fidelity` print to stdout today and write a file only with
`--output` or `--report-out`. After: when the masked file argument lies in a run folder (`owning_run` for
any pipeline in the project) and no output flag is given, the JSON report is also written to
`<run folder>/reports/<kind>.json` (`REPLACE`), and the path is printed. A typed flag wins. A report on a
file outside a run folder writes nothing new (Q12).

### 3.10 `decoy init` makes pipelines

`init` keeps its job, creating a pipeline, now inside a project:

- `decoy init NAME [--source FILE] [--preset P] [--yes]` writes `<root>/pipelines/NAME/pipeline.yaml`.
  `NAME` must pass `is_valid_pipeline_name`. An existing file there needs `--yes` (today's overwrite rule,
  `init.py:512-515`).
- The positional token follows the shared token classifier: an existing file is the source, as today
  (`decoy init data.csv`), and the name is `slug(stem)`; otherwise it is the name.
- The source path is written relative to the YAML's folder when the source is inside the project, else
  absolute. Targets are bare `<table>.masked.<ext>` (placed into run folders at run time). No `name:` key is
  written: the folder is the name.
- Outside any project, without `-o`: exit 1 `layout.project_not_found`, hint `decoy project new .` or `-o
  FILE`. Creating a project silently would make whatever folder the user stood in (often `$HOME` or
  Downloads) a project root; one explicit command avoids that (Q8).
- `-o FILE` works anywhere, as today, with source paths written relative to `FILE`'s folder (the
  `init.py:305-306` fix). `-o -` writes to stdout.
- Inside a project, no positional token keeps the current wizard. It prompts for the pipeline name and
  writes that pipeline folder. Outside a project, no positional token and no `-o` refuses before a prompt.
- The scaffold code lives in `cli/project/_scaffold.py` (`write_pipeline_scaffold`), called by `init` and
  later by INIT-WIZARD; `init.py` only maps arguments.

### 3.11 `decoy project` group

A command group (`src/decoy/cli/project/`, a new subpackage because `cli/` is frozen) rather than top-level
`decoy projects` and `decoy pipelines`: `decoy list` already means engine registries (`reference.py:132`), and
a group keeps project commands together the way `decoy report` and `decoy validate` do (Q3).

- **`decoy project new DIR`** (`DIR` may be `.`; made if missing, parents too): writes `DIR/decoy.yaml`,
  `DIR/pipelines/`, `DIR/out/.gitignore` (`*`), and `.decoy/` with its `.gitignore` (`ensure_decoy_dir`).
  The marker and hidden files use the create-once calls in 3.1. Running it again on a valid project fills
  only missing entries and prints "already a project". An existing invalid `decoy.yaml` refuses. Refused
  for `$HOME`, an ancestor of it, or `/` (`layout.project_root_refused`).
  Inside another project it warns `layout.project_nested`; the nearer marker wins for its subtree. Prints the
  root and the next command (`decoy init <name> --source <file>`).
- **`decoy project show`**: the selected project (3.3): root, marker, and a table of pipelines from
  `list_pipelines`: name, YAML (root-relative), last run (newest folder accepted by the shared run-id
  parser), last clean run (the same strict `LATEST` reader),
  status (from LIB run records once L3a lands; `-` before). `--json` gives the same.
- **`decoy project list [DIR]`** (`DIR` defaults to the current folder): `DIR` itself if a project, and each
  direct subfolder that is one: folder, root path, pipeline count. One level only.

**One project per client** (T0248): records, job logs, evidence, retention and export are per project
(LIB keeps `.decoy/` at the root), so a client's data and history can be handed over, archived or deleted as
one folder. Several clients in one project would share `out/`, `.decoy/library/` and the claim namespace;
deleting one client's data would mean picking files out of shared folders, and a name like `members-mask`
would need a client prefix to stay unique. Names are unique per project only.

### 3.12 `decoy run` with no argument, and `--all`

- **No argument:** the project from 3.3; exactly one pipeline: run it, printing "Running the only pipeline:
  NAME"; none: exit 1 with hint `decoy init <name>`; several: list them and exit 1 (Q11). No project: the
  missing-argument usage error as today (exit 2) plus the hint.
- **`--all`:** every name from `list_pipelines`, sorted by name. `run NAME --all` is refused with exit 1.
  Each runs in
  its own process, `sys.executable -m decoy --project <root> run <yaml> --json` plus the forwarded flags
  (`--project` so each child places outputs exactly as the parent resolved the project), so engine state, the
  logger and memory limits do not carry over between pipelines and each child's exit code means what it means
  for a single run. The run goes on after a failure. Flags that name one file (`--evidence-out`, `--vault`,
  `--out-dir`) are refused with `--all` (exit 1): one file for many pipelines would be overwritten. The
  summary table lists name, exit code, run folder; `--json` gives a list of the children's payloads. The exit
  code is the first present in the order 3, 5, 1, 4, 2, 0 (failed to finish, refused, then finished with
  findings or warnings). A child code outside 0 to 5, a negative code (killed by a signal), or a child
  whose `--json` output does not parse counts as 3, so a killed or crashed pipeline never reads as clean.
  Code in `cli/project/_run_all.py`.

### 3.13 Shell completion

Every config parameter uses public Typer `autocompletion=pipeline_names`. The function returns public
`typer.models.CompletionItem` objects for project names that start with `incomplete` (project from
`--project` already on the line, else `DECOY_PROJECT`, else the walk from the current folder), plus
`CompletionItem(incomplete, type="file")`. Errors return no names. Completion is already on
(`add_completion=True`, `__main__.py:74`).

### 3.14 Validate and gate

The gate's config layer (`gate/_layers.py`) runs the placement-context matrix in 3.6.1. `validate`, `ci
check`, direct `validate preflight` and `run` share `layout_issues`; `run` supplies normal placement,
`--out-dir`, or no-write preview context. `run` repeats the claim check at `open`. The codes come from the
central layout descriptor registry. `ci/rule_codes.py` derives its gate set from the public
`decoy.cli.io` export. It repeats no literals.

### 3.15 Engine log

E2 changes the engine's default log file to `None` (`internal/logging.py:111`); a caller that wants a file
passes one. Console output is unchanged. The CLI adds no call; `ci/engine_logging.py` drops its `chdir`. The
engine log can carry table names and advisories, and LIB's `.decoy/logs/` is value-free by contract, so the
file log is off rather than moved there.

## 4. User walk-through

A new user, two clients, two pipelines each. Every command typed and every path printed. `$` lines are typed;
the lines after are the output. The user's home is `/home/ana`; sources are in `~/data/`.

```text
$ mkdir -p ~/work && cd ~/work
$ decoy project new acme
Created project /home/ana/work/acme
  acme/decoy.yaml
  acme/pipelines/
  acme/out/.gitignore
  acme/.decoy/.gitignore
Next: cd acme && decoy init <name> --source <file>

$ decoy project new globex
Created project /home/ana/work/globex
  globex/decoy.yaml
  globex/pipelines/
  globex/out/.gitignore
  globex/.decoy/.gitignore
Next: cd globex && decoy init <name> --source <file>

$ cd acme
$ decoy init members-mask --source ~/data/acme/members.csv
Wrote pipelines/members-mask/pipeline.yaml (1 table: members; source /home/ana/data/acme/members.csv)
Next: decoy run members-mask

$ decoy init members-generate --preset generate
Wrote pipelines/members-generate/pipeline.yaml (preset generate)
Next: decoy run members-generate

$ decoy run members-mask
Pipeline members-mask (project /home/ana/work/acme)
  members  10,000 rows  masked
Output folder: out/members-mask/20261109T141502000001Z-3f9c2a1b/
  members: out/members-mask/20261109T141502000001Z-3f9c2a1b/members.masked.csv
latest -> out/members-mask/20261109T141502000001Z-3f9c2a1b/

$ cd pipelines/members-generate
$ decoy run members-generate
Pipeline members-generate (project /home/ana/work/acme)
  employees  1,000 rows  generated
Output folder: /home/ana/work/acme/out/members-generate/20261109T141533000001Z-a07e5d12/
  employees: /home/ana/work/acme/out/members-generate/20261109T141533000001Z-a07e5d12/employees.csv
latest -> /home/ana/work/acme/out/members-generate/20261109T141533000001Z-a07e5d12/

$ cd ~/work/acme
$ decoy project show
Project /home/ana/work/acme
  name              yaml                                      last run              last clean            status
  members-generate  pipelines/members-generate/pipeline.yaml  20261109T141533000001Z-a07e5d12  20261109T141533000001Z-a07e5d12  -
  members-mask      pipelines/members-mask/pipeline.yaml      20261109T141502000001Z-3f9c2a1b  20261109T141502000001Z-3f9c2a1b  -

$ decoy report integrity out/members-mask/latest/members.masked.csv --source ~/data/acme/members.csv --config members-mask
Integrity: pass (0 findings)
Report: out/members-mask/20261109T141502000001Z-3f9c2a1b/reports/integrity.json

$ cd ~/work/globex
$ decoy init claims-mask --source ~/data/globex/claims.parquet
Wrote pipelines/claims-mask/pipeline.yaml (1 table: claims; source /home/ana/data/globex/claims.parquet)
Next: decoy run claims-mask

$ decoy init providers-mask --source ~/data/globex/providers.csv
Wrote pipelines/providers-mask/pipeline.yaml (1 table: providers; source /home/ana/data/globex/providers.csv)
Next: decoy run providers-mask

$ cd ~/work
$ decoy --project globex run --all
Pipeline claims-mask (project /home/ana/work/globex)
Pipeline providers-mask (project /home/ana/work/globex)
  pipeline        exit  output folder
  claims-mask     0     globex/out/claims-mask/20261109T141702000001Z-5b1c09e4/
  providers-mask  0     globex/out/providers-mask/20261109T141705000001Z-c2d8f310/
All 2 pipelines exited 0.

$ decoy run claims-mask
error: layout.project_not_found: no Decoy project at or above /home/ana/work
  hint: cd into a project, pass --project DIR, or give the pipeline's path

$ decoy project list
Projects in /home/ana/work
  folder  root                     pipelines
  acme    /home/ana/work/acme      2
  globex  /home/ana/work/globex    2

$ decoy --project acme run members-mask
Pipeline members-mask (project /home/ana/work/acme)
  members  10,000 rows  masked
Output folder: acme/out/members-mask/20261109T141810000001Z-91f0aa27/
  members: acme/out/members-mask/20261109T141810000001Z-91f0aa27/members.masked.csv
latest -> acme/out/members-mask/20261109T141810000001Z-91f0aa27/

$ ls acme/out/members-mask/
20261109T141502000001Z-3f9c2a1b  20261109T141810000001Z-91f0aa27  LATEST  PIPELINE  latest
$ cat acme/out/members-mask/LATEST
20261109T141810000001Z-91f0aa27

$ decoy --project acme report fidelity ~/data/acme/members.csv acme/out/members-mask/latest/members.masked.csv --config members-mask
Fidelity: grade B (overall 0.87)
Report: acme/out/members-mask/20261109T141810000001Z-91f0aa27/reports/fidelity.json
```

What the user never sees: a `pipeline.yaml` in `~/work`, a `logs/` folder, an output file beside a YAML, or
one client's output in the other's folder. Each `out/<name>/` holds the `PIPELINE` claim written by the
first run. The report input given through `latest` is resolved before the report path is made, so the
printed path names the real run folder. The grade and score shown are placeholders; AT-26 asserts paths, the
tree and exit codes, not report numbers.

## 5. Command map (every command that takes a config path or writes a file)

| Command | Today | After |
|---|---|---|
| `decoy run CONFIG` | YAML path; relative targets beside the YAML; quarantine relative to the current folder; overwrite in place | path or name; relative targets and quarantine in `out/<p>/<run-id>/`; `latest` on exit 0; `--out-dir` for a fixed folder |
| `decoy run` (no argument) | usage error | runs the only pipeline, else lists and exits 1 |
| `decoy run --all` | n/a | every pipeline, one process each, worst exit code |
| `decoy validate config/compile/preflight CONFIG` | YAML path | path or name; layout gate findings; preflight checks placed paths |
| `decoy validate compile --output F` | as typed | unchanged (typed) |
| `decoy validate CONFIG` (default) | YAML path | path or name; layout gate findings |
| `decoy explain TOPIC` | topic name | unchanged (no pipeline argument) |
| `decoy tokenize CONFIG` | YAML path; targets beside the YAML | path or name; run folders like `run` (Q10) |
| `decoy detokenize CONFIG ...` | default `<input>.detokenized.<ext>` beside the input | path or name; default unchanged (beside the input, so in the run folder for a run output) |
| `decoy unmask CONFIG MASKED` | default `<input>.unmasked.<ext>` beside the input | path or name; default unchanged; declared format recognized through `owning_run` |
| `decoy subset CONFIG --output F` | YAML path; output as typed | path or name; output unchanged (typed) |
| `decoy report fidelity SRC OUT --config C --report-out F` | config path; report to stdout or `F` | config path or name; with no `--report-out` and `OUT` in a run folder, also `<run>/reports/fidelity.json` |
| `decoy report integrity MASKED --config C --output F` | config path; stdout or `F` | config path or name; with no `--output` and `MASKED` in a run folder, also `<run>/reports/integrity.json` |
| `decoy report vault --config C` | config path | path or name |
| `decoy report show/render/verify/diff` | manifest path; `--output` as typed | unchanged; every stored path validates through the manifest-aware resolver, and `verify` and `diff` use its resolved files (3.9) |
| `decoy run --evidence-out F`, `--vault F` | as typed | unchanged (typed); manifest paths project-relative |
| `decoy init [FILE] -o F` | `./pipeline.yaml`; paths copied as typed | `decoy init NAME [--source FILE]` writes `pipelines/NAME/pipeline.yaml` in the project; outside a project refused unless `-o`; `-o` paths relative to the YAML |
| `decoy project new DIR` | n/a | creates a project |
| `decoy project show`, `decoy project list` | n/a | read only |
| `decoy fit SOURCE` | `<source>.snapshot.json` beside the source | unchanged (Q6); name from `side_file_default` |
| `decoy scan FILE --output F` | as typed; engine `logs/` in the current folder | unchanged; no `logs/` |
| `decoy demo` | absolute targets in the demo folder; `logs/` | unchanged targets; no `logs/` |
| `decoy schema`, `decoy show`, `decoy list` | stdout or typed path | unchanged |
| `decoy ci check --output F` | as typed; `chdir` for the engine log | unchanged; no `chdir` |
| `decoy upgrade`, `decoy doctor`, `decoy info` | no config, no output file | unchanged |
| `mask()` (API) | targets beside the config; `out=` rewrites targets | `RunLayout.fixed`: `out=` relative to the current folder, else today's base |

## 6. Behavior

| Case | Today | After |
|---|---|---|
| `targets.orders.path: orders.csv`, YAML `proj/pipelines/orders/pipeline.yaml`, marker in `proj/` | `proj/pipelines/orders/orders.csv`, overwritten | `proj/out/orders/20261109T041500000001Z-1a2b3c4d/orders.csv`; `LATEST` and `latest` updated |
| same YAML as `proj/jobs/orders.yaml`, no `name:` | beside the YAML | `proj/out/orders/<run-id>/orders.csv`, claim `out/orders/PIPELINE` = `jobs/orders.yaml` |
| then `proj/old/orders.yaml`, no `name:` | n/a | `proj/out/orders-<6 hex>/<run-id>/orders.csv` (derived name, hash suffix) |
| then `proj/old/orders.yaml` with `name: orders` | n/a | exit 1 `layout.pipeline_name_collision` |
| `proj/pipelines/orders/pipeline.yaml` with `name: sales` | n/a | exit 1 `layout.pipeline_name_mismatch` |
| YAML with no marker anywhere above it | beside the YAML | `<yaml dir>/out/<name>/<run-id>/orders.csv` |
| `path: /data/delivery/orders.csv` | that path | that path |
| `path: sub/orders.csv` | `<yaml dir>/sub/orders.csv` | `<run folder>/sub/orders.csv` |
| `path: ../../../x.csv`, `path: .`, `path: ""` | written outside, or an error at write | validate and run exit 1, `layout.output_path_escapes` |
| `quarantine.output_path: q.jsonl` | the current folder | `<run folder>/q.jsonl`; config hash unchanged |
| run exits 3 after one of two targets | one file beside the YAML | one file in the run folder; `latest` unchanged; `--json` has that file in `outputs[]` and has `output_dir` |
| `decoy run members-mask` from `proj/a/b/` | n/a | finds `proj/pipelines/members-mask/pipeline.yaml` |
| `decoy run membrs-mask` | n/a | exit 1 `layout.pipeline_unknown`: "known: members-generate, members-mask; did you mean members-mask?" |
| `decoy run ./members-mask` with no such file | file not found (exit 2) | file not found (exit 2; a path token is never a name) |
| `decoy run p.yaml --out-dir build/` | n/a | `build/orders.csv`, no `latest` |
| `decoy unmask members-mask out/members-mask/latest/x.masked.csv` | n/a | declared format; output `out/members-mask/<run-id>/x.masked.unmasked.csv` |
| `decoy init data.csv` in an empty folder | `pipeline.yaml` here | exit 1 `layout.project_not_found`, hint `decoy project new .` |
| `decoy init data.csv` inside a project | `pipeline.yaml` here | `pipelines/data/pipeline.yaml`, source relative to it if inside the project |
| `decoy init -o sub/p.yaml data.csv` | source not found at run | `sub/p.yaml`, source `../data.csv` |
| `decoy scan data.csv`, `decoy run p.yaml` | `logs/decoy_engine.log` in the current folder | no `logs/` |
| evidence for a relative target | wrong file or `None` | the placed file, recorded project-relative with `path_base: project` |
| `decoy report verify ev.json` from another folder | resolves against the current folder | resolves against the project root |
| `decoy report diff a.json b.json --require-data --json` from another folder | existing outputs reported missing | exit 0 after each output resolves against its manifest's project root |

## 7. Enumerations (from the code at CLI `ed5de4ed`, engine `44d6afe2`)

### 7.1 Routes (each writer and its placement)

| Writer | Today (file:line) | After |
|---|---|---|
| whole-table targets (`run`) | `_write_mask_outputs` `run.py:1645-1662` to `write_targets` `_targets.py:401-422` | `write_targets(config, outputs, layout)` |
| chunked targets (`run`) | `run.py:1493`, `:1502` to `write_chunked_output` `_targets.py:425-462` | takes `layout` |
| `tokenize` targets | `tokenize.py:363` | `layout` |
| `demo` targets | `demo.py:272-280` (absolute already, `demo.py:116`, `:496`) | `RunLayout.fixed(demo folder)`; same files |
| `mask()` API | `api.py:501`, `:556`, `_apply_out_override` `api.py:290-307` | `RunLayout.fixed` (3.8) |
| quarantine JSONL (engine) | `quarantine.py:254-274` | `run_pipeline(quarantine_path=layout.place_quarantine(...))` |
| `--evidence-out`, `--vault` | as typed | unchanged (typed) |
| `unmask`, `detokenize` defaults | `unmask.py:279`, `tokenize.py:608-613` | `side_file_default`, same place |
| `fit` default | `fit.py:495` | `side_file_default`, same place |
| report JSON | `report.py:1971` `--output`, fidelity `--report-out` | typed as today; else `<run>/reports/<kind>.json` when the input is in a run folder |
| `init` output | `init.py:471`, `:537`, `:618`, `:634`, `:670` | `cli/project/_scaffold.py` unless `-o` |
| `project new` files | n/a | `_atomic` create-once calls via `_project.py` |
| `scan --output`, `report show/render/diff --output`, `validate compile --output`, `schema`, `ci check --output`, `subset --output` | as typed | unchanged |
| engine log file | `internal/logging.py:111` | off (E2) |

### 7.2 Exit paths that touch the run folder

| Exit | Run folder | `LATEST` |
|---|---|---|
| gate refusal (1, 5) | never created | unchanged |
| 0 | kept | moved if this run id sorts after the current one |
| 2 (warnings), 4 (findings) after writes | kept | unchanged |
| 3 during writes | kept if not empty | unchanged |
| interrupt (Ctrl-C) | kept if not empty | unchanged |

### 7.3 FK shapes

N/A: placement reads only target, quarantine and side-file paths and pipeline names; no foreign key or
relationship is read or changed.

### 7.4 Path roles

- input, resolved against the YAML folder: sources, `--duckdb-source`, `snapshot_file` (row 24o);
- output, placed: file targets, `quarantine.output_path`, report JSON with no flag;
- typed on the command line, relative to the current folder: every `--output`, `--report-out`,
  `--evidence-out`, `--vault`, `--out-dir`, `--project`, `mask(out=...)`, and the masked-file arguments;
- a pipeline token: a path (above) or a name looked up under `<root>/pipelines/`.

### 7.5 Pipeline token forms

| Token | Meaning |
|---|---|
| an existing file | path |
| `-` | stdin, where accepted today |
| has a separator, or ends `.yaml` or `.yml` | path; if it does not exist, file not found (exit 2) |
| anything else | name; must pass `is_valid_pipeline_name` before any join |

### 7.6 Fields added

- engine strict `PipelineConfig.name: str | None` (optional, excluded from dumps when absent);
- engine `run_pipeline(..., quarantine_path: str | None = None)`, strict at runtime and applied after the
  config hash;
- run `--json`: conditional `output_dir` and `outputs` per 3.6.1 C (`{table, path}` for target files actually
  published), plus `project` (`root`, `implicit`, `skipped`) and `pipeline` (`name`, `yaml`, `given_as`);
- `run --all --json`: `{"pipelines": [<child payload>...], "exit_code": N}`;
- evidence manifest: exact string `path_base: "project"` when paths are project-relative;
- marker: `kind: decoy-project/v1`.

### 7.7 Output surfaces

- the run summary (pipeline, project, run folder, `latest`);
- run `--json` (7.6);
- gate findings in `validate`, `ci check` and `run` (layout codes);
- warnings on stderr (`latest`, `.gitignore`, nested project, config under `out/`);
- `decoy project show`, `decoy project list`, `run --all` tables and their `--json`;
- the unknown-name message (names and the close match);
- CHANGELOG and `docs/project-layout.md`.

No surface prints a row value: layout messages name folders, files, pipeline names, codes and exit codes
only.

## 8. Class table

| # | Class | Applies here | Structure that closes it | Sentry or property test | Mutation that turns it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | layout messages; the quarantine, unmasked and report files hold rows or row-derived values | messages come from the value-free registry; run folders are 0700; row files stay in run folders or typed locations; `out/.gitignore` holds `*` | AT-12 canary (stdout, stderr, `--json`, every refusal), AT-15 | MP11: a target's first row in the escape message |
| 2 | Cleanup missing on an exit path | an empty run folder after an early failure; a temp link after a failed swap; a temp file after a failed claim | `abandon()` removes an empty folder; `replace_symlink` removes its temp name on failure; the claim's temp is removed by `_atomic` as for every write | AT-6 failure cells, AT-7 no-temp-left cell, `tests/unit/test_atomic.py` link cells | MP12: skip `abandon()` |
| 3 | State and ordering | `latest` moved before the outcome is known, or moved back by an older run; the folder made before the gate; JSON infers publication from an opened folder | microsecond run ids; strict shared parser; `commit_latest` only on exit 0 and only forward; `open` after the gate; one publication ledger | AT-5, AT-6, AT-32 | MP4: `commit_latest` in a `finally`; MP15: drop the run id comparison; MP24: derive JSON from the opened layout |
| 4 | Route parity and silent fallback | `run`, `tokenize`, `demo`, `mask()`, chunked writes placing differently; `validate` passing what `run` refuses; one command taking a name and another not | one `RunLayout` for both table writers; one gate; one token callback | AT-3 per route, AT-4 per command, AT-18 per command, G-ONE-OUTPUT-PLACE (c), G-ONE-PIPELINE-ARG | MP1, MP5, MP16: `subset` loses the callback |
| 5 | Referential integrity | the claim naming its YAML; listed names resolving to members; `LATEST` naming a run folder; `owning_run` matching a target; manifest paths naming files; two outputs naming one destination | claim by exclusive create; list only validated pipeline folders; strict `LATEST`; `owning_run`; one manifest-aware path resolver guarded by G-ONE-MANIFEST-PATH; one resolved-destination collision check | AT-7, AT-9, AT-11, AT-25, AT-31 | MP7, MP9, MP3, MP21, MP23 |
| 6 | Untrusted producer | a marker in a parent folder written by another user; a hand-written marker; a pipeline name from a stem or folder; a name token on the command line | owner check on the opened descriptor; `kind` check; one strict name rule; name lookup remains physically under `pipelines/` | AT-1, AT-2 property, AT-19 | MP10: skip the owner check; MP18: join a name without the rule check |
| 7 | Check then use on a path (TOCTOU) | claim checked at the gate, written at `open`; run folder clash; marker checked then read | claim re-checked at `open` and made by hard-link `CREATE_ONCE`; private-directory exclusive create; `fstat` on the descriptor read; physical containment | AT-4, AT-5 clash cell, AT-7 race cell, AT-1 swap cell | MP13: non-exclusive directory create |
| 8 | Weak tests and overclaimed evidence | a sweep that checks only the current folder; a placement test that only checks a file exists | AT-12 snapshots the project, the current folder and `$HOME` stand-in and asserts the full set of new paths; AT-3 asserts the exact path and no other copy | AT-3, AT-12, AT-26 | MP1 |
| 9 | Behavior-preserving refactor drift | side-file names moved; `ci/engine_logging.py` simplified; distribution link swap moved; config parameters gain one callback | moved verbatim; existing tests stay green unchanged | `test_unmask_command.py`, `test_tokenize_cli.py`, `test_fit_command.py`, `test_ci_output_isolation.py`, distribution layout tests, every command's existing path-argument tests | MP2 |
| 10 | Frozen contract drift | run `--json`, evidence manifest and `ci-contracts.md`, engine schema and registry, target location, `init` | conditional JSON fields tied to the publication ledger; `path_base` additive with the old rule kept; engine dump identity without `name`; CHANGELOG breaking entries | E1 dump identity, AT-8, AT-9 old-manifest cell, AT-32, reason minor fixture | MP14: emit `name: null` in dumps; MP24: render an opened folder as published |

All mutations MP1 to MP24 are listed in section 9.

## 9. Acceptance tests (red first)

CLI unit tests in `tests/unit/project_layout/`, e2e in `tests/e2e/project_layout/` (CLI `tests/unit/` has
39 flat modules and `tests/e2e/` 81, so named folders per CODEMAP `:59-60`). Engine tests in
`tests/unit/config/` and `tests/unit/internal/`.

- **AT-1** Root: a marker two levels up is found; the nearest of two wins; none gives the YAML folder with
  `implicit`; the walk stops after a `.git` folder and after a `.git` file, at a device change (patched
  `st_dev`), and below `$HOME` (a marker in a patched `$HOME` is not found); a marker owned by another uid
  exits 1 `layout.project_marker_untrusted` before a source-read spy fires; a symlinked marker is refused
  (`O_NOFOLLOW`); a marker swapped for another file after `open` is judged by the opened descriptor;
  `kind: other` or bad YAML exits 1 `layout.project_marker_invalid`; a `decoy.yaml` with no `kind` is skipped
  and listed in `project.skipped`.
- **AT-2** Name: `pipelines/<dir>/` gives `<dir>`; an invalid declared `name:` and an invalid `<dir>` exit 1
  `layout.pipeline_name_invalid`; a stem `My Pipeline` derives `My-Pipeline-<6 hex>`; `CON.yaml` derives
  `CON-<6 hex>`; the reserved-name set includes superscript device forms but allows `COM0` and `LPT0`;
  a trailing newline fails; bool, int and other non-string `name` values fail without coercion; the engine
  and CLI give the same verdict on a property-generated set, and every derived name passes the rule.
- **AT-3** Placement: a relative target lands at `out/<p>/<run-id>/<path>` through `run` (whole and chunked),
  `tokenize`; `demo` writes the same files as on `main`; `mask(path)` with no `out=` writes where `main`
  does, `mask(path, out="o")` writes under `./o/`, `mask(dict)` writes under the current folder; csv,
  parquet and fixed-width each; an absolute target lands at its path; S3 and GCS targets reach the same
  uploader arguments as on `main`; no second copy anywhere in the tree.
- **AT-4** Escape: `../../x.csv`, `.`, `""`, `sub/` and a quarantine `../../q.jsonl` refused by `validate`,
  `ci check` and `run`, exit 1 `layout.output_path_escapes`, before a source-read spy fires; `a/../b.csv`
  accepted; a symlink ancestor cannot leave the physical project output or typed `--out-dir`; explicit
  `--chunked` with enabled quarantine refuses before the source-read spy; `place_target` refuses directly.
- **AT-5** Run id uses `re.fullmatch(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}(?:[0-9a-f]{4}){0,6}", value)`; a forced prefix clash gives
  two folders; two starts in one second sort by their six fractional digits; the evidence `run_id` equals
  the invocation id in the folder name; `mint_invocation_id` is called once per command (spy).
- **AT-6** `latest`: moves on exit 0 only; exit 2, 3 and 4 after writes and an interrupt leave it; an older
  run id finishing last does not move it back; `LATEST` holds the folder name; on POSIX `latest` is a
  relative symlink; a file named `latest` in the way gives `layout.latest_link_failed` and exit 0; on
  Windows (lane when WIN-RUNNER exists) only `LATEST`; invalid `LATEST` warns `layout.latest_invalid` and
  the next clean run repairs it; a planted `LATEST` symlink is replaced and its target is unchanged.
- **AT-7** Claim: the first run writes `PIPELINE`, for a `pipelines/` pipeline and a free-standing YAML
  alike; a second YAML declaring the same name exits 1 `layout.pipeline_name_collision` before any write; a
  second YAML deriving it gets the hash suffix; with `pipelines/orders/` present (run or not),
  `jobs/orders.yaml` without `name:` writes to `out/orders-<6 hex>/` and with `name: orders` exits 1; when
  `jobs/orders.yaml` ran first, `pipelines/orders` exits 1 naming the claim; two processes racing the first
  claim through `write_atomic(..., CREATE_ONCE)` leave one complete winner, which the loser reads, and no
  temp file; a patched `ATOMIC_NOCLOBBER_UNSUPPORTED` exits 3 naming
  the mount; `Orders` and `orders` collide on a case-insensitive filesystem; a config with only absolute
  targets writes no claim and no `out/`.
- **AT-8** Surfaces: the summary prints project, run folder and `latest`; `--json` has conditional
  `output_dir` and `outputs[]` per 3.6.1 C, plus `project` and `pipeline`; a failure after a publish lists
  only the files already published, while a failure before publication and a gate refusal have neither
  conditional field; human paths are relative under the current folder and absolute otherwise.
- **AT-9** Evidence: output fingerprints are the placed files (non-null, equal to a re-hash); input
  fingerprints resolve sources against the YAML folder; the config fingerprint is equal across two runs.
  Every row below starts with `cwd != project root`, keeps the output files present only at their recorded
  project-relative locations, and exports `DECOY_PROJECT` for another project. This proves that no current
  consumer falls back to the current folder or the ambient project. Each command test spies on
  `resolve_manifest_path`, asserts that every stored output reaches it, and asserts that each returned path
  is the existing file below the correct project root.

  | Consumer | Outside-project acceptance |
  |---|---|
  | `evidence.verify_manifest_issues` | Pass the evidence file and explicit project hint; it returns no missing-output issue and every output fingerprint re-hashes the placed file. |
  | `decoy report show --json` | Exit 0 after `read_manifest` accepts every stored path through the resolver, and return every recorded output entry unchanged. It renders metadata and does not dereference an output file. |
  | `decoy report render` | Exit 0 after the same resolved-path validation and write the requested metadata-only report outside the project. |
  | `decoy report verify --project <root> --json` | Exit 0 with status `ok` and no missing pipeline, input or output issue. |
  | `decoy ci check` evidence adapter | Exit 0 from its typed CI manifest and project context, with the evidence check passing and no missing-output finding. |
  | `decoy report diff A B --require-data --json` | Exit 0 with status `ok`, data comparison present, and an empty `missing_files`; each side resolves against its own manifest's project root. |

  The remaining AT-9 cells hold: no marker and no typed hint refuses; an implicit-project run records
  absolute paths; a manifest without `path_base` uses the old current-folder rule; missing or unknown
  `schema_version`, an unknown `path_base`, or a wrong field type refuses; extra fields are tolerated; a
  rehashed `../` path or a symlink out of the project refuses; evidence from project A read under project B
  refuses; a null required field or a top-level list refuses without a crash.
- **AT-10** Config untouched: the loaded dict deep-equals and keeps the same nested `id`s before and after
  the run; the quarantine file lands in the run folder for normal `run`, `tokenize` and `mask()`, and on
  each engine route (`full_frame`, `sequential`, `out_of_core`, engine cells in E2); an absolute
  quarantine path is honored; the plan hash is equal for two runs (quarantine hashed, override applied after
  the hash); `quarantine_path` rejects bool and other non-strings before a source read.
- **AT-11** Side files: `unmask` and `detokenize` of a run's fixed-width target, by run path and through
  `latest`, use the declared layout; a file at the old YAML-folder place still does; default output is
  beside the input with the `latest` link resolved first; `detokenize`'s refuse-to-overwrite rule holds.
- **AT-12** No stray files: with the current folder outside the project and a patched `$HOME`, run each
  command with default flags (`project new`, `init`, `scan`, `validate`, `run`, `run --all`, `tokenize`,
  `unmask`, `detokenize`, `report fidelity`, `report integrity`, `demo`, `fit`); snapshot the project, the
  current folder and `$HOME`; every new path is in the guarantee 8 set; a canary value in the source never
  appears on stdout, stderr or in `--json`, including every refusal in the Failure modes table.
- **AT-13** Engine log: `run`, `scan` and `demo` create no `logs/`; an engine warning still reaches stderr;
  `decoy ci` isolation tests stay green without the `chdir`.
- **AT-14** Init `-o`: `-o sub/p.yaml data.csv` writes source `../data.csv` and runs; `-o -` writes no file.
- **AT-15** `out/.gitignore` holds `*` after the first run in a project whose `out/` the user made by hand;
  a user-edited one is kept; an unwritable one warns `layout.gitignore_write_failed` and the run exits 0;
  under umask 0 and 0777 each run folder is 0700; a mode-verification failure exits 3 before a data write.
- **AT-16** Preflight: no overwrite or missing-folder warning for a relative target in a fresh project run;
  an existing absolute target still warns; under `--out-dir`, an existing resolved relative target warns.
- **AT-17** Windows budget: with a patched `os.name`, a placed path over 259 characters with the 55-character
  run id exits 1 `layout.path_too_long`; on POSIX the same path passes.
- **AT-18** Name argument per command: for every command in 3.4, a name from a subfolder of the project gives
  the same result as the path from the root (`run`, `validate`, `validate config`, `validate compile`,
  `validate preflight`, `tokenize`, `detokenize`, `unmask`, `subset`, `report fidelity --config`, `report
  integrity --config`, `report vault --config`); for each, an unknown name exits 1 with
  `layout.pipeline_unknown` inside the command's `--json` envelope; `decoy explain modes` still works.
- **AT-19** Token rules: an existing extension-less file named like a pipeline is a path (`given_as: path`);
  `./missing.yaml` and `x/y` give file not found (exit 2); `../x` where `../x` is a folder is a path, never
  joined under `pipelines/`; `a b` exits 1 `layout.pipeline_name_invalid`; an unknown name exits 1
  `layout.pipeline_unknown` with all names and the close match; a name with no project exits 1
  `layout.project_not_found`; a symlinked pipeline folder or YAML that resolves outside physical
  `pipelines/` is refused and omitted from listing and completion.
- **AT-20** Name rule: `pipelines/orders/pipeline.yaml` with `name: sales` exits 1
  `layout.pipeline_name_mismatch`; with `name: orders` or no `name:` it runs into `out/orders/`.
- **AT-21** `run` with no argument: one pipeline runs; none exits 1 with the init hint; two exit 1 and list
  both; outside a project exits 2 with the usage message and the hint.
- **AT-22** `run --all`: three pipelines run in name order, each in its own process (spy on the child
  command line); a failing middle one does not stop the third; the exit code follows the 3, 5, 1, 4, 2, 0
  order (cells for each pair); a child killed by a signal, a child exiting 9, and a child printing broken
  JSON each make the summary exit 3; each child command line carries `--project <root>`; `--evidence-out`
  with `--all` exits 1; `run NAME --all` exits 1; `--json` lists every child payload.
- **AT-23** Project selection: `--project DIR` from outside resolves names in `DIR`; `DECOY_PROJECT` the same;
  `--project` beats the variable, the variable beats the walk; `--project` with a path argument from another
  project exits 1 `layout.project_mismatch`; `DECOY_PROJECT` with such a path is ignored; `--project` on a
  folder with no marker exits 1 `layout.project_not_found`.
- **AT-24** `decoy project new`: writes the four entries; a second call adds only missing ones and says
  "already a project"; a concurrent create leaves one complete valid marker; an existing invalid marker
  refuses; refuses a patched `$HOME`, its parent and `/`; inside another project warns
  `layout.project_nested`; `.decoy/.gitignore` equals LIB 4.9's content.
- **AT-25** `decoy project show` and `list`: show lists only valid `pipelines/*/pipeline.yaml` members with
  last run and last clean run from the folders (status `-`); a free-standing claimed YAML is not listed;
  malformed run folders and `LATEST` entries are ignored with the specified warning; list shows projects
  one level down with pipeline counts; both `--json`.
- **AT-26** Walk-through: section 4 as one e2e test (paths under `tmp_path`, `$HOME` patched, time and
  invocation id seeded), asserting every printed path and the final tree byte for byte.
- **AT-27** Completion: `pipeline_names` returns public `typer.models.CompletionItem` entries for names with
  the typed prefix and a file item, reads `--project` already on the line, and returns no names outside a
  project. A sentry rejects `typer._click` and other private imports.
- **AT-28** Init inside a project: `init members-mask --source <in-project file>` writes a relative source;
  an outside source is absolute; the target is `members.masked.csv`; the config runs; `init data.csv`
  derives the name `data`; an existing `pipelines/NAME/pipeline.yaml` needs `--yes`; outside a project exits 1
  with the `project new` hint; inside a project, no argument keeps the wizard and prompts for the name;
  outside a project, no argument and no `-o` refuses before prompts.
- **AT-29** Reports: `report integrity` on a run output with no `--output` writes
  `<run>/reports/integrity.json` and prints it; with `--output` only the typed file is written; on a file
  outside any run folder no file is written; same three cells for `report fidelity`.
- **AT-30** P4 gate matrix (`tests/e2e/project_layout/test_layout_gate.py::test_layout_gate_matrix`): one
  parametrized row for every cell in 3.6.1 A asserts runs, skipped or refused, its exit and code, and that a
  source-read spy stays empty on refusal. Red-first inputs include a path config below an invalid marker with
  a valid `--out-dir` (must run), the same config through `validate preflight` (must refuse), a `--rows`
  generate preview below the invalid marker (must run), a Windows-over-budget destination under `--out-dir`
  (must refuse), an existing fixed-directory target (must warn), and a `DIR` that is a regular file (must
  refuse 1 `layout.output_dir_unusable`). Mutation MP22 drops the placement context at `check_before_run`;
  the invalid-marker `--out-dir` cell must turn red.
- **AT-31** Destination collision
  (`tests/e2e/project_layout/test_layout_gate.py::test_resolved_output_collisions_refuse_before_source`):
  red-first configs use two tables targeting `masked.csv`, a target plus enabled quarantine targeting one
  file, two equal absolute targets, case-only names under a case-insensitive parent, and two spellings through
  a symlink ancestor. Cells cover project placement, `--out-dir`, direct `validate preflight`, and a run whose
  `--evidence-out` or `--vault` aliases a target or each other. Every cell exits 1 with
  `layout.output_path_collision`, names only the two config locations or flag names, fires before the
  source-read spy, and leaves every destination absent or unchanged. Mutation MP23 removes the quarantine
  and typed-file entries from the single collision enumeration; the corresponding cells must turn red.
- **AT-32** JSON publication
  (`tests/e2e/project_layout/test_run_surfaces.py::test_json_location_fields_follow_publication`): red-first
  cells cover a valid `--out-dir` plus gate refusal, placed and fixed-directory failures before the first
  publish, a two-target failure after the first publish, normal success, empty chunked success, and
  absolute-target-only success. They assert the exact presence or absence of `output_dir` and `outputs`, and
  exact absolute entries when present. Mutation MP24 derives either field from `layout.describe()` instead
  of the publication ledger; the refusal and empty-success cells must turn red.
- **G-ONE-OUTPUT-PLACE** (`tests/sentry/io_policy/test_output_placement.py`, in the sentry manifest): (a)
  normalized AST imports, aliases and qualified calls to `resolve_path` are allowed only at input sites in
  a shrink-only baseline
  (`tests/sentry/baselines/output-placement-allow.json`: file, function, count); (b) path-building calls
  (`with_suffix`, `/` joins, `Path(...)` of an f-string) that use the default-name literals (`.unmasked`,
  `.detokenized`, `.snapshot.json`, `.masked`) or the `out` folder literal appear only in
  `cli/io/_layout.py` and `cli/project/_scaffold.py`; (c) `write_targets` and `write_chunked_output`
  annotate their placement parameter as `RunLayout`.
- **G-ONE-MANIFEST-PATH** (`tests/sentry/io_policy/test_manifest_path_resolution.py`, registered in
  `tests/sentry/test_sentry_manifest.py`): an AST walk over `src/decoy/cli` follows direct, imported-as and
  module-qualified `pathlib.Path`/`PurePath` and `os.path` calls, `/` joins, and filesystem or data-reader
  calls through one-hop assignments. It marks `pipeline_path` and each `path` below
  `input_fingerprints` or `output_fingerprints` as stored manifest paths. The only path-building allowlist
  entry is exact identity
  `(src/decoy/cli/evidence.py, resolve_manifest_path)`. The only resolver-call allowlist entries are exact
  identities `(src/decoy/cli/evidence.py, read_manifest)`,
  `(src/decoy/cli/evidence.py, verify_manifest_issues)` and
  `(src/decoy/cli/report.py, compare_data)`. `report show` and `report render` are listed as metadata-only
  consumers with no filesystem call and no resolver exemption. Any other module or function that turns a
  marked value into a filesystem path fails, so a future consumer cannot silently bypass the choke point.
  Self-tests seed `Path(entry["path"])`, aliased `Path`, `pathlib.Path`, `os.path.join`, a `/` join and a
  one-hop alias in a scratch tree; every realistic spelling turns the sentry red. A seeded direct path in
  `report.py:compare_data` also turns AT-9 `report diff --require-data --json` red from outside the project.
  Removing any real resolver caller makes the exact allowed-call set fail, so the allowlist cannot hide
  an unchecked forwarding helper.
- **G-ONE-PIPELINE-ARG** (`tests/sentry/io_policy/test_pipeline_argument.py`, in the manifest): walk the
  Typer app; every parameter named `config`, `pipeline_config` or `pipeline`, or whose help text says
  "pipeline YAML", has the same `parse_pipeline_token` callback, and the command function calls
  `resolve_pipeline` after output setup. Normalize direct, aliased and module-qualified forms. Reject
  private Typer imports. A shrink-only allowlist starts empty.
- **G-ONE-PROJECT-ROOT** (same file): no module outside `cli/io/_project.py` reads a file named
  `decoy.yaml` or walks `.parents` looking for one. Normalize import and call aliases.
- **G-ONE-LAYOUT-CODE** (`tests/sentry/io_policy/test_layout_errors.py`): no `layout.*` literal occurs in
  `src/` outside `_layout_errors.py`; every gate descriptor is exported through `decoy.cli.io` and appears
  in the derived CI gate set; consumers outside `cli/io` do not import its private modules.

Seeded mutations, each shown red against the named test: MP1 `write_targets` joins `config.parent` (AT-3,
AT-12, sentry (c)); MP2 inline `.unmasked` in `unmask.py` (sentry (b)); MP3 evidence fingerprints
`Path(tgt["path"])` again (AT-9); MP4 `commit_latest` in a `finally` (AT-6); MP5 skip the escape check
(AT-4); MP6 engine default log file restored (AT-13); MP7 skip the claim (AT-7); MP8 write the placed
quarantine path into the config dict (AT-10); MP9 `_targets.py` without `owning_run` (AT-11); MP10 skip the
owner check (AT-1); MP11 a row value in the escape message (AT-12 canary); MP12 skip `abandon()` (AT-6);
MP13 `mkdir(exist_ok=True)` (AT-5); MP14 `name: null` in dumps (E1 identity); MP15 drop the run id
comparison in `commit_latest` (AT-6); MP16 `subset` declares `config: Path` (G-ONE-PIPELINE-ARG, AT-18);
MP17 `run --all` runs children in-process (AT-22 process spy); MP18 join a name under `pipelines/` without
the rule check (AT-19); MP19 `pipelines/` runs skip the claim (AT-7 both-orders cells); MP20 add a
`layout.*` literal outside the registry (G-ONE-LAYOUT-CODE); MP21 restore `Path(entry["path"])` in
`report.py:compare_data` (G-ONE-MANIFEST-PATH and the outside-project AT-9 diff row); MP22 drop the output
placement context passed to the gate (AT-30); MP23 omit quarantine and typed side files from
`resolved_output_collisions` (AT-31); MP24 derive JSON location fields from an opened layout instead of the
publication ledger (AT-32).

## 10. Owner questions (recommended option taken)

Owner answers (Cam, 2026-11-09): "go with recommended". Every question below takes its recommended option.

1. **Escape.** Refuse (recommended: a relative path that leaves the run folder is the loose file the owner
   named; an absolute path delivers elsewhere) or warn.
2. **`name:` that differs from its `pipelines/` folder.** Refuse (recommended: one name for the folder, the
   output and LIB records; the fix is one line) or warn and use the folder.
3. **Pipeline list command.** `decoy project show` in a `decoy project` group (recommended: `decoy list`
   already lists engine registries; the group holds `new`, `show`, `list`) or top-level `decoy pipelines`
   and `decoy projects`.
4. **Retention of `out/`.** Never pruned in V1 (recommended, LIB class 4); `decoy clean` later (F1).
5. **`--out-dir`.** Include (recommended: scripts needing a fixed path keep working; small).
6. **`fit` default.** Unchanged, beside its source (recommended: `fit` has no pipeline).
7. **When `latest` moves.** Exit 0 only, and only forward (recommended).
8. **`decoy init` outside a project.** Refuse with the `decoy project new .` hint (recommended: no surprise
   project roots in `$HOME` or Downloads; `-o FILE` still works anywhere) or create a project in the current
   folder.
9. **`mask()` placement.** Fixed folder: `out=` relative to the current folder, else today's base
   (recommended: library callers need predictable paths and have no `latest` reader) or run folders.
10. **`tokenize` run folders.** Yes (recommended: it writes the pipeline's targets, so it follows `run`).
11. **Exit code for an unknown name and for `run` with several pipelines and no argument.** 1, usage
    (recommended: exit 2 is `EXIT_WARNINGS`, `exit_codes.py:49`, which CI scripts treat as "ran with
    warnings") or 2 as the addendum wrote.
12. **Reports into run folders.** Write `<run>/reports/<kind>.json` when the input is a run output and no
    output flag is given (recommended: the walk-through's "find reports" needs a place; stdout is unchanged)
    or stdout only.
13. **Walk ceiling.** Stop below `$HOME` (recommended: a marker in `$HOME` would capture every folder) or no
    ceiling.
14. **`decoy projects` workspace view.** V1 as `decoy project list DIR`, one level, no configuration
    (recommended: cheap) or V2.

## 11. Reuse inventory

| Need | Reused | Not built |
|---|---|---|
| Atomic files | `_atomic.write_local_target`, `WriteMode.REPLACE` | a second writer |
| Create once | `_atomic.write_atomic` or `_atomic.write_local_target` with `CREATE_ONCE` | a check-then-replace helper; an `O_EXCL` write on the final name |
| Atomic link swap | new `_atomic.replace_symlink` beside `_publish`; `distribution/layout.py` moves onto it | a second link swap |
| Table writes | `cli/io/_targets.py` writers | a writer per command |
| Input resolution | `_sources.resolve_path` | changes to it |
| Gate findings | `gate/_layers.py` config layer, `GateFinding`, `ci/rule_codes.py` | a separate check pass |
| Invocation id | `mint_invocation_id`, shared with evidence and LIB | a second id |
| Library root and `.decoy/.gitignore` | LIB `resolve_root` calls `find_project`; LIB writers call `ensure_decoy_dir` | a second root finder or gitignore writer |
| Completion | public Typer callbacks and `typer.models.CompletionItem`; `cli/completers.py` for the source | a private Click type; a per-command parser |
| Close match | `difflib.get_close_matches` | an edit-distance function |
| Name rule | engine `is_valid_pipeline_name` | a CLI copy of the pattern |
| Command groups | the Typer sub-app pattern of `report` and `validate` | a new dispatch |

## 12. Placement

| What | Where | Size | Why there |
|---|---|---|---|
| project root, marker, selection, `ensure_decoy_dir` | `src/decoy/cli/io/_project.py` (new) | about 220 | CODEMAP "Where things go": reader and writer support belongs in `cli/io/`; `cli/` is frozen |
| layout, placement context and collision check | `src/decoy/cli/io/_layout.py` (new in P2a, extended in P1b and P4) | P4 head 764, about +80, final below 900 | same; `resolved_output_collisions` sits beside the one output enumeration and reuses containment; no second resolver or new module |
| pipeline argument | `src/decoy/cli/io/_pipelines.py` (new) | about 220 | the argument resolves to a file the I/O layer reads |
| layout descriptors and public I/O API | `src/decoy/cli/io/_layout_errors.py` (new), `cli/io/__init__.py` | about 150 | the same CODEMAP row; one registry and public package boundary |
| private run directory | `src/decoy/_private_file.py` | about +35 | existing private file and permission choke point |
| `decoy project` group | `src/decoy/cli/project/` (new): `__init__.py` (Typer app), `_new.py`, `_show.py`, `_list.py`, `_scaffold.py`, `_run_all.py` | about 650 | CODEMAP is amended in the same slice; a subpackage avoids adding to the 32-module flat `cli/` package |
| link swap | `src/decoy/_atomic.py` | about +35 (482 to 517) | the one atomic module (CODEMAP `:48`) |
| manifest path resolver | `src/decoy/cli/evidence.py` | about +40 | beside the verify code it serves |
| manifest-path sentry | `tests/sentry/io_policy/test_manifest_path_resolution.py`; register in `tests/sentry/test_sentry_manifest.py` | about 120 | CODEMAP "Where Things Go" sentry rows `:53-54,67`; filesystem I/O policy sentries live in `tests/sentry/io_policy/`, and every sentry is registered in the merge-gate manifest |
| engine name field and rule | engine `config/_pipeline.py`, export in `decoy_engine/__init__.py` | about +25 | engine CODEMAP "Config schema"; the model owns its fields |
| engine quarantine keyword, log default | engine `execution/_pipeline.py:115`, `internal/logging.py` | about +30 | engine CODEMAP execution facade and internal support rows |
| unit tests | `tests/unit/project_layout/` (new) | about 700 | named folder (CODEMAP `:59-60`) |
| e2e tests | `tests/e2e/project_layout/` (new) | about 1300 | named folder |
| other I/O sentries | `tests/sentry/io_policy/test_output_placement.py`, `test_pipeline_argument.py`, `test_layout_errors.py` | about 350 | CODEMAP test policy row; I/O policy sentries live together |
| docs | `docs/project-layout.md` (new), `docs/cli-reference.md`, `docs/ci-contracts.md` | about 200 | user reference, frozen contract |
| CODEMAP rows | CLI `CODEMAP.md` | 8 rows | four `cli/io` modules, its public API, `cli/project/`, and two test folders |

At the P4 head the run command is already split under `cli/run/`. P4 changes `_context.py` (130 lines),
`_prepare.py` (482), `_errors.py` (314) and `_render.py` (216), each for its existing concern; it adds no
logic to a flat `cli/run.py`. The later `--all` loop remains in `cli/project/_run_all.py`. `report.py` is
2340 lines and gets call-site edits only in P5 and P9: the parameter type, the `resolve_pipeline` call, and a
call to `_layout.report_default_path`.

V2-LOG size: at the P4 head, `cli/io/_layout.py` is 764 lines and this remediation is expected to leave it
between 800 and 900; `cli/preflight.py` is already pinned at 891 and does not grow. Both are cleanup-pass
items under the owner size rule, not P4 blockers. No P4 file crosses 900 and no new module is added.

## 13. Frozen contracts touched

- **Target write location** (breaking, pre-GA): relative targets move into run folders. CHANGELOG
  "Changed (breaking)"; the summary and `--json` name the folder; `docs/project-layout.md` gives the ways
  out (absolute path, `out/<p>/latest/`, `--out-dir`).
- **`decoy init`** (breaking, pre-GA): writes `pipelines/NAME/pipeline.yaml` in a project; refused outside
  one without `-o`.
- **Pipeline arguments** (additive): every config argument accepts a name.
- **Run `--json`** (additive fields, conditional presence): `output_dir` and `outputs` follow 3.6.1 C;
  `project` and `pipeline` keep their prior presence and shapes.
- **Evidence manifest and `docs/ci-contracts.md`** (additive): `path_base: "project"`; the old rule kept for
  manifests without it; the reader requires exact `schema_version: "cli-local-1"`; `run_id` keeps its UUID4
  value and equals the invocation id embedded in the folder name.
- **Report commands** (additive): a report JSON in the run folder when no flag is given (Q12).
- **Engine `PipelineConfig` schema** (additive): optional `name`; byte-identical dump without it (E1 test).
  Registry gains `config.pipeline_name_invalid` (next free minor, renumbered at merge).
- **Engine public API** (additive): `is_valid_pipeline_name`, `run_pipeline(quarantine_path=...)`.
- **Engine log default** (breaking for a caller that read `logs/decoy_engine.log`, pre-GA): no file unless
  asked.
- **`_atomic.py` API** (additive): `replace_symlink`.
- **Gate codes** (additive, in the central layout registry and derived by CI): `layout.project_marker_invalid`,
  `layout.project_marker_untrusted`, `layout.project_not_found`, `layout.project_mismatch`,
  `layout.pipeline_unknown`, `layout.pipeline_name_invalid`, `layout.pipeline_name_mismatch`,
  `layout.pipeline_name_collision`, `layout.output_path_escapes`, `layout.path_too_long`,
  `layout.output_path_collision`, `layout.output_dir_unusable`, `layout.project_root_refused`. (Refusals raised by `resolve_pipeline` and `project new` use the same codes
  in the command's error envelope.) Runtime warnings (not gate codes): `layout.latest_invalid`, `layout.latest_link_failed`,
  `layout.latest_write_failed`, `layout.gitignore_write_failed`, `layout.project_nested`,
  `layout.config_inside_out`.

## 14. Slices

| Slice | Repo | Files | Size | Tests |
|---|---|---|---|---|
| E1 | engine | `config/_pipeline.py`, `decoy_engine/__init__.py`, `reasons/config/_part2.py`, `reasons/_registry.py`, reason manifest fixture, `docs/reasons.md`, `tests/unit/config/test_pipeline_name.py`, `tests/unit/test_public_api.py`, `CHANGELOG.md` (9) | about 190 | AT-2, strict wire types, dump identity and exact public API census first; full engine suite |
| E2 | engine | `execution/_pipeline.py`, `internal/logging.py`, `tests/unit/internal/test_quarantine_path.py` (one cell per route), `tests/unit/execution/test_r3_public_signature_freeze.py`, `tests/fileaccess/test_char_cli_logging.py`, `tests/fileaccess/test_policy_strace.py`, `tests/sentry/file_access_registry.toml`, `tests/sentry/baselines/wave-b-string-target-exempt.json`, `CHANGELOG.md` (9) | about 220 | build the context and hash first, then use `dataclasses.replace` with a copied effective config; route and strict-type cells first; update the existing default-log characterization, trace allowlist, registry and shrink-only baseline; full engine suite |
| R | both | engine release, CLI repin (claudeorchestrator) | | full CLI suite (dependency lock) |
| P1a | CLI | `_atomic.py`, `distribution/layout.py`, `tests/sentry/test_atomic_writer.py`, `tests/unit/test_atomic.py` (4) | about 120 | link cells first; T1 plus distribution layout tests; sentry shrink shown |
| P1b | CLI | `cli/io/__init__.py`, `cli/io/_project.py`, `cli/io/_layout.py` (extend: P2a created it; reuse `is_run_id`, `RunFolder` and `placed_path`, do not redefine), `cli/io/_layout_errors.py`, `_private_file.py`, `tests/unit/project_layout/__init__.py`, `test_project_root.py`, `test_layout.py`, `tests/unit/private_file/test_private_file.py`, `tests/sentry/io_policy/test_private_files.py`, `tests/sentry/io_policy/file_sinks.toml`, `tests/sentry/baselines/private-file-sinks.json`, `tests/sentry/io_policy/test_pipeline_argument.py` (root guard), `tests/sentry/io_policy/test_layout_errors.py`, `tests/sentry/test_sentry_manifest.py`, `CODEMAP.md` (16) | about 1100 (half tests) | AT-1, AT-2, AT-5, AT-15, AT-17, G-ONE-PROJECT-ROOT and G-ONE-LAYOUT-CODE first; update private-directory seeds and registry with the helper; T1 |
| P2a | CLI | `cli/io/_layout.py` (new: `is_run_id`, `RunFolder`, `owning_run(path, root, name)`, `placed_path`), `cli/io/_targets.py` (`input_format` calls them; the old compare is at `:203-217`), `tests/e2e/project_layout/__init__.py`, `test_owning_run.py` (4) | about 200 | AT-11 old-path and run-folder cells first; T1 plus `tests/e2e/cli_fmt` |
| P2b | CLI | `cli/io/_layout.py` (extend: `RunLayout`, `mint_invocation_id`, on top of P1b's project, claim and private-directory helpers), `cli/io/_targets.py`, `cli/run.py`, `cli/demo.py`, `cli/tokenize.py`, `api.py`, `tests/e2e/project_layout/test_run_placement.py`, `tests/unit/test_run_local_io_guard.py`, `tests/e2e/cli_fmt/test_target_format_dispatch.py`, `tests/e2e/test_vault_commit_order.py`, `tests/unit/cli_fmt/test_targets_format.py`, `tests/sentry/io_policy/test_output_placement.py`, `tests/sentry/baselines/output-placement-allow.json`, `tests/sentry/test_sentry_manifest.py`, `CHANGELOG.md` (14) | about 800 | AT-3, AT-5, AT-6, AT-7, AT-10 and initial G-ONE-OUTPUT-PLACE first; the four signature tests move to `RunLayout` in the same commit; full CLI suite |
| P3 | CLI | `cli/evidence.py`, `ci/adapters.py`, `cli/report.py` (`_load_manifest` uses the shared reader; `compare_data` resolves both manifests through the shared resolver), `cli/run/_evidence.py` (passes the evidence path), `docs/ci-contracts.md`, `tests/e2e/project_layout/test_evidence_paths.py`, `tests/sentry/io_policy/test_manifest_path_resolution.py`, `tests/sentry/test_sentry_manifest.py`, `CHANGELOG.md` (9) | about 720 | AT-9 consumer matrix and G-ONE-MANIFEST-PATH first; run the sentry's seeded spellings and the outside-project `report diff --require-data --json` mutation on the final head; full CLI suite (frozen contract) |
| P4 | CLI | `cli/gate/_layers.py`, `ci/rule_codes.py`, `cli/preflight.py` (call site only, 891-line pin unchanged), `cli/run/_context.py`, `_prepare.py`, `_errors.py`, `_render.py`, `cli/run/_execute.py` (pass the publication ledger to the two writer call sites only), `cli/run/_flow.py` (only to move the `--out-dir` directory creation after the gate), `cli/io/__init__.py` (exports), `cli/io/_layout.py`, `_layout_errors.py`, `_targets.py` (publication mapping only), `tests/e2e/project_layout/test_layout_gate.py`, `test_run_surfaces.py`, `test_run_placement.py` and `tests/unit/project_layout/test_layout.py` (call updates for the changed `layout_issues` signature only), `docs/cli-reference.md`, `CHANGELOG.md` (19) | about 800; `_layout.py` remains below 900 | AT-4, AT-8, AT-16, AT-30, AT-31 and AT-32 first; MP22 to MP24 red; full CLI suite (`--json` contract) |
| P5 | CLI | `cli/io/_pipelines.py`, `cli/io/__init__.py`, `__main__.py` (`--project`), `cli/completers.py`, `cli/run.py`, `cli/validate.py`, `cli/compile_explain.py`, `cli/preflight.py`, `cli/tokenize.py`, `cli/unmask.py`, `cli/subset.py`, `cli/report.py`, `tests/e2e/project_layout/test_pipeline_arg.py`, `tests/unit/project_layout/test_completion.py`, `tests/sentry/io_policy/test_pipeline_argument.py`, `docs/cli-reference.md` (regenerated), `CHANGELOG.md` (17) | about 800 | AT-18, AT-19, AT-20, AT-23, AT-27 and G-ONE-PIPELINE-ARG first; MP16 red; full CLI suite |
| P6 | CLI | `cli/project/__init__.py`, `_new.py`, `_show.py`, `_list.py`, `__main__.py` (register), `tests/e2e/project_layout/test_project_group.py`, `CODEMAP.md`, `docs/cli-reference.md` (regenerated), `CHANGELOG.md` (9) | about 550 | AT-24, AT-25 first; T1 |
| P7 | CLI | `cli/project/_scaffold.py`, `cli/init.py`, `tests/e2e/project_layout/test_init_project.py`, `tests/e2e/test_init_command.py`, `tests/e2e/test_init_scaffold_roundtrip.py`, `docs/project-layout.md`, `docs/cli-reference.md` (regenerated), `CHANGELOG.md` (8) | about 500 | AT-14, AT-28 first; T1 = init tests, `tests/unit/test_init_inference.py`, `tests/e2e/test_stateless_cli.py` |
| P8 | CLI | `cli/project/_run_all.py`, `cli/run.py`, `tests/e2e/project_layout/test_run_all.py`, `docs/cli-reference.md` (regenerated), `CHANGELOG.md` (5) | about 400 | AT-21, AT-22, MP17 first; T1 |
| P9 | CLI | `cli/unmask.py`, `cli/tokenize.py`, `cli/fit.py`, `cli/report.py`, `cli/io/_layout.py`, `tests/sentry/baselines/output-placement-allow.json`, `tests/e2e/project_layout/test_side_files.py`, `test_reports.py`, `CHANGELOG.md` (9) | about 450 | AT-11 remaining cells, AT-29 first; shrink G-ONE-OUTPUT-PLACE in the same commit; T1 = unmask, tokenize, fit, report tests, `tests/e2e/cli_fmt` |
| P10 | CLI | `ci/engine_logging.py`, `tests/e2e/project_layout/test_no_stray_files.py`, `test_walkthrough.py`, `CHANGELOG.md` (4) | about 550 | AT-12, AT-13, AT-26, final sentry run and MP1 to MP24 shown red; full CLI suite |
| LIB-A | CLI plan | LIB plan amendments: 4.1 step 3 calls `find_project`; the invocation id comes from `mint_invocation_id`; `.decoy/.gitignore` written by `ensure_decoy_dir`; class 4 names run folders; the `--emit-config out/p.yaml` example moves out of `out/` (it would warn `layout.config_inside_out`) (claudeorchestrator owns that branch) | about 12 lines | none |

Order: E1 and E2, then R. P1a any time. P1b after R (needs `is_valid_pipeline_name`). P2a any time after P1a. P2b after P1b and P2a (`RunLayout.open` needs
`find_project`, the claim and `create_private_directory` from P1b, and `place_quarantine` needs E2's
`quarantine_path` through R). Then P3 and P4 in either order. P5 after P1b (the name lookup needs `find_project`; it does not need placement). P6
after P5, P7 after P6, P8 after P5. P9 after P2b and P5 (it calls `list_pipelines` and `resolve_pipeline`). P10 last: the sweep, the walk-through and the placement
sentry's final empty-baseline check hold only when every writer is placed and every command takes names.
The sentry itself lands in P2b and shrinks in each later writer slice. P2b refuses escapes at write
time (`place_target`), so no build between P2b and P4 writes outside a run folder; P4 adds the earlier gate
refusal.

Position against other rows:

- **24o GEN-CLI:** its target half ("targets relative to the config file") is replaced by this plan; sources
  and `snapshot_file` stay with 24o. Whichever lands first adds `outputs[]` to `--json`.
- **LIB:** L1b.2's `resolve_root` step 3 becomes `find_project(...).root / ".decoy"`. If L1b.2 lands first,
  P1b changes that step in place; if P1b lands first, L1b.2 calls it. LIB's `test_stateless_cli.py`
  conflict is LIB's; `run` here creates no `.decoy/` (only `project new` does).
- **INIT-WIZARD phase 1a:** its default target `out/<table>.masked.<ext>` (plan line 406) becomes
  `<table>.masked.<ext>`, or it lands at `out/<p>/<run-id>/out/...`; its writer calls
  `write_pipeline_scaffold`, and W1a's collision check compares placed paths. Its lane is serialized on
  `init.py` (plan `:857-859`), so P7 and W1a must not run at once; whichever lands second rebases.

## 15. Pre-mortem

- **Scripts read the old output path.** Pre-GA; CHANGELOG gives three ways out; the summary prints the
  folder on every run.
- **A parent folder's marker captures outputs.** Another user's marker refuses; the user's own marker in a
  parent applies, and the summary prints the project root on every run. The walk stops below `$HOME`.
- **A user names a pipeline `decoy.yaml`.** No `kind` key, so it is skipped, not mistaken for a marker.
- **An extension-less file shadows a name.** The task's rule: an existing file wins; `--json` says
  `given_as: path`, and the summary prints the YAML used.
- **`out/` fills the disk.** Never pruned in V1 (Q4); F1 adds a clean command.
- **Masked or unmasked rows get committed.** `out/.gitignore` with `*`, checked on every run.
- **`run --all` is slow for many small pipelines.** One process each costs about a second of start-up;
  isolation is worth it in V1. F7 records an in-process mode if it matters.
- **The engine's subset-after-mask check compares raw strings** (`config/_pipeline.py:324-330`); a source
  `data.parquet` and a relative target `data.parquet` are now different files but are still refused.
  Renaming the target fixes it; F2.
- **`_targets.py` misses a run output** moved out of its run folder or written with `--out-dir`; it takes
  the suffix rule, today's behavior for any other path (F6).
- **Windows.** No symlink and no owner check; `LATEST` is the pointer (F4, F5).
- **The claim blocks a moved pipeline with a declared name.** The message names the claim file and both
  fixes.

## 16. Follow-ups (recorded, not in V1)

- F1 `decoy clean out --keep N` per pipeline, preview first.
- F2 the engine subset-after-mask alias check compares placed paths.
- F3 a configured workspace list for `decoy project list`.
- F4 a Windows owner check for the marker.
- F5 Windows `latest` as a junction.
- F6 `owning_run` for `--out-dir` folders (a run file written into the folder).
- F7 an in-process `run --all` mode.
- F8 `decoy runs <pipeline>` listing run folders with their status from LIB run records.
- F9 V2-LOG: serialize `LATEST` commits if real concurrency shows the read-replace race matters.

## Done when

Plan-lint clean; Dennis round 2 claims verified or corrected above; Codex r1 GO; owner answers on section 10.
