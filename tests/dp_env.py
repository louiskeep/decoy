"""Which DP refusal code this environment's fit must raise.

The engine's `check_fit_environment` refuses a platform that is not `CERTIFIED_PLATFORM`
first (`dp_platform_uncertified`), then an uncertified proof-stack row (`dp_stack_uncertified`).
Tests that reach the real fit gate assert the code this host earns, so they hold on Linux
x86-64 (stack arm) and on macOS (platform arm) alike. `current_platform` is read through the
module attribute, the lookup the engine makes, so one monkeypatch moves both the gate and
this helper.
"""

from __future__ import annotations

from decoy_engine.quality import dp_provenance


def current_row_is_certified() -> bool:
    platform = dp_provenance.current_platform()
    cpython = dp_provenance.current_cpython()
    fingerprint = dp_provenance.compute_lock_fingerprint(dp_provenance.installed_distribution_set())
    certified = dp_provenance._CERTIFIED_STACKS.get((platform, cpython))
    return certified is not None and fingerprint in certified


def foreign_platform() -> dp_provenance.PlatformTriple:
    """A copy of `CERTIFIED_PLATFORM` with one field changed: never the certified platform."""
    return dp_provenance.CERTIFIED_PLATFORM._replace(system="plan9")


def expected_dp_refusal_code() -> str | None:
    """The code `check_fit_environment` raises here, or None on a certified row."""
    if current_row_is_certified():
        return None
    if dp_provenance.current_platform() != dp_provenance.CERTIFIED_PLATFORM:
        return "dp_platform_uncertified"
    return "dp_stack_uncertified"


def expected_dp_refusal_code_required() -> str:
    """Like `expected_dp_refusal_code`, but a certified row fails the test loudly."""
    code = expected_dp_refusal_code()
    if code is None:
        raise AssertionError("this venv is a certified DP row; the refusal tests do not apply")
    return code
