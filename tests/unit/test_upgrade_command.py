"""`decoy upgrade`: resolve-and-plan, perform via an injected installer, and the
command surface (`--check`, `--json`, errors). No network and no real install.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy import _version_endpoint as ve
from decoy.cli import upgrade as up

runner = CliRunner()


def _doc(latest="9.9.9", target="linux-x86_64"):
    return ve.VersionDocument(
        latest=latest,
        artifacts={target: ve.Artifact(url=f"https://h/cli/{latest}/b.tar.gz", sha256="s", sig="g")},
    )


def test_plan_resolves_latest_artifact():
    plan = up.plan_upgrade(current="0.1.0", target="linux-x86_64", document=_doc())
    assert plan.error is None
    assert plan.up_to_date is False
    assert plan.resolved_version == "9.9.9"
    assert plan.artifact is not None


def test_plan_up_to_date():
    plan = up.plan_upgrade(current="9.9.9", target="linux-x86_64", document=_doc())
    assert plan.up_to_date is True
    assert plan.error is None


def test_plan_pinned_version_installs_even_if_equal():
    # A pinned --version is an explicit re-install, not a no-op.
    plan = up.plan_upgrade(
        current="9.9.9", target="linux-x86_64", document=_doc(), pinned_version="9.9.9"
    )
    assert plan.up_to_date is False
    assert plan.resolved_version == "9.9.9"


def test_plan_no_target_is_an_error():
    plan = up.plan_upgrade(current="0.1.0", target=None, document=_doc())
    assert plan.error is not None
    assert "no Decoy bundle target" in plan.error


def test_plan_no_document_is_an_error():
    plan = up.plan_upgrade(current="0.1.0", target="linux-x86_64", document=None)
    assert plan.error is not None
    assert "version endpoint" in plan.error


def test_plan_missing_artifact_for_target_is_an_error():
    # Document names a latest but no bundle for this host's target.
    doc = ve.VersionDocument(latest="9.9.9", artifacts={})
    plan = up.plan_upgrade(current="0.1.0", target="macos-arm64", document=doc)
    assert plan.error is not None
    assert "no bundle for macos-arm64" in plan.error


def test_perform_upgrade_invokes_installer_with_resolved_version():
    calls = []

    def fake_runner(version, target, artifact, version_url):
        calls.append((version, target, artifact.url, version_url))

    plan = up.plan_upgrade(current="0.1.0", target="linux-x86_64", document=_doc())
    up.perform_upgrade(plan, version_url="https://h/cli/version.json", installer_runner=fake_runner)
    assert calls == [("9.9.9", "linux-x86_64", "https://h/cli/9.9.9/b.tar.gz", "https://h/cli/version.json")]


def test_perform_upgrade_refuses_a_broken_plan():
    plan = up.plan_upgrade(current="0.1.0", target=None, document=_doc())
    with pytest.raises(RuntimeError):
        up.perform_upgrade(plan, version_url="https://h/cli/version.json", installer_runner=lambda *a: None)


# --- B1: no silent downgrade / rollback ------------------------------------


def test_plan_unpinned_refuses_a_served_lower_latest():
    # A document that serves a `latest` LOWER than installed (a signed rollback /
    # replay) installs nothing: there is nothing newer to move to.
    plan = up.plan_upgrade(current="0.12.0", target="linux-x86_64", document=_doc(latest="0.1.0"))
    assert plan.up_to_date is True
    assert plan.error is None


def test_plan_unpinned_incomparable_latest_installs_nothing():
    # A `latest` that is not a valid version cannot be proven newer, so fail
    # closed: no install.
    plan = up.plan_upgrade(
        current="0.12.0", target="linux-x86_64", document=_doc(latest="not-a-version")
    )
    assert plan.up_to_date is True
    assert plan.error is None


def test_plan_pinned_downgrade_refused_without_ack():
    plan = up.plan_upgrade(
        current="0.12.0",
        target="linux-x86_64",
        document=_doc(latest="0.1.0"),
        pinned_version="0.1.0",
    )
    assert plan.error is not None
    assert "downgrade" in plan.error.lower()
    assert plan.up_to_date is False


def test_plan_pinned_downgrade_allowed_with_ack():
    plan = up.plan_upgrade(
        current="0.12.0",
        target="linux-x86_64",
        document=_doc(latest="0.1.0"),
        pinned_version="0.1.0",
        allow_downgrade=True,
    )
    assert plan.error is None
    assert plan.up_to_date is False
    assert plan.resolved_version == "0.1.0"
    assert plan.artifact is not None


def test_plan_refuses_a_yanked_resolved_version():
    doc = ve.VersionDocument(
        latest="9.9.9",
        yanked=("9.9.9",),
        artifacts={"linux-x86_64": ve.Artifact(url="https://h/cli/9.9.9/b.tar.gz", sha256="s", sig="g")},
    )
    plan = up.plan_upgrade(current="0.1.0", target="linux-x86_64", document=doc)
    assert plan.error is not None
    assert "yanked" in plan.error.lower()


# --- command surface --------------------------------------------------------


def _patch(monkeypatch, *, target="linux-x86_64", document, runner_calls=None):
    monkeypatch.setattr(ve, "detect_target", lambda: target)
    monkeypatch.setattr(up._version_endpoint, "detect_target", lambda: target)
    monkeypatch.setattr(up._version_endpoint, "fetch_document", lambda url: document)

    def fake_validated(url):
        # The executing path fails closed; model an unreachable endpoint as the
        # strict fetch raising, same as the real client.
        if document is None:
            raise ve.VersionDocumentError("could not reach the Decoy version endpoint")
        return document

    monkeypatch.setattr(up._version_endpoint, "fetch_document_validated", fake_validated)

    def fake_default_runner(version, tgt, artifact, version_url):
        if runner_calls is not None:
            runner_calls.append((version, tgt))

    monkeypatch.setattr(up, "_default_installer_runner", fake_default_runner)


def _app():
    from decoy.__main__ import app

    return app


def test_command_check_reports_available(monkeypatch):
    _patch(monkeypatch, document=_doc(latest="9.9.9"))
    result = runner.invoke(_app(), ["upgrade", "--check", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "check"
    assert payload["update_available"] is True
    assert payload["latest"] == "9.9.9"


def test_command_installs_and_reports(monkeypatch):
    calls = []
    _patch(monkeypatch, document=_doc(latest="9.9.9"), runner_calls=calls)
    result = runner.invoke(_app(), ["upgrade", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["action"] == "installed"
    assert payload["installed"] == "9.9.9"
    assert calls == [("9.9.9", "linux-x86_64")]


def test_command_up_to_date_installs_nothing(monkeypatch):
    calls = []
    from decoy import __version__

    _patch(monkeypatch, document=_doc(latest=__version__), runner_calls=calls)
    result = runner.invoke(_app(), ["upgrade", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["action"] == "none"
    assert calls == []


def test_command_unsupported_target_errors(monkeypatch):
    _patch(monkeypatch, target=None, document=_doc())
    result = runner.invoke(_app(), ["upgrade", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"


def test_command_endpoint_unreachable_errors(monkeypatch):
    _patch(monkeypatch, document=None)
    result = runner.invoke(_app(), ["upgrade", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"


def test_command_unpinned_served_lower_latest_installs_nothing(monkeypatch):
    # B1 at the command surface: __version__ is 0.1.0; a document serving an
    # older latest must install nothing, never downgrade.
    calls = []
    _patch(monkeypatch, document=_doc(latest="0.0.1"), runner_calls=calls)
    result = runner.invoke(_app(), ["upgrade", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["action"] == "none"
    assert calls == []


def test_command_malformed_document_fails_closed(monkeypatch):
    # M3: the executing path validates and fails closed; a strict-fetch failure
    # becomes a clean error, nothing is installed.
    calls = []
    monkeypatch.setattr(up._version_endpoint, "detect_target", lambda: "linux-x86_64")

    def boom(url):
        raise ve.VersionDocumentError("the version document does not match the published schema")

    monkeypatch.setattr(up._version_endpoint, "fetch_document_validated", boom)
    monkeypatch.setattr(
        up, "_default_installer_runner", lambda *a: calls.append(a)
    )
    result = runner.invoke(_app(), ["upgrade", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "schema" in payload["error"]
    assert calls == []


# --- B2: the REAL runner never downloads the installer; origin is pinned -----
#
# These drive `_default_installer_runner` itself (not monkeypatched): the one
# code path that the command tests above stub out. `subprocess.run` is captured
# so no install actually runs, and `urlopen` is booby-trapped so any attempt to
# fetch a remote install.sh fails the test.


@pytest.fixture
def no_network(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("the upgrade runner must never make a network request")

    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.fixture
def capture_run(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

    monkeypatch.setattr(up.subprocess, "run", fake_run)
    return calls


_VERSION_URL = "https://decoy.dev/cli/version.json"


def test_real_runner_refuses_non_https_artifact(no_network, capture_run):
    art = ve.Artifact(url="http://decoy.dev/cli/9.9.9/b.tar.gz", sha256="s", sig="g")
    with pytest.raises(RuntimeError, match="non-https"):
        up._default_installer_runner("9.9.9", "linux-x86_64", art, _VERSION_URL)
    assert capture_run == []


def test_real_runner_refuses_file_url_artifact(no_network, capture_run):
    art = ve.Artifact(url="file:///etc/passwd", sha256="s", sig="g")
    with pytest.raises(RuntimeError, match="non-https"):
        up._default_installer_runner("9.9.9", "linux-x86_64", art, _VERSION_URL)
    assert capture_run == []


def test_real_runner_refuses_cross_origin_artifact(no_network, capture_run):
    art = ve.Artifact(url="https://evil.example/cli/9.9.9/b.tar.gz", sha256="s", sig="g")
    with pytest.raises(RuntimeError, match="origin"):
        up._default_installer_runner("9.9.9", "linux-x86_64", art, _VERSION_URL)
    assert capture_run == []


def test_real_runner_refuses_cross_origin_base_url_override(no_network, capture_run, monkeypatch):
    monkeypatch.setenv("DECOY_INSTALL_BASE_URL", "https://evil.example/cli")
    art = ve.Artifact(url="https://decoy.dev/cli/9.9.9/b.tar.gz", sha256="s", sig="g")
    with pytest.raises(RuntimeError, match="origin"):
        up._default_installer_runner("9.9.9", "linux-x86_64", art, _VERSION_URL)
    assert capture_run == []


@pytest.mark.skipif(
    __import__("platform").system() == "Windows", reason="posix install.sh resolution"
)
def test_real_runner_runs_local_script_same_origin(no_network, capture_run, monkeypatch):
    # A valid, same-origin https artifact: the runner resolves the LOCAL install
    # script, pins the base URL to the endpoint's origin, and shells out to it.
    monkeypatch.delenv("DECOY_INSTALL_BASE_URL", raising=False)
    monkeypatch.delenv("DECOY_INSTALL_SCRIPT", raising=False)
    art = ve.Artifact(url="https://decoy.dev/cli/9.9.9/b.tar.gz", sha256="s", sig="g")
    up._default_installer_runner("9.9.9", "linux-x86_64", art, _VERSION_URL)
    assert len(capture_run) == 1
    cmd, kwargs = capture_run[0]
    assert cmd[0] == "sh"
    script = cmd[1]
    assert script.endswith("packaging/install/install.sh")
    assert Path(script).is_file()  # a real, local file (never downloaded)
    assert cmd[-2:] == ["--version", "9.9.9"]
    assert kwargs["env"]["DECOY_INSTALL_BASE_URL"] == "https://decoy.dev/cli"
