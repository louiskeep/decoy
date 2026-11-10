"""Max memory and threads for `decoy run`: one resolver, one settings file.

Order per key, first hit wins: flag, environment variable, `$DECOY_HOME/settings.json`, `auto`.
`auto` threads is the engine's cgroup-aware `detect_usable_cpus()`. `auto` memory is the engine's
`resolve_conservative_ooc_budget_bytes()` (25% of the memory ceiling, so two automatic runs share
a host). The CLI passes the resulting bytes explicitly and never owns the floor or the 25%
arithmetic: the engine's budget resolver refuses a value below its floor.

Every value comes from an untrusted producer (flag, env, file). Sizes and counts are matched in
full with `re.fullmatch`, stored primitives are checked by exact type (a JSON boolean is not an
integer), and an error names the key and a fixed reason, never the offending text. Errors are
raised outside any `except` block so they carry neither `__cause__` nor `__context__`.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from decoy._atomic import WriteMode, write_atomic
from decoy.distribution.layout import decoy_home

SCHEMA_VERSION = "1.0"
SETTINGS_NAME = "settings.json"
ENV_MEMORY = "DECOY_MAX_MEMORY"
ENV_THREADS = "DECOY_THREADS"
AUTO = "auto"

_MAX_FILE_BYTES = 64 * 1024
_MAX_BYTES = 2**62
_MAX_THREADS = 65535
_UNITS = {
    "B": 1,
    "KB": 10**3,
    "MB": 10**6,
    "GB": 10**9,
    "TB": 10**12,
    "KiB": 2**10,
    "MiB": 2**20,
    "GiB": 2**30,
    "TiB": 2**40,
}
_SIZE = re.compile(r"([1-9][0-9]{0,15})(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)?")
_COUNT = re.compile(r"[1-9][0-9]{0,4}")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")

_TEXT = {
    "size": 'must be a size such as 8GiB, 512MiB or 4000000000, or "auto"',
    "count": 'must be a whole number from 1 to 65535, or "auto"',
    "version": 'schema_version must be a string like "1.0" with major version 1',
    "table": "resources must be a table",
    "unreadable": "cannot be read",
    "invalid": "is not a valid settings object",
    "busy": "is being updated by another decoy process; re-run in a moment",
    "detect": "could not detect this host's value; set it explicitly",
}

MAX_MEMORY_OPTION: Any = typer.Option(
    None,
    "--max-memory",
    metavar="SIZE",
    help=(
        "Memory budget for the out-of-core route, such as 8GiB, or auto. Overrides "
        f"{ENV_MEMORY} and settings.json. Default auto: 25% of the memory ceiling. "
        "Ignored by --chunked."
    ),
)
THREADS_OPTION: Any = typer.Option(
    None,
    "--threads",
    metavar="N",
    help=(
        "Worker threads for the native and out-of-core routes, or auto. Overrides "
        f"{ENV_THREADS} and settings.json. Default auto: the usable CPUs. Ignored by --chunked."
    ),
)


class ResourceError(Exception):
    """A resource setting is unusable. The text is the key and a fixed reason."""

    def __init__(self, where: str, code: str) -> None:
        super().__init__(f"{where} {_TEXT[code]}")
        self.code = code


@dataclass(frozen=True)
class Resolved:
    memory_bytes: int
    threads: int
    memory_source: str
    threads_source: str

    def record(self) -> dict[str, Any]:
        return {
            "max_memory_bytes": self.memory_bytes,
            "max_memory_source": self.memory_source,
            "threads": self.threads,
            "threads_source": self.threads_source,
        }


def run_pipeline_kwargs(resolved: Resolved) -> dict[str, int]:
    """The `run_pipeline` keywords for a resolved record (an explicit byte budget, even for auto)."""
    return {
        "native_threads": resolved.threads,
        "out_of_core_threads": resolved.threads,
        "out_of_core_budget_bytes": resolved.memory_bytes,
    }


def parse_size(text: object) -> int | None:
    """Bytes for `8GiB` style text, or None. A bare number is bytes."""
    if not isinstance(text, str):
        return None
    match = _SIZE.fullmatch(text)
    if match is None:
        return None
    total = int(match[1]) * _UNITS[match[2] or "B"]
    return total if total <= _MAX_BYTES else None


def format_size(n: int) -> str:
    for unit in ("TiB", "GiB", "MiB", "KiB"):
        if n % _UNITS[unit] == 0:
            return f"{n // _UNITS[unit]}{unit}"
    return f"{n}B"


def parse_memory(text: object) -> int | str | None:
    return AUTO if text == AUTO else parse_size(text)


def _bounded(n: int) -> int | None:
    return n if 1 <= n <= _MAX_THREADS else None


def parse_threads(text: object) -> int | str | None:
    """A thread count from flag or env text (digits), or `auto`."""
    if text == AUTO:
        return AUTO
    if isinstance(text, str) and _COUNT.fullmatch(text):
        return _bounded(int(text))
    return None


def _stored_threads(value: object) -> int | str | None:
    # A JSON boolean is an int subclass in Python and a quoted "6" is text: neither is a count.
    if type(value) is int:
        return _bounded(value)
    return AUTO if value == AUTO else None


def settings_path() -> Path:
    return decoy_home() / SETTINGS_NAME


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = dict(pairs)
    if len(out) != len(pairs):
        raise ValueError("duplicate key")
    return out


def _refuse_constant(_name: str) -> Any:
    raise ValueError("NaN and Infinity are not allowed")


def load_document(path: Path | None = None) -> dict[str, Any] | None:
    """The settings document, or None when the file does not exist.

    Checks the structure only (an object, `schema_version` major 1, `resources` an object). Values
    are checked per key by `read_settings`, so one bad stored value never blocks another key.
    """
    path = path or settings_path()
    where = SETTINGS_NAME
    raw: bytes | None = None
    failure = None
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError:
        failure = "unreadable"
    data: Any = None
    if failure is None:
        assert raw is not None
        try:
            if len(raw) > _MAX_FILE_BYTES:
                failure = "invalid"
            else:
                data = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_no_duplicates,
                    parse_constant=_refuse_constant,
                )
        except (UnicodeDecodeError, ValueError, RecursionError):
            failure = "invalid"
        if failure is None and not isinstance(data, dict):
            failure = "invalid"
    if failure is None:
        version = data.get("schema_version")
        match = _VERSION.fullmatch(version) if isinstance(version, str) else None
        if match is None or match[1] != "1":
            failure, where = "version", f"{SETTINGS_NAME} schema_version"
        elif not isinstance(data.get("resources", {}), dict):
            failure = "table"
    if failure is not None:
        raise ResourceError(where, failure)
    return data


_STORED = {
    "max_memory": (parse_memory, "size"),
    "threads": (_stored_threads, "count"),
}


def read_settings(
    path: Path | None = None, keys: tuple[str, ...] = tuple(_STORED)
) -> dict[str, int | str]:
    """The stored `resources` values for `keys` that are present (`max_memory` bytes or auto).

    A missing file is empty. Only the requested keys are validated. Unknown keys and unknown
    minor versions are accepted.
    """
    data = load_document(path)
    table = (data or {}).get("resources", {})
    out: dict[str, int | str] = {}
    for key in keys:
        if key not in table:
            continue
        parse, code = _STORED[key]
        value = parse(table[key])
        if value is None:
            raise ResourceError(f"{SETTINGS_NAME} resources.{key}", code)
        out[key] = value
    return out


def _auto_memory() -> int:
    ok = True
    try:
        from decoy_engine import resolve_conservative_ooc_budget_bytes

        value = int(resolve_conservative_ooc_budget_bytes())
    except Exception:
        ok = False
    if not ok or value < 1:
        raise ResourceError("max_memory", "detect")
    return value


def _auto_threads() -> int:
    ok = True
    try:
        from decoy_engine import detect_usable_cpus

        value = int(detect_usable_cpus())
    except Exception:
        ok = False
    if not ok or value < 1:
        raise ResourceError("threads", "detect")
    return value


def detect() -> tuple[int, int]:
    """The auto memory budget in bytes and the usable CPU count for this host."""
    return _auto_memory(), _auto_threads()


def resolve(
    *,
    max_memory: str | None = None,
    threads: str | None = None,
    env: Mapping[str, str] | None = None,
    settings: Path | None = None,
) -> Resolved:
    env = os.environ if env is None else env
    picks: dict[str, tuple[int | str, str]] = {}
    for key, flag, flag_name, var, parse, code in (
        ("max_memory", max_memory, "--max-memory", ENV_MEMORY, parse_memory, "size"),
        ("threads", threads, "--threads", ENV_THREADS, parse_threads, "count"),
    ):
        for source, where, text in (("flag", flag_name, flag), ("env", var, env.get(var) or None)):
            if text is None:
                continue
            value = parse(text)
            if value is None:
                raise ResourceError(where, code)
            picks[key] = (value, source)
            break
    # Only a key that falls through to the file may fail on its stored value.
    wanted = tuple(k for k in _STORED if k not in picks)
    stored = read_settings(settings, wanted) if wanted else {}
    for key in wanted:
        picks[key] = (stored[key], "settings") if key in stored else (AUTO, AUTO)
    memory, memory_source = picks["max_memory"]
    count, threads_source = picks["threads"]
    return Resolved(
        memory_bytes=_auto_memory() if memory == AUTO else int(memory),
        threads=_auto_threads() if count == AUTO else int(count),
        memory_source=memory_source,
        threads_source=threads_source,
    )


def write_settings(text: str) -> Path:
    """Write the settings file atomically (the one writer in `_atomic`)."""
    home = decoy_home()
    home.mkdir(parents=True, exist_ok=True)
    write_atomic(home, SETTINGS_NAME, text.encode("utf-8"), WriteMode.REPLACE)
    return home / SETTINGS_NAME
