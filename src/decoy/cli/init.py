"""`decoy init` -- interactive scaffolder for a starter pipeline YAML.

The only place wizards belong (CLI_UX_GUIDE.md section 13). Walks the user
through a couple of prompts and writes a starter `pipeline.yaml` they can
iterate on. The body of every preset comes from `decoy.templates`, so
`decoy init --preset hipaa` and `decoy show template hipaa` produce the
same YAML up to input/output path edits.

OSS.4c (2026-06-02) added a column-aware path: `decoy init <file>` runs
STORM against the input, picks a starter strategy per column from the
inference table in `_init_inference.py`, and emits the YAML with
`# REVIEW:` comments above every auto-inferred entry. Source patterns:
dbt init (template scaffold + ask user to review) and cookiecutter
(static-template-driven). The user MUST read the REVIEW comments and
edit before running -- the scaffolder makes a best-guess call, not a
binding choice.
"""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any, NoReturn

import typer
import yaml

from decoy import _mask_secret_guidance
from decoy.cli._init_inference import Inference, _infer_strategy_for_column
from decoy.cli._sources import CSV_DIALECT_KEYS, csv_file_source
from decoy.cli.completers import init_presets
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.io import LayoutError, explicit_project, shown_path
from decoy.cli.project._scaffold import (
    Argument,
    Placement,
    ScaffoldRefused,
    member_placement,
    place,
    prepare_folder,
    source_text,
    split_argument,
    target_text,
)
from decoy.templates import get_template
from decoy.templates import template_names as _template_names
from decoy.ui.output import OutputMode, OutputState, emit_error, emit_json, setup_output
from decoy.ui.theme import accent, code, hint, success

_INIT_EPILOG = """\
Examples:

  decoy init members-mask --source data/members.csv
    In a project: STORM reads the file, picks a starter strategy per column, and writes
    pipelines/members-mask/pipeline.yaml with `# REVIEW:` comments above every inferred entry.
    The source is written relative to the pipeline when it is inside the project. Read and edit
    before running. Then: decoy run members-mask

  decoy init members.csv
    The same, named after the file: pipelines/members/pipeline.yaml.

  decoy init orders --preset hipaa
    Scaffold pipelines/orders/pipeline.yaml from the HIPAA template.

  decoy init
    In a project: ask for the pipeline name, the preset and the paths.

  decoy init customers.csv -o pipeline.yaml
    Write the YAML to a file of your choice, in or outside a project. Its source path is written
    relative to that file.

  decoy init --preset generate -o -
    Print the generate template on stdout and nothing else there.

  decoy init people.csv --preset generate -o gen/pipeline.yaml
    Fit people.csv, then write gen/people.snapshot.json and a generate config
    that names it. Both files are written together or not at all.

  decoy init orders --preset minimal --yes
    Skip confirmation when overwriting an existing pipeline.

Outside a project, `init` needs -o: run `decoy project new .` first to make the folder a project.
Pick another project with `decoy --project DIR init ...`.

See also: decoy project new, decoy validate config, decoy run, decoy scan, decoy list templates.
"""


# Templates used by the wizard. Only the flat masking templates hold one file
# source and one file target to path-edit; `generate` has no source, so it is
# written unchanged.
_PATHED_PRESETS: tuple[str, ...] = ("minimal", "hipaa", "pci", "gdpr")


def _render(preset: str, input_path: str | None, output_path: str | None) -> str:
    """Build the YAML body for a preset, optionally rewriting its source and target paths.

    For flat masking presets (minimal/hipaa/pci/gdpr), substitute the wizard's
    chosen paths into the bundled template's first `sources:` and `targets:`
    entries. Every other preset is returned as-is.
    """
    template = get_template(preset)
    if template is None:
        raise ValueError(f"unknown preset: {preset!r}")
    body = template.body
    if preset in _PATHED_PRESETS and input_path and output_path:
        body = _replace_yaml_path(body, "sources", input_path)
        body = _replace_yaml_path(body, "targets", output_path)
    return body


# A plain-scalar value and an optional trailing comment; quoted values are replaced whole.
_PLAIN_VALUE_WITH_COMMENT = re.compile(r"(?P<value>[^'\"#][^#]*?)(?P<comment>[ \t]+#.*)?\Z")


def _entry_path_line(lines: list[str], key: str) -> int:
    """Index of the `path:` key directly under the first entry of the top-level `key:` block.

    A deeper `path:` (inside a nested mapping) and the next entry's `path:` are not it.
    """
    head = next((i for i, line in enumerate(lines) if line.rstrip() == f"{key}:"), None)
    entry_indent = child_indent = None
    for i in range(len(lines) if head is None else head + 1, len(lines)):
        text = lines[i].rstrip("\n")
        stripped = text.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(text) - len(stripped)
        if indent == 0 or (entry_indent is not None and indent <= entry_indent):
            break
        if entry_indent is None:
            entry_indent = indent
            continue
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and stripped.startswith("path:"):
            return i
    raise ValueError(f"preset template has no path under {key}:")


def _template_path(body: str, key: str) -> str:
    """The path of the first entry under a template's top-level `key:` block."""
    lines = body.splitlines(keepends=True)
    line = lines[_entry_path_line(lines, key)]
    return str(yaml.safe_load(line.split("path:", 1)[1]))


def _replace_yaml_path(body: str, key: str, new_path: str) -> str:
    """Rewrite the path of the first entry under the top-level `key:` block.

    Avoids a YAML round-tripper for two paths. A trailing comment on a plain value is
    kept. A template whose shape no longer matches raises instead of silently keeping
    its own path.
    """
    lines = body.splitlines(keepends=True)
    i = _entry_path_line(lines, key)
    prefix, rest = lines[i].split("path:", 1)
    ending = "\n" if rest.endswith("\n") else ""
    rest = rest.rstrip("\n").strip()
    match = _PLAIN_VALUE_WITH_COMMENT.match(rest)
    comment = (match.group("comment") or "") if match else ""
    lines[i] = f"{prefix}path: {_yaml_quote(new_path)}{comment}{ending}"
    return "".join(lines)


def _rule_count(body: str) -> int:
    """Cheap count of mask/generate column entries so the JSON envelope
    can report it. CLI.3 (2026-06-02): templates moved from V1 `- column:`
    to V2 `- name:`; the counter follows."""
    return sum(1 for line in body.splitlines() if line.strip().startswith("- name:"))


# --- Column-aware scaffolding (OSS.4c) -------------------------------------
#
# `decoy init <file>` scans the input with STORM and writes a starter
# pipeline.yaml with one column entry per detected field. The YAML is
# hand-emitted (no full YAML round-tripper) so REVIEW comments land in
# the exact positions we need them; the body is smoke-validated through
# `PipelineConfig.model_validate` before it touches disk. Source patterns:
# dbt init (template-driven scaffolding) + cookiecutter (static-template
# rendering). The scaffolder owns the COMMENTS; the engine owns the SCHEMA.


_TABLE_NAME = "data"
"""Name used for the single source/target/table the scaffolder emits.

The column-aware path only handles one input file at a time. Multi-table
pipelines are out of scope; the user authors those by hand or chains
multiple init runs.
"""


def _scaffold_source(input_file: Path) -> dict[str, Any]:
    """The source descriptor the scaffold declares for `input_file`, from its suffix.

    The one suffix rule for both the inference read and the YAML: `.parquet` and `.pq` are
    parquet, `.tsv` is csv with a tab delimiter, anything else is csv with the default dialect.
    Raises ValueError for a suffix the scaffolder does not support.
    """
    suffix = input_file.suffix.lower()
    path = str(input_file)
    if suffix in (".parquet", ".pq"):
        return {"type": "file", "format": "parquet", "path": path}
    if suffix == ".tsv":
        from decoy.cli._sources import csv_file_source

        return csv_file_source(path, delimiter="\t")
    if suffix == ".csv":
        from decoy.cli._sources import csv_file_source

        return csv_file_source(path)
    raise ValueError(f"unsupported file extension {suffix!r}; expected .csv, .tsv, or .parquet")


def _load_dataframe(input_file: Path):
    """Read the user's input file into a pandas DataFrame for STORM.

    Supports the two formats the v1 launch covers: CSV (and TSV) and Parquet. The suffix
    is the dispatch hint, through `_scaffold_source`; csv reads through the CLI's one CSV
    read point so the inference sees the dialect the YAML will declare.
    """
    descriptor = _scaffold_source(input_file)
    if descriptor["format"] == "csv":
        from decoy.cli._sources import read_csv_frame

        return read_csv_frame(_TABLE_NAME, descriptor, Path.cwd(), dtype=None, nrows=10_000)
    from decoy.cli._sources import read_file

    return read_file(input_file, "parquet", None, table=_TABLE_NAME)


def _yaml_scalar(value: object) -> str:
    """A dialect value as a YAML scalar: bools as true/false, text as a JSON-quoted string."""
    return str(value).lower() if isinstance(value, bool) else _json.dumps(value)


def _yaml_quote(value: str) -> str:
    """Quote a string for the hand-emitted YAML.

    Single-quoted style matches the bundled templates. Single quotes
    inside the value are escaped by doubling, per the YAML 1.1 spec
    section 5.3.2 (single-quoted scalars).
    """
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _wrap_review_comment(review: str, indent: str) -> str:
    """Wrap a REVIEW comment to ~80 columns and prefix `# REVIEW: ` to the
    first line, plain `# ` to continuations.

    Indent is the leading whitespace of the surrounding YAML node so
    the comment lines up with the entry it annotates.
    """
    import textwrap

    width = max(40, 80 - len(indent) - len("# REVIEW: "))
    lines = textwrap.wrap(review, width=width) or [""]
    out = [f"{indent}# REVIEW: {lines[0]}"]
    for cont in lines[1:]:
        out.append(f"{indent}#   {cont}")
    return "\n".join(out)


# Strategies that raise `<strategy>_requires_namespace` at RUNTIME
# (execution/_strategies/*.py) when `ColumnConfig.namespace` is None.
# `ColumnConfig.namespace` defaults to None and there is no compile-time
# check, so a scaffold omitting `namespace:` for one of these passes
# `decoy validate config` / `PipelineConfig.model_validate` cleanly and
# then fails `decoy run` with exit 3. hash/fpe/date_shift are the
# strategies this scaffolder currently emits; shuffle/categorical/
# bucket_perturb/code_set are included for completeness/future-proofing
# even though today's `_INFERENCE_TABLE` never picks them.
_NAMESPACE_REQUIRED_STRATEGIES: frozenset[str] = frozenset(
    {"hash", "fpe", "date_shift", "shuffle", "categorical", "bucket_perturb", "code_set"}
)


def _emit_column_yaml(name: str, inference: Inference, indent: str = "      ") -> str:
    """Emit one column block: REVIEW comment + `- name: ...` body.

    The shape matches engine `ColumnConfig` (decoy_engine.config._tables):
    columns under tables[].columns carry name + strategy + (provider for
    faker) + namespace (required for hash/fpe/date_shift/shuffle/
    categorical/bucket_perturb/code_set -- see
    `_NAMESPACE_REQUIRED_STRATEGIES`) + (provider_config for date_shift /
    truncate / fpe -- ColumnConfig has no `params` field; extra="forbid"
    rejects one). date_shift reads provider_config['min_days'] /
    ['max_days'] (_strategies/_date_shift.py); truncate reads
    provider_config['length'] (_strategies/_truncate.py -- 'keep' there is
    a 'head'/'tail' direction flag, not a character count); fpe reads
    provider_config['charset'] / ['validate_luhn']
    (_strategies/_fpe.py) -- the scaffold emits charset: digits +
    validate_luhn: true so masked PANs stay Luhn-valid, matching the
    bundled PCI template (templates/pci.yaml).

    Namespace value: the column name (`namespace: <name>`), verified to
    validate and run. REVIEW: columns that SHARE a namespace mask
    consistently (same source value -> same masked value across those
    columns); the per-column default here gives every column its own
    namespace, which is safe but does not give cross-column coherence
    (e.g. two columns that both hold the same customer id). Edit the
    namespace value by hand if you need that.
    """
    lines = [_wrap_review_comment(inference.review, indent)]
    lines.append(f"{indent}- name: {name}")
    body_indent = indent + "  "
    lines.append(f"{body_indent}strategy: {inference.strategy}")
    if inference.strategy == "faker" and inference.provider:
        lines.append(f"{body_indent}provider: {inference.provider}")
    if inference.strategy in _NAMESPACE_REQUIRED_STRATEGIES:
        lines.append(f"{body_indent}namespace: {name}")
    if inference.strategy == "date_shift":
        lines.append(f"{body_indent}provider_config:")
        lines.append(f"{body_indent}  min_days: -365")
        lines.append(f"{body_indent}  max_days: 365")
    elif inference.strategy == "truncate":
        lines.append(f"{body_indent}provider_config:")
        lines.append(f"{body_indent}  length: 3")
    elif inference.strategy == "fpe":
        lines.append(f"{body_indent}provider_config:")
        lines.append(f"{body_indent}  charset: digits")
        lines.append(f"{body_indent}  validate_luhn: true")
    if inference.deterministic:
        lines.append(f"{body_indent}deterministic: true")
    return "\n".join(lines)


def _build_scaffold_yaml(
    *,
    input_path: Path,
    output_path: Path,
    column_names: list[str],
    inferences: dict[str, Inference],
    file_format: str,
    delimiter: str | None = None,
    input_text: str | None = None,
    output_text: str | None = None,
) -> str:
    """Compose the full scaffold YAML body from the per-column inferences.

    The header names the input file so the user has the provenance pinned
    at the top of the file. Path values are quoted so
    Windows paths with backslashes round-trip cleanly through YAML 1.1.
    """
    # `input_text` and `output_text` are the paths as written into the YAML (relative to its
    # folder); the Path arguments name the file for the header and the dialect.
    input_quoted = _yaml_quote(input_text if input_text is not None else str(input_path))
    output_quoted = _yaml_quote(output_text if output_text is not None else str(output_path))

    header = (
        "# Decoy pipeline scaffold (column-aware).\n"
        f"# Generated by `decoy init {input_path.name}`.\n"
        "# Read the # REVIEW: comments above each column before running.\n"
        "# When you are satisfied with the choices, delete the REVIEW comments\n"
        "# and run `decoy validate config <this-file>` followed by `decoy run`.\n"
        "#\n"
        "# Run `decoy explain pipeline` for the V2 pipeline shape.\n"
    )

    # The csv dialect lines come from the one csv descriptor builder, not a second copy of its
    # defaults; the descriptor's own type/format/path lines are written below.
    dialect = (
        {
            k: v
            for k, v in csv_file_source(
                input_path, **({"delimiter": delimiter} if delimiter else {})
            ).items()
            if k in CSV_DIALECT_KEYS
        }
        if file_format == "csv"
        else {}
    )
    dialect_lines = "".join(f"    {k}: {_yaml_scalar(v)}\n" for k, v in dialect.items())
    sources_block = (
        "sources:\n"
        f"  {_TABLE_NAME}:\n"
        "    type: file\n"
        f"    format: {file_format}\n"
        f"    path: {input_quoted}\n"
        f"{dialect_lines}"
    )
    targets_block = (
        "targets:\n"
        f"  {_TABLE_NAME}:\n"
        "    type: file\n"
        f"    format: {file_format}\n"
        f"    path: {output_quoted}\n"
    )

    column_blocks = "\n".join(
        _emit_column_yaml(name, inferences[name]) for name in column_names
    )

    tables_block = (
        "tables:\n"
        f"  - name: {_TABLE_NAME}\n"
        "    columns:\n"
        f"{column_blocks}\n"
    )

    body = (
        "version: 2\n\n"
        "global_settings:\n"
        "  seed: 42\n\n"
        f"{sources_block}\n"
        f"{tables_block}\n"
        f"{targets_block}"
    )
    import yaml as _yaml

    if _mask_secret_guidance.config_is_keyed(_yaml.safe_load(body)):
        header += "#\n" + _mask_secret_guidance.YAML_COMMENT
    return f"{header}\n{body}"


def _validate_scaffold(body: str) -> None:
    """Smoke-test the emitted YAML through PipelineConfig before we hand
    the user a file that will fail validation later. Raises if the
    parsed YAML does not satisfy the engine's V2 PipelineConfig schema.

    The check is best-effort: PipelineConfig may live behind a feature
    gate or import path the CLI cannot reach in some embedded contexts;
    in that case the function returns silently and the user's
    `decoy validate config` step picks up any schema issue. This matches the
    pattern used in `decoy.cli.report._integrity`.
    """
    try:
        import yaml
        from decoy_engine.config import parse_pipeline_config
    except Exception:
        return
    parsed = yaml.safe_load(body)
    parse_pipeline_config(parsed)


def _scaffold_from_file(
    *,
    input_file: Path,
    destination: Placement,
    state,
) -> tuple[str, int]:
    """Run STORM against `input_file` and produce the scaffold YAML body.

    Returns a (yaml_body, column_count) tuple so JSON-mode callers can
    report column_count without re-parsing the body. Callers handle
    writing the body (to disk or stdout). Raises typer.Exit(EXIT_USAGE)
    on a bad input file and typer.Exit(EXIT_RUNTIME) on an unexpected
    scanner crash.
    """
    if not input_file.exists():
        emit_error(state, "init", f"{input_file} does not exist.")
        raise typer.Exit(code=EXIT_USAGE)

    # The extension check has fixed, value-free text, so it is shown whole.
    unsupported: str | None = None
    try:
        _scaffold_source(input_file)
    except ValueError as exc:
        unsupported = str(exc)
    if unsupported is not None:
        emit_error(state, "init", unsupported)
        raise typer.Exit(code=EXIT_USAGE)

    # Messages below name the exception type only: a reader's text can quote the file's bytes.
    try:
        df = _load_dataframe(input_file)
    except ValueError as exc:
        emit_error(state, "init", f"could not read {input_file}: {type(exc).__name__}.")
        raise typer.Exit(code=EXIT_USAGE) from exc
    except Exception as exc:
        emit_error(state, "init", f"could not read {input_file}: {type(exc).__name__}.")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    try:
        from decoy_engine import profile_columns

        profile = profile_columns(df, source_label=str(input_file))
    except Exception as exc:
        emit_error(state, "init", f"STORM scan failed: {type(exc).__name__}.")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    column_names = [fs.name for fs in profile.fields]
    inferences: dict[str, Inference] = {
        fs.name: _infer_strategy_for_column(fs) for fs in profile.fields
    }

    source = _scaffold_source(input_file)
    file_format = source["format"]
    output_text = target_text(input_file, file_format)

    body = _build_scaffold_yaml(
        input_path=input_file,
        output_path=Path(output_text),
        input_text=source_text(input_file, destination),
        output_text=output_text,
        column_names=column_names,
        inferences=inferences,
        file_format=file_format,
        delimiter=source.get("delimiter"),
    )

    try:
        _validate_scaffold(body)
    except Exception as exc:
        # Validation failure here is a bug in the scaffolder (not the
        # user's input) since we built the YAML ourselves. Surface
        # loudly via EXIT_RUNTIME so it doesn't slip past CI.
        emit_error(
            state,
            "init",
            "scaffolder emitted YAML that failed PipelineConfig validation: "
            f"{type(exc).__name__}.",
        )
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    return body, len(column_names)


def _init(
    ctx: typer.Context,
    token: str = typer.Argument(
        None,
        metavar="[NAME|FILE]",
        help=(
            "The pipeline's name, or a source file (.csv/.tsv/.parquet) to name it after. "
            "With a file and no --preset, STORM scans it and scaffolds a column-aware pipeline "
            "with `# REVIEW:` comments above every auto-inferred column."
        ),
        show_default=False,
    ),
    source: Path = typer.Option(
        None,
        "--source",
        help="The source file (.csv/.tsv/.parquet) of the pipeline, when NAME is given.",
        show_default=False,
    ),
    out: Path = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Write the pipeline YAML here instead of pipelines/NAME/pipeline.yaml, in or outside "
            "a project. Use `-` to write to stdout."
        ),
        show_default=False,
    ),
    preset: str = typer.Option(
        None,
        "--preset",
        help="Skip the preset prompt and use this template directly.",
        autocompletion=init_presets,
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip overwrite confirmation.",
    ),
    json_: bool = typer.Option(
        False, "--json", help="Skip the wizard; emit a JSON record of what was written."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Scaffold a starter pipeline in the current project.

    Use this inside a project (`decoy project new DIR`) to get a working pipeline you can run
    end to end, then edit the rules to match your data. The wizard is the only interactive
    prompt in the CLI -- every other command is one-shot.
    """
    state = setup_output(json_, quiet, verbose)

    # Placement is settled before anything is read, asked or written.
    refusal: LayoutError | ScaffoldRefused | None = None
    argument: Argument | None = None
    destination: Placement | None = None
    try:
        argument = split_argument(token, source)
        destination = place(argument, out, explicit_project(ctx))
    except (LayoutError, ScaffoldRefused) as exc:
        refusal = exc
    if refusal is not None:
        _refuse(state, refusal)
    assert argument is not None and destination is not None
    input_file = argument.source
    if input_file is not None and preset != "generate":
        _supported_format(state, input_file)

    if destination.is_member and destination.name is None:
        # Inside a project with nothing to name the pipeline after: the wizard asks.
        if state.mode is not OutputMode.default:
            emit_error(state, "init", "Give the pipeline a name: decoy init <name>.")
            raise typer.Exit(code=EXIT_USAGE)
        asked = typer.prompt("Pipeline name").strip()
        try:
            destination = member_placement(destination.root, asked)
        except LayoutError as exc:
            refusal = exc
        if refusal is not None:
            _refuse(state, refusal)
        assert destination is not None
    out = destination.yaml if destination.yaml is not None else Path("-")
    # What the user types next: the pipeline's name in a project, else the file.
    next_ref = destination.name if destination.is_member and destination.name else str(out)
    shown = shown_path(out) if destination.yaml is not None else "-"

    # A CSV with the generate preset fits a snapshot and writes it with the config.
    if input_file is not None and preset == "generate":
        from decoy.cli.gen import scaffold_generate

        scaffold_generate(state, input_file, out, yes=yes)
        return

    # Column-aware scaffolding (OSS.4c): an input file without --preset
    # routes through STORM-driven inference instead of the template path.
    # If both are given, --preset wins (explicit user override).
    if input_file is not None and preset is None:
        out_is_stdout = destination.is_stdout

        if not out_is_stdout and out.exists() and not yes:
            if state.mode is not OutputMode.default:
                _refuse_overwrite(state, out)
            size = out.stat().st_size
            state.console.print(
                f"This will overwrite {shown} ({size} bytes). Continue?",
            )
            if not typer.confirm("Overwrite?", default=False):
                state.console.print(hint("aborted."))
                raise typer.Exit(code=EXIT_USAGE)

        body, column_count = _scaffold_from_file(
            input_file=input_file,
            destination=destination,
            state=state,
        )

        if out_is_stdout:
            import sys
            sys.stdout.write(body)
            return

        _prepare(state, destination)
        out.write_text(body, encoding="utf-8")

        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "init",
                    "status": "ok",
                    "out": str(out),
                    "source": str(input_file),
                    "mode": "scaffold-from-file",
                    "column_count": column_count,
                    **_placed_members(destination),
                },
            )
            return
        if state.mode is OutputMode.quiet:
            return
        state.console.print()
        state.console.print(
            success("OK"),
            "scaffolded",
            code(shown),
            "from",
            code(str(input_file)),
        )
        state.console.print(
            hint("Next:"),
            "read the # REVIEW: comments, edit as needed, then",
            code(f"decoy validate config {next_ref}"),
        )
        _print_keyed_hint(state, body)
        return

    # Validate --preset early so the error path is consistent across modes.
    if preset is not None and preset not in _template_names():
        from difflib import get_close_matches

        guess = get_close_matches(preset, _template_names(), n=1, cutoff=0.5)
        emit_error(
            state,
            "init",
            f"unknown preset {preset!r}.",
            hint=(
                f"did you mean {guess[0]}?"
                if guess
                else "list every preset with `decoy list templates`."
            ),
            context={"preset": preset, "did_you_mean": guess[0] if guess else None},
        )
        raise typer.Exit(code=EXIT_USAGE)

    if destination.is_stdout:
        _template_to_stdout(state, preset)
        return

    if out.exists() and not yes:
        if state.mode is not OutputMode.default:
            _refuse_overwrite(state, out)
        size = out.stat().st_size
        state.console.print(
            f"This will overwrite {shown} ({size} bytes). Continue?",
        )
        if not typer.confirm("Overwrite?", default=False):
            state.console.print(hint("aborted."))
            raise typer.Exit(code=EXIT_USAGE)

    # A source named with a template: its paths go into the pathed presets.
    given_in, given_out = _preset_paths(state, input_file, destination)

    if state.mode is OutputMode.json:
        # Non-interactive: produce a scaffold with the chosen (or default) preset.
        chosen = preset or "minimal"
        rendered = _render(chosen, given_in, given_out)
        _prepare(state, destination)
        out.write_text(rendered, encoding="utf-8")
        emit_json(
            state,
            {
                "command": "init",
                "status": "ok",
                "out": str(out),
                "preset": chosen,
                "rule_count": _rule_count(rendered),
                **_placed_members(destination),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        chosen = preset or "minimal"
        rendered = _render(chosen, given_in, given_out)
        _prepare(state, destination)
        out.write_text(rendered, encoding="utf-8")
        return

    # Interactive Q&A.
    state.console.print(accent("decoy init"), "-- starter pipeline scaffold")
    state.console.print(hint("press Enter to accept the default in [brackets]."))
    state.console.print()

    if preset is None:
        choices = " | ".join(_template_names())
        chosen = typer.prompt(
            f"Preset ({choices})",
            default="minimal",
        ).strip().lower()
        while chosen not in _template_names():
            emit_error(
                state,
                "init",
                f"unknown preset {chosen!r}.",
                hint=f"pick one of: {', '.join(_template_names())}.",
            )
            chosen = typer.prompt("Preset", default="minimal").strip().lower()
    else:
        chosen = preset

    try:
        if chosen in _PATHED_PRESETS:
            # Defaults are the template's own paths, so Enter writes what --quiet writes.
            body = _render(chosen, None, None)
            input_path = typer.prompt(
                "Input CSV path", default=given_in or _template_path(body, "sources")
            )
            output_path = typer.prompt(
                "Output CSV path", default=given_out or _template_path(body, "targets")
            )
            rendered = _render(chosen, input_path, output_path)
        else:
            rendered = _render(chosen, None, None)
    except ValueError as exc:
        emit_error(state, "init", str(exc))
        raise typer.Exit(code=EXIT_RUNTIME) from None

    _prepare(state, destination)
    out.write_text(rendered, encoding="utf-8")

    state.console.print()
    state.console.print(success("OK"), "wrote", code(shown), "(preset:", code(chosen) + ")")
    state.console.print(hint("Next:"), code(f"decoy validate config {next_ref}"))
    _print_keyed_hint(state, rendered)


def _refuse(state: OutputState, failure: LayoutError | ScaffoldRefused) -> NoReturn:
    """Print a placement refusal (a `layout.*` code or fixed text) and exit 1."""
    emit_error(state, "init", failure.message, code=failure.code)
    raise typer.Exit(code=EXIT_USAGE)


def _prepare(state: OutputState, destination: Placement) -> None:
    """Make the folder the YAML is written into, or refuse with fixed text."""
    problem: ScaffoldRefused | None = None
    try:
        prepare_folder(destination)
    except ScaffoldRefused as exc:
        problem = exc
    if problem is not None:
        _refuse(state, problem)


def _placed_members(destination: Placement) -> dict[str, str]:
    """The `--json` members a project pipeline adds: its name and the project root."""
    if destination.is_member and destination.name and destination.root:
        return {"name": destination.name, "project": str(destination.root)}
    return {}


def _supported_format(state: OutputState, source: Path) -> str:
    """The source's file format, or exit 1 with the fixed unsupported-extension text."""
    unsupported: str | None = None
    file_format = ""
    try:
        file_format = _scaffold_source(source)["format"]
    except ValueError as exc:
        unsupported = str(exc)
    if unsupported is not None:
        emit_error(state, "init", unsupported)
        raise typer.Exit(code=EXIT_USAGE)
    return file_format


def _preset_paths(
    state: OutputState, source: Path | None, destination: Placement
) -> tuple[str | None, str | None]:
    """The source and target paths for a template, when a source file was named."""
    if source is None:
        return None, None
    file_format = _supported_format(state, source)
    return source_text(source, destination), target_text(source, file_format)


def _refuse_overwrite(state: OutputState, out: Path) -> NoReturn:
    """`--json` and `--quiet` cannot ask before overwriting: refuse and name the flag."""
    emit_error(state, "init", f"{out} already exists.", hint="rerun with --yes to overwrite.")
    raise typer.Exit(code=EXIT_USAGE)


def _template_to_stdout(state: OutputState, preset: str | None) -> None:
    """`-o -` with a template: the YAML alone on stdout, every other line on stderr.

    No wizard: its prompts would land on stdout beside the YAML. `--json` also wants stdout,
    so the two are refused.
    """
    import sys

    if state.mode is OutputMode.json:
        emit_error(state, "init", "-o - prints the YAML on stdout, which --json also uses.")
        raise typer.Exit(code=EXIT_USAGE)
    chosen = preset or "minimal"
    rendered = _render(chosen, None, None)
    sys.stdout.write(rendered)
    sys.stdout.flush()
    if state.mode is not OutputMode.quiet:
        state.err_console.print(success("OK"), "printed preset", code(chosen))
        _print_keyed_hint(state, rendered, to_stderr=True)


def _print_keyed_hint(state: OutputState, body: str, *, to_stderr: bool = False) -> None:
    import yaml as _yaml

    if _mask_secret_guidance.config_is_keyed(_yaml.safe_load(body)):
        console = state.err_console if to_stderr else state.console
        console.print(hint("Keyed:"), _mask_secret_guidance.INIT_HINT, markup=False)


_init.__doc__ = _init.__doc__

INIT_EPILOG = _INIT_EPILOG


def init_command():  # exported for __main__
    return _init
