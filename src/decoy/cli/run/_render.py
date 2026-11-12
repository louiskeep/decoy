"""The success tail of `decoy run`: JSON payload, summary card, report sections and the
`--post-validate-enforce` exit."""

from pathlib import Path

import typer
from rich.text import Text

from decoy.cli import gen
from decoy.cli.exit_codes import EXIT_FINDINGS
from decoy.cli.io import shown_path
from decoy.cli.run._context import Mode, RunContext
from decoy.cli.run._prepare import _has_kind
from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json
from decoy.ui.summary import (
    render_execution_route,
    render_fidelity,
    render_generated_fidelity_pointer,
    render_post_validation,
    render_table_lines,
    render_warnings,
    warning_records,
)
from decoy.ui.theme import warn


def _seed_warnings(raw_cfg: dict | None, *, key_in_effect: bool) -> list[dict]:
    """The `seed_ignored_with_master_key` warning: a key is set, the YAML sets a seed and the
    config has a generate table, where the key and `--key-label` decide the output instead."""
    from decoy_engine.reasons.warning import SEED_IGNORED_WITH_MASTER_KEY

    if not (key_in_effect and _has_kind(raw_cfg, "generate_columns")):
        return []
    settings = raw_cfg.get("global_settings") if isinstance(raw_cfg, dict) else None
    if not isinstance(settings, dict) or settings.get("seed") is None:
        return []
    return [{"code": SEED_IGNORED_WITH_MASTER_KEY}]


def _next_hint_for_run(raw_cfg: dict | None, mode: "Mode") -> str | None:
    """Best-effort follow-up hint based on the YAML's output path."""
    try:
        out = raw_cfg.get("output", {}).get("path") if isinstance(raw_cfg, dict) else None
        if out:
            return f"head {out}"
    except Exception:
        pass
    return None


def commit_latest(ctx: RunContext) -> None:
    """Move `LATEST` and `current` to this run when the run will exit 0, and warn if it could not."""
    if ctx.layout is None:
        return
    if ctx.post_validate_enforce and (ctx._report_quality_metrics or {}).get("failed_checks"):
        return
    for item in ctx.layout.commit_latest():
        if ctx.state.mode is not OutputMode.quiet:
            ctx.state.err_console.print(warn("warning:"), Text(f"{item.code}: {item.message}"))


def _where_written(ctx: RunContext) -> dict:
    """The plan 7.6 `--json` members: the ledger's files and folder, project and pipeline."""
    described = (
        ctx.layout.describe() if ctx.layout is not None else {"project": None, "pipeline": None}
    )
    return {**ctx.published_members(), **described}


def finish(ctx: RunContext) -> None:
    """Render the success result and apply the `--post-validate-enforce` exit mapping."""
    # S5 enforce mapping (plan P1-2): the engine never fails the job on a
    # hard-failed validator check -- it only stamps `failed_checks`. The CLI
    # maps a non-empty `failed_checks` under --post-validate-enforce to
    # EXIT_FINDINGS, AFTER the requested sections render and the outputs /
    # evidence are already written. --post-validate (without enforce) is
    # warn-only and leaves the exit code at 0.
    _qm = ctx._report_quality_metrics or {}
    _warnings = warning_records(
        ctx._ev_engine_warnings,
        [*_seed_warnings(ctx.raw_cfg, key_in_effect=ctx.resolver is not None), *ctx._cli_warnings],
    )
    _enforce_fires = bool(ctx.post_validate_enforce and _qm.get("failed_checks"))

    if ctx.state.mode is OutputMode.json:
        payload: dict = {
            "command": "run",
            "status": "ok",
            "config": ctx.config_str,
            "mode": ctx.yaml_mode,
            "elapsed_s": round(ctx.elapsed, 3),
            "tables": ctx._table_records,
            "warnings": _warnings,
            **_where_written(ctx),
        }
        payload["resources"] = ctx._resources_record
        if ctx.notify_channels:
            payload["notify"] = ctx.notify_results
        if ctx._native_route is not None:
            payload["native_route"] = {
                "applicable": ctx._native_route.applicable,
                "state": ctx._native_route.state,
                "label": ctx._native_route.label,
            }
        if ctx._report_flags:
            report: dict = {}
            if ctx.explain_plan:
                report["execution_plan"] = _qm.get("execution_plan")
            if ctx.fidelity:
                report["fidelity_reports"] = _qm.get("fidelity_reports")
            if ctx.post_validation:
                report["failed_checks"] = _qm.get("failed_checks")
                report["quality_summary"] = _qm.get("quality_summary")
                report["post_validation_enforce"] = ctx.post_validate_enforce
            payload["report"] = report
        emit_json(ctx.state, payload)
        if _enforce_fires:
            raise typer.Exit(code=EXIT_FINDINGS)
        return

    if ctx.state.mode is OutputMode.quiet:
        if _enforce_fires:
            raise typer.Exit(code=EXIT_FINDINGS)
        return

    facts = [
        ("Pipeline", ctx.config.name),
        ("Mode", ctx.yaml_mode),
        ("Elapsed", f"{ctx.elapsed:.2f}s"),
        ("Tables", str(len(ctx._table_records))),
        (
            "Rows",
            "n/a (chunked)" if ctx.chunked else str(sum(r["rows"] for r in ctx._table_records)),
        ),
        ("Files", str(sum(1 for r in ctx._table_records if r["path"] is not None))),
    ]
    if ctx.layout is not None:
        facts.extend(ctx.layout.summary_facts())
    if _warnings:
        facts.append(("Warnings", str(len(_warnings))))
    if ctx._native_route is not None:
        facts.append(("Route", ctx._native_route.label))
    if ctx.notify_channels:
        delivered = sum(1 for r in ctx.notify_results if r["delivered"])
        facts.append(("Notify", f"{delivered}/{len(ctx.notify_results)} delivered"))

    render_card(
        ctx.state,
        command="decoy run",
        facts=facts,
        next_hint=_next_hint_for_run(ctx.raw_cfg, ctx.mode),
        status="ok",
    )

    # S5 report sections (human mode). Rendered below the summary card so the
    # card stays the one-glance result; each is report-only and reads the
    # captured quality metrics.
    render_table_lines(
        ctx.state,
        [
            {**r, "path": shown_path(Path(r["path"]).resolve()) if r["path"] else None}
            for r in ctx._table_records
        ],
    )
    render_warnings(ctx.state, _warnings)
    if ctx.explain_plan:
        render_execution_route(ctx.state, _qm.get("execution_plan"))
    if ctx.fidelity:
        render_fidelity(ctx.state, _qm.get("fidelity_reports"))
        if _has_kind(ctx.raw_cfg, "generate_columns"):
            render_generated_fidelity_pointer(ctx.state)
    if ctx.post_validation:
        render_post_validation(ctx.state, _qm, enforce=ctx.post_validate_enforce)

    if _enforce_fires:
        raise typer.Exit(code=EXIT_FINDINGS)


def finish_preview(ctx: RunContext) -> None:
    """Render a `--rows` preview: the sampled rows (or the `--json` payload) and the warnings."""
    warnings = warning_records(
        ctx._ev_engine_warnings,
        _seed_warnings(ctx.raw_cfg, key_in_effect=ctx.resolver is not None),
    )
    if ctx.state.mode is OutputMode.json:
        emit_json(
            ctx.state,
            {
                "command": "run",
                "status": "ok",
                "preview": True,
                "config": ctx.config_str,
                "tables": ctx._preview_tables,
                "warnings": warnings,
            },
        )
        return
    gen.render_preview(ctx.state, ctx._preview_tables)
    if ctx.state.mode is not OutputMode.quiet:
        render_warnings(ctx.state, warnings)
