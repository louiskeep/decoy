# Decoy CLI + Engine — QA Audit Checklist

Manual QA pass over the `decoy` CLI (this repo, `decoy-cli`) and the `decoy-engine`
library it wraps. This is **not** a re-statement of the automated test suite — both
repos already have unusually thorough coverage (nearly every CLI command has a
dedicated e2e test; the recent crypto/security engine fixes each ship with a named
regression test proven to fail pre-fix). This checklist exists to catch what automated
tests structurally can't:

1. **Happy-path flows run by a human**, typing the documented example commands into a
   real terminal against real files — the kind of thing that only breaks when someone
   actually does it.
2. **Deliberate probes of known gaps** — commands/behaviors that are thin on coverage,
   recently changed, or explicitly documented as a limitation.
3. **Cross-cutting flows** spanning multiple commands that no single unit test exercises
   end to end.

Environment: `decoy-cli` v0.1.0 / `decoy-engine` v0.4.0, both on `main` as of 2026-07-16
(`decoy` HEAD `b7a01e6`, `decoy-engine` HEAD `2249b75`).

Sign-off block is at the bottom. Check items off in place (`- [x]`) as you go; leave a
one-line note next to any failure with the exact command and output.

---

## Section 0 — Environment sanity

- [ ] `pip install decoy-cli` into a clean virtualenv succeeds; `decoy --version` reports `0.4.0`+ engine floor.
- [ ] `decoy doctor` — all hard requirements present, exit 0.
- [ ] `decoy doctor --json` — same data as JSON.
- [ ] `decoy doctor --quiet` — silent, exit code only.
- [ ] `decoy --help` — banner + quick-start hints render; every command listed matches this checklist's Section 1.
- [ ] `decoy --install-completion` — shell completion installs without error (bash/zsh, whichever you use).

## Section 1 — CLI happy-path flows, by command group

For each group: run the literal example command(s), confirm exit code + output shape
match the doc. Full flag reference: `docs/cli-reference.md` (auto-generated, kept fresh
by `tests/unit/test_cli_surface.py`).

### `decoy run` / `decoy preflight`
- [ ] `decoy run pipeline.yaml` — default mask mode, exit 0.
- [ ] `decoy run pipeline.yaml --json` — structured result, no chrome on stdout.
- [ ] `decoy run pipeline.yaml --chunked --chunk-size 100000` — completes, output row count matches source, byte-identical to a plain run on the same input.
- [ ] `decoy run pipeline.yaml --chunked --substrate polars` vs. the pandas default — confirm outputs are **value-equal**, and that any CSV byte differences are explained by Arrow type-width drift (not a real data discrepancy). Don't take the "value-equal" doc claim on faith — actually diff the two CSVs.
- [ ] `decoy run pipeline.yaml --vault vault.bin` then round-trip via `decoy unmask ... --vault vault.bin` (see below) — recovered values match originals.
- [ ] `decoy run pipeline.yaml --notify webhook:<url>` against a **working** webhook — notification received.
- [ ] `decoy run pipeline.yaml --notify webhook:<deliberately-broken-url>` — run still succeeds and exits 0; notify failure never changes exit code (see Section 4 for the dedicated negative case).
- [ ] `decoy run pipeline.yaml --notify slack:<url> --notify-on failure` — on a successful run, confirm NO notification fires (only `failure` requested).
- [ ] `decoy preflight pipeline.yaml` — passes on a good config.
- [ ] `decoy preflight pipeline.yaml --fail-on-warning` on a config whose output target already exists — exits non-zero.
- [ ] `decoy preflight` correctly reports missing/unreadable source files without running anything.

### `decoy unmask`
- [ ] `decoy unmask pipeline.yaml masked.csv` — recovers `fpe` columns into `masked.unmasked.csv`.
- [ ] `decoy unmask pipeline.yaml masked.csv --table accounts` — disambiguates a multi-table config.
- [ ] `decoy unmask pipeline.yaml masked.csv --vault vault.bin` — also recovers `vault: true` one-way columns.
- [ ] **`--json` vs. non-`--json` summary parity**: run against a config masked under the no-mask-secret (job-seed) fallback, then unmask. Confirm the **human-readable** (non-JSON) summary shows the `reversed_unverified` bucket and the "FPE is unauthenticated" caveat — this was a real bug fixed in the most recent commit (`b7a01e6`); regression-check it manually since there's no dedicated e2e test for the human-readable path specifically.

### `decoy fit`
- [ ] `decoy fit customers.csv` — writes `customers.snapshot.json`.
- [ ] `decoy fit customers.csv --parse-dates signup_date` — datetime column parsed correctly.
- [ ] `decoy fit customers.csv --joint state,tier` — contingency table captured.
- [ ] `decoy fit customers.csv --epsilon 1.0` — DP noise applied; sanity-check the noised histogram counts are plausible (not wildly off from the true distribution).
- [ ] `decoy fit customers.csv --epsilon 1.0 --joint state,tier` — **must error** (`--epsilon` + `--joint` incompatible in v1). Confirm it actually errors rather than silently ignoring one flag.

### `decoy init` / `decoy templates` / `decoy demo` / `decoy explain` / `decoy info` / `decoy schema`
- [ ] `decoy init` — interactive wizard completes, writes `pipeline.yaml`.
- [ ] `decoy init --preset hipaa --out hipaa_pipeline.yaml` — scaffolds from template, validates clean.
- [ ] `decoy init customers.csv --out pipeline.yaml` — STORM column-aware scaffold, `# REVIEW:` comments present above every inferred column.
- [ ] `decoy templates list` and `decoy templates show hipaa` — bundled templates (minimal, hipaa, pci, gdpr) all print valid YAML.
- [ ] `decoy demo` — end-to-end scan→mask walkthrough completes in `./decoy_demo/`.
- [ ] `decoy explain` (no topic) — lists all topics; `decoy explain differential-privacy` and `decoy explain vault` — render sensible plain-English text.
- [ ] `decoy info` / `decoy info --json` — banner and metadata render.
- [ ] `decoy schema` / `decoy schema -o decoy.schema.json` — valid JSON Schema output.

### `decoy plan` / `decoy compile` / `decoy profile`
- [ ] `decoy plan pipeline.yaml --no-profile` — compiles without loading data; `checks_skipped` populated.
- [ ] `decoy plan pipeline.yaml --profile profile.json` — runs all five S1 plan-compile checks.
- [ ] `decoy compile pipeline.yaml --explain` — per-column strategy/params/rationale shown.
- [ ] `decoy profile data.csv --show-fields` — dtype/null_rate/distinct_count/PII-candidate-flag per field; confirm **no raw cell values** appear anywhere in the output (this is a hard documented guarantee — worth eyeballing directly, not trusting the doc).
- [ ] `decoy profile data.csv --rows 0` — full scan completes on a file bigger than the 10k default sample.

### `decoy subset`
- [ ] `decoy subset pipeline.yaml --dry-run` — projected row counts printed, **nothing written to disk** (confirm no output dir/files appear).
- [ ] `decoy subset pipeline.yaml --out subset_out/` — real run, writes filtered Parquet + `subset-manifest.json`; re-running against the same non-empty `subset_out/` correctly refuses (must-not-already-exist guard).
- [ ] Preflight rejects a CSV-sourced relationship table with a clear "subsetting requires Parquet" error naming the offending table.
- [ ] Fan-out budget (`max_total_rows`/`max_table_seed_multiple`) is enforced **before** any output directory is created — verify by setting an absurdly low budget and confirming no partial output is left behind.

### `decoy validate config` / `decoy validate distribution`
- [ ] `decoy validate config pipeline.yaml` — prints OK on a good config.
- [ ] `decoy validate config pipeline.yaml --fail-on-warning` on a config whose output already exists — exits non-zero (exit 2 for config warnings per the doc's explicit contrast with `validate distribution`'s exit 4).
- [ ] `decoy validate distribution source.csv output.csv --config pipeline.yaml` — intentional loss (hash/bucketize/faker columns) not flagged as accidental drift.
- [ ] `decoy validate distribution source.csv output.csv --mode fail --min-grade B` — exits `EXIT_FINDINGS` (4) when grade falls below B; exits 0 when it doesn't.
- [ ] `decoy validate distribution source.csv synthetic.csv --generate` — row-count mismatch NOT flagged (generate mode expects it).

### `decoy storm` (analyze / scan / integrity / fields / show / diff / test)
- [ ] `decoy storm analyze data.csv` — saves `scan_<timestamp>.json`.
- [ ] `decoy storm analyze records.fwf --layout layout.yaml` — fixed-width format works with an explicit layout.
- [ ] **`decoy storm scan data.csv`** (the deprecated alias) — still functions identically to `analyze`, only emits a deprecation notice, does **not** error. Removal target is 0.2.0 — confirm it isn't accidentally already broken/removed.
- [ ] `decoy storm integrity masked.csv --source source.csv --config pipeline.yaml` — all three post-mask check buckets (`residual_pii`, `fk_preservation`, `policy_validation`) populate.
- [ ] `decoy storm fields scan.json --pii high --quasi` — filter combination works.
- [ ] `decoy storm show scan.json <field>` — per-field detail card renders.
- [ ] `decoy storm diff baseline.json new.json --strict` — exits 1 on a deliberately introduced PII-bucket regression (bump a field from low to high PII between two scans and confirm strict mode catches it).
- [ ] `decoy storm test` — fake animation + summary card, confirm **no data is read and nothing is written** (run in an empty dir, confirm dir stays empty after).

### `decoy vault` / `decoy evidence` / `decoy report`
- [ ] `decoy vault info vault.bin --config pipeline.yaml` — entry count/namespaces/dropped-ambiguous count shown; using the WRONG config (different seed) correctly fails with exit 1.
- [ ] `decoy evidence show evidence.json` — human-readable card renders.
- [ ] `decoy evidence verify evidence.json` — clean run: exits 0.
- [ ] **Evidence verify limitation, positive case**: edit a masked output file after a run, re-run `decoy evidence verify` — drift correctly detected (non-zero exit, `EXIT_FINDINGS`).
- [ ] **Evidence verify limitation, documented negative case**: hand-edit the evidence manifest JSON itself AND recompute `manifest_hash` by hand to match — confirm `verify` does **NOT** catch this (per the doc: "UNKEYED SHA-256... does NOT detect a motivated tamperer"). This is a documented limitation, not a bug — confirm the doc is accurate, not stale or overstated.
- [ ] `decoy report render evidence.json --out report.html` — self-contained offline HTML, opens without needing network access; confirm no raw row values/PII leak into the report (grep the HTML for anything that looks like source data).
- [ ] `decoy report render evidence.json --format markdown --out report.md` — plain Markdown variant.
- [ ] `decoy report compare old-evidence.json new-evidence.json` — fingerprint/row-count/warning deltas reported correctly on two runs of the same pipeline with a source change in between.
- [ ] `decoy report show <run-id>` and `decoy report diff <run-id-a> <run-id-b>` — see Section 4 (requires the full project/catalog/jobs lifecycle first).

### `decoy strategies` / `decoy providers` / `decoy checksums` / `decoy validators`
- [ ] `decoy strategies list` — all engine strategy handlers registered; count matches `docs/capability-matrix.md` (22 masking strategies, per engine audit).
- [ ] `decoy strategies inspect fpe` — parameters/behavior shown correctly.
- [ ] `decoy providers list` — 34 registered providers (Faker/Mimesis/composite/decoy_native), backend type + poolable flag shown.
- [ ] `decoy checksums list` / `decoy validators list` — non-empty, matches engine's registered checksum schemes / job-level validators (11 built-ins).

### `decoy project` / `decoy catalog` / `decoy jobs`
- [ ] `decoy project init` — creates `.decoy/{workspace.json,scans,runs,evidence,reports}/`; running it again is a no-op (idempotent, doesn't overwrite).
- [ ] `decoy project show` — resolves upward from a subdirectory (like `git` finding `.git/`), not just cwd.
- [ ] `decoy catalog add ./data/customers.csv --sensitivity full-sensitive` — entry registered; confirm raw data is NOT copied into `.decoy/catalog.duckdb` (only metadata).
- [ ] `decoy catalog show <id-prefix>` — 4-character prefix match resolves correctly, including the ambiguous-prefix error case (two entries sharing a prefix).
- [ ] `decoy jobs list` — shows runs recorded by prior `decoy run` invocations, most-recent first.
- [ ] `decoy jobs watch <run-id>` — always shows an already-complete status (local runs are synchronous — confirm this is actually true and there's no misleading "in progress" state ever shown).

### Deprecated / removed surfaces
- [ ] **`forge <anything>`** — the deprecated shim console script. Confirm it prints the migration-redirect message and exits with code 2, and critically that it does **NOT** actually execute whatever subcommand was passed. This is the single clearest coverage hole found in exploration — no e2e test currently exercises the installed `forge` entry point directly.
- [ ] **`decoy platform ...`** — confirm this command group does **not** exist (removed as a phantom command, commit `ba13ab4`). Should fail as an unrecognized command with Typer's standard "no such command" error, not partially work or hang.

### Exit-code contract sweep
Cross-check against `src/decoy/cli/exit_codes.py`:
- [ ] Exit `0` (OK) — any successful `decoy run`.
- [ ] Exit `1` (USAGE) — `decoy run` against a malformed YAML.
- [ ] Exit `2` (DEPRECATED_SHIM) — `forge` only (see above); confirm no other command ever returns 2 for an unrelated reason.
- [ ] Exit `3` (RUNTIME) — force an unexpected crash (e.g. corrupt an intermediate file mid-pipeline if feasible) and confirm it's 3, not silently swallowed into 1.
- [ ] Exit `4` (FINDINGS) — `decoy storm integrity` / `decoy validate distribution --mode fail` / `decoy evidence verify` on drifted files, each independently confirmed.

---

## Section 2 — Documentation-drift check

- [ ] `decoy-engine/docs/cli.md`'s top-level command table omits `decoy fit` even though `decoy-engine/docs/what-we-cannot-prove.md` and `docs/compatibility-contract.md` both treat `decoy fit --epsilon` as load-bearing. Confirm `decoy fit --epsilon` still works from the CLI (it does, per `docs/cli-reference.md` in this repo) and file a follow-up doc fix against `decoy-engine` — this checklist doesn't fix it, just flags it.

---

## Section 3 — Engine capability probes (things automated tests don't fully close)

Run these against `/home/cam/vscode/decoy-engine` directly (Python API), or via the CLI
where a command surface exists.

- [ ] **Out-of-core / 50M+ row memory claim**: unit + parity tests exist, but per the
  2026-07-12 adversarial architecture review, no real multi-million/50M-row memory
  benchmark has actually been run, and "the public lazy OOC boundary is still eager."
  Run a genuinely large out-of-core FK job (`decoy_engine.execution.out_of_core.run_fk_out_of_core`)
  while watching RSS (e.g. `/usr/bin/time -v` or a memory profiler) and confirm it does
  NOT silently materialize the full frame in memory.
- [ ] **TB-5 OOM auto-router default flip** (`73998a5`) — this changed default routing
  for every eligible job. Re-run 2-3 representative jobs that previously routed
  full-frame and confirm **output is byte-identical**, only the internal routing path
  changed.
- [ ] **DE-08 quarantine hardening** (`20add89`) — no dedicated `test_de08_*.py` file;
  coverage is folded into general quarantine tests. Manually construct a row-error
  during a table-commit failure and confirm quarantined rows persist correctly rather
  than being silently dropped.
- [ ] **DE-02 KeyProvider — confirm it fully closes the "seed-entropy/key-separation
  defect"** the 2026-07-12 adversarial review called "more fundamental" and left
  unresolved (the review predates DE-02 by 2 days; no later re-review exists in-repo).
  This is the single highest-value manual confirmation on this list — walk through the
  `SecretKeyProvider` vs. `SeedKeyProvider` fail-closed-at-GA behavior directly and
  confirm a keyed plan with no ≥32-byte secret hard-errors at GA as documented.
- [ ] **FPE orphan-remap partial-charset leak** (documented, accepted limitation in
  `what-we-cannot-prove.md`): construct a MIXED in/out-of-charset orphan key under
  `orphan_policy: remap` and confirm it leaks the out-of-charset characters exactly as
  documented — i.e. confirm the doc is accurate today, not stale.
- [ ] **Unsigned joblib model-pack loading**: confirm the ML classifier pack loader
  (`storm/model_pack/`) actually enforces `DECOY_PACK_SIGNING_KEY` and rejects an
  unsigned/tampered `.joblib` file rather than silently loading it.
- [ ] **Connector contract tests are moto-mocked only** — if in scope for this pass, do
  one real smoke test against an actual S3/GCS/SFTP endpoint (not just the mocked
  contract tests) for at least one connector.
- [ ] **NER-backed `text_redact`**: confirm graceful degradation both with and without
  the optional `ner` extra installed (`pip install decoy-engine[ner]` +
  `python -m spacy download en_core_web_sm`) — should fall back to regex-only when
  spaCy/model absent, never error.
- [ ] **`decoy fit --epsilon` DP release**: only unit-tested (`test_dp.py`, 9 tests), no
  acceptance-level job exercises it end to end. Manually run a DP release and
  sanity-check the noised histogram is plausible (not wildly divergent from ground truth,
  not accidentally exact/un-noised).

---

## Section 4 — Cross-cutting / integration flows

- [ ] **Full local-workspace lifecycle**: `decoy project init` → `decoy run pipeline.yaml
  --evidence-out evidence.json` → `decoy catalog add evidence.json --type evidence` →
  `decoy jobs list` (confirm the run appears) → `decoy jobs show <id>` → `decoy report
  show <run-id>` → `decoy report diff <run-id-a> <run-id-b>` (second run against a
  changed source) — confirm IDs thread through every stage without manual bookkeeping.
- [ ] **`--notify` best-effort semantics, negative case**: point `--notify` at a
  deliberately unreachable webhook URL and confirm the run still succeeds and exits 0 —
  notify failure must never change the run's exit code, and this must hold for both
  `--notify-on always` and `--notify-on failure` on an otherwise-successful run.
- [ ] **`decoy preflight` catches problems before `decoy run` would**: point preflight at
  a config with a missing source file — confirm it fails cleanly with a specific message,
  *before* attempting a real `decoy run` on the same config (which should also fail, but
  preflight should be faster/clearer).
- [ ] **Acceptance/ship-gate harness itself**: run `python scripts/test_flight.py` (or
  `pytest testflight -m testflight`) once manually in `decoy-engine` and read
  `testflight/_artifacts/report.md`. This harness is on-demand + nightly only, **not** a
  per-PR required gate — confirm it's actually green right now, not just historically
  green at last manual run.
- [ ] **`tests/perf/` re-run** (decoy-engine): lower-frequency-run than the unit suite;
  confirm perf/governor tests (`test_governor_reroute_completion.py` etc.) are currently
  green, not stale from a prior pass.

---

## Sign-off

| Field | Value |
|---|---|
| QA engineer | |
| Date | |
| decoy-cli commit tested | |
| decoy-engine commit tested | |
| Total items | Section 0: 6 · Section 1: ~65 · Section 2: 1 · Section 3: 9 · Section 4: 5 |
| Blocking failures found | |
| Non-blocking issues filed | |
| Overall verdict | Pass / Pass with notes / Blocked |
