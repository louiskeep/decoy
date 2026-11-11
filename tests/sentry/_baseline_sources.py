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

import ast
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


def _literal_constant(path: Path, constant: str) -> Any:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == constant and node.value is not None:
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in {"frozenset", "set", "tuple", "list"}
                and len(value.args) == 1
            ):
                value = value.args[0]
            return ast.literal_eval(value)
    raise ValueError(f"{path.name}: no literal {constant}")


@dataclass(frozen=True)
class InCode:
    """Keys of a module-level collection in a sentry file (path relative to the repo root).

    ``literal`` reads the constant from the source with ``ast.literal_eval`` (unwrapping one
    ``frozenset``/``set``/``tuple``/``list`` call) instead of importing a module whose import
    has side effects, such as building the live Typer app.
    """

    test_file: str
    constant: str
    key: Callable[[Any], str] = _flat
    reason: Callable[[Any], str] | None = None
    literal: bool = False

    @property
    def name(self) -> str:
        return Path(self.test_file).name

    def items(self) -> tuple[Any, ...]:
        if self.literal:
            return tuple(_literal_constant(ROOT / self.test_file, self.constant))
        return tuple(getattr(load_module(ROOT / self.test_file), self.constant))

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
    data_file: str = ""  # a committed data file the sentry reads besides its baseline


_SURFACE = "tests/unit/test_surface_docs_consistency.py"
_ROOT_HELP_WHY = (
    "top-level command deliberately kept out of the curated root help quick-start; "
    "the full surface is in decoy --help"
)
_README_WHY = (
    "real command the README Common commands table deliberately does not repeat; "
    "the table points readers to decoy --help"
)
SOURCES: tuple[Source, ...] = (
    Source(
        "engine-internal-allow",
        "tests/sentry/test_engine_internal_boundary.py",
        InCode(
            "tests/sentry/test_engine_internal_boundary.py",
            "ALLOWLIST",
            key=lambda e: f"{e.file}::{e.symbol}",
            reason=lambda e: e.reason,
        ),
    ),
    Source(
        "atomic-writer-allow",
        "tests/sentry/test_atomic_writer.py",
        InCode(
            "tests/sentry/test_atomic_writer.py",
            "ALLOWLIST",
            key=lambda e: e.file,
            reason=lambda e: e.reason,
        ),
    ),
    Source(
        "csv-read-allow",
        "tests/sentry/test_csv_read_choke_point.py",
        InCode(
            "tests/sentry/test_csv_read_choke_point.py",
            "ALLOWLIST",
            key=lambda e: f"{e.file}::{e.function}",
            reason=lambda e: e.reason,
        ),
    ),
    Source(
        "target-writes-allow",
        "tests/sentry/io_policy/test_target_writes.py",
        InCode(
            "tests/sentry/io_policy/test_target_writes.py",
            "ALLOWLIST",
            key=lambda e: f"{e.file}::{e.function}",
            reason=lambda e: e.reason,
        ),
    ),
    Source(
        "private-file-sinks",
        "tests/sentry/io_policy/test_private_files.py",
        InCode(
            "tests/sentry/io_policy/test_private_files.py",
            "BASELINE_ROWS",
            key=lambda e: e[0],
            reason=lambda e: e[1],
        ),
        data_file="tests/sentry/io_policy/file_sinks.toml",
    ),
    Source(
        "gate-single-entry-allow",
        "tests/sentry/test_gate_single_entry.py",
        InCode(
            "tests/sentry/test_gate_single_entry.py",
            "ALLOWLIST",
            key=lambda e: f"{e.module}::{e.function}::{e.rule}",
            reason=lambda e: e.reason,
        ),
    ),
    Source(
        "config-route-allow",
        "tests/sentry/defects/test_config_error_routes.py",
        InCode(
            "tests/sentry/defects/test_config_error_routes.py",
            "ALLOWLIST",
            key=lambda e: e[0],
            reason=lambda e: e[1],
        ),
    ),
    Source(
        "root-help-omitted",
        _SURFACE,
        InCode(_SURFACE, "_ROOT_HELP_OMITTED", reason=lambda e: _ROOT_HELP_WHY, literal=True),
    ),
    Source(
        "readme-table-omitted",
        _SURFACE,
        InCode(_SURFACE, "_README_TABLE_OMITTED", reason=lambda e: _README_WHY, literal=True),
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
    """First inventory of each source that has no baseline yet. Never rewrites one that exists:
    after its first inventory a baseline only shrinks, by hand."""
    BASELINES.mkdir(exist_ok=True)
    rows = []
    for src in SOURCES:
        path = baseline_path(src.sentry_id)
        if path.exists():
            continue
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
    if not rows:
        raise SystemExit("every source already has a baseline; nothing to write")
    REGISTRY.write_text(
        REGISTRY.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + "\n".join(rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-initial"]:
        write_initial()
    else:
        raise SystemExit("usage: _baseline_sources.py --write-initial")
