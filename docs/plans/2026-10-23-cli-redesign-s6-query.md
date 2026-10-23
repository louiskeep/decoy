# S6 build plan — `decoy query` (+ privacy-metrics deferral)

Status: build plan, PRE-RELEASE (2026-10-23). Sixth/final sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Additive (one new command), pre-GA. Awaiting plan-gate.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, scope-discipline,
documentation, reuse-first, testing.

Established solutions: n/a — no custom logic; the CLI surfaces the public `decoy_engine.run_discovery_sql`
verbatim. The SELECT-only allowlist + arbitrary-file-read guards (banning `read_parquet(...)`/`FROM '/path'`
inside the SQL) live in and are cited by the engine module (`data_discovery.py` QA-triage M20, 2026-05-31);
the CLI adds no SQL-string concatenation.

Risk: R2 (additive CLI command surfacing an existing public engine function; no engine change;
feature-branch; no merge). The engine function is read-only and hardened (SELECT-only allowlist); the CLI is
a thin wrapper.

Plan-gate review incorporated (GO-WITH-REVISIONS, 2026-10-23): P1 #1-#3 + P2 #4-#8 folded in. Headlines:
#1 the engine returns no truncation signal — query `row_limit+1`, set `truncated = len(rows) > row_limit`,
trim to `row_limit`; #2 the engine only wraps `con.execute(sql)` in `DiscoverySqlError`, so a present-but-
non-Parquet/corrupt file raises raw `duckdb.Error` — the CLI catches `duckdb.Error`/`Exception` around the
call too and maps to `EXIT_USAGE` (no traceback); #3 the `--table NAME=PATH` surface is kept as primary
(faithful to the engine `Mapping`, supports JOIN) with a recorded decision + a single-file convenience.

## Scope

Ship the cleanly-public fast-follow and defer the rest:
- **SHIP `decoy query`** — read-only SQL over masked Parquet output via the public
  `decoy_engine.run_discovery_sql(sql, tables, *, row_limit) -> DiscoveryResult` (in
  `decoy_engine.__all__`; SELECT/WITH/VALUES/TABLE-only, in-memory DuckDB, `read_parquet` views).
- **DEFER `report fidelity --privacy`** (DCR / new-row-synthesis / membership-inference metrics): the engine
  `quality` compute surface (`compute_dcr`/`compute_attack_metrics`/`compute_quality_report`/...) is NOT in
  `decoy_engine.__all__` (confirmed). Like `list detectors` and `scan --suggest`, this needs an additive
  engine export first, then a one-flag CLI slice. Owner/engine follow-up.
- **`fit` polish** — DROPPED from this slice (P2-7: unrelated help text riding the query slice). `fit`
  already works; a one-line help clarification is recorded as a trivial standalone follow-up, not built here.

Non-goals: no engine change; nothing disguise-related (S5 escalation); `run --pin` (engine export).

## Guarantee

`decoy query "SELECT ..." --table NAME=PATH.parquet [--table ...] [--row-limit N]` runs a read-only SQL
query against one or more masked-output Parquet files and prints the result (a table in human mode; a
`{command:"query", status, columns, rows, row_count, truncated}` envelope under `--json`). It is the engine
function verbatim: SELECT-only (anything else → clean `EXIT_USAGE`, not a traceback), Parquet-only, row-
capped by `--row-limit` (default 10000, surfaced as the engine default). No data semantics in the CLI — the
CLI parses `NAME=PATH`, calls `run_discovery_sql`, and renders `DiscoveryResult`.

## Design notes

House style. No new abstraction: a single `query` command in a new `cli/query.py`, registered on the app.
It maps `--table NAME=PATH` pairs into the `tables` mapping `run_discovery_sql` wants and renders the
`DiscoveryResult(columns, rows)`. `DiscoverySqlError` → `EXIT_USAGE` with the engine's message (mirrors how
other commands map typed engine errors). A missing/non-Parquet path → clean `EXIT_USAGE` before the engine
call (the engine is `read_parquet`-only; fail with a readable message naming the file).

## Surface

```
query SQL --table [NAME=]PATH [--table [NAME=]PATH ...] [--row-limit N] [--json|--quiet|--verbose]
```
- `SQL` is the positional statement (quote it in the shell; SELECT never starts with `-`, so no clash).
- `--table NAME=PATH` (repeatable, at least one required) registers each Parquet file under NAME for the
  query's FROM/JOIN.
- **Single-file convenience (P2-3):** `--table PATH` with no `NAME=` infers NAME from the file stem
  (sanitized to a simple identifier), so the common case is `decoy query "SELECT count(*) FROM out"
  --table out.parquet`. **Recorded decision:** the redesign sketch's positional `query OUTPUT "SELECT ..."`
  is NOT adopted — explicit `--table` is faithful to the engine's `Mapping[str,str]`, supports JOINs across
  several outputs, and avoids a magic implied table name; the stem-inference form recovers the one-file
  ergonomics without a second positional.
- `--row-limit N` caps returned rows (default 10000, the engine default). The CLI queries with `row_limit+1`
  and sets `truncated = len(rows) > N`, then trims to `N` for display — an accurate flag (the engine returns
  no truncation signal; P1-1). `row_count` is the trimmed length.

## Slice (single)

- New `cli/query.py`: the `query` command. Parse each `--table` value: `NAME=PATH`, or `PATH` alone (infer
  NAME from the stem, sanitized to a simple identifier); validate NAME is a simple identifier and PATH
  exists + is a file; build the `{NAME: abspath}` mapping; call `run_discovery_sql(sql, tables,
  row_limit=row_limit + 1)` (the +1 for the truncation flag, P1-1); set `truncated`, trim to `row_limit`;
  render `DiscoveryResult.columns`/`.rows` as a Rich table (human) or the `--json` envelope
  `{command:"query", status:"ok", columns, rows, row_count, truncated}`. An empty result renders cleanly
  ("0 rows"). Lazy-import the engine inside the body.
- **Error handling (P1-2, P2-4):** wrap the engine call catching BOTH `DiscoverySqlError` AND `duckdb.Error`
  (import duckdb lazily) — or a broad `except Exception` around the call — because the engine only wraps
  `con.execute(sql)`, so a present-but-non-Parquet/corrupt file raises a raw `duckdb.IOException`/
  `InvalidInputException` from the `read_parquet().create_view()` step. Map all of them to `EXIT_USAGE` with a
  readable message naming the offending file/SQL; under `--json` emit `{command:"query", status:"error",
  error: msg}` BEFORE exiting (house pattern). No traceback reaches the user.
- Register `query` in `__main__.py`; feature a `_ROOT_HELP` line (e.g. `decoy query "SELECT ..." --table
  t=out.parquet`); regen `docs/cli-reference.md`. **Anti-drift (P2-5):** `query` is a new TOP-LEVEL command,
  so BOTH hand-written surfaces must be satisfied — it is featured in `_ROOT_HELP` (above) AND must be a
  deliberate entry in `test_surface_docs_consistency.py`'s `_README_TABLE_OMITTED` (allowlisted like the
  other delight commands `subset`/`fit`, since the README Common-commands table stays curated) or added as a
  README row; otherwise `test_every_top_level_command_is_in_readme_table_or_allowlisted` fails.
- Tests (`tests/e2e/test_query_command.py`): small Parquet fixture; `query "SELECT count(*) AS n FROM t"
  --table t=<fixture>` returns the right count (human + `--json` envelope shape incl. `truncated:false`); the
  `--table PATH` stem-inference form works; a non-SELECT (`DROP`/`INSERT`/`UPDATE`) → `EXIT_USAGE`
  (SELECT-only guard); the **arbitrary-file-read guard** — `SELECT * FROM read_parquet('/etc/passwd')` and
  `... FROM '/etc/passwd'` → `EXIT_USAGE` (engine bans both; the security-relevant path, assert no traceback);
  a **present-but-invalid Parquet** file (e.g. a text file renamed `.parquet`) → `EXIT_USAGE` naming the file
  (the raw-duckdb-error path, P1-2) — distinct from a missing path, which also → `EXIT_USAGE`; `--row-limit`
  trims AND sets `truncated:true` only when the cap is exceeded (not when the result is exactly N); a
  two-`--table` JOIN works; a malformed `--table` (no `=` AND not a readable file) and a non-identifier NAME
  → `EXIT_USAGE`; an empty result renders "0 rows" cleanly.

## Verification

Full `pytest -q` green; `ruff check`; regen reference + the three doc sentries green; test-strength on the
`--table` parsing + the SELECT-only/error mappings.

## Acceptance

- `decoy query` runs read-only SQL over Parquet output via `run_discovery_sql`, rendering a table / `--json`
  envelope; SELECT-only + Parquet-only + row-limit enforced; typed errors → `EXIT_USAGE` (no tracebacks).
- `report fidelity --privacy` is recorded as an engine-export follow-up (not built); `fit` unchanged (or
  help-only polish); no engine change; full suite + ruff + sentries green.

## Loop handoff

Plan-gate review before DEVELOP (confirm the `--table NAME=PATH` surface vs the redesign's `query OUTPUT
"SELECT ..."` sketch; the Parquet-only constraint messaging; the privacy-metrics deferral). On GO: build the
single slice, self-check + verify, independent review, DOCUMENT (and this closes the S1-S6 loop — final
DOCUMENT reconciles the sprint doc + flags the ROADMAP-index follow-up). No merge to main.