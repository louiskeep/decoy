# Frozen surfaces

Status: current

What freezes at 1.0.0 and which test or snapshot pins it. `tests/sentry/release/test_frozen_surface_map.py`
reads this table: every path in the last two columns must exist, every item of the "Public surface" list in
[versioning.md](versioning.md) must have a row, and so must each name in `exit_codes.__all__`, each lazy export of
`src/decoy/__init__.py` and each file in `docs/schemas/`. A row with no test says
`accepted-known-limit: <V2-LOG id>` instead, and the readiness record lists it.

The "Hidden commands and options" row lists each hidden command and option as `name: tier`, with tier `internal` (a `_` command, outside the contract) or `frozen-hidden` (frozen like a visible name). The sentry for that row walks the live command tree and fails on a hidden name with no span or a span with no hidden name.

The engine's own map is `docs/frozen-surfaces.md` in the engine repo.

| Surface | Completeness source | Owning code | Pinning test or snapshot |
|---|---|---|---|
| Command and flag set | versioning.md item 1 | `src/decoy/__main__.py` | `tests/unit/test_cli_surface.py` (against `docs/cli-reference.md`) |
| Exit-code integers 0 to 6 and 130, `RUN_EXIT_MAP`, `PRECEDENCE`, the `EXIT_*` constants | versioning.md item 2, `exit_codes.__all__` | `src/decoy/cli/exit_codes.py` | `tests/unit/test_exit_codes.py`, `tests/unit/test_exit_code_registries.py`, `tests/e2e/test_run_exit_map.py`, `tests/sentry/cli_text/test_exit_code_docs.py` |
| YAML pipeline schema (engine-owned) | versioning.md item 3 | engine `PipelineConfig` | the engine snapshot (engine map); in the CLI `tests/e2e/test_schema_command.py` |
| `--json` success shapes, per command | versioning.md item 4, the `--json` leaf commands | `src/decoy/cli/` | `tests/e2e/release_freeze/test_json_shapes.py`, `tests/fixtures/release_freeze/json-shapes.json` |
| `--json` error object | versioning.md item 4, `docs/schemas/decoy-error-v1.schema.json` | `src/decoy/ui/output.py` | `tests/unit/test_ui_emit_error.py`, `tests/e2e/first_user/test_items_error_envelope.py`; gate and warning reason codes (`GATE_CODES`, `WARNING_CODES`, `_CLI_GATE_CODES`, owned by `src/decoy/cli/io/_layout_errors.py` and `src/decoy/ci/rule_codes.py`): `tests/sentry/io_policy/test_layout_errors.py`, every other reason code, including `CLI_WARNING_CODES`, is not pinned (a known limit) |
| Bundled template set | versioning.md item 5 | `src/decoy/templates/` | `tests/e2e/test_release_smoke.py`, `tests/unit/test_bundled_templates.py` |
| CI manifest | `docs/schemas/decoy-ci-v1.schema.json` | `src/decoy/ci/` | `tests/unit/test_ci_manifest.py` |
| Python API: `mask`, `scan`, `MaskSecretConfigError`, `ConfigValidationError`, `UnsupportedCloudEndpointError` | `_LAZY_API` in `src/decoy/__init__.py` | `src/decoy/api.py` | `tests/unit/test_api.py` (the signature tests pin `mask` and `scan`), `tests/unit/api_scan/` (`scan` returns the same document as `decoy scan --output`) |
| Version document and installer contract (tags `cli-version-document/v1`, `cli-bundle-manifest/v1`) | `src/decoy/distribution/` | `src/decoy/distribution/` | `tests/unit/test_distribution.py`, `tests/unit/test_distribution_acceptance.py`, `tests/unit/test_version_document_schema.py` |
| `cli-local-1` evidence payload | the evidence writer | `src/decoy/cli/evidence.py` | `tests/unit/test_evidence.py` |
| CLI version literal | `src/decoy/_version.py` | `src/decoy/_version.py` | `tests/unit/release/test_version_agreement.py` |
| `decoy-ci/v1` CI manifest tag | tag census | `src/decoy/ci/contracts.py` | `tests/unit/test_ci_manifest.py` |
| `decoy-ci-report/v1` CI report tag | tag census | `src/decoy/ci/__init__.py` | `tests/unit/test_ci_reporting.py` |
| `primary/v1` SARIF fingerprint key | tag census | `src/decoy/ci/reporting.py` | `tests/e2e/test_ci_sarif.py` |
| `decoy-project/v1` project marker kind | tag census | `src/decoy/cli/io/_project.py` | `tests/unit/project_layout/test_layout.py` |
| `scan-set/v1` saved scan tag | tag census | `src/decoy/cli/io/_scan_set.py` | `tests/e2e/test_scan_command.py` |
| Tag literals built with f-strings or concatenation | tag census | `tests/sentry/release/_tags.py` | accepted-known-limit: S7B-KL-1 |
| Hidden commands and options | `scan _scan: internal`; `validate _gate: internal`; `upgrade --url: frozen-hidden`; `ci check --unsafe-debug-log: frozen-hidden`; `run --sample: frozen-hidden`; `run --sample-root: frozen-hidden` | `src/decoy/cli/scan.py`, `src/decoy/cli/validate.py`, `src/decoy/cli/upgrade.py`, `src/decoy/cli/ci.py`, `src/decoy/cli/run/__init__.py` | `tests/sentry/release/test_hidden_names.py` |
| Public renames before 1.0 (pointer to the engine contract) | the engine taxonomy rename | `docs/release/public-renames.md` | `tests/sentry/release/test_retired_name_residual.py` |

## Limits of the `--json` snapshot

The snapshot holds key paths and JSON types, never a cell value. Object keys that carry data (a map keyed by
table or column name) are declared per command and collapse to `*`. Two lists keep "content varies by host"
apart from "key may be absent". An opaque key (`run` `/warnings`, `info` `/native_companion`) is always present
and only its content varies, so the snapshot pins its declared type (`array`, `null|object`) and a run that loses
the key changes the snapshot. An optional key (`run` `/native_route`, `/notify`, `/report`, `/subset`) may be
absent, depending on the flags used, and is left out, so the snapshot covers the listed paths only. The fixture run also pins `run` `outputs` and `output_dir` (set in `run/_context.py`) and the nullable `project` and `pipeline` (set in `_layout.py`) as present, which is stricter than the CLI's contract. Commands with no good input
in a test environment (`doctor`, `schema`, `setup`, `upgrade`) carry a stated exemption. Regenerate with
`python -m tests.e2e.release_freeze.write_shapes`, review the diff, and add a `CHANGELOG.md` entry: the
`shape-changelog` CI job refuses a pull request that changes the snapshot without one.
