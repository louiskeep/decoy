"""The supported per-platform target ids, and detection of the running host's target.

The authoritative advertised matrix is the set of targets the version document lists
and the build assembles. A host that maps to no target is a LOUD refusal at install,
never a partial or slow install (the launch rule: native-on by default, no silent
fallback).

Targets intentionally NOT in the advertised matrix at launch (both refuse with a clear
message rather than running bits the host cannot complete a lifecycle on):

- **macOS Intel (x86_64):** not in the native wheel matrix. Rosetta-on-arm64 or adding
  the target are a Cam decision.
- **Windows (x86_64):** GATED OFF this cycle. The managed-runtime model is POSIX-shaped
  (a `current` symlink swap + a `python/bin/python3` launcher), and the Windows install/
  upgrade/rollback lifecycle could not be verified end to end in this remediation cycle
  (no Windows runner available). Per the launch rule we refuse rather than advertise an
  unrunnable path. See `docs/distribution/decisions/2026-10-26-windows-target-gated.md`.
  Removing it here is the single lever: `make_version_document` iterates this dict, so no
  Windows artifact is advertised, and `detect_target` returns None on Windows, so the
  installers refuse at target detection.
"""

from __future__ import annotations

import platform

# Target id -> human label. Order is the matrix order.
SUPPORTED_TARGETS: dict[str, str] = {
    "linux-x86_64": "Linux x86_64 (glibc, manylinux_2_28+)",
    "linux-aarch64": "Linux aarch64 (glibc, manylinux_2_28+)",
    "macos-arm64": "macOS arm64 (Apple Silicon)",
}

# machine() values that mean the same architecture, normalized to our ids.
_ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "arm64",
}


def detect_target(system: str | None = None, machine: str | None = None) -> str | None:
    """Map a (system, machine) pair to a supported target id, or None if unsupported.

    Defaults read the running host via `platform`. ``machine`` is lowercased and
    aliased (amd64->x86_64, arm64/aarch64 kept per-OS) before mapping. Returning None
    is the signal for a loud refusal; callers must not substitute a different target."""
    system = (system or platform.system()).lower()
    raw = (machine or platform.machine()).lower()
    arch = _ARCH_ALIASES.get(raw)
    if arch is None:
        return None

    if system == "linux":
        if arch == "x86_64":
            return "linux-x86_64"
        if arch == "aarch64":
            return "linux-aarch64"
    elif system == "darwin":
        # macOS: only arm64 is in the matrix. x86_64 (Intel) is intentionally
        # unsupported at launch -- see the module docstring.
        if arch == "arm64":
            return "macos-arm64"
    # Windows is gated off the advertised matrix this cycle (see the module docstring);
    # a Windows host returns None here and the installer refuses loudly.
    return None
