# Decoy CLI — UX standards & practices

> **Status:** partial — Slices 1–3 shipped 2026-05-04: theme module, --json/--quiet/--verbose plumbing, --install-completion, progress wrappers (spinner / bar / multistage), run-summary cards, themed Rich tables, new commands (`storm scan`, `forecast recommend`, `init`, `demo`), and tab-completion sources for Disguises / transforms / Faker providers. Future commands must continue to follow these standards; ~/.decoy/logs traceback fallback (section 9) and telemetry (section 15) remain forward-looking.
> **Last reviewed:** 2026-05-04

The standards every contributor follows when adding or modifying a `decoy` CLI command. Read this before you write a new command. If you're tempted to deviate, file a PR against this doc first.

This guide is opinionated and Decoy-specific, not a generic CLI-design listicle. It's the reason every Decoy command feels like the same tool instead of a grab-bag.

---

## 1. Where the CLI fits in the product

Decoy ships in three shapes: the **CLI** (this repo, free, `pip install decoy`), the **platform** (self-hosted FastAPI + React, Business tier), and the **engine** (`decoy-engine`, the shared Python library both use). The CLI and the platform are deliberately different products with different jobs.

**One-shot vs. session.** A CLI invocation runs one command and exits. It does not maintain state between calls beyond what's saved on disk (config files, scan outputs, license tokens). It does not present a continuous workspace. Users come to the CLI when they know what they want done and want it done now.

**What stays in the Web UI.** The pipeline canvas (drag-and-drop graph editor), the FORECAST drill-down (click a column → see its detector hits, sentinel values, mask alternatives), the audit list of past Reports, scheduled runs with cron triggers, sharable signed Report PDFs — none of these belong in the CLI. They are **session experiences**: long-lived, exploratory, multi-step. The CLI shouldn't try to imitate them with TUI panes or live dashboards.

**What's CLI-only or CLI-best.** CI/cron scripting (the CLI's killer use case — `decoy run pipeline.yaml` in a GitHub Action). Air-gapped customers (the CLI ships standalone, no platform required). The engineer's local iteration loop (edit YAML, `decoy run`, eyeball output, repeat — much faster than clicking through a web app). Ad-hoc one-shot analysis (`decoy storm scan some.csv | jq …`).

A useful test: if you can imagine the user reaching for `tmux` to keep the CLI running, you're building the wrong thing. Send them to the web product.

---

## 2. Principles (the load-bearing rules)

These six rules don't change. Everything else in this guide is downstream of them.

1. **Pipe-friendly by default.** Default human-readable output goes to stdout. With `--json`, structured output to stdout, all chatter to stderr. With `--quiet`, only errors to stderr. Stdout is the data plane; stderr is the chrome plane.
2. **Colors are semantic, not decorative.** Green never means "look at this," it means "success." Red never means "this is bold," it means "error." Tokens are defined once in the theme module; commands reference tokens, not raw colors.
3. **Progress for any operation that can exceed ~1 second.** Spinners for indeterminate ops, bars for known-length ops, multi-stage indicators for pipelines. Always to stderr.
4. **Hints belong at the error site.** When something fails, tell the user what to do next in the same message. Don't make them dig through `--help` to recover from a typo.
5. **Stay headless-friendly.** When stdout isn't a terminal, drop Rich rendering automatically (it does this on its own — just don't fight it). Honor the `NO_COLOR` env var.
6. **Don't be a TUI.** No multi-pane layouts. No live-refreshing dashboards. No long-lived sessions with stateful navigation. See section 13 for the explicit list.

---

## 3. Command + flag conventions

### Naming

- **Verb–noun, not noun–verb.** `decoy storm scan`, not `decoy scan-storm`. `decoy connectors list`, not `decoy list-connectors`.
- Use **subcommand groups** when a noun has multiple verbs: `decoy connectors list`, `decoy connectors test`, `decoy connectors create`. Don't flatten to top-level if the group is meaningful.
- Avoid abbreviations except for universal ones (`config`, `info`). `decoy gen` is wrong; `decoy generate` is right (the user can alias it themselves).

### Standard flags

Every command has these. They go in a shared parameter group so they're never re-implemented per-command.

- `--help` — Typer gives you this for free.
- `--json` — structured JSON to stdout, no Rich rendering. Errors still go to stderr.
- `--quiet` / `-q` — suppress all stdout chatter. Errors still go to stderr. Exit code carries success/failure.
- `--verbose` / `-v` — debug-level logging on stderr. Stack traces on uncaught errors.

`-v -q` together is a user error → `error: --verbose and --quiet are mutually exclusive` (exit 1).

### Flag style

- **Long flags are kebab-case:** `--sample-rows`, not `--sample_rows` or `--sampleRows`.
- **Boolean flags use `--flag` / `--no-flag` form** when both states matter. Otherwise just `--flag` for true.
- **Short flags only when frequent.** `-v`, `-q`, `-y`, `-h`, `-o` are reserved cross-command. Don't invent new short flags for low-frequency options.
- **Positional args first, then flags.** `decoy run config.yaml --mode mask`, not `decoy run --mode mask config.yaml`.
- **`-` as a path means stdin/stdout** where it makes sense:
  - `decoy validate -` reads YAML from stdin.
  - `decoy storm scan ./data.csv --out -` writes scan JSON to stdout.

---

## 4. Output modes — the contract

The contract is simple. The default mode is rich-rendered for humans on a TTY. Three flags toggle deviations.

| Mode | When to use | stdout | stderr |
|---|---|---|---|
| **Default (TTY)** | interactive terminal | Rich-rendered: panels, tables, color | progress, status, warnings |
| **Default (non-TTY)** | piped output | plain text equivalent — same content, no ANSI | progress disabled, warnings still shown |
| **`--json`** | scripting | one structured JSON object to stdout | progress + errors |
| **`--quiet`** | cron/CI | nothing on success | errors only |
| **`--verbose`** | debugging | normal stdout | adds debug logs + stack traces |

**TTY auto-detection.** Rich does this automatically when you use a `Console`. Don't fight it. Don't write code that checks `sys.stdout.isatty()` directly — let Rich handle it.

**`NO_COLOR`.** Honor it across all modes. If `NO_COLOR=1` is set in the environment, no ANSI escapes appear in output regardless of the `--json/--quiet/--verbose` mode. Rich respects this when properly configured; verify with `NO_COLOR=1 decoy --help`.

**`DECOY_DEBUG=1`.** Opts into stack traces on uncaught errors without requiring `--verbose`. Useful for environments where you can't pass flags (Lambda, container entrypoints).

**Stdout is the data plane.** The output of a command, when piped, must be useful. `decoy storm scan data.csv | jq '.fields[].name'` should work without `--json` flag; the default JSON output piped to a non-TTY should be valid JSON. (For commands whose default human output is unstructured prose, that command's `--json` flag is required when piping.)

**Errors always go to stderr** — never stdout — regardless of mode. `decoy run x.yaml > out.csv` should produce a clean CSV file even if the command logged warnings to stderr.

---

## 5. Color palette as semantic tokens

All color decisions flow through a single theme module. Commands reference tokens by name, never raw colors.

| Token | Meaning | Default Rich style |
|---|---|---|
| `success` | OK, validation pass, run complete | `green` |
| `error` | failure, exception, refusal | `bold red` |
| `warn` | deprecation, non-fatal anomaly | `yellow` |
| `info` | progress narration, neutral status | `white` |
| `hint` | "try this," "see also," next-step nudges | `dim` |
| `accent` | identifiers, file paths, table headers | `cyan` |
| `code` | inline code, transform IDs, masked column names | `bright_blue` |
| `risk_high` | sentinel values, high PII score, HIPAA quasi-identifiers | `bold red` |
| `risk_med` | quasi-identifier members, mid PII score | `yellow` |

**The right shape:**
```python
from decoy.ui.theme import success, error, hint
console.print(success("OK") + " ", config_path)
console.print(error("Invalid config:"), reason)
console.print(hint("hint:") + " run", code("decoy validate"))
```

**Anti-pattern:**
```python
# DO NOT do this.
console.print("[red]error:[/red] ...")
console.print("\033[32mOK\033[0m")
```

The reason: the day we want to add a high-contrast theme, or a Solarized variant, or per-token darkmode, every direct color reference becomes a refactor. Tokenize once.

**Risk-color note:** `risk_high` and `error` happen to share a default style today. They're separate tokens because they may diverge — `error` is for the CLI failing, `risk_high` is for the data being flagged. Keep them distinct in code.

---

## 6. Help format

Every command's `--help` follows the same shape. Typer auto-generates the structural pieces; the prose is yours.

1. **One-line summary.** First line of the docstring. Shows up in the parent command's help table.
2. **Description.** 1–3 lines explaining what the command does and when you'd reach for it. Plain prose.
3. **Usage line.** Auto-generated by Typer.
4. **Args + flags table.** Auto-generated by Typer, styled by the theme.
5. **Examples panel.** A Rich `Panel` titled "Examples" with 1–3 realistic invocations + a one-line "what this does." Wired with Typer's `epilog` parameter.
6. **See also.** Pointers to related commands and a docs URL. Always last.

A finished `--help` looks like:

```
Usage: decoy storm scan [OPTIONS] SOURCE

  Scan a dataset and produce a STORM profile (PII detectors, sentinels,
  re-identification risk). Use this when you've been handed a dataset and
  want to know what's in it before writing a masking pipeline.

Arguments:
  SOURCE  Path to a CSV file, or a connector ID prefixed with conn:.  [required]

Options:
  --rows INTEGER       Sample row cap. Default 100K.
  --strategy [full|head|random|stratified]
                       Sampling strategy.  [default: head]
  --out PATH           Where to write the scan JSON. Use - for stdout.
  --json               Emit JSON to stdout, progress to stderr.
  --quiet              Suppress stdout. Errors still go to stderr.
  --verbose            Add debug logs to stderr.
  --help               Show this message and exit.

╭── Examples ──────────────────────────────────────────────────╮
│ decoy storm scan data.csv                                    │
│   Scan ./data.csv with default sampling, print summary.      │
│                                                              │
│ decoy storm scan data.csv --json > scan.json                 │
│   Capture the full StormProfile for piping into forecast.    │
│                                                              │
│ decoy storm scan conn:prod_pg --rows 50000 --strategy random │
│   Sample 50K random rows from a saved Postgres connector.    │
╰──────────────────────────────────────────────────────────────╯

See also: decoy forecast recommend, decoy run.
Docs: https://decoy.dev/docs/storm
```

If your command's help looks different from this — add an examples panel, polish the description, or fix the option naming.

---

## 7. Progress patterns

Three patterns. Pick the one that matches your operation. All progress streams to **stderr**.

### Spinner — indeterminate

Use when you don't know how long the operation will take and you can't show progress. Examples: loading a YAML config, opening a database connection, the brief moment before a known-length operation kicks off.

```python
from decoy.ui.progress import spinner

with spinner("Loading config…"):
    config = load_pipeline_config(path)
```

Auto-disabled when `--quiet` is set or when stderr isn't a TTY.

### Progress bar — known length

Use when you can advance a counter — most commonly, processing N rows of a CSV.

```python
from decoy.ui.progress import progress_bar

with progress_bar(total=row_count, label="Processing rows") as bar:
    for chunk in read_chunks(path):
        process(chunk)
        bar.advance(len(chunk))
```

Show: percent, bar, ETA, throughput (rows/sec).

### Multi-stage indicator — pipelines

Use for any operation that has named, ordered phases. STORM is the canonical example: load → profile → detect → score.

```
[✓] Load source       (1.2s)
[▶] Profile columns   ████████████░░░░  72%  ETA 0:00:03
[ ] Run detectors
[ ] Compute risk score
```

Implemented with Rich's `Progress` carrying multiple `task_id`s. The wrapper in `decoy.ui.progress` exposes:

```python
from decoy.ui.progress import multistage

with multistage(["Load source", "Profile columns", "Run detectors", "Compute risk score"]) as stages:
    df = load_csv(path)
    stages.complete()  # advance to "Profile columns"
    profile = profile_columns(df)
    stages.complete()  # advance to "Run detectors"
    ...
```

When a stage is the data-bearing one (e.g., "Profile columns" iterating per row), the wrapper supports nested progress within that stage.

### Anti-patterns

- **Don't print bare progress dots** (`...`, `....`). Use the spinner.
- **Don't put progress on stdout.** It pollutes pipes and breaks `--json`.
- **Don't use a spinner to hide >10s of work without showing what's happening.** Switch to a multi-stage indicator and tell the user where time is going.
- **Don't render any progress when `--quiet` is set.** Honor the contract.

---

## 8. Run summary cards

After any meaningful command finishes, print a Rich `Panel` summarizing what happened. The card has a fixed shape so users learn to scan it.

### Shape

- **Top row:** `<status icon> <command>` — e.g., `✓ decoy storm scan`. Icons: `✓` success, `!` warn, `✗` error.
- **Body:** key facts laid out in two columns. Aim for 4–7 facts; trim everything that isn't useful at a glance.
- **Bottom row:** `Next:` followed by the natural follow-up command.

### Examples

```
╭── ✓ decoy run ───────────────────────────────────────────╮
│  Pipeline      patients_demo.yaml                         │
│  Mode          mask                                       │
│  Rows masked   50,317                                     │
│  Columns       9 (4 transforms applied)                   │
│  Elapsed       2.3s                                       │
│  Output        masked/output.csv                          │
│                                                           │
│  Next: head masked/output.csv                             │
╰───────────────────────────────────────────────────────────╯
```

```
╭── ✓ decoy storm scan ────────────────────────────────────╮
│  Source            patients_demo.csv                      │
│  Rows scanned      50,000 (head)                          │
│  Columns           10                                     │
│  PII columns       6 (high)                               │
│  Reid risk score   88.9                                   │
│  Saved profile     scan_2026-05-04.json                   │
│                                                           │
│  Next: decoy forecast recommend scan_2026-05-04.json      │
╰───────────────────────────────────────────────────────────╯
```

```
╭── ✓ decoy forecast recommend ────────────────────────────╮
│  Top recommendation   HIPAA Disguise (score 0.90)         │
│  Fields covered       6 of 10                             │
│  Risk flags           4 (2 sentinels, 2 quasi-identifier) │
│  Draft pipeline       forecast/draft.yaml                 │
│                                                           │
│  Next: decoy run forecast/draft.yaml                      │
╰───────────────────────────────────────────────────────────╯
```

### Rules

- **Always include `Next:`.** Every meaningful command leads somewhere. Telling the user what's next is half the value of the card.
- **Don't render the card with `--json`.** The structured JSON output already covers it. The card is for humans.
- **Don't render the card with `--quiet`.** Honor the contract.
- **Use `code` token for paths and identifiers.** Cyan paths read better than the default white.

---

## 9. Error UX

Errors get more design care than success because they're the moments users get stuck.

### Shape

```
error: <one-line cause, no jargon>

  hint: <what to do — a verb sentence>
  docs: <URL if applicable>
```

Concrete:

```
error: Connector "prod_pg" not found.

  hint: list connectors with `decoy connectors list`.
  docs: https://decoy.dev/docs/connectors
```

```
error: Invalid pipeline config: missing required key "input.path".

  hint: see `decoy validate --help` or the config schema:
  docs: https://decoy.dev/docs/yaml-reference#input
```

The cause is one line. The hint is a verb sentence telling the user what to do. The docs link is optional but expected for any non-obvious error.

### "Did you mean?" suggestions

Typer has built-in Levenshtein-based suggestion for unknown subcommands. Enable it. If the user types `decoy stom scan`, Typer should respond:

```
error: No such command 'stom'.

  hint: did you mean 'storm'?
```

Same applies to value errors on `--apply`, `--strategy`, etc. — provide a list of valid values.

### Stack traces

Hidden by default. Show with `--verbose` or when `DECOY_DEBUG=1` is set. Rich's `Console.print_exception()` produces nice tracebacks; use it.

When hiding the trace, log it to the local log file (`~/.decoy/logs/`) so support can request it without asking the user to re-run with `--verbose`.

### Exit immediately on error

Don't print an error and continue. Don't accumulate errors and dump at the end. One error → print → exit nonzero. Multi-error commands (e.g., `decoy validate` checking many configs) are the exception; document them explicitly.

---

## 10. Confirmations

Most commands should not prompt. The CLI's job is to do what the user asked. Confirmation prompts get used sparingly.

### When to confirm

- **Overwriting a file** that already exists and contains user data (e.g., the output of a previous run).
- **Deleting a saved scan, profile, or Disguise.**
- **Applying a Disguise** that touches >N columns (TBD threshold; possibly never — applying produces a draft pipeline, not a destructive action).
- **License-affecting operations** (e.g., switching tier in a logged-in CLI).

### When not to confirm

- Validation that won't write anything.
- Read-only inspection.
- Running a pipeline (the user explicitly invoked the command).

### Shape

```
This will overwrite ./output.csv (47 KB, modified 2 minutes ago).
Continue? [y/N]:
```

- **Default is no.** A stray Enter does not trigger.
- **Skippable with `--yes` / `-y`.** Required for use in CI/cron.
- **Tell the user the consequence**, not just "are you sure?" The first sentence of the prompt names what's about to happen.

### Implementation

Typer has `typer.confirm()`. Don't reach for `questionary` or other libraries unless you have a specific reason; consistency is more valuable than richness here.

---

## 11. Tab completion

Typer ships shell completion for free. We extend it with custom completers for known value sets.

### Install

```
decoy --install-completion
```

Auto-detects the user's shell. Supports bash, zsh, pwsh, fish.

Document this prominently in `decoy --help` and on the docs site.

### Custom completers

For flags whose values come from a finite set:

| Flag | Source |
|---|---|
| `--apply` | `decoy_engine.disguises.load_disguises()` returns the list (`default`, `hipaa`, future bundles). |
| `--mode` | Static set: `mask`, `generate`, `convert`. |
| `--mask` (when picking a transform manually) | The engine's transform factory key set: `faker`, `hash`, `redact`, `map`, `shuffle`, `passthrough`, `date_shift`, `formula`. |
| `--faker-type` | `decoy_engine.internal.helpers.get_faker_providers()` (40+ entries). |
| `--connector` | Read from `~/.decoy/state.json` (Business tier). |

When wiring a completer, use Typer's `autocompletion=` parameter on the `Option`. Keep the completer fast — it runs every Tab press. Cache where useful.

### File-path completion

Typer auto-completes paths for `Path`-typed args. Don't override unless you need to filter (e.g., `*.yaml`).

---

## 12. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | User error (bad args, missing file, invalid config) |
| 2 | Deprecation / migration notice (the `forge` rename shim uses this) |
| 3 | Engine error (pipeline run failed, scan failed, internal exception caught) |
| 4 | License / tier-gate error (Business-only command on Free) — reserved, not used yet |
| 64–79 | Reserved for sysexits.h compatibility (future) |

### Rules

- **Pick the most specific code.** Don't return 1 for an engine error; that's 3.
- **Document the codes in the command's `--help` epilog** when nonstandard codes apply.
- **Tests assert exit codes**, not just output strings. CI scripts depend on these.

---

## 13. What the CLI is NOT for — explicit guardrails

Two lists. Hard ban means "don't even propose it." Soft ban means "default to no, but reasonable exceptions exist."

### Hard ban

- **Multi-pane TUI dashboards.** No `decoy ui`, no `decoy dashboard`, no `htop`-style live screens.
- **Real-time canvas / pipeline graph editing.** Use the web UI.
- **Long-lived sessions with stateful navigation between subcommands.** Each invocation is independent.
- **Embedded FORECAST drill-down.** Showing a list of recommendations is fine; making it interactively navigable in the terminal is web-UI territory.
- **Animations purely for show.** Every Rich element must serve communication. No spinners that exist just because long-running operations "feel weird without one."

### Soft ban (default to no, justify if you must)

- **Interactive wizards beyond `decoy init`.** Wizards on every command turn into the worst kind of CLI. The one-time `init` flow is the only place wizards belong.
- **Spinners that hide >10s of work.** Switch to a multi-stage indicator and tell the user where time is going.
- **Configuration via flags when YAML would be clearer.** If a command takes more than ~5 flags' worth of state, you're using the wrong shape. Move it to YAML.
- **CLI-only features without a web equivalent.** Most things should land in both surfaces. CLI-only feature is fine when it's genuinely CLI-shaped (e.g., shell completion install) but rare.

---

## 14. Cross-platform

Decoy targets Windows (cmd.exe + PowerShell), macOS (Terminal + iTerm2), and Linux (bash + zsh + WSL). Most cross-platform pain comes from one place: terminal Unicode support.

### Default-output Unicode is restricted

Avoid in default output:
- Arrows: `→` `←` `↑` `↓`
- Em-dashes: `—`
- Box-drawing: `─` `│` `┌` `└`
- Most emoji

**Why:** Windows cmd.exe defaults to cp1252, which corrupts these as `â†’`, `â€"`, etc. Even on UTF-8 terminals, our test data has hit cp1252 issues during development.

**Use instead:**
- `->`, `<-`, `^`, `v` for arrows
- `--` for em-dash
- Rich's `Panel` and `Table` for box-drawing — Rich handles fallback.

### Lean on Rich

Rich detects terminal capability and renders accordingly. When you use Rich primitives (`Console`, `Panel`, `Table`, `Progress`), you get cross-platform behavior for free. When you fall back to raw `print()` or `\033[…]` ANSI codes, you're on your own.

The rule: **never write raw ANSI to the console.** Always go through the theme module.

### Test matrix

Before merging a UI-affecting change, sanity-check on at least:
- Windows PowerShell 7 (UTF-8) — the team's primary dev shell.
- macOS Terminal — the most common buyer environment.
- Linux bash piped to `cat` — the most common CI/scripting environment (no TTY).

A test that catches half the cross-platform bugs: pipe the command's output to `cat` and compare to running it in a TTY. The non-TTY version should be plain text with no escape sequences and no progress chrome.

---

## 15. Telemetry (forward-looking)

Decoy will eventually offer opt-in usage telemetry: which commands ran, with what flag combinations, success or failure, anonymized. **None of this is implemented yet.** The convention is documented now so commands are built consistently.

When it lands:

- **`--telemetry on/off` flag** on every command, wired through the shared parameter group.
- **`DECOY_TELEMETRY=on/off` env var** for headless environments.
- **First-run prompt** (after `pip install decoy`, before any command runs): "Send anonymized usage data to help improve Decoy? [y/N]". Default off.
- **What's never sent:** dataset content, column values, file paths, connector strings, schema/table names, any PII detected by the user's STORM scans. Only command + flag tokens.
- **Documented in the CLI's `--help`** as a top-level flag with a link to the privacy doc.

Don't gate any feature behind telemetry. Don't log anything that would betray dataset content. When in doubt, send less.

---

## When you're adding a CLI command — checklist

Run through this before opening the PR:

- [ ] Verb–noun command name; flat or grouped sensibly.
- [ ] One-line summary, 1–3 line description, examples panel, `See also` line in help.
- [ ] `--json`, `--quiet`, `--verbose` wired via shared parameter group.
- [ ] Output: human → stdout, progress → stderr, errors → stderr.
- [ ] Long-running ops have spinner / bar / multi-stage progress.
- [ ] Run summary card on success with a `Next:` hint.
- [ ] Errors follow the cause / hint / docs shape; "did you mean?" enabled.
- [ ] Confirmations only for destructive ops; `--yes` skip flag wired.
- [ ] Custom tab completers for any flag with a finite value set.
- [ ] Exit codes mapped per section 12.
- [ ] No raw ANSI codes; all colors flow through the theme module.
- [ ] Output is ASCII-safe in the default render (no arrows, em-dashes, or box-drawing emitted by hand).
- [ ] `NO_COLOR=1` and non-TTY both render correctly.
- [ ] Tests cover: default output, `--json`, `--quiet`, error path, exit codes.

If you skipped one and it wasn't a deliberate trade-off, you have rework to do.

---

## Implementation roadmap

This document is the standard. Implementation lands in three slices, each ≤ ~1 day's work, in separate PRs:

**Slice 1 — baseline plumbing:**
- `src/decoy/ui/theme.py` — Rich Theme + token helpers (`success()`, `error()`, etc.).
- `src/decoy/ui/output.py` — shared `--json` / `--quiet` / `--verbose` flag group + `Console` configured for the active mode.
- Wire `decoy --install-completion`.
- Standardize help format on existing `run` and `validate` commands per section 6.
- Tests: valid JSON in `--json`, empty stdout in `--quiet`, ANSI strip with `NO_COLOR=1`.

**Slice 2 — progress, cards, new commands:**
- `src/decoy/ui/progress.py` — spinner, bar, multistage wrappers.
- `src/decoy/ui/card.py` — run-summary Panel.
- `src/decoy/ui/table.py` — Rich Table styled with the theme.
- New: `decoy storm scan`, `decoy forecast recommend`. These are the primary consumers of the new UI components and the test surface for slice 1.

**Slice 3 — polish:**
- `decoy init` (interactive Q&A scaffold).
- `decoy demo` (bundled CSV + 30-second walkthrough).
- Custom tab completers for Disguise IDs, transform IDs, Faker types.

Each slice ships with tests that snapshot rendered output (default + `--json`) so future changes can't regress the visual spec without breaking a test.
