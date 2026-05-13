# PLAN — decoy (CLI)

> Source of truth for **what the agent is working on right now** in `forge` (CLI).
> Long-horizon "what to build next" lives cross-repo in [`../forge-platform/ROADMAP.md`](../forge-platform/ROADMAP.md). This file is the short-loop companion for CLI-side work.

---

## Status

- **Project:** decoy CLI (Typer + Rich; thin wrapper over `decoy-engine`)
- **Stage:** building (pre-customer)
- **Current focus:** Quiet repo; CLI is stable. Most active work is platform-side. Pick up when a roadmap item adds a CLI surface.
- **Last updated:** 2026-05-12

---

## 1. Spec

**Product:** Terminal-driven Decoy: `decoy mask <yaml>`, `decoy generate <yaml>`, `decoy storm <file>` (planned), etc. Single-process, single-run, file-in / file-out.

**User:** Solo developers and small teams who'd rather drive masking from `cron` / Makefiles / CI than spin up a self-hosted platform. The "pip install decoy" path from the marketing site.

**Success criteria:**
- `pip install decoy` then `decoy mask <yaml>` works against a 1M-row CSV in under 5 minutes, end-to-end, on a fresh machine.
- CLI output is readable — Rich progress bars, clear errors, JSON-on-error tail for CI integration.
- Disguise bundles (templates in `src/decoy/templates/`) just work via `decoy mask --disguise hipaa <file>`.

**Non-goals:**
- No HTTP API. That's `forge-platform`.
- No scheduling, alerts, multi-user. Those are platform concerns.
- No GUI / dashboard.

---

## 2. Architecture & Stack

- **Language:** Python 3.10+
- **Build:** hatchling
- **CLI framework:** Typer
- **Output:** Rich
- **Hard deps:** `decoy-engine` (and its transitive set: pandas, polars, duckdb, etc.)
- **Tests:** pytest, Typer's `CliRunner`

---

## 3. MVP Scope

Cross-repo MVP framing in `../forge-platform/ROADMAP.md`. CLI-specific anchors:

### Already shipped
- `decoy mask` / `decoy generate` against engine.
- Disguise template includes via `src/decoy/templates/`.
- `forge` deprecation shim points users at `decoy`.

### Active queue
- (None CLI-specific at this writing — pulled by larger product work as it lands.)

### Not in scope
- Anything that touches HTTP, DB, multi-user, scheduling.

---

## 4. Milestones

CLI work tends to be a thin reflection of engine + platform milestones. See `../forge-platform/ROADMAP.md`.

---

## 5. Current Task

**Task:** _(none active)_
**Context:** N/A.
**Acceptance:** N/A.

---

## 6. Decision Log

- 2026-05-12 — CLI repo remains the thin Typer shell over `decoy-engine`. No expansion into platform territory. (Cross-repo decision.)

---

## 7. Open Questions

- [ ] When Item 24 (file-only ETL SDK) lands engine-side, does the CLI grow a `decoy run <pipeline.yaml>` graph-mode command, or does graph-mode stay platform-only? Lean: add to CLI once engine API stabilizes.

---

## 8. Risks & Trade-offs

- **Risk:** CLI dependency surface includes the engine's transitive deps (polars, duckdb, pyarrow). `pip install decoy` is heavier than a typical Typer-only tool. **Acceptable because:** engine is the value; a "lite" CLI without it would be pointless.

---

## 9. Backlog / Future

- `decoy storm <file>` — wire up STORM scanning from the CLI (currently platform-only entry point).
- `decoy run <graph.yaml>` — drive graph-mode pipelines from the terminal once engine surface settles.

---

## Changelog

- 2026-05-12 — initial PLAN.md drafted alongside AGENTS.md.
