"""The retention policy model: `.decoy/library.yaml`, one strict pydantic model (plan 4.7; L1b.3).

An absent or empty file means the defaults below; docs render from this model. Nothing enforces
retention yet: L4b's prune and L5b's log rotation read it. The file is per machine and per
project, so it is not part of the pipeline YAML (which the platform compiles) and is YAML, not
TOML, because Python 3.10 has no `tomllib`.

The file is read through `decoy.cli.io.read_small_file` (a regular file only, no links, pipes or
devices; 64 KiB at most) and parsed with `yaml.safe_load`, as the project marker is. Every
model is `extra="forbid"` with strict types, so a typo or `"30"` for a number is refused. A bad
file is `library_policy_invalid` carrying the failing field locations only: the YAML parser's
message and pydantic's input both hold the file's text, so neither is kept or chained. The
locations come from the engine's `safe_output.validation_problems`, the one value-free reading
of a pydantic error; the error is caught as `ValueError` so the CLI never imports pydantic's
`ValidationError` (tests/sentry/defects/test_config_error_routes.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, cast

import yaml
from decoy_engine import records
from decoy_engine.safe_output import validation_problems
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from decoy.cli.io import UnsafeFileError, read_small_file
from decoy.cli.library._errors import LIBRARY_POLICY_INVALID, LibraryError
from decoy.cli.library._paths import POLICY_FILE

__all__ = [
    "KeepAll",
    "KeepLast",
    "LibraryPolicy",
    "LogRetention",
    "RecordRetention",
    "Retention",
    "ScratchRetention",
    "load_policy",
]

MAX_POLICY_BYTES = 64 * 1024
_Positive = Annotated[StrictInt, Field(ge=1)]
_MAX_FIELDS = 8


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class KeepAll(_Strict):
    keep: Literal["all"] = "all"


class KeepLast(_Strict):
    keep_last: _Positive


RecordRule = KeepAll | KeepLast


class RecordRetention(_Strict):
    """`default` applies to every kind; any other key is a registered kind's override."""

    default: RecordRule = Field(default_factory=KeepAll)
    kinds: dict[str, RecordRule] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _split_kinds(cls, data: Any) -> Any:
        # The file writes overrides beside `default` (`run-result: {keep_last: 500}`).
        if not isinstance(data, dict):
            return data
        split: dict[str, Any] = {"kinds": {k: v for k, v in data.items() if k != "default"}}
        if "default" in data:
            split["default"] = data["default"]
        return split

    @field_validator("kinds")
    @classmethod
    def _registered(cls, kinds: dict[str, RecordRule]) -> dict[str, RecordRule]:
        known = {spec.kind for spec in records.registered_kinds()}
        if set(kinds) - known:
            raise ValueError("not a registered record kind")
        return kinds


class LogRetention(_Strict):
    keep_last_runs_per_pipeline: _Positive = 50
    max_age_days: _Positive = 30


class ScratchRetention(_Strict):
    sample_ttl_hours: _Positive = 24
    staging: Literal["delete_on_exit"] = "delete_on_exit"


class Retention(_Strict):
    records: RecordRetention = Field(default_factory=RecordRetention)
    logs: LogRetention = Field(default_factory=LogRetention)
    scratch: ScratchRetention = Field(default_factory=ScratchRetention)


class LibraryPolicy(_Strict):
    retention: Retention = Field(default_factory=Retention)


def load_policy(root: Path) -> LibraryPolicy:
    """The policy in `<root>/library.yaml`, or the defaults when there is none. Raises
    `LibraryError` (`library_policy_invalid`)."""
    unsafe = False
    found = None
    try:
        found = read_small_file(root / POLICY_FILE, MAX_POLICY_BYTES + 1)
    except UnsafeFileError:
        unsafe = True
    if unsafe or (found is not None and found.size > MAX_POLICY_BYTES):
        raise LibraryError(LIBRARY_POLICY_INVALID)
    if found is None:
        return LibraryPolicy()
    parsed: object = None
    broken = False
    try:
        parsed = yaml.safe_load(found.data)
    except (yaml.YAMLError, UnicodeDecodeError, RecursionError):
        broken = True
    if broken or not (parsed is None or isinstance(parsed, dict)):
        raise LibraryError(LIBRARY_POLICY_INVALID)
    fields: tuple[str, ...] = ()
    try:
        return LibraryPolicy.model_validate(parsed or {})
    except ValueError as exc:  # pydantic's ValidationError; see the module docstring
        fields = tuple(dict.fromkeys(p.location for p in validation_problems(cast(Any, exc))))
    raise LibraryError(LIBRARY_POLICY_INVALID, fields=fields[:_MAX_FIELDS])
