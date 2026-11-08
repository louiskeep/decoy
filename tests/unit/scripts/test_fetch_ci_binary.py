"""The CI binary fetcher retries a transient network failure and nothing else."""

from __future__ import annotations

import http.client
import importlib.util
import io
import socket
import ssl
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "fetch_ci_binary.py"
_spec = importlib.util.spec_from_file_location("fetch_ci_binary", SCRIPT)
assert _spec and _spec.loader
fcb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fcb)

CUT = b"<cut off mid-read>"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def read(self, *args: object) -> bytes:  # type: ignore[override]
        if self.getvalue() == CUT:
            raise http.client.IncompleteRead(b"partial", 100)
        return super().read()


def _patch(monkeypatch: pytest.MonkeyPatch, outcomes: list[object]) -> list[str]:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float):
        calls.append(url)
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _Response(outcome)

    monkeypatch.setattr(fcb.urllib.request, "urlopen", fake_urlopen)
    return calls


def _http(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "x", {}, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "first",
    [
        TimeoutError("read timed out"),
        ConnectionResetError(),
        urllib.error.URLError(TimeoutError("timed out")),
        urllib.error.URLError(ConnectionResetError()),
        urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, "try again")),
        _http(500),
        _http(503),
        _http(504),
        CUT,
    ],
    ids=[
        "timeout",
        "reset",
        "url-timeout",
        "url-reset",
        "dns-again",
        "http500",
        "http503",
        "http504",
        "cut-mid-read",
    ],
)
def test_a_transient_failure_is_retried(monkeypatch: pytest.MonkeyPatch, first: object) -> None:
    calls = _patch(monkeypatch, [first, b"ok"])
    waits: list[float] = []
    assert fcb.download("https://x", sleep=waits.append) == b"ok"
    assert len(calls) == 2 and waits == [fcb.BACKOFF_SECONDS[0]]


def test_the_last_failure_is_raised_after_every_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, [TimeoutError()] * fcb.ATTEMPTS)
    waits: list[float] = []
    with pytest.raises(TimeoutError):
        fcb.download("https://x", sleep=waits.append)
    assert len(calls) == fcb.ATTEMPTS and len(waits) == fcb.ATTEMPTS - 1


@pytest.mark.parametrize(
    "err",
    [
        _http(403),
        _http(404),
        _http(429),
        _http(499),
        urllib.error.URLError(ssl.SSLCertVerificationError("bad cert")),
        urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, "no such host")),
        urllib.error.URLError(FileNotFoundError("missing")),
        urllib.error.URLError("unknown url type"),
    ],
    ids=[
        "http403",
        "http404",
        "http429",
        "http499",
        "cert",
        "dns-noname",
        "file-missing",
        "scheme",
    ],
)
def test_a_permanent_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch, err: OSError) -> None:
    calls = _patch(monkeypatch, [err])
    with pytest.raises(type(err)):
        fcb.download("https://x", sleep=lambda _s: pytest.fail("no wait on a permanent failure"))
    assert len(calls) == 1


def test_main_reports_a_cut_off_body_as_a_clean_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, [CUT] * fcb.ATTEMPTS)
    monkeypatch.setattr(fcb.time, "sleep", lambda _s: None)
    policy = tmp_path / "policy.toml"
    policy.write_text('[[binary_tool]]\nname = "tool"\nurl = "https://x"\nsha256 = "0"\n')
    assert fcb.main(["tool", "--dest", str(tmp_path / "bin"), "--policy", str(policy)]) == 1
    assert "IncompleteRead" in capsys.readouterr().err
