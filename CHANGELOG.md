# Changelog

All notable changes to the `decoy` CLI land here. The CLI ships as a signed
bundle (the `decoy` import package, the `decoy` console script and the pinned
engine), not from PyPI.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
version numbers follow the [versioning policy](docs/release/versioning.md).

## [Unreleased]

### Added

- **`decoy run --sample N` and `--sample-root TABLE`, hidden until the sample run lands (SAMPLE SC1).** The options check their input and refuse unsafe combinations (eight flags, a bad root table, a generated parent above a masked child) before anything is read. A sample run writes only into a staged scratch folder that is deleted on failure, and refuses unsafe output names before it writes. A request that passes every check stops with `--sample is not available yet` until SC2.

### Changed

- **`decoy report fidelity` marks columns masked by a value-replacing strategy as intended (row 24e, DI close C1).** A correct `hash`, `faker` or `redact` masking no longer fails `--mode fail` for a low score on those columns. The table shows `intended` beside the score, a `--joint` pair that names such a column prints `intended` in place of its score and does not count against a pairwise minimum, and one note line explains it. Intended columns still count in the grade and the overall score, so `--min-grade` can still fail. An explicit threshold for a column or strategy still applies.

- **`decoy report integrity` shows how much of each column still matches the source.** The residual-PII table gains a "Same as source" column (`-` when the engine has no rate), and without `--config` the text no longer says a column was "not configured to be masked".

- **A relationship between two generate tables needs no `namespace`.** `decoy validate` and `decoy run` accept it. The output is the same as for the same pipeline without the `relationships:` block. A relationship with a masked table on either side still needs a namespace.

- **Engine repin to `decoy-engine==0.28.2` (`v0.28.2`).** The pin moves from 0.28.1; `requirements-certified.txt` keeps its 70 pins and records fingerprint `44aaa90f...`, which engine 0.28.2 lists as a certified row (only the hashed engine version moved). Engine changes you see through the CLI: a `date_shift` column without `provider_config.date_format` is refused at plan compile (`date_shift_requires_date_format`), and `jitter_days: N` now sets the window `[-N, N]`; a plain `decoy fit` snapshot floors interior numeric bins at 10 rows, so it can have fewer bins than `numeric_bins`, and `numeric_bins` outside 1 to 1000 is refused; a `text_mask` config naming an unknown detector or an unrunnable detector and strategy pair is refused at validate; a table that lists the same column name twice is refused; a `when:` filter refuses the reserved column names `null`, `true`, `false`, `between`, `like`, `ilike`, `matches`, `startswith` and `endswith`. No CLI flag or verb changes. The `decoy report fidelity --json` document gains `policy.intended_columns` and `policy.intended_joints` (empty lists unless a run marks value-replacing columns as intended).

- **`decoy scan` refuses a negative `--rows` as a usage error (FREEZE-SURFACE item 3, C1).** It exits 1 with `rows must be 0 or more`; the engine used to refuse it with exit 3. `decoy scan` and `decoy demo` now make their engine call through one shared function, so their output bytes do not change.

- **Breaking: `decoy.scan()` returns the `decoy scan --output` document and follows the CLI's input rules (FREEZE-SURFACE item 3, audit J2).** It now calls the same function as `decoy scan` and returns the value-free `scan-set/v1` core as a dict, not the engine's `ColumnProfile`; it has no top values, modes, minimum or maximum. It runs the regex detectors only. A CSV path needs `has_header=True` or `has_header=False` (with `column_names`). A `.tsv` file is read tab-delimited. Other suffixes keep the CLI's CSV fallback. The default is the first 10,000 rows; `rows=None` or `rows=0` reads every row. A Parquet source with a repeated column name is refused. Table names follow `decoy scan` (`source_label` overrides; a DataFrame is `dataframe`, with source path `<dataframe>`). Usage errors are `ValueError`s that name the keyword arguments; scan errors are the engine's class-only errors. `format`, `layout`, `has_header` and `column_names` with a DataFrame now raise `ValueError`. A DataFrame is staged to an owner-only temp Parquet file for the scan and removed afterwards. For the value-bearing profile, call `decoy_engine.profile_columns`.

- **`decoy.mask()` and `decoy.scan()` report a DataFrame that Arrow cannot convert as a `TypeError` naming the error class only.** The Arrow message, which can quote a cell, is no longer raised or chained.

- **`decoy scan --detectors` and `--ner-model` choose the pre-scan detectors (SCAN-ML C2b).** `--detectors regex,classifier,ner` adds the lgbm classifier and the spaCy NER model to the regex detectors; `regex` must be in the list, and `--ner-model NAME` needs `ner`. A model that cannot run here refuses before any table is read: exit 1, the reason code and the install hint. The card gains `Detectors  regex; classifier lgbm-v1 0.1.0`, `--json` gains `detectors: [{source, model_id, model_version}]` (always, `regex` alone by default), and the saved scan records the same list. `-v` prints the `pre_scan.detectors` record on stderr. With models on, the PII note says the fields were flagged by pattern matching and the detector models. `decoy scan --config` follows with SCAN-MULTI S1c.2 and shares the same preflight.

- **Unkeyed `date_shift` refusal is pinned on every CLI surface (DATE-SHIFT-UNKEYED C1).** No CLI code change: engine 0.28.1 already refuses a `date_shift` column with no mask secret (`keyed_strategy_requires_secret`). New tests pin that `decoy run`, `decoy run --chunked` and `decoy.mask()` refuse it with the fixed text, write no target and echo no source date.

- **Every `<name>/vN` tag in the CLI is a frozen format with a map row (freeze batch S7b).** A new sentry fails the build when a tag such as `scan-set/v1` appears in `src/decoy` (Python literals and shipped yaml, json, toml and txt files) without a row in `docs/release/frozen-surfaces.md`. The seven tags the CLI writes have rows. `docs/release/public-renames.md` points to the engine contract for the old-to-new engine names, and a sentry fails if CLI source uses an old one. No command, flag or output byte changes.

- **Breaking: `decoy scan` labels a sample and `--json` `row_count` is the source row count (PROFILE-SAMPLE-LABELS C1).** The default scan profiles the first 10,000 rows. The card now reads `Rows scanned 10,000 of about 28,058 (sample, head)` on a sample and `4,812 (whole file)` on a whole read, and `Key candidates` reads `not checked (sampled scan; --rows 0 reads every row)` on a sample, because a key needs every row. `--show-fields` headers read `Null rate (sample)` and `Distinct (sample)`. In `--json`, each table object (and the flat single-file payload) gains `basis` (`sample` or `whole`), `scanned_rows` and `row_count_exact`, and `row_count` is now the source row count; before it was the rows scanned, so a script that read `row_count` for the scanned rows should read `scanned_rows`. `key_candidates` is empty on a sample. `decoy scan show` adds `(in 10,000 scanned rows)` to Nulls and Distinct on a sampled saved scan and puts `basis` and `scanned_rows` in `--json`; a scan saved before the labels reads as a sample and says `basis not recorded; read as a sample`. The `scan show --json` shape adds `basis` and `scanned_rows`.

- **`decoy run --post-validate` names merged `faker` outputs (FAKER-POOL-DISTINCT Z-C1).** When a deterministic `faker` column that is not `unique` maps distinct source values to a shared output, the post-validation section prints `table.column: N distinct source values map to M distinct outputs (L merged, pool_size P)`. Names and counts only. `--json` already carried the `cardinality_collisions` code under `report.quality_summary.quality_warnings`.

- **`decoy report integrity` ends green on the demo output (REPORT-INTEGRITY-DEMO).** No CLI code change: with engine 0.28.x, a redacted `customer_id` no longer matches the `mrn` detector as residual PII, so `decoy demo` followed by `decoy report integrity customers_masked.csv --source customers.csv` exits 0. A new test pins the walk-through.

- **Engine repin to `decoy-engine==0.28.1` (`v0.28.1`, carries 0.28.0).** Engine changes you see through the CLI: a plain `decoy fit` snapshot is `distribution-snapshot/v2` with `value_policy: flagged-redacted/v2`, keeps no label, joint cell or year held by fewer than 10 rows and no exact numeric or date extreme, and writes short sentence columns as free text (use `--include-values` for the old content); a plain profile document redacts the same small groups; `scan_baseline.on_drift: fail` needs `scan_baseline.sha256`; a `pre_scan` or `post_scan` NER model other than `en_core_web_sm` or `en_core_web_md` is refused at load; a resume under a different NER model is refused; a generate snapshot with a negative or non-finite weight is refused at run; ten connector reasons now map to outcome `configuration`; and run warnings carry flat `detail` values, so the out-of-core residency warning in `--json` now holds `no_sink` and `resident_source` flags instead of a `shapes` list. The CLI adapts its warning lines to the joined `detail` strings the engine now writes (`fit_joint_cells_truncated` columns, `generation_fidelity_below_threshold` column scores) and renames its local settings failure `too_large` to `over_limit` so it no longer copies an engine reason code. `rule_codes.py` follows the engine's literal codes. A `when:` test on an integer column now treats a blank cell the same way on every route (`!=`, `not in` and `not (...)` select blank rows), so FK keys, `date_shift` anchors and `top_code` columns can mask more rows than before; a pass-through `large_string` column is written as `string` when its values fit; published Parquet files no longer carry the source file's custom metadata; and a sampled scan profile lists no `key_candidates` and gains `basis` (the CLI scan cards and `--json` follow in a later change). The engine adds `joserfc`, `rfc8785` and `pynacl` as base dependencies, so `requirements-certified.txt` grows to 70 pins and records fingerprint `b61dcfd6...`, which engine 0.28.1 lists as a certified row. No CLI flag or verb changes.

- **Breaking: `decoy demo --ref` and `--rows` are removed (FREEZE-SURFACE S2).** Both were hidden flags that only printed that the 3-table demo was deferred and exited 1. They now exit 2 as unknown options. The dead FK dataset builder behind them is deleted. `decoy demo` and `--dir`, `--json`, `--quiet` and `--verbose` are unchanged.

- **Breaking: outbound URLs are checked by scheme and redirect, and `--notify` errors no longer echo the spec (freeze batch S6).** One function, `decoy._outbound.open_url`, now opens every urllib request the CLI makes, under a purpose (telemetry keeps its `requests` call and SMTP stays in `notify`, each held by the new sentry). `decoy upgrade --url` and the version document's artifact URLs accept `https` and `file`; an `ftp://` or `http://` value exits 1 with `url_scheme_refused` before any connection. A download redirected from https to anything but https exits 3 with `url_redirect_refused`. A disallowed scheme in a version document's artifact URL is refused while downloading, so it exits 3 with `url_scheme_refused` (the runtime path), not 1. `--notify webhook:` accepts `https` and `http`, `--notify slack:` accepts `https`; any other scheme (`file:///...` included) exits 1 at option parse with `notify_url_scheme_refused`, and each redirect hop is re-checked. The update check still follows no redirect. Every `--notify` spec error is now fixed text with no part of the spec (a webhook token can sit in it), and the `--json` error object gains `code`. A script that passed `--url http://...` to `decoy upgrade`, or a `--notify` target that was not an https or http URL, now needs a refused-scheme fix. An `http:` `DECOY_VERSION_URL` now turns the update check off (it opens `https` only), an `http:` `DECOY_BUNDLE_BASE` is refused by `decoy upgrade`, and `--quiet` now prints a bad `--notify` spec error to stderr. A new sentry fails the build when first-party code outside an exact function list makes a network call.

- **Breaking: the ambiguous `--source` refusal of `decoy report fidelity --config` has the code `report.source_ambiguous` (FREEZE-SURFACE S4).** It was `layout.report_source_ambiguous`; the code appears in the `--json` error `code` and in the CI rule set. The exit code (1) is unchanged. The `--json` message is now the fixed text "--source matches no declared source and the config declares several tables; pass the declared file" (it printed an internal object name before). The gate and warning code sets are now pinned by a snapshot test.
- **A printed path is never folded.** Off a terminal, `decoy library path` and other one-line outputs (`OK <path>`, `Wrote <path>`, `Evidence: <path>`) split a long path across lines at 80 columns. The CLI console now keeps every text-only line whole and leaves tables and panels as they were. No flag or JSON change.

- **Breaking: the `ml` extra is gone, and the NER install hint is `decoy models install ner`.** The classifier's packages are base engine dependencies, so `pip install decoy-cli[ml]` no longer resolves an extra and `all` is `cloud,ner,vault`. A pipeline that needs spaCy now prints `decoy models install ner` instead of `pip install decoy-cli[ner]` and the separate `spacy download` step. `requirements-certified.txt` names engine 0.27.0 in its header (the pins and fingerprint `789b1eae...` are unchanged).

- **`decoy validate` refuses a declared column the source lacks (QA-GATE G-cli, roadmap row 24b).** A declared column missing from a local source, or a source column the config does not declare, now exits 1 from `decoy validate` and `decoy validate preflight` with the code `decoy run` gives (`source_file.declared_column_missing`, `source_file.undeclared_column`). Before, the capacity step raised the engine refusal as a traceback. The gate reads no data row for this check. An `s3` or `gcs` source is never opened at validate: each gets a warning, "declared columns not checked: remote source, checked at run" (exit 2 with `--fail-on-warning`), and `decoy run` still refuses before any row. A config that also has a remote source skips the capacity estimate, so its local sources are not column-checked at validate until the engine repin that adds `DeclarationRequest.for_validate`. `decoy validate preflight` alone prints no remote-source warning.

- **Help and template text no longer carries internal references (DI-CLOSE C2, roadmap row 24e).** `report fidelity --help` and `report integrity --help` lose a source line reference, a `BF1` id and "the platform's" wording. `decoy explain keys` starts with which key goes with which job, states the key as 64 hex characters (32 bytes) and fits one screen. The `faker` strategy note says equal source values get different fakes unless the column is deterministic. `decoy explain modes` drops its history line. The `generate` template no longer mentions a top-level `mode: generate`, and `examples/generate_example.yaml` now has an `orders` table joined to `customers` by a `reference` column. The text sentry bans source line references, `BF<n>` ids and "the platform's".

- **A generate `formula` that raises exits 1, and the guide shows how formulas read numbers (GEN-FORMULA-SEQ C1, roadmap row 24y).** With the engine's typing fix (0.24.0 and later), `round(a / 3)` over a `sequence` gives numbers, not blanks. `decoy run` now exits 1 (not 3) with `generate_formula_evaluation_failed` when a formula raises on a row, and writes no output; the message holds the table, column, row index and a reason word, no cell value. `generate_formula_number_used_as_text` (a number used as text, such as `'ORD-' + id`) exits 1 from `decoy validate` and `decoy run`. `decoy explain exit-codes` names the run failure under exit 1. No `--json` field is added. The fit-and-generate guide has a migration table for the refused spellings.

- **Versioning policy and license wording checks (REL-GATE RG-L).** `docs/release/versioning.md` now describes the signed-bundle release and the exact `decoy-engine==` pin instead of a PyPI publish and a `>=` floor, and the 1.0.0 gate list is current. New metadata tests keep FSL-1.1-ALv2 as the one license id across the license docs and refuse a PyPI or `>=` statement in the policy. No command or flag changes.

### Added

- **The Decoy language: a compiler, a converter and a formatter for `.decoy` pipeline files (row DECOY-LANG).** A `.decoy` file is a short way to write a pipeline: sources, masking rules per column, generated tables, links between tables, checks and a subset. The compiler writes the same pipeline config the YAML files hold and runs the engine's own validation on it; an error names a line and a word, never a value from the file. A converter writes a YAML pipeline as `.decoy` and refuses, with a reason, any config it cannot write so that it compiles back to the same pipeline. A formatter keeps comments and refuses to change what the program means. A `csv` source must say `header: true` or `header: false`. Every `decoy` command that takes a pipeline file reads a `.decoy` file as it reads a YAML one, and `python -m decoy.lang` is gone. A `.decoy` file with a rule still marked `?` is refused until the mark is removed. `decoy fmt`, `decoy convert` and a `.decoy` form of `decoy init` follow. The guides are in `docs/guides/decoy-language/`. New dependency: `lark` (parser); `hypothesis` joins the test dependencies.
- **The `hipaa` and `pci` templates set `date_format` on their date_shift columns, and `decoy init` writes it when the scan proves one format (DATE-SHIFT-FORMAT C1).** The templates fix `%Y-%m-%d` on `dob`, `admission_date`, `discharge_date` and `transaction_date`; data in another format needs that line edited (a comment marks each one). `decoy init` writes `date_format` only when the engine reports one format fits every value; a mixed or unparseable date column gets `redact` with a note. Engine 0.28.1 does not report that, so init output there is unchanged. A hand-written pipeline needs `provider_config.date_format` on each `date_shift` column before the engine release that refuses one without it; the key is accepted today. No `--json` shape changes.

- **`decoy library prune`, `clean` and `export` (LIB L4b, roadmap row 40).** `prune [--kind K] [--keep-last N] [--older-than D] [--yes]` previews the exact record ids it would delete and deletes them only with `--yes`; with no options it applies the `keep_last` rules in `.decoy/library.yaml` (the default keeps all). It never deletes a record reachable from a ref or from a kept record through links, one younger than one hour, or one of a kind or version this Decoy cannot read (whose links still protect their targets). It runs under the library lock, deletes file by file, and drops a record's index rows only after its file is gone. `clean [--yes]` previews, then removes only `.decoy/scratch/`. A file left behind (held open on Windows) is listed and the command exits 4; degraded mode exits 3 with `library_lock_unavailable`. `export --output FILE [--kind K] [--since D] [--ref R] [--include-logs] [--keep-paths]` writes `decoy-library-export/v1` through the engine codec (raw envelopes in link order, refs, a 0600 file): a default export reduces path fields to file names and withholds records this version cannot strip (unknown kinds, newer payload fields), naming them in the header and counting them in a stderr notice; `--kind` and `--since` choose the starting records and every record they link to is exported too, a record that links to a withheld one is withheld as well, and a file whose records would link outside it is refused (`export_not_closed`); `--keep-paths` exports every record byte for byte. Scratch is never exported; `--include-logs` exports none until job logs exist. Prune and export first take stock of every ref and record file under the library lock (`src/decoy/cli/library/_inventory.py`); an entry they cannot account for makes prune `--yes` and export refuse with `library_unexplained_entries` (the prune preview counts them), and a ref with a byte order mark still protects its record. Deletes go through the library's one filesystem module: prune and clean never delete through a linked `library/`, `objects/` or `scratch/` (`library_path_unsafe`), and a link inside scratch is removed as an entry. `export --output` refuses a file inside `library/` or `scratch/` or a symlink (`export_destination_unsafe`), `--ref` cannot be combined with `--kind` or `--since`, and prune and export share one link-closure walk (`_index.reachable`). A ref or a link that names a record not in the library also counts as unexplained, so an export is always closed. The same rule applies to prune: while a ref names a record that is gone (a dangling ref), `prune --yes` refuses with `library_unexplained_entries` until `decoy library fsck --repair` removes the ref. The export file is written through one checked entry point, `_fs.write_export`, built on the shared `_atomic.destination_entry` placement rule, and the library has one timestamp parser (`parse_instant`).

- **`decoy library list`, `show`, `diff` and `ref` (LIB L4a, roadmap row 39).** `list [--kind K] [--pipeline P] [--table T] [--since D] [--json]` reads the index (no record file opened), oldest first, and shows a record of an unknown kind as `unknown kind <name>, needs a newer Decoy`. `--pipeline` takes a pipeline name or the path to its YAML through the shared pipeline argument (`pipeline_option`, `resolve_pipeline`), and lists the records labelled with that YAML's project-relative path; an unknown name exits 1 with `layout.pipeline_unknown`. `show ID|REF [--json]` prints the envelope and, when readable, the payload. `diff A B [--json]` compares two records of one kind: scan records per table through the `decoy scan diff` rules, evidence through the `report diff` manifest comparison, run results by status, route, delivery and per-table outcome, rows and delivery, other kinds as changed payload paths; different kinds or unreadable records exit 1. `ref KIND/NAME [ID]` prints or sets a ref under the library lock (degraded mode exits 3 with `library_lock_unavailable`). Records are named by id, a unique 8+ hex prefix (ambiguous ones refused), `KIND/NAME` refs, or `KIND/latest[~N]`; `latest` is no longer accepted as a stored ref name. Errors go to stderr; `--json` stdout carries only a successful result. All take `--library DIR`. A ref points only at a record of its own kind (`ref_kind_mismatch`, exit 1, no ref file written; a committed ref naming another kind is refused when read), and a ref read or write through a linked `refs/<kind>` or scope folder is refused with `library_path_unsafe` through the library's one filesystem module. All six `library` commands now share one root, error and exit path (`src/decoy/cli/library/_cli.py`): errors go through the one emitter (`error: [code] ...` on stderr, one error object on stdout under `--json`), exit 1 for what was typed and 3 for the library's state, the same from `path` and `fsck` as from `list`, `show`, `diff` and `ref`. The `--json` shapes of `library list`, `show` and `diff` are recorded in the release snapshot (`tests/fixtures/release_freeze/json-shapes.json`).

- **`decoy run --result PATH` writes the run result document to a file (RESULT C-DOC3, roadmap row 62).** The file holds the same document as the `result` member of `--json`, and is written on every end of the run: success, a refusal, an error and Ctrl-C. Human mode prints `Result: <path>`; `--json` adds `result_status.file` (`written` or `failed`). It goes through the same placement rules as `--evidence-out`: a path equal to an output, the quarantine file, `--evidence-out` or `--vault` (a symlink or hard link to one included) is refused with `layout.output_path_collision` before any source is read, a path under the project's `out/` folder is refused, and an existing file is replaced. A refusal that comes before the layout check (a bad `--notify`, for one) writes no file when the path is not clear, and so does any other layout fault in the config (fail closed). `--result` and `--evidence-out` are also refused when they name the pipeline file or a local file source, directly or through a symlink or hard link. A `--rows` preview writes the file in every output mode. A failed write exits as before and prints one stderr line with `run_result_write_failed` and no path. `--result` is not accepted with `--all`.

- **`decoy run --json` carries the run result document (RESULT C-DOC1, roadmap row 62).** Every `--json` envelope of a run that reaches the engine, success or failure, and the `--rows` preview envelope gain `result`: the `decoy-run-result/v1` document with the run's status, exit code, pipeline kind, route, delivery, one entry per table (outcome, rows, delivery), checks, warnings, failure and timings, and a new member `result_status` (`document` built or failed, `file` not requested, `code`). The document holds codes, counts and names only. The exit code in it is the process exit code; no exit integer and no existing `--json` member changes. If the document cannot be built the run keeps its exit code, the envelope has no `result`, `result_status.document` is `failed` with `run_result_build_failed`, and one stderr line names the exception class. The `--json` shape snapshot (`tests/fixtures/release_freeze/json-shapes.json`) gains only `/result/*` and `/result_status/*` paths for `run`; no existing path is removed or retyped. A `--chunked` run reports no row counts. Refusals before the run starts, the evidence write failure and Ctrl-C get a document in a later slice.

- **Every end of `decoy run --json` carries the run result document (RESULT C-DOC2, roadmap row 62).** The refusals before the run starts (a bad `--notify`, a `--rows` or `--fidelity` that cannot run), a bad `--master-key` or `--key-label` (exit 2), the `--evidence-out` write failure (exit 3) and Ctrl-C (exit 130) now print one `--json` envelope with `result` and `result_status`. The envelope of the bad `--master-key`, the evidence failure and Ctrl-C is new: they printed no JSON before; the bad `--notify` and `--rows` envelopes keep their members and add the two. A refusal before the run starts has timings, no config, no table and no route. No exit integer changes, the human text is the same, and the bad `--master-key` keeps Click's message on stderr. One module (`cli/run/_result.py`) now writes the envelope and ends the run; a new guard test fails when another module under `cli/run/` does. Named limits, with no document: a Click parse error, an output conflict, the managed-runtime refusal, a crash after the run's `try` closes (exit 1, `internal error`), and a process killed by SIGTERM, SIGKILL or the kernel.

- **`decoy models list`, `decoy models install ner` and the `models` step of `decoy setup` (SCAN-ML C1, roadmap row 32a).** `decoy models list [--model NAME] [--json]` prints one row per detector model (the `lgbm-v1` classifier and the spaCy NER model): available, version, runtime version, or the reason code and the fix (`brew install libomp` on macOS, `unset DECOY_ML_DISABLED`, `decoy models install ner`); it exits 0 whether or not a model is available, and 1 (`ner_model_invalid`) for a `--model` that is not a plain package name. `decoy models install ner [--model NAME] [--from PATH] [--yes] [--json]` installs spaCy and the model wheel pinned by SHA-256 into the running interpreter, through `python -m pip` or, in a venv without pip, `uv pip install --python`. Every call is wheels only (`--only-binary :all:`) under a constraints file holding every installed package at its version, so nothing installed can move, and `decoy-engine` is never named to the installer. `--from` takes a model `.whl` (only where spaCy is already installed) or a directory of `.whl` files (a fresh offline environment); the files are copied into a private folder first, symlinks and source distributions are refused, and the content is stated as trusted. Installer output is never shown. It prints the plan and asks; off a terminal it needs `--yes`. Exit 0 installed and verified; 1 `models.source_invalid`, `models.model_unpinned`, `models.managed_runtime`, `models.pip_missing`, or no `--yes` off a terminal; 3 `models.install_failed` (with `installer_exit_code`) or `models.env_changed` (naming each moved package). `decoy setup` gains `--ner install|skip` and `--ner-from PATH`: after the settings are written it offers the same install, stores nothing in `settings.json`, and `--yes` alone never installs; `--json` gains a `models` object. Installing NER takes the environment off a certified DP row, and `models list`, `models install` and `doctor` say so.
- **`decoy validate`, `decoy ci check` and `decoy run` refuse a `post_scan` model that cannot run here.** A `post_scan.detectors` entry of `classifier` or `ner` whose model is not available is a preflight error with the engine reason code (`classifier_unavailable`, `ner_spacy_not_installed`, `ner_model_not_installed`, `ner_model_incompatible`) and, outside `ci check`, the fix; exit 1. A `pre_scan` model is not checked here.
- **`decoy doctor` gains `model:classifier`, `model:ner` and `dp-certified` rows** (soft rows: they warn, never fail the exit code).
- **`decoy run` writes the post-scan report, and an NER block withholds the run (SCAN-ML C2a, roadmap row 32a).** With `post_scan.integrity: true`, `decoy run` writes the engine's integrity report beside the first target as `<config stem>.post-scan.json`, or at the new `--integrity-out PATH` (refused with `--all`); a rerun replaces it. The report carries `config_sha256`, the SHA-256 of the exact YAML bytes the run read (a CRLF file keeps its own hash). The card prints one line (`Post-scan: regex; ner en_core_web_sm 3.8.0. 2 warnings, 0 fail. Report: <path>`) and `--json` gains `post_scan: {detectors, counts, report}`. A run the post-scan blocks (`ner_findings: fail` with a failing NER finding, or a regex `fail`) exits 4, publishes no target, commits no vault and writes no evidence manifest, still writes the report, sends the failure notification with the type name only, and prints the reason registry's fixed summary; its `--json` error carries `error_kind: post_scan_blocked`, `code` (such as `post_scan.ner_blocked`) and the `post_scan` block. A report that cannot be written exits 3 with `run.integrity_write_failed` after the outputs are written. The post-scan models load before any source row is read, and one that cannot load exits 1 with its reason code and fix. `--chunked` with a model post-scan detector or `ner_findings: fail` exits 1 with `route.post_scan_models_unsupported` before any read (regex-only integrity keeps the existing `--chunked` refusal). `-v` prints the engine's `post_scan.detectors` and `post_scan.models` lines on stderr. `decoy report integrity --config` stamps the same `config_sha256` and runs the config's post-scan detectors, loaded before either CSV is read; a model that cannot run exits 1 with its reason code and fix.

- **Six industry generate starter templates (GEN-CATALOG GC2, roadmap row 24s).** `generate-healthcare`, `generate-banking`, `generate-insurance`, `generate-retail`, `generate-telecom` and `generate-hr`. Each is a three-table generate config with foreign keys through `reference` columns, so every child key exists in its parent. They use only faker output, no real-looking seeds. `decoy list templates`, `decoy show template` and `decoy init --preset` list them. A test reads the registry and checks that each template validates, runs, links its keys and uses only types and faker types that the live engine catalogs know.

- **`decoy list generate-types` and `decoy list faker-types` (GEN-CATALOG GC1, roadmap row 24s).** `generate-types` lists every generate column type with its required and optional options, and the options every type accepts; `faker-types` lists every value a column's `faker_type` accepts. Both read the engine's live catalogs (`generate_option_catalog()` and `list_generate_faker_providers()`), take `--json`, and appear in the unknown-kind message. `decoy list generate-type` suggests the plural. No flag is added.

- **`decoy run` hands the engine one progress sink and shows its phases (LIB L5a, roadmap row 41).** `cli/run/_progress.py` is a fan-out over the engine's `ProgressSink`: every engine event reaches each registered consumer unchanged and in emission order, and a consumer that raises is counted, never retried, and never changes the run's outcome or exit code. The sink goes to `run_pipeline(progress=...)` on the whole-table run and the `--rows` preview (only when the installed engine takes the keyword, as with the native lane). The bare spinner is replaced by a stderr line that follows phase and rate events (`Running mask: mask (people)`); `--quiet` and `--json` keep stdout free of it. `--chunked` gets no events yet: `run_mask_pipeline_chunked` in engine 0.22.0 takes no sink (RESULT E3 adds it). No file is written and no CLI field is added to events.

- **Library scratch (LIB L1d, roadmap row 34).** No command uses it yet. `Library.scratch(owner, invocation_id, ttl=None)` allocates row folders under `.decoy/scratch/` only through the engine's protected allocator: `open_protected_dir` reopens and checks `scratch/` on every command (an empty too-open one is tightened, a too-open one with files is refused with `scratch_unsafe`) and `protected_scratch_dir` makes each staging folder, removed when its block exits on success or error; a `ttl` allocation is kept at `scratch/<owner>-<invocation_id>`. An ACL failure stops the owner before any row is written and leaves nothing (`scratch_acl_failed`). Deletes are file by file: a file held open is skipped and reported (`library_delete_skipped`) and `Library.delete_scratch` removes it later. The CLI has no directory creation or ACL code of its own here. Deleting a scratch folder goes through the library's one filesystem module: a linked `scratch/` (for example one pointing at `library/`) or a link on the way is refused with `library_path_unsafe` and nothing is deleted, and a link inside is removed as an entry and never entered. A library at a `--library` folder with another name now gets that folder's `.gitignore` (the same text as `.decoy/.gitignore`, from the one writer `decoy.cli.io.write_decoy_gitignore`) and `.gitattributes`, once, only if absent; a scratch allocation carries the library's layout warnings (`ScratchAllocation.warnings`).

- **`decoy library path` and `decoy library fsck [--repair]` (LIB L1c.2, roadmap row 35).** A new `library` group in the Check and report panel. `path` prints the library root, its source (`--library`, `DECOY_LIBRARY` or the project), whether records are on and whether the library is degraded and why. `fsck` checks every record by the id rule (CRLF copies pass), envelopes and payloads (unknown kinds by id only), refs, dangling links (warnings), the index against the files, temp files older than an hour, private modes for the index, `tmp/`, `scratch/` and `logs/` (records and refs get a note), and job log lines; it prints one line per item and exits 0 when clean, 4 (`EXIT_FINDINGS`) on findings. `--repair` copies corrupt records into `library/quarantine/` through the atomic writer before removing them, deletes stale temp files, removes refs to missing records under the library lock and rebuilds the index; it never deletes a valid record and refuses a newer `LAYOUT`. Both take `--library DIR`. A new sentry, G-KIND-CANARY (`tests/sentry/defects/test_kind_canary.py`), requires a canary fixture or a pending row for every writable record kind (four pending: `scan-set`, `evidence`, `run-result`, `sample-run`). `decoy --help` still imports no engine code: the library facade loads lazily. Every library read, write, list and remove goes through one module, `src/decoy/cli/library/_fs.py`, which checks each folder below the library root with `lstat` and refuses a link, a junction or a non-folder with `library_path_unsafe`; fsck reports a linked library folder as `path_linked` and repair never acts under it. G-LIB-FS (`tests/sentry/io_policy/test_library_fs.py`) fails if any other library module removes, renames or writes a file. An entry fsck cannot read is its own finding and never aborts check or repair (`layout_unreadable`, `object_unreadable`, `ref_unreadable`, `log_unreadable`); a pipe at the index is `index_not_file` and is never opened. Repair re-reads each corrupt record under the library lock and moves it only on a parse failure or an id mismatch, removes a ref only when it was read and holds the id of a record that is not stored (a leading byte order mark is accepted), and reports `quarantine_failed` or `temp_delete_failed` for one entry it cannot move or delete and goes on. The library root's own `library/` folder, the SQLite index path and every object presence check go through that module too: a linked `library/` is `library_path_unsafe` before anything is opened, an object file that is a link does not count as stored, and the module owns the two SQLite opens after judging their path; G-LIB-FS now also bans path inspection, copy writers and the repo's file helpers, at any depth of the package.

- **Engine repin to `decoy-engine==0.27.0` (`v0.27.0`).** Engine changes you see through the CLI: the post-scan report is `post-scan-integrity/v3` (it was `v2`), so `decoy report integrity` writes the v3 tag and `match_rate` may be `null` for a classifier finding; the isolated route and the reference sink publish through `publish_unit`, so a published folder holds `_decoy_publication.json` and its parent holds `.<leaf>.decoy-lock`, and a target holding another result is refused as `publication_target_occupied`; `row_errors.json` is no longer written by the isolated route; `joint_mask` output changes for null `key_by` values and for `mode: gen`; and `ScratchArena.open` is now `fresh`. The CLI calls none of the removed or renamed engine names, so no CLI code changes. `requirements-certified.txt` records fingerprint `789b1eae...` for engine 0.27.0 with the same 67 pins. No CLI flag or verb changes.

- **Breaking: every route that reads a declared source checks its columns first (CONFIG-EXPLICIT C1a, roadmap row 22).** An undeclared column or a source with no `tables` entry exits 1 with `source_file.undeclared_column` or `source_file.undeclared_table` before a data row is read, staged or acquired, on `decoy tokenize`, `decoy demo`, `decoy.mask()` with a config or with DataFrame or Arrow data (it raises `PipelineValidationError`), `decoy run --duckdb-source` (checked from the relation's `DESCRIBE`, before the relation is copied), `decoy run --chunked` and `decoy subset`; a declared source that is missing, unreadable or malformed exits 1 with a coded refusal (`source_file.file_not_found`, or `csv_malformed`) and no path or value, not an internal error. `decoy detokenize` validates its config and opens no declared source, so it works when the declared files are gone. `decoy run` already refused these through the engine. `decoy report fidelity --config` and `decoy report integrity --config` check the file you pass as `--source` against the table's declaration and read it with that table's dialect: fidelity picks the declared source whose path is `--source`, else the config's only table, else exits 1 with `layout.report_source_ambiguous` (now `report.source_ambiguous`, see above) ("--source matches no declared source and the config declares several tables; pass the declared file"); integrity keeps the first declared table. Before, a `--source` that matched no declared path was read with the default header dialect. Without `--config` both verbs read your file as before.

- **SSHSIG release sidecars and key tooling (MAC-V1b).** `packaging_tools/sign_release.py` gains `sshsig` (writes `<file>.sshsig` with `ssh-keygen -Y sign`, namespace `decoy-release`), `pubkeys`, `inject-keys` and `check-keys` (the PEM and the `ssh-ed25519` form pinned in `install.sh` must be one key). `install.sh` carries the new `PINNED_SSH_PUBKEY` placeholder and a known-answer pair but does not read them yet. The version-document schema is unchanged. See `docs/distribution/version-endpoint-contract.md`.

- **`decoy scan diff --strict` exits 4 on drift (REL-GATE Q8).** Drift is a finding in the data, so `--strict` uses the same code as `decoy ci check` for the same drift (`EXIT_FINDINGS`, 4). `--strict` was never in a release, so this is the flag's definition, not a change. Without `--strict` the exit stays 0. Usage errors such as a missing file or two stdin inputs still exit 1.

- **Release readiness template and check (REL-GATE RG-R).** `docs/release/release-readiness.md` lists the 18 gate rows and `scripts/release/readiness_check.py` checks a filled copy: rows, results, evidence, G3/G5 to G7 identity, the candidate record, known-limit cells in both frozen-surface maps and, with `--release`, the sign-off and licensor lines. It prints reason codes only.

- **Canonical release smoke (REL-GATE RG-S).** `python -m packaging_tools.candidate` writes `SHA256SUMS` (every tarball, signature, installer and the version document) and `candidate.json` (CLI version and commit, engine tag and commit, and the digest of `SHA256SUMS`) beside a signed bundle set. `python -m packaging_tools.smoke_install --from-dist DIR --candidate candidate.json --pubkey PEM --target TAG` smokes that set on the host it runs on: it checks the set against the candidate record, the signed version document (not expired, the version not yanked) and the pinned keys (every installer pins `--pubkey`), installs with the candidate's own `install.sh` from a copy of the tarball, then runs, with none of the caller's `DECOY_*` or `XDG_*` settings, `decoy --version`, `decoy doctor --json`, `packaging_tools/smoke/native.yaml` (which must report `native_route.state` `native`) and the bundled `minimal` template. It works in a temporary folder it always removes (a folder it cannot remove fails the last step, `cleanup`), refuses `--keep` and `DECOY_RELEASE_PUBKEY_FILE`, and prints one `decoy-release-smoke/v1` summary. `scripts/release/record_smoke.py` appends a green summary that matches the candidate to the canonical table of `docs/release/smoke-log.md` and refuses a red run, an unknown schema, a loose type, a platform that is not a supported target or an edited row. The log's old header is replaced, and the past green `release-smoke` runs are listed once in a separate wheel-smoke table that does not count toward the release gate. Windows is refused with exit 2 while the target is gated. The shipped CLI does not change.
- **The `--json` success shapes are pinned by a snapshot (REL-GATE RG-F2).** `tests/fixtures/release_freeze/json-shapes.json` records the key paths and JSON types of one success document per `--json` command, never a value. A change to any shape now shows up as a snapshot diff, and the `shape-changelog` CI job refuses a pull request that changes the snapshot without a `CHANGELOG.md` entry. See `docs/release/frozen-surfaces.md`.

- **Library index, freshness and degraded mode (LIB L1c.1, roadmap row 35).** No command uses them yet. `library/index.sqlite` (pre-created 0600 before SQLite opens it, through the same open and lock as refs) indexes each record's kind, schema, time, invocation, pipeline, status, digest, size, tables and links, with unknown kinds kept as opaque rows. Every `open_library` lists the object file names and catches the index up in one locked transaction (missing rows inserted, rows for deleted files dropped); a missing, corrupt, other-version or table-less index is rebuilt, never migrated, and a schema rebuilt mid-process is filled from the objects before it answers. A corrupt index is emptied in place (`open_private(..., truncate=True)`, the same inode), never replaced, so two processes cannot each hold the lock on a different file. No `sqlite3.Error` leaves the lock: a corrupt index is `library_index_corrupt` (emptied and retried once), any other SQLite failure `library_index_failed`. `put` inserts the row after the object exists and a failed insert or commit never fails the put. `Library.rows(kind, pipeline, table)` and the virtual `Library.latest` (largest creation time, then id) read the index without opening record files. A network filesystem (Linux `statfs` magic numbers, macOS `f_fstypename`, Windows UNC or `DRIVE_REMOTE`) or an index that cannot be locked puts the library in degraded mode: `put` still works, ref updates refuse with `library_lock_unavailable`, and queries parse the files. See `docs/library.md`.

- **Engine repin to `decoy-engine==0.25.0` (`v0.25.0`).** Engine changes you see through the CLI: a config holding a YAML date or timestamp, NaN or Infinity is refused at plan compile (`plan/config_value_not_json`), so quote the value as a string, and an unpaired surrogate must be removed; a namespace beginning `decoy-set-namespace-` is refused (`config/namespace_placeholder_unset`); the custom provider folder variable `CUSTOM_PROVIDERS_DIR` is now `DECOY_CUSTOM_PROVIDERS_DIR`; and `pipeline_config_hash` moves because the engine canonicalises every digest input. The evidence manifest's pipeline fingerprint hashes the YAML bytes and does not move. `requirements-certified.txt` records fingerprint `c80550ef...` for engine 0.25.0 with the same 67 pins. No CLI flag or verb changes.

- **No stray files, checked end to end (PROJECT-LAYOUT P10, roadmap row 24t).** New end-to-end tests run every command with default flags from a folder outside the project and a stand-in home folder, and require each new path to sit in a place the guarantee allows: the run folder, a path you typed, the folder of an input you gave, or the demo folder. They also walk through the two-client example from the plan and check the whole resulting tree. `decoy ci` no longer changes into a scratch folder to import the engine, because the engine opens no log file by default. The generate scaffold names its snapshot through the same side-file name table as `decoy fit`, so no default file name is built outside `cli/io/_layout.py` any more. No change to command output.

- **Breaking: `decoy init` writes a pipeline into the project (PROJECT-LAYOUT P7, roadmap row 24t).** In a project, `decoy init NAME [--source FILE] [--preset P]` writes `pipelines/NAME/pipeline.yaml`; before, it wrote `pipeline.yaml` into the current folder. An existing file as the argument is still the source and now also names the pipeline after its stem (`decoy init data.csv` writes `pipelines/data/pipeline.yaml`); an invalid name exits 1 with `layout.pipeline_name_invalid`, and a name ending in `.csv`, `.tsv`, `.parquet` or `.pq` that is not a file is "does not exist" as before. The source path is written relative to the pipeline's folder when the file is inside the project and absolute otherwise, and the target is the bare `<stem>.masked.<ext>`, which `run` places in the run folder; before, both were copied as typed, with the target beside the source. Outside a project, `init` without `-o` exits 1 with `layout.project_not_found` before it reads a file or asks a question; run `decoy project new .` first, or give `-o FILE`. `-o FILE` works anywhere and now writes the source relative to `FILE`'s folder, so `decoy init -o sub/p.yaml data.csv` writes `../data.csv` and `decoy run sub/p.yaml` finds it; it also makes the folder of `FILE`. `-o -` still prints the YAML and writes no file. `--source FILE` names the source when the argument is a name, and with `--preset` its paths go into the template. Inside a project, no argument keeps the wizard and asks for the pipeline name; `--json` and `--quiet` cannot ask and exit 1. `--project DIR` and `DECOY_PROJECT` pick the project; `--json` gains `name` and `project` for a pipeline written in a project. New `docs/project-layout.md` describes the layout.

- **`decoy run` applies a pipeline's `subset:` block, and `--no-subset` skips it (SUB-RUN C1).** A run with `subset:` masks only the kept rows and writes only them. `--json` gains a `subset` object (`applied`, `fingerprint`, per-table `source_rows` and `kept_rows`, `excluded_edges`) and the summary prints `subset: kept N of M rows across K tables`. `--no-subset` masks every row without editing the YAML, and `--json` then shows `"subset": {"applied": false}`; `decoy run --all` passes it to each child. `--chunked` with `subset:` exits 1 with `config.subset_run_unsupported`, also under `--no-subset`. A subset failure during the run (such as an exceeded fan-out budget) exits 3 like other run failures. `decoy validate` and `decoy validate compile --explain` compile the run config, so a pipeline with `subset:` no longer fails the compile check, and a subset config error is a finding.

- **`decoy run` with no argument, and `decoy run --all` (PROJECT-LAYOUT P8, roadmap row 24t).** In a project with exactly one pipeline, `decoy run` runs it and prints `Running the only pipeline: NAME`. With none it exits 1 and points to `decoy init <name>`; with several it exits 1 and lists them. Outside a project it is the missing-argument usage error (exit 2) with a hint. `decoy run --all` runs every pipeline in `pipelines/`, in name order, each in its own process (the installed `decoy` entry point started with `python -c`, `--project ROOT run YAML --json` and your flags, with the working folder and the project root taken off the import path so a `decoy.py` in a project cannot replace the CLI), so engine state, logging and memory limits do not carry over and each child's exit code keeps its single-run meaning. A failure does not stop the rest. The summary table lists each pipeline, its exit code and run folder. The exit code is the first of 5, 3, 1, 6, 4, 2, 0 (the order `decoy ci check` uses) that any child produced, and a child's 6 is kept; a child that exits outside 0 to 6, dies from a signal or prints `--json` output that is not one object counts as 3. Ctrl-C at the parent stops the fan-out and exits 130. `--json` gives `{"pipelines": [child payloads, each with its exit_code], "exit_code": N}`. `--master-key` reaches children through `DECOY_MASTER_KEY`, not their command line. `--all` refuses a pipeline name, `--evidence-out`, `--vault` and `--out-dir` (exit 1), because one file would be overwritten once per pipeline.

- **Side files and reports follow the run folder (PROJECT-LAYOUT P9, roadmap row 24t).** `decoy unmask` and `decoy detokenize` now read a run's target in the format the pipeline declares (fixed width included) when you give the file by its run folder path or through `out/<name>/current/`; a copy at the old pipeline-folder place still works. The default output still goes beside the input, and a `current` link is resolved first so it lands in the run folder. `decoy report integrity` and `decoy report fidelity` on a file inside a run folder, with no `--output` or `--report-out`, also write `<run folder>/reports/integrity.json` or `fidelity.json` (owner-only) and print the path. A typed flag wins and is the only file written; a file outside any run folder writes nothing new. The default side-file names (`.unmasked`, `.detokenized`, `.snapshot.json`) now come from one table in `cli/io/_layout.py`, unchanged.

- **`decoy tokenize --out-dir DIR` (PROJECT-LAYOUT P9, roadmap row 24t).** `tokenize` takes the same option as `decoy run`: relative targets go into DIR (relative to the current folder, made owner-only after the checks) instead of a run folder, with no run id or `current` link, and files there are overwritten. The layout check `run --out-dir` makes runs first, with `--vault` in the collision rule, so a clash, an escaping target or a DIR that cannot be used exits 1 before any source is read or folder made.

- **One config loader, one exit map, one secret-reference rule (DUP-FREEZE CL3, roadmap row 24zf).** A pipeline config that is not UTF-8 text now exits 1 with code `yaml.not_utf8` and the text "Pipeline YAML is not UTF-8 text." from `validate` (all forms), `run`, `tokenize`, `detokenize`, `unmask`, `subset`, `report vault`, `report fidelity --config`, `report integrity --config` and `decoy.mask()`; before, most of them ended in an uncaught codec error and `run` exited 3. An empty file is `yaml.empty` and a file that is not a mapping is `yaml.not_mapping` on every command, with the text `validate` already used, instead of "not NoneType" or a command-specific line. `decoy ci check` reports a non-UTF-8 pipeline as SARIF rule `validate.yaml.not_utf8` (it was `validate.yaml.parse_error`). An unreadable config file (a permission error) is no longer reported as a usage error by `validate compile`; it exits 3 like the other commands. `--mask-secret` and `mask_secret_ref` accept the scheme in any case, so `ENV:NAME` works as `env:NAME`, and a malformed reference gets the same message from `run`, `tokenize`, `detokenize`, `unmask`, `report vault` and `decoy.mask()`. `decoy init` (every path but the generate scaffold), `decoy setup` and `decoy upgrade` print their failures as the `--json` error object and as `error:` on stderr under `--quiet`; `init` printed nothing for a missing input file in the default mode and now says so. `init` error text names the exception type, not the file's text. Two sentries keep it that way: a config is loaded only through `decoy._config_file`, and no new code maps exceptions to exit codes outside `decoy.cli.exit_codes.exit_code_for`.

- **Engine repin to `decoy-engine==0.24.0` (`v0.24.0`).** Engine changes you see through the CLI: with relationships declared, a run whose output gains primary key duplicates or nulls, or foreign key orphans the inputs did not have, is withheld by the post-scan gate and `decoy run` now exits 4 (findings) instead of 3; a column that leaves out a setting its strategy needs (a namespace for `hash`, `fpe`, `date_shift`, `bucket_perturb`, `categorical`, `tokenize`, or `shuffle` with `deterministic: true`) is refused by `decoy validate`; a generate `formula` reads numeric columns as numbers, and text use (`'ID-' + id`) is refused at compile, so write `str(id)`; a `formula` that raises fails the run with `generate_formula_evaluation_failed`; a `derived` column that reads a null timestamp writes a null cell; the CLI's local token vault now mints the derivation scope the engine needs when it creates the vault, so two vaults tokenize the same value to different tokens and a vault made by an older CLI is refused (use a new vault); `decoy run --vault` publishes the vault through the engine and refuses an existing vault path with exit 1 instead of replacing it, and `decoy run` now refuses that path up front, before any source loads (`--chunked` with `--vault` was already refused). A profile's `generated_at` ends `+00:00` instead of `Z`; a stored profile with `Z` still loads. `requirements-certified.txt` records fingerprint `620a48a5...` for engine 0.24.0 with the same 67 pins. No CLI flag or verb changes.

- **One error shape under `--json`, and errors that survive `--quiet` (DUP-FREEZE C1, roadmap row 24zf).** A failure now goes through one emitter. Under `--json` it is one object, `docs/schemas/decoy-error-v1.schema.json`: `command`, `status: "error"`, `error`, and when the failure has them `code` and `hint`, plus the command's own members (`config`, `source`, `kind`). `decoy fit --json` no longer sends a `message` member and no longer starts `error` with the code: `code` is its own member and `error` is the plain message. Without `--json`, `unmask`, `tokenize`, `detokenize`, `subset`, `fit`, `report vault`, `report fidelity`, `validate compile`, multi-file `scan`, `show` and the `init --preset generate` scaffold print `error:` and any hint to stderr under `--quiet`; `--quiet` silences stdout only. A coded error prints as `error: [code] message`. Nine `--quiet` help texts now say errors still reach stderr. Exit codes do not change.

- **One rule for environment switches (DUP-FREEZE CL2, roadmap row 24zf).** `CI`, `DECOY_NO_UPDATE_CHECK`, `DECOY_DEBUG` and `NO_COLOR` now read through one module. The accepted spellings are `1`, `true`, `yes`, `on` and `0`, `false`, `no`, `off`, in any case. `CI=false` or `CI=0` is no longer treated as CI, so the startup update notice can show there. `NO_COLOR=` (empty) keeps colour, as no-color.org says. An unknown value never exits: `DECOY_NO_UPDATE_CHECK=maybe` turns the update check off, and `DECOY_DEBUG=maybe` leaves debug off. `DECOY_DEBUG` accepts `true` and `yes` as well as `1`. `decoy schema` and `decoy scan --output -` print the same bytes as before, now through `ui/output.py`. Two sentries keep it that way: no other code reads a switch from the environment, and no other code writes JSON to stdout.

- **Breaking: more engine refusals exit 5 (capacity) in `decoy run` and `decoy validate preflight` (RESULT C-CAP, roadmap row 62).** Exit 5 now covers every code in the engine's capacity set, not only the fan-in and out-of-core memory gate and the generation budget: a faker pool budget that is too small (`out_of_core_faker_pool_budget_exceeded`), a reorder budget that is too small (`out_of_core_reorder_budget_too_small`), a pool over its cache budget (`pool_exceeds_cache_budget`), and a worker or process that ran out of memory (`isolated_worker_out_of_memory`, `process_out_of_memory`). `decoy validate preflight` let them escape as a traceback, and `decoy run` exited 3 for them before engine 0.23.0. `--json` reports `error_kind: capacity` and the code for each. Codes the engine lists as not capacity (a rejected budget setting, disk or quota, a routing refusal) keep their exit. The CLI keeps no list of its own, so a code the engine adds to its set exits 5 with no CLI change. `decoy explain exit-codes` and the README describe the wider set.

- **`decoy project new`, `show` and `list` (PROJECT-LAYOUT P6, roadmap row 24t).** `decoy project new DIR` makes a project: `decoy.yaml` (`kind: decoy-project/v1`), `pipelines/`, `out/` with a `.gitignore` of `*`, and `.decoy/` with its `.gitignore`. `DIR` may be `.` and is made with its parents. Run it again and it adds only what is missing and says "already a project"; two runs at once leave one valid marker. An existing `decoy.yaml` that is not a valid marker exits 1 (`layout.project_marker_invalid`) and changes nothing; your home folder, a parent of it and `/` exit 1 (`layout.project_root_refused`); a project made inside another warns `layout.project_nested`. `decoy project show` prints the selected project (`--project`, `DECOY_PROJECT`, or the walk from the current folder): each pipeline in `pipelines/<name>/pipeline.yaml`, its newest run folder and its last clean run (from `LATEST`; one that names no run folder is ignored with `layout.latest_invalid`). Status is `-` until run records exist. `decoy project list [DIR]` shows `DIR` if it is a project and each folder directly inside it that is one, with pipeline counts; links are not followed and a folder with an unusable `decoy.yaml` is skipped with a warning. All three take `--json`.

- **Cloud target root rule, offline (CLI-CLOUD CC1, roadmap row 64).** `validate`, `ci check` and `run` now judge a config with `s3` or `gcs` targets before any row is read or network call. All cloud targets must share one type, bucket, region and key directory, and not mix with file targets (`layout.delivery_root_split`). A key with a leading or trailing slash, an empty, `.` or `..` segment, a control character, the file name `MANIFEST`, or a file name another table uses, give `layout.cloud_target_invalid`. `credentials_ref` or `endpoint_url` on a target, enabled quarantine, `--chunked` and any `gcs` target give `layout.cloud_target_unsupported`; `endpoint_url` stays allowed on sources. With a cloud target, `--vault` and `--evidence-out` may not point inside the project's `out/` folder (`layout.side_file_in_out`), also under `--out-dir`. Messages name the table and field, never a key, bucket or endpoint. `decoy run` still refuses cloud endpoints at execution; this slice adds no upload.

- **One delivery folder per run, and side files kept out of `out/` (DELIV C1, roadmap row 61).** `validate`, `ci check` and `run` now refuse, before any row is read and with exit 1, a config whose file outputs (targets and an enabled quarantine file) do not share one delivery folder: in a project all must be relative, and under `--out-dir` each absolute output must sit directly in that folder with the relative ones (`layout.delivery_root_split`). In a project, `--vault` and `--evidence-out` may no longer point inside the project's `out/` folder (`layout.side_file_in_out`); a fixed `--out-dir` keeps today's rule. Both messages name the config location or flag, never a path.

- **Engine repin to `decoy-engine==0.23.0` (`v0.23.0`).** Engine changes you see through the CLI: the post-scan integrity gate now judges foreign keys from the declared keys' facts, so one orphan a run introduces fails at any table size, and a relationship entry that does not parse raises `PipelineConfigError`; the chunked and out-of-core mask routes refuse a config that asks for a model post-scan detector or `ner_findings: fail` (`route/post_scan_models_unsupported`); a token vault opens only under the mask root of a secret, so a vault keyed on the job seed by an older engine must be regenerated; S3 and GCS errors carry fixed text and a `kind`, and `S3Config.region` has no default. The bundled lgbm field classifier ships in every install, so scikit-learn, lightgbm, joblib and threadpoolctl are now engine dependencies. The engine is licensed FSL-1.1-ALv2 from this release. `requirements-certified.txt` records fingerprint `73acf493...` for engine 0.23.0 and gains four pins (joblib 1.5.3, threadpoolctl 3.6.0, scikit-learn 1.7.2, lightgbm 4.6.0; 67 pins). No CLI flag or verb changes.

- **`decoy run --json` failure envelope carries a `reason` (RESULT C-REASON, roadmap row 62).** When the engine raised the failure, the envelope gains `reason`: the engine's registered reason (namespace, code, kind, phase, severity, retry class and a value-free context) computed from the exception as raised, so a missing-extra or NER rewrite keeps the engine's own record. A refusal the CLI raises itself (a gate refusal, a vault or output-folder refusal, a bad flag, a missing extra) carries no `reason`. The `error`, `error_kind`, `code` members and every exit code are unchanged. If the reason cannot be computed the member is left out and the exit does not change.

- **Exit 6 and one exit map for `decoy run` (RESULT C-EXIT, roadmap row 62).** `EXIT_PARTIAL = 6` is a new public exit code for a run that delivered some tables and withheld the rest. Nothing returns it yet; best-effort delivery will. The `decoy run` error handler and the `--post-validate-enforce` exits now take their integer from one table, `RUN_EXIT_MAP` in `decoy.cli.exit_codes`, read through the engine's `derive_outcome`; the remaining early refusals move to it in a later slice. No exit integer of a path changes. `decoy ci` accepts 6 in its reports and ranks it between usage (1) and findings (4): `5 > 3 > 1 > 6 > 4 > 2 > 0`. `decoy explain exit-codes`, the README and `docs/ci-contracts.md` list it.

- **Name a pipeline instead of its path, on every command (PROJECT-LAYOUT P5, roadmap row 24t).** Inside a project, `decoy run orders` runs `pipelines/orders/pipeline.yaml` from any folder of the project. The same works for `validate` (also `validate config`, `compile` and `preflight`), `tokenize`, `detokenize`, `unmask`, `subset` and the `--config` option of `report fidelity`, `report integrity` and `report vault`. A token that is an existing file, has a separator or ends in `.yaml` or `.yml` is a path, as before. Any other token is a name; an unknown or invalid name, a missing project, or a pipeline folder or YAML that is a symbolic link or cannot be read (such a member is not found by name) exits 1 with a `layout.*` code (it was exit 2 for a missing file), listing the project's pipeline names and the closest match, in the command's own `--json` envelope. `decoy --project DIR <command>` and `DECOY_PROJECT` pick the project for a name; `--project` also refuses a path from another project (`layout.project_mismatch`), and `DECOY_PROJECT` is ignored for a path. A name whose folder holds its own `decoy.yaml` or `.git` is refused for the same reason. `run --json` reports `pipeline.given_as: "name"` for a name, and tab completion offers the project's names. A pipeline named `config`, `compile` or `preflight` cannot be given by name to bare `decoy validate`; use `decoy validate config <name>`.

- **`decoy run --rows` refuses a config with quarantine enabled (SAMPLE SC0, roadmap row 63).** The preview writes nothing, and an enabled quarantine block could write the quarantine file at its declared path. It now exits 1 before any source is read and writes nothing; turn `quarantine.enabled` off to preview. A config without an enabled quarantine block previews as before. Every engine run the CLI starts now passes its quarantine path explicitly, and a sentry fails a new call that does not.

- **`decoy run --chunked` refuses `post_scan.integrity: true` (DELIV CR, roadmap row 61).** The chunked route never ran the relationship key check, so a config that asked for it ran unchecked. It now exits 1 before any source is read and writes nothing; drop `--chunked` or turn `post_scan.integrity` off. A config that declares `relationships` without asking for the check still runs, with the warning shown once in the run summary and a `chunked_key_check_not_run` entry in the `run --json` `warnings` list. The warning is interim and goes away when the chunked route runs the key check. No message carries a value or a path.

- **`decoy run` exports spans to your collector (F30 C1b, roadmap row 71).** With `--otel-endpoint` (or `DECOY_OTEL_ENDPOINT`) and the `decoy-cli[otel]` extra, a run sends one `decoy.run` trace with the engine's phase spans to your OTLP/HTTP collector. Spans carry counts, durations and closed names only: no table, column, path, connection string, value or error text, and a failed span has no description or exception event. The exporter closes and flushes on every exit path inside a 2 second budget; a dead collector loses spans and changes no exit code, `--json` envelope or stderr. The `--chunked` route emits no engine phase events, so it exports the root span only. `decoy-cli[otel]` makes a DP fit refuse with `dp_stack_uncertified`; run DP fits without the extra. See `docs/guides/telemetry/README.md`.

- **Library refs and the retention policy model (LIB L1b.3, roadmap row 34).** No command uses them yet. `Library.set_ref(kind, name, id)` writes `library/refs/<kind>/<name>` (one record id) through `_atomic` `REPLACE` under the library lock, a SQLite `BEGIN IMMEDIATE` on `library/index.sqlite`, which is pre-created 0600 with `open_private` before SQLite opens it. A second writer waits up to 5 s and then fails with `library_busy` without overwriting; a lock that cannot be taken is `library_lock_unavailable`; on Windows a ref file held open by another handle (`winerror` 32 or 33) is retried by the atomic writer, which then reports its own `atomic_target_busy`, shown as `library_busy`; any other write failure, including access denied (`winerror` 5) at the publish step, is `library_write_failed` and is not retried. Kinds must be registered and names follow `[a-z0-9][a-z0-9._-]{0,63}` with one optional `/` scope (`ref_name_invalid`); the one-part name `baseline` is `ref_name_reserved`; the target must be stored (`record_not_found`); a ref file is read through `read_small_file`, capped at 128 bytes. `Library.get` reads a record back through the engine reader (`record_not_found`, `record_corrupt`), and `src/decoy/cli/library/_store.py` is the one exact-file exemption for `records.decode` in G-ONE-SCAN-READER. `load_policy` reads the optional `.decoy/library.yaml` into one strict model with the plan defaults (records keep all, per-kind `keep_last`; logs 50 runs per pipeline and 30 days; sample scratch 24 h, staging deleted on exit); it is read by `decoy.cli.io.read_owned_yaml`, the project marker's reader (owner check included: another user's file is `library_policy_untrusted`); a bad file is `library_policy_invalid` naming fields, never values. Nothing enforces retention yet. See `docs/library.md`.

- **Local record library store (LIB L1b.2, roadmap row 34).** No command uses it yet. `decoy.cli.library` resolves the library root (`--library`, then `DECOY_LIBRARY`, where `off` turns records off, then the project root's `.decoy/` from `find_project`, starting at the pipeline YAML's folder, or for scan the `--emit-config` folder then the `--config` folder, else the current folder) and stores engine `decoy-record/v1` envelopes as immutable `library/objects/ab/<62 hex>.json` files. A write goes through `_atomic.write_atomic` with a no-clobber link and never replaces a file; storing a record again is success, a different file under its id is `record_corrupt`, and a record that links to a record not yet stored is `record_link_missing` with nothing written. The first write creates `.decoy/.gitignore` (through `ensure_decoy_dir`), `.decoy/.gitattributes` (`library/objects/** -text`) and `library/LAYOUT`, never editing a file that exists; files are 0600 and created folders 0700 on POSIX. On Windows a root over 150 characters is refused with `library_path_too_long` before any write. Every library file is read through `decoy.cli.io.read_small_file` (no symlink, FIFO or device; a record over 16 MiB is `library_file_too_large` on read and on write). Errors carry a code and an error class, never a path. `evidence.compute_manifest_hash` now hashes `decoy_engine.records.canonical_bytes` (byte-identical; existing manifests verify unchanged). Two new sentries: G-LIB-WRITER (`tests/sentry/io_policy/test_library_writer.py`: no private library import, no `records.encode`, no `.decoy` path literal and no `DECOY_DIR` path outside the library, two allowlisted literals) and G-ONE-CANONICAL (`tests/sentry/io_policy/test_canonical_json.py`: no sorted-key `json.dumps` outside five allowlisted sites). See `docs/library.md`.

- **`decoy fit --fanout COLUMN` records how many rows each key has (QA-FK-FANOUT C1, roadmap row 24h).** Repeatable. Name the child-side key of a foreign key (`decoy fit visits.csv --fanout patient_id`) and the snapshot gains a `fanout` block on that column: the row count, the key count and a histogram of children per key. It holds counts only, never a key value. A generate `reference` column with `distribution: fitted` and that snapshot gives each generated parent a child count drawn from the source shape, with no orphans; other distributions are unchanged. `fit` prints `fan-out kept for patient_id: 8 keys, up to 8 rows per key` and a hint to use `fitted`; `fit --json` gains `fanout_columns` (empty when the flag is not used). A column that is not in the CSV exits 1 naming it (`fanout_column_unknown`) before the snapshot is computed. `--fanout` with `--epsilon` exits 1 (`dp_mode_fanout_unsupported`) before the CSV is read, because a DP release carries no per-key counts. Needs engine 0.22.0, which the CLI already pins. A snapshot fitted without `--fanout` is byte-identical to before.

- **Generation is easier to find (GEN-CLI C3, roadmap row 24o).** `decoy --help` groups the commands into panels (Start, Run, Generate, Mask, Check and report, Reference) and its footer names the generation path (`fit`, `run`, `report fidelity ... --generate`); a sentry fails a command that has no panel. New topic `decoy explain generation` covers the workflow, the path rule, seed versus `--master-key`, the fidelity warning and `run --rows`, and lists every column type and option from the engine's `generate_option_catalog()`, so a type the engine adds shows up with no CLI edit. `decoy validate compile --explain` now shows each generate table (rows, column types, references) and the generation order, parents first, from the engine's `generation_order`; `--json` gains `generation`. The "no FK dependencies detected" line no longer prints for a pipeline that has generate tables. `explain transforms` lists the strategies the engine registers (the same set as `decoy list strategies`), uses `strategy:`, and no longer mentions `masking_rule` or a future `--mask` flag; `explain pipeline` and `explain yaml` state the path rule and the generate column shape. Three user-text pointers to topics that never existed (`explain types`, `explain strategies`, `explain evidence`) now name real ones, and a test fails on the next one.
- **CLI checks for strict generate-column options (GEN-STRICT C1, roadmap row 24k).** No behavior change: the engine 0.22.0 repin above brought the checks. New tests in `tests/e2e/generate_config/` hold the CLI to them. Each input from the generation QA record that used to pass `decoy validate` (an option typo, a negative or all-zero weight, `null_probability: 2`, `step: 0`, a duplicate column name, an unknown faker type, locale or keyword, a broken or unreferenced formula, mixed category types, `group_by` equal to `order_by`, a `derived` column that reads a later one) now fails `validate` with exit 1 and its code, located at `tables.<i>.generate_columns.<j>.<key>` or named by table, column and option, and `decoy run` stops at its pre-run gate with exit 1 before writing any output. No message carries the option's value. `decoy schema` closes each of the 13 generate types (`additionalProperties: false`). The capacity cases (`row_count` too large for memory, exit 5) follow in C2.

- **`decoy fit --joint-max-cells` and warnings when a `condition_on` pair loses combinations (GEN-COND-CAP C1, roadmap row 24w).** A `--joint` pair keeps its 25 most common combinations; `--joint-max-cells N` keeps up to N (at most 1000, the engine's bound) and needs `--joint` (`fit_joint_max_cells_needs_joint`, exit 1, checked before the `--epsilon` rules, so `--joint` with `--epsilon` still exits with `dp_mode_joint_unsupported`). A value outside 1 to 1000 or not a whole number exits 1 with `contingency_top_k_invalid`. Without `--include-values` a cap above 25 needs both columns to be plain categories, else exit 1 with `contingency_top_k_kind_unsupported`; no snapshot is written on any of these errors. When the cap drops combinations `fit` prints one `warning:` line per pair on stderr (not with `--quiet`) with the counts and the cap that keeps them all, and `fit --json` gains a `warnings` list (`code`, `message`, `detail`), empty when nothing was dropped. A pair touching a withheld sensitive column gets no warning. `decoy run` now words `generation_condition_parent_unseen` in its summary: how many rows of a conditional column had a parent value with no fitted combination and drew from the column's overall counts. Warnings carry column names and counts, never a value.

- **Project root finder, pipeline names, run-folder helpers and the `layout.*` error registry (PROJECT-LAYOUT P1b, roadmap row 24t).** No command uses them yet; they are the services the next slices build on. `find_project` looks for `decoy.yaml` with `kind: decoy-project/v1` from a folder upward, stopping after a folder that holds `.git`, at a device change and before `$HOME`, and refuses a marker that is a link, over 64 KiB, bad YAML, or owned by another user. Pipeline names follow the engine's `is_valid_pipeline_name`; a name claim file, the `out/` folder with its `.gitignore`, UTC run ids and 0700 run folders (`_private_file.create_private_directory`) and the Windows 259-character budget are in `decoy.cli.io`. Two sentries (`test_pipeline_argument.py`, `test_layout_errors.py`) hold the single root finder and the single code registry; the registry's gate codes join the `decoy ci` rule-code set.

### Changed

- **The update check and installers use `trydecoy.com`; pinned bundles are GitHub release assets (REL-WEB RW-C2a).** The default version endpoint is now `https://trydecoy.com/cli/version.json` in the update notice, `decoy upgrade`, `install.sh` and `install.ps1`. `decoy upgrade` now reads `DECOY_VERSION_URL` too (`--url` still wins). A pinned install (`decoy upgrade --version X`, `install.sh --version X`, `install.ps1 -Version X`) now fetches `<base>/vX/decoy-X-<target>.tar.gz` from the release download base (`ARTIFACT_BASE` in `decoy.distribution.release_identity`, today `https://github.com/decoy-data/decoy/releases/download`), not from beside the version document. `DECOY_BUNDLE_BASE` overrides that base, for the latest version too. The signature check against the pinned key is unchanged.

- **The startup update check sends a fixed User-Agent and follows no redirect (REL-WEB RW-C1, roadmap row 91).** The request now carries only `Host`, `User-Agent: decoy-update-check`, `Accept-Encoding: identity` and `Connection: close`; before, urllib's default User-Agent named the Python version. A 3xx response ends the check with no notice instead of being followed to another host. The response is read up to 64 KiB, and the notice shows the latest version only in its canonical PEP 440 form; any other answer is cached as unknown for 24 hours. The opt-outs are unchanged (`--no-update-check`, `DECOY_NO_UPDATE_CHECK`); the module text no longer mentions a config setting, which never existed.

- **Engine repin to `decoy-engine==0.26.0` (`v0.26.0`), and one code for two tables on one destination (DUP-DEST CL2, roadmap row 24zh).** Two declared tables whose targets write to one destination (equal paths after `.` and repeated separators are dropped, or one S3 bucket and key, or one GCS bucket and object) are now the engine's refusal, `target_shared_destination`, at `targets.<table>.path`, `.key` or `.object`. `decoy run`, `decoy validate` and `decoy ci check` report that code for the same config and exit 1; before, they reported `layout.output_path_collision`. `validate compile` refuses it too, exit 1, before it writes `--output`; it used to compile such a config cleanly. `validate preflight` reports it as `schema.field` at those locations. `decoy tokenize` reports it as its config error, exit 1. Breaking for the Python API: `decoy.mask()` raises `ConfigValidationError` with the engine code for equal targets, instead of `LayoutError` `layout.output_path_collision`. Outputs that meet only on disk (a symlinked folder, hard links, a case-folding volume, a `..` segment, a target on the quarantine file or `--vault`) keep `layout.output_path_collision` everywhere. Engine change you also see through the CLI: a fixed-width row count checks record framing but no longer casts values, so a bad value no longer fails the count. `requirements-certified.txt` records fingerprint `dceac0cd...` for engine 0.26.0. No CLI flag or verb changes.

- **`decoy validate`, `decoy ci check` and `decoy run` refuse a misplaced output before reading any source, `run` says where it wrote, and `run --out-dir DIR` (PROJECT-LAYOUT P4, roadmap row 24t).** The gate's config layer now runs the layout checks that need no write, for every relative file target and an enabled quarantine path: a path that leaves its run folder or names no file (`../x.csv`, `.`, an empty path, `sub/`) is `layout.output_path_escapes`; with a relative output it also reads the project marker (`layout.project_marker_invalid` or `layout.project_marker_untrusted`), the pipeline name (`layout.pipeline_name_mismatch`, `layout.pipeline_name_invalid`) and an existing claim, read only (`layout.pipeline_name_collision`), and on Windows the 259-character budget (`layout.path_too_long`). Each exits 1 at `validate` and at `run`'s pre-run gate, and is a `validate.layout.*` rule in `ci check`, before a source is read and before `out/` exists. A config with only absolute targets skips these checks. The `would_overwrite`, `path_invalid` and `parent_unwritable` advisories now look only at absolute targets, since a relative one lands in a new run folder. `decoy run --chunked` with `quarantine.enabled: true` exits 1 before reading a source; the chunked path never wrote quarantine rows. The `run` summary prints `Project`, `Run folder` and `Latest` (relative under the current folder, else absolute), and the table lines print paths the same way. `run --json` adds `output_dir`, `outputs` (`{table, path}` for each file a writer finished publishing, kept in one ledger so a failure after the first file still lists it; absent when nothing was published), `project` (`root`, `implicit`, `skipped`) and `pipeline` (`name`, `yaml`, `given_as`), every path absolute; `project` and `pipeline` are null for a config with only absolute targets or with `--out-dir`. `output_dir` appears only when a listed file is below the run folder or `--out-dir`, so a gate refusal, a failure before the first publish, an empty chunked run and an absolute-target-only run have none. Two outputs that resolve to one destination (two targets, a target and the quarantine file, two absolute spellings, a symlinked folder, or `--evidence-out` or `--vault` aliasing one) exit 1 with `layout.output_path_collision` before a source is read, naming only the config locations or flag names; `validate preflight` applies the same rule to the config outputs. `decoy run --out-dir DIR` writes relative outputs into DIR (relative to the current folder) instead of a run folder: no project, claim, run id, `LATEST` or `current` checks, and files there are overwritten with a pre-run warning. A DIR that is a file, a dangling link or has no parent exits 1 with `layout.output_dir_unusable` before a source is read; a missing DIR is made 0700 only after the gate passes and only when a relative output needs it. A `--rows` preview runs no layout check, since it writes nothing. A relative target must stay inside DIR, through existing links too. Absolute targets are unchanged. `tokenize --out-dir` is not in this slice.
- **CI lanes are registered and checked (CI-L1b).** `ci/required-jobs.toml` lists the jobs a pull request must pass and `ci/unlaned.toml` the lane exceptions (today only the diagram regen's path filter). `tests/sentry/tooling/test_ci_lanes.py` fails when a job, marker or test folder has no automatic lane, an `--ignore`d test file runs in no other job, a job has no `timeout-minutes`, or the release-smoke drift canary becomes required. The `ci` workflow now also runs daily, a newer push to a pull request cancels its stale run, and every job has a timeout. No CLI behavior change.
- **Evidence manifests verify the same from any folder (PROJECT-LAYOUT P3, roadmap row 24t).** In a project with a `decoy.yaml` marker, `decoy run --evidence-out` records the pipeline, source and output paths relative to the project root and adds `path_base: "project"`; a path outside the project is absolute. Without a marker every path is absolute and there is no `path_base`. Sources are fingerprinted at the file the run read, resolved from the YAML's folder (they used to be hashed from the working directory), and outputs at the placed file in the run folder. `decoy report verify` and `decoy ci check` read the manifest through one reader: a `path_base: "project"` manifest resolves from the typed `report verify --project`, else from the marker above the manifest file, never from `DECOY_PROJECT` or the working directory; with neither, `report verify` exits 1 naming `--project` and `ci check` refuses the check with `ci.evidence_unreadable`. A manifest without `path_base` keeps the old rule (relative paths from the working directory). The reader now refuses a manifest whose `schema_version` is not exactly `cli-local-1`, whose `path_base` is not absent or `"project"`, or whose paths, fingerprints or fingerprint groups have the wrong type, with exact JSON types (`true` is not an integer, `"12"` is not a number) (`report verify` exits 1, `ci check` gives `ci.evidence_unreadable`); unknown extra keys are still allowed. The refusal names the field, never its value. Paths are resolved before they are made relative, so `sub/../../x` or a symlinked folder is recorded absolute, and the reader reads a project-relative path by the layout's one path rule (`decoy.cli.io.contained_path`, shared with target placement): `/` only, no backslash, no drive or UNC anchor, no climb above the root, no symlink out. A project file whose name breaks that rule is recorded absolute. A project manifest also records `project_manifest` (where it was written in its project, or null outside it); evidence moved to another project or another place in it is refused (`report verify` exits 1, `ci check` gives `ci.evidence_unreadable`), and one written outside its project needs `report verify --project`. Every `decoy report` command and `ci check` now read manifests through one strict reader whose schema the writer also checks: a top-level list, a null required field or `NaN` is refused instead of crashing. That reader also resolves every stored file path (the pipeline and each entry with a fingerprint), so `report show` and `report render` refuse a manifest `report verify` would refuse, and `report diff` reads each manifest's outputs from that manifest's own project instead of the working directory (`--require-data` from another folder used to report them missing). A sentry (`tests/sentry/io_policy/test_manifest_path_resolution.py`) fails any other code that turns a stored manifest path into a file path. `docs/ci-contracts.md` states both rules.
- **`decoy run` and `decoy tokenize` write relative outputs into a run folder (breaking, pre-GA; PROJECT-LAYOUT P2b, roadmap row 24t).** A relative target or quarantine path now lands at `<project>/out/<name>/<run-id>/<path>` instead of beside the YAML, for whole-table and `--chunked` runs and every format. The project is the nearest `decoy.yaml` marker above the YAML, else the YAML's folder; the name comes from `pipelines/<name>/`, a declared `name:` or the file stem. The first run writes `out/<name>/PIPELINE`; a second YAML that declares a claimed name exits 1 with `layout.pipeline_name_collision` before any write, and one that only derives it gets a 6-hex suffix. Each run folder is 0700 and named `<UTC time>-<8 hex>`, the hex from the command's invocation id, which is also the evidence `run_id`. After a run that exits 0, `out/<name>/LATEST` holds the folder name and `current` links to it (POSIX; not `latest`, which would collide with `LATEST` on case-insensitive filesystems such as the macOS and Windows defaults); a failed or interrupted run leaves both alone, and a run that failed before writing removes its empty folder. A relative path that leaves the run folder exits 1 with `layout.output_path_escapes`. Absolute and cloud paths are written as given, and a config with only those makes no `out/` folder. The quarantine path goes to the engine as `quarantine_path`, so the config dict and its hash are unchanged. `decoy demo` and `decoy.mask()` keep fixed paths; a relative `mask(out=...)` is relative to the current folder. Output writers now take a `RunLayout`, and a sentry (`tests/sentry/io_policy/test_output_placement.py`) holds output path building to it.
- **Generated tables too large for memory exit 5 at `decoy validate` and before `decoy run` writes anything (GEN-STRICT C2, roadmap row 24k).** With engine 0.22.0 the preflight capacity check refuses a config whose resident generated output cannot fit the machine's memory (`generation_budget_exceeded`), so `decoy validate` exits 5 and `decoy run` stops at its pre-run gate with exit 5 (`--json` `error_kind: capacity` and the code). The finding text is picked by code: a generate refusal shows the engine's byte counts and largest table name and says to lower `row_count` or use a bigger host, while an out-of-core refusal keeps its old text. A bare `MemoryError` during a run now exits 5 with `capacity: the run ran out of memory.` (`--json` `error_kind: capacity`, no code) instead of exit 3 with an empty `error: `. A config with a non-file source skips the estimate, so a generate floor refusal there exits 5 only at `decoy run`. A config with a missing or unreadable source file exits 1 first (the engine is not reached), so the exit 5 needs readable sources. `decoy validate preflight --help`, `decoy explain exit-codes` and the README exit-code table no longer say the generate path is unchecked. No message carries a generated value.
- **Config errors show names and locations, never submitted values (VALUE-FREE-ERRORS A3, roadmap row 24a).** Every command that validates a pipeline config (`validate`, `validate config`, `validate preflight`, `subset`, `run`, `tokenize`, `detokenize`, `report fidelity --config`, `report integrity --config`, `demo`, `init`) and `decoy.api.mask` now goes through the engine's `parse_pipeline_config` and prints `PipelineConfigError.problems`. The old paths printed Pydantic's text, which echoed a bad value, an unknown key's value or the union tag you typed. Config keys, table and column names and file names stay in the text. `--json` keeps its `code`, `message` and `location` keys; the `message` text for validator failures and the form of `location` change, and `decoy validate config` text now ends with the location. `decoy tokenize` no longer cuts the error at 500 characters. `decoy.api.mask` raises `ConfigValidationError` with no chained Pydantic error. `sanitize_yaml_error` is now the engine's `yaml_error_text`. A new sentry (`tests/sentry/defects/test_config_error_routes.py`) walks `src/decoy` for any other route to a raw `ValidationError` and runs each config-taking command on a marker config.

- **`decoy validate compile` sees the pipeline's relationships, and `decoy validate` reports a relationship error once (CLI-QA1 C1).** The no-profile compile used a sentinel profile with no relationships, so it printed `no FK dependencies detected` for a pipeline that declares one and passed a relationship the engine cannot resolve. It now builds the sentinel from the config's `relationships:` through the engine's `profile_relationships_from_config`: `--explain` lists the parent table before its child, and a parent and child column with no shared namespace fail with `namespace_missing` (exit 1) as `decoy validate` reports it. A composite relationship whose parent and child column counts differ is a compile error on both commands, not a crash. In `decoy validate`, when the compile layer already reports the error the capacity estimate hit, the preflight `capacity.plan_uncompilable` row becomes a warning that says capacity was not checked, so the error shows once and the preflight layer no longer prints `passed`; `decoy validate preflight` on its own still fails that row. Breaking pre-GA: a no-namespace relationship that `validate compile` used to pass now fails. A new first-user test also checks that `scan`, `demo` and `run` leave no `logs/` folder in the working directory (fixed by the engine 0.21.0 pin).
- **License changes from BUSL-1.1 to FSL-1.1-ALv2 (breaking, pre-GA).** `decoy-cli` now uses the Functional Source License, Version 1.1, Apache 2.0 Future License, the license `decoy-engine` takes from its first FSL release onward (earlier engine releases, including the currently pinned 0.22.0, stay Apache-2.0). Any use is permitted, including production use inside your company, except a Competing Use: making Decoy available to others in a commercial product or service that substitutes for it or offers substantially similar functionality. Unlike the BUSL draft, this also covers a forked, rebranded on-prem product, not only a hosted service. Each release converts to Apache-2.0 two years after it ships, replacing BUSL's single 2030-05-10 Change Date. Package metadata reads `license = "FSL-1.1-ALv2"`. [`LICENSING.md`](LICENSING.md) answers the common questions in plain English. The licensor name (Decoy Labs LLC) stays a placeholder until the LLC is formed; counsel confirms in release gate R1-c.

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
- **`decoy run` runs the whole `decoy validate` check before it reads any data (breaking, pre-1.0).** Config, compile and preflight run first, through the same code `decoy validate` and `decoy ci check` use (a `--duckdb-source` relation is staged first so the check sees the file the run reads; a config that is not UTF-8 still exits 3 until FU-7); an error stops the run with `decoy validate`'s exit code (1, or 5 for a capacity refusal) and nothing is read or written. There is no skip flag. Exit codes: a missing, unreadable or corrupt source file, and a no-profile compile crash, now exit 1 where `decoy run` exited 3. `decoy run --json` on a refusal keeps `command`, `status`, `config`, `mode` and `error` and adds `error_kind` (`validation`, or `capacity` with `code`, or `missing_extra` with `extra`, as before) and `messages` (the list `decoy validate --json` emits, each message cut to 500 characters). The `error` text for a config refusal is now a one-line summary naming the first finding and its location, no longer Pydantic's `str(exc)`. Warnings never stop a run; human mode prints one stderr line with their count. On `--chunked` a capacity refusal is an advisory warning, because that route never takes the out-of-core path it prices. Related contract changes: a `cardinality_mode: unique` column moves from the error `no_profile_unique_incompatible` to the warning `compile.needs_profile` in `decoy validate` (exit 0, or 2 with `--fail-on-warning`; `validate compile --no-profile` keeps its error), and `decoy ci check` rule `validate.no_profile_unique_incompatible` (error) becomes `validate.compile.needs_profile` (warning); `decoy validate config` reports `target.<table>.would_overwrite` (was `target_file.would_overwrite`) and `target.<table>.parent_unwritable`, and `decoy ci check` in config-only mode reports them too; the `capacity.source_unreadable` check (code `capacity_source_unprofilable`) prints the error type, no longer the reader's text.
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

- **Launch pin check (RG-F3).** `scripts/release/launch_pin_check.py --engine-tag vX.Y.Z` fails closed unless `lock_version.sh --engine-spec` ends in that tag, the lock-profile sentry and `lock.sh --check` pass, and `pyproject.toml`, `_version.py` and `decoy --version` agree; one line per step, exit 0, 1 or 2. The engine pin test now reads the pin from `lock_version.sh`.
- **CycloneDX SBOM generator (R1-c).** `scripts/release/sbom.sh` writes a reproducible CycloneDX 1.6 SBOM of the certified runtime pins (`requirements-certified.txt`) with the tool environment pinned, hash-enforced and wheel-only from `scripts/release/sbom-tool-requirements.txt`, run isolated (`python -I`, `uv --no-config`, no ambient `UV_*` settings, CPython 3.12 only); no timestamp or serial; well-formed public pins only, one per package, with the generated components checked against the pins. Not signed or published. Docs: `docs/release/sbom.md`.

### Fixed

- **`decoy library path` prints a long root on one line.** The root was wrapped at the terminal width, so a long path (a macOS temp folder, for example) came out split across lines; it now prints whole and is never read as markup.
- **`decoy report fidelity` names the column, metric and reason of a `gof_unavailable` warning (roadmap row 24zv).** The line printed the placeholder text `gof_unavailable (column, metric, reason)`. It now reads `column <name>: <metric> goodness-of-fit unavailable (<reason>)`. `--json` is unchanged.
- **`decoy report vault --help` no longer says the vault key comes from the seed (roadmap row 24zw).** The help said the vault was keyed from `global_settings.seed` while the command text said the seed is not key material. Both now say the vault opens under the mask secret and the seed is not key material.

- **`decoy validate` checks absolute output targets without a false first-run warning (CLI-QA1 C3b).** `run` creates a missing output folder, so the `target.<table>.parent_missing` warning was false on every first run; it is removed. `target.<table>.parent_unwritable` replaces it and fires only when the nearest existing parent is a file, a folder you cannot write or no reachable ancestor exists. An absolute target path the system cannot inspect now produces a value-free `target.<table>.path_invalid` warning instead of an internal error. A relative target lands in a new run folder, so these checks skip it. `decoy ci check` maps the warnings to `target.parent_unwritable` and `target.path_invalid`.

- **Identifier, hash, glob and tag checks refuse a trailing newline (VALUE-FREE-ERRORS B2, roadmap row 24a).** Eight Python `re` patterns ended in `$`, which matches before a final `\n`, so `orders\n` passed the `--duckdb-source` relation check that guards SQL text, and a `decoy ci` rule token, finding fingerprint, path glob, staged git object id, templated rule code or scan tag could carry a trailing newline. They now end in `\Z`. The `decoy init` comment split reads an already stripped line and behaves as before. Two sentries in `tests/sentry/defects/` use the engine's recurring-defect scanner (vendored byte for byte, pinned in `ci/vendored.toml`): `test_anchored_regex.py` fails on a new `$` anchor, and `test_exception_context.py` holds the 37 existing `raise ... from None` sites inside an `except` block as a shrink-only baseline.

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

[Unreleased]: https://github.com/decoy-data/decoy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/decoy-data/decoy/releases/tag/v0.1.0
