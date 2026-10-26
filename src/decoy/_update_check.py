"""Startup "new version available" notice for the self-hosted update channel.

The pip-world analogue described in the readiness report (section 4.3): on an
interactive start, check the Decoy-hosted version document at most once per cadence
window, cache the result, and print ONE non-blocking line when a newer version exists,
with the exact upgrade command. It never blocks or slows a run and fails silent on any
error.

Hard rules honored here:
  - Interactive only: suppressed when stderr/stdout is not a TTY, under CI, and when
    output is piped or ``--json`` (the caller passes ``suppress=True`` then).
  - Opt-out: ``--no-update-check``, ``DECOY_NO_UPDATE_CHECK``, or a config setting all
    disable it.
  - Leak-safe: the check fetches only the signed version document. It sends NO data, no
    identifiers, no telemetry -- consistent with the CLI's raw-value isolation posture.
  - Fail-silent: any network/parse/cache error is swallowed; the notice is advisory.

The notice does NOT trust the document for anything but display: it is advisory text,
not an action. The signed verification that gates an actual swap lives in
`decoy.distribution.installer` / `install.sh`.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from decoy import __version__
from decoy.distribution import layout
from decoy.distribution import version_document as vd

_DEFAULT_VERSION_URL = "https://decoy.dev/cli/version.json"
_CADENCE_SECONDS = 24 * 60 * 60  # at most one network check per day
_FETCH_TIMEOUT = 1.5  # never make startup wait long
_CACHE_NAME = "update-check.json"


def _opted_out() -> bool:
    val = os.environ.get("DECOY_NO_UPDATE_CHECK")
    return bool(val) and val != "0"


def _interactive() -> bool:
    # CI and non-TTY are not interactive. stdout-not-a-TTY covers piped/`--json` output.
    if os.environ.get("CI"):
        return False
    try:
        return sys.stderr.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _cache_path() -> Path:
    return layout.cache_dir() / _CACHE_NAME


def _read_cache() -> dict | None:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(latest: str | None) -> None:
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"checked_at": int(time.time()), "latest": latest}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _fetch_latest(url: str) -> str | None:
    """Fetch the version document and return its ``latest``. No signature check here --
    this is advisory display only; a tampered 'newer version' line at worst prints a
    wrong number, and the actual upgrade re-verifies against the pinned key. Returns None
    on any failure."""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={})  # no identifying headers
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            data = resp.read()
        payload = vd.parse_document(data)
        latest = payload.get("latest")
        return latest if isinstance(latest, str) else None
    except Exception:
        return None


def check_latest(*, url: str | None = None, now: int | None = None) -> str | None:
    """Return the latest version, from cache within the cadence window or a fresh fetch.
    Updates the cache on a fetch. Returns None if unknown."""
    url = url or os.environ.get("DECOY_VERSION_URL", _DEFAULT_VERSION_URL)
    now = now if now is not None else int(time.time())
    cache = _read_cache()
    if cache and isinstance(cache.get("checked_at"), int):
        if now - cache["checked_at"] < _CADENCE_SECONDS:
            latest = cache.get("latest")
            return latest if isinstance(latest, str) else None
    latest = _fetch_latest(url)
    _write_cache(latest)
    return latest


def maybe_print_notice(*, suppress: bool = False, stream=None) -> bool:
    """Print the one-line notice to stderr if a newer version is available. Returns True
    iff a notice was printed. Never raises."""
    try:
        if suppress or _opted_out() or not _interactive():
            return False
        latest = check_latest()
        if not latest:
            return False
        try:
            if vd.compare_versions(__version__, latest) >= 0:
                return False
        except ValueError:
            return False
        out = stream or sys.stderr
        out.write(
            f"decoy: a newer version is available ({__version__} -> {latest}). "
            "Upgrade with: decoy upgrade\n"
        )
        return True
    except Exception:
        return False
