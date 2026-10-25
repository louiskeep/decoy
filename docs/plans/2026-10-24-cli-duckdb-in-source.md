# Build plan, DuckDB-in CLI source (B-1 slice)

Status: record (2026-10-24). Part of B-1 (CLI redesign adoption). Additive, pre-GA, CLI-repo-only.
BUILT and gated: dennis GO; Codex GO-WITH-CHANGES with findings remediated (reserved-word / case-variant
quoting, default-schema-only lookup, malformed-tables crash guard, view-trust scope note, multi-table
and reserved-word tests). Pending the final merge to main.

Rules consulted: 00-universal, development-loop, autonomous-operation, risk-and-exceptions, scope-discipline,
documentation, reuse-first, testing, security.

## Premise correction (read first)

The B-1 handoff frames this as "`src/decoy/cli/_sources.py` supports only csv / parquet / fixed_width; add a
`duckdb` input source", i.e. a new source format the CLI reads. **That shape is not CLI-only and will fail
at the gate.** The engine owns `sources:` validation: `decoy_engine.config._sources.SourceDescriptor` is a
closed discriminated union over `type` (`file` / `s3` / `gcs`), each model `extra="forbid"`, and
`FileSource.format` is `Literal["csv", "parquet", "fixed_width"]` (`config/_sources.py:86`). `run_pipeline`
validates `config_dict` against this schema before `cli/_sources.read_source` is ever reached, so a
`type: duckdb` or `format: duckdb` source is rejected at `model_validate`, not dispatched to a new reader.
Adding a real DuckDB source *format* therefore requires an engine change (a new `SourceDescriptor` variant +
`_ADMITTED_SOURCE_FORMATS` in `execution/_unified_slice_admission.py:157`), which is out of the CLI-only
scope the handoff asserts ("entirely in the `decoy` repo, no engine collision").

The CLI-only design below avoids the engine entirely by following the **established DB-input methodology**,
not by inventing a new source format.

## Established solution (cited)

The engine already ships the database-input pattern: `decoy_engine.connectors.postgres_snapshot.
snapshot_tables_to_parquet`, a read-only DuckDB ATTACH that exports structured relations to an **atomic
Parquet set**, then the normal file-based masking runs over that Parquet unchanged. The platform DuckDB-IO
plan states the governing principle (Cam 2026-10-22): "Decoy's database support envelope is exactly what
DuckDB offers natively... Keep database acquisition/publication in narrow, typed primitives... **Reuse
file-based masking unchanged. Do not force database operations into a file-stream protocol.**" S6
`decoy query` uses the same lean: DuckDB over Parquet via the public read-only `run_discovery_sql`.

This slice mirrors that: **acquire the DuckDB relation to a temporary Parquet via DuckDB's own
read-only engine, rewrite the in-memory source to that Parquet, then mask it on the existing parquet path.**
No new engine format; no raw-user-SQL surface (postgres_snapshot's "structured identifiers, no raw user SQL").

Risk: R2 (additive CLI flag; no engine change; worker-branch; no merge). DuckDB is already a declared CLI
dependency (`pyproject.toml:102`, `duckdb>=0.9`); the read is a read-only connection; no outward write.

## Guarantee

`decoy run pipeline.yaml --duckdb-source TABLE=DB_PATH [--duckdb-source ...]` masks a pipeline whose input
table(s) come from a DuckDB database file instead of a CSV/Parquet/fixed-width file. For each flag the CLI
opens `DB_PATH` **read-only**, copies the relation named `TABLE` to a temporary Parquet file (DuckDB owns the
type mapping, as in postgres_snapshot), rewrites `config_dict["sources"][TABLE]` to
`{type: file, format: parquet, path: <tmp>}` before validation/run, and the pipeline proceeds exactly as a
parquet run. Everything downstream, schema validation, native-on eligibility, `--chunked`, output writing,
evidence, is unchanged because the source the engine sees is an ordinary parquet file.

## Surface

```
run PIPELINE.yaml --duckdb-source TABLE=DB_PATH [--duckdb-source TABLE2=DB_PATH2 ...]
```
- `--duckdb-source TABLE=DB_PATH` (repeatable). `TABLE` must be a simple identifier matching a table declared
  in the pipeline's `tables:`; `DB_PATH` is a `.duckdb` file. The relation read from the DB is the one named
  `TABLE` (relation name == pipeline table name, the common, unambiguous case).
- **Relation-name only in v1 (no raw SQL).** Matching postgres_snapshot's "no raw user SQL / structured
  identifiers", v1 reads a named relation via a parameter-bound identifier, never a user SQL string. This
  removes the SQL-injection / arbitrary-file-read (`read_parquet('/etc/..')`, `ATTACH`) surface entirely.
  A `--duckdb-sql TABLE="SELECT ..."` projection form is recorded as a **deferred follow-up** (would reuse the
  engine's SELECT-only allowlist, same as S6; not built here).
- The flag **overrides** any `sources[TABLE]` the YAML declares; a flag naming a `TABLE` with no matching
  `tables:` entry, or a YAML `sources[TABLE]` that conflicts with a flag, is a clean `EXIT_USAGE`.
- Interaction: works on both the default and `--chunked` paths (the temp Parquet streams via the existing
  `iter_source_chunks` parquet branch). Native-on is unaffected (the rewritten source is parquet, already in
  `_NATIVE_SOURCE_FORMATS`), so the native loud-refusal contract is preserved with no `_native_gate` change.

## Mechanism

New `src/decoy/cli/_duckdb_source.py` (thin, CLI-local; the engine stays narrow):
- `acquire_duckdb_relation(db_path: Path, relation: str, dest_dir: Path) -> Path`: lazy `import duckdb`;
  `con = duckdb.connect(str(db_path), read_only=True)`; verify the relation exists via a parameter-bound
  lookup against `duckdb_tables()`/`information_schema` (never string-concatenated into SQL); `COPY "<ident>"
  TO '<tmp>.parquet' (FORMAT PARQUET)` with the identifier quoted/escaped by DuckDB's own quoting, written to
  a temp file then returned. Read-only connect refuses a DB that would need a write lock and never mutates the
  source. Errors (`duckdb.Error`, missing file, unknown relation, read-only-open failure) are caught and
  re-raised as a typed CLI usage error with a readable, path-safe message, never a traceback (mirrors S6
  P1-2 and postgres_snapshot's redacted errors: no connection string, no cell values).
- Temp Parquet lifecycle: write under a run-scoped temp dir (`tempfile.mkdtemp`), cleaned in a `finally`
  after the run; the atomic-publication posture is the engine primitive's, not re-implemented here (single
  local file, created-then-used).

Wiring in `cli/run.py`:
- Add the repeatable `--duckdb-source` option. Immediately after `raw_cfg = _load_raw_config(config)` and
  before the chunked/non-chunked branch (and before schema validation), resolve each flag: parse `TABLE=PATH`
  (reuse the S6 `NAME=PATH` parsing idiom), acquire the Parquet, and set
  `config_dict["sources"][TABLE] = {"type": "file", "format": "parquet", "path": <abs tmp path>}`.
  Validation and both run paths then see a plain parquet source.
- No change to `_sources.py`, `_native_gate.py`, `_write_mask_outputs`, or the engine.

## Slices

1. **`_duckdb_source.py` + flag wiring.** The acquisition helper, the `--duckdb-source` option, config rewrite
   before validation, temp-dir lifecycle, typed-usage-error mapping. `--duckdb-source` featured in the run
   help body; regen `docs/cli-reference.md`.
2. **Tests** (`tests/e2e/test_duckdb_source.py`): build a `.duckdb` fixture with a known table; (a) a run with
   `--duckdb-source t=fixture.duckdb` masks the table and writes output equal to the same data masked from a
   parquet source (parity); (b) `--json` run-record shape unchanged; (c) missing DB file → `EXIT_USAGE`, no
   traceback; (d) unknown relation → `EXIT_USAGE` naming the relation, no traceback; (e) a `TABLE` with no
   `tables:` entry → `EXIT_USAGE`; (f) `--chunked` run over a duckdb source works (temp parquet streams);
   (g) native eligibility is unchanged (the rewritten source counts as a native parquet source); (h) the
   source `.duckdb` file is not modified (read-only); (i) the temp Parquet is cleaned up after the run;
   (j) a non-identifier `TABLE` and a malformed flag value → `EXIT_USAGE`. Assertion test (parity, case a)
   lands first.

## Verification

Full `pytest -q` green; `ruff check`; `mypy` per the repo baseline; regen the CLI reference + run the doc
sentries (new top-level flag, not a new command, so no README-table sentry entry, confirm
`test_surface_docs_consistency.py` still passes); test-strength on the flag parsing, the read-only guarantee,
and the typed-error mappings.

## Acceptance

- `decoy run --duckdb-source TABLE=DB_PATH` masks a DuckDB-sourced table by acquiring it read-only to a temp
  Parquet and running the unchanged parquet path; default + `--chunked` + native-on all work with no engine
  change; typed errors → `EXIT_USAGE` (no tracebacks); the source DB is never written; temp files cleaned.
- Raw-SQL projection (`--duckdb-sql`) recorded as a deferred follow-up; no engine/`_sources.py` change.

## Open questions for the plan gate

1. **Flag token syntax.** `--duckdb-source TABLE=DB_PATH` (relation name == table name) vs. an explicit
   relation selector (`TABLE=DB_PATH#RELATION`) for when the DB relation name differs from the pipeline table
   name. Recommendation: ship name==name in v1; add `#RELATION` only if a real case needs it.
2. **Raw SQL in v1 or deferred?** Plan defers it (security + methodology). Confirm, or pull it in with the
   engine SELECT-only allowlist reused (not re-implemented).
3. **Reuse vs CLI-local acquisition.** This plan keeps a thin CLI-local `COPY ... TO parquet` rather than
   adding a generic `duckdb_snapshot` engine primitive. Confirm that's the right boundary (postgres_snapshot
   is Postgres-specific; a generic local-DuckDB snapshot could live in the engine later if the platform needs
   it too, but that would be an engine task, not this CLI slice).
4. **Scope intent.** Confirm "DuckDB-in" means *read an input table from a DuckDB database file* (this plan),
   vs. "use DuckDB to read other files" (which the parquet/csv paths already cover), the handoff is terse.
5. **Premise.** Confirm the engine-schema finding above so B-1's row and the handoff are corrected (no
   `_sources.py` format addition).

## Loop handoff

Plan-gate (dennis + Codex) before DEVELOP, focused on the 5 questions above and the premise correction. On
GO: Sonnet builds slice 1 then slice 2, self-check + verify, independent review, DOCUMENT. No merge to main
(orchestrator runs the gates and merges). A cloud worker cannot post the Slack pre-push flag, that step is
the orchestrator's.

cam
