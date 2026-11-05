# Branch register (engine and CLI)

Status: current

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

Every open row names its branch. A remote branch neither merged nor named here has no owner on record
and is a cleanup candidate (`~/bin/branch-analysis`).

| Branch | What it holds | Disposition |
|---|---|---|
| engine PR #333 `claude/sharp-goodall-ikag71` | superseded A-4 draft | per-branch check, then delete |
| engine `feat/file-access-policy`, `feat/file-access-integrated-wip`, `feat/file-access-sink-coverage`, `claude/laughing-galileo-h18woa` | superseded A-4 work | cleanup candidates |
| engine `claude/youthful-ride-0azacx` (`e780df30`) | earlier copy of the native-release workflow | compare with #353, then retire |
| engine and platform `claude/v2-warehouse-sources-and-tokenization-vault` | warehouse connectors (home F01, F02) | FOLD; HIGH lost-work risk |
| engine `fix/faker-40-31-migration` (`e68b66c1`) | mimesis rebinding regression tests; no merge base | replay by patch after R1 (D-4) |
| engine `feat/b6-batch-vault-writer-engine` (`e3c539d6`) | B-6 batch vault writer | owner: fold into the B-6 core chain or retire |
| engine `feat/f13-e1-file-secret-permissions` (`37f43e47`) | shipped inside A-4 | retire |
| engine `plan/b6-vault-crypto-remediation` (`91488afb`) | B-6 crypto plan | retire after B-6 core merges |
| engine `plan/cdf-exact-arithmetic` (`f89f4ab7`) | built as #363 | retire |
| engine `plan/slice0` (`3a49b782`) | slice 0 plans | retire after slice 0 merges |
| engine `plan/route-coverage-ph2` (`864c2352`), `claude/optimistic-feynman-m5cfy5` (`2086fc73`), `claude/blissful-goldberg-mkwpdk` (`e1f96acb`) | route-coverage phase 2 (post-V1; Codex GO-WITH-FIXES with 5 HIGH) | keep; `blissful-goldberg` HIGH lost-work risk, do not delete |
| CLI `claude/eager-clarke-14deh1` (`d697c6d8`) | stale STORM rename | retire after the STORM CLI half |
| CLI `claude/storm-split-cli` (`a677d509`) | STORM CLI split | owner: compare with the re-cut CLI slices |
| CLI `claude/vibrant-feynman-1khw1v` (`8fa00fb2`) | CLI pre-scan and post-scan work | owner: compare with the re-cut CLI slices |
| CLI `feat/f26-local-cleanup`, PR #68 | F26 CLI half | parked until F22 |
| CLI `plan/f43-ci-integration` | F43 plan; built as #69 | retire |

Platform branches are in the platform pause record.
