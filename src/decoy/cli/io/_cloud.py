"""The cloud delivery root: what a run's S3 or GCS targets must share, checked offline.

`cloud_root_issues` is the gate's cloud arm (called from `layout_issues`); nothing here
contacts a network. Objects will land at `<dir>/<pipeline>/runs/<run_id>/<basename>` with the
pointer at `<dir>/<pipeline>/CURRENT`, so two pipelines in one directory keep two pointers.
Messages name tables and fields, never a key, bucket or endpoint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from decoy.cli.io._layout import new_run_id, quarantine_enabled, relative_outputs
from decoy.cli.io._layout_errors import (
    CLOUD_TARGET_INVALID,
    CLOUD_TARGET_UNSUPPORTED,
    DELIVERY_ROOT_SPLIT,
    LayoutError,
)

# Key field per cloud type. GCS stays refused until real-bucket evidence exists (AT-C40).
_KEY_FIELD = {"s3": "key", "gcs": "object"}
_UNSUPPORTED_TYPES = frozenset({"gcs"})
_RESERVED_BASENAME = "MANIFEST"
# Fullmatch, never match: a trailing newline or a later bad segment must not pass.
_KEY = re.compile(r"[^/\x00-\x1f\x7f-\x9f]+(?:/[^/\x00-\x1f\x7f-\x9f]+)*")
_RUN_ID_EXTRA_BLOCKS = 6

Issue = tuple[str | None, LayoutError]


@dataclass(frozen=True)
class CloudRoot:
    """The one root every cloud target of a run shares, parsed from a checked config."""

    type: str
    bucket: str
    region: str | None
    dir: str
    pipeline: str
    basenames: tuple[tuple[str, str], ...]  # (table, basename), sorted by table

    @property
    def prefix(self) -> str:
        return "/".join(part for part in (self.dir, self.pipeline) if part)

    @property
    def pointer_key(self) -> str:
        return f"{self.prefix}/CURRENT"


def new_cloud_run_id(started: datetime, invocation_id: str) -> str:
    """A run id with all 32 digits of the invocation id: no folder exists to clash on."""
    return new_run_id(started, invocation_id, extra_blocks=_RUN_ID_EXTRA_BLOCKS)


def _cloud_targets(config_dict: dict) -> dict[str, dict]:
    targets = config_dict.get("targets")
    if not isinstance(targets, dict):
        return {}
    return {
        str(table): entry
        for table, entry in targets.items()
        if isinstance(entry, dict) and entry.get("type") in _KEY_FIELD
    }


def has_cloud_targets(config_dict: dict) -> bool:
    return bool(_cloud_targets(config_dict))


def _split_key(entry: dict) -> tuple[str, str] | None:
    raw = entry.get(_KEY_FIELD[entry["type"]])
    if not isinstance(raw, str):
        return None
    directory, _, basename = raw.rpartition("/")
    return directory, basename


def _key_is_plain(raw: object) -> bool:
    return (
        isinstance(raw, str)
        and _KEY.fullmatch(raw) is not None
        and not any(part in (".", "..") for part in raw.split("/"))
    )


def _unsupported(table: str, field: str) -> Issue:
    return None, CLOUD_TARGET_UNSUPPORTED.error(subject=f"table {table}", field=field)


def _unsupported_issues(config_dict: dict, cloud: dict[str, dict], chunked: bool) -> list[Issue]:
    issues: list[Issue] = []
    first = next(iter(cloud))
    for table, entry in cloud.items():
        if entry["type"] in _UNSUPPORTED_TYPES:
            issues.append(_unsupported(table, "type"))
        # endpoint_url stays allowed on sources: reads need no preconditions (Q-C).
        for field in ("credentials_ref", "endpoint_url"):
            if entry.get(field) is not None:
                issues.append(_unsupported(table, field))
    if quarantine_enabled(config_dict):
        issues.append(_unsupported(first, "quarantine.enabled"))
    if chunked:
        issues.append(_unsupported(first, "--chunked"))
    return issues


def _key_issues(cloud: dict[str, dict]) -> list[Issue]:
    issues: list[Issue] = []
    seen: dict[str, str] = {}
    for table, entry in cloud.items():
        subject = f"table {table}"
        field = _KEY_FIELD[entry["type"]]
        if not isinstance(entry.get(field), str):
            continue  # a missing or non-string key is the engine schema's refusal
        if not _key_is_plain(entry.get(field)):
            issues.append(
                (
                    f"targets.{table}.{field}",
                    CLOUD_TARGET_INVALID.error(
                        subject=subject,
                        rule=f"has a {field} that is not a plain object path (no leading or "
                        "trailing slash, empty or dot segment, or control character)",
                    ),
                )
            )
            continue
        _directory, basename = _split_key(entry) or ("", "")
        if basename == _RESERVED_BASENAME:
            issues.append(
                (
                    f"targets.{table}.{field}",
                    CLOUD_TARGET_INVALID.error(
                        subject=subject, rule="uses the reserved file name MANIFEST"
                    ),
                )
            )
        elif basename in seen:
            issues.append(
                (
                    f"targets.{table}.{field}",
                    CLOUD_TARGET_INVALID.error(
                        subject=subject, rule=f"shares its file name with table {seen[basename]}"
                    ),
                )
            )
        else:
            seen[basename] = table
    return issues


def _split_issues(config_dict: dict, cloud: dict[str, dict]) -> list[Issue]:
    """The first output that leaves the root the first cloud target sets, as two labels."""
    files = [
        location
        for location, _raw in relative_outputs(config_dict)
        if location.startswith("targets.")
    ]
    first_table, first = next(iter(cloud.items()))
    if files:
        label = f"targets.{first_table}.{_KEY_FIELD[first['type']]}"
        return [(None, DELIVERY_ROOT_SPLIT.error(first=files[0], second=label))]
    first_dir = (_split_key(first) or ("", ""))[0]
    for table, entry in list(cloud.items())[1:]:
        key_field = _KEY_FIELD[entry["type"]]
        for name, same in (
            ("type", entry["type"] == first["type"]),
            ("bucket", entry.get("bucket") == first.get("bucket")),
            ("region", entry.get("region") == first.get("region")),
            (key_field, (_split_key(entry) or ("", ""))[0] == first_dir),
        ):
            if not same:
                return [
                    (
                        None,
                        DELIVERY_ROOT_SPLIT.error(
                            first=f"targets.{first_table}.{name}", second=f"targets.{table}.{name}"
                        ),
                    )
                ]
    return []


def cloud_root_issues(config_dict: dict, *, chunked: bool = False) -> list[Issue]:
    """The cloud root rule's refusals for a config, empty when it has no cloud target."""
    cloud = _cloud_targets(config_dict)
    if not cloud:
        return []
    return [
        *_unsupported_issues(config_dict, cloud, chunked),
        *_key_issues(cloud),
        *_split_issues(config_dict, cloud),
    ]


def cloud_root(config_dict: dict, pipeline: str) -> CloudRoot | None:
    """The root of a config's cloud targets, None when it has none or they do not share one."""
    cloud = _cloud_targets(config_dict)
    if not cloud or cloud_root_issues(config_dict):
        return None
    first = next(iter(cloud.values()))
    basenames = tuple(sorted((table, (_split_key(e) or ("", ""))[1]) for table, e in cloud.items()))
    return CloudRoot(
        type=first["type"],
        bucket=first["bucket"],
        region=first.get("region"),
        dir=(_split_key(first) or ("", ""))[0],
        pipeline=pipeline,
        basenames=basenames,
    )
