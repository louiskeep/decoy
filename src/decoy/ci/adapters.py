"""Thin adapters from Decoy's EXISTING check results to value-free `CheckOutcome`s.

Nothing here re-implements a check. Each adapter calls the same seam the direct command
uses (`validate.run_gate`, `scan.compute_scan_diff`, `evidence.verify_manifest_issues`),
keeps only codes, severities, counts and logical paths from the result, and discards the
raw prose before the report boundary. Any exception becomes a `failed` check with a fixed
reason; its text goes to the unsafe debug sink and nowhere else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from decoy.ci.contracts import (
    CheckOutcome,
    DriftCheck,
    EvidenceCheck,
    PipelineRef,
    RegressionRef,
    SafeFinding,
)
from decoy.ci.debug import DebugSink
from decoy.ci.locations import YamlSourceIndex
from decoy.ci.manifest import LoadedManifest
from decoy.cli.exit_codes import (
    EXIT_CAPACITY,
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    EXIT_WARNINGS,
)


def failed(check_id: str, kind: str, sink: DebugSink) -> CheckOutcome:
    sink.add_exception(f"{check_id}")
    return CheckOutcome.create(
        id=check_id,
        kind=kind,
        status="failed",
        reason_code="ci.check_runtime_failure",
        exit_code=EXIT_RUNTIME,
    )


def refused(check_id: str, kind: str, reason: str) -> CheckOutcome:
    return CheckOutcome.create(
        id=check_id, kind=kind, status="refused", reason_code=reason, exit_code=EXIT_USAGE
    )


def not_applicable(check_id: str, kind: str) -> CheckOutcome:
    return CheckOutcome.create(
        id=check_id,
        kind=kind,
        status="noop",
        reason_code="ci.precommit_not_applicable",
        exit_code=EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Validation (full / config) over the existing pre-run gate
# ---------------------------------------------------------------------------

_CODE_CHARS = re.compile(r"[^a-z0-9_.-]+")


def rule_code(code: str) -> str:
    """Engine/CLI codes are stable tokens; anything else is flattened to the grammar."""
    cleaned = _CODE_CHARS.sub("_", str(code).lower()).strip("_.-")[:100]
    if not cleaned or not cleaned[0].isalpha():
        return "unrecognized_code"
    return cleaned


def validation_outcome(
    loaded: LoadedManifest,
    ref: PipelineRef,
    *,
    mode: str,
    fail_on_warning: bool,
    sink: DebugSink,
) -> CheckOutcome:
    check_id = f"validation.{ref.id}"
    try:
        from decoy.cli.validate import gate_exit_code, run_config_gate, run_gate

        path = loaded.resolve(ref.path)
        rel = loaded.repo_relative(path)
        if rel is None or not path.is_file():
            return refused(check_id, "validation", "ci.input_missing")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            # The direct gate would crash here; report it as the parse error it is.
            finding = SafeFinding.create(
                rule_id="validate.yaml.parse_error",
                level="error",
                safe_message_id="ci.validation_failed",
                check_id=check_id,
                artifact_path=rel,
            )
            return CheckOutcome.create(
                id=check_id,
                kind="validation",
                status="findings",
                reason_code=None,
                findings=[finding],
                exit_code=EXIT_USAGE,
            )
        index = YamlSourceIndex.from_text(rel, text)
        result = run_config_gate(path, text) if mode == "config" else run_gate(path, text)
        findings: list[SafeFinding] = []
        for item in result.findings:
            logical = item.logical_path or item.location
            findings.append(
                SafeFinding.create(
                    rule_id=f"validate.{rule_code(item.code)}",
                    level="error" if item.severity == "error" else "warning",
                    safe_message_id=(
                        "ci.validation_failed"
                        if item.severity == "error"
                        else "ci.validation_warning"
                    ),
                    check_id=check_id,
                    location=index.locate(logical),
                    logical_path=logical,
                    artifact_path=rel,
                )
            )
        code = gate_exit_code(result, fail_on_warning)
        if code == EXIT_CAPACITY:
            status, reason = "refused", "ci.capacity_refused"
        elif code in (EXIT_USAGE, EXIT_WARNINGS):
            status, reason = "findings", None
        else:
            status, reason = "ok", None
        return CheckOutcome.create(
            id=check_id,
            kind="validation",
            status=status,
            reason_code=reason,
            findings=findings,
            exit_code=code,
        )
    except Exception:
        return failed(check_id, "validation", sink)


# ---------------------------------------------------------------------------
# Drift (saved STORM scans) over the existing categorizer
# ---------------------------------------------------------------------------


def _load_scan(path: Path) -> dict:
    # An absolute path always: the shared loader treats the literal "-" as stdin.
    from decoy.cli.scan import _load_scan_dict

    data = _load_scan_dict(str(path))
    if not isinstance(data, dict):
        raise ValueError("scan is not a mapping")
    return data


def drift_outcome(loaded: LoadedManifest, check: DriftCheck, sink: DebugSink) -> CheckOutcome:
    check_id = f"drift.{check.id}"
    try:
        from decoy.cli.scan import compute_scan_diff

        baseline = loaded.resolve(check.baseline)
        current = loaded.resolve(check.current)
        if not baseline.is_file() or not current.is_file():
            return refused(check_id, "drift", "ci.input_missing")
        try:
            diff = compute_scan_diff(_load_scan(baseline), _load_scan(current))
        except (OSError, ValueError, AttributeError, TypeError, KeyError) as exc:
            sink.add(check_id, f"unreadable scan: {exc!r}")
            return refused(check_id, "drift", "ci.drift_unreadable")
        rel = loaded.repo_relative(current)
        from decoy.ci.contracts import SourceLocation

        location = SourceLocation(uri=rel) if rel else None
        level = "error" if check.blocking else "warning"
        buckets = (
            (
                "drift.pii_bucket_increased",
                "ci.drift_pii_bucket_increased",
                len(diff.pii_increased),
            ),
            ("drift.new_high_pii_field", "ci.drift_new_high_pii_field", len(diff.new_high_pii)),
            (
                "drift.new_quasi_identifier_group",
                "ci.drift_new_quasi_identifier_group",
                len(diff.qi_added),
            ),
        )
        findings = [
            SafeFinding.create(
                rule_id=rule,
                level=level,
                safe_message_id=message,
                check_id=check_id,
                location=location,
                occurrences=count,
            )
            for rule, message, count in buckets
            if count
        ]
        if findings and check.blocking:
            return CheckOutcome.create(
                id=check_id,
                kind="drift",
                status="findings",
                reason_code=None,
                findings=findings,
                exit_code=EXIT_FINDINGS,
            )
        return CheckOutcome.create(
            id=check_id,
            kind="drift",
            status="ok",
            reason_code=None,
            findings=findings,
            exit_code=EXIT_OK,
        )
    except Exception:
        return failed(check_id, "drift", sink)


# ---------------------------------------------------------------------------
# Evidence (cli-local-1 manifests) over the existing typed verifier
# ---------------------------------------------------------------------------


def evidence_outcome(loaded: LoadedManifest, check: EvidenceCheck, sink: DebugSink) -> CheckOutcome:
    check_id = f"evidence.{check.id}"
    try:
        from decoy.cli.evidence import verify_manifest_issues

        path = loaded.resolve(check.manifest)
        if not path.is_file():
            return refused(check_id, "evidence", "ci.input_missing")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            sink.add(check_id, f"unreadable evidence manifest: {exc!r}")
            return refused(check_id, "evidence", "ci.evidence_unreadable")
        if not isinstance(manifest, dict):
            return refused(check_id, "evidence", "ci.evidence_unreadable")
        issues = verify_manifest_issues(manifest, regular_files_only=True)
        for issue in issues:
            sink.add(check_id, issue.message)
        rel = loaded.repo_relative(path)
        from decoy.ci.contracts import SourceLocation

        location = SourceLocation(uri=rel) if rel else None
        findings = [
            SafeFinding.create(
                rule_id=f"evidence.{rule_code(issue.kind)}",
                level="error",
                safe_message_id="ci.evidence_mismatch",
                check_id=check_id,
                location=location,
            )
            for issue in issues
        ]
        return CheckOutcome.create(
            id=check_id,
            kind="evidence",
            status="findings" if findings else "ok",
            reason_code=None,
            findings=findings,
            exit_code=EXIT_FINDINGS if findings else EXIT_OK,
        )
    except Exception:
        return failed(check_id, "evidence", sink)


# ---------------------------------------------------------------------------
# F12 regression suites: no public runner exists at this baseline -> fail closed
# ---------------------------------------------------------------------------


def regression_outcome(ref: RegressionRef) -> CheckOutcome:
    return refused(f"regression.{ref.id}", "regression", "ci.regression_runner_unavailable")


__all__ = [
    "drift_outcome",
    "evidence_outcome",
    "failed",
    "not_applicable",
    "refused",
    "regression_outcome",
    "rule_code",
    "validation_outcome",
]
