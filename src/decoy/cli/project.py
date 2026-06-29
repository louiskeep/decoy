"""`decoy project` -- local .decoy/ workspace management (SP-17b).

A `.decoy/` workspace is a LOCAL-ONLY convenience area for storing derived
Decoy artifacts: metadata, scan records, pipeline drafts, and run history.
It is analogous to a `.git/` directory: it anchors a Decoy project to a
directory and provides a home for derived artifacts.

What the project workspace provides (honest framing)
------------------------------------------------------
- `project init`: Create a `.decoy/` workspace in a directory.
  Writes `.decoy/workspace.json` and creates subdirectories for scans,
  runs, evidence, and reports.
- `project show`: Print the resolved workspace config.

What the .decoy/ workspace is NOT
-----------------------------------
- It does NOT sync with the platform server.
- It does NOT track remote state, RBAC, schedules, or platform audit logs.
- It does NOT replace platform governance or managed operations.
- It is a LOCAL convenience workspace only; the platform Web UI remains the
  authoritative store for collaboration, audit, and managed pipelines.
- Deleting `.decoy/` removes derived Decoy artifacts only; it never
  deletes your source data files.

Upward discovery
-----------------
Commands that depend on a workspace search upward from the current working
directory to find a `.decoy/` directory, mirroring how `git` finds `.git/`.
This means `decoy project show` works from any subdirectory inside a Decoy
project. Use `--workspace DIR` to override the search root explicitly.

Workspace layout
-----------------
.decoy/
  workspace.json   -- workspace config (version, defaults, timestamps)
  catalog.duckdb   -- local metadata catalog (created by `decoy catalog`)
  scans/           -- STORM scan artifacts (local diagnostic; may be sensitive)
  runs/            -- run record metadata
  evidence/        -- evidence manifests from local runs
  reports/         -- rendered report artifacts
"""

from __future__ import annotations

import json as _json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success

# Workspace config schema version. Bump when the workspace.json format changes
# in a backward-incompatible way.
_WORKSPACE_VERSION = 1

# Subdirectories created inside .decoy/ on init.
_WORKSPACE_SUBDIRS = ("scans", "runs", "evidence", "reports")

# App definition

project_app = typer.Typer(
    name="project",
    help=(
        "Manage a local .decoy/ workspace. "
        "LOCAL ONLY -- does not sync with the platform server, track remote state, "
        "or replace RBAC, audit logs, or managed operations. "
        "Use `project init` to create a workspace; `project show` to inspect it."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Workspace discovery helpers
# ---------------------------------------------------------------------------


def find_workspace(start: Path | None = None) -> Path | None:
    """Walk upward from `start` (default: cwd) to find a .decoy/ directory.

    Returns the PARENT directory that contains `.decoy/` (i.e. the workspace
    root), or None if no workspace is found before the filesystem root.

    This mirrors how `git` discovers its `.git/` directory so that users can
    run catalog and project commands from any subdirectory inside a project.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / ".decoy"
        if candidate.is_dir() and (candidate / "workspace.json").exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding a workspace.
            return None
        current = parent


def _resolve_workspace(workspace_override: str | None) -> Path | None:
    """Resolve the workspace root from an explicit override or env var, then discovery.

    Priority order:
    1. --workspace flag (explicit; highest priority).
    2. DECOY_WORKSPACE_ROOT env var (CI/scripting convenience).
    3. Upward discovery from cwd.
    """
    if workspace_override:
        return Path(workspace_override).resolve()
    env_root = os.environ.get("DECOY_WORKSPACE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return find_workspace()


def _dotdecoy(workspace_root: Path) -> Path:
    """Return the .decoy/ path inside workspace_root."""
    return workspace_root / ".decoy"


# ---------------------------------------------------------------------------
# project init
# ---------------------------------------------------------------------------

_INIT_EPILOG = """\
Examples:

  decoy project init
    Create a .decoy/ workspace in the current directory.

  decoy project init --workspace /path/to/project
    Create a .decoy/ workspace at an explicit location.

  decoy project init --json
    Emit a structured JSON result.

What init creates:
  .decoy/workspace.json     -- workspace config (version, defaults)
  .decoy/catalog.duckdb     -- created lazily by `decoy catalog` commands
  .decoy/scans/             -- STORM scan artifacts (local; may be sensitive)
  .decoy/runs/              -- run record metadata
  .decoy/evidence/          -- evidence manifests from local runs
  .decoy/reports/           -- rendered report artifacts

What this does NOT do:
  - It does NOT create a platform project, register a workspace server-side,
    or require a platform login.
  - Deleting .decoy/ removes derived Decoy artifacts; it never deletes
    your source data.

See also: decoy project show, decoy catalog list.
"""


@project_app.command(name="init", epilog=_INIT_EPILOG)
def _init(
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help=(
            "Directory to create the .decoy/ workspace in. "
            "Defaults to the current working directory. "
            "Can also be set via the DECOY_WORKSPACE_ROOT environment variable."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Create a local .decoy/ workspace in the current directory.

    The workspace is a LOCAL convenience area for derived Decoy artifacts
    (scan records, run metadata, evidence manifests, rendered reports). It
    does NOT sync with the platform server, track remote state, or replace
    RBAC, audit logs, or managed platform operations.

    Running `project init` a second time in an existing workspace is safe
    (idempotent): it will not overwrite existing config or artifacts.

    Deleting .decoy/ removes derived Decoy artifacts only. It never deletes
    your source data files.
    """
    state = setup_output(json_, quiet, verbose)

    # Resolve workspace root (override flag, env var, or cwd).
    root = Path(workspace).resolve() if workspace else Path(os.environ.get("DECOY_WORKSPACE_ROOT", ".")).resolve()
    dotdecoy = _dotdecoy(root)

    already_exists = dotdecoy.is_dir() and (dotdecoy / "workspace.json").exists()

    # Create .decoy/ and subdirectories.
    dotdecoy.mkdir(parents=True, exist_ok=True)
    for subdir in _WORKSPACE_SUBDIRS:
        (dotdecoy / subdir).mkdir(exist_ok=True)

    # Write workspace.json only if it does not already exist (idempotent).
    ws_json_path = dotdecoy / "workspace.json"
    if not ws_json_path.exists():
        ws_config: dict[str, Any] = {
            "workspace_version": _WORKSPACE_VERSION,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "source_dir": ".",
            "output_dir": "output",
            "recipe_dir": "recipes",
        }
        ws_json_path.write_text(_json.dumps(ws_config, indent=2), encoding="utf-8")

    action = "workspace already exists" if already_exists else "workspace created"

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "project init",
                "status": "ok",
                "action": action,
                "workspace_root": str(root),
                "dotdecoy": str(dotdecoy),
                "subdirs": list(_WORKSPACE_SUBDIRS),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    if already_exists:
        state.console.print(success("OK"), code(str(dotdecoy)), hint("(workspace already exists, no changes made)"))
    else:
        state.console.print(success("OK"), code(str(dotdecoy)), hint("workspace initialized"))
        for subdir in _WORKSPACE_SUBDIRS:
            state.console.print(" ", hint("-"), code(str(dotdecoy / subdir) + "/"))
    state.console.print(
        " ",
        hint("next:"),
        code("decoy project show"),
        hint("to inspect the workspace config"),
    )


# ---------------------------------------------------------------------------
# project show
# ---------------------------------------------------------------------------

_SHOW_EPILOG = """\
Examples:

  decoy project show
    Print the workspace config. Searches upward from cwd for .decoy/.

  decoy project show --workspace /path/to/project
    Show config for an explicit workspace location.

  decoy project show --json
    Emit a structured JSON result.

What show displays:
  - Workspace root path and .decoy/ location.
  - Config defaults (source_dir, output_dir, recipe_dir).
  - Created-at timestamp and workspace version.
  - Presence of catalog.duckdb and artifact subdirectories.

Upward discovery:
  Commands search upward from the current directory to find .decoy/,
  mirroring how git discovers .git/. Use --workspace to override.

See also: decoy project init, decoy catalog list.
"""


@project_app.command(name="show", epilog=_SHOW_EPILOG)
def _show(
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        help=(
            "Workspace root to show. Defaults to upward discovery from cwd. "
            "Can also be set via DECOY_WORKSPACE_ROOT."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit structured JSON instead of a human-readable card.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Print the resolved .decoy/ workspace config.

    Searches upward from the current directory for a .decoy/ workspace,
    mirroring how git discovers .git/. Use --workspace to point at an
    explicit location.

    This is a read-only command. It does not modify the workspace or
    contact the platform.
    """
    state = setup_output(json_, quiet, verbose)

    root = _resolve_workspace(workspace)

    if root is None:
        msg = (
            "No .decoy/ workspace found. "
            "Run `decoy project init` in your project directory first."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "project show", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("hint:"),
                "run",
                code("decoy project init"),
                "to create a workspace in the current directory.",
            )
        raise typer.Exit(code=EXIT_USAGE)

    dotdecoy = _dotdecoy(root)
    ws_json_path = dotdecoy / "workspace.json"

    # Branch on whether .decoy/ exists at all vs. exists but is incomplete.
    if not dotdecoy.is_dir():
        msg = (
            "No .decoy/ workspace found. "
            "Run `decoy project init` in your project directory first."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "project show", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("hint:"),
                "run",
                code("decoy project init"),
                "to create a workspace in the current directory.",
            )
        raise typer.Exit(code=EXIT_USAGE)

    # .decoy/ dir exists but workspace.json is missing -- incomplete init.
    if not ws_json_path.exists():
        msg = f".decoy/ found at {dotdecoy} but workspace.json is missing. Run `decoy project init`."
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "project show", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    ws_config: dict[str, Any] = _json.loads(ws_json_path.read_text(encoding="utf-8"))

    # Build catalog presence flag (catalog.duckdb is created lazily by `catalog`).
    catalog_path = dotdecoy / "catalog.duckdb"
    catalog_present = catalog_path.exists()

    subdir_status = {s: (dotdecoy / s).is_dir() for s in _WORKSPACE_SUBDIRS}

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "project show",
                "status": "ok",
                "workspace_root": str(root),
                "dotdecoy": str(dotdecoy),
                "config": ws_config,
                "catalog_present": catalog_present,
                "subdirs": subdir_status,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable card.
    state.console.print(success("OK"), "decoy project workspace")
    state.console.print(" ", hint("root:"), code(str(root)))
    state.console.print(" ", hint(".decoy/:"), code(str(dotdecoy)))
    state.console.print(
        " ", hint("workspace_version:"), code(str(ws_config.get("workspace_version", "?")))
    )
    state.console.print(
        " ", hint("created_at:"), code(ws_config.get("created_at", "?"))
    )
    state.console.print(
        " ", hint("source_dir:"), code(ws_config.get("source_dir", "."))
    )
    state.console.print(
        " ", hint("output_dir:"), code(ws_config.get("output_dir", "output"))
    )
    state.console.print(
        " ", hint("recipe_dir:"), code(ws_config.get("recipe_dir", "recipes"))
    )
    state.console.print(
        " ", hint("catalog:"),
        code("present") if catalog_present else hint("not created yet (run `decoy catalog` commands)")
    )
    for subdir, present in subdir_status.items():
        glyph = success("v") if present else hint("-")
        state.console.print(" ", glyph, hint(f".decoy/{subdir}/"))
    state.console.print(
        " ",
        hint("note:"),
        "local workspace only -- does not sync with the platform server.",
    )


# Public exports
__all__ = ["find_workspace", "project_app"]
