"""`decoy jobs` -- LOCAL run history from the DuckDB catalog (SP-18b).

Reads from .decoy/catalog.duckdb entries with entry_type='run'. Run entries are
written by `decoy run` when a .decoy/ workspace exists upward from the working
directory. If no workspace is initialized, no history is recorded.

LOCAL ONLY. This command does not connect to the platform server, reflect
remote job state, or track platform-managed schedules or audit logs.
There is no `decoy platform` command group -- remote job monitoring is a
platform-service concern (see the platform web UI / API), not this CLI.

Watch honesty note
-------------------
`jobs watch <run-id>`: local CLI runs are SYNCHRONOUS. `decoy run` blocks until
the run is complete before returning. A run entry is only written to the catalog
AFTER the run finishes, so by the time any run appears in the catalog it is
already done. `watch` is honest about this: it shows the completed run status
and explains that live watching is not applicable to synchronous local runs.

If you want to monitor a run while it is happening, re-run it in the foreground:
the spinner in `decoy run` shows live progress. There is no background-job
mechanism in local CLI mode.
"""

from __future__ import annotations

from typing import Any

import typer

from decoy.cli.catalog import _catalog_db, _require_workspace, _row_to_dict
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success

jobs_app = typer.Typer(
    name="jobs",
    help=(
        "LOCAL run history from the DuckDB catalog. "
        "Shows runs recorded by `decoy run` when a .decoy/ workspace exists. "
        "LOCAL ONLY -- does not connect to the platform server or reflect remote job state. "
        "Use `decoy project init` to create a workspace before using jobs commands."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _entry_to_run_dict(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten a catalog entry dict into a run summary dict."""
    meta = entry.get("metadata") or {}
    return {
        "id": entry["id"],
        "name": entry["name"],
        "status": meta.get("status", "unknown"),
        "mode": meta.get("mode", "unknown"),
        "run_timestamp": meta.get("run_timestamp") or entry.get("recorded_at", ""),
        "elapsed_s": meta.get("elapsed_s"),
        "config_path": meta.get("config_path"),
        "evidence_path": meta.get("evidence_path"),
        "engine_version": meta.get("engine_version"),
        "cli_version": meta.get("cli_version"),
        "run_id": meta.get("run_id"),
        "recorded_at": entry.get("recorded_at", ""),
        "sensitivity_class": entry.get("sensitivity_class", "evidence-safe"),
    }


def _lookup_run(
    run_id_arg: str,
    conn: Any,
    command: str,
    state: Any,
) -> dict[str, Any]:
    """Look up a single run catalog entry by id or prefix. Exits on error."""
    if len(run_id_arg) < 4:
        msg = "Run id prefix must be at least 4 characters."
        if state.mode is OutputMode.json:
            emit_json(state, {"command": command, "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    rows = conn.execute(
        "SELECT id, entry_type, name, path, recorded_at, metadata, sensitivity_class "
        "FROM entries WHERE entry_type = 'run' AND (id = ? OR id LIKE ?)",
        [run_id_arg, run_id_arg + "%"],
    ).fetchall()

    if not rows:
        msg = f"No run found for id {run_id_arg!r}."
        if state.mode is OutputMode.json:
            emit_json(state, {"command": command, "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ", hint("hint:"), "run", code("decoy jobs list"), "to see available run ids."
            )
        raise typer.Exit(code=EXIT_USAGE)

    if len(rows) > 1:
        msg = (
            f"Ambiguous id prefix {run_id_arg!r}: matches {len(rows)} runs. "
            "Provide a longer prefix."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": command, "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    return _row_to_dict(rows[0])


# ---------------------------------------------------------------------------
# jobs list
# ---------------------------------------------------------------------------

_LIST_EPILOG = """\
Examples:

  decoy jobs list
    List local runs from the catalog (most-recent first). Searches upward
    from cwd for .decoy/.

  decoy jobs list --json
    Emit structured JSON with a `runs` array.

  decoy jobs list --workspace /path/to/project
    List runs for an explicit workspace.

LOCAL ONLY: shows runs recorded by `decoy run` in this local workspace.
No platform job history, schedules, or remote state is included.
Use `decoy project init` to create a workspace if you haven't already.

See also: decoy jobs show, decoy jobs watch, decoy project init.
"""


@jobs_app.command(name="list", epilog=_LIST_EPILOG)
def _list(
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help="Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit structured JSON on stdout."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
) -> None:
    """List local runs from the catalog, most-recent first.

    Runs are recorded by `decoy run` when a .decoy/ workspace exists. Entries
    have entry_type='run' in the DuckDB catalog.

    LOCAL ONLY: does not connect to the platform server or reflect remote state.
    """
    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "jobs list", state)

    with _catalog_db(root, "jobs list", state) as conn:
        rows = conn.execute(
            "SELECT id, entry_type, name, path, recorded_at, metadata, sensitivity_class "
            "FROM entries WHERE entry_type = 'run' ORDER BY recorded_at DESC"
        ).fetchall()

    entries = [_row_to_dict(r) for r in rows]
    runs = [_entry_to_run_dict(e) for e in entries]

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "jobs list",
                "status": "ok",
                "workspace_root": str(root),
                "count": len(runs),
                "runs": runs,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    if not runs:
        state.console.print(
            hint("no runs recorded."),
            "Run a pipeline with",
            code("decoy run pipeline.yaml"),
            "in a project with a .decoy/ workspace.",
        )
        return

    state.console.print(success("local runs"), hint(f"({len(runs)} total, most-recent first)"))
    for r in runs:
        status_str = r.get("status") or "unknown"
        ts = (r.get("run_timestamp") or r.get("recorded_at") or "")[:19]
        state.console.print(
            " ",
            code(r["id"][:8] + "..."),
            hint(status_str),
            code(r["name"]),
            hint(ts),
        )


# ---------------------------------------------------------------------------
# jobs show
# ---------------------------------------------------------------------------

_SHOW_EPILOG = """\
Examples:

  decoy jobs show <run-id>
    Show full metadata for a local run (prefix match supported).

  decoy jobs show <run-id> --json
    Emit structured JSON for the run.

LOCAL ONLY: shows local run metadata from the DuckDB catalog.

See also: decoy jobs list, decoy report show <run-id>.
"""


@jobs_app.command(name="show", epilog=_SHOW_EPILOG)
def _show(
    run_id: str = typer.Argument(
        ...,
        help="Run catalog id (or prefix, min 4 chars).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit structured JSON on stdout."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help="Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.",
    ),
) -> None:
    """Show full metadata for a local run entry.

    The run id can be the full UUID or a prefix (at least 4 characters).
    Use `decoy jobs list` to see all run ids.

    LOCAL ONLY: reads from the local DuckDB catalog. Does not connect to
    the platform server.
    """
    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "jobs show", state)

    with _catalog_db(root, "jobs show", state) as conn:
        entry = _lookup_run(run_id, conn, "jobs show", state)

    run = _entry_to_run_dict(entry)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "jobs show",
                "status": "ok",
                "workspace_root": str(root),
                "run": run,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    status_str = run.get("status") or "unknown"
    state.console.print(success("run"), code(run["id"]))
    state.console.print(" ", hint("name:"), code(run["name"]))
    state.console.print(" ", hint("status:"), code(status_str))
    state.console.print(" ", hint("mode:"), code(run.get("mode") or "unknown"))
    state.console.print(
        " ", hint("timestamp:"), code(run.get("run_timestamp") or run.get("recorded_at") or "(none)")
    )
    if run.get("elapsed_s") is not None:
        state.console.print(" ", hint("elapsed:"), code(f"{run['elapsed_s']:.2f}s"))
    if run.get("config_path"):
        state.console.print(" ", hint("config:"), code(run["config_path"]))
    if run.get("evidence_path"):
        state.console.print(" ", hint("evidence:"), code(run["evidence_path"]))
    if run.get("run_id"):
        state.console.print(" ", hint("run_id:"), code(run["run_id"]))
    if run.get("engine_version"):
        state.console.print(" ", hint("engine:"), code(run["engine_version"]))
    if run.get("cli_version"):
        state.console.print(" ", hint("cli:"), code(run["cli_version"]))


# ---------------------------------------------------------------------------
# jobs watch
# ---------------------------------------------------------------------------

_WATCH_EPILOG = """\
Examples:

  decoy jobs watch <run-id>
    Show the status of a local run. If the run is complete, prints its status.

Honesty note -- local CLI runs are SYNCHRONOUS:
  `decoy run` blocks until the run is done before returning. A run entry is
  only written to the catalog AFTER the run finishes, so every run in the
  catalog is already complete by the time you can `watch` it.

  This command shows the recorded completed status. It does NOT stream live
  progress for an in-progress run, because local CLI runs have no background
  mechanism that would allow that.

  There is no `decoy platform` command group. Remote/async job monitoring
  is a platform-service concern, outside this CLI's local-only scope.

  To watch a run while it is happening, run it in the foreground:
    decoy run pipeline.yaml
  The spinner shows live progress.

See also: decoy jobs list, decoy jobs show, decoy run.
"""


@jobs_app.command(name="watch", epilog=_WATCH_EPILOG)
def _watch(
    run_id: str = typer.Argument(
        ...,
        help="Run catalog id (or prefix, min 4 chars).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit structured JSON on stdout."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug-level logs."),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help="Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.",
    ),
) -> None:
    """Show status of a local run (always complete -- local runs are synchronous).

    LOCAL CLI RUNS ARE SYNCHRONOUS. A run entry only appears in the catalog
    after `decoy run` has already finished. This command shows the recorded
    completed status.

    For live progress during a run, use `decoy run pipeline.yaml` in the
    foreground -- the spinner shows progress. There is no `decoy platform`
    command group; remote job monitoring is a platform-service concern.
    """
    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "jobs watch", state)

    with _catalog_db(root, "jobs watch", state) as conn:
        entry = _lookup_run(run_id, conn, "jobs watch", state)

    run = _entry_to_run_dict(entry)
    status_str = run.get("status") or "unknown"

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "jobs watch",
                "status": "ok",
                "workspace_root": str(root),
                "run_status": status_str,
                "already_complete": True,
                "note": (
                    "Local CLI runs are synchronous. This run is already complete. "
                    "There is no `decoy platform` command group; remote job "
                    "monitoring is a platform-service concern."
                ),
                "run": run,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    ts = (run.get("run_timestamp") or run.get("recorded_at") or "")[:19]
    state.console.print(
        success("run complete"),
        code(run["id"][:8] + "..."),
        hint(f"status: {status_str}"),
        hint(ts),
    )
    state.console.print(
        " ",
        hint("note:"),
        "local CLI runs are synchronous -- this run finished before its catalog entry was written.",
    )
    state.console.print(
        " ",
        hint("for live progress, run in the foreground:"),
        code("decoy run pipeline.yaml"),
    )
    if run.get("evidence_path"):
        state.console.print(
            " ",
            hint("evidence at:"),
            code(run["evidence_path"]),
            hint("(use `decoy report show` to render)"),
        )


# Public exports
__all__ = ["jobs_app"]
