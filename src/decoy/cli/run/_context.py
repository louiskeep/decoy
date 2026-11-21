"""The shared state of one `decoy run`, passed from phase to phase.

`run()` used to hold all of this as locals. The phases (`_prepare`, `_execute`, `_errors`,
`_render`, `_evidence`, `_flow`) now read and write the same names as fields of `RunContext`;
a field keeps the name of the local it replaced, leading underscore included. Slots make a
misspelled field raise `AttributeError` instead of quietly adding an attribute.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from decoy import _native_gate, _resources
from decoy.cli.gate import GateFinding
from decoy.cli.io import (
    DuckDBSourceError,
    LayoutError,
    OutputPlacement,
    PipelineRef,
    RunLayout,
    parse_flags,
    pipeline_label,
    resolve_path,
)
from decoy.ui.output import OutputState
from decoy.ui.theme import warn

# Rows per chunk when `--chunk-size` is not given. The option has no default of its own so a
# preview can tell whether it was passed.
DEFAULT_CHUNK_SIZE = 100_000

# The machine-readable `code` of each warning the CLI raises itself. Closed: a new code is
# added here, so the `--json` `warnings` vocabulary has one list.
CLI_WARNING_CODES: frozenset[str] = frozenset(
    {"chunked_key_check_not_run", "run_result_build_failed", "run_result_write_failed"}
)


class RunRefusal(Exception):
    """A refusal `decoy run` raises itself, before or after the engine runs.

    `_errors.refused` turns it into the run result document, the one stderr line and the exit.
    The text names flags and codes, never a value. Raise one only after any `except` block has
    closed, so it carries no `__context__` (the document never holds the cause).
    """

    category = "usage"  # the run result's failure category; the exit integer comes from the map

    def __init__(self, text: str, *, code: str | None = None) -> None:
        super().__init__(text)
        self.text = text
        self.code = code


class UsageRefusal(RunRefusal):
    """A request the CLI refuses before the run starts (exit 1): a bad `--notify`, a `--rows`
    preview that cannot run, `--fidelity` with no mask table."""


class EvidenceWriteRefusal(RunRefusal):
    """The `--evidence-out` manifest could not be written after the outputs (exit 3)."""

    category = "runtime"


class IntegrityWriteRefusal(RunRefusal):
    """The post-scan report could not be written after the outputs (exit 3)."""

    category = "runtime"


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"


class NotifyOn(str, Enum):
    success = "success"
    failure = "failure"
    always = "always"


def library_label(config: Path) -> str | Any:
    """The record label of this run (`decoy.cli.io.pipeline_label`, the resolver `library list`
    uses), or a failed `StoreOutcome` carrying the layout code: a record is lost, the run is not."""
    from decoy_engine.reasons import warning

    from decoy.cli.library import StoreOutcome

    try:
        return pipeline_label(config)
    except LayoutError as exc:
        return StoreOutcome(
            "failed", code=str(getattr(exc, "code", None) or warning.LIBRARY_WRITE_FAILED)
        )


@dataclass(slots=True)
class RunContext:
    """Options, then the state each phase sets for the next; see the module docstring."""

    # The 27 options of `decoy run`, as `run()` receives them.
    pipeline: PipelineRef | None
    all_: bool
    named: bool  # a pipeline was typed, found or not
    cli: typer.Context
    mode: Mode
    json_: bool
    quiet: bool
    verbose: bool
    master_key: str
    mask_secret: str
    chunked: bool
    chunk_size: int | None
    max_memory: str | None
    threads: str | None
    vault: Path
    key_label: str
    evidence_out: Path
    no_library: bool
    result: Path | None
    integrity_out: Path | None
    out_dir: Path | None
    notify: list[str]
    notify_on: NotifyOn
    native: bool
    no_native: bool
    explain_plan: bool
    fidelity: bool
    post_validate: bool
    post_validate_enforce: bool
    duckdb_source: list[str]
    no_subset: bool
    otel_endpoint: str
    rows: int | None
    sample: int | None
    sample_root: str | None
    state: OutputState

    # Set by `_flow.execute` from `pipeline`, or from the project's only pipeline.
    config: Path = field(init=False)
    given_as: str = field(init=False, default="path")  # "name" for a project name

    # Set before the try block.
    config_str: str = field(init=False)
    notify_channels: list = field(init=False)
    raw: object = field(init=False)
    saved_findings: list[GateFinding] = field(init=False)
    config_read_error: Exception | None = field(init=False)
    raw_cfg: dict | None = field(init=False)
    yaml_mode: str = field(init=False)
    resolver: Any = field(init=False)
    # S5 report flags. `post_validation` is on when EITHER post-validate flag
    # is set (--post-validate-enforce implies --post-validate); it feeds the
    # engine kwarg. `_report_flags` gates the --chunked rejection below. The
    # non-chunked branch stamps `_report_quality_metrics` so the tail can
    # render the requested sections and apply the enforce -> EXIT_FINDINGS map.
    post_validation: bool = field(init=False)
    _report_flags: bool = field(init=False)
    _run_started_at: datetime = field(init=False)
    started: float = field(init=False)
    # True from the moment `_execute.execute` hands the pipeline to the engine. A failure before
    # it is a refusal (nothing ran); one after it is a run that failed, whatever its category.
    execution_started: bool = field(init=False, default=False)
    # One id per command: the run folder name, the evidence `run_id` and later records share it.
    invocation_id: str = field(init=False)
    # Where this run writes; opened by `_execute` once the gate has passed.
    layout: RunLayout | None = field(init=False, default=None)
    # The one engine progress sink (`_progress.ProgressFanout`), built by `_flow`.
    progress: Any = field(init=False, default=None)
    # SHA-256 of the YAML bytes read; the post-scan report and its file (`cli/io`, SCAN-ML C2a).
    config_sha256: str | None = field(init=False, default=None)
    _post_scan: dict | None = field(init=False, default=None)
    _post_scan_file: Path | None = field(init=False, default=None)
    # The run-result collector riding on that sink, and the engine's `ExecutionResult` of the plain
    # branch; the one result builder (`_result`) reads both.
    _collector: Any = field(init=False, default=None)
    _execution: Any = field(init=False, default=None)

    # `--sample`: the project found for the pipeline, the library holding its scratch, and the
    # private scratch folder every sample output lands in (`_sample`).
    _sample_project: Any = field(init=False, default=None)
    _library: Any = field(init=False, default=None)
    _scratch: Path | None = field(init=False, default=None)

    # Temp dir holding Parquet snapshots acquired from --duckdb-source inputs;
    # created only when the flag is used, torn down in the run's finally.
    _duckdb_tmpdir: Path | None = field(init=False, default=None)

    # Sentinels for evidence manifest building (set on successful plain run).
    _ev_config_dict: dict | None = field(init=False, default=None)
    _ev_engine_version: str | None = field(init=False, default=None)
    _ev_row_counts: dict | None = field(init=False, default=None)
    _ev_timings: tuple = field(init=False, default=())
    _ev_engine_warnings: tuple = field(init=False, default=())
    # The library's `StoreOutcome` for this run's evidence record; None until stored or skipped.
    library_outcome: Any = field(init=False, default=None)
    # The library root this run resolved, once (`library_choice`); None until first asked.
    _library: Any = field(init=False, default=None)
    # Row count for the --notify event; unconditional (unlike _ev_row_counts,
    # which only fills for --evidence-out). None for --chunked runs (no
    # ExecutionResult to count).
    _notify_row_count: int | None = field(init=False, default=None)
    # The publication ledger: table to the file a writer has finished publishing. `--json`
    # `outputs` and `output_dir` come only from it.
    _published: dict[str, Path] = field(init=False, default_factory=dict)
    # Per-table {name, rows, path} for the summary; rows is None on a chunked run.
    _table_records: list[dict] = field(init=False, default_factory=list)
    # Native route classification (Phase 3.1), set on a successful run for
    # the run-summary line and JSON record.
    _native_route: _native_gate.RouteClassification | None = field(init=False, default=None)
    _resources_record: dict | None = field(init=False, default=None)
    # Warnings the CLI raises itself (`code`, `message`); they join the engine's in the summary.
    _cli_warnings: list[dict] = field(init=False, default_factory=list)
    _report_quality_metrics: dict | None = field(init=False, default=None)
    # The engine's `quality_metrics["subset"]` block: counts and fingerprint when the config's
    # `subset:` was applied, `{"applied": False}` under `--no-subset`, None when it has none.
    _subset_metrics: dict | None = field(init=False, default=None)
    # `--rows` preview: the sampled tables, set by `_execute.execute_preview`.
    _preview_tables: list[dict] = field(init=False, default_factory=list)

    # Set by `_prepare.prepare`, read by `_execute.execute`. `engine_version` is bound where the
    # lazy engine import runs, not at construction.
    config_dict: dict = field(init=False)
    gate_result: _native_gate.PreGateResult = field(init=False)
    any_generate: bool = field(init=False)
    native_intent: _native_gate.NativeIntent = field(init=False)
    _res: _resources.Resolved = field(init=False)
    sources: dict = field(init=False)
    key_provider: Any = field(init=False)
    vault_writer: Any = field(init=False)
    engine_version: str = field(init=False)

    # Set by the success tail.
    elapsed: float = field(init=False)
    notify_results: list[dict] = field(init=False)

    def add_cli_warning(self, code: str, message: str) -> None:
        """Record a CLI warning for the run summary, the only place it is printed."""
        if code not in CLI_WARNING_CODES:
            raise ValueError(f"unknown CLI warning code: {code!r}")
        self._cli_warnings.append({"code": code, "message": message})

    def published_members(self) -> dict:
        """The `--json` `outputs` and `output_dir` members (plan 3.6.1 C), from the publication
        ledger only: an opened folder is not evidence that a file exists.

        Nothing published gives no member. `output_dir` appears only when a listed file is
        below the run folder or `--out-dir`; absolute paths are listed without it.
        """
        if not self._published:
            return {}
        files = [Path(path).resolve() for path in self._published.values()]
        members: dict = {
            "outputs": [{"table": t, "path": str(f)} for t, f in zip(self._published, files)]
        }
        folder = self.layout.output_dir() if self.layout is not None else None
        if folder is not None and any(folder in f.parents for f in files):
            members["output_dir"] = str(folder)
        return members


def output_placement(ctx: RunContext) -> OutputPlacement:
    """Where this run's relative outputs land, for the gate: the typed `--out-dir`, else the
    project run folder; the typed side files join the collision rule either way."""
    typed = tuple(
        (flag, path)
        for flag, path in (
            ("--evidence-out", ctx.evidence_out),
            ("--integrity-out", ctx.integrity_out),
            ("--vault", ctx.vault),
            ("--result", ctx.result),
        )
        if path is not None
    )
    # Each well-formed entry is protected even when another is malformed: the refusal for the bad
    # spelling still writes a result document, and it must not land on a good database.
    databases: list[Path] = []
    for value in ctx.duckdb_source:
        try:
            (flag,) = parse_flags([value])
        except DuckDBSourceError:
            continue
        databases.append(resolve_path(flag.db_path, ctx.config.parent))
    library = library_choice(ctx).root
    if ctx.out_dir is not None:
        return OutputPlacement.fixed(ctx.out_dir, typed, ctx.chunked, tuple(databases), library)
    return OutputPlacement(
        typed=typed, chunked=ctx.chunked, inputs=tuple(databases), library=library
    )


@dataclass(frozen=True)
class LibraryChoice:
    """Where this run's records go: `root` is the resolved library root, or None when records
    are off or the project finder refused (the gate reports that). `code` is set when the root
    could not be resolved: the run delivers, stores nothing and warns once."""

    root: Path | None = None
    code: str | None = None


def library_choice(ctx: RunContext) -> LibraryChoice:
    """The library root of this run, resolved once and kept on the context.

    The gate, the evidence store and the result store all read this one answer, so a root the
    gate did not check is never written. A root that cannot be resolved (`library_path_unsafe`)
    is warned about here, once, and recorded as the run's failed library outcome; the run's exit
    code is its own (plan 4.17).
    """
    if ctx._library is None:
        ctx._library = _resolve_library(ctx)
    return ctx._library


def _resolve_library(ctx: RunContext) -> LibraryChoice:
    if ctx.no_library or ctx.rows is not None:
        return LibraryChoice()
    from decoy.cli.library import LibraryError, StoreOutcome, resolve_root

    try:
        found = resolve_root(pipeline=Path(ctx.config))
    except LayoutError:
        return LibraryChoice()
    except LibraryError as exc:
        ctx.library_outcome = StoreOutcome("failed", code=exc.code)
        # Not gated on --quiet: a warning about a lost record is not chatter.
        ctx.state.err_console.print(
            warn("warning:"),
            f"{exc.code}: the run's records were not stored in the library",
            markup=False,
        )
        return LibraryChoice(code=exc.code)
    return LibraryChoice(root=found.path) if found.records else LibraryChoice()
