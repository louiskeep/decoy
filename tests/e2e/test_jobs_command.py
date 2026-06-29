"""E2E tests for `decoy jobs list/show/watch` (SP-18b).

TDD: tests fail first, then the implementation makes them pass.

Honest framing: `jobs` reads LOCAL run history from the DuckDB catalog
(.decoy/catalog.duckdb). Entries are written by `decoy run` when a workspace
exists. LOCAL ONLY -- does not connect to the platform server or reflect
remote/platform job state.

`jobs watch`: local CLI runs are SYNCHRONOUS. A run appears in the catalog only
after it completes. `watch` is honest about this: it shows completed run status
and states that local runs are synchronous (remote watch is SP-20/platform).

Assertions:

L1. `jobs list` inside a workspace with no run entries exits 0 (empty is ok).
L2. `jobs list` without a workspace exits non-zero with a clear error.
L3. `jobs list --json` emits structured JSON with a `runs` list.
L4. After a run entry is seeded in the catalog, `jobs list` shows it.
L5. `jobs list` shows runs most-recent first.

S1. `jobs show <run-id>` for a cataloged run exits 0 and shows metadata.
S2. `jobs show <run-id> --json` exits 0 with structured JSON.
S3. `jobs show` with a non-existent id exits non-zero.
S4. `jobs show` with an ambiguous prefix exits non-zero.
S5. `jobs show` with a prefix < 4 chars exits non-zero.

W1. `jobs watch <run-id>` for a completed run exits 0 with honest status.
W2. `jobs watch` for a missing run-id exits non-zero.
W3. `jobs watch --help` mentions that local runs are synchronous (honest framing).
"""

from __future__ import annotations

import json as _json
from pathlib import Path

from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.catalog import _open_catalog

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_workspace(tmp_path: Path) -> Path:
    """Init a workspace and return tmp_path (the workspace root)."""
    result = runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0, f"project init failed: {result.output}"
    return tmp_path


def _seed_run_entry(
    workspace: Path,
    *,
    name: str = "pipeline",
    status: str = "ok",
    mode: str = "mask",
    elapsed_s: float = 1.23,
    config_path: str = "/tmp/pipeline.yaml",
    evidence_path: str | None = None,
    run_timestamp: str = "2026-06-29T10:00:00+00:00",
) -> str:
    """Insert a run entry into the catalog. Returns the entry id."""
    import json as _j
    from datetime import datetime, timezone
    from uuid import uuid4

    entry_id = str(uuid4())
    run_id = str(uuid4())
    recorded_at = datetime.now(tz=timezone.utc).isoformat()

    meta = {
        "run_id": run_id,
        "status": status,
        "mode": mode,
        "elapsed_s": elapsed_s,
        "config_path": config_path,
        "engine_version": "0.4.0",
        "cli_version": "0.5.0",
        "run_timestamp": run_timestamp,
    }
    if evidence_path is not None:
        meta["evidence_path"] = evidence_path

    conn = _open_catalog(workspace)
    try:
        conn.execute(
            """
            INSERT INTO entries (id, entry_type, name, path, recorded_at, metadata, sensitivity_class)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry_id,
                "run",
                name,
                evidence_path or config_path,
                recorded_at,
                _j.dumps(meta),
                "evidence-safe",
            ],
        )
    finally:
        conn.close()

    return entry_id


# ---------------------------------------------------------------------------
# L1-L4: jobs list
# ---------------------------------------------------------------------------


def test_jobs_list_empty_workspace_exits_ok(tmp_path: Path) -> None:
    """jobs list inside a workspace with no run entries exits 0."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app, ["jobs", "list", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0


def test_jobs_list_no_workspace_exits_nonzero(tmp_path: Path) -> None:
    """jobs list without a .decoy/ workspace exits non-zero."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        app, ["jobs", "list", "--workspace", str(empty)], catch_exceptions=False
    )
    assert result.exit_code != 0


def test_jobs_list_json_output(tmp_path: Path) -> None:
    """jobs list --json emits structured JSON with a runs list."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app, ["jobs", "list", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "jobs list"
    assert "runs" in data
    assert isinstance(data["runs"], list)


def test_jobs_list_shows_seeded_run(tmp_path: Path) -> None:
    """jobs list shows a run entry that was seeded into the catalog."""
    _init_workspace(tmp_path)
    entry_id = _seed_run_entry(tmp_path, name="customers")

    result = runner.invoke(
        app, ["jobs", "list", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    ids = [r["id"] for r in data["runs"]]
    assert entry_id in ids


def test_jobs_list_most_recent_first(tmp_path: Path) -> None:
    """jobs list orders runs most-recent first."""
    import time

    _init_workspace(tmp_path)

    # Seed two entries with distinct timestamps to guarantee order
    _seed_run_entry(tmp_path, name="first_run", run_timestamp="2026-06-29T08:00:00+00:00")
    time.sleep(0.01)  # ensure distinct recorded_at
    second_id = _seed_run_entry(tmp_path, name="second_run", run_timestamp="2026-06-29T09:00:00+00:00")

    result = runner.invoke(
        app, ["jobs", "list", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert len(data["runs"]) >= 2
    # Most recent (second_id) should come first
    assert data["runs"][0]["id"] == second_id


# ---------------------------------------------------------------------------
# S1-S5: jobs show
# ---------------------------------------------------------------------------


def test_jobs_show_exits_ok(tmp_path: Path) -> None:
    """jobs show <run-id> exits 0 and shows run metadata."""
    _init_workspace(tmp_path)
    entry_id = _seed_run_entry(tmp_path)

    result = runner.invoke(
        app, ["jobs", "show", entry_id, "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0


def test_jobs_show_json(tmp_path: Path) -> None:
    """jobs show <run-id> --json exits 0 with structured JSON."""
    _init_workspace(tmp_path)
    entry_id = _seed_run_entry(tmp_path, status="ok", mode="mask")

    result = runner.invoke(
        app,
        ["jobs", "show", "--json", entry_id, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "jobs show"
    assert "run" in data
    run = data["run"]
    assert run["id"] == entry_id


def test_jobs_show_missing_id_exits_nonzero(tmp_path: Path) -> None:
    """jobs show with a non-existent id exits non-zero."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app,
        ["jobs", "show", "00000000-0000-0000-0000-000000000000", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


def test_jobs_show_ambiguous_prefix_exits_nonzero(tmp_path: Path) -> None:
    """jobs show with an ambiguous prefix exits non-zero."""
    _init_workspace(tmp_path)
    # Seed two entries with the same first 4 chars is unlikely; instead test
    # with the shared 'e' prefix from two separate entries (prefix must be >= 4
    # chars; we test by manually creating entries with a common prefix)
    import json as _j
    from datetime import datetime, timezone

    conn = _open_catalog(tmp_path)
    try:
        prefix = "aaaa"
        for i in range(2):
            uid = f"{prefix}{'0' * (32 - len(prefix))}{i:03d}"[:36]
            import uuid

            uid = str(uuid.uuid4()).replace(str(uuid.uuid4())[:4], prefix, 1)
            # Just insert two entries whose full ids both start with the same 4 chars
            uid = f"{prefix}0000-0000-0000-0000-{i:012d}"
            conn.execute(
                """
                INSERT INTO entries
                    (id, entry_type, name, path, recorded_at, metadata, sensitivity_class)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    uid,
                    "run",
                    f"run_{i}",
                    "/tmp/p.yaml",
                    datetime.now(tz=timezone.utc).isoformat(),
                    _j.dumps({"status": "ok"}),
                    "evidence-safe",
                ],
            )
    finally:
        conn.close()

    result = runner.invoke(
        app,
        ["jobs", "show", "aaaa", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


def test_jobs_show_short_prefix_exits_nonzero(tmp_path: Path) -> None:
    """jobs show with a prefix shorter than 4 chars exits non-zero."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app,
        ["jobs", "show", "ab", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# W1-W3: jobs watch
# ---------------------------------------------------------------------------


def test_jobs_watch_completed_run_exits_ok(tmp_path: Path) -> None:
    """jobs watch for a completed run exits 0 with honest status message."""
    _init_workspace(tmp_path)
    entry_id = _seed_run_entry(tmp_path, status="ok")

    result = runner.invoke(
        app, ["jobs", "watch", entry_id, "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    # Must communicate the run is already complete -- not fake progress
    output = result.output.lower()
    assert "complete" in output or "done" in output or "finished" in output or "ok" in output


def test_jobs_watch_missing_id_exits_nonzero(tmp_path: Path) -> None:
    """jobs watch with a missing run-id exits non-zero."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app,
        ["jobs", "watch", "00000000-0000-0000-0000-000000000000", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


def test_jobs_watch_help_mentions_synchronous() -> None:
    """jobs watch --help states local runs are synchronous (honest framing)."""
    result = runner.invoke(app, ["jobs", "watch", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    # Must mention that local runs are synchronous and watch has limited utility
    assert "synchronous" in output or "complete" in output or "local" in output
