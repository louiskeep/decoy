"""`decoy query` -- read-only SQL over masked-output Parquet files.

Thin wrapper over the public `decoy_engine.run_discovery_sql(sql, tables, *,
row_limit) -> DiscoveryResult`. This module does `--table` parsing, output
formatting, and exit-code mapping ONLY -- the SELECT-only allowlist, the
arbitrary-file-read guard (banning `read_parquet(...)`/`FROM '/path'` inside
the SQL), the in-memory DuckDB session, and the `read_parquet` view
registration all live in and are cited by the engine
(`data_discovery.py`, QA-triage M20). The CLI adds no SQL-string
concatenation and reimplements none of that logic.

Two engine-contract quirks the CLI compensates for (both recorded in the
S6 plan-gate review):

- The engine returns no truncation signal (the result is just `columns` +
  `rows`). So the CLI queries at `row_limit + 1` and sets
  `truncated = len(rows) > row_limit`, then trims to `row_limit` for both
  display and the JSON envelope. `row_count` is the trimmed length.
- The engine only wraps `con.execute(sql)` in `DiscoverySqlError`; the
  `read_parquet().create_view()` step runs before that, so a present-but-
  non-Parquet/corrupt file raises a RAW `duckdb.Error` (IOException /
  InvalidInputException) the engine does not translate. The CLI therefore
  catches `DiscoverySqlError` AND `duckdb.Error` (plus a broad fallback)
  around the one engine call and maps all of them to `EXIT_USAGE` with a
  readable message -- no traceback ever reaches the user.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import code, error, hint

QUERY_EPILOG = """\
Examples:

  decoy query "SELECT count(*) AS n FROM out" --table out.parquet
    Bare PATH: the table name is inferred from the file stem ("out").

  decoy query "SELECT * FROM t WHERE amount > 100" --table t=masked.parquet
    NAME=PATH: register masked.parquet under the name `t`.

  decoy query "SELECT c.id FROM customers c JOIN orders o ON o.cust = c.id" \\
      --table customers=customers.parquet --table orders=orders.parquet
    Repeat --table to JOIN across several masked outputs.

  decoy query "SELECT * FROM t" --table t=out.parquet --row-limit 50 --json
    Cap at 50 rows and emit a structured envelope on stdout.

Read-only by construction: only SELECT / WITH / VALUES / TABLE statements are
allowed, and the SQL may not read arbitrary files (`read_parquet(...)` or
`FROM '/path'` inside the query are rejected). Anything else is a clean usage
error, not a traceback. Tables must be Parquet.

See also: decoy run, decoy report fidelity.
"""

# A "simple identifier": a DuckDB-safe unquoted view name the CLI will accept
# as a --table NAME and that stem inference sanitizes down to.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _infer_name(path: Path) -> str:
    """Derive a simple identifier from a file stem.

    Non-identifier characters collapse to `_`; a leading non-letter/underscore
    (e.g. a stem starting with a digit) gets an `_` prefix so the result is
    always a valid unquoted view name.
    """
    stem = path.stem
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not sanitized or not re.match(r"[A-Za-z_]", sanitized[0]):
        sanitized = "_" + sanitized
    return sanitized


def _fail_usage(state, msg: str) -> None:
    """Emit the error (JSON envelope or stderr line) for a usage failure.

    Caller raises `typer.Exit(EXIT_USAGE)` right after. markup=False: the
    message can quote paths / engine text that Rich would try to parse as
    style tags.
    """
    if state.mode is OutputMode.json:
        emit_json(state, {"command": "query", "status": "error", "error": msg})
        return
    if state.mode is OutputMode.quiet:
        return
    state.err_console.print(error("error:"), msg, markup=False)


def query(
    sql: str = typer.Argument(
        ...,
        help="The SELECT statement to run (quote it in the shell).",
    ),
    tables: list[str] = typer.Option(
        [],
        "--table",
        help=(
            "A Parquet table to query, as NAME=PATH or a bare PATH (the name is "
            "inferred from the file stem). Repeatable; at least one is required."
        ),
    ),
    row_limit: int = typer.Option(
        10000,
        "--row-limit",
        min=1,
        help="Maximum number of rows to return (default 10000).",
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
        help="Suppress stdout. Errors still go to stderr; exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Run a read-only SQL query over one or more masked-output Parquet files.

    Registers each `--table` file as a view and runs the SELECT via the
    engine's `run_discovery_sql` (SELECT-only, Parquet-only, no arbitrary
    file reads). Prints a table in human mode or a
    `{command:"query", status, columns, rows, row_count, truncated}` envelope
    under `--json`. Bad input (a malformed `--table`, a non-SELECT statement,
    an unreadable/non-Parquet file) is a clean `EXIT_USAGE`, never a traceback.
    """
    state = setup_output(json_, quiet, verbose)

    if not tables:
        _fail_usage(
            state,
            "decoy query requires at least one --table NAME=PATH (or --table PATH).",
        )
        raise typer.Exit(code=EXIT_USAGE)

    # --- Parse + validate every --table BEFORE touching the engine. ---
    mapping: dict[str, str] = {}
    for raw in tables:
        if "=" in raw:
            name, _, path_str = raw.partition("=")
            if not _IDENTIFIER.match(name):
                _fail_usage(
                    state,
                    f"invalid --table name {name!r}: a table name must be a simple "
                    "identifier ([A-Za-z_][A-Za-z0-9_]*).",
                )
                raise typer.Exit(code=EXIT_USAGE)
            path = Path(path_str)
        else:
            path = Path(raw)
            name = _infer_name(path)

        if not path.exists() or not path.is_file():
            _fail_usage(
                state,
                f"--table path does not exist or is not a file: {path}",
            )
            raise typer.Exit(code=EXIT_USAGE)

        mapping[name] = str(path.resolve())

    # --- Run the query. Lazy-import the engine + duckdb inside the body. ---
    import duckdb
    from decoy_engine import DiscoverySqlError, run_discovery_sql

    try:
        # row_limit + 1 so we can detect truncation: the engine returns no
        # truncation signal, so an extra row means "there was more".
        result = run_discovery_sql(sql, mapping, row_limit=row_limit + 1)
    except DiscoverySqlError as exc:
        # SELECT-only / arbitrary-file-read / SQL execution error -- the
        # engine message is already readable and quote-safe.
        _fail_usage(state, str(exc))
        raise typer.Exit(code=EXIT_USAGE)
    except duckdb.Error as exc:
        # Raw DuckDB error from the pre-execute read_parquet()/create_view()
        # step (present-but-non-Parquet/corrupt file). The message names the
        # offending file path.
        _fail_usage(state, f"could not read a --table file: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    except Exception as exc:  # pragma: no cover - defensive: never leak a traceback
        _fail_usage(state, str(exc))
        raise typer.Exit(code=EXIT_USAGE)

    truncated = len(result.rows) > row_limit
    trimmed = result.rows[:row_limit]
    row_count = len(trimmed)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "query",
                "status": "ok",
                "columns": result.columns,
                "rows": trimmed,
                "row_count": row_count,
                "truncated": truncated,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    _render_human(state, result.columns, trimmed, truncated=truncated, row_limit=row_limit)


def _render_human(state, columns, rows, *, truncated: bool, row_limit: int) -> None:
    tbl = make_table(*columns)
    for row in rows:
        # None -> "" keeps SQL NULLs from printing as the literal "None".
        tbl.add_row(*["" if row.get(c) is None else str(row.get(c)) for c in columns])
    state.console.print(tbl)
    if not rows:
        state.console.print(hint("0 rows."))
    elif truncated:
        state.console.print(
            hint(f"Showing first {row_limit} rows (truncated; more rows matched)."),
            " ",
            hint("Raise"),
            code("--row-limit"),
            hint("to see more."),
        )
