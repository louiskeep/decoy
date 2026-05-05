# decoy — Claude Context

The public CLI tool. A thin Typer wrapper around `decoy-engine`. Contains zero data manipulation logic — if it touches data, it belongs in `decoy-engine`.

**CLI UX standards: read [CLI_UX_GUIDE.md](CLI_UX_GUIDE.md) before adding or modifying a command.**

## Repo structure

```
src/decoy/
├── __main__.py          ← entry point: app = typer.Typer()
├── _deprecated.py       ← `forge` console-script shim (prints rename msg, exits 2)
├── cli/
│   ├── run.py           ← decoy run <config.yaml> [--mode mask|generate|convert]
│   ├── validate.py      ← decoy validate <config.yaml>
│   ├── init.py          ← decoy init (interactive scaffolder)
│   └── demo.py          ← decoy demo (30-second bundled sample)
├── ui/
│   ├── logger.py        ← RichLogger — implements decoy_engine.context.Logger
│   ├── progress.py      ← Rich progress bar
│   └── theme.py         ← colors/styles
├── license/commands.py  ← decoy login, decoy license
├── config/settings.py   ← ~/.decoy/ local config
└── telemetry/client.py  ← opt-in usage events
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
