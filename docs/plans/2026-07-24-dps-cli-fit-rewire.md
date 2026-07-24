# DPS-CLI: rewire `decoy fit` to the typed-carrier DP API

Status: PLAN v2 (Opus-authored, Codex-reviewed + revised 2026-07-24) — build-ready.
Owner item: cross-repo ROADMAP §DPS, loop item 2 (CLI half; platform scoped separately per Cam 2026-07-24).

## Context

DPS-CODEC merged to decoy-engine local main (`8cb630e`). It replaced the parked
Option-A `apply_dp_noise` with `fit_dp_snapshot`, and the DP artifact is now
`dps-marginal/v3` built over declared typed carriers (`number`/`flag`/`text`),
stability-1 by construction.

`decoy fit --epsilon` (`src/decoy/cli/fit.py:159-166`) still imports and calls
`from decoy_engine.quality.dp import apply_dp_noise` — a symbol that no longer
exists. **Against the merged engine the DP path is broken (ImportError on use).**
So this is a fix (restore a working DP fit) plus a feature (expose the new
typed-carrier + budget surface), pre-GA, breaking changes allowed.

### The new engine surface (the target)

```python
fit_dp_snapshot(
    source: pd.DataFrame | CarrierTable,
    column_schema: dict[str, dict],   # {col: {"kind": "numeric"|"categorical",
                                      #        "carrier": "number"|"flag"|"text",
                                      #        "bounds": [lo, hi]}}  (bounds numeric-only)
    *, epsilon: float, delta: float, numeric_bins: int = <default>,
) -> dict   # the dps-marginal/v3 artifact
```

Key differences from the old path:
- Takes the **source frame**, not a pre-computed snapshot (no
  `compute_distribution_snapshot` + noise two-step for the DP case).
- Requires a **per-column `column_schema`**: kind + carrier, and, for numeric,
  a **data-independent domain** `bounds` (declared, never read from the data —
  reading min/max from the data would itself leak).
- Requires **`delta`** alongside `epsilon` (approximate `(epsilon, delta)`-DP).
- **Only columns in `column_schema` are released.** Any other source column is
  omitted from the artifact (this is engine finding M1: fail-safe omission, not
  a silent wrong release — but the operator must be told).

## Goal

`decoy fit <source> --epsilon E --delta D <carrier declarations>` produces a
valid `dps-marginal/v3` artifact that `decoy run` can consume and generate from,
with the operator explicitly choosing which columns are released and how, clear
errors for the engine's fail-closed codes, and a loud, itemized notice of any
source column omitted from the DP release.

The **non-DP** path (`decoy fit` with no `--epsilon`) is unchanged: it still
writes a `distribution-snapshot/v1` via `compute_distribution_snapshot`.

## Design decisions

Each is marked **[RECOMMEND]** with alternatives. Codex plan-review
(2026-07-24) resolved the earlier open questions and required the fail-closed
corrections below; this section reflects the post-review design.

### D0 — DP mode is explicit and fail-closed (Codex REVISE)

The command has two modes: non-DP (`compute_distribution_snapshot`,
`distribution-snapshot/v1`) and DP (`fit_dp_snapshot`, `dps-marginal/v3`).
`--epsilon` is the ONLY selector of DP mode, and the two must never blur:

- Every DP-only option (`--delta`, any carrier declaration, `--numeric-bins`,
  the omission-control flags) is a **usage error when `--epsilon` is absent**.
  Without this, an operator who declares carriers + `--delta` but forgets
  `--epsilon` silently falls through to the exact non-DP snapshot — a fail-open
  release of exact data. Fail closed instead.
- `--epsilon` **requires** `--delta` AND at least one carrier declaration; an
  epsilon with nothing declared releases nothing and is a usage error.

### D1 — How the operator declares `column_schema` [CAM]

The engine's stance (and the repo memory "user picks PII type per field; never
propose pipelines") is explicit per-field choice, no silent auto-classification.
So the CLI must not guess carriers. Options:

- **[RECOMMEND] A: repeatable typed flags.**
  - `--dp-number COL:LO:HI` (repeatable) — numeric carrier + declared domain.
  - `--dp-flag COL` (repeatable) — boolean/flag carrier.
  - `--dp-text COL` (repeatable) — categorical text carrier.
  Explicit, scriptable, self-documenting, and forces the numeric domain to be
  declared (not inferred). Verbose for very wide frames, but DP releases are
  rarely wide, and a config file (below) covers that case.
- **B: a `--dp-schema FILE` JSON/YAML** mapping columns to `{carrier, bounds}`,
  mirroring the engine dict shape 1:1. Cleaner for many columns; add as a
  SECOND accepted input (A and B compose: file is the base, flags override).
- **C: infer kind from a profile + default carrier, flags only to override.**
  REJECTED as the primary mechanism: silent carrier defaulting is exactly the
  auto-classification the engine design forbids, and for numeric it cannot infer
  a data-independent domain without leaking.

Plan builds **A now**, leaves **B** as a fast follow (same parsed structure).
Rejecting C. **Duplicate or conflicting declarations for one column are a usage
error** (Codex) — never silently overwritten by flag order.

### D2 — `delta` handling [RECOMMEND]

Require `--delta` whenever `--epsilon` is given (no default): delta is a real
privacy parameter, and a silent default (e.g. 1e-5) would set a privacy level
the operator did not choose. Error clearly if `--epsilon` is present and
`--delta` is absent. `--numeric-bins` optional (engine default), surfaced as a
flag for parity with the engine knob.

### D3 — Undeclared columns / M1 seam (error by default, Codex)

`fit_dp_snapshot` releases only declared columns; the rest are omitted. The CLI
makes omission deliberate and fails closed by default:
- Compute `omitted = source.columns - declared.columns`.
- If `omitted` is non-empty, it is a **usage error by default** that lists every
  omitted column and tells the operator to declare them or pass `--dp-allow-omit`.
- `--dp-allow-omit` opts into proceeding, still printing the itemized omission
  notice (stderr + JSON result). Codex plan-review chose error-by-default over
  warn-and-proceed: silently dropping a column the operator expected to release
  is the foot-gun; make the omission an explicit, acknowledged choice. An omitted
  column is never released under a non-DP path by this command (D0 keeps the two
  modes disjoint), so the only failure mode is "expected a column, didn't get
  it," which the error prevents.

### D4 — `--joint` interaction

Unchanged from today: `--epsilon` + `--joint` remains a usage error (joint DP
needs composition accounting not in scope). Keep the existing guard.

### D5 — Error surfaces and exit codes (Codex)

Surface ALL FOUR engine exception families, `code` and `message` as separate
JSON fields (not one concatenated string):

- `DpError` — invalid fit parameters, invalid/reversed numeric domain
  (`dp_numeric_domain_invalid`). → `EXIT_USAGE`.
- `CarrierError` — schema/carrier/bounds failures. → `EXIT_USAGE`.
- `DpBudgetError` — unsupported or infeasible requested budget. → `EXIT_USAGE`.
- `ProvenanceError` — uncertified platform/stack (`dp_platform_uncertified`,
  `dp_stack_uncertified`). This is an EXPECTED fail-closed environment refusal,
  not malformed data: give it a dedicated human-readable hint ("this host is not
  a certified DP platform/stack"), not a bare code. → its own exit treatment.
- `dp_schedule_mismatch` is an internal-invariant failure, not user input →
  `EXIT_RUNTIME`, not `EXIT_USAGE`.

Generation-time verification (`_checks_dp.py`) failures surface later, through
`PlanCompileError` in `decoy run`, not here; the e2e test must prove that path
is engaged (the receipt is accepted before generation).

### D6 — CSV dtype and the flag carrier (data-independent, Codex REVISE)

CSV carries no dtype, so a `--dp-flag` column is read as strings by pandas, and
`decode_flag` rejects strings — so a raw CSV flag column would drop entirely to
null. The CLI must map it, but the mapping must be **total and data-independent**:
it may not error, warn, or count based on any cell's content, because that would
make a fit's success/failure a function of the data — the exact channel the
codec design (totality + boxing-invariance) exists to close. My first draft
(error on any cell outside the accept-set) was that bug; removed.

The build instead applies a fixed, case-insensitive grammar to a declared
`--dp-flag` column BEFORE the codec: `true`/`false`/`1`/`0` (with documented
whitespace trimming) map to `True`/`False`; **every other cell maps to null,
silently** — no error, no warning, no count. The flag codec then releases the
canonical `true`/`false`. `--dp-text` columns pass their genuine CSV lexemes
through unchanged (the text codec keeps real strings, nulls the rest, itself
total). `--dp-number` columns are read against the declared domain (the number
codec clamps/ nulls, total).

Datetime is handled at the **option** level, never by inspecting data: `--epsilon`
together with `--parse-dates` is a usage error (rejected before the CSV is read).
Without `--parse-dates`, a date-looking column declared `--dp-text` is ordinary
categorical text — valid. There is no data-driven "is this a datetime" check.

## Prerequisite — engine version floor (Codex)

decoy-engine is at `0.4.0`, and so was the OLD (pre-DPS-CODEC) engine: the CLI's
`decoy-engine>=0.4.0` floor would let a resolver install a 0.4.0 that lacks
`fit_dp_snapshot`. Before/alongside the CLI build:
1. Bump decoy-engine to **0.5.0** on local main (pyproject.toml `version` +
   `src/decoy_engine/__init__.py __version__`) — a minor bump for the
   DPS-CODEC feature and the `dps-marginal` v2→v3 artifact break. Commit on main.
2. Bump the CLI floor to `decoy-engine>=0.5.0` in `decoy-fix/pyproject.toml`.
3. Dev env installs the local 0.5.0 engine editable so the CLI resolves against
   the code containing `fit_dp_snapshot`.

## Backward compatibility

Pre-GA, breaking allowed. `decoy fit --epsilon E` WITHOUT the new required flags
(`--delta`, at least one carrier declaration) now errors with guidance instead
of running the old mechanism; every DP-only option without `--epsilon` errors
(D0). Update the command help/epilog and `decoy explain differential-privacy`.
No migration shim (pre-GA hard-delete rule, CLI CLAUDE.md).

## Test strategy

- **Land the assertion first**: `decoy fit --epsilon --delta <carriers>` produces
  a `dps-marginal/v3` artifact (not the removed path), and today's
  `--epsilon`-only invocation errors.
- **Mode selection is fail-closed** (Codex): a DP-only option without `--epsilon`
  (each of `--delta`, a carrier, `--numeric-bins`, an omit flag) errors and NEVER
  enters the non-DP branch; `--epsilon` with no carriers errors; `--epsilon` with
  `--parse-dates` errors BEFORE the CSV is read; `--epsilon`+`--joint` errors.
- **Declaration validation**: a bad `--dp-number COL:LO:HI` spec errors; a
  reversed/non-finite domain errors; duplicate/conflicting declarations for one
  column error (not last-wins).
- **Data-independence of the flag map** (Codex): unsupported flag tokens map to
  null with NO error/warning/count; and adding one row does not reinterpret prior
  flag/text cells (a boxing-invariance assertion at the CLI seam).
- **Omission**: omitted columns error by default listing them; `--dp-allow-omit`
  proceeds; an omitted column is absent from output and cannot be generated via
  any fallback.
- **Failure hygiene**: no artifact is created or overwritten when the fit fails;
  each of the four engine exception families (`DpError`/`CarrierError`/
  `ProvenanceError`/`DpBudgetError`) is surfaced with its code+message and the
  right exit class.
- **Artifact shape**: assert both the non-DP `distribution-snapshot/v1` and the
  DP `dp.schema == dps-marginal/v3`.
- **End-to-end** (the real proof), constrained per Codex: run on the certified
  proof stack (else `fit_dp_snapshot` rightly raises `dp_stack_uncertified`);
  declare `global_settings.dp` with a sufficient ceiling; avoid
  `allow_real_categories`/`high_cardinality`/`condition_on`; exercise
  `validate`/compile BEFORE `run` so the verification receipt is proven accepted;
  assert declared columns appear with correct dtypes (bool flag, numeric within
  domain, text categories) but NOT exact noisy counts (production noise is
  unseeded).
- Regenerate `docs/cli-reference.md` for `fit` (barry, at DOCUMENT).

## Build order

1. Engine 0.5.0 bump + CLI floor bump (prerequisite above); dev env on the local
   0.5.0 engine.
2. Land the failing assertion (broken import + new-contract test) — RED.
3. **Parse + validate ALL declarations BEFORE reading the CSV** (Codex): carrier
   flags → `column_schema`, domain finite/ordered, carrier valid, no duplicates,
   `--epsilon`/`--delta`/`--parse-dates`/`--joint` mode rules (D0). Declared-column
   handling is fixed before pandas ever infers a dtype.
4. Read CSV; build the typed frame (flag grammar map per D6, data-independent).
5. DP branch: `fit_dp_snapshot(df, column_schema, epsilon=, delta=, numeric_bins=)`;
   omitted-column check (D3); write the artifact only on success.
6. Error mapping (D5, four families + exit classes) + help/epilog + `explain
   differential-privacy` copy.
7. Tests green (unit + e2e), mypy/ruff, then dennis → Codex gate.

## Open questions — RESOLVED by Codex plan-review (2026-07-24)

1. **Typed flags now**, config-file as a fast follow; reject duplicate/conflicting
   declarations.
2. **Error by default** on omitted columns; require explicit `--dp-allow-omit`.
3. **Fixed case-insensitive `true/false/1/0`** grammar with documented whitespace
   handling; preserve genuine text lexemes; unsupported tokens → null silently; no
   explicit token-map feature yet.
4. **Hard-error** the old `--epsilon`-only invocation (no safe alias — neither
   `delta` nor the carrier/domain declarations can be inferred), and reject every
   DP-only option when `--epsilon` is absent.

## Platform (out of scope here, per Cam 2026-07-24)

decoy-platform has no engine/DP import in `src`; there is nothing to "wire" yet.
Deliver a separate short finding + options doc for platform DP integration (how
platform would reach `fit_dp_snapshot` — SDK call vs `decoy` subprocess vs job
worker) and let Cam scope it as its own item.
