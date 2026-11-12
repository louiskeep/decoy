# Engine primitive call census, slice b1 (hashing/HMAC, JSON, RNG, encodings, caching)

Scope: `/home/user/decoy-engine/src/decoy_engine`. Input: `census/in/engine_calls_b1.txt`.
Guard-test survey: `tests/sentry/` has NO test that scans `src` for `hashlib`, `hmac`, `json.dumps`, `json.loads`,
`default_rng`, `random.Random`, `uuid` or `lru_cache` (checked by grepping tests/sentry; the hits there are
the tests' own hashing of repo files). Related guards that DO exist and are cited below:
`test_secret_material_census.py` (AST census of key-holding locals), `test_file_access_boundary.py` +
`file_access_registry.toml` (sinks), `tests/native/test_draw_sites_catalogue_pinned.py` (pins the RNG draw-site
catalogue by digest, does not scan source). YAML: no yaml target appears in this slice's input file; not assessed.

Ordering is by value (correctness risk x number of sites).

---

## EX-1  Canonical JSON bytes feeding a digest   -- verdict: CENTRALIZE

Sites: about 19 hash-feeding `json.dumps` calls (plus ~15 non-hashing `json.dumps` that are fine), 14 packages.
`json.dumps` total in slice: 34 calls / 25 files / 14 packages.

Existing owner (partial): `records/_canonical.py::canonical_bytes` / `sha256_tag` / `payload_digest`
(sort_keys, compact separators, `ensure_ascii=False`, `allow_nan=False`). Its docstring calls it "the one
canonical JSON form", but it is scoped to records. Nothing else uses it for config/plan/profile hashing.

Variants found (each is a hand-rolled `json.dumps(...)` whose result is hashed or MACed):
- A. sort_keys + compact separators, default ensure_ascii (True), no `default=`:
  `generators/derivation.py:183` (`strategy_config_fingerprint`), `generation/_pinned_plan.py:200` (`_canonical`),
  `phase.py:481` (`_encode`), `profiling/model_pack/provenance.py:201` (HMAC input).
- B. same + `default=str`: `generation/_reproducibility.py:204` (`build_envelope` config digest).
  `generation/_reproducibility.py:163` (`PinnedEnvelope.digest`) is sort_keys + compact over a list.
- C. `ensure_ascii=True` explicit, no `default`: `plan/_compile.py:657` (`pipeline_config_hash`),
  `profile/_serialize.py:74` (`profile_hash` bytes).
- D. `ensure_ascii=True` + `default=str`: `generation/pool/_builder.py:41` (`_config_hash`).
- E. `ensure_ascii=False`, `allow_nan=False`: `records/_canonical.py:20`.
- F. sort_keys only, DEFAULT separators (", ", ": "), `default=str`, then the resulting string is hashed elsewhere:
  `plan/_generation.py:329` (`config_json`, hashed at `execution/physical/_compiler.py:382` and checked at
  `execution/physical/_shadow_generation.py:213`), `generation/_pinned_compile.py:295` (`spec_json`, hashed at
  `_pinned_plan.py:230`) and `:315` (`config_json`).
- G. sort_keys + `indent=2` + `default=str`, hashed: `profiling/model_pack/trainer.py:592-593`
  (`eval_report_hash`). On-disk manifest uses `indent=2, sort_keys=True` without default at `provenance.py:184`.
- H. sort_keys + `default=repr`: `execution/physical/_inputs.py:94` (`_canonical_config_json`, feeds `plan_hash`).
- I. framed headers with sort_keys, default separators, then SHA-256/Fernet framing:
  `declared_casting/_quarantine_local.py:251,265,327`, `vault.py:320`.
- J. no sort_keys, but input is a list so order is fixed (fine): `secret_providers/_types.py:90,296`,
  `generators/derivation.py:92`.

`allow_nan`: only variant E sets `allow_nan=False`; every other variant emits bare `NaN`/`Infinity` tokens if a
float nan reaches it (json.dumps default). Not a line-level bug, but the same config hashes by different
rules in different places.

Risk (read and confirmed at the lines):
1. Inconsistent `default=` policy on config digests. `plan/_compile.py:645-656` carries a comment (QA F9) that
   deliberately REMOVED `default=str` because it makes `str()`-equal values collide and hides non-native types.
   Siblings kept it: `_reproducibility.py:204`, `pool/_builder.py:41`, `plan/_generation.py:329`,
   `_pinned_compile.py:295,315`, `_inputs.py:94` (`repr`). Consequence: the same config object either raises
   `TypeError` (variant C/A) or silently stringifies (B/D/F/H) depending on the digest. `str()`/`repr()` of an
   object with a default `object.__repr__` embeds a memory address, which would make that digest
   non-deterministic; `str()` of a `set` is hash-order dependent. UNVERIFIED whether any such value reaches
   these sites in production: `config/_global_settings.py:131` shows YAML timestamps are normalised to text for
   `reference_date`, so the F9 comment's claim "yaml.safe_load is JSON-native only" is not true in general
   (safe_load yields `datetime.date`/`datetime` for unquoted timestamps); other date-valued fields would hit the
   TypeError path in `_compile.py:657` but be silently coerced in the `default=str` paths.
2. Platform parity: `records/_canonical.py` docstring says its form matches the platform's canonical JSON
   (`ensure_ascii=False`); the engine's own config/profile hashes use `ensure_ascii=True`. Two "canonical" forms
   in one library. Whether the platform repo hashes any of the engine's values with its own form: UNVERIFIED.
3. `build_envelope` (`_reproducibility.py:180`) has no caller in `src` (only tests: tests/parity, tests/unit);
   its digest rules therefore are not exercised by production paths. Worth knowing before converting it.

Proposed choke point: extend `records/_canonical.py` (or hoist to `decoy_engine/_canonical.py`, a leaf next to
`_value_free.py`) with `canonical_json_bytes(value, *, ascii_only: bool, strict: bool)` and
`digest_hex(value)`. Pick ONE policy for `default=` (recommended: none, raise `TypeError`) and keep any
byte-pinned legacy form as a named variant (`pinned_config_json` for `config_json`, since its string bytes are
hashed downstream and compat-pinned; do NOT change bytes without a compat bump).
Guard test (`tests/sentry/test_canonical_json_choke_point.py`): AST-scan `src` for `json.dumps(` calls that pass
`sort_keys=True` or are an argument chain into `hashlib.*`/`hmac.new`, and for `json.dumps(..., default=)`; fail
outside the owner module and a baseline `baselines/canonical-json-sites.json` (ratchet: may only shrink).
Size: M to L (about 19 call sites; byte-pinned ones need golden-digest tests first; the pinned compat corpus
`tests/integration/compat_corpus/` will catch drift).

---

## EX-2  RNG construction and seed derivation   -- verdict: CENTRALIZE (catalogue exists, no source guard)

Sites: `numpy.random.default_rng` 45 calls / 28 files / 9 packages; `random.Random` 23 calls / 14 files /
8 packages; plus `secrets` (EX-8). Total 68 construction sites.

Existing owner (partial): `determinism/_derive.py` (`derive`, `derive_index`), `generators/derivation.py::
GenDeriveContext` (`base_int(family)`, `row_int`), and the DRAW_SITES catalogue
(`execution/native/_draw_sites_*.py`, 39 entries pinned by `tests/native/test_draw_sites_catalogue_pinned.py`).
The catalogue documents sites by `call_site="file:line"` strings but no test scans source for new
`default_rng(`/`random.Random(` calls, so a new RNG can appear without a catalogue entry. Line numbers in
`call_site` strings can also drift silently (UNVERIFIED whether a test checks them).

Seed-derivation variants (distinct ways the seed is produced):
- V1 `GenDeriveContext.base_int(family)` (full 256-bit, per column/family): `generation/_column_streams.py:142,206,228`,
  `kinds/_parametric.py:64`, `native/protocol/providers_gen.py:34,62,111,133`, `providers_gen_unique.py:23`,
  `generators/columns.py:219,410,505`, `generation/_unique.py:43,176`, `synthesize.py:434,563`,
  `_synthesize_derived.py:147,207`.
- V2 mask side `int.from_bytes(derive(mask_key, ns, src)[:8], "big")` written inline each time (truncates to 64 bits):
  `execution/_strategies/_shuffle.py:76-78`, `transforms/windowed_date.py:333-336`,
  `transforms/grouped_series.py:287-291`, and the mirrored copies in `native/protocol/providers_mask.py:212,243,297`
  (`seed_int`/`group_seed_int`/`row_seed_int`). `determinism/_derive.py:338` has the same idiom inside
  `derive_index` but there is no `derive_seed_int` helper to call.
- V3 raw bytes with NO length check: `int.from_bytes(seed, "big")` at `generation/composite/_person.py:143`,
  `_name_email.py:135`, `_address.py:97`, `_provider.py:117`, `_custom.py:207`, `providers_gen.py:75`.
  The pool path enforces exactly 8 bytes via `_seed_bytes_to_int` (`generation/pool/_sampler.py:168-190`, raises
  `INVALID_SEED_LENGTH`); used at `_sampler.py:270,518` and `_faker_pool.py:459`. Composite sites bypass it.
  Composite falls back to `b"\x00"*8` when `spec.seed is None` (`_person.py:142`), i.e. a fixed seed, not random.
- V4 raw column `seed` int handed in: `generators/_distribution.py:141,266,386` (origin is `base_int("np")` at
  `_distribution.py:65`), `generators/columns.py:68` (`random.Random(self.seed)`, the raw job seed).
- V5 raw key prefix: `transforms/joint_mask.py:338,367` seeds `default_rng(int.from_bytes(job_seed[:8], "big"))`
  where `job_seed` is `ctx.mask_key` (`execution/_strategies/_joint_mask.py:123`, doc at `joint_mask.py:311`: "the
  keyed-mask IKM"). No namespace/column separation and the first 8 bytes of the key material are the seed.
- V6 unseeded: 18 `np.random.default_rng()` in the nine `providers_v2/identifiers/_*.py` adapters (two each,
  e.g. `_cusip.py:197,206`), `native/protocol/providers_base.py:231` (`UnseededProvider.fresh_generator`),
  `random.Random()` at `generators/_formula.py:192,262` and `generation/statistical/_sample.py:409`
  (the last three are reseeded per row at `_formula.py:198,267`, `_sample.py:363,432,469,507,535`),
  `profile/_source.py:139` (unseeded when `seed is None`, after a `warnings.warn`).
- V7 constant: `execution/_chunked_profile.py:46,136` `random.Random(0)`; `profiling/eval/fixtures.py:226`.
- V8 text-derived: `transforms/formula.py:54-55` and `native/protocol/providers_mask.py:327-330` both compute
  `int(sha256(f"{column}|{formula}").hexdigest()[:16], 16)` (duplicate, must stay byte-equal); documented
  "independent of mask_key by design" in the providers_mask docstring.
- V9 per-row legacy `rng.seed(col_seed + start + i)`: `generation/statistical/_sample.py:363,432,469,507,535`,
  `providers_gen.py:178`. With full-width `col_seed` this does not collide in practice.

Risks (read at the lines):
1. `transforms/joint_mask.py:338,366-367` (V5): every joint_mask column in a job, in both mask-mode null-key
   fallback and gen mode, starts from the identical PCG64 stream (no namespace or column in the seed), so two
   joint_mask columns with the same table and row count pick the same row indices; and the first 64 bits of the
   mask key (or the verbatim 8-byte job seed when no secret) are used as an RNG seed whose outputs (reference-row
   indices) are observable. Not reached through `derive()` like every other mask-side RNG (V2). I did not
   confirm whether this is intentional (the column correlation may be wanted for "joint" semantics).
2. `transforms/formula.py` module docstring says output is "a pure function of (formula text, the column's
   deterministic seed)" but the code at line 54-55 uses only column name and expression, no seed. Output does not
   change with `job_seed`/`mask_key`. Stable, but the docstring and code disagree (and the duplicate in
   providers_mask.py:327 documents "by design").
3. Legacy `generators/_distribution.py:65,141,266,386` draws the value stream from `default_rng(base_int("np"))`
   and `generators/columns.py:219` draws the null mask from `default_rng(base_int("np"))` on the same column
   (`null_probability` applies to every column type). `generators/derivation.py:186-198` documents that
   exactly this sharing is the reason the "dist" family exists. I checked with numpy: `rng.random(n) < p` and
   `rng.choice(k, size=n, p=...)` from the same seed put every null row in bin 0 (output of a 20000-row run:
   null rows per bin [1966, 0, 0, 0] vs non-null [3126, 5005, 4934, 4969]). Reachability from a plan:
   `synthesize.py:343` routes `kind == "distribution"` elsewhere (the `kinds/_parametric.py` "dist" path), so this
   is reachable at least via direct `ColumnGenerator.generate_column(type="distribution", snapshot=...,
   null_probability>0)`. Whether any plan path still reaches it: UNVERIFIED. Draw site `gen.distribution_snapshot`
   (`_draw_sites_gen.py:207`) is catalogued with family "np".
4. Unseeded `default_rng()` x19 and `random.Random()` x4 cannot be injected in tests; they are all deliberate
   (S4 random-by-default contract, `_draw_sites_provider_backed.py:119`), but nothing prevents a new unseeded
   RNG from appearing in a deterministic path.

Proposed choke point: `decoy_engine/determinism/_rng.py` with `generator_from_key(mask_key, ns, source) -> Generator`
(V2 idiom, one place for `[:8]`), `generator_from_seed_bytes(seed: bytes)` (length-checked, absorbs V3/V4),
`python_rng_from_int(n)`, and `unseeded_generator()` (V6, the only place that may call `default_rng()` with no
argument). Keep the catalogue as the documentation layer and make it the allowlist.
Guard test: AST-scan `src` for `default_rng(`, `random.Random(`, `np.random.seed`, `SystemRandom` outside
`determinism/_rng.py`, `generators/derivation.py`, and a ratcheted baseline `baselines/rng-construction-sites.json`
whose entries each name their DRAW_SITES id; plus a check that every DRAW_SITES `call_site` file:line still
contains an RNG construction.
Size: L for a full conversion (68 sites); S to M for the first step (sentry with baseline of the current 68, plus
the V2 helper for its 7 call sites and the unseeded helper for its 19).

---

## EX-3  Keyed derivation (HMAC / HKDF)   -- verdict: ALREADY-OWNED, with stragglers

Sites: `hmac.new` 16 calls / 12 files / 9 packages; `hmac.compare_digest` 3 sites (see EX-6).

Owner: `determinism/_hkdf.py` (RFC 5869) and `determinism/_derive.py` (`derive`, `derive_source`,
`derive_sources`, `derive_index`). HKDF is genuinely centralised: `context.py:351` was a divergent copy and was
rewired to `hkdf_sha256` (docstring records QA Q11); every other HKDF caller imports `determinism._hkdf`
(`keyprovider.py:40`, `_quarantine_local.py:34`, `provenance.py:119`, `_derive.py:51`). Secret lifetime for these
functions is guarded by `test_secret_material_census.py`.

Stragglers (same job, separate code):
- `generators/derivation.py:218` `_gen_hmac`: byte-for-byte copy of the version||len||label||len||extra framing in
  `determinism/_derive.py:240,254` (its docstring says "mirrors ... byte-for-byte"). Drift risk, not a bug today.
- HMAC-hex of `str(value)` with `errors="replace"`: `internal/crypto.py:55` (`hmac_hex`) and its mirror
  `execution/native/protocol/providers_mask.py:53` (`_hmac_hex`); `internal/crypto.py:70` `hmac_seed` takes
  `digest[:4]`; `transforms/date_shift.py:123` takes `digest[:8]` of an HMAC over `val.encode(..., errors="replace")`.
- Text-mask span key: `transforms/text_mask.py:260` uses `matched_text.encode("utf-8", errors="replace")`;
  the "verbatim" copy at `execution/native/_draw_site_providers.py:114` uses `matched_text.encode("utf-8")` with no
  `errors=`. They differ for a string containing a lone surrogate (strict encode raises `UnicodeEncodeError`,
  replace yields `?`). I did not find a test or caller proving the two are exercised on such input.
- `transforms/_text_mask_synthetic.py:26` counter-mode HMAC stream with its own label.
- Distinct purposes, not stragglers: `_quarantine_local.py:405` token MAC, `provenance.py:232` manifest signing,
  `secret_providers/_types.py:91` per-process salted cache key.
- Legacy unkeyed: `transforms/date_shift.py:112` `hashlib.md5` (documented legacy fallback, `# noqa: S324`) and
  `internal/crypto.py:39` `hashlib.sha256(f"{value}{seed}")` (emits `DeprecationWarning`; no callers found by
  grep in `src`).
- Unkeyed fallback root: `generators/derivation.py:299` `sha256(seed8 || fingerprint || identity)` (no
  length framing; `fingerprint` is fixed-length hex so not ambiguous today).

Proposed: make `derive_source`-style framing public once (`determinism._derive.frame_hmac(key, label, extra)`)
and have `_gen_hmac`, `internal/crypto.hmac_*`, `_hmac_hex`, `_span_key` call it; one `utf8_for_mac(value)` helper
for the `errors="replace"` rule. Guard: ban `hmac.new(` outside `determinism/` plus an explicit allowlist (the
three distinct-purpose sites).
Size: S (about 8 call sites to convert).

---

## EX-4  Snapshot/file content digest and the `sha256:` tag   -- verdict: CENTRALIZE (small)

Sites: `hashlib.sha256` 32 calls / 22 files / 14 packages in total; this concern is the 6 that digest file bytes
(`generation/statistical/_spec.py:203`, `plan/_generation.py:215`, `generators/derivation.py:141`,
`plan/_serialize.py:321`, `profiling/model_pack/loader.py:295`, `trainer.py:549,644`) plus 5 hand-built tag sites.

Variants:
- The snapshot read -> sha256 -> `json.loads` -> schema check sequence exists in three places: `_spec._load_snapshot`
  (`_spec.py:175-225`), `plan/_generation.read_and_pin_snapshots` (`_generation.py:215-228`), and
  `derivation._snapshot_content_digest` (read + hash only). All read through `fileaccess.read_all` (owned),
  but the hash and parse are repeated.
- Digest shape: bare hex everywhere except `derivation.py:141` which returns `"sha256:" + hex`. The
  `sha256:<hex>` string enters the per-column fingerprint and therefore the seed (`derivation.py:183`), so the exact
  shape matters. It is rebuilt by hand with an f-string in `generation/statistical/_fanout.py:67`,
  `generation/_statistical_column.py:83`, `generation/synthesize.py:385`, `generation/window.py:201`,
  `generation/_pinned_compile.py:313`. `records/_canonical.sha256_tag` is a sixth, unrelated spelling of the tag.
- Model pack: `loader.py:295-296` and `trainer.py:644-645` compare bare hex with `!=` (integrity of a file whose
  manifest is separately HMAC-verified; not a secret compare).

Risk (confirmed): `json.loads(raw)` is called on BYTES at `_spec.py:205` and `plan/_generation.py:217`, but only
`json.JSONDecodeError` is caught. I ran `json.loads(b'\xc3\x28')`: it raises `UnicodeDecodeError`, which is not a
`JSONDecodeError`. A snapshot file with invalid UTF-8 therefore escapes as an uncoded `UnicodeDecodeError`
instead of `STATISTICAL_SNAPSHOT_UNREADABLE`. (Contrast `vault.py:482` and
`_faker_deterministic_admission.py:169`, which catch it.) Error-handling hazard, not a determinism one.

Proposed choke point: `generation/statistical/_snapshot_io.py` (or in `fileaccess` adapters): one
`read_snapshot_bytes -> (sha256_hex, parsed)` that owns the decode error mapping, and one
`seed_digest_tag(hex) -> "sha256:<hex>"`. Guard: ban the literal `f"sha256:` / `"sha256:" +` outside that module
and `records/_canonical.py`.
Size: S.

---

## EX-5  Strict vs plain JSON loading   -- verdict: CENTRALIZE (small)

Sites: `json.loads` 38 calls / 24 files / 15 packages. Most are fine one-offs (round-tripping our own
`config_json` strings at `_pinned_execute.py:82,84,105,113,130,139,205,224`, `_pinned_plan.py:220`,
`_plan_entry.py:101`; framed headers; cache keys at `_catalog.py:298,473,478`).

Duplicate strict parsers: `records/_codec.py:161-181` (`_no_duplicates`, `_refuse_constant`, `json_object`) and
the inline copy in `execution/native/_faker_deterministic_admission.py:153-171` (`_reject_duplicate_keys`,
`_reject_constant`). Same behaviour (duplicate keys and NaN/Infinity rejected, UTF-8 and ValueError mapped to
`None`). These are the only two uses of `object_pairs_hook`/`parse_constant` in `src`.

Plain parsers over untrusted or externally supplied JSON (last duplicate key wins, `NaN` accepted):
`plan/_serialize.py:342,434` (untrusted plan manifest, says so in its docstring), `profiling/model_pack/loader.py:256`,
`provenance.py:168`, `trainer.py:633`, snapshots (EX-4), `_quarantine_local.py:426,478,506`.
Whether duplicate-key acceptance matters for any of these: UNVERIFIED (no downstream use was traced).

Error handling varies: `except json.JSONDecodeError` only (`_spec.py:205`, `plan/_generation.py:217`,
`_isolated_commit.py:133`, `_shadow_generation.py:248`, `profile/_serialize.py:44`); `(UnicodeDecodeError, ValueError)`
(`vault.py:482`, `_faker_deterministic_admission.py:169`); `except Exception` (`_nested.py:325`,
`connectors/_clients.py:137`).

Proposed: promote `records/_codec.json_object` to a shared leaf (`decoy_engine/_json_strict.py`) with
`loads_strict(data) -> Any | raises JsonRefused`, use it for the two duplicates and the untrusted-manifest loaders.
Guard: none needed beyond a unit test; a sentry banning `json.loads` would be too broad (38 sites, mostly benign).
Size: S (2 duplicates + ~4 untrusted loaders).

---

## EX-6  Constant-time comparison   -- verdict: FINE (already correct)

Sites: `hmac.compare_digest` 3 sites / 3 packages: `profiling/model_pack/provenance.py:265` (manifest MAC),
`declared_casting/_quarantine_local.py:463` (quarantine token MAC), `vault.py:251` (key match). I grepped
for `==`/`!=` against MAC, token, signature and key names and found none comparing secret material. The
`!=` on bare digests at `plan/_serialize.py:321`, `_quarantine_local.py:488`, `loader.py:296`, `trainer.py:645`
compare content hashes of data, not MACs. No action.

---

## EX-7  Short random names for staging files/dirs and run ids   -- verdict: FINE (sinks are owned)

Sites: `uuid.uuid4` 4 calls / 4 packages (`connectors/postgres_snapshot.py:454`, `execution/_isolated_commit.py:61`,
`execution/native/_pool_quality.py:245`, `quality/dp.py:408`); `secrets.token_hex` 6 calls / 2 packages
(`fileaccess/_local.py:257`, `_output.py:304`, `_protected_dir.py:304`, `declared_casting/_quarantine_local.py:215,248`,
`_boundary.py:192`).
Variants: `uuid4().hex` (full or `[:12]`) vs `token_hex(6|8|16)`. Uses: temp/staging names (7), a run id (2), a
token salt (1), and `quality/dp.py:408` a release id that is a non-deterministic artifact identity (documented in the
comment above it). The directories and files created from these names are governed by
`fileaccess/` and registered in `file_access_registry.toml` / `file_access_modules.toml`
(`postgres_snapshot.py` and `_isolated_commit.py` are listed as ambient-only modules); the name generator itself
has no shared helper. Low value to centralise; none of these feed a hash or an RNG.

---

## EX-8  Memoisation (`functools.lru_cache`)   -- verdict: FINE

Sites: 11 calls / 9 files / 8 packages. All are pure memoisation of derived read-only objects, keyed by
hashable strings: `declared_casting/_catalog.py:296,471,476` (keyed by sorted JSON of a format spec),
`_date.py:25`, `execution/native/_text_mask_native_fpe.py:56` (`maxsize=1`, caches `None` after a failed kernel load
for the process life, by design per its docstring), `expressions/_when_parser.py:222` (only successes cached),
`generation/composite/_city_state_zip.py:38`, `generation/kinds/_output_type.py:71`, `plan/checks/_generate_columns.py:146`
(returns one shared Faker object plus provider names; stateful object shared across calls, I did not check that
nothing seeds or draws from it: UNVERIFIED), `reason_adapter.py:115`, `safe_output/_exception.py:71`.
No shared rule applies. The `_catalog.py` JSON-blob-as-cache-key trick (`json.dumps(..., sort_keys=True, default=str)`
at `:293,482`) is a variant of EX-1's `default=str` but affects only cache hits, not output bytes.

---

## EX-9  base64 / struct / framing   -- verdict: FINE

`base64.b64decode` 4 calls / 3 packages: `plan/_serialize.py:320` (non-strict, then SHA-256 verified),
`generation/_plan_entry.py:127` (decodes and re-parses the same pinned snapshot bytes the plan already holds,
redundant but harmless), `secret_providers/_requirements.py:145,163` (`validate=True`). `struct` is used only in
`_quarantine_local.py` (7 calls). There are two length-prefixed container codecs, `vault.py:109-124`
(`_frame`/`_read_frame`, 4-byte big-endian) and `_quarantine_local.py:252,312,332,425-485` (`struct ">I"`); same
wire idea, different formats, each with its own tests. No central rule warranted.

---

## Non-crypto and identifier hashes   -- verdict: FINE

`hashlib.sha1(..., usedforsecurity=False)` at `quality/synth_report.py:425` (a set-membership key, commented as
non-cryptographic). `hashlib.md5` at `transforms/date_shift.py:112` (see EX-3). `declared_casting/_quarantine_local.py:102,106`
(`_owner_hash`, `_run_hash`: truncated to 32 hex chars; `_run_hash` mixes a `b"run:"` prefix and `_owner_hash`
does not, so the two domains are separated only by the extra prefix on one side). `execution/physical/_shadow_snapshot.py:49`,
`_inputs.py:258,344`, `_activation.py:140`: SHA-256 over `repr(...)` of tuples; the tuple parts I read are primitives,
sorted tuples, strings and bools (`_inputs.py:258,327` sort their dict/set contents), so I found no hash-order
dependence. `quality/dp_provenance.py:185` hashes a sorted `name==version` text, deterministic.

---

## Summary table

| ID | Concern | Verdict | Sites | Packages | Size |
|----|---------|---------|-------|----------|------|
| EX-1 | canonical JSON feeding a digest | CENTRALIZE | ~19 hash-feeding (34 `json.dumps` total) | 14 | M-L |
| EX-2 | RNG construction and seed derivation | CENTRALIZE | 68 (45 + 23) | 12 | L (S-M first step) |
| EX-3 | keyed derivation (HMAC/HKDF) | ALREADY-OWNED + stragglers | 16 `hmac.new` | 9 | S |
| EX-4 | snapshot/file content digest and `sha256:` tag | CENTRALIZE | ~11 | 5 | S |
| EX-5 | strict vs plain JSON load | CENTRALIZE (small) | 2 duplicates + ~4 untrusted of 38 | 15 | S |
| EX-6 | constant-time compare | FINE | 3 | 3 | none |
| EX-7 | random staging names / ids | FINE | 10 | 6 | none |
| EX-8 | lru_cache | FINE | 11 | 8 | none |
| EX-9 | base64 / struct | FINE | 4 + 7 | 3 | none |
