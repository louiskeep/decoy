"""The `--evidence-out` manifest of `decoy run`."""

import json as _json
from pathlib import Path

import typer

from decoy import __version__ as _cli_version
from decoy._atomic import AtomicWriteError, WriteMode, describe, write_local_target
from decoy.cli.exit_codes import EXIT_RUNTIME
from decoy.cli.io import LayoutError, find_project
from decoy.cli.run._context import RunContext
from decoy.ui.output import OutputMode
from decoy.ui.theme import error


def _marked_project_root(config: Path) -> Path | None:
    """The root of the project holding the YAML when it has a marker; None otherwise.

    Paths are recorded project-relative only under a marker, which a verifier can find again
    from the manifest's folder. Without one they are recorded absolute.
    """
    try:
        found = find_project(config.resolve().parent, None)
    except LayoutError:
        return None
    return None if found.implicit else found.root


def write_evidence(ctx: RunContext) -> None:
    """Write the manifest when `--evidence-out` is set; a failed write exits EXIT_RUNTIME."""
    # Evidence manifest (--evidence-out), for plain and chunked runs; chunked runs have
    # no row_counts/timings/warnings (see the flag help).
    if ctx.evidence_out is not None and ctx._ev_config_dict is not None:
        from decoy.cli.evidence import build_manifest

        manifest = build_manifest(
            pipeline_path=ctx.config,
            config_dict=ctx._ev_config_dict,
            run_result={"row_counts": ctx._ev_row_counts or {}},
            cli_version=_cli_version,
            engine_version=ctx._ev_engine_version or "unknown",
            key_label=ctx.key_label,
            run_id=ctx.invocation_id,
            place_target=ctx.layout.place_target if ctx.layout is not None else None,
            project_root=_marked_project_root(ctx.config),
            timings=ctx._ev_timings,
            engine_warnings=ctx._ev_engine_warnings,
        )
        try:
            write_local_target(
                ctx.evidence_out, _json.dumps(manifest, indent=2).encode("utf-8"), WriteMode.REPLACE
            )
        except AtomicWriteError as exc:
            ctx.state.err_console.print(error("error:"), describe(exc), markup=False)
            raise typer.Exit(code=EXIT_RUNTIME)
        if ctx.state.mode is not OutputMode.json and ctx.state.mode is not OutputMode.quiet:
            from decoy.ui.theme import success as _success

            ctx.state.console.print(_success("Evidence:"), str(ctx.evidence_out))
