"""`decoy run` — execute a masking or synthetic-generation pipeline from a YAML config."""

import logging
from enum import Enum
from pathlib import Path

import typer


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"
    convert = "convert"


def run(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config.",
    ),
    mode: Mode = typer.Option(
        Mode.mask,
        "--mode",
        "-m",
        help="Operation: mask existing data, generate synthetic data, or convert format.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose CLI output."
    ),
) -> None:
    """Run a decoy pipeline from a YAML config.

    The engine handles its own logging according to the YAML's `logging`
    section. CLI flags here only affect output from the CLI itself.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )
    cli_log = logging.getLogger("decoy")

    config_str = str(config)

    if mode in (Mode.mask, Mode.convert):
        from decoy_engine import Masker

        Masker(config_str).mask()
        cli_log.info(f"{mode.value} completed: {config}")
    elif mode is Mode.generate:
        from decoy_engine import DataGenerator

        DataGenerator(config_str).generate()
        cli_log.info(f"generate completed: {config}")
