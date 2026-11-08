# V1+ sprints: readers, detectors, generators, meaning-preserving masks

Status: proposal (sprint outline for after CLI V1; nothing here is scheduled)

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.
Feature detail: [v2-v3-expansion-candidates.md](v2-v3-expansion-candidates.md) (X-01, X-08, X-09,
X-10). Effort and dependencies: [v2-v3-complexity-and-ecosystem.md](v2-v3-complexity-and-ecosystem.md).
V2 sprints: [v2-sprints.md](v2-sprints.md).

This document orders the V1+ features into sprints and gives each slice the inputs FRAME and PLAN
need, so a planner starts from a checked outline rather than a blank page. It does not replace the
plan: each slice still needs its own plan on disk, the gates its risk level requires, and the
research the development loop asks for (`/home/cam/dev-rules/development-loop.md`).

## Scope and starting conditions

- **Features:** X-01 Avro and ORC, X-09 secrets detection, X-08 international detectors and
  generators (not the region disguises, which are V2), X-10 meaning-preserving masks.
- **Starts after:** CLI-REL (row 94) and the D-4 launch engine freeze lifting. X-01 also needs
  CLI-FMT (rows 20 and 21) and CONFIG-EXPLICIT (row 22), which fix how the CLI reads and writes a
  declared format.
- **Size:** 11 to 14 slices, about 2.5 to 3.5 engineer-months at one slice per engineer-week
  (recalibrate with the measured rate).
- **Releases:** one engine point release per sprint, then a CLI repin. Each sprint ships on its
  own; none blocks another except where "Depends on" says so.

## Building ahead of CLI V1 (parallel track)

V1+ slices are built now, in parallel with CLI V1, through the standard dev loop, under three rules
so they cause neither V1 delays nor later rework:

1. **Dark.** A slice merges to main only if V1 behavior is unchanged: new capabilities are opt-in
   (not in default detector sets, starter configs or disguises). Defaults switch on after CLI-REL.
   Nothing merges during the D-4 launch freeze.
2. **No collisions with live V1 work.** A slice starts only when no live V1 branch writes its
   files, and it adds no reason codes until REG-RENUMBER (row 8) merges, because the registry
   chain is serial until then.
3. **Short-lived branches.** One branch per slice, rebased on main and merged; never a long-lived
   V1+ integration branch. V1 rows have priority in the gate queue.

**When each slice can start** (engine branches checked 2026-11-06):

| When | Slices | Why |
|---|---|---|
| Now | V1P-2.1 check digits; V1P-2.3 generators | `checksums.py` and `providers_v2/identifiers/` are touched by no live branch; no new reason codes |
| Now (REG-RENUMBER merged 2026-11-07) | V1P-3.1 email domain, V1P-3.3 card BIN, V1P-3.4 IP prefix | no live V1 branch writes their files; reason codes allowed, renumbered at merge |
| After STORM E1 (row 16) and a split of `detection/detectors.py` (1046 lines, over the engine maximum) | V1P-1.1, V1P-2.2, then V1P-3.2 and V1P-3.5 | STORM E1 rewrites `detection/` and `profiling/`; detectors cannot be added to an over-maximum file |
| After CLI V1 lanes clear | V1P-1.2, V1P-2.4 (census-limited `faker_setup.py`), V1P-4 | `scan.py` lane, SCAN-MULTI S3, F16; CLI-FMT and CONFIG-EXPLICIT; `feat/csv-source-reader` is rewriting the readers |

**Build status and branches.** Each slice has its own plan (in the engine's `docs/plans/`, named
`2026-11-06-v1plus-<slice>-...`) and a pair of branches: `plan/v1plus-<slice>-<name>` for the plan
and its review, and `feat/v1plus-<slice>-<name>` for the build, stacked on the plan. The engine
CHANGELOG entry for each slice says "V1+ track" and links back here.

| Slice | Repo | Plan branch | Build branch | State |
|---|---|---|---|---|
| V1P-2.1 check-digit schemes | engine | `plan/v1plus-p2.1-check-digit-schemes` | `feat/v1plus-p2.1-check-digit-schemes` | built, head `22ab5e51` (engine main `dd31ea91`, 0.19.0 with REG-RENUMBER, merged in 2026-11-07; changelog conflict only). Plan review PASS WITH CONCERNS (rev 2); code review PASS WITH CONCERNS (round 2, advisory fixed); T1 gates green on the new head, `registry_renumber.py --check` consistent. Still to do: Codex gate, T3 full suite on the merge head. Not merged (owner instruction 2026-11-07: do not merge) |
| V1P-2.3 national identifier generators | engine | `plan/v1plus-p2.3-national-id-generators` (stacked on V1P-2.1) | `feat/v1plus-p2.3-national-id-generators` | built, head `208f52f0`; plan review PASS WITH CONCERNS (rev 2); code review PASS WITH CONCERNS (4 P2, handled); T1 gates green. Still to do: Codex gate, T3 on the merge head. **Merge held until after CLI-REL** (owner decision: the new providers appear in the CLI cockpit listing) |
| V1P-2.4 truthful Faker locales | engine | `plan/v1plus-p2.4-faker-locales` (from main) | `feat/v1plus-p2.4-faker-locales` | built, head `de34b864`; plan review PASS WITH CONCERNS (rev 3); code review PASS WITH CONCERNS (5 P2, handled); T1 gates green. Still to do: Codex gate, T3 on the merge head. **Merge held until after CLI-REL** (owner decision). Rescoped after a probe: locales already work for Faker providers; this slice makes the advertised locales true and codes locale faults. Follow-ups: V1P-2.4b plan-compile locale check (after REG-RENUMBER), V1P-2.4c coherent non-US addresses (needs licensed postal data, e.g. GeoNames). Pre-existing defects found: seeded `address_city` pools in Italian locales depend on `PYTHONHASHSEED` (not reproducible); unseeded multi-locale `generate()` raises `TypeError` (unhashable cache key) |
| V1P-3.1 email keeps domain or domain class | engine | `plan/v1plus-p3.1-email-keep-domain` (from main `dd31ea91`) | `feat/v1plus-p3.1-email-keep-domain` | built, head `e010155a` (main `b5b1ad16` merged in). New strategy `email_mask` (`keep: domain` or `domain_class`); refused without a mask secret. Plan review PASS WITH CONCERNS (rev 2); code review PASS WITH CONCERNS, all findings fixed and re-reviewed. T1 gates all green (sentry 4286, tests 6041), registry consistent, no ratchet growth. Still to do: Codex gate, T3 on the merge head. Not merged (owner instruction 2026-11-07: do not merge) |
| V1P-3.3 card keeps BIN and valid Luhn | engine | `plan/v1plus-p3.3-card-keep-bin` (from main `dd31ea91`) | `feat/v1plus-p3.3-card-keep-bin` | built, head `60b7d802` (main `b5b1ad16` merged in). `fpe` option `keep_bin: 6 | 8` with `checksum: luhn`. Plan review PASS WITH CONCERNS (rev 2); code review PASS after one remediation round. T1 gates all green (sentry 4261, tests 3597), registry consistent, no ratchet growth. Owner item: option left out of `strategy_catalog()` until a `requires` field exists. Still to do: Codex gate, T3. Not merged (owner instruction 2026-11-07) |
| V1P-3.4 IP keeps subnet prefix | engine | `plan/v1plus-p3.4-ip-keep-prefix` (from main `dd31ea91`) | `feat/v1plus-p3.4-ip-keep-prefix` | built, head `ee6a4a5d` (main `b5b1ad16` merged in). New strategy `ip_prefix` (verbatim prefix + Crypto-PAn, reference vectors pass). Plan review PASS WITH CONCERNS (rev 2); code review FAIL then PASS after three remediation rounds. T1: all steps green except the sentry ratchet, which flags 3 `gcs-call-kwargs` rows (`OpaqueBox.open` calls, same as FPE's) needing an owner exception; tests 6934 passed; registry consistent. Owner items: the 3 rows; Crypto-PAn self-map rate (about 1 in 15 hosts unchanged at /24, documented) vs a non-reference variant. Merge held until after CLI-REL (published capability listing). Not merged (owner instruction 2026-11-07) |
| V1P-4.1 Avro and ORC, engine readers and writers | engine | `plan/v1plus-p4.1-avro-orc` | `feat/v1plus-p4.1-avro-orc` | built, head `ae2434d5` (engine main `b5b1ad16`). Opt-in `format: avro` and `format: orc`; hand-written Avro container framer (decoding stays in polars), hardened and fuzzed; ORC timestamp columns refused on read (pyarrow silently corrupts out-of-range values). Plan review FAIL, then PASS WITH CONCERNS; code review FAIL, then PASS WITH CONCERNS. T1: all green except the sentry ratchet, which flags exactly the one planned file-access-registry entry (in-memory Avro decode) needing an owner exception; sentry tests 4308 passed when run directly; tests 5682 passed; registry consistent. Owner 2026-11-08: the entry is approved for merge time (exception record in the plan, section 10); ORC timestamp columns stay refused. Follow-up for V1P-4.2: a minimum Avro chunk budget of about 4 MiB. Not merged (owner instruction 2026-11-07) |

## Defaults for every slice

These apply unless a slice says otherwise, so the slices below do not repeat them.

- **Risk: R2.** Detectors, masks and readers of untrusted files are privacy or security logic,
  and new config keys and reason codes are compatibility surface. R2 means a reviewed plan on
  disk, adversarial review and an exact-artifact gate.
- **Rules consulted (starting set):** `00-universal.md`, `risk-and-exceptions.md`,
  `development-loop.md`, `feature-dev.md`, `reuse-first.md`, `testing.md`, `security.md`,
  `api-and-compatibility.md`, `cross-cutting-concerns.md`, `documentation.md`, and the recurring
  defect catalog. Add `config-secrets-and-supply-chain.md` for any new dependency and
  `performance.md` for anything on the per-cell hot path. Read them during planning; do not
  recall them.
- **Registry and docs touch points:** new strategies, providers or detectors appear in
  `E:docs/capability-matrix.md` (regenerate with `scripts/gen_capability_matrix.py`; the drift
  guard enforces it) and `E:docs/strategies.md`. New refusals get reason codes in
  `E:src/decoy_engine/reasons/` in registry order (REG-RENUMBER, row 8).
- **Determinism:** every new mask must be a pure function of input, config and key, with a test
  that runs it twice and across the full-frame and chunked routes it is admitted to.
- **Route admission:** a new strategy or option states which routes admit it (full frame,
  chunked, sequential, out of core) and refuses the rest with a reason code at plan time, never at
  run time. See `E:docs/execution-backends.md`.
- **Dependencies:** licence check, lock update, SBOM and `pip-audit` clean before merge.
- **Close-out:** shipped-log entry, roadmap update, graph refresh and the plain-language Slack
  note, as the DOCUMENT phase requires.

## Sprint order

| Sprint | Theme | Slices | Why this order |
|---|---|---|---|
| V1P-1 | Detection foundation: secrets | 2 | Smallest and highest value; sets the pattern for adding detectors that V1P-2 reuses |
| V1P-2 | International identifiers | 4 to 5 | Builds on the detector pattern; extends `checksums.py`; generators pair with detectors |
| V1P-3 | Meaning-preserving masks | 3 to 5 | Uses V1P-2's phone and card work; each option is independent |
| V1P-4 | Avro and ORC | 2 | Independent of the others; waits on CLI-FMT, so it may run in parallel or last |

---

## Sprint V1P-1: Secrets detection (X-09)

**Goal.** `decoy scan` and `text_mask` find credentials (API keys, tokens, private keys, passwords
in connection strings) in columns and inside free text, and mask them by default.

### V1P-1.1 Secrets detector catalog

- **Repo:** engine. **Size:** 1 slice. **Depends on:** none.
- **FRAME**
  - Problem: production copies carry live credentials in config, log and integration columns;
    no detector finds them today.
  - Done when: a fixed list of credential kinds is detected at column level (scan) and as spans
    (text), each with a stated pattern source, and a labelled fixture set shows recall and false
    positive rate per kind.
  - Non-goals: checking whether a credential is live (no network calls, ever); entropy-only
    detection of unknown formats; secrets in binary files.
  - Reuse check: `E:src/decoy_engine/detection/_patterns.py` and `detectors.py` (the existing
    catalog), the `iter_spans` path in `transforms/text_mask.py`, and the labelled-fixture
    harness in `E:src/decoy_engine/profiling/eval/`.
- **PLAN**
  - Established solutions to search: Yelp detect-secrets plugins (Apache-2.0), gitleaks default
    rules (MIT), GitHub secret scanning partner patterns, TruffleHog detectors (AGPL: read for
    ideas only, copy nothing). Record which patterns are adapted and their licence attribution.
  - Design notes: one detector entry per credential kind in the existing catalog, not a new
    subsystem. Context words (for example `api_key=`) raise confidence; entropy is a tie-breaker,
    not a detector on its own.
  - Choke point: the detector registry the capability matrix reads. Guard: the drift-guard test
    fails when a detector is added outside the registry. Mutation: remove one entry from the
    registry while leaving its pattern; the guard must go red.
  - Placement: patterns beside the existing ones in `detection/_patterns.py` (or a
    `detection/_secrets.py` sibling if the census limit would be crossed); fixtures under
    `profiling/eval/` fixtures.
  - Acceptance: labelled fixtures with real-shaped, inert credentials per kind (vendor docs
    publish example keys); a false-positive set of high-entropy harmless strings (UUIDs, hashes,
    base64 images); recall and false positive rate recorded. Failure modes: catastrophic regex
    backtracking on long cells (add a time-bounded test on a 1 MB cell), overlap with `url` and
    `email` detectors (state the overlap rule).
  - Raw-value isolation: findings and reports never print the matched secret; extend the
    existing raw-value isolation sentry to the new detector ids.

### V1P-1.2 Secrets in scan output, starter config and disguises

- **Repo:** engine, then CLI. **Size:** 1 slice. **Depends on:** V1P-1.1.
- **FRAME**
  - Problem: detection alone does not protect users; scan must rank secrets as high severity and
    the starter config must mask them.
  - Done when: scan reports a secrets finding as its own severity class; the starter config
    (SCAN-MULTI S3) emits `redact` for secrets columns and `text_mask` with the secrets detectors
    for free-text columns; every disguise includes the secrets rule.
  - Non-goals: a new `secrets` strategy (redact and text_mask already cover it).
  - Reuse check: `starter_config` (row 28), disguise YAML in `E:src/decoy_engine/disguises/`.
- **PLAN**
  - Established solutions: how gitleaks and GitHub report severity and remediation text.
  - Choke point: the disguise loader; guard is a test that every shipped disguise names the
    secrets rule. Mutation: delete it from one YAML; the guard must go red.
  - Acceptance: an end-to-end CLI test where a CSV with an embedded key is scanned, the starter
    config is emitted and run, and the output contains no key (post-scan residual check).

---

## Sprint V1P-2: International identifiers (X-08, detectors and generators)

**Goal.** Detect, validate, generate and format-preserve the main non-US identifiers, and generate
locale-correct names, addresses and phone numbers.

### V1P-2.1 Check-digit schemes

- **Repo:** engine. **Size:** 1 slice. **Depends on:** none.
- **FRAME**
  - Problem: `E:src/decoy_engine/checksums.py` has seven schemes; international identifiers need
    more (mod 11 variants, Verhoeff, ISO 7064 mod 97-10 and mod 11-2, the UK NINO and NHS rules,
    Canadian SIN Luhn, Aadhaar Verhoeff, Spanish DNI letter, Italian codice fiscale check
    character, French NIR key).
  - Done when: each scheme validates and computes a check digit, with published test vectors.
  - Non-goals: detectors and generators (next slices).
  - Reuse check: the existing registry API (`validate`, compute) and its tests.
- **PLAN**
  - Established solutions: `python-stdnum` (LGPL-2.1) is already a core engine dependency and
    already backs `checksums.py`'s luhn, iban, isbn and ean schemes, so the new schemes use it
    for validation and, where it has one, its calculator. ISO/IEC 7064 for the mod schemes;
    government publications for NHS and TFN, whose calculators stdnum lacks. (Updated
    2026-11-06 after the code survey; see the slice plan.)
  - Choke point: the scheme registry in `checksums.py`; guard test enumerates schemes and checks
    each has test vectors. Mutation: register a scheme with no vectors; guard goes red.
  - Acceptance: published test vectors per scheme, plus property tests (compute then validate
    round-trips; single-digit and transposition errors are caught where the scheme promises it).

### V1P-2.2 International detectors

- **Repo:** engine. **Size:** 1 to 2 slices. **Depends on:** V1P-2.1, V1P-1.1 pattern.
- **FRAME**
  - Problem: detection is mostly US formats.
  - Done when: detectors for UK NINO and NHS number, Canadian SIN, Indian Aadhaar and PAN,
    Australian TFN and Medicare, German Steuer-ID, French NIR, Spanish DNI and NIE, Italian
    codice fiscale, passport (format only), IBAN by country, and international phone numbers,
    each pattern plus checksum, each with fixtures.
  - Non-goals: region disguises (V2-S2); NER for non-English prose (V2 X-11).
  - Reuse check: existing `iban` and `us_phone` detectors; `name_hints` for column-name evidence.
- **PLAN**
  - Established solutions: Presidio's predefined recognizers (MIT) for pattern plus context
    words per country; libphonenumber (`phonenumbers`, Apache-2.0) for phone parsing and
    validation.
  - Design notes: a country tag on each detector so scan can report "UK identifiers found" and
    DETECT-PROFILES can select by region later.
  - Choke point and guard: as V1P-1.1 (detector registry plus drift guard).
  - Acceptance: per detector, valid and invalid fixtures (wrong checksum must not match);
    performance budget test on a large column; overlap rules with existing detectors stated
    (for example Aadhaar 12 digits against card numbers).

### V1P-2.3 International generators and format-preserving formats

- **Repo:** engine. **Size:** 1 to 2 slices. **Depends on:** V1P-2.1.
- **FRAME**
  - Problem: masked values for these identifiers must pass the receiving system's validation.
  - Done when: one `decoy_native` provider per identifier that emits checksum-valid values
    (deterministic and unique, like the existing `synthetic_ssn`), and FPE support that keeps the
    check digit valid where the existing `_fpe_checksum.py` pattern applies.
  - Non-goals: real-issuer ranges beyond what the published format defines.
  - Reuse check: `E:src/decoy_engine/providers_v2/identifiers/` (SSN, NPI, IBAN providers) and
    `E:src/decoy_engine/transforms/_fpe_checksum.py`.
- **PLAN**
  - Established solutions: the existing identifier providers are the in-repo pattern; FF1 (NIST
    SP 800-38G) for FPE, already used.
  - Placement: one module per identifier family in `providers_v2/identifiers/`, beside
    `_ssn.py`; check the directory fan-out limit first.
  - Acceptance: every generated value validates; uniqueness over a large draw; determinism
    across processes; FPE round-trip with the vault.

### V1P-2.4 Locale-aware names, addresses and phones

- **Repo:** engine. **Size:** 1 slice. **Depends on:** none (pairs with V1P-2.2).
- **FRAME**
  - Problem: US-shaped fake names and addresses in a UK or EU dataset break realism and
    downstream validation (postcode formats).
  - Done when: a `locale` setting on faker and composite providers, with the Faker and Mimesis
    locales we support listed and tested; composite address keeps city, region and postcode
    consistent for each supported locale.
  - Non-goals: transliteration; right-to-left layout.
  - Reuse check: the `locale` handling already in `providers_v2` and `internal/faker_setup.py`;
    the composite address generator.
- **PLAN**
  - Established solutions: Faker and Mimesis locale providers; national postcode formats from the
    Universal Postal Union.
  - Acceptance: per locale, generated postcodes match the national format, and the composite
    address is internally consistent; determinism per seed and locale.

---

## Sprint V1P-3: Meaning-preserving masks (X-10)

**Goal.** Options that keep the property tests and analytics depend on. Each slice is one option
and can ship alone; order by customer pull.

| Slice | Option | Method to cite | Depends on |
|---|---|---|---|
| V1P-3.1 | Email: keep domain or domain class | Domain list for free mail (public lists); hash or faker on the local part | none |
| V1P-3.2 | Phone: keep country and area code | libphonenumber parsing, FF1 on the subscriber digits | V1P-2.2 |
| V1P-3.3 | Card: keep BIN or IIN and brand, valid Luhn | ISO/IEC 7812 structure, FF1 on the account digits, Luhn recompute | none |
| V1P-3.4 | IP address: keep subnet prefix | CryptoPAn (Xu et al. 2002; the Crypto-PAn paper), AES-based prefix-preserving mapping | none |
| V1P-3.5 | Names: keep likely gender and culture | Attribute-tagged name pools from public name data (US SSA, ONS) | V1P-2.4 |

For each slice:

- **FRAME:** state the exact property kept and its leak (for example, keeping the email domain
  reveals the employer). Done when: the property holds on every output row and the leak is
  documented in `E:docs/what-we-cannot-prove.md`. Non-goal: any option that keeps more than the
  stated property.
- **PLAN:** check first whether `derived` or `formula` already expresses it; if so, the slice is a
  named option over that code, not new logic. Choke point: the strategy option schema in
  `E:src/decoy_engine/config/`; the planner refuses an option on a route that cannot honour it.
  Acceptance: a property test (for example, every output IP shares the input's /24 when the
  prefix is 24), determinism, collision and uniqueness behaviour stated, and for CryptoPAn the
  published test vectors.

---

## Sprint V1P-4: Avro and ORC (X-01)

**Goal.** Avro and ORC files as sources and targets beside CSV, Parquet and fixed width.

### V1P-4.1 Engine readers and writers

- **Repo:** engine. **Size:** 1 slice. **Depends on:** none in the engine.
- **FRAME**
  - Problem: Hadoop and Kafka-era data arrives as Avro or ORC; users convert by hand today.
  - Done when: `FileSource.format` and the target format accept `avro` and `orc`; reads go
    through the Arrow path with bounded memory (ORC stripes and Avro blocks as chunks); writes
    keep the schema, including Avro logical types (date, timestamp, decimal); profiling and scan
    read both.
  - Non-goals: Avro schema evolution across files; Schema Registry; compressed codecs beyond
    what the libraries ship by default.
  - Reuse check: `E:src/decoy_engine/config/_sources.py`, `profile/_readers.py`,
    `fileaccess/adapters/arrow.py`, input-format parity plan
    `E:docs/plans/2026-07-22-input-format-parity.md`.
- **PLAN**
  - Established solutions: `pyarrow.orc`; `fastavro` (MIT) or Polars' Avro reader; Avro 1.11
    specification for logical types.
  - Choke point: the format literal in `config/_sources.py` and the reader dispatch; guard is
    the format parity test that every declared format has a reader, a writer and a profile path.
    Mutation: add a format literal without a reader; guard goes red.
  - Acceptance: round-trip tests (read, mask with passthrough, write, compare schema and values);
    a large-file bounded-memory test on the chunked route; corrupt and truncated file tests that
    refuse with a reason code, never a stack trace.

### V1P-4.2 CLI wiring

- **Repo:** CLI. **Size:** 1 slice. **Depends on:** V1P-4.1 release and repin; CLI-FMT parts A
  and B (rows 20, 21); CONFIG-EXPLICIT (row 22).
- **FRAME**
  - Done when: `decoy run`, `scan`, `detokenize`, `unmask` and `report diff` handle both formats
    through `C:src/decoy/cli/io/` (the CODEMAP's place for readers and writers); format and
    suffix mismatch is refused, like the other formats.
- **PLAN**
  - Placement: `C:src/decoy/cli/io/` per the CLI CODEMAP "Where things go" table; `cli/` is
    frozen.
  - Acceptance: one CLI end-to-end test per format; the evidence manifest records the format.

---

## Questions to settle before V1P-1 starts

1. Settled 2026-11-06: python-stdnum is already a core engine dependency, so it is used directly.
2. Which countries first for V1P-2? The list above is a default; customer pull should reorder it.
3. Does V1P-4 wait for CLI-FMT, or does the engine half ship first so the platform can use it?
