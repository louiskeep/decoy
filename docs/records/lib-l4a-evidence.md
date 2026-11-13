# LIB L4a (library read commands and refs): build evidence

Slice L4a of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7: slice L4a-cli, sections 4.3a, 4.5 and 4.15 for `list`, `show`, `diff` and `ref` only).
`show --log` (L5b) and `export` (L4b) are not built. Branch `feat/lib-l4a-read` from the L1d head
`5133e4c` (`feat/lib-l1d-scratch`).

## Environment

- OS: Linux 6.18.44 (x86_64), ext4, run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`).
- Engine: `decoy-engine` 0.22.0.
- Code head the checks ran on: `7b25b76`. This record is the only later commit (Markdown only).

## Commits

| Commit | What |
|---|---|
| `95a4a98` | red-first `tests/e2e/library/test_library_read_commands.py` |
| `8fc3683` | `_read.py` (list, show, diff, ref), `_diff.py`, `_resolve.py`, `_cli.py`, registration in `_commands.py`, `latest` reserved as a ref name in `_refs.py`, `docs/cli-reference.md` regenerated, docs, CHANGELOG, CODEMAP |
| `7b25b76` | the ref-lock test strengthened after ML4-ref-nolock survived (below) |

## Red first (`95a4a98`)

`pytest tests/e2e/library/test_library_read_commands.py`: **21 failed**. There were no
`list`, `show`, `diff` or `ref` commands.

## What was built

- **`list [--kind K] [--pipeline P] [--table T] [--since D] [--json] [--library DIR]`**
  - Reads `Library.rows` (the index; no record file is opened). `--since` takes `YYYY-MM-DD` or
    an ISO time (UTC unless zoned); anything else exits 1.
  - `--json` is `{"command": "library list", "count", "records": [...]}`, sorted by
    `(created_at, id)`.
  - Opaque rows show as `unknown kind <name>, needs a newer Decoy`.
  - `--kind` completion comes lazily from `records.registered_kinds()`, but any name still
    filters (4.3a).
- **`show ID|REF [--json] [--library DIR]`**
  - A known record prints its envelope plus payload.
  - An opaque record prints its envelope only, and says the payload cannot be read by this
    version; `RecordNeedsNewer` says it needs a newer Decoy.
  - `--json` gives `status` (`known`, `opaque` or `needs_newer`), `payload_schema` and `record`
    (no `payload` unless known).
- **`diff A B [--json] [--library DIR]`** dispatches on the registry's `diff_rule` (`_diff.py`):
  - `scan-set`: the payload goes through `decoy.cli.io.scan_set_from_data` (the public
    saved-scan reader), then `decoy.cli.scan.compute_scan_diff` runs per common table (the rules
    `scan diff` and `decoy ci check` share); tables added or removed are listed by name.
  - `evidence`: `decoy.cli.report.compare_manifests`, the `report diff` manifest comparison,
    with warning lists reduced to codes.
  - `run-result`: status, exit code, route (execution mode, reason, chunked), delivery, and per
    table outcome, rows out, delivery state and format.
  - Any other known kind: a structural diff, as JSON-pointer paths (changed, added, removed)
    plus the two payload digests.
  - Different kinds, or an opaque or newer record, exit 1.
- **`ref KIND/NAME [ID] [--library DIR]`** shows a ref, or sets it through `Library.set_ref`
  (under the library lock).
  - A bad name exits 1.
  - An unset ref exits 1.
  - Degraded mode exits 3 with `library_lock_unavailable` (`EXIT_RUNTIME`, the library's own
    state).
- **Naming records (`_resolve.py`):** a full id, or a unique prefix of 8 or more hex digits
  (ambiguous refused); `KIND/NAME` or `KIND/SCOPE/NAME` refs; `KIND/latest` and
  `KIND/latest~N`, read from the index by `(created_at, id)`.
- **Reuse, with no new exception:** both `compute_scan_diff` and `compare_manifests` are public
  names in flat `cli` modules and are imported lazily inside `_diff.py`. Same `cli` tier, no
  private import, no import-layer change, nothing copied.
- **Startup:** `decoy --help` still imports no engine code.

## Mutations (`mutate_l4a.py`; each applied once and restored; `src` clean)

| Mutation | Change | Test | Result |
|---|---|---|---|
| ML4-filter | `--pipeline` dropped from the query | `test_list_filters_by_kind_pipeline_table_and_time` | red |
| ML4-first-match | ambiguity check removed (first match taken) | `test_show_refuses_an_ambiguous_prefix` | red |
| ML4-ref-nolock (first run) | `ref` writes the file directly, without `set_ref` or the lock | `test_ref_sets_under_the_lock_and_prints` | **green**, a real test gap: its spy counted `_index.locked` calls, and opening the library already takes the lock for the index catch-up. `test_ref_unset_is_a_usage_error_and_degraded_set_refuses` was red |
| ML4-ref-nolock (after `7b25b76`) | same | the strengthened test records whether the lock is held at the ref-file write | red |
| ML4-generic | every kind gets the structural diff | `test_diff_run_results_by_status_route_rows_and_delivery`, `test_diff_evidence_uses_the_report_diff_comparison`, `test_diff_scan_sets_uses_the_scan_diff_rules` | red, all three |

## Checks on `7b25b76`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/library tests/e2e/library tests/sentry -q -p no:cacheprovider` | 1268 passed, 6 skipped (Windows/macOS-only cases) |
| `.venv/bin/ruff check src tests` | pass |
| `ruff format --check` on the `.py` files changed since the base | 7 files already formatted |
| `uvx mypy --python-executable .venv/bin/python src/decoy`, compared with the base | no new error |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection (`tests/unit/library tests/e2e/library tests/unit/test_cli_surface.py tests/unit/test_surface_docs_consistency.py tests/unit/test_no_dead_command_strings.py tests/sentry/cli_text tests/unit/test_report.py tests/e2e/test_report_diff_command.py tests/e2e/test_ci_existing_contracts.py tests/e2e/test_stateless_cli.py`) | branch 345 passed, 6 skipped; base `5133e4c` (`PYTHONPATH=<worktree>/src`; same paths, with only `test_library_fsck.py` from `tests/e2e/library`) 324 passed, 6 skipped |
| real run (two records, then `list`, `diff sample-run/latest~1 sample-run/latest --json`, `ref sample-run/base sample-run/latest`, `show sample-run/base`, `show zz`) | as expected; `show zz` exits 1 with a value-free message |

Failure sets: branch none; base none.

## Sentry registrations

None needed.

- The private-file census stays at 61 / 23: no new write site, since refs go through
  `set_ref`.
- No baseline changed.
- Two sentries shaped the code instead of growing:
  - G-ONE-CANONICAL flagged `json.dumps(sort_keys=True)` in the human output. It was dropped,
    because stored envelopes are already in canonical key order.
  - `test_json_command_names` requires literal envelope `command` values (`FORWARDERS` is its
    only escape). The success envelopes use literals, and errors are not wrapped in a JSON
    envelope (Deviation 1).

## OS lanes

- Linux: run.
- macOS and Windows: NOT RUN. The plan's lane table lists L4a as Linux only.

## Not run

The full suite, and mypy from `.venv`.

## Deviations

1. **Errors go to stderr only, also under `--json`** (stdout empty; exit 1 or 3). Main's
   `scan diff` emits a JSON error object instead. Emitting one here would need either a variable
   `command` value or new `FORWARDERS` entries in `test_json_command_names.py`, and I chose not
   to widen that escape list.
2. **`latest` and `latest~N` are written `KIND/latest[~N]`.** 4.15 gives `diff` no filter flags,
   so `latest` is filtered by kind only; the pipeline and table filters of plan 4.5 are not
   reachable from the CLI in this slice (V2-LOG). Because `KIND/latest` is a virtual name,
   `latest` is now refused as a stored ref name (`ref_name_invalid`), matching 4.5's "no stored
   file".
3. **The run-result diff includes `exit_code` and the delivery block** besides the plan's
   status, route, row counts and per-table delivery. These are value-free states.
4. **The structural diff reports paths, never values.** Two payload digests show that the
   content differs.

## V2-LOG (noticed, not built)

- `latest` filtered by pipeline or table set (4.5) needs a syntax or flags; for example
  `--pipeline` and `--table` on `diff` (an additive surface change for the owner).
- A JSON error envelope for the `library` commands would need a forwarder entry in
  `test_json_command_names.py`.
- `show` for a `run-result` could add the `links.log` state once L5b fills it.
- `list` human output is one plain line per record; a table renderer would match the other
  read commands.
