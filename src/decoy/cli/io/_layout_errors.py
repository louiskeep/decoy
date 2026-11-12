"""The `layout.*` descriptors: one registry of codes and fixed, value-free messages.

Every refusal and warning of the project layout (project root, pipeline names, run folders)
is built from a `Descriptor` here. A message template names folders, files, pipeline names
and counts, never a row value, and no other module writes a `layout.*` code as a literal
(`tests/sentry/io_policy/test_layout_errors.py`). Gate findings, command errors and the CI
rule-code set all read this registry through the public `decoy.cli.io` package.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutWarning:
    """A runtime warning that never changes an exit code."""

    code: str
    message: str


class LayoutError(Exception):
    """A refusal with a registry code; the text is the descriptor's message, nothing else.

    Callers exit 1 with it (the gate and every command body use the same code and text).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Descriptor:
    """One code with its fixed message template; `{field}` slots take paths, names or counts."""

    code: str
    template: str

    def message(self, **fields: object) -> str:
        return self.template.format(**fields)

    def warning(self, **fields: object) -> LayoutWarning:
        return LayoutWarning(self.code, self.message(**fields))

    def error(self, **fields: object) -> LayoutError:
        return LayoutError(self.code, self.message(**fields))


PROJECT_MARKER_INVALID = Descriptor(
    "layout.project_marker_invalid",
    "{path} is not a valid Decoy project marker: it must be a small YAML file with "
    "`kind: decoy-project/v1`, owned by you and not a link.",
)
PROJECT_MARKER_UNTRUSTED = Descriptor(
    "layout.project_marker_untrusted",
    "The project marker {path} belongs to another user, so it is not trusted. Remove the file, "
    "or make your user its owner.",
)
PROJECT_NOT_FOUND = Descriptor(
    "layout.project_not_found",
    "No Decoy project found for {where}. Make one with `project new <dir>`, "
    "or pass a pipeline path.",
)
PROJECT_MISMATCH = Descriptor(
    "layout.project_mismatch",
    "{path} is in the project {actual}, but --project or DECOY_PROJECT names {given}.",
)
PIPELINE_UNKNOWN = Descriptor(
    "layout.pipeline_unknown",
    "No pipeline named {name} in {root}. Known pipelines: {known}.{close}",
)
PIPELINE_NAME_INVALID = Descriptor(
    "layout.pipeline_name_invalid",
    "{name} is not a valid pipeline name: use 1 to 64 letters, digits, `_`, `.` or `-`, "
    "start with a letter or digit, do not end with `.`, and avoid Windows device names.",
)
PIPELINE_NAME_MISMATCH = Descriptor(
    "layout.pipeline_name_mismatch",
    "{path} declares the name {declared}, but its folder is {folder}. "
    "Change `name:` or rename the folder.",
)
PIPELINE_NAME_COLLISION = Descriptor(
    "layout.pipeline_name_collision",
    "The pipeline name {name} is already used by {other} (claim {claim}). "
    "Set a different `name:` or rename one YAML, or delete the claim file.",
)
OUTPUT_PATH_ESCAPES = Descriptor(
    "layout.output_path_escapes",
    "The output location {path} is not inside {base}. A relative output path must name a "
    "file under its run folder.",
)
PATH_TOO_LONG = Descriptor(
    "layout.path_too_long",
    "The output path would be {length} characters long as Windows counts them; Windows allows {limit}. "
    "Shorten the project path, the pipeline name or the output path.",
)
OUTPUT_PATH_COLLISION = Descriptor(
    "layout.output_path_collision",
    "Configured outputs {first} and {second} resolve to one destination. "
    "Give each output a different path.",
)
OUTPUT_DIR_UNUSABLE = Descriptor(
    "layout.output_dir_unusable",
    "--out-dir must name an existing directory, or a new directory whose parent exists.",
)
PROJECT_ROOT_REFUSED = Descriptor(
    "layout.project_root_refused",
    "{path} cannot be a project root: it is your home folder, one of its parents, or `/`.",
)

LATEST_INVALID = Descriptor(
    "layout.latest_invalid",
    "The LATEST file in {path} is not a run folder name; it is ignored until the next clean run.",
)
LATEST_LINK_FAILED = Descriptor(
    "layout.latest_link_failed",
    "Could not make the `current` link in {path}; LATEST still names the last clean run.",
)
LATEST_WRITE_FAILED = Descriptor(
    "layout.latest_write_failed",
    "Could not write LATEST in {path}; the run itself is unaffected.",
)
GITIGNORE_WRITE_FAILED = Descriptor(
    "layout.gitignore_write_failed",
    "Could not write {path}; the run goes on without it.",
)
PROJECT_NESTED = Descriptor(
    "layout.project_nested",
    "{path} is inside another project ({outer}).",
)
CONFIG_INSIDE_OUT = Descriptor(
    "layout.config_inside_out",
    "The pipeline YAML {path} is inside an out/ folder, where run folders live.",
)

# Codes a gate or command can refuse with (exit 1); the CI rule-code set is derived from them.
GATE_DESCRIPTORS: tuple[Descriptor, ...] = (
    PROJECT_MARKER_INVALID,
    PROJECT_MARKER_UNTRUSTED,
    PROJECT_NOT_FOUND,
    PROJECT_MISMATCH,
    PIPELINE_UNKNOWN,
    PIPELINE_NAME_INVALID,
    PIPELINE_NAME_MISMATCH,
    PIPELINE_NAME_COLLISION,
    OUTPUT_PATH_ESCAPES,
    PATH_TOO_LONG,
    OUTPUT_PATH_COLLISION,
    OUTPUT_DIR_UNUSABLE,
    PROJECT_ROOT_REFUSED,
)
WARNING_DESCRIPTORS: tuple[Descriptor, ...] = (
    LATEST_INVALID,
    LATEST_LINK_FAILED,
    LATEST_WRITE_FAILED,
    GITIGNORE_WRITE_FAILED,
    PROJECT_NESTED,
    CONFIG_INSIDE_OUT,
)
GATE_CODES: frozenset[str] = frozenset(d.code for d in GATE_DESCRIPTORS)
WARNING_CODES: frozenset[str] = frozenset(d.code for d in WARNING_DESCRIPTORS)
