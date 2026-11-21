# LIB L3a (evidence half): build evidence

Slice L3a of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7, section L3a-cli with the amendment of 2026-11-12, and sections 4.16 and 4.17). This
is the evidence half only. The run-result half waits on RESULT C1a and C1b (roadmap row 62, in
progress). Branch `claude/inspiring-hopper-bb38t6` from main `4e6d60b`.

## Environment

- OS: Linux 6.18.44 (x86_64), ext4, run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`; `scripts/dev/bootstrap.sh` OK against `requirements-dev.lock`).
- Engine: `decoy-engine` 0.27.0 (commit `ddd014a`). Its `EvidencePayload` already has the
  amendment's `path_base` and `project_manifest` keys, so no engine slice was needed first.
- Code head: `b7c6d9f` (mutations). Full suite: `2124e17` (adds Markdown only). `e7e76d9` fixes a
  CODEMAP path (Markdown only); this record is the last commit (Markdown only).

## Commits

| Commit | What |
|---|---|
| `2174e83` | red first: `tests/e2e/library/test_run_evidence_records.py`; the `evidence` canary case; the `evidence` pending row removed from G-KIND-CANARY and its baseline; the one-caller sentry |
| `6cd486b` | `cli/library/_run_records.py` (`store_evidence`, `StoreOutcome`) on the facade; `cli/run/_evidence.py` builds the manifest once, writes `--evidence-out` and stores the record; `--no-library` (forwarded by `--all`); the `library` member in `--json` and the card's `Library` line; `json-shapes.json` regenerated (`/library` opaque); CLI reference regenerated |
| `b7c6d9f` | the label is computed run-side (G-LIB-FS); the tests that compare two runs' `--json` and list a run's files take the new record into account; sentry manifest entry |
| `2124e17` | `docs/library.md`, CHANGELOG, CODEMAP |
| `e7e76d9` | CODEMAP names the caller by its full path (`test_codemap_paths.py`) |

## Red first (`2174e83`)

`test_run_evidence_records.py`: 8 of 9 failed (no record, no `--no-library`, no `library` key).
The `--rows` preview case passes on main too: it guards that a preview stays out. The canary case,
the G-KIND-CANARY pending count and the one-caller sentry failed.

## What was built

- **One store function.** `decoy.cli.library.store_evidence(manifest, pipeline=, label=,
  invocation_id=, enabled=)`:
  - It resolves the root from the run's YAML (`resolve_root(pipeline=...)`).
  - It builds an `evidence` envelope from the manifest dict as built, and puts it.
  - It returns `StoreOutcome` (`stored` with root and id, `skipped`, or `failed` with a code).
  - It never raises.
- **One caller.** `cli/run/_evidence.py` is the only call site, which a sentry holds
  (amendment: `finish` takes the call over in the RESULT PR).
- **Built once.** The manifest is built once per successful run, whether or not `--evidence-out` is
  given. The same dict goes to the file and to the record.
- **Labels.** `pipeline` is the YAML's project-relative POSIX path (absolute outside a project);
  `tables` are the target names. No links: the run-result record will link to the evidence.
- **Off switches.** `--no-library` and `DECOY_LIBRARY=off` give `skipped`. A `--duckdb-source`
  run is skipped too: its input is a transient snapshot with no defined fingerprint, the reason
  `--evidence-out` already refuses it.
- **Failure (4.17).** The run warns once on stderr (`warning: <code>: ...`), `--json` has
  `library.status = "failed"` with the code, and the exit code is the run's own.

## Acceptance tests and mutations (on `b7c6d9f`)

`mutate_l3a.py`: each mutation applied once by exact string replace, its tests run, the file
restored; `src` clean after.

| Plan row | Test | Mutation | Result |
|---|---|---|---|
| L3-records (evidence part) | `test_a_run_stores_one_evidence_record_by_default` | ML3-label: label is the file name | red |
| L3-evidence-same | `test_the_record_payload_equals_the_evidence_out_file[project, no-marker]` | ML3-drift: build the manifest a second time for the store | red (both) |
| L3-baseline-link (root half) | same, no-marker case: the record lands in the YAML's library, not the current folder's | ML3-cwd-root: resolve the root without the YAML | red |
| L3-no-library | `test_no_library_or_env_off_stores_nothing[flag, env]` | ML3-ignore: `--no-library` ignored | red (flag) |
| L3-readonly | `test_a_library_that_cannot_be_written_warns_and_keeps_the_exit_code` | ML3-fail: exit 3; ML3-silent-fail: no warning | red, red |
| L3-failed-run (evidence part) | `test_a_run_that_fails_stores_no_evidence` | none: the failure path never reaches `write_evidence` | guard |
| L3-canary | `test_canary.py` with the new `evidence` case | M-PAYLOAD-LEAK not applied: the payload model refuses unknown fields, so there is no CLI-side spot to inject a value | positive and negative checks pass |
| one caller | `test_evidence_store_caller.py` | ML3-second-caller | red |

L3-readonly uses a file where the `.decoy` folder goes, not a 0555 folder: this container runs as
root, and root writes through a read-only mode.

Run-result half (stacked PR on this branch, `feat/lib-l3a-run-result`): see the section "Run-result
half" below. Still not built: L3-log-link (waits on L5b, roadmap row 42, which writes the job log),
L3-baseline-link (waits on L2, row 36: no scan record exists yet, so a run has nothing to link to as
its baseline) and L3-report-id (`report show`, `verify` and `diff` by id: `report.py` must not
grow, see Deviations).

## Finding: some runs' manifests failed the engine's evidence model (resolved by engine 0.28.1)

On the first head, the freeze snapshot's two-table FK mask run (hash and redact) stored nothing:
`record_invalid`. The engine's out-of-core route attached the warning
`out_of_core_caller_managed_residency` with `provider: ""` and a list in `detail`, which
`EvidencePayload.warnings` refused. Engine 0.28.1 (the CLI pin since the merge of main into this
branch) accepts it. The strict xfail that pinned the gap came out XPASS on the merge head, so it is
removed: `test_an_out_of_core_fk_run_stores_its_evidence` now runs as a plain test. No owner
decision is needed.

## Checks

The slice changes a default (every successful run now writes under `.decoy/`) and a frozen
`--json` shape. Both are full-suite triggers, so the whole suite ran at the slice.

`scripts/dev/gates.sh --keep-going tests` on `2124e17`:

| Step | Result |
|---|---|
| env | PASS |
| ruff | PASS |
| sentry | 1431 passed, 2 failed |
| layers | 23 passed |
| tests (whole `tests/`) | 6556 passed, 25 skipped, 2 failed |

- **The two failing ids** are `tests/sentry/layout/test_codemap_paths.py::test_every_path_in_the_codemap_layout_section_exists`
  and `::test_a_missing_concrete_path_in_the_section_is_red`. My CODEMAP row named
  `cli/run/_evidence.py` without `src/decoy/`. `e7e76d9` fixes it, and that file then passes
  (6 passed).
- **Main baseline.** Main `4e6d60b` is green in CI. No main-side full suite ran (the rule is to
  diff against the stored baseline), so no other failing id is attributed to main.
- **An earlier full run** on a superseded head found 19 failures. One was my mistake: a
  `ruff format` over all of `src/` and `tests/` had reformatted unrelated files (`scan.py` then
  tripped the module-size census). The two commits were rebuilt with only this slice's files.
  The other 18 came from the new default and are fixed in `b7c6d9f`:
  - G-LIB-FS: the label's `Path.resolve` was in the library module.
  - The sentry manifest was missing the new sentry file.
  - `--all` forwarding had no `--no-library` sample.
  - Seven tests that compare two runs' `--json` now ignore the per-run record id.
  - Two layout guarantee tests now list the library files a run writes.
- **Format.** No format gate is in `ci.yml`. The files this slice touches pass `ruff format --check`.

## OS lanes

- Linux: run.
- macOS and Windows: not required (plan 5.1: L3a is Linux only).

## Not run

mypy (no gate in `ci.yml`). The run-result half and `report ... <id>`.

## Deviations

1. **`--library DIR` is not on `decoy run` yet.** The plan's file list for L3a names only
   `--no-library`, and 4.16's `--library` mention refers to the root rule. `DECOY_LIBRARY=<dir>`
   moves the records today.
2. **`report show/verify/diff <id>` (L3-report-id) is left to a second part.** `report.py` is
   2382 lines and must not grow. Routing it through one library call is a separate, reviewable
   change, and it does not block the default write.
3. **Paths are stored as the manifest has them.** That is project-relative inside a project and
   absolute outside one. The amendment's "built once and stored as built" replaces the earlier
   "relativized by the kind spec" text. Export strips the declared path fields.
4. **`/library` is an opaque object in the frozen `--json` shape.** Its members depend on the
   store outcome, so the snapshot holds the key's presence and type.

## V2-LOG

- The pipeline label now calls `decoy.cli.io.project_relative_posix`, the helper L4a added.
- `decoy library list` on a project after this lands shows evidence rows. `library show` of one
  prints raw warning text, which is #215's V2-LOG a.

## Run-result half

`decoy.cli.library.store_run_result` stores the document `cli/run/_result.py` already builds, as
built, once. Its one caller is `_result._store_record`, called from `_write_file`, which both
`emit` and `report_error` use: every end of the run that writes the `--json` envelope or the
`--result` file stores the record, and the payload equals the `result` member of `--json`.

- **Link.** The envelope links one way to the run's evidence record (`rel: evidence`) when one was
  stored. The evidence is stored first and links to nothing. The reverse direction is an index
  query over `links`.
- **Labels.** `pipeline`, `tables`, `status` and `exit_code`.
- **Which runs.** Success, findings and a run that failed after it started (runtime, capacity,
  cancelled, and a config-caused engine fault that exits 1) store a record. A refusal before the run
  starts (the engine was never called: `ctx.execution_started` is false) stores
  nothing, as before, so the "refusal writes no file" sentries stay true. A preview, `--no-library`,
  `DECOY_LIBRARY=off` and a failed document build store nothing.
- **Failure (4.17).** A failed store warns once and keeps the exit code. When the evidence store
  already failed, the run-result store is skipped, so one run gives one warning.
- **`--json`.** On success the `library` member gains `result` (the run-result record id).
  Error envelopes are unchanged.
- **Cells.** `tests/e2e/library/test_run_result_records.py` (L3-records run-result part,
  L3-payload-from-finish on success and on a runtime failure, L3-failed-run, L3-no-library,
  L3-readonly, the `--result` file equals the record), the `run-result` canary case, and
  `tests/sentry/io_policy/test_run_result_store_caller.py` (one caller).
- **Not covered.** L3-payload-from-finish on a `findings` run (exit 4) has no cell: it needs a
  post-validate fixture and uses the same `_write_file` path as the cells that exist.

## Mutations at the final head (`057cc05d`, Codex round 2 fix)

Each mutation applied once by exact string replace, the 5 test files below run
(55 tests with the guard file), the file restored. Cells are
`tests/e2e/library/test_run_evidence_records.py`, `test_run_result_records.py`,
`test_library_output_guard.py` and the two `tests/sentry/io_policy/test_*_store_caller.py` files.
"Red" gives the failing test count.

| Mutation | Result |
|---|---|
| ML3-label: label is the file name | red (3) |
| ML3-drift: the store gets a different manifest than the file | red (10) |
| ML3-cwd-root: root resolved without the YAML | red (1) |
| ML3-ignore: off switch ignored (`store = True`) | red (3) |
| ML3-ignore: `enabled=True` with `--evidence-out` | red (1) |
| ML3-fail: a failed store raises | red (4) |
| ML3-silent-fail: no warning on a failed store (evidence, result) | red (3), red (1) |
| ML3-second-caller: `store_run_result` called under an alias in `_render.py` | red (1) |
| RR-category-proxy: persistence decided by an outcome proxy, not `execution_started` | red (1) |
| RR-start-unset: `execution_started` never set | red (8) |
| RR-pre-start-stores: a pre-start refusal stores a result | red (27) |
| RR-quiet-silent: no warning under `--quiet` (result, evidence) | red (1), red (1) |
| RR-link-dropped: run-result does not link its evidence | red (2) |
| RR-double-warn: result store not skipped after a failed evidence store | red (3) |
| RR-label-resolver-copy: result label not from the shared resolver | red (3) |
| LG-registration-removed: the library root is not given to the collision rule | red (25 of 26 guard cells; the `--no-library` control stays green) |

The `ML3-fail` first try (`raise` in the `OSError` handler only) survived, because the
unwritable-library cells fail through the layout and library errors, not `OSError`. The mutation
that makes the whole failure return raise is red.

## Output guard (Codex round 2)

The resolved library root is one more destination in `resolved_output_collisions`
(`OutputPlacement.library`, set once by `output_placement` in `cli/run/_context.py`). A `--result`,
`--evidence-out`, `--integrity-out` or a configured target at or inside the root is refused by the
gate with the usual collision refusal before any write. The root is not checked anywhere else.
Cells: `tests/e2e/library/test_library_output_guard.py` (unset env, relative `DECOY_LIBRARY`,
absolute `DECOY_LIBRARY`; at the root and inside it; the relative `r.json` case; `--no-library`
leaves the root free).

## Revision 8 (Codex round 3): one output inventory, one containment rule

Code head `95f390b3`. The mutations below ran on that tree (the record commit changes only this
file). Each was applied once by exact string replace, the test set run, the file restored. The set is
the guard matrix (`test_library_output_guard.py`), `tests/sentry/io_policy/run_outputs/`,
`test_paths.py`, `test_placement_typed_files.py`, `test_library_read_commands.py`, the two run record
files and `test_private_files.py` (201 tests with the full set green). "Red" gives the failing count.

| Mutation | Result |
|---|---|
| MO-implicit-drop: `run_outputs` omits the implicit report | red (5) |
| MO-report-fork: `report_file` derives its own name | red (1) |
| MO-second-walk: the collision rule calls `relative_outputs` | red (1) |
| MO-unlisted-writer: a run writes one more file beside a target | red (13) |
| MO-one-direction: drop branch (b) of `overlaps_root` | red (11) |
| MO-entry-only: check the entry, not the followed landing | red (9) |
| MO-lexical: compare text paths, not `_destination_key` | red (17) |
| MO-prefix: compare string prefixes | red (1) |
| MO-narrow-catch: `anchor` catches `OSError` only | red (13) |
| MO-fault-raises: `_library_root` lets `LibraryError` through | red (10) |
| MO-re-resolve: a store function calls `resolve_root` again | red (1, the static check) |
| MO-fault-fallback: on a fault, store under the project `.decoy` | red (9) |
| MO-cli-root: `LibraryCommand.root()` catches `LayoutError` only | red (1) |
| MO-two-warnings: the evidence store prints its own warning | red (9) |
| MO-raw-first-target: `implicit_report_path` gets the raw text | red (2) |
| MO-sink-unlisted: a run-reached module gains a write call with no row | red (9) |
| Registration removed (`library = None`) | red (55) |

MO-lexical survived once (201 passed): the first form compared text paths of the landing, and
`_landing` already resolves links. The mutation that compares the declared output text, with no
landing and no key, is red. The write audit and the sentry rows are in
`tests/sentry/io_policy/run_outputs/test_run_output_inventory.py`.

Where the test matrix differs from the plan text: for `integrity-implicit` and `quarantine` the
report and the quarantine file share their folder with the first target, so when they sit inside the
root the target does too, and the refusal names the target first. The cells accept either label
there. The `layout` row's "above" cell has the same property. Also, `--chunked` lists the implicit
report like any other run (the gate does not know whether a chunked run writes one).
