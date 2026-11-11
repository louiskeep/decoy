# Changelog

All notable changes to the `decoy-cli` PyPI distribution (which ships
the `decoy` import package + the `decoy` console script) land here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
version numbers follow the [versioning policy](docs/release/versioning.md).

## [Unreleased]

### Added

- **`decoy fit --fanout COLUMN` records how many rows each key has (QA-FK-FANOUT C1, roadmap row 24h).** Repeatable. Name the child-side key of a foreign key (`decoy fit visits.csv --fanout patient_id`) and the snapshot gains a `fanout` block on that column: the row count, the key count and a histogram of children per key. It holds counts only, never a key value. A generate `reference` column with `distribution: fitted` and that snapshot gives each generated parent a child count drawn from the source shape, with no orphans; other distributions are unchanged. `fit` prints `fan-out kept for patient_id: 8 keys, up to 8 rows per key` and a hint to use `fitted`; `fit --json` gains `fanout_columns` (empty when the flag is not used). A column that is not in the CSV exits 1 naming it (`fanout_column_unknown`) before the snapshot is computed. `--fanout` with `--epsilon` exits 1 (`dp_mode_fanout_unsupported`) before the CSV is read, because a DP release carries no per-key counts. Needs engine 0.22.0, which the CLI already pins. A snapshot fitted without `--fanout` is byte-identical to before.

- **Generation is easier to find (GEN-CLI C3, roadmap row 24o).** `decoy --help` groups the commands into panels (Start, Run, Generate, Mask, Check and report, Reference) and its footer names the generation path (`fit`, `run`, `report fidelity ... --generate`); a sentry fails a command that has no panel. New topic `decoy explain generation` covers the workflow, the path rule, seed versus `--master-key`, the fidelity warning and `run --rows`, and lists every column type and option from the engine's `generate_option_catalog()`, so a type the engine adds shows up with no CLI edit. `decoy validate compile --explain` now shows each generate table (rows, column types, references) and the generation order, parents first, from the engine's `generation_order`; `--json` gains `generation`. The "no FK dependencies detected" line no longer prints for a pipeline that has generate tables. `explain transforms` lists the strategies the engine registers (the same set as `decoy list strategies`), uses `strategy:`, and no longer mentions `masking_rule` or a future `--mask` flag; `explain pipeline` and `explain yaml` state the path rule and the generate column shape. Three user-text pointers to topics that never existed (`explain types`, `explain strategies`, `explain evidence`) now name real ones, and a test fails on the next one.
- **CLI checks for strict generate-column options (GEN-STRICT C1, roadmap row 24k).** No behavior change: the engine 0.22.0 repin above brought the checks. New tests in `tests/e2e/generate_config/` hold the CLI to them. Each input from the generation QA record that used to pass `decoy validate` (an option typo, a negative or all-zero weight, `null_probability: 2`, `step: 0`, a duplicate column name, an unknown faker type, locale or keyword, a broken or unreferenced formula, mixed category types, `group_by` equal to `order_by`, a `derived` column that reads a later one) now fails `validate` with exit 1 and its code, located at `tables.<i>.generate_columns.<j>.<key>` or named by table, column and option, and `decoy run` stops at its pre-run gate with exit 1 before writing any output. No message carries the option's value. `decoy schema` closes each of the 13 generate types (`additionalProperties: false`). The capacity cases (`row_count` too large for memory, exit 5) follow in C2.

- **`decoy fit --joint-max-cells` and warnings when a `condition_on` pair loses combinations (GEN-COND-CAP C1, roadmap row 24w).** A `--joint` pair keeps its 25 most common combinations; `--joint-max-cells N` keeps up to N (at most 1000, the engine's bound) and needs `--joint` (`fit_joint_max_cells_needs_joint`, exit 1, checked before the `--epsilon` rules, so `--joint` with `--epsilon` still exits with `dp_mode_joint_unsupported`). A value outside 1 to 1000 or not a whole number exits 1 with `contingency_top_k_invalid`. Without `--include-values` a cap above 25 needs both columns to be plain categories, else exit 1 with `contingency_top_k_kind_unsupported`; no snapshot is written on any of these errors. When the cap drops combinations `fit` prints one `warning:` line per pair on stderr (not with `--quiet`) with the counts and the cap that keeps them all, and `fit --json` gains a `warnings` list (`code`, `message`, `detail`), empty when nothing was dropped. A pair touching a withheld sensitive column gets no warning. `decoy run` now words `generation_condition_parent_unseen` in its summary: how many rows of a conditional column had a parent value with no fitted combination and drew from the column's overall counts. Warnings carry column names and counts, never a value.

- **Project root finder, pipeline names, run-folder helpers and the `layout.*` error registry (PROJECT-LAYOUT P1b, roadmap row 24t).** No command uses them yet; they are the services the next slices build on. `find_project` looks for `decoy.yaml` with `kind: decoy-project/v1` from a folder upward, stopping after a folder that holds `.git`, at a device change and before `$HOME`, and refuses a marker that is a link, over 64 KiB, bad YAML, or owned by another user. Pipeline names follow the engine's `is_valid_pipeline_name`; a name claim file, the `out/` folder with its `.gitignore`, UTC run ids and 0700 run folders (`_private_file.create_private_directory`) and the Windows 259-character budget are in `decoy.cli.io`. Two sentries (`test_pipeline_argument.py`, `test_layout_errors.py`) hold the single root finder and the single code registry; the registry's gate codes join the `decoy ci` rule-code set.

### Changed

- **Generated tables too large for memory exit 5 at `decoy validate` and before `decoy run` writes anything (GEN-STRICT C2, roadmap row 24k).** With engine 0.22.0 the preflight capacity check refuses a config whose resident generated output cannot fit the machine's memory (`generation_budget_exceeded`), so `decoy validate` exits 5 and `decoy run` stops at its pre-run gate with exit 5 (`--json` `error_kind: capacity` and the code). The finding text is picked by code: a generate refusal shows the engine's byte counts and largest table name and says to lower `row_count` or use a bigger host, while an out-of-core refusal keeps its old text. A bare `MemoryError` during a run now exits 5 with `capacity: the run ran out of memory.` (`--json` `error_kind: capacity`, no code) instead of exit 3 with an empty `error: `. A config with a non-file source skips the estimate, so a generate floor refusal there exits 5 only at `decoy run`. A config with a missing or unreadable source file exits 1 first (the engine is not reached), so the exit 5 needs readable sources. `decoy validate preflight --help`, `decoy explain exit-codes` and the README exit-code table no longer say the generate path is unchecked. No message carries a generated value.
- **Config errors show names and locations, never submitted values (VALUE-FREE-ERRORS A3, roadmap row 24a).** Every command that validates a pipeline config (`validate`, `validate config`, `validate preflight`, `subset`, `run`, `tokenize`, `detokenize`, `report fidelity --config`, `report integrity --config`, `demo`, `init`) and `decoy.api.mask` now goes through the engine's `parse_pipeline_config` and prints `PipelineConfigError.problems`. The old paths printed Pydantic's text, which echoed a bad value, an unknown key's value or the union tag you typed. Config keys, table and column names and file names stay in the text. `--json` keeps its `code`, `message` and `location` keys; the `message` text for validator failures and the form of `location` change, and `decoy validate config` text now ends with the location. `decoy tokenize` no longer cuts the error at 500 characters. `decoy.api.mask` raises `ConfigValidationError` with no chained Pydantic error. `sanitize_yaml_error` is now the engine's `yaml_error_text`. A new sentry (`tests/sentry/defects/test_config_error_routes.py`) walks `src/decoy` for any other route to a raw `ValidationError` and runs each config-taking command on a marker config.

- **`decoy validate compile` sees the pipeline's relationships, and `decoy validate` reports a relationship error once (CLI-QA1 C1).** The no-profile compile used a sentinel profile with no relationships, so it printed `no FK dependencies detected` for a pipeline that declares one and passed a relationship the engine cannot resolve. It now builds the sentinel from the config's `relationships:` through the engine's `profile_relationships_from_config`: `--explain` lists the parent table before its child, and a parent and child column with no shared namespace fail with `namespace_missing` (exit 1) as `decoy validate` reports it. A composite relationship whose parent and child column counts differ is a compile error on both commands, not a crash. In `decoy validate`, when the compile layer already reports the error the capacity estimate hit, the preflight `capacity.plan_uncompilable` row becomes a warning that says capacity was not checked, so the error shows once and the preflight layer no longer prints `passed`; `decoy validate preflight` on its own still fails that row. Breaking pre-GA: a no-namespace relationship that `validate compile` used to pass now fails. A new first-user test also checks that `scan`, `demo` and `run` leave no `logs/` folder in the working directory (fixed by the engine 0.21.0 pin).

- **`decoy fit --rows N` fits on a seeded sample of a large file.** A file over the limit is cut to N rows drawn at random from the whole file (fixed seed 42, file order kept), never the first N, so the same file gives the same sample. The limit is `--rows`, else `fit.max_rows` in `$DECOY_HOME/settings.json` (a `fit` object beside `resources`; `decoy setup` leaves it alone), else 1,000,000. The rows are chosen by record position before pandas infers column types, and only the sampled rows are materialized and type-inferred (a first pass counts every record, a second keeps the sampled ones), so a row outside the sample cannot change a column's kind and the whole file is never held in memory. Blank and whitespace-only lines are not records, as in an unsampled fit, and a quoted newline stays inside its record. The engine's `distribution_snapshot_document` runs on the sample with no `profile_row_cap`, so the sensitivity check and the stored values come from the same rows. The seeded row choice is shared with `decoy scan --strategy random` and the `decoy.scan` API. A file at or under the limit uses every row and writes the same bytes as before. The summary line now reads `fitted on N of M rows` and `fit --json` gains `rows_used` and `rows_total`. `--rows` of 0, a negative number or a non-integer, and a bad `fit.max_rows`, exit 1. `--rows` with `--epsilon` exits 1 (`dp_mode_rows_unsupported`); a DP fit never samples and ignores the setting. A CSV record with more fields than the header is now refused (exit 1, value-free) on every fit, sampled or not; pandas used to read an over-wide first record as an index column and shift every value one column left.

- **`decoy fit` and `decoy report fidelity` show null rates, and CSV output keeps integer spelling (GEN-FIT-SHAPE C1, roadmap row 24l).** The `fit` summary appends `, N% null` to each column that has nulls, and `fit --json` gains an additive `null_rates` map (column to share, from the engine's `snapshot_null_fraction`). `report fidelity` adds a `Nulls (source/output)` column to the per-column table when some column's `missing_value_similarity` is below 1; its `--json` is unchanged. Both CSV writers (whole table and `--chunked`) convert Arrow through one `_csv_frame` that maps each signed and unsigned integer type to its pandas nullable dtype, so a null-bearing integer prints `23` and `uint64` is not narrowed. Two sentries (`tests/sentry/io_policy/test_csv_frame_choke_point.py`) fail on a direct `to_pandas().to_csv` and on a null-rate division outside the engine helper.

- **`decoy run` exits 1 when a `unique` generate column cannot be satisfied, and 5 when generated output cannot fit the memory budget (GEN-UNIQUE C1).** With engine 0.21.0, `unique: true` on a `faker`, `categorical` or `reference` column and `unique_together` on a table can fail at run time (a parent with fewer distinct keys than rows, a faker type that runs out). That engine refusal, `uniqueness_impossible`, now exits 1 (a config problem) instead of 3, before any output is written; the message names the table and column, with counts or the row where values ran out, and never a value. This also moves the masking pool's `uniqueness_impossible` refusal from 3 to 1. Other `GenerationError` codes (`dtype_unsafe`, `timezone_naive_datetime`) still exit 3. `generation_budget_exceeded` now exits 5 (`--json` carries `error_kind: capacity` and the code) instead of 3. New topic `decoy explain unique` covers `unique`, `unique_together` and `pooled`; `decoy explain exit-codes` and the README table name both cases. No flag or verb changes.

- **Relative YAML paths read from the config file's folder in every command, and `decoy run --fidelity` refuses a config with no mask table (breaking, pre-GA; GEN-CLI C1).** A relative source or output path in the YAML now resolves against the folder holding the config file, not the shell's working directory, in `run`, `tokenize`, `validate`, `preflight`, `demo` and the Python api; run from another folder and the same config reads and writes the same files. `decoy run --fidelity` on a config with no mask table (generate tables only) now exits 1 with a pointer to `decoy report fidelity ... --generate`, where it exited 0 and scored nothing. `decoy run` also prints the engine's warnings and one line per table under the summary card; a warning that carries a large map shows its size in the human line (`key=<N entries>`) and keeps the full detail in `--json`.

- **`decoy fit --epsilon` refuses an uncertified install before it reads any data row (QA-DP-GATED).** DP mode reads only the CSV header, runs the column-name checks, and asks the engine's `check_dp_fit_request` (bad `--epsilon`, `--delta`, `--numeric-bins` and carrier declarations keep their codes), then reads the body. On an install that is not a certified platform and package set, `fit` exits 3 with `DP fit is not available on this install: it runs only on a certified platform and package set.` and a hint that names `--include-values` first and says a DP release needs a certified install. The engine code, platform and fingerprint print under `--verbose`; `--json` still carries `code` and `message`, and `hint` holds the new text. A CSV that changes between the header and body reads exits 1 with `dp_source_changed`. `fit --help` and `decoy explain differential-privacy` say DP is gated.

- **`decoy fit` withholds the values of sensitive columns by default (breaking, pre-GA; QA-FIT-REDACT).** The snapshot used to copy real cell values (SSNs, names, ids) into `top_values`. `fit` now writes it through the engine's `distribution_snapshot_document`, profiling the whole file: columns the profiler flags keep no cell values, a number column keeps one range and a date column keeps years. The file carries `value_policy: flagged-redacted/v1` and `redacted_columns`, `fit` prints the withheld column names (never values), and `--json` gains `value_policy` and `redacted_columns`. A `statistical` column on a withheld column now fails `decoy validate` with `statistical_snapshot_values_redacted`. Fix: re-run `decoy fit --include-values` to keep the values (the file then holds real data and `fit` warns on stderr); it is a usage error with `--epsilon`. Snapshots now also carry `cell_format` per column. An unreadable CSV no longer echoes the parser's text.

- **`decoy demo` writes a redacted `scan.json`.** The demo scan file was the engine's raw `profile.to_dict()`, with the sample's top values. It is now `decoy_engine.profile_document`: `value_policy: flagged-redacted/v1`, a `redacted_columns` list, and `[redacted]` in place of the sensitive columns' values. `decoy scan show` and `scan fields` read it as before. `decoy explain security` no longer says a saved scan can hold top values (it says `decoy scan --output` files hold none, and that a plain `decoy fit` snapshot withholds sensitive columns' values unless you pass `--include-values`), and the `decoy.scan()` docstring says the returned profile holds cell values while `decoy scan --output` writes the value-free core. A new sentry (`tests/sentry/io_policy/test_profile_document_route.py`) fails when a module calls `.to_dict()` on a profile from `profile_columns`.

- **`decoy scan` takes several files, needs a header flag for every CSV, and `--output` holds no cell values (breaking, pre-GA; SCAN-MULTI S1c.1).** `decoy scan A B C` profiles each file as its own table (named from the file stem, lower-cased to `[a-z0-9_]`, a `t_` prefix before a leading digit; two files with one stem are refused before any read) through the engine's `scan_sources`, and prints one summary row per table plus the PII-suggestion note once. A CSV now needs `--has-header` or `--no-header`; scan no longer assumes a header row, and a CSV without either flag exits 1 before reading. `--no-header` needs `--column-names a,b,c` for exactly one file. A header row that looks like data (a structured PII value, or an all-numeric or all-date row) prints a warning naming the table, and the saved scan then names those columns `c0`, `c1`, and so on. `--output` (and `--output -`) now writes the value-free `scan-set/v1` core (counts, rates, type labels, detector ids, column names) instead of the engine's `profile.to_dict()`, whose `top_values` held cell values; the file is written once, after every table scanned, so a failed table leaves no file. A single-file `--json` keeps its flat keys; several files print a `scan_schema`/`tables`/`relationships` envelope. `decoy scan fields`, `show` and `diff` read saved scans through one reader that accepts `scan-set/v1` and the older bare profile, take `--table` (required when the file holds more than one table), and no longer print `top_values` or sentinel values from an old scan file. `--config`, `--column-names-file` and the integrity block follow in S1c.2.

- **Engine repin to `decoy-engine==0.22.0` (`v0.22.0`).** Breaking for consumers: a generate column that names an unknown faker type or locale, passes a keyword its provider does not take, mixes category types, reads a column that is not ready yet, or has a formula with an unknown name now fails at `decoy validate` and `decoy run`. Engine changes you see through the CLI: two new generate column types, `constant` and `distribution` (only `family: uniform` ships), need no source file; a `formula` the runtime cannot evaluate is refused with `generate_formula_invalid` instead of generating nulls; profiling a full frame is back to seconds at 1M rows, with k-anonymity now covering category-dtype and mixed-object columns. `requirements-certified.txt` records fingerprint `d5898d1f...` for engine 0.22.0 (the 63 pins are unchanged). No CLI flag or verb changes.
- **Engine repin to `decoy-engine==0.21.0` (`v0.21.0`).** Breaking for consumers: `contingency_top_k` accepts only an int from 1 to 1000, and a cap above the default is refused in a plain snapshot when a joint column is numeric, datetime, freetext, empty or `high_cardinality` (`quality.contingency_top_k_kind_unsupported`). Engine changes you see through the CLI: a conditional `statistical` generate column whose `condition_on` parent has no fitted combination now raises `warning.generation_condition_parent_unseen`, and a generation table or column below `fidelity_warn_threshold` raises `warning.generation_fidelity_below_threshold` (the CLI maps codes from the engine registry, now 1.22.0); fitted number columns keep their shape through a quantile grid, so generated numbers differ from 0.20.0 for a fitted snapshot; tables with two or more parents generate parents first, so the order of written targets may differ. `requirements-certified.txt` records fingerprint `aa038ddd...` for engine 0.21.0 (the 63 pins are unchanged). No CLI flag or verb changes.
- **Engine repin to `decoy-engine==0.20.0` (`v0.20.0`).** The engine types generated numeric columns (an unformatted `sequence`, a faker provider that returns an int or a float) as int64/float64 instead of text. CSV targets now write an integer column that holds a null as integers (`1001`, not `1001.0`), for generated and masked tables, on plain and `--chunked` runs, and `decoy.mask()` returns pandas nullable integer columns for generated tables. Engine changes you see through the CLI: a generate column with an option key its `type` does not read is refused at validate with a `config.generate_*` code (deleting the key changes that column's seed and output); `decoy report fidelity` scores numeric columns on the source interquartile range, so scores drop for skewed or drifted columns (re-check `--min-score`, `--min-grade` and `fidelity_warn_threshold`); a generate run whose output cannot fit in memory is refused with `generation_budget_exceeded`; a source with duplicate field names is refused with `duplicate_source_field_names`; under `global_settings.dp` a `reference` column with `distribution: fitted` is refused. `requirements-certified.txt` records fingerprint `725f80a3...` for engine 0.20.0 (the 63 pins are unchanged). No CLI flag or verb changes.
- **`decoy run` says how many tables, rows and files it wrote.** The summary card gains `Tables`, `Rows` and `Files`, and the `--json` payload gains `tables`, a list of `{name, rows, path}` records. `path` is the file actually published, never one inferred from the config, and a `--chunked` run reports `rows: null` (card: `Rows n/a (chunked)`) because it streams without counting. A chunked table whose stream yields nothing publishes no file, so it is `path: null` and is not counted in `Files`.

- **`--json` output of `decoy validate compile` and `decoy validate preflight` reports the command you typed (breaking, pre-1.0).** The `command` field said `compile explain` and `preflight`, the names from before both moved under `validate`; it now says `validate compile` and `validate preflight`, with no alias. A new sentry reads the command tree and fails when any envelope `command` value is not a command the CLI has.
- **User text no longer names tickets, private modules or hidden commands.** The old-engine mask-secret refusal on `decoy run`, `decoy tokenize` and `decoy.mask()` no longer cites an internal ticket id; each surface prints one fixed text from the mask-secret guidance registry and says to upgrade `decoy-engine` to 0.4.0 or later. A new sentry (`tests/sentry/cli_text/test_user_text_internal_names.py`) fails when command help, usage lines, `explain` topics, string constants or bundled templates carry a ticket id, a private engine module path or `_scan`/`_gate`.

- **`decoy validate preflight` and `decoy validate` report a plan the engine cannot compile as a failed check, not a traceback.** A relationship whose parent and child columns share no namespace made the capacity estimate raise the engine's `namespace_missing` out of the command. The capacity step now records a `capacity.plan_uncompilable` failure carrying the engine's error code and config path (`decoy validate` shows the code, exit 1), and the `--chunked` route keeps it a failure. `decoy run` refuses the same config through its pre-run gate instead of crashing. `capacity.plan_uncompilable` is added to the `decoy ci check` rule-code vocabulary.
- **An unexpected crash in any command prints one line and exits 1, not a Python traceback.** The root app now wraps every command: an unhandled exception prints `error: internal error (<ClassName>)` with a hint to rerun with `--verbose`, which adds the traceback (and a note that diagnostic output may contain row data). `DECOY_DEBUG=1` re-raises the exception untouched, as `decoy explain output` already documented. Exit codes for usage errors (2), Ctrl-C (130), `SystemExit`, a closed pipe and every code a command sets itself are unchanged.
- **The install `current` link swap moves onto `_atomic.replace_symlink` (PROJECT-LAYOUT P1a).** Behavior is unchanged except that a regular file or folder named `current` is now refused (`could not place or activate`) instead of replaced; only a symlink or nothing is swapped.
- **`decoy validate compile --output` writes a private, atomic plan file, and the token vault and `decoy.mask()` spool use one private-file helper (X7c).** The plan artifact is now owner-only (0600) on Linux and macOS and is written atomically; a write failure prints `atomic_write_failed` with the OS reason and exits 3 (`--json` emits `status: error`). `decoy tokenize --vault` now refuses a symlink at the vault path (opened with `O_NOFOLLOW`) with `vault_open_error`. The `vault_permission_error` text no longer names the path. A `decoy.mask()` spool failure is raised as a `PrivateFileError` (an `OSError` carrying a code and errno, no path), the spool temp file name is now `.decoy-mask-<table>-....decoy-<hex>.tmp` in the system temp directory, and a spool whose Parquet write fails is removed.
- **`decoy run` runs the whole `decoy validate` check before it reads any data (breaking, pre-1.0).** Config, compile and preflight run first, through the same code `decoy validate` and `decoy ci check` use (a `--duckdb-source` relation is staged first so the check sees the file the run reads; a config that is not UTF-8 still exits 3 until FU-7); an error stops the run with `decoy validate`'s exit code (1, or 5 for a capacity refusal) and nothing is read or written. There is no skip flag. Exit codes: a missing, unreadable or corrupt source file, and a no-profile compile crash, now exit 1 where `decoy run` exited 3. `decoy run --json` on a refusal keeps `command`, `status`, `config`, `mode` and `error` and adds `error_kind` (`validation`, or `capacity` with `code`, or `missing_extra` with `extra`, as before) and `messages` (the list `decoy validate --json` emits, each message cut to 500 characters). The `error` text for a config refusal is now a one-line summary naming the first finding and its location, no longer Pydantic's `str(exc)`. Warnings never stop a run; human mode prints one stderr line with their count. On `--chunked` a capacity refusal is an advisory warning, because that route never takes the out-of-core path it prices. Related contract changes: a `cardinality_mode: unique` column moves from the error `no_profile_unique_incompatible` to the warning `compile.needs_profile` in `decoy validate` (exit 0, or 2 with `--fail-on-warning`; `validate compile --no-profile` keeps its error), and `decoy ci check` rule `validate.no_profile_unique_incompatible` (error) becomes `validate.compile.needs_profile` (warning); `decoy validate config` reports `target.<table>.would_overwrite` (was `target_file.would_overwrite`) and `target.<table>.parent_missing`, and `decoy ci check` in config-only mode reports them too; the `capacity.source_unreadable` check (code `capacity_source_unprofilable`) prints the error type, no longer the reader's text.
- **A failed target write no longer leaves a partial or clobbered output (V1 data-loss fix).** `decoy run` (plain and `--chunked`), `decoy tokenize`, `decoy unmask`, `decoy detokenize`, `decoy demo` and `decoy.mask(out=...)` write CSV and Parquet through a hidden temp file in the target's directory (`.<name>.decoy-XXXX.tmp`) and move it onto the target only after the writer finishes, so a failure leaves the old file, or no file if there was none. A symlinked target updates its destination and stays a link; a FIFO, a device, and an fd alias (`/dev/stdout`, `/dev/stderr`, `/dev/fd/N`, `/proc/self/fd/N`, including a stdout redirected to a regular file) is written through as before, without staging. A `format: csv` target under `.gz`, `.bz2`, `.xz`, `.zst`, `.zip` or `.tar*` is still compressed by the real name; a `.tar.gz` or `.zip` archive now holds one member named like the target without the archive suffix (`out.csv`). Permissions: an existing output keeps its mode bits, a new one gets the umask default, and `decoy unmask` and `decoy detokenize` outputs, `decoy fit` snapshots, `decoy scan -o` profiles, `--evidence-out` manifests and `decoy report` files are now owner-only (0600) on Linux and macOS and written atomically; on Windows they inherit their folder's permissions, as before, until Windows private-file ACLs land (CLI roadmap X7c and WIN-FEAS). A write failure prints the code and the OS reason (`atomic_write_failed (No space left on device)`), with exit 3 for run, tokenize, unmask, detokenize, fit, scan and the evidence manifest and exit 1 for report files. Named limits: SIGKILL (or an unhandled SIGTERM) before the move keeps the target intact but can leave the hidden temp; a multi-target run is not one transaction (a finished target stays, a later failure leaves its target as it was, exit non-zero); a `.gz` header can store the temp name; hard links to an output are broken by the replace; for a moment the disk holds the old and the new file; an extended ACL or xattr on an old output is not copied; an output you can write in a directory you cannot write to (or another user's file in a sticky directory) now fails with `atomic_write_failed` and keeps the old file; a read-only existing output is now replaced and keeps its read-only bits.
- **File targets are written by their declared `format` (breaking, pre-1.0).** `decoy run` (plain and `--chunked`), `decoy tokenize`, `decoy demo` and `decoy.mask()` wrote CSV unless the path ended in `.parquet`, and ignored `format`. A target whose declared format contradicts its suffix (`format: parquet` at `out.csv`, `format: csv` at `out.parquet` or `out.pq`, `format: fixed_width` at `.csv`, `.parquet` or `.pq`) now exits 1 before an ordinary file source is read (named limits: `decoy demo` reads its sources first, `--duckdb-source` snapshots its relation first, and `decoy.mask(data=...)` stages a temporary Parquet first), with a message naming the table, the format and the suffix. Parquet and `fixed_width` targets, and `decoy unmask` and `decoy detokenize` outputs that resolve to Parquet, also exit 1 under a compression suffix (`.gz`, `.zip`, ...), because those writers do not compress. `.pq`, `.dat` and suffix-less Parquet targets and every `fixed_width` target now hold their declared format (fixed width is written by the engine's `write_fixed_width`; an `int` column accepts canonical integer text from a CSV source, and any other value fails with the engine's value-free message, exit 3). `--chunked` with a `fixed_width` target, or with a CSV target in a `.zip` or `.tar` archive, exits 1 before any table is written. `decoy unmask -o x.parquet` now writes Parquet, and `decoy detokenize -o x.pq` writes Parquet instead of CSV. For `decoy.mask(out=...)`, a new path whose suffix claims a format (`.csv`, `.parquet`, `.pq`) sets the target's format and drops its fixed-width `layout`; any other suffix keeps the declared format, so a fixed-width target redirected to `m.dat` now holds fixed width. `decoy validate` and `decoy ci check` report the format and suffix contradiction as an error (rule `target_format_suffix_mismatch`), matching `decoy run`. `decoy detokenize`, `decoy unmask` and `decoy report diff` read those files by their declared format (a file that is not the table's target is read by suffix, `.parquet` or `.pq` as Parquet); evidence manifests record each output's `format` and fixed-width `layout` (additive to `cli-local-1`; older manifests are read by suffix as before).
- **CSV sources honour `has_header`, `column_names` and `delimiter`.** `decoy run` (plain and `--chunked`), `decoy tokenize`, `decoy demo`, `decoy.mask()` (including a `data=` override) and the source read of `decoy report fidelity` and `report integrity` (when `--config` declares that file) read a declared CSV source through the engine's `read_csv_source`, so a headerless file with `column_names` or a tab or pipe file runs instead of failing with `'column_1'`. A headerless file whose rows do not match `column_names` (wrong field count, no data rows, a NUL byte, a lone CR, an unterminated quote) fails with the engine's `source_file.*` code in the message (exit 1); a plain run writes nothing, and so does a `--chunked` run that fails after its first chunk (see the atomic output entry). `decoy init file.tsv` declares `delimiter: "\t"`. Engine pinned to 0.19.0.
- **Hosted CI installs from `requirements-dev.lock`.** The `ci` pytest and ruff jobs, the PR fresh-install smoke, the release smoke and the diagram regen build their environment through one `lock-env` action (`scripts/dev/bootstrap.sh` on a pinned `uv`) instead of an unlocked `pip install`, which had resolved pydantic-core 2.50.4 against a lock that pins 2.50.2 and failed 91 tests on each Python. Clean-venv wheel installs pass `-c requirements-dev.lock`; the certified-profile job installs the engine and wheel with `--no-deps`, then its fingerprinted closure; the weekly release-smoke run keeps one registered unconstrained install to see dependency drift. `ci/install-policy.toml` is the registry and `tests/sentry/test_ci_lock_installs.py` the guard. `scripts/dev/lock_version.sh` now owns the engine spec, ruff pin, Python minors and key dependencies that `bootstrap.sh` and `lock.sh` used to read from `ci.yml`. `ci-template-lint` installs check-jsonschema from the hash-checked, wheel-only `ci/ci-tools.lock` and runs the pinned actionlint release binary after a sha256 check. The scanner's shell parsing is one vendored file, `tests/sentry/_ci_shell_tokens.py`. No CLI behavior change.
- **Engine repin to `decoy-engine==0.18.0` (R-b, `v0.18.0` / `f5b46a2c`).** The engine now checks a `file:` mask secret is owner-only on the descriptor it reads; a file whose mode widens after the CLI's own check is refused with the same `secret_file_permissions_unsafe` text (exit 1) on `run`, `run --chunked`, `tokenize`, `unmask`, `report vault` and `decoy.mask()`. Weighted categorical masking output moves by at most one CDF slot per threshold (engine's exact-integer CDF); no bundled template or example uses weighted categorical masking. `decoy ci` rule codes list one more literal engine code (`unreachable`, 15 total); the two new registry identities are admitted through the registry. `requirements-certified.txt` records fingerprint `b643894d...` for engine 0.18.0 (the 63 pins are unchanged). No CLI flag or verb changes.
- **Mask-secret refusals print fixed text chosen by their code** on `decoy run`, `decoy tokenize`, `decoy unmask` and `decoy report vault` (exit 1): `weak_mask_secret`, `missing_mask_secret`, `bad_secret_ref`, `secret_provider_unknown` and `secret_file_permissions_unsafe` (which says the file must be owner-only) each have one constant remedy, and the keyed refusal keeps each surface's own text (`decoy tokenize` now has its own). The engine's message is never printed. `decoy unmask` checks the secret code before its other error classes, and its CSV-read and runtime failures print the error type only (a parse error can quote a cell).
- **`decoy unmask` and `decoy report vault` take `--mask-secret REF`** (`env:NAME`, `file:/PATH`), the same flag `decoy run` has; it fills `global_settings.mask_secret_ref`, and setting both is a usage error (exit 1). `decoy run --vault` (and a `--chunked` multi-table run) reads the mask secret once and hands that one key to the vault writer and every table, instead of reading it again per engine call. A `vault://` ref now reaches the engine, which refuses it with `secret_provider_unknown` (the CLI registers no Vault provider). The `unmask` and `report vault` remedies and `decoy explain keys` name the flag and an owner-only `file:` recipe. There is still no implicit source: no auto-read variable, default key file or generated key.
- **`decoy run --chunked --vault` is refused (exit 1) before any work.** A chunked run writes each output chunk before the vault that re-identifies it exists, and the engine refuses a chunked entry with a vault writer. The CLI now stops first with one fixed message naming both flags; no output, no vault and no secret read. Run without `--chunked` to write a vault.
- **Engine repin to `decoy-engine==0.17.0` (R-a, `v0.17.0` / `1132d29e`), crossing 0.16.0.** Every engine call uses the new names: `run_storm` -> `profile_columns`, `decoy_engine.storm.postmask.run_storm_post_mask` -> `decoy_engine.verification.postmask.run_post_mask` (report schema `post-scan-integrity/v2`), `decoy_engine.storm.ner` -> `decoy_engine.detection.ner`. Generated and bundled pipelines (`decoy init`, `decoy demo`, `report integrity`, the five templates, `examples/`) declare `version: 2`, which the engine now requires. The native eligibility hint declines `post_scan: {integrity: true}` (was `run_storm`). The local token vault's `put` returns the stored token (engine 0.16.0 `TokenVaultWriter` contract). `decoy explain keys` states that a keyed strategy with no mask secret is rejected (`keyed_strategy_requires_secret`); the pre-GA `job_seed` fallback is gone. `requirements-certified.txt` records fingerprint `a7b40d54...` for engine 0.17.0. CLI verbs are not renamed.
- **A keyed pipeline with no mask secret now gets a CLI remedy, not the engine's.** `decoy run` (plain and `--chunked`) prints one fixed `keyed_strategy_requires_secret` message naming `--mask-secret env:NAME|file:/PATH` and `global_settings.mask_secret_ref` (exit 1); `decoy unmask` names `global_settings.mask_secret_ref` and now exits 1 instead of 3 for every mask-secret error (`missing_mask_secret`, `weak_mask_secret`, the keyed refusal), matching `run` and `tokenize`; `decoy.mask()` raises its documented `MaskSecretConfigError` naming `mask_secret=`. The gdpr, hipaa and pci templates, `decoy init` scaffolds of keyed files, the init next steps, `decoy explain keys`, `decoy explain vault` and `decoy unmask --help` say a secret is required and how to supply one; none still says the seed is the key.
- **`decoy report vault` opens the vault with the mask secret, not the seed.** It admits `global_settings.mask_secret_ref` through the engine's `secret_providers.admit_mask_key` (the path `decoy unmask` reaches) and refuses with a fixed `keyed_strategy_requires_secret` message when no secret is set; the `job_seed` key path is gone. Missing, wrong or malformed secrets exit 1. There is no `--mask-secret` flag on `unmask` or `report vault`.
- **`decoy ci` rule codes: the engine half of the allowlist is derived from the engine's reason registry** (`decoy_engine.reasons.manifest()`, SARIF-safe tokens only) on first use, plus 14 literal codes the engine raises outside the registry, instead of a hand-written list. The pydantic, CLI-gate, evidence and templated sets are unchanged.

### Added

- **Resource settings: `decoy run --max-memory` and `--threads`, `DECOY_MAX_MEMORY` and `DECOY_THREADS`, `decoy setup`, and `settings.json` (RUN-STREAM C3).** Each key resolves on its own: flag, then environment variable, then `$DECOY_HOME/settings.json`, then `auto`. `auto` threads is the engine's cgroup-aware usable CPU count, and `auto` memory is the engine's conservative out-of-core budget (25% of the memory ceiling, passed as explicit bytes), so two automatic runs on one host do not both claim most of it. The values reach the native and out-of-core routes; `--chunked` ignores them until it moves to the shared path. `decoy setup` (`--yes` accepts the detected values, `--json` for a result) writes the file atomically with mode 0600, keeps every other section and key already in it, and replaces a file it cannot read. The file is a JSON object with `schema_version` `"1.0"`; unknown minors and keys are accepted, and an unknown major, a duplicate key, a boolean or text where a number belongs, or NaN is refused with a value-free message (exit 1). `decoy doctor` lists the resolved memory and threads with their source and warns when the file is group or world writable. The `decoy run --json` payload gains `resources` with `max_memory_bytes`, `max_memory_source`, `threads` and `threads_source`.

- **CycloneDX SBOM generator (R1-c).** `scripts/release/sbom.sh` writes a reproducible CycloneDX 1.6 SBOM of the certified runtime pins (`requirements-certified.txt`) with the tool environment pinned, hash-enforced and wheel-only from `scripts/release/sbom-tool-requirements.txt`, run isolated (`python -I`, `uv --no-config`, no ambient `UV_*` settings, CPython 3.12 only); no timestamp or serial; well-formed public pins only, one per package, with the generated components checked against the pins. Not signed or published. Docs: `docs/release/sbom.md`.

### Fixed

- **Report and scan output a first-time user misread (CLI-QA1 C4).** `decoy report fidelity` in its default report mode no longer prints PASS: it prints `REPORT ONLY (no threshold violations)` or `REPORT ONLY: N threshold violation(s) not enforced (use --mode fail)`, including violations from strategy defaults with no flags set; warn and fail modes, the JSON `verdict` and every exit code are unchanged. `decoy report integrity` human output lists each residual-PII finding (table, column, detector, severity, configured strategy and the engine's fixed message, no cell values) under the bucket summary. `decoy scan` prints the reid risk as `N / 100 (k=K)` (`k=n/a` when k is unknown) and `decoy scan diff` prints its delta in points. `decoy ci check` with an unreadable or missing manifest prints one stderr line naming the path as given and `decoy ci --help`; stdout stays the same `decoy-ci-report/v1` document and `--quiet` prints nothing.

- **User text a first-time user reads (CLI-QA1 C2a).** A usage error or `--help` after a positional on `decoy scan` and `decoy validate` reads `decoy scan [OPTIONS] SOURCE` (and `decoy validate [OPTIONS] CONFIG`), no longer naming the hidden default command. `decoy explain pipeline` gives `version 2`, the version the engine accepts. The `decoy list disguises` tip no longer offers `decoy init --preset <id>` for disguise ids `init` rejects; it names `decoy list templates` and `decoy explain disguises`. `decoy explain tokenize` says the token vault is a plaintext SQLite file created 0600, and `decoy explain vault` says it is a different store. Internal ticket ids, a platform docs path and a private engine module path are gone from the explain topics, the `init` help and scaffold header, and the minimal, generate and hipaa templates.

### Security

- **Installer / update-system hardening (B-2 r7).** The signed version document now
  carries a monotonic `serial` and an `expires` deadline (TUF-style freshness);
  `decoy upgrade` and `install.sh` refuse an expired document, and refuse a `serial`
  lower than the highest accepted (kept in `$DECOY_HOME/trust_state.json`), so a
  replayed signed document can no longer freeze or downgrade a client. A pin below the
  signed `min_supported` is refused. Archive extraction validates hardlink names as
  archive-root paths, rejects members written through earlier symlinks, and refuses to
  extract at all when the stdlib `data` filter is unavailable (no unfiltered fallback).
  `DECOY_RELEASE_PUBKEY_FILE` now only replaces the trust anchor while the build still
  carries the placeholder key (loud warning); it is ignored, with a warning, in a release
  build. `make_version_document` gains `--serial` / `--valid-days`.

### Added

- **`decoy ci check` (F43: CI checks, SARIF, pre-commit, portable manifest).** A thin,
  local, network-free wrapper over the existing contracts. A committed `decoy-ci/v1`
  manifest (`docs/schemas/decoy-ci-v1.schema.json`, example `examples/decoy-ci.yaml`)
  selects full or config-only validation, saved-scan drift, evidence verification, and an
  optional bounded scan of STAGED files for exact customer literals. One value-free
  report is emitted as `decoy-ci-report/v1` JSON, SARIF 2.1.0 (validated against the
  OASIS schema; exact YAML line/column for validation findings, rules, and
  `partialFingerprints`), or Markdown. Exit integers are the existing taxonomy
  (precedence 5 > 3 > 1 > 4 > 2 > 0); no integer is added and direct commands keep their
  behavior. Ships `.pre-commit-hooks.yaml` (`decoy-ci-check`, offline, needs pre-commit
  >= 4.4.0 and a pre-installed `decoy`) and invoker-only GitHub Actions / GitLab CI
  templates under `integrations/`. Contract: `docs/ci-contracts.md`. Deferred, by design:
  the F12 regression runner (a non-empty `regression_suites` is refused, never skipped),
  F18 includes, a packaged Marketplace action, platform export, and any upload or comment
  behavior (uploads are your CI workflow's opt-in step).
- `pydantic>=2,<3` is now a direct dependency; `jsonschema` and `pre-commit` join the `dev`
  extra (test oracles only).

- **`decoy tokenize` / `decoy detokenize` (reversible tokenization, B-1).** A
  local, single-operator tokenization pair over the engine's keyed token-vault
  seam (A-8). `decoy tokenize pipeline.yaml --vault tokens.db` runs a masking
  job whose `strategy: tokenize` columns are replaced by deterministic
  surrogates; the engine derives each token (keyed, HKDF-SHA256) and the CLI
  persists the `(namespace, plaintext) -> token` mapping in a local SQLite
  vault. `decoy detokenize pipeline.yaml tokenized.csv --vault tokens.db`
  reverses it from that vault. Tokens are deterministic (same plaintext +
  namespace -> same token; the vault is authoritative), and the same plaintext
  under two namespaces gets two distinct tokens. There is NO auth model (local
  tool; the multi-user de-tokenize authorization is the platform's job).
  `--mask-secret env:NAME|file:/PATH` keys the tokens from a secret instead of
  the pipeline seed. Fail-closed: a missing vault, a non-vault file, or a token
  absent under the column's namespace writes no output. See
  `decoy explain tokenize`. Requires the engine's A-8 token-vault seam, which
  the existing `decoy-engine>=0.7.0` floor already carries (the seam is present
  in engine `main`), so no engine-pin change rides with it.
- **Self-hosted signed distribution + `decoy upgrade` (CLI-LAUNCH).** The CLI now
  ships as a signed, self-contained, per-platform bundle served from Decoy (a
  bundled standalone CPython + the matched engine/native/CLI wheels + a `decoy`
  launcher on PATH), not public PyPI. `install.sh` / `install.ps1` verify the hosted
  version document's Ed25519 signature, the bundle's SHA-256 checksum, and the
  bundle's Ed25519 signature before laying anything down, and run a native-companion
  self-check that refuses loudly (never a silent slow pandas path) if the companion is
  missing or ABI-mismatched. `decoy upgrade` re-runs the verified install, swaps the
  managed runtime atomically, and keeps the previous version for rollback. An
  interactive, opt-out, fail-silent startup notice reports a newer version
  (`--no-update-check` / `DECOY_NO_UPDATE_CHECK`). Verify side ships in
  `decoy.distribution`; the build pipeline + install scripts live in `packaging_tools/`
  (build host only). Signing reuses the in-repo Ed25519 signed-envelope pattern. The
  managed runtime runs with bytecode writing off and the bundle manifest rejects any
  on-disk `__pycache__`/`.pyc`, so a forged cache can never execute past verification.
  Launch targets: `linux-x86_64`, `linux-aarch64`, `macos-arm64`; `windows-x86_64` is
  gated off the advertised matrix until its lifecycle is verified end to end (see
  `docs/distribution/decisions/2026-10-26-windows-target-gated.md`). See `docs/install.md`
  and `docs/distribution/`.
- **`decoy run --duckdb-source TABLE=DB_PATH`.** Read a pipeline input table from
  a DuckDB database file instead of a CSV/Parquet/fixed-width file. Repeatable;
  the named relation is acquired read-only (the database is never written) to a
  temporary Parquet, which is masked on the normal parquet path, so native-on and
  `--chunked` apply unchanged. No raw SQL (the relation name is the handle); no
  new engine source format. Not supported with `--evidence-out` yet.

### Removed (`--substrate` / `DECOY_SUBSTRATE`, 2026-10-31) -- BREAKING, pre-GA

- **`decoy run --substrate` and the `DECOY_SUBSTRATE` env var are gone, and
  `decoy.mask()` no longer takes `substrate=`.** The pinned engine (0.15.1) ships
  one execution adapter and deleted `resolve_substrate` and `run_pipeline`'s
  `substrate` parameter; every `--chunked` run (and every `mask()` call that
  passed `substrate=`) failed on the import. The flag had no remaining effect:
  `pandas` was the only accepted value and plain runs ignored it. A run that still
  passes `--substrate` now exits with Typer's usage error (exit 2, "No such
  option"); `DECOY_SUBSTRATE` is no longer read. `decoy explain substrate` stays
  and says so. The chunked route label is the fixed `pandas chunked stream`.
- **Engine import-surface sentry.** `tests/sentry/test_engine_import_surface.py`
  derives, by AST, every `decoy_engine` name the CLI imports and every keyword it
  passes to `run_pipeline` (including those reaching it through a `**kwargs`
  dict), and resolves each against the installed engine. It fails closed on a
  missing name and on any keyword set it cannot derive statically, so engine API
  drift is caught at test time instead of at the first user's `--chunked` run.

### Changed (CLI command-surface redesign, 2026-10-23) -- BREAKING, pre-GA

The `decoy` command surface was redesigned from ~17 top-level commands plus 11
sub-apps into one coherent, discoverable set. Pre-GA hard delete: there are no
migration shims. Highlights:

- **One `run`.** Masking, generation, and mixed jobs all run through `decoy
  run <config>`; the mode is inferred from the config.
- **One pre-run gate, `validate`.** `plan`, `compile`, `preflight`, and the old
  `validate config` folded into `decoy validate <config>`, which compiles,
  preflights, and reports the plan. `--fail-on-warning` returns exit code 2
  (`EXIT_WARNINGS`).
- **`scan` replaces `storm`/`profile`/`fit`** as the one "look at my data" verb.
- **One reference vocabulary, `list` / `show`.** `decoy list <kind>` and `decoy
  show <kind> [name]` replace the per-registry sub-apps (strategies, providers,
  templates, validators).
- **One post-run noun, `report`.** `evidence`, the old `report` verbs, `validate
  distribution`, and `storm integrity` folded into `report`
  (`summarize`/`diff`/`integrity`/`verify`/`show`/`fidelity`/`vault`). The CLI is
  now stateless and file-first: `project`, `catalog`, and `jobs` are removed; a
  `report` verb takes manifest/output file paths, not catalog run-ids.
- **`vault info` moved to `report vault`.**
- **`run` capability flags.** `--explain-plan`, `--fidelity`, and
  `--post-validate` surface the report-shaped engine results `run` already
  computes. All default off; the default hot path is unchanged.
- **One flag vocabulary.** `--out` renamed to `--output`/`-o` everywhere; a
  uniform `--json` (stable machine envelope) / `--quiet,-q` / `--verbose,-v`
  trio on every command; `plan`'s former off-meaning `--json` removed.
- **Deletions.** `storm test`, the deprecated `storm scan` alias, `jobs watch`,
  and the `forge` compatibility shim (and its exit code) are gone. The exit-code
  contract is the six documented codes (0/1/2/3/4/5).
- **Anti-drift.** The README "Common commands" table and root help are generated
  from `docs/cli-reference.md`; a sentry fails if the three surfaces diverge.

`decoy query` (read-only SQL over masked Parquet output) is NOT in this release:
its pre-merge security review found two defects in the engine's
`run_discovery_sql` validator (a stacked-write bypass and arbitrary file read).
It returns once the engine validator is hardened and released.

### Fixed (CLI redesign hardening, 2026-10-23)

- **`scan --output -` no longer leaks when combined with `--json` or
  `--quiet`.** Streaming the rich profile to stdout conflicts with the JSON
  envelope and with quiet suppression (both carry raw values), so the
  combination is now rejected up front with a usage error instead of streaming.
- **`report diff` degrades instead of crashing on a corrupt output file.** A
  present-but-unreadable CSV/Parquet is now treated like a missing file
  (manifest-level still reported, data level skipped, `--require-data` still
  hard-fails), rather than raising out of the command. The raw parser message is
  not surfaced.
- **The surface drift sentry now guards the hidden default-command handlers.**
  `scan` and `validate` dispatch a bare positional to a hidden handler whose
  flags no other sentry watched; their option surface is now pinned (every
  spelling, aliases included) so a flag change there is a reviewed edit.
- **A YAML parse error no longer echoes the offending config line.** PyYAML's
  error text quotes the line it failed on, so a malformed config whose broken
  line held a secret leaked that secret into the message. Every command that
  parses a config (`run`, `validate`, `validate config`, `validate preflight`,
  `compile`, `subset`, `unmask`, `report fidelity`/`integrity`) now reports a
  sanitized message with only the line/column and a fixed classification. A new
  sentry asserts a secret-bearing malformed config never appears in any output
  stream.

### Fixed (CLI reads sources by declared format, 2026-09-30)

- **Sources are read by their declared `format`, not by file suffix.** A
  `format: fixed_width` source (with its `layout`) now reads typed columns
  through the engine's public `read_fixed_width`, matching the platform.
  Before, it was parsed as CSV. A Parquet file named `.pq` (or with no
  extension) and a CSV named `.dat` now read correctly in plain and
  `--chunked` runs. `decoy run --chunked` refuses `fixed_width` sources up
  front (usage error, nothing written) because the engine has no streaming
  fixed-width reader.
- **Native eligibility follows the declared format.** CSV and fixed-width
  jobs are now native-eligible (and fail closed on a broken companion) the
  same way Parquet jobs are.
- **Engine floor raised to `decoy-engine>=0.7.0`**, the first release that
  exports `read_fixed_width`. Installs and CI need that engine release.

### Added (Phase 3.1: CLI native packaging default-on-when-present, 2026-09-26)

- **`decoy run --native` / `--no-native`.** A non-chunked, mask-only run
  already prefers the compiled `decoy-engine-native` kernel over the pandas
  adapter whenever the companion is installed and the job is eligible
  (single non-FK Parquet table, using passthrough/redact/truncate and/or
  hash/categorical/bucket_perturb/group_key) -- no flag needed. `--native`
  now requires it: it refuses before any run on
  `--chunked` or a generate/mixed config, refuses before any run on an
  absent/broken companion, and refuses AFTER the run (writing nothing) if
  the job finished without positive compiled-kernel evidence.
  `--no-native` forces the legacy pandas adapter, the documented rollback.
  `decoy.mask(native=...)` mirrors this exactly, through the same shared
  gate (`decoy._native_gate`), so the library cannot silently write a
  result the CLI would refuse.
- **A present-but-broken companion now fails closed by default.** Before,
  an `abi-mismatch` / `kat-corrupt` / `load-error` companion silently
  declined admission and ran pandas with no signal. `decoy run` (and
  `decoy.mask()`) now refuse with the classified reason and a remediation
  hint instead; `--no-native` downgrades that to a warned fallback.
  `status.cause` is never shown; a companion's own `abi_version()` string
  is sanitized (length-capped, printable-only, and a non-string value
  shows a fixed marker instead of crashing) before display.
- **Three-state route indicator.** The run summary and `--json` record now
  report `native_route`: `native (compiled kernel)`, `unified slice (no
  compiled kernel)` (a passthrough/redact/truncate-only job activating the
  unified slice without the companion -- never mislabeled "pandas"), or
  `pandas (legacy adapter)`, scoped to whether the run was even a
  unified-slice candidate. A `--chunked` run reports its resolved
  substrate; a generate/mixed run reports the engine's own
  `execution_mode`, or a neutral "not a unified-slice candidate" label.
- **`decoy info` / `decoy preflight` companion visibility.** `decoy info`
  reports companion presence, reason, expected/actual ABI, and version
  (JSON and human). `decoy preflight` adds a companion-health check
  (pass/warn) plus a native-eligibility line computed from config shape
  alone, explicitly labeled a static possibility, not a guarantee of the
  resolved route.
- **`decoy explain native`.** New topic covering the native lane, the two
  flags, and the fail-closed default. No `native` extra and no published
  install artifact exist yet (no paired PyPI release of the companion), so
  the topic says exactly that rather than pointing at an install command
  that would fail today; everything else already works against a
  companion installed by other means.
- **Known, accepted gap: companion-health gating is all-or-nothing, not
  per-kernel.** The engine can run hash/categorical/bucket_perturb natively
  even when only the additive raw-hex kernel is missing (`native_kernel_
  availability()`), but that per-kernel breakdown is not part of the
  engine's public surface (only the blanket `native_companion_status()` is)
  -- and the plan is explicit that this CLI reuses the engine's probe
  rather than reimplementing companion detection. This module therefore
  treats a partially-capable companion as fully broken, which is the safe
  direction (over-conservative, never a false native claim) but can
  occasionally fail closed a job the engine would have run natively.
- **Graceful degradation on an older `decoy-engine`.** `decoy run`,
  `decoy.mask()`, `decoy info`, and `decoy preflight` all detect whether
  the installed engine actually has `native_companion_status()` before
  calling it, and never pass `unified_slice_enabled=True` explicitly (only
  `False`, for `--no-native`) -- an engine that predates this Phase 3.1
  work keeps running a plain `decoy run` instead of crashing.

### Changed (OOM checker recalibration: build-floor refusal is now advisory, capacity refusal is fan-in-only, 2026-09-08)

- **`FIT` no longer means "clears the budget."** The engine's OOM checker
  paired with this release (`fix/ooc-preflight-overreject-recalibration`)
  redefines its public `CapacityVerdict.FIT` to mean "no hard impossibility
  detected." The measured completion-cap data showed the old flat
  build-floor refusal was over-rejecting jobs that would have completed;
  that refusal is now a WARNING with a recommended host size, not a job
  refusal. The only capacity refusal left is fan-in (co-live DuckDB
  instances that cannot fit even a 1 MB `memory_limit` under the budget) --
  see the updated `EXIT_CAPACITY` doc comment in `exit_codes.py`.
- **`decoy preflight` renders the advisory as a warning, not a green pass.**
  When the engine estimate reports `FIT` with `warned=True`, preflight now
  emits a `capacity.out_of_core_fk` finding with `status: "warn"` (both
  human and `--json` output) instead of folding it into a silent pass --
  `--fail-on-warning` governs whether that alone exits nonzero; default
  execution still proceeds. A fan-in impossibility discovered while the
  engine resolves its memory budget (previously mis-rendered, if at all) now
  reliably surfaces as a `capacity.out_of_core_fk` FAIL and exits
  `EXIT_CAPACITY`, matching `decoy run`'s behavior for the same case.
- **Legacy-engine compat kept.** `out_of_core_insufficient_memory` (the old
  build-floor hard-fail code) stays recognized by `decoy run`'s capacity
  matcher for an older, not-yet-recalibrated engine; a current engine never
  raises it.

### Added (OOM checker v1: labeled capacity refusal in `decoy run` + a pre-run capacity check in `decoy preflight`, 2026-07-24)

- **New exit code `EXIT_CAPACITY = 5`.** The engine's out-of-core-FK
  memory gate has always refused a job it predicts will not fit; the CLI
  used to fold that refusal into the generic `EXIT_RUNTIME` path, printed
  as a bare `error:` line with no distinct signal a script could switch
  on. `decoy run` now matches the engine's two capacity-refusal codes
  (`out_of_core_insufficient_memory`, `out_of_core_fanin_exceeds_budget`)
  narrowly, prints a `capacity:`-labeled line, and exits `EXIT_CAPACITY`;
  `--json` adds `error_kind: "capacity"` and `code` to the existing error
  envelope (`command`/`config`/`mode`/`error` are unchanged). Any other
  `ExecutionError`, and any config error, keep their existing exit codes.
- **`decoy preflight` predicts the same refusal before a run starts.** A
  new capacity section calls the engine's `estimate_job_capacity` (added
  this cycle) against the SAME evaluator the mid-run gate uses, so the two
  can't drift apart. Renders one of four states -- `capacity: OK`,
  `capacity: INSUFFICIENT` (exits `EXIT_CAPACITY`, not the generic
  usage-error path), `capacity: not checked` (RAM undetectable, an
  unpriceable CSV row count, or an engine too old to have the estimator),
  `capacity: not applicable` (this job would not take the out-of-core-FK
  route) -- without running the pipeline. `--json` carries a structured
  `capacity` block plus a `code` field on the matching `checks` entry, so
  scripts never need to parse the message text.
- **Honest scope, stated up front (v1):** this checks ONE gate, the
  out-of-core-FK route's resident-memory floor. `decoy run` fully loads
  every source into memory before it calls the engine at all, so an
  ingestion `MemoryError` or an OS OOM-kill happens before this gate ever
  runs, and neither command's capacity check covers that or the generate
  path. `decoy explain exit-codes` and both commands' help text say so.
- The engine floor stays `decoy-engine>=0.5.0`; an older, already-installed
  engine without `estimate_job_capacity` degrades `decoy preflight`'s
  capacity section to `not checked` rather than failing.

### Fixed (`decoy unmask` console summary is now a complete census, 2026-07-15)

- **`decoy unmask`'s human-readable summary (non-`--json`) now accounts for
  every column, so its counts can no longer silently lie.** Previously the
  summary tallied only `reversed` / `irreversible` / `untouched` (plus
  `vault_reversed` when a `--vault` was passed), so three genuine per-column
  outcomes the engine emits vanished from the arithmetic entirely:
  - `reversed_unverified` -- an FPE column reversed under the non-secret
    `job_seed` fallback (no `mask_secret_ref` at mask time). A masked PAN that
    was in fact decrypted back to plaintext used to show as
    `"0 column(s) reversed, 3 irreversible, 0 untouched."` -- the column
    dropped out of every bucket and the "FPE is unauthenticated -- a wrong key
    yields plausible but WRONG plaintext" caveat never printed.
  - `vault_miss` -- a vaulted column the supplied vault could not reverse (the
    note printed but the count stayed at zero, so the totals did not add up).
  - `table_missing` -- other configured tables when a multi-table config is
    unmasked one file at a time; these were neither counted nor noted.

  The summary is now a complete census: the six present-column statuses
  (`reversed`, `reversed_unverified`, `vault_reversed`, `vault_miss`,
  `irreversible`, `untouched`) always sum to the number of real columns, each
  non-empty secondary bucket is surfaced (`, N reversed (unverified)`,
  `, N vault-reversed`, `, N vault-miss`), and absent tables are reported in
  their own clause (`, N configured table(s) not in this input`) rather than
  miscounted as columns. Every reversible/miss/absent status also prints its
  detail as a `note:`. `--json` output was already complete and is unchanged.

### Fixed (`decoy init` scaffold runnability + config exit codes, 2026-07-15)

- **`decoy init <file>` now scaffolds configs that actually run.** The
  column-aware scaffolder emits real `provider_config:` keys instead of a
  phantom `params:` block (which `ColumnConfig`'s `extra="forbid"` always
  rejected), AND now emits the `namespace:` field that `hash`, `fpe`, and
  `date_shift` require at runtime (`ColumnConfig.namespace` defaults to
  `None` with no compile-time check, so a missing namespace used to pass
  `decoy validate config` and only fail at `decoy run` with exit 3). `fpe`
  scaffolds for PAN/credit-card columns now also set
  `provider_config: {charset: digits, validate_luhn: true}` so masked PANs
  stay Luhn-valid, matching the bundled PCI template.
- **A malformed pipeline config now exits `EXIT_USAGE` (1), not
  `EXIT_RUNTIME` (3).** `decoy run` catches `PipelineConfig.model_validate`'s
  `ValidationError` narrowly at the validation call site and reclassifies it
  as a usage error -- the operator's YAML is wrong, not an engine crash.
- **A non-dict `global_settings` (e.g. a YAML list) is now rejected before
  schema validation**, with a redacted message, instead of reaching
  `PipelineConfig.model_validate` -- which would otherwise echo any value
  nested inside it (including a smuggled `mask_secret_ref`) via Pydantic's
  `input_value` diagnostics.

### Added (DE-02 keyed-masking CLI surface, 2026-07-15)

- **`decoy run --mask-secret <ref>`**: a first-class flag for keyed masking.
  It sets `global_settings.mask_secret_ref` for the run, feeding the engine's
  DE-02 KeyProvider (the `env:NAME` / `file:/PATH` reference to a >=32-byte
  secret) on both the plain and `--chunked` paths. Independent of
  `--master-key`, which stays generation-only -- the two are separate secrets
  and neither affects the other. Explicit flag only (deliberately no env var,
  since the ref it carries already indirects through the environment).
  Passing both `--mask-secret` and a YAML `mask_secret_ref`, or an empty /
  malformed ref, is a usage error (`EXIT_USAGE`), never a silent unkeyed run.
- **Engine floor raised to `decoy-engine>=0.4.0`** (DE-02's release marker) for
  the DE-02 keyprovider module. The floor now guarantees `decoy_engine.keyprovider`
  is present; a configured mask secret is additionally guarded at run time as
  defense-in-depth: if a broken or forced install lacks `decoy_engine.keyprovider`,
  `decoy run` refuses the run rather than let the engine silently emit UNKEYED
  output.

### Fixed (DE-02 keyed-masking CLI surface, 2026-07-15)

- A bad / missing / weak mask-secret reference (engine `MaskSecretError` and
  its subclasses) now exits `EXIT_USAGE` (the operator's config is wrong)
  instead of `EXIT_RUNTIME`.
- `decoy explain keys` documents `--mask-secret`, corrects the resolver owner
  (the ENGINE resolves the ref, not the CLI), clarifies that an unkeyed
  (job_seed) masking run is reproducible but NOT re-identification-safe
  (the job seed is public, not a confidentiality key), and notes the GA
  fail-closed behavior (a keyed strategy with no resolved secret is rejected
  at GA, per `decoy_engine.release.is_pre_ga()`).

### Added (Sprint 5 CLI closure, 2026-07-04)

- **`decoy validate distribution <source> <output>`**: recompute distribution
  fidelity between a pre-mask/pre-generate source CSV and its post-run output.
  A thin CLI surface over the engine's `compute_quality_report` +
  `apply_quality_policy` (no CLI-side metric). Flags: `--joint a,b`
  (repeatable), `--generate` (drops the row-parity expectation), `--config`
  (names each column's strategy so intentional loss is not flagged as
  accidental drift), `--policy` / `--mode` / `--min-grade` / `--min-score`,
  `--report-out`. A `fail` policy verdict exits `EXIT_FINDINGS` (4), matching
  `decoy storm integrity`'s data-audit exit-code contract.

- **`decoy run --notify <kind:target>`** (repeatable) + **`--notify-on
  {success,failure,always}`**: send a best-effort notification after a run
  reaches its terminal state. Channels: `webhook` (HMAC-signed when
  `DECOY_NOTIFY_WEBHOOK_SECRET` is set), `slack` (incoming webhook), `email`
  (`DECOY_NOTIFY_SMTP_HOST/_PORT/_USER/_PASS/_FROM`). Targets and secrets are
  flags/env only, never persisted to `.decoy/workspace.json`. A channel
  failure never changes the run's exit code. Payloads carry facts only
  (status, row count, config path, timings); the raw engine error is NEVER
  put on the wire (only the exception type name), so a failed run cannot
  egress source-row values to a third-party channel.

### Changed (Sprint 5 CLI closure, 2026-07-04)

- **`decoy validate` is now a command group**: `decoy validate <cfg>` becomes
  **`decoy validate config <cfg>`** (the config schema check is unchanged; it
  moved under the `config` subcommand so `distribution` can sit beside it).
  Pre-GA hard-delete break: no back-compat shim. Note: `validate config
  --fail-on-warning` exits `2` (its long-standing code) while `validate
  distribution --fail-on-warning` exits `EXIT_FINDINGS` (4); the two
  subcommands intentionally use different warning exit codes for their
  different domains (config well-formedness vs. data-fidelity findings).
### Fixed (#15, 2026-07-04)

- **HIPAA template disguise-version drift (under-masking regression)**:
  the bundled `hipaa` template's `mrn` column still used FPE
  `charset: alphanum` after the engine's HIPAA disguise widened it to
  `ALPHANUM` (2026-06-29, passthrough-leak fix: FPE's
  `preserve_separators` mode passes characters outside the configured
  charset through unchanged, so lowercase-only `alphanum` let uppercase
  letters in institution-specific MRN formats, e.g. `MRN12345A`, leak
  in the clear). The template was never re-derived against the new
  disguise version, so the CLI's default HIPAA scaffold shipped the
  same under-masking defect. Fixed by widening the template's `mrn`
  charset to `ALPHANUM` and bumping its `x-derived-from-disguise`
  pin to `hipaa@2026-06-29`. The `test_template_disguise_drift.py`
  guard (`test_pinned_version_matches_live_disguise` +
  `test_every_mapped_column_matches_its_disguise_rule`) now passes.

### Added (SP-16 CLI foundation, 2026-06-28)

- **`decoy validate config --fail-on-warning`**: exits non-zero (code 2) when
  any advisory warning fires. Enables CI gates that treat warnings as blocking.
  Current warnings: output target file already exists (overwrite advisory).

- **`decoy validate config --json` multi-message output**: the JSON envelope
  now includes a `messages` list with ALL validation messages
  (`severity`/`code`/`message`/`location`), not just the first error string.
  Pydantic `ValidationError` with multiple field failures now surfaces all of
  them at once. Backward-compatible: the top-level `error` string key is
  preserved for error responses.

- **`decoy storm analyze --format parquet|fixed-width|delimited`**: explicit
  format selector for the STORM analyzer. Format is also inferred from file
  extension (`.parquet`/`.pq` -> parquet; `.fwf`/`.dat`/`.fixed`/`.fw` ->
  fixed-width; everything else -> delimited/CSV).

- **`decoy storm analyze` Parquet support**: `.parquet` files are now read via
  `pd.read_parquet` (pyarrow is a core engine dependency). Sampling
  strategies (`--rows`, `--strategy`) apply after load.

- **`decoy storm analyze --layout <layout.yaml>`**: fixed-width input support
  behind an explicit layout spec (column name + start offset + width). Layout
  can be YAML or JSON. Fixed-width without `--layout` fails closed with a
  clear, actionable error -- column boundaries are ambiguous without a spec.

### Added (capability gaps, 2026-06-12)

- **`decoy run --chunked [--chunk-size N]`** (streaming). Streams each
  mask table's CSV source through the engine chunk-by-chunk (default
  100k rows) for inputs too large for memory; output is byte-identical
  to a plain run. Only value-keyed strategies qualify (hash, fpe,
  redact, truncate, text_redact, date_shift, bucketize); anything else
  exits 1 with the engine's typed rejection before any rows process.
  CSV sources only in v1.

- **`decoy fit` verb** (statistical synthesis). Fits a
  distribution-snapshot/v1 artifact from a source CSV
  (`--parse-dates` for datetime columns, repeatable `--joint a,b` for
  the contingency tables `condition_on` needs). The snapshot is what
  `type: statistical` generate columns reference via `snapshot_file`;
  `decoy validate config` now rejects configs whose snapshot artifact is
  missing or incompatible (engine check row 12).

- **`decoy unmask` verb** (detokenization). Recovers `strategy: fpe`
  columns from a masked CSV using the same pipeline config the mask run
  used; the config's seed + per-column namespace re-derive the Feistel
  key (engine SEED_PROTOCOL_VERSION 5, single key per seed+namespace).
  One-way strategies (hash, redact, faker, ...) pass through unchanged
  with an `irreversible` entry in the per-column report (`--json` for
  the structured form). SECURITY: the config now functions as the
  decryption key for its fpe columns; handle accordingly.

### Fixed (audit remediation, 2026-06-12)

Findings from the 2026-06-11 full-codebase audit.

- **hipaa/pci/gdpr templates rewritten and no longer dead-on-arrival**
  (audit H5 + H12). All three crashed at `decoy run` on any input
  (faker on the non-poolable uuid provider). Templates are now derived
  from the engine's dated disguises and carry an
  `x-derived-from-disguise: <id>@<version>` marker enforced by a
  drift-guard test: hipaa upgrades ssn/mrn/account/vehicle to
  format-preserving encryption and dates to keyed date_shift (joins and
  intervals survive); pci PANs are FPE'd with Luhn-valid output and
  transaction ids hash-pseudonymised; gdpr device ids
  hash-pseudonymised per Art 4(5). A new E2E net runs EVERY bundled
  template against synthesized data on every CI run.
- **`decoy validate config` now runs the engine's config-only plan checks**
  (audit H5): unknown providers, non-poolable faker providers, and
  missing deterministic namespaces fail validate with the typed code
  instead of passing schema-only and crashing at run.
- **Typed exit codes** (audit H10): engine config errors
  (PlanCompileError / PipelineValidationError / ConfigError) exit
  EXIT_USAGE(1) per the documented contract; runtime crashes stay
  EXIT_RUNTIME(3).
- **Mixed mask+generate configs rejected** (audit H11): previously they
  exited 0 while silently writing no output for the generate tables.
- **`storm integrity` exit 4 is reachable** (engine audit C1/H6): a
  masked file identical to its source now fails with a residual_pii
  'fail'; E2E locks both directions.
- **Config parsed once per `decoy run`** (audit L3; was up to 4 parses).
- **ruff clean** (audit L4: 13 errors cleared, zero-error gate).

### Added

- OSS.3 packaging metadata: PyPI Trove classifiers, keywords, project
  URLs, and the distribution rename to `decoy-cli` (per Q-OSS-1 RESOLVED
  2026-06-01). The import package + console script + the `decoy-engine`
  dependency are unchanged.
- This `CHANGELOG.md` itself, plus the `docs/release/versioning.md`
  semver policy doc.
- **Generated CLI reference** (`docs/cli-reference.md`, produced by
  `python -m typer decoy.__main__ utils docs`). A
  `tests/unit/test_cli_surface.py` drift guard fails CI when the command or
  flag surface changes without the reference being regenerated.

### Changed

- Help-text accuracy pass: root and `storm test` help no longer reference the
  old `storm scan` verb (now `storm analyze`); the `templates` help example no
  longer shows the removed `graph` template; `explain modes` help no longer
  lists the removed `convert`/`graph` modes; `explain transforms` notes the full
  12-strategy set instead of claiming "eight"; `CODEMAP.md` drops the removed
  `forecast` command / `forecast.py`.
- PyPI distribution name: `decoy` -> `decoy-cli` (Q-OSS-1). Existing
  `pip install decoy` continues to work today (the bare name is still
  reserved, just not pursued as a launch-blocker); future installs
  should use `pip install decoy-cli`.

## [0.1.0] - 2026-06-02

The first publishable cut of the CLI. Not yet pushed to the real PyPI
index; first publish lands with OSS.7.

### Added

- OSS.1 release gate: `.github/workflows/release-smoke.yml` builds the
  wheel + installs into a clean Python 3.10 / 3.11 / 3.12 venv + runs
  `decoy --version`, `decoy demo --json`, and the canonical `decoy run`
  cell against the bundled minimal template. Manual runbook lives at
  `docs/release/fresh-install-smoke.md`.
- Centralized exit-code contract: `decoy.cli.exit_codes` exports
  `EXIT_OK` (0), `EXIT_USAGE` (1), `EXIT_DEPRECATED_SHIM` (2), and
  `EXIT_RUNTIME` (3). Integer values stable across releases; full table
  at `decoy explain exit-codes`.
- V2-shape bundled examples (`examples/mask_example.yaml` +
  `examples/generate_example.yaml`) with a parametrized validation gate.
- CLI.1-4: rewired `decoy --help`, `decoy run`, `decoy demo`,
  `decoy validate`, `decoy plan` against the V2 engine spine
  (`PipelineConfig.model_validate` -> `compile_plan` ->
  `select_execution_adapter`). Pre-CLI.1 the entire CLI raised
  ImportError at module load against the post-S22 engine.
- FC-1 schema alignment: the top-level `mode:` field is gone (engine
  FC-1 dropped it); `decoy run --mode mask|generate` flag is still
  accepted as a hint, but the actual mode is inferred per-table from
  `columns` (mask) vs `generate_columns` (generate) presence. Bundled
  templates + examples + the demo's emitter all updated.

### Fixed (from QA review docs/qa/review-2026-06-02-cli-v2-migration.md)

- F2: stale `FORECAST` mention in `demo.py` module docstring (the
  legacy recommender was retired under storm-reframe-C).
- F3: `plan.py::_empty_profile_for_no_profile` now uses POSIX epoch as
  a "no real profile" sentinel instead of a hardcoded slice date.
- F5: orphan V1-shape YAML builders in `demo.py` carry per-function
  `# V1 SHAPE -- replace with V2 PipelineConfig before wiring to --ref`
  warnings + a top-of-block fence comment.
- F6: `demo.py::_build_pipeline_yaml` builds a dict and serializes via
  `yaml.safe_dump` instead of f-string templating; a path with a single
  quote (e.g. `--dir "O'Hare_demo"`) no longer crashes.
- F7: `decoy run` + `decoy demo` no longer swallow inner `typer.Exit`
  into the EXIT_RUNTIME catch-all.
- F8: JSON error envelopes truncate engine exception messages at 500
  chars to bound log growth + reduce PII risk.
- F9: `decoy validate` reports "Pipeline YAML is empty." on an empty
  file instead of the unhelpful "must be a YAML mapping, not
  NoneType."
- F10: bare `assert` in `plan.py` replaced with `RuntimeError` so the
  invariant cannot be stripped by `python -O`.
- F11: deleted unused `import os` in `run.py`.
- F12: added "See also:" blocks to `decoy plan --help` and
  `decoy replan --help` epilogs.
- F13: `decoy explain pipeline` topic body leads with the V2 shape;
  the V1 shape is demoted to a "Legacy V1 shape (REJECTED by
  `decoy validate`)" footnote.
- F14: deleted no-op `run.__doc__ = run.__doc__` self-assignment.

### Deferred

- F1 (~150 LOC dispatch dedup between `run.py` and `demo.py`): real
  refactor; should land alongside an `_dispatch.py` extraction.
- F4 (run.py triple YAML read on hot path): real refactor; threads
  the parsed raw dict through `_detect_mode` + `_detect_key_label` +
  the spinner body.

Tracked in `decoy/PLAN.md` so they do not rot.

[Unreleased]: https://github.com/louiskeep/decoy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/louiskeep/decoy/releases/tag/v0.1.0
