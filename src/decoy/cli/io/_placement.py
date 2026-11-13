"""The gate's view of output placement: where relative outputs land and what may collide.

`OutputPlacement` is the one route decision (project run folder, typed `--out-dir`, or a
no-write preview). `layout_issues` is the gate's single layout check for `validate`, `ci check`,
`validate preflight` and `run`; the one collision rule (`resolved_output_collisions`) runs inside
it, so no route has a second collision loop. Path rules come from `_layout.py`, one way.
"""

from __future__ import annotations

import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from decoy._atomic import destination_entry
from decoy.cli.io._layout import (
    _same_dir,
    check_path_budget,
    contained_path,
    is_placed_relative,
    names_a_file_inside,
    pipeline_folder,
    pipeline_name_for,
    relative_outputs,
)
from decoy.cli.io._layout_errors import (
    DELIVERY_ROOT_SPLIT,
    OUTPUT_PATH_COLLISION,
    OUTPUT_PATH_ESCAPES,
    SIDE_FILE_IN_OUT,
    LayoutError,
)


@dataclass(frozen=True)
class OutputPlacement:
    """Where relative outputs land for one gate call (plan 3.6.1): the one route decision.

    `project` is normal placement under `<root>/out/<name>/<run-id>/`; `fixed` is a typed
    `--out-dir` (`directory`); `preview` is a `--rows` run that writes nothing. `typed` holds
    the `(flag, path)` side files (`--evidence-out`, `--vault`) that join the collision rule.
    """

    kind: str = "project"
    directory: Path | None = None
    typed: tuple[tuple[str, Path], ...] = ()

    @classmethod
    def fixed(cls, directory: Path, typed: tuple[tuple[str, Path], ...] = ()) -> OutputPlacement:
        return cls("fixed", Path(os.path.abspath(directory)), typed)

    @classmethod
    def preview(cls) -> OutputPlacement:
        return cls("preview")


def _folds_case(folder: Path) -> bool:
    """True when the existing `folder` sits on a case-insensitive filesystem.

    Probed without writing: swap the case of the nearest alphabetic path component and ask
    whether that spelling is the same directory.
    """
    for part in (folder, *folder.parents):
        swapped = part.name.swapcase()
        if swapped != part.name:
            return _same_dir(part.with_name(swapped), part)
    return False


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
    try:
        real = destination_entry(path, follow_final=not replaces_final)
    except (OSError, ValueError):
        # The read-only gate stays lenient where a writer must fail strict parent resolution.
        try:
            absolute = path.absolute()
            parent = Path(os.path.realpath(absolute.parent))
            real = parent / absolute.name if replaces_final else Path(os.path.realpath(path))
        except (OSError, ValueError):
            real = path
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


def _destination_is_within(child: Path, parent: Path) -> bool:
    """True when `child` or one of its lexical ancestors is the same destination as `parent`.

    Identity comes only from `_destination_key`, so links, case folding and missing paths
    behave as they do for the collision rule. The caller resolves `child` first.
    """
    target = _destination_key(parent)
    return any(_destination_key(path) == target for path in (child, *child.parents))


def _split_root(config_dict: dict, fixed: Path | None = None) -> tuple[str, str] | None:
    """The first two local file outputs that do not share one delivery root, as labels.

    Relative outputs share the run folder, or the `--out-dir` folder when `fixed` is set;
    absolute ones must share one parent folder, judged by `_destination_key`. In a project a
    relative and an absolute output never share; under `--out-dir` an absolute output directly
    in that folder shares with the relative ones.
    """
    relative_key = _destination_key(fixed) if fixed is not None else ("relative",)
    roots: list[tuple[str, tuple]] = []
    for location, raw in relative_outputs(config_dict):
        if is_placed_relative(raw):
            roots.append((location, relative_key))
        elif Path(raw).is_absolute():
            roots.append((location, _destination_key(Path(raw).parent)))
    return next(((roots[0][0], loc) for loc, key in roots[1:] if key != roots[0][1]), None)


def _side_file_in_out(out: Path, typed: tuple[tuple[str, Path], ...]) -> str | None:
    """The flag of the first side file whose destination is under the project's `out/` folder."""
    for flag, path in typed:
        try:
            # Only the parent is resolved: a writer that replaces a final link writes here.
            absolute = Path(path).absolute()
            resolved = absolute.parent.resolve() / absolute.name
        except (OSError, RuntimeError, ValueError):
            continue
        if _destination_is_within(resolved, out):
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
            destinations.append((location, Path(raw), False))
        elif is_placed_relative(raw) and base is not None and names_a_file_inside(raw):
            destinations.append((location, Path(os.path.normpath(base / raw)), False))
    destinations.extend((flag, Path(path).absolute(), flag == "--vault") for flag, path in typed)
    for label, path, replaces_final in destinations:
        key = _destination_key(path, replaces_final=replaces_final)
        # A writer that replaces a final link turns it into a file, and a later writer that
        # follows the same name would then replace that file, so one name is one destination
        # whichever way each writer treats the link.
        entry = key if replaces_final else _destination_key(path, replaces_final=True)
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
