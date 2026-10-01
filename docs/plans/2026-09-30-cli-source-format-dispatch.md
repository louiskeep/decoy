# CLI source reading by declared format (Rust engine program A5a + A5b)

Status: plan (revision 2: folds the Codex plan-gate GO-with-revisions; split into A5a engine and A5b CLI)

Date: 2026-09-30. Program: decoy-engine `docs/plans/2026-09-30-rust-engine-program.md`, Phase A (record gap P5). Branch `fix/cli-source-format-dispatch`, off decoy-cli main `b8274b0`.

## Problem

The CLI reads each source by file extension: `.parquet` goes to `pyarrow.parquet.read_table`, and everything else goes to `pandas.read_csv(dtype=str)` (`src/decoy/cli/run.py` `_load_sources_from_config` ~1191-1224, duplicated in `src/decoy/cli/demo.py` ~268-285). The chunked path has its own suffix dispatch that recognizes only `.parquet` (`run.py` ~605, ~1095, ~1108). A source the config declares as `format: fixed_width` (with its `layout`) is therefore parsed as CSV, producing one wrong column per line instead of the layout's typed columns. The platform reads fixed-width with the engine's own reader, typed per the layout, so the same config masks differently in the CLI and the platform.

Separately, the CLI's native eligibility (`src/decoy/_native_gate.py` ~275-298) hard-codes Parquet, while the engine's unified-slice admission has accepted CSV and fixed-width since engine #180. CLI users with CSV or fixed-width files never get the Rust path.

## Design

### A5a (decoy-engine): a public source reader

The CLI must not import the engine's private `decoy_engine.profile._fixed_width_reader`: the engine README (~69-85) says non-top-level symbols may change without a version bump, and the CLI accepts any future engine version (`pyproject.toml` ~84-88). Export the fixed-width reader through `decoy_engine.__all__` as `read_fixed_width`, document it as public, and add it to the compatibility contract's public surface list. It ships in the Phase A paired engine release.

### A5b (decoy-cli): one reader, dispatching on the declared format

`FileSource.format` is required by the engine schema (`config/_sources.py` ~38-50), and run, demo and the API validate before reading (`run.py` ~444, `demo.py` ~223, `api.py` ~426), so there is no extension fallback.

- `decoy.cli._sources.read_source(table_name, src, base_dir) -> pa.Table`, used by `run.py` and `demo.py` in place of both copies: `parquet` with `pq.read_table`; `csv` with `pd.read_csv(dtype=str)` then `pa.Table.from_pandas(preserve_index=False)` (unchanged); `fixed_width` with the public `decoy_engine.read_fixed_width(path, layout)` then `pa.Table.from_pandas(preserve_index=False)`, as the platform does. An unknown format that somehow passes validation fails with the table and format named.
- `iter_source_chunks(table_name, src, base_dir, chunk_size)` for the chunked path, dispatching strictly on `src["format"]`; `_run_chunked_mask` passes the descriptor, not a path. CSV and Parquet stream regardless of suffix. The engine has no bounded fixed-width iterator, so `fixed_width` with `--chunked` is rejected in preflight with `EXIT_USAGE` before any table is written.
- Native eligibility accepts declared `csv`, `parquet` and `fixed_width`, with no suffix inference; its comments are updated.
- The CLI's minimum engine version is bumped to `decoy-engine>=0.7.0`, the release that will carry A5a (`read_fixed_width`), shipped later with other slices. CI and installs of this branch need that release; until then the branch is developed against the engine integration branch source on `PYTHONPATH`.
- Out of scope: `profile.py` (~120) and `init.py` (~122) are standalone path-driven profile and scaffold readers, not pipeline mask-source loaders.

## Acceptance tests (written first)

A5a:
1. `from decoy_engine import read_fixed_width` works and returns the same table as the private module; it is listed in `__all__` and in the compatibility contract.

A5b:
2. `decoy run` (default mode) with a `fixed_width` source reads typed columns per the layout (assert the Arrow schema) and produces the same masked output as the engine on `read_fixed_width` output; the same for `demo.py`'s path and for `decoy.mask(config=...)`.
3. CSV and Parquet sources read exactly as before (byte-identical output on existing fixtures).
4. Declared format wins over the suffix, in plain and chunked modes: a Parquet file named `.pq` or with no extension, declared `format: parquet`, reads as Parquet; a CSV file named `.dat` declared `format: csv` reads as CSV.
5. Missing or unknown `format` fails at the real schema boundary: CLI `EXIT_USAGE`, API `ConfigValidationError`.
6. `fixed_width` with `--chunked` exits `EXIT_USAGE` in preflight and writes no output table.
7. A malformed fixed-width file (short record, bad cast) surfaces the engine reader's error.
8. Native gate: CSV and fixed-width jobs are native-eligible when the companion is healthy; with a broken companion they fail closed as Parquet does; fixed-width succeeds under `--no-native` and `mask(native=False)`.
9. Before the change, tests 2, 4 and 8 fail.

## Gates

Codex plan-gate, Sonnet build, dennis, Codex final. A5a is an engine slice (merges under the standing Rust rule and ships in the Phase A paired release). A5b is a CLI slice: merge needs Cam's go, after CI is back and after the engine release it depends on.
