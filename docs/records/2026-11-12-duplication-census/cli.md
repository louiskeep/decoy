# CLI duplication and cross-cutting census: triage

Repo /home/user/decoy (src/decoy), engine /home/user/decoy-engine. Paths are relative to src/decoy unless they start with tests/. Everything below was read in the code unless marked UNVERIFIED. I could not run the CLI (typer is not installed in this sandbox), so no runtime behaviour was exercised.
Size: S under 10 sites, M 10-30, L over 30.

## Part A. Clones and same-name functions

Ordered by value.

### CC-1  Raw `mask_secret_ref` shape guard, four copies  -- EXTRACT, S
Sites: api.py:108-125 `_validate_mask_secret_ref_shape`; cli/run/_prepare.py:199-226 `_guard_mask_secret_ref`; cli/tokenize.py:215-231 (tokenize); cli/tokenize.py:557-573 (detokenize). All four do the same two checks (non-mapping `global_settings`, then `_is_valid_mask_secret_ref(ref)`), each in front of `parse_pipeline_config`, because Pydantic echoes `input_value`.
Drift (quoted):
- api.py:122 message ends "It is a REFERENCE, never the raw secret." and has no pointer. _prepare.py:224 and tokenize.py:229 append "See: decoy explain keys."
- The global_settings message differs: api.py:116 "global_settings must be a mapping (key: value pairs), not a ...". _prepare.py:211 and tokenize.py:220 say "(a YAML block of key: value pairs)", and _prepare.py adds "See: decoy explain keys."
- The failure type differs: api raises `MaskSecretConfigError`, _prepare `_MaskSecretUsageError`, tokenize calls `_emit_error` + `typer.Exit(EXIT_USAGE)`.
Home: one function `mask_secret_ref_problem(raw) -> str | None` in `_mask_secret.py` (already "the one mask-secret path the CLI surfaces share", `_mask_secret.py:1`), each caller maps the text to its own error type. This is a secret-leak control, so the next change (a new ref scheme, see CE-1) must not have to find four copies. tests/sentry/test_mask_secret_ref_shape.py tests the behaviour per surface but does not force one implementation.

### CC-2  Per-command `_emit_error` closures  -- EXTRACT, L
SHAPE clones: cli/report.py:2234-2251 and cli/unmask.py:136-153 (76 nodes); cli/tokenize.py:181-197 and :527-541 (73 nodes). Same job in more places (all "if json: emit_json({command,status:error,...}) elif not quiet: err_console.print(error('error:'), msg); hint line"): cli/fit.py:403-425, cli/report.py:1721, cli/scanning/_multi.py:216-224, cli/gen/_scaffold.py:164-176 `_fail`, cli/scan.py:440-470 `_emit_load_error`, cli/reference.py:272-284 and :300-313, cli/subset.py `_fail_usage` (call at :159), cli/compile_explain.py `_simple_error`. About 49 `err_console.print(error("error:")` lines in 23 files and 40 `"status": "error"` payloads in 19 files (grep counts).
Drift (read, each is a behaviour difference between commands):
- Markup: report.py/unmask.py/tokenize.py/_scaffold.py pass `markup=False` (comment at unmask.py:147 says engine text with `[vault]` loses the bracket otherwise). fit.py:~422 `state.err_console.print(error("error:"), f"{prefix}{message}")`, scanning/_multi.py:222 and reference.py:285 do not, so bracketed text can be dropped there.
- Quiet mode: tokenize/unmask/report/fit/reference print nothing when quiet (`elif state.mode is not OutputMode.quiet`). scanning/_multi.py:221-222 and gen/_scaffold.py:171-172 print the error line in quiet mode (only the hint is gated in _multi.py:223).
- JSON shape: fit.py adds `code`/`message`/`error`/`hint` keys; _scaffold adds `hint`; others carry `error` only, and the context key varies (`config`, `vault`, `source`, `scan`, `kind`).
Home: `ui/output.py` (next to `emit_json`, ui/output.py:154) as `emit_error(state, command, message, *, hint=None, code=None, **context)`. See CX-1 for the guard.

### CC-3  YAML load plus "must be a mapping" preamble  -- EXTRACT, S
cli/tokenize.py:201-207 (tokenize) and :545-551 (detokenize), cli/unmask.py:155-162, cli/report.py:2254-2261: identical `try safe_load(config.read_text) / except YAMLError -> sanitize_yaml_error / not isinstance dict -> "Pipeline YAML must be a YAML mapping (object), not ..."`. Part of CX-2.

### CC-4  `decoy demo` re-implements run's source loader and target writer  -- EXTRACT, S
cli/demo.py:266-277 `_load_sources_from_config` vs cli/run/_execute.py:152-179; cli/demo.py:280-288 `_write_mask_outputs` vs cli/run/_execute.py:182-199.
Drift: demo's loader skips `_require_local_io_endpoints(config_dict)` and `check_target_formats(config_dict, chunked=False)` and filters with `isinstance(src.get("path"), str)`, where run uses `_native_gate.source_is_materialized(src)`. Demo's writer returns None, run's returns `dict[str, Path]`. Run's docstring says the format check happens "before the first read"; demo gets it only after masking (demo.py:283).
Home: `cli/io/` (the declared owner of source readers and target writers); both commands import it from the public `decoy.cli.io`.

### CC-5  Exception to exit-code mapping, two copies  -- EXTRACT, S
cli/demo.py:587-591 (`PlanCompileError, PipelineValidationError, ConfigError` -> EXIT_USAGE else EXIT_RUNTIME) vs cli/run/_errors.py:128-156 (same tuple plus `TargetFormatError`, `LayoutError`, `_VaultUsageError`, `_MaskSecretUsageError`, `_OtelSettingsUsageError`, capacity, `GenerationError` unique case). Demo's list is the old subset, so the same config failure can exit 1 in `run` and 3 in `demo`. Also cli/gate (`gate_exit_code`) and cli/fit.py:660-665 hold their own mappings. Home: `cli/exit_codes.py` gets `exit_code_for(exc)`; demo and run call it.

### CC-6  Within-file text clones  -- EXTRACT, S (3 independent items)
- cli/init.py:550-563 and :643-656: "out exists and not --yes -> error / hint / overwrite prompt". A third copy in cli/gen/_scaffold.py:~171-188 `_confirm_overwrite`. Drift: the first copy is guarded by `out_is_stdout = str(out) == "-"` (init.py:547); the second (init.py:~637) relies on an earlier `_template_to_stdout` branch. Same text, so a change to the prompt needs three edits.
- cli/fit.py:658-670 and :718-731: identical `except ProvenanceError / DpBudgetError / (DpError, CarrierError)` chain run once for the request check and once for the snapshot fit. One local helper.
- cli/evidence.py:550-559 and :570-579: input/output fingerprint table rows. cli/reference.py:275-284 and :302-313: the two "show kind needs NAME / no detail view" error blocks. Local helper each.

### CC-7  `_disabled(state)` progress guard  -- EXTRACT, S
ui/progress.py:25-27 and ui/storm_animation.py:155-156: identical body `state.mode is quiet or not state.err_console.is_terminal`. Put it in ui/output.py (as `OutputState.progress_disabled`).

### CC-8  Same name by design  -- INTERFACE, 6 names
`_show` (cli/report.py:1071, cli/scan.py:725, cli/templates.py:72), `_render` (cli/ci.py:70, cli/init.py:74, cli/report.py:651), `_diff` (cli/report.py:1203, cli/scan.py:943), `_scan` (ci/staged.py:274, cli/scan.py:504), `execute` (cli/run/_execute.py:202, cli/run/_flow.py:23: the flow calls the phase), `template_names` (cli/completers.py:101 wraps templates/__init__.py:44 with a try/except for tab completion).

### CC-9  Name collision only  -- BENIGN, 6 names
`render_markdown` (ci/reporting.py:187 CI report, cli/report.py:345 evidence manifest: different documents), `verify_manifest` (cli/evidence.py:484 wraps `verify_manifest_issues`; distribution/manifest.py:156 verifies the bundle), `info` (cli/info.py:30 command, ui/theme.py:45 style helper), `run_pipeline_kwargs` (_native_gate.py:482 native flag; _resources.py:114 thread and memory budget; both are spread into one call at cli/run/_execute.py:252-253, but api.py:534-535 spreads only the native one. UNVERIFIED whether that omission is deliberate), `_parse` (ci/manifest.py:103 YAML manifest, distribution/version_document.py:159 version string), `_score` (cli/scanning/_multi.py:343 one decimal, ui/summary.py:28 two decimals; different displays).

## Part B. Cross-cutting concerns

Ordered by value.

### CX-1  CLI error rendering  -- CENTRALIZE, L
Variants and drift are quoted in CC-2. No owner exists: `ui/output.py` owns `setup_output` and `emit_json` only; tests/sentry/cli_text/test_no_traceback_escape.py guards crashes, not the error line.
Choke point: `ui/output.py::emit_error`. Guard test (new, tests/sentry/cli_text/): no `err_console.print(error(` and no `"status": "error"` dict literal outside `ui/output.py`, with a shrink-only baseline of the ~49 existing lines.

### CX-2  YAML config loading, parsing and the secret-ref guard  -- CENTRALIZE, M
`yaml.safe_load`: 21 calls in 14 files. Ways it is done (all `safe_load`; the only `yaml.load` is the strict loader at ci/manifest.py:106, deliberate):
1. Full load, YAMLError sanitised, mapping check, then `parse_pipeline_config(raw).model_dump()`: cli/tokenize.py:202 and :546, cli/unmask.py:156, cli/report.py:2255 (CC-3).
2. Load only, sanitised: cli/preflight.py:704 (None -> "yaml.empty"), cli/subset.py:158 (None -> "yaml.empty"), cli/gate/_layers.py:98 (returns findings, `yaml.parse_error`), cli/compile_explain.py:177.
3. Load that also catches `(OSError, UnicodeDecodeError)`: cli/compile_explain.py:177-181, cli/io/_project.py:89 (also `RecursionError`), api.py:93 (YAMLError only, calls `yaml_error_text` directly).
4. Load inside a broad `except Exception`: cli/report.py:1761-1768 and :1774-1779, cli/scan.py:243 (falls back to `json.loads`).
5. Re-parse of text the CLI itself produced: cli/init.py:124, :387, :408, :750; cli/gen/_scaffold.py:141; cli/plan.py:44; cli/demo.py:229 (no error handling at all).
Existing owners: `cli/_yaml_errors.py::sanitize_yaml_error` (wraps engine `safe_output.yaml_error_text`) for the message only; `cli/gate/` for the pre-run gate; tests/sentry/test_yaml_error_leak_isolation.py guards the leak. Nothing owns the read-parse step.
Inconsistencies read in code:
- Variant 1 and variant 2 handle only `YAMLError`. A config that is not UTF-8 raises `UnicodeDecodeError` out of `read_text` (tokenize.py:202, unmask.py:156, report.py:2255, preflight.py:704, subset.py:158), which reaches the global handler at __main__.py:140 as a generic crash instead of a usage error. UNVERIFIED at runtime (could not run). compile_explain.py:181 shows the intended handling.
- Empty file: preflight/subset say "Pipeline YAML is empty."; tokenize/unmask/report vault say "must be a YAML mapping (object), not NoneType".
- `parse_pipeline_config(...)` is called at 11 sites (api.py:476, cli/report.py:1762, :2022, cli/gate/_layers.py:148, cli/tokenize.py:259, :579, cli/init.py:409, cli/demo.py:230, cli/subset.py:181, cli/preflight.py:456, :728), each with its own except list.
Choke point: `cli/io/_config.py` (or `cli/gate/`) `load_config_mapping(path) -> (raw, problem)` doing read, decode, safe_load, mapping check, empty check, sanitising, plus the CC-1 guard. Guard test: `yaml.safe_load` of a user-supplied path only in that module (allowlist for the init/plan re-parses).

### CX-3  JSON output  -- CENTRALIZE, M
`json.dumps`: 30 calls in 20 files (grep). Roles:
- `--json` stdout emitter: `ui/output.py:161` `emit_json` = `sys.stdout.write(json.dumps(payload) + "\n")` (no indent, no sort_keys, no `default`). Stragglers writing `--json` stdout directly: cli/scanning/_multi.py:471 `sys.stdout.write(json.dumps(core) + "\n")`; cli/schema.py:91-92 (indent=2, no flush) and :68 (`json` mode content written to a file with the same envelope); distribution/selfcheck.py:83 `print(json.dumps(asdict(result)))` (standalone stdlib script, acceptable).
- Artifact files written with different settings: cli/fit.py:737 and cli/gen/_scaffold.py:229 `indent=1` (snapshot); cli/demo.py:155, cli/report.py:1815, :2063, cli/run/_evidence.py:36, cli/scanning/_multi.py:457, cli/setup/__init__.py:103, cli/schema.py:72 all `indent=2`; ci/reporting.py:30-35 `ensure_ascii=True` with compact separators; ci/manifest.py:204 `indent=2, sort_keys=True`; plan.py:44 `sort_keys=False`.
- Canonical bytes (hash/sign inputs, deliberately specific): cli/evidence.py:131-139, distribution/signing.py:47, distribution/installer.py:193, notify.py:240. Fine.
- `default=` is used once (cli/gen/_preview.py:76 `default=str`). `emit_json` has none, so a non-serialisable value in any `--json` payload raises mid-command.
Choke points: keep `emit_json` as the one stdout emitter (route _multi.py:471 and schema.py:91 through it); add `write_json_artifact(path, doc, *, indent=2)` next to `write_local_target` for artifact files. Guard test: no `sys.stdout.write(json.dumps` in src/decoy/cli; shrink baseline for artifact-file dumps.

### CX-4  Process exit  -- ALREADY-OWNED, S
Owner: cli/exit_codes.py (EXIT_OK 0, USAGE 1, WARNINGS 2, RUNTIME 3, FINDINGS 4, CAPACITY 5), guard tests/unit/test_exit_codes.py:52-72.
`typer.Exit`: 201 calls in 27 files. Literal integers: one, `__main__.py:165` `raise typer.Exit(1)`, plus `__main__.py:206` `typer.Exit()` (0, fine). The guard regex (test_exit_codes.py:61) is `typer\.Exit\(code=\d|sys\.exit\(\d`, so it does not match the positional form `typer.Exit(1)`; that is why it passes. It also does not match `SystemExit`. All other sites use `EXIT_*` or a variable assigned from them (ci.py:196-205, validate.py:160-163, demo.py:587, run/_errors.py:128-156, fit.py:662).
Not covered: distribution/first_install.py:53,81, layout_point.py:20,22, verify_extracted.py:61-70, selfcheck.py:96 return literal 0/1/2 from standalone stdlib `main()` scripts (the install scripts call them). Acceptable, but the docs should say so.
Action: change `__main__.py:165` to `EXIT_USAGE`; widen the regex to `typer\.Exit\(\s*(code=)?\d` and `SystemExit\(\d`.

### CX-5  Environment variables  -- CENTRALIZE (light), M
`os.environ.get`: 16 calls in 6 files. Reads: DECOY_NO_UPDATE_CHECK (_update_check.py:42), CI (:48), DECOY_VERSION_URL (:100), DECOY_DEBUG (__main__.py:141), NO_COLOR (ui/output.py:47), DECOY_OTEL_ENDPOINT/HEADERS (cli/run/_notify.py:32, :59), DECOY_NOTIFY_* (:132-138), DECOY_HOME and DECOY_BIN_DIR (distribution/layout.py:33, :101), DECOY_RELEASE_PUBKEY_FILE (distribution/release_key.py:46), DECOY_MAX_MEMORY and DECOY_THREADS (_resources.py:32-33, resolved at :310 with flag > env > settings file > auto).
Owner: `_resources.resolve()` is a real resolver but only for memory and threads. No general settings module.
Inconsistent truthiness, all read:
- DECOY_NO_UPDATE_CHECK: set and not "0" (_update_check.py:42-43).
- DECOY_DEBUG: exactly "1" (__main__.py:141).
- CI: any non-empty string, so `CI=false` disables update checks (_update_check.py:48).
- NO_COLOR: present even if empty (ui/output.py:47); no-color.org says non-empty. UNVERIFIED whether that matters to the project.
- cli/run/_notify.py:135 `int(os.environ.get("DECOY_NOTIFY_SMTP_PORT") or 587)`: a non-numeric value raises ValueError, which the outer `except Exception` turns into "notify dispatch failed: invalid literal for int()" (read at :151-156): non-fatal but not a settings error.
- `DECOY_PROJECT` is named in the docstring at cli/io/_project.py:120 and in docs/ROADMAP.md:289, but no code in src reads it. Either dead text or a missing feature; UNVERIFIED which.
Choke point: `src/decoy/_env.py` with `flag(name)`, `text(name)`, `integer(name, default)`; guard test forbids `os.environ` outside it, `_resources.py` (injectable `env`) and distribution/ (stdlib-only). Value is mid: the default-value variety is small today.

### CX-6  Timestamps  -- FINE
`datetime.now`: 8 calls, all timezone-aware UTC: cli/evidence.py:329 (isoformat), cli/run/_flow.py:44, :94, cli/run/_errors.py:224, cli/io/_layout.py:440, distribution/version_document.py:69, :122, notify.py:190. Formats: isoformat() for payloads, `%Y%m%dT%H%M%S%fZ` for run folders (_layout.py:351), `TIME_FORMAT` for version documents; each has one definition site. `time.time()` epoch ints in _update_check.py:72, :101. Minor: evidence.py:329 takes its own clock read instead of the run's `ctx._run_started_at` (_flow.py:44), so manifest `run_timestamp` can differ from the run-folder stamp by the run duration. UNVERIFIED whether it is meant to be "evidence built at" rather than "run started at".

### CX-7  Low-level file operations  -- ALREADY-OWNED, S
Owners: `_atomic.py`, `_private_file.py`, guards tests/sentry/test_atomic_writer.py (os.replace, rename, link, mkstemp, shutil.move outside `_atomic.py`; baseline tests/sentry/baselines/atomic-writer-allow.json) and tests/sentry/io_policy/test_private_files.py (baseline private-file-sinks.json).
Stragglers (all in the baselines, with reasons):
- cli/run/_vault.py:62-97 `_commit_vault`: mkstemp, os.fsync (:68), os.link backup (:74), os.replace (:80, :89), os.unlink (:92, :97). Baseline says L5a moves it to `_vault_commit.py`.
- distribution/installer.py:133, :669-673 (launcher shim: mkstemp, chmod, replace, unlink), first_install.py:71 (os.replace).
Not covered by any sentry (watch list lacks them): `os.unlink`, `shutil.rmtree`, `os.fsync`, `os.open`. Sites: shutil.rmtree at cli/run/_flow.py:75 (`ignore_errors=True` on a `tempfile.mkdtemp` dir), distribution/installer.py:153, :160, :534, :583, :613, :711, first_install.py:74; os.open at cli/io/_small_file.py:64 (read-only, O_NOFOLLOW), distribution/lock.py:59 (0o600 lock file), cli/run/_vault.py:66, _mask_secret.py:124. I read these; none writes data unsafely. Risk is a future inline `os.unlink` or `os.fsync` appearing unwatched; low priority.

### CX-8  Network  -- CENTRALIZE (small), S
`urllib.request.urlopen`, 5 call sites, four timeouts:
- _update_check.py:88 `timeout=_FETCH_TIMEOUT` (1.5 s), no headers.
- cli/upgrade.py:56 `_fetch` `timeout=30`; passed to the installer as `download=_fetch` (:170).
- distribution/installer.py:231 `_urllib_download`: `urlopen(url)` with NO timeout (default is blocking forever). It is the installer's default `download` (:461); the `decoy upgrade` command overrides it, so the hang only reaches callers that use the default. Likely bug for those callers.
- notify.py:254 `timeout=8` (webhook retries) and :319 `timeout=10` (Slack). notify.py:368 `smtplib.SMTP(..., timeout=10)`.
No TLS settings anywhere (default context, which is fine), and no scheme check on user-supplied webhook/Slack/`--url` values was found in notify.py (grep for scheme/startswith found none; `_host_only` at :420 is for logging). `file://` in `--url` or webhook is therefore accepted by urlopen. UNVERIFIED whether cli/run/_prepare.py validates `--notify` targets elsewhere.
Choke point: `distribution/_http.py::fetch(url, *, timeout)` used by upgrade, installer and _update_check; `notify.py` keeps its own POST helper. Guard test: `urlopen` only in those two modules, `timeout=` keyword mandatory, scheme must be https unless a test hook.

### CX-9  Hashing  -- CENTRALIZE (small), S
`hashlib.sha256`, 6 calls in 4 files. Two file hashers: cli/evidence.py:100-114 `hash_file` (returns `sha256:<hex>`, 64 KiB chunks) and distribution/manifest.py:96-101 `sha256_file` (returns hex, `_CHUNK`). The rest hash short strings with distinct purposes (ci/contracts.py:232 finding fingerprint, cli/io/_layout.py:242 6-hex name suffix, cli/evidence.py:140 canonical manifest hash, distribution/manifest.py:104 bytes): FINE. Note the evidence docstring says it matches "decoy-platform/api/evidence/hashing.py", so that form is a cross-repo contract. Home: evidence.hash_file calls `distribution.manifest.sha256_file` (or both call a `_hashing.py`). Engine does not export a file hasher (checked `__all__`).

### CX-10  Direct pandas.read_csv  -- ALREADY-OWNED, S
Owner: cli/_sources.py (moving to cli/io), guard tests/sentry/test_csv_read_choke_point.py (AST watch for read_csv, read_parquet, `pd.read_*`, polars, pyarrow readers) with shrink-only baseline csv-read-allow.json. Stragglers, all allowlisted with a reason: cli/demo.py:153 (bundled sample), cli/gen/_fit.py:48 `read_fit_csv`, cli/scan.py:304-312 `_load_csv_with_sampling` (and a fixed-width twin). No unlisted straggler.

### CX-11  uuid and secrets ids  -- FINE
uuid4: cli/io/_layout.py:387 `mint_invocation_id` (the owner, named in its docstring), notify.py:237 (webhook delivery id, different concept), cli/evidence.py:328 `run_id if run_id is not None else str(uuid4())` (straggler: should call `mint_invocation_id`, otherwise an evidence manifest built without an id gets an id unrelated to any run folder; UNVERIFIED which callers pass None). secrets.token_hex: _atomic.py:524, :731, _private_file.py:107, cli/run/_vault.py:72, all temp/backup name suffixes. No other id generation found.

### CX-12  Raw stdout writes versus the console helper  -- CENTRALIZE (small), S
`sys.stdout.write`: 9 calls in 6 files, `typer.echo`: 10 calls in 2 files (cli/ci.py, __main__.py).
Raw text that must not go through Rich: cli/ci.py:187-188 (write + flush), cli/init.py:572 (write, local `import sys`, no flush) and :740-741 (write + flush), cli/templates.py:146-148 (write, no flush), cli/schema.py:91-92 (write, no flush), cli/scanning/_multi.py:471, ui/output.py:161 (`emit_json`, write + flush). Flushing is inconsistent, and the `typer.echo` sites (ci.py:79, :193-224, __main__.py:205, :241) are a fourth way. No `print(` in cli or ui (distribution scripts only).
Guards: tests/sentry/test_one_stderr_console.py covers consoles only; test_ci_output_isolation.py covers ci. Choke point: `ui/output.py::emit_text(text)` (write, ensure trailing newline, flush); guard forbids `sys.stdout.write` and `typer.echo` in src/decoy/cli outside it.

## Part C. Co-change pairs and wide commits

Ordered by value.

### CP-1  api.py with cli/tokenize.py, cli/demo.py, cli/preflight.py  -- HIDDEN-SHARED-RULE
Pairs: api.py<->tokenize.py (7 together, 0.7), api.py<->demo.py (8), api.py<->preflight.py (7). Commits (git show --stat): ed39bb7 "route config errors through the engine value-free parse" touched api.py, demo.py, gate/_layers.py, init.py, preflight.py, report.py, subset.py, tokenize.py, validate.py, _yaml_errors.py; 38cdb69 (config-folder path resolution) touched api.py, _sources.py, compile_explain.py, demo.py, _layers.py, preflight.py, run.py, tokenize.py; b4f19ba (mask secret handling) touched api.py, tokenize.py, unmask.py, report.py, run.py, _mask_secret.py; 6f4db85 (file targets by declared format) touched api.py, _sources.py, demo.py, tokenize.py, unmask.py, run.py, io/_targets.py.
Shared rule: "load config -> secret-ref guard -> `parse_pipeline_config` -> resolve source paths against the config folder -> read sources -> write targets by declared format". It lives as separate copies in `decoy.api.mask`, `tokenize`, `demo`, `run`. This is CC-1, CC-4, CX-2. Fix those and the pair stops co-changing.

### CP-2  explain.py with api.py and _native_gate.py  -- HIDDEN-SHARED-RULE (low)
Pairs: api.py<->explain.py (11, 0.39), _native_gate.py<->explain.py (6, 0.6). Commits: 850fd92 (remove dead substrate plumbing) touched _native_gate.py, api.py, explain.py, run.py; 1c784ae (native packaging), 57e8b81, f38db9e.
Shared rule: explain.py:331-364 (`native` topic) and the mask/keys topics are hand-written prose describing `--native`, `--no-native`, `--mask-secret`, DECOY_MASTER_KEY (explain.py:167, :207, :441) that the option definitions (cli/run/__init__.py:137) and `_native_gate` enforce. Behaviour changes must be mirrored in prose by hand. UNVERIFIED whether a test compares topic text to the option set (tests/unit/test_surface_docs_consistency.py covers docs, not explain topics, as far as the CODEMAP row says).

### CP-3  __main__.py with validate.py, init.py, explain.py  -- EXPECTED
Pairs: __main__<->validate (9, 0.43), <->init (6), <->explain (9). These are the command registration (`app.command(...)(...)`, __main__.py:254-273) plus the hand-maintained root help epilog (__main__.py:50-70) that lists each command. Commits 8f5991f, f5ffee9, 61c29c5, f3c9b9b are command renames/merges, which must touch the registry. Guarded by tests/unit/test_cli_surface.py and tests/sentry/baselines/root-help-omitted.json (existence read; assertions not read, so the guard's exact coverage is UNVERIFIED).

### CP-4  Wide commit f32834b "multi-file scan sets with FK discovery (#166)", 8 files, 6 packages  -- EXPECTED
Files: __main__.py, ci/adapters.py, cli/io/*, cli/scan.py, cli/scanning/*, ui/banner.py. A new feature that moved code out of scan.py. Two small side effects read in the diff: ci/adapters.py swapped `from decoy.cli.scan import _load_scan_dict` (a private cross-package import) for the public `decoy.cli.io.load_scan_set`; and the example string `decoy scan data.csv --has-header` is hand-written in ui/banner.py:51, __main__.py:57 and docs/cli-reference.md:7, :1139, so a flag change touches all of them. No NOISE entries.

## Part D. Re-implementations of public engine helpers

Engine `__all__` (228 names in /home/user/decoy-engine/src/decoy_engine/__init__.py) compared with helpers in src/decoy. No hand-rolled byte-size formatter, duration formatter, or profile redactor was found that duplicates an engine export (the only size text is cli/gate/_capacity_text.py:13 `format_gib`, with no engine equivalent). Findings, ordered by value:

### CE-1  Secret-reference grammar  -- narrower copy, drift
CLI: _mask_secret.py:35 `_REF_PREFIXES = ("env:", "file:", "vault://")` and :61-62 `is_valid_mask_secret_ref` = case-sensitive `startswith`; the error text hard-codes "'env:NAME' or 'file:/PATH'" (api.py:121, _prepare.py:222). Engine: `decoy_engine.secret_providers.parse_ref` (secret_providers/_types.py:94-130, exported at secret_providers/__init__.py:59) lower-cases the scheme and accepts "any other well-formed scheme:locator ... so the registry, not the parser, owns the 'unknown provider' decision", and `register_secret_provider` is a public top-level export. So a registered third-party scheme, or `ENV:NAME`, is accepted by the engine and refused by the CLI guard before the engine sees it. Fix: guard calls `parse_ref` (catch the bare `bad_secret_ref`) instead of a prefix tuple. Ties into CC-1.

### CE-2  File-name safety rule beside the engine's pipeline-name rule  -- related rule, two definitions
CLI: _atomic.py:117 `_NAME_PATTERN` (up to 200 chars) and :120-124 `_DEVICE_STEMS` (adds CONIN$, CONOUT$, superscript digits, per CPython `os.path.isreserved`). Engine: config/_pipeline.py:61 `_PIPELINE_NAME` (up to 64 chars) and :64-68 `_WINDOWS_DEVICES` (CON, PRN, AUX, NUL, COM1-9, LPT1-9), with public `is_valid_pipeline_name` (docstring: "the one pipeline-name rule"). The CLI's pipeline-name check does call the engine function (cli/io/_layout.py:58-60), which is correct. The `_atomic.py` rule is for arbitrary written file names, so it is not a plain duplicate, but the engine's device list is a subset of the CLI's (a pipeline named `CONIN$` is excluded by the pattern anyway; `COM¹` is excluded by the character class). No live bug found. Flag: two device-name tables that must agree.

### CE-3  Private scratch directory  -- engine helper bypassed, baselined
cli/run/_prepare.py:300 `tempfile.mkdtemp(prefix="decoy-duckdb-")`, cleaned with `shutil.rmtree(..., ignore_errors=True)` at cli/run/_flow.py:75. Engine exports `protected_scratch_dir` and `open_protected_dir` (fileaccess/_protected_dir.py:268, context manager, removed on every exit, registered as engine-owned). tests/sentry/baselines/private-file-sinks.json:`cli/run/_prepare.py::prepare::tempfile.mkdtemp::1` records it as 0700 by stdlib, exit "WIN-FEAS". Also ci/engine_logging.py:29 uses `tempfile.TemporaryDirectory` (baselined). Cleanup is manual and `ignore_errors=True`, so a failed removal of a directory holding unmasked Parquet is silent.

### CE-4  YAML error text under two names  -- cosmetic
api.py:88-95 imports `decoy_engine.safe_output.yaml_error_text` directly; everything under cli/ goes through `cli/_yaml_errors.py::sanitize_yaml_error`, which is a one-line wrapper (cli/_yaml_errors.py:14-21). Collapsing to one is optional.

### CE-5  Engine reason-code strings copied  -- already ratcheted
tests/sentry/test_engine_reason_code_copies.py with baseline tests/sentry/baselines/engine-reason-code-copies.json lists legacy copies in _mask_secret.py and _mask_secret_guidance.py (secret_file_permissions_unsafe, bad_secret_ref, keyed_strategy_requires_secret, missing_mask_secret, secret_provider_unknown, weak_mask_secret, ...). Owned; nothing new.

Not duplicated (checked): `_resources.py:288` and :275 call engine `detect_usable_cpus` and `resolve_conservative_ooc_budget_bytes`; cli/io/_layout.py:58 uses `is_valid_pipeline_name`; `sanitize_yaml_error` delegates to the engine. No file-hash helper or redaction helper in the engine to duplicate.
