"""``decoy local-cleanup``: manifest-scoped, dry-run-first removal of declared run outputs (F26).

STATELESS and EXACT. The only things it will ever consider are the OUTPUT files an explicit
``cli-local-1`` evidence manifest declares, beneath an explicit ``--root``. It never discovers files,
never touches inputs, the pipeline file or the manifest, writes no catalog or workspace, and never
prints a path, filename, bucket, hash or exception text: output is the shared value-free
``retention-report/v1`` from the engine (``decoy_engine.retention``), counts and opaque ids only.

Dry-run is the default. ``--execute`` additionally needs (1) the inventory digest of the exact
reviewed set and (2) a fresh confirmation: typing the digest's first 12 characters on a TTY, or on a
script an explicit ``--owner-token`` equal to ``$DECOY_LOCAL_CLEANUP_TOKEN``. The inventory is
recomputed from disk at execution time, so ANY change since the preview (content, size, inode, mtime,
a symlink swap) changes the digest and refuses. Each file is then re-opened without following
symlinks, compared, and unlinked relative to its parent descriptor.

Dry-run-then-force with a content-addressed digest follows git-clean; the contract (reason and exit
codes, report schema) is the engine's, shared with the platform sweeper.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from decoy.cli import _local_cleanup_io as io
from decoy.cli.exit_codes import EXIT_USAGE

LOCAL_CLEANUP_EPILOG = """\
Examples:
  decoy local-cleanup --manifest evidence.json --root ./out
  decoy local-cleanup --manifest evidence.json --root ./out --execute --confirm-digest <digest>

Only the output files declared by the manifest, beneath --root, are ever candidates.
Exit codes: 0 success, 10 nothing to do, 11 everything retained, 12 partial, 13 refused.
"""

MAX_MANIFEST_BYTES = 32 * 1024 * 1024
TOKEN_ENV = "DECOY_LOCAL_CLEANUP_TOKEN"


def _opaque(manifest_hash: str, table: str) -> str:
    return hashlib.sha256(f"{manifest_hash}\0{table}".encode()).hexdigest()[:32]


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _read_manifest(path: Path) -> dict[str, Any] | None:
    from decoy.cli.evidence import compute_manifest_hash

    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != "cli-local-1" or data.get("producer") != "decoy-cli":
        return None
    recorded = data.get("manifest_hash")
    try:
        if not isinstance(recorded, str) or recorded != compute_manifest_hash(data):
            return None
    except (TypeError, ValueError):
        return None
    return data


def _protected(manifest: dict[str, Any], manifest_path: Path) -> set[tuple[int, int]]:
    """(dev, ino) of everything that is NOT an output: inputs, the pipeline, the manifest."""
    out: set[tuple[int, int]] = set()
    paths = [str(manifest_path), str(manifest.get("pipeline_path") or "")]
    for entry in (manifest.get("input_fingerprints") or {}).values():
        if isinstance(entry, dict):
            paths.append(str(entry.get("path") or ""))
    for p in paths:
        if not p:
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.add((st.st_dev, st.st_ino))
    return out


def _resolve(raw: str, manifest_dir: Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else manifest_dir / p


def build_inventory(manifest_path: Path, roots: list[Path], max_files: int):
    """Returns ``(items, identities, complete, refusal)``. ``items`` are engine ReportItems;
    ``identities`` maps artifact id -> (root index, parts, Identity) for the eligible ones."""
    from decoy_engine.retention import ArtifactClass, Decision, ReasonCode, ReportItem

    R = ReasonCode
    manifest = _read_manifest(manifest_path)
    if manifest is None:
        return [], {}, False, R.REFUSED_MANIFEST_INVALID, ""
    mhash = str(manifest["manifest_hash"])
    outputs = manifest.get("output_fingerprints")
    if not isinstance(outputs, dict):
        return [], {}, False, R.REFUSED_MANIFEST_INVALID, mhash
    protected = _protected(manifest, manifest_path)
    root_fds: list[int] = []
    try:
        for r in roots:
            root_fds.append(io.open_root(r))
    except OSError:
        for fd in root_fds:
            os.close(fd)
        return [], {}, False, R.REFUSED_MANIFEST_INVALID, mhash
    items: list[Any] = []
    identities: dict[str, tuple[int, tuple[str, ...], io.Identity, bytes]] = {}
    seen: set[tuple[int, int]] = set()
    complete = len(outputs) <= max_files
    try:
        for table in sorted(outputs, key=str)[:max_files]:
            entry = outputs[table]
            aid = _opaque(mhash, str(table))

            def retain(reason, size=None, _aid=aid):
                items.append(
                    ReportItem(
                        artifact_id=_aid,
                        artifact_class=ArtifactClass.PUBLISHED_OUTPUT,
                        decision=Decision.RETAINED,
                        reason=reason,
                        size_bytes=size,
                    )
                )

            if not isinstance(entry, dict) or not entry.get("path") or not entry.get("fingerprint"):
                retain(R.RETAIN_IDENTITY_UNREADABLE)  # nothing was recorded to compare against
                continue
            fp = str(entry["fingerprint"])
            size = entry.get("size_bytes")
            if not (
                fp.startswith("sha256:") and isinstance(size, int) and not isinstance(size, bool)
            ):
                retain(R.RETAIN_IDENTITY_UNREADABLE)
                continue
            path = _resolve(str(entry["path"]), manifest_path.resolve().parent)
            hit = None
            for idx, root in enumerate(roots):
                parts = io.split_beneath(path, root)
                if parts is not None:
                    hit = (idx, parts)
                    break
            if hit is None:
                retain(R.RETAIN_UNREGISTERED)  # not beneath an allowed root: not ours to touch
                continue
            idx, parts = hit
            state, ident = io.probe(root_fds[idx], parts)
            if state is io.Probe.ABSENT:
                retain(R.RETAIN_IDENTITY_MISMATCH)
            elif state is io.Probe.UNREADABLE:
                retain(R.RETAIN_IDENTITY_UNREADABLE)
            elif state is not io.Probe.MATCH or ident is None:
                retain(R.RETAIN_IDENTITY_MISMATCH)
            elif ident.size != size or f"sha256:{ident.sha256}" != fp:
                retain(R.RETAIN_IDENTITY_MISMATCH, ident.size)
            elif (ident.dev, ident.ino) in protected:
                retain(R.RETAIN_UNREGISTERED, ident.size)  # an input, the pipeline or the manifest
            elif (ident.dev, ident.ino) in seen:
                retain(R.RETAIN_IDENTITY_MISMATCH, ident.size)  # two outputs naming one file
            else:
                seen.add((ident.dev, ident.ino))
                rst = os.fstat(root_fds[idx])
                token = json.dumps(
                    [
                        ident.sha256,
                        ident.size,
                        ident.dev,
                        ident.ino,
                        ident.mtime_ns,
                        rst.st_dev,
                        rst.st_ino,
                    ]
                ).encode()
                identities[aid] = (idx, parts, ident, token)
                items.append(
                    ReportItem(
                        artifact_id=aid,
                        artifact_class=ArtifactClass.PUBLISHED_OUTPUT,
                        decision=Decision.ELIGIBLE,
                        reason=R.ELIGIBLE,
                        size_bytes=ident.size,
                    )
                )
    finally:
        for fd in root_fds:
            os.close(fd)
    return items, identities, complete, None, mhash


def _report(kind, mhash, items, identities, complete, roots_n, limits, refusal=None, results=None):
    from decoy_engine.retention import (
        DEFAULT_POLICY,
        ArtifactClass,
        Decision,
        ReasonCode,
        ReportItem,
        RetentionReport,
        counts_from_items,
        inventory_digest,
    )

    eligible = [
        (i.artifact_id, hashlib.sha256(identities[i.artifact_id][3]).hexdigest())
        for i in items
        if i.artifact_id in identities
    ]
    digest = inventory_digest(
        policy_id=DEFAULT_POLICY.policy_id,
        scope=[ArtifactClass.PUBLISHED_OUTPUT],
        limits=limits,
        expires_at=0,
        eligible=eligible,
    )
    out_items = items
    approved = 0
    bytes_deleted = 0
    if results is not None:
        approved = len(identities)
        out_items = []
        for it in items:
            res = results.get(it.artifact_id)
            if res is None:
                out_items.append(it)
                continue
            result, retained_reason = res
            if retained_reason is not None:
                it = ReportItem(
                    it.artifact_id,
                    it.artifact_class,
                    Decision.RETAINED,
                    retained_reason,
                    it.size_bytes,
                    result,
                )
            else:
                it = ReportItem(
                    it.artifact_id, it.artifact_class, it.decision, it.reason, it.size_bytes, result
                )
                bytes_deleted += it.size_bytes or 0
            out_items.append(it)
    counts = counts_from_items(out_items, approved=approved, bytes_deleted=bytes_deleted)
    rid = hashlib.sha256(f"{mhash}\0run".encode()).hexdigest()[:32]
    return RetentionReport(
        kind=kind,
        run_id=rid,
        policy_id=DEFAULT_POLICY.policy_id,
        scope=(ArtifactClass.PUBLISHED_OUTPUT,),
        complete=complete,
        limits=limits,
        counts=counts,
        digest=digest,
        items=tuple(out_items),
        refusal=refusal if isinstance(refusal, ReasonCode) else None,
    )


def _refusal_report(kind, code, limits):
    from decoy_engine.retention import DEFAULT_POLICY, ArtifactClass, Counts, RetentionReport

    return RetentionReport(
        kind=kind,
        run_id="0" * 32,
        policy_id=DEFAULT_POLICY.policy_id,
        scope=(ArtifactClass.PUBLISHED_OUTPUT,),
        complete=False,
        limits=limits,
        counts=Counts(),
        digest="0" * 64,
        refusal=code,
    )


def _confirmed(digest: str, owner_token: str | None) -> bool:
    if _is_tty():
        typed = typer.prompt(
            f"Type the first 12 characters of the digest to delete ({digest[:4]}...)",
            default="",
            show_default=False,
        )
        return hmac.compare_digest(typed.strip().encode(), digest[:12].encode())
    expected = os.environ.get(TOKEN_ENV, "")
    return (
        bool(expected)
        and owner_token is not None
        and hmac.compare_digest(owner_token.encode(), expected.encode())
    )


def local_cleanup(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="A cli-local-1 evidence manifest. Only its declared OUTPUT files are ever candidates.",
    ),
    root: list[Path] = typer.Option(
        ...,
        "--root",
        help="Allowed root directory (repeatable). Outputs outside every root are retained.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Delete the reviewed set. Needs --confirm-digest and a fresh confirmation.",
    ),
    confirm_digest: str | None = typer.Option(
        None, "--confirm-digest", help="The inventory digest printed by the dry run."
    ),
    owner_token: str | None = typer.Option(
        None, "--owner-token", help=f"Non-interactive confirmation; must equal ${TOKEN_ENV}."
    ),
    max_files: int = typer.Option(
        500, "--max-files", min=1, max=5000, help="Bound on declared outputs considered."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print the canonical retention-report/v1 JSON."
    ),
) -> None:
    """Preview (default) or delete the output files an evidence manifest declares."""
    # Importing the engine configures its logger, whose default is a rotating file under ./logs:
    # a stateless command that may be cleaning that very directory must not create one.
    os.environ.setdefault("DECOY_ENGINE_LOG_FILE", "")
    from decoy_engine.retention import (
        Limits,
        ReasonCode,
        ReportKind,
        render_text,
    )

    R = ReasonCode
    limits = Limits(max_items=max_files, max_bytes=2**62, max_backend_calls=0, max_seconds=0)

    def finish(report) -> None:
        typer.echo(report.to_json() if json_out else render_text(report))
        raise typer.Exit(code=int(report.exit_code))

    if not roots_ok(root):
        typer.echo("error: --root must be an existing directory.", err=True)
        raise typer.Exit(code=EXIT_USAGE)
    kind = ReportKind.EXECUTE if execute else ReportKind.PREVIEW
    items, identities, complete, refusal, mhash = build_inventory(manifest, list(root), max_files)
    if refusal is not None:
        finish(_refusal_report(kind, refusal, limits))
    preview = _report(ReportKind.PREVIEW, mhash, items, identities, complete, len(root), limits)
    if not execute:
        finish(preview)

    # ---- execute: every proof, in order, before the first unlink ---------------------------
    if not io.safe_open_supported():
        finish(_refusal_report(kind, R.REFUSED_UNSAFE_PLATFORM, limits))
    if not complete:
        finish(_refusal_report(kind, R.REFUSED_RUN_INCOMPLETE, limits))
    if not confirm_digest or not hmac.compare_digest(
        confirm_digest.encode(), preview.digest.encode()
    ):
        finish(_refusal_report(kind, R.REFUSED_DIGEST_MISMATCH, limits))
    if not identities:
        finish(_report(kind, mhash, items, identities, complete, len(root), limits, results={}))
    if not _confirmed(preview.digest, owner_token):
        finish(_refusal_report(kind, R.REFUSED_CONFIRMATION, limits))

    results: dict[str, tuple[Any, Any]] = {}
    root_fds = [io.open_root(r) for r in root]
    try:
        for aid, (idx, parts, ident, _tok) in sorted(identities.items()):
            if io.unlink_exact(root_fds[idx], parts, ident):
                state, _ = io.probe(root_fds[idx], parts)
                if state is io.Probe.ABSENT:
                    results[aid] = (R.RESULT_DELETED, None)
                else:
                    results[aid] = (R.RESULT_RETRYABLE, None)
            else:
                results[aid] = (R.RESULT_BACKEND_REFUSED, R.RETAIN_STATE_CHANGED)
    finally:
        for fd in root_fds:
            os.close(fd)
    finish(_report(kind, mhash, items, identities, complete, len(root), limits, results=results))


def roots_ok(roots: list[Path]) -> bool:
    try:
        return all(Path(r).is_dir() for r in roots)
    except OSError:  # e.g. permission denied while stat-ing the root: not a usable root
        return False
