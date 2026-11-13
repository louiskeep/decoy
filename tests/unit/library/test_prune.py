"""Prune (plan 4.7, 4.8, 4.3a; L4b): preview and apply, reachability, grace, opaque kinds.

`prune_preview` and `prune_apply` are separate functions; both resolve the exact targets under
the library lock, and apply deletes only those.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from decoy_engine import records
from tests.unit.library._helpers import INVOCATION, PRODUCER, envelope, object_files, object_path

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, _prune, open_library
from decoy.cli.library._errors import LIBRARY_LOCK_UNAVAILABLE

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def _local(_path: Path) -> None:
    return None


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


def _rec(n: int, day: int, links: tuple[str, ...] = (), hour: int = 0) -> records.RecordEnvelope:
    payload = json.loads(records.encode(envelope(n)))["payload"]
    return records.build(
        "sample-run", payload, producer=PRODUCER, invocation_id=INVOCATION,
        created_at=datetime(2026, 11, day, hour, tzinfo=timezone.utc),
        links=[{"rel": "sample", "id": t} for t in links],
    )  # fmt: skip


def _put(root: Path, *envs: records.RecordEnvelope) -> list[str]:
    library = open_library(root, probe=_local)
    return [library.put(e).id for e in envs]


def _opaque(root: Path, day: int, links: tuple[str, ...] = ()) -> str:
    raw = json.loads(records.encode(_rec(90, day, links)))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    return str(raw["id"])


def _rule(**kw: object) -> _prune.Rule:
    return _prune.Rule(**kw)  # type: ignore[arg-type]


# -- L4b-prune-preview -------------------------------------------------------------------------


def test_preview_lists_exact_ids_and_deletes_nothing(root: Path) -> None:
    """ML4-apply: deleting on preview turns this red."""
    ids = _put(root, _rec(0, 1), _rec(1, 2), _rec(2, 3))
    before = object_files(root)
    library = open_library(root, probe=_local)
    plan = _prune.prune_preview(library, [_rule(keep_last=1)], now=NOW)
    assert plan.delete == tuple(ids[:2])  # oldest first, exact ids
    assert object_files(root) == before and len(before) == 3


def test_apply_deletes_the_planned_ids_and_their_index_rows(root: Path) -> None:
    ids = _put(root, _rec(0, 1), _rec(1, 2), _rec(2, 3))
    library = open_library(root, probe=_local)
    report = _prune.prune_apply(library, [_rule(keep_last=1)], now=NOW)
    assert report.deleted == tuple(ids[:2]) and report.left == ()
    assert [p.name for p in object_files(root)] == [object_path(root, ids[2]).name]
    assert [r.id for r in open_library(root, probe=_local).rows()] == [ids[2]]


# -- L4b-prune-reach ---------------------------------------------------------------------------


def test_records_reachable_from_a_ref_or_a_kept_record_survive(root: Path) -> None:
    """ML4-noreach: ignoring refs and links deletes protected records; red."""
    referenced = _put(root, _rec(0, 1))[0]
    linked = _put(root, _rec(1, 2))[0]
    plain = _put(root, _rec(2, 3))[0]
    newest = _put(root, _rec(3, 4, links=(linked,)))[0]
    library = open_library(root, probe=_local)
    library.set_ref("sample-run", "main", referenced)
    plan = _prune.prune_preview(library, [_rule(keep_last=1)], now=NOW)
    assert plan.delete == (plain,)
    assert set(plan.protected) == {referenced, linked}  # non-vacuous: both were candidates
    _prune.prune_apply(library, [_rule(keep_last=1)], now=NOW)
    left = {p.name for p in object_files(root)}
    assert left == {object_path(root, i).name for i in (referenced, linked, newest)}


def test_a_chain_of_links_is_protected_transitively(root: Path) -> None:
    a = _put(root, _rec(0, 1))[0]
    b = _put(root, _rec(1, 2, links=(a,)))[0]
    c = _put(root, _rec(2, 3, links=(b,)))[0]
    library = open_library(root, probe=_local)
    library.set_ref("sample-run", "keep", c)
    assert _prune.prune_preview(library, [_rule(keep_last=0)], now=NOW).delete == ()


# -- L4b-prune-grace ---------------------------------------------------------------------------


def test_a_record_younger_than_an_hour_survives(root: Path) -> None:
    """ML4-nograce: deleting young records turns this red."""
    old = _put(root, _rec(0, 1))[0]
    young = _put(root, _rec(1, 19, hour=23))[0]
    library = open_library(root, probe=_local)
    now = datetime(2026, 11, 19, 23, 30, tzinfo=timezone.utc)  # the young one is 30 minutes old
    plan = _prune.prune_preview(library, [_rule(keep_last=0)], now=now)
    assert plan.delete == (old,) and young in plan.young


# -- older-than and kind -----------------------------------------------------------------------


def test_older_than_and_kind_filters(root: Path) -> None:
    ids = _put(root, _rec(0, 1), _rec(1, 10), _rec(2, 18))
    library = open_library(root, probe=_local)
    plan = _prune.prune_preview(library, [_rule(older_than=timedelta(days=5))], now=NOW)
    assert plan.delete == tuple(ids[:2])
    both = _prune.prune_preview(
        library, [_rule(keep_last=1, older_than=timedelta(days=15))], now=NOW
    )
    assert both.delete == (ids[0],)  # beyond keep-last and older than 15 days
    assert (
        _prune.prune_preview(library, [_rule(kind="evidence", keep_last=0)], now=NOW).delete == ()
    )


# -- L4b-prune-unknown -------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [None, "future-thing"])
def test_an_opaque_record_and_what_it_links_to_are_never_pruned(
    root: Path, kind: str | None
) -> None:
    """ML4-prune-unknown: applying kind rules to opaque records turns this red."""
    target = _put(root, _rec(0, 1))[0]
    other = _put(root, _rec(1, 2))[0]
    future = _opaque(root, 3, links=(target,))
    library = open_library(root, probe=_local)
    report = _prune.prune_apply(library, [_rule(kind=kind, keep_last=0)], now=NOW)
    names = {p.name for p in object_files(root)}
    assert object_path(root, future).name in names and object_path(root, target).name in names
    assert report.deleted == ((other,) if kind is None else ())


# -- the lock ----------------------------------------------------------------------------------


def test_a_degraded_library_refuses_prune(root: Path) -> None:
    _put(root, _rec(0, 1))
    (root / "library" / "index.sqlite").unlink()
    (root / "library" / "index.sqlite").mkdir()
    library = open_library(root, probe=_local)
    assert library.degraded == "lock_unavailable"
    for call in (_prune.prune_preview, _prune.prune_apply):
        with pytest.raises(LibraryError) as caught:
            call(library, [_rule(keep_last=0)], now=NOW)
        assert caught.value.code == LIBRARY_LOCK_UNAVAILABLE
    assert len(object_files(root)) == 1


# -- the policy --------------------------------------------------------------------------------


def test_policy_rules_come_from_library_yaml(root: Path) -> None:
    ids = _put(root, _rec(0, 1), _rec(1, 2), _rec(2, 3))
    (root / "library.yaml").write_text(
        "retention:\n  records:\n    sample-run: {keep_last: 2}\n", encoding="utf-8"
    )
    library = open_library(root, probe=_local)
    rules = _prune.policy_rules(root)
    assert rules == [_rule(kind="sample-run", keep_last=2)]
    assert _prune.prune_preview(library, rules, now=NOW).delete == (ids[0],)
    (root / "library.yaml").unlink()
    assert _prune.policy_rules(root) == []  # the default keeps all


def test_a_file_that_cannot_be_deleted_is_left_and_reported(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _put(root, _rec(0, 1), _rec(1, 2))
    library = open_library(root, probe=_local)
    import os

    real = os.unlink
    stuck = object_path(root, ids[0]).name

    def unlink(path: object, *a: object, **k: object) -> None:
        if os.fspath(path).endswith(stuck):  # type: ignore[arg-type]
            raise PermissionError(13, "held open")
        real(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "unlink", unlink)
    report = _prune.prune_apply(library, [_rule(keep_last=0)], now=NOW)
    monkeypatch.undo()
    assert report.left == (ids[0],) and report.deleted == (ids[1],)
    rows = {r.id for r in open_library(root, probe=_local).rows()}
    assert ids[0] in rows  # its index row stays until its file is gone
