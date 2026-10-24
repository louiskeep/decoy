"""`decoy status` -- active and recent local runs (parity C4).

Reads the run records `decoy run` writes under `$DECOY_HOME/runs` (see
`decoy.runs`). A `running` record whose process is gone or whose heartbeat
expired shows as `stale`; the CLI never guesses that a stale run succeeded.
Read-only: it starts, stops and cancels nothing.
"""

from __future__ import annotations

import time
from typing import Optional

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import error, hint

STATUS_EPILOG = """Examples:

  decoy status
    Active and recent local runs, newest first.

  decoy status 20261024T120000-1a2b3c
    One run in detail: phase, rows, route, exit code, record directory.

  decoy status --follow
    Re-render every second until no run is active (Ctrl-C to stop).

  decoy status --json
    The same as a JSON list, for scripts.

See also: decoy run --progress jsonl, decoy explain progress.
"""


def _row(rec) -> dict:
    st = rec.status
    return {
        "run_id": st.run_id,
        "state": rec.effective_state(),
        "phase": st.phase,
        "table": st.table,
        "rows_done": st.rows_done,
        "rows_per_sec": None if st.rows_per_sec is None else round(st.rows_per_sec, 1),
        "tables_done": st.tables_done,
        "route": st.route,
        "lane": st.lane,
        "mode": st.mode,
        "config": st.config,
        "pid": st.pid,
        "started_at": st.started_at,
        "updated_at": st.updated_at,
        "finished_at": st.finished_at,
        "exit_code": st.exit_code,
        "error_class": st.error_class,
        "record_dir": str(rec.dir),
    }


def _render_list(state, rows: list[dict]) -> None:
    if not rows:
        state.console.print(hint("no local runs recorded yet; `decoy run` writes one per run."))
        return
    tbl = make_table("Run id", "State", "Phase", "Table", "Rows", "Rows/s", "Mode", "Config")
    for r in rows:
        tbl.add_row(
            r["run_id"],
            r["state"],
            r["phase"] or "",
            r["table"] or "",
            f"{r['rows_done']:,}",
            "" if r["rows_per_sec"] is None else f"{r['rows_per_sec']:,.0f}",
            r["mode"],
            r["config"],
        )
    state.console.print(tbl)


def _render_detail(state, r: dict) -> None:
    tbl = make_table("Field", "Value")
    for key in (
        "run_id", "state", "mode", "config", "phase", "table", "rows_done", "rows_per_sec",
        "tables_done", "route", "lane", "pid", "started_at", "updated_at", "finished_at",
        "exit_code", "error_class", "record_dir",
    ):
        value = r.get(key)
        tbl.add_row(key, "" if value is None else str(value))
    state.console.print(tbl)


def status_command(
    run_id: Optional[str] = typer.Argument(None, help="Show one run in detail."),
    json_: bool = typer.Option(False, "--json", help="Emit JSON on stdout."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout; exit code carries the answer."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug-level CLI logs on stderr."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Re-render every second while any run is active."),
    limit: int = typer.Option(20, "--limit", help="How many recent runs to list.", min=1),
    active: bool = typer.Option(False, "--active", help="List only running (or stale) runs."),
) -> None:
    """Show active and recent local runs recorded by `decoy run`."""
    state = setup_output(json_, quiet, verbose)
    from decoy import runs as _runs

    def snapshot() -> list[dict]:
        if run_id is not None:
            rec = _runs.find_run(run_id)
            return [_row(rec)] if rec is not None else []
        rows = [_row(r) for r in _runs.list_runs(limit=limit)]
        if active:
            rows = [r for r in rows if r["state"] in ("running", "stale")]
        return rows

    rows = snapshot()
    if run_id is not None and not rows:
        msg = f"no run record named {run_id!r} under {_runs.runs_root()}"
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "status", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    if follow and state.mode is OutputMode.default:
        from rich.live import Live

        def table_for(rows: list[dict]):
            tbl = make_table("Run id", "State", "Phase", "Table", "Rows", "Rows/s", "Mode", "Config")
            for r in rows:
                tbl.add_row(r["run_id"], r["state"], r["phase"] or "", r["table"] or "", f"{r['rows_done']:,}",
                            "" if r["rows_per_sec"] is None else f"{r['rows_per_sec']:,.0f}", r["mode"], r["config"])
            return tbl

        try:
            with Live(table_for(rows), console=state.console, refresh_per_second=4) as live:
                while any(r["state"] == "running" for r in rows):
                    time.sleep(1.0)
                    rows = snapshot()
                    live.update(table_for(rows))
        except KeyboardInterrupt:
            pass
        return

    if state.mode is OutputMode.json:
        emit_json(state, {"command": "status", "status": "ok", "runs": rows})
        return
    if state.mode is OutputMode.quiet:
        return
    if run_id is not None:
        _render_detail(state, rows[0])
    else:
        _render_list(state, rows)
