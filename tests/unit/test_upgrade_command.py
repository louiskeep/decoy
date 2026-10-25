"""`decoy upgrade`: resolve-and-plan, perform via an injected installer, and the
command surface (`--check`, `--json`, errors). No network and no real install.
"""

from __future__ import annotations

import json

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

    def fake_runner(version, target, artifact):
        calls.append((version, target, artifact.url))

    plan = up.plan_upgrade(current="0.1.0", target="linux-x86_64", document=_doc())
    up.perform_upgrade(plan, installer_runner=fake_runner)
    assert calls == [("9.9.9", "linux-x86_64", "https://h/cli/9.9.9/b.tar.gz")]


def test_perform_upgrade_refuses_a_broken_plan():
    plan = up.plan_upgrade(current="0.1.0", target=None, document=_doc())
    with pytest.raises(RuntimeError):
        up.perform_upgrade(plan, installer_runner=lambda *a: None)


# --- command surface --------------------------------------------------------


def _patch(monkeypatch, *, target="linux-x86_64", document, runner_calls=None):
    monkeypatch.setattr(ve, "detect_target", lambda: target)
    monkeypatch.setattr(up._version_endpoint, "detect_target", lambda: target)
    monkeypatch.setattr(up._version_endpoint, "fetch_document", lambda url: document)

    def fake_default_runner(version, tgt, artifact):
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
