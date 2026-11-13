"""`decoy project`: make, show and list projects (a folder with a `decoy.yaml` marker).

Commands import the project layout services from the public `decoy.cli.io` package, never a
`_` module there. `project_app` is registered in `decoy.__main__`.
"""

from __future__ import annotations

import typer

from decoy.cli.project._list import LIST_EPILOG, list_command
from decoy.cli.project._new import NEW_EPILOG, create_project, new_command
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

__all__ = ["create_project", "project_app"]
