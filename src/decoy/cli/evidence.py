"""Local run evidence manifests: build, hash, verify, and render (SP-17).

Local evidence manifests are produced by `decoy run --evidence-out <path>` and
contain fingerprints of the pipeline config, input files, and output files at
the time of the run. They also include a self-consistency fingerprint
(`manifest_hash`) that covers the entire manifest body.

It is a helper module for `decoy report` (show, render, verify, diff) and `decoy ci check`:
the builder, hasher, the one strict reader and verifier, and the `report show` card. It
registers no Typer app of its own.

`report verify` re-hashes the pipeline config, each input and output file, and the manifest
body (`manifest_hash`) to detect drift. It does not check platform audit logs, that the output
came from the declared pipeline, data correctness, or secret access. `manifest_hash` is an
UNKEYED SHA-256 check: it catches accidental change, not a tamperer who recomputes it (keyed
signing is platform R4; same limit as decoy-platform `api/evidence/hashing.py`). The manifest
never holds row values.

Evidence manifest schema version: "cli-local-1"

Output entry format keys (additive to cli-local-1)
--------------------------------------------------
An `output_fingerprints` entry for a file target also records `format` (`csv`, `parquet` or
`fixed_width`, the format the file was written in) and, for fixed width only, `layout` (the
target's validated layout: column names and positions, no data). The version string does not
change. A reader treats an entry without `format` as written by an older CLI and applies the
legacy rule: `.parquet` is Parquet, everything else CSV. It must not use the suffix rule of
`format_for_path` for those entries, because the old writer put CSV bytes into a `.pq` path.
`manifest_hash` covers the new keys on new manifests; old manifests verify unchanged.

Path base (additive to cli-local-1)
-----------------------------------
A run in a project with a `decoy.yaml` marker records `path_base: "project"` and writes every
path inside the project relative to its root (POSIX); paths outside it are absolute. A run with
no marker records absolute paths and no `path_base`. A stored path becomes a file path only in
`resolve_manifest_path` (sentry G-ONE-MANIFEST-PATH), which `read_manifest`,
`verify_manifest_issues` and `report diff`'s `compare_data` call. It reads `path_base` paths
from the project root: the typed `--project`, else the marker found above the manifest file,
never `DECOY_PROJECT` or the working directory, so every consumer works from any folder. A manifest without `path_base` keeps the old rule (paths as recorded,
relative ones from the working directory).

Paths are resolved before they are made relative, so a lexical `..` or a symlinked folder is
never recorded as inside the project. The reader parses a project-relative path with
`decoy.cli.io.contained_path`, the layout's one rule: "/" separators only, no drive or UNC
anchor, no climb above the root, no symlink out.

Project binding: a `path_base` manifest records `project_manifest`, where it was written
relative to its project root, or null when written outside the project. The reader refuses a
manifest whose file is not at that place under the root it reads from, so evidence for one
project copied into another is refused instead of read against the other project's files. A
manifest written outside its project has nothing to check and needs the typed `--project`.
Limit: an exact copy at the same relative place in another project still binds there; its
fingerprints then report the other project's files as changed.

Schema: `_FIELDS` and `_ENTRY_FIELDS` are the one schema. Types are exact JSON types: `true` is
not an integer and `"12"` is not a number, for `size_bytes` and every `row_counts` value. `build_manifest` checks its own output
against them and `read_manifest` checks every file it reads, so the writer and the readers
(`report`, `decoy ci check`) cannot disagree.
"""

from __future__ import annotations

import hashlib
import json as _json
import os
import posixpath
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from decoy.cli.io import (
    LayoutError,
    RunLayout,
    TargetFormatError,
    contained_path,
    find_project,
    resolve_target_format,
    resolved_source_config,
)
from decoy.ui.theme import warn

_SCHEMA_VERSION = "cli-local-1"
PATH_BASE_PROJECT = "project"

# Fields stripped before computing manifest_hash. Mirrors the platform's
# _MANIFEST_HASH_STRIP_FIELDS (api/evidence/hashing.py) so adding a
# signature field later does not silently break the hash.
_MANIFEST_HASH_STRIP_FIELDS: frozenset[str] = frozenset(
    {
        "manifest_hash",
        "signature",
        "signature_alg",
        "signature_key_id",
    }
)

# The manifest schema: field -> (accepted types, required, wording). A required string field
# must also be non-empty. Extra keys are tolerated so an additive field does not break a reader.
_Rule = tuple[tuple[type, ...], bool, str]
_STR: _Rule = ((str,), True, "a non-empty string")
_OPT: _Rule = ((str,), False, "a string")
_OPT_STR_OR_NULL: _Rule = ((str, type(None)), False, "a string or null")
_FIELDS: dict[str, _Rule] = {
    "schema_version": _STR,
    "producer": _OPT,
    "path_base": _OPT,
    "project_manifest": _OPT_STR_OR_NULL,
    "run_id": _OPT,
    "run_timestamp": _OPT,
    "cli_version": _OPT,
    "engine_version": _OPT,
    "pipeline_path": _STR,
    "pipeline_fingerprint": _STR,
    "input_fingerprints": ((dict,), True, "an object"),
    "output_fingerprints": ((dict,), True, "an object"),
    "row_counts": ((dict,), False, "an object"),
    "key_label": _OPT_STR_OR_NULL,
    "warnings": ((list,), False, "a list"),
    "timings": ((list,), False, "a list"),
    "strategies": ((list,), False, "a list"),
    "manifest_hash": _STR,
}
_ENTRY_FIELDS: dict[str, _Rule] = {
    "path": _STR,
    "fingerprint": ((str, type(None)), True, "a non-empty string or null"),
    "fingerprint_method": _OPT_STR_OR_NULL,
    "size_bytes": ((int, type(None)), False, "an integer or null"),
    "format": _OPT,
    "layout": ((object,), False, "any value"),
}

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def hash_file(path: Path) -> str:
    """Return the SHA-256 fingerprint of the file at `path` as ``sha256:<hex>``.

    Reads in 64 KiB chunks so it works on large files without loading all
    into memory. Standard Python stdlib hashlib; no external dependency.

    Returns a ``sha256:<hex>`` prefixed string (71 chars total) matching
    the fingerprint form used by decoy-platform/api/evidence/hashing.py.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    """Compute SHA-256 over the manifest body, returning ``sha256:<hex>``.

    Strips the four reserved fields (``manifest_hash``, ``signature``,
    ``signature_alg``, ``signature_key_id``) before hashing, matching the
    platform's field-strip set so a future signature field does not silently
    break the hash. Rejects non-finite floats (NaN, Infinity) per the R3.1
    canonical-JSON rule -- they do not round-trip JSON.

    This lets `evidence verify` detect edits to the manifest file itself.
    """
    # Imported here so the engine stays off the CLI's start-up path.
    from decoy_engine.records import canonical_bytes

    body = {k: v for k, v in manifest.items() if k not in _MANIFEST_HASH_STRIP_FIELDS}
    # The one canonical form (engine records, byte-identical to the platform's canonical_json:
    # sorted, compact, ensure_ascii=False), so a manifest hash and a record id agree on bytes.
    return f"sha256:{hashlib.sha256(canonical_bytes(body)).hexdigest()}"


def _format_keys(table: str, tgt: dict[str, Any]) -> dict[str, Any]:
    """The `format` (and fixed-width `layout`) keys of a file target; none for any other target.

    A target the writer would have refused (suffix contradiction) cannot reach here after a
    successful run; if one does, the entry stays in the legacy shape rather than failing a
    finished run.
    """
    if tgt.get("type", "file") != "file":
        return {}
    try:
        fmt = resolve_target_format(table, tgt)
    except TargetFormatError:
        # Cannot fire after a run: the gate refuses these targets before any source is read.
        return {}
    keys: dict[str, Any] = {"format": fmt}
    if fmt == "fixed_width" and tgt.get("layout") is not None:
        keys["layout"] = tgt["layout"]
    return keys


def _placed(place_target: Callable[[str], Path] | None, raw: str, base: Path) -> Path | None:
    """Where the run put `raw`; None when the layout refuses it (nothing was written there)."""
    if place_target is None:
        place_target = RunLayout.fixed(base).place_target
    try:
        return place_target(raw)
    except LayoutError:
        return None


def _inside(path: Path, root: Path) -> str | None:
    """`path` relative to `root` (POSIX) with both resolved first; None when it lies outside or
    when the reader's rule (`contained_path`) would not read the text back, such as a POSIX
    file name holding a backslash.

    Resolving first keeps `sub/../../x` and a symlink out of the project from passing a lexical
    prefix test.
    """
    try:
        text = path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        return None
    return text if contained_path(root, text) is not None else None


def _recorded(path: Path, root: Path | None) -> str:
    """The manifest text for `path`: relative to `root` when inside it, else absolute."""
    if root is None:
        return str(path)
    inside = _inside(path, root)
    return str(path.resolve()) if inside is None else inside


def _fingerprint(path: Path | None) -> dict[str, Any]:
    if path is not None and path.exists():
        return {
            "fingerprint": hash_file(path),
            "fingerprint_method": "full",
            "size_bytes": path.stat().st_size,
        }
    return {"fingerprint": None, "fingerprint_method": None, "size_bytes": None}


def build_manifest(
    *,
    pipeline_path: Path,
    config_dict: dict[str, Any],
    run_result: dict[str, Any],
    cli_version: str,
    engine_version: str,
    key_label: str | None = None,
    warnings: list[str] | None = None,
    timings: Any = None,
    engine_warnings: Any = None,
    run_id: str | None = None,
    place_target: Callable[[str], Path] | None = None,
    project_root: Path | None = None,
    evidence_path: Path | None = None,
) -> dict[str, Any]:
    """Build an evidence manifest dict for a completed local run.

    `run_id` is the command's invocation id (it names the run folder); a new one is made when
    absent. `place_target` maps a declared target path to the file the run writes there (the
    run's `RunLayout.place_target`). Every target is recorded at that path, written or not, so
    a target that published nothing gets a null fingerprint instead of matching a same-named
    file in the working directory. Without it, targets resolve against the YAML's folder, as
    sources always do. `project_root` is the root of a project with a marker: paths inside it
    are recorded relative to it and the manifest gains `path_base: "project"` and
    `project_manifest` (where `evidence_path`, the file the manifest is written to, sits in the
    project; null when outside it). Without it every path is recorded absolute.

    The manifest records:
      - versions, run metadata, pipeline fingerprint
      - per-table input and output file fingerprints (sha256:<hex> + size)
      - per-table row timings and engine quality warnings
      - per-column strategy summary (no raw values)
      - a manifest_hash covering all of the above

    Raw row values, secrets, plaintext key material, and PII samples are
    NEVER included. The spec for this invariant is the `no_raw_values` test.
    Schema ``cli-local-1``, producer ``"decoy-cli"``, so a reader can route by both. Only the
    success path calls this; failed runs leave no CLI-local manifest.
    """
    pipeline_fingerprint = hash_file(pipeline_path)
    pipeline_path = pipeline_path.resolve()
    yaml_dir = pipeline_path.parent

    # --- Input fingerprints: the files the run read, file sources resolved from the YAML folder ---
    sources = resolved_source_config(config_dict, yaml_dir).get("sources") or {}
    input_fingerprints: dict[str, Any] = {}
    for table_name, src in sources.items():
        if not isinstance(src, dict):
            continue
        src_path_str = src.get("path")
        if not src_path_str:
            continue
        src_path = Path(str(src_path_str))
        if "://" in str(src_path_str) or not src_path.is_absolute():
            # A URL, or a non-file source the run did not open from this path: nothing to hash.
            input_fingerprints[table_name] = {"path": str(src_path_str), **_fingerprint(None)}
            continue
        input_fingerprints[table_name] = {
            "path": _recorded(src_path, project_root),
            **_fingerprint(src_path),
        }

    # --- Output fingerprints ---
    targets = config_dict.get("targets") or {}
    output_fingerprints: dict[str, Any] = {}
    for table_name, tgt in targets.items():
        if not isinstance(tgt, dict):
            continue
        tgt_path_str = tgt.get("path")
        if not tgt_path_str:
            continue
        tgt_path = _placed(place_target, str(tgt_path_str), yaml_dir)
        recorded = str(tgt_path_str) if tgt_path is None else _recorded(tgt_path, project_root)
        entry: dict[str, Any] = {"path": recorded}
        entry.update(_format_keys(table_name, tgt))
        entry.update(_fingerprint(tgt_path))
        output_fingerprints[table_name] = entry

    # --- Row counts ---
    row_counts = (run_result or {}).get("row_counts") or {}

    # --- Timings: serialize StrategyTimingRecord objects to dicts ---
    timings_out: list[dict[str, Any]] = []
    for t in timings or ():
        if hasattr(t, "strategy_type"):
            timings_out.append(
                {
                    "strategy_type": t.strategy_type,
                    "column": t.column,
                    "elapsed_ms": t.elapsed_ms,
                    "peak_memory_delta_kb": t.peak_memory_delta_kb,
                }
            )
        elif isinstance(t, dict):
            timings_out.append(t)

    # --- Warnings: merge CLI warnings + engine QualityWarning objects ---
    warnings_out: list[Any] = list(warnings or [])
    for w in engine_warnings or ():
        if hasattr(w, "code"):
            warnings_out.append(
                {
                    "code": w.code,
                    "provider": w.provider,
                    "column": w.column,
                    "detail": dict(w.detail) if w.detail else {},
                }
            )
        elif isinstance(w, (str, dict)):
            warnings_out.append(w)

    # --- Strategy summary (no raw values) ---
    tables = config_dict.get("tables") or []
    strategies: list[dict[str, str]] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        tname = table.get("name", "")
        for col in table.get("columns") or []:
            if not isinstance(col, dict):
                continue
            strategies.append(
                {
                    "table": tname,
                    "column": col.get("name", ""),
                    "strategy": col.get("strategy", ""),
                }
            )
        for gen_col in table.get("generate_columns") or []:
            if not isinstance(gen_col, dict):
                continue
            strategies.append(
                {
                    "table": tname,
                    "column": gen_col.get("name", ""),
                    "strategy": "generate",
                }
            )

    binding: dict[str, Any] = {}
    if project_root is not None:
        written_at = None if evidence_path is None else _inside(evidence_path, project_root)
        binding = {"path_base": PATH_BASE_PROJECT, "project_manifest": written_at}
    manifest: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "producer": "decoy-cli",
        **binding,
        "run_id": run_id if run_id is not None else str(uuid4()),
        "run_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "cli_version": cli_version,
        "engine_version": engine_version,
        "pipeline_path": _recorded(pipeline_path, project_root),
        "pipeline_fingerprint": pipeline_fingerprint,
        "input_fingerprints": input_fingerprints,
        "output_fingerprints": output_fingerprints,
        "row_counts": row_counts,
        "key_label": key_label,
        "warnings": warnings_out,
        "timings": timings_out,
        "strategies": strategies,
        "manifest_hash": "",  # placeholder; filled below
    }
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    return check_manifest(manifest)


@dataclass(frozen=True)
class EvidenceIssue:
    """One typed verification issue. `kind` is the stable machine contract (`decoy ci`
    reads only this); `message` is the exact legacy prose `report verify` prints."""

    kind: str
    message: str


class ManifestError(ValueError):
    """A manifest the verifier will not read. `kind` is a fixed label; `message` names fields
    and files, never a recorded value."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _malformed(field: str, rule: str) -> ManifestError:
    return ManifestError("malformed", f"evidence manifest is malformed: `{field}` {rule}.")


def _is(value: Any, types: tuple[type, ...]) -> bool:
    """Exact JSON types: `true` is not an integer and `"12"` is not a number."""
    return any(t is object or type(value) is t for t in types)


def _check_fields(obj: dict[str, Any], fields: dict[str, _Rule], prefix: str) -> None:
    for key, (types, required, wording) in fields.items():
        if key not in obj:
            if required:
                raise _malformed(prefix + key, "is required")
            continue
        value = obj[key]
        if not _is(value, types) or (required and value == ""):
            raise _malformed(prefix + key, f"must be {wording}")


def check_manifest(manifest: Any) -> dict[str, Any]:
    """Refuse anything but a manifest of the schema above; return it typed as an object.

    `build_manifest` runs this on its own output and every reader on what it reads. Messages
    name fields and tables, never a recorded value.
    """
    if not isinstance(manifest, dict):
        raise ManifestError(
            "malformed", "evidence manifest is malformed: the top level must be a JSON object."
        )
    _check_fields(manifest, _FIELDS, "")
    if manifest["schema_version"] != _SCHEMA_VERSION:
        raise _malformed("schema_version", f"must be {_SCHEMA_VERSION}")
    if manifest.get("path_base", PATH_BASE_PROJECT) != PATH_BASE_PROJECT:
        raise _malformed("path_base", f"must be absent or {PATH_BASE_PROJECT}")
    if "path_base" in manifest and "project_manifest" not in manifest:
        raise _malformed("project_manifest", "is required with path_base")
    for group in ("input_fingerprints", "output_fingerprints"):
        for table, info in manifest[group].items():
            if not isinstance(info, dict):
                raise _malformed(f"{group}.{table}", "must be an object")
            _check_fields(info, _ENTRY_FIELDS, f"{group}.{table}.")
    for table, count in manifest.get("row_counts", {}).items():
        if not _is(count, (int,)):
            raise _malformed(f"row_counts.{table}", "must be an integer")
    return manifest


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def read_manifest(path: Path, project: Path | None = None) -> dict[str, Any]:
    """The one way a manifest file is read: parsed, checked by `check_manifest`, and every
    stored file path sent through `resolve_manifest_path` (`project` is the typed `--project`).

    Raises `ManifestError` with kind `missing` (no regular file there), `unreadable` (I/O,
    encoding, or not JSON; NaN and Infinity are refused because the hash cannot carry them),
    as `check_manifest`, or as the resolver. Messages name the file, never its content.
    """
    if not path.is_file():
        raise ManifestError("missing", f"evidence file not found: {path}")
    refusal = None
    try:
        parsed = _json.loads(path.read_text(encoding="utf-8"), parse_constant=_no_constant)
    except (OSError, UnicodeDecodeError) as exc:
        refusal = f"could not read {path}: {type(exc).__name__}"
    except (ValueError, RecursionError) as exc:
        why = exc.msg if isinstance(exc, _json.JSONDecodeError) else type(exc).__name__
        refusal = f"could not parse {path.name} as JSON: {why}"
    # Raised outside the handlers so the parser's error, which can quote the file, is not chained.
    if refusal is not None:
        raise ManifestError("unreadable", refusal)
    manifest = check_manifest(parsed)
    for _at, _table, field, raw, _recorded_fp in _stored_files(manifest):
        resolve_manifest_path(manifest, raw, manifest_file=path, project=project, field=field)
    return manifest


def _stored_files(manifest: dict[str, Any]) -> list[tuple[int, str, str, str, str]]:
    """(0 pipeline / 1 input / 2 output, table, field, recorded path, recorded fingerprint) for
    every stored path that names a file. An entry with a null fingerprint names no file (a URL
    source, or a target the run wrote nothing to), so it is metadata only."""
    found = [(0, "", "pipeline_path", manifest["pipeline_path"], manifest["pipeline_fingerprint"])]
    for at, group in ((1, "input_fingerprints"), (2, "output_fingerprints")):
        for table, info in manifest[group].items():
            if info["fingerprint"] is not None:
                found.append(
                    (at, table, f"{group}.{table}.path", info["path"], info["fingerprint"])
                )
    return found


def _same_file(a: Path, b: Path | None) -> bool:
    try:
        return b is not None and os.path.samefile(a, b)
    except OSError:
        return False


def _manifest_root(
    manifest: dict[str, Any], manifest_file: Path | None, project: Path | None
) -> Path | None:
    """The folder `path_base: "project"` paths are read from; None for the old rule.

    The root is the typed `--project`, else the marker above the manifest file. Either way the
    manifest file must sit where the run wrote it in that project (`project_manifest`).
    """
    if manifest.get("path_base") != PATH_BASE_PROJECT:
        return None
    where = "the manifest" if manifest_file is None else manifest_file.name
    written_at = manifest["project_manifest"]
    failure: LayoutError | None = None
    root: Path | None = None
    try:
        if project is not None:
            root = find_project(None, project).root
        elif manifest_file is not None and written_at is not None:
            found = find_project(manifest_file.resolve().parent, None)
            root = None if found.implicit else found.root
    except LayoutError as exc:
        failure = exc
    # Raised outside the handler so no layout error is chained onto the refusal.
    if failure is not None:
        raise ManifestError(failure.code, failure.message)
    if root is None:
        why = (
            "was written outside its Decoy project"
            if written_at is None
            else "records paths relative to a Decoy project, and no project marker was found "
            "above it"
        )
        raise ManifestError(
            "project_not_found", f"{where} {why}; pass --project with the project folder."
        )
    if written_at is not None:
        expected = contained_path(root, written_at)
        if expected is None:
            raise _outside("project_manifest")
        if not _same_file(expected, manifest_file):
            raise ManifestError(
                "project_mismatch",
                f"{where} is not where its run wrote it in this Decoy project (another project "
                "or another place); verify it where the run wrote it.",
            )
    return root


def _outside(field: str) -> ManifestError:
    return ManifestError(
        "path_outside_project",
        f"evidence manifest is malformed: `{field}` must name a file inside the project, "
        'written with "/".',
    )


def resolve_manifest_path(
    manifest: dict[str, Any],
    raw: str,
    *,
    manifest_file: Path | None,
    project: Path | None = None,
    field: str = "path",
) -> Path:
    """The one way a stored manifest path becomes a file path (sentry G-ONE-MANIFEST-PATH).

    `manifest_file` is where `manifest` was read from and `project` the typed `--project`; with
    `path_base: "project"` they give the root (`_manifest_root`), never the working directory
    or `DECOY_PROJECT`. A manifest without `path_base` keeps the old rule: `raw` as recorded,
    a relative one from the working directory. An absolute path (a file outside the project,
    recorded as such) is read as recorded. Every other path is parsed by
    `decoy.cli.io.contained_path`, the one rule for stored relative paths: "/" only, no drive or
    UNC anchor, and it must stay inside the root (no climb above it, no symlink out).
    Otherwise `ManifestError` names `field`, not the path.
    """
    root = _manifest_root(manifest, manifest_file, project)
    if root is None or posixpath.isabs(raw) or os.path.isabs(raw):
        return Path(raw)
    path = contained_path(root, raw)
    if path is None:
        raise _outside(field)
    return path


def verify_manifest_issues(
    manifest: dict[str, Any],
    *,
    manifest_file: Path | None = None,
    project: Path | None = None,
    regular_files_only: bool = False,
) -> list[EvidenceIssue]:
    """Verify a manifest's fingerprints against the current on-disk state.

    The one manifest reader `report verify` and `decoy ci check` share. `manifest_file` is
    where the manifest was read from and `project` the typed `--project`; they locate the
    root for a `path_base: "project"` manifest (see the module docstring). Raises
    `ManifestError` for a malformed manifest, a path outside the project, or a project root
    that cannot be found or does not hold the manifest. Every path is checked before any file
    is hashed. Returns typed issues; empty means the manifest_hash (UNKEYED: catches drift, not
    a tamperer who recomputes it) and every recorded fingerprint match.

    `regular_files_only` (used by `decoy ci check`, where the manifest may come from an
    untrusted change): a recorded path that exists but is not a regular file (FIFO, device)
    is reported as missing instead of being hashed, so it cannot hang the check.
    """
    check_manifest(manifest)
    # All resolved before any hashing so a refused path never leaves a partial result.
    checks = [
        (
            at,
            f" (table {table!r})" if at else "",
            raw,
            recorded,
            resolve_manifest_path(
                manifest, raw, manifest_file=manifest_file, project=project, field=field
            ),
        )
        for at, table, field, raw, recorded in _stored_files(manifest)
    ]

    issues: list[EvidenceIssue] = []
    recorded_hash = manifest["manifest_hash"]
    computed_hash = compute_manifest_hash(manifest)
    if recorded_hash != computed_hash:
        issues.append(
            EvidenceIssue(
                "manifest_hash_mismatch",
                f"manifest integrity: manifest_hash mismatch "
                f"(recorded {recorded_hash[:16]}..., computed {computed_hash[:16]}...); "
                "manifest file may have been edited",
            )
        )
        # Keep going so every other issue surfaces in the same pass.
    # Kinds stay literal in each call: `decoy ci` allowlists them by reading this module.
    for at, label, text, recorded, path in checks:
        what = ("pipeline", "input", "output")[at]
        if not path.exists() or (regular_files_only and not path.is_file()):
            issues.append(
                EvidenceIssue(
                    ("pipeline_missing", "input_missing", "output_missing")[at],
                    f"{what} missing: {text}{label} not found",
                )
            )
            continue
        current = hash_file(path)
        if current != recorded:
            issues.append(
                EvidenceIssue(
                    (
                        "pipeline_fingerprint_changed",
                        "input_fingerprint_changed",
                        "output_fingerprint_changed",
                    )[at],
                    f"{what} fingerprint changed: {text}{label} "
                    f"(recorded {recorded[:16]}..., current {current[:16]}...)",
                )
            )
    return issues


def verify_manifest(
    manifest: dict[str, Any], *, manifest_file: Path | None = None, project: Path | None = None
) -> list[str]:
    """`verify_manifest_issues` rendered as the public list of issue strings."""
    issues = verify_manifest_issues(manifest, manifest_file=manifest_file, project=project)
    return [issue.message for issue in issues]


# ---------------------------------------------------------------------------
# Shared manifest-summary card (rendered by `decoy report show`)
# ---------------------------------------------------------------------------


def _render_manifest_card(state: Any, manifest: dict[str, Any], evidence_file: Path) -> None:
    """Human-readable evidence manifest summary card."""
    from decoy.ui.card import render_card
    from decoy.ui.table import make_table

    # Quick manifest integrity check for the display (informational only).
    recorded_hash = manifest.get("manifest_hash", "")
    computed_hash = compute_manifest_hash(manifest)
    hash_ok = recorded_hash == computed_hash

    schema_v = manifest.get("schema_version", "?")
    run_id = manifest.get("run_id", "?")
    run_ts = manifest.get("run_timestamp", "?")
    cli_v = manifest.get("cli_version", "?")
    eng_v = manifest.get("engine_version", "?")
    pipeline_path = manifest.get("pipeline_path", "?")
    pipeline_fp = manifest.get("pipeline_fingerprint") or ""
    key_label = manifest.get("key_label") or "(none)"
    warnings_list = manifest.get("warnings") or []
    timings_list = manifest.get("timings") or []
    hash_status = "ok (unkeyed integrity check)" if hash_ok else "MISMATCH (manifest may be edited)"

    facts: list[tuple[str, str]] = [
        ("Schema version", schema_v),
        ("Producer", manifest.get("producer", "?")),
        ("Run ID", run_id[:16] + "..." if len(run_id) > 16 else run_id),
        ("Run timestamp", run_ts),
        ("CLI version", cli_v),
        ("Engine version", eng_v),
        ("Pipeline", pipeline_path),
        ("Pipeline fingerprint", pipeline_fp[:23] + "..." if pipeline_fp else "(none)"),
        ("Key label", key_label),
        ("Manifest hash", hash_status),
        ("Warnings", str(len(warnings_list))),
        ("Timings recorded", str(len(timings_list))),
    ]

    render_card(
        state,
        command="decoy report show",
        facts=facts,
        next_hint=f"decoy report verify {evidence_file}",
        status="ok" if hash_ok else "warn",
    )

    for group, title in (("input_fingerprints", "Input"), ("output_fingerprints", "Output")):
        entries = manifest.get(group) or {}
        if not entries:
            continue
        t = make_table(
            "Table", "Path", "Fingerprint (prefix)", "Method", "Size", title=f"{title} fingerprints"
        )
        for tname, info in entries.items():
            if not isinstance(info, dict):
                continue
            fp = (info.get("fingerprint") or "")[:23] + "..."
            method = info.get("fingerprint_method") or "?"
            size = str(info.get("size_bytes") or "?")
            t.add_row(tname, info.get("path", "?"), fp, method, size)
        state.console.print(t)

    # Strategies table
    strategies = manifest.get("strategies") or []
    if strategies:
        t = make_table("Table", "Column", "Strategy", title="Masking strategies")
        for s in strategies:
            if not isinstance(s, dict):
                continue
            t.add_row(s.get("table", "?"), s.get("column", "?"), s.get("strategy", "?"))
        state.console.print(t)

    if not hash_ok:
        state.err_console.print(
            warn("warning:"),
            "manifest_hash does not match the manifest body. "
            "The manifest file may have been edited. "
            "Run `decoy report verify` for a full fingerprint check.",
        )


# Public exports (used by run.py --evidence-out and tests)
__all__ = [
    "ManifestError",
    "build_manifest",
    "check_manifest",
    "compute_manifest_hash",
    "hash_file",
    "read_manifest",
    "resolve_manifest_path",
    "verify_manifest",
    "verify_manifest_issues",
]
