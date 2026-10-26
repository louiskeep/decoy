# CLI launch packaging -- implementation report (CLI-LAUNCH / RW-B, R1)

**Status:** built, tested, pushed to branch `claude/youthful-ride-0azacx` (engine + CLI).
Not merged (the orchestrator gates: dennis then Codex). Risk tier R2 (supply-chain /
release machinery): independent review required, no author self-certification.

## Remediation round 4 (post round-3 Codex gate) -- SIMPLIFY the shell transaction

Round 3's cross-model Codex gate found that the shell installer's transactional promotion
had grown a new bug each time it was hardened (round 2: destructive delete; round 3: a
failed restore deleting the backup, and an EXIT-only trap that catchable signals skip).
Per Cam's decision the fix this round is to **stop hardening the in-place replacement and
remove it entirely**: a `versions/<v>/` directory is NEVER mutated in place.

- **Never replace a version dir in place (the primitive).** Every install, reinstall, and
  repair stages the fresh bits into a FRESH directory and makes them live by the one atomic
  symlink flip (`layout.atomic_point_current_at` -- a temp symlink `os.replace`'d over
  `current`). A first/different-version install renames into the absent `versions/<v>`; a
  same-version repair stages into a distinct `versions/<v>+<build>`, flips to it, then
  reclaims the old dir (reclamation is not time-critical and needs no backup/restore). The
  Python installer's move-aside/backup/restore machinery (`_promote_staged` + the old
  `_restore_backup`/`_reclaim_backup`) is gone; `installer.py` now just stages a fresh slot
  and the single flip decides everything.
- **HIGH 1 (shell recovery deleted the backup after a failed restore) -- eliminated by
  construction.** There is no backup and no restore because nothing is replaced in place.
  Regression: `test_same_version_staging_failure_before_flip_preserves_runtime` -- an
  injected failure DURING staging (before the flip) leaves the existing runtime live and
  untouched.
- **HIGH 2 (the interruption safety net only trapped EXIT) -- eliminated by construction.**
  Staging a fresh dir never touches `current`; the only state change is the atomic flip,
  which cannot half-complete, so an interruption (INT/TERM/HUP/KILL) at any point leaves
  EITHER the old runtime live (flip not reached) OR the new one (flip done), never a
  missing `current`. No signal trap is needed (the shell keeps an EXIT-only trap purely to
  drop its temp dir). Regression:
  `test_same_version_flip_is_atomic_never_missing_current`.
- **The shell bootstrap is first-install-only (refuse-and-redirect).** `install.sh` /
  `install.ps1` lay down a fresh runtime and REFUSE to replace an existing one, directing
  all same-version repair and upgrades through `decoy upgrade` (the Python path, which uses
  the stage-fresh + atomic-flip above). The bootstrap never deletes or overwrites an
  existing runtime, so it has nothing to recover. Regression:
  `test_install_sh_refuses_when_already_installed` (existing runtime left untouched, nothing
  staged); the first-install identity check is retained as
  `test_install_sh_refuses_wrong_version_without_installing_anything`.
- **MEDIUM (the import-isolation positive case was vacuous).** The positive case ran
  `sys.executable -I` (not the packaged launcher), permitted `ImportError`, and never
  asserted success, so it passed even with no usable Decoy install. It now runs the actual
  launcher invocation (`-I -B`) against a bundle-resident `decoy` (a venv whose own site
  holds the signed package -- how the real bundle's interpreter imports under `-I`) from a
  hostile CWD + PYTHONPATH, and asserts it SUCCEEDS, imports `decoy` from INSIDE the bundle
  (expected origin + version), and leaves no attack marker. The negative controls are kept.
  (`test_import_isolation_runs_bundle_decoy_and_blocks_hostile_cwd_and_pythonpath`.)
- **LOW (PowerShell recovery).** `install.ps1` is given the same refuse-and-redirect now
  (refuse an existing install, plain first-install placement, no backup/restore), so there
  is nothing to recover there either. Windows stays gated off the advertised matrix.

This supersedes round 2's HIGH 3 (the stage-beside/backup/restore mechanism described
below) and renames its shell identity regression. Not merged; the orchestrator re-gates
(dennis then Codex) on push.

## Remediation round 2 (post cross-model Codex gate)

The cross-model Codex gate found four HIGH and three MEDIUM defects; all were fixed at the
source with named regressions (unit suite now 425 passed; lint clean on `src tests` and
`packaging_tools`).

- **HIGH 1 -- unsigned bytecode bypassed rollback integrity.** The manifest excluded all
  `__pycache__`/`.pyc`, and Python's default timestamp-based cache invalidation
  authenticates a `.pyc` only against the source's mtime+size (not a hash), so a forged
  cache whose header matched the signed source executed in its place while
  `verify_manifest(...) == []`. Fixed two ways: the managed runtime now launches with
  bytecode writing OFF (`-B` + `PYTHONDONTWRITEBYTECODE`, inherited by children -- the
  launcher and every install/activate self-check), and `verify_manifest` now REJECTS any
  `__pycache__`/`.pyc`/`.pyo` found on disk as tampering (a correct cache-free runtime
  verifies clean). Regressions: `test_manifest_rejects_bytecode_cache_and_unexpected`
  (manifest level) and `test_activate_local_refuses_forged_bytecode_cache` (a substituted
  `.pyc` in a retained runtime makes activation refuse).
- **HIGH 2 -- installers permitted wrong-version/target replacement.** Round 1 fixed only
  the Python path. The declared **version AND target** identity check now runs before any
  deletion in EVERY installer: `install.sh` and `install.ps1` read the signed
  `BUNDLE_INFO.json` and refuse a mismatch before `rm`/`Remove-Item`, and the Python path
  gained the target check beside its existing version check. Regressions:
  `test_installer_target_mismatch_refuses_without_touching_dest` (Python) and
  `test_install_sh_refuses_wrong_version_without_touching_dest` (shell, offline path, real
  Ed25519 via openssl). (`install.ps1`'s check is corrected at the source but the target is
  gated off this cycle -- see HIGH 4 -- so it is not an advertised/executed path and has no
  live pwsh regression; this is called out below.)
- **HIGH 3 -- same-version forced reinstall destroyed the rollback target.** The Python
  installer removed the destination before promoting, so `decoy upgrade --force` when
  already current could leave no runtime and a post-swap "rollback" landing on the
  replacement. Promotion now stages the validated replacement beside the original, moves
  the original ASIDE (retained), moves the replacement in, and reclaims the original only
  after post-swap validation passes; a failed promotion or post-swap validation restores
  the original bits. Regressions:
  `test_same_version_force_post_swap_failure_preserves_runtime` and
  `test_same_version_promotion_failure_preserves_runtime`.
- **HIGH 4 -- Windows lifecycle could not complete.** `install.ps1` executed the
  interpreter from its pre-move location, and the `current`-symlink + POSIX-launcher model
  is not verifiable on Windows here (no Windows runner / `pwsh`). Per the launch rule,
  Windows is **gated off the advertised matrix** this cycle (removed from
  `SUPPORTED_TARGETS`; `detect_target`/both installers refuse on Windows; `build_bundle`
  refuses the target; the version document advertises no Windows artifact). The ps1 body
  was also corrected at the source (path recomputed after promotion; identity check; `-B`)
  for re-enablement. Decision + re-enable checklist:
  `docs/distribution/decisions/2026-10-26-windows-target-gated.md`. Regressions:
  `test_windows_gated_off_advertised_matrix`, `test_build_bundle_refuses_windows_target`,
  and the updated `test_detect_target`.
- **MEDIUM 1 -- local rollback depended on the network.** `decoy upgrade --version <local>`
  now resolves + activates an already-installed version BEFORE any endpoint fetch, so an
  outage never blocks rolling back to verified local bits. Regression:
  `test_upgrade_resolves_local_before_network` (network call monkeypatched to assert it is
  never reached).
- **MEDIUM 2 -- smoke bound all interfaces.** `smoke_install.py` now binds `127.0.0.1`
  explicitly. Regression: `test_smoke_serve_binds_loopback_only`.
- **MEDIUM 3 -- pin test overwrote the user's launcher.** A shared autouse fixture now
  isolates `DECOY_BIN_DIR` (and `DECOY_HOME`) for every installer test, so the suite never
  writes outside its temp dirs.

Also folded in the two dennis LOWs: `decoy upgrade --version <local> --force` now routes to
a real reinstall/repair (download + re-verify), not the local swap
(`test_upgrade_force_local_reinstalls_not_swap`); and a pinned-path flipped-byte test
asserts refusal specifically on SIGNATURE (`test_installer_pin_flipped_byte_refuses_on_signature`).

Not merged; the orchestrator re-gates (dennis then Codex) on push.

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
Targets: `linux-x86_64`, `linux-aarch64`, `macos-arm64`. `windows-x86_64` is in the native
wheel matrix but GATED OFF the advertised distribution matrix this cycle (lifecycle
unverified -- see the round-2 note and
`docs/distribution/decisions/2026-10-26-windows-target-gated.md`). ~600-650 MB installed /
~290 MB compressed. Reproducible archive bytes.

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
1. **Windows target (gated off this cycle).** `windows-x86_64` is off the advertised
   matrix until its install/upgrade/rollback lifecycle is verified end to end on a real
   Windows runner (no Windows/`pwsh` here). The re-enable checklist and the signature-
   tooling sub-decision (`openssl` on PATH vs a bundled `minisign`) live in
   `docs/distribution/decisions/2026-10-26-windows-target-gated.md`. The ps1 body is
   corrected and reviewable for that day but inert while gated.
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
