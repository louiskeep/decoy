# Reachability pass: packages A and B (row 24zd, DUP-DEFECTS)

Status: record

Date: 2026-11-12. CLI main `e642d69b`, engine main `c96e2855`; the CLI pins `decoy-engine==0.22.0`.
Input: [REMEDIATION.md](REMEDIATION.md) packages A (17 engine items) and B (11 CLI items). No code
was changed.

For each item the question was: can the copies give different results for the same input that a
user reaches from a `decoy` command? Marks:

- **REACHABLE-DEFECT**: a CLI command and a config or input a user can write reach the difference,
  and output bytes, the exit code or the message differ. A single-behavior item (no second copy)
  gets this mark when a user path reaches the bad behavior.
- **LATENT**: the copies differ, but no user path reaches the difference, or an earlier check
  refuses first. Library and platform callers may still reach it; the item says so.
- **IDENTICAL**: the copies behave the same for every input.

READ means settled by reading the code; RUN means a small check ran in the CLI venv (pinned
engine) or the engine venv through `~/bin/vm-run`, on the Mac or a test VM, with synthetic values.
No test suite ran. Line numbers are current at the SHAs above, so some differ from REMEDIATION.md.
Path shorthand as there: `E:` is `decoy-engine/src/decoy_engine/`, `C:` is `decoy/src/decoy/`.

## Counts

| Package | REACHABLE-DEFECT | LATENT | IDENTICAL | Items |
|---|---|---|---|---|
| A (engine) | 5 | 12 | 0 | 17 |
| B (CLI) | 6 | 4 | 1 | 11 |
| **All** | **11** | **16** | **1** | **28** |

## REACHABLE-DEFECT list

| # | Command and trigger | What differs | Effect |
|---|---|---|---|
| A1 | `decoy run`, two `joint_mask` groups with null `key_by` cells (mask mode) or `provider_config.mode: gen` | Both groups seed `default_rng` from `mask_key[:8]` with no namespace, so the n-th fallback row of each group picks the same reference row | Output bytes; contradicts engine `docs/determinism.md:117` ("Two columns in different namespaces are independent") |
| A5 | `decoy validate` / `decoy run` with a statistical `snapshot_file` holding a non-UTF-8 byte | `UnicodeDecodeError` escapes the `JSONDecodeError` catch | validate: "internal error (UnicodeDecodeError)", exit 1; run: raw codec text, exit 3. A truncated snapshot gets `STATISTICAL_SNAPSHOT_UNREADABLE`, exit 1 |
| A6 | `decoy validate compile --profile p.json` on Python 3.10, a profile whose `profiled_at` ends in `Z` | `E:profile/_serialize.py:153` has no `Z` shim | 3.10: "did not parse as a Profile JSON", exit 1; 3.11+: compiles. Decoy writes `+00:00`, so only a hand-made profile hits it |
| A10 | `decoy run`, parquet timestamp column with a null (`NaT`) feeding a `derived` expression such as `case_when(a < b, 1, 0)` | `derived._is_null` counts only `None` and float NaN; the kernel counts `NaT` as missing | Output bytes: `explicit_null` gives `0` instead of an empty cell; `sentinel` and `default` skip substitution |
| A15 | `decoy run --chunked` on a parquet source whose text columns are `large_string`, with a `when` on a categorical or non-deterministic faker column | The chunked `when` guard accepts `string` only; admission treats `large_string` as equal | A valid config is refused with a widening message that is false for `large_string`; the same data as `string`, or without `--chunked`, runs. Fails closed |
| B5 | Any config file that is not UTF-8 | Seven loaders catch only `YAMLError` | `validate` (all forms, `--json` too), `tokenize`, `unmask`, `subset`: "internal error (UnicodeDecodeError)", exit 1, no `--json` envelope; `run`: raw codec text, exit 3; `compile_explain`: "could not read", exit 1 |
| B6 | `decoy scan` or `decoy gen` error with `--quiet` | The error line prints; other commands print nothing in quiet mode | Message. The `--quiet` help says "Errors still go to stderr", so scan and gen match the help and the other commands are the odd ones |
| B7 | `decoy scan 'd[v2].csv'`, `decoy show schema '[x]'`, `decoy fit --dp-number 'a[v2]:0:5:9'` | Printed without `markup=False`; Rich drops `[tag]` text | Message: the bracketed part of a path or flag value disappears from the error. `--json` unaffected |
| B8 | `decoy run` or `tokenize` with `mask_secret_ref: ENV:FOO` (or `Env:`, or another registered scheme) | CLI guard is a case-sensitive `env:`/`file:`/`vault://` prefix test; engine `parse_ref` lower-cases and accepts any registered scheme | Usage refusal in the CLI for a ref the engine accepts. Side finding: the gate has no mask-secret check, so such a config passes `decoy validate` and fails at `decoy run` (read, not run) |
| B9 | `CI=false decoy <cmd>`; `DECOY_NOTIFY_SMTP_PORT=abc decoy run --notify webhook:...` | `CI` read as truthy when set to anything; the port is parsed before dispatch for every channel | The update notice is suppressed; a bad SMTP port drops webhook and Slack notifications too ("notify dispatch failed: invalid literal for int()"). Run exit code unchanged |
| B11 | `decoy run --notify webhook:file:///p` or `slack:file:///p`; `decoy upgrade --url file:///...` | No scheme check anywhere on notify targets or `--url` | Notify: the file is opened, then the channel reports "unexpected error"; nothing is sent. Upgrade: a local file is read, but the version document and bundle still verify against the release key, so no bypass. Hardening only |

## Package A (engine)

### A1 EX-2: `joint_mask` fallback and gen-mode generator ignore the namespace
- Mark: REACHABLE-DEFECT (READ)
- Sites: `E:transforms/joint_mask.py:338` (null-key fallback in `_pick_rows_mask`), `:366-367` (`_pick_rows_gen`), both `default_rng(int.from_bytes(job_seed[:8], "big"))`; key from `E:execution/_strategies/_joint_mask.py:123` (`job_seed=ctx.mask_key`). The namespace passed at `:124` reaches only the keyed-row HMAC at `joint_mask.py:333`.
- Path: `decoy run` with two `joint_mask` groups in different namespaces; mask mode needs null `key_by` cells, gen mode needs `provider_config.mode: gen` (read unvalidated at `_joint_mask.py:69`).
- Differs: both groups draw the same `integers(0, row_count)` stream, so the n-th fallback row of each picks the same reference row. Keyed rows are namespace-scoped and unaffected. The 8-byte cut also shrinks a 32-byte mask key to 64 bits of seed.
- Evidence: `E:docs/determinism.md:117` promises independence across namespaces; `E:docs/strategies.md:597-640` promises only a "seeded random row". Within one group the shared stream is harmless.

### A2 EN-2, EX-3: native `_span_key` strict UTF-8
- Mark: LATENT (READ)
- Sites: `E:execution/native/_draw_site_providers.py:107-117` (copy, strict); `E:transforms/text_mask.py:242-263` (original, `errors="replace"`, used at `:498`).
- Path: none. The copy is reached only through `shift_days` and `span_seed` on the draw-site reference providers, via `provider_for`; none of these has a caller in either repo's `src/`. The shipped native text_mask route uses `TextMaskHandler`, which uses the original. Arrow and Parquet text is valid UTF-8, so a lone surrogate cannot come from a file.
- Differs: only for a direct call of the dead copy with a lone surrogate (raises instead of replacing).

### A3 EX-2, ED-7: composite no-seed fallback (zero seed vs `os.urandom`)
- Mark: LATENT (READ)
- Sites: zero seed at `E:generation/composite/_address.py:70,96`, `_provider.py:78,116`, `_city_state_zip.py:86`, `_custom.py:184,206`, `_name_email.py:81,134`, `_person.py:79,142`; random at `_address.py:181`, `_provider.py:204`, `_city_state_zip.py:124`, `_custom.py:280`, `_name_email.py:221`, `_person.py:239`.
- Path: none reaches `spec.seed is None`. The only production caller, `E:execution/_strategies/_composite.py:123-131`, passes `ctx.mask_key` or `ctx.job_seed`; `job_seed` is always 8 bytes (`E:plan/_seed.py` defaults a missing seed to 0) and `mask_key` falls back to it (`E:execution/_adapter.py:263`). `ProviderSpec._validate` forbids `deterministic=True` with no seed.
- Differs: a library caller with `seed=None` gets a reproducible pool but fresh sampling entropy.

### A4 EX-2: `int.from_bytes(seed, "big")` with no length check
- Mark: LATENT (READ)
- Sites: `E:generation/composite/_person.py:143`, `_name_email.py:135`, `_address.py:97`, `_provider.py:117`, `_custom.py:207`, `E:execution/native/protocol/providers_gen.py:75` (reference model, no production caller); pool check at `E:generation/pool/_sampler.py:168-190`.
- Path: composite seeds come only through `ProviderSpec`, whose `_validate` (`E:providers_v2/_adapter.py`, `SEED_WRONG_LENGTH`) refuses lengths other than 8 or 32. Both valid lengths work with `default_rng`.
- Differs: nothing observable; the rules differ only on paper.

### A5 EX-4: snapshot `json.loads(bytes)` misses `UnicodeDecodeError`
- Mark: REACHABLE-DEFECT (RUN)
- Sites: `E:plan/_generation.py:217-224` (`read_and_pin_snapshots`, the live path); `E:generation/statistical/_spec.py:205-211` (reached only through `resolve_pinned_snapshot` when no read pass ran; `compile_plan` and `run_config_only_checks` always run the read pass, so this site is CLI-latent).
- Path: `decoy validate cfg.yaml` or `decoy run cfg.yaml`, a `type: statistical` generate column whose `snapshot_file` contains a byte such as `\xff`. `decoy fit` and `decoy init` write snapshots; a user can edit or corrupt one. The `gen` scaffold gate runs the same compile pass.
- Differs: truncated JSON gives `STATISTICAL_SNAPSHOT_UNREADABLE`, exit 1, in both commands. Invalid UTF-8 gives "internal error (UnicodeDecodeError)", exit 1, in `validate` and the raw codec message, exit 3, in `run`.
- Evidence: the gate (`C:cli/gate/_layers.py`) catches only `PlanCompileError`; `UnicodeDecodeError` is a `ValueError` but not a `JSONDecodeError`. `E:vault.py:482` shows the fix shape.

### A6 ED-4: `datetime.fromisoformat` and a trailing `Z` on Python 3.10
- Mark: REACHABLE-DEFECT for one site (READ). Python 3.10 is supported: CLI `requires-python >=3.10`, engine `>=3.10,<3.13`, CLI release smoke runs 3.10 to 3.12. The 3.10 behavior is the language's; no 3.10 interpreter was run.
- Sites and marks:
  - `E:profile/_serialize.py:153` (no shim): REACHABLE. `decoy validate compile --profile p.json` (`C:cli/compile_explain.py:198-210`) with `"profiled_at": "...Z"`. On 3.10 it refuses with "did not parse as a Profile JSON", exit 1; on 3.11+ it compiles. Decoy writes `+00:00` (`E:profile/_source.py:169`), so only a hand-made profile carries `Z`.
  - `E:generation/statistical/_sample.py:503-504` (no shim): LATENT. A hand-edited snapshot `min`/`max` with `Z` crashes on every version (ValueError on 3.10, a naive/aware TypeError on 3.11+); `decoy fit` writes naive values (`E:quality/snapshot.py:498`).
  - `E:generation/_window_admission.py:177`: LATENT. Library only (`generate_rows`); refuses on both versions with different text.
  - `E:generation/_pinned_compile.py:196` and `E:_reference_date.py:37`: IDENTICAL. Input is normalized first; library pinned path only.

### A7 ED-5: epsilon and delta validators
- Mark: LATENT (READ)
- Sites: `E:quality/dp.py:145-190` (`_validate_fit_params`, `float(epsilon)` first); `E:plan/_checks_dp.py:86-130` (`parse_dp_ceiling`, refuses bool and str at `:110`), second use at `:522`.
- Path: the two guard different inputs. `parse_dp_ceiling` reads YAML `global_settings.dp`; `_validate_fit_params` is reached only from `decoy fit --epsilon/--delta` (`C:cli/fit.py:597-718`), which are typer `float` options, so a string or bool never arrives.
- Differs: nothing on a CLI path. Other asymmetries on separate inputs: `delta=0` is refused by `dp.py` and accepted by the plan ceiling.

### A8 ED-6: `DECOY_ML_DISABLED` vs the strict signature flag
- Mark: LATENT (READ; the census claim is accurate)
- Sites: `E:profiling/model_pack/loader.py:186` (`== "1"` only), also read at `_detectors.py:71` and `loader.py:205`; strict set at `loader.py:57-58`, `:81-99`.
- Path: none from the CLI. `ModelPackLoader`, `load_detectors`, `classify_fields` and `classifier_status` have no caller outside `profiling/model_pack/` besides re-exports in `E:__init__.py` (same at tag v0.22.0); the CLI never references `model_pack` or either variable.
- Differs: for a library or platform caller, `DECOY_ML_DISABLED=true` leaves ML on silently.

### A9 EC-6: identifier locale gate
- Mark: LATENT (READ, RUN for the CLI path)
- Sites: refuse at `E:providers_v2/identifiers/_ssn.py:110-116`, `_ein.py:158-163`, `_ndc.py:94-99`, `_npi.py:89-94`; locale ignored at `_pan.py:97`, `_iban.py:203`, `_icd10.py:88`, `_cusip.py:151`, `_mrn.py:89-95`. The gate is only in `generate_random`; `derive_value` never reads locale.
- Path: identifiers are reachable only as `strategy: faker` with `provider: synthetic_*`, or as `composite_custom` slots. All are `poolable=False`, and the plan check `check_non_poolable_provider_with_pool_backend` (`E:plan/_checks.py:98`) refuses them first; composite slots set locale to `en_US`.
- Differs: nothing reachable. RUN: `validate config` and `run` on `synthetic_ssn`, `synthetic_pan`, `synthetic_mrn`, deterministic true and false, `locale: de_DE`: all 12 refuse with `non_poolable_provider_with_pool_backend`. The owner decision in REMEDIATION.md (refuse in all or drop the gate) still stands for GEN-PROVIDERS (row 24p), which would expose these.

### A10 ED-2: `NaT` and `pd.NA` in `derived` and formula null checks
- Mark: REACHABLE-DEFECT for `NaT` in `derived` (RUN). `pd.NA` was not reached on the paths tried.
- Sites: `E:transforms/derived.py:206-210` (`_is_null`: `None` or float NaN); `E:generators/_formula.py:206` (same rule); `E:kernel/_scalar.py:14-47` (`_is_missing` counts `NaT` and `pd.NA`).
- Path: `decoy run`, mask config, parquet source with a timestamp column holding a null, a `derived` column with the default `null_propagation: explicit_null` and `case_when(a < b, 1, 0)`. Mask-mode `derived` reads `df[refs].itertuples()`, so `NaT` reaches `_is_null` as non-null.
- Differs: output bytes. Row `a=NaT, b=2020-02-02` gives `0` where `explicit_null` should give an empty cell; `sentinel` and `default` also skip substitution. Expressions whose functions return null on `NaT` (`days_between`) hide it.
- Evidence: RUN output `2,,2020-02-02,0`. Nullable ints from parquet, faker-masked nulls and generate `null_probability` reached the check as `None` or NaN and were handled.

### A11 EN-5: self-FK ordering, out-of-core vs sequential
- Mark: LATENT (READ, RUN of the CLI shape). The census's "fails only on the large route" does not hold.
- Sites: `E:execution/out_of_core/_route_policy.py:216-245` (self-edge is a cycle); `E:execution/_sequential_order.py:18-60` (self-edge skipped); earlier gate `E:execution/out_of_core/_compat.py:493-520` (rejects a self-FK with `out_of_core_self_referential_fk_unsupported`, citing the `_table_order` crash).
- Path: out-of-core is chosen only after `check_out_of_core_compatibility` accepts; the CLI has no execution-mode flag, and `--chunked` also checks first. A self-FK falls back to the sequential route.
- Differs: nothing. RUN: `emp(id, manager_id)` self-FK ran on `Route sequential`, exit 0; `--chunked` gives the chunked lane's own typed refusals, never the cycle error.

### A12 EC-27: three generation entries without `@entry_point`
- Mark: LATENT (READ)
- Sites: decorated `E:generation/_plan_entry.py:178-251` (`generate_tables`); undecorated `:254` (`generate_tables_streamed`), `:292` (`generate_tables_from_generation_plan`), `:326` (`generate_tables_streamed_from_generation_plan`). `E:fileaccess/__init__.py:75` lists only `generate_tables`.
- Path: no engine `src/` caller and no CLI caller for the three; the CLI generate route goes through `run_pipeline` (decorated). The engine sentry `tests/sentry/test_file_access_entry_points.py` builds its set from `__all__` and skips `_`-prefixed modules, so it never sees them.
- Differs: nothing on the CLI. A platform process that called `forbid_ambient()` would fail closed on them, and they cannot take `file_access=`. Whether they reach `current()` was read from the shared `run_generation`, not traced call by call.

### A13 ED-4: `pd.to_datetime(errors="coerce")` on mixed offsets
- Mark: LATENT (RUN on the pinned stack; the census failure did not reproduce)
- Sites: `E:profiling/_date_sniff.py:31` (every string column, from `profiler.py:250`); `E:profiling/_distributions.py:70` (only when `inferred_type == "date"`).
- Path: the pin is pandas 2.3.3 (engine `pandas>=1.5.0,<3`; CLI `requirements-certified.txt` `pandas==2.3.3`); the census saw the raise on 3.0.5. `decoy scan` and `decoy fit` reach `_date_sniff.py:31`; `_distributions.py:70` is not reachable with mixed offsets (the column stays object, inferred "string" or "mixed").
- Differs: nothing wrong in output. `fit` prints a pandas FutureWarning twice to stderr; `date_min`/`date_max` are correct instants in their original offsets. A pandas 3 upgrade hazard.

### A14 EX-2: legacy distribution sampler shares the `"np"` stream with the null mask
- Mark: LATENT (READ)
- Sites: `E:generators/_distribution.py:65,141,266,386`; null mask `E:generators/columns.py:219-221`; dispatch `columns.py:119`.
- Path: none. `ColumnGenerator.generate_column` has no caller in either repo's `src/`; `type: distribution` routes to `E:generation/kinds/_parametric.py` through `E:generation/synthesize.py:343` on the `"dist"` family; the legacy sampler needs a `snapshot` key the config schema does not allow (`E:config/_generate_options.py:382`).
- Differs: nothing for a user. The draw-site catalog entries for the legacy sampler (`E:execution/native/protocol/providers_gen.py:46`, `_draw_sites_gen.py:207`) are not wired to any path; per REMEDIATION.md the action is delete.

### A15 ED-1: chunked `when` guard refuses `large_string`
- Mark: REACHABLE-DEFECT (RUN)
- Sites: guard `E:execution/_chunked_when_guard.py:66` (`is_string or is_null`), installed at `E:execution/_chunked_oracle.py:208-222`; admission treats both as equal at `E:execution/native/_dispatch.py:500` and `E:execution/native/_when_admission.py:245-251`.
- Path: `decoy run cfg.yaml --chunked --chunk-size 2`, parquet source with text stored as `large_string` (`ParquetFile.iter_batches` restores it from the file schema), column `c` with `strategy: categorical`, a `when` such as `keep == 'A'`. A non-deterministic faker with `when` hits the same guard. CSV arrives as `string`, so only parquet reaches it from the CLI.
- Differs: the `string` copy runs; the `large_string` copy is refused with `chunked_categorical_nondeterministic_when_not_supported` and a per-chunk widening reason that does not apply to `large_string`. Without `--chunked` the same file runs. Fails closed; no wrong output.

### A16 ED-3: bool columns get numeric stats
- Mark: LATENT (RUN)
- Sites: `E:profiling/profiler.py:210` (typed "boolean"); `:235-238` (min, max, mean set because bool is numeric); `E:profiling/sentinels.py:138`.
- Path: `decoy scan t.csv --has-header` with a `True`/`False` column reaches it, but no CLI output carries the stats: `scan` shows `Type boolean`, `scan --output` writes dtype, null rate, distinct count and PII only, `fit` uses the profile for sensitivity names. Sentinels never fire (0.0 and 1.0 are not sentinels).
- Differs: only in the library `ColumnProfile` (`min_value="False"`, `mean_value="0.6667"`).

### A17 EN-6: `_find_table` without an `isinstance(tbl, dict)` guard
- Mark: LATENT (RUN)
- Sites: `E:execution/native/_plan.py:405-409`, called at `:242` and from `E:execution/native/_dispatch.py:263`.
- Path: none. A non-dict `tables` entry (`- foo`, `- null`, `- 5`) is refused by config validation in `validate config`, `run` and `run --chunked` ("Input should be a valid dictionary or instance of TableConfig (tables[1])") before engine code runs.
- Differs: only a library caller passing a raw unvalidated dict gets `AttributeError`.

## Package B (CLI)

### B1 CC-5: `demo` vs `run` exception-to-exit map
- Mark: LATENT (READ)
- Sites: `C:cli/demo.py:587-591`; `C:cli/run/_errors.py:140-196`; `C:cli/fit.py:663`, `:724`; `C:cli/gate/_layers.py:357` (`gate_exit_code`, works on findings).
- Path: `demo` builds a fixed config (one CSV source, one CSV target at absolute paths under `--dir`, `demo.py:77-130`); the `run`-only exception types (layout, target format, resources, cloud, native gate, mask secret, pre-run check) cannot arise from it. `--ref` prints "deferred" and returns 1.
- Differs: nothing reachable; an out-of-memory failure on the 6-row sample would exit 5 in `run` and 3 in `demo`, which is theoretical. The `fit` and gate maps are not copies of the same map.

### B2 CC-4: `demo`'s own loader and writer
- Mark: LATENT (READ)
- Sites: `C:cli/demo.py:266`, `:280` (`check_target_formats` at `:284`, after masking); `C:cli/run/_execute.py:152`, `:182` (checks at `:166-167`, `:193-194`).
- Path: the skipped checks refuse cloud endpoints and suffix/format contradictions; demo's generated config has neither, and `--dir` is its only input.
- Differs: nothing reachable.

### B3 CX-4: literal `typer.Exit(1)` in the global handler
- Mark: IDENTICAL (READ)
- Sites: `C:__main__.py:165`; guard regex at `tests/unit/test_exit_codes.py:61` misses the positional form.
- Differs: nothing; 1 equals `EXIT_USAGE`. Side note: uncaught crashes exit 1 (usage), not 3 (runtime); see B5.

### B4 CX-8: installer download without a timeout
- Mark: LATENT (READ; single-behavior item)
- Sites: `C:distribution/installer.py:228-232` (default at `:461`); `C:cli/upgrade.py:56` (`timeout=30`).
- Path: the only `src/` caller of `install_version` is `C:cli/upgrade.py:163`, which always passes `download=_fetch`; `first_install.py` does not download.
- Differs: nothing a CLI user reaches.

### B5 CX-2: non-UTF-8 config file
- Mark: REACHABLE-DEFECT (RUN; `report vault` READ)
- Sites: `C:cli/tokenize.py:202`, `:546`, `C:cli/unmask.py:156`, `C:cli/report.py:2255`, `C:cli/preflight.py:704`, `C:cli/subset.py:158`, `C:cli/gate/_layers.py:97` (all catch `YAMLError` only); `C:cli/run/_prepare.py:56-58` (catches it, surfaces it as a runtime error by design); `C:cli/compile_explain.py:177-181` (catches it).
- Path: `printf '\xff\xfe\x00bad: 1\n' > bad.yaml`, then each command.
- Differs:

| Command | Exit | Output |
|---|---|---|
| `validate`, `validate config`, `validate preflight`, also `--json` | 1 | "internal error (UnicodeDecodeError)" and the `--verbose` hint; no `--json` envelope |
| `tokenize --vault v.json`, `unmask`, `subset --dry-run` | 1 | same |
| `run` | 3 | the codec message |
| `run --json` | 3 | error envelope on stdout with the codec message |
| `compile_explain` (read) | 1 | "could not read <path>: UnicodeDecodeError" |

`report vault` shares the `unmask` code; `detokenize` shares `tokenize.py:546`. The census expected a usage error; the real outcome is a crash report in six commands and a runtime exit in `run`.

### B6 CC-2: error line in `--quiet`
- Mark: REACHABLE-DEFECT (RUN for scan, READ for gen)
- Sites: `C:cli/scanning/_multi.py:216-224` (only the hint is gated); `C:cli/gen/_scaffold.py:164-176`.
- Path: `decoy scan 'd[v2].csv' --quiet` printed "error: d.csv: say whether the first row is a header.", exit 1.
- Differs: other commands print nothing in quiet mode (`tokenize.py:195`, `unmask.py:150`, `fit.py:420`). The `--quiet` help says "Errors still go to stderr", so scan and gen follow the help; the fix direction is a C1 decision.

### B7 CC-2: error text printed with Rich markup on
- Mark: REACHABLE-DEFECT (RUN)
- Sites: `C:cli/fit.py:423`, `C:cli/scanning/_multi.py:222`, `C:cli/reference.py:264`. The other `reference.py` messages hold fixed text only (LATENT).
- Path and runs: `decoy scan 'd[v2].csv'` drops `[v2]`; `decoy show schema '[x]'` prints `(got '')`; `decoy fit a.csv --epsilon 1 --delta 1e-6 --dp-number 'a[v2]:0:5:9'` prints `got 'a:0:5:9'`.
- Differs: Rich removes a `[tag]` starting with a letter, `#`, `/` or `@`; `tokenize`, `unmask`, `report` and `run` pass `markup=False` and show it. `--json` is unaffected.

### B8 CE-1: hard-coded secret-ref prefixes vs engine `parse_ref`
- Mark: REACHABLE-DEFECT (RUN for the predicate and the engine parser, READ for the guard path)
- Sites: `C:_mask_secret.py:35` (`_REF_PREFIXES`), `:61-62` (case-sensitive `startswith`); `C:cli/run/_prepare.py:199-226` (guard, called at `:241`, `:264`); `C:api.py:108` (called at `:446`); `E:secret_providers/_types.py:94-128` (`parse_ref` lower-cases the scheme).
- Path: `global_settings.mask_secret_ref: "ENV:MY_SECRET"` or `--mask-secret Env:X` with `decoy run` or `tokenize`.
- Differs: the CLI refuses with its usage message; the engine would accept. RUN: `ENV:FOO`, `Env:FOO`, `acme:x` are all refused by the CLI predicate and all parse in engine 0.22.0.
- Side finding (READ): the gate and `decoy validate` have no mask-secret check and the engine schema takes any string, so a malformed ref passes `validate` and is refused only at `run`, exit 1.

### B9 CX-5: `CI` and SMTP port environment handling
- Mark: REACHABLE-DEFECT (RUN)
- Sites: `C:_update_check.py:48`; `C:cli/run/_notify.py:135`.
- Path: `CI=false decoy <cmd>` in a terminal; `DECOY_NOTIFY_SMTP_PORT=abc decoy run p.yaml --notify webhook:https://...`.
- Differs: `CI=false` counts as CI and hides the update notice (advisory only). The SMTP config is built before dispatch for every channel, so a bad port drops webhook and Slack notifications too, with "notify dispatch failed: invalid literal for int() with base 10: 'abc'". Run exit code unchanged (`except Exception` at `_notify.py:151`).

### B10 CX-11: `str(uuid4())` in `build_manifest`
- Mark: LATENT (READ)
- Sites: `C:cli/evidence.py:395`; owner `C:cli/io/_layout.py:387` (`mint_invocation_id`).
- Path: the only `src/` caller, `C:cli/run/_evidence.py:37`, passes `ctx.invocation_id`, set once by `mint_invocation_id()` in `C:cli/run/_flow.py:23-25`; tests are the only `None` callers.
- Differs: nothing a CLI user reaches.

### B11 CX-8: no scheme check on notify targets and `upgrade --url`
- Mark: REACHABLE-DEFECT (RUN; single-behavior item, hardening only)
- Sites: `C:notify.py:254`, `:319` (`urlopen`); `C:notify.py:119-140` (`parse_notify_spec`); `C:cli/run/_notify.py:67-90` (`parse_channels`); `C:cli/upgrade.py:56`, `:95-98` (hidden `--url`).
- Path: `decoy run p.yaml --notify webhook:file:///path` or `slack:file:///path`; `decoy upgrade --url file:///dir/version.json`. No scheme check in the parsers, `_prepare.py` or config validation.
- Differs: notify opens the local file, then fails with a TypeError and reports "unexpected error"; nothing is sent and the run exit code is unchanged. `upgrade` reads the local file (and `<url>.sig`), but the version document must verify against the pinned release key and the bundle against its digest and signature, so the scheme gives no bypass; `http://` is also accepted.

## Notes for the remediation rows

- A11's census claim ("fails only on the large route") is wrong: `_compat.py` refuses a self-FK before routing. The `_table_order` self-edge handling can go with the V1+ `topo_order` refactor (package L).
- A13 is a pandas 3 hazard, not a V1 defect on the pinned 2.3.3.
- A2, A4 (`providers_gen.py`), A14 and the A12 entries point at code with no production caller; REMEDIATION.md's hard-delete actions apply.
- A5 and B5 share a cause: a `UnicodeDecodeError` reaching the global handler. `run` reports it as a runtime error by design (`_prepare.py:51-53`); `validate` reports a crash.
- B8's side finding (no mask-secret check in the gate) is a validate/run mismatch beyond the duplication item.
