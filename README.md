# decoy

Decoy masks real data and generates synthetic data for test environments. You describe a
pipeline in YAML, and `decoy` writes a masked or generated copy that is repeatable: the same
input, seed and keys give the same output. `decoy` is the command-line front end for the
[`decoy-engine`](https://github.com/decoy-data/decoy-engine) library. It is for one person or one
CI job on one machine.

The CLI is source-available under the Functional Source License
(FSL-1.1-ALv2): use it for anything, including production at your company,
except building a competing product. Each release becomes Apache-2.0 two
years after it ships. See `LICENSE.md` for the full terms and
[`LICENSING.md`](LICENSING.md) for a plain-English FAQ.

`decoy` runs locally. There is no server and no account. Your input and output data stay on
your machine. A once-a-day update check sends no data and you can turn it off. Trace export
is opt-in ([telemetry guide](docs/guides/telemetry/README.md)).

## Status

The CLI is at version 0.1.0 on `main`. Version 1.0.0 is the first release. Its target is the end
of December 2026. The full list of work for 1.0.0, with the state of each row, is in
[docs/ROADMAP.md](docs/ROADMAP.md) (section 5). Version 1 covers the CLI and the engine for one
user. The team server (the platform) is parked until after the CLI ships.

A pipeline runs these steps in order:

1. Read the source files.
2. Subset the rows (optional). Related rows stay together.
3. Pre-scan (optional). It finds sensitive columns.
4. Mask or generate, one table at a time.
5. Post-scan. It checks the output for leaks and for fidelity.
6. Deliver the finished output to the targets.

The token vault (reversible tokens) and CI checks are part of version 1. The threat model for
version 1 is accidental leaks. It does not defend against a hostile process on the same host.

Some of this is not on `main` yet. Planned and in progress, with their roadmap rows:

- Reading from and writing to S3 and GCS (row 64). Today a source or target on S3 or GCS is refused with a clear error.
- Stage-then-deliver output (row 61) and `decoy run --sample N` (row 63).
- The guided `decoy init` wizard (row 32b).
- Scans over many tables with saved snapshots (rows 27 to 30).
- More generate types, relations and a catalog command (rows 24n to 24s).

## Install

Decoy ships as a signed bundle for Linux and macOS: a managed Python, the matching engine, the
native Rust companion and the CLI. One command installs it and puts `decoy` on your `PATH`:

```sh
curl -LsSf https://decoy.dev/cli/install.sh | sh
decoy --version
decoy doctor
```

Supported targets are `linux-x86_64`, `linux-aarch64` and `macos-arm64`. Windows and Intel Macs are
not supported at launch. The install takes about 600 MB. The installer checks the checksum and the
Ed25519 signature of the bundle before it changes anything. Upgrade and rollback use
`decoy upgrade`. [docs/install.md](docs/install.md) has the offline install, uninstall and
upgrade steps.

To work on the CLI itself, install from a clone. See [CONTRIBUTING.md](CONTRIBUTING.md):

```sh
git clone https://github.com/decoy-data/decoy && cd decoy
pip install -e ".[dev]"
```

The source package has optional extras: `cloud` (S3 and GCS SDKs), `ner` (spaCy detection for
`text_mask` and `text_redact`; install it with `decoy models install ner`, which also installs the
pinned model) and `otel` (trace export). If a pipeline needs an extra that is missing, `decoy`
stops and prints the exact install line.

## First run

Run the bundled demo. It needs no config and writes to `./decoy_demo/`:

```sh
decoy demo
```

Then mask your own CSV. `decoy init` scans the file, picks a strategy for each column and writes
the YAML with a `# REVIEW:` comment above every guess. Read those comments and edit the file
before you run it:

```sh
decoy init customers.csv --output pipeline.yaml
decoy validate pipeline.yaml
decoy run pipeline.yaml
```

`decoy validate` runs the full pre-run gate (config schema, plan compile and source preflight) and
gives one report and one exit code. `decoy run` writes the masked output to the path under
`targets:`. To start from a template, use `decoy init --preset minimal --output pipeline.yaml`. The
presets are `minimal`, `hipaa`, `pci`, `gdpr` and `generate`. The file
[`examples/mask_example.yaml`](examples/mask_example.yaml) is a complete mask pipeline.

## Common commands

| Command                          | What it does                                                                  |
|-----------------------------------|-------------------------------------------------------------------------------|
| `decoy demo`                     | Run a packaged end-to-end mask on synthetic input.                            |
| `decoy init [name\|file]`        | Write a starter `pipeline.yaml`, from a data file or from a preset (`-o FILE` writes anywhere). |
| `decoy validate <path>`          | Run the full pre-run gate: one report, one exit code.                        |
| `decoy run <path>`               | Run a pipeline: read sources, mask or generate, write targets. `--all` runs every pipeline of a project. |
| `decoy project new <dir>`        | Make a project folder (`decoy.yaml`, `pipelines/`, `out/`). `decoy project show` and `list` inspect projects. |
| `decoy setup`                    | Set the maximum memory and threads for this machine. `--max-memory` and `--threads` override one run. |
| `decoy models list`              | Show which detector models can run here; `decoy models install ner` installs spaCy and the pinned model. |
| `decoy tokenize <path>`          | Replace each `strategy: tokenize` column with a deterministic surrogate. Record the mapping in a local vault. A mask secret is required. |
| `decoy detokenize <path> <file>` | Reverse a tokenized file from its vault. Fails closed on a missing or wrong vault. |
| `decoy fit <source.csv>`         | Fit a distribution snapshot of a CSV for `statistical` generate columns. Sensitive columns keep no cell values. |
| `decoy scan <path>...`           | Profile source files: distributions, PII candidates, cardinality hints. A CSV needs `--has-header` or `--no-header`. |
| `decoy report show <evidence.json>` | The post-run surface: `show`, `verify`, `fidelity`, `integrity`, `diff` and `vault` over run artifacts. |
| `decoy ci check [manifest]`      | Run the checks in a `decoy-ci/v1` manifest and write one value-free JSON, SARIF 2.1.0 or Markdown report. |
| `decoy library fsck`             | Check the project's record library (`.decoy/library`). `decoy library path` shows where it is. |
| `decoy list templates`           | List the bundled pipeline templates.                                          |
| `decoy show template <name>`     | Print one bundled template, for example `decoy show template hipaa`.          |
| `decoy explain <topic>`          | In-CLI reference: exit codes, providers, strategies, generation.              |

Six more commands are not in the table. `decoy subset` cuts a foreign-key-complete subset of
Parquet tables (use `--dry-run` first). `decoy unmask` recovers `fpe` columns from a masked file.
`decoy doctor` checks the runtime. `decoy upgrade` upgrades or rolls back. `decoy info` and
`decoy schema` print the banner and the pipeline JSON Schema. Every flag is in the generated
[command reference](docs/cli-reference.md). `decoy --help` and `decoy <command> --help` show the
same text.

Sources are local CSV, Parquet and fixed-width files, and DuckDB tables through
`decoy run --duckdb-source TABLE=DB_PATH`. Targets are local files.

## Reversible tokens

`decoy tokenize <pipeline>` replaces each `strategy: tokenize` column with a deterministic
surrogate and records the (namespace, plaintext) to token mapping in a local SQLite vault.
`decoy detokenize <pipeline> <file>` reverses it. Both need a mask secret, given with
`--mask-secret` or `global_settings.mask_secret_ref`. The vault is the full re-identification
map. Keep it off shared storage and treat it as sensitive.

## Generate synthetic data

A generate table builds rows from column types. No source rows reach the output.

```console
$ decoy init source.csv --preset generate -o pipeline.yaml   # fit the CSV, write config + snapshot
$ decoy run pipeline.yaml --rows 5                            # preview a few rows, writes nothing
$ decoy run pipeline.yaml                                     # generate and write the targets
$ decoy report fidelity source.csv synthetic.csv --generate   # score the output against the source
```

[`examples/generate_example.yaml`](examples/generate_example.yaml) is a complete generate
pipeline. Most column kinds stream, so a large table does not need to fit in memory. `unique`
columns and columns with `min_per_parent` or `max_per_parent` are held in memory. If they exceed
the memory budget, the run stops before it writes anything and exits 5. A relative path in the
YAML is read from the folder that holds the YAML file. `global_settings.seed` fixes a plain run.
With `--master-key`, the key drives generation and the seed is not used for generated tables.
`decoy explain generation` lists every column type and option, and
`decoy validate compile pipeline.yaml --explain` shows the order the tables are built in.

## CI integration

`decoy ci check` runs the checks listed in a committed `.decoy-ci.yaml`: config or full
validation, saved-scan drift, evidence verification and an optional scan of staged files for
literal seeded identifiers. It writes one report, uploads nothing and prints no matched value.

```bash
decoy ci check .decoy-ci.yaml --format sarif --output decoy.sarif
```

- Manifest example: [`examples/decoy-ci.yaml`](examples/decoy-ci.yaml). Schema: [`docs/schemas/decoy-ci-v1.schema.json`](docs/schemas/decoy-ci-v1.schema.json).
- GitHub Actions and GitLab CI templates are in [`integrations/`](integrations). They need a pinned `decoy` on the runner.
- pre-commit: add this repository under `repos:` and enable the hook `decoy-ci-check`.
- Full contract, limits and false-positive behavior: [docs/ci-contracts.md](docs/ci-contracts.md).

## Exit codes

`decoy` returns these codes. Scripts, Make recipes, and CI
pipelines can switch on the integer; the contract is stable across releases.

| Code | Name                   | Meaning                                                                                    |
|------|------------------------|--------------------------------------------------------------------------------------------|
| 0    | `EXIT_OK`              | Success.                                                                                   |
| 1    | `EXIT_USAGE`           | Usage error: config did not validate, path did not exist, flag combination was invalid, or a `unique` generate column the data cannot satisfy (`uniqueness_impossible`). Also an internal error that escaped a command (`error: internal error (<Type>)`; `--verbose` prints the traceback, `DECOY_DEBUG=1` re-raises it; a traceback can hold row data). |
| 2    | `EXIT_WARNINGS`        | The command ran clean except for advisory warnings, and `--fail-on-warning` was set. Also the code for a Click usage error and a bad `--master-key` or `--key-label` on `decoy run`. Returned by `decoy validate config` / `validate preflight` (and the `validate` aggregate). Without `--fail-on-warning` the same run exits 0. |
| 3    | `EXIT_RUNTIME`         | A command caught a run-time failure: the engine raised an unexpected error, an output write failed, or a transient I/O problem happened. |
| 4    | `EXIT_FINDINGS`        | The CLI ran cleanly but found data issues (e.g. `decoy report integrity` flagged residual PII or FK preservation failures, or the post-scan gate withheld a run's output). The fix is in the data being checked, not in the CLI invocation. |
| 5    | `EXIT_CAPACITY`        | `decoy run` or `decoy validate preflight` refused the job: it needs more memory than the host/budget has. The engine decides which refusals count: the out-of-core-FK fan-in and memory gate, a faker pool or reorder budget that is too small, a pool over its cache budget, generated output that cannot fit the machine's memory (`generation_budget_exceeded`), and a process or worker that ran out of memory. A rejected budget setting, a disk or quota limit and a routing refusal keep their usual exit. The fix is a bigger host/cgroup ceiling or a smaller job. `decoy validate preflight`'s v1 check does not cover the ingestion peak. Generated tables whose output cannot fit exit 5 at `decoy validate` and before `decoy run` writes anything; a missing or unreadable source file exits 1 first, so this needs readable sources; a run that runs out of memory exits 5 as well. |
| 6    | `EXIT_PARTIAL`         | `decoy run` delivered some tables and withheld the rest. Reserved for best-effort delivery; no run exits 6 yet. |
| 130  | -                      | Interrupted (Ctrl-C while a command runs), 128 plus SIGINT. Ctrl-C at a confirmation prompt exits 1. Not part of the `decoy ci` taxonomy. |

A command that reports several outcomes (`decoy ci check` across checks,
`decoy run --all` across pipelines) exits with the first of
**5 > 3 > 1 > 6 > 4 > 2 > 0** that occurred; a child's 6 is kept.

Constants and the order (`PRECEDENCE`) live in `decoy.cli.exit_codes`.
`decoy explain exit-codes` prints the same table from the CLI.

## Documentation

- [docs/install.md](docs/install.md): install, upgrade, rollback, offline and uninstall.
- [docs/cli-reference.md](docs/cli-reference.md): every command and flag, generated from the CLI.
- [docs/guides/shape-and-privacy/](docs/guides/shape-and-privacy/README.md): check what shape masking kept, fit and generate look-alike data, read fidelity reports, and use the differential-privacy fit.
- [docs/guides/telemetry/README.md](docs/guides/telemetry/README.md): the opt-in trace export and what it sends.
- [docs/library.md](docs/library.md) and [docs/project-layout.md](docs/project-layout.md): the record library and the project folder layout.
- [docs/ROADMAP.md](docs/ROADMAP.md): the one roadmap for CLI 1.0.0 and the platform.
- [CHANGELOG.md](CHANGELOG.md): release notes. [CODEMAP.md](CODEMAP.md): a map of the source.
- [decoy-engine](https://github.com/decoy-data/decoy-engine): the library behind the CLI. Import it directly to embed masking or generation in your own Python tool.

## Contributing and security

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to build, test and propose changes. Report a
vulnerability privately as described in [SECURITY.md](SECURITY.md). The trademark policy is
[TRADEMARKS.md](TRADEMARKS.md).

## License

Functional Source License, Version 1.1, Apache 2.0 Future License
(FSL-1.1-ALv2). `decoy-engine` moves to the same license from its first FSL
release onward; engine 0.22.0 and earlier stay Apache-2.0; 0.23.0 and later, including the 0.28.2 this CLI pins
today, are FSL-1.1-ALv2. You may use, modify and
redistribute Decoy for any purpose except a Competing Use: offering it, or
something substantially similar built from it, to others as a commercial
product or service. Internal production use is allowed. Each release
converts to the Apache License 2.0 on the second anniversary of its
release. FSL is source-available, not OSI open source. See `LICENSE.md` for
the full terms, [`LICENSING.md`](LICENSING.md) for a plain-English FAQ, and
`TRADEMARKS.md` for the trademark policy.
