"""`fsck` (plan 4.10; L1c.2): read-only checks and the `--repair` actions, at the module level.

C1-crlf, C1-fsck-findings, C1-repair-safe and C1-layout-newer; the command-level exit codes are
in tests/e2e/library/test_library_fsck.py.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from decoy_engine import records
from tests.unit.library._helpers import envelope, job_log, object_files, object_path

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, _fsck, open_library
from decoy.cli.library._errors import LIBRARY_LAYOUT_NEWER

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


def _local(_path: Path) -> None:
    return None


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / DECOY_DIR


def _library(root: Path, count: int = 2) -> list[str]:
    library = open_library(root, probe=_local)
    return [library.put(envelope(n)).id for n in range(count)]


def _codes(report: _fsck.FsckReport, level: str = "finding") -> list[tuple[str, str]]:
    return sorted((f.code, f.target) for f in report.items if f.level == level)


def _temp(root: Path, name: str, hours: float) -> Path:
    path = root / "library" / "tmp" / name
    path.write_bytes(b"partial")
    os.chmod(path, 0o600)
    then = time.time() - hours * 3600
    os.utime(path, (then, then))
    return path


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def test_a_sound_library_is_clean(root: Path) -> None:
    ids = _library(root)
    report = _fsck.check(root, probe=_local)
    assert report.items == () and report.clean
    assert report.objects == len(ids)  # non-vacuous: every object was checked


# -- C1-crlf -----------------------------------------------------------------------------------


def test_a_crlf_rewritten_record_passes(root: Path) -> None:
    """MC1-raw-hash: hashing the file bytes reports the CRLF copy as corrupt; red."""
    ids = _library(root)
    stored = object_path(root, ids[0])
    pretty = json.dumps(json.loads(stored.read_bytes()), indent=2).replace("\n", "\r\n")
    stored.write_bytes(pretty.encode("utf-8"))
    assert b"\r\n" in stored.read_bytes()
    report = _fsck.check(root, probe=_local)
    assert report.clean and report.objects == 2


# -- C1-fsck-findings --------------------------------------------------------------------------


def test_each_problem_is_one_finding(root: Path) -> None:
    """MC1-silent: skipping the id check misses the corrupt object; red."""
    ids = _library(root, 3)
    corrupt = object_path(root, ids[0])
    corrupt.write_bytes(corrupt.read_bytes().replace(b'"sample_size":1', b'"sample_size":7'))
    refs = root / "library" / "refs" / "sample-run"
    refs.mkdir(parents=True)
    (refs / "baseline").write_text(envelope(9).id + "\n", encoding="utf-8")  # a missing target
    stale = _temp(root, ".x.decoy-1.tmp", hours=2)
    _temp(root, ".y.decoy-2.tmp", hours=0)  # younger than an hour: a running writer's, left alone
    report = _fsck.check(root, probe=_local)
    assert _codes(report) == [
        ("object_corrupt", _rel(root, corrupt)),
        ("ref_dangling", "library/refs/sample-run/baseline"),
        ("temp_stale", _rel(root, stale)),
    ]
    assert not report.clean


@posix_only
def test_open_modes_are_findings_for_logs_and_notes_for_records(root: Path) -> None:
    """MC1-record-mode: treating a 0644 record as a finding turns this red."""
    ids = _library(root)
    logs = root / "logs"
    logs.mkdir(mode=0o700)
    log = logs / "0b6c9a3e-1d2f-4c5b-8a7e-9f0e1d2c3b4a.jsonl"
    log.write_bytes(job_log())
    os.chmod(log, 0o644)
    os.chmod(object_path(root, ids[0]), 0o644)
    report = _fsck.check(root, probe=_local)
    assert _codes(report) == [("mode_open", "logs/0b6c9a3e-1d2f-4c5b-8a7e-9f0e1d2c3b4a.jsonl")]
    assert _codes(report, "note") == [("mode_open", _rel(root, object_path(root, ids[0])))]
    os.chmod(log, 0o600)
    report = _fsck.check(root, probe=_local)
    assert report.clean and _codes(report, "note")  # a 0644 record alone stays clean


def test_job_log_lines_are_checked(root: Path) -> None:
    _library(root)
    logs = root / "logs"
    logs.mkdir(mode=0o700)
    (logs / "a.jsonl").write_bytes(job_log() + b'{"kind":"pha')  # a crash mid-line
    (logs / "b.jsonl").write_bytes(job_log() + b"not json\n" + b'{"kind":"x"}\n')
    (logs / "c.jsonl").write_bytes(b"no header\n")
    for p in logs.iterdir():
        os.chmod(p, 0o600)
    report = _fsck.check(root, probe=_local)
    assert _codes(report) == [
        ("log_bad_line", "logs/b.jsonl"),
        ("log_header_invalid", "logs/c.jsonl"),
    ]
    assert _codes(report, "warning") == [("log_truncated", "logs/a.jsonl")]


def test_an_opaque_record_is_checked_by_id_only(root: Path) -> None:
    _library(root)
    raw = json.loads(records.encode(envelope(4)))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["payload"] = {"anything": ["the", "model", "is", "unknown"]}
    raw["payload_digest"] = records.payload_digest(raw["payload"])
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    open_library(root, probe=_local)  # indexed as opaque (C1-unknown-kind)
    report = _fsck.check(root, probe=_local)
    assert report.clean and report.objects == 3
    raw["payload"]["anything"] = "edited"  # the id no longer matches: still caught
    target.write_bytes(records.canonical_bytes(raw))
    assert _codes(_fsck.check(root, probe=_local)) == [("object_corrupt", _rel(root, target))]


def test_dangling_links_are_warnings(root: Path) -> None:
    ids = _library(root, 1)
    library = open_library(root, probe=_local)
    linked = envelope(5, links=[ids[0]])
    library.put(linked)
    object_path(root, ids[0]).unlink()  # a pruned, unprotected target
    report = _fsck.check(root, probe=_local)
    assert ("link_dangling", linked.id) in _codes(report, "warning")
    assert ("index_stale", "library/index.sqlite") in _codes(report)  # the row is still there


def test_an_index_that_does_not_match_the_objects_is_a_finding(root: Path) -> None:
    ids = _library(root)
    (root / "library" / "index.sqlite").unlink()
    assert _codes(_fsck.check(root, probe=_local)) == [("index_missing", "library/index.sqlite")]
    open_library(root, probe=_local)  # rebuilt
    object_path(root, ids[1]).unlink()
    assert _codes(_fsck.check(root, probe=_local)) == [("index_stale", "library/index.sqlite")]


def test_check_writes_nothing(root: Path) -> None:
    _library(root)
    (root / "library" / "index.sqlite").unlink()
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    _fsck.check(root, probe=_local)
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


# -- C1-repair-safe ----------------------------------------------------------------------------


def test_repair_quarantines_deletes_temps_drops_dangling_refs_and_keeps_valid_records(
    root: Path,
) -> None:
    """MC1-delete: deleting the corrupt object instead of quarantining it turns this red."""
    ids = _library(root, 3)
    raw = json.loads(records.encode(envelope(6)))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["id"] = records.record_id(raw)
    opaque = object_path(root, raw["id"])
    opaque.parent.mkdir(exist_ok=True)
    opaque.write_bytes(records.canonical_bytes(raw))
    corrupt = object_path(root, ids[0])
    bad_bytes = corrupt.read_bytes().replace(b'"sample_size":1', b'"sample_size":7')
    corrupt.write_bytes(bad_bytes)
    refs = root / "library" / "refs" / "sample-run"
    refs.mkdir(parents=True)
    (refs / "gone").write_text(envelope(9).id + "\n", encoding="utf-8")
    library = open_library(root, probe=_local)
    library.set_ref("sample-run", "kept", ids[1])
    stale = _temp(root, ".x.decoy-1.tmp", hours=2)

    actions, after = _fsck.repair(root, probe=_local)

    assert sorted(a.code for a in actions) == [
        "index_rebuilt", "object_quarantined", "ref_removed", "temp_deleted",
    ]  # fmt: skip
    quarantined = list((root / "library" / "quarantine").iterdir())
    assert [q.read_bytes() for q in quarantined] == [bad_bytes]  # moved, never lost
    assert not corrupt.exists() and not stale.exists() and not (refs / "gone").exists()
    assert {p.name for p in object_files(root)} == {
        object_path(root, i).name for i in (ids[1], ids[2], raw["id"])
    }  # every valid record kept, the opaque one included
    assert library.read_ref("sample-run", "kept") == ids[1]
    assert after.clean


def test_repair_never_touches_a_record_whose_payload_this_version_rejects(root: Path) -> None:
    """A record whose id holds but whose payload fails the read model is reported, not moved."""
    _library(root, 1)
    raw = json.loads(records.encode(envelope(8)))
    raw["payload"]["sample_size"] = "not-a-number"
    raw["payload_digest"] = records.payload_digest(raw["payload"])
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    open_library(root, probe=_local)  # the sync leaves it out of the index; that is not stale
    assert _codes(_fsck.check(root, probe=_local)) == [("payload_invalid", _rel(root, target))]
    actions, _after = _fsck.repair(root, probe=_local)
    assert target.is_file()
    assert "object_quarantined" not in {a.code for a in actions}


# -- C1-layout-newer ---------------------------------------------------------------------------


def test_a_newer_layout_refuses_writes_and_repair(root: Path) -> None:
    """MC1-ignore: ignoring `LAYOUT` lets the write through; red."""
    _library(root, 1)
    (root / "library" / "LAYOUT").write_text('{"layout":2}', encoding="utf-8")
    with pytest.raises(LibraryError) as caught:
        open_library(root, probe=_local).put(envelope(1))
    assert caught.value.code == LIBRARY_LAYOUT_NEWER
    assert len(object_files(root)) == 1
    report = _fsck.check(root, probe=_local)
    assert _codes(report) == [("layout_newer", "library/LAYOUT")]
    actions, after = _fsck.repair(root, probe=_local)
    assert actions == () and not after.clean
