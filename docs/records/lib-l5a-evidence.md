# LIB L5a (engine ProgressSink into `decoy run`): build evidence

Slice L5a of the LIB plan (`plan/local-record-library:docs/plans/2026-11-05-local-record-library.md`,
revision 7: slice L5a-cli), as changed by `docs/records/lib-reframe-2026-11-11.md`. The vault
commit is already in `cli/run/_vault.py` and the invocation id is already minted in
`cli/run/_flow.py`, so neither moves here. Branch `feat/lib-l5a-progress` from
`origin/feat/lib-l1c2-fsck` at `2e549b9`.

## Environment

- OS: Linux 6.18.44 (x86_64), ext4, run as uid 0 in a container.
- `python -V`: Python 3.10.20 (`.venv`, matches `requirements-dev.lock`).
- Engine: `decoy-engine` 0.22.0.
- Code head the checks ran on: `27bd5ff`. This record is the only later commit (Markdown only).

## Commits

| Commit | What |
|---|---|
| `a11d3e6` | red-first `tests/unit/test_progress_fanout.py` and `tests/e2e/run_progress/test_run_progress_events.py`; `_progress` registered in the run-package `ORDER`; the stale `_vault.py` allowlist reason corrected in `tests/sentry/test_atomic_writer.py` and its baseline JSON (same file, same 4 sites, allowlist still 3) |
| `dd59f3d` | `cli/run/_progress.py`, the sink on both `run_pipeline` calls, the event-fed display in `ui/progress.py` replacing the bare spinner, `RunContext.progress`, CHANGELOG |
| `27bd5ff` | typing fix (`TaskID`) so the new display adds no mypy error |

## Red first (`a11d3e6`)

`pytest tests/unit/test_progress_fanout.py tests/e2e/run_progress tests/sentry/test_atomic_writer.py tests/sentry/layout/test_run_package_shape.py tests/sentry/test_baseline_registry.py --continue-on-collection-errors`:
**1 failed, 78 passed, 2 errors.**

- 2 collection errors: both new test files import `decoy.cli.run._progress`, which did not
  exist yet.
- 1 failure: `test_run_package_shape.py::test_the_scan_sees_every_phase_module`, because the new
  `ORDER` entry named a module not yet on disk.

## How the engine takes a sink, and the routes `decoy run` reaches (engine 0.22.0)

- `run_pipeline(..., progress: ProgressSink | None)` takes the sink. Probed directly, a
  whole-table mask run emits phase, route and terminal events.
- **Routes the CLI can take, and what each now gets:**

  | CLI route | Engine call | Sink |
  |---|---|---|
  | whole-table run (mask, generate, mixed with a relationship) | `run_pipeline` | passed; tested |
  | `--rows` preview | `run_pipeline` | passed; tested |
  | `--chunked` | `run_mask_pipeline_chunked(config, chunks, *, table, engine_version, registry, adapter, vault_writer, chunk_result_sink, key_provider, base_row_offset, file_access)` | **none: no progress parameter in 0.22.0** |

- **`--chunked` is blocked by the engine release.** The plan expects this (its chunked case
  waits for RESULT E3). No event is faked. `test_the_chunked_route_feeds_the_sink` is skipped
  with that reason. `test_the_chunked_engine_api_still_takes_no_sink` pins the absence, and goes
  red when a pinned engine gains the keyword, the signal to pass the sink and unskip.
- **Engine-internal routes.** `decoy run` passes no `execution_mode`, so the engine routes
  automatically, and whatever route it picks receives the same sink inside `run_pipeline`. No
  `decoy run` flag forces `sequential` or `out_of_core`; both need relationships and
  size/budget conditions the CLI does not expose (`--native` / `--no-native` only toggle the
  unified slice, and the native companion is not installed here). `stream` needs a
  transactional `sink=` the CLI never passes. The plan's "sample" route does not exist on main
  (SAMPLE not started). All four test cases above routed `full_frame`.
- **Older engines.** The keyword is sent only when the installed `run_pipeline` accepts it
  (`_progress.run_pipeline_kwargs`, the same capability check `_native_gate` uses). Without it,
  `tests/e2e/test_run_native.py::test_no_native_stays_compatible_with_an_older_engine` (a fake
  older engine with no `**kwargs`) failed. That test was not edited.

## What was built

- **`cli/run/_progress.py`: `ProgressFanout`** implements the engine's `ProgressSink`
  (`isinstance` holds) and forwards each event object unchanged, in emission order, to every
  consumer. A consumer that raises is counted in `faults`, skipped for that event, never
  retried, and never reaches the engine or the run. `build()` makes the run's one sink;
  `run_pipeline_kwargs` adds it when the engine accepts it.
- **`ui/progress.py`: `run_progress(state, message)`** is a spinner whose text follows phase
  (`Running mask... mask (people)`) and rate (`N rows (table), R rows/s`) events. It is rendered
  only on `state.err_console`, suppressed like `spinner` (quiet mode, or stderr not a terminal);
  the handle still accepts events then.
- **`cli/run/_flow.py`** builds the fan-out, registers the display as one consumer, and keeps
  the sink on `ctx.progress`. No file is written: `test_stateless_cli.py` is unchanged and
  green.

## Mutations (`mutate_l5a.py`; each applied once and restored; `src` clean)

| Mutation | Change | Test | Result |
|---|---|---|---|
| ML5a-route | sink passed on the whole-table call only | `test_every_route_feeds_the_sink` | red (the `--rows` preview case) |
| ML5a-buffer | events held in a set and flushed at the terminal event | `test_every_consumer_sees_every_event_in_emission_order` | red |
| ML5a-propagate | no `try` around the consumer | unit fault test; `test_a_failing_consumer_changes_nothing` | red, both |
| ML5a-stdout | the display renders on `state.console` (stdout) | `test_the_display_renders_phases_on_stderr` | red |
| ML5a-stdout | same | `test_quiet_and_json_keep_stdout_free_of_progress` | green: these runs finish before Rich renders a frame, so the transient display writes nothing to either stream. The display-level test above catches the mutation |
| ML5a-wrap | consumers get a CLI object with a `message` field | `test_events_carry_no_cell_value` | red |
| ML5a-vault-generic | `_commit_vault` through `_atomic.staged_private_target` (`REPLACE`, no backup or rollback) | `test_vault_commit_order.py::test_a_pre_existing_vault_survives_a_failed_rewrite`, `::test_preexisting_vault_survives_backup_link_failure` | red, both |

## Checks on `27bd5ff`

| Command | Result |
|---|---|
| `.venv/bin/pytest tests/unit/test_progress_fanout.py tests/e2e/run_progress tests/sentry tests/e2e/test_vault_commit_order.py tests/e2e/test_card_and_progress.py tests/e2e/test_stateless_cli.py -q -p no:cacheprovider` | 1129 passed, 1 skipped (the blocked chunked case) |
| run e2e the change can affect, on identical code at `dd59f3d` (plus the above): `tests/e2e/test_run_*.py tests/e2e/first_user tests/e2e/project_layout` with the sentries | 1821 passed, 4 skipped |
| `.venv/bin/ruff check src tests` | pass |
| `ruff format --check` on the `.py` files changed since the base | 10 files already formatted |
| `uvx mypy --python-executable .venv/bin/python src/decoy`, compared with base `2e549b9` | no new error. The `_execute.py` `**kwargs` errors are pre-existing; their argument numbers shift by one because a `**` argument was added ahead of them. Compared with argument numbers stripped, the sets are equal |
| `bash scripts/dev/gates.sh --steps layers` | PASS 22/22 |
| impact selection (`tests/unit/test_progress_fanout.py tests/e2e/run_progress tests/e2e/test_vault_commit_order.py tests/e2e/test_card_and_progress.py tests/e2e/test_stateless_cli.py tests/e2e/test_run_native.py tests/e2e/test_run_command.py tests/e2e/test_run_chunked.py tests/e2e/test_run_mixed.py tests/e2e/first_user/test_items_generate_preview.py tests/sentry/layout tests/sentry/test_atomic_writer.py tests/sentry/test_one_stderr_console.py`) | branch 249 passed, 4 skipped; base (`PYTHONPATH=<worktree>/src`, minus the two new test paths) 234 passed, 3 skipped |

Failure sets: branch none; base none. `tests/e2e/test_vault_commit_order.py` passes with no edit
(L5a-vault-same).

## Sentry registrations

- `tests/sentry/layout/test_run_package_shape.py` `ORDER` gains `_progress` (first, since it
  imports no sibling). The shape rules are unchanged: `_progress.py` is 58 lines and imports no
  private module and no engine at module level.
- G-ONE-ATOMIC-WRITER: the `cli/run/_vault.py` reason text was corrected; the file, its 4 sites
  and the 3-entry allowlist are unchanged; no key was added (the ratchet passes).
- G-ONE-STDERR-CONSOLE is green: the display uses `state.err_console`, and no new Console exists.

## OS lanes

- Linux: run.
- macOS and Windows: not required (the plan's lane table lists L5a as Linux only).

## Not run

The full suite, mypy from `.venv`, and the `--chunked` event case (blocked by the engine
release).

## Deviations

1. **The `--chunked` route has no sink** (engine API); the case is skipped as blocked, not faked.
2. **The sink is sent only when the engine accepts `progress`** (capability check), to keep main's
   older-engine compatibility contract.
3. **Sequential, out-of-core and streaming routes are not forced** by any test: there is no CLI
   flag for them. The one `run_pipeline` call carries the sink whichever route the engine takes.
4. **No vault move and no invocation-id mint** (already on main); only the allowlist reason text
   was corrected.

## V2-LOG (noticed, not built)

- Once the engine pin carries RESULT E3: pass the fan-out to `run_mask_pipeline_chunked`, unskip
  the chunked case, and drop the "still takes no sink" pin.
- A test seam to force the engine's `execution_mode` from the CLI (or a `--execution-mode`
  developer flag) would let L5a-every-route cover sequential and out-of-core directly.
- The display could show a per-table bar once rate events carry `rows_total_estimate`.
