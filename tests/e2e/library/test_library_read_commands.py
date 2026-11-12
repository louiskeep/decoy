"""`decoy library list`, `show`, `diff` and `ref` (plan 4.3a, 4.5, 4.15; L4a).

Records are built directly with `records.build` (run-result included) and stored with
`Library.put`; scan-set payloads come from a real `decoy scan --output` on tiny CSVs.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from decoy_engine import records
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import evidence as evidence_module
from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.io import DECOY_DIR
from decoy.cli.library import _index, _refs, open_library
from tests.unit.library._helpers import INVOCATION, PRODUCER, envelope, object_path

runner = CliRunner()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECOY_LIBRARY", raising=False)
    return tmp_path / DECOY_DIR


def _cli(root: Path, *args: str) -> Any:
    return runner.invoke(app, ["library", *args, "--library", str(root)])


def _at(day: int) -> datetime:
    return datetime(2026, 11, day, tzinfo=timezone.utc)


def _build(kind: str, payload: dict, day: int, **labels: Any) -> records.RecordEnvelope:
    return records.build(
        kind, payload, producer=PRODUCER, invocation_id=INVOCATION, created_at=_at(day),
        labels=labels or None,
    )  # fmt: skip


def _sample(n: int, day: int, **labels: Any) -> records.RecordEnvelope:
    payload = json.loads(records.encode(envelope(n)))["payload"]
    return _build("sample-run", payload, day, **labels)


def _table(i: int, name: str, rows: int, state: str = "delivered") -> dict:
    return {
        "index": i, "name": name, "kind": "mask", "outcome": "succeeded", "rows_out": rows,
        "rows_source": "outputs", "row_errors": 0, "elapsed_s": 0.5, "reason": None,
        "delivery": {"state": state, "format": "csv", "output": f"out/{name}.csv",
                     "reason": None, "dropped_because": None},
    }  # fmt: skip


def _run_result(day: int, status: str, tables: list[dict], chunked: bool = False) -> Any:
    payload = {
        "invocation_id": INVOCATION, "status": status, "exit_code": 0, "pipeline_kind": "mask",
        "producer": {"cli_version": "0.1.0", "engine_version": "0.22.0",
                     "registry_version": "1.22.0", "event_schema": 1},
        "config": {"name": "claims", "file_sha256": "sha256:" + "b" * 64, "semantic_hash": "a" * 64},
        "route": {"execution_mode": "full_frame", "route_reason": None, "chunked": chunked,
                  "native": None},
        "delivery": {"mode": "strict", "outcome": "delivered", "vault": "not_used"},
        "tables": tables, "checks": [], "warnings": [], "failure": None,
        "timings": {"started_at": "2026-11-11T00:00:00.000000Z",
                    "finished_at": "2026-11-11T00:00:01.000000Z", "elapsed_s": 1.0, "phases": []},
        "links": {"log": None, "evidence": None, "baseline": None},
    }  # fmt: skip
    return _build("run-result", payload, day)


def _evidence(tmp_path: Path, day: int, rows: int) -> Any:
    src = tmp_path / "in.csv"
    src.write_text("id\n1\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    out.write_text(f"id\n{rows}\n", encoding="utf-8")
    config = {
        "version": 2,
        "sources": {"t": {"type": "csv", "path": str(src), "has_header": True,
                          "column_names": ["id"]}},
        "tables": [{"name": "t", "columns": []}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(out)}},
    }  # fmt: skip
    pipeline = tmp_path / "p.yaml"
    pipeline.write_text(yaml.dump(config), encoding="utf-8")
    manifest = evidence_module.build_manifest(
        pipeline_path=pipeline, config_dict=config, run_result={"row_counts": {"t": rows}},
        cli_version="0.1.0", engine_version="0.22.0",
    )  # fmt: skip
    return _build("evidence", manifest, day)


def _scan_set(tmp_path: Path, name: str, header: str, day: int) -> Any:
    tmp_path.mkdir(exist_ok=True)
    csv = tmp_path / f"{name}.csv"
    csv.write_text(header + "\n" + "\n".join(f"{i},a{i}@b.com,Ann{i}" for i in range(5)) + "\n")
    out = tmp_path / f"{name}.scan.json"
    result = runner.invoke(app, ["scan", str(csv), "--has-header", "--output", str(out)])
    assert result.exit_code == EXIT_OK, result.output
    return _build("scan-set", json.loads(out.read_text(encoding="utf-8")), day)


def _opaque(root: Path, day: int = 20) -> str:
    raw = json.loads(records.encode(_sample(9, day)))
    raw["kind"], raw["payload_schema"] = "future-thing", "future-thing/v1"
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    return str(raw["id"])


def _put(root: Path, *envs: Any) -> list[str]:
    library = open_library(root)
    return [library.put(e).id for e in envs]


# -- L4-list -----------------------------------------------------------------------------------


def test_list_filters_by_kind_pipeline_table_and_time(root: Path) -> None:
    """ML4-filter: dropping a filter lists rows it should not; red."""
    a = _sample(1, 11, pipeline="pipes/a.yaml", tables=["orders"])
    b = _sample(2, 12, pipeline="pipes/b.yaml", tables=["users"])
    c = _run_result(13, "succeeded", [_table(0, "orders", 3)])
    ids = _put(root, a, b, c)

    def listed(*args: str) -> list[str]:
        result = _cli(root, "list", "--json", *args)
        assert result.exit_code == EXIT_OK, result.output
        return [r["id"] for r in json.loads(result.stdout)["records"]]

    assert listed() == ids  # sorted by (created_at, id)
    assert listed("--kind", "sample-run") == [a.id, b.id]
    assert listed("--pipeline", "pipes/b.yaml") == [b.id]
    assert listed("--table", "orders") == [a.id]
    assert listed("--since", "2026-11-12") == [b.id, c.id]
    assert listed("--kind", "sample-run", "--since", "2026-11-12T00:00:00Z") == [b.id]


def test_list_json_is_stable_and_sorted(root: Path) -> None:
    _put(root, _sample(2, 12), _sample(1, 11))
    first = _cli(root, "list", "--json")
    second = _cli(root, "list", "--json")
    assert first.exit_code == EXIT_OK and first.stdout == second.stdout
    rows = json.loads(first.stdout)["records"]
    assert [r["created_at"] for r in rows] == sorted(r["created_at"] for r in rows)
    assert set(rows[0]) >= {"id", "kind", "created_at", "pipeline", "tables", "status", "known"}


def test_list_shows_an_unknown_kind_and_filters_on_its_name(root: Path) -> None:
    known = _put(root, _sample(1, 11))[0]
    future = _opaque(root)
    result = _cli(root, "list")
    assert result.exit_code == EXIT_OK, result.output
    assert "unknown kind future-thing, needs a newer Decoy" in result.output
    assert known[:15] in result.output
    rows = json.loads(_cli(root, "list", "--json", "--kind", "future-thing").stdout)["records"]
    assert [(r["id"], r["known"]) for r in rows] == [(future, False)]


def test_list_refuses_a_bad_since(root: Path) -> None:
    _put(root, _sample(1, 11))
    result = _cli(root, "list", "--since", "last tuesday")
    assert result.exit_code == EXIT_USAGE


# -- L4-show -----------------------------------------------------------------------------------


def test_show_resolves_a_unique_prefix_and_prints_the_envelope(root: Path) -> None:
    rid = _put(root, _sample(1, 11), _sample(2, 12))[0]
    digest = rid.removeprefix("sha256:")
    for token in (rid, digest[:8], f"sha256:{digest[:12]}"):
        result = _cli(root, "show", token, "--json")
        assert result.exit_code == EXIT_OK, result.output
        doc = json.loads(result.stdout)
        assert doc["record"]["id"] == rid and doc["status"] == "known"
        assert doc["record"]["payload"]["sample_size"] == 2  # envelope(1) holds n + 1
    human = _cli(root, "show", digest[:8])
    assert rid in human.output and "sample-run" in human.output


def test_show_refuses_an_ambiguous_prefix(root: Path) -> None:
    """ML4-first-match: taking the first of several matches turns this red."""
    rid = _put(root, _sample(1, 11))[0]
    stored = object_path(root, rid)
    twin = stored.with_name(stored.name[:10] + "0" * 52 + ".json")  # shares a 12-hex prefix
    twin.write_bytes(b"{}")
    prefix = rid.removeprefix("sha256:")[:12]
    assert len(open_library(root).resolve(prefix)) == 2  # non-vacuous: two names match
    result = _cli(root, "show", prefix)
    assert result.exit_code == EXIT_USAGE
    assert "ambiguous" in result.output


def test_show_refuses_a_short_or_unknown_id(root: Path) -> None:
    _put(root, _sample(1, 11))
    assert _cli(root, "show", "abc").exit_code == EXIT_USAGE
    assert _cli(root, "show", "0" * 12).exit_code == EXIT_USAGE


def test_show_an_opaque_or_newer_record_prints_the_envelope_only(root: Path) -> None:
    _put(root, _sample(1, 11))
    future = _opaque(root)
    result = _cli(root, "show", future)
    assert result.exit_code == EXIT_OK, result.output
    assert "future-thing" in result.output and "cannot be read by this version" in result.output
    doc = json.loads(_cli(root, "show", future, "--json").stdout)
    assert doc["status"] == "opaque" and "payload" not in doc["record"]
    raw = json.loads(records.encode(_sample(3, 14)))
    raw["payload_schema"] = "sample-run/v9"
    raw["id"] = records.record_id(raw)
    target = object_path(root, raw["id"])
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(records.canonical_bytes(raw))
    newer = json.loads(_cli(root, "show", raw["id"], "--json").stdout)
    assert newer["status"] == "needs_newer" and newer["payload_schema"] == "sample-run/v9"


# -- L4-ref ------------------------------------------------------------------------------------


def test_ref_sets_under_the_lock_and_prints(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ML4-ref-nolock: writing the ref file without the library lock turns this red. The spy
    records whether the lock is held at the moment the ref file is written (opening the
    library also takes the lock, so a bare call count would not tell)."""
    rid = _put(root, _sample(1, 11))[0]
    held: list[bool] = []
    writes: list[bool] = []
    real_locked, real_write = _index.locked, _refs.replace_file

    @contextlib.contextmanager
    def locked(*args: Any, **kwargs: Any) -> Iterator[Any]:
        with real_locked(*args, **kwargs) as conn:
            held.append(True)
            try:
                yield conn
            finally:
                held.pop()

    def write(*args: Any, **kwargs: Any) -> None:
        writes.append(bool(held))
        real_write(*args, **kwargs)

    monkeypatch.setattr(_index, "locked", locked)
    monkeypatch.setattr(_refs, "replace_file", write)
    result = _cli(root, "ref", "sample-run/main", rid.removeprefix("sha256:")[:10])
    assert result.exit_code == EXIT_OK, result.output
    assert writes == [True]  # one ref write, made while the library lock was held
    shown = _cli(root, "ref", "sample-run/main")
    assert shown.exit_code == EXIT_OK and rid in shown.output
    scoped = _cli(root, "ref", "sample-run/claims/baseline", rid)
    assert scoped.exit_code == EXIT_OK
    assert open_library(root).read_ref("sample-run", "claims/baseline") == rid


@pytest.mark.parametrize(
    "name", ["Sample-run/x", "sample-run", "sample-run/a/b/c", "nope/x", "sample-run/latest"]
)
def test_ref_with_a_bad_name_is_a_usage_error(root: Path, name: str) -> None:
    rid = _put(root, _sample(1, 11))[0]
    result = _cli(root, "ref", name, rid)
    assert result.exit_code == EXIT_USAGE, result.output
    assert not (root / "library" / "refs").exists()


def test_ref_unset_is_a_usage_error_and_degraded_set_refuses(root: Path) -> None:
    rid = _put(root, _sample(1, 11))[0]
    assert _cli(root, "ref", "sample-run/main").exit_code == EXIT_USAGE
    (root / "library" / "index.sqlite").unlink()
    (root / "library" / "index.sqlite").mkdir()
    result = _cli(root, "ref", "sample-run/main", rid)
    assert result.exit_code == EXIT_RUNTIME
    assert "library_lock_unavailable" in result.output
    assert not (root / "library" / "refs").exists()


# -- L4-diff -----------------------------------------------------------------------------------


def _diff(root: Path, a: str, b: str) -> dict:
    result = _cli(root, "diff", a, b, "--json")
    assert result.exit_code == EXIT_OK, result.output
    return json.loads(result.stdout)


def test_diff_run_results_by_status_route_rows_and_delivery(root: Path) -> None:
    """ML4-generic: a structural diff for every kind loses these fields; red."""
    old = _run_result(11, "succeeded", [_table(0, "orders", 10), _table(1, "users", 5)])
    new = _run_result(
        12, "partially_delivered", [_table(0, "orders", 12), _table(1, "users", 5, "failed")],
        chunked=True,
    )  # fmt: skip
    a, b = _put(root, old, new)
    doc = _diff(root, a, b)
    assert doc["rule"] == "run-result"
    diff = doc["diff"]
    assert diff["status"] == {"old": "succeeded", "new": "partially_delivered"}
    assert diff["route"]["chunked"] == {"old": False, "new": True}
    tables = {t["table"]: t for t in diff["tables"]}
    assert tables["orders"]["rows_out"] == {"old": 10, "new": 12}
    assert tables["users"]["delivery"] == {"old": "delivered", "new": "failed"}


def test_diff_evidence_uses_the_report_diff_comparison(root: Path, tmp_path: Path) -> None:
    (tmp_path / "e1").mkdir()
    (tmp_path / "e2").mkdir()
    a, b = _put(root, _evidence(tmp_path / "e1", 11, 3), _evidence(tmp_path / "e2", 12, 4))
    doc = _diff(root, a, b)
    assert doc["rule"] == "evidence"
    assert doc["diff"]["row_count_deltas"] == [{"table": "t", "old": 3, "new": 4, "delta": 1}]
    assert doc["diff"]["any_change"] is True


def test_diff_scan_sets_uses_the_scan_diff_rules(root: Path, tmp_path: Path) -> None:
    old = _scan_set(tmp_path / "v1", "people", "id,email,name", 11)
    new = _scan_set(tmp_path / "v2", "people", "id,email,full_name", 12)
    a, b = _put(root, old, new)
    doc = _diff(root, a, b)
    assert doc["rule"] == "scan-set"
    people = doc["diff"]["tables"]["people"]
    assert [r["name"] for r in people["added_rows"]] == ["full_name"]
    assert [r["name"] for r in people["removed_rows"]] == ["name"]
    assert set(people) >= {"pii_increased", "qi_added", "risk_delta", "drift"}
    assert doc["diff"]["tables_added"] == [] and doc["diff"]["tables_removed"] == []


def test_diff_a_generic_kind_is_structural_and_value_free(root: Path) -> None:
    a, b = _put(root, _sample(1, 11), _sample(2, 12))
    doc = _diff(root, a, b)
    assert doc["rule"] == "structural"
    assert "/payload/sample_size" in doc["diff"]["changed"]
    assert "2" not in json.dumps(doc["diff"]["changed"])  # paths only, never the values


def test_diff_resolves_latest_and_latest_n(root: Path) -> None:
    ids = _put(root, _sample(1, 11), _sample(2, 12), _sample(3, 13))
    doc = _diff(root, "sample-run/latest~2", "sample-run/latest")
    assert (doc["a"], doc["b"]) == (ids[0], ids[2])
    open_library(root).set_ref("sample-run", "base", ids[1])
    doc = _diff(root, "sample-run/base", "sample-run/latest~0")
    assert (doc["a"], doc["b"]) == (ids[1], ids[2])
    assert _cli(root, "diff", "sample-run/latest~9", ids[0]).exit_code == EXIT_USAGE


def test_diff_refuses_mismatched_kinds_and_opaque_records(root: Path) -> None:
    a, b = _put(root, _sample(1, 11), _run_result(12, "succeeded", [_table(0, "t", 1)]))
    mismatched = _cli(root, "diff", a, b)
    assert mismatched.exit_code == EXIT_USAGE and "kind" in mismatched.output
    future = _opaque(root)
    assert _cli(root, "diff", a, future).exit_code == EXIT_USAGE
