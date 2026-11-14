# CONFIG-EXPLICIT C1a build record (2026-11-14)

Status: record

Slice: roadmap row 22, CLI part C1a. Engine pin: decoy-engine 0.24.0 (already pinned).
Plan: the CONFIG-EXPLICIT handoff, Part C1 as narrowed by revision note r11.

## Where each route gates

| Route | Gate, before the first row read, stage or acquisition |
|---|---|
| `decoy run`, `tokenize`, `decoy.mask()` with a config | `run/_execute.py::_load_sources_from_config` calls `prepared_sources` |
| `decoy run --chunked` | `_run_chunked_mask` calls it before any reader or iterator exists, and passes the resolved config to the engine |
| `decoy demo` | `demo.py::_run_v2_mask`, before `profile_source` |
| `decoy.mask()` with DataFrame or Arrow data | `api.py::_gate_in_memory_data`, before `_stage_source_entry` writes a temp file |
| `decoy run --duckdb-source` | `_sources.check_declared_before_acquire`: `DESCRIBE` through `_duckdb_source.describe_relation`, engine check, then `acquire_relation` |
| `decoy report fidelity` and `integrity` with `--config` | `_sources.gate_report_source` on the selected table's descriptor with `path` set to `--source` |
| `decoy subset`, `decoy detokenize` | `prepared_sources` after the config parses, before the engine or the tokenized file is read |

`prepared_sources` (in `cli/_sources.py`) holds no rule. It builds the reader-side copy and calls
the engine's `prepare_declared_sources`. The CLI keeps its own readers.

## Changes on purpose

- `tests/e2e/test_source_csv_dialect.py::test_report_verbs_read_declared_dialect[fidelity|integrity]`:
  a single-table config now applies its own descriptor to the file given as `--source`, so a
  comma-headered declaration over a pipe-delimited file is refused (exit 1,
  `source_file.undeclared_column`). It used to fall back to the default dialect and compare
  `!= expected`.
- Fixture declarations added: `orders.id` passthrough in `tests/e2e/test_subset_command.py` and
  `tests/e2e/project_layout/test_pipeline_arg.py`; `tables` entries in
  `tests/e2e/test_source_format_dispatch.py::test_csv_and_parquet_sources_read_as_before`.

## Notes

- `acquire_relation(..., dest_dir=None)` returns the column names (`describe_relation` is the typed
  wrapper), so the DuckDB connection point and its sentry rows stay in one function.
- `decoy.mask(data=<path>)` and its `has_header` keyword (AT-C10) are C1b, not here.
- Not built, by ruling: the repin, `_config_load.py`, dump-site and path-copy edits (done earlier).
