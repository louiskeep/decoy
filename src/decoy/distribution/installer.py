"""Verified install + atomic swap with rollback (the Python side shared by upgrade/tests).

`install.sh` is the shell bootstrap for the FIRST install, where no Python exists yet.
Once a managed runtime is in place, `decoy upgrade` runs here: it performs the exact
same verification chain against the distribution primitives, so the two paths cannot
drift in what they accept. A failed signature or checksum is a hard refusal
(``InstallError``), never a warning-and-continue.

Flow (mirrors install.sh):
  1. verify the version document's detached signature against the PINNED release key,
     then its freshness (unexpired, ``serial`` not below the highest ever accepted, see
     below) and its ``min_supported`` floor;
  2. select the target's {url, sha256, sig}; download the bundle + its signature;
  3. verify the SHA-256 against the signed document, then the bundle's Ed25519
     signature against the pinned key (the trust anchor);
  4. quarantine-extract; verify the in-bundle signed manifest (forward + reverse);
  5. refuse a bundle that does not declare the requested version AND target (before its
     interpreter runs), then run its native-present self-check (loud refusal);
  6. stage the verified bits into a FRESH ``versions/`` slot (never mutating an existing
     ``versions/<version>`` in place), then flip ``current`` atomically to it;
  7. post-swap validation; on failure flip ``current`` back; once live, reclaim the old
     same-version slot.

Every mutation (stage, flip, validate, rollback, reclaim, prune) runs under one
single-flight per-installation lock (`decoy.distribution.lock`); a second concurrent
command is refused rather than queued, so one process can never reclaim the slot another
just made live. ``current`` may point at a ``<version>+<build>`` repair slot; the slot name
is internal and every user-facing value is the semantic version (`layout.slot_version`).

A ``versions/<version>`` directory is never replaced in place (Cam decision): a first or
different-version install renames the bits into the absent ``versions/<version>``, and a
same-version repair stages them into a distinct ``versions/<version>+<build>`` and flips
to that, leaving the live runtime untouched until the flip. The flip is the one atomic
state change, so there is no move-aside, backup, restore, or signal-trap recovery to get
wrong: an interruption at any point leaves either the old runtime live (flip not reached)
or the new one (flip done), never a missing ``current``.

Freshness / anti-rollback (TUF pattern, https://theupdateframework.github.io/specification/latest/:
timestamp-role ``version`` + ``expires``, client-side "fast-forward/rollback attack"
checks): a signature proves who signed a document, not that it is current. The signed
document therefore carries a monotonic ``serial`` and an ``expires`` deadline. An expired
document is refused, and the highest accepted ``serial`` and the ``latest`` it carried are
persisted in ``<DECOY_HOME>/trust_state.json`` so a replayed older signed document (lower
serial) cannot freeze or downgrade a client. ``install.sh`` applies the same rules to the
same file. The file is local state, not a secret: an attacker who can write it can already
replace the runtime.

The downloader + the optional post-swap validator are injected so the whole flow is
unit-testable offline and a failure can be injected at step 7 to exercise rollback.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from decoy.distribution import layout, lock, verify_extracted
from decoy.distribution import manifest as manifest_mod
from decoy.distribution import targets as targets_mod
from decoy.distribution import version_document as vd

Downloader = Callable[[str], bytes]
PostSwapValidator = Callable[[Path], bool]

# The per-bundle metadata file the assembler writes (packaging_tools/build_bundle.py).
_BUNDLE_INFO = "BUNDLE_INFO.json"


class InstallError(RuntimeError):
    """A hard refusal: a failed verification or a broken bundle. The managed runtime is
    left exactly as it was (or rolled back)."""


@contextlib.contextmanager
def _exclusive(home: Path):
    """Hold the per-installation single-flight lock (`decoy.distribution.lock`) for a whole
    mutate-then-reclaim critical section; a held lock is a refusal, not a queue."""
    try:
        with lock.exclusive(home):
            yield
    except lock.InstallBusyError as exc:
        raise InstallError(str(exc)) from exc


@dataclass(frozen=True)
class InstallOutcome:
    version: str
    target: str
    version_dir: Path
    previous_version: str | None
    rolled_back: bool
    # A semantic version that is still retained on disk and so can be rolled back to
    # locally; None when the previous runtime is gone or is the same version.
    rollback_version: str | None = None


def _fresh_same_version_slot(versions: Path, version: str) -> Path:
    """A ``versions/<version>+<build>`` dir that does not yet exist, for staging a
    same-version repair WITHOUT touching the live ``versions/<version>``. The ``+<build>``
    suffix keeps the semantic version readable (``layout.slot_version`` strips it) while
    guaranteeing a distinct directory to flip to."""
    n = 0
    while True:
        n += 1
        candidate = versions / f"{version}+{os.getpid()}.{n}"
        if not candidate.exists():
            return candidate


def _promote_staged(bundle_root: Path, version: str, versions: Path) -> Path:
    """Rename the validated ``bundle_root`` into a FRESH ``versions/`` slot and return it.

    Never mutates an existing ``versions/<version>`` in place: a first or different-version
    install renames the bits into the absent ``versions/<version>``; a same-version repair
    renames them into a distinct ``versions/<version>+<build>`` so the live runtime is
    untouched until the caller's atomic flip confirms the replacement (and the old slot is
    reclaimed afterward). The rename is within ``versions`` (one filesystem), so it is
    atomic; a failure leaves the existing runtime live and the staged bits in the
    quarantine dir, with no move-aside/backup/restore to unwind."""
    dest = versions / version
    target = dest if not dest.exists() else _fresh_same_version_slot(versions, version)
    try:
        os.replace(bundle_root, target)
    except OSError as exc:
        raise InstallError(
            f"could not stage the new runtime into versions/{target.name}: {exc}; "
            "the existing runtime is intact"
        ) from exc
    return target


def _reclaim_superseded(versions: Path, version: str, live_slot: str) -> None:
    """Drop every other ``versions/`` slot that holds ``version`` once ``live_slot`` is the
    live one, so a same-version repair leaves exactly one slot for the version. Reclamation
    is not time-critical and never touches a different version's slot (those are the
    retained rollback targets). Callers hold the installation lock, so ``current`` cannot
    move underneath this; it is still re-read so the live slot is never a candidate."""
    live_now = layout.read_current_slot(versions.parent)
    for entry in versions.iterdir():
        if entry.name.startswith(".") or entry.name in (live_slot, live_now):
            continue
        if layout.slot_version(entry.name) == version:
            shutil.rmtree(entry, ignore_errors=True)


def _sweep_stale_staging(versions: Path) -> None:
    """Drop quarantine dirs a killed run left behind. Safe only because the caller holds
    the installation lock, so no live process owns a ``.incoming.*`` dir."""
    for entry in versions.glob(".incoming.*"):
        shutil.rmtree(entry, ignore_errors=True)


_TRUST_STATE = "trust_state.json"


def _read_trust_state(home: Path) -> dict:
    """Absent state is a first run ({}); a present but unreadable/invalid one is refused,
    never treated as "nothing seen", or corrupting the file would reset rollback protection."""
    import json

    path = home / _TRUST_STATE
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc} -- refusing (trust state unreadable)") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise InstallError(f"{path} is corrupt -- refusing (trust state unreadable)") from exc
    serial = data.get("serial") if isinstance(data, dict) else None
    if not isinstance(serial, int) or isinstance(serial, bool) or serial < 0:
        raise InstallError(f"{path} has no valid 'serial' -- refusing (trust state unreadable)")
    return data


def _trust_state_text(latest: object, serial: int) -> str:
    """Canonical compact sorted form; ``install.sh`` reads the serial from it with a
    whitespace-tolerant pattern, so the two sides do not depend on matching formatting."""
    import json

    return json.dumps({"latest": latest, "serial": serial}, sort_keys=True, separators=(",", ":")) + "\n"


def check_document_freshness(
    doc: dict, home: Path, *, now: _dt.datetime | None = None, record: bool = True
) -> None:
    """Refuse an expired or replayed (lower ``serial``) signature-verified document; with
    ``record`` persist the accepted serial/latest to ``<home>/trust_state.json``. Raises InstallError."""
    try:
        vd.check_fresh(doc, now=now)
    except ValueError as exc:
        raise InstallError(f"version document rejected: {exc}") from exc
    state = _read_trust_state(home)
    seen_serial = state.get("serial") if isinstance(state.get("serial"), int) else 0
    serial, latest = doc["serial"], doc.get("latest")
    if serial < seen_serial:
        raise InstallError(
            f"version document serial {serial} is older than the newest accepted ({seen_serial}) "
            "-- refusing (rollback/replay)"
        )
    if not record:
        return
    # ``latest`` is recorded for diagnostics only: a signer may legitimately move it back
    # (pull a bad release) under a HIGHER serial, so the serial alone gates rollback.
    home.mkdir(parents=True, exist_ok=True)
    tmp = home / f".{_TRUST_STATE}.{os.getpid()}.tmp"
    tmp.write_text(_trust_state_text(latest, serial), encoding="utf-8")
    os.replace(tmp, home / _TRUST_STATE)


def _urllib_download(url: str) -> bytes:
    import urllib.request

    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _no_bytecode_env() -> dict[str, str]:
    """Env for spawning the bundled interpreter so it writes NO bytecode caches into the
    managed runtime. The bundle manifest does not sign ``__pycache__``/``.pyc`` and the
    verifier rejects any found on disk (see `decoy.distribution.manifest`), so install-
    and activation-time self-checks must not leave caches behind that a later
    verify/rollback would then refuse."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _selfcheck(python_bin: Path) -> subprocess.CompletedProcess:
    """Run the bundle's native self-check through its own interpreter, import-isolated
    and bytecode-free (``-I -B`` + env).

    ``-I`` drops the CWD/script dir from ``sys.path`` and ignores ``PYTHONPATH``/
    ``PYTHON*`` env, so a hostile working directory or environment at install/activation
    time cannot shadow the signed runtime with a planted ``decoy``/``decoy_engine``
    package and forge a passing self-check. ``-B`` stops bytecode writes so the check
    never leaves an unsigned ``__pycache__`` the manifest does not cover (``-I`` ignores
    the env var, so the explicit flag is what guarantees it here)."""
    return subprocess.run(
        [str(python_bin), "-I", "-B", "-m", "decoy.distribution.selfcheck"],
        capture_output=True,
        text=True,
        env=_no_bytecode_env(),
    )


_MAX_LINK_HOPS = 40


def _resolve_in_archive(rel: str, symlinks: dict[str, str]) -> str | None:
    """Resolve archive-root-relative ``rel`` through the symlinks already seen in the
    archive, component by component, as the filesystem would after extraction. Returns the
    normalized real path, or None if it climbs above the root (or loops)."""
    done: list[str] = []
    todo = list(PurePosixPath(rel).parts)
    hops = 0
    while todo:
        part = todo.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if not done:
                return None
            done.pop()
            continue
        here = "/".join([*done, part])
        if here in symlinks:
            hops += 1
            target = symlinks[here]
            if hops > _MAX_LINK_HOPS or target.startswith("/"):
                return None
            todo = list(PurePosixPath(target).parts) + todo
            continue
        done.append(part)
    return "/".join(done)


def _extract_bundle(tar_bytes: bytes, dest: Path) -> Path:
    """Safely extract the .tar.gz into ``dest`` and return the single top-level dir.

    Rejects member names that are absolute or climb out with '..', members written through
    an earlier symlink, symlinks whose target escapes the extraction root, and hardlinks
    whose archive-root path is absolute, climbs out, or resolves (through earlier symlinks)
    outside the root. The embedded interpreter's own INTERNAL symlinks are allowed; the
    in-bundle signed manifest then re-checks every link target against what was signed.
    Extraction is ONLY done with the stdlib "data" filter; a runtime without it refuses."""
    import io

    from decoy.distribution.manifest import _symlink_target_escapes

    if not hasattr(tarfile, "data_filter"):
        raise InstallError(
            "this Python's tarfile has no extraction filters (needs 3.12+ or a recent 3.8-3.11 "
            "patch release); refusing to extract an archive unfiltered"
        )

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        members = tar.getmembers()
        tops: set[str] = set()
        symlinks: dict[str, str] = {}
        for m in members:
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise InstallError(f"bundle archive has an unsafe path: {m.name!r}")
            rel = PurePosixPath(m.name).as_posix()
            # A member must not be written THROUGH a symlink extracted earlier.
            parent = PurePosixPath(rel).parent.as_posix()
            if parent != "." and _resolve_in_archive(parent, symlinks) != PurePosixPath(parent).as_posix():
                raise InstallError(f"bundle archive member writes through a symlink: {m.name!r}")
            if m.issym():
                if _symlink_target_escapes(rel, m.linkname):
                    raise InstallError(f"bundle archive symlink escapes root: {m.name!r}")
                symlinks[rel] = m.linkname
            elif m.islnk():
                # A hardlink name is a path from the ARCHIVE ROOT (not relative to the
                # link), so it is validated as one, then resolved through earlier symlinks.
                lp = PurePosixPath(m.linkname)
                if lp.is_absolute() or ".." in lp.parts or not m.linkname:
                    raise InstallError(f"bundle archive hardlink escapes root: {m.name!r}")
                if _resolve_in_archive(m.linkname, symlinks) is None:
                    raise InstallError(f"bundle archive hardlink escapes root: {m.name!r}")
            tops.add(p.parts[0])
        if len(tops) != 1:
            raise InstallError("bundle archive must hold exactly one top-level directory")
        try:
            tar.extractall(dest, filter="data")
        except TypeError as exc:
            raise InstallError("tarfile rejected the 'data' extraction filter; refusing to extract unfiltered") from exc
    return dest / next(iter(tops))


def _try_download_sha(download: Downloader, url: str) -> str | None:
    """Best-effort fetch of a ``.sha256`` sidecar; returns its hex digest or None. A
    missing sidecar is not fatal (the Ed25519 signature is the real trust anchor)."""
    try:
        parts = download(url).decode("ascii").split()
    except Exception:
        return None
    return parts[0] if parts else None


def _bundle_declared_version(bundle_root: Path) -> str | None:
    """The version the extracted bundle declares (BUNDLE_INFO.json, falling back to the
    signed manifest). None if neither is readable, which the caller treats as a refusal."""
    import json

    for name, key in ((_BUNDLE_INFO, "version"), (manifest_mod.MANIFEST_NAME, "version")):
        try:
            return json.loads((bundle_root / name).read_text(encoding="utf-8"))[key]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def local_version_present(version: str, home: Path | None = None) -> bool:
    """Whether a slot holding the SEMANTIC ``version`` is retained on disk (e.g. the
    rollback target), whatever repair-slot name it lives under."""
    return layout.resolve_slot(version, home or layout.decoy_home()) is not None


def activate_local_version(
    version: str,
    home: Path | None = None,
    *,
    expected_public_pem: str | None = None,
    run_self_check: bool = True,
) -> InstallOutcome:
    """Point ``current`` at an already-installed ``versions/<version>`` via an atomic
    symlink swap -- the local rollback path (no download, no overwrite). Re-verifies the
    on-disk runtime (manifest + native self-check) before activating, so a corrupted or
    companion-stripped retained runtime is refused rather than activated."""
    home = home or layout.decoy_home()
    with _exclusive(home):
        slot = layout.resolve_slot(version, home)
        if slot is None:
            raise InstallError(f"version {version} is not installed locally")
        dest = layout.versions_dir(home) / slot
        if expected_public_pem is not None:
            problems = verify_extracted.verify_extracted(dest, expected_public_pem=expected_public_pem)
            if problems:
                raise InstallError(
                    "refusing to activate: local runtime failed verification: "
                    + "; ".join(problems[:5])
                )
        if run_self_check:
            python_bin = dest / "python" / "bin" / "python3"
            proc = _selfcheck(python_bin)
            if proc.returncode != 0:
                raise InstallError(
                    "refusing to activate: native self-check failed for the local runtime: "
                    + (proc.stderr.strip() or "no detail")
                )
        previous = layout.read_current_version(home)
        layout.atomic_point_current_at(slot, home)
        _write_launcher_shim(home)
        return InstallOutcome(
            version=version,
            target=_bundle_declared_target(dest) or (targets_mod.detect_target() or "local"),
            version_dir=dest,
            previous_version=previous,
            rolled_back=False,
            rollback_version=_retained_other(previous, version, home),
        )


def _retained_other(previous: str | None, version: str, home: Path) -> str | None:
    """``previous`` when it is a different version that is still on disk (a real rollback
    destination), else None."""
    if previous is None or previous == version:
        return None
    return previous if layout.resolve_slot(previous, home) is not None else None


def _bundle_declared_target(bundle_root: Path) -> str | None:
    """The target the extracted bundle declares (BUNDLE_INFO.json, falling back to the
    signed manifest). None if neither is readable, which the caller treats as a refusal."""
    import json

    for name in (_BUNDLE_INFO, manifest_mod.MANIFEST_NAME):
        try:
            return json.loads((bundle_root / name).read_text(encoding="utf-8"))["target"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def install_version(
    *,
    version_doc_bytes: bytes,
    version_doc_sig_b64: str,
    expected_public_pem: str,
    target: str | None = None,
    home: Path | None = None,
    pin_version: str | None = None,
    base_url: str | None = None,
    download: Downloader | None = None,
    run_self_check: bool = True,
    post_swap_validate: PostSwapValidator | None = None,
    now: _dt.datetime | None = None,
) -> InstallOutcome:
    home = home or layout.decoy_home()
    with _exclusive(home):
        download = download or _urllib_download
        target = target or targets_mod.detect_target()
        if target is None:
            raise InstallError("unsupported platform; no bundle target for this host")

        # 1) version document signature (pinned key)
        if not vd.verify_document(version_doc_bytes, version_doc_sig_b64, expected_public_pem=expected_public_pem):
            raise InstallError("version-document signature invalid -- refusing (possible tampering)")
        try:
            doc = vd.parse_document(version_doc_bytes)
        except ValueError as exc:
            # A correctly signed document of the wrong schema/shape is still a refusal, not
            # a traceback (JSONDecodeError is a ValueError).
            raise InstallError(f"version document rejected: {exc}") from exc
        check_document_freshness(doc, home, now=now)
        version = pin_version or doc.get("latest")
        if not isinstance(version, str) or not version:
            raise InstallError("version document has no usable 'latest'")
        try:
            below = vd.below_floor(version, doc)
        except ValueError:
            below = False
        if below:
            raise InstallError(
                f"version {version} is below the signed min_supported {doc.get('min_supported')} -- refusing"
            )
        if vd.is_yanked(doc, version):
            raise InstallError(f"version {version} is yanked -- refusing")

        # 2) resolve the bundle URL for the REQUESTED version (not blindly the latest),
        #    then download. The v1 document carries only the latest release's artifacts, so
        #    a pinned non-latest version resolves by the published URL convention -- the same
        #    scheme install.sh uses -- from the base the version document was served under.
        expected_sha: str | None
        if version == doc.get("latest"):
            art = vd.select_artifact(doc, target)
            if art is None:
                raise InstallError(f"version document lists no bundle for target {target}")
            url, sig_url, expected_sha = art["url"], art["sig"], art["sha256"]
        else:
            if not base_url:
                raise InstallError(
                    f"cannot resolve pinned version {version}: the version document lists "
                    "only the latest release and no base URL was given to resolve older bundles"
                )
            name = f"decoy-{version}-{target}.tar.gz"
            url = f"{base_url.rstrip('/')}/{version}/{name}"
            sig_url = url + ".sig"
            # CHECKSUM EXCEPTION: the signed v1 document carries only the latest release's
            # sha256, so a pinned older download has NO signed checksum. The sidecar is an
            # unsigned, best-effort corruption check (skipped if absent); the Ed25519 bundle
            # signature below is the sole trust anchor on this path, as in install.sh.
            expected_sha = _try_download_sha(download, url + ".sha256")

        tar_bytes = download(url)
        sig_b64 = download(sig_url).decode("ascii").strip()

        # 3) checksum (when known) then signature (the trust anchor, always enforced)
        if expected_sha is not None:
            got_sha = manifest_mod.sha256_bytes(tar_bytes)
            if got_sha != expected_sha:
                raise InstallError(f"bundle checksum mismatch (expected {expected_sha} got {got_sha})")
        from decoy.distribution import signing

        if not signing.verify_detached(tar_bytes, sig_b64, expected_public_pem=expected_public_pem):
            raise InstallError("bundle signature invalid -- refusing (possible tampering)")

        # 4) quarantine-extract + manifest verify (defense in depth)
        versions = layout.versions_dir(home)
        versions.mkdir(parents=True, exist_ok=True)
        _sweep_stale_staging(versions)
        incoming = versions / f".incoming.{version}.{os.getpid()}"
        if incoming.exists():
            shutil.rmtree(incoming)
        try:
            bundle_root = _extract_bundle(tar_bytes, incoming)
            problems = verify_extracted.verify_extracted(bundle_root, expected_public_pem=expected_public_pem)
            if problems:
                raise InstallError("bundle manifest verification failed: " + "; ".join(problems[:5]))

            python_bin = bundle_root / "python" / "bin" / "python3"
            if not python_bin.exists():
                raise InstallError("bundle is missing its interpreter")

            # Fail-closed defense in depth: the extracted bundle must DECLARE the version AND
            # the target we asked for. Without this, a wrong-version OR wrong-target download
            # (e.g. latest bits resolved for a pinned older version, or another platform's
            # bundle served at a pinned URL) would be staged + flipped to as mislabeled bits.
            # Checked BEFORE the new bundle's interpreter runs (self-check) and BEFORE any staging, so a
            # mismatch never executes the bundle, creates a slot, or touches a retained runtime.
            declared = _bundle_declared_version(bundle_root)
            if declared != version:
                raise InstallError(
                    f"refusing to install: the downloaded bundle declares version "
                    f"{declared!r} but {version!r} was requested (resolution mismatch); "
                    f"versions/{version} on disk is left untouched"
                )
            declared_target = _bundle_declared_target(bundle_root)
            if declared_target != target:
                raise InstallError(
                    f"refusing to install: the downloaded bundle declares target "
                    f"{declared_target!r} but this host is {target!r} (resolution mismatch); "
                    f"versions/{version} on disk is left untouched"
                )

            # 5) native self-check through the NEW bundle's interpreter (loud refusal)
            if run_self_check:
                proc = _selfcheck(python_bin)
                if proc.returncode != 0:
                    raise InstallError(
                        "native companion self-check failed for the new bundle -- refusing: "
                        + (proc.stderr.strip() or "no detail")
                    )

            # Stage the validated bits into a FRESH slot. An existing versions/<version> is
            # never mutated in place: a same-version repair stages a distinct
            # versions/<version>+<build> instead, so the live runtime is untouched right up to
            # the atomic flip below. Nothing is moved aside, so there is nothing to restore.
            previous = layout.read_current_version(home)
            previous_slot = layout.read_current_slot(home)
            slot = _promote_staged(bundle_root, version, versions)
        finally:
            shutil.rmtree(incoming, ignore_errors=True)

        # 6) THE atomic flip: point `current` at the freshly staged slot. This is the only
        #    operation that makes the new runtime live. Before it, the prior runtime is still
        #    live; the flip is all-or-nothing (a temp symlink os.replace'd over `current`), so
        #    an interruption (INT/TERM/HUP/KILL) at any point leaves EITHER the prior runtime
        #    live (flip not reached) OR the new one (flip done), never a missing `current`.
        layout.atomic_point_current_at(slot.name, home)

        # 7) post-swap validation; on failure flip `current` back to the prior runtime (still
        #    on disk -- a same-version repair never touched versions/<version>, a different
        #    version is its own untouched slot) and drop the unvalidated replacement.
        rolled_back = False
        if post_swap_validate is not None:
            try:
                ok = post_swap_validate(layout.current_link(home))
            except Exception:
                ok = False
            if not ok:
                # Switch `current` away from the failed slot FIRST; only a slot that is no
                # longer live may be deleted. With no previous runtime (an interrupted first
                # install left `current` absent) there is nothing to flip back to, so restore
                # the absent state by unlinking the symlink and keep whatever is retained.
                if previous_slot is not None:
                    layout.atomic_point_current_at(previous_slot, home)
                else:
                    with contextlib.suppress(FileNotFoundError):
                        layout.current_link(home).unlink()
                same_version_repair = slot.name != version
                if same_version_repair and layout.read_current_slot(home) != slot.name:
                    shutil.rmtree(slot, ignore_errors=True)
                if previous_slot is None:
                    raise InstallError(
                        f"post-install validation failed; the new runtime {version} was left "
                        "inactive (there was no previous runtime to restore, so no runtime is "
                        "live -- rerun `decoy upgrade --force` or the install script)."
                    )
                rolled_back = True
                kept = (
                    f"restored the previous {version} runtime (the live runtime is intact)"
                    if same_version_repair
                    else f"The new runtime {version} remains on disk but is not active"
                )
                raise InstallError(f"post-upgrade validation failed; rolled back to {previous!r}. {kept}.")

        # Replacement is live: reclaim any older slot still holding this version (a same-version
        # repair's prior dir). A different version's slot is left as the rollback target.
        _reclaim_superseded(versions, version, slot.name)
        _write_launcher_shim(home)
        return InstallOutcome(
            version=version,
            target=target,
            version_dir=slot,
            previous_version=previous,
            rolled_back=rolled_back,
            rollback_version=_retained_other(previous, version, home),
        )


def _write_launcher_shim(home: Path) -> None:
    """Write/refresh the PATH launcher shim that execs ``<home>/current/decoy``. POSIX
    only; on Windows the installer writes a .cmd shim (see install.ps1).

    The live launcher is never truncated in place: an already-correct shim is left alone,
    otherwise a sibling temp file is written, chmod'ed, and ``os.replace``d over it (the
    same atomic-rename discipline as the ``current`` flip), so an interruption leaves the
    old launcher or the new one, never a zero-byte ``decoy``."""
    if sys.platform.startswith("win"):
        return
    bin_dir = layout.launcher_bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / layout.LAUNCHER_NAME
    content = f'#!/bin/sh\nexec "{home}/current/decoy" "$@"\n'
    try:
        if (
            not shim.is_symlink()
            and shim.read_text(encoding="utf-8") == content
            and os.access(shim, os.X_OK)
        ):
            return
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=bin_dir, prefix=f".{layout.LAUNCHER_NAME}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, 0o755)
        os.replace(tmp, shim)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def prune_old_versions(home: Path | None = None, *, keep: int = 2) -> list[str]:
    """Keep the live runtime and the ``keep`` most-recent OTHER semantic versions (for
    rollback), removing the rest. Versions are counted by semantic version, never by slot,
    so abandoned repair slots neither consume the budget nor survive. Returns the slot
    names removed. Never removes the live slot."""
    home = home or layout.decoy_home()
    versions = layout.versions_dir(home)
    if not versions.is_dir():
        return []
    with _exclusive(home):
        live_slot = layout.read_current_slot(home)
        live_version = layout.read_current_version(home)
        # Skip transient promotion dirs (.incoming/.staged/.backup/.failed); only real
        # slots are prune candidates.
        slots = [d.name for d in versions.iterdir() if d.is_dir() and not d.name.startswith(".")]
        distinct = {layout.slot_version(n) for n in slots} - {live_version}

        def _key(name: str):
            try:
                from packaging.version import Version

                return (1, Version(name))
            except Exception:
                return (0, name)

        kept_versions = set(sorted(distinct, key=_key, reverse=True)[:keep])
        if live_version:
            kept_versions.add(live_version)
        # One slot per retained version: the live slot for the live version, the newest
        # slot for each retained rollback version.
        keep_slots = {live_slot} | {layout.resolve_slot(v, home) for v in kept_versions - {live_version}}
        removed = []
        for name in slots:
            if name not in keep_slots:
                shutil.rmtree(versions / name, ignore_errors=True)
                removed.append(name)
        return removed
