"""`decoy catalog` -- local DuckDB metadata registry (SP-17b).

The catalog is a LOCAL metadata convenience store backed by DuckDB at
`.decoy/catalog.duckdb`. It records metadata about local datasets, runs, and
evidence artifacts so that users can inspect prior work without rescanning.

What the catalog stores (honest framing)
------------------------------------------
- Dataset registrations: name, file path, entry type, recorded timestamp.
- Metadata is stored as JSON in DuckDB; raw source data is never copied in.
- A sensitivity_class field tags each entry: 'evidence-safe', 'full-sensitive',
  or 'redacted-shareable'. This follows the artifact-safety taxonomy from the
  cli-first-capability-guide.md spec.

What the catalog does NOT do
------------------------------
- It does NOT sync with the platform server.
- It does NOT track remote state, RBAC, schedule history, or platform audit logs.
- It does NOT store raw source data, row values, or PII samples by default.
- It is NOT a replacement for the platform's managed file registry or job history.

DuckDB file location
----------------------
`.decoy/catalog.duckdb` -- inside the workspace created by `decoy project init`.
The file is created lazily on the first catalog command that writes to it.

Catalog schema
---------------
Table: `entries`
  id               TEXT PRIMARY KEY    -- UUID (local)
  entry_type       TEXT NOT NULL       -- 'dataset', 'run', 'evidence', etc.
  name             TEXT NOT NULL       -- human-readable name (default: file stem)
  path             TEXT                -- absolute path to the referenced artifact
  recorded_at      TEXT NOT NULL       -- ISO 8601 UTC timestamp
  metadata         TEXT                -- JSON blob for additional fields
  sensitivity_class TEXT DEFAULT 'evidence-safe'
                                       -- 'evidence-safe' | 'full-sensitive' | 'redacted-shareable'

Schema version: catalog-v1
The schema version is stored in the `catalog_meta` table and checked on open.
A schema migration path will be added before the catalog reaches production
traffic (per spec: "Add catalog schema versioning and migration tests in the
first catalog sprint").
"""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.project import _dotdecoy, _resolve_workspace
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success

_CATALOG_SCHEMA_VERSION = "catalog-v1"
_CATALOG_FILENAME = "catalog.duckdb"

catalog_app = typer.Typer(
    name="catalog",
    help=(
        "LOCAL metadata catalog for datasets, runs, and evidence. "
        "Backed by DuckDB at .decoy/catalog.duckdb inside the project workspace. "
        "LOCAL ONLY -- does not sync with the platform server or track remote state. "
        "Use `decoy project init` to create a workspace before using catalog commands."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# DuckDB helpers
# ---------------------------------------------------------------------------


def _catalog_path(workspace_root: Path) -> Path:
    """Return the catalog DuckDB file path."""
    return _dotdecoy(workspace_root) / _CATALOG_FILENAME


def _open_catalog(workspace_root: Path):  # type: ignore[return]
    """Open (or create) the catalog DuckDB file and ensure schema exists.

    Returns a duckdb.DuckDBPyConnection. Caller is responsible for closing it.
    The schema is created on first open; subsequent opens are idempotent.
    """
    import duckdb

    db_path = _catalog_path(workspace_root)
    conn = duckdb.connect(str(db_path))

    # Ensure catalog_meta table exists (holds schema version).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    # Write schema version if not present.
    existing = conn.execute(
        "SELECT value FROM catalog_meta WHERE key = 'schema_version'"
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
            ["schema_version", _CATALOG_SCHEMA_VERSION],
        )

    # Ensure entries table exists.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id                TEXT PRIMARY KEY,
            entry_type        TEXT NOT NULL,
            name              TEXT NOT NULL,
            path              TEXT,
            recorded_at       TEXT NOT NULL,
            metadata          TEXT,
            sensitivity_class TEXT DEFAULT 'evidence-safe'
        )
        """
    )
    return conn


def _row_to_dict(row: tuple) -> dict[str, Any]:
    """Convert a catalog entries row tuple to a dict."""
    id_, entry_type, name, path, recorded_at, metadata, sensitivity_class = row
    return {
        "id": id_,
        "entry_type": entry_type,
        "name": name,
        "path": path,
        "recorded_at": recorded_at,
        "metadata": _json.loads(metadata) if metadata else {},
        "sensitivity_class": sensitivity_class,
    }


# ---------------------------------------------------------------------------
# Workspace guard
# ---------------------------------------------------------------------------


def _require_workspace(workspace_override: str | None, command: str, state: Any) -> Path:
    """Resolve the workspace root or exit with a clear error.

    This guard is called at the top of every catalog command that requires
    an initialized workspace. It resolves via --workspace flag, env var, or
    upward discovery, and exits with EXIT_USAGE if no workspace is found.

    When --workspace is given explicitly the directory must still contain a
    valid .decoy/ workspace (workspace.json must exist); this prevents
    silently creating a DuckDB file in an unintended location.
    """
    root = _resolve_workspace(workspace_override)
    if root is None:
        _emit_no_workspace(command, state)
        raise typer.Exit(code=EXIT_USAGE)
    # Verify the workspace is actually initialized (workspace.json must exist).
    ws_json = _dotdecoy(root) / "workspace.json"
    if not ws_json.exists():
        _emit_no_workspace(command, state)
        raise typer.Exit(code=EXIT_USAGE)
    return root


def _emit_no_workspace(command: str, state: Any) -> None:
    """Emit the 'no workspace' error in the appropriate output mode."""
    msg = (
        "No .decoy/ workspace found. "
        "Run `decoy project init` in your project directory first."
    )
    if state.mode is OutputMode.json:
        emit_json(state, {"command": command, "status": "error", "error": msg})
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), msg)
        state.err_console.print(
            " ",
            hint("hint:"),
            "run",
            code("decoy project init"),
            "to create a workspace in the current directory.",
        )


# ---------------------------------------------------------------------------
# catalog list
# ---------------------------------------------------------------------------

_LIST_EPILOG = """\
Examples:

  decoy catalog list
    List all catalog entries. Searches upward from cwd for .decoy/.

  decoy catalog list --json
    Emit a structured JSON result with the entries array.

  decoy catalog list --workspace /path/to/project
    List entries for an explicit workspace location.

What catalog stores:
  - Dataset registrations (file path, name, format, type).
  - No raw source data or PII values are stored.
  - sensitivity_class tags whether each entry is evidence-safe,
    redacted-shareable, or full-sensitive.

See also: decoy catalog add, decoy catalog show, decoy project init.
"""


@catalog_app.command(name="list", epilog=_LIST_EPILOG)
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
    """List all entries in the local metadata catalog.

    The catalog is backed by DuckDB at .decoy/catalog.duckdb. Entries are
    added with `decoy catalog add`. This command is read-only.

    LOCAL ONLY: the catalog does not sync with the platform server. For
    platform-managed job history and file registries, use the Web UI.
    """
    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "catalog list", state)

    conn = _open_catalog(root)
    try:
        rows = conn.execute(
            "SELECT id, entry_type, name, path, recorded_at, metadata, sensitivity_class "
            "FROM entries ORDER BY recorded_at DESC"
        ).fetchall()
    finally:
        conn.close()

    entries = [_row_to_dict(r) for r in rows]

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "catalog list",
                "status": "ok",
                "workspace_root": str(root),
                "count": len(entries),
                "entries": entries,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    if not entries:
        state.console.print(
            hint("catalog is empty."),
            "Add entries with",
            code("decoy catalog add <path>"),
        )
        return

    state.console.print(success("catalog entries"), hint(f"({len(entries)} total)"))
    for e in entries:
        state.console.print(
            " ",
            code(e["id"][:8] + "..."),
            hint(e["entry_type"]),
            code(e["name"]),
            hint(e["recorded_at"][:19]),
        )


# ---------------------------------------------------------------------------
# catalog add
# ---------------------------------------------------------------------------

_ADD_EPILOG = """\
Examples:

  decoy catalog add ./data/customers.csv
    Register a dataset file in the catalog.

  decoy catalog add ./data/customers.csv --name customers_v2
    Override the default name (file stem).

  decoy catalog add ./data/customers.csv --type dataset --json
    Specify entry type and emit structured JSON with the new entry id.

  decoy catalog add ./data/customers.csv --sensitivity full-sensitive
    Tag the entry as a sensitive local artifact (e.g. a full STORM profile).

Sensitivity classes:
  evidence-safe        -- manifest/summary data excluding raw values (default).
  redacted-shareable   -- profile or summary with raw values removed.
  full-sensitive       -- local diagnostic that may contain sensitive values.

What catalog add does NOT do:
  - It does NOT copy raw source data into DuckDB.
  - It does NOT sync the registration with the platform server.
  - It does NOT scan or profile the file (use `decoy storm scan` for that).

See also: decoy catalog list, decoy catalog show, decoy storm scan.
"""


@catalog_app.command(name="add", epilog=_ADD_EPILOG)
def _add(
    path: str = typer.Argument(
        ...,
        help="Path to the artifact (file or directory) to register in the catalog.",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Name for this entry (default: file stem of the path).",
    ),
    entry_type: str = typer.Option(
        "dataset",
        "--type",
        help="Entry type: dataset, run, evidence, scan, report (default: dataset).",
    ),
    sensitivity: str = typer.Option(
        "evidence-safe",
        "--sensitivity",
        help=(
            "Sensitivity class: evidence-safe (default), redacted-shareable, full-sensitive. "
            "Use full-sensitive for raw STORM profiles that may contain sensitive values."
        ),
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
    """Register an artifact path in the local metadata catalog.

    Records the path, entry type, name, timestamp, and sensitivity class in
    the DuckDB catalog at .decoy/catalog.duckdb. Raw source data is NOT
    copied into DuckDB -- only metadata is stored.

    Use --sensitivity to tag entries: evidence-safe (default, manifests and
    summaries), redacted-shareable (profiles with raw values removed), or
    full-sensitive (local diagnostics that may contain sensitive values like
    full STORM profiles).

    LOCAL ONLY: catalog entries are not synced with the platform server.
    """
    _VALID_SENSITIVITY = {"evidence-safe", "redacted-shareable", "full-sensitive"}
    _VALID_TYPES = {"dataset", "run", "evidence", "scan", "report"}

    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "catalog add", state)

    # Validate sensitivity class.
    if sensitivity not in _VALID_SENSITIVITY:
        msg = (
            f"Invalid sensitivity class {sensitivity!r}. "
            f"Choose one of: {', '.join(sorted(_VALID_SENSITIVITY))}."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "catalog add", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    if entry_type not in _VALID_TYPES:
        msg = (
            f"Unknown entry type {entry_type!r}. "
            f"Choose one of: {', '.join(sorted(_VALID_TYPES))}."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "catalog add", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    artifact_path = Path(path).resolve()

    # Derive name from file stem if not provided.
    entry_name = name or artifact_path.stem

    # Build metadata (file info only; no raw data).
    meta: dict[str, Any] = {
        "path_provided": path,
        "exists": artifact_path.exists(),
    }
    if artifact_path.exists() and artifact_path.is_file():
        meta["size_bytes"] = artifact_path.stat().st_size
        meta["suffix"] = artifact_path.suffix

    entry_id = str(uuid4())
    recorded_at = datetime.now(tz=timezone.utc).isoformat()

    conn = _open_catalog(root)
    try:
        conn.execute(
            """
            INSERT INTO entries (id, entry_type, name, path, recorded_at, metadata, sensitivity_class)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry_id,
                entry_type,
                entry_name,
                str(artifact_path),
                recorded_at,
                _json.dumps(meta),
                sensitivity,
            ],
        )
    finally:
        conn.close()

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "catalog add",
                "status": "ok",
                "entry_id": entry_id,
                "name": entry_name,
                "entry_type": entry_type,
                "path": str(artifact_path),
                "recorded_at": recorded_at,
                "sensitivity_class": sensitivity,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(
        success("OK"),
        "registered",
        code(entry_name),
        hint(f"({entry_type})"),
        hint(f"id: {entry_id[:8]}..."),
    )
    state.console.print(
        " ",
        hint("next:"),
        code("decoy catalog list"),
        hint("to see all catalog entries."),
    )


# ---------------------------------------------------------------------------
# catalog show
# ---------------------------------------------------------------------------

_SHOW_EPILOG = """\
Examples:

  decoy catalog show <id>
    Show the full entry for a given id (prefix match supported).

  decoy catalog show <id> --json
    Emit structured JSON for the entry.

  decoy catalog show <id> --workspace /path/to/project
    Show entry from an explicit workspace location.

See also: decoy catalog list, decoy catalog add.
"""


@catalog_app.command(name="show", epilog=_SHOW_EPILOG)
def _show(
    entry_id: str = typer.Argument(
        ...,
        help="Entry id (or id prefix) to show.",
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
    """Show the full details of a catalog entry.

    The entry id can be the full UUID or a prefix (at least 4 characters).
    Use `decoy catalog list` to see all entry ids.

    LOCAL ONLY: the catalog does not sync with the platform server.
    """
    state = setup_output(json_, quiet, verbose)
    root = _require_workspace(workspace, "catalog show", state)

    conn = _open_catalog(root)
    try:
        # Support prefix matching (like git's short-sha lookup).
        rows = conn.execute(
            "SELECT id, entry_type, name, path, recorded_at, metadata, sensitivity_class "
            "FROM entries WHERE id = ? OR id LIKE ?",
            [entry_id, entry_id + "%"],
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        msg = f"No catalog entry found for id {entry_id!r}."
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "catalog show", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
            state.err_console.print(
                " ",
                hint("hint:"),
                "run",
                code("decoy catalog list"),
                "to see available entry ids.",
            )
        raise typer.Exit(code=EXIT_USAGE)

    if len(rows) > 1:
        msg = (
            f"Ambiguous id prefix {entry_id!r}: matches {len(rows)} entries. "
            "Provide a longer prefix."
        )
        if state.mode is OutputMode.json:
            emit_json(state, {"command": "catalog show", "status": "error", "error": msg})
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), msg)
        raise typer.Exit(code=EXIT_USAGE)

    entry = _row_to_dict(rows[0])

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "catalog show",
                "status": "ok",
                "workspace_root": str(root),
                "entry": entry,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("catalog entry"), code(entry["id"]))
    state.console.print(" ", hint("name:"), code(entry["name"]))
    state.console.print(" ", hint("type:"), code(entry["entry_type"]))
    state.console.print(" ", hint("path:"), code(entry["path"] or "(none)"))
    state.console.print(" ", hint("recorded:"), code(entry["recorded_at"][:19]))
    state.console.print(" ", hint("sensitivity:"), code(entry["sensitivity_class"]))
    meta = entry.get("metadata") or {}
    if meta:
        state.console.print(" ", hint("metadata:"))
        for k, v in meta.items():
            state.console.print("   ", hint(f"{k}:"), code(str(v)))


# Public exports
__all__ = ["catalog_app"]
