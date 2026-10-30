"""Local run evidence manifests: build, hash, verify, and render (SP-17).

Local evidence manifests are produced by `decoy run --evidence-out <path>` and
contain fingerprints of the pipeline config, input files, and output files at
the time of the run. They also include a self-consistency fingerprint
(`manifest_hash`) that covers the entire manifest body.

S4b (CLI redesign) folded the former `evidence` verbs (show/verify) into
the `decoy report` noun (`report show` / `report verify`). This module is now a
HELPER module: it owns the manifest builder/hasher/verifier plus the shared
manifest-summary card renderer that `decoy report` imports. It registers no
Typer sub-app of its own.

What `report show` renders (via `_render_manifest_card`)
--------------------------------------------------------
Read-only. The manifest in human-readable or JSON form. Does NOT expose raw
row values (the manifest itself never contains them).

What `report verify` checks (via `verify_manifest`)
---------------------------------------------------
Re-hashes the current files to detect drift (accidental file changes):
  - pipeline_fingerprint: sha256:<hex> of pipeline.yaml
  - input_fingerprints: sha256:<hex> of each source file
  - output_fingerprints: sha256:<hex> of each target file
  - manifest_hash: sha256:<hex> of the manifest body itself

What verify does NOT check
--------------------------
* Platform audit logs, RBAC, schedule history, or secret access records.
* Whether the output was produced by the declared pipeline (it only checks
  that the files have not changed since the manifest was recorded).
* Data correctness or masking quality.
* Network, vault, or secrets accessibility.

Integrity limit
---------------
``manifest_hash`` is an UNKEYED SHA-256 integrity check. It detects
accidental change and drift; it does NOT detect a motivated tamperer who
can edit the manifest and recompute the hash (no secret key = no
authenticity). Cryptographic authenticity (keyed signing) is platform R4
territory. This limit mirrors the note at
decoy-platform/api/evidence/hashing.py (verify_manifest_hash docstring).

This is explicitly a LOCAL evidence facility. It proves "these files look the
same as when the run completed." It is not a replacement for platform-managed
audit history.

Interop note: the producer/schema markers make this manifest routable by a
future platform importer; no import adapter exists today (that is R4+ work).

Evidence manifest schema version: "cli-local-1"
"""

from __future__ import annotations

import hashlib
import json as _json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from decoy.ui.theme import warn

_SCHEMA_VERSION = "cli-local-1"

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
    body = {k: v for k, v in manifest.items() if k not in _MANIFEST_HASH_STRIP_FIELDS}
    # ensure_ascii=False mirrors the platform canonical_json rule (api/evidence/
    # hashing.py) byte-for-byte, so a future R4 import adapter sees identical
    # manifest_hash bytes for non-ASCII content (unicode column names/paths).
    canonical = _json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


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
) -> dict[str, Any]:
    """Build an evidence manifest dict for a completed local run.

    The manifest records:
      - versions, run metadata, pipeline fingerprint
      - per-table input and output file fingerprints (sha256:<hex> + size)
      - per-table row timings and engine quality warnings
      - per-column strategy summary (no raw values)
      - a manifest_hash covering all of the above

    Raw row values, secrets, plaintext key material, and PII samples are
    NEVER included. The spec for this invariant is the `no_raw_values` test.

    Fingerprint form: ``sha256:<hex>`` with a ``fingerprint_method`` field,
    matching decoy-platform/api/evidence/hashing.py's output_file_hash form.

    Schema: ``cli-local-1`` -- a namespace distinct from the platform's
    ``r3.x`` series so a manifest reader can route by producer + version.
    The ``producer`` field is ``"decoy-cli"``. A platform import adapter is
    future work (R4+); interop is not guaranteed beyond the routing markers.

    Failed-run artifacts are explicitly out of scope for CLI-local manifests;
    the platform handles error artifacts server-side. This function is only
    called on the success path.
    """
    pipeline_fingerprint = hash_file(pipeline_path)

    # --- Input fingerprints ---
    sources = config_dict.get("sources") or {}
    input_fingerprints: dict[str, Any] = {}
    for table_name, src in sources.items():
        if not isinstance(src, dict):
            continue
        src_path_str = src.get("path")
        if not src_path_str:
            continue
        src_path = Path(src_path_str)
        if src_path.exists():
            input_fingerprints[table_name] = {
                "path": str(src_path),
                "fingerprint": hash_file(src_path),
                "fingerprint_method": "full",
                "size_bytes": src_path.stat().st_size,
            }
        else:
            input_fingerprints[table_name] = {
                "path": str(src_path),
                "fingerprint": None,
                "fingerprint_method": None,
                "size_bytes": None,
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
        tgt_path = Path(tgt_path_str)
        if tgt_path.exists():
            output_fingerprints[table_name] = {
                "path": str(tgt_path),
                "fingerprint": hash_file(tgt_path),
                "fingerprint_method": "full",
                "size_bytes": tgt_path.stat().st_size,
            }
        else:
            output_fingerprints[table_name] = {
                "path": str(tgt_path),
                "fingerprint": None,
                "fingerprint_method": None,
                "size_bytes": None,
            }

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

    manifest: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "producer": "decoy-cli",
        "run_id": str(uuid4()),
        "run_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "cli_version": cli_version,
        "engine_version": engine_version,
        "pipeline_path": str(pipeline_path),
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
    return manifest


@dataclass(frozen=True)
class EvidenceIssue:
    """One typed verification issue. `kind` is the stable machine contract (`decoy ci`
    reads only this); `message` is the exact legacy prose `report verify` prints."""

    kind: str
    message: str


def verify_manifest_issues(
    manifest: dict[str, Any], *, regular_files_only: bool = False
) -> list[EvidenceIssue]:
    """Verify a manifest's fingerprints against the current on-disk state.

    Returns typed issues. Empty list = clean (all fingerprints match, manifest_hash is
    valid). Non-empty = fingerprint mismatch or drift detected.

    Integrity limit: manifest_hash is an UNKEYED SHA-256 check. It detects
    accidental drift; it does NOT detect a motivated tamperer who can edit
    the manifest and recompute the hash. This function is useful for catching
    unintended file changes, not adversarial edits.

    What is checked:
    * manifest_hash: re-computed and compared (detects manifest edits).
    * pipeline_fingerprint: current hash of pipeline_path vs recorded.
    * input_fingerprints: current hash of each source file vs recorded.
    * output_fingerprints: current hash of each target file vs recorded.

    What is NOT checked:
    * Data correctness or masking quality.
    * Whether the output was actually produced by the recorded pipeline.

    `regular_files_only` (used by `decoy ci check`, where the manifest may come from an
    untrusted change): a recorded path that exists but is not a regular file (FIFO, device)
    is reported as missing instead of being hashed, so it cannot hang the check.
    """
    issues: list[EvidenceIssue] = []

    def _absent(path: Path) -> bool:
        if not path.exists():
            return True
        return regular_files_only and not path.is_file()

    # --- Manifest integrity check ---
    recorded_hash = manifest.get("manifest_hash", "")
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
        # If the manifest itself changed we still proceed so that all
        # other issues are surfaced in one pass.

    # --- Pipeline fingerprint ---
    pipeline_path_str = manifest.get("pipeline_path")
    recorded_pf = manifest.get("pipeline_fingerprint")
    if pipeline_path_str and recorded_pf:
        pipeline_path = Path(pipeline_path_str)
        if _absent(pipeline_path):
            issues.append(
                EvidenceIssue(
                    "pipeline_missing", f"pipeline missing: {pipeline_path_str} not found"
                )
            )
        else:
            current_pf = hash_file(pipeline_path)
            if current_pf != recorded_pf:
                issues.append(
                    EvidenceIssue(
                        "pipeline_fingerprint_changed",
                        f"pipeline fingerprint changed: {pipeline_path_str} "
                        f"(recorded {recorded_pf[:16]}..., current {current_pf[:16]}...)",
                    )
                )

    # --- Input fingerprints ---
    for table_name, info in (manifest.get("input_fingerprints") or {}).items():
        if not isinstance(info, dict):
            continue
        path_str = info.get("path")
        recorded_fp = info.get("fingerprint")
        if not path_str or not recorded_fp:
            continue
        p = Path(path_str)
        if _absent(p):
            issues.append(
                EvidenceIssue(
                    "input_missing",
                    f"input missing: {path_str} (table {table_name!r}) not found",
                )
            )
            continue
        current_fp = hash_file(p)
        if current_fp != recorded_fp:
            issues.append(
                EvidenceIssue(
                    "input_fingerprint_changed",
                    f"input fingerprint changed: {path_str} (table {table_name!r}) "
                    f"(recorded {recorded_fp[:16]}..., current {current_fp[:16]}...)",
                )
            )

    # --- Output fingerprints ---
    for table_name, info in (manifest.get("output_fingerprints") or {}).items():
        if not isinstance(info, dict):
            continue
        path_str = info.get("path")
        recorded_fp = info.get("fingerprint")
        if not path_str or not recorded_fp:
            continue
        p = Path(path_str)
        if _absent(p):
            issues.append(
                EvidenceIssue(
                    "output_missing",
                    f"output missing: {path_str} (table {table_name!r}) not found",
                )
            )
            continue
        current_fp = hash_file(p)
        if current_fp != recorded_fp:
            issues.append(
                EvidenceIssue(
                    "output_fingerprint_changed",
                    f"output fingerprint changed: {path_str} (table {table_name!r}) "
                    f"(recorded {recorded_fp[:16]}..., current {current_fp[:16]}...)",
                )
            )

    return issues


def verify_manifest(manifest: dict[str, Any]) -> list[str]:
    """`verify_manifest_issues` rendered as the public list of issue strings."""
    return [issue.message for issue in verify_manifest_issues(manifest)]


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

    # Input fingerprints table
    input_fps = manifest.get("input_fingerprints") or {}
    if input_fps:
        t = make_table(
            "Table",
            "Path",
            "Fingerprint (prefix)",
            "Method",
            "Size",
            title="Input fingerprints",
        )
        for tname, info in input_fps.items():
            if not isinstance(info, dict):
                continue
            fp = (info.get("fingerprint") or "")[:23] + "..."
            method = info.get("fingerprint_method") or "?"
            size = str(info.get("size_bytes") or "?")
            t.add_row(tname, info.get("path", "?"), fp, method, size)
        state.console.print(t)

    # Output fingerprints table
    output_fps = manifest.get("output_fingerprints") or {}
    if output_fps:
        t = make_table(
            "Table",
            "Path",
            "Fingerprint (prefix)",
            "Method",
            "Size",
            title="Output fingerprints",
        )
        for tname, info in output_fps.items():
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
    "build_manifest",
    "compute_manifest_hash",
    "hash_file",
    "verify_manifest",
]
