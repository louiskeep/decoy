"""E2E tests for `decoy project` (SP-17b).

TDD: tests fail first, then the implementation makes them pass.

Honest framing: `.decoy/` is a LOCAL convenience workspace. It does NOT sync
with the platform server, track remote state, or replace RBAC/audit-log features.
Deleting `.decoy/` removes derived Decoy artifacts; it never deletes source data.

Assertions:
I1. `project init` exits 0 and creates a `.decoy/` directory.
I2. `project init` creates a `workspace.json` config file inside `.decoy/`.
I3. `project init` creates expected subdirectories (scans, runs, evidence, reports).
I4. `project init` is idempotent: re-running in an existing workspace exits 0.
I5. `project init --json` emits structured JSON with status and workspace_root.
I6. `project --help` mentions that the workspace is local-only (honest framing).
I7. `project init --help` mentions that it does not sync with the platform.

S1. `project show` inside a workspace exits 0 and prints config facts.
S2. `project show --json` exits 0 with structured JSON (status ok, workspace_root).
S3. `project show` from a subdirectory discovers `.decoy/` in the parent (upward discovery).
S4. `project show` outside any workspace exits non-zero with a clear error.
S5. `project show --json` outside any workspace exits non-zero with JSON error.
S6. `project show` with no `.decoy/` dir emits "No .decoy/ workspace found", not a misleading message.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# I1-I7: project init
# ---------------------------------------------------------------------------


def test_project_init_creates_dotdecoy(tmp_path: Path):
    """project init exits 0 and creates a .decoy/ directory."""
    # Both invocations use --workspace so .decoy/ lands in tmp_path, not the repo root.
    runner.invoke(app, ["project", "init", "--workspace", str(tmp_path)],
                  catch_exceptions=False)
    result2 = runner.invoke(app, ["project", "init", "--workspace", str(tmp_path)],
                            catch_exceptions=False)
    assert result2.exit_code == 0
    assert (tmp_path / ".decoy").is_dir()


def test_project_init_creates_workspace_json(tmp_path: Path):
    """project init creates workspace.json inside .decoy/."""
    result = runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    ws_json = tmp_path / ".decoy" / "workspace.json"
    assert ws_json.exists(), f".decoy/workspace.json not found; .decoy/ contents: {list((tmp_path / '.decoy').iterdir()) if (tmp_path / '.decoy').exists() else 'missing'}"
    data = _json.loads(ws_json.read_text(encoding="utf-8"))
    assert data.get("workspace_version") == 1
    assert "created_at" in data


def test_project_init_creates_subdirs(tmp_path: Path):
    """project init creates expected subdirectories inside .decoy/."""
    result = runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    dotdecoy = tmp_path / ".decoy"
    for subdir in ("scans", "runs", "evidence", "reports"):
        assert (dotdecoy / subdir).is_dir(), f".decoy/{subdir}/ was not created"


def test_project_init_is_idempotent(tmp_path: Path):
    """project init is idempotent: re-running in an existing workspace exits 0."""
    runner.invoke(app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False)
    result = runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    # workspace.json should still be valid
    ws_json = tmp_path / ".decoy" / "workspace.json"
    data = _json.loads(ws_json.read_text(encoding="utf-8"))
    assert data.get("workspace_version") == 1


def test_project_init_json_output(tmp_path: Path):
    """project init --json emits structured JSON with status and workspace_root."""
    result = runner.invoke(
        app, ["project", "init", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "project init"
    assert "workspace_root" in data


def test_project_init_help_honest_framing():
    """project --help mentions the workspace is local-only."""
    result = runner.invoke(app, ["project", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "local" in output


def test_project_init_subcommand_help_honest_framing():
    """project init --help states it does not sync with the platform."""
    result = runner.invoke(app, ["project", "init", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "local" in output
    assert "does not sync" in output
    assert "platform" in output


# ---------------------------------------------------------------------------
# S1-S5: project show
# ---------------------------------------------------------------------------


def test_project_show_inside_workspace(tmp_path: Path):
    """project show inside a workspace exits 0 and prints config facts."""
    runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    result = runner.invoke(
        app, ["project", "show", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    output = result.output
    # Should mention the workspace path or key config fields
    assert ".decoy" in output or str(tmp_path) in output


def test_project_show_json(tmp_path: Path):
    """project show --json exits 0 with structured JSON."""
    runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    result = runner.invoke(
        app, ["project", "show", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "project show"
    assert "workspace_root" in data
    assert "config" in data


def test_project_show_upward_discovery(tmp_path: Path, monkeypatch):
    """project show from a subdirectory genuinely exercises find_workspace upward walk.

    This test MUST FAIL if find_workspace is broken (returns None): the command
    would exit non-zero and the exit_code assertion would fail.
    """
    # Init workspace at tmp_path
    runner.invoke(
        app, ["project", "init", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    # Create a deep subdirectory (3 levels) that has no .decoy/ of its own
    subdir = tmp_path / "data" / "subdir"
    subdir.mkdir(parents=True)
    # chdir into the nested dir -- find_workspace() must walk up to tmp_path
    monkeypatch.chdir(subdir)
    # Invoke WITHOUT --workspace: discovery must walk up from subdir to tmp_path
    result = runner.invoke(
        app, ["project", "show"], catch_exceptions=False
    )
    assert result.exit_code == 0, (
        f"Upward discovery failed from {subdir}: exit={result.exit_code}\n{result.output}"
    )
    # The workspace root (tmp_path) must appear in the output
    assert str(tmp_path) in result.output


def test_project_show_no_workspace_exits_nonzero(tmp_path: Path):
    """project show with no .decoy/ workspace exits non-zero."""
    # Use a path with no .decoy/ workspace
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        app, ["project", "show", "--workspace", str(empty)], catch_exceptions=False
    )
    assert result.exit_code != 0


def test_project_show_no_workspace_json_error(tmp_path: Path):
    """project show --json with no workspace exits non-zero with JSON error."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        app, ["project", "show", "--json", "--workspace", str(empty)], catch_exceptions=False
    )
    assert result.exit_code != 0
    data = _json.loads(result.stdout)
    assert data["status"] == "error"
    assert data["command"] == "project show"


def test_project_show_no_dotdecoy_dir_correct_message(tmp_path: Path):
    """project show with no .decoy/ dir emits 'No .decoy/ workspace found', not 'workspace.json is missing'."""
    empty = tmp_path / "no_ws"
    empty.mkdir()
    result = runner.invoke(
        app, ["project", "show", "--workspace", str(empty)], catch_exceptions=False
    )
    assert result.exit_code != 0
    combined = result.output
    # Must say "No .decoy/" -- NOT misleadingly say "workspace.json is missing"
    assert "no .decoy/" in combined.lower(), f"Expected 'No .decoy/' in output:\n{combined}"
    assert "workspace.json is missing" not in combined, (
        f"Misleading 'workspace.json is missing' shown when .decoy/ does not exist:\n{combined}"
    )
