"""Native-present self-check for the managed runtime: a loud refusal, never a slow path.

The launch rule (readiness report + ROADMAP, Cam 2026-10-22): every bundle ships the
platform-matched native companion, native is on by default, and a missing or
ABI-mismatched companion is a LOUD refusal at install and at first run -- never a
silent drop to the pandas oracle. The engine itself treats the companion as an
optional accelerator with a correct slower fallback; this check is the packaging
layer enforcing the stricter launch policy on top of that.

Reuse, not re-implementation: this calls the engine's own public probe
``decoy_engine.native_companion_status()`` (the reuse mandate in
`decoy/src/decoy/_native_gate.py`), the same probe `decoy doctor`/`decoy info` read.
It does not reach into the engine's private `_companion_status` module.

Runnable as ``python -m decoy.distribution.selfcheck`` so the install script can invoke it
through the freshly-laid-down bundled interpreter and refuse the install on a
non-zero exit. ``--json`` emits a machine-readable result for the installer to log.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SelfCheckResult:
    ok: bool
    reason: str
    detail: str


def check_native_present() -> SelfCheckResult:
    """OK only when the engine reports the companion present AND usable (ABI matched).

    Any other state -- probe absent (an engine too old to carry one), companion absent,
    or companion present-but-unusable (ABI mismatch) -- is a refusal, because a managed
    bundle is built to always contain a matched companion; its absence means a tampered
    or wrongly-assembled bundle, which must fail closed."""
    try:
        import decoy_engine
    except Exception as exc:  # noqa: BLE001 -- a broken import is itself a failed check
        return SelfCheckResult(False, "engine-import-failed", str(exc)[:200])

    probe = getattr(decoy_engine, "native_companion_status", None)
    if probe is None:
        return SelfCheckResult(
            False,
            "probe-missing",
            "installed decoy-engine predates native_companion_status(); bundle is malformed",
        )
    try:
        status = probe()
    except Exception as exc:  # noqa: BLE001
        return SelfCheckResult(False, "probe-raised", str(exc)[:200])

    if getattr(status, "ok", False) and getattr(status, "present", False):
        return SelfCheckResult(True, "present-ok", f"native companion v{status.version} healthy")

    # abi_actual/version are untrusted third-party strings; reuse the CLI's sanitizer.
    try:
        from decoy import _native_gate

        abi_actual = _native_gate.sanitize_abi(getattr(status, "abi_actual", None))
    except Exception:  # noqa: BLE001
        abi_actual = "?"
    reason = getattr(status, "reason", "unknown")
    detail = (
        f"native companion not usable (reason={reason}, "
        f"abi_expected={getattr(status, 'abi_expected', '?')}, abi_actual={abi_actual!r})"
    )
    return SelfCheckResult(False, "native-unavailable", detail)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="decoy.distribution.selfcheck")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = ap.parse_args(argv)
    result = check_native_present()
    if args.json:
        print(json.dumps(asdict(result)))
    elif result.ok:
        print(f"OK: {result.detail}")
    else:
        # LOUD: a clear, actionable refusal on stderr.
        print(
            "decoy: native-companion self-check FAILED -- "
            f"{result.detail}. This managed install is incomplete or tampered; "
            "re-run the installer to get a matched native companion. "
            "(Decoy runs native-on by default and refuses rather than silently "
            "falling back to the slow path.)",
            file=sys.stderr,
        )
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
