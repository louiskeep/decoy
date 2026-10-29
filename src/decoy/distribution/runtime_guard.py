"""Run-time native-companion enforcement for the MANAGED runtime.

The install-time self-check (`decoy.distribution.selfcheck`) proves the companion was
present when the bundle was laid down; it cannot see a companion deleted, or an engine/
companion pair swapped to an ABI-mismatched one, AFTER install. The launch rule is a loud
refusal at install AND at run, so every managed `decoy` invocation re-runs the same
probe before doing work.

Scope is deliberate:
- Only a bundled-runtime interpreter (`layout.managed_home()`) is guarded. A pip/dev
  install keeps the engine's own contract (the companion is an optional accelerator with a
  correct slower fallback), and a bare ``import decoy`` / library use is never guarded.
- ``upgrade`` is exempt: it is the repair path for exactly this failure, so refusing it
  would strand a broken runtime. ``--version`` and ``--help`` exit before the root callback
  and so need no exemption.
"""

from __future__ import annotations

from decoy.distribution import layout, selfcheck

# Subcommands that must stay runnable on a companion-broken managed runtime.
EXEMPT_COMMANDS = frozenset({"upgrade"})


def refusal_message(result: selfcheck.SelfCheckResult) -> str | None:
    """The loud refusal text for an unusable companion, or None when it is healthy."""
    if result.ok:
        return None
    return (
        f"native companion check FAILED at run time -- {result.detail}. This managed "
        "install was changed after it was installed (companion removed or ABI-mismatched). "
        "Decoy runs native-on by default and refuses rather than silently falling back to "
        "the slow path. Repair it with: decoy upgrade --force"
    )


def enforce(invoked_subcommand: str | None) -> str | None:
    """Return the refusal message if this invocation must be refused, else None."""
    if layout.managed_home() is None or invoked_subcommand in EXEMPT_COMMANDS:
        return None
    return refusal_message(selfcheck.check_native_present())
