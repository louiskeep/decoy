# decoy-cli

`decoy` is a command-line tool for masking and generating synthetic data.
It is the developer / CI front end for the `decoy-engine` library: you point
it at a YAML pipeline that describes your sources, your tables, and the
strategy for each column, and it produces a masked or synthesized copy of
your data with deterministic, repeatable output.

The CLI is source-available under the Business Source License 1.1 (BUSL-1.1):
source is readable, non-commercial and internal-business use is permitted by
the Additional Use Grant, and commercial competing-service use is restricted.
The license auto-converts to Apache-2.0 on the Change Date (2030-05-10). See
`LICENSE.md` for the full terms. The CLI runs locally: there is no server,
no account, no telemetry phone-home. Input data and output data stay on your
machine.

## Install

```
pip install decoy-cli
```

This installs the `decoy` console script and pulls in `decoy-engine` as a
dependency. Python 3.10, 3.11, and 3.12 are supported.

## Quickstart

Run the bundled demo (no config, no setup) to see a full mask + report
end to end:

```
decoy demo
```

Scaffold your first pipeline against your own CSV. Two paths:

```
# Column-aware: STORM scans the file, picks a strategy per column, writes
# the YAML with `# REVIEW:` comments above every auto-inferred entry.
decoy init customers.csv --out pipeline.yaml
# read the REVIEW comments + edit anything you disagree with
decoy validate config pipeline.yaml
decoy run pipeline.yaml
```

```
# Template-driven: scaffold from a bundled preset (minimal, hipaa, pci, gdpr).
decoy init --preset minimal --out pipeline.yaml
# edit pipeline.yaml: point `sources.people.path` at your CSV
decoy validate config pipeline.yaml
decoy run pipeline.yaml
```

`decoy validate config` checks the YAML against the engine's pipeline
schema without touching your data. `decoy validate distribution` recomputes
distribution fidelity between a source and an output CSV after a run.
`decoy run` runs the pipeline and writes the masked output to the path
declared under `targets:` in the YAML.

## Common commands

| Command                          | What it does                                                                  |
|-----------------------------------|-------------------------------------------------------------------------------|
| `decoy demo`                     | Run a packaged end-to-end mask on synthetic input. Good first call.           |
| `decoy init [file]`              | Scaffold a starter `pipeline.yaml`. With a file: column-aware via STORM. Without: prompt for preset (`minimal`, `gdpr`, ...). |
| `decoy validate config <path>`   | Validate a pipeline YAML against the engine schema. Exits non-zero on error.  |
| `decoy validate distribution <source> <output>` | Recompute distribution fidelity between a source and an output CSV. |
| `decoy run <path>`               | Execute a pipeline: read sources, mask, write targets.                        |
| `decoy storm analyze <path>`     | Profile a source file: distributions, PII candidates, cardinality hints.      |
| `decoy templates list`           | List the bundled pipeline templates.                                         |
| `decoy explain <topic>`          | In-CLI reference (exit codes, providers, strategies).                         |

Run `decoy --help` for the full surface, or `decoy <command> --help` for
any subcommand.

## Exit codes

`decoy` returns one of these five codes. Scripts, Make recipes, and CI
pipelines can switch on the integer; the contract is stable across releases.

| Code | Name                   | Meaning                                                                                    |
|------|------------------------|--------------------------------------------------------------------------------------------|
| 0    | `EXIT_OK`              | Success.                                                                                   |
| 1    | `EXIT_USAGE`           | Usage error: config did not validate, path did not exist, flag combination was invalid.    |
| 2    | `EXIT_DEPRECATED_SHIM` | The legacy `forge` console entry point was invoked; migrate to `decoy ...`.                |
| 3    | `EXIT_RUNTIME`         | The CLI itself failed mid-run (engine error, output write failure, transient I/O problem). |
| 4    | `EXIT_FINDINGS`        | The CLI ran cleanly but found data issues (e.g. `decoy storm integrity` flagged residual PII or FK preservation failures). The fix is in the data being checked, not in the CLI invocation. |

Constants live in `decoy.cli.exit_codes`. `decoy explain exit-codes` prints
the same table from the CLI.

## Where to go next

- `examples/` -- runnable mask and generate YAML configs.
- `src/decoy/templates/` -- the starter templates `decoy init` ships.
- `CHANGELOG.md` -- release notes and the versioning policy.
- `SECURITY.md` -- how to report a vulnerability privately.
- `CONTRIBUTING.md` -- how to build, test, and propose changes.
- `decoy-engine` (PyPI) -- the data-plane library; import it directly if
  you want to embed masking or generation inside your own Python tool
  instead of going through the CLI.

## License

Business Source License 1.1 (BUSL-1.1). The source is readable, internal and
non-commercial use is permitted, and competing-service use is restricted by
the Additional Use Grant. The license auto-converts to Apache License 2.0
on the Change Date (2030-05-10). BUSL-1.1 is source-available, not OSI
open-source. See `LICENSE.md` for the full terms and `TRADEMARKS.md` for
the trademark policy.
