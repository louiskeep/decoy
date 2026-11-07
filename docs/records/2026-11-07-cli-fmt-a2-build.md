# CLI-FMT Part A2 build record

Status: record

## Environment

Part A head `1586b29a`, `origin/main` `05bf8408`. GCP VM `cli` slot 6, venv `venv-cli-vmrun-1`, Python 3.10.22. Handoff amended 2026-11-07: `WRITERS` also holds `_write_fixed_width` (private helper of `write_table` in `_targets.py`).

## Write sites on Part A's head

Outside `_targets.py`: `api.py::_stage_source_entry` (spool) only. Inside: `write_table`, `write_chunked_output`, `_write_fixed_width`.

## Red runs (stubbed `_calls.py`)

21 failed, 9 passed on `test_target_writes.py` and `test_gate_target_format.py`. All failures are assertions: the spelling cases, the seeded bypass, the live-allowlist check, the writers check, and four gate tests (validate exit 0, no `ci check` finding, codes missing from `validation_codes()`). Passing under the stub by design: look-alikes, no-write-outside, baseline, matching-config.

## Green runs

48 passed (sentries, read sentry, gate e2e). T1 `gates.sh --keep-going --baseline`: sentry 511 passed, tests 555 passed, no failing ids on branch or baseline. Behavior-kept set (validate, ci, cli_fmt, rule codes, surface): 209 passed. `ratchet_check.py --slice CLI-FMT-A2`: `target-writes-allow: first inventory, 1 key(s), review required`, no finding.
Read sentry: real-tree tally is identical before and after the refactor (7 keys, 13 sites).

## Mutations (each red, reverted)

| Mutation | Red test |
|---|---|
| drop `method_names` | `test_seeded_bypass_is_red` |
| no attribute chain walk | `test_walk_sees_each_spelling[pyarrow.parquet.write_table]` |
| `write_table` on any receiver | `test_walk_ignores_lookalikes` |
| spool sites 2 | `test_allowlist_entries_are_live_and_exact` |
| drop WRITERS membership check | `test_writer_module_writes_only_in_its_writers` |
| drop registry row | `test_baseline_registry` |
| skip aliased from-import | read sentry `rc` spelling case |
| drop gate call | `test_validate_reports_the_contradiction` |
| drop mismatch code | `test_ci_check_renders_the_rule_id_not_the_unknown_token` |
| drop unknown code | `test_both_dynamic_codes_are_allowlisted_for_ci` |
| `to_csv` in `cli/unmask.py` | `test_no_table_write_outside_the_writer_module`, names `cli/unmask.py::unmask` |

## Deviations

- The validate output assertion checks the finding, not the whole envelope: the envelope's own `config` key echoes the path the caller passed (existing behavior).
- Look-alike case uses a local built by a factory call, since `pq.ParquetWriter(...)` is itself a watched construct.
- `ci check` fixture pattern copied from `tests/e2e/test_ci_exit_codes.py` (`tests/ci_support.py`).

## V2-LOG

Scanner limits (runtime-bound names, assignment aliases, star imports); unwatched writers (polars, feather, other pandas writers); chunked-only refusals stay run-time until `decoy run` adopts the gate (`_layers.py` `GateRoute.CHUNKED` branch); `csv.writer` and `write_text` unwatched.

## Gate round 1

Rebased onto Part A `b0b716e` (CHANGELOG conflict kept both sentences). Sentry and WRITERS hold on A's new code (`check_output_path`, compression backstop add no write site outside `write_table`, `write_chunked_output`, `_write_fixed_width`).

- Codex DESIGN: the gate imports `target_format_issues` from `decoy.cli.io` (`__all__` holds only that name), not the private module.
- Dennis MEDIUM: a watched member is reported wherever it is named, so `pool.submit(pq.write_table, ...)` and `functools.partial(pq.write_table, ...)` are seen.
- Dennis LOW: `pyarrow.dataset.write_dataset` is watched; `pyarrow.parquet`, `pyarrow.csv`, `pyarrow.dataset` and `decoy_engine` match as module prefixes (`pyarrow.parquet.core.write_table`).
- Dennis LOW: scopes are qualified names (`Class.method`, `outer.inner`); a nested `def write_table` is not the writer.
- Codex V2-LOG: bindings are per scope now (an import binds in its own module, function or class and what it contains). A parameter or local that shadows an import is still a named limit.
- Deviation: the read sentry passes `qualified_scopes=False`, because its frozen baseline key `cli/report.py::_load` is a nested function (`compare_data._load` when qualified). Part B can re-key it. Read tally still 7 keys, 13 sites.

Red first: 9 new cases failed on the old scanner (value references, `pyarrow.parquet.core`, `write_dataset`, scope names, nested writer, scoped imports). Mutations, each red then reverted: value references ignored (spelling cases), exact module match (`core` case), drop `write_dataset`, leaf scope names (`test_scopes_are_qualified_names`, nested-writer case), global bindings (`test_imports_are_scoped_to_where_they_are_made`); the earlier eleven mutations re-run, all red.

## Not verified

macOS arm64 run (not done). mypy (not installed in the VM venv; ruff check and format clean).
