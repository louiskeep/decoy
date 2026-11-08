Status: record

# VALIDATE-ALWAYS Part 2 build record (`decoy run` runs the validate gate)

Plan `docs/plans/2026-11-06-validate-always.md` (branch `plan/validate-always`), part P2, plus the P1 carry-over `validate-always-p2-carryover.md`. Branch `feat/validate-always-p2-run` from CLI `origin/main` `60c3519`. P1 is CLI #88.

## Environment

- Tests ran on VM 6 through `~/bin/vm-run cli` (lock-faithful venv, engine 0.19.0). The devbox venv has an older engine and was used only for lint and the typer docs regeneration. `ruff` was run as the pinned `0.15.14` (`uvx ruff@0.15.14`), because the devbox ruff 0.15.20 reformats 12 unrelated files.
- Heads: `f263184` (feature), `6933940` (path-free refusal text, found by gates), then the record commit.

## Anchors that moved (plan line to current line on `60c3519`)

| Plan anchor | Now |
|---|---|
| `run.py:243-258` `_load_raw_config` | `:252-264` (now a thin call to `parse_pipeline_yaml`) |
| `:576-588` re-parse in the spinner | `:584-597` (replaced by the saved-findings raise) |
| `:590-622` DE-02 guard | `:600-632` (unchanged) |
| `:628-668` `--duckdb-source` staging | `:637-677` (unchanged) |
| `:684` `PipelineConfig.model_validate` | `:693-696` (replaced by `check_before_run`) |
| `:697` `--mask-secret` | `:706` |
| `:821` native gate | `:830` |
| `:842` / `:856` / `:882` source read, chunked, `run_pipeline` | `:851` / `:865` / `:891` |
| `:917-1160` handler; `:1005-1065` exit map | `:931-1170`; `:1005-1065` |
| `:1071-1073` 500 cap | `:1076-1078` (now `cap_error_text`) |
| `:1100-1124` JSON `error_kind` | `:1105-1126` |
| `preflight.py:514-518` unreadable text | already fixed text from P1 (`:474-480`) |

No planned edit stopped making sense. CLI-DIALECT, CLI-FMT and ATOMIC-OUTPUT only moved the lines above; `run.py` shrank from 1757 to 1730.

## What changed

- `gate/_run.py` (new, 148 lines): `check_before_run`, `PreRunCheckError` (`from_result`, `from_findings`, `json_members`), `ERROR_TEXT_CAP`, `cap_error_text`, `CAPACITY_CODES` (moved from `run.py`, one list for the run handler and the gate).
- `run.py`: one YAML parse through `parse_pipeline_yaml`; a YAML syntax finding raises `PreRunCheckError` before the DE-02 guard; the gate runs after `--duckdb-source` staging and before `--mask-secret`, the native gate and any read; the handler gains one `PreRunCheckError` branch (exit code, `--json` members, no verbose hint). `_ConfigValidationError` and its exit-map entry are gone. Docstring gains the gate paragraph, so `docs/cli-reference.md` is regenerated (`python -m typer ... docs`).
- `gate/_layers.py`: the chunked capacity finding carries route-specific text (L2); the check name comes from `preflight.CAPACITY_CHECK` (L1).
- `preflight.py`: `CAPACITY_CHECK` constant replaces nine literals and two comparisons (885 lines, was 886).
- Sentry `test_gate_single_entry.py`: the three `run.py` exemptions are deleted (test and baseline JSON); `yaml.*load*` (any `load` spelling) and `compile_plan(**kwargs)` are flagged and seeded (Dennis MEDIUM-2).
- `test_validate_gate.py::test_corrupt_source_leaves_no_reader_text` now patches `decoy_engine.profile.profile_source` to raise with the marker (Dennis MEDIUM-1; a real pyarrow error never echoes file bytes, so the old fixture could not fail). It asserts the real finding code `capacity_source_unprofilable` (L4).
- `CHANGELOG.md` `### Changed` entry (L3, Q2 and every 11d change).

File sizes: `run.py` 1730 (was 1757), `preflight.py` 885 (was 886), `validate.py` 411 (untouched), `gate/_run.py` 148, `gate/_layers.py` 348, `gate/__init__.py` 35, `test_run_validate_always.py` 500. No pin raised.

## Exit-code and assertion changes

- `tests/e2e/test_run_command.py::TestExitCodeDispatch::test_runtime_error_still_exits_runtime` (missing source, exit 3) became `test_missing_source_is_refused_by_the_gate` and asserts exit 1 (plan AT-1, Q2). The runtime-3 class is pinned by AT-14 in the new file. This is the only existing assertion that moved.
- No other test was edited except the Dennis MEDIUM-1 fix above (a test that could not fail, made able to fail) and the sentry changes the plan names.

## Acceptance tests (new file `tests/e2e/test_run_validate_always.py`, 37 tests)

Parity matrix (10 finding kinds x plain and `--chunked`): AT-1, AT-2, AT-3, AT-5, AT-5e, AT-5y, AT-9. Singles: AT-1 stderr location, AT-3c, L2 text, AT-4, AT-6, AT-7, AT-7m (three cells and the cap), AT-8 (two), AT-10, AT-12, AT-13, AT-14. AT-12 is a unit-level check of `check_before_run` and `from_findings`; the handler discards the original exception under CliRunner, so the run path itself is not observable.

Red-first: the feature and its tests were written together; the red evidence is the mutation table. Before the code, the old behavior was visible in the one retargeted test (exit 3).

## Mutations (each applied once on the feature head, named test went red, reverted; run on VM 6)

| Mutation | First red test | Red count |
|---|---|---|
| M1 delete the `check_before_run` call | `test_run_refuses_what_validate_refuses_before_any_read[yaml_empty-plain]` | 15 |
| M2 gate after `_load_sources_from_config` | same matrix, `[yaml_empty-plain]` (spy sees a read) | 14 |
| M3 capacity refusal exits 1 | matrix `[yaml_syntax-plain]` (exit mismatch); the `fan_in` cells too | 15 |
| M4 drop the chunked route rule | matrix `[fan_in-chunked]`, `test_chunked_capacity_refusal_is_a_warning` | 3 |
| M5 restore error severity on `compile.needs_profile` | `test_unique_column_runs_and_validate_warns` | 1 |
| M6 `messages` only for config-layer findings | matrix `[compile_error-plain]` | 8 |
| M7 drop `extra` from the NER finding | matrix `[ner_absent-plain]` | 2 |
| M8 print warnings to stdout | `test_warnings_print_one_count_line_in_human_mode_only` | 1 |
| M9 gate above the DE-02 guard | `test_bad_mask_secret_ref_stays_behind_the_de02_guard` | 3 |
| M10 restore the engine message in `_check_capacity` | `test_reader_text_never_reaches_output[argv0]` | 3 |
| M11 drop the run-envelope cap | `test_run_caps_each_message_and_validate_does_not` | 1 |
| M12 gate on the YAML before staging | `test_gate_runs_on_the_staged_parquet` | 2 |
| M13 gate in the non-chunked branch only | matrix `[yaml_empty-chunked]` | 8 |
| M14 `typer.Exit` from the adapter | matrix `[yaml_empty-plain]` (no refusal envelope); AT-10 also loses its event | 15 |
| M15 build the error inside an `except` | `test_pre_run_check_error_has_no_cause_or_context` | 1 |
| M18 classify every post-gate exception as usage | `test_runtime_failure_after_the_gate_still_exits_runtime` | 1 |
| S1 `_check_source_files` call in `run.py` | `test_no_pre_run_check_outside_the_gate` | 1 |
| S2 `from yaml import safe_load as s` in `run.py` | same | 1 |
| S3 `decoy_engine.PipelineConfig.model_validate` in `run.py` | same | 1 |
| S4 `yaml.load(..., Loader=...)` in `run.py` | same | 1 |
| S5 `compile_plan(r, p, **kw)` in `run.py` | same | 1 |

Not mutated: AT-13 (bypass the engine reader `profile_source` uses; no clean one-line mutation of the gate) and the carry-over MEDIUM-1 "restore reader text" mutation as a separate row (it is M10, which is the same edit). The seeded sentry spellings for `yaml.load`, `full_load` and `**kwargs` are cases in `_SEEDS`, run by `test_walk_sees_each_spelling`.

## Gates (T1)

- `scripts/dev/gates.sh --keep-going --baseline`, VM 6, head `f263184`: ruff and sentry (559) pass; selected tests branch 5 failed, baseline 0 failed. All five were `tests/e2e/cli_fmt/test_target_format_dispatch.py` cells that assert the temp path is not in `decoy run` output: my first summary text embedded the config path. Fixed in `6933940` (the text now says `decoy validate CONFIG`).
- `scripts/dev/gates.sh --keep-going`, VM 6, head `6933940`: env, ruff and sentry (559) pass; tests 354 passed, 0 failed.
- Before the fix, one wider run on VM 6: `tests/e2e/test_run_*.py`, `test_validate_gate.py`, `test_ci_*.py`, `test_gate_single_entry.py`, `test_ci_rule_codes.py`: 333 passed, 3 skipped, after the one retarget above.
- Full suite: not run (orchestrator). The plan names P2 a full-suite trigger (exit-code mapping on a public contract).

## Timing note (plan section 12)

1M-row source, one redact column, VM 6, three rounds each, wall time of `CliRunner` `decoy run` in a fresh process (gate = this head; no gate = the same head with `check_before_run` replaced by `PipelineConfig.model_validate` only):

| Source | With gate | Without gate | Gate cost |
|---|---|---|---|
| CSV 1M rows | 2.59 / 2.55 / 2.52 s | 1.77 / 1.75 / 1.80 s | about +0.8 s (+45%) |
| Parquet 1M rows | 1.06 / 1.02 / 1.03 s | 0.27 / 0.26 / 0.26 s | about +0.77 s (about 4x on a fast run) |

This is over the plan's 10 percent line and goes to the owner. The cost is nearly constant (about 0.8 s), not per row: the bounded 10k-row profile and the no-profile compile run once. On a run that takes minutes it is noise; on a sub-second run it dominates. The measurement was on a 1-column redact job, the cheapest possible run.

## AT-3c: the chunked `remap` variant

The T8 fan-in graph (67 parents, `orphan_policy: remap`) under `--chunked`: the gate prints its one warning and does not exit 5. Without declared key dtypes it then exits 1 with `chunked_fk_child_key_dtype_unprovable` (an engine chunked-compat rule after the gate, not a gate finding). With `dtype: string` declared on every column it runs to exit 0 and writes the target. The `preserve` graph under `--chunked` exits 1 with `chunked_fk_orphan_policy_not_remap`. Plain `run` of the same graph exits 5 (`capacity`, `out_of_core_fanin_exceeds_budget`).

## Deviations (technical choices, recorded)

1. `_load_raw_config` returns `(raw, findings, read_error)`. `parse_pipeline_yaml` catches only `YAMLError`; an unreadable or non-UTF-8 config used to be swallowed and re-raised inside `try`, giving exit 3. Keeping that avoids a traceback before the `try` (FU-7 is the planned proper fix).
2. `run.py` calls `cap_error_text(...)` (exported with `ERROR_TEXT_CAP`) instead of reading the constant; one function, no second literal.
3. The refusal summary says `decoy validate CONFIG`, not the real path: existing CLI-FMT tests require that no temp path reach `decoy run` output. The findings' own messages are unchanged (a missing-source finding still names its path, as `decoy validate` does).
4. `CAPACITY_CODES` moved from `run.py` to `gate/_run.py`: the gate needs it to pick the capacity finding, and a second copy would be the class the sentry exists for.
5. AT-4's config uses a non-deterministic unique faker column. With `deterministic: true` plus `cardinality_mode: unique` the profiled compile refuses the job at run time (`deterministic_mode_unsupported_cardinality`), which is a genuine config error, not an example of Q1.
6. The optional carry-over "qualify class methods as `Class.method`" in the sentry was not done (no class method is flagged today).

## Self-review (defect classes)

1. Value-bearing output: checked `PreRunCheckError` text, `messages`, the warning line, `--notify` (type name only, AT-10), AT-7 (marker in a mask_secret_ref list never printed), AT-7m (reader text). The schema `msg` fields come from the gate as before; `str(exc)` with `input_value` no longer reaches run.
2. Races and locking: n/a, one synchronous call. TOCTOU between the source check and the read is the plan's accepted limit (section 11a #7).
3. Input normalization: empty, list and scalar YAML, non-mapping `global_settings`, non-UTF-8 config (deviation 1).
4. Every route and caller: plain, `--chunked`, `--duckdb-source`, `--vault` and native flags all pass the single call; `validate`, `ci check` untouched. The matrix covers plain and chunked.
5. Referential integrity: n/a.
6. Tests that can fail: mutation table above. No pin raised, no test weakened.
7. Honest records: CHANGELOG lists each 11d change; the code names in this record were read from the code (`capacity_source_unprofilable`, not `capacity.source_unreadable`).
8. Field paths and keys: finding locations are config paths (names), as in `decoy validate`.
9. Sentry: nothing routed around; the new sentry cases are in `_SEEDS`.
10. Today's rule: exit mapping read from `gate_exit_code` (capacity 5, error 1); `--fail-on-warning` is not used by `run`.
11. Read paths match write paths: `run` and `validate` now share one reader path for the gate (AT-13).
12. Cross-OS and files: n/a, no file writes added.
13. Characterization: `test_chunked_gate_warning_text_names_the_route` is a text pin for L2, red under M4.
14. Choke points: `decoy.cli.gate.check_before_run` (run), `run_gate_on_config` (all), `CAPACITY_CODES`, `CAPACITY_CHECK`, `cap_error_text`.
15. Sizes: above.
16. Sameness: the 500-char cap literal was the only copy in `run.py`; `demo.py:544-545` and `tokenize.py:245,542` keep their own (FU-1 in the plan).
17. Placement: `gate/_run.py` is where the plan's Placement table puts it.
18. Recurring-defect catalog: anchored regex n/a; strict wire types n/a; no exception context (AT-12, M15); versioned read models n/a; normalized scanners (sentry resolves aliases, seeded); no private imports (the existing `preflight._check_*` imports stay inside the gate); no hidden CI failures (gates run); one trust class per entry point n/a; mutations on the final head: run on `6933940`-equivalent source (the only later change is this record); checked allowlisted helpers n/a; no raised pins.

## Not done

- Full suite and hosted CI (orchestrator). Roadmap row 23 and `docs/RECENTLY-SHIPPED.md` update at merge.
- AT-13 mutation. A second pass of the mutations on the exact final head if the record commit is not the final one.
- Windows/macOS runs.

## Gate round 1 fixes (orchestrator)

- Mac and VM full runs found two red cells the impact selection skipped: `test_source_csv_dialect.py::test_headerless_misfit_fails_closed[open_quote-True]` and `[late_quote-True]`. The gate's bounded profile (engine `profile_source`, 10,000 rows) now refuses an unterminated quote before the chunked engine runs, so those cells no longer reach it. Every assertion is kept; the two cells now expect the gate to stop the run and no target. A new `past_window_quote` cell puts the quote past the profile window and still requires the chunked engine to be reached, the same code and no target. `test_chunked_failure_after_chunk_one_writes_no_target` (row 61a) uses the past-window file, so it still proves a chunked failure after staged chunks publishes nothing.
- Dennis M1: CHANGELOG now says the `capacity.source_unreadable` check (code `capacity_source_unprofilable`) prints the error type; it does not name the table.
- Dennis L2: the `assert result.config is not None` in `gate/_run.py` is an explicit check that survives `python -O`.
- V2-LOG from Dennis: L1 (`--duckdb-source` with list YAML refuses with `DuckDBSourceError`, FU-2), L3 (add `report.py:2146` and `subset.py:274` to FU-1), L4 (`ci/rule_codes.py:41` literal), L5 (human capacity refusal drops the old remediation lines).
