# Decoy CLI Codemap

## One-Line Project Summary

Installable Typer/Rich CLI that wraps `decoy-engine` for local validation, runs, STORM/FORECAST, templates, examples, and terminal UX.

## Tech Stack

| Area | Stack |
|---|---|
| Runtime | Python 3.10 |
| CLI | Typer, Rich |
| Engine | Imports sibling/package `decoy-engine` |
| Tests | pytest, Typer CliRunner/subprocess e2e |

## Entry Points

| Path | Purpose |
|---|---|
| `src/decoy/__main__.py` | Typer app and command registration |
| `src/decoy/cli/` | Command modules |
| `src/decoy/ui/` | Rich output helpers |
| `examples/` | Sample configs |

## Directory Map

| Path | What Lives Here |
|---|---|
| `src/decoy/cli/` | `run`, `validate`, `plan`, `storm`, `init`, `demo`, `explain`, `info`, `upgrade`, `templates`, `tokenize`/`detokenize` commands |
| `src/decoy/cli/ci.py` | `decoy ci check`: flags and report file I/O only (F43) |
| `src/decoy/ci/` | CI integration layer: `contracts` (manifest + value-free finding boundary), `manifest` (strict loader/schema), `locations` (YAML marks), `adapters` (thin wrappers over existing checks), `staged` + `_git` (bounded Git-index scan), `reporting` (JSON/SARIF/Markdown), `runner`, `debug` |
| `src/decoy/cli/_token_vault.py` | Local SQLite token vault (the engine's `TokenVaultWriter` seam, B-1) |
| `src/decoy/distribution/` | Shipped verify + update machinery (Ed25519 verify, bundle manifest, version-document contract, `~/.decoy` layout, native self-check, `decoy upgrade` installer core) |
| `packaging_tools/` | Build-host release pipeline (bundle assembler, signing, install scripts, version-document generator, smoke) -- NOT shipped in the wheel |
| `src/decoy/ui/` | Theme, output state, progress, tables, cards |
| `src/decoy/templates/` | Packaged YAML templates |
| `examples/` | Example YAML configs |
| `tests/` | CLI tests |
| `docs/` | CLI docs, plus the one Decoy roadmap (`docs/ROADMAP.md`, `docs/roadmap/`) and the shipped log (`docs/RECENTLY-SHIPPED.md`) |
| `logs/`, `.pytest_cache/`, `__pycache__/` | Ignore generated/runtime content |

## Where Things Go

One row per kind of module. Path cells are checked by `tests/sentry/layout/test_codemap_paths.py`: a concrete path must exist, a `<placeholder>` or `*` checks the parent before it, and `(target)` marks a path that does not exist yet (only its parent is checked). Where today's tree differs from the rule, the row states the rule and names the exception. The layer contracts (`.importlinter`) are not built yet; their row is marked `(target)`.

| Kind | Goes in | File naming | Tests | Sentries and registries |
|---|---|---|---|---|
| Command module | `src/decoy/cli/`; new commands go in a named sub-package below it (the flat folder is frozen at 30 modules by `tests/sentry/layout/test_package_fanout.py`) | `src/decoy/cli/<command>.py` today; `src/decoy/cli/<command>/_<noun>.py` for new work, as in `src/decoy/cli/setup/` (`decoy setup`) | `tests/e2e/test_<command>*.py` using CliRunner or subprocess; `tests/unit/` | commands register in `src/decoy/__main__.py`; `tests/unit/test_cli_surface.py` |
| Command-private helpers | a named sub-package below `src/decoy/cli/` for new work | `src/decoy/cli/<command>/_<noun>.py`; flat `src/decoy/cli/_<name>.py` is the current exception | `tests/unit/` | - |
| `decoy run` internals (phases, error arm, summary, evidence, notifications, vault commit) | `src/decoy/cli/run/`; `src/decoy/cli/run/__init__.py` keeps only the options, `_RUN_EPILOG` and the re-exports | `src/decoy/cli/run/_<noun>.py`: `src/decoy/cli/run/_prepare.py`, `src/decoy/cli/run/_execute.py`, `src/decoy/cli/run/_errors.py`, `src/decoy/cli/run/_render.py`, `src/decoy/cli/run/_evidence.py`, `src/decoy/cli/run/_notify.py`, `src/decoy/cli/run/_vault.py`, `src/decoy/cli/run/_flow.py` (order of the phases), `src/decoy/cli/run/_context.py` (`RunContext`, the state they share) | `tests/e2e/`, `tests/unit/` | `tests/sentry/layout/test_run_package_shape.py` (thin `__init__`, 600-line cap, import order, no private imports) |
| `decoy scan` internals (argument resolution, engine call, card and `--json`) | `src/decoy/cli/scanning/`; `src/decoy/cli/scan.py` keeps only the options | `src/decoy/cli/scanning/_<noun>.py`: `src/decoy/cli/scanning/_multi.py` | `tests/e2e/`, `tests/unit/` | - |
| Pre-run check gate shared by `validate`, `ci check` and `run` | `src/decoy/cli/gate/` | `src/decoy/cli/gate/_<noun>.py`: `src/decoy/cli/gate/_layers.py` (layers and entries), `src/decoy/cli/gate/_run.py` | `tests/unit/test_gate_*.py`, `tests/e2e/test_run_validate_always.py`; generate-column option checks in `tests/e2e/generate_config/` (new ones go here, not the flat `tests/e2e/`) | `tests/sentry/test_gate_single_entry.py` |
| Source readers and target writers (owner rule 2026-11-06: new ones go here from now on) | `src/decoy/cli/io/` | `src/decoy/cli/io/_<noun>.py`: `src/decoy/cli/io/_targets.py`, `src/decoy/cli/io/_scan_set.py`, `src/decoy/cli/io/_compression.py`; today's exception `src/decoy/cli/_sources.py` moves here under H-1 | `tests/unit/cli_fmt/`, `tests/e2e/cli_fmt/` | `tests/sentry/io_policy/`; `tests/sentry/baselines/target-writes-allow.json` |
| Project layout services: project root finder and `.decoy/` setup, pipeline names and claims, run folders, `out/`, the Windows path budget, the `layout.*` descriptors. Everything outside `src/decoy/cli/io/` imports them from the public `decoy.cli.io` package | `src/decoy/cli/io/` | `src/decoy/cli/io/_project.py` (the only reader of `decoy.yaml`), `src/decoy/cli/io/_layout.py`, `src/decoy/cli/io/_placement.py` (the gate's output placement and the one collision rule), `src/decoy/cli/io/_layout_errors.py` (the only home of a `layout.*` code), `src/decoy/cli/io/_pipelines.py` (the only parser of a pipeline token) | `tests/unit/project_layout/`, `tests/e2e/project_layout/` (new ones go here, not the flat `tests/unit/` and `tests/e2e/`) | `tests/sentry/io_policy/test_layout_errors.py` (one `layout.*` registry), `tests/sentry/io_policy/test_pipeline_argument.py` (one project root finder; G-ONE-PIPELINE-ARG, one pipeline token parser) |
| Local record library (LIB): root rule, store, and later refs, index, scratch and logs; commands import the facade, never its `_` modules | `src/decoy/cli/library/` | `src/decoy/cli/library/_<noun>.py`: `src/decoy/cli/library/_paths.py` (root rule, names, Windows budget), `src/decoy/cli/library/_fs.py` (calls `_private_file` and `_atomic` only), `src/decoy/cli/library/_errors.py`, `src/decoy/cli/library/_store.py` (`put`, `resolve`) | `tests/unit/library/` | `tests/sentry/io_policy/test_library_writer.py` (G-LIB-WRITER), `tests/sentry/io_policy/test_canonical_json.py` (G-ONE-CANONICAL) |
| Generation CLI helpers (the exact fit shared by `fit` and `init`, the `run --rows` preview, the CSV generate scaffold; the flat `cli/` is frozen) | `src/decoy/cli/gen/`; commands import the package facade, never its `_` modules | `src/decoy/cli/gen/_<noun>.py`: `src/decoy/cli/gen/_fit.py`, `src/decoy/cli/gen/_preview.py`, `src/decoy/cli/gen/_scaffold.py`, `src/decoy/cli/gen/_topic.py` | `tests/e2e/first_user/`, `tests/unit/` | - |
| Exit codes | `src/decoy/cli/` | `src/decoy/cli/exit_codes.py` | `tests/unit/test_exit_codes.py` | `src/decoy/ci/` and `src/decoy/ui/` import it from a lower tier: ignore lines in `.importlinter`, to drop when it moves below them |
| Python API | `src/decoy/` | `src/decoy/api.py` | `tests/unit/test_api.py` | - |
| CI integration | `src/decoy/ci/`; wrapper command `src/decoy/cli/ci.py` | `src/decoy/ci/<concern>.py` | `tests/unit/test_ci_*.py`, `tests/e2e/test_ci_*.py` | `tests/sentry/test_ci_output_isolation.py`, `tests/sentry/test_ci_r2_leak_paths.py` |
| Terminal output | `src/decoy/ui/`; run card extras, warning lines and `report fidelity` text in `src/decoy/ui/summary.py` | `src/decoy/ui/<concern>.py` | `tests/unit/test_ui_summary.py`, `tests/e2e/test_card_and_progress.py` | `tests/sentry/test_one_stderr_console.py` |
| User-facing CLI text and crash handling | `tests/sentry/cli_text/` for new sentries, not the flat `tests/sentry/` | `tests/sentry/cli_text/test_<rule>.py`; helper `tests/sentry/cli_text/_<name>.py` | self-tests and seeded mutations in the same file | `tests/sentry/cli_text/test_no_traceback_escape.py` |
| Shipped install and update | `src/decoy/distribution/` | `src/decoy/distribution/<concern>.py` | `tests/unit/test_distribution.py` | - |
| Build-host release tools (not shipped in the wheel) | `packaging_tools/` | `packaging_tools/<concern>.py` | `tests/unit/test_release_smoke_workflow.py` | - |
| Packaged templates | `src/decoy/templates/` | `src/decoy/templates/<name>.yaml` | `tests/unit/test_bundled_templates.py`, `tests/e2e/test_bundled_templates_e2e.py` | `tests/unit/test_template_disguise_drift.py` |
| Private shared filesystem or process primitives used by more than one package | `src/decoy/` | `src/decoy/_<noun>.py`: `src/decoy/_atomic.py`, `src/decoy/_private_file.py` (owner-only creation and every mode change), `src/decoy/_mask_secret.py`, `src/decoy/_native_gate.py`, `src/decoy/_version.py` (the version literal the root re-exports) | `tests/unit/test_<noun>.py`; private-file contract tests in `tests/unit/private_file/`, `tests/e2e/private_file/` | `tests/sentry/test_atomic_writer.py`, `tests/sentry/io_policy/test_private_files.py` |
| Notifications, telemetry | `src/decoy/` | `src/decoy/notify.py`, `src/decoy/telemetry.py` | `tests/unit/test_notify.py`, `tests/unit/test_telemetry_exporter.py` | `tests/sentry/test_notify_redaction.py`, `tests/sentry/test_otel_closed.py` |
| First-user QA item tests, grouped by behavior | `tests/e2e/first_user/` (new ones go here, not the flat `tests/e2e/`) | `tests/e2e/first_user/test_items_<behavior>.py` | - | shared fixture `tests/fixtures/qa_first_user/` (copy it to `tmp_path`, never edit in place) |
| Sentry test | existing rules in `tests/sentry/`; fitness functions on how a package is cut into modules, and the layout map guard, in `tests/sentry/layout/`; test tooling rules (pytest plugins and settings) in `tests/sentry/tooling/`; recurring-defect class rules in `tests/sentry/defects/`; `decoy run` choke points in `tests/sentry/run/test_<rule>.py` (`tests/sentry/run/test_one_run_reason.py`); shared CI scan helpers in `tests/sentry/ci_scan/`; the engine boundary (public imports only, no copied reason-code strings: `tests/sentry/test_engine_reason_code_copies.py`, shrink-only baseline `tests/sentry/baselines/engine-reason-code-copies.json`) | `tests/sentry/<group>/test_<rule>.py`; helper `_<name>.py`; vendored from the engine and pinned in `ci/vendored.toml`: `tests/sentry/layout/_layout.py`, `tests/sentry/layout/_ratchet_cases.py` | self-tests and seeded mutations in the same file | `tests/sentry/test_sentry_manifest.py` (`SENTRIES`); `tests/sentry/test_baseline_registry.py`; `tests/sentry/baselines/`; `scripts/dev/sentry_registry.toml`; `tests/sentry/_baseline_sources.py`; `tests/sentry/_ratchet.py`; module size cap (800 lines) `tests/sentry/layout/test_module_size.py` with `tests/sentry/baselines/module-size.json`; package fan-out cap (25 modules) `tests/sentry/layout/test_package_fanout.py` with `tests/sentry/baselines/package-fanout.json`; vendor pins `tests/sentry/layout/test_vendored_files.py` |
| Layer contracts | `.importlinter` beside `pyproject.toml` | `.importlinter` | `tests/sentry/layout/test_import_layers.py` | ignore baseline `tests/sentry/baselines/import-layers.json` |
| Shared cross-suite test helpers (constants and lookups used by more than one test folder) | `tests/`, one module per concern | `tests/keyed_secret.py`, `tests/dp_env.py` | - | - |
| Developer environment scripts | `scripts/dev/` | `scripts/dev/lock.sh`, `scripts/dev/bootstrap.sh`, `scripts/dev/lock_version.sh`, `scripts/dev/fetch_ci_binary.py` | `tests/unit/scripts/`: `tests/unit/scripts/test_gates_baseline_file.py`, `tests/unit/scripts/test_gates_legacy_verdict.py`, harness `tests/unit/scripts/_gates_harness.py` | `scripts/dev/gates.sh`, `scripts/dev/ratchet_check.py` |
| Release scripts | `scripts/release/` | `scripts/release/<concern>.py` | `tests/unit/test_sbom_script.py` | - |
| CI install, vendor and lane policy | `ci/` | `ci/install-policy.toml` (the install registry), `ci/vendored.toml`, `ci/ci-tools.in`, `ci/ci-tools.lock`, `ci/required-jobs.toml` (merge tier), `ci/unlaned.toml` (lane exceptions) | `tests/sentry/test_ci_lock_installs.py`, `tests/sentry/tooling/test_ci_lanes.py` | `tests/sentry/_ci_lock_scan.py`, `tests/sentry/tooling/_ci_lanes.py` |
| Composite CI actions | `.github/actions/<name>/` | `action.yml`: `.github/actions/setup-uv/`, `.github/actions/lock-env/` | - | - |
| Task-oriented user guides (one folder per topic, with a `README.md` index) | `docs/guides/<topic>/` | `docs/guides/shape-and-privacy/` | - | `tests/unit/test_surface_docs_consistency.py` |
| Root legal files (license text, notice, licensing FAQ, trademark policy) | repo root | `LICENSE.md`, `NOTICE`, `LICENSING.md`, `TRADEMARKS.md` | `tests/unit/test_pyproject_metadata.py` | - |
| Roadmap, plans, records | `docs/ROADMAP.md`, `docs/roadmap/`, `docs/plans/`, `docs/records/` | `docs/plans/YYYY-MM-DD-<slug>.md`; `docs/records/YYYY-MM-DD-<slug>.md` (build and gate evidence) | - | shipped log `docs/RECENTLY-SHIPPED.md` |

## Where Do I Find...

| Task | Start Here |
|---|---|
| Current roadmap (all repos) | [docs/ROADMAP.md](docs/ROADMAP.md); shipped log [docs/RECENTLY-SHIPPED.md](docs/RECENTLY-SHIPPED.md) |
| CLI role guide | [AGENTS.md](AGENTS.md) (summary) |
| User guide: data shape, fit and generate, fidelity reports, differential privacy | [docs/guides/shape-and-privacy/README.md](docs/guides/shape-and-privacy/README.md) |
| Command registration | `src/decoy/__main__.py` |
| Run command | `src/decoy/cli/run/` (options in `__init__.py`, phases in `_prepare.py`, `_execute.py`, `_errors.py`, `_render.py`) |
| Tokenize / detokenize | `src/decoy/cli/tokenize.py` (store: `_token_vault.py`) |
| Validate command | `src/decoy/cli/validate.py` (gate: `src/decoy/cli/gate/`) |
| CI checks / SARIF / pre-commit | `src/decoy/ci/`, `src/decoy/cli/ci.py`, `docs/ci-contracts.md`, `.pre-commit-hooks.yaml`, `integrations/` |
| Hosted CI installs (lock-env, setup-uv, install policy, scanner) | `.github/actions/`, `ci/install-policy.toml`, `scripts/dev/lock_version.sh`, `tests/sentry/_ci_lock_scan.py` |
| STORM command | `src/decoy/cli/storm.py` |
| Plan command | `src/decoy/cli/plan.py` |
| Output formatting | `src/decoy/ui/` |
| Templates | `src/decoy/templates/` |
| CLI examples | `examples/` |

## Conventions

| Situation | Convention |
|---|---|
| Add command | Put it in a named sub-package below `src/decoy/cli/` (the flat folder is frozen); see the "Command module" row of Where Things Go. Register in `__main__.py`, test with CliRunner |
| Data behavior | Add to `decoy-engine`, not CLI |
| Output | Use Rich helpers; avoid raw `print()` in command bodies |
| Examples | Prefer graph-mode YAML for new examples |
| Verification | Run pytest and a real fixture command |

## Gotchas

| Gotcha | Note |
|---|---|
| CLI is thin | No FastAPI, DB, auth, platform persistence, or data semantics |
| Legacy CLI compatibility shim may exist | Keep only for compatibility messaging |
| Exit codes are public UX | Ask before changing command contracts |

## Ignore For Navigation

| Path | Reason |
|---|---|
| `.pytest_cache/`, `__pycache__/` | Generated |
| `logs/` | Runtime output |
| `decoy_demo/`, `decoy_demo_ref/` | Demo output unless demo task |
