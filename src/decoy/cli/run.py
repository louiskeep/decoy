"""`decoy run` -- execute a masking or synthetic-generation pipeline."""

import time
from enum import Enum
from pathlib import Path

import typer

from decoy.ui.card import render_card
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import spinner
from decoy.ui.theme import error, hint


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"
    convert = "convert"


_RUN_EPILOG = """\
Examples:

  decoy run pipeline.yaml
    Run with default mode (mask).

  decoy run pipeline.yaml --mode generate
    Generate a synthetic dataset from the config.

  decoy run pipeline.yaml --json
    Suppress chrome and emit a structured result for scripting.

See also: decoy validate.
"""


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
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout. Progress goes to stderr.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr; exit code carries success.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Run a decoy pipeline from a YAML config.

    Use this to execute a masking, synthetic-generation, or format-conversion
    job described in YAML. The engine handles its own logging per the YAML's
    `logging:` section; flags here only affect CLI-side output.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    started = time.perf_counter()
    try:
        with spinner(state, f"Running {mode.value}..."):
            if mode in (Mode.mask, Mode.convert):
                from decoy_engine import Masker

                Masker(config_str).mask()
            else:
                from decoy_engine import DataGenerator

                DataGenerator(config_str).generate()
    except Exception as exc:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "run",
                    "status": "error",
                    "config": config_str,
                    "mode": mode.value,
                    "error": str(exc),
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), str(exc))
            state.err_console.print(" ", hint("hint:"), "rerun with --verbose for the full traceback.")
        if state.verbose:
            state.err_console.print_exception()
        raise typer.Exit(code=3)

    elapsed = time.perf_counter() - started

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "run",
                "status": "ok",
                "config": config_str,
                "mode": mode.value,
                "elapsed_s": round(elapsed, 3),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    render_card(
        state,
        command="decoy run",
        facts=[
            ("Pipeline", config.name),
            ("Mode", mode.value),
            ("Elapsed", f"{elapsed:.2f}s"),
        ],
        next_hint=_next_hint_for_run(config, mode),
        status="ok",
    )


def _next_hint_for_run(config: Path, mode: "Mode") -> str | None:
    """Best-effort follow-up hint based on the YAML's output path."""
    try:
        import yaml

        cfg = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        out = cfg.get("output", {}).get("path") if isinstance(cfg, dict) else None
        if out:
            return f"head {out}"
    except Exception:
        pass
    return None


run.__doc__ = run.__doc__  # keep docstring; epilog wired by __main__ on registration


# Surfaced for __main__ to wire into typer.command(epilog=...)
RUN_EPILOG = _RUN_EPILOG
