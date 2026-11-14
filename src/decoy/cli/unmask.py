"""`decoy unmask` -- recover fpe-masked columns from a masked output file.

Capability-gaps WS1 (2026-06-12). The inverse of the fpe leg of
`decoy run`: the SAME pipeline config the mask run used carries the
mask secret reference (`--mask-secret` or `global_settings.mask_secret_ref`) plus per-column
namespace/charset, which is exactly what `decoy_engine.unmask_pipeline`
needs to re-derive the Feistel key and invert the permutation. One-way strategies (hash, redact, faker,
date_shift, ...) pass through unchanged and are reported irreversible.

SECURITY: anyone holding the mask secret and the config can reverse its
fpe columns. The secret is the decryption key; the config only names it.
"""

from __future__ import annotations

from pathlib import Path

import typer

from decoy import _mask_secret, _mask_secret_guidance
from decoy._atomic import AtomicWriteError, describe
from decoy._config_file import ConfigFileError, config_refusal, load_config_mapping
from decoy.cli._sources import read_file
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE, exit_code_for
from decoy.cli.io import (
    TargetFormatError,
    check_output_path,
    format_for_path,
    input_format,
    pipeline_argument,
    resolve_pipeline,
    write_private_table,
)
from decoy.ui.output import OutputMode, emit_error, emit_json, setup_output
from decoy.ui.theme import code, success, warn

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
unless the column was vaulted at mask time. --mask-secret (or the
config's global_settings.mask_secret_ref) must name the secret the mask
run used; the vault file is a re-identification map, store it separately from the
masked output.

See also: decoy run, decoy explain transforms.
"""


def unmask(
    config: str = pipeline_argument(
        help=(
            "The pipeline config the mask run used. The mask secret (--mask-secret or "
            "its global_settings.mask_secret_ref) must be the one that run used."
        ),
    ),
    masked: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The masked file produced by `decoy run` for one table (read by the target's declared format, else by extension).",
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
            "mask secret (--mask-secret or global_settings.mask_secret_ref)."
        ),
    ),
    mask_secret: str | None = typer.Option(None, "--mask-secret", help=_mask_secret.FLAG_HELP),
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
    a keyed bijection; the key derives from the mask secret + namespace).
    Other strategies are one-way and pass through unchanged with an
    `irreversible` report entry. Exits 0 on success, 1 on a config/usage
    error, 3 on a runtime failure.
    """
    state = setup_output(json_, quiet, verbose)
    config_path = resolve_pipeline(config, state, "unmask").yaml

    def _emit_error(message: str, *, hint_text: str | None = None, code: str | None = None) -> None:
        emit_error(
            state, "unmask", message, code=code, hint=hint_text, context={"config": str(config)}
        )

    try:
        raw = load_config_mapping(config_path)
    except (ConfigFileError, OSError) as exc:
        _emit_error(**config_refusal(exc))
        raise typer.Exit(code=exit_code_for(exc))
    try:
        _mask_secret.apply_mask_secret(raw, mask_secret)
    except _mask_secret.MaskSecretFlagError as exc:
        _emit_error(str(exc))
        raise typer.Exit(code=EXIT_USAGE)

    if output is not None:
        try:
            check_output_path(output)
        except TargetFormatError as exc:
            _emit_error(f"{exc.code}: {exc}")
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

    import pyarrow as pa
    from decoy_engine import VaultError, unmask_pipeline
    from decoy_engine.errors import ConfigError
    from decoy_engine.execution import ExecutionError
    from decoy_engine.keyprovider import MaskSecretError
    from decoy_engine.plan import PlanCompileError

    # The declared format of the table's target when `masked` is that file, else the suffix rule.
    try:
        in_format, in_layout = input_format(raw, target_table, masked, config_path.parent)
    except TargetFormatError as exc:
        _emit_error(f"{exc.code}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)

    try:
        df = read_file(masked, in_format, in_layout, table=target_table)
    except Exception as exc:
        # The type only: a parse error can quote a cell, and the path is not ours to print.
        _emit_error(f"could not read the masked file: {type(exc).__name__}")
        raise typer.Exit(code=EXIT_USAGE)

    declared = [
        c.get("name")
        for t in raw.get("tables") or []
        if isinstance(t, dict) and t.get("name") == target_table
        for c in t.get("columns") or []
        if isinstance(c, dict)
    ]
    if declared and not any(name in df.columns for name in declared):
        _emit_error(
            "unmask_columns_missing: the input holds none of the configured columns for "
            "this table; check that the file and --table match the run and that the file "
            "is in the format the target declares."
        )
        raise typer.Exit(code=EXIT_USAGE)

    try:
        # Admitted the way `run` admits it (an owner-only `file:` is checked on its open
        # descriptor); the engine gets the provider and never reads the ref itself.
        with _mask_secret.admitted_key_provider(raw) as key_provider:
            result = unmask_pipeline(
                raw,
                {target_table: pa.Table.from_pandas(df, preserve_index=False)},
                vault_path=str(vault) if vault is not None else None,
                key_provider=key_provider,
            )
    except MaskSecretError as exc:
        # Before the class branches: a secret refusal gets its remedy whatever else it is.
        _emit_error(_mask_secret_guidance.secret_error_text(exc, _mask_secret_guidance.UNMASK))
        raise typer.Exit(code=EXIT_USAGE)
    except PlanCompileError as exc:
        from decoy.cli.extras import plan_compile_error_fields

        err_code, message = plan_compile_error_fields(exc)
        _emit_error(f"{err_code}: {message}")
        raise typer.Exit(code=EXIT_USAGE)
    except (ExecutionError, ConfigError) as exc:
        _emit_error(f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', exc)}")
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
                f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', exc)}"
            )
        raise typer.Exit(code=EXIT_USAGE)
    except Exception as exc:  # runtime failure, not a usage problem
        # The type only: a runtime error's text can quote a source or masked cell.
        _emit_error(f"unmask failed: {type(exc).__name__}")
        raise typer.Exit(code=EXIT_RUNTIME)

    out_path = output if output is not None else masked.with_suffix(".unmasked.csv")
    try:
        write_private_table(result.outputs[target_table], format_for_path(out_path), out_path)
    except AtomicWriteError as exc:
        _emit_error(f"could not write the output: {describe(exc)}")
        raise typer.Exit(code=EXIT_RUNTIME)

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

    # `table_missing` is a pseudo-entry (column "*") for a CONFIGURED TABLE
    # absent from this single-file input (engine unmask.py ~L247), not a
    # column of the file we processed. Split it out so it is never counted
    # as a "column(s)"; it gets its own clause below.
    table_missing = [e for e in entries if e["status"] == "table_missing"]
    column_entries = [e for e in entries if e["status"] != "table_missing"]

    # Complete census: every present-column status the engine can emit
    # (enumerated from decoy_engine/unmask.py), so the counts always sum to
    # the number of real columns and no status can silently vanish. Keeping
    # all six -- not just the ones a given run happens to hit -- is what makes
    # the arithmetic honest if a previously-unreachable status starts firing.
    _CENSUS_STATUSES = (
        "reversed",
        "reversed_unverified",
        "vault_reversed",
        "vault_miss",
        "irreversible",
        "untouched",
    )
    counts = {
        status: sum(1 for e in column_entries if e["status"] == status)
        for status in _CENSUS_STATUSES
    }
    summary = (
        f"  {counts['reversed']} column(s) reversed, "
        f"{counts['irreversible']} irreversible, "
        f"{counts['untouched']} untouched."
    )
    # Surface each secondary bucket whenever it is non-empty, independent of
    # --vault: `vault_miss` arises precisely when a vault could NOT reverse a
    # requested column, and `reversed_unverified` for every fpe reversal (FF1 is
    # unauthenticated, even under a real secret) -- both are genuine per-column outcomes an
    # operator must see, not artifacts of whether a vault was passed.
    if counts["reversed_unverified"]:
        summary = summary[:-1] + f", {counts['reversed_unverified']} reversed (unverified)."
    if counts["vault_reversed"]:
        summary = summary[:-1] + f", {counts['vault_reversed']} vault-reversed."
    if counts["vault_miss"]:
        summary = summary[:-1] + f", {counts['vault_miss']} vault-miss."
    # Absent configured tables are their own clause so real columns and
    # missing tables are never conflated in one count.
    if table_missing:
        summary = summary[:-1] + (f", {len(table_missing)} configured table(s) not in this input.")
    state.console.print(success("OK"), code(str(out_path)))
    state.console.print(summary)
    for e in entries:
        if (
            e["status"]
            in (
                "reversed",
                "reversed_unverified",
                "vault_reversed",
                "vault_miss",
                "table_missing",
            )
            and e["detail"]
        ):
            # table_missing carries column "*"; name the table instead so the
            # note identifies which configured table was absent.
            label = e["column"] if e["column"] != "*" else e["table"]
            state.console.print(" ", warn("note:"), f"{label}: {e['detail']}")


UNMASK_EPILOG = _UNMASK_EPILOG
