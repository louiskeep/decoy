"""`forge validate` — check whether a YAML pipeline config is well-formed."""

from pathlib import Path

import typer
from rich.console import Console

err_console = Console(stderr=True)
console = Console()


def validate(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config to validate.",
    ),
) -> None:
    """Validate a forge pipeline config without running it."""
    from forge_engine import validate_config
    from forge_engine.exceptions import ConfigError, PipelineValidationError

    try:
        validate_config(str(config))
    except (PipelineValidationError, ConfigError) as e:
        err_console.print(f"[red]Invalid config:[/red] {e}")
        raise typer.Exit(code=1)

    console.print(f"[green]OK[/green] {config}")
