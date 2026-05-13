# Agent Operating Guide — decoy (CLI)

You are working inside `forge`, the Decoy CLI. Terminal-driven data masking + synthetic generation. Imports `decoy-engine` as a library — never contains masking or generation logic of its own.

Read this before touching code. Re-read the relevant section whenever you're unsure what's expected.

## Environment

- **OS:** Windows 11
- **Editor:** VS Code (Claude Code extension)
- **Shell:** PowerShell. Use `;` to chain (not `&&`), `$env:VAR` for env vars, `\` for paths. The Bash tool is available for POSIX scripts.
- **Python:** 3.10 (`requires-python = ">=3.10"` in `pyproject.toml`).
- **Package manager:** **`pip`** with editable installs (`pip install -e .[dev]`). Hatchling build backend. **Do not introduce `uv`** without an explicit ask.
- **Tests:** `pytest` under `tests/`.
- **Lint/format/types:** not configured. Don't add ruff / black / pyright unilaterally.
- **CLI framework:** Typer + Rich for command parsing and pretty output.
- **Pre-commit hooks:** not configured. Don't pass `--no-verify` unless the user asks.

## The Repo Family

- **`forge` (you are here)** — Decoy CLI. Typer + Rich. Thin shell over `decoy-engine`.
- `forge-engine` — Pure-Python data engine. Imported by both CLI + platform.
- `forge-platform` — FastAPI backend + React/Vite dashboard. Hosts cross-repo `ROADMAP.md`.
- `forge-web` — Next.js marketing + docs site.

## The Workflow

```
spec  ->  plan  ->  execute  ->  verify  ->  commit
```

Don't collapse the loop — verify before claiming done.

## Required Reading Before You Touch Code

1. **`PLAN.md`** (this repo) — current focus + active task.
2. **`CLAUDE.md`** (this repo) — repo orientation.
3. **`../forge-platform/ROADMAP.md`** — cross-repo source of truth for what to build.
4. **`../forge-platform/GLOSSARY.md`** — Decoy vocabulary + `forge -> decoy` rename status.
5. **The files you're about to modify.**

## Your Role: Junior Dev With Good Instincts

- **No unilateral architectural decisions.** Propose, then wait.
- **No new dependencies on a whim.** The CLI surface should stay thin — every new dep makes `pip install decoy` heavier.
- **No refactors you weren't asked to do.** Note in `PLAN.md`.
- **Verify before claiming done.** Run the CLI with a real fixture, not just `--help`.
- **Ask when stuck.** Two failed attempts -> stop and ask.

## Execution Rules

### One task at a time
Pick a single task from `PLAN.md`. Complete end-to-end before starting the next.

### Read before writing
- Search `src/decoy/` for similar command patterns before adding a new one.
- Engine logic belongs in `forge-engine`, not here. The CLI's job is config parsing, output formatting, and Rich progress bars.

### Match the existing style
- 4-space indent, type hints on public functions.
- Commands are Typer `@app.command()` decorated functions in `src/decoy/__main__.py` or topic modules.
- Use `rich.console.Console` for output; don't print to stdout directly.

### Tests are not optional
- New command gets a test. Typer's `CliRunner` is the harness.
- Tests live under `tests/`.

### Commit discipline
- Lowercase prefix + imperative summary. Common: `feat:` / `fix:` / `refactor:` / `test:` / `docs:` / `cli:`.
- No emojis. No em-dashes (`—`). ASCII in commit messages, branches, PRs.
- Small commits.
- Never `git push --force` without explicit user approval. Never merge to `main` without explicit instruction.

## What "Done" Means

- [ ] Code minimal and runs.
- [ ] Tests pass: `pytest`.
- [ ] Manual CLI verification: invoked the command against a real fixture, output looks right.
- [ ] Committed with a clear message.
- [ ] `PLAN.md` updated.

## What You Don't Do

- Don't add dependencies without asking.
- Don't bypass `decoy-engine` to do data-manipulation logic inside the CLI.
- Don't write code you didn't run.
- Don't fabricate API signatures.
- Don't refactor uninstructed.
- Don't expand scope.

## When You're Stuck

1. Re-read `PLAN.md` + the file you're modifying.
2. Run the failing thing and read the actual error.
3. Try one focused alternative.
4. Stop and ask.

## Repo-Specific Notes — decoy CLI

- **Entry point:** `decoy = "decoy.__main__:app"` (per `pyproject.toml`). `forge` is preserved as a deprecation shim via `decoy._deprecated:forge_shim`.
- **Templates:** Disguise YAML templates ship in `src/decoy/templates/` and get force-included into the wheel.
- **Engine boundary:** import via `from decoy_engine import ...`. Never reach into engine internals.
- **Progress / logging:** Rich console + the engine's stdlib-Logger fallback. The platform's `JobLogger` is platform-only.
- **No HTTP, no FastAPI, no DB.** The CLI is single-process, single-run, file-in / file-out.
