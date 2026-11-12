# Census: duplicated code and uncentralized cross-cutting concerns (engine and CLI)

Date: 2026-11-12. Engine main `35b82bd8`, CLI main `9cc0434`. No code was changed.

Purpose: a candidate list for V2 remediation. It answers the roadmap's review question (section
4.3): "is this doing something that every other class does differently? could it be rolled into a
central location?" Nothing here is scheduled; none of it is a roadmap row yet.

The working list, with every finding sorted into V1 or V1+ and its locations, is
[REMEDIATION.md](REMEDIATION.md).

## Method

Five mechanical passes over `src/` (tests and the Rust crate were not scanned), then a read of
each candidate at its lines by five triage agents, one per slice. The script is
[`census.py`](census.py) in this folder; the copy-paste pass is `jscpd` 4 with `--min-tokens 70
--min-lines 8`.

| Pass | Finds |
|---|---|
| Copy-paste (`jscpd`) | blocks that are textually the same |
| Same shape | functions whose syntax tree is identical after names and literals are erased |
| Primitive-call census | stdlib and third-party calls, by how many packages call them directly |
| Same name | module-level functions defined in more than one file |
| Co-change | files in different packages that change in the same commit 6 or more times; commits that touch 6 or more packages |

To rerun: `python census.py <repo> <src subdir> <out dir> <own import prefixes>`, for example
`python census.py ../decoy-engine src/decoy_engine out/engine decoy_engine`.

## What the passes measured

| Measure | Engine | CLI |
|---|---|---|
| Source scanned | 785 files, about 176,000 lines | 113 files, about 30,000 lines |
| Copy-paste blocks | 92 clones, 1,250 lines, 0.7% | 6 clones, 77 lines, 0.29% |
| Same-shape function groups | 48 | 3 |
| Function names defined in more than one file | 95 | 15 |
| External call targets reached from 5 or more packages | 61 | 8 |
| Cross-package file pairs that change together 6 or more times | 49 | 8 |

Literal copy-paste is under 1% in both repos. The duplication that exists is of the other kind:
the same rule written separately in many modules, and parallel per-strategy modules that have
drifted apart.

## What triage found

| Slice | Detail file | Result |
|---|---|---|
| Engine clones | [engine-clones.md](engine-clones.md) | 28 findings: 6 extract with drift, 16 extract, 6 families; about 20 groups benign |
| Engine hashing, randomness, serialization | [engine-hashing-rng-serialization.md](engine-hashing-rng-serialization.md) | 9 concerns: 4 centralize, 1 owned with stragglers, 4 fine |
| Engine data handling, I/O, regex | [engine-data-io-regex.md](engine-data-io-regex.md) | 15 concerns: 9 centralize, 2 owned, 3 fine, 1 not read |
| Engine same names and co-change | [engine-names-cochange.md](engine-names-cochange.md) | 17 duplicate helper groups; 9 hidden shared rules behind 16 file pairs; 15 wide commits classified |
| CLI, all passes | [cli.md](cli.md) | 7 extractions, 7 concerns to centralize, 2 hidden shared rules, 3 engine re-implementations |

Finding ids (EC, EX, ED, EN, EP, EW for the engine; CC, CX, CP, CE for the CLI) are defined in
the detail files, with every site as `path:line`.

## Highest-value candidates

Ordered by how many sites share the rule and whether the copies already differ.

**Engine**

1. **Random-generator construction (EX-2).** 68 sites in about 12 packages build a generator
   (`numpy.random.default_rng`, `random.Random`) with 9 different seed derivations. No guard test
   scans for a new construction. First step: a sentry with a baseline and one seed-derivation
   helper.
2. **JSON that feeds a digest (EX-1, EN-3).** About 19 call sites in 8 variants (`sort_keys`,
   separators, `default=str` or `default=repr` or none). `records/_canonical.py` owns it for
   records only.
3. **Per-strategy out-of-core modules (EC-3, EN-1).** Seven `out_of_core/_*_native.py` and
   `_hash_run.py` modules each carry their own column-decision class, table plan, `gate()` and
   `decide_table()`. Four are identical apart from names; bucket, faker and hash have drifted.
4. **Strategy names in parallel hand-kept tables (EP-1, EP-2).** `SCALAR_HANDLERS`,
   `TECHNIQUE_CLASS_BY_STRATEGY` and `_STATIC_BEHAVIOR` change together on every new strategy, and
   admitting one strategy to the native routes touched 16 files. A catalog that reads each
   handler's own attributes already exists.
5. **"Is this column text" (ED-1) and "is this cell null" (ED-2).** The Arrow string check is
   written inline in about 19 files; the null test has five private helpers with different rules
   for `pd.NA` and `NaT`.
6. **Keyed derivation stragglers (EX-3).** `determinism/_derive.py` owns HMAC and HKDF framing;
   about 8 sites still build their own.
7. **Config walk in plan checks (EC-8).** The same loop over tables and columns is copied across
   about 35 `plan/_checks*.py` sites.
8. **Smaller, clear cases.** The DP query-count formula written three times (EP-4); five
   topological sorts (EN-5); `_luhn_check_digit` in five files (EC-7); snapshot digest and the
   `sha256:` tag rebuilt by hand in 5 places (EX-4); NER config parse inline in two modules beside
   the shared `_ner_config.py` (EC-1).

**CLI**

1. **Error output (CX-1, CC-2).** Per-command error emitters and `"status": "error"` payloads are
   repeated across the command modules (7 functions named `_emit_error`, more under other names).
   They differ on markup escaping, `--quiet` and JSON shape. Proposed home: one `emit_error` in
   `ui/output.py`, with a sentry.
2. **Pipeline config loading (CX-2, CC-1, CC-3, CP-1).** 16 files call `yaml.safe_load`; the
   `mask_secret_ref` guard exists in 4 copies; non-UTF-8 handling is in one command only.
3. **`decoy demo` re-implements `run` (CC-4, CC-5).** Its own source loader, target writer and
   exception-to-exit-code map.
4. **Secret reference grammar (CE-1).** `_mask_secret.py` hard-codes the `env:`, `file:` and
   `vault://` prefixes instead of using the engine's `parse_ref`.
5. **`--json` output (CX-3).** Two sites bypass `emit_json`.

## Possible defects surfaced on the way

These came out of comparing copies. "Confirmed" means the line was re-read for this record and
says what is described; it does not mean a user-visible failure was reproduced. None was run end
to end.

| Where | What the code does | State |
|---|---|---|
| `E:transforms/joint_mask.py:338,366` | seeds a generator from `job_seed[:8]` directly, with no namespace or column in the derivation, so every `joint_mask` column draws from the same stream | confirmed at the line; whether intended is not known |
| `E:execution/native/_draw_site_providers.py:114` and `E:transforms/text_mask.py:259` | the native copy of `_span_key` encodes strict UTF-8, the original uses `errors="replace"`; they differ on a lone surrogate | confirmed at the lines; no parity test found |
| `E:generation/composite/*` | the missing-seed fallback is `b"\x00" * 8` at some sites and `os.urandom(8)` at others in the same files | confirmed at the lines |
| `E:generation/_window_admission.py:177` and two more | `datetime.fromisoformat` without the "Z" shim that `_reference_date.py:37` applies; Python 3.10 rejects a trailing "Z" | confirmed at the first line; the other two not re-read |
| `E:quality/dp.py:152` | `float(epsilon)` before any type check, so `True` passes; `plan/_checks_dp.py` rejects bool for the same setting | confirmed at the line; reachability not checked |
| `E:providers_v2/identifiers/` | `_ein`, `_ndc`, `_npi`, `_ssn` refuse a non-US locale; `_cusip`, `_iban`, `_icd10` do not, though all declare US only | confirmed by search |
| `E:profiling/model_pack/loader.py` | `DECOY_ML_DISABLED` is honored only for the exact value `1`; the signature flag in the same file takes a strict true or false set | reported, not re-read |
| `E:` config digests | `plan/_compile.py` dropped `default=str` from its hash input; five other digest sites kept it or use `default=repr` | reported, not re-read |
| `E:generators/_distribution.py:65` | draws values from the same stream as the null mask | line confirmed; the triage agent could not show a plan path that reaches it |
| `C:src/decoy/__main__.py:165` | `typer.Exit(1)` literal; the guard in `tests/unit/test_exit_codes.py` matches only the `code=` form | confirmed at both lines |
| `C:src/decoy/cli/demo.py:587` | maps three exception types to exit 1, where `run/_errors.py:128` maps many more, so the same failure can exit differently in `demo` and `run` | confirmed at both lines |
| `C:` installer `_urllib_download` | `urlopen` with no timeout | confirmed at the line; `decoy upgrade` is reported to override this downloader |
| `C:src/decoy/cli/io/_project.py:120` | `DECOY_PROJECT` is named in a docstring; nothing reads it | confirmed by search (the roadmap has it as planned in PROJECT-LAYOUT) |

## Limits

- The platform repo, all test code and the Rust crate were not scanned.
- The passes cannot see two pieces of code that do the same job in a different shape.
- Triage read samples, not every site, for the larger concerns; each detail file says how many
  sites were read and marks unread claims UNVERIFIED.
- Site counts in the detail files come from the census or from search and were not all recounted.

## Keeping it from growing

- Put `jscpd` in `gates.sh` behind a shrink-only baseline (the existing ratchet), per repo.
- Turn the primitive-call census into a diff check: a change that adds a direct call to a
  primitive that has an owner fails.
- Generate an index of shared helpers with their one-line docstrings for builders to read at PLAN.
