# F43 verification evidence (build branch `feat/f43-ci-integration`)

Baseline: `main` @ `574aa1e9ec2b95f9ba8af5eb8112c1a3c0fcf434` (merge-base re-verified before the PR).
Engine: `decoy-engine==0.15.1`, stamp `fd51be10673225d81a8c000d460b0172112b26ac`
(built from the `v0.15.1` tag; never engine `main`). Python 3.12.3 primary, 3.10.20 spot run.
The Codex -> Opus-4.8 Dennis -> owner code gates run on the pushed commit; nothing here is a
verdict from them.

## 0. Worker-confirm (Dennis L4)

At the pinned engine `fd51be10` the plan's anchors hold exactly: `decoy_engine/plan/_errors.py`
`PlanCompileError` is lines 24-47 (`__init__(code, path|None, message)`),
`decoy_engine/errors.py` `PipelineValidationError` is lines 33-55 (`path|None`, `code|None`), and
`check_unknown_provider` raises `PlanCompileError(code="unknown_provider",
path=f"tables.{table}.columns.{col}.provider")` (`plan/_checks.py:52-95`): a column-level path.
No amendment to the plan was needed. The location-free fallback is tested separately.

## 1. RED first (fail-before)

`docs/ci-evidence/red-baseline-574aa1e.txt`: A1-A10 against the untouched baseline source:
113 failed, 3 collection errors (`No module named decoy.ci`), 1 pass (the offline-guard negative
control). Every failure is "feature absent" (`No such command 'ci'`, missing module/hook/templates),
none a missing dependency. A11 (existing-contract pins) is green before and after.

## 2. Acceptance results (final tree)

| Check | Result |
|---|---|
| F43 suites (A1-A11 + extras), Python 3.12 | 324 passed (coverage run) |
| Same suites + CLI-surface docs tests, Python 3.10.20 | 335 passed, 1 failed: `test_cli_surface` caught that `docs/cli-reference.md` was stale after a later epilog edit; regenerated, then green on 3.10 and 3.12 |
| Full repo suite `pytest tests` (3.12) | 1646 passed, 5 skipped (all 5 pre-existing), 29 failed |
| The 29 failures | the identical 29 on untouched baseline `574aa1e` (`cannot import name 'resolve_substrate' from 'decoy_engine.execution'`: the pinned engine lacks a symbol the baseline CLI calls). `diff` of the sorted failure lists is empty. Not caused by or related to F43 |
| `ruff check src tests` | clean |
| `ruff format --check` on every new file + `evidence.py` | clean (legacy `validate.py`/`scan.py`/`__main__.py` were not format-clean at baseline and are not reformatted) |
| `docs/cli-reference.md` | regenerated; `test_cli_surface` green; hidden debug flag absent |
| Branch coverage, `src/decoy/ci/**` + `src/decoy/cli/ci.py` (subprocess-aware) | 93% (1224 stmts, 392 branches); runner 100%; uncovered lines are OS-error branches (flush/replace failure), Git output-shape defenses, and unreachable-by-construction guards |

### Official SARIF schema
Vendored `tests/fixtures/schemas/sarif-schema-2.1.0.json`, SHA-256
`c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e`, Draft-04 via `jsonschema`.
Provenance caveat (also in the fixtures README): `docs.oasis-open.org` was unreachable from the
build environment; the file came from the OASIS SARIF TC repository
(`oasis-tcs/sarif-spec`, declares the Errata 01 `id`). A maintainer should confirm the hash
against the published artifact.

### Exit matrix (observed, real CLI process, from `matrix.py`)
| Scenario | exit | report status | reason codes | findings |
|---|---:|---|---|---:|
| clean validation | 0 | ok | - | 0 |
| staged-only, nothing staged | 0 | noop | ci.no_staged_files | 0 |
| staged hit | 4 | findings | - | 1 |
| evidence mismatch | 4 | findings | - | 1 |
| validation ok then real git failure (corrupt index) | 3 | partial | ci.git_failure | 0 |
| malformed manifest | 1 | refused | ci.manifest_invalid | 0 |
| non-empty F12 selection alone | 1 | refused | ci.regression_runner_unavailable | 0 |
| F12 selection + validation | 1 | partial | ci.regression_runner_unavailable | 0 |
| over-limit staged scan (201 files) | 1 | partial | ci.staged_scan_limit | 0 |
| validation warning + `fail_on_warning` | 2 | findings | - | 1 |
| validation error | 1 | findings | - | 1 |
| capacity refusal (in-process, estimator patched like the existing `validate` suite) | 5 | refused/partial | ci.capacity_refused | - |

### Exact-location oracle
`tests/e2e/test_ci_sarif.py`: a real pinned-engine `unknown_provider` on a hand-authored fixture
maps to `pipeline.yaml` line 14 column 9; inserting two lines moves it to 16/9 while the
`partialFingerprints["primary/v1"]` is unchanged; no `snippet`. The location-free finding
(`yaml.not_mapping`) and a missing top-level key yield schema-valid SARIF with no `locations` /
no region, a fingerprint, and a matching `rules[]` entry.

### Offline pre-commit (real `pre-commit` 4.7.0, `PIP_NO_INDEX=1`, socket-denying `sitecustomize`)
Transcript of `pre-commit run --verbose` with a staged synthetic identifier (the test asserts the
literal and the value are absent from the output):

```
decoy ci check...........................................................Failed
- hook id: decoy-ci-check
- exit code: 4

# Decoy CI report
**Status:** findings (exit 4)
| validation.primary | validation | ok | - | 0 |
| staged_scan | staged_scan | findings | - | 1 |
## Notes
- Running in pre-commit mode; validation narrowed from 'full' to 'config' ...
### staged.pii.seeded-test-identifier (error)
- fixtures/seed.txt:2:3 (staged_scan)
```

### Leak sentry
`tests/sentry/test_ci_output_isolation.py`: 4 scenarios (clean / finding / refused / partial) x 3
formats x 4 surfaces (stdout, file, verbose stdout, verbose file) = 48 cells + 5 hatch tests, all
green. Six canaries (staged blob, pattern literal, pipeline scalar, engine exception source,
evidence manifest, manifest field) plus the absolute temp root, each checked as full string,
name prefix and hex tail, over stdout, stderr and the written file. Each cell first asserts the
real exit integer and the real report status/shape, so the sentry cannot pass on an empty output.
Positive control: the direct `decoy validate --json` output DOES contain the exception canary.
`tests/e2e/test_ci_unexpected_failures.py` forces exceptions carrying a canary and an absolute
path out of every adapter, the runner, and the manifest loader: stdout/stderr stay clean, no
traceback escapes, and only the explicit `--unsafe-debug-log` file holds the raw text.

### Template lint (static platform syntax; no live GitHub/GitLab run)
- `actionlint` 1.7.12 (`actionlint-py==1.7.12.25`) on `integrations/github-actions/decoy-ci.yml`:
  exit 0; negative control (undefined context + unpinned `uses`) exits 1.
- GitLab CI JSON schema via `check-jsonschema==0.39.0 --builtin-schema vendor.gitlab-ci` on
  `integrations/gitlab/decoy-ci.yml`: ok; negative control exits 1.
- Both are now a pinned `ci-template-lint` job in `.github/workflows/ci.yml`.
- Third-party actions in the GitHub template are pinned to full commit SHAs resolved from the
  public tag refs on 2026-10-29: `actions/checkout` v7.0.1, `actions/upload-artifact` v7.0.2,
  `actions/download-artifact` v8.0.2, `github/codeql-action/upload-sarif` v4.39.1 (annotated tag,
  peeled commit).

### Build and fresh install
`python -m build --wheel --sdist`: the wheel contains `decoy/ci/*` and `decoy/cli/ci.py`; the
sdist contains `.pre-commit-hooks.yaml`, `integrations/`, `docs/schemas/decoy-ci-v1.schema.json`,
`docs/ci-contracts.md`, `examples/decoy-ci.yaml` and no tests. A fresh venv with the pinned engine
plus the NON-editable wheel ran `decoy ci check --format sarif` end to end (exit 1, exact region
`startLine 14 / startColumn 9`), and the new `ci.yml` "smoke 4" step was replayed locally against
the bundled `minimal` template (exit 0, `results: []`).

### Targeted mutation testing (hand-picked mutants, not a mutation-tool score)
47 mutants (plus 2 added after the first round) over the safe factory, exit precedence, path containment, the YAML resolver, staged
limits and git trust flags, the SARIF region mapping, output-path safety and the FIFO guard.
Rounds: 39/47 killed first run; after test hardening the added/changed mutants (fingerprint churn,
`..` inside the root, replace-refs, budget, worktree-instead-of-index) were all killed. Remaining
survivors, each analysed as an equivalent mutant (a second layer enforces the same property):
absolute-URI check (the empty-segment check also rejects it), YAML alias check (an alias needs an
anchor, which is rejected first), non-allowlisted YAML tag check (SafeLoader also rejects those
for this schema), `--no-ext-diff/--no-textconv` on `--name-status` (that mode never invokes diff
drivers, so the flags are belt-and-braces; the execution test has a negative control proving plain
`git diff` does run the configured program).

## 3. Deviations and decisions to review

1. Three small modules beyond the plan's file list: `manifest.py` (strict loader + generated
   schema), `_git.py` (the single Git trust boundary), `debug.py` (the one raw sink).
2. `pre-commit>=4.4.0` joins the dev extra with `jsonschema`: A8 needs the real tool, and 4.4.0 is
   the first release with `language: unsupported`, so the hook declares
   `minimum_pre_commit_version: "4.4.0"`.
3. The staged diff omits `--diff-filter` so `T` (type change) and `U` (unmerged) are visible:
   a file turned from symlink to regular is scanned, an unmerged index anywhere is refused, and an
   unknown status is refused. `-M` is passed so renames are detected regardless of `diff.renames`.
4. `max_files` counts in-scope staged files (those matching a pattern), not every staged path.
5. Validation errors keep `decoy validate`'s exit 1 with report status `findings` (the plan's table
   lists 4 for "findings" but also "existing validation refusal" under 1); a capacity refusal is a
   `refused` check carrying its findings. SARIF carries findings only: completeness lives in the JSON
   report and the exit code.
6. A `refused` check next to a completed one is `partial`; a lone runtime failure is also `partial`
   (it exits 3, which `refused` may not).
7. Pre-commit context runs only config-mode validation and the staged scan; drift/evidence/regression
   are reported `noop` (`ci.precommit_not_applicable`) and the narrowing note covers both.
8. `tests/unit/test_bundled_examples.py` now exempts `examples/decoy-ci.yaml` (not a pipeline).
9. The engine writes `logs/decoy_engine.log` under the working directory during full validation
   (existing behavior of `decoy validate`); documented, not changed.
10. `pydantic>=2,<3` is the only runtime dependency promoted; PyYAML stays a transitive via the engine
    as it already was for `validate.py`.

## 4. Not run / known limits

- No live GitHub Actions or GitLab run of the templates; no SARIF upload (by design).
- Codex / Dennis / owner gates are pending on the pushed commit.
- The vendored SARIF schema is not byte-compared with the OASIS-hosted file (host unreachable).
- Python 3.11 was only compile-checked; 3.10 and 3.12 ran the suites.
- F12 runner, F16 policy-ID findings, F18 includes, a packaged Marketplace action and platform export
  remain deferred as planned.
