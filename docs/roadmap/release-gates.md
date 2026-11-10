# V1 completion gates

Status: plan

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

**R1 = CLI V1** (engine, CLI and marketing web). The release work is rows 89 to 94.

- **D-4** Freeze a DP-certified launch engine (Faker 40.23.0) and the matched CLI pin. Version
  agreement done (R-a, R-b; static `version` with hatchling). Open: CLI `__version__` literal
  `"0.1.0"`; wide engine dependency floors (G12, F10). Branch `E:fix/faker-40-31-migration`
  (`e68b66c1`, replay by patch after R1).
- **B-3** Marketing-web currency: `docs-src/` off STORM branding and the old command surface;
  `CLAIMS-AUDIT.md` complete; `/proof` synced to the catalog.
- **D-5** Public Fumadocs launch-gate flip, aligned to FSL-1.1-ALv2 at launch.
- **GA-confidentiality freeze (audit packets 11 to 20):** 11.1 and the 12.1 residue land before the
  pre-GA to GA flip (rows 11, 13). 12.2 is closed on the full-frame path; chunked and native paths were
  read, not run. 20.1 is overstated ([findings-register.md](findings-register.md)).
- **R1-c** signing key and license review (owner and counsel); needed for the first signed
  release, not before. Engine, native companion and CLI are FSL-1.1-ALv2 (owner decision
  2026-11-10); counsel confirms the licensor entity (Decoy Labs LLC is a placeholder until
  the LLC is formed) and a contributor license agreement. Platform `LICENSE-COMMERCIAL.md`, decoy-web
  no LICENSE file.
- **R1 gate:** canonical CLI release smoke with recorded runs (G3: `smoke-log.md` had no green runs);
  a filled `release-readiness.md` instance; claims and license checkpoint; docs honesty; local gates
  and the worker-bootstrap gates (R1-d).
- Review item (not adopted): a threat model for the CLI installer and upgrade boundary and the local
  token vault.

**R2 = Platform V1** (parked).

- PREGA-AU automatic-update and recovery run.
- Section AUDIT at a frozen commit and a filled release-readiness instance green on the local gates;
  define AUDIT as a `dev-rules/pre-release-audit.md` instance with SAST, secret scan, dependency audit
  and tool versions recorded (G19, G21, not adopted).
- Dependency hygiene: python-jose replaced (#136); NOTICE and license gates (#137, engine #362); CLI
  root NOTICE (part of REL-PKG); `known-open-vulns.md` and `TRIAGE-001` (G18, not adopted).
- Security ledger at 0 gaps; closes packets 11 to 20 R2 findings 12.3, 11.8, 13.2, 13.7, 17.2, 17.3.
- Validation (not features): B-11 prodsim rebuild and the A-2 100M-row characterization (no 100M run;
  extrapolate from 1M and 10M).
- Market-positioning review against the shipped surface; Go or No-Go.
