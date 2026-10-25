#!/usr/bin/env python3
"""A local stub for the Decoy version endpoint + download host.

For LOCAL TESTING ONLY. It serves a channel directory over HTTP so the installer
and the CLI update client can be exercised end to end without standing up real
infrastructure: the real version endpoint is static JSON behind a CDN plus a
download host, and this serves exactly that shape from a local directory.

Expected channel layout (what the build pipeline produces and signs):

    <root>/version.json                         the version document
    <root>/install.sh                           a copy of packaging/install/install.sh
    <root>/<version>/decoy-<version>-<target>.tar.gz
    <root>/<version>/SHA256SUMS
    <root>/<version>/SHA256SUMS.sig

Usage:
    python packaging/version/serve_stub.py <root> [--port 8000]

Then, against it:
    DECOY_INSTALL_BASE_URL=http://127.0.0.1:8000 packaging/install/install.sh
    DECOY_UPDATE_URL=http://127.0.0.1:8000/version.json decoy upgrade --check
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Local stub for the Decoy version/download host.")
    parser.add_argument("root", type=Path, help="Channel directory to serve.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()

    if not args.root.is_dir():
        parser.error(f"channel root not found: {args.root}")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.root))
    with socketserver.TCPServer((args.bind, args.port), handler) as httpd:
        print(f"serving {args.root} at http://{args.bind}:{args.port} (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
