"""The gate's view of output placement: where relative outputs land and what may collide.

`OutputPlacement` is the one route decision (project run folder, typed `--out-dir`, or a
no-write preview). `layout_issues` is the gate's single layout check for `validate`, `ci check`,
`validate preflight` and `run`; the one collision rule (`resolved_output_collisions`) runs inside
it, so no route has a second collision loop. Path rules come from `_layout.py`, one way.
"""

from __future__ import annotations

import os
import stat
import sys
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from decoy._atomic import AtomicWriteError, describe, destination_entry
from decoy._config_file import ConfigFileError, load_config_mapping
from decoy._private_file import PrivateFileError
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.io._cloud import cloud_root_issues, has_cloud_targets
from decoy.cli.io._layout import (
    RunFolder,
    RunLayout,
    _same_dir,
    check_path_budget,
    contained_path,
    is_placed_relative,
    is_run_id,
    names_a_file_inside,
    owning_run,
    pipeline_folder,
    pipeline_identity,
    project_out_folder,
    read_claim,
    relative_outputs,
)
from decoy.cli.io._layout_errors import (
    DELIVERY_ROOT_SPLIT,
    OUTPUT_DIR_UNUSABLE,
    OUTPUT_PATH_COLLISION,
    OUTPUT_PATH_ESCAPES,
    REPORT_NOT_WRITTEN,
    SIDE_FILE_IN_OUT,
    LayoutError,
    LayoutWarning,
)
from decoy.cli.io._run_outputs import OutputKind, RunOutput, replaces_final, run_outputs

if TYPE_CHECKING:
    from decoy.cli.io._pipelines import PipelineRef
    from decoy.cli.io._project import Project


@dataclass(frozen=True)
class OutputPlacement:
    """Where relative outputs land for one gate call (plan 3.6.1): the one route decision.

    `project` is normal placement under `<root>/out/<name>/<run-id>/`; `fixed` is a typed
    `--out-dir` (`directory`); `preview` is a `--rows` run that writes nothing. `inputs` holds resolved
    input paths no side file may replace (the `--duckdb-source` databases). `typed` holds
    the `(flag, path)` side files (`--evidence-out`, `--vault`, `--result`) that join the collision rule.
    `library` is the resolved record-library root when this run stores records: no output or
    side file may land at or inside it. `chunked` is the route, which the cloud kind cannot use.
    """

    kind: str = "project"
    directory: Path | None = None
    typed: tuple[tuple[str, Path], ...] = ()
    chunked: bool = False
    inputs: tuple[Path, ...] = ()
    library: Path | None = None

    @classmethod
    def fixed(
        cls,
        directory: Path,
        typed: tuple[tuple[str, Path], ...] = (),
        chunked: bool = False,
        inputs: tuple[Path, ...] = (),
        library: Path | None = None,
    ) -> OutputPlacement:
        return cls("fixed", Path(os.path.abspath(directory)), typed, chunked, inputs, library)

    @classmethod
    def preview(cls) -> OutputPlacement:
        return cls("preview")


LIBRARY_LABEL = "the record library"


def _landing(path: Path, replaces: bool) -> Path:
    """Where the bytes for `path` land: the strictly resolved parent plus the written entry.

    A writer that follows a final link lands where the link points; one that replaces it lands
    on the link's own name. The gate stays lenient where a writer must fail strict resolution.
    """
    try:
        return destination_entry(path, follow_final=not replaces)
    except (OSError, ValueError):
        try:
            absolute = path.absolute()
            parent = Path(os.path.realpath(absolute.parent))
            return parent / absolute.name if replaces else Path(os.path.realpath(path))
        except (OSError, ValueError):
            return path


def _folds_case(folder: Path) -> bool:
    """True when `folder` sits on a case-insensitive filesystem.

    Probed without writing: swap the case of the nearest existing path component that has a
    letter and ask whether that spelling is the same directory. When no component has a
    letter to swap (`C:\\123`), the platform default decides: Windows and macOS fold.
    """
    for part in (folder, *folder.parents):
        swapped = part.name.swapcase()
        if swapped != part.name:
            return _same_dir(part.with_name(swapped), part)
    return sys.platform in ("win32", "darwin")


def _destination_key(path: Path, *, replaces_final: bool = False) -> tuple:
    """Return one key for every spelling that the filesystem treats as one destination.

    The same key covers a symlink anywhere in the path; a dangling final symlink and its
    missing target; dot segments and repeated or trailing separators; hard links to an existing
    file; and case variants of an existing ancestor or missing suffix on a folding filesystem.
    NFC and NFD variants of a missing suffix also share a key where names fold, as on APFS and
    HFS+. Existing files use device and inode identity. Missing files use that identity for the
    nearest existing directory plus its filesystem-normalized suffix. Two mounts of one remote
    share are outside this contract.
    """
    real = _landing(path, replaces_final)
    try:
        entry = os.lstat(real) if replaces_final else None
        found = None if entry is not None and stat.S_ISLNK(entry.st_mode) else os.stat(real)
    except (OSError, ValueError):
        found = None
    if found is not None:
        return ("file", found.st_dev, found.st_ino)
    for ancestor in real.parents:
        try:
            identity = os.stat(ancestor)
        except (OSError, ValueError):
            continue
        if not stat.S_ISDIR(identity.st_mode):
            continue
        suffix = real.relative_to(ancestor).parts
        try:
            folds = _folds_case(ancestor)
        except (OSError, ValueError):
            folds = False
        if folds:
            suffix = tuple(
                unicodedata.normalize("NFC", unicodedata.normalize("NFC", part).casefold())
                for part in suffix
            )
        return ("path", identity.st_dev, identity.st_ino, suffix)
    try:
        return ("unresolved", os.path.normpath(os.fspath(real)))
    except (OSError, TypeError, ValueError):
        return ("unresolved",)


def _destination_is_within(child: Path, parent: Path, *, replaces: bool = False) -> bool:
    """True when `child` lands in, or sits lexically in, the same destination as `parent`.

    Identity comes only from `_destination_key`, so links, case folding and missing paths
    behave as they do for the collision rule. `replaces` is the writer's final-link policy.
    """
    target = _destination_key(parent)
    landed = _landing(child, replaces)
    return any(_destination_key(path) == target for path in (landed, *landed.parents))


def _split_root(config_dict: dict, fixed: Path | None = None) -> tuple[str, str] | None:
    """The first two local file outputs that do not share one delivery root, as labels.

    Relative outputs share the run folder, or the `--out-dir` folder when `fixed` is set;
    absolute ones must share one folder, the parent of where the file lands, judged by
    `_destination_key`. In a project a relative and an absolute output never share; under
    `--out-dir` an absolute output directly in that folder shares with the relative ones.
    """
    relative_key = _destination_key(fixed) if fixed is not None else ("relative",)
    roots: list[tuple[str, tuple]] = []
    for location, raw in relative_outputs(config_dict):
        if is_placed_relative(raw):
            roots.append((location, relative_key))
        elif Path(raw).is_absolute():
            landed = _landing(Path(raw), replaces_final(location))
            roots.append((location, _destination_key(landed.parent)))
    return next(((roots[0][0], loc) for loc, key in roots[1:] if key != roots[0][1]), None)


def _side_file_in_out(out: Path, typed: tuple[tuple[str, Path], ...]) -> str | None:
    """The flag of the first side file that sits or lands under the project's `out/` folder.

    A final link that sits in `out/` is refused even when it points away, so the entry is
    checked too; a link outside `out/` that points in is refused by where it lands.
    """
    for flag, path in typed:
        entry = _destination_is_within(Path(path), out, replaces=True)
        if entry or _destination_is_within(Path(path), out, replaces=replaces_final(flag)):
            return flag
    return None


def protected_inputs(
    config: Path, config_dict: dict, inputs: tuple[Path, ...] = ()
) -> tuple[tuple[str, Path], ...]:
    """The pipeline file, every local file source and the `inputs` paths, as `(label, path)`,
    that no typed side file may be written onto.

    Source paths come from the CLI's one resolver (`resolved_source_config`), over the engine's
    `FILE_SOURCE_PATH_FIELDS`, so a relative path joins the config's folder as a run reads it.
    A remote path (`://`) is skipped. `inputs` are paths the placement already resolved, such as
    the `--duckdb-source` databases.
    """
    from decoy_engine import FILE_SOURCE_PATH_FIELDS

    from decoy.cli._sources import resolved_source_config

    found: list[tuple[str, Path]] = [("the pipeline file", Path(config))]
    declared = config_dict.get("sources")
    if isinstance(declared, dict):
        resolved = resolved_source_config(config_dict, Path(config).parent)["sources"]
        for name, spec in declared.items():
            if not (isinstance(spec, dict) and spec.get("type") == "file"):
                continue
            for field in FILE_SOURCE_PATH_FIELDS:
                value = spec.get(field)
                if isinstance(value, str) and value and "://" not in value and "\x00" not in value:
                    found.append((f"sources.{name}.{field}", Path(resolved[name][field])))
    found.extend(("--duckdb-source", path) for path in inputs)
    return tuple(found)


_SIDE_KINDS = frozenset(
    {
        OutputKind.INTEGRITY_EXPLICIT,
        OutputKind.INTEGRITY_IMPLICIT,
        OutputKind.RESULT,
        OutputKind.EVIDENCE,
        OutputKind.VAULT,
    }
)


def overlaps_root(output: RunOutput, root: Path) -> bool:
    """True when `output` and the library `root` share a destination, in either direction.

    `root` is the anchored root (absolute, links resolved, it may not exist yet). Identity
    comes only from `_destination_key`, for the entry name and the followed landing, so a link
    outside the root that points in is caught whichever final-link policy the writer has.
    (a) at or below: the root is the output's landing or a folder above it.
    (b) above: the output's landing is the root or a folder above it, existing or not.
    """
    root_key = _destination_key(root)
    above = {_destination_key(folder) for folder in (root, *root.parents)}
    for landing in (_landing(output.path, True), _landing(output.path, False)):
        if any(_destination_key(path) == root_key for path in (landing, *landing.parents)):
            return True
        if _destination_key(landing) in above:
            return True
    return False


def resolved_output_collisions(
    outputs: tuple[RunOutput, ...],
    protected: tuple[tuple[str, Path], ...] = (),
    library: Path | None = None,
) -> tuple[str, str] | None:
    """The first two outputs that resolve to one destination, as `(first, second)` labels.

    The one collision rule (plan 3.6.1 B). It reads only `outputs`, the run's one inventory
    (`run_outputs`): every local file target, quarantine, side file and layout file takes part.
    `library` is the record library root: an output that overlaps it, in either direction,
    is refused with the library as the first party. Labels are config locations or flag names,
    never path values.
    """
    seen: dict[tuple, str] = {}
    entries: dict[tuple, str] = {}
    if library is not None:
        # The run writes its records there, so an output on it would lose to the store.
        for out in outputs:
            if overlaps_root(out, library):
                return LIBRARY_LABEL, out.label
    for out in outputs:
        key = _destination_key(out.path, replaces_final=out.replaces_final)
        # A writer that replaces a final link turns it into a file, and a later writer that
        # follows the same name would then replace that file, so one name is one destination
        # whichever way each writer treats the link.
        entry = key if out.replaces_final else _destination_key(out.path, replaces_final=True)
        first = seen.get(key) or entries.get(entry)
        if first is not None:
            return first, out.label
        seen[key] = out.label
        entries[entry] = out.label
    # A side file never lands on an input: the same key, so links and hard links are covered.
    for label, path in protected:
        held = {_destination_key(path), _destination_key(path, replaces_final=True)}
        for side in outputs:
            if side.kind not in _SIDE_KINDS:
                continue
            keys = {
                _destination_key(side.path, replaces_final=side.replaces_final),
                _destination_key(side.path, replaces_final=True),
            }
            if keys & held:
                return label, side.label
    return None


def fixed_target_overwrites(config_dict: dict, directory: Path) -> list[tuple[str, str]]:
    """`(table, location)` for each relative file target that already exists in `directory`."""
    found: list[tuple[str, str]] = []
    for location, raw in relative_outputs(config_dict):
        if location.startswith("targets.") and is_placed_relative(raw):
            placed = contained_path(directory, raw)
            if placed is not None and placed.exists():
                found.append((location.removeprefix("targets.").removesuffix(".path"), location))
    return found


def layout_issues(
    config: Path, config_dict: dict, placement: OutputPlacement = OutputPlacement()
) -> list[tuple[str | None, LayoutError]]:
    """The layout refusals the gate can find without writing (plan 3.14), with locations.

    Escape is judged on the text alone. With a relative output the project marker is read
    and the pipeline name and any claim are checked read-only, then each placed path is
    held to the Windows path budget. A fixed `--out-dir` skips the project checks and holds
    each path to the physical directory instead; a preview checks nothing. Then all
    outputs must share one delivery root, and in a project no side file may sit under `out/`.
    Last, no two outputs may resolve to one destination.
    """
    from decoy.cli.io._project import find_project

    if placement.kind == "preview":
        return []
    outputs = relative_outputs(config_dict)
    placed = [(location, raw) for location, raw in outputs if is_placed_relative(raw)]
    urls = [
        (location, raw)
        for location, raw in outputs
        if not is_placed_relative(raw) and not Path(raw).is_absolute()
    ]
    issues: list[tuple[str | None, LayoutError]] = []
    fixed = placement.directory if placement.kind == "fixed" else None
    folder: Path | None = None
    project_out: Path | None = None
    base = "--out-dir" if fixed is not None else "its run folder"
    if fixed is not None:
        folder = fixed.resolve() if fixed.exists() else fixed
        if not (fixed.is_dir() if os.path.lexists(fixed) else fixed.parent.is_dir()):
            issues.append((None, OUTPUT_DIR_UNUSABLE.error()))
    elif placed or urls:
        try:
            found, pn = pipeline_identity(config, config_dict.get("name"))
            name = pn.name
            folder, base = pipeline_folder(found.root, name), f"out/{name}/<run-id>"
            project_out = folder.parent
        except LayoutError as exc:
            issues.append((None, exc))
    elif placement.typed:
        # Absolute targets only: a project-placement run still owns `<root>/out/`, so the side
        # file rule needs the root even though no output lands there. No root, no rule.
        try:
            project_out = project_out_folder(find_project(config.resolve().parent, None).root)
        except LayoutError:
            project_out = None
    if has_cloud_targets(config_dict):
        # The cloud kind keeps its pointer lock under the project's out/ (an implicit project
        # uses the config folder), so the side-file rule applies even with --out-dir.
        try:
            # Same naming rule as local delivery; the name itself is used from CC2a on.
            found, _pn = pipeline_identity(config, config_dict.get("name"))
            project_out = project_out_folder(found.root)
        except LayoutError as exc:
            if all(seen.code != exc.code for _loc, seen in issues):
                issues.append((None, exc))
        issues.extend(cloud_root_issues(config_dict, chunked=placement.chunked))
    for location, _raw in urls:
        issues.append((location, OUTPUT_PATH_ESCAPES.error(path="a URL", base=base)))
    for location, raw in placed:
        if not names_a_file_inside(raw) or (
            fixed is not None and fixed.exists() and contained_path(folder or fixed, raw) is None
        ):
            issues.append((location, OUTPUT_PATH_ESCAPES.error(path=raw or '""', base=base)))
        elif folder is not None:
            try:
                check_path_budget(folder, raw, run_folder=fixed is None)
            except LayoutError as exc:
                issues.append((location, exc))
    issues.extend(
        (location, OUTPUT_PATH_ESCAPES.error(path="a path with a NUL byte", base=base))
        for location, raw in outputs
        if Path(raw).is_absolute() and "\x00" in raw
    )
    issues.extend(
        (None, OUTPUT_PATH_ESCAPES.error(path=f"the {flag} path (it has a NUL byte)", base=base))
        for flag, typed in placement.typed
        if "\x00" in os.fspath(typed)
    )
    if not issues and (split := _split_root(config_dict, fixed)) is not None:
        issues.append((None, DELIVERY_ROOT_SPLIT.error(first=split[0], second=split[1])))
    if (
        not issues
        and project_out is not None
        and (flag := _side_file_in_out(project_out, placement.typed))
    ):
        issues.append((None, SIDE_FILE_IN_OUT.error(flag=flag, base="the project's out/ folder")))
    if not issues:
        where = folder if fixed is not None else folder and folder / "<run-id>"
        clash = resolved_output_collisions(
            run_outputs(config_dict, placement, config, where),
            protected_inputs(config, config_dict, placement.inputs),
            placement.library,
        )
        if clash is not None:
            first_location = next((c for c in clash if not c.startswith("--")), None)
            issues.append(
                (first_location, OUTPUT_PATH_COLLISION.error(first=clash[0], second=clash[1]))
            )
    return issues


def layout_failures(config: Path, config_dict: dict) -> list[tuple[str, str, str | None]]:
    """`layout_issues` as plain `(code, message, location)` rows for the preflight gate."""
    return [(err.code, err.message, loc) for loc, err in layout_issues(config, config_dict)]


def owning_pipeline(
    config: Path, declared: object, project: Project | None
) -> tuple[Path, str] | None:
    """`(project root, run-folder name)` of a pipeline YAML, for finding its run outputs.

    None when the name is refused; the caller then reads files by the suffix rule alone.
    """
    try:
        found, name = pipeline_identity(config, declared, project)
    except LayoutError:
        return None
    return found.root, name.name


def _claimed_run(root: Path, name: str, file: Path) -> RunFolder | None:
    """The run folder of pipeline `name` in `root` that holds `file`, when its claim vouches.

    A look-alike `out/<name>/<run-id>/` has no such claim. The claim must be a regular file naming
    a YAML inside the project that exists and whose identity, by the rule `decoy run` uses, is
    `name`. Anything else, or a YAML that cannot be read, is None.
    """
    from decoy.cli.io._project import Project

    run = owning_run(file, root, name)
    claimed = read_claim(project_out_folder(root), name) if run is not None else None
    yaml = contained_path(root, claimed) if claimed is not None else None
    if run is None or yaml is None:
        return None
    try:
        declared = load_config_mapping(yaml).get("name")
        _found, identity = pipeline_identity(yaml, declared, Project(root=root))
    except (ConfigFileError, OSError, LayoutError):
        return None
    return run if identity.name == name else None


def _root_of_run_folder(file: Path) -> Path | None:
    """The root a file's own folder names point at: `<R>/out/<name>/<run-id>/...`, claim included."""
    resolved = file.resolve()
    for run in resolved.parents:
        root = run.parent.parent.parent
        if is_run_id(run.name) and _claimed_run(root, run.parent.name, resolved) is not None:
            return root
    return None


def _default_report_path(
    kind: str, file: Path, ref: PipelineRef | None
) -> Path | LayoutWarning | None:
    """Where `report <kind>` writes by default: `<run>/reports/<kind>.json` for a run output.

    Candidate roots are the pipeline's project, the config's folder, the project found from the
    file and the root its own folders name; each goes through `_claimed_run`, so only a run folder
    its pipeline claim vouches for qualifies. Makes the owner-only `reports/` folder. None for any
    other file, so nothing new is written; a `LayoutWarning` when the folder cannot be made.
    """
    from decoy.cli.io._project import find_project

    roots = [ref.project.root] if ref is not None and ref.project is not None else []
    if ref is not None:
        roots.append(ref.yaml.resolve().parent)
    try:
        roots.append(find_project(file.resolve().parent, None).root)
    except LayoutError:
        pass
    if (own := _root_of_run_folder(file)) is not None:
        roots.append(own)
    for root in roots:
        try:
            names = os.listdir(project_out_folder(root))
        except OSError:
            continue
        run = next((r for n in names if (r := _claimed_run(root, n, file)) is not None), None)
        if run is None:
            continue
        folder = run.path / "reports"
        failed = False
        try:
            RunLayout.out_dir(folder, create=True)
        except (NotADirectoryError, PrivateFileError):
            failed = True
        return REPORT_NOT_WRITTEN.warning() if failed else folder / f"{kind}.json"
    return None


def open_out_dir(directory: Path) -> RunLayout:
    """The layout for `--out-dir DIR`; anything unusable is `layout.output_dir_unusable`.

    Always the registry text: the caller's wording and the path are dropped. Nothing is made
    here; DIR is created by the first relative placement, after the gate.
    """
    failed = False
    try:
        layout = RunLayout.out_dir(directory)
    except (OSError, PrivateFileError, ValueError):
        failed = True
    if failed:
        raise OUTPUT_DIR_UNUSABLE.error()
    return layout


@dataclass
class ReportTarget:
    """Where one report goes: a typed path, or the default under a run folder (`implicit`).

    A failed write sets `warning` for a default (the check's exit code never changes) and
    `error`, the rendered reason, for a typed path (the command refuses).
    """

    path: Path | None
    implicit: bool
    warning: LayoutWarning | None = None
    error: str | None = None
    exit_code: int = EXIT_USAGE

    @property
    def paths(self) -> tuple[Path, ...]:
        """The files to write: none when there is no default report to make."""
        return () if self.path is None else (self.path,)

    @contextmanager
    def recording(self) -> Iterator[None]:
        """Record a failed write on this target instead of raising it."""
        try:
            yield
        except AtomicWriteError as exc:
            if self.implicit:
                self.warning = REPORT_NOT_WRITTEN.warning()
            else:
                self.error = f"could not write {self.path}: {describe(exc)}"


def report_dest(kind: str, file: Path, ref: PipelineRef | None, typed: Path | None) -> ReportTarget:
    """The typed path if given, else the default `<run>/reports/<kind>.json` for a run output."""
    if typed is not None:
        return ReportTarget(typed, False)
    found = _default_report_path(kind, file, ref)
    if isinstance(found, LayoutWarning):
        return ReportTarget(None, True, found)
    return ReportTarget(found, True)
