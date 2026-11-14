"""`decoy upgrade` failures carry fixed text and a code, never a quoted network or installer string.

A canary rides the `--url` (as a credential would) and the exception text; it must not appear in
the human, `--json` or `--quiet` output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import upgrade as upgrade_mod
from decoy.cli.exit_codes import EXIT_RUNTIME
from decoy.distribution import installer

runner = CliRunner()
CANARY = "CANARY-token-7d2f"
URL = f"https://user:{CANARY}@example.invalid/cli/version.json"


@pytest.fixture
def managed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upgrade_mod, "_managed_home", lambda: tmp_path)
    monkeypatch.setattr(upgrade_mod.release_key, "pinned_public_pem", lambda: "pem")


def _network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fetch(url: str) -> bytes:
        raise OSError(f"connect failed for {url} {CANARY}")

    monkeypatch.setattr(upgrade_mod, "_fetch", _fetch)


def _installer_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upgrade_mod, "_fetch", lambda url: b"AAAA")
    vd = upgrade_mod.vd
    monkeypatch.setattr(vd, "verify_document", lambda *a, **k: True)
    monkeypatch.setattr(vd, "parse_document", lambda b: {"latest": "99.0.0"})
    monkeypatch.setattr(vd, "newer_available", lambda *a, **k: True)
    monkeypatch.setattr(installer, "check_document_freshness", lambda *a, **k: None)

    def _install(**_kwargs):
        raise installer.InstallError(f"bundle at {CANARY} is broken")

    monkeypatch.setattr(installer, "install_version", _install)


@pytest.mark.parametrize("failure", [_network_failure, _installer_failure])
@pytest.mark.parametrize("flag", [None, "--json", "--quiet"], ids=["human", "json", "quiet"])
def test_a_failure_never_quotes_the_url_or_the_exception(
    managed: None, monkeypatch: pytest.MonkeyPatch, failure, flag: str | None
) -> None:
    failure(monkeypatch)

    result = runner.invoke(app, ["upgrade", "--url", URL, *([flag] if flag else [])])

    assert result.exit_code == EXIT_RUNTIME, result.output
    assert CANARY not in result.stdout + result.stderr
    assert "error: " in result.stderr or flag == "--json"
    if flag == "--json":
        payload = json.loads(result.stdout)
        assert payload["code"].startswith("upgrade_")
        assert CANARY not in json.dumps(payload)
