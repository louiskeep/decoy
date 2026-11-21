# Owner decisions (dated)

Status: record

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

- **2026-11-21 (Windows QA).** Windows stays in 1.0 (the 2026-11-18 call) and is built last, after the V1 build. QA covers the Windows build as well as Linux and macOS: the Windows install, upgrade, rollback and demo run are QA items before release. Install stays a one-line script (`install.ps1`), with no `.exe` or setup wizard in 1.0. A Windows code-signing certificate is an open owner question.
- **2026-11-21 (REL-GATE Q3, go with recommended).** (a): the engine flips `RELEASE_PHASE` to `"ga"` in the D-4 launch engine release, so the 1.0.0 CLI ships on a binding compatibility contract. RG-GA and RG-GA-C are built before the freeze.
- **2026-11-21 (work found off the roadmap, go with recommended).** COLUMN-SHAPE-RULE (owner decision of the same day; `bucket_perturb` format detection is a freeze item) becomes a 1.0 row in the mask group. PRE-SCAN-RUN stays the 1.0 row added by CLI #368. F07 82-E3b (engine #684) is a new feature on row 82, which the 2026-11-18 scope triage moved to 1.1, so it is held as a draft until 1.1 and no further F07 slices are built before 1.0.
- **2026-11-21 (language write-up findings).** Cloud bucket delivery stays out of 1.0 (row 64 CLI-CLOUD). Go with recommended on the rest: `decoy run` running the `pre_scan` block becomes 1.0 row PRE-SCAN-RUN; the missing line number on `.decoy` schema errors goes into DECOY-LANG; the guide `date_shift` examples are checked inside DATE-SHIFT-FORMAT.
- **2026-11-21 (engine data-flow gaps).** Go with recommended on the twelve gaps in vault `30_Resources/Decoy-Engine-Data-Flow-Gaps.md`. Gap 2 (no row-count check after a mask handler on the pandas paths) becomes 1.0 row HANDLER-ROW-COUNT. Gap 1 (config read after compile) and gaps 4, 5, 6 and 8 (mutation and golden-test depth) are v1+ candidates in the run group. Gap 9 (the `Plan` docstring seed history) and the gap 7 contract sentence on `vault-key` are doc fixes carried by the HANDLER-ROW-COUNT slice. Gaps 3, 7, 10, 11 and 12 are not gaps.
- **2026-11-19 (init wizard stops).** The `decoy init` guided wizard (row 32b) is not developed further. Finish
  what is open (engine #653 E1 and #654 E2) and stop; that is the 1.0 scope for this surface. If the surface
  is incomplete as it stands, 1.0 reduces it to simple table structures only. The owner is building a different
  way to author pipelines. E1 and E2 ship in the experimental tier, since no 1.0 command calls them. The rest of
  `C:plan/init-wizard-v1-rest` is stopped.
- **2026-11-19 (Decoy language).** The Decoy language (`.decoy` files) is a 1.0 focus: it is the
  native way to define a pipeline, ahead of the wizard plus hand-edited YAML. YAML stays supported.
  `decoy validate`, `decoy run` and the other pipeline commands read `.decoy` directly in 1.0. An
  inferred line from `decoy init` carries a `?` review marker and `decoy run` refuses until it is
  cleared. The `lark` dependency and the lock regeneration it needs are approved. Row DECOY-LANG;
  plan `docs/plans/2026-11-19-decoy-language-completion.md` (decisions E1, E3, E4, E5).
- **2026-11-19 (Decoy language commands, O1 to O5).** The format command is `decoy fmt`. A run
  record keeps the compiled YAML next to the `.decoy` file's hash. A folder with both
  `pipeline.yaml` and `pipeline.decoy` is refused. `decoy init` writes `.decoy` by default at 1.0,
  with `--yaml` for the old output, after the loader and the run commands read `.decoy`; this is
  an output-format change only, so the wizard freeze otherwise holds. The subset guard gets one
  narrow exemption: `lang/_subset.py` may build the `subset` block (stores and dict displays);
  pop, delete and filtering stay banned everywhere. Plan
  `docs/plans/2026-11-19-decoy-language-commands.md`.
- **2026-11-19 (physical seam and Faker).**
  - Physical seam: option C. The physical-plan compiler stays and becomes a "what would run and why"
    explainer for every route; execution stays in today's routes. The shadow-only execution branches
    and audit C4 and C5 may be deleted. Work: SEAM-REASONS, then SEAM-EXPLAIN (run group, 1.x).
    Handoff: `handoffs/2026-11-19-engine-physical-seam.md`.
  - FAKER-REPRO owner questions: recommended on Q1 and Q3 to Q6. Q2: no upstream Faker pull requests.
  - Engine speed and route record (engine #715): recommended on Q1 to Q6. M1 blocks 1.0 (parts (a)
    and (c); part (b) only if small). F1, F3, F4 and M3 are V1. C1 and C4 are V1 if a slot is free,
    else 1.0.x. F2 is held to 2.0. `date_shift` requires `date_format`. GEN providers, types and
    catalog are V1. pip installs get a warning in V1 and a `native` extra in 1.x. Work with no row
    became named slots (1.0.x, 1.1, 1.2, 1.3); scheduled work stays where it is. Every 1.x speed
    release keeps output byte-identical.
- **2026-11-18 (owner calls on the bucket list).**
  - Opt-in defaults: F11 output ordering, F38 dataset metadata and F08 free-text identity binding stay
    opt-in for 1.0 (option A). The docs tell users to turn F08 on for free-text columns.
  - Upgrade key: 1.0 ships a backup release key and a coded refusal of an unknown version-document
    format (option B). Row UPGRADE-KEY. The owner creates the backup key and keeps it offline.
  - The 2.0 holding list was checked item by item: none of the ten needs 2.0. Generation, detection
    and profiling changes ship in 1.x behind a version setting that new configs get and old configs
    do not. The URL scheme check moves to 1.0 (FREEZE-SURFACE).
  - Source metadata reaches masked output on the out-of-core route. This is a leak and blocks 1.0:
    row OUTPUT-METADATA-LEAK.
  - Chunked and whole-file profiles do not disagree (no route merges chunks), but sampled numbers are
    shown as if whole-file and can wrongly flag a key column. Fixed before the freeze: row
    PROFILE-SAMPLE-LABELS.
- **2026-11-18 (release buckets and freeze work).** Anything that does not break the contract is v1+;
  anything that breaks it is v2 (`roadmap/2.0-holding.md`). Work that would be a breaking change after
  1.0 is done in v1: rows FREEZE-SURFACE, FREEZE-OUTPUT and FAKER-MIGRATE. Faker moves to 40.31 before
  the freeze, not after R1. The unreferenced platform reason codes (audit B9) stay in the registry as
  the platform wire contract, with the platform consumer recorded beside each (row 24zj). Default-on
  choices (F11, F38, F08) stay opt-in.
- **2026-11-18 (Windows is 1.0).** WIN-FEAS (row 89) and WIN-RUNNER (row 6) are back in 1.0: the owner
  must be able to download the CLI and demo it on a Windows machine. This reverses the same day's move
  of Windows to 1.x.
- **2026-11-18 (experimental tier).** 1.0 labels two surfaces experimental, so they may change in a 1.x
  minor: the Python API (`decoy.mask`, `decoy.scan`) and custom providers with the connector SDK. The
  `decoy library` commands are decided at the release gate. Row EXPERIMENTAL-TIER.
- **2026-11-18 (1.0 scope cut and roadmap split).** 1.0 is the rows in the 1.0 tables of the group
  files (`roadmap/groups/`), not the whole track; this replaces the 2026-11-05 "CLI 1.0 scope" entry
  below. A row blocks 1.0 only on freeze, safety or broken-today; additive rows are Later (1.x) and
  internal cleanup is Maintenance. INIT-WIZARD stays in 1.0: a user cannot be asked to hand build
  complex YAML on a new product they do not yet trust. CLI-CLOUD, CLI-DB-SRC, F01, the additive GEN
  rows and Windows move to 1.x. New work enters through `roadmap/inbox.md`. Record:
  [2026-11-18-1.0-scope-triage.md](../records/2026-11-18-1.0-scope-triage.md).
- **2026-11-05 (this move).** CLI V1 complete, then platform; the roadmap moves to the CLI repo and
  the platform links to it. Develop correctly: central registries for cross-cutting concerns and
  correctly sized files and directories (ROADMAP section 4). Registry slices may build in parallel with
  REG-RENUMBER renumbering at merge. Engine releases every 2 to 3 days with a cumulative CLI repin.
  A Windows self-hosted runner on GCP is approved spend. Platform: Group 1 merges, the rest is
  parked.
- **2026-11-05 (X0a-h off the V1 path).** Platform H1, H2, H4 and H6 stay parked, and the engine
  and CLI ports (E1, E2, C1, C2) leave the CLI V1 path. Meanwhile the orchestrator flags any ratchet
  baseline growth by hand at each gate. Re-entry trigger: a hidden exception slips past review, or the
  platform restarts.
- **2026-11-05 (CLI 1.0 scope).** CLI 1.0 is everything on the CLI V1 track; no early 1.0 cut with
  later phases as 1.x.
- **2026-11-05 (detector role floor).** Developers can manage detector settings (custom detectors
  and overrides). The code already gates those routes at `developer`
  (`P:api/storm/detectors_router.py`, `storm.override`, `min_role="developer"`) and does not change.
  This supersedes the 2026-11-03 "STORM detector mutations stay admin-only" wording; docs that said
  admin-only are corrected. New V2 row: detection settings profiles ([post-1.0-plan.md](post-1.0-plan.md)).
- **2026-11-05 late night (OQ-1 to OQ-4).** OQ-1 = A1: X0a-h H1, H2, H4 are shared gate tooling on
  the finish-out list (now parked; see the X0a-h entry above). OQ-2 = B1: re-cut the STORM CLI half; CLI V1 ships the
  new names. OQ-3 = C1: SUB-STOP 1.6.0, STORM E1 1.7.0, then build order. OQ-4: Windows "would be
  ideal if possible" (WIN-FEAS). SAMPLE confirmed CLI V1. The starter YAML defaults columns with no PII
  to `redact`. LIB rows added before SCAN-MULTI; SCAN-MULTI S1d becomes LIB L2.
- **2026-11-05 night (scan and checks model).** Two kinds of integrity run through both scans: data
  integrity and distribution integrity ("2 different things but both incorporated in pre/post
  scans"). Standard: strict delivery; post-scan integrity on every route; output PK and FK checks
  when keys are declared; every validate check before a run. Opt-in: drift, distribution integrity,
  user rules and contracts (F35, F36), NER. Explicit config (CONFIG-EXPLICIT). `decoy scan` stores a
  versioned snapshot in a local library, referenced by the YAML and hashed into evidence.
- **2026-11-05 (CLI V1 scope).** SCAN-MULTI is CLI V1: "a decoy scan should be able to scan multiple
  files at once in order to build the single YAML for the pipeline." FK discovery parked for V2:
  "users can set up their own FKs, but we do want multi-file discovery at once. 1 scan for 1 pipeline
  build, on however many tables the user selects". CLI-CLOUD assumed CLI V1.
- **2026-11-05 (release order).** CLI V1 first, platform after (quotes in section 1). Supersedes the
  2026-10-22 "CLI-LAUNCH after V1" order and the 2026-11-04 sequence. UX map round 2: Q22 strict
  delivery and Q24 sample block CLI V1 for their CLI halves; OUT-PATH (Q23) is a platform row.
- **2026-11-05 (UX map section 8 adopted).** "Section 8, proposed roadmap changes, let's update our
  roadmap now." Workflows retired (X10b becomes WF-R). Stage then deliver, strict and best-effort.
  Sample output through the subset. "Studio" is the platform web UI, a prototype owned by a separate
  frontend developer. The CLI does not self-orchestrate; the platform applies per-job policy (form
  pending Q21).
- **2026-11-04.** Phase 0.5 cross-cutting foundations before the STORM wave; R1-c to the pre-release
  list; H-1 Wave B completes before Phase 1, after the STORM rename; GEN-API real-host rows after the
  STORM wave; reviews stay org-wide; the self-hosted CI runner may use the Mac; no OpenRouter gates.
- **2026-11-03.** B-5 job vault write: option A (#152's path-based persist kept behind a platform
  output handle); the `bounded_child.py` annotation not approved. Registry chain order F34 E0 1.3.0,
  F06 1.4.0, F31 E0c 1.5.0, then STORM E1, F35 E1a, F32 E1b, F36 slice 4. Merge B-5 without polish.
  V2 audit after V1 from the V2 log. Phases 1 to 3 are hardening. F06 after B-6 lifted. Role floors:
  users are developers; everyone except a viewer builds and runs pipelines including formulas. (The
  2026-11-03 "STORM detector mutations stay admin-only" wording is superseded by the 2026-11-05
  detector role floor.) Docs audit applied (platform #161, #162). The Mac mini is a test
  node; stacked PRs get one full suite on the stack top.
- **2026-11-02 night.** STORM Q8 refuse `variable.unknown_scope`; Q9 (a) keep the W0 forward shims;
  Q11 version A (E1 rides R-c). B-5 161 DEFER rows approved. F33 Q16 False; E1b waiver. F36-P planning
  after Phase 0. F32 re-cut accepted. Engine release order: F34 first. F31 CUT the alias, legend and
  run-UUID stack.
- **2026-11-02.** F31 O1 to O3 (see [row-detail.md](row-detail.md), F31). Stale STORM rename branches re-cut from main. B-6
  existing-vault compatibility is a hard cut; the CLI refuses to overwrite an existing vault. The
  dormant scheduler code is to be finished and activated, never deleted (still dormant). DuckDB opportunities added to V2.
- **2026-10-31.** Pre-release, no backwards compatibility; no migration for seed-keyed vaults; two
  engine releases (R-a, R-b); R1-c key generated offline by the owner; SBOM tool CycloneDX; CLI
  `claude/enterprise-hardening` parked.
- **2026-10-30.** V1 threat model: self-hosted, single org, engine process trusted; in scope are
  accidental leaks of values or paths into exceptions, logs, reprs, results and reports; hostile
  in-process hardening is V2. Slice 0 before F31. F25 before F22. F13 preflight stays in Phase 1.
  Secret retention in `KeyboardInterrupt(secret)` args is a V2 note.
- **2026-10-29.** STORM concept reframe. GEN-API 1f ships default OFF with per-deployment opt-in.

Full text of the 2026-10-30 to 2026-11-03 decisions: `OWNER-DECISIONS-2026-10-30.md` in the vault
handoffs folder (mirrored on platform `handoffs/queue`).
