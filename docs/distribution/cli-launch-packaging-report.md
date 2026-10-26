# CLI launch packaging -- implementation report (CLI-LAUNCH / RW-B, R1)

**Status:** built, tested, pushed to branch `claude/youthful-ride-0azacx` (engine + CLI).
Not merged (the orchestrator gates: dennis then Codex). Risk tier R2 (supply-chain /
release machinery): independent review required, no author self-certification.

## Remediation round 1 (post-gate)

Two gate-blocking defects and one declaration were fixed at the source:

- **BLOCKER 1 (lint gate red).** The ported platform `# noqa: S310/S202/BLE001` idioms
  were unused under this repo's narrower ruff `select` (`E,F,I,B,RUF`), so RUF100 and a
  few other rules reddened CI. Fixed: `ruff check src tests` with the pinned
  `ruff==0.15.14` now exits 0 (removed the pointless noqas, made a `pytest.raises(match=)`
  pattern raw, renamed an unused unpack, split semicolon statements). `packaging_tools/`
  (outside the CI scope) was also made lint-clean.
- **BLOCKER 2 (`decoy upgrade --version <older>` destroyed the rollback runtime).** The
  Python installer resolved only the latest artifact, so a pinned older version downloaded
  the latest bits and overwrote `versions/<older>`. Fixed three ways: (1) the Python path
  resolves a pinned non-latest version by the published URL convention, exactly like
  `install.sh`; (2) a fail-closed guard reads the extracted bundle's declared version and
  refuses BEFORE the destructive `rmtree` if it does not equal the requested version, so a
  resolution mismatch can never destroy an existing version dir; (3) the rollback path is
  now a local atomic `current`-pointer swap to the retained runtime
  (`installer.activate_local_version`) with no download or overwrite, and the
  `decoy upgrade` rollback hint points at it. New tests cover pin-older-installs-real-bits,
  pin-mismatch-refuses-without-touching-dest, and activate-is-a-swap-not-a-download.
- **MEDIUM (undeclared direct deps).** `cryptography` and `packaging` are imported at CLI
  startup but were only transitive; added `cryptography>=42` and `packaging>=21.0` to
  `[project] dependencies` (floors matching the engine's). The certified closure
  (`requirements-certified.txt`) already pins both at satisfying versions
  (`cryptography==49.0.0`, `packaging==26.2`), so the resolved closure and its DP
  fingerprint are unchanged and the frozen file is correctly left byte-identical (editing
  it would break the fingerprint; a legitimate re-derive would reproduce it).

Re-verified: `ruff check src tests` exits 0; `tests/unit` + `tests/sentry` green (414
passed); and the end-to-end smoke is `RESULT: ALL PASS` (install + version + run, checksum
refusal, signature refusal, loud native refusal, real `decoy upgrade` 0.1.0 -> 0.2.0).

Scope delivered: the signed, self-contained CLI distribution machinery for the V1 R1 cut
-- bundle builder, signing, install scripts, version-endpoint contract, and
`decoy upgrade`. CLI features are unchanged (the CLI is feature-current on the adopted
stateless surface).

## What was built

### Shipped in the CLI (`decoy-cli`), `src/decoy/distribution/`
- `signing.py` -- detached Ed25519 verify, a faithful port of the in-repo
  `decoy-platform/api/crypto/signed_envelope.py` (confident-dirac passport / airgap
  manifest), cited in the docstring. Verify only; no private-key code ships.
- `manifest.py` -- bundle checksum manifest (compute + forward/reverse verify), ported
  from `decoy-platform/scripts/airgap/manifest.py`, extended to record + verify the
  interpreter's internal symlinks and to exclude regenerable `__pycache__`.
- `version_document.py` -- the `cli-version-document/v1` contract (PEP 440 ordering via
  `packaging.version`, yank/floor logic, graceful degrade).
- `targets.py`, `layout.py` -- host->target mapping; `~/.decoy` layout + atomic
  `current`-symlink swap.
- `selfcheck.py` -- native-present self-check reusing the engine's public
  `native_companion_status()` probe; loud refusal.
- `installer.py` -- the verified install + atomic-swap-with-rollback core shared by
  `decoy upgrade` and the tests.
- `verify_extracted.py`, `layout_point.py` -- installer helpers run through the bundled
  interpreter.
- `release_key.py` + `release_key.pub.pem` -- the pinned public key (placeholder until the
  release-publish step fills it; a placeholder build refuses to upgrade).
- `cli/upgrade.py` + `_update_check.py` + `__main__.py` wiring -- the `decoy upgrade`
  command and the interactive startup update notice.

### Build host only (`packaging_tools/`, not shipped)
- `sign_release.py` -- Ed25519 key custody (key from env, never committed) + detached
  signing. Same key/alg/bytes as the verify side.
- `build_bundle.py` -- deterministic per-target bundle assembler (standalone CPython +
  matched wheels + launcher + signed manifest + reproducible tar.gz + sha256 + sig).
- `make_version_document.py` -- assemble + sign the hosted version document.
- `install/install.sh`, `install/install.ps1`, `install/uninstall.sh`.
- `smoke_install.py` -- the end-to-end acceptance smoke.

### Engine repo (`decoy-engine/.github/workflows/`)
- `native-companion-release.yml` -- tag-triggered release pipeline that reuses the proven
  four-target matrix build and publishes durable, Ed25519-signed, versioned wheels +
  `SHA256SUMS` to a GitHub Release. Additive workflow file; no engine source change.

## Bundle format + platforms
Per-target tarball `decoy-<version>-<target>.tar.gz` containing `python/` (a
python-build-standalone CPython), the matched `decoy-engine` + `decoy-engine-native` +
`decoy-cli` wheels installed into it, a `decoy` launcher (`python -m decoy`, resolves the
bundle via the `current` symlink), `BUNDLE_INFO.json`, and a signed `manifest.json`.
Targets: `linux-x86_64`, `linux-aarch64`, `macos-arm64`, `windows-x86_64` (the native
matrix). ~600-650 MB installed / ~290 MB compressed. Reproducible archive bytes.

## Signing + verification path (one scheme, three verifiers)
Ed25519 via `cryptography`, reusing the in-repo signed-envelope pattern (cited). The
signature is detached and over the exact on-disk file bytes, so the identical signature is
verified by: `openssl pkeyutl -verify -rawin` in `install.sh`; `signing.verify_detached`
in `decoy upgrade`; and the platform primitive on an auditor's host. No minisign/cosign,
no second scheme, no hand-rolled crypto. The release public key is pinned in the installer
and shipped in the CLI; the private key lives only in the release secret store.

## Version endpoint contract
`GET /cli/version.json` (+ `.sig`): `{schema_version, latest, min_supported, yanked[],
message, generated, artifacts:{<target>:{url, sha256, sig}}}`, canonical JSON, static file
behind a CDN for V1. Full spec: `docs/distribution/version-endpoint-contract.md`.

## Smoke results (linux-x86_64, recorded: `RESULT: ALL PASS`)
`packaging_tools/smoke_install.py` built a real signed bundle from a
python-build-standalone cp3.12 + the matched engine + a locally-built native companion
wheel (cp312 manylinux_2_34, ABI `decoy-native-abi-3`), served it locally, and asserted
each case:
- **case1** clean install -> `decoy --version` = `decoy 0.1.0`; `decoy doctor` reports a
  present, healthy native companion; `decoy run examples/generate_example.yaml` produced
  `customers.csv` (1001 rows), route `full_frame`. PASS.
- **case2** one-byte tamper -> install refuses on **checksum MISMATCH**. PASS.
- **case3** corrupted signature (valid bytes) -> install refuses on **signature INVALID**. PASS.
- **case4** native companion removed -> install refuses **loudly at the native self-check**,
  nothing laid down (no `current`). PASS.
- **case5** real `decoy upgrade` 0.1.0 -> 0.2.0 swaps atomically (`current` -> 0.2.0,
  previous kept). PASS. Rollback-on-injected-failure is asserted deterministically by
  `tests/unit/test_distribution.py::test_installer_rolls_back_on_post_swap_failure` (a real
  signed bundle + an injected post-swap failure -> `current` rolls back, new runtime kept
  on disk).

The upgrade leg drives the endpoint over `file://` so it does not depend on an HTTP
proxy's loopback handling; `install.sh`/`curl` exercise the HTTP download path for the
earlier cases. Unit tests: `tests/unit/test_distribution.py` (30 cases) plus the full CLI
unit suite (381 passed) and the sentry suite (29 passed) green. Surface drift guards
regenerated (`docs/cli-reference.md`; `upgrade` added to the surface-omission allowlists).

## Decisions that need Cam
1. **Windows signature tooling.** `install.ps1` verifies Ed25519 via `openssl` on PATH
   (Git-for-Windows ships it) and refuses if absent -- consistent with the loud-refusal
   rule but a prerequisite. Alternative: a bundled/pinned `minisign`. (install.ps1 is
   written and reviewable but was not executed in this Linux smoke.)
2. **macOS Intel (x86_64):** unsupported at launch (not in the matrix). Rosetta-on-arm64
   or adding the target are the alternatives.
3. **Download host + key-custody store + release cadence:** static site + CDN vs object
   storage; where the private key lives and its rotation window.
4. **Engine pin for the final bundle** waits on D-4 (the DP-certified launch engine). The
   smoke built against the current local engine (0.7.0 convention); the final cut re-pins.

## Dependency note
Built against the adopted stateless CLI surface (B-1, already on `decoy` main:
run/validate/scan/report/list/show/... no project/catalog/jobs). `decoy query` (S6) is out
of R1 as decided. The native wheel matrix was consumed, not rebuilt (a companion wheel was
built locally only to feed the smoke).
