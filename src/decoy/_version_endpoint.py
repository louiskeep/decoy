"""Client for the Decoy-hosted CLI version document.

Distribution is self-hosted (the B-2 launch bundles), so the CLI reads the
current version from a Decoy endpoint, not the public PyPI JSON API. This module
owns that contract on the client side: fetch the document, parse it tolerantly,
compare versions with PEP 440, cache the result, and decide whether to show a
startup notice. It does no printing and imports no `typer`: the `decoy upgrade`
command and the root startup notice are the two callers that render (library code
does not know its callers).

Leak-safe by construction: the fetch is a plain GET of a version document and
nothing else. It sends no identifiers, no config, and no telemetry, consistent
with the CLI's raw-value isolation posture.

The document is an external contract (api-and-compatibility): it carries a
`schema_version`, and every field is optional with a defined default, so an older
CLI reading a newer document degrades cleanly rather than crashing.
"""

from __future__ import annotations

import json
import os
import platform
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packaging.version import InvalidVersion, Version

# The hosted version document. Static JSON behind a CDN is enough (the spec); the
# client never assumes anything dynamic about it.
DEFAULT_VERSION_URL = "https://decoy.dev/cli/version.json"

# Opt-outs (readiness report 4.3): the env var and the `--no-update-check` flag.
# A CI environment or a non-interactive session suppresses the notice too.
NO_UPDATE_CHECK_ENV = "DECOY_NO_UPDATE_CHECK"
UPDATE_URL_ENV = "DECOY_UPDATE_URL"

# A short network timeout keeps the notice non-blocking: a slow or dead endpoint
# costs at most this, once per cadence window, then fails silent.
DEFAULT_TIMEOUT_SECONDS = 1.5

# Check at most once per cadence window; the result is cached with a timestamp.
DEFAULT_CADENCE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class Artifact:
    """One target's published bundle in the version document."""

    url: str
    sha256: str
    sig: str


@dataclass(frozen=True)
class VersionDocument:
    """The parsed version document. Every field has a safe default so a missing
    or newer-shaped document never raises past `parse_document`."""

    latest: str | None = None
    min_supported: str | None = None
    yanked: tuple[str, ...] = ()
    message: str | None = None
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    schema_version: int = 1

    def artifact_for(self, target: str) -> Artifact | None:
        return self.artifacts.get(target)


@dataclass(frozen=True)
class UpdateDecision:
    """What the current CLI should conclude from a version document."""

    current: str
    latest: str | None
    update_available: bool
    current_is_yanked: bool
    below_min_supported: bool
    message: str | None
    notice_line: str | None


def parse_document(data: Any) -> VersionDocument:
    """Parse a decoded JSON object into a `VersionDocument`, tolerantly.

    A non-object, or any field of the wrong type, degrades to the default for
    that field rather than raising: an older CLI must survive a newer or
    malformed document (api-and-compatibility)."""
    if not isinstance(data, dict):
        return VersionDocument()
    latest = data.get("latest")
    min_supported = data.get("min_supported")
    message = data.get("message")
    yanked_raw = data.get("yanked")
    yanked = tuple(str(v) for v in yanked_raw) if isinstance(yanked_raw, list) else ()
    artifacts: dict[str, Artifact] = {}
    raw_artifacts = data.get("artifacts")
    if isinstance(raw_artifacts, dict):
        for key, value in raw_artifacts.items():
            if isinstance(value, dict) and {"url", "sha256", "sig"} <= set(value):
                artifacts[str(key)] = Artifact(
                    url=str(value["url"]),
                    sha256=str(value["sha256"]),
                    sig=str(value["sig"]),
                )
    schema_version = data.get("schema_version")
    return VersionDocument(
        latest=str(latest) if isinstance(latest, str) else None,
        min_supported=str(min_supported) if isinstance(min_supported, str) else None,
        yanked=yanked,
        message=str(message) if isinstance(message, str) else None,
        artifacts=artifacts,
        schema_version=schema_version if isinstance(schema_version, int) else 1,
    )


def fetch_document(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[[str, float], bytes] | None = None,
) -> VersionDocument | None:
    """Fetch and parse the version document, or return None on ANY error.

    Fail-silent is the contract: a network error, a timeout, a non-200, or
    malformed JSON all return None so the caller simply shows nothing. `opener`
    is injectable for tests; the default is a plain urllib GET with no custom
    headers (no identifiers)."""
    try:
        if opener is None:
            raw = _default_opener(url, timeout)
        else:
            raw = opener(url, timeout)
        return parse_document(json.loads(raw.decode("utf-8")))
    except Exception:
        # Any failure is non-fatal and silent by design (readiness report 4.3).
        return None


def _default_opener(url: str, timeout: float) -> bytes:
    # A bare GET of the fixed https version document. No headers are added, so
    # nothing identifies the caller.
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _compare(a: str, b: str) -> int | None:
    """PEP 440 compare: -1 if a<b, 0 if equal, 1 if a>b, None if either is not a
    valid version (so a malformed document version never crashes a comparison)."""
    try:
        va, vb = Version(a), Version(b)
    except InvalidVersion:
        return None
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0


def detect_target() -> str | None:
    """Map the host to a bundle target key, or None if unsupported.

    Mirrors the installer's detection (packaging/install/install.sh) so the
    client and the installer agree on what this host is. Kept here, small, so the
    CLI does not import the `packaging/` build tree at runtime."""
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "linux-x86_64"
        if machine in ("aarch64", "arm64"):
            return "linux-aarch64"
    elif system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "macos-arm64"
    elif system == "Windows":
        if machine in ("amd64", "x86_64"):
            return "windows-x86_64"
    return None


def compute_update_decision(current: str, document: VersionDocument | None) -> UpdateDecision:
    """Decide what the current CLI should conclude. Pure; renders nothing."""
    if document is None or document.latest is None:
        return UpdateDecision(
            current=current,
            latest=None,
            update_available=False,
            current_is_yanked=False,
            below_min_supported=False,
            message=None,
            notice_line=None,
        )
    latest = document.latest
    cmp_latest = _compare(current, latest)
    update_available = cmp_latest == -1
    current_is_yanked = current in document.yanked
    below_min = (
        document.min_supported is not None and _compare(current, document.min_supported) == -1
    )
    notice_line = None
    if update_available:
        notice_line = (
            f"decoy {latest} is available (you have {current}). "
            "Upgrade with `decoy upgrade`."
        )
    return UpdateDecision(
        current=current,
        latest=latest,
        update_available=update_available,
        current_is_yanked=current_is_yanked,
        below_min_supported=below_min,
        message=document.message,
        notice_line=notice_line,
    )


# --- startup notice, fully gated and cached ---------------------------------


def _cache_path(home: Path | None = None) -> Path:
    base = home or Path(os.environ.get("DECOY_INSTALL_HOME", "")) or (Path.home() / ".decoy")
    return base / "update-check.json"


def read_cache(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache(path: Path, checked_at: float, document: VersionDocument | None) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "checked_at": checked_at,
            "latest": None if document is None else document.latest,
        }
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    except Exception:
        # A cache we cannot write is not an error: the next run just rechecks.
        pass


def _notice_suppressed(*, argv: list[str], env: dict[str, str], isatty: bool) -> bool:
    """The gates from readiness report 4.3. Any one suppresses the notice."""
    if not isatty:
        return True  # no TTY / piped output
    if env.get(NO_UPDATE_CHECK_ENV, "") not in ("", "0", "false", "False"):
        return True  # explicit opt-out env var
    if "--no-update-check" in argv:
        return True  # explicit opt-out flag
    if "--json" in argv or "-q" in argv or "--quiet" in argv:
        return True  # machine-readable or quiet output must stay clean
    # Common CI markers. CI must never emit the notice.
    if env.get("CI", "") not in ("", "0", "false", "False"):
        return True
    return False


def maybe_update_notice(
    *,
    current: str,
    argv: list[str],
    env: dict[str, str],
    isatty: bool,
    cache_home: Path | None = None,
    url: str | None = None,
    now: float | None = None,
    cadence_seconds: int = DEFAULT_CADENCE_SECONDS,
    fetcher: Callable[[str], VersionDocument | None] | None = None,
) -> str | None:
    """Return a one-line update notice, or None if suppressed or nothing is new.

    Cache-first and non-blocking: it reads the cached result, and only reaches
    the network when the cache is stale, with a short timeout, failing silent.
    All inputs are injectable so the gating and cadence are testable without a
    TTY, a network, or a clock."""
    if _notice_suppressed(argv=argv, env=env, isatty=isatty):
        return None
    now = time.time() if now is None else now
    cache_file = _cache_path(cache_home)
    cached = read_cache(cache_file)
    latest: str | None = None
    if cached and isinstance(cached.get("checked_at"), (int, float)):
        if now - cached["checked_at"] < cadence_seconds:
            latest = cached.get("latest")
        else:
            latest = _refresh(cache_file, env, url, now, fetcher)
    else:
        latest = _refresh(cache_file, env, url, now, fetcher)
    if not latest:
        return None
    decision = compute_update_decision(current, VersionDocument(latest=latest))
    return decision.notice_line


def _refresh(
    cache_file: Path,
    env: dict[str, str],
    url: str | None,
    now: float,
    fetcher: Callable[[str], VersionDocument | None] | None,
) -> str | None:
    resolved_url = url or env.get(UPDATE_URL_ENV) or DEFAULT_VERSION_URL
    if fetcher is not None:
        document = fetcher(resolved_url)
    else:
        document = fetch_document(resolved_url)
    write_cache(cache_file, now, document)
    return None if document is None else document.latest
