"""The one builder of the run result document of a `decoy run` (RESULT C-DOC1).

The run's facts live on `RunContext`: the engine's `ExecutionResult`, the progress collector, the
publication ledger and the config. This module turns them into the document, and into the exit
integer the document carries, in one place. `_errors` and `_render` call it with the category and
the reason; neither builds a document, a delivery fact or a status of its own.

A build that raises is a defect in the document, never in the run: the run keeps its exit code
(read from the same `RUN_EXIT_MAP` through the engine's `derive_outcome`), the `--json` envelope
loses its `result` member and `result_status` says why. Only value-free facts go in: table names
pass the engine's name check, outputs are run-relative, no message and no path of the caller.

Named limit: a `--chunked` run emits no progress events, so its tables carry no row counts.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from decoy._atomic import AtomicWriteError, WriteMode, describe, write_local_target
from decoy._version import __version__ as _cli_version
from decoy.cli import exit_codes
from decoy.cli.exit_codes import run_exit_code
from decoy.cli.io import declared_format
from decoy.cli.run._context import RunContext, library_choice, library_label, output_placement
from decoy.ui.output import OutputMode, emit_error, emit_json
from decoy.ui.theme import warn

_BUILT = {"document": "built", "file": "not_requested", "code": None}
_FAILED = {"document": "failed", "file": "not_requested", "code": "run_result_build_failed"}


@dataclass(frozen=True)
class Document:
    """What the builder hands back: the `result` payload (None when the build failed), the
    `result_status` member and the run's exit integer."""

    payload: dict | None
    status: dict
    exit_code: int


def collect(ctx: RunContext) -> Callable[[Any], None]:
    """Start the run's collector and return the consumer to put on the progress sink."""
    from decoy_engine.run_result import RunResultCollector

    ctx._collector = RunResultCollector()
    return ctx._collector.on_event


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _output(ctx: RunContext, path: Path) -> str | None:
    """The file as the run folder (or `--out-dir`) names it, else its file name."""
    resolved = Path(path).resolve()
    folder = ctx.layout.output_dir() if ctx.layout is not None else None
    if folder is not None and folder in resolved.parents:
        return resolved.relative_to(folder).as_posix()
    return resolved.name


def _entry(ctx: RunContext, name: str, targets: dict) -> Any:
    from decoy_engine.run_result import TableDelivery

    published = ctx._published.get(name)
    if published is None:
        return TableDelivery(
            state="none", format=None, output=None, reason=None, dropped_because=None
        )
    spec = targets.get(name)
    fmt = declared_format(spec)
    try:
        return TableDelivery(
            state="delivered",
            format=fmt,
            output=_output(ctx, published),
            reason=None,
            dropped_because=None,
        )
    except ValueError:
        # An output name the document may not carry: delivered, with no file shown.
        return TableDelivery(
            state="delivered", format=fmt, output=None, reason=None, dropped_because=None
        )


def delivery_facts(ctx: RunContext, config: dict, *, vault_failed: bool) -> Any:
    """The one provider of delivery facts. Before DELIV a table is delivered when the publication
    ledger holds its file, and not otherwise; a preview and a config with no target say nothing."""
    from decoy_engine.config import classify_table_kinds
    from decoy_engine.run_result import DeliveryFacts

    targets = config.get("targets")
    targets = targets if isinstance(targets, dict) else {}
    declared = classify_table_kinds(config)
    names = [name for name in targets if name in declared]
    if ctx.rows is not None or not names:
        return DeliveryFacts.not_applicable()
    writer = getattr(ctx, "vault_writer", None)
    if writer is None:
        vault = "not_used"
    elif vault_failed:
        vault = "failed"
    else:
        vault = "committed" if Path(ctx.vault).exists() else "not_used"
    return DeliveryFacts(
        "in_place",
        vault,
        {name: _entry(ctx, name, targets) for name in names},  # type: ignore[arg-type]
    )


def _config(ctx: RunContext) -> dict:
    config = getattr(ctx, "config_dict", None)
    if isinstance(config, dict):
        return config
    return ctx.raw_cfg if ctx.raw_cfg is not None else {}


def _config_ref(ctx: RunContext, config: dict) -> Any:
    from decoy_engine import pipeline_config_hash
    from decoy_engine.reasons import approve_name
    from decoy_engine.run_result import ConfigRef

    from decoy.cli.evidence import hash_file

    def attempt(read: Callable[[], Any]) -> Any:
        try:
            return read()
        except Exception:
            return None

    return ConfigRef(
        name=approve_name(ctx.config.name),
        file_sha256=attempt(lambda: hash_file(ctx.config)),
        semantic_hash=attempt(lambda: pipeline_config_hash(config)),
    )


def _native(ctx: RunContext) -> Any:
    from decoy_engine.run_result import NativeRoute

    route = ctx._native_route
    if route is None:
        return None
    state = route.state if route.state in ("pandas", "native", "unified_slice") else None
    return NativeRoute(applicable=route.applicable, state=state)


def _build(
    ctx: RunContext,
    category: str | None,
    reason: Any,
    error_class: str | None,
    blocking_failed: bool,
    vault_failed: bool,
    early: bool,
) -> tuple[dict, int]:
    from decoy_engine import route_summary
    from decoy_engine.run_result import (
        FailureInput,
        Links,
        build_run_result,
        project_tables,
    )

    # A refusal before the run starts has read no config: it names none and holds no table.
    config = {} if early else _config(ctx)
    failed = category is not None
    facts = None if ctx._collector is None else ctx._collector.snapshot()
    execution = ctx._execution
    delivery = delivery_facts(ctx, config, vault_failed=vault_failed)
    tables = project_tables(
        config=config,
        execution_result=execution,
        facts=facts,
        delivery=delivery,
        run_failed=failed,
    )
    now = datetime.now(timezone.utc)
    elapsed = getattr(ctx, "elapsed", None)
    elapsed = time.perf_counter() - ctx.started if elapsed is None else elapsed
    document = build_run_result(
        tables=tables,
        execution_result=execution,
        failure=FailureInput(category, reason, error_class) if failed else None,  # type: ignore[arg-type]
        config_ref=None if early else _config_ref(ctx, config),
        producer=_cli_version,
        invocation_id=ctx.invocation_id,
        exit_map=exit_codes.RUN_EXIT_MAP,
        blocking_failed=blocking_failed,
        native=_native(ctx),
        chunked=ctx.chunked,
        route=None if execution is None else route_summary(execution.quality_metrics),
        links=Links(log=None, evidence=None, baseline=None),
        started_at=_stamp(ctx._run_started_at),
        finished_at=_stamp(now),
        elapsed_s=max(0.0, float(elapsed)),
        phases=() if facts is None else facts.phases,
    )
    return document.to_payload(), document.exit_code


def build(
    ctx: RunContext,
    *,
    category: str | None = None,
    reason: Any = None,
    error_class: str | None = None,
    blocking_failed: bool = False,
    vault_failed: bool = False,
    early: bool = False,
) -> Document:
    """The document of this run and its exit integer. `reason` is the engine's `ReasonRecord`.

    `early` marks a refusal that came before the config was read: the document has no config,
    no table and no route.

    Never raises for a document defect: the exit then comes straight from `derive_outcome` with
    the same inputs, and the one stderr line names the exception class and the code only.
    """
    try:
        payload, code = _build(
            ctx, category, reason, error_class, blocking_failed, vault_failed, early
        )
    except Exception as exc:
        if ctx.state.mode is not OutputMode.quiet:
            ctx.state.err_console.print(
                warn("warning:"), f"run_result_build_failed ({type(exc).__name__})", markup=False
            )
        return Document(
            None, dict(_FAILED), run_exit_code(category, blocking_failed=blocking_failed)
        )
    return Document(payload, dict(_BUILT), code)


def _placement_refused(ctx: RunContext) -> str | None:
    """A reason code when the gate's layout rules refuse this run's outputs with `--result` among them.

    The same check the gate runs before a source is read, run again here because a refusal that
    came before the gate (a bad `--notify`, a bad key) never reached it, and because the gate's
    own refusal for a colliding `--result` must not then write the file it refused. Any layout
    fault blocks the write: the result path is then not known to be clear of the outputs. Fails
    closed on an error, and then the code names the exception class.
    """
    from decoy.cli.gate import layout_findings, parse_pipeline_yaml

    try:
        raw = getattr(ctx, "raw", None)
        raw = raw if raw is not None else parse_pipeline_yaml(ctx.config)[0]
        config = raw if isinstance(raw, dict) else {}
        found = layout_findings(ctx.config, config, output_placement(ctx))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return f"output_path_refused_{type(exc).__name__}"
    return "output_path_refused" if found else None


def _store_record(ctx: RunContext, document: Document) -> None:
    """Store the document as a `run-result` record: the one store call, so every exit path that
    writes the envelope stores it, built once by `build`. Never changes the exit code (plan 4.17).

    A preview, `--no-library`, a refusal before the run starts, a failed build and a second call
    for the same run store nothing, and neither does a run whose evidence store already failed
    (it warned once; the root is the cause). "Before the run starts" is `ctx.execution_started`,
    never the failure category: a post-start engine fault can be a `usage` failure.
    """
    if (
        ctx.no_library
        or ctx.rows is not None
        or document.payload is None
        or not ctx.execution_started
    ):
        return
    choice = library_choice(ctx)
    prior = ctx.library_outcome
    if prior is not None and (prior.result or prior.status == "failed"):
        return
    from decoy.cli.library import store_run_result

    label = library_label(ctx.config)
    outcome = (
        store_run_result(
            document.payload,
            root=choice.root,
            label=label,
            invocation_id=ctx.invocation_id,
            prior=prior,
        )
        if isinstance(label, str)
        else label
    )
    ctx.library_outcome = outcome
    # Not gated on --quiet: a warning about a lost record is not chatter.
    if outcome.status == "failed":
        ctx.state.err_console.print(
            warn("warning:"),
            f"{outcome.code}: the run's result record was not stored in the library",
            markup=False,
        )


def _write_file(ctx: RunContext, document: Document) -> Document:
    """Write the document to `--result` and return it with `result_status.file` filled.

    The one writer of the file: `emit` and `report_error` call it before the envelope is
    written, so the envelope can say whether the file landed. The path goes through the
    placement rules first, then `write_local_target` (replace, atomic). A failure is one stderr
    line with the code and no path, and never changes the exit integer.
    """
    _store_record(ctx, document)
    if ctx.result is None:
        return document
    status = dict(document.status)
    code = None
    if document.payload is None:
        code = status["code"]
    elif (refused := _placement_refused(ctx)) is not None:
        code = refused
    else:
        try:
            body = json.dumps(document.payload, indent=2).encode("utf-8")
            write_local_target(ctx.result, body, WriteMode.REPLACE)
        except (AtomicWriteError, OSError) as exc:
            code = describe(exc) if isinstance(exc, AtomicWriteError) else type(exc).__name__
    if code is None:
        status["file"] = "written"
        if ctx.state.mode is OutputMode.default:
            ctx.state.console.print("Result:", str(ctx.result), markup=False)
    else:
        status["file"] = "failed"
        if document.payload is not None:
            status["code"] = "run_result_write_failed"
            if ctx.state.mode is not OutputMode.quiet:
                ctx.state.err_console.print(
                    warn("warning:"), f"run_result_write_failed ({code})", markup=False
                )
    return replace(document, status=status)


def members(document: Document) -> dict:
    """The `--json` members the document adds to an envelope: `result` (when built) and
    `result_status`."""
    added: dict = {} if document.payload is None else {"result": document.payload}
    added["result_status"] = document.status
    return added


def emit(ctx: RunContext, document: Document, payload: dict | None) -> None:
    """Write the run's one `--json` envelope: `payload` with the document's members added.

    A no-op outside `--json` and when `payload` is None. This and `finish` are the only places
    under `cli/run/` that write the envelope or end the process (G-RUN-ONE-EXIT).
    """
    document = _write_file(ctx, document)
    if payload is not None:
        if ctx.library_outcome is not None and "library" in payload:
            payload = {**payload, "library": ctx.library_outcome.to_json()}
        emit_json(ctx.state, {**payload, **members(document)})


def finish(ctx: RunContext, document: Document, payload: dict | None = None) -> None:
    """Write the envelope, then end the run with the document's exit integer when it is not 0.

    Every exit of `decoy run` that has a document comes through here, so the integer in the
    document is the integer of the process.
    """
    emit(ctx, document, payload)
    if document.exit_code != 0:
        raise typer.Exit(code=document.exit_code)


def report_error(
    ctx: RunContext,
    document: Document,
    text: str,
    *,
    code: str | None = None,
    context: dict | None = None,
    human: bool = True,
    stderr_line: bool = False,
) -> None:
    """Write a run that ended outside the error arm, through the one error emitter.

    `--json`: the `decoy-error-v1` object with `context` and the document's members added.
    Other modes: the one stderr line, unless `human` is False (Click or the interrupt prints
    its own). `stderr_line` keeps the stderr line under `--json` too, for a run whose outputs
    are already written. Does not end the run; `finish_error` does.
    """
    document = _write_file(ctx, document)
    if ctx.state.mode is OutputMode.json:
        if stderr_line:
            # The same emitter in its human form: one `error:` line on stderr, then the envelope.
            emit_error(replace(ctx.state, mode=OutputMode.default), "run", text, code=code)
        emit_error(
            ctx.state, "run", text, code=code, context={**(context or {}), **members(document)}
        )
    elif human:
        emit_error(ctx.state, "run", text, code=code)


def finish_error(ctx: RunContext, document: Document, text: str, **kwargs: Any) -> None:
    """`report_error`, then the exit of the document."""
    report_error(ctx, document, text, **kwargs)
    raise typer.Exit(code=document.exit_code)
