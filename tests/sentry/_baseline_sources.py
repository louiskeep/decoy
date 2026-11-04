"""Where each CLI sentry's committed allowlist lives, as a set of keys.

``SOURCES`` is the single table the registry test and the one-off ``--write-initial``
generator share. Entries here are the X0a initial inventory; after that the ratchet
(``scripts/dev/ratchet_check.py``) lets a baseline only shrink.

Ported from decoy-engine ``tests/sentry/_baseline_sources.py`` (X0a). The CLI allowlist is a
tuple of ``AllowedInternal`` dataclass instances, so ``InCode`` takes a key function instead of
stringifying a whole entry (which would put reason and removal text in the key).

Named limit: the ratchet sees ``file::symbol`` keys only. Raising an existing entry's ``count``
is not a new key; the boundary sentry's exact-count check and review hold it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SENTRY = ROOT / "tests" / "sentry"
BASELINES = SENTRY / "baselines"
REGISTRY = ROOT / "scripts" / "dev" / "sentry_registry.toml"
CREATED_IN = "X0a"
MIN_REASON = 15


def _flat(item: Any) -> str:
    return "::".join(map(str, item)) if isinstance(item, (tuple, list)) else str(item)


def load_module(path: Path) -> Any:
    name = f"_bl_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


@dataclass(frozen=True)
class InCode:
    """Keys of a module-level collection in a ``tests/sentry`` file."""

    test_file: str
    constant: str
    key: Callable[[Any], str] = _flat
    reason: Callable[[Any], str] | None = None

    def items(self) -> tuple[Any, ...]:
        return tuple(getattr(load_module(SENTRY / self.test_file), self.constant))

    def __call__(self) -> set[str]:
        return {self.key(e) for e in self.items()}

    def reasons(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for e in self.items():
            k = self.key(e)
            if k in out:
                raise ValueError(f"{self.constant}: duplicate key {k}")
            out[k] = self.reason(e) if self.reason else ""
        return out


@dataclass(frozen=True)
class Source:
    sentry_id: str
    where: str  # file the sentry reads
    keys: InCode


SOURCES: tuple[Source, ...] = (
    Source(
        "engine-internal-allow",
        "test_engine_internal_boundary.py",
        InCode(
            "test_engine_internal_boundary.py",
            "ALLOWLIST",
            key=lambda e: f"{e.file}::{e.symbol}",
            reason=lambda e: e.reason,
        ),
    ),
)

# Allowlist-shaped constants a sentry holds that are a closed contract, not a bypass list.
NOT_A_LIST_CONSTS: dict[tuple[str, str], str] = {
    ("test_notify_redaction.py", "_ALLOWED_EVENT_FIELDS"): (
        "closed notification fact set, pinned by test_notify_redaction lane 1"
    ),
    ("test_engine_import_surface.py", "_GUARD_EXCEPTIONS"): (
        "exception names the import guard recognises, not a bypass list"
    ),
}


def baseline_path(sentry_id: str) -> Path:
    return BASELINES / f"{sentry_id}.json"


def write_initial() -> None:
    """One-off: write each baseline from its live source. Refuses to overwrite (no add mode)."""
    BASELINES.mkdir(exist_ok=True)
    rows = []
    for src in SOURCES:
        path = baseline_path(src.sentry_id)
        if path.exists():
            raise SystemExit(f"{path} exists; baselines only shrink after the first inventory")
        reasons = src.keys.reasons()
        short = sorted(k for k, r in reasons.items() if len(r.strip()) < MIN_REASON)
        if short:
            raise SystemExit(f"{src.sentry_id}: reason under {MIN_REASON} chars for {short}")
        entries = {k: {"reason": reasons[k].strip()} for k in sorted(reasons)}
        doc = {"sentry_id": src.sentry_id, "created_in": CREATED_IN, "entries": entries}
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        rows.append(
            f'[[sentry]]\nid = "{src.sentry_id}"\nbaseline = "tests/sentry/baselines/{path.name}"\n'
        )
    REGISTRY.write_text(
        REGISTRY.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + "\n".join(rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-initial"]:
        write_initial()
    else:
        raise SystemExit("usage: _baseline_sources.py --write-initial")
