# Decoy CLI interface redesign — pre-release capability audit & command-surface plan

Status: writeup / design, PRE-RELEASE (2026-10-23). Not build-ready: this settles the SHAPE of the whole
CLI surface. A per-slice build plan + the normal gate chain (Codex plan-gate -> build -> dennis -> Codex
final) come before any code. Breaking CLI change, acceptable under the CLI's pre-GA "hard delete"
convention (no migration shims).

Scope: CLI surface only. No `decoy-engine` behavior change (one small engine export is noted and already
tracked elsewhere). The CLI owns command surface, terminal UX, exit codes, packaged templates, and example
configs; data behavior stays in the engine (AGENTS.md role split).

Rules consulted: 00-universal, documentation, api-and-compatibility, scope-discipline, risk-and-exceptions.

Relationship to existing docs: this is the umbrella **PRE-RELEASE CLI CAPABILITY AUDIT (Cam 2026-10-23)**
that `docs/plans/2026-10-23-validate-consolidation-writeup.md` and
`docs/plans/2026-09-30-cli-source-format-dispatch.md` call out as the thing that "sets the whole command
surface." Those two remain the build slices for the `validate` gate and the file-format contract; this doc
sets the surface they slot into and does not re-decide their internals. The cross-repo roadmap
(`decoy-platform/docs/ROADMAP.md`) is the index; this plan lives in the repo that implements it.

---

## 1. Goal

Redesign the `decoy` command surface from scratch for a developer working from the shell, before GA
freezes it. "From scratch" is a design stance, not a rewrite of the engine wiring: the command modules that
already call the engine correctly are kept; what changes is the *shape* a user sees — which verbs exist,
how they group, what they are named, and which engine capabilities are surfaced at all.

Two forces make now the moment:
1. The surface has sprawled to ~17 top-level commands + 11 sub-apps (~50 commands) with three different,
   mutually-disagreeing "what commands exist" lists (README table, root help, actual registration).
2. The engine exposes 149 public symbols across 16 capability domains; several of the strongest
   (FK-aware subsetting, quality/fidelity + synth privacy metrics, compliance disguises, job-level
   validators) are **not surfaced in the CLI at all**, while four near-duplicate commands surface the same
   "compile a plan" capability.

The deliverable of the build work this plan gates is: one coherent, discoverable, scriptable surface, with
one generated source of truth that README and root help derive from.

## 2. Method

- **Engine audit** — inventoried `decoy_engine.__all__` (149 symbols) and the generated
  `decoy-engine/docs/capability-matrix.md` (23 mask strategies, 12 generation strategies, 34 providers,
  6 connectors, 25 STORM detectors, 10 disguises), grouped into 16 domains with an exposure verdict each.
- **CLI audit** — read every module under `src/decoy/cli/` and the registration in `src/decoy/__main__.py`
  against the generated `docs/cli-reference.md` (2554 lines); catalogued commands, flags, overlaps,
  naming drift, and vestigial surface. (The CLI could not be executed in the audit sandbox — engine pins
  Python `<3.13`; findings are from source and the generated reference, which the drift sentry keeps true.)
- **External research** — the Command Line Interface Guidelines (clig.dev), the 12-Factor CLI thesis
  (oclif), and the noun-verb / verb-noun conventions of `gh`, `git`, `kubectl`, `docker`. Sources in §12.

## 3. Engine capability inventory — what we *could* surface

16 domains. "Exposed" = reachable from today's CLI; "latent" = public (or near-public) engine capability
with no CLI door. Pre-GA caveat: `decoy_engine.release.py` has `RELEASE_PHASE="pre-ga"`, so the
compatibility contract and the DE-02 keyed-secret hard gate are wired but not yet enforced.

| # | Domain | Core entrypoints | CLI exposure |
|---|--------|------------------|--------------|
| 1 | Config & validation | `PipelineConfig`, `validate_config`, `run_config_only_checks` | exposed (`validate config`) |
| 2 | Plan compilation | `compile_plan`, `plan_to_yaml`, `job_seed_for_config` | exposed ×2 (`plan`, `compile`) — redundant |
| 3 | Masking execution (spine) | `run_pipeline` -> `ExecutionResult.outputs` | exposed (`run`) |
| 4 | Chunked / out-of-core | `run_mask_chunked`, `check_out_of_core_compatibility`, auto-chunk router | partial (`run --chunked`); OOC query latent |
| 5 | Synthetic generation | `generate_tables`; composite providers; pools | exposed (`run` generate mode); **pinned/streamed gen latent** |
| 6 | STORM profiling & PII | `run_storm` -> `StormProfile` (25 detectors, re-id risk); **`load_disguises` (10 bundles)** | profiling exposed (`storm`, `profile`); **disguises latent** |
| 7 | Relationships, FK & subsetting | graph builders; `run_subset`/`plan_subset`/`run_subset_preflight` | exposed (`subset`) — but subset APIs not yet top-level in engine |
| 8 | Providers & identifier families | `ProviderRegistry`, `register_faker_provider*`, identifier adapters, `checksums` | exposed (`providers`, `checksums`); custom-provider *loading* latent |
| 9 | Connectors & IO | `FileSource`/`FileSink` SDK, S3/GCS/SFTP, `read_fixed_width`, **`run_discovery_sql`** | SDK + fixed-width exposed via config; **SQL-over-output latent** |
| 10 | Vault, unmask, reversible tokens | `unmask_pipeline`, `VaultWriter`, `load_vault` | exposed (`unmask`, `vault info`) |
| 11 | Capacity estimation / OOM | `estimate_job_capacity` -> `CapacityVerdict` | exposed (`preflight`) |
| 12 | Determinism, seeding, keys | `derive`, `KeyProvider`, `make_key_resolver`, `mask_secret_ref` | exposed as `run` flags/config |
| 13 | Quality / fidelity reporting | `PostValidationRunner`, dist-fidelity, **synth attack metrics (DCR), DP** | **largely latent** — only `validate distribution` + `run --fidelity` wired |
| 14 | Structured events / telemetry | `ExecutionContext`, `emit_*`, timing collector | plumbing (progress UI seam); `bench` latent |
| 15 | Native companion | `native_companion_status()` | exposed (`doctor`) |
| 16 | Licensing | `LicenseVerifier` (**stub: always free tier**), `SchemaInspector` (**NotImplementedError**) | do not build on — stubs |

**Biggest latent surfaces, in priority order (strongest net-new CLI value):**
1. **Compliance disguises** (domain 6) — 10 named bundles (HIPAA 21-rule Safe Harbor, PCI, GDPR, GLBA,
   CCPA, FERPA, SOX, CPNI, PC) that map detectors -> masking rules. Highest-leverage: turns `scan` from
   "here is your PII" into "here is a compliant config." Wire into `init --preset` and `scan --suggest`.
2. **Quality / fidelity + synthetic-privacy metrics** (domain 13) — distribution fidelity grading plus
   DCR / new-row-synthesis attack metrics. The whole `quality` compute subtree is lazy and absent from
   top-level `__all__`; needs an engine export decision, then a `report fidelity` surface.
3. **Job-level validators** (domain 13) — 11 built-ins (luhn / npi / iban / vin / fk_intact /
   no_orphan_children / leak_check / regex_match / column_in_set / parent_window_respected /
   reconciliation_holds) + quarantine routing. Surface as `list validators` + run them in `report integrity`.
4. **SQL over masked output** (domain 9) — read-only `run_discovery_sql` (SELECT/WITH/VALUES/TABLE only,
   in-memory DuckDB) is a clean `decoy query OUTPUT "SELECT ..."`.
5. **Pinned generation** (domain 5) — seed-independent SHA-256 fingerprint for byte-reproducible synthesis;
   a `run --pin`/`--fingerprint` reproducibility flag.

Two stubs to **not** design around: `LicenseVerifier` (always `{"tier":"free"}`) and `SchemaInspector`
(raises `NotImplementedError`). No tier/feature gating exists to surface.

## 4. Current CLI surface audit — what we *have*

Registered surface (`src/decoy/__main__.py:112-138`): ~17 top-level commands + 11 sub-apps. The problems,
in descending order of how much they hurt a new user:

**(a) Redundancy — the same capability behind many doors.**
- *"Compile a plan and report decisions"* is reachable four+ ways: `plan` (`cli/plan.py`), `compile`
  (`cli/compile_explain.py`), `compile --explain`, `preflight` (`cli/preflight.py`), and partly
  `validate config`. `plan` and `compile` even share a near-identical one-line docstring.
- *"Analyze a source file"* has three entry points: `profile <source>`, `storm analyze <source>`, and
  `fit <source>` — all ingest a source and emit stats/structure (fit adds a DP-budgeted snapshot).
- *"Judge a run's output"* is split across two sub-apps and the `validate` group: `evidence show/verify`,
  `report render/summarize/compare/show/diff`, `validate distribution`, and `storm integrity` — five
  "render a manifest / diff / fidelity / integrity" verbs with three different input models (manifest file,
  cataloged run, source+output pair).

**(b) Naming / structure inconsistency.**
- `--out` (subset, plan, storm, report, init, catalog) vs `--output` (fit, unmask, schema) for the same idea.
- `--json` is overloaded: everywhere it means "machine envelope on stdout," but in `plan` it means
  "emit JSON instead of YAML" — different semantics on the same flag name.
- Top level mixes bare verbs (`run`, `fit`, `compile`, `plan`, `unmask`, `subset`, `profile`) with
  noun-grouped sub-apps (`catalog list`, `jobs show`). `storm` is a *brand/event name* ("the STORM event"),
  so `storm analyze` reads verb-verb, not noun-verb.
- `storm show` / `storm fields` use one inspection verb vocabulary while `strategies inspect` /
  `providers inspect` use another.

**(c) Vestigial / confusing surface.**
- `jobs watch` admits in its own docstring it does nothing ("always complete — local runs are synchronous")
  — a server concept with no local meaning.
- `storm test` ships the rain/lightning *animation preview* as a production command.
- `storm scan` is a live deprecated alias ("removed in 0.2.0") still in the surface.
- `vault` sub-app has only `info` despite the README stating vault has "no CLI wiring at all today."

**(d) Platform-mirror local state.** `project` / `catalog` / `jobs` manage a local `.decoy/` DuckDB
workspace that each disclaims as "LOCAL ONLY — does not sync with the platform server." This mirrors the
commercial platform the OSS CLI only stubs; `run` auto-records into it when a workspace exists.

**(e) Doc drift — three disagreeing surfaces.** The README "Common commands" table documents ~8 commands
(`demo`, `init`, `validate config/distribution`, `run`, `storm analyze`, `templates list`, `explain`). Root
help (`__main__.py:57-81`) advertises a *different* ~17-command list (incl. `compile --explain`,
`subset --dry-run`, `project init`, `catalog list`, `jobs list`, `report show/diff`). The actual
registration is a third list. ~20+ commands have no README coverage at all.

**What's already good and must be preserved.** The six-code exit contract (`cli/exit_codes.py`) is clean and
scriptable. The output discipline is sound — `OutputMode` default/json/quiet, JSON envelope to stdout,
messaging/progress/animations to stderr with TTY + `NO_COLOR` auto-disable, `--json`+`--quiet` mutually
exclusive, centralized theme tokens (`ui/theme.py`). The redesign keeps these and makes them *uniform*
(today `plan` has only `--json`; `schema`/`info`/`doctor` effectively only `--json`).

## 5. Design principles (from the external research, adapted)

From the Command Line Interface Guidelines and the 12-Factor CLI thesis (§12), the ones that bind here:

1. **Human-first, machine-ready.** Rich default output; `--json` (stable envelope) and `--quiet` on *every*
   command for scripts and CI. Data to stdout, everything else to stderr. (Already the convention — make it
   universal.)
2. **Consistency over cleverness.** One verb vocabulary, one flag vocabulary. Users build muscle memory;
   `--out`/`--output` and dual-meaning `--json` break it.
3. **Discoverability / conversation.** Lead help with examples; suggest the next command; "did you mean"
   on typos; no-args shows concise help. Three disagreeing command lists is the opposite of discoverable —
   collapse to one generated source of truth.
4. **Say just enough; no ambiguous twins.** Don't ship two commands that do the same thing (`plan` vs
   `compile`) or near-homonyms. Fold or delete.
5. **Composability & robustness.** Keep the stable exit-code contract; validate input early; be responsive
   (feedback <100ms, progress on long runs — already via the Rich seam); make outputs idempotent and
   overwrites explicit.
6. **Confirm by severity.** Overwriting an output file or a vault is moderate→prompt + `--force`/`--yes`
   to bypass; nothing silently clobbers.
7. **Future-proof additively.** After GA, new flags not changed behavior; script authors told to pin
   `--json`. Pre-GA, this redesign spends the one breaking budget we have.

## 6. Proposed command surface

A small set of **workflow verbs** at the top level (the golden path a dev walks: *look → author → check →
run → verify*, plus *reverse*), with **nouns only where a resource genuinely has several operations**
(reference catalogs, run history). This is the `gh`/`git` hybrid CLIG endorses: top-level verbs,
noun-grouped subcommands, one consistent vocabulary throughout.

### Golden path (top-level verbs)

```
decoy init [SOURCE]            Scaffold a pipeline. Q&A by default; with a SOURCE, STORM column-aware
                               (--preset minimal|hipaa|pci|gdpr maps to a compliance disguise bundle).
decoy scan SOURCE              Profile + PII/risk in one look. (Merges today's `profile` + `storm analyze`.)
decoy validate CONFIG          Unified pre-run gate: config + compile + preflight in one report.
decoy run CONFIG               Execute: mask, generate, or mixed — mode inferred from config.
decoy subset CONFIG            Cut a referentially-complete FK-aware slice (pre-mask).
decoy unmask CONFIG MASKED     Reverse fpe columns / read the token vault.
decoy report RUN|MANIFEST      Judge a run's output: summary, fidelity, integrity, evidence, diff.
decoy demo                     Bundled end-to-end scan->mask walkthrough. (Keep — best onboarding.)
```

### Reference & help (nouns + `list`/`show`)

```
decoy explain TOPIC            Plain-English concept help (~18 topics). Keep — strong discoverability.
decoy list KIND                strategies | providers | detectors | validators | checksums |
                               templates | disguises  (one verb for every engine registry)
decoy show KIND NAME           Detail for one item (replaces `strategies inspect`, `storm show`, etc.).
decoy schema                   PipelineConfig JSON Schema (alias of `show schema`; keep top-level for CI).
```

### Diagnostics & (optional) history

```
decoy doctor                   Engine / deps / native-companion health.
decoy history ...              OPTIONAL local run log (folds project+catalog+jobs). See owner decision D3.
```

### Subcommand shape (where a verb owns a cluster)

- `decoy validate [CONFIG]` — default runs the whole gate; `validate config|compile|preflight` run one
  layer each; `validate compile --explain` is the plan-explanation path. **Per the validate-consolidation
  writeup**, which this adopts unchanged except that distribution-fidelity moves out (see below).
- `decoy scan SOURCE` — produces a profile (`--out scan.json`). Saved-scan ops become subcommands:
  `scan show SCAN FIELD`, `scan diff OLD NEW`. The STORM rain/lightning animation stays under `scan`
  (it's good UX); `storm test` as a standalone animation-demo command is deleted.
- `decoy report` — the single post-run noun. Collapses `evidence` + `report` (×5) + `validate distribution`
  + `storm integrity`:
  ```
  report show RUN|MANIFEST        Human summary (was report show/summarize, evidence show).
  report render MANIFEST -o FILE  HTML/Markdown report (was report render).
  report verify MANIFEST          Fingerprint check (was evidence verify).
  report fidelity SOURCE OUTPUT   Distribution fidelity grade (was validate distribution).
  report integrity MASKED --source SRC   Residual-PII / FK / validator check (was storm integrity).
  report diff A B                 Data-level compare of two runs/outputs (was report diff/compare).
  ```

### What this does to the count

~50 commands -> **8 workflow verbs + 4 reference/help + 2 diagnostics**, each with a tight, named
subcommand set. Every former capability keeps a door (§8); the doors just stop overlapping.

### Net-new doors for latent capability (prioritized; each its own small build slice)

- `init --preset hipaa` / `scan --suggest` wire **disguises** (domain 6) — the top recommendation.
- `report fidelity [--privacy]` surfaces **quality + DCR/synth metrics** (domain 13; needs engine export).
- `list validators` + `report integrity` run the **job-level validators** (domain 13).
- `decoy query OUTPUT "SELECT ..."` surfaces read-only **discovery SQL** (domain 9) — optional, high delight.
- `run --pin` surfaces **pinned-generation reproducibility** (domain 5) — optional.

## 7. Global conventions (apply to every command)

- **Output:** rich default; `--json` = stable machine envelope on stdout (fix `plan`'s off-meaning);
  `--quiet/-q`; `--verbose/-v`. Data->stdout, messaging/progress/errors->stderr. `NO_COLOR` + TTY detection
  already honored; keep.
- **Flags:** standardize `--output/-o` (retire `--out`), `--force/-f`, `--dry-run/-n`, `--yes/-y`,
  `--no-input`. Full-word long flags for everything; single-letter only for the common few.
- **Exit codes:** keep the six-code contract verbatim (0 OK / 1 USAGE / 3 RUNTIME / 4 FINDINGS /
  5 CAPACITY). `2 EXIT_DEPRECATED_SHIM` (the legacy `forge` entry) is a hard-delete candidate pre-GA
  (owner decision D4). The aggregated `validate` precedence is settled in the consolidation writeup.
- **Help:** examples lead every command's help; no-args -> concise help; "did you mean" on typos; a support
  URL in top-level help; `explain` cross-links. README table + root-help list are **generated from / checked
  against** `docs/cli-reference.md` so the three surfaces can never diverge again.
- **Errors:** typed engine errors mapped to the right exit code with an actionable hint (the cross-version
  vault case in the capability-adds plan is the pattern); tracebacks only under `--verbose`.
- **Interactivity:** prompts only when stdin is a TTY; `--no-input` disables all; every prompt has a flag
  equivalent. Overwriting an output/vault prompts unless `--force`/`--yes`.

## 8. Capability coverage map (nothing dropped silently)

| Engine capability (§3) | Today | Proposed |
|---|---|---|
| Validate / lint config | `validate config` | `validate config` (layer of `validate`) |
| Compile / explain plan | `plan`, `compile`, `compile --explain` | `validate compile [--explain]` (one door) |
| Mask / generate / mixed | `run` | `run` (+ `--explain-plan`, `--fidelity`, `--pin` flags) |
| Chunked / out-of-core | `run --chunked` | `run --chunked`; OOC eligibility shown in `validate preflight` |
| Profile + PII + risk | `profile`, `storm analyze` | `scan` (one door) + `scan show`/`scan diff` |
| Distribution fit (statistical gen) | `fit` | `fit` (kept; documented as generation-prep) |
| FK-aware subset | `subset` | `subset` |
| Unmask / vault | `unmask`, `vault info` | `unmask`; `vault info` -> `report`/`show vault` (D5) |
| Capacity / OOM preflight | `preflight` | `validate preflight` |
| Evidence / fidelity / integrity / diff | `evidence`, `report`×5, `validate distribution`, `storm integrity` | `report {show,render,verify,fidelity,integrity,diff}` |
| Strategies/providers/checksums/validators | 4 sub-apps | `list KIND` + `show KIND NAME` |
| Templates | `templates list/show` | `list templates` + `show templates NAME` |
| Config JSON Schema | `schema` | `schema` (+ `show schema`) |
| Native / deps health | `doctor` | `doctor` |
| Local run history | `project`/`catalog`/`jobs` | `history` (optional) or dropped (D3) |
| Concepts help | `explain` | `explain` |
| **Disguises** (latent) | — | `init --preset`, `scan --suggest`, `list disguises` |
| **Quality/DCR metrics** (latent) | — | `report fidelity --privacy` |
| **Discovery SQL** (latent) | — | `decoy query` (optional) |

## 9. Migration (breaking, pre-GA hard delete)

- No shims (CLI pre-GA convention; the `forge` shim is itself a delete candidate, D4). Deleted top-level
  commands fail with Typer's "No such command."
- Rewire `src/decoy/__main__.py`; delete/merge the affected `cli/` modules; rebuild the test surface
  (`tests/e2e/test_cli_surface.py` is the drift net).
- Regenerate `docs/cli-reference.md` (the drift sentry); rewrite the README "Common commands" table and the
  root-help block **from** the regenerated reference, establishing it as the single source of truth.
- Update `examples/`, `explain` topic text, and any internal scripts that invoke old forms.
- One engine dependency: `report fidelity --privacy` needs the `quality` compute surface exported from
  `decoy_engine.__all__` (today lazy/private). That's an additive engine export, tracked as its own slice;
  the rest of this plan is pure CLI-side.

## 10. Owner decisions before build

RESOLVED 2026-10-23 (Cam): all six locked to the recommended option ("go with recommended"). This section
is kept as the decision record; the build sequences against these in
`docs/plans/2026-10-23-cli-redesign-sprints.md`. The locked choices: D1 one `run` (mode inferred, no
`mask`/`generate` aliases); D2 rename to `scan` (STORM stays the engine profiler + keeps the animation);
D3 drop `project`/`catalog`/`jobs`, CLI goes stateless and `report` is file-first; D4 hard-delete the
`forge` shim and `EXIT_DEPRECATED_SHIM` (exit code 2); D5 `vault info` -> `report vault`, no standalone
`vault` noun; D6 disguises in the first cut, `query`/`run --pin` as fast-follows, `report fidelity
--privacy` gated on the engine `quality` export.

- **D1 — Golden-path verb set.** Confirm the 8 top-level workflow verbs, and whether `run` stays one
  command with mode inferred, or ships `mask`/`generate` as thin aliases for discoverability.
  (Recommendation: one `run`, mode inferred, `--mode` override; aliases are cheap to add later and risk the
  "ambiguous twins" anti-pattern now.)
- **D2 — STORM brand.** Drop `storm` from the command name in favor of `scan` (keeps the profiler named
  STORM in the engine and keeps the animation), or keep `decoy storm ...`?
  (Recommendation: `scan`; `storm analyze` reads verb-verb and buries the capability behind a brand.)
- **D3 — Local state.** Keep a local run log at all, and if so as one `history` noun, or drop
  `project`/`catalog`/`jobs` and make the CLI stateless (reports read evidence manifests + files directly)?
  (Recommendation: drop the platform-mirror trio for the OSS CLI; make `report` file-first. It's the
  largest sprawl reduction and removes the "LOCAL ONLY / does not sync" confusion. Revisit a local log only
  if a real need appears.)
- **D4 — `forge` shim / `EXIT_DEPRECATED_SHIM`.** Hard-delete the legacy `forge` entry point and exit code 2
  pre-GA, or keep through GA? (Recommendation: delete pre-GA.)
- **D5 — `vault info` home.** Under `report`, under `show`, or kept as a thin `vault` noun if vault CLI
  wiring grows? (Recommendation: `report vault` / defer until vault gets real write-side wiring.)
- **D6 — Latent-capability scope for the first cut.** Which net-new doors ship with the redesign vs. land
  as follow-ons? (Recommendation: disguises in the first cut — highest leverage, already half-present via
  `init --preset`; `query` and `--pin` as fast-follows; `report fidelity --privacy` gated on the engine export.)

## 11. Phasing & acceptance sketch

This plan gates a sequence of small build slices, each with its own plan + the standard gate chain. The two
in-flight slices slot in unchanged:
1. **`validate` gate** — `docs/plans/2026-10-23-validate-consolidation-writeup.md` (fold preflight+compile
   under `validate`; this plan additionally moves `distribution` -> `report fidelity`).
2. **File-format contract** — `docs/plans/2026-09-30-cli-source-format-dispatch.md`.
3. Then: `scan` merge (profile+storm) · `report` consolidation · `list`/`show` unification · flag/output
   normalization · deletions (`storm test`/`scan` alias, `jobs watch`, platform-mirror trio per D3) ·
   disguise wiring · README/root-help regeneration from the reference.

Acceptance, at the surface level (each slice expands its own):
- Every registered command is in `docs/cli-reference.md`, and the README table + root help are generated
  from it (no three-way drift; a drift-sentry test enforces it).
- Every command accepts `--json`/`--quiet`/`--verbose` with identical semantics; `--output/-o` is the one
  spelling; no flag has two meanings.
- Each engine capability in §8 resolves to exactly one command path (no duplicate doors).
- The six-code exit contract is unchanged; `validate` aggregation follows the consolidation writeup.
- No deleted command resolves; no vestigial/animation-demo command remains in the surface.

## 12. Sources (external research)

- Command Line Interface Guidelines — <https://clig.dev/> (Prasad, Firshman, Tashian, Parish). Philosophy,
  arguments & flags, output, errors, help, subcommands, interactivity, robustness, future-proofing,
  configuration, naming.
- 12-Factor CLI Apps — Jeff Dickey / oclif (2018): great help is essential; prefer flags to positional args.
- Convention precedents: `gh` (noun-verb), `git` / `kubectl` / `docker` (verb-noun), `.NET` CLI guidelines
  (top-level verbs, noun subcommands). Consensus: consistency matters more than which order.
