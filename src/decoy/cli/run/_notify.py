"""`decoy run` side channels that must never change the run: `--notify` and telemetry."""

import os

import typer

from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.extras import MissingExtraError, translate_missing_extra
from decoy.cli.run._context import RunContext
from decoy.ui.output import OutputMode, emit_json
from decoy.ui.theme import error, warn


class _OtelSettingsUsageError(Exception):
    """A refused --otel-endpoint / DECOY_OTEL_* setting; user error (exits EXIT_USAGE)."""


def _start_telemetry(flag_endpoint: str | None, state):
    """Build the trace exporter when --otel-endpoint or DECOY_OTEL_ENDPOINT asks for it.

    Neither set: `opentelemetry` is never imported, whatever `OTEL_*` holds. The flag
    without the `[otel]` extra raises into run's missing-extra arm; the env var alone
    only warns, so an exported variable cannot fail unrelated runs.
    """
    if flag_endpoint is not None:
        # An empty flag is refused, not read as "unset": falling through would export
        # to DECOY_OTEL_ENDPOINT while the operator believed the flag chose the target.
        if not flag_endpoint.strip():
            raise _OtelSettingsUsageError("--otel-endpoint is empty; give an OTLP/HTTP traces URL")
        endpoint = flag_endpoint
    else:
        endpoint = os.environ.get("DECOY_OTEL_ENDPOINT")
        if not endpoint:
            return None
    try:
        from decoy import telemetry
    except ModuleNotFoundError as exc:
        if translate_missing_extra(exc) is None:
            raise
        if flag_endpoint is not None:
            # Own wording: the shared extras message says "this pipeline needs", but
            # here the trigger was the flag, not the pipeline.
            raise MissingExtraError(
                "--otel-endpoint needs the otel extra, which is not installed. "
                "Add it with:  pip install decoy-cli[otel]",
                extra="otel",
            ) from None
        if state.mode is not OutputMode.quiet:
            state.err_console.print(
                warn("warning:"),
                "DECOY_OTEL_ENDPOINT is set but the otel extra is not installed, so traces "
                "are off. Add it with:  pip install decoy-cli[otel]",
                markup=False,
            )
        return None
    try:
        return telemetry.configure(
            endpoint,
            os.environ.get("DECOY_OTEL_HEADERS"),
            endpoint_setting="--otel-endpoint" if flag_endpoint else "DECOY_OTEL_ENDPOINT",
        )
    except telemetry.OtelSettingsError as exc:
        # The message names the setting only; drop the chain so no value rides along.
        raise _OtelSettingsUsageError(str(exc)) from None


def _begin_trace(otel):
    """Open the `decoy.run` root span and its phase recorder; None when telemetry is off or
    the tracer fails. Telemetry never changes the run, so any failure here is swallowed."""
    if otel is None:
        return None
    try:
        from decoy import telemetry

        return telemetry.RunTrace(otel)
    except Exception:
        return None


def _end_trace(otel, trace, *, ok: bool, error_class: str | None = None) -> None:
    """Close the recorder, end the root and flush within the bounded budget. Runs on every
    exit path after the exit code is decided, and can never raise into it."""
    if otel is None:
        return
    try:
        from decoy import telemetry

        try:
            if trace is not None:
                trace.finish(ok=ok, error_class=error_class)
        finally:
            telemetry.flush_bounded(otel)
    except Exception:
        pass


def parse_channels(ctx: RunContext) -> None:
    """Parse the `--notify` specs into `ctx.notify_channels`; a bad spec exits EXIT_USAGE."""
    # Parse --notify specs BEFORE the run (D3): a bad spec is a usage error
    # the user can fix, never a run failure. Notification is a side effect
    # appended after the run reaches its terminal state; it must never
    # change what the run itself does.
    ctx.notify_channels = []
    if ctx.notify:
        from decoy.notify import NotifySpecError, parse_notify_spec

        try:
            ctx.notify_channels = [parse_notify_spec(spec) for spec in ctx.notify]
        except NotifySpecError as exc:
            msg = str(exc)
            if ctx.state.mode is OutputMode.json:
                emit_json(
                    ctx.state,
                    {"command": "run", "status": "error", "config": ctx.config_str, "error": msg},
                )
            elif ctx.state.mode is not OutputMode.quiet:
                # The message quotes the user's spec: print it verbatim (no markup) and
                # unfolded, like the run error prints below.
                ctx.state.err_console.print(error("error:"), msg, markup=False)
            raise typer.Exit(code=EXIT_USAGE)


def _dispatch_run_notifications(
    channels: list,
    *,
    notify_on: str,
    status: str,
    config_path: str,
    row_count: int | None,
    started_at,
    finished_at,
    error_summary: str | None,
    state,
) -> list[dict]:
    """Best-effort post-run notification fan-out (N3).

    Called AFTER the run reaches its terminal state (both the success tail
    and the failure tail call this). Never raises and never changes the
    run's own exit code: a channel failure only logs a stderr warning and
    is reflected in the returned per-channel results (D2 -- "alerting must
    never take a job down", mirrors dispatcher.py:14-17). Returns `[]`
    when no --notify channels were configured, or when --notify-on filters
    out this outcome.
    """
    if not channels:
        return []

    from decoy.notify import SmtpConfig, build_run_event, dispatch, should_notify

    if not should_notify(notify_on, status):
        return []

    try:
        event = build_run_event(
            status=status,
            config_path=config_path,
            row_count=row_count,
            started_at=started_at,
            finished_at=finished_at,
            error_summary=error_summary,
        )
        webhook_secret = os.environ.get("DECOY_NOTIFY_WEBHOOK_SECRET")
        smtp = SmtpConfig(
            host=os.environ.get("DECOY_NOTIFY_SMTP_HOST", ""),
            port=int(os.environ.get("DECOY_NOTIFY_SMTP_PORT") or 587),
            user=os.environ.get("DECOY_NOTIFY_SMTP_USER") or None,
            password=os.environ.get("DECOY_NOTIFY_SMTP_PASS") or None,
            from_addr=os.environ.get("DECOY_NOTIFY_SMTP_FROM") or None,
        )
        results = dispatch(event, channels, webhook_secret=webhook_secret, smtp=smtp)
        if state.mode is not OutputMode.quiet:
            for r in results:
                if not r.delivered:
                    detail = f": {r.detail}" if r.detail else "."
                    state.err_console.print(
                        warn("warning:"),
                        f"notify {r.kind} to {r.target_host} did not deliver{detail}",
                        markup=False,
                    )
        return [
            {"kind": r.kind, "delivered": r.delivered, "target_host": r.target_host}
            for r in results
        ]
    except Exception as exc:  # notify must never take the run down (D2)
        if state.mode is not OutputMode.quiet:
            state.err_console.print(
                warn("warning:"), f"notify dispatch failed: {exc}", markup=False
            )
        return []
