"""Run folders under `<project>/out/<name>/<run-id>/`: the run-id rule and path placement.

One place owns what a run id looks like (`is_run_id`), how a file is matched to the run
folder that holds it (`owning_run`), and how a declared relative path is placed inside a
run folder (`placed_path`). Writers and readers both go through these.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from decoy_engine import is_valid_pipeline_name

from decoy._atomic import AtomicWriteError, WriteMode, write_atomic, write_local_target
from decoy._private_file import PRIVATE_EXISTS, PrivateFileError, create_private_directory
from decoy.cli.io._layout_errors import (
    GITIGNORE_WRITE_FAILED,
    OUTPUT_PATH_ESCAPES,
    PATH_TOO_LONG,
    PIPELINE_NAME_COLLISION,
    PIPELINE_NAME_INVALID,
    PIPELINE_NAME_MISMATCH,
    LayoutWarning,
)

# <UTC start YYYYMMDDTHHMMSSffffffZ>-<8 hex of the invocation id>, plus 4 more hex digits per
# clash, up to all 32.
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}(?:[0-9a-f]{4}){0,6}")


MAX_RUN_ID_LENGTH = 55
WINDOWS_PATH_LIMIT = 259
_CLAIM_NAME = "PIPELINE"
_CLAIM_MAX_BYTES = 4096
_SLUG_MAX = 56
_SLUG_BAD = re.compile(r"[^A-Za-z0-9_.-]+")
_DASH_RUNS = re.compile(r"-{2,}")


def is_run_id(value: str) -> bool:
    """True when `value` is a well-formed run folder name."""
    return _RUN_ID.fullmatch(value) is not None


@dataclass(frozen=True)
class RunFolder:
    """A run folder `<root>/out/<name>/<run-id>/`, fully resolved."""

    path: Path
    run_id: str


def same_path(a: Path, b: Path) -> bool:
    """True when both paths name one file: by identity when both exist, else by resolved text.

    Identity, not spelling, so a case-insensitive filesystem or a second path to the same
    directory does not split one file in two. Unresolvable paths (a loop, an I/O error) are
    never the same.
    """
    try:
        return os.path.samefile(a, b)
    except OSError:
        pass
    try:
        return a.resolve() == b.resolve()
    except (OSError, RuntimeError):
        return False


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def owning_run(path: Path, root: Path, name: str) -> RunFolder | None:
    """The run folder of pipeline `name` in project `root` that holds `path`, else None.

    `path` is resolved first, so a `latest` link is followed and a link that leaves the run
    folder is judged by where it lands. A run folder is found by identity: the ancestor of
    the file whose parent is the pipeline folder. The run folder itself holds no file and
    gives None. An unresolvable path gives None.
    """
    try:
        base = (root / "out" / name).resolve()
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None
    for ancestor in resolved.parents:
        if _same_dir(ancestor.parent, base):
            if not is_run_id(ancestor.name):
                return None
            return RunFolder(base / ancestor.name, ancestor.name)
    return None


def placed_path(run: RunFolder, raw: str) -> Path | None:
    """`raw` placed inside `run` and resolved, or None when it does not stay inside.

    Refused: any backslash (a declared path uses "/" only, so it means the same on every
    OS), an anchor or drive (`/x`, `C:x`, `//host/share/x`), a trailing separator (a
    directory, not a file), a `..` that climbs above the run at any step (even to come back
    in), and a result that lands outside the run through an existing symlink. Containment is
    by file identity, so another spelling of the run folder still counts. The result is
    resolved, so it compares with a resolved input path. A path that cannot be resolved
    gives None.
    """
    if not raw or "\\" in raw or raw.endswith("/"):
        return None
    for style in (PurePosixPath, PureWindowsPath):
        pure = style(raw)
        if pure.anchor or pure.drive:
            return None
    depth = 0
    for part in PurePosixPath(raw).parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return None
        elif part != ".":
            depth += 1
    if depth == 0:
        return None
    try:
        resolved = Path(os.path.normpath(run.path / raw)).resolve()
    except (OSError, RuntimeError):
        return None
    if any(_same_dir(ancestor, run.path) for ancestor in resolved.parents):
        return resolved
    return None


def _on_windows() -> bool:
    return os.name == "nt"


def _inside(child: Path, parent: Path) -> bool:
    return any(_same_dir(ancestor, parent) for ancestor in (child, *child.parents))


def check_path_budget(name_dir: Path, rel: str) -> None:
    """Refuse on Windows a placed path that can pass 259 characters with the longest run id.

    `name_dir` is `<root>/out/<name>`; the run id is counted at its maximum length so a path
    that fits today does not fail on a run-id clash later. POSIX has no such limit here.
    Raises `LayoutError`.
    """
    if not _on_windows():
        return
    length = len(str(name_dir)) + 1 + MAX_RUN_ID_LENGTH + 1 + len(rel)
    if length > WINDOWS_PATH_LIMIT:
        raise PATH_TOO_LONG.error(length=length, limit=WINDOWS_PATH_LIMIT)


# --- the out/ folder ---------------------------------------------------------------------


def prepare_out(root: Path) -> tuple[Path, tuple[LayoutWarning, ...]]:
    """`<root>/out/` made, kept inside the project, with its `.gitignore` holding `*`.

    Returns the physical folder. An `out` that is a link leaving the project is refused. A
    `.gitignore` that already exists is kept; one that cannot be written is a warning.
    Raises `LayoutError`, or `OSError` when `out/` cannot be made.
    """
    out = root / "out"
    out.mkdir(exist_ok=True)
    physical = out.resolve()
    if not _inside(physical, root.resolve()) or _same_dir(physical, root):
        raise OUTPUT_PATH_ESCAPES.error(path=out, base=root)
    target = physical / ".gitignore"
    failed = False
    try:
        write_local_target(target, b"*\n", WriteMode.CREATE_ONCE)
    except AtomicWriteError:
        failed = True
    if failed:
        return physical, (GITIGNORE_WRITE_FAILED.warning(path=target),)
    return physical, ()


# --- pipeline names and claims -----------------------------------------------------------


@dataclass(frozen=True)
class PipelineName:
    """The folder name `out/<name>/` for a pipeline YAML, and how firm it is.

    A `firm` name (the `pipelines/<dir>/` folder or a declared `name:`) refuses on a clash; a
    derived one takes a path-hash suffix instead. `yaml_rel` is the YAML's path from the project
    root in POSIX form, the text the claim file holds.
    """

    name: str
    firm: bool
    yaml_rel: str


def _rel_posix(root: Path, yaml: Path) -> str:
    resolved = yaml.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _slug(stem: str) -> str:
    slug = _DASH_RUNS.sub("-", _SLUG_BAD.sub("-", stem))
    slug = slug.lstrip("-._")[:_SLUG_MAX]
    return slug.rstrip("-.")


def _derived(root: Path, yaml_rel: str, stem: str) -> str:
    digest = hashlib.sha256(yaml_rel.encode()).hexdigest()[:6]
    slug = _slug(stem)
    for base in (slug or "pipeline", "pipeline"):
        candidate = f"{base}-{digest}"
        if is_valid_pipeline_name(candidate):
            return candidate
    return f"pipeline-{digest}"


def read_claim(out: Path, name: str) -> str | None:
    """The YAML path `out/<name>/PIPELINE` names, or None when there is no claim."""
    try:
        with open(out / name / _CLAIM_NAME, "rb") as handle:
            raw = handle.read(_CLAIM_MAX_BYTES)
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace").strip() or None


def _taken(root: Path, name: str, yaml_rel: str) -> str | None:
    """The other YAML that holds `name`: by claim, or by a `pipelines/<name>/` folder."""
    claimed = read_claim(root / "out", name)
    if claimed is not None and claimed != yaml_rel:
        return claimed
    member = f"pipelines/{name}/pipeline.yaml"
    if (root / "pipelines" / name).exists() and member != yaml_rel:
        return member
    return None


def pipeline_name_for(root: Path, yaml: Path, declared: object) -> PipelineName:
    """The name a pipeline YAML runs under (plan 3.5), checking claims read-only.

    1. `<root>/pipelines/<dir>/pipeline.yaml` is named `<dir>`; the folder must pass the engine's
       name rule and a differing `name:` is refused.
    2. Any other YAML with `name:` takes it; an invalid or already-held name is refused.
    3. Otherwise the file stem is slugged; a changed, empty, reserved or held slug gets
       `-<6 hex of sha256(root-relative path)>` and never refuses.

    Raises `LayoutError`.
    """
    yaml_rel = _rel_posix(root, yaml)
    parts = yaml_rel.split("/")
    if len(parts) == 3 and parts[0] == "pipelines" and parts[2] == "pipeline.yaml":
        folder = parts[1]
        if not is_valid_pipeline_name(folder):
            raise PIPELINE_NAME_INVALID.error(name=folder)
        if declared is not None and declared != folder:
            raise PIPELINE_NAME_MISMATCH.error(path=yaml_rel, declared=declared, folder=folder)
        return PipelineName(folder, True, yaml_rel)
    if declared is not None:
        if not is_valid_pipeline_name(declared):
            raise PIPELINE_NAME_INVALID.error(name=declared)
        assert isinstance(declared, str)
        other = _taken(root, declared, yaml_rel)
        if other is not None:
            raise PIPELINE_NAME_COLLISION.error(
                name=declared, other=other, claim=f"out/{declared}/{_CLAIM_NAME}"
            )
        return PipelineName(declared, True, yaml_rel)
    stem = yaml.name.rsplit(".", 1)[0] if "." in yaml.name else yaml.name
    slug = _slug(stem)
    if slug == stem and is_valid_pipeline_name(slug) and _taken(root, slug, yaml_rel) is None:
        return PipelineName(slug, False, yaml_rel)
    return PipelineName(_derived(root, yaml_rel, stem), False, yaml_rel)


def name_dir(out: Path, name: str) -> Path:
    """`out/<name>/` made and kept inside the physical `out/`. Raises `LayoutError`."""
    folder = out / name
    folder.mkdir(exist_ok=True)
    physical = folder.resolve()
    if not _inside(physical, out) or _same_dir(physical, out):
        raise OUTPUT_PATH_ESCAPES.error(path=folder, base=out)
    return physical


def write_claim(folder: Path, yaml_rel: str) -> str | None:
    """Make sure `<folder>/PIPELINE` names `yaml_rel`; return the other YAML if it names one.

    The first run creates the claim with a hard-linked, fully written temp (`CREATE_ONCE`), so a
    reader never sees an empty claim and two racing first runs leave one winner, which the loser
    reads and compares. Raises `AtomicWriteError` (a mount without hard links is one).
    """
    created = write_atomic(folder, _CLAIM_NAME, f"{yaml_rel}\n".encode(), WriteMode.CREATE_ONCE)
    if created:
        return None
    existing = read_claim(folder.parent, folder.name)
    return None if existing == yaml_rel else (existing or "")


# --- run ids and run folders -------------------------------------------------------------


def new_run_id(started: datetime, invocation_id: str, extra_blocks: int = 0) -> str:
    """`<UTC YYYYMMDDTHHMMSSffffffZ>-<8 hex of the invocation id>`, plus 4 hex per clash.

    `invocation_id` is a UUID in any spelling; at most six extra blocks (all 32 digits).
    """
    stamp = started.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    digits = uuid.UUID(invocation_id).hex
    return f"{stamp}-{digits[: 8 + 4 * extra_blocks]}"


def create_run_folder(folder: Path, started: datetime, invocation_id: str) -> RunFolder:
    """Make `<folder>/<run-id>/` owner-only, taking 4 more id digits on each clash.

    `folder` is the physical `out/<name>/`. The directory is made by the private-directory
    helper (exclusive create, 0700), so an existing run folder is never reused. Raises
    `PrivateFileError`; running out of digits is `private_exists`.
    """
    for blocks in range(7):
        run_id = new_run_id(started, invocation_id, blocks)
        try:
            create_private_directory(folder / run_id)
        except PrivateFileError as exc:
            if exc.code != PRIVATE_EXISTS:
                raise
            continue
        return RunFolder(folder / run_id, run_id)
    raise PrivateFileError(PRIVATE_EXISTS)
