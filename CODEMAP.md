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
| Private shared filesystem or process primitives used by more than one package | top-level `src/decoy/`, file named `_<noun>.py`, tests in `tests/unit/test_<noun>.py`, its sentry in `tests/sentry/` | `_atomic.py`, `_mask_secret.py`, `_native_gate.py` |
| CLI source readers and target writers (owner rule 2026-11-06: new ones go here from now on; `cli/` is frozen) | `src/decoy/cli/io/`, file named `_<noun>.py` | target writer `cli/io/_targets.py` (CLI-FMT); today's exception `cli/_sources.py` moves here under H-1 |
| Composite CI actions (`action.yml`) | `.github/actions/<name>/` | `setup-uv`, `lock-env` |
| CI install, vendor and lane policy (`*.toml`) | `ci/` | `ci/install-policy.toml` (the install registry), `ci/vendored.toml`, `ci/ci-tools.lock` |
| Developer environment scripts | `scripts/dev/` | `lock.sh`, `bootstrap.sh`, `lock_version.sh` |
| Repository policy sentries and their scanners | `tests/sentry/` | `_ratchet.py`, `_ci_lock_scan.py`, `_ci_shell_tokens.py`, `test_ci_lock_installs.py` |
| Build and gate evidence records | `docs/records/` | `2026-11-06-ci-l1-build.md` |

## Where Do I Find...

| Task | Start Here |
|---|---|
| Current roadmap (all repos) | [docs/ROADMAP.md](docs/ROADMAP.md); shipped log [docs/RECENTLY-SHIPPED.md](docs/RECENTLY-SHIPPED.md) |
| CLI role guide | [AGENTS.md](AGENTS.md) (summary) |
| Command registration | `src/decoy/__main__.py` |
| Run command | `src/decoy/cli/run.py` |
| Tokenize / detokenize | `src/decoy/cli/tokenize.py` (store: `_token_vault.py`) |
| Validate command | `src/decoy/cli/validate.py` |
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
