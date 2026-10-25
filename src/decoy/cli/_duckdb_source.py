"""Acquire a DuckDB relation into a temporary Parquet file for `decoy run`.

Database input follows the engine's established snapshot-to-Parquet pattern
(`decoy_engine.connectors.postgres_snapshot.snapshot_tables_to_parquet`): DuckDB
owns the read and the type mapping, Decoy stages the relation to a Parquet file,
and the normal file-based masking path runs over that Parquet unchanged. The CLI
never adds a new engine source format (the engine's `SourceDescriptor` stays a
closed file/s3/gcs union) and never accepts a raw user SQL string -- only a
structured relation identifier -- so there is no SQL-injection or
arbitrary-file-read surface.

Reference: DuckDB Parquet export via `COPY (...) TO ... (FORMAT PARQUET)`
(https://duckdb.org/docs/stable/sql/statements/copy) over a read-only
connection, the same posture as the postgres_snapshot connector.
"""

from __future__ import annotations

import re
from pathlib import Path

# A relation name we will interpolate into `COPY (SELECT * FROM <name>)`. The
# allowlist is exactly a simple SQL identifier, so the name cannot carry a
# quote, a space, or any metacharacter -- interpolation is injection-safe by
# construction and no identifier-quoting helper is needed.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DuckDBSourceError(Exception):
    """A `--duckdb-source` the operator can fix: a malformed flag value, a
    missing database file, an unknown relation, or an unreadable database.
    `decoy run` maps it to EXIT_USAGE and never prints a traceback."""


def parse_flag(value: str) -> tuple[str, str]:
    """Parse one `--duckdb-source TABLE=DB_PATH` value into `(table, db_path)`.

    `TABLE` must be a simple identifier (it is both the pipeline table name and
    the DuckDB relation read); `DB_PATH` is the path to the `.duckdb` file.
    """
    table, sep, db_path = value.partition("=")
    if not sep:
        raise DuckDBSourceError(f"--duckdb-source: expected TABLE=DB_PATH, got {value!r}")
    table = table.strip()
    db_path = db_path.strip()
    if not _IDENT_RE.match(table):
        raise DuckDBSourceError(
            f"--duckdb-source: table name {table!r} is not a simple identifier "
            "(letters, digits, underscore; not starting with a digit)"
        )
    if not db_path:
        raise DuckDBSourceError(f"--duckdb-source: {table!r} has an empty DB_PATH")
    return table, db_path


def acquire_relation(db_path: Path, relation: str, dest_dir: Path) -> Path:
    """Copy `relation` from the read-only DuckDB at `db_path` to a Parquet file
    under `dest_dir`, returning that Parquet path.

    DuckDB owns the type mapping on export. The connection is read-only, so the
    source database is never modified. `relation` is verified against the
    database catalog (case-insensitively, parameter-bound) before it is read;
    it is already constrained to a simple identifier by `parse_flag`.
    """
    if not db_path.exists() or not db_path.is_file():
        raise DuckDBSourceError(f"--duckdb-source: database file not found: {db_path}")
    if not _IDENT_RE.match(relation):
        # Defensive: callers pass a parse_flag-validated name, but never trust a
        # raw identifier into the COPY below.
        raise DuckDBSourceError(f"--duckdb-source: invalid relation name {relation!r}")

    import duckdb

    try:
        conn = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        raise DuckDBSourceError(
            f"--duckdb-source: cannot open {db_path} read-only ({type(exc).__name__})"
        ) from None
    try:
        row = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE lower(table_name) = lower(?) LIMIT 1",
            [relation],
        ).fetchone()
        if not row:
            raise DuckDBSourceError(
                f"--duckdb-source: relation {relation!r} not found in {db_path}"
            )
        # Use the catalog's exact-case name, double-quoted, so a table whose name
        # is a SQL reserved word (e.g. ``order``) or a case variant reads correctly.
        # The name comes from the catalog (not the caller), the caller's name
        # already passed the identifier allowlist, and any embedded quote is
        # doubled, so this cannot inject.
        actual = str(row[0])
        actual_sql = actual.replace('"', '""')
        dest = dest_dir / f"{relation}.parquet"
        dest_sql = str(dest.as_posix()).replace("'", "''")
        conn.execute(f"COPY (SELECT * FROM \"{actual_sql}\") TO '{dest_sql}' (FORMAT PARQUET)")
    except DuckDBSourceError:
        raise
    except Exception as exc:
        raise DuckDBSourceError(
            f"--duckdb-source: failed reading {relation!r} from {db_path} ({type(exc).__name__})"
        ) from None
    finally:
        conn.close()
    return dest
