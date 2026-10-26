"""Checksum manifest for a CLI bundle (compute + verify).

Established methodology, ported pattern: a faithful port of the platform's
air-gapped install-bundle manifest, `decoy-platform/scripts/airgap/manifest.py`
(the same forward + reverse SHA-256 check the production offline installer uses),
reused here because the CLI repo cannot import the private platform package. The
manifest payload is signed by the shared Ed25519 primitive
(`decoy.distribution.signing`), so the release key proves the bundle's contents and
the installer verifies with only the public key.

Difference from the air-gapped source: a CLI bundle legitimately contains the embedded
interpreter's own INTERNAL symlinks (e.g. ``python3 -> python3.12``, terminfo aliases),
whereas the air-gapped Docker bundle had none and rejected all symlinks. So symlinks
are first-class manifest entries here: each records its link target, and verification
checks the target matches AND stays inside the bundle (a relative target that cannot
climb past the root). An absolute target, a target that escapes the root, or an
unlisted symlink is still rejected -- that is the symlink-escape attack the reverse
walk defends against.

The reverse walk still rejects any on-disk path (file OR symlink) not in the signed
manifest: a forward-only check would verify clean even if an attacker ADDED an unlisted
file.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_SCHEMA_VERSION = "cli-bundle-manifest/v1"
_CHUNK = 1 << 20
MANIFEST_NAME = "manifest.json"
MANIFEST_SIG_NAME = "manifest.json.sig"
_DEFAULT_IGNORE = (MANIFEST_NAME, MANIFEST_SIG_NAME)


def _is_unsafe_rel(path_str: str) -> bool:
    """A manifest entry path that is absolute or climbs out of root (`..`)."""
    return os.path.isabs(path_str) or ".." in Path(path_str).parts


def _is_regenerable(rel: str) -> bool:
    """True for interpreter-written bytecode caches. These CANNOT be part of a stable
    signed manifest: Python regenerates ``__pycache__/*.pyc`` on first run (and their
    bytes vary by interpreter patchlevel), and it writes them even during the install's
    own verify/self-check steps. Integrity rests on the signed ``.py`` SOURCE, which
    Python validates each cached ``.pyc`` against before loading it; a planted ``.pyc``
    whose source hash does not match is ignored by the interpreter. So they are excluded
    from both sides of the manifest rather than flagged as tampering."""
    parts = PurePosixPath(rel).parts
    return "__pycache__" in parts or rel.endswith((".pyc", ".pyo"))


def _symlink_target_escapes(rel: str, target: str) -> bool:
    """True if a symlink at ``rel`` pointing at ``target`` would resolve outside the
    bundle root. An absolute target always escapes; a relative target is resolved against
    the link's PARENT directory (posix semantics) and must not climb above the root.

    Resolution is tracked as a depth below root: it starts at the number of path
    components in the link's parent directory, each '..' decrements it and each normal
    component increments it. If depth ever goes negative the link has climbed above the
    root -- an escape."""
    if target.startswith("/") or PurePosixPath(target).is_absolute():
        return True
    parent_parts = [p for p in PurePosixPath(rel).parent.parts if p not in ("", ".")]
    depth = len(parent_parts)
    for part in PurePosixPath(target).parts:
        if part == ".":
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
        else:
            depth += 1
    return False


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _walk_entries(root: Path, ignore: set[str]):
    """Yield (rel, path) for every file and symlink under ``root`` (symlinks are not
    followed; dir-symlinks are yielded as entries and not descended), sorted for
    determinism."""
    collected: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        base = Path(dirpath)
        # Dir-symlinks appear in dirnames; record them and do not descend.
        # Prune __pycache__ dirs so the walk never descends into regenerable bytecode.
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in list(dirnames):
            p = base / name
            if p.is_symlink():
                rel = p.relative_to(root).as_posix()
                if rel not in ignore and not _is_regenerable(rel):
                    collected.append((rel, p))
                dirnames.remove(name)
        for name in filenames:
            p = base / name
            rel = p.relative_to(root).as_posix()
            if rel not in ignore and not _is_regenerable(rel):
                collected.append((rel, p))
    return sorted(collected, key=lambda t: t[0])


def compute_manifest(root: str | Path, *, version: str, target: str) -> dict[str, Any]:
    """Hash every bundle file and record every symlink into a signed payload.
    ``version``/``target`` bind the manifest to the release it describes. Raises if a
    symlink escapes the bundle (a well-formed bundle has only internal links)."""
    root = Path(root)
    ignore = set(_DEFAULT_IGNORE)
    entries: list[dict[str, Any]] = []
    for rel, p in _walk_entries(root, ignore):
        if p.is_symlink():
            tgt = os.readlink(p)
            if _symlink_target_escapes(rel, tgt):
                raise ValueError(f"bundle symlink escapes root: {rel} -> {tgt}")
            entries.append({"path": rel, "type": "link", "target": tgt})
        else:
            entries.append({"path": rel, "sha256": sha256_file(p), "size": p.stat().st_size})
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": version,
        "target": target,
        "files": entries,
    }


def verify_manifest(
    manifest: dict[str, Any], root: str | Path, *, ignore: tuple[str, ...] = _DEFAULT_IGNORE
) -> list[dict[str, str]]:
    """Return a list of problems ([] = clean). Each: {path, problem}. problem is one of
    'missing' | 'size' | 'hash' | 'unexpected' | 'symlink' | 'link-target' |
    'link-escape' | 'not-a-link' | 'unsafe_path' | 'unreadable'.

    Forward: every signed entry present + correct (hash for files, matching safe target
    for links). Reverse: every on-disk file/symlink must be in the signed manifest.
    Fails closed on an un-enumerable directory."""
    root = Path(root)
    problems: list[dict[str, str]] = []
    listed: set[str] = set()

    for e in manifest.get("files", []):
        rel = e["path"]
        if _is_unsafe_rel(rel):
            problems.append({"path": rel, "problem": "unsafe_path"})
            continue
        listed.add(rel)
        fp = root / rel
        is_link_entry = e.get("type") == "link"
        on_disk_link = fp.is_symlink()
        if is_link_entry:
            if not on_disk_link:
                problems.append({"path": rel, "problem": "not-a-link"})
                continue
            tgt = os.readlink(fp)
            if tgt != e.get("target"):
                problems.append({"path": rel, "problem": "link-target"})
            elif _symlink_target_escapes(rel, tgt):
                problems.append({"path": rel, "problem": "link-escape"})
            continue
        # file entry
        if on_disk_link:
            problems.append({"path": rel, "problem": "symlink"})
            continue
        if not fp.exists():
            problems.append({"path": rel, "problem": "missing"})
            continue
        if fp.stat().st_size != e.get("size"):
            problems.append({"path": rel, "problem": "size"})
            continue
        if sha256_file(fp) != e.get("sha256"):
            problems.append({"path": rel, "problem": "hash"})

    ignore_set = set(ignore)

    def _on_walk_error(err: OSError) -> None:
        fn = getattr(err, "filename", None)
        try:
            rel = str(Path(fn).relative_to(root)) if fn else str(err)
        except ValueError:
            rel = str(fn)
        problems.append({"path": rel, "problem": "unreadable"})

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_on_walk_error):
        base = Path(dirpath)
        # __pycache__ holds interpreter-written bytecode (regenerable, never signed); do
        # not descend into it and do not flag its contents as unexpected.
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in list(dirnames):
            p = base / name
            if p.is_symlink():
                rel = p.relative_to(root).as_posix()
                if rel not in listed:
                    problems.append({"path": rel, "problem": "unexpected"})
                dirnames.remove(name)
        for name in filenames:
            p = base / name
            rel = p.relative_to(root).as_posix()
            if rel in ignore_set or _is_regenerable(rel):
                continue
            if rel not in listed:
                problems.append({"path": rel, "problem": "unexpected"})
    return problems
