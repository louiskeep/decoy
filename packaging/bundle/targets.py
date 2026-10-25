"""The approved per-platform bundle targets.

Mirrors `decoy-engine/docs/native/supported-matrix.md` section 2 (the approved
companion wheel starter pack). The bundle set is one bundle per target; a target
with no companion wheel has no bundle, and the installer fails loudly on a host
that maps to an unsupported target rather than laying down a partial or slow
install.

One place per fact: this is the CLI-side copy of the engine's authoritative
target list. If the engine adds a target (the open macOS-x86_64 decision, for
one), it is added there first and reflected here, and `supported-matrix.md` stays
the source of truth. The ABI tag the companion must report lives in
`packaging/pin.env` (`DECOY_LAUNCH_NATIVE_ABI`), not here, so the ABI pin has one
owner.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    """One approved build target.

    `key` is the canonical bundle target string used in artifact names, the
    version document's `artifacts` map, and the installer's detected-target
    lookup. `os_name` / `arch` are what an installer's `uname`-style probe
    resolves to; `python_build_triple` is the python-build-standalone platform
    tag the embedded interpreter is fetched for.
    """

    key: str
    os_name: str
    arch: str
    python_build_triple: str


# The four approved targets. No macOS x86_64 (Intel): that is an open lane
# decision (unsupported / Rosetta on arm64 / add the target), recorded in the
# distribution spec, so the installer treats an Intel Mac as an unsupported
# target and fails loudly, which is the honest behavior until the decision lands.
TARGETS: tuple[Target, ...] = (
    Target(
        key="linux-x86_64",
        os_name="linux",
        arch="x86_64",
        python_build_triple="x86_64-unknown-linux-gnu",
    ),
    Target(
        key="linux-aarch64",
        os_name="linux",
        arch="aarch64",
        python_build_triple="aarch64-unknown-linux-gnu",
    ),
    Target(
        key="windows-x86_64",
        os_name="windows",
        arch="x86_64",
        python_build_triple="x86_64-pc-windows-msvc",
    ),
    Target(
        key="macos-arm64",
        os_name="macos",
        arch="arm64",
        python_build_triple="aarch64-apple-darwin",
    ),
)

TARGETS_BY_KEY = {t.key: t for t in TARGETS}


def target_for_key(key: str) -> Target:
    """Resolve a target by its canonical key, or raise a clear error.

    Raises `KeyError` with the supported keys listed, so a caller (the assembler
    or a test) that is handed a bad or unsupported target key fails loudly rather
    than silently producing a partial bundle set."""
    try:
        return TARGETS_BY_KEY[key]
    except KeyError:
        supported = ", ".join(sorted(TARGETS_BY_KEY))
        raise KeyError(f"unknown bundle target {key!r}; supported targets: {supported}") from None
