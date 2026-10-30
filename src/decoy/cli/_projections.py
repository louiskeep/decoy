"""Typed, allowlisted, value-free projections for pre-scan and post-scan.

Each function reads an engine object (a profile dict, a saved scan, a
`post-scan-integrity/v2` report, a `quality-report/v1` + policy result) as
untrusted input and returns a minted `Projection`. Keys are allowlisted and
VALUES are constrained, so nothing reaches a surface unless it passes one of:

* numbers: real finite numbers (never bool/str); scores and rates also in [0, 1];
* vocabulary strings: an exact member of a closed set, otherwise the generic
  `unrecognized` code (the entry stays visible, its text does not);
* names (columns, quasi-identifier members, fk namespaces, strategies): at most
  `MAX_IDENTIFIER_LENGTH` characters from a conservative charset, otherwise an
  opaque label (`field-N` by column position for a scan, `redacted-name-N`
  per response elsewhere). A short clean-charset column name is schema and is
  output by design; paths, URLs, DSNs, exception text and long strings are not;
* tables: always an opaque `table-N`. The CLI derives table names from file
  stems and config, so they are never output;
* free text the engine writes (finding messages, violation details, warning
  details) is never read.

Mirrors the platform's `fidelity-report/v1` projection (decoy-platform
`api/jobs/fidelity_projection.py`), which solved the same problem for the same
engine report. The raw engine reports themselves are never rewritten.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from decoy.cli._value_free import Projection, mint

UNRECOGNIZED = "unrecognized"
MAX_IDENTIFIER_LENGTH = 64
_IDENTIFIER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ .\-]*")
_TYPE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")

PII_CANDIDATE_THRESHOLD = 0.6

PII_NOTE = (
    "PII candidates are SUGGESTIONS based on pattern matching. "
    "They are not authoritative classifications. Review each flagged field "
    "and decide what masking to apply. Decoy never auto-classifies PII."
)
FIDELITY_NOTE = (
    "Fidelity measures statistical similarity between source and output. "
    "It is not a privacy guarantee."
)
INTEGRITY_NOTE = (
    "Report-only: findings cover the integrity checks that ran. This is not a "
    "release decision or a guarantee that no sensitive data remains."
)

SAMPLE_STRATEGIES = frozenset({"full", "head", "random"})
DTYPES = frozenset({"integer", "float", "string", "date", "datetime", "boolean", "mixed", "empty"})
PII_BUCKETS = frozenset({"high", "med", "low", "none"})


def _detectors() -> frozenset[str]:
    from decoy_engine.detection import DOMAIN_BY_DETECTOR

    return frozenset(DOMAIN_BY_DETECTOR)


# ---- value policies --------------------------------------------------------------------------


def number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def score(value: Any) -> int | float | None:
    n = number(value)
    return n if n is not None and 0 <= n <= 1 else None


def magnitude(value: Any) -> int | float | None:
    n = number(value)
    return n if n is not None and n >= 0 else None


def count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def flag(value: Any) -> bool:
    return value is True


def timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return None


def vocab(value: Any, allowed: frozenset[str]) -> str:
    return value if isinstance(value, str) and value in allowed else UNRECOGNIZED


def vocab_or_none(value: Any, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def type_name(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and _TYPE_NAME.fullmatch(value) else UNRECOGNIZED


def clean_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_IDENTIFIER_LENGTH
        and _IDENTIFIER.fullmatch(value) is not None
    )


class Names:
    """One response's identifier policy; opaque labels are stable within the response."""

    def __init__(self, positions: dict[str, int] | None = None) -> None:
        self._positions = positions or {}
        self._labels: dict[str, str] = {}

    def one(self, value: Any) -> str | None:
        if value is None:
            return None
        if clean_identifier(value):
            return value
        if isinstance(value, str) and value in self._positions:
            return f"field-{self._positions[value]}"
        key = value if isinstance(value, str) else repr(type(value))
        if key not in self._labels:
            self._labels[key] = f"redacted-name-{len(self._labels) + 1}"
        return self._labels[key]

    def many(self, values: Any) -> list[str | None]:
        return [self.one(v) for v in values] if isinstance(values, (list, tuple)) else []


class Tables:
    """Tables are always opaque: `table-1`, `table-2` in first-seen order."""

    def __init__(self) -> None:
        self._ids: dict[str, str] = {}

    def one(self, value: Any) -> str | None:
        if value is None:
            return None
        key = value if isinstance(value, str) else repr(type(value))
        if key not in self._ids:
            self._ids[key] = f"table-{len(self._ids) + 1}"
        return self._ids[key]


def _entries(block: Any, key: str) -> list[dict[str, Any]]:
    raw = block.get(key) if isinstance(block, dict) else None
    return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []


def _block(block: Any, key: str) -> dict[str, Any]:
    inner = block.get(key) if isinstance(block, dict) else None
    return inner if isinstance(inner, dict) else {}


# ---- pre-scan --------------------------------------------------------------------------------


def pii_bucket(value: Any) -> str:
    s = number(value)
    if s is None or s <= 0:
        return "none"
    if s >= PII_CANDIDATE_THRESHOLD:
        return "high"
    if s >= 0.3:
        return "med"
    return "low"


def scan_names(fields: list[dict[str, Any]]) -> Names:
    """Field labels for a scan: a dirty name becomes `field-N` by column position."""
    positions: dict[str, int] = {}
    for i, f in enumerate(fields, start=1):
        name = f.get("name")
        if isinstance(name, str):
            positions.setdefault(name, i)
    return Names(positions)


def scan_fields(scan: dict[str, Any]) -> list[dict[str, Any]]:
    return _entries(scan, "fields")


def field_record(field: dict[str, Any], names: Names) -> dict[str, Any]:
    detectors = _detectors()
    raw_hits = field.get("detector_matches")
    hits = []
    for m in raw_hits if isinstance(raw_hits, list) else []:
        if isinstance(m, dict):
            hits.append(vocab(m.get("detector_id") or m.get("detector"), detectors))
    pii = score(field.get("pii_score"))
    null_rate = score(field.get("null_rate"))
    return {
        "name": names.one(field.get("name")),
        "dtype": vocab(field.get("inferred_type") or field.get("dtype"), DTYPES),
        "null_rate": round(null_rate, 4) if null_rate is not None else None,
        "distinct_count": count(field.get("distinct_count", field.get("unique_count"))),
        "pii_score": round(pii, 3) if pii is not None else None,
        "pii_bucket": pii_bucket(pii),
        "pii_candidate": pii is not None and pii >= PII_CANDIDATE_THRESHOLD,
        "detector_hits": hits,
    }


def _qi_groups(scan: dict[str, Any], names: Names) -> list[list[str | None]]:
    raw = scan.get("quasi_identifier_groups")
    return [names.many(g) for g in raw if isinstance(g, (list, tuple))] if isinstance(raw, list) else []


def profile(scan: dict[str, Any], *, include_fields: bool, saved: bool) -> Projection:
    fields = scan_fields(scan)
    names = scan_names(fields)
    records = [field_record(f, names) for f in fields]
    body: dict[str, Any] = {
        "row_count": count(scan.get("row_count")),
        "field_count": len(records),
        "sample_strategy": vocab_or_none(scan.get("sample_strategy"), SAMPLE_STRATEGIES),
        "pii_candidate_count": sum(1 for r in records if r["pii_candidate"]),
        "pii_note": PII_NOTE,
        "reid_risk_score": magnitude(scan.get("reid_risk_score")),
        "quasi_identifier_groups": _qi_groups(scan, names),
        "saved": saved,
    }
    if include_fields:
        body["fields"] = records
    return mint("pre-scan-profile/v1", body)


def field_list(scan: dict[str, Any], *, pii: str | None, quasi: bool) -> Projection:
    fields = scan_fields(scan)
    names = scan_names(fields)
    qi = _qi_groups(scan, names)
    members = {m for g in qi for m in g}
    rows = []
    for f in fields:
        rec = field_record(f, names)
        is_qi = rec["name"] in members
        if pii is not None and rec["pii_bucket"] != pii:
            continue
        if quasi and not is_qi:
            continue
        rows.append(
            {
                "name": rec["name"],
                "pii_score": rec["pii_score"],
                "pii_bucket": rec["pii_bucket"],
                "quasi_identifier": is_qi,
            }
        )
    return mint("pre-scan-fields/v1", {"matched": len(rows), "total": len(fields), "fields": rows})


def find_field(scan: dict[str, Any], requested: str) -> dict[str, Any] | None:
    """Match by exact name, or by the `field-N` label a dirty name is shown as."""
    fields = scan_fields(scan)
    for f in fields:
        if f.get("name") == requested:
            return f
    m = re.fullmatch(r"field-([1-9][0-9]{0,5})", requested)
    if m and int(m.group(1)) <= len(fields):
        return fields[int(m.group(1)) - 1]
    return None


def closest_field(scan: dict[str, Any], requested: str) -> str | None:
    """A policed suggestion for a mistyped field name."""
    import difflib

    fields = scan_fields(scan)
    names = scan_names(fields)
    raw = [f.get("name") for f in fields if isinstance(f.get("name"), str)]
    close = difflib.get_close_matches(requested, raw, n=1)
    return names.one(close[0]) if close else None


def field_detail(scan: dict[str, Any], field: dict[str, Any]) -> Projection:
    names = scan_names(scan_fields(scan))
    rec = field_record(field, names)
    qi = [g for g in _qi_groups(scan, names) if rec["name"] in g]
    sentinels = field.get("sentinels")
    return mint(
        "pre-scan-field/v1",
        {
            "field": rec,
            "pii_bucket": rec["pii_bucket"],
            "quasi_identifier_groups": qi,
            "sentinel_count": len(sentinels) if isinstance(sentinels, list) else 0,
            "values_withheld": bool(field.get("top_values")) or bool(sentinels),
        },
    )


def scan_diff(old: dict[str, Any], new: dict[str, Any]) -> Projection:
    old_fields = {f.get("name"): f for f in scan_fields(old) if isinstance(f.get("name"), str)}
    new_fields = {f.get("name"): f for f in scan_fields(new) if isinstance(f.get("name"), str)}
    # One label space across both scans, positioned by the newer scan first.
    positions: dict[str, int] = {}
    for i, n in enumerate([*new_fields, *[n for n in old_fields if n not in new_fields]], 1):
        positions[n] = i
    names = Names(positions)
    rank = {"none": 0, "low": 1, "med": 2, "high": 3}

    def row(name: str, f: dict[str, Any]) -> dict[str, Any]:
        s = score(f.get("pii_score"))
        return {"name": names.one(name), "pii_score": s, "pii_bucket": pii_bucket(s)}

    increased, decreased = [], []
    for name in sorted(set(old_fields) & set(new_fields)):
        o, n = row(name, old_fields[name]), row(name, new_fields[name])
        change = {
            "name": n["name"],
            "old_score": o["pii_score"],
            "new_score": n["pii_score"],
            "old_bucket": o["pii_bucket"],
            "new_bucket": n["pii_bucket"],
        }
        if rank[n["pii_bucket"]] > rank[o["pii_bucket"]]:
            increased.append(change)
        elif rank[n["pii_bucket"]] < rank[o["pii_bucket"]]:
            decreased.append(change)
    added = [row(n, new_fields[n]) for n in sorted(set(new_fields) - set(old_fields))]
    removed = [row(n, old_fields[n]) for n in sorted(set(old_fields) - set(new_fields))]
    old_qi = {tuple(sorted(str(x) for x in g)) for g in _qi_groups(old, names)}
    new_qi = {tuple(sorted(str(x) for x in g)) for g in _qi_groups(new, names)}
    qi_added = sorted(new_qi - old_qi)
    qi_removed = sorted(old_qi - new_qi)
    old_risk, new_risk = magnitude(old.get("reid_risk_score")), magnitude(new.get("reid_risk_score"))
    delta = None if old_risk is None or new_risk is None else float(new_risk) - float(old_risk)
    new_high = [r for r in added if r["pii_bucket"] == "high"]
    return mint(
        "pre-scan-diff/v1",
        {
            "summary": {
                "added": len(added),
                "removed": len(removed),
                "pii_increased": len(increased),
                "pii_decreased": len(decreased),
                "qi_groups_added": len(qi_added),
                "qi_groups_removed": len(qi_removed),
                "reid_risk_delta": delta,
            },
            "changes": {
                "added": added,
                "removed": removed,
                "pii_increased": increased,
                "pii_decreased": decreased,
                "qi_groups_added": [list(g) for g in qi_added],
                "qi_groups_removed": [list(g) for g in qi_removed],
            },
            "drift": bool(increased or new_high or qi_added),
        },
    )


# ---- post-scan integrity ---------------------------------------------------------------------

INTEGRITY_SOURCE_SCHEMAS = frozenset({"post-scan-integrity/v2"})
INTEGRITY_SEVERITIES = frozenset({"info", "warning", "fail", "error"})
INTEGRITY_BUCKETS = ("residual_pii", "fk_preservation", "policy_validation")


def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        sev = f["severity"]
        counts[sev] = counts.get(sev, 0) + 1
    return dict(sorted(counts.items()))


def integrity_report(report: Any) -> Projection:
    """`integrity-report/v1` from a `post-scan-integrity/v2` report dict."""
    names, tables, detectors = Names(), Tables(), _detectors()
    residual = [
        {
            "table": tables.one(f.get("table")),
            "column": names.one(f.get("column")),
            "detector": vocab(f.get("detector_id"), detectors),
            "severity": vocab(f.get("severity"), INTEGRITY_SEVERITIES),
            "match_rate": score(f.get("match_rate")),
            "sample_match_count": count(f.get("sample_match_count")),
            "configured_strategy": names.one(f.get("configured_strategy")),
            "source_identity_rate": score(f.get("source_identity_rate")),
            "source_compared": flag(f.get("source_compared")),
        }
        for f in _entries(report, "residual_pii")
    ]
    fk = [
        {
            "parent_table": tables.one(f.get("parent_table")),
            "parent_column": names.one(f.get("parent_column")),
            "child_table": tables.one(f.get("child_table")),
            "child_column": names.one(f.get("child_column")),
            "severity": vocab(f.get("severity"), INTEGRITY_SEVERITIES),
            "orphan_count": count(f.get("orphan_count")),
            "total_child_rows": count(f.get("total_child_rows")),
            "orphan_rate": score(f.get("orphan_rate")),
            "namespace": names.one(f.get("namespace")),
        }
        for f in _entries(report, "fk_preservation")
    ]
    policy = [
        {
            "table": tables.one(f.get("table")),
            "column": names.one(f.get("column")),
            "strategy": names.one(f.get("strategy")),
            "severity": vocab(f.get("severity"), INTEGRITY_SEVERITIES),
            "source_distinct": count(f.get("source_distinct")),
            "output_distinct": count(f.get("output_distinct")),
            "bytes_identical": flag(f.get("bytes_identical")),
        }
        for f in _entries(report, "policy_validation")
    ]
    block = report if isinstance(report, dict) else {}
    counts = {k: count(block.get(k)) or 0 for k in ("pass_count", "warning_count", "fail_count", "error_count")}
    by_bucket = dict(zip(INTEGRITY_BUCKETS, (residual, fk, policy), strict=True))
    return mint(
        "integrity-report/v1",
        {
            "source_schema_version": vocab_or_none(
                block.get("schema_version"), INTEGRITY_SOURCE_SCHEMAS
            ),
            "generated_at": timestamp(block.get("generated_at")),
            **counts,
            "pass_failed_with": type_name(block.get("pass_failed_with")),
            "buckets": {
                name: {"findings": len(items), "severities": _severity_counts(items)}
                for name, items in by_bucket.items()
            },
            **by_bucket,
            "note": INTEGRITY_NOTE,
        },
    )


# ---- post-scan fidelity (mirrors decoy-platform api/jobs/fidelity_projection.py) -------------

GRADES = frozenset({"A", "B", "C", "D", "F", "unavailable"})
WARNING_SOURCES = frozenset({"diagnostic", "fidelity"})
WARNING_CODES = frozenset(
    {
        "column_survival",
        "row_count",
        "kind_drift",
        "null_drift",
        "no_comparable_columns",
        "no_comparable_joints",
        "gof_unavailable",
    }
)
ENTRY_KINDS = frozenset({"column", "joint"})
SEVERITIES = frozenset({"warn", "fail"})
GOF_METRICS = frozenset({"ks_complement", "chi_cramers_v"})
METHODS = frozenset(
    {
        "no_output_joint",
        "kind_mismatch",
        "empty",
        "unknown_kind",
        "no_quantiles",
        "no_range",
        "quantile_rmse",
        "no_data",
        "tvd",
        "no_length",
        "length_mean_diff",
        "bin_counts_sorted_tvd",
        "freq_vector_sorted_tvd",
        "year_bins_sorted_tvd",
        "length_bins_sorted_tvd",
        "joint_cells_sorted_tvd",
        "ks_complement_binned_cdf",
        "chi_square_common_partition_cramers_v",
    }
)
POLICY_SCHEMAS = frozenset({"quality-policy/v1"})
POLICY_VERDICTS = frozenset({"pass", "warn", "fail"})
POLICY_MODES = frozenset({"report", "warn", "fail"})
POLICY_CHECKS = frozenset(
    {
        "diagnostic",
        "overall",
        "marginal",
        "pairwise",
        "column",
        "shape_overall",
        "shape_marginal",
        "shape_pairwise",
        "shape_column",
    }
)


def method(value: Any) -> str:
    if isinstance(value, str) and value.startswith("unknown_kind:"):
        return "unknown_kind"
    return vocab(value, METHODS)


def _warnings(report: dict[str, Any], names: Names) -> list[dict[str, Any]]:
    out = []
    for w in _entries(report, "warnings"):
        item: dict[str, Any] = {
            "source": vocab(w.get("source"), WARNING_SOURCES),
            "code": vocab(w.get("code"), WARNING_CODES),
        }
        if "column" in w:
            item["column"] = names.one(w["column"])
        if "kind" in w:
            item["kind"] = vocab(w["kind"], ENTRY_KINDS)
        if "severity" in w:
            item["severity"] = vocab(w["severity"], SEVERITIES)
        if "threshold" in w:
            item["threshold"] = number(w["threshold"])
        if "metric" in w:
            item["metric"] = vocab(w["metric"], GOF_METRICS)
        out.append(item)
    return out


def _omissions(report: dict[str, Any], names: Names) -> list[dict[str, Any]]:
    out = []
    for o in _entries(report, "omissions"):
        kind = vocab(o.get("kind"), ENTRY_KINDS)
        raw = o.get("name")
        name = (
            "+".join(str(names.one(p)) for p in raw.split("+"))
            if kind == "joint" and isinstance(raw, str)
            else names.one(raw)
        )
        item: dict[str, Any] = {"kind": kind, "name": name, "reason": method(o.get("reason"))}
        if "method" in o:
            item["method"] = method(o["method"])
        out.append(item)
    return out


def _policy(verdict: Any) -> dict[str, Any] | None:
    if not isinstance(verdict, dict):
        return None
    return {
        "schema_version": vocab_or_none(verdict.get("schema_version"), POLICY_SCHEMAS),
        "verdict": vocab_or_none(verdict.get("verdict"), POLICY_VERDICTS),
        "mode": vocab_or_none(verdict.get("mode"), POLICY_MODES),
        "violations": [
            {
                "check": vocab(v.get("check"), POLICY_CHECKS),
                "severity": vocab(v.get("severity"), SEVERITIES),
                "expected": number(v.get("expected")),
                "actual": number(v.get("actual")),
            }
            for v in _entries(verdict, "violations")
        ],
    }


def _columns(report: dict[str, Any], names: Names) -> list[dict[str, Any]]:
    shape = {
        sc["column"]: sc
        for sc in _entries(_block(_block(report, "shape_fidelity"), "marginal"), "columns")
        if isinstance(sc.get("column"), str)
    }
    out = []
    for col in _entries(_block(report, "marginal"), "columns"):
        raw = col.get("column")
        entry: dict[str, Any] = {
            "name": names.one(raw),
            "score": score(col.get("similarity")),
            "comparable": col.get("comparable", True) is not False,
            "method": method(col.get("method")),
        }
        if isinstance(raw, str) and raw in shape:
            entry["shape_score"] = score(shape[raw].get("shape_similarity"))
            entry["shape_method"] = method(shape[raw].get("method"))
        out.append(entry)
    return out


def _pairs(report: dict[str, Any], names: Names) -> list[dict[str, Any]]:
    shape: dict[tuple[str, ...], dict[str, Any]] = {}
    for sj in _entries(_block(_block(report, "shape_fidelity"), "pairwise"), "joints"):
        cols = sj.get("columns")
        if isinstance(cols, list) and cols:
            shape[tuple(str(c) for c in cols)] = sj
    out = []
    for joint in _entries(_block(report, "pairwise"), "joints"):
        cols = joint.get("columns")
        raw = cols if isinstance(cols, list) else []
        entry: dict[str, Any] = {
            "columns": names.many(raw),
            "score": score(joint.get("similarity")),
            "comparable": joint.get("comparable", True) is not False,
            "method": method(joint.get("method")),
        }
        key = tuple(str(c) for c in raw)
        if key in shape:
            entry["shape_score"] = score(shape[key].get("shape_similarity"))
            entry["shape_method"] = method(shape[key].get("method"))
        out.append(entry)
    return out


def fidelity_report(report: Any, policy_result: Any) -> Projection:
    """`fidelity-report/v1` from a `quality-report/v1` and its `quality-policy/v1` verdict."""
    names = Names()
    report = report if isinstance(report, dict) else {}
    shape = _block(report, "shape_fidelity")
    return mint(
        "fidelity-report/v1",
        {
            "source_schema_version": vocab_or_none(
                report.get("schema_version"), frozenset({"quality-report/v1"})
            ),
            "generated_at": timestamp(report.get("generated_at")),
            "grade": vocab_or_none(report.get("grade"), GRADES),
            "overall_score": score(report.get("overall_score")),
            "marginal_score": score(_block(report, "marginal").get("score")),
            "pairwise_score": score(_block(report, "pairwise").get("score")),
            "shape_score": score(shape.get("overall_shape_score")),
            "diagnostic_passed": flag(_block(report, "diagnostic").get("passed")),
            "source_row_count": count(_block(report, "source").get("row_count")),
            "output_row_count": count(_block(report, "output").get("row_count")),
            "sampled": flag(report.get("sampled")),
            "sample_size": count(report.get("sample_size")),
            "columns": _columns(report, names),
            "pairs": _pairs(report, names),
            "warnings": _warnings(report, names),
            "omissions": _omissions(report, names),
            "policy": _policy(policy_result),
            "note": FIDELITY_NOTE,
        },
    )
