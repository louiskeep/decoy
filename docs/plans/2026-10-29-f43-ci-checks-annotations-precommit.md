# F43 FRAME + PLAN: CI checks, SARIF annotations, pre-commit, and portable manifest

Status: plan draft for independent review; no implementation has started.
Feature: F43 — CI checks, annotations, pre-commit `[V1*] [PARTIAL]`, CLI-led.
Repository / branch / baseline: `decoy`, `plan/f43-ci-integration`, `origin/main` at
`574aa1e9ec2b95f9ba8af5eb8112c1a3c0fcf434`.
Risk: **R2** — this adds versioned public schemas and exit behavior, emits security-tool
artifacts, scans potentially sensitive staged content, and creates CI supply-chain surfaces.
No author self-certification.
Owners: CLI and distribution tooling; engine owns checks and source-path provenance;
Platform owns export. Owner approval is required after independent plan gates.
Created: 2026-10-29. Plan author: Codex.

Rules consulted: `/home/cam/dev-rules/00-universal.md`,
`/home/cam/dev-rules/development-loop.md`, `/home/cam/dev-rules/risk-and-exceptions.md`,
`/home/cam/dev-rules/workspace-and-vcs.md`, `/home/cam/dev-rules/reuse-first.md`,
`/home/cam/dev-rules/exploration.md`, `/home/cam/dev-rules/scope-discipline.md`,
`/home/cam/dev-rules/verification.md`, `/home/cam/dev-rules/feature-dev.md`,
`/home/cam/dev-rules/testing.md`, `/home/cam/dev-rules/architecture.md`,
`/home/cam/dev-rules/api-and-compatibility.md`,
`/home/cam/dev-rules/config-secrets-and-supply-chain.md`,
`/home/cam/dev-rules/security.md`, `/home/cam/dev-rules/documentation.md`, and
`/home/cam/dev-rules/code-review.md`.

Authoritative product contract: the F43 MASTER text supplied with this task. Supporting
recall was retrieved from the indexed MASTER F43 section (`qmd://decoy-platform/docs/plans/
Market-Expansion-Specs/MASTER-Decoy-Feature-Specification.md`, lines 1244-1268), F12
(lines 438-462), F15-F18 (lines 516-600), and F29 (lines 880-904). The implementation
must follow the actual baseline below when a summary and code disagree.

## 1. FRAME

### Problem

Teams can wire Decoy into CI by hand, but each team must currently assemble commands,
parse output, decide exit precedence, and create platform-specific glue. There is no
portable check manifest, no SARIF result, no maintained GitHub/GitLab invocation, and no
staged-content guard. Hand-built wrappers can drift from the engine, leak a matched
sample into an annotation, or point a finding at the wrong YAML line.

F43 must add one reusable, local-first integration layer. It must orchestrate the checks
that already exist; it must not reimplement validation, drift, evidence, policy, or F12
regression semantics. Its new data-sensitive behavior is only the explicitly configured,
bounded staged-file literal scan.

### Guarantee

Given a valid `decoy-ci/v1` manifest, `decoy ci check` runs the selected existing Decoy
contracts, produces exactly one versioned value-free JSON report, SARIF 2.1.0 log, or
review-oriented Markdown report, and exits with the existing Decoy numeric taxonomy.
Every emitted finding contains only a stable rule/pattern ID, severity, fixed safe summary,
check identity, and an optional repository-relative source location. A resolved YAML
location points to the actual offending key in the actual source file; when origin cannot
be proved, the report omits the region rather than guessing. The same manifest can be
invoked by the shipped GitHub Actions workflow, GitLab CI template, and pre-commit hook.
The CLI itself never comments, uploads, or makes a network call.

The optional staged scan examines only the staged post-image of files selected from
`git diff --cached`; it never reads an unstaged worktree value. It uses configured exact
byte literals, is bounded by hard limits, and reports IDs/counts/locations without the
literal or matched value.

### Definition of done

1. A strict, typed, versioned `decoy-ci/v1` manifest and committed JSON Schema select:
   full or config-only validation; saved-scan drift comparisons; evidence-manifest
   verification; F12 regression-suite references; and optional staged sensitive-pattern
   scanning.
2. `decoy ci check MANIFEST --format json|sarif|markdown [--output PATH|-]` is documented,
   uses one normalized safe-result boundary, preserves the existing exit integers, and has
   deterministic ordering and stable contract tests.
3. SARIF validates offline against the official OASIS SARIF 2.1.0 Errata 01 schema,
   produces `results: []` for clean input, uses stable `ruleId` values, and maps proven
   YAML marks to repository-relative `artifactLocation.uri` plus one-based `region`.
4. A real pre-commit run, with networking disabled and a preinstalled `decoy`, blocks a
   staged fixture containing a configured seeded identifier and prints no identifier.
5. Maintained GitHub Actions and GitLab CI templates run only `decoy ci check`; they do
   not copy engine/CLI check logic. GitHub SARIF upload is an explicit customer workflow
   step with least privilege, not behavior inside Decoy.
6. The JSON, SARIF, Markdown, stdout, stderr, and verbose/log surfaces pass a seeded-canary
   leak sentry. The official schema, hook metadata, templates, examples, wheel, docs, and
   generated CLI reference are verified.
7. F12 and F18 gaps are handled honestly: a non-empty F12 selector fails closed until a
   real F12 runner exists; v1 has no manifest or pipeline includes. Neither missing feature
   is silently skipped or privately reimplemented in F43.

### Boundaries and non-goals

- V1 supports GitHub Actions and GitLab CI. Jenkins, CircleCI, Azure Pipelines, Bitbucket,
  and vendor-specific comment bots are not maintained integrations; they can call the
  portable CLI contract.
- Ship repository-hosted workflow/template YAML and root `.pre-commit-hooks.yaml` now.
  A Marketplace-packaged JavaScript/composite Action, GitLab Catalog component, installer
  action, and separate hooks repository may trail under the roadmap's reduced-scope rule.
- Templates do not install an unpinned runtime. They require a pre-provisioned, pinned
  `decoy` executable (F44 owns distribution) and fail if it is absent. Installation examples
  may show a customer-controlled pinned step, but the reusable check template owns no
  credentials or package index.
- No engine check, policy predicate, detector, scan-diff rule, evidence verifier, or F12
  comparison is duplicated. In particular, F16's “forbidden strategy with policy ID” is not
  present at this baseline; F43 projects such a finding once the engine supplies it.
- No arbitrary commands, shell snippets, environment interpolation, expression language,
  remote include, YAML custom tag, or plugin hook is accepted in the CI manifest.
- No automatic baseline approval, golden update, evidence signing, platform export UI,
  external PR comment, artifact upload, or SARIF upload. Platform export is a later consumer
  of the committed schema; it is not implemented in this CLI worktree.
- No claim that a literal pattern scan is PII classification, secret discovery, or evidence
  of absence. Coverage and false-positive behavior are stated explicitly below.
- No raw snippets, SARIF `region.snippet`, matched values, pattern literals, source rows,
  secret references, connection strings, or raw exception messages in CI reports.

### Phase-1 pillar alignment

| Pillar | F43 rule |
|---|---|
| One value-free boundary | Every adapter creates metadata-only candidates; one `SafeFinding` factory validates IDs/locations and supplies fixed message text. JSON, SARIF, Markdown, and logs consume only `SafeFinding`. |
| Bounded local work | Manifest counts, paths, staged blobs, literals, output findings, and Git subprocess duration have hard caps. Hook execution is offline and reads no source dataset for config-only mode. |
| Machine-readable/versioned | `decoy-ci/v1`, its JSON Schema, `decoy-ci-report/v1`, SARIF 2.1.0, and the existing numeric exit constants are contract-tested. |
| Fail closed | Unknown schema fields/versions/check kinds, unresolved requested F12 suites, missing inputs, limits, ambiguous source origin, and Git failures never become a pass. A location may be omitted, but a selected check may not be omitted. |
| No sample/secret leakage | Reports use rule IDs, counts, and safe locations only. A cross-format canary sentry guards the class, not individual messages. |
| Customer-controlled external effects | Decoy performs no upload or comment. CI service uploads occur only in customer-selected YAML with the service's explicit token/permissions. |

### Required FRAME decisions

| Required decision | Decision for `decoy-ci/v1` |
|---|---|
| Portable manifest | YAML or JSON mapping with literal `schema_version: decoy-ci/v1`; strict typed fields; `extra=forbid`; no custom tags/includes/interpolation/commands. Relative references resolve from the manifest directory, must remain under the Git root, and are rendered repository-relative. The committed JSON Schema is generated from and drift-tested against the typed model. |
| Default check set | If `checks` is omitted, run full `decoy validate` for every declared pipeline with warnings blocking. Drift, evidence, regression, and staged scans require explicit entries because they need baselines/artifacts/patterns. In pre-commit hook mode, validation is deliberately narrowed to existing `validate config` semantics and the configured staged scan; no source/preflight read occurs. |
| Supported CI systems | V1: GitHub Actions and GitLab CI, plus the portable local/pre-commit command. Ship YAML templates now; marketplace/catalog packaging can trail. |
| Locations through includes | Baseline engine F18 has no include/extends loader. V1 forbids `include` in both CI and pipeline schemas and maps a dotted engine/Pydantic path only within the single parsed YAML file. When F18 later returns an origin `{uri, dotted_path}` per finding, the same resolver must parse that origin file. Never map a flattened path to the root file by assumption. An unproved/ambiguous/wildcard path yields a file-level location or no location, never a false region. |
| Staged scan and false positives | Select changed paths from `git diff --cached`, read their exact stage-0 index blobs (never worktree files), and scan the whole staged post-image. V1 supports exact byte literals only, not regex/entropy/heuristics. Every pattern has a stable ID and required path globs. Reports aggregate by pattern ID and path and never echo the literal/match. Scope exclusions are path-based and explicit. Any skipped selected blob or exceeded limit makes the check partial and non-zero. |

## 2. Current baseline, with source anchors

### Existing contracts to preserve and reuse

- The dependency is hard-pinned to `decoy-engine==0.15.1`, stamp `fd51be10`, at
  `pyproject.toml:88-99`. Do not design against engine `main` or an imagined F16/F18/F12
  surface.
- Shared output plumbing emits exactly one compact JSON object on stdout in JSON mode
  (`src/decoy/ui/output.py:23-35,47-82,85-93`). The aggregate pre-run gate already emits
  `{command,status,config,messages[]}` (`src/decoy/cli/validate.py:661-700`). Each message
  carries layer, severity, code, message, and optional location
  (`src/decoy/cli/validate.py:394-406,689-697`).
- `decoy validate CONFIG` already composes config, compile, and preflight without
  reimplementing their checks (`src/decoy/cli/validate.py:417-580`) and defines aggregation
  precedence (`src/decoy/cli/validate.py:614-658`). `--fail-on-warning` is public on both
  config and aggregate paths (`src/decoy/cli/validate.py:221-228,608-612`) and returns the
  existing warning exit (`:319-320,656-657`). F43 must call/extract this result path, not
  create a second validator.
- Review-oriented Markdown exists: evidence reports are pure, offline manifest projections
  (`src/decoy/cli/report.py:21-34,326-333`), and `report render --format markdown` writes
  them (`src/decoy/cli/report.py:636-689`). F43 needs a CI-result Markdown projection, not
  a copy of evidence-report logic; both follow the same value-safe precedent.
- Evidence drift already has a pure verifier. `report verify` rehashes the pipeline,
  inputs, outputs, and manifest and returns `EXIT_FINDINGS` on mismatch
  (`src/decoy/cli/report.py:1465-1519`). The evidence manifest is explicitly versioned
  `cli-local-1` and excludes values/secrets/samples
  (`src/decoy/cli/evidence.py:65,128-163,277-296`).
- Discovery drift exists as `scan diff --strict`: it compares saved STORM scan JSON and
  identifies PII-bucket increases, new high-PII fields, and new QI groups without rereading
  raw data (`src/decoy/cli/scan.py:1132-1159,1192-1256`). Its direct-command compatibility
  behavior currently returns `EXIT_USAGE` on strict drift (`:1258-1292,1391-1392`); F43
  must not silently change that public command. Extract its categorization once and let the
  new CI aggregate classify detected drift as `EXIT_FINDINGS` in the new versioned contract.
- Report isolation is already a project invariant: renderers accept evidence-safe dicts and
  do not read source/output files (`src/decoy/cli/report.py:21-34,140-147`). Existing class
  sentries live at `tests/sentry/test_report_raw_value_isolation.py:1-180`,
  `tests/sentry/test_profile_raw_value_isolation.py`, and
  `tests/sentry/test_yaml_error_leak_isolation.py`. Extend this sentry layer rather than
  relying on one-off redaction in each emitter.

### Existing location representation

- Pydantic schema failures become dotted/indexed locations by joining `ValidationError.loc()`
  (`src/decoy/cli/validate.py:275-289` and `:459-470`).
- The pinned engine's `PlanCompileError` carries stable `code`, human `message`, and a
  dotted YAML `path`; examples are `tables.customers.columns.customer_id` and the path may
  be `None` for a global error (`decoy_engine/plan/_errors.py:24-47` at engine stamp
  `fd51be10`). `PipelineValidationError` uses the same optional dotted-path concept
  (`decoy_engine/errors.py:33-55`). The CLI copies `exc.path` into `_GateFinding.location`
  (`src/decoy/cli/validate.py:527-536`).
- This is a logical config path, **not** a physical file/line region. The baseline loader is
  `yaml.safe_load` followed by strict `PipelineConfig.model_validate`
  (`src/decoy/cli/validate.py:438-470`), so it discards PyYAML marks. F43 must add a parallel,
  read-only `yaml.compose` mark index over the same bytes and never mutate the value passed to
  the engine.
- Semantic engine paths name table/column list entries (`tables.<table>.columns.<column>`) while
  Pydantic paths may use list indexes. The resolver therefore indexes both numeric paths and
  aliases from mapping entries' `name` fields. Mapping keys such as `sources.<name>` are indexed
  directly. Wildcards and diagnostic pseudo-paths such as `<snapshot_file=...>` are not physical
  source paths and must not be guessed.

### Exit codes are already public

`src/decoy/cli/exit_codes.py:40-98` is authoritative:

| Integer | Existing constant | F43 usage |
|---:|---|---|
| 0 | `EXIT_OK` | all selected checks clean, or a genuine no-op such as no matching staged files |
| 1 | `EXIT_USAGE` | invalid manifest/input, unsupported requested dependency, bounded-scan refusal, or existing validation refusal |
| 2 | `EXIT_WARNINGS` | clean except advisory warnings when warnings are configured to block |
| 3 | `EXIT_RUNTIME` | CLI/engine/Git execution failed; report may be `partial` if earlier checks completed |
| 4 | `EXIT_FINDINGS` | evidence mismatch, selected drift, staged-pattern hit, or future F12/F16 finding |
| 5 | `EXIT_CAPACITY` | existing preflight capacity refusal |

The values are stable across releases (`src/decoy/cli/exit_codes.py:10-18`). F43 adds no
integer and does not reinterpret direct commands. `ok`, `noop`, `findings`, `partial`, and
`refused` are report outcomes, not new process codes. A `partial` report exits with the
underlying non-zero category (normally 1 or 3); a `refused` report exits 1 or 5 as applicable.
Reason IDs use existing engine/CLI codes and F29 vocabulary when present; F43-specific reasons
use the namespaced `ci.*` registry documented with this contract.

### Honest dependency gaps

- F12 is only partial at this baseline: dual-run/internal primitives and `report verify/diff`
  exist, but there is no user-invoked rehearsal command or portable customer suite runner.
  F43 may type and select an F12 suite reference, but cannot execute one without duplicating
  F12. Non-empty `regression_suites` therefore returns `ci.regression_runner_unavailable` /
  `EXIT_USAGE` until a real public F12 runner lands.
- F16 has no reusable prohibition language or policy-ID compile finding at this baseline. The
  example “forbidden strategy” annotation becomes automatic when the engine emits that coded
  finding; F43 does not invent a policy evaluator.
- F18 has no include/extends/fragment loader. That absence determines the v1 include decision
  above.

## 3. Established solutions researched first

Searches were run before design against official primary sources:

- `site:docs.oasis-open.org sarif v2.1.0 physicalLocation region artifactLocation schema`
- `site:docs.github.com code scanning SARIF upload annotations pull request physicalLocation`
- `site:pre-commit.com .pre-commit-hooks.yaml pass_filenames offline`
- `site:docs.gitlab.com CI YAML include templates project local remote`
- `site:git-scm.com/docs/git-diff --cached staged changes index`

### Adopted patterns

1. **SARIF 2.1.0 Errata 01, not a guessed JSON shape.** The
   [OASIS standard](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html)
   defines `physicalLocation` as artifact plus region and requires a result region to identify
   where the result was detected (§3.29). Text regions are one-based and `endColumn` is
   exclusive (§3.30). Use the official
   [OASIS schema](https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json)
   as the offline test oracle. Vendor that schema under `tests/fixtures/schemas/` with its
   source URL, retrieval date, SHA-256, and OASIS notices; do not add a runtime SARIF library
   merely to assemble a small pure projection.
2. **GitHub annotation is an explicit upload consumer.** GitHub documents that third-party
   SARIF is uploaded by a separate `github/codeql-action/upload-sarif` step and requires
   `security-events: write` plus read permissions as applicable
   ([upload guide](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file)).
   Code scanning uses stable `ruleId` and locations for alert identity/annotations
   ([SARIF support](https://docs.github.com/en/enterprise-cloud@latest/code-security/reference/code-scanning/sarif-files/sarif-support)).
   Decoy only writes the file; the customer template owns the upload and token.
3. **Use the pre-commit provider contract.** A hook provider supplies root
   `.pre-commit-hooks.yaml`; hooks fail by non-zero exit; `pass_filenames: false` prevents
   worktree filenames from becoming the scan source; `always_run: true` lets the command
   determine a true staged no-op. These fields and staged execution are defined by
   [pre-commit's official documentation](https://pre-commit.com/index.html#creating-new-hooks).
   Use `language: unsupported` (the maintained name for the former `system` language) so a
   preinstalled pinned `decoy` is invoked with no environment download. Document the minimum
   pre-commit version supporting this spelling.
4. **GitLab ships include-able YAML, pinned by the customer.** GitLab merges included config
   first and supports `include:local`, `project`, `remote`, and template forms. Remote includes
   should be integrity-pinned; project includes should use protected immutable refs
   ([GitLab YAML reference](https://docs.gitlab.com/ci/yaml/#include)). The shipped file is a
   normal include-able job template; customer config chooses/pins the source.
5. **The Git index is the source of truth.** `git diff --cached` is the change between HEAD and
   the index—the content that would be committed
   ([git-diff documentation](https://git-scm.com/docs/git-diff)). The index stores each staged
   file as a blob ([Git data model](https://git-scm.com/docs/gitdatamodel.html)). Enumerate the
   cached path set, resolve stage-0 blob IDs with Git plumbing, and read blobs by object ID.
   Do not read the worktree or parse human patch text.

### Reuse/custom-code decision

- Reuse PyYAML already present through the engine for `safe_load`/`compose` and promote
  `pydantic>=2,<3` to a direct CLI dependency because the CLI will own a Pydantic schema
  instead of relying on a transitive dependency (`validate.py` already imports it).
- Add `jsonschema>=4,<5` only to the `dev` extra to validate the vendored OASIS draft-04
  schema. No runtime validation dependency is needed for emitted SARIF.
- Use stdlib JSON, subprocess, pathlib, and exact byte search. Do not add a regex engine,
  patch parser, secret-scanning package, or SARIF SDK for v1.
- Custom code remains necessary only for: typed orchestration across Decoy's existing result
  types; dotted-path-to-YAML-mark resolution; a pure SARIF/Markdown projection; and bounded
  exact-literal inspection of Git index blobs. Each is Decoy-specific glue, not a substitute
  for an existing standard or engine check.

## 4. Public contracts

### 4.1 `decoy-ci/v1` manifest

Canonical example (also commit as `examples/decoy-ci.yaml`):

```yaml
schema_version: decoy-ci/v1

pipelines:
  - id: primary
    path: pipeline.yaml

checks:
  validation:
    enabled: true
    mode: full
    pipelines: [primary]
    fail_on_warning: true
  drift:
    - id: discovery-baseline
      baseline: ci/baselines/customer-scan.json
      current: build/customer-scan.json
      blocking: true
  evidence:
    - id: protected-output
      manifest: build/evidence.json
  regression_suites: []

staged_scan:
  enabled: true
  patterns:
    - id: pii.seeded-test-identifier
      literal: "DECOY_TEST_IDENTIFIER_"
      paths: ["fixtures/**", "examples/**"]
      exclude_paths: []
```

Typed rules:

- `schema_version` is required and exactly `decoy-ci/v1`.
- IDs match `^[a-z][a-z0-9_.-]{0,63}$` and are unique within the manifest.
- `pipelines` is a non-empty list of at most 32 `{id,path}` records. Paths are UTF-8,
  repository-relative regular files; absolute paths, `..`, NUL, outside-root resolution, and
  duplicate resolved paths are rejected.
- `validation.mode` is `full` or `config`. The normal CI default is `full`; hook mode uses
  `config` regardless of the normal mode and records the effective mode in its report. It
  does not mutate the manifest or pretend preflight ran.
- `drift` has at most 32 saved-scan pairs and reuses the current `scan diff` categorizer.
  `blocking: false` yields a warning; `true` yields a finding.
- `evidence` has at most 32 `cli-local-1` manifest paths and reuses the existing verifier.
- `regression_suites` has at most 16 `{id,suite}` references. At this baseline, any non-empty
  list is a clean refusal with the stable safe reason above. Empty is not reported as a check
  and does not create a false “passed regression” claim.
- `staged_scan.patterns` has at most 32 entries. Each exact UTF-8 literal is 4-128 bytes,
  IDs are safe, and at least one repository-relative path glob is required. Literals are
  never emitted or persisted beyond the customer-authored manifest. `exclude_paths` only
  narrows path scope; v1 has no value suppression or broad default detector corpus.
- Unknown fields, aliases, YAML merge keys, duplicate YAML keys, anchors/aliases, custom
  tags, and multiple YAML documents are rejected. `yaml.safe_load` alone does not reject all
  of these; the compose pass must enforce the contract before Pydantic validation.
- Relative paths resolve against the manifest directory, then are checked against the Git
  root. Output paths may be `-` or a repository-local regular path; refuse symlink targets
  that resolve outside the root.
- No implicit search for manifests. The CLI argument defaults only to the literal
  `.decoy-ci.yaml` in the current directory and reports that path. Platform export writes
  this same schema; no hidden catalog/state exists.

Commit a generated `docs/schemas/decoy-ci-v1.schema.json`. A sentry regenerates it from the
typed model and compares bytes so model/schema cannot drift. Schema changes within v1 may only
be backward-compatible optional additions with defined omitted behavior; a changed meaning or
new required field needs `decoy-ci/v2` and an owner-approved compatibility plan.

### 4.2 Normalized safe result and outputs

The only emitter input is an immutable `SafeCiReport` containing:

```text
schema_version = "decoy-ci-report/v1"
status = ok | noop | findings | partial | refused
exit_code = one of 0..5 from decoy.cli.exit_codes
checks[] = {id, kind, status, reason_code, finding_count}
notes[] = {note_id}  # authored, value-free text IDs only (e.g. `ci.precommit_mode_narrowed`); never a scalar, path, or value
findings[] = {
  rule_id, level(error|warning|note), safe_message_id,
  check_id, optional SourceLocation(uri,start_line,start_column,end_line,end_column),
  fingerprint_inputs = {rule_id, normalized_repo_relative_path?, logical_config_path?}
}
```

`SafeFinding.create(...)` is the choke point:

- accepts no free-form message and no `detail`/sample/exception field;
- validates `rule_id`, `check_id`, and `safe_message_id` against bounded token grammars;
- maps `safe_message_id` to fixed authored text such as “Selected validation rule failed” or
  “Configured sensitive pattern matched staged content”;
- accepts only repository-relative URI plus positive numeric region;
- sorts/deduplicates by `(check_id, rule_id, uri, line, column)`; and
- derives a stable, value-free fingerprint from `(rule_id, normalized repo-relative path, logical config path)` for `partialFingerprints`, so a finding tracks across line moves; the fingerprint inputs are tokens/paths only and carry no scalar value.

Adapters may retain raw messages only inside their existing direct-command renderer. The F43
adapter passes code, severity, and logical path to the safe factory and discards raw prose before
the report boundary. No emitter has access to the manifest's literal patterns or child exception.

JSON is one compact object through `emit_json`. Markdown is generated from the same report and
contains a summary table plus findings by rule/location; it contains no code block or source
snippet. Both are deterministic apart from no timestamp being emitted at all.

SARIF projection:

- root `$schema` is the official OASIS Errata 01 schema URI; `version` is `2.1.0`; one run;
- `tool.driver.name = "Decoy"`, `semanticVersion` is the installed CLI version, and
  `rules[]` is the sorted unique rule registry for this run: EVERY `ruleId` used by a result
  MUST have a matching `rules[]` object carrying `id` (equal to the `ruleId`) and
  `shortDescription.text` derived from its `safe_message_id`. A result whose `ruleId` has no
  `rules[]` entry is a build-failing projection error, since SARIF 2.1.0 requires the rule to be
  defined in the driver;
- each finding becomes one result with `ruleId`, mapped SARIF `level`, fixed
  `message.text`, a `partialFingerprints` map with a versioned primary key (`primary/v1`)
  computed from the finding's value-free fingerprint inputs (so code-scanning tools track an
  alert across line moves instead of churning it as new/fixed), and at most one location;
- `artifactLocation.uri` is percent-encoded repository-relative POSIX form. Do not emit an
  absolute `file://` URI, workspace path, `uriBaseId` requiring a leaked base, or path outside
  the repository;
- `region` is emitted only when a source mark is exact. Start line/column are one-based;
  end line/column are included only when valid under SARIF's exclusive-end rule;
- omit `snippet`, `contextRegion`, raw invocation command line, environment, stdout/stderr,
  exception objects, and attachments; and
- clean execution still emits a schema-valid run with `results: []`. SARIF output format does
  not change the process exit selected by the runner.

Debuggability escape hatch (never on the safe path): a hidden `--unsafe-debug-log PATH` may write
a separate, unstructured text file with raw exception and subprocess prose for local diagnosis. It
is never written to stdout/stderr, is never emitted as a CI-template artifact, and the CLI help and
docs warn prominently that its contents are unsafe, may contain secrets or sample values, and must
not be parsed or uploaded. This keeps the single safe `SafeFinding`/`SafeCiReport` boundary intact
so a developer diagnosing an orchestration failure is never tempted to weaken it.

### 4.3 Outcome and exit aggregation

Run all independent selected checks in manifest order, but never run a dependent check after its
input/refusal makes it meaningless. Report every completed check. Numeric precedence is:

1. capacity refusal: 5;
2. runtime failure: 3;
3. invalid/refused input or unsupported selected dependency: 1;
4. findings: 4;
5. blocking warnings: 2;
6. clean/no-op: 0.

This ordering preserves the existing aggregate's capacity/error precedence while keeping genuine
data/policy findings distinct. `status=partial` means at least one check completed and another
could not complete; it never exits 0. `status=refused` means no selected check ran. `status=noop`
is only valid when all selected work is genuinely inapplicable (for example staged-scan-only with
no staged matching paths); it exits 0 and records `ci.no_staged_files`.

### 4.4 Source-location resolver

`YamlSourceIndex.from_bytes(uri, data)` performs a compose-only pass over the exact bytes already
given to `safe_load`. It stores marks for mapping keys and scalar/list values under:

- numeric paths (`tables.0.columns.2.provider`);
- semantic aliases for named table/column/generate-column list entries
  (`tables.customers.columns.email.provider`); and
- normal mapping-key paths (`sources.customers.path`).

Resolution chooses the deepest exact key, never a fuzzy substring. If the exact leaf is absent,
it may fall back to the nearest proved parent key in the same file and marks the finding as
file/parent-level; wildcard, ambiguous alias, duplicate name, pseudo-path, or unknown origin has
no region. Unit tests cover quoted keys, Unicode, CRLF, block/flow style, list indexes, semantic
aliases, duplicate names, and malformed YAML. The index contains marks and path tokens only; it
does not enter reports or logs with scalar values.

### 4.5 Staged scan algorithm and hard limits

Trust boundary: the repository, manifest, Git filenames, index metadata, blob bytes, and Git
errors are untrusted. Invoke Git with argv arrays, `shell=False`, repository root as `cwd`,
`--no-ext-diff`, no textconv, and a sanitized locale. Never execute hooks, filters, attributes,
or a filename as a revision/option.

1. Resolve the Git root with `git rev-parse --show-toplevel`; require it to equal/contain the
   manifest root under the path rules above.
2. Enumerate staged `A/C/M/R` post-image paths with NUL-delimited
   `git diff --cached --name-status -z --no-ext-diff --diff-filter=ACMR`.
3. Resolve each selected path's stage-0 blob ID via NUL-safe Git plumbing and read the blob by
   object ID with `git cat-file`, never by opening the worktree path. Refuse unmerged entries,
   submodules, symlinks, missing stage-0 blobs, or blob/path identity disagreement.
4. Apply pattern path globs, then exact byte search. The whole staged post-image is scanned, not
   only added lines; document this to make false positives predictable. For valid UTF-8 text,
   compute a line/column without retaining the matched line. For binary/non-UTF-8 blobs, emit a
   file-level finding only.
5. Aggregate repeated hits by `(pattern_id,path)` with count capped in memory. Output the count,
   ID, and safe location only.

Defaults are also hard maxima in v1 (customers may lower, never raise): 200 staged files, 1 MiB
per blob, 5 MiB total bytes, 32 patterns, 128 bytes per literal, 100 emitted finding groups, and
10 seconds total Git subprocess time. Exceeding a cap, timeout, or unreadable selected blob yields
`status=partial`, reason `ci.staged_scan_limit` or `ci.git_failure`, and `EXIT_USAGE`/`EXIT_RUNTIME`;
it never reports the inspected subset as clean.

False-positive policy: exact customer literals and required path scopes only; no built-in
heuristic/entropy/PII detector, no regex, no case folding, and no value allowlist. A false positive
is corrected by narrowing the literal or path scope in reviewed config. Suppressing by raw value in
another file is deliberately unsupported because that creates a second sensitive-value store.

## 5. RED-first acceptance suite

Slice 0 writes these tests and fixtures before production code. Record their expected failures on
baseline `574aa1e`; no test may be skipped, loosened, replaced by schema-shape-only assertions, or
mocked past the boundary it claims to prove.

1. **Official SARIF validation and zero-hit clean case**
   (`tests/e2e/test_ci_sarif.py`): run the real CLI on a clean real pipeline; parse stdout/file;
   validate with `jsonschema` against the vendored OASIS schema; assert `version=2.1.0`, one run,
   `results == []`, and exit 0. The schema is the oracle, not a hand-picked key list.
2. **Correct safe physical location**: use a hand-authored YAML fixture with stable line numbers
   that triggers a real pinned-engine coded compile/schema finding (for example an actual
   `unknown_provider` path, not a fabricated `CiFinding`). Run `decoy ci check --format sarif` and
   assert exact repo-relative URI, `ruleId`, start line, and start column. Move the bad key in a
   second fixture and assert the region moves. Assert there is no snippet. When F16 supplies a real
   policy-ID finding, add the MASTER forbidden-strategy fixture to this same oracle; do not mock F16
   in F43. **Location-free case:** trigger a real engine finding that has no provable logical path
   (for example a global/config-level error), run `--format sarif`, and assert the run stays
   schema-valid and that finding's `result` either omits `locations` entirely or emits
   `locations: []`, never a `locations` entry with a missing `physicalLocation`. Assert the same
   result still carries valid `partialFingerprints` and that its `ruleId` has a matching
   `tool.driver.rules[]` entry.
3. **Exit matrix** (`tests/e2e/test_ci_exit_codes.py`): real clean validation -> 0/`ok`; staged-only
   manifest with no staged matching file -> 0/`noop`; real evidence mismatch or staged hit ->
   4/`findings`; one clean check followed by a forced real Git/runtime failure -> 3/`partial`;
   malformed manifest, over-limit scan, and non-empty F12 selection -> 1/`refused` or `partial` as
   specified; real validation warning with `fail_on_warning` -> 2; existing capacity fixture -> 5.
   Assert imported constants, never integer literals. Do not mock the final command/exit boundary.
4. **Manifest strictness and portability** (`tests/unit/test_ci_manifest.py`): version, omitted
   defaults, duplicate IDs/keys, unknown fields, YAML aliases/merge keys/custom tags/multiple docs,
   absolute/outside paths, symlink escape, oversized lists/literals, invalid globs, and deterministic
   generated-schema parity. Non-empty regression selection must fail closed, not disappear.
5. **Location resolver** (`tests/unit/test_ci_locations.py`): exact numeric/semantic aliases and
   PyYAML marks across block/flow/Unicode/CRLF inputs; ambiguous names/wildcards/pseudo-paths produce
   no guessed region. Use actual parsed YAML bytes and real dotted paths.
6. **Pure projections** (`tests/unit/test_ci_reporting.py`): the same `SafeCiReport` projects to
   stable JSON, schema-valid SARIF, and Markdown; ordering/dedup is deterministic; clean means zero
   SARIF results. Attempting to supply a free message, absolute URI, bad token, zero line, or raw
   exception is structurally impossible or rejected at the factory.
7. **Staged index, not worktree** (`tests/e2e/test_ci_staged_scan.py`): in a real temporary Git repo,
   stage a canary then replace the worktree with clean content; the scan still blocks. Reverse it
   (clean index, dirty worktree canary) and the scan passes. Cover rename, deletion, symlink,
   non-UTF-8/binary, weird filename, unmerged index, per-file/total cap, timeout, and no staged files.
8. **Real offline pre-commit** (`tests/e2e/test_ci_precommit.py`): validate the shipped provider
   manifest, configure the repository hook, set `PIP_NO_INDEX=1` and network-denying test guards,
   stage a violating fixture, and run actual `pre-commit`. It must use the preinstalled executable,
   exit non-zero, name only pattern ID/path/count, and contain neither literal nor value. A clean
   staged fixture passes. This proves hook metadata plus CLI, not a direct helper call.
9. **Thin GitHub/GitLab invokers** (`tests/unit/test_ci_templates.py`): parse both shipped YAML files,
   assert their check step is exactly the documented `decoy ci check` contract, runtime version is
   checked, output artifact paths are fixed, no engine/check logic or curl/comment command appears,
   and GitHub upload—if enabled—is a distinct explicit `upload-sarif` step with least permissions.
   Execute the extracted local command against fixtures in e2e; static YAML parsing is sufficient only
   for the platform syntax/invoker assertion.
10. **Leak class sentry** (`tests/sentry/test_ci_output_isolation.py`): seed distinctive canaries into
    a staged blob, pattern literal, pipeline scalar, engine exception source, evidence manifest, and
    absolute temp root. Exercise clean/finding/refused/partial paths in JSON, SARIF, Markdown, stdout,
    stderr, and verbose mode. Assert the full canaries and identifying substrings are absent from every
    byte artifact. Assert no SARIF snippet/context and no raw `str(exc)`. Keep this as one parameterized
    build-blocking sentry so every future emitter automatically inherits the class guard.
11. **Existing-contract regression**: current validate JSON shapes, `--fail-on-warning`, direct
    `scan diff --strict` exit behavior, report verify output, report Markdown, CLI surface/reference,
    and all current sentries remain unchanged unless an explicit compatibility decision above says
    otherwise.

## 6. Proposed structure and design notes

New package:

```text
src/decoy/ci/
  __init__.py       public schema/report version constants only
  contracts.py      typed manifest, SafeFinding/SafeCiReport, reason/exit aggregation
  locations.py      compose-only YAML mark index and dotted-path resolver
  adapters.py       thin validation/drift/evidence/F12 adapters
  staged.py         bounded Git-index exact-literal scan
  reporting.py      pure JSON/SARIF/Markdown projections
  runner.py         ordered orchestration; no check semantics
src/decoy/cli/ci.py Typer surface and file I/O only
```

This split is earned by distinct reasons to change: public contract/versioning, YAML source mapping,
existing-check adaptation, Git trust-boundary code, output standards, and orchestration. It prevents the
security choke point from becoming a general CLI file and lets future F12 add one adapter without editing
emitters. It is not a plugin system: the v1 adapter registry is a closed typed mapping, and arbitrary
commands are impossible.

Concrete reuse/refactors:

- Extract the aggregate validation computation from `_gate` into a typed, side-effect-free result
  function used by both existing `validate` rendering and the F43 adapter. Preserve existing CLI bytes/
  exits with golden regression tests. Do not call the Typer command recursively and do not duplicate its
  three layers.
- Extract `scan diff` categorization into one pure typed function; the existing command renders its
  current JSON/human output and keeps its current exit. The CI adapter consumes only safe category IDs
  and counts.
- Make typed evidence issues the source of truth beneath `verify_manifest`; preserve the existing
  public list-of-strings output by rendering those typed issues for `report verify`. The CI adapter never
  parses prose.
- The F12 adapter is an explicit unavailable adapter at this baseline. Replace it only when F12 exposes a
  public typed runner; that change must add a real cross-contract acceptance test and may not invoke an
  internal golden test suite.
- Register `ci_app` in `src/decoy/__main__.py` following the current Typer pattern
  (`src/decoy/__main__.py:140-157`). Add `decoy ci check` to root help.

House style: typed context objects rather than long parameter lists; single-purpose functions; no boolean
flag that changes a function's meaning (separate full/config validation adapter methods); one source for
each exit/reason/message mapping; comments explain security/location reasons. No renderer reaches back to
raw adapter objects.

## 7. Implementation slices and gates

Every slice ends in this mandatory loop: **self-check diff and invariants -> targeted verification with
observed output -> adversarial independent review -> remediate every supported finding -> repeat
self-check and targeted verification before re-review**. Three review rounds on the same unresolved
artifact return to the owner. Do not merge or open the next slice on inferred green.

### Slice 0 — freeze contracts and write RED acceptance

1. Add typed manifest/report contract tests, canonical example, generated JSON Schema expectation,
   vendored OASIS schema/provenance, location fixtures, and every RED acceptance named in §5.
2. Add a concise contract document under `docs/ci-contracts.md` containing the manifest schema, outcomes,
   numeric exit mapping, safe-field allowlist, scan coverage/limits, and F12/F18 refusal behavior.
3. Run the new tests against baseline and record fail-before evidence: command-not-found/missing schema/
   missing hook/template failures must correspond to the intended feature, not missing dependencies.
4. Self-check that no acceptance criterion was weakened to accommodate current code; targeted verify the
   current validate/report/scan suites stay green; adversarial review focuses on contract ambiguity,
   false clean states, and leakable fields; remediate the plan/tests before implementation.

### Slice 1 — safe result boundary, locations, and pure report projections

1. Implement `contracts.py` and fixed safe message/reason registries using existing exit constants.
2. Implement the compose-only source index without changing the bytes/value graph sent to the engine.
3. Implement deterministic JSON, OASIS SARIF, and Markdown projections from `SafeCiReport` only.
4. Make official-schema, zero-results, exact-location, ambiguity, deterministic-order, and factory-negative
   tests green. Run the leak sentry at unit boundary now.
5. Self-check value reachability (emitters cannot import manifest literals/raw messages); targeted unit +
   OASIS-schema verification; adversarial review with malicious YAML/path/Unicode/region cases; remediate.

### Slice 2 — strict manifest loader, adapters, orchestration, and CLI

1. Add direct Pydantic dependency, strict loader, path containment, generated schema, and version refusal.
2. Extract typed computation seams beneath existing validation, scan diff, and evidence verify while
   pinning their current public output/exit behavior.
3. Implement adapters and runner aggregation, including explicit unavailable F12 behavior.
4. Add `decoy ci check`, output file/stdout atomicity, format selection, quiet/verbose behavior, root
   registration/help, and generated CLI reference. Refuse overwriting an existing report unless the
   repository's normal `--output` convention explicitly permits it; make the chosen behavior documented
   and tested before code.
5. Make real clean/location/exit/partial/refused tests green. Self-check no child check was reimplemented;
   targeted validation/scan/report/CI e2e; adversarial review child failure/precedence/output-write
   atomicity; remediate.

### Slice 3 — bounded staged scan and offline pre-commit

1. Implement Git-root/path/blob plumbing with no shell, exact index blobs, hard caps, timeouts, and no raw
   child output in diagnostics.
2. Add staged adapter and CLI behavior; add `.pre-commit-hooks.yaml` with the config-only/offline entry,
   `pass_filenames: false`, `always_run: true`, and `stages: [pre-commit]`.
3. Make index-vs-worktree, weird-path, binary, limit, partial, canary, and real offline pre-commit
   acceptance green.
4. Self-check subprocess argv/env/timeout and that no worktree open occurs; targeted staged/pre-commit/
   sentry suites; adversarial review filename/revision injection, symlink/submodule/unmerged/race/resource
   cases; remediate.

### Slice 4 — official CI templates, integration docs, and distribution check

1. Add `integrations/github-actions/decoy-ci.yml`: least `contents: read`; pre-provisioned version check;
   run `decoy ci check .decoy-ci.yaml --format sarif --output decoy.sarif`; explicit optional customer
   upload step using the official CodeQL action with pinned immutable revision and
   `security-events: write`. Explain fork/private-repo permission limits. No upload in Decoy code.
2. Add `integrations/gitlab/decoy-ci.yml`: hidden/reusable job plus documented `include:project` immutable
   ref and local include examples; pre-provisioned version check; same CLI contract; SARIF retained only
   through customer-configured artifacts. Do not claim GitLab converts SARIF to annotations unless that
   exact report feature is configured and verified.
3. Add template contract tests and local extracted-command e2e. Validate GitHub YAML with `actionlint` at
   an attributable pinned version; validate GitLab YAML with a local schema/linter. An optional live
   customer CI-lint probe is supplementary, not the only gate and never runs with secrets.
4. Build wheel/sdist and verify Python modules/schema resources are present; root hook and integration
   templates are source-distribution assets as documented. Run fresh-install smoke with a pre-provisioned
   engine stamp matching `pyproject.toml`.
5. Self-check permissions/action pins/includes/no hidden network; targeted template/install tests;
   adversarial supply-chain review; remediate.

### Slice 5 — full verification and durable documentation

1. Run the complete evidence plan below. Inspect all output, not just summaries.
2. Update `README.md`, `CHANGELOG.md` `[Unreleased]`, `docs/cli-reference.md`, `docs/ci-contracts.md`,
   `docs/schemas/decoy-ci-v1.schema.json`, hook/template usage, exit-code docs, SARIF field policy, scan
   limitations/false positives, offline behavior, and external-upload boundary.
3. Confirm generated schema/reference are byte-current and no source string advertises unsupported F12,
   includes, packaged actions, policy checks, or annotations without upload.
4. Self-check exact diff; full verification; independent Codex code review; remediate/reverify; independent
   Opus-4.8 Dennis code review; remediate/reverify; exact-artifact owner gate.

## 8. Verification and evidence plan

Record exact commit SHA, engine stamp, commands, results, skips, and limitations.

Targeted checks:

```text
pytest -q tests/unit/test_ci_manifest.py tests/unit/test_ci_locations.py tests/unit/test_ci_reporting.py
pytest -q tests/e2e/test_ci_sarif.py tests/e2e/test_ci_exit_codes.py tests/e2e/test_ci_staged_scan.py tests/e2e/test_ci_precommit.py
pytest -q tests/sentry/test_ci_output_isolation.py
pytest -q tests/e2e/test_validate_gate.py tests/e2e/test_validate_sp16.py tests/e2e/test_storm_diff.py tests/e2e/test_report_verify_command.py tests/e2e/test_report_command.py
pytest -q tests/unit/test_ci_templates.py tests/unit/test_cli_surface.py tests/unit/test_surface_docs_consistency.py
```

Project checks:

```text
ruff check src tests
ruff format --check src/decoy/ci src/decoy/cli/ci.py src/decoy/cli/validate.py src/decoy/cli/scan.py src/decoy/cli/report.py src/decoy/__main__.py tests/unit/test_ci_*.py tests/e2e/test_ci_*.py tests/sentry/test_ci_output_isolation.py
pytest -q tests/unit tests/sentry tests/e2e --tb=short
python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md
python -m build --wheel --sdist
```

Run the CLI acceptance cells in a fresh environment using pinned engine `v0.15.1` /
`fd51be10673225d81a8c000d460b0172112b26ac`; do not substitute engine `main`. Inspect the
built artifact and run `decoy ci check` from the installed wheel, not only editable source.

Test strength before merge:

- Use branch coverage on `src/decoy/ci/**` and `src/decoy/cli/ci.py`; record the measured baseline and
  uncovered branches. Do not choose a cosmetic percentage target.
- Run mutation testing on the safe factory, exit precedence, path containment, source resolver, staged
  limit checks, and SARIF region mapping. Every surviving mutant in a leak, containment, fail-closed,
  staged-vs-worktree, or exit-precedence branch is implementation work, not an accepted score.
- Existing command regressions are consumer contract evidence; template static tests do not prove a live
  GitHub/GitLab service accepted/uploaded the file. Record that platform integration gap unless a safe
  owner-controlled test repository runs the exact template.

Required evidence bundle for review:

- fail-before output from Slice 0;
- official-schema validation output and schema SHA-256/provenance;
- exact-location oracle results and zero-result clean SARIF;
- exit-matrix table with observed integer/outcome/reason;
- offline pre-commit transcript with canaries redacted by the test (not manually);
- leak sentry results for all formats/streams;
- template lint and extracted-command results;
- full ruff/pytest/build/fresh-install results;
- branch coverage and mutation report for changed high-risk units; and
- self-check diff plus known limitations (F12 runner, F16 policy, F18 includes, no live upload test).

## 9. Documentation plan

- `README.md`: one CI quickstart, supported systems, manifest location, offline hook requirement, and link
  to the full contract.
- Generated `docs/cli-reference.md`: `decoy ci check`, formats, output behavior, hook mode, and exact exits.
- `docs/ci-contracts.md`: authoritative human reference for manifest v1, JSON report v1, SARIF mapping,
  safe fields, reason/exit mapping, default check set, location behavior, includes refusal, scan limits/
  false positives, pre-commit, GitHub upload permissions, GitLab include pinning, and platform export
  compatibility.
- `docs/schemas/decoy-ci-v1.schema.json`: generated machine contract with `$id`, descriptions, and no
  permissive additional properties.
- `examples/decoy-ci.yaml`: runnable local example with synthetic/non-sensitive identifiers only.
- `CHANGELOG.md`: additive command/schema/template/hook contract and explicit deferred packaged action,
  F12 execution, F18 include, and Platform export.
- Source templates contain short comments that state “invoker only,” runtime provisioning/pin ownership,
  upload boundary, and where to configure the manifest. No copied prose tables that can drift from the
  contract document.

At DOCUMENT close, update the commercial roadmap/shipped log through the owning workflow only after merge;
do not edit an inaccessible companion repo from the remote worker. This CLI repo is not listed as a
graphify-managed repo in the global close rule, so no graph refresh is claimed unless the owner has added
it by then. Send the section-complete plain-language Slack only after an actual merged slice, not after
this plan.

## 10. Failure modes and sentries

| Defect class | Choke point | Sentry / response |
|---|---|---|
| Sample/secret/raw exception leaks into any report or annotation | `SafeFinding.create`; emitters accept only `SafeCiReport` | Parameterized canary scan across JSON/SARIF/Markdown/stdout/stderr/verbose and assertions forbidding snippets/context/raw exception. Build fails. |
| Wrong file/line, especially future include flattening | `YamlSourceIndex.resolve(origin,path)` | Exact fixture line/column oracle, semantic/numeric path parity, ambiguity tests, and future F18 origin-file contract. Omit region rather than guess. |
| Wrapper drifts from engine checks | Typed adapters beneath existing commands | Direct-command vs adapter parity tests on real fixtures; one call-count/typed-result seam; template sentry forbids check commands other than `decoy ci check`. |
| Clean result after skipped/limited staged content | `StagedScanner` coverage ledger + runner aggregation | File/byte/time/binary/unmerged/submodule tests require partial/refused non-zero; no “clean subset” path. |
| Worktree content scanned instead of index | blob-ID reader | Opposed index/worktree canary tests in a real Git repo. |
| Manifest/schema drift or permissive unknown fields | Pydantic model -> generated schema | Byte regeneration sentry plus negative unknown/version/duplicate/tag tests. |
| SARIF hand-rolled incorrectly | pure projector | Official OASIS schema validation on clean and finding logs; GitHub-supported field subset assertions. |
| Exit changes break automation | one aggregator using imported constants | Full real exit matrix and unchanged direct-command regression suite. |
| CI template gains hidden network/write authority | template files and permissions | Static permission/action/include pin test plus adversarial supply-chain review. |

## 11. Gate chain and remote-worker handoff

Plan gates for this document, in order:

1. Gemini reviews the exact plan file against the F43 MASTER and baseline anchors.
2. Opus-4.8 Dennis performs the independent tech-lead/adversarial plan review.
3. Owner approves scope decisions, especially literal-only scanning, unsupported non-empty F12 suites,
   no v1 includes, template runtime provisioning, and exit precedence.

Only then hand this file to the remote `claude.ai/code` worker. The worker sees only the remote `decoy`
repository, so this plan is the complete brief. It must verify HEAD/merge-base before work, install the
pinned private engine tag/stamp, preserve all RED acceptance, implement only the slices above, push a
branch, and open a PR. It must not merge, upload SARIF, comment externally, update Platform, or silently
skip tests if private-engine access is unavailable; inaccessible dependencies are reported BLOCKED with
the exact unrun checks.

Code gates are deliberately **Codex first, then Opus-4.8 Dennis, then owner** on the exact finished commit:

1. Worker self-check and full evidence.
2. Codex independent code review; every finding remediated and reverified.
3. Opus-4.8 Dennis tech-lead/adversarial code review; every finding remediated and reverified.
4. Owner consumes exact-artifact evidence and decides merge. Any code change after a verdict invalidates
   later evidence and re-enters self-check/verification/review.

The pinned guarantee and non-goals bound review. A request to add F12's runner, F16 policy evaluation,
F18 composition, a Marketplace action, automatic upload/commenting, regex/entropy scanning, or another CI
vendor is a new reviewed plan, not remediation under F43 v1.

## 12. Gemini plan-gate (2026-10-29): GO-WITH-FIXES, fixes folded

Gemini (google/gemini-2.5-pro) reviewed the plan against the MASTER contract. Verdict GO-WITH-FIXES:
1 BLOCKER, 2 HIGH, 1 MEDIUM, 1 LOW. All folded (Opus, with provenance):

- **BLOCKER (SARIF `rules[]` population), §4.2:** the plan named the `rules[]` registry but did not
  require every `ruleId` to have a matching `tool.driver.rules[]` object. Folded: each `ruleId` MUST
  have a `rules[]` entry carrying `id` + `shortDescription.text` (from `safe_message_id`); a result with
  an undefined rule is a build-failing projection error. SARIF 2.1.0 requires it.
- **HIGH (stable fingerprints), §4.2:** no `partialFingerprints`, so alerts churn as new/fixed on line
  moves. Folded: `SafeFinding` carries value-free `fingerprint_inputs = {rule_id, normalized
  repo-relative path, logical config path}`; the SARIF projector emits a versioned `primary/v1`
  `partialFingerprints`.
- **HIGH (location-free acceptance test), §5 item 2:** only the positive-location case was tested.
  Folded: added a location-free case asserting a real no-logical-path finding yields schema-valid SARIF
  with `locations` omitted or `[]` (never a `locations` entry missing `physicalLocation`), plus valid
  `partialFingerprints` and a matching `rules[]` entry.
- **MEDIUM (debuggability escape hatch), §4.2:** the strict value-free boundary left no diagnosis path,
  tempting future boundary-weakening. Folded: a hidden `--unsafe-debug-log PATH` writing a separate
  unstructured file, never stdout/stderr, never a CI artifact, with a loud unsafe warning.
- **LOW (pre-commit mode-override notice):** forcing `validation.mode=config` in pre-commit was silent.
  Folded: when a context forces a narrowing override, emit a human-readable `note` in the report and a
  `stderr` message ("Running in pre-commit mode; validation narrowed from 'full' to 'config'...") when
  not writing a machine-readable format to stdout.

## 13. Opus-4.8 Dennis repo-grounded plan gate (2026-10-29): GO-WITH-FIXES, fixes folded

Dennis cold-read the plan and byte-verified every cited CLI anchor against the repo at baseline `574aa1e`. **Grounding is CLEAN: no phantom prereqs** (a marked improvement). Verdict GO-WITH-FIXES: 0 BLOCKER, 0 HIGH, 3 MEDIUM, 4 LOW. All folded (Opus, with provenance); M1 and M2 close gaps the earlier Gemini folds opened.

- **MEDIUM M1 (debug-hatch raw sink is unguarded):** the `--unsafe-debug-log PATH` hatch (§4.2) is a sanctioned raw/secret/sample sink, but no test keeps it off the safe path. Folded: acceptance must assert (a) the flag is hidden from `--help` and the CLI reference, (b) no shipped GitHub/GitLab template or pre-commit hook ever passes it, (c) no run creates the file unless the flag is explicitly given, (d) its contents never reach stdout/stderr. Add these to A9 (templates) and A10 (leak sentry).
- **MEDIUM M2 (pre-commit `note` had no home in the contract):** the Gemini LOW fold promised a report `note` + stderr message, but `SafeCiReport` had no field to carry it. Folded: added a value-free `notes[] = {note_id}` field to the `SafeCiReport` schema in §4.2 (authored text IDs only, no scalars). The pre-commit mode-narrowing surfaces as `note_id = ci.precommit_mode_narrowed` in `notes[]` AND a one-line stderr message ("Running in pre-commit mode; validation narrowed from 'full' to 'config'...") emitted only when a machine-readable format is NOT being written to stdout. Add one acceptance assertion covering both surfaces.
- **MEDIUM M3 (staged `--name-status -z` rename/copy desync):** `R`/`C` entries carry TWO NUL-separated path fields (`R100\0old\0new\0`) while `A/M/D` carry one; a naive "status then next field" parse desyncs the whole stream after the first rename and scans the wrong path. Folded: §4.5 step 2 must specify the R/C two-field parse explicitly, and A7 must stage a real rename+modify mixed with A/M entries and assert the renamed POST-image blob (by object ID) is the one scanned with the parse staying aligned.
- **LOW L1 (SARIF rationale overstated), §4.2:** reword "SARIF 2.1.0 requires the rule to be defined in the driver" to "SARIF best practice and GitHub code-scanning expect the rule defined in the driver" (the association is RECOMMENDED, not strictly required). The self-imposed strictness stays; only the justification was wrong.
- **LOW L2 (loose anchor range), §2:** `tests/sentry/test_report_raw_value_isolation.py` is 289 lines, not `:1-180`; trim or drop the range.
- **LOW L3 (status label partial vs refused), §4.3:** state that a per-check refusal ALONGSIDE any completed check reports `partial`; `refused` is reserved for the all-refused case. (Exit code is already unambiguous: `EXIT_USAGE` outranks findings.)
- **LOW L4 (engine anchors verified structurally only), informational:** the engine error classes `PlanCompileError(code, path|None, message)` / `PipelineValidationError(message, path|None, code|None)` and the `tables.customers.columns.customer_id` example match at the nearest local checkout (v0.14.1), but the exact line ranges at stamp `fd51be10`/v0.15.1 were not byte-verifiable on this box. The remote worker MUST confirm the exact ranges and that `unknown_provider` carries a column-level `path` at v0.15.1 before relying on A2's positive-location oracle; the location-free fallback covers the `path=None` case regardless.

Plan is owner-ready. The build gate on the finished code stays Codex first -> Opus-4.8 Dennis -> owner.
