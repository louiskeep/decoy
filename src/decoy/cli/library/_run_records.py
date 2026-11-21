"""Store a `decoy run`'s evidence and run-result records in the library (plan 4.3, 4.16, 4.17; L3a).

The run builds its `cli-local-1` manifest once (`decoy.cli.evidence.build_manifest`) and hands
that same dict here, so the record payload equals the `--evidence-out` file byte for byte after
canonicalization (amendment 2026-11-12: built once, stored as built; no path is rewritten here,
export strips the declared path fields). The envelope carries the run's invocation id, the
`pipeline` label the run passes in (the YAML's project-relative POSIX path, what
`library list --pipeline` reads) and the table names. Evidence links to nothing.

The run-result record stores the document `cli/run/_result.py` built, as built (`store_run_result`
rebuilds nothing). Its envelope links one way to the evidence record of the same run when one was
stored: an id hashes its links, so a later record can never be linked from an earlier one.

Records are on by default (4.16): `--no-library` or `DECOY_LIBRARY=off` skips them. A store that
fails never fails the run (4.17): `store_evidence` returns a coded outcome for the caller to warn
with, and never raises.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from decoy.cli.library._errors import LIBRARY_WRITE_FAILED, LibraryError

__all__ = ["StoreOutcome", "store_evidence", "store_run_result"]


@dataclass(frozen=True)
class StoreOutcome:
    """What happened to the run's records: `stored` (with the root and the evidence id),
    `skipped` (records are off) or `failed` (with a code; the run's exit code is unchanged)."""

    status: Literal["stored", "skipped", "failed"]
    root: Path | None = None
    evidence: str | None = None
    result: str | None = None
    code: str | None = None

    def to_json(self) -> dict[str, str]:
        out: dict[str, str] = {"status": self.status}
        if self.root is not None:
            out["root"] = str(self.root)
        if self.evidence is not None:
            out["evidence"] = self.evidence
        if self.result is not None:
            out["result"] = self.result
        if self.code is not None:
            out["code"] = self.code
        return out


def _put_record(
    kind: str,
    payload: Mapping[str, Any],
    *,
    root: Path,
    invocation_id: str,
    meta: Callable[[], tuple[Mapping[str, Any], list[dict[str, str]]]],
    stored: Callable[[Path, str], StoreOutcome],
    failed: Callable[[Path | None, str], StoreOutcome],
) -> StoreOutcome:
    """The one write path of a run's records: budget, envelope, put, and the exception map.

    `root` is the library root the run resolved once (`run/_context.py`): this path never
    resolves one, so a root the gate did not check cannot be written.

    `stored` and `failed` build the outcome (a record kind decides which ids it reports). Never
    raises: every library, layout and engine fault becomes a coded `failed` outcome (plan 4.17).
    """
    import decoy_engine
    from decoy_engine import DecoyError, records

    from decoy._version import __version__
    from decoy.cli.io import LayoutError
    from decoy.cli.library._paths import check_root_budget
    from decoy.cli.library._store import open_library

    code: str | None = None
    try:
        check_root_budget(root)
        labels, links = meta()  # inside the try: a malformed payload is a failed store, not a raise
        envelope = records.build(
            kind,
            dict(payload),
            producer={
                "name": "decoy-cli",
                "version": __version__,
                "engine_version": decoy_engine.__version__,
            },
            invocation_id=invocation_id,
            created_at=datetime.now(timezone.utc),
            labels=dict(labels),
            links=links,
        )
        return stored(root, open_library(root).put(envelope).id)
    except LibraryError as exc:
        code = exc.code
    except (LayoutError, DecoyError) as exc:
        code = str(getattr(exc, "code", None) or LIBRARY_WRITE_FAILED)
    except OSError:
        code = LIBRARY_WRITE_FAILED
    return failed(root, code)


def store_evidence(
    manifest: Mapping[str, Any],
    *,
    root: Path | None,
    label: str,
    invocation_id: str,
    enabled: bool = True,
) -> StoreOutcome:
    """Put the run's manifest as an `evidence` record in the library at `root`, the root the run
    resolved (None when records are off). `label` is the YAML's project-relative POSIX path.
    Never raises."""
    if not enabled or root is None:
        return StoreOutcome("skipped")
    return _put_record(
        "evidence",
        manifest,
        root=root,
        invocation_id=invocation_id,
        meta=lambda: (
            {"pipeline": label, "tables": sorted(manifest.get("output_fingerprints") or {})},
            [],
        ),
        stored=lambda root, rid: StoreOutcome("stored", root=root, evidence=rid),
        failed=lambda root, code: StoreOutcome("failed", root=root, code=code),
    )


def store_run_result(
    payload: Mapping[str, Any],
    *,
    root: Path | None,
    label: str,
    invocation_id: str,
    prior: StoreOutcome | None,
    enabled: bool = True,
) -> StoreOutcome:
    """Put the run's result document (the payload `_result.build` made) as a `run-result` record.

    `prior` is the evidence outcome of the same run: a stored evidence id becomes the record's
    `evidence` link. Returns the outcome with the result id added; never raises.
    """
    evidence = None if prior is None else prior.evidence
    if not enabled or root is None:
        return prior or StoreOutcome("skipped")
    return _put_record(
        "run-result",
        payload,
        root=root,
        invocation_id=invocation_id,
        meta=lambda: (
            {
                "pipeline": label,
                "tables": sorted(t["name"] for t in payload.get("tables") or ()),
                "status": payload.get("status"),
                "exit_code": payload.get("exit_code"),
            },
            [{"rel": "evidence", "id": evidence}] if evidence else [],
        ),
        stored=lambda root, rid: StoreOutcome("stored", root=root, evidence=evidence, result=rid),
        failed=lambda root, code: StoreOutcome("failed", root=root, evidence=evidence, code=code),
    )
