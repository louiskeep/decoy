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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from decoy._atomic import destination_entry
from decoy.cli.io._cloud import cloud_root_issues, has_cloud_targets
from decoy.cli.io._layout import (
    _same_dir,
    check_path_budget,
    contained_path,
    is_placed_relative,
    names_a_file_inside,
    pipeline_folder,
    pipeline_name_for,
    project_out_folder,
    relative_outputs,
    report_default_path,
)
from decoy.cli.io._layout_errors import (
    DELIVERY_ROOT_SPLIT,
    OUTPUT_PATH_COLLISION,
    OUTPUT_PATH_ESCAPES,
    SIDE_FILE_IN_OUT,
    LayoutError,
)

if TYPE_CHECKING:
    from decoy.cli.io._pipelines import PipelineRef
    from decoy.cli.io._project import Project


@dataclass(frozen=True)
class OutputPlacement:
    """Where relative outputs land for one gate call (plan 3.6.1): the one route decision.

    `project` is normal placement under `<root>/out/<name>/<run-id>/`; `fixed` is a typed
    `--out-dir` (`directory`); `preview` is a `--rows` run that writes nothing. `typed` holds
    the `(flag, path)` side files (`--evidence-out`, `--vault`) that join the collision rule.
    `chunked` is the route, which the cloud kind cannot use.
    """

    kind: str = "project"
    directory: Path | None = None
    typed: tuple[tuple[str, Path], ...] = ()
    chunked: bool = False

    @classmethod
    def fixed(
        cls, directory: Path, typed: tuple[tuple[str, Path], ...] = (), chunked: bool = False
    ) -> OutputPlacement:
        return cls("fixed", Path(os.path.abspath(directory)), typed, chunked)

    @classmethod
    def preview(cls) -> OutputPlacement:
        return cls("preview")


# The one policy for a destination's final path component. A writer either follows a final
# symlink (file targets, quarantine and `--evidence-out`, which use `write_local_target`
# REPLACE) or replaces it with a file (`--vault`). Everything not listed follows. The split
# root, the side-file check and the collision rule all read this, so none decides alone.
_REPLACES_FINAL = frozenset({"--vault"})


def replaces_final(label: str) -> bool:
    """True when the writer behind `label` (a config location or flag) replaces a final link."""
    return label in _REPLACES_FINAL


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


def resolved_output_collisions(
    config_dict: dict, base: Path | None, typed: tuple[tuple[str, Path], ...] = ()
) -> tuple[str, str] | None:
    """The first two outputs that resolve to one destination, as `(first, second)` labels.

    The one collision rule (plan 3.6.1 B). It walks `relative_outputs`, so every local file
    target and enabled quarantine takes part; `base` is the folder relative paths land in
    (None when it is unknown), and `typed` adds the side files by flag name. URLs and remote
    targets do not take part. Labels are config locations or flag names, never path values.
    """
    seen: dict[tuple, str] = {}
    entries: dict[tuple, str] = {}
    destinations: list[tuple[str, Path, bool]] = []
    for location, raw in relative_outputs(config_dict):
        if Path(raw).is_absolute():
            # As written, like the writer opens it: collapsing ".." as text first would name
            # the wrong folder when the part before it is a symlink.
            destinations.append((location, Path(raw), replaces_final(location)))
        elif is_placed_relative(raw) and base is not None and names_a_file_inside(raw):
            destinations.append(
                (location, Path(os.path.normpath(base / raw)), replaces_final(location))
            )
    destinations.extend((flag, Path(path).absolute(), replaces_final(flag)) for flag, path in typed)
    for label, path, replaces in destinations:
        key = _destination_key(path, replaces_final=replaces)
        # A writer that replaces a final link turns it into a file, and a later writer that
        # follows the same name would then replace that file, so one name is one destination
        # whichever way each writer treats the link.
        entry = key if replaces else _destination_key(path, replaces_final=True)
        first = seen.get(key) or entries.get(entry)
        if first is not None:
            return first, label
        seen[key] = label
        entries[entry] = label
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
    elif placed or urls:
        yaml = config.resolve()
        try:
            root = find_project(yaml.parent, None).root
            name = pipeline_name_for(root, yaml, config_dict.get("name")).name
            folder, base = pipeline_folder(root, name), f"out/{name}/<run-id>"
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
            root = find_project(config.resolve().parent, None).root
            # Same naming rule as local delivery; the name itself is used from CC2a on.
            pipeline_name_for(root, config.resolve(), config_dict.get("name"))
            project_out = project_out_folder(root)
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
        clash = resolved_output_collisions(config_dict, where, placement.typed)
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

    The project is the one given, else the marker folder above the YAML, else the YAML's folder.
    None when the name is refused; the caller then reads files by the suffix rule alone.
    """
    from decoy.cli.io._project import find_project

    yaml = config.resolve()
    try:
        root = (project or find_project(yaml.parent, None)).root
        return root, pipeline_name_for(root, yaml, declared).name
    except LayoutError:
        return None


def run_report_path(kind: str, file: Path, ref: PipelineRef | None) -> Path | None:
    """Where `report <kind>` writes by default: `<run>/reports/<kind>.json` for a run output.

    The run is looked for under the pipeline's project, the config's folder and the project
    found from the file. None for any other file, so nothing new is written for it.
    """
    from decoy.cli.io._project import find_project

    roots = [ref.project.root] if ref is not None and ref.project is not None else []
    if ref is not None:
        roots.append(ref.yaml.resolve().parent)
    try:
        roots.append(find_project(file.resolve().parent, None).root)
    except LayoutError:
        pass
    return report_default_path(kind, file, tuple(roots))
