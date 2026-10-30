# CI integration contracts (F43)

`decoy ci check` is a thin, local, network-free wrapper over Decoy's existing
validation, saved-scan drift, and evidence-verification contracts, plus one bounded
staged-file literal scan. It never uploads, comments, or calls out. Everything it
reports passes through a single value-free boundary (`SafeFinding` / `SafeCiReport`).

```text
decoy ci check [MANIFEST] [--format json|sarif|markdown] [--output PATH|-]
               [--context ci|pre-commit] [-q|-v]
```

`MANIFEST` defaults to the literal `.decoy-ci.yaml` in the current directory. There is no
manifest search. Relative references in the manifest resolve from the manifest's directory
and must stay inside the Git work tree (or the manifest directory outside a work tree).

## Manifest: `decoy-ci/v1`

YAML or JSON mapping. Strict: unknown fields, YAML anchors/aliases/merge keys, custom tags,
duplicate keys, and multiple documents are rejected. No commands, includes, interpolation,
or expressions exist. The committed machine contract is
[`schemas/decoy-ci-v1.schema.json`](schemas/decoy-ci-v1.schema.json) (generated from the
typed model and drift-tested byte for byte); a runnable example is
[`examples/decoy-ci.yaml`](../examples/decoy-ci.yaml).

| Field | Rule |
|---|---|
| `schema_version` | required, exactly `decoy-ci/v1` |
| `pipelines` | 1-32 `{id, path}`; repo-relative regular files; no absolute, `..`, NUL, symlink escape, or duplicate resolved paths |
| `checks.validation` | `{enabled=true, mode=full\|config, pipelines=<all>, fail_on_warning=true}` |
| `checks.drift` | 0-32 `{id, baseline, current, blocking=true}` saved STORM scan pairs |
| `checks.evidence` | 0-32 `{id, manifest}` `cli-local-1` evidence manifests |
| `checks.regression_suites` | 0-16 `{id, suite}`; **any entry is refused** until a public F12 runner exists (`ci.regression_runner_unavailable`) |
| `staged_scan` | `{enabled=false, patterns[], limits}`; enabled needs 1-32 patterns |
| pattern | `{id, literal, paths[1+], exclude_paths[]}`; literal is 4-128 UTF-8 bytes, no control characters; globs are repo-root relative using `*`, `**`, `?` only |

IDs match `^[a-z][a-z0-9_.-]{0,63}$` and are unique (pipeline ids; check ids across
drift/evidence/regression; pattern ids). IDs are emitted in reports (`staged.<pattern id>`,
`validation.<pipeline id>`), so never put a sensitive value in an ID.

Roots: the containment root is the Git work tree that contains the manifest, or the
manifest's own directory when it is not in a work tree (a staged scan then cannot read an
index and reports `ci.git_failure`). Reported URIs are relative to that root.

Default when `checks` is omitted: full validation of every declared pipeline with warnings
blocking. Drift, evidence, regression, and staged scans must be requested explicitly.

## Outcomes and exit integers

The process exit integer is always one of the existing public constants
(`decoy.cli.exit_codes`); F43 adds none and does not reinterpret direct commands.

| Exit | Constant | F43 meaning |
|---:|---|---|
| 0 | `EXIT_OK` | all selected checks clean, or a genuine no-op |
| 1 | `EXIT_USAGE` | invalid manifest/input, refused dependency, bounded-scan refusal, validation errors (same as `decoy validate`) |
| 2 | `EXIT_WARNINGS` | validation warnings with `fail_on_warning: true` |
| 3 | `EXIT_RUNTIME` | CLI/engine/Git execution failed |
| 4 | `EXIT_FINDINGS` | evidence mismatch, blocking drift, staged-pattern hit |
| 5 | `EXIT_CAPACITY` | preflight capacity refusal |

Precedence across checks: **5 > 3 > 1 > 4 > 2 > 0**. Report `status`:
`ok` | `noop` (only genuinely inapplicable work, e.g. nothing staged) | `findings` |
`partial` (a selected check did not complete, alongside any completed check, or the staged
scan could not cover every selected blob) | `refused` (no selected check could run). A
`partial` or `refused` report never exits 0. A non-blocking drift pair reports warnings and
exits 0. The JSON report and exit code are authoritative for completeness; SARIF carries
findings only.

## Output

`--output PATH` writes the single report atomically (temp file + rename) and leaves stdout
empty; `-` (the default) writes it to stdout. Like the other `--output` flags, an explicit
path is the operator's deliberate choice and replaces an existing regular file. The path
must be inside the root, its directory must already exist, and it may not be a symlink.
When the report goes to a file, one value-free summary line is printed on stderr.
Evidence manifests record paths as `decoy run` saw them; they are resolved the way
`decoy report verify` resolves them (relative to the working directory), so run the check
from the repository root. A recorded path that exists but is not a regular file is treated
as missing and never read. Full validation runs the engine's compile layer, which (as for
`decoy validate`) writes the engine log to `logs/decoy_engine.log` under the working
directory; ignore that path in version control.

## Report: `decoy-ci-report/v1` (`--format json`)

One compact object, deterministic, no timestamps:

```json
{"schema_version":"decoy-ci-report/v1","status":"findings","exit_code":1,
 "checks":[{"id":"validation.primary","kind":"validation","status":"findings","reason_code":null,"finding_count":1}],
 "notes":[{"note_id":"ci.precommit_mode_narrowed"}],
 "findings":[{"rule_id":"validate.unknown_provider","level":"error","safe_message_id":"ci.validation_failed",
   "check_id":"validation.primary","location":{"uri":"pipeline.yaml","start_line":14,"start_column":9,"end_line":14,"end_column":17},
   "fingerprint":"<sha256>","occurrences":1}]}
```

Safe-field allowlist (nothing else is ever emitted): rule/check/message/note/reason ids from
fixed registries, severity, a repository-relative URI, one-based region numbers, a SHA-256
fingerprint of `(rule_id, repo-relative path, logical config path)`, and counts. No message
text from the engine, no exceptions, no matched values, no literals, no snippets, no
absolute paths. Reports contain only fixed authored text (`safe_message_id`).

Check kinds: `validation`, `drift`, `evidence`, `regression`, `staged_scan`, `manifest`.
Check statuses: `ok`, `noop`, `findings`, `partial`, `refused`, `failed`.

Rule id namespaces: `validate.<code>` (engine/CLI validation code), `drift.*`
(`pii_bucket_increased`, `new_high_pii_field`, `new_quasi_identifier_group`), `evidence.*`
(`manifest_hash_mismatch`, `pipeline_missing`, `pipeline_fingerprint_changed`,
`input_missing`, `input_fingerprint_changed`, `output_missing`, `output_fingerprint_changed`),
`staged.<pattern id>`.

Reason codes: `ci.manifest_unreadable`, `ci.manifest_invalid`, `ci.manifest_version_unsupported`,
`ci.manifest_path_rejected`, `ci.input_missing`, `ci.evidence_unreadable`, `ci.drift_unreadable`,
`ci.regression_runner_unavailable`, `ci.no_staged_files`, `ci.staged_scan_limit`,
`ci.staged_unsupported_entry`, `ci.staged_unmerged`, `ci.git_failure`,
`ci.check_runtime_failure`, `ci.capacity_refused`, `ci.precommit_not_applicable`.

Note ids: `ci.precommit_mode_narrowed`.

## SARIF 2.1.0 (`--format sarif`)

Validated offline in CI against the OASIS SARIF 2.1.0 schema (Draft-04), vendored under
`tests/fixtures/schemas/`. One run; `tool.driver.name = "Decoy"`; `columnKind` is
`unicodeCodePoints` (YAML marks are code points). Every `ruleId` has a `tool.driver.rules[]`
entry (`id`, `shortDescription` from the fixed message). Every result has
`partialFingerprints["primary/v1"]` (value-free), so alerts survive line moves. A `region`
is emitted only for an exact mark: a validation finding whose logical path resolves to a key
in the single parsed YAML file; a proven parent yields a file-level location; wildcard,
ambiguous, duplicate, pseudo, or unknown paths yield no location. No `snippet`,
`contextRegion`, `invocations`, or attachments. A clean run emits `results: []`.

## Pre-commit and CI templates

`.pre-commit-hooks.yaml` ships hook `decoy-ci-check` (`language: unsupported`,
`pass_filenames: false`, `always_run: true`, `stages: [pre-commit]`, requires
pre-commit >= 4.4.0). It requires a preinstalled, pinned `decoy` on `PATH`; it installs
nothing and uses no network. It runs `--context pre-commit`: validation narrows to the
existing `validate config` semantics (no source or preflight reads) and the staged scan
runs; drift/evidence/regression are reported `noop` (`ci.precommit_not_applicable`). The
narrowing is announced as note `ci.precommit_mode_narrowed` and one stderr line, the latter
only when a machine-readable format is not being written to stdout.

`integrations/github-actions/decoy-ci.yml` and `integrations/gitlab/decoy-ci.yml` are
invoker-only templates: a runtime version check, then
`decoy ci check .decoy-ci.yaml --format sarif --output decoy.sarif`. Decoy never uploads. The
GitHub template's optional `upload-sarif` job is an explicit customer opt-in with
`security-events: write`; fork and private-repository token limits are the customer's to
configure. The templates never pass the unsafe debug option.

## Staged scan

Reads the Git **index** (stage-0 blobs by object id through `git cat-file`), never the
worktree. Changed paths come from `git diff --cached --name-status -z -M` (renames/copies
carry two path fields; the post-image path is scanned). Added, copied, modified, renamed, and
type-changed entries are scanned; deletions are skipped; an unmerged entry anywhere refuses
the whole scan (`ci.staged_unmerged`), and an unknown status is refused rather than ignored. Git runs with an argv
array, `shell=False`, repository root as cwd, `--no-ext-diff`, no textconv, a sanitized
environment, and a shared time budget. Symlinks, submodules, unmerged entries, and missing
stage-0 blobs are refused. Matching is exact byte search of customer literals over the whole
staged post-image: no regex, entropy, case folding, or built-in detector, so it is not PII
classification, secret discovery, or evidence of absence. Hits aggregate per
`(pattern id, path)` with a count; binary or non-UTF-8 blobs yield a file-level finding.

Hard limits are maxima (a manifest may lower them under `staged_scan.limits`, never raise):

| Limit | Maximum |
|---|---:|
| `max_files` (in-scope staged files) | 200 |
| `max_blob_bytes` | 1 MiB |
| `max_total_bytes` | 5 MiB |
| patterns | 32 |
| literal | 128 bytes |
| `max_finding_groups` | 100 |
| `max_git_seconds` (all Git calls) | 10 |

Exceeding a limit, a timeout, or an unreadable selected blob yields a `partial` report
(`ci.staged_scan_limit` -> exit 1, `ci.git_failure` -> exit 3), never a clean subset.
False positives are fixed by narrowing the literal or its path scope in reviewed config; there
is deliberately no value allowlist (it would be a second sensitive-value store).

## Debugging

`--unsafe-debug-log PATH` is a hidden, deliberate raw sink for local diagnosis only. It
writes a separate unstructured file that may contain secrets, sample values, absolute paths,
and raw exception text. It is never written to stdout/stderr, never created unless given,
never passed by any shipped template or hook, and its contents must not be parsed or
uploaded.

## Known limits

No F12 regression runner (non-empty `regression_suites` is refused), no F16 policy-ID
finding (projected automatically when the engine emits it), no F18 includes (`include` is
rejected; locations resolve only within the single parsed file), no packaged Marketplace
action, no live GitHub/GitLab acceptance test of the templates.
