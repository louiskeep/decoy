"""`decoy preflight` -- local file, source, and schema readiness checks (SP-17).

`preflight` helps catch common problems BEFORE running a pipeline. It performs
local checks that do not require the engine to execute the full pipeline.

What preflight checks (honest framing)
----------------------------------------
1. YAML syntax:        Is the pipeline file a valid YAML document?
2. Schema:             Does the config satisfy the PipelineConfig schema?
3. Config logic:       Profile-free plan-compile checks (same as `decoy validate`).
4. File existence:     Does each declared source file exist on disk?
5. File readability:   Can each source file be opened for reading?
6. Target overwrite:   Does any output target already exist (advisory)?
7. Capacity (v1):      Would the engine's out-of-core-FK memory gate refuse this
                       job? Covers the out-of-core-FK route ONLY -- see the OOM
                       checker v1 note below.

What preflight does NOT check
------------------------------
* Platform preflight conditions (the platform's server-side pre-run checks
  include secrets, RBAC, schedule validity, and network targets -- none of
  those are local CLI checks).
* Data validity or masking quality.
* Engine run-time constraints beyond the out-of-core-FK capacity check above
  (provider capacity, null-bearing integer distributions) -- these require a
  profile pass during the run.
* Vault or secrets accessibility.
* Network connectivity.
* Whether the engine can successfully execute the pipeline.

OOM checker v1 (docs/plans/2026-07-24-oom-checker-cli-v1.md): the capacity
check is an "OOC-FK engine-gate capacity checker", NOT a whole-job OOM
guarantee. `decoy run` fully loads every source into memory BEFORE it calls
the engine, so an ingestion `MemoryError` or OS OOM-kill happens before this
gate ever runs -- this check does not cover that, and does not cover the
generate path. A "capacity: OK" here means one specific thing: the
out-of-core-FK route's estimated resident floor is within budget.

Do NOT describe the output of this command as "platform parity." Preflight
here is a local file/source/schema readiness gate. The spec (cli-first-
capability-guide.md lines 99-100) is explicit: frame this as FILE / SOURCE /
SCHEMA checks. Platform preflight is a different product.

The same engine primitives (PipelineConfig.model_validate,
run_config_only_checks) are used for steps 1-3; this keeps both commands
in sync on what "structurally valid" means without literally reusing the
validate command's code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
import yaml as _yaml

from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success, warn

_PREFLIGHT_EPILOG = """\
Examples:

  decoy preflight pipeline.yaml
    Run local readiness checks: YAML validity, schema, and source file existence.

  decoy preflight pipeline.yaml --local
    Same as above (--local is the explicit form; all checks are local by default).

  decoy preflight pipeline.yaml --json
    Emit a structured JSON result with per-check findings.

  decoy preflight pipeline.yaml --fail-on-warning
    Exit non-zero when advisory warnings fire (e.g. output already exists).

What preflight checks:
  - YAML syntax and schema (same as `decoy validate`)
  - Source file existence and readability
  - Target overwrite risk (advisory warning)
  - Out-of-core-FK memory capacity (v1; exits EXIT_CAPACITY if insufficient --
    see: decoy explain exit-codes)

What preflight does NOT check:
  - Platform server-side conditions (secrets, RBAC, schedules, network targets)
  - Engine run-time constraints beyond out-of-core-FK capacity (row counts,
    provider limits)
  - The ingestion peak `decoy run` pays before the engine's capacity gate runs,
    or the generate path (both out of the v1 capacity check's scope)
  - Data validity or masking quality
  - Vault or secrets accessibility

See also: decoy validate, decoy run, decoy evidence verify, decoy explain exit-codes.
"""

_WARN_EXIT = 2


# ---------------------------------------------------------------------------
# Check accumulator (reused from validate)
# ---------------------------------------------------------------------------


@dataclass
class _CheckResult:
    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str
    location: str | None = None
    # OOM checker v1: the engine's capacity-refusal code (one of
    # out_of_core_insufficient_memory / out_of_core_fanin_exceeds_budget),
    # carried as its own field so a --json caller can assert on it directly
    # instead of parsing `message` text (R9).
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "message": self.message,
        }
        if self.location is not None:
            d["location"] = self.location
        if self.code is not None:
            d["code"] = self.code
        return d


@dataclass
class _PreflightAccumulator:
    checks: list[_CheckResult] = field(default_factory=list)
    # OOM checker v1 (T7): an INSUFFICIENT capacity verdict must exit
    # EXIT_CAPACITY, not fold into the generic has_failures -> EXIT_USAGE
    # path -- tracked separately from `checks` status so the two exit
    # reasons can never be confused with each other.
    capacity_insufficient: bool = False

    def add_pass(
        self, name: str, message: str, location: str | None = None, code: str | None = None
    ) -> None:
        self.checks.append(
            _CheckResult(name=name, status="pass", message=message, location=location, code=code)
        )

    def add_warn(
        self, name: str, message: str, location: str | None = None, code: str | None = None
    ) -> None:
        self.checks.append(
            _CheckResult(name=name, status="warn", message=message, location=location, code=code)
        )

    def add_fail(
        self, name: str, message: str, location: str | None = None, code: str | None = None
    ) -> None:
        self.checks.append(
            _CheckResult(name=name, status="fail", message=message, location=location, code=code)
        )

    @property
    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.checks]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_source_files(raw: dict[str, Any], acc: _PreflightAccumulator) -> None:
    """Check that every declared source file exists and is readable.

    File checks only. Parser config, column layout, and format inference are
    NOT checked here (those are engine-level concerns that require a profile
    pass). This check is about the files themselves, not their contents.
    """
    sources = raw.get("sources") or {}
    if not isinstance(sources, dict):
        return

    for table_name, src in sources.items():
        if not isinstance(src, dict):
            continue

        src_type = src.get("type") or "file"
        if src_type != "file":
            # Only file sources have a local path to check.
            # Non-file sources (database, API) are not checkable here.
            acc.add_pass(
                name=f"source.{table_name}.type",
                message=f"Source {table_name!r}: non-file type {src_type!r}; skipping local file check.",
                location=f"sources.{table_name}.type",
            )
            continue

        src_path_str = src.get("path")
        if not src_path_str:
            acc.add_fail(
                name=f"source.{table_name}.path",
                message=f"Source {table_name!r}: no 'path' declared.",
                location=f"sources.{table_name}.path",
            )
            continue

        src_path = Path(src_path_str)
        if not src_path.exists():
            acc.add_fail(
                name=f"source.{table_name}.exists",
                message=f"Source file not found: {src_path_str}",
                location=f"sources.{table_name}.path",
            )
            continue

        if not src_path.is_file():
            acc.add_fail(
                name=f"source.{table_name}.is_file",
                message=f"Source path is not a regular file: {src_path_str}",
                location=f"sources.{table_name}.path",
            )
            continue

        # Readability check (open for reading, read 0 bytes).
        try:
            with src_path.open("rb") as fh:
                fh.read(0)
        except OSError as exc:
            acc.add_fail(
                name=f"source.{table_name}.readable",
                message=f"Source file not readable: {src_path_str}: {exc}",
                location=f"sources.{table_name}.path",
            )
            continue

        acc.add_pass(
            name=f"source.{table_name}.exists",
            message=f"Source file exists and is readable: {src_path_str}",
            location=f"sources.{table_name}.path",
        )


def _check_target_overwrite(raw: dict[str, Any], acc: _PreflightAccumulator) -> None:
    """Advisory: warn when an output target file already exists.

    This is a warning, not a failure. The run succeeds by overwriting,
    but this check surfaces the risk in CI so it can be treated as blocking
    with --fail-on-warning.
    """
    targets = raw.get("targets") or {}
    if not isinstance(targets, dict):
        return

    for table_name, target in targets.items():
        if not isinstance(target, dict):
            continue
        if target.get("type") not in ("file", None):
            continue
        out_path_str = target.get("path")
        if not out_path_str:
            continue
        out_path = Path(out_path_str)
        if out_path.exists():
            acc.add_warn(
                name=f"target.{table_name}.would_overwrite",
                message=f"Output target already exists and would be overwritten: {out_path_str}",
                location=f"targets.{table_name}.path",
            )
        else:
            # Check that the parent directory exists or can be created.
            parent = out_path.parent
            if not parent.exists():
                acc.add_warn(
                    name=f"target.{table_name}.parent_missing",
                    message=f"Output target directory does not exist: {parent!s}",
                    location=f"targets.{table_name}.path",
                )


# ---------------------------------------------------------------------------
# Capacity check (OOM checker v1, docs/plans/2026-07-24-oom-checker-cli-v1.md)
# ---------------------------------------------------------------------------

_GIB = 1024**3


def _format_gib(byte_count: int | None) -> str:
    return f"~{byte_count / _GIB:.1f} GB" if byte_count else "an unknown amount"


def _check_capacity(raw: dict[str, Any], config_path: Path, acc: _PreflightAccumulator) -> None:
    """Predict the out-of-core-FK memory-capacity gate before a run starts.

    R4 honest framing: this covers ONE gate -- the out-of-core-FK route's
    resident-memory floor. `decoy run` fully loads every source into memory
    BEFORE it ever calls the engine, so an ingestion `MemoryError` or OS
    OOM-kill happens before this gate runs; a "capacity: OK" here says
    nothing about that. See the module docstring's "OOM checker v1" note.

    R5 capability-detect: an engine older than the one that ships
    `estimate_job_capacity` degrades to "not checked" rather than an
    ImportError -- the CLI's floor stays >=0.5.0 either way.

    Degrades to "not checked" on ANY unexpected exception (a compile defect
    on a valid-but-uncovered shape, an unreadable source, ...) instead of
    crashing the rest of preflight -- this section augments the command, it
    does not gate whether the command itself can complete.

    Scope + posture: this section reads FILE-source metadata (parquet footer /
    a bounded local sample) to size the job. To keep preflight local and
    no-network, it runs only when every source is a file; if any source is
    non-file (database/API), capacity is "not checked" here rather than opening
    a remote connection during a "local" preflight.
    """
    import decoy_engine.execution as _engine_execution

    if not hasattr(_engine_execution, "estimate_job_capacity"):
        acc.add_pass(
            name="capacity.out_of_core_fk",
            message="not checked -- capacity check needs a newer engine.",
        )
        return

    # Preserve preflight's local, no-network posture: the engine estimate reads
    # each source, which for a non-file source means opening a DB/remote
    # connection. A "local" preflight must not do that, so skip capacity when
    # any source is non-file (matches _check_source_files' file-only scope).
    sources = raw.get("sources") or {}
    if isinstance(sources, dict) and any(
        isinstance(s, dict) and (s.get("type") or "file") != "file" for s in sources.values()
    ):
        acc.add_pass(
            name="capacity.out_of_core_fk",
            message="not checked -- capacity is estimated only for file sources in local preflight.",
        )
        return

    try:
        from decoy_engine import PipelineConfig
        from decoy_engine.execution.out_of_core._memory_estimate import CapacityVerdict

        config_dump = PipelineConfig.model_validate(raw).model_dump()
        estimate = _engine_execution.estimate_job_capacity(config_dump, config_path.parent)
    except Exception as exc:  # degrade, never crash preflight over this section
        acc.add_warn(
            name="capacity.out_of_core_fk",
            message=f"capacity check could not run: {exc}",
        )
        return

    needed = _format_gib(estimate.needed_bytes)
    available = _format_gib(estimate.available_bytes)

    if estimate.verdict is CapacityVerdict.FIT:
        acc.add_pass(
            name="capacity.out_of_core_fk",
            message=(
                "OK -- OOC-FK estimated resident floor is within budget (does not "
                f"include ingestion peak). Needs {needed}, budget {available}."
            ),
        )
    elif estimate.verdict is CapacityVerdict.INSUFFICIENT:
        acc.capacity_insufficient = True
        acc.add_fail(
            name="capacity.out_of_core_fk",
            message=(
                f"INSUFFICIENT -- needs {needed}, budget {available}; use a larger "
                "tier or reduce the job. This estimate is conservative: a real run "
                "may still admit the job via full-frame recovery."
            ),
            code=estimate.code,
        )
    elif estimate.verdict is CapacityVerdict.UNKNOWN:
        acc.add_pass(name="capacity.out_of_core_fk", message=f"not checked -- {estimate.message}")
    else:  # NOT_APPLICABLE
        acc.add_pass(
            name="capacity.out_of_core_fk", message=f"not applicable -- {estimate.message}"
        )


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


def preflight(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML pipeline config to check.",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help=(
            "Explicit local mode (all checks are local by default; "
            "this flag makes the intent explicit in scripts)."
        ),
    ),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a structured JSON result on stdout.",
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
    fail_on_warning: bool = typer.Option(
        False,
        "--fail-on-warning",
        help="Exit non-zero when any advisory warning fires.",
    ),
) -> None:
    """Local pre-run readiness checks for a pipeline config.

    Checks file existence, file readability, YAML syntax, schema validity,
    and (v1) whether the engine's out-of-core-FK memory gate would refuse
    the job. Reports findings as pass/warn/fail with structured output
    available via --json. An insufficient capacity result exits
    EXIT_CAPACITY (see `decoy explain exit-codes`), distinct from a config
    problem (EXIT_USAGE).

    This is a LOCAL check only. It does NOT check platform server-side
    conditions, most engine run-time constraints, data quality, vault
    access, secrets availability, or network connectivity. The capacity
    check covers the out-of-core-FK route only -- it does not cover the
    ingestion peak `decoy run` pays before the engine's gate runs, or the
    generate path. Use `decoy validate` for pure schema-only checks; use
    this command when you want to confirm source files are present and the
    job would clear the memory gate before starting a run.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)
    acc = _PreflightAccumulator()

    from decoy_engine import (
        ConfigError,
        PipelineConfig,
        PipelineValidationError,
        run_config_only_checks,
    )
    from decoy_engine.plan import PlanCompileError
    from pydantic import ValidationError

    # -- Step 1: YAML parse ---------------------------------------------------
    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        acc.add_fail(name="yaml.parse_error", message=f"YAML parse error: {exc}")
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    if raw is None:
        acc.add_fail(name="yaml.empty", message="Pipeline YAML is empty.")
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    if not isinstance(raw, dict):
        acc.add_fail(
            name="yaml.not_mapping",
            message=f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.",
        )
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # YAML parse passed
    acc.add_pass(name="yaml.syntax", message="YAML syntax is valid.")

    # -- Step 2: Schema validation --------------------------------------------
    try:
        PipelineConfig.model_validate(raw)
        acc.add_pass(name="schema.valid", message="Pipeline schema is valid.")
    except ValidationError as exc:
        for e in exc.errors():
            loc_parts = [str(p) for p in e.get("loc", ())]
            location = ".".join(loc_parts) if loc_parts else None
            acc.add_fail(
                name="schema.field",
                message=e.get("msg", str(e)),
                location=location,
            )
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)
    except (PipelineValidationError, ConfigError) as exc:
        acc.add_fail(name="schema.validation_error", message=str(exc))
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 3: Profile-free plan-compile checks ----------------------------
    try:
        run_config_only_checks(raw)
        acc.add_pass(name="config.plan_checks", message="Profile-free plan-compile checks passed.")
    except PlanCompileError as exc:
        acc.add_fail(name=f"config.{exc.code}", message=exc.message)
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 4: Source file checks ------------------------------------------
    _check_source_files(raw, acc)

    # -- Step 5: Target overwrite advisory -----------------------------------
    _check_target_overwrite(raw, acc)

    # -- Step 6: Capacity check (OOM checker v1) -----------------------------
    _check_capacity(raw, config, acc)

    # -- Emit and exit --------------------------------------------------------
    _emit_preflight_result(state, acc, config_str, fail_on_warning)

    # T7: INSUFFICIENT capacity exits EXIT_CAPACITY, checked BEFORE the
    # generic has_failures path so it is never masked as a plain EXIT_USAGE
    # config problem -- a distinct, machine-detectable "needs more memory"
    # result up front, before a run starts.
    if acc.capacity_insufficient:
        raise typer.Exit(code=EXIT_CAPACITY)
    if acc.has_failures:
        raise typer.Exit(code=EXIT_USAGE)
    if fail_on_warning and acc.has_warnings:
        raise typer.Exit(code=_WARN_EXIT)


def _emit_preflight_result(
    state: Any,
    acc: _PreflightAccumulator,
    config_str: str,
    fail_on_warning: bool,
) -> None:
    """Render the accumulated preflight result."""
    capacity_checks = [c for c in acc.checks if c.name == "capacity.out_of_core_fk"]

    if state.mode is OutputMode.json:
        status = "ok" if not acc.has_failures else "fail"
        if status == "ok" and fail_on_warning and acc.has_warnings:
            status = "warn"
        payload: dict[str, Any] = {
            "command": "preflight",
            "status": status,
            "config": config_str,
            "checks": acc.to_dicts(),
            "fail_count": sum(1 for c in acc.checks if c.status == "fail"),
            "warn_count": sum(1 for c in acc.checks if c.status == "warn"),
            "pass_count": sum(1 for c in acc.checks if c.status == "pass"),
        }
        # A structured top-level `capacity` block, in addition to its entry
        # in `checks` -- R9: assertable without parsing display text.
        if capacity_checks:
            cap = capacity_checks[0]
            payload["capacity"] = {
                "status": cap.status,
                "message": cap.message,
                "code": cap.code,
            }
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable: print warnings then failures, then overall result.
    for chk in acc.checks:
        if chk.name == "capacity.out_of_core_fk":
            continue  # rendered separately below, at every status (not just warn/fail)
        if chk.status == "warn":
            loc_hint = f" ({chk.location})" if chk.location else ""
            state.err_console.print(warn("warning:"), chk.message + loc_hint)
        elif chk.status == "fail":
            loc_hint = f" ({chk.location})" if chk.location else ""
            state.err_console.print(error("fail:"), chk.message + loc_hint)

    # The capacity line always prints, regardless of pass/warn/fail: OK, not
    # checked, and not applicable are all informative outcomes an operator
    # should see, not just the failure case.
    for cap in capacity_checks:
        label = error("capacity:") if cap.status == "fail" else hint("capacity:")
        state.err_console.print(label, cap.message)

    if acc.has_failures:
        state.err_console.print(
            error("FAIL"),
            code(config_str),
            hint("- fix the errors above, then rerun."),
        )
        return

    state.console.print(success("OK"), code(config_str))

    if acc.has_warnings and fail_on_warning:
        state.err_console.print(
            warn("warning:"),
            "warnings present and --fail-on-warning is set.",
        )


PREFLIGHT_EPILOG = _PREFLIGHT_EPILOG
