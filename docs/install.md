# Installing the Decoy CLI

Decoy ships as a **signed, self-contained, per-platform bundle** served from Decoy, not
from public PyPI. One command lays down a managed runtime (a bundled Python + the matched
engine, native companion, and CLI) and puts a `decoy` launcher on your PATH. You do not
bring your own Python, and a fast native run is guaranteed: every bundle ships the
platform-matched Rust companion and refuses loudly if it is missing, rather than silently
dropping to the slow path.

> License: the engine and CLI ship under BUSL-1.1 at launch. Public `pip install` arrives
> later, with the license change; it is not the install path today.

## Quick install

Linux / macOS:

```sh
curl -LsSf https://decoy.dev/cli/install.sh | sh
```

Windows is **not supported at launch** (see Supported platforms below).

Then restart your shell (or add the printed directory to `PATH`) and check:

```sh
decoy --version
decoy doctor
```

`decoy doctor` confirms the bundled Python, the engine, and a **present, healthy** native
companion.

## Supported platforms

| Target          | Notes                                   |
| --------------- | --------------------------------------- |
| `linux-x86_64`  | glibc, manylinux_2_28+                   |
| `linux-aarch64` | glibc, manylinux_2_28+                   |
| `macos-arm64`   | Apple Silicon                            |

macOS Intel (x86_64) is **not supported at launch** (it is not in the native wheel
matrix). Windows (x86_64) is **gated off this cycle** until its install/upgrade/rollback
lifecycle is verified end to end (see
`docs/distribution/decisions/2026-10-26-windows-target-gated.md`). On an unsupported
platform the installer refuses with a clear message rather than installing a slow or
broken runtime.

A full install is roughly 600-650 MB on disk (the bundled interpreter plus pandas /
Polars / DuckDB / PyArrow and the native companion).

## What the installer verifies

Before anything is laid down, the installer:

1. fetches the signed version document and verifies its **Ed25519 signature** against the
   release public key pinned in the installer;
2. verifies the bundle's **SHA-256 checksum** against that signed document;
3. verifies the bundle's own **Ed25519 signature**;
4. extracts into a quarantine directory and re-checks every file against the bundle's
   signed manifest;
5. runs a **native-companion self-check** and refuses loudly if the companion is missing
   or ABI-mismatched.

Only then does it swap the new runtime into place. **A failed checksum or signature is a
hard refusal, never a warning-and-continue.** Verification uses `openssl` (Ed25519); the
installer requires it and refuses rather than skip signature verification.

The signed version document is also checked for shape and status, in both the shell
installer and `decoy upgrade`: a correctly signed document of any schema other than
`cli-version-document/v1` is refused, and a version the document lists as **yanked** is
refused whether it is the latest or an explicit `--version` pin. The extracted bundle must
declare the requested version and this host's target; a mismatch is refused before the
bundle's interpreter is run and before any version directory is staged.

**Where the SHA-256 checksum is (and is not) signed.** The checksum is *not* a universal
signed sidecar:

| Path | Checksum source | Trust anchor |
|---|---|---|
| Latest release (installer or `decoy upgrade`) | `sha256` in the **signed** version document | signed checksum + bundle signature |
| Pinned older version (`--version <not latest>`) | the published `.sha256` sidecar, **unsigned**, best-effort (skipped if absent) | bundle Ed25519 signature only |
| Offline `DECOY_LOCAL_BUNDLE` | the required local `.sha256` sidecar, **unsigned** | bundle Ed25519 signature only |

The v1 document carries only the latest release's artifacts, so a pinned older download has
no signed checksum; a corrupted or tampered older bundle is caught by the signature, not
the checksum. The offline path has no version document at all, so yank status cannot be
checked there (no network by design); the pinned-key signature is still enforced.

**Run-time companion enforcement.** The native companion is re-checked on every
invocation of a *managed* runtime, not only at install: if it is removed or becomes
ABI-mismatched afterwards, every command except `decoy upgrade` (the repair path) and
`--version`/`--help` refuses loudly with exit code 3 and points at `decoy upgrade --force`.
A pip/dev install is never guarded; it keeps the engine's optional-accelerator contract.

## Upgrading

The one-line installer is **first-install-only**: it lays down a fresh runtime and refuses
to replace an existing one (re-running it on an installed host prints a notice and points
you here). Every upgrade and same-version repair goes through `decoy upgrade`:

```sh
decoy upgrade          # upgrade to the latest release if one is available
decoy upgrade --check  # report only; change nothing
decoy upgrade --version 0.2.0   # install a specific version (pin or downgrade)
decoy upgrade --force  # reinstall/repair the current version from verified bits
```

`decoy upgrade` re-runs the same verified install against the hosted version endpoint,
stages the new runtime in a fresh version directory beside the current one, and swaps the
`current` pointer atomically. It never replaces a version directory in place -- a
same-version repair stages a distinct directory and flips to it, then reclaims the old one
-- so an interrupted upgrade always leaves a working runtime. The previous version stays on disk, so a rollback is:

```sh
decoy upgrade --version <previous-version>
```

When that version is still installed locally (the common rollback case), this is an
atomic `current`-pointer swap back to the retained runtime: no download, and it never
overwrites the bits it is rolling back to. A version not present locally is downloaded
and verified by the published URL convention, and is installed only if the downloaded
bundle actually declares that version (a resolution mismatch refuses without touching any
existing version directory). A failed post-upgrade validation rolls the `current` pointer
back automatically.

**Offline-rollback policy.** Rolling back to a retained local version resolves before any
network access and works with no network. It still requires a pinned release key (a build
with the unresolved placeholder refuses), and it re-verifies the retained runtime's signed
manifest and native self-check before flipping. It does **not** consult the yank list (that
needs the network): activating a retained version that was yanked after you installed it is
allowed, and `decoy upgrade --check` online reports the yank. Add `--force` to re-download
and re-verify instead.

**Guarantee.** Install, upgrade and rollback are interruption-safe on supported POSIX
systems: a fresh directory is staged and `current` is flipped with one atomic rename, so
a killed process leaves either the old or the new runtime live. Power-loss durability
(fsync ordering of the flip) is **not** claimed.

## Update notice

On an interactive start, Decoy checks the version endpoint at most once per day and prints
one line to stderr if a newer version exists. It is advisory and non-blocking, sends no
data or identifiers, and fails silent on any network error. Suppress it with any of:

- `decoy --no-update-check ...`
- `DECOY_NO_UPDATE_CHECK=1`
- a non-interactive / piped / CI session (suppressed automatically).

## Offline / air-gapped install

Download the bundle, its `.sha256`, and its `.sig` for your target on a connected machine,
copy all three to the target, then:

```sh
DECOY_LOCAL_BUNDLE=/path/to/decoy-<version>-<target>.tar.gz sh install.sh
```

The installer verifies the checksum and signature from the local sidecars exactly as it
would for a download. This is a first install only (like the online bootstrap, it refuses
to replace an existing runtime). The update check degrades silently with no network.

## Uninstall

```sh
sh install.sh uninstall     # or: sh uninstall.sh
```

This removes `~/.decoy` and the `decoy` launcher. Remove the PATH line from your shell
profile if you added one.

## Where things live

```
~/.decoy/
  versions/<version>/   one extracted bundle (python/, decoy launcher, wheels, manifest)
  current -> versions/<version>   the live runtime (the atomic swap point)
  cache/                update-check cache
~/.local/bin/decoy      the launcher on PATH (POSIX)
```

`DECOY_HOME` and `DECOY_BIN_DIR` override the install root and launcher directory.
