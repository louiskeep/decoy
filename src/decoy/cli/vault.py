"""`decoy vault` -- vault inspection utilities.

A vault file is an AES-GCM-encrypted map from (namespace, masked_value)
to original source value, written by `decoy run --vault` for columns
declared `vault: true`. The `info` subcommand inspects a vault without
decoding every entry: it reports how many entries are present, which
namespaces appear, and how many ambiguous entries were dropped at write
time.

SECURITY: the vault is encrypted under a key derived from the pipeline
config's seed. The config must match the one used at mask time; a
mismatched seed surfaces a clean EXIT_USAGE error, not a traceback.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success

vault_app = typer.Typer(
    name="vault",
    help="Vault inspection utilities. `info` summarises a vault without full decode.",
    no_args_is_help=True,
)


_INFO_EPILOG = """\
Examples:

  decoy vault info vault.bin --config pipeline.yaml
    Show entry count, namespaces, and ambiguous-dropped count.

  decoy vault info vault.bin --config pipeline.yaml --json
    Same data as a JSON envelope for scripting.

  decoy vault info vault.bin --config pipeline.yaml --quiet
    Silent mode; exit code 0 = vault opened successfully.

The vault is encrypted under a key derived from the config's seed. The
config passed to --config must be the SAME config (or at least the same
global_settings.seed) used by the `decoy run --vault` call that wrote
the vault, otherwise the decrypt will fail and the command exits 1.

See also: decoy run --vault, decoy unmask --vault.
"""


def _info(
    vault: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The vault file written by `decoy run --vault`.",
    ),
    config: Path = typer.Option(
        ...,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "The pipeline config the mask run used (must carry the same seed "
            "as the run that wrote the vault)."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout. Errors still go to stderr.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress stdout. Errors still go to stderr; exit code carries the result.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level CLI logs on stderr.",
    ),
) -> None:
    """Inspect a vault file: report entry count, namespaces, and dropped-ambiguous count.

    Opens the vault using the seed derived from the pipeline config. A
    mismatched seed (wrong config) exits 1 with a clear error message.
    Exits 0 on success, 1 on a config/vault/usage error.
    """
    state = setup_output(json_, quiet, verbose)

    def _emit_error(message: str, *, hint_text: str | None = None) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "vault-info",
                    "status": "error",
                    "vault": str(vault),
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), message)
            if hint_text:
                state.err_console.print(" ", hint("hint:"), hint_text)

    # Parse config YAML.
    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _emit_error(f"YAML parse error in {config}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    if not isinstance(raw, dict):
        _emit_error(
            f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}."
        )
        raise typer.Exit(code=EXIT_USAGE)

    from decoy_engine import VaultError, job_seed_for_config, load_vault
    from decoy_engine.plan import PlanCompileError

    # Derive the job seed from the config (fails cleanly for bool/float seeds).
    try:
        job_seed = job_seed_for_config(raw)
    except PlanCompileError as exc:
        _emit_error(
            f"{getattr(exc, 'code', type(exc).__name__)}: "
            f"{getattr(exc, 'message', exc)}"
        )
        raise typer.Exit(code=EXIT_USAGE)

    # Open the vault.
    try:
        mapping, ambiguous_dropped = load_vault(str(vault), job_seed)
    except VaultError as exc:
        if getattr(exc, "code", None) == "vault_protocol_version_mismatch":
            _emit_error(
                f"{exc.code}: {exc.message}",
                hint_text=(
                    "the vault was written under a different engine protocol version; "
                    "re-mask under the current engine, or use the engine "
                    "version that wrote the vault."
                ),
            )
        else:
            _emit_error(
                f"{getattr(exc, 'code', type(exc).__name__)}: "
                f"{getattr(exc, 'message', exc)}",
                hint_text=(
                    "the config's seed does not match the vault; "
                    "use the same config (or seed) as the `decoy run --vault` call "
                    "that wrote this vault."
                ),
            )
        raise typer.Exit(code=EXIT_USAGE)

    entries = len(mapping)
    namespaces = sorted({ns for (ns, _) in mapping})

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "vault-info",
                "status": "ok",
                "vault": str(vault),
                "entries": entries,
                "namespaces": namespaces,
                "ambiguous_dropped": ambiguous_dropped,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("OK"), code(str(vault)))
    state.console.print(f"  entries:           {entries}")
    state.console.print(f"  namespaces ({len(namespaces)}):   {', '.join(namespaces) or '(none)'}")
    state.console.print(f"  ambiguous dropped: {ambiguous_dropped}")


vault_app.command(name="info", epilog=_INFO_EPILOG)(_info)
