"""`load_scan_set`: the one reader of a saved scan, from a path or from stdin.

`decoy scan fields`, `show` and `diff` (and the CI drift check) read a scan through here
and nowhere else, so the accepted shapes and the value-free guarantee live in one place.
G-ONE-SCAN-READER (tests/sentry/test_scan_reader.py) fails when another module reads the
`scan_schema` key itself.

Two shapes come in, and both leave as a `scan-set/v1` dict:

- a file with a top-level `scan_schema`: it must carry the `scan-set/v1` major and match the
  engine's read model (`ScanSetCoreRead`, which ignores fields a newer minor added);
- a file without one: the bare `profile.to_dict()` that `decoy scan --output` wrote before
  `scan-set/v1`. It is shape-checked strictly (see `_LEGACY_*`) and presented as a one-table
  set named from its `source_label`. Its `top_values`, `sentinels` and every other
  value-bearing member are dropped here, so no caller can print one.

Every refusal is a `ScanSetFormatError` with a fixed message. The input text is never put in
an error, because a file that is not a saved scan can hold cell data.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from decoy.cli.scanning import table_name_from_path

_NOT_A_SCAN = "not a saved scan Decoy can read"
_SCHEMA_MAJOR = "scan-set/v1"
_TAG_SHAPE = re.compile(r"^[A-Za-z0-9._/-]{1,32}\Z")
_PII_CANDIDATE_THRESHOLD = 0.6

# What a legacy `profile.to_dict()` must carry. The capture script and fixture beside the
# tests (tests/fixtures/scan/) hold a real one; a test pins that it meets this list. Only the
# members every consumer needs are required; the rest are type-checked when present.
_LEGACY_FIELD_REQUIRED: dict[str, tuple[type, ...]] = {"name": (str,)}
_LEGACY_FIELD_OPTIONAL: dict[str, tuple[type, ...]] = {
    "inferred_type": (str,),
    "null_count": (int,),
    "null_rate": (int, float),
    "distinct_count": (int,),
    "pii_score": (int, float),
    "detector_matches": (list,),
}
_LEGACY_TOP_REQUIRED: dict[str, tuple[type, ...]] = {"fields": (list,)}
_LEGACY_TOP_OPTIONAL: dict[str, tuple[type, ...]] = {
    "row_count": (int,),
    "source_label": (str,),
    "sample_strategy": (str,),
    "sample_row_cap": (int,),
    "reid_risk_score": (int, float),
    "quasi_identifier_groups": (list,),
}


class ScanSetFormatError(ValueError):
    """The input is not a saved scan this CLI can read. The message is fixed text."""


def load_scan_set(path_or_dash: str) -> dict[str, Any]:
    """Read a saved scan (`-` is stdin) and return it as a `scan-set/v1` dict."""
    try:
        if path_or_dash == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(path_or_dash).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # A ValueError, not an OSError: normalised so callers that catch OSError report it
        # cleanly instead of crashing with a traceback. The decode error text is not kept.
        raise OSError("scan file is not valid UTF-8") from None
    return scan_set_from_data(json.loads(raw))


def scan_set_from_data(data: object) -> dict[str, Any]:
    """The same interpretation for an already-parsed document."""
    if not isinstance(data, dict) or _has_non_finite(data):
        raise ScanSetFormatError(_NOT_A_SCAN)
    if "scan_schema" in data:
        return _from_core(data)
    return _from_legacy(data)


def _has_non_finite(node: object) -> bool:
    """True when a parsed document holds NaN, Infinity or an overflowed float anywhere.

    The one check for both saved formats: `json.loads` accepts the bare constants and turns
    `1e999` into infinity, and none of them is valid JSON on the way back out.
    """
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, float):
            if not math.isfinite(item):
                return True
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


def select_table(scan_set: dict[str, Any], table: str | None) -> dict[str, Any]:
    """The one table `fields`, `show` and `diff` work on."""
    tables = scan_set["tables"]
    names = [str(t["name"]) for t in tables]
    if table is None:
        if len(tables) == 1:
            return dict(tables[0])
        raise ScanSetFormatError(
            f"the scan holds {len(tables)} tables ({', '.join(names)}); pass --table NAME"
        )
    for t in tables:
        if t["name"] == table:
            return dict(t)
    raise ScanSetFormatError(f"the scan has no table {table!r}; it holds: {', '.join(names)}")


def _from_core(data: dict[str, Any]) -> dict[str, Any]:
    from decoy_engine.profiling import ScanSetCoreRead

    tag = data.get("scan_schema")
    if not (isinstance(tag, str) and (tag == _SCHEMA_MAJOR or tag.startswith(_SCHEMA_MAJOR + "."))):
        shown = tag if isinstance(tag, str) and _TAG_SHAPE.fullmatch(tag) else "an unrecognised tag"
        raise ScanSetFormatError(f"scan_schema {shown} is not supported (expected {_SCHEMA_MAJOR})")
    failed = False
    try:
        model = ScanSetCoreRead.model_validate({**data, "scan_schema": _SCHEMA_MAJOR})
    except Exception:
        failed = True
    # Raised outside the handler: a validation error carries the input and must not chain.
    if failed:
        raise ScanSetFormatError(_NOT_A_SCAN)
    dumped: dict[str, Any] = model.model_dump()
    return dumped


def _typed(record: dict[str, Any], required: dict, optional: dict) -> None:
    """Refuse a record missing a required member, or holding any member of the wrong type."""
    for key in required:
        if record.get(key) is None:
            raise ScanSetFormatError(_NOT_A_SCAN)
    for key, kinds in {**required, **optional}.items():
        value = record.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, kinds)):
            raise ScanSetFormatError(_NOT_A_SCAN)


def _from_legacy(data: dict[str, Any]) -> dict[str, Any]:
    if "profile" in data and "fields" not in data and isinstance(data["profile"], dict):
        data = data["profile"]
    _typed(data, _LEGACY_TOP_REQUIRED, _LEGACY_TOP_OPTIONAL)
    groups = data.get("quasi_identifier_groups") or []
    if not all(isinstance(g, list) and all(isinstance(n, str) for n in g) for g in groups):
        raise ScanSetFormatError(_NOT_A_SCAN)
    fields = []
    for raw in data["fields"]:
        if not isinstance(raw, dict):
            raise ScanSetFormatError(_NOT_A_SCAN)
        _typed(raw, _LEGACY_FIELD_REQUIRED, _LEGACY_FIELD_OPTIONAL)
        fields.append(_legacy_field(raw))
    label = data.get("source_label")
    return {
        "scan_schema": _SCHEMA_MAJOR,
        "engine_version": "",
        "scanned_at": "",
        "tables": [
            {
                "name": table_name_from_path(Path(label)) if label else "table",
                "descriptor": {},
                "row_count": data.get("row_count") or 0,
                "row_count_exact": True,
                "sample_strategy": data.get("sample_strategy"),
                "sample_row_cap": data.get("sample_row_cap"),
                "fields": fields,
                "key_candidates": [],
                "warnings": [],
                "reid_risk_score": data.get("reid_risk_score"),
                "quasi_identifier_groups": [list(g) for g in groups],
            }
        ],
        "relationships": [],
    }


def _legacy_field(raw: dict[str, Any]) -> dict[str, Any]:
    """The value-free members of a legacy field, in the `FieldCore` shape."""
    score = raw.get("pii_score")
    hits = []
    for match in raw.get("detector_matches") or []:
        if isinstance(match, dict):
            ident = match.get("detector_id") or match.get("detector")
            if isinstance(ident, str):
                hits.append(ident)
    return {
        "name": raw["name"],
        "dtype": raw.get("inferred_type"),
        "null_count": raw.get("null_count"),
        "null_rate": raw.get("null_rate"),
        "distinct_count": raw.get("distinct_count"),
        "pii_score": score,
        "pii_candidate": bool(score is not None and score >= _PII_CANDIDATE_THRESHOLD),
        "detector_hits": hits,
        "leading_zero_count": None,
    }
