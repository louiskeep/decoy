"""`decoy unmask` -- recover fpe-masked columns from a masked output file.

Capability-gaps WS1 (2026-06-12). The inverse of the fpe leg of
`decoy run`: the SAME pipeline config the mask run used carries the
seed (the secret) plus per-column namespace/charset, which is exactly
what `decoy_engine.unmask_pipeline` needs to re-derive the Feistel key
and invert the permutation. One-way strategies (hash, redact, faker,
date_shift, ...) pass through unchanged and are reported irreversible.

SECURITY: anyone holding the pipeline config can reverse its fpe
columns. Treat the config file (specifically `global_settings.seed`)
with the sensitivity of a decryption key.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success, warn

_UNMASK_EPILOG = """\
Examples:

  decoy unmask pipeline.yaml masked.csv
    Recover fpe columns into masked.unmasked.csv.

  decoy unmask pipeline.yaml masked.csv --output recovered.csv
    Choose the output path.

  decoy unmask pipeline.yaml masked.csv --table accounts
    Disambiguate when the config masks more than one table.

  decoy unmask pipeline.yaml masked.csv --json
    Emit the per-column reversibility report as JSON.

  decoy unmask pipeline.yaml masked.csv --vault vault.bin
    Also recover one-way columns the mask run vaulted
    (decoy run ... --vault vault.bin with vault: true columns).

Only `strategy: fpe` columns reverse from the config alone; hash,
redact, faker and the other one-way strategies pass through unchanged
unless the column was vaulted at mask time. The config carries the
seed: treat it as a key; the vault file is a re-identification map,
store it separately from the masked output.

See also: decoy run, decoy explain strategies.
"""


def unmask(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The pipeline config the mask run used (carries seed + namespaces).",
    ),
    masked: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The masked CSV produced by `decoy run` for one table.",
    ),
    table: str | None = typer.Option(
        None,
        "--table",
        help="Which config table the masked file belongs to. Required when the config masks more than one table.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Where to write the recovered CSV. Default: <masked>.unmasked.csv next to the input.",
    ),
    vault: Path | None = typer.Option(
        None,
        "--vault",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Vault file the mask run wrote (decoy run --vault). Recovers "
            "one-way columns declared vault: true; decrypts under the "
            "config's seed."
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
    """Recover fpe-masked columns from a masked file using the pipeline config.

    Reverses every `strategy: fpe` column (format-preserving encryption is
    a keyed bijection; the key derives from the config's seed + namespace).
    Other strategies are one-way and pass through unchanged with an
    `irreversible` report entry. Exits 0 on success, 1 on a config/usage
    error, 3 on a runtime failure.
    """
    state = setup_output(json_, quiet, verbose)

    def _emit_error(message: str, *, hint_text: str | None = None) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "unmask",
                    "status": "error",
                    "config": str(config),
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), message)
            if hint_text:
                state.err_console.print(" ", hint("hint:"), hint_text)

    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _emit_error(f"YAML parse error: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    if not isinstance(raw, dict):
        _emit_error(
            f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}."
        )
        raise typer.Exit(code=EXIT_USAGE)

    mask_tables = [
        t.get("name")
        for t in (raw.get("tables") or [])
        if isinstance(t, dict) and t.get("name") and t.get("columns")
    ]
    if table is not None:
        if table not in mask_tables:
            _emit_error(
                f"table {table!r} is not a mask table in this config "
                f"(mask tables: {', '.join(mask_tables) or 'none'})."
            )
            raise typer.Exit(code=EXIT_USAGE)
        target_table = table
    elif len(mask_tables) == 1:
        target_table = mask_tables[0]
    else:
        _emit_error(
            f"config has {len(mask_tables)} mask tables; pass --table to pick "
            f"the one this file belongs to ({', '.join(mask_tables) or 'none'}).",
            hint_text="decoy unmask pipeline.yaml masked.csv --table <name>",
        )
        raise typer.Exit(code=EXIT_USAGE)

    import pandas as pd
    import pyarrow as pa
    from decoy_engine import VaultError, unmask_pipeline
    from decoy_engine.errors import ConfigError
    from decoy_engine.execution import ExecutionError
    from decoy_engine.plan import PlanCompileError

    try:
        df = pd.read_csv(masked, dtype=str)
    except Exception as exc:
        _emit_error(f"could not read {masked}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    try:
        result = unmask_pipeline(
            raw,
            {target_table: pa.Table.from_pandas(df, preserve_index=False)},
            vault_path=str(vault) if vault is not None else None,
        )
    except (ExecutionError, PlanCompileError, ConfigError) as exc:
        _emit_error(
            f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', exc)}"
        )
        raise typer.Exit(code=EXIT_USAGE)
    except VaultError as exc:
        # A bad or mismatched vault is an input problem, not a CLI crash.
        if getattr(exc, "code", None) == "vault_protocol_version_mismatch":
            _emit_error(
                f"{exc.code}: {exc.message}",
                hint_text=(
                    "the vault was written under a different engine protocol version; "
                    "re-mask under the current engine, or unmask with the engine "
                    "version that wrote the vault."
                ),
            )
        else:
            _emit_error(
                f"{getattr(exc, 'code', type(exc).__name__)}: "
                f"{getattr(exc, 'message', exc)}"
            )
        raise typer.Exit(code=EXIT_USAGE)
    except Exception as exc:  # runtime failure, not a usage problem
        _emit_error(f"unmask failed: {type(exc).__name__}: {exc}"[:500])
        raise typer.Exit(code=EXIT_RUNTIME)

    out_path = output if output is not None else masked.with_suffix(".unmasked.csv")
    result.outputs[target_table].to_pandas().to_csv(out_path, index=False)

    entries = [
        {
            "table": r.table,
            "column": r.column,
            "strategy": r.strategy,
            "status": r.status,
            "detail": r.detail,
        }
        for r in result.columns
    ]

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "unmask",
                "status": "ok",
                "config": str(config),
                "input": str(masked),
                "output": str(out_path),
                "table": target_table,
                "columns": entries,
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return

    reversed_count = sum(1 for e in entries if e["status"] == "reversed")
    vault_reversed_count = sum(1 for e in entries if e["status"] == "vault_reversed")
    summary = (
        f"  {reversed_count} column(s) reversed, "
        f"{sum(1 for e in entries if e['status'] == 'irreversible')} irreversible, "
        f"{sum(1 for e in entries if e['status'] == 'untouched')} untouched."
    )
    if vault is not None:
        summary = summary[:-1] + f", {vault_reversed_count} vault-reversed."
    state.console.print(success("OK"), code(str(out_path)))
    state.console.print(summary)
    for e in entries:
        if e["status"] in ("reversed", "vault_reversed", "vault_miss") and e["detail"]:
            state.console.print(" ", warn("note:"), f"{e['column']}: {e['detail']}")


UNMASK_EPILOG = _UNMASK_EPILOG
