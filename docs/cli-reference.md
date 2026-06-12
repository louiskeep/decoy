# `decoy`

Decoy -- data masking and synthetic generation CLI.

Try one of:
  decoy demo                       30-second end-to-end walkthrough.
  decoy storm analyze data.csv     Profile a dataset for PII and risk.
  decoy run pipeline.yaml          Run a masking or generation pipeline.
  decoy validate pipeline.yaml     Check a YAML pipeline before running.
  decoy unmask pipeline.yaml masked.csv   Recover fpe columns from a masked file.
  decoy init                       Scaffold a starter pipeline interactively.
  decoy templates list             Browse bundled pipeline templates.
  decoy explain modes              Plain-English topic help. `explain` lists topics.
  decoy info                       Branded splash + quick-start hints.

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
* `unmask`: Recover fpe-masked columns from a masked...
* `init`: Scaffold a starter pipeline YAML through a...
* `demo`: Walk through scan -&gt; mask on a bundled...
* `explain`: Explain a Decoy concept in plain English.
* `info`: Print the Decoy CLI banner with...
* `plan`: Compile a pipeline config into a versioned...
* `replan`: Re-compile a plan from a job manifest.
* `storm`: Dataset analysis -- the STORM event.
* `templates`: Browse and dump bundled starter pipeline...

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
* `--key-label TEXT`: Stable namespace string for the masking key hierarchy. Required when --master-key is set. Pick something durable (e.g. &#x27;customers_q4&#x27;); changing it produces a different masked output. Read from the YAML&#x27;s top-level &#x27;key_label:&#x27; field if not passed on the command line.
* `--help`: Show this message and exit.

Examples:

  decoy run pipeline.yaml
    Run with default mode (mask).

  decoy run pipeline.yaml --json
    Suppress chrome and emit a structured result for scripting.

See also: decoy validate.


## `decoy validate`

Validate a decoy pipeline config without running it.

Use this in CI or before a long run to fail fast on a bad YAML. Exits 0
on a well-formed config, 1 on a parse / schema error or a config-level
plan-compile error (unknown provider, non-poolable provider on the
faker/pool path, missing deterministic namespace).

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
* `--help`: Show this message and exit.

Examples:

  decoy validate pipeline.yaml
    Print OK on stdout when the config parses.

  decoy validate pipeline.yaml --json
    Emit a JSON status object for scripting.

  decoy validate pipeline.yaml --quiet
    Stay silent on success; exit code carries the result.

See also: decoy run.


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

Only `strategy: fpe` columns are reversible; hash, redact, faker and
the other one-way strategies are reported irreversible and pass
through unchanged. The config carries the seed: treat it as a key.

See also: decoy run, decoy explain strategies.


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

Pass `--ref` to run the referential-integrity variant instead: three
related CSVs (customers, orders, payments) with foreign-key columns,
masked through three pipelines that hash the FK columns identically.
Determinism is what preserves the joins -- no shared state needed.

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

  decoy demo --ref
    Generate 3 related CSVs (customers, orders, payments) with FK
    relationships and mask all three with deterministic hashing.
    FK joins survive masking without any shared state. ~1000 rows each.

  decoy demo --ref --rows 5000 --dir my_demo
    Same, but 5K rows per dataset and a custom output directory.

  decoy demo --json
    Same flow, but emit a JSON summary instead of cards.

See also: decoy storm analyze, decoy run.


## `decoy explain`

Explain a Decoy concept in plain English.

Built-in topics: modes, transforms, disguises, output, pipeline, yaml,
storm, keys, security, completion. Run with no topic to see the
full list.

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
    The eight built-in masking transforms with one-line descriptions.

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


## `decoy replan`

Re-compile a plan from a job manifest. Not yet implemented.

The engine has no public manifest-read API today (verified in
CLI.2 audit, 2026-06-02); the manifest is a platform-side artifact
at api/jobs/v2_runner.py. Use `decoy plan &lt;pipeline.yaml&gt;` to
compile from the YAML config instead.

**Usage**:

```console
$ decoy replan [OPTIONS]
```

**Options**:

* `--from FILE`: Path to a job manifest JSON to re-compile from.  [required]
* `--source PATH`: (Optional) Override source data path; re-profile against this and re-compile.
* `--help`: Show this message and exit.

`decoy replan --from <manifest.json>` re-compiles the plan from a job
manifest. Not yet implemented: the manifest format is currently a
platform-only artifact written by api/jobs/v2_runner.py; the engine
does not expose a public manifest-read API for the CLI to consume.

Use `decoy plan <pipeline.yaml>` to compile the plan directly from the
YAML config instead. Manifest -> plan replay is on the CLI backlog;
open an issue if you need it.

See also: decoy plan.


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

**Usage**:

```console
$ decoy storm analyze [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: Path to a CSV file to scan.  [required]

**Options**:

* `--rows INTEGER`: Sample row cap. Default: scan everything.
* `--strategy [full|head|random]`: Sampling strategy when --rows is set.  [default: head]
* `--out PATH`: Where to save the scan JSON. Use - for stdout. Default: scan_&lt;timestamp&gt;.json next to the source.
* `--json`: Emit the full StormProfile JSON to stdout. No card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
* `--help`: Show this message and exit.

Examples:

  decoy storm analyze data.csv
    Analyze a CSV with default sampling, save scan_<timestamp>.json.

  decoy storm analyze data.csv --rows 50000 --strategy random
    Sample 50K random rows.

  decoy storm analyze data.csv --json > scan.json
    Pipe the full StormProfile JSON for downstream tooling.

See also: decoy storm fields, decoy storm show, decoy storm diff,
  decoy storm integrity, decoy init, decoy run.


### `decoy storm scan`

Scan a dataset and produce a STORM profile.

Use this when you&#x27;ve been handed a dataset and want to know what&#x27;s in it
-- which fields are PII, which look like quasi-identifiers, what
re-identification risk the dataset carries -- before writing a masking
pipeline. Pass the saved scan JSON to `decoy storm fields` or
`decoy storm show`.

**Usage**:

```console
$ decoy storm scan [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: Path to a CSV file to scan.  [required]

**Options**:

* `--rows INTEGER`: Sample row cap. Default: scan everything.
* `--strategy [full|head|random]`: Sampling strategy when --rows is set.  [default: head]
* `--out PATH`: Where to save the scan JSON. Use - for stdout. Default: scan_&lt;timestamp&gt;.json next to the source.
* `--json`: Emit the full StormProfile JSON to stdout. No card.
* `-q, --quiet`: Suppress stdout. Errors still go to stderr.
* `-v, --verbose`: Enable debug-level CLI logs on stderr.
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
