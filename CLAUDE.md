# forge — Claude Context

The public CLI tool. A thin Typer wrapper around `forge-engine`. Contains zero data manipulation logic — if it touches data, it belongs in `forge-engine`.

## Repo structure

```
src/forge/
├── __main__.py          ← entry point: app = typer.Typer()
├── cli/
│   ├── run.py           ← forge run <config.yaml> [--mode mask|generate|convert]
│   ├── validate.py      ← forge validate <config.yaml>
│   ├── init.py          ← forge init (interactive scaffolder)
│   └── demo.py          ← forge demo (30-second bundled sample)
├── ui/
│   ├── logger.py        ← RichLogger — implements forge_engine.context.Logger
│   ├── progress.py      ← Rich progress bar
│   └── theme.py         ← colors/styles
├── license/commands.py  ← forge login, forge license
├── config/settings.py   ← ~/.forge/ local config
└── telemetry/client.py  ← opt-in usage events
examples/                ← sample YAML pipeline configs
tests/e2e/               ← CLI invocation tests (CliRunner or subprocess)
```

## What is NOT in this repo

- Masking/generation logic → `forge-engine` (dependency)
- Web platform, auth, scheduling → `forge-platform`
- Marketing site → `forge-web`

**Decision rule:** "Does this manipulate data?" → belongs in `forge-engine`, not here.

## Key pattern: Logger injection

The CLI never calls `print()` or `logging` directly in CLI commands. It constructs a `RichLogger` (which implements `forge_engine.context.Logger`) and passes it through `ExecutionContext` to the engine:

```python
from forge_engine import Pipeline, PipelineConfig, ExecutionContext
from forge.ui.logger import RichLogger

ctx = ExecutionContext(logger=RichLogger(verbose=verbose))
Pipeline(PipelineConfig.from_yaml(config)).run(ctx)
```

## Setup

```bash
pip install -e ../forge-engine   # local dev: editable engine
pip install -e .
```

## Run

```bash
forge --help
forge run examples/mask_example.yaml --mode mask
forge validate examples/mask_example.yaml
forge demo
```

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
# open PR → wait for approval before merging
```

Branch naming: `feature/`, `fix/`, `chore/`
