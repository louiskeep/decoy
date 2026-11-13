# decoy-cli

`decoy` is a command-line tool for masking and generating synthetic data.
It is the developer / CI front end for the `decoy-engine` library: you point
it at a YAML pipeline that describes your sources, your tables, and the
strategy for each column, and it produces a masked or synthesized copy of
your data with deterministic, repeatable output.

The CLI is source-available under the Functional Source License
(FSL-1.1-ALv2): use it for anything, including production at your company,
except building a competing product. Each release becomes Apache-2.0 two
years after it ships. See `LICENSE.md` for the full terms and
[`LICENSING.md`](LICENSING.md) for a plain-English FAQ. The CLI runs locally: there is no server,
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
| `ml` | The STORM field-classifier (scikit-learn/lightgbm) | `pip install decoy-cli[ml]` |
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
# Column-aware: STORM scans the file, picks a strategy per column, writes
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
the fast schema-only subset; `decoy report fidelity` recomputes
distribution fidelity between a source and an output CSV after a run.
`decoy run` runs the pipeline and writes the masked output to the path
declared under `targets:` in the YAML.

## Common commands

| Command                          | What it does                                                                  |
|-----------------------------------|-------------------------------------------------------------------------------|
| `decoy demo`                     | Run a packaged end-to-end mask on synthetic input. Good first call.           |
| `decoy init [file]`              | Scaffold a starter `pipeline.yaml`. With a file: column-aware via STORM. Without: prompt for preset (`minimal`, `gdpr`, ...). |
| `decoy validate <path>`          | Run the whole pre-run gate (config + compile + preflight): one report, one exit code. |
| `decoy run <path>`               | Execute a pipeline: read sources, mask, write targets.                        |
| `decoy project new <dir>`        | Make a project folder (`decoy.yaml`, `pipelines/`, `out/`). `decoy project show` and `list` inspect them. |
| `decoy setup`                    | Set this box's max memory and threads (`~/.decoy/settings.json`); `--max-memory` and `--threads` override per run. |
| `decoy tokenize <path>`          | Run the pipeline, replace each `strategy: tokenize` column with a deterministic surrogate, and record the mapping in a local vault. Needs a mask secret. |
| `decoy detokenize <path> <file>` | Reverse a tokenized file from its vault. Fails closed on a missing/wrong vault or namespace. |
| `decoy fit <source.csv>`         | Fit a distribution snapshot of a CSV for `statistical` generate columns. Sensitive columns keep no cell values. |
| `decoy scan <path>...`           | Profile source files, one table each: distributions, PII candidates, cardinality hints. A CSV needs `--has-header` or `--no-header`. |
| `decoy report show <evidence.json>` | The post-run surface: show / verify / fidelity / integrity / diff / vault over run artifacts. |
| `decoy ci check [manifest]`      | Run the checks in a `decoy-ci/v1` manifest and emit one value-free JSON, SARIF 2.1.0, or Markdown report. See [CI integration](#ci-integration). |
| `decoy list templates`           | List the bundled pipeline templates.                                         |
| `decoy show template <name>`     | Dump one bundled template to stdout (e.g. `decoy show template hipaa`).      |
| `decoy explain <topic>`          | In-CLI reference (exit codes, providers, strategies).                         |

Run `decoy --help` for the full surface, or `decoy <command> --help` for
any subcommand.

## Generate synthetic data

A generate table builds rows from column types, with no source rows in the output.

```console
$ decoy init source.csv --preset generate -o pipeline.yaml   # fit the CSV, write config + snapshot
$ decoy run pipeline.yaml --rows 5                            # preview a few rows, writes nothing
$ decoy run pipeline.yaml                                     # generate and write the targets
$ decoy report fidelity source.csv synthetic.csv --generate   # score the output against the source
```

A relative path in the YAML (sources, targets, `snapshot_file`) is read from the folder that holds
the YAML file, whatever the working directory. `global_settings.seed` fixes a plain run; with
`--master-key` the key drives generation and the seed is not used for generated tables. `decoy run`
warns when a generated table scores below `fidelity_warn_threshold`, overall or on any one column.
`decoy explain generation` lists every column type and option the installed engine supports, and
`decoy validate compile pipeline.yaml --explain` shows each generate table, its references and the
order the tables are built in.

## CI integration

`decoy ci check` runs the checks listed in a committed `.decoy-ci.yaml` (full or config-only
validation, saved-scan drift, evidence verification, and an optional bounded scan of
*staged* files for literal seeded identifiers) and writes one report. It uses the exit codes
below, never uploads or comments, and prints no matched value.

```bash
decoy ci check .decoy-ci.yaml --format sarif --output decoy.sarif
```

- **Manifest:** `examples/decoy-ci.yaml`; schema `docs/schemas/decoy-ci-v1.schema.json`.
- **GitHub Actions / GitLab CI:** invoker-only templates in `integrations/`. They need a
  pre-provisioned, pinned `decoy` on the runner; code-scanning upload is an opt-in step you
  configure, not something Decoy does.
- **pre-commit:** add this repository under `repos:` and enable hook `decoy-ci-check`
  (pre-commit >= 4.4.0, a pre-installed `decoy` on `PATH`, no network).
- Full contract, limits, and false-positive behavior: [docs/ci-contracts.md](docs/ci-contracts.md).

## Exit codes

`decoy` returns one of these seven codes. Scripts, Make recipes, and CI
pipelines can switch on the integer; the contract is stable across releases.

| Code | Name                   | Meaning                                                                                    |
|------|------------------------|--------------------------------------------------------------------------------------------|
| 0    | `EXIT_OK`              | Success.                                                                                   |
| 1    | `EXIT_USAGE`           | Usage error: config did not validate, path did not exist, flag combination was invalid, or a `unique` generate column the data cannot satisfy (`uniqueness_impossible`). |
| 2    | `EXIT_WARNINGS`        | The command ran clean except for advisory warnings, and `--fail-on-warning` was set. Also the code for a Click usage error and a bad `--master-key` or `--key-label` on `decoy run`. Returned by `decoy validate config` / `validate preflight` (and the `validate` aggregate). Without `--fail-on-warning` the same run exits 0. |
| 3    | `EXIT_RUNTIME`         | The CLI itself failed mid-run (engine error, output write failure, transient I/O problem). |
| 4    | `EXIT_FINDINGS`        | The CLI ran cleanly but found data issues (e.g. `decoy report integrity` flagged residual PII or FK preservation failures). The fix is in the data being checked, not in the CLI invocation. |
| 5    | `EXIT_CAPACITY`        | `decoy run` or `decoy validate preflight` refused the job: it needs more memory than the host/budget has. The engine decides which refusals count: the out-of-core-FK fan-in and memory gate, a faker pool or reorder budget that is too small, a pool over its cache budget, generated output that cannot fit the machine's memory (`generation_budget_exceeded`), and a process or worker that ran out of memory. A rejected budget setting, a disk or quota limit and a routing refusal keep their usual exit. The fix is a bigger host/cgroup ceiling or a smaller job. `decoy validate preflight`'s v1 check does not cover the ingestion peak. Generated tables whose output cannot fit exit 5 at `decoy validate` and before `decoy run` writes anything; a missing or unreadable source file exits 1 first, so this needs readable sources; a run that runs out of memory exits 5 as well. |
| 6    | `EXIT_PARTIAL`         | `decoy run` delivered some tables and withheld the rest. Reserved for best-effort delivery; no run exits 6 yet. |

Constants live in `decoy.cli.exit_codes`. `decoy explain exit-codes` prints
the same table from the CLI.

## Where to go next

- `examples/` -- runnable mask and generate YAML configs.
- `docs/guides/shape-and-privacy/` -- user guide: check what shape masking
  kept, fit and generate look-alike data, read fidelity reports, and use the
  differential-privacy fit.
- `docs/guides/telemetry/README.md` -- opt-in trace export to your collector: what is
  sent, the closed attribute set and the limits (DP fits, lost spans).
- `src/decoy/templates/` -- the starter templates `decoy init` ships.
- `CHANGELOG.md` -- release notes and the versioning policy.
- `SECURITY.md` -- how to report a vulnerability privately.
- `CONTRIBUTING.md` -- how to build, test, and propose changes.
- `decoy-engine` (PyPI) -- the data-plane library; import it directly if
  you want to embed masking or generation inside your own Python tool
  instead of going through the CLI.

## License

Functional Source License, Version 1.1, Apache 2.0 Future License
(FSL-1.1-ALv2). `decoy-engine` moves to the same license from its first FSL
release onward; engine 0.22.0 and earlier stay Apache-2.0; 0.23.0 and later, including the 0.23.0 this CLI pins
today, are FSL-1.1-ALv2. You may use, modify and
redistribute Decoy for any purpose except a Competing Use: offering it, or
something substantially similar built from it, to others as a commercial
product or service. Internal production use is allowed. Each release
converts to the Apache License 2.0 on the second anniversary of its
release. FSL is source-available, not OSI open source. See `LICENSE.md` for
the full terms, [`LICENSING.md`](LICENSING.md) for a plain-English FAQ, and
`TRADEMARKS.md` for the trademark policy.
