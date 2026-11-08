"""The CI binary fetcher retries a transient network failure and nothing else."""

from __future__ import annotations

import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "fetch_ci_binary.py"
_spec = importlib.util.spec_from_file_location("fetch_ci_binary", SCRIPT)
assert _spec and _spec.loader
fcb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fcb)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


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
        urllib.error.URLError("reset"),
        _http(504),
        ConnectionResetError(),
    ],
    ids=["timeout", "urlerror", "http504", "reset"],
)
def test_a_transient_failure_is_retried(monkeypatch: pytest.MonkeyPatch, first: OSError) -> None:
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


@pytest.mark.parametrize("code", [403, 404])
def test_a_client_error_is_not_retried(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    calls = _patch(monkeypatch, [_http(code)])
    with pytest.raises(urllib.error.HTTPError):
        fcb.download("https://x", sleep=lambda _s: pytest.fail("no wait on a client error"))
    assert len(calls) == 1
