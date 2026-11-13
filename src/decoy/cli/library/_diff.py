"""`decoy library diff`: compare two records of one kind, dispatched by the registry's `diff_rule`.

- `scan-set`: each table common to both scans goes through `decoy.cli.scan.compute_scan_diff`,
  the rules `decoy scan diff` and `decoy ci check` already use, after the payload is read by
  `decoy.cli.io.scan_set_from_data`, the one saved-scan reader. Tables added or removed are
  listed by name.
- `evidence`: `decoy.cli.report.compare_manifests`, the `report diff` manifest comparison. Its
  warning lists are reduced to codes, since a warning's detail can carry engine text.
- `run-result`: status, exit code, route, delivery, and per table outcome, rows out, delivery
  state and format.
- any other known kind: a structural diff of the payload, as JSON-pointer paths (RFC 6901)
  that changed, were added or were removed, plus the two payload digests.

No rule is copied here, and every output holds names, counts, codes, states and digests only.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from typing import Any

__all__ = ["diff_payloads"]


def diff_payloads(
    rule: str | None, old: Mapping[str, Any], new: Mapping[str, Any]
) -> tuple[str, dict]:
    """(`rule used`, `diff`) for two verified payloads of one kind."""
    if rule == "scan-set":
        return "scan-set", _scan_set(old, new)
    if rule == "evidence":
        return "evidence", _evidence(old, new)
    if rule == "run-result":
        return "run-result", _run_result(old, new)
    return "structural", _structural(old, new)


def _scan_set(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict:
    from decoy.cli.io import scan_set_from_data
    from decoy.cli.scan import compute_scan_diff

    before = {str(t["name"]): t for t in scan_set_from_data(dict(old))["tables"]}
    after = {str(t["name"]): t for t in scan_set_from_data(dict(new))["tables"]}
    tables: dict[str, dict] = {}
    for name in sorted(set(before) & set(after)):
        found = compute_scan_diff(before[name], after[name])
        tables[name] = {**dataclasses.asdict(found), "drift": found.drift}
    return {
        "tables": tables,
        "tables_added": sorted(set(after) - set(before)),
        "tables_removed": sorted(set(before) - set(after)),
    }


def _warning_codes(items: list[Any]) -> list[str]:
    return [
        str(w.get("code")) if isinstance(w, dict) and w.get("code") else "message" for w in items
    ]


def _evidence(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict:
    from decoy.cli.report import compare_manifests

    found = compare_manifests(dict(old), dict(new))
    found["warnings_added"] = _warning_codes(found.get("warnings_added") or [])
    found["warnings_removed"] = _warning_codes(found.get("warnings_removed") or [])
    return found


def _pair(old: Any, new: Any) -> dict:
    return {"old": old, "new": new}


def _tables(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(t.get("name") if t.get("name") is not None else f"#{t.get('index')}"): t
        for t in payload.get("tables") or ()
    }


def _run_result(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict:
    route_old, route_new = old.get("route") or {}, new.get("route") or {}
    deliv_old, deliv_new = old.get("delivery") or {}, new.get("delivery") or {}
    before, after = _tables(old), _tables(new)
    tables = []
    for name in sorted(set(before) & set(after)):
        a, b = before[name], after[name]
        da, db = a.get("delivery") or {}, b.get("delivery") or {}
        tables.append(
            {
                "table": name,
                "outcome": _pair(a.get("outcome"), b.get("outcome")),
                "rows_out": _pair(a.get("rows_out"), b.get("rows_out")),
                "delivery": _pair(da.get("state"), db.get("state")),
                "format": _pair(da.get("format"), db.get("format")),
            }
        )
    return {
        "status": _pair(old.get("status"), new.get("status")),
        "exit_code": _pair(old.get("exit_code"), new.get("exit_code")),
        "route": {
            k: _pair(route_old.get(k), route_new.get(k))
            for k in ("execution_mode", "route_reason", "chunked")
        },
        "delivery": {
            k: _pair(deliv_old.get(k), deliv_new.get(k)) for k in ("mode", "outcome", "vault")
        },
        "tables": tables,
        "tables_added": sorted(set(after) - set(before)),
        "tables_removed": sorted(set(before) - set(after)),
    }


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _leaves(value: Any, pointer: str) -> Iterator[tuple[str, Any]]:
    if isinstance(value, Mapping) and value:
        for key in sorted(value):
            yield from _leaves(value[key], f"{pointer}/{_escape(str(key))}")
    elif isinstance(value, (list, tuple)) and value:
        for i, item in enumerate(value):
            yield from _leaves(item, f"{pointer}/{i}")
    else:
        yield pointer, value


def _structural(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict:
    from decoy_engine.records import payload_digest

    before, after = dict(_leaves(old, "/payload")), dict(_leaves(new, "/payload"))
    return {
        "changed": sorted(p for p in set(before) & set(after) if before[p] != after[p]),
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "payload_digest": _pair(payload_digest(dict(old)), payload_digest(dict(new))),
    }
