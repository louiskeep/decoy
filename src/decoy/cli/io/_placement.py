"""The gate's view of output placement: where relative outputs land and what may collide.

`OutputPlacement` is the one route decision (project run folder, typed `--out-dir`, or a
no-write preview). `layout_issues` is the gate's single layout check for `validate`, `ci check`,
`validate preflight` and `run`; the one collision rule (`resolved_output_collisions`) runs inside
it, so no route has a second collision loop. Path rules come from `_layout.py`, one way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
from decoy.cli.io._layout_errors import OUTPUT_PATH_COLLISION, OUTPUT_PATH_ESCAPES, LayoutError


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


def _destination_key(path: Path) -> tuple:
    """What two spellings of one destination share: file identity if it exists, else the
    resolved nearest existing folder plus the unresolved suffix (case-folded on a folding
    filesystem)."""
    try:
        found = os.stat(path)
    except (OSError, ValueError):
        found = None
    if found is not None:
        return ("file", found.st_dev, found.st_ino)
    ancestor = next((p for p in path.parents if p.is_dir()), Path(path.anchor))
    try:
        resolved = ancestor.resolve()
    except (OSError, RuntimeError):
        resolved = ancestor
    suffix = path.relative_to(ancestor).parts
    if _folds_case(resolved):
        suffix = tuple(part.casefold() for part in suffix)
    return ("path", str(resolved), suffix)


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
    destinations: list[tuple[str, Path]] = []
    for location, raw in relative_outputs(config_dict):
        if Path(raw).is_absolute():
            destinations.append((location, Path(os.path.abspath(raw))))
        elif is_placed_relative(raw) and base is not None and names_a_file_inside(raw):
            destinations.append((location, Path(os.path.normpath(base / raw))))
    destinations.extend((flag, Path(os.path.abspath(path))) for flag, path in typed)
    for label, path in destinations:
        key = _destination_key(path)
        if key in seen:
            return seen[key], label
        seen[key] = label
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
    each path to the physical directory instead; a preview checks nothing. Last, no two
    outputs may resolve to one destination.
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
    base = "--out-dir" if fixed is not None else "its run folder"
    if fixed is not None:
        folder = fixed.resolve() if fixed.exists() else fixed
    elif placed or urls:
        yaml = config.resolve()
        try:
            root = find_project(yaml.parent, None).root
            name = pipeline_name_for(root, yaml, config_dict.get("name")).name
            folder, base = pipeline_folder(root, name), f"out/{name}/<run-id>"
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
