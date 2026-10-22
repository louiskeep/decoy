# Decoy CLI Distribution and Packaging Spec

**Status:** draft, pre-gate. Needs a Codex plan-gate before any build (per the
cross-model gate rule). Authored early so the `§CLI-LAUNCH` pre-release lane is
build-ready; the build itself runs after the V1 completion point.
**Date:** 2026-10-22
**Scope:** how the `decoy` CLI (with the Rust engine) is packaged, distributed,
installed, and updated for the engine/CLI/web launch.
**Roadmap home:** `§CLI-LAUNCH` in `decoy-platform/docs/ROADMAP.md`. Findings:
`decoy-platform/docs/product/cli-launch-readiness-report-2026-10-22.md`.

**Rules consulted:** universal, development-loop, risk-and-exceptions,
release-and-rollback, config-secrets-and-supply-chain, security,
api-and-compatibility, documentation (read during planning). This is a scoping
spec; each build slice below opens its own gated PLAN (with the Codex plan-gate)
before implementation.

## Goal and non-goals

**Goal:** a user runs one install command (or downloads one archive) and gets a
`decoy` CLI that is fast by default (Rust companion present), with a managed,
self-contained runtime they never have to think about, and a startup notice plus
`decoy upgrade` when a new version ships.

**Non-goals:** public PyPI distribution (that arrives with the Apache flip, post
adoption); the platform (separate, private, Docker); the `decoy observe` harness
(post-launch adoption lane).

## Inherited decisions (Cam 2026-10-22)

- Self-hosted, signed, per-platform bundles. Not public PyPI yet.
- Engine + CLI both BUSL-1.1 at launch; convert to Apache after adoption.
- Managed self-contained runtime, no user-managed venv.
- Native on by default; a missing companion is a loud refusal, never a silent
  drop to the slow Python path.
- Hosted version endpoint feeds the startup notice and `decoy upgrade`.

## Current state (what already exists)

- **The native wheel matrix is built and green in CI.** `decoy-engine`'s
  `.github/workflows/native-companion.yml` (Task 3.1) builds `decoy-engine-native`
  for the four approved targets (Linux x86_64 + aarch64 under manylinux_2_28,
  Windows x86_64, macOS arm64) across cp310-cp312 via `PyO3/maturin-action`,
  asserts the compiled `_kernel` is in each wheel, runs the shared
  `parity_smoke.py` (ABI + hash/index KATs) on every row, and uploads the wheels
  as artifacts (14-day retention). The authoritative target list lives in
  `decoy-engine/docs/native/supported-matrix.md`.
- **The CLI and engine are pure-Python hatchling builds** (`uv build` produces
  sdist + wheel trivially).
- **What does NOT exist yet:** a durable, signed, versioned release pipeline (the
  current matrix produces 14-day CI artifacts, not published release artifacts);
  the bundle assembler; the managed-runtime install; signing; the install script;
  the hosted version endpoint; the `decoy upgrade` command; the startup notice.

So the packaging job is mostly release-pipeline and bundling on top of an
existing, proven build matrix, not a build-from-scratch.

## Established solutions

The distribution model is a solved problem; this follows established patterns
rather than inventing them (research 2026-10-22):

- **Managed self-contained CLI install** (private interpreter + a launcher on
  PATH, no user venv): the model `uv`/`rye`, `rustup`, and `pipx`-managed tools
  use. Adopt their install-dir + `current`-symlink + shell-PATH approach.
- **Embedded interpreter:** `python-build-standalone` (the portable CPython
  `uv`/`rye` ship), not a hand-rolled interpreter.
- **Native wheels:** PyO3/maturin + manylinux_2_28 is ALREADY in use
  (`native-companion.yml`); keep it, add the publish step. No new build method
  (the engine CLAUDE.md forbids cibuildwheel here).
- **Artifact integrity + signing:** a maintained signer (minisign or
  Sigstore/cosign) + a SHA-256 checksums manifest + verify-before-extract, the
  pattern the `rustup`/`uv` installers use. No custom crypto (security.md + the
  engine methodology rule).
- **Version / update channel:** a static version document plus a cached, opt-out,
  fail-silent startup check, the pattern `npm`/`cargo`/`gh` and many CLIs use;
  PEP 440 for version comparison. No telemetry.
- **Packaging metadata:** PEP 621 (`pyproject`), PEP 440 (versions). Public-index
  resolution (PEP 503) is the FUTURE Apache/PyPI path, out of scope here.

Remaining custom work is only assembly and orchestration glue (bundle layout,
install script, the version-document shape), not any primitive.

## Target matrix

The four approved targets (from `supported-matrix.md`): Linux x86_64, Linux
aarch64, Windows x86_64, macOS arm64. Note: **no macOS x86_64 (Intel)**. Decision
needed (below): Intel Mac unsupported at launch, or run the arm64 build under
Rosetta, or add the target.

## Bundle design

Each per-target bundle contains:
1. a **standalone CPython** (a python-build-standalone distribution), pinned to
   one cp3.x in the supported range,
2. a **private venv** with the matched `decoy-engine` + the correct
   `decoy-engine-native` wheel for the target + `decoy-cli` + their deps already
   installed,
3. a **`decoy` launcher** that invokes the venv's entry point.

On-disk layout: a versioned directory under `~/.decoy/` (e.g.
`~/.decoy/versions/<version>/`) with a `current` symlink, so `decoy upgrade` is an
atomic symlink swap and rollback is trivial. Size budget ~600-650 MB per install
(native + pandas/polars/duckdb/pyarrow dominate).

## Build pipeline

1. Build engine + CLI wheels (hatchling) at the launch versions.
2. Produce **durable, signed** native wheels per target. Extend the existing
   `native-companion.yml` matrix into a release workflow (tag-triggered) that
   uploads versioned artifacts instead of 14-day ones. The build + parity logic
   is already proven; this adds durability + signing, not new build logic.
3. Fetch the pinned standalone CPython per target.
4. Assemble each per-target bundle: install the matched wheels into the embedded
   venv.
5. Smoke each bundle on its target: `decoy doctor`, a real mask run, and an
   assertion that the native route actually engaged (not a silent Python
   fallback).
6. Checksum + sign each bundle and a manifest.
7. Publish bundles to the download host and update the version endpoint.

## Install script contract

`curl -LsSf https://decoy.dev/install.sh | sh` (plus an `install.ps1` for
Windows). The script:
- detects OS + arch and maps to a target; a target with no bundle **fails loudly**
  with a clear message (never a partial or slow install),
- downloads the bundle + its checksum + its signature,
- **verifies the signature before extracting** (a `curl | sh` installer requires
  it),
- extracts to `~/.decoy/versions/<version>/`, flips the `current` symlink,
- puts the `decoy` launcher on PATH (`~/.local/bin` symlink on macOS/Linux, a shim
  on Windows) and tells the user to restart the shell or source the profile,
- is idempotent and re-runnable, supports a pinned `--version`, and ships an
  `uninstall`.
- Offline/air-gapped: the same bundle + checksum + signature are downloadable as a
  plain archive and installable from a local path; the version check degrades
  silently.

## Signing scheme

Sign bundles and the checksums manifest (minisign or cosign, decision below).
Publish the public key in the repo and on the site. The install script verifies
the signature before extraction. Define private-key custody and rotation
(config-secrets-and-supply-chain: secrets stay out of source/artifacts, with a
rotation path).

## Version endpoint contract

`GET https://decoy.dev/cli/version.json` returns, at minimum: `{ latest,
min_supported, yanked: [...], message, artifacts: { <target>: { url, sha256,
sig } } }`. It can start as static JSON served from the site behind a CDN. The
client sends **no data, no identifiers, no telemetry**: it fetches a version
document and nothing else. Treat this document as an external contract
(api-and-compatibility): version it and keep omitted-field behavior defined so an
older CLI reading a newer document degrades cleanly.

## Update flow

- **Startup notice:** interactive sessions only. Cache the last check + timestamp
  under `~/.decoy/`, check at most once per cadence window, non-blocking,
  fail-silent on any network error. Suppressed with no TTY, under CI, and on
  `--json` or piped output. Opt out via `--no-update-check`, the
  `DECOY_NO_UPDATE_CHECK` env var, and a config setting. One line, with the exact
  upgrade command.
- **`decoy upgrade`:** fetches the latest bundle for the target, verifies it, and
  swaps the `current` symlink (rollback = swap back).

## Native-on-by-default and loud refusal

Every bundle ships the matched native wheel, so the companion is present by
construction. The CLI already classifies the route and fails closed under
`--native`; at launch the default is native-on, and a missing companion (only
reachable by tampering or an unsupported target) produces a clear error, not a
silent slow path. `--no-native` stays available as an explicit debugging opt-out.
The default must not silently enable a degraded mode (config-secrets rule: no
default that silently turns an unsafe/degraded operation on).

## Open decisions (for the lane, not now)

1. **macOS Intel (x86_64):** unsupported, Rosetta on the arm64 build, or add the
   target (grows the matrix).
2. **Download host:** static site + CDN, or object storage; where signed bundles
   live.
3. **Signing tool + key custody:** minisign vs cosign; where the private key
   lives and how it rotates.
4. **Download gating under BUSL:** open download with click-through license, or a
   gated download (email / license acceptance) so adoption is visible.
5. **Release cadence:** so "new version available" carries meaning.

## Build slices (ordered, each gate-able)

- **S1 native release workflow** (engine repo): extend the proven
  `native-companion.yml` matrix into a tag-triggered pipeline that publishes
  durable, signed, versioned wheels. Additive; no engine source change.
- **S2 bundle assembler + per-target smoke** (new packaging tooling): standalone
  CPython + matched wheels into a bundle, smoke each on its target.
- **S3 install script + signing** (packaging): `install.sh` + `install.ps1`,
  signature verification, checksums, uninstall.
- **S4 version endpoint + startup notice** (CLI repo + site): the hosted document
  + the CLI update-notice feature.
- **S5 `decoy upgrade`** (CLI repo).
- **S6 docs** (CLI repo): install guide, supported platforms, offline install,
  uninstall.

S1-S3 are the critical path to a first installable bundle; S4-S5 deliver the
update channel; S6 ships the docs. Each slice runs the full dev loop (plan +
Codex plan-gate, build, dennis, Codex final gate, CI) before merge.

## Release and rollback

The release unit is one signed bundle set + the updated version document.
Preconditions: all target bundles built and smoked, signed, checksums published.
Rollback: the version document points back to the previous `latest`, and
`decoy upgrade` / the installer's `current`-symlink swap returns a user to the
prior version (no data migration is involved, so the binary rollback is the whole
rollback). Post-release signal: a smoke install from the published artifacts on
each target before announcing.

## Relationship to active work (OBS / TQ / GEN-API)

Everything here lives in the `decoy` CLI repo, in new packaging tooling, or as an
additive workflow in the engine repo (S1 adds a workflow file; it does not touch
engine source that GEN-API or TQ edit). Nothing here touches `decoy-platform`
`api/` (OBS territory). So this lane can build in parallel without interference
when it is scheduled.
