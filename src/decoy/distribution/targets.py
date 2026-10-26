"""The supported per-platform target ids, and detection of the running host's target.

The authoritative target list is `decoy-engine/docs/native/supported-matrix.md`: the
four targets the native wheel matrix (`native-companion.yml`) already builds and
parity-smokes. A host that maps to no target is a LOUD refusal at install, never a
partial or slow install (the launch rule: native-on by default, no silent fallback).

Open decision for the lane (carried from the packaging spec): macOS Intel (x86_64)
is unsupported at launch -- it is not in the native wheel matrix. The alternatives
(Rosetta on the arm64 build, or adding the target) are a Cam decision; until then a
macOS x86_64 host refuses with a clear message rather than silently running an arm64
bundle it cannot execute.
"""

from __future__ import annotations

import platform

# Target id -> human label. Order is the matrix order.
SUPPORTED_TARGETS: dict[str, str] = {
    "linux-x86_64": "Linux x86_64 (glibc, manylinux_2_28+)",
    "linux-aarch64": "Linux aarch64 (glibc, manylinux_2_28+)",
    "windows-x86_64": "Windows x86_64",
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
    elif system == "windows":
        if arch == "x86_64":
            return "windows-x86_64"
    return None
