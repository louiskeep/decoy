"""The one list of every file `decoy run` writes outside the record library.

`run_outputs` is the only input of the collision rule (`resolved_output_collisions`), so a
writer that is not listed here is not protected, and the write audit in
`tests/sentry/io_policy/run_outputs/` fails when a run writes a file this list does not name.
Each entry carries a label (a config location or a flag name, never a path value), its kind, the
path the writer opens and whether that writer replaces a final link.

Writes under the library root (records, index, scratch) belong to the library and are not here.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from decoy.cli.io._layout import (
    _CLAIM_NAME,
    _LATEST_FILE,
    _LATEST_LINK,
    has_placed_output,
    is_placed_relative,
    names_a_file_inside,
    relative_outputs,
    side_file_name,
)

if TYPE_CHECKING:
    from decoy.cli.io._placement import OutputPlacement

__all__ = [
    "OutputKind",
    "RunOutput",
    "implicit_report_path",
    "replaces_final",
    "run_outputs",
]

RUN_FOLDER = "the run folder"
IMPLICIT_REPORT = "the integrity report"


class OutputKind(str, Enum):
    TARGET = "target"
    QUARANTINE = "quarantine"
    INTEGRITY_EXPLICIT = "integrity-explicit"
    INTEGRITY_IMPLICIT = "integrity-implicit"
    RESULT = "result"
    EVIDENCE = "evidence"
    VAULT = "vault"
    LAYOUT = "layout"


# The side file each typed flag names.
_FLAG_KINDS = {
    "--integrity-out": OutputKind.INTEGRITY_EXPLICIT,
    "--result": OutputKind.RESULT,
    "--evidence-out": OutputKind.EVIDENCE,
    "--vault": OutputKind.VAULT,
}
# The one policy for a destination's final path component. A writer either follows a final
# symlink (file targets, quarantine, `--evidence-out` and `--result`, which use
# `write_local_target` REPLACE) or replaces it with a file (`--vault`). Everything not listed
# follows. The split root, the side-file check and the collision rule all read this.
_REPLACES_FINAL = frozenset({"--vault"})


def replaces_final(label: str) -> bool:
    """True when the writer behind `label` (a config location or flag) replaces a final link."""
    return label in _REPLACES_FINAL


@dataclass(frozen=True)
class RunOutput:
    """One file a run writes: `label` names it in a refusal, `path` is where the writer opens it."""

    label: str
    kind: OutputKind
    path: Path
    replaces_final: bool = False


def implicit_report_path(placed: Path, config_path: Path) -> Path:
    """The default post-scan report: beside the first target, named from the config.

    The one derivation of that name. It takes the placed path, never the raw text, so
    `--out-dir` and project placement both count; the gate and the writer share it.
    """
    return placed.parent / side_file_name("post_scan", Path(config_path).stem)


def _declared(raw: str, base: Path | None) -> Path | None:
    """The path a declared output opens: as written when absolute, else placed on `base`."""
    if Path(raw).is_absolute():
        # As written, like the writer opens it: collapsing ".." as text first would name
        # the wrong folder when the part before it is a symlink.
        return Path(raw)
    if is_placed_relative(raw) and base is not None and names_a_file_inside(raw):
        return Path(os.path.normpath(base / raw))
    return None


def _declared_outputs(config_dict: dict, base: Path | None) -> list[RunOutput]:
    found: list[RunOutput] = []
    for location, raw in relative_outputs(config_dict):
        path = _declared(raw, base)
        if path is not None:
            kind = OutputKind.QUARANTINE if location.startswith("quarantine") else OutputKind.TARGET
            found.append(RunOutput(location, kind, path, replaces_final(location)))
    return found


def _implicit_report(config_dict: dict, config_path: Path, base: Path | None) -> RunOutput | None:
    """The default report path when the integrity suite is asked for and `--integrity-out` is not
    given: derived from the first target, whatever its type, as the writer does."""
    from decoy_engine.config import post_scan_integrity_requested

    if not post_scan_integrity_requested(config_dict):
        return None
    first = next(iter((config_dict.get("targets") or {}).values()), None)
    raw = first.get("path") if isinstance(first, Mapping) else None
    placed = _declared(raw, base) if isinstance(raw, str) and "://" not in raw else None
    if placed is None:
        return None
    return RunOutput(
        IMPLICIT_REPORT, OutputKind.INTEGRITY_IMPLICIT, implicit_report_path(placed, config_path)
    )


def _layout_outputs(base: Path) -> list[RunOutput]:
    """What the project layout writes around a run folder `base` (`out/<name>/<run-id>`)."""
    pipeline = base.parent
    found = [
        pipeline.parent / ".gitignore",
        pipeline / _CLAIM_NAME,
        pipeline / _LATEST_FILE,
        base,
    ]
    if os.name == "posix":
        found.insert(3, pipeline / _LATEST_LINK)
    return [RunOutput(RUN_FOLDER, OutputKind.LAYOUT, path) for path in found]


def run_outputs(
    config_dict: dict,
    placement: OutputPlacement,
    config_path: Path,
    base: Path | None,
) -> tuple[RunOutput, ...]:
    """Every file this run writes outside the library, in a fixed order.

    `base` is the folder relative outputs land in (None when it is unknown). The project run
    folder's own files are listed only under project placement with a relative output.
    """
    declared = _declared_outputs(config_dict, base)
    typed: dict[OutputKind, list[RunOutput]] = {kind: [] for kind in _FLAG_KINDS.values()}
    for flag, path in placement.typed:
        kind = _FLAG_KINDS[flag]
        typed[kind].append(RunOutput(flag, kind, Path(path).absolute(), replaces_final(flag)))
    implicit = (
        []
        if typed[OutputKind.INTEGRITY_EXPLICIT]
        else [out for out in [_implicit_report(config_dict, config_path, base)] if out]
    )
    layout = (
        _layout_outputs(base)
        if placement.kind == "project" and base is not None and has_placed_output(config_dict)
        else []
    )
    return (
        *declared,
        *typed[OutputKind.INTEGRITY_EXPLICIT],
        *implicit,
        *typed[OutputKind.RESULT],
        *typed[OutputKind.EVIDENCE],
        *typed[OutputKind.VAULT],
        *layout,
    )
