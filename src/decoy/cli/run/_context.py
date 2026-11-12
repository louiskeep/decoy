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

from decoy import _native_gate, _resources
from decoy.cli.gate import GateFinding
from decoy.cli.io import RunLayout
from decoy.ui.output import OutputState

# Rows per chunk when `--chunk-size` is not given. The option has no default of its own so a
# preview can tell whether it was passed.
DEFAULT_CHUNK_SIZE = 100_000

# The machine-readable `code` of each warning the CLI raises itself. Closed: a new code is
# added here, so the `--json` `warnings` vocabulary has one list.
CLI_WARNING_CODES: frozenset[str] = frozenset({"chunked_key_check_not_run"})


class Mode(str, Enum):
    mask = "mask"
    generate = "generate"


class NotifyOn(str, Enum):
    success = "success"
    failure = "failure"
    always = "always"


@dataclass(slots=True)
class RunContext:
    """Options, then the state each phase sets for the next; see the module docstring."""

    # The 26 options of `decoy run`, as `run()` receives them.
    config: Path
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
    otel_endpoint: str
    rows: int | None
    state: OutputState
    given_as: str = "path"  # "name" when the pipeline was given as a project name

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
    # One id per command: the run folder name, the evidence `run_id` and later records share it.
    invocation_id: str = field(init=False)
    # Where this run writes; opened by `_execute` once the gate has passed.
    layout: RunLayout | None = field(init=False, default=None)
    # The one engine progress sink (`_progress.ProgressFanout`), built by `_flow`.
    progress: Any = field(init=False, default=None)

    # Temp dir holding Parquet snapshots acquired from --duckdb-source inputs;
    # created only when the flag is used, torn down in the run's finally.
    _duckdb_tmpdir: Path | None = field(init=False, default=None)

    # Sentinels for evidence manifest building (set on successful plain run).
    _ev_config_dict: dict | None = field(init=False, default=None)
    _ev_engine_version: str | None = field(init=False, default=None)
    _ev_row_counts: dict | None = field(init=False, default=None)
    _ev_timings: tuple = field(init=False, default=())
    _ev_engine_warnings: tuple = field(init=False, default=())
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
