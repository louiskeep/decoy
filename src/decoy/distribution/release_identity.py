"""The one release-identity fact: which repos, site and download host a release names.

Every other module imports these values instead of spelling them. The shell installers run
before Python exists, so `install.sh` and `install.ps1` carry checked copies; the sentry in
`tests/sentry/release/test_release_identity_sentry.py` keeps them equal to this file.

Comparisons against these values are exact equality. Prefix, suffix, case-fold and `$`
anchored matches are not used, so a fork, a renamed repo or a value with a trailing newline
is refused.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

CLI_REPO = "decoy-data/decoy"
ENGINE_REPO = "decoy-data/decoy-engine"
WEB_REPO = "decoy-data/decoy-web"
SITE_ORIGIN = "https://trydecoy.com"

# Layout of every artifact URL: <ARTIFACT_BASE>/v<version>/<name>.
ARTIFACT_BASE = "https://github.com/decoy-data/decoy/releases/download"
# A GitHub origin for artifacts is refused unless this names a dated owner decision.
ARTIFACT_HOST_EXCEPTION: str | None = (
    "owner 2026-11-18: V1 bundles are GitHub Release assets of decoy-data/decoy, "
    "a dated exception to the 2026-11-12 static site plus CDN decision"
)

# The author and committer of a decoy-web commit, as `git log` prints them: %an %ae %cn %ce.
WEB_COMMIT_IDENTITY = ("ckeep", "decoy@trydecoy.com", "ckeep", "decoy@trydecoy.com")

_GITHUB_APEXES = ("github.com", "githubusercontent.com", "github.io")
# The one registry of GitHub-hosted artifact bases: exact base -> the exact dated owner decision
# that allows it. A GitHub-hosted base absent from here, or paired with any other text, is refused.
APPROVED_GITHUB_BASES: dict[str, str | None] = {ARTIFACT_BASE: ARTIFACT_HOST_EXCEPTION}
# `owner YYYY-MM-DD <text>`, with an optional colon after the date. The one grammar for a dated
# owner decision for ratchet `approved_growth` (the sentry ratchet loads `is_dated_owner_decision`
# from this file). Artifact bases do not use it: they match the exact registered pair above.
_DECISION = re.compile(r"owner (\d{4}-\d{2}-\d{2}):? (.{10,})")


class ReleaseIdentityError(ValueError):
    """A release fact broke the identity rule. The message is a fixed code."""


def artifact_url(version: str, name: str, base: str = ARTIFACT_BASE) -> str:
    """The one place an artifact URL is built: `<base>/v<version>/<name>`."""
    return f"{base.rstrip('/')}/v{version}/{name}"


def _is_github_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == apex or host.endswith("." + apex) for apex in _GITHUB_APEXES)


def is_dated_owner_decision(text: object) -> bool:
    """True for `owner YYYY-MM-DD[:] <text>` with a real calendar date and at least 10 text chars."""
    if not isinstance(text, str):
        return False
    match = _DECISION.fullmatch(text)
    if match is None:
        return False
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return False
    return True


def check_artifact_origin(base: str, exception: str | None) -> None:
    """Refuse a base that is not plain https, carries credentials, or is GitHub-hosted without
    being a registered (base, decision) pair."""
    try:
        parts = urlsplit(base)
        host, user, password, _port = parts.hostname, parts.username, parts.password, parts.port
    except ValueError as exc:
        raise ReleaseIdentityError("release_identity_mismatch") from exc
    if parts.scheme != "https" or not host or user is not None or password is not None:
        raise ReleaseIdentityError("release_identity_mismatch")
    if _is_github_host(host) and not (
        exception is not None and APPROVED_GITHUB_BASES.get(base) == exception
    ):
        raise ReleaseIdentityError("release_identity_mismatch")


def validate() -> None:
    """Check the shipped values. Signing commands call this before they load a key."""
    check_artifact_origin(ARTIFACT_BASE, ARTIFACT_HOST_EXCEPTION)
