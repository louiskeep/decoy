"""Live-channel proof for `decoy run --notify` (Slice 3, N3 "proven to send").

This is the CI-safe half of the sprint's live-channel proof: it stands up
a REAL local HTTP server (stdlib `http.server`, no mocking) on
127.0.0.1, runs `decoy run <pipeline.yaml> --notify webhook:... --notify-on
always` as a real subprocess (the actual `python -m decoy` entry point,
not the in-process Typer test harness), and asserts the server received
one real POST over a real socket whose body matches the event shape and
whose `X-Decoy-Signature` HMAC verifies against a real
`DECOY_NOTIFY_WEBHOOK_SECRET`.

This closes the ledger gap the sprint guide names: prior --notify tests
(tests/e2e/test_run_notify.py, tests/unit/test_notify.py) mock
`decoy.notify.send_webhook`/`urllib.request.urlopen`; this test proves the
transport itself, not just the builder. "Proven to send" for --notify is
THIS test, not the mocked ones.

The manual runbook for a real Slack incoming-webhook + a real SMTP relay
(the part that cannot run headlessly in CI) lives at
docs/release/notify-live-channel-log.md, mirroring the pattern in
docs/release/smoke-log.md (an append-only log of recorded executions).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_WEBHOOK_SECRET = "sprint5-live-webhook-proof-secret"


class _CapturingHandler(BaseHTTPRequestHandler):
    """Records the first POST it receives; responds 200 to every request."""

    received: list[dict] = []  # class-level: shared across the single test server instance

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        _CapturingHandler.received.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": body,
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):
        pass


def _start_echo_server() -> tuple[HTTPServer, threading.Thread, int]:
    server = HTTPServer(("127.0.0.1", 0), _CapturingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def _write_tiny_pipeline(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"customer_id": ["1", "2", "3"], "name": ["a", "b", "c"]}).to_csv(
        src, index=False
    )
    cfg = {
        "version": 1,
        "global_settings": {"seed": 7},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "customer_id",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "customer_identity",
                    }
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def test_notify_webhook_live_round_trip_over_a_real_socket(tmp_path: Path):
    """A real `decoy run --notify webhook:...` subprocess delivers a real,
    HMAC-signed HTTP POST to a real local socket. This is the sprint's
    Slice 3 "proven to send" proof for --notify."""
    _CapturingHandler.received = []
    server, thread, port = _start_echo_server()
    try:
        pipeline = _write_tiny_pipeline(tmp_path)
        env = dict(os.environ)
        env["DECOY_NOTIFY_WEBHOOK_SECRET"] = _WEBHOOK_SECRET
        env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "decoy",
                "run",
                str(pipeline),
                "--notify",
                f"webhook:http://127.0.0.1:{port}/hook",
                "--notify-on",
                "always",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT,
            env=env,
        )
        assert proc.returncode == 0, (
            f"decoy run --notify subprocess failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
        envelope = json.loads(proc.stdout)
        assert envelope["status"] == "ok"
        assert envelope["notify"] == [
            {"kind": "webhook", "delivered": True, "target_host": f"127.0.0.1:{port}"}
        ]
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert len(_CapturingHandler.received) == 1, (
        "the local echo server must have received exactly one real POST over a real socket"
    )
    request = _CapturingHandler.received[0]
    assert request["path"] == "/hook"

    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert "x-decoy-signature" in headers
    assert "x-decoy-delivery-id" in headers
    assert headers.get("x-decoy-event-kind") == "run_completed"

    expected_sig = hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"), request["body"], hashlib.sha256
    ).hexdigest()
    assert headers["x-decoy-signature"] == f"sha256={expected_sig}", (
        "the webhook signature must verify against the real DECOY_NOTIFY_WEBHOOK_SECRET"
    )

    event = json.loads(request["body"])
    assert event["kind"] == "run_completed"
    assert event["status"] == "success"
    assert event["row_count"] == 3
    assert "delivery_id" in event
