# V1 feature checklist (29 Council-V1 features)

Status: plan

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

V1 = the 29 Council-V1 features (20 full, 9 reduced `V1*`) from the LLM Council scope doc (owner's
notes); contracts in the MASTER feature specification (owner's notes). Status is from the 2026-10-27
code audit; "merged" means a slice landed, not that the contract is met. Engine and CLI halves run in
the CLI V1 track; platform halves are parked.

| Fxx | Feature | Council | Status | Repos | Phase | Shipped groundwork |
|---|---|---|---|---|---|---|
| F01 | Connected DB copies and app-ready targets | V1 | PARTIAL | E+P | 3 | PG snapshot read |
| F02 | Cloud object storage and SFTP | V1* | PARTIAL | E+C+P | 3 | S3 and GCS |
| F04 | Referential subset and mask in one run | V1 | PARTIAL | E+C+P | 0 to 1 | engine subset; explicit keys (#366) |
| F06 | Declared parsing, casting, quarantine | V1 | PARTIAL | E | 1 | MERGED (#338) |
| F07 | Path-aware nested data | V1* | PARTIAL | E | 2 | nested masking strategy |
| F09 | Cross-job identity domains and vault | V1* | PARTIAL | E+C+P | 0 to 2 | B-6 stages 1 and 2; CLI vault (#64) |
| F10 | Version locks and fleet inventory | V1 | PARTIAL | E+C | 2 | fingerprints; `api/golden/` |
| F13 | Secret providers and preflight | V1 | PARTIAL | E+C+P | 1 to 2 | #339; CLI #78 |
| F14 | Platform wrapping-key rotation | V1 | PARTIAL(thin) | P | 2 | B-6 vault-key half |
| F15 | Continuous discovery and drift | V1 | PARTIAL | E+C+P | 2 | scan loop; schema contract |
| F16 | Reusable policy and selectors | V1 | PARTIAL(thin) | E+C+P | 2 | disguises |
| F21 | Studio parity | V1* | PARTIAL(near) | P | 1 | slices 1, 1b, 3a, 5 |
| F22 | Atomic and idempotent publication | V1 | PARTIAL(near) | E | 1 | atomic publish golden-tested |
| F23 | Recoverable execution and checkpoints | V1 | PARTIAL(near) (engine NEW) | E+C+P | 2 | platform leases and fencing |
| F24 | Capacity estimation and admission | V1* | PARTIAL | E+P | 0 to 2 | estimator (#328); B-10 S0 to S1b |
| F25 | Protected scratch and orphan recovery | V1 | PARTIAL | E | 1 | spill budget and memory caps |
| F26 | Upload, output, staging retention | V1* | PARTIAL | E+C+P | 1 | PRs parked |
| F29 | Machine-readable errors and progress | V1 | PARTIAL | E+C+P | 1 | #336; #367 |
| F30 | Customer-controlled telemetry | V1* | PARTIAL(thin) | E+C+P | 1 | CLI #80; #369; P1a #158 |
| F31 | Shared safe-output and redaction | V1 | PARTIAL | E+C+P | 1 | #368; #377 |
| F32 | Safe support bundles and reproduction | V1 | NEW | E+C+P | 1 | E1 in gate |
| F33 | Signed evidence and offline verify | V1 | PARTIAL(near) | E+C+P | 1 | evidence; `api/passport/` |
| F34 | Residual canary detection (span) | V1 | PARTIAL | E | 1 | #365, #370, #371 |
| F35 | User-defined quality contracts | V1 | PARTIAL | E+P | 1 | B-9 measurement |
| F36 | Cross-column invariants and fidelity | V1 | PARTIAL | E | 1 | `pk_uniqueness` |
| F43 | CI checks, annotations, hooks | V1* | PARTIAL (merged; remainder recorded) | C | 1 | CLI #69 |
| F44 | Signed distribution and upgrade | V1 | PARTIAL | E+C+P | 0 to 3 | B-2; SBOM (#355, #75) |
| F45 | Authorization and enterprise readiness | V1 | PARTIAL | E+P | 0 to 3 | A-4 (#361); B-5 (#157) |
| H-1 | Code organization (tandem) | V1 | NEW | E+C+P | 1 | Wave A; E0 stack; E5; E3 |

F04's remaining contract (no standalone unmasked subset artifact; platform materialization) rides
F22, F25 and SUB-RUN.

Legacy items: A-4 and B-5 become F45; A-5 is the STORM rename; A-7 and D2 merged; A-8, B-6 and B-1
become F09 and F14; B-2 becomes F44; B-9 becomes F35 and F36; B-10 becomes F24; route-coverage phase 2
is post-V1; GEN-API go-live merged (#153); B-11 and A-2 are R2 validation; B-12 scheduler is F27
(council V2), and the dormant scheduler code is to be finished and activated on the platform
restart (not done yet); D-1 to D-5 are shipped or R1 gates.
