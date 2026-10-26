"""Verified install + atomic swap with rollback (the Python side shared by upgrade/tests).

`install.sh` is the shell bootstrap for the FIRST install, where no Python exists yet.
Once a managed runtime is in place, `decoy upgrade` runs here: it performs the exact
same verification chain against the distribution primitives, so the two paths cannot
drift in what they accept. A failed signature or checksum is a hard refusal
(``InstallError``), never a warning-and-continue.

Flow (mirrors install.sh):
  1. verify the version document's detached signature against the PINNED release key;
  2. select the target's {url, sha256, sig}; download the bundle + its signature;
  3. verify the SHA-256 against the signed document, then the bundle's Ed25519
     signature against the pinned key (the trust anchor);
  4. quarantine-extract; verify the in-bundle signed manifest (forward + reverse);
  5. run the new bundle's native-present self-check (loud refusal);
  6. flip ``current`` atomically to the new version, keeping the previous for rollback;
  7. post-swap validation; on any failure after the swap, roll ``current`` back.

The downloader + the optional post-swap validator are injected so the whole flow is
unit-testable offline and a failure can be injected at step 7 to exercise rollback.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from decoy.distribution import layout, verify_extracted
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


@dataclass(frozen=True)
class InstallOutcome:
    version: str
    target: str
    version_dir: Path
    previous_version: str | None
    rolled_back: bool


def _urllib_download(url: str) -> bytes:
    import urllib.request

    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _extract_bundle(tar_bytes: bytes, dest: Path) -> Path:
    """Safely extract the .tar.gz into ``dest`` and return the single top-level dir.

    Rejects member names that are absolute or climb out with '..', and symlink/hardlink
    members whose target escapes the extraction root (the symlink-escape attack). The
    embedded interpreter's own INTERNAL symlinks are allowed; the in-bundle signed
    manifest then re-checks every link target against what was signed."""
    import io

    from decoy.distribution.manifest import _symlink_target_escapes

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        members = tar.getmembers()
        tops: set[str] = set()
        for m in members:
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise InstallError(f"bundle archive has an unsafe path: {m.name!r}")
            if m.issym() or m.islnk():
                # Validate the link target cannot escape the bundle root.
                rel = p.as_posix()
                if m.islnk():
                    # hardlink target is a path within the archive; same escape test.
                    if _symlink_target_escapes(rel, m.linkname):
                        raise InstallError(f"bundle archive hardlink escapes root: {m.name!r}")
                elif _symlink_target_escapes(rel, m.linkname):
                    raise InstallError(f"bundle archive symlink escapes root: {m.name!r}")
            tops.add(p.parts[0])
        if len(tops) != 1:
            raise InstallError("bundle archive must hold exactly one top-level directory")
        # Members are validated above; the stdlib "data" filter (3.12+, backported to
        # recent 3.8-3.11 patch levels) is a second line that rejects absolute/escaping
        # paths and out-of-tree links. Fall back on a runtime too old to know it.
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)
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
    """Whether ``versions/<version>`` is already installed on disk (a retained runtime,
    e.g. the rollback target)."""
    return layout.version_dir(version, home or layout.decoy_home()).is_dir()


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
    dest = layout.version_dir(version, home)
    if not dest.is_dir():
        raise InstallError(f"version {version} is not installed locally")
    if expected_public_pem is not None:
        problems = verify_extracted.verify_extracted(dest, expected_public_pem=expected_public_pem)
        if problems:
            raise InstallError(
                "refusing to activate: local runtime failed verification: "
                + "; ".join(problems[:5])
            )
    if run_self_check:
        python_bin = dest / "python" / "bin" / "python3"
        proc = subprocess.run(
            [str(python_bin), "-m", "decoy.distribution.selfcheck"], capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise InstallError(
                "refusing to activate: native self-check failed for the local runtime: "
                + (proc.stderr.strip() or "no detail")
            )
    previous = layout.read_current_version(home)
    layout.atomic_point_current_at(version, home)
    _write_launcher_shim(home)
    return InstallOutcome(
        version=version,
        target=_bundle_declared_target(dest) or (targets_mod.detect_target() or "local"),
        version_dir=dest,
        previous_version=previous,
        rolled_back=False,
    )


def _bundle_declared_target(bundle_root: Path) -> str | None:
    import json

    try:
        return json.loads((bundle_root / _BUNDLE_INFO).read_text(encoding="utf-8")).get("target")
    except (OSError, ValueError, TypeError):
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
) -> InstallOutcome:
    home = home or layout.decoy_home()
    download = download or _urllib_download
    target = target or targets_mod.detect_target()
    if target is None:
        raise InstallError("unsupported platform; no bundle target for this host")

    # 1) version document signature (pinned key)
    if not vd.verify_document(version_doc_bytes, version_doc_sig_b64, expected_public_pem=expected_public_pem):
        raise InstallError("version-document signature invalid -- refusing (possible tampering)")
    doc = vd.parse_document(version_doc_bytes)
    version = pin_version or doc.get("latest")
    if not isinstance(version, str) or not version:
        raise InstallError("version document has no usable 'latest'")
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
        # The signature is the trust anchor; the sidecar sha is a best-effort corruption
        # check (it is unsigned, like install.sh's pinned path).
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

        # 5) native self-check through the NEW bundle's interpreter (loud refusal)
        if run_self_check:
            proc = subprocess.run(
                [str(python_bin), "-m", "decoy.distribution.selfcheck"],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise InstallError(
                    "native companion self-check failed for the new bundle -- refusing: "
                    + (proc.stderr.strip() or "no detail")
                )

        # Fail-closed defense in depth: the extracted bundle must DECLARE the version we
        # asked for. Without this, a wrong-version download (e.g. latest bits resolved
        # for a pinned older version) would overwrite -- and destroy -- the retained
        # versions/<version> rollback runtime with mislabeled bits. Checked BEFORE the
        # destructive rmtree, so a mismatch never touches an existing version dir.
        declared = _bundle_declared_version(bundle_root)
        if declared != version:
            raise InstallError(
                f"refusing to install: the downloaded bundle declares version "
                f"{declared!r} but {version!r} was requested (resolution mismatch); "
                f"versions/{version} on disk is left untouched"
            )

        dest = layout.version_dir(version, home)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(bundle_root), str(dest))
    finally:
        shutil.rmtree(incoming, ignore_errors=True)

    # 6) atomic swap, keeping the previous for rollback
    previous = layout.read_current_version(home)
    layout.atomic_point_current_at(version, home)

    # 7) post-swap validation; roll back current on failure
    rolled_back = False
    if post_swap_validate is not None:
        try:
            ok = post_swap_validate(layout.current_link(home))
        except Exception:
            ok = False
        if not ok:
            if previous is not None:
                layout.atomic_point_current_at(previous, home)
            rolled_back = True
            raise InstallError(
                f"post-upgrade validation failed; rolled back to {previous!r}. "
                f"The new runtime {version} remains on disk but is not active."
            )

    _write_launcher_shim(home)
    return InstallOutcome(
        version=version,
        target=target,
        version_dir=layout.version_dir(version, home),
        previous_version=previous,
        rolled_back=rolled_back,
    )


def _write_launcher_shim(home: Path) -> None:
    """Write/refresh the PATH launcher shim that execs ``<home>/current/decoy``. POSIX
    only; on Windows the installer writes a .cmd shim (see install.ps1)."""
    if sys.platform.startswith("win"):
        return
    bin_dir = layout.launcher_bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / layout.LAUNCHER_NAME
    shim.write_text(
        f'#!/bin/sh\nexec "{home}/current/decoy" "$@"\n', encoding="utf-8"
    )
    shim.chmod(0o755)


def prune_old_versions(home: Path | None = None, *, keep: int = 2) -> list[str]:
    """Keep the ``current`` version and the ``keep`` most-recent others (for rollback),
    removing the rest. Returns the versions removed. Never removes ``current``."""
    home = home or layout.decoy_home()
    versions = layout.versions_dir(home)
    if not versions.is_dir():
        return []
    current = layout.read_current_version(home)
    entries = [d.name for d in versions.iterdir() if d.is_dir() and not d.name.startswith(".incoming")]

    def _key(name: str):
        try:
            from packaging.version import Version

            return (1, Version(name))
        except Exception:
            return (0, name)

    ordered = sorted(entries, key=_key, reverse=True)
    keepers = set()
    if current:
        keepers.add(current)
    for name in ordered:
        if len(keepers) >= keep + (1 if current else 0):
            break
        keepers.add(name)
    removed = []
    for name in entries:
        if name not in keepers:
            shutil.rmtree(versions / name, ignore_errors=True)
            removed.append(name)
    return removed
