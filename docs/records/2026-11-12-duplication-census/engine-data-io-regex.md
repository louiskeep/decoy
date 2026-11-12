# Engine primitive call census, slice b2: triage

Repo /home/user/decoy-engine, paths relative to src/decoy_engine. Input: census/in/engine_calls_b2.txt.
Only what I read in code is stated as fact. "Sampled" counts are sites whose surrounding code I read.
Existing guard tests looked at: tests/sentry/{test_private_files, test_pandas_eval_sites, test_log_interpolation,
test_null_fraction_single_source, test_outbound_clients, defects/test_anchored_regex, file_access_registry.toml}.
No sentry covers pyarrow.types predicates, null predicates, dtype-kind inference, date parsing, env reads or finite checks.

Order by value:
ED-1 Arrow text/key type predicates, ED-2 null-cell predicate, ED-3 pandas dtype to column kind, ED-4 lenient date parse,
ED-5 finite-real / epsilon validation, ED-6 env var reads, ED-7 fresh-seed fallback, ED-8 wall-clock stamps,
ED-9 numexpr-fallback capture, ED-10 regex, ED-11 filesystem/process, ED-12 logger, ED-13 concurrency, ED-14 elapsed timing, ED-15 not examined.

---------------------------------------------------------------------------------------------------

## ED-1  "Is this Arrow type a string / key-able type"  (pyarrow.types.is_string, is_large_string, is_integer, is_null, is_timestamp, is_floating, ...)
Verdict: CENTRALIZE (the text family first; the rest of the family set as a second step)
Sites: is_string 26 calls / 21 files / 7 packages; is_large_string 26 / 21 / 8 (same sites, always paired); is_integer 34 / 23; is_null 23 / 18; is_timestamp 17 / 12; is_floating 18 / 14; is_boolean 10 / 8; is_dictionary 12 / 7; binary-family 6-10 each.
Sampled: all 22 string sites read (3 lines of context each); admission bodies of _key_width, _external_sort_bounding, _batch_join:515-550, _chunked_fk_dtype_safety:105-140, _planner:480-520, _when_admission:238-258 read in full.
Existing owner: none shared. Two private helpers exist and are used only locally: execution/_chunked_profile.py:248 `_is_string_type` (string or large_string) and execution/_mem_estimate_arrow.py:100 `_is_string_family` (string, large_string, string_view, binary, large_binary, binary_view).

Variants of "is text":
 a. `is_string or is_large_string` written inline (about 19 files): declared_casting/_boundary.py:433, declared_casting/_eligibility.py:247, execution/_chunked_fk_dtype_safety.py:116, _chunked_group_key.py:199, _mixed_admission.py:136, _mixed_fk_bridge.py:114, native/_chunk_masking.py:308, native/_dispatch.py:500, native/_faker_null_mask.py:40, native/_when_admission.py:249, out_of_core/_batch_join.py:533, out_of_core/_key_width.py:88, physical/_shadow_bindings.py:184, generation/_streamed.py:272, generation/window.py:247, plan/_checks_correctness.py:84.
 b. helper-wrapped, same rule: _chunked_profile.py:249.
 c. string only (large_string refused): execution/_chunked_when_guard.py:66 (`is_string(typ) or is_null(typ)`).
 d. widest family incl. string_view and binary: _mem_estimate_arrow.py:102-107. string_view is handled in only three places (_mem_estimate_arrow, _chunked_profile.py:227 normalize, verification/canary/_canonical.py:183); every admission predicate in (a) rejects or ignores string_view.
 e. text-or-null: native/_chunk_masking.py:308-310 (adds is_null); _chunked_when_guard:66.
 f. text-or-binary key allowlist, repeated three times with different subsets: out_of_core/_key_width.py:81-92 (`_boundable_value_type`: includes bool, null, decimal, temporal, fixed binary), _external_sort_bounding.py:66-75 (`_is_supported_key_type`: integer, text, binary, date, timestamp; excludes float and bool), _batch_join.py:523-545 (round-trip image table).
 g. "integer with nulls is unstable, everything else listed is fine" lists: _planner.py:486-500 vs native/_when_admission.py:246-253 vs _chunked_fk_dtype_safety.py:118-137. Same families, different membership (planner admits boolean/temporal/null, when_admission admits date32/date64/timestamp but not time/duration, fk_dtype_safety admits only tz-aware timestamp and refuses date64). Each has a comment explaining its own reason, so these look deliberate, not drift.
Inconsistency / candidate bug (not proven): execution/_chunked_when_guard.py:66 accepts only `string`/`null` per chunk and raises a coded PlanCompileError otherwise, while native/_dispatch.py:500 and _when_admission.py:249 treat `large_string` as equal to `string` for the same positional-faker/when columns. A chunk typed large_string would pass admission and then be refused by the guard. It fails closed, and the docstring says "string", so it may be intentional; I did not trace whether a reader can produce large_string there. UNVERIFIED reachability.
Proposed choke point: `decoy_engine/_arrow_types.py` (leaf, imports only pyarrow) with `is_text(t)` (string, large_string; one documented place to add string_view), `is_text_or_null(t)`, `is_binary_like(t)`, `is_variable_width(t)`, and `unwrap_dictionary(t)`. Keep the per-route admission tables where they are; only the family membership moves.
Guard: sentry (AST scan, ratchet baseline like `baselines/*.json`) forbidding `pa.types.is_string`, `is_large_string`, `is_binary`, `is_large_binary` calls outside `_arrow_types.py`; allowlist the ~6 sites that intentionally differ (_mem_estimate_arrow, _scan_integrity, _key_width width math) with reasons.
Size: M (about 21 files for the text family; the integer/null/timestamp predicates are not worth converting, no variant disagreement seen).

---------------------------------------------------------------------------------------------------

## ED-2  "Is this cell null / missing"  (pandas.isna 20 calls / 17 files / 10 pkgs; math.isnan 5 / 5 / 5)
Verdict: CENTRALIZE
Sampled: 12 isna sites, all 5 isnan sites, and the 5 private helpers below.
Existing owner: none. Five private helpers re-implement it:
 - kernel/_scalar.py:14 `_is_missing`: None, then `value != value`, then falls back to `pd.isna` (covers NaN, Decimal NaN, pd.NA).
 - quality/carrier_adapter.py:194 `_is_null`: `pd.isna`, accepts only a 0-dim result (array-valued cell is present), exceptions mean "present".
 - transforms/derived.py:208 `_is_null`: None or float NaN only. pd.NA, pd.NaT, Decimal NaN, np.float32 NaN are NOT null here.
 - transforms/windowed_date.py:209 `_is_null_cell`: None, NaT, NA, or float NaN (is-checks plus `raw != raw`).
 - profiling/profiler.py:76 `_is_null_like`: None, then `pd.isna` in try/except (TypeError, ValueError); array cell would hit bool() ambiguity only via ValueError.
Inline variants: execution/_pandas_adapter.py:656, _strategies/_date_shift.py:275, _nested.py:322, _tokenize.py:136, _top_code.py:325, transforms/formula.py:57, profiling/sentinels.py:104 (bare `pd.isna(x)`, no try); generators/_formula.py:206 `val is None or (isinstance(val, float) and pd.isna(val))` (pd.NA and NaT are not counted as null there); execution/_fk_keys.py:97 `math.isnan` after an isinstance float check, :356 `pd.isna` in try/except (TypeError, ValueError) with a comment that array-likes make bool() raise; profile/_fixed_width_writer.py:107 and quality/carriers.py:181 `isnan` are numeric-domain checks, not cell-null.
Inconsistency (read at the line): derived.py:212 and generators/_formula.py:206 treat pd.NA / NaT as non-null while kernel/_scalar.py:14 explicitly says pd.NA must count as missing, citing a real divergence (C6a). Whether a nullable-dtype cell can reach derived.py:208 or the formula generator I did not trace. UNVERIFIED reachability; the definitions do disagree.
Proposed choke point: `decoy_engine/_cells.py` (or kernel) with `is_null_cell(v)` (None, float/Decimal NaN, pd.NA, pd.NaT; array-valued is not null; never raises, KeyboardInterrupt propagates) and `null_mask(series)`; sentry forbidding `pd.isna(` / `pd.notna(` on scalars and `x != x` outside it (series-level `.isna()` stays).
Size: M (about 15 scalar sites + 5 helpers).

---------------------------------------------------------------------------------------------------

## ED-3  "Infer a column kind from its pandas dtype"  (pandas.api.types.is_* : integer 6, bool 6, datetime64_any 5, string 6, numeric 5, object 3, extension_array 10)
Verdict: CENTRALIZE (small, because one copy is literal)
Sampled: profiler.py:204-218, 232-247, 262-267; features/builder.py:118-134; quality/snapshot.py:272-316; profile/_walk.py:180-188; sentinels.py:130-141; quality/_dcr.py:170-176. The 10 is_extension_array_dtype sites in strategies/transforms/native were NOT read: UNVERIFIED.
Existing owner: none.
Variants:
 - profiling/profiler.py:208-218 chain: datetime, bool, integer, float, string, else "mixed".
 - profiling/features/builder.py:120-132 `_infer_type`: docstring says "same mapping the profiler uses inline"; a verbatim copy of the chain. Drift risk, no shared function.
 - quality/snapshot.py:278-285: a different taxonomy (bool to categorical, numeric, datetime, else by distinct count), bool tested first because `is_numeric_dtype(bool)` is True.
 - profiling/profiler.py:235 and profiling/sentinels.py:138: `is_numeric_dtype` without excluding bool, after the same files classify bool separately (profiler.py:210). A bool column gets min/max/mean numeric stats (profiler.py:235-238) while its inferred type is "boolean"; sentinels run `_scan_numerics` on bool columns. Effect on output not tested: UNVERIFIED.
 - quality/snapshot.py:310-313 allow-list for high-cardinality uses `is_object_dtype or CategoricalDtype or (is_string_dtype and not is_object_dtype)`.
Proposed choke point: `profiling/_classification.py` (already holds column-shape helpers) gains `infer_type_label(series)`; builder.py and profiler.py call it. Guard: unit test that both call sites import it (or sentry forbidding `is_datetime64_any_dtype` + `is_bool_dtype` in the same function outside it).
Size: S (2 duplicated chains; snapshot.py's taxonomy differs on purpose).

---------------------------------------------------------------------------------------------------

## ED-4  "Parse a cell/column as a date"  (pandas.to_datetime 18 calls / 12 files / 7 pkgs; datetime.fromisoformat 7; date.fromisoformat 3; strptime 7)
Verdict: CENTRALIZE (two narrow helpers)
Sampled: 14 of 18 to_datetime sites, all 8 fromisoformat sites.
Existing owner: `internal/pandas_compat.py:46 utc_naive_datetimes` (coerce, dropna, tz to naive UTC) is used by generation/statistical/_cell_format.py:136 and quality/snapshot.py:492 only.
Variants of lenient (no format) parsing, `errors="coerce"`:
 - profiling/_date_sniff.py:25-31: wrapped in `warnings.filterwarnings("ignore", "Could not infer format")`.
 - profiling/_distributions.py:70, profiling/sentinels.py:116, validators/_relationship_checks.py:142,143,152: same call, no warning filter, no tz handling.
 - internal/pandas_compat.py:52: the tz-normalizing version above.
Variants of formatted parsing (same settings, `format=fmt, errors="coerce"`): execution/_strategies/_date_shift.py:260, native/_date_shift_ext.py:194, native/_bucket_perturb_ext.py:101,273, transforms/date_shift.py:191, bucket_perturb.py:172, date_preserve.py:173. These agree with each other and say they mirror each other (docstrings); fine.
fromisoformat with "Z" shim: `datetime.fromisoformat(v.replace("Z", "+00:00"))` at _reference_date.py:37 (guarded, coded error) and generation/_pinned_compile.py:196 (unguarded); NO shim at generation/_window_admission.py:177, statistical/_sample.py:503-504, profile/_serialize.py:153. The project runtime is Python 3.10 per CODEMAP, where fromisoformat rejects a trailing "Z". Snapshot min/max written via utc_naive_datetimes are naive, so the missing shim is probably unreachable for engine-written snapshots; a hand-authored snapshot with "Z" would raise in _sample.py (uncoded ValueError) and be refused with a code in _window_admission. UNVERIFIED end-to-end.
Likely bug: profiling/_distributions.py:70 `pd.to_datetime(non_null, errors="coerce").dropna()` then `.dt.year`: with a column of ISO strings with mixed UTC offsets pandas raises (I ran the bare `pd.to_datetime(Series(['...+01:00','...+05:00']), errors='coerce')` on the installed pandas 3.0.5: `ValueError: Mixed timezones detected`). profiling/_date_sniff.py:31 (`sniff_dates`, called from profiler.py:250 on every string column) makes the same call with no try. I could not run `profile_columns` end to end (lark not installed), so whether a profile of such a column crashes is UNVERIFIED. pyproject pins pandas below 3, whose behavior for mixed offsets differs (not tested).
Proposed choke point: `internal/pandas_compat.py` gains `coerce_datetimes(series, *, fmt=None)` (suppresses the infer-format warning, handles mixed tz via utc=True, returns tz-naive UTC) for the 6 no-format sites, and `parse_iso_instant(text)` (Z shim, aware result) for the 5 fromisoformat sites. Guard: sentry forbidding `pd.to_datetime(` without `format=` and `.fromisoformat(` on possibly-Z strings outside pandas_compat.
Size: S (about 7 + 5 sites).

---------------------------------------------------------------------------------------------------

## ED-5  "Is this a finite real number" / epsilon-delta validation  (math.isfinite 46 calls / 24 files / 12 pkgs)
Verdict: CENTRALIZE (narrow: finite real, bool excluded, with one named validator for DP knobs)
Sampled: 12 of the 24 files (config/_generate_type_checks, config/_generate_options, _progress_events, plan/_checks_dp x4 sites, plan/_checks_dp_carrier, quality/dp x3, dp_session, telemetry/_vocab, phase, generation/_window_admission, profiling/_value_redaction, expressions/_when_parser).
Existing owner: quality/dp.py:206 `_is_finite_real` (int or float, not bool, finite): private, used inside dp.py.
Variants of the type gate:
 - `isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)`: quality/dp.py:206 helper; plan/_checks_dp.py:111-121 and :522-532 repeated inline four times (epsilon >0, delta in [0,1), totals >=0).
 - `type(x) is float` / `type(x) is int` then isfinite: config/_generate_options.py:222-223, config/_generate_type_checks.py:54, telemetry/_vocab.py:101.
 - `isinstance(value, (int, float))` with no bool exclusion: _progress_events.py:48-50.
 - coercing validator: quality/dp.py:150 `epsilon = float(epsilon)` then `isfinite` and `> 0`.
Inconsistency (read at the lines): the config-time check plan/_checks_dp.py:111-114 refuses `epsilon=True`, but the runtime validator quality/dp.py:148-163 (`_validate_fit_params`) coerces with `float()` first, so `True` becomes 1.0 and a numeric string such as "0.5" becomes 0.5 and both pass. The same knob has two acceptance rules. Whether the public fit entry is reachable with such input without passing the plan check first: UNVERIFIED. _progress_events.py:48 also lets `True` pass as a count of 1 (low impact, not traced).
Proposed choke point: `decoy_engine/_numbers.py` `is_finite_real(v)` plus `dp` knob validators `parse_epsilon`, `parse_delta` returning the value or a reason; plan and quality call the same one. Guard: sentry forbidding `math.isfinite(` inside `isinstance(..., (int, float))` expressions outside `_numbers.py`; DP validators single-sourced like test_reason_policy_single_source.
Size: M (about 12 sites to convert; the other ~30 isfinite calls are numeric-domain checks on computed floats and are fine).

---------------------------------------------------------------------------------------------------

## ED-6  Environment variable reads  (os.environ.get 8 calls / 5 files / 4 pkgs; os.getenv 1; direct `os.environ` 2)
Verdict: CENTRALIZE (small)
Sampled: all 9 sites.
Existing owner: none for flags. secret_providers/_local.py:79 reads an env var by caller-supplied locator through the secret-provider contract (legitimate, separate). Vault takes `environ` mapping as a parameter (vault.py:83).
Variants:
 - profiling/model_pack/loader.py:90 `DECOY_PACK_REQUIRE_SIGNATURE`: default "0", `.strip().lower()`, truthy {1,true,yes,on}, falsy {0,false,no,off,""}, anything else raises ModelPackLoadError.
 - profiling/model_pack/loader.py:186 `DECOY_ML_DISABLED`: default "0", disabled only when value == "1" exactly. `true`, `yes`, ` 1` do not disable ML, silently. Same package, same style of flag, different parsing.
 - execution/_isolated_run.py:221,238 and :469 `ISOLATED_WORKER_ENV` compared `== "1"` / `!= "1"`.
 - profiling/model_pack/loader.py:351 and provenance.py:282 signing key via SIGNING_KEY_ENV, `.strip()` in one, raw in the other.
 - connectors/sftp.py:138 `DECOY_SFTP_KNOWN_HOSTS` default `~/.ssh/known_hosts`; internal/faker_setup.py:223 `CUSTOM_PROVIDERS_DIR` default "custom_providers" (relative to cwd; no DECOY_ prefix, unlike all the others).
Inconsistency (verified at loader.py:186 vs :90): DECOY_ML_DISABLED=true is ignored.
Proposed choke point: `decoy_engine/_env.py` with `env_flag(name, default=False)` (the strict token set of loader.py:57-58), `env_str`, and a registry of the DECOY_* names with docs; sentry forbids `os.environ` / `os.getenv` outside `_env.py`, `secret_providers/`, and the isolated-worker env builder.
Size: S (9 sites).

---------------------------------------------------------------------------------------------------

## ED-7  "Fresh seed when the spec has none"  (os.urandom 8 calls / 3 pkgs)
Verdict: CENTRALIZE (tiny)
Sampled: all 8 sites. Six are the identical line `seed = spec.seed if spec.seed is not None else os.urandom(8)` in generation/composite/{_address.py:181, _person.py:239, _provider.py:204, _custom.py:280, _name_email.py:221, _city_state_zip.py:124}, each followed by `PoolSampler().sample_bundle(...)`. The other two are different jobs (generators/derivation.py:275 root key of 32 bytes; secret_providers/_types.py:40 process salt of 32 bytes).
Existing owner: none; a determinism package exists (`determinism/`) and `_reproducibility.py` lists "fresh" as an exclusion from pinned runs, so the unseeded path is a named concept.
Proposed choke point: `determinism/` gets `fresh_seed()` (documented, single place that may call os.urandom for sampling); sentry forbids `os.urandom` outside determinism/, secret_providers/ and fileaccess/. Also worth noting: np.random.default_rng() without a seed appears in providers_v2/identifiers/_cusip.py:197,206 and _ein.py:207,216 (found while grepping; not in this slice, not read further).
Size: S (6 sites).

---------------------------------------------------------------------------------------------------

## ED-8  Wall-clock timestamps  (datetime.now 4 calls; plus time.time and utcnow found by grep)
Verdict: CENTRALIZE (small, low value)
Sampled: all 4 datetime.now sites and the grep extras.
Variants: `datetime.now(timezone.utc)` in profile/_source.py:169 (datetime object), profiling/scan_set.py:283, quality/report.py:257 and verification/postmask/runner.py:167 (`.isoformat()`, gives "+00:00"); profiling/types.py:193 `datetime.utcnow().isoformat() + "Z"` (naive then "Z" appended, "Z" suffix, `utcnow` deprecated from Python 3.12); generators/columns.py:74 `pd.Timestamp.utcnow()`; profiling/sentinels.py:176 `date.today()` (host-local date, used as "today" for DOB range checks; note generation has a pinned reference-date concept in _reference_date.py that this does not use). quality/report.py takes `now_iso` injection; others cannot be pinned by tests.
Inconsistency: two string shapes for "generated at" across reports ("...+00:00" vs "...Z"), one of them from a deprecated call. Whether a consumer parses both: UNVERIFIED (run_result/_model.py:125 defines `UtcTimestamp`; I did not read its pattern).
Proposed: `decoy_engine/_clock.py` `utc_now()` / `utc_now_iso()` with test override; sentry forbids `datetime.now`, `utcnow`, `date.today`, `Timestamp.utcnow` elsewhere.
Size: S (6 sites).

---------------------------------------------------------------------------------------------------

## ED-9  Capture of numexpr's python-engine fallback around `df.eval`  (warnings.catch_warnings 11 calls; simplefilter 10)
Verdict: CENTRALIZE (one duplicate pair); the other warnings uses are FINE
Sampled: all 7 catch_warnings files.
Duplicate pair: execution/_transforms.py:82-91 (`_eval_clamped`) and execution/_when_gate.py:145-163 both run `catch_warnings(record=True)`, `simplefilter("always", RuntimeWarning)`, `eval(engine="numexpr", local_dict={}, global_dict={})`, then log each RuntimeWarning with the expression withheld. The second comment says it copies the first. Eval call sites are already pinned by tests/sentry/test_pandas_eval_sites.py, so the choke point is half there.
Others (FINE, unrelated reasons): detection/ner.py:184 ignore all around get_model_meta; generation/_pinned_execute.py:185 ignore FutureWarning around pandas option_context; quality/carrier_adapter.py:221-249 and carriers.py:163-235 ignore all around cell fetch/float coercion; profiling/_date_sniff.py:25 (see ED-4). `warnings.warn` (5 sites: _pipeline_routing_signals.py:201, internal/crypto.py:30, profile/_source.py:132,216, transforms/date_shift.py:94) are user-facing advisories; no shared rule, though the engine's own channel is QualityWarning (a different mechanism).
Proposed: `execution/_eval.py` `eval_numexpr(df, expr, *, on_fallback)` used by both; test_pandas_eval_sites audited-site list shrinks by one.
Size: S (2 sites).

---------------------------------------------------------------------------------------------------

## ED-10  Compiled regex  (re.compile 116 calls / 43 files / 28 pkgs; re.fullmatch 6)
Verdict: ALREADY-OWNED for the safety rule (end anchors: tests/sentry/defects/test_anchored_regex.py via defects/_defect_scan.py, no pattern ends with `$`). The patterns themselves are domain-specific and FINE, with two small duplicates.
Sampled: detection/_patterns.py (24 patterns), detection/detectors.py:210-265, profiling/features/builder.py:92-102, data_discovery.py:38-80, quality/_freetext_names.py:36-76, profiling/sentinels.py:84-111, plus a grep for duplicates.
Stragglers:
 - Header camelCase split: profiling/features/builder.py:97 `_CAMEL_1` and quality/_freetext_names.py:40 `_CAMEL_BOUNDARY` are the same pattern `(?<=[a-z0-9])(?=[A-Z])`; builder.py also tokenizes with `_HEADER_SPLIT` (`[\s_\-./]+`). Two header tokenizers.
 - US ZIP: detection/_patterns.py:36 `_US_ZIP_RE` and detection/detectors.py (`_US_ZIP_VARIANTS` second entry) repeat the same lookaround rule; the detectors.py comment states it was copied ("same non-word boundary protection").
 - ISO-date shape defined three times with different meaning under one name `_ISO_DATE_RE`: detection/_patterns.py:41 (compact 8-digit allowed, optional Z), profiling/sentinels.py:89 (1-2 digit month/day, trailing text allowed). Name collision only; no sharing expected.
Proposed (optional): move the header tokenizer to one module (S, 2 sites). No guard needed beyond the existing one.

---------------------------------------------------------------------------------------------------

## ED-11  Filesystem and process calls  (os.open/close/fdopen/fsync/fchmod/replace/unlink/scandir/dup/fstat/fspath/strerror/abspath/path.join, shutil.rmtree 16, builtins.open 6, tempfile, parquet write_table 5, read_table 3, read_metadata 4)
Verdict: ALREADY-OWNED by `fileaccess/` (FileAccess policy, `_protected_dir.py`, `_private.py`, `_output.py`, `_local.py`, `_rooted.py`) with tests/sentry/file_access_registry.toml (1836 lines, one row per sink including os.replace and shutil.rmtree), tests/sentry/fa/ scan, test_private_files.py and baselines/private-file-sinks.json, test_file_access_boundary.py.
Sampled: os.replace x3 outside fileaccess (connectors/postgres_snapshot.py:520, execution/_isolated_commit.py:81, declared_casting/_quarantine_local.py:357), rmtree x5 (execution/_isolated_run.py:540, out_of_core/_runner.py:326, _stream_driver.py:561, postgres_snapshot.py:536, fileaccess/_protected_dir.py:161), private-file baseline entries.
Stragglers (all present in the file-access module/registry lists, i.e. known, not unguarded): the directory publish via `os.replace` in postgres_snapshot and _isolated_commit; fsync-parent-dir pattern repeated in declared_casting/_quarantine_local.py:357-360 and fileaccess/_local.py:191; `rmtree(ignore_errors=True)` cleanup at 6 sites outside fileaccess; staged isolated-worker files written at the umask (baseline entries _isolated_run._write_payload, _isolated_worker._stage_outputs, with reason text saying "V1 found, out of scope (X7b)"). tempfile: the only uses outside fileaccess are docs and `tempfile.gettempdir()` in out_of_core/_spill_estimate.py:153,528.
Not checked: whether every one of the 16 rmtree and 4 read_metadata sites has its own registry row (spot-checked sinks, not each site). UNVERIFIED per site.

---------------------------------------------------------------------------------------------------

## ED-12  Logger setup  (logging.getLogger 38 calls / 38 files / 16 pkgs)
Verdict: FINE
Sampled: all 38 declarations (grep).
33 use `getLogger(__name__)`. Literal names: fileaccess/_local.py:36 "decoy_engine.quarantine"; detection/_model_status.py:35 `getLogger("decoy_engine").getChild("detectors")` (comment: to dodge the string-target sentry); execution/native/_text_mask_native_{fpe,splice}.py:43,49 "decoy_engine.transforms.text_mask" (shares the logger of the module it mirrors); internal/logging.py:75 configures the "decoy_engine" logger; `__init__.py:56` adds the single NullHandler. Variable name varies (`_log`, `_LOG`, `_logger`, `logger`): cosmetic. Log content is already guarded by tests/sentry/test_log_interpolation.py (ratchet).
One oddity: fileaccess/_local.py logs under "decoy_engine.quarantine" though it is the generic local access module. Not a bug.

## ED-13  Concurrency primitives  (threading.Lock 17 / 13 files, threading.local 5, Event 4, contextvars.ContextVar 9 / 7)
Verdict: FINE
Sampled: 8 Lock sites, all 5 threading.local sites, all ContextVar files (grep + 3 read).
Locks guard module or instance caches (model status, model pack, faker providers, secret registry, pool cache, recorder, duckdb recorder): different data, no shared rule. ContextVar holds run-scoped bindings (casting ledger, detector scope, snapshot guard, admission registry, duckdb recorder; fileaccess has run_in_context/bind_iterator to carry them across threads). threading.local holds per-thread Faker instances (synthesize.py:73, transforms/_faker_span.py:21: same idea written twice, S), failure capture (reason_adapter.py:273), timing (instrumentation/timing.py:129) and the progress channel (progress.py:501, documented "bound to this thread"). The progress channel is the one run-scoped binding on threading.local rather than ContextVar, so a worker thread sees the no-op channel; documented, not a defect I can show.

## ED-14  Elapsed-time clocks  (time.perf_counter 41 calls / 13 files; time.monotonic 8 / 4)
Verdict: FINE
Sampled: 10 perf_counter sites, 4 monotonic sites. Convention holds: perf_counter for durations (progress.py, adapters, validators, eval bands), monotonic for deadlines/budgets (pool builder, window.py:294, scan_set.py:269, secret_providers/_types.py:310 which wraps its own injectable clock). Only exception seen: internal/logging.py:209,225,269 uses `time.time()` for elapsed (not in this slice's list).

## ED-15  Not examined in depth
decimal.Decimal (29 calls, 8 files): not sampled beyond the file list. pandas.to_numeric (9 sites, 7 files): every call seen is `errors="coerce"`, call lines only. pyarrow.compute.cast (3), datetime.timedelta/date construction, os.path.* path helpers inside fileaccess: FINE by role, not read. UNVERIFIED.
