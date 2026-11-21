"""`decoy run --sample N`: the config, the placement and the scratch folder of a sample.

A sample masks a head slice of the sources into a private scratch folder and writes nothing else
(plan 4.4). This module owns the three decisions that keep it there:

- `sample_config` renames every output to one relative file name, so nothing a pipeline declares
  (a path, a database, a bucket) is read back or reached;
- `sample_placement` and `open_sample_layout` put those names in the scratch folder, through the
  one `OutputPlacement.fixed` and `RunLayout.out_dir` that `--out-dir` uses;
- `require_project` and `open_scratch` find the project and take the scratch folder from its
  library, never from `open_run_layout`, so no claim, `out/<name>/`, `LATEST` or `current`.

Row choice stays in the engine: `subset.sample_request` is the only builder of a sample request.
Messages name flags, tables and codes, never a value.
"""

from __future__ import annotations

import contextlib
import copy
from datetime import timedelta
from pathlib import Path

from decoy.cli.io import (
    OUTPUT_PATH_ESCAPES,
    PROJECT_NOT_FOUND,
    TARGET_SUFFIX,
    LayoutError,
    OutputPlacement,
    RunLayout,
    explicit_project,
    find_project,
    is_portable_component,
    quarantine_enabled,
    sample_target_format,
)
from decoy.cli.run._context import RunContext, UsageRefusal
from decoy.ui.output import OutputMode
from decoy.ui.theme import warn

SCRATCH_OWNER = "sample"  # the library scratch owner; the folder is `sample-<invocation id>`
SCRATCH_TTL = timedelta(hours=24)
QUARANTINE_FILE = "quarantine.jsonl"
_SAMPLE_BASE = "the sample folder"
_NOT_READY = "--sample is not available yet. Run the pipeline without --sample."


def sample_config(config_dict: dict) -> dict:
    """A copy of `config_dict` whose every output is one relative file name in the scratch folder.

    A table with a target gets `<table>.csv` for a csv file target, `<table>.parquet` for a
    parquet one, `<table>.txt` (and its layout) for fixed width, and `<table>.parquet` for every
    database and cloud target. An enabled quarantine block gets `quarantine.jsonl`. Declared
    paths are never read back. A file target with an unsupported format raises `TargetFormatError`
    (`target_format_unknown`), as the gate does. Raises `LayoutError` (`layout.output_path_escapes`) for a table
    name that is not one path component, judged before the suffix is added, since `..` plus a
    suffix would pass. Case-folded twins are the gate's collision rule, not repeated here.
    """
    config = copy.deepcopy(config_dict)
    targets = config.get("targets")
    if isinstance(targets, dict):
        for table in targets:
            if not is_portable_component(table):
                raise OUTPUT_PATH_ESCAPES.error(path=f"the table name {table!r}", base=_SAMPLE_BASE)
        config["targets"] = {table: _sample_target(table, spec) for table, spec in targets.items()}
    if quarantine_enabled(config):
        config["quarantine"]["output_path"] = QUARANTINE_FILE
    return config


def _sample_target(table: str, spec: object) -> dict:
    """The file target that stands in for one declared target."""
    declared = spec if isinstance(spec, dict) else {}
    fmt = sample_target_format(table, declared)
    target: dict = {"type": "file", "format": fmt, "path": f"{table}{TARGET_SUFFIX[fmt]}"}
    if fmt == "fixed_width":
        target["layout"] = copy.deepcopy(declared.get("layout"))
    return target


def sample_placement(scratch: Path, typed: tuple[tuple[str, Path], ...] = ()) -> OutputPlacement:
    """The gate's placement for a sample: the scratch folder, as `--out-dir` is placed."""
    return OutputPlacement.fixed(scratch, typed)


def open_sample_layout(scratch: Path) -> RunLayout:
    """The run layout for a sample: the scratch folder stands in for the run folder."""
    return RunLayout.out_dir(scratch)


def require_project(ctx: RunContext) -> None:
    """Find the project of the pipeline, or refuse with `layout.project_not_found` (exit 1).

    A sample keeps its rows in the project's library, so a folder with no Decoy project marker
    (`Project.implicit`) has nowhere to put them. Runs before any scratch folder or engine call.
    """
    failure: LayoutError | None = None
    project = None
    try:
        project = find_project(ctx.config.resolve().parent, explicit_project(ctx.cli))
    except LayoutError as exc:
        failure = exc
    if failure is None and project is not None and project.implicit:
        failure = PROJECT_NOT_FOUND.error(where="the pipeline's folder")
    if failure is not None:
        raise UsageRefusal(failure.message, code=failure.code)
    ctx._sample_project = project


def open_scratch(ctx: RunContext, scopes: contextlib.ExitStack) -> None:
    """Take this run's scratch folder from the project library and point the layout at it.

    The folder is kept 24 hours (`decoy library clean` is the reaper until the sample record
    lands) and `discard_scratch` removes it on any failure. Raises `LibraryError`.
    """
    from decoy.cli.library import open_library, resolve_project_root

    root = resolve_project_root(ctx._sample_project.root).path
    library = open_library(root)
    allocation = scopes.enter_context(
        library.scratch(SCRATCH_OWNER, ctx.invocation_id, ttl=SCRATCH_TTL)
    )
    ctx._library, ctx._scratch = library, allocation.path
    ctx.layout = open_sample_layout(allocation.path)


def discard_scratch(ctx: RunContext) -> None:
    """Delete this run's scratch folder, best effort; a no-op when none was taken."""
    if ctx._library is not None and ctx._scratch is not None:
        report = ctx._library.delete_scratch(ctx._scratch)
        ctx._scratch = None
        if report.skipped:
            if ctx.state.mode is not OutputMode.quiet:
                ctx.state.err_console.print(
                    warn("warning:"),
                    f"{len(report.skipped)} file(s) of the sample folder could not be removed "
                    "and stay until `decoy library clean` ({code})".format(code=report.code),
                    markup=False,
                )


def begin(ctx: RunContext, scopes: contextlib.ExitStack) -> None:
    """The sample branch of `_flow`: the scratch folder, then (until SC2) a refusal.

    The run itself lands in SAMPLE SC2. Until then a sample that got this far stops here, so no
    run can write a declared target by mistake; `_flow` deletes the scratch folder.
    """
    open_scratch(ctx, scopes)
    raise UsageRefusal(_NOT_READY)
