"""Pure projections of a `SafeCiReport` to JSON, SARIF 2.1.0, and Markdown.

These functions take ONLY a `SafeCiReport`; they cannot reach manifest literals, raw
engine messages, or exceptions. Prose is looked up from the fixed registries in
`contracts`. Output is deterministic: no timestamps, sorted rules and findings.

Prior art: OASIS SARIF 2.1.0 (rules in `tool.driver.rules`, `partialFingerprints`,
one-based `region` with exclusive end column, `columnKind`); GitHub code scanning's use
of stable `ruleId` + fingerprints for alert identity.
"""

from __future__ import annotations

import json
from typing import Any

from decoy.ci import contracts
from decoy.ci.contracts import SafeCiReport, SafeFinding, SourceLocation

SARIF_SCHEMA_URI = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)
SARIF_VERSION = "2.1.0"
_FINGERPRINT_KEY = "primary/v1"


class SarifProjectionError(RuntimeError):
    """A report could not be projected to a schema-correct SARIF log (build-failing)."""


def _dumps(doc: Any, *, indent: int | None = None) -> str:
    if indent is None:
        return json.dumps(doc, separators=(",", ":"), ensure_ascii=True) + "\n"
    return json.dumps(doc, indent=indent, ensure_ascii=True) + "\n"


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _location_dict(loc: SourceLocation | None) -> dict[str, Any] | None:
    if loc is None:
        return None
    return {
        "uri": loc.encoded_uri,
        "start_line": loc.start_line,
        "start_column": loc.start_column,
        "end_line": loc.end_line,
        "end_column": loc.end_column,
    }


def report_to_dict(report: SafeCiReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "status": report.status,
        "exit_code": report.exit_code,
        "checks": [
            {
                "id": c.id,
                "kind": c.kind,
                "status": c.status,
                "reason_code": c.reason_code,
                "finding_count": c.finding_count,
            }
            for c in report.checks
        ],
        "notes": [{"note_id": n} for n in report.notes],
        "findings": [
            {
                "rule_id": f.rule_id,
                "level": f.level,
                "safe_message_id": f.safe_message_id,
                "check_id": f.check_id,
                "location": _location_dict(f.location),
                "fingerprint": f.fingerprint,
                "occurrences": f.occurrences,
            }
            for f in report.findings
        ],
    }


def render_json(report: SafeCiReport) -> str:
    return _dumps(report_to_dict(report))


# ---------------------------------------------------------------------------
# SARIF 2.1.0
# ---------------------------------------------------------------------------


def _message_text(message_id: str) -> str:
    try:
        return contracts.SAFE_MESSAGES[message_id]
    except KeyError as exc:
        raise SarifProjectionError("a finding references an unregistered message id") from exc


def _sarif_location(loc: SourceLocation) -> dict[str, Any]:
    physical: dict[str, Any] = {"artifactLocation": {"uri": loc.encoded_uri}}
    if loc.has_region:
        region: dict[str, Any] = {"startLine": loc.start_line, "startColumn": loc.start_column}
        if loc.end_line is not None:
            region["endLine"] = loc.end_line
            region["endColumn"] = loc.end_column
        physical["region"] = region
    return {"physicalLocation": physical}


def _sarif_result(f: SafeFinding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ruleId": f.rule_id,
        "level": f.level,
        "message": {"text": _message_text(f.safe_message_id)},
        "partialFingerprints": {_FINGERPRINT_KEY: f.fingerprint},
    }
    if f.location is not None:
        result["locations"] = [_sarif_location(f.location)]
    if f.occurrences > 1:
        result["occurrenceCount"] = f.occurrences
    return result


def _sarif_rules(findings: tuple[SafeFinding, ...]) -> list[dict[str, Any]]:
    # One rules[] object per ruleId. If a rule was reported with more than one fixed
    # message, the lexicographically first message id names it: deterministic and still
    # derived from a safe_message_id.
    chosen: dict[str, str] = {}
    for f in findings:
        current = chosen.get(f.rule_id)
        if current is None or f.safe_message_id < current:
            chosen[f.rule_id] = f.safe_message_id
    return [
        {"id": rule_id, "shortDescription": {"text": _message_text(message_id)}}
        for rule_id, message_id in sorted(chosen.items())
    ]


def render_sarif(report: SafeCiReport, *, tool_version: str) -> str:
    rules = _sarif_rules(report.findings)
    defined = {r["id"] for r in rules}
    results = [_sarif_result(f) for f in report.findings]
    for result in results:
        if result["ruleId"] not in defined:  # pragma: no cover - unreachable by construction
            raise SarifProjectionError("a result's ruleId has no tool.driver.rules entry")
    doc = {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Decoy",
                        "semanticVersion": tool_version,
                        "rules": rules,
                    }
                },
                # PyYAML marks and staged-scan columns are counted in code points.
                "columnKind": "unicodeCodePoints",
                "results": results,
            }
        ],
    }
    return _dumps(doc, indent=2)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _where(loc: SourceLocation | None) -> str:
    if loc is None:
        return "(no location)"
    if loc.has_region:
        return f"{loc.encoded_uri}:{loc.start_line}:{loc.start_column}"
    return loc.encoded_uri


def render_markdown(report: SafeCiReport) -> str:
    lines = [
        "# Decoy CI report",
        "",
        f"**Status:** {report.status} (exit {report.exit_code})",
        "",
        "| Check | Kind | Status | Reason | Findings |",
        "|---|---|---|---|---|",
    ]
    for c in report.checks:
        lines.append(
            f"| {c.id} | {c.kind} | {c.status} | {c.reason_code or '-'} | {c.finding_count} |"
        )
    if report.notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {contracts.NOTE_TEXTS[n]}" for n in report.notes]
    lines += ["", "## Findings", ""]
    if not report.findings:
        lines.append("No findings.")
    else:
        current: tuple[str, str] | None = None
        for f in report.findings:
            heading = (f.rule_id, f.level)
            if heading != current:
                current = heading
                lines += [f"### {f.rule_id} ({f.level})", "", _message_text(f.safe_message_id), ""]
            count = f" x{f.occurrences}" if f.occurrences > 1 else ""
            lines.append(f"- {_where(f.location)}{count} ({f.check_id})")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
