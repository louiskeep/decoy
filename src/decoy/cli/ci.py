"""`decoy ci check`: the Typer surface and file I/O for the CI integration layer.

All behavior lives in `decoy.ci`; this module parses flags, loads the manifest, writes the
one report (stdout or an atomic file), and sets the exit integer. It never uploads,
comments, or touches the network.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from enum import Enum
from pathlib import Path

import typer

from decoy import __version__
from decoy.ci import reporting
from decoy.ci.contracts import NOTE_TEXTS, SafeCiReport
from decoy.ci.debug import DebugSink
from decoy.ci.manifest import ManifestError, load_manifest
from decoy.ci.runner import (
    PRECOMMIT_NOTE,
    Context,
    manifest_refusal,
    run_checks,
    unexpected_failure_report,
)
from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import setup_output

ci_app = typer.Typer(
    name="ci",
    help="CI integration: portable checks, SARIF, and pre-commit.",
    no_args_is_help=True,
    add_completion=False,
)

DEFAULT_MANIFEST = ".decoy-ci.yaml"

CHECK_EPILOG = """\
Examples:

  decoy ci check

    Run the checks in ./.decoy-ci.yaml and print one JSON report.

  decoy ci check .decoy-ci.yaml --format sarif --output decoy.sarif

    Write a SARIF 2.1.0 log for a code-scanning upload step you configure.

  decoy ci check --context pre-commit --format markdown

    What the pre-commit hook runs (config-only validation plus the staged scan).

Exit codes: 0 clean; 1 invalid input or validation errors; 2 blocking warnings;
3 runtime failure; 4 findings; 5 capacity refusal. See docs/ci-contracts.md.
Decoy never uploads or comments; uploads belong to your CI workflow.
"""


class ReportFormat(str, Enum):
    json = "json"
    sarif = "sarif"
    markdown = "markdown"


def _render(report: SafeCiReport, fmt: ReportFormat) -> str:
    if fmt is ReportFormat.sarif:
        return reporting.render_sarif(report, tool_version=__version__)
    if fmt is ReportFormat.markdown:
        return reporting.render_markdown(report)
    return reporting.render_json(report)


def _refuse(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code=EXIT_USAGE)


def _safe_target(raw: str, root: Path) -> Path:
    """A regular-file target inside `root`; refuses symlinks and escapes."""
    target = Path(raw)
    if not target.is_absolute():
        target = Path.cwd() / target
    # Containment is judged on the parent so a not-yet-existing file is allowed, and the
    # target itself must not be a symlink even when it points inside the root.
    parent = target.parent.resolve()
    try:
        parent.relative_to(root)
    except ValueError:
        raise _refuse("an output path must be inside the repository") from None
    if not parent.is_dir():
        raise _refuse("the output directory does not exist")
    final = parent / target.name
    if final.is_symlink() or (final.exists() and not final.is_file()):
        raise _refuse("an output path must be a regular file, not a symlink")
    return final


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".decoy-ci-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@ci_app.command(name="check", epilog=CHECK_EPILOG)
def check(
    manifest: Path = typer.Argument(
        Path(DEFAULT_MANIFEST),
        help="Path to the decoy-ci/v1 manifest (YAML or JSON). No manifest search is done.",
    ),
    format_: ReportFormat = typer.Option(
        ReportFormat.json,
        "--format",
        help="Report format: json (decoy-ci-report/v1), sarif (2.1.0), or markdown.",
    ),
    output: str = typer.Option(
        "-",
        "--output",
        "-o",
        help="Write the report to this file inside the repository, or `-` for stdout.",
    ),
    context: Context = typer.Option(
        Context.ci,
        "--context",
        help="`pre-commit` narrows to config-only validation plus the staged scan.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stderr notes and summary."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print one value-free line per check on stderr."
    ),
    unsafe_debug_log: Path | None = typer.Option(
        None,
        "--unsafe-debug-log",
        hidden=True,
        help="Write raw diagnostic text (may contain secrets) to this file. Never share it.",
    ),
) -> None:
    """Run the checks in a decoy-ci/v1 manifest and emit ONE value-free report.

    Wraps `decoy validate`, saved-scan drift, evidence verification, and a bounded
    staged-file literal scan. Findings carry rule ids, severities, fixed text, and
    repository-relative locations only. Exits with the existing Decoy exit integers.
    """
    setup_output(False, quiet, verbose)
    to_stdout = output == "-"

    deferred: list[str] = []
    loaded = None
    try:
        loaded = load_manifest(manifest)
    except ManifestError as err:
        report = manifest_refusal(err)
    except Exception:
        # Nothing may escape as a traceback (Typer prints locals): the report is the output.
        report = unexpected_failure_report()
        deferred.append(traceback.format_exc())
    root = loaded.root if loaded else Path.cwd().resolve()

    sink_path: Path | None = None
    if unsafe_debug_log is not None:
        if str(unsafe_debug_log) == "-":
            raise _refuse("the debug log must be a file, never stdout")
        sink_path = _safe_target(str(unsafe_debug_log), root)
    out_path = None if to_stdout else _safe_target(output, root)
    if sink_path is not None and out_path is not None and sink_path == out_path:
        raise _refuse("the debug log must not be the report path")
    sink = DebugSink(sink_path)
    for trace in deferred:
        sink.add("manifest-load", trace)

    if loaded is not None:
        try:
            report = run_checks(loaded, context, sink)
        except Exception:
            sink.add_exception("runner")
            report = unexpected_failure_report()

    text = _render(report, format_)
    if out_path is None:
        sys.stdout.write(text)
        sys.stdout.flush()
    else:
        try:
            _write_atomic(out_path, text)
        except OSError:
            typer.echo("error: could not write the report.", err=True)
            raise typer.Exit(code=EXIT_RUNTIME) from None

    if sink.enabled:
        try:
            sink.flush()
        except OSError:
            typer.echo("error: could not write the debug log.", err=True)
        typer.echo(
            "warning: an UNSAFE debug log was written; it may contain secrets or sample "
            "values. Do not share, parse, or upload it.",
            err=True,
        )

    if not quiet:
        machine_on_stdout = to_stdout and format_ in (ReportFormat.json, ReportFormat.sarif)
        if PRECOMMIT_NOTE in report.notes and not machine_on_stdout:
            typer.echo(NOTE_TEXTS[PRECOMMIT_NOTE], err=True)
        if verbose:
            for c in report.checks:
                reason = f" reason={c.reason_code}" if c.reason_code else ""
                typer.echo(f"check {c.id}: {c.status}{reason} findings={c.finding_count}", err=True)
        if not to_stdout:
            typer.echo(
                f"decoy ci check: status={report.status} exit={report.exit_code} "
                f"checks={len(report.checks)} findings={len(report.findings)}",
                err=True,
            )

    if report.exit_code != EXIT_OK:
        raise typer.Exit(code=report.exit_code)
