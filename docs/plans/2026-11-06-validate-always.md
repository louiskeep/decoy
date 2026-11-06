# VALIDATE-ALWAYS: `decoy run` runs the whole `decoy validate` gate first

Status: plan (2026-11-06, not built). CLI only. Roadmap row 23.

Rules consulted: `~/dev-rules/README.md` (routing table), `00-universal.md`,
`risk-and-exceptions.md`, `development-loop.md` (PLAN, plan-lint), `cross-cutting-concerns.md`,
`architecture.md` (Layout), `testing.md` (Test depth), `api-and-compatibility.md` (exit codes and
`--json` are public), `catalogs/recurring-defects.md` (all classes). Also read: CLI
`origin/main` `5bd60b9` (`docs/ROADMAP.md` 4.1, 4.2, 5.2 rule 2, row 23; `CODEMAP.md` "Where things
go"); LAYOUT plan (engine `origin/plan/layout`, CLI rows and owner Q4); VALUE-FREE-ERRORS plan
(engine `origin/plan/value-free-errors`); vault handoffs `p05-cli-dialect-build-handoff.md`,
`p05-config-explicit-build-handoff.md`, `p05-result-build-handoff.md`; owner priorities
`v1-pragmatic-gate-priorities` (working V1, recommended technical options, block only on cascading
design).

Risk: R2. It changes when `decoy run` stops and, for some inputs, which exit code it returns (a
public contract). No data path, engine or schema change.

## 1. Guarantee and non-goals

The change promises:

1. `decoy run CONFIG` runs the same three layers as `decoy validate CONFIG` (config, compile,
   preflight), through the same function, before it reads any source rows into the run
   (`_load_sources_from_config`, `_run_chunked_mask`) and before the native pre-execution gate.
2. Any gate error stops the run. The exit code is `gate_exit_code(result, fail_on_warning=False)`:
   5 for a capacity refusal, else 1. No new exit code.
3. Gate warnings never stop a run. Human mode prints one stderr line with the warning count and
   the command that lists them. `--quiet` and `--json` print nothing extra on success.
4. `--json` on a gate refusal keeps today's envelope members (`command`, `status`, `config`,
   `mode`, `error`) and adds `error_kind: "validation"` (or `"capacity"` with `code`, exactly as the
   engine capacity path sets them today) and `messages`, the list shape `decoy validate --json`
   emits (`layer`, `severity`, `code`, `message`, `location`).
5. There is one gate. `decoy validate`, `decoy ci check` and `decoy run` call it; `run.py` calls no
   layer check itself.

Non-goals (a finding here is a follow-up, not a blocker):

- `decoy tokenize`, `decoy demo` and the Python API `decoy.mask()`, which also run pipelines. FU-1.
- The `--duckdb-source` staging read. It runs before the gate, because the gate must see the staged
  Parquet path the run will use. FU-2.
- Making `decoy validate` catch every run-time failure. This row makes `run` run the gate; it does
  not widen the gate (beyond Q1).
- Value-free text inside gate messages. VALUE-FREE-ERRORS owns that and lands on the gate's one
  config site (section 9).
- The run result document. RESULT records gate findings later (FU-3).
- A skip flag (Q3 recommends none).

## 2. Measured today

Gate (CLI `5bd60b9`):

- `src/decoy/cli/validate.py:420-502` `_run_config_base`: YAML parse, empty and non-mapping
  refusals, `PipelineConfig.model_validate` (`:466`, findings from `exc.errors()` `type`, `msg`,
  `loc`), then `decoy_engine.run_config_only_checks` (`:491`).
- `:505-562` `_run_compile_layer`: the H2 guard refuses any `cardinality_mode: unique` column as
  `no_profile_unique_incompatible` (`:527-541`), then `compile_plan(..., no_profile=True)` (`:539`);
  a broad `except Exception` maps to `compile_error` (`:551`).
- `:565-598` `_run_preflight_layer`: `_check_source_files`, `_check_target_overwrite`,
  `_check_capacity`, `_check_native` from `preflight.py` (private names). `_check_capacity`
  (`preflight.py:368`) profiles every file source with a bounded sample (engine
  `estimate_job_capacity`, `execution/capacity.py:208`, at most 10k rows per source, the same call
  `run_pipeline` makes) and skips non-file sources (no network). `_check_native` only passes or warns.
- `:601-644` `GateResult`, `run_config_gate`, `run_gate(config, source_text)`, `gate_exit_code`
  (capacity 5, error 1, warning with `--fail-on-warning` 2, else 0).
- `:647-705` `_gate` (the hidden default command) renders it; `src/decoy/ci/adapters.py:78,105`
  consumes `run_gate` and `run_config_gate` for `decoy ci check`. This is the shared check function
  already; no second copy exists to merge, except the `decoy validate preflight` command body
  (`preflight.py:624-767`), which re-runs steps 1-3 itself (CONFIG-EXPLICIT C2 folds it).

`decoy run` (`src/decoy/cli/run.py`, 1805 lines, over the cap and frozen):

- `:243` `_load_raw_config`; `:576-588` YAML re-parse with `sanitize_yaml_error`; `:590-622` DE-02
  `mask_secret_ref` guard; `:628-668` `--duckdb-source` staging; `:684` `PipelineConfig.model_validate`
  is the only config check, rendered with `str(exc)` (`:686`, which includes Pydantic's
  `input_value`); `:697` `--mask-secret` applied; `:821` native pre-execution gate; `:842`
  `_load_sources_from_config` (first full read) or `:856` `_run_chunked_mask`; `:882` `run_pipeline`,
  which profiles and compiles after the read.
- `run` never calls `run_config_only_checks`, the compile layer or any preflight check.
- Error path: one handler (`:917-1160`) maps exception types to 1, 3 or 5 (`:1005-1065`), caps
  `error` at 500 characters (`:1071`), dispatches `--notify`, and emits one JSON envelope with
  `error_kind` for capacity, native and missing extras (`:1100-1124`).
- `tests/e2e/test_run_command.py:331-344` pins "source file missing, not a config error, exit 3".

Probe (main checkout `e86b97c`, engine 0.14.0 in its venv; directional only, re-measure on the part
base), bundled `examples/mask_example.yaml` in a scratch directory:

| Case | `decoy validate` | `decoy run` today |
|---|---|---|
| source file missing | exit 1, `source.customers.exists`, location `sources.customers.path` | exit 3, `[Errno 2] No such file ...` with the absolute path |
| `cardinality_mode: unique` on one column, source present | exit 1, `no_profile_unique_incompatible` | exit 0, output written |
| valid config, 1-row CSV | exit 0, 1.1 s wall (whole process) | exit 0, 3.3 s wall |

Row 2 is why the gate cannot be bolted on as is: the aggregate gate refuses a config that `run`
handles, because the run has a profile. The engine says so (`plan/_compile.py:489-494`: naive
`compile_plan(no_profile=True)` "hard-errors on `cardinality_mode: unique` columns that a profiled
run accepts").

Capacity parity already holds: preflight and the run-time out-of-core route call the same
`evaluate_capacity` (engine `out_of_core/_capacity_eval.py:235-309`, "keeps preflight and run in
lockstep"); `INSUFFICIENT` is returned only for the fan-in impossibility, and CLI
`tests/e2e/test_run_preflight_capacity_parity.py` pins both commands to exit 5.

## 3. Established solutions

Search run: web search "terraform apply runs validate implicitly before plan; kubectl apply
--validate; dbt run compile before execution", plus the repo (the gate, `decoy ci check`, the
capacity parity test).

- Terraform: `plan` and `apply` without a saved plan validate the configuration implicitly, with no
  skip flag ([Firefly: terraform validate](https://www.firefly.ai/academy/terraform-validate),
  [KodeKloud notes](https://notes.kodekloud.com/docs/HashiCorp-Certified-Terraform-Associate-004/The-Core-Terraform-Workflow/Terraform-Validate/page)).
- `kubectl apply` validates manifests by default and offers `--validate=false` as an escape hatch
  (kubectl reference, recalled; the search did not return it).
- `dbt run` compiles every selected model before it executes any (dbt docs, recalled).

Followed: the Terraform pattern. The execute command calls the validation the standalone command
runs, implicitly and without a skip flag; the standalone command stays for CI and editors. Custom
code left: a run-side adapter (about 80 lines) that turns a `GateResult` into the run's typed error
and stderr line. No library applies.

## 4. Design notes

- **One choke point.** The gate moves out of `validate.py` into a package and gains one entry that
  takes an already-parsed config: `run_gate_on_config(raw, config_path) -> GateResult`
  (`config_path` is used only for its directory, as today). `run_gate` becomes "parse the YAML,
  then `run_gate_on_config`". Change pain removed: today a new check added to the gate silently
  skips `run`.
- **The gate returns the validated config.** `GateResult.config: dict | None` holds the
  `PipelineConfig.model_validate(raw).model_dump()` the config layer already computes. `run` uses it
  and drops its own `model_validate` (`run.py:684`), so the config is validated once, in one place.
  When CONFIG-EXPLICIT C1 lands, its `_config_load.validated_config` replaces that one call.
- **The unique-column finding becomes a skip (Q1).** In the aggregate gate a
  `cardinality_mode: unique` column turns the compile layer into the warning
  `compile.needs_profile` ("compile checks need a profile; `decoy run` checks them"). The explicit
  `decoy validate compile --no-profile` keeps its error. No flag argument: every caller gets the
  same gate.
- **Run policy sits beside the gate.** `gate/_run.py` holds
  `check_before_run(raw, config_path, state) -> dict`: it calls the gate, prints the warning-count
  line, and returns the config or raises `PreRunCheckError`. The error carries `exit_code`,
  `error_kind`, `code` and `messages`. Its `str()` is a one-line summary (count, first error with
  its location, "run `decoy validate CONFIG` for the full report"), so the handler's 500-character
  cap never cuts a list.
- **Order inside `run`.** After the DE-02 guard and the `--duckdb-source` staging (the gate must
  see the staged path), in place of `run.py:670-686`; before `--mask-secret`, the native gate and
  any source read. The handler gains one `isinstance(exc, PreRunCheckError)` branch that takes the
  exit code and merges the extra JSON members. The refusal still goes through the one handler, so
  `--notify` and the temp-dir cleanup behave as for any other config error.
- **House style.** Typed `GateResult` and `PreRunCheckError`; no flag arguments; `run.py` does not
  grow (offset: the deleted `model_validate` block and its comment).

## 5. Placement

| New file | Directory | Map row | Sits beside |
|---|---|---|---|
| `gate/__init__.py` (public: `GateResult`, `GateFinding`, `run_gate`, `run_config_gate`, `run_gate_on_config`, `gate_exit_code`, `check_before_run`, `PreRunCheckError`) | `src/decoy/cli/gate/` | map change: add the row "Pre-run check gate shared by `validate`, `ci check` and `run`: `src/decoy/cli/gate/`, `_<noun>.py`, tests in `tests/unit/test_gate_*.py` and `tests/e2e/test_run_validate_always.py`". Owner Q4 (LAYOUT): `cli/` is frozen at 31 modules and new code goes in a named sub-package | `cli/io/` (CLI-FMT) |
| `gate/_layers.py` (moved from `validate.py:394-644`, plus `run_gate_on_config`) | same | same | `validate.py` |
| `gate/_run.py` (`check_before_run`, `PreRunCheckError`) | same | same | `_layers.py` |
| `tests/unit/test_gate_layers.py`, `tests/e2e/test_run_validate_always.py`, `tests/sentry/test_gate_single_entry.py` | existing test dirs | existing CLI test locations | `tests/e2e/test_validate_gate.py` |

`src/decoy/cli/` gains one sub-package and no module. `validate.py` keeps the renderer
(`_emit_gate`) and the Typer commands. `ci/adapters.py:78` imports from `decoy.cli.gate`; if LAYOUT
C3 has landed, its exact ignore entry `ci.adapters -> cli.validate` is renamed to
`ci.adapters -> cli.gate` in the same diff (same count, class 11).

## 6. Choke points, guards and red mutations

| Rule | Choke point | Guard (walks) | Red mutation |
|---|---|---|---|
| Every pre-run command runs the whole gate | `decoy.cli.gate.run_gate_on_config` | `tests/e2e/test_run_validate_always.py` parity matrix: one broken config per finding kind (YAML, schema, config-only check, compile error, missing source, unreadable source, capacity fan-in through the existing T8 topology). For each, `decoy validate` and `decoy run` refuse with the same exit code and the same first `code`, and spies on `read_source`, `iter_source_chunks` and `run_pipeline` record zero calls | delete the `check_before_run` call in `run.py`: red; move it below `_load_sources_from_config`: red (spy) |
| No layer check outside the gate | `gate/_layers.py` | `tests/sentry/test_gate_single_entry.py`: AST walk of `src/decoy` (alias-aware: `import x as y`, `from x import y`, attribute calls; recurring class 5) for calls to `run_config_only_checks`, `compile_plan` with `no_profile=True`, and preflight `_check_source_files`, `_check_target_overwrite`, `_check_capacity`, `_check_native` outside `gate/`. Named exemptions: `preflight.py` (the `validate preflight` command, until CONFIG-EXPLICIT C2) and `compile_explain.py` (the explicit `validate compile` command) | add `_check_source_files(raw, ...)` to `run.py`: red; `import decoy_engine as de; de.run_config_only_checks(x)` in a scratch module: red |
| One config validation in the run path | `GateResult.config` | the same sentry flags `PipelineConfig.model_validate` in `run.py` | restore `run.py:684`: red |

The sentry is seeded-bypass tested, registered in `SENTRIES` and `scripts/dev/sentry_registry.toml`,
and runs in the merge gate's sentry step. Its exemption list is a ratchet that only shrinks.

## 7. Acceptance tests

Each names the mutation that turns it red; red-first evidence is an assertion failure.

- AT-1 (stop before read): missing source, `decoy run`: exit 1, stderr names
  `sources.customers.path`, no target file, `read_source` never called. Replaces the exit-3
  expectation at `test_run_command.py:344` under Q2. Mutation: gate after the read.
- AT-2 (compile error before read): a config whose no-profile compile fails: exit 1 with the
  compile `code`; spy shows no read. Mutation: drop the compile layer from `run_gate_on_config`.
- AT-3 (capacity): the T8 fan-in topology: `decoy run --json` exits 5 with `error_kind: "capacity"`
  and `code: "out_of_core_fanin_exceeds_budget"`, before `run_pipeline`. Mutation: map a gate
  capacity refusal to 1.
- AT-4 (unique column, Q1): unique-column config with its source present: `decoy run` exit 0 with
  output written; `decoy validate` exit 0 with warning `compile.needs_profile`, exit 2 with
  `--fail-on-warning`; `decoy validate compile --no-profile` still exit 1. Mutation: restore the
  error severity.
- AT-5 (JSON shape): for every refusal in the parity matrix, the envelope keys are a superset of
  today's (`command`, `status`, `config`, `mode`, `error`) and `messages` equals
  `decoy validate --json`'s `messages` for the same config. Mutation: emit `messages` only for
  config-layer failures.
- AT-6 (warnings): a target that already exists: `decoy run` exit 0 and one stderr line with the
  warning count; `--json` stdout is one JSON document; `--quiet` prints nothing. Mutation: print
  each warning to stdout.
- AT-7 (secrets): a wrong-typed `mask_secret_ref` holding a marker still exits 1 through the DE-02
  guard and the marker appears in no output; a config with keyed strategies and only
  `--mask-secret env:X` passes the gate. Mutation: move the gate above the DE-02 guard.
- AT-8 (duckdb): `--duckdb-source` with a declared table runs the gate on the staged Parquet path
  and exits 0. Mutation: run the gate on the YAML before staging.
- AT-9 (chunked): the missing-source cell under `--chunked` exits 1 before `iter_source_chunks`.
  Mutation: place the call inside the non-chunked branch only.
- AT-10 (notify): a gate refusal with `--notify` pointing at a local test server sends one failure
  event whose `error_summary` is `PreRunCheckError`. Mutation: raise `typer.Exit` from the adapter.
- AT-11 (move is behavior-preserving): `tests/e2e/test_validate_gate.py`,
  `test_validate_command.py`, `test_validate_sp16.py` and the `test_ci_*` suite pass unchanged
  except AT-4's one expectation. Mutation: any behavior change in the move.
- AT-12 (chain): `PreRunCheckError` has `__cause__ is None` and `__context__ is None`. Mutation:
  raise it inside an `except` block.
- AT-13 (size): `wc -l src/decoy/cli/run.py` on the head is at or below the base value;
  `validate.py` is under 800. Mutation: add a line to `run.py`.

## 8. Parts (slices)

Commit subjects: Conventional Commits, at most 72 characters, final line `cam`, no body unless it
explains why. Test depth T0 per edit, T1 per commit and slice head, T2 at the gate.

| Part | Branch | Base | Lane | Depends on | Hand-written lines |
|---|---|---|---|---|---:|
| P1 gate package | `feat/validate-always-p1-gate` | CLI main | none (no `run.py` edit) | none; can build now | ~300 (moved lines not counted) |
| P2 run wiring | `feat/validate-always-p2-run` | CLI main after P1 | `run.py` lane | P1 merged; CLI-DIALECT's `run.py` writer merged; lane free | ~350 |

**P1.** Move `validate.py:394-644` to `gate/_layers.py` unchanged; add `run_gate_on_config`,
`GateResult.config`, the Q1 severity change, the CODEMAP row, the `ci/adapters.py` import, AT-4,
AT-11 and the sentry with its seeded cases. Re-target any test that patches the moved private
names, without weakening it. Subject: `refactor(cli): move the pre-run gate into cli/gate`.

**P2.** `gate/_run.py`, the `run.py` call and handler branch with the offsetting deletion, AT-1 to
AT-3, AT-5 to AT-10, AT-12, AT-13, the CHANGELOG `### Changed` entry listing the exit-code moves
under Q2, and `docs/cli-reference.md` for `run`. Subject:
`feat(cli): run the validate gate before decoy run reads data`.

## 9. Test scope and in-flight sequencing

| In flight | Touches | Effect |
|---|---|---|
| CLI-DIALECT (row 19; engine `feat/csv-source-reader`; CLI part not on origin yet) | `cli/_sources.py`, the run read points | P2 waits for its `run.py` writer (lane rule 5.2.2). The gate reads no rows, so no reader conflict |
| CONFIG-EXPLICIT (row 22, plan pending; C1 adds `_config_load.py`, C2 edits `validate.py:466`) | the gate's config site and `run.py:683` | P1 is expected first (C1 waits on two engine releases). C1 and C2 then edit `gate/_layers.py` instead of `validate.py`, and `run.py:683` is already gone. Their header and column checks reach `run` with no extra wiring |
| VALUE-FREE-ERRORS (engine `plan/value-free-errors`, CLI part A3) | sites `validate.py:277,462`, `run.py:684` | P1 moves `:462` into `gate/_layers.py`; P2 deletes `run.py:684`. A3 re-measures; its Click-tree walk covers `run` through the gate. Names stay visible and values hidden, per its Q1 |
| RESULT (row 62, CLI half after R-d) | `run.py` error path and envelope | lands after P2; its exit map classifies `PreRunCheckError` as `usage` or `capacity` and its document records the gate (FU-3) |
| CLI-FMT A, SUB-RUN, CLI delivery, LIB L3a+, F29 C1, F30 C1b | `run.py` | ordinary lane order; P2 holds the lane for one slice |

Full-suite trigger: P2 (exit-code mapping on a public contract). P1 runs T1: tests importing
`validate`, `ci.adapters`, `preflight` or `plan`; `tests/e2e/test_validate_*`, `test_ci_*`,
`test_preflight_*`, `test_compile_explain_command.py`; all sentries.

## 10. File sizes

| File | Today | After |
|---|---:|---:|
| `src/decoy/cli/validate.py` | 807 | ~560 |
| `src/decoy/cli/gate/_layers.py` | new | ~290 |
| `src/decoy/cli/gate/_run.py` | new | ~90 |
| `src/decoy/cli/gate/__init__.py` | new | ~25 |
| `src/decoy/cli/run.py` | 1805 | at or below 1805 |
| `src/decoy/cli/preflight.py` | 886 | unchanged |
| `src/decoy/ci/adapters.py` | 289 | 289 |
| `tests/e2e/test_run_validate_always.py` | new | ~300 |
| `tests/sentry/test_gate_single_entry.py` | new | ~140 |

## 11. Recurring-defect coverage

Class 3: `PreRunCheckError` is raised after any `except` closes (AT-12). Class 5: the sentry
normalizes aliases and attribute calls, with a seeded case per spelling. Class 9: mutations re-run
on each part's final head. Class 11: no pin raised; `run.py` does not grow. Classes 1, 2, 4, 6, 7,
8 and 10 are not touched: no regex, no persisted model, no new reader, no new private import (the
existing `preflight._check_*` imports move with the gate unchanged), no CI script.

## 11a. General review taxonomy (plan contract)

| # | Class | Applies | Closing structure | Proof and mutation |
|---|---|---|---|---|
| 1 | Value-bearing output | Yes, narrowly: run's schema error stops printing `str(exc)` (which carries `input_value`) and prints the gate's `msg` and `loc`. Gate text is otherwise unchanged; VALUE-FREE-ERRORS owns the rest | one config site in `gate/_layers.py` | AT-5, AT-7; mutation: render `str(exc)` in the summary: a marker in a wrong-typed value appears, red |
| 2 | Cleanup on an exit path | Yes: a gate refusal must still remove the `--duckdb-source` temp dir and send `--notify` | the refusal raises into run's one handler and `finally` | AT-8 asserts the temp dir is gone after a refusal; AT-10; mutation: `typer.Exit` from the adapter: red |
| 3 | State machine and concurrency | N/A: one synchronous call, no shared state | none | none |
| 4 | Route parity and silent fallback | Yes: plain and `--chunked` runs, `--duckdb-source`, and the `validate` and `ci check` routes must see the same gate | one entry, parity matrix, sentry | AT-1, AT-9, AT-11; mutation: call only in the non-chunked branch: red |
| 5 | Referential integrity | N/A: no data or FK handling; the gate's FK compile checks are unchanged | none | none |
| 6 | Untrusted producer | Yes: the YAML is user input | the DE-02 guard stays first; the gate reads `errors()` fields, never `input` | AT-7 |
| 7 | Check then use (TOCTOU) | Yes: a source checked present can vanish before the read | accepted: the later read fails as today (exit 3); no lock is added | recorded limit, no test |
| 8 | Weak tests and overclaimed evidence | Yes: a parity matrix that passes because neither command refuses | each matrix cell also asserts the refusal `code`; seeded sentry bypasses; numbers re-measured on each base | AT-1 to AT-3 assert codes; mutation: drop the source-file check: cells red |
| 9 | Behavior-preserving refactor drift | Yes: P1 moves 250 lines | move unchanged, existing suites green with one named expectation change | AT-11 |
| 10 | Frozen contract drift | Yes: exit-code mapping and `--json` members | Q2, CHANGELOG, key-superset test | AT-5; mutation: drop `config` from the envelope: red |

## 11b. Enumerations

### Exit paths

- Refusal: `PreRunCheckError` into run's handler (`run.py:917`), exit 1 or 5 (`:1005-1065`).
- Pass: the run continues to `--mask-secret` (`run.py:697`).
- Unexpected exception from the gate (for example from `_check_capacity`, `preflight.py:368`):
  propagates to the handler, exit 3 as today.

### Routes

- `decoy run` plain (`run.py:842`), `--chunked` (`:856`), `--duckdb-source` (`:628`), `--vault`,
  `--native` and `--no-native` (`:821`).
- `decoy validate` default gate (`validate.py:647`), `decoy ci check` (`ci/adapters.py:105`).

### FK shapes

- N/A: no FK handling; the compile layer's FK checks are unchanged.

### Fields

- No config model field is added or changed (`PipelineConfig` untouched).
- `GateResult` (`validate.py:601` today) gains `config: dict | None`, in-process only, never
  serialized.

### Output surfaces

- Run stderr: the refusal summary and the warning-count line.
- Run `--json` envelope (`run.py:1100-1124`): `error_kind` and `messages` added.
- `--notify` failure event: type name only, unchanged rule (`run.py:1087`).
- `decoy validate` human and `--json` output: Q1's severity change only.

## 11c. Reuse inventory

`run_gate` and `gate_exit_code` (`validate.py:620,634`), `sanitize_yaml_error`, the preflight
`_check_*` functions, `plan_compile_error_fields` (`extras.py`), run's existing error handler and
`error_kind` pattern, the T8 capacity topology fixture, the X0a ratchet and sentry registry.

## 11d. Frozen contracts

- Exit-code integers (`exit_codes.py`) do not change; the mapping for source-file and unexpected
  compile failures in `run` moves from 3 to 1 (Q2, CHANGELOG).
- `decoy run --json` failure keys: today's keys keep their names; `error_kind` and `messages` are
  added; `error` text changes for config refusals.
- `decoy validate --json` and `decoy ci check` output: unchanged except Q1's unique-column severity.

## 12. Pre-mortem

- A false refusal stops a run that works today. Known case: unique columns (Q1). Others could come
  from the no-profile compile; the parity matrix plus the existing `test_run_*` suite on P2's head
  is the check, and a new case is fixed in the gate (one place), not with a skip flag.
- The bounded profile in `_check_capacity` slows large runs. It reads at most 10k rows per file
  source, and `run_pipeline` repeats the same call. P2 records wall time for a 1M-row CSV and a
  1M-row Parquet run before and after; more than 10 percent slower is reported to the owner.
- An unexpected compile crash in the gate exits 1 where the same crash inside `run_pipeline` exits
  3. Accepted, as `decoy validate` behaves today; FU-4.
- A test that asserted exit 3 for a missing or corrupt source moves to 1. Allowed only as the Q2
  change, listed in the evidence record, never to make an unrelated check pass.
- `ci check` output drifts after the move. AT-11 runs the CI suite unchanged.

## 13. Questions (owner)

- **Q1 (UX, `decoy validate` result).** The aggregate `decoy validate` reports a
  `cardinality_mode: unique` config as a warning (`compile.needs_profile`) instead of an error, so
  `run` can use the same gate; `validate compile --no-profile` keeps its error. Recommended: yes.
  Without it, `run` refuses configs it runs fine today.
- **Q2 (exit codes and `--json`).** `decoy run` exits 1, not 3, for a missing, unreadable or corrupt
  source file and for an unexpected no-profile compile crash, and its `--json` failure gains
  `error_kind: "validation"` and `messages`. The integers do not move; the mapping does.
  Recommended: yes, with a CHANGELOG entry (pre-1.0 MINOR, `docs/release/versioning.md`).
- **Q3 (skip flag).** Recommended: no `--no-validate` in V1. Every gate refusal is one the run
  would hit anyway once Q1 is in; capacity uses the run's own evaluator; Terraform has no skip
  either. Add one later only for a measured false refusal.

Technical calls taken (recorded, not asked): gate package under `cli/gate/`; the gate returns the
validated config; warnings shown as a count only; the gate runs after `--duckdb-source` staging.

## 14. Follow-ups

- FU-1: `decoy tokenize`, `decoy demo` and `decoy.mask()` call `check_before_run`, and the sentry
  gains a Click-tree walk over every command that calls `run_pipeline`.
- FU-2: check `--duckdb-source` relations before staging (CONFIG-EXPLICIT's `DESCRIBE` boundary).
- FU-3: RESULT records gate findings as a `checks[]` entry; `--json` success carries warnings
  through the result document.
- FU-4: the gate's broad `except Exception` in the compile layer maps to exit 3, like `run`.
- FU-5: fold the `validate preflight` command body onto the gate (CONFIG-EXPLICIT C2) and drop its
  sentry exemption.

## 15. Done when

- [ ] P1 and P2 merged in order; `decoy run` refuses every parity-matrix config before any read,
      with `decoy validate`'s exit code and first code.
- [ ] No pre-run layer check is called outside `cli/gate/` except the two named exemptions; the
      sentry's seeded bypasses were shown red on the final head.
- [ ] Q1 to Q3 answered and applied; CHANGELOG and `docs/cli-reference.md` updated.
- [ ] `run.py` did not grow; `validate.py` is under 800; the CODEMAP row is in.
- [ ] P2's full suite shows no new failing id against the saved baseline; the timing note is
      recorded.
- [ ] Roadmap row 23 and `docs/RECENTLY-SHIPPED.md` updated when P2 merges.
