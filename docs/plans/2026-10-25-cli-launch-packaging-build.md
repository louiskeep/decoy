# Decoy CLI Launch Packaging: Build Plan (B-2, §CLI-LAUNCH)

**Status:** build (author lane RW-B). A remote cloud worker authors this on a
branch and pushes; the orchestrator runs the dennis + Codex gate and merges, and
swaps the launch-engine pin when D-4 lands. No gate is claimed here.
**Date:** 2026-10-25
**Scope:** the signed, self-contained CLI distribution for R1, built in the
`decoy` CLI repo only. Packaging and `decoy upgrade` only; no command-surface
redesign, no `decoy query`, no public PyPI.
**Roadmap home:** `decoy-platform/docs/ROADMAP.md` B-2 / §CLI-LAUNCH.
**Findings + spec:**
`decoy-platform/docs/product/cli-launch-readiness-report-2026-10-22.md` and
`docs/plans/2026-10-22-cli-distribution-and-packaging-spec.md`.

**Rules consulted:** universal, development-loop, risk-and-exceptions,
autonomous-operation, release-and-rollback, config-secrets-and-supply-chain,
security, api-and-compatibility, reuse-first, scope-discipline, documentation
(read during planning).

## Risk

R2. Supply-chain and signing surface, a new external contract (the version
document), and a new install path, all reversible (self-hosted bundles, a
version document that points back to the previous `latest`, a `current`-symlink
swap for rollback). No destructive or irreversible production action is taken by
this change: it builds the tooling and the client. Standing up real
infrastructure and cutting the real release are out of scope and stay with the
orchestrator.

## Goal and the guarantee

One install command (or one archive download) lays down a managed, self-contained
`decoy` runtime that is fast by default (native companion present), verifies a
checksum and a signature before it installs anything, refuses loudly rather than
installing on a bad verify, and offers `decoy upgrade` against a Decoy-hosted
version document.

**This change promises, and its tests prove:**

1. The installer refuses on a bad checksum or a bad signature, with a tampered
   artifact, and installs nothing on a failed verify.
2. A missing or mismatched native companion under a managed runtime is a loud,
   actionable refusal, never a silent drop to the slow Python path.
3. `decoy upgrade` reads the version document, picks the artifact for the host
   target, and re-runs the installer against it to land a matched runtime.
4. The launch engine pin is one marked variable, swapped in one place.

**Non-goals (recorded follow-ups, not blockers for this change):** standing up
the real download host, the real version endpoint, or the real signing key
(local test key only, with a documented plug-in point); rebuilding the native
wheel matrix (already green in engine CI); public PyPI; the `decoy observe`
harness; the animated wordmark; macOS Intel support (open lane decision).

## Established solutions

The distribution model is a solved problem; this follows established patterns
rather than inventing them (research 2026-10-25, consistent with the spec's own
2026-10-22 survey):

- **Managed self-contained install** (private interpreter plus a launcher on
  PATH, no user venv): the model `uv` / `rye` / `rustup` / `pipx`-managed tools
  use. Adopt the versioned-dir + `current`-symlink + shell-PATH layout so an
  upgrade is an atomic symlink swap and rollback is the swap back.
- **Embedded interpreter:** `python-build-standalone` (the portable CPython that
  `uv` / `rye` ship), fetched per target, not a hand-rolled interpreter.
- **Native wheels:** PyO3 / maturin + manylinux_2_28 is ALREADY green in
  `decoy-engine/.github/workflows/native-companion.yml`. Build against those
  wheels; do not rebuild the matrix, and do not introduce cibuildwheel (the
  engine CLAUDE.md forbids it there).
- **Artifact integrity + signing:** a SHA-256 checksums manifest plus a detached
  signature over the manifest, verified before extraction, the pattern the
  `rustup` / `uv` installers use. The concrete scheme here is an Ed25519
  detached signature over the `SHA256SUMS` manifest, verified with `openssl`
  (present on all four target platforms and needing no extra binary for the
  bootstrap installer). No custom crypto: `openssl` and `sha256sum` / `shasum`
  are maintained primitives. The signing tool for the real key (minisign vs
  cosign vs a signing service) stays the open lane decision; whichever is
  chosen only has to emit an Ed25519 detached signature over the manifest.
- **Version / update channel:** a static version document plus a cached,
  opt-out, fail-silent startup check and a `decoy upgrade`, the pattern `npm` /
  `cargo` / `gh` use. PEP 440 (`packaging.version`, already an install
  dependency of `packaging`) for version comparison. No telemetry: the client
  fetches a version string and nothing else.
- **Packaging metadata:** PEP 621 (`pyproject`), PEP 440 (versions). Public-index
  resolution (PEP 503) is the FUTURE Apache / PyPI path, out of scope.

Remaining custom work is only assembly and orchestration glue (the bundle
layout, the install script, the version-document shape), not any primitive.

## Design notes

Design principles applied, and the change pain each addresses:

- **One place per fact.** The launch engine version lives in exactly one file,
  `packaging/pin.env`, as `DECOY_LAUNCH_ENGINE_VERSION`, with a loud marker. The
  bundle assembler, the version-document generator, and the pin-single-source
  test all read it; nothing hard-codes a launch version. Pain addressed: the
  D-4 swap is a one-line edit the orchestrator makes once, not a hunt across
  scripts. A sentry test fails if a second literal launch-version source appears.
- **Typed context objects over long parameter lists.** The bundle assembler
  takes a `BundleSpec` dataclass (target, versions, interpreter, wheel set,
  output root) and returns a `BundlePlan`; the version client returns a typed
  `VersionDocument` and `UpdateDecision`. The native gate already uses this
  shape (`PreGateResult`, `RouteClassification`); the new code matches it.
- **Library code does not know its callers.** The version-document client
  (`src/decoy/_version_endpoint.py`) does no printing and no `typer`: it fetches,
  parses, compares, and caches, and returns typed results. The `decoy upgrade`
  command and the startup notice are the two callers that render. The assembler
  and installer live in `packaging/`, not in `src/decoy/`, because they are
  build-and-ship tooling, not CLI runtime.
- **No default that silently turns a degraded operation on.** Native-on-by-default
  with a loud refusal is enforced at the engine-call gate: under a managed
  runtime (the launcher sets `DECOY_MANAGED_RUNTIME=1`), an absent or broken
  companion is a `NativeGateError`, not the info-and-fallback a bare `pip`
  install still gets. `--no-native` stays the explicit, documented opt-out.
- **An external contract is versioned and degrades cleanly.** The version
  document has a JSON schema, a `schema_version`, and defined behavior for
  omitted fields, so an older CLI reading a newer document degrades rather than
  crashing (api-and-compatibility).

House style (typed context objects, one place per fact, single-purpose
functions, no behavior-switching flag arguments, comments that say why) applies
to the code this change adds; it is not a license to restyle untouched code.

## What is built (file map)

CLI runtime (`src/decoy/`):

- `_version_endpoint.py`: the version-document client. Fetch (urllib, short
  timeout, fail-silent), parse + validate against the contract, PEP 440 compare,
  a cache (read/write with a timestamp and a cadence window), and
  `compute_update_decision()`. All I/O is injectable for tests; the module sends
  no identifiers and no telemetry.
- `cli/upgrade.py`: the `decoy upgrade` command. `--check` reports latest vs
  current without installing; the default re-runs the installer for the detected
  target against the version document and lands a matched runtime; `--version X`
  pins a specific version. The resolve-and-invoke core is a testable helper that
  takes an injected fetcher and an injected installer runner.
- `_native_gate.py`: add the managed-runtime escalation to the default-intent
  path (see "Native-on-by-default").
- `__main__.py`: register `upgrade`; call the (fully gated, fail-silent) startup
  notice from the root callback.

Packaging tooling (`packaging/`, new tree):

- `pin.env`: the single launch-engine pin variable.
- `bundle/targets.py`: the four approved targets, mirroring
  `decoy-engine/docs/native/supported-matrix.md`.
- `bundle/assemble.py`: the bundle assembler (plan / dry-run + real assembly),
  the `BundleSpec` / `BundlePlan` types, and the pin-match assertion.
- `bundle/launcher/decoy`, `bundle/launcher/decoy.cmd`: the launcher templates
  (posix symlink target + Windows shim) that set `DECOY_MANAGED_RUNTIME=1` and
  invoke the embedded venv entry point.
- `sign/sign.sh`, `sign/gen-test-key.sh`, `sign/README.md`: the signing scheme,
  a local test-key generator (keys never committed), and the key-custody /
  rotation / plug-in doc.
- `install/install.sh`, `install/install.ps1`, `install/decoy-release.pub`: the
  installers (verify-before-extract, loud refusal, PATH, uninstall, offline,
  `--version`) and the committed PUBLIC half of the local TEST key.
- `version/version.schema.json`, `version/version.example.json`,
  `version/serve_stub.py`: the version-document contract, an example, and a
  local stub server for testing (no real infrastructure).
- `README.md`: the operator install / verify / upgrade guide with recorded
  command output, the per-platform build steps, and the signing-key handoff
  point. This becomes part of the R1 canonical smoke.

Tests (`tests/`):

- `unit/test_native_gate_managed_runtime.py`: the loud-refusal proof (injected
  status, no engine needed).
- `unit/test_version_endpoint.py`: parse, compare, cache, cadence, notice
  gating, fail-silent.
- `unit/test_upgrade_command.py`: the resolve-and-invoke helper picks the host
  artifact and re-runs the installer; version-match.
- `unit/test_bundle_assembler.py`: plan / layout / manifest / pin-match, and a
  version-mismatch raises.
- `unit/test_pin_single_source.py`: the pin is one variable; no second literal
  launch-version source.
- `packaging/test_install_verify.py`: assemble a tiny fake bundle, sign it with
  a generated test key, install it (success + layout), then tamper the bundle
  and the signature and assert a hard refusal with nothing installed; and assert
  an unsupported target fails loudly.

## Acceptance tests (pinned before build)

1. `install.sh` against a tampered bundle exits non-zero, prints a clear
   verify-failed message, and leaves no `~/.decoy/versions/<version>/` and no
   launcher. Same for a tampered signature. (`test_install_verify.py`.)
2. Under `DECOY_MANAGED_RUNTIME=1`, a default-intent run with an absent or broken
   companion raises `NativeGateError` with an actionable message; without the
   marker, today's info-and-fallback behavior is unchanged.
   (`test_native_gate_managed_runtime.py`.)
3. `decoy upgrade` with a stub version document and a stub installer runner
   resolves the host target's artifact and calls the installer with the document's
   version and URL; a document with no artifact for the host target fails loudly.
   (`test_upgrade_command.py`.)
4. `grep` finds the launch engine version as a value only in `packaging/pin.env`.
   (`test_pin_single_source.py`.)
5. The existing surface sentries stay green: `docs/cli-reference.md` regenerated
   with `upgrade`, and the root-help / README consistency allowlists updated.
6. `ruff check` clean on the new code; no unicode em-dash anywhere.

Known environment limit (recorded honestly): this build ran in a Python 3.13
container where `decoy-engine` (requires-python `<3.13`) cannot be installed, so
the engine-dependent e2e suite was not run here. The new tests are engine-free by
construction (the native gate accepts an injected status). The orchestrator's
gate runs the full suite against the real engine build.

## Release and rollback

The release unit is one signed bundle set plus the updated version document.
Preconditions: all target bundles built, smoked, signed, checksums published.
Rollback: the version document points `latest` back to the previous version, and
`decoy upgrade` / the installer's `current`-symlink swap returns a user to the
prior version. No data migration is involved, so the binary rollback is the whole
rollback. This change does not perform a release; it builds the mechanism.

## Build slices mapping (from the spec)

This plan builds the `decoy`-repo portions of spec slices S2 (bundle assembler),
S3 (install script + signing), S4 (version endpoint + the client half of the
notice), S5 (`decoy upgrade`), and S6 (docs). Spec slice S1 (the engine-repo
tag-triggered native release workflow) is explicitly out of this lane's boundary
(do not touch `decoy-engine` source); the per-platform build steps doc records
what S1 must publish for the assembler to consume.

## Completion

Author lane RW-B. Built on branch `claude/upbeat-shannon-r8zfmw` (the
orchestrator-designated branch for this repo; the system branch rule overrides
the handoff's suggested `feat/cli-launch-packaging` name, and a remote worker may
not push to a different branch without explicit permission). Not gated, not
merged: the orchestrator runs the dennis + Codex gate and swaps the launch-engine
pin when D-4 lands.

### What was built

- **Engine pin as one marked variable.** `packaging/pin.env` holds
  `DECOY_LAUNCH_ENGINE_VERSION` (currently the current engine build `0.12.0`, a
  placeholder with a loud "swap on D-4" marker), plus the native ABI tag, the
  standalone-CPython pin, and the CLI version. Every tool reads it; nothing else
  assigns a launch-engine version (a sentry enforces this).
- **Bundle assembler + launcher + targets.** `packaging/bundle/assemble.py`
  assembles a per-target bundle (embedded CPython + matched wheels into a private
  venv + a launcher + a manifest), and enforces the matched-version /
  matched-target invariant before any disk I/O. `packaging/bundle/launcher/`
  carries the posix + Windows launchers that set `DECOY_MANAGED_RUNTIME=1`.
  `packaging/bundle/targets.py` mirrors the engine's four approved targets.
- **Installer with verify.** `packaging/install/install.sh` (+ `install.ps1`)
  detects the target (loud fail on an unsupported one), verifies a SHA-256
  checksum and an ECDSA-P256/SHA-256 signature over the manifest BEFORE
  extracting, hard-stops on a bad verify (nothing installed), lays down the
  versioned runtime, flips `current` atomically, puts the launcher on PATH, and
  supports `--version`, offline local install, and `uninstall`.
- **Signing.** `packaging/sign/` has the manifest-signing script, a local
  test-key generator (keys `.gitignore`'d, never committed), and a README with
  the custody / rotation / plug-in point. The committed public key is the TEST
  key's public half.
- **Version endpoint + client + `decoy upgrade`.** `packaging/version/` holds the
  JSON-schema contract, an example, and a stub server. `decoy._version_endpoint`
  is the fetch / parse / PEP-440 / cache / notice client (no telemetry).
  `decoy upgrade` (+ `--check`) re-runs the installer against the version
  document to land a matched runtime. A gated, fail-silent startup notice and the
  `--no-update-check` opt-out are wired into the root callback.
- **Native-on-by-default, loud refusal.** `decoy._native_gate` escalates an
  absent companion on a native-eligible job to a `NativeGateError` under the
  managed-runtime marker; present-but-broken already refused. A bare `pip`
  install keeps today's soft fallback.

### What is proven by tests (ran green here)

- `tests/packaging/test_install_verify.py` (6): install succeeds and lays down
  the runtime; a tampered tarball, a tampered signature, and a tampered manifest
  entry are each refused with NOTHING installed; an unsupported target fails
  loudly; uninstall removes the runtime.
- `tests/unit/test_native_gate_managed_runtime.py` (8): the loud-refusal matrix.
- `tests/unit/test_version_endpoint.py` (23): parse / degrade / compare / cache /
  cadence / notice-gating / fail-silent.
- `tests/unit/test_upgrade_command.py` (13): plan + perform + command surface,
  including that upgrade invokes the installer with the resolved version.
- `tests/unit/test_bundle_assembler.py` (7) and `test_pin_single_source.py` (2).
- The surface sentries stay green: `docs/cli-reference.md` regenerated with
  `upgrade`, root-help + README updated. `ruff check src tests` is clean. No
  unicode em-dash in any new file.

### Where the real things plug in

- **Launch engine pin:** swap `DECOY_LAUNCH_ENGINE_VERSION` in
  `packaging/pin.env` when D-4 cuts the certified launch engine; the whole
  pipeline repins off that one value.
- **Signing key:** generate + hold the real key out of band; point `sign.sh` at
  it, and replace the committed public TEST key in three places
  (`packaging/install/decoy-release.pub` and the embedded block in `install.sh` /
  `install.ps1`). See `packaging/sign/README.md`.
- **Version endpoint + download host:** publish `version.json` (per
  `packaging/version/version.schema.json`) and the signed bundles at the real
  host; the client reads `DECOY_UPDATE_URL` / `DEFAULT_VERSION_URL` and the
  installer reads `DECOY_INSTALL_BASE_URL`.

### Uncertain / needs the orchestrator's gate

- The engine-dependent e2e suite was NOT run here: this container is Python 3.13
  and `decoy-engine` requires `<3.13`, so it cannot be installed. All new tests
  are engine-free by construction (the native gate takes an injected status). The
  gate must run the full suite against the real engine build.
- The bundle assembler's real wheel-install step and the per-target smoke
  (`decoy doctor`, a real mask, the native-route assertion) run on the matching
  host in the build pipeline; here only the plan / layout / manifest / matching
  are exercised (no 600 MB CPython, no real wheels, no engine).
- `install.ps1` is verified by inspection only (no Windows runner here); it
  mirrors the proven `install.sh` verify-before-extract flow and gets real
  verification in CI on a Windows host.
- Scope note: a root `--no-update-check` option was added (required by the update
  channel, readiness report 4.3). It is additive with a safe default; it is the
  one root-surface change beyond the `decoy upgrade` command.

## Remediation (dennis gate NO-GO, 2026-10-25)

A dennis adversarial gate returned NO-GO on the `decoy upgrade` client path. The
installer core (verify-before-extract, tamper refusals, offline path, native
loud refusal, single-source pin, committed public-key-only) was unaffected and
is untouched. Both blockers were real failures of stated acceptance and both
were untested because the real install path was monkeypatched out of every test.
Fixed at root on this branch, with the previously missing tests added. Still not
gated, not merged: the orchestrator re-gates (dennis + Codex) and merges.

- **B1 (blocker) signed downgrade / rollback.** `plan_upgrade` only treated
  `resolved == current` as up-to-date, so an endpoint serving a `latest` LOWER
  than installed would install the older (still signature-valid) build: a
  rollback/replay. Fixed: an unpinned upgrade now PEP-440-compares
  (`_version_endpoint._compare`) and only moves forward; a served-lower or
  incomparable `latest` installs nothing. A non-newer build installs only via an
  explicit `--version`, and a true downgrade even then requires the new
  `--allow-downgrade`. A yanked resolved version is refused. Tests: unpinned
  served-lower and incomparable install nothing; pinned downgrade refused without
  the ack and allowed with it; yanked refused; command-level no-op proof.
- **B2 (blocker) arbitrary-URL fetch-and-execute of the trust anchor.** The
  default runner derived a base URL from the network-fetched document and, by
  default, downloaded and ran `install.sh` from that document-controlled host
  with no verification, defeating the signing chain (the release pubkey lives in
  install.sh). Fixed: the install scripts and the version schema now ship as
  package data under `decoy/_packaging/` (hatch `force-include`); the runner runs
  the LOCAL copy and never downloads the installer. The artifact URL must be
  https and share the version endpoint's origin, and `DECOY_INSTALL_BASE_URL` is
  constrained to that same origin. Test: the real (non-monkeypatched) runner
  refuses non-https, `file://`, cross-origin artifact URLs and a cross-origin
  base-URL override, makes no network request, and otherwise runs the local
  script with the origin-pinned base URL.
- **M3 version client fails closed.** The executing path now validates the
  document against `version.schema.json` (jsonschema, shipped as package data)
  and fails closed before planning an install; the non-executing startup-notice
  and `--check` paths keep the tolerant degrade.
- **M4 update-check cache in CWD.** An empty `DECOY_INSTALL_HOME` (`Path("")` is
  truthy) made the cache land at `./update-check.json`. Fixed to treat an empty
  value as unset and fall back to `~/.decoy`.
- **LOWs.** `install.sh` / `install.ps1` now extract into a temp dir and swap
  into place (a failed extract no longer breaks the active runtime), and validate
  the version string against `^[0-9A-Za-z.+-]+$` before using it in paths/URLs.
  `plan_upgrade` now refuses a yanked target (folded into B1).

New runtime dependency: `jsonschema>=4.0` (M3). New root/command surface:
`decoy upgrade --allow-downgrade` (B1); `docs/cli-reference.md` regenerated. All
touched tests ran green here (`tests/unit/test_upgrade_command.py`,
`tests/unit/test_version_endpoint.py`, `tests/packaging/test_install_verify.py`),
ruff clean, no em-dash. The engine-dependent suite still cannot run in this
Python 3.13 container (unchanged limit); the new tests remain engine-free.
