"""E2E tests for `decoy catalog` (SP-17b).

TDD: tests fail first, then the implementation makes them pass.

Honest framing: the catalog is a LOCAL metadata convenience store backed by
DuckDB at `.decoy/catalog.duckdb`. It records metadata about local datasets,
runs, and evidence artifacts. It does NOT sync with the platform server and
does NOT track remote state.

Assertions:
L1. `catalog list` inside a workspace exits 0 (empty table is fine).
L2. `catalog list` outside a workspace exits non-zero with a clear error.
L3. `catalog list --json` emits structured JSON with a "entries" list.
L4. `catalog list` from a nested subdirectory resolves workspace via upward discovery.

A1. `catalog add` with a path exits 0 and records an entry.
A2. `catalog add --json` emits structured JSON with status ok and the entry id.
A3. Added entry appears in `catalog list` output.
A4. `catalog add` without a path exits non-zero (usage error).
A5. `catalog --help` states the catalog is local-only.

W1. `catalog show <id>` exits 0 and shows the entry details.
W2. `catalog show <id> --json` exits 0 with structured JSON.
W3. `catalog show <id>` for a missing id exits non-zero with a clear error.
W4. `catalog show` with a prefix shorter than 4 chars exits non-zero (enforced).

D1. DuckDB file is created at `.decoy/catalog.duckdb` after the first catalog command.
D2. Round-trip: add -> list -> show produces consistent data.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

from typer.testing import CliRunner

from decoy.__main__ import app

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


# ---------------------------------------------------------------------------
# L1-L3: catalog list
# ---------------------------------------------------------------------------


def test_catalog_list_empty_workspace(tmp_path: Path):
    """catalog list inside an empty workspace exits 0."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app, ["catalog", "list", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0


def test_catalog_list_no_workspace_exits_nonzero(tmp_path: Path):
    """catalog list without a .decoy/ workspace exits non-zero."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        app, ["catalog", "list", "--workspace", str(empty)], catch_exceptions=False
    )
    assert result.exit_code != 0


def test_catalog_list_json_output(tmp_path: Path):
    """catalog list --json emits structured JSON with an entries list."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app, ["catalog", "list", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "catalog list"
    assert "entries" in data
    assert isinstance(data["entries"], list)


def test_catalog_list_upward_discovery(tmp_path: Path, monkeypatch):
    """catalog list from a nested subdir resolves workspace via upward discovery.

    This test MUST FAIL if find_workspace is broken (returns None): the command
    would exit non-zero because no workspace is found.
    """
    _init_workspace(tmp_path)
    subdir = tmp_path / "nested" / "deep"
    subdir.mkdir(parents=True)
    # Ensure upward discovery (find_workspace) is genuinely exercised: an
    # ambient DECOY_WORKSPACE_ROOT would short-circuit the cwd walk and make
    # this test silently vacuous.
    monkeypatch.delenv("DECOY_WORKSPACE_ROOT", raising=False)
    monkeypatch.chdir(subdir)
    # Invoke WITHOUT --workspace: discovery must walk up from subdir to tmp_path
    result = runner.invoke(
        app, ["catalog", "list"], catch_exceptions=False
    )
    assert result.exit_code == 0, (
        f"Catalog upward discovery failed from {subdir}: exit={result.exit_code}\n{result.output}"
    )


# ---------------------------------------------------------------------------
# A1-A5: catalog add
# ---------------------------------------------------------------------------


def test_catalog_add_exits_ok(tmp_path: Path):
    """catalog add with a path exits 0 and records an entry."""
    _init_workspace(tmp_path)
    # Create a file to register
    data_file = tmp_path / "customers.csv"
    data_file.write_text("id,name\n1,Alice\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog", "add", str(data_file), "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_catalog_add_json_output(tmp_path: Path):
    """catalog add --json emits structured JSON with status ok and entry id."""
    _init_workspace(tmp_path)
    data_file = tmp_path / "members.csv"
    data_file.write_text("id,email\n1,a@b.com\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog", "add", "--json", str(data_file), "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "catalog add"
    assert "entry_id" in data


def test_catalog_add_then_list(tmp_path: Path):
    """Entry added via catalog add appears in catalog list."""
    _init_workspace(tmp_path)
    data_file = tmp_path / "orders.csv"
    data_file.write_text("order_id\n1\n2\n", encoding="utf-8")
    runner.invoke(
        app, ["catalog", "add", str(data_file), "--workspace", str(tmp_path)], catch_exceptions=False
    )
    result = runner.invoke(
        app, ["catalog", "list", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert len(data["entries"]) >= 1
    names = [e.get("name") for e in data["entries"]]
    assert "orders" in names or any("orders" in (n or "") for n in names)


def test_catalog_add_no_path_exits_usage(tmp_path: Path):
    """catalog add with no path argument exits non-zero."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app, ["catalog", "add", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert result.exit_code != 0


def test_catalog_help_honest_framing():
    """catalog --help states the catalog is local-only."""
    result = runner.invoke(app, ["catalog", "--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "local" in output


# ---------------------------------------------------------------------------
# W1-W3: catalog show
# ---------------------------------------------------------------------------


def test_catalog_show_exits_ok(tmp_path: Path):
    """catalog show <id> exits 0 and shows entry details."""
    _init_workspace(tmp_path)
    data_file = tmp_path / "claims.csv"
    data_file.write_text("claim_id\n1\n", encoding="utf-8")
    # Add and capture the entry id
    add_result = runner.invoke(
        app,
        ["catalog", "add", "--json", str(data_file), "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert add_result.exit_code == 0
    entry_id = _json.loads(add_result.stdout)["entry_id"]

    result = runner.invoke(
        app,
        ["catalog", "show", entry_id, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_catalog_show_json(tmp_path: Path):
    """catalog show <id> --json exits 0 with structured JSON."""
    _init_workspace(tmp_path)
    data_file = tmp_path / "payments.csv"
    data_file.write_text("payment_id\n1\n", encoding="utf-8")
    add_result = runner.invoke(
        app,
        ["catalog", "add", "--json", str(data_file), "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    entry_id = _json.loads(add_result.stdout)["entry_id"]

    result = runner.invoke(
        app,
        ["catalog", "show", "--json", entry_id, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["command"] == "catalog show"
    assert "entry" in data


def test_catalog_show_missing_id_exits_nonzero(tmp_path: Path):
    """catalog show with a non-existent id exits non-zero."""
    _init_workspace(tmp_path)
    result = runner.invoke(
        app,
        ["catalog", "show", "00000000-0000-0000-0000-000000000000", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0


def test_catalog_show_short_prefix_exits_nonzero(tmp_path: Path):
    """catalog show with a prefix shorter than 4 chars exits non-zero (enforced)."""
    _init_workspace(tmp_path)
    # "ab" is 2 chars -- below the 4-char minimum stated in the docstring
    result = runner.invoke(
        app,
        ["catalog", "show", "ab", "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert "at least 4" in result.output.lower() or "4 characters" in result.output.lower()


# ---------------------------------------------------------------------------
# D1-D2: DuckDB file and round-trip
# ---------------------------------------------------------------------------


def test_catalog_duckdb_file_created(tmp_path: Path):
    """catalog.duckdb is created at .decoy/catalog.duckdb."""
    _init_workspace(tmp_path)
    runner.invoke(
        app, ["catalog", "list", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert (tmp_path / ".decoy" / "catalog.duckdb").exists()


def test_catalog_roundtrip(tmp_path: Path):
    """Round-trip: add -> list -> show produces consistent data."""
    _init_workspace(tmp_path)
    data_file = tmp_path / "users.csv"
    data_file.write_text("user_id,email\n1,a@b.com\n2,c@d.com\n", encoding="utf-8")

    # Add
    add_result = runner.invoke(
        app,
        ["catalog", "add", "--json", str(data_file), "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert add_result.exit_code == 0
    add_data = _json.loads(add_result.stdout)
    entry_id = add_data["entry_id"]

    # List
    list_result = runner.invoke(
        app, ["catalog", "list", "--json", "--workspace", str(tmp_path)], catch_exceptions=False
    )
    assert list_result.exit_code == 0
    list_data = _json.loads(list_result.stdout)
    ids = [e["id"] for e in list_data["entries"]]
    assert entry_id in ids

    # Show
    show_result = runner.invoke(
        app,
        ["catalog", "show", "--json", entry_id, "--workspace", str(tmp_path)],
        catch_exceptions=False,
    )
    assert show_result.exit_code == 0
    show_data = _json.loads(show_result.stdout)
    assert show_data["entry"]["id"] == entry_id
    assert show_data["entry"]["name"] == "users"
