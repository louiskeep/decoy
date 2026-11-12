"""`decoy validate preflight` -- local file, source, and schema readiness checks (SP-17).

`preflight` helps catch common problems BEFORE running a pipeline. It performs
local checks that do not require the engine to execute the full pipeline.

What preflight checks (honest framing)
--------------------------------------
1. YAML syntax, schema and profile-free config logic.
2. Project-layout output paths (the same refusals as `decoy validate`).
3. Source file existence and readability.
4. Existing output targets (advisory).
5. Out-of-core-FK capacity and generated-output floor (hard refusals exit EXIT_CAPACITY).
6. Native companion health and static config-shape eligibility.

What preflight does NOT check
------------------------------
* Platform preflight conditions such as secrets, RBAC, schedules, and network targets.
* Engine run-time constraints beyond the out-of-core-FK capacity check above
  (provider capacity, null-bearing integer distributions) -- these require a
  profile pass during the run.
* Vault or secret access, network connectivity, or successful engine execution.

OOM checker v1 (docs/plans/2026-07-24-oom-checker-cli-v1.md): the capacity
check is an "OOC-FK engine-gate capacity checker", NOT a whole-job OOM
guarantee. `decoy run` fully loads every source into memory BEFORE it calls
the engine, so an ingestion `MemoryError` or OS OOM-kill happens before this
gate ever runs -- this check does not cover that. A "capacity: OK" here means
only that no hard impossibility was found. The build-floor estimate is
ADVISORY: when the predicted relation-build floor exceeds its cap, the check
reports a WARNING with a recommended size and the job still proceeds
(`--fail-on-warning` turns that warning into a nonzero exit). Two hard
capacity refusals exit EXIT_CAPACITY: a fan-in impossibility (more co-live
DuckDB joiners than the budget can seat), and generate tables whose resident
output cannot fit the machine's memory (`generation_budget_exceeded`, GEN-STRICT
row 24k). A config with a non-file source skips the estimate, so a generate floor
refusal exits 5 only at `decoy run`. A missing or unreadable source file
fails first (exit 1), so the exit 5 needs readable sources.

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
from rich.text import Text

from decoy.cli._yaml_errors import sanitize_yaml_error
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_USAGE, EXIT_WARNINGS
from decoy.cli.gate._capacity_text import format_gib as _format_gib
from decoy.cli.gate._capacity_text import insufficient_text as _insufficient_text
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import code, error, hint, success, warn

_PREFLIGHT_EPILOG = """\
Examples:

  decoy validate preflight pipeline.yaml
    Run local readiness checks: YAML validity, schema, and source file existence.

  decoy validate preflight pipeline.yaml --local
    Same as above (--local is the explicit form; all checks are local by default).

  decoy validate preflight pipeline.yaml --json
    Emit a structured JSON result with per-check findings.

  decoy validate preflight pipeline.yaml --fail-on-warning
    Exit non-zero when advisory warnings fire (e.g. output already exists).

What preflight checks:
  - YAML syntax and schema (same as `decoy validate`)
  - Source file existence and readability
  - Target overwrite risk (advisory warning)
  - Out-of-core-FK memory capacity (v1; build-floor is advisory, a fan-in
    impossibility exits EXIT_CAPACITY -- see: decoy explain exit-codes)
  - Generated tables whose output cannot fit memory (exit EXIT_CAPACITY)
  - Native companion health, plus a STATIC (config-shape-only) native
    eligibility possibility -- see: decoy explain native

What preflight does NOT check:
  - Platform server-side conditions (secrets, RBAC, schedules, network targets)
  - Engine run-time constraints beyond out-of-core-FK capacity (row counts,
    provider limits)
  - The ingestion peak `decoy run` pays before the engine's capacity gate runs
    (out of the v1 capacity check's scope)
  - Data validity or masking quality
  - Vault or secrets accessibility

See also: decoy validate, decoy run, decoy report verify, decoy explain exit-codes.
"""


# ---------------------------------------------------------------------------
# Check accumulator (reused from validate)
# ---------------------------------------------------------------------------

# The capacity check's name; `decoy.cli.gate` keys its chunked-route rule on it.
CAPACITY_CHECK = "capacity.out_of_core_fk"
# A plan the engine cannot compile, found while pricing capacity. Not CAPACITY_CHECK, so the
# chunked-route downgrade leaves it a FAIL.
PLAN_UNCOMPILABLE_CHECK = "capacity.plan_uncompilable"


@dataclass
class _CheckResult:
    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str
    location: str | None = None
    # OOM checker v1: the engine's capacity-refusal code (out_of_core_insufficient_memory,
    # out_of_core_fanin_exceeds_budget or generation_budget_exceeded),
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


def _check_source_files(raw: dict[str, Any], base_dir: Path, acc: _PreflightAccumulator) -> None:
    """Check that every declared source file exists and is readable.

    File checks only. Parser config, column layout, and format inference are
    NOT checked here (those are engine-level concerns that require a profile
    pass). This check is about the files themselves, not their contents.

    Relative source paths resolve against `base_dir` (the pipeline YAML's
    directory), the SAME way `decoy run` and `estimate_job_capacity` resolve
    them (Codex re-gate MEDIUM). Resolving against CWD instead let a
    same-named file in the caller's working directory mask a source that is
    genuinely missing where the runner would look, so preflight could exit 0
    on a job `decoy run` would fail -- and the capacity guard's
    YAML-dir-resolved skip then hid it a second time.
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
        if not src_path.is_absolute():
            src_path = base_dir / src_path
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
    """Advisory: warn when an absolute output target is invalid, exists or cannot be written.

    These are warnings, not failures: the run overwrites, and the writer creates a missing
    folder, so only an existing file or a parent no run could write is worth surfacing. A
    relative path lands in a new run folder (AT-16), so none of these can apply to it.
    """
    from decoy.cli.io import is_placed_relative, target_parent_writable

    targets = raw.get("targets")
    for table_name, target in targets.items() if isinstance(targets, dict) else ():
        if not isinstance(target, dict) or target.get("type") not in ("file", None):
            continue
        out_path_str = target.get("path")
        if not isinstance(out_path_str, str) or is_placed_relative(out_path_str):
            continue
        if not Path(out_path_str).is_absolute():
            continue
        location = f"targets.{table_name}.path"
        out_path = Path(out_path_str)
        try:
            exists = out_path.exists()
            writable = exists or target_parent_writable(out_path)
        except (ValueError, OSError):
            msg = f"Output target path for table {table_name} is invalid."
            acc.add_warn(f"target.{table_name}.path_invalid", msg, location)
            continue
        if exists:
            msg = f"Output target already exists and would be overwritten: {out_path_str}"
            acc.add_warn(
                name=f"target.{table_name}.would_overwrite", message=msg, location=location
            )
        elif not writable:
            msg = f"Output target directory for table {table_name} cannot be created or written."
            acc.add_warn(f"target.{table_name}.parent_unwritable", msg, location)


# ---------------------------------------------------------------------------
# Capacity check (OOM checker v1, docs/plans/2026-07-24-oom-checker-cli-v1.md)
# ---------------------------------------------------------------------------


def _file_sources_missing_on_disk(raw: dict[str, Any], base_dir: Path) -> bool:
    """True if any declared FILE-type source does not resolve to a readable
    regular file, resolved the SAME way `estimate_job_capacity`,
    `_check_source_files`, and `decoy run` resolve them (relative to
    `base_dir`, the pipeline YAML's directory -- R2). All three now agree on
    resolution, so a source missing where the runner would look is reported
    by Step 4 as a `fail` AND skipped here, never silently passed.

    Root-cause guard for a real regression: without it, a job whose source
    is already known missing (Step 4's `_check_source_files` already
    reported a `fail` for it) would still reach `estimate_job_capacity`,
    which raises on an unreadable source (its own documented R3 contract,
    "an unreadable source" propagates) -- and since that exception is no
    longer swallowed here (R3, Codex P1-2), it would crash the WHOLE
    `preflight` command before `_emit_preflight_result` ever runs, losing
    every finding accumulated so far, including the one that already
    explained the problem. Skipping the capacity estimate for a source we
    already know cannot be read is not swallowing a defect -- it is
    declining to run a check whose precondition is already known false,
    exactly like the sibling non-file-source skip below.
    """
    sources = raw.get("sources") or {}
    if not isinstance(sources, dict):
        return False
    for src in sources.values():
        if not isinstance(src, dict) or (src.get("type") or "file") != "file":
            continue
        path_str = src.get("path")
        if not path_str:
            return True
        path = Path(path_str)
        if not path.is_absolute():
            path = base_dir / path
        if not path.is_file():
            return True
        # Present but UN-OPENABLE counts too (Codex re-gate MEDIUM): a
        # permission-denied file opens-then-fails, and `estimate_job_capacity`
        # -> `profile_source` opens the source, so with the broad catch removed
        # (R3) it would crash the command. Skip the estimate; Step 4's
        # readability check already reported the `fail`. This tests filesystem
        # ACCESSIBILITY only (open + zero-byte read) -- a file that opens but is
        # truncated/corrupt/wrong-format is NOT caught here (parsing would be
        # required); that case is handled downstream by the estimator's typed
        # `capacity_source_unprofilable` error, rendered as a capacity fail.
        try:
            with path.open("rb") as fh:
                fh.read(0)
        except OSError:
            return True
    return False


def _check_capacity(raw: dict[str, Any], config_path: Path, acc: _PreflightAccumulator) -> None:
    """Predict the out-of-core-FK memory-capacity gate before a run starts.

    R4 honest framing: this covers the out-of-core-FK route's memory check,
    which has two branches -- an ADVISORY build-floor prediction (an over-cap
    floor WARNS with a recommended size, it does not refuse) and a hard fan-in
    impossibility guard (the only branch that exits EXIT_CAPACITY). `decoy run`
    fully loads every source into memory BEFORE it ever calls the engine, so an
    ingestion `MemoryError` or OS OOM-kill happens before this gate runs; a
    "capacity: OK" here says nothing about that. See the module docstring's
    "OOM checker v1" note.

    R5 capability-detect: an engine older than the one that ships
    `estimate_job_capacity` degrades to "not checked" rather than an
    ImportError -- the CLI's engine floor is >=0.6.0 either way.

    R3 (Codex P1-2): `estimate_job_capacity` returns a typed verdict
    (`UNKNOWN` for expected indeterminacy) or raises. A plan the engine
    rejects (`PlanCompileError`) becomes a `capacity.plan_uncompilable` FAIL;
    any other exception is a real defect and propagates, since folding it
    into a WARN would report a false pass. Only the THREE guarded
    early-returns below (capability-detect, non-file sources, a source
    already known missing/unreadable from disk) skip the estimator. The third
    exists because a missing source is also one of the estimator's documented
    propagating cases: without it, a source Step 4 (`_check_source_files`)
    already flagged would crash the command before any finding is printed.

    Scope + posture: this section reads FILE-source metadata (parquet footer /
    a bounded local sample) to size the job. To keep preflight local and
    no-network, it runs only when every source is a file; if any source is
    non-file (database/API), capacity is "not checked" here rather than opening
    a remote connection during a "local" preflight.
    """
    import decoy_engine.execution as _engine_execution

    if not hasattr(_engine_execution, "estimate_job_capacity"):
        acc.add_pass(
            name=CAPACITY_CHECK,
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
            name=CAPACITY_CHECK,
            message="not checked -- capacity is estimated only for file sources in local preflight.",
        )
        return

    # A source already known missing/unreadable (Step 4 already reported this
    # as a `fail`) cannot be estimated -- see `_file_sources_missing_on_disk`'s
    # docstring for why this guard exists (a real regression it fixes).
    if _file_sources_missing_on_disk(raw, config_path.parent):
        acc.add_pass(
            name=CAPACITY_CHECK,
            message="not checked -- one or more declared source files are missing or "
            "unreadable; see the source-file findings above.",
        )
        return

    from decoy_engine import CapacityVerdict, ExecutionError, parse_pipeline_config
    from decoy_engine.plan import PlanCompileError

    # The ONE narrow catch here (R3): a source that is present but corrupt /
    # not-the-declared-format passes the on-disk guard above (which only tests
    # filesystem accessibility, not parseability) and fails when the estimator
    # profiles it -- `estimate_job_capacity` raises the typed
    # `capacity_source_unprofilable` for exactly that. Render it as a FAIL (the
    # profile read is the first check that actually parses the source, so this
    # is where a corrupt file legitimately surfaces) rather than crashing on a
    # raw traceback. Any OTHER exception -- an unexpected estimator defect --
    # still propagates, never degraded into a WARN or a false pass (Codex
    # P1-2 / re-gate MEDIUM).
    config_dump = parse_pipeline_config(raw).model_dump()
    try:
        estimate = _engine_execution.estimate_job_capacity(config_dump, base_dir=config_path.parent)
    except ExecutionError as exc:
        if exc.code == "out_of_core_fanin_exceeds_budget":
            # Round-4 (engine): the build-floor gate is now advisory, so
            # `estimate_job_capacity` no longer returns INSUFFICIENT for
            # that case -- but a fan-in impossibility discovered while
            # resolving the memory budget still PROPAGATES as this
            # ExecutionError instead of coming back as a verdict. Render it
            # the same way the INSUFFICIENT verdict branch below does (a
            # FAIL that trips EXIT_CAPACITY), so a fan-in job still refuses
            # cleanly instead of crashing preflight on a raw traceback.
            acc.capacity_insufficient = True
            acc.add_fail(
                name=CAPACITY_CHECK,
                message=f"INSUFFICIENT -- {exc.message}",
                code=exc.code,
            )
            return
        if exc.code != "capacity_source_unprofilable":
            raise
        acc.add_fail(
            name="capacity.source_unreadable",
            message=f"Cannot estimate capacity -- source not parsed ({type(exc.__cause__).__name__})",
            code=exc.code,
        )
        return
    except PlanCompileError as exc:
        # Own check name so CHUNKED's CAPACITY_CHECK downgrade cannot make it a warning.
        # Only the structured code and path are shown, never the engine's message text.
        from decoy_engine.relationships import NamespaceConfigError

        hint = (
            "Run `decoy explain pipeline` for how namespaces are resolved."
            if isinstance(exc, NamespaceConfigError)
            else "Run `decoy validate compile` for the compile error."
        )
        acc.add_fail(
            name=PLAN_UNCOMPILABLE_CHECK,
            message=f"Cannot estimate capacity -- the plan does not compile ({exc.code}). {hint}",
            location=exc.path,
            code=exc.code,
        )
        return

    needed = _format_gib(estimate.needed_bytes)
    available = _format_gib(estimate.available_bytes)

    if estimate.verdict is CapacityVerdict.FIT and estimate.warned:
        # Round-4: FIT no longer means "clears the build-floor budget" -- it
        # means "no hard impossibility detected". `warned=True` marks an
        # adverse build-floor prediction (relation-build only; excludes
        # resident inputs, accumulated outputs, and ingestion peak); render
        # it as a WARNING, not a green PASS, so `--fail-on-warning` can act
        # on it, but the job is not refused either way.
        # Relay the engine's own wording verbatim: it distinguishes a floor that
        # NEARS its cap (the warn band, floor still under cap) from one that
        # EXCEEDS it, so a hardcoded "exceeds" here would misreport a warn-band
        # floor that still sits under its cap as over it.
        acc.add_warn(
            name=CAPACITY_CHECK,
            message=(
                f"ADVISORY -- {estimate.message} Recommends {needed} (budget {available}); "
                "the job is not refused, this is a recommendation."
            ),
        )
    elif estimate.verdict is CapacityVerdict.FIT:
        acc.add_pass(
            name=CAPACITY_CHECK,
            message=(
                "OK -- OOC-FK estimated resident floor is within budget (does not "
                f"include ingestion peak). Needs {needed}, budget {available}."
            ),
        )
    elif estimate.verdict is CapacityVerdict.INSUFFICIENT:
        acc.capacity_insufficient = True
        acc.add_fail(name=CAPACITY_CHECK, message=_insufficient_text(estimate), code=estimate.code)
    elif estimate.verdict is CapacityVerdict.UNKNOWN:
        # An uncertain route (a byte-estimate-promoted OOC job) forces UNKNOWN,
        # but a build-floor advisory can still ride along on the estimate. Surface
        # it as a warning so the recommendation is not lost and --fail-on-warning
        # can act on it, exactly as it does on the confirmed FIT+warned path.
        if estimate.warned:
            acc.add_warn(
                name=CAPACITY_CHECK,
                message=f"ADVISORY (route unconfirmed) -- {estimate.message}",
            )
        else:
            acc.add_pass(name=CAPACITY_CHECK, message=f"not checked -- {estimate.message}")
    else:  # NOT_APPLICABLE
        acc.add_pass(name=CAPACITY_CHECK, message=f"not applicable -- {estimate.message}")


# ---------------------------------------------------------------------------
# Native companion + eligibility check (Phase 3.1)
# ---------------------------------------------------------------------------


def _check_native(raw: dict[str, Any], acc: _PreflightAccumulator) -> None:
    """Companion health (pass/warn, never a hard fail here -- a broken
    companion is `decoy run`'s fail-closed gate's job, not a preflight
    refusal) plus a STATIC, config-shape-only native-eligibility line.

    The eligibility line is explicitly labeled a possibility, not a
    guarantee (plan approach 4, open question 5): real admission needs the
    resolved route, the source profile, the resident Arrow table, and the
    compiled physical plan, none of which a profile-free preflight has.
    """
    import decoy_engine

    from decoy import _native_gate

    probe = getattr(decoy_engine, "native_companion_status", None)
    if probe is None:
        # R5 capability-detect (matches `_check_capacity`'s own posture): an
        # engine this old predates the probe entirely, not an error.
        acc.add_pass(
            name="native.companion",
            message="not checked -- native companion health needs a newer engine.",
        )
    else:
        status = probe()
        if status.ok:
            acc.add_pass(
                name="native.companion",
                message=(
                    f"native companion present and healthy "
                    f"(v{_native_gate.sanitize_abi(status.version)})."
                ),
            )
        elif status.present:
            acc.add_warn(
                name="native.companion",
                message=(
                    f"native companion present but not usable ({status.reason}) -- "
                    f"expected ABI {status.abi_expected}, got "
                    f"{_native_gate.sanitize_abi(status.abi_actual)!r}. `decoy run` "
                    "fails closed on this by default; use --no-native to roll back."
                ),
                code=status.reason,
            )
        else:
            acc.add_pass(
                name="native.companion",
                message="native companion not installed; masking runs on the Python fallback.",
            )

    if _native_gate.static_native_eligibility(raw):
        acc.add_pass(
            name="native.eligibility",
            message=(
                "Native eligibility: eligible by config (single non-FK csv/parquet/fixed_width "
                "mask table, companion-dependent native strategy present) -- a "
                "STATIC possibility, not a guarantee; the actual route depends "
                "on the resolved profile and resident data at run time."
            ),
        )
    else:
        acc.add_pass(
            name="native.eligibility",
            message=(
                "Native eligibility: not eligible by config shape (needs a single "
                "non-FK mask table (declared csv, parquet or fixed_width) with at least one hash/categorical/"
                "bucket_perturb/group_key column, and no validators/quarantine/"
                "post-scan integrity/vault/transforms/when-gates)."
            ),
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
    and (v1) the engine's out-of-core-FK memory feasibility. The build-floor
    estimate is advisory: an over-budget prediction reports a WARNING with a
    recommended size, not a refusal (`--fail-on-warning` makes it exit
    nonzero). A fan-in impossibility, and generated tables whose output
    cannot fit the machine's memory, exit EXIT_CAPACITY (see `decoy explain
    exit-codes`), distinct from a config problem (EXIT_USAGE). Reports
    findings as pass/warn/fail with structured output available via --json.

    This is a LOCAL check only. It does NOT check platform server-side
    conditions, most engine run-time constraints, data quality, vault
    access, secrets availability, or network connectivity. The capacity
    check does not cover the ingestion peak `decoy run` pays before the
    engine's gate runs. Use `decoy validate` for pure schema-only checks; use
    this command when you want to confirm source files are present and check
    the job's capacity feasibility before starting a run.
    """
    state = setup_output(json_, quiet, verbose)
    config_str = str(config)
    acc = _PreflightAccumulator()

    from decoy_engine import (
        ConfigError,
        PipelineValidationError,
        parse_pipeline_config,
        run_config_only_checks,
    )
    from decoy_engine.config import PipelineConfigError
    from decoy_engine.plan import PlanCompileError

    # -- Step 1: YAML parse ---------------------------------------------------
    try:
        raw = _yaml.safe_load(config.read_text(encoding="utf-8"))
    except _yaml.YAMLError as exc:
        acc.add_fail(name="yaml.parse_error", message=sanitize_yaml_error(exc))
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
        parse_pipeline_config(raw)
        acc.add_pass(name="schema.valid", message="Pipeline schema is valid.")
    except PipelineConfigError as exc:
        for problem in exc.problems:
            acc.add_fail(
                name="schema.field",
                message=problem.text,
                location=problem.location or None,
            )
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)
    except (PipelineValidationError, ConfigError) as exc:
        acc.add_fail(name="schema.validation_error", message=str(exc))
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 3: Profile-free plan-compile checks ----------------------------
    try:
        run_config_only_checks(raw, base_dir=config.parent)
        acc.add_pass(name="config.plan_checks", message="Profile-free plan-compile checks passed.")
    except PlanCompileError as exc:
        # Rewrite ner_spacy_not_installed to decoy-cli's own [ner] extra;
        # see plan_compile_error_fields's docstring for why every
        # PlanCompileError display site goes through it.
        from decoy.cli.extras import plan_compile_error_fields

        code, message = plan_compile_error_fields(exc)
        acc.add_fail(name=f"config.{code}", message=message)
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 3b: Project-layout checks --------------------------------------
    from decoy.cli.io import layout_failures

    for code, message, location in layout_failures(config, raw):
        acc.add_fail(name=code, message=message, location=location, code=code)
    if acc.has_failures:
        _emit_preflight_result(state, acc, config_str, fail_on_warning)
        raise typer.Exit(code=EXIT_USAGE)

    # -- Step 4: Source file checks ------------------------------------------
    _check_source_files(raw, config.parent, acc)

    # -- Step 5: Target overwrite advisory -----------------------------------
    _check_target_overwrite(raw, acc)

    # -- Step 6: Capacity check (OOM checker v1) -----------------------------
    _check_capacity(raw, config, acc)

    # -- Step 7: Native companion health + static eligibility (Phase 3.1) ----
    _check_native(raw, acc)

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
        raise typer.Exit(code=EXIT_WARNINGS)


def _emit_preflight_result(
    state: Any,
    acc: _PreflightAccumulator,
    config_str: str,
    fail_on_warning: bool,
) -> None:
    """Render the accumulated preflight result."""
    capacity_checks = [c for c in acc.checks if c.name == CAPACITY_CHECK]
    native_checks = [c for c in acc.checks if c.name in ("native.companion", "native.eligibility")]

    if state.mode is OutputMode.json:
        status = "ok" if not acc.has_failures else "fail"
        if status == "ok" and fail_on_warning and acc.has_warnings:
            status = "warn"
        payload: dict[str, Any] = {
            "command": "validate preflight",
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
        # Same structured-block treatment as `capacity` (R9): a --json
        # caller asserts on `native.companion` / `native.eligibility`
        # directly instead of parsing `checks` by name.
        for chk in native_checks:
            payload[chk.name.replace(".", "_")] = {
                "status": chk.status,
                "message": chk.message,
                "code": chk.code,
            }
        emit_json(state, payload)
        return

    if state.mode is OutputMode.quiet:
        return

    # Human-readable: print warnings then failures, then overall result.
    for chk in acc.checks:
        if chk.name in (CAPACITY_CHECK, "native.companion", "native.eligibility"):
            continue  # rendered separately below, at every status (not just warn/fail)
        # markup=False on every message print in this function: a check
        # message is not authored markup. It can carry an install hint like
        # `pip install decoy-cli[ner]` (Rich would parse `[ner]` as an
        # unknown tag and drop it), a user path, or engine text relayed
        # verbatim. The styled labels are Text objects and keep their style.
        if chk.status == "warn":
            loc_hint = f" ({chk.location})" if chk.location else ""
            state.err_console.print(warn("warning:"), chk.message + loc_hint, markup=False)
        elif chk.status == "fail":
            loc_hint = f" ({chk.location})" if chk.location else ""
            state.err_console.print(error("fail:"), chk.message + loc_hint, markup=False)

    # The capacity line always prints, regardless of pass/warn/fail: OK, not
    # checked, and not applicable are all informative outcomes an operator
    # should see, not just the failure case.
    for cap in capacity_checks:
        if cap.status == "fail":
            label = error("capacity:")
        elif cap.status == "warn":
            label = warn("capacity:")
        else:
            label = hint("capacity:")
        state.err_console.print(label, cap.message, markup=False)

    # Same always-print treatment for the native companion + eligibility
    # lines: both are informative even at "pass" (companion absent, or
    # config not eligible, are normal outcomes an operator should still see).
    # Text(): the message can carry an untrusted `abi_actual` value (see
    # sanitize_abi) that Rich's default string markup would otherwise
    # reinterpret.
    for nat in native_checks:
        if nat.status == "warn":
            label = warn("native:")
        else:
            label = hint("native:")
        state.err_console.print(label, Text(nat.message))

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
