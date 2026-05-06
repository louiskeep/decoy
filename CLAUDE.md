# decoy — Claude Context

The public CLI tool. A thin Typer wrapper around `decoy-engine`. Contains zero data manipulation logic — if it touches data, it belongs in `decoy-engine`.

**CLI UX standards: read [CLI_UX_GUIDE.md](CLI_UX_GUIDE.md) before adding or modifying a command.**

## Docs in this repo

We use two doc types. Distinguishing them keeps long-term plans aligned and short-term plans from rotting.

- **Guides** are durable specs describing target state. Filename: `*_GUIDE.md`, repo root. Header carries `Status:` (`target` / `partial` / `superseded`) and `Last reviewed:`. When a feature ships, the implementer updates the relevant guide in the same PR.
- **Plans** are transient, scoped to a PR or sprint. Live in `plans/`, dated. Header carries `Status:` (`planning` / `in-progress` / `shipped` / `abandoned`), `Branch:`, and `References:` (the guides being implemented). Once a plan ships, it can be deleted — git history is the archive.

Orientation files (this `CLAUDE.md`, `dev-help.md`, `README.md`) are conventional contributor entry points and stay outside the guide/plan taxonomy.

## Comment style

Comments explain what a section / code block does in good detail, in **1–2 sentences**. Reach for more only when the block is genuinely complex — a state machine, a non-obvious algorithm, security-sensitive math, a workaround for a specific bug. Default mode: terse and to the point.

- **Yes:** `# Format inference is the whole point — pandas warns when it falls back to dateutil; suppress.`
- **No:** silent code with no context.
- **No:** restating what the next ten lines obviously do.

Comments live next to the surprise, not at the top of the file. If the non-obvious thing is the *why*, write that, not the *what*.

### Active guides

- [CLI_UX_GUIDE.md](CLI_UX_GUIDE.md) — CLI UX standards & practices. *(partial)*
- [PIPELINE_GRAPH_GUIDE.md](PIPELINE_GRAPH_GUIDE.md) — CLI-side mirror of the cross-repo graph pipeline contract; `decoy run/validate` dispatch. *(target)*

The CLI's planned `RichLogger` (Slice F in [`../forge-platform/LOGGING_GUIDE.md`](../forge-platform/LOGGING_GUIDE.md) section 10) bridges `decoy.ui.output.OutputState` to the engine's `Logger` Protocol so engine narration surfaces in the terminal. Until that slice ships, `decoy run` invokes the engine without a logger and runs silent from the CLI's perspective.

## Repo structure

```
src/decoy/
├── __main__.py          ← entry point: app = typer.Typer()
├── _deprecated.py       ← `forge` console-script shim (prints rename msg, exits 2)
├── cli/
│   ├── run.py           ← decoy run <config.yaml> [--mode mask|generate|convert]
│   ├── validate.py      ← decoy validate <config.yaml>
│   ├── storm.py         ← decoy storm scan <csv> -- STORM analysis
│   ├── forecast.py      ← decoy forecast recommend <scan.json>
│   ├── init.py          ← decoy init (interactive scaffolder)
│   ├── demo.py          ← decoy demo (bundled scan→forecast→mask walkthrough)
│   └── completers.py    ← tab-completion sources (Disguises, transforms, Faker)
└── ui/
    ├── theme.py         ← semantic color tokens (success, error, hint, ...)
    ├── output.py        ← OutputState + --json/--quiet/--verbose plumbing
    ├── progress.py      ← spinner / progress_bar / multistage wrappers
    ├── card.py          ← run-summary Panel
    └── table.py         ← Rich Table styled with the theme
examples/                ← sample YAML pipeline configs
tests/e2e/               ← CLI invocation tests (CliRunner or subprocess)
```

## What is NOT in this repo

- Masking/generation logic → `decoy-engine` (dependency)
- Web platform, auth, scheduling → `decoy-platform`
- Marketing site → `decoy-web`

**Decision rule:** "Does this manipulate data?" → belongs in `decoy-engine`, not here.

## Key pattern: Logger injection

The CLI never calls `print()` or `logging` directly in CLI commands. It constructs a `RichLogger` (which implements `decoy_engine.context.Logger`) and passes it through `ExecutionContext` to the engine:

```python
from decoy_engine import Masker, ExecutionContext
from decoy.ui.logger import RichLogger

ctx = ExecutionContext(logger=RichLogger(verbose=verbose))
Masker(config_path).mask(ctx)
```

## Setup

```bash
pip install -e ../forge-engine   # directory still named forge-engine on disk; package is decoy-engine
pip install -e .
```

## Run

```bash
decoy --help
decoy run examples/mask_example.yaml --mode mask
decoy validate examples/mask_example.yaml
decoy demo
```

`forge ...` still resolves while the deprecation shim is in place; it prints the rename message and exits non-zero.

## Tests

```bash
pytest tests/
pytest tests/e2e/ -v             # verbose E2E output
```

## Branch workflow

**Never commit directly to `main`.** All work on a feature branch.

```bash
git checkout -b feature/your-feature-name
# work, commit
# open PR -> wait for approval before merging
```

Branch naming: `feature/`, `fix/`, `chore/`
