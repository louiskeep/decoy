# Decoy CLI QA report

Tested as a first-time user on a made-up dataset: `patients.csv` (10 rows: `patient_id`, `full_name`, `ssn`) and `visits.csv` (20 rows: `patient_id` FK, `diagnosis`). That is 30 rows, 2 tables, 5 columns, 3 PHI (`full_name`, `ssn`, `diagnosis`), 1 FK.
Build: decoy-cli 0.1.0 + decoy-engine 0.19.0, installed from source on Python 3.12 (the engine rejects 3.13). Color checked through a real pty.
Coverage: every top-level command was exercised except `upgrade` (help only; it needs the hosted channel). `report vault` was exercised via `--help` only.

## 1. QA question bank

### A. User ignorance ("I've never used this")
| # | Question a new user asks | What happened | Verdict |
|---|---|---|---|
| A1 | What does this tool do and where do I start? | `decoy` and `decoy info` show a good splash; root help is a 25-line wall | OK, noisy |
| A2 | I mistyped a command | `scna` gives "Did you mean scan, schema?" | Good |
| A3 | What is STORM? | Appears in scan output, demo, init, explain. It is not a command | Confusing |
| A4 | Which preset do I pick? | Wizard lists names only, no descriptions. Typo `hippa` gets no suggestion, and the re-prompt drops the choices | Weak |
| A5 | What is a "mask secret" and why do I need one? | The error is accurate but a one-line wall; `explain keys` is long | Weak |
| A6 | What is a namespace? | Never explained at the point of failure; only the schema says so | Gap |
| A7 | What does "reid risk 100.0" mean? | No unit or scale in the panel (the scale is 0-100 only in `explain storm`) | Confusing |
| A8 | Is my data safe to share after this? | No single "safe/unsafe" answer; `integrity`, `fidelity` and `verify` each say something different | Gap |

### B. User expectations ("I assumed it would...")
| # | Expectation | Reality | Verdict |
|---|---|---|---|
| B1 | Columns I forgot to list get masked (or at least flagged) | **Copied in clear, no warning** from `validate` or `run` | **Critical** |
| B2 | `validate` passing means `run` will work | Failed: missing source columns (bare `'account_number'`), `fpe` without namespace | High |
| B3 | A wizard preset fits my CSV | HIPAA preset is 21 generic columns; my CSV has 3 | High |
| B4 | FK joins survive masking | Yes, `hash` + shared namespace keeps patient 1 joinable across tables | Good |
| B5 | Re-running with same config and secret gives the same output | `patients` identical; `visits` (`shuffle`) differed between runs | Question |
| B6 | Raw PHI never appears in saved artifacts | Outputs and evidence clean; **scan JSON holds raw names/SSNs** and `scan show` prints them | High |
| B7 | `run` tells me what it did | Panel shows pipeline, mode, elapsed, route. No rows, no files, no tables | Weak |
| B8 | `--preset` skips the wizard | Still prompts for paths; with no tty it exits 1 "Aborted." | Minor |
| B9 | `list disguises` ids work with `init --preset` | The tip says so; only 5 of 10 ids exist (`ccpa` fails) | Bug |
| B10 | Integer ids stay integers | `hash` turns `1` into a 64-char hex string | Surprise |

### C. Unclear workflow ("what do I do next?")
| # | Question | What happened | Verdict |
|---|---|---|---|
| C1 | I have two tables; how do I scaffold? | `init` accepts one file; extra files error; `init .` exits 1 silently | Gap |
| C2 | How do I find FKs between files? | Nothing does; `scan` is per file | Gap |
| C3 | How do I author a `relationships:` block? | Only the JSON schema or trial and error | Gap |
| C4 | Where is the walk-through from scan to masked output? | `demo` is single-table, redacts the id, truncates its paths | Weak |
| C5 | `ci check` with no manifest | Raw JSON `ci.manifest_unreadable`, no hint, no `ci init` | Weak |
| C6 | `subset` with no `subset:` block | Clear message, but no scaffold | OK |
| C7 | How do I read the evidence file? | `report show/verify/diff/render` work well; `render` requires `--output` | Good |
| C8 | Ctrl-C in the wizard | Clean "Aborted.", exit 1 | Good |

## 2. Findings by severity

### Critical
1. **Uncovered columns pass through unmasked, silently.** Removing `ssn` from the pipeline: `validate` = OK, `run` = exit 0, output still contains `431-29-7468`. Fix: warn (or fail by default) on any source column not listed; require explicit `passthrough`.

### High
2. **`validate` and `validate preflight` crash with a raw Rich traceback** when a relationship has no resolvable namespace (internal paths shown, exit 1). `validate compile` accepts the same file and says "no FK dependencies detected" while one is declared.
3. **Gate passes, run fails.** Declared columns missing from the source (hipaa preset on a 3-column CSV) pass preflight, then `run` dies with `error: 'account_number'` (exit 3). `fpe` without namespace also passes the gate, then fails at run with exit 3 (a config error returning a runtime code).
4. **Wizard presets are not data-aware.** It never reads your file; presets scaffold columns you don't have and miss ones you do (`full_name` was not covered by the HIPAA template). The column-aware path (`init file.csv`) is separate and undiscoverable from the wizard.
5. **Scan artifacts contain raw PHI.** `scan_patients.json` includes real names and SSNs in `top_values`; `scan show ssn` prints them. File mode is 0600, but the format is built to be diffed and checked in CI.

### Medium
6. Scan misses clinical PHI (`diagnosis` "none detected"), without saying detectors cover patterns, not meaning. Reid risk is 0.0 for the table with SSN + name and 100.0 for the 2-column table, with no unit. `scan show` prints `Detectors  ?`.
7. Internals leak into user text: `decoy scan _scan` in usage errors (`scan nofile.csv`, `scan .`); "STORM"; ticket ids (OSS.4c, FC-1, CLI.3, storm-reframe-C); a `decoy-platform/docs/...` path; "Storm integrity".
8. `explain pipeline` says `version 1`; every scaffold and the schema use `version: 2`.
9. `run` summary is thin (no rows, files, tables) and `--json` is the same. "2 pre-run warning(s); run `decoy validate`" makes you run a second command. The warning "output directory does not exist" is a false alarm: `run` creates it.
10. `report fidelity` prints "PASS grade F overall_score 0.000". `report integrity` shows "residual_pii: 2 warnings" with no columns even with `--verbose` (only `--json` has detail), and they are expected: FPE/faker output looks like SSNs/names by design.
11. `shuffle` output differed between two runs with the same seed and secret. Confirm whether that is intended.
12. Stray `logs/decoy_engine.log` created in the current directory by `scan`, `demo` and `run`.
13. `list disguises` tip (`init --preset <id>`) is wrong for ccpa, cpni, default, ferpa, glba, pc, sox.
14. `ci check` without a manifest prints compact JSON and no next step.
15. The tokenize vault `tokens.db` stores plaintext values (0600 SQLite); `explain vault` talks about an *encrypted* vault. Say which is which.

### Low / polish
- Root help repeats the Commands panel and wraps without indent; `init --help` examples have mangled whitespace.
- Demo panel truncates paths with `…`, including the copy-paste "Next:" command; `report show` truncates the Run ID.
- `validate compile --json` reports `"command": "compile explain"` without `--explain`.
- `list strategies` shows class names, not summaries; `show strategy fpe` has no parameters or YAML example.
- `report render` has no stdout default; `detokenize` has no `--mask-secret` while `tokenize` does.
- `demo` redacts `customer_id`, which breaks joins in the very example people copy.

### Worked well
Typo suggestions; most error hints; key/secret errors; 0600 file modes; outputs and evidence contain no raw values; FK preserved; tamper detection (`report verify` exit 4); documented exit codes; clean Ctrl-C; `diff` and `render`; the tokenize/detokenize round-trip.

## 3. Do the command families make sense?
Mostly, with three fixes:
- **Flat top level.** 18 commands in one list. Use Typer `rich_help_panel` to group: *Start* (demo, init, info), *Discover* (scan), *Check* (validate), *Transform* (run, subset, fit, tokenize, detokenize, unmask), *Prove* (report, ci), *Reference* (list, show, explain, schema), *Setup* (doctor, upgrade). Zero behavior change.
- **Reversal commands** (tokenize/detokenize/unmask) are a coherent family; consider `decoy reverse ...` or keep flat but panel them.
- **Reference family** (`list`, `show`, `explain`, `schema`) overlaps; `explain` is the best entry point, so make `list`/`show` point to it.
- Hidden default subcommands (`_scan`, `_gate`) are good UX but leak in errors.

## 4. Wizard: color and interactivity
Today only the title (cyan), hints (dim), `error:` (red), `OK` (green) and paths (blue) are colored; prompts are plain.
1. A step header ("Step 1/3 - Preset") and a colored prompt with the default in dim brackets.
2. A preset table with one-line summaries (reuse `list templates`), and an arrow-key picker instead of typing names; "did you mean" on typos; keep the choices on re-prompt.
3. If a CSV is given or found, read it first and show a live column table (name, type, PII suggestion in yellow/red) so the user confirms the strategy per column; this removes the preset/columns mismatch.
4. Ask for multiple tables, then offer to detect FKs by value overlap and write `relationships:` + `namespace:`.
5. A closing summary panel: files written, columns covered vs uncovered (red), the exact next three commands (copyable, never truncated), and the mask-secret setup as a numbered step.
6. Honor `NO_COLOR` and non-tty (already works); add `--no-input` so `--preset` + `--yes` never prompts.

## 5. Missing / suggested additions
- Uncovered-column guard (item 1) plus a `--strict` mode.
- A data-aware preflight: every declared column exists in the source; every source column has a rule.
- Multi-file `scan` (directory/glob) and `decoy relationships detect`.
- `decoy secret generate` (so users don't copy `openssl rand` from errors) and a doctor check for it.
- `run --dry-run` and a real run summary (rows in/out, files written, columns by strategy, evidence path).
- A single `decoy report summary` verdict that combines verify + integrity + fidelity in plain words.
- `decoy ci init`; `decoy subset init`.
- Redact `top_values` for PII-flagged fields in saved scans (opt in to raw values).
- Pointer from every gate error to a docs/`explain` topic (namespace, relationships).

## 6. Environment note
Install friction: the engine pins Python `<3.13`, so `pip install` fails on a default Python 3.13 box with only a version error. Worth a clearer message or a wider pin.

