# Parity C4: local run records, `--watch`, progress stream, and a small `--jobs N` queue

Status: plan, PRE-RELEASE (2026-10-24). Part of the parity program; source: parity audit §6 (the
orchestration and monitoring gap) and §1 item 3. Reopens redesign decision D3 (`docs/plans/2026-10-23-cli-
interface-redesign.md` §10): the product owner's stated vision is the "real need" D3 deferred to. Depends
on engine E1 (progress contract). Supersedes the unapproved concept `decoy-platform/docs/plans/2026-10-01-
cli-harness-and-startup-animation-concept.md` for the first slice; the wordmark spike is out of scope.

Rules consulted: 00-universal, development-loop, risk-and-exceptions, observability-and-resilience,
architecture, api-and-compatibility, security, reuse-first, testing, documentation; CLI `CLAUDE.md`.

Risk: R2 (concurrency; a local state directory; a new machine-readable stream CI will depend on).

## 1. Guarantee and non-goals

Guarantee: `decoy run` can execute several configs with a bounded number of concurrent jobs, emit a
line-delimited JSON progress stream that works without a TTY, record each run's state locally, and let a
second terminal (`decoy status`, `decoy run --watch`) see active and recent runs with live row counts and
rates. Run records hold metadata only: never cell values, secrets, full config contents or unredacted
exception text. A crashed run is shown as stale, never guessed as succeeded. Python callers get the same
events through `decoy.run(config, on_progress=...)`.

Non-goals: a daemon or scheduler, retries, cancel of another process's run (first slice: read-only
observation; a later slice may add `decoy cancel` via a cooperative flag file), platform job access
(SP-20 remote client stays last and platform-release-bound), multi-user semantics, resumable runs.

## 2. What exists

- Nothing local: `project`/`catalog`/`jobs` were removed on 2026-10-23; `jobs watch` was a no-op. The
  only leftover is the docstring "Nothing is persisted to .decoy/workspace.json".
- Progress: a single Rich spinner (`ui/progress.py`), disabled when stderr is not a TTY; `--json` emits one
  envelope at exit; `--notify` fires once at terminal state.
- Engine after E1: `ProgressSink` events (phase, rate, route, warning, terminal).
- Platform: queue worker, memory ledger, target locks, heartbeats, reaper, SSE. These are orchestration;
  the CLI needs a lightweight local equivalent, not a port.

## 3. Established solutions

- Progress stream: dbt `--log-format json` and Bazel's Build Event Protocol: one JSON object per line on
  stderr (or `--progress-file`), stable `event` names, consumers parse by name. Adopted as `--progress
  jsonl`.
- Local job queue: `pueue` and `task-spooler` show the minimal shape (a run directory per task, a status
  file, a log file, N parallel slots); `make -j N` and GNU `parallel` show "N at a time" without a daemon.
  Adopted: a `concurrent.futures.ProcessPoolExecutor(max_workers=N)` over the configs, each child a normal
  `decoy run` of one config; no daemon, no persistence beyond run records.
- Liveness: pidfile plus heartbeat mtime (the systemd/pueue convention); stale when the pid is gone or the
  heartbeat is older than 3 intervals. Adopted from the observe concept's sketch.
- Admission: the engine's `estimate_job_capacity` (E2c) decides whether a second job may start now; no
  CLI-side memory model.
- Remaining custom code: run-record layout and the Rich status table.

## 4. Design

- Run records in `${DECOY_HOME:-~/.decoy}/runs/<run-id>/` (not the project directory): `status.json`
  (atomic replace), `events.jsonl` (append-only, E1 events as emitted), `heartbeat` (touched by the
  runner), `run.log` (redacted narrative). `run-id` = UTC timestamp + short random; `--run-id` override for
  orchestrators. Retention: keep last 50 or `--keep`.
- `decoy run CONFIG... [--jobs N] [--progress jsonl|rich|none] [--watch] [--run-id ID]`:
  N configs, N at a time (default 1, so single-config behaviour is unchanged); each job writes its own
  record; the parent aggregates exit codes (worst wins, same six-code contract) and prints one summary.
  `--progress jsonl` streams every job's events, each tagged with `run_id` and `config`, to stderr or
  `--progress-file`; it works without a TTY and never co-exists with `--json` on stdout (envelope stays
  the one stdout object).
- `decoy status [RUN_ID] [--json] [--follow]`: lists active/recent runs with state, phase, rows done,
  rows/s, elapsed; `--follow` re-renders every second from the records; a stale heartbeat shows `stale`.
- `decoy run --watch` is `status --follow` attached to the runs this invocation started.
- Admission between concurrent jobs: before starting job k, call `estimate_job_capacity` and hold the job
  if the sum of estimates exceeds the host budget (`--memory-budget`, default from the engine's cgroup/host
  read), printing why. Target collision: refuse two configs that declare the same target path up front.
- Library: `decoy.run(config_or_paths, *, jobs=1, on_progress=None, run_dir=None)` returns per-config
  results; `decoy.mask()` gains `on_progress=`.

## 5. Slices and acceptance

1. **C4a progress stream + run records for a single run** (`--progress jsonl`, records, heartbeat).
   Tests: JSONL lines parse and carry the E1 event names; no value or secret appears in any record
   (sentry with a secret-bearing config); records written atomically (kill -9 mid-run leaves a
   parseable `status.json` and `stale` on next `status`).
2. **C4b `decoy status` / `--watch`.** Tests: Rich snapshot and `--json`; stale detection by pid and by
   heartbeat age.
3. **C4c `--jobs N` over multiple configs** with admission and target-collision refusal. Tests: two small
   configs complete concurrently with correct aggregate exit code; one failing job yields `EXIT_RUNTIME`
   while the other's output is intact; same-target refusal is `EXIT_USAGE`.
4. **C4d library `decoy.run` + `on_progress`**, docs (`explain progress`, README "Running several
   pipelines"), CHANGELOG. Record the D3 reversal in the redesign plan's decision record.

## 6. Failure modes

Orphaned children on parent SIGINT (forward the signal, mark records `interrupted`); disk full in the
records dir (fail the record write loudly, never the data run); two CLIs sharing `~/.decoy/runs` (per-run
directories, no shared index file to corrupt); secrets in `run.log` (reuse the notify redaction and the
YAML-error sanitiser; sentry).

## 7. Done when

A developer can start two pipelines from one command, watch both from another terminal, and pipe a JSONL
progress stream into CI logs; the audit's "no concurrency, no monitor" finding is false; the redesign
decision record carries the D3 reversal; plan archived.
