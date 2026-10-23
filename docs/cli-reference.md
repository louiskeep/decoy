# `decoy`

Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy scan data.csv              Profile a dataset for PII and re-id risk (candidates as suggestions).
  decoy validate pipeline.yaml     Run the whole pre-run gate (config + compile + preflight).
  decoy validate compile pipeline.yaml --explain  Explain per-column strategy and compile decisions.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy subset pipeline.yaml --dry-run   Preview a FK-aware referential subset.
  decoy unmask pipeline.yaml masked.csv   Recover fpe columns from a masked file.
  decoy fit source.csv             Fit a distribution snapshot for statistical generation.
  decoy init                       Scaffold a starter pipeline interactively.
  decoy list templates             Browse bundled pipeline templates.
  decoy show template hipaa        Dump one bundled template to stdout.
  decoy explain modes              Plain-English topic help. `explain` lists topics.
  decoy info                       Branded splash + quick-start hints.
  decoy report show evidence.json  Render the evidence report from an evidence manifest file.
  decoy report diff a.json b.json  Data-level compare between two evidence manifests.

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
* `unmask`: Recover fpe-masked columns from a masked...
* `fit`: Fit a distribution-snapshot/v1 artifact...
* `init`: Scaffold a starter pipeline YAML through a...
* `demo`: Walk through scan -&gt; mask on a bundled...
* `explain`: Explain a Decoy concept in plain English.
* `info`: Print the Decoy CLI banner with...
* `schema`: Print the PipelineConfig JSON Schema to...
* `list`: List the contents of one engine registry.
* `show`: Show detail for one reference item.
* `doctor`: Check engine and dependency health.
* `subset`: Cut a referentially-complete FK-aware...
* `validate`: Pre-run validation gate.
* `scan`: Profile a dataset for PII and...
* `storm`: Masked-file verification -- `integrity`...
* `vault`: Vault inspection utilities.
* `evidence`: Show and verify local run evidence manifests.
* `report`: Render, summarize, and compare local...

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
* `--master-key TEXT`: 64-char hex master key for keyed deterministic SYNTHETIC GENERATION only (generate_columns:). Same key + same --key-label always yield bitwise-identical generated output across runs and machines. Reads DECOY_MASTER_KEY env var when omitted; without either, generation falls back to the legacy seeded path (per-input deterministic but not portable). This flag does NOT affect masking -- masking&#x27;s keyed determinism is configured separately via &#x27;--mask-secret&#x27; (or the pipeline YAML&#x27;s &#x27;global_settings.mask_secret_ref&#x27;), never this flag or its env var. See: decoy explain keys.  [env var: DECOY_MASTER_KEY]
* `--mask-secret TEXT`: env:NAME or file:/PATH pointing at a &gt;=32-byte mask secret for keyed masking (mask: strategies -- fpe, hash, date_shift, and others). Independent of --master-key (which is generation-only). Sets &#x27;global_settings.mask_secret_ref&#x27; for this run; an error if the YAML already sets it. Explicit flag only -- it deliberately has NO env var, because the ref it carries (e.g. &#x27;env:DECOY_MASK_SECRET&#x27;) already indirects through the environment; a second env layer would absorb the raw exported secret as this flag&#x27;s value. See: decoy explain keys.
* `--chunked`: Stream the source through the engine chunk-by-chunk, for inputs too large to load whole. Works for mask configs whose every strategy is value-keyed (hash, fpe, redact, truncate, text_redact, date_shift, bucketize), plus faker/categorical when deterministic with an explicit pool_size / categories declared in config; output is byte-identical to a plain run. Sources are read by their declared format (csv or parquet; fixed_width is not supported with --chunked); targets are written by file suffix. See: decoy explain chunked.
* `--chunk-size INTEGER RANGE`: Rows per chunk in --chunked mode.  [default: 100000; x&gt;=1]
* `--vault PATH`: Write the token vault (encrypted source-to-masked map for vault: true columns) to this path. The vault plus the config re-identify every vaulted value: store them separately and never alongside the masked output. Needs the engine&#x27;s vault extra (cryptography).
* `--substrate TEXT`: Execution substrate for --chunked runs. pandas is the only substrate (the default); any other value, including the removed &#x27;polars&#x27;, is rejected with a usage error. Non-chunked (plain) runs always use the engine&#x27;s pandas adapter; this flag and the DECOY_SUBSTRATE env var are consulted only for --chunked runs, and setting either on a plain run emits a warning to stderr and is otherwise ignored.  [env var: DECOY_SUBSTRATE]
* `--key-label TEXT`: Stable namespace string for the --master-key generation key hierarchy (synthetic generation only, not masking). Required when --master-key is set. Pick something durable (e.g. &#x27;customers_q4&#x27;); changing it produces different generated output. CLI flag only -- PipelineConfig forbids unknown top-level keys, so there is no YAML equivalent.
* `--evidence-out PATH`: Write a local evidence manifest (JSON) to this path after a successful run. The manifest records pipeline hash, input/output file fingerprints, run metadata, and row counts/timings/warnings where available (these are omitted for --chunked runs). It does NOT contain raw data values. Use `decoy evidence verify` to check the manifest against current files. See: decoy explain evidence (when available).
* `--notify TEXT`: Notify a channel after the run reaches its terminal state. Repeatable. Spec is &#x27;kind:target&#x27;: webhook:&lt;url&gt;, slack:&lt;url&gt;, email:&lt;address&gt;. Best-effort: a channel failure never changes the run&#x27;s exit code. Webhook signing key from DECOY_NOTIFY_WEBHOOK_SECRET (unsigned if unset); SMTP from DECOY_NOTIFY_SMTP_HOST/_PORT/_USER/_PASS/_FROM. Nothing is persisted to .decoy/workspace.json -- targets and secrets are flags/env only, never written to disk.
* `--notify-on [success|failure|always]`: Which terminal outcome(s) to notify on: success, failure, or always.  [default: always]
* `--native`: Require that a compiled native kernel actually executed. Refuses up front (no run) on --chunked or a generate/mixed config, or on an absent/broken decoy-engine-native companion. Refuses AFTER the run, before any output is written, if the job finished without positive compiled-kernel evidence (e.g. an FK table or a table masked only with passthrough/redact/truncate). Mutually exclusive with --no-native. See: decoy explain native.
* `--no-native`: Force the legacy pandas adapter, bypassing the unified slice entirely -- the documented rollback for native-on-when-present. Mutually exclusive with --native. See: decoy explain native.
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

  decoy run pipeline.yaml --chunked
    Stream a large single-table mask in bounded memory (pandas chunked path).
    (Masking uses the pandas substrate. See: decoy explain substrate.)

  decoy run pipeline.yaml --notify webhook:https://hooks.example.com/x
    Notify a webhook after the run reaches its terminal state. Repeatable;
    kind in webhook/slack/email. Best-effort: a channel failure never
    changes the run's exit code. Webhook signing key from
    DECOY_NOTIFY_WEBHOOK_SECRET; SMTP from DECOY_NOTIFY_SMTP_HOST/_PORT/
    _USER/_PASS/_FROM. Nothing is persisted to .decoy/workspace.json.

  decoy run pipeline.yaml --notify slack:https://hooks.slack.com/services/x --notify-on failure
    Only notify on a failed run.

See also: decoy validate config, decoy validate distribution, decoy explain chunked, decoy explain vault.


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

Without --epsilon: reads the source CSV, captures per-column
distribution shape (numeric histograms + quantiles, categorical top-k,
datetime year bins) plus any requested pairwise contingency tables, and
writes the JSON artifact `type: statistical` generate columns reference
via `snapshot_file`.

With --epsilon: fits a `dps-marginal/v3` artifact instead, releasing
ONLY the columns declared via --dp-number/--dp-flag/--dp-text under one
(epsilon, delta) budget. Exits 0 on success, 1 on bad input, 3 if the
engine&#x27;s DP fit refuses at run time (an uncertified proof stack, or an
internal schedule invariant).

**Usage**:

```console
$ decoy fit [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: Source CSV to fit the distribution snapshot from.  [required]

**Options**:

* `-o, --output PATH`: Where to write the snapshot JSON. Default: &lt;source&gt;.snapshot.json.
* `--parse-dates TEXT`: Column(s) to parse as datetimes (repeatable). CSV carries no dtype, so date columns must be named explicitly. Not supported with --epsilon.
* `--joint TEXT`: Column pair &#x27;a,b&#x27; whose contingency table to capture (repeatable). Needed for `condition_on`. Not supported with --epsilon.
* `--epsilon FLOAT`: Select DP mode: fit a dps-marginal/v3 artifact via the engine&#x27;s fit_dp_snapshot instead of the exact snapshot. Requires --delta and at least one carrier declaration (--dp-number/--dp-flag/--dp-text). This is the ONLY DP-mode selector -- every DP-only option is a usage error without it, so a forgotten --epsilon never silently falls back to the exact release.
* `--delta FLOAT`: DP failure probability, required with --epsilon (no default: a silent delta would set an unchosen privacy level). Finite, in (0, 1).
* `--dp-number TEXT`: &#x27;COL:LO:HI&#x27; -- declare COL as a DP numeric carrier with a data-independent domain (repeatable). Requires --epsilon.
* `--dp-flag TEXT`: Declare COL as a DP boolean/flag carrier (repeatable). Requires --epsilon.
* `--dp-text TEXT`: Declare COL as a DP categorical text carrier (repeatable). Requires --epsilon.
* `--numeric-bins INTEGER`: Bin count per DP numeric column (engine default if omitted). Requires --epsilon.
* `--dp-allow-omit`: Allow the DP release to omit source columns nobody declared with --dp-number/--dp-flag/--dp-text (default: omission is a usage error listing the columns). Requires --epsilon.
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

  decoy fit customers.csv --epsilon 1.0 --delta 1e-6 \
      --dp-number amount:0:500 --dp-text state --dp-flag is_active
    Differentially private release (dps-marginal/v3): every declared
    column is released under one (epsilon, delta) budget through OpenDP.
    Every column MUST be declared with a carrier (--dp-number for a
    numeric column plus its data-independent domain, --dp-text for a
    categorical column, --dp-flag for a boolean column); an undeclared
    source column is a usage error unless --dp-allow-omit is passed.
    --epsilon requires --delta and is incompatible with --joint and
    --parse-dates.

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

* `-o, --output PATH`: Where to write the pipeline YAML. Use `-` to write to stdout.  [default: pipeline.yaml]
* `--preset TEXT`: Skip the preset prompt and use this template directly.
* `-y, --yes`: Skip overwrite confirmation.
* `--json`: Skip the wizard; emit a JSON record of what was written.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy init
    Interactive Q&A; writes pipeline.yaml in the current directory.

  decoy init --preset hipaa --output hipaa_pipeline.yaml
    Skip the wizard; scaffold from the HIPAA template.

  decoy init customers.csv --output pipeline.yaml
    Column-aware scaffolding (OSS.4c, 2026-06-02). Runs STORM against
    the file, picks a starter strategy per column from the inference
    table, writes the YAML with `# REVIEW:` comments above every
    inferred entry. The user must read + edit before running.

  decoy init --yes
    Skip confirmation when overwriting an existing file.

See also: decoy validate config, decoy run, decoy scan, decoy list templates.


## `decoy demo`

Walk through scan -&gt; mask on a bundled sample dataset.

Use this on a fresh install to see what Decoy can do end to end without
needing your own data or pipeline. All output lands in `./decoy_demo/`
(override with `--dir`).

**Usage**:

```console
$ decoy demo [OPTIONS]
```

**Options**:

* `--dir PATH`: Where to drop the demo artifacts.  [default: decoy_demo]
* `--json`: Emit a JSON summary instead of cards.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy demo
    Run the simple scan -> mask walkthrough in ./decoy_demo/.

  decoy demo --json
    Same flow, but emit a JSON summary instead of cards.

See also: decoy scan, decoy run.


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

See also: decoy --help, decoy list templates.


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

See also: decoy --help, decoy explain, decoy list templates.


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

See also: decoy validate, decoy list templates.


## `decoy list`

List the contents of one engine registry.

One verb over the live registries: strategies, providers, checksums,
validators, templates, and regulatory disguise bundles.

**Usage**:

```console
$ decoy list [OPTIONS] KIND
```

**Arguments**:

* `KIND`: What to list: strategies|providers|checksums|validators|templates|disguises.  [required]

**Options**:

* `--json`: Emit the listing as a JSON envelope instead of a table.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy list strategies
    Every registered mask strategy with its class.

  decoy list providers --json
    Every generation provider as JSON.

  decoy list disguises
    The regulatory Disguise bundles (hipaa, gdpr, ...) with rule counts.

Kinds: strategies, providers, checksums, validators, templates, disguises.

See also: decoy show, decoy explain.


## `decoy show`

Show detail for one reference item.

`show strategy|provider|template NAME` gives per-item detail; `show schema`
prints the PipelineConfig JSON Schema (`--output` writes it to a file).
Note: `decoy scan show SCAN FIELD` is a different `show` -- it reports a
field from a saved scan, not a reference item.

**Usage**:

```console
$ decoy show [OPTIONS] KIND [NAME]
```

**Arguments**:

* `KIND`: What to show: strategy|provider|template (needs NAME), or schema.  [required]
* `[NAME]`: Which item to show. Required for strategy/provider/template; omit for schema.

**Options**:

* `-o, --output PATH`: (schema only) Write the schema to this file instead of stdout.
* `--json`: Emit a JSON record instead of human output.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy show strategy fpe
    Details for one mask strategy.

  decoy show provider person_name --json
    One provider's capability matrix as JSON.

  decoy show template hipaa > pipeline.yaml
    Dump one bundled template to stdout.

  decoy show schema -o decoy.schema.json
    Write the PipelineConfig JSON Schema to a file.

Kinds: strategy, provider, template (NAME required); schema (no NAME).

See also: decoy list, decoy validate.


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


## `decoy subset`

Cut a referentially-complete FK-aware subset of a relational dataset.

Seeds a subset of root-table rows (per the config&#x27;s `subset.seeds:`
block) and pulls every row needed to keep foreign keys intact: children
of a surviving parent (downward) and, by default, every parent of a
surviving child (upward -- prevents dangling FKs). Runs a fail-closed
preflight first (Parquet-only, schema/type checks, source-orphan scan)
and a budget check before any output is written.

`--dry-run` computes the same estimate and writes nothing; use it to see
the projected row counts before committing to a real run.

**Usage**:

```console
$ decoy subset [OPTIONS] CONFIG
```

**Arguments**:

* `CONFIG`: Path to the YAML pipeline config (must declare a subset: block).  [required]

**Options**:

* `-o, --output PATH`: Output directory for the filtered Parquet + subset-manifest.json. Required unless --dry-run. Must not already exist as a non-empty directory.
* `--dry-run`: Compute the projected per-table row counts and print them WITHOUT materializing anything. No Parquet is written, no output_dir is created or touched. Use this before every real run.
* `--json`: Emit a structured JSON result on stdout.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr; exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy subset pipeline.yaml --dry-run
    Compute and print the projected per-table row counts WITHOUT writing
    anything. Runs the full preflight + closure estimate. Always do this
    before a real run on data you have not subsetted before.

  decoy subset pipeline.yaml --output subset_out/
    Run the subset for real: write filtered Parquet per table plus
    subset-manifest.json into subset_out/. subset_out/ must not already
    exist (or must be empty).

  decoy subset pipeline.yaml --output subset_out/ --json
    Same as above, structured JSON result on stdout.

The pipeline YAML must declare a `subset:` block (seeds + optional budget /
edge_directions / allow_dangling) alongside its `relationships:` block --
the same config surface `decoy run` reads. See `decoy schema` for the full
shape.

What this command checks before touching any data:
  - Every subsetted/relationship table's source is Parquet (subsetting does
    not run on CSV; the error names the offending table).
  - Every relationship edge's key columns exist, are type-compatible, and
    are not a half-declared composite.
  - Source-level FK orphans, per each relationship's orphan_policy.
  - The fan-out budget (max_total_rows / max_table_seed_multiple), BEFORE
    any output directory is created.

See also: decoy run, decoy validate, decoy validate preflight.


## `decoy validate`

Pre-run validation gate. `decoy validate CONFIG` runs the whole gate (config + compile + preflight) and emits one report + one exit code. Subcommands run a single layer: schema + config checks (`config`), plan compilation + checks (`compile`), source/capacity readiness (`preflight`), and post-run distribution fidelity (`distribution`).

**Usage**:

```console
$ decoy validate [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

Examples:

  decoy validate pipeline.yaml
    Run the whole pre-run gate (config + compile + preflight): one report
    grouped by layer, one aggregated exit code.

  decoy validate config pipeline.yaml
    Schema + config-only checks (fast, no source read).

  decoy validate compile pipeline.yaml --explain
    Compile the plan, run plan-compile checks, explain per-column decisions.

  decoy validate preflight pipeline.yaml
    Source / file / schema readiness + capacity estimate + native probe.

  decoy validate distribution source.csv output.csv
    Recompute distribution fidelity between a pre-mask source and its
    masked output (post-run; moving to `report fidelity` in S4).

See also: decoy run, decoy fit.


**Commands**:

* `config`: Validate a decoy pipeline config without...
* `distribution`: Recompute distribution fidelity between a...
* `compile`: Compile a pipeline config and run...
* `preflight`: Local pre-run readiness checks for a...

### `decoy validate config`

Validate a decoy pipeline config without running it.

Use this in CI or before a long run to fail fast on a bad YAML. Exits 0
on a well-formed config, 1 on a parse / schema error or a config-level
plan-compile error (unknown provider, non-poolable provider on the
faker/pool path, missing deterministic namespace).

With --fail-on-warning, also exits non-zero when advisory warnings fire
(e.g. an output file already exists and would be overwritten on run).

**Usage**:

```console
$ decoy validate config [OPTIONS] CONFIG
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

  decoy validate config pipeline.yaml
    Print OK on stdout when the config parses.

  decoy validate config pipeline.yaml --json
    Emit a structured JSON result (multi-message) for scripting.

  decoy validate config pipeline.yaml --quiet
    Stay silent on success; exit code carries the result.

  decoy validate config pipeline.yaml --fail-on-warning
    Exit non-zero if any advisory warning fires (e.g. output target exists).

See also: decoy run, decoy validate distribution.


### `decoy validate distribution`

Recompute distribution fidelity between a source and an output CSV.

Wraps `decoy_engine.quality.compute_quality_report` +
`apply_quality_policy` (report.py:97, policy.py:142): the engine owns
every metric and the letter grade; this command computes no fidelity
number itself. Reads both CSVs fresh on every invocation (pure,
repeatable) -- the CLI&#x27;s local evidence manifest records file
fingerprints but not the raw frames, so recomputing from the two files
is the only honest source for this number (BF1).

Exit codes: 0 when the policy verdict is &#x27;pass&#x27; (or &#x27;warn&#x27; without
--fail-on-warning); EXIT_FINDINGS (4) when the verdict is &#x27;fail&#x27;, or
&#x27;warn&#x27; with --fail-on-warning set. This mirrors `decoy storm
integrity`&#x27;s exit-code contract -- a data-audit verb that reports
findings, not a run that crashed -- rather than EXIT_RUNTIME (reserved
for the CLI/engine blowing up unexpectedly).

**Usage**:

```console
$ decoy validate distribution [OPTIONS] SOURCE OUTPUT
```

**Arguments**:

* `SOURCE`: Pre-mask / pre-generate source CSV (ground truth).  [required]
* `OUTPUT`: Post-mask / post-generate output CSV to check.  [required]

**Options**:

* `--joint TEXT`: Column pair &#x27;a,b&#x27; to also score jointly (repeatable).
* `--generate`: Output is synthetic generation, not masking: row counts may legitimately differ (sets expect_row_parity=False). Default assumes masking (row parity expected).
* `--config FILE`: Pipeline YAML naming each column&#x27;s strategy, so intentional loss (hash, bucketize, faker, ...) is not flagged as accidental drift. Without it, per-column policy checks run on defaults only.
* `--policy FILE`: A quality-policy config (YAML or JSON: mode / thresholds / strategy_expectations) overriding --mode / --min-grade / --min-score.
* `--mode TEXT`: report (record only, verdict always pass) | warn (violations promote verdict to warn) | fail (violations promote verdict to fail). Ignored when --policy sets its own mode.  [default: report]
* `--min-grade TEXT`: Shorthand: minimum letter grade (A/B/C/D) the overall score must reach.
* `--min-score FLOAT`: Shorthand: minimum overall_score in [0, 1].
* `--fail-on-warning`: Also exit non-zero (EXIT_FINDINGS) when the policy verdict is &#x27;warn&#x27;.
* `--report-out PATH`: Write the full quality-report/v1 + policy JSON to this path.
* `--json`: Emit the full quality-report/v1 + policy result as JSON.
* `-q, --quiet`: Suppress stdout. Exit code carries the result.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy validate distribution source.csv output.csv
    Recompute distribution fidelity between a pre-mask source and its
    masked output. Report mode (record only): always exits 0.

  decoy validate distribution source.csv output.csv --config pipeline.yaml
    Pass the pipeline config so intentional loss (hash, bucketize, ...)
    is not flagged as accidental drift.

  decoy validate distribution source.csv synthetic.csv --generate
    Row counts are expected to differ (synthetic generation, not masking).

  decoy validate distribution source.csv output.csv --mode fail --min-grade B
    Exit non-zero (EXIT_FINDINGS) when the overall grade falls below B.

  decoy validate distribution source.csv output.csv --joint state,tier --json
    Include a (state, tier) joint fidelity score; emit the full
    quality-report/v1 + policy JSON.

  decoy validate distribution source.csv output.csv --report-out report.json
    Also write the full report + policy verdict to disk.

Exit codes: 0 pass (or warn without --fail-on-warning); 4 EXIT_FINDINGS
when the policy verdict is fail, or warn with --fail-on-warning set;
1 EXIT_USAGE for bad input (missing columns, unreadable CSV, bad flags).

Note: the sibling `validate config --fail-on-warning` exits 2 for its
warnings (config well-formedness), while this command exits 4 for its
warnings (data-fidelity findings). The two subcommands intentionally use
different warning exit codes for their different domains.

See also: decoy validate config, decoy fit, decoy run.


### `decoy validate compile`

Compile a pipeline config and run plan-compile checks.

Use --explain to see per-column strategy, params, and rationale for each
compile decision. Without --explain, shows a compact pass/fail summary.
Use --profile to run the profile-dependent checks, and --output to also
write the frozen plan artifact (the folded `plan` behavior).

HONESTY: compile explains what is in the config and what the compiler
verified. It does not guarantee correctness, PII coverage, or safety.

**Usage**:

```console
$ decoy validate compile [OPTIONS] CONFIG
```

**Arguments**:

* `CONFIG`: Path to the pipeline YAML config to compile.  [required]

**Options**:

* `--explain`: Explain the compiled plan: per-column declared strategy, params, execution order, and rationale. Without this flag, only the compile pass/fail summary is shown.
* `--profile FILE`: Path to a pre-computed Profile JSON file. Runs ALL plan-compile checks, including the profile-dependent ones. Without it, --no-profile mode is used (profile-dependent checks are skipped).
* `--no-profile`: Compile without source data (the default). Profile-dependent checks land in plan_compile.checks_skipped. Incompatible with --profile.
* `-o, --output PATH`: Also write the frozen plan artifact to this path (absorbs the old `plan` command).
* `--format TEXT`: On-disk format for the --output artifact: yaml (default) or json.  [default: yaml]
* `--json`: Emit structured JSON instead of the styled table output.
* `-q, --quiet`: Suppress stdout. Exit code carries success or failure.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy validate compile pipeline.yaml
    Compile a recipe and show pass/fail for all compile checks (--no-profile).

  decoy validate compile pipeline.yaml --explain
    Compile a recipe and show per-column declared strategy, params, and rationale.

  decoy validate compile pipeline.yaml --profile profile.json
    Load a pre-computed Profile and run ALL plan-compile checks (none skipped).

  decoy validate compile pipeline.yaml --output plan.yaml
    Also write the frozen plan artifact to plan.yaml (YAML; use --format json for JSON).

  decoy validate compile pipeline.yaml --explain --json
    Same as --explain but as structured JSON for scripting or CI.

  decoy validate compile pipeline.yaml --explain --quiet
    Silent compile; exit code 0 = all checks passed.

HONESTY: compile --explain explains decisions declared in the config and what the
compiler verified. It does not guarantee the strategy is correct for the data,
that all PII is covered, or that the output is safe to share.

See also: decoy validate, decoy validate config, decoy scan.


### `decoy validate preflight`

Local pre-run readiness checks for a pipeline config.

Checks file existence, file readability, YAML syntax, schema validity,
and (v1) the engine&#x27;s out-of-core-FK memory feasibility. The build-floor
estimate is advisory: an over-budget prediction reports a WARNING with a
recommended size, not a refusal (`--fail-on-warning` makes it exit
nonzero). Only a fan-in impossibility exits EXIT_CAPACITY (see `decoy
explain exit-codes`), distinct from a config problem (EXIT_USAGE). Reports
findings as pass/warn/fail with structured output available via --json.

This is a LOCAL check only. It does NOT check platform server-side
conditions, most engine run-time constraints, data quality, vault
access, secrets availability, or network connectivity. The capacity
check covers the out-of-core-FK route only -- it does not cover the
ingestion peak `decoy run` pays before the engine&#x27;s gate runs, or the
generate path. Use `decoy validate` for pure schema-only checks; use
this command when you want to confirm source files are present and check
the job&#x27;s capacity feasibility before starting a run.

**Usage**:

```console
$ decoy validate preflight [OPTIONS] CONFIG
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

  decoy validate preflight pipeline.yaml
    Run local readiness checks: YAML validity, schema, and source file existence.

  decoy validate preflight pipeline.yaml --local
    Same as above (--local is the explicit form; all checks are local by default).

  decoy validate preflight pipeline.yaml --json
    Emit a structured JSON result with per-check findings.

  decoy validate preflight pipeline.yaml --fail-on-warning
    Exit non-zero when advisory warnings fire (e.g. output already exists).

What preflight checks:
  - YAML syntax and schema (same as `decoy validate`)
  - Source file existence and readability
  - Target overwrite risk (advisory warning)
  - Out-of-core-FK memory capacity (v1; build-floor is advisory, only a fan-in
    impossibility exits EXIT_CAPACITY -- see: decoy explain exit-codes)
  - Native companion health, plus a STATIC (config-shape-only) native
    eligibility possibility -- see: decoy explain native

What preflight does NOT check:
  - Platform server-side conditions (secrets, RBAC, schedules, network targets)
  - Engine run-time constraints beyond out-of-core-FK capacity (row counts,
    provider limits)
  - The ingestion peak `decoy run` pays before the engine's capacity gate runs,
    or the generate path (both out of the v1 capacity check's scope)
  - Data validity or masking quality
  - Vault or secrets accessibility

See also: decoy validate, decoy run, decoy evidence verify, decoy explain exit-codes.


## `decoy scan`

Profile a dataset for PII and re-identification risk. `decoy scan SOURCE` scans a CSV/Parquet/fixed-width file (shape, field stats, PII candidates as suggestions, quasi-identifiers, reid risk) and, with `--output scan.json`, saves the scan. Subcommands operate on a saved scan: list fields (`fields`), per-field detail (`show`), compare two scans (`diff`).

**Usage**:

```console
$ decoy scan [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

Examples:

  decoy scan data.csv
    Profile a CSV: row/field counts, PII candidates (as suggestions), reid risk.
    Reads the first 10 000 rows by default (--rows 0 for a full scan).

  decoy scan data.csv --show-fields
    Per-field detail: dtype, null_rate, distinct_count, PII candidate flag.

  decoy scan data.csv --rows 50000 --strategy random
    Sample 50K random rows instead of the first 10 000.

  decoy scan data.csv --output scan.json
    Save the scan to scan.json, then: decoy scan fields scan.json

  decoy scan data.csv --output -
    Stream the scan JSON to stdout for downstream tooling.

  decoy scan records.fwf --layout layout.yaml
    Scan a fixed-width file using an explicit column layout.
    Layout YAML: columns: [{name: id, start: 0, width: 5}, ...]

HONESTY: PII candidates are SUGGESTIONS based on STORM pattern matching. They
are NOT authoritative classifications. You review each flagged field and decide
what masking to apply. Decoy never auto-classifies PII.

No raw cell values appear in the inline output. Field stats include dtype,
null_rate, distinct_count only.

See also: decoy scan fields, decoy scan show, decoy scan diff,
  decoy explain storm, decoy validate.


**Commands**:

* `fields`: List fields from a saved scan, with...
* `show`: Per-field detail from a saved scan.
* `diff`: Compare two scans -- catch schema, PII,...

### `decoy scan fields`

List fields from a saved scan, with optional filters.

Print the fields that matter, filter by PII bucket or quasi-identifier
membership, pipe the result somewhere else. For per-field detail, see
`decoy scan show`.

**Usage**:

```console
$ decoy scan fields [OPTIONS] SCAN
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

  decoy scan fields scan.json
    List every field with PII score, bucket, quasi-identifier flag.

  decoy scan fields scan.json --pii high --quasi
    Only fields that are high PII *and* part of a quasi-identifier group.

  decoy scan fields scan.json --json | jq '.fields[].name'
    Pipe just the matching field names somewhere else.

See also: decoy scan, decoy scan show.


### `decoy scan show`

Per-field detail from a saved scan.

The drill-down view of one field: PII score + bucket, detector matches,
sentinel hits, top values, quasi-identifier membership. Read-only.

**Usage**:

```console
$ decoy scan show [OPTIONS] SCAN FIELD
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

  decoy scan show scan.json ssn
    Per-field detail card -- PII score, detectors, sentinels, top values, QI.

  decoy scan show scan.json email --json
    Same data as a structured JSON envelope.

  decoy scan data.csv --output - | decoy scan show - ssn
    Pipe a fresh scan straight in.

See also: decoy scan, decoy scan fields.


### `decoy scan diff`

Compare two scans -- catch schema, PII, and risk drift.

Designed for CI: run `decoy scan diff baseline.json new.json --strict`
on every PR to fail the build when a column&#x27;s PII bucket goes up, a new
high-PII field appears, or a new quasi-identifier group forms. Read-only
-- the scans are JSON; raw data never enters the CLI.

**Usage**:

```console
$ decoy scan diff [OPTIONS] OLD NEW
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

  decoy scan diff baseline.json new.json
    Print field-, PII-, QI-, and risk-level differences between two scans.

  decoy scan diff baseline.json new.json --strict
    Same, but exit 1 on drift (PII bucket bumped up, new high-PII field, or
    new quasi-identifier group). Wire this into CI.

  decoy scan diff baseline.json new.json --json | jq '.drift'
    Boolean drift flag for scripting.

See also: decoy scan, decoy scan fields.


## `decoy storm`

Masked-file verification -- `integrity` checks a masked file against its pre-mask source (post-run; moves to `report integrity` in S4). Pre-run profiling now lives in `decoy scan`.

**Usage**:

```console
$ decoy storm [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `integrity`: Verify a masked file&#x27;s integrity against...

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
* `-o, --output PATH`: Write the JobStormReport JSON to this path. The Rich table still renders to stderr.
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

  decoy storm integrity masked.csv --source source.csv --output report.json
    Write JSON to file + render a Rich summary on stderr.

Exit codes: 0 clean (no fail/error findings); 4 EXIT_FINDINGS (one
or more fail-severity findings); 1 EXIT_USAGE for missing files;
3 EXIT_RUNTIME for unexpected exceptions.

See also: decoy scan, decoy run, decoy explain exit-codes.


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
* `show`: Render the evidence report from an...
* `diff`: Compare output data files from two...

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

* `-o, --output PATH`: Output file path (e.g. report.html or report.md).  [required]
* `--format TEXT`: Output format: &#x27;html&#x27; (default) or &#x27;markdown&#x27;.  [default: html]
* `--json`: Emit a JSON record of what was written instead of the human summary.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy report render evidence.json --output report.html
    Render the manifest as a self-contained offline HTML report.

  decoy report render evidence.json --format markdown --output report.md
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

* `--json`: Emit the evidence manifest as JSON instead of the card.
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


### `decoy report show`

Render the evidence report from an evidence manifest file.

Loads the evidence manifest at the given path and renders it using the
same format as `decoy report summarize` (terminal) or `decoy report
render` (file output with --format and --output).

Reads only the file it is given; never connects to a server or catalog.

**Usage**:

```console
$ decoy report show [OPTIONS] EVIDENCE_FILE
```

**Arguments**:

* `EVIDENCE_FILE`: Path to an evidence manifest JSON (from `decoy run --evidence-out`).  [required]

**Options**:

* `--format TEXT`: Output format when --output is given: &#x27;html&#x27; or &#x27;markdown&#x27;. Without --output, prints a terminal summary.
* `-o, --output PATH`: Write the report to this file path (requires --format).
* `--json`: Emit the evidence manifest as JSON.
* `-q, --quiet`: Suppress stdout.
* `-v, --verbose`: Enable debug-level logs.
* `--help`: Show this message and exit.

Examples:

  decoy report show evidence.json
    Print a summary of the evidence manifest to the terminal.

  decoy report show evidence.json --format html --output report.html
    Write a full HTML report from the evidence manifest.

  decoy report show evidence.json --json
    Emit the raw evidence manifest as structured JSON.

Requirements:
  - An evidence manifest JSON produced by `decoy run --evidence-out`.

See also: decoy report summarize, decoy report render.


### `decoy report diff`

Compare output data files from two evidence manifests at the data level.

Loads both evidence manifests, reads the output data files referenced in
them, and compares:
  - Per-table row counts
  - Schema (columns added/removed/type-changed)
  - Per-column null-count and unique-count deltas

EVIDENCE-SAFE: only aggregate counts are reported -- no raw values.
See `decoy report compare` for manifest-level (fingerprint) comparison.
Reads only the files it is given; never connects to a server or catalog.

**Usage**:

```console
$ decoy report diff [OPTIONS] EVIDENCE_FILE_A EVIDENCE_FILE_B
```

**Arguments**:

* `EVIDENCE_FILE_A`: Path to the first evidence manifest JSON.  [required]
* `EVIDENCE_FILE_B`: Path to the second evidence manifest JSON.  [required]

**Options**:

* `--json`: Emit structured JSON.
* `-q, --quiet`: Suppress stdout.
* `-v, --verbose`: Enable debug-level logs.
* `--help`: Show this message and exit.

Examples:

  decoy report diff a.json b.json
    Compare the output data files referenced by two evidence manifests at the
    data level.

  decoy report diff a.json b.json --json
    Emit structured JSON with per-table row-count and column-level deltas.

What diff compares:
  - Row counts per table (from actual data files)
  - Schema: columns added/removed/type-changed between runs
  - Per column: null-count delta, unique-count delta

What diff does NOT compare:
  - Raw row or cell values (never -- evidence-safe by design)
  - Platform-managed state, audit logs, or remote job history
  - Pipeline config changes (use `decoy report compare` for manifest-level diff)

Scope and limitations:
  - Takes two evidence manifest JSON files (`decoy run --evidence-out`).
  - Requires the output files referenced in the evidence manifests to still
    exist at their recorded paths.
  - Compares aggregate counts only -- not a full row-by-row diff.

Methodology: pandas.Series.nunique() / .isnull().sum() for column-level
counts (pandas v2.x). No novel statistical method is used.

See also: decoy report compare (manifest-level).
