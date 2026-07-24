"""`decoy explain <topic>` -- on-demand explanations for core concepts.

The CLI ships every topic the user might Google before reaching for
`--help`: modes, transforms, disguises, output flags, pipeline schema,
YAML authoring, STORM, master-key flow, and safety boundaries.
Each topic renders as a styled Panel with a one-line summary, a body,
and a `See also:` line. Tab completion suggests topic names; unknown
topics produce a `did you mean?` hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches

import typer
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, info


@dataclass(frozen=True)
class _Topic:
    name: str
    summary: str
    body: str
    see_also: tuple[str, ...] = ()


_TOPICS: dict[str, _Topic] = {
    "modes": _Topic(
        name="modes",
        summary="What `decoy run --mode` does and which mode to pick.",
        body=(
            "decoy run dispatches one of two modes:\n\n"
            "  mask       Replace columns of an input CSV with masked values.\n"
            "             The default. Pick when you have real data and want to share a sanitized copy.\n"
            "  generate   Build a synthetic dataset from scratch.\n"
            "             Pick when you don't have real data and need realistic-looking rows for testing.\n\n"
            "Mode is inferred per-table from the YAML: a table with `columns:` is a\n"
            "mask table, one with `generate_columns:` is a generate table (FC-1,\n"
            "2026-06-02; the old top-level `mode:` key was removed). The --mode flag is\n"
            "now only a label for progress/JSON output; it does not override what the\n"
            "tables declare.\n\n"
            "V1 had two additional modes (graph + convert) that were removed under storm-reframe-C\n"
            "and S22-CL-V1GRAPHRUNNER (2026-05-30). YAML with `mode: graph` or `mode: convert`\n"
            "is rejected by the V2 PipelineConfig validator with a typed error."
        ),
        see_also=("decoy run --help", "decoy explain pipeline"),
    ),
    "transforms": _Topic(
        name="transforms",
        summary="The most common masking transforms (full set in the strategies reference).",
        body=(
            "Each masking_rule in the YAML names a `type:` from this set:\n\n"
            "  faker        Replace with a realistic fake value of a chosen `faker_type`\n"
            "               (name, email, phone_number, ssn, address, ...). The most common pick.\n"
            "  hash         Replace with a deterministic hash. Same input -> same output.\n"
            "               Use when downstream needs to join on the value but not see it.\n"
            "  redact       Replace with literal text (e.g. 'XXX-XX-XXXX'). Use for fields you\n"
            "               must blank out entirely, or when format is more important than realism.\n"
            "  categorical  Select from an explicit list of categories, optionally weighted.\n"
            "               In mask mode, the same input and policy choose the same category.\n"
            "  shuffle      Randomly reorder a column's values across rows. Preserves the\n"
            "               column's distribution while breaking the link to a specific row.\n"
            "  passthrough  Leave the column unchanged. Useful as documentation of intent.\n"
            "  date_shift   Add or subtract a random number of days. Preserves date proximity\n"
            "               for analytics while breaking the exact value.\n"
            "  formula      Compute the value from a Python-like expression and other columns.\n"
            "               Power-user knob; can reference {col1}, {col2}, randint(), etc.\n\n"
            "Five more advanced strategies exist: bucketize, fpe, text_redact, truncate, nested.\n"
            "The engine ships 13 mask strategies in total; see the strategies reference.\n\n"
            "Tab completion: `decoy run --help` shows --mode; the engine's transform factory key\n"
            "set is what completes when a future --mask flag is added."
        ),
        see_also=("decoy explain disguises", "decoy explain pipeline"),
    ),
    "disguises": _Topic(
        name="disguises",
        summary="Bundles of transforms that map to a regulation or use case.",
        body=(
            "A Disguise is a named set of (column-pattern -> transform) defaults. Two ship today:\n\n"
            "  default   The fallback. Generic name/email/SSN handling.\n"
            "  hipaa     The 18 PHI identifiers from 45 CFR 164.514(b)(2) -- Safe Harbor.\n\n"
            "Pick a Disguise by hand via `decoy templates show hipaa` (gets the pipeline shape\n"
            "you'd start from) or by browsing the engine source under decoy_engine.disguises.\n\n"
            "The V1 FORECAST recommender (which scored Disguises against a STORM scan and drafted\n"
            "a pipeline) was retired under storm-reframe-C (2026-05-30); pick the Disguise by\n"
            "hand from the templates set for now."
        ),
        see_also=("decoy templates show hipaa", "decoy explain transforms"),
    ),
    "output": _Topic(
        name="output",
        summary="--json / --quiet / --verbose and the stdout/stderr contract.",
        body=(
            "Every command takes the same three flags. They never combine:\n\n"
            "  --json      Structured JSON object on stdout, progress + errors on stderr.\n"
            "              Use in scripts and pipes.\n"
            "  --quiet/-q  Nothing on stdout. Errors still go to stderr; exit code carries\n"
            "              success or failure. Use in cron / CI.\n"
            "  --verbose/-v  Adds debug logs and stack traces to stderr. Use when something\n"
            "              broke and you want details.\n\n"
            "Stdout is the data plane. Errors always go to stderr -- `decoy run x.yaml > out.csv`\n"
            "produces a clean CSV file even when warnings were logged.\n\n"
            "Environment overrides:\n"
            "  NO_COLOR=1     Strip ANSI from every output mode.\n"
            "  DECOY_DEBUG=1  Show stack traces without --verbose (useful in container entrypoints)."
        ),
        see_also=("decoy --help",),
    ),
    "pipeline": _Topic(
        name="pipeline",
        summary="The shape of a decoy pipeline YAML.",
        body=(
            "V2 PipelineConfig shape (current; `decoy validate` accepts these):\n\n"
            "  version            1 (integer, not '1.0').\n"
            "  global_settings    seed, default_locale.\n"
            "  sources            dict[name -> {type, format, path}].\n"
            "  tables             list of {name, columns: [{name, strategy, ...}]}\n"
            "                     for mask, or {name, row_count, generate_columns: [...]}\n"
            "                     for generate.\n"
            "  targets            dict[name -> {type, format, path}].\n"
            "  relationships      optional FK relationships across tables.\n"
            "  namespaces         optional namespace -> declared_by mapping.\n\n"
            "  key_label is NOT a YAML field -- PipelineConfig forbids unknown\n"
            "  top-level keys, so a top-level `key_label:` fails validation.\n"
            "  Pass it as `--key-label` on `decoy run` instead. See `decoy\n"
            "  explain keys`.\n\n"
            "Mode is inferred per-table from `columns` (mask) vs `generate_columns`\n"
            "(generate); a single pipeline can mix both kinds (FC-1, 2026-06-02).\n\n"
            "Pick a template to start from: `decoy templates show minimal`.\n\n"
            "Legacy V1 shape (REJECTED by `decoy validate` since storm-reframe-C,\n"
            "2026-05-30): `version: '1.0'`, `input:`, `output:`, `masking_rules:`.\n"
            "Old YAML on disk must be re-authored to the V2 shape above; the\n"
            "graph builder in decoy-platform's web UI emits V2 directly.\n\n"
            "Validate any pipeline before running it: `decoy validate config pipeline.yaml`."
        ),
        see_also=("decoy validate config --help", "decoy templates list"),
    ),
    "yaml": _Topic(
        name="yaml",
        summary="How to author a Decoy YAML file without starting from scratch.",
        body=(
            "Start from a template, edit paths, validate, then run on a small fixture:\n\n"
            "  decoy templates list\n"
            "  decoy templates show minimal > pipeline.yaml\n"
            "  decoy validate config pipeline.yaml\n"
            "  decoy run pipeline.yaml\n\n"
            "Pick one top-level mode:\n"
            "  mask      sources + tables + targets (V2 PipelineConfig shape).\n"
            "  generate  tables with generate_columns + targets.\n\n"
            "Common V2 column shape (mask):\n\n"
            "  - name: email\n"
            "    strategy: faker\n"
            "    provider: person_email\n\n"
            "Use `--key-label` with --master-key/DECOY_MASTER_KEY when you need portable\n"
            "deterministic synthetic generation across machines (generate_columns:). This is\n"
            "a CLI flag, not a YAML field -- PipelineConfig forbids unknown top-level keys.\n"
            "For portable keyed MASKING, set `global_settings.mask_secret_ref` instead --\n"
            "see `decoy explain keys`.\n"
            "Treat STORM scan JSON, reference files, and real input/output files as\n"
            "sensitive artifacts.\n\n"
            "Full guide in the docs hub:\n"
            "  decoy-platform/docs/guides/cli-yaml-workflows.md"
        ),
        see_also=("decoy explain pipeline", "decoy templates list", "decoy validate config --help"),
    ),
    "storm": _Topic(
        name="storm",
        summary="Dataset analysis -- scan a CSV for PII before writing a mask.",
        body=(
            "STORM (Statistical Top-down Risk Mapping) scans a dataset and produces a profile:\n"
            "  - Per-column type, cardinality, null fraction, top values.\n"
            "  - PII detector hits (regex + named-entity recognition).\n"
            "  - Sentinel-value flags (the 999s, 99/99/9999s, NA-like literals that pollute stats).\n"
            "  - Quasi-identifier groups (sets of columns that uniquely identify a row).\n"
            "  - A re-identification risk score, 0-100.\n\n"
            "Run it before writing a masking pipeline. The output JSON gives you the column-by-column\n"
            "PII signal the operator uses to pick a Disguise template + tune the mask."
        ),
        see_also=("decoy storm analyze --help", "decoy templates list"),
    ),
    "keys": _Topic(
        name="keys",
        summary="Two separate key mechanisms: --master-key for generation, --mask-secret/mask_secret_ref for masking.",
        body=(
            "Decoy has two independent keyed-determinism mechanisms. They do not share a\n"
            "secret and setting one has no effect on the other.\n\n"
            "1) SYNTHETIC GENERATION (generate_columns:) -- `--master-key` / `--key-label`\n"
            "   By default, generation is per-input deterministic: same seed -> same\n"
            "   generated output within one run, but not portable across machines.\n"
            "   With --master-key (32-byte hex) plus a --key-label, the engine derives\n"
            "   generation keys from the master/label pair, so:\n"
            "     - Same key + same label -> bitwise-identical generated output, anywhere.\n"
            "     - Same key + different label -> different output (label is the namespace).\n"
            "   Generate a key:\n"
            "     python -c 'import secrets; print(secrets.token_hex(32))'\n"
            "   Pass it via --master-key, the DECOY_MASTER_KEY env var, or both. The label\n"
            "   is a CLI-only flag: `--key-label`. It is NOT a pipeline YAML field --\n"
            "   PipelineConfig forbids unknown top-level keys, so a top-level `key_label:`\n"
            "   in the YAML fails validation.\n\n"
            "2) MASKING (mask: strategies) -- `--mask-secret` or `global_settings.mask_secret_ref`\n"
            "   --master-key does NOT affect masking. Keyed masking strategies (fpe, hash,\n"
            "   date_shift, and others) are keyed off a secret referenced two ways -- pick\n"
            "   ONE (setting both is a usage error):\n"
            "     decoy run pipeline.yaml --mask-secret env:DECOY_MASK_SECRET\n"
            "   or in the YAML:\n"
            "     global_settings:\n"
            '       mask_secret_ref: "env:DECOY_MASK_SECRET"   # or "file:/path/to/secret"\n'
            "   --mask-secret is an explicit flag only -- unlike --master-key it has NO env\n"
            "   var, because the ref it carries already indirects through the environment\n"
            "   (a second env layer would swallow the raw exported secret as the flag value).\n"
            "   It is a completely separate secret from --master-key; the two are independent\n"
            "   and setting one has no effect on the other.\n"
            "   The ref points at a >=32-byte secret (hex or base64); the ENGINE resolves it\n"
            "   from the referenced env var or file at run time and never logs or serializes\n"
            "   the raw secret.\n"
            "   Pre-GA: without a mask secret, keyed masking strategies still run, keyed off\n"
            "   the 8-byte job_seed. The job_seed IS deterministic across machines, so the\n"
            "   output is reproducible -- but the job_seed is PUBLIC (not a confidentiality\n"
            "   secret), so unkeyed masking is NOT re-identification-safe: anyone with the\n"
            "   config can reproduce the mapping. AT GA: a keyed masking strategy with no\n"
            "   resolved mask secret is REJECTED outright (fail-closed) rather than silently\n"
            "   falling back to job_seed -- see `decoy_engine.release.is_pre_ga()`. Configure\n"
            "   a real mask secret before then."
        ),
        see_also=("decoy run --help",),
    ),
    "vault": _Topic(
        name="vault",
        summary="Reversible masking -- write an encrypted token vault with `decoy run --vault`.",
        body=(
            "Most masking is one-way. To recover original values later, mark the\n"
            "columns you need reversible with `vault: true` in the YAML and pass a\n"
            "vault path on the run:\n\n"
            "  decoy run pipeline.yaml --vault vault.bin\n\n"
            "The vault is an encrypted source-to-masked map for the vaulted columns.\n"
            "Recover the originals with:\n\n"
            "  decoy unmask masked.csv --vault vault.bin --table customers -o recovered.csv\n\n"
            "The vault key is derived from the run's seed, so unmask needs the SAME\n"
            "config (seed + namespace) that produced it. Store the vault separately\n"
            "from the masked output and treat it as sensitive -- together they\n"
            "re-identify every vaulted value. Needs the engine's vault extra\n"
            "(cryptography). FPE columns are reversible on their own and do not use\n"
            "the vault."
        ),
        see_also=("decoy run --help", "decoy unmask --help", "decoy explain keys"),
    ),
    "chunked": _Topic(
        name="chunked",
        summary="Stream large inputs through `decoy run --chunked` without loading them whole.",
        body=(
            "By default a run loads the whole source into memory. For inputs too\n"
            "large to fit, stream them chunk-by-chunk:\n\n"
            "  decoy run pipeline.yaml --chunked --chunk-size 100000\n\n"
            "Chunked output is byte-identical to a plain run for CSV targets. Only\n"
            "value-keyed strategies qualify -- ones whose output depends only on the\n"
            "input value, not on the rest of the column: hash, fpe, redact, truncate,\n"
            "text_redact, date_shift, bucketize (plus faker/categorical when the\n"
            "config declares an explicit pool). Anything that needs the whole column\n"
            "(e.g. shuffle) is rejected with a usage error.\n\n"
            "Sources and targets may be CSV or Parquet independently; the file suffix\n"
            "picks the reader and writer."
        ),
        see_also=("decoy run --help", "decoy explain substrate"),
    ),
    "substrate": _Topic(
        name="substrate",
        summary="Pick the pandas or polars execution engine for `--chunked` runs.",
        body=(
            "Decoy supports two dataframe substrates:\n\n"
            "  pandas   The only substrate for plain (non-chunked) runs. Plain runs\n"
            "           go through the engine's unified run_pipeline (V2 path), which\n"
            "           uses the internal PandasExecutionAdapter. --substrate and the\n"
            "           DECOY_SUBSTRATE env var are only consulted for --chunked runs;\n"
            "           setting either on a plain run emits a warning to stderr.\n\n"
            "  polars   Available for --chunked runs via --substrate polars or by\n"
            "           setting DECOY_SUBSTRATE=polars in the environment.\n"
            "           pandas is the --chunked default (the byte-stable contract that\n"
            "           mode shipped with).\n\n"
            "To select polars for a chunked run:\n\n"
            "  decoy run pipeline.yaml --chunked --substrate polars\n\n"
            "Outputs are value-equal across substrates. CSV bytes are identical; only\n"
            "Arrow type-width metadata can differ, which CSV does not carry.\n"
            "(See: decoy explain chunked for when to use --chunked.)"
        ),
        see_also=("decoy run --help", "decoy explain chunked"),
    ),
    "differential-privacy": _Topic(
        name="differential-privacy",
        summary="Fit a dps-marginal/v3 release with `decoy fit --epsilon`.",
        body=(
            "`decoy fit` captures a distribution snapshot that `type: statistical`\n"
            "generate columns sample from. --epsilon selects a second, disjoint mode\n"
            "that fits a dps-marginal/v3 release through the engine's OpenDP-backed\n"
            "fit_dp_snapshot instead of the exact snapshot:\n\n"
            "  decoy fit customers.csv --epsilon 1.0 --delta 1e-6 \\\n"
            "      --dp-number amount:0:500 --dp-text state --dp-flag is_active\n\n"
            "Every released column must be declared with a carrier: --dp-number\n"
            "COL:LO:HI for a numeric column plus its domain (declared, never read\n"
            "from the data), --dp-text COL for a categorical column, --dp-flag COL\n"
            "for a boolean column. A source column nobody declared is a usage error\n"
            "unless you pass --dp-allow-omit (then it is dropped from the release\n"
            "and the omission is printed). --delta is required alongside --epsilon\n"
            "(no default: it sets a real privacy parameter). --epsilon is\n"
            "incompatible with --joint and --parse-dates.\n\n"
            "The fit also requires a certified DP proof stack (a pinned lock the\n"
            "engine has been validated against). On an uncertified host it refuses\n"
            "with dp_stack_uncertified rather than release under an unverified\n"
            "guarantee."
        ),
        see_also=("decoy fit --help", "decoy run --help"),
    ),
    "security": _Topic(
        name="security",
        summary="What the CLI can expose and how to keep local artifacts safe.",
        body=(
            "The CLI reads and writes local files. It does not provide platform RBAC,\n"
            "audit rows, server logs, Reporting, runtime secrets, schedules, reviews,\n"
            "or evidence packages.\n\n"
            "Keep these artifacts private:\n"
            "  - Raw input files and masked/generated outputs.\n"
            "  - STORM scan JSON, because it can contain sensitive aggregates and top values.\n"
            "  - Master keys and key labels (generation) and mask_secret_ref secrets\n"
            "    (masking) -- see `decoy explain keys`.\n"
            "  - Reference files and categorical policy values.\n\n"
            "Prefer DECOY_MASTER_KEY over --master-key so the raw key is less likely to\n"
            "land in shell history. Do not commit scan JSON, real data, or keys.\n\n"
            "CLI JSON output is command status, not platform evidence, unless a future\n"
            "`--evidence-out` feature is explicitly implemented and tested."
        ),
        see_also=("decoy explain keys", "decoy explain yaml"),
    ),
    "exit-codes": _Topic(
        name="exit-codes",
        summary="The process exit codes every `decoy` command returns.",
        body=(
            "Every `decoy` subcommand returns one of five exit codes. Scripts,\n"
            "Make recipes, and CI pipelines can switch on the integer value.\n\n"
            "  0   Success. The command did what it said. POSIX convention.\n"
            "  1   Usage error. The caller's request was wrong: config did not\n"
            "      validate, a path did not exist, an incompatible flag\n"
            "      combination was passed. The fix is in the user's input.\n"
            "  2   Deprecated shim. The legacy `forge` console entry point was\n"
            "      invoked; the CLI printed a migration hint and exited. The\n"
            "      fix is to run `decoy ...` instead of `forge ...`.\n"
            "  3   Runtime error. The CLI itself failed mid-run: the engine\n"
            "      raised an unexpected error, an output write failed, a\n"
            "      transient I/O problem happened. The fix is in the CLI or\n"
            "      engine, not the user's request.\n"
            "  4   Findings. The CLI ran cleanly but found data issues (e.g.\n"
            "      `decoy storm integrity` flagged residual PII or FK\n"
            "      preservation failures). The fix is in the data being\n"
            "      checked, not in the CLI invocation. Pattern source:\n"
            "      semgrep's exit-code split.\n\n"
            "Integer values are stable across releases. The named constants\n"
            "(EXIT_OK / EXIT_USAGE / EXIT_DEPRECATED_SHIM / EXIT_RUNTIME /\n"
            "EXIT_FINDINGS) live in `decoy.cli.exit_codes` for callers that\n"
            "import them in Python."
        ),
        see_also=("decoy --help", "decoy run --help"),
    ),
    "completion": _Topic(
        name="completion",
        summary="Tab completion -- install, troubleshoot.",
        body=(
            "Install once per shell:\n\n"
            "  decoy --install-completion\n\n"
            "Auto-detects the user's shell (bash, zsh, fish, pwsh). Restart the shell or source\n"
            "the rc file after install. Test with:\n\n"
            "  decoy run --mode <Tab>\n"
            "  decoy explain <Tab>\n"
            "  decoy templates show <Tab>\n\n"
            "If completion stops working after a Decoy upgrade, re-run --install-completion to\n"
            "refresh the script. Custom completers cache lookups in-process; they're cheap."
        ),
        see_also=("decoy --help",),
    ),
}


def topic_names() -> list[str]:
    """Returned to Typer's `autocompletion=` for the topic argument."""
    return list(_TOPICS.keys())


_EXPLAIN_EPILOG = """\
Examples:

  decoy explain modes
    Plain-English description of mask vs generate.

  decoy explain transforms
    The built-in masking transforms with one-line descriptions.

  decoy explain
    No topic -- list every topic with its summary.

See also: decoy --help, decoy templates list.
"""


def _render_topic(state, topic: _Topic) -> None:
    """Print one topic as a Rich Panel."""
    body_text = Text(topic.body, style="info")
    children = [body_text]
    if topic.see_also:
        children.append(Text(""))
        children.append(
            Text.assemble(
                ("See also:", "hint"),
                " ",
                (", ".join(topic.see_also), "code"),
            )
        )
    title = Text.assemble(("explain: ", "hint"), (topic.name, "accent"))
    state.console.print(
        Panel(
            Group(*children),
            title=title,
            title_align="left",
            border_style="accent",
            subtitle=Text(topic.summary, style="info"),
            subtitle_align="left",
        )
    )


def _render_index(state) -> None:
    """No topic given -- print the index table."""
    state.console.print(accent("Topics:"))
    table = make_table("Topic", "Summary", title=None)
    for topic in _TOPICS.values():
        table.add_row(topic.name, topic.summary)
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("Tip:"),
        "run",
        code("decoy explain <topic>"),
        info("for the full text."),
    )


def explain(
    topic: str = typer.Argument(
        None,
        help="Which topic to explain. Omit to list every topic.",
        autocompletion=topic_names,
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON object instead of a rendered Panel.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Explain a Decoy concept in plain English.

    Built-in topics: modes, transforms, disguises, output, pipeline, yaml,
    storm, keys, vault, chunked, substrate, differential-privacy, security,
    completion. Run with no topic to see the full list.
    """
    state = setup_output(json_, quiet, verbose)

    if topic is None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "explain",
                    "status": "ok",
                    "topics": [{"name": t.name, "summary": t.summary} for t in _TOPICS.values()],
                },
            )
            return
        if state.mode is OutputMode.quiet:
            return
        _render_index(state)
        return

    found = _TOPICS.get(topic)
    if found is None:
        # Levenshtein-style suggestion for unknown topics.
        guess = get_close_matches(topic, _TOPICS.keys(), n=1, cutoff=0.5)
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "explain",
                    "status": "error",
                    "topic": topic,
                    "error": f"unknown topic {topic!r}",
                    "did_you_mean": guess[0] if guess else None,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"unknown topic {topic!r}.")
            if guess:
                state.err_console.print(" ", hint("hint:"), "did you mean", code(guess[0]) + "?")
            else:
                state.err_console.print(
                    " ",
                    hint("hint:"),
                    "list every topic with",
                    code("decoy explain") + ".",
                )
        raise typer.Exit(code=EXIT_USAGE)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "explain",
                "status": "ok",
                "topic": found.name,
                "summary": found.summary,
                "body": found.body,
                "see_also": list(found.see_also),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    _render_topic(state, found)


EXPLAIN_EPILOG = _EXPLAIN_EPILOG
