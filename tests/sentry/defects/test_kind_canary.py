"""G-KIND-CANARY: every writable record kind has a canary end-to-end fixture, or one pending row.

Records are value-free by construction (plan 1, guarantee 3), and the proof is a canary run per
kind: every cell holds a canary string, the real producer command runs, and the canary must
appear in no file under `.decoy/library/` or `.decoy/logs/` (plan 3, choke points). The kind list
comes from `decoy_engine.records.registered_kinds()`, so a kind the engine adds cannot skip it. A
kind is writable when it has a write model; reserved kinds are not.

A kind is covered by a runnable case in `tests/e2e/library/_canary.py` (`CASES`), which
`tests/e2e/library/test_canary.py` runs with both its positive and negative checks; a file name
covers nothing. Kinds whose producer is not built yet sit in PENDING_ALLOWLIST with the slice that
adds the case. The list only shrinks (tests/sentry/baselines/kind-canary-pending.json): L2 removes
`scan-set`, L3a `evidence` and `run-result`, L3b `sample-run`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decoy_engine import records
from tests.e2e.library._canary import CASES, CanaryCase
from tests.sentry._ratchet import load_allowlist

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PendingKind:
    kind: str
    reason: str


PENDING_ALLOWLIST: tuple[PendingKind, ...] = tuple(
    PendingKind(kind, e["reason"]) for kind, e in load_allowlist("kind-canary-pending").items()
)


def findings(
    specs: Any, pending: tuple[PendingKind, ...], cases: Mapping[str, CanaryCase]
) -> list[str]:
    writable = {s.kind: s.canary_fixture for s in specs if s.write_model is not None}
    waiting = {p.kind for p in pending}
    out: list[str] = []
    for kind, fixture in sorted(writable.items()):
        case = cases.get(kind)
        has = case is not None and case.kind == kind and callable(case.produce)
        if fixture is None:
            out.append(f"{kind}: writable kind with no canary_fixture id in the engine registry")
        elif not has and kind not in waiting:
            out.append(f"{kind}: no runnable canary case and no pending row")
        elif has and kind in waiting:
            out.append(f"{kind}: canary case exists; remove its pending row")
    out += [
        f"{kind}: pending row for a kind that is not writable (remove it)"
        for kind in sorted(waiting - set(writable))
    ]
    return out


def test_every_writable_kind_has_a_canary_or_a_pending_row() -> None:
    specs = records.registered_kinds()
    assert any(s.write_model is not None for s in specs)  # non-vacuous: kinds were read
    assert findings(specs, PENDING_ALLOWLIST, CASES) == []


def test_pending_rows_are_unique_and_explained() -> None:
    kinds = [p.kind for p in PENDING_ALLOWLIST]
    assert len(set(kinds)) == len(kinds) == 2
    assert all(len(p.reason.strip()) >= 15 for p in PENDING_ALLOWLIST)


@dataclass(frozen=True)
class _Spec:
    kind: str
    write_model: object
    canary_fixture: str | None


def test_seeded_kind_without_a_case_is_red() -> None:
    """M-KIND-NOFIX: a writable kind registered with no canary case and no pending row."""
    specs = (*records.registered_kinds(), _Spec("audit-thing", object(), "audit-thing"))
    assert findings(specs, PENDING_ALLOWLIST, CASES) == [
        "audit-thing: no runnable canary case and no pending row"
    ]


def _runnable(kind: str) -> CanaryCase:
    return CanaryCase(kind, produce=lambda _project: None)


def test_an_empty_placeholder_fixture_file_covers_nothing(tmp_path: Path) -> None:
    """Review round 1 on #210, DESIGN 10: coverage comes from the case registry, never a file."""
    (tmp_path / "test_canary_scan_set.py").write_text("", encoding="utf-8")
    rows = tuple(p for p in PENDING_ALLOWLIST if p.kind != "scan-set")
    found = findings(records.registered_kinds(), rows, CASES)
    assert "scan-set: no runnable canary case and no pending row" in found


def test_seeded_case_clears_its_kind_and_flags_a_leftover_row() -> None:
    cases = {**CASES, "scan-set": _runnable("scan-set")}
    found = findings(records.registered_kinds(), PENDING_ALLOWLIST, cases)
    assert found == ["scan-set: canary case exists; remove its pending row"]
    rows = tuple(p for p in PENDING_ALLOWLIST if p.kind != "scan-set")
    assert findings(records.registered_kinds(), rows, cases) == []


def test_seeded_reserved_kind_needs_nothing_and_a_stale_row_is_red() -> None:
    specs = (_Spec("later", None, None),)
    assert findings(specs, (), {}) == []
    assert findings(specs, (PendingKind("later", "r" * 20),), {}) == [
        "later: pending row for a kind that is not writable (remove it)"
    ]
    nofix = (_Spec("odd", object(), None),)
    assert findings(nofix, (), {}) == [
        "odd: writable kind with no canary_fixture id in the engine registry"
    ]
