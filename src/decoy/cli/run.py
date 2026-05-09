"""`decoy run` -- execute a masking or synthetic-generation pipeline."""

import binascii
import os
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
    graph = "graph"


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
        case_sensitive=False,
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
    master_key: str = typer.Option(
        None,
        "--master-key",
        envvar="DECOY_MASTER_KEY",
        help=(
            "64-char hex master key for keyed deterministic masking. "
            "Same key + same --key-label always yield bitwise-identical "
            "output across runs and machines. Reads DECOY_MASTER_KEY env "
            "var when omitted; without either, masking falls back to the "
            "legacy seeded path (per-input deterministic but not portable)."
        ),
    ),
    key_label: str = typer.Option(
        None,
        "--key-label",
        help=(
            "Stable namespace string for the masking key hierarchy. "
            "Required when --master-key is set. Pick something durable "
            "(e.g. 'customers_q4'); changing it produces a different "
            "masked output. Read from the YAML's top-level 'key_label:' "
            "field if not passed on the command line."
        ),
    ),
) -> None:
    """Run a decoy pipeline from a YAML config.

    Use this to execute a masking, synthetic-generation, or format-conversion
    job described in YAML. The engine handles its own logging per the YAML's
    `logging:` section; flags here only affect CLI-side output.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    # Mode is read from the YAML when present; the --mode flag remains a
    # back-compat hint for legacy YAML that omits a top-level mode key.
    yaml_mode = _detect_mode(config) or mode.value

    # Build the keyed-determinism resolver if the user supplied a master key.
    # Falls back to None (legacy seeded path) when no key is configured.
    resolver = _build_resolver(master_key, key_label, config, state)

    started = time.perf_counter()
    try:
        with spinner(state, f"Running {yaml_mode}..."):
            from decoy_engine.context import ExecutionContext
            ctx = ExecutionContext(derive_key=resolver)

            if yaml_mode == "graph":
                from decoy_engine import run_graph

                yaml_text = config.read_text(encoding="utf-8")
                result = run_graph(yaml_text, ctx=ctx)
                if not result.get("success"):
                    failed = next(
                        (n for n in result.get("nodes", []) if n.get("status") == "error"),
                        None,
                    )
                    if failed:
                        raise RuntimeError(
                            f"node {failed['node_id']!r} ({failed.get('kind')}): {failed.get('error')}"
                        )
                    raise RuntimeError("graph run failed")
            elif yaml_mode in ("mask", "convert"):
                from decoy_engine import Masker

                Masker(config_str, ctx=ctx).mask()
            else:
                from decoy_engine import DataGenerator

                # DataGenerator doesn't yet consume ctx.derive_key (precondition
                # for recursive-determinism work); pass ctx anyway so the
                # interface is uniform and the future wire-up is one-line.
                DataGenerator(config_str, ctx=ctx).generate()
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
                "mode": yaml_mode,
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
            ("Mode", yaml_mode),
            ("Elapsed", f"{elapsed:.2f}s"),
        ],
        next_hint=_next_hint_for_run(config, mode),
        status="ok",
    )


def _build_resolver(master_key_hex: str | None, key_label: str | None, config_path: Path, state):
    """Construct the engine-facing ``derive_key`` resolver, or None when no
    master key was supplied. Keeps the legacy seeded fallback default so
    runs without a key behave exactly as before."""
    if not master_key_hex:
        return None

    # Normalize: accept hex with or without leading 0x; trim whitespace.
    raw = master_key_hex.strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    try:
        master = bytes.fromhex(raw)
    except (ValueError, binascii.Error) as exc:
        raise typer.BadParameter(
            f"--master-key must be valid hex ({exc}). Generate one via: "
            "python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    if len(master) != 32:
        raise typer.BadParameter(
            f"--master-key must decode to 32 bytes (got {len(master)})."
        )

    # Pull key_label from YAML if not on the command line.
    label = key_label or _detect_key_label(config_path)
    if not label:
        raise typer.BadParameter(
            "--master-key requires a --key-label (or top-level 'key_label:' "
            "in the YAML). Pick a stable namespace string like 'customers_q4'."
        )

    from decoy_engine import make_key_resolver
    return make_key_resolver(master, label)


def _detect_key_label(config_path: Path) -> str | None:
    """Read the top-level ``key_label:`` from the YAML, or return None."""
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            label = cfg.get("key_label")
            if isinstance(label, str) and label.strip():
                return label.strip()
    except Exception:
        pass
    return None


def _detect_mode(config_path: Path) -> str | None:
    """Read the top-level ``mode:`` from the YAML, or return None if absent."""
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            m = cfg.get("mode")
            if isinstance(m, str):
                return m.lower()
    except Exception:
        pass
    return None


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
