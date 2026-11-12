"""Record builders shared by the `decoy library` e2e tests (built directly with `records.build`).

Scan-set payloads come from a real `decoy scan --output` on a tiny CSV, so their descriptor path
fields are real; run-result payloads carry an output path per table.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decoy_engine import records
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK
from tests.unit.library._helpers import INVOCATION, PRODUCER, envelope

runner = CliRunner()


def at(day: int) -> datetime:
    return datetime(2026, 11, day, tzinfo=timezone.utc)


def build(
    kind: str, payload: dict, day: int, links: Iterable[tuple[str, str]] = (), **labels: Any
) -> records.RecordEnvelope:
    return records.build(
        kind, payload, producer=PRODUCER, invocation_id=INVOCATION, created_at=at(day),
        labels=labels or None, links=[{"rel": rel, "id": rid} for rel, rid in links],
    )  # fmt: skip


def sample(n: int, day: int, **labels: Any) -> records.RecordEnvelope:
    payload = json.loads(records.encode(envelope(n)))["payload"]
    return build("sample-run", payload, day, **labels)


def table(i: int, name: str, rows: int, state: str = "delivered") -> dict:
    return {
        "index": i, "name": name, "kind": "mask", "outcome": "succeeded", "rows_out": rows,
        "rows_source": "outputs", "row_errors": 0, "elapsed_s": 0.5, "reason": None,
        "delivery": {"state": state, "format": "csv", "output": f"out/{name}.csv",
                     "reason": None, "dropped_because": None},
    }  # fmt: skip


def run_result(
    day: int,
    status: str,
    tables: list[dict],
    chunked: bool = False,
    links: Iterable[tuple[str, str]] = (),
) -> Any:
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
    return build("run-result", payload, day, links=links)


def scan_set(tmp_path: Path, name: str, header: str, day: int) -> Any:
    tmp_path.mkdir(exist_ok=True)
    csv = tmp_path / f"{name}.csv"
    csv.write_text(header + "\n" + "\n".join(f"{i},a{i}@b.com,Ann{i}" for i in range(5)) + "\n")
    out = tmp_path / f"{name}.scan.json"
    result = runner.invoke(app, ["scan", str(csv), "--has-header", "--output", str(out)])
    assert result.exit_code == EXIT_OK, result.output
    return build("scan-set", json.loads(out.read_text(encoding="utf-8")), day)
