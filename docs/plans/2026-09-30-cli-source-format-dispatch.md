# CLI source reading by declared format (Rust engine program A5)

Status: plan

Date: 2026-09-30. Program: decoy-engine `docs/plans/2026-09-30-rust-engine-program.md`, Phase A (record gap P5). Branch `fix/cli-source-format-dispatch`, off decoy-cli main `b8274b0`.

## Problem

The CLI reads each source by file extension: `.parquet` goes to `pyarrow.parquet.read_table`, and everything else goes to `pandas.read_csv(dtype=str)` (`src/decoy/cli/run.py` `_load_sources_from_config` ~1191-1224, duplicated in `src/decoy/cli/demo.py` ~268-285). A source the config declares as `format: fixed_width` (with its `layout`) is therefore parsed as CSV, which produces one wrong column per line instead of the layout's typed columns. The platform reads fixed-width with the engine's own reader, typed per the layout (decoy-platform `api/jobs/v2_cloud_staging.py` `_read_sources_as_arrow`), so the same config masks differently in the CLI and the platform. The extension rule also misses `.pq`, which the CLI's own API (`src/decoy/api.py` ~227, ~297) treats as Parquet.

## Design

One shared reader, `decoy.cli._sources.read_source(src, base_dir) -> pa.Table`, used by `run.py` and `demo.py`, replacing both copies:
- Dispatch on the descriptor's declared `format`, which the engine's config schema requires on file sources: `parquet` reads with `pq.read_table`; `csv` reads with `pd.read_csv(dtype=str)` then `pa.Table.from_pandas(preserve_index=False)` (unchanged behavior); `fixed_width` reads with `decoy_engine.profile._fixed_width_reader.read_fixed_width(path, layout)` then `pa.Table.from_pandas(preserve_index=False)`, exactly as the platform does.
- If a descriptor has no `format`, fall back to the extension (`.parquet` and `.pq` for Parquet, otherwise CSV), keeping today's behavior for hand-written configs that omit it.
- An unknown format fails with a clear error naming the table and format, not a silent CSV read.

The engine import of the fixed-width reader is a private module; the platform already depends on it the same way. If the engine exposes a public reader later, both call sites switch together.

## Acceptance tests (written first)

1. A config with a `fixed_width` source and a layout: `decoy run` (default mode) reads typed columns per the layout and produces the same masked output as the engine reading the same file (compare with a direct `run_pipeline` call on `read_fixed_width` output).
2. The same in `demo.py`'s reader path.
3. CSV and Parquet sources read exactly as before (byte-identical output on existing fixtures).
4. A `.pq` Parquet source with a declared `format: parquet` reads as Parquet; with no declared format, `.pq` also reads as Parquet.
5. An unknown declared format fails with the table and format in the message.
6. Before the change, test 1 fails (the fixed-width file is read as one CSV column).

## Gates

Codex plan-gate, Sonnet build, dennis, Codex final. CLI slice: merge needs Cam's go, after CI is back.
