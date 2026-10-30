"""A6: one SafeCiReport -> stable JSON, schema-valid SARIF, and Markdown.

The factory is the leak choke point, so most of this file is about what cannot
be expressed: free messages, absolute URIs, bad tokens, zero lines, exceptions.
"""

from __future__ import annotations

import json

import pytest
from tests.ci_support import assert_valid_sarif

from decoy.ci import contracts
from decoy.ci.contracts import (
    CheckOutcome,
    SafeCiReport,
    SafeFinding,
    SourceLocation,
    UnsafeFindingError,
)
from decoy.ci.reporting import SarifProjectionError, render_json, render_markdown, render_sarif
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_RUNTIME, EXIT_USAGE, EXIT_WARNINGS


def _finding(
    rule="validate.unknown_provider",
    level="error",
    msg="ci.validation_failed",
    check="validation.primary",
    loc=None,
    logical="tables.a.columns.b.provider",
    n=1,
):
    return SafeFinding.create(
        rule_id=rule,
        level=level,
        safe_message_id=msg,
        check_id=check,
        location=loc,
        logical_path=logical,
        occurrences=n,
    )


def _loc(line=14, col=9, uri="pipeline.yaml", end_col=17):
    return SourceLocation(
        uri=uri, start_line=line, start_column=col, end_line=line, end_column=end_col
    )


def _report(findings=(), *, status="findings", exit_code=EXIT_USAGE, notes=()):
    outcome = CheckOutcome.create(
        id="validation.primary",
        kind="validation",
        status=status,
        reason_code=None,
        findings=tuple(findings),
        exit_code=exit_code,
    )
    return SafeCiReport.from_outcomes([outcome], notes=notes)


# ---- the factory: structurally impossible to smuggle prose or values -------------


def test_factory_accepts_no_free_message_or_detail_fields() -> None:
    for kw in ("message", "detail", "text", "sample", "exception", "value", "snippet"):
        with pytest.raises(TypeError):
            SafeFinding.create(  # type: ignore[call-arg]
                rule_id="validate.x",
                level="error",
                safe_message_id="ci.validation_failed",
                check_id="validation.primary",
                **{kw: "anything"},
            )


@pytest.mark.parametrize(
    "bad", ["", "Has Space", "UPPER", "a" * 129, "x/y", "x\ny", "e\u00e9", "a'b", "1abc"]
)
def test_rule_and_check_tokens_are_bounded(bad: str) -> None:
    with pytest.raises(UnsafeFindingError):
        _finding(rule=bad)
    with pytest.raises(UnsafeFindingError):
        _finding(check=bad)


def test_unknown_safe_message_id_is_rejected() -> None:
    with pytest.raises(UnsafeFindingError):
        _finding(msg="ci.made_up")


def test_a_raw_exception_cannot_stand_in_for_a_token() -> None:
    with pytest.raises(UnsafeFindingError):
        _finding(rule=ValueError("secret sample value"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "uri",
    [
        "/abs/path.yaml",
        "C:/abs/path.yaml",
        "file:///x.yaml",
        "../up.yaml",
        "a/../b.yaml",
        "",
        "a\\b.yaml",
        "https://example.invalid/x",
        "a\u0000b.yaml",
    ],
)
def test_locations_must_be_repo_relative_posix(uri: str) -> None:
    with pytest.raises(UnsafeFindingError):
        SourceLocation(uri=uri)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_line": 0, "start_column": 1},
        {"start_line": -1, "start_column": 1},
        {"start_line": 1, "start_column": 0},
        {"start_line": 5, "start_column": 3, "end_line": 4, "end_column": 9},
        {
            "start_line": 5,
            "start_column": 9,
            "end_line": 5,
            "end_column": 9,
        },  # exclusive end must be > start
        {"start_line": 5, "start_column": 9, "end_line": 5, "end_column": 3},
        {"start_line": 5, "start_column": 1, "end_line": 6},  # end column required with end line
        {"start_column": 4},  # column without a line
        {"start_line": 1, "start_column": 1, "end_column": 2},  # end column without end line
        {"start_line": True, "start_column": 1},  # bool is not a position
    ],
)
def test_region_must_be_positive_one_based_and_consistent(kwargs) -> None:
    with pytest.raises(UnsafeFindingError):
        SourceLocation(uri="a.yaml", **kwargs)


def test_uri_with_special_characters_is_stored_decoded_and_encoded_on_output() -> None:
    loc = SourceLocation(uri="fixtures/with space/\u00e9.txt")
    sarif = json.loads(render_sarif(_report([_finding(loc=loc)]), tool_version="1.0.0"))
    uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"][
        "uri"
    ]
    assert uri == "fixtures/with%20space/%C3%A9.txt"
    assert (
        "uriBaseId"
        not in sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]
    )


def test_findings_are_immutable() -> None:
    f = _finding()
    with pytest.raises(Exception):
        f.rule_id = "validate.other"  # type: ignore[misc]


def test_fingerprint_is_value_free_and_stable_across_line_moves() -> None:
    a = _finding(loc=_loc(line=14))
    b = _finding(loc=_loc(line=99))
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != _finding(logical="tables.a.columns.c.provider", loc=_loc()).fingerprint
    assert a.fingerprint != _finding(rule="validate.other", loc=_loc()).fingerprint
    assert len(a.fingerprint) == 64 and all(c in "0123456789abcdef" for c in a.fingerprint)


# ---- JSON ------------------------------------------------------------------------


def test_json_report_is_one_compact_deterministic_object() -> None:
    f1 = _finding(rule="validate.b", loc=_loc(line=30))
    f2 = _finding(rule="validate.a", loc=_loc(line=10))
    r1 = render_json(_report([f1, f2]))
    r2 = render_json(_report([f2, f1, f2]))  # reordered and duplicated
    assert r1 == r2
    assert r1.endswith("\n") and r1.count("\n") == 1  # compact: one line
    doc = json.loads(r1)
    assert list(doc) == ["schema_version", "status", "exit_code", "checks", "notes", "findings"]
    assert doc["schema_version"] == "decoy-ci-report/v1"
    assert [f["rule_id"] for f in doc["findings"]] == ["validate.a", "validate.b"]
    assert doc["checks"] == [
        {
            "id": "validation.primary",
            "kind": "validation",
            "status": "findings",
            "reason_code": None,
            "finding_count": 2,
        }
    ]
    assert "timestamp" not in r1


def test_json_finding_fields_are_the_allowlist() -> None:
    doc = json.loads(render_json(_report([_finding(loc=_loc())])))
    (f,) = doc["findings"]
    assert set(f) == {
        "rule_id",
        "level",
        "safe_message_id",
        "check_id",
        "location",
        "fingerprint",
        "occurrences",
    }
    assert set(f["location"]) == {"uri", "start_line", "start_column", "end_line", "end_column"}


# ---- SARIF -----------------------------------------------------------------------


def test_clean_report_is_schema_valid_with_zero_results() -> None:
    report = _report([], status="ok", exit_code=EXIT_OK)
    doc = json.loads(render_sarif(report, tool_version="1.2.3"))
    assert_valid_sarif(doc)
    assert doc["version"] == "2.1.0"
    assert doc["$schema"].startswith("https://docs.oasis-open.org/sarif/sarif/v2.1.0/")
    (run,) = doc["runs"]
    assert run["results"] == []
    assert run["tool"]["driver"]["name"] == "Decoy"
    assert run["tool"]["driver"]["semanticVersion"] == "1.2.3"
    assert run["columnKind"] == "unicodeCodePoints"


def test_findings_project_with_rules_fingerprints_and_regions() -> None:
    findings = [
        _finding(rule="validate.unknown_provider", loc=_loc(14, 9, end_col=17)),
        _finding(
            rule="validate.missing",
            level="warning",
            msg="ci.validation_warning",
            loc=SourceLocation(uri="pipeline.yaml"),
            logical="tables.a",
        ),
        _finding(rule="validate.yaml.not_mapping", loc=None, logical=None),
    ]
    doc = json.loads(render_sarif(_report(findings), tool_version="1.0.0"))
    assert_valid_sarif(doc)
    run = doc["runs"][0]
    rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == sorted(rules)
    assert len(rules) == len(run["tool"]["driver"]["rules"])
    for res in run["results"]:
        assert res["ruleId"] in rules
        assert rules[res["ruleId"]]["shortDescription"]["text"]
        assert res["partialFingerprints"]["primary/v1"]
        assert res["message"]["text"]
        assert len(res.get("locations", [])) <= 1
    by_rule = {r["ruleId"]: r for r in run["results"]}
    exact = by_rule["validate.unknown_provider"]["locations"][0]["physicalLocation"]
    assert exact["artifactLocation"]["uri"] == "pipeline.yaml"
    assert exact["region"] == {"startLine": 14, "startColumn": 9, "endLine": 14, "endColumn": 17}
    file_level = by_rule["validate.missing"]["locations"][0]["physicalLocation"]
    assert "region" not in file_level
    assert by_rule["validate.missing"]["level"] == "warning"
    free = by_rule["validate.yaml.not_mapping"]
    assert "locations" not in free or free["locations"] == []
    assert free["partialFingerprints"]["primary/v1"]


def test_sarif_never_carries_snippets_context_or_invocations() -> None:
    text = render_sarif(_report([_finding(loc=_loc())]), tool_version="1.0.0")
    for banned in (
        "snippet",
        "contextRegion",
        "invocations",
        "commandLine",
        "environmentVariables",
        "stdout",
        "stderr",
        "exception",
        "attachments",
        "uriBaseId",
        "file://",
    ):
        assert banned not in text, banned


def test_partial_fingerprint_is_stable_when_the_line_moves() -> None:
    def fp(line):
        doc = json.loads(render_sarif(_report([_finding(loc=_loc(line))]), tool_version="1"))
        return doc["runs"][0]["results"][0]["partialFingerprints"]["primary/v1"]

    assert fp(14) == fp(200)


def test_occurrence_count_uses_the_sarif_field() -> None:
    doc = json.loads(render_sarif(_report([_finding(n=7, loc=_loc())]), tool_version="1"))
    assert_valid_sarif(doc)
    assert doc["runs"][0]["results"][0]["occurrenceCount"] == 7


def test_a_rule_without_a_driver_entry_is_a_projection_error(monkeypatch) -> None:
    finding = _finding(loc=_loc())
    report = _report([finding])
    monkeypatch.delitem(contracts.SAFE_MESSAGES, "ci.validation_failed")
    with pytest.raises(SarifProjectionError):
        render_sarif(report, tool_version="1.0.0")


def test_sarif_is_deterministic() -> None:
    f = [_finding(rule="validate.b", loc=_loc(30)), _finding(rule="validate.a", loc=_loc(10))]
    assert render_sarif(_report(f), tool_version="1") == render_sarif(
        _report(f[::-1]), tool_version="1"
    )


# ---- Markdown --------------------------------------------------------------------


def test_markdown_has_summary_table_and_findings_without_code_blocks() -> None:
    report = _report([_finding(loc=_loc())], notes=("ci.precommit_mode_narrowed",))
    md = render_markdown(report)
    assert md.endswith("\n")
    assert "| Check" in md and "validation.primary" in md
    assert "validate.unknown_provider" in md and "pipeline.yaml:14:9" in md
    assert "```" not in md
    assert contracts.NOTE_TEXTS["ci.precommit_mode_narrowed"] in md
    assert render_markdown(report) == md


def test_markdown_clean_report_says_so() -> None:
    md = render_markdown(_report([], status="ok", exit_code=EXIT_OK))
    assert "No findings" in md


# ---- aggregation -----------------------------------------------------------------


def _o(i, status, code, kind="validation", reason=None):
    return CheckOutcome.create(
        id=i, kind=kind, status=status, reason_code=reason, findings=(), exit_code=code
    )


def test_exit_precedence_is_capacity_runtime_usage_findings_warnings_ok() -> None:
    order = [5, 3, 1, 4, 2, 0]
    for hi in range(len(order)):
        for lo in range(hi + 1, len(order)):
            outs = [_o("a", "ok", order[lo]), _o("b", "ok", order[hi])]
            assert SafeCiReport.from_outcomes(outs).exit_code == order[hi]
            assert SafeCiReport.from_outcomes(outs[::-1]).exit_code == order[hi]


def test_report_status_rules() -> None:
    S = SafeCiReport.from_outcomes
    assert S([_o("a", "ok", EXIT_OK)]).status == "ok"
    assert S([_o("a", "noop", EXIT_OK, "staged_scan", "ci.no_staged_files")]).status == "noop"
    assert S([_o("a", "ok", EXIT_OK), _o("b", "noop", EXIT_OK, "staged_scan")]).status == "ok"
    assert S([_o("a", "findings", EXIT_FINDINGS)]).status == "findings"
    assert S([_o("a", "findings", EXIT_WARNINGS)]).status == "findings"
    # a refused check alongside a completed one is partial; refused only when nothing completed
    assert (
        S(
            [
                _o("a", "ok", EXIT_OK),
                _o("b", "refused", EXIT_USAGE, "regression", "ci.regression_runner_unavailable"),
            ]
        ).status
        == "partial"
    )
    assert (
        S([_o("b", "refused", EXIT_USAGE, "regression", "ci.regression_runner_unavailable")]).status
        == "refused"
    )
    assert (
        S(
            [
                _o("a", "ok", EXIT_OK),
                _o("b", "failed", EXIT_RUNTIME, "staged_scan", "ci.git_failure"),
            ]
        ).status
        == "partial"
    )
    assert (
        S([_o("a", "partial", EXIT_USAGE, "staged_scan", "ci.staged_scan_limit")]).status
        == "partial"
    )
    assert S([_o("a", "partial", EXIT_USAGE), _o("b", "ok", EXIT_OK)]).exit_code == EXIT_USAGE


def test_a_partial_or_refused_report_never_exits_zero() -> None:
    with pytest.raises(ValueError):
        SafeCiReport.from_outcomes([_o("a", "refused", EXIT_OK)])
    with pytest.raises(ValueError):
        SafeCiReport.from_outcomes([_o("a", "failed", EXIT_OK)])
    with pytest.raises(ValueError):
        SafeCiReport.from_outcomes([_o("a", "partial", EXIT_OK)])


def test_exit_codes_must_be_the_public_taxonomy() -> None:
    for bad in (6, -1, 99):
        with pytest.raises(ValueError):
            _o("a", "ok", bad)


def test_unknown_note_ids_are_rejected() -> None:
    with pytest.raises(ValueError):
        SafeCiReport.from_outcomes([_o("a", "ok", EXIT_OK)], notes=("free text note",))


def test_finding_count_matches_findings_and_cannot_be_forged() -> None:
    outcome = CheckOutcome.create(
        id="validation.primary",
        kind="validation",
        status="findings",
        reason_code=None,
        findings=(_finding(), _finding(rule="validate.other")),
        exit_code=EXIT_USAGE,
    )
    assert outcome.result.finding_count == 2
