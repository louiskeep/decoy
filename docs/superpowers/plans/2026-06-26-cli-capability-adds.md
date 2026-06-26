# Decoy CLI — Capability Adds (C1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.
> On execution, save this plan into the CLI repo as `docs/superpowers/plans/2026-06-26-cli-capability-adds.md`.

## Context

A review of the Decoy CLI (`/home/cam/vscode/decoy`, a thin Typer/Rich wrapper over `decoy-engine`)
found one real capability gap and several smaller adds. A prior hygiene pass (branch
`cli/hygiene-and-feature-docs`, commit `66d6233`) already fixed the doc-drift and feature-doc gaps.
This plan covers the **buildable-now capability adds** plus a **dead-command removal**, and specs the
**engine-gated** features so they stay tracked behind the engine remediation track (E1–E6).

**Why now:** the CLI artificially rejects mixed mask+generate pipelines that the engine already
supports (`run_pipeline`), ships a dead `replan` command, and lacks a schema-export + vault-inspect
utility. These are small, high-signal improvements to the local workflow before the platform/MCP work.

**Scope decisions (confirmed with Cam, 2026-06-26):**
- Build: **#1 mixed mask+generate run**, **#5 `decoy schema`**, **#7 `decoy vault info`**.
- **Remove** the dead `replan` command (pre-GA hard delete).
- Custom *faker* providers (#6a) — NOT in this round.
- Engine-gated features (#2 cross-version unmask guard, #4 frozen-plan replay, #6b custom
  *strategies*) — spec'd as blocked/future, no buildable tasks here.

**Goal:** Wire the engine's unified run entry, add `schema`/`vault info` commands, and delete `replan`.

**Architecture:** Pure CLI-side, except #7 which needs one small public helper added to `decoy-engine`
to expose the job-seed derivation that reading an (encrypted) vault requires. Each command stays a thin
Typer wrapper that lazy-imports the engine and renders via the existing `decoy.ui` helpers.

**Tech Stack:** Python 3.11 (dev venv already built this session at `/home/cam/vscode/decoy/.venv` via
`uv`, with the local `decoy-engine` installed editable), Typer, Rich, pytest, the engine library.

## Global Constraints
- **CLI stays thin** (CODEMAP/CLAUDE charter): no platform/auth/DB/data-semantics. Data behavior lives
  in `decoy-engine`, not the CLI.
- **Drift sentry:** any command/flag/help change requires regenerating the reference, or
  `tests/e2e/test_cli_surface.py` fails:
  `.venv/bin/python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md`
- **Gates per task (run before commit):** `.venv/bin/python -m pytest -q` (full suite, currently 324
  green), `.venv/bin/ruff check src/decoy tests`. (Repo `ruff format` baseline drifts under ruff
  0.15.20 across untouched files — a pre-existing version-skew; do NOT `ruff format` the repo as part of
  this work.)
- **Output convention:** use `decoy.ui` helpers + `setup_output`/`emit_json`; no raw `print()` in
  command bodies. Typed exit codes from `decoy.cli.exit_codes`.
- **Branch:** continue on `cli/hygiene-and-feature-docs` or a fresh `cli/capability-adds` off `main`.

## Key existing-code facts (verified this session)
- Unified entry: `run_pipeline(config: dict, sources: dict[str, pa.Table] | None = None, *,
  engine_version: str, registry=None, derive_key=None, instance_default_locale: str | None = None,
  vault_writer=None) -> ExecutionResult`. Takes the **raw config** (profiles + compiles + builds the
  relationship graph internally) and returns `ExecutionResult` with `.outputs: dict[table -> pa.Table]`
  for **all** target tables (mask + generate). Exported from `decoy_engine`.
- Today `decoy run` (`src/decoy/cli/run.py:178-318`) hand-rolls the dispatch: `all_generate` →
  `generate_tables`; mask → `profile_source`→`compile_plan`→`build_*`→`adapter.run`; and **rejects mixed
  configs** via `_MixedConfigError` (`run.py:238-244`). The chunked path (`_run_chunked_mask`) is
  mask-only streaming and stays as-is.
- `PipelineConfig.model_json_schema()` is available (pydantic v2) — exported as `decoy_engine.PipelineConfig`.
- `load_vault(path: str | Path, job_seed: bytes) -> tuple[dict[(ns, masked) -> source], int]`. The vault
  is Fernet-encrypted, so reading it needs `job_seed` **bytes**. The engine derives that via the private
  `decoy_engine.plan._compile._normalize_job_seed(config) -> bytes` (NOT exported). Vault does **not**
  stamp `SEED_PROTOCOL_VERSION` today (`vault.py:29`) — that stamping is engine v6 work (gates #2).
- `replan` (`src/decoy/cli/plan.py:243-279`) is a stub that always exits `EXIT_USAGE` with a pointer to
  `decoy plan`. Registered in `src/decoy/__main__.py`. Pinned by 3 tests in
  `tests/e2e/test_plan_command.py` (`test_replan_help_documents_not_yet_implemented`,
  `test_replan_errors_with_actionable_message`, `test_replan_requires_from_flag`).
- Reusable writers in `run.py`: `_load_sources_from_config(config_dict, base_dir)`,
  `_write_mask_outputs(config_dict, result, base_dir)` (writes every target present in `result.outputs`),
  `_resolve_path`. `_build_resolver(...)` builds the keyed `derive_key`.

---

### Task 1: `decoy schema` — export the PipelineConfig JSON Schema

**Files:**
- Create: `src/decoy/cli/schema.py`
- Modify: `src/decoy/__main__.py` (register the command + epilog, mirroring `templates`/`info`)
- Test: `tests/e2e/test_schema_command.py`
- Regen: `docs/cli-reference.md`

**Interfaces — Produces:** a `schema(output: Path | None, json_, quiet, verbose)` Typer command.

Behavior: print `PipelineConfig.model_json_schema()` as indented JSON to stdout (raw, mirroring how
`templates show` prints raw YAML); `--output/-o PATH` writes the JSON to a file instead; `--json` wraps
it in the standard `{command, status, schema}` envelope; `--quiet` suppresses stdout. Lazy-import the
engine inside the body.

- [ ] **Step 1 — failing test.** In `test_schema_command.py`: invoke `["schema"]`, assert exit 0 and
  `json.loads(stdout)` has `properties`/`$defs` and the top-level keys `version`, `sources`, `tables`,
  `targets` appear in the schema; a second test for `["schema", "-o", str(tmp_path/"s.json")]` writes a
  file that parses as JSON; a `--json` test asserts the `{command:"schema", status:"ok"}` envelope.
- [ ] **Step 2 — run, verify fail** (`pytest tests/e2e/test_schema_command.py -q` → fail: no such command).
- [ ] **Step 3 — implement** `src/decoy/cli/schema.py`: `from decoy_engine import PipelineConfig`,
  `schema = PipelineConfig.model_json_schema()`, render via `setup_output`/`emit_json`; register in
  `__main__.py` with a `SCHEMA_EPILOG` (one example: `decoy schema -o decoy.schema.json`).
- [ ] **Step 4 — regen reference + run suite** (regen command above; `pytest -q`; `ruff check`).
- [ ] **Step 5 — commit** (`feat(cli): add 'decoy schema' JSON Schema export`).

### Task 2: Mixed mask+generate run via `run_pipeline` (the capability gap)

**Files:**
- Modify: `src/decoy/cli/run.py` — replace the split non-chunked dispatch (`run.py:202-316`) with a
  single `run_pipeline(...)` call; delete `_MixedConfigError` + its raise (`run.py:45-47, 238-244`);
  keep the chunked path; add a guard that `--chunked` + any generate-table errors clearly.
- Test: `tests/e2e/test_run_mixed.py` (new); existing `tests/e2e/test_run_command.py` is the regression net.

**Interfaces — Consumes:** `run_pipeline` (signature above). **Produces:** unchanged `decoy run` CLI
contract (same flags, same JSON envelope), now accepting mixed configs.

New non-chunked body (replaces the inline profile/compile/adapter orchestration):
```python
sources = _load_sources_from_config(config_dict, config.parent)
instance_locale = (config_dict.get("global_settings") or {}).get("default_locale")
result = run_pipeline(
    config_dict,
    sources,
    engine_version=engine_version,
    derive_key=resolver,
    instance_default_locale=instance_locale,
    vault_writer=vault_writer,
)
_write_mask_outputs(config_dict, result, config.parent)  # writes every target in result.outputs
```
`vault_writer` is still built by the existing pre-flight (`iter_vault_columns` guard stays; drop only the
`all_generate` vault-guard wording so a mixed config with vault columns is allowed). The
`profile_source`/`compile_plan`/`build_namespace_registry`/`build_relationship_graph` imports and the
`generate_tables` branch are removed (run_pipeline does all of it).

- [ ] **Step 1 — failing tests.** In `test_run_mixed.py`, build a 2-table config: a generate parent
  (`generate_columns`, `row_count`) + a mask child (`columns`) with a `relationships:` FK to the parent.
  Run `["run", cfg]`; assert exit 0 and BOTH target files written; assert the child's FK values are a
  subset of the parent's generated PK values (join preserved). Add a `--chunked` + generate-table test
  asserting a clear usage error (exit 1).
- [ ] **Step 2 — run, verify fail** (mixed config currently exits 1 with `_MixedConfigError` text).
- [ ] **Step 3 — implement** the `run_pipeline` rewrite + the chunked-vs-generate guard; delete
  `_MixedConfigError`.
- [ ] **Step 4 — full regression.** `pytest tests/e2e/test_run_command.py tests/e2e/test_run_chunked.py
  tests/e2e/test_run_mixed.py -q` (mask-only + generate-only + chunked must all still pass); then
  `pytest -q` whole suite; `ruff check`. Regen reference if any help text shifted (it should not).
- [ ] **Step 5 — commit** (`feat(cli): run mixed mask+generate pipelines via run_pipeline`).

### Task 3: Remove the dead `replan` command

**Files:**
- Modify: `src/decoy/cli/plan.py` — delete `replan(...)` (`plan.py:243-279`) and any `REPLAN_EPILOG`.
- Modify: `src/decoy/__main__.py` — remove the `replan` registration.
- Modify: `tests/e2e/test_plan_command.py` — delete the 3 `replan` tests + the module-docstring mention.
- Grep + clean any `replan` reference in `completers.py`/`explain.py` (none expected).
- Regen: `docs/cli-reference.md`.

- [ ] **Step 1 — failing test.** Add `test_replan_command_is_gone`: `runner.invoke(app, ["replan",
  "--help"])` asserts a non-zero exit and "No such command" (Typer's unknown-command behavior).
- [ ] **Step 2 — run, verify fail** (the command still exists → test fails).
- [ ] **Step 3 — remove** the function + registration; delete the 3 obsolete `replan` tests.
- [ ] **Step 4 — regen reference + run suite** (`replan` section drops from the reference; `pytest -q`;
  `ruff check`).
- [ ] **Step 5 — commit** (`refactor(cli)!: remove the dead 'replan' command (no engine manifest API)`).

### Task 4: `decoy vault info` (needs one small engine helper)

**Files:**
- Modify (**decoy-engine repo**): `src/decoy_engine/__init__.py` — export a public
  `job_seed_for_config(config: dict) -> bytes` thin wrapper over the existing private
  `plan._compile._normalize_job_seed`; add to `__all__`. (Smallest honest surface; alternative is a
  fuller `inspect_vault(path, config)` — defer that to when v6 stamps the vault version.)
- Create (**CLI**): `src/decoy/cli/vault.py` with a `vault` Typer sub-app and an `info` subcommand.
- Modify: `src/decoy/__main__.py` — register the `vault` sub-app (mirror the `storm`/`templates` sub-app
  registration).
- Test (engine): `tests/unit/test_job_seed_for_config.py` — round-trips a known config to 8 bytes,
  deterministic.
- Test (CLI): `tests/e2e/test_vault_info.py`.
- Regen: `docs/cli-reference.md`.

**Interfaces — Consumes:** `decoy_engine.job_seed_for_config(config) -> bytes`,
`decoy_engine.load_vault(path, job_seed) -> tuple[dict, int]`, `vault_writer_for_config`. **Produces:**
`decoy vault info VAULT --config CONFIG [--json] [...]`.

Behavior: `decoy vault info vault.bin --config pipeline.yaml` loads the config, derives `job_seed =
job_seed_for_config(config_dict)`, calls `load_vault(vault_path, job_seed)`, and reports entry count +
the distinct namespaces present (keys are `(namespace, masked)` tuples). `--json` emits
`{command, status, vault, entries, namespaces}`. A wrong/missing seed (vault won't decrypt) surfaces a
clean `EXIT_USAGE` error, not a stack trace.

- [ ] **Step 1 (engine) — failing test** `test_job_seed_for_config`: same config → same 8 bytes; matches
  what `vault_writer_for_config(config)` uses internally (compare against a vault written then read back).
- [ ] **Step 2 (engine) — implement + export** `job_seed_for_config`; run the engine suite for the
  determinism/vault modules. **Do this additively on a fresh `feat/job-seed-for-config` branch off engine
  `main`** — do NOT disturb the in-flight `fix/v6-determinism-a2` working tree (it has uncommitted WIP;
  coordinate before branching).
- [ ] **Step 3 (CLI) — failing test** `test_vault_info`: write a small vaulted mask run (reuse the
  `tests/e2e/test_vault_cli.py` fixture pattern), then `vault info <vault> --config <cfg>` asserts exit 0
  and a reported entry count > 0; a `--config` with the wrong seed asserts `EXIT_USAGE`.
- [ ] **Step 4 (CLI) — implement** `src/decoy/cli/vault.py` + register the sub-app.
- [ ] **Step 5 — regen reference + run suite + ruff; commit** both repos
  (`feat(cli): add 'decoy vault info'` + `feat(engine): export job_seed_for_config`).

---

### Task 5: Cross-version unmask guard (formerly deferred #2 — engine gate now cleared)

**Why now:** the engine landed F13 (`decoy-vault/v2`, commit `ca49ed0`): the vault stamps `seed_protocol_version`
in its header and `load_vault`/`unmask_pipeline` raise a typed `VaultError(code="vault_protocol_version_mismatch")`
on a cross-version vault. VERIFIED: `VaultError` is NOT a `DecoyError`/`ExecutionError` subclass, so the CLI's
current `except (ExecutionError, PlanCompileError, ConfigError)` in `unmask.py` MISSES it — a cross-version vault
falls through to the generic `except Exception` → EXIT_RUNTIME(3) with an unhelpful message and no migration hint.

**Files:**
- Modify: `src/decoy/cli/unmask.py` — import `VaultError` from `decoy_engine`; add `except VaultError as exc:`
  BEFORE the generic `except Exception` (currently ~line 197). Map it to **EXIT_USAGE**; when
  `getattr(exc, "code", None) == "vault_protocol_version_mismatch"`, include a re-mask migration hint
  ("the vault was written under a different engine protocol version; re-mask under the current engine, or use
  the engine version that wrote it"). Other `VaultError` codes → EXIT_USAGE with `code: message`.
- Test: `tests/e2e/test_unmask_command.py` (extend; or the existing unmask vault test file).

**Interfaces — Consumes:** `decoy_engine.VaultError` (`.code`, `.message`).

- [ ] **Step 1 — failing test.** Monkeypatch `decoy_engine.unmask_pipeline` (or the symbol the CLI imports) to
  raise `VaultError(code="vault_protocol_version_mismatch", message=...)`; invoke `["unmask", cfg, masked,
  "--vault", vaultpath]`; assert exit code == EXIT_USAGE (1, NOT 3) and the stderr/JSON error mentions the
  version mismatch + a re-mask hint. (Monkeypatch is the right level: the CLI's job is to MAP the typed error;
  the engine owns detecting the mismatch.) Optionally also a `--json` envelope assertion.
- [ ] **Step 2 — run, verify fail** (currently the generic catch returns EXIT_RUNTIME(3), so the EXIT_USAGE
  assertion fails).
- [ ] **Step 3 — implement** the `except VaultError` clause + hint.
- [ ] **Step 4 — gates.** `.venv/bin/python -m pytest tests/e2e/test_unmask_command.py -q`, then full
  `.venv/bin/python -m pytest -q` (no help/flag change → reference regen should be a no-op, but run it to be
  safe), `.venv/bin/ruff check src/decoy tests`.
- [ ] **Step 5 — commit** (`feat(cli): map cross-version vault mismatch to a clean usage error in unmask`).

## Deferred — engine-gated (spec only, no buildable tasks here)

These stay tracked behind the engine remediation track (E1–E6 in the platform sprint ledger). Author a
CLI task for each only once its engine dependency lands.

- **#2 Cross-version unmask guard** — `decoy unmask` / vault read must refuse a `SEED_PROTOCOL_VERSION`
  mismatch instead of silently returning wrong values. **Blocked on:** engine **v6** stamping the
  protocol version into the vault artifact (today `vault.py` does not — it's part of the v6 cluster, and
  the cross-version vaulted-unmask guard is an explicit deliverable of engine **E2/E3**). Plan-once-
  unblocked: read the stamped version via the `inspect_vault`/`load_vault` path, compare to
  `decoy_engine.SEED_PROTOCOL_VERSION`, error with a re-mask migration hint on mismatch.
- **#4 Frozen-plan replay** — `decoy run --plan <frozen-plan.yaml>` to execute a precompiled plan for
  byte-reproducibility/audit. **Blocked on:** a public engine plan *loader* (`compile_plan`/`validate_plan`
  are exported, but there is no `plan_from_yaml`/`load_plan` to deserialize a frozen plan back into a
  `Plan` the adapter can run). Plan-once-unblocked: add a `--plan` input to `run` that loads the frozen
  plan and skips profile/compile.
- **#6b Custom strategies** — register user masking *strategies* (not just faker providers).
  **Blocked on:** gap-closure **item 9** (the engine's compile-time `unknown_strategy` check is unsafe;
  needs a fixture migration before custom strategies are safe). Custom *faker providers* via
  `load_custom_providers` are buildable independently if desired later.

## Verification (end-to-end)
- `decoy schema` emits valid JSON Schema (stdout + `-o file`); `--json` envelope shape holds.
- A mixed mask+generate config runs in one `decoy run`, writes both targets, and the child FK joins to
  the generated parent PK; mask-only, generate-only, and `--chunked` runs all still pass (regression
  net green).
- `decoy replan` is gone (`No such command`); reference no longer lists it.
- `decoy vault info <vault> --config <cfg>` reports a correct entry count; wrong seed → `EXIT_USAGE`;
  engine `job_seed_for_config` is deterministic and matches the writer's seed.
- After every task: `pytest -q` green (drift sentry included, reference regenerated), `ruff check` clean.

## Execution Handoff — GATE-1
Stops at **GATE-1 for Cam** (this plan). On approval: subagent-driven-development (TDD per task);
Task 2 is the security/correctness-sensitive one (run-path rewrite) and warrants a focused review; Task
4 spans both repos (engine export first, on a branch off engine `main` — do not disturb the in-flight
`fix/v6-determinism-a2` working tree). Then dennis whole-branch review → GATE-2.
