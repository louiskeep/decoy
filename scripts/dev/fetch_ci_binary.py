#!/usr/bin/env python3
"""Download a pinned release binary and check its sha256 before it can run.

Usage: fetch_ci_binary.py NAME --dest DIR [--policy FILE]
NAME is a [[binary_tool]] entry in ci/install-policy.toml, which holds the url, version and sha256
and is the only place they are written. A digest mismatch deletes nothing and installs nothing:
the script exits 1 and the CI job fails. The url may be https or, for tests, file.

A timeout, a dropped connection or an HTTP 5xx is retried (ATTEMPTS tries in all, with a short
backoff) because the release host times out now and then and one miss used to fail the whole job.
A digest mismatch or an HTTP 4xx is never retried.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import socket
import sys
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "ci" / "install-policy.toml"
ATTEMPTS = 3
BACKOFF_SECONDS = (5.0, 15.0)


def _transient(err: Exception) -> bool:
    """A failure a second try can fix: a 5xx, a timeout, a dropped connection, a temporary DNS miss,
    or a body cut off mid-read. A 4xx, a certificate failure or a bad url fails at once."""
    if isinstance(err, urllib.error.HTTPError):
        return err.code >= 500
    if isinstance(err, urllib.error.URLError):
        reason = err.reason
        return isinstance(reason, (TimeoutError, ConnectionError)) or (
            isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN
        )
    return isinstance(err, (TimeoutError, ConnectionError, http.client.IncompleteRead))


def download(url: str, *, sleep: Callable[[float], None] | None = None) -> bytes:
    """Read `url`, retrying a transient network failure; the last failure is raised."""
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except (OSError, http.client.HTTPException) as err:
            if attempt == ATTEMPTS - 1 or not _transient(err):
                raise
            print(f"fetch_ci_binary: {type(err).__name__}, retrying", file=sys.stderr)
            (sleep or time.sleep)(BACKOFF_SECONDS[attempt])
    raise AssertionError("unreachable")


def fetch(entry: dict[str, str], dest: Path) -> Path:
    """Verify the archive digest, then extract only the one named member into `dest`."""
    blob = download(entry["url"])
    digest = hashlib.sha256(blob).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"sha256 mismatch for {entry['name']}: got {digest}")
    member = entry.get("member", entry["name"])
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        info = next((m for m in tar.getmembers() if m.isfile() and m.name == member), None)
        if info is None or (stream := tar.extractfile(info)) is None:
            raise ValueError(f"{member} is not a file in the {entry['name']} archive")
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / Path(member).name
        target.write_bytes(stream.read())
    target.chmod(0o755)
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(argv)
    tools = tomllib.loads(args.policy.read_text(encoding="utf-8")).get("binary_tool", [])
    entry = next((t for t in tools if t["name"] == args.name), None)
    if entry is None:
        print(f"fetch_ci_binary: {args.name} is not a registered binary_tool", file=sys.stderr)
        return 2
    try:
        print(fetch(entry, args.dest))
    except (ValueError, OSError, http.client.HTTPException) as err:
        print(f"fetch_ci_binary: {type(err).__name__}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
