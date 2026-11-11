"""Run folders under `<project>/out/<name>/<run-id>/`: the run-id rule and path placement.

`RunLayout` is the one builder of output paths: it opens the run folder, places each declared
target and quarantine path inside it, and moves `latest` after a clean run. One place owns what
a run id looks like (`is_run_id`), how a file is matched to the run folder that holds it
(`owning_run`), and how a declared relative path is placed inside a run folder (`placed_path`).
Writers and readers both go through these.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from decoy._atomic import (
    AtomicWriteError,
    WriteMode,
    replace_symlink,
    write_atomic,
    write_local_target,
)
from decoy._private_file import PRIVATE_EXISTS, PrivateFileError, create_private_directory
from decoy.cli.io._layout_errors import (
    GITIGNORE_WRITE_FAILED,
    LATEST_INVALID,
    LATEST_LINK_FAILED,
    LATEST_WRITE_FAILED,
    OUTPUT_PATH_ESCAPES,
    PATH_TOO_LONG,
    PIPELINE_NAME_COLLISION,
    PIPELINE_NAME_INVALID,
    PIPELINE_NAME_MISMATCH,
    LayoutWarning,
)
from decoy.cli.io._small_file import UnsafeFileError, read_small_file

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


def _valid_name(name: str) -> bool:
    """The engine's pipeline name rule, imported on use: this package loads on every CLI start."""
    from decoy_engine import is_valid_pipeline_name

    return bool(is_valid_pipeline_name(name))


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


def _utf16_units(text: str) -> int:
    # Windows measures paths in UTF-16 units: a character past U+FFFF counts twice.
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def check_path_budget(name_dir: Path, rel: str) -> None:
    """Refuse on Windows a placed path that can pass 259 characters with the longest run id.

    `name_dir` is `<root>/out/<name>`; the run id is counted at its maximum length so a path
    that fits today does not fail on a run-id clash later. POSIX has no such limit here.
    Raises `LayoutError`.
    """
    if not _on_windows():
        return
    length = _utf16_units(str(name_dir)) + 1 + MAX_RUN_ID_LENGTH + 1 + _utf16_units(rel)
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
        if _valid_name(candidate):
            return candidate
    return f"pipeline-{digest}"


def _read_small(path: Path) -> bytes | None:
    """At most `_CLAIM_MAX_BYTES` of the regular file at `path`, else None.

    None covers a missing or unreadable file and anything that is not a plain regular file, so a
    planted link, pipe or device in a run's bookkeeping files is never read through.
    """
    try:
        found = read_small_file(path, _CLAIM_MAX_BYTES)
    except UnsafeFileError:
        return None
    return found.data if found is not None else None


def read_claim(out: Path, name: str) -> str | None:
    """The YAML path `out/<name>/PIPELINE` names, or None when there is no claim."""
    raw = _read_small(out / name / _CLAIM_NAME) or b""
    # Only the writer's newline goes: spaces are valid at either end of a POSIX path.
    return raw.decode("utf-8", errors="replace").removesuffix("\n") or None


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
        if not _valid_name(folder):
            raise PIPELINE_NAME_INVALID.error(name=folder)
        if declared is not None and declared != folder:
            raise PIPELINE_NAME_MISMATCH.error(path=yaml_rel, declared=declared, folder=folder)
        return PipelineName(folder, True, yaml_rel)
    if declared is not None:
        if not _valid_name(declared):
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
    if slug == stem and _valid_name(slug) and _taken(root, slug, yaml_rel) is None:
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


# --- the run layout ----------------------------------------------------------------------

_LATEST_FILE = "LATEST"
_LATEST_LINK = "latest"


def mint_invocation_id() -> str:
    """A new invocation id (UUID4 text). Called once per command, at its entry.

    The run folder name, the evidence `run_id` and later run records all carry this one value.
    """
    return str(uuid.uuid4())


class RunLayout:
    """Where one command writes its files: a run folder, or a fixed base folder.

    `RunLayout.open` makes `out/<name>/<run-id>/` (claim, `.gitignore`, private folder) and
    `RunLayout.fixed(base)` places relative paths against `base` as the pre-layout code did
    (`demo`, `mask()`): no claim, no run id, no `latest`. `place_target` and
    `place_quarantine` are the only way a command turns a declared path into a file path.
    """

    def __init__(
        self,
        base: Path,
        *,
        run: RunFolder | None = None,
        pipeline_dir: Path | None = None,
        warnings: tuple[LayoutWarning, ...] = (),
    ) -> None:
        self._base = base
        self._run = run
        self._pipeline_dir = pipeline_dir
        self.warnings = warnings

    @classmethod
    def fixed(cls, base: Path) -> RunLayout:
        """A layout with no run folder: relative paths resolve against `base`."""
        return cls(base)

    @classmethod
    def open(
        cls,
        root: Path,
        name: PipelineName,
        invocation_id: str,
        started: datetime | None = None,
    ) -> RunLayout:
        """Make the run folder for pipeline `name` in project `root` (plan 3.6).

        Runs after the gate passes and before the first write: `out/` and its `.gitignore`,
        the claim, then `out/<name>/<run-id>/` (0700). A claim naming another YAML is a
        collision. Raises `LayoutError`, `AtomicWriteError` or `PrivateFileError`.
        """
        out, warnings = prepare_out(root)
        folder = name_dir(out, name.name)
        other = write_claim(folder, name.yaml_rel)
        if other is not None:
            raise PIPELINE_NAME_COLLISION.error(
                name=name.name,
                other=other or "unreadable claim",
                claim=f"out/{name.name}/{_CLAIM_NAME}",
            )
        run = create_run_folder(folder, started or datetime.now(timezone.utc), invocation_id)
        return cls(root, run=run, pipeline_dir=folder, warnings=warnings)

    @property
    def run(self) -> RunFolder | None:
        """The run folder, or None for a fixed layout."""
        return self._run

    @property
    def base(self) -> Path:
        """The folder relative paths resolve against: the run folder, or the fixed base."""
        return self._run.path if self._run is not None else self._base

    def place_target(self, raw: str) -> Path:
        """The file path for a declared target path.

        Absolute paths stay. In a run folder a relative path lands inside it and must name a
        file (`layout.output_path_escapes` otherwise). A fixed layout resolves it against its
        base. Raises `LayoutError`.
        """
        from decoy.cli._sources import resolve_path

        if self._run is None or Path(raw).is_absolute():
            return resolve_path(raw, self._base)
        if self._pipeline_dir is not None:
            check_path_budget(self._pipeline_dir, raw)
        placed = placed_path(self._run, raw)
        if placed is None:
            raise OUTPUT_PATH_ESCAPES.error(path=raw, base=self._run.path)
        return placed

    def place_quarantine(self, config_dict: dict) -> str | None:
        """The `run_pipeline(quarantine_path=...)` value: the placed quarantine file, when on.

        None unless quarantine is enabled and names an output path; the engine then keeps its
        own rule. The engine applies the path after it hashes the config, so the plan hash
        matches the path as declared and the caller's dict is never edited.
        """
        quarantine = config_dict.get("quarantine")
        if not isinstance(quarantine, dict) or not quarantine.get("enabled"):
            return None
        raw = quarantine.get("output_path")
        if not isinstance(raw, str):
            return None
        return str(self.place_target(raw))

    def commit_latest(self) -> tuple[LayoutWarning, ...]:
        """Point `LATEST` and `latest` at this run, after a clean (exit 0) run.

        Moves nothing when `LATEST` already names a later run id. An invalid `LATEST` is
        treated as absent and warned. A failure here never changes the run's outcome: it is
        returned as a warning.
        """
        if self._run is None or self._pipeline_dir is None:
            return ()
        folder, run_id = self._pipeline_dir, self._run.run_id
        warnings: list[LayoutWarning] = []
        current = _read_latest(folder)
        if current is not None and not is_run_id(current):
            warnings.append(LATEST_INVALID.warning(path=folder))
        elif current is not None and current > run_id:
            return ()
        try:
            write_atomic(folder, _LATEST_FILE, f"{run_id}\n".encode(), WriteMode.REPLACE)
        except AtomicWriteError:
            return (*warnings, LATEST_WRITE_FAILED.warning(path=folder))
        if os.name == "posix":
            try:
                replace_symlink(folder / _LATEST_LINK, run_id)
            except (AtomicWriteError, OSError):
                warnings.append(LATEST_LINK_FAILED.warning(path=folder))
        return tuple(warnings)

    def abandon(self) -> None:
        """Remove the run folder when it holds no file (a run that failed before any write).

        Empty sub-folders a nested target made are removed first, deepest first; `rmdir`
        removes only empty folders, so a written file keeps the folder and its parents.
        """
        if self._run is None:
            return
        for current, _dirs, _files in os.walk(self._run.path, topdown=False):
            try:
                os.rmdir(current)
            except OSError:
                pass


def _read_latest(folder: Path) -> str | None:
    """The run id `LATEST` names; None when absent, "" when something unreadable is there."""
    path = folder / _LATEST_FILE
    raw = _read_small(path)
    if raw is None:
        # A link, pipe or unreadable file is not absent: "" fails is_run_id, so it is warned.
        return "" if os.path.lexists(path) else None
    return raw.decode("utf-8", errors="replace").strip() or None


def has_placed_output(config_dict: dict) -> bool:
    """True when the config has a relative local file target or a relative enabled quarantine path.

    Only such a config gets an `out/<name>/` folder and a claim (plan 3.5).
    """
    targets = config_dict.get("targets")
    entries = (
        [e for e in targets.values() if isinstance(e, dict)] if isinstance(targets, dict) else []
    )
    paths = [e.get("path") for e in entries if e.get("type", "file") == "file"]
    quarantine = config_dict.get("quarantine")
    if isinstance(quarantine, dict) and quarantine.get("enabled"):
        paths.append(quarantine.get("output_path"))
    return any(
        isinstance(p, str) and p and not Path(p).is_absolute() and "://" not in p for p in paths
    )


def open_run_layout(
    config: Path, config_dict: dict, invocation_id: str, *, project: Path | None = None
) -> RunLayout:
    """The layout for a pipeline YAML: a run folder when it has a placed output, else fixed.

    The project root is the marker folder above the YAML, or the YAML's folder when none is
    found. Raises `LayoutError`, `AtomicWriteError` or `PrivateFileError`.
    """
    from decoy.cli.io._project import find_project

    yaml = config.resolve()
    if not has_placed_output(config_dict):
        return RunLayout.fixed(yaml.parent)
    root = find_project(yaml.parent, project).root
    name = pipeline_name_for(root, yaml, config_dict.get("name"))
    return RunLayout.open(root, name, invocation_id)
