"""Run folders under `<project>/out/<name>/<run-id>/`: the run-id rule and path placement.

`RunLayout` is the one builder of output paths: it opens the run folder, places each declared
target and quarantine path inside it, and moves `LATEST` and `current` after a clean run. One place owns what
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
from typing import TYPE_CHECKING, Literal, TypeGuard

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

if TYPE_CHECKING:
    from decoy.cli.io._project import Project

# <UTC start YYYYMMDDTHHMMSSffffffZ>-<8 hex of the invocation id>, plus 4 more hex digits per
# clash, up to all 32.
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}(?:[0-9a-f]{4}){0,6}")


MAX_RUN_ID_LENGTH = 55
WINDOWS_PATH_LIMIT = 259
_CLAIM_NAME = "PIPELINE"
PIPELINES_DIR = "pipelines"
PIPELINE_YAML = "pipeline.yaml"


def member_yaml(root: Path, name: str) -> Path:
    """Where the member `name` lives: the one spelling of `pipelines/<name>/pipeline.yaml`."""
    return root / PIPELINES_DIR / name / PIPELINE_YAML


_CLAIM_MAX_BYTES = 4096
_SLUG_MAX = 56
_SLUG_BAD = re.compile(r"[^A-Za-z0-9_.-]+")
_DASH_RUNS = re.compile(r"-{2,}")
_URL_PATH = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


def is_valid_name(name: str) -> bool:
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
    except (OSError, RuntimeError, ValueError):
        return False


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def owning_run(path: Path, root: Path, name: str) -> RunFolder | None:
    """The run folder of pipeline `name` in project `root` that holds `path`, else None.

    `path` is resolved first, so a `current` link is followed and a link that leaves the run
    folder is judged by where it lands. A run folder is found by identity: the ancestor of
    the file whose parent is the pipeline folder. The run folder itself holds no file and
    gives None. An unresolvable path gives None.
    """
    try:
        base = (root / "out" / name).resolve()
        resolved = path.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    for ancestor in resolved.parents:
        if _same_dir(ancestor.parent, base):
            if not is_run_id(ancestor.name):
                return None
            return RunFolder(base / ancestor.name, ancestor.name)
    return None


SideKind = Literal["unmasked", "detokenized", "snapshot"]
_SIDE_SUFFIX: dict[str, str] = {
    "unmasked": ".unmasked.csv",
    "detokenized": ".detokenized.csv",
    "snapshot": ".snapshot.json",
}


def side_file_name(kind: SideKind, stem: str) -> str:
    """The default name of a side file for a file stem: the one place the suffixes join a stem."""
    return f"{stem}{_SIDE_SUFFIX[kind]}"


def side_file_default(kind: SideKind, input_path: Path, *, parquet: bool = False) -> Path:
    """The default side file beside its input; `current` is resolved first. Unknown kind: `KeyError`."""
    suffix = ".detokenized.parquet" if parquet and kind == "detokenized" else _SIDE_SUFFIX[kind]
    real, plain = input_path.parent.resolve(), Path(os.path.abspath(input_path.parent))
    beside = input_path if real == plain else real / input_path.name
    return beside.with_suffix(suffix)


def placed_path(run: RunFolder, raw: str) -> Path | None:
    """`raw` placed inside `run` and resolved, or None when it does not stay inside.

    The rule is `contained_path` with the run folder as the base.
    """
    return contained_path(run.path, raw)


def contained_path(base: Path, raw: str) -> Path | None:
    """`raw`, a relative path written with "/", placed under `base` and resolved; None when
    it does not stay inside. The one parser of stored and declared relative paths.

    Refused: any backslash (a stored or declared path uses "/" only, so it means the same on
    every OS), an anchor or drive (`/x`, `C:x`, `//host/share/x`), a trailing separator (a
    directory, not a file), a `..` that climbs above `base` at any step (even to come back
    in), and a result that lands outside `base` through an existing symlink. Containment is
    by file identity, so another spelling of `base` still counts. The result is resolved, so
    it compares with a resolved input path. A path that cannot be resolved gives None.
    """
    if not names_a_file_inside(raw):
        return None
    try:
        resolved = Path(os.path.normpath(base / raw)).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if any(_same_dir(ancestor, base) for ancestor in resolved.parents):
        return resolved
    return None


def names_a_file_inside(raw: str) -> bool:
    """The lexical half of `contained_path`: True when `raw` names a file below its base.

    Reads only the text, so the gate can run it before any folder exists.
    """
    if not raw or "\x00" in raw or "\\" in raw or raw.endswith("/"):
        return False
    for style in (PurePosixPath, PureWindowsPath):
        pure = style(raw)
        if pure.anchor or pure.drive:
            return False
    depth = 0
    for part in PurePosixPath(raw).parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return False
        elif part != ".":
            depth += 1
    return depth > 0


def _on_windows() -> bool:
    return os.name == "nt"


def _inside(child: Path, parent: Path) -> bool:
    return any(_same_dir(ancestor, parent) for ancestor in (child, *child.parents))


def _utf16_units(text: str) -> int:
    # Windows measures paths in UTF-16 units: a character past U+FFFF counts twice.
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def check_path_budget(name_dir: Path, rel: str, *, run_folder: bool = True) -> None:
    """Refuse on Windows a placed path that can pass 259 characters with the longest run id.

    `name_dir` is `<root>/out/<name>`; the run id is counted at its maximum length so a path
    that fits today does not fail on a run-id clash later. POSIX has no such limit here.
    `run_folder=False` is a fixed `--out-dir`: `name_dir` is that folder and no run id follows.
    Raises `LayoutError`.
    """
    if not _on_windows():
        return
    run_id = MAX_RUN_ID_LENGTH + 1 if run_folder else 0
    length = _utf16_units(str(name_dir)) + 1 + run_id + _utf16_units(rel)
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


def name_slug(stem: str) -> str:
    """A file stem as a pipeline-name candidate: safe characters only, at most 56. May be empty."""
    slug = _DASH_RUNS.sub("-", _SLUG_BAD.sub("-", stem))
    slug = slug.lstrip("-._")[:_SLUG_MAX]
    return slug.rstrip("-.")


def _derived(root: Path, yaml_rel: str, stem: str) -> str:
    digest = hashlib.sha256(yaml_rel.encode()).hexdigest()[:6]
    slug = name_slug(stem)
    for base in (slug or "pipeline", "pipeline"):
        candidate = f"{base}-{digest}"
        if is_valid_name(candidate):
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
    member = f"{PIPELINES_DIR}/{name}/{PIPELINE_YAML}"
    if member_yaml(root, name).parent.exists() and member != yaml_rel:
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
    if len(parts) == 3 and parts[0] == PIPELINES_DIR and parts[2] == PIPELINE_YAML:
        folder = parts[1]
        if not is_valid_name(folder):
            raise PIPELINE_NAME_INVALID.error(name=folder)
        if declared is not None and declared != folder:
            raise PIPELINE_NAME_MISMATCH.error(path=yaml_rel, declared=declared, folder=folder)
        return PipelineName(folder, True, yaml_rel)
    if declared is not None:
        if not is_valid_name(declared):
            raise PIPELINE_NAME_INVALID.error(name=declared)
        assert isinstance(declared, str)
        other = _taken(root, declared, yaml_rel)
        if other is not None:
            raise PIPELINE_NAME_COLLISION.error(
                name=declared, other=other, claim=f"out/{declared}/{_CLAIM_NAME}"
            )
        return PipelineName(declared, True, yaml_rel)
    stem = yaml.name.rsplit(".", 1)[0] if "." in yaml.name else yaml.name
    slug = name_slug(stem)
    if slug == stem and is_valid_name(slug) and _taken(root, slug, yaml_rel) is None:
        return PipelineName(slug, False, yaml_rel)
    return PipelineName(_derived(root, yaml_rel, stem), False, yaml_rel)


def project_out_folder(root: Path) -> Path:
    """`<root>/out/` as a path only: nothing is made, read or resolved."""
    return root / "out"


def pipeline_folder(root: Path, name: str) -> Path:
    """`<root>/out/<name>/` as a path only: nothing is made, read or resolved."""
    return project_out_folder(root) / name


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
# Not `latest`: macOS and Windows fold case by default, so it would collide with `LATEST`.
_LATEST_LINK = "current"


def mint_invocation_id() -> str:
    """A new invocation id (UUID4 text). Called once per command, at its entry.

    The run folder name, the evidence `run_id` and later run records all carry this one value.
    """
    return str(uuid.uuid4())


def target_parent_writable(path: Path) -> bool:
    """True when `path` has an existing, writable directory ancestor.

    `os.access` checks the process's effective access. On Windows it does not evaluate ACLs,
    so this remains an advisory preflight check rather than a write guarantee.
    """
    ancestor = next((parent for parent in path.parents if parent.exists()), None)
    return ancestor is not None and ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK)


class RunLayout:
    """Where one command writes its files: a run folder, or a fixed base folder.

    `RunLayout.open` makes `out/<name>/<run-id>/` (claim, `.gitignore`, private folder) and
    `RunLayout.fixed(base)` places relative paths against `base` as the pre-layout code did
    (`demo`, `mask()`): no claim, no run id, no `LATEST` or `current`. `RunLayout.out_dir`
    is `--out-dir`: a fixed folder that relative paths must stay inside. `place_target` and
    `place_quarantine` are the only way a command turns a declared path into a file path.
    """

    def __init__(
        self,
        base: Path,
        *,
        run: RunFolder | None = None,
        pipeline_dir: Path | None = None,
        warnings: tuple[LayoutWarning, ...] = (),
        project: Project | None = None,
        pipeline: PipelineName | None = None,
        contained: bool = False,
    ) -> None:
        self._base = base
        self._run = run
        self._pipeline_dir = pipeline_dir
        self._project = project
        self._pipeline = pipeline
        self._contained = contained
        self.warnings = warnings

    @classmethod
    def fixed(cls, base: Path) -> RunLayout:
        """A layout with no run folder: relative paths resolve against `base`."""
        return cls(base)

    @classmethod
    def out_dir(cls, folder: Path, *, create: bool = False) -> RunLayout:
        """`--out-dir DIR` (plan 3.6): `DIR` stands in for the run folder.

        A relative `DIR` is taken from the current folder. Only its shape is checked here: it
        must be a directory (or a link to one), or be missing with an existing parent. A missing
        `DIR` is made owner-only by `place_target`, after the gate, for the first relative
        output; an existing one is used as it is and its files are overwritten. No claim, run
        id, `LATEST` or `.gitignore`. A relative target must stay inside `DIR`, through
        existing links too. `create=True` (the first relative placement) makes a missing `DIR`.
        Raises `NotADirectoryError` for an unusable shape, or `PrivateFileError`.
        """
        base = Path(os.path.abspath(folder))
        if not (base.is_dir() if os.path.lexists(base) else base.parent.is_dir()):
            raise NotADirectoryError
        if create and not base.exists():
            create_private_directory(base)
        return cls(base, contained=True)

    @classmethod
    def open(
        cls,
        root: Path,
        name: PipelineName,
        invocation_id: str,
        started: datetime | None = None,
        *,
        project: Project | None = None,
    ) -> RunLayout:
        """Make the run folder for pipeline `name` in project `root` (plan 3.6).

        Runs after the gate passes and before the first write: `out/` and its `.gitignore`,
        the claim, then `out/<name>/<run-id>/` (0700). A claim naming another YAML is a
        collision. `project` is what `find_project` returned, kept for `describe`. Raises
        `LayoutError`, `AtomicWriteError` or `PrivateFileError`.
        """
        from decoy.cli.io._project import Project

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
        return cls(
            root,
            run=run,
            pipeline_dir=folder,
            warnings=warnings,
            project=project or Project(root=root),
            pipeline=name,
        )

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

        if is_absolute_local(raw) or (self._run is None and not self._contained):
            return resolve_path(raw, self._base)
        if self._run is None and not self._base.exists():
            RunLayout.out_dir(self._base, create=True)
        if self._pipeline_dir is not None:
            check_path_budget(self._pipeline_dir, raw)
        placed = (
            placed_path(self._run, raw)
            if self._run is not None
            else contained_path(self._base, raw)
        )
        if placed is None:
            raise OUTPUT_PATH_ESCAPES.error(path=raw, base=self.base)
        return placed

    def place_quarantine(self, config_dict: dict) -> str | None:
        """The `run_pipeline(quarantine_path=...)` value: the placed quarantine file, when on.

        None unless quarantine is enabled and names an output path; the engine then keeps its
        own rule. The engine applies the path after it hashes the config, so the plan hash
        matches the path as declared and the caller's dict is never edited.
        """
        if not quarantine_enabled(config_dict):
            return None
        raw = config_dict["quarantine"].get("output_path")
        if not isinstance(raw, str):
            return None
        return str(self.place_target(raw))

    def commit_latest(self) -> tuple[LayoutWarning, ...]:
        """Point `LATEST` and `current` at this run, after a clean (exit 0) run.

        Moves nothing when `LATEST` already names a later run id. An invalid `LATEST` is
        treated as absent and warned. A failure here never changes the run's outcome: it is
        returned as a warning.
        """
        if self._run is None or self._pipeline_dir is None:
            return ()
        folder, run_id = self._pipeline_dir, self._run.run_id
        warnings: list[LayoutWarning] = []
        current = read_latest(folder)
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

    def output_dir(self) -> Path | None:
        """The folder this run writes relative paths into: the run folder or `--out-dir`.

        None for a plain fixed layout (only absolute targets, `demo`, `mask()`), and None
        once `abandon` has removed an empty run folder, so no output names a folder that is gone.
        """
        if self._run is None and not self._contained:
            return None
        folder = self.base
        return folder.resolve() if folder.is_dir() else None

    def describe(self, given_as: str = "path") -> dict[str, object]:
        """The run `--json` members of plan 7.6 that come from the layout, every path absolute.

        `output_dir` is not one of them: it follows the publication ledger (plan 3.6.1 C).
        `project` is `{root, implicit, skipped}` and `pipeline` is `{name, yaml, given_as}`;
        both are None when no run folder was opened (only absolute targets, or `--out-dir`).
        `given_as` is "name" when the run was started with a pipeline name, else "path".
        """
        project = pipeline = None
        if self._project is not None:
            project = {
                "root": str(self._project.root.resolve()),
                "implicit": self._project.implicit,
                "skipped": [str(p.resolve()) for p in self._project.skipped],
            }
        if self._pipeline is not None:
            yaml = self._project.root.resolve() if self._project is not None else Path.cwd()
            pipeline = {
                "name": self._pipeline.name,
                "yaml": str((yaml / self._pipeline.yaml_rel).resolve()),
                "given_as": given_as,
            }
        return {"project": project, "pipeline": pipeline}

    def summary_facts(self) -> list[tuple[str, str]]:
        """The summary lines: project, run folder and the latest pointer.

        A path under the current folder prints relative to it, any other path absolute.
        """
        facts: list[tuple[str, str]] = []
        if self._project is not None:
            facts.append(("Project", shown_path(self._project.root.resolve())))
        folder = self.output_dir()
        if folder is not None:
            facts.append(
                ("Run folder" if self._run is not None else "Output folder", shown_path(folder))
            )
        if self._pipeline_dir is not None:
            pointer = _LATEST_LINK if os.name == "posix" else _LATEST_FILE
            facts.append(("Latest", shown_path(self._pipeline_dir / pointer)))
        return facts

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


def shown_path(path: Path) -> str:
    """`path` for human output: relative to the current folder when under it, else absolute."""
    try:
        here = Path.cwd().resolve()
    except (OSError, RuntimeError):
        return str(path)
    try:
        return str(path.relative_to(here))
    except ValueError:
        return str(path)


def read_latest(folder: Path) -> str | None:
    """The run id `LATEST` names; None when absent, "" when something unreadable is there."""
    path = folder / _LATEST_FILE
    raw = _read_small(path)
    if raw is None:
        # A link, pipe or unreadable file is not absent: "" fails is_run_id, so it is warned.
        return "" if os.path.lexists(path) else None
    return raw.decode("utf-8", errors="replace").strip() or None


def is_placed_relative(raw: object) -> bool:
    """True when `raw` is a local path that placement resolves below its output folder.

    Empty strings count so the layout gate can refuse them. A URL is only a string whose
    scheme and `://` start at offset zero; URL-like text later in a relative path is local.
    """
    return isinstance(raw, str) and not is_absolute_local(raw) and _URL_PATH.match(raw) is None


def is_absolute_local(raw: object) -> TypeGuard[str]:
    """True when `raw` is a path that placement leaves where it is.

    `pathlib` decides, as in `place_target`. `os.path.isabs` disagrees with it on Windows for a
    rooted path with no drive (`\\x`, `/x`) and differs between Python versions.
    """
    return isinstance(raw, str) and Path(raw).is_absolute()


def quarantine_enabled(cfg: object) -> bool:
    """True when `cfg` has a `quarantine` block with a truthy `enabled`.

    The one reader of this fact. The engine's schema check owns the value's type, so a
    non-bool `enabled` is judged by truthiness here, as it always was.
    """
    block = cfg.get("quarantine") if isinstance(cfg, dict) else None
    return isinstance(block, dict) and bool(block.get("enabled"))


def relative_outputs(config_dict: dict) -> list[tuple[str, str]]:
    """Enumerate every string path the local target writers can place.

    The predicate `is_placed_relative` decides which entries receive relative placement.
    Keeping absolute paths and URLs in this one enumeration lets the gate distinguish them
    without a second target walk. An empty path is retained so the gate refuses it.
    """
    found: list[tuple[str, object]] = []
    targets = config_dict.get("targets")
    if isinstance(targets, dict):
        found.extend(
            (f"targets.{table}.path", entry.get("path"))
            for table, entry in targets.items()
            if isinstance(entry, dict) and entry.get("type", "file") in ("file", None)
        )
    if quarantine_enabled(config_dict):
        found.append(("quarantine.output_path", config_dict["quarantine"].get("output_path")))
    return [(location, raw) for location, raw in found if isinstance(raw, str)]


def has_placed_output(config_dict: dict) -> bool:
    """True when the config has a non-empty relative local output."""
    return any(raw and is_placed_relative(raw) for _location, raw in relative_outputs(config_dict))


def open_run_layout(
    config: Path, config_dict: dict, invocation_id: str, *, project: Path | None = None
) -> RunLayout:
    """The layout for a pipeline YAML: a run folder when it has a placed output, else fixed.

    The project root is the marker folder above the YAML, or the YAML's folder when none is
    found. Raises `LayoutError`, `AtomicWriteError` or `PrivateFileError`.
    """
    yaml = config.resolve()
    if not has_placed_output(config_dict):
        return RunLayout.fixed(yaml.parent)
    found, name = pipeline_identity(yaml, config_dict.get("name"), project)
    return RunLayout.open(found.root, name, invocation_id, project=found)


def pipeline_identity(
    config: Path, declared: object, project: Project | Path | None = None
) -> tuple[Project, PipelineName]:
    """The project and run-folder name of a pipeline YAML: the one place both are decided.

    `project` is a found project, a root to read (`--project`), or None to walk up. Raises `LayoutError`.
    """
    from decoy.cli.io._project import find_project

    walk = project is None or isinstance(project, Path)
    found = find_project(config.resolve().parent, project) if walk else project
    return found, pipeline_name_for(found.root, config.resolve(), declared)
