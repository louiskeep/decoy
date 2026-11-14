"""The one parser and resolver of a pipeline argument: a path, or a name under `pipelines/`.

`parse_pipeline_token` is the Typer callback every pipeline parameter uses (the sentry in
`tests/sentry/io_policy/test_pipeline_argument.py` walks the app and holds the line). It only
classifies the token, so a path-shaped token that does not exist still fails as a Click usage
error (exit 2) as before. `resolve_pipeline` runs first in each command body, after output
setup, so a refusal exits 1 inside the command's own `--json` envelope. It never reads the YAML:
the command does that as it always has.

A name must pass the engine's name rule before it is joined under `<root>/pipelines/`, and the
YAML it finds must stay inside the physical `pipelines/` folder, so neither `..` nor a symlink
reaches a file outside it. The project is `--project`, else `DECOY_PROJECT`, else the walk from
the current folder; `explicit_project` is the only reader of that variable. `DECOY_PROJECT` is
ignored for a path, because it is ambient; `--project` is checked against the path's own project.

Typer vendors Click, so the root `--project` value is read from the context Typer hands a
parameter callback, not from a global.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, overload

import typer

from decoy.cli.completers import pipeline_names
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.io._layout import (
    PIPELINE_YAML,
    PIPELINES_DIR,
    is_run_id,
    is_valid_name,
    member_yaml,
    pipeline_folder,
    project_out_folder,
    read_latest,
    same_path,
)
from decoy.cli.io._layout_errors import (
    LATEST_INVALID,
    PIPELINE_NAME_INVALID,
    PIPELINE_UNKNOWN,
    PROJECT_MISMATCH,
    PROJECT_NOT_FOUND,
    LayoutError,
    LayoutWarning,
)
from decoy.cli.io._project import Project, find_project
from decoy.ui.output import OutputMode, OutputState, emit_json
from decoy.ui.theme import error

_PATH_SUFFIXES = (".yaml", ".yml")


@dataclass(frozen=True)
class PipelineToken:
    """A pipeline argument as typed, classified, with the root `--project` value."""

    raw: str
    kind: str  # "path" or "name"
    project_flag: Path | None = None

    def __str__(self) -> str:
        return self.raw


@dataclass(frozen=True)
class PipelineRef:
    """A resolved pipeline. `project` is None for a path given without `--project`."""

    yaml: Path
    project: Project | None
    name: str | None
    given_as: str


@dataclass(frozen=True)
class PipelineEntry:
    """A member of a project: `pipelines/<name>/pipeline.yaml`."""

    name: str
    yaml: Path


def project_flag(ctx: typer.Context | None) -> Path | None:
    """The root `--project DIR` value, None when it was not given."""
    if ctx is None:
        return None
    value = ctx.find_root().params.get("project")
    return None if value is None else Path(value)


def _env_project() -> Path | None:
    raw = os.environ.get("DECOY_PROJECT", "")
    return Path(raw) if raw.strip() else None


def _select(flag: Path | None) -> Path | None:
    return flag if flag is not None else _env_project()


def explicit_project(ctx: typer.Context | None) -> Path | None:
    """The project named outside the pipeline path: `--project`, else a non-empty `DECOY_PROJECT`.

    None means "walk from the current folder". `find_project` takes this as its `explicit`.
    """
    return _select(project_flag(ctx))


def _looks_like_path(raw: str) -> bool:
    return raw == "-" or "/" in raw or "\\" in raw or raw.lower().endswith(_PATH_SUFFIXES)


def _require_readable_file(raw: str) -> None:
    """Click's `exists`, `dir_okay=False` and `readable` checks, kept for every path token."""
    path = Path(raw)
    if not path.exists():
        reason = "does not exist"
    elif path.is_dir():
        reason = "is a directory"
    elif not os.access(path, os.R_OK):
        reason = "is not readable"
    else:
        return
    raise typer.BadParameter(f"File '{raw}' {reason}.")


def parse_pipeline_token(ctx: typer.Context, value: str | None) -> PipelineToken | None:
    """Classify a pipeline argument. The declared parameter type stays `str`.

    An existing file is a path, even one named like a pipeline. A token with a separator or a
    YAML suffix is a path and must exist (exit 2). Anything else is a name.
    """
    if value is None:
        return None
    flag = project_flag(ctx)
    if _looks_like_path(value) or os.path.isfile(value):
        _require_readable_file(value)
        return PipelineToken(value, "path", flag)
    return PipelineToken(value, "name", flag)


def pipeline_argument(*, help: str, optional: bool = False) -> Any:
    """The `typer.Argument` of a pipeline parameter: the one declaration every command shares.

    `optional` is for `run`, which picks the project's only pipeline when none is given.
    """
    return typer.Argument(
        None if optional else ...,
        callback=parse_pipeline_token,
        autocompletion=pipeline_names,
        help=help,
    )


def pipeline_option(default: Any, *names: str, help: str) -> Any:
    """The `typer.Option` of a pipeline parameter (`--config`), required with `...`."""
    return typer.Option(
        default, *names, callback=parse_pipeline_token, autocompletion=pipeline_names, help=help
    )


def _member(root: Path, name: str) -> Path | None:
    """`<root>/pipelines/<name>/pipeline.yaml` when a regular file, with no link on the way.

    A linked folder or YAML would run under the name of its target (run folder, claim, LATEST),
    so a link is not a member. A failed filesystem probe is not a member; link loops stay safe.
    """
    yaml = member_yaml(root, name)
    try:
        if any(p.is_symlink() for p in (root / PIPELINES_DIR, yaml.parent, yaml)):
            return None
        return yaml if yaml.is_file() else None
    except OSError:
        return None


def list_pipelines(project: Project) -> list[PipelineEntry]:
    """The project's members by name: valid names whose YAML passes the same checks as a lookup."""
    try:
        folders = sorted(os.listdir(project.root / PIPELINES_DIR))
    except OSError:
        return []
    found = ((n, _member(project.root, n)) for n in folders if is_valid_name(n))
    return [PipelineEntry(n, y) for n, y in found if y is not None]


@dataclass(frozen=True)
class RunHistory:
    """The newest run folder and the last clean run of one pipeline, read from `out/<name>/`."""

    last_run: str | None
    last_clean: str | None
    warnings: tuple[LayoutWarning, ...] = ()


def _is_plain_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def _contained_history_folder(root: Path, name: str) -> Path | None:
    """`out/<name>/` when no link is on the way and it lies inside the project, else None.

    A linked `out/` or pipeline folder would report another place's runs as this project's.
    """
    out = project_out_folder(root)
    folder = pipeline_folder(root, name)
    try:
        if out.is_symlink() or folder.is_symlink():
            return None
        return folder if folder.resolve().is_relative_to(root.resolve()) else None
    except (OSError, RuntimeError):
        return None


def run_history(root: Path, name: str) -> RunHistory:
    """Run ids of pipeline `name`: the newest well-formed folder, and `LATEST` when it checks out.

    Folders that are not run ids (or are links) are ignored, and so is a history folder that
    is a link or lies outside the project. A `LATEST` that is not a run id, or names no run
    folder, is ignored with `layout.latest_invalid`. Reads only; nothing is made.
    """
    folder = _contained_history_folder(root, name)
    if folder is None:
        return RunHistory(None, None)
    try:
        found = os.listdir(folder)
    except OSError:
        found = []
    runs = sorted(r for r in found if is_run_id(r) and _is_plain_dir(folder / r))
    latest = read_latest(folder)
    if latest is None or latest in runs:
        return RunHistory(runs[-1] if runs else None, latest)
    return RunHistory(runs[-1] if runs else None, None, (LATEST_INVALID.warning(path=folder),))


def _by_path(token: PipelineToken) -> PipelineRef:
    yaml = Path(token.raw)
    if token.project_flag is None:
        return PipelineRef(yaml, None, None, "path")
    given = find_project(None, token.project_flag)
    walked = find_project(yaml.resolve().parent, None)
    if not same_path(walked.root, given.root):
        raise PROJECT_MISMATCH.error(path=token.raw, actual=walked.root, given=given.root)
    return PipelineRef(yaml, given, None, "path")


def _by_name(token: PipelineToken) -> PipelineRef:
    name = token.raw
    if not is_valid_name(name):
        raise PIPELINE_NAME_INVALID.error(name=name)
    project = find_project(None, _select(token.project_flag))
    if project.implicit:
        raise PROJECT_NOT_FOUND.error(where="the current folder")
    if _member(project.root, name) is None:
        names = [entry.name for entry in list_pipelines(project)]
        close = difflib.get_close_matches(name, names, n=1)
        raise PIPELINE_UNKNOWN.error(
            name=name,
            root=project.root,
            known=", ".join(names) or "none",
            close=f" Did you mean {close[0]}?" if close else "",
        )
    return member_ref(project, name)


def member_ref(project: Project, name: str) -> PipelineRef:
    """The `PipelineRef` of a listed member, after the check that no nested marker moves it.

    Placement walks up from the YAML's folder. A marker or `.git` inside `pipelines/<name>/`
    would put outputs in another project than the one selected, so that is refused here for a
    name given on the command line and for one picked from `list_pipelines` alike.
    """
    yaml = _member(project.root, name)
    if yaml is None:
        raise PIPELINE_UNKNOWN.error(name=name, root=project.root, known="none", close="")
    walked = find_project(yaml.resolve().parent, None)
    if not same_path(walked.root, project.root):
        raise PROJECT_MISMATCH.error(
            path=f"{PIPELINES_DIR}/{name}/{PIPELINE_YAML}", actual=walked.root, given=project.root
        )
    return PipelineRef(yaml, project, name, "name")


@overload
def resolve_pipeline(token: str, state: OutputState, command: str) -> PipelineRef: ...
@overload
def resolve_pipeline(token: str | None, state: OutputState, command: str) -> PipelineRef | None: ...
def resolve_pipeline(token: str | None, state: OutputState, command: str) -> PipelineRef | None:
    """Find the pipeline's YAML (and project) for a parsed token, or exit 1 with a `layout.*` code.

    `token` is what `parse_pipeline_token` returned (typed `str` like the parameter); a plain
    string, as a direct call passes, is taken as a path. `None` passes through.
    """
    if token is None:
        return None
    parsed = token if isinstance(token, PipelineToken) else PipelineToken(str(token), "path")
    try:
        return _by_path(parsed) if parsed.kind == "path" else _by_name(parsed)
    except LayoutError as exc:
        failure = exc
    # Emitted and raised here, outside the handler, so the refusal carries no chained context.
    # This is the one emitter of a pipeline-argument refusal; `command` is a literal at each of
    # the 12 call sites (the forwarder entry in `tests/sentry/cli_text/test_json_command_names.py`).
    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": command,
                "status": "error",
                "config": parsed.raw,
                "code": failure.code,
                "error": failure.message,
            },
        )
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), failure.message, markup=False)
    raise typer.Exit(code=EXIT_USAGE)
