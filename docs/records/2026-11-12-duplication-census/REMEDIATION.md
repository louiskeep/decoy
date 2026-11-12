# Remediation report: duplicated code and uncentralized concerns (engine and CLI)

Date: 2026-11-12. Engine main `35b82bd8`, CLI main `9cc0434`. No code was changed.

This is the working list for remediation. It sorts every finding of the census
([README.md](README.md)) into **V1** (do now, inside the CLI V1 track) or **V1+** (after CLI V1).
Each row gives the action and the locations. The five detail files in this folder hold the full
site lists, the quoted differences between copies and the triage notes; a row that says "all
sites: X" points there.

Path shorthand: `E:` is `decoy-engine/src/decoy_engine/`, `C:` is `decoy/src/decoy/`. Ids (EC,
EX, ED, EN, EP, EW, CC, CX, CP, CE) are the ids in the detail files:
[engine-clones.md](engine-clones.md) (EC),
[engine-hashing-rng-serialization.md](engine-hashing-rng-serialization.md) (EX),
[engine-data-io-regex.md](engine-data-io-regex.md) (ED),
[engine-names-cochange.md](engine-names-cochange.md) (EN, EP, EW), [cli.md](cli.md) (CC, CX, CP,
CE).

## 1. How the tiers were set

An item is **V1** when one of these holds:

1. **Possible defect.** Two copies disagree in a way that can change output, an exit code or an
   error. These need a reachability check first; a confirmed one meets the V1 bar (roadmap
   section 3).
2. **Frozen at release.** The change moves output bytes, a digest, an exit code, a `--json`
   shape or an environment variable's meaning. REL-GATE (row 93) freezes those, and
   `RELEASE_PHASE` makes the compatibility contract binding. Before that, a change is a
   changelog line; after it, a migration.
3. **Guard.** A sentry with a baseline of today's sites. No behavior change, and it stops the
   count growing while V1 rows keep adding code.
4. **Small and safe.** Under about 50 lines moved, behavior-preserving, in files no roadmap row
   names as a single-writer lane.
5. **Cuts V1 churn.** The duplication is costing edits on V1 rows today.

Everything else is **V1+**: medium and large behavior-preserving refactors, and anything inside
a hot lane (roadmap rule 5.2.2: `C:cli/run/_execute.py`, `_flow.py`, `_errors.py`, `_render.py`,
`_evidence.py`, `_notify.py`, `C:cli/scan.py`).

Each V1 package still runs the dev loop (PLAN, double gate). The PLAN re-checks lanes: this
report used the lanes the roadmap names, not the live branch list.

"Confirmed" in a State column means the line was re-read for this report and says what is
described. It does not mean a failure was reproduced. Nothing was run end to end.

## 2. Counts

| Tier | Package | Items |
|---|---|---|
| V1 | A. Engine possible defects | 17 |
| V1 | B. CLI possible defects | 11 |
| V1 | C. Settle before the freeze | 10 |
| V1 | D. Guards | 11 |
| V1 | E. Engine small extractions | 24 |
| V1 | F. CLI small extractions | 7 |
| V1 | G. Churn reducers | 3 |
| V1+ | H to N (O is the leave-alone list) | 37 |

Suggested order: A and B first (verify, then fix what is real), D next (cheap, stops growth),
C before REL-GATE, G as soon as a builder is free, E and F as filler between row merges.

---

## 3. V1

### A. Engine: possible defects (verify reachability, then fix)

| # | Id | Where | What the code does | Action | State |
|---|---|---|---|---|---|
| A1 | EX-2 | `E:transforms/joint_mask.py:338`, `:366-367`; key passed at `E:execution/_strategies/_joint_mask.py:123` | Seeds `default_rng` from `job_seed[:8]` (the mask key) with no namespace or column, so every `joint_mask` column draws the same stream, and 8 bytes of key material are the seed | Decide whether the shared stream is intended. If not, seed through `derive(mask_key, namespace, source)` like the other mask-side generators. Changes output | Confirmed |
| A2 | EN-2, EX-3 | `E:execution/native/_draw_site_providers.py:107-117` (copy), `E:transforms/text_mask.py:242-263` (original) | Native `_span_key` encodes strict UTF-8; the original uses `errors="replace"`. A lone surrogate keys differently or raises on the native route | Delete the copy and import the original. Add a parity test with a lone surrogate | Confirmed |
| A3 | EX-2, ED-7 | Zero fallback: `E:generation/composite/_address.py:70,96`, `_city_state_zip.py:86`, `_custom.py:184,206`, `_name_email.py:81,134`, `_person.py:79,142`. Random fallback: `_address.py:181`, `_city_state_zip.py:124`, `_custom.py:280`, `_name_email.py:221`, `_person.py:239`, `_provider.py:204` | With no seed, some paths in the same file use a fixed all-zero seed and others `os.urandom(8)` | Decide the rule per path (deterministic paths may be right to use a fixed seed). Put the random one behind one `fresh_seed()` in `E:determinism/` | Confirmed |
| A4 | EX-2 | `E:generation/composite/_person.py:143`, `_name_email.py:135`, `_address.py:97`, `_provider.py:117`, `_custom.py:207`, `E:execution/native/protocol/providers_gen.py:75` | `int.from_bytes(seed, "big")` with no length check; the pool path enforces 8 bytes (`E:generation/pool/_sampler.py:168-190`) | Call `_seed_bytes_to_int` (move it to `E:determinism/`) | Reported |
| A5 | EX-4 | `E:generation/statistical/_spec.py:205`, `E:plan/_generation.py:217` | `json.loads(bytes)` catches only `JSONDecodeError`; invalid UTF-8 raises `UnicodeDecodeError`, so a bad snapshot escapes without `STATISTICAL_SNAPSHOT_UNREADABLE` | Catch `(UnicodeDecodeError, ValueError)` as `E:vault.py:482` does. Fold into E-X4 | Reported (agent ran the bare call) |
| A6 | ED-4 | No shim: `E:generation/_window_admission.py:177`, `E:generation/statistical/_sample.py:503-504`, `E:profile/_serialize.py:153`. Shim, unguarded: `E:generation/_pinned_compile.py:196`. Shim, guarded: `E:_reference_date.py:37` | `datetime.fromisoformat` rejects a trailing "Z" on Python 3.10 | One `parse_iso_instant` in `E:internal/pandas_compat.py`; use at all five | First line confirmed |
| A7 | ED-5 | `E:quality/dp.py:148-163` vs `E:plan/_checks_dp.py:111-114` | Run-time check does `float(epsilon)` first, so `True` and `"0.5"` pass; the plan check refuses bool | One epsilon and delta validator used by both | Confirmed at `dp.py:152` |
| A8 | ED-6 | `E:profiling/model_pack/loader.py:186` vs `:90` | `DECOY_ML_DISABLED` is honored only for exactly `1`; the signature flag in the same file takes a strict true or false set and refuses anything else | Parse both with the strict set. Fold into C7 | Reported |
| A9 | EC-6 | Refuse: `E:providers_v2/identifiers/_ein.py`, `_ndc.py`, `_npi.py`, `_ssn.py`. Accept: `_cusip.py`, `_iban.py`, `_icd10.py`, `_pan.py` (`generate_random` in each) | All declare `supported_locales=("en_US",)`; only four raise `UNSUPPORTED_LOCALE` | Owner decision: refuse in all, or drop the gate. GEN-PROVIDERS (row 24p) exposes these to generation, so settle it there | Confirmed by search |
| A10 | ED-2 | `E:transforms/derived.py:208`, `E:generators/_formula.py:206` vs `E:kernel/_scalar.py:14` | `pd.NA` and `NaT` count as non-null in the first two; the kernel says `pd.NA` must count as missing | Check whether a nullable-dtype cell can reach them. Related to row 24y (formula reads a sequence column) | Reported |
| A11 | EN-5 | `E:execution/out_of_core/_route_policy.py:216-245` vs `E:execution/_sequential_order.py:18-60` | Out-of-core ordering treats a self-FK as a cycle (`OUT_OF_CORE_RELATIONSHIP_CYCLE`); sequential skips self-edges | Check whether out-of-core refuses a self-FK earlier. If not, a self-referencing table fails only on the large route | Reported |
| A12 | EC-27 | `E:generation/_plan_entry.py:179-251` (has `@entry_point` and `file_access`), `:254-289`, `:292-323`, `:326-350` (do not) | Three of four public generation entries lack the file-access entry decoration | Check against `tests/sentry/test_file_access_entry_points.py`; a gap is a policy hole, not a cleanup | Reported |
| A13 | ED-4 | `E:profiling/_date_sniff.py:31`, `E:profiling/_distributions.py:70` | `pd.to_datetime(errors="coerce")` with no time-zone handling; raised on mixed offsets under pandas 3.0.5 in the sandbox | Re-test on the pinned pandas (below 3). Fold into the ED-4 helper | Not reproduced on the pinned version |
| A14 | EX-2 | `E:generators/_distribution.py:65,141,266,386` and `E:generators/columns.py:219` | Values and the null mask draw from the same stream (`base_int("np")`) | Check whether any plan path still reaches the legacy class (`E:generation/synthesize.py:343` routes elsewhere). If unreachable, delete it (pre-GA hard delete) | Line confirmed; reachability not shown |
| A15 | ED-1 | `E:execution/_chunked_when_guard.py:66` vs `E:execution/native/_dispatch.py:500`, `_when_admission.py:249` | Guard accepts `string` only; admission treats `large_string` as equal | Check whether a reader yields `large_string` there. Fails closed | Reported |
| A16 | ED-3 | `E:profiling/profiler.py:235`, `E:profiling/sentinels.py:138` vs `profiler.py:210` | Bool columns get numeric stats while typed "boolean" | Check output; exclude bool if wrong | Reported |
| A17 | EN-6 | `E:execution/native/_plan.py:405-409` | Table lookup with no `isinstance(tbl, dict)` guard; a non-dict entry raises `AttributeError` | Add the guard now; full fix is V1+ package I | Reported |

### B. CLI: possible defects

| # | Id | Where | What the code does | Action | State |
|---|---|---|---|---|---|
| B1 | CC-5 | `C:cli/demo.py:587-591` vs `C:cli/run/_errors.py:128-156`; also `C:cli/fit.py:660-665`, `cli/gate` (`gate_exit_code`) | `demo` maps three exception types to exit 1; `run` maps many more, so the same failure can exit 1 in `run` and 3 in `demo` | `exit_code_for(exc)` in `C:cli/exit_codes.py`; all four call it. `_errors.py` is a lane (RESULT, F29 C1): coordinate | Confirmed |
| B2 | CC-4 | `C:cli/demo.py:266-288` vs `C:cli/run/_execute.py:152-199` | `demo` has its own source loader and target writer; skips `_require_local_io_endpoints` and `check_target_formats` | Move both to `C:cli/io/`; `demo` and `run` import them. `_execute.py` is a lane | Reported |
| B3 | CX-4 | `C:__main__.py:165`; guard at `tests/unit/test_exit_codes.py:61` | `typer.Exit(1)` literal; the guard regex matches only `code=` | Use `EXIT_USAGE`; widen the regex to `typer\.Exit\(\s*(code=)?\d` and `SystemExit\(\d` | Confirmed |
| B4 | CX-8 | `C:distribution/installer.py:231` (`_urllib_download`) | `urlopen(url)` with no timeout; it is the installer's default downloader (`:461`) | Add a timeout. Fold into F6 | Confirmed |
| B5 | CX-2 | `C:cli/tokenize.py:202`, `:546`, `C:cli/unmask.py:156`, `C:cli/report.py:2255`, `C:cli/preflight.py:704`, `C:cli/subset.py:158`; handled at `C:cli/compile_explain.py:177-181` | A config that is not UTF-8 raises `UnicodeDecodeError` to the global handler instead of a usage error | Fixed by C5. VALIDATE-ALWAYS FU-7 (row 23) is the same issue for `run` | Reported; not run |
| B6 | CC-2 | `C:cli/scanning/_multi.py:221-222`, `C:cli/gen/_scaffold.py:171-172` | Error line printed in `--quiet` mode; other commands print nothing | Fixed by C1 | Reported |
| B7 | CC-2 | `C:cli/fit.py:~422`, `C:cli/scanning/_multi.py:222`, `C:cli/reference.py:285` | Error text printed without `markup=False`, so bracketed engine text such as `[vault]` can be dropped | Fixed by C1 | Reported |
| B8 | CE-1 | `C:_mask_secret.py:35`, `:61-62`; messages at `C:api.py:121`, `C:cli/run/_prepare.py:222` | Hard-codes `env:`, `file:`, `vault://`, case-sensitive; the engine's `parse_ref` lower-cases and accepts any registered scheme | Call `decoy_engine.secret_providers.parse_ref`. Do with F1 | Confirmed at `:35` |
| B9 | CX-5 | `C:_update_check.py:48`; `C:cli/run/_notify.py:135` | `CI=false` still counts as CI; a non-numeric `DECOY_NOTIFY_SMTP_PORT` surfaces as "invalid literal for int()" | Fixed by C7 | Reported |
| B10 | CX-11 | `C:cli/evidence.py:328` | `str(uuid4())` when no run id is passed, instead of `mint_invocation_id` (`C:cli/io/_layout.py:387`) | Check which callers pass `None`; call the owner | Reported |
| B11 | CX-8 | `C:notify.py:254`, `:319`; `C:cli/upgrade.py:56` | No scheme check found on webhook, Slack or `--url` values, so `file://` reaches `urlopen` | Check whether `_prepare.py` validates them; if not, require https | Reported, not traced |

### C. Settle before the versioning freeze (REL-GATE, row 93)

| # | Id | What must be decided or unified | Where | Size |
|---|---|---|---|---|
| C1 | CX-1, CC-2 | One CLI error emitter: `emit_error(state, command, message, *, hint, code, **context)` in `C:ui/output.py`, one `--json` error shape. Convert the drifted sites now (B6, B7, `fit`'s different shape at `C:cli/fit.py:403-425`); the rest go behind the D7 baseline | Emitters: `C:cli/report.py:1721`, `:2234-2251`, `C:cli/unmask.py:136-153`, `C:cli/tokenize.py:181-197`, `:527-541`, `C:cli/fit.py:403-425`, `C:cli/scanning/_multi.py:216-224`, `C:cli/gen/_scaffold.py:164-176`, `C:cli/scan.py:440-470`, `C:cli/reference.py:272-284`, `:300-313`, `C:cli/subset.py` (`_fail_usage`), `C:cli/compile_explain.py` (`_simple_error`) | M now, L in full |
| C2 | CC-5 | One exception-to-exit-code map (B1) | as B1 | S |
| C3 | EX-1 | One rule for JSON that feeds a digest: `default=` policy, `ensure_ascii`, `allow_nan`. `E:plan/_compile.py:645-657` removed `default=str` on purpose; these kept it: `E:generation/_reproducibility.py:204`, `E:generation/pool/_builder.py:41`, `E:plan/_generation.py:329`, `E:generation/_pinned_compile.py:295`, `:315`, `E:execution/physical/_inputs.py:94` (`default=repr`). Plan and config hashes move, which is free only before GA | All 19 sites and 8 variants: EX-1 | M |
| C4 | EX-2 | Seed derivations that change output: A1, A3, A4. Any other change to how a seed is derived belongs here too | as A1, A3, A4 | S |
| C5 | CX-2, CC-1, CC-3 | One config loader `load_config_mapping(path)` (read, decode, `safe_load`, empty check, mapping check, sanitized error) plus the secret-ref guard, so every command gives the same message and exit code for the same bad file | Loader copies: `C:cli/tokenize.py:201-207`, `:545-551`, `C:cli/unmask.py:155-162`, `C:cli/report.py:2254-2261`, `C:cli/preflight.py:704`, `C:cli/subset.py:158`, `C:cli/gate/_layers.py:98`, `C:cli/compile_explain.py:177`, `C:api.py:93`. Guard copies: F1 | M |
| C6 | CX-3 | `--json` output through `emit_json` only | Bypasses: `C:cli/scanning/_multi.py:471`, `C:cli/schema.py:91-92` | S |
| C7 | CX-5, ED-6 | One truthiness rule for flag variables, in each repo | CLI: `C:_update_check.py:42`, `:48`, `:100`, `C:__main__.py:141`, `C:ui/output.py:47`, `C:cli/run/_notify.py:32`, `:59`, `:132-138`. Engine: `E:profiling/model_pack/loader.py:90`, `:186`, `:351`, `E:profiling/model_pack/provenance.py:282`, `E:execution/_isolated_run.py:221`, `:238`, `:469`, `E:connectors/sftp.py:138`, `E:internal/faker_setup.py:223` (`CUSTOM_PROVIDERS_DIR`, no `DECOY_` prefix) | S each |
| C8 | ED-8 | One "generated at" shape | `E:profiling/types.py:193` (`utcnow().isoformat() + "Z"`, deprecated) vs `E:profiling/scan_set.py:283`, `E:quality/report.py:257`, `E:verification/postmask/runner.py:167` (`+00:00`) | S |
| C9 | EC-1 | One message for `NER_MODEL_VERSION_MISMATCH` (three wordings today) | `E:execution/_strategies/_text_mask.py:120-150`, `E:execution/out_of_core/_mask_group_c.py:320-358`; shared helper `E:execution/_strategies/_ner_config.py:51-116` | S |
| C10 | A9 | Identifier locale rule | as A9 | S |

### D. Guards (sentry plus a baseline of today's sites; no behavior change)

| # | Id | Guard | Forbids outside the owner |
|---|---|---|---|
| D1 | all | `jscpd` in `gates.sh`, shrink-only baseline, both repos | new copy-paste blocks |
| D2 | EX-2 | `tests/sentry/test_rng_construction.py`, baseline of the 68 sites, each entry naming its draw-site id | `default_rng(`, `random.Random(`, `np.random.seed`, `SystemRandom` outside `E:determinism/` and `E:generators/derivation.py` |
| D3 | EX-1 | `tests/sentry/test_canonical_json_choke_point.py`, baseline of the 19 sites | `json.dumps(sort_keys=True` or `default=` feeding `hashlib` or `hmac` outside the owner |
| D4 | EX-3 | hmac sentry with a 3-site allowlist (`E:declared_casting/_quarantine_local.py:405`, `E:profiling/model_pack/provenance.py:232`, `E:secret_providers/_types.py:91`) | `hmac.new(` outside `E:determinism/` |
| D5 | ED-1 | Arrow text predicate sentry, baseline of the 21 files | `pa.types.is_string`, `is_large_string`, `is_binary`, `is_large_binary` outside the owner |
| D6 | ED-6, CX-5 | environment sentry, one per repo | `os.environ`, `os.getenv` outside the owner, `secret_providers/`, the isolated-worker builder, `C:_resources.py`, `C:distribution/` |
| D7 | CX-1 | `tests/sentry/cli_text/`, baseline of about 49 lines | `err_console.print(error(` and `"status": "error"` literals outside `C:ui/output.py` |
| D8 | CX-2 | config-load sentry, allowlist for re-parses of CLI-written text | `yaml.safe_load` of a user path outside the loader |
| D9 | CX-12, CX-3 | stdout sentry | `sys.stdout.write`, `typer.echo` in `C:cli/` outside `C:ui/output.py` |
| D10 | CX-4 | widen the exit-code regex (B3) | literal exit codes in any call form |
| D11 | CX-7 | add `os.unlink`, `shutil.rmtree`, `os.fsync`, `os.open` to the atomic-writer watch list | new unwatched file operations |

### E. Engine: small extractions (behavior-preserving)

| # | Id | Extract | From | To |
|---|---|---|---|---|
| E1 | EC-1 | NER config parse and version guard (with C9) | `E:execution/_strategies/_text_mask.py:120-150`, `E:execution/out_of_core/_mask_group_c.py:320-358` | existing `E:execution/_strategies/_ner_config.py` |
| E2 | EC-2 | DP `column_schema` validation and the kind-to-carrier table | `E:quality/carrier_adapter.py:88`, `:95-152`; `E:quality/dp_fit_schema.py:24`, `:60-120` | `E:quality/carriers.py` |
| E3 | EP-4 | DP query count `1 + numeric + 2 * categorical` | `E:plan/_checks_dp.py:352`, `E:plan/_checks_dp_carrier.py:50` | `E:quality/dp_schedule.py:77` |
| E4 | EC-7, EN-7 | Luhn check digit and the NPI prefix `"80840"` | `E:providers_v2/identifiers/_npi.py:31`, `:34-46`, `_pan.py:42-58`, `E:transforms/fpe.py:182-192`, `E:checksums.py:85`, `:89-103` | `checksums.calc_check_digit`. Leave `E:profiling/eval/fixtures.py:58` and `_cusip.py:77` |
| E5 | EN-4 | `text_mask_sub_floor_warning` (three copies) | `E:execution/native/_text_mask_route.py:52-70`, `E:execution/out_of_core/_mask_group_c.py:121-146`, `E:execution/_strategies/_text_mask.py:249-276` | beside `TextMaskHandler` |
| E6 | EN-9, EC-4 | `_fixed_output_schema`, `_fk_component_map` | `E:execution/out_of_core/_rewrite_pass.py:331-371` | existing `E:execution/out_of_core/_stream_driver_support.py:43`, `:86`. Keep `_iter_source_batches` (patch seam) |
| E7 | EN-11 | `_unsafe_cols_in_schema` and its type tuple | `E:execution/_chunked_bucket_perturb.py:75`, `:102-112`, `_chunked_code_set.py:88`, `:120-130`, `_chunked_text_mask.py:39`, `:50-60` | new `E:execution/_chunked_string_gate.py` |
| E8 | EN-12 | `resident_block`, `_slices`, `_mismatch` | `E:execution/_chunked_input.py:101`, `:243`; `_chunked_output_sink.py:78`, `:346`; `_pipeline_auto_chunk.py:131`, `:152` | `_chunked_input.py` and `_pipeline_auto_chunk.py` |
| E9 | EN-13 | `_nfkc`, `_has_when`, `_provider_config` | `E:execution/_chunked_carry.py:60`, `_faker_degenerate_pin.py:50`, `native/_chunked_schema_rule.py:75`, `_chunked_fk_edge_checks.py:390` | `E:execution/_column_access.py:69`, `:127` |
| E10 | EC-20, EN-14 | `_compute_overall`, `_SCORE_PRECISION`, the TVD tail | `E:quality/fidelity.py:140`, `:479-492`, `:566-594`; `E:quality/shape_fidelity.py:60`, `:243-253` | new `E:quality/_scoring.py` |
| E11 | EN-15 | `_join_key` | `E:connectors/s3.py:168-177`, `E:connectors/gcs.py:91-95` | new `E:connectors/_keys.py` |
| E12 | EN-16 | `_strict` (fail-closed default in four places) | `E:fileaccess/adapters/arrow.py:17`, `pandas.py:18`, `polars.py:14`, `serial.py:15` | `E:fileaccess/_types.py` |
| E13 | EN-17 | `_q` SQL identifier quoting | `E:connectors/postgres_snapshot.py:204-206`, `E:execution/out_of_core/_join.py:521-522` | new `E:internal/sql_ident.py` |
| E14 | EC-12 | Arrow IPC spill writer | `E:execution/out_of_core/_payload_store.py:145-168`, `:205-228` | base class in the same module |
| E15 | EC-13 | file-policy handle on `LazySource` | `E:profile/_readers.py:213-239`, `:232`, `:367`, `:403`; `E:profile/_readers_csv.py:58` | existing `E:profile/_policy_bound.py:11-21` |
| E16 | EC-14 | relationship edge resolution | `E:validators/_relationship_checks.py:118-135`, `:255-272` | same module |
| E17 | EC-15 | locality audit loop | `E:validation/post/_checks/_composite_coherence.py:100-118`, `:156-174` | same module |
| E18 | EC-19 | layout against `fixed_width` validator | `E:config/_sources.py:157-167`, `E:config/_targets.py:55-65` | small `E:config/` leaf |
| E19 | EC-21 | index-kernel result check | `E:execution/native/_categorical_ext.py:100-117`, `_operator_step.py:214-231` | `_operator_step.py` |
| E20 | EC-25 | six `thresholds[key].min` checks | `E:quality/policy.py:243-312`, `:363-426` | one `_check_min` and a table, same module |
| E21 | EC-28 | registry binding lookup | `E:providers_v2/_registry.py:51-81` | same module |
| E22 | ED-3 | pandas dtype to type label | `E:profiling/features/builder.py:120-132`, `E:profiling/profiler.py:208-218` | `E:profiling/_classification.py` |
| E23 | ED-9, ED-10 | numexpr-fallback capture; header camelCase split; US ZIP pattern | `E:execution/_transforms.py:82-91`, `_when_gate.py:145-163`; `E:profiling/features/builder.py:97`, `E:quality/_freetext_names.py:40`; `E:detection/_patterns.py:36`, `E:detection/detectors.py` (`_US_ZIP_VARIANTS`) | `E:execution/_eval.py`; one header tokenizer; `_patterns.py` |
| E24 | EX-3, EX-4, EX-5 | HMAC framing stragglers; snapshot read-hash-parse and the `sha256:` tag; strict JSON parser | EX-3: `E:generators/derivation.py:218`, `E:internal/crypto.py:55`, `:70`, `E:execution/native/protocol/providers_mask.py:53`, `E:transforms/date_shift.py:123`. EX-4: `E:generation/statistical/_spec.py:175-225`, `E:plan/_generation.py:215-228`, `E:generators/derivation.py:141`; tag at `_fanout.py:67`, `_statistical_column.py:83`, `synthesize.py:385`, `window.py:201`, `_pinned_compile.py:313`. EX-5: `E:records/_codec.py:161-181`, `E:execution/native/_faker_deterministic_admission.py:153-171` | `E:determinism/_derive.py`; new `E:generation/statistical/_snapshot_io.py`; new `E:_json_strict.py`. Bytes must not change: golden test first |

### F. CLI: small extractions

| # | Id | Extract | From | To |
|---|---|---|---|---|
| F1 | CC-1 | `mask_secret_ref` shape guard, four copies with three message variants (with B8) | `C:api.py:108-125`, `C:cli/run/_prepare.py:199-226`, `C:cli/tokenize.py:215-231`, `:557-573` | `mask_secret_ref_problem(raw)` in `C:_mask_secret.py` |
| F2 | CC-6 | overwrite prompt | `C:cli/init.py:550-563`, `:643-656`, `C:cli/gen/_scaffold.py:171-188` | one helper |
| F3 | CC-6 | DP exception chain; fingerprint rows; "show needs NAME" blocks | `C:cli/fit.py:658-670`, `:718-731`; `C:cli/evidence.py:550-559`, `:570-579`; `C:cli/reference.py:275-284`, `:302-313` | local helper each |
| F4 | CC-7 | `_disabled(state)` | `C:ui/progress.py:25-27`, `C:ui/storm_animation.py:155-156` | `OutputState` in `C:ui/output.py` |
| F5 | CX-9 | file hasher | `C:cli/evidence.py:100-114`, `C:distribution/manifest.py:96-101` | one function; keep the `sha256:` form the platform shares |
| F6 | CX-8 | download helper with a required timeout (with B4) | `C:_update_check.py:88`, `C:cli/upgrade.py:56`, `C:distribution/installer.py:231` | new `C:distribution/_http.py` |
| F7 | CX-12, CE-4 | `emit_text` (write, newline, flush); one name for the YAML error text | `C:cli/ci.py:187-188`, `C:cli/init.py:572`, `:740-741`, `C:cli/templates.py:146-148`, `C:cli/schema.py:91-92`; `C:api.py:88-95` vs `C:cli/_yaml_errors.py:14-21` | `C:ui/output.py` |

### G. Churn reducers (the duplication costs V1 edits today)

| # | Id | Problem | Where | Action |
|---|---|---|---|---|
| G1 | EP-3 | The draw-site catalog stores `file:line`, so every edit that shifts a line in generation code edits the catalog (seen in `937d9e53`, `1e8739ae`, `24796b0f`, `45533490`, `6bdd4840`, `cfef8a6e`) | `E:execution/native/_draw_sites_gen.py:21-376` (16 `call_site` strings) | Key by `module:function` or a `# DRAW-SITE <id>` marker checked by the pinned test |
| G2 | EP-5 | Every engine release hand-edits two 64-hex fingerprints; releases are daily (rule 5.2.4) | `E:quality/dp_provenance.py:273` (`_CERTIFIED_STACKS`) | `scripts/release/cut-release.sh` writes the row; keep `tests/sentry/test_dp_lock_row.py` |
| G3 | EP-6 | Every new reason code hand-bumps `REGISTRY_VERSION` | `E:reasons/_registry.py:27` | Already planned: REG-RELEASE E2 (row 8), waiting on owner question R1 |

---

## 4. V1+

Behavior-preserving refactors. None changes a frozen surface if done as described, so they can
follow the release. Sizes: S under 50 lines moved or 10 sites, M up to 200 or 30, L above.

### H. One definition per strategy (engine)

| Id | Refactor | Where | Size |
|---|---|---|---|
| EP-1 | Derive the strategy tables from handler class attributes | `E:execution/_strategies/__init__.py:47-76` (`SCALAR_HANDLERS`), `E:execution/_technique_class.py:73`, `E:execution/_distribution_behavior.py:70`; mirrors at `E:validators/_leak_check.py:31,56`, `E:execution/_column_access.py:12`, `E:execution/native/_capabilities.py:29`, `_determinism_protocol.py:69,97` | M |
| EP-2 | Extend `OperatorSpec` so native and shadow modules look a strategy up instead of branching on its name | `E:execution/_operator_registry.py`; branches at `E:execution/native/_operator_params.py:235`, `_requirements.py:535`, `_chunked_schema_rule.py:127`, `_real_type_admission.py:62`, `_capabilities.py:222`, `_determinism_protocol.py:97`; `E:execution/physical/_shadow_*.py` | L |
| EC-3, EN-1, EN-19 | One generic native table plan; `_hash_run.py` loops over a strategy table | `E:execution/out_of_core/_fpe_native.py:77-188`, `_categorical_native.py:84-195`, `_text_mask_native.py:112-225`, `_text_redact_native.py:92-205` (identical apart from names: do first), `_bucket_native.py:80-215`, `_faker_native.py:94-256`, `_hash_run.py:107-200`, `:330-420`; `decline_reason` return shapes at `_bucket_native.py:57`, `_faker_native.py:76`, `_hash_native.py:50` | L |
| EC-23 | One chunked strategy gate (`reject_when`, `reject_fk_keys`) | `E:execution/_chunked_code_set.py:186-262`, `_chunked_dgrn.py:129-155`, `_chunked_group_key.py:338-365`, `_chunked_text_mask.py:137-163`, `_chunked_bucket_perturb.py:226-310`; callers `E:execution/_chunked.py:310-326` | M |
| EC-22, EC-26 | Strategy option resolution and the NER window loop shared by the pandas and out-of-core paths | `E:execution/_strategies/_bucket_perturb.py:45-60`, `_text_mask.py:86-110`, `:206-224`, `_text_redact.py:169-187`; `E:execution/out_of_core/_mask_group_c.py:248-263`, `:467-482`, `_mask_group_b.py:286-301` | S |
| EP-9 | Generic evidence sink on `StrategyContext` | `E:execution/_adapter.py:157-176`, `:214-215`, `:266-267` | S |

### I. Config access (engine)

| Id | Refactor | Where | Size |
|---|---|---|---|
| EC-8 | `iter_table_entries`, `iter_mask_columns`, `table_column_names(include_generate=)` in new `E:plan/_config_walk.py` | about 35 sites, all listed in EC-8; name-set blocks at `E:plan/_checks.py:605`, `_checks_group_key.py:55`, `_checks_windowed_date.py:60`, `_checks_grouped_series.py:64`, `_checks_derived_aggregate.py:57`, `_checks_date_shift.py:102` (deliberately `columns` only) | M |
| EC-9, EN-6 | `table_entry`, `column_entry`, `column_strategy` in new `E:config/_lookup.py`, one rule for a non-dict entry | named copies: `E:profile/_declared_columns.py:34`, `E:execution/_chunked_fk_runtime.py:65`, `_unified_slice_admission.py:163`, `native/_plan.py:405`, `_transforms_gate.py:28`, `_chunked_bucket_perturb.py:256`, `_chunked_code_set.py:215`, `_chunked_carry.py:191`; about 20 inline sites in EC-9 | M |
| EC-18, EN-10 | Relationship edge iteration and `child_key_pairs` in `E:relationships/` | `E:profile/_source.py:253-350`; `E:execution/out_of_core/_validate_batch.py:98-141`, `_vault_collect.py:106-136`; `E:execution/_faker_degenerate_pin.py:55-65`, `E:validators/_leak_check.py:131-148`; 28 files read `relationships` by hand | M |
| EC-5 | `_config_ref_columns(plan, registry, strategy, key)`; test the `joint_mask` kind filter first | `E:execution/_runner.py:153-255` | S |
| EC-16 | Use the plan's freeze and thaw; check the plan hash on the golden corpus first | `E:execution/physical/_inputs.py:49-86`, `E:plan/_types.py:333-364` | S |

### J. Determinism: full conversion (engine)

| Id | Refactor | Where | Size |
|---|---|---|---|
| EX-1, EN-3 | Route every digest-feeding `json.dumps` through one canonical module (after C3 and D3); keep byte-pinned legacy forms as named variants | owner `E:records/_canonical.py:18-26`; sites by variant in EX-1, including `E:phase.py:479-484`, `E:generation/_pinned_plan.py:200`, `E:profiling/model_pack/provenance.py:201`, `E:generators/derivation.py:183`, `E:plan/_compile.py:657`, `E:profile/_serialize.py:74` | M to L |
| EX-2 | Route all 68 generator constructions through new `E:determinism/_rng.py` (after D2) | by variant in EX-2. Inline `derive(...)[:8]`: `E:execution/_strategies/_shuffle.py:76-78`, `E:transforms/windowed_date.py:333-336`, `grouped_series.py:287-291`, `E:execution/native/protocol/providers_mask.py:212,243,297`. Unseeded: 18 calls in `E:providers_v2/identifiers/_*.py`, `providers_base.py:231`, `E:generators/_formula.py:192,262`, `E:generation/statistical/_sample.py:409`, `E:profile/_source.py:139`. Text-derived twin: `E:transforms/formula.py:54-55`, `providers_mask.py:327-330` (docstring at `formula.py` disagrees with the code) | L |
| EW-15 | Seed protocol version in one place across Python and Rust | `E:determinism/_derive.py`, `decoy-engine-native/src/derive.rs:40` | S |

### K. Data predicates (engine)

| Id | Refactor | Where | Size |
|---|---|---|---|
| ED-1 | `is_text`, `is_text_or_null`, `is_binary_like` in new `E:_arrow_types.py` (after D5) | 21 files in ED-1; private helpers at `E:execution/_chunked_profile.py:248`, `_mem_estimate_arrow.py:100` | M |
| ED-2 | `is_null_cell` in one place | helpers `E:kernel/_scalar.py:14`, `E:quality/carrier_adapter.py:194`, `E:transforms/derived.py:208`, `windowed_date.py:209`, `E:profiling/profiler.py:76`; inline at `E:execution/_pandas_adapter.py:656`, `_strategies/_date_shift.py:275`, `_nested.py:322`, `_tokenize.py:136`, `_top_code.py:325`, `E:transforms/formula.py:57`, `E:profiling/sentinels.py:104`, `E:generators/_formula.py:206`, `E:execution/_fk_keys.py:97,356` | M |
| ED-4 | `coerce_datetimes` for the unformatted parses (with A6, A13) | `E:profiling/_date_sniff.py:25-31`, `_distributions.py:70`, `sentinels.py:116`, `E:validators/_relationship_checks.py:142,143,152`; owner `E:internal/pandas_compat.py:46` | S |
| ED-5 | `is_finite_real` and the DP knob validators (with A7) | `E:quality/dp.py:206`; `E:plan/_checks_dp.py:111-121`, `:522-532`; `E:config/_generate_options.py:222`, `_generate_type_checks.py:54`, `E:telemetry/_vocab.py:101`, `E:_progress_events.py:48` | M |
| EN-8 | `is_exact_int`, `is_count`, `is_json_number` | `E:generation/statistical/_cell_format.py:72`, `_fanout.py:134`, `E:reasons/_record.py:100`, `E:verification/canary/_types.py:142`, `E:config/_generate_options.py:99,103`, `_generate_type_checks.py:59`, `E:generation/_numeric_typing.py:81`, `kinds/_output_type.py:113`, `E:telemetry/_recorder.py:40`, `E:generation/pool/_errors.py:68` | M |
| ED-8 | `utc_now()` with a test override (after C8) | `E:profile/_source.py:169`, `E:profiling/scan_set.py:283`, `types.py:193`, `sentinels.py:176` (`date.today()`), `E:quality/report.py:257`, `E:verification/postmask/runner.py:167`, `E:generators/columns.py:74` | S |

### L. Out-of-core and native plumbing (engine)

| Id | Refactor | Where | Size |
|---|---|---|---|
| EC-4 | Rest of the shared rewrite pass (tracker, deferred commit, resident tail); settle the cleanup difference | `E:execution/out_of_core/_rewrite_pass.py:64-325`, `_stream_driver.py:125-565` | M |
| EN-5 | One `topo_order(nodes, deps, tie_break, ignore_self)` (after A11) | `E:execution/out_of_core/_route_policy.py:216-245`, `E:execution/_sequential_order.py:18-60`, `E:relationships/_graph.py:~270-310`, `E:execution/_runner.py:~465-500`, `E:generation/synthesize.py:255` | M |
| EC-24 | One kernel loader and probe; fail-closed code, test every stage | `E:execution/native/_group_key_ext.py:135-267`, `_index_ext.py:124-264`, `_crypto_ext.py:394-428`, `_companion_status.py:153-220`; `E:execution/out_of_core/_hash_run.py:254-321` | M |
| EP-7, EC-17 | Pass `PipelineRunContext` to route executors instead of unpacking it | `E:execution/_pipeline_route_dispatch.py:3-8`, `_pipeline_route_exec.py`, `_sequential.py`, `out_of_core/_runner.py`; `_pipeline_context.py:536-549`, `pipeline/_stream.py:133-146`; `capacity.py:357-372`, `:419-434` | M to L |
| EW-9 | One export point for a new public function | `E:__init__.py`, `E:execution/__init__.py`, `E:profile/__init__.py`, `E:profiling/__init__.py`, `E:fileaccess/__init__.py:97` | M |

### M. Generation and providers (engine)

| Id | Refactor | Where | Size |
|---|---|---|---|
| EC-10 | Composite base (`generate_bundle`, `_check_pool_size`, `_POOL_SIZE_MAX`) | `E:generation/composite/_address.py:63-184`, `_custom.py:156-283`, `_name_email.py:43-224`, `_person.py:39-242`, `_provider.py:71-207` | M |
| EC-6 | Identifier adapter base (after A9); the capability matrix must stay byte-identical | `E:providers_v2/identifiers/_cusip.py:166-225`, `_ein.py:176-235`, `_iban.py:220-279`, `_icd10.py:103-162`, `_ndc.py:115-174`, `_npi.py:107-166`, `_pan.py:109-168`, `_ssn.py:134-198`, `_mrn.py:107-183` | M |
| EP-8, EW-8 | A generate-type registry that `synthesize.py` and the stage modules dispatch through. GEN-TYPES and GEN-PROVIDERS (rows 24q, 24p) add types now; if either row's PLAN can take this, move it to V1 | `E:config/_tables.py:330-335`, `E:generation/synthesize.py:324`, `_admission.py`, `_bounds.py`, `_streamed.py`, `_statistical_column.py`, `_pinned_execute.py`, `window.py` | M |
| EC-27 | One private `_run` behind the four generation entries (after A12) | `E:generation/_plan_entry.py:179-350` | S |
| EC-11 | Windowed CSV base for S3 and GCS; connector mixins. CLI-CLOUD (row 64) and F02 (row 87) touch these files: do it in their PLAN or after | `E:profile/_cloud_readers.py:271-291`, `:298`, `:374-394`, `:401`; `E:connectors/gcs.py:114-129`, `:198-211`; `E:connectors/s3.py:198-210`, `:301-312` | S |

### N. CLI

| Id | Refactor | Where | Size |
|---|---|---|---|
| CX-1 | Move the remaining error sites to `emit_error` and empty the D7 baseline | about 49 print lines in 23 files and 40 payloads in 19 files (CC-2) | L |
| CX-2 | Remaining `parse_pipeline_config` call sites share one except list | `C:api.py:476`, `C:cli/report.py:1762`, `:2022`, `C:cli/gate/_layers.py:148`, `C:cli/tokenize.py:259`, `:579`, `C:cli/init.py:409`, `C:cli/demo.py:230`, `C:cli/subset.py:181`, `C:cli/preflight.py:456`, `:728` | M |
| CX-3 | `write_json_artifact(path, doc, indent=2)` | `C:cli/fit.py:737`, `C:cli/gen/_scaffold.py:229` (`indent=1`); `C:cli/demo.py:155`, `C:cli/report.py:1815`, `:2063`, `C:cli/run/_evidence.py:36`, `C:cli/scanning/_multi.py:457`, `C:cli/setup/__init__.py:103`, `C:cli/schema.py:72` | S |
| CP-2 | Generate the `explain` topics for flags from the option definitions, or test them against it | `C:cli/explain.py:167`, `:207`, `:331-364`, `:441`; `C:cli/run/__init__.py:137` | M |
| CE-2 | One Windows device-name table | `C:_atomic.py:117-124`; engine `E:config/_pipeline.py:61-68` | S |
| CE-3 | Use the engine's `protected_scratch_dir`; already tied to WIN-FEAS (row 89) in the baseline | `C:cli/run/_prepare.py:300`, `C:cli/run/_flow.py:75`, `C:ci/engine_logging.py:29` | S |
| CX-7 | Vault commit to its own module; already tied to LIB L5a in the baseline | `C:cli/run/_vault.py:62-97` | S |

### O. Leave as they are

Judged benign or deliberate; listed so nobody re-triages them. Engine: the BENIGN table in
[engine-clones.md](engine-clones.md) (about 20 groups, including the FF1 encrypt and decrypt
pair, the physical-seam delegating drivers, strategy handler boilerplate and the
`profiling/eval/fixtures.py` Luhn oracle), EX-6 to EX-9, ED-11 to ED-14, EN-18 and EN-20 to
EN-22, EP-10 to EP-16. CLI: CC-8, CC-9, CX-6, CX-10, CE-5, CP-3, CP-4.

---

## 5. Not covered

- The platform repo, all test code and the Rust crate were not scanned.
- ED-15 (`decimal`, `to_numeric`) and the 10 `is_extension_array_dtype` sites were not read.
- For concerns with many sites the triage read a sample; counts marked "about" come from search.
- `DECOY_PROJECT` is named at `C:cli/io/_project.py:120` and nothing reads it yet. It is planned
  work in PROJECT-LAYOUT (row 24t), not a finding.
- No roadmap rows were added. Packages A to G are sized to become rows or to ride inside the
  rows named in their notes.
