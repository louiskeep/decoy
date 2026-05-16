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
| `src/decoy/cli/` | `run`, `validate`, `storm`, `forecast`, `init`, `demo` commands |
| `src/decoy/ui/` | Theme, output state, progress, tables, cards |
| `src/decoy/templates/` | Packaged YAML templates |
| `examples/` | Example YAML configs |
| `tests/` | CLI tests |
| `docs/` | Local/legacy docs; active planning in `../decoy-platform/docs/` |
| `logs/`, `mappings/`, `.pytest_cache/`, `__pycache__/` | Ignore generated/runtime content |

## Where Do I Find...

| Task | Start Here |
|---|---|
| Current roadmap | `../decoy-platform/docs/ROADMAP.md` |
| CLI role guide | `../decoy-platform/docs/guides/cli-agent-guide.md` |
| Command registration | `src/decoy/__main__.py` |
| Run command | `src/decoy/cli/run.py` |
| Validate command | `src/decoy/cli/validate.py` |
| STORM command | `src/decoy/cli/storm.py` |
| FORECAST command | `src/decoy/cli/forecast.py` |
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
| `logs/`, `mappings/` | Runtime output |
| `decoy_demo/`, `decoy_demo_ref/` | Demo output unless demo task |
