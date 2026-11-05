# Owner decisions (dated)

Status: record

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

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
  admin-only are corrected. New V2 row: detection settings profiles ([out-of-scope.md](out-of-scope.md)).
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
