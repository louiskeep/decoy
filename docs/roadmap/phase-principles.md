# Phase principles (the acceptance lens)

Status: current

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

The phases follow the MASTER delivery sequence. Read the phase pillars before an item's MASTER Fxx
contract at FRAME. If an item cannot meet its phase's pillars, that is a FRAME signal: the item is
mis-scoped, or the pillar needs a recorded exception.

**Phase 0, close the open branches (CLOSED 2026-11-04).** Finish, don't expand; respect the gate
chain; lockstep what is coupled; keep main bootable; every branch names its Fxx; security blockers
lead.

**Phase 1, trustworthy local run.** A local run is safe (no secret or canary leak on any surface),
honest (signed evidence, stable reason codes, nothing published on an inconclusive result), bounded
(every spool and temp file answers to a quota) and reproducible (atomic, idempotent publication).
Pillars: one sanitizing boundary, not per-surface patches (F31 first); validation never mutates and
evidence is frozen; bounded by default; machine-readable and versioned (one reason registry, stable
exit codes); fail closed on uncertainty; the engine owns the contract and the CLI and platform consume
it.

**Phase 2, portable and repeatable.** The same pipeline gives equivalent results across machines,
engine versions and time. Pillars: portable artifacts over implicit state; explicit drift, never a
silent change; immutable, versioned objects; no version flip without the determinism gate and the
synthetic probe; a reduced scope is a drawn line, not a weakened contract; resume with an unchanged
plan.

**Phase 3, connected safe-copy and enterprise readiness.** Pillars: depth before breadth (one complete
PostgreSQL round trip before more connectors); re-authorize at the point of execution; a connected
target keeps every Phase 1 guarantee; signed, attested distribution; recoverable upgrades; enterprise
breadth only when a customer pulls.
