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
| `decoy subset` | `prepared_sources` after the config parses, before the engine opens a source |
| `decoy detokenize` | none: a caller-named-artifact route, no declared source is opened (ruling below) |

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

## Fix round 1 (Dennis NO-GO)

- Ruling on the spec conflict for `detokenize`: the route table line 228 wins ("validate and gate
  the config before reading the artifact; no declared source is opened"). The first build called
  `prepared_sources`, which opens every declared file, so a deleted source broke detokenize.
  The call is gone, the sentry no longer lists detokenize as a gated reader, and the AT-C13 cell
  asserts the declared file is never needed.
- One exception contract: `prepared_sources` turns an engine read failure (`OSError`,
  `ValueError` from Arrow or decoding, a non-gate `DecoyError`) into a `PipelineValidationError`
  with a registered code (`source_file.file_not_found`, else the error's own code or
  `csv_malformed`) and a fixed path-free text. Every caller already catches that one type.
- `gate_report_source` checks a non-csv declared descriptor with `csv_file_source(source)`, the
  descriptor `read_report_source` reads with.
- `duckdb_probe_config` (in `_sources.py`) is the one placeholder-probe builder for
  `check_declared_before_acquire` and `_refuse_chunked_integrity`. It is the r11 ruling-4
  exception: the config is parsed before the gate only so that an unparseable config keeps the
  gate's own error.
- The ambiguous `--source` refusal has the CLI-registry code `layout.report_source_ambiguous`.
  Subset prints an engine refusal's text without its leading code.
