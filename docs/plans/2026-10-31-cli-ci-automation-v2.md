# Decoy CLI CI and Automation: V2 Consolidation

**Status:** V2 candidate reference, not committed scope. Promotion of any item into
real scope is a planner decision; nothing here is a build authorization.
**Date:** 2026-10-31
**Scope:** how the `decoy` CLI is used in CI and production automation today, where it
fits and falls short in real-life scenarios, and the consolidated list of V2 candidate
work items that close the gaps.
**Roadmap home:** `decoy-platform/docs/ROADMAP.md` §6 (V2) and
`decoy-platform/docs/backlog/v2-candidate-plan.md` items 13-30.
**Supersedes:** `docs/backlog/cli-first/ci-automation-concepts.md` on platform branch
`claude/exciting-bell-xyyvuh` (items 13-28 are carried here unchanged in numbering).

**Rules consulted:** 00-universal, documentation, scope-discipline, reuse-first,
api-and-compatibility (exit codes are a public contract).

---

## 1. What ships today (F43 and the gate-able surface)

The CLI is a local, network-free step that an orchestrator calls. It reads files,
writes files, and reports through six stable exit codes and `--json` on every command.
Nothing phones home.

| Surface | Command | Automation role |
|---|---|---|
| Pre-run gate | `decoy validate <pipeline> [--fail-on-warning]` | Config schema, plan compile, source and capacity preflight in one report and one exit code |
| CI manifest | `decoy ci check [.decoy-ci.yaml] --format json\|sarif\|markdown` | Validation, saved-scan drift, evidence verification, bounded staged-literal scan; value-free `SafeFinding` boundary; `docs/ci-contracts.md` |
| Pre-commit | hook `decoy-ci-check` (`.pre-commit-hooks.yaml`) | Config-only validation plus the staged scan, offline, pinned `decoy` on `PATH` |
| CI templates | `integrations/github-actions/`, `integrations/gitlab/` | Invoker-only; SARIF upload is an explicit customer opt-in |
| Drift gate | `decoy scan diff <old> <new> --strict` | Exit 1 when a PII bucket rises, a high-PII field appears, or a new quasi-identifier group forms |
| Run | `decoy run <pipeline> --evidence-out --post-validate-enforce --notify --notify-on --chunked --duckdb-source` | The masking or generation step; evidence manifest; warn-only or enforcing post-validation; webhook, Slack, or email on terminal state |
| Post-run gates | `decoy report verify\|integrity\|fidelity\|diff` | Fingerprint drift, residual PII and FK checks, distribution thresholds, manifest comparison |
| Reversible | `decoy tokenize` / `decoy detokenize` | Deterministic surrogates with a local SQLite vault; fails closed on a wrong vault or namespace |
| Fixtures | `decoy subset --dry-run`, `decoy fit`, generate pipelines | FK-aware referential subsets and distribution snapshots for synthetic data |
| Environment | `decoy doctor --json`, `decoy info --json`, `decoy upgrade` | Dependency and version assertions in images and health checks |

Exit codes: 0 ok, 1 usage, 2 warnings with `--fail-on-warning`, 3 runtime, 4 findings,
5 capacity. `decoy ci check` precedence across checks is 5 > 3 > 1 > 4 > 2 > 0.

### The production use model

1. The pipeline YAML lives in git and changes go through the pull-request gate.
   Secrets are references (`env:NAME`, `file:/path`) resolved at run time, never values.
2. An orchestrator (Airflow, Dagster, cron, a Kubernetes CronJob, a CI schedule) runs a
   short script on a host with a pinned `decoy`:

   ```bash
   set -euo pipefail
   decoy validate pipeline.yaml --fail-on-warning --json > validate.json
   decoy run pipeline.yaml \
     --mask-secret env:DECOY_MASK_SECRET \
     --evidence-out build/evidence.json \
     --post-validate-enforce \
     --notify slack:"$SLACK_HOOK" --notify-on failure \
     --json > run.json
   decoy report integrity build/masked.csv --source input/customers.csv --json
   ```

3. Extraction from the source system and loading into the destination happen outside
   the CLI. File sources are dropped into the input path; a DuckDB file is read
   read-only through `--duckdb-source`.
4. Large inputs stream with `--chunked`, which bounds memory for value-keyed strategies
   but drops evidence, post-validation, and inline fidelity. Those run as separate
   report steps afterwards.
5. The evidence manifest is stored next to the output. A downstream consumer runs
   `decoy report verify` before accepting the files.

### Known limits of the shipped surface

- `decoy run` reads and writes local files only. S3, GCS, SFTP, and database targets
  fail closed (F01, F02).
- No run lock, no resume, no scheduler, no local retention cleanup (F23, F27, F28, F26).
- The staged scan is exact-literal only with hard limits (200 files, 1 MiB per blob,
  5 MiB total, 32 patterns). It is not secret detection or PII classification.
- `regression_suites` in the CI manifest is refused until an F12 runner exists.
- Evidence `manifest_hash` is an unkeyed SHA-256, not a signature (F33).
- The shipped GitHub template carries a placeholder `DECOY_EXPECTED_VERSION`.
- Pin drift is live: the CLI pins an engine version that no longer exports a function
  `run.py` imports (roadmap R1-a); the fix rides the STORM engine release.

---

## 2. Real-life scenarios: fit and shortfall

Item numbers refer to section 3. Feature IDs refer to the MASTER specification in
`decoy-platform/docs/plans/Market Expansion Specs/`.

### S1. SaaS QA refresh: nightly copy of production PostgreSQL into staging

- **Fits.** The engine reads a consistent PostgreSQL snapshot; the run writes evidence;
  post-validation can fail the job; integrity catches residual PII and orphan keys;
  failure alerts go to Slack.
- **Falls short.** The CLI run path exposes no PostgreSQL source (files and a DuckDB
  file only) and no database write target, so both edges are wrapper scripts (F01).
  No CLI scheduler, and the platform one is decommissioned (F27). No run lock, so an
  urgent manual refresh can collide with the nightly one (item 24, F23). No resume, so
  a crash at table 18 of 42 restarts from zero (F23). Chunked runs on big tables drop
  evidence and post-validation.

### S2. Fintech monthly data drop to an outsourced analytics vendor over SFTP

- **Fits.** `tokenize` keeps customer IDs joinable across months under a stable secret;
  the evidence manifest travels with the files; `report render` produces an HTML audit
  record; the vendor runs `report verify` before accepting the drop.
- **Falls short.** The run refuses SFTP, S3, and GCS targets, so the transfer is
  external (F02). Evidence is unsigned, so the vendor cannot prove who produced it
  (F33). No accepted-signer consumer gate (item 19). The vault is cleartext at rest
  with no rotation workflow (F09), so secret handling is a manual runbook.

### S3. Healthcare schema-migration gate in CI (the MX-03 flow)

- **Fits.** A scan of the migration test database compared with a committed baseline
  under `--strict` fails the build when a new high-PII column appears; the CI manifest
  runs that drift check beside validation; the HIPAA preset is a starting pipeline.
- **Falls short.** The baseline is hand-produced (item 13). The scan reads files, so
  the migration database is exported first. No compile-time prohibition forbids
  passthrough on a sensitive identifier (F16), so a reviewer can still approve an
  unsafe pipeline. Strict drift blocks only the CI check, not the next run, because the
  publication-block preflight was removed (F15).

### S4. Developer seed data: `make seed` for laptops and pull-request preview environments

- **Fits.** Generate pipelines with fitted snapshots produce realistic fixtures; a fixed
  seed regenerates identical data everywhere; `subset --dry-run` previews a referential
  slice before materializing it.
- **Falls short.** No table selector, so one table cannot be regenerated alone
  (item 22). No fast sample mode, so a preview environment pays for a full run
  (item 18). Chunked mode excludes generate configs. Loading into the preview database
  stays outside the tool (F01).

### S5. Engine upgrade across forty pipelines owned by a platform team

- **Fits.** Running each pipeline before and after the pin change and comparing evidence
  manifests with `report diff` shows which outputs changed; `doctor` and `info` assert
  installed versions.
- **Falls short.** The regression-suite slot is refused because no runner exists (F12).
  No portable lock envelope, so compatibility is proven by rerunning everything (F10).
  No change-based rerun (item 23). The pin problem is live today (R1-a) and the GitHub
  template expected-version is a placeholder.

### S6. Pre-commit in a data-engineering monorepo with dozens of pipelines and fixtures

- **Fits.** The hook runs config-only validation and the staged scan offline, prints no
  values, and stays within bounded limits.
- **Falls short.** Exact-literal matching only; a large fixture commit exceeds the file
  or byte limits and reports `partial`, which never exits 0. No `include` support means
  shared fragments have no source locations (F18). No CI scaffold (item 15), no
  formatter check (item 26), no JUnit or GitHub annotation output (item 25).

### S7. Air-gapped batch node where an application drops files to be masked (the F28 flow)

- **Fits.** Offline and network-free; stable exit codes; signed bundle install path in
  progress (F44).
- **Falls short.** No intake daemon, ledger, or duplicate detection, so the operator
  builds a cron loop with a filesystem lock and done-markers (F28). The CLI is stateless
  by design, so nothing records which requests were served.

### S8. Data-quality gate for a machine-learning team consuming synthetic training data

- **Fits.** `report fidelity` accepts a minimum grade or score and exits with findings;
  its JSON feeds a dashboard.
- **Falls short.** Thresholds live on a command line, not in a versioned reviewed
  contract (F35). No invariant language beyond the fixed set (F36). No first-class test
  verb (item 27), so the gate is a chain of report commands.

### Patterns across the scenarios

**Fits every time:** offline execution, value-free output, stable exit codes, JSON on
every command, deterministic keyed masking, and an evidence manifest.

**Falls short repeatedly, four themes:**

1. **Edges.** Database and object-storage input and output sit outside the run path, so
   every scenario wraps both sides (F01, F02).
2. **Unattended operation.** No lock, no resume, no scheduler, no local cleanup
   (items 24 and 30; F23, F26, F27, F28).
3. **Approval friction.** Baselines, regression goldens, and quality thresholds are
   hand-made files with no review step (items 13 and 27; F12, F15, F35).
4. **Trust.** Evidence is unsigned, so provenance cannot be proven to a third party
   (item 19; F33).

---

## 3. Consolidated V2 candidate items

Items 13-28 are carried from the earlier concepts doc with their numbers kept, because
the V2 candidate plan indexes them by number. Items 29-30 are new from the scenarios.
"Serves" names the scenarios above.

| # | Item | Serves | Builds on / overlaps | Size |
|---|---|---|---|---|
| 13 | `decoy ci baseline`: run the scan, write the drift baseline, show a reviewable diff against the previous one, record approvals as `# REVIEW:` markers | S3 | F15 approved baselines, `api/column_dispositions/` | M |
| 14 | `decoy ci explain <finding-id>`: offline help for one stable reason code; never echoes data | S3, S6 | F29 reason-code registry | S |
| 15 | `decoy ci init`: scaffold `.decoy-ci.yaml` plus the pinned Actions, GitLab, or pre-commit snippet | S6 | `integrations/` templates | S |
| 16 | `decoy diff <old> <new>`: plain-language pipeline comparison; flags masked-to-passthrough as risk-loosening; read-only half of F19 | S3, S5 | F19 semantic diff | M |
| 17 | `decoy ci budget`: fail when a run is materially slower or heavier than the recorded baseline; confidence band, not a point estimate | S5 | F24 estimator, exit 5, benchmark harness | M |
| 18 | `decoy run --check`: compile, preflight, mask a deterministic sample, post-scan it, write no targets | S4, S6 | F04 referential subset | M |
| 19 | Consumer-side passport gate: one-line verify with an accepted-signer policy and a stable exit | S2, S5 | F33 signed evidence; `report verify` | S after F33 |
| 20 | `--baseline-mode ratchet` (accept current findings, fail new ones) and `--watch` for `ci check` | S6 | stable value-free finding IDs | S / S |
| 21 | `decoy init` guided wizard (project mode and per-section edit mode); spec draft lives on CLI branch `claude/exciting-bell-xyyvuh` per the roadmap branch register (not found at the listed path on 2026-10-31) | S4 | item 26 comment-preserving writes | L |
| 22 | Table and pipeline selectors (`--table`, `--pipeline`) on run, validate, scan, subset; rule for FK closure when parents are excluded | S4, S5 | `dbt --select`, `pytest -k` pattern | M |
| 23 | Change-based reruns (`--changed`): skip when pipeline hash, source fingerprints, and version lock match; any doubt reruns and says why | S5 | F10 fingerprints, evidence manifest | M |
| 24 | Run lock: one writer per target, stale-lock rule, holder named in the message | S1, S7 | F22 atomic publication, F23, F25 | S |
| 25 | `ci check --format junit` and `--format github` (workflow-command annotations) through the same `SafeFinding` boundary | S6 | F43 | S |
| 26 | `decoy fmt` and `fmt --check`: canonical YAML layout, comment-preserving | S6 | item 21 wizard splice | M |
| 27 | `decoy test`: first-class verb for the F35 quality contract and F36 invariants over a source and output pair; JSON, JUnit, SARIF; hosts F12 suites when a runner exists | S8, S5 | F35, F36, F12; wraps or replaces `report integrity` and `fidelity` | L |
| 28 | `init` writes a `# yaml-language-server: $schema=` header from `decoy schema` for editor completion | S4 | `decoy schema` version match | XS |
| 29 | `--notify` and `--notify-on` on `scan diff` and the `report` gates, not only `run`; same compact value-free payload and env-only secrets | S3, S8 | `run --notify` dispatcher (notifications backlog N3) | S |
| 30 | Machine-readable run event stream (`--events PATH`, JSON lines: phase, table, rows, bytes, rate, last checkpoint) for orchestrators; the CLI half of the MX-04 "CLI experience" | S1, S7 | F29 progress, F23 checkpoints | M |

Items that map directly onto roadmap features and are not re-listed: CLI resume and
checkpoint store (F23), local cleanup command (F26), database write target (F01),
cloud and SFTP targets on `run` (F02), signed evidence and offline verify (F33), local
execution node (F28), governed schedules (F27), compile-time prohibitions (F16),
regression manifest and runner (F12), version-lock envelope (F10), vault rotation (F09).

---

## 4. Suggested order if any are pulled

1. Item 13 baseline helper. Removes the largest adoption friction and needs no engine
   work.
2. Item 24 run lock, then item 25 output formats, then item 28 schema header. All small
   and unblock unattended and CI use immediately.
3. Item 16 pipeline diff, read-only half, coordinated with F19.
4. Item 22 selectors, then item 23 `--changed`.
5. Item 18 `run --check`, then item 17 budget. Both depend on sample and measurement
   work.
6. Item 29 notify on gates and item 30 event stream, in step with F29.
7. Item 27 `decoy test` once F35 and F36 contracts settle; item 19 once F33 lands.
8. Items 14, 15, 20, 21, 26 as follow-ups.

---

## 5. Constraints that apply to every item

- Stay offline and value-free: no network, no matched value in any output. The
  `SafeFinding` boundary in F43 and the F31 safe-output contract apply.
- Reuse the six public exit codes; add none (F43 rule). Exit codes are public UX; ask
  before changing any command contract.
- Library code does not know its callers: data semantics live in the engine, the CLI
  stays a thin Typer wrapper. Items that need engine changes (18, 23, 27, 30) open an
  engine plan first.
- Pre-GA = hard delete: no compatibility shims if the manifest or report schemas
  change.
- Modules aim for 600 LOC with a hard max of 700.

---

## 6. Sources

- `docs/ci-contracts.md` (this repo): the shipped `decoy-ci/v1` contract.
- `docs/cli-reference.md` (this repo): command and flag reference.
- `decoy-platform/docs/backlog/cli-first/ci-automation-concepts.md` on branch
  `claude/exciting-bell-xyyvuh` (items 13-28, superseded by this document).
- `decoy-platform/docs/backlog/cli-first/cli-first-capability-guide.md`: target-state
  CLI tracks (validation parity, local evidence mode).
- `decoy-platform/docs/backlog/notifications-job-outcome-alerts.md`: origin of
  `run --notify` (slice N3).
- `decoy-platform/docs/plans/Market Expansion Specs/MASTER - Decoy Feature
  Specification.md`: F01, F02, F10, F12, F15, F16, F19, F23, F26, F27, F28, F29, F33,
  F35, F36, F43, F44.
- `MX-03 Continuous Discovery and Reusable Policy.md` and `MX-04 Reliable Production
  Operation.md`: the CI drift-block and resume example flows.
- `decoy-platform/docs/ROADMAP.md`: F43 row, §6 V2 list, Phase 0 R1-a pin drift, and the
  unfiled-branch register.
