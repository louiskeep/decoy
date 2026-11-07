# CLI-FMT Part B build record

Status: record

## Environment

Base: Part A2 head `16e82b1` on Part A `1586b29`, `origin/main` `05bf840`. GCP VM `cli` slot 6, venv `venv-cli-vmrun`, Python 3.10.22, engine 0.19.0, ruff 0.15.14 (mypy is not installed in that venv; the repo has no mypy gate). No repin.

## Reader table

R1 `detokenize` and R2 `unmask` read through `_targets.input_format` then `_sources.read_file`. R3 `report diff` reads each side through `_targets.entry_format` then `_sources.read_file`. I1 (`decoy init`) and S1 (`decoy scan`) Parquet reads moved into `_sources.read_file`. Read-site grep outside `_sources.py` after the change: `demo.py` (1 `read_csv`), `fit.py` (2), `scan.py` CSV (4) and fixed width (3). Nothing else.

## Manifest compatibility rule

`cli-local-1` gains optional `format` and fixed-width `layout` on `output_fingerprints` entries (module docstring of `evidence.py`). An entry without `format` takes the legacy rule (`.parquet` Parquet, else CSV), never `format_for_path`. Precondition 3 held: `docs/schemas/decoy-ci-v1.schema.json` `EvidenceCheck` holds `id` and `manifest` only and `src/decoy/ci/contracts.py` does not read `output_fingerprints`, so no closed key set applies.

## Changed sentry tests

`test_parquet_read_table_is_not_a_hit` became `test_parquet_reads_are_hits` (the owner widened the scope). `test_the_choke_point_reads_through_the_engine` keeps its guarantee for CSV-kind sites only (`_owns_csv`). Allowlist lost `cli/report.py::_load`, `cli/tokenize.py::detokenize`, `cli/unmask.py::unmask` (7 keys to 4); no key gained. Spellings added to `test_walk_sees_each_spelling`: `pd.read_parquet`, `pandas.read_json`, `pq.read_table`, `pyarrow.parquet.read_table`, `from pyarrow import parquet`, `pq.ParquetFile`, `from decoy_engine import read_fixed_width`, `polars.read_parquet`.

## Token width

AT-B2 and AT-B3 measure the token length from a CSV tokenize probe run (`_token_width`) and size the email column from it; AT-B3 uses one character less. AT-B6 sizes every column from the masked frame with `_target_layout` and sets `type: str` on all of them (`id`, `email` vaulted, `name`). Fixture shared with AT-B5: `id` passthrough, `email` hash with `vault: true`, `name` redact. STOP 3b did not fire: `unmask_pipeline` accepted the fixed-width read.

## Red runs (on A2 head 16e82b1)

13 of 16 e2e cases failed with assertions (B1, B2, B4, B5, B6, B15, B7, B8 x3, B9, B11, B12). Green by design: B3, B10, B10b. AT-B14 digests recorded on the base, twice, identical: init YAML `bd50b329...3271c0c`, scan JSON `81b904aa...f090a476` (temp folder replaced by `<TMP>`). AT-B13 and AT-B12 unit: red shown by mutation (below), not by a base run.

## Green runs

Named and behavior-kept tests plus `gates.sh --keep-going --baseline`: see Gates.

## Mutations (final code, each red, reverted)

| # | Mutation | Red test |
|---|---|---|
| M1 | R1 keyed on `.parquet` again | `test_detokenize_parquet_pq_round_trip`, `test_detokenize_fixed_width_round_trip`, `test_reader_off_target_uses_suffix` |
| M2 | no fixed-width branch in `read_file` | `test_detokenize_fixed_width_round_trip`, `test_unmask_fixed_width_target`, `test_report_diff_fixed_width_both_sides` |
| M3 | `write_table` falls back to CSV on a fixed-width write failure | `test_fixed_width_tokenize_refused_before_any_file` |
| M4 | `format_for_path` drops `.pq` | `test_reader_off_target_uses_suffix` |
| M5 | R2 CSV-only read | `test_unmask_parquet_target_at_dat`, `test_unmask_fixed_width_target` |
| M6 | `input_format` ignores the declaration | `test_unmask_parquet_target_at_dat`, `test_unmask_fixed_width_target`, `test_input_format_uses_the_declaration_for_the_target_file` |
| M7 | manifest drops `layout` | `test_manifest_records_format_and_layout`, `test_entries_carry_format_and_only_fixed_width_carries_layout` |
| M8 | R3 keyed on suffix | `test_report_diff_parquet_at_pq_dat_and_no_suffix` (3), `test_report_diff_sides_read_independently` |
| M9 | R3 reads fixed width as CSV (proxy for "layout from the pipeline file", which is not applicable as a one-line mutation) | `test_report_diff_fixed_width_both_sides` |
| M10 | legacy fallback is always CSV | `test_report_diff_old_manifest_falls_back` |
| M11 | legacy fallback uses `format_for_path` | `test_report_diff_old_manifest_pq_holds_csv` |
| M12 | side B read with side A's descriptor | `test_report_diff_sides_read_independently` |
| M13a | drop `DecoyError` from the `_load` except | `test_unreadable_entries_are_value_free` (engine-refused fixed-width case) |
| M13b | skip the unreadable-format check | the `input_format` and `entry_format` refusal unit tests |
| M14a-d | drop `read_parquet`, pandas `read_*`, `pyarrow.parquet` `read_table`, engine `read_fixed_width` from the watch table | matching `test_walk_sees_each_spelling` cases (`read_parquet` via the polars case) |
| M14e | `pd.read_parquet` back in `init.py` | `test_no_csv_read_outside_the_choke_point` |
| M15 | drop the second `.resolve()` | `test_reader_match_through_symlinked_dir` |
| M16 | `read_file` Parquet through `pq.read_table(...).to_pandas()` | none: AT-B14 is characterization only, the digests do not change |

Finding: the undecodable-CSV case in AT-B12 does not exercise `DecoyError`. With the default dialect the engine CSV reader raised `UnicodeDecodeError` or a pandas `ParserError` (both `ValueError`) for every bad input I tried; M13a survived until I added an engine-refused fixed-width case (`FixedWidthParseError`), which kills it. The undecodable-CSV case stays as a `ValueError` check.

## Gates

See the report: `gates.sh --keep-going --baseline` on the final head, VM slot 6.

## Files vs allowed list

All changed files are in the handoff list. Added beyond the list: none.

## Size

Hand-written insertions exceed the plan's 800 line cap (tests, about 710 of them). Accepted by the coordinator. `_targets.py` is 417 lines (cap 400): V2-LOG.

## Deviations

1. `read_file` passes `str(path.resolve())` to `read_csv_frame`; the plan's `str(path)` with `path.parent` doubles a relative path.
2. `input_format` and `entry_format` read the declared `format` directly, without the suffix contradiction check, so an old file (CSV at `.pq`) stays readable.
3. `build_manifest` omits `format` for a target that `resolve_target_format` refuses. It cannot fire after a run: the gate refuses those targets before any source is read.
4. AT-B9 mutation uses a proxy (M9).
5. `report.py`: pandas guard is `import pandas  # noqa: F401`; `DecoyError` is imported inside `compare_data`. Net lines 2381 to 2369.
6. The unreadable-format error text is fixed and holds no path or format name.

## Self-review (brief classes 1 to 18)

1. checked: error and note texts in `input_format`, `entry_format`, `read_file`, detokenize and unmask read failures, and `report diff` unreadable path. Texts are fixed literals; AT-B12 asserts no cell value, the unit test asserts no format name or path. The detokenize failure line prints the input path as before.
2. checked: no new locking or shared state; reads only.
3. checked: `input_format` on a non-mapping `targets`, a missing table, a non-string path, an empty layout; `entry_format` on a missing `path`, `format: None`.
4. checked: R1, R2, R3, I1, S1 all go through `_sources.read_file`; sides A and B read independently (AT-B11, M12). The `scan`/`demo`/`fit` CSV reads stay allowlisted.
5. n/a: no foreign keys or stored rows.
6. checked: every AT has a mutation (table above); no test weakened, no pin raised (allowlist shrank by 3 keys, size pins untouched). The two sentry test edits are named above.
7. checked: manifest docstring, changelog sentence, help text and generated reference match the code (suffix rule `.parquet` or `.pq`, declared format first).
8. checked: layout column names go into the manifest (names and positions only, no data) and are not printed.
9. checked: no read moved past the sentry; the sentry was widened and the three allowlist keys removed, `init.py` and `scan.py` rerouted, not allowlisted.
10. checked: legacy rule is the old writer's (`.parquet` Parquet, else CSV), AT-B10 and B10b.
11. checked: every format a writer can produce (csv, parquet, fixed_width) is read back by detokenize, unmask and report diff; `decoy report fidelity` and `integrity` stay CSV-only (V2-LOG).
12. checked: symlinked directories (AT-B15). Windows case-folding and unicode-normalized paths not tested.
13. checked: no test that cannot go red; AT-B14 and the three green-by-design tests say so.
14. checked: one reader module (`cli/_sources.py`), one format-decision module (`cli/io/_targets.py`).
15. checked: `report.py` 2369 (down), `_sources.py` 183, `_targets.py` 417 (over its 400 cap, logged), `tokenize.py` 741, `evidence.py` 584, test file 498.
16. checked: grep of read calls and of suffix-to-format logic. Copies: `format_for_path` and `_legacy_format_for_path` are two deliberately different rules (documented); no third.
17. checked: new tests in `tests/e2e/cli_fmt/` and `tests/unit/cli_fmt/` per the plan's Placement table; no new directory.
18. recurring-defects catalog: 1 anchored validation n/a (no regex added); 2 strict wire types n/a (manifest entries are read as untyped dicts; unknown or non-string `format` is refused); 3 no exception context: errors are built in `_unreadable` outside any except block (unit test asserts `__cause__` and `__context__` are None); 4 versioned read models: the manifest version tag is unchanged and the missing-`format` case is the documented legacy read; 5 normalized scanners: seeded case per new spelling; 6 private imports: `evidence.py` imports `decoy.cli.io._targets` (same package family, as `run.py` does); 7 hidden CI failures n/a; 8 trust classes n/a; 9 mutations run on the final code head; 10 allowlisted helpers: the allowlist only shrank; 11 no raised pins.

## V2-LOG

- `decoy report fidelity` (`report.py` near :1812, :1817) and `decoy report integrity` (near :2082) read CSV only through `read_report_source`.
- `build_manifest` records target paths as written in the YAML, not resolved against the config folder (`evidence.py` output loop); `report verify` and `report diff` resolve them against the current folder. No test runs from another folder.
- The read sentry's file and id still say "csv"; H-1 renames them.
- `_targets.py` is 417 lines (cap 400).
- `compare_data` skips every later table once any `missing_files` entry exists (`if missing_files: continue`).
- Windows case-folding and unicode paths for the reader match are not tested.

## Not verified

macOS arm64 run (optional per the brief) not done. mypy not run (not installed in the VM venv; no repo gate). Full suite not run (orchestrator T3 covers the serialization and sentry-baseline triggers).
