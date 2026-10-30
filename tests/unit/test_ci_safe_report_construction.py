"""`SafeCiReport` and its parts are intrinsically safe: direct construction is validated.

The factories are conveniences, not the only gate. A caller (or a future emitter) that builds
the dataclasses directly with free text must be refused, and no render function may emit it.
"""

from __future__ import annotations

import dataclasses

import pytest

from decoy.ci import reporting
from decoy.ci.contracts import (
    CI_REPORT_VERSION,
    CheckOutcome,
    CheckResult,
    SafeCiReport,
    SafeFinding,
    UnsafeFindingError,
)
from decoy.cli.exit_codes import EXIT_OK

CANARY = "SECRET_CANARY"


def _result(**over):
    base = dict(id="validation.primary", kind="validation", status="ok", reason_code=None)
    base.update(finding_count=0)
    base.update(over)
    return CheckResult(**base)


def _report(**over):
    base = dict(
        schema_version=CI_REPORT_VERSION,
        status="ok",
        exit_code=EXIT_OK,
        checks=(_result(),),
        notes=(),
        findings=(),
    )
    base.update(over)
    return SafeCiReport(**base)


def test_a_valid_direct_construction_is_accepted_and_renders() -> None:
    report = _report()
    assert reporting.render_json(report).count(CANARY) == 0


BAD_RESULTS = {
    "id": {"id": CANARY},
    "id-spaced": {"id": "SECRET CANARY"},
    "kind": {"kind": CANARY},
    "status": {"status": CANARY},
    "reason": {"reason_code": CANARY},
    "count-negative": {"finding_count": -1},
    "count-bool": {"finding_count": True},
}


@pytest.mark.parametrize("over", BAD_RESULTS.values(), ids=BAD_RESULTS.keys())
def test_check_result_refuses_unsafe_fields_directly(over) -> None:
    with pytest.raises(UnsafeFindingError) as raised:
        _result(**over)
    assert CANARY not in str(raised.value)


BAD_REPORT_FIELDS = {
    "notes-text": lambda: {"notes": (CANARY,)},
    "notes-str": lambda: {"notes": "ci.precommit_mode_narrowed"},
    "checks-text": lambda: {"checks": (CANARY,)},
    "checks-empty": lambda: {"checks": ()},
    "findings-text": lambda: {"findings": (CANARY,)},
    "schema": lambda: {"schema_version": CANARY},
    "status": lambda: {"status": CANARY},
    "status-failed": lambda: {"status": "failed"},
    "exit-unknown": lambda: {"exit_code": 99},
    "exit-bool": lambda: {"exit_code": True},
}


@pytest.mark.parametrize("make", BAD_REPORT_FIELDS.values(), ids=BAD_REPORT_FIELDS.keys())
def test_direct_report_construction_refuses_unsafe_fields(make) -> None:
    with pytest.raises(UnsafeFindingError) as raised:
        _report(**make())
    assert CANARY not in str(raised.value)


def test_a_spec_example_from_review_is_refused() -> None:
    with pytest.raises(UnsafeFindingError):
        CheckResult(CANARY, "validation", "ok", None, 0)
    with pytest.raises(UnsafeFindingError):
        SafeCiReport(
            CI_REPORT_VERSION,
            "ok",
            EXIT_OK,
            (CheckResult("validation.primary", "validation", "ok", None, 0),),
            (CANARY,),
            (),
        )


def test_direct_outcome_and_finding_construction_is_refused() -> None:
    with pytest.raises(UnsafeFindingError):
        CheckOutcome(_result(), (CANARY,), EXIT_OK)  # type: ignore[arg-type]
    with pytest.raises(UnsafeFindingError):
        CheckOutcome(_result(), (), 99)
    with pytest.raises(UnsafeFindingError):
        CheckOutcome(_result(status="failed"), (), EXIT_OK)
    with pytest.raises(UnsafeFindingError):
        SafeFinding(CANARY, "error", "ci.validation_failed", "validation.p", None, "0" * 64)


def test_replace_cannot_smuggle_text_past_the_validator() -> None:
    good = _report()
    with pytest.raises(UnsafeFindingError):
        dataclasses.replace(good, notes=(CANARY,))


@pytest.mark.parametrize("render", [reporting.render_json, reporting.render_markdown])
def test_renderers_reject_a_report_mutated_after_construction(render) -> None:
    good = _report()
    object.__setattr__(good, "notes", (CANARY,))
    with pytest.raises(UnsafeFindingError):
        render(good)


def test_sarif_renderer_also_revalidates() -> None:
    good = _report()
    object.__setattr__(good, "notes", (CANARY,))
    with pytest.raises(reporting.SarifProjectionError):
        reporting.render_sarif(good, tool_version="0")
