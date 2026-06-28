# Changelog

All notable changes to the `decoy-cli` PyPI distribution (which ships
the `decoy` import package + the `decoy` console script) land here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
version numbers follow the [versioning policy](docs/release/versioning.md).

## [Unreleased]

### Added (SP-16 CLI foundation, 2026-06-28)

- **`decoy validate --fail-on-warning`**: exits non-zero (code 2) when any
  advisory warning fires. Enables CI gates that treat warnings as blocking.
  Current warnings: output target file already exists (overwrite advisory).

- **`decoy validate --json` multi-message output**: the JSON envelope now
  includes a `messages` list with ALL validation messages
  (`severity`/`code`/`message`/`location`), not just the first error string.
  Pydantic `ValidationError` with multiple field failures now surfaces all of
  them at once. Backward-compatible: the top-level `error` string key is
  preserved for error responses.

- **`decoy storm analyze --format parquet|fixed-width|delimited`**: explicit
  format selector for the STORM analyzer. Format is also inferred from file
  extension (`.parquet`/`.pq` -> parquet; `.fwf`/`.dat`/`.fixed`/`.fw` ->
  fixed-width; everything else -> delimited/CSV).

- **`decoy storm analyze` Parquet support**: `.parquet` files are now read via
  `pd.read_parquet` (pyarrow is a core engine dependency). Sampling
  strategies (`--rows`, `--strategy`) apply after load.

- **`decoy storm analyze --layout <layout.yaml>`**: fixed-width input support
  behind an explicit layout spec (column name + start offset + width). Layout
  can be YAML or JSON. Fixed-width without `--layout` fails closed with a
  clear, actionable error -- column boundaries are ambiguous without a spec.

### Added (capability gaps, 2026-06-12)

- **`decoy run --chunked [--chunk-size N]`** (streaming). Streams each
  mask table's CSV source through the engine chunk-by-chunk (default
  100k rows) for inputs too large for memory; output is byte-identical
  to a plain run. Only value-keyed strategies qualify (hash, fpe,
  redact, truncate, text_redact, date_shift, bucketize); anything else
  exits 1 with the engine's typed rejection before any rows process.
  CSV sources only in v1.

- **`decoy fit` verb** (statistical synthesis). Fits a
  distribution-snapshot/v1 artifact from a source CSV
  (`--parse-dates` for datetime columns, repeatable `--joint a,b` for
  the contingency tables `condition_on` needs). The snapshot is what
  `type: statistical` generate columns reference via `snapshot_file`;
  `decoy validate` now rejects configs whose snapshot artifact is
  missing or incompatible (engine check row 12).

- **`decoy unmask` verb** (detokenization). Recovers `strategy: fpe`
  columns from a masked CSV using the same pipeline config the mask run
  used; the config's seed + per-column namespace re-derive the Feistel
  key (engine SEED_PROTOCOL_VERSION 5, single key per seed+namespace).
  One-way strategies (hash, redact, faker, ...) pass through unchanged
  with an `irreversible` entry in the per-column report (`--json` for
  the structured form). SECURITY: the config now functions as the
  decryption key for its fpe columns; handle accordingly.

### Fixed (audit remediation, 2026-06-12)

Findings from the 2026-06-11 full-codebase audit.

- **hipaa/pci/gdpr templates rewritten and no longer dead-on-arrival**
  (audit H5 + H12). All three crashed at `decoy run` on any input
  (faker on the non-poolable uuid provider). Templates are now derived
  from the engine's dated disguises and carry an
  `x-derived-from-disguise: <id>@<version>` marker enforced by a
  drift-guard test: hipaa upgrades ssn/mrn/account/vehicle to
  format-preserving encryption and dates to keyed date_shift (joins and
  intervals survive); pci PANs are FPE'd with Luhn-valid output and
  transaction ids hash-pseudonymised; gdpr device ids
  hash-pseudonymised per Art 4(5). A new E2E net runs EVERY bundled
  template against synthesized data on every CI run.
- **`decoy validate` now runs the engine's config-only plan checks**
  (audit H5): unknown providers, non-poolable faker providers, and
  missing deterministic namespaces fail validate with the typed code
  instead of passing schema-only and crashing at run.
- **Typed exit codes** (audit H10): engine config errors
  (PlanCompileError / PipelineValidationError / ConfigError) exit
  EXIT_USAGE(1) per the documented contract; runtime crashes stay
  EXIT_RUNTIME(3).
- **Mixed mask+generate configs rejected** (audit H11): previously they
  exited 0 while silently writing no output for the generate tables.
- **`storm integrity` exit 4 is reachable** (engine audit C1/H6): a
  masked file identical to its source now fails with a residual_pii
  'fail'; E2E locks both directions.
- **Config parsed once per `decoy run`** (audit L3; was up to 4 parses).
- **ruff clean** (audit L4: 13 errors cleared, zero-error gate).

### Added

- OSS.3 packaging metadata: PyPI Trove classifiers, keywords, project
  URLs, and the distribution rename to `decoy-cli` (per Q-OSS-1 RESOLVED
  2026-06-01). The import package + console script + the `decoy-engine`
  dependency are unchanged.
- This `CHANGELOG.md` itself, plus the `docs/release/versioning.md`
  semver policy doc.
- **Generated CLI reference** (`docs/cli-reference.md`, produced by
  `python -m typer decoy.__main__ utils docs`). A
  `tests/unit/test_cli_surface.py` drift guard fails CI when the command or
  flag surface changes without the reference being regenerated.

### Changed

- Help-text accuracy pass: root and `storm test` help no longer reference the
  old `storm scan` verb (now `storm analyze`); the `templates` help example no
  longer shows the removed `graph` template; `explain modes` help no longer
  lists the removed `convert`/`graph` modes; `explain transforms` notes the full
  12-strategy set instead of claiming "eight"; `CODEMAP.md` drops the removed
  `forecast` command / `forecast.py`.
- PyPI distribution name: `decoy` -> `decoy-cli` (Q-OSS-1). Existing
  `pip install decoy` continues to work today (the bare name is still
  reserved, just not pursued as a launch-blocker); future installs
  should use `pip install decoy-cli`.

## [0.1.0] - 2026-06-02

The first publishable cut of the CLI. Not yet pushed to the real PyPI
index; first publish lands with OSS.7.

### Added

- OSS.1 release gate: `.github/workflows/release-smoke.yml` builds the
  wheel + installs into a clean Python 3.10 / 3.11 / 3.12 venv + runs
  `decoy --version`, `decoy demo --json`, and the canonical `decoy run`
  cell against the bundled minimal template. Manual runbook lives at
  `docs/release/fresh-install-smoke.md`.
- Centralized exit-code contract: `decoy.cli.exit_codes` exports
  `EXIT_OK` (0), `EXIT_USAGE` (1), `EXIT_DEPRECATED_SHIM` (2), and
  `EXIT_RUNTIME` (3). Integer values stable across releases; full table
  at `decoy explain exit-codes`.
- V2-shape bundled examples (`examples/mask_example.yaml` +
  `examples/generate_example.yaml`) with a parametrized validation gate.
- CLI.1-4: rewired `decoy --help`, `decoy run`, `decoy demo`,
  `decoy validate`, `decoy plan` against the V2 engine spine
  (`PipelineConfig.model_validate` -> `compile_plan` ->
  `select_execution_adapter`). Pre-CLI.1 the entire CLI raised
  ImportError at module load against the post-S22 engine.
- FC-1 schema alignment: the top-level `mode:` field is gone (engine
  FC-1 dropped it); `decoy run --mode mask|generate` flag is still
  accepted as a hint, but the actual mode is inferred per-table from
  `columns` (mask) vs `generate_columns` (generate) presence. Bundled
  templates + examples + the demo's emitter all updated.

### Fixed (from QA review docs/qa/review-2026-06-02-cli-v2-migration.md)

- F2: stale `FORECAST` mention in `demo.py` module docstring (the
  legacy recommender was retired under storm-reframe-C).
- F3: `plan.py::_empty_profile_for_no_profile` now uses POSIX epoch as
  a "no real profile" sentinel instead of a hardcoded slice date.
- F5: orphan V1-shape YAML builders in `demo.py` carry per-function
  `# V1 SHAPE -- replace with V2 PipelineConfig before wiring to --ref`
  warnings + a top-of-block fence comment.
- F6: `demo.py::_build_pipeline_yaml` builds a dict and serializes via
  `yaml.safe_dump` instead of f-string templating; a path with a single
  quote (e.g. `--dir "O'Hare_demo"`) no longer crashes.
- F7: `decoy run` + `decoy demo` no longer swallow inner `typer.Exit`
  into the EXIT_RUNTIME catch-all.
- F8: JSON error envelopes truncate engine exception messages at 500
  chars to bound log growth + reduce PII risk.
- F9: `decoy validate` reports "Pipeline YAML is empty." on an empty
  file instead of the unhelpful "must be a YAML mapping, not
  NoneType."
- F10: bare `assert` in `plan.py` replaced with `RuntimeError` so the
  invariant cannot be stripped by `python -O`.
- F11: deleted unused `import os` in `run.py`.
- F12: added "See also:" blocks to `decoy plan --help` and
  `decoy replan --help` epilogs.
- F13: `decoy explain pipeline` topic body leads with the V2 shape;
  the V1 shape is demoted to a "Legacy V1 shape (REJECTED by
  `decoy validate`)" footnote.
- F14: deleted no-op `run.__doc__ = run.__doc__` self-assignment.

### Deferred

- F1 (~150 LOC dispatch dedup between `run.py` and `demo.py`): real
  refactor; should land alongside an `_dispatch.py` extraction.
- F4 (run.py triple YAML read on hot path): real refactor; threads
  the parsed raw dict through `_detect_mode` + `_detect_key_label` +
  the spinner body.

Tracked in `decoy/PLAN.md` so they do not rot.

[Unreleased]: https://github.com/louiskeep/decoy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/louiskeep/decoy/releases/tag/v0.1.0
