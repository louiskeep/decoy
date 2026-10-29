"""On-disk layout of the managed, self-contained runtime under ``~/.decoy``.

The model is the one `uv`/`rye`/`rustup` use: a versioned install directory plus a
``current`` symlink, so an upgrade is an atomic symlink swap and rollback is the swap
back. One bundle version never overwrites another in place, so a failed upgrade
cannot leave a half-written live runtime.

    ~/.decoy/
      versions/<version>/        one extracted bundle (python/, decoy launcher, wheels, manifest)
      current -> versions/<version>   the live runtime (atomic swap point)
      cache/                     startup-notice check cache (timestamp + last-seen latest)

The launcher that goes on PATH (``~/.local/bin/decoy`` on POSIX) points through
``current``, so the swap is the only thing an upgrade touches on PATH.

This module is pure path arithmetic + the atomic swap primitive; it does no network
or extraction. ``DECOY_HOME`` overrides the root (used by the test harness to install
into a throwaway dir).
"""

from __future__ import annotations

import os
from pathlib import Path

LAUNCHER_NAME = "decoy"


def decoy_home() -> Path:
    override = os.environ.get("DECOY_HOME")
    return Path(override) if override else Path.home() / ".decoy"


def versions_dir(home: Path | None = None) -> Path:
    return (home or decoy_home()) / "versions"


def version_dir(version: str, home: Path | None = None) -> Path:
    return versions_dir(home) / version


def slot_version(slot_name: str) -> str:
    """The semantic version a ``versions/`` slot directory encodes.

    A slot is normally named exactly ``<version>``. A same-version repair must not mutate
    the live ``versions/<version>`` in place, so it stages the fresh bits into a distinct
    ``versions/<version>+<build>`` and flips ``current`` to that; this strips the build
    suffix we add (decoy versions carry no PEP 440 local segment of their own) to recover
    the semantic version the slot holds."""
    return slot_name.split("+", 1)[0]


def current_link(home: Path | None = None) -> Path:
    return (home or decoy_home()) / "current"


def managed_home() -> Path | None:
    """The managed-runtime home IFF this interpreter is a bundled-runtime interpreter.

    A managed interpreter's ``sys.prefix`` is exactly ``<home>/versions/<slot>/python``, and
    the home must carry a ``current`` symlink into ``versions/`` and the slot a bundle
    ``manifest.json``. An ancestor named ``versions`` alone is not identity (pyenv keeps
    interpreters under ``.pyenv/versions/<x>``), nor is a venv nested inside a bundle.
    Deriving the home from the interpreter, not ``DECOY_HOME``, keeps a custom-home install
    working when the env var is unset. None for a pip/dev install, which keeps the pip/dev
    import contract separate from the managed run-time guard."""
    import sys

    from decoy.distribution.manifest import MANIFEST_NAME

    try:
        prefix = Path(sys.prefix).resolve()
        slot = prefix.parent
        home = slot.parent.parent
        if prefix.name != "python" or slot.parent.name != "versions":
            return None
        if not (slot / MANIFEST_NAME).is_file():
            return None
        link = current_link(home)
        if not link.is_symlink() or Path(os.readlink(link)).parent.name != "versions":
            return None
    except OSError:
        return None
    return home


def cache_dir(home: Path | None = None) -> Path:
    return (home or decoy_home()) / "cache"


def launcher_bin_dir() -> Path:
    """Where the ``decoy`` launcher symlink goes on POSIX (`~/.local/bin`, the XDG
    user-local convention the install script adds to PATH)."""
    return Path(os.environ.get("DECOY_BIN_DIR", str(Path.home() / ".local" / "bin")))


def read_current_slot(home: Path | None = None) -> str | None:
    """The raw ``versions/`` slot name ``current`` points at (internal identity: may be a
    ``<version>+<build>`` repair slot), or None if there is no live runtime."""
    try:
        target = os.readlink(current_link(home))
    except OSError:
        return None
    return Path(target).name


def read_current_version(home: Path | None = None) -> str | None:
    """The SEMANTIC version of the live runtime, or None. Slot identity never leaks into
    user-facing output or rollback hints; use ``read_current_slot`` for the directory."""
    slot = read_current_slot(home)
    return None if slot is None else slot_version(slot)


def slots_for_version(version: str, home: Path | None = None) -> list[str]:
    """Every real ``versions/`` slot holding ``version``, live slot first, then newest."""
    versions = versions_dir(home)
    if not versions.is_dir():
        return []
    live = read_current_slot(home)
    found = [
        d for d in versions.iterdir()
        if d.is_dir() and not d.name.startswith(".") and slot_version(d.name) == version
    ]
    found.sort(key=lambda d: (d.name != live, -d.stat().st_mtime_ns, d.name))
    return [d.name for d in found]


def resolve_slot(version: str, home: Path | None = None) -> str | None:
    """The retained slot that satisfies the semantic ``version`` (the live one if it
    matches), or None when no slot holds it."""
    slots = slots_for_version(version, home)
    return slots[0] if slots else None


def atomic_point_current_at(slot: str, home: Path | None = None) -> None:
    """Point ``current`` at ``versions/<slot>`` atomically.

    ``slot`` is the version-dir name to make live -- normally ``<version>``, or a
    ``<version>+<build>`` repair slot (see ``slot_version``). A symlink cannot be
    retargeted in place, so write a temp link beside it and ``os.replace`` it over
    ``current``: replace is atomic on POSIX, so a concurrent reader sees either the old or
    the new target, never a missing link. This is the ONLY operation that makes a staged
    runtime live, which is why staging a fresh dir plus this flip needs no move-aside,
    backup, or restore. The target is stored RELATIVE (``versions/<slot>``) so the whole
    ``~/.decoy`` tree can be moved without breaking the link."""
    home = home or decoy_home()
    link = current_link(home)
    rel_target = os.path.join("versions", slot)
    tmp = home / f".current.{os.getpid()}.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(rel_target, tmp)
    os.replace(tmp, link)
