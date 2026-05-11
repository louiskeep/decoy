# decoy — Developer Reference

## First-time setup

```bash
# decoy-engine must be installed first (it's a dependency)
pip install -e ../decoy-engine

# Install decoy CLI in editable mode
pip install -e .

# Verify
decoy --help
```

> Both repos should be cloned side-by-side under the same parent
> directory so the `../decoy-engine` path resolves correctly.

## Daily development loop

```bash
# 1. Branch
git checkout -b feature/my-change

# 2. Edit src/decoy/...
# Changes to decoy-engine are live immediately (editable install)

# 3. Test
decoy run examples/mask_example.yaml
pytest tests/e2e/

# 4. Commit and push
git add -p
git commit -m "feat: describe the change"
git push -u origin feature/my-change
# Open PR — do not merge without approval
```

## Common commands

```bash
# Pipeline execution
decoy run <config.yaml>                    # mode read from YAML; defaults to mask
decoy run <config.yaml> --mode generate    # back-compat: override when YAML omits mode
decoy validate <config.yaml>               # validate config without running
decoy init                                 # interactive config scaffolder
decoy init --preset hipaa                  # skip the wizard; scaffold from a template
decoy demo                                 # bundled scan->forecast->mask walkthrough

# Dataset analysis (STORM / FORECAST)
decoy storm scan <csv>                     # PII / sentinel / re-id risk scan
decoy forecast <scan.json>                 # pick a Disguise + draft a pipeline
decoy storm scan data.csv --json | decoy forecast -   # streamed

# Discoverability
decoy templates list                       # browse bundled starter pipelines
decoy templates show <name>                # print template YAML to stdout
decoy explain <topic>                      # plain-English topic help
decoy info                                 # branded splash + quick-start hints

# Plumbing
decoy --install-completion                 # install shell tab completion
decoy --version                            # show version
decoy --help                               # full help
decoy run --help                           # command-specific help
```

Every command also takes the standard `--json`, `--quiet`, `--verbose`
flags documented in [CLI_UX_GUIDE.md](CLI_UX_GUIDE.md) section 4.

### Keyed deterministic masking

`decoy run` accepts `--master-key <hex>` (or the `DECOY_MASTER_KEY` env
var) plus `--key-label <str>` to produce bitwise-identical masked output
across runs and machines. Without either, masking falls back to the
legacy seeded path (per-input deterministic but not portable).

```bash
# Generate a master key once, store it in your secret manager.
python -c 'import secrets; print(secrets.token_hex(32))'

# Per run: the same key + same label always produces the same output.
export DECOY_MASTER_KEY=<hex>
decoy run pipeline.yaml --key-label customers_q4

# Or set key_label at the top of the YAML and skip the flag.
```

The deprecated `forge ...` command still resolves during the deprecation
window — it prints the rename message and exits non-zero.

## Testing

```bash
pytest tests/                              # all tests
pytest tests/e2e/ -v                       # verbose E2E (invokes CLI directly)
pytest -k "test_mask"                      # run matching tests
```

E2E tests use Typer's `CliRunner` or `subprocess` — they invoke `decoy`
as a real CLI call and check output/exit codes.

## Adding a new CLI command

**Before you start: read [CLI_UX_GUIDE.md](CLI_UX_GUIDE.md).** It covers
help format, color tokens, output modes (`--json` / `--quiet` /
`--verbose`), progress patterns, run summary cards, error UX, exit codes,
tab completion, and the explicit list of things the CLI is NOT for. The
end-of-doc checklist is the gate before opening a PR.

1. Create (or edit) a file in `src/decoy/cli/`
2. Define a Typer command function
3. Register it in `src/decoy/__main__.py`
4. Any data logic goes in `decoy-engine`, not here — the CLI just calls
   the engine
5. Walk the CLI_UX_GUIDE.md checklist before opening the PR.

## Updating the engine during CLI development

If you need a new `decoy-engine` feature while working on the CLI:
1. Switch to the engine repo, create a feature branch there
2. Implement and test the engine change
3. Come back to `decoy` — the editable install picks it up immediately
4. Open PRs in both repos; note the dependency in the PR description

## Sample YAML configs

`examples/` contains working configs for common scenarios:
- `mask_example.yaml` — basic CSV masking, demonstrates every transform
- `generate_example.yaml` — synthetic data generation with relationships
- `fixed_width_example.yaml` — fixed-width file masking
- `graph_example.yaml` — graph-mode pipeline (multi-step DAG)

The shorter, opinionated starter pipelines bundled with the package
live in `src/decoy/templates/` and are surfaced via `decoy templates`.
