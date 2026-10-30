"""Ordered orchestration of the selected checks. No check semantics live here.

Order is the manifest's: validation (per pipeline), drift, evidence, regression, then the
staged scan. A selected check is never silently dropped: it yields an outcome, even if only
a refusal. In the pre-commit context only validation (narrowed to config semantics) and the
staged scan run; the other kinds are reported `noop` with a fixed reason.
"""

from __future__ import annotations

from enum import Enum

from decoy.ci import adapters
from decoy.ci.contracts import CheckOutcome, SafeCiReport
from decoy.ci.debug import DebugSink
from decoy.ci.manifest import LoadedManifest, ManifestError
from decoy.ci.staged import scan_staged
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE

PRECOMMIT_NOTE = "ci.precommit_mode_narrowed"


class Context(str, Enum):
    ci = "ci"
    pre_commit = "pre-commit"


def manifest_refusal(error: ManifestError) -> SafeCiReport:
    outcome = CheckOutcome.create(
        id="manifest",
        kind="manifest",
        status="refused",
        reason_code=error.reason_code,
        exit_code=EXIT_USAGE,
    )
    return SafeCiReport.from_outcomes([outcome])


def unexpected_failure_report() -> SafeCiReport:
    """A fixed report for a failure outside any adapter; the cause goes to the debug sink."""
    outcome = CheckOutcome.create(
        id="manifest",
        kind="manifest",
        status="failed",
        reason_code="ci.check_runtime_failure",
        exit_code=EXIT_RUNTIME,
    )
    return SafeCiReport.from_outcomes([outcome])


def _staged_outcome(loaded: LoadedManifest, sink: DebugSink) -> CheckOutcome:
    try:
        result = scan_staged(loaded.root, loaded.manifest.staged_scan)
    except Exception:
        return adapters.failed("staged_scan", "staged_scan", sink)
    sink.add_all("staged_scan", result.raw)
    return CheckOutcome.create(
        id="staged_scan",
        kind="staged_scan",
        status=result.status,
        reason_code=result.reason_code,
        findings=result.findings,
        exit_code=result.exit_code,
    )


def run_checks(loaded: LoadedManifest, context: Context, sink: DebugSink) -> SafeCiReport:
    manifest = loaded.manifest
    checks = manifest.checks
    precommit = context is Context.pre_commit
    outcomes: list[CheckOutcome] = []
    narrowed = False

    validation = checks.validation
    if validation.enabled:
        selected = [
            p
            for p in manifest.pipelines
            if validation.pipelines is None or p.id in validation.pipelines
        ]
        mode = "config" if precommit else validation.mode
        narrowed = narrowed or (precommit and validation.mode == "full")
        for ref in selected:
            outcomes.append(
                adapters.validation_outcome(
                    loaded, ref, mode=mode, fail_on_warning=validation.fail_on_warning, sink=sink
                )
            )

    for drift in checks.drift:
        if precommit:
            outcomes.append(adapters.not_applicable(f"drift.{drift.id}", "drift"))
            narrowed = True
        else:
            outcomes.append(adapters.drift_outcome(loaded, drift, sink))
    for evidence in checks.evidence:
        if precommit:
            outcomes.append(adapters.not_applicable(f"evidence.{evidence.id}", "evidence"))
            narrowed = True
        else:
            outcomes.append(adapters.evidence_outcome(loaded, evidence, sink))
    for suite in checks.regression_suites:
        if precommit:
            outcomes.append(adapters.not_applicable(f"regression.{suite.id}", "regression"))
            narrowed = True
        else:
            outcomes.append(adapters.regression_outcome(suite))

    if manifest.staged_scan.enabled:
        outcomes.append(_staged_outcome(loaded, sink))

    if not outcomes:
        # An empty selection must not look like a pass.
        outcomes.append(
            CheckOutcome.create(
                id="manifest",
                kind="manifest",
                status="refused",
                reason_code="ci.manifest_invalid",
                exit_code=EXIT_USAGE,
            )
        )
    return SafeCiReport.from_outcomes(outcomes, notes=[PRECOMMIT_NOTE] if narrowed else [])
