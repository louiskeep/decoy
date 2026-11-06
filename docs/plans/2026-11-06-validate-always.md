# VALIDATE-ALWAYS: `decoy run` runs the whole `decoy validate` gate first

Status: plan (2026-11-06, not built). CLI only. Roadmap row 23.

Revision note r2 (applying Dennis r1 and owner Q1-Q3, 2026-11-06). Owner answered Q1 to Q3 with the
recommended options. Dennis r1 (BLOCK, 0/2/4/4 on `1192c82`): H1 keeps the `missing_extra` envelope
and lists the `ci check` rule-id change; H2 folds `validate config` onto the gate and deletes its
duplicate `_check_target_overwrite`; M1 routes run's YAML parse through the gate; M2 makes a
capacity refusal a warning on the chunked route; M3 caps each message and adds a corrupt-CSV marker
test; M4 lists each retargeted test; L1 to L3 as listed under section 7.

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
   5 for a capacity refusal, else 1. No new exit code. On the `--chunked` route a capacity
   refusal is a warning (section 4), because that route never takes the out-of-core path.
3. Gate warnings never stop a run. Human mode prints one stderr line with the warning count and
   the command that lists them. `--quiet` and `--json` print nothing extra on success.
4. `--json` on a gate refusal keeps `command`, `status`, `config`, `mode` and `error`, and adds
   `messages` (the list `decoy validate --json` emits: `layer`, `severity`, `code`, `message`,
   `location`) and `error_kind`. `error_kind` keeps today's values where today has one:
   `"capacity"` with `code`, and `"missing_extra"` with `extra` for an absent optional extra (spaCy
   for NER). Every other refusal is `"validation"`. Each `messages[].message` and `error` is capped
   at run's 500-character limit.
5. There is one gate. `decoy validate` (default and `config`), `decoy ci check` and `decoy run` call
   it; `run.py` and `validate.py` call no layer check and parse no pipeline YAML themselves.

Non-goals (a finding here is a follow-up, not a blocker):

- `decoy tokenize`, `decoy demo` and the Python API `decoy.mask()`, which also run pipelines. FU-1.
- The `--duckdb-source` staging read. It runs before the gate, because the gate must see the staged
  Parquet path the run will use. FU-2.
- Making `decoy validate` catch every run-time failure. This row makes `run` run the gate; it does
  not widen the gate (beyond Q1).
- Value-free text inside gate messages beyond the one capacity message in M3. VALUE-FREE-ERRORS owns
  the rest and lands on the gate's one config site (section 9).
- The run result document. RESULT records gate findings later (FU-3).
- A skip flag (Q3, owner: none).

## 2. Measured today

Gate (CLI `5bd60b9`):

- `src/decoy/cli/validate.py:420-502` `_run_config_base`: YAML parse, empty and non-mapping
  refusals, `PipelineConfig.model_validate` (`:466`, findings from `exc.errors()` `type`, `msg`,
  `loc`), then `decoy_engine.run_config_only_checks` (`:491`). A `PlanCompileError` goes through
  `plan_compile_error_fields` (`extras.py:208`), which rewrites `ner_spacy_not_installed` to code
  `missing_extra` and drops the `extra` name.
- `:505-562` `_run_compile_layer`: the H2 guard refuses any `cardinality_mode: unique` column as
  `no_profile_unique_incompatible` (`:527-541`), then `compile_plan(..., no_profile=True)` (`:539`);
  a broad `except Exception` maps to `compile_error` (`:551`).
- `:565-598` `_run_preflight_layer`: `_check_source_files`, `_check_target_overwrite`,
  `_check_capacity`, `_check_native` from `preflight.py` (private names). `_check_capacity`
  (`preflight.py:368`) profiles every file source with a bounded sample (engine
  `estimate_job_capacity`, `execution/capacity.py:208`, at most 10k rows per source, the same call
  `run_pipeline` makes) and skips non-file sources. Its unreadable-source finding embeds the engine
  message (`preflight.py:514-518`), which embeds the reader's exception text
  (`capacity.py`, `capacity_source_unprofilable`). `_check_native` only passes or warns.
- `:601-644` `GateResult`, `run_config_gate`, `run_gate(config, source_text)`, `gate_exit_code`
  (capacity 5, error 1, warning with `--fail-on-warning` 2, else 0).
- `:647-705` `_gate` (the hidden default command) renders it; `src/decoy/ci/adapters.py:78,105`
  consumes `run_gate` and `run_config_gate` for `decoy ci check`; `src/decoy/ci/rule_codes.py:39-46`
  `_CLI_GATE_CODES` allowlists the gate's codes, including `no_profile_unique_incompatible`.

Second copy of the config layer (Dennis H2): `decoy validate config` (`validate.py:196-320`)
parses the YAML, refuses empty and non-mapping input, runs `model_validate` and
`run_config_only_checks` itself, then calls its own `_check_target_overwrite` (`validate.py:164-188`,
code `target_file.would_overwrite`), a copy of `preflight.py:268-302` (codes
`target.<t>.would_overwrite` and `target.<t>.parent_missing`). The `decoy validate preflight`
command body (`preflight.py:624-767`) is a third copy of steps 1-3 (CONFIG-EXPLICIT C2 folds it).

`decoy run` (`src/decoy/cli/run.py`, 1805 lines, over the cap and frozen):

- `:243` `_load_raw_config`; `:576-588` YAML re-parse with `sanitize_yaml_error`; `:590-622` DE-02
  `mask_secret_ref` guard; `:628-668` `--duckdb-source` staging; `:684` `PipelineConfig.model_validate`
  is the only config check, rendered with `str(exc)` (`:686`, which includes Pydantic's
  `input_value`); `:697` `--mask-secret` applied; `:821` native pre-execution gate; `:842`
  `_load_sources_from_config` (first full read) or `:856` `_run_chunked_mask`; `:882` `run_pipeline`,
  which profiles and compiles after the read.
- `run` never calls `run_config_only_checks`, the compile layer or any preflight check.
- Error path: one handler (`:917-1160`) maps exception types to 1, 3 or 5 (`:1005-1065`), caps
  `error` at 500 characters (`:1071-1073`, a literal), dispatches `--notify`, and emits one JSON
  envelope with `error_kind` for capacity, native and missing extras (`:1100-1124`; `extra` at
  `:1121-1122`).
- `tests/e2e/test_run_command.py:331-344` pins "source file missing, not a config error, exit 3".

Chunked route and capacity (Dennis M2): `_run_chunked_mask` (`run.py:1464-1518`) streams each mask
table through `run_mask_pipeline_chunked` and never enters the out-of-core FK route, while
`_check_capacity` prices that route. The T8 fan-in topology
(`tests/e2e/test_run_preflight_capacity_parity.py:252-312`) uses `orphan_policy: preserve`, which
`check_chunked_compatibility` refuses (engine `execution/_chunked.py:257-305`,
`chunked_fk_orphan_policy_not_remap`), so T8 itself is not chunk-compatible. A `remap` variant of
the same graph meets every listed chunked FK rule on reading (hash keys, matching namespaces and
strategies); a run of it was not possible here (no current-engine venv on the devbox). Under the
gate as is, that variant would exit 5 on `--chunked` for a job the chunked route never sizes. The
plan makes the refusal a warning on that route either way (section 4); P2 records whether the
variant runs to exit 0.

Probe (main checkout `e86b97c`, engine 0.14.0 in its venv; directional only, re-measure on the part
base), bundled `examples/mask_example.yaml` in a scratch directory:

| Case | `decoy validate` | `decoy run` today |
|---|---|---|
| source file missing | exit 1, `source.customers.exists`, location `sources.customers.path` | exit 3, `[Errno 2] No such file ...` with the absolute path |
| `cardinality_mode: unique` on one column, source present | exit 1, `no_profile_unique_incompatible` | exit 0, output written |
| valid config, 1-row CSV | exit 0, 1.1 s wall (whole process) | exit 0, 3.3 s wall |

Row 2 is why the gate needed Q1: the engine says naive `compile_plan(no_profile=True)`
"hard-errors on `cardinality_mode: unique` columns that a profiled run accepts"
(`plan/_compile.py:489-494`).

Capacity parity on the plain route already holds: preflight and the run-time out-of-core route call
the same `evaluate_capacity` (engine `out_of_core/_capacity_eval.py:235-309`); `INSUFFICIENT` is
returned only for the fan-in impossibility, and the T8 test pins both commands to exit 5.

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
code left: a run-side adapter (about 90 lines) that turns a `GateResult` into the run's typed error
and stderr line. No library applies.

## 4. Design notes

- **One choke point, two entries.** The gate moves out of `validate.py` into a package with a parse
  entry and a config entry:
  - `parse_pipeline_yaml(config_path, source_text=None) -> (raw, findings)`: YAML syntax only
    (`yaml.parse_error` through `sanitize_yaml_error`).
  - `run_gate_on_config(raw, config_path, route=GateRoute.PLAIN) -> GateResult`: owns the empty
    (`yaml.empty`) and non-mapping (`yaml.not_mapping`) refusals, then the three layers.
    `config_path` is used only for its directory, as today.
  - `run_gate` and `run_config_gate` compose the two, so `validate`, `ci check` and `run` share
    every refusal.
- **`validate config` folds onto the gate (H2).** It renders `run_config_gate`'s result through its
  existing `_emit_result` (same envelope, `checks_run` included). Its own parse, schema and
  config-only code and its `_check_target_overwrite` copy are deleted. The target-overwrite
  advisory moves from the preflight layer into the config layer (it needs no data), so it runs
  once per gate and `validate config` keeps showing it. Code changes listed in 11d.
- **The gate returns what callers need.** `GateResult` gains `checks_run: tuple[str, ...] = ()`
  and, last, `config: dict | None = None` (the `model_validate(raw).model_dump()` the config layer
  already computes). `run` uses `config` and drops `run.py:684`. When CONFIG-EXPLICIT C1 lands, its
  `_config_load.validated_config` replaces that one call in the gate.
- **`GateFinding` carries `extra: str | None = None`** (H1a). The config and compile layers call
  `translate_ner_unavailable` (`extras.py:172`) once and keep its `.extra`, so `run` can emit
  `error_kind: "missing_extra"` and `extra` as it does today.
- **The unique-column finding becomes a skip (Q1, owner).** In the aggregate gate a
  `cardinality_mode: unique` column turns the compile layer into the warning
  `compile.needs_profile`. `decoy validate compile --no-profile` keeps its error.
- **Route value, not a user flag (M2).** `GateRoute` is an enum with `PLAIN` and `CHUNKED`. `run`
  passes `CHUNKED` when `--chunked` is set. On `CHUNKED` the gate emits a capacity `INSUFFICIENT`
  finding as a warning and leaves `capacity_insufficient` false. No CLI flag is added; the route is
  a fact the run already knows.
- **Message cap (M3).** `gate/_run.py` defines `ERROR_TEXT_CAP = 500`; `run.py:1072-1073` reads it
  instead of the literal (net zero lines), and every `messages[].message` is capped with it. The
  `capacity.source_unreadable` finding uses fixed text with the source table and the exception type
  name, never the reader's exception text (one line in `preflight.py:514-518`, net zero).
- **Run policy sits beside the gate.** `gate/_run.py` holds
  `check_before_run(raw, config_path, route, state) -> dict`: it calls `run_gate_on_config`,
  prints the warning-count line, and returns `GateResult.config` or raises `PreRunCheckError`. The
  error carries `exit_code`, `error_kind`, `code`, `extra` and `messages`. Its `str()` is a one-line
  summary (count, first error with its location, "run `decoy validate CONFIG` for the full
  report").
- **Order inside `run` (M1).** `run.py:576-588` (the YAML re-parse) becomes one
  `parse_pipeline_yaml` call that raises `PreRunCheckError` on a syntax error. Then the DE-02 guard
  and `--duckdb-source` staging, unchanged. Then `check_before_run` in place of `run.py:670-686`,
  before `--mask-secret`, the native gate and any source read. The handler gains one
  `isinstance(exc, PreRunCheckError)` branch that takes the exit code and merges the JSON members.
  The refusal still goes through the one handler, so `--notify` and the temp-dir cleanup behave as
  for any other config error.
- **House style.** Typed `GateResult`, `GateFinding`, `GateRoute` and `PreRunCheckError`; new
  dataclass fields go last with defaults; `run.py` does not grow.

## 5. Placement

| New file | Directory | Map row | Sits beside |
|---|---|---|---|
| `gate/__init__.py` (public: `GateResult`, `GateFinding`, `GateRoute`, `parse_pipeline_yaml`, `run_gate`, `run_config_gate`, `run_gate_on_config`, `gate_exit_code`, `check_before_run`, `PreRunCheckError`, `ERROR_TEXT_CAP`) | `src/decoy/cli/gate/` | map change: add the row "Pre-run check gate shared by `validate`, `ci check` and `run`: `src/decoy/cli/gate/`, `_<noun>.py`, tests in `tests/unit/test_gate_*.py` and `tests/e2e/test_run_validate_always.py`". Owner Q4 (LAYOUT): `cli/` is frozen at 31 modules and new code goes in a named sub-package | `cli/io/` (CLI-FMT) |
| `gate/_layers.py` (moved from `validate.py:394-644`, plus the two entries and the route rule) | same | same | `validate.py` |
| `gate/_run.py` (`check_before_run`, `PreRunCheckError`, `ERROR_TEXT_CAP`) | same | same | `_layers.py` |
| `tests/unit/test_gate_layers.py`, `tests/e2e/test_run_validate_always.py`, `tests/sentry/test_gate_single_entry.py` | existing test dirs | existing CLI test locations | `tests/e2e/test_validate_gate.py` |

`src/decoy/cli/` gains one sub-package and no module. `validate.py` keeps the renderers
(`_emit_result`, `_emit_gate`) and the Typer commands. `ci/adapters.py:78` imports from
`decoy.cli.gate`; if LAYOUT C3 has landed, its exact ignore entry `ci.adapters -> cli.validate` is
renamed to `ci.adapters -> cli.gate` in the same diff (same count, class 11).

## 6. Choke points, guards and red mutations

| Rule | Choke point | Guard (walks) | Red mutation |
|---|---|---|---|
| Every pre-run command runs the whole gate | `decoy.cli.gate.run_gate_on_config` | `tests/e2e/test_run_validate_always.py` parity matrix: one broken config per finding kind (YAML syntax, empty YAML, list YAML, schema, config-only check, NER extra absent, compile error, missing source, unreadable source, capacity fan-in through T8). For each, `decoy validate` and `decoy run` refuse with the same exit code and the same first `code`, and spies on `read_source`, `iter_source_chunks` and `run_pipeline` record zero calls | delete the `check_before_run` call in `run.py`: red; move it below `_load_sources_from_config`: red (spy) |
| No layer check or pipeline-YAML parse outside the gate | `gate/_layers.py` | `tests/sentry/test_gate_single_entry.py`: AST walk of `src/decoy`. Each call is resolved through the module's import table to a `(module, name)` pair (`import x as y`, `from x import y as z`, attribute calls on module aliases; recurring class 5), never matched by bare name. Flagged targets: `decoy_engine.run_config_only_checks`, `decoy_engine.plan.compile_plan` with `no_profile=True`, `decoy.cli.preflight._check_source_files`, `_check_target_overwrite`, `_check_capacity`, `_check_native`, and `yaml.safe_load` in `run.py` and `validate.py`, outside `decoy/cli/gate/`. Exemptions (named, ratchet): `preflight.py` (the `validate preflight` command, until CONFIG-EXPLICIT C2) and `compile_explain.py` (the explicit `validate compile` command). No new exemption: `validate config` goes through the gate | add `_check_source_files(raw, ...)` to `run.py`: red; `import decoy_engine as de; de.run_config_only_checks(x)` in a scratch module: red; `from yaml import safe_load as s` in `run.py`: red; restore `validate.py`'s `_check_target_overwrite` and call it: red |
| One config validation in the run path | `GateResult.config` | the same sentry flags `decoy_engine.PipelineConfig.model_validate` in `run.py` and `validate.py` | restore `run.py:684`: red |

The sentry is seeded-bypass tested, registered in `SENTRIES` and `scripts/dev/sentry_registry.toml`,
and runs in the merge gate's sentry step. Its exemption list is a ratchet that only shrinks.

## 7. Acceptance tests

Each names the mutation that turns it red; red-first evidence is an assertion failure.

- AT-1 (stop before read): missing source, `decoy run`: exit 1, stderr names
  `sources.customers.path`, no target file, `read_source` never called. Replaces the exit-3
  expectation at `test_run_command.py:344` (Q2, owner). Mutation: gate after the read.
- AT-2 (compile error before read): a config whose no-profile compile fails: exit 1 with the
  compile `code`; spy shows no read. Mutation: drop the compile layer from `run_gate_on_config`.
- AT-3 (capacity, plain): the T8 fan-in topology: `decoy run --json` exits 5 with
  `error_kind: "capacity"` and `code: "out_of_core_fanin_exceeds_budget"`, before `run_pipeline`.
  Mutation: map a gate capacity refusal to 1.
- AT-3c (capacity, chunked; M2): the `remap` variant of T8 under `--chunked` is not refused by the
  gate (no exit 5) and `decoy run` reaches `run_mask_pipeline_chunked`; the T8 `preserve` graph
  under `--chunked` exits 1 with `chunked_fk_orphan_policy_not_remap`. P2 records the variant's
  final exit. Mutation: drop the route rule: the variant exits 5, red.
- AT-4 (unique column, Q1): unique-column config with its source present: `decoy run` exit 0 with
  output written; `decoy validate` exit 0 with warning `compile.needs_profile`, exit 2 with
  `--fail-on-warning`; `decoy validate compile --no-profile` still exit 1. Mutation: restore the
  error severity.
- AT-5 (JSON shape): for every refusal in the parity matrix, the envelope has `command`, `status`,
  `config`, `mode`, `error`, `error_kind`, and `messages` equal to `decoy validate --json`'s
  `messages` for the same config. Mutation: emit `messages` only for config-layer failures.
- AT-5e (missing extra; H1a): NER-absent config (spaCy import patched out): `decoy run --json`
  exits 1 with `error_kind: "missing_extra"` and `extra: "ner"`, as today. Mutation: drop `extra`
  from `GateFinding`: red.
- AT-5y (YAML; M1): empty file, a YAML list, and a syntax error: `decoy run` exits 1 with
  `yaml.empty`, `yaml.not_mapping` and `yaml.parse_error`, the same codes `decoy validate` gives.
  Mutation: restore `run.py:576-588`; the sentry is red and the codes differ.
- AT-6 (warnings): a target that already exists: `decoy run` exit 0 and one stderr line with the
  warning count; `--json` stdout is one JSON document; `--quiet` prints nothing. Mutation: print
  each warning to stdout.
- AT-7 (secrets): a wrong-typed `mask_secret_ref` holding a marker still exits 1 through the DE-02
  guard and the marker appears in no output; a config with keyed strategies and only
  `--mask-secret env:X` passes the gate. Mutation: move the gate above the DE-02 guard.
- AT-7m (corrupt CSV; M3): a CSV source with a marker in a malformed row: `decoy run`, `decoy run
  --json` and `decoy validate --json` exit 1 with `capacity.source_unreadable`, and the marker is
  in no output. A 600-character finding message is cut to 500 plus `...` in `messages`. Mutation:
  restore the engine message in `_check_capacity`; drop the per-message cap.
- AT-8 (duckdb): `--duckdb-source` with a declared table runs the gate on the staged Parquet path
  and exits 0; after a gate refusal the temp dir is gone. Mutation: run the gate on the YAML before
  staging.
- AT-9 (chunked): the missing-source cell under `--chunked` exits 1 before `iter_source_chunks`.
  Mutation: place the call inside the non-chunked branch only.
- AT-10 (notify): a gate refusal with `--notify` pointing at a local test server sends one failure
  event whose `error_summary` is `PreRunCheckError`. Mutation: raise `typer.Exit` from the adapter.
- AT-11 (validate config fold; H2): `decoy validate config` gives the same envelope keys, codes
  and exit codes as on the base for the existing `test_validate_command.py` and
  `test_validate_sp16.py` cells, except the target-overwrite code listed in 11d. Mutation: drop the
  target-overwrite advisory from the config layer.
- AT-12 (chain): `PreRunCheckError` has `__cause__ is None` and `__context__ is None`. Mutation:
  raise it inside an `except` block.
- AT-14 (runtime still 3; L1): a valid config whose `run_pipeline` raises `RuntimeError` after the
  gate passes exits 3 with `error_kind` absent. Mutation: classify every exception after the gate
  as usage.

Retargeted tests (M4). Each keeps its assertion and moves its lookup site only:

| Test | Today | After | Rule |
|---|---|---|---|
| `tests/unit/test_ci_rule_codes.py:143-150` `_cli_gate_codes` | walks `decoy.cli.validate`'s AST for `_GateFinding(...)` | walks `decoy.cli.gate._layers` for `GateFinding(...)` | the walk covers the module that builds findings |
| `tests/unit/test_ci_rule_codes.py:292` | `{"yaml.parse_error", "missing_extra", "validation_error"} <= codes` | adds `compile.needs_profile` to the required set | the new code must be allowlisted |
| `tests/e2e/test_ci_unexpected_failures.py:70` | patches `("decoy.cli.validate", "run_gate")` | patches `("decoy.cli.gate", "run_gate")` | patch where the adapter looks it up |
| `tests/e2e/test_validate_gate.py:295-296` | patches `validate_mod._run_compile_layer`, `_run_preflight_layer` | patches the same names on `decoy.cli.gate._layers` | same short-circuit assertion, new lookup site |
| `tests/e2e/test_run_command.py:331-344` | missing source exits 3 | becomes AT-1 (exit 1) | Q2, owner-approved contract change |

Size (L3): no hard-coded line-count test. File sizes are evidence in each part's gate record, and
the LAYOUT C2 size ratchet holds `run.py` at its allowlisted value once C2 lands.

## 8. Parts (slices)

Commit subjects: Conventional Commits, at most 72 characters, final line `cam`, no body unless it
explains why. Test depth T0 per edit, T1 per commit and slice head, T2 at the gate.

| Part | Branch | Base | Lane | Depends on | Hand-written lines |
|---|---|---|---|---|---:|
| P1 gate package | `feat/validate-always-p1-gate` | CLI main | none (no `run.py` edit) | none; can build now | ~480 (moved lines not counted) |
| P2 run wiring | `feat/validate-always-p2-run` | CLI main after P1 | `run.py` lane | P1 merged; CLI-DIALECT's `run.py` writer merged; lane free | ~450 |

**P1.** Move `validate.py:394-644` to `gate/_layers.py` unchanged; add `parse_pipeline_yaml`,
`run_gate_on_config`, `GateRoute`, `GateResult.checks_run` and `.config`, `GateFinding.extra`, the
Q1 severity change, the target-overwrite move into the config layer, the fixed
`capacity.source_unreadable` text, the CODEMAP row, the `ci/adapters.py` import, and the
`ci/rule_codes.py:39-46` `_CLI_GATE_CODES` edit (add `compile.needs_profile`, remove
`no_profile_unique_incompatible`, which the gate no longer emits). Fold `validate config` onto
`run_config_gate` and delete `validate.py:164-188`. AT-4, AT-7m (validate cells), AT-11, the
retargeted tests and the sentry with its seeded cases. Subject:
`refactor(cli): move the pre-run gate into cli/gate`.

**P2.** `gate/_run.py`, the `run.py` parse call, gate call and handler branch with the offsetting
deletions, `ERROR_TEXT_CAP` read at `run.py:1072-1073`, AT-1 to AT-3c, AT-5 to AT-10, AT-12, AT-14,
the CHANGELOG `### Changed` entry (Q2: exit-code moves, `--json` members, Q1 severity, `ci check`
rule-id change), and `docs/cli-reference.md` for `run`. Subject:
`feat(cli): run the validate gate before decoy run reads data`.

## 9. Test scope and in-flight sequencing

| In flight | Touches | Effect |
|---|---|---|
| CLI-DIALECT (row 19; engine `feat/csv-source-reader`; CLI part not on origin yet) | `cli/_sources.py`, the run read points | P2 waits for its `run.py` writer (lane rule 5.2.2). The gate reads no rows, so no reader conflict |
| CONFIG-EXPLICIT (row 22, plan pending; C1 adds `_config_load.py`, C2 edits `validate.py:277,466`) | the gate's config site, `validate config`, `run.py:683` | P1 is expected first (C1 waits on two engine releases). C1 and C2 then edit `gate/_layers.py` only; `validate.py:277` and `run.py:683` are already gone. Their header and column checks reach `run` with no extra wiring |
| VALUE-FREE-ERRORS (engine `plan/value-free-errors`, CLI part A3) | sites `validate.py:277,462`, `run.py:684` | P1 leaves one site, in `gate/_layers.py`; P2 deletes `run.py:684`. A3 re-measures; its Click-tree walk covers `run` through the gate. Names stay visible and values hidden, per its Q1 |
| RESULT (row 62, CLI half after R-d) | `run.py` error path and envelope | lands after P2; its exit map classifies `PreRunCheckError` as `usage` or `capacity` and its document records the gate (FU-3) |
| CLI-FMT A, SUB-RUN, CLI delivery, LIB L3a+, F29 C1, F30 C1b | `run.py` | ordinary lane order; P2 holds the lane for one slice |

Full-suite trigger: P2 (exit-code mapping on a public contract). P1 runs T1: tests importing
`validate`, `ci.adapters`, `ci.rule_codes`, `preflight` or `plan`; `tests/e2e/test_validate_*`,
`test_ci_*`, `test_preflight_*`, `test_compile_explain_command.py`; all sentries.

## 10. File sizes

| File | Today | After |
|---|---:|---:|
| `src/decoy/cli/validate.py` | 807 | ~450 |
| `src/decoy/cli/gate/_layers.py` | new | ~340 |
| `src/decoy/cli/gate/_run.py` | new | ~100 |
| `src/decoy/cli/gate/__init__.py` | new | ~30 |
| `src/decoy/cli/run.py` | 1805 | at or below 1805 |
| `src/decoy/cli/preflight.py` | 886 | at or below 886 |
| `src/decoy/ci/adapters.py`, `ci/rule_codes.py` | 289, 161 | 289, 161 |
| `tests/e2e/test_run_validate_always.py` | new | ~380 |
| `tests/sentry/test_gate_single_entry.py` | new | ~170 |

## 11. Recurring-defect coverage

Class 3: `PreRunCheckError` is raised after any `except` closes (AT-12). Class 5: the sentry
resolves imports and aliases to `(module, name)`, with a seeded case per spelling. Class 9:
mutations re-run on each part's final head. Class 11: no pin raised; `run.py` and `preflight.py`
do not grow; `_CLI_GATE_CODES` swaps one code for another. Classes 1, 2, 4, 6, 7, 8 and 10 are not
touched: no regex, no persisted model, no new reader, no new private import (the existing
`preflight._check_*` imports move with the gate), no CI script.

## 11a. General review taxonomy (plan contract)

| # | Class | Applies | Closing structure | Proof and mutation |
|---|---|---|---|---|
| 1 | Value-bearing output | Yes: run's schema error stops printing `str(exc)` (with `input_value`); the unreadable-source finding stops embedding reader text; every message is capped | one config site in `gate/_layers.py`; fixed capacity text; `ERROR_TEXT_CAP` | AT-5, AT-7, AT-7m |
| 2 | Cleanup on an exit path | Yes: a gate refusal must still remove the `--duckdb-source` temp dir and send `--notify` | the refusal raises into run's one handler and `finally` | AT-8, AT-10; mutation: `typer.Exit` from the adapter: red |
| 3 | State machine and concurrency | N/A: one synchronous call, no shared state | none | none |
| 4 | Route parity and silent fallback | Yes: plain and `--chunked` runs, `--duckdb-source`, `validate`, `validate config` and `ci check` must see the same gate; the chunked route differs only by the named capacity rule | one entry, `GateRoute`, parity matrix, sentry | AT-1, AT-3c, AT-9, AT-11 |
| 5 | Referential integrity | N/A: no data or FK handling; the gate's FK compile checks are unchanged | none | none |
| 6 | Untrusted producer | Yes: the YAML is user input | the DE-02 guard stays ahead of validation; the gate reads `errors()` fields, never `input` | AT-7, AT-5y |
| 7 | Check then use (TOCTOU) | Yes: a source checked present can vanish before the read | accepted: the later read fails as today (exit 3, AT-14's class of failure); no lock | recorded limit |
| 8 | Weak tests and overclaimed evidence | Yes: a parity matrix that passes because neither command refuses | each cell asserts the refusal `code`; seeded sentry bypasses; numbers re-measured on each base | AT-1 to AT-3 assert codes |
| 9 | Behavior-preserving refactor drift | Yes: P1 moves about 250 lines and folds `validate config` | retargeted tests listed in section 7 with their rules; AT-11 | AT-11 |
| 10 | Frozen contract drift | Yes: exit-code mapping, `--json` members, `ci check` rule ids, `validate config` warning code | Q2, CHANGELOG, 11d | AT-5, AT-5e |

## 11b. Enumerations

### Exit paths

- Refusal: `PreRunCheckError` into run's handler (`run.py:917`), exit 1 or 5 (`:1005-1065`).
- Pass: the run continues to `--mask-secret` (`run.py:697`).
- Unexpected exception from the gate (for example from `_check_capacity`, `preflight.py:368`):
  propagates to the handler, exit 3 as today.

### Routes

- `decoy run` plain (`run.py:842`), `--chunked` (`:856`), `--duckdb-source` (`:628`), `--vault`,
  `--native` and `--no-native` (`:821`).
- `decoy validate` default gate (`validate.py:647`), `decoy validate config` (`validate.py:196`),
  `decoy ci check` (`ci/adapters.py:105`).

### FK shapes

- N/A: no FK handling; the compile layer's FK checks are unchanged. The chunked FK rules are read
  only for AT-3c.

### Fields

- No config model field is added or changed (`PipelineConfig` untouched).
- `GateResult` (`validate.py:601` today) gains `checks_run` and, last, `config: dict | None = None`;
  `GateFinding` gains `extra: str | None = None`. In-process only, never serialized as such.

### Output surfaces

- Run stderr: the refusal summary and the warning-count line.
- Run `--json` envelope (`run.py:1100-1124`): `error_kind` and `messages` added.
- `--notify` failure event: type name only, unchanged rule (`run.py:1087`).
- `decoy validate`, `validate config`, `validate preflight` and `ci check` output: the changes in 11d.

## 11c. Reuse inventory

`run_gate` and `gate_exit_code` (`validate.py:620,634`), `_emit_result` (`validate.py:323`),
`sanitize_yaml_error`, the preflight `_check_*` functions, `plan_compile_error_fields` and
`translate_ner_unavailable` (`extras.py:172,208`), run's existing error handler and `error_kind`
pattern, the T8 capacity topology fixture, the X0a ratchet and sentry registry.

## 11d. Frozen contracts

- Exit-code integers (`exit_codes.py`) do not change. `decoy run` moves from 3 to 1 for a missing,
  unreadable or corrupt source file and for an unexpected no-profile compile crash (Q2).
- `decoy run --json` failure: `command`, `status`, `config`, `mode` and `error` keep their names;
  `error` text changes for config refusals. `error_kind` keeps `"capacity"` (with `code`) and
  `"missing_extra"` (with `extra`) where today sets them; config refusals that today carry no
  `error_kind` now carry `"validation"`; `messages` is new.
- `decoy validate` default gate: a unique-column config moves from error
  `no_profile_unique_incompatible` (exit 1) to warning `compile.needs_profile` (exit 0, or 2 with
  `--fail-on-warning`) (Q1). The target-overwrite warnings move from the `preflight` layer to the
  `config` layer.
- `decoy ci check`: rule id `validate.no_profile_unique_incompatible` (error) becomes
  `validate.compile.needs_profile` (warning). Config-only mode now also reports the
  target-overwrite advisories (`target.<t>.would_overwrite`, `target.<t>.parent_missing`).
- `decoy validate config`: warning code `target_file.would_overwrite` becomes
  `target.<t>.would_overwrite`, and it gains `target.<t>.parent_missing`.
- `capacity.source_unreadable` message text (in `validate`, `validate preflight`, `ci check` and
  `run`) no longer carries the reader's exception text.

## 12. Pre-mortem

- A false refusal stops a run that works today. Known cases: unique columns (Q1) and capacity on
  the chunked route (M2), both closed. Others could come from the no-profile compile; the parity
  matrix plus the existing `test_run_*` suite on P2's head is the check, and a new case is fixed in
  the gate, not with a skip flag.
- The bounded profile in `_check_capacity` slows large runs. It reads at most 10k rows per file
  source, and `run_pipeline` repeats the same call. P2 records wall time for a 1M-row CSV and a
  1M-row Parquet run before and after; more than 10 percent slower is reported to the owner.
- An unexpected compile crash in the gate exits 1 where the same crash inside `run_pipeline` exits
  3. Accepted, as `decoy validate` behaves today; FU-4.
- A script that greps `decoy validate config` output for `target_file.would_overwrite` breaks.
  Pre-GA, listed in the CHANGELOG.
- `ci check` output drifts after the move beyond 11d. The CI suite runs with only the retargets in
  section 7.

## 13. Questions (owner)

- **Q1 (answered, owner 2026-11-06, recommended).** The aggregate `decoy validate` reports a
  `cardinality_mode: unique` config as a warning (`compile.needs_profile`);
  `validate compile --no-profile` keeps its error.
- **Q2 (answered, owner 2026-11-06, recommended).** `decoy run` uses validate's exit mapping, with
  `error_kind` and `messages` in `--json`, and a CHANGELOG entry (pre-1.0 MINOR,
  `docs/release/versioning.md`).
- **Q3 (answered, owner 2026-11-06, recommended).** No skip flag in V1.

Technical calls taken (recorded, not asked): gate package under `cli/gate/`; the gate returns the
validated config; warnings shown as a count only; the gate runs after `--duckdb-source` staging;
capacity is advisory on the chunked route; the target-overwrite advisory lives in the config layer.

## 14. Follow-ups

- FU-1: `decoy tokenize`, `decoy demo` and `decoy.mask()` call `check_before_run`, and the sentry
  gains a Click-tree walk over every command that calls `run_pipeline`.
- FU-2: check `--duckdb-source` relations before staging (CONFIG-EXPLICIT's `DESCRIBE` boundary).
- FU-3: RESULT records gate findings as a `checks[]` entry; `--json` success carries warnings
  through the result document.
- FU-4: the gate's broad `except Exception` in the compile layer maps to exit 3, like `run`.
- FU-5: fold the `validate preflight` command body onto the gate (CONFIG-EXPLICIT C2) and drop its
  sentry exemption.
- FU-6: a chunked-route capacity estimate, if the chunked path ever gains its own memory gate.

## 15. Done when

- [ ] P1 and P2 merged in order; `decoy run` refuses every parity-matrix config before any read,
      with `decoy validate`'s exit code and first code.
- [ ] No pre-run layer check or pipeline-YAML parse is called outside `cli/gate/` except the two
      named exemptions; the sentry's seeded bypasses were shown red on the final head.
- [ ] `validate config` runs through the gate and its duplicate `_check_target_overwrite` is gone.
- [ ] CHANGELOG lists every 11d change; `docs/cli-reference.md` updated.
- [ ] `run.py` and `preflight.py` did not grow and `validate.py` is under 800, recorded in each
      part's gate evidence; the CODEMAP row is in.
- [ ] P2's full suite shows no new failing id against the saved baseline; the timing note and the
      AT-3c variant's exit are recorded.
- [ ] Roadmap row 23 and `docs/RECENTLY-SHIPPED.md` updated when P2 merges.
