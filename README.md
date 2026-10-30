# decoy-cli

`decoy` is a command-line tool for masking and generating synthetic data.
It is the developer / CI front end for the `decoy-engine` library: you point
it at a YAML pipeline that describes your sources, your tables, and the
strategy for each column, and it produces a masked or synthesized copy of
your data with deterministic, repeatable output.

A pipeline has three named phases, and each makes a different claim:

```text
Pre-scan                 Transform            Post-scan
profile / detect   ->    mask / generate  ->  check the result
decoy pre-scan           decoy run            decoy post-scan
```

Pre-scan flags candidate sensitive fields for you to review. Transform applies
masking or generation. Post-scan reports integrity findings and distribution
fidelity on the output. Detection candidates, fidelity, artifact integrity
(`decoy report verify`) and a release decision are four different things; none
of them stands in for another, and fidelity is not a privacy guarantee.

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
dependency. Python 3.10, 3.11, and 3.12 are supported. The base install is
the full local masker + generator (CSV/Parquet, DuckDB, the pandas/polars/
pyarrow data plane) with no extras to think about.

For an isolated install that never collides with your other Python
environments, use `uv` or `pipx` instead of a bare `pip install`:

```
uv tool install decoy-cli
# or
pipx install decoy-cli
```

### Extras

A few heavier capabilities are opt-in, so the default install stays lean:

| Extra | Adds | Install |
|-------|------|---------|
| `cloud` | The S3 / GCS SDK dependencies (`boto3`, `google-cloud-storage`) | `pip install decoy-cli[cloud]` |
| `ner` | spaCy-based PII autodetect for `text_mask`/`text_redact` | `pip install decoy-cli[ner]` |
| `ml` | The Pre-scan field-classifier (scikit-learn/lightgbm) | `pip install decoy-cli[ml]` |
| `vault` | Compatibility alias only; installs nothing extra (see note below) | `pip install decoy-cli[vault]` |
| `all` | Every extra above | `pip install decoy-cli[all]` |

You don't need to plan ahead: run a pipeline that needs one of these without
it installed and `decoy` fails closed with the exact install line, not a
raw traceback. `ner` also needs a downloaded spaCy model, a separate step:
`python -m spacy download en_core_web_sm`.

`decoy run` does not read from or write to S3/GCS yet -- `cloud` installs
the SDK dependencies for other tooling in the stack, but the CLI's own
execution path only reads/writes local files, and a config that points a
`decoy run` source or target at S3/GCS fails closed with a clear error
rather than silently dropping the job's output.

Reversible tokenization is wired: `decoy tokenize <pipeline>` replaces each
`strategy: tokenize` column with a deterministic surrogate and records the
(namespace, plaintext) -> token mapping in a local SQLite vault, and `decoy
detokenize <pipeline> <file>` reverses it from that vault. A mask secret is
required (via `--mask-secret` or `global_settings.mask_secret_ref`). The vault
is the full re-identification map and is cleartext at rest (created `0600`), so
keep it off shared storage and treat it as sensitive. The `vault` extra is a
compatibility alias that installs nothing extra; the commands need no extra.

## Quickstart

Run the bundled demo (no config, no setup) to see a full mask + report
end to end:

```
decoy demo
```

Scaffold your first pipeline against your own CSV. Two paths:

```
# Column-aware: Pre-scan profiles the file, picks a strategy per column, writes
# the YAML with `# REVIEW:` comments above every auto-inferred entry.
decoy init customers.csv --output pipeline.yaml
# read the REVIEW comments + edit anything you disagree with
decoy validate pipeline.yaml
decoy run pipeline.yaml
```

```
# Template-driven: scaffold from a bundled preset (minimal, hipaa, pci, gdpr).
decoy init --preset minimal --output pipeline.yaml
# edit pipeline.yaml: point `sources.people.path` at your CSV
decoy validate pipeline.yaml
decoy run pipeline.yaml
```

`decoy validate pipeline.yaml` runs the whole pre-run gate -- config schema,
plan compile, and source/capacity preflight -- in one pass, with one report
grouped by layer and one aggregated exit code. `decoy validate config` runs
the fast schema-only subset; `decoy post-scan fidelity` recomputes
distribution fidelity between a source and an output CSV after a run
(a similarity measurement, not a privacy guarantee).
`decoy run` runs the pipeline and writes the masked output to the path
declared under `targets:` in the YAML.

## Common commands

| Command                          | What it does                                                                  |
|-----------------------------------|-------------------------------------------------------------------------------|
| `decoy demo`                     | Run a packaged end-to-end mask on synthetic input. Good first call.           |
| `decoy init [file]`              | Scaffold a starter `pipeline.yaml`. With a file: column-aware via Pre-scan. Without: prompt for preset (`minimal`, `gdpr`, ...). |
| `decoy validate <path>`          | Run the whole pre-run gate (config + compile + preflight): one report, one exit code. |
| `decoy run <path>`               | Execute a pipeline: read sources, mask, write targets.                        |
| `decoy tokenize <path>`          | Run the pipeline, replace each `strategy: tokenize` column with a deterministic surrogate, and record the mapping in a local vault. Needs a mask secret. |
| `decoy detokenize <path> <file>` | Reverse a tokenized file from its vault. Fails closed on a missing/wrong vault or namespace. |
| `decoy pre-scan <path>`          | Pre-scan: profile a source file (distributions, PII candidates as suggestions, cardinality hints). Subcommands: `fields`, `show`, `diff` on a saved profile. |
| `decoy post-scan integrity <masked> --source <src>` | Post-scan: residual-PII / FK / policy findings on a masked file. Report-only; not a release decision. |
| `decoy post-scan fidelity <src> <out>` | Post-scan: distribution similarity between source and output. A measurement, not a privacy guarantee. |
| `decoy report show <evidence.json>` | The run-artifact surface: show / render / verify / diff / vault. `verify` checks artifact fingerprints, not privacy. |
| `decoy list templates`           | List the bundled pipeline templates.                                         |
| `decoy show template <name>`     | Dump one bundled template to stdout (e.g. `decoy show template hipaa`).      |
| `decoy explain <topic>`          | In-CLI reference (exit codes, providers, strategies).                         |

Run `decoy --help` for the full surface, or `decoy <command> --help` for
any subcommand.

**Pre-scan and Post-scan output is value-free.** Every printed surface of
`decoy pre-scan` and `decoy post-scan` (stdout, `--json`, `--output -`,
`--report-out`, errors, `--verbose`) carries no cell values, file paths, table
names or free-text diagnostics; policed column names (at most 64 characters of
`[A-Za-z0-9_ .-]`) are shown. The one exception is explicit:
**`decoy pre-scan SOURCE --output FILE` writes the full scan profile including
sample top values and sentinels** (owner-only, mode 0600, source path not
recorded). Protect that file like the source, or use `--json` / `--output -`
for the value-free projection.

## Exit codes

`decoy` returns one of these six codes. Scripts, Make recipes, and CI
pipelines can switch on the integer; the contract is stable across releases.

| Code | Name                   | Meaning                                                                                    |
|------|------------------------|--------------------------------------------------------------------------------------------|
| 0    | `EXIT_OK`              | Success.                                                                                   |
| 1    | `EXIT_USAGE`           | Usage error: config did not validate, path did not exist, flag combination was invalid.    |
| 2    | `EXIT_WARNINGS`        | The command ran clean except for advisory warnings, and `--fail-on-warning` was set. Returned by `decoy validate config` / `validate preflight` (and the `validate` aggregate). Without `--fail-on-warning` the same run exits 0. |
| 3    | `EXIT_RUNTIME`         | The CLI itself failed mid-run (engine error, output write failure, transient I/O problem). |
| 4    | `EXIT_FINDINGS`        | The CLI ran cleanly but found data issues (e.g. `decoy post-scan integrity` flagged residual PII or FK preservation failures). The fix is in the data being checked, not in the CLI invocation. |
| 5    | `EXIT_CAPACITY`        | `decoy run` or `decoy validate preflight` refused the job: it needs more memory than the host/budget has (the engine's out-of-core-FK memory gate). The fix is a bigger host/cgroup ceiling or a smaller job. `decoy validate preflight`'s v1 check covers the out-of-core-FK route only, not the ingestion peak or the generate path. |

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
