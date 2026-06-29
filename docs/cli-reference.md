# `decoy`

Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy storm analyze data.csv     Profile a dataset for PII and risk.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy validate pipeline.yaml     Check a YAML pipeline before running.
  decoy unmask pipeline.yaml masked.csv   Recover fpe columns from a masked file.
  decoy fit source.csv             Fit a distribution snapshot for statistical generation.
  decoy init                       Scaffold a starter pipeline interactively.
  decoy templates list             Browse bundled pipeline templates.
  decoy explain modes              Plain-English topic help. `explain` lists topics.
  decoy info                       Branded splash + quick-start hints.
  decoy project init               Create a local .decoy/ workspace (local only).
  decoy catalog list               List the local metadata catalog entries.

Run `decoy --install-completion` to enable shell tab completion.

**Usage**:

```console
$ decoy [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--version`: Show the decoy CLI version and exit.
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `run`: Run a decoy pipeline from a YAML config.
* `validate`: Validate a decoy pipeline config without...
* `preflight`: Local pre-run readiness checks for a...
* `unmask`: Recover fpe-masked columns from a masked...
* `fit`: Fit a distribution-snapshot/v1 artifact...
* `init`: Scaffold a starter pipeline YAML through a...
* `demo`: Walk through scan -&gt; mask on a bundled...
* `explain`: Explain a Decoy concept in plain English.
* `info`: Print the Decoy CLI banner with...
* `schema`: Print the PipelineConfig JSON Schema to...
* `plan`: Compile a pipeline config into a versioned...
* `doctor`: Check engine and dependency health.
* `storm`: Dataset analysis -- the STORM event.
* `templates`: Browse and dump bundled starter pipeline...
* `vault`: Vault inspection utilities.
* `evidence`: Show and verify local run evidence manifests.
* `report`: Render, summarize, and compare local...
* `strategies`: Enumerate and inspect the engine&#x27;s...
* `providers`: Enumerate and inspect the engine&#x27;s...
* `checksums`: List the engine&#x27;s registered checksum...
* `validators`: List the engine&#x27;s registered job-level...
* `project`: Manage a local .decoy/ workspace.
* `catalog`: LOCAL metadata catalog for datasets, runs,...

## `decoy run`

Run a decoy pipeline from a YAML config.

Use this to execute a masking or synthetic-generation job described in
YAML. The engine handles its own logging per the YAML&#x27;s `logging:`
section; flags here only affect CLI-side output.

**Usage**:

```console
$ decoy run [OPTIONS] CONFIG
```

**Arguments**:

* `CONFIG`: Path to the YAML pipeline config.  [required]

**Options**:

* `-m, --mode [mask|generate]`: Operation: mask existing data or generate synthetic data.  [default: mask]
* `--json`: Emit a structured JSON result on stdout. Progress goes to stderr.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr; exit code carries success.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--master-key TEXT`: 64-char hex master key for keyed deterministic masking. Same key + same --key-label always yield bitwise-identical output across runs and machines. Reads DECOY_MASTER_KEY env var when omitted; without either, masking falls back to the legacy seeded path (per-input deterministic but not portable).  [env var: DECOY_MASTER_KEY]
* `--chunked`: Stream the source through the engine chunk-by-chunk, for inputs too large to load whole. Works for mask configs whose every strategy is value-keyed (hash, fpe, redact, truncate, text_redact, date_shift, bucketize), plus faker/categorical when deterministic with an explicit pool_size / categories declared in config; output is byte-identical to a plain run. Sources/targets may be CSV or Parquet. See: decoy explain chunked.
* `--chunk-size INTEGER RANGE`: Rows per chunk in --chunked mode.  [default: 100000; x&gt;=1]
* `--vault PATH`: Write the token vault (encrypted source-to-masked map for vault: true columns) to this path. The vault plus the config re-identify every vaulted value: store them separately and never alongside the masked output. Needs the engine&#x27;s vault extra (cryptography).
* `--substrate TEXT`: Execution substrate for --chunked runs: pandas (default) or polars. Non-chunked (plain) runs always use the engine&#x27;s pandas adapter (the V2 unified run_pipeline path); this flag and the DECOY_SUBSTRATE env var are only consulted for --chunked runs. Setting either on a plain run emits a warning to stderr and is otherwise ignored. Cross-substrate outputs are value-equal; CSV bytes may differ only via Arrow type-width drift, which CSV does not carry.  [env var: DECOY_SUBSTRATE]
* `--key-label TEXT`: Stable namespace string for the masking key hierarchy. Required when --master-key is set. Pick something durable (e.g. &#x27;customers_q4&#x27;); changing it produces a different masked output. Read from the YAML&#x27;s top-level &#x27;key_label:&#x27; field if not passed on the command line.
* `--evidence-out PATH`: Write a local evidence manifest (JSON) to this path after a successful run. The manifest records pipeline hash, input/output file fingerprints, run metadata, and row counts/timings/warnings where available (these are omitted for --chunked runs). It does NOT contain raw data values. Use `decoy evidence verify` to check the manifest against current files. See: decoy explain evidence (when available).
* `--help`: Show this message and exit.

Examples:

  decoy run pipeline.yaml
    Run with default mode (mask).

  decoy run pipeline.yaml --json
    Suppress chrome and emit a structured result for scripting.

  decoy run pipeline.yaml --chunked --chunk-size 100000
    Stream a large source through the engine instead of loading it whole.
    (See: decoy explain chunked.)

  decoy run pipeline.yaml --vault vault.bin
    Write an encrypted token vault for columns marked `vault: true`, so
    they can be recovered later with `decoy unmask`. (See: decoy explain vault.)

  decoy run pipeline.yaml --chunked --substrate polars
    Stream with polars instead of the chunked-path pandas default.
    (--substrate only affects --chunked runs; plain runs always use pandas.
    See: decoy explain substrate.)

See also: decoy validate, decoy explain chunked, decoy explain vault.


## `decoy validate`

Validate a decoy pipeline config without running it.

Use this in CI or before a long run to fail fast on a bad YAML. Exits 0
on a well-formed config, 1 on a parse / schema error or a config-level
plan-compile error (unknown provider, non-poolable provider on the
faker/pool path, missing deterministic namespace).

With --fail-on-warning, also exits non-zero when advisory warnings fire
(e.g. an output file already exists and would be overwritten on run).

**Usage**:

```console
$ decoy validate [OPTIONS] CONFIG
```

**Arguments**:

* `CONFIG`: Path to the YAML pipeline config to validate.  [required]

**Options**:

* `--json`: Emit a structured JSON result on stdout. Errors still go to stderr.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr; exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--fail-on-warning`: Exit non-zero if any advisory warning fires (e.g. output target exists). Enables CI gates that treat warnings as blocking.
* `--help`: Show this message and exit.

Examples:

  decoy validate pipeline.yaml
    Print OK on stdout when the config parses.

  decoy validate pipeline.yaml --json
    Emit a structured JSON result (multi-message) for scripting.

  decoy validate pipeline.yaml --quiet
    Stay silent on success; exit code carries the result.

  decoy validate pipeline.yaml --fail-on-warning
    Exit non-zero if any advisory warning fires (e.g. output target exists).

See also: decoy run.


## `decoy preflight`

Local pre-run readiness checks for a pipeline config.

Checks file existence, file readability, YAML syntax, and schema
validity. Reports findings as pass/warn/fail with structured output
available via --json.

This is a LOCAL check only. It does NOT check platform server-side
conditions, engine run-time constraints, data quality, vault access,
secrets availability, or network connectivity. Use `decoy validate`
for pure schema-only checks; use this command when you want to confirm
source files are present before starting a run.

**Usage**:

```console
$ decoy preflight [OPTIONS] CONFIG
```

**Arguments**:

* `CONFIG`: Path to the YAML pipeline config to check.  [required]

**Options**:

* `--local`: Explicit local mode (all checks are local by default; this flag makes the intent explicit in scripts).
* `--json`: Emit a structured JSON result on stdout.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr; exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--fail-on-warning`: Exit non-zero when any advisory warning fires.
* `--help`: Show this message and exit.

Examples:

  decoy preflight pipeline.yaml
    Run local readiness checks: YAML validity, schema, and source file existence.

  decoy preflight pipeline.yaml --local
    Same as above (--local is the explicit form; all checks are local by default).

  decoy preflight pipeline.yaml --json
    Emit a structured JSON result with per-check findings.

  decoy preflight pipeline.yaml --fail-on-warning
    Exit non-zero when advisory warnings fire (e.g. output already exists).

What preflight checks:
  - YAML syntax and schema (same as `decoy validate`)
  - Source file existence and readability
  - Target overwrite risk (advisory warning)

What preflight does NOT check:
  - Platform server-side conditions (secrets, RBAC, schedules, network targets)
  - Engine run-time constraints (capacity, row counts, provider limits)
  - Data validity or masking quality
  - Vault or secrets accessibility

See also: decoy validate, decoy run, decoy evidence verify.


## `decoy unmask`

Recover fpe-masked columns from a masked file using the pipeline config.

Reverses every `strategy: fpe` column (format-preserving encryption is
a keyed bijection; the key derives from the config&#x27;s seed + namespace).
Other strategies are one-way and pass through unchanged with an
`irreversible` report entry. Exits 0 on success, 1 on a config/usage
error, 3 on a runtime failure.

**Usage**:

```console
$ decoy unmask [OPTIONS] CONFIG MASKED
```

**Arguments**:

* `CONFIG`: The pipeline config the mask run used (carries seed + namespaces).  [required]
* `MASKED`: The masked CSV produced by `decoy run` for one table.  [required]

**Options**:

* `--table TEXT`: Which config table the masked file belongs to. Required when the config masks more than one table.
* `-o, --output PATH`: Where to write the recovered CSV. Default: &lt;masked&gt;.unmasked.csv next to the input.
* `--vault FILE`: Vault file the mask run wrote (decoy run --vault). Recovers one-way columns declared vault: true; decrypts under the config&#x27;s seed.
* `--json`: Emit a structured JSON result on stdout. Errors still go to stderr.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr; exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy unmask pipeline.yaml masked.csv
    Recover fpe columns into masked.unmasked.csv.

  decoy unmask pipeline.yaml masked.csv --output recovered.csv
    Choose the output path.

  decoy unmask pipeline.yaml masked.csv --table accounts
    Disambiguate when the config masks more than one table.

  decoy unmask pipeline.yaml masked.csv --json
    Emit the per-column reversibility report as JSON.

  decoy unmask pipeline.yaml masked.csv --vault vault.bin
    Also recover one-way columns the mask run vaulted
    (decoy run ... --vault vault.bin with vault: true columns).

Only `strategy: fpe` columns reverse from the config alone; hash,
redact, faker and the other one-way strategies pass through unchanged
unless the column was vaulted at mask time. The config carries the
seed: treat it as a key; the vault file is a re-identification map,
store it separately from the masked output.

See also: decoy run, decoy explain strategies.


## `decoy fit`

Fit a distribution-snapshot/v1 artifact for statistical generation.

Reads the source CSV, captures per-column distribution shape (numeric
histograms + quantiles, categorical top-k, datetime year bins) plus
any requested pairwise contingency tables, and writes the JSON
artifact `type: statistical` generate columns reference via
`snapshot_file`. Exits 0 on success, 1 on bad input.

**Usage**:

```console
$ decoy fit [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: Source CSV to fit the distribution snapshot from.  [required]

**Options**:

* `-o, --output PATH`: Where to write the snapshot JSON. Default: &lt;source&gt;.snapshot.json.
* `--parse-dates TEXT`: Column(s) to parse as datetimes (repeatable). CSV carries no dtype, so date columns must be named explicitly.
* `--joint TEXT`: Column pair &#x27;a,b&#x27; whose contingency table to capture (repeatable). Needed for `condition_on`.
* `--epsilon FLOAT`: Differentially private release: per-column Laplace noise on all snapshot counts; exact quantiles/means are removed. The budget is PER COLUMN HISTOGRAM (k columns compose to ~k*epsilon total). Incompatible with --joint in v1.
* `--json`: Emit a structured JSON result on stdout.
* `-q, --quiet`: Suppress stdout. Exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy fit customers.csv
    Write customers.snapshot.json next to the source.

  decoy fit customers.csv --output snapshot.json --parse-dates signup_date
    Treat signup_date as a datetime column.

  decoy fit customers.csv --joint state,tier
    Capture the (state, tier) contingency table so a statistical column
    can use `condition_on`.

  decoy fit customers.csv --epsilon 1.0
    Differentially private release: Laplace noise on every snapshot
    count (OpenDP/SmartNoise histogram mechanism). The budget is per
    column histogram; incompatible with --joint in v1.

See also: decoy run, decoy validate, decoy explain differential-privacy.


## `decoy init`

Scaffold a starter pipeline YAML through a short Q&amp;A.

Use this on a fresh project to get a working pipeline you can run end to
end, then edit the rules and paths to match your data. The wizard is the
only interactive prompt in the CLI -- every other command is one-shot.

**Usage**:

```console
$ decoy init [OPTIONS] [INPUT_FILE]
```

**Arguments**:

* `[INPUT_FILE]`: Optional input file (.csv/.tsv/.parquet). When given without --preset, runs STORM against the file and scaffolds a column-aware pipeline.yaml with `# REVIEW:` comments above every auto-inferred column.

**Options**:

* `--out PATH`: Where to write the pipeline YAML. Use `-` to write to stdout.  [default: pipeline.yaml]
* `--preset TEXT`: Skip the preset prompt and use this template directly.
* `-y, --yes`: Skip overwrite confirmation.
* `--json`: Skip the wizard; emit a JSON record of what was written.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy init
    Interactive Q&A; writes pipeline.yaml in the current directory.

  decoy init --preset hipaa --out hipaa_pipeline.yaml
    Skip the wizard; scaffold from the HIPAA template.

  decoy init customers.csv --out pipeline.yaml
    Column-aware scaffolding (OSS.4c, 2026-06-02). Runs STORM against
    the file, picks a starter strategy per column from the inference
    table, writes the YAML with `# REVIEW:` comments above every
    inferred entry. The user must read + edit before running.

  decoy init --yes
    Skip confirmation when overwriting an existing file.

See also: decoy validate, decoy run, decoy storm analyze, decoy templates list.


## `decoy demo`

Walk through scan -&gt; mask on a bundled sample dataset.

Use this on a fresh install to see what Decoy can do end to end without
needing your own data or pipeline. All output lands in `./decoy_demo/`
(override with `--dir`).

The `--ref` referential-integrity variant (three related CSVs masked
with joinable FK columns) is deferred to a follow-up sprint and
currently exits with a usage error; use the default single-table flow.

**Usage**:

```console
$ decoy demo [OPTIONS]
```

**Options**:

* `--dir PATH`: Where to drop the demo artifacts.  [default: decoy_demo]
* `--ref`: Run the 3-table referential-integrity variant (customers + orders + payments).
* `--rows INTEGER RANGE`: Rows per dataset when --ref is set. Default 1000.  [default: 1000; 10&lt;=x&lt;=100000]
* `--json`: Emit a JSON summary instead of cards.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy demo
    Run the simple scan -> mask walkthrough in ./decoy_demo/.

  decoy demo --json
    Same flow, but emit a JSON summary instead of cards.

Note: `decoy demo --ref` (the 3-table FK variant) is deferred to a follow-up
sprint and currently exits with a usage error.

See also: decoy storm analyze, decoy run.


## `decoy explain`

Explain a Decoy concept in plain English.

Built-in topics: modes, transforms, disguises, output, pipeline, yaml,
storm, keys, vault, chunked, substrate, differential-privacy, security,
completion. Run with no topic to see the full list.

**Usage**:

```console
$ decoy explain [OPTIONS] [TOPIC]
```

**Arguments**:

* `[TOPIC]`: Which topic to explain. Omit to list every topic.

**Options**:

* `--json`: Emit a structured JSON object instead of a rendered Panel.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy explain modes
    Plain-English description of mask vs generate.

  decoy explain transforms
    The built-in masking transforms with one-line descriptions.

  decoy explain
    No topic -- list every topic with its summary.

See also: decoy --help, decoy templates list.


## `decoy info`

Print the Decoy CLI banner with quick-start hints.

**Usage**:

```console
$ decoy info [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON record of CLI metadata instead of the banner.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy info
    Render the branded splash + quick-start hints.

  decoy info --json
    Emit version + counts of bundled topics and templates as JSON.

See also: decoy --help, decoy explain, decoy templates list.


## `decoy schema`

Print the PipelineConfig JSON Schema to stdout.

**Usage**:

```console
$ decoy schema [OPTIONS]
```

**Options**:

* `-o, --output PATH`: Write the schema to this file instead of stdout.
* `--json`: Wrap the schema in a {command, status, schema} JSON envelope.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy schema
    Print the PipelineConfig JSON Schema to stdout.

  decoy schema -o decoy.schema.json
    Write the schema to a file (for editor / IDE integration).

  decoy schema --json
    Wrap the schema in the standard {command, status, schema} envelope.

See also: decoy validate, decoy templates list.


## `decoy plan`

Compile a pipeline config into a versioned plan artifact.

**Usage**:

```console
$ decoy plan [OPTIONS] CONFIG
```

**Arguments**:

* `CONFIG`: Path to the pipeline YAML config to compile.  [required]

**Options**:

* `--profile FILE`: Path to a pre-computed Profile JSON file (from decoy_engine.profile).
* `--no-profile`: Skip the profile phase; profile-dependent checks land in plan_compile.checks_skipped.
* `--json`: Emit JSON instead of YAML on stdout. (yaml.safe_load -&gt; json.dumps shape.)
* `--out PATH`: Write the plan to a file instead of stdout.
* `--help`: Show this message and exit.

Examples:

  decoy plan pipeline.yaml --no-profile
    Compile-check the config without loading source data. Faster; some
    profile-dependent checks are skipped (recorded in
    plan_compile.checks_skipped on the emitted plan).

  decoy plan pipeline.yaml --profile profile.json
    Load a pre-computed Profile (JSON) and run all five S1 plan-compile
    checks.

  decoy plan pipeline.yaml --no-profile --json
    Emit the plan as JSON (yaml.safe_load -> json.dumps round-trip).

  decoy plan pipeline.yaml --no-profile --out plan.yaml
    Write the plan to a file instead of stdout.

The fully-automated path (`decoy plan pipeline.yaml` with no profile
flag) lands once the profile_source orchestration slice ships.

See also: decoy validate, decoy run.


## `decoy doctor`

Check engine and dependency health.

Exits 0 when all hard requirements are present. Exits non-zero when a
hard requirement is missing. Soft-requirement absences produce warnings
but do not change the exit code.

**Usage**:

```console
$ decoy doctor [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON health report instead of a table.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy doctor
    Run all environment health checks and print a report.

  decoy doctor --json
    Same data as JSON for CI or support tooling.

  decoy doctor --quiet
    Silent mode; exit code 0 = healthy, non-zero = hard requirement missing.

See also: decoy --version, decoy info.


## `decoy storm`

Dataset analysis -- the STORM event. `analyze` looks at a file (pre-run); `integrity` verifies a masked file (post-run). The previous `scan` verb is a deprecated alias for `analyze`.

**Usage**:

```console
$ decoy storm [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `analyze`: Scan a dataset and produce a STORM profile.
* `scan`: Scan a dataset and produce a STORM profile.
* `integrity`: Verify a masked file&#x27;s integrity against...
* `fields`: List fields from a saved STORM scan, with...
* `show`: Per-field detail from a saved STORM scan.
* `diff`: Compare two STORM scans -- catch schema,...
* `test`: Preview the `storm analyze` UX without...

### `decoy storm analyze`

Scan a dataset and produce a STORM profile.

Use this when you&#x27;ve been handed a dataset and want to know what&#x27;s in it
-- which fields are PII, which look like quasi-identifiers, what
re-identification risk the dataset carries -- before writing a masking
pipeline. Pass the saved scan JSON to `decoy storm fields` or
`decoy storm show`.

Supported formats: delimited (CSV/TSV, default), parquet, and fixed-width.
Fixed-width input requires an explicit --layout spec (column boundaries
are ambiguous without one). Format is inferred from the file extension
when --format is not supplied.

**Usage**:

```console
$ decoy storm analyze [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: Path to a file to scan (CSV, Parquet, or fixed-width).  [required]

**Options**:

* `--rows INTEGER`: Sample row cap. Default: scan everything.
* `--strategy [full|head|random]`: Sampling strategy when --rows is set.  [default: head]
* `--out PATH`: Where to save the scan JSON. Use - for stdout. Default: scan_&lt;timestamp&gt;.json next to the source.
* `--json`: Emit the full StormProfile JSON to stdout. No card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--format [delimited|parquet|fixed-width]`: Input format: delimited (CSV/TSV), parquet, or fixed-width. Default: inferred from file extension. fixed-width always requires --layout.
* `--layout PATH`: Layout spec (YAML or JSON) for fixed-width input. Required when format is fixed-width. Each column needs &#x27;name&#x27;, &#x27;start&#x27; (0-indexed), and &#x27;width&#x27;.
* `--help`: Show this message and exit.

Examples:

  decoy storm analyze data.csv
    Analyze a CSV with default sampling, save scan_<timestamp>.json.

  decoy storm analyze data.csv --rows 50000 --strategy random
    Sample 50K random rows.

  decoy storm analyze data.csv --json > scan.json
    Pipe the full StormProfile JSON for downstream tooling.

  decoy storm analyze data.parquet
    Analyze a Parquet file (format inferred from extension).

  decoy storm analyze data.parquet --format parquet
    Same, with explicit format flag.

  decoy storm analyze records.fwf --layout layout.yaml
    Analyze a fixed-width file using an explicit column layout.
    Layout YAML: columns: [{name: id, start: 0, width: 5}, ...]

See also: decoy storm fields, decoy storm show, decoy storm diff,
  decoy storm integrity, decoy init, decoy run.


### `decoy storm scan`

Scan a dataset and produce a STORM profile.

Use this when you&#x27;ve been handed a dataset and want to know what&#x27;s in it
-- which fields are PII, which look like quasi-identifiers, what
re-identification risk the dataset carries -- before writing a masking
pipeline. Pass the saved scan JSON to `decoy storm fields` or
`decoy storm show`.

Supported formats: delimited (CSV/TSV, default), parquet, and fixed-width.
Fixed-width input requires an explicit --layout spec (column boundaries
are ambiguous without one). Format is inferred from the file extension
when --format is not supplied.

**Usage**:

```console
$ decoy storm scan [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: Path to a file to scan (CSV, Parquet, or fixed-width).  [required]

**Options**:

* `--rows INTEGER`: Sample row cap. Default: scan everything.
* `--strategy [full|head|random]`: Sampling strategy when --rows is set.  [default: head]
* `--out PATH`: Where to save the scan JSON. Use - for stdout. Default: scan_&lt;timestamp&gt;.json next to the source.
* `--json`: Emit the full StormProfile JSON to stdout. No card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--format [delimited|parquet|fixed-width]`: Input format: delimited (CSV/TSV), parquet, or fixed-width. Default: inferred from file extension. fixed-width always requires --layout.
* `--layout PATH`: Layout spec (YAML or JSON) for fixed-width input. Required when format is fixed-width. Each column needs &#x27;name&#x27;, &#x27;start&#x27; (0-indexed), and &#x27;width&#x27;.
* `--help`: Show this message and exit.

DEPRECATED: `decoy storm scan` is the old name for `decoy storm analyze`.
Run `decoy storm analyze --help` for the canonical examples.

Removal target: 0.2.0.


### `decoy storm integrity`

Verify a masked file&#x27;s integrity against its pre-mask source.

Wraps `decoy_engine.storm.postmask.run_storm_post_mask`. Runs the
three post-mask check buckets (residual_pii, fk_preservation,
policy_validation) the platform&#x27;s mask job already runs when
`run_storm: true` is declared in the pipeline; this verb lets the
CLI user run the same checks standalone.

Exit codes: 0 clean; 4 EXIT_FINDINGS on any fail-severity finding;
1 EXIT_USAGE for missing files; 3 EXIT_RUNTIME for unexpected
exceptions.

OSS.4b (2026-06-02).

**Usage**:

```console
$ decoy storm integrity [OPTIONS] MASKED
```

**Arguments**:

* `MASKED`: Path to the masked CSV to verify.  [required]

**Options**:

* `--source FILE`: Pre-mask source CSV (ground truth for the integrity check).  [required]
* `--config FILE`: Optional pipeline.yaml. When passed, policy_validation can compare against the configured masks. Without it the runner still produces residual_pii + fk_preservation findings.
* `--out PATH`: Write the JobStormReport JSON to this path. The Rich table still renders to stderr.
* `--allow-source-mismatch`: Suppress the stderr warning when --source does not match the pipeline&#x27;s declared sources block.
* `--json`: Emit the full JobStormReport JSON to stdout. No card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy storm integrity masked.csv --source source.csv
    Run all three post-mask checks (residual_pii + fk_preservation +
    policy_validation) against a masked file with its pre-mask
    baseline as ground truth. Render a Rich findings table.

  decoy storm integrity masked.csv --source source.csv --config pipeline.yaml
    Same, but load the pipeline YAML so policy_validation can
    compare against the configured masks. Without --config the
    runner still produces residual_pii findings; policy_validation
    is reduced to "no config provided" notes.

  decoy storm integrity masked.csv --source source.csv --json > report.json
    Pipe the full JobStormReport-shaped JSON for downstream tooling.

  decoy storm integrity masked.csv --source source.csv --out report.json
    Write JSON to file + render a Rich summary on stderr.

Exit codes: 0 clean (no fail/error findings); 4 EXIT_FINDINGS (one
or more fail-severity findings); 1 EXIT_USAGE for missing files;
3 EXIT_RUNTIME for unexpected exceptions.

See also: decoy storm analyze, decoy run, decoy explain exit-codes.


### `decoy storm fields`

List fields from a saved STORM scan, with optional filters.

The list view of the web FORECAST drill-down -- print the fields that
matter, filter by PII bucket or quasi-identifier membership, pipe the
result somewhere else. For per-field detail, see `decoy storm show`.

**Usage**:

```console
$ decoy storm fields [OPTIONS] SCAN
```

**Arguments**:

* `SCAN`: Path to a STORM scan JSON, or `-` for stdin.  [required]

**Options**:

* `--pii [high|med|low|none]`: Filter to fields whose PII score falls in this bucket.
* `--quasi`: Only fields that participate in any quasi-identifier group.
* `--json`: Emit the filtered field list as JSON to stdout.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy storm fields scan.json
    List every field with PII score, bucket, quasi-identifier flag.

  decoy storm fields scan.json --pii high --quasi
    Only fields that are high PII *and* part of a quasi-identifier group.

  decoy storm fields scan.json --json | jq '.fields[].name'
    Pipe just the matching field names somewhere else.

See also: decoy storm analyze, decoy storm show.


### `decoy storm show`

Per-field detail from a saved STORM scan.

The drill-down view of one field: PII score + bucket, detector matches,
sentinel hits, top values, quasi-identifier membership. Stays read-only
-- for live exploration use the web FORECAST panel.

**Usage**:

```console
$ decoy storm show [OPTIONS] SCAN FIELD
```

**Arguments**:

* `SCAN`: Path to a STORM scan JSON, or `-` for stdin.  [required]
* `FIELD`: Field name to inspect.  [required]

**Options**:

* `--json`: Emit the full field detail as JSON to stdout.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy storm show scan.json ssn
    Per-field detail card -- PII score, detectors, sentinels, top values, QI.

  decoy storm show scan.json email --json
    Same data as a structured JSON envelope.

  decoy storm analyze data.csv --json | decoy storm show - ssn
    Pipe a fresh scan straight in.

See also: decoy storm analyze, decoy storm fields.


### `decoy storm diff`

Compare two STORM scans -- catch schema, PII, and risk drift.

Designed for CI: run `decoy storm diff baseline.json new.json --strict`
on every PR to fail the build when a column&#x27;s PII bucket goes up, a new
high-PII field appears, or a new quasi-identifier group forms. Read-only
-- the scans are JSON; raw data never enters the CLI.

**Usage**:

```console
$ decoy storm diff [OPTIONS] OLD NEW
```

**Arguments**:

* `OLD`: Path to the older STORM scan JSON, or `-` for stdin.  [required]
* `NEW`: Path to the newer STORM scan JSON, or `-` for stdin.  [required]

**Options**:

* `--strict`: Exit 1 on drift -- any PII bucket bumped up, any new high-PII field, or any new quasi-identifier group.
* `--json`: Emit the categorized diff as JSON to stdout.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy storm diff baseline.json new.json
    Print field-, PII-, QI-, and risk-level differences between two scans.

  decoy storm diff baseline.json new.json --strict
    Same, but exit 1 on drift (PII bucket bumped up, new high-PII field, or
    new quasi-identifier group). Wire this into CI.

  decoy storm diff baseline.json new.json --json | jq '.drift'
    Boolean drift flag for scripting.

See also: decoy storm analyze, decoy storm fields.


### `decoy storm test`

Preview the `storm analyze` UX without scanning any data.

Runs the stormy multistage animation for ~10 seconds (the default), then
prints a clearly-marked fake summary card. No data is read; nothing is
written. Use this to demo the CLI on a clean terminal, record a screen
capture, or confirm the storm animation renders before pointing the real
scan at a slow dataset.

--json and --quiet skip the animation -- they are pipeline-shape only.

**Usage**:

```console
$ decoy storm test [OPTIONS]
```

**Options**:

* `--seconds FLOAT RANGE`: How long to run the simulated scan stages (default 10).  [default: 10.0; x&gt;=0.0]
* `--json`: Skip the animation, emit a fake scan-shaped envelope to stdout.
* `-q, --quiet`: Suppress stdout. Skips the animation and exits 0.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy storm test
    10 seconds of stormy multistage animation, then a fake summary card.
    No data is read; nothing is written.

  decoy storm test --seconds 30
    Stretch the demo to 30 seconds -- handy for screen recording.

  decoy storm test --json
    Skip the animation, emit a fake envelope. For pipeline smoke tests.

See also: decoy storm analyze, decoy demo.


## `decoy templates`

Browse and dump bundled starter pipeline templates.

**Usage**:

```console
$ decoy templates [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List every bundled pipeline template.
* `show`: Print one bundled template to stdout.

### `decoy templates list`

List every bundled pipeline template.

**Usage**:

```console
$ decoy templates list [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON list of {name, summary} objects instead of a table.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy templates list
    Print every template with a one-line summary.

  decoy templates list --json
    Same data as JSON for scripting.

See also: decoy templates show, decoy init.


### `decoy templates show`

Print one bundled template to stdout.

Default mode prints raw YAML so it pipes cleanly to a file:
`decoy templates show hipaa &gt; pipeline.yaml`. Wrap in --json when a
script needs the metadata too.

**Usage**:

```console
$ decoy templates show [OPTIONS] NAME
```

**Arguments**:

* `NAME`: Which template to print. Tab-completes from the bundled set.  [required]

**Options**:

* `--json`: Wrap the body in a JSON envelope instead of printing raw YAML.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy templates show hipaa
    Print the HIPAA pipeline YAML to stdout.

  decoy templates show pci > pipeline.yaml
    Save the PCI template directly to a file.

  decoy templates show hipaa > pipeline.yaml
    Save the HIPAA template, then validate it with `decoy validate pipeline.yaml`.

See also: decoy templates list, decoy init.


## `decoy vault`

Vault inspection utilities. `info` summarises a vault without full decode.

**Usage**:

```console
$ decoy vault [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `info`: Inspect a vault file: report entry count,...

### `decoy vault info`

Inspect a vault file: report entry count, namespaces, and dropped-ambiguous count.

Opens the vault using the seed derived from the pipeline config. A
mismatched seed (wrong config) exits 1 with a clear error message.
Exits 0 on success, 1 on a config/vault/usage error.

**Usage**:

```console
$ decoy vault info [OPTIONS] VAULT
```

**Arguments**:

* `VAULT`: The vault file written by `decoy run --vault`.  [required]

**Options**:

* `--config FILE`: The pipeline config the mask run used (must carry the same seed as the run that wrote the vault).  [required]
* `--json`: Emit a structured JSON result on stdout. Errors still go to stderr.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr; exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy vault info vault.bin --config pipeline.yaml
    Show entry count, namespaces, and ambiguous-dropped count.

  decoy vault info vault.bin --config pipeline.yaml --json
    Same data as a JSON envelope for scripting.

  decoy vault info vault.bin --config pipeline.yaml --quiet
    Silent mode; exit code 0 = vault opened successfully.

The vault is encrypted under a key derived from the config's seed. The
config passed to --config must be the SAME config (or at least the same
global_settings.seed) used by the `decoy run --vault` call that wrote
the vault, otherwise the decrypt will fail and the command exits 1.

See also: decoy run --vault, decoy unmask --vault.


## `decoy evidence`

Show and verify local run evidence manifests. `show` renders a manifest; `verify` checks file fingerprints for drift.

**Usage**:

```console
$ decoy evidence [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `show`: Render a local evidence manifest in...
* `verify`: Verify a local evidence manifest&#x27;s...

### `decoy evidence show`

Render a local evidence manifest in human-readable form.

Shows pipeline fingerprint, input/output fingerprints, run metadata,
masking strategies, and manifest self-consistency status. Read-only:
this command never modifies files and never exposes raw data values
(the manifest itself does not contain them).

Use `decoy evidence verify` to check whether the recorded fingerprints
still match the current on-disk files.

What this does NOT prove: manifest_hash is an UNKEYED SHA-256 check.
It detects accidental drift; it does NOT detect a motivated tamperer who
can edit the manifest and recompute the hash. Keyed signing is platform
R4 territory.

**Usage**:

```console
$ decoy evidence show [OPTIONS] EVIDENCE_FILE
```

**Arguments**:

* `EVIDENCE_FILE`: Path to a local evidence manifest JSON (produced by decoy run --evidence-out).  [required]

**Options**:

* `--json`: Emit the manifest as structured JSON instead of a human-readable card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy evidence show evidence.json
    Render the evidence manifest in a human-readable card.

  decoy evidence show evidence.json --json
    Emit the manifest as structured JSON (suitable for scripting).

What evidence show does NOT do:
  - It does not verify fingerprints against current files.
  - Use `decoy evidence verify` to check for drift (accidental file changes).

Integrity note: manifest_hash is an UNKEYED SHA-256 fingerprint. It detects
accidental drift; it does NOT detect a motivated tamperer who can edit the
manifest and recompute the hash. Keyed signing is platform R4 territory.

See also: decoy evidence verify, decoy run --evidence-out.


### `decoy evidence verify`

Verify a local evidence manifest&#x27;s fingerprints against current files.

Re-hashes the pipeline config, input files, and output files and
compares against the fingerprints recorded in the manifest. Also checks
manifest_hash to detect edits to the manifest file itself.

Exits 0 when all fingerprints match (no drift). Exits non-zero
(EXIT_FINDINGS) when any fingerprint has changed.

What this DOES prove: the files look the same as when the run
completed. What this does NOT prove: correctness of the output,
platform audit compliance, or that the run actually occurred.

Integrity limit: manifest_hash is an UNKEYED SHA-256 check. It detects
accidental drift (file changes since the run), NOT a motivated tamperer
who can edit the manifest and recompute the hash. Keyed signing (R4) is
required for adversarial authenticity guarantees.

**Usage**:

```console
$ decoy evidence verify [OPTIONS] EVIDENCE_FILE
```

**Arguments**:

* `EVIDENCE_FILE`: Path to a local evidence manifest JSON.  [required]

**Options**:

* `--json`: Emit a structured JSON result instead of human-readable output.
* `-q, --quiet`: Suppress stdout. Exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy evidence verify evidence.json
    Check all fingerprints (pipeline, inputs, outputs, manifest integrity).
    Exits 0 when all match; non-zero when any changed.

  decoy evidence verify evidence.json --json
    Emit a structured JSON result with the list of issues found.

What verify checks:
  - manifest_hash: detects edits to the manifest JSON file.
  - pipeline_fingerprint: detects changes to pipeline.yaml.
  - input_fingerprints: detects changes to source data files.
  - output_fingerprints: detects changes to masked/generated output files.

What verify does NOT check:
  - Whether the output was produced by the declared pipeline.
  - Data correctness or masking quality.
  - Platform audit logs, RBAC, or schedule history.
  - Network, vault, or secrets accessibility.

Integrity limit: manifest_hash is an UNKEYED SHA-256 check. It detects
accidental drift; it does NOT detect a motivated tamperer who can edit the
manifest and recompute the hash. Keyed signing is platform R4 territory.

Exit codes: 0 clean; 4 fingerprint drift detected; 1 bad input.

See also: decoy evidence show, decoy run --evidence-out.


## `decoy report`

Render, summarize, and compare local evidence manifests. Operates on evidence JSON files produced by `decoy run --evidence-out`.

**Usage**:

```console
$ decoy report [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `render`: Render an evidence manifest to an HTML or...
* `summarize`: Print a concise terminal summary of a...
* `compare`: Compare two evidence manifests and report...

### `decoy report render`

Render an evidence manifest to an HTML or Markdown report file.

The report is built from the manifest only (evidence-safe). Raw row
values, PII, and STORM profile internals are never included.

HTML output is self-contained and offline-capable (no CDN/external JS).
Markdown output is plain text.

**Usage**:

```console
$ decoy report render [OPTIONS] EVIDENCE_FILE
```

**Arguments**:

* `EVIDENCE_FILE`: Path to a local evidence manifest JSON (produced by decoy run --evidence-out).  [required]

**Options**:

* `--out PATH`: Output file path (e.g. report.html or report.md).  [required]
* `--format TEXT`: Output format: &#x27;html&#x27; (default) or &#x27;markdown&#x27;.  [default: html]
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy report render evidence.json --out report.html
    Render the manifest as a self-contained offline HTML report.

  decoy report render evidence.json --format markdown --out report.md
    Render the manifest as a plain Markdown report.

What the report includes:
  Run summary, pipeline identity (fingerprint), input/output fingerprints,
  row counts, masking strategies (names only), node timings, and warnings.

What the report intentionally excludes:
  Raw row values, PII samples, STORM profile internals, diagnostic values.
  The evidence manifest records strategy names and fingerprints only; the
  report renders that safe subset.

See also: decoy report summarize, decoy report compare, decoy evidence show.


### `decoy report summarize`

Print a concise terminal summary of a local evidence manifest.

Renders key fields from the manifest in a Rich card: run metadata,
pipeline fingerprint, input/output counts, row counts, and warnings.
Read-only; never modifies files.

**Usage**:

```console
$ decoy report summarize [OPTIONS] EVIDENCE_FILE
```

**Arguments**:

* `EVIDENCE_FILE`: Path to a local evidence manifest JSON.  [required]

**Options**:

* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy report summarize evidence.json
    Print a concise summary of the evidence manifest to the terminal.

What summarize shows:
  Run ID, timestamp, CLI/engine versions, pipeline fingerprint (prefix),
  input/output fingerprint counts, row counts per table, and warning count.

See also: decoy report render, decoy evidence show.


### `decoy report compare`

Compare two evidence manifests and report what changed between runs.

Detects changes in pipeline fingerprint, per-table input/output
fingerprints, row counts, and warnings. MANIFEST-vs-MANIFEST only --
does not read source/output CSV data files.

Exits 0 in both change and no-change cases. Use --json for scripting.

**Usage**:

```console
$ decoy report compare [OPTIONS] OLD_EVIDENCE NEW_EVIDENCE
```

**Arguments**:

* `OLD_EVIDENCE`: Path to the older evidence manifest JSON.  [required]
* `NEW_EVIDENCE`: Path to the newer evidence manifest JSON.  [required]

**Options**:

* `--json`: Emit structured JSON instead of human-readable output.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy report compare old-evidence.json new-evidence.json
    Compare two evidence manifests and show which fingerprints changed,
    row-count deltas, and warnings added or removed.

  decoy report compare old-evidence.json new-evidence.json --json
    Emit structured JSON suitable for scripting.

What compare checks:
  - Pipeline fingerprint change.
  - Per-table input fingerprint changes (added/removed/changed).
  - Per-table output fingerprint changes (added/removed/changed).
  - Row count deltas per table.
  - Warnings added or removed.

What compare does NOT check:
  - Data correctness or masking quality.
  - Platform audit logs or schedule history.

Scope: MANIFEST-vs-MANIFEST only. Data-level compare (source.csv vs masked.csv)
is deferred to SP-18b/19.

See also: decoy report summarize, decoy evidence verify.


## `decoy strategies`

Enumerate and inspect the engine&#x27;s registered mask strategies.

**Usage**:

```console
$ decoy strategies [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List every registered mask strategy in the...
* `inspect`: Show details for one registered mask...

### `decoy strategies list`

List every registered mask strategy in the engine.

**Usage**:

```console
$ decoy strategies list [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON list of registered strategies instead of a table.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy strategies list
    Print every registered mask strategy with its class name.

  decoy strategies list --json
    Same data as JSON for CI or support tooling.

See also: decoy strategies inspect, decoy providers list.


### `decoy strategies inspect`

Show details for one registered mask strategy.

**Usage**:

```console
$ decoy strategies inspect [OPTIONS] NAME
```

**Arguments**:

* `NAME`: Strategy name to inspect.  [required]

**Options**:

* `--json`: Emit a JSON record instead of a panel.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy strategies inspect fpe
    Show parameters and behavior for the FPE strategy.

  decoy strategies inspect geo_generalize --json
    Same data as JSON.

See also: decoy strategies list.


## `decoy providers`

Enumerate and inspect the engine&#x27;s registered generation providers.

**Usage**:

```console
$ decoy providers [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List every registered generation provider...
* `inspect`: Show capability details for one registered...

### `decoy providers list`

List every registered generation provider in the engine.

**Usage**:

```console
$ decoy providers list [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON list of registered providers instead of a table.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy providers list
    Print every registered provider with backend type and poolable flag.

  decoy providers list --json
    Same data as JSON.

See also: decoy providers inspect, decoy strategies list.


### `decoy providers inspect`

Show capability details for one registered provider.

**Usage**:

```console
$ decoy providers inspect [OPTIONS] NAME
```

**Arguments**:

* `NAME`: Provider name to inspect.  [required]

**Options**:

* `--json`: Emit a JSON record instead of a panel.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy providers inspect person_name
    Show capability matrix for the person_name provider.

  decoy providers inspect synthetic_ssn --json
    Same data as JSON.

See also: decoy providers list.


## `decoy checksums`

List the engine&#x27;s registered checksum schemes (SP-04).

**Usage**:

```console
$ decoy checksums [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List every registered checksum scheme in...

### `decoy checksums list`

List every registered checksum scheme in the engine (SP-04).

**Usage**:

```console
$ decoy checksums list [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON list of checksum scheme names.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy checksums list
    Print every registered checksum scheme.

  decoy checksums list --json
    Same data as JSON.

See also: decoy validators list.


## `decoy validators`

List the engine&#x27;s registered job-level validators (SP-05).

**Usage**:

```console
$ decoy validators [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List every registered job-level validator...

### `decoy validators list`

List every registered job-level validator in the engine (SP-05).

**Usage**:

```console
$ decoy validators list [OPTIONS]
```

**Options**:

* `--json`: Emit a JSON list of validator names.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy validators list
    Print every registered job-level validator.

  decoy validators list --json
    Same data as JSON.

See also: decoy checksums list.


## `decoy project`

Manage a local .decoy/ workspace. LOCAL ONLY -- does not sync with the platform server, track remote state, or replace RBAC, audit logs, or managed operations. Use `project init` to create a workspace; `project show` to inspect it.

**Usage**:

```console
$ decoy project [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `init`: Create a local .decoy/ workspace in the...
* `show`: Print the resolved .decoy/ workspace config.

### `decoy project init`

Create a local .decoy/ workspace in the current directory.

The workspace is a LOCAL convenience area for derived Decoy artifacts
(scan records, run metadata, evidence manifests, rendered reports). It
does NOT sync with the platform server, track remote state, or replace
RBAC, audit logs, or managed platform operations.

Running `project init` a second time in an existing workspace is safe
(idempotent): it will not overwrite existing config or artifacts.

Deleting .decoy/ removes derived Decoy artifacts only. It never deletes
your source data files.

**Usage**:

```console
$ decoy project init [OPTIONS]
```

**Options**:

* `--workspace TEXT`: Directory to create the .decoy/ workspace in. Defaults to the current working directory. Can also be set via the DECOY_WORKSPACE_ROOT environment variable.
* `--json`: Emit a structured JSON result on stdout.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy project init
    Create a .decoy/ workspace in the current directory.

  decoy project init --workspace /path/to/project
    Create a .decoy/ workspace at an explicit location.

  decoy project init --json
    Emit a structured JSON result.

What init creates:
  .decoy/workspace.json     -- workspace config (version, defaults)
  .decoy/catalog.duckdb     -- created lazily by `decoy catalog` commands
  .decoy/scans/             -- STORM scan artifacts (local; may be sensitive)
  .decoy/runs/              -- run record metadata
  .decoy/evidence/          -- evidence manifests from local runs
  .decoy/reports/           -- rendered report artifacts

What this does NOT do:
  - It does NOT create a platform project, register a workspace server-side,
    or require a platform login.
  - Deleting .decoy/ removes derived Decoy artifacts; it never deletes
    your source data.

See also: decoy project show, decoy catalog list.


### `decoy project show`

Print the resolved .decoy/ workspace config.

Searches upward from the current directory for a .decoy/ workspace,
mirroring how git discovers .git/. Use --workspace to point at an
explicit location.

This is a read-only command. It does not modify the workspace or
contact the platform.

**Usage**:

```console
$ decoy project show [OPTIONS]
```

**Options**:

* `--workspace TEXT`: Workspace root to show. Defaults to upward discovery from cwd. Can also be set via DECOY_WORKSPACE_ROOT.
* `--json`: Emit structured JSON instead of a human-readable card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy project show
    Print the workspace config. Searches upward from cwd for .decoy/.

  decoy project show --workspace /path/to/project
    Show config for an explicit workspace location.

  decoy project show --json
    Emit a structured JSON result.

What show displays:
  - Workspace root path and .decoy/ location.
  - Config defaults (source_dir, output_dir, recipe_dir).
  - Created-at timestamp and workspace version.
  - Presence of catalog.duckdb and artifact subdirectories.

Upward discovery:
  Commands search upward from the current directory to find .decoy/,
  mirroring how git discovers .git/. Use --workspace to override.

See also: decoy project init, decoy catalog list.


## `decoy catalog`

LOCAL metadata catalog for datasets, runs, and evidence. Backed by DuckDB at .decoy/catalog.duckdb inside the project workspace. LOCAL ONLY -- does not sync with the platform server or track remote state. Use `decoy project init` to create a workspace before using catalog commands.

**Usage**:

```console
$ decoy catalog [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List all entries in the local metadata...
* `add`: Register an artifact path in the local...
* `show`: Show the full details of a catalog entry.

### `decoy catalog list`

List all entries in the local metadata catalog.

The catalog is backed by DuckDB at .decoy/catalog.duckdb. Entries are
added with `decoy catalog add`. This command is read-only.

LOCAL ONLY: the catalog does not sync with the platform server. For
platform-managed job history and file registries, use the Web UI.

**Usage**:

```console
$ decoy catalog list [OPTIONS]
```

**Options**:

* `--workspace TEXT`: Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.
* `--json`: Emit structured JSON on stdout.
* `-q, --quiet`: Suppress stdout.
* `-v, --verbose`: Enable debug-level logs.
* `--help`: Show this message and exit.

Examples:

  decoy catalog list
    List all catalog entries. Searches upward from cwd for .decoy/.

  decoy catalog list --json
    Emit a structured JSON result with the entries array.

  decoy catalog list --workspace /path/to/project
    List entries for an explicit workspace location.

What catalog stores:
  - Dataset registrations (file path, name, format, type).
  - No raw source data or PII values are stored.
  - sensitivity_class tags whether each entry is evidence-safe,
    redacted-shareable, or full-sensitive.

See also: decoy catalog add, decoy catalog show, decoy project init.


### `decoy catalog add`

Register an artifact path in the local metadata catalog.

Records the path, entry type, name, timestamp, and sensitivity class in
the DuckDB catalog at .decoy/catalog.duckdb. Raw source data is NOT
copied into DuckDB -- only metadata is stored.

Use --sensitivity to tag entries: evidence-safe (default, manifests and
summaries), redacted-shareable (profiles with raw values removed), or
full-sensitive (local diagnostics that may contain sensitive values like
full STORM profiles).

LOCAL ONLY: catalog entries are not synced with the platform server.

**Usage**:

```console
$ decoy catalog add [OPTIONS] PATH
```

**Arguments**:

* `PATH`: Path to the artifact (file or directory) to register in the catalog.  [required]

**Options**:

* `--name TEXT`: Name for this entry (default: file stem of the path).
* `--type TEXT`: Entry type: dataset, run, evidence, scan, report (default: dataset).  [default: dataset]
* `--sensitivity TEXT`: Sensitivity class: evidence-safe (default), redacted-shareable, full-sensitive. Use full-sensitive for raw STORM profiles that may contain sensitive values.  [default: evidence-safe]
* `--json`: Emit structured JSON on stdout.
* `-q, --quiet`: Suppress stdout.
* `-v, --verbose`: Enable debug-level logs.
* `--workspace TEXT`: Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.
* `--help`: Show this message and exit.

Examples:

  decoy catalog add ./data/customers.csv
    Register a dataset file in the catalog.

  decoy catalog add ./data/customers.csv --name customers_v2
    Override the default name (file stem).

  decoy catalog add ./data/customers.csv --type dataset --json
    Specify entry type and emit structured JSON with the new entry id.

  decoy catalog add ./data/customers.csv --sensitivity full-sensitive
    Tag the entry as a sensitive local artifact (e.g. a full STORM profile).

Sensitivity classes:
  evidence-safe        -- manifest/summary data excluding raw values (default).
  redacted-shareable   -- profile or summary with raw values removed.
  full-sensitive       -- local diagnostic that may contain sensitive values.

What catalog add does NOT do:
  - It does NOT copy raw source data into DuckDB.
  - It does NOT sync the registration with the platform server.
  - It does NOT scan or profile the file (use `decoy storm scan` for that).

See also: decoy catalog list, decoy catalog show, decoy storm scan.


### `decoy catalog show`

Show the full details of a catalog entry.

The entry id can be the full UUID or a prefix (at least 4 characters).
Use `decoy catalog list` to see all entry ids.

LOCAL ONLY: the catalog does not sync with the platform server.

**Usage**:

```console
$ decoy catalog show [OPTIONS] ENTRY_ID
```

**Arguments**:

* `ENTRY_ID`: Entry id (or id prefix) to show.  [required]

**Options**:

* `--json`: Emit structured JSON on stdout.
* `-q, --quiet`: Suppress stdout.
* `-v, --verbose`: Enable debug-level logs.
* `--workspace TEXT`: Workspace root (default: search upward from cwd). Overrides DECOY_WORKSPACE_ROOT.
* `--help`: Show this message and exit.

Examples:

  decoy catalog show <id>
    Show the full entry for a given id (prefix match supported).

  decoy catalog show <id> --json
    Emit structured JSON for the entry.

  decoy catalog show <id> --workspace /path/to/project
    Show entry from an explicit workspace location.

See also: decoy catalog list, decoy catalog add.
