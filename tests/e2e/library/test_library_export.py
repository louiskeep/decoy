"""`decoy library export` (plan 4.11, 4.3a, 4.15; L4b) over the engine 0.22.0 codec.

The CLI selects records, puts their raw verified envelopes in link order, adds the refs and
writes the codec's lines through the atomic writer; stripping, link remapping and ids are the
codec's (`records.export_lines`).

Owner decision (2026-11-12): accept the codec's behavior. A default export WITHHOLDS records this
version cannot strip (an unknown kind, or a payload with fields this version does not know) and
names them in the header's `withheld_records`; `--keep-paths` exports every record byte for byte.
L4b-export-newer, -unknown and -closure are rewritten to that behavior; -import, -remap and
-scratch stand as the plan states them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from decoy_engine import records
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import open_library
from tests.e2e.library._records import run_result, sample, scan_set, table
from tests.unit.library._helpers import INVOCATION, object_path

runner = CliRunner()
CANARY = "SCRATCHCANARY9d2"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    return tmp_path / DECOY_DIR


def _export(root: Path, out: Path, *args: str) -> Any:
    result = runner.invoke(
        app, ["library", "export", "--output", str(out), *args, "--library", str(root)]
    )
    return result


def _read(out: Path) -> tuple[Any, list[Any]]:
    items = list(records.read_export(out.read_bytes().splitlines(keepends=True)))
    header, lines = items[0], items[1:]
    assert all(type(x).__name__ == "ExportedRecord" for x in lines), lines  # nothing bad
    return header, lines


def _put(root: Path, *envs: Any) -> list[str]:
    library = open_library(root)
    return [library.put(e).id for e in envs]


def _hand_place(root: Path, raw: dict) -> str:
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    open_library(root)  # index it, as a `git pull` then the next command would
    return str(raw["id"])


def _newer(root: Path, links: tuple[str, ...] = ()) -> str:
    """A run-result as a newer CLI writes it: same tag, one payload field this version lacks."""
    raw = json.loads(records.encode(run_result(15, "succeeded", [table(0, "orders", 3)])))
    raw["payload"]["written_by_a_newer_cli"] = 7
    raw["payload_digest"] = records.payload_digest(raw["payload"])
    raw["links"] = [{"rel": "baseline", "id": t} for t in links]
    return _hand_place(root, raw)


def _opaque(root: Path, links: tuple[str, ...] = ()) -> str:
    raw = json.loads(records.encode(sample(80, 16)))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["links"] = [{"rel": "scan", "id": t} for t in links]
    return _hand_place(root, raw)


def _original(line: Any) -> str:
    return line.source_id or line.record.id


# -- L4b-export-import (as the plan states it) -------------------------------------------------


def test_export_then_read_gives_the_same_ids_and_strips_only_path_fields(
    root: Path, tmp_path: Path
) -> None:
    """ML4-paths: keeping paths by default turns this red."""
    ids = _put(root, sample(1, 11), sample(2, 12))
    out = tmp_path / "export.jsonl"
    result = _export(root, out)
    assert result.exit_code == EXIT_OK, result.output
    header, lines = _read(out)
    assert header.record_count == 2 and header.paths_stripped is True
    assert sorted(_original(x) for x in lines) == sorted(ids)
    for line in lines:
        payload = line.record.raw["payload"]
        stored = json.loads(object_path(root, line.source_id).read_bytes())["payload"]
        assert payload["scratch_dir"] == "sample"  # the declared path field, reduced to a name
        assert {k: v for k, v in payload.items() if k != "scratch_dir"} == {
            k: v for k, v in stored.items() if k != "scratch_dir"
        }  # every other field unchanged
    kept = tmp_path / "keep.jsonl"
    assert _export(root, kept, "--keep-paths").exit_code == EXIT_OK
    header, lines = _read(kept)
    assert header.paths_stripped is False
    assert sorted(x.record.id for x in lines) == sorted(ids)
    assert all(x.source_id is None for x in lines)


def test_ref_exports_exactly_the_reachable_set(root: Path, tmp_path: Path) -> None:
    base = _put(root, sample(1, 11))[0]
    other = _put(root, sample(2, 12))[0]
    top = _put(root, run_result(13, "succeeded", [table(0, "t", 1)], links=[("baseline", base)]))[0]
    library = open_library(root)
    library.set_ref("run-result", "release", top)
    out = tmp_path / "ref.jsonl"
    result = _export(root, out, "--ref", "run-result/release", "--keep-paths")
    assert result.exit_code == EXIT_OK, result.output
    header, lines = _read(out)
    assert sorted(x.record.id for x in lines) == sorted([base, top])
    assert other not in {x.record.id for x in lines}
    assert header.refs == {"run-result/release": top} and header.external_links == 0


def test_kind_and_since_select_records(root: Path, tmp_path: Path) -> None:
    a, b = _put(root, sample(1, 11), sample(2, 14))
    _put(root, run_result(15, "succeeded", [table(0, "t", 1)]))
    out = tmp_path / "x.jsonl"
    assert (
        _export(
            root, out, "--kind", "sample-run", "--since", "2026-11-13", "--keep-paths"
        ).exit_code
        == EXIT_OK
    )
    assert [x.record.id for x in _read(out)[1]] == [b]
    assert _export(root, out, "--since", "yesterday").exit_code == EXIT_USAGE
    assert a  # non-vacuous: an older sample existed and was filtered out


# -- L4b-export-remap (as the plan states it) --------------------------------------------------


def test_links_and_refs_point_at_the_new_ids_after_stripping(root: Path, tmp_path: Path) -> None:
    scan = scan_set(tmp_path / "scan", "people", "id,email,name", 11)
    scan_id = _put(root, scan)[0]
    run_id = _put(
        root, run_result(12, "succeeded", [table(0, "people", 5)], links=[("baseline", scan_id)])
    )[0]
    open_library(root).set_ref("scan-set", "baseline", scan_id)
    out = tmp_path / "remap.jsonl"
    assert _export(root, out).exit_code == EXIT_OK
    header, lines = _read(out)
    by_source = {x.source_id: x.record for x in lines}
    assert set(by_source) == {scan_id, run_id}  # both changed (paths stripped), so both remapped
    new_scan = by_source[scan_id].id
    assert new_scan != scan_id
    assert [link["id"] for link in by_source[run_id].raw["links"]] == [new_scan]
    assert header.refs == {"scan-set/baseline": new_scan}
    assert header.external_links == 0


# -- L4b-export-scratch (as the plan states it) ------------------------------------------------


@pytest.mark.parametrize(
    "flags", [(), ("--keep-paths",), ("--include-logs",), ("--keep-paths", "--include-logs")]
)
def test_no_option_exports_scratch(root: Path, tmp_path: Path, flags: tuple[str, ...]) -> None:
    """ML4-scratch: reading anything under scratch/ into the export turns this red."""
    from datetime import timedelta

    _put(root, sample(1, 11))
    library = open_library(root)
    with library.scratch("sample", INVOCATION, ttl=timedelta(hours=1)) as alloc:
        alloc.write("orders.csv", f"id\n{CANARY}\n".encode())
    assert CANARY in (alloc.path / "orders.csv").read_text()  # non-vacuous: the rows are there
    out = tmp_path / "e.jsonl"
    result = _export(root, out, *flags)
    assert result.exit_code == EXIT_OK, result.output
    assert CANARY not in out.read_text(encoding="utf-8")
    if "--include-logs" in flags:
        assert "no job logs" in result.output  # logs arrive with L5b; none exported


# -- L4b-export-newer (rewritten to the engine codec) ------------------------------------------


def test_a_newer_record_is_withheld_by_default_and_kept_byte_for_byte_with_keep_paths(
    root: Path, tmp_path: Path
) -> None:
    """ML4-export-view: exporting from the typed view drops the newer field; red."""
    _put(root, sample(1, 11))
    newer = _newer(root)
    stored = object_path(root, newer).read_bytes()
    out = tmp_path / "d.jsonl"
    result = _export(root, out)
    assert result.exit_code == EXIT_OK, result.output
    header, lines = _read(out)
    assert header.withheld_records == (newer,)
    assert newer not in {_original(x) for x in lines}
    assert (
        "1 record" in result.stderr and newer in result.stderr and "--keep-paths" in result.stderr
    )
    assert object_path(root, newer).read_bytes() == stored  # the library is untouched
    kept = tmp_path / "k.jsonl"
    assert _export(root, kept, "--keep-paths").exit_code == EXIT_OK
    header, lines = _read(kept)
    line = next(x for x in lines if x.record.id == newer)
    assert line.source_id is None and records.encode(line.record.raw) == records.canonical_bytes(
        json.loads(stored)
    )
    assert line.record.raw["payload"]["written_by_a_newer_cli"] == 7
    assert header.withheld_records == ()


# -- L4b-export-unknown (rewritten to the engine codec) ----------------------------------------


def test_an_opaque_record_is_withheld_by_default_and_kept_with_keep_paths(
    root: Path, tmp_path: Path
) -> None:
    """ML4-skip-unknown (rewritten): leaving unknown kinds out of a --keep-paths export, or out of
    the withheld list, turns this red."""
    base = _put(root, sample(1, 11))[0]
    future = _opaque(root, links=(base,))
    stored = object_path(root, future).read_bytes()
    out = tmp_path / "d.jsonl"
    result = _export(root, out)
    assert result.exit_code == EXIT_OK, result.output
    header, _lines = _read(out)
    assert header.withheld_records == (future,) and future in result.stderr
    kept = tmp_path / "k.jsonl"
    assert _export(root, kept, "--keep-paths").exit_code == EXIT_OK
    header, lines = _read(kept)
    line = next(x for x in lines if x.record.id == future)
    assert type(line.record).__name__ == "OpaqueRecord"
    assert line.source_id is None and records.encode(line.record.raw) == records.canonical_bytes(
        json.loads(stored)
    )


# -- L4b-export-closure (rewritten to the engine codec) ----------------------------------------


def test_closure_every_link_resolves_or_is_counted(root: Path, tmp_path: Path) -> None:
    scan = scan_set(tmp_path / "scan", "people", "id,email,name", 11)
    scan_id = _put(root, scan)[0]
    future = _opaque(root, links=(scan_id,))
    newer = _newer(root, links=(scan_id,))
    for flags, withheld in (((), {future, newer}), (("--keep-paths",), set())):
        out = tmp_path / f"c{len(flags)}.jsonl"
        assert _export(root, out, *flags).exit_code == EXIT_OK
        header, lines = _read(out)
        exported = {x.record.id for x in lines}
        outside = sum(
            1 for x in lines for link in x.record.raw["links"] if link["id"] not in exported
        )
        assert header.external_links == outside == 0
        assert set(header.withheld_records) == withheld
        assert {_original(x) for x in lines} == {scan_id, future, newer} - withheld
        for x in lines:  # every envelope verifies (read_export decoded it) and source_id is outside
            assert "source_id" not in x.record.raw
            assert x.record.id == records.record_id(x.record.raw)


def test_export_refuses_an_unknown_ref(root: Path, tmp_path: Path) -> None:
    _put(root, sample(1, 11))
    out = tmp_path / "x.jsonl"
    result = _export(root, out, "--ref", "scan-set/missing")
    assert result.exit_code == EXIT_USAGE and not out.exists()
