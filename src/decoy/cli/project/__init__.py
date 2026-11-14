"""`decoy project`: make, show and list projects (a folder with a `decoy.yaml` marker).

`decoy init` takes its placement and scaffold text from the names exported here, never from a
`_` module. Commands import the project layout services from the public `decoy.cli.io` package, never a
`_` module there. `project_app` is registered in `decoy.__main__`.
"""

from __future__ import annotations

import typer

from decoy.cli.project._columns import (
    emit_column_yaml,
    wrap_review_comment,
    yaml_quote,
    yaml_scalar,
)
from decoy.cli.project._list import LIST_EPILOG, list_command
from decoy.cli.project._new import NEW_EPILOG, create_project, new_command
from decoy.cli.project._run_all import only_pipeline, run_all
from decoy.cli.project._scaffold import (
    SOURCE_SUFFIXES,
    Placement,
    placed_members,
    prepare,
    resolve_destination,
    source_text,
    target_text,
)
from decoy.cli.project._show import SHOW_EPILOG, show_command

project_app = typer.Typer(
    name="project",
    help="Make and inspect projects: one folder per client, holding pipelines, outputs and records.",
    no_args_is_help=True,
    add_completion=False,
)
project_app.command(name="new", epilog=NEW_EPILOG)(new_command)
project_app.command(name="show", epilog=SHOW_EPILOG)(show_command)
project_app.command(name="list", epilog=LIST_EPILOG)(list_command)

__all__ = [
    "SOURCE_SUFFIXES",
    "Placement",
    "create_project",
    "emit_column_yaml",
    "only_pipeline",
    "placed_members",
    "prepare",
    "project_app",
    "resolve_destination",
    "run_all",
    "source_text",
    "target_text",
    "wrap_review_comment",
    "yaml_quote",
    "yaml_scalar",
]
