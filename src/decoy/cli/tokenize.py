"""`decoy tokenize` / `decoy detokenize` -- reversible tokenization over the
engine's keyed token-vault seam (A-8), backed by a LOCAL vault store (B-1).

`decoy tokenize` runs a masking job in which `strategy: tokenize` columns are
replaced by deterministic surrogates; the engine derives each token (keyed
HKDF-SHA256, see `decoy_engine ...tokenize`) and records the
`(namespace, plaintext) -> token` mapping through a LocalTokenVault, a SQLite
file this CLI owns. `decoy detokenize` is the inverse: it reads that same local
vault and restores a tokenized column by reversing `(namespace, token) ->
plaintext`.

Single-operator, local scope (V1). There is NO user or permission model here:
reversing is gated only by possession of the local vault file. The multi-user
auth model for de-tokenization is the platform's job (B-6), not the CLI's. The
engine owns the token derivation and the NFC normalization; the CLI only
persists and looks up the mapping (no hand-rolled crypto).

SECURITY: the vault file is the only place the plaintext-to-token mapping
lives. Store it separately from the tokenized output -- together they
re-identify every tokenized value. Neither verb ever prints or logs a plaintext
or a token; both surface counts and column/namespace names only.
"""

from __future__ import annotations

from pathlib import Path

import typer

from decoy import _mask_secret, _mask_secret_guidance
from decoy._atomic import AtomicWriteError, describe
from decoy.cli._sources import read_file
from decoy.cli._token_vault import LocalTokenVault, TokenVaultError, iter_tokenize_columns
from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.io import (
    TargetFormatError,
    check_output_path,
    format_for_path,
    input_format,
    write_private_table,
)
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.progress import spinner
from decoy.ui.theme import code, error, hint, success, warn

_TOKENIZE_EPILOG = """\
Examples:

  decoy tokenize pipeline.yaml --vault tokens.db --mask-secret env:DECOY_MASK_SECRET
    Run the pipeline, replacing every `strategy: tokenize` column with a
    deterministic surrogate, and write the (namespace, plaintext) -> token
    mapping to the local vault tokens.db. The mask secret (env:NAME or
    file:/PATH to a >=32-byte secret) keys the tokens.

  decoy tokenize pipeline.yaml --vault tokens.db
    The same run when the YAML already sets global_settings.mask_secret_ref.

A mask secret is REQUIRED (--mask-secret OR global_settings.mask_secret_ref, in
exactly one place): tokenize fails closed without one, because tokens keyed on
the public pipeline seed are forgeable offline -- anyone with the config could
recompute them without the vault.

Each `strategy: tokenize` column needs an explicit `namespace:` in the YAML
(the token is keyed on it, so different namespaces tokenize apart). Tokens are
deterministic: the same plaintext under the same namespace always maps to the
same token, and the vault is authoritative -- re-running against the same vault
reuses stored tokens. Reverse a tokenized file with `decoy detokenize`. Store
the vault separately from the output and treat it as sensitive.

At rest the vault is cleartext (not encrypted): decoy creates it 0600 (and a
newly created parent directory 0700) as the mitigation. The file is the whole
re-identification map, so keep it off shared storage and out of backups.

See also: decoy detokenize, decoy run, decoy explain tokenize.
"""

_FORMAT_NAMES = {"csv": "CSV", "parquet": "Parquet", "fixed_width": "fixed width"}

_DETOKENIZE_EPILOG = """\
Examples:

  decoy detokenize pipeline.yaml tokenized.csv --vault tokens.db
    Restore every tokenize column in tokenized.csv from the local vault,
    writing tokenized.detokenized.csv.

  decoy detokenize pipeline.yaml tokenized.csv --vault tokens.db -o recovered.csv
    Choose the output path.

  decoy detokenize pipeline.yaml tokenized.csv --vault tokens.db --table accounts
    Disambiguate when the config tokenizes more than one table.

The config supplies each tokenize column's namespace; the vault supplies the
reverse mapping. The tokenized file is read in the format tokenize wrote it: the
table's declared target format when the file is that target, otherwise by its
extension (.parquet or .pq is Parquet, anything else CSV). The recovered file is
written as Parquet for Parquet input and CSV otherwise. A missing vault, a vault
that is not a decoy token vault, or a token that is not in the vault under the
column's namespace (a wrong vault or wrong namespace) fails closed -- no output is written -- rather than emit a
value it cannot vouch for. So does a file missing any tokenize column the
config declares for the table, and an already-existing default output
(<tokenized>.detokenized.<ext>); pass -o to choose a path deliberately.

The recovered file is cleartext PII. On Linux and macOS it is written
owner-only (0600), like the vault; on Windows it inherits its folder's permissions. Protect
any copy you make.

See also: decoy tokenize, decoy explain tokenize.
"""


_is_valid_mask_secret_ref = _mask_secret.is_valid_mask_secret_ref


def tokenize(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config (with `strategy: tokenize` columns).",
    ),
    vault: Path = typer.Option(
        ...,
        "--vault",
        help=(
            "Local token vault file to write the (namespace, plaintext) -> token "
            "mapping to (created if absent). Required: tokenize fails closed "
            "without a vault. Store it separately from the output; it "
            "re-identifies every tokenized value."
        ),
    ),
    mask_secret: str = typer.Option(
        None,
        "--mask-secret",
        help=(
            "env:NAME or file:/PATH pointing at a >=32-byte mask secret to key the "
            "tokens from. REQUIRED unless the YAML sets "
            "global_settings.mask_secret_ref: tokenize fails closed without an "
            "effective secret, because seed-derived tokens are forgeable offline "
            "from the public pipeline seed. Sets 'global_settings.mask_secret_ref' "
            "for this run; an error if the YAML already sets it. Explicit flag only "
            "(no env var)."
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
    """Run a tokenize masking job, writing the token mapping to a local vault.

    Replaces every `strategy: tokenize` column with a deterministic surrogate
    (derived by the engine, keyed on the column namespace) and records the
    reverse mapping in the local vault so `decoy detokenize` can recover the
    originals. A mask secret is required (--mask-secret or
    global_settings.mask_secret_ref); without one the tokens would derive from
    the public pipeline seed and be forgeable offline, so tokenize fails closed.
    Exits 0 on success, 1 on a config/usage error, 3 on a runtime failure.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    def _emit_error(message: str, *, hint_text: str | None = None) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "tokenize",
                    "status": "error",
                    "config": config_str,
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            # markup=False: engine/vault text can carry `[...]` (e.g. an install
            # hint) that Rich would otherwise parse as markup and drop.
            state.err_console.print(error("error:"), message, markup=False)
            if hint_text:
                state.err_console.print(" ", hint("hint:"), hint_text)

    import yaml as _yaml

    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _emit_error(sanitize_yaml_error(exc))
        raise typer.Exit(code=EXIT_USAGE)
    if not isinstance(raw, dict):
        _emit_error(f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.")
        raise typer.Exit(code=EXIT_USAGE)

    # DE-02 secret-disclosure ROOT guard (mirrors decoy.cli.run): validate the
    # RAW YAML global_settings / mask_secret_ref BEFORE PipelineConfig.model_validate.
    # A wrong-type mask_secret_ref would otherwise ride a Pydantic ValidationError
    # (which echoes input_value, i.e. the secret) into str(exc) below, leaking it.
    # Redacted here so no ref value ever reaches Pydantic's diagnostics.
    _raw_gs = raw.get("global_settings")
    if _raw_gs is not None and not isinstance(_raw_gs, dict):
        _emit_error(
            "global_settings must be a mapping (a YAML block of key: value "
            f"pairs), not a {type(_raw_gs).__name__}."
        )
        raise typer.Exit(code=EXIT_USAGE)
    _raw_ref = _raw_gs.get("mask_secret_ref") if isinstance(_raw_gs, dict) else None
    if _raw_ref is not None and not _is_valid_mask_secret_ref(_raw_ref):
        _emit_error(
            "Invalid global_settings.mask_secret_ref: expected an 'env:NAME' or "
            "'file:/PATH' reference to a >=32-byte secret. It is a REFERENCE, "
            "never the raw secret. See: decoy explain keys."
        )
        raise typer.Exit(code=EXIT_USAGE)

    # --mask-secret injects the same global_settings.mask_secret_ref slot the
    # YAML can set; one secret source per run, chosen explicitly. Keyed on
    # PRESENCE so a YAML `mask_secret_ref: ""` is still "configured" and the
    # flag must not silently override it.
    if mask_secret is not None:
        if not _is_valid_mask_secret_ref(mask_secret):
            _emit_error(
                "Invalid --mask-secret: expected an 'env:NAME' or 'file:/PATH' "
                "reference to a >=32-byte secret. It is a REFERENCE, never the raw secret."
            )
            raise typer.Exit(code=EXIT_USAGE)
        gs = raw.get("global_settings")
        if isinstance(gs, dict) and gs.get("mask_secret_ref") is not None:
            _emit_error(
                "--mask-secret was passed but the YAML already sets "
                "global_settings.mask_secret_ref. Set the masking secret in "
                "exactly one place."
            )
            raise typer.Exit(code=EXIT_USAGE)

    from decoy_engine import PipelineConfig, run_pipeline
    from decoy_engine import __version__ as engine_version
    from decoy_engine.errors import ConfigError
    from decoy_engine.execution import ExecutionError
    from decoy_engine.plan import PlanCompileError

    try:
        from pydantic import ValidationError as _PydanticValidationError

        config_dict = PipelineConfig.model_validate(raw).model_dump()
    except _PydanticValidationError as exc:
        _emit_error(str(exc)[:500])
        raise typer.Exit(code=EXIT_USAGE)

    if mask_secret is not None:
        config_dict.setdefault("global_settings", {})["mask_secret_ref"] = mask_secret

    # Fail closed before any work when the config declares no tokenize column:
    # the vault would be pointless and this is almost always operator error
    # (wrong config, or `strategy: tokenize` misspelled).
    tok_cols: list[tuple[str, str, str]] = []  # (table, column, namespace)
    for table in config_dict.get("tables") or []:
        if not isinstance(table, dict) or not table.get("name"):
            continue
        for col, ns in iter_tokenize_columns(config_dict, table["name"]):
            tok_cols.append((table["name"], col, ns))
    if not tok_cols:
        _emit_error(
            "no column declares `strategy: tokenize` in this config; tokenize "
            "has nothing to write to the vault.",
            hint_text="add `strategy: tokenize` (with a `namespace:`) to a column.",
        )
        raise typer.Exit(code=EXIT_USAGE)

    # Every tokenize column needs an explicit namespace -- the token is keyed on
    # it and detokenize reverses by it. Report it here (before opening the
    # vault) with the same reason the engine would raise.
    missing_ns = [f"{t}.{c}" for (t, c, ns) in tok_cols if not ns]
    if missing_ns:
        _emit_error(
            "these tokenize columns have no `namespace:` (the token is keyed on "
            f"it, so it is required): {', '.join(missing_ns)}."
        )
        raise typer.Exit(code=EXIT_USAGE)

    # BLOCKER (B-1): tokenize is ALWAYS keyed. The engine (>=0.17.0) also rejects a
    # keyed run with no secret, but this check keeps the CLI's own coded error; with
    # no secret every token is tok_ + derive(job_seed, namespace, NFC(plaintext)),
    # and job_seed is public, so anyone holding the output plus the config can
    # recompute the tokens offline and re-identify low-entropy values WITHOUT the
    # vault -- the exact "only the vault reverses it" promise tokenize makes. So
    # require an effective mask secret and fail closed (coded) when none is set,
    # ahead of the engine's GA hard-error. Both input paths are already
    # format-validated (the flag above; the YAML by the ROOT guard), so a present
    # ref is well-formed here; PRESENCE is what is checked.
    effective_ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
    if effective_ref is None:
        _emit_error(
            "tokenize_requires_secret: tokenize needs a mask secret so tokens are "
            "not derivable from the public pipeline seed. Pass --mask-secret "
            "env:NAME (or file:/PATH to a >=32-byte secret), or set "
            "global_settings.mask_secret_ref in the config.",
            hint_text="decoy tokenize pipeline.yaml --vault tokens.db --mask-secret env:DECOY_MASK_SECRET",
        )
        raise typer.Exit(code=EXIT_USAGE)
    # Defense-in-depth: a mask_secret_ref is only honored by a DE-02 engine; one
    # without the keyprovider module would SILENTLY IGNORE the ref and emit
    # job-seed-keyed (forgeable) tokens. The engine pin guarantees it; probe
    # anyway and refuse rather than leak an unkeyed artifact on a broken install.
    try:
        # Importing the name doubles as the keyprovider presence probe (an
        # ImportError means a pre-DE-02 engine) and binds MaskSecretError for
        # the run_pipeline failure handler below, which maps a well-shaped but
        # unresolvable secret (missing env var, unreadable/short file) to a
        # clean coded usage error instead of the catch-all.
        from decoy_engine.keyprovider import MaskSecretError
    except ImportError as exc:
        _emit_error(_mask_secret_guidance.OLD_ENGINE_TOKENIZE)
        raise typer.Exit(code=EXIT_USAGE) from exc

    from decoy.cli.run import _load_sources_from_config, _write_mask_outputs

    # Whether the vault file already existed: a failed run only removes a file
    # THIS run created (see the finally), never a re-run's pre-existing vault.
    vault_preexisted = vault.exists()
    token_vault: LocalTokenVault | None = None
    committed = False
    try:
        with spinner(state, "Tokenizing..."):
            sources = _load_sources_from_config(config_dict, config.parent)
            instance_locale = (config_dict.get("global_settings") or {}).get("default_locale")
            # The CLI admits the secret (an owner-only `file:` is checked on its open
            # descriptor) and hands the engine the provider, so the engine never reads the
            # ref itself.
            with _mask_secret.admitted_key_provider(config_dict) as key_provider:
                token_vault = LocalTokenVault(vault, create=True)
                result = run_pipeline(
                    config_dict,
                    sources,
                    engine_version=engine_version,
                    instance_default_locale=instance_locale,
                    token_vault_writer=token_vault,
                    key_provider=key_provider,
                )
            vault_count = token_vault.count()
            row_count = sum(len(tbl) for tbl in result.outputs.values())
            # The mapping is durable BEFORE any output is published: tokenized output whose
            # mapping was never committed can never be reversed. A failure before commit
            # leaves no partial vault; `committed` is the exact "mappings are on disk" flag
            # for the finally's cleanup.
            token_vault.commit()
            committed = True
            _write_mask_outputs(config_dict, result, config.parent)
    except TokenVaultError as exc:
        _emit_error(f"{exc.code}: {exc.message}")
        raise typer.Exit(code=EXIT_USAGE)
    except MaskSecretError as exc:
        # A fixable operator problem; dispatched on the code before the classes below.
        _emit_error(_mask_secret_guidance.secret_error_text(exc, _mask_secret_guidance.TOKENIZE))
        raise typer.Exit(code=EXIT_USAGE)
    except (PlanCompileError, ExecutionError, ConfigError, TargetFormatError) as exc:
        _emit_error(f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', exc)}")
        raise typer.Exit(code=EXIT_USAGE)
    except AtomicWriteError as exc:
        _emit_error(f"could not write the output: {describe(exc)}")
        raise typer.Exit(code=EXIT_RUNTIME)
    except typer.Exit:
        raise
    except Exception as exc:  # unexpected runtime failure, not a usage problem
        # Never echo the exception text: engine tokenize errors are value-free
        # today, but a future non-vault error (e.g. a pandas codec error) could
        # embed a source cell value. Surface the type only -- never the message.
        if committed:
            _emit_error(
                f"tokenize failed with an unexpected {type(exc).__name__} while writing "
                "the output; the vault was committed first, so it holds this run's "
                "mappings. Earlier tables' outputs may already be written; a failed table's "
                "output is unchanged. Re-run."
            )
        else:
            _emit_error(
                f"tokenize failed with an unexpected {type(exc).__name__}; the run was "
                "aborted before the vault was committed, so it holds no mappings from "
                "this run. No output was written."
            )
        raise typer.Exit(code=EXIT_RUNTIME) from exc
    finally:
        if token_vault is not None:
            token_vault.close()
        # LocalTokenVault(create=True) writes the file + schema up front, so a
        # run that fails before commit leaves an empty vault on disk even though
        # its rows were discarded. Remove that file when THIS run created it and
        # nothing was committed, so a failed tokenize leaves no empty vault to
        # mistake for output. A pre-existing vault (a re-run) is kept: its prior
        # mappings are intact and only this run's uncommitted rows were dropped.
        if not committed and not vault_preexisted and vault.exists():
            vault.unlink(missing_ok=True)

    columns = [{"table": t, "column": c, "namespace": ns} for (t, c, ns) in tok_cols]
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "tokenize",
                "status": "ok",
                "config": config_str,
                "vault": str(vault),
                "rows": row_count,
                "vault_entries": vault_count,
                "columns": columns,
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return

    state.console.print(success("OK"), code(str(vault)))
    state.console.print(
        f"  {len(tok_cols)} tokenize column(s), {row_count} row(s); "
        f"{vault_count} mapping(s) in the vault."
    )
    for t, c, ns in tok_cols:
        state.console.print(" ", warn("note:"), f"{t}.{c}: namespace {ns}")
    state.console.print(
        " ",
        hint("hint:"),
        "reverse with: decoy detokenize",
        code(config.name),
        "<output> --vault",
        code(str(vault)),
    )


def detokenize(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The pipeline config the tokenize run used (carries each column's namespace).",
    ),
    tokenized: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="The tokenized file produced by `decoy tokenize` for one table (read by the target's declared format, else by extension).",
    ),
    vault: Path = typer.Option(
        ...,
        "--vault",
        help=(
            "The local token vault `decoy tokenize` wrote. Required: detokenize "
            "fails closed without it."
        ),
    ),
    table: str = typer.Option(
        None,
        "--table",
        help="Which config table the file belongs to. Required when the config tokenizes more than one table.",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Where to write the recovered file (format by extension). Default: <tokenized>.detokenized.parquet for Parquet input, otherwise <tokenized>.detokenized.csv, next to the input.",
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
    """Restore tokenized columns from a local vault using the pipeline config.

    Reverses every `strategy: tokenize` column by looking each token back up in
    the vault under the column's namespace. The tokenized file is read in the
    format tokenize wrote it (the table's declared target format when the file
    is that target, otherwise by extension) and the recovered file is written
    as Parquet for Parquet input, CSV otherwise. A missing or wrong vault, or a
    token the vault does not hold under that namespace, fails closed (no output is
    written). Exits 0 on success, 1 on a config/usage or fail-closed error, 3 on
    a runtime failure.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)

    def _emit_error(message: str, *, hint_text: str | None = None) -> None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "detokenize",
                    "status": "error",
                    "config": config_str,
                    "error": message,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), message, markup=False)
            if hint_text:
                state.err_console.print(" ", hint("hint:"), hint_text)

    import yaml as _yaml

    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        _emit_error(sanitize_yaml_error(exc))
        raise typer.Exit(code=EXIT_USAGE)
    if not isinstance(raw, dict):
        _emit_error(f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.")
        raise typer.Exit(code=EXIT_USAGE)

    # Same raw secret-reference guard as tokenize: a wrong-type mask_secret_ref
    # must not ride a Pydantic ValidationError (which echoes input_value) into
    # the error text.
    _raw_gs = raw.get("global_settings")
    if _raw_gs is not None and not isinstance(_raw_gs, dict):
        _emit_error(
            "global_settings must be a mapping (a YAML block of key: value "
            f"pairs), not a {type(_raw_gs).__name__}."
        )
        raise typer.Exit(code=EXIT_USAGE)
    _raw_ref = _raw_gs.get("mask_secret_ref") if isinstance(_raw_gs, dict) else None
    if _raw_ref is not None and not _is_valid_mask_secret_ref(_raw_ref):
        _emit_error(
            "Invalid global_settings.mask_secret_ref: expected an 'env:NAME' or "
            "'file:/PATH' reference to a >=32-byte secret. It is a REFERENCE, "
            "never the raw secret. See: decoy explain keys."
        )
        raise typer.Exit(code=EXIT_USAGE)

    from decoy_engine import PipelineConfig
    from decoy_engine.errors import ConfigError
    from decoy_engine.plan import PlanCompileError

    try:
        from pydantic import ValidationError as _PydanticValidationError

        config_dict = PipelineConfig.model_validate(raw).model_dump()
    except _PydanticValidationError as exc:
        _emit_error(str(exc)[:500])
        raise typer.Exit(code=EXIT_USAGE)
    except (PlanCompileError, ConfigError) as exc:
        _emit_error(f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', exc)}")
        raise typer.Exit(code=EXIT_USAGE)

    # Tables that declare at least one tokenize column -- the reversible set.
    tok_tables = [
        t.get("name")
        for t in (config_dict.get("tables") or [])
        if isinstance(t, dict)
        and t.get("name")
        and any(
            isinstance(c, dict) and c.get("strategy") == "tokenize"
            for c in (t.get("columns") or [])
        )
    ]
    if not tok_tables:
        _emit_error("no column declares `strategy: tokenize` in this config; nothing to reverse.")
        raise typer.Exit(code=EXIT_USAGE)
    if table is not None:
        if table not in tok_tables:
            _emit_error(
                f"table {table!r} has no tokenize column in this config "
                f"(tokenize tables: {', '.join(tok_tables)})."
            )
            raise typer.Exit(code=EXIT_USAGE)
        target_table = table
    elif len(tok_tables) == 1:
        target_table = tok_tables[0]
    else:
        _emit_error(
            f"config has {len(tok_tables)} tokenize tables; pass --table to pick "
            f"the one this file belongs to ({', '.join(tok_tables)}).",
            hint_text="decoy detokenize pipeline.yaml tokenized.csv --vault tokens.db --table <name>",
        )
        raise typer.Exit(code=EXIT_USAGE)

    try:
        in_format, in_layout = input_format(config_dict, target_table, tokenized, config.parent)
    except TargetFormatError as exc:
        _emit_error(f"{exc.code}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    out_path = (
        output
        if output is not None
        else tokenized.with_suffix(
            ".detokenized.parquet" if in_format == "parquet" else ".detokenized.csv"
        )
    )
    try:
        check_output_path(out_path)
    except TargetFormatError as exc:
        _emit_error(f"{exc.code}: {exc}")
        raise typer.Exit(code=EXIT_USAGE)
    # Only the DEFAULT name is guarded: it is derived, so two inputs differing
    # only in final extension (a.csv / a.tsv) or a re-run would silently clobber
    # recovered PII. An explicit --output is the operator's deliberate choice.
    if output is None and out_path.exists():
        _emit_error(
            f"detokenize_output_exists: {out_path} already exists; refusing to "
            "overwrite it. Move it aside or pass --output.",
        )
        raise typer.Exit(code=EXIT_USAGE)

    columns = list(iter_tokenize_columns(config_dict, target_table))
    missing_ns = [c for (c, ns) in columns if not ns]
    if missing_ns:
        _emit_error(
            "these tokenize columns have no `namespace:` (required to reverse): "
            f"{', '.join(missing_ns)}."
        )
        raise typer.Exit(code=EXIT_USAGE)

    import pandas as pd

    # Read the tokenized file in the format tokenize wrote it: the table's declared target
    # format when the input is that target file, the suffix rule for any other path. CSV is
    # read all-text so a token matches the vault byte-for-byte; Parquet columns are already
    # typed (tokens are strings), so no dtype coercion.
    try:
        df = read_file(tokenized, in_format, in_layout, table=target_table)
    except Exception as exc:
        # Coded + value-free: a read failure here is a wrong or corrupt file, not a
        # leakable cell value. Surface the expected format only -- never the raw
        # codec error, which a CSV/Parquet decoder can echo file bytes into.
        _emit_error(
            f"detokenize_unreadable_target: could not read {tokenized} as "
            f"{_FORMAT_NAMES[in_format]}. detokenize reads the file in the format "
            "tokenize wrote it (the target's declared format, otherwise by extension: "
            ".parquet or .pq, else CSV)."
        )
        raise typer.Exit(code=EXIT_USAGE) from exc

    # A declared tokenize column absent from the file would be left unreversed
    # while the run reports success; fail closed like a token miss instead.
    absent = [c for (c, _ns) in columns if c not in df.columns]
    if absent:
        _emit_error(
            "detokenize_column_missing: the input does not contain these configured "
            f"tokenize columns: {', '.join(absent)}; no output written. Check that "
            "the file and --table match the tokenize run."
        )
        raise typer.Exit(code=EXIT_USAGE)

    try:
        token_vault = LocalTokenVault(vault, create=False)
    except TokenVaultError as exc:
        _emit_error(f"{exc.code}: {exc.message}")
        raise typer.Exit(code=EXIT_USAGE)

    entries: list[dict] = []
    # Reverse everything first; write nothing until every requested token
    # resolves. A single miss means a wrong vault, wrong namespace, or a value
    # that was never tokenized -- fail closed rather than emit a column that is
    # part recovered, part surrogate.
    misses: list[str] = []
    recovered: dict[str, list] = {}
    try:
        for col, ns in columns:
            col_miss = 0
            reversed_count = 0
            out_values: list = []
            for value in df[col].tolist():
                if pd.isna(value):
                    out_values.append(value)  # null preserved; nothing to reverse
                    continue
                plaintext = token_vault.reverse(ns, value)
                if plaintext is None:
                    col_miss += 1
                    out_values.append(value)
                else:
                    reversed_count += 1
                    out_values.append(plaintext)
            recovered[col] = out_values
            if col_miss:
                misses.append(f"{col} ({col_miss} token(s) not in vault under namespace {ns})")
            entries.append(
                {
                    "column": col,
                    "namespace": ns,
                    "status": "reversed" if col_miss == 0 else "miss",
                    "reversed": reversed_count,
                    "misses": col_miss,
                }
            )
    finally:
        token_vault.close()

    if misses:
        _emit_error(
            "fail-closed: some tokens could not be reversed from this vault "
            f"({'; '.join(misses)}); no output written. Check that --vault and the "
            "config namespaces match the tokenize run.",
        )
        raise typer.Exit(code=EXIT_USAGE)

    for col, values in recovered.items():
        df[col] = values

    try:
        # Output format follows the output path's extension: the default matches
        # the input (Parquet in -> Parquet out), and an explicit -o picks by its
        # own suffix.
        write_private_table(df, format_for_path(out_path), out_path)
    except AtomicWriteError as exc:
        _emit_error(f"could not write the output: {describe(exc)}")
        raise typer.Exit(code=EXIT_RUNTIME) from exc
    except Exception as exc:
        # Value-free: a write failure is a path/permission problem, not a cell value.
        _emit_error(f"could not write {out_path}.")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "detokenize",
                "status": "ok",
                "config": config_str,
                "input": str(tokenized),
                "output": str(out_path),
                "table": target_table,
                "columns": entries,
            },
        )
        return
    if state.mode is OutputMode.quiet:
        return

    total_reversed = sum(e.get("reversed", 0) for e in entries)
    state.console.print(success("OK"), code(str(out_path)))
    state.console.print(f"  {len(entries)} column(s) reversed, {total_reversed} value(s).")


TOKENIZE_EPILOG = _TOKENIZE_EPILOG
DETOKENIZE_EPILOG = _DETOKENIZE_EPILOG
