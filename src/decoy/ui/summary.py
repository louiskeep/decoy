"""Run and report summary renderers: the text `decoy run` and `decoy report fidelity` print.

The three run report sections (`--explain-plan`, `--fidelity`, `--post-validate`), the
`report fidelity` renderer, the per-table lines under the run card and the warning lines both
commands share. `warning_records` builds the list the card and `run --json` both read, and
`warning_lines` renders it, so the two surfaces cannot disagree. Warnings name codes, tables,
columns and numbers only, never a cell value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

import typer

from decoy.ui.output import OutputMode, OutputState, emit_error
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, info, success, warn

SEED_IGNORED_MESSAGE = (
    "global_settings.seed is not used for generated tables when a master key is set; "
    "the key and --key-label decide them. Masked tables still use the seed."
)
FIDELITY_POINTER = (
    "Generated tables are not scored here. Score them with: decoy report fidelity "
    "<source.csv> <synthetic.csv> --generate"
)


def _score(value: object) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "n/a"


def _fidelity_message(table: object, detail: Mapping[str, Any]) -> str:
    threshold = _score(detail.get("threshold"))
    overall = _score(detail.get("overall_score"))
    if detail.get("trigger") == "column":
        below = [(str(n), s) for n, s in detail.get("below_columns") or []]
        if len(below) == 1:
            name, score = below[0]
            return (
                f"table {table}: column {name} scores {_score(score)}, below "
                f"fidelity_warn_threshold {threshold} (overall {overall})"
            )
        named = ", ".join(f"{n} {_score(s)}" for n, s in below)
        return (
            f"table {table}: columns {named} score below "
            f"fidelity_warn_threshold {threshold} (overall {overall})"
        )
    text = f"table {table}: fidelity {overall} is below fidelity_warn_threshold {threshold}"
    worst = detail.get("worst_columns") or []
    if worst:
        text += f"; lowest: {worst[0][0]} {_score(worst[0][1])}"
    return text


def _fact(value: object) -> str:
    """A detail value for the human line. A dict or list prints its size, not its contents,
    because some warnings carry per-row maps; `--json` keeps the full detail."""
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        return f"<{len(value)} entries>"
    return str(value)


def _generic_message(code_: str, table: object, column: object, detail: Mapping[str, Any]) -> str:
    where = ", ".join(
        f"{label} {value}" for label, value in (("table", table), ("column", column)) if value
    )
    head = f"{code_} ({where})" if where else code_
    facts = ", ".join(f"{k}={_fact(v)}" for k, v in detail.items() if k not in ("table", "column"))
    return f"{head}: {facts}" if facts else head


def _joint_cap_message(detail: Mapping[str, Any]) -> str:
    """`fit_joint_cells_truncated`: counts and column names only, never a kept or dropped label."""
    pair = " x ".join(str(c) for c in detail.get("columns") or [])
    cap_dropped = detail.get("cap_dropped", 0)
    policy_dropped = detail.get("policy_dropped", 0)
    text = (
        f"joint {pair}: {detail.get('cell_count')} combinations, {detail.get('cells_kept')} "
        f"kept; {cap_dropped} dropped by the cell cap"
    )
    if policy_dropped:
        text += f", {policy_dropped} more were left out by the value policy"
    text += (
        f", {detail.get('other_count')} rows in all fall outside the kept ones. A parent value "
        "with no kept combination is generated from the child's overall counts."
    )
    if cap_dropped:
        text += f" Raise --joint-max-cells (at most {_max_cells()}) to keep the {cap_dropped}."
    return text


def _max_cells() -> int:
    from decoy_engine.quality.snapshot import MAX_CONTINGENCY_TOP_K

    return MAX_CONTINGENCY_TOP_K


def _parent_unseen_message(table: object, detail: Mapping[str, Any]) -> str:
    """`generation_condition_parent_unseen`: how many rows fell back, never which parent values."""
    # The engine caps how many distinct parent values it counts; past it the number is a floor.
    count = (
        f"at least {detail.get('parent_values')}"
        if detail.get("parent_values_capped")
        else f"one of {detail.get('parent_values')}"
    )
    return (
        f"table {table}, column {detail.get('column')} (condition_on "
        f"{detail.get('condition_on')}): {detail.get('rows')} of {detail.get('rows_total')} rows "
        f"({detail.get('rows_null_parent')} of them with an empty parent) had {count} "
        "parent values with no fitted combination and drew from the column's overall counts."
    )


def warning_record(
    code_: str,
    *,
    table: str | None = None,
    column: str | None = None,
    detail: Mapping[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """One warning as the card and `--json` carry it: code, table, column, message, detail."""
    from decoy_engine.reasons.warning import (
        FIT_JOINT_CELLS_TRUNCATED,
        GENERATION_CONDITION_PARENT_UNSEEN,
        GENERATION_FIDELITY_BELOW_THRESHOLD,
        SEED_IGNORED_WITH_MASTER_KEY,
    )

    detail = dict(detail or {})
    table = table if table is not None else detail.get("table")
    if message is None:
        if code_ == GENERATION_FIDELITY_BELOW_THRESHOLD:
            message = _fidelity_message(table, detail)
        elif code_ == FIT_JOINT_CELLS_TRUNCATED:
            message = _joint_cap_message(detail)
        elif code_ == GENERATION_CONDITION_PARENT_UNSEEN:
            message = _parent_unseen_message(table, detail)
        elif code_ == SEED_IGNORED_WITH_MASTER_KEY:
            message = SEED_IGNORED_MESSAGE
        else:
            message = _generic_message(code_, table, column, detail)
    return {"code": code_, "table": table, "column": column, "message": message, "detail": detail}


def warning_records(
    engine_warnings: Iterable[Any], cli_warnings: Iterable[Mapping[str, Any]] = ()
) -> list[dict[str, Any]]:
    """Engine `QualityWarning` entries then the CLI's own, in one list. Every entry is shown."""
    records = [warning_record(w.code, column=w.column, detail=w.detail) for w in engine_warnings]
    records.extend(
        warning_record(w["code"], **{k: v for k, v in w.items() if k != "code"})
        for w in cli_warnings
    )
    return records


def report_warning_records(report_warnings: Iterable[Any]) -> list[dict[str, Any]]:
    """Turn a quality report's `warnings` into records, one per drifted column for the drifts."""
    records: list[dict[str, Any]] = []
    for w in report_warnings:
        if not isinstance(w, dict):
            continue
        code_ = str(w.get("code", "?"))
        raw_detail = w.get("detail")
        detail: dict[str, Any] = raw_detail if isinstance(raw_detail, dict) else {}
        drifted = [d for d in detail.get("drifted") or [] if isinstance(d, dict)]
        if code_ == "null_drift" and drifted:
            limit = detail.get("threshold_pp")
            for d in drifted:
                text = (
                    f"column {d.get('column')}: {_pct(d.get('source_null_pct'))} empty in the "
                    f"source, {_pct(d.get('output_null_pct'))} in the output "
                    f"(limit {_limit(limit)} points)"
                )
                records.append(warning_record(code_, column=str(d.get("column")), message=text))
        elif code_ == "kind_drift" and drifted:
            for d in drifted:
                text = (
                    f"column {d.get('column')}: {d.get('source_kind')} in the source, "
                    f"{d.get('output_kind')} in the output"
                )
                records.append(warning_record(code_, column=str(d.get("column")), message=text))
        else:
            keys = ", ".join(sorted(str(k) for k in detail))
            text = f"{code_} ({keys})" if keys else code_
            records.append(warning_record(code_, message=text))
    return records


def _pct(value: object) -> str:
    return f"{value:.1f}%" if isinstance(value, (int, float)) else "n/a"


def _limit(value: object) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else "n/a"


def warning_lines(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """One line per warning record, the same sentence on every surface."""
    return [str(r["message"]) for r in records]


def render_warnings(state: Any, records: list[dict[str, Any]]) -> None:
    """Print `Warnings: N` and one line per warning (nothing when there are none)."""
    if not records:
        return
    state.console.print()
    state.console.print(warn("Warnings:"), str(len(records)))
    for line in warning_lines(records):
        # The line quotes table and column names from the config: print it as plain text.
        state.console.print("  ", line, markup=False, highlight=False)


def render_table_lines(state: Any, table_records: list[dict[str, Any]]) -> None:
    """The per-table lines under the run card: table, rows, file."""
    if not table_records:
        return
    state.console.print()
    for rec in table_records:
        rows = rec.get("rows")
        count = "rows n/a" if rows is None else f"{rows} rows"
        where = "no file" if rec.get("path") is None else str(rec["path"])
        # Names and paths come from the config: print them as plain text, never folded.
        state.console.print(
            f"  {rec.get('name', '?')}  {count}  {where}",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )


def render_generated_fidelity_pointer(state: Any) -> None:
    """After a mixed pipeline's mask report: where generated tables get scored."""
    state.console.print(hint("  Note:"), FIDELITY_POINTER)


def render_execution_route(state, execution_plan: dict | None) -> None:
    """Render the EXECUTION ROUTE decision (--explain-plan).

    `execution_plan` is `quality_metrics["execution_plan"]` =
    `{mode, reason, rejections}`: which run lane the engine chose (sequential /
    full_frame / out_of_core) and why. This is deliberately NOT the per-column
    masking rationale `validate compile --explain` renders pre-run (plan P1-1) --
    a different payload, so a small dedicated renderer rather than reusing
    compile_explain's column table. `rejections` maps each lane the engine
    DECLINED to the reason it was declined.
    """
    state.console.print()
    state.console.print(accent("Execution route"))
    if not execution_plan:
        # explain_plan was requested but the engine stamped nothing (e.g. a path
        # that produced no decision). Say so rather than render an empty table.
        state.console.print(hint("  "), "no execution-route decision was recorded for this run.")
        return
    state.console.print("  Mode:", code(str(execution_plan.get("mode", "?"))))
    state.console.print("  Reason:", str(execution_plan.get("reason", "?")))
    rejections = execution_plan.get("rejections") or {}
    if rejections:
        tbl = make_table("Lane declined", "Why")
        for lane, why in rejections.items():
            tbl.add_row(str(lane), str(why))
        state.console.print(tbl)
    state.console.print(
        hint("  Note:"),
        "this is the execution ROUTE decision, not the per-column masking rationale. For that, run",
        code("decoy validate compile --explain"),
        "before the run.",
    )


def render_fidelity(state, fidelity_reports: dict | None) -> None:
    """Render the QUICK inline marginal-fidelity check (--fidelity).

    `fidelity_reports` is `quality_metrics["fidelity_reports"]`, a per-mask-table
    `quality-report/v1` block. This is a quick inline glance (letter grade +
    overall score, marginal-only); it NEVER fails the run. The fuller post-hoc
    grade is `decoy report fidelity` (plan P2-4).
    """
    state.console.print()
    state.console.print(accent("Fidelity (quick inline check)"))
    if not fidelity_reports:
        state.console.print(hint("  "), "no mask-table fidelity report was produced for this run.")
        return
    tbl = make_table("Table", "Grade", "Overall score")
    for table_name, rep in fidelity_reports.items():
        rep = rep or {}
        score = rep.get("overall_score")
        tbl.add_row(
            str(table_name),
            str(rep.get("grade", "?")),
            "n/a" if score is None else f"{score:.3f}",
        )
    state.console.print(tbl)
    state.console.print(
        hint("  Note:"),
        "a quick marginal check; a low grade does not fail the run. For the "
        "fuller post-hoc grade, run",
        code("decoy report fidelity"),
        ".",
    )


def render_post_validation(state, qm: dict, *, enforce: bool) -> None:
    """Render the post-execution validator results (--post-validate[-enforce]).

    Reads `quality_metrics["failed_checks"]` (a list of `{code, message}`) and
    `["quality_summary"]` (the manifest block). Warn-only by default; under
    --post-validate-enforce a non-empty `failed_checks` maps to EXIT_FINDINGS in
    the caller (the engine never fails the job -- plan P1-2).
    """
    state.console.print()
    state.console.print(accent("Post-validation"))
    failed = qm.get("failed_checks") or []
    summary = qm.get("quality_summary")
    if summary is None:
        state.console.print(hint("  "), "no post-validation summary was produced for this run.")
        return
    if not failed:
        state.console.print(success("  All post-validation checks passed."))
        return
    tbl = make_table("Failed check", "Detail")
    for item in failed:
        item = item or {}
        tbl.add_row(str(item.get("code", "?")), str(item.get("message", "")))
    state.console.print(tbl)
    if enforce:
        state.console.print(
            warn("  enforce:"),
            f"{len(failed)} hard-failed check(s); outputs were written, exiting "
            "with findings (code 4).",
        )
    else:
        state.console.print(
            hint("  Note:"),
            f"{len(failed)} hard-failed check(s) reported; warn-only, the run still exits 0. Use",
            code("--post-validate-enforce"),
            "to exit with findings.",
        )


def _rate_text(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.1%}"


def null_rate_pairs(
    report: dict[str, Any], src_df: Any, out_df: Any
) -> dict[str, tuple[float | None, float | None]]:
    """Source and output null rates per column, only when some column's rates differ.

    The report carries `missing_value_similarity` but not the rates behind it, so the two
    frames are profiled again and each rate comes from the engine's `snapshot_null_fraction`.
    Returns an empty map when every column scored 1 (or None), so the common case pays nothing.
    """
    columns = [c for c in report.get("marginal", {}).get("columns", []) if isinstance(c, dict)]
    if not any(
        isinstance(c.get("missing_value_similarity"), (int, float))
        and c["missing_value_similarity"] < 1
        for c in columns
    ):
        return {}
    from decoy_engine import distribution_snapshot_document
    from decoy_engine.quality import snapshot_null_fraction

    # Only the counts are read. The redacting writer is the one snapshot builder the CLI uses.
    src_cols = distribution_snapshot_document(src_df, source_label="source")["columns"]
    out_cols = distribution_snapshot_document(out_df, source_label="output")["columns"]
    return {
        str(c.get("column")): (
            snapshot_null_fraction(src_cols[c["column"]]) if c.get("column") in src_cols else None,
            snapshot_null_fraction(out_cols[c["column"]]) if c.get("column") in out_cols else None,
        )
        for c in columns
    }


def render_fidelity_report(
    state: Any,
    report: dict[str, Any],
    policy_result: dict[str, Any],
    null_rates: Mapping[str, tuple[float | None, float | None]] | None = None,
) -> None:
    """Human-readable rendering of a quality-report/v1 + policy result.

    `null_rates` maps a column to its (source, output) null rate; when given, the marginal
    table gains a nulls column.
    """
    grade = report.get("grade", "unavailable")
    overall = report.get("overall_score")
    overall_str = f"{overall:.3f}" if isinstance(overall, (int, float)) else "n/a"
    verdict = policy_result.get("verdict", "pass")
    violations = policy_result.get("violations", [])

    # The engine's report-mode verdict is always "pass", even with violations
    # (strategy defaults apply with no flags), so a green PASS beside grade F
    # read as approval. Report mode names what it recorded instead.
    if policy_result.get("mode") == "report":
        if violations:
            verdict_text = info(
                f"REPORT ONLY: {len(violations)} threshold violation(s) not enforced "
                "(use --mode fail)"
            )
        else:
            verdict_text = info("REPORT ONLY (no threshold violations)")
    elif verdict == "pass":
        verdict_text = success(verdict.upper())
    elif verdict == "warn":
        verdict_text = warn(verdict.upper())
    else:
        verdict_text = error(verdict.upper())
    state.console.print(verdict_text, f"grade {grade}  overall_score {overall_str}")

    columns = report.get("marginal", {}).get("columns", [])
    if columns:
        headers = ["Column", "Comparable", "Similarity"]
        if null_rates:
            headers.append("Nulls (source/output)")
        table = make_table(*headers, title="Marginal fidelity")
        for col in columns:
            if not isinstance(col, dict):
                continue
            sim = col.get("similarity")
            sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "n/a"
            row = [
                str(col.get("column", "?")),
                "yes" if col.get("comparable") else "no",
                sim_str,
            ]
            if null_rates:
                src_rate, out_rate = null_rates.get(str(col.get("column")), (None, None))
                row.append(f"{_rate_text(src_rate)} / {_rate_text(out_rate)}")
            table.add_row(*row)
        state.console.print(table)

    joints = report.get("pairwise", {}).get("joints", [])
    if joints:
        table = make_table("Joint", "Comparable", "Similarity", title="Pairwise fidelity")
        for j in joints:
            if not isinstance(j, dict):
                continue
            sim = j.get("similarity")
            sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "n/a"
            table.add_row(
                "x".join(j.get("columns", [])),
                "yes" if j.get("comparable") else "no",
                sim_str,
            )
        state.console.print(table)

    render_warnings(state, report_warning_records(report.get("warnings") or []))

    if violations:
        table = make_table("Check", "Column", "Expected", "Actual", title="Policy violations")
        for v in violations:
            table.add_row(
                str(v.get("check", "?")),
                str(v.get("column", "-")),
                str(v.get("expected", "-")),
                str(v.get("actual", "-")),
            )
        state.console.print(table)
    elif verdict == "pass":
        state.console.print(success("OK"), "no policy violations.")


class _ReportView(Protocol):
    """What `announce_report` reads of a report target (`decoy.cli.io.ReportTarget`)."""

    path: Path | None
    implicit: bool
    warning: _Fixed | None
    error: str | None
    exit_code: int


class _Fixed(Protocol):
    code: str
    message: str


def announce_report(state: OutputState, target: _ReportView) -> Path | None:
    """Say how a report write ended; return the default path written, else None.

    A typed path that failed is refused (`error:` and exit 1). A default that failed gets a fixed,
    value-free warning on stderr (never under `--quiet`) and the command goes on. A default that
    was written is named in default mode only; a typed path is not announced.
    """
    if target.error is not None:
        emit_error(state, "report", target.error)
        raise typer.Exit(code=target.exit_code)
    if target.warning is not None:
        if state.mode is not OutputMode.quiet:
            line = f"{target.warning.code}: {target.warning.message}"
            state.err_console.print(warn("warning:"), line, markup=False)
        return None
    if not target.implicit or target.path is None:
        return None
    if state.mode is OutputMode.default:
        state.console.print("Report:", target.path, markup=False, soft_wrap=True)
    return target.path
