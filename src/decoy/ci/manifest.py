"""Strict loading of a `decoy-ci/v1` manifest, path containment, and the generated schema.

`yaml.safe_load` alone accepts anchors, aliases, merge keys, duplicate keys, explicit tags
and multi-document streams. The manifest contract forbids all of them, so the text is
checked on the PyYAML EVENT stream (which still shows anchors/aliases/tags) and loaded
through a duplicate-key-rejecting SafeLoader before Pydantic ever sees it.

Errors are `ManifestError(reason_code)`: the message is the fixed reason code, never any
input text, so a bad manifest cannot leak its own contents into a report or log.

Prior art: Pydantic v2 `extra="forbid"` models and `model_json_schema()` as the single
source of the committed JSON Schema; the PyYAML event API for tag/anchor inspection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from decoy.ci import CI_MANIFEST_VERSION
from decoy.ci._git import GitBudget, toplevel
from decoy.ci.contracts import CiManifest

MAX_MANIFEST_BYTES = 1024 * 1024
SCHEMA_ID = "https://github.com/louiskeep/decoy/blob/main/docs/schemas/decoy-ci-v1.schema.json"

_ALLOWED_TAGS = frozenset(
    f"tag:yaml.org,2002:{t}" for t in ("str", "int", "float", "bool", "null", "map", "seq")
)


class ManifestError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True)
class LoadedManifest:
    manifest: CiManifest
    manifest_path: Path
    base_dir: Path
    root: Path

    def resolve(self, rel: str) -> Path:
        """Absolute path for a manifest reference, contained in the root."""
        return _contained(self.base_dir, rel, self.root)

    def repo_relative(self, absolute: Path) -> str | None:
        """POSIX path relative to the root, or None if the path is outside it."""
        try:
            return absolute.relative_to(self.root).as_posix()
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Strict YAML
# ---------------------------------------------------------------------------


class _StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                if key in seen:
                    raise ManifestError("ci.manifest_invalid")
                seen.add(key)
            except TypeError:
                raise ManifestError("ci.manifest_invalid") from None
        return super().construct_mapping(node, deep=deep)


def _check_events(text: str) -> None:
    documents = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.DocumentStartEvent):
            documents += 1
            if documents > 1:
                raise ManifestError("ci.manifest_invalid")
        elif isinstance(event, yaml.AliasEvent):
            raise ManifestError("ci.manifest_invalid")
        elif isinstance(event, yaml.NodeEvent):
            if event.anchor is not None:
                raise ManifestError("ci.manifest_invalid")
            tag = getattr(event, "tag", None)
            if tag is not None and tag not in _ALLOWED_TAGS:
                raise ManifestError("ci.manifest_invalid")
            if isinstance(event, yaml.ScalarEvent) and event.value == "<<" and event.implicit[0]:
                raise ManifestError("ci.manifest_invalid")


def _parse(text: str) -> dict[str, Any]:
    try:
        _check_events(text)
        data = yaml.load(text, Loader=_StrictLoader)
    except ManifestError:
        raise
    except (yaml.YAMLError, ValueError, RecursionError):
        raise ManifestError("ci.manifest_invalid") from None
    if not isinstance(data, dict):
        raise ManifestError("ci.manifest_invalid")
    return data


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _contained(base: Path, rel: str, root: Path) -> Path:
    try:
        resolved = (base / rel).resolve()
        resolved.relative_to(root)
    except (ValueError, OSError, RuntimeError):
        raise ManifestError("ci.manifest_path_rejected") from None
    return resolved


def _check_paths(manifest: CiManifest, base: Path, root: Path) -> None:
    seen_pipelines: set[Path] = set()
    for ref in manifest.pipelines:
        resolved = _contained(base, ref.path, root)
        if resolved.exists() and not resolved.is_file():
            raise ManifestError("ci.manifest_path_rejected")
        if resolved in seen_pipelines:
            raise ManifestError("ci.manifest_path_rejected")
        seen_pipelines.add(resolved)
    for drift in manifest.checks.drift:
        for rel in (drift.baseline, drift.current):
            resolved = _contained(base, rel, root)
            if resolved.exists() and not resolved.is_file():
                raise ManifestError("ci.manifest_path_rejected")
    for ev in manifest.checks.evidence:
        resolved = _contained(base, ev.manifest, root)
        if resolved.exists() and not resolved.is_file():
            raise ManifestError("ci.manifest_path_rejected")
    for reg in manifest.checks.regression_suites:
        _contained(base, reg.suite, root)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(path: Path, *, root: Path | None = None) -> LoadedManifest:
    manifest_path = Path(path)
    try:
        if not manifest_path.is_file():
            raise ManifestError("ci.manifest_unreadable")
        raw = manifest_path.read_bytes()
    except OSError:
        raise ManifestError("ci.manifest_unreadable") from None
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError("ci.manifest_invalid")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ManifestError("ci.manifest_invalid") from None

    data = _parse(text)
    version = data.get("schema_version")
    if (
        isinstance(version, str)
        and version != CI_MANIFEST_VERSION
        and version.startswith("decoy-ci/")
    ):
        raise ManifestError("ci.manifest_version_unsupported")
    try:
        manifest = CiManifest.model_validate(data)
    except ValidationError as exc:
        # Only the machine `type` of each error is inspected; `input` is never read.
        if any(e.get("type") == "path_rejected" for e in exc.errors(include_input=False)):
            raise ManifestError("ci.manifest_path_rejected") from None
        raise ManifestError("ci.manifest_invalid") from None

    base_dir = manifest_path.resolve().parent
    if root is None:
        root = toplevel(base_dir, GitBudget(10)) or base_dir
    root = root.resolve()
    _check_paths(manifest, base_dir, root)
    return LoadedManifest(manifest, manifest_path.resolve(), base_dir, root)


def manifest_json_schema_text() -> str:
    """The committed JSON Schema, generated from the typed model (drift-tested)."""
    schema = CiManifest.model_json_schema()
    ordered = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        **schema,
    }
    return json.dumps(ordered, indent=2, sort_keys=True) + "\n"
