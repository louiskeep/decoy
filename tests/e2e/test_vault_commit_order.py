"""A vault (or token map) is durable BEFORE any masked output is published.

Masked output without its vault cannot be reversed, so `decoy run --vault` publishes the vault
first and only then the outputs. The engine owns the publish (0.24.0): a private stage, fsync,
an exclusive link, a directory fsync. An existing vault is refused (exit 1), never overwritten.
A failed write exits 3, writes no output and shows no path. `decoy tokenize` commits its token
map before it writes output, for the same reason.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytest.importorskip("cryptography")
pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()
SOURCE = ["alice@example.com", "bob@example.com", "carol@example.com"]
CANARY = "canary-vault-9b2d"


@pytest.fixture
def mask_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV

    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    return TEST_MASK_SECRET_REF


def _pipeline(root: Path, *, strategy: str = "hash") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    src = root / "a.csv"
    pd.DataFrame({"email": SOURCE}).to_csv(src, index=False)
    column: dict = {"name": "email", "strategy": strategy, "namespace": "em"}
    if strategy == "hash":
        column["vault"] = True
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [column]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": str(root / "out.csv")}},
    }
    path = root / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _vault_failed_text() -> str:
    from decoy.cli import run as run_mod

    return getattr(run_mod, "VAULT_WRITE_FAILED", "<no VAULT_WRITE_FAILED constant>")


def _leftovers(directory: Path, vault_name: str) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name.startswith(f".{vault_name}"))


def _fail_vault_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from decoy_engine.vault import VaultWriter

    def _boom(self, path):
        raise OSError(28, f"No space left on device: {CANARY}")

    monkeypatch.setattr(VaultWriter, "write", _boom)


def _fail_directory_fsync(monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.fsync

    def _fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(5, f"Input/output error: {CANARY}")
        real(fd)

    monkeypatch.setattr(os, "fsync", _fsync)


def _assert_no_output(result, root: Path, vault: Path, text: str) -> None:
    assert not list(root.rglob("out.csv")), "masked output was published without its vault"
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert " ".join(text.split()) in " ".join(result.output.split())
    assert CANARY not in result.output
    assert _leftovers(vault.parent, vault.name) == []


def test_a_failed_vault_write_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _pipeline(tmp_path)
    vault = tmp_path / "vault.bin"
    _fail_vault_write(monkeypatch)
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault), *extra])
        _assert_no_output(result, tmp_path, vault, _vault_failed_text())
        assert not vault.exists()


def test_a_failed_directory_fsync_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine reports its own coded failure; the CLI writes no output after it."""
    cfg = _pipeline(tmp_path)
    vault = tmp_path / "vault.bin"
    _fail_directory_fsync(monkeypatch)
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
    _assert_no_output(result, tmp_path, vault, "vault_commit_failed")


def test_an_existing_vault_is_refused_and_left_alone(tmp_path: Path) -> None:
    vault = tmp_path / "vault.bin"
    first = runner.invoke(app, ["run", str(_pipeline(tmp_path / "first")), "--vault", str(vault)])
    assert first.exit_code == 0, first.output
    before = vault.read_bytes()
    root = tmp_path / "second"
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(_pipeline(root)), "--vault", str(vault), *extra])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "vault_exists" in result.output
        assert not list(root.rglob("out.csv")), "masked output was published without its vault"
        assert vault.read_bytes() == before, "the existing vault was replaced or removed"
        assert _leftovers(vault.parent, vault.name) == []


def test_run_writes_the_vault_durably_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vault is published first, with owner-only mode and no stage left behind."""
    from decoy_engine.vault import VaultWriter

    from decoy.cli.run import _execute as run_execute

    events: list[str] = []
    real_outputs, real_write = run_execute._write_mask_outputs, VaultWriter.write
    vault = tmp_path / "vault.bin"

    def _outputs(*a, **k):
        events.append("outputs")
        return real_outputs(*a, **k)

    def _write(self, path):
        events.append("vault_write")
        return real_write(self, path)

    monkeypatch.setattr(run_execute, "_write_mask_outputs", _outputs)
    monkeypatch.setattr(VaultWriter, "write", _write)
    result = runner.invoke(app, ["run", str(_pipeline(tmp_path)), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert events[: events.index("outputs") + 1] == ["vault_write", "outputs"]
    assert vault.exists()
    assert stat.S_IMODE(vault.stat().st_mode) == 0o600
    assert _leftovers(tmp_path, vault.name) == []


def test_tokenize_commits_the_token_map_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import _token_vault
    from decoy.cli import run as run_mod

    events: list[str] = []
    real_outputs, real_commit = run_mod._write_mask_outputs, _token_vault.LocalTokenVault.commit

    def _outputs(*a, **k):
        events.append("outputs")
        return real_outputs(*a, **k)

    def _commit(self):
        events.append("commit")
        return real_commit(self)

    monkeypatch.setattr(run_mod, "_write_mask_outputs", _outputs)
    monkeypatch.setattr(_token_vault.LocalTokenVault, "commit", _commit)
    cfg = _pipeline(tmp_path, strategy="tokenize")
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "tokens.db")])
    assert result.exit_code == 0, result.output
    assert events == ["commit", "outputs"]


def test_tokenize_failed_commit_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import _token_vault

    def _boom(self):
        raise OSError(28, f"No space left on device: {CANARY}")

    monkeypatch.setattr(_token_vault.LocalTokenVault, "commit", _boom)
    cfg = _pipeline(tmp_path, strategy="tokenize")
    vault = tmp_path / "tokens.db"
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert CANARY not in result.output
    assert not (tmp_path / "out.csv").exists(), "tokenized output was published uncommitted"
    assert not vault.exists()
