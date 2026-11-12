"""Pre-run checks and admission for `decoy run`: everything from the config read to the
vault writer, before any row is masked."""

import binascii
import contextlib
from pathlib import Path

import typer
from rich.text import Text

from decoy import _mask_secret, _mask_secret_guidance, _native_gate, _resources
from decoy.cli import gen
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.gate import (
    GateFinding,
    GateRoute,
    PreRunCheckError,
    check_before_run,
    parse_pipeline_yaml,
)
from decoy.cli.io import DuckDBSourceError, OutputPlacement, acquire_relation, parse_flag
from decoy.cli.io import resolve_path as _resolve_path
from decoy.cli.run._context import RunContext
from decoy.cli.run._execute import (
    _check_chunked_tables,
    _ChunkedFixedWidthError,
    _ChunkedGenerateError,
    _ChunkedReportFlagError,
    _load_sources_from_config,
    _note_chunked_key_check_skipped,
    _require_local_io_endpoints,
)
from decoy.cli.run._vault import _CHUNKED_VAULT_MESSAGE, _ChunkedVaultError, _VaultUsageError
from decoy.ui.output import OutputMode, emit_json
from decoy.ui.theme import error, hint, warn


class _MaskSecretUsageError(Exception):
    """--mask-secret AND YAML mask_secret_ref both set; user error (exits EXIT_USAGE)."""


# The raw pre-check (before Pydantic) and the effective-ref guard share the one
# predicate in `decoy._mask_secret`; callers never echo the value.
_is_valid_mask_secret_ref = _mask_secret.is_valid_mask_secret_ref


def _load_raw_config(
    config_path: Path,
) -> tuple[object, list[GateFinding], Exception | None]:
    """The run path's single YAML parse, through the gate's parser.

    Returns `(raw, findings, read_error)`: `findings` holds a YAML syntax error (the run
    refuses it before any work), `read_error` an unreadable or non-UTF-8 file (kept as
    today: it surfaces through the run-level handler as a runtime error).
    """
    try:
        raw, findings = parse_pipeline_yaml(config_path)
    except (OSError, UnicodeDecodeError) as exc:
        return None, [], exc
    return raw, findings, None


def _build_resolver(master_key_hex: str | None, key_label: str | None, raw_cfg: dict | None, state):
    """Construct the engine-facing ``derive_key`` resolver, or None when no
    master key was supplied. Keeps the legacy seeded fallback default so
    runs without a key behave exactly as before.

    ``raw_cfg`` is accepted (and unused) for call-site symmetry with the
    other pre-flight helpers that share the one parsed YAML dict; it used
    to feed a top-level YAML ``key_label:`` reader. This function runs
    early (the run() body calls it ~L307), BEFORE ``PipelineConfig
    .model_validate`` (~L371), so that reader could observe a top-level
    ``key_label:`` value -- but model_validate then runs on the same raw
    dict and PipelineConfig's ``extra="forbid"`` rejects the unknown field,
    so a config carrying it could never reach a successful run regardless
    of what the reader returned. The reader was therefore dead and
    misleading; it is removed. ``--key-label`` is the only live source
    (doc/config mismatch fix, see `decoy explain keys`).
    """
    if not master_key_hex:
        return None

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
        raise typer.BadParameter(f"--master-key must decode to 32 bytes (got {len(master)}).")

    if not key_label:
        raise typer.BadParameter(
            "--master-key requires a --key-label. Pick a stable namespace "
            "string like 'customers_q4'."
        )

    from decoy_engine import make_key_resolver

    return make_key_resolver(master, key_label)


def _detect_mode(raw_cfg: dict | None) -> str | None:
    """Infer mode from the YAML's tables, or return None if not determinable.

    FC-1 (2026-06-02) dropped the top-level `mode:` field; the engine now
    infers per-table kind from `columns` (mask) vs `generate_columns`
    (generate) presence. This helper picks one label for the spinner / the
    JSON envelope's `mode` field: returns "generate" iff EVERY table is
    generate-kind; "mask" iff at least one mask-kind table is present
    (mixed configs label as "mask" because the mask back-half is the
    workflow that touches the operator's source data). The choke-point
    validator still rejects malformed configs.
    """
    if not isinstance(raw_cfg, dict):
        return None
    tables = raw_cfg.get("tables") or []
    if not isinstance(tables, list):
        return None
    has_mask = any(isinstance(t, dict) and t.get("columns") for t in tables)
    has_gen = any(isinstance(t, dict) and t.get("generate_columns") for t in tables)
    if has_mask:
        return "mask"
    if has_gen:
        return "generate"
    return None


def _has_kind(raw_cfg: dict | None, field: str) -> bool:
    """Whether any table of the raw config declares `field` (`columns` is a mask table,
    `generate_columns` a generate table)."""
    tables = raw_cfg.get("tables") if isinstance(raw_cfg, dict) else None
    if not isinstance(tables, list):
        return False
    # A mask table is declared by the `columns` key even when the list is empty; a generate
    # table needs at least one `generate_columns` entry.
    if field == "columns":
        return any(isinstance(t, dict) and field in t for t in tables)
    return any(isinstance(t, dict) and t.get(field) for t in tables)


_FIDELITY_NEEDS_MASK = (
    "--fidelity scores mask tables and this pipeline has none. Score generated tables with: "
    "decoy report fidelity <source.csv> <synthetic.csv> --generate"
)


def _refuse_usage(state, config_str: str, text: str) -> None:
    """Print a usage refusal in the active output mode and exit 1, before any engine call."""
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {"command": "run", "status": "error", "config": config_str, "error": text},
        )
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), text, markup=False)
    raise typer.Exit(code=EXIT_USAGE)


def _refuse_fidelity_without_mask(state, config_str: str, raw_cfg: dict) -> None:
    """Exit 1 before any engine call when `--fidelity` is given and no table is a mask table.

    A config with no tables at all is left to the normal config check.
    """
    if not raw_cfg.get("tables"):
        return
    _refuse_usage(state, config_str, _FIDELITY_NEEDS_MASK)


def refuse_preview(ctx: RunContext) -> None:
    """Exit 1 before any engine call when `--rows` cannot run: a bad size, a flag that writes
    or reports, or a mask table. Names flags only."""
    assert ctx.rows is not None
    flags = [
        name
        for name, given in (
            ("--chunked", ctx.chunked),
            ("--chunk-size", ctx.chunk_size is not None),
            ("--evidence-out", ctx.evidence_out is not None),
            ("--notify", bool(ctx.notify)),
            ("--vault", ctx.vault is not None),
            ("--fidelity", ctx.fidelity),
            ("--explain-plan", ctx.explain_plan),
            ("--post-validate", ctx.post_validate),
            ("--post-validate-enforce", ctx.post_validate_enforce),
            ("--native", ctx.native),
            ("--duckdb-source", bool(ctx.duckdb_source)),
            ("--out-dir", ctx.out_dir is not None),
        )
        if given
    ]
    text = gen.refusal(ctx.rows, flags, _has_kind(ctx.raw_cfg, "columns"))
    if text is not None:
        _refuse_usage(ctx.state, ctx.config_str, text)


def _guard_mask_secret_ref(raw: object) -> None:
    """DE-02 secret-disclosure ROOT guard: validate the RAW YAML `mask_secret_ref` BEFORE
    PipelineConfig.model_validate(raw). A wrong-type value would raise a Pydantic
    ValidationError echoing `input_value` (the secret) as exit 3. A redacted usage error here
    keeps the value out of Pydantic's diagnostics. YAML-only: the --mask-secret flag is always
    a str from Typer.
    """
    _raw_gs = raw.get("global_settings") if isinstance(raw, dict) else None
    # A non-dict `global_settings` (e.g. a YAML list) is malformed AND
    # could smuggle a mask_secret_ref value nested where the dict-path
    # check below can't see it -- Pydantic would then echo that value in
    # its ValidationError. Reject a present-but-non-mapping
    # global_settings here, with a redacted message, before
    # model_validate ever sees the raw structure.
    if _raw_gs is not None and not isinstance(_raw_gs, dict):
        raise _MaskSecretUsageError(
            "global_settings must be a mapping (a YAML block of "
            f"key: value pairs), not a {type(_raw_gs).__name__}. "
            "See: decoy explain keys."
        )
    _raw_ref = _raw_gs.get("mask_secret_ref") if isinstance(_raw_gs, dict) else None
    if _raw_ref is not None and not _is_valid_mask_secret_ref(_raw_ref):
        raise _MaskSecretUsageError(
            "Invalid global_settings.mask_secret_ref: expected an "
            "'env:NAME' or 'file:/PATH' reference to a >=32-byte secret. "
            "It is a REFERENCE, never the raw secret. "
            "See: decoy explain keys."
        )


def _placement(ctx: RunContext) -> OutputPlacement:
    """Where this run's relative outputs land, for the gate: the typed `--out-dir`, else the
    project run folder; the typed side files join the collision rule either way."""
    typed = tuple(
        (flag, path)
        for flag, path in (("--evidence-out", ctx.evidence_out), ("--vault", ctx.vault))
        if path is not None
    )
    if ctx.out_dir is not None:
        return OutputPlacement.fixed(ctx.out_dir, typed)
    return OutputPlacement(typed=typed)


def prepare_preview(ctx: RunContext) -> None:
    """The `--rows` counterpart of `prepare`: the config guards and the gate on the scaled
    config. No source is read and no vault or key provider is opened, because a preview has
    no mask table."""
    from decoy_engine import __version__ as engine_version

    assert ctx.rows is not None
    ctx.engine_version = engine_version
    if ctx.config_read_error is not None:
        raise ctx.config_read_error
    if ctx.saved_findings:
        raise PreRunCheckError.from_findings(ctx.saved_findings)
    _guard_mask_secret_ref(ctx.raw)
    ctx.config_dict = check_before_run(
        gen.scale_row_counts(ctx.raw, ctx.rows),
        ctx.config,
        GateRoute.PLAIN,
        ctx.state,
        OutputPlacement.preview(),
    )
    ctx.any_generate = True
    ctx._res = _resources.resolve(max_memory=ctx.max_memory, threads=ctx.threads)


def prepare(ctx: RunContext, _scopes: contextlib.ExitStack) -> None:
    """Everything between the config read and the first row: the engine import, the config
    guards, `--duckdb-source` staging, the gate, admission and the source load."""
    from decoy_engine import (
        __version__ as engine_version,
    )
    from decoy_engine import run_pipeline  # noqa: F401  (import kept at its original point)

    ctx.engine_version = engine_version

    if ctx.config_read_error is not None:
        raise ctx.config_read_error
    if ctx.saved_findings:
        raise PreRunCheckError.from_findings(ctx.saved_findings)

    _guard_mask_secret_ref(ctx.raw)

    # DuckDB-in sources: acquire each flagged relation read-only to a
    # temp Parquet and rewrite the in-memory source to that Parquet
    # BEFORE schema validation, so the engine only ever sees a plain
    # parquet file source (its SourceDescriptor has no duckdb variant).
    # Mirrors the engine's snapshot-to-Parquet DB-input pattern
    # (connectors.postgres_snapshot): DuckDB owns the read, masking runs
    # over the staged Parquet unchanged.
    if ctx.duckdb_source:
        if ctx.evidence_out is not None:
            raise DuckDBSourceError(
                "--duckdb-source is not supported with --evidence-out yet "
                "(the manifest's input fingerprint for a transient snapshot "
                "is unspecified); run them separately."
            )
        if not isinstance(ctx.raw, dict):
            raise DuckDBSourceError("--duckdb-source needs a mapping pipeline config")
        _raw_sources = ctx.raw.get("sources")
        if _raw_sources is None:
            _raw_sources = ctx.raw["sources"] = {}
        elif not isinstance(_raw_sources, dict):
            raise DuckDBSourceError("pipeline `sources:` must be a mapping to use --duckdb-source")
        # Build the declared-table set defensively: a malformed `tables:`
        # (not a list, or non-string names) must NOT crash here with a
        # TypeError. When it is malformed, skip the flag's membership check
        # and let PipelineConfig validation report the bad shape normally.
        _raw_tables = ctx.raw.get("tables")
        _tables_wellformed = isinstance(_raw_tables, list)
        _declared = {
            t["name"]
            for t in (_raw_tables if _tables_wellformed else [])
            if isinstance(t, dict) and isinstance(t.get("name"), str)
        }
        import tempfile

        ctx._duckdb_tmpdir = Path(tempfile.mkdtemp(prefix="decoy-duckdb-"))
        for _spec in ctx.duckdb_source:
            _tbl, _db = parse_flag(_spec)
            if _tables_wellformed and _tbl not in _declared:
                raise DuckDBSourceError(
                    f"--duckdb-source: {_tbl!r} is not a table in the pipeline "
                    f"`tables:` ({sorted(n for n in _declared if n)})"
                )
            _parquet = acquire_relation(
                _resolve_path(_db, ctx.config.parent), _tbl, ctx._duckdb_tmpdir
            )
            _raw_sources[_tbl] = {
                "type": "file",
                "format": "parquet",
                "path": str(_parquet),
            }

    # The whole `decoy validate` gate (config, compile, preflight) before any source
    # row is read. A refusal raises into the one handler below; a pass hands back the
    # validated config, so the run validates once. The DE-02 guard above keeps a
    # mask_secret_ref value out of every schema diagnostic.
    ctx.config_dict = check_before_run(
        ctx.raw,
        ctx.config,
        GateRoute.CHUNKED if ctx.chunked else GateRoute.PLAIN,
        ctx.state,
        _placement(ctx),
    )

    # Cloud (s3/gcs) sources/targets are refused inside the shared
    # I/O helpers below (_load_sources_from_config /
    # _run_chunked_mask / _write_mask_outputs, via
    # _require_local_io_endpoints), not here, so `decoy.mask()` --
    # which calls the same helpers -- gets the identical refusal.

    # --mask-secret fills the same `global_settings.mask_secret_ref` slot the
    # YAML can set; one source per run, presence-keyed, never echoed (the
    # flag has no env var, so None means "flag absent").
    _mask_secret.apply_mask_secret(ctx.config_dict, ctx.mask_secret, error=_MaskSecretUsageError)
    if (ctx.config_dict.get("global_settings") or {}).get("mask_secret_ref") is not None:
        # A mask_secret_ref is only honored by a DE-02 engine; a
        # pre-DE-02 engine has no `keyprovider` module and would
        # SILENTLY IGNORE the ref, emitting job-seed-keyed output
        # (fail-open). The pyproject floor (decoy-engine>=0.4.0, DE-02's
        # release marker) is the first line of defense; this runtime
        # probe is defense-in-depth against a broken or forced install
        # that satisfies the resolver but lacks keyprovider -- refuse
        # the run rather than leak an unkeyed artifact.
        try:
            import decoy_engine.keyprovider  # noqa: F401
        except ImportError as exc:
            raise _MaskSecretUsageError(_mask_secret_guidance.OLD_ENGINE_RUN) from exc

    ctx._ev_config_dict = ctx.config_dict
    ctx._ev_engine_version = ctx.engine_version

    # FC-1 (2026-06-26): run_pipeline is now wired as the single
    # non-chunked entry for all config shapes (mask-only, generate-
    # only, and mixed). The engine handles profiling, planning, the
    # FK graph, and sequencing (generate first, then mask with
    # generate outputs merged into sources). The old split between
    # `generate_tables` and `PandasExecutionAdapter.run` is removed.
    ctx.any_generate = _has_kind(ctx.config_dict, "generate_columns")

    # Chunked mask streaming is mask-only. Reject loudly when the
    # config has any generate-kind table so the operator gets a clear
    # message instead of silently skipping those tables.
    if ctx.chunked and ctx.any_generate:
        raise _ChunkedGenerateError(
            "--chunked is only supported for mask-only configs; "
            "this config includes generate tables (generate_columns:). "
            "Run without --chunked to execute a mixed or generate pipeline."
        )

    # S5 (P2-3): the report flags read fields of the non-chunked
    # run_pipeline's ExecutionResult.quality_metrics; the chunked path
    # returns no ExecutionResult, so the flags have nothing to render.
    # Reject the combination up front rather than silently no-op.
    if ctx.chunked and ctx._report_flags:
        _requested = [
            name
            for name, on in (
                ("--explain-plan", ctx.explain_plan),
                ("--fidelity", ctx.fidelity),
                ("--post-validate", ctx.post_validate),
                ("--post-validate-enforce", ctx.post_validate_enforce),
            )
            if on
        ]
        raise _ChunkedReportFlagError(
            f"--chunked cannot be combined with {', '.join(_requested)}: "
            "the report flags surface fields of the non-chunked run's "
            "ExecutionResult, which the streaming --chunked path does not "
            "produce. Run without --chunked to use these flags."
        )
    if ctx.chunked and ctx.vault is not None:
        raise _ChunkedVaultError(_CHUNKED_VAULT_MESSAGE)

    # The engine has no bounded fixed-width iterator, so a chunked
    # run cannot stream one. Refuse before any table is written
    # rather than part-way through a multi-table config.
    if ctx.chunked:
        _fw_tables = sorted(
            str(_n)
            for _n, _s in (ctx.config_dict.get("sources") or {}).items()
            if isinstance(_s, dict) and _s.get("format") == "fixed_width"
        )
        if _fw_tables:
            raise _ChunkedFixedWidthError(
                "--chunked cannot read format: fixed_width sources "
                f"({', '.join(_fw_tables)}); the engine has no streaming "
                "fixed-width reader. Run without --chunked."
            )

    # A cheap, no-secret-access check: whether --vault was passed
    # AND at least one column declares it. Computed before
    # constructing the real vault writer (which resolves key
    # material) so the flag-conflict and native-gate usage checks
    # below run first -- a usage error should never wait on a
    # secret-reading side effect.
    vault_columns_declared = False
    if ctx.vault is not None:
        from decoy_engine.vault import iter_vault_columns

        vault_columns_declared = bool(iter_vault_columns(ctx.config_dict))
        if not vault_columns_declared:
            raise _VaultUsageError(
                "--vault was passed but no column declares vault: true "
                "in this config. Add `vault: true` to the columns whose "
                "source values the vault should record."
            )

    # Phase 3.1: resolve --native/--no-native intent and run the
    # shared pre-execution gate (approach 2 Stage 0/1, plus the
    # broken-companion classification of approach 3) BEFORE any
    # dispatch. `vault_active` must be known here (not just visible
    # in the config's `vault: true` columns): admission declines
    # ANY job with a live vault writer regardless of column markers,
    # so the fail-closed scoping needs the real runtime state, not a
    # config-shape proxy. Using `vault_columns_declared` here (not
    # the constructed writer) is equivalent for this decision --
    # `--vault` always fails closed above unless a vault column
    # exists, so "the flag was given and validated" already implies
    # "a writer will exist" -- without paying for key resolution
    # before the gate has had its say.
    if ctx.native and ctx.no_native:
        raise _native_gate.NativeGateError(
            "--native and --no-native are mutually exclusive.",
            code="native_flag_conflict",
        )
    ctx.native_intent = "require" if ctx.native else "disable" if ctx.no_native else "default"
    ctx.gate_result = _native_gate.pre_execution_gate(
        intent=ctx.native_intent,
        chunked=ctx.chunked,
        any_generate=ctx.any_generate,
        config_dict=ctx.config_dict,
        vault_active=ctx.vault is not None and vault_columns_declared,
    )
    if ctx.gate_result.info_message and ctx.state.mode is not OutputMode.quiet:
        # Wrapped in Text(): a gate message is free text (e.g. a
        # remediation hint), which Rich's default string markup
        # parsing could otherwise reinterpret.
        ctx.state.err_console.print(hint("native:"), Text(ctx.gate_result.info_message))
    if ctx.gate_result.warn_message and ctx.state.mode is not OutputMode.quiet:
        ctx.state.err_console.print(warn("warning:"), Text(ctx.gate_result.warn_message))

    # Usage and source refusals come before the secret read, in the order the engine
    # used when it admitted inside each entry.
    _require_local_io_endpoints(ctx.config_dict)
    ctx._res = _resources.resolve(max_memory=ctx.max_memory, threads=ctx.threads)
    ctx._resources_record = ctx._res.record()
    if ctx.chunked:
        _check_chunked_tables(ctx.config_dict)
        _note_chunked_key_check_skipped(ctx)
    else:
        ctx.sources = _load_sources_from_config(ctx.config_dict, ctx.config.parent)
    # One admission per run: the vault writer and every engine entry get this
    # provider, so the secret is read once and output and vault share one key.
    ctx.key_provider = _scopes.enter_context(_mask_secret.admitted_key_provider(ctx.config_dict))
    # None is the engine default; omitting it keeps run_pipeline's call shape for
    # an unkeyed config.
    _key_kwargs = {} if ctx.key_provider is None else {"key_provider": ctx.key_provider}
    ctx.vault_writer = None
    if ctx.vault is not None:
        from decoy_engine import vault_writer_for_config

        ctx.vault_writer = vault_writer_for_config(ctx.config_dict, **_key_kwargs)
