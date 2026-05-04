# decoy — Developer Reference

## First-time setup

```bash
# decoy-engine must be installed first (it's a dependency)
pip install -e ../forge-engine    # directory still named forge-engine on disk; package is decoy-engine

# Install decoy CLI in editable mode
pip install -e .

# Verify
decoy --help
```

> Both repos should be cloned side-by-side under the same parent directory so the `../forge-engine` path resolves correctly.

## Daily development loop

```bash
# 1. Branch
git checkout -b feature/my-change

# 2. Edit src/decoy/...
# Changes to decoy-engine are live immediately (editable install)

# 3. Test
decoy run examples/mask_example.yaml --mode mask
pytest tests/e2e/

# 4. Commit and push
git add -p
git commit -m "feat: describe the change"
git push -u origin feature/my-change
# Open PR — do not merge without approval
```

## Common commands

```bash
decoy run <config.yaml> --mode mask        # run a masking pipeline
decoy run <config.yaml> --mode generate    # run a generation pipeline
decoy run <config.yaml> --mode convert     # convert file format
decoy validate <config.yaml>               # validate config without running
decoy init                                 # interactive config scaffolder
decoy demo                                 # bundled 30-second sample run
decoy login                                # activate a Business license
decoy license                              # show current license status
decoy --version                            # show version
decoy --help                               # full help
decoy run --help                           # command-specific help
```

`forge ...` still resolves during the deprecation window — it prints the rename message and exits non-zero.

## Testing

```bash
pytest tests/                              # all tests
pytest tests/e2e/ -v                       # verbose E2E (invokes CLI directly)
pytest -k "test_mask"                      # run matching tests
```

E2E tests use Typer's `CliRunner` or `subprocess` — they invoke `decoy` as a real CLI call and check output/exit codes.

## Adding a new CLI command

1. Create (or edit) a file in `src/decoy/cli/`
2. Define a Typer command function
3. Register it in `src/decoy/__main__.py`
4. Any data logic goes in `decoy-engine`, not here — the CLI just calls the engine

## Updating the engine during CLI development

If you need a new `decoy-engine` feature while working on the CLI:
1. Switch to the engine repo, create a feature branch there
2. Implement and test the engine change
3. Come back to `decoy` — the editable install picks it up immediately
4. Open PRs in both repos; note the dependency in the PR description

## Sample YAML configs

`examples/` contains working configs for common scenarios:
- `mask_example.yaml` — basic CSV masking
- `generate_example.yaml` — synthetic data generation
- `fixed_width_example.yaml` — fixed-width file masking
