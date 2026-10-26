# Decision: Windows gated off the advertised CLI distribution matrix (launch R2)

**Date:** 2026-10-26
**Status:** accepted (this remediation cycle)
**Area:** CLI launch packaging / self-hosted distribution (`src/decoy/distribution/`,
`packaging_tools/`)

## Context

The signed self-hosted distribution (`install.sh`, `install.ps1`, `decoy upgrade`) was
built for four targets: `linux-x86_64`, `linux-aarch64`, `macos-arm64`, and
`windows-x86_64`. The cross-model Codex gate found that the Windows path cannot complete
its lifecycle:

- `install.ps1` moved the quarantined bundle into place and then executed the bundled
  interpreter from its OLD (pre-move) location, so the install could not finish.
- The managed-runtime model is POSIX-shaped: a `current` symlink swap
  (`layout.atomic_point_current_at` via `os.symlink`/`os.replace`) and a
  `python/bin/python3` launcher. On Windows `os.symlink` needs privilege (developer mode
  or admin) and the launcher/interpreter paths differ, so install, upgrade, and rollback
  were never verified end to end.

The launch rule is loud-refusal, never ship-and-hope: "a missing native companion or an
unrunnable install is a hard refusal, never warn-and-continue."

This remediation runs on a remote Linux worker with **no Windows runner and no PowerShell
(`pwsh`) available**, so the Windows install/upgrade/rollback lifecycle **could not be
verified end to end this cycle**.

## Decision

**Gate the `windows-x86_64` target off the advertised matrix** rather than ship an
unrunnable advertised path. Concretely:

- `windows-x86_64` is removed from `decoy.distribution.targets.SUPPORTED_TARGETS`, and
  `detect_target` returns `None` for a Windows host (a loud refusal). This is the single
  lever: `make_version_document` iterates `SUPPORTED_TARGETS`, so the hosted version
  document advertises **no** Windows artifact; `build_bundle` refuses a target outside the
  matrix, so no Windows bundle can be produced; and `install.sh` / `install.ps1` refuse at
  target detection.
- The Codex-flagged Windows bugs were **also fixed at the source** in `install.ps1` so the
  path is correct for the day Windows is re-enabled (not merely bypassed): the interpreter
  path is recomputed AFTER promotion, the declared-version/target identity check runs
  before any deletion, and bytecode writing is disabled. That body is retained but inert
  while the target is gated off (`Resolve-Target` returns `""`).

Linux (x86_64, aarch64) and macOS arm64 remain fully supported, built, advertised, and
tested (the Linux path by the unit suite and the end-to-end smoke).

## Consequences

- Windows users get a clear refusal ("not a supported target at launch") instead of a
  half-installed or unrunnable runtime.
- No change to the supported targets' behaviour.

## Re-enabling Windows (prerequisites)

1. Decide the `current` mechanism on Windows (directory junction, a `current.txt` pointer
   read by a `.cmd` launcher, or a privileged symlink) and implement it in
   `layout`/`installer` without POSIX `os.symlink` assumptions.
2. Use platform-specific interpreter + launcher paths throughout
   (`python\python.exe` vs `python/bin/python3`), recomputing them after promotion.
3. Verify install -> `decoy --version`/`decoy run` -> `decoy upgrade` -> rollback end to
   end on a real Windows runner (and a `pwsh`-driven regression for the installer's
   wrong-version refusal, mirroring the sh/Python tests).
4. Re-add `windows-x86_64` to `SUPPORTED_TARGETS` and have `Resolve-Target` return it for
   AMD64 again.

Until all four hold, Windows stays off the advertised matrix.
