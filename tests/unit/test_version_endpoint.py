"""Version-document client: parse, compare, cache, notice gating, fail-silent.

No network and no engine: `fetch_document` and the notice take an injected
fetcher, and the comparison / parse / gating are pure.
"""

from __future__ import annotations

import json

from decoy import _version_endpoint as ve


def test_parse_full_document():
    data = {
        "schema_version": 1,
        "latest": "0.12.0",
        "min_supported": "0.10.0",
        "yanked": ["0.11.0"],
        "message": "security fix",
        "artifacts": {
            "linux-x86_64": {"url": "u", "sha256": "s", "sig": "g"},
        },
    }
    doc = ve.parse_document(data)
    assert doc.latest == "0.12.0"
    assert doc.min_supported == "0.10.0"
    assert doc.yanked == ("0.11.0",)
    assert doc.message == "security fix"
    art = doc.artifact_for("linux-x86_64")
    assert art is not None and art.url == "u" and art.sha256 == "s" and art.sig == "g"


def test_parse_degrades_on_garbage():
    # A non-object, and wrong-typed fields, must not raise.
    assert ve.parse_document("not a dict").latest is None
    doc = ve.parse_document({"latest": 123, "yanked": "nope", "artifacts": "nope"})
    assert doc.latest is None
    assert doc.yanked == ()
    assert doc.artifacts == {}


def test_parse_drops_incomplete_artifact():
    doc = ve.parse_document({"latest": "1.0.0", "artifacts": {"linux-x86_64": {"url": "u"}}})
    assert doc.artifact_for("linux-x86_64") is None


def test_fetch_document_fail_silent_on_error():
    def boom(url, timeout):
        raise OSError("network down")

    assert ve.fetch_document("https://x", opener=boom) is None


def test_fetch_document_parses_bytes():
    payload = json.dumps({"latest": "0.9.0"}).encode()
    doc = ve.fetch_document("https://x", opener=lambda u, t: payload)
    assert doc is not None and doc.latest == "0.9.0"


def test_fetch_document_bad_json_is_none():
    assert ve.fetch_document("https://x", opener=lambda u, t: b"{not json") is None


def test_update_decision_available():
    doc = ve.VersionDocument(latest="0.12.0")
    d = ve.compute_update_decision("0.10.0", doc)
    assert d.update_available is True
    assert d.notice_line is not None
    assert "0.12.0" in d.notice_line


def test_update_decision_up_to_date():
    doc = ve.VersionDocument(latest="0.12.0")
    d = ve.compute_update_decision("0.12.0", doc)
    assert d.update_available is False
    assert d.notice_line is None


def test_update_decision_ahead_of_latest():
    # A dev build ahead of the published latest is not "update available".
    doc = ve.VersionDocument(latest="0.12.0")
    d = ve.compute_update_decision("0.13.0", doc)
    assert d.update_available is False


def test_update_decision_yanked_and_min_supported():
    doc = ve.VersionDocument(latest="0.12.0", min_supported="0.11.0", yanked=("0.10.0",))
    d = ve.compute_update_decision("0.10.0", doc)
    assert d.current_is_yanked is True
    assert d.below_min_supported is True


def test_update_decision_none_document():
    d = ve.compute_update_decision("0.1.0", None)
    assert d.update_available is False and d.notice_line is None


def test_invalid_version_never_crashes():
    doc = ve.VersionDocument(latest="not-a-version")
    d = ve.compute_update_decision("0.1.0", doc)
    assert d.update_available is False


# --- notice gating ----------------------------------------------------------

_DOC = ve.VersionDocument(latest="9.9.9")


def _fetcher(url):
    return _DOC


def _notice(tmp_path, **over):
    kw = dict(
        current="0.1.0",
        argv=[],
        env={},
        isatty=True,
        cache_home=tmp_path,
        now=1000.0,
        fetcher=_fetcher,
    )
    kw.update(over)
    return ve.maybe_update_notice(**kw)


def test_notice_shown_when_interactive_and_newer(tmp_path):
    line = _notice(tmp_path)
    assert line is not None and "9.9.9" in line


def test_notice_suppressed_without_tty(tmp_path):
    assert _notice(tmp_path, isatty=False) is None


def test_notice_suppressed_under_ci(tmp_path):
    assert _notice(tmp_path, env={"CI": "true"}) is None


def test_notice_suppressed_on_json(tmp_path):
    assert _notice(tmp_path, argv=["run", "--json"]) is None


def test_notice_suppressed_on_quiet(tmp_path):
    assert _notice(tmp_path, argv=["run", "--quiet"]) is None


def test_notice_suppressed_by_flag(tmp_path):
    assert _notice(tmp_path, argv=["--no-update-check"]) is None


def test_notice_suppressed_by_env(tmp_path):
    assert _notice(tmp_path, env={ve.NO_UPDATE_CHECK_ENV: "1"}) is None


def test_notice_uses_cache_within_cadence(tmp_path):
    calls = []

    def counting_fetcher(url):
        calls.append(url)
        return _DOC

    # First call fetches and caches.
    assert _notice(tmp_path, fetcher=counting_fetcher) is not None
    assert len(calls) == 1
    # Second call within the cadence window reads the cache, no refetch.
    assert _notice(tmp_path, fetcher=counting_fetcher, now=1001.0) is not None
    assert len(calls) == 1


def test_notice_refreshes_after_cadence(tmp_path):
    calls = []

    def counting_fetcher(url):
        calls.append(url)
        return _DOC

    assert _notice(tmp_path, fetcher=counting_fetcher, now=1000.0) is not None
    assert len(calls) == 1
    later = 1000.0 + ve.DEFAULT_CADENCE_SECONDS + 1
    assert _notice(tmp_path, fetcher=counting_fetcher, now=later) is not None
    assert len(calls) == 2


def test_notice_fetch_failure_is_silent(tmp_path):
    assert _notice(tmp_path, fetcher=lambda u: None) is None


def test_detect_target_returns_a_known_key_or_none():
    # On this host it is either a supported key or None; never a crash.
    target = ve.detect_target()
    assert target in {None, "linux-x86_64", "linux-aarch64", "macos-arm64", "windows-x86_64"}
