# Recently shipped

Reverse-chronological log of shipped work, moved off the roadmap so the roadmap
carries only current + next-up work. This is orientation context, not the
exhaustive record: the full dated history lives in `sprint-ledger.md`, and each
program's own plan doc under the implementing repo's `docs/plans/` holds the
per-task gate detail.

Standing rule (dev-loop DOCUMENT phase): when a slice lands, move it here, update
the roadmap's current + next-up, and reconcile any trailing plan STATUS lines.

Status: record

Moved here from `decoy-platform/docs/backlog/RECENTLY-SHIPPED.md` on 2026-11-05 with the roadmap
([ROADMAP.md](ROADMAP.md)). The platform copy is frozen at that date. Entries below 2026-11-05 are
copied unchanged; paths in them are relative to the repo they name.

Last updated: 2026-11-05 (entries for 2026-10-27 to 2026-10-30 are not filled in here; see the repos'
git logs).

---

## 2026-11-03 to 2026-11-05 (summary, from the roadmap main-tips rows)

Re-read from each repo's `origin/main` on 2026-11-05. One line per merge group; detail is in each PR.

- **Engine** (`41a86f47`): H-1 E0 pure-move checker and Wave B sentries (#372 to #375); F31 E0c
  registry 1.5.0 (#377); X0a ratchet and manifest (#378, #379); X0a self-hosted gate (#380); H-1 E5
  (#381); X7b isolated-run payload as a private file (#382); CI-E0 golden suite repair and tokenize
  coverage (#383); X4d GCS client timeouts and the outbound client construction sentry (#384, #385);
  H-1 E3 module splits (#386).
- **CLI** (`8fba6af`): F30 C1a OTel exporter (#80); CLI X0a ratchet, every sentry gated and
  baselines shrink-only (#81), CLI allowlists registered in the ratchet (#82).
- **Platform** (`73a0bfca`): user role builds and runs pipelines (#164); B-10 S1b (#165); F21 s1b
  layout authoring (#170); credential cascade on user delete (#171); RBAC S0-pre shared route walk
  (#173); X0b (#178); X0a gate CI (#180); X0a-h plan (#181); X7a (#182, #183); deactivation S1 and
  S1b (#184, #193); test trust (#185, #186); CI lanes plan (#187); X5b (#188, #189); password-reset
  token fix (#192); pipeline baseline (#194); X2a FK delete policy (#195, #196).


## 2026-11-01 evening (merges after R-a)

Re-read from each repo's `origin/main` on 2026-11-02. Gate verdicts are from the gate ledger; test counts are
worker-reported unless marked.

- **Platform #131** (`32b4149f`, `fix/key-restore-output`): key restore returns only `which`,
  `restart_required` and `message`; the three 422 refusals use fixed text with no cause or context;
  `KeyDurabilityError` no longer chains the `OSError`; the SSO discovery test returns no URL or error text.
  Canary tests fail on the old behavior. Gate: argon text-only GO.
- **Platform #132** (`584a15a7`): roadmap currency, Phase 0 evening update.
- **Engine #359** (`a3fe49e8`, `fix/sbom-polish`): SBOM generator failures use fixed messages, raw `uv`
  and CycloneDX output is replaced by fixed lines unless `DECOY_SBOM_DEBUG=1`, `PIP_*` and `PYTHON*` scrubbed by
  allowlist. Gate: argon text-only GO-WITH-FIXES. Known follow-ups: `sbom.sh` line 96 `cd` stderr can name
  the caller path; lock-mode refusal still prints lock package names.
- **Platform #133** (`2d40c9a5`, `feat/di1-gof-build`): DI1 goodness-of-fit measurement. Main merged in with
  one docs-header conflict (main's header kept). Suites: no new failing id against main.
  `api/quality/runner_hook.py` is now 710 lines (main was 631).
- **CLI #76** (`57e8b81`, `chore/repin-engine-0.17.0`): repin to engine 0.17.0 (split renames,
  `version: 2` configs, keyed mask secret on `report vault` and `unmask`, rule-code allowlist derived lazily
  from the engine reason registry, per-route keyed-secret guidance). 1979 tests pass on 3.10, 3.11 and 3.12
  against 1866 on the previous main. Gate: argon text-only GO.

## 2026-11-01 (engine release R-a, platform remainder)

Re-read from each repo's `origin/main` on 2026-11-01. Worker-reported test counts are from `uv.lock` or
`requirements-dev.lock` venvs and were not rerun by the orchestrator.

- **Engine release R-a:** annotated tag `v0.17.0` at `1132d29e` (R-a prep merge: version single
  source 0.17.0, `docs/records/release-ra-facts.md`, `scripts/release/cut-release.sh`, reason-release pin
  tooling, differential-privacy rows re-pinned). Carries the STORM close-out, F13 slices 0-2, the OOC
  correctness harvest, the main-health fixes, the B-2 release script fixes and the SBOM generator.
- **Platform #130** (`19b50071`, `fix/platform-remainder`): the suite is green apart from a known list.
  Str-valued enums format as their value on every Python (59 enums, one base class, a sentry);
  24 mutating routes classified for audit coverage with a test that every listed helper writes audit;
  `hash_csv_file` handles NUL on 3.10; `/api` router wiring moved to `api/api_router.py` with an
  identical route table; stale tests corrected; the slow h5 test sized for the row-framed reader
  (about 156 s down to 7 s alone). Worker-reported on 3.10: 15 failures left, all known (13 P6
  parquet-size drift, one p6b golden case kept red for BLOCKER-2, one flaky genapi_1f test).

---

## 2026-10-31 evening (all repos): main-health fixes, release script, SBOM generators

Merge commits re-read from each repo's `origin/main` on 2026-11-01. Tests quoted here were run by the
workers on `uv.lock`/`requirements-dev.lock` venvs, not rerun by the orchestrator.

- **Engine #352** (`0090f6f9`): main-health fixes (module-size census, 3.12 f-string and fd fixes, mypy
  16 to 0, numpy timedelta, `type` added to the frozen `when` reserved names). **Engine #353**
  (`78b78e2d`): the native companion release workflow and its checks script (relative key paths survive
  the `cd`, five-field wheel names, anchored platform regexes, pinned version, checksum parsing like
  `sha256sum --check`); unexercised, Actions is billing-blocked. **Engine #354** (`1491c7fa`): OOC
  correctness harvest. **Engine #355** (`1ee89e68`): CycloneDX SBOM generation from `uv.lock` in a
  hash-pinned tool environment. Engine main worker-reported: 0 failures on 3.10, one known failure on
  3.12 (`test_skewed_weights_skew_cdf`, `899999 == 900000`). Released as `v0.17.0` on 2026-11-01 (R-a).
- **Platform #128** (`4077fa21`): canary-check ownership checked against the caller, `create_job`
  passes the authorized pipeline id, snapshot-less canary-check refused (409), `run_job` persists the
  snapshot atomically with pending to running, log-key contracts. **Platform #129** (`c7bc3dc4`): main
  imports and collects again (storm consumer migration, duplicate catalog keys removed, mypy and ruff
  clean, route-template label under FastAPI 0.162, new engine-import-surface sentry). Worker-reported
  full suite on the #129 branch: 41 failures remain (13 P6 parquet-size drift, 28 other groups).
- **CLI #74** (`8834ab9`): AST sentry forbidding private `decoy_engine` references outside an exact,
  counted allowlist. **CLI #75** (`df4c069`): CycloneDX SBOM generation for the CLI runtime pins.

Not shipped from this day, still open: the OOC temporal FK seam (built, round 2), A-4 (Codex NO-GO,
round 3), the B-6 batch writer (not gated), release R-a (prep running), the platform remainder.

## 2026-10-31 (all repos): STORM close-out, F13 slices 0-2, R1-a closed, health records

Merge commits re-read from each repo's `origin/main` on 2026-10-31.

- **Engine #339** (`6ce435ce`): F13 secret provider, engine slices 0-2 (secret-provider/v1 contract,
  before-read admission, Vault KV v2 adapter; 7 `runtime` reason identities). Slices 3-5 are next.
- **Engine #349** (`6d82517f`): STORM close-out. Profiling/verification split, F29 registry
  unification, v0.16.0 identities kept as tombstones. Registry on main after #339 and #349: 891
  identities, 14 namespaces, 2 tombstones (counted with `uv run --frozen` from `uv.lock`). Not yet
  released; the latest engine tag is still v0.16.0.
- **Engine #350** (`79b5c264`): engine main health record (survey only). **Engine #351**
  (`545d913c`): per-column routing performance concept (docs, not gated).
- **Platform #124** (`aad2de7`, 2026-10-30 23:50 -0500): roadmap branch register. **Platform #125**
  (`b31bbaa`): cross-model audit packets 11-20. **Platform #126** (`a4f5857`): platform main
  health record (survey only).
- **CLI #71** (`850fd92`): dead engine substrate plumbing removed and an engine import-surface
  sentry added; closes R1-a. Breaking, pre-GA. **CLI #72** (`8b4353b`): CLI main health record.
  **CLI #73** (`c459758`): `decoy init` wizard spec, registered Post-V1 on demand.

Main was red in all three repos on 2026-10-31 (engine module-size sentry, platform `api.main`
import, CLI e2e until #71). Fixes are in flight and not shipped, so they are not logged here.

## 2026-10-26 (platform): main un-red - tokenize catalog coverage + engine 0.15.1 reconcile

Platform main had been non-bootable since the #105 repin left the 0.15.x migration half-done
(pyproject + CI at 0.15.0, but the engine_compat specifier, the version-fence tests, FROZEN, the
capability doc, the fence PIN_PREFIX, and the Dockerfile engine ARG all still at 0.14.2). The GitHub CI
is billing-blocked, so only the local ci-mirror caught it. Un-red landed as a decoupled standalone
(`c717fa43`; dennis GO, and Codex had already cleared the catalog coverage + import against 0.15.1 in
the B-6 gate): the confirmed-safe tokenize strategy-catalog coverage plus the full engine 0.15.1
reconcile, WITHOUT the B-6 vault feature (whose crypto/concurrency half was still in security
remediation). `api.main` now imports and boots on engine 0.15.1 (tag v0.15.1, stamp fd51be10). The
vault platform half rebases onto this bootable main and lands its vault-only delta once it clears both
gates.

## 2026-10-26 (engine): 0.15.1 release + B-9 DI1a engine half (datetime / free-text GOF)

The DI1a measurement half (engine) merged and shipped as a point release:

- **B-9 DI1a engine measurement** (engine PR #326, merge `f6ce5db1`): extends generation-output
  fidelity (GOF) measurement to datetime and free-text columns. Report-only; no distribution claim.
  dennis GREEN; Codex final GO (one non-blocking MEDIUM: a serialized metric keeps the generic
  `ks_complement_binned_cdf` tag without the domain label).
- **Engine 0.15.1 release**: version stamp off `release/v0.15.1` (`fd51be10`), tagged `v0.15.1`. It is
  0.15.0 plus the DI1a GOF and the post-0.15.0 main progression (the #309 bounded reader, parity E2a).
  DI0 golden is byte-identical on both 0.15.0 and 0.15.1 (the GOF is additive). Platform reconciles to
  `decoy-engine==0.15.1` as part of the B-6 platform-half merge.

## 2026-10-26 (engine): 0.15.0 release + route-coverage, tokenize sentries, bounded reader

Four engine merges landed after the B-6 write-seam, all two-checkpoint gated (dennis then Codex
cross-model) and reconciled onto a moving main:

- **Route-coverage phase 1** (PR #324, `a39c648`): B3-B7 out-of-core and bounded-sequential strategy
  coverage (faker pool, group_key, text_mask, code_set).
- **Tokenize sentry registration** (PR #323, `bbe4dce`): registered the `tokenize` strategy across the
  correctness sentries (distribution-behavior label, leak-check TRANSFORMATIVE, proof-manifest waiver,
  capability matrix, technique class) that the #322 write-seam had left unregistered, which had reddened
  main. Green-main fix.
- **gm bounded reader + progress sink** (PR #309, tip `17c0bdeb`): parity E2a `decoy_engine.io` reader plus
  the value-free progress sink (output bytes never depend on the sink).
- **Engine 0.15.0 release**: version stamp off main, tagged `v0.15.0` (the additive feature release since
  0.14.2: vault write-seam, Phase D FK, CSV source params, route coverage). Platform repin to 0.15.0 is the
  remaining D-4 piece.

## 2026-10-26 (platform): docs currency - capabilities + roadmap ground truth (#103, #104)

Refreshed `docs/product/capabilities.md` to the shipped surface (engine tokenize write-seam, the 10-feature
governance bundle, FORECAST retired, mask count 24) and added `docs/backlog/roadmap-vs-reality-2026-10-26.md`:
a code-verified SHIPPED/PARTIAL/OPEN map of all 27 V1 build-order items (12/7/8), then folded those verdicts
and the day's merges into ROADMAP.md and archived the superseded current-assignment table.

## 2026-10-26 (engine): B-6 tokenization vault - engine write-seam (PR #322)

Engine half of reversible tokenization. A `tokenize` masking strategy writes a deterministic surrogate
token per source value and records the plaintext->token mapping through a platform-injected
`TokenVaultWriter`; `run_pipeline` gains a keyword-only `token_vault_writer` (additive, recorded in
compatibility-contract 3.4). Full-frame only; fails closed with no vault, no namespace, non-string
dtype, or any vault error (coded `tokenize_vault_error`, no value/token leak). Always-keyed, so GA
requires a real secret. Vault identity is scoped by `(namespace, plaintext)`.

Gate: dennis GREEN; Codex final GO. The Codex cross-model gate caught three security findings the
internal review missed - GA secret bypass, cross-namespace token collision, and plaintext leaking
through a vault-callback exception - all fixed at source with regression tests and confirmed closed on
re-gate. Local verification 7803 passed / 8 skipped; ruff + mypy clean.

Next in the B-6 chain: cut an engine release exposing the write-seam, repin the platform, then build
the platform half - the vault store (must key by `(namespace, plaintext)`; its exception-logging must
not dump `exc.__context__`) plus the admin-only de-tokenize auth (already implemented + dennis-verified).

## 2026-10-26 (platform): confident-dirac 10-feature hardening bundle + OBS-5 audit-drift fix

**confident-dirac bundle.** The ten reviewed-and-remediated platform-idea features merged to main:
Ed25519-signed output passport, external-KMS master-key envelope, air-gapped install bundle, bounded
output canary-leak check, referential-subset preview, checksum-validated regional detector packs,
source schema-contract with drift detection, upgrade-determinism golden gate, advisory
column-disposition memory, and admin-authored org-disguise presets. Four alembic migrations serialize
into one linear head (table count 79). dennis-GO on the rebase reconcile (migration chain + 79 tables
verified on real Postgres; feature code byte-identical to the earlier Codex-GO'd state).

**OBS-5 audit-action drift guard.** Registered the ENV-2 `pipeline.binding.*` actions in
`AUDIT_ACTIONS` and classified the `genkey.*` and confident-dirac governance actions
(`passport.sign`, `golden.*`, `schema_contract.*`, `column_disposition.*`, `org_disguise.*`) as
blocking in `SECURITY_CRITICAL`, greening the audit-coverage drift guard.

---

## 2026-10-26 (engine): cross-column PR1, release-hygiene, v0.14.2

**Cross-column dependency PR1 (engine #315).** Fixes a latent order-dependent read: `derived`,
`group_key`, and `joint_mask` could read a declared sibling driver column by lexicographic name-sort
accident instead of its masked value. Adds an explicit dependent-after-driver ordering edge and pins
the driver-read direction per strategy (derived/group_key read masked from the live frame; joint_mask
key_by reads source from the pre-mask snapshot). Double-gated (dennis GO + Codex GO) after three Codex
remediation rounds that closed the joint_mask multi-entry writer-map stale read, the missing-snapshot
fail-closed gap, the when-gated snapshot alignment, and the gated multi-output writeback. PR2 (the
derivation feature itself) is a later slice.

**Engine release hygiene (#314).** `gen_proof_manifest.py` now derives the stamped engine version from
the newest CHANGELOG release section instead of a frozen `0.2.0`; the proof manifest was regenerated.

**Engine v0.14.2 tagged.** Patch release carrying the subset single-table edgeless-over-budget fix
(#312), cut so the platform referential-subsetting preview can pin it.

**Known CI note:** the `substrate (pandas)` RSS perf test (`_ENVELOPE_FACTOR = 1.35`) is too tight for
the CI runner and fails non-blockingly on engine PRs; recalibration to ~1.45 is queued (decision D2).
The CodSpeed `benchmarks` job is also broken repo-wide (action v4 + installer-hash mismatch).

---

## 2026-10-25 (docs + web currency): D-1/D-2 refresh, marketing-site honesty fixes

**D-1 capabilities.md (platform).** Refreshed to the V1 shape and then a follow-up pass corrected
the stateless-CLI command surface, stated pandas as the default masking engine (Polars scoped to
subset only), and fixed an over-stated platform vault-recovery claim (the full-frame route does wire
a VaultWriter; end-to-end recovery is not yet developer-verified). dennis docs-honesty gate caught
the false vault claim; fixed and re-gated GO.

**D-2 architecture docs (platform).** Rewrote the living `docs/architecture/*.md` to the stateless
CLI shape and dropped the retired project/catalog/jobs and FORECAST surfaces. Accepted ADRs were
left immutable (the refresh touched only the living docs).

**Marketing-site honesty (B-3 partial, decoy-web).** Softened two overstated claims: the audit-log
heading now reads "tamper-evident" rather than "proves it was not edited", and single sign-on reads
"supported, documented for" rather than "tested with" (real-IdP testing is customer-deferred; CI is
mock-based). The homepage performance figures, DP wording, and license split were flagged for a
human decision and left unchanged.

**A-3 reconciled.** Confirmed the route/backend capability page already shipped as
`decoy-engine/docs/execution-backends.md` (#305), including the composite and multi-parent FK
decline-with-reason detail; no second page was created.

## 2026-10-25: Phase D multi-parent FK (A-9, Dmp) + DuckDB-in CLI source (B-1)

**Dmp (multi-parent FK, engine #310, `c5e70982`).** Multi-parent foreign keys now admit on the
out-of-core (streaming) route with byte-parity to the reference path (folds N parent relations into one
first-hit-wins relation, then the child joins once; deterministic; fail-closed on cross-parent dtype
mismatch). Rebased onto the post-dcomp main (supersedes the closed #308). Double-gated; the real-kernel
suite is non-vacuous (require_companion gate, 150 passed), zero new substrate failures. With dcomp
(#307) this completes A-9: both hard FK shapes are native on the out-of-core route.

**DuckDB-in CLI source (decoy #c1f5e60).** `decoy run --duckdb-source TABLE=DB_PATH` (repeatable) reads
a table from a DuckDB file as a masking source: opens read-only, snapshots the relation to a temp
parquet (reserved-word / case-variant safe via catalog-resolved double-quoting, default-schema-only),
and masks via the ordinary parquet path (no engine change). Double-gated; 18 e2e tests. Completes the
B-1 DuckDB-in item.

## 2026-10-24: Environments / release RBAC (B-7, PR #100)

Typed per-environment pipeline resource bindings (`pipeline_resource_bindings`, the `${resource.*}`
scope) plus promotion/release RBAC merged to main (`14209a19`). The remote worker's branch was rebased
onto current main (migration re-pointed onto the `genapi1e` head for a single alembic head), then
double-gated across several rounds. The gate closed: the ENV-2 cross-user validate-yaml binding leak
(HIGH, foreign user now 404s with zero decrypt), value-free refusals (no submitted field, descriptor
type, or role echoed anywhere), a false-green `${resource.db.<field>}` at validate time (now matches
the run-time field walk, bare NO_DEFAULT references too), and existence-only validate (no decrypt on
the reject path). dennis GO + Codex GO. The in-app admin/RM/user roles are the V1 model; owner/grant
self-service de-token stays V2.

## 2026-10-24: Served PipelineConfig JSON Schema endpoint

`GET /api/pipelines/config-schema` now serves the engine's `PipelineConfig.model_json_schema()` (in an
envelope with the installed engine version) so the web client can pre-check a pipeline document's shape
before a server round-trip. Read-only, authenticated with the standard pipelines gate, no new
permission. The served schema is the engine model's own, so it can never fork from server validation;
`validate-yaml` and job-preview stay the authority. First of the 2026-10-24 remote-worker `feature/*`
batch to clear the gate (dennis GO, Codex GO-WITH-CHANGES on docs only). Merged `a69265e0`; branch
deleted. Plan: `docs/plans/2026-10-24-served-pipelineconfig-json-schema.md`.

## 2026-10-24: MCP server (B-8) + platform-wide file-source authorization

The in-app MCP server merged to platform main (`ababaf6c`): an agent-facing `/mcp` surface with a
capability-tier registry, a fail-closed `CuratedTargetGuard` (exact-route allowlist, refuses to mount if
any curated route is missing), and a `wait_for_job` long-poll that releases its DB connection before
sleeping and caps waiters per-principal and globally. It ships with `api/jobs/source_authz.py`, a single
choke-point that authorizes every pipeline file source under the caller's principal at four entry points
(create_job, job preview, node preview, workflow-step build): a non-admin may read only their own managed
uploads; absolute/external paths stay admin-only; foreign and missing uploads return an identical 403 (no
existence oracle); any descriptor that is not a literal `s3`/`gcs` binding type has its path authorized,
so a variable/missing/unknown source type cannot smuggle an absolute path past the check. Double-gated
(dennis + Codex); the cross-model gate caught and closed, across rounds, a path-injection tier bypass, a
source-authz BOLA, an unbounded download, a connection-pool exhaustion, and the variable-typed-source
escape. Deferred (documented): a claim-time re-check for jobs queued before the fix and for iteration
children (defense-in-depth for the single-org trust boundary). Supersedes the earlier MCP branches and
PR #101 (landed via the rebased `feat/mcp-b8-complete`). Plan:
`docs/plans/archive/2026-10-22-mcp-server-buildout.md`.

## 2026-10-24: GEN-API 1f (public one-shot generation route) + slice-1 program complete

The public one-shot generation route `POST /api/generate/{job_id}` merged to platform main
(`a7d203fb`), INERT behind the default-off `generation_enabled` flag. This completes the GEN-API
slice-1 program (1a credential type, 1b config-bound key, 1c admission/seed adapter, 1d bounded child +
encoder, 1e DB-atomic quota + limits, 1f public route). 1f composes `resolve_generation_key` ->
`authorize_generation_call` -> `admit_window` -> `generate_bounded` under `enforce_generation_limits`,
with a retained completion-owner that settles quota, releases the response-byte reservation, and writes
one terminal tamper-evident audit row exactly once across disconnect, task cancel, and send-failure.
json + jsonl served; `/stream` and csv/parquet deferred to Slice 2. Double-gated (dennis + Codex); the
cross-model gate caught a real post-lease-before-owner resource-leak that was remediated before merge,
and the DB-atomic settle path was verified on real Postgres. Go-live (flipping the flag on) is a separate
pending Cam decision. Plan: `docs/plans/2026-10-24-genapi-1f-public-route.md`.

### 2026-10-24 -- GEN-API 1e (resource-limit + DB-atomic quota layer) MERGED (platform `3aba113b`)

The operator-guardrail layer over 1d's bounded child: a durable per-key daily quota (a
`generation_quota` row per key per UTC day, reserved with a single conditional cross-worker
`UPDATE ... WHERE remaining >= n` so two workers can never both pass a near-exhausted counter, create-
if-absent `ON CONFLICT DO NOTHING` that never refills an exhausted row), a `generation_quota_settlement`
lease that commits the refund and its terminal state together so an ambiguous-commit retry credits
exactly once, per-key burst + in-flight caps on top of the global generation lane, uniform `429` +
`Retry-After` value-free refusals (with a quota-DB outage failing closed as `503`, not a quota
masquerade), and a `decoy_generation_refusals_total{code}` metric. Internal only (the limit gate is
wired in 1f); the quota is a self-hosted operator guardrail, not a billing meter.

Gate history: Opus plan took 3 plan-gate rounds (dennis + Codex) hardening the transaction boundary,
`ON CONFLICT DO NOTHING`, durable settlement idempotence, the 1f-sole-audit-owner contract, and the
burst-token-stays-consumed rule. Build (Sonnet, tests-first) ran the two-worker atomic-race and
concurrent-settlement proofs on a real Postgres. Final: dennis GO (ran the Postgres race proof himself;
verified the obs5f-guard and migration-pin edits are legitimate register-ahead-of-writer accommodations,
not weakening) + Codex GO-WITH-CHANGES (no correctness defect; two completeness items closed before
merge: a fully-populated-downgrade migration test and this doc pass).

### 2026-10-24 -- D-1 capabilities.md V1 currency refresh MERGED (platform `ed8804a3`)

Brought the product capability catalog (the customer-facing source of truth) current for V1.
Retired FORECAST and split the surviving disguise catalog into a standalone Disguises capability;
added the shipped observability program (tamper-evident audit hash chain + integrity verifier,
reader/export, admin retention, opt-in Prometheus metrics, request-id logs), fixed-width OUTPUT,
Postgres database input, the re-identification/unmask vault, the GEN-API foundations (through 1d,
marked internal/no-route), and the operator/admin split; added the auto-update non-claim; and
pointed the detector/strategy/disguise enumerations at the generated engine capability matrix to
stop future drift. Double-gated for accuracy: dennis verified every changed claim against code
(caught 5 residual FORECAST mentions, swept); Codex caught two semantic imprecisions (the audit
verify is `POST /integrity/verify`, not `GET /integrity`; `outputs.unmask` is an admin permission,
not a job setting), both corrected and re-verified against source.

### 2026-10-24 -- GEN-API 1d (bounded generation child + exact-byte encoder) MERGED (platform `18da588a`)

The execution + encoding half of the Generation API. Given an admitted pinned plan (1c), a caller
seed, and a bounded window (offset/count/format), 1d runs the generation in a killable child under
hard RLIMIT_AS + deadline limits (a new `generation` lane on the shared supervision registry,
wired into `_start_supervision`/`_stop_supervision`/`validate_host_child_budget`, fail-closed
acquire) and encodes the rows to exact wire bytes with a framing-independent window digest
(len8-prefixed BLAKE2b-256 over canonical records; JSON and JSONL agree). Internal only
(`generate_bounded`); no route until 1f. Ships the response-bytes reservation primitive 1e builds
the quota over.

Gate history (the value of the two-model gate on display): Opus plan took 3 Codex plan-gate rounds
(grounded against the real `api/supervision/{registry,reaper,startup}` primitives and the actual
`AdmittedGenerationPlan` shape). The CODE then took 3 final-gate rounds, all on one confidentiality
class: round 1 serialized the whole `config_json` to the child; round 2 added a key-level allowlist
but copied nested values verbatim (Codex reproduced a leak: a sequence column carrying a nested
`distribution:{seed,credentials,path}` survived into both projections); round 3 replaced it with a
type-aware, fail-closed, scalar-only projection (`_PROJECTIONS` + `_project_column` raising
`window_invalid` on any non-servable type, unexpected field, or non-scalar value), applied to both
the generation config and the pinned projection, with an engine-drift pin test. Final: dennis GO
(independently reproduced the exploit + 70-case fuzz, all refused) + Codex GO. The only residual is
by-design (a caller's own `prefix`/`suffix` string served back as generation data). Known 1f
follow-up: a seed-sensitive full-oracle parity test once seed-dependent generators are servable
(today's Class-A tables are sequence-only, so served bytes are seed-independent).

### 2026-10-24 -- Doc-currency D-3 (engine CHANGELOG per-tag cut) MERGED (engine #306)

First remote cloud-agent deliverable, gated and merged here. The engine `CHANGELOG.md` kept
everything since 0.7.0 under one `[Unreleased]` heading (the release process stamps each version
on its tag and never merges it back); #306 re-files those entries into per-version sections
`[0.8.0rc1]` through `[0.14.1]`, additively (90 insertions, 0 deletions: the dated entries stay in
place and order, with version headers + each tag's stamped summary inserted between them).
`[Unreleased]` retains only `§CSV-PARAMS` (#303, which shipped after v0.14.1). Double gate: dennis
GO 0/0/0/0 (all 8 version boundaries exact by tag-set comparison, additive-safety formal); Codex
GO after one BLOCKER fix (the 0.10.0 summary, copied from the tag stamp, wrongly said OBS-1b was
"carried since 0.9.0"; OBS-1b shipped in 0.10.0, corrected in the cut). CHANGELOG-only; no graph
refresh needed.

### 2026-10-24 -- V1 build-order A-3 (execution-backends reference doc) MERGED (engine main c4ca838d)

New engine reference `docs/execution-backends.md`: a reader-facing reading of the test-enforced
compute matrix. For masking, which backend computes each strategy per route (compiled Rust /
compiled index selection / named-Arrow / no-op / dedicated-Python / declined-with-reason / excluded),
across the sequential, out-of-core, and native-chunked routes, with the FK key surfaces and the
documented dedicated-Python exception set. For generation, the headline fact (Python/NumPy by
design, never the compiled companion; FR3 shelved) with the per-kind compute classes. Sources
cited: the D-audit compute-matrix record + the F-audit generation plan. Registered in the Reference
toctree + prose index. Gate: dennis GO 0/0/0/0; Codex GO after 3 rounds, closing 6 accuracy MEDIUMs
(declined-vs-rerouted, the code_set SEQ row, OOC excluded/mask-mode, narrowed composite/multi-parent
scope, generation compute classes, the sphinx-excluded F-audit link, and the faker masking-vs-generation
conflation). Docs sphinx -W workflow green on the head commit (it failed on the first commit over the
excluded plans/ link, which the remediation fixed). Doc-only; no graph refresh needed.

### 2026-10-24 -- V1 build-order A-1 (engine release hygiene) MERGED (engine main 0b8219f5)

First slices of the V1 clean-release build order. **CSV source params** (#303, `b5d3cbbc`):
additive `FileSource` `has_header` / `column_names` / `delimiter` + profiler reader support,
closing the headerless + non-comma delimited input gap; the two-tokenizer root cause (stdlib
`csv.reader` vs pandas disagreeing on byte classes) was closed by rejecting NUL and lone-CR
before tokenizing, plus frame-width and coded-pandas backstops (LF/CRLF only). **Release
hygiene** (#304, `0b8219f5`): retired the overstated ~10x calibration benchmark (the manifest
now publishes no throughput figure; the sentry still enforces provenance on any that exist) and
excluded `tests/` from the sdist (wheel byte-identical). Both double-gated (dennis GO + Codex
GO) under the new light-tier model (regression-gate/fuzz-sanitizer non-required, benchmarks/
pip-audit advisory). Deferred (own slices): engine CHANGELOG per-tag cut (doc-currency), full
`/proof` regeneration (couples to the frozen launch engine). See ROADMAP A-1.

### 2026-10-23 -- GEN-API Slice 1c MERGED: snapshot admission + caller-seed adapter (platform main ce34665a)

Platform `api/generation/pinned_adapter.py` admits a generation job's frozen snapshot into a
reproducible pinned plan plus per-table window admission, from one engine compile. Admission only: no
route, no execution. The caller supplies the seed; the adapter never reads a stored job seed, the
instance default, or a master-key-derived seed. Statistical and DP references are refused for V1. Engine
refusals map to fixed codes by exception type, and no cell value reaches the error. Adapter lineage:
`8f9ba2c5` (feat), then `5ebb3ad6` (drift-guard coverage) and `ce34665a` (exception-type mapping). Open
before-1f follow-ups are recorded on the roadmap (statistical refusal ahead of compile; exact-code test
assertions). Slice 1f (public retrieval route + `execute_pinned` wiring) is next.

### 2026-10-23 -- GEN-API 1c engine prerequisites + engine 0.14.0 / 0.14.1 releases, platform pins bumped

Engine #299 (`fb144c65`, `classify_window_from_generation_plan` pinned-admission bridge), #301
(`c0e2fb51`, `reference_date` global-settings field + admission bridge), and #302 (`6bc4a5c9`,
`compile_pinned_plan_with_generation` returns the `PinnedPlan` and `GenerationPlan` from one compile).
Released as decoy-engine 0.14.0 (`e66f7f07`, tag `v0.14.0`, carries #299 and #301) and 0.14.1
(`12e84c39`, tag `v0.14.1`, adds #302). Platform engine pin moved `==0.13.0` to `==0.14.0` (`f6bfa4c8`),
then `==0.14.0` to `==0.14.1` (`1d8ce08a`).

### 2026-10-23 -- Fixed-width OUTPUT platform wiring MERGED (platform main f8122f0e); CLI half PARKED

Platform side of the fixed-width writer (engine primitive below): format-authoritative output, an
immutable layout snapshot taken at job time, retrieval decode, and a refusal for streaming output
(`fixed_width_output_streaming_unsupported`). Series: `c682354c` (wiring), `7e4a93ce` (path-free errors
for OSError and engine errors), `c1605894` (deterministic path-prefix strip), `f8122f0e` (restore the
source-byte scan budget; cover blank-line partial pages). The CLI half is built and dennis-approved on
decoy-cli branch `feat/cli-fixed-width-output-v2` (`51f00c8`) but NOT merged. Cam parked it deliberately,
blocked on a cross-repo DP re-certification decision. Recorded as PARKED, not done.

### 2026-10-23 -- Fixed-width OUTPUT writer MERGED (engine #297, main 86f75448)

The last any-to-any file-format direction: a public `write_fixed_width(frame, layout, path)` that is
the exact inverse of `read_fixed_width`. A field is emitted only when the reader's own decode reads
it back unchanged, so the writer fails closed on every value that would not round-trip (overflow,
pad-character ambiguity, a record-separator LF/CR pad, null/NaN, type mismatch, embedded newline,
non-UTF-8, a signed-zero sign flip, an oversize integer past Python's int-to-str cap). Publication is
failure-safe: records go to a temp file, fsync, then `os.replace` only on full success (plus a
best-effort directory fsync), so a mid-frame failure leaves the destination untouched. Errors are
PII-safe (position, column, length, never a cell value, no exception chain). `FileTarget` gains
`format="fixed_width"` with a required `layout`; `S3Target`/`GCSTarget` still reject it. This is an
unwired engine primitive: the CLI and platform wiring to call it, and output-dtype coercion for a
pandas-widened integer column, are tracked follow-up slices. Gate chain: took a parallel-session
head-start branch through a clean rebase (CHANGELOG-only conflict), dennis APPROVE (0 blocker/high),
then Codex gpt-6-astra final across three rounds that each surfaced a genuine boundary defect (a HIGH
record-separator-pad silent row loss; a signed-zero round-trip sign loss; an unguarded
directory-fsync close; a duplicate-column AttributeError; an uncoded extreme-integer error), all
remediated at root cause with regressions, to a final GO. 607 writer + sentry tests green,
ruff/format/mypy clean. Merged onto an engine main already red from a separate, pre-existing
`assert_exact_evidence` signature mismatch (an earlier r1b refactor, tracked for its own fix); this
slice touches none of those files and adds no new failures.

### 2026-10-23 -- GEN-API Slice 1b-P: configuration-bound generation keys MERGED (platform main, FF d31c805c..e6725799)

A generation API key is now bound at mint to one specific `mode=='generate'` job AND that job's approved configuration digest (`pipeline_hash`). `authorize_generation_call` refuses unless the binding is present, the key is active, the requested job matches the bound job, and the job's current snapshot digest equals the approved digest; any mismatch returns a coded `needs_reapproval` / `job_snapshot_corrupt` / `not_bound` / `job_not_bound`, fail-closed. The job-identity check runs before the requested job is loaded, so bound-to-other-job and nonexistent-job are indistinguishable (no enumeration). V1 jobs are immutable, so the digest is the version anchor with no integer version counter; an admin `reapprove` re-binds to the new digest and `revoke` deletes the binding. Every authorization read refreshes current DB state (`populate_existing` on binding, key and job), so a stale session cannot authorize an out-of-date approval. The minted digest is `repr`-hidden alongside the secret (it belongs in the audit channel only). There is NO public generation endpoint yet (wired in slice 1f); this is inert binding infrastructure. Gate chain: dennis APPROVE; Codex gpt-6-astra FINAL NO-GO then GO after remediation (closed a stale-ORM confinement gap with independent-session regressions that prove the stale session observes a committed reapproval/rewrite/revocation, reconciled the program-plan version contract from the obsolete integer counter to the shipped digest model, and hid the digest from the mint-result repr). ruff/format/mypy clean; 63 SQLite / 69 Postgres tests (stale-session regressions pass on Postgres). Plan `docs/plans/2026-10-22-genapi-1bP-binding-plan.md` + program `docs/plans/2026-10-22-genapi-slice1-program.md`. NEXT GEN-API: 1c snapshot/admission/seed, then 1d bounded child + exact-byte encoder, 1e resource limits + atomic quota, 1f route + audit (public endpoint last; the 1f `resolve_generation_key` inactive-owner vs OPEN-7 org-grants-survive-deactivation reconciliation is a tracked 1f blocker).

### 2026-10-23 -- DI1b: nested-GOF unavailability propagates into the quality report MERGED (engine #295, main 28986fa5)

Closes distribution-integrity finding F-DI0-2 from the DI0 contract: a nested per-column goodness-of-fit metric that is unavailable (skipped or errored) now propagates a `gof_unavailable` marker up to the report level instead of silently vanishing, so the omission is visible in the `QualityReport`. Additive to `quality/report.py` with a new golden snapshot (`gof_unavailable.sha256`) and baseline assertion; 652 quality tests pass. Report-only, no masking-path change. Gate chain: dennis APPROVE + Codex gpt-6-astra final GO (clean, additive); rebased onto current engine main and re-verified before merge. Pairs with the platform DI1a measurement-coverage half.

### 2026-10-23 -- Engine-correctness pass: when-gated string-output on numeric + vault-passthrough + seam-sentry CI + pandas range error MERGED (engine #294, main 92c3db85)

Took a parallel-session head-start branch through the full gate chain and shipped four mid-run crash / silent-truncation fixes as coded, fail-closed errors, closing bucket-4 pre-§AUDIT items §WHEN-NUMERIC, §VAULT-PASSTHROUGH, §SEAM-SENTRY-CI, §PANDAS-RANGE-ERROR (and confirming §MEM-EST-DTYPES). The headline fix (§WHEN-NUMERIC) was COMPLETED, not left partial: a `when:`-gated string-output mask on a numeric column is rejected at COMPILE for every statically-typeable strategy (reusing the engine's own `masked_output_type`, no parallel type logic) AND caught at EXECUTION by one generalized guard (`reject_gated_string_on_numeric`, in `execution/_gated_string_guard.py`) that fires on the exact crash condition: a resulting column that would be type-mixed (a string and a number together), for every gated write (faker, bucket_perturb, any pandas-only string emitter), covering partial gates, nullable predicates and intrinsically-mixed output; numeric-only passthrough and uniform-string full replacement are allowed (the latter casts to object to avoid a deprecated pandas upcast). Also: `vault:true` on a passthrough column rejected at compile; the physical-seam byte-identical sentry now RUNS in CI (fetch-depth:0) with the new guard module in its permitted-non-physical allowlist; a coded error replaces a raw crash on an unrepresentable full-frame value. The new/moved checks were decomposed into `plan/_checks_correctness.py` so `_checks.py` returned under its census ceiling. Gate chain: dennis APPROVE x3 (closed an incomplete-coverage MEDIUM then a bucketize MEDIUM via generalizing the guard); Codex gpt-6-astra cross-model FINAL caught FIVE real issues dennis missed (a CI-red from the new module not being in the sentry allowlist; a nullable-predicate guard bypass; a bucket_perturb compile false-positive; a mixed-output guard escape; a categorical-dtype helper TypeError) - all remediated at root cause, final verdict GO. Tracked follow-up (out of scope, pre-existing): a `when:`-gated NON-string/non-numeric type mix (bool source / decimal output) is not guarded. Engine CHANGELOG [0.14.0-unreleased] + plan `decoy-engine docs/plans/2026-10-22-engine-correctness-when-numeric.md` carry the detail. Follow-on (engine #296, main 62569e28, 2026-10-23): four pre-existing tests that still asserted the old pre-#294 behavior were updated to the new coded-rejection contract and un-redded engine main. Test-only, no production change; every invalid config stays fed-in and still rejected, with stricter exact (exception-type, code) assertions per route (a passthrough-vault fixture was repointed to a maskable strategy so its declined-full-frame/oracle-vault intent survives, with the passthrough rejection keeping dedicated coverage). dennis APPROVE (0 findings) + first-hand anti-laundering verification.

### 2026-10-22 -- OBS admin Storage page (read-only on-disk visibility) MERGED (feat/obs-storage-visibility, FF 307bc32e..f7b05e02)

Admins can now see what fills the disk from inside the app instead of SSHing to the box. `GET /api/admin/storage` (admin-only, non-admin 403) walks the two managed roots (`output_dir`, `upload_dir`) and returns every artifact with its category (output_local / output_remote / upload / staging_dir / chunk / vault / orphan), size + provenance, owning job + status, mtime, a 3-valued `in_use` flag, a `likely_reclaimable` hint, and a non-overlapping local on-disk total; a thin read-only Storage tab renders it. This is the VISIBILITY half of OBS storage reclamation, narrowed to read-only after two gate rounds showed safe on-disk deletion is genuinely hard for every class (live staging writers; a terminal job's output path can be reused by another active job via target_locks; a cancelled job's worker can keep writing). No delete action ships in V1.

The design is fail-safe by construction (the property the gate hammered): `in_use` is FALSE (and a unit only then hinted reclaimable) ONLY on complete, positive evidence (owning job terminal-success/failed AND no active target-lock on the path AND no committing attempt AND past the staging grace window AND resolved ownership); a cancelled-without-exit-evidence job, a terminal-held lock, a truncated walk, a non-ENOENT read error, or unresolved ownership all read UNKNOWN and are never hinted reclaimable; a missing mtime is never FALSE; directory units aggregate descendant evidence. The walk is descriptor-confined (open_root + openat2 `RESOLVE_BENEATH|NO_SYMLINKS|NO_MAGICLINKS` + `fstat`, reusing the merged `api/file_access/jail.py`), bounded (os.scandir + islice, max_names 20000, depth cap), and never resolves a pathname that could escape the roots; a symlinked or swapped directory cannot make it read metadata outside the managed roots. Remote (`s3://`/`gcs://`) outputs are shown but excluded from the local total. Responses carry no file content or raw exception text. Gate chain: dennis GO (1 P2 + 3 LOW remediated); a background security review caught a fail-open that became the fail-safe invariant; Codex gpt-6-astra final GO after 5 rounds that closed real fail-safe edges (realpath root identity, uncapped non-terminal lock query, descendant-evidence aggregation, read-error/truncation -> UNKNOWN, overlapping-root dedup). ruff/format/mypy clean; 44 tests on real Postgres (red-first). DEFERRED to a later worker-quiescence-gated slice: any delete (server-side delete must first prove the worker has exited and no other consumer references the target; the current per-output delete does not check job status), staging-directory reclamation, and remote object cleanup. Retention doc (`docs/security/retention.md`) updated with the visibility surface and the deferred-delete boundary.

### 2026-10-22 -- GEN-API Slice 1a: generation API-key credential-type separation MERGED (feat/genapi-1a-credential-type)

First platform slice of the Generation API, built on the reconciled + Codex-reviewed authorization model (`docs/security/rbac-and-genapi-auth-model.md`). A generation API key is now a DISTINCT credential type, minted with a `tm_gen_` secret prefix (vs platform `tm_key_`) and marked `ApiKey.credential_type='generation'`. It can never authenticate as its owner on the platform: the credential-type gate lives at the single shared auth choke-point, so every platform/admin/mint route (including the `/mcp` bearer-only path and the retrieval + server-log-streaming callers that use `authenticate()` directly) rejects a generation key before any owner lookup, with no cookie fallback even under any auth-scheme casing or RFC 6750 multi-space spacing. Generation auth uses a separate `resolve_generation_key` dependency returning a role-less `GenerationPrincipal` (never a `User`), so it cannot be fed to a platform authorization helper. Minting is session-only (a bearer, even alongside a valid cookie, cannot mint any key) and a generation key additionally requires an admin session; a generation key can never mint anything. Legacy/NULL `credential_type` reads as platform (existing keys unchanged); an unknown value fails closed everywhere. The `tm_gen_` prefix is the load-bearing rollback-safety mechanism: type-unaware/old code (a code-only rollback, an old reader in a mixed deployment) gates on `tm_key_` and so rejects a generation key at the prefix check, never authenticating it as its owner. Additive nullable migration (server default `platform`); downgrade refuses while active generation keys exist. Gate chain: Codex plan-gate GO (after rounds that closed an indirect admin-chain escalation and the code-only-rollback vector); dennis APPROVE (one LOW fixed: scheme case); Codex final GO round 2 (closed two P2: a multi-space bearer bypass and a vacuous NULL test). ruff/format/mypy clean; 37 new tests on real Postgres. There is NO public generation endpoint yet (wired in slice 1f); this slice is inert credential infrastructure. NEXT: slice 1b binds a generation key to a specific `mode=='generate'` job at mint (V1 treats generation jobs as immutable, so the binding keys off the job's frozen snapshot hash with no config-version-bump machinery; revisit under V2 environments).

### 2026-10-22 -- OBS-9b: audit-log retention by redaction (R-simple) MERGED (merge 55b409f8)

Closes the audit half of OBS-9 retention: old audit rows are aged out by BLANKING their data-bearing content fields (before/after/meta/detail) while keeping the row, its order, prev_hash and signature, so the tamper-evidence chain keeps its shape (dennis APPROVE 0-blocker/0-high + Codex gpt-6-astra final GO, on real Postgres). This is the sanctioned alternative to deletion, which is what breaks the chain (QLDB-redaction pattern). The guarantee is R-simple-reduced, Cam's explicit choice: the chain still proves no row was inserted, reordered or deleted, and every non-redacted row stays fully content-authenticated; a redacted row's surviving envelope is no longer chain-re-derivable (the verifier skips its content->signature recompute since the content is gone), so its integrity rests on DB access control. The redaction UPDATE runs as a dedicated non-owner, non-superuser `decoy_audit_purge` role (created NOLOGIN; operator enables it + sets `DECOY_AUDIT_PURGE_DATABASE_URL`) through a role-gated Postgres trigger carve-out that admits only the exact blank+mark shape (pinned by exclusion over every other column) and rejects everything else; a BEFORE INSERT trigger rejects pre-marked rows from any role; DELETE/TRUNCATE stay blocked. Each batch writes one blocking, value-free `audit.redact` event; a failed event rolls the batch back. Admin-only `POST /api/admin/retention/audit-redact` (dry-run count + confirm token; 409 on stale token or broken chain; 503 with no purge URL). The primary runtime-role threat cannot produce a validly-marked row at all. Finding 1 (folded in, commit 55b409f8): the trigger also bakes a fixed 1-day minimum age so even the purge credential cannot first-redact a just-created row at the DB level, defense-in-depth below the Python floor. FAST-FOLLOW tracked: Finding 2 (the verifier should tie a redacted row to the signed `audit.redact` event covering its id range) as its own gated slice; and keeping `audit.redact` events non-redactable so they stay load-bearing proof. Postgres-only controls, like the OBS-6 append-only DDL.

### 2026-10-22 -- DI0: distribution-integrity current-state contract + honest capability statement MERGED (merge 45e0eee4)

First slice of the distribution-integrity program (whose program plan, Codex plan-gate GO, also landed 2026-10-22). Tests + docs only, no production change (dennis GO + Codex gpt-6-astra final GO). It freezes, as a characterization contract, what the existing quality primitives produce TODAY so later slices (DI1 measure, DI2 persist) extend a known baseline: the engine GOF metrics (KS `ks_complement_binned_cdf` binned-CDF + point-mass reporting 1-D; chi-square `chi_square_common_partition_cramers_v` top-K/other reporting 1 - Cramer's V, no p-value; both additive in `marginal.columns[*].extra_metrics`, not folded into overall_score), the platform QualityReport shape, and the `/quality` + `/quality/details` payloads (details filters raw-bearing fields; `labels=raw` gated on `storm.read_samples`, 403 fail-closed). It pins the real today-behavior honestly: the hook returns None on skip/error (no persisted distinct failed/skipped/partial state -- recorded as a DI2 gap, not papered over), matched-same-table source/target pairing, bounded seeded reservoir sampling keyed on the job id. Two primitive findings are PINNED as-is and routed to DI1 (not silently fixed): F-DI0-1 chi-square returns `insufficient_identifiable_support` on maximal categorical drift (disjoint label sets) and on a constant-identical column (primary TVD still scores both correctly, so the headline grade is not corrupted); F-DI0-2 nested per-column GOF unavailability does not propagate to report-level omissions. The honest capability statement (`docs/backlog/distribution-integrity/honest-capability-statement.md`) states the qualified allowed claim ("measure and explain how much analytic shape a mask job preserved", scoped to supported coverage, report-only) and the forbidden claims (no DP, no synthetic-privacy certification, no "more similar == more private", no enforcement wording until DI4); contradictory in-repo copy was corrected in-slice (api-surface.md two factual errors, release-1-known-limits.md, the shuffle line), with three production/UI-string overclaims listed as deferred blockers. The golden contract is backed by semantic assertions (the Codex final gate caught + got fixed two vacuous tests first: the same-table pairing now fails if source selection regresses, the sampling test now distinguishes reservoir+job-id-seeding from a head-sample/fixed-seed), and the DB-semantic tests are wired into the backend-postgres CI leg.

### 2026-10-21 -- AUDIT-2: best-effort audit for 17 operational endpoints + writer hardening MERGED (merge 1d19d3c7)

Closes the operationally-meaningful audit-coverage gaps (dennis APPROVE 0-above-LOW + Codex gpt-6-astra plan-gate GO and final GO). Best-effort audit rows (post-commit, non-raising) now cover storm scan/report/batch lifecycle (10 actions), environments CRUD + variables (5), and pipeline variables (2). Secret-safety is the core contract: no row carries a data value or secret. The environment-variable row logs only `{name, sensitive}` (the key is `sensitive`, not `is_secret`, because the audit value-scrubber drops any meta key matching `/secret/`, which would silently strip the flag); pipeline-variable logs only `{name}` (never `default_value`); report-note and upload-error free-text are never logged; every storm detail string is plain scalar identifiers. A root-cause hardening (caught by the Codex plan-gate) makes `write_audit_best_effort` genuinely non-raising: its rollback, metrics, and logging cleanup plus the trailing success metric are each guarded with `except Exception` (so KeyboardInterrupt/SystemExit still propagate), so a post-commit audit failure can never turn a 200 into a 500; the blocking `write_audit` is unchanged and still re-raises for AUDIT-1's atomicity. New `environment` + `pipeline_variable` audit domains; registry 111 -> 128 actions, 29 -> 31 domains. The endpoint-coverage ratchet moved 17 routes known-gap -> audited (EXPECTED_KNOWN_GAPS 20 -> 3). The 3 remaining are deliberate documented non-gaps: dev-fixtures seed/wipe (dev-only tool, not a production surface) and PATCH /api/me/preferences (per-user UI preference). This completes the audit-coverage program: every production state change is now audited or deliberately exempted, enforced by the structural guard.

### 2026-10-21 -- AUDIT-1: blocking audit for unmask reveal + review approve/reject MERGED (merge 679a77c2)

Closes all three cam-deferred audit gaps (dennis APPROVE 0-above-LOW + Codex gpt-6-astra cross-model final GO). The three most sensitive mutations now write a blocking, security-critical audit row. `unmask.reveal`: de-pseudonymization is the most sensitive read in the product, so the reveal is audited BEFORE the response is built; if the audit infrastructure is down, `write_audit` re-raises and the handler 500s, so revealed values never reach the client untraced. The row carries only schema-level facts (table, row count, vault job id, per-column `{column, strategy, status}` verdict) and never a revealed value, the masked input, or the seed; the engine's `status`/`strategy` are fixed label vocabularies, not data. `review.approve` / `review.reject`: a release-gate decision overrides the privacy block, so `write_audit` replaces the handler commit and the decision, job-status flip, and audit row commit in one transaction; a failed audit rolls the decision (and the flip) back and re-raises. New `review` + `unmask` audit domains; registry 108 -> 111 actions, 27 -> 29 domains; the three actions added to SECURITY_CRITICAL (classification enforced by the writer-per-action guard). The endpoint-coverage ratchet moved the three routes from cam-deferred to audited (EXPECTED_CAM_DEFERRED 3 -> 0). Acceptance tests prove no revealed plaintext reaches the log, audit-down leaks no values to the client, and a failed audit rolls back both the review decision and the job-status flip. Remaining audit work is the 20 known-gap routes (audit-vs-exempt judgment calls).

### 2026-10-21 -- Audit coverage batch 3: workflow + folder CRUD MERGED (merge f9f07907)

Closes the last unambiguous audit-worthy gaps from the coverage survey (dennis GO + Fable cross-model final GO, 0 above LOW). Best-effort audit coverage, mirroring the already-audited `pipeline.*`/`projects.*` patterns, for `workflow.create/update/revert/move/run` and `folder.create/update/delete`. Each writes after the business commit and after every rejection check (404/403/409/503), so a rejected request writes no row; `workflow.run` audits only after the WorkflowRun commits (the release flag 503s it with no row). No coupling defect (version-history snapshot/_prune commit before the best-effort audit, so an audit rollback can't drop a row); no secret in any row (meta carries only name/ids/flags; a planted secret in the description never reaches a row). New `workflow` + `folder` audit domains; registry 100 -> 108 actions, 25 -> 27 domains. The endpoint-coverage guard ratchet moved these 8 routes from known-gap to audited (EXPECTED_KNOWN_GAPS 28 -> 20). logging.md's workflow/folder audit-shape table (a richer target) annotated with the minimal shape actually shipped. This completes the clear-value audit-coverage work; the remaining 20 known-gaps are audit-vs-exempt judgment calls (storm analysis artifacts, dev-fixtures, /me/preferences, pipeline-variable, feature-flagged-off environments) + 3 cam-deferred (unmask.reveal, review approve/reject, env secrets), all tracked on the guard ratchet for Cam's prioritization.

### 2026-10-21 -- Audit coverage batch 2: job purge + notification-rule CRUD MERGED (merge dbb8563c)

Closes the security-meaningful subset of the 32 tracked audit-coverage gaps (dennis GO + Fable cross-model final GO). **job.purge** (blocking): the admin `POST /api/admin/purge-jobs` endpoint deleted jobs with no audit row; now audited with the deleted count + mode + value. It is non-atomic by documented design (`_apply_retention` commits internally and is shared with the settings-save path, so it was not restructured), but it fails loud: a failed audit 500s with the deletion already applied, never a silent unlogged purge; the settings-save path still records only `settings.update` (no `job.purge`), so there is no double/mislabeled audit. **notification_rule.create/update/delete** (best-effort): config controlling where job failure/quality data egresses was unaudited; now audited, with the channel target redacted to `scheme://host` by URL SHAPE (not `channel_kind`) so a Slack/webhook bearer path can never reach the row -- a Fable-flagged bypass (a PATCH mislabeling a URL rule as `email`) was fixed to key on the parsed scheme, since this redaction is the sole defense (the audit value scrubber does not mask URL paths); `condition_args` is never logged. New `notification_rule` audit domain; registry 96 -> 100 actions, 24 -> 25 domains. The structural endpoint-coverage guard ratchet moved these 4 routes from known-gap to audited (EXPECTED_KNOWN_GAPS 32 -> 28). Remaining tracked gaps (28, lower-value ordinary CRUD: workflow/folder/pipeline-variable, storm analysis artifacts, dev-fixtures, /me/preferences, feature-flagged-off environments) + the 3 cam-deferred (unmask.reveal, review approve/reject) stay on the guard's ratchet for prioritization.

### 2026-10-21 -- Structural audit endpoint-coverage guard (test-only) MERGED (merge 05381813)

The survey's top structural recommendation, and the fix for the root cause of every coverage gap found this session: the existing guards check that known actions use the right writer, but nothing checked endpoint coverage, so an endpoint calling no audit writer was invisible. `tests/test_audit_endpoint_coverage.py` enumerates every mutating route (POST/PUT/PATCH/DELETE) from the live app and forces each into an explicit classification (audited / exempt-read-or-preview / exempt-transitive / known-gap / cam-deferred); a new or stale mutating route fails the test until consciously classified, so an unaudited endpoint can never again silently ship. It pins EXPECTED_KNOWN_GAPS=32 / EXPECTED_CAM_DEFERRED=3 as a ratchet (closing a gap moves it to audited and lowers the count). The classification is an in-code inventory of the remaining coverage work: 147 mutating routes = 89 audited, 16 exempt-read/preview, 7 exempt-transitive, 32 known-gap, 3 cam-deferred. dennis gave an exhaustive honesty pass (every exempt_* genuinely persists nothing or is transitively audited; all 35 gaps are real unaudited mutations; the enumeration reconciles). The inventory also caught gaps beyond the earlier survey, notably POST /api/admin/purge-jobs deleting jobs with no audit row. Test-only; no api/ behavior change. The 32 known-gaps (MEDIUM additive-coverage adds) + 3 cam-deferred (unmask.reveal, review approve/reject) are the backlog for the audit-coverage-completion program, now tracked with a failing-on-regression ratchet.

### 2026-10-21 -- Audit coverage: failed logins + webhook secret lifecycle (HIGH gaps) MERGED (merge f5eb0ac9)

A systematic audit-coverage completeness survey (reading every state-changing endpoint against what the tamper-evident log should capture) found the root cause of gaps like the earlier group-RBAC miss: the audit guards check that KNOWN actions use the right writer, but nothing checks endpoint COVERAGE, so an endpoint with no audit call at all is invisible to them. Seven mutating routers emit no audit row; this slice closes the two HIGH ones (dennis GO + Fable cross-model final GO). **auth.login_failed** (best-effort): failed logins (bad password, disabled account, seat-limit) were unlogged, so brute-force / credential-stuffing left no forensic trace; now audited, with a best-effort write so a lost audit never turns a clean 401/403 into a 500. An automated security review caught that the first cut wrote the raw, unvalidated, unbounded submitted email into the verbatim `detail` field (log-injection / unbounded write); fixed to record a length-bounded `attempted_email` in the scrubbed `meta` with a fixed `reason` code, and `user_id` only when the email matched (the password never reaches the row). **webhook.create/rotate/deactivate** (blocking): the inbound-trigger HMAC secret lifecycle was untraceable; now audited atomically (a failed audit rolls the rotation back), with no plaintext/encrypted secret or HMAC in the row (meta carries only the webhook id). New `webhook` audit domain; registry 92 -> 96 actions, 23 -> 24 domains; 9 new tests; the 3 webhook actions pinned blocking in the writer-classification guard. INFO flagged for Cam: `/api/auth/login` has no rate limiter, so each failed attempt now also does a chained audit insert under the global audit-chain lock (the intended always-log-failures trade; revisit if login throttling is added). REMAINING audit-coverage-completion work (flagged for Cam, survey is the report): the MEDIUM additive adds (workflow / folder / notification-rule / storm.scan.delete + column_override / pipeline-variable), a high-leverage structural endpoint-coverage guard test (enumerate every mutating route; assert each audits or is allowlisted), and the Cam-gated items -- unmask.reveal (the single most sensitive operation, currently unlogged; recommend blocking the reveal on the audit), review approve/reject (release-gate override; recommend blocking + SECURITY_CRITICAL), and environment-variable/secret auditing (only reachable if DECOY_ENABLE_ENVIRONMENTS is flipped, off at GA).

### 2026-10-21 -- Audit coverage + retention hardening (from a cross-cutting security review) MERGED (merge d341ae79)

After the OBS-7/9a work shipped, a report-only cross-cutting security review of the whole audit/retention/job-authz subsystem (looking for interaction bugs the per-slice gates could not see) surfaced four issues, all fixed here (dennis GO + Fable cross-model final GO, 0 findings). **HIGH:** the group->project RBAC endpoints (add/remove group member, grant/revoke group project access) wrote no audit row, so the central access-control action in the single-org RBAC model was invisible in the tamper-evident log; all four now write a blocking, atomic audit row (new actions `groups.member_add`/`member_remove`/`project_grant`/`project_revoke`; a failed audit rolls the membership/grant change back), registry 88 -> 92. **MEDIUM:** `job.admission_force_run` (a privileged admission/OOM-gate override) was audited best-effort while the comparable job-cancel was blocking; now blocking, so a lost audit rolls the override back. **MEDIUM:** a settings PATCH touching only the (unenforced) `audit_retention_days` field still triggered the job-row retention purge as a side effect; scoped so the purge runs only when a job-retention field is patched (removes a surprise deletion, adds none). **LOW:** the operator `audit_retention_floor_days` env field was capped `le=36_500` so the retention-preview timedelta cannot overflow. 12 new RBAC-coverage tests; the new blocking actions are pinned in the writer-classification guard. The review also produced strong clean negatives: the job-BOLA class is fully closed, the audit append-only invariant is never violated by the new read/export path, retention never mutates audit rows, export leak hygiene and secret scrubbing hold, and the chain verifier fails closed. (The HIGH was pre-existing, not a regression; it belongs on the pre-GA security list and is now closed.)

### 2026-10-21 -- Security: close the job-BOLA class (cancel + telemetry reads) MERGED (merges 8b32122e, 64112619)

Surfaced during OBS-7d (when job.cancel got audit coverage, its missing ownership check became visible). Two small fixes, each dennis-reviewed (OWASP API1:2023 Broken Object Level Authorization). (1) `POST /api/jobs/{id}/cancel` used the unchecked `_require_job`, so any authenticated user could cancel any non-sealed job; now routed through `require_job_owner_or_404` (owner-or-admin, 404 otherwise), the choke-point the other job sub-routes already use. (2) The six job runtime-facts GET reads (node-runs, steps, throughput, lineage, fidelity, quarantines) read another user's job telemetry without an owner check (`node-runs` inline, the other five via `_require_job`); all six now route through the same choke-point. Non-owner non-admin gets 404 (existence hidden); owner and admin unchanged. Tests: the cancel 3-case plus a parametrized 6-endpoint x 3-principal telemetry suite; cancel-guard and companion suites green. `force_run_job` was confirmed admin-gated (not a BOLA). Both pre-existing, not regressions; fixed under tech-lead authority as security follow-ups while the OBS program ran.

### 2026-10-21 -- Observability OBS-9a: retention-admin foundation (non-destructive) MERGED (merge 4366c175)

The read/configure half of retention policy, plus a hardening of the settings surface a companion admin-controls survey found weak. Plan `docs/plans/2026-10-21-obs-9-retention-admin.md` (rev 1.2, Fable plan-gate GO). NON-DESTRUCTIVE: it adds no path that deletes any log. `SettingsPatch` now validates (job_retention_mode is an enum; job_retention_value/version_retention_count/audit_retention_days are bounded, with 100-year day caps so the preview's timedelta cannot overflow) where before a typo silently disabled job pruning. Every settings change is now audited as a single blocking `settings.update` row written atomically with the change (a failed audit rolls the change back), recorded in the signed before/after and secret-safe (the SMTP password is captured only as a boolean "is one set"); previously only `ml_enabled` was audited. `audit_retention_days` (gated field-only in OBS-6c) is now admin-editable above an operator-set floor `DECOY_AUDIT_RETENTION_FLOOR_DAYS`, and GET /api/admin/settings exposes read-only `audit_retention_floor_days`, `audit_retention_effective_days` (= max(stored, floor)), and `audit_retention_enforced` (false, honest: nothing purges yet). A dry-run `GET /api/admin/retention/preview` returns per-stream counts of what WOULD be purged, sharing the exact candidate query with `_apply_retention` so the preview matches the purge, and deletes nothing. `GET /settings` now tolerates a legacy invalid stored mode instead of 500ing. The admin-controls survey (Cam's task) ran read-only and is folded into the plan: a KEEP-ENV boundary (fences, path roots, launcher/scheduler security, DoS caps stay env-only) and promote-candidates (admission/preview/retrieval toggles, a read-only capacity panel). docs/security/retention.md was corrected (job default is keep_all; version pruning is write-time; the server-log janitor reclaims only dead-writer files; the evidence manifest's output_retention_days=30 is advertised but unenforced). This slice also REMEDIATED a red main left by OBS-7: `audit.export` and `job.cancel` use the blocking audit writer by design but were never added to the writer-classification guard in test_obs5_migrate_atomic.py (my per-sub-slice OBS-7 gates did not run that test); classifying them restored green. Gates: dennis GO + Fable cross-model final GO (Codex was down overnight), both re-ran the suites (80 passed) and confirmed non-destructive/atomic/secret-safe and that the remediation pins the contract rather than weakening a test. HELD FOR CAM: OBS-9b, the destructive retention purge. The audit-log purge must deliberately lift the OBS-6a append-only trigger (which blocks DELETE for every role including superuser), which materially weakens the OBS-6 tamper-evidence guarantee, so it needs an explicit sign-off and a design decision (a checkpoint chain design is the only viable one; re-anchoring hashes is impossible because the hash signs its own prev_hash). The server-log/job auto-janitor and upload/output sweep are the other 9b pieces. NEXT: OBS-9b on Cam's sign-off; then the terminal §AUDIT review.

### 2026-10-21 -- Observability OBS-7: audit reader/export surface + coverage close-out MERGED (4 sub-slices)

The read side of the audit trail, so an operator can inspect and export the tamper-evident log that OBS-5/6 built. Backend only; the reporting UI is the frontend lane. Plan `docs/plans/2026-10-21-obs-7-audit-reader-export.md` (rev 2.1; plan-gated through two cross-model rounds). Shipped in four independently gated sub-slices: **7a** (`9ee21cd6`) a single-event detail endpoint `GET /api/audit/{id}` returning the full signed field set plus forensic session/ip/user-agent, list-filter expansion (equality filters on actor/resource_type/resource_id/outcome/request_id, an escaped action prefix so `%`/`_` are literal, and a deterministic created_at+id ordering), and five additive `AuditEntryOut` fields; **7b** (`92669aa1`) `GET /api/audit/aggregations` (event counts per UTC time bucket and domain, bounded to a default 30-day window and a max bucket count) and `GET /api/audit/top-actors`, with UTC-correct bucketing proven on both SQLite and Postgres (a live-PG test under a Pacific/Auckland session timezone), plus a lower bound on the list `limit`; **7c** (`4478fd85`) `POST /api/audit/export` (CSV and JSON of human-facing columns only, no signed or secret columns, a 50k row cap, CSV formula-injection neutralization) that audits itself as the new `audit.export` action transactionally, so an unrecordable export fails rather than leaking untraced data; **7d** (`8126f4c2`) audit coverage for `job.cancel` (committed atomically with the cancel) and a UTC normalization of the list/export date filters. Every event is attributed by the authoritative signed `actor` from OBS-6a, never a live join, so an api-key-initiated action is now distinguishable at the API (the frontend "(system)" placeholder can be replaced by consuming `actor`). Decisions were made under Cam's tech-lead authority (export columns/cap, admin-only for V1, block self-audit, the coverage set). Gates: every sub-slice passed a dennis adversarial review and a Fable cross-model final review (Codex was not emitting verdicts overnight, so Fable was the cross-model gate per policy); all sub-slice tests green on SQLite with a live-Postgres leg for the dialect-sensitive bucketing. Registered-action count 86 -> 88 (`audit.export`, `job.cancel`). FLAGS surfaced for a follow-up (pre-existing, not OBS-7 regressions): `POST /api/jobs/{id}/cancel` has no ownership check (any authenticated user can cancel any non-sealed job); `schedule.update` audits best-effort rather than atomically; OBS-6a's `user_email` field carries `str(user.id)` rather than an email. NEXT: OBS-9 (retention-policy admin editing + bounded purge + admin-controls audit).

### 2026-10-21 -- DuckDB database input, Slice 3 (customer reference doc) MERGED (merge af5788ef)

The closing slice of the v1 PostgreSQL database-input feature (roadmap INTEROP I3). Docs only, no code change. Adds `docs/reference/database-input.md`, a customer/operator reference for the two-step flow: the operator deploy-config setup (`DECOY_POSTGRES_ALLOWED_REFS` allowlist where each ref names an env var holding a JSON connection bundle, plus `DECOY_DUCKDB_EXTENSION_DIR`), then the three in-app steps (register a `postgres` cloud account and test it, pull selected relations to Parquet datasets via `POST /api/files/from-postgres`, mask the datasets as ordinary files). Documents the closed-selection rules (identifier regex, columns/order_by constraints), the caps (16 relations, 256 columns, 180s deadline, concurrency 2, 10 GiB/file), the full error-code to HTTP-status contract, the disconnect-does-not-cancel caveat, the `file.pull.postgres` audit behavior, and the leak-safety and operator-fence posture. Indexed in the reference README and cross-linked from files.md. Every claim was verified against `api/files/pg_pull_router.py`, `pg_pull.py`, `cloud/pg_fence.py`, and `cloud/accounts.py`. Gate: dennis ran the accuracy audit as the acting gate (the Codex cross-model gate tool was not emitting verdicts tonight, see note); it found 1 HIGH (the bundle-failure error row named `pg_bundle_*` at 403 when the pull endpoint actually returns `pg_pull_bundle_unset`/`pg_pull_bundle_malformed` at 502) plus 2 LOW, all fixed and re-verified first-hand against the code before merge. The v1 Postgres database-input flow is now complete end to end. NEXT in the DuckDB program: the audit/UI presentation polish (frontend lane, ties into OBS-7 actor display); input/output expansion stays in §PREGA.

### 2026-10-21 -- Observability OBS-6c: gated audit-retention field MERGED

Adds `AppSettings.audit_retention_days` (default 2555, about 7 years) to record the intended audit-log retention window. It is a FIELD ONLY by design: nothing purges, archives, or sweeps on it, and the admin settings PATCH (`SettingsPatch`) cannot edit it, so the value cannot yet be changed through any API. OBS-9 owns the editing surface and any destructive purge. The migration `obs6c_audit_retention` adds the column NOT NULL with `server_default="2555"` so the existing settings singleton backfills on both Postgres and SQLite, and the model carries the matching `server_default` so a fresh upgrade stays schema-identical (empty autogenerate diff); downgrade drops the column. Single migration head. `docs/security/retention.md` states the honest posture: audit logs are retained indefinitely until OBS-9 regardless of this value, so a deployment with a strict window should not claim compliance on the field alone. For proportionality (a trivial additive gated field) this ran the Codex cross-model gate only, skipping a separate dennis pass. Gate: Codex (gpt-6-astra) GO with no findings, confirming the field cannot be mutated through any route, nothing reads it, both databases backfill and enforce NOT NULL, and the docs do not overclaim; 31 tests passed including real-Postgres parity and migration round trips. NEXT: OBS-7 (audit reader/export; switches the reporting UI and exports to the signed `actor`, api-key actions show "(system)" until then).

### 2026-10-21 -- DuckDB database input, Slice 2 (pull a Postgres account's relations to a dataset) MERGED (merge 062da7a4)

The platform acquisition half of the DuckDB Postgres database-input feature (roadmap INTEROP I3; Option C "pull to a dataset, then mask as files", chosen over an integrated one-click to avoid admission/scheduler surgery). New admin-only endpoint `POST /api/files/from-postgres` takes `{account_id, relations:[{schema,table,columns,order_by}]}`, snapshots each selected relation from a fenced managed Postgres `CloudAccount` (Slice 1) to Parquet via the engine's `snapshot_tables_to_parquet` primitive (decoy-engine 0.11.0, released for this), and registers one `UploadedFile` per relation so the existing file-masking path runs unchanged (the masking job sees a normal Parquet). The request is a CLOSED structured selection (identifier regex matching the engine's, no raw SQL/WHERE/`*`, order_by a subset of columns, relation/column caps); the DSN is assembled from the fenced bundle and passed to a bounded `python -I` child over stdin only, never in argv/env/logs/audit/response/traceback. Bounds: 180s deadline with kill+reap, RLIMIT_FSIZE single-file cap (strictly positive, fail-closed), in-process concurrency cap, private per-request staging root (mode 700) resolved to an absolute path, offline extension load from an operator-trusted directory. Registration is atomic: stream SHA-256, promote each file, add+flush+commit once; a pre-commit failure rolls back and removes every promoted file (robust to a failing rollback), and a commit failure keeps the files rather than risk deleting one a durable row references (a rolled-back commit leaves a reclaimable orphan, never a dangling row). Every pre-acquisition rejection (fence, wrong provider, unknown account, untrusted extension, staging failure) is audited value-free as `file.pull.postgres`. Gates: dennis APPROVE/GO (0 blocker/0 high; 1 medium + 1 low fixed); Codex final GO after 3 rounds (round 1 caught a lost-commit-ack file deletion HIGH + relative-upload-dir + cleanup-traceback-leak + zero-cap; round 2 caught a TOCTOU in the first HIGH fix; round 3 clean), each fixed at root cause with real-Postgres fault-injection regressions. 76 Slice-2 tests plus the engine-ownership and actions-guard suites green on SQLite and real Postgres; registered-action count now 85. FOLLOW-UP: an upload-orphan sweep to reclaim Parquet left by a rolled-back commit (bounded disk cost, no dangling row). NEXT: Slice 3 (customer docs for the two-step DB-input flow + audit/UI presentation polish).

### 2026-10-20 -- DuckDB database input, Slice 1 (platform managed Postgres account + operator fence) MERGED (merge cc318b55)

The platform half of the DuckDB Postgres database-input feature (roadmap INTEROP I3, after engine Slice 0). An operator can register a PostgreSQL database as a managed `CloudAccount` (new `CloudProvider.postgres`) reusing the existing cloud-account surface, create/list/test it, with the connection resolving to a bundle the later staging slice consumes. No data is read or masked yet (Slice 2). The trust boundary is a CONFIG-BASED operator fence, not a permission flag (the in-app permission system admin-bypasses, so a permission cannot restrain an admin): a deploy-config allowlist (`DECOY_POSTGRES_ALLOWED_REFS`) of permitted `credentials_ref` values, not app-mutable, re-read on every resolve/probe and enforced fail-closed at use time, so an admin can create a postgres account but it is unusable unless its ref is operator-allowlisted, and a ref revoked after creation stops resolving. Any API-supplied DSN/connection field/endpoint override is rejected value-free (422); the DSN/host/user/password never appears in a row, log, metric label, response, or exception. The connectivity probe runs in a short-lived child process the parent SIGKILLs at a hard deadline (a stuck thread cannot be killed and psycopg's cancel() blocks), with the bundle passed over stdin only and a minimal child environment so the operator credential-bundle env vars are not inherited. Migration `ds1_cloudprovider_postgres` adds the enum value (Postgres `ADD VALUE` in an autocommit block, retry-safe; downgrade refuses with postgres rows present), re-parented onto `obs5b_audit_user_fk` at the OBS-5-migrate-B merge to keep a single linear head. Gates: dennis GO (0 blocker/high; 1 medium + 2 low fixed); Codex final GO after 3 rounds (round 1 caught two HIGH credential-leak paths and a deadline defeat; round 2 caught a HIGH regression the first fix introduced plus env inheritance; round 3 clean), each finding fixed at root cause with leak-sentinel + post-auth-stall + child-environ regressions. 80+ account tests and the migration chain green on SQLite and real Postgres. NEXT (platform): Slice 2 (staging + acquisition-in-preflight), which pins an engine release containing the Slice 0 primitive; then Slice 3 (audit event + docs).

### 2026-10-21 -- Observability OBS-6b: audit chain verifier + integrity endpoint MERGED (merge 914d17fd)

The detection half of audit tamper-evidence, coupled with OBS-6a's chain. Two new tables
(`audit_chain_status` singleton + `audit_chain_gaps`) and a verifier (`api/audit/verifier.py`) that
walks `audit_entries` in id order, recomputing each row's signature only through the frozen
`api/audit/chain.py` and checking two things: a `signature_mismatch` (recomputed != stored, detected at
that row, including a row whose stored fields cannot even be decoded) and a `prev_hash_mismatch` (a
row's stored prev_hash != the prior row's stored signature, catching a deleted/inserted/reordered row).
It runs hourly on a bounded high-water snapshot and on demand via admin `POST /api/audit/integrity/verify`
(202, background); `GET /api/audit/integrity` returns the verdict (never_verified/ok/stale/broken +
green/red indicator + the untrusted-from boundary), with no row contents. A break sets `chain_ok=false`,
logs CRITICAL with ids and counts only, and never halts the app; each run writes one chained
`audit.integrity_check` row. Gaps are sticky (a later clean read cannot silently turn the badge green);
the untrusted region starts at a monotonic `earliest_break_id` that survives the 10k gap cap. Overlap is
handled by a process-local lock plus a Postgres advisory lock on a key distinct from the chain writer's,
so verification never blocks audit writes. Leak hygiene held across the hardest paths the gate probed:
a corrupt row (SQLite non-timestamp, Postgres out-of-range year raising DataError, deep JSON raising
RecursionError) is recorded as a signature mismatch per row with no value-bearing exception escaping;
and a hostile session DateStyle (`SQL, DMY`) is neutralized by pinning `SET LOCAL DateStyle 'ISO, YMD'`
for the verify transaction and the snapshot read. Shutdown is cooperative: the walk polls a stop flag
between batches and the scheduler awaits the in-flight thread so it closes its session rather than being
orphaned. Gates: dennis APPROVE/GO (0 blocker/0 high; LOW fixes applied) then Codex final GO after FOUR
rounds (r1 HIGH decode-leak + relative-dir + cleanup-traceback + zero-cap, r2 HIGH PG out-of-range
DataError + gap-cap boundary + unclean shutdown, r3 MEDIUM non-ISO DateStyle, r4 clean), each fixed at
root cause with real-Postgres regressions. Verifier suite 25 + migration/parity/registry checks green on
SQLite and real Postgres; registered-action count now 86 (new `audit` domain + `audit.integrity_check`).
DOCUMENTED LIMIT: suffix-truncation or a privileged whole-chain rewrite (the chain is unkeyed SHA-256;
append-only DB protection, not secrecy, stops a runtime-role rewrite) needs an external anchor (Slice H).
FOLLOW-UP: a long full re-walk at the ~100M-row cap holds one read transaction (future chunked-commit /
cheaper incremental signal); no operator gap-clear surface yet (OBS-7/OBS-9). NEXT: OBS-6c (gated
`audit_retention_days` field).

### 2026-10-21 -- Observability OBS-6a: audit hash chain + append-only + reset-survives MERGED (merge 54280204)

The tamper-EVIDENCE core of the audit log (first of OBS-6's three sub-slices). Every audit row now carries a SHA-256 signature chaining it to the prior row: the signature covers a frozen signed-field set (now including the legacy `detail` and `source` columns) canonicalized with RFC 8785 JCS plus an integer-preserving extension (exact decimal for integers beyond 2^53; a vendored ECMA-262 float serializer validated against Node over ~100k doubles). The chain is computed in the same transaction as the insert under one global advisory lock, so concurrent writers produce a single unbroken chain. On Postgres (production) `audit_entries` is append-only at the database level: `REVOKE UPDATE/DELETE/TRUNCATE` from PUBLIC and the runtime role, plus a BEFORE UPDATE/DELETE row trigger and a separate BEFORE TRUNCATE statement trigger, so not even the app's own database role can alter or delete an audit row (verified as a real non-superuser role); SQLite (dev/test) skips the DDL. `reset_instance` no longer wipes the audit log and records its own chained `admin.reset_instance` row inside the reset transaction. Per Cam's decision (D), `audit_entries.user_id` became an immutable snapshot (the OBS-5-migrate-B `ON DELETE SET NULL` FK dropped), so deleting a user leaves audit rows untouched and the signature stable; the signed `actor` field is the authoritative attribution (the reader now exposes it; the live-join that could misattribute after an id reuse was removed). The one-transaction migration widens the id to BigInteger, validates-or-backfills the chain with a self-consistent-fork check, sets the chain columns NOT NULL + a unique signature, and refuses downgrade while a deleted user's id is still a snapshot. Gates: dennis GO-WITH-CHANGES (0 blocker/0 high after the attribution HIGH was fixed; anti-laundering checks reproduced the pre-existing failures on the clean base and confirmed the conftest test-harness trigger-bypass does not weaken production); Codex final GO after 2 rounds (closed the live-join misattribution, fixed the backup/restore drill's unsigned-insert, added actor-authoritative reader regressions). 200+ tests green on SQLite and real Postgres. DEFERRED to OBS-7 (audit reader/export): the audit REPORTING UI + exports should display the signed `actor` (api-key-initiated actions currently show "(system)" there; the authoritative value is in the API). NEXT: OBS-6b (the scheduled + on-demand chain verifier + `audit_chain_status`/`gaps` + `GET /api/audit/integrity`), then OBS-6c (the gated retention field).

### 2026-10-20 -- Observability OBS-5-migrate sub-slice B: audit-actor FK ON DELETE SET NULL MERGED (merge cd590683)

Completes OBS-5-migrate (after sub-slice A). Deleting a user now keeps that user's audit history: the `audit_entries.user_id` foreign key becomes `ON DELETE SET NULL` (with `passive_deletes=True` so the database does the orphaning, not an ORM update sweep), so a deleted user's audit rows survive with `user_id` NULL and the `actor` string from the foundation keeps attribution, instead of the delete failing on the foreign key or the history being erased. SQLite foreign-key enforcement is turned on per connection (`PRAGMA foreign_keys=ON` on the real app engine) so the rule actually fires on the dev/test backend; Postgres (the production backend) enforced it all along. The Alembic migration (`obs5b_audit_user_fk` on `obs5f_audit_schema`, single head) preflights for pre-existing dangling `user_id` values and refuses before any change (no silent repair), recreates the FK with SET NULL (SQLite batch recreate with a naming convention to drop the baseline's unnamed FK; Postgres inspector drop/add), preserves all columns and indexes, and is reversible; the SQLite rebuild drops any stranded `_alembic_tmp_audit_entries` first so a failed attempt is retry-safe. Gates: dennis GO (0 blocker/high/medium; dennis verified the one unrelated test failure is pre-existing on main, a run-owner log-message defect, not this slice's PRAGMA listener); Codex final GO after 2 rounds (one MEDIUM: the SQLite rebuild was not retry-safe after a mid-migration failure; fixed + regression). 14 migration tests green on SQLite and real Postgres. NEXT: OBS-6 (hash chain + append-only + retention), coupled with migrate.

### 2026-10-20 -- Observability OBS-5-migrate sub-slice A: atomic audit for security-critical actions MERGED (merge 94a818d2)

The transaction-semantics migration of the audit write path (the second OBS-5 sub-slice after foundation). Security-critical actions (encryption keys and seed material, API keys, permission flags, users and roles, cloud credentials, SSO identity link/provision, login session) now write their audit row inside the SAME database transaction as the action itself: the row is staged, the business change is flushed, the audit write runs as a blocking call, and only then does the request commit. If the audit write fails, the action rolls back, so a security-critical change can never land without its audit trail, and no key or token is released before the row is durable. Everything else is best-effort through a new `write_audit_best_effort`: the business change commits first, then the audit is written in its own transaction and a failure is swallowed so it cannot poison the response. The scheduler probe canary was downgraded from atomic to best-effort (business commit first); the two filesystem side-effect sites (key restore, job-output delete) record an `attempted` audit row before the irreversible unlink/restore; `password_reset_request` stays best-effort and keeps its enumeration-safe 200. Gates: dennis GO (0 blocker / 0 high; the full-suite stall did not reproduce across ~1850 tests and is environmental, not from this slice); Codex final GO after 2 rounds (one MEDIUM: the two new best-effort-failure diagnostic fields were not registered in the logging-extras value contract, so both formatters silently dropped them and the obs3 extra-key sentry failed; fixed at root cause by registering `audit_action` + `audit_error_type` with the identifier contract plus formatter and end-to-end leak regressions). The same work cleared a pre-existing log-interpolation sentry red in `metrics._note_failure` (unrelated to the slice, red on main). Local suites green (migrate, foundation, writer, obs3 leak + interpolation sentry, metrics). NEXT: OBS-5-migrate sub-slice B (FK `ON DELETE SET NULL` for the audit actor + SQLite FK-enforcement PRAGMA + dangling-ref preflight), then OBS-6 (hash chain + append-only + retention), coupled.

### 2026-10-20 -- DuckDB database input, Slice 0 (engine primitive) MERGED (decoy-engine PR #291, merge d4517f4f)

The engine half of the DuckDB-backed Postgres database-input feature (roadmap INTEROP I3). New `decoy_engine.connectors.postgres_snapshot`: a read-only, structured-selection snapshot-to-Parquet primitive over DuckDB's postgres scanner. One ATTACH + one transaction (multi-table one-snapshot consistency proven on DuckDB 1.5.6), atomic publish + cleanup, identifier-safe (no raw SQL), DSN never persisted, offline extension load, preserve-or-reject type-fidelity guards, case-collision rejection. Unused by the engine itself; the platform wires it as a managed DB source in later slices. Gates: dennis GO; Codex final GO after 3 rounds (two real silent-wrong-data HIGHs caught + fixed: case-colliding columns and array lower-bound loss); local CI green (ruff/format/mypy, 115 tests incl. docker-Postgres integration). Decisions (Cam 2026-10-20): v1 = Postgres snapshot, column projection only, platform-tier (CLI stays local-files). NEXT (platform): Slice 1 (CloudProvider.postgres + managed account + operator fence) -> Slice 2 (staging + acquisition in preflight) -> Slice 3 (audit event + docs). An engine release pinning this primitive is cut before Slice 2.

### 2026-10-20 -- Observability OBS-5-foundation: audit schema + enriched writer + action registry MERGED (PR #99, merge 77685c69)

Behavior-preserving foundation of the audit-log rebuild (OBS-5 split per Cam into foundation -> migrate -> OBS-6). Additive nullable audit-schema migration + indexes (user_id FK + deletion untouched, `_ensure_schema` untouched); import-compatible `write_audit` that still commits and auto-enriches each row with request/actor context (reusing OBS-3's context), with JSON-safe + redacted structured-value coercion that never aborts the write; a 83-action/22-domain registry with a live AST drift guard. No callsite transaction change, no chain/append-only/retention, no reader change (later sub-slices). Gates: dennis GO; Codex final GO after 3 rounds (a never-raises contract violation + two int-subclass edges found and fixed, terminal fix Cam-approved); local CI green (ruff/format/mypy, 93 passed/19 PG-skips). Postgres migration leg runs in CI's PG matrix (local has no PG). NEXT: OBS-5-migrate (security-critical atomic conversion + the FK/deletion change + AF/RO ordering), then OBS-6 (chain + append-only + retention), coupled.

### 2026-10-20 -- Observability OBS-8: opt-in Prometheus app metrics + atomic job-cancel fix MERGED (merge 9db803f9)

The metrics slice of the observability program. An operator can now point Prometheus at `GET /api/metrics` and see job starts and outcomes, job duration, which backend ran each masked column, HTTP request counts and latency, log-record counts by level, and audit-write outcomes. It is off by default (`DECOY_METRICS_ENABLED`); when off, the route does not exist. Every label value comes from a closed list, so no series can carry a request, job, user, path, column or free-text value, and the series count stays bounded. A metrics failure is swallowed and never reaches a job, request, log line or audit write. No dashboards ship; the guide is `docs/guides/metrics.md`.

The same merge fixes a real race in job cancel. Cancelling a job used to read its status into memory and then write "cancelled", so it could overwrite a job a worker had just finished. Cancel is now two guarded database statements, safe on Postgres and SQLite alike: the cancel lands only if the job is still cancellable, and a running job's target locks are left to the worker's own terminal path to release. The one case it does not close is a cancel that loses a pending-to-running claim in the gap between its two statements. The job then keeps running and the route says it was not cancelled. A second cancel lands it, and no data is lost. Gate chain: dennis APPROVE, Codex final GO on the cancel gate, CI mirror clean, 132 tests passing. Next in the program: OBS-5 (audit write path), then OBS-6 and OBS-9.

---

### 2026-10-19 -- Observability OBS-1b: engine log-leak scrub + safe isolated-run error summary MERGED (engine PR #289)

The error-message safety slice of the observability program (engine-only; nothing about how a job masks data changed). When a masking job fails or crashes, the error a user sees no longer contains raw exception text, a data row, a file path, or a stray "code" that merely looks safe; it shows a clean summary instead (what failed, the exit/signal, memory info). An exception's code is now shown only when it is one the engine actually registered, so a secret-shaped value can't ride along in the code slot. It also stops a zip-code value from being written to a debug log, and upgrades the automatic leak detector so this whole class of bug is caught on future changes, not just the obvious cases. Importantly it preserves the one piece the engine itself reads out of that error text (the marker that tells it to retry on a different route), so job routing is unaffected. Example: a crash that used to surface "ValueError: could not parse 123-45-6789 ..." now surfaces "child terminated abnormally (returncode=-11, signal=SIGSEGV, reason=no_result_envelope)". Gate chain earned its keep: Codex plan-gate GO (3 rounds), dennis GO (one mechanical allowlist blocker fixed), Codex final NO-GO then GO (it caught a real residual leak in the code echo). Two separate pre-existing leaks were found and filed as §AUDIT follow-ups (a quality-warning repr leak into job output; and richer engine error codes needing an engine-owned registry to echo safely). Next: OBS-2 (fill the remaining job-log gaps: kernel-call counts, the one route that records no engine, per-job peak memory, row errors).

---

### 2026-10-19 -- Observability OBS-1: route + per-column engine in the job log, engine-version fix MERGED (platform PR #98)

First build slice of the observability program (program plan `docs/plans/2026-10-19-observability-program.md`, which lands with this slice; OBS-0, the dev-loop "logging wired" done-state line, shipped earlier into dev-rules). The job log a user reads now shows, for each table a job masked, which route it took and which engine handled each column -- information that until now only lived in the technical evidence, not the readable log. It also fixes a real bug: the platform recorded the engine version as a hardcoded "0.1.0" at five places while the engine is actually the installed version, so every job record was wrong; it now reads the real installed version and records the Rust companion build too. None of the user's data goes into the log -- only routes, engines, column names and bounded counts; everything else (values, expressions, raw errors, free-text reasons) is dropped by an allowlist. Example: a job log now reads "engine decoy-engine 0.9.0; native companion present", then "accounts: chunked route, 1.2s; email by the Rust engine, notes by Python". Gate chain: Codex plan-gate GO (2 rounds) -> dennis GO (0 blocker/high/medium) -> Codex final GO (0 blocker/high/medium; 4 low safety-hardenings applied to the log scrubber with regression tests). No accepted-job output change (byte oracle). The engine version fix is also a correctness win beyond observability. Next: OBS-1b (scrub the last few raw-exception engine log lines), then OBS-2 (job-log completeness).

---

### 2026-10-19 -- Phase F F-audit: no-legacy generation compute audit MERGED (engine PR #288); PHASE F CLOSED

The terminal Phase F slice, and it closes the phase. It is tests and docs only; nothing about how the engine runs changed. The audit proves, from a table built out of the engine's own dispatch rules (not from watching a run), that every kind of generated column is computed exactly where we say it is: on plain Python or NumPy, and never on the compiled Rust helper. It watches the one place a generated value could reach that helper and proves it stays at zero, and a deliberately broken version that routes a column the wrong way makes the audit fail, so the check cannot pass for the wrong reason. It also proves that eligible jobs run on the fast unified core rather than the old whole-table path, on both the streaming and in-memory routes; that the generate-then-mask hand-off is correct; that an empty or all-blank column cannot make a check pass by having nothing to check; and that locale-specific fake data (like a German street name) is pooled or not exactly as the rule says. Re-scoped for the earlier FR3 shelve: the old "did a claimed Rust generator quietly fall back" question no longer applies, so the audit re-targets what generation actually guarantees now. Gate chain: Codex plan review GO over four rounds, then dennis GO (no blockers), then Codex final review which first caught a real gap (the locale case was untested) and returned GO once that was fixed and re-reviewed. With this in, Phase F is CLOSED: the unified generation core, the date-window generator, the mixed generate-plus-mask route, the capacity evidence, and this audit are all shipped; the Rust-generation-kernel idea was shelved after it measured slower; the extra evidence-transport work folded into the later observability program; and the big 100-million pure-generation cloud run was skipped because the 10-million run already answered the speed question. Still owed: the engine knowledge-graph refresh (its main checkout is parked on another branch; batch it when that frees).

---

### 2026-10-19 -- Phase F F4a: lower-tier generation + mixed capacity evidence MERGED (engine PR #287)

The first part of F4 (capacity), the local tiers before the cloud run. It measures data generation and the mixed generate-plus-mask job at 1 million and 10 million rows, each run twice, and checks memory stays under a ceiling set before the run, that a rerun produces identical output, and which engine produced each column. Results: pure generation holds memory steady as it scales (about 227 MB at 10 million) but is throughput-bound by the date-window step (about 14k rows/second, so a 100-million pure-generation run would take roughly two hours). The mixed job's memory grows about 1.7x from 1M to 10M, bounded and under its ceiling, because that route keeps the child and its resolved keys in memory; the straight-line extrapolation to 100 million (about 7 GB) matches the real 100-million cloud run that came in at 7.86 GB, so the local and cloud numbers agree. This slice is bench and evidence only, no engine behavior changed. Findings recorded: the mixed route grows with scale (not flat), the date-window step dominates generation time, and a generated parent containing blanks falls to an unbounded path (that lift is F2 scope). Gates: dennis GO (clean), Codex final GO. Next in F4: the platform evidence-transport slice, then the 100M cloud run (owner-approved spend, flagged first), then F-audit closes Phase F.

---

### 2026-10-18 -- Phase F FR1: windowed_date in the re-baselined generation core MERGED (engine PR #285)

Second re-baseline slice. The `windowed_date` generator (a date drawn within a window of another date column) now runs through the unified generation core instead of being declined, so these columns can stream like the rest. Its anchor date must be a strict, absolute, timezone-free ISO date; wall-clock forms like "now", timezone-bearing strings, and ambiguous or partial dates are refused, which keeps the output reproducible. A missing anchor produces a missing value; an anchor that cannot be read, or that lands outside the supported 1700 to 2200 range, fails the job cleanly rather than guessing, and the bad value is never written into the error or its traceback. Because the rule lives in one shared place, the masking side of windowed_date gets the same safety. Gate chain: dennis GO-with-changes (added the CHANGELOG entry and a mask-path test), then Codex final NO-GO then GO (it caught the raw date leaking through the exception chain; fixed and pinned with a traceback test). The supported-range widening to pandas' full representable bounds is tracked in the backlog. Next: FR3 (route some generators through the Rust kernel), then F4 (capacity) and F-audit.

---

### 2026-10-18 -- Phase F FR0: unified generation core (re-baseline) MERGED (engine PR #283)

The first slice of the generation re-baseline, and it also lands the re-baseline program plan (`decoy-engine/docs/plans/2026-10-18-phase-f-rebaseline-f1-f3.md`, which passed four Codex plan-gate rounds). The old contract required accelerated generation to match today's bytes exactly, which kept failing; the re-baseline replaces it with a reproducible, route-independent oracle re-frozen to the accelerated output. FR0 makes resident and streamed generation run one shared core, so a job produces the same data whether it streams to a sink or stays in memory. It adds a reserve-before-allocate memory ledger (a column with no defensible memory bound is refused before any generator runs, on every path; the batch layout is lazy and charged before any stage reserves, so a too-big job is rejected without first allocating it) and re-freezes the generation golden. Only the all-null / zero-row fixture changed type (now `string` instead of inferred `null`); every value is unchanged. A zero-row generated table still matches the full-frame oracle. Gate chain: dennis GO-with-changes (built the missing mixed generate-then-mask acceptance test, fixed a zero-row route-identity regression) -> Codex final NO-GO then GO (it caught a reserve-before-allocate hole that allocated ~80 MB before refusing, the zero-row divergence breadth, and a pool-lifetime charge; all fixed with regressions that fail on the pre-fix code). Local ruff/format/mypy clean, FR0 and F2 suites green. Owner cleared the merge on dennis + Codex green. Next: FR1 (windowed_date admission), FR3 (Rust generation selection), F4 (capacity), F-audit. Deferred DOCUMENT item: the engine graphify graph refresh (the main checkout is parked on another branch; batch at the Phase F boundary).

---

### 2026-10-17 -- Phase F F2: mixed generate+mask on the Rust routes MERGED (engine PR #274)

Jobs that both generate some tables and mask others now mask those tables on the bounded Rust routes under `auto`. Generation stays resident, as before. The output is byte-identical to the full-frame mixed path. For a coupled job (a generated parent with a masked child through one foreign key), the child key is resolved against the resident parent in one pass, and both tables publish in one transaction. Jobs the route does not admit still run full-frame: fpe, text_mask, top_code, geo_generalize, and nested columns (their warnings are not chunk-invariant), plus composite keys, the out-of-core mask driver, and generated output with nulls, NaN, or nested values. The engine turns the route on by default. The platform gets it on its next engine dependency bump; platform activation is a separate decision and is not made yet. Plan: `decoy-engine/docs/plans/2026-10-17-phase-f-f2-mixed-masking-rust.md`. F4 and F-audit remain upcoming. F1 and F3 stay held for a re-baselined generation oracle.

---

### 2026-10-16 -- Phase F F0: generation parity contract + backend witness MERGED (engine PR #273)

Phase F (generation + mixed jobs) has begun. F0 is the tests-only safety net the rest of the phase is gated against. Before the upcoming slices make generation stream in bounded batches (F1) and route some generators through the Rust kernel (F3) - both of which could silently change output - F0 freezes exactly how generation behaves today: a whole-table parity oracle with checked-in canonical-Arrow digests, a supported/deferred matrix over 20 generator fixtures, invariants pinned by mutations through the real production code paths (so a batched or kernel-swapped future that diverges fails loudly), and a per-column "which engine ran this" witness with a marking kernel that catches a discarded or recomputed selection. Both reviewers independently traced every mutation to its real seam and confirmed the contract genuinely bites rather than rubber-stamps. Tests-only, no production change. Gate chain: Codex plan-gate GO (3 rounds) -> dennis GO -> Codex final GO. Plan: `decoy-engine/docs/plans/2026-10-16-phase-f-f0-contract.md`. Next: F1 (bounded generation) + F3 (Rust generation selection), with a committed composite-repeatability test first.

---

### 2026-10-16 -- Phase E 100M milestone MET (bounded-memory confirmed)

The headline scale milestone. After the memory fix (#272), the confirming 100-million-row relational masking run on GCP came in at 8.0 GB peak memory, tracking its 8 GB budget (within a 12 GB ceiling), down from ~29-30 GB before the fix. Same correct output (referential integrity intact on every FK edge), all 41 masked columns on the compiled Rust path (not one silently fell to Python), real external spill-and-merge, and the same ~42-minute mask time. So Decoy masks 100 million relational rows correctly, fully on the Rust engine, within a bounded ~8 GB memory budget on a single box. Per the owner's recommended-scope call, the bounded 100M closes the Phase E milestone; the 200M external-reorder proof is deferred to backlog. The per-column Rust evidence is captured in the bench's disposition record; surfacing/asserting it inside the platform rides the Phase F generation-evidence-transport slice. Evidence: `decoy-platform` d4-bench worktree `docs/product/release-1-validation-runs/2026-10-16-tb6-50m/`.

---

### 2026-10-16 -- OOC reorder-lane memory fix: spill readers no longer memory-map (engine PR #272)

The Phase E 100M run surfaced it: masking 100 million relational rows worked and ran fully on the Rust path, but peaked at ~29-30 GB of memory even when told to stay under 8 GB. The cause was that the streaming reorder path read its temporary spill files by memory-mapping them, which makes the file's pages count as the program's resident memory, scaling with the data size and ignoring the memory budget entirely. The fix reads those files the ordinary streaming way (`pa.OSFile`), exactly as the external sorter next door already does and documents. It is a read-handle swap only, so output is byte-for-byte identical; proven locally on a forced-reorder run (peak memory 1.56 GB -> 650 MB, same speed), and guarded by a new regression test that fails on the old memory-mapped reader and passes on the new one, plus deterministic file-handle-close tests across every path (including the child-key reader's two consumers). Gate chain: Codex plan-gate GO (3 rounds) -> dennis (one blocker: the two changed modules needed physical-seam allowlist entries, fixed) -> Codex cross-model final GO. Plan: `decoy-engine/docs/plans/2026-10-16-ooc-spill-mmap-rss-fix.md`. This removes the spill-file mapping growth; the end-to-end bounded-100M claim is confirmed by a separate post-fix 100M GCP re-run (owner-approved, pending).

---

### 2026-10-16 -- R4/E6: ShadowCoordinator coordinator/batch-runner split MERGED (engine PR #271)

The refactor that clears the gate before Phase E. The engine's unified-slice masking coordinator (`_shadow_coordinator.py`) was the most-edited engine file and sat at its 600-line size cap, with per-batch execution and pool/kernel resolution crammed in alongside the plan-shape routing. Phase E's 100M scale-hardening will edit exactly that per-batch path, so this makes the change easy first: it carves the per-node/per-batch loop + pool/kernel resolution out into a new `_shadow_batch_runner.py` (344 lines), moves the result type to `_shadow_result.py`, and leaves a thin 287-line coordinator that just routes and assembles. Same carve pattern already used for the synthesis/mixed/full-frame branches. It is strictly behavior-preserving: no masking output, route, evidence, or timing change on any path. Proven by a 19-case characterization baseline captured on the pre-change and post-change code that came out byte-for-byte identical (same SHA-256), independently re-run by both reviewers, plus the full physical/sentry/unit test suites green and the LOC caps tightened so the regrowth this removed cannot creep back. Gate chain: Codex plan-gate GO (round 2, after folding 4 acceptance-plan findings; the carve itself was approved round 1) -> dennis GO -> Codex cross-model final GO. Plan: `decoy-engine/docs/plans/2026-10-16-r4-shadow-coordinator-split.md`. Next in Phase E: one 100M run.

---

### 2026-10-16 -- D-audit: Phase D no-legacy compute-backend audit MERGED (engine PR #269)

The terminal Phase D slice. Decoy masks on several internal backends depending on job size and shape (a compiled Rust path, named-Arrow kernels, compiled index-selection for faker, a no-op for passthrough, and a dedicated Python path for the few operators without a fast version). The risk in any such system is a job quietly slipping onto the slow generic pandas path unnoticed. This slice is a permanent, self-checking proof against that: a compute-admission matrix derived from the live SEQ / out-of-core / native-chunked admission constants (so a new or renamed operator fails the pin until it is classified), plus consumed-output witnesses that fail if an admitted cell's work is ever discarded and recomputed on the generic fallback. Retained live fallbacks (the redact conversion-failure path, the OOC bucket_perturb bridge when the companion is absent) are witness-fenced rather than deleted, and reorder-reachability checks confirm the live external-reorder lane with no reverted-regression remnant. Tests + docs only; no production code changed. The text-masking witnesses were the hard part -- the Codex cross-model final gate broke them three times until the distinguishing mark originates at the compiled-candidate-kernel boundary and every Python detection path is fenced, so a mutant that discards the compiled spans and recomputes in Python is now caught. The record honestly scopes each citation (the chunked text suites prove the route and byte-parity, not compiled-span consumption; the real compiled-span witnesses are the sequential and out-of-core suites) and classifies the dedicated-Python operators (code_set, NER, faker's declined/FK-key cells, out-of-core text_mask) rather than hiding them. Gate chain: dennis GO -> Codex cross-model final GO (3 rounds). Matrix/record: `decoy-engine/docs/records/2026-10-16-d-audit-compute-matrix.md`. Phase D's FK-route code and no-legacy audit are now complete; the remaining program Done-when item (the 100M + 200M scale proofs within memory ceilings) is marked "feeds Phase E" and carries into the Phase E milestone.

---

### 2026-10-16 -- D5: Phase D shipped to the platform (engine 0.9.0 pin + OOC certification) MERGED (platform PR #95)

The platform now runs the Phase-D engine. We cut engine release 0.9.0 (tag `v0.9.0`, commit `de0eda0b` on `release/0.9.0`, off engine main which stays 0.7.0 by design) and atomically re-pinned the platform to it: `decoy-engine==0.9.0`, companion `decoy-native-abi-3`, engine checkout SHA across pyproject/engine_compat/backend.yml/fixtures-verify.yml/Dockerfile/tests/CODEMAP, moving off the pre-Phase-D `0.8.0rc1`/abi-2 pin. So the whole Phase-D stack (the Rust out-of-core FK kernels D1-D4 + the reorder parent-size guard, GAP9 multi-core on the sequential + OOC routes, the OOC null-bearing-int guard, and consistent int+null hashing) is what the platform executes. New certification `tests/test_d5_ooc_certification.py` proves the already-live out-of-core route byte-matches the full-frame oracle across 10 payload operators x 5 FK-key shapes (incl. int+null+hash), preserves referential integrity + NULL FKs on published output, fails closed on an unresolvable budget, and that the companion-ABI gate fires on a mismatch. Gate chain: Codex plan-gate GO -> Opus VERIFY -> dennis GO -> Codex cross-model final GO; 267 tests pass. Certification-only, no new rollout flag. Deferred (non-blocking): the production-image build runs as a pre-deploy check; a small certification follow-up (redact FK-key + a scheduler dtype case). Plan: `docs/plans/archive/2026-10-16-d5-phase-d-release.md`.

### 2026-10-16 -- Phase D: hashing an integer column with nulls, consistent across routes MERGED (engine PR #267)

Hashing an integer column that contains nulls was rejected everywhere; it is now supported on every route and byte-identical to the native path, including values beyond 2**53 (uint64 max, int64 min stay exact). The small-job pandas path used to widen such a column to float-with-NaN and fail; hash now keys from the exact-integer snapshot (`_exact_int_faker.py` renamed `_exact_int_sources.py`) fed to the kernel as a typed Arrow array, so no precision is lost. `hash` left the int+null reject set; truncate and categorical stay rejected. Conditional (`when:`) hashing of an integer column is deferred (V2 items 11-12, it needs a pre-existing predicate-precision fix) and now returns a clean `gated_hash_on_integer_unsupported` instead of the pre-existing late crash. The same PR also carried the out-of-core null-bearing-int ingest guard (truncate/categorical) that brought the OOC route in line with the others. The determinism envelope is unchanged. Gate chain: Codex plan-gate GO (7 rounds, 2 of them product-owner scope decisions) -> dennis GO -> Codex cross-model final GO (caught one weakened test, fixed). Plan: `decoy-engine/docs/plans/2026-10-16-int-null-hash-support-consistent.md`.

### 2026-10-15 -- Phase D GAP9: honor native_threads on the sequential + out-of-core routes MERGED (engine PR #266)

The native kernels already ran multi-threaded on the chunked, full-frame, and unified-slice routes, but the sequential and out-of-core routes dropped the thread grant and always ran on one core. GAP9 wires the grant through both, so a large multi-table job that streams through the out-of-core path can use the cores it was granted. Memory stays bounded: the rayon pool is sized from host cores, not the grant, so what extra threads add is per-thread batch buffers (tens to hundreds of MB on these fixtures), not whole-table copies. Default is unchanged (one core unless more are granted). Verified by a fresh-process RSS harness: peak memory at four threads stays within a tight additive tolerance of the single-thread run. Plan: `decoy-engine/docs/plans/2026-10-15-gap9-native-thread-grant.md`.

### 2026-10-15 -- Reorder parent-size guard on the out-of-core reorder lane MERGED (engine PR #265)

The reorder lane builds the parent side in DuckDB, so a large parent (many distinct keys) could overshoot the memory cap. The route now sends a reorder-eligible table to the bounded batch lane when its parent-key count is above a ceiling derived from DuckDB's actual cap. Demotion keeps the output byte-identical (batch preserves row order), so it trades speed for memory and never rejects a job. The ceiling counts keys, not bytes, so very wide keys remain a known gap; the fixes (a partitioned join and a width-aware ceiling) are recorded as V2 items 9 and 10. Plan: `decoy-engine/docs/plans/2026-10-15-reorder-parent-size-guard.md`.

### 2026-10-15 -- Phase D3a: validators on the bounded out-of-core route MERGED (engine PR #264)

A RAM-fitting pure-mask FK job with validators used to fall back to the full-frame path. The bounded route now runs validators on each masked batch when every validator is a per-cell check (luhn, npi, iban, vin, regex_match, column_in_set) on a string column. The report matches the full-frame oracle, and a validation failure stops the run before anything is published. Jobs with other validators, hash or categorical or numeric-output columns, incoming FK child keys, or quarantine on validation failure still run full-frame. Follow-ups are tracked in the roadmap's Phase D row. Plan: `decoy-engine/docs/plans/2026-10-15-d3a-validators-bounded-ooc.md`.

### 2026-10-15 -- Phase D4: reorder lane carries the masked payload as large_string (Arrow 2GB fix) MERGED (engine PR #263)

At 100M rows the out-of-core FK job with the reorder path on failed with an Arrow error: the external sorter de-chunks a whole run into one array, and the masked string payload overflowed Arrow's signed 32-bit offset limit (just over 2GB in one array). The fix carries that payload through the sorter lane as Arrow's 64-bit `large_string`/`large_binary`, then narrows it back on output, so the result stays byte-identical. This is the change that lets the 100M reorder run complete (byte-parity confirmed on the GCP run); the batch path was never affected. A separate per-batch size ceiling remains documented as a scoped limit. Both reviewers approved (tech-lead + cross-model). Plan: `decoy-engine/docs/plans/2026-10-15-d4-reorder-large-string-overflow.md`.

### 2026-10-15 -- Phase D4 bench infrastructure MERGED (engine PR #262)

The measurement scaffolding for the 100M/200M-row external-reorder scale proof, plus the cheap D4a revalidation that runs before any cloud spend. No production or masking code (engine: scripts/tests/docs only). It adds a deterministic FK-chain fixture builder, a supervised bench worker that measures external memory from outside the process and classifies every failure mode (timeout, out-of-memory kill, crash, missing or malformed output) as a non-success, and tests that prove the reorder lane is actually taken and that its sorter really spills and merges. D4a is recorded green at the real 2-million-key threshold (route stays on the bounded out-of-core lane, reorder fires on both child tables, memory stays under its ceiling, output matches), with the worker's own JSON linked as evidence. Both reviewers approved (tech-lead + cross-model). One flaky test (a forced out-of-memory check that behaves differently on the CI runner) was made deterministic with a timeout backstop. The platform-side launcher PR (#94) is held because platform CI is broadly broken at setup right now, unrelated to this change; the GCP runs will run from that branch. The 100M/200M cloud runs are the remaining Phase D step (owner-approved spend).

### 2026-10-15 -- Phase D3b: token vault on the bounded out-of-core route MERGED (engine PR #261)

A relationship-bearing (FK) pure-mask job that also writes a token vault used to be shut out of the fast, low-memory routes: writing a vault forced it onto the full-frame path (whole table in memory) or made it reject outright. This slice lets such a job ride the out-of-core (OOC) route when it fits in the memory budget, so a vault FK job gets the same faster, lower-memory treatment as a non-vault one. The vault is collected per batch at the mask step in both OOC drivers, before the join reorder, so each source value stays aligned with its masked value.

Admission is strict and byte-identical-or-decline: only an explicit allowlist of operators (hash, categorical, truncate, redact, passthrough) on string columns, never an incoming FK child key (parent keys are allowed, since recovering the parent key is the common case). It is gated on the job fitting (`full_frame_fits_estimate is True`): the vault accumulates one entry per distinct value-triple in Python memory, which is not bounded by the OOC disk-spill budget, so a job too big to fit (or one we cannot price) rejects exactly as a too-big vault job does today. Anything outside the allowlist falls back to the full-frame path.

Vault contents match the full-frame oracle byte-for-byte, with one accepted exception already carried by hash/categorical masked output: the native-vs-Python Unicode-normalization (NFC) envelope. For such a row the stored key equals the run's own masked output, so it recovers correctly; no new divergence. A failed run writes no vault (the write is success-gated). Full gate chain green: tech-lead (dennis) APPROVE, cross-model (Codex) final GO. The cross-model gate caught a real issue the first review missed (a missing fit gate that would let an oversized high-cardinality vault run out of memory), which was fixed and re-verified. No Rust; 100% changed-line coverage. Follow-ons (not in this PR): a spillable vault to unblock too-big vault jobs, SEQ-native vault, numeric vaulted columns.

### 2026-10-15 -- Phase C6b-ii slice c: native FF1 for plain-digit text_mask fpe spans MERGED (engine PR #260)

Completes native text_mask. A `text_mask` span with the `fpe` (format-preserving encryption) strategy ran one value at a time in Python; slice c routes the plain-digit, non-checksum spans (ssn, us_phone, us_zip ZIP+4) through the already-shipped Rust FF1 kernel, with no new Rust code. Byte-for-byte identical to the Python output (same detector-specific key and tweak, separators preserved), verified by pinned known-answer values and a 1,600-plus-case differential. Checksum detectors (pan, npi), ZIP5 and sub-floor cases, and non-ASCII cells keep the Python path; in a mixed cell each declined span runs through Python once in span order, with identical warnings and notice counts. Any kernel error fails safe to the oracle. Measured 4.2-5.2x on the unified/chunked route and ~4-4.9x on the sequential route for fpe configs. Both reviewers approved. (Process note: the automated final reviewer merged the PR itself before CI finished; code was fully gated and correct, CI watched post-merge, prompt wording tightened to prevent a repeat.)

### 2026-10-15 -- Phase C6b-ii: native (Rust) splice for text_mask, slices a+b MERGED (engine PR #259)

`text_mask` (free-text PII scrubbing) ran a Python per-cell splice on every route, which the audit flagged as the throughput floor for text masking. Slice a reuses the already-shipped `text_redact` Rust detection kernel and extracts the splice to its own module, plus wires a real sequential-route execution seam; slice b adds a Rust splice kernel that does the redact/passthrough splice natively. Strict byte-identical-or-decline contract: anything it cannot reproduce exactly (an fpe/faker/date_shift span, a non-ASCII cell, an unrepresentable token, a non-string strategy value, an older companion) falls back to the Python splice, so there is no new semantic-differences entry. Measured 6.5-7.5x on the unified/chunked route and 2.5-3.4x on the sequential route for the eight Rust-supported detectors; lookaround-detector configs (ssn/us_zip/street_address) stay ~1.2-1.3x because Python detection dominates there. The cross-model final gate caught two real crash-class edge cases the first reviewer missed (an unrepresentable token, an unhashable strategy value); both now decline. CI all green. Remaining: slice c (native plain-digit fpe spans) and a native out-of-core twin are follow-ons.

### 2026-10-14 -- Phase D (audit GAP6): prefer the bounded route over the full-frame oracle for RAM-fitting FK jobs MERGED (engine PR #258)

Fourth fix from the bottleneck audit. Under `auto`, a relationship-bearing (foreign-key) pure-mask job that fit in RAM was routed to the full-frame pandas oracle, which masks one cell at a time (the audit measured ~2583s at 10M, about 4.3x over the target). It now prefers the measured-faster bounded route (sequential or out-of-core), with a schema-aware guard that diverts any fitting job whose key dtype the out-of-core route would reject (but the oracle completes) to the sequential route instead, so no job that used to work starts failing. Measured 5.8-6.4x faster on the sequential route with about 2x less memory across 50k-500k rows per table; full-frame runs out of memory by ~1M rows per table. The cross-model final gate caught a real edge case the first reviewer missed (a key that is both a child and a parent key is retyped by the upstream join, so the out-of-core route would reject it); fixed and re-approved. Owner-approved output envelope (option A). CI green. Follow-up: the governor-reroute acceptance test premise no longer holds (retire or retarget separately).

### 2026-10-14 -- Phase D (audit GAP8): integer foreign-key encryption native on the sequential route MERGED (engine PR #257)

Third fix from the bottleneck audit. Format-preserving encryption (fpe) on an **integer foreign-key key** column masked one value at a time in Python on the sequential route (the audit measured ~1756s at 10M, about 3x over the target), because the fast path required the column to already be text. This admits integer foreign-key columns to the existing compiled encryption kernel, byte-for-byte identical to the old output. Measured **8.6x** faster on that step (identical results, confirmed by a full-row checksum match; 10M projects to about 132s, well under the 10-minute bar). No new Rust.

The planning gate earned its keep here: a reviewer reproduced a real correctness trap and the scope was tightened in response. On this route, nullable integer *data* columns (not keys) get widened to floating-point when the table is loaded, so the old Python path was actually encrypting the float text ("123456.0"), and a naive fast path would have encrypted the integer text ("123456") and produced different output. Foreign-key columns are kept exact on load, so the fix is limited to them; nullable integer data columns stay on the old path (a noted follow-up), with a guard that aborts the run if a key ever arrives non-integer rather than risk a mismatch. Both reviewers approved; full gate chain green.

### 2026-10-14 -- Phase D: free-text redaction native on the out-of-core route MERGED (engine PR #256)

Second fix from the bottleneck audit. On the out-of-core (large/streaming) route, free-text redaction (`text_redact`, find-and-redact PII in free text) still masked one value at a time in Python even though the compiled kernel existed. This wires that kernel onto the route, mirroring the fpe fix (#255). Measured **2.3x** faster on the text-redaction step (native 15.9s vs Python 36.1s at 1M rows; about 159s at 10M, well under the 10-minute bar). Output is identical, to the byte: the kernel does the detection, and the parts it deliberately can't do in Rust (lookaround patterns like SSN/ZIP, non-ASCII cells) are replayed in Python per cell, same as the other routes. Name/location redaction via the NER model stays on Python by design; a non-string source, bad config, or absent companion safely stay on Python too. A real execution fault in the kernel aborts the run rather than silently emitting unredacted PII. No new Rust. Both reviewers approved, full gate chain green.

### 2026-10-14 -- Phase D: format-preserving encryption native on the out-of-core route MERGED (engine PR #255)

First fix from the bottleneck audit. On the out-of-core (large/streaming) route, format-preserving encryption (fpe) masked one value at a time in Python; the audit measured a single fpe column alone blowing the 10-minute bar on that route (~16 min at 10M rows). This wires the existing compiled encryption kernel onto that route, the same kernel the other routes already use. Measured **16x** faster on the fpe step (that column drops from ~16 min to ~1 min at 10M). Identical output; checksum / non-string / no-namespace fpe safely stay on the Python path. No new Rust. Both reviewers approved, full gate chain green.

### 2026-10-14 -- C-phase: free-text redaction native on the sequential route MERGED (engine PR #254)

Puts `text_redact` (find-and-redact PII in free text, e.g. emails/phones/card numbers) on the Rust fast path on the main bounded route too, as the 7th masking method wired there.
- **What it did.** The compiled text-redaction kernel already ran on the streaming and full routes; a text_redact column on a multi-table (foreign-key) job on the main bounded route still fell back to the slow Python path. This wires the existing kernel onto that route. No new Rust. Output is identical to before, to the byte: the kernel does the PII detection, and the few things it deliberately can't do in Rust (lookaround patterns, non-ASCII text) are replayed in Python per cell, same as on the other routes.
- **The limits.** Name/location redaction via the NER model stays on Python by design (a documented permanent exception). A text_redact column used as a foreign-key key stays on Python too.
- **Why it matters.** It removes the last text-redaction bottleneck for foreign-key and mixed jobs on this route. Measured about 1.8-1.9x faster on that step, with 10M rows extrapolating to roughly 4 minutes, well under the 10-minute target. (Large text-redaction-only jobs already ran native on the streaming route; this covers the mixed and smaller jobs that run on the bounded route.)

### 2026-10-14 -- Phase D: pin the out-of-core multi-parent FK decline MERGED (engine PR #253)

Tests-only, no behavior change. A FRAME found the multi-parent foreign-key shape (one child key column pointing at several parent tables) is already fully handled on the main bounded route and the full-frame route, so "Dmp" as a feature slice was already shipped. The one real gap was a safety net with no test: the streaming (out-of-core) route deliberately declines that shape (it reroutes to a route that can handle it), and that decline was asserted by no test, so it could have silently broken. Added two tests pinning it (the gate check and the fail-closed run), mirroring the existing self-referencing-FK decline tests. Both reviewers approved; the pin was verified to bind specifically to that decline (a single-parent control is accepted with no rejection).

### 2026-10-13 -- Phase D: fake-value masking native on the sequential route MERGED (engine PR #252)

Puts `faker` masking (realistic fake names and the like, drawn from a value pool) on the Rust fast path on the main bounded route too.
- **What it did.** On the bounded (sequential) route, faker masking already derived its pool picks on Rust, but then stitched the column back together one row at a time in Python. This moves that assembly onto the Arrow fast path for the two reproducible modes: the deterministic one (the same source value always maps to the same fake value) and the position-based reuse one (keyed on the row's position, preserved correctly even when only some rows are selected by a `when:` filter). Output is identical to before, to the byte. It reuses the exact kernel and helpers the streaming route already ships, so this is wiring, not new masking logic.
- **The deliberate limits.** Modes that need to look at the whole column at once (make-every-value-unique, match/scale the number of distinct values) stay on Python, as do a non-string source, a provider outside the supported set, and a pool that doesn't produce text. Each carries an explicit, data-free label saying why. A faker column used as a foreign-key *key* stays on Python too, because fake-value selection can map two different inputs to the same output and that would collapse a key.
- **Why it matters.** It removes the last per-row Python loop from faker on the main route, so a faker column no longer drags on the Rust columns beside it in a mixed job. Measured on the faker step alone: about 1.1-1.3x faster (a few hundred milliseconds saved per million rows); byte-identical results.

### 2026-10-13 -- Phase D: format-preserving encryption native on a foreign-key key MERGED (engine PR #251)

Extends the Rust fast path to foreign-key *key* columns, for the one masking method where it is safe to do so.
- **What it did.** A foreign key is masked so that the parent row and every child that points at it get the same new value. Until now, only the `hash` method did that on the Rust fast path on the large-relational route; the others ran Python there. This makes **format-preserving encryption** (which keeps a value's shape, e.g. a 9-digit id stays 9 digits) run on Rust as a foreign-key key too, including the case where a child points at a parent row that does not exist (the engine mints the replacement key on Rust using the parent's settings, and refuses safely if a value can't be encrypted). The `hash` behavior is unchanged to the byte.
- **The deliberate limit.** The other non-hash methods (categorical, date-bucketing, date-shift) are **not** moved to Rust on a key, on purpose: they can map two different source values to the same output, which would collapse a key and break the parent/child link. They keep working on Python as a key and now carry an explicit, data-free label saying why. Used on ordinary (non-key) columns they remain on the Rust fast path as before.
- **Why it matters.** It removes a Python step from a common foreign-key setup (format-preserving ids) on the route that handles big linked datasets, without risking key integrity for the methods where Rust would be unsafe.

### 2026-10-13 -- Phase D: internal module split (SEQ-native decision types) MERGED (engine PR #250)

Housekeeping with zero behavior change: split one over-full module in the sequential-route fast path into two, to make room for the foreign-key-key work above. Every existing test passed unchanged.

### 2026-10-13 -- Phase D / Dcomp: composite foreign-key parity-completeness on the SEQ route MERGED (engine PR #249)

Proves the engine masks multi-column (composite) foreign keys correctly on the large-relational route, across the cases earlier slices had not covered.
- **What it did.** A composite foreign key is one where several columns together point at a parent row (for example member id + plan id + date). The masking of each column was already on the fast path, and the engine already keeps the linked rows consistent; this slice is tests-only (no engine change) that pins the exact behavior across the gaps: when a child points at a parent that does not exist the job stops with a clear, value-free error; when the parent row itself had a bad value the child is set aside under a quarantine rule instead (and the first key column decides the reason); the "warn and keep" option emits the right warning; very large integer key values keep their exact type and refuse the cases that could not be represented without silently rounding; empty and all-missing inputs behave correctly; and the engine routes the job the same way the customer would see. It also confirms the two shapes the engine deliberately does not accept still decline with a readable reason rather than silently doing the wrong thing.
- **Why it matters.** Composite keys are common in real databases. This closes the gap between "it works" and "it is proven to match the reference exactly, on every policy and edge case," on the route that handles big linked datasets. The cross-model review caught a test that looked like it checked precision loss but did not, which was fixed before merge.
- **Honest boundary.** This covers keys masked with the hash method (the usual choice). Making the other masking methods run on the fast path when used on a key, and the same proof on the out-of-core route, are their own upcoming slices.

### 2026-10-13 -- Phase D / D2c-iv: date_shift native on the SEQ route MERGED (engine PR #246)

Completes the date operators on the bounded (sequential) route's native path, and introduces the first survive-and-report error channel there.
- **What it did.** Registered `date_shift` (shift a date by a keyed per-row offset inside a bounded window) as the fifth native operator on the large-relational route, byte-identical to the Python path. The new piece: a non-null date that fails to parse keeps its original value AND is reported as a row error, rather than silently dropped or killing the job. These errors survive and surface; the pipeline then does what it always does with reported errors (fail loud by default, or set them aside under a quarantine rule and finish), the same whether the column ran on the fast path or on Python. A genuine engine fault still aborts the job; a date so close to the calendar limits that the shift would overflow aborts the same way on both paths. The sentinel pass-through (`preserve_values`) carries through, recorded only when a sentinel actually matched.
- **Why it matters.** Date-shift is the most common date-masking operator; it now runs on the fast engine on the route that handles big linked datasets. This finishes the date operators on that route (after date-bucketing). The error channel built here is reusable by any later operator that needs to report bad rows rather than fail.
- **Gate chain.** Codex plan GO (2 rounds) -> dennis APPROVE (0 blocker/high, 1 medium carry-forward, 1 low fixed) -> coverage 100% line+branch on the changed units + mutation (131/135 killed, 4 survivors injection-proven equivalent) -> Codex final GO (2 rounds). Each gate round caught a test-quality gap (a disposition label; a Unicode test fixture that wasn't actually testing two different forms) with no code bug; both fixed. Main CI green post-merge.
- **Next.** D2c-v (text masking) on the same route, after first splitting the sequential-native module, which is now at its size ceiling.

### 2026-10-13 -- Phase D / D2c-iii: bucket_perturb native on the SEQ route MERGED (engine PR #245)

Adds the fourth operator to the bounded (sequential) route's native path: the first DATE operator, and the one that builds the shared date-handling the remaining date operator reuses.
- **What it did.** Registered `bucket_perturb` (date coarsening: shift a date to its week/month/quarter bucket) as the fourth tenant of the SEQ-native descriptor framework. Non-key payload columns now mask on the fast Rust index kernel on the large-relational route, byte-identical to the Python handler. The near-boundary-date safety check became a shared check with a per-route response: the streaming out-of-core route still aborts (it cannot re-buffer), while the sequential route hands the whole column back to Python, whose wider date arithmetic masks dates the native kernel cannot. So turning on the fast path never makes a job fail that used to succeed. Sentinel pass-through (`preserve_values`, e.g. keep `9999-12-31` as-is) is wired through the sequential path, computed before the range check so a preserved far-future date is protected rather than refused.
- **Why it matters.** Date-bucketing (a common way to coarsen birth dates or event dates while keeping them useful) now runs on the fast path on the route that carries the big linked-table jobs. The shared date-range check and the sentinel plumbing are the groundwork the next slice (`date_shift`) reuses, so it is a smaller step. Perf mirrors the other index-kernel operators; identical output digests.
- **Gate chain.** Codex plan GO (2 rounds; scope narrowed to bucket_perturb only, `date_shift` moved to D2c-iv) -> dennis APPROVE (0 blocker/high/medium, 1 cosmetic low tracked) -> coverage 100% line+branch on the changed units + mutation (all meaningful mutants killed) -> Codex final GO. The final gate caught a genuine test-evidence gap (a boundary mutant wrongly called equivalent, because the date parser keeps nanosecond precision and the exact threshold is reachable); fixed with exact-equality tests, no production change. This native-touching PR ran the full compiled-companion build/test matrix in CI, so the companion-present parity suite was exercised in the gate. Main CI green post-merge.
- **Next.** D2c-iv (`date_shift` native on the SEQ route) via the same framework, extended with a survive-and-report row-error channel.

### 2026-10-12 -- Phase D / D2c-ii: categorical native on the SEQ route + generalized disposition MERGED (engine PR #244)

Adds the third operator to the bounded (sequential) route's native path and makes the per-operator reporting self-describing, so the remaining operators are a one-line registration.
- **What it did.** Registered `categorical` as the third tenant of the SEQ-native descriptor framework (after hash + fpe) via a thin adapter over the out-of-core admission already proven on that route (deterministic + namespaced + string-category config AND a string source, with a buildable weight distribution; declines the rest with a value-free reason). `categorical` non-key payload columns now mask native on the sequential route, byte-identical to the Python handler and carrying the same accepted native-vs-Python Unicode-normalization difference as hash (fpe, by contrast, carries none). A `categorical` column used as a foreign key stays on Python (native REMAP is hash-only). A kernel fault aborts the job closed with no Python retry; a transactional output writes nothing, a streaming output keeps only the tables already delivered. The per-operator metrics now iterate the descriptor table, so each operator reports under its own key and the hash + fpe reporting stays byte-identical.
- **Why it matters.** Categorical masking (realistic category draws that hold a column's distribution) now runs on the fast Rust path on the large-relational route, not only in memory. The reporting generalization means D2c-iii and later operators register in one place instead of editing the metrics code each time. Perf mirrors the other index-kernel operators (~20x class), identical digests.
- **Gate chain.** Codex plan GO (2 rounds; scope narrowed to categorical only, date operators moved to D2c-iii) -> dennis APPROVE (0 blocker/high, 1 medium-docs fixed, 2 LOW) -> coverage 100% line+branch on both changed units + mutation (all added-logic mutants killed, 3 gap tests added) -> Codex final GO. One post-gate fix: a decline test quietly depended on the optional Rust companion, so it passed locally but failed the standard-CI run that has no companion; made it companion-independent like its siblings and confirmed green against a companion-free runner before and after merge. Main CI green post-merge.
- **Next.** D2c-iii (bucket_perturb + date_shift index kernels) via the same framework.

### 2026-10-12 -- Phase D / D2c-i: SEQ-native operator framework + fpe MERGED (engine PR #243)

Opens the bounded (sequential) route to native masking beyond `hash` by generalizing the seam, and wires format-preserving encryption as the first new operator.
- **What it did.** Generalized the hash-specific SEQ-native seam into a small strategy-keyed descriptor table (per-strategy: load kernel, config-aware admission, apply-with-error-channel, handler warning pass, isolated kernel state), then wired `fpe` through it, reusing the compiled fpe kernel the chunked route already uses. `fpe` non-key payload columns now mask native on the sequential route, byte-identical to the Python handler; fpe is NFC-agnostic so (unlike hash) it carries no Unicode-version nuance. An `fpe` column used as a foreign key stays on Python (native REMAP is hash-only); any checksum scheme, non-string type, missing namespace, or invalid charset declines to Python; per-cell encryption errors fail the job closed; the handler's residual-risk warnings are preserved. `hash` stays byte-identical through the refactor.
- **Why it matters.** FPE (used to mask things like card/account numbers while keeping their shape) now runs on the fast Rust path on the large-relational route, not only the in-memory one. More importantly the descriptor framework is the reusable seam the remaining SEQ operators plug into, so D2c-ii/iii are additive. Perf: ~7x on the fpe step, identical digests.
- **Gate chain.** Codex plan GO (2 rounds) -> dennis APPROVE (0/0/0/2 LOW, fixed) -> coverage 100%/99% on the two changed units + mutation (all security-critical mutants killed, 19 real gaps pinned by 16 behavior tests) -> Codex final GO. Branch merged; D2-cycle remains parked for V2.
- **Next.** D2c-ii (categorical/bucket_perturb/date_shift index kernels) via the same framework.

### 2026-10-12 -- Phase D / D2b: SEQ-route hash native across FK shapes + composite keys MERGED (engine PR #242)

Extends D2a's native-SEQ `hash` across every acyclic FK shape that masks today, so the sequential (large-relational) route runs native for real linked-table workloads.
- **What it did.** A separate REMAP-only decision map keyed on any column that is a parent key of an edge, so a chain's middle column (child AND parent) re-derives orphan keys on the kernel while matched children still inherit (never rehashed). Native + byte-identical (modulo accepted NFC) across chain, diamond (first-hit-wins), multi-parent (policy-conflict guard intact), self-reference (drain-fold), junction, and single-level composite keys (per-member admission; a mixed admitted/declined tuple is native/Python per member). A new SEQ-only runtime wrapper declines a composite MULTI-HOP chain (which errors on every path today) with a clean coded reason only when a genuine orphan hits it; matched-only composite chains run native. Shared orphan path and full-frame untouched.
- **Why it matters.** The sequential route carries the big relational jobs the out-of-core route declines; D2a made single-hop hash native, D2b makes it native across the real relationship shapes. Perf: ~1.8-2x on a 1M-row chain+composite workload, identical digests, memory neutral.
- **Gate chain.** Codex plan GO (2 rounds) -> build -> independent verification (caught + remediated the over-broad preflight decline -> runtime, and a type fix) -> dennis APPROVE (0 blocker/high/medium, 2 LOW) -> Codex final GO (0 blocker/high/medium, 1 LOW). Both reviewers confirmed REMAP-native-per-hop and that the decline wrapper doesn't swallow legitimate errors. Follow-ups (non-blocking): the decline attributes by child table not failing edge (contrived mislabel, aborts safely) -> thread the failing edge; add a FAIL-policy composite-chain test.

### 2026-10-12 -- Phase D / D2a: SEQ-route parity contract + hash on the compiled kernel MERGED (engine PR #241)

First native slice on the sequential (SEQ) FK route. SEQ is the bounded, table-at-a-time pandas route that carries every relational masking job too large for full-frame and declined by the out-of-core route; its masking was pure Python. D2a lands a strict SEQ parity contract + a SEQ-specific native-execution witness, then moves the `hash` operator onto the compiled companion kernel there.
- **What it did.** A run-scoped per-column hash decision (pinned Arrow type at table prep) reuses the D1a `out_of_core/_hash_native.py` kernel unchanged, byte-identical to the Python hash handler except the pre-accepted NFC divergence. Three FK paths are distinct: native parent/payload derivation at the handler seam; a matched child inherits the parent's masked key via `resolve_fk_keys` (no kernel call); REMAP orphan keys mint on the companion only when the parent ran there. The decision is transported via a context field set only by `run_sequential`, so full-frame and chunked routes never reach the kernel. SEQ's bounded pandas orchestration is retained. Admission stays behind the existing ingest guards; no fallback after a native selection; abort/no-commit scoped to a transactional sink; value-free disposition on `quality_metrics`.
- **Why it matters.** The SEQ route carries the large relational jobs OOC declines, and its masking was entirely Python. This is the first operator (`hash`, payload + FK keys) moved onto the fast kernel there. Perf: the hash step ~6.6x faster (14.6s vs 95.9s on a 5M-row parent+FK-child), 2.13x total, identical output digests, memory neutral.
- **Referential integrity.** A child's masked key equals its parent's by token-copy within the run; orphan (REMAP) keys reference no parent so the native/Python split across orphan batches stays within the accepted NFC envelope and breaks no RI constraint. dennis and Codex both confirmed this specifically.
- **Gate chain.** Codex plan gate GO (2 rounds) -> build -> independent verification -> dennis APPROVE (0 blocker/high/medium, 2 non-blocking LOW; REMAP RI + witness non-fakeability confirmed) -> Codex final GO (0 blocker/high/medium, 1 doc LOW applied). ci-mirror full suite 24087 passed; abi-3 tier 10863 passed/0 failed incl all sentries + the D1a/D1b-i/D1b-ii/D1c regressions. Follow-ups (non-blocking): a cross-table REMAP MIXED edge (inside the NFC envelope); 4 pre-existing `dict_uint64` failures on the native CHUNKED route (unrelated to SEQ, tracked for the companion test job).

### 2026-10-12 -- Phase D / D1c: date sentinel-preserve MERGED (engine PR #240)

Lets a user mark exact dates to pass through `bucket_perturb` and `date_shift` unchanged, so sentinel markers (`9999-12-31` "never expires", `2099-01-01` "unknown") survive masking and downstream `= sentinel` checks keep working. Previously an in-range sentinel was perturbed like any other date and broke the check; an out-of-range one survived only by accident (it failed to parse).
- **What it did.** A per-field `preserve_values` list (requires an explicit `date_format` when set). A row whose date matches a listed literal is physically excluded from compute on every route (oracle, native-chunked, native full-frame, and out-of-core bucket_perturb) before any parse/derive/arithmetic/format, and its source rendered back as a string. Everything else masks exactly as before; unset means byte-identical output to today. Matching uses the operator's own pandas parse, with a full-range Python fallback only for out-of-range sentinels pandas cannot represent. A value-free preserved-row count is surfaced on the run metrics (no literals logged).
- **Why it matters.** Sentinel dates carry meaning that masking must not destroy. This makes preservation explicit and user-controlled, closing the gap where in-range markers were silently moved.
- **v1 scope (fail-closed).** Payload dates and single-hop scalar foreign-key dates (parent-owned, child inherits). Multi-hop FK chains, composite keys, same-table edges, multi-parent shared children, and the `group_by` combination are compile-rejected with clear codes rather than risk referential integrity; recorded as v2.
- **Gate chain.** Plan gate GO (Codex, 4 converging rounds) -> build -> independent verification -> dennis APPROVE (0 blocker/high; a commit-security "masking bypass" flag did NOT reproduce - no over-preserve path on any route) -> Codex final GO (0 blocker/high, no over-preserve scenario). Both reviewers independently confirmed preservation emits only the exactly-configured dates. Three CI-surface fixes rode the merge (a docs cross-ref, a pre-existing C6b-i stale gate test re-pointed to `bucketize`, and the G4 adapter-call pin declaring the new metric call). Follow-ups tracked (non-blocking): preserved-count propagation through multi-table/auto-chunk merge paths (evidence-only), two test-hardening items, and a docs cross-reference.

### 2026-10-12 -- Phase D / D1b-i: bucket_perturb masking native on the out-of-core route MERGED (engine PR #239)

Completes the D1 native operator group (hash = D1a, categorical = D1b-ii, bucket_perturb = D1b-i). The out-of-core route previously perturbed dates by running `apply_bucket_perturb` over a pandas Series; D1b-i routes that compute through the existing compiled index kernel for columns it handles identically, graded against the D0 parity contract and witness.
- **What it did.** A new adapter dispatches bucket_perturb to the native operator when the column is admissible (a `string` source whose config the shared resolver accepts); everything else keeps the Python path with a caller-visible reason (non-string sources, tz directives, no companion). The decision and pinned source type are fixed once per run; a batch whose type drifts, a missing pinned column, or a mid-run kernel fault aborts the sink with nothing committed (never half-native); empty/all-null batches short-circuit with no kernel call. The reference path (`apply_bucket_perturb`) and the shared native operator (`native_bucket_perturb`) are untouched, and config validation keeps its existing stages and order so a config that errors on Python errors identically before the kernel is reached.
- **Why it matters.** Closes the D1 group's third and last operator, so the three most common out-of-core date/value masks (hash, categorical, bucket_perturb) now run native. Perf: native p50 7.70s vs Python 344.6s on 5M rows (~45x), peak RSS 226 MiB against a 1024 MiB ceiling, byte-identical output digest.
- **Date-range limitation (accepted, Cam 2026-10-11).** The native operator does its bucket arithmetic on pandas Timestamps (1677-09-21 to 2262-04-11); a parseable date within one bucket of either bound fails the job with a clear reason rather than risk a silently wrapped result, and running without the companion perturbs those near-bound dates on the Python path. Dates outside the range entirely (such as `9999-12-31`) pass through unchanged on both paths.
- **Accepted difference (Cam 2026-10-11).** bucket_perturb keys its in-bucket position on the NFC-canonicalized source, so native and Python can select a different position for a date_format carrying a codepoint newer than the running Python's Unicode version. Native is canonical; characterized, locked, version-guarded, and documented (`decoy-engine/docs/strategies.md` bucket_perturb, `compatibility-contract.md` 3.3).
- **Gate chain.** Plan gate GO (rev 6, after six rounds that resolved the config-classification precedence, the silent-wrap guard, the source-type binding, and the validation ordering) -> build (4 green commits) -> independent verification -> dennis APPROVE (0 blocker/high/medium, 2 non-blocking LOW) -> Codex final GO (0 blocker/high/medium, 1 doc-precision LOW applied). The one companion-present native-suite failure is pre-existing (C6b-i's text_mask admission, an ancestor of base) and unrelated; tracked as a C6b-i follow-up.

### 2026-10-12 -- Phase D / D1b-ii: categorical masking native on the out-of-core route MERGED (engine PR #238)

Completes the D1 operator group (hash = D1a, bucket_perturb = D1b-i pending). The out-of-core route previously remapped deterministic `categorical` values onto the category pool in a pure-Python loop; D1b-ii routes that through the existing compiled index kernel for eligible columns, graded against the D0 parity contract and witness.
- **What it did.** A new adapter dispatches categorical to the native operator when the column is admissible by one shared two-stage predicate (deterministic + namespaced + string-category config, AND a `string` source); everything else keeps the Python path with a caller-visible reason (non-string sources, non-finite weights, no companion). Decision + prepared pool/CDF + pinned source type fixed once per run; drift/missing-column/kernel-fault abort the sink with nothing committed; empty/all-null batches short-circuit to null with no kernel call. The oracle, the native operator, and the config/prep resolver are untouched.
- **Why it matters.** Proves the native-OOC mechanism on the operator with per-run prepared state, closing the D1 group's core. Perf: native p50 ~2.1s vs Python ~44s on 5M rows (~20x), peak RSS ~216 MiB against a 1024 MiB ceiling, byte-identical output digest.
- **Accepted difference (Cam 2026-10-11).** Categorical keys on the NFC-canonicalized source value, so native and Python can pick a different category for source text with a codepoint newer than the running Python's Unicode version. Native is canonical; characterized, locked, version-guarded, and documented (`decoy-engine/docs/strategies.md` categorical, `compatibility-contract.md` 3.3).
- **Gate chain.** Plan gate GO (rev 2) -> build -> independent verification -> dennis APPROVE (0 blocker/high/medium) -> Codex final found + got remediated one HIGH (the witness IDLE state could mislabel a populated Python batch, laundering a mixed column as native) then GO. The 5 native-suite failures are pre-existing on the native-chunked route (reproduced on base).

### 2026-10-11 -- Phase D / D1a: out-of-core hash masking on the compiled companion MERGED (engine PR #237)

First real OOC kernel slice of Phase D. The out-of-core route previously computed the `hash` strategy in a pure-Python per-value loop; D1a routes that compute (payload and parent-key hash columns, through `mask_batch` on both streaming drivers) to the existing compiled companion kernel for parity-eligible admitted Arrow types, graded against the D0 parity contract and witness.
- **What it did.** Admitted-type hash columns (utf8/large_utf8/bool/int and uint widths) now mask on Rust/Arrow instead of the Python loop. Everything else takes an explicit declined-with-reason Python path, surfaced per column on `ExecutionResult.quality_metrics` and visible through `run_pipeline`: the REMAP join sites and tz-aware timestamps are deferred, non-admitted types keep their typed errors. The decision is pinned once per run; a batch whose type drifts, or a missing pinned column, or a mid-run kernel fault, aborts the run with nothing committed (never half-native). The companion is loaded once and threaded into the per-batch call. Reuses `derive_batch`; no new Rust, no ABI change, `hash_array` untouched.
- **Why it matters.** Proves the native-OOC mechanism on the simplest operator before categorical and bucket_perturb follow (D1b). Perf: native p50 1.85s vs Python 41.9s on 5M rows (~20x), peak RSS 219 MiB against a 1024 MiB ceiling, byte-identical output digest across backends.
- **Normalization decision (Cam, 2026-10-11).** The native (Rust) and Python paths NFC-normalize text under different Unicode versions, so hash tokens can differ for text with codepoints newer than the running Python's Unicode version. Native is canonical; the difference is accepted, characterized, token-locked, version-guarded, and documented (`decoy-engine/docs/strategies.md` hash, `compatibility-contract.md` 3.3) with the Python-only to companion-present join-stability caveat.
- **Gate chain.** Plan gate GO (rev 5, after four rounds that caught a timestamp parity trap, a reachability error, and the Unicode-version divergence) -> build (5 green commits) -> independent verification -> dennis APPROVE (0 blocker/0 high) -> Codex final GO (no must-fix). The 5 native-suite failures are pre-existing on base (native-chunked route, untouched) and companion-only; the companion-less path (CI default) is fully green.
- **Deferred (non-blocking LOW).** Empty-REMAP and zero-row declined columns report a backend label where `none` would read cleaner (reporting only); a `_stream_driver_support` docstring now serves both drivers.

### 2026-10-11 -- Phase D / D0: strict parity contract + native-execution witness MERGED (engine PR #236)

First build-slice of the Phase D (Rust FK routes) program. TEST-ONLY -- no kernel, no `src/` change. Groundwork that de-risks every later FK-kernel slice.
- **What it did.** Froze the contract that later FK-kernel slices are graded against, so a kernel slice cannot silently drift the FK output or claim native execution it did not perform. Three test-side pieces: (1) a strict per-executor parity comparator (9 independent dimensions -- schema structure, field metadata, type width, column/row order, row set, cellwise, null-vs-NaN -- that do NOT fold like the existing normalized harness); (2) a frozen baseline case table over the OOC FK single-edge chain, pinning each executor's exact field definitions (name/type/nullability/field-metadata), cells, and rejection codes as hardcoded literals, with the known gaps characterized (pandas schema metadata, NaN-vs-null, empty-child and all-null FK schemas) and int64-vs-float64 frozen as a probe-verified AGREEMENT rather than a fabricated delta; (3) a native-execution witness that patches the OOC `_mask` kernel bindings where they are looked up, reads provenance from the actual returned object, and requires the native result to be the one consumed (a native-then-fallback does not satisfy it).
- **Why it matters.** The parity contract carries the GATE-TQ0 byte-parity lineage. Building it before any Rust kernel means D1 lands against a proven, honest harness instead of a harness shaped to pass it.
- **Gates.** Codex plan gate GO (5 rounds -- design locked at r2, later rounds tightened fixture facts I confirmed by probing the engine directly). Build by subagent, diff independently verified test-only. ci-mirror PASS (ruff/format/mypy clean, 336 passed). dennis adversarial APPROVE (0 blocker/high, 2 LOW carry-forwards). Codex cross-model final GO after one HIGH found-and-fixed (the baseline originally under-pinned -- it asserted the per-dimension verdict but not absolute per-field nullability/metadata, so a mutation could widen a known gap undetected; now pins exact per-field defs with negative controls proving it bites). Engine GitHub CI green on the PR and the merge; nightly testflight green.
- **Carry-forwards to D1.** Witness per-column attribution (concat-equality) needs hardening when a chunked or multi-column native kernel lands (dennis L1). The `ci-mirror` editable venv `.pth` was stale (pointed at a pruned worktree) and needed `--rebuild`.

### 2026-10-11 -- P6b: create_job_core split into named phases MERGED (platform PR #93)

Refactor track (P6 follow-up). Groundwork, not a feature.
- **What it did.** The job-creation entry point `create_job_core` was one ~450-line function running every pre-create step inline (pipeline resolve, idempotency, environment/role gating, stored-config size guard, YAML selection, mode, seed, preflight, per-run binding, admission sizing, persistence, audit). P6b extracts those into named phase helpers in a new `api/jobs/_create_phases.py`; the main service file drops 574 -> 291 lines.
- **Proven to change nothing.** Behavior-preserving: a 62-case observable baseline (the persisted job row, audit rows, HTTP status/detail, config snapshot hash, and whether caller inputs were mutated) was captured on the old code and reproduced exactly; the auth/permission gating order, the three stored-config guard points, idempotency, preflight severity handling, and the audit entry are all unchanged.
- **Gates.** Codex plan gate GO, build, independent anti-laundering check, dennis GO (0 blocker/high), Codex final GO. Platform GitHub CI is on the billing hold, so the local gate chain is the verification; the one remaining backend failure is the known pre-existing r6_3 audit-coverage blind spot (a retrieval route that authenticates in-handler), unrelated to this change and tracked separately.

### 2026-10-10 -- P6: platform job-runner refactored (run context + per-route executors) MERGED (platform PR #92)

Refactor track (before Phase D). Platform sibling of engine R3. Groundwork, not a feature.
- **What it did.** The platform's main job-runner function had grown a ~506-line, 28-branch body with route selection split across two code paths. P6 replaces that with a run-context object, one decision step, and four named route executors behind a small dispatch, so the next big step (adding Rust foreign-key routes in Phase D) adds a route by adding an executor instead of threading another branch. The main file shrank 580 -> 340 lines.
- **Proven to change nothing.** Behavior-preserving: before the refactor we captured a byte-level snapshot of the job runner's observable output (status, evidence manifest, per-node records, metrics) across 24 route/flag combinations plus 27 failure/cancellation/cleanup traces, and the refactored code reproduces them. The subtle platform-specific invariants were explicitly preserved: scheduler evidence stays gated on an authoritative plan, the error path still reads the corrected route and commit flags, and the exact try/finally boundaries are unchanged.
- **Gates.** Codex plan gate GO (4 rounds; it caught that the platform runner is trickier than the engine and the first plans oversimplified it), build, independent anti-laundering check, dennis GO (0 blocker/high/medium), Codex final GO (0 findings). Platform GitHub CI is on the billing hold, so the local gate chain is the verification; the ~36 devbox suite failures are confirmed environmental/pre-existing, not P6.
- **Next:** `create_job_core` phase extraction (P6b), then Phase D (Rust FK routes).

### 2026-10-10 -- R3: pipeline internals refactored so the Rust foreign-key work can land cleanly MERGED (engine PR #235)

Refactor track (before Phase D). Groundwork, not a feature.
- **What it did.** The engine's main pipeline function had grown a ~37-argument signature plus a workaround that forwarded its own local variables through a hidden hack, and its execution routes were shaped inconsistently. R3 replaces that with one clean run-context object, gives all three in-memory routes a uniform named entry point, and deletes the workaround. This is what the big foreign-key/Rust work (Phase D) was waiting on. The main pipeline file shrank from 684 to 306 lines.
- **Proven to change nothing.** Behavior-preserving: before the refactor we captured a byte-level snapshot of every route's output, errors, warnings, ordering, and telemetry on the current main, and the refactored code reproduces it exactly. Routing logic and the public pipeline signature are untouched.
- **Also banked.** A reconciliation record confirming the out-of-core reorder lane is the live, tested design (not a remnant of a reverted experiment), which Phase D needs before it removes any legacy foreign-key code paths.
- **Gates.** Codex plan gate (4 rounds; round 1 caught a real call-graph error in the plan before any code was written), build, independent anti-laundering check (only the pre-approved test changes landed), dennis GO (0 blocker/high/medium, 1 doc fix), Codex final GO (0 findings), ci-mirror clean, full engine CI green.
- **Next:** the platform half (P6) as a sibling slice.

### 2026-10-10 -- C6b-fakerfix: text masking's fake-value step is ~10x faster MERGED (engine PR #234)

Phase C. Follows C6b-i.
- **Same masked output, much faster fake-value generation.** When text masking replaces a detected name/address with a realistic fake, it was rebuilding the whole fake-value generator from scratch for every single match. It now reuses one generator (re-seeded per match), which is byte-for-byte identical output and about 10x faster on that step (912us -> 90us per fake-value span). On a realistic mixed note that roughly halves the per-cell cost.
- **Proven identical, not just faster.** The change was checked against the old behavior across ~6,800 cross-model parity probes with zero differences, plus a test that fails if the generator is ever rebuilt per match (so the speedup can't silently regress). Keying, which values are masked, and the no-raw-data-in-logs guarantee are all unchanged.
- **Why it mattered first.** Measuring text masking showed the slow part is the per-match work, not detection, and this fake-value rebuild was the single biggest chunk. The remaining heavy cost is the fake-value generation itself and the ML name-detector, which can't move off Python, so the planned Rust version is now a narrower decision (for ID-encryption-heavy columns only) that's back with Cam.
- **Gates.** Codex plan gate (3 rounds), build, dennis GO (2 minor; one test strengthened, one noted as a follow-up), Codex final GO, ci-mirror clean.

### 2026-10-10 -- C6b-i: text masking no longer drags its whole table onto the slow path MERGED (engine PR #233)

Phase C.
- **A text-masking column stops slowing down its neighbours.** "Text masking" scans free-text cells for PII (names, SSNs, emails, etc.) and masks each hit. Until now, a column using it forced its entire table, every other column included, onto the slower general-purpose path. It now runs on the fast path, so the rest of the table stays fast. Same masked output, byte-for-byte.
- **No shortcuts on correctness.** Text masking is key-driven and does a lot per cell (different hits can be encrypted, faked, date-shifted or redacted), so the fast-path version reuses the exact same masking engine rather than reimplementing it: identical values, warnings, and errors. The one case that needs the ML name-detector still uses the normal path.
- **Speed note.** This slice is about routing, not per-cell speed; a dedicated fast kernel for the per-cell work comes next (C6b-ii).
- **Gates.** The cross-model review caught two ordering mismatches on the chunked path: when two columns both failed, and the order warnings came out, didn't match the normal path. Both fixed at the source (process columns in the same canonical order the normal path uses), which also corrected the same latent quirk for the encryption feature.

Gates: Codex plan gate, Opus build, dennis GO (2 minor fixes), Codex final gate NO-GO on 2 ordering defects -> fixed -> dennis re-check GO -> Codex final GO, ci-mirror clean. One pre-existing, unrelated error-message-wording difference in the encryption feature noted for a later cleanup.

### 2026-10-10 -- C6a: format-preserving encryption runs on the fast Rust path MERGED (engine PR #232)

Phase C.
- **Faster, same output.** Format-preserving encryption (turns an ID or account number into a realistic, reversible fake one) now runs on the fast Rust path on both routes, byte-for-byte identical to the normal path. 1M rows encrypt in ~6s single-thread, ~1.8s on four.
- **No hand-rolled crypto.** Uses an audited FF1 crate, proven identical to our existing Python cipher across thousands of vectors (every alphabet size, the official NIST samples).
- **Stays correct by declining the hard cases.** Checksum modes (Luhn/NPI/IBAN/etc.) and a missing companion both fall back to the normal path, unchanged; a bad value fails the whole job with the same error it always did.
- **Gates.** The cross-model review caught two edge cases, both fixed: a validation-order mismatch on an unusual oversized-alphabet config, and a test that was checking the fallback's error rather than the fast path's. CI now runs the Rust crate-parity gate, the fast-path acceptance tests, and a guard against a version record silently drifting.

Gates: Codex plan gate, Opus build (foundation + route wiring), dennis BLOCK on CI-coverage gaps -> fixed -> dennis GO, Codex final gate (2 edge cases -> fixed -> GO), ci-mirror clean. One pre-existing, unrelated test-vs-pyarrow-version issue noted for later.

### 2026-10-09 -- C5c-ii: repeatable fake names/IDs over number columns run on the fast chunked path MERGED (engine PR #230)

Phase C. Follows C5c-i and C5c-a.
- **Faster, same output.** A "repeatable fake value" column (a stable fake name or ID keyed off a real number, boolean, or integer column) now runs natively on both fast paths, byte-for-byte identical to the standard path.
- **One empty-only edge made consistent.** When such a column comes out entirely empty or all-blank, its type is now recorded as text on every path (it used to vary by path). This is a small pre-GA output-type change for that empty-only case (Cam's option A), matching how the other fake-value and category columns already behave.
- **Stays correct by refusing the unsafe case.** If someone registers a fake-value provider under a known name but makes it return numbers instead of text, the fast chunked path now stops with a clear message instead of silently turning the numbers into text. This was a real bug the final cross-model review caught: without the guard, the fast path would have quietly changed those values. The standard (whole-table) path was already correct.

Gates: Codex plan gate (with a mid-plan remediation for the chunked path), Opus build (tests-first), dennis APPROVE, Codex final gate (found and we fixed the numbers-into-text bug), Codex re-gate GO, a focused dennis re-review of the fix, full engine test sweep green (18,349 passed), ci-mirror clean. Temporal and decimal fake-value sources remain not planned.

### 2026-10-09 -- C6c-ii: Rust text-redaction speedup MERGED (engine PR #229)

Phase C. Follows C6c-i. First the slow part was measured to confirm it was worth doing: redacting PII inside free-text columns (clinical notes) ran at ~32k rows/second, about 8x slower than the other masking types, so a large notes column was the bottleneck.

- **Faster, same output.** The detection for eight of the eleven built-in PII patterns (email, phone, card number, IBAN, IPv4, ICD-10, NPI, URL) plus their validators now run in a compiled Rust component instead of the per-row Python loop. On representative clinical text it is about 2.1x faster, and the redacted output is byte-for-byte identical to before.
- **Correct on every input, by routing not by luck.** The Rust path only runs on cells that are plain ASCII (which is the vast majority of real clinical text), where it provably matches the old behavior exactly. Any cell with unusual characters (non-ASCII digits, control separators) or the three boundary-sensitive patterns (SSN, ZIP, street address) falls back to the original Python path, so nothing is ever mis-redacted. No companion installed, or an out-of-date one, also falls back.
- **Memory stays bounded.** A first full-size (1M row) run showed the new path using too much peak memory because it processed the whole column at once; fixed by working in fixed batches, so memory no longer grows with column size. Re-measured within budget.

Gates: Codex plan gate (4 rounds, correctness validated with ~17k checks), Opus build (tests-first), dennis APPROVE (260k+ sample comparisons, zero differences), Codex final GO (another ~140k comparisons), a focused re-review of the memory fix, ci-mirror clean, and full engine CI green. One deferred non-reachable item: a numeric-offset widening that only matters for a single cell larger than 4 GiB (which cannot occur).

### 2026-10-08 -- C8-iii-d-2: filtered random-value columns run on the fast paths MERGED (engine PR #228)

Phase C. Follows C8-iii-d-1.
- **Fast paths for filtered random values.** "Only mask rows where..." filters on a column that draws random-but-stable values (a non-deterministic category picker, or a reused fake-value column) now run on both fast paths, not only the standard path. The output is byte-for-byte the same as the standard-path version from d-1, because the fast paths key each selected row on the same whole-table row number.
- **Two shapes still take the standard path.** A filtered date-window column (no fast-path version yet) and a filtered fake-value column drawn from a number column both still run on the standard path, same result.
- **Stays correct by refusing the unsafe case.** When a filter would need the fast path to compare against a non-text column, it declines with a clear reason rather than risk picking different rows per chunk. Columns with no filter are unchanged.

Gates: Codex plan gate (3 rounds), Opus build, dennis GO (two low notes folded: delete an unused fixture, tighten an equality check to exact byte identity), Codex final GO, ci-mirror PASS. Post-rebase: two test fixtures had assumed the wrong decline reason and were corrected (see #226 note); a stray packaging file and a duplicate lint entry from the rebase were removed.

### 2026-10-08 -- C8-iii-d-1: filtered random values stay put when the filter changes MERGED (engine PR #227)

Phase C.
- **Stable values under a filter.** When a filter is applied to a column that draws random-but-stable values (a non-deterministic category picker, a reused fake-value column, or a date-window column), each selected row now gets the value it would have had with no filter at all. Changing the filter, or adding rows elsewhere in the table, no longer reshuffles the values of rows that did not themselves change.
- **Scope.** This is a pre-GA output change for those three column types when they carry a filter (Cam's call). Columns with no filter are byte-identical to before, as are nested children and the order-sensitive strategies (shuffling, unique/match/scale fake values, joint masking). This slice covers the standard path; the fast-path version is d-2.

Gates: Codex plan gate (2 rounds), Opus build, dennis GO (two low doc notes folded), Codex final GO, ci-mirror PASS. A stray strace packaging file accidentally committed during the build was removed before merge.

### 2026-10-08 -- C8-iii-c: every filter now goes through the same safe grammar MERGED (engine PR #226)

Phase C.
- **One rule, every door.** The "only mask rows where..." filter language is a fixed, safe subset of expressions. That rule was already enforced when a job config loaded the normal way, but a few side doors (a raw config dictionary, a stored plan, a direct engine call) skipped it and ran the filter through general evaluation. Every door now enforces the same rule, with a clear error that names the column.
- **Errors no longer echo the filter.** A filter can contain real data values (for example `ssn == '123-45-6789'`). The error messages and stack traces now name only the column and masking type, never the filter text.
- **Scope.** Pre-GA behavior tightening; a filter outside the safe subset that used to slip through now fails up front with a migration table in the changelog for the old forms.

Gates: Codex plan gate (3 rounds), Opus build, dennis GO, Codex final GO, ci-mirror PASS. Post-rebase, two test fixtures that had been migrated to the new rule were asserting the wrong decline reason; both were corrected to the real reason (a stable numeric filter is now admitted to the fast path; a date-bucketing filter declines because of its settings, not its grammar), verified, and merged.

### 2026-10-07 -- C8-iii-b: filters that read number columns keep jobs on the fast path MERGED (engine PR #225)

Phase C.
- **More filters stay fast.** A large job whose filter compares against a number, date or long-text column now stays on the fast path (auto-chunking) instead of dropping to the slow whole-table path, as long as the engine can confirm the column has no empty cells. The filtered selection and every masked column match the whole-table run.
- **What still runs whole-table.** A filter that reads a number or true/false column that has empty cells, or has no empty-cell count recorded, or reads a more exotic column type, still runs whole-table. The masked target column must still be text.
- **Exact passthrough.** The columns a filter reads, when passed through, keep their exact original type and values, so these jobs now show the fast path's normal small differences from a whole-table run (a not-a-number value stays as-is; long-text and 64-bit-date columns keep their type).

Gates: Codex plan gate (4 rounds), Opus build, dennis GO, Codex final GO, ci-mirror PASS.

### 2026-10-07 -- Date-bucketing settings that destroyed dates now fail up front MERGED (engine PR #224)

Phase C. The "next fix" promised in the C8-iii-a note.
- **Fixed a silent data-destroyer.** A date-bucketing column whose format setting had no date in it (for example `ISO8601`, `mixed`, or a typo like `foo`) used to replace every date with the format text itself. The job reported success and the column held the same literal string in every row. It now stops before any masking or output, with a clear error that names the column and asks for a real pattern such as `%Y-%m-%d`.
- **Checked everywhere.** The check runs when the config compiles and in a config-only check, covers a nested date-bucketing child column, and is repeated in the handler and both large-job paths for configs that skip compile. The fast path declines the same settings.
- **Still accepted.** A format that has a real date in it still works and gives the same output; leaving the format unset still auto-detects.

Gates: Codex plan gate, Opus build, dennis GO, Codex final GO, ci-mirror PASS.

### 2026-10-07 -- C8-iii-a: filters for three more masking types on the fast paths MERGED (engine PR #223)

Phase C.
- **More filtered masking on the fast paths.** "Only mask rows where..." filters now run on both fast paths for text redaction, date bucketing and date shifting. At 1M rows with 10% selected, date bucketing went from 8.4 s to 0.4 s and date shifting from 1.2 s to 0.6 s. Text redaction gains nothing yet, because its detection is pure Python everywhere; the planned Rust version (C6c-ii) is the fix.
- **Date errors in the right place.** Dates that cannot be read are reported at the right row, and only for rows the filter picked.
- **Crash fixed.** Two loose date-format settings (`mixed`, `ISO8601`) made the fast path crash on dates with different time zones. Those jobs now run on the standard path.
- **Known issue found, next fix.** Those two settings write the format's name over every date, on every path, and always have. Cam chose to reject them with a clear error; that fix is being built.

Gates: Codex plan gate (3 rounds), Sonnet build, dennis (blocked a misleading release note, now fixed; code checks all matched), Codex final GO with no findings, ci-mirror PASS.

### 2026-10-07 -- Memory evidence for silent crashes (engine PR #222)

Follows the flaky out-of-memory test. In CI it showed a job dying with a segmentation fault and no message.
- **New:** while a memory-capped job runs, Decoy watches its memory use. A job that crashes with no message now carries a record of its memory at the time. A "likely memory pressure" flag is set when it died close to its cap.
- **Outcomes unchanged** (Cam's call: "evidence, not relabel"). A crash is still reported as a crash, so nothing gets wrongly retried. The evidence just makes it explainable.
- **Honest limit:** it is a strong hint, not proof. A job that asks for one large block of memory and is refused can still crash without the flag. Per-job kernel memory groups are the recorded upgrade path if this proves not enough.

Gates: Codex plan gate (3 rounds; it showed the first "relabel" idea could not be made reliable, which led to Cam's choice), Sonnet build, dennis GO (fixed how the age of a reading is measured), Codex final GO in round 2 (round 1 caught a reading being stamped too late), ci-mirror PASS.

### 2026-10-07 -- C5c-a deterministic fake values on whole-number columns with empty cells MERGED (engine PR #221)

- **Fixed.** Deterministic Faker on a whole-number column with empty cells used to fail the whole job. Pandas turned the numbers into decimals, and Faker refuses decimals. It now works (Cam's call). Each number gets the same fake value it would get in a column with no empty cells, including very large numbers.
- **Nothing else changes.** The fix hands Faker the original numbers directly, so the rest of the job sees the data exactly as before. 11 recorded baselines of jobs that already worked stay byte-identical.
- **Known limit.** A filter that masks only some rows of a number column with a text provider can still leave a mixed column, which fails on save. That was already true before this fix.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (2 medium fixes), Codex final GO in round 2 (round 1 caught a rare naming collision with nested Faker, now fixed), ci-mirror PASS.

### 2026-10-07 -- C5c-i random fake values on number and true/false columns MERGED (engine PR #220)

Phase C.
- **More columns on the fast path.** Random (non-deterministic) Faker now runs on the fast paths for whole numbers, decimals and true/false columns. Before, only text columns could. Output is identical to the reference path.
- **Empty cells decided the pandas way.** This Faker only needs to know which cells are empty. The fast path asks pandas, using the same conversion the reference path uses. That matters because pandas treats some "not a number" values as real values in some formats.
- **Text columns unchanged.** They keep their original fast check, so they lose no speed.
- **Still on the slow path:** dates, times, money-style decimals, nested data, and deterministic Faker on non-text columns (next slices).

Gates: Codex plan gate (3 rounds; it narrowed the slice after finding five problems in the first design), Sonnet build, dennis GO (1 medium fix), Codex final GO with no findings, ci-mirror PASS.

### 2026-10-07 -- Memory-capped jobs report out-of-memory correctly (engine PR #219)

Follows an intermittent CI failure where a capped job that ran out of memory was reported as "crashed".
- **Named correctly.** Memory failures in the steps after a job's main work, and in the worker's outer handler, are now reported as "ran out of memory", not "crashed".
- **No data in stored errors.** One Arrow memory error used to copy a raw data value into the stored error text. The value is now removed before storing, in both the isolated and the in-process path.
- **No leftovers.** A job that reports its own failure no longer leaves partially written output behind.
- **Not yet known.** The exact cause of the original CI failure is still unexplained. The test now prints the full error shape, so the next occurrence will tell us. A deeper fix (watching the job's memory directly) is held until that evidence exists.

Gates: Codex plan gate (3 rounds; it caught that a first idea would break jobs that work today), Sonnet build, dennis GO (2 medium fixes), Codex final GO, ci-mirror PASS. 40 of 40 soak runs classified correctly.

### 2026-10-07 -- FPE test stand-in fixed for empty cells (engine PR #218)

- **What it is.** The internal stand-in that the future Rust format-preserving-encryption kernel will be checked against. It used to try to encrypt empty cells and report an error. The real masking passes empty cells through unchanged, and now the stand-in does too.
- **Why it matters.** It had to be right before the Rust version is built, or that version would copy the mistake. Nothing users see changes.
- **Found along the way.** The stand-in also treats one kind of pandas missing value differently from the real masking. That is noted for the Rust FPE work (C6a).

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (540-case comparison), Codex final GO, ci-mirror PASS.

### 2026-10-07 -- C8-ii `when:` filters on the whole-table fast path MERGED (engine PR #217)

Phase C.
- **Whole-table fast path.** Single-table jobs whose "only mask rows where..." filters use hash, redact, truncate or deterministic categorical on text columns now run on the whole-table fast path. Before, they used the slow path. Output matches exactly, including column types.
- **Same filter meaning.** The filter is checked once, by the same pandas code the reference path uses, so the rows picked are identical. If a filter cannot be checked, the job goes to the reference path before anything runs, so it reports the same error.
- **Faster filtered masking on both fast paths.** Masking now runs only on the rows a filter picks, so a filter that picks few rows costs little. Before, every row was masked and the unpicked ones were thrown away.
- **Safety.** A filtered column can never be masked unfiltered, whatever its masking type.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (2 medium fixes: the low-selectivity cost and the unfiltered-run guard), Codex final GO in round 1 with no findings, ci-mirror PASS.

### 2026-10-06 -- Nightly ship-gate test fixed (engine PR #216)

- **What broke.** From Oct 6 the nightly ship-gate test failed on one job's recorded output fingerprint. C5b-i (#205) had changed random fake names and emails on purpose, and the recorded fingerprint was never updated.
- **Fix.** The fingerprint is re-recorded. Between the commits before and after #205, only those two columns differ, and repeated fresh runs give the same result.
- **Process.** A deliberate output change now updates the ship-gate fingerprint in the same slice, and each loop iteration checks the nightly run.

Gates: dennis GO, Codex final GO, ci-mirror PASS.

### 2026-10-06 -- C5b-iii position-keyed categorical and Faker on the whole-table fast path MERGED (engine PR #215)

Phase C.
- **Whole-table fast path.** The seeded random categorical and the random (non-deterministic, reuse) Faker now run on the whole-table fast path. Before, only the chunked fast path ran them, and a whole-table job fell back to the slow path.
- **Same output.** Output matches the reference path exactly, including tables processed in several batches and nulls at batch edges.
- **Stricter evidence check.** Only the random Faker may report "no kernel ran" on an empty table. Every other operator must still show its fast kernel ran.
- **Existing jobs unchanged.** Deterministic Faker, deterministic categorical and hash keep the same output and evidence.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (2 small fixes), Codex final GO in round 1 with no findings, ci-mirror PASS.

### 2026-10-06 -- C8-i public `when:` and native `when` on the chunked route MERGED (engine PR #214)

Phase C.
- **Public `when:` field.** A column's `when:` filter ("only mask rows where...") is now part of the public config. It accepts a small, safe language checked when the config is loaded: column names, values, comparisons, `in` lists, `and`/`or`/`not`. Anything else, including function calls, is rejected with a clear error at the right place in the config. Cam chose this closed language. Older raw-dict callers keep the old behavior for now.
- **Fast path.** Tables with `when:` filters on hash, redact, truncate or deterministic categorical columns no longer fall back to the slow path on the chunked route. The rows to mask are picked by the same pandas code as before, so results match. Only the masking runs on the fast path.
- **Existing jobs unchanged.** Jobs that do not use `when:` keep exactly the same config fingerprint as before, which a test locks in.
- **Not yet covered:** the whole-table fast path, more operators, and numeric filters on auto-chunked tables (C8-ii and C8-iii).

Gates: Codex plan gate (4 rounds), Sonnet build with tests first, dennis (2 rounds; caught a fingerprint change for every job, now fixed), Codex final (3 rounds; caught filter spellings pandas cannot run, now rejected up front), ci-mirror PASS.

### 2026-10-06 -- Engine log-safety check MERGED (engine PR #213)

This is the automated half of the new "no data in logs" rule. A test now reads every engine log call and fails when new code logs a raw error message, a data value or an expression. It understands the usual ways of building a message and of naming a logger. The 10 existing sites are listed with reasons and exact counts, and four of them are on the Observability list to fix later. The list can only shrink. Gates: dennis GO, Codex final (three rounds, each finding narrower edge cases). Cam chose to merge after round 3's fixes.

### 2026-10-06 -- C5b-ii non-deterministic Faker on the chunked route MERGED (engine PR #212)

Phase C.
- **What changed:** a column using the default (non-deterministic) Faker setting used to push a large job onto the slow whole-table pandas path. It now runs on the chunked route.
  - String sources run on the fast path.
  - Other sources run chunked through the pandas leg without errors.
  - The values match a whole-table run exactly, including the per-table default naming and multi-table jobs.
- **Limits:**
  - Only providers known to return text run this way; others stay whole-table as before.
  - Columns with a `when:` filter are rejected on this route.
  - A custom provider registered under a built-in name that returns numbers now stops with a clear error instead of silently changing the column's type.
  - The whole-table fast path (unified route) is the next slice, C5b-iii.

Gates: Codex plan gate (4 rounds, the 4th approved by Cam), Sonnet build with tests first, dennis GO (one mutation thought harmless was not; a test now covers it), Codex final GO, ci-mirror PASS.

### 2026-10-06 -- Engine logs stop carrying expression text and data values (engine PR #211)

Cam asked for this after the logging review.
- **What it changed:** the engine's warning lines for `when:` filters and table transforms used to print the whole expression, so a filter like `email == 'bob@example.com'` ended up in server logs. They now say where the expression came from (column and strategy, or the transform step). The reviews turned up more sites, now fixed the same way:
  - the legacy date_shift path, which logged values it could not parse;
  - formula generation, which logged exception text per row that could quote cell values;
  - the distribution sampler, which logged snapshot bounds;
  - the disguise loader, which logged validation and YAML errors that echoed the input.
- **Unchanged:** outputs.
- **Going forward:** a dev-rules rule makes this a per-change check instead of a later sweep, and an automated engine check is next. The few remaining sites are listed in the roadmap's Observability section.

Gates: dennis (3 rounds), Codex final (3 rounds), ci-mirror PASS.

### 2026-10-06 -- C6c-i text_redact on both native routes MERGED (engine PR #210)

Phase C, first stage of C6c.
- **What changed:** a table with a text_redact (free-text PII redaction) column used to fall back to pandas in full. text_redact is now a native operator on both the unified and chunked routes, so the table's other columns (hash, Faker and the rest) run natively alongside it.
- **Speed:** the text_redact column itself runs the same Python span logic as before. It calls the oracle's own detection and splice code, so output matches by construction. Its own speed is unchanged.
- **Admitted configs:** no NER, a text token, a plain detector list, a text source, no `when:`. Every other config stays on pandas with a coded reason.
- **Output types:** on the chunked route an empty or all-null chunk is now `string`. Before, chunk types could mix within one column.
- **Next:** C6c-ii is a Rust span kernel. It needs a regex-engine decision first, because the detectors use lookarounds, and it will add a single-owner helper for the pass-through rules (a dennis follow-up).

Gates: Codex plan gate (3 rounds), Sonnet build with tests first (26/26 mutants killed), dennis GO (44-case differential fuzz equal on both routes), Codex final GO, ci-mirror PASS. Build record: decoy-engine `docs/records/2026-10-06-c6c-i-text-redact-arrow-build.md`.

### 2026-10-06 -- R1b shared kernel step MERGED (engine PR #209)

Fourth Refactor-track slice, no behavior change.
- **One step per operator:** each native masking operator now has one typed parameter object, resolved once per run, and one shared kernel step that both the unified full-frame route and the chunked route call. What differs between routes on purpose (evidence, companion errors, the date_shift error channel, where group_key reads its sibling, empty-output casts) stays in each route's adapter.
- **Defaults in one place:** the redact, truncate, bucket, date_shift, group_key and categorical defaults, which were written once per route, are resolved in one function. The chunked operator module shrank from 559 to 244 lines.
- **Why now:** position-keyed Faker (C5b-ii) becomes one parameter field and one step branch instead of two parallel dispatch branches.

Gates: Codex plan gate (3 rounds), Sonnet build with tests that pin today's behavior written first, dennis GO (one missing planned test added, three small fixes), Codex final GO with no findings, ci-mirror PASS. Build record: decoy-engine `docs/records/2026-10-06-r1b-merged-dispatch-build.md`.

### 2026-10-06 -- Engine main CI red-to-green (engine PR #208)

The CI regression gate had been red since 2026-10-05 on one stale speed test: it built a non-deterministic categorical without the namespace and row offset that C1b requires. Test-only fix; the 1-second budget still holds. Post-merge checks now include `tests/perf` and the latest main CI result.

### 2026-10-06 -- R1 operator registry MERGED (engine PR #207)

Third Refactor-track slice, no behavior change.
- **One descriptor per operator:** each of the nine native slice operators has one frozen `OperatorSpec` in a leaf module (stdlib and pyarrow only), holding its id, planned backend, kernel, resident types, assembly shape and Faker allowlist. Seventeen parallel tables across admission, evidence, physical bindings and the native route now derive from it, keeping their names, types and values (pinned by a literal snapshot taken before the refactor). Adding an operator is now one registry entry plus its kernel call.
- **Routed diagnostics are policy:** an explicit descriptor field, checked against what the capability reducers emit. The first plan derived it from the reducers, which made the admission check compare a table to itself; dennis caught it and the plan was corrected.
- **Smaller cleanups:** the three identical string-only chunked type gates are one function, with byte-identical reasons; the unused phase-3 eligibility predicate was removed; a guard test covers the forced-oracle stand-in.
- **Split out:** merging the two per-route dispatch chains (E2) is now its own slice, R1b, because the chains differ on purpose by route.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis NO-GO (vacuous routed-diagnostics gate, a plan error) then GO, Codex final GO, ci-mirror PASS. Build record: decoy-engine `docs/records/2026-10-06-r1-operator-registry-build.md`.

### 2026-10-06 -- R0 engine cleanup MERGED (engine PR #206)

Second Refactor-track slice, no routing or output change.
- **Exception taxonomy:** 25 engine exception roots now inherit `DecoyError`, which claims to be the base for all engine errors. Stdlib ancestry is kept where callers rely on it, internal control-flow carriers are excluded, and a sentry fails on any new public engine exception outside the base.
- **date_shift oracle:** derives its keys in one batch per column and skips per-row lookups for usable cells. It is byte- and dtype-identical to before, checked across 384 independent comparisons including float16/float32 all-null columns.
- **CI:** every job has a timeout, the slowest tests are reported, and the ruff version is aligned across CI, the dev extra and pre-commit.
- **Docs:** stale claims were corrected (including CLAUDE.md's import-linter and removed `graph/` references).
- **Size policy:** the module-size policy names its dense-exception rule, and its growth history moved to a decisions doc.
- **Branch pruning:** merged branches and worktrees were pruned in both repos (14 engine, 17 platform), skipping anything unmerged, dirty, detached or parked.

Gates: Codex plan gate (3 rounds), Sonnet build (7/7 mutants), dennis NO-GO (a test that broke collection on CI's Python 3.10, plus a seam permit) then GO, Codex final GO, ci-mirror PASS. Build record: engine `docs/records/2026-10-06-r0-engine-cleanup-build.md`.

### 2026-10-06 -- C5b-i MERGED (engine PR #205): position-keyed non-deterministic Faker

Owner-approved semantics change for Faker's default mode (`deterministic: false`, `cardinality_mode: reuse`). One-time pre-GA output break: row `g` now takes `pool.values[derive_index(job_seed, selection_namespace, encode_int(g), pool_size)]`, so any chunk can be computed independently (the prerequisite for C5b-ii's fast paths).
- The selection namespace is the configured one, else a length-prefixed table/column default. That fixes a real bug: two namespace-less columns with the same provider used to come out identical row for row.
- Pools, deterministic Faker, the other cardinality modes, generation and composites are unchanged, and routing is unchanged.
- The docs claiming default-mode Faker was "unseeded" were wrong and are corrected.
- During review the pure-Python reference index kernel was made about 3x faster (HKDF key derived once per column, HMAC state copied per row), byte-identical, which speeds up every non-companion caller.

Gates: Codex plan gate (2 rounds), Sonnet build (88 new tests, 9/9 mutants), dennis NO-GO then GO, Codex final GO (0 findings), ci-mirror PASS. Build record: engine `docs/records/2026-10-05-c5b-i-positional-nondet-faker-build.md`.

### 2026-10-06 -- R0 platform cleanup MERGED (platform PR #91)

First Refactor-track slice: platform docs-accuracy fixes (route-evidence docstring, CODEMAP, user-facing engine-pin text, setup guide) and removal of unused `aiosqlite` / `passlib` and a stale requirements file. dennis GO, Codex GO.

### 2026-10-05 -- Unified-slice route evidence MERGED (engine PR #204)

The full-frame unified slice now reports, per column: the backend that was planned, the backend that actually ran, and how many batches it ran. It uses the same vocabulary and the same single executed-backend rule as the chunked route, and the two routes now share that rule. This brings the unified slice up to the program's route-evidence contract; it was C5a's section 3h, which Cam moved into its own slice at the review cap.

Elapsed time stays out of `quality_metrics`, as on the chunked route, so the evidence is deterministic. It is published in `ExecutionResult.timings`, and the lane checks there is exactly one timing record per admitted column.

Two truth fixes came with it:
- Full-frame bucket_perturb and date_shift used to claim the Rust kernel ran even on empty or all-null input; they now report it only when it actually ran.
- The compiled flag now accumulates across batches. group_key used to overwrite it each batch, so a later empty batch could hide real Rust work.

Evidence assembly is now a pure, unit-tested helper module. Output reconstruction moved there unchanged, settling a long-owed file split. Outputs, warnings and errors are unchanged.

Gates: Codex plan gate (r1 REVISE, r2 GO); Sonnet build tests-first (71 new tests, 12 mutants killed); a plan correction during build (keep elapsed out of `quality_metrics`); dennis GO; Codex final GO with zero findings; ci-mirror PASS. Build record: engine `docs/records/2026-10-05-unified-route-evidence-build.md`.

### 2026-10-05 -- C5a MERGED (engine PR #203): pooled Faker on the unified slice

First Faker slice of Phase C. Deterministic-REUSE pooled Faker (namespace + pool_size set, `person_first_name` / `person_last_name`, string source, no `when`/`vault`/FK) now runs on the full-frame unified slice instead of pandas, byte-and-type identical to the oracle. Research showed the shadow Faker binding and the shared selection helper were already built and dormant (Task 4.6 slice 1), so no new Rust: the slice switches them on. A provider builds each pool at most once per job: one job-scoped `PoolCache` (default 256 MiB budget) is shared by the lane and the oracle adapter, a non-string pool from a rebound provider reroutes on that single coded difference, and pool build failures re-raise the original exception with its cause chain intact. Two lane-wide fixes rode along: `native_threads` now reaches every compiled unified operator (before, they ran single-threaded regardless of the grant), and the unified coordinator visits nodes in the oracle's sorted `order_work` order for every operator, so error order, row-error order and stateful providers match the oracle (this also fixed a latent date_shift row-error ordering divergence). Gates: Codex plan gate 3 rounds (0 blockers), then Cam's scope call at the cap (lane-wide route evidence moved to its own follow-up slice) and a confirming review; Sonnet build tests-first (12 mutants killed); dennis NO-GO (node order, lost cause chain), remediated, then GO; Codex final GO with zero findings (first review on gpt-6-astra); ci-mirror clean-env PASS. Also on 2026-10-05: engine PR #202 fixed two unit-test spies that C3 left stale, which had turned main red. Build record under engine `docs/records/2026-10-05-c5a-unified-slice-faker-build.md`. Follow-ups: lane-wide route evidence (planned/executed backend, calls, elapsed per column); the owed `_unified_slice.py` post-run split; the lane's finalize row-error reroute (wasted work, mislabeled log; pre-existing). Phase C remaining: C5b (default non-deterministic Faker), C5c (non-string Faker sources), C6a/b/c (FPE/text_mask/text_redact), C8 (when-predicates), C9 (platform admission).

### 2026-10-05 -- C3 MERGED (engine PR #201): chunked dispatcher for group_key

Sixth Phase C operator, and the last strategy on the chunked-route veto list (the veto set is now empty). Research showed `group_key` is value-keyed with no cross-chunk state, so it needed the same native chunked-leg admission as C2/C4 rather than new sibling-state machinery. No new Rust: the chunked leg reuses the existing raw-hex kernel. Value-keying only holds inside the collision-free {string, int64, bool} sibling domain (the operator caches on the raw value but derives on `str(value)`, so float/decimal forms like 0.0 and -0.0 would be order-dependent); float/decimal siblings stay rejected and wider types reroute to the oracle leg instead of failing closed. The sibling is read from the RAW pre-cast chunk so a null sibling derives `"None"` exactly like the oracle. Order-dependence declines cover a masked sibling, a self-anchored column and a missing sibling. The kernel now resolves before the empty-frame short-circuit, `NativePreflight` threads it, and all four loader-failure modes report `raw_hex_extension_unavailable`. The string schema pin keys on the sibling's first-chunk type at both schema sites. One change outside the gated plan: `compile_native_plan` gained an optional `resident_sources` argument because the profile typed an int64-with-nulls sibling as double and rejected it before the real-type gate; it reuses the full-frame resident-Arrow mechanism, defaults to unchanged behavior, and both dennis and Codex approved it (int64-with-nulls verified native == oracle). Test fixtures that forced the oracle leg through group_key were migrated at the single shared helper to a deterministic numeric categorical. Gates: plan gate 4 rounds (Codex x3, then Fable as the sanctioned substitute while Codex was at capacity), Cam authorized the build, Sonnet build (10,255 passed companion-present, 22 mutants killed), dennis GO, Codex final GO, ci-mirror companion-absent clean-env PASS. Post-merge main verified green (5,282 native/group_key/categorical tests). Build record under engine `docs/records/2026-10-05-c3-chunked-group-key-build.md`. Carry-forward LOWs: a mistyped+masked-sibling regression test, a defense-in-depth comment, and consolidating duplicated order/pin logic. Phase C remaining: C5a/b/c (Faker), C6a/b/c (FPE/text_mask/text_redact), C8 (when-predicates), C9 (platform admission).

### 2026-10-05 -- C4 MERGED (engine PR #200): chunked dispatcher for date_shift

Fifth Phase C operator. Native-admissible `date_shift` (string source, explicit `date_format`, no `group_by`, namespace, no timezone directive, in-range bounds) now runs natively per chunk via the existing compiled index kernel, byte-and-type-identical to the pandas-oracle chunked route; its table no longer forces the oracle. No new Rust (the `native_date_shift` kernel already existed on the full-frame route). Output type is string-pinned on both chunked legs at both schema-rule construction sites (dispatcher + streamed sink), companion-independent, matching C1's categorical pattern (date_shift is tokenizing, not null-on-empty); two accepted route-dependent diffs recorded (empty `double` to `string`, all-null `null` to `string`). The date_shift-specific piece is the format_error row-error obligation: a new `native/_chunked_row_errors.py` module collects the kernel's per-chunk unparseable-date positions, keeps them CHUNK-LOCAL (matching the oracle leg, which does not add the row offset), attributes table+column, emits them in the oracle work-list order, appends the failing chunk's result to the sink before raising `RowErrorsFailedError`, and stops at the first failing chunk, before any offset advance, vault write or yield. Evidence is honest: `kernel_calls` stays the branch-execution counter (C2 contract), and truthful compiled work rides an optional `derive_calls` spy (the kernel's 2-tuple return is unchanged, so the full-frame consumer is untouched); zero-row, all-null and all-unparseable chunks run no kernel and report `arrow_python`. Non-string source routes to the oracle leg (not fail-closed, the C1b-ii regression lesson). Gates: Codex plan-gate (3 rounds, design GO; the recurring forced-oracle fixture-inventory finding was fixed at the root by migrating the single shared `force_oracle` helper to a group_key self-anchor rather than hand-listing sites), Cam authorized the build, dennis APPROVE (0 blocker/0 high, all three builder judgment calls ruled sound), Codex final GO after two added tests (a mask-key differential KAT and a large_string fail-closed regression). 258 targeted tests; changed-unit coverage (new row-errors module 100%); 16 hand-mutants, 0 survivors (including the add-row_offset mutant and a wrong-mask-key mutant); ruff/mypy clean; ci-mirror companion-absent clean-env PASS. Build record under engine `docs/records/2026-10-05-c4-chunked-date-shift-build.md`. Branched off main-with-C1b-ii (`9bf5f393`); merged on local gates while Actions is out of minutes. Phase C remaining (as of C4): C3 (group_key), C5a/b/c (Faker), C6a/b/c (FPE/text_mask/text_redact), C8 (when-predicates), C9 (platform admission).

### 2026-10-05 -- C1b-ii stale-test reconcile MERGED (engine PR #199)

A one-test follow-up to C1b-ii. C1b-ii intentionally admitted seeded non-deterministic string categorical to the native chunked route, but `test_chunked_route_declines_non_admissible_categorical[non_deterministic]` still asserted it declines, which left main red (caught by the C4 dennis + Codex gates as a pre-existing, out-of-scope failure). Fix: move the non-deterministic case to the admits test (parametrized over `deterministic`), keep only `numeric_categories` in the declines test. Test-only, no production change; landed before C4 so main returned to all-green first.

### 2026-10-04 -- C1b-ii MERGED (engine PR #198): non-deterministic categorical on the native chunked fast path

Completes the categorical story (with C1b-i). Seeded non-deterministic `categorical` now runs the native CHUNKED route: a STRING source runs the compiled kernel keyed by the per-chunk uint64 global row offset (`derive_index_batch`, byte-parity with the oracle, no new Rust); a NON-STRING source routes to the existing chunked-ORACLE leg (reproducible, the same path deterministic categorical uses). Two-stage admission (config-only verdict shared by the compat veto + static route decision + evidence + preparation; source-dtype picks native-vs-oracle LEG). Scope deliberately bounded to the chunked route: full-frame physical stays closed, multi-table split + out-of-core stay vetoed (deferred to C1b-iii/C1b-iv, each needs new global-offset plumbing), `when:` rejected, null-first governed by the pre-existing `chunked_leading_null_type` gate. NOTABLE: the first build fail-closed on non-string sources, which REGRESSED auto-chunked jobs that previously ran full-frame (a valid int64/float64-source random categorical crashed); the dennis build-gate caught it empirically (before/after), the decision was corrected to the oracle-leg reroute, and an auto-router end-to-end regression test was added (the coverage gap that hid it). The clean-env `ci-mirror` then caught a companion-only test assertion that would have gone red in CI (fixed with `@NEEDS_COMPANION`) -- the per-slice clean-env check earning its keep. Gates: Codex plan-gate (3 rounds) + reversal re-gate (2 rounds), Sonnet build + remediation, dennis GO (re-gate), Codex final GO, ci-mirror PASS. ~2.5k targeted tests green; 100% line/branch on the new module; hand-mutation 0 survivors. Branched off main-with-C1b-i (`d93e3bde`). Merged on local gates while Actions is out of minutes. Remaining categorical follow-ups: C1b-iii (multi-table split) + C1b-iv (out-of-core).

### 2026-10-04 -- C1b-i MERGED (engine PR #197): non-deterministic categorical is now reproducible + reclassified seeded

Split from C1b (the plan-gate showed the full change was cross-cutting). C1b-i makes non-deterministic `categorical` REPRODUCIBLE: it now seeds the draw and keys it by the handler-frame ordinal via `derive_index` + the public `encode_int` + the shared CDF (the same position-keyed pattern windowed_date/DGRN already use; no new primitive). The old unseeded `default_rng` path is gone. The operator is reclassified truthfully as seeded across the engine's determinism machinery (determinism protocol, draw-site providers, capabilities, both draw-site-inventory summaries with a structural count gate), nested, multi-table sentries, and out-of-core compat. Crucially, it HOLDS EVERY ROUTING OUTCOME CONSTANT: the "reproducible vs random" label doubles as a live route gate (multi-table split, out-of-core, native, chunked), so C1b-i swaps the now-false "unseeded" label for honest "positional-deferred" vetoes, keeping the exact set of jobs on the exact routes they ran before. The chunked/native fast-path admission is the follow-up slice C1b-ii (which removes those temporary vetoes). Owner-flagged pre-release break: non-deterministic categorical now requires a `namespace` (reproducibility needs a key), consistent with deterministic mode; documented in CHANGELOG + compatibility-contract + strategies.md. Gates: Codex plan-gate GO (5 rounds, 8->4->2->2->0 findings), Sonnet tests-first build (red-before), dennis GO (0 blocking, 2 informational LOW), Codex final GO, ci-mirror clean-env PASS (the new per-slice clean-env check, which also caught a self-consistency prose violation in an interim changelog edit). 22k+ tests green across execution/native/physical/parity/sentry. Branched off main-with-C2 (`c4ea0f37`). Merged on local gates while Actions is out of minutes.

### 2026-10-04 -- C2 MERGED (engine PR #195): chunked dispatcher for bucket_perturb

Second Phase C operator. Native-admissible `bucket_perturb` (string source, explicit `date_format`, no timezone directive, valid bucket week/month/quarter, namespace) now runs natively per chunk via the existing compiled index kernel, byte-and-type-identical to the pandas-oracle chunked route; its table no longer forces the oracle. Output type is content-dependent (NOT string-pinned like C1): empty/all-null chunk -> Arrow `null`, valued -> `string`, reassembled -> `string`, matching the oracle leg; a post-kernel reconciliation makes the native branch emit `null` on degenerate chunks. Evidence is honest: `compiled_kernel_executed` and per-column `executed_backend` reflect ACTUAL per-chunk kernel execution (a degenerate chunk runs no `derive_index_batch`, so it reports `arrow_python`, not `rust_companion`), with identical merge logic across the resident and streamed/sink aggregation paths. `large_string` source is a native-decline/oracle case (profile resolution collapses width); a drifted later null-typed chunk now raises the same code on both legs (parity-gap fix). Non-admissible cases keep their exact existing codes. Gates: Codex plan-gate GO (5 rounds, 12->4->3->2->0 findings), dennis GO (2 non-blocking LOWs), Codex final GO (after 3 NO-GO rounds on a test-proof class: every forced-oracle leg now proves it ran the oracle via a self-asserting `run_pair` + column-qualified reasons across all 14 `force_oracle` sites). Full native suite 4343 passed / 1 skipped. Engine-internal; platform keeps its 0.8.0rc1 pin and picks C2 up at a later pin advance. Branched off main-with-C1 (`a2b97856`). Merged on local gates while Actions is out of minutes. Follow-up noted: the full-frame route (`_shadow_operators.py:257`) has the same unconditional `compiled_kernel_executed` evidence gap C2 fixed on the chunked route (pre-GA fix).

### 2026-10-04 -- C1 MERGED (engine PR #194): chunked dispatcher for deterministic categorical

First Phase C operator. Native-admissible deterministic `categorical` (deterministic/allow_collisions + namespace + all-string categories + buildable CDF + string source) now runs natively per chunk via the compiled index kernel, byte-identical to the pandas oracle across chunk shapes, sizes, thread counts, uniform + weighted; its table no longer forces the oracle. Non-admissible categorical (numeric categories, large_string/dictionary/empty-int64 source) stays on the oracle with its exact type, not string-cast. Non-deterministic fails chunked preflight with `categorical_nondeterministic_not_chunk_safe`. Output type pinned to `string` on both chunked legs (conditional on admissibility; route-dependent vs full-frame, recorded under ROUTE-OUTPUT-CONTRACT). Gates: Codex plan-gate GO (3 rounds), dennis GO, Codex final GO; mutation 48->0; 136 new tests. Engine-internal; platform keeps its 0.8.0rc1 pin and picks C1 up at a later pin advance. Build on feat/c1-chunked-categorical was rebased onto main-with-B6b (zero src overlap) + composition verified (12461 passed) before merge. Merged on local gates while Actions is out of minutes.

### 2026-10-04 -- B3 MERGED (platform PR #90): platform Phase 1 on the chunked dispatcher

Branch `feat/b3-platform-dispatcher` (plan `docs/plans/archive/2026-10-02-b3-platform-dispatcher.md` rev 3a, build record `docs/records/2026-10-03-b3-platform-dispatcher-build.md`). dennis GO + Codex final GO. Merges on local gates once the engine tag is pushed (GitHub Actions is out of minutes this month). The engine artifact `v0.8.0rc1` (commit `37694fcb`, engine main `02dc2827` plus a version-only commit) is built locally; the tag/branch push to the engine repo is the final step before merge.

- Phase 1 jobs mask each table on `run_mask_chunked` with the persisted thread budget, a bounded result sink and per-table evidence; full-frame jobs pass the same threads and let the engine auto-chunk and split. The worker's thread check compares the real request with the grant. Engine error codes reach the job (`native_chunk_schema_drift` and the rest) with the table and chunk as the location. Each mask node carries its own route, reasons, threads and per-column backend and time; `GET /api/jobs/{id}` returns an `execution` summary. `NATIVE_DISPATCHER_ENABLED=false` is the rollback lever. The engine fence is exactly `==0.8.0rc1`.
- Measured through the real job path on the devbox: speed p50 ratio 0.12 to 0.49 against the pandas route (bars 0.5 and 1.0), every `VmHWM` at least 168 MiB under its priced reservation, t=1 and t=4 outputs equal. One bar missed: the 10M-minus-1M `VmHWM` delta, 70.0 MiB at 1 thread and 75.9 at 4 (bar 64). A bare `run_mask_chunked` loop with no platform evidence code shows the same 70 MiB, so it comes from the engine's direct reader/writer path, not from B3's evidence handling. A re-pin to include B6a/B6b was considered and abandoned (Codex: those slices activate only on the `run_pipeline` path, not B3's `run_mask_chunked` path). Owner accepted the miss as a pre-GA deferral (no users; absolute bar passes with 168 MiB margin; real fix deferred to the Phase E 100M milestone). No bar loosened in code; mutation 50/50 killed.
- Pre-existing defect (not B3): a failed Phase 1 job's evidence manifest already fails its own schema (`job.table_publications` is added after the hash and is not in the strict model), on unmodified main too. T6/T7's "manifest validates" sub-assertions are kept as `xfail(strict=True)` and tracked as a follow-up (schema extension + re-hash before GA); the core T6/T7 assertions pass.

### 2026-10-03 -- B5 and B6b merged (native admission pricing + lazy batch input)

Both landed on local gates (dennis GO + Codex GO + full local suites) while GitHub Actions is out of minutes for the month. Cam's call: merge each gated slice to main on the local gates, build out through Phase F, and stand up a self-hosted runner later to do a clean-env validation sweep before relying on the result.

- **B5 native admission pricing (platform PR #89).** A streaming job's memory reservation is priced from its source (process floor + thread allowance + footer/CSV-cap decoder bound + one chunk's working set), the reader enforces that byte budget, and every claim stamps `Job.native_budget`. Gates: dennis GO, Codex GO. The golden-comparison test was made robust to a pyarrow `attributes`-field version drift (CI resolves pyarrow 21 under the platform's `<22` pin; the golden was baked under local 24); the h3 wall-clock concurrency failure was confirmed a CI-runner-load flake (passes 3/3 locally, deterministic twin passes). Engine pin left unchanged (B3 advances it).
- **B6b lazy batch input (engine PR #193).** Streams a local Parquet source into the auto-chunk lane via `LazySource` instead of materializing the whole table; input memory is flat in rows (~470 MiB at 2M/10M/50M), output byte-identical to the resident twin. Built on B6a (in main) and the B1 dispatcher contract. Gates: dennis GO, Codex GO (after remediating one mem-cap-test BLOCKER: the paired OOM test was recalibrated to 4M rows / 1536 MiB so it discriminates on both the native and companion-absent substrates). All 19 hand-mutants killed; benchmark B6B-BENCH-2026-10-03 all 20 bars pass. Build record `docs/records/2026-10-03-b6b-lazy-batch-input-build.md` (in decoy-engine).

### 2026-10-02 -- B5 native admission pricing built (platform, not yet merged)

Branch `feat/b5-native-pricing` (plan `docs/plans/archive/2026-10-02-b5-native-admission-pricing.md` rev 3.1; build
record `docs/records/2026-10-02-b5-native-pricing-build.md`). Merges only with Cam's go after dennis and Codex final.

- A streaming job's memory reservation is computed from its source (a fixed process floor, a thread-pool
  allowance, a decoder bound taken from the Parquet footer or the CSV record cap, and one chunk's working
  set) instead of the constant 384 MiB, and the reader now enforces the byte budget it was priced with
  (Parquet by row group, dictionary-first and owned-buffer chunks; CSV through a quote-aware record framer
  that rejects an oversized record before PyArrow sees it).
- Every claim records an admitted budget on `Job.native_budget` (route, thread grant, reservation, per-table
  limits and source identity). Threads are granted from a cgroup-aware core count: a fair share inline, one
  thread for an external worker, and flag on the scheduler offers each route at 1, 2, 4 threads.
- Cloud sources are priced from bounded range reads pinned to one object version, and staged from that
  same version. Four operator settings (`NATIVE_THREADS_MAX`, `NATIVE_CHUNK_BUDGET_MAX_MB`, `MAX_ROW_BYTES`,
  `NATIVE_METADATA_MAX_BYTES`) tune it; see `docs/plans/deployment-sizing-and-concurrency.md`.
- Migration `b5_native_budget` adds the nullable `jobs.native_budget` column.

### 2026-10-01 -- Rust engine program Phase A merged (engine + platform)

Engine PRs merged:

- **Engine PR #181 (A7):** the D9/GP1 peak-memory ratio gates are replaced by an absolute peak-RSS ceiling (`--max-peak-rss-mb`).
- **Engine PR #182 (A6):** the unified slice (Rust lane) returns real per-column timings and `boundary_conversion_ms`.
- **Engine PR #183 (A5a):** `read_fixed_width` and `FixedWidthParseError` are public.
- **Engine PR #184 (docs):** the Rust engine program plan, the coverage and evidence audit records, the D9 v2 recertification (green on the GCP reference host) and the file-format contract write-up.
- **Engine PR #185 (A8):** `run_pipeline` owns per-table transforms; public `apply_table_transforms`. Version stays 0.6.0 until the 0.7.0 release.
- **Engine PR #186 (B1):** public `run_mask_chunked`, the compiled chunked dispatcher as a production entry point with a per-table pandas fallback; passthrough columns are carried exactly in Arrow; Faker pool cache identity includes the provider binding (fixes a stale-pool bug on reused caches).

- **Engine PR #187 (release 0.7.0):** version 0.7.0 on engine main (installed from git, not PyPI); both DP certified-stack fingerprints re-pinned for the version string only.

Decoy CLI PR merged:

- **CLI PR #54 (A5b):** sources read by declared format (csv, parquet, fixed_width) in run, demo and `decoy.mask()`; CSV and fixed-width admitted by the native gate; requires engine 0.7.0; certified profile re-pinned; `--substrate` accepts only `pandas`.

Platform PRs merged:

- **Platform PR #74:** uploaded fixed-width files keep the recipe's format and layout.
- **Platform PR #72 (S11b):** disk-quota admission wired into the job claim.
- **Platform PR #76:** `engine-bench.sh --battery unified-cert` (D9 certification on GCP).
- **Platform PR #75 (A1+A2):** upload bindings are owner-scoped; cloud descriptors leave the executable job snapshot; the claim path is one locked candidate per transaction.
- **Platform PR #77 (A8p-0):** the platform is fenced below engine 0.7 until it stops applying transforms itself (A8p).
- **Platform PR #78 (A3+A4):** FK cycles route full-frame; fixed-width skips Phase 1 streaming.

### 2026-09-26 to 2026-09-30 -- Scheduler S10/S11 + P12 merged; MinIO CI; prod-image cloud extra

Platform PRs merged today (2026-09-30):

- **Platform PR #71 (ci/s4-minio-from-source):** the `s4-real-backends` CI job (real S3/GCS contract tests) builds MinIO from its open-source release tag, because MinIO withdrew its community images and binaries. The job had been red on every PR since 2026-09-21.
- **Platform PR #69 (feat/scheduler-s10-s11-tmpdir-localstage):** S10 (worker TMPDIR pin) and S11 (full-frame LOCAL_STAGE quota root), merged behind the scheduler feature flag. Its new `real-fs-quota` CI job proves the project quota trips on a real ext4 mount. S11b (disk-quota admission in the claim) remains open as platform #72.
- **Platform PR #70 (fix/p12-fallback-ladder-pricing):** enforces the fallback-ladder pricing invariants in host-lease admission and the priced claim.
- **Platform PR #73 (fix/prod-image-cloud-extra):** the prod image and dev compose request `decoy-engine[cloud]`. The engine side, moving boto3 and google-cloud-storage into the opt-in `cloud` extra with a guarded import, is engine #178.

Earlier (2026-09-26):

- **Platform PR #67 (feat/scheduler-s12-recovery):** S12 crash-safe recovery coordinator and flag-on startup wiring.
- **Engine PR #178 (feat/cloud-extra-split):** cloud connectors moved into an opt-in `[cloud]` extra behind a guarded import.
- **Engine PR #179 (feat/native-date-shift):** native date_shift operator (Phase 5).
- **Decoy CLI PR #50 (feat/cli-install-dx-extras):** pass-through install extras and fail-closed missing-extra errors.
- **Decoy CLI PR #51 (feat/cli-native-packaging-default-on):** native packaging default-on when the companion is present.

### 2026-09-26 -- Roadmap correction: CLI PR #47 unblock confirmed resolved (decoy PR #47, merged 2026-09-12)

The roadmap still listed this as an open `[Cam]` decision (pin+regen / merge-into-known-red /
hold) after the decision had already been made and acted on. Checked GitHub directly: decoy
PR #47 ("Preflight: render OOC capacity build-floor as an advisory warning") merged 2026-09-12
with 3 of 5 CI checks failing (pytest on 3.10/3.11/3.12), matching the merge-into-known-red
option. Two follow-up commits landed the same day and fixed the pytest red: `f6b1c92c` (synced
`seed_protocol_version` assertions to engine v7 after the FF1 bump) and `6eb0ca02` (pinned typer
to the 0.26 line so `cli-reference.md` regenerates reproducibly). decoy main has not moved since
that merge, and its latest CI run is green across all 5 checks -- confirmed no residual red.
Roadmap updated to mark Stage E item 20 (CLI PR #47) DONE and drop the matching "follow-ups to carry" entry.

### 2026-09-25 -- Adaptive scheduler S8 + S8b: worker-migration + cross-process RPC dispatch capstone (PR #65, merge fc38805a)

The R3 capstone of the V1-7 integration. The whole V2 job lifecycle now runs (flag-on) as an
execve'd worker born into the job's cgroup, launched by the single-threaded supervisor over the S3
socket; the controller stays the sole lease-DB authority and the supervisor is DB-free, coordinating
preflight -> convert -> launch -> observe-real-exit -> confirmed-populated-0 release across a
DB-free RPC protocol (preflight_start/status, run_job_start/status, result_ack, fence). Exactly-once
capacity release, generation fencing, SCM_RIGHTS fd handoff, a lost-run_job_start recovery state
machine, and cloud fd read-through. Behind `adaptive_scheduler_lease_authority_enabled` (default
off) = byte-identical to today. Gate history: Codex PLAN GO (3 rounds) -> 5 build sub-slices ->
mid-way dennis (2 safety gaps remediated) -> atomic gate NO-GO (real R3 defects) -> 2 remediation
rounds (F2-F8) + an F5/F7 completion round -> dennis GO + Codex FINAL GO. One CI follow-up (authz
allowlist relocation after a refactor moved a reviewed lookup). S1-S8 now all merged behind the flag.
DEFERRED/owed: **S9 (thread-grant) deferred** (native parallelism dormant until engine Task 1.5;
grant is fairness not safety); F1 install_backend wiring -> S12; full real-supervisor e2e attestation
-> S14 prodsim; §4.1 module splits (v2_orchestrator 605 / runner 732 LOC). NEXT = S10/S11/S12/S13,
then prodsim + the Cam-gated flag flip. State: memory [[decoy-scheduler-v1-build-state]].

### 2026-09-25 -- Verification-hardening cluster: post-validation suite, KS/chi-square, local post-mask checks (A1/A2/A5a)

The three-part cluster that finishes the post-mask verification surface the product already
half-shipped, so prodsim validates a complete one. All R2, all default-OFF or report-only.

- **A1 (engine, PR #176, merge `7ec1c5ec`).** Wired the built-but-dormant 8-scan post-validation
  suite into `run_pipeline` behind default-OFF runtime args (`post_validation` /
  `post_validation_skip` / `post_validation_sample_size` / `post_validation_enforce`). The engine
  records `quality_metrics["failed_checks"]` + `["post_validation_enforce"]` but never fails the
  job itself; the platform consumer decides. The platform ENFORCEMENT half (instance-setting
  opt-in, fail-closed route admission + crashed-scan) is a separate slice, plan-ready (Cam
  decisions 2026-09-25).
- **A2 (engine, PR #177, merge `daa8dd39`).** Added KS-complement (numeric) and chi-square
  Cramer's V (categorical) goodness-of-fit metrics to the distribution-integrity comparator, in
  named `extra_metrics` fields. Additive and report-only: the primary similarity/method, the
  overall_score, and the A-F grade are byte-identical (proven against pre-A2 output). Hand-rolled
  from the aggregate snapshots, no scipy, no raw-value reads.
- **A5a (platform).** Local parquet source/target support in the Storm + Quality post-mask hooks,
  and a seeded reservoir sampler (bounded in rows AND bytes) replacing a biased first-100k head
  sample so integrity reports on sorted local files are representative. Shared `_io_discovery`
  helper; cloud descriptors are an honest skip (the cloud half A5b stays deferred). The
  double-gate hardened it materially: a credential-leak fix (exception text and file paths kept
  out of `job.log`), a sampling-uniformity fix (fixed-count ceiling from a data-constant max row,
  so wide rows are not under-represented when the byte cap binds), and a dtype-expansion fix (the
  byte ceiling bounds the reconstructed `from_records` frame, not the input dtypes).

### 2026-09-21 -- Phase 5 native operators: categorical, bucket_perturb, group_key (engine PRs #171/#173/#174)

Three more masking strategies gained native operators through the unified coordinator's operator
seam. Categorical deterministic pool selection (#171, the first Phase 5 operator picked from the
reprofiled workload mix); bucket_perturb (#173, S-port slate #1); and group_key (#174, merged 2026-09-22 UTC; S-slate #2,
which needed a new canonicalize-free `derive_hex_raw_batch` kernel, preserves the source
pandas-metadata on stringify, and is scoped to `{string, int64, bool}` sibling types). Each is
shadow-parity-proven against the pandas oracle and double-gated (dennis + Codex; group_key's Codex
FINAL caught a pandas-metadata P0, remediated at source). All three merged 2026-09-21, full CI
green. Carry-forward from the group_key review: its sibling-table input seam is correct but should
be refactored to declared input-slots / an `OperatorInputContext` before the next sibling-reading
native operator copies it. Plans: `decoy-engine: docs/plans/` (phase5-categorical, native
bucket_perturb, native group_key).

### 2026-09-21 -- Generation fast-path: native-ize the World B pool sampler (engine PR #169)

The last identified `derive_index_batch` drop-in. The World B pool sampler (`generation/pool/_sampler.py`)
mapped a canonicalized source value to a pool slot with a PER-ROW `derive_index` loop, in both the scalar
deterministic path and the composite `sample_bundle` deterministic branch. Both now use the batched
`derive_index_batch` kernel (the same one that made Phase 2 pool-index selection ~13x). BYTE-IDENTICAL to
the former per-row output -- proven compiled == reference == legacy across every value class (ascii +
NFC/NFD unicode, bools, signed/unsigned + numpy ints of every width, tz-aware incl. sub-microsecond and
non-UTC timestamps, `Decimal("NaN")`, `uint64 > 2^63`, int64 bounds, bytes/uuid, duplicates, empty/
all-null/mixed nulls). Measured ~10.6x at 100k rows (1160ms -> 110ms). Nulls are stripped before the
kernel (matching the legacy `source.isna()` contract, avoiding the `pd.NA` vs `_is_missing` divergence);
the composite bundle keeps its one-shared-index-per-row tuple integrity; the non-deterministic path is
untouched; value classes the compiled kernel rejects fall back to the reference kernel over raw Python
values (byte-identical, "supported, correct, slower"). Codex plan-gate GO -> dennis APPROVE (ns-timestamp
end-to-end guard + docstring remediated) -> Codex FINAL GO (no findings) -> full CI green (both
substrates, 34-min regression suite). Plan: `decoy-engine: docs/plans/2026-09-21-worldb-sampler-native-index.md`.

### 2026-09-21 -- Phase 6: delete the dormant Polars masking adapter (engine PR #168)

Pre-GA hard-delete of the Polars MASKING adapter. `"polars"` was a value-parity-with-pandas opt-in
that measured no faster for the per-value keyed-crypto masking workload, was reverted to dormant, and
is now removed: `execution/polars/` (the adapter + its strategy ports), the `polars_native` planner
mode, the polars when-gate variant, the polars reason-code translation, and the physical-plan
`Substrate.POLARS` capability. `VALID_SUBSTRATES` is `("pandas",)`; `substrate="polars"` /
`DECOY_SUBSTRATE=polars` now raise `invalid_substrate`. Net ~-5,600 LOC (100 files). No masking
behavior change (pandas was always the masking output, byte-identical; test-flight fingerprints
unchanged); the retained generic non-pandas guards stay as fail-closed defence, re-covered by
synthetic-`future_substrate` unit tests. `subset/` keeps the polars LIBRARY for FK-closure joins,
and the `polars>=1.0,<2.0` dependency is unchanged. The V2 baseline benchmark harness (its only
correctness dimension was pandas==polars parity) was retired, its historical baseline preserved as a
dated validation record. Executed via the plan's iterative delete->sweep->sentry method (the wide-
but-shallow reference cleanup took several passes). dennis APPROVE + Codex substantive-GO (Codex's
sandbox-only pyarrow `string`/`large_string` test failures were ruled out against the pinned-env
full CI, which is green -- both substrate + regression-gate suites pass). §9 compatibility checklist
completed (pre-GA hard delete). Plan: `decoy-engine: docs/plans/2026-09-18-polars-masking-removal.md`.

### 2026-09-21 -- Phase 3.3: platform rollback lever + unified-lane route evidence (platform PR #53)

The engine's unified-slice masking lane is already the production default (activation, #165),
so the platform worker reaches it with no code change. This slice adds the platform-owned
CONTROL and OBSERVABILITY around that: a rollback lever `UNIFIED_SLICE_ENABLED` (pydantic
setting, default True) threaded into both engine `run_pipeline` call sites -- the job runner
and the preview helper -- so ops can fall back to the legacy pandas oracle without an engine
release (flip to False; the spawned bounded-preview child inherits it via `os.environ`). The
job report now records the route the engine ACTUALLY ran (`execution_route` in the node-run
exports: `unified_slice` / `legacy_full_frame` / `legacy_chunked`), derived from engine
evidence -- the `unified_slice_activation` leaf, then `quality_metrics["auto_chunk"]["mode"]`
-- never from the flag, so an enabled-but-non-admissible or legacy-chunked job is labeled by
the path used, not the setting. The literal Task 3.3 plan was obsolete post-activation/4.7
(it referenced the deleted `native_route_enabled`); re-scoped by Opus, Codex plan-gated. dennis
APPROVE (2 MEDIUM test-quality findings remediated: a vacuous spawn-child test and a weak parity
assertion). Codex final NO-GO round 1 caught the legacy-chunked route mislabel (P2), remediated
at root by reading the engine's second routing-evidence source; Codex re-gate GO. Full CI green
(both substrates). Task 3.4 (bounded release: prodsim/canary, fingerprint comparison, abort
criteria) is deferred to Stage B, where it merges with the prodsim validation. Plan:
`decoy-platform: docs/plans/2026-09-21-phase-3.3-unified-lever.md`.

### 2026-09-20 -- Task 4.7: delete the superseded native routing lane (engine PR #166)

Removed the dead standalone single-pass streaming native lane now that the unified-slice
coordinator (activated in #165) owns the production single-table masking path. The
`native_route_enabled` flag always defaulted False and was never enabled in production, so
this is a behavior-neutral pre-GA hard cutover: deleted `_native_route*.py` +
`physical/drivers/_native_stream.py` + 8 native test files, removed the flag from the
pipeline/admission/compiler and the `ExecutionResult.native_route` field + `DriverId.NATIVE_STREAM`
+ the native reason-code catalog. Net -7,300 lines; one production decision path remains. The
compiled deterministic-Faker kernel package (`execution/native/`) is untouched. One observable
side effect: the internal `plan_hash` shifts by a one-time constant (no platform consumer compares
it). dennis + Codex gated (dennis caught a second sentry allowlist that needed the deleted paths);
full CI green (both substrates). Plan: `decoy-engine: docs/plans/2026-09-20-task-4.7-delete-native-route.md`.

### 2026-09-20 -- Route activation: unified lane is the production default (engine PR #165)

`unified_slice_enabled` now defaults True, and admission no longer declines a
full_frame job that carries the platform worker's inert sink, so the certified
unified-slice lane is the production default for its admitted subset (single non-FK
Parquet mask table on the four native scalar strategies, pandas full-frame). The
platform isolated-worker reaches the lane with no platform-side change; admission
stays the safety gate and every non-admissible shape falls through to the unchanged
legacy route. D9 re-cert GREEN on the exact commit (n2-standard-8): 10k RSS 1.023x,
100k 1.048x, 1M 1.094x under the 1.25x band, ~4.3x faster at 1M. Full engine suite
green (11265); dennis + Codex (plan-gate round 3 + final) gated. Cert artifact under
`docs/product/release-1-validation-runs/2026-09-20-d9-recert/`. Next: Task 4.7
(delete the superseded routing). Plan: `decoy-engine: docs/plans/2026-09-20-unified-slice-activation.md`.

### 2026-09-12 -- FPE is now NIST SP 800-38G FF1, not the home-rolled Feistel (engine PR #132)

The `fpe` strategy's cipher is NIST SP 800-38G FF1 (Algorithms 5/6), AES-256 through the audited
`cryptography` package, KAT-locked against NIST's published known-answer vectors plus a
Wycheproof-derived corpus and a structurally separate differential oracle (source SHAs recorded in
#133). This was a pre-GA HARD CUTOVER (Task 5.2, native-throughput plan): the engine's earlier
home-rolled 8-round HMAC-SHA256 Feistel construction was DELETED entirely, no dual-primitive period,
gated by `SEED_PROTOCOL_VERSION` 6 -> 7. Every `fpe` column and the `fpe`-branch text-mask spans now
use FF1, and every keyed derivation that mixes in the shared version byte changed output. The
conformance claim is precise: "AES-FF1 conformant to NIST SP 800-38G," enforcing the Rev.1 Second
Public Draft restrictions (FF1 only; FF3/FF3-1 withdrawn after the Beyne 2021 attack); NOT
"NIST-certified" or "FIPS 140 validated." dennis + Codex final gated; FF1-primitive mutation ledger
at logic-100% (crown-jewel bar). Detail: `decoy-engine: docs/security/de-01-ff1-adoption.md`.
Open item for Cam (not resolved by the ship): the Voltage/OpenText FF1 method-patent question the
FF1 design flagged as a legal check is not recorded as decided anywhere; see the ROADMAP "Deferred /
parked" note.

---

## Execution Consolidation and Native Throughput program (native/Rust masking)

Plan: `decoy-engine: docs/plans/2026-09-09-execution-consolidation-and-native-throughput.md`.
This is the active governing program for native masking. It SUPERSEDES the earlier
`2026-08-26-engine-efficiency-plan.md` (predecessor; its Part 1 Phases map onto this
program's Phase 1-2, its Part 2 onto Phase 5). The five original efficiency-plan
"open decisions" (native language, streaming all-or-nothing, funding, parallel
Phase 0 start, 100M cap) are all RESOLVED. Do not track native work against the
2026-08-26 doc.

### 2026-09-18 -- D9 perf-cert GREEN + per-tier RSS budget (engine PR #164)

The unified-slice lane is now D9-certified on the reference host (GCE n2-standard-8):
`d9_certified: true`, all tiers pass -- 10k RSS 1.025x, 100k 1.071x, 1M 1.121x, wall
~3-4.3x faster (1M: 9.6s vs 41.2s). The peak-RSS gate was made per-tier (1.10x below
1M, 1.25x at 1M+): the 1M lane peaks ~1.12x of legacy, over the old flat 1.10x band,
but that band is a relative regression check, not an absolute-safety limit (absolute
peak ~1.8GB, far under the 6.5GiB host ceiling). This unblocks route activation (the
cert was activation's governance gate). Cert artifact:
`docs/product/release-1-validation-runs/2026-09-18-tb6-50m/`. dennis + Codex FINAL gated.

Naming note: this program's "Phase 4/Phase 5" are DISTINCT from the older
streaming/OOC efficiency work that was once also called "phases 4-5" (see the
"streaming routes + OOC reorder" entry below). They are different work.

### Shipped to engine main

- **Faker widening (generation throughput): DONE + MERGED 2026-09-18 (engine PRs
  #162 harness, #163 addition).** A cross-process/cross-time determinism harness
  (`scripts/faker-determinism/`) certifies which pooled faker `(type, locale)` pairs
  produce byte-identical output across fresh processes (varied `PYTHONHASHSEED`) and
  a committed golden: **183 certified pairs**. On top of it, a locale-aware
  `pool_eligible` adds **29 new reuse-safe PII types** (gendered name/prefix/suffix
  variants, job/company variants, geo scalars) as 135 certified pairs. Measured:
  pooled generation **~2.2M rows/s** (8x past the 267k-rows/s masking kernel), so
  those columns drop from ~10-23k rows/s per-row Faker to ~2.2M at N>=50k. Legacy 10
  types unchanged (global); unique-key types (email/uuid/ssn) stay per-row by design;
  byte-identical where pooling declines. Codex plan+final GO + dennis APPROVE on both.
- **D9 RSS overshoot PART 1 (native single-range pool fix): DONE + MERGED 2026-09-18
  (engine PR #161).** The native derive built the host-sized shared rayon pool even
  for single-range batches (whose per-thread runtime state scales with host cores),
  the core-dependent half of the D9 1M peak-RSS overshoot. `run_range_tasks` now runs
  a single range serially, never constructing the pool; >=2 ranges still use it.
  Byte-identical (thread-invariance parity tests). Dropped 1M peak RSS ~1.22x ->
  ~1.18x. dennis APPROVE + Codex final GO. (PART 2, the pandas-reconstruction
  remainder, is Cam-deferred; see the ROADMAP Phase-4 blocker.)
- **Phase 0 (freeze decision + evidence): DONE, Cam-approved 2026-09-09.** Frozen
  workloads, route inventory, acceptance matrix; Task 0.2 authoritative baseline on
  the reference host (GCP n2-standard-8), all 8 section-15 decisions locked.
- **Phase 1 (optimize the Rust keyed-hash kernel): COMPLETE + MERGED (engine PR #129,
  merge `8d833c30`).** Cached namespace key, GIL release, bounded Rayon. Headline
  result: **100M rows masked in a median 429.9 s at 8 threads** (mask-only, the
  frozen W2 workload, <=600 s contract met with ~170 s margin), peak RSS ~447 MB
  (flat). Hash kernel: 1,280 s baseline -> 299.7 s single-thread (~4.3x) -> 94.8 s at
  8 threads (**~13.5x** total).
- **Phase 2 (compiled deterministic Faker pool selection, `derive_index_batch`):
  COMPLETE + Cam-approved (engine PR #129).** Pool-index selection ~105k -> **~1.37M
  rows/s (~13x)**; 1M-tier total wall 60.9 s -> 13.1 s. (Pool BUILD time is separate
  and unchanged.)
- **Phase 3.2 (native companion bundled in the production image + probe):
  MERGED 2026-09-13** (engine #135 `712aa1ea`; platform #45 `0e13b607`).
- **Phase 4.1-4.4 (unified physical-plan scaffolding): MERGED.** 4.1 design (`c13e1b62`),
  4.2 adapter seam (`31ae76fb`), 4.3 physical-plan compiler (`f2811e32`), 4.4 shadow
  coordinator (`c617b47a`). These are the disconnected physical-plan + shadow-mode
  layers; they do not yet own any production route.
- **Phase 4.5 (unified-slice production lane): MERGED 2026-09-15** (engine #141
  `90b49abf`). A default-OFF engine-only lane (`unified_slice_enabled=False`) that runs
  one bounded slice through the coordinator and returns a result byte-identical to the
  pandas full-frame route. Engine-ready; caller activation deferred to 4.6.
- **D9 perf-cert harness (a 4.6 prerequisite): MERGED 2026-09-15** (engine #142
  `54120b97`). `scripts/bench-unified-slice/bench_compare.py`: a two-arm (flag off vs on)
  statistical driver over the frozen worker, paired ratio + p95 + seeded bootstrap CI and
  peak-RSS ratio. Built but NOT yet run: the offline 10k/100k/1M cert run on a bench node
  is still owed before any 4.6 route activation.
- **Phase 4.6 slice-1 (deterministic-Faker shadow operator): MERGED 2026-09-16** (engine
  #143 `42b5e16f`). Shadow-only parity vs the oracle (no publish, no activation): the
  coordinator selects Faker pool values through the same identity + per-run registry the
  oracle uses, proven cell-for-cell.
- **Phase 4.6 slice-2 (single-table chunked masking parity): MERGED 2026-09-16** (engine
  #144 `794c684e`). Test-layer only (no production src change): proves the coordinator
  matches the chunked oracle cell-for-cell across identical chunk boundaries, over the
  five shadow strategies.
- **Phase 4.6 slices 3-6: ALL MERGED 2026-09-16** (engine #145/#147/#150/#152/#154).
  slice-3 DuckDB out-of-core FK shadow parity (wraps `run_fk_out_of_core` via the Task 4.2
  adapter); slice-4 bounded Group B/C payload operators; slice-5 generation ownership
  (5a generate-only, 5b-i mixed generate+mask, 5b-ii mixed generate-parent->mask-child FK
  + stitch); slice-6 global full-frame path. All double-gated (dennis + Codex), main green.
- **Activation prerequisites: BOTH MERGED 2026-09-17.** The unified-slice exception boundary
  widened to reroute ANY unexpected error on an admitted job to the legacy route (engine
  PR #158 `4369f38c`), and the shared bench driver hardened to fail closed on missing per-rep
  RSS + render None-safe summaries (engine PR #159 `88f8291b`).
- **Generation-throughput workstream: MERGED 2026-09-17.** GP2 pool-based Faker generation
  (engine PR #156 `4501b85f`): an eligible faker column builds a bounded value pool once and
  vector-samples it, ~124x faster at 1M rows, byte-preserving below a 50k threshold, opt-out
  via `pooled: false`. GP1 throughput probe harness (engine PR #157 `08ca57f5`), the tool that
  measures the pooled-vs-per-row crossover (the real sweep + N_THRESHOLD refinement is an owed
  offline follow-up). 5a-faker (engine PR #160): admits the 10 deterministic faker types to
  the generation shadow-parity proof, threading an immutable custom-provider snapshot through
  admission + both generate calls so the two sequential runs cannot diverge.
- **D9 cert RUN 2026-09-17 (result: unified lane FASTER but over the RSS budget).** On a GCE
  n2-standard-8: the unified lane is ~3-4.4x faster at 10k/100k/1M, but peak RSS at 1M is
  ~1.18x the legacy route (budget <=1.10x; 10k 1.03x and 100k 1.095x pass). Wall-time and CI
  gates pass at every tier. The overhead is not in tracked Python (tracemalloc) or Arrow
  (pyarrow-allocated) memory, pointing at native-kernel runtime. Route activation is BLOCKED
  pending a fix-or-accept decision (see the roadmap's current-priority block). A reusable
  `unified-cert` battery was added to the gcp-bench harness (provisions Rust + builds/verifies
  the native companion, then runs `bench_compare.py --require-cert`).

### What the native speedup covers (and does NOT) as of 2026-09-16

- **Covered, merged:** the Rust crate `decoy-engine-native` (`derive_batch` keyed
  hash, `derive_index_batch` pool index, one shared long-lived Rayon pool); native
  scalar kernels for passthrough / redact / truncate / keyed-hash; compiled Faker
  pool-index selection.
- **NOT yet:** it is a **bounded slice** (single non-FK table, fixed Arrow schema,
  the four scalar strategies + pooled Faker), **default-OFF** (`native_route_enabled=
  False`), and **not the customer default**. The opt-in Route 4a excludes hash; the
  optimized hash kernel has no production caller until Phase 4's coordinator
  activates it. redact/truncate are native but still single-threaded (the new serial
  floor, a Phase 5 target). FPE, Faker providers/generation, date_shift, bucketize,
  code_set, formula, nested-JSON, text/NER, and arbitrary-Python providers all remain
  on the pandas oracle.

Bottom line: the Rust work is real, merged, byte-parity-clean, double-gated, and hit
its headline target as a benchmarked capability. It becomes the shipped customer
default only as Phase 4 (4.5+) activates it.

---

## Older streaming / out-of-core efficiency work (NOT the native-throughput program)

- **Streaming routes + out-of-core reorder + batched NER: SHIPPED 2026-09-09.**
  (Previously labeled "engine efficiency phases 4-5" on the roadmap; relabeled here
  to remove the collision with the native-throughput program's Phase 4-5.) Engine-
  efficiency streaming routes and out-of-core reorder with a native columnar lane
  (engine PR #126); batched NER inference for ~5x text-masking speedup, byte-identical
  (engine PR #127); OOC capacity preflight recalibration with advisory build-floor,
  hard fan-in, recalibrated slope (engine PR #128). GCP curve on main: 100M @ 8GB,
  200M @ 16GB, 400M @ 24GB peak, parity-clean on the streaming path. A faker-payload
  GCP run confirmed the OOC route rejects faker by design (falls back to
  sequential/full-frame): the 100M-to-8GB streaming win covers FK-relational plus
  hash/redact/truncate, NOT faker/pool payloads.

---

## Programs and features (relocated from the roadmap's inline history)

- **§TEST Enterprise-readiness program: COMPLETE 2026-07-29..30 (behavior under
  load), plus the T1+T2 test-suite audit.** TEST-1/2/3/4/5/6/7/9/10 all DONE and
  merged; verdict CONDITIONAL GO (acceptance test-flight 53/53 green with matching
  fingerprints; five of six readiness gates MET, gate 1 partial pending the
  100M/200M capacity run). TEST-3 found and fixed three real cleartext-leak paths in
  the `nested` JSON strategy. The T1+T2 coverage audit reset baselines (engine 87.6%
  / platform 76.6%) and caught platform `main` un-runnable against engine `main` for
  ~11 days (fixed, suite 0 -> 3222 passing); T3-T6 deferred. Remaining tail: TEST-8
  (web E2E, needs Playwright infra) and the 200M capacity run (BENCH). Full detail:
  `docs/product/enterprise-readiness-go-no-go.md`.
- **§TQ Test-Quality Program: crown jewels + focused sweep + execution substrates
  SHIPPED 2026-07-26..28 (engine PRs #113, #114, #115, #116).** TQ-0 measure-first
  mutation grading with mutmut; ~33 modules to logic-100% in #113 (crypto + RI/FK at
  the 100% bar, ~15 execution strategies, ~7 transforms, codeset config/index); #114
  closed the execution-SUBSTRATE tier mutmut had mis-scored (a `scripts/tq_mutate.py`
  post-processor re-adjudicates survivors); #115/#116 closed the last residuals plus
  the RI correctness fix (`_fk_keys.py`: equal-valued float and Decimal now mint the
  same FK join token). All dennis- and Codex-approved. In-process-gradeable tier
  COMPLETE. TQ PAUSED at diminishing returns (Cam 2026-07-28); spawn-boundary +
  codeset_etl / plan / env-gated tiers DEFERRED to pre-release (engine tq-findings #15).
- **§DPS Differential Privacy Synthesis: marginal DP SHIPPED 2026-07-24 (engine
  PR #110).** DPS-CODEC 0.5.0 + CLI cert-stack + `decoy fit` on `fit_dp_snapshot`;
  marginal DP over numeric AND categorical via OpenDP mechanisms + Google
  `dp_accounting` PLD composition; nine `dp_*` modules, crown-jewel graded. Follow-ons
  (not current): platform-side DP integration (rides the held platform release) and
  DPS-4 / PrivBayes (joint/correlated DP).
- **OOM / capacity checker v1: SHIPPED (engine PR #112, 2026-07-25).**
  `enforce_ooc_memory_preflight` productized into a customer-facing capacity estimator
  + CLI wiring: refuses early with "needs ~X GB, you have Y" instead of OOM-crashing.
- **§OOC memory architecture: PRODUCT DECISION 2026-07-22. Tiered RAM guidance
  replaces infinite-scale streaming.** Routing / disk-aware admission / phase-aware
  budgeting from engine PRs #86/#87/#88/#94 remains shipped. The single-read OOC-B
  (PR #107) was reverted by PR #108 after the 200M@8GB GCP proof showed peak RSS ~21GB;
  main runs the O(parent) relation path. Deterministic/keyed FK masking is unlimited
  at any row count (flat memory); full synthetic remap + linked-table generation are
  RAM-tiered (published sizing guidance); OOM safety net is the graceful preflight.
  Bounded external-reorder work SHELVED on `feat/ooc-b-external-reorder` (`67c3bd6`).
  Sizing guide: `docs/guides/sizing-and-hardware.md`.
- **§HC healthcare de-id + code sets: COMPLETE 2026-07-21.** HC-2/3a/3b/5/6/7 merged;
  HC-1 public-domain corpora: ETL infra (#100), ICD-10-CM (#101), O(1) mask selection
  (#102), HCPCS Level II (#103), MS-DRG (#104), ICD-10-PCS (#105), full-corpus ETL doc
  (#106); NDC parquet present. GA-corpus-freeze blocker cleared. HC-4 parked (compliance).
- **§TX free-text NER: TX-1 + TX-2 shipped.** Activate text_redact NER (#90); wire
  spaCy NER into text_mask so person/location synthesize (#92).
- **§MLF ML post-merge hardening: mostly shipped.** CI ml-gate (#81); wheel-include
  pack + require pack signatures, DE-07/DE-04 (#82/#83); corpus expansion + isotonic
  calibration, MLF-4/5 (#84); doc staleness MLF-7 (#85).
- **§TEST / §BENCH: partial.** CodSpeed harness + Mergify JUnit wiring, inert
  (#96/#98, TEST-1); canonical hard-caps sweep (#95, TEST-4); per-strategy payload
  probe knob (#99, BENCH-CODE-1). GCP BENCH-R1 sizing runs 1-4 (100M + 200M@8/16GB).
- **ML foundation (ML0-ML3.2):** 2026-06-27: LightGBM `lgbm-v1`, 11 semantic types,
  macro-F2 0.979, HMAC-signed packs, `POST /api/v2/classify-fields` (admin-gated,
  off by default, advisory). Live-but-off; no operator UI (ML3.3 open).
- **Crypto GA delivery** (DE-01/02/03/11): engine main 2026-07-14: whole keyed
  surface rekeys off a secret, fail-closed at GA.
- **Backlog-buildout (SP-01..SP-28):** 2026-06-29; **Capability-review A-H:**
  2026-07-03; **FK-RI memory-scaling** `run_sequential` (~25-27% peak-RSS cut);
  **50M-row OOM + throughput hardening** (#49/#50); **DE-10 chunked-FK dtype family**
  (#74). Detail in `sprint-ledger.md`.
