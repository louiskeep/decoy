"""AT-H2 (identity half): the artifact origin rule of `release_identity`.

A GitHub origin for `ARTIFACT_BASE` is refused unless `ARTIFACT_HOST_EXCEPTION` names a dated
owner decision. The shipped values pass. The signing commands that refuse before `release_key()`
arrive with S0a2; they call `release_identity.validate()`.
"""

from __future__ import annotations

import pytest

from decoy.distribution import release_identity as ri

GITHUB_BASES = (
    "https://github.com/decoy-data/decoy/releases/download",
    "https://objects.githubusercontent.com/decoy-data/decoy/releases/download",
    "https://release-assets.githubusercontent.com/decoy-data/decoy/releases/download",
    "https://GitHub.com/decoy-data/decoy/releases/download",
    "https://github.com./decoy-data/decoy/releases/download",
    "https://www.github.com/decoy-data/decoy/releases/download",
    "https://api.github.com/decoy-data/decoy/releases/download",
    "https://codeload.github.com/decoy-data/decoy/releases/download",
    "https://uploads.github.com/decoy-data/decoy/releases/download",
    "https://raw.githubusercontent.com./decoy-data/decoy/releases/download",
)
DATED = "owner 2026-11-18: V1 bundles are GitHub Release assets, a dated exception"


@pytest.mark.parametrize("base", GITHUB_BASES)
def test_artifact_origin_rule(base):
    with pytest.raises(ri.ReleaseIdentityError, match=r"^release_identity_mismatch$"):
        ri.check_artifact_origin(base, None)
    with pytest.raises(ri.ReleaseIdentityError):
        ri.check_artifact_origin(base, DATED)


@pytest.mark.parametrize(
    "exception",
    [
        "",
        "ok",
        "owner approved it",
        "owner 2026-13-40 bad date here",
        "2026-11-18 x" * 3,
        "owner 2026-11-18: xxxxxxxxxx",
        (ri.ARTIFACT_HOST_EXCEPTION or "") + " ",
    ],
)
def test_the_exact_base_needs_the_exact_registered_decision(exception):
    with pytest.raises(ri.ReleaseIdentityError):
        ri.check_artifact_origin(ri.ARTIFACT_BASE, exception)


@pytest.mark.parametrize(
    "base",
    [
        "https://someone.github.io/decoy/releases/download",
        "https://GitHub.io/decoy/releases/download",
        "https://x.GITHUB.IO./decoy/releases/download",
    ],
)
def test_github_io_is_github_hosted(base):
    with pytest.raises(ri.ReleaseIdentityError):
        ri.check_artifact_origin(base, ri.ARTIFACT_HOST_EXCEPTION)


@pytest.mark.parametrize(
    "base",
    [
        "https://user@downloads.example.invalid/cli",
        "https://user:pw@downloads.example.invalid/cli",
        "https://:pw@downloads.example.invalid/cli",
        "https://downloads.example.invalid:badport/cli",
    ],
)
def test_credentials_in_the_url_are_refused(base):
    with pytest.raises(ri.ReleaseIdentityError):
        ri.check_artifact_origin(base, None)


def test_shipped_values_pass_and_are_the_exact_owner_values():
    ri.validate()
    assert ri.ARTIFACT_BASE == "https://github.com/decoy-data/decoy/releases/download"
    assert ri.ARTIFACT_HOST_EXCEPTION is not None
    assert ri.ARTIFACT_HOST_EXCEPTION.startswith("owner 2026-11-18")


def test_removing_the_exception_fails_closed(monkeypatch):
    monkeypatch.setattr(ri, "ARTIFACT_HOST_EXCEPTION", None)
    with pytest.raises(ri.ReleaseIdentityError):
        ri.validate()


def test_a_non_github_https_origin_needs_no_exception():
    ri.check_artifact_origin("https://downloads.example.invalid/cli", None)


@pytest.mark.parametrize("base", ["http://downloads.example.invalid/cli", "downloads/cli", ""])
def test_a_non_https_origin_is_refused(base):
    with pytest.raises(ri.ReleaseIdentityError):
        ri.check_artifact_origin(base, DATED)


def test_artifact_url_layout():
    assert ri.artifact_url("1.0.0", "x.tar.gz", "https://h.invalid/b") == (
        "https://h.invalid/b/v1.0.0/x.tar.gz"
    )


def test_the_fixed_facts():
    assert (ri.CLI_REPO, ri.ENGINE_REPO, ri.WEB_REPO) == (
        "decoy-data/decoy",
        "decoy-data/decoy-engine",
        "decoy-data/decoy-web",
    )
    assert ri.SITE_ORIGIN == "https://trydecoy.com"
    assert ri.WEB_COMMIT_IDENTITY == ("ckeep", "decoy@trydecoy.com", "ckeep", "decoy@trydecoy.com")


@pytest.mark.parametrize(
    "base",
    [
        "https://github.com/someone/decoy/releases/download",
        "https://github.com/decoy-data/decoy-engine/releases/download",
        "https://github.com/decoy-data/decoy/releases/download/",
        "https://github.com/decoy-data/decoy/releases/download/extra",
        "https://objects.githubusercontent.com/decoy-data/decoy/releases/download",
    ],
)
def test_a_github_base_must_be_this_repos_download_base_even_with_the_exception(base):
    with pytest.raises(ri.ReleaseIdentityError, match=r"^release_identity_mismatch$"):
        ri.check_artifact_origin(base, ri.ARTIFACT_HOST_EXCEPTION)


def test_a_trailing_slash_is_not_the_artifact_url_base_but_is_joined_cleanly():
    assert ri.artifact_url("1", "n", "https://h.invalid/b/") == "https://h.invalid/b/v1/n"


def test_the_exact_github_base_passes_with_the_exception():
    ri.check_artifact_origin(ri.ARTIFACT_BASE, ri.ARTIFACT_HOST_EXCEPTION)
