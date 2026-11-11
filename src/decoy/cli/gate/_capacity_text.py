"""Finding text for the preflight capacity check, kept out of `preflight.py` for size."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decoy_engine import CapacityEstimate

_GIB = 1024**3


def format_gib(byte_count: int | None) -> str:
    return f"~{byte_count / _GIB:.1f} GB" if byte_count else "an unknown amount"


def insufficient_text(estimate: CapacityEstimate) -> str:
    """The INSUFFICIENT finding text for the engine code. The engine's generate message holds
    byte counts and a table name, never a generated value."""
    from decoy_engine.reasons.runtime import GENERATION_BUDGET_EXCEEDED

    # The generate floor holds whatever the values are, so no run admits that job; the
    # out-of-core estimate is conservative and full-frame recovery may still admit it.
    if estimate.code == GENERATION_BUDGET_EXCEEDED:
        return (
            f"INSUFFICIENT -- {estimate.message} Lower the table's row_count or use a host "
            "with more memory."
        )
    return (
        f"INSUFFICIENT -- needs {format_gib(estimate.needed_bytes)}, budget "
        f"{format_gib(estimate.available_bytes)}; use a larger tier or reduce the job. This "
        "estimate is conservative: a real run may still admit the job via full-frame recovery."
    )
