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

## Where things go

First row of the layout map the LAYOUT slice completes (one line per kind of module).

| Kind of module | Where | Examples |
|---|---|---|
| Private shared filesystem or process primitives used by more than one package | top-level `src/decoy/`, file named `_<noun>.py`, tests in `tests/unit/test_<noun>.py`, its sentry in `tests/sentry/` | `_atomic.py`, `_private_file.py` (owner-only creation and every mode change), `_mask_secret.py`, `_native_gate.py` |
| Pre-run check gate shared by `validate`, `ci check` and `run` | `src/decoy/cli/gate/`, file named `_<noun>.py`, tests in `tests/unit/test_gate_*.py` and `tests/e2e/test_run_validate_always.py` | `_layers.py` (layers and entries); `cli/io/` is the sibling sub-package |
| CLI source readers and target writers (owner rule 2026-11-06: new ones go here from now on; `cli/` is frozen) | `src/decoy/cli/io/`, file named `_<noun>.py` | target writer `cli/io/_targets.py` (CLI-FMT), saved-scan reader `cli/io/_scan_set.py`; today's exception `cli/_sources.py` moves here under H-1 |
| `decoy scan` internals (argument resolution, engine call, card and `--json`) | `src/decoy/cli/scanning/`, file named `_<noun>.py`; `scan.py` keeps only the options | `_multi.py` |
| `decoy run` internals (phases, error arm, summary, evidence, notifications, vault commit) | `src/decoy/cli/run/`, file named `_<noun>.py`; `__init__.py` keeps only the options, `_RUN_EPILOG` and the re-exports | `_prepare.py`, `_execute.py`, `_errors.py`, `_render.py`, `_evidence.py`, `_notify.py`, `_vault.py`, `_flow.py` (the order of the phases), `_context.py` (`RunContext`, the state they share) |
| Composite CI actions (`action.yml`) | `.github/actions/<name>/` | `setup-uv`, `lock-env` |
| CI install, vendor and lane policy (`*.toml`) | `ci/` | `ci/install-policy.toml` (the install registry), `ci/vendored.toml`, `ci/ci-tools.in`, `ci/ci-tools.lock` |
| Developer environment scripts | `scripts/dev/` | `lock.sh`, `bootstrap.sh`, `lock_version.sh`, `fetch_ci_binary.py` |
| Tests of developer scripts | `tests/unit/scripts/` | `test_gates_baseline_file.py`, `test_gates_legacy_verdict.py`, shared harness `_gates_harness.py` |
| Shared cross-suite test helpers (constants and lookups used by more than one test folder) | `tests/` root, one module per concern | `keyed_secret.py`, `dp_env.py` |
| Repository policy sentries and their scanners (CI scan helpers shared with the engine in the `ci_scan/` sub-package) | `tests/sentry/` | `_ratchet.py`, `_ci_lock_scan.py`, `test_ci_lock_installs.py`; shared CI scan helpers in `tests/sentry/ci_scan/` |
| I/O policy sentries (reads and writes) and their shared call scanner | `tests/sentry/io_policy/` | `_calls.py`, `test_target_writes.py` |
| User-facing CLI text and crash-handling sentries (new ones go here, not the flat `tests/sentry/`; `io_policy/` is the adjacent pattern) | `tests/sentry/cli_text/` | `test_no_traceback_escape.py` |
| Layout fitness functions (how a package is cut into modules) | `tests/sentry/layout/` | `test_run_package_shape.py` (`cli/run/`: thin `__init__`, 600-line cap, import order, no private imports) |
| Task-oriented user guides (one folder per topic, with a `README.md` index) | `docs/guides/<topic>/` | `docs/guides/shape-and-privacy/` |
| Build and gate evidence records | `docs/records/` | `2026-11-06-ci-l1-build.md` |
| CLI format contract tests (new ones go in these named folders, not the flat `tests/e2e/` and `tests/unit/`) | `tests/e2e/cli_fmt/`, `tests/unit/cli_fmt/` | `test_target_format_dispatch.py`, `test_targets_format.py` |
| Private-file contract tests (new ones go in these named folders, not the flat `tests/e2e/` and `tests/unit/`) | `tests/unit/private_file/`, `tests/e2e/private_file/` | `test_private_file.py` |
| First-user QA item tests, grouped by behavior (new ones go here, not the flat `tests/e2e/`; `cli_fmt/` is the adjacent pattern) | `tests/e2e/first_user/` | `test_items_text.py`, `test_items_reports.py`, `test_items_preflight.py`, `test_items_compile.py`, `test_items_logging.py` |
| Run and report summary renderers (run card extras, warning lines, `report fidelity` text) | `src/decoy/ui/summary.py` | `card.py`, `table.py` |
| Shared first-user QA fixture (patients and visits CSVs plus two pipelines; copy it to `tmp_path`, never edit in place) | `tests/fixtures/qa_first_user/` | `patients.csv`, `pipeline_no_namespace.yaml` |

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
| Add command | Add command module under `src/decoy/cli/`, register in `__main__.py`, test with CliRunner |
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
