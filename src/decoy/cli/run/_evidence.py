"""The evidence manifest of `decoy run`: the `--evidence-out` file and the library record."""

import json as _json
from pathlib import Path

from rich.text import Text

from decoy._atomic import AtomicWriteError, WriteMode, describe, write_local_target
from decoy._version import __version__ as _cli_version
from decoy.cli.io import LayoutError, find_project
from decoy.cli.run._context import EvidenceWriteRefusal, RunContext, library_choice, library_label
from decoy.ui.output import OutputMode
from decoy.ui.theme import warn


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
    """Build the manifest once; write it to `--evidence-out` and store it in the record library.

    A failed `--evidence-out` write raises EvidenceWriteRefusal. The library store (on by default,
    plan 4.16) never changes the exit code: a failure is one stderr warning with its code (4.17).
    """
    # Chunked runs have no row_counts/timings/warnings (see the --evidence-out help).
    # A --duckdb-source input is a transient snapshot with no defined fingerprint, so such a run
    # stores no evidence record (and refuses --evidence-out before it starts).
    store = not ctx.no_library and not ctx.duckdb_source
    if ctx._ev_config_dict is None or (ctx.evidence_out is None and not store):
        _record_skipped(ctx)
        return
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
        evidence_path=ctx.evidence_out,
        timings=ctx._ev_timings,
        engine_warnings=ctx._ev_engine_warnings,
    )
    if ctx.evidence_out is not None:
        failed = None
        try:
            write_local_target(
                ctx.evidence_out, _json.dumps(manifest, indent=2).encode("utf-8"), WriteMode.REPLACE
            )
        except AtomicWriteError as exc:
            failed = describe(exc)
        if failed is not None:
            # Outside the block: the refusal has no context. `_errors.refused` prints and exits.
            raise EvidenceWriteRefusal(failed)
        if ctx.state.mode is not OutputMode.json and ctx.state.mode is not OutputMode.quiet:
            from decoy.ui.theme import success as _success

            ctx.state.console.print(_success("Evidence:"), str(ctx.evidence_out))
    from decoy.cli.library import store_evidence

    choice = library_choice(ctx)
    if choice.code is not None:
        return  # the root fault was warned about once, where it was found
    label = library_label(ctx.config)
    ctx.library_outcome = (
        store_evidence(
            manifest,
            root=choice.root,
            label=label,
            invocation_id=ctx.invocation_id,
            enabled=store,
        )
        if isinstance(label, str)
        else label
    )
    # Not gated on --quiet: a warning about a lost record is not chatter.
    if ctx.library_outcome.status == "failed":
        ctx.state.err_console.print(
            warn("warning:"),
            Text(
                f"{ctx.library_outcome.code}: the run's evidence record was not stored in the "
                "library; the run's result is unchanged."
            ),
        )


def _record_skipped(ctx: RunContext) -> None:
    from decoy.cli.library import StoreOutcome

    if ctx.library_outcome is None or ctx.library_outcome.status != "failed":
        ctx.library_outcome = StoreOutcome("skipped")
