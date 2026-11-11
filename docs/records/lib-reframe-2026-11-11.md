# LIB re-FRAME against current main (2026-11-11)

Step 0 of the LIB build handoff (roadmap rows 34 to 42). No production code is in this record's
branch. It maps the plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7) onto CLI `main` at `1d53eda` and engine 0.22.0 (the pinned release; registry 1.22.0).

Verdict: **one guarantee change found (the default library root, item G1). Stopped before building.**
Everything else is placement only, or an open question listed in section 4.

Read for this record: the LIB plan, `plan/project-layout:docs/plans/2026-11-09-project-layout.md`,
`CODEMAP.md`, `.importlinter`, `src/decoy/_atomic.py`, `src/decoy/_private_file.py`,
`src/decoy/cli/io/` (`_project.py`, `_layout.py`, `__init__.py`), `src/decoy/cli/run/`,
`src/decoy/cli/evidence.py`, `tests/sentry/test_atomic_writer.py`,
`tests/sentry/io_policy/test_private_files.py`, `tests/sentry/layout/`, `tests/e2e/test_stateless_cli.py`,
and the installed engine's `decoy_engine.records`, `reasons` and top-level exports.

## 1. Guarantee changes (stop conditions)

### G1. The default library root moves from the YAML's folder to the project root

- Plan 4.1 and guarantee 1: the root is `--library`, else `DECOY_LIBRARY`, else
  `<directory of the pipeline YAML>/.decoy/`, else `<current directory>/.decoy/`.
- Main today: PROJECT-LAYOUT guarantee 1 says "LIB's `.decoy/` lives at the root; one function answers
  for both", and its LIB-A row says plan 4.1 step 3 becomes `find_project(...).root / ".decoy"`.
  `find_project` and `ensure_decoy_dir` are on main (`src/decoy/cli/io/_project.py`), and the sentry
  `tests/sentry/io_policy/test_pipeline_argument.py` allows no second root finder. LIB-A has not been
  applied to the LIB plan branch, so the plan text still states the old rule.
- Effect: with no `decoy.yaml` marker, the root is still the YAML's folder (no change). With a marker
  above the YAML (`<root>/pipelines/p/pipeline.yaml`), records and job logs land in `<root>/.decoy/`,
  not `<root>/pipelines/p/.decoy/`. The `DECOY_LIBRARY=off` job-log root (4.1, L5-always) moves the
  same way. Tests B1-resolve, L3-baseline-link, L5-always, L5-stateless-replaced and the L5b
  `test_run_writes_only_resolved_library` assertion ("under `<yaml dir>/.decoy/`") must be reworded to
  the project root.
- The owner decided the direction on 2026-11-09 in the PROJECT-LAYOUT plan, so the build is most
  likely "apply LIB-A". It is still a library-root change, which the handoff lists as a stop. Three
  points need an answer (section 4, Q1 to Q3).

No record format change was found: the envelope, the kinds and the payload tags in engine 0.22.0
match plan 4.3 (`decoy-record/v1`; `scan-set`, `evidence`, `run-result`, `sample-run` writable;
`publication`, `checkpoint` reserved). No change to the 4.15 verb list is forced by main; Q2 asks
about one flag.

## 2. Placement map (placement only; no guarantee moves)

| Plan placement | Where it goes on main | Why |
|---|---|---|
| `src/decoy/cli/_library/` (`__init__`, `_paths`, `_fs`, `_errors`, `_store`, `_refs`, `_policy`, `_index`, `_remote`, `_fsck`, `_scratch`, `_diff`, `_prune`, `_logs`) | `src/decoy/cli/library/` with the same `_<noun>.py` names | CODEMAP rule `src/decoy/cli/<command>/_<noun>.py`; about 15 modules, under the 25-module fan-out cap |
| `src/decoy/cli/library.py` (the command group; L1c.2, L4a, L4b, L5b) | `src/decoy/cli/library/_commands.py`, re-exported by `library/__init__.py`, registered in `src/decoy/__main__.py` | the flat `cli/` is frozen at 30 modules (`package-fanout.json`, shrink only) |
| `_library/_fs.py`: `create_private_file`, `ensure_private_dir` | no new creator: `library/_fs.py` is a thin caller of `decoy._private_file` (`create_private_directory`, `open_private`) and `decoy._atomic.write_atomic(..., tmp_dir=library/tmp)` | G-ONE-PRIVATE-FILE (`tests/sentry/io_policy/test_private_files.py`) already holds one creator and one mode module; a second copy would break LM4 and P4 |
| `_paths.py` owns the `.decoy` name | import `DECOY_DIR` from `decoy.cli.io`; `_paths.py` owns only `library/`, `logs/`, `scratch/` and their children | `cli/io/_project.py` is the one home of `.decoy` on main. G-LIB-WRITER's literal allowlist starts with two entries (`distribution/layout.py`, `cli/io/_project.py`), not one |
| `.decoy/.gitignore` written by the library (B1-gitfiles) | `ensure_decoy_dir(root)` from `decoy.cli.io` (content already equals plan 4.9). `.gitattributes` has no writer on main: the library writes it once, `CREATE_ONCE`, through `_atomic` | LIB-A; one writer |
| `_paths.resolve_root(...)` step 3 | calls `find_project` (see G1) | LIB-A |
| Windows path budget (root over 150 characters) | stays a library check in `library/_paths.py`; the 259 limit constant comes from `decoy.cli.io` if exported, else a V2-LOG note | `check_path_budget` on main is for run folders; the library's 150-character root rule is its own number |
| Invocation id minted in `run.py` (L5a) | already minted: `mint_invocation_id()` in `cli/run/_flow.py`, stored on `RunContext.invocation_id` | PROJECT-LAYOUT P2b; L5a mints nothing |
| `src/decoy/cli/_progress_fanout.py` (L5a) | `src/decoy/cli/run/_progress.py` | flat freeze; `tests/sentry/layout/test_run_package_shape.py` (600-line cap, thin `__init__`) applies |
| `src/decoy/cli/_vault_commit.py` (L5a byte-for-byte move) | already done by the run split: `src/decoy/cli/run/_vault.py`. L5a moves nothing and only corrects the allowlist reason text that still says "L5a moves it" | G-ONE-ATOMIC-WRITER allowlist is 3 entries on main (plan said 7); it does not grow |
| `src/decoy/cli/run.py` edits (L5a, L5b, L3a) | `cli/run/_execute.py`, `_flow.py`, `_context.py`; option declarations in `cli/run/__init__.py` | the split; "net change at or below zero for `run.py`" becomes "each `cli/run/` module stays under 600 lines" |
| `src/decoy/cli/_run_records.py` (L3a) | `src/decoy/cli/run/_records.py` | flat freeze |
| `src/decoy/cli/_run_outcome.py` (`finish`, RESULT C1a/C1b) | does not exist on main; RESULT's CLI half is not started (row 62) | L3a run-result half and L5b's `links.log` hand-off stay blocked |
| Canonical JSON rewire of `evidence.compute_manifest_hash` and G-ONE-CANONICAL (plan put them in L1b.1, "moves to L1b.2 if L1b.1 lands first") | L1b.2: neither is on main (`evidence.py:131` still calls `json.dumps`; no `tests/sentry/test_canonical_json.py`). Two more canonical-form copies exist now (`ci/manifest.py`, `cli/report.py`) | the allowlist size is measured at build time and reported, not assumed to be 3 |
| `tests/unit/library/` | unchanged | named folder |
| `tests/e2e/test_library_*.py`, `tests/e2e/test_job_logs.py`, `tests/e2e/test_run_library_records.py` | `tests/e2e/library/test_*.py` | CODEMAP: new e2e tests go in named folders |
| `tests/sentry/test_library_writer.py`, `test_canonical_json.py`, `test_kind_canary.py` | `tests/sentry/io_policy/test_library_writer.py`, `tests/sentry/io_policy/test_canonical_json.py`, `tests/sentry/defects/test_kind_canary.py`; each registered in `SENTRIES` and `scripts/dev/sentry_registry.toml` | CODEMAP: new sentries go in a group folder |
| `pyproject.toml` engine pin (L1b.2) | nothing to do: main pins 0.22.0, which carries L0, L1a and the scan-set kind | repin already merged |
| `uv sync --frozen --extra dev` (handoff check line) | `bash scripts/dev/bootstrap.sh` (there is no `uv.lock`; the lock is `requirements-dev.lock` and the engine installs from its git tag). Checks then run from `.venv` | main's bootstrap; verified working on this node, Python 3.10 |
| OS lane paths in plan 5.1 | `tests/unit/library/`, `tests/e2e/library/`, the two `io_policy` guards and `tests/sentry/test_atomic_writer.py` | follows the rows above |
| `docs/library.md`, `docs/cli-reference.md` (regenerated), `CHANGELOG.md` `[Unreleased]` bullets, `CODEMAP.md` row for `cli/library/` | unchanged, plus the CODEMAP row (checked by `test_codemap_paths.py`) and an `.importlinter` check (the package sits inside the existing `cli` tier, so no new tier line is expected) | main conventions |

## 3. Plan assumptions that no longer hold, by slice

- **L1b.2/L1b.3 (row 34).** Paths as mapped. Root rule: G1. The library error codes the plan names
  (`library_busy`, `library_lock_unavailable`, `library_path_too_long`, `library_layout_newer`,
  `record_link_missing`) are not in engine 0.22.0's reason registry; it carries `record_invalid`,
  `record_corrupt`, `record_kind_reserved`, `scratch_acl_failed`, `scratch_unsafe` and four warning
  event codes (`library_write_failed`, `library_degraded`, `library_delete_skipped`,
  `job_log_write_failed`). See Q4.
- **L1c (row 35).** Placement only. `fsck` and `path` become the first registered verbs.
- **L1d (row 34).** `decoy_engine.protected_scratch_dir(parent, prefix)` and
  `open_protected_dir(path, create=, parents=)` are public in 0.22.0. Placement only.
- **L4a, L4b (rows 39, 40).** Placement only. `decoy library clean` and PROJECT-LAYOUT's later
  `decoy clean` (F1) are different commands; no conflict today.
- **L5a (row 41).** No vault move, no id mint (both done). `decoy run` still passes no `ProgressSink`
  and uses `ui.progress.spinner` (`cli/run/_flow.py:51`), so the wiring itself is still to build.
  Routes on main: whole-table, `--chunked`, the `--rows` preview. The plan's "sample" route does not
  exist (SAMPLE not started).
- **L5b (row 42).** Blocked as the handoff says (needs L3a and RESULT). `test_stateless_cli.py:90`
  still asserts no `.decoy` path; the replacement assertion names the project root, not the YAML
  folder (G1).
- **L3a (row 37).** Blocked on CLI #200 (open, head `ce4f2d3`) and RESULT. One thing to check when
  #200 merges: the plan for P3 adds a manifest field `path_base: project`, and the engine's
  `EvidencePayload` write model in 0.22.0 has no such field and forbids extras. If #200 ships the
  field, an evidence record cannot be built until the engine model gains it. That would be a record
  format question for the owner, not a CLI workaround. V2-LOG until L3a starts.
- **L3b, L2, L5c.** Not built here.

## 4. Questions for the owner or orchestrator

- **Q1 (G1).** Confirm the default library root is `find_project(start, explicit).root / ".decoy"`,
  with `start` the YAML's folder for a pipeline given by path and the current folder otherwise, and
  that `--project` and `DECOY_PROJECT` feed `explicit` exactly as PROJECT-LAYOUT 3.2 states.
- **Q2.** Do `--library DIR` and `DECOY_LIBRARY` stay as plan 4.1 has them (they override the root
  for records and logs only, ahead of the project rule), now that `--project` and `DECOY_PROJECT`
  exist? Recommended: keep them; a container that mounts a volume for records still needs them.
- **Q3.** For `scan` with no pipeline, PROJECT-LAYOUT 3.2 keeps the LIB order (`--config`, else the
  current folder) as the `start`. Plan 4.1 puts `--emit-config`'s folder first. L2 is not built here,
  but `resolve_root` takes the scan inputs in L1b.2 (B1-resolve, MB1-scan-cwd). Recommended: keep the
  plan's order for `start` (`--emit-config` folder, then `--config` folder, then the current folder)
  and then walk up with `find_project`.
- **Q4.** CLI-raised library error codes that the engine registry does not hold: keep them as CLI
  constants in `cli/library/_errors.py` (the `layout.*` and `atomic_*` precedent; they are printed,
  never written into a job-log event, so the "unregistered code" rule in 4.12 is not touched)?
  Recommended: yes. The alternative is an engine registry minor and a repin before L1b.2.
- **Q5 (branches).** The handoff asks for one branch and PR per slice part, stacked. This session is
  set up to push only to `claude/gifted-einstein-vvvzkw` in each repo. Either allow slice branches
  (for example `feat/lib-l1b2-store`), or accept one branch with the slices as ordered commits and
  one PR.
- **Q6 (OS lanes).** This node is Linux only. macOS and Windows lanes for L1b, L1c, L1d and L4b would
  be recorded NOT RUN.

## 5. What was not run

No tests, no gates: nothing was built. The dev environment was bootstrapped and matches
`requirements-dev.lock` (Linux, Python 3.10, engine 0.22.0).
