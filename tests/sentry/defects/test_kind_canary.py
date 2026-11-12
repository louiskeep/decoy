"""G-KIND-CANARY: every writable record kind has a canary end-to-end fixture, or one pending row.

Records are value-free by construction (plan 1, guarantee 3), and the proof is a canary run per
kind: every cell holds a canary string, the real producer command runs, and the canary must
appear in no file under `.decoy/library/` or `.decoy/logs/` (plan 3, choke points). The kind list
comes from `decoy_engine.records.registered_kinds()`, so a kind the engine adds cannot skip it. A
kind is writable when it has a write model; reserved kinds are not.

A fixture is `tests/e2e/library/test_canary_<fixture id>.py` (the kind's `canary_fixture`, `-` as
`_`). Kinds whose producer is not built yet sit in PENDING_ALLOWLIST with the slice that adds the
fixture. The list only shrinks (tests/sentry/baselines/kind-canary-pending.json): L2 removes
`scan-set`, L3a `evidence` and `run-result`, L3b `sample-run`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decoy_engine import records

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "e2e" / "library"
BASELINE = ROOT / "tests" / "sentry" / "baselines" / "kind-canary-pending.json"
_PREFIX = "test_canary_"


@dataclass(frozen=True)
class PendingKind:
    kind: str
    reason: str


PENDING_ALLOWLIST: tuple[PendingKind, ...] = (
    PendingKind("scan-set", "L2-cli writes scan records and adds the scan-set canary fixture."),
    PendingKind("evidence", "L3a-cli writes evidence records and adds the evidence canary."),
    PendingKind("run-result", "L3a-cli writes run-result records and adds the canary fixture."),
    PendingKind("sample-run", "L3b-cli writes sample-run records and adds the canary fixture."),
)


def fixture_ids(folder: Path = FIXTURES) -> set[str]:
    return {
        p.stem[len(_PREFIX) :].replace("_", "-")
        for p in folder.glob(f"{_PREFIX}*.py")
        if p.is_file()
    }


def findings(specs: Any, pending: tuple[PendingKind, ...], fixtures: set[str]) -> list[str]:
    writable = {s.kind: s.canary_fixture for s in specs if s.write_model is not None}
    waiting = {p.kind for p in pending}
    out: list[str] = []
    for kind, fixture in sorted(writable.items()):
        has = fixture is not None and fixture in fixtures
        if fixture is None:
            out.append(f"{kind}: writable kind with no canary_fixture id in the engine registry")
        elif not has and kind not in waiting:
            out.append(f"{kind}: no canary fixture {_PREFIX}{fixture.replace('-', '_')}.py "
                       "and no pending row")  # fmt: skip
        elif has and kind in waiting:
            out.append(f"{kind}: canary fixture exists; remove its pending row")
    out += [
        f"{kind}: pending row for a kind that is not writable (remove it)"
        for kind in sorted(waiting - set(writable))
    ]
    return out


def test_every_writable_kind_has_a_canary_or_a_pending_row() -> None:
    specs = records.registered_kinds()
    assert any(s.write_model is not None for s in specs)  # non-vacuous: kinds were read
    assert findings(specs, PENDING_ALLOWLIST, fixture_ids()) == []


def test_pending_rows_are_unique_and_explained() -> None:
    kinds = [p.kind for p in PENDING_ALLOWLIST]
    assert len(set(kinds)) == len(kinds) == 4
    assert all(len(p.reason.strip()) >= 15 for p in PENDING_ALLOWLIST)


def test_baseline_json_records_the_same_rows() -> None:
    entries = json.loads(BASELINE.read_text(encoding="utf-8"))["entries"]
    assert {k: v["reason"] for k, v in entries.items()} == {
        p.kind: p.reason for p in PENDING_ALLOWLIST
    }


@dataclass(frozen=True)
class _Spec:
    kind: str
    write_model: object
    canary_fixture: str | None


def test_seeded_kind_without_a_fixture_is_red() -> None:
    """M-KIND-NOFIX: a writable kind registered with no fixture and no pending row."""
    specs = (*records.registered_kinds(), _Spec("audit-thing", object(), "audit-thing"))
    assert findings(specs, PENDING_ALLOWLIST, fixture_ids()) == [
        "audit-thing: no canary fixture test_canary_audit_thing.py and no pending row"
    ]


def test_seeded_fixture_clears_its_kind_and_flags_a_leftover_row(tmp_path: Path) -> None:
    (tmp_path / "test_canary_scan_set.py").write_text("", encoding="utf-8")
    found = findings(records.registered_kinds(), PENDING_ALLOWLIST, fixture_ids(tmp_path))
    assert found == ["scan-set: canary fixture exists; remove its pending row"]
    rows = tuple(p for p in PENDING_ALLOWLIST if p.kind != "scan-set")
    assert findings(records.registered_kinds(), rows, fixture_ids(tmp_path)) == []


def test_seeded_reserved_kind_needs_nothing_and_a_stale_row_is_red() -> None:
    specs = (_Spec("later", None, None),)
    assert findings(specs, (), set()) == []
    assert findings(specs, (PendingKind("later", "r" * 20),), set()) == [
        "later: pending row for a kind that is not writable (remove it)"
    ]
    nofix = (_Spec("odd", object(), None),)
    assert findings(nofix, (), set()) == [
        "odd: writable kind with no canary_fixture id in the engine registry"
    ]
