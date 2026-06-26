"""`decoy schema` -- export the PipelineConfig JSON Schema.

Prints the full JSON Schema for the Decoy pipeline configuration to stdout.
Useful for editor integration, validation tooling, or generating a local
schema file for IDE auto-complete.
"""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import Optional

import typer

from decoy.ui.output import OutputMode, emit_json, setup_output


_SCHEMA_EPILOG = """\
Examples:

  decoy schema
    Print the PipelineConfig JSON Schema to stdout.

  decoy schema -o decoy.schema.json
    Write the schema to a file (for editor / IDE integration).

  decoy schema --json
    Wrap the schema in the standard {command, status, schema} envelope.

See also: decoy validate, decoy templates list.
"""

SCHEMA_EPILOG = _SCHEMA_EPILOG


def schema(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the schema to this file instead of stdout.",
        show_default=False,
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Wrap the schema in a {command, status, schema} JSON envelope.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Print the PipelineConfig JSON Schema to stdout."""
    state = setup_output(json_, quiet, verbose)

    from decoy_engine import PipelineConfig  # lazy import; engine may be heavy

    schema_dict = PipelineConfig.model_json_schema()

    if output is not None:
        # Compose --output and --json: when --json is set, write the envelope;
        # otherwise write the raw schema. Both go to the file, not stdout.
        if state.mode is OutputMode.json:
            content = _json.dumps(
                {"command": "schema", "status": "ok", "schema": schema_dict}
            )
        else:
            content = _json.dumps(schema_dict, indent=2)
        output.write_text(content, encoding="utf-8")
        return

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "schema",
                "status": "ok",
                "schema": schema_dict,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    # Default mode: raw indented JSON so it pipes cleanly to a file.
    sys.stdout.write(_json.dumps(schema_dict, indent=2))
    sys.stdout.write("\n")
