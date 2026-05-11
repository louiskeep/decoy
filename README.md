# decoy

**Public.** The free Decoy CLI tool — `pip install decoy`.

Decoy is a Typer-based command-line tool for masking real datasets and
generating synthetic ones. It is a thin terminal wrapper over
`decoy-engine`; this repo owns the command surface, the Rich-based
terminal UX, the bundled starter pipelines, and the end-to-end CLI
tests. All data logic lives in the engine.

## What lives here

Nine commands, grouped by what they do:

**Execute a pipeline**
- `decoy run <pipeline.yaml>` — mask, generate, convert, or run a graph.
- `decoy validate <pipeline.yaml>` — schema-check a YAML before running.
- `decoy init` — interactive wizard that scaffolds a starter pipeline.
- `decoy demo` — bundled scan → forecast → mask walkthrough.

**Analyze a dataset (the STORM / FORECAST pair)**
- `decoy storm scan <data.csv>` — profile a dataset for PII, sentinels,
  and re-identification risk; saves a JSON profile.
- `decoy forecast recommend <scan.json>` — recommend a Disguise and
  draft a pipeline YAML from a saved STORM profile.

**Discover what's available**
- `decoy templates list` / `decoy templates show <name>` — browse and
  print the bundled starter pipelines (`minimal`, `hipaa`, `pci`,
  `gdpr`, `generate`, `graph`).
- `decoy explain <topic>` — plain-English topic help (modes, transforms,
  disguises, output, pipeline, storm, forecast, keys, completion).
- `decoy info` — branded splash + quick-start hints.

Every command also accepts the standard `--json`, `--quiet`, and
`--verbose` flags. `decoy run` additionally accepts `--master-key`
(or `DECOY_MASTER_KEY`) and `--key-label` for keyed deterministic
masking — same key + same label always yields bitwise-identical
output across runs and machines.

## What does NOT live here

- Data manipulation logic → `decoy-engine` (the engine is a dependency,
  not duplicated here)
- Web platform → `decoy-platform`
- Marketing site → `decoy-web`

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the system map
and module overview. The CLI UX standards every command follows are in
[`CLI_UX_GUIDE.md`](CLI_UX_GUIDE.md).

## Quick start

```bash
pip install decoy

# 1. Scan a dataset to see what's in it.
decoy storm scan data.csv

# 2. Recommend a Disguise + draft a pipeline.
decoy forecast recommend scan_*.json

# 3. Validate the draft, then run it.
decoy validate forecast_*.pipeline.yaml
decoy run forecast_*.pipeline.yaml
```

Or scaffold from a template:

```bash
decoy templates list
decoy templates show hipaa > pipeline.yaml
decoy run pipeline.yaml
```

## Dev setup

```bash
# Install engine as editable dep (local dev only); clone decoy-engine
# next to this repo.
pip install -e ../decoy-engine
pip install -e .

decoy run examples/mask_example.yaml
```

See [dev-help.md](dev-help.md) for the daily loop, test invocation, and
the "adding a new CLI command" walkthrough.

## License

Source-available under the Business Source License 1.1 (BUSL-1.1) — see [LICENSE.md](LICENSE.md). The Change License is Apache License, Version 2.0, effective on the Change Date `2030-05-10` (or four years from first publication, whichever comes first).

Use of the "Decoy" name and marks is governed by [TRADEMARKS.md](TRADEMARKS.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Contributions require a DCO sign-off (`git commit -s`) and are licensed under BUSL-1.1. Security issues: see [SECURITY.md](SECURITY.md).
