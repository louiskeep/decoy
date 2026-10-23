"""End-to-end tests for `decoy query` (S6 CLI wrapper).

Thin wrapper over the public `decoy_engine.run_discovery_sql`; these tests
exercise the CLI surface only (--table parsing, truncation accounting,
output formatting, exit-code mapping). The SELECT-only allowlist, the
arbitrary-file-read guard, and the DuckDB session live in and are tested by
the engine -- not re-tested here, only that the CLI surfaces them cleanly.

Assertions:
Q1.  count(*) returns the right number in human mode + a well-shaped --json
     envelope (incl. truncated:false).
Q2.  bare --table PATH infers the table name from the file stem.
Q3.  non-SELECT (DROP/INSERT/UPDATE) -> EXIT_USAGE, no traceback.
Q4.  arbitrary-file-read guard: read_parquet('/etc/passwd') and FROM '/path'
     -> EXIT_USAGE, no traceback.
Q5.  present-but-invalid Parquet -> EXIT_USAGE naming the file; a MISSING
     path -> EXIT_USAGE.
Q6.  --row-limit: below the row count -> truncated:true + exactly N rows;
     exactly the row count -> truncated:false (no false positive).
Q7.  two --table JOIN works.
Q8.  malformed --table (neither NAME=PATH nor a readable file) and a
     non-identifier NAME -> EXIT_USAGE.
Q9.  empty result renders "0 rows" cleanly, exit 0.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_parquet(tmp_path: Path, name: str = "t.parquet", n: int = 3) -> Path:
    path = tmp_path / name
    pl.DataFrame(
        {
            "id": list(range(1, n + 1)),
            "v": [f"row{i}" for i in range(1, n + 1)],
        }
    ).write_parquet(path)
    return path


def _write_customers_orders(tmp_path: Path) -> tuple[Path, Path]:
    customers = tmp_path / "customers.parquet"
    orders = tmp_path / "orders.parquet"
    pl.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}).write_parquet(customers)
    pl.DataFrame({"id": [10, 11, 12], "cust": [1, 1, 2]}).write_parquet(orders)
    return customers, orders


# ---------------------------------------------------------------------------
# Q1 -- count(*) human + --json envelope
# ---------------------------------------------------------------------------


def test_count_human(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path, n=3)
    result = runner.invoke(app, ["query", "SELECT count(*) AS n FROM t", "--table", f"t={p}"])
    assert result.exit_code == 0, result.output
    assert "n" in result.output
    assert "3" in result.output


def test_count_json_envelope(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path, n=3)
    result = runner.invoke(
        app, ["query", "SELECT count(*) AS n FROM t", "--table", f"t={p}", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["command"] == "query"
    assert data["status"] == "ok"
    assert data["columns"] == ["n"]
    assert data["rows"] == [{"n": 3}]
    assert data["row_count"] == 1
    assert data["truncated"] is False


# ---------------------------------------------------------------------------
# Q2 -- bare PATH stem inference
# ---------------------------------------------------------------------------


def test_bare_path_stem_inference(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path, name="orders_masked.parquet", n=5)
    # stem "orders_masked" is already a valid identifier -> FROM orders_masked
    result = runner.invoke(
        app, ["query", "SELECT count(*) AS n FROM orders_masked", "--table", str(p), "--json"]
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["rows"] == [{"n": 5}]


# ---------------------------------------------------------------------------
# Q3 -- non-SELECT statements
# ---------------------------------------------------------------------------


def test_non_select_statements_rejected(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path)
    for sql in ["DROP TABLE t", "INSERT INTO t VALUES (99, 'x')", "UPDATE t SET v = 'x'"]:
        result = runner.invoke(app, ["query", sql, "--table", f"t={p}"])
        assert result.exit_code == 1, f"{sql!r}: {result.output}"
        assert "Traceback" not in result.output, sql


# ---------------------------------------------------------------------------
# Q4 -- arbitrary-file-read guard
# ---------------------------------------------------------------------------


def test_arbitrary_file_read_guard(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path)
    for sql in [
        "SELECT * FROM read_parquet('/etc/passwd')",
        "SELECT * FROM '/etc/passwd'",
    ]:
        result = runner.invoke(app, ["query", sql, "--table", f"t={p}"])
        assert result.exit_code == 1, f"{sql!r}: {result.output}"
        assert "Traceback" not in result.output, sql
        assert "root:" not in result.output, f"/etc/passwd contents leaked for {sql!r}"


def test_arbitrary_file_read_guard_json(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path)
    result = runner.invoke(
        app,
        ["query", "SELECT * FROM read_parquet('/etc/passwd')", "--table", f"t={p}", "--json"],
    )
    assert result.exit_code == 1
    data = _json.loads(result.stdout)
    assert data == {
        "command": "query",
        "status": "error",
        "error": data["error"],
    }
    assert data["error"]


# ---------------------------------------------------------------------------
# Q5 -- invalid Parquet (raw-duckdb path) vs missing path
# ---------------------------------------------------------------------------


def test_present_but_invalid_parquet_names_file(tmp_path: Path) -> None:
    bad = tmp_path / "foo.parquet"
    bad.write_text("this is not parquet\n", encoding="utf-8")
    result = runner.invoke(app, ["query", "SELECT * FROM foo", "--table", f"foo={bad}"])
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    assert "foo.parquet" in result.output


def test_missing_path_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "nope.parquet"
    result = runner.invoke(app, ["query", "SELECT * FROM t", "--table", f"t={missing}"])
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    assert "nope.parquet" in result.output


# ---------------------------------------------------------------------------
# Q6 -- --row-limit truncation accounting
# ---------------------------------------------------------------------------


def test_row_limit_truncates(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path, n=5)
    result = runner.invoke(
        app, ["query", "SELECT * FROM t ORDER BY id", "--table", f"t={p}", "--row-limit", "2", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["truncated"] is True
    assert data["row_count"] == 2
    assert len(data["rows"]) == 2


def test_row_limit_exact_is_not_false_positive(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path, n=3)
    result = runner.invoke(
        app, ["query", "SELECT * FROM t ORDER BY id", "--table", f"t={p}", "--row-limit", "3", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["truncated"] is False
    assert data["row_count"] == 3


# ---------------------------------------------------------------------------
# Q7 -- two --table JOIN
# ---------------------------------------------------------------------------


def test_two_table_join(tmp_path: Path) -> None:
    customers, orders = _write_customers_orders(tmp_path)
    result = runner.invoke(
        app,
        [
            "query",
            "SELECT c.name AS name, count(*) AS orders FROM customers c "
            "JOIN orders o ON o.cust = c.id GROUP BY c.name ORDER BY c.name",
            "--table",
            f"customers={customers}",
            "--table",
            f"orders={orders}",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["columns"] == ["name", "orders"]
    assert data["rows"] == [{"name": "a", "orders": 2}, {"name": "b", "orders": 1}]


# ---------------------------------------------------------------------------
# Q8 -- malformed --table
# ---------------------------------------------------------------------------


def test_no_table_is_usage_error() -> None:
    result = runner.invoke(app, ["query", "SELECT 1"])
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output


def test_malformed_table_not_pair_nor_file(tmp_path: Path) -> None:
    # No "=" and not a readable file.
    result = runner.invoke(app, ["query", "SELECT 1", "--table", "definitely_not_a_file"])
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output


def test_non_identifier_table_name(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path)
    result = runner.invoke(app, ["query", "SELECT 1", "--table", f"9bad={p}"])
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    assert "9bad" in result.output


# ---------------------------------------------------------------------------
# Q9 -- empty result renders cleanly
# ---------------------------------------------------------------------------


def test_empty_result_human(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path)
    result = runner.invoke(app, ["query", "SELECT * FROM t WHERE 1=0", "--table", f"t={p}"])
    assert result.exit_code == 0, result.output
    assert "0 rows" in result.output


def test_empty_result_json(tmp_path: Path) -> None:
    p = _write_parquet(tmp_path)
    result = runner.invoke(
        app, ["query", "SELECT * FROM t WHERE 1=0", "--table", f"t={p}", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.stdout)
    assert data["row_count"] == 0
    assert data["rows"] == []
    assert data["truncated"] is False
