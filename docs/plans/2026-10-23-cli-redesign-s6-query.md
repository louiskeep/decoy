# S6 build plan — `decoy query` (+ privacy-metrics deferral)

Status: build plan, PRE-RELEASE (2026-10-23). Sixth/final sprint of the CLI redesign
(`docs/plans/2026-10-23-cli-redesign-sprints.md`). Additive (one new command), pre-GA. Awaiting plan-gate.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, scope-discipline,
documentation, reuse-first, testing.

Risk: R2 (additive CLI command surfacing an existing public engine function; no engine change;
feature-branch; no merge). The engine function is read-only and hardened (SELECT-only allowlist); the CLI is
a thin wrapper.

## Scope

Ship the cleanly-public fast-follow and defer the rest:
- **SHIP `decoy query`** — read-only SQL over masked Parquet output via the public
  `decoy_engine.run_discovery_sql(sql, tables, *, row_limit) -> DiscoveryResult` (in
  `decoy_engine.__all__`; SELECT/WITH/VALUES/TABLE-only, in-memory DuckDB, `read_parquet` views).
- **DEFER `report fidelity --privacy`** (DCR / new-row-synthesis / membership-inference metrics): the engine
  `quality` compute surface (`compute_dcr`/`compute_attack_metrics`/`compute_quality_report`/...) is NOT in
  `decoy_engine.__all__` (confirmed). Like `list detectors` and `scan --suggest`, this needs an additive
  engine export first, then a one-flag CLI slice. Owner/engine follow-up.
- **`fit` polish** (minor): tighten `fit`'s help to state its relationship to generate-mode + the DP knobs.
  No behavior change. Optional — fold in only if trivial; otherwise leave `fit` as-is (it already works).

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
query SQL --table NAME=PATH [--table NAME=PATH ...] [--row-limit N] [--json|--quiet|--verbose]
```
- `SQL` is the positional statement (quote it in the shell).
- `--table NAME=PATH` (repeatable, at least one required) registers each Parquet file under NAME for the
  query's FROM/JOIN. (Single-table is the common case: `--table t=out.parquet`, then `... FROM t`.)
- `--row-limit N` caps returned rows (passes through; default 10000). The result notes truncation when the
  cap is hit.

## Slice (single)

- New `cli/query.py`: the `query` command. Parse each `--table` value as `NAME=PATH`; validate `NAME` is a
  simple identifier and `PATH` exists + is a file (and, defensively, looks like Parquet — `.parquet`/`.pq`
  or let the engine error surface); build the `{NAME: abspath}` mapping; call
  `run_discovery_sql(sql, tables, row_limit=row_limit)`; render `DiscoveryResult.columns`/`.rows` as a Rich
  table (human) or the `--json` envelope. Map `DiscoverySqlError` → `EXIT_USAGE` with its message; an empty
  result renders cleanly ("0 rows"). Lazy-import the engine inside the body.
- Register `query` in `__main__.py`; add a `_ROOT_HELP` line (e.g. `decoy query "SELECT ..." --table
  t=out.parquet`); regen `docs/cli-reference.md`; keep the three doc sentries green (add `query` to the
  consistency allowlists if it is not featured).
- Tests (`tests/e2e/test_query_command.py`): write a small Parquet fixture; `query "SELECT count(*) AS n
  FROM t" --table t=<fixture>` returns the right count (human + `--json` envelope shape); a non-SELECT
  statement (`DROP`/`INSERT`/`UPDATE`) → `EXIT_USAGE` (SELECT-only guard); a missing/non-Parquet path →
  `EXIT_USAGE` with the file named; `--row-limit` truncates + flags truncation; a two-`--table` JOIN works; a
  malformed `--table` value (no `=`) → `EXIT_USAGE`.

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