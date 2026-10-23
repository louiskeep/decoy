# CLI check consolidation: `decoy validate` as the single pre-run gate (writeup)

Status: writeup / design, PRE-RELEASE (Cam 2026-10-23). Not build-ready: this settles the SHAPE; a full
build plan + the normal gate chain (Codex plan-gate -> build -> dennis -> Codex final) come before any code.
Scope: CLI surface only (no engine behavior change). Breaking CLI change, acceptable under the CLI's pre-GA
"hard delete" convention.

Rules consulted: 00-universal, development-loop, risk-and-exceptions, api-and-compatibility.

Do this alongside the broader PRE-RELEASE CLI CAPABILITY AUDIT (Cam 2026-10-23): before GA, survey every
built CLI capability, decide which to surface, how to surface it, and under what command/subcommand shape.
This validate/preflight/compile consolidation is one output of that audit; the delimiter + headerless-input
item (§FILE-FORMAT-CONTRACT) is another. The audit sets the whole command surface; this writeup is the
check-command slice of it.

## Problem
Pre-run checking is spread across three commands at two levels:
- `decoy preflight <cfg>` (top-level): local file / source / schema readiness + an advisory capacity estimate
  + a native-companion probe.
- `decoy compile <cfg> [--explain]` (top-level): compile the plan, run the five S1 plan-compile checks, and
  optionally explain the per-column strategy + table order.
- `decoy validate config <cfg>` (a subcommand of the `validate` Typer group): schema validation
  (`PipelineConfig.model_validate`) + the profile-free config-only checks (`run_config_only_checks`). The
  same group also holds `validate distribution <source> <output>`, a POST-run fidelity comparison.

A user who just wants to know "is my job OK to run?" has to know which of three commands to call, and the
depth relationship between them is invisible.

## Proposed surface
Consolidate the pre-run checks under the existing `validate` group, default to running the whole gate:

- `decoy validate <cfg>`            -> run the WHOLE pre-run gate (config + compile + preflight), one report.
- `decoy validate config <cfg>`     -> schema + config-only correctness (fast, no source read). (unchanged)
- `decoy validate compile <cfg>`    -> plan compilation + the S1 checks; `--explain` for the rationale.
- `decoy validate preflight <cfg>`  -> local file/source/schema readiness + capacity + native probe.
- `decoy validate distribution ...` -> UNCHANGED, and explicitly NOT part of the default (post-run only).

So: the default checks the entire job; the subcommands are opt-in when you only want one layer.

## Design decisions to get right (the non-obvious bits)
1. LAYER + DEDUPE, do not re-run. The checks overlap by depth: `config` ⊂ `preflight` (preflight already runs
   the schema + config-only checks as its steps 1-3), and `compile` runs the plan-compile checks. Structure
   the shared config-only validation as ONE layer that each path composes, so `decoy validate` runs it once,
   not three times. Target shape: config-layer -> compile-layer -> preflight-layer (source/capacity/native),
   each reusing the one below.
2. DISTRIBUTION STAYS OUT OF THE DEFAULT. `validate distribution` is a post-run comparison of a source vs an
   output file; it cannot run as part of a pre-run gate (no output exists yet). It remains an explicit,
   opt-in subcommand only.
3. ONE EXIT-CODE CONTRACT. Today the three carry distinct codes (EXIT_FINDINGS, EXIT_USAGE, EXIT_CAPACITY).
   The aggregated default needs a single rule: aggregate all findings, worst-severity wins; preserve the hard
   capacity refusal (fan-in impossibility) as its own non-zero exit; `--fail-on-warning` applies across the
   whole aggregate so an ADVISORY capacity warning does not fail the default run unless asked. Define the
   exact precedence (usage error > capacity refusal > findings > warnings) up front.
4. OUTPUT. The default emits one combined report (grouped by layer) and one combined `--json` envelope with a
   `messages` list carrying each finding's layer/severity/code/message/location (extend the existing
   multi-message JSON shape). `--explain` remains a `compile` concern; decide whether `decoy validate` surfaces
   the explain output or only the pass/fail (lean: pass/fail by default, explain only under the compile
   subcommand or an explicit flag).

## Migration (breaking, pre-GA hard delete)
- `decoy preflight` and `decoy compile` move UNDER `validate` and the old top-level commands are deleted (no
  shims, per the CLI's pre-GA convention). Update `__main__.py` wiring, the command epilogs, help text, the
  CLI reference docs, and any internal scripts / docs that invoke the old forms.
- `decoy validate config` is unchanged; `decoy validate` (no subcommand) changes from the pre-promotion
  behavior to "run all" - note this in the changelog as a behavior change.

## Acceptance (sketch; the build plan expands this)
- `decoy validate <cfg>` runs config + compile + preflight, reports one grouped result + one JSON envelope,
  and the shared config-only checks execute exactly once (no triple-run).
- Each subcommand runs exactly its layer with the same semantics it has today.
- Exit codes follow the single precedence; a hard capacity impossibility still exits the capacity code; an
  advisory capacity warning exits 0 unless `--fail-on-warning`.
- `validate distribution` is unaffected and is NOT invoked by the default.
- Removed top-level `preflight`/`compile` invocations fail with a clear "moved to `decoy validate ...`" usage
  error (or are simply gone, per the hard-delete decision - owner call).

## Owner decisions before build
- Does `decoy validate` default to running preflight's filesystem/capacity layer (heavier), or only the fast
  config+compile layers, with preflight opt-in? (Recommendation: run all, since "is my job OK to run" implies
  the source checks; keep config/compile as the fast-iteration subcommands.)
- Exit-code precedence (above) confirmed.
- Whether to keep a thin top-level alias for the deleted commands during a grace window, or hard-delete.

Pairs with the §FILE-FORMAT-CONTRACT pre-release item (user-set delimiter + headerless delimited input); both
are CLI-surface / file-format pre-release work and could share one build plan.
