# B-2 CLI-LAUNCH packaging: completion plan + remediation addendum

Status: plan (§4 code residual DISPATCHABLE now; §5 release ACTIVATION blocked on owner decisions + release infra, see §7).
Feature: F44 (signed distribution, containers, SBOM, upgrade recovery).
Tier: R2 (security-sensitive supply-chain surface + a consequential public distribution). Plan gate chain: Dennis -> Codex.
Branches: CLI `claude/youthful-ride-0azacx` (repo `decoy`, 6 ahead / 1 behind) + engine `claude/youthful-ride-0azacx` (additive release workflow, ~40 behind).
Author: orchestrator (local). Created: 2026-10-28.

Rules consulted: `~/dev-rules/00-universal.md`, `~/dev-rules/development-loop.md`,
`~/dev-rules/risk-and-exceptions.md`, `~/dev-rules/security.md`,
`~/dev-rules/config-secrets-and-supply-chain.md`, `~/dev-rules/release-and-rollback.md`,
`~/dev-rules/testing.md`; plan source `docs/plans/2026-10-22-cli-distribution-and-packaging-spec.md`.

## 1. Where it stands

Substantial and close on the Linux path, but NOT merge-ready. Built (in
`decoy/src/decoy/distribution/` + `decoy/packaging_tools/`): Ed25519 detached verify,
checksum manifest, `cli-version-document/v1`, `~/.decoy` layout + atomic current-symlink
swap, native loud-refusal self-check, verified install + rollback, single-flight `flock`,
`decoy upgrade` + startup update-notice. Engine side: a tag-triggered signed
native-companion release workflow (additive). Smoke: linux-x86_64 only, all pass.

The hard DESIGN churn is resolved: the 3 Codex NO-GO rounds were all on the installer's
version-dir promotion, a self-reinforcing in-place-mutation patch loop that only broke when
the owner forced the design back to the plan's atomic-swap primitive in round 4. Round 5
sits on the correct primitive.

## 2. Mandated primitive (PIN it, so no future round regresses)

NEVER mutate a `versions/<v>/` directory in place. Install/upgrade = stage a FRESH version
dir, then ONE atomic `os.replace` symlink flip; rollback = flip the symlink back. FORBID
delete-then-replace and move-aside/backup/restore in-place mutation (both the Python
installer and the `install.sh`/`install.ps1` shells). This is the design decision that
ended the NO-GO loop; it is now a hard constraint, not an implementation choice.

## 3. Adversarial acceptance set (enumerated from what the rounds discovered)

The security surface is wide; the acceptance must pin every class a round surfaced:
- Signed-bundle + checksum + signature verification BEFORE extraction; tamper/bad-sig =
  hard refusal (no partial install).
- Signature ENVELOPE/algorithm pinning (reject an unexpected alg or envelope schema;
  `test_verify_envelope_schema_and_alg`).
- Yanked-version refusal (`install_version` consults `is_yanked`;
  `test_version_document_pep440_and_flags`).
- Wrong-version / wrong-target refusal BEFORE promotion or mutation of any RETAINED runtime
  (quarantine extraction into an isolated staging dir is permitted; the live `current` and
  its version slot are never touched until the atomic flip).
- Bytecode-cache rejection (run with `-B`; reject a planted `__pycache__`), and `-I`
  import isolation so a planted module on sys.path cannot run.
- Single-flight `flock`: concurrent installs/upgrades serialize, never interleave a flip.
- Same-version repair stages fresh + flips (never deletes the live runtime).
- Offline/local rollback resolves before any network and works with no network.
- Native-on-by-default loud refusal at install AND run when the companion is absent /
  ABI-mismatched. The RUN-time refusal must be enforced by the managed runtime, with
  BEHAVIORAL acceptance for both companion-removal-after-install and ABI-mismatch-after-install
  (not only the install-time self-check); preserve the separate pip/dev import contract.

The §3 list states the required classes; the branch's ~52 test functions are COUNTED, not a
proven coverage result. The code gate must land an acceptance-to-test matrix separating
existing evidence from required additions, and must specifically add: installer-level
yanked-version refusal AND online-bootstrap yank enforcement (`install.sh` does not yet check
`yanked`); detached-signature SCHEMA enforcement tests distinct from the envelope-helper test;
and an explicit offline-rollback policy statement. Document the pinned-older-download checksum
exception accurately rather than implying a universal checksum sidecar.

## 4. Code residual (doable on a Linux worker, under the §2 primitive)

- Rebase: CLI 1 behind (trivial); engine ~40 behind (additive workflow file, expected-low
  conflict, must still rebase) -- and RE-RUN engine CI on the rebased engine branch before the
  re-gate; do not assume low-conflict across ~40 commits.
- Before landing: re-run BOTH repos' applicable checks on the FINAL rebased SHAs (fresh CLI
  verification, not only engine CI), gather the §3 acceptance evidence, then a fresh
  Dennis -> Codex implementation gate on those SHAs.
- Keep the `release_key.pub.pem` placeholder behavior (hard-refuse upgrade when unpinned)
  until a real key exists (§7).

## 5. Release-ops residual (a remote Linux worker CANNOT complete alone)

- Provision the real Ed25519 signing key: inject the real public key into
  `release_key.pub.pem` AND the inline pin in `install.sh`; create the engine secret
  `DECOY_RELEASE_KEY_PEM`; run the tag pipeline on a real tag (never run yet).
- Multi-arch smoke on real runners: `macos-arm64`, `linux-aarch64` (and Windows if
  re-enabled); the e2e native suites need a published `decoy-engine-native`.
- Host the version endpoint (`decoy.dev/cli/version.json`, signed static doc; generator
  exists, not hosted).

## 6. Pinned guarantee and non-goals

**Guarantee.** A self-hosted, Ed25519-signed, checksum-verified CLI distribution whose
install/upgrade/rollback are PROCESS-INTERRUPTION-safe on supported POSIX systems (atomic
symlink flip, never in-place mutation), with a loud native-companion refusal. Power-loss
durability (fsync ordering of the swap) is not claimed by the inspected code.

**Non-goals (this cycle).** Windows (gated off, see the decision record + its 4-item
re-enable checklist); macOS Intel; the final engine-pin cut (awaits D-4 launch engine);
containers/SBOM (F44 Phase 3).

## 7. Owner decisions that BLOCK dispatch (needs Cam)

A remote worker cannot decide these, and the RELEASE-OPS residual (§5) cannot start without
them: (a) signing-key custody store + rotation policy; (b) the download host; (c) release
cadence; (d) macOS Intel support (currently unsupported); (e) Windows re-enable or keep
gated; (f) the engine pin for the final bundle (tied to D-4).

**The §4 CODE residual carries ZERO §7 dependency and is dispatchable NOW.** The atomic-swap
primitive is pinned and implemented; the installer accepts compatible, validated bundles
without changing installer version constants (so §7(f)/D-4 does not gate it). Crucially,
LANDING the code publishes NO release because §4 explicitly EXCLUDES every release trigger:
no release-tag push, no manual release-workflow dispatch, no production key
provisioning/injection, no artifact/endpoint publication. (The engine workflow has BOTH a
`push: native-v*` trigger and a `workflow_dispatch` manual path, and its signing job refuses a
missing engine secret independently of the CLI placeholder, and `DECOY_RELEASE_PUBKEY_FILE`
can override the CLI placeholder -- so "ships nothing releasable" is NOT an enforceable
property of the placeholder key; it is a property of §4 excluding the triggers. Without a key
override the placeholder CLI still refuses `upgrade` before network access, as defence in
depth.) So the dispatchable slice is: rebase CLI + engine onto current main, re-run both
repos' checks on the final SHAs, fresh Dennis -> Codex on those SHAs against the pinned §2
primitive + §3 acceptance, then land. This also arrests the engine branch's growing
40-commit drift. All release ACTIVATION stays in §5, blocked on §7(a)-(f).
