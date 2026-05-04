# forge

**Public.** The free Forge CLI tool — `pip install forge`.

## What lives here

- Typer-based CLI commands (`forge run`, `forge validate`, `forge init`, `forge demo`)
- Rich terminal UI (`forge.ui`)
- License verification (`forge login`, `forge license`)
- Sample pipeline configs (`examples/`)
- End-to-end CLI tests

## What does NOT live here

- Data manipulation logic → `forge-engine` (the engine is a dependency, not duplicated here)
- Web platform → `forge-platform`
- Marketing site → `forge-web`

## Dev setup

```bash
# Install engine as editable dep (local dev only)
pip install -e ../forge-engine
pip install -e .

forge run examples/mask_example.yaml --mode mask
```

## License

BUSL-1.1 — see [LICENSE.md](LICENSE.md). Auto-converts to Apache 2.0 after 4 years.
