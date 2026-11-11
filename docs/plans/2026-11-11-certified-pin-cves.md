# CERT-PIN-CVES: repin four certified runtime packages past their advisories

Status: plan

Owner: Cam. Roadmap row 24zc (`docs/ROADMAP.md`, section 5). Source: automated QA scan 2026-11-11,
finding F1. Owner decision 2026-11-11: a V1 release blocker.

Rules consulted: 00-universal, development-loop, config-secrets-and-supply-chain,
release-and-rollback, testing, scope-discipline.

Base: CLI main `3870d26` (pins `decoy-engine==0.22.0`), engine main `9878d17e`.

**Guarantee.** The certified DP runtime set (`requirements-certified.txt`) pins exactly certifi
2026.10.18, cryptography 50.0.0, pyasn1 0.6.5 and urllib3 2.8.0, and that set is a certified row in
the engine the CLI pins, so a real DP fit still completes on the certified platform. No other line
moves. No version goes above the four named.

**Non-goals:** moving any other certified pin; moving `requirements-dev.lock` (it already holds
certifi 2026.10.23, cryptography 50.0.2 and urllib3 2.8.0, which are dev-only and not shipped);
raising the `cryptography>=42` floor in `pyproject.toml`; a pip-audit CI step (see "Follow-ups");
the platform image (platform V1 is parked).

## Why

`pip-audit` on `requirements-certified.txt` (QA scan 2026-11-11) found:

| Package | Pinned | Advisories | Fixed in |
|---|---|---|---|
| certifi | 2026.7.22 | PYSEC-2026-4320 | 2026.10.18 |
| cryptography | 49.0.0 | PYSEC-2026-3552 | 50.0.0 |
| pyasn1 | 0.6.4 | GHSA-2qm8-x737-gmw5, GHSA-fm9c-5rcf-2q5p, GHSA-mm57-4v3p-rchx, GHSA-9m75-vc3g-4x39 | 0.6.5 |
| urllib3 | 2.7.0 | PYSEC-2026-4175, -4176, -4177 | 2.8.0 |

This file is what the release ships for DP and what `scripts/release/sbom.sh` turns into the SBOM, so
the SBOM would list open advisories. The engine's own lock already holds the fixed versions and its
dev/CI row is certified with them.

## Behavior

- **Pins.** In `requirements-certified.txt`: `certifi==2026.10.18`, `cryptography==50.0.0`,
  `pyasn1==0.6.5`, `urllib3==2.8.0`. The count stays 63. `pyasn1-modules==0.4.2` stays (it accepts
  pyasn1 0.6.x). cryptography 50.0.0 ships `cp39-abi3` manylinux x86-64 wheels, so CPython 3.10.20
  installs a wheel, not a build.
- **Fingerprint.** The fingerprint hashes every installed distribution and version, so the four
  moves change it from `d5898d1f...` to a new value `F`. `F` is a CLI-profile row that the engine
  must carry, so this is a cross-repo change in two slices (below).
- **Engine version.** The engine release that adds row `F` is the next one (call it `N`). The
  fingerprint also hashes `decoy-engine`'s version, so `F` is computed for exactly `N`, and the CLI
  repins to `N` in the same slice that moves the four pins.
- **Old rows stay.** `d5898d1f...` and every older CLI-profile row stay in `_CERTIFIED_STACKS` so
  snapshots recorded on them still compile (the "keep every prior release's row" rule from 0.18.0).
- **Install and smoke.** `requirements-certified.txt` header, `scripts/cert_smoke.py` and the
  certified-profile CI job name engine `N` and fingerprint `F`.

## Where the pins and the fingerprint move

Every location, checked on CLI `3870d26` and engine `9878d17e`. The CLI engine repin list is the
same 15 files CLI #184 (`990199ef`) moved for 0.22.0.

**Engine (slice E1, on the release cut for `N`):**

1. `src/decoy_engine/quality/dp_provenance.py:273-327` `_CERTIFIED_STACKS`: add `F` to the
   CLI-profile block and extend its re-pin history comment ("0.22.0 -> N with certifi, cryptography,
   pyasn1, urllib3 moved: F"). Keep `d5898d1f...` and older rows.
2. The same release's engine dev/CI row for `N` (the normal release step; the engine lock does not
   change).
3. `tests/unit/generation/test_dp_prior_release_rows.py:62-75`: add `_VN_ROWS` (the dev/CI row and
   `F`) and append it to `_ALL_ROWS`.
4. `_CERTIFIED_ANNOTATIONS` (`dp_provenance.py:330`): unchanged; none of the four is proof-critical.

**CLI (slice C1, after `N` is tagged):**

5. `requirements-certified.txt:54, 57, 88, 109`: the four pins.
6. `requirements-certified.txt:5-12, 23`: engine `N`, fingerprint `F`, and the history line
   ("Was d5898d1f... on engine 0.22.0 with the four pre-advisory pins").
7. `pyproject.toml:115-122`: `decoy-engine==N` and its comment.
8. `requirements-dev.lock`: the `decoy-engine` line only, through `scripts/dev/lock.sh` (stale-lock
   rule: regenerate, do not hand-edit).
9. `.github/workflows/ci.yml:285` and `.github/workflows/release-smoke.yml:83`: the engine tag.
10. `scripts/cert_smoke.py:8-11`: docstring names engine `N` and `F`.
11. `scripts/dev/bootstrap.sh:32`, `scripts/dev/lock_version.sh:17`: the engine spec.
12. `docs/guides/shape-and-privacy/04-differential-privacy.md:88`, `.../README.md:10-13`,
    `docs/release/fresh-install-smoke.md:47, 87, 115`: the engine tag.
13. `src/decoy/ci/rule_codes.py:209`: the engine version in the comment, after re-checking the
    literal codes against `N`.
14. `tests/unit/test_pyproject_metadata.py:112-113`, `tests/e2e/test_run_native.py:407`: `==N`.
15. `CHANGELOG.md`: one entry (engine repin plus the four security pins, fingerprint `F`).
16. SBOM: no committed SBOM file. `scripts/release/sbom.sh` reads the pin list at release time;
    `tests/unit/test_sbom_script.py:312` asserts 63 pins and stays green.
17. `docs/release/sbom.md:20-21` ("63-package"): unchanged.

**Not moved:** `requirements-dev.lock` third-party lines, `ci/ci-tools.lock`,
`pyproject.toml:143` (`cryptography>=42`), the engine's `uv.lock`, the platform.

## Failure modes and reason codes

| Failure | Code or signal (fixed, value-free) | Where caught |
|---|---|---|
| Installed set is not a certified row (stale `F`, wrong engine version in the hash, a fifth pin moved) | `ProvenanceError` code `dp_stack_uncertified` | `cert_smoke.py` in the certified-profile CI job; AT-3 |
| Header fingerprint does not match the pins | `cert_smoke.py` failure naming "pinned file no longer produces the fingerprint it records" | CI; AT-2 |
| A pin left at an advisory version, or raised above the named version | AT-1 failure naming the package and the expected version | T1 |
| cryptography 50.0.0 needs a dependency the set does not hold | `uv pip install -r requirements-certified.txt` resolution error | C1 build step; stop and report, do not move a fifth pin |
| A snapshot recorded on `d5898d1f...` no longer compiles | existing prior-release-rows test | E1 T1 |

Messages carry package names, versions and fingerprints only. No data values, paths or secrets.

## Pre-mortem

| Risk | Guard |
|---|---|
| `F` computed for the wrong engine version (for example 0.22.1 against a 0.23.0 release) | `F` is computed on the release cut after the version is stamped; C1's certified-profile job installs the real tag and runs `cert_smoke.py`, which fails on a mismatch |
| The repin raises a pin past the named fix (cryptography 50.0.2 copied from the dev lock) | AT-1 checks exact equality |
| E1 drops an old row while adding `F` | AT-4 (existing prior-release-rows test extended) |
| The dev lock gets regenerated with a wider move | `lock.sh` is run with only the engine spec changed; the diff is checked to touch the `decoy-engine` line only |
| Row `F` is admitted before any real install proves it | C1 cannot merge until the certified-profile job is green; E1's row comment records "derived" until then, as for earlier rows |

## Acceptance tests (red first)

| # | Test | Red on |
|---|---|---|
| AT-1 | New `tests/unit/test_certified_pins.py`: parse `requirements-certified.txt`; `certifi`, `cryptography`, `pyasn1`, `urllib3` equal exactly `2026.10.18`, `50.0.0`, `0.6.5`, `2.8.0`; 63 pins; every line `name==version` | current main (four old pins); M1, M4 |
| AT-2 | Same file: the header fingerprint equals `compute_lock_fingerprint` over the 63 pins plus `decoy-engine` at the `pyproject.toml` pin plus `decoy-cli` at the project version (pure computation, runs in the dev venv) | M2 |
| AT-3 | Same file: that fingerprint is in `_CERTIFIED_STACKS[(CERTIFIED_PLATFORM, "3.10.20.final")]` of the installed engine | M3 (and current main once AT-1 is satisfied without E1) |
| AT-4 | Engine `test_dp_prior_release_rows.py`: `_VN_ROWS` includes `F`; every older row still compiles | an E1 that drops `d5898d1f...` |
| AT-5 | CI certified-profile job: fresh 3.10.20 venv, engine tag `N` and the CLI wheel with `--no-deps`, then `-r requirements-certified.txt`, then `cert_smoke.py` (fingerprint, manifest row, real DP fit) | M2, M3, a fifth pin moved |

**Named mutations** (on the C1 head; each must turn a test red):

- M1: leave `urllib3==2.7.0`.
- M2: keep the old header fingerprint `d5898d1f...`.
- M3: install an engine without row `F` (point AT-3 at a `_CERTIFIED_STACKS` copy minus `F`).
- M4: pin `cryptography==50.0.2`.

## Enumerations (CLI `3870d26`, engine `9878d17e`)

### Routes

- Certified install: `.github/workflows/ci.yml:285-291` (`--no-deps` engine plus wheel, then the
  pin file, then `cert_smoke.py`).
- Release smoke: `.github/workflows/release-smoke.yml:83`.
- Fit-time gate: `E:src/decoy_engine/quality/dp_provenance.py:347` `check_fit_environment`.
- Recorded-snapshot gate: `E:src/decoy_engine/quality/dp_provenance.py:382`
  `validate_recorded_provenance`.

### Exit paths

- `cert_smoke.py` exits non-zero on any mismatch (`scripts/cert_smoke.py:40` `_fail`).
- A fit on an uncertified set raises `ProvenanceError` `dp_stack_uncertified`.
- A clean install exits 0 after a real fit.

### FK shapes

N/A: dependency pins only; no data path changes.

### Fields

N/A: no config key, result key or reason code is added; the change is version strings and one
fingerprint.

### Output surfaces

- The SBOM produced at release from `requirements-certified.txt` (`scripts/release/sbom.sh:76`).
- `cert_smoke.py` messages: package names, versions, fingerprints.
- `CHANGELOG.md` entry.

## Class table

| # | Class | Where it applies | Structure that closes it | Proof | Mutation that must turn it red |
|---|---|---|---|---|---|
| 1 | Value-bearing output | none; certifi and urllib3 carry data in transit, which is why the pins move | exact fixed versions in the shipped set | AT-1 | M1 |
| 2 | Cleanup missing on an exit path | none | N/A: no runtime code changes | n/a | n/a |
| 3 | State machine and concurrency | none | N/A: no runtime code changes | n/a | n/a |
| 4 | Route parity and silent fallback | certified install vs dev install | only the certified set is fingerprinted and certified; the dev lock is separate and not shipped | AT-5 | M3 |
| 5 | Referential integrity | none | N/A: dependency pins only, no keys or FK data paths change | n/a | n/a |
| 6 | Untrusted producer | package index content | `uv` installs wheels by exact pin; the engine gate checks the installed set by fingerprint | AT-5 | M2 |
| 7 | Check then use (TOCTOU) | the fingerprint is computed from the installed set at fit time, not from the file | unchanged engine gate | AT-5 | n/a |
| 8 | Weak tests | today only CI's real install checks the pins; nothing in T1 pins them | AT-1 to AT-3 in the dev venv | AT-1, AT-2, AT-3 | M1, M2, M4 |
| 9 | Refactor drift | the 15-file engine repin | follow CLI #184's file list; `test_pyproject_metadata.py` pins `==N` | AT-5, existing metadata test | leave `ci.yml` on `v0.22.0` (AT-5 red) |
| 10 | Frozen contract drift | the DP certified-row set and prior snapshots | add `F`, keep every older row | AT-4 | drop `d5898d1f...` (AT-4 red) |

## Reuse inventory, frozen contracts

- **Reuse:** engine `compute_lock_fingerprint` and `_CERTIFIED_STACKS` (AT-2, AT-3), `cert_smoke.py`,
  the certified-profile CI job, `scripts/dev/lock.sh`, CLI #184's repin file list.
- **Frozen contracts:** the DP certified-row set grows by one CLI-profile row; no row is removed.
  The 63-package count and the proof-critical versions in `_CERTIFIED_ANNOTATIONS` do not change.

## Placement

| Change | File | Sits beside |
|---|---|---|
| Row `F` and history comment | `E:src/decoy_engine/quality/dp_provenance.py` | the CLI-profile rows |
| `_VN_ROWS` | `E:tests/unit/generation/test_dp_prior_release_rows.py` | `_V0_22_0_ROWS` |
| Four pins, header | `requirements-certified.txt` | the other 59 pins |
| Pin and fingerprint tests | `tests/unit/test_certified_pins.py` (new) | `tests/unit/test_sbom_script.py` |
| Engine repin | the 15 files listed above | as in CLI #184 |

## Slices

| Slice | Repo | Branch | Size | Gate | Depends on |
|---|---|---|---|---|---|
| E1 | engine | the release branch for `N` | XS (one row, one test tuple) | T1: `tests/unit/generation/test_dp_prior_release_rows.py`, `tests/unit/quality/` DP provenance tests | the daily engine release |
| C1 | CLI | `chore/certified-pin-cves-c1` | S (four pins, header, 15-file repin, one new test file) | T1: `tests/unit/test_certified_pins.py`, `test_pyproject_metadata.py`, `test_sbom_script.py`; CI certified-profile job green on the exact head; M1 to M4. Full suite per the testing.md trigger (dependency lock and version pin) | E1 released as tag `vN` |

`F` cannot be proven before C1's CI job runs: the DP certified row covers only Linux x86-64 CPython
3.10.20 glibc, so the Mac cannot check it. E1 computes `F` from the exact set with
`compute_lock_fingerprint`; C1's job proves it with a real install.

## Engineering calls made

- One row per release, not a 0.22.0 row: a row for engine 0.22.0 plus the new pins would only help
  if a 0.22.0 build carried it, and no released 0.22.0 can change. So the row goes in the next
  release.
- The dev lock is left alone. Its versions are newer than the named fixes and it is not shipped;
  aligning it to the certified pins would lower them, which the owner's "no version above the
  named" limit does not ask for.

## Follow-ups (not in this row)

- A `pip-audit` step on `requirements-certified.txt` in CI (V2-LOG candidate; needs a pinned tool
  and network access in CI).
- Platform image pins (platform V1 parked).
