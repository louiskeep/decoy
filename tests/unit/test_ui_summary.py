"""The warning sentences the run summary and `report fidelity` share (GEN-CLI C1)."""

from __future__ import annotations

from decoy_engine import QualityWarning

from decoy.ui.summary import (
    report_warning_records,
    warning_lines,
    warning_record,
    warning_records,
)

_DETAIL = {
    "table": "orders",
    "snapshot_index": 0,
    "overall_score": 0.42,
    "threshold": 0.8,
    "trigger": "overall",
    "worst_columns": [["start_date", 0.39], ["age", 0.5]],
    "below_columns": [["start_date", 0.39]],
}


def _engine(**overrides: object) -> QualityWarning:
    return QualityWarning(
        code="generation_fidelity_below_threshold",
        provider="statistical",
        detail={**_DETAIL, **overrides},
    )


def test_overall_trigger_sentence() -> None:
    (rec,) = warning_records([_engine()])
    assert warning_lines([rec]) == [
        "table orders: fidelity 0.42 is below fidelity_warn_threshold 0.80; lowest: start_date 0.39"
    ]
    assert rec["table"] == "orders" and rec["code"] == "generation_fidelity_below_threshold"


def test_column_trigger_sentence() -> None:
    (rec,) = warning_records(
        [
            _engine(
                table="people",
                trigger="column",
                overall_score=0.861,
                below_columns=[["null90", 0.096]],
            )
        ]
    )
    assert rec["message"] == (
        "table people: column null90 scores 0.10, below fidelity_warn_threshold 0.80 (overall 0.86)"
    )


def test_unknown_engine_code_prints_code_and_detail() -> None:
    w = QualityWarning(code="pool_fallback", provider="p", column="c", detail={"rows": 3})
    (rec,) = warning_records([w])
    assert rec["message"] == "pool_fallback (column c): rows=3"


def test_cli_warning_follows_the_engine_warnings() -> None:
    recs = warning_records([_engine()], [{"code": "seed_ignored_with_master_key"}])
    assert [r["code"] for r in recs] == [
        "generation_fidelity_below_threshold",
        "seed_ignored_with_master_key",
    ]
    assert "Masked tables still use the seed." in recs[1]["message"]


def test_report_drift_lines_one_per_column() -> None:
    recs = report_warning_records(
        [
            {
                "source": "diagnostic",
                "code": "null_drift",
                "detail": {
                    "threshold_pp": 10.0,
                    "drifted": [
                        {"column": "a", "source_null_pct": 90.0, "output_null_pct": 0.0},
                        {"column": "b", "source_null_pct": 50.0, "output_null_pct": 5.0},
                    ],
                },
            },
            {"source": "fidelity", "code": "no_comparable_columns", "detail": {}},
        ]
    )
    assert warning_lines(recs) == [
        "column a: 90.0% empty in the source, 0.0% in the output (limit 10 points)",
        "column b: 50.0% empty in the source, 5.0% in the output (limit 10 points)",
        "no_comparable_columns",
    ]


def test_huge_dict_detail_stays_short_in_human_line_and_whole_in_json() -> None:
    big = {f"row{i}": i for i in range(10_000)}
    w = QualityWarning(code="pool_fallback", provider="p", column="c", detail={"by_row": big})
    (rec,) = warning_records([w])
    assert rec["message"] == "pool_fallback (column c): by_row=<10000 entries>"
    assert len(rec["message"]) < 200
    assert len(rec["detail"]["by_row"]) == 10_000


def test_has_kind_counts_a_mask_table_with_empty_columns() -> None:
    from decoy.cli.run import _has_kind

    assert _has_kind({"tables": [{"name": "t", "columns": []}]}, "columns")
    assert not _has_kind(
        {"tables": [{"name": "t", "generate_columns": [{"name": "a"}]}]}, "columns"
    )
    assert not _has_kind({"tables": [{"name": "t", "generate_columns": []}]}, "generate_columns")
    assert not _has_kind(None, "columns")


def _joint_cap(**overrides: object) -> str:
    detail = {
        "columns": ["kid", "parent"],
        "cell_count": 36,
        "cells_kept": 22,
        "cap_dropped": 11,
        "policy_dropped": 3,
        "other_count": 400,
        **overrides,
    }
    return str(warning_record("fit_joint_cells_truncated", detail=detail)["message"])


def test_joint_cap_line_keeps_policy_drops_apart_from_the_cap_advice() -> None:
    line = _joint_cap()
    assert line.startswith("joint kid x parent: 36 combinations, 22 kept; 11 dropped by the cell")
    assert "3 more were left out by the value policy" in line
    assert line.endswith("Raise --joint-max-cells (at most 1000) to keep the 11.")


def test_joint_cap_line_without_policy_drops_says_nothing_of_policy() -> None:
    line = _joint_cap(cells_kept=25, policy_dropped=0, other_count=366)
    assert "value policy" not in line
    assert "366 rows in all fall outside the kept ones" in line
