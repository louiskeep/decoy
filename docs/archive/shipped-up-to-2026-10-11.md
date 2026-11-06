# Shipped log archive: up to 2026-10-11

Status: record

Older entries of [../RECENTLY-SHIPPED.md](../RECENTLY-SHIPPED.md), moved here unchanged on 2026-11-05 (entries dated 2026-10-11 and earlier). Index: [README.md](README.md).

### 2026-10-11 -- P6b: create_job_core split into named phases MERGED (platform PR #93)

Refactor track (P6 follow-up). Groundwork, not a feature.
- **What it did.** The job-creation entry point `create_job_core` was one ~450-line function running every pre-create step inline (pipeline resolve, idempotency, environment/role gating, stored-config size guard, YAML selection, mode, seed, preflight, per-run binding, admission sizing, persistence, audit). P6b extracts those into named phase helpers in a new `api/jobs/_create_phases.py`; the main service file drops 574 -> 291 lines.
- **Proven to change nothing.** Behavior-preserving: a 62-case observable baseline (the persisted job row, audit rows, HTTP status/detail, config snapshot hash, and whether caller inputs were mutated) was captured on the old code and reproduced exactly; the auth/permission gating order, the three stored-config guard points, idempotency, preflight severity handling, and the audit entry are all unchanged.
- **Gates.** Codex plan gate GO, build, independent anti-laundering check, dennis GO (0 blocker/high), Codex final GO. Platform GitHub CI is on the billing hold, so the local gate chain is the verification; the one remaining backend failure is the known pre-existing r6_3 audit-coverage blind spot (a retrieval route that authenticates in-handler), unrelated to this change and tracked separately.

### 2026-10-10 -- P6: platform job-runner refactored (run context + per-route executors) MERGED (platform PR #92)

Refactor track (before Phase D). Platform sibling of engine R3. Groundwork, not a feature.
- **What it did.** The platform's main job-runner function had grown a ~506-line, 28-branch body with route selection split across two code paths. P6 replaces that with a run-context object, one decision step, and four named route executors behind a small dispatch, so the next big step (adding Rust foreign-key routes in Phase D) adds a route by adding an executor instead of threading another branch. The main file shrank 580 -> 340 lines.
- **Proven to change nothing.** Behavior-preserving: before the refactor we captured a byte-level snapshot of the job runner's observable output (status, evidence manifest, per-node records, metrics) across 24 route/flag combinations plus 27 failure/cancellation/cleanup traces, and the refactored code reproduces them. The subtle platform-specific invariants were explicitly preserved: scheduler evidence stays gated on an authoritative plan, the error path still reads the corrected route and commit flags, and the exact try/finally boundaries are unchanged.
- **Gates.** Codex plan gate GO (4 rounds; it caught that the platform runner is trickier than the engine and the first plans oversimplified it), build, independent anti-laundering check, dennis GO (0 blocker/high/medium), Codex final GO (0 findings). Platform GitHub CI is on the billing hold, so the local gate chain is the verification; the ~36 devbox suite failures are confirmed environmental/pre-existing, not P6.
- **Next:** `create_job_core` phase extraction (P6b), then Phase D (Rust FK routes).

### 2026-10-10 -- R3: pipeline internals refactored so the Rust foreign-key work can land cleanly MERGED (engine PR #235)

Refactor track (before Phase D). Groundwork, not a feature.
- **What it did.** The engine's main pipeline function had grown a ~37-argument signature plus a workaround that forwarded its own local variables through a hidden hack, and its execution routes were shaped inconsistently. R3 replaces that with one clean run-context object, gives all three in-memory routes a uniform named entry point, and deletes the workaround. This is what the big foreign-key/Rust work (Phase D) was waiting on. The main pipeline file shrank from 684 to 306 lines.
- **Proven to change nothing.** Behavior-preserving: before the refactor we captured a byte-level snapshot of every route's output, errors, warnings, ordering, and telemetry on the current main, and the refactored code reproduces it exactly. Routing logic and the public pipeline signature are untouched.
- **Also banked.** A reconciliation record confirming the out-of-core reorder lane is the live, tested design (not a remnant of a reverted experiment), which Phase D needs before it removes any legacy foreign-key code paths.
- **Gates.** Codex plan gate (4 rounds; round 1 caught a real call-graph error in the plan before any code was written), build, independent anti-laundering check (only the pre-approved test changes landed), dennis GO (0 blocker/high/medium, 1 doc fix), Codex final GO (0 findings), ci-mirror clean, full engine CI green.
- **Next:** the platform half (P6) as a sibling slice.

### 2026-10-10 -- C6b-fakerfix: text masking's fake-value step is ~10x faster MERGED (engine PR #234)

Phase C. Follows C6b-i.
- **Same masked output, much faster fake-value generation.** When text masking replaces a detected name/address with a realistic fake, it was rebuilding the whole fake-value generator from scratch for every single match. It now reuses one generator (re-seeded per match), which is byte-for-byte identical output and about 10x faster on that step (912us -> 90us per fake-value span). On a realistic mixed note that roughly halves the per-cell cost.
- **Proven identical, not just faster.** The change was checked against the old behavior across ~6,800 cross-model parity probes with zero differences, plus a test that fails if the generator is ever rebuilt per match (so the speedup can't silently regress). Keying, which values are masked, and the no-raw-data-in-logs guarantee are all unchanged.
- **Why it mattered first.** Measuring text masking showed the slow part is the per-match work, not detection, and this fake-value rebuild was the single biggest chunk. The remaining heavy cost is the fake-value generation itself and the ML name-detector, which can't move off Python, so the planned Rust version is now a narrower decision (for ID-encryption-heavy columns only) that's back with Cam.
- **Gates.** Codex plan gate (3 rounds), build, dennis GO (2 minor; one test strengthened, one noted as a follow-up), Codex final GO, ci-mirror clean.

### 2026-10-10 -- C6b-i: text masking no longer drags its whole table onto the slow path MERGED (engine PR #233)

Phase C.
- **A text-masking column stops slowing down its neighbours.** "Text masking" scans free-text cells for PII (names, SSNs, emails, etc.) and masks each hit. Until now, a column using it forced its entire table, every other column included, onto the slower general-purpose path. It now runs on the fast path, so the rest of the table stays fast. Same masked output, byte-for-byte.
- **No shortcuts on correctness.** Text masking is key-driven and does a lot per cell (different hits can be encrypted, faked, date-shifted or redacted), so the fast-path version reuses the exact same masking engine rather than reimplementing it: identical values, warnings, and errors. The one case that needs the ML name-detector still uses the normal path.
- **Speed note.** This slice is about routing, not per-cell speed; a dedicated fast kernel for the per-cell work comes next (C6b-ii).
- **Gates.** The cross-model review caught two ordering mismatches on the chunked path: when two columns both failed, and the order warnings came out, didn't match the normal path. Both fixed at the source (process columns in the same canonical order the normal path uses), which also corrected the same latent quirk for the encryption feature.

Gates: Codex plan gate, Opus build, dennis GO (2 minor fixes), Codex final gate NO-GO on 2 ordering defects -> fixed -> dennis re-check GO -> Codex final GO, ci-mirror clean. One pre-existing, unrelated error-message-wording difference in the encryption feature noted for a later cleanup.

### 2026-10-10 -- C6a: format-preserving encryption runs on the fast Rust path MERGED (engine PR #232)

Phase C.
- **Faster, same output.** Format-preserving encryption (turns an ID or account number into a realistic, reversible fake one) now runs on the fast Rust path on both routes, byte-for-byte identical to the normal path. 1M rows encrypt in ~6s single-thread, ~1.8s on four.
- **No hand-rolled crypto.** Uses an audited FF1 crate, proven identical to our existing Python cipher across thousands of vectors (every alphabet size, the official NIST samples).
- **Stays correct by declining the hard cases.** Checksum modes (Luhn/NPI/IBAN/etc.) and a missing companion both fall back to the normal path, unchanged; a bad value fails the whole job with the same error it always did.
- **Gates.** The cross-model review caught two edge cases, both fixed: a validation-order mismatch on an unusual oversized-alphabet config, and a test that was checking the fallback's error rather than the fast path's. CI now runs the Rust crate-parity gate, the fast-path acceptance tests, and a guard against a version record silently drifting.

Gates: Codex plan gate, Opus build (foundation + route wiring), dennis BLOCK on CI-coverage gaps -> fixed -> dennis GO, Codex final gate (2 edge cases -> fixed -> GO), ci-mirror clean. One pre-existing, unrelated test-vs-pyarrow-version issue noted for later.

### 2026-10-09 -- C5c-ii: repeatable fake names/IDs over number columns run on the fast chunked path MERGED (engine PR #230)

Phase C. Follows C5c-i and C5c-a.
- **Faster, same output.** A "repeatable fake value" column (a stable fake name or ID keyed off a real number, boolean, or integer column) now runs natively on both fast paths, byte-for-byte identical to the standard path.
- **One empty-only edge made consistent.** When such a column comes out entirely empty or all-blank, its type is now recorded as text on every path (it used to vary by path). This is a small pre-GA output-type change for that empty-only case (Cam's option A), matching how the other fake-value and category columns already behave.
- **Stays correct by refusing the unsafe case.** If someone registers a fake-value provider under a known name but makes it return numbers instead of text, the fast chunked path now stops with a clear message instead of silently turning the numbers into text. This was a real bug the final cross-model review caught: without the guard, the fast path would have quietly changed those values. The standard (whole-table) path was already correct.

Gates: Codex plan gate (with a mid-plan remediation for the chunked path), Opus build (tests-first), dennis APPROVE, Codex final gate (found and we fixed the numbers-into-text bug), Codex re-gate GO, a focused dennis re-review of the fix, full engine test sweep green (18,349 passed), ci-mirror clean. Temporal and decimal fake-value sources remain not planned.

### 2026-10-09 -- C6c-ii: Rust text-redaction speedup MERGED (engine PR #229)

Phase C. Follows C6c-i. First the slow part was measured to confirm it was worth doing: redacting PII inside free-text columns (clinical notes) ran at ~32k rows/second, about 8x slower than the other masking types, so a large notes column was the bottleneck.

- **Faster, same output.** The detection for eight of the eleven built-in PII patterns (email, phone, card number, IBAN, IPv4, ICD-10, NPI, URL) plus their validators now run in a compiled Rust component instead of the per-row Python loop. On representative clinical text it is about 2.1x faster, and the redacted output is byte-for-byte identical to before.
- **Correct on every input, by routing not by luck.** The Rust path only runs on cells that are plain ASCII (which is the vast majority of real clinical text), where it provably matches the old behavior exactly. Any cell with unusual characters (non-ASCII digits, control separators) or the three boundary-sensitive patterns (SSN, ZIP, street address) falls back to the original Python path, so nothing is ever mis-redacted. No companion installed, or an out-of-date one, also falls back.
- **Memory stays bounded.** A first full-size (1M row) run showed the new path using too much peak memory because it processed the whole column at once; fixed by working in fixed batches, so memory no longer grows with column size. Re-measured within budget.

Gates: Codex plan gate (4 rounds, correctness validated with ~17k checks), Opus build (tests-first), dennis APPROVE (260k+ sample comparisons, zero differences), Codex final GO (another ~140k comparisons), a focused re-review of the memory fix, ci-mirror clean, and full engine CI green. One deferred non-reachable item: a numeric-offset widening that only matters for a single cell larger than 4 GiB (which cannot occur).

### 2026-10-08 -- C8-iii-d-2: filtered random-value columns run on the fast paths MERGED (engine PR #228)

Phase C. Follows C8-iii-d-1.
- **Fast paths for filtered random values.** "Only mask rows where..." filters on a column that draws random-but-stable values (a non-deterministic category picker, or a reused fake-value column) now run on both fast paths, not only the standard path. The output is byte-for-byte the same as the standard-path version from d-1, because the fast paths key each selected row on the same whole-table row number.
- **Two shapes still take the standard path.** A filtered date-window column (no fast-path version yet) and a filtered fake-value column drawn from a number column both still run on the standard path, same result.
- **Stays correct by refusing the unsafe case.** When a filter would need the fast path to compare against a non-text column, it declines with a clear reason rather than risk picking different rows per chunk. Columns with no filter are unchanged.

Gates: Codex plan gate (3 rounds), Opus build, dennis GO (two low notes folded: delete an unused fixture, tighten an equality check to exact byte identity), Codex final GO, ci-mirror PASS. Post-rebase: two test fixtures had assumed the wrong decline reason and were corrected (see #226 note); a stray packaging file and a duplicate lint entry from the rebase were removed.

### 2026-10-08 -- C8-iii-d-1: filtered random values stay put when the filter changes MERGED (engine PR #227)

Phase C.
- **Stable values under a filter.** When a filter is applied to a column that draws random-but-stable values (a non-deterministic category picker, a reused fake-value column, or a date-window column), each selected row now gets the value it would have had with no filter at all. Changing the filter, or adding rows elsewhere in the table, no longer reshuffles the values of rows that did not themselves change.
- **Scope.** This is a pre-GA output change for those three column types when they carry a filter (Cam's call). Columns with no filter are byte-identical to before, as are nested children and the order-sensitive strategies (shuffling, unique/match/scale fake values, joint masking). This slice covers the standard path; the fast-path version is d-2.

Gates: Codex plan gate (2 rounds), Opus build, dennis GO (two low doc notes folded), Codex final GO, ci-mirror PASS. A stray strace packaging file accidentally committed during the build was removed before merge.

### 2026-10-08 -- C8-iii-c: every filter now goes through the same safe grammar MERGED (engine PR #226)

Phase C.
- **One rule, every door.** The "only mask rows where..." filter language is a fixed, safe subset of expressions. That rule was already enforced when a job config loaded the normal way, but a few side doors (a raw config dictionary, a stored plan, a direct engine call) skipped it and ran the filter through general evaluation. Every door now enforces the same rule, with a clear error that names the column.
- **Errors no longer echo the filter.** A filter can contain real data values (for example `ssn == '123-45-6789'`). The error messages and stack traces now name only the column and masking type, never the filter text.
- **Scope.** Pre-GA behavior tightening; a filter outside the safe subset that used to slip through now fails up front with a migration table in the changelog for the old forms.

Gates: Codex plan gate (3 rounds), Opus build, dennis GO, Codex final GO, ci-mirror PASS. Post-rebase, two test fixtures that had been migrated to the new rule were asserting the wrong decline reason; both were corrected to the real reason (a stable numeric filter is now admitted to the fast path; a date-bucketing filter declines because of its settings, not its grammar), verified, and merged.

### 2026-10-07 -- C8-iii-b: filters that read number columns keep jobs on the fast path MERGED (engine PR #225)

Phase C.
- **More filters stay fast.** A large job whose filter compares against a number, date or long-text column now stays on the fast path (auto-chunking) instead of dropping to the slow whole-table path, as long as the engine can confirm the column has no empty cells. The filtered selection and every masked column match the whole-table run.
- **What still runs whole-table.** A filter that reads a number or true/false column that has empty cells, or has no empty-cell count recorded, or reads a more exotic column type, still runs whole-table. The masked target column must still be text.
- **Exact passthrough.** The columns a filter reads, when passed through, keep their exact original type and values, so these jobs now show the fast path's normal small differences from a whole-table run (a not-a-number value stays as-is; long-text and 64-bit-date columns keep their type).

Gates: Codex plan gate (4 rounds), Opus build, dennis GO, Codex final GO, ci-mirror PASS.

### 2026-10-07 -- Date-bucketing settings that destroyed dates now fail up front MERGED (engine PR #224)

Phase C. The "next fix" promised in the C8-iii-a note.
- **Fixed a silent data-destroyer.** A date-bucketing column whose format setting had no date in it (for example `ISO8601`, `mixed`, or a typo like `foo`) used to replace every date with the format text itself. The job reported success and the column held the same literal string in every row. It now stops before any masking or output, with a clear error that names the column and asks for a real pattern such as `%Y-%m-%d`.
- **Checked everywhere.** The check runs when the config compiles and in a config-only check, covers a nested date-bucketing child column, and is repeated in the handler and both large-job paths for configs that skip compile. The fast path declines the same settings.
- **Still accepted.** A format that has a real date in it still works and gives the same output; leaving the format unset still auto-detects.

Gates: Codex plan gate, Opus build, dennis GO, Codex final GO, ci-mirror PASS.

### 2026-10-07 -- C8-iii-a: filters for three more masking types on the fast paths MERGED (engine PR #223)

Phase C.
- **More filtered masking on the fast paths.** "Only mask rows where..." filters now run on both fast paths for text redaction, date bucketing and date shifting. At 1M rows with 10% selected, date bucketing went from 8.4 s to 0.4 s and date shifting from 1.2 s to 0.6 s. Text redaction gains nothing yet, because its detection is pure Python everywhere; the planned Rust version (C6c-ii) is the fix.
- **Date errors in the right place.** Dates that cannot be read are reported at the right row, and only for rows the filter picked.
- **Crash fixed.** Two loose date-format settings (`mixed`, `ISO8601`) made the fast path crash on dates with different time zones. Those jobs now run on the standard path.
- **Known issue found, next fix.** Those two settings write the format's name over every date, on every path, and always have. Cam chose to reject them with a clear error; that fix is being built.

Gates: Codex plan gate (3 rounds), Sonnet build, dennis (blocked a misleading release note, now fixed; code checks all matched), Codex final GO with no findings, ci-mirror PASS.

### 2026-10-07 -- Memory evidence for silent crashes (engine PR #222)

Follows the flaky out-of-memory test. In CI it showed a job dying with a segmentation fault and no message.
- **New:** while a memory-capped job runs, Decoy watches its memory use. A job that crashes with no message now carries a record of its memory at the time. A "likely memory pressure" flag is set when it died close to its cap.
- **Outcomes unchanged** (Cam's call: "evidence, not relabel"). A crash is still reported as a crash, so nothing gets wrongly retried. The evidence just makes it explainable.
- **Honest limit:** it is a strong hint, not proof. A job that asks for one large block of memory and is refused can still crash without the flag. Per-job kernel memory groups are the recorded upgrade path if this proves not enough.

Gates: Codex plan gate (3 rounds; it showed the first "relabel" idea could not be made reliable, which led to Cam's choice), Sonnet build, dennis GO (fixed how the age of a reading is measured), Codex final GO in round 2 (round 1 caught a reading being stamped too late), ci-mirror PASS.

### 2026-10-07 -- C5c-a deterministic fake values on whole-number columns with empty cells MERGED (engine PR #221)

- **Fixed.** Deterministic Faker on a whole-number column with empty cells used to fail the whole job. Pandas turned the numbers into decimals, and Faker refuses decimals. It now works (Cam's call). Each number gets the same fake value it would get in a column with no empty cells, including very large numbers.
- **Nothing else changes.** The fix hands Faker the original numbers directly, so the rest of the job sees the data exactly as before. 11 recorded baselines of jobs that already worked stay byte-identical.
- **Known limit.** A filter that masks only some rows of a number column with a text provider can still leave a mixed column, which fails on save. That was already true before this fix.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (2 medium fixes), Codex final GO in round 2 (round 1 caught a rare naming collision with nested Faker, now fixed), ci-mirror PASS.

### 2026-10-07 -- C5c-i random fake values on number and true/false columns MERGED (engine PR #220)

Phase C.
- **More columns on the fast path.** Random (non-deterministic) Faker now runs on the fast paths for whole numbers, decimals and true/false columns. Before, only text columns could. Output is identical to the reference path.
- **Empty cells decided the pandas way.** This Faker only needs to know which cells are empty. The fast path asks pandas, using the same conversion the reference path uses. That matters because pandas treats some "not a number" values as real values in some formats.
- **Text columns unchanged.** They keep their original fast check, so they lose no speed.
- **Still on the slow path:** dates, times, money-style decimals, nested data, and deterministic Faker on non-text columns (next slices).

Gates: Codex plan gate (3 rounds; it narrowed the slice after finding five problems in the first design), Sonnet build, dennis GO (1 medium fix), Codex final GO with no findings, ci-mirror PASS.

### 2026-10-07 -- Memory-capped jobs report out-of-memory correctly (engine PR #219)

Follows an intermittent CI failure where a capped job that ran out of memory was reported as "crashed".
- **Named correctly.** Memory failures in the steps after a job's main work, and in the worker's outer handler, are now reported as "ran out of memory", not "crashed".
- **No data in stored errors.** One Arrow memory error used to copy a raw data value into the stored error text. The value is now removed before storing, in both the isolated and the in-process path.
- **No leftovers.** A job that reports its own failure no longer leaves partially written output behind.
- **Not yet known.** The exact cause of the original CI failure is still unexplained. The test now prints the full error shape, so the next occurrence will tell us. A deeper fix (watching the job's memory directly) is held until that evidence exists.

Gates: Codex plan gate (3 rounds; it caught that a first idea would break jobs that work today), Sonnet build, dennis GO (2 medium fixes), Codex final GO, ci-mirror PASS. 40 of 40 soak runs classified correctly.

### 2026-10-07 -- FPE test stand-in fixed for empty cells (engine PR #218)

- **What it is.** The internal stand-in that the future Rust format-preserving-encryption kernel will be checked against. It used to try to encrypt empty cells and report an error. The real masking passes empty cells through unchanged, and now the stand-in does too.
- **Why it matters.** It had to be right before the Rust version is built, or that version would copy the mistake. Nothing users see changes.
- **Found along the way.** The stand-in also treats one kind of pandas missing value differently from the real masking. That is noted for the Rust FPE work (C6a).

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (540-case comparison), Codex final GO, ci-mirror PASS.

### 2026-10-07 -- C8-ii `when:` filters on the whole-table fast path MERGED (engine PR #217)

Phase C.
- **Whole-table fast path.** Single-table jobs whose "only mask rows where..." filters use hash, redact, truncate or deterministic categorical on text columns now run on the whole-table fast path. Before, they used the slow path. Output matches exactly, including column types.
- **Same filter meaning.** The filter is checked once, by the same pandas code the reference path uses, so the rows picked are identical. If a filter cannot be checked, the job goes to the reference path before anything runs, so it reports the same error.
- **Faster filtered masking on both fast paths.** Masking now runs only on the rows a filter picks, so a filter that picks few rows costs little. Before, every row was masked and the unpicked ones were thrown away.
- **Safety.** A filtered column can never be masked unfiltered, whatever its masking type.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (2 medium fixes: the low-selectivity cost and the unfiltered-run guard), Codex final GO in round 1 with no findings, ci-mirror PASS.

### 2026-10-06 -- Nightly ship-gate test fixed (engine PR #216)

- **What broke.** From Oct 6 the nightly ship-gate test failed on one job's recorded output fingerprint. C5b-i (#205) had changed random fake names and emails on purpose, and the recorded fingerprint was never updated.
- **Fix.** The fingerprint is re-recorded. Between the commits before and after #205, only those two columns differ, and repeated fresh runs give the same result.
- **Process.** A deliberate output change now updates the ship-gate fingerprint in the same slice, and each loop iteration checks the nightly run.

Gates: dennis GO, Codex final GO, ci-mirror PASS.

### 2026-10-06 -- C5b-iii position-keyed categorical and Faker on the whole-table fast path MERGED (engine PR #215)

Phase C.
- **Whole-table fast path.** The seeded random categorical and the random (non-deterministic, reuse) Faker now run on the whole-table fast path. Before, only the chunked fast path ran them, and a whole-table job fell back to the slow path.
- **Same output.** Output matches the reference path exactly, including tables processed in several batches and nulls at batch edges.
- **Stricter evidence check.** Only the random Faker may report "no kernel ran" on an empty table. Every other operator must still show its fast kernel ran.
- **Existing jobs unchanged.** Deterministic Faker, deterministic categorical and hash keep the same output and evidence.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis GO (2 small fixes), Codex final GO in round 1 with no findings, ci-mirror PASS.

### 2026-10-06 -- C8-i public `when:` and native `when` on the chunked route MERGED (engine PR #214)

Phase C.
- **Public `when:` field.** A column's `when:` filter ("only mask rows where...") is now part of the public config. It accepts a small, safe language checked when the config is loaded: column names, values, comparisons, `in` lists, `and`/`or`/`not`. Anything else, including function calls, is rejected with a clear error at the right place in the config. Cam chose this closed language. Older raw-dict callers keep the old behavior for now.
- **Fast path.** Tables with `when:` filters on hash, redact, truncate or deterministic categorical columns no longer fall back to the slow path on the chunked route. The rows to mask are picked by the same pandas code as before, so results match. Only the masking runs on the fast path.
- **Existing jobs unchanged.** Jobs that do not use `when:` keep exactly the same config fingerprint as before, which a test locks in.
- **Not yet covered:** the whole-table fast path, more operators, and numeric filters on auto-chunked tables (C8-ii and C8-iii).

Gates: Codex plan gate (4 rounds), Sonnet build with tests first, dennis (2 rounds; caught a fingerprint change for every job, now fixed), Codex final (3 rounds; caught filter spellings pandas cannot run, now rejected up front), ci-mirror PASS.

### 2026-10-06 -- Engine log-safety check MERGED (engine PR #213)

This is the automated half of the new "no data in logs" rule. A test now reads every engine log call and fails when new code logs a raw error message, a data value or an expression. It understands the usual ways of building a message and of naming a logger. The 10 existing sites are listed with reasons and exact counts, and four of them are on the Observability list to fix later. The list can only shrink. Gates: dennis GO, Codex final (three rounds, each finding narrower edge cases). Cam chose to merge after round 3's fixes.

### 2026-10-06 -- C5b-ii non-deterministic Faker on the chunked route MERGED (engine PR #212)

Phase C.
- **What changed:** a column using the default (non-deterministic) Faker setting used to push a large job onto the slow whole-table pandas path. It now runs on the chunked route.
  - String sources run on the fast path.
  - Other sources run chunked through the pandas leg without errors.
  - The values match a whole-table run exactly, including the per-table default naming and multi-table jobs.
- **Limits:**
  - Only providers known to return text run this way; others stay whole-table as before.
  - Columns with a `when:` filter are rejected on this route.
  - A custom provider registered under a built-in name that returns numbers now stops with a clear error instead of silently changing the column's type.
  - The whole-table fast path (unified route) is the next slice, C5b-iii.

Gates: Codex plan gate (4 rounds, the 4th approved by Cam), Sonnet build with tests first, dennis GO (one mutation thought harmless was not; a test now covers it), Codex final GO, ci-mirror PASS.

### 2026-10-06 -- Engine logs stop carrying expression text and data values (engine PR #211)

Cam asked for this after the logging review.
- **What it changed:** the engine's warning lines for `when:` filters and table transforms used to print the whole expression, so a filter like `email == 'bob@example.com'` ended up in server logs. They now say where the expression came from (column and strategy, or the transform step). The reviews turned up more sites, now fixed the same way:
  - the legacy date_shift path, which logged values it could not parse;
  - formula generation, which logged exception text per row that could quote cell values;
  - the distribution sampler, which logged snapshot bounds;
  - the disguise loader, which logged validation and YAML errors that echoed the input.
- **Unchanged:** outputs.
- **Going forward:** a dev-rules rule makes this a per-change check instead of a later sweep, and an automated engine check is next. The few remaining sites are listed in the roadmap's Observability section.

Gates: dennis (3 rounds), Codex final (3 rounds), ci-mirror PASS.

### 2026-10-06 -- C6c-i text_redact on both native routes MERGED (engine PR #210)

Phase C, first stage of C6c.
- **What changed:** a table with a text_redact (free-text PII redaction) column used to fall back to pandas in full. text_redact is now a native operator on both the unified and chunked routes, so the table's other columns (hash, Faker and the rest) run natively alongside it.
- **Speed:** the text_redact column itself runs the same Python span logic as before. It calls the oracle's own detection and splice code, so output matches by construction. Its own speed is unchanged.
- **Admitted configs:** no NER, a text token, a plain detector list, a text source, no `when:`. Every other config stays on pandas with a coded reason.
- **Output types:** on the chunked route an empty or all-null chunk is now `string`. Before, chunk types could mix within one column.
- **Next:** C6c-ii is a Rust span kernel. It needs a regex-engine decision first, because the detectors use lookarounds, and it will add a single-owner helper for the pass-through rules (a dennis follow-up).

Gates: Codex plan gate (3 rounds), Sonnet build with tests first (26/26 mutants killed), dennis GO (44-case differential fuzz equal on both routes), Codex final GO, ci-mirror PASS. Build record: decoy-engine `docs/records/2026-10-06-c6c-i-text-redact-arrow-build.md`.

### 2026-10-06 -- R1b shared kernel step MERGED (engine PR #209)

Fourth Refactor-track slice, no behavior change.
- **One step per operator:** each native masking operator now has one typed parameter object, resolved once per run, and one shared kernel step that both the unified full-frame route and the chunked route call. What differs between routes on purpose (evidence, companion errors, the date_shift error channel, where group_key reads its sibling, empty-output casts) stays in each route's adapter.
- **Defaults in one place:** the redact, truncate, bucket, date_shift, group_key and categorical defaults, which were written once per route, are resolved in one function. The chunked operator module shrank from 559 to 244 lines.
- **Why now:** position-keyed Faker (C5b-ii) becomes one parameter field and one step branch instead of two parallel dispatch branches.

Gates: Codex plan gate (3 rounds), Sonnet build with tests that pin today's behavior written first, dennis GO (one missing planned test added, three small fixes), Codex final GO with no findings, ci-mirror PASS. Build record: decoy-engine `docs/records/2026-10-06-r1b-merged-dispatch-build.md`.

### 2026-10-06 -- Engine main CI red-to-green (engine PR #208)

The CI regression gate had been red since 2026-10-05 on one stale speed test: it built a non-deterministic categorical without the namespace and row offset that C1b requires. Test-only fix; the 1-second budget still holds. Post-merge checks now include `tests/perf` and the latest main CI result.

### 2026-10-06 -- R1 operator registry MERGED (engine PR #207)

Third Refactor-track slice, no behavior change.
- **One descriptor per operator:** each of the nine native slice operators has one frozen `OperatorSpec` in a leaf module (stdlib and pyarrow only), holding its id, planned backend, kernel, resident types, assembly shape and Faker allowlist. Seventeen parallel tables across admission, evidence, physical bindings and the native route now derive from it, keeping their names, types and values (pinned by a literal snapshot taken before the refactor). Adding an operator is now one registry entry plus its kernel call.
- **Routed diagnostics are policy:** an explicit descriptor field, checked against what the capability reducers emit. The first plan derived it from the reducers, which made the admission check compare a table to itself; dennis caught it and the plan was corrected.
- **Smaller cleanups:** the three identical string-only chunked type gates are one function, with byte-identical reasons; the unused phase-3 eligibility predicate was removed; a guard test covers the forced-oracle stand-in.
- **Split out:** merging the two per-route dispatch chains (E2) is now its own slice, R1b, because the chains differ on purpose by route.

Gates: Codex plan gate (2 rounds), Sonnet build, dennis NO-GO (vacuous routed-diagnostics gate, a plan error) then GO, Codex final GO, ci-mirror PASS. Build record: decoy-engine `docs/records/2026-10-06-r1-operator-registry-build.md`.

### 2026-10-06 -- R0 engine cleanup MERGED (engine PR #206)

Second Refactor-track slice, no routing or output change.
- **Exception taxonomy:** 25 engine exception roots now inherit `DecoyError`, which claims to be the base for all engine errors. Stdlib ancestry is kept where callers rely on it, internal control-flow carriers are excluded, and a sentry fails on any new public engine exception outside the base.
- **date_shift oracle:** derives its keys in one batch per column and skips per-row lookups for usable cells. It is byte- and dtype-identical to before, checked across 384 independent comparisons including float16/float32 all-null columns.
- **CI:** every job has a timeout, the slowest tests are reported, and the ruff version is aligned across CI, the dev extra and pre-commit.
- **Docs:** stale claims were corrected (including CLAUDE.md's import-linter and removed `graph/` references).
- **Size policy:** the module-size policy names its dense-exception rule, and its growth history moved to a decisions doc.
- **Branch pruning:** merged branches and worktrees were pruned in both repos (14 engine, 17 platform), skipping anything unmerged, dirty, detached or parked.

Gates: Codex plan gate (3 rounds), Sonnet build (7/7 mutants), dennis NO-GO (a test that broke collection on CI's Python 3.10, plus a seam permit) then GO, Codex final GO, ci-mirror PASS. Build record: engine `docs/records/2026-10-06-r0-engine-cleanup-build.md`.

### 2026-10-06 -- C5b-i MERGED (engine PR #205): position-keyed non-deterministic Faker

Owner-approved semantics change for Faker's default mode (`deterministic: false`, `cardinality_mode: reuse`). One-time pre-GA output break: row `g` now takes `pool.values[derive_index(job_seed, selection_namespace, encode_int(g), pool_size)]`, so any chunk can be computed independently (the prerequisite for C5b-ii's fast paths).
- The selection namespace is the configured one, else a length-prefixed table/column default. That fixes a real bug: two namespace-less columns with the same provider used to come out identical row for row.
- Pools, deterministic Faker, the other cardinality modes, generation and composites are unchanged, and routing is unchanged.
- The docs claiming default-mode Faker was "unseeded" were wrong and are corrected.
- During review the pure-Python reference index kernel was made about 3x faster (HKDF key derived once per column, HMAC state copied per row), byte-identical, which speeds up every non-companion caller.

Gates: Codex plan gate (2 rounds), Sonnet build (88 new tests, 9/9 mutants), dennis NO-GO then GO, Codex final GO (0 findings), ci-mirror PASS. Build record: engine `docs/records/2026-10-05-c5b-i-positional-nondet-faker-build.md`.

### 2026-10-06 -- R0 platform cleanup MERGED (platform PR #91)

First Refactor-track slice: platform docs-accuracy fixes (route-evidence docstring, CODEMAP, user-facing engine-pin text, setup guide) and removal of unused `aiosqlite` / `passlib` and a stale requirements file. dennis GO, Codex GO.

### 2026-10-05 -- Unified-slice route evidence MERGED (engine PR #204)

The full-frame unified slice now reports, per column: the backend that was planned, the backend that actually ran, and how many batches it ran. It uses the same vocabulary and the same single executed-backend rule as the chunked route, and the two routes now share that rule. This brings the unified slice up to the program's route-evidence contract; it was C5a's section 3h, which Cam moved into its own slice at the review cap.

Elapsed time stays out of `quality_metrics`, as on the chunked route, so the evidence is deterministic. It is published in `ExecutionResult.timings`, and the lane checks there is exactly one timing record per admitted column.

Two truth fixes came with it:
- Full-frame bucket_perturb and date_shift used to claim the Rust kernel ran even on empty or all-null input; they now report it only when it actually ran.
- The compiled flag now accumulates across batches. group_key used to overwrite it each batch, so a later empty batch could hide real Rust work.

Evidence assembly is now a pure, unit-tested helper module. Output reconstruction moved there unchanged, settling a long-owed file split. Outputs, warnings and errors are unchanged.

Gates: Codex plan gate (r1 REVISE, r2 GO); Sonnet build tests-first (71 new tests, 12 mutants killed); a plan correction during build (keep elapsed out of `quality_metrics`); dennis GO; Codex final GO with zero findings; ci-mirror PASS. Build record: engine `docs/records/2026-10-05-unified-route-evidence-build.md`.

### 2026-10-05 -- C5a MERGED (engine PR #203): pooled Faker on the unified slice

First Faker slice of Phase C. Deterministic-REUSE pooled Faker (namespace + pool_size set, `person_first_name` / `person_last_name`, string source, no `when`/`vault`/FK) now runs on the full-frame unified slice instead of pandas, byte-and-type identical to the oracle. Research showed the shadow Faker binding and the shared selection helper were already built and dormant (Task 4.6 slice 1), so no new Rust: the slice switches them on. A provider builds each pool at most once per job: one job-scoped `PoolCache` (default 256 MiB budget) is shared by the lane and the oracle adapter, a non-string pool from a rebound provider reroutes on that single coded difference, and pool build failures re-raise the original exception with its cause chain intact. Two lane-wide fixes rode along: `native_threads` now reaches every compiled unified operator (before, they ran single-threaded regardless of the grant), and the unified coordinator visits nodes in the oracle's sorted `order_work` order for every operator, so error order, row-error order and stateful providers match the oracle (this also fixed a latent date_shift row-error ordering divergence). Gates: Codex plan gate 3 rounds (0 blockers), then Cam's scope call at the cap (lane-wide route evidence moved to its own follow-up slice) and a confirming review; Sonnet build tests-first (12 mutants killed); dennis NO-GO (node order, lost cause chain), remediated, then GO; Codex final GO with zero findings (first review on gpt-6-astra); ci-mirror clean-env PASS. Also on 2026-10-05: engine PR #202 fixed two unit-test spies that C3 left stale, which had turned main red. Build record under engine `docs/records/2026-10-05-c5a-unified-slice-faker-build.md`. Follow-ups: lane-wide route evidence (planned/executed backend, calls, elapsed per column); the owed `_unified_slice.py` post-run split; the lane's finalize row-error reroute (wasted work, mislabeled log; pre-existing). Phase C remaining: C5b (default non-deterministic Faker), C5c (non-string Faker sources), C6a/b/c (FPE/text_mask/text_redact), C8 (when-predicates), C9 (platform admission).

### 2026-10-05 -- C3 MERGED (engine PR #201): chunked dispatcher for group_key

Sixth Phase C operator, and the last strategy on the chunked-route veto list (the veto set is now empty). Research showed `group_key` is value-keyed with no cross-chunk state, so it needed the same native chunked-leg admission as C2/C4 rather than new sibling-state machinery. No new Rust: the chunked leg reuses the existing raw-hex kernel. Value-keying only holds inside the collision-free {string, int64, bool} sibling domain (the operator caches on the raw value but derives on `str(value)`, so float/decimal forms like 0.0 and -0.0 would be order-dependent); float/decimal siblings stay rejected and wider types reroute to the oracle leg instead of failing closed. The sibling is read from the RAW pre-cast chunk so a null sibling derives `"None"` exactly like the oracle. Order-dependence declines cover a masked sibling, a self-anchored column and a missing sibling. The kernel now resolves before the empty-frame short-circuit, `NativePreflight` threads it, and all four loader-failure modes report `raw_hex_extension_unavailable`. The string schema pin keys on the sibling's first-chunk type at both schema sites. One change outside the gated plan: `compile_native_plan` gained an optional `resident_sources` argument because the profile typed an int64-with-nulls sibling as double and rejected it before the real-type gate; it reuses the full-frame resident-Arrow mechanism, defaults to unchanged behavior, and both dennis and Codex approved it (int64-with-nulls verified native == oracle). Test fixtures that forced the oracle leg through group_key were migrated at the single shared helper to a deterministic numeric categorical. Gates: plan gate 4 rounds (Codex x3, then Fable as the sanctioned substitute while Codex was at capacity), Cam authorized the build, Sonnet build (10,255 passed companion-present, 22 mutants killed), dennis GO, Codex final GO, ci-mirror companion-absent clean-env PASS. Post-merge main verified green (5,282 native/group_key/categorical tests). Build record under engine `docs/records/2026-10-05-c3-chunked-group-key-build.md`. Carry-forward LOWs: a mistyped+masked-sibling regression test, a defense-in-depth comment, and consolidating duplicated order/pin logic. Phase C remaining: C5a/b/c (Faker), C6a/b/c (FPE/text_mask/text_redact), C8 (when-predicates), C9 (platform admission).

### 2026-10-05 -- C4 MERGED (engine PR #200): chunked dispatcher for date_shift

Fifth Phase C operator. Native-admissible `date_shift` (string source, explicit `date_format`, no `group_by`, namespace, no timezone directive, in-range bounds) now runs natively per chunk via the existing compiled index kernel, byte-and-type-identical to the pandas-oracle chunked route; its table no longer forces the oracle. No new Rust (the `native_date_shift` kernel already existed on the full-frame route). Output type is string-pinned on both chunked legs at both schema-rule construction sites (dispatcher + streamed sink), companion-independent, matching C1's categorical pattern (date_shift is tokenizing, not null-on-empty); two accepted route-dependent diffs recorded (empty `double` to `string`, all-null `null` to `string`). The date_shift-specific piece is the format_error row-error obligation: a new `native/_chunked_row_errors.py` module collects the kernel's per-chunk unparseable-date positions, keeps them CHUNK-LOCAL (matching the oracle leg, which does not add the row offset), attributes table+column, emits them in the oracle work-list order, appends the failing chunk's result to the sink before raising `RowErrorsFailedError`, and stops at the first failing chunk, before any offset advance, vault write or yield. Evidence is honest: `kernel_calls` stays the branch-execution counter (C2 contract), and truthful compiled work rides an optional `derive_calls` spy (the kernel's 2-tuple return is unchanged, so the full-frame consumer is untouched); zero-row, all-null and all-unparseable chunks run no kernel and report `arrow_python`. Non-string source routes to the oracle leg (not fail-closed, the C1b-ii regression lesson). Gates: Codex plan-gate (3 rounds, design GO; the recurring forced-oracle fixture-inventory finding was fixed at the root by migrating the single shared `force_oracle` helper to a group_key self-anchor rather than hand-listing sites), Cam authorized the build, dennis APPROVE (0 blocker/0 high, all three builder judgment calls ruled sound), Codex final GO after two added tests (a mask-key differential KAT and a large_string fail-closed regression). 258 targeted tests; changed-unit coverage (new row-errors module 100%); 16 hand-mutants, 0 survivors (including the add-row_offset mutant and a wrong-mask-key mutant); ruff/mypy clean; ci-mirror companion-absent clean-env PASS. Build record under engine `docs/records/2026-10-05-c4-chunked-date-shift-build.md`. Branched off main-with-C1b-ii (`9bf5f393`); merged on local gates while Actions is out of minutes. Phase C remaining (as of C4): C3 (group_key), C5a/b/c (Faker), C6a/b/c (FPE/text_mask/text_redact), C8 (when-predicates), C9 (platform admission).

### 2026-10-05 -- C1b-ii stale-test reconcile MERGED (engine PR #199)

A one-test follow-up to C1b-ii. C1b-ii intentionally admitted seeded non-deterministic string categorical to the native chunked route, but `test_chunked_route_declines_non_admissible_categorical[non_deterministic]` still asserted it declines, which left main red (caught by the C4 dennis + Codex gates as a pre-existing, out-of-scope failure). Fix: move the non-deterministic case to the admits test (parametrized over `deterministic`), keep only `numeric_categories` in the declines test. Test-only, no production change; landed before C4 so main returned to all-green first.

### 2026-10-04 -- C1b-ii MERGED (engine PR #198): non-deterministic categorical on the native chunked fast path

Completes the categorical story (with C1b-i). Seeded non-deterministic `categorical` now runs the native CHUNKED route: a STRING source runs the compiled kernel keyed by the per-chunk uint64 global row offset (`derive_index_batch`, byte-parity with the oracle, no new Rust); a NON-STRING source routes to the existing chunked-ORACLE leg (reproducible, the same path deterministic categorical uses). Two-stage admission (config-only verdict shared by the compat veto + static route decision + evidence + preparation; source-dtype picks native-vs-oracle LEG). Scope deliberately bounded to the chunked route: full-frame physical stays closed, multi-table split + out-of-core stay vetoed (deferred to C1b-iii/C1b-iv, each needs new global-offset plumbing), `when:` rejected, null-first governed by the pre-existing `chunked_leading_null_type` gate. NOTABLE: the first build fail-closed on non-string sources, which REGRESSED auto-chunked jobs that previously ran full-frame (a valid int64/float64-source random categorical crashed); the dennis build-gate caught it empirically (before/after), the decision was corrected to the oracle-leg reroute, and an auto-router end-to-end regression test was added (the coverage gap that hid it). The clean-env `ci-mirror` then caught a companion-only test assertion that would have gone red in CI (fixed with `@NEEDS_COMPANION`) -- the per-slice clean-env check earning its keep. Gates: Codex plan-gate (3 rounds) + reversal re-gate (2 rounds), Sonnet build + remediation, dennis GO (re-gate), Codex final GO, ci-mirror PASS. ~2.5k targeted tests green; 100% line/branch on the new module; hand-mutation 0 survivors. Branched off main-with-C1b-i (`d93e3bde`). Merged on local gates while Actions is out of minutes. Remaining categorical follow-ups: C1b-iii (multi-table split) + C1b-iv (out-of-core).

### 2026-10-04 -- C1b-i MERGED (engine PR #197): non-deterministic categorical is now reproducible + reclassified seeded

Split from C1b (the plan-gate showed the full change was cross-cutting). C1b-i makes non-deterministic `categorical` REPRODUCIBLE: it now seeds the draw and keys it by the handler-frame ordinal via `derive_index` + the public `encode_int` + the shared CDF (the same position-keyed pattern windowed_date/DGRN already use; no new primitive). The old unseeded `default_rng` path is gone. The operator is reclassified truthfully as seeded across the engine's determinism machinery (determinism protocol, draw-site providers, capabilities, both draw-site-inventory summaries with a structural count gate), nested, multi-table sentries, and out-of-core compat. Crucially, it HOLDS EVERY ROUTING OUTCOME CONSTANT: the "reproducible vs random" label doubles as a live route gate (multi-table split, out-of-core, native, chunked), so C1b-i swaps the now-false "unseeded" label for honest "positional-deferred" vetoes, keeping the exact set of jobs on the exact routes they ran before. The chunked/native fast-path admission is the follow-up slice C1b-ii (which removes those temporary vetoes). Owner-flagged pre-release break: non-deterministic categorical now requires a `namespace` (reproducibility needs a key), consistent with deterministic mode; documented in CHANGELOG + compatibility-contract + strategies.md. Gates: Codex plan-gate GO (5 rounds, 8->4->2->2->0 findings), Sonnet tests-first build (red-before), dennis GO (0 blocking, 2 informational LOW), Codex final GO, ci-mirror clean-env PASS (the new per-slice clean-env check, which also caught a self-consistency prose violation in an interim changelog edit). 22k+ tests green across execution/native/physical/parity/sentry. Branched off main-with-C2 (`c4ea0f37`). Merged on local gates while Actions is out of minutes.

### 2026-10-04 -- C2 MERGED (engine PR #195): chunked dispatcher for bucket_perturb

Second Phase C operator. Native-admissible `bucket_perturb` (string source, explicit `date_format`, no timezone directive, valid bucket week/month/quarter, namespace) now runs natively per chunk via the existing compiled index kernel, byte-and-type-identical to the pandas-oracle chunked route; its table no longer forces the oracle. Output type is content-dependent (NOT string-pinned like C1): empty/all-null chunk -> Arrow `null`, valued -> `string`, reassembled -> `string`, matching the oracle leg; a post-kernel reconciliation makes the native branch emit `null` on degenerate chunks. Evidence is honest: `compiled_kernel_executed` and per-column `executed_backend` reflect ACTUAL per-chunk kernel execution (a degenerate chunk runs no `derive_index_batch`, so it reports `arrow_python`, not `rust_companion`), with identical merge logic across the resident and streamed/sink aggregation paths. `large_string` source is a native-decline/oracle case (profile resolution collapses width); a drifted later null-typed chunk now raises the same code on both legs (parity-gap fix). Non-admissible cases keep their exact existing codes. Gates: Codex plan-gate GO (5 rounds, 12->4->3->2->0 findings), dennis GO (2 non-blocking LOWs), Codex final GO (after 3 NO-GO rounds on a test-proof class: every forced-oracle leg now proves it ran the oracle via a self-asserting `run_pair` + column-qualified reasons across all 14 `force_oracle` sites). Full native suite 4343 passed / 1 skipped. Engine-internal; platform keeps its 0.8.0rc1 pin and picks C2 up at a later pin advance. Branched off main-with-C1 (`a2b97856`). Merged on local gates while Actions is out of minutes. Follow-up noted: the full-frame route (`_shadow_operators.py:257`) has the same unconditional `compiled_kernel_executed` evidence gap C2 fixed on the chunked route (pre-GA fix).

### 2026-10-04 -- C1 MERGED (engine PR #194): chunked dispatcher for deterministic categorical

First Phase C operator. Native-admissible deterministic `categorical` (deterministic/allow_collisions + namespace + all-string categories + buildable CDF + string source) now runs natively per chunk via the compiled index kernel, byte-identical to the pandas oracle across chunk shapes, sizes, thread counts, uniform + weighted; its table no longer forces the oracle. Non-admissible categorical (numeric categories, large_string/dictionary/empty-int64 source) stays on the oracle with its exact type, not string-cast. Non-deterministic fails chunked preflight with `categorical_nondeterministic_not_chunk_safe`. Output type pinned to `string` on both chunked legs (conditional on admissibility; route-dependent vs full-frame, recorded under ROUTE-OUTPUT-CONTRACT). Gates: Codex plan-gate GO (3 rounds), dennis GO, Codex final GO; mutation 48->0; 136 new tests. Engine-internal; platform keeps its 0.8.0rc1 pin and picks C1 up at a later pin advance. Build on feat/c1-chunked-categorical was rebased onto main-with-B6b (zero src overlap) + composition verified (12461 passed) before merge. Merged on local gates while Actions is out of minutes.

### 2026-10-04 -- B3 MERGED (platform PR #90): platform Phase 1 on the chunked dispatcher

Branch `feat/b3-platform-dispatcher` (plan `docs/plans/archive/2026-10-02-b3-platform-dispatcher.md` rev 3a, build record `docs/records/2026-10-03-b3-platform-dispatcher-build.md`). dennis GO + Codex final GO. Merges on local gates once the engine tag is pushed (GitHub Actions is out of minutes this month). The engine artifact `v0.8.0rc1` (commit `37694fcb`, engine main `02dc2827` plus a version-only commit) is built locally; the tag/branch push to the engine repo is the final step before merge.

- Phase 1 jobs mask each table on `run_mask_chunked` with the persisted thread budget, a bounded result sink and per-table evidence; full-frame jobs pass the same threads and let the engine auto-chunk and split. The worker's thread check compares the real request with the grant. Engine error codes reach the job (`native_chunk_schema_drift` and the rest) with the table and chunk as the location. Each mask node carries its own route, reasons, threads and per-column backend and time; `GET /api/jobs/{id}` returns an `execution` summary. `NATIVE_DISPATCHER_ENABLED=false` is the rollback lever. The engine fence is exactly `==0.8.0rc1`.
- Measured through the real job path on the devbox: speed p50 ratio 0.12 to 0.49 against the pandas route (bars 0.5 and 1.0), every `VmHWM` at least 168 MiB under its priced reservation, t=1 and t=4 outputs equal. One bar missed: the 10M-minus-1M `VmHWM` delta, 70.0 MiB at 1 thread and 75.9 at 4 (bar 64). A bare `run_mask_chunked` loop with no platform evidence code shows the same 70 MiB, so it comes from the engine's direct reader/writer path, not from B3's evidence handling. A re-pin to include B6a/B6b was considered and abandoned (Codex: those slices activate only on the `run_pipeline` path, not B3's `run_mask_chunked` path). Owner accepted the miss as a pre-GA deferral (no users; absolute bar passes with 168 MiB margin; real fix deferred to the Phase E 100M milestone). No bar loosened in code; mutation 50/50 killed.
- Pre-existing defect (not B3): a failed Phase 1 job's evidence manifest already fails its own schema (`job.table_publications` is added after the hash and is not in the strict model), on unmodified main too. T6/T7's "manifest validates" sub-assertions are kept as `xfail(strict=True)` and tracked as a follow-up (schema extension + re-hash before GA); the core T6/T7 assertions pass.

### 2026-10-03 -- B5 and B6b merged (native admission pricing + lazy batch input)

Both landed on local gates (dennis GO + Codex GO + full local suites) while GitHub Actions is out of minutes for the month. Cam's call: merge each gated slice to main on the local gates, build out through Phase F, and stand up a self-hosted runner later to do a clean-env validation sweep before relying on the result.

- **B5 native admission pricing (platform PR #89).** A streaming job's memory reservation is priced from its source (process floor + thread allowance + footer/CSV-cap decoder bound + one chunk's working set), the reader enforces that byte budget, and every claim stamps `Job.native_budget`. Gates: dennis GO, Codex GO. The golden-comparison test was made robust to a pyarrow `attributes`-field version drift (CI resolves pyarrow 21 under the platform's `<22` pin; the golden was baked under local 24); the h3 wall-clock concurrency failure was confirmed a CI-runner-load flake (passes 3/3 locally, deterministic twin passes). Engine pin left unchanged (B3 advances it).
- **B6b lazy batch input (engine PR #193).** Streams a local Parquet source into the auto-chunk lane via `LazySource` instead of materializing the whole table; input memory is flat in rows (~470 MiB at 2M/10M/50M), output byte-identical to the resident twin. Built on B6a (in main) and the B1 dispatcher contract. Gates: dennis GO, Codex GO (after remediating one mem-cap-test BLOCKER: the paired OOM test was recalibrated to 4M rows / 1536 MiB so it discriminates on both the native and companion-absent substrates). All 19 hand-mutants killed; benchmark B6B-BENCH-2026-10-03 all 20 bars pass. Build record `docs/records/2026-10-03-b6b-lazy-batch-input-build.md` (in decoy-engine).

### 2026-10-02 -- B5 native admission pricing built (platform, not yet merged)

Branch `feat/b5-native-pricing` (plan `docs/plans/archive/2026-10-02-b5-native-admission-pricing.md` rev 3.1; build
record `docs/records/2026-10-02-b5-native-pricing-build.md`). Merges only with Cam's go after dennis and Codex final.

- A streaming job's memory reservation is computed from its source (a fixed process floor, a thread-pool
  allowance, a decoder bound taken from the Parquet footer or the CSV record cap, and one chunk's working
  set) instead of the constant 384 MiB, and the reader now enforces the byte budget it was priced with
  (Parquet by row group, dictionary-first and owned-buffer chunks; CSV through a quote-aware record framer
  that rejects an oversized record before PyArrow sees it).
- Every claim records an admitted budget on `Job.native_budget` (route, thread grant, reservation, per-table
  limits and source identity). Threads are granted from a cgroup-aware core count: a fair share inline, one
  thread for an external worker, and flag on the scheduler offers each route at 1, 2, 4 threads.
- Cloud sources are priced from bounded range reads pinned to one object version, and staged from that
  same version. Four operator settings (`NATIVE_THREADS_MAX`, `NATIVE_CHUNK_BUDGET_MAX_MB`, `MAX_ROW_BYTES`,
  `NATIVE_METADATA_MAX_BYTES`) tune it; see `docs/plans/deployment-sizing-and-concurrency.md`.
- Migration `b5_native_budget` adds the nullable `jobs.native_budget` column.

### 2026-10-01 -- Rust engine program Phase A merged (engine + platform)

Engine PRs merged:

- **Engine PR #181 (A7):** the D9/GP1 peak-memory ratio gates are replaced by an absolute peak-RSS ceiling (`--max-peak-rss-mb`).
- **Engine PR #182 (A6):** the unified slice (Rust lane) returns real per-column timings and `boundary_conversion_ms`.
- **Engine PR #183 (A5a):** `read_fixed_width` and `FixedWidthParseError` are public.
- **Engine PR #184 (docs):** the Rust engine program plan, the coverage and evidence audit records, the D9 v2 recertification (green on the GCP reference host) and the file-format contract write-up.
- **Engine PR #185 (A8):** `run_pipeline` owns per-table transforms; public `apply_table_transforms`. Version stays 0.6.0 until the 0.7.0 release.
- **Engine PR #186 (B1):** public `run_mask_chunked`, the compiled chunked dispatcher as a production entry point with a per-table pandas fallback; passthrough columns are carried exactly in Arrow; Faker pool cache identity includes the provider binding (fixes a stale-pool bug on reused caches).

- **Engine PR #187 (release 0.7.0):** version 0.7.0 on engine main (installed from git, not PyPI); both DP certified-stack fingerprints re-pinned for the version string only.

Decoy CLI PR merged:

- **CLI PR #54 (A5b):** sources read by declared format (csv, parquet, fixed_width) in run, demo and `decoy.mask()`; CSV and fixed-width admitted by the native gate; requires engine 0.7.0; certified profile re-pinned; `--substrate` accepts only `pandas`.

Platform PRs merged:

- **Platform PR #74:** uploaded fixed-width files keep the recipe's format and layout.
- **Platform PR #72 (S11b):** disk-quota admission wired into the job claim.
- **Platform PR #76:** `engine-bench.sh --battery unified-cert` (D9 certification on GCP).
- **Platform PR #75 (A1+A2):** upload bindings are owner-scoped; cloud descriptors leave the executable job snapshot; the claim path is one locked candidate per transaction.
- **Platform PR #77 (A8p-0):** the platform is fenced below engine 0.7 until it stops applying transforms itself (A8p).
- **Platform PR #78 (A3+A4):** FK cycles route full-frame; fixed-width skips Phase 1 streaming.

### 2026-09-26 to 2026-09-30 -- Scheduler S10/S11 + P12 merged; MinIO CI; prod-image cloud extra

Platform PRs merged today (2026-09-30):

- **Platform PR #71 (ci/s4-minio-from-source):** the `s4-real-backends` CI job (real S3/GCS contract tests) builds MinIO from its open-source release tag, because MinIO withdrew its community images and binaries. The job had been red on every PR since 2026-09-21.
- **Platform PR #69 (feat/scheduler-s10-s11-tmpdir-localstage):** S10 (worker TMPDIR pin) and S11 (full-frame LOCAL_STAGE quota root), merged behind the scheduler feature flag. Its new `real-fs-quota` CI job proves the project quota trips on a real ext4 mount. S11b (disk-quota admission in the claim) remains open as platform #72.
- **Platform PR #70 (fix/p12-fallback-ladder-pricing):** enforces the fallback-ladder pricing invariants in host-lease admission and the priced claim.
- **Platform PR #73 (fix/prod-image-cloud-extra):** the prod image and dev compose request `decoy-engine[cloud]`. The engine side, moving boto3 and google-cloud-storage into the opt-in `cloud` extra with a guarded import, is engine #178.

Earlier (2026-09-26):

- **Platform PR #67 (feat/scheduler-s12-recovery):** S12 crash-safe recovery coordinator and flag-on startup wiring.
- **Engine PR #178 (feat/cloud-extra-split):** cloud connectors moved into an opt-in `[cloud]` extra behind a guarded import.
- **Engine PR #179 (feat/native-date-shift):** native date_shift operator (Phase 5).
- **Decoy CLI PR #50 (feat/cli-install-dx-extras):** pass-through install extras and fail-closed missing-extra errors.
- **Decoy CLI PR #51 (feat/cli-native-packaging-default-on):** native packaging default-on when the companion is present.

### 2026-09-26 -- Roadmap correction: CLI PR #47 unblock confirmed resolved (decoy PR #47, merged 2026-09-12)

The roadmap still listed this as an open `[Cam]` decision (pin+regen / merge-into-known-red /
hold) after the decision had already been made and acted on. Checked GitHub directly: decoy
PR #47 ("Preflight: render OOC capacity build-floor as an advisory warning") merged 2026-09-12
with 3 of 5 CI checks failing (pytest on 3.10/3.11/3.12), matching the merge-into-known-red
option. Two follow-up commits landed the same day and fixed the pytest red: `f6b1c92c` (synced
`seed_protocol_version` assertions to engine v7 after the FF1 bump) and `6eb0ca02` (pinned typer
to the 0.26 line so `cli-reference.md` regenerates reproducibly). decoy main has not moved since
that merge, and its latest CI run is green across all 5 checks -- confirmed no residual red.
Roadmap updated to mark Stage E item 20 (CLI PR #47) DONE and drop the matching "follow-ups to carry" entry.

### 2026-09-25 -- Adaptive scheduler S8 + S8b: worker-migration + cross-process RPC dispatch capstone (PR #65, merge fc38805a)

The R3 capstone of the V1-7 integration. The whole V2 job lifecycle now runs (flag-on) as an
execve'd worker born into the job's cgroup, launched by the single-threaded supervisor over the S3
socket; the controller stays the sole lease-DB authority and the supervisor is DB-free, coordinating
preflight -> convert -> launch -> observe-real-exit -> confirmed-populated-0 release across a
DB-free RPC protocol (preflight_start/status, run_job_start/status, result_ack, fence). Exactly-once
capacity release, generation fencing, SCM_RIGHTS fd handoff, a lost-run_job_start recovery state
machine, and cloud fd read-through. Behind `adaptive_scheduler_lease_authority_enabled` (default
off) = byte-identical to today. Gate history: Codex PLAN GO (3 rounds) -> 5 build sub-slices ->
mid-way dennis (2 safety gaps remediated) -> atomic gate NO-GO (real R3 defects) -> 2 remediation
rounds (F2-F8) + an F5/F7 completion round -> dennis GO + Codex FINAL GO. One CI follow-up (authz
allowlist relocation after a refactor moved a reviewed lookup). S1-S8 now all merged behind the flag.
DEFERRED/owed: **S9 (thread-grant) deferred** (native parallelism dormant until engine Task 1.5;
grant is fairness not safety); F1 install_backend wiring -> S12; full real-supervisor e2e attestation
-> S14 prodsim; §4.1 module splits (v2_orchestrator 605 / runner 732 LOC). NEXT = S10/S11/S12/S13,
then prodsim + the Cam-gated flag flip. State: memory [[decoy-scheduler-v1-build-state]].

### 2026-09-25 -- Verification-hardening cluster: post-validation suite, KS/chi-square, local post-mask checks (A1/A2/A5a)

The three-part cluster that finishes the post-mask verification surface the product already
half-shipped, so prodsim validates a complete one. All R2, all default-OFF or report-only.

- **A1 (engine, PR #176, merge `7ec1c5ec`).** Wired the built-but-dormant 8-scan post-validation
  suite into `run_pipeline` behind default-OFF runtime args (`post_validation` /
  `post_validation_skip` / `post_validation_sample_size` / `post_validation_enforce`). The engine
  records `quality_metrics["failed_checks"]` + `["post_validation_enforce"]` but never fails the
  job itself; the platform consumer decides. The platform ENFORCEMENT half (instance-setting
  opt-in, fail-closed route admission + crashed-scan) is a separate slice, plan-ready (Cam
  decisions 2026-09-25).
- **A2 (engine, PR #177, merge `daa8dd39`).** Added KS-complement (numeric) and chi-square
  Cramer's V (categorical) goodness-of-fit metrics to the distribution-integrity comparator, in
  named `extra_metrics` fields. Additive and report-only: the primary similarity/method, the
  overall_score, and the A-F grade are byte-identical (proven against pre-A2 output). Hand-rolled
  from the aggregate snapshots, no scipy, no raw-value reads.
- **A5a (platform).** Local parquet source/target support in the Storm + Quality post-mask hooks,
  and a seeded reservoir sampler (bounded in rows AND bytes) replacing a biased first-100k head
  sample so integrity reports on sorted local files are representative. Shared `_io_discovery`
  helper; cloud descriptors are an honest skip (the cloud half A5b stays deferred). The
  double-gate hardened it materially: a credential-leak fix (exception text and file paths kept
  out of `job.log`), a sampling-uniformity fix (fixed-count ceiling from a data-constant max row,
  so wide rows are not under-represented when the byte cap binds), and a dtype-expansion fix (the
  byte ceiling bounds the reconstructed `from_records` frame, not the input dtypes).

### 2026-09-21 -- Phase 5 native operators: categorical, bucket_perturb, group_key (engine PRs #171/#173/#174)

Three more masking strategies gained native operators through the unified coordinator's operator
seam. Categorical deterministic pool selection (#171, the first Phase 5 operator picked from the
reprofiled workload mix); bucket_perturb (#173, S-port slate #1); and group_key (#174, merged 2026-09-22 UTC; S-slate #2,
which needed a new canonicalize-free `derive_hex_raw_batch` kernel, preserves the source
pandas-metadata on stringify, and is scoped to `{string, int64, bool}` sibling types). Each is
shadow-parity-proven against the pandas oracle and double-gated (dennis + Codex; group_key's Codex
FINAL caught a pandas-metadata P0, remediated at source). All three merged 2026-09-21, full CI
green. Carry-forward from the group_key review: its sibling-table input seam is correct but should
be refactored to declared input-slots / an `OperatorInputContext` before the next sibling-reading
native operator copies it. Plans: `decoy-engine: docs/plans/` (phase5-categorical, native
bucket_perturb, native group_key).

### 2026-09-21 -- Generation fast-path: native-ize the World B pool sampler (engine PR #169)

The last identified `derive_index_batch` drop-in. The World B pool sampler (`generation/pool/_sampler.py`)
mapped a canonicalized source value to a pool slot with a PER-ROW `derive_index` loop, in both the scalar
deterministic path and the composite `sample_bundle` deterministic branch. Both now use the batched
`derive_index_batch` kernel (the same one that made Phase 2 pool-index selection ~13x). BYTE-IDENTICAL to
the former per-row output -- proven compiled == reference == legacy across every value class (ascii +
NFC/NFD unicode, bools, signed/unsigned + numpy ints of every width, tz-aware incl. sub-microsecond and
non-UTC timestamps, `Decimal("NaN")`, `uint64 > 2^63`, int64 bounds, bytes/uuid, duplicates, empty/
all-null/mixed nulls). Measured ~10.6x at 100k rows (1160ms -> 110ms). Nulls are stripped before the
kernel (matching the legacy `source.isna()` contract, avoiding the `pd.NA` vs `_is_missing` divergence);
the composite bundle keeps its one-shared-index-per-row tuple integrity; the non-deterministic path is
untouched; value classes the compiled kernel rejects fall back to the reference kernel over raw Python
values (byte-identical, "supported, correct, slower"). Codex plan-gate GO -> dennis APPROVE (ns-timestamp
end-to-end guard + docstring remediated) -> Codex FINAL GO (no findings) -> full CI green (both
substrates, 34-min regression suite). Plan: `decoy-engine: docs/plans/2026-09-21-worldb-sampler-native-index.md`.

### 2026-09-21 -- Phase 6: delete the dormant Polars masking adapter (engine PR #168)

Pre-GA hard-delete of the Polars MASKING adapter. `"polars"` was a value-parity-with-pandas opt-in
that measured no faster for the per-value keyed-crypto masking workload, was reverted to dormant, and
is now removed: `execution/polars/` (the adapter + its strategy ports), the `polars_native` planner
mode, the polars when-gate variant, the polars reason-code translation, and the physical-plan
`Substrate.POLARS` capability. `VALID_SUBSTRATES` is `("pandas",)`; `substrate="polars"` /
`DECOY_SUBSTRATE=polars` now raise `invalid_substrate`. Net ~-5,600 LOC (100 files). No masking
behavior change (pandas was always the masking output, byte-identical; test-flight fingerprints
unchanged); the retained generic non-pandas guards stay as fail-closed defence, re-covered by
synthetic-`future_substrate` unit tests. `subset/` keeps the polars LIBRARY for FK-closure joins,
and the `polars>=1.0,<2.0` dependency is unchanged. The V2 baseline benchmark harness (its only
correctness dimension was pandas==polars parity) was retired, its historical baseline preserved as a
dated validation record. Executed via the plan's iterative delete->sweep->sentry method (the wide-
but-shallow reference cleanup took several passes). dennis APPROVE + Codex substantive-GO (Codex's
sandbox-only pyarrow `string`/`large_string` test failures were ruled out against the pinned-env
full CI, which is green -- both substrate + regression-gate suites pass). §9 compatibility checklist
completed (pre-GA hard delete). Plan: `decoy-engine: docs/plans/2026-09-18-polars-masking-removal.md`.

### 2026-09-21 -- Phase 3.3: platform rollback lever + unified-lane route evidence (platform PR #53)

The engine's unified-slice masking lane is already the production default (activation, #165),
so the platform worker reaches it with no code change. This slice adds the platform-owned
CONTROL and OBSERVABILITY around that: a rollback lever `UNIFIED_SLICE_ENABLED` (pydantic
setting, default True) threaded into both engine `run_pipeline` call sites -- the job runner
and the preview helper -- so ops can fall back to the legacy pandas oracle without an engine
release (flip to False; the spawned bounded-preview child inherits it via `os.environ`). The
job report now records the route the engine ACTUALLY ran (`execution_route` in the node-run
exports: `unified_slice` / `legacy_full_frame` / `legacy_chunked`), derived from engine
evidence -- the `unified_slice_activation` leaf, then `quality_metrics["auto_chunk"]["mode"]`
-- never from the flag, so an enabled-but-non-admissible or legacy-chunked job is labeled by
the path used, not the setting. The literal Task 3.3 plan was obsolete post-activation/4.7
(it referenced the deleted `native_route_enabled`); re-scoped by Opus, Codex plan-gated. dennis
APPROVE (2 MEDIUM test-quality findings remediated: a vacuous spawn-child test and a weak parity
assertion). Codex final NO-GO round 1 caught the legacy-chunked route mislabel (P2), remediated
at root by reading the engine's second routing-evidence source; Codex re-gate GO. Full CI green
(both substrates). Task 3.4 (bounded release: prodsim/canary, fingerprint comparison, abort
criteria) is deferred to Stage B, where it merges with the prodsim validation. Plan:
`decoy-platform: docs/plans/2026-09-21-phase-3.3-unified-lever.md`.

### 2026-09-20 -- Task 4.7: delete the superseded native routing lane (engine PR #166)

Removed the dead standalone single-pass streaming native lane now that the unified-slice
coordinator (activated in #165) owns the production single-table masking path. The
`native_route_enabled` flag always defaulted False and was never enabled in production, so
this is a behavior-neutral pre-GA hard cutover: deleted `_native_route*.py` +
`physical/drivers/_native_stream.py` + 8 native test files, removed the flag from the
pipeline/admission/compiler and the `ExecutionResult.native_route` field + `DriverId.NATIVE_STREAM`
+ the native reason-code catalog. Net -7,300 lines; one production decision path remains. The
compiled deterministic-Faker kernel package (`execution/native/`) is untouched. One observable
side effect: the internal `plan_hash` shifts by a one-time constant (no platform consumer compares
it). dennis + Codex gated (dennis caught a second sentry allowlist that needed the deleted paths);
full CI green (both substrates). Plan: `decoy-engine: docs/plans/2026-09-20-task-4.7-delete-native-route.md`.

### 2026-09-20 -- Route activation: unified lane is the production default (engine PR #165)

`unified_slice_enabled` now defaults True, and admission no longer declines a
full_frame job that carries the platform worker's inert sink, so the certified
unified-slice lane is the production default for its admitted subset (single non-FK
Parquet mask table on the four native scalar strategies, pandas full-frame). The
platform isolated-worker reaches the lane with no platform-side change; admission
stays the safety gate and every non-admissible shape falls through to the unchanged
legacy route. D9 re-cert GREEN on the exact commit (n2-standard-8): 10k RSS 1.023x,
100k 1.048x, 1M 1.094x under the 1.25x band, ~4.3x faster at 1M. Full engine suite
green (11265); dennis + Codex (plan-gate round 3 + final) gated. Cert artifact under
`docs/product/release-1-validation-runs/2026-09-20-d9-recert/`. Next: Task 4.7
(delete the superseded routing). Plan: `decoy-engine: docs/plans/2026-09-20-unified-slice-activation.md`.

### 2026-09-12 -- FPE is now NIST SP 800-38G FF1, not the home-rolled Feistel (engine PR #132)

The `fpe` strategy's cipher is NIST SP 800-38G FF1 (Algorithms 5/6), AES-256 through the audited
`cryptography` package, KAT-locked against NIST's published known-answer vectors plus a
Wycheproof-derived corpus and a structurally separate differential oracle (source SHAs recorded in
#133). This was a pre-GA HARD CUTOVER (Task 5.2, native-throughput plan): the engine's earlier
home-rolled 8-round HMAC-SHA256 Feistel construction was DELETED entirely, no dual-primitive period,
gated by `SEED_PROTOCOL_VERSION` 6 -> 7. Every `fpe` column and the `fpe`-branch text-mask spans now
use FF1, and every keyed derivation that mixes in the shared version byte changed output. The
conformance claim is precise: "AES-FF1 conformant to NIST SP 800-38G," enforcing the Rev.1 Second
Public Draft restrictions (FF1 only; FF3/FF3-1 withdrawn after the Beyne 2021 attack); NOT
"NIST-certified" or "FIPS 140 validated." dennis + Codex final gated; FF1-primitive mutation ledger
at logic-100% (crown-jewel bar). Detail: `decoy-engine: docs/security/de-01-ff1-adoption.md`.
Open item for Cam (not resolved by the ship): the Voltage/OpenText FF1 method-patent question the
FF1 design flagged as a legal check is not recorded as decided anywhere; see the ROADMAP "Deferred /
parked" note.

---
