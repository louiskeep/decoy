# decoy

**Public.** The free Decoy CLI tool — `pip install decoy`.

## What lives here

- Typer-based CLI commands (`decoy run`, `decoy validate`, `decoy init`, `decoy demo`)
- Rich terminal UI (`decoy.ui`)
- License verification (`decoy login`, `decoy license`)
- Sample pipeline configs (`examples/`)
- End-to-end CLI tests

## What does NOT live here

- Data manipulation logic → `decoy-engine` (the engine is a dependency, not duplicated here)
- Web platform → `decoy-platform`
- Marketing site → `decoy-web`

## Dev setup

```bash
# Install engine as editable dep (local dev only)
pip install -e ../forge-engine    # directory still named forge-engine on disk
pip install -e .

decoy run examples/mask_example.yaml --mode mask
```

## License

BUSL-1.1 — see [LICENSE.md](LICENSE.md). Auto-converts to Apache 2.0 after 4 years.
