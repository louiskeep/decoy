Status: record

# CLI-DIALECT Part C build record (read CSV sources with their declared dialect)

Handoff `p05-cli-dialect-build-handoff.md`, Part C. Branch `feat/cli-dialect-c` from CLI `origin/main` `dd403986` (the handoff names `fix/cli-dialect-honour-csv-fields`; the orchestrator cut this branch name).

## Environment

- Base `dd4039869bc69a99644a185b8446de04b66bf0b0`. Engine `v0.19.0` is tag `71c9d60d`, commit `4a0d5b1f0d2014f35e663d29f7794622a5c7d334`.
- Red and green runs: devbox venv `~/.cache/decoy-cli-dialect-venv` (CPython 3.10.20, `requirements-dev.lock`, engine 0.19.0) through `~/bin/pytest-one`. T1 gates: VM 5 and VM 6 through `vm-run` (`venv-cli-vmrun`, lock-faithful).
- Blob prefixes matched the handoff for every file this slice edits. Two files differ from the handoff list and none is a census row: `run.py` (`9810caa9f92d`, not edited), `scripts/dev/sentry_registry.toml` (`61e1a92f4488`) and `CHANGELOG.md` (`b250f75622a6`), both moved by earlier merges.

## Dennis repro

Config: headerless CSV, `column_names: [id, name, age]`, `hash` on `name`.

- Repin commit `5fcc982` (src as at the repin): `decoy validate config` exit 0, `decoy run` exit 3, `error: 'name'` (the handoff says `'column_1'`; with the declared names in the plan the missing key is `name`).
- Head: `decoy run` exit 0, output columns `id,name,age`, `name` hashed, `id` and `age` unchanged.

## Red runs (commit 1, repin without its fixes)

Pin moved, lock regenerated, test and header edits withheld: 7 failures, all in the allowed list.

- `test_pyproject_metadata.py::test_engine_dependency_pinned` (pin `==0.18.0` vs `0.19.0`).
- `test_ci_rule_codes.py::test_every_engine_code_is_allowlisted` and `::test_the_engine_half_is_derived_from_the_registry_not_written_by_hand`: three new literal engine codes, `digest` (`declared_casting/_quarantine_local.py:504`), `magic` (`:439`), `type` (`config/_declared_casting.py:55`). Fixed in `rule_codes.py`; the test is unedited.
- `test_plan_command.py` three tests: `plan_version` 2 to 3 (expected constant only, comment re-worded).
- `test_ner_missing_extra.py::...test_model_not_installed_leaves_engine_message_untranslated`: `spacy download` to `install its wheel` (substring only).
- `test_ci_lock_installs.py::test_lock_profile_lives_in_lock_version_and_the_policy` went green once `ci.yml`, `release-smoke.yml` and `lock_version.sh` moved with the pin, as the pre-launch note said. No test edit.

Green after the fixes: 597 passed (those files plus `tests/sentry` and `test_sbom_script.py`). No other id changed result.

Acceptance tests (commit 2) on the repin tree before the reader change: 38 failed, 14 passed (the 14 are cases the engine already refuses at validate, the sentry self-checks, and the byte-pin). On head: all pass.

| Test | Red on repin | Green on head |
|---|---|---|
| AT-D1 `test_headerless_with_column_names_runs` x3 (run, tokenize, mask) | 3 failed | 3 passed |
| AT-D2 `test_delimiters` x3 | 3 failed | 3 passed |
| AT-D3 `test_default_dialect_unchanged`, `test_report_source_without_config_equals_pandas` | the byte pin is green by design; the report-source test needs the new function | passed |
| AT-D4 `test_chunked_honours_dialect` x4 | 4 failed | 4 passed |
| AT-D5 `test_headerless_misfit_fails_closed` x12 | 7 failed (the rest are already refused by the validate gate) | 12 passed |
| AT-D6 `test_mask_data_override_keeps_dialect` x2 | 2 failed | 2 passed (see DESIGN item 1) |
| AT-D7 `test_init_tsv_declares_delimiter` | failed | passed |
| AT-D8 `test_cli_read_errors_are_coded_and_value_free` x12 | 12 failed | 12 passed |
| AT-D9 `test_report_verbs_read_declared_dialect` x2 | (added after the red run; red by mutation D9 and D11) | 2 passed |
| AT-D10 `test_iter_source_chunks_fails_at_call` | failed | passed |
| AT-D11 `test_csv_read_choke_point.py` | 2 failed (reads outside `_sources.py`) | 8 passed |
| AT-D12 pin test | red on the 0.18.0 pin (above) | passed |
| AT-D13 cert smoke | below | below |

## Mutations (each applied once, the named test went red, reverted)

| Mutation | First red test |
|---|---|
| D1 `CsvDialect()` instead of `resolve_csv_dialect(src)` | `test_headerless_with_column_names_runs[run]` |
| D2 dialect without `delimiter` | `test_headerless_with_column_names_runs[run]` (headerless pipe read as one column) |
| D3 `read_report_source` passes `dtype=str` | `test_read_report_source_declared_and_default`; default branch: `test_report_source_without_config_equals_pandas` |
| D4 restore `pd.read_csv(path, dtype=str, chunksize=...)` | `test_chunked_honours_dialect[headerless]` |
| D5 replace the engine call with `pd.read_csv(sep, header=None, names)` | `test_headerless_misfit_fails_closed[extra_field-True]` |
| D6 copy the dialect only when `format == "csv"` | not killable: see DESIGN item 1 |
| D7 drop the `delimiter` line from the init YAML | `test_init_tsv_declares_delimiter` |
| D8 re-raise the coded error without `from None` | `test_cli_read_errors_are_coded_and_value_free[extra_field-whole]` |
| D9 `read_report_source` ignores `config_dict` | `test_report_verbs_read_declared_dialect[fidelity]` |
| D10 `iter_source_chunks` back to a generator | `test_iter_source_chunks_fails_at_call` |
| D11 `pd.read_csv(source)` back in `report fidelity` | `test_csv_read_choke_point.py::test_no_csv_read_outside_the_choke_point` |
| D12 pin back to `==0.18.0` | `test_engine_dependency_pinned` |
| D13 old fingerprint in the `requirements-certified.txt` header | `cert_smoke.py`: `running fingerprint 795732eb... does not match the b643894d... recorded` |
| rule_codes: drop the three new entries | the two `test_ci_rule_codes.py` tests (the red run above) |

## Certification smoke (AT-D13)

Fresh CPython 3.10.20 venv, `uv pip install --no-deps` of engine `v0.19.0` and the CLI wheel, then `requirements-certified.txt`, then `python scripts/cert_smoke.py`:

```
running platform: PlatformTriple(system='linux', machine='x86_64', implementation='CPython', libc='glibc')
running cpython: 3.10.20.final
running fingerprint: 795732eb0808001d9c4591f3693637187637bb383a87b8caa95b8f2f269f9211
matches requirements-certified.txt: OK
certified row in engine manifest: OK
dp schema: dps-marginal/v3
recorded fingerprint matches running environment: OK
FIT + ARTIFACT: OK
GENERATION FROM DP SNAPSHOT: OK
CERTIFICATION SMOKE PASSED
```

The fingerprint is the CLI runtime row Part R admitted in `dp_provenance.py` (`795732eb...`); the 63 pins are unchanged.

## Gates (T1)

- Commit 1 (`5fcc982`), VM 6, `scripts/dev/gates.sh --keep-going --baseline`: branch 0 failing; baseline (origin/main tests on the 0.19.0 environment) 6 failing, all repin fallout above; ruff and sentry (466) pass.
- Head (`fa515bd` plus the record commit), VM 5, same command plus the named, behavior-kept and git-grep files (32 files): gates branch=0 baseline=6 branch-only=0; the file run: 931 passed, 4 skipped.
- Lock check: `scripts/dev/lock.sh --check` OK. Only the engine line of `requirements-dev.lock` moved.
- Full suite: not run (orchestrator, merge head).

## Files vs allowed list

Commit 1: the repin set plus `rule_codes.py`, `test_plan_command.py`, `test_ner_missing_extra.py` (the pre-launch addition) and the comment re-anchors (`_token_vault.py`, `pyproject.toml`). Commit 2: `_sources.py`, `api.py` (`_stage_source_entry` and docstring), `init.py`, `report.py`, the three new test files, `csv-read-allow.json`, `sentry_registry.toml`, `_baseline_sources.py`, `test_sentry_manifest.py`. Commit 3: `CHANGELOG.md`, the public-API channel line. `test_sentry_manifest.py` lists every sentry file, so its one added line is part of registration (the gate-single-entry precedent did the same). Nothing else is touched. `report.py` net: `git diff --numstat origin/main...HEAD -- src/decoy/cli/report.py` prints `9 10`, net minus 1.

Line counts: `_sources.py` 146 (was 91), `init.py` 647, `report.py` 2381, `api.py` 627, `test_source_csv_dialect.py` 281, `test_sources_dialect.py` 84, `test_csv_read_choke_point.py` 190.

## Self-review

- Class 1 and 8: every refusal message and the AT-D8 `str`, `repr`, `__cause__`, `__context__` checks hold no cell value, path or file name. Checked: `test_cli_read_errors_are_coded_and_value_free`, D8 mutation.
- Class 3: BOM, CRLF, a quoted field with an embedded delimiter and newline, a blank line, no trailing newline and a one-column headerless file all read (ad hoc run through `read_source`); an unterminated quote is refused with `source_file.column_count_mismatch`.
- Class 4 and 16: the census grep shows no `read_csv` or `read_csv_source` call under `src/decoy` outside `_sources.py` and the six allowlisted readers. One suffix-to-separator rule remains (`_scaffold_source`).
- Class 6 and 13: each acceptance test has its mutation (table above).
- Class 7: CHANGELOG, docstrings and the pin comment match the code.
- Class 11: `decoy validate` profiles a bounded sample (1,000 rows for `schema()`), so it agrees with `decoy run` only within that sample; a misfit row past the sample passes validate and `decoy run` refuses it with the code.
- Class 14: choke points are `_sources.read_csv_frame` (CLI) and `decoy_engine.read_csv_source` (engine); error codes are the engine registry.

## DESIGN

1. AT-D6 parquet case: the handoff expects a `format: parquet` declaration with `delimiter` to pass silently on the base. It does not. `decoy.mask(config=...)` validates the config first and the engine refuses the declaration (`delimited params (delimiter) are only valid when format='csv'`) before `_stage_source_entry` runs. The copy-the-keys-whatever-the-format edit is kept, but mutation D6 has no observable effect, so the test asserts the config-time refusal instead. Its message is pydantic text without the `source_file.csv_param_on_non_csv` code.
2. AT-D5 chunked unterminated quote: the engine reader cannot see it in its scan; in a chunked read the parser error surfaces on the first chunk step, after `run_mask_pipeline_chunked` has been called. The run still exits 1 with `error: source_file.column_count_mismatch: source people ...`, no output file, no leaked value. The "no chunk reached the engine" assertion therefore skips that one case.
3. `_build_scaffold_yaml` keeps its `file_format` parameter and gains `delimiter=None`, because `tests/unit/test_init_inference.py` calls it with `file_format`; changing the signature to take the descriptor would edit an existing test.
4. `read_csv_frame` returns `Any` (a frame, or an iterator with `chunk_size`); `read_source` and `iter_source_chunks` are its typed callers.
5. `report integrity` warns on a source mismatch by resolving the declared path against cwd (`report.py:2058-2062`), while the dialect match resolves it against the config directory. They can disagree when cwd is not the config directory. Not fixed; it belongs to the `_resolve_path` follow-up.
6. Follow-up copies not folded: `_resolve_path` (`_sources.py`, `run.py`, `demo.py`), `demo.py` `_load_sources_from_config` vs `run.py`, the platform upload reader, `iter_csv_chunks` in the engine.
7. Existing `ruff format` drift in `init.py`, `report.py`, `rule_codes.py` and `test_plan_command.py` is untouched (there is no format gate in `ci.yml`).

## V2-LOG

- Multi-table `decoy run --chunked`: a misfit in a later table fails after earlier tables' outputs are written (`run.py:1508-1510`); belongs with F22.
- `decoy init` infers only `.tsv` as tab-delimited.
- `decoy scan` and `decoy fit` take caller-named files and their own flags, not a declared dialect.
- Other coded engine errors reach `decoy run` as `str(exc)` without their code (generic fix belongs in `run.py`, CLI-FMT Part A).

## Not verified

- macOS arm64: the Mac mini is reachable but has no `uv`, `tmux` or a CPython 3.10, so the named tests and gates were not run there. The lone-CR and CRLF behavior on macOS is unchecked.
- The full suite on the merge head (orchestrator).
